#!/usr/bin/env python3
"""
Existing Tokens Microstructure Logger — P2  (v2, patched)
==========================================================
Patches applied:
  Fix 2: LP cliff via k-invariant drop (not reserve change)
  Fix 5: buy_count_ratio (renamed), avg_trade_usd, spam/trap heuristics
  Fix 3+4: Only logs tokens from universe_snapshot (already gated by pool_type + SOL quote)
"""
import os
import sys
import time
import logging
import sqlite3
import requests
from datetime import datetime, timezone

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

DEXSCREENER_BASE    = "https://api.dexscreener.com"
HELIUS_RPC_URL      = os.environ.get("HELIUS_RPC_URL", "")
POLL_INTERVAL_SEC   = 15
LP_CLIFF_THRESHOLD  = 0.05
DEXSCREENER_TIMEOUT = 12
MAX_TOKENS_PER_BATCH = 30

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
        -- Volume
        vol_m5                   REAL,
        vol_h1                   REAL,
        vol_h6                   REAL,
        vol_h24                  REAL,
        -- Flow (Fix 5: renamed + new fields)
        buys_m5                  INTEGER,
        sells_m5                 INTEGER,
        buys_h1                  INTEGER,
        sells_h1                 INTEGER,
        buy_count_ratio_m5       REAL,   -- renamed from buy_sell_ratio_m5
        buy_count_ratio_h1       REAL,   -- renamed from buy_sell_ratio_h1
        avg_trade_usd_m5         REAL,   -- new: vol_m5 / (buys+sells)
        avg_trade_usd_h1         REAL,   -- new: vol_h1 / (buys_h1+sells_h1)
        spam_flag                INTEGER DEFAULT 0,  -- avg_trade < $1
        -- Derived flow signals
        vol_accel_m5_vs_h1       REAL,
        txn_accel_m5_vs_h1       REAL,
        -- Liquidity
        liq_usd                  REAL,
        liq_quote_sol            REAL,
        liq_base                 REAL,
        -- Fix 2: k-invariant LP cliff (not reserve-change cliff)
        k_invariant              REAL,
        k_prev                   REAL,
        k_change_pct             REAL,
        lp_removal_flag          INTEGER DEFAULT 0,
        -- Safety flags (from RPC, nullable)
        mint_authority_present   INTEGER,
        freeze_authority_present INTEGER,
        -- Metadata
        fdv                      REAL,
        market_cap               REAL
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_micro_logged_at ON microstructure_log(logged_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_micro_mint ON microstructure_log(mint_address, logged_at)")
    conn.commit()
    conn.close()
    logger.info("Table initialized: microstructure_log (v2)")

# ── k-invariant tracking ──────────────────────────────────────────────────────
_k_cache: dict[str, float] = {}

def get_k_cliff(mint: str, k_new: float) -> tuple[float | None, float | None, int]:
    """Returns (k_prev, k_change_pct, lp_removal_flag)."""
    k_old = _k_cache.get(mint)
    if k_old is None:
        _k_cache[mint] = k_new
        return None, None, 0
    result = k_lp_cliff(k_old, k_new, LP_CLIFF_THRESHOLD)
    _k_cache[mint] = k_new
    return k_old, result["k_change_pct"], int(result["lp_removal_flag"])

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
def get_eligible_mints() -> list[tuple[str, str]]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT mint_address, pair_address
        FROM universe_snapshot
        WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM universe_snapshot)
          AND eligible = 1
        ORDER BY vol_h24 DESC
        LIMIT 200
    """)
    rows = c.fetchall()
    conn.close()
    return [(r["mint_address"], r["pair_address"]) for r in rows]

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
    rows = []

    for i in range(0, len(eligible), MAX_TOKENS_PER_BATCH):
        batch = eligible[i:i + MAX_TOKENS_PER_BATCH]
        mints = [m for m, _ in batch]
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

        for mint, _ in batch:
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

            # Fix 5: renamed ratios
            buy_count_ratio_m5 = buys_m5 / total_m5 if total_m5 > 0 else None
            buy_count_ratio_h1 = buys_h1 / total_h1 if total_h1 > 0 else None
            avg_trade_usd_m5   = vol_m5 / total_m5 if total_m5 > 0 else None
            avg_trade_usd_h1   = vol_h1 / total_h1 if total_h1 > 0 else None
            spam_flag = 1 if (avg_trade_usd_m5 is not None and avg_trade_usd_m5 < 1.0) else 0

            vol_accel = (vol_m5 * 12) / vol_h1 if vol_h1 > 0 else None
            txn_accel = (total_m5 * 12) / total_h1 if total_h1 > 0 else None

            # Fix 2: k-invariant LP cliff
            k_new = liq_base * liq_quote_sol if liq_base > 0 and liq_quote_sol > 0 else 0
            k_prev, k_change_pct, lp_flag = get_k_cliff(mint, k_new)

            ma, fa = get_cached_authorities(mint)

            rows.append((
                logged_at, mint,
                pair.get("baseToken", {}).get("symbol", ""),
                pair.get("pairAddress", ""), pair.get("dexId", ""),
                float(pair.get("priceUsd", 0) or 0),
                float(pair.get("priceNative", 0) or 0),
                float(pc.get("m5", 0) or 0),
                float(pc.get("h1", 0) or 0),
                float(pc.get("h6", 0) or 0),
                float(pc.get("h24", 0) or 0),
                vol_m5, vol_h1, vol_h6, vol_h24,
                buys_m5, sells_m5, buys_h1, sells_h1,
                buy_count_ratio_m5, buy_count_ratio_h1,
                avg_trade_usd_m5, avg_trade_usd_h1, spam_flag,
                vol_accel, txn_accel,
                liq_usd, liq_quote_sol, liq_base,
                k_new if k_new > 0 else None,
                k_prev, k_change_pct, lp_flag,
                ma, fa,
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
             vol_m5, vol_h1, vol_h6, vol_h24,
             buys_m5, sells_m5, buys_h1, sells_h1,
             buy_count_ratio_m5, buy_count_ratio_h1,
             avg_trade_usd_m5, avg_trade_usd_h1, spam_flag,
             vol_accel_m5_vs_h1, txn_accel_m5_vs_h1,
             liq_usd, liq_quote_sol, liq_base,
             k_invariant, k_prev, k_change_pct, lp_removal_flag,
             mint_authority_present, freeze_authority_present,
             fdv, market_cap)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
        conn.close()
        n_lp = sum(1 for r in rows if r[32] == 1)
        n_spam = sum(1 for r in rows if r[23] == 1)
        logger.info(f"Logged {len(rows)} rows | lp_removal_events={n_lp} | spam_flags={n_spam}")

def run():
    logger.info("=" * 65)
    logger.info("Existing Tokens Microstructure Logger v2 starting (P2)")
    logger.info(f"  LP cliff threshold: {LP_CLIFF_THRESHOLD*100:.0f}% k-drop")
    logger.info(f"  Spam threshold: avg_trade_usd < $1")
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
