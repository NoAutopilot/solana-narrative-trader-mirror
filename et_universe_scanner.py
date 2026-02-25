import random
#!/usr/bin/env python3
"""
Existing Tokens Universe Scanner — P0 + P1  (v2, patched)
==========================================================
Patches applied:
  Fix 1: Correct CPAMM x*y=k math (imported from cpamm_math)
  Fix 2: LP cliff via k-invariant drop, not reserve-change
  Fix 3: Pool type gating — CPMM-valid dexIds only
  Fix 4: SOL/wSOL quote token filter
  Fix 5: buy_count_ratio (not "imbalance"), avg_trade_usd, spam heuristics
  Fix 6: Deterministic candidate discovery rule + discovery_log table
  Fix 7: Jupiter quote path restored (api.jup.ag/swap/v1/quote) for validation

Discovery rule (deterministic, logged):
  Source: DexScreener /latest/dex/search?q=SOL (top-volume Solana pairs)
  Filter: age >= 1h, age <= 30d, vol_h24 >= $10k, liq_usd >= $5k,
          dexId in CPMM_VALID_DEX_IDS, quote token = SOL/wSOL
  Sort: vol_h24 DESC, take top 200
  Logged to: discovery_log table with rule_version and filter params
"""
import os
import sys
import time
import logging
import sqlite3
import requests
from datetime import datetime, timezone, timedelta

# Import corrected CPAMM math
sys.path.insert(0, "/root/solana_trader")
try:
    from cpamm_math import cpamm_round_trip, k_lp_cliff, gate_pair, CPMM_VALID_DEX_IDS, SOL_QUOTE_MINTS
except ImportError:
    # Fallback inline if module not found
    def cpamm_round_trip(sol_in, x, y, fee=0.0025):
        if x <= 0 or y <= 0 or sol_in <= 0:
            return {"buy_slippage": 1.0, "sell_slippage": 1.0, "total_friction": 1.0, "sol_returned": 0.0}
        s_eff = sol_in * (1 - fee)
        tokens_out = x * s_eff / (y + s_eff)
        if tokens_out <= 0:
            return {"buy_slippage": 1.0, "sell_slippage": 1.0, "total_friction": 1.0, "sol_returned": 0.0}
        t_eff = tokens_out * (1 - fee)
        sol_out = y * t_eff / (x + t_eff)
        spot = y / x
        eff_buy = sol_in / tokens_out
        eff_sell = sol_out / tokens_out
        return {
            "buy_slippage":   eff_buy / spot - 1.0,
            "sell_slippage":  1.0 - eff_sell / spot,
            "total_friction": 1.0 - sol_out / sol_in,
            "sol_returned":   sol_out,
        }
    def k_lp_cliff(k_old, k_new, threshold=0.05):
        if k_old <= 0:
            return {"k_change_pct": 0.0, "lp_removal_flag": False}
        k_change = (k_new - k_old) / k_old
        return {"k_change_pct": k_change, "lp_removal_flag": k_change < -threshold}
    CPMM_VALID_DEX_IDS = {"raydium", "orca", "pumpswap", "meteora", "fluxbeam", "pumpfun", "meteoradbc"}
    SOL_QUOTE_MINTS = {
        "So11111111111111111111111111111111111111112",
        "So11111111111111111111111111111111111111111",
    }
    def gate_pair(pair):
        dex_id = pair.get("dexId", "").lower()
        quote_mint = pair.get("quoteToken", {}).get("address", "")
        if dex_id not in CPMM_VALID_DEX_IDS:
            return False, f"unknown_pool_type:{dex_id}"
        if quote_mint not in SOL_QUOTE_MINTS:
            return False, f"non_sol_quote:{quote_mint[:8]}"
        return True, "ok"

from config.config import DB_PATH, LOGS_DIR, DATA_DIR

os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("et_universe_scanner")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s [universe_scanner] %(levelname)s: %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "et_universe_scanner.log"))
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

# ── Constants ─────────────────────────────────────────────────────────────────
DEXSCREENER_BASE    = "https://api.dexscreener.com"
JUPITER_QUOTE_URL   = "https://api.jup.ag/ultra/v1/order"  # Updated: ultra endpoint
WSOL_MINT           = "So11111111111111111111111111111111111111112"
DEXSCREENER_TIMEOUT = 12
JUPITER_TIMEOUT     = 8
SCAN_INTERVAL_SEC   = 60
TRADE_SIZE_SOL      = 0.02
ROUND_TRIP_GATE     = 0.03   # 3% max round-trip friction
LP_CLIFF_THRESHOLD  = 0.05   # 5% k drop = LP removal flag

