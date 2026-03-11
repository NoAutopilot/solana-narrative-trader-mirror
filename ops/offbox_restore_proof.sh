#!/usr/bin/env bash
# offbox_restore_proof.sh — Prove off-box backup restore works end-to-end
# Steps:
#   1) List remote backups
#   2) Download latest compressed backup of solana_trader to temp dir
#   3) Verify SHA256
#   4) Decompress with zstd
#   5) Run sqlite3 integrity_check
#   6) Write reports/ops/offbox_restore_proof.md
#
# Usage: /root/solana_trader/ops/offbox_restore_proof.sh [db_name]
# Default db_name: solana_trader
set -euo pipefail

DB_NAME="${1:-solana_trader}"
ENV_FILE="/etc/solana_trader.env"
BACKUP_ROOT="/root/solana_trader/backups/sqlite"
REPORT_DIR="/root/solana_trader/reports/ops"
REPORT_FILE="$REPORT_DIR/offbox_restore_proof.md"
LOG_FILE="/var/log/solana_trader/offbox_sync.log"

mkdir -p "$REPORT_DIR"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] RESTORE_PROOF $*" | tee -a "$LOG_FILE"; }

log "=== offbox_restore_proof.sh START db=$DB_NAME ==="

# ── Load credentials ──────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    log "BLOCKED: $ENV_FILE not found."
    cat > "$REPORT_FILE" << 'BLOCKED_EOF'
# Off-Box Restore Proof

**Status: BLOCKED**

`/etc/solana_trader.env` not found. Off-box backup is not yet configured.
Follow `/root/solana_trader/reports/ops/offbox_setup_instructions.md` to set up credentials.
BLOCKED_EOF
    exit 1
fi
source "$ENV_FILE"

if [[ -z "${RCLONE_REMOTE:-}" ]]; then
    log "BLOCKED: RCLONE_REMOTE not set."
    exit 1
fi

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RESTORE_DIR="$(mktemp -d)"
PASS=true
NOTES=""

# ── Step 1: List remote backups ───────────────────────────────────────────
log "Step 1: Listing remote backups..."
REMOTE_LIST="$(rclone ls "$RCLONE_REMOTE/$DB_NAME/" 2>&1)"
REMOTE_COUNT="$(echo "$REMOTE_LIST" | grep '\.db\.zst$' | wc -l)"
log "  Remote files: $REMOTE_COUNT .db.zst files"

# ── Step 2: Download latest backup ───────────────────────────────────────
log "Step 2: Finding and downloading latest backup..."
LATEST_REMOTE="$(rclone ls "$RCLONE_REMOTE/$DB_NAME/" 2>/dev/null | grep '\.db\.zst$' | awk '{print $2}' | sort | tail -1)"
if [[ -z "$LATEST_REMOTE" ]]; then
    log "FAIL: No .db.zst files found on remote."
    PASS=false
    NOTES="No compressed backups found on remote $RCLONE_REMOTE/$DB_NAME/"
else
    log "  Latest: $LATEST_REMOTE"
    rclone copy "$RCLONE_REMOTE/$DB_NAME/$LATEST_REMOTE" "$RESTORE_DIR/" 2>&1 | tee -a "$LOG_FILE"
    # Also download sha256
    SHA256_REMOTE="${LATEST_REMOTE}.sha256"
    rclone copy "$RCLONE_REMOTE/$DB_NAME/$SHA256_REMOTE" "$RESTORE_DIR/" 2>/dev/null || \
        log "  WARN: no .sha256 file on remote for $LATEST_REMOTE"
    DOWNLOADED="$RESTORE_DIR/$LATEST_REMOTE"
    COMP_SIZE="$(stat -c%s "$DOWNLOADED" 2>/dev/null || echo 0)"
    log "  Downloaded: $DOWNLOADED ($COMP_SIZE bytes)"
fi

# ── Step 3: Verify SHA256 ─────────────────────────────────────────────────
SHA256_STATUS="SKIP (no .sha256 on remote)"
if [[ "$PASS" == "true" ]] && [[ -f "$RESTORE_DIR/${LATEST_REMOTE}.sha256" ]]; then
    log "Step 3: Verifying SHA256..."
    cd "$RESTORE_DIR"
    if sha256sum -c "${LATEST_REMOTE}.sha256" --status 2>/dev/null; then
        SHA256_STATUS="PASS"
        log "  SHA256: PASS"
    else
        SHA256_STATUS="FAIL"
        PASS=false
        log "  SHA256: FAIL"
    fi
    cd - > /dev/null
else
    log "Step 3: SHA256 file not available — skipping"
fi

# ── Step 4: Decompress ────────────────────────────────────────────────────
DECOMP_STATUS="SKIP"
DECOMP_DB=""
RAW_SIZE=0
RATIO="N/A"
if [[ "$PASS" == "true" ]] && [[ -f "$DOWNLOADED" ]]; then
    log "Step 4: Decompressing with zstd..."
    DECOMP_DB="$RESTORE_DIR/${DB_NAME}_restored.db"
    if zstd -d --quiet "$DOWNLOADED" -o "$DECOMP_DB" 2>&1; then
        RAW_SIZE="$(stat -c%s "$DECOMP_DB")"
        RATIO="$(python3 -c "print('%.1f' % ($RAW_SIZE / max($COMP_SIZE, 1)))")"
        DECOMP_STATUS="PASS"
        log "  Decompressed: raw=${RAW_SIZE}B ratio=${RATIO}x"
    else
        DECOMP_STATUS="FAIL"
        PASS=false
        log "  Decompression FAILED"
    fi
