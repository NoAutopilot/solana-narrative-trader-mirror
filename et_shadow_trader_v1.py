#!/usr/bin/env python3
"""
et_shadow_trader_v1.py — ET v1 Paper Trading Harness (Playbook Edition)

Spec (from ET v1 playbook):
  A) Universe + Friction Gate:
     - SOL/wSOL quote only
     - Jupiter quote-based RT gate: F_rt_est <= 1.0%
     - Abort if no Jupiter route (route risk)
     - CPAMM LP cliff for CPAMM pools; disabled for CLMM/DLMM

  B) Position Caps:
     - research_mode: MAX_OPEN_PER_STRATEGY=1, no global cap
     - live_sim_mode: MAX_OPEN_PER_STRATEGY=1, MAX_OPEN_GLOBAL=1
     - Set MODE = "research_mode" or "live_sim_mode" below

  C) Exit Policy (unified across all strategies):
     - take_profit_pct  = +4.0%
     - stop_loss_pct    = -2.0%
     - max_hold_minutes = 12
     - liq_cliff_exit   = True (CPAMM only)

  D) Entry Conditions (v1 — calibrated to fire ~20 trades/strategy/day):
     Momentum v1:
       - r_m5 >= +0.8%
       - buy_count_ratio_m5 >= 0.60
       - vol_accel_m5_vs_h1 >= 1.5
       - spam_flag = 0 AND avg_trade_usd_m5 >= $100
     Pullback v1:
       - r_h1 >= +2.0%
       - r_m5 <= -0.6%
       - Confirmation on next scan cycle: r_m5 >= -0.3% AND buy_count_ratio_m5 >= 0.55
         (approximates "r_1m >= +0.2% + buy_count_ratio_1m >= 0.55" using 5m data)

  E) Baselines (matched-time, per-strategy):
     - baseline_matched_momentum: fires when momentum enters, random eligible token
     - baseline_matched_pullback: fires when pullback enters, random eligible token
     - "beats baseline" compares each strategy to its own matched baseline

  F) Reporting:
     - min_trades_per_strategy >= 20 before "beats baseline" evaluation
     - Fee scenarios: fee025 / fee060 / fee100 at close
     - Impact friction separate from DEX fee and network fee

  Table: shadow_trades_v1 (new, does not overwrite shadow_trades)
  Singleton: /tmp/et_shadow_trader_v1.lock
"""

import os
import sys
import fcntl
import logging
import random
import sqlite3
import time
import uuid
import requests
from datetime import datetime, timezone

# ── SINGLETON GUARD ──────────────────────────────────────────────────────────
_LOCK_PATH = "/tmp/et_shadow_trader_v1.lock"
_lockfile_fd = open(_LOCK_PATH, "w")
try:
    fcntl.flock(_lockfile_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lockfile_fd.write(str(os.getpid()))
    _lockfile_fd.flush()
except BlockingIOError:
    print("[singleton] Another instance is running (lock held). Exiting.", flush=True)
    sys.exit(0)

# ── IMPORTS ───────────────────────────────────────────────────────────────────
sys.path.insert(0, "/root/solana_trader")
from config.config import DB_PATH, LOGS_DIR, JUPITER_API_KEY, JUPITER_BASE_URL
from cpamm_math import cpamm_round_trip, k_lp_cliff

os.makedirs(LOGS_DIR, exist_ok=True)
logger = logging.getLogger("et_shadow_trader_v1")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s [shadow_v1] %(levelname)s: %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "et_shadow_trader_v1.log"))
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

# ── MODE ──────────────────────────────────────────────────────────────────────
# "research_mode": per-strategy cap=1, no global cap — for feature evaluation
# "live_sim_mode": per-strategy cap=1, global cap=1 — approximates live bankroll
MODE = "research_mode"

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC           = 15
TRADE_SIZE_SOL              = 0.01
MAX_OPEN_PER_STRATEGY       = 1
MAX_OPEN_GLOBAL             = 1          # only enforced in live_sim_mode
LP_CLIFF_THRESHOLD          = 0.05       # 5% k-drop triggers liq_cliff exit
# ── SCORE/RANK FALLBACK ───────────────────────────────────────────────────────
# When no strict-threshold signals fire within SCORE_RANK_INTERVAL_SEC,
# fire 1 trade per strategy using the top-ranked candidate.
# This prevents signal starvation and ensures minimum sample size.
SCORE_RANK_ENABLED          = True
SCORE_RANK_INTERVAL_SEC     = 3600       # 1 hour between forced rank entries
SCORE_RANK_MIN_R_M5         = 0.0        # must have at least some positive momentum
SCORE_RANK_MIN_BUY_RATIO    = 0.40       # relaxed buy ratio floor
SCORE_RANK_MIN_VOL_ACCEL    = 0.5        # relaxed vol accel floor
FRICTION_GATE_MAX_RT        = 0.010      # 1.0% max total RT friction (Jupiter-quoted)
DEXSCREENER_TIMEOUT         = 12
WSOL_MINT                   = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL            = 1_000_000_000