# ── PumpSwap universe lane ────────────────────────────────────────────────────
# Refreshed every PUMPSWAP_REFRESH_SEC (default: 1800s = 30 min).
# Queries DexScreener for recently graduated pump.fun tokens on pumpswap.
# Filters: age 1h–7d, vol_h24 >= $5k, liq_usd >= $2k, dexId = pumpswap
PUMPSWAP_REFRESH_SEC    = 1800   # refresh every 30 min
PUMPSWAP_MAX_AGE_DAYS   = 7      # only recently graduated tokens
PUMPSWAP_MIN_VOL_H24    = 5_000  # lower bar than established lane ($5k)
PUMPSWAP_MIN_LIQ_USD    = 2_000  # lower bar ($2k)
PUMPSWAP_MAX_TOKENS     = 50     # top-50 by vol
_pumpswap_cache: list[dict] = []
_pumpswap_last_refresh: float = 0.0

# ── Discovery rule (deterministic, versioned) ─────────────────────────────────
DISCOVERY_RULE = {
    "version":       "v1.1",
    "source":        "dexscreener_tokens_mint_lookup + pumpswap_graduated",
    "min_age_hours": 1,
    "max_age_days":  3650,
    "min_vol_h24":   10_000,   # USD (established lane)
    "min_liq_usd":   5_000,    # USD (established lane)
    "max_tokens":    200,
    "sort_by":       "vol_h24_desc",
    "pool_types":    sorted(CPMM_VALID_DEX_IDS),
    "quote_filter":  "SOL_wSOL_only",
    "scan_method":   "fixed_mint_list_20_tokens + pumpswap_graduated_lane",
    "universe_lane": "trending_established + pumpswap_graduated",
    "lane_caveat":   "Two lanes: top-20 large-cap + top-50 recently graduated pumpswap tokens",
}

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_tables():
    conn = get_conn()
    c = conn.cursor()

    # Universe snapshot (eligible tokens per minute)
    c.execute("""
    CREATE TABLE IF NOT EXISTS universe_snapshot (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_at     TEXT    NOT NULL,
        mint_address    TEXT    NOT NULL,
        token_symbol    TEXT,
        pair_address    TEXT,
        venue           TEXT,
        pool_type       TEXT,
        eligible        INTEGER DEFAULT 0,
        gate_reason     TEXT,
        -- Liquidity
        liq_usd         REAL,
        liq_quote_sol   REAL,
        liq_base        REAL,
        k_invariant     REAL,
        -- Volume
        vol_h24         REAL,
        vol_h1          REAL,
        vol_m5          REAL,
        -- Price
        price_usd       REAL,
        price_native    REAL,
        -- Flow (Fix 5: renamed)
        buys_m5         INTEGER,
        sells_m5        INTEGER,
        buy_count_ratio_m5  REAL,   -- renamed from buy_sell_ratio
        avg_trade_usd_m5    REAL,   -- new: vol_m5 / (buys+sells)
        spam_flag           INTEGER DEFAULT 0,  -- new: avg_trade < $1
        -- Impact gate
        impact_buy_pct  REAL,
        impact_sell_pct REAL,
        round_trip_pct  REAL,
        -- Jupiter quote validation (nullable)
        jup_quote_in_sol    REAL,
        jup_quote_out_tokens REAL,
        jup_slippage_pct    REAL,
        jup_vs_cpamm_diff_pct REAL,
        -- Age
        pair_created_at TEXT,
        age_hours       REAL
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_snap_at ON universe_snapshot(snapshot_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snap_mint ON universe_snapshot(mint_address, snapshot_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snap_eligible ON universe_snapshot(eligible, snapshot_at)")

    # Impact gate log (every token evaluated, pass or fail)
    c.execute("""
    CREATE TABLE IF NOT EXISTS impact_gate_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        evaluated_at    TEXT    NOT NULL,
        mint_address    TEXT    NOT NULL,
        trade_size_sol  REAL,
        impact_buy_pct  REAL,
        impact_sell_pct REAL,
        round_trip_pct  REAL,
        passes_gate     INTEGER DEFAULT 0,
        fail_reason     TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_gate_at ON impact_gate_log(evaluated_at)")

    # Discovery log (Fix 6: deterministic rule + params logged per run)
    c.execute("""
    CREATE TABLE IF NOT EXISTS discovery_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        discovered_at   TEXT    NOT NULL,
        rule_version    TEXT    NOT NULL,
        source          TEXT    NOT NULL,
        filter_params   TEXT    NOT NULL,   -- JSON
        total_fetched   INTEGER,
        total_passed_gate INTEGER,
        total_rejected_pool_type INTEGER,
        total_rejected_quote     INTEGER,
        total_rejected_age       INTEGER,
        total_rejected_vol       INTEGER,
        total_rejected_liq       INTEGER
    )
    """)

    conn.commit()
    conn.close()
    logger.info("Tables initialized: universe_snapshot, impact_gate_log, discovery_log")

# ── k-invariant tracking ──────────────────────────────────────────────────────
_k_cache: dict[str, float] = {}  # mint -> last k

def check_k_cliff(mint: str, k_new: float) -> tuple[float | None, bool]:
    k_old = _k_cache.get(mint)
    if k_old is None:
        _k_cache[mint] = k_new
        return None, False
    result = k_lp_cliff(k_old, k_new, LP_CLIFF_THRESHOLD)
    _k_cache[mint] = k_new
    return result["k_change_pct"], result["lp_removal_flag"]

# ── Jupiter quote validation ──────────────────────────────────────────────────
_jup_available: bool | None = None

def check_jupiter_available() -> bool:
    global _jup_available
    if _jup_available is not None:
        return _jup_available
    try:
        r = requests.get(
            JUPITER_QUOTE_URL,
            params={
                "inputMint": WSOL_MINT,
                "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                "amount": "1000000",
                "slippageBps": "50",
            },
            timeout=JUPITER_TIMEOUT
        )
        _jup_available = r.status_code == 200
        if _jup_available:
            logger.info("Jupiter quote API available at api.jup.ag/swap/v1/quote")
        else:
            logger.warning(f"Jupiter quote API returned {r.status_code} — CPAMM-only mode")
    except Exception as e:
        logger.warning(f"Jupiter quote API unavailable: {e} — CPAMM-only mode")
        _jup_available = False
    return _jup_available

def get_jupiter_quote(input_mint: str, output_mint: str, sol_in: float) -> dict | None:
    """
    Get Jupiter quote for validation against CPAMM model.
    sol_in is in SOL (not lamports).
    """
    if not check_jupiter_available():
        return None
    try:
        lamports = int(sol_in * 1e9)
        r = requests.get(
            JUPITER_QUOTE_URL,
            params={
                "inputMint": WSOL_MINT,
                "outputMint": output_mint,
                "amount": str(lamports),
                "slippageBps": "300",
                "onlyDirectRoutes": "true",
            },
            timeout=JUPITER_TIMEOUT
        )
        if r.status_code != 200:
            return None
        data = r.json()
        out_amount = int(data.get("outAmount", 0))
        price_impact_pct = float(data.get("priceImpactPct", 0))
        return {
            "out_amount_raw": out_amount,
            "price_impact_pct": price_impact_pct,
        }
    except Exception:
        return None

# ── DexScreener candidate discovery ──────────────────────────────────────────
def fetch_pumpswap_graduated() -> list[dict]:
    """
    Fetch recently graduated pump.fun tokens from DexScreener pumpswap lane.
    Refreshes every PUMPSWAP_REFRESH_SEC; returns cached list between refreshes.
    """
    global _pumpswap_cache, _pumpswap_last_refresh
    now = time.time()
    if now - _pumpswap_last_refresh < PUMPSWAP_REFRESH_SEC and _pumpswap_cache:
        return _pumpswap_cache

    pairs = []
    # DexScreener: search for pumpswap pairs sorted by volume
    # Use the /latest/dex/search endpoint with chain=solana filter
    try:
        r = requests.get(
            f"{DEXSCREENER_BASE}/latest/dex/search",
            params={"q": "pumpswap"},
            timeout=DEXSCREENER_TIMEOUT,
        )
        data = r.json()
        raw = data.get("pairs") or []
        # Filter to pumpswap on Solana
        sol_pump = [
            p for p in raw
            if isinstance(p, dict)
            and p.get("chainId") == "solana"
            and p.get("dexId", "").lower() == "pumpswap"
        ]
        pairs.extend(sol_pump)
    except Exception as e:
        logger.debug(f"PumpSwap search error: {e}")

    # Also try the /token-profiles endpoint for recently boosted tokens
    try:
        r2 = requests.get(
            f"{DEXSCREENER_BASE}/token-profiles/latest/v1",
            timeout=DEXSCREENER_TIMEOUT,
        )
        if r2.status_code == 200:
            profiles = r2.json()
            if isinstance(profiles, list):
                sol_mints = [
                    p.get("tokenAddress") for p in profiles
                    if p.get("chainId") == "solana" and p.get("tokenAddress")
                ][:30]
                if sol_mints:
                    # Batch lookup
                    for i in range(0, len(sol_mints), 10):
                        batch = sol_mints[i:i+10]
                        try:
                            rb = requests.get(
                                f"{DEXSCREENER_BASE}/latest/dex/tokens/{','.join(batch)}",
                                timeout=DEXSCREENER_TIMEOUT,
                            )
                            bp = rb.json().get("pairs") or []
                            sol_pump_b = [
                                p for p in bp
                                if isinstance(p, dict)
                                and p.get("chainId") == "solana"
                                and p.get("dexId", "").lower() == "pumpswap"
                            ]
                            pairs.extend(sol_pump_b)
                        except Exception:
                            pass
    except Exception as e:
        logger.debug(f"PumpSwap token-profiles error: {e}")

    # Apply filters
    now_dt = datetime.now(timezone.utc)
    filtered = []
    seen = set()
    pairs.sort(key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0), reverse=True)
    for pair in pairs:
        if len(filtered) >= PUMPSWAP_MAX_TOKENS:
            break
        mint = pair.get("baseToken", {}).get("address", "")
        if not mint or mint in seen:
            continue
        # Quote filter
        quote_mint = pair.get("quoteToken", {}).get("address", "")
        if quote_mint not in SOL_QUOTE_MINTS:
            continue
        # Age filter
        created_ms = pair.get("pairCreatedAt")
        if created_ms:
            created_dt = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
            age_h = (now_dt - created_dt).total_seconds() / 3600
            if age_h < 1 or age_h > PUMPSWAP_MAX_AGE_DAYS * 24:
                continue
            pair["_age_hours"] = age_h
        else:
            pair["_age_hours"] = None
        # Volume / liquidity filters
        vol_h24 = float(pair.get("volume", {}).get("h24", 0) or 0)
        liq_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        if vol_h24 < PUMPSWAP_MIN_VOL_H24 or liq_usd < PUMPSWAP_MIN_LIQ_USD:
            continue
        seen.add(mint)
        filtered.append(pair)

    _pumpswap_cache = filtered
    _pumpswap_last_refresh = now
    logger.info(f"PumpSwap lane refreshed: {len(filtered)} graduated tokens (raw={len(pairs)})")
    return filtered


