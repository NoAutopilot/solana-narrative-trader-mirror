#!/usr/bin/env python3
"""
feature_tape_v2.py  (post-audit rewrite, 2026-03-12)
=====================================================
Collects pre-fire features for every candidate at each 15-minute fire.
READ-ONLY data collection — no trade execution, no observer logic.

Feature families:
  A) Order-flow / urgency   — from microstructure_log (micro-native)
                              + universe_snapshot fallback (snap-native)
  B) Route / quote quality  — from universe_snapshot (snap-native, ~100%)
  C) Market-state / gating  — fire-level aggregates from both sources

Schema changes vs. abandoned v1 attempt (3-fire sample):
  REMOVED (unavailable in current phase):
    buy_count_1m, sell_count_1m, buy_usd_1m, sell_usd_1m,
    signed_flow_1m, buy_sell_ratio_1m, avg_trade_usd_1m,
    txn_accel_m1_vs_h1, vol_accel_m1_vs_h1,
    median_trade_usd_5m, max_trade_usd_5m, signed_flow_5m
  FIXED:
    lane — derived at collection time from eligible+gate_reason+pool_type
            (universe_snapshot.lane is always NULL)
  FIXED:
    pool-level breadth/dispersion — computed from micro r_m5 values
  FIXED:
    micro-only fields — NULL (not 0) when no micro row found

See reports/ops/feature_tape_v2_source_map.md for full field-level audit.
See reports/ops/feature_tape_v2_unavailable_fields.md for removed fields.

Deployed via: solana-feature-tape-v2.service
"""

import os
import sys
import time
import sqlite3
import logging
import hashlib
import statistics
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH         = "/root/solana_trader/data/solana_trader.db"
LOG_PATH        = "/root/solana_trader/logs/feature_tape_v2.log"
FIRE_INTERVAL_S = 900          # 15 minutes
SNAP_LOOKBACK_S = 300          # snapshot must be within 5 min before fire
MICRO_LOOKBACK_S = 60          # micro row must be within 60s before fire

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("feature_tape_v2")

