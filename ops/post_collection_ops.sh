#!/usr/bin/env bash
# post_collection_ops.sh — Execute all queued ops changes after feature_tape_v1 completes
# Triggered by: wait_for_collection_complete.sh when fires=96
# DO NOT run while feature_tape_v1 is still collecting.
#
# Actions:
#   1) Verify collection is complete (96 fires)
#   2) Stop backup timer
#   3) Deploy v4 backup script (zstd compression, 24h hourly retention)
#   4) Run retention cleanup (removes old uncompressed backups)
#   5) Run fresh compressed backup
#   6) Run restore test
#   7) Resume backup timer
#   8) Stop bare feature_tape_v1 process
#   9) Enable + start feature-tape-v1.service
#  10) Verify systemd service is running and collecting
#  11) Report off-box status
set -euo pipefail

LOG_FILE="/var/log/solana_trader/post_collection_ops.log"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"; }

log "=== post_collection_ops.sh START ==="

# ── 1) Verify collection complete ─────────────────────────────────────────
log "Step 1: Verifying collection complete..."
FIRES=$(python3 -c "
import sqlite3
db = '/root/solana_trader/data/solana_trader.db'
con = sqlite3.connect('file:' + db + '?mode=ro', uri=True, timeout=10)
n = con.execute('SELECT COUNT(DISTINCT fire_id) FROM feature_tape_v1').fetchone()[0]
con.close()
print(n)
")
log "  fires collected: $FIRES / 96"
if [[ "$FIRES" -lt 96 ]]; then
    log "ABORT: collection not complete ($FIRES/96). Do not run post_collection_ops until all 96 fires are in."
    exit 1
fi
log "  Collection complete: $FIRES fires confirmed."

# ── 2) Stop backup timer ──────────────────────────────────────────────────
log "Step 2: Stopping backup timer..."
systemctl stop solana-backup-sqlite.timer
systemctl stop solana-backup-sqlite.service 2>/dev/null || true
sleep 2
ps aux | grep backup_sqlite | grep -v grep && { log "WARN: backup process still running, waiting..."; sleep 10; } || true
log "  Backup timer stopped."

# ── 3) Deploy v4 backup script ────────────────────────────────────────────
log "Step 3: Deploying v4 backup script (zstd, 24h hourly)..."
cp /root/solana_trader/ops/backup_sqlite_v4.sh /root/solana_trader/ops/backup_sqlite.sh
chmod +x /root/solana_trader/ops/backup_sqlite.sh
grep 'KEEP_HOURLY_HOURS\|KEEP_15MIN_HOURS\|KEEP_DAILY_HOURS\|COMPRESSION' /root/solana_trader/ops/backup_sqlite.sh | head -5
log "  v4 script deployed."

# ── 4) Retention cleanup (remove old uncompressed backups) ────────────────
log "Step 4: Running retention cleanup..."
python3 - <<'PYEOF'
import os, glob, re
from datetime import datetime, timezone

BACKUP_ROOT = '/root/solana_trader/backups/sqlite'
NOW = datetime.now(timezone.utc)

KEEP_15MIN_HOURS = 6
KEEP_HOURLY_HOURS = 24
KEEP_DAILY_HOURS  = 24 * 7

ARCHIVED_DBS = {
    'observer_lcr_cont_v1', 'observer_pfm_cont_v1',
    'observer_pfm_rev_v1', 'post_bonding'
}

deleted = 0
kept = 0
freed_bytes = 0

for db_dir in sorted(glob.glob(f'{BACKUP_ROOT}/*/')):
    db_name = os.path.basename(db_dir.rstrip('/'))

    if db_name in ARCHIVED_DBS:
        # Keep all archived snapshots
        files = [f for f in glob.glob(f'{db_dir}*')
                 if (f.endswith('.db.zst') or f.endswith('.db'))
                 and not f.endswith('.sha256') and not f.endswith('.meta.json')]
        kept += len(files)
        continue

    # Active DBs: tiered retention
    files = sorted([f for f in glob.glob(f'{db_dir}*')
                    if (f.endswith('.db.zst') or f.endswith('.db'))
                    and not f.endswith('.sha256') and not f.endswith('.meta.json')])

    db_deleted = 0
    db_kept = 0
    for f in files:
        fname = os.path.basename(f)
        m = re.match(r'^(\d{8}T\d{6}Z)\.db(\.zst)?$', fname)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        except:
            continue
        age_h = (NOW - ts).total_seconds() / 3600

        if age_h <= KEEP_15MIN_HOURS:
            db_kept += 1
            continue
        if age_h <= KEEP_HOURLY_HOURS and ts.minute == 0:
            db_kept += 1
            continue
        if age_h <= KEEP_DAILY_HOURS and ts.hour == 0 and ts.minute == 0:
            db_kept += 1
            continue

        sz = os.path.getsize(f)
        freed_bytes += sz
        for ext in ['', '.sha256', '.meta.json', '.zst', '.zst.sha256', '.zst.meta.json']:
            fp = f + ext
            if os.path.exists(fp):
                os.remove(fp)
        db_deleted += 1
        deleted += 1

    kept += db_kept
    print(f'  {db_name}: kept={db_kept} deleted={db_deleted}')

print(f'Cleanup: kept={kept} deleted={deleted} freed={freed_bytes/1024/1024:.0f}MB')
PYEOF
log "  Retention cleanup done."

# ── 5) Fresh compressed backup ────────────────────────────────────────────
log "Step 5: Running fresh compressed backup..."
/root/solana_trader/ops/backup_sqlite.sh 15min 2>&1 | tee -a "$LOG_FILE"
log "  Fresh backup done."

# ── 6) Restore test ───────────────────────────────────────────────────────
log "Step 6: Running restore test..."
/root/solana_trader/ops/restore_test.sh solana_trader 2>&1 | tee -a "$LOG_FILE"
log "  Restore test done."

# ── 7) Resume backup timer ────────────────────────────────────────────────
log "Step 7: Resuming backup timer..."
systemctl start solana-backup-sqlite.timer
systemctl is-active solana-backup-sqlite.timer
log "  Backup timer resumed."

# ── 8) Stop bare feature_tape_v1 process ─────────────────────────────────
log "Step 8: Stopping bare feature_tape_v1 process..."
FT_PID=$(pgrep -f 'python3 /root/solana_trader/feature_tape_v1.py' || echo "")
if [[ -n "$FT_PID" ]]; then
    log "  Sending SIGTERM to PID $FT_PID..."
    kill -TERM "$FT_PID"
    # Wait up to 30s for graceful exit
    for i in $(seq 1 30); do
        sleep 1
        kill -0 "$FT_PID" 2>/dev/null || { log "  PID $FT_PID exited after ${i}s"; break; }
    done
    # Force kill if still running
    kill -0 "$FT_PID" 2>/dev/null && { log "  WARN: still running after 30s, sending SIGKILL"; kill -9 "$FT_PID"; } || true
else
    log "  No bare feature_tape_v1 process found (already exited)."
fi

# ── 9) Enable + start systemd service ────────────────────────────────────
log "Step 9: Enabling and starting feature-tape-v1.service..."
systemctl enable feature-tape-v1.service
systemctl start feature-tape-v1.service
sleep 5

# ── 10) Verify systemd service ────────────────────────────────────────────
log "Step 10: Verifying feature-tape-v1.service..."
systemctl is-active feature-tape-v1.service
NEW_PID=$(pgrep -f 'python3 /root/solana_trader/feature_tape_v1.py' || echo "")
log "  Service status: $(systemctl is-active feature-tape-v1.service)"
log "  New PID: ${NEW_PID:-NONE}"
if [[ -z "$NEW_PID" ]]; then
    log "WARN: feature_tape_v1.py not running under systemd — check journal"
    journalctl -u feature-tape-v1.service --no-pager -n 20
fi

# ── 11) Off-box sync + restore proof ─────────────────────────────────────
log "Step 11: Off-box backup sync..."
/root/solana_trader/ops/offbox_sync.sh 2>&1 | tee -a "$LOG_FILE" || \
    log "WARN: offbox_sync.sh exited non-zero — check /var/log/solana_trader/offbox_sync.log"

log "Step 11b: Off-box restore proof..."
/root/solana_trader/ops/offbox_restore_proof.sh solana_trader 2>&1 | tee -a "$LOG_FILE" || \
    log "WARN: offbox_restore_proof.sh failed — check /root/solana_trader/reports/ops/offbox_restore_proof.md"

# ── Final disk report ─────────────────────────────────────────────────────
log "=== FINAL DISK STATE ==="
df -h / | tee -a "$LOG_FILE"
du -sh /root/solana_trader/backups/sqlite/ 2>/dev/null | tee -a "$LOG_FILE"
du -sh /root/solana_trader/backups/sqlite/*/ 2>/dev/null | tee -a "$LOG_FILE"

log "=== post_collection_ops.sh COMPLETE ==="
