#!/usr/bin/env bash
# backup_sqlite.sh — Hot SQLite backup with zstd compression, SHA256, meta.json, tiered retention
# Safe for live DBs: uses SQLite online backup API via Python, then compresses with zstd
# Usage: ./backup_sqlite.sh [15min|hourly|daily]
# Called by systemd timer; tier argument used for retention labelling only.
#
# RETENTION POLICY (v4 — 2026-03-11, durable for 24GB VPS):
#
#   ACTIVE DBs (solana_trader — live, growing):
#     15-min backups : keep 6h    (~24 copies × ~30MB compressed = ~0.7GB)
#     hourly backups : keep 24h   (~24 copies × ~30MB compressed = ~0.7GB)
#     daily backups  : keep 7d    (~7  copies × ~30MB compressed = ~0.2GB)
#     Steady state   : ~1.6GB (vs 18GB uncompressed) — well within 24GB disk
#
#   ARCHIVED / STATIC DBs (observer_*, post_bonding — no active writes):
#     Keep ONE immutable local snapshot (compressed)
#     No 15-min backups, no hourly backups
#
# COMPRESSION: zstd -3 (fast, ~8:1 ratio on SQLite files)
# OUTPUT: <timestamp>.db.zst + <timestamp>.db.zst.sha256 + <timestamp>.db.zst.meta.json
#
# OFF-BOX: rclone sync configured separately (see ops/offbox_backup.sh)
# Local durability only until off-box credentials are configured.
set -euo pipefail

TIER="${1:-15min}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="/root/solana_trader/backups/sqlite"
LOG_FILE="/var/log/solana_trader/backup_sqlite.log"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"; }
log "=== backup_sqlite.sh START tier=$TIER ts=$TIMESTAMP ==="

# ── ACTIVE DBs — backed up every 15 min ───────────────────────────────────
declare -A ACTIVE_DBS=(
    ["solana_trader"]="/root/solana_trader/data/solana_trader.db"
)

# ── ARCHIVED / STATIC DBs — one immutable snapshot only ───────────────────
declare -A ARCHIVED_DBS=(
    ["observer_lcr_cont_v1"]="/root/solana_trader/data/observer_lcr_cont_v1.db"
    ["observer_pfm_cont_v1"]="/root/solana_trader/data/observer_pfm_cont_v1.db"
    ["observer_pfm_rev_v1"]="/root/solana_trader/data/observer_pfm_rev_v1.db"
    ["post_bonding"]="/root/solana_trader/data/post_bonding.db"
)

BACKUP_OK=0
BACKUP_FAIL=0

# ── Helper: backup one DB ──────────────────────────────────────────────────
backup_db() {
    local DB_NAME="$1"
    local SRC="$2"
    local DEST_DIR="$BACKUP_ROOT/$DB_NAME"
    mkdir -p "$DEST_DIR"

    if [[ ! -f "$SRC" ]]; then
        log "SKIP $DB_NAME — not found at $SRC"
        return 0
    fi

    local TMP_DB
    TMP_DB="$(mktemp /tmp/backup_${DB_NAME}_XXXXXX.db)"
    local DEST_FILE="$DEST_DIR/${TIMESTAMP}.db.zst"

    log "Backing up $DB_NAME ($SRC) -> $DEST_FILE"

    # Hot backup via Python sqlite3 online backup API
    python3 - <<PYEOF
import sqlite3, sys
src = "$SRC"
dst = "$TMP_DB"
try:
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    dst_con = sqlite3.connect(dst, timeout=30)
    src_con.backup(dst_con, pages=100)
    dst_con.close()
    src_con.close()
    print(f"OK: {dst}")
except Exception as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

    if [[ $? -ne 0 ]]; then
        log "FAIL sqlite backup $DB_NAME"
        rm -f "$TMP_DB"
        BACKUP_FAIL=$((BACKUP_FAIL + 1))
        return 1
    fi

    local RAW_SIZE
    RAW_SIZE="$(stat -c%s "$TMP_DB")"

    # Row counts from raw backup
    local ROW_COUNTS
    ROW_COUNTS="$(python3 - <<PYEOF
import sqlite3, json
con = sqlite3.connect(f"file:$TMP_DB?mode=ro", uri=True, timeout=10)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
counts = {}
for t in tables:
    try: counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    except: counts[t] = -1
con.close()
print(json.dumps(counts))
PYEOF
)"

    # Compress with zstd -3 (fast, good ratio)
    zstd -3 --force --quiet "$TMP_DB" -o "$DEST_FILE"
    rm -f "$TMP_DB"

    if [[ $? -ne 0 ]] || [[ ! -f "$DEST_FILE" ]]; then
        log "FAIL zstd compression $DB_NAME"
        rm -f "$DEST_FILE"
        BACKUP_FAIL=$((BACKUP_FAIL + 1))
        return 1
    fi

    local COMP_SIZE
    COMP_SIZE="$(stat -c%s "$DEST_FILE")"

    local RATIO
    RATIO="$(python3 -c "print('%.1f' % ($RAW_SIZE / max($COMP_SIZE, 1)))")"

    # SHA256 of compressed file
    local SHA256
    SHA256="$(sha256sum "$DEST_FILE" | awk '{print $1}')"
    echo "$SHA256  ${TIMESTAMP}.db.zst" > "${DEST_FILE}.sha256"

    # meta.json
    python3 - <<PYEOF
