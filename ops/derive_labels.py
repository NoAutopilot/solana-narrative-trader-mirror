#!/usr/bin/env python3
"""
derive_labels.py — Continuous label backfill for feature_tape_v1.

For each feature_tape_v1 row whose +5m / +15m / +30m labels are due and missing,
derives forward return labels from universe_snapshot (primary) with
microstructure_log as fallback.

No-lookahead rule enforced via epoch timestamps:
  entry price  : latest price row with ts <= fire_epoch
  forward price: closest price row to fire_epoch + offset, strictly > fire_epoch

Usage:
  python3 ops/derive_labels.py              # run once on all unlabeled rows
  python3 ops/derive_labels.py --loop 60   # run continuously, poll every 60s
  python3 ops/derive_labels.py --dry-run   # print stats, write nothing
"""

import sqlite3
import argparse
import time
import os
import sys
from datetime import datetime, timezone

DB = os.environ.get('SOLANA_TRADER_DB', '/root/solana_trader/data/solana_trader.db')
LOG_PREFIX = '[derive_labels]'

OFFSETS = {
    '5m':  300,
    '15m': 900,
    '30m': 1800,
}
ENTRY_LOOKBACK  = 60   # max seconds before fire for entry price
FWD_TOLERANCE   = 60   # ±60s tolerance around target forward time
STALE_THRESHOLD = 30   # seconds — above this is 'stale', below is 'good'

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_tape_v1_labels (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fire_id             TEXT NOT NULL,
    candidate_mint      TEXT NOT NULL,
    fire_time_utc       TEXT NOT NULL,
    fire_time_epoch     REAL NOT NULL,
    price_entry         REAL,
    entry_snapshot_ts   TEXT,
    entry_lag_sec       REAL,
    price_fwd_5m        REAL,
    fwd_5m_snapshot_ts  TEXT,
    fwd_5m_lag_sec      REAL,
    r_forward_5m        REAL,
    price_fwd_15m       REAL,
    fwd_15m_snapshot_ts TEXT,
    fwd_15m_lag_sec     REAL,
    r_forward_15m       REAL,
    price_fwd_30m       REAL,
    fwd_30m_snapshot_ts TEXT,
    fwd_30m_lag_sec     REAL,
    r_forward_30m       REAL,
    label_source        TEXT,
    label_quality       TEXT,
    derived_at          TEXT,
    UNIQUE(fire_id, candidate_mint)
)
"""

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f'{ts} {LOG_PREFIX} {msg}', flush=True)

def ts_to_epoch(ts_str):
    if ts_str is None:
        return None
    ts_str = ts_str.replace('+00:00', '').replace('Z', '').strip()
    try:
        return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None

def find_entry(price_rows, fire_epoch):
    """Latest row with ts <= fire_epoch and within ENTRY_LOOKBACK seconds."""
    best_ts, best_price, best_ts_str = None, None, None
    for ts_str, price in price_rows:
        ts = ts_to_epoch(ts_str)
        if ts is None or price is None:
            continue
        if ts <= fire_epoch and (fire_epoch - ts) <= ENTRY_LOOKBACK:
            if best_ts is None or ts > best_ts:
                best_ts = ts
                best_price = price
                best_ts_str = ts_str
    return best_ts_str, best_ts, best_price

def find_forward(price_rows, fire_epoch, offset):
    """Closest row to fire_epoch + offset, strictly after fire_epoch, within FWD_TOLERANCE."""
    target = fire_epoch + offset
    best_ts, best_price, best_ts_str, best_dist = None, None, None, float('inf')
    for ts_str, price in price_rows:
        ts = ts_to_epoch(ts_str)
        if ts is None or price is None:
            continue
        if ts <= fire_epoch:
            continue
        dist = abs(ts - target)
        if dist <= FWD_TOLERANCE and dist < best_dist:
            best_dist = dist
            best_ts = ts
            best_price = price
            best_ts_str = ts_str
    return best_ts_str, best_ts, best_price

def quality(entry_lag, fwd_lag):
    if entry_lag is None or fwd_lag is None:
        return 'missing'
    if max(entry_lag, fwd_lag) < STALE_THRESHOLD:
        return 'good'
    elif max(entry_lag, fwd_lag) <= 120:
        return 'stale'
    return 'missing'

def get_price_rows(con, mint, table, ts_col, price_col):
    return con.execute(
        f"SELECT {ts_col}, {price_col} FROM {table} WHERE mint_address=? ORDER BY {ts_col}",
        (mint,)
    ).fetchall()

def run_once(con, dry_run=False):
    now_epoch = time.time()

    # Get all feature_tape rows not yet labeled (or partially labeled)
    ft_rows = con.execute("""
        SELECT ft.fire_id, ft.candidate_mint, ft.fire_time_utc, ft.fire_time_epoch
        FROM feature_tape_v1 ft
        WHERE NOT EXISTS (
            SELECT 1 FROM feature_tape_v1_labels lbl
            WHERE lbl.fire_id = ft.fire_id AND lbl.candidate_mint = ft.candidate_mint
        )
        AND ft.fire_time_epoch <= ?
        ORDER BY ft.fire_time_epoch ASC
    """, (now_epoch - OFFSETS['5m'] - FWD_TOLERANCE,)).fetchall()

    if not ft_rows:
        log("No unlabeled rows due for labeling.")
        return 0

    log(f"Processing {len(ft_rows)} unlabeled rows...")

    # Pre-load price data per mint
    mints = list(set(r[1] for r in ft_rows))
    snap_cache = {}
    micro_cache = {}
    for mint in mints:
        snap_cache[mint] = get_price_rows(con, mint, 'universe_snapshot', 'snapshot_at', 'price_usd')
        micro_cache[mint] = get_price_rows(con, mint, 'microstructure_log', 'logged_at', 'price_usd')

    inserted = 0
    skipped = 0
    now_str = datetime.now(timezone.utc).isoformat()

    for fire_id, mint, fire_time_utc, fire_time_epoch in ft_rows:
        # Try snapshot first, micro as fallback
        for source_name, cache in [('universe_snapshot', snap_cache), ('microstructure_log', micro_cache)]:
            price_rows = cache.get(mint, [])

            entry_ts_str, entry_ts, price_entry = find_entry(price_rows, fire_time_epoch)
            if price_entry is None:
                continue  # try next source

            # Derive all three forward windows
            results = {}
            for label, offset in OFFSETS.items():
                # Only derive if enough time has passed
                if now_epoch < fire_time_epoch + offset + FWD_TOLERANCE:
                    results[label] = (None, None, None, None, None)
                    continue
                fwd_ts_str, fwd_ts, price_fwd = find_forward(price_rows, fire_time_epoch, offset)
                fwd_lag = round(abs(fwd_ts - (fire_time_epoch + offset)), 1) if fwd_ts else None
                r_fwd = round((price_fwd / price_entry) - 1, 6) if (price_fwd and price_entry and price_entry > 0) else None
                results[label] = (fwd_ts_str, fwd_ts, price_fwd, fwd_lag, r_fwd)

            entry_lag = round(fire_time_epoch - entry_ts, 1) if entry_ts else None
            fwd_5m_lag = results['5m'][3] if results['5m'][0] is not None else None
            qual = quality(entry_lag, fwd_5m_lag)

            if dry_run:
                log(f"  DRY-RUN: {mint[:8]}.. fire={fire_time_utc[:16]} entry_lag={entry_lag}s r_5m={results['5m'][4] if results['5m'][0] else 'pending'} source={source_name}")
                inserted += 1
                break

            try:
                con.execute("""
                    INSERT OR REPLACE INTO feature_tape_v1_labels (
                        fire_id, candidate_mint, fire_time_utc, fire_time_epoch,
                        price_entry, entry_snapshot_ts, entry_lag_sec,
                        price_fwd_5m,  fwd_5m_snapshot_ts,  fwd_5m_lag_sec,  r_forward_5m,
                        price_fwd_15m, fwd_15m_snapshot_ts, fwd_15m_lag_sec, r_forward_15m,
                        price_fwd_30m, fwd_30m_snapshot_ts, fwd_30m_lag_sec, r_forward_30m,
                        label_source, label_quality, derived_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    fire_id, mint, fire_time_utc, fire_time_epoch,
                    price_entry, entry_ts_str, entry_lag,
                    results['5m'][2],  results['5m'][0],  results['5m'][3],  results['5m'][4],
                    results['15m'][2], results['15m'][0], results['15m'][3], results['15m'][4],
                    results['30m'][2], results['30m'][0], results['30m'][3], results['30m'][4],
                    source_name, qual, now_str
                ))
                inserted += 1
            except Exception as e:
                log(f"  INSERT ERROR {mint}: {e}")
                skipped += 1
            break  # stop trying sources once entry found

        else:
            skipped += 1  # no source had entry price

    if not dry_run:
        con.commit()

    log(f"Done: inserted={inserted} skipped={skipped}")
    return inserted

