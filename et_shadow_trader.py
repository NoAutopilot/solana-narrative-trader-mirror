#!/usr/bin/env python3
"""
Existing Tokens Shadow-Live Paper Harness — P3 + P4  (v2, patched)
====================================================================
Patches applied:
  Fix 1: Correct CPAMM x*y=k math (imported from cpamm_math)
  Fix 2: LP cliff exit via k-invariant drop
  Fix 5: Uses buy_count_ratio (renamed column)
"""
import os
import sys
import time
import uuid
import logging
import sqlite3
import random
import requests

    # Prove-It 3: Fee sensitivity across scenarios
    # fee_low = 0.25% (Raydium v4 maker rebate scenario)
    # fee_med = 0.60% (standard Raydium taker)
    # fee_p90 = 1.00% (high-fee scenario, thin pools)
    FEE_SCENARIOS = {'fee_low': 0.0025, 'fee_med': 0.006, 'fee_p90': 0.010}
    
    def compute_pnl_with_fee(entry_price, exit_price, fee_rate):
        """Compute PnL including buy + sell fee at given rate."""
        gross = (exit_price / entry_price) - 1.0
        total_fee = fee_rate * 2  # buy + sell
        return gross - total_fee
from datetime import datetime, timezone

sys.path.insert(0, "/root/solana_trader")
try:
    from cpamm_math import cpamm_round_trip, k_lp_cliff
except ImportError:
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

from config.config import DB_PATH, LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("et_shadow_trader")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s [shadow_trader] %(levelname)s: %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "et_shadow_trader.log"))
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

DEXSCREENER_BASE    = "https://api.dexscreener.com"
DEXSCREENER_TIMEOUT = 12
POLL_INTERVAL_SEC   = 15
TRADE_SIZE_SOL      = 0.02
FIXED_FEE_PCT       = 0.006
ROUND_TRIP_THRESHOLD = 0.03
LP_CLIFF_THRESHOLD   = 0.05

# Strategy params (frozen)
STRATEGIES = {
    "momentum": {
        "entry_r_m5_min":        2.0,
        "entry_buy_count_ratio_min": 0.60,   # Fix 5: renamed
        "entry_vol_accel_min":   1.5,
        "take_profit_pct":       8.0,
        "stop_loss_pct":        -4.0,
        "max_hold_minutes":      30,
        "liq_cliff_exit":        True,
    },
    "pullback": {
        "entry_r_h1_min":        3.0,
        "entry_r_m5_max":       -0.5,
        "entry_buy_count_ratio_min": 0.55,   # Fix 5: renamed
        "take_profit_pct":       5.0,
        "stop_loss_pct":        -3.0,
        "max_hold_minutes":      20,
        "liq_cliff_exit":        True,
    },
    "baseline": {
        "take_profit_pct":       8.0,
        "stop_loss_pct":        -4.0,
        "max_hold_minutes":      30,
        "liq_cliff_exit":        True,
        "random_entry_rate":     0.05,
    },
}

