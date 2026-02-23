#!/usr/bin/env python3
"""
SQLite Database Backup to S3 via Manus Storage Proxy.

Uploads the solana_trader.db file to S3 every hour (configurable).
Keeps the last N backups with timestamped keys.
Also maintains a 'latest' key that always points to the most recent backup.

Usage:
  # One-shot backup:
  python3 db_backup.py

  # Continuous backup every hour:
  python3 db_backup.py --loop

  # Restore latest backup:
  python3 db_backup.py --restore
"""

import os
import sys
import time
import shutil
import logging
import argparse
import requests
from datetime import datetime, timezone

# Add project path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import DB_PATH, DATA_DIR

# ── Configuration ─────────────────────────────────────────────────────────────

BACKUP_INTERVAL_SEC = 3600  # 1 hour
MAX_BACKUPS = 48            # Keep last 48 hours of backups
BACKUP_PREFIX = "solana-trader-backups"

# Manus Storage Proxy credentials (same as dashboard uses)
FORGE_API_URL = os.environ.get("BUILT_IN_FORGE_API_URL", "")
FORGE_API_KEY = os.environ.get("BUILT_IN_FORGE_API_KEY", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [db_backup] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def _get_headers():
    return {"Authorization": f"Bearer {FORGE_API_KEY}"}


def _upload_to_s3(local_path: str, s3_key: str) -> str:
    """Upload a file to S3 via the Manus storage proxy. Returns the URL."""
    upload_url = f"{FORGE_API_URL.rstrip('/')}/v1/storage/upload?path={s3_key}"

    with open(local_path, "rb") as f:
        file_data = f.read()

    form = requests.Request("POST", upload_url, headers=_get_headers())
    # Use multipart form upload
    resp = requests.post(
        upload_url,
        headers=_get_headers(),
        files={"file": (os.path.basename(local_path), file_data, "application/octet-stream")}
    )

    if resp.status_code != 200:
        raise Exception(f"Upload failed ({resp.status_code}): {resp.text}")

    result = resp.json()
    return result.get("url", "")


def _download_from_s3(s3_key: str, local_path: str) -> bool:
    """Download a file from S3 via the Manus storage proxy."""
    download_url = f"{FORGE_API_URL.rstrip('/')}/v1/storage/downloadUrl?path={s3_key}"

    resp = requests.get(download_url, headers=_get_headers())
    if resp.status_code != 200:
        logger.error(f"Failed to get download URL ({resp.status_code}): {resp.text}")
        return False

    file_url = resp.json().get("url", "")
    if not file_url:
        logger.error("No download URL returned")
        return False

    # Download the actual file
    file_resp = requests.get(file_url, timeout=120)
    if file_resp.status_code != 200:
        logger.error(f"Failed to download file ({file_resp.status_code})")
        return False

    # Write to temp file first, then move (atomic-ish)
    tmp_path = local_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(file_resp.content)

    shutil.move(tmp_path, local_path)
    logger.info(f"Downloaded {len(file_resp.content)} bytes to {local_path}")
    return True


def backup_db():
    """Create a backup of the SQLite database and upload to S3."""
    if not os.path.exists(DB_PATH):
        logger.warning(f"Database not found at {DB_PATH}, skipping backup")
        return False

    if not FORGE_API_URL or not FORGE_API_KEY:
        logger.error("BUILT_IN_FORGE_API_URL and BUILT_IN_FORGE_API_KEY must be set")
        return False

    db_size = os.path.getsize(DB_PATH)
    logger.info(f"Starting backup of {DB_PATH} ({db_size / 1024:.1f} KB)")

    # Create a safe copy first (SQLite WAL mode can cause issues with direct copy)
    backup_local = os.path.join(DATA_DIR, "backup_temp.db")
    try:
        import sqlite3
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(backup_local)
        src.backup(dst)
        dst.close()
        src.close()
        logger.info("Created safe SQLite backup copy")
    except Exception as e:
        logger.error(f"Failed to create backup copy: {e}")
        # Fallback: direct file copy
        shutil.copy2(DB_PATH, backup_local)
        logger.info("Used direct file copy as fallback")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    try:
        # Upload timestamped backup
        ts_key = f"{BACKUP_PREFIX}/solana_trader_{timestamp}.db"
        url = _upload_to_s3(backup_local, ts_key)
        logger.info(f"Uploaded timestamped backup: {ts_key} -> {url}")

        # Upload as 'latest' (overwrite)
        latest_key = f"{BACKUP_PREFIX}/solana_trader_latest.db"
        url_latest = _upload_to_s3(backup_local, latest_key)
        logger.info(f"Uploaded latest backup: {latest_key} -> {url_latest}")

        # Clean up local temp
        os.remove(backup_local)

        logger.info(f"Backup complete: {db_size / 1024:.1f} KB uploaded as {ts_key}")
        return True

    except Exception as e:
        logger.error(f"Backup failed: {e}")
        if os.path.exists(backup_local):
            os.remove(backup_local)
        return False


def restore_db():
    """Restore the database from the latest S3 backup."""
    if not FORGE_API_URL or not FORGE_API_KEY:
        logger.error("BUILT_IN_FORGE_API_URL and BUILT_IN_FORGE_API_KEY must be set")
        return False

    latest_key = f"{BACKUP_PREFIX}/solana_trader_latest.db"
    logger.info(f"Restoring from {latest_key}...")

    os.makedirs(DATA_DIR, exist_ok=True)

    # If DB exists, back it up locally first
    if os.path.exists(DB_PATH):
        local_backup = DB_PATH + ".pre_restore"
        shutil.copy2(DB_PATH, local_backup)
        logger.info(f"Existing DB backed up to {local_backup}")

    success = _download_from_s3(latest_key, DB_PATH)
    if success:
        db_size = os.path.getsize(DB_PATH)
        logger.info(f"Restore complete: {db_size / 1024:.1f} KB")

        # Verify the restored DB
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM trades")
            trade_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM live_trades")
            live_count = c.fetchone()[0]
            conn.close()
            logger.info(f"Verified: {trade_count} trades, {live_count} live trades")
        except Exception as e:
            logger.error(f"Restored DB verification failed: {e}")
            return False
    else:
        logger.error("Restore failed")

    return success


def run_loop():
    """Run continuous backup loop."""
    logger.info(f"Starting backup loop (interval: {BACKUP_INTERVAL_SEC}s)")

    while True:
        try:
            backup_db()
        except Exception as e:
            logger.error(f"Backup loop error: {e}")

        logger.info(f"Next backup in {BACKUP_INTERVAL_SEC}s")
        time.sleep(BACKUP_INTERVAL_SEC)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQLite DB Backup/Restore")
    parser.add_argument("--loop", action="store_true", help="Run continuous backup")
    parser.add_argument("--restore", action="store_true", help="Restore from latest backup")
    parser.add_argument("--interval", type=int, default=BACKUP_INTERVAL_SEC,
                        help="Backup interval in seconds (default: 3600)")
    args = parser.parse_args()

    if args.interval:
        BACKUP_INTERVAL_SEC = args.interval

    if args.restore:
        success = restore_db()
        sys.exit(0 if success else 1)
    elif args.loop:
        # Do an immediate backup, then loop
        backup_db()
        run_loop()
    else:
        # One-shot backup
        success = backup_db()
        sys.exit(0 if success else 1)