def print_coverage(con):
    total_ft = con.execute("SELECT COUNT(*) FROM feature_tape_v1").fetchone()[0]
    total_lbl = con.execute("SELECT COUNT(*) FROM feature_tape_v1_labels").fetchone()[0]
    good = con.execute("SELECT COUNT(*) FROM feature_tape_v1_labels WHERE label_quality='good'").fetchone()[0]
    stale = con.execute("SELECT COUNT(*) FROM feature_tape_v1_labels WHERE label_quality='stale'").fetchone()[0]
    missing = con.execute("SELECT COUNT(*) FROM feature_tape_v1_labels WHERE label_quality='missing'").fetchone()[0]
    r5m_null = con.execute("SELECT COUNT(*) FROM feature_tape_v1_labels WHERE r_forward_5m IS NULL").fetchone()[0]
    log(f"Coverage: {total_lbl}/{total_ft} rows labeled ({100*total_lbl/total_ft:.1f}%)")
    log(f"  good={good}  stale={stale}  missing={missing}")
    log(f"  r_forward_5m populated: {total_lbl - r5m_null}/{total_lbl}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop', type=int, default=0, help='Poll interval in seconds (0=run once)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    log(f"Starting. DB={DB} loop={args.loop}s dry_run={args.dry_run}")

    con = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")

    if not args.dry_run:
        con.execute(SCHEMA)
        con.commit()

    if args.loop > 0:
        while True:
            try:
                run_once(con, args.dry_run)
                print_coverage(con)
            except Exception as e:
                log(f"ERROR: {e}")
            time.sleep(args.loop)
    else:
        run_once(con, args.dry_run)
        if not args.dry_run:
            print_coverage(con)

    con.close()

if __name__ == '__main__':
    main()