import json
meta = {
    "db_name": "$DB_NAME",
    "db_path": "$SRC",
    "backup_path": "$DEST_FILE",
    "timestamp_utc": "$TIMESTAMP",
    "tier": "$TIER",
    "compression": "zstd-3",
    "raw_size_bytes": $RAW_SIZE,
    "compressed_size_bytes": $COMP_SIZE,
    "compression_ratio": $RATIO,
    "sha256": "$SHA256",
    "row_counts": $ROW_COUNTS,
    "retention_policy": "active: 6h/15min 24h/hourly 7d/daily",
    "durability_note": "Local durability only — off-box backup not yet configured (blocked: no credentials)."
}
with open("${DEST_FILE}.meta.json", "w") as f:
    json.dump(meta, f, indent=2)
print("meta written")
PYEOF

    log "OK $DB_NAME raw=${RAW_SIZE}B compressed=${COMP_SIZE}B ratio=${RATIO}x sha256=${SHA256:0:16}..."
    BACKUP_OK=$((BACKUP_OK + 1))
}

# ── Back up active DBs ─────────────────────────────────────────────────────
for DB_NAME in "${!ACTIVE_DBS[@]}"; do
    backup_db "$DB_NAME" "${ACTIVE_DBS[$DB_NAME]}"
done

# ── Back up archived DBs (one immutable snapshot only) ────────────────────
for DB_NAME in "${!ARCHIVED_DBS[@]}"; do
    DEST_DIR="$BACKUP_ROOT/$DB_NAME"
    EXISTING=$(find "$DEST_DIR" -name "*.db.zst" ! -name "*.sha256" ! -name "*.meta.json" 2>/dev/null | wc -l)
    if [[ "$EXISTING" -gt 0 ]]; then
        log "SKIP archived $DB_NAME — immutable snapshot already exists ($EXISTING files)"
        continue
    fi
    log "Creating one-time immutable snapshot for archived DB: $DB_NAME"
    backup_db "$DB_NAME" "${ARCHIVED_DBS[$DB_NAME]}"
done

# ── Retention cleanup ──────────────────────────────────────────────────────
log "Running retention cleanup..."
python3 - <<PYEOF
import os, glob, re
from datetime import datetime, timezone

BACKUP_ROOT = "$BACKUP_ROOT"
NOW = datetime.now(timezone.utc)

# Active DB retention windows (v4)
KEEP_15MIN_HOURS = 6        # 15-min backups: keep 6h   (~24 copies)
KEEP_HOURLY_HOURS = 24      # hourly backups: keep 24h  (~24 copies at :00)
KEEP_DAILY_HOURS  = 24 * 7  # daily backups:  keep 7d   (~7 copies at 00:00)

ARCHIVED_DBS = {
    "observer_lcr_cont_v1", "observer_pfm_cont_v1",
    "observer_pfm_rev_v1", "post_bonding"
}

deleted = 0
kept = 0

for db_dir in glob.glob(f"{BACKUP_ROOT}/*/"):
    db_name = os.path.basename(db_dir.rstrip("/"))

    if db_name in ARCHIVED_DBS:
        # Keep all existing snapshots for archived DBs
        files = [f for f in glob.glob(f"{db_dir}*.db.zst")
                 if not f.endswith('.sha256') and not f.endswith('.meta.json')]
        kept += len(files)
        continue

    # Active DBs: tiered retention (match both .db.zst and legacy .db)
    files = sorted([f for f in glob.glob(f"{db_dir}*")
                    if (f.endswith('.db.zst') or f.endswith('.db'))
                    and not f.endswith('.sha256') and not f.endswith('.meta.json')])

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
            kept += 1
            continue
        if age_h <= KEEP_HOURLY_HOURS and ts.minute == 0:
            kept += 1
            continue
        if age_h <= KEEP_DAILY_HOURS and ts.hour == 0 and ts.minute == 0:
            kept += 1
            continue

        # Delete backup and all sidecars (both .db and .db.zst variants)
        for ext in ['', '.sha256', '.meta.json', '.zst', '.zst.sha256', '.zst.meta.json']:
            fp = f + ext
            if os.path.exists(fp):
                os.remove(fp)
        deleted += 1

print(f"Retention cleanup: kept={kept} deleted={deleted}")
PYEOF

# ── Off-box sync (rclone) ─────────────────────────────────────────────────
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
if [[ -n "$RCLONE_REMOTE" ]]; then
    log "Syncing to off-box: $RCLONE_REMOTE"
    rclone sync "$BACKUP_ROOT" "$RCLONE_REMOTE" \
        --transfers=4 \
        --checksum \
        --log-level INFO \
        --log-file="$LOG_FILE" \
        --exclude="*.tmp" \
        2>&1 | tee -a "$LOG_FILE"
    log "rclone sync done (exit=$?)"
else
    log "SKIP off-box sync — RCLONE_REMOTE not set (blocked: no credentials)"
fi

log "=== backup_sqlite.sh DONE ok=$BACKUP_OK fail=$BACKUP_FAIL ==="
if [[ $BACKUP_FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
