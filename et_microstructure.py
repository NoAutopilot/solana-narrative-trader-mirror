#!/usr/bin/env python3
"""
Existing Tokens Microstructure Logger — v1.8
=============================================
Changes from v2:
  + rv_1m:        realized vol (stdev of log-returns) over last 4 polls (~1m)
  + rv_5m:        realized vol over last 20 polls (~5m)
  + range_5m:     (max_price - min_price) / mid_price over last 20 polls
  + pumpfun_origin: 1 if token originated on Pump.fun (venue=pumpswap OR pair_created_at < 48h ago)
  + buy_sell_ratio_m5 / buy_sell_ratio_h1 aliases kept for backward compat
"""
import os
import sys
import time
import math
import logging
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

sys.path.insert(0, "/root/solana_trader")
try:
    from cpamm_math import k_lp_cliff
except ImportError:
    def k_lp_cliff(k_old, k_new, threshold=0.05):
        if k_old <= 0:
            return {"k_change_pct": 0.0, "lp_removal_flag": False}
        k_change = (k_new - k_old) / k_old
        return {"k_change_pct": k_change, "lp_removal_flag": k_change < -threshold}

from config.config import DB_PATH, LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("et_microstructure")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s [microstructure] %(levelname)s: %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "et_microstructure.log"))
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

DEXSCREENER_BASE     = "https://api.dexscreener.com"
HELIUS_RPC_URL       = os.environ.get("HELIUS_RPC_URL", "")
POLL_INTERVAL_SEC    = 15
LP_CLIFF_THRESHOLD   = 0.05
DEXSCREENER_TIMEOUT  = 12
MAX_TOKENS_PER_BATCH = 30

# Rolling price buffers for rv computation
# deque of (timestamp_float, log_price) per mint
# 20 polls @ 15s = 5m; 4 polls = 1m
_price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=24))
RV_1M_POLLS  = 4    # ~1 minute
RV_5M_POLLS  = 20   # ~5 minutes

def compute_rv(prices: list[float]) -> float | None:
    """Compute annualized realized vol from a list of prices (stdev of log-returns)."""
    if len(prices) < 2:
        return None
    log_rets = []
    for i in range(1, len(prices)):
        if prices[i-1] > 0 and prices[i] > 0:
            log_rets.append(math.log(prices[i] / prices[i-1]))
    if len(log_rets) < 1:
        return None
    n = len(log_rets)
    mean = sum(log_rets) / n
    variance = sum((r - mean) ** 2 for r in log_rets) / max(n - 1, 1)
    return math.sqrt(variance) * 100  # as percent per poll-interval (not annualized)