LATENCY_PENALTY_MEAN_MS = 850
LATENCY_PENALTY_STD_MS  = 400

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_tables():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS shadow_trades (
        trade_id                TEXT    PRIMARY KEY,
        strategy                TEXT    NOT NULL,
        mint_address            TEXT    NOT NULL,
        token_symbol            TEXT,
        pair_address            TEXT,
        entered_at              TEXT    NOT NULL,
        entry_price_usd         REAL,
        entry_price_native      REAL,
        entry_liq_usd           REAL,
        entry_liq_quote_sol     REAL,
        entry_liq_base          REAL,
        entry_k_invariant       REAL,
        entry_impact_buy_pct    REAL,
        entry_impact_sell_pct   REAL,
        entry_round_trip_pct    REAL,
        latency_penalty_ms      REAL,
        entry_r_m5              REAL,
        entry_r_h1              REAL,
        entry_buy_count_ratio   REAL,   -- Fix 5: renamed
        entry_vol_accel         REAL,
        exited_at               TEXT,
        exit_price_usd          REAL,
        exit_price_native       REAL,
        exit_liq_usd            REAL,
        exit_liq_base           REAL,
        exit_k_invariant        REAL,
        exit_impact_sell_pct    REAL,
        exit_round_trip_pct     REAL,
        exit_reason             TEXT,
        gross_pnl_pct           REAL,
        shadow_pnl_pct          REAL,
        shadow_pnl_sol          REAL,
        status                  TEXT    DEFAULT 'open'
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_shadow_strategy ON shadow_trades(strategy, entered_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_shadow_status ON shadow_trades(status)")
    conn.commit()
    conn.close()
    logger.info("Table initialized: shadow_trades (v2)")

def get_latest_microstructure() -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.*
        FROM microstructure_log m
        INNER JOIN (
            SELECT mint_address, MAX(logged_at) as max_at
            FROM microstructure_log
            WHERE logged_at >= datetime('now', '-2 minutes')
              AND spam_flag = 0
            GROUP BY mint_address
        ) latest ON m.mint_address = latest.mint_address AND m.logged_at = latest.max_at
        INNER JOIN universe_snapshot u ON m.mint_address = u.mint_address
            AND u.snapshot_at = (SELECT MAX(snapshot_at) FROM universe_snapshot)
            AND u.eligible = 1 AND u.cpamm_valid_flag = 1
        ORDER BY m.vol_h24 DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_open_trades() -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM shadow_trades WHERE status = 'open'")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def fetch_current_price(mint: str) -> dict | None:
    try:
        r = requests.get(
            f"{DEXSCREENER_BASE}/latest/dex/tokens/{mint}",
            timeout=DEXSCREENER_TIMEOUT
        )
        pairs = r.json().get("pairs", [])
        if not pairs:
            return None
        best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        liq = best.get("liquidity", {})
        liq_base = float(liq.get("base", 0) or 0)
        liq_quote = float(liq.get("quote", 0) or 0)
        return {
            "price_usd":    float(best.get("priceUsd", 0) or 0),
            "price_native": float(best.get("priceNative", 0) or 0),
            "liq_usd":      float(liq.get("usd", 0) or 0),
            "liq_quote_sol": liq_quote,
            "liq_base":     liq_base,
            "k_invariant":  liq_base * liq_quote if liq_base > 0 and liq_quote > 0 else None,
        }
    except Exception:
        return None

def check_already_open(mint: str, strategy: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM shadow_trades
        WHERE mint_address = ? AND strategy = ? AND status = 'open'
    """, (mint, strategy))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def should_enter_momentum(row: dict) -> bool:
    p = STRATEGIES["momentum"]
    return (
        (row.get("r_m5") or 0)                  >= p["entry_r_m5_min"] and
        (row.get("buy_count_ratio_m5") or 0)     >= p["entry_buy_count_ratio_min"] and
        (row.get("vol_accel_m5_vs_h1") or 0)     >= p["entry_vol_accel_min"]
    )

def should_enter_pullback(row: dict) -> bool:
    p = STRATEGIES["pullback"]
    return (
        (row.get("r_h1") or 0)               >= p["entry_r_h1_min"] and
        (row.get("r_m5") or 0)               <= p["entry_r_m5_max"] and
        (row.get("buy_count_ratio_m5") or 0) >= p["entry_buy_count_ratio_min"]
    )

def open_trade(strategy: str, row: dict):
    mint = row["mint_address"]
    if check_already_open(mint, strategy):
        return

    liq_b = row.get("liq_base") or 0
    liq_q = row.get("liq_quote_sol") or 0
    rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_b, liq_q)
    if rt["total_friction"] > ROUND_TRIP_THRESHOLD:
        return

    k = liq_b * liq_q if liq_b > 0 and liq_q > 0 else None
    latency_ms = max(100, random.gauss(LATENCY_PENALTY_MEAN_MS, LATENCY_PENALTY_STD_MS))
    now = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    conn.execute("""
        INSERT INTO shadow_trades
        (trade_id, strategy, mint_address, token_symbol, pair_address,
         entered_at, entry_price_usd, entry_price_native,
         entry_liq_usd, entry_liq_quote_sol, entry_liq_base, entry_k_invariant,
         entry_impact_buy_pct, entry_impact_sell_pct, entry_round_trip_pct,
         latency_penalty_ms,
         entry_r_m5, entry_r_h1, entry_buy_count_ratio, entry_vol_accel,
         status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), strategy, mint,
        row.get("token_symbol"), row.get("pair_address"),
        now,
        row.get("price_usd"), row.get("price_native"),
        row.get("liq_usd"), liq_q, liq_b, k,
        round(rt["buy_slippage"], 6), round(rt["sell_slippage"], 6), round(rt["total_friction"], 6),
        round(latency_ms, 1),
        row.get("r_m5"), row.get("r_h1"),
        row.get("buy_count_ratio_m5"), row.get("vol_accel_m5_vs_h1"),
        "open"
    ))
    conn.commit()
    conn.close()
    logger.info(f"OPEN {strategy} {row.get('token_symbol','?')} ({mint[:8]}...) "
                f"rt={rt['total_friction']*100:.2f}%")

def close_trade(trade: dict, current: dict, reason: str):
    entry_price = trade["entry_price_usd"]
    exit_price  = current["price_usd"]
    if entry_price <= 0 or exit_price <= 0:
        return

    liq_b = current["liq_base"]
    liq_q = current["liq_quote_sol"]
    rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_b, liq_q)

    gross_pnl_pct  = (exit_price / entry_price) - 1.0
    shadow_pnl_pct = gross_pnl_pct - rt["total_friction"]
    shadow_pnl_sol = shadow_pnl_pct * TRADE_SIZE_SOL
    # Fix 4: fee scenarios (impact is fixed; only fee component varies)
    impact_only = rt["buy_slippage"] + rt["sell_slippage"]
    pnl_fee025  = gross_pnl_pct - (impact_only + 0.0025)
    pnl_fee060  = gross_pnl_pct - (impact_only + 0.006)
    pnl_fee100  = gross_pnl_pct - (impact_only + 0.01)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute("""
        UPDATE shadow_trades SET
            exited_at           = ?,
            exit_price_usd      = ?,
            exit_price_native   = ?,
            exit_liq_usd        = ?,
            exit_liq_base       = ?,
            exit_k_invariant    = ?,
            exit_impact_sell_pct = ?,
            exit_round_trip_pct = ?,
            exit_reason         = ?,
            gross_pnl_pct       = ?,
            shadow_pnl_pct      = ?,
            shadow_pnl_sol      = ?,
            shadow_pnl_pct_fee025 = ?,
            shadow_pnl_pct_fee060 = ?,
            shadow_pnl_pct_fee100 = ?,
            status              = 'closed'
        WHERE trade_id = ?
    """, (
        now,
        exit_price, current["price_native"],
        current["liq_usd"], liq_b, current.get("k_invariant"),
        round(rt["sell_slippage"], 6), round(rt["total_friction"], 6),
        reason,
        round(gross_pnl_pct, 6), round(shadow_pnl_pct, 6), round(shadow_pnl_sol, 6),
        round(pnl_fee025, 6), round(pnl_fee060, 6), round(pnl_fee100, 6),
        trade["trade_id"]
    ))
    conn.commit()
    conn.close()
    logger.info(f"CLOSE {trade['strategy']} {trade.get('token_symbol','?')} "
                f"reason={reason} pnl={shadow_pnl_pct*100:+.2f}%")

