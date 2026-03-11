#!/usr/bin/env bash
# offbox_sync.sh — Sync retained local backups to off-box remote via rclone
#
# Syncs only currently-retained backup files:
#   .db.zst, .db.zst.sha256, .db.zst.meta.json
# Does NOT sync temporary files, expired/deleted backups, or raw .db files.
#
# Credentials: loaded from /etc/solana_trader.env (mode 600, root-owned)
# Remote name: solana_backups_remote  (set RCLONE_REMOTE in env file)
#
# Usage:
#   /root/solana_trader/ops/offbox_sync.sh              # sync all retained backups
#   /root/solana_trader/ops/offbox_sync.sh --dry-run    # show what would be synced
#   /root/solana_trader/ops/offbox_sync.sh --list       # list remote contents
set -euo pipefail

ENV_FILE="/etc/solana_trader.env"
BACKUP_ROOT="/root/solana_trader/backups/sqlite"
LOG_FILE="/var/log/solana_trader/offbox_sync.log"
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] OFFBOX $*" | tee -a "$LOG_FILE"; }

MODE="${1:-sync}"

# ── Load credentials ──────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    log "BLOCKED: $ENV_FILE not found. Run offbox_setup_instructions.md steps first."
    exit 1
fi

# Check permissions
PERMS=$(stat -c '%a' "$ENV_FILE")
if [[ "$PERMS" != "600" ]]; then
    log "WARN: $ENV_FILE has permissions $PERMS — expected 600. Fixing..."
    chmod 600 "$ENV_FILE"
fi

source "$ENV_FILE"

if [[ -z "${RCLONE_REMOTE:-}" ]]; then
    log "BLOCKED: RCLONE_REMOTE not set in $ENV_FILE."
    log "  Set RCLONE_REMOTE=solana_backups_remote:<bucket>/sqlite and re-run."
    exit 1
fi

log "=== offbox_sync.sh START remote=$RCLONE_REMOTE ==="

# ── List mode ─────────────────────────────────────────────────────────────
if [[ "$MODE" == "--list" ]]; then
    log "Listing remote contents..."
    rclone ls "$RCLONE_REMOTE" 2>&1 | tee -a "$LOG_FILE"
    exit 0
fi

# ── Dry-run mode ──────────────────────────────────────────────────────────
DRY_RUN_FLAG=""
if [[ "$MODE" == "--dry-run" ]]; then
    DRY_RUN_FLAG="--dry-run"
    log "DRY-RUN mode — no files will be transferred"
fi

# ── Verify rclone remote is reachable ─────────────────────────────────────
log "Checking remote connectivity..."
if ! rclone lsd "$RCLONE_REMOTE" > /dev/null 2>&1; then
    log "FAIL: Cannot reach remote $RCLONE_REMOTE"
    log "  Check credentials in $ENV_FILE and rclone config in ~/.config/rclone/rclone.conf"
    exit 1
fi
log "Remote reachable: OK"

# ── Count local retained files ────────────────────────────────────────────
LOCAL_COUNT=$(find "$BACKUP_ROOT" -name "*.db.zst" ! -name "*.sha256" ! -name "*.meta.json" 2>/dev/null | wc -l)
LOCAL_SIZE=$(du -sh "$BACKUP_ROOT" 2>/dev/null | cut -f1)
log "Local retained backups: $LOCAL_COUNT .db.zst files, total $LOCAL_SIZE"

# ── Sync retained backups to remote ──────────────────────────────────────
# Include only compressed backup files and their sidecars.
# Exclude raw .db files (legacy uncompressed), temp files, and WAL files.
log "Syncing to $RCLONE_REMOTE ..."
rclone sync "$BACKUP_ROOT" "$RCLONE_REMOTE" \
    $DRY_RUN_FLAG \
    --transfers=4 \
    --checkers=8 \
    --checksum \
    --include="*.db.zst" \
    --include="*.db.zst.sha256" \
    --include="*.db.zst.meta.json" \
    --exclude="*.db" \
    --exclude="*.db-shm" \
    --exclude="*.db-wal" \
    --exclude="*.tmp" \
    --exclude="*.bak" \
    --log-level INFO \
    --log-file="$LOG_FILE" \
    --stats=30s \
    2>&1 | tee -a "$LOG_FILE"

SYNC_EXIT=$?

if [[ $SYNC_EXIT -eq 0 ]]; then
    REMOTE_COUNT=$(rclone ls "$RCLONE_REMOTE" 2>/dev/null | grep '\.db\.zst$' | wc -l)
    log "Sync complete. Remote now has $REMOTE_COUNT .db.zst files."
    log "=== offbox_sync.sh DONE exit=0 ==="
else
    log "FAIL: rclone sync exited with code $SYNC_EXIT"
    log "=== offbox_sync.sh DONE exit=$SYNC_EXIT ==="
    exit $SYNC_EXIT
fi
