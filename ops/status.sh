#!/usr/bin/env bash
# ops/status.sh
# Print a full status snapshot of the VPS:
#   - Deployed commit hash (from .deployed_sha and git)
#   - Service status
#   - Latest run_id, version, signature from run_registry
#   - Key DB invariants (null_age, lane distribution, |E| rate)
#   - Last 3 RANK log lines
#
# Usage:
#   ./ops/status.sh
#
# Requires:
#   - SSH key at ~/.ssh/manus_vps_key (or set VPS_KEY env var)
#   - VPS reachable at VPS_HOST (default: root@142.93.24.227)

set -euo pipefail

VPS_HOST="${VPS_HOST:-root@142.93.24.227}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/manus_vps_key}"
VPS_DIR="/root/solana_trader"
SERVICE="solana-trader.service"
SSH_OPTS="-i ${VPS_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=20"
DB="/root/solana_trader/data/solana_trader.db"

echo "================================================================"
echo " SOLANA TRADER — VPS STATUS  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================"

# shellcheck disable=SC2087
ssh ${SSH_OPTS} "${VPS_HOST}" bash -s <<'REMOTE'
set -euo pipefail
VPS_DIR="/root/solana_trader"
DB="/root/solana_trader/data/solana_trader.db"
SERVICE="solana-trader.service"

echo ""
echo "── COMMIT ──────────────────────────────────────────────────────"
cd "${VPS_DIR}"
DEPLOYED_SHA="$(cat .deployed_sha 2>/dev/null | cut -c1-7 || echo 'NO_DEPLOYED_SHA')"
DEPLOYED_FULL="$(cat .deployed_sha 2>/dev/null || echo 'NO_DEPLOYED_SHA')"
echo "  deployed_sha:  ${DEPLOYED_SHA}  (GitHub master)"
echo "  full_sha:      ${DEPLOYED_FULL}"

echo ""
echo "── SERVICE ─────────────────────────────────────────────────────"
systemctl status "${SERVICE}" --no-pager | head -6

echo ""
echo "── RUN REGISTRY (latest 3) ─────────────────────────────────────"
python3 -c "
import sqlite3
conn = sqlite3.connect('${DB}', timeout=10)
rows = conn.execute('''
    SELECT run_id, start_ts, version, signature
    FROM run_registry
    ORDER BY start_ts DESC LIMIT 3
''').fetchall()
for r in rows:
    print(f'  run_id={r[0][:8]}  ts={r[1][:19]}  ver={r[2]}  sig={r[3]}')
conn.close()
"

echo ""
echo "── DB INVARIANTS ───────────────────────────────────────────────"
python3 -c "
import sqlite3, json
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('${DB}', timeout=10)

# Latest universe snapshot
snap = conn.execute('''
    SELECT snapshot_at, COUNT(*) as total,
           SUM(CASE WHEN age_hours IS NULL THEN 1 ELSE 0 END) as null_age,
           SUM(CASE WHEN pair_created_at IS NULL THEN 1 ELSE 0 END) as null_pca
    FROM universe_snapshot
    WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM universe_snapshot)
    GROUP BY snapshot_at
''').fetchone()
if snap:
    print(f'  snapshot:  {snap[0][:19]}  total={snap[1]}  null_age={snap[2]}  null_pca={snap[3]}')
else:
    print('  snapshot:  (no data)')

# |E|>=2 rate last 6h
cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
fires = conn.execute('''
    SELECT COUNT(*) as fires,
           SUM(CASE WHEN tradeable_count >= 2 THEN 1 ELSE 0 END) as e_ge2
    FROM selection_tick_log
    WHERE logged_at >= ?
''', (cutoff,)).fetchone()
total_fires = fires[0] or 0
e_ge2 = fires[1] or 0
rate = round(100 * e_ge2 / total_fires, 1) if total_fires > 0 else 0
print(f'  |E|>=2 rate (6h): {e_ge2}/{total_fires} fires = {rate}%')

# Top blocker
blockers = conn.execute('''
    SELECT rej_pf_stability, rej_anti_chase, rej_lane_pf_early, rej_lane_age,
           rej_lane_liq, rej_lane_vol, rej_rug
    FROM selection_tick_log
    WHERE logged_at >= ?
''', (cutoff,)).fetchall()
if blockers:
    totals = {
        'pf_stability': sum(r[0] or 0 for r in blockers),
        'anti_chase':   sum(r[1] or 0 for r in blockers),
        'pf_early':     sum(r[2] or 0 for r in blockers),
        'lane_age':     sum(r[3] or 0 for r in blockers),
        'lane_liq':     sum(r[4] or 0 for r in blockers),
        'lane_vol':     sum(r[5] or 0 for r in blockers),
        'rug':          sum(r[6] or 0 for r in blockers),
    }
    top = sorted(totals.items(), key=lambda x: -x[1])
    print('  top blockers (6h): ' + '  '.join(f'{k}={v}' for k, v in top[:4]))

conn.close()
"

echo ""
echo "── LAST 3 RANK LINES ───────────────────────────────────────────"
grep -a "RANK pullback_score_rank" "${VPS_DIR}/logs/et_shadow_trader_v1.log" 2>/dev/null \
    | grep -v "WHAT-IF" | tail -3 \
    | sed 's/^/  /'
echo ""
echo "── WHAT-IF (latest) ────────────────────────────────────────────"
grep -a "WHAT-IF gate relief" "${VPS_DIR}/logs/et_shadow_trader_v1.log" 2>/dev/null \
    | tail -1 | sed 's/^/  /'

echo ""
echo "================================================================"
REMOTE