def compute_range(prices: list[float]) -> float | None:
    """Compute (max - min) / mid as a percent."""
    if len(prices) < 2:
        return None
    hi = max(prices)
    lo = min(prices)
    mid = (hi + lo) / 2
    if mid <= 0:
        return None
    return (hi - lo) / mid * 100

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_tables():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS microstructure_log (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at                TEXT    NOT NULL,
        mint_address             TEXT    NOT NULL,
        token_symbol             TEXT,
        pair_address             TEXT,
        venue                    TEXT,
        -- Price & returns
        price_usd                REAL,
        price_native             REAL,
        r_m5                     REAL,
        r_h1                     REAL,
        r_h6                     REAL,
        r_h24                    REAL,
        -- Realized vol (v1.8)
        rv_1m                    REAL,   -- stdev of log-returns over last ~1m polls, as %
        rv_5m                    REAL,   -- stdev of log-returns over last ~5m polls, as %
        range_5m                 REAL,   -- (max-min)/mid over last ~5m polls, as %
        -- Volume
        vol_m5                   REAL,
        vol_h1                   REAL,
        vol_h6                   REAL,
        vol_h24                  REAL,
        -- Flow
        buys_m5                  INTEGER,
        sells_m5                 INTEGER,
        buys_h1                  INTEGER,
        sells_h1                 INTEGER,
        buy_sell_ratio_m5        REAL,   -- alias for buy_count_ratio_m5
        buy_sell_ratio_h1        REAL,   -- alias for buy_count_ratio_h1
        buy_count_ratio_m5       REAL,
        buy_count_ratio_h1       REAL,
        avg_trade_usd_m5         REAL,
        avg_trade_usd_h1         REAL,
        spam_flag                INTEGER DEFAULT 0,
        -- Derived flow signals
        vol_accel_m5_vs_h1       REAL,
        txn_accel_m5_vs_h1       REAL,
        -- Liquidity
        liq_usd                  REAL,
        liq_quote_sol            REAL,
        liq_base                 REAL,
        liq_prev_usd             REAL,
        liq_change_pct           REAL,
        liq_cliff_flag           INTEGER DEFAULT 0,
        -- k-invariant LP cliff
        k_invariant              REAL,
        k_prev                   REAL,
        k_change_pct             REAL,
        lp_removal_flag          INTEGER DEFAULT 0,
        -- Safety flags
        mint_authority_present   INTEGER,
        freeze_authority_present INTEGER,
        -- Origin flag (v1.8)
        pumpfun_origin           INTEGER DEFAULT 0,  -- 1 if pump.fun graduated token
        -- Metadata
        fdv                      REAL,
        market_cap               REAL
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_micro_logged_at ON microstructure_log(logged_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_micro_mint ON microstructure_log(mint_address, logged_at)")

    # Add new columns to existing table if missing (migration)
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(microstructure_log)")}
    migrations = [
        ("rv_1m",          "ALTER TABLE microstructure_log ADD COLUMN rv_1m REAL"),
        ("rv_5m",          "ALTER TABLE microstructure_log ADD COLUMN rv_5m REAL"),
        ("range_5m",       "ALTER TABLE microstructure_log ADD COLUMN range_5m REAL"),
        ("pumpfun_origin", "ALTER TABLE microstructure_log ADD COLUMN pumpfun_origin INTEGER DEFAULT 0"),
        ("buy_sell_ratio_m5", "ALTER TABLE microstructure_log ADD COLUMN buy_sell_ratio_m5 REAL"),
        ("buy_sell_ratio_h1", "ALTER TABLE microstructure_log ADD COLUMN buy_sell_ratio_h1 REAL"),
        ("liq_prev_usd",   "ALTER TABLE microstructure_log ADD COLUMN liq_prev_usd REAL"),
        ("liq_change_pct", "ALTER TABLE microstructure_log ADD COLUMN liq_change_pct REAL"),
        ("liq_cliff_flag", "ALTER TABLE microstructure_log ADD COLUMN liq_cliff_flag INTEGER DEFAULT 0"),
    ]
    for col_name, sql in migrations:
        if col_name not in existing_cols:
            try:
                c.execute(sql)
                logger.info(f"Migration: added column {col_name}")
            except Exception as e:
                logger.warning(f"Migration skipped {col_name}: {e}")

    conn.commit()
    conn.close()
    logger.info("Table initialized: microstructure_log (v1.8)")

# ── k-invariant tracking ──────────────────────────────────────────────────────
_k_cache: dict[str, float] = {}

def get_k_cliff(mint: str, k_new: float) -> tuple[float | None, float | None, int]:
    k_old = _k_cache.get(mint)
    if k_old is None:
        _k_cache[mint] = k_new
        return None, None, 0
    result = k_lp_cliff(k_old, k_new, LP_CLIFF_THRESHOLD)
    _k_cache[mint] = k_new
    return k_old, result["k_change_pct"], int(result["lp_removal_flag"])

# ── Liquidity tracking ────────────────────────────────────────────────────────
_liq_cache: dict[str, float] = {}

def get_liq_change(mint: str, liq_new: float) -> tuple[float | None, float | None, int]:
    liq_old = _liq_cache.get(mint)
    if liq_old is None:
        _liq_cache[mint] = liq_new
        return None, None, 0
    change_pct = (liq_new - liq_old) / liq_old if liq_old > 0 else None
    cliff = 1 if (change_pct is not None and change_pct < -0.10) else 0
    _liq_cache[mint] = liq_new
    return liq_old, change_pct, cliff

# ── Safety flags ──────────────────────────────────────────────────────────────
_authority_cache: dict[str, tuple] = {}
AUTHORITY_CACHE_TTL = 3600

def get_cached_authorities(mint: str) -> tuple[int | None, int | None]:
    cached = _authority_cache.get(mint)
    if cached:
        _, _, fetched_at = cached
        if time.time() - fetched_at < AUTHORITY_CACHE_TTL:
            return cached[0], cached[1]
    if not HELIUS_RPC_URL:
        return None, None
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [mint, {"encoding": "jsonParsed"}]
        }
        r = requests.post(HELIUS_RPC_URL, json=payload, timeout=5)
        info = r.json().get("result", {}).get("value", {}).get("data", {}).get("parsed", {}).get("info", {})
        ma = 1 if info.get("mintAuthority") else 0
        fa = 1 if info.get("freezeAuthority") else 0
        _authority_cache[mint] = (ma, fa, time.time())
        return ma, fa
    except Exception:
        return None, None

# ── Fetch ─────────────────────────────────────────────────────────────────────
def get_eligible_mints() -> list[tuple[str, str, str | None]]:
    """Returns (mint_address, pair_address, pair_created_at)."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT mint_address, pair_address, pair_created_at, venue
        FROM universe_snapshot
        WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM universe_snapshot)
          AND eligible = 1 AND cpamm_valid_flag = 1
        ORDER BY vol_h24 DESC
        LIMIT 200
    """)
    rows = c.fetchall()
    conn.close()
    return [(r["mint_address"], r["pair_address"], r["pair_created_at"], r["venue"]) for r in rows]