def check_exits(open_trades: list[dict]):
    for trade in open_trades:
        strategy = trade["strategy"]
        params = STRATEGIES.get(strategy, STRATEGIES["momentum"])
        mint = trade["mint_address"]

        current = fetch_current_price(mint)
        if not current:
            continue

        entry_price = trade["entry_price_usd"]
        if entry_price <= 0:
            continue

        gross_pnl_pct = (current["price_usd"] / entry_price - 1.0) * 100

        entered_at = datetime.fromisoformat(trade["entered_at"])
        hold_min = (datetime.now(timezone.utc) - entered_at).total_seconds() / 60
        if hold_min >= params["max_hold_minutes"]:
            close_trade(trade, current, "timeout")
            continue
        if gross_pnl_pct >= params["take_profit_pct"]:
            close_trade(trade, current, "tp")
            continue
        if gross_pnl_pct <= params["stop_loss_pct"]:
            close_trade(trade, current, "sl")
            continue

        # Fix 2: LP cliff exit via k-invariant
        if params.get("liq_cliff_exit"):
            entry_k = trade.get("entry_k_invariant")
            exit_k  = current.get("k_invariant")
            if entry_k and exit_k:
                cliff = k_lp_cliff(entry_k, exit_k, LP_CLIFF_THRESHOLD)
                if cliff["lp_removal_flag"]:
                    close_trade(trade, current, "lp_removal")
                    continue

        time.sleep(0.1)

def run():
    logger.info("=" * 65)
    logger.info("Shadow-Live Paper Harness v2 starting (P3 + P4)")
    logger.info(f"  Strategies: {list(STRATEGIES.keys())}")
    logger.info(f"  Trade size: {TRADE_SIZE_SOL} SOL")
    logger.info(f"  LP cliff threshold: {LP_CLIFF_THRESHOLD*100:.0f}% k-drop")
    logger.info("=" * 65)
    init_tables()

    for _ in range(20):
        rows = get_latest_microstructure()
        if rows:
            logger.info(f"Microstructure ready: {len(rows)} tokens")
            break
        logger.info("Waiting for microstructure data...")
        time.sleep(15)

    while True:
        loop_start = time.time()
        try:
            open_trades = get_open_trades()
            if open_trades:
                check_exits(open_trades)

            rows = get_latest_microstructure()
            for row in rows:
                mint = row.get("mint_address")
                if not mint:
                    continue
                if should_enter_momentum(row):
                    open_trade("momentum", row)
                if should_enter_pullback(row):
                    open_trade("pullback", row)
                if random.random() < STRATEGIES["baseline"]["random_entry_rate"]:
                    open_trade("baseline", row)
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
        elapsed = time.time() - loop_start
        time.sleep(max(2, POLL_INTERVAL_SEC - elapsed))

if __name__ == "__main__":
    run()