def discover_candidates() -> tuple[list[dict], dict]:
    """
    Deterministic candidate discovery per DISCOVERY_RULE.
    Two lanes: (1) established top-20 large-cap, (2) pumpswap graduated.
    Returns (pairs, rejection_counts).
    """
    rejection_counts = {
        "pool_type": 0, "quote": 0, "age": 0, "vol": 0, "liq": 0, "ok": 0
    }
    all_pairs = []

    # Fetch top-volume SOL pairs from DexScreener
    # Deterministic discovery: fetch pairs for known high-volume Solana mints
    # Batched in groups of 30 (DexScreener limit per request)
    KNOWN_SOLANA_MINTS = [
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
        "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",  # POPCAT
        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",   # JUP
        "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",  # FARTCOIN
        "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",  # TRUMP
        "FUAfBo2jgks6gB4Z4LfZkqSZgzNucisEHqnNebaRxM1P",  # MELANIA
        "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",   # ORCA
        "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  # RAY
        "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",  # PYTH
        "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",   # mSOL
        "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",   # bSOL
        "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
        "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # ETH
        "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",   # BOME
        "A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump",  # FWOG
        "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump",  # CHILLGUY
        "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzc8eu",  # MOODENG
        "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump",  # PNUT
        "Cn5Ne1vmR9ctMGY9z5NC71A3NYFvopjXNyxYtfVYpump",  # GOAT
    ]
    search_queries = [
        f"{DEXSCREENER_BASE}/latest/dex/tokens/{','.join(KNOWN_SOLANA_MINTS[:10])}",
        f"{DEXSCREENER_BASE}/latest/dex/tokens/{','.join(KNOWN_SOLANA_MINTS[10:20])}",
    ]

    for url in search_queries:
        try:
            r = requests.get(url, timeout=DEXSCREENER_TIMEOUT)
            data = r.json()
            pairs = data.get("pairs", data.get("data", []))
            if isinstance(pairs, list):
                # Filter to Solana only
                sol_pairs = [p for p in pairs if isinstance(p, dict) and p.get("chainId") == "solana"]
                all_pairs.extend(sol_pairs)
        except Exception as e:
            logger.debug(f"Discovery fetch error ({url}): {e}")

    # Lane 2: PumpSwap graduated tokens (refreshed every 30 min)
    pumpswap_pairs = fetch_pumpswap_graduated()
    all_pairs.extend(pumpswap_pairs)
    logger.debug(f"Universe: {len(all_pairs)} total pairs (established + {len(pumpswap_pairs)} pumpswap)")

    now = datetime.now(timezone.utc)
    filtered = []
    seen_mints = set()

    # Sort by volume descending
    all_pairs.sort(key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0), reverse=True)

    for pair in all_pairs:
        if len(filtered) >= DISCOVERY_RULE["max_tokens"]:
            break

        mint = pair.get("baseToken", {}).get("address", "")
        if not mint or mint in seen_mints:
            continue

        # Fix 3: Pool type gate
        passes, reason = gate_pair(pair)
        if not passes:
            if "pool_type" in reason:
                rejection_counts["pool_type"] += 1
            else:
                rejection_counts["quote"] += 1
            continue

        seen_mints.add(mint)
        # Age filter
        created_at_ms = pair.get("pairCreatedAt")
        if created_at_ms:
            created_dt = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
            age_hours = (now - created_dt).total_seconds() / 3600
            if age_hours < DISCOVERY_RULE["min_age_hours"]:
                rejection_counts["age"] += 1
                continue
            if age_hours > DISCOVERY_RULE["max_age_days"] * 24:
                rejection_counts["age"] += 1
                continue
        else:
            age_hours = None

        # Volume filter
        vol_h24 = float(pair.get("volume", {}).get("h24", 0) or 0)
        if vol_h24 < DISCOVERY_RULE["min_vol_h24"]:
            rejection_counts["vol"] += 1
            continue

        # Liquidity filter
        liq_usd = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        if liq_usd < DISCOVERY_RULE["min_liq_usd"]:
            rejection_counts["liq"] += 1
            continue

        pair["_age_hours"] = age_hours
        filtered.append(pair)
        rejection_counts["ok"] += 1

    return filtered, rejection_counts