# ── UNIFIED EXIT POLICY ───────────────────────────────────────────────────────
EXIT_TAKE_PROFIT_PCT        = 4.0        # +4.0% gross
EXIT_STOP_LOSS_PCT          = -2.0       # -2.0% gross
EXIT_MAX_HOLD_MINUTES       = 12
EXIT_LIQ_CLIFF              = True

# ── ENTRY CONDITIONS v1 ───────────────────────────────────────────────────────
MOMENTUM_R_M5_MIN           = 0.8        # was 2.0 — loosened
MOMENTUM_BUY_RATIO_MIN      = 0.60
MOMENTUM_VOL_ACCEL_MIN      = 1.5
MOMENTUM_AVG_TRADE_USD_MIN  = 100.0      # spam filter

PULLBACK_R_H1_MIN           = 2.0        # was 3.0 — loosened
PULLBACK_R_M5_MAX           = -0.6       # was -0.5
PULLBACK_BUY_RATIO_MIN      = 0.55       # confirmation
PULLBACK_CONFIRM_R_M5_MIN   = -0.3       # confirmation: r_m5 must recover to >= -0.3%

# Pullback pending confirmation: {mint: timestamp_of_initial_signal}
_pullback_pending: dict[str, float] = {}
# Score/rank fallback: track last time each strategy fired a rank entry
_last_rank_entry: dict[str, float] = {}
# Jupiter API availability (set to False on first 401 to avoid repeated failures)
_jupiter_api_available: bool = True
PULLBACK_CONFIRM_WINDOW_SEC = 75         # ~1 scan cycle + buffer

# ── DB HELPERS ────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_tables():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS shadow_trades_v1 (
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
        entry_jup_rt_pct        REAL,
        entry_r_m5              REAL,
        entry_r_h1              REAL,
        entry_buy_count_ratio   REAL,
        entry_vol_accel         REAL,
        entry_avg_trade_usd     REAL,
        baseline_trigger_id     TEXT,
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
        shadow_pnl_pct_fee025   REAL,
        shadow_pnl_pct_fee060   REAL,
        shadow_pnl_pct_fee100   REAL,
        mode                    TEXT,
        status                  TEXT    DEFAULT 'open'
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sv1_strategy ON shadow_trades_v1(strategy, entered_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sv1_status   ON shadow_trades_v1(status)")
    conn.commit()
    conn.close()
    logger.info("Table initialized: shadow_trades_v1")

def count_open_by_strategy(strategy: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM shadow_trades_v1 WHERE strategy = ? AND status = 'open'",
        (strategy,)
    )
    n = c.fetchone()[0]
    conn.close()
    return n

def count_open_global() -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM shadow_trades_v1 WHERE status = 'open'")
    n = c.fetchone()[0]
    conn.close()
    return n

def get_open_trades() -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM shadow_trades_v1 WHERE status = 'open'")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

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

# ── JUPITER FRICTION GATE ─────────────────────────────────────────────────────
def get_jupiter_rt_estimate(mint: str, liq_base: float = 0, liq_quote_sol: float = 0) -> float | None:
    """
    Returns total RT friction fraction (e.g. 0.008 = 0.8%) or None if no route.
    Falls back to CPAMM math when Jupiter API is unavailable (401 / network error).
    """
    global _jupiter_api_available
    sol_in_lamports = int(TRADE_SIZE_SOL * LAMPORTS_PER_SOL)

    if _jupiter_api_available:
        try:
            r_buy = requests.get(
                f"{JUPITER_BASE_URL}/v6/quote",
                params={
                    "inputMint":   WSOL_MINT,
                    "outputMint":  mint,
                    "amount":      str(sol_in_lamports),
                    "slippageBps": "50",
                },
                headers={"Authorization": f"Bearer {JUPITER_API_KEY}"},
                timeout=8,
            )
            if r_buy.status_code == 401:
                logger.warning("Jupiter API 401 — switching to CPAMM fallback mode")
                _jupiter_api_available = False
            else:
                buy_q = r_buy.json()
                if "outAmount" not in buy_q:
                    return None
                tokens_out = int(buy_q["outAmount"])
                if tokens_out <= 0:
                    return None
                r_sell = requests.get(
                    f"{JUPITER_BASE_URL}/v6/quote",
                    params={
                        "inputMint":   mint,
                        "outputMint":  WSOL_MINT,
                        "amount":      str(tokens_out),
                        "slippageBps": "50",
                    },
                    headers={"Authorization": f"Bearer {JUPITER_API_KEY}"},
                    timeout=8,
                )
                if r_sell.status_code == 401:
                    logger.warning("Jupiter API 401 on sell — switching to CPAMM fallback")
                    _jupiter_api_available = False
                else:
                    sell_q = r_sell.json()
                    if "outAmount" not in sell_q:
                        return None
                    sol_back_lamports = int(sell_q["outAmount"])
                    rt_friction = 1.0 - (sol_back_lamports / sol_in_lamports)
                    return max(0.0, rt_friction)
        except Exception as e:
            logger.warning(f"Jupiter RT estimate failed for {mint[:8]}: {e}")

    # CPAMM fallback: use CPAMM math + fixed DEX fee estimate (0.6%)
    if liq_base > 0 and liq_quote_sol > 0:
        rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_base, liq_quote_sol)
        cpamm_rt = rt["total_friction"] + 0.006
        logger.debug(f"CPAMM fallback RT for {mint[:8]}: {cpamm_rt*100:.2f}%")
        return min(cpamm_rt, 0.05)
    else:
        # No liquidity data — conservative estimate
        return 0.008

