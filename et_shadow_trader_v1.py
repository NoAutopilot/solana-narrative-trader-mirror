#!/usr/bin/env python3
""""et_shadow_trader_v1.py — ET v1 Paper Trading Harness (Playbook Edition) v1.10

Strategy variants:
  momentum_strict  — strict threshold entries (r_m5>=0.8%, buy_ratio>=0.60, vol_accel>=1.5)
  pullback_strict  — strict two-stage entries (r_h1>=2%, r_m5<=-0.6% + confirmation)
  momentum_rank    — score/rank fallback: top-1 per 30min from ALL eligible tokens
  pullback_rank    — score/rank fallback: top-1 per 30min from ALL eligible tokens
  baseline_matched_momentum_strict  — matched-time baseline for momentum_strict
  baseline_matched_pullback_strict  — matched-time baseline for pullback_strict
  baseline_matched_momentum_rank    — matched-time baseline for momentum_rank
  baseline_matched_pullback_rank    — matched-time baseline for pullback_rank

Key changes from previous version:
  - Renamed momentum->momentum_strict, pullback->pullback_strict (clean separation)
  - Score/rank uses get_all_eligible_microstructure() (no cpamm_valid_flag filter)
    so rank mode can fire even when strict-universe is empty
  - Rank interval: 1800s (30 min) instead of 3600s — reach n>=20 faster
  - Signal frequency counters written to signal_frequency_log table each cycle
  - Universe expansion: rank mode scans all eligible tokens (not just CPAMM)

v1.7 additions:
  - Crash/rug risk filters: sell_ratio_spike, vol_h1_spike, liq_drop_proxy
  - filter_rejection_log table for audit trail of blocked entries
  - Baseline trades bypass rug filters (model unfiltered random selection)
  - Note: mint/freeze authority check omitted (pump.fun tokens have revoked
    authorities by design — check never fires, adds latency)

v1.10 additions:
  - Lane split (4 lanes):
      pumpfun_early:      pumpfun_origin=1 AND age < 24h  -> NO TRADES (log only)
      pumpfun_mature:     pumpfun_origin=1 AND age >= 24h -> eligible with stability gates
      non_pumpfun_mature: pumpfun_origin=0 AND age >= 4h
      large_cap_ray:      age >= 30d (benchmark)
  - pumpfun_mature extra stability gates:
      rv_5m <= PF_MATURE_RV5M_MAX (1.5%)
      range_5m <= PF_MATURE_RANGE_MULT * rv_5m (3x)
      sell_ratio_spike=0, liq_drop_proxy=0, vol_h1_spike=0 over last N polls
  - EXCLUDE_PUMPFUN_ORIGIN removed; replaced by lane-based eligibility
  - Universe composition section in report (pumpfun share by vol/liq tier)

v1.9 additions:
  - P0:  Hard pumpfun_origin exclusion gate — log but never trade pumpfun_origin tokens
  - P0.1: run_id (UUID per process start) + git_commit + lane_at_entry stored on every trade
  - P1:  momentum_strict DISABLED; anti-chase filter (r_m5 > 1.0% blocks all entries)
  - P2:  pullback_score_rank is SOLE active strategy; all others log-only
  - P3:  Continuous score: z_depth + vol_accel + buy_ratio - penalty*risk_flags; top-1/hour
  - P4:  filters_evaluated_count per scan + per-filter trigger counters

v1.8 additions:
  - Volatility-adaptive exits: SL/TP scale with rv_5m from microstructure_log
    SL = -max(RT_FLOOR + SL_BUFFER, K_SL * rv_5m)
    TP =  max(RT_FLOOR + TP_EDGE,   K_TP * rv_5m)
  - Vol no-trade filter: skip entry if K_SL * rv_5m > VOL_CAP_PCT (regime too hot)
  - entry_sl_pct / entry_tp_pct stored per trade for parameter sweep report
  - pumpfun_origin lane tag from microstructure_log
  - Baseline trades use FIXED exits (K_SL=0 path) for clean comparison

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

  C) Exit Policy (v1.8 volatility-adaptive):
     - SL = -max(RT_FLOOR + SL_BUFFER, K_SL * rv_5m)  [floor: -2.0%]
     - TP =  max(RT_FLOOR + TP_EDGE,   K_TP * rv_5m)  [floor: +4.0%]
     - max_hold_minutes = 12
     - liq_cliff_exit   = True (CPAMM only)
     - Vol no-trade: skip if K_SL * rv_5m > VOL_CAP_PCT (4.5%)

  D) Entry Conditions (v1):
     momentum_strict:
       - r_m5 >= +0.8%
       - buy_count_ratio_m5 >= 0.60
       - vol_accel_m5_vs_h1 >= 1.5
       - spam_flag = 0 AND avg_trade_usd_m5 >= $100
     pullback_strict:
       - r_h1 >= +2.0%
       - r_m5 <= -0.6%
       - Confirmation on next scan cycle: r_m5 >= -0.3% AND buy_count_ratio_m5 >= 0.55

  E) Score/Rank Fallback (fires at most 1 per SCORE_RANK_INTERVAL_SEC per strategy):
     momentum_rank: top-1 by r_m5 * buy_ratio * vol_accel * avg_trade_norm
     pullback_rank: top-1 by r_h1 * (-r_m5) * buy_ratio
     Uses ALL eligible tokens (not just CPAMM) to avoid starvation

  F) Baselines (matched-time, per-strategy variant):
     Each entry fires a matched baseline at the same timestamp

  G) Signal Frequency Logging:
     signal_frequency_log table: signals_seen, trades_opened per strategy per cycle

  Table: shadow_trades_v1 (does not overwrite shadow_trades)
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
POLL_INTERVAL_SEC           = 4          # base poll interval (was 15s — caused SL overshoot)
POLL_INTERVAL_NEAR_EXIT_SEC = 2          # faster polling when within 0.5% of SL or TP
EXIT_PROXIMITY_PCT          = 0.5        # trigger fast-poll when |gross| > SL-0.5% or TP-0.5%
TIMEOUT_MIN_GROSS_BUFFER    = 0.0025     # at timeout: skip exit unless gross >= RT_floor + 0.25%
HARD_MAX_HOLD_MINUTES       = 30         # absolute max hold regardless of timeout filter
TRADE_SIZE_SOL              = 0.01
MAX_OPEN_PER_STRATEGY       = 1
MAX_OPEN_GLOBAL             = 1          # only enforced in live_sim_mode
LP_CLIFF_THRESHOLD          = 0.05       # 5% k-drop triggers liq_cliff exit

# ── SCORE/RANK FALLBACK ───────────────────────────────────────────────────────
# v1.9: pullback_score_rank is the SOLE active strategy.
# All other variants are LOG-ONLY (signals counted, no trades opened).
SCORE_RANK_ENABLED          = True
# v1.11 P2: research_mode fires top-1 every 15 min; live_sim keeps 1h cadence
SCORE_RANK_INTERVAL_SEC_RESEARCH = 900   # 15 min — accelerated data collection
SCORE_RANK_INTERVAL_SEC_LIVE     = 3600  # 1 hour — live sim cadence
SCORE_RANK_INTERVAL_SEC     = SCORE_RANK_INTERVAL_SEC_RESEARCH if MODE == "research_mode" else SCORE_RANK_INTERVAL_SEC_LIVE
SCORE_RANK_MIN_R_M5         = 0.0
SCORE_RANK_MIN_BUY_RATIO    = 0.25
SCORE_RANK_MIN_VOL_ACCEL    = 0.2

# ── v1.10 LANE GATES ──────────────────────────────────────────────────────────
# pumpfun_early (age < 24h) is always blocked — no constant needed.
# pumpfun_mature (age >= 24h) is eligible but requires extra stability gates:
PF_MATURE_MIN_AGE_H         = 24.0       # hours — pumpfun_origin must be >= 24h old
PF_MATURE_RV5M_MAX          = 1.5        # % — max rv_5m for pumpfun_mature entries
PF_MATURE_RANGE_MULT        = 3.0        # range_5m must be <= this * rv_5m
# non_pumpfun_mature: pumpfun_origin=0, age >= LANE_GATE_MIN_AGE_H (4h)
# large_cap_ray: age >= 30 days (benchmark lane, no extra gates)

# P1: Anti-chase filter — block ALL long entries when r_m5 > this cap.
R_M5_CHASE_CAP              = 1.0        # % — skip entry if r_m5 > this
ANTI_CHASE_FILTER_ENABLED   = True

# P3: pullback_score_rank weights
# score = W_DEPTH*z_depth + W_VOL_ACCEL*vol_accel + W_BUY_RATIO*(buy_ratio-0.5) - W_PENALTY*risk_flags
PSR_W_DEPTH                 = 1.0
PSR_W_VOL_ACCEL             = 1.5
PSR_W_BUY_RATIO             = 0.5
PSR_W_PENALTY               = 3.0
PSR_MIN_R_H1                = 0.5        # % — minimum h1 gain before pullback
PSR_MIN_DEPTH               = 0.3        # % — minimum pullback depth
PSR_MIN_BUY_RATIO           = 0.25

FRICTION_GATE_MAX_RT        = 0.010      # 1.0% max total RT friction
DEXSCREENER_TIMEOUT         = 12
WSOL_MINT                   = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL            = 1_000_000_000

# ── UNIFIED EXIT POLICY (v1.8 volatility-adaptive) ──────────────────────────
# Fixed floors (used when rv_5m unavailable or for baseline trades)
EXIT_TAKE_PROFIT_PCT        = 4.0        # +4.0% gross floor
EXIT_STOP_LOSS_PCT          = -2.0       # -2.0% gross floor
EXIT_MAX_HOLD_MINUTES       = 12
EXIT_LIQ_CLIFF              = True

# Adaptive exit multipliers (v1.8)
# SL = -max(RT_floor + SL_BUFFER, K_SL * rv_5m)
# TP =  max(RT_floor + TP_EDGE,   K_TP * rv_5m)
ADAPTIVE_EXITS_ENABLED      = True
K_SL                        = 2.0        # SL = K_SL * rv_5m (e.g. 2 sigma)
K_TP                        = 4.0        # TP = K_TP * rv_5m (e.g. 4 sigma)
SL_BUFFER                   = 0.003      # 0.3% buffer above RT floor for SL
TP_EDGE                     = 0.015      # 1.5% edge buffer above RT floor for TP
VOL_CAP_PCT                 = 4.5        # skip entry if K_SL * rv_5m > this (regime too hot)
RV_WARMUP_POLLS             = 4          # min polls before rv_5m is trusted (else use fixed)

# ── CRASH / RUG RISK FILTERS (v1.7) ──────────────────────────────────────────
# Applied in open_trade() BEFORE the Jupiter friction gate.
# These are logged to filter_rejection_log for audit.
RUG_FILTER_ENABLED          = True
RUG_LIQ_DROP_1H_MAX         = 0.40   # block if liq_usd dropped >40% in last 1h
                                      # proxy: vol_h1 / vol_h6 ratio spike
RUG_SELL_RATIO_MAX          = 0.75   # block if sell txns > 75% of all txns in m5
                                      # (churn proxy: sudden holder exit)
RUG_VOL_H1_SPIKE_MAX        = 8.0    # block if vol_h1 > 8x vol_h6/6 (1h avg)
                                      # catches sudden volume spikes preceding rugs
RUG_MIN_TXNS_M5             = 5      # only apply sell-ratio filter if >=5 txns in m5
                                      # (avoid false positives on thin trading)

# ── ENTRY CONDITIONS v1 (strict) ──────────────────────────────────────────────
MOMENTUM_R_M5_MIN           = 0.8
MOMENTUM_BUY_RATIO_MIN      = 0.60
MOMENTUM_VOL_ACCEL_MIN      = 1.5
MOMENTUM_AVG_TRADE_USD_MIN  = 100.0      # spam filter

PULLBACK_R_H1_MIN           = 2.0
PULLBACK_R_M5_MAX           = -0.6
PULLBACK_BUY_RATIO_MIN      = 0.55       # confirmation
PULLBACK_CONFIRM_R_M5_MIN   = -0.3       # confirmation: r_m5 must recover to >= -0.3%
PULLBACK_CONFIRM_WINDOW_SEC = 75         # ~1 scan cycle + buffer

# ── IN-MEMORY STATE ───────────────────────────────────────────────────────────
# Pullback pending confirmation: {mint: timestamp_of_initial_signal}
_pullback_pending: dict[str, float] = {}
# Score/rank fallback: track last time each strategy fired a rank entry
_last_rank_entry: dict[str, float] = {}
# Jupiter API availability (set to False on first 401 to avoid repeated failures)
_jupiter_api_available: bool = True
# Signal frequency counters: {strategy: {"signals_seen": int, "trades_opened": int}}
_signal_freq: dict[str, dict] = {}
# Per-trade adaptive SL/TP thresholds: {trade_id: {"sl_pct": float, "tp_pct": float}}
_adaptive_thresholds: dict[str, dict] = {}

# ── v1.9 RUN IDENTITY ────────────────────────────────────────────────────────
# run_id: UUID generated at process start, stored on every trade for run isolation.
# git_commit: short hash of current HEAD (or 'unknown' if not in a git repo).
import subprocess as _subprocess
_RUN_ID: str = str(uuid.uuid4())
def _get_git_commit() -> str:
    try:
        return _subprocess.check_output(
            ["git", "-C", "/root/solana_trader", "rev-parse", "--short", "HEAD"],
            stderr=_subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "unknown"
_GIT_COMMIT: str = _get_git_commit()

# ── v1.9 FILTER SCAN COUNTERS ────────────────────────────────────────────────
# Accumulated per main-loop cycle, written to filter_rejection_log summary.
_filter_scan_counts: dict[str, int] = {
    "evaluated":          0,
    "pumpfun_excluded":   0,
    "anti_chase":         0,
    "lane_age":           0,
    "lane_liq":           0,
    "lane_vol":           0,
    "sell_ratio_spike":   0,
    "vol_h1_spike":       0,
    "liq_drop_proxy":     0,
    "vol_no_trade":       0,
    "friction_gate":      0,
}

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
        prev_poll_at            TEXT,
        prev_poll_pnl_pct       REAL,
        curr_poll_at            TEXT,
        curr_poll_pnl_pct       REAL,
        timeout_skipped_count   INTEGER DEFAULT 0,
        exited_at               TEXT,
        exit_price_usd          REAL,
        exit_price_native       REAL,
        exit_liq_usd            REAL,
        exit_liq_base           REAL,
        exit_k_invariant        REAL,
        exit_impact_sell_pct    REAL,
        exit_round_trip_pct     REAL,
        exit_reason             TEXT,
        sl_threshold_crossed_at TEXT,   -- UTC ISO: when SL was first breached
        tp_threshold_crossed_at TEXT,   -- UTC ISO: when TP was first breached
        exit_overshoot_pct      REAL,   -- realized_pnl - threshold (negative = overshoot past SL)
        exit_overshoot_sec      REAL,   -- seconds between threshold cross and actual exit
        gross_pnl_pct           REAL,
        shadow_pnl_pct          REAL,
        shadow_pnl_sol          REAL,
        shadow_pnl_pct_fee025   REAL,
        shadow_pnl_pct_fee060   REAL,
        shadow_pnl_pct_fee100   REAL,
        mode                    TEXT,
        status                  TEXT    DEFAULT 'open',
        -- Lane tagging (v1.6)
        lane                    TEXT,   -- mature_raydium | mature_pumpswap | fresh_pumpswap | large_cap
        age_at_entry_h          REAL,   -- token age in hours at entry
        liq_usd_at_entry        REAL,   -- liquidity USD at entry
        vol_24h_at_entry        REAL,   -- 24h volume USD at entry
        pool_type_at_entry      TEXT,   -- raydium | pumpswap | meteora | etc.
        venue_at_entry          TEXT,   -- venue from universe_snapshot
        spam_flag_at_entry      INTEGER -- spam_flag from universe_snapshot
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sv1_strategy ON shadow_trades_v1(strategy, entered_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sv1_status   ON shadow_trades_v1(status)")
    # Migrations for existing tables (v1.7 filter_rejection_log)
    try:
        c.execute("""
        CREATE TABLE IF NOT EXISTS filter_rejection_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at       TEXT    NOT NULL,
            strategy        TEXT    NOT NULL,
            mint_address    TEXT    NOT NULL,
            token_symbol    TEXT,
            filter_name     TEXT    NOT NULL,
            filter_value    REAL,
            filter_threshold REAL,
            lane            TEXT,
            age_h           REAL,
            liq_usd         REAL,
            vol_24h         REAL
        )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_frl_at ON filter_rejection_log(logged_at, strategy)")
    except Exception:
        pass

    # Migrations for existing tables (v1.6 lane columns) — must run BEFORE creating lane index
    for col, coltype in [
        ("lane",               "TEXT"),
        ("age_at_entry_h",     "REAL"),
        ("liq_usd_at_entry",   "REAL"),
        ("vol_24h_at_entry",   "REAL"),
        ("pool_type_at_entry", "TEXT"),
        ("venue_at_entry",     "TEXT"),
        ("spam_flag_at_entry", "INTEGER"),
        # v1.9 columns
        ("run_id",             "TEXT"),
        ("git_commit",         "TEXT"),
        ("lane_at_entry",      "TEXT"),
        ("entry_score",        "REAL"),
    ]:
        try:
            c.execute(f"ALTER TABLE shadow_trades_v1 ADD COLUMN {col} {coltype}")
        except Exception:
            pass  # column already exists
    # Lane index after migration (column guaranteed to exist)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sv1_lane ON shadow_trades_v1(lane)")

    # Filter rejection log: one row per rejected trade attempt
    c.execute("""
    CREATE TABLE IF NOT EXISTS filter_rejection_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at       TEXT    NOT NULL,
        strategy        TEXT    NOT NULL,
        mint_address    TEXT    NOT NULL,
        token_symbol    TEXT,
        filter_name     TEXT    NOT NULL,
        filter_value    REAL,
        filter_threshold REAL,
        lane            TEXT,
        age_h           REAL,
        liq_usd         REAL,
        vol_24h         REAL
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_frl_at ON filter_rejection_log(logged_at, strategy)")

    # Signal frequency log: one row per strategy per scan cycle
    c.execute("""
    CREATE TABLE IF NOT EXISTS signal_frequency_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at       TEXT    NOT NULL,
        strategy        TEXT    NOT NULL,
        signals_seen    INTEGER DEFAULT 0,
        trades_opened   INTEGER DEFAULT 0,
        universe_size   INTEGER DEFAULT 0
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sfl_at ON signal_frequency_log(logged_at, strategy)")

    # v1.9: filter_scan_log — per-cycle filter evaluation counts
    c.execute("""
    CREATE TABLE IF NOT EXISTS filter_scan_log (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at           TEXT    NOT NULL,
        run_id              TEXT,
        evaluated           INTEGER DEFAULT 0,
        pumpfun_excluded    INTEGER DEFAULT 0,
        anti_chase          INTEGER DEFAULT 0,
        lane_age            INTEGER DEFAULT 0,
        lane_liq            INTEGER DEFAULT 0,
        lane_vol            INTEGER DEFAULT 0,
        sell_ratio_spike    INTEGER DEFAULT 0,
        vol_h1_spike        INTEGER DEFAULT 0,
        liq_drop_proxy      INTEGER DEFAULT 0,
        vol_no_trade        INTEGER DEFAULT 0,
        friction_gate       INTEGER DEFAULT 0
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_fsl_at ON filter_scan_log(logged_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sv1_run ON shadow_trades_v1(run_id)")

    # v1.11 P0: run_registry — one row per process start, for run isolation
    c.execute("""
    CREATE TABLE IF NOT EXISTS run_registry (
        run_id          TEXT    PRIMARY KEY,
        git_commit      TEXT,
        start_ts        TEXT    NOT NULL,
        mode            TEXT,
        version         TEXT,
        lane_gates      TEXT,
        key_params      TEXT
    )
    """)

    # v1.11 P4: invalid_pair column on shadow_trades_v1
    try:
        c.execute("ALTER TABLE shadow_trades_v1 ADD COLUMN invalid_pair INTEGER DEFAULT 0")
    except Exception:
        pass

    conn.commit()
    conn.close()
    logger.info("Tables initialized: shadow_trades_v1, run_registry, signal_frequency_log, filter_scan_log")

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
    """
    Returns tokens that pass the STRICT universe filter:
    - cpamm_valid_flag = 1 (CPAMM pools only)
    - eligible = 1
    - spam_flag = 0
    - microstructure data within last 2 minutes
    Used for: momentum_strict, pullback_strict entries.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.*,
               u.age_hours, u.liq_usd, u.vol_h24, u.venue, u.pool_type,
               u.cpamm_valid_flag, u.spam_flag, u.pair_address as u_pair_address
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

def get_rv5m_for_mint(mint: str) -> float | None:
    """
    Return the most recent rv_5m for a mint from microstructure_log.
    Returns None if no data or column missing (warmup period).
    """
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rv_5m FROM microstructure_log
            WHERE mint_address = ?
              AND rv_5m IS NOT NULL
            ORDER BY logged_at DESC
            LIMIT 1
        """, (mint,))
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None:
            return float(row[0])
        return None
    except Exception:
        return None

def compute_adaptive_exits(rt_floor: float, rv_5m: float | None) -> tuple[float, float]:
    """
    Compute adaptive SL and TP thresholds.
    Returns (sl_pct, tp_pct) as signed percentages (sl negative, tp positive).
    Falls back to fixed floors when rv_5m is None.
    """
    if not ADAPTIVE_EXITS_ENABLED or rv_5m is None:
        return EXIT_STOP_LOSS_PCT, EXIT_TAKE_PROFIT_PCT
    sl = -max(rt_floor * 100 + SL_BUFFER * 100, K_SL * rv_5m)
    tp =  max(rt_floor * 100 + TP_EDGE * 100,   K_TP * rv_5m)
    # Clamp: SL floor at -10% (don't widen too far), TP cap at 20%
    sl = max(sl, -10.0)
    tp = min(tp, 20.0)
    return sl, tp

def get_all_eligible_microstructure() -> list[dict]:
    """
    Returns ALL eligible tokens regardless of pool type (CPAMM, CLMM, DLMM).
    Used exclusively by score/rank fallback to avoid starvation when CPAMM
    universe is empty or has no qualifying candidates.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.*,
               u.age_hours, u.liq_usd, u.vol_h24, u.venue, u.pool_type,
               u.cpamm_valid_flag, u.spam_flag, u.pair_address as u_pair_address
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
            AND u.eligible = 1
        ORDER BY m.vol_h24 DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def log_filter_rejection(
    strategy: str, mint: str, symbol: str, filter_name: str,
    filter_value: float | None, filter_threshold: float | None,
    lane: str | None = None, age_h: float | None = None,
    liq_usd: float | None = None, vol_24h: float | None = None,
):
    """Write a filter rejection to filter_rejection_log for audit."""
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO filter_rejection_log
            (logged_at, strategy, mint_address, token_symbol, filter_name,
             filter_value, filter_threshold, lane, age_h, liq_usd, vol_24h)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            strategy, mint, symbol, filter_name,
            filter_value, filter_threshold, lane, age_h, liq_usd, vol_24h,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"filter_rejection_log write error: {e}")

def check_rug_risk(row: dict, strategy: str) -> tuple[bool, str]:
    """
    Check crash/rug risk signals before entry.
    Returns (is_risky: bool, reason: str).
    Logs rejections to filter_rejection_log.

    Filters applied:
      1. sell_ratio_spike: sell txns > RUG_SELL_RATIO_MAX of all m5 txns
         (sudden holder exit / churn proxy)
      2. vol_h1_spike: vol_h1 > RUG_VOL_H1_SPIKE_MAX * (vol_h6/6)
         (abnormal 1h volume spike preceding rug pulls)
      3. liq_drop_1h: vol_h1 / vol_h6 ratio combined with sell_ratio
         (heuristic for liquidity drain)

    Note: mint/freeze authority check via RPC is intentionally omitted.
    pump.fun graduated tokens have revoked authorities (None) by design —
    the check would never fire and adds latency. The k-drop exit (LP cliff)
    already handles in-trade liquidity removal.
    """
    if not RUG_FILTER_ENABLED:
        return False, ""

    mint   = row.get("mint_address", "?")
    symbol = row.get("token_symbol", "?")
    lane   = classify_lane(row)
    age_h  = row.get("age_hours") or 0
    liq    = row.get("liq_usd") or 0
    vol24h = row.get("vol_h24") or 0

    # ── Filter 1: Sell-ratio spike (churn proxy) ──────────────────────────────
    sells_m5 = row.get("sells_m5") or 0
    buys_m5  = row.get("buys_m5")  or 0
    total_m5 = buys_m5 + sells_m5
    if total_m5 >= RUG_MIN_TXNS_M5 and sells_m5 > 0:
        sell_ratio = sells_m5 / total_m5
        if sell_ratio > RUG_SELL_RATIO_MAX:
            reason = f"sell_ratio_spike: {sell_ratio:.2f} > {RUG_SELL_RATIO_MAX} (sells={sells_m5} buys={buys_m5})"
            logger.info(f"RUG_FILTER {strategy} {symbol} ({mint[:8]}): {reason}")
            log_filter_rejection(
                strategy, mint, symbol, "sell_ratio_spike",
                sell_ratio, RUG_SELL_RATIO_MAX, lane, age_h, liq, vol24h
            )
            return True, reason

    # ── Filter 2: Vol-H1 spike (abnormal volume preceding rug) ───────────────
    vol_h1 = row.get("vol_h1") or 0
    vol_h6 = row.get("vol_h6") or 0
    if vol_h6 > 0 and vol_h1 > 0:
        vol_h1_vs_avg = vol_h1 / (vol_h6 / 6.0)  # ratio vs 1h average over last 6h
        if vol_h1_vs_avg > RUG_VOL_H1_SPIKE_MAX:
            reason = f"vol_h1_spike: {vol_h1_vs_avg:.1f}x avg (vol_h1=${vol_h1:,.0f} vol_h6avg=${vol_h6/6:,.0f})"
            logger.info(f"RUG_FILTER {strategy} {symbol} ({mint[:8]}): {reason}")
            log_filter_rejection(
                strategy, mint, symbol, "vol_h1_spike",
                vol_h1_vs_avg, RUG_VOL_H1_SPIKE_MAX, lane, age_h, liq, vol24h
            )
            return True, reason

    # ── Filter 3: Liq-drop proxy (high sell ratio + vol spike combined) ───────
    # If sell ratio is elevated (>60%) AND vol_h1 is >4x avg, flag as liq drain
    if total_m5 >= RUG_MIN_TXNS_M5 and vol_h6 > 0 and vol_h1 > 0:
        sell_ratio_soft = sells_m5 / total_m5 if total_m5 > 0 else 0
        vol_h1_ratio    = vol_h1 / (vol_h6 / 6.0)
        if sell_ratio_soft > 0.60 and vol_h1_ratio > 4.0:
            reason = (
                f"liq_drop_proxy: sell_ratio={sell_ratio_soft:.2f} + "
                f"vol_h1_spike={vol_h1_ratio:.1f}x (combined rug signal)"
            )
            logger.info(f"RUG_FILTER {strategy} {symbol} ({mint[:8]}): {reason}")
            log_filter_rejection(
                strategy, mint, symbol, "liq_drop_proxy",
                vol_h1_ratio, 4.0, lane, age_h, liq, vol24h
            )
            return True, reason

    return False, ""

def log_signal_frequency(strategy: str, signals_seen: int, trades_opened: int, universe_size: int):
    """Write signal frequency data to DB for reporting."""
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO signal_frequency_log (logged_at, strategy, signals_seen, trades_opened, universe_size)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now(timezone.utc).isoformat(), strategy, signals_seen, trades_opened, universe_size))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"signal_frequency_log write error: {e}")

