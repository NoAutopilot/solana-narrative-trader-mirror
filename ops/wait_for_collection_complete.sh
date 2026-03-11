#!/usr/bin/env bash
# wait_for_collection_complete.sh — Poll until feature_tape_v1 reaches 96 fires,
# then trigger post_collection_ops.sh automatically.
# Run in background: nohup /root/solana_trader/ops/wait_for_collection_complete.sh &
set -euo pipefail

TARGET_FIRES=96
POLL_INTERVAL=60  # seconds between checks
LOG_FILE="/var/log/solana_trader/post_collection_ops.log"
OPS_SCRIPT="/root/solana_trader/ops/post_collection_ops.sh"
DB="/root/solana_trader/data/solana_trader.db"

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WATCHER $*" | tee -a "$LOG_FILE"; }

log "=== wait_for_collection_complete.sh START (target=$TARGET_FIRES fires, poll=${POLL_INTERVAL}s) ==="

while true; do
    FIRES=$(python3 -c "
import sqlite3
db = '$DB'
try:
    con = sqlite3.connect('file:' + db + '?mode=ro', uri=True, timeout=5)
    n = con.execute('SELECT COUNT(DISTINCT fire_id) FROM feature_tape_v1').fetchone()[0]
    con.close()
    print(n)
except Exception as e:
    print(0)
" 2>/dev/null || echo 0)

    log "fires=$FIRES/$TARGET_FIRES"

    if [[ "$FIRES" -ge "$TARGET_FIRES" ]]; then
        log "Target reached: $FIRES fires. Triggering post_collection_ops.sh..."
        bash "$OPS_SCRIPT" 2>&1 | tee -a "$LOG_FILE"
        log "post_collection_ops.sh complete. Watcher exiting."
        exit 0
    fi

    sleep "$POLL_INTERVAL"
done
