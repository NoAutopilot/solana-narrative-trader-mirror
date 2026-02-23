#!/usr/bin/env python3
"""
Safe SQLite snapshot creator.
Uses SQLite's backup API to create a consistent copy of the database
even while the paper trader is actively writing to it.
This avoids the "database disk image is malformed" error from raw file copies.
"""
import sqlite3
import os
import sys
import time

DB_PATH = "/root/solana_trader/data/solana_trader.db"
SNAPSHOT_PATH = "/root/solana_trader/data/solana_trader_snapshot.db"

def create_snapshot():
    """Create a safe snapshot using SQLite backup API."""
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Source DB not found: {DB_PATH}", file=sys.stderr)
        return False
    
    try:
        src = sqlite3.connect(DB_PATH)
        # Remove old snapshot if exists
        if os.path.exists(SNAPSHOT_PATH):
            os.remove(SNAPSHOT_PATH)
        dst = sqlite3.connect(SNAPSHOT_PATH)
        src.backup(dst)
        src.close()
        dst.close()
        
        # Verify the snapshot
        verify = sqlite3.connect(SNAPSHOT_PATH)
        result = verify.execute("PRAGMA integrity_check").fetchone()
        count = verify.execute("SELECT count(*) FROM trades").fetchone()
        verify.close()
        
        if result[0] == "ok":
            size = os.path.getsize(SNAPSHOT_PATH)
            print(f"OK: snapshot created, {count[0]} trades, {size} bytes")
            return True
        else:
            print(f"ERROR: snapshot failed integrity check: {result[0]}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = create_snapshot()
    sys.exit(0 if success else 1)