def log_filter_scan(counts: dict):
    """Write per-cycle filter evaluation counts to filter_scan_log."""
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO filter_scan_log
            (logged_at, run_id, evaluated, pumpfun_excluded, anti_chase,
             lane_age, lane_liq, lane_vol,
             sell_ratio_spike, vol_h1_spike, liq_drop_proxy, vol_no_trade, friction_gate)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            datetime.now(timezone.utc).isoformat(), _RUN_ID,
            counts.get("evaluated", 0),
            counts.get("pumpfun_excluded", 0),
            counts.get("anti_chase", 0),
            counts.get("lane_age", 0),
            counts.get("lane_liq", 0),
            counts.get("lane_vol", 0),
            counts.get("sell_ratio_spike", 0),
            counts.get("vol_h1_spike", 0),
            counts.get("liq_drop_proxy", 0),
            counts.get("vol_no_trade", 0),
            counts.get("friction_gate", 0),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"filter_scan_log write error: {e}")

# ── LANE CLASSIFICATION ──────────────────────────────────────────────────────
# Hard gates: tokens must pass ALL to be eligible for any strategy entry.
# These are enforced in open_trade() before the friction gate.
LANE_GATE_MIN_AGE_H    = 4.0       # hours — exclude fresh graduates
LANE_GATE_MIN_LIQ_USD  = 100_000   # USD — minimum liquidity
LANE_GATE_MIN_VOL_24H  = 250_000   # USD — minimum 24h volume

