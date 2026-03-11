#!/usr/bin/env python3
"""
feature_tape_v1.py
==================
Feature acquisition service — READ-ONLY data collection only.
Fires every 15 minutes. Writes one row per fire × candidate to feature_tape_v1.
No trade execution. No observer logic. No state changes.

Deployed via: solana-feature-tape.service
"""

import os
import sys
import time
import uuid
import sqlite3
import logging
import subprocess
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH    = "/root/solana_trader/data/solana_trader.db"
SCRIPT_PATH = os.path.abspath(__file__)
FIRE_INTERVAL_S = 900  # 15 minutes
LOG_PATH   = "/root/solana_trader/logs/feature_tape_v1.log"
MICRO_LOOKBACK_S = 60  # micro row must be within 60s before fire time

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING (single FileHandler — systemd captures stdout separately)
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
log = logging.getLogger("feature_tape_v1")
log.setLevel(logging.INFO)
if not log.handlers:
    fh = logging.FileHandler(LOG_PATH)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)


def get_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", os.path.dirname(SCRIPT_PATH), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_table(conn: sqlite3.Connection):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS feature_tape_v1 (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        fire_id                 TEXT NOT NULL,
        fire_time_utc           TEXT NOT NULL,
        fire_time_epoch         REAL NOT NULL,
        candidate_mint          TEXT NOT NULL,
        candidate_symbol        TEXT,
        snapshot_at_used        TEXT,
        micro_ts_used           TEXT,
        lane                    TEXT,
        venue                   TEXT,
        pumpfun_origin          INTEGER,
        age_hours               REAL,
        liquidity_usd           REAL,
        vol_h1                  REAL,
        rv5m                    REAL,
        r_m5                    REAL,
        range_5m                REAL,
        buy_sell_ratio_m5       REAL,
        signed_flow_m5          REAL,
        txn_accel_m5_vs_h1      REAL,
        vol_accel_m5_vs_h1      REAL,
        avg_trade_usd_m5        REAL,
        jup_vs_cpamm_diff_pct   REAL,
        round_trip_pct          REAL,
        impact_buy_pct          REAL,
        impact_sell_pct         REAL,
        liq_change_pct          REAL,
        breadth_positive_pct    REAL,
        median_pool_r_m5        REAL,
        pool_dispersion_r_m5    REAL,
        r_m5_source             TEXT,
        order_flow_source       TEXT,
        quote_source            TEXT,
        liq_source              TEXT,
        created_at              TEXT NOT NULL
    )
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_ft_fire_id ON feature_tape_v1(fire_id)
    """)
    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_ft_fire_time ON feature_tape_v1(fire_time_utc)
    """)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# PREFLIGHT