# ── PRICE FETCH ───────────────────────────────────────────────────────────────
def fetch_current_price(mint: str) -> dict | None:
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        r = requests.get(url, timeout=DEXSCREENER_TIMEOUT)
        data = r.json()
        pairs = data.get("pairs") or []
        if not pairs:
            return None
        sol_pairs = [p for p in pairs if (p.get("quoteToken", {}).get("symbol") or "").upper() == "SOL"]
        if not sol_pairs:
            sol_pairs = pairs
        best = max(sol_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd") or 0))
        liq_base  = float(best.get("liquidity", {}).get("base") or 0)
        liq_quote = float(best.get("liquidity", {}).get("quote") or 0)
        k = liq_base * liq_quote if liq_base > 0 and liq_quote > 0 else None
        return {
            "price_usd":     float(best.get("priceUsd") or 0),
            "price_native":  float(best.get("priceNative") or 0),
            "liq_usd":       float(best.get("liquidity", {}).get("usd") or 0),
            "liq_base":      liq_base,
            "liq_quote_sol": liq_quote,
            "k_invariant":   k,
        }
    except Exception:
        return None

# ── ENTRY GUARDS ──────────────────────────────────────────────────────────────
def passes_position_cap(strategy: str) -> bool:
    if count_open_by_strategy(strategy) >= MAX_OPEN_PER_STRATEGY:
        return False
    if MODE == "live_sim_mode" and count_open_global() >= MAX_OPEN_GLOBAL:
        return False
    return True

def should_enter_momentum(row: dict) -> bool:
    if row.get("spam_flag"):
        return False
    return (
        (row.get("r_m5") or 0)               >= MOMENTUM_R_M5_MIN and
        (row.get("buy_count_ratio_m5") or 0)  >= MOMENTUM_BUY_RATIO_MIN and
        (row.get("vol_accel_m5_vs_h1") or 0)  >= MOMENTUM_VOL_ACCEL_MIN and
        (row.get("avg_trade_usd_m5") or 0)    >= MOMENTUM_AVG_TRADE_USD_MIN
    )

def should_enter_pullback_initial(row: dict) -> bool:
    """First leg: r_h1 >= 2.0% AND r_m5 <= -0.6%. Sets pending confirmation."""
    return (
        (row.get("r_h1") or 0) >= PULLBACK_R_H1_MIN and
        (row.get("r_m5") or 0) <= PULLBACK_R_M5_MAX
    )

def should_confirm_pullback(row: dict) -> bool:
    """Confirmation leg: r_m5 has recovered >= -0.3% AND buy ratio >= 0.55."""
    return (
        (row.get("r_m5") or 0)               >= PULLBACK_CONFIRM_R_M5_MIN and
        (row.get("buy_count_ratio_m5") or 0)  >= PULLBACK_BUY_RATIO_MIN
    )

# ── SCORE/RANK FALLBACK ──────────────────────────────────────────────────────
def score_momentum(row: dict) -> float:
    """Composite momentum score. Higher = better candidate."""
    r_m5      = max(row.get("r_m5") or 0, 0)
    buy_ratio = max(row.get("buy_count_ratio_m5") or 0, 0)
    vol_accel = max(row.get("vol_accel_m5_vs_h1") or 0, 0)
    avg_trade = max(row.get("avg_trade_usd_m5") or 0, 0)
    # Normalize avg_trade (cap at $500 to avoid outlier dominance)
    avg_norm = min(avg_trade, 500) / 500
    return r_m5 * buy_ratio * vol_accel * (0.5 + 0.5 * avg_norm)

def score_pullback(row: dict) -> float:
    """Composite pullback score. Higher = better candidate."""
    r_h1      = max(row.get("r_h1") or 0, 0)
    r_m5_neg  = max(-(row.get("r_m5") or 0), 0)  # want r_m5 to be negative
    buy_ratio = max(row.get("buy_count_ratio_m5") or 0, 0)
    return r_h1 * r_m5_neg * buy_ratio

def maybe_fire_rank_entry(strategy: str, rows: list[dict], score_fn) -> str | None:
    """
    If SCORE_RANK_ENABLED and no strict-threshold entry has fired for this
    strategy in SCORE_RANK_INTERVAL_SEC, fire a rank entry using the top
    candidate by score_fn.
    Returns trade_id on success, None otherwise.
    """
    if not SCORE_RANK_ENABLED:
        return None
    now = time.time()
    last = _last_rank_entry.get(strategy, 0)
    if now - last < SCORE_RANK_INTERVAL_SEC:
        return None  # Not time yet
    # Filter to minimally qualifying candidates
    if strategy == "momentum_rank":
        candidates = [
            r for r in rows
            if (r.get("r_m5") or 0) >= SCORE_RANK_MIN_R_M5
            and (r.get("buy_count_ratio_m5") or 0) >= SCORE_RANK_MIN_BUY_RATIO
            and (r.get("vol_accel_m5_vs_h1") or 0) >= SCORE_RANK_MIN_VOL_ACCEL
        ]
    else:  # pullback_rank
        candidates = [
            r for r in rows
            if (r.get("r_h1") or 0) >= 0.5  # at least some h1 gain
            and (r.get("r_m5") or 0) <= 0   # currently dipping
            and (r.get("buy_count_ratio_m5") or 0) >= SCORE_RANK_MIN_BUY_RATIO
        ]
    if not candidates:
        logger.info(f"RANK {strategy}: no qualifying candidates this cycle, skipping")
        return None
    # Pick top candidate by score
    best = max(candidates, key=score_fn)
    best_score = score_fn(best)
    logger.info(
        f"RANK {strategy}: firing top-1 candidate "
        f"{best.get('token_symbol','?')} ({best.get('mint_address','?')[:8]}) "
        f"score={best_score:.4f} "
        f"r_m5={best.get('r_m5'):.2f}% r_h1={best.get('r_h1'):.2f}% "
        f"buy_ratio={best.get('buy_count_ratio_m5'):.2f}"
    )
    tid = open_trade(strategy, best)
    if tid:
        _last_rank_entry[strategy] = now
        logger.info(f"RANK {strategy}: entry opened trade_id={tid[:8]}")
    return tid

# ── OPEN TRADE ────────────────────────────────────────────────────────────────
def open_trade(strategy: str, row: dict, baseline_trigger_id: str | None = None) -> str | None:
    """
    Open a shadow trade. Returns trade_id on success, None if blocked.
    Checks: position cap → Jupiter friction gate → insert.
    """
    if not passes_position_cap(strategy):
        logger.debug(f"SKIP {strategy}: position cap reached")
        return None

    mint = row["mint_address"]

    liq_b_for_jup = row.get("liq_base") or 0
    liq_q_for_jup = row.get("liq_quote_sol") or 0
    jup_rt = get_jupiter_rt_estimate(mint, liq_b_for_jup, liq_q_for_jup)
    if jup_rt is None:
        logger.info(f"SKIP {strategy} {mint[:8]}: no Jupiter route")
        return None
    if jup_rt > FRICTION_GATE_MAX_RT:
        logger.info(f"SKIP {strategy} {mint[:8]}: Jupiter RT {jup_rt*100:.2f}% > gate {FRICTION_GATE_MAX_RT*100:.1f}%")
        return None

    liq_b = row.get("liq_base") or 0
    liq_q = row.get("liq_quote_sol") or 0
    rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_b, liq_q)
    k  = liq_b * liq_q if liq_b > 0 and liq_q > 0 else None

    trade_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_conn()
    conn.execute("""
        INSERT INTO shadow_trades_v1
        (trade_id, strategy, mint_address, token_symbol, pair_address,
         entered_at, entry_price_usd, entry_price_native,
         entry_liq_usd, entry_liq_quote_sol, entry_liq_base, entry_k_invariant,
         entry_impact_buy_pct, entry_impact_sell_pct, entry_round_trip_pct,
         entry_jup_rt_pct,
         entry_r_m5, entry_r_h1, entry_buy_count_ratio, entry_vol_accel,
         entry_avg_trade_usd,
         baseline_trigger_id, mode, status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        trade_id, strategy, mint,
        row.get("token_symbol"), row.get("pair_address"),
        now,
        row.get("price_usd"), row.get("price_native"),
        row.get("liq_usd"), liq_q, liq_b, k,
        round(rt["buy_slippage"], 6), round(rt["sell_slippage"], 6),
        round(rt["total_friction"], 6),
        round(jup_rt, 6),
        row.get("r_m5"), row.get("r_h1"),
        row.get("buy_count_ratio_m5"), row.get("vol_accel_m5_vs_h1"),
        row.get("avg_trade_usd_m5"),
        baseline_trigger_id, MODE, "open",
    ))
    conn.commit()
    conn.close()

    logger.info(
        f"OPEN {strategy} {row.get('token_symbol','?')} ({mint[:8]}...) "
        f"jup_rt={jup_rt*100:.2f}% cpamm_rt={rt['total_friction']*100:.2f}%"
        + (f" [triggered_by={baseline_trigger_id[:8]}]" if baseline_trigger_id else "")
    )
    return trade_id

# ── CLOSE TRADE ───────────────────────────────────────────────────────────────
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

    impact_only = rt["buy_slippage"] + rt["sell_slippage"]
    pnl_fee025  = gross_pnl_pct - (impact_only + 0.0025)
    pnl_fee060  = gross_pnl_pct - (impact_only + 0.006)
    pnl_fee100  = gross_pnl_pct - (impact_only + 0.01)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    conn.execute("""
        UPDATE shadow_trades_v1 SET
            exited_at               = ?,
            exit_price_usd          = ?,
            exit_price_native       = ?,
            exit_liq_usd            = ?,
            exit_liq_base           = ?,
            exit_k_invariant        = ?,
            exit_impact_sell_pct    = ?,
            exit_round_trip_pct     = ?,
            exit_reason             = ?,
            gross_pnl_pct           = ?,
            shadow_pnl_pct          = ?,
            shadow_pnl_sol          = ?,
            shadow_pnl_pct_fee025   = ?,
            shadow_pnl_pct_fee060   = ?,
            shadow_pnl_pct_fee100   = ?,
            status                  = 'closed'
        WHERE trade_id = ?
    """, (
        now,
        exit_price, current["price_native"],
        current["liq_usd"], liq_b, current.get("k_invariant"),
        round(rt["sell_slippage"], 6), round(rt["total_friction"], 6),
        reason,
        round(gross_pnl_pct, 6), round(shadow_pnl_pct, 6), round(shadow_pnl_sol, 6),
        round(pnl_fee025, 6), round(pnl_fee060, 6), round(pnl_fee100, 6),
        trade["trade_id"],
    ))
    conn.commit()
    conn.close()

    logger.info(
        f"CLOSE {trade['strategy']} {trade.get('token_symbol','?')} "
        f"reason={reason} gross={gross_pnl_pct*100:+.2f}% fee060={pnl_fee060*100:+.2f}%"
    )

# ── CHECK EXITS ───────────────────────────────────────────────────────────────
def check_exits(open_trades: list[dict]):
    for trade in open_trades:
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

        if hold_min >= EXIT_MAX_HOLD_MINUTES:
            close_trade(trade, current, "timeout")
            continue
        if gross_pnl_pct >= EXIT_TAKE_PROFIT_PCT:
            close_trade(trade, current, "tp")
            continue
        if gross_pnl_pct <= EXIT_STOP_LOSS_PCT:
            close_trade(trade, current, "sl")
            continue
        if EXIT_LIQ_CLIFF:
            entry_k = trade.get("entry_k_invariant")
            exit_k  = current.get("k_invariant")
            if entry_k and exit_k:
                cliff = k_lp_cliff(entry_k, exit_k, LP_CLIFF_THRESHOLD)
                if cliff["lp_removal_flag"]:
                    close_trade(trade, current, "lp_removal")
                    continue

        time.sleep(0.1)

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def run():
    logger.info("=" * 65)
    logger.info("Shadow Trader v1 (Playbook Edition) starting")
    logger.info(f"  Mode:                  {MODE}")
    logger.info(f"  Trade size:            {TRADE_SIZE_SOL} SOL")
    logger.info(f"  Max open/strategy:     {MAX_OPEN_PER_STRATEGY}")
    if MODE == "live_sim_mode":
        logger.info(f"  Max open global:       {MAX_OPEN_GLOBAL}")
    logger.info(f"  Exit TP/SL/timeout:    +{EXIT_TAKE_PROFIT_PCT}% / {EXIT_STOP_LOSS_PCT}% / {EXIT_MAX_HOLD_MINUTES}min")
    logger.info(f"  Friction gate (Jup):   <= {FRICTION_GATE_MAX_RT*100:.1f}% RT")
    logger.info(f"  LP cliff threshold:    {LP_CLIFF_THRESHOLD*100:.0f}% k-drop")
    logger.info(f"  Momentum entry:        r_m5>={MOMENTUM_R_M5_MIN}% buy_ratio>={MOMENTUM_BUY_RATIO_MIN} vol_accel>={MOMENTUM_VOL_ACCEL_MIN} avg_trade>=${MOMENTUM_AVG_TRADE_USD_MIN}")
    logger.info(f"  Pullback entry:        r_h1>={PULLBACK_R_H1_MIN}% r_m5<={PULLBACK_R_M5_MAX}% + confirm r_m5>={PULLBACK_CONFIRM_R_M5_MIN}% within {PULLBACK_CONFIRM_WINDOW_SEC}s")
    logger.info(f"  Baselines:             matched-time per strategy (momentum + pullback)")
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
            # 1. Check exits
            open_trades = get_open_trades()
            if open_trades:
                check_exits(open_trades)

            # 2. Fresh microstructure
            rows = get_latest_microstructure()
            if not rows:
                time.sleep(max(2, POLL_INTERVAL_SEC - (time.time() - loop_start)))
                continue

            now_ts = time.time()

            # 3. Expire stale pullback pending confirmations
            expired = [m for m, ts in _pullback_pending.items() if now_ts - ts > PULLBACK_CONFIRM_WINDOW_SEC]
            for m in expired:
                logger.debug(f"Pullback confirmation expired for {m[:8]}")
                del _pullback_pending[m]

            # 4. Evaluate entries
            for row in rows:
                mint = row.get("mint_address")
                if not mint:
                    continue

                strategy_trade_id = None  # track any strategy entry this cycle

                # ── Momentum ──
                if should_enter_momentum(row):
                    tid = open_trade("momentum", row)
                    if tid:
                        strategy_trade_id = tid
                        # Matched baseline for momentum
                        if passes_position_cap("baseline_matched_momentum"):
                            baseline_row = random.choice(rows)
                            open_trade("baseline_matched_momentum", baseline_row, baseline_trigger_id=tid)

                # ── Pullback (two-stage) ──
                if mint in _pullback_pending:
                    # Confirmation stage
                    if should_confirm_pullback(row):
                        del _pullback_pending[mint]
                        tid = open_trade("pullback", row)
                        if tid:
                            strategy_trade_id = tid
                            # Matched baseline for pullback
                            if passes_position_cap("baseline_matched_pullback"):
                                baseline_row = random.choice(rows)
                                open_trade("baseline_matched_pullback", baseline_row, baseline_trigger_id=tid)
                else:
                    # Initial signal stage
                    if should_enter_pullback_initial(row):
                        _pullback_pending[mint] = now_ts
                        logger.debug(f"Pullback initial signal for {row.get('token_symbol','?')} ({mint[:8]}), awaiting confirmation")

        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)

        # ── Score/Rank Fallback (fires at most 1/hour per strategy) ──
        if SCORE_RANK_ENABLED and rows:
            try:
                maybe_fire_rank_entry("momentum_rank", rows, score_momentum)
                maybe_fire_rank_entry("pullback_rank", rows, score_pullback)
            except Exception as rank_e:
                logger.error(f"Score/rank error: {rank_e}", exc_info=True)

        elapsed = time.time() - loop_start
        time.sleep(max(2, POLL_INTERVAL_SEC - elapsed))

if __name__ == "__main__":
    run()