def classify_lane(row: dict) -> str:
    """
    Assign a lane label based on pumpfun_origin flag, age, and venue.

    Lane taxonomy (v1.10):
      pumpfun_early:      pumpfun_origin=1 AND age < 24h  -> blocked (log only)
      pumpfun_mature:     pumpfun_origin=1 AND age >= 24h -> eligible with stability gates
      large_cap_ray:      pumpfun_origin=0 AND age >= 30d -> benchmark lane
      non_pumpfun_mature: pumpfun_origin=0 AND 4h <= age < 30d -> standard eligible
      unknown:            fallback (missing data)
    """
    age_h     = row.get("age_hours") or 0
    pf_origin = row.get("pumpfun_origin") or 0

    # Also treat pumpswap venue as pumpfun_origin if flag not set
    venue     = (row.get("venue") or "").lower()
    pool_type = (row.get("pool_type") or "").lower()
    if "pumpswap" in venue or "pump" in pool_type:
        pf_origin = 1

    if pf_origin:
        return "pumpfun_mature" if age_h >= PF_MATURE_MIN_AGE_H else "pumpfun_early"

    # Non-pump venues
    if age_h >= 24 * 30:  # 30 days
        return "large_cap_ray"
    return "non_pumpfun_mature"

# ── JUPITER FRICTION GATE ─────────────────────────────────────────────────────
# Jupiter Ultra API: single call returns priceImpactPct + routePlan label.
# Endpoint: GET /ultra/v1/order  Header: x-api-key
# Pool-type rules:
#   cpamm_valid_flag=1  → CPAMM math fallback OK when Jupiter unavailable
#   cpamm_valid_flag=0  → REQUIRE Jupiter quote; no CPAMM fallback (wrong math)
_jup_health_checked: bool = False

