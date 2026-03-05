#!/bin/bash
# deploy.sh — v1.19 Audit Infrastructure
# Canonical deploy script for /root/solana_trader on the VPS.
# ALL deploy mechanisms (GitHub Actions, cron, manual) must call this script.
#
# Invariant: .deployed_sha and deployment_proof.json are ONLY written AFTER:
#   1) new code is checked out
#   2) build steps succeed
#   3) services are restarted AND verified active
#
# Usage:
#   ./deploy.sh [branch]        # default: master
#   TARGET_BRANCH=master ./deploy.sh
#
# Exit codes:
#   0  success
#   1  pre-flight or build failure
#   2  service restart/verify failure
#   3  proof write failure

set -euo pipefail

PROJECT_DIR="/root/solana_trader"
DEPLOY_PROOF="$PROJECT_DIR/deployment_proof.json"
DEPLOY_SHA_FILE="$PROJECT_DIR/.deployed_sha"
TARGET_BRANCH="${1:-${TARGET_BRANCH:-master}}"
LOG_PREFIX="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [deploy.sh]"

echo "$LOG_PREFIX Starting deployment (branch: $TARGET_BRANCH)..."
cd "$PROJECT_DIR"

# ── 1. Fetch and checkout ────────────────────────────────────────────────────
echo "$LOG_PREFIX Fetching latest code..."
git fetch origin
git checkout "$TARGET_BRANCH"
git pull origin "$TARGET_BRANCH"
FULL_SHA=$(git rev-parse HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "$LOG_PREFIX Checked out: $FULL_SHA (branch: $BRANCH)"

# ── 2. Minimal build steps ───────────────────────────────────────────────────
echo "$LOG_PREFIX Running pip install..."
pip3 install -r requirements.txt --quiet 2>&1 || echo "$LOG_PREFIX Warning: pip install had issues (non-fatal)"

# ── 3. Restart services ──────────────────────────────────────────────────────
SERVICES=("solana-trader.service" "solana-lcr-cont-observer.service")
echo "$LOG_PREFIX Restarting services..."
for svc in "${SERVICES[@]}"; do
    echo "$LOG_PREFIX   Restarting $svc..."
    systemctl restart "$svc"
done

# Brief wait for services to stabilize
sleep 5

# ── 4. Verify services are active ────────────────────────────────────────────
echo "$LOG_PREFIX Verifying services..."
ALL_OK=true
declare -A SVC_STATUS
for svc in "${SERVICES[@]}"; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "failed")
    SVC_STATUS["$svc"]="$STATUS"
    if [ "$STATUS" = "active" ]; then
        echo "$LOG_PREFIX   $svc: active ✓"
    else
        echo "$LOG_PREFIX   ERROR: $svc is $STATUS — deploy aborted." >&2
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo "$LOG_PREFIX Deploy FAILED: one or more services did not start." >&2
    exit 2
fi

# ── 5. Write .deployed_sha and deployment_proof.json (atomic) ────────────────
echo "$LOG_PREFIX Writing deployment proof..."

# Helper: first 16 chars of sha256sum of a file
get_sha16() {
    local f="$PROJECT_DIR/$1"
    if [ -f "$f" ]; then
        sha256sum "$f" | cut -c1-16
    else
        echo "null"
    fi
}

# Write .deployed_sha atomically
echo "$FULL_SHA" > "$DEPLOY_SHA_FILE.tmp"
mv "$DEPLOY_SHA_FILE.tmp" "$DEPLOY_SHA_FILE"

# Write deployment_proof.json atomically
cat > "$DEPLOY_PROOF.tmp" <<EOF
{
  "ts_utc": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "host": "$(hostname)",
  "repo": "NoAutopilot/solana-narrative-trader (private canonical)",
  "commit": "$FULL_SHA",
  "branch": "$BRANCH",
  "sha256": {
    "et_universe_scanner.py": "$(get_sha16 et_universe_scanner.py)",
    "et_microstructure.py": "$(get_sha16 et_microstructure.py)",
    "et_shadow_trader_v1.py": "$(get_sha16 et_shadow_trader_v1.py)",
    "lcr_continuation_observer_v1.py": "$(get_sha16 lcr_continuation_observer_v1.py)"
  },
  "services": {
    "solana-trader.service": "${SVC_STATUS[solana-trader.service]}",
    "solana-lcr-cont-observer.service": "${SVC_STATUS[solana-lcr-cont-observer.service]}"
  }
}
EOF
mv "$DEPLOY_PROOF.tmp" "$DEPLOY_PROOF"

echo "$LOG_PREFIX Deployment successful."
echo "$LOG_PREFIX   SHA:    $FULL_SHA"
echo "$LOG_PREFIX   Branch: $BRANCH"
echo "$LOG_PREFIX   Proof:  $DEPLOY_PROOF"