fi

# ── Step 5: integrity_check ───────────────────────────────────────────────
INTEGRITY_STATUS="SKIP"
FIRES=0
ROWS=0
LATEST_FIRE="N/A"
TABLE_COUNTS=""
if [[ "$PASS" == "true" ]] && [[ -f "$DECOMP_DB" ]]; then
    log "Step 5: Running sqlite3 integrity_check..."
    RESULT="$(python3 - <<PYEOF
import sqlite3, json, sys
db = "$DECOMP_DB"
con = sqlite3.connect("file:" + db + "?mode=ro", uri=True, timeout=30)
result = con.execute("PRAGMA integrity_check").fetchone()[0]
print("integrity:" + result)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
counts = {}
for t in tables:
    try: counts[t] = con.execute('SELECT COUNT(*) FROM "' + t + '"').fetchone()[0]
    except: counts[t] = -1
print("counts:" + json.dumps(counts))
if "feature_tape_v1" in tables:
    fires = con.execute("SELECT COUNT(DISTINCT fire_id) FROM feature_tape_v1").fetchone()[0]
    rows  = con.execute("SELECT COUNT(*) FROM feature_tape_v1").fetchone()[0]
    last  = con.execute("SELECT MAX(fire_time_utc) FROM feature_tape_v1").fetchone()[0]
    print("fires:" + str(fires))
    print("rows:" + str(rows))
    print("latest:" + str(last))
con.close()
PYEOF
)"
    INTEGRITY_RESULT="$(echo "$RESULT" | grep '^integrity:' | cut -d: -f2)"
    TABLE_COUNTS_JSON="$(echo "$RESULT" | grep '^counts:' | cut -d: -f2-)"
    FIRES="$(echo "$RESULT" | grep '^fires:' | cut -d: -f2 || echo 0)"
    ROWS="$(echo "$RESULT" | grep '^rows:' | cut -d: -f2 || echo 0)"
    LATEST_FIRE="$(echo "$RESULT" | grep '^latest:' | cut -d: -f2- || echo N/A)"

    if [[ "$INTEGRITY_RESULT" == "ok" ]]; then
        INTEGRITY_STATUS="PASS"
        log "  integrity_check: ok"
        log "  feature_tape_v1: fires=$FIRES rows=$ROWS latest=$LATEST_FIRE"
    else
        INTEGRITY_STATUS="FAIL ($INTEGRITY_RESULT)"
        PASS=false
        log "  integrity_check: FAIL ($INTEGRITY_RESULT)"
    fi
fi

COMPLETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OVERALL="$([ "$PASS" == "true" ] && echo PASS || echo FAIL)"

# ── Step 6: Write report ──────────────────────────────────────────────────
log "Step 6: Writing restore proof report..."
cat > "$REPORT_FILE" << REPORT_EOF
# Off-Box Restore Proof

**Overall result: $OVERALL**  
**DB tested:** $DB_NAME  
**Remote:** $RCLONE_REMOTE  
**Started:** $STARTED_AT  
**Completed:** $COMPLETED_AT  

---

## Step 1 — List Remote Backups

Remote path: \`$RCLONE_REMOTE/$DB_NAME/\`  
Files found: **$REMOTE_COUNT** \`.db.zst\` files

\`\`\`
$REMOTE_LIST
\`\`\`

---

## Step 2 — Download Latest Backup

File downloaded: \`$LATEST_REMOTE\`  
Compressed size: $COMP_SIZE bytes  

---

## Step 3 — SHA256 Verification

Result: **$SHA256_STATUS**

---

## Step 4 — Decompression (zstd)

Result: **$DECOMP_STATUS**  
Raw size after decompression: $RAW_SIZE bytes  
Compression ratio: ${RATIO}x  

---

## Step 5 — SQLite Integrity Check

Result: **$INTEGRITY_STATUS**  
feature_tape_v1: fires=$FIRES  rows=$ROWS  latest=$LATEST_FIRE  

Table row counts:
\`\`\`json
$TABLE_COUNTS_JSON
\`\`\`

---

## Summary

| Step | Result |
|------|--------|
| 1. List remote backups | $REMOTE_COUNT files found |
| 2. Download latest     | $LATEST_REMOTE |
| 3. SHA256 verify       | $SHA256_STATUS |
| 4. Decompress (zstd)   | $DECOMP_STATUS |
| 5. integrity_check     | $INTEGRITY_STATUS |
| **OVERALL**            | **$OVERALL** |

${NOTES:+**Notes:** $NOTES}
REPORT_EOF

log "  Report written: $REPORT_FILE"
rm -rf "$RESTORE_DIR"
log "=== offbox_restore_proof.sh DONE overall=$OVERALL ==="
[[ "$PASS" == "true" ]] && exit 0 || exit 1