def _check_jup_health():
    """One-time startup health check. Sets _jupiter_api_available."""
    global _jupiter_api_available, _jup_health_checked
    if _jup_health_checked:
        return
    _jup_health_checked = True
    try:
        r = requests.get(
            f"{JUPITER_BASE_URL}/ultra/v1/order",
            headers={"x-api-key": JUPITER_API_KEY},
            params={"inputMint": WSOL_MINT,
                    "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "amount": "1000000"},
            timeout=10,
        )
        if r.status_code == 200:
            _jupiter_api_available = True
            logger.info("JUP_HEALTH: OK (ultra/v1/order 200) — Jupiter RT quotes active")
        elif r.status_code == 401:
            _jupiter_api_available = False
            logger.warning("JUP_HEALTH: FAIL 401 — Jupiter unavailable. CPAMM-only lanes OK; CLMM/DLMM lanes BLOCKED.")
        else:
            _jupiter_api_available = False
            logger.warning(f"JUP_HEALTH: FAIL {r.status_code} — Jupiter unavailable.")
    except Exception as e:
        _jupiter_api_available = False
        logger.warning(f"JUP_HEALTH: ERROR {e} — Jupiter unavailable.")


def get_jupiter_rt_estimate(
    mint: str,
    liq_base: float = 0,
    liq_quote_sol: float = 0,
    cpamm_valid: bool = True,
) -> float | None:
    """
    Returns total RT friction fraction (e.g. 0.008 = 0.8%) or None if no route.

    Pool-type aware:
      cpamm_valid=True  → CPAMM math fallback when Jupiter unavailable
      cpamm_valid=False → return None when Jupiter unavailable (CLMM/DLMM: wrong math)

    Uses Jupiter Ultra API: GET /ultra/v1/order (x-api-key header).
    priceImpactPct from Ultra is one-way impact; RT = 2 * |priceImpactPct| + DEX_FEE_RT.
    """
    global _jupiter_api_available
    _check_jup_health()  # no-op after first call
    sol_in_lamports = int(TRADE_SIZE_SOL * LAMPORTS_PER_SOL)

    if _jupiter_api_available:
        try:
            r = requests.get(
                f"{JUPITER_BASE_URL}/ultra/v1/order",
                headers={"x-api-key": JUPITER_API_KEY},
                params={
                    "inputMint":  WSOL_MINT,
                    "outputMint": mint,
                    "amount":     str(sol_in_lamports),
                },
                timeout=8,
            )
            if r.status_code == 401:
                if _jupiter_api_available:  # log only once
                    logger.warning("Jupiter 401 mid-session — switching to CPAMM fallback for CPAMM pools")
                _jupiter_api_available = False
            elif r.status_code == 404:
                # No route for this token
                return None
            elif r.status_code == 200:
                data = r.json()
                impact = abs(float(data.get("priceImpactPct") or 0)) / 100.0  # convert % to fraction
                # RT = 2x one-way impact + platform fee (feeBps)
                fee_bps = int(data.get("feeBps") or 0)
                platform_fee_rt = 2 * fee_bps / 10000
                # DEX fee is embedded in the quote (not separate), so RT ≈ 2*impact + platform_fee
                rt_pct = 2 * impact + platform_fee_rt
                # Log route label for auditability
                route_plan = data.get("routePlan") or []
                label = route_plan[0].get("swapInfo", {}).get("label", "?") if route_plan else "?"
                logger.debug(
                    f"Jup ultra RT for {mint[:8]}: impact={impact*100:.3f}% "
                    f"fee={platform_fee_rt*100:.3f}% total={rt_pct*100:.3f}% route={label}"
                )
                return max(rt_pct, 0.0)
        except requests.exceptions.Timeout:
            logger.debug(f"Jupiter timeout for {mint[:8]}")
        except Exception as e:
            logger.debug(f"Jupiter error for {mint[:8]}: {e}")

    # Jupiter unavailable — pool-type determines fallback behaviour
    if not cpamm_valid:
        # CLMM/DLMM: CPAMM math is wrong for these pools. Block the trade.
        logger.debug(f"SKIP {mint[:8]}: Jupiter unavailable and pool is not CPAMM — no safe friction estimate")
        return None

    # CPAMM fallback: use CPAMM math + accurate DEX fee (0.50% RT = 0.25% each way)
    if liq_base > 0 and liq_quote_sol > 0:
        rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_base, liq_quote_sol)
        cpamm_rt = rt["total_friction"] + 0.005  # 0.50% RT DEX fee (Raydium CPAMM)
        logger.debug(f"CPAMM fallback RT for {mint[:8]}: {cpamm_rt*100:.2f}%")
        return min(cpamm_rt, 0.05)
    else:
        # No liquidity data and no Jupiter — conservative estimate for CPAMM
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