# ─────────────────────────────────────────────────────────────────────────────
def preflight(commit: str) -> bool:
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  feature_tape_v1  —  PREFLIGHT                               ║
╠══════════════════════════════════════════════════════════════╣
║  script      : {SCRIPT_PATH:<46} ║
║  commit      : {commit:<46} ║
║  db_path     : {DB_PATH:<46} ║
║  feature_tgt : 18 columns (5 order-flow, 4 quote, 4 mkt)    ║
╚══════════════════════════════════════════════════════════════╝
""", flush=True)

    checks = []

    # 1. DB path exists
    if os.path.exists(DB_PATH):
        checks.append(("[PASS] DB path exists", True))
    else:
        checks.append((f"[FAIL] DB not found: {DB_PATH}", False))

    try:
        conn = get_conn()

        # 2. Table can be created
        try:
            ensure_table(conn)
            checks.append(("[PASS] feature_tape_v1 table exists/created", True))
        except Exception as e:
            checks.append((f"[FAIL] table creation: {e}", False))

        # 3. Latest snapshot readable
        try:
            row = conn.execute(
                "SELECT MAX(snapshot_at) as latest FROM universe_snapshot"
            ).fetchone()
            checks.append((f"[PASS] latest snapshot: {row['latest']}", True))
        except Exception as e:
            checks.append((f"[FAIL] snapshot read: {e}", False))

        # 4. Latest micro row readable
        try:
            row = conn.execute(
                "SELECT MAX(logged_at) as latest FROM microstructure_log"
            ).fetchone()
            checks.append((f"[PASS] latest micro: {row['latest']}", True))
        except Exception as e:
            checks.append((f"[FAIL] micro read: {e}", False))

        # 5. Write test (rollback)
        try:
            conn.execute("BEGIN")
            conn.execute("""
                INSERT INTO feature_tape_v1
                (fire_id, fire_time_utc, fire_time_epoch, candidate_mint, created_at)
                VALUES ('preflight_test', 'preflight', 0.0, 'preflight_mint', 'preflight')
            """)
            conn.execute("ROLLBACK")
            checks.append(("[PASS] write test (rolled back)", True))
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            checks.append((f"[FAIL] write test: {e}", False))

        conn.close()

    except Exception as e:
        checks.append((f"[FAIL] DB connection: {e}", False))

    all_pass = True
    for msg, ok in checks:
        print(f"  {msg}", flush=True)
        if not ok:
            all_pass = False

    print(flush=True)
    return all_pass


# ─────────────────────────────────────────────────────────────────────────────
# FIRE LOGIC
# ─────────────────────────────────────────────────────────────────────────────
def next_fire_time(now: datetime) -> datetime:
    """Align to next 15-minute boundary."""
    minute = (now.minute // 15 + 1) * 15
    base = now.replace(second=0, microsecond=0)
    if minute >= 60:
        base = base.replace(minute=0) + timedelta(hours=1)
    else:
        base = base.replace(minute=minute)
    return base


def run_fire(fire_time: datetime, conn: sqlite3.Connection) -> dict:
    """Execute one fire cycle. Returns stats dict."""
    fire_id = str(uuid.uuid4())[:8]
    fire_ts = fire_time.isoformat()
    fire_epoch = fire_time.timestamp()

    log.info(f"FIRE fire_id={fire_id} fire_time={fire_ts}")

    # ── 1. Select snapshot (B-strict: MAX snapshot_at <= fire_time) ──────────
    snap_row = conn.execute("""
        SELECT MAX(snapshot_at) as snap_at FROM universe_snapshot
        WHERE snapshot_at <= ?
    """, (fire_ts,)).fetchone()
    snapshot_at = snap_row["snap_at"] if snap_row else None

    if not snapshot_at:
        log.warning(f"fire_id={fire_id} no snapshot available, skipping")
        return {"fire_id": fire_id, "n_candidates": 0, "n_written": 0, "skipped": True}

    # ── 2. Get eligible candidates from that snapshot ────────────────────────
    candidates = conn.execute("""
        SELECT mint_address, token_symbol, lane, venue, pumpfun_origin,
               age_hours, liq_usd, vol_h1, r_m5,
               jup_vs_cpamm_diff_pct, round_trip_pct,
               impact_buy_pct, impact_sell_pct
        FROM universe_snapshot
        WHERE snapshot_at = ?
          AND eligible = 1
    """, (snapshot_at,)).fetchall()

    if not candidates:
        log.warning(f"fire_id={fire_id} no eligible candidates in snapshot {snapshot_at}")
        return {"fire_id": fire_id, "n_candidates": 0, "n_written": 0, "skipped": False}

    # ── 3. Breadth / pool-level metrics (derived, no lookahead) ─────────────
    # Source r_m5 from microstructure_log (not snapshot — snapshot.r_m5 is often NULL).
    # Collect the most recent micro r_m5 for each eligible candidate within the 60s window.
    fire_ts_minus_60 = (fire_time - timedelta(seconds=MICRO_LOOKBACK_S)).isoformat()
    pool_micro_r_m5_rows = conn.execute("""
        SELECT m.r_m5
        FROM (
            SELECT mint_address, MAX(logged_at) as latest_at
            FROM microstructure_log
            WHERE logged_at <= ?
              AND logged_at >= ?
              AND mint_address IN ({})
            GROUP BY mint_address
        ) best
        JOIN microstructure_log m
          ON m.mint_address = best.mint_address AND m.logged_at = best.latest_at
        WHERE m.r_m5 IS NOT NULL
    """.format(",".join("?" * len(candidates))),
        [fire_ts, fire_ts_minus_60] + [c["mint_address"] for c in candidates]
    ).fetchall()
    r_m5_vals = [row[0] for row in pool_micro_r_m5_rows if row[0] is not None]
    breadth_positive_pct = (
        sum(1 for v in r_m5_vals if v > 0) / len(r_m5_vals) * 100
        if r_m5_vals else None
    )
    median_pool_r_m5 = sorted(r_m5_vals)[len(r_m5_vals) // 2] if r_m5_vals else None
    pool_dispersion_r_m5 = (
        max(r_m5_vals) - min(r_m5_vals) if len(r_m5_vals) >= 2 else None
    )

    # ── 4. Per-candidate micro join ──────────────────────────────────────────
    rows_written = 0
    now_utc = datetime.now(timezone.utc).isoformat()

    for c in candidates:
        mint = c["mint_address"]

        # Micro row: MAX(logged_at) WHERE logged_at <= fire_time AND >= fire_time-60s
        micro = conn.execute("""
            SELECT logged_at, rv_5m, range_5m,
                   buy_sell_ratio_m5, buys_m5, sells_m5,
                   txn_accel_m5_vs_h1, vol_accel_m5_vs_h1,
                   avg_trade_usd_m5, liq_change_pct
            FROM microstructure_log
            WHERE mint_address = ?
              AND logged_at <= ?
              AND logged_at >= ?
            ORDER BY logged_at DESC
            LIMIT 1
        """, (mint, fire_ts, fire_ts_minus_60)).fetchone()

        micro_ts = micro["logged_at"] if micro else None

        # Derived: signed_flow_m5 = (buys_m5 - sells_m5) / (buys_m5 + sells_m5)
        signed_flow_m5 = None
        if micro and micro["buys_m5"] is not None and micro["sells_m5"] is not None:
            total = (micro["buys_m5"] or 0) + (micro["sells_m5"] or 0)
            if total > 0:
                signed_flow_m5 = ((micro["buys_m5"] or 0) - (micro["sells_m5"] or 0)) / total

        # Source flags
        r_m5_source = "snapshot" if c["r_m5"] is not None else "missing"
        order_flow_source = "micro" if micro else "missing"
        quote_source = "snapshot" if c["jup_vs_cpamm_diff_pct"] is not None else "missing"
        liq_source = "micro" if (micro and micro["liq_change_pct"] is not None) else "missing"

        conn.execute("""
            INSERT INTO feature_tape_v1 (
                fire_id, fire_time_utc, fire_time_epoch,
                candidate_mint, candidate_symbol,
                snapshot_at_used, micro_ts_used,
                lane, venue, pumpfun_origin,
                age_hours, liquidity_usd, vol_h1,
                rv5m, r_m5, range_5m,
                buy_sell_ratio_m5, signed_flow_m5,
                txn_accel_m5_vs_h1, vol_accel_m5_vs_h1, avg_trade_usd_m5,
                jup_vs_cpamm_diff_pct, round_trip_pct,
                impact_buy_pct, impact_sell_pct,
                liq_change_pct,
                breadth_positive_pct, median_pool_r_m5, pool_dispersion_r_m5,
                r_m5_source, order_flow_source, quote_source, liq_source,
                created_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            fire_id, fire_ts, fire_epoch,
            mint, c["token_symbol"],
            snapshot_at, micro_ts,
            c["lane"], c["venue"], c["pumpfun_origin"],
            c["age_hours"], c["liq_usd"], c["vol_h1"],
            micro["rv_5m"] if micro else None,
            c["r_m5"],
            micro["range_5m"] if micro else None,
            micro["buy_sell_ratio_m5"] if micro else None,
            signed_flow_m5,
            micro["txn_accel_m5_vs_h1"] if micro else None,
            micro["vol_accel_m5_vs_h1"] if micro else None,
            micro["avg_trade_usd_m5"] if micro else None,
            c["jup_vs_cpamm_diff_pct"],
            c["round_trip_pct"],
            c["impact_buy_pct"],
            c["impact_sell_pct"],
            micro["liq_change_pct"] if micro else None,
            breadth_positive_pct,
            median_pool_r_m5,
            pool_dispersion_r_m5,
            r_m5_source, order_flow_source, quote_source, liq_source,
            now_utc
        ))
        rows_written += 1

    conn.commit()
    log.info(
        f"FIRE_COMPLETE fire_id={fire_id} snapshot={snapshot_at} "
        f"n_candidates={len(candidates)} n_written={rows_written}"
    )
    return {
        "fire_id": fire_id,
        "snapshot_at": snapshot_at,
        "n_candidates": len(candidates),
        "n_written": rows_written,
        "skipped": False
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────
def main():
    commit = get_commit()

    if not preflight(commit):
        log.error("PREFLIGHT FAILED — aborting")
        sys.exit(1)

    log.info(f"STARTUP commit={commit} db={DB_PATH}")

    conn = get_conn()
    ensure_table(conn)

    while True:
        now = datetime.now(timezone.utc)
        fire_at = next_fire_time(now)
        wait_s = (fire_at - now).total_seconds()
        log.info(f"WAITING next_fire={fire_at.isoformat()} wait_s={wait_s:.1f}")
        time.sleep(max(0, wait_s))

        try:
            stats = run_fire(fire_at, conn)
            log.info(f"STATS {stats}")
        except Exception as e:
            log.error(f"FIRE_ERROR {e}", exc_info=True)


if __name__ == "__main__":
    main()