# ── Main scan ─────────────────────────────────────────────────────────────────
def scan_and_log():
    snapshot_at = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
    evaluated_at = datetime.now(timezone.utc).isoformat()

    pairs, rejections = discover_candidates()
    total_fetched = sum(rejections.values())

    snap_rows = []
    gate_rows = []
    n_eligible = 0
    n_jup_validated = 0

    for pair in pairs:
        mint = pair.get("baseToken", {}).get("address", "")
        symbol = pair.get("baseToken", {}).get("symbol", "")
        liq = pair.get("liquidity", {})
        vol = pair.get("volume", {})
        txns = pair.get("txns", {}).get("m5", {})

        liq_usd       = float(liq.get("usd", 0) or 0)
        liq_quote_sol = float(liq.get("quote", 0) or 0)
        liq_base      = float(liq.get("base", 0) or 0)
        price_usd     = float(pair.get("priceUsd", 0) or 0)
        price_native  = float(pair.get("priceNative", 0) or 0)
        vol_h24       = float(vol.get("h24", 0) or 0)
        vol_h1        = float(vol.get("h1", 0) or 0)
        vol_m5        = float(vol.get("m5", 0) or 0)

        buys_m5  = int(txns.get("buys", 0) or 0)
        sells_m5 = int(txns.get("sells", 0) or 0)
        total_m5 = buys_m5 + sells_m5

        # Fix 5: buy_count_ratio (not "imbalance")
        buy_count_ratio_m5 = buys_m5 / total_m5 if total_m5 > 0 else None

        # Fix 5: avg_trade_usd and spam flag
        avg_trade_usd_m5 = vol_m5 / total_m5 if total_m5 > 0 else None
        spam_flag = 1 if (avg_trade_usd_m5 is not None and avg_trade_usd_m5 < 1.0) else 0

        # Fix 2: k-invariant for LP cliff detection
        k_invariant = liq_base * liq_quote_sol if liq_base > 0 and liq_quote_sol > 0 else None
        k_change_pct, k_cliff = check_k_cliff(mint, k_invariant or 0)

        # Fix 1: Correct CPAMM impact using x=base, y=quote
        rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_base, liq_quote_sol)
        impact_buy  = rt["buy_slippage"]
        impact_sell = rt["sell_slippage"]
        round_trip  = rt["total_friction"]

        passes_gate = round_trip <= ROUND_TRIP_GATE and not spam_flag
        fail_reason = None
        if round_trip > ROUND_TRIP_GATE:
            fail_reason = f"rt_friction:{round_trip*100:.2f}%"
        elif spam_flag:
            fail_reason = f"spam:avg_trade_usd={avg_trade_usd_m5:.2f}"

        if passes_gate:
            n_eligible += 1

        # Jupiter quote validation (opportunistic, non-blocking)
        jup_out = jup_slip = jup_diff = None
        if passes_gate and check_jupiter_available():
            jq = get_jupiter_quote(WSOL_MINT, mint, TRADE_SIZE_SOL)
            if jq:
                jup_out = jq["out_amount_raw"]
                jup_slip = jq["price_impact_pct"]
                # Compare Jupiter slippage vs CPAMM model
                jup_diff = abs(jup_slip - impact_buy * 100)
                n_jup_validated += 1

        # Fix 2: price_from_reserves validation
        price_native  = float(pair.get("priceNative", 0) or 0)
        price_from_res = (liq_quote_sol / liq_base) if liq_base > 0 else None
        if price_from_res and price_native > 0:
            price_diff_pct = abs(price_from_res - price_native) / price_native * 100
            cpamm_valid = 1 if price_diff_pct < 20 else 0
        else:
            price_diff_pct = None
            cpamm_valid = 0
        
        # Jupiter cross-validation (1 in 10 pairs, rate-limit safe)
        jup_out_sol = None
        jup_slip_pct = None
        jup_diff_pct = None
        if cpamm_valid == 1 and random.random() < 0.1:
            # Sell TRADE_SIZE_SOL worth of tokens, get SOL back
            token_amount = int(TRADE_SIZE_SOL * 1e9 / price_native) if price_native > 0 else 0
            if token_amount > 0:
                jq = get_jupiter_quote(mint, WSOL_MINT, token_amount)
                if jq:
                    jup_out_raw = int(jq.get('outAmount', 0))
                    jup_out_sol = jup_out_raw / 1e9
                    expected_sol = TRADE_SIZE_SOL
                    jup_slip_pct = (expected_sol - jup_out_sol) / expected_sol * 100 if expected_sol > 0 else None
                    # Compare Jupiter route vs CPAMM model
                    cpamm_out = compute_sell_impact(liq_base, liq_quote, token_amount / 1e9, fee_rate=0.0025)
                    if cpamm_out and jup_out_sol:
                        jup_diff_pct = abs(cpamm_out - jup_out_sol) / jup_out_sol * 100

        snap_rows.append((
        snapshot_at, snapshot_at, mint, symbol,
        pair.get("pairAddress", ""), pair.get("dexId", ""),
        pair.get("dexId", ""),  # pool_type = dexId for now
        1 if passes_gate else 0, fail_reason,
        liq_usd, liq_quote_sol, liq_base, k_invariant,
        vol_h24, vol_h1, vol_m5,
        price_usd, price_native,
        buys_m5, sells_m5,
        buy_count_ratio_m5, avg_trade_usd_m5, spam_flag,
        round(impact_buy, 6), round(impact_sell, 6), round(round_trip, 6),
        TRADE_SIZE_SOL, jup_out, jup_slip, jup_diff,
        pair.get("pairCreatedAt"), pair.get("_age_hours"),
        price_from_res, price_diff_pct, cpamm_valid,
        ))

        # Fix 6: compute 0.04 SOL sizing for friction scaling (inline, no compute_impact)
        rt04 = cpamm_round_trip(0.04, liq_base, liq_quote_sol)
        impact_buy_04  = rt04["buy_slippage"]
        impact_sell_04 = rt04["sell_slippage"]
        round_trip_04  = rt04["total_friction"]
        passes_04      = round_trip_04 <= ROUND_TRIP_GATE
        gate_rows.append((
            evaluated_at, mint, TRADE_SIZE_SOL,
            round(impact_buy, 6), round(impact_sell, 6), round(round_trip, 6),
            1 if passes_gate else 0, fail_reason,
            round(impact_buy_04, 6), round(impact_sell_04, 6), round(round_trip_04, 6),
            1 if passes_04 else 0,
        ))

    import json
    conn = get_conn()
    conn.executemany("""
        INSERT INTO universe_snapshot
        (snapshot_at, received_at, mint_address, token_symbol, pair_address, venue, pool_type,
         eligible, gate_reason,
         liq_usd, liq_quote_sol, liq_base, k_invariant,
         vol_h24, vol_h1, vol_m5,
         price_usd, price_native,
         buys_m5, sells_m5,
         buy_count_ratio_m5, avg_trade_usd_m5, spam_flag,
         impact_buy_pct, impact_sell_pct, round_trip_pct,
         jup_quote_in_sol, jup_quote_out_tokens, jup_slippage_pct, jup_vs_cpamm_diff_pct,
         pair_created_at, age_hours,
         price_from_reserves, price_vs_dex_pct_diff, cpamm_valid_flag)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, snap_rows)

    conn.executemany("""
        INSERT INTO impact_gate_log
        (evaluated_at, mint_address, trade_size_sol,
         impact_buy_pct, impact_sell_pct, round_trip_pct, passes_gate, fail_reason,
         impact_buy_pct_04, impact_sell_pct_04, round_trip_pct_04, passes_gate_04)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, gate_rows)

    conn.execute("""
        INSERT INTO discovery_log
        (discovered_at, rule_version, source, filter_params,
         total_fetched, total_passed_gate,
         total_rejected_pool_type, total_rejected_quote,
         total_rejected_age, total_rejected_vol, total_rejected_liq)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        evaluated_at,
        DISCOVERY_RULE["version"],
        DISCOVERY_RULE["source"],
        json.dumps(DISCOVERY_RULE),
        total_fetched, n_eligible,
        rejections["pool_type"], rejections["quote"],
        rejections["age"], rejections["vol"], rejections["liq"],
    ))

    conn.commit()
    conn.close()

    # Prove-It 2: Coverage audit log
    try:
        import sqlite3 as _sq
        from config.config import DB_PATH as _dbp
        _c2 = _sq.connect(_dbp)
        _c2.execute(
            "INSERT INTO coverage_audit (scan_at, unique_mints_seen, unique_pairs_seen, eligible_count, scan_method, discovery_source) VALUES (?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(), total_fetched, total_fetched, n_eligible,
             DISCOVERY_RULE.get("scan_method","dexscreener"), "WATCHLIST_LANE_NOT_FULL_UNIVERSE")
        )
        _c2.commit(); _c2.close()
    except Exception as _e:
        pass
    logger.info(
        f"Scan complete: {total_fetched} fetched | {n_eligible} eligible | "
        f"rejected: pool_type={rejections['pool_type']} quote={rejections['quote']} "
        f"age={rejections['age']} vol={rejections['vol']} liq={rejections['liq']} | "
        f"jup_validated={n_jup_validated}"
    )

def run():
    logger.info("=" * 65)
    logger.info("Existing Tokens Universe Scanner v2 starting (P0+P1)")
    logger.info(f"  Discovery rule: {DISCOVERY_RULE['version']}")
    logger.info(f"  Impact gate: RT ≤ {ROUND_TRIP_GATE*100:.0f}% at {TRADE_SIZE_SOL} SOL")
    logger.info(f"  Pool types: {sorted(CPMM_VALID_DEX_IDS)}")
    logger.info(f"  Quote filter: SOL/wSOL only")
    logger.info("=" * 65)

    init_tables()
    check_jupiter_available()  # Log availability at startup

    while True:
        loop_start = time.time()
        try:
            scan_and_log()
        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
        elapsed = time.time() - loop_start
        time.sleep(max(5, SCAN_INTERVAL_SEC - elapsed))

if __name__ == "__main__":
    run()
