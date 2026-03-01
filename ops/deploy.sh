#!/usr/bin/env bash
# ops/deploy.sh <sha>
# Deploy a specific commit from GitHub to the VPS and restart the service.
# Usage:
#   ./ops/deploy.sh f0cf7f2          # deploy exact short or full SHA
#   ./ops/deploy.sh HEAD             # deploy current local HEAD
#
# Requires:
#   - SSH key at ~/.ssh/manus_vps_key (or set VPS_KEY env var)
#   - VPS reachable at VPS_HOST (default: root@142.93.24.227)
#   - /root/solana_trader on VPS is a git repo with origin configured
#
# Exit codes:
#   0  success
#   1  bad usage or pre-flight failure
#   2  deploy failure

set -euo pipefail

VPS_HOST="${VPS_HOST:-root@142.93.24.227}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/manus_vps_key}"
VPS_DIR="/root/solana_trader"
SERVICE="solana-trader.service"
SSH_OPTS="-i ${VPS_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=20"

# ── 1. Argument check ────────────────────────────────────────────────────────
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <sha>" >&2
    echo "  sha: git commit hash (short or full) or HEAD" >&2
    exit 1
fi

TARGET_SHA="$1"

# Resolve HEAD to actual hash if needed
if [[ "$TARGET_SHA" == "HEAD" ]]; then
    TARGET_SHA="$(git rev-parse HEAD)"
fi

echo "=== DEPLOY: target sha=${TARGET_SHA:0:7} ==="
echo "    VPS: ${VPS_HOST}:${VPS_DIR}"
echo "    Service: ${SERVICE}"
echo ""

# ── 2. Verify the commit exists in local repo ────────────────────────────────
if ! git cat-file -e "${TARGET_SHA}^{commit}" 2>/dev/null; then
    echo "ERROR: commit '${TARGET_SHA}' not found in local repo. Did you push?" >&2
    exit 1
fi

FULL_SHA="$(git rev-parse "${TARGET_SHA}")"
SHORT_SHA="${FULL_SHA:0:7}"
echo "Resolved: ${SHORT_SHA} (${FULL_SHA})"

# ── 3. Export the file tree at that commit as a tarball ──────────────────────
TMPTAR="/tmp/solana_trader_deploy_${SHORT_SHA}.tar.gz"
echo "Packing archive from git tree ${SHORT_SHA}..."
git archive --format=tar.gz "${FULL_SHA}" -o "${TMPTAR}"
echo "Archive: ${TMPTAR} ($(du -sh "${TMPTAR}" | cut -f1))"

# ── 4. Copy archive to VPS ───────────────────────────────────────────────────
echo "Copying to VPS..."
scp ${SSH_OPTS} "${TMPTAR}" "${VPS_HOST}:/tmp/solana_trader_deploy.tar.gz"

# ── 5. On VPS: backup, extract, stamp commit, restart ───────────────────────
echo "Deploying on VPS..."
# shellcheck disable=SC2087
ssh ${SSH_OPTS} "${VPS_HOST}" bash -s <<REMOTE
set -euo pipefail
cd "${VPS_DIR}"

echo "  [VPS] Backing up current file..."
cp et_shadow_trader_v1.py "et_shadow_trader_v1.py.bak_deploy_\$(date +%Y%m%d_%H%M%S)"

echo "  [VPS] Extracting archive..."
tar -xzf /tmp/solana_trader_deploy.tar.gz --overwrite

echo "  [VPS] Stamping deployed commit..."
echo "${FULL_SHA}" > .deployed_sha
echo "  [VPS] Deployed SHA: \$(cat .deployed_sha | cut -c1-7)"

echo "  [VPS] Syntax check..."
python3 -m py_compile et_shadow_trader_v1.py && echo "  [VPS] Syntax OK"

echo "  [VPS] Restarting service..."
systemctl restart "${SERVICE}"
sleep 5
systemctl status "${SERVICE}" --no-pager | head -6

echo "  [VPS] Done."
REMOTE

# ── 6. Cleanup ───────────────────────────────────────────────────────────────
rm -f "${TMPTAR}"

echo ""
echo "=== DEPLOY COMPLETE: ${SHORT_SHA} ==="
echo "Run ./ops/status.sh to verify."
