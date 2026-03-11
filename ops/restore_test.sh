#!/usr/bin/env bash
# restore_test.sh — Verify latest backup: decompress, integrity_check, row counts
# Works with both .db.zst (compressed) and legacy .db (uncompressed) backups.
# Usage: ./restore_test.sh [db_name]
# Default db_name: solana_trader
set -euo pipefail

DB_NAME="${1:-solana_trader}"
BACKUP_ROOT="/root/solana_trader/backups/sqlite"
DEST_DIR="$BACKUP_ROOT/$DB_NAME"
LOG_FILE="/var/log/solana_trader/backup_sqlite.log"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] RESTORE_TEST $*" | tee -a "$LOG_FILE"; }
log "=== restore_test.sh START db=$DB_NAME ==="

# ── Find latest backup (prefer .db.zst, fall back to .db) ─────────────────
LATEST_ZST="$(ls "$DEST_DIR"/*.db.zst 2>/dev/null | grep -v '.sha256\|.meta.json' | sort | tail -1 || true)"
LATEST_DB="$(ls "$DEST_DIR"/*.db 2>/dev/null | grep -v '.sha256\|.meta.json' | sort | tail -1 || true)"

if [[ -n "$LATEST_ZST" ]]; then
    LATEST="$LATEST_ZST"
    COMPRESSED=true
    log "Found compressed backup: $LATEST"
elif [[ -n "$LATEST_DB" ]]; then
    LATEST="$LATEST_DB"
    COMPRESSED=false
    log "Found uncompressed backup (legacy): $LATEST"
else
    log "FAIL — no backup files found in $DEST_DIR"
    exit 1
fi

# ── SHA256 verify ─────────────────────────────────────────────────────────
SHA256_FILE="${LATEST}.sha256"
if [[ -f "$SHA256_FILE" ]]; then
    cd "$(dirname "$LATEST")"
    sha256sum -c "$(basename "$SHA256_FILE")" --status && log "SHA256: PASS" || { log "SHA256: FAIL"; exit 1; }
    cd - > /dev/null
else
    log "WARNING: no .sha256 file found — skipping checksum verify"
fi

# ── Decompress to temp dir ────────────────────────────────────────────────
RESTORE_DIR="$(mktemp -d)"
RESTORE_DB="$RESTORE_DIR/${DB_NAME}_restore_test.db"

if [[ "$COMPRESSED" == "true" ]]; then
    log "Decompressing with zstd..."
    zstd -d --quiet "$LATEST" -o "$RESTORE_DB"
    COMP_SIZE="$(stat -c%s "$LATEST")"
    RAW_SIZE="$(stat -c%s "$RESTORE_DB")"
    RATIO="$(python3 -c "print('%.1f' % ($RAW_SIZE / max($COMP_SIZE, 1)))")"
    log "Decompressed: compressed=${COMP_SIZE}B raw=${RAW_SIZE}B ratio=${RATIO}x"
else
    cp "$LATEST" "$RESTORE_DB"
    RAW_SIZE="$(stat -c%s "$RESTORE_DB")"
    log "Copied uncompressed: size=${RAW_SIZE}B"
fi

# ── Integrity check + row counts ──────────────────────────────────────────
python3 - <<PYEOF
import sqlite3, json, sys

db = "$RESTORE_DB"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)

# Integrity check
result = con.execute("PRAGMA integrity_check").fetchone()[0]
print(f"integrity_check: {result}")
if result != "ok":
    print("FAIL: integrity_check did not return 'ok'", file=sys.stderr)
    sys.exit(1)

# All tables
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables ({len(tables)}): {', '.join(sorted(tables))}")

# Key table row counts
key_tables = sorted(tables)
for t in key_tables:
    try:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t}: {n} rows")
    except Exception as e:
        print(f"  {t}: ERROR {e}")

# Feature tape specific
if "feature_tape_v1" in tables:
    fires = con.execute("SELECT COUNT(DISTINCT fire_id) FROM feature_tape_v1").fetchone()[0]
    rows  = con.execute("SELECT COUNT(*) FROM feature_tape_v1").fetchone()[0]
    first = con.execute("SELECT MIN(fire_time_utc) FROM feature_tape_v1").fetchone()[0]
    last  = con.execute("SELECT MAX(fire_time_utc) FROM feature_tape_v1").fetchone()[0]
    print(f"feature_tape_v1 summary: fires={fires} rows={rows} first={first} last={last}")

con.close()
print("RESTORE TEST: PASS")
PYEOF

RC=$?
rm -rf "$RESTORE_DIR"
log "=== restore_test.sh DONE exit=$RC ==="
exit $RC