def is_pumpfun_origin(venue: str | None, pair_created_at: str | None) -> int:
    """
    Returns 1 if token is pump.fun-origin:
    - venue is 'pumpswap' or 'pump' (graduated from pump.fun), OR
    - pair_created_at is within last 48h on any venue (fresh launch)
    """
    if venue and venue.lower() in ("pumpswap", "pump", "pump.fun"):
        return 1
    if pair_created_at:
        try:
            created = datetime.fromisoformat(pair_created_at.replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            if age_h < 48:
                return 1
        except Exception:
            pass
    return 0

def fetch_pairs_batch(mints: list[str]) -> list[dict]:
    if not mints:
        return []
    try:
        r = requests.get(
            f"{DEXSCREENER_BASE}/latest/dex/tokens/{','.join(mints[:MAX_TOKENS_PER_BATCH])}",
            timeout=DEXSCREENER_TIMEOUT
        )
        return r.json().get("pairs", [])
    except Exception as e:
        logger.debug(f"Batch fetch error: {e}")
        return []

# ── Poll ──────────────────────────────────────────────────────────────────────
def poll_and_log():
    eligible = get_eligible_mints()
    if not eligible:
        return

    logged_at = datetime.now(timezone.utc).isoformat()
    now_ts = time.time()
    rows = []

    for i in range(0, len(eligible), MAX_TOKENS_PER_BATCH):
        batch = eligible[i:i + MAX_TOKENS_PER_BATCH]
        mints = [m for m, _, _, _ in batch]
        pairs = fetch_pairs_batch(mints)

        mint_to_pair: dict[str, dict] = {}
        for pair in pairs:
            mint = pair.get("baseToken", {}).get("address", "")
            if not mint:
                continue
            liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
            existing = mint_to_pair.get(mint)
            if existing is None or liq > float(existing.get("liquidity", {}).get("usd", 0) or 0):
                mint_to_pair[mint] = pair

        for mint, _, pair_created_at, venue_db in batch:
            pair = mint_to_pair.get(mint)
            if not pair:
                continue

            liq    = pair.get("liquidity", {})
            vol    = pair.get("volume", {})
            pc     = pair.get("priceChange", {})
            txns   = pair.get("txns", {})

            liq_usd       = float(liq.get("usd", 0) or 0)
            liq_quote_sol = float(liq.get("quote", 0) or 0)
            liq_base      = float(liq.get("base", 0) or 0)

            vol_m5  = float(vol.get("m5", 0) or 0)
            vol_h1  = float(vol.get("h1", 0) or 0)
            vol_h6  = float(vol.get("h6", 0) or 0)
            vol_h24 = float(vol.get("h24", 0) or 0)

            buys_m5  = int(txns.get("m5", {}).get("buys", 0) or 0)
            sells_m5 = int(txns.get("m5", {}).get("sells", 0) or 0)
            buys_h1  = int(txns.get("h1", {}).get("buys", 0) or 0)
            sells_h1 = int(txns.get("h1", {}).get("sells", 0) or 0)
            total_m5 = buys_m5 + sells_m5
            total_h1 = buys_h1 + sells_h1

            buy_count_ratio_m5 = buys_m5 / total_m5 if total_m5 > 0 else None
            buy_count_ratio_h1 = buys_h1 / total_h1 if total_h1 > 0 else None
            avg_trade_usd_m5   = vol_m5 / total_m5 if total_m5 > 0 else None
            avg_trade_usd_h1   = vol_h1 / total_h1 if total_h1 > 0 else None
            spam_flag = 1 if (avg_trade_usd_m5 is not None and avg_trade_usd_m5 < 1.0) else 0

            vol_accel = (vol_m5 * 12) / vol_h1 if vol_h1 > 0 else None
            txn_accel = (total_m5 * 12) / total_h1 if total_h1 > 0 else None

            # k-invariant LP cliff
            k_new = liq_base * liq_quote_sol if liq_base > 0 and liq_quote_sol > 0 else 0
            k_prev, k_change_pct, lp_flag = get_k_cliff(mint, k_new)

            # Liquidity change
            liq_prev, liq_chg_pct, liq_cliff = get_liq_change(mint, liq_usd)

            ma, fa = get_cached_authorities(mint)

            # ── v1.8: Realized vol from rolling price history ──────────────────
            price_usd = float(pair.get("priceUsd", 0) or 0)
            if price_usd > 0:
                _price_history[mint].append((now_ts, price_usd))

            hist = _price_history[mint]
            hist_prices = [p for _, p in hist]

            rv_1m    = None
            rv_5m    = None
            range_5m = None

            if len(hist_prices) >= 2:
                rv_5m    = compute_rv(hist_prices[-RV_5M_POLLS:])
                range_5m = compute_range(hist_prices[-RV_5M_POLLS:])
            if len(hist_prices) >= 2:
                rv_1m = compute_rv(hist_prices[-RV_1M_POLLS:])

            # ── v1.8: pumpfun_origin flag ──────────────────────────────────────
            venue_pair = pair.get("dexId", "") or ""
            pf_origin = is_pumpfun_origin(venue_pair or venue_db, pair_created_at)

            rows.append((
                logged_at, mint,
                pair.get("baseToken", {}).get("symbol", ""),
                pair.get("pairAddress", ""), venue_pair,
                price_usd,
                float(pair.get("priceNative", 0) or 0),
                float(pc.get("m5", 0) or 0),
                float(pc.get("h1", 0) or 0),
                float(pc.get("h6", 0) or 0),
                float(pc.get("h24", 0) or 0),
                rv_1m, rv_5m, range_5m,
                vol_m5, vol_h1, vol_h6, vol_h24,
                buys_m5, sells_m5, buys_h1, sells_h1,
                buy_count_ratio_m5, buy_count_ratio_h1,  # buy_sell_ratio aliases
                buy_count_ratio_m5, buy_count_ratio_h1,  # buy_count_ratio
                avg_trade_usd_m5, avg_trade_usd_h1, spam_flag,
                vol_accel, txn_accel,
                liq_usd, liq_quote_sol, liq_base,
                liq_prev, liq_chg_pct, liq_cliff,
                k_new if k_new > 0 else None,
                k_prev, k_change_pct, lp_flag,
                ma, fa,
                pf_origin,
                float(pair.get("fdv", 0) or 0),
                float(pair.get("marketCap", 0) or 0),
            ))

        time.sleep(0.3)

    if rows:
        conn = get_conn()
        conn.executemany("""
            INSERT INTO microstructure_log
            (logged_at, mint_address, token_symbol, pair_address, venue,
             price_usd, price_native, r_m5, r_h1, r_h6, r_h24,
             rv_1m, rv_5m, range_5m,
             vol_m5, vol_h1, vol_h6, vol_h24,
             buys_m5, sells_m5, buys_h1, sells_h1,
             buy_sell_ratio_m5, buy_sell_ratio_h1,
             buy_count_ratio_m5, buy_count_ratio_h1,
             avg_trade_usd_m5, avg_trade_usd_h1, spam_flag,
             vol_accel_m5_vs_h1, txn_accel_m5_vs_h1,
             liq_usd, liq_quote_sol, liq_base,
             liq_prev_usd, liq_change_pct, liq_cliff_flag,
             k_invariant, k_prev, k_change_pct, lp_removal_flag,
             mint_authority_present, freeze_authority_present,
             pumpfun_origin,
             fdv, market_cap)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
        conn.close()
        n_lp    = sum(1 for r in rows if r[40] == 1)
        n_spam  = sum(1 for r in rows if r[28] == 1)
        n_pf    = sum(1 for r in rows if r[43] == 1)
        rv_vals = [r[12] for r in rows if r[12] is not None]
        rv_med  = sorted(rv_vals)[len(rv_vals)//2] if rv_vals else None
        logger.info(
            f"Logged {len(rows)} rows | lp_removal={n_lp} | spam={n_spam} | "
            f"pumpfun_origin={n_pf} | rv_5m_median={rv_med:.4f}%" if rv_med else
            f"Logged {len(rows)} rows | lp_removal={n_lp} | spam={n_spam} | pumpfun_origin={n_pf} | rv_5m=warming_up"
        )

def run():
    logger.info("=" * 65)
    logger.info("Existing Tokens Microstructure Logger v1.8 starting")
    logger.info(f"  LP cliff threshold: {LP_CLIFF_THRESHOLD*100:.0f}% k-drop")
    logger.info(f"  Spam threshold: avg_trade_usd < $1")
    logger.info(f"  rv_5m: {RV_5M_POLLS} polls (~{RV_5M_POLLS*POLL_INTERVAL_SEC}s window)")
    logger.info(f"  rv_1m: {RV_1M_POLLS} polls (~{RV_1M_POLLS*POLL_INTERVAL_SEC}s window)")
    logger.info("=" * 65)
    init_tables()

    for _ in range(12):
        mints = get_eligible_mints()
        if mints:
            logger.info(f"Universe ready: {len(mints)} eligible tokens")
            break
        logger.info("Waiting for universe_snapshot data...")
        time.sleep(10)

    while True:
        loop_start = time.time()
        try:
            poll_and_log()
        except Exception as e:
            logger.error(f"Poll error: {e}", exc_info=True)
        elapsed = time.time() - loop_start
        time.sleep(max(2, POLL_INTERVAL_SEC - elapsed))

if __name__ == "__main__":
    run()