# ── Schema ────────────────────────────────────────────────────────────────────
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS feature_tape_v2 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    fire_id                 TEXT    NOT NULL,
    fire_time_utc           TEXT    NOT NULL,
    fire_time_epoch         REAL    NOT NULL,
    candidate_mint          TEXT    NOT NULL,
    candidate_symbol        TEXT,
    snapshot_at_used        TEXT,
    micro_ts_used           TEXT,
    created_at              TEXT    NOT NULL,

    -- Classification
    lane                    TEXT    NOT NULL,   -- derived_at_collection; never NULL
    lane_source             TEXT    NOT NULL DEFAULT 'derived_at_collection',
    venue                   TEXT,
    pool_type               TEXT,
    pumpfun_origin          INTEGER,
    eligible                INTEGER,
    gate_reason             TEXT,

    -- Fundamentals (snapshot-native)
    age_hours               REAL,
    liquidity_usd           REAL,
    vol_h1                  REAL,
    vol_h24                 REAL,
    price_usd               REAL,
    r_m5_snap               REAL,
    r_h1_snap               REAL,

    -- Family A: Order-flow (micro-native; NULL if no micro row)
    buys_m5                 REAL,
    sells_m5                REAL,
    buys_h1                 REAL,
    sells_h1                REAL,
    buy_sell_ratio_m5       REAL,
    buy_sell_ratio_h1       REAL,
    buy_count_ratio_m5      REAL,
    buy_count_ratio_h1      REAL,
    avg_trade_usd_m5        REAL,
    avg_trade_usd_h1        REAL,
    vol_accel_m5_vs_h1      REAL,
    txn_accel_m5_vs_h1      REAL,
    r_m5_micro              REAL,
    rv_5m                   REAL,
    rv_1m                   REAL,
    range_5m                REAL,

    -- Family A: Order-flow fallback (snapshot-native; always available)
    buys_m5_snap            REAL,
    sells_m5_snap           REAL,
    buy_count_ratio_m5_snap REAL,
    avg_trade_usd_m5_snap   REAL,

    -- Family B: Route/quote quality (snapshot-native; ~100% coverage)
    jup_vs_cpamm_diff_pct   REAL,
    round_trip_pct          REAL,
    impact_buy_pct          REAL,
    impact_sell_pct         REAL,
    impact_asymmetry_pct    REAL,

    -- Family C: Liquidity (micro-native; NULL if no micro row)
    liq_change_pct          REAL,
    liq_cliff_flag          INTEGER,

    -- Family C: Fire-level market-state aggregates
    --   (computed once per fire; identical across all rows in a fire)
    breadth_positive_pct    REAL,   -- fraction of micro-covered mints with r_m5 > 0
    breadth_negative_pct    REAL,   -- fraction of micro-covered mints with r_m5 < 0
    median_pool_r_m5        REAL,   -- median r_m5 across micro-covered mints
    pool_dispersion_r_m5    REAL,   -- stdev of r_m5 across micro-covered mints
    median_pool_rv5m        REAL,   -- median rv_5m across micro-covered mints
    pool_liquidity_median   REAL,   -- median liq_usd across all snapshot candidates
    pool_vol_h1_median      REAL,   -- median vol_h1 across all snapshot candidates
    pool_size_total         INTEGER,
    pool_size_with_micro    INTEGER,
    coverage_ratio_micro    REAL,

    -- Source flags
    order_flow_source       TEXT    NOT NULL DEFAULT 'missing',
    quote_source            TEXT    NOT NULL DEFAULT 'universe_snapshot',
    liq_source              TEXT    NOT NULL DEFAULT 'missing',

    UNIQUE(fire_id, candidate_mint)
)
"""

CREATE_FIRE_LOG = """
CREATE TABLE IF NOT EXISTS feature_tape_v2_fire_log (
    fire_id         TEXT    PRIMARY KEY,
    fire_time_utc   TEXT    NOT NULL,
    fire_time_epoch REAL    NOT NULL,
    candidates_n    INTEGER,
    rows_written    INTEGER,
    duration_s      REAL,
    created_at      TEXT    NOT NULL
)
"""


# ── Lane derivation ───────────────────────────────────────────────────────────
def derive_lane(eligible, gate_reason, pool_type):
    """
    Canonical lane derivation.
    universe_snapshot.lane is always NULL — must derive here.
    """
    if eligible == 1:
        pt = (pool_type or "").lower()
        if "pumpswap" in pt:
            return "pumpswap_live"
        elif "raydium" in pt:
            return "raydium_live"
        elif "orca" in pt:
            return "orca_live"
        elif "meteora" in pt:
            return "meteora_live"
        else:
            return "other_live"
    gr = (gate_reason or "").lower()
    if "spam" in gr:
        return "spam_filtered"
    elif "impact" in gr or "round_trip" in gr or "slippage" in gr:
        return "impact_filtered"
    elif "age" in gr:
        return "age_filtered"
    elif "vol" in gr or "volume" in gr:
        return "vol_filtered"
    elif "liq" in gr or "liquidity" in gr:
        return "liq_filtered"
    else:
        return "ineligible"


# ── Fire timing ───────────────────────────────────────────────────────────────
def get_next_fire_time():
    """Return the next 15-minute boundary in UTC."""
    now = datetime.now(timezone.utc)
    minutes = (now.minute // 15 + 1) * 15
    if minutes >= 60:
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return now.replace(minute=minutes, second=0, microsecond=0)


def make_fire_id(fire_epoch: float) -> str:
    return hashlib.md5(f"ftv2_{fire_epoch}".encode()).hexdigest()[:8]


# ── Safe aggregates ───────────────────────────────────────────────────────────
def safe_median(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def safe_stdev(vals):
    if len(vals) < 2:
        return None
    try:
        return statistics.stdev(vals)
    except Exception:
        return None


# ── Core fire collection ──────────────────────────────────────────────────────
def collect_fire(con: sqlite3.Connection, fire_epoch: float,
                 fire_utc: str, fire_id: str) -> int:
    cur = con.cursor()
    t0 = time.time()

    # Use isoformat() strings for comparison — matches the +00:00 format
    # written by the scanner (datetime.now(timezone.utc).isoformat())
    fire_ts   = datetime.fromtimestamp(fire_epoch, tz=timezone.utc).isoformat()
    snap_ts   = datetime.fromtimestamp(fire_epoch - SNAP_LOOKBACK_S, tz=timezone.utc).isoformat()
    micro_ts_floor = datetime.fromtimestamp(fire_epoch - MICRO_LOOKBACK_S, tz=timezone.utc).isoformat()

    # ── 1. Candidate universe: all mints with a recent snapshot ──────────────
    cur.execute("""
        SELECT s.mint_address, s.token_symbol, s.snapshot_at,
               s.venue, s.pool_type, s.pumpfun_origin,
               s.eligible, s.gate_reason,
               s.age_hours, s.liq_usd, s.vol_h1, s.vol_h24, s.price_usd,
               s.r_m5, s.r_h1,
               s.buys_m5, s.sells_m5, s.buy_count_ratio_m5, s.avg_trade_usd_m5,
               s.jup_vs_cpamm_diff_pct, s.round_trip_pct,
               s.impact_buy_pct, s.impact_sell_pct
        FROM universe_snapshot s
        INNER JOIN (
            SELECT mint_address, MAX(snapshot_at) AS latest_at
            FROM universe_snapshot
            WHERE snapshot_at <= ?
              AND snapshot_at >= ?
            GROUP BY mint_address
        ) best ON s.mint_address = best.mint_address
               AND s.snapshot_at = best.latest_at
    """, (fire_ts, snap_ts))

    snap_rows = cur.fetchall()
    if not snap_rows:
        log.warning(f"[{fire_id}] No snapshot candidates found in window")
        return 0

    log.info(f"[{fire_id}] {len(snap_rows)} candidates at fire {fire_utc}")
    pool_size_total = len(snap_rows)

    # ── 2. Fire-level micro aggregates (all mints, not just candidates) ─────────
    cur.execute("""
        SELECT m.mint_address, m.r_m5, m.rv_5m
        FROM microstructure_log m
        INNER JOIN (
            SELECT mint_address, MAX(logged_at) AS latest_at
            FROM microstructure_log
            WHERE logged_at <= ?
              AND logged_at >= ?
            GROUP BY mint_address
        ) best ON m.mint_address = best.mint_address
               AND m.logged_at = best.latest_at
    """, (fire_ts, micro_ts_floor))

    all_micro_agg = cur.fetchall()
    pool_size_with_micro = len(all_micro_agg)
    coverage_ratio_micro = (
        pool_size_with_micro / pool_size_total if pool_size_total > 0 else 0.0
    )

    r_m5_vals = [r[1] for r in all_micro_agg if r[1] is not None]
    rv5m_vals = [r[2] for r in all_micro_agg if r[2] is not None]

    breadth_positive_pct = (
        sum(1 for v in r_m5_vals if v > 0) / len(r_m5_vals)
        if r_m5_vals else None
    )
    breadth_negative_pct = (
        sum(1 for v in r_m5_vals if v < 0) / len(r_m5_vals)
        if r_m5_vals else None
    )
    median_pool_r_m5     = safe_median(r_m5_vals)
    pool_dispersion_r_m5 = safe_stdev(r_m5_vals)
    median_pool_rv5m     = safe_median(rv5m_vals)

    snap_liq_vals = [r[9]  for r in snap_rows if r[9]  is not None]
    snap_vol_vals = [r[10] for r in snap_rows if r[10] is not None]
    pool_liquidity_median = safe_median(snap_liq_vals)
    pool_vol_h1_median    = safe_median(snap_vol_vals)

    # ── 3. Per-candidate micro rows ───────────────────────────────────────────
    mint_list = [r[0] for r in snap_rows]
    placeholders = ",".join("?" * len(mint_list))
    cur.execute(f"""
        SELECT m.mint_address, m.logged_at,
               m.buys_m5, m.sells_m5, m.buys_h1, m.sells_h1,
               m.buy_sell_ratio_m5, m.buy_sell_ratio_h1,
               m.buy_count_ratio_m5, m.buy_count_ratio_h1,
               m.avg_trade_usd_m5, m.avg_trade_usd_h1,
               m.vol_accel_m5_vs_h1, m.txn_accel_m5_vs_h1,
               m.r_m5, m.rv_5m, m.rv_1m, m.range_5m,
               m.liq_change_pct, m.liq_cliff_flag
        FROM microstructure_log m
        INNER JOIN (
            SELECT mint_address, MAX(logged_at) AS latest_at
            FROM microstructure_log
            WHERE logged_at <= ?
              AND logged_at >= ?
              AND mint_address IN ({placeholders})
            GROUP BY mint_address
        ) best ON m.mint_address = best.mint_address
               AND m.logged_at = best.latest_at
    """, [fire_ts, micro_ts_floor] + mint_list)

    micro_by_mint = {r[0]: r for r in cur.fetchall()}

    # ── 4. Write per-candidate rows ───────────────────────────────────────────
    rows_written = 0
    now_utc = datetime.now(timezone.utc).isoformat()

    for snap in snap_rows:
        (mint, symbol, snap_at, venue, pool_type, pumpfun_origin,
         eligible, gate_reason,
         age_hours, liq_usd, vol_h1, vol_h24, price_usd,
         r_m5_snap, r_h1_snap,
         buys_m5_snap, sells_m5_snap, buy_count_ratio_m5_snap, avg_trade_usd_m5_snap,
         jup_vs_cpamm_diff_pct, round_trip_pct,
         impact_buy_pct, impact_sell_pct) = snap

        lane = derive_lane(eligible, gate_reason, pool_type)

        impact_asymmetry_pct = (
            (impact_buy_pct - impact_sell_pct)
            if (impact_buy_pct is not None and impact_sell_pct is not None)
            else None
        )

        micro = micro_by_mint.get(mint)
        if micro:
            (_, micro_ts,
             buys_m5, sells_m5, buys_h1, sells_h1,
             buy_sell_ratio_m5, buy_sell_ratio_h1,
             buy_count_ratio_m5, buy_count_ratio_h1,
             avg_trade_usd_m5, avg_trade_usd_h1,
             vol_accel_m5_vs_h1, txn_accel_m5_vs_h1,
             r_m5_micro, rv_5m, rv_1m, range_5m,
             liq_change_pct, liq_cliff_flag) = micro
            order_flow_source = "microstructure_log"
            liq_source = "microstructure_log"
        else:
            # All micro-native fields are NULL — do NOT substitute zeros
            (micro_ts,
             buys_m5, sells_m5, buys_h1, sells_h1,
             buy_sell_ratio_m5, buy_sell_ratio_h1,
             buy_count_ratio_m5, buy_count_ratio_h1,
             avg_trade_usd_m5, avg_trade_usd_h1,
             vol_accel_m5_vs_h1, txn_accel_m5_vs_h1,
             r_m5_micro, rv_5m, rv_1m, range_5m,
             liq_change_pct, liq_cliff_flag) = (None,) * 19
            order_flow_source = "missing"
            liq_source = "missing"

        try:
            cur.execute("""
                INSERT OR IGNORE INTO feature_tape_v2 (
                    fire_id, fire_time_utc, fire_time_epoch,
                    candidate_mint, candidate_symbol,
                    snapshot_at_used, micro_ts_used, created_at,
                    lane, lane_source, venue, pool_type, pumpfun_origin,
                    eligible, gate_reason,
                    age_hours, liquidity_usd, vol_h1, vol_h24, price_usd,
                    r_m5_snap, r_h1_snap,
                    buys_m5, sells_m5, buys_h1, sells_h1,
                    buy_sell_ratio_m5, buy_sell_ratio_h1,
                    buy_count_ratio_m5, buy_count_ratio_h1,
                    avg_trade_usd_m5, avg_trade_usd_h1,
                    vol_accel_m5_vs_h1, txn_accel_m5_vs_h1,
                    r_m5_micro, rv_5m, rv_1m, range_5m,
                    buys_m5_snap, sells_m5_snap,
                    buy_count_ratio_m5_snap, avg_trade_usd_m5_snap,
                    jup_vs_cpamm_diff_pct, round_trip_pct,
                    impact_buy_pct, impact_sell_pct, impact_asymmetry_pct,
                    liq_change_pct, liq_cliff_flag,
                    breadth_positive_pct, breadth_negative_pct,
                    median_pool_r_m5, pool_dispersion_r_m5, median_pool_rv5m,
                    pool_liquidity_median, pool_vol_h1_median,
                    pool_size_total, pool_size_with_micro, coverage_ratio_micro,
                    order_flow_source, quote_source, liq_source
                ) VALUES (
                    ?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,
                    ?,?,?,?,?,
                    ?,?,
                    ?,?,?,?,?,?,?,?,?,?,
                    ?,?,?
                )
            """, (
                fire_id, fire_utc, fire_epoch,
                mint, symbol,
                snap_at, micro_ts, now_utc,
                lane, "derived_at_collection", venue, pool_type, pumpfun_origin,
                eligible, gate_reason,
                age_hours, liq_usd, vol_h1, vol_h24, price_usd,
                r_m5_snap, r_h1_snap,
                buys_m5, sells_m5, buys_h1, sells_h1,
                buy_sell_ratio_m5, buy_sell_ratio_h1,
                buy_count_ratio_m5, buy_count_ratio_h1,
                avg_trade_usd_m5, avg_trade_usd_h1,
                vol_accel_m5_vs_h1, txn_accel_m5_vs_h1,
                r_m5_micro, rv_5m, rv_1m, range_5m,
                buys_m5_snap, sells_m5_snap,
                buy_count_ratio_m5_snap, avg_trade_usd_m5_snap,
                jup_vs_cpamm_diff_pct, round_trip_pct,
                impact_buy_pct, impact_sell_pct, impact_asymmetry_pct,
                liq_change_pct, liq_cliff_flag,
                breadth_positive_pct, breadth_negative_pct,
                median_pool_r_m5, pool_dispersion_r_m5, median_pool_rv5m,
                pool_liquidity_median, pool_vol_h1_median,
                pool_size_total, pool_size_with_micro, coverage_ratio_micro,
                order_flow_source, "universe_snapshot", liq_source,
            ))
            rows_written += cur.rowcount
        except Exception as e:
            log.error(f"[{fire_id}] Insert error for {mint}: {e}")

    con.commit()
    duration = time.time() - t0

    # Write fire log
    cur.execute("""
        INSERT OR REPLACE INTO feature_tape_v2_fire_log
        (fire_id, fire_time_utc, fire_time_epoch,
         candidates_n, rows_written, duration_s, created_at)
        VALUES (?,?,?,?,?,?,?)
    """, (fire_id, fire_utc, fire_epoch,
          len(snap_rows), rows_written, round(duration, 2),
          datetime.now(timezone.utc).isoformat()))
    con.commit()

    log.info(
        f"[{fire_id}] Wrote {rows_written}/{len(snap_rows)} rows in {duration:.1f}s "
        f"| micro_coverage={pool_size_with_micro}/{pool_size_total} "
        f"| breadth+={breadth_positive_pct:.1%} "
        f"| median_r_m5={median_pool_r_m5}"
        if breadth_positive_pct is not None and median_pool_r_m5 is not None
        else f"[{fire_id}] Wrote {rows_written}/{len(snap_rows)} rows in {duration:.1f}s "
             f"| micro_coverage={pool_size_with_micro}/{pool_size_total}"
    )
    return rows_written


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info("feature_tape_v2 starting (post-audit rewrite 2026-03-12)")
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(CREATE_TABLE)
    con.execute(CREATE_FIRE_LOG)
    con.commit()
    log.info("Schema ready")

    while True:
        next_fire = get_next_fire_time()
        wait_s = (next_fire - datetime.now(timezone.utc)).total_seconds()
        if wait_s > 0:
            log.info(f"Next fire at {next_fire.isoformat()} (in {wait_s:.0f}s)")
            time.sleep(wait_s)

        fire_epoch = next_fire.timestamp()
        fire_utc   = next_fire.strftime("%Y-%m-%dT%H:%M:%SZ")
        fire_id    = make_fire_id(fire_epoch)

        log.info(f"FIRE {fire_id} at {fire_utc}")
        try:
            collect_fire(con, fire_epoch, fire_utc, fire_id)
        except Exception as e:
            log.error(f"[{fire_id}] Unhandled error: {e}", exc_info=True)

        # Small sleep past boundary to avoid double-fire edge case
        time.sleep(5)


if __name__ == "__main__":
    main()