def should_enter_momentum_strict(row: dict) -> bool:
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
    """Composite pullback score (legacy rank). Higher = better candidate."""
    r_h1      = max(row.get("r_h1") or 0, 0)
    r_m5_neg  = max(-(row.get("r_m5") or 0), 0)  # want r_m5 to be negative
    buy_ratio = max(row.get("buy_count_ratio_m5") or 0, 0)
    return r_h1 * r_m5_neg * buy_ratio

def score_pullback_v19(row: dict) -> float:
    """
    v1.9 continuous pullback score (P3).
    score = W_DEPTH*z_depth + W_VOL_ACCEL*vol_accel + W_BUY_RATIO*(buy_ratio-0.5) - W_PENALTY*risk_flags

    z_depth = -r_m5 / rv_5m  (depth in sigma units; requires rv_5m > 0)
    Falls back to raw -r_m5 when rv_5m unavailable.
    risk_flags: count of active risk signals (sell_ratio_spike, vol_h1_spike, liq_drop_proxy)
    """
    r_m5      = row.get("r_m5") or 0
    rv_5m     = row.get("rv_5m") or 0
    vol_accel = max(row.get("vol_accel_m5_vs_h1") or 0, 0)
    buy_ratio = max(row.get("buy_count_ratio_m5") or 0, 0)

    # Depth component: z_depth (sigma units) or raw depth
    if rv_5m > 0.01:  # require at least 0.01% rv_5m to avoid div-by-zero
        z_depth = max(-r_m5 / rv_5m, 0)  # positive when r_m5 is negative
    else:
        z_depth = max(-r_m5, 0)  # raw depth fallback

    # Risk flag count (penalty)
    sells_m5 = row.get("sells_m5") or 0
    buys_m5  = row.get("buys_m5") or 0
    total_m5 = buys_m5 + sells_m5
    vol_h1   = row.get("vol_h1") or 0
    vol_h6   = row.get("vol_h6") or 0
    risk_flags = 0
    if total_m5 >= RUG_MIN_TXNS_M5 and total_m5 > 0:
        sell_ratio = sells_m5 / total_m5
        if sell_ratio > RUG_SELL_RATIO_MAX:
            risk_flags += 1
    if vol_h6 > 0 and vol_h1 > 0:
        if (vol_h1 / (vol_h6 / 6.0)) > RUG_VOL_H1_SPIKE_MAX:
            risk_flags += 1

    score = (
        PSR_W_DEPTH     * z_depth
        + PSR_W_VOL_ACCEL * vol_accel
        + PSR_W_BUY_RATIO * (buy_ratio - 0.5)
        - PSR_W_PENALTY   * risk_flags
    )
    return score

def maybe_fire_rank_entry(strategy: str, all_rows: list[dict], score_fn) -> str | None:
    """
    v1.9: Only fires for pullback_score_rank (sole active strategy).
    All other strategies are log-only — this function returns None for them.
    Applies P0 (pumpfun exclusion) and P1 (anti-chase) gates to candidate pool.
    """
    if not SCORE_RANK_ENABLED:
        return None
    # v1.9: only pullback_score_rank opens trades
    if strategy not in ("pullback_score_rank", "baseline_matched_pullback_score_rank"):
        return None
    now = time.time()
    last = _last_rank_entry.get(strategy, 0)
    if now - last < SCORE_RANK_INTERVAL_SEC:
        return None  # Not time yet

    # v1.10: include pumpfun_mature; exclude only pumpfun_early
    mature_rows = [r for r in all_rows if classify_lane(r) != "pumpfun_early"]

    # v1.11 P1: NO hard AND gate — all mature tokens are candidates.
    # Score handles signal strength continuously. Only hard safety gates apply:
    #   - r_m5 <= R_M5_CHASE_CAP (anti-chase, applied inside open_trade)
    #   - lane/liq/vol/friction/rug gates (applied inside open_trade)
    # Soft preference: tokens with r_m5 < 0 (pullback) score higher via z_depth.
    candidates = mature_rows  # all mature tokens are candidates

    if not candidates:
        # P3: detailed no-candidate diagnostic
        logger.info(
            f"RANK {strategy}: NO CANDIDATES "
            f"(universe={len(all_rows)} mature={len(mature_rows)} "
            f"pumpfun_early_blocked={sum(1 for r in all_rows if classify_lane(r)=='pumpfun_early')})"
        )
        _last_rank_entry[strategy] = now
        return None

    # Score all candidates, pick top-1
    scored = [(score_fn(r), r) for r in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]

    # P3: log top-3 candidates for diagnostics
    top3 = scored[:3]
    top3_str = "  ".join(
        f"{r.get('token_symbol','?')}(sc={sc:.2f} r_m5={r.get('r_m5') or 0:.2f}% r_h1={r.get('r_h1') or 0:.2f}%)"
        for sc, r in top3
    )
    logger.info(
        f"RANK {strategy}: top-3 candidates [{top3_str}] "
        f"universe={len(all_rows)} mature={len(mature_rows)}"
    )

    _last_rank_entry[strategy] = now
    logger.info(
        f"RANK {strategy}: firing top-1 "
        f"{best.get('token_symbol','?')} ({best.get('mint_address','?')[:8]}) "
        f"score={best_score:.4f} "
        f"r_m5={best.get('r_m5') or 0:.2f}% r_h1={best.get('r_h1') or 0:.2f}% "
        f"rv_5m={best.get('rv_5m') or 0:.4f}% "
        f"buy_ratio={best.get('buy_count_ratio_m5') or 0:.2f} "
        f"lane={classify_lane(best)} pumpfun={best.get('pumpfun_origin',0)}"
    )
    tid = open_trade(strategy, best, entry_score=best_score)
    if tid:
        logger.info(f"RANK {strategy}: entry opened trade_id={tid[:8]}")
        # P4: Matched baseline — random from mature universe, must succeed 1:1
        baseline_strat = "baseline_matched_pullback_score_rank"
        if passes_position_cap(baseline_strat) and mature_rows:
            baseline_row = random.choice(mature_rows)
            btid = open_trade(baseline_strat, baseline_row, baseline_trigger_id=tid)
            if not btid:
                # P4: baseline failed — mark strategy trade as invalid_pair
                logger.warning(f"RANK {strategy}: baseline open FAILED for trigger={tid[:8]} — marking invalid_pair")
                try:
                    conn = get_conn()
                    conn.execute("UPDATE shadow_trades_v1 SET invalid_pair=1 WHERE trade_id=?", (tid,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"invalid_pair mark failed: {e}")
    else:
        # P3: open_trade rejected top-1 — log why (gates fired inside open_trade)
        logger.info(f"RANK {strategy}: top-1 {best.get('token_symbol','?')} rejected by open_trade gates")
    return tid

# ── OPEN TRADE ────────────────────────────────────────────────────────────────
def open_trade(strategy: str, row: dict, baseline_trigger_id: str | None = None, entry_score: float | None = None) -> str | None:
    """
    Open a shadow trade. Returns trade_id on success, None if blocked.
    Checks: position cap → P0 pumpfun gate → P1 anti-chase → lane gates → rug filters → Jupiter → insert.
    """
    # Baseline trades are virtual controls — exempt from ALL position cap checks.
    # They must always open 1:1 with the strategy trade; blocking them creates invalid_pair.
    is_baseline = baseline_trigger_id is not None
    if not is_baseline and not passes_position_cap(strategy):
        logger.debug(f"SKIP {strategy}: position cap reached")
        return None

    # ── P0: LANE ELIGIBILITY CHECK (v1.10) ─────────────────────────────────────────
    # pumpfun_early is always blocked.
    # pumpfun_mature is eligible but requires extra stability gates (checked below).
    # non_pumpfun_mature and large_cap_ray: standard gates only.
    lane_check = classify_lane(row)
    if lane_check == "pumpfun_early":
        _filter_scan_counts["pumpfun_excluded"] = _filter_scan_counts.get("pumpfun_excluded", 0) + 1
        logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: pumpfun_early (age={row.get('age_hours',0):.1f}h < {PF_MATURE_MIN_AGE_H}h)")
        return None

    # ── P1: ANTI-CHASE FILTER (v1.9) ───────────────────────────────────────────────
    # Block ALL long entries when r_m5 > R_M5_CHASE_CAP (1.0%).
    # Does not apply to baseline trades (they model unfiltered selection).
    if ANTI_CHASE_FILTER_ENABLED and not strategy.startswith("baseline_"):
        r_m5_entry = row.get("r_m5") or 0
        if r_m5_entry > R_M5_CHASE_CAP:
            _filter_scan_counts["anti_chase"] = _filter_scan_counts.get("anti_chase", 0) + 1
            log_filter_rejection(
                strategy, row.get("mint_address", "?"), row.get("token_symbol", "?"),
                "anti_chase", r_m5_entry, R_M5_CHASE_CAP,
                classify_lane(row), row.get("age_hours"), row.get("liq_usd"), row.get("vol_h24")
            )
            logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: anti_chase r_m5={r_m5_entry:.2f}% > cap={R_M5_CHASE_CAP}%")
            return None

    # ── HARD LANE GATES ───────────────────────────────────────────────────────────
    # Applied to ALL strategies (strict + rank). Prevents rug-risk tokens.
    age_h   = row.get("age_hours") or 0
    liq_usd = row.get("liq_usd")   or 0
    vol_24h = row.get("vol_h24")   or 0
    if age_h < LANE_GATE_MIN_AGE_H:
        _filter_scan_counts["lane_age"] = _filter_scan_counts.get("lane_age", 0) + 1
        logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: age {age_h:.1f}h < {LANE_GATE_MIN_AGE_H}h gate")
        return None
    if liq_usd < LANE_GATE_MIN_LIQ_USD:
        _filter_scan_counts["lane_liq"] = _filter_scan_counts.get("lane_liq", 0) + 1
        logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: liq ${liq_usd:,.0f} < ${LANE_GATE_MIN_LIQ_USD:,} gate")
        return None
    if vol_24h < LANE_GATE_MIN_VOL_24H:
        _filter_scan_counts["lane_vol"] = _filter_scan_counts.get("lane_vol", 0) + 1
        logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: vol24h ${vol_24h:,.0f} < ${LANE_GATE_MIN_VOL_24H:,} gate")
        return None
    # ── CRASH / RUG RISK FILTERS (v1.7) ──────────────────────────────────────
    # Applied after lane gates, before Jupiter friction gate.
    # Baseline trades are NOT filtered (they model unfiltered random selection).
    if not strategy.startswith("baseline_"):
        is_risky, rug_reason = check_rug_risk(row, strategy)
        if is_risky:
            logger.info(f"SKIP {strategy} {row.get('token_symbol','?')} ({row.get('mint_address','?')[:8]}): rug_filter={rug_reason}")
            return None

    lane = classify_lane(row)
    mint = row["mint_address"]

    # ── PUMPFUN_MATURE STABILITY GATES (v1.10) ────────────────────────────────────
    # Applied only to pumpfun_mature tokens. Baseline trades bypass.
    if lane == "pumpfun_mature" and not strategy.startswith("baseline_"):
        rv5m_check  = row.get("rv_5m") or None
        range5m     = row.get("range_5m") or None
        # Gate 1: rv_5m must be available and <= PF_MATURE_RV5M_MAX
        if rv5m_check is None:
            logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: pumpfun_mature rv_5m unavailable")
            return None
        if rv5m_check > PF_MATURE_RV5M_MAX:
            logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: pumpfun_mature rv_5m={rv5m_check:.3f}% > {PF_MATURE_RV5M_MAX}%")
            log_filter_rejection(strategy, mint, row.get('token_symbol','?'), "pf_mature_rv5m",
                rv5m_check, PF_MATURE_RV5M_MAX, lane, age_h, liq_usd, vol_24h)
            return None
        # Gate 2: range_5m <= PF_MATURE_RANGE_MULT * rv_5m
        if range5m is not None and rv5m_check > 0:
            if range5m > PF_MATURE_RANGE_MULT * rv5m_check:
                logger.debug(f"SKIP {strategy} {row.get('token_symbol','?')}: pumpfun_mature range_5m={range5m:.3f}% > {PF_MATURE_RANGE_MULT}x rv_5m")
                log_filter_rejection(strategy, mint, row.get('token_symbol','?'), "pf_mature_range",
                    range5m, PF_MATURE_RANGE_MULT * rv5m_check, lane, age_h, liq_usd, vol_24h)
                return None
        # Gate 3: no active risk flags (sell_ratio_spike, liq_drop_proxy, vol_h1_spike)
        # check_rug_risk already ran above; if we reach here, no flags fired.
        # (rug filters are applied to all non-baseline strategies before this block)

    # ── VOL NO-TRADE FILTER (v1.8) ────────────────────────────────────────────
    # Skip entry if realized vol is too high for our bankroll to absorb the SL.
    # Baseline trades bypass this filter (they model unfiltered random selection).
    if not strategy.startswith("baseline_") and ADAPTIVE_EXITS_ENABLED:
        rv5m = get_rv5m_for_mint(mint)
        if rv5m is not None and (K_SL * rv5m) > VOL_CAP_PCT:
            reason = f"vol_no_trade: K_SL*rv_5m={K_SL*rv5m:.2f}% > cap={VOL_CAP_PCT}% (rv_5m={rv5m:.4f}%)"
            logger.info(f"SKIP {strategy} {row.get('token_symbol','?')} ({mint[:8]}): {reason}")
            log_filter_rejection(
                strategy, mint, row.get('token_symbol','?'), "vol_no_trade",
                K_SL * rv5m, VOL_CAP_PCT, lane, age_h, liq_usd, vol_24h
            )
            return None

    liq_b_for_jup  = row.get("liq_base") or 0
    liq_q_for_jup  = row.get("liq_quote_sol") or 0
    cpamm_valid    = bool(row.get("cpamm_valid_flag", 1))  # default True if field missing
    jup_rt = get_jupiter_rt_estimate(mint, liq_b_for_jup, liq_q_for_jup, cpamm_valid=cpamm_valid)
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

    # ── Compute adaptive SL/TP for this trade (v1.8) ─────────────────────────
    rv5m_entry = get_rv5m_for_mint(mint)
    rt_floor   = rt["total_friction"]
    entry_sl, entry_tp = compute_adaptive_exits(rt_floor, rv5m_entry)
    # Baseline trades always use fixed exits for clean comparison
    if strategy.startswith("baseline_"):
        entry_sl, entry_tp = EXIT_STOP_LOSS_PCT, EXIT_TAKE_PROFIT_PCT

    conn = get_conn()
    # Migrate entry_sl_pct / entry_tp_pct / entry_rv5m columns if missing
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(shadow_trades_v1)")}
    for col, ctype in [("entry_sl_pct", "REAL"), ("entry_tp_pct", "REAL"), ("entry_rv5m", "REAL")]:
        if col not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE shadow_trades_v1 ADD COLUMN {col} {ctype}")
            except Exception:
                pass
    conn.execute("""
        INSERT INTO shadow_trades_v1
        (trade_id, strategy, mint_address, token_symbol, pair_address,
         entered_at, entry_price_usd, entry_price_native,
         entry_liq_usd, entry_liq_quote_sol, entry_liq_base, entry_k_invariant,
         entry_impact_buy_pct, entry_impact_sell_pct, entry_round_trip_pct,
         entry_jup_rt_pct,
         entry_r_m5, entry_r_h1, entry_buy_count_ratio, entry_vol_accel,
         entry_avg_trade_usd,
         baseline_trigger_id, mode, status,
         lane, age_at_entry_h, liq_usd_at_entry, vol_24h_at_entry,
         pool_type_at_entry, venue_at_entry, spam_flag_at_entry,
         entry_sl_pct, entry_tp_pct, entry_rv5m,
         run_id, git_commit, lane_at_entry, entry_score)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        lane, age_h, liq_usd, vol_24h,
        row.get("pool_type"), row.get("venue"), row.get("spam_flag"),
        round(entry_sl, 4), round(entry_tp, 4), round(rv5m_entry, 6) if rv5m_entry else None,
        _RUN_ID, _GIT_COMMIT, lane, entry_score,
    ))
    conn.commit()
    conn.close()

    # Store adaptive thresholds in memory for fast exit checking
    _adaptive_thresholds[trade_id] = {"sl_pct": entry_sl, "tp_pct": entry_tp}

    logger.info(
        f"OPEN {strategy} {row.get('token_symbol','?')} ({mint[:8]}...) "
        f"lane={lane} age={age_h:.1f}h liq=${liq_usd:,.0f} "
        f"jup_rt={jup_rt*100:.2f}% cpamm_rt={rt['total_friction']*100:.2f}% "
        f"SL={entry_sl:+.2f}% TP={entry_tp:+.2f}% rv5m={rv5m_entry:.4f}%" if rv5m_entry else
        f"OPEN {strategy} {row.get('token_symbol','?')} ({mint[:8]}...) "
        f"lane={lane} age={age_h:.1f}h liq=${liq_usd:,.0f} "
        f"jup_rt={jup_rt*100:.2f}% cpamm_rt={rt['total_friction']*100:.2f}% "
        f"SL={entry_sl:+.2f}% TP={entry_tp:+.2f}% rv5m=warmup"
        + (f" [triggered_by={baseline_trigger_id[:8]}]" if baseline_trigger_id else "")
    )
    return trade_id

def _register_run():
    """P0: Write one row to run_registry at process start."""
    import json
    key_params = json.dumps({
        "mode": MODE,
        "sl": EXIT_STOP_LOSS_PCT,
        "tp": EXIT_TAKE_PROFIT_PCT,
        "timeout_min": EXIT_MAX_HOLD_MINUTES,
        "k_sl": K_SL,
        "k_tp": K_TP,
        "vol_cap": VOL_CAP_PCT,
        "interval_sec": SCORE_RANK_INTERVAL_SEC,
        "r_m5_chase_cap": R_M5_CHASE_CAP,
        "pf_mature_min_age_h": PF_MATURE_MIN_AGE_H,
        "pf_mature_rv5m_max": PF_MATURE_RV5M_MAX,
    })
    lane_gates = f"pumpfun_early=BLOCKED pumpfun_mature=rv5m<={PF_MATURE_RV5M_MAX}% non_pumpfun_mature=OK large_cap_ray=OK"
    try:
        conn = get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO run_registry
            (run_id, git_commit, start_ts, mode, version, lane_gates, key_params)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (_RUN_ID, _GIT_COMMIT, datetime.datetime.utcnow().isoformat(), MODE, "v1.11", lane_gates, key_params))
        conn.commit()
        conn.close()
        logger.info(f"RUN_REGISTRY: registered run_id={_RUN_ID[:8]} version=v1.11 mode={MODE}")
    except Exception as e:
        logger.error(f"run_registry insert failed: {e}")

# ── CLOSE TRADE ──────────────────────────────────────────────────────────────
def close_trade(trade: dict, current: dict, reason: str, cross: dict | None = None):
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

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Overshoot audit
    sl_crossed_at = (cross or {}).get("sl_crossed_at")
    tp_crossed_at = (cross or {}).get("tp_crossed_at")
    threshold_crossed_at = sl_crossed_at if reason == "sl" else (tp_crossed_at if reason == "tp" else None)
    threshold_pct = EXIT_STOP_LOSS_PCT if reason == "sl" else (EXIT_TAKE_PROFIT_PCT if reason == "tp" else None)
    overshoot_pct = None
    overshoot_sec = None
    if threshold_pct is not None:
        overshoot_pct = round((gross_pnl_pct * 100) - threshold_pct, 4)  # negative = overshoot past SL
    if threshold_crossed_at:
        try:
            cross_dt = datetime.fromisoformat(threshold_crossed_at)
            overshoot_sec = round((now - cross_dt).total_seconds(), 1)
        except Exception:
            pass

    conn = get_conn()
    # Poll-gap columns: prev/curr snapshot at first threshold cross
    if reason == "sl":
        prev_poll_at  = (cross or {}).get("sl_prev_poll_at")
        prev_poll_pnl = (cross or {}).get("sl_prev_poll_pnl")
    elif reason == "tp":
        prev_poll_at  = (cross or {}).get("tp_prev_poll_at")
        prev_poll_pnl = (cross or {}).get("tp_prev_poll_pnl")
    else:
        prev_poll_at  = (cross or {}).get("curr_poll_at")
        prev_poll_pnl = (cross or {}).get("curr_poll_pnl")
    curr_poll_at  = (cross or {}).get("curr_poll_at")
    curr_poll_pnl = (cross or {}).get("curr_poll_pnl")
    timeout_skipped = (cross or {}).get("timeout_skipped", 0)

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
            sl_threshold_crossed_at = ?,
            tp_threshold_crossed_at = ?,
            exit_overshoot_pct      = ?,
            exit_overshoot_sec      = ?,
            prev_poll_at            = ?,
            prev_poll_pnl_pct       = ?,
            curr_poll_at            = ?,
            curr_poll_pnl_pct       = ?,
            timeout_skipped_count   = ?,
            gross_pnl_pct           = ?,
            shadow_pnl_pct          = ?,
            shadow_pnl_sol          = ?,
            shadow_pnl_pct_fee025   = ?,
            shadow_pnl_pct_fee060   = ?,
            shadow_pnl_pct_fee100   = ?,
            status                  = 'closed'
        WHERE trade_id = ?
    """, (
        now_iso,
        exit_price, current["price_native"],
        current["liq_usd"], liq_b, current.get("k_invariant"),
        round(rt["sell_slippage"], 6), round(rt["total_friction"], 6),
        reason,
        sl_crossed_at, tp_crossed_at,
        overshoot_pct, overshoot_sec,
        prev_poll_at, round(prev_poll_pnl, 6) if prev_poll_pnl is not None else None,
        curr_poll_at, round(curr_poll_pnl, 6) if curr_poll_pnl is not None else None,
        timeout_skipped,
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

# ── OVERSHOOT TRACKING ───────────────────────────────────────────────────────
# Maps trade_id -> {"sl_crossed_at": ISO, "tp_crossed_at": ISO,
#                   "prev_poll_at": ISO, "prev_poll_pnl": float,
#                   "timeout_skipped": int}
_threshold_cross_times: dict[str, dict] = {}

# ── CHECK EXITS ───────────────────────────────────────────────────────────────
def check_exits(open_trades: list[dict]):
    now_utc = datetime.now(timezone.utc)
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
        hold_min = (now_utc - entered_at).total_seconds() / 60
        trade_id = trade["trade_id"]

        # ── Adaptive SL/TP thresholds (v1.8) ─────────────────────────────────
        # Use in-memory thresholds if available (set at entry).
        # Fall back to DB columns, then fixed floors.
        if trade_id in _adaptive_thresholds:
            sl_threshold = _adaptive_thresholds[trade_id]["sl_pct"]
            tp_threshold = _adaptive_thresholds[trade_id]["tp_pct"]
        else:
            # Recover from DB on restart
            sl_db = trade.get("entry_sl_pct")
            tp_db = trade.get("entry_tp_pct")
            if sl_db is not None and tp_db is not None:
                sl_threshold = sl_db
                tp_threshold = tp_db
                _adaptive_thresholds[trade_id] = {"sl_pct": sl_threshold, "tp_pct": tp_threshold}
            else:
                sl_threshold = EXIT_STOP_LOSS_PCT
                tp_threshold = EXIT_TAKE_PROFIT_PCT

        # Track threshold-cross times and poll-gap data for overshoot audit
        cross = _threshold_cross_times.setdefault(trade_id, {"timeout_skipped": 0})

        # Record prev/curr poll snapshot for poll-gap diagnosis on first threshold cross
        prev_at  = cross.get("prev_poll_at")
        prev_pnl = cross.get("prev_poll_pnl")
        cross["prev_poll_at"]  = cross.get("curr_poll_at", now_utc.isoformat())
        cross["prev_poll_pnl"] = cross.get("curr_poll_pnl", gross_pnl_pct)
        cross["curr_poll_at"]  = now_utc.isoformat()
        cross["curr_poll_pnl"] = gross_pnl_pct

        if gross_pnl_pct <= sl_threshold and "sl_crossed_at" not in cross:
            cross["sl_crossed_at"]  = now_utc.isoformat()
            cross["sl_prev_poll_at"]  = prev_at
            cross["sl_prev_poll_pnl"] = prev_pnl
        if gross_pnl_pct >= tp_threshold and "tp_crossed_at" not in cross:
            cross["tp_crossed_at"]  = now_utc.isoformat()
            cross["tp_prev_poll_at"]  = prev_at
            cross["tp_prev_poll_pnl"] = prev_pnl

        if hold_min >= HARD_MAX_HOLD_MINUTES:
            # Hard max hold — always exit regardless of timeout filter
            close_trade(trade, current, "timeout", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            continue

        if hold_min >= EXIT_MAX_HOLD_MINUTES:
            # Soft timeout: apply fee filter before exiting
            rt_floor = trade.get("entry_round_trip_pct") or 0.006
            min_gross_to_exit = rt_floor + TIMEOUT_MIN_GROSS_BUFFER
            if gross_pnl_pct < min_gross_to_exit and gross_pnl_pct > EXIT_STOP_LOSS_PCT:
                # Extend hold — don't crystallize a fee-negative tiny win
                cross["timeout_skipped"] = cross.get("timeout_skipped", 0) + 1
                logger.debug(
                    f"TIMEOUT_SKIP {trade.get('token_symbol','?')} "
                    f"(skip #{cross['timeout_skipped']}): "
                    f"gross={gross_pnl_pct:+.2f}% < min_exit={min_gross_to_exit*100:.2f}% — extending hold"
                )
                continue
            close_trade(trade, current, "timeout", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            continue
        if gross_pnl_pct >= tp_threshold:
            close_trade(trade, current, "tp", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            continue
        if gross_pnl_pct <= sl_threshold:
            close_trade(trade, current, "sl", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            continue
        if EXIT_LIQ_CLIFF:
            entry_k = trade.get("entry_k_invariant")
            exit_k  = current.get("k_invariant")
            if entry_k and exit_k:
                cliff = k_lp_cliff(entry_k, exit_k, LP_CLIFF_THRESHOLD)
                if cliff["lp_removal_flag"]:
                    close_trade(trade, current, "lp_removal", cross)
                    _threshold_cross_times.pop(trade_id, None)
                    _adaptive_thresholds.pop(trade_id, None)
                    continue

        time.sleep(0.05)

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def run():
    logger.info("=" * 65)
    logger.info("Shadow Trader v1 (Playbook Edition) starting")
    logger.info(f"  Mode:                  {MODE}")
    logger.info(f"  Trade size:            {TRADE_SIZE_SOL} SOL")
    logger.info(f"  Max open/strategy:     {MAX_OPEN_PER_STRATEGY}")
    if MODE == "live_sim_mode":
        logger.info(f"  Max open global:       {MAX_OPEN_GLOBAL}")
    logger.info(f"  Exit TP/SL/timeout:    +{EXIT_TAKE_PROFIT_PCT}% / {EXIT_STOP_LOSS_PCT}% / {EXIT_MAX_HOLD_MINUTES}min (fixed floors)")
    logger.info(f"  Adaptive exits:        {'ENABLED' if ADAPTIVE_EXITS_ENABLED else 'DISABLED'} K_SL={K_SL} K_TP={K_TP} vol_cap={VOL_CAP_PCT}%")
    logger.info(f"  Friction gate (Jup):   <= {FRICTION_GATE_MAX_RT*100:.1f}% RT")
    logger.info(f"  LP cliff threshold:    {LP_CLIFF_THRESHOLD*100:.0f}% k-drop")
    logger.info(f"  Momentum strict:       DISABLED (log-only, falsified)")
    logger.info(f"  Pullback strict:       log-only (not trading)")
    logger.info(f"  pullback_score_rank:   SOLE ACTIVE STRATEGY (interval={SCORE_RANK_INTERVAL_SEC}s top-1/hour)")
    logger.info(f"  Anti-chase filter:     {'ENABLED' if ANTI_CHASE_FILTER_ENABLED else 'DISABLED'} r_m5_cap={R_M5_CHASE_CAP}%")
    logger.info(f"  Lane split (v1.10):    pumpfun_early=BLOCKED pumpfun_mature=ELIGIBLE(rv5m<={PF_MATURE_RV5M_MAX}%) non_pumpfun_mature=OK large_cap_ray=OK")
    logger.info(f"  run_id:                {_RUN_ID}")
    logger.info(f"  git_commit:            {_GIT_COMMIT}")
    logger.info("=" * 65)

    init_tables()
    _register_run()


    # Startup Jupiter health check
    _check_jup_health()

    # Wait for microstructure data
    for _ in range(20):
        rows = get_all_eligible_microstructure()
        if rows:
            logger.info(f"Microstructure ready: {len(rows)} tokens (all eligible)")
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

            # 2. Fresh microstructure — two universes
            strict_rows = get_latest_microstructure()        # CPAMM only, for strict entries
            all_rows    = get_all_eligible_microstructure()  # All eligible, for rank entries

            now_ts = time.time()

            # 3. Expire stale pullback pending confirmations
            expired = [m for m, ts in _pullback_pending.items() if now_ts - ts > PULLBACK_CONFIRM_WINDOW_SEC]
            for m in expired:
                logger.debug(f"Pullback confirmation expired for {m[:8]}")
                del _pullback_pending[m]

            # 4. Strict entries (CPAMM universe only)
            mom_signals = 0
            mom_opened  = 0
            pull_signals = 0
            pull_opened  = 0

            for row in strict_rows:
                mint = row.get("mint_address")
                if not mint:
                    continue

                # ── Momentum strict ──
                if should_enter_momentum_strict(row):
                    mom_signals += 1
                    tid = open_trade("momentum_strict", row)
                    if tid:
                        mom_opened += 1
                        # Matched baseline
                        if passes_position_cap("baseline_matched_momentum_strict"):
                            baseline_row = random.choice(strict_rows)
                            open_trade("baseline_matched_momentum_strict", baseline_row, baseline_trigger_id=tid)

                # ── Pullback strict (two-stage) ──
                if mint in _pullback_pending:
                    # Confirmation stage
                    if should_confirm_pullback(row):
                        del _pullback_pending[mint]
                        pull_signals += 1
                        tid = open_trade("pullback_strict", row)
                        if tid:
                            pull_opened += 1
                            # Matched baseline
                            if passes_position_cap("baseline_matched_pullback_strict"):
                                baseline_row = random.choice(strict_rows)
                                open_trade("baseline_matched_pullback_strict", baseline_row, baseline_trigger_id=tid)
                else:
                    # Initial signal stage
                    if should_enter_pullback_initial(row):
                        _pullback_pending[mint] = now_ts
                        pull_signals += 1
                        logger.debug(f"Pullback initial signal for {row.get('token_symbol','?')} ({mint[:8]}), awaiting confirmation")

            # Log strict signal frequency
            if strict_rows:
                log_signal_frequency("momentum_strict", mom_signals, mom_opened, len(strict_rows))
                log_signal_frequency("pullback_strict", pull_signals, pull_opened, len(strict_rows))

            # 5. Score/rank: pullback_score_rank ONLY (v1.9 sole active strategy)
            if SCORE_RANK_ENABLED and all_rows:
                try:
                    maybe_fire_rank_entry("pullback_score_rank", all_rows, score_pullback_v19)
                except Exception as rank_e:
                    logger.error(f"Score/rank error: {rank_e}", exc_info=True)

            # 6. Log filter scan counts every cycle (P4)
            _filter_scan_counts["evaluated"] = len(all_rows)
            log_filter_scan(_filter_scan_counts)
            # Reset per-cycle counters (keep evaluated as running total)
            for k in list(_filter_scan_counts.keys()):
                if k != "evaluated":
                    _filter_scan_counts[k] = 0

            # Periodic status log
            if int(now_ts) % 300 < POLL_INTERVAL_SEC:  # ~every 5 min
                logger.info(
                    f"STATUS: strict_universe={len(strict_rows)} all_eligible={len(all_rows)} "
                    f"open_trades={len(get_open_trades())} "
                    f"jup_api={'OK' if _jupiter_api_available else 'FALLBACK'}"
                )

        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)

        elapsed = time.time() - loop_start
        # Adaptive sleep: poll faster when any trade is near SL/TP
        open_now = get_open_trades()
        near_exit = False
        for t in open_now:
            ep = t.get("entry_price_usd", 0)
            if ep > 0:
                # We don't have current price here without fetching, so use fast poll
                # whenever any position is open (conservative but safe)
                near_exit = True
                break
        interval = POLL_INTERVAL_NEAR_EXIT_SEC if near_exit else POLL_INTERVAL_SEC
        time.sleep(max(1, interval - elapsed))

if __name__ == "__main__":
    run()
