#!/usr/bin/env python3
""""et_shadow_trader_v1.py — ET v1 Paper Trading Harness (Playbook Edition) v1.19

v1.19 additions (2026-02-26):
  - duration_sec + poll_count: tracked in-memory per trade, written to DB on close.
    Report flags any SL/timeout exit with duration_sec < 60s.
  - forced_close + exit_reason_effective: when a strategy leg closes, its paired
    baseline (if still open) is immediately closed with exit_reason_effective=
    'forced_pair_close'. forced_close=1 stored in DB. Baseline's own exit_reason
    is preserved; effective reason used in report display.
  - Price sanity check (robust): native-to-native comparison at open.
    dex_price_native (SOL/token from DexScreener priceNative) vs
    jup_exec_price_native = (inAmount_lamports/1e9) / (outAmount_raw/10^decimals).
    Decimals from get_mint_decimals(): Jupiter Tokens V2 API -> RPC getTokenSupply fallback.
    Amounts cast to int (Jupiter returns strings). Decimal math (no float drift).
    jup_exec_vs_dex_pct = jup_exec_price_native/dex_price_native - 1.
    price_mismatch=1 if |jup_exec_vs_dex_pct| > 2% AND lane=large_cap_ray.
    Route identity (label, ammKey, contextSlot) logged on mismatch.
    If decimals unavailable: skip mismatch flag, keep trading.
    entry_jup_implied_price column stores jup_exec_price_native (SOL/token).

v1.18 additions (2026-02-26):
  - MFE/MAE correctness: _mfe_mae now stores entry_price, max_price_seen, min_price_seen
    (absolute USD). mfe_gross_pct = max_price/entry-1, mae_gross_pct = min_price/entry-1.
    Report can prove MFE/MAE from price path (5 sample trades show entry/max/min/mfe/mae).
  - MFE_net columns: mfe_net_dex_pct (vs DEX floor = rt+0.006) and mfe_net_fee100_pct
    (vs fee100 floor = rt+0.01) stored alongside mfe_gross_pct.
  - lp_removal audit log: new lp_removal_log table captures liq_before, liq_after,
    pct_drop, k_before, k_after, k_change_pct, pool_type, venue, and Jupiter
    quote status (re-quote attempted at trigger: route_ok, jup_rt_pct).
  - Token identity: mint_prefix (first 8 chars) stored in shadow_trades_v1.
    All OPEN/CLOSE log lines use SYMBOL(mint_prefix) format.
v1.17 additions (2026-02-26):
  - MFE/MAE tracking: mfe_gross_pct and mae_gross_pct tracked in-memory per poll,
    written to DB on close. NULL for pre-v1.17 rows (no backfill).
  - Schema migration: ALTER TABLE adds mfe_gross_pct REAL, mae_gross_pct REAL.
  - Version bump in run_registry (v1.16 -> v1.17) and signature hash.

v1.14 additions (2026-02-26):
  - Rollover cleanup on startup: open trades from old run_ids are closed with
    exit_reason=rollover_close (excluded from reports)
  - Position cap log now shows blocking trade_id + run_id + age_minutes
  - Rejection reason primary counts added to selection_tick_log

v1.13 additions (2026-02-26):
  - TRUE atomic pairing: if baseline open_trade fails, strategy trade is ROLLED BACK
    (deleted from DB) so no unpaired strategy trades ever exist.
  - Lane sub-reason diagnostics: selection_tick_log now has separate columns for
    rej_lane_age, rej_lane_liq, rej_lane_vol, rej_lane_pf_early (DB migration added).
  - Stall diagnostics: when tradeable=0, log one example token with its blocking reason.
  - Report: all pnl fields stored as decimal fractions; display must multiply by 100.
  - Report: run_id filter is mandatory (no silent ALL-runs aggregation).
  - Report: n_closed_pairs computed by join on baseline_trigger_id, not min().
  - Tick reason: 'pair_open_baseline_pending' when baseline still open.

v1.12 additions:
  - selection_tick_log: one heartbeat row per 15-min interval with eligible_count,
    tradeable_count, top_token, top_score, opened_trade_bool, reason_no_trade, rejection counts
  - Tradeable set E: pre-validate all gates (lane+rug+vol+friction+Jupiter quote) before scoring
  - Atomic pair open: baseline chosen from E\\{strategy}; if |E|<2, no trade
  - Baseline bypasses ALL position caps and already-open checks (is_baseline flag)
  - No min-score threshold in research_mode; always trade top-1 from E

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
from config.config import DB_PATH, LOGS_DIR, JUPITER_API_KEY, JUPITER_BASE_URL, RPC_URL
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

# ── FAST_RISK_GATE (v1.19, feature-flag, default OFF) ────────────────────────
# When ON: rejects candidates whose mint is in the fast_blacklist table.
# A mint is added to fast_blacklist when a strategy leg closes SL with
# duration_sec < 60s. It stays blacklisted for FAST_BLACKLIST_DURATION_H hours.
# This converts post-hoc FAST exclusion into a prospective, testable rule.
# Deploy under a NEW signature by setting this to True in config.
# Current run (sig=01f9bdf7d0385d0d) keeps this OFF until n_pairs=50.
FAST_RISK_GATE_ENABLED      = False
FAST_BLACKLIST_DURATION_H   = 12   # hours a mint stays blacklisted after FAST SL
# ── MIN_SCORE_TO_TRADE (v1.19, feature-flag, default None = OFF) ─────────────────
# When set to a float, a tick is skipped entirely unless the top candidate's
# pullback_score_rank score >= this threshold.
# Goal: filter out low-confidence setups and focus capital on high-score entries.
# Pre-registered for post-n=50 experiment. Deploy under a NEW signature.
# Current run (sig=01f9bdf7d0385d0d) keeps this None until n_pairs=50.
# Example: MIN_SCORE_TO_TRADE = 5.0  (top ~33% of observed scores)
MIN_SCORE_TO_TRADE          = None   # float or None; None = OFF (no score filter)
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
    # v1.12: selection_tick_log heartbeat
    try:
        c.execute("""
        CREATE TABLE IF NOT EXISTS selection_tick_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at           TEXT    NOT NULL,
            run_id              TEXT,
            eligible_count      INTEGER,
            tradeable_count     INTEGER,
            top_token           TEXT,
            top_score           REAL,
            opened_trade_bool   INTEGER DEFAULT 0,
            reason_no_trade     TEXT,
            rej_lane_age        INTEGER DEFAULT 0,
            rej_lane_liq        INTEGER DEFAULT 0,
            rej_lane_vol        INTEGER DEFAULT 0,
            rej_lane_pf_early   INTEGER DEFAULT 0,
            rej_anti_chase      INTEGER DEFAULT 0,
            rej_friction        INTEGER DEFAULT 0,
            rej_vol_cap         INTEGER DEFAULT 0,
            rej_rug             INTEGER DEFAULT 0,
            rej_jup_fail        INTEGER DEFAULT 0,
            rej_pf_stability    INTEGER DEFAULT 0,
            stall_example_token TEXT,
            stall_example_reason TEXT,
            best_token TEXT,
            best_score REAL,
            best_block_reason TEXT,
            whatif_no_pf_stability  INTEGER DEFAULT 0,
            whatif_no_anti_chase    INTEGER DEFAULT 0,
            whatif_no_pf_early      INTEGER DEFAULT 0,
            whatif_no_lane_liq      INTEGER DEFAULT 0,
            whatif_no_lane_vol      INTEGER DEFAULT 0
        )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_stl_at ON selection_tick_log(logged_at, run_id)")
    except Exception:
        pass
    # v1.13: migrate existing selection_tick_log to add sub-reason columns if missing
    stl_existing = {r[1] for r in c.execute("PRAGMA table_info(selection_tick_log)").fetchall()}
    for col, ctype in [
        ("rej_lane_age",       "INTEGER DEFAULT 0"),
        ("rej_lane_liq",       "INTEGER DEFAULT 0"),
        ("rej_lane_vol",       "INTEGER DEFAULT 0"),
        ("rej_lane_pf_early",  "INTEGER DEFAULT 0"),
        ("rej_anti_chase",     "INTEGER DEFAULT 0"),
        ("rej_friction",       "INTEGER DEFAULT 0"),
        ("rej_vol_cap",        "INTEGER DEFAULT 0"),
        ("rej_rug",            "INTEGER DEFAULT 0"),
        ("rej_jup_fail",       "INTEGER DEFAULT 0"),
        ("rej_pf_stability",   "INTEGER DEFAULT 0"),
        ("stall_example_token",  "TEXT"),
        ("stall_example_reason", "TEXT"),
        ("best_token",                "TEXT"),
        ("best_score",                "REAL"),
        ("best_block_reason",         "TEXT"),
        ("whatif_no_pf_stability",    "INTEGER DEFAULT 0"),
        ("whatif_no_anti_chase",      "INTEGER DEFAULT 0"),
        ("whatif_no_pf_early",        "INTEGER DEFAULT 0"),
        ("whatif_no_lane_liq",        "INTEGER DEFAULT 0"),
        ("whatif_no_lane_vol",        "INTEGER DEFAULT 0"),
    ]:
        if col not in stl_existing:
            try:
                c.execute(f"ALTER TABLE selection_tick_log ADD COLUMN {col} {ctype}")
            except Exception:
                pass
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
        # v1.17 columns
        ("mfe_gross_pct",      "REAL"),   # max favorable excursion (decimal fraction)
        ("mae_gross_pct",      "REAL"),   # max adverse excursion (decimal fraction)
        # v1.18 columns
        ("mfe_net_dex_pct",    "REAL"),   # MFE net of DEX floor (rt+0.006)
        ("mfe_net_fee100_pct", "REAL"),   # MFE net of fee100 floor (rt+0.01)
        ("max_price_seen",     "REAL"),   # highest price_usd seen during hold
        ("min_price_seen",     "REAL"),   # lowest price_usd seen during hold
        ("mint_prefix",        "TEXT"),   # first 8 chars of mint_address for display
        # v1.19 columns
        ("duration_sec",       "REAL"),   # seconds from entered_at to exited_at
        ("poll_count",         "INTEGER"),# number of check_exits polls during hold
        ("forced_close",       "INTEGER"),# 1 if baseline was force-closed by strategy exit
        ("exit_reason_effective", "TEXT"),# 'forced_pair_close' for forced baseline, else = exit_reason
        ("entry_jup_implied_price", "REAL"),# Jupiter exec priceNative (SOL/token) at entry — native-to-native check
        ("price_mismatch",     "INTEGER"),# 1 if |jup_exec_native/dex_native - 1| > 2% AND lane=large_cap_ray
        ("jup_price_unit_native_ok", "INTEGER"),# 1 = native-to-native method used (real decimals, direction enforced); 0 = pre-fix or fallback
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
    # v1.18: lp_removal_log — one row per lp_removal exit trigger
    c.execute("""
    CREATE TABLE IF NOT EXISTS fast_blacklist (
        mint_address    TEXT NOT NULL,
        blacklisted_at  TEXT NOT NULL,
        expires_at      TEXT NOT NULL,
        reason          TEXT,
        PRIMARY KEY (mint_address, blacklisted_at)
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS lp_removal_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        logged_at       TEXT    NOT NULL,
        trade_id        TEXT    NOT NULL,
        run_id          TEXT,
        mint_address    TEXT,
        token_symbol    TEXT,
        mint_prefix     TEXT,
        pool_type       TEXT,
        venue           TEXT,
        liq_before_usd  REAL,
        liq_after_usd   REAL,
        liq_pct_drop    REAL,
        k_before        REAL,
        k_after         REAL,
        k_change_pct    REAL,
        jup_route_ok    INTEGER,
        jup_rt_pct      REAL,
        gross_pnl_pct   REAL
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_lpl_trade ON lp_removal_log(trade_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lpl_at ON lp_removal_log(logged_at)")
    # v1.11 P0: run_registry — one row per process start, for run isolation
    c.execute("""
    CREATE TABLE IF NOT EXISTS run_registry (
        run_id          TEXT    PRIMARY KEY,
        git_commit      TEXT,
        start_ts        TEXT    NOT NULL,
        mode            TEXT,
        version         TEXT,
        lane_gates      TEXT,
        key_params      TEXT,
        signature       TEXT
    )
    """)

    # v1.11 P4: invalid_pair column on shadow_trades_v1
    try:
        c.execute("ALTER TABLE shadow_trades_v1 ADD COLUMN invalid_pair INTEGER DEFAULT 0")
    except Exception:
        pass
    # v1.15: signature column on run_registry
    try:
        c.execute("ALTER TABLE run_registry ADD COLUMN signature TEXT")
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

def log_selection_tick(eligible_count: int, tradeable_count: int, top_token: str | None,
                       top_score: float | None, opened: bool, reason_no_trade: str | None,
                       rej: dict, stall_example: tuple | None = None,
                       best_token: str | None = None, best_score: float | None = None,
                       best_block_reason: str | None = None,
                       whatif: dict | None = None):
    """v1.13+: Write one heartbeat row per selection interval to selection_tick_log.
    stall_example: (token_symbol, reason_str) for the first token that failed the gate.
    best_token/best_score/best_block_reason: highest-scoring eligible token even when
    no tradeable tokens exist — populated on zero-open ticks for diagnostics.
    whatif: dict of what-if gate counter results, e.g.
      {'no_pf_stability': 3, 'no_anti_chase': 2, ...}
    """
    wi = whatif or {}
    try:
        conn = get_conn()
        ex_tok = stall_example[0] if stall_example else None
        ex_rsn = stall_example[1] if stall_example else None
        conn.execute("""
            INSERT INTO selection_tick_log
            (logged_at, run_id, eligible_count, tradeable_count, top_token, top_score,
             opened_trade_bool, reason_no_trade,
             rej_lane_age, rej_lane_liq, rej_lane_vol, rej_lane_pf_early,
             rej_anti_chase, rej_friction, rej_vol_cap, rej_rug, rej_jup_fail, rej_pf_stability,
             stall_example_token, stall_example_reason,
             best_token, best_score, best_block_reason,
             whatif_no_pf_stability, whatif_no_anti_chase, whatif_no_pf_early,
             whatif_no_lane_liq, whatif_no_lane_vol)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            datetime.now(timezone.utc).isoformat(), _RUN_ID,
            eligible_count, tradeable_count, top_token, top_score,
            1 if opened else 0, reason_no_trade,
            rej.get("lane_age", 0), rej.get("lane_liq", 0), rej.get("lane_vol", 0), rej.get("lane_pf_early", 0),
            rej.get("anti_chase", 0), rej.get("friction", 0), rej.get("vol_cap", 0),
            rej.get("rug", 0), rej.get("jup_fail", 0), rej.get("pf_stability", 0),
            ex_tok, ex_rsn,
            best_token, best_score, best_block_reason,
            wi.get("no_pf_stability"), wi.get("no_anti_chase"), wi.get("no_pf_early"),
            wi.get("no_lane_liq"), wi.get("no_lane_vol"),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"selection_tick_log write error: {e}")

# ── LANE CLASSIFICATION ──────────────────────────────────────────────────────
# Hard gates: tokens must pass ALL to be eligible for any strategy entry.
# These are enforced in open_trade() before the friction gate.
LANE_GATE_MIN_AGE_H    = 4.0       # hours — exclude fresh graduates
LANE_GATE_MIN_LIQ_USD  = 100_000   # USD — minimum liquidity
LANE_GATE_MIN_VOL_24H  = 250_000   # USD — minimum 24h volume

# ── ANCHOR MINT LIST ─────────────────────────────────────────────────────────
# Always-scanned mature tokens that bypass the universe scanner's eligible gate.
# These are high-liquidity, non-pumpfun tokens that should always be in the
# tradeable universe. Add/remove as needed.
ANCHOR_MINTS = {
    # Large-cap Raydium (age >= 30d, liq >= 1M)
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # $WIF
    "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",   # BOME
    "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",  # POPCAT
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # Bonk
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",   # JUP
    "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4",  # RAY
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # WETH (Wormhole)
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",  # PYTH
    "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",  # WBTC (Wormhole)
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",   # ORCA
    "A9mUU4qviSctJVPJdBJWkb28deg915LYJKrzQ19ji3FM",   # USDCet
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "So11111111111111111111111111111111111111112",     # SOL (wrapped)
}

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


# ── Mint decimals cache + resolver ──────────────────────────────────────────────
# Used by the native-to-native price mismatch check.
# Negative cache prevents repeated lookups for mints that consistently fail.
MINT_DECIMALS_CACHE:    dict[str, int]   = {}  # mint -> decimals
MINT_DECIMALS_NEGCACHE: dict[str, float] = {}  # mint -> last_fail_ts

def get_mint_decimals(mint: str) -> int | None:
    """Return token decimals for `mint`.
    1) Positive cache hit.
    2) Negative cache: skip if failed within last 300s.
    3) Jupiter Tokens V2 search (lite-api, preferred).
    4) Solana RPC getTokenSupply fallback (Helius if configured).
    Returns None if both sources fail; caller skips mismatch classification.
    """
    import time
    if mint in MINT_DECIMALS_CACHE:
        return MINT_DECIMALS_CACHE[mint]

    # avoid spamming recently-failed mints
    last_fail = MINT_DECIMALS_NEGCACHE.get(mint)
    if last_fail is not None and (time.time() - last_fail) < 300:
        return None

    # Option A: Jupiter Tokens V2 search (lite-api, no auth required but key accepted)
    try:
        r = requests.get(
            "https://lite-api.jup.ag/tokens/v2/search",
            params={"query": mint},
            headers={"x-api-key": JUPITER_API_KEY},
            timeout=5,
        )
        if r.status_code == 200:
            arr = r.json() or []
            hit = next(
                (x for x in arr if x.get("id") == mint or x.get("address") == mint),
                None,
            )
            if hit is not None:
                decimals = int(hit.get("decimals", -1))
                if decimals >= 0:
                    MINT_DECIMALS_CACHE[mint] = decimals
                    return decimals
    except Exception:
        pass

    # Option B: Solana RPC getTokenSupply (Helius if configured, else public mainnet)
    try:
        rpc_url = RPC_URL or "https://api.mainnet-beta.solana.com"
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]}
        r = requests.post(rpc_url, json=payload, timeout=5)
        if r.status_code == 200:
            result = (r.json() or {}).get("result") or {}
            decimals = int(((result.get("value") or {}).get("decimals", -1)))
            if decimals >= 0:
                MINT_DECIMALS_CACHE[mint] = decimals
                return decimals
    except Exception:
        pass

    MINT_DECIMALS_NEGCACHE[mint] = time.time()
    return None


def get_jupiter_rt_estimate(
    mint: str,
    liq_base: float = 0,
    liq_quote_sol: float = 0,
    cpamm_valid: bool = True,
    return_price: bool = False,
) -> "float | None | tuple":
    """
    Returns total RT friction fraction (e.g. 0.008 = 0.8%) or None if no route.
    If return_price=True, returns (rt_fraction, jup_quote_data) or (None, None).
    jup_quote_data is a dict with keys: inAmount (lamports), outAmount (raw token units),
    route_label, amm_key, context_slot — used by caller for native-to-native price comparison.
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
                return (None, None) if return_price else None
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
                rt_final = max(rt_pct, 0.0)
                if return_price:
                    # Return raw quote amounts + route identity for native-to-native price check.
                    # Caller computes: jup_exec_price_native = (inAmount/1e9) / (outAmount/10^decimals)
                    # and compares to DexScreener priceNative (SOL per token).
                    swap_info = route_plan[0].get("swapInfo", {}) if route_plan else {}
                    jup_quote_data = {
                        "inAmount":     int(data.get("inAmount") or sol_in_lamports),
                        "outAmount":    int(data.get("outAmount") or 0),
                        "inputMint":    data.get("inputMint", WSOL_MINT),
                        "outputMint":   data.get("outputMint", mint),
                        "routePlan":    route_plan,
                        "contextSlot":  int(data.get("contextSlot") or 0),
                        # legacy flat keys kept for backward compat
                        "route_label":  swap_info.get("label", "?"),
                        "amm_key":      swap_info.get("ammKey", "?"),
                        "context_slot": int(data.get("contextSlot") or 0),
                    }
                    return rt_final, jup_quote_data
                return rt_final
        except requests.exceptions.Timeout:
            logger.debug(f"Jupiter timeout for {mint[:8]}")
        except Exception as e:
            logger.debug(f"Jupiter error for {mint[:8]}: {e}")

    # Jupiter unavailable — pool-type determines fallback behaviour
    if not cpamm_valid:
        # CLMM/DLMM: CPAMM math is wrong for these pools. Block the trade.
        logger.debug(f"SKIP {mint[:8]}: Jupiter unavailable and pool is not CPAMM — no safe friction estimate")
        return (None, None) if return_price else None
    # CPAMM fallback: use CPAMM math + accurate DEX fee (0.50% RT = 0.25% each way)
    if liq_base > 0 and liq_quote_sol > 0:
        rt = cpamm_round_trip(TRADE_SIZE_SOL, liq_base, liq_quote_sol)
        cpamm_rt = rt["total_friction"] + 0.005  # 0.50% RT DEX fee (Raydium CPAMM)
        logger.debug(f"CPAMM fallback RT for {mint[:8]}: {cpamm_rt*100:.2f}%")
        val = min(cpamm_rt, 0.05)
        return (val, None) if return_price else val  # no Jupiter impact available in fallback
    else:
        # No liquidity data and no Jupiter — conservative estimate for CPAMM
        return (0.008, None) if return_price else 0.008

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

def _check_tradeable(row: dict) -> tuple[bool, str]:
    """
    v1.12: Pre-validate all gates for a token (for strategy, not baseline).
    Returns (tradeable: bool, reason: str).
    Checks: lane, age, liq, vol, anti-chase, rug, pf_mature_stability, vol_cap, Jupiter.
    Does NOT check position cap (that's strategy-level).
    """
    lane = classify_lane(row)
    if lane == "pumpfun_early":
        return False, "lane:pumpfun_early"
    age_h   = row.get("age_hours") or 0
    liq_usd = row.get("liq_usd") or 0
    vol_24h = row.get("vol_h24") or 0
    if age_h < LANE_GATE_MIN_AGE_H:
        return False, "lane:age"
    if liq_usd < LANE_GATE_MIN_LIQ_USD:
        return False, "lane:liq"
    if vol_24h < LANE_GATE_MIN_VOL_24H:
        return False, "lane:vol"
    # Anti-chase
    if ANTI_CHASE_FILTER_ENABLED:
        r_m5 = row.get("r_m5") or 0
        if r_m5 > R_M5_CHASE_CAP:
            return False, "anti_chase"
    # Rug risk
    if RUG_FILTER_ENABLED:
        is_risky, rug_reason = check_rug_risk(row, "pullback_score_rank")
        if is_risky:
            return False, f"rug:{rug_reason}"
    # pumpfun_mature stability gates
    if lane == "pumpfun_mature":
        rv5m_check = row.get("rv_5m")
        if rv5m_check is None:
            return False, "pf_stability:rv5m_missing"
        if rv5m_check > PF_MATURE_RV5M_MAX:
            return False, f"pf_stability:rv5m={rv5m_check:.3f}%>{PF_MATURE_RV5M_MAX}%"
        range5m = row.get("range_5m")
        if range5m is not None and rv5m_check > 0 and range5m > PF_MATURE_RANGE_MULT * rv5m_check:
            return False, f"pf_stability:range_5m={range5m:.3f}%>{PF_MATURE_RANGE_MULT}xrv5m"
    # Vol cap
    if ADAPTIVE_EXITS_ENABLED:
        mint = row.get("mint_address", "")
        rv5m = get_rv5m_for_mint(mint)
        if rv5m is not None and (K_SL * rv5m) > VOL_CAP_PCT:
            return False, f"vol_cap:{K_SL*rv5m:.2f}%>{VOL_CAP_PCT}%"
    # Jupiter friction gate — use cached round_trip_pct from universe_snapshot
    # (universe scanner already validated Jupiter friction; no need to re-call at trade time)
    cached_rt = row.get("round_trip_pct")
    if cached_rt is None:
        # No cached RT — fall back to live Jupiter call
        mint = row.get("mint_address", "")
        liq_b = row.get("liq_base") or 0
        liq_q = row.get("liq_quote_sol") or 0
        cpamm_valid = bool(row.get("cpamm_valid_flag", 1))
        jup_rt = get_jupiter_rt_estimate(mint, liq_b, liq_q, cpamm_valid=cpamm_valid)
        if jup_rt is None:
            return False, "jup:no_route"
        if jup_rt > FRICTION_GATE_MAX_RT:
            return False, f"jup:rt={jup_rt*100:.2f}%>{FRICTION_GATE_MAX_RT*100:.1f}%"
    else:
        if cached_rt > FRICTION_GATE_MAX_RT:
            return False, f"jup:rt={cached_rt*100:.2f}%>{FRICTION_GATE_MAX_RT*100:.1f}%"
    # FAST_RISK_GATE (feature-flag, default OFF)
    if FAST_RISK_GATE_ENABLED:
        mint = row.get("mint_address", "")
        if mint and _is_fast_blacklisted(mint):
            return False, "fast_blacklist"
    return True, "ok"

def _is_fast_blacklisted(mint: str) -> bool:
    """Return True if mint is currently in the fast_blacklist (not expired)."""
    try:
        conn = get_conn()
        now_iso = datetime.now(timezone.utc).isoformat()
        row = conn.execute(
            "SELECT 1 FROM fast_blacklist WHERE mint_address=? AND expires_at > ? LIMIT 1",
            (mint, now_iso)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False

def add_to_fast_blacklist(mint: str, reason: str = "fast_sl"):
    """Add mint to fast_blacklist for FAST_BLACKLIST_DURATION_H hours.
    Called when a strategy leg closes SL with duration_sec < 60s.
    No-op when FAST_RISK_GATE_ENABLED is False (records for observability only).
    """
    try:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=FAST_BLACKLIST_DURATION_H)
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO fast_blacklist (mint_address, blacklisted_at, expires_at, reason) "
            "VALUES (?, ?, ?, ?)",
            (mint, now.isoformat(), expires.isoformat(), reason)
        )
        conn.commit()
        conn.close()
        logger.info(f"FAST_BLACKLIST add mint={mint[:8]} expires={expires.isoformat()[:16]} reason={reason}")
    except Exception as e:
        logger.warning(f"FAST_BLACKLIST insert failed: {e}")

def _count_tradeable_without(all_rows: list[dict], skip_gate: str) -> int:
    """Instrumentation only — count how many tokens from all_rows would pass
    _check_tradeable if exactly one gate is disabled.  Does NOT affect trading.
    skip_gate must be one of: 'pf_stability', 'anti_chase', 'pf_early',
    'lane_liq', 'lane_vol'.
    """
    count = 0
    for row in all_rows:
        lane = classify_lane(row)
        # pf_early gate
        if lane == "pumpfun_early":
            if skip_gate == "pf_early":
                pass  # pretend this gate doesn't exist
            else:
                continue
        age_h   = row.get("age_hours") or 0
        liq_usd = row.get("liq_usd") or 0
        vol_24h = row.get("vol_h24") or 0
        if age_h < LANE_GATE_MIN_AGE_H:
            continue  # age gate is never skipped
        if liq_usd < LANE_GATE_MIN_LIQ_USD:
            if skip_gate != "lane_liq":
                continue
        if vol_24h < LANE_GATE_MIN_VOL_24H:
            if skip_gate != "lane_vol":
                continue
        if ANTI_CHASE_FILTER_ENABLED and skip_gate != "anti_chase":
            r_m5 = row.get("r_m5") or 0
            if r_m5 > R_M5_CHASE_CAP:
                continue
        if RUG_FILTER_ENABLED:
            is_risky, _ = check_rug_risk(row, "pullback_score_rank")
            if is_risky:
                continue  # rug gate is never skipped
        if lane == "pumpfun_mature" and skip_gate != "pf_stability":
            rv5m_check = row.get("rv_5m")
            if rv5m_check is None:
                continue
            if rv5m_check > PF_MATURE_RV5M_MAX:
                continue
            range5m = row.get("range_5m")
            if range5m is not None and rv5m_check > 0 and range5m > PF_MATURE_RANGE_MULT * rv5m_check:
                continue
        if ADAPTIVE_EXITS_ENABLED:
            mint = row.get("mint_address", "")
            rv5m = get_rv5m_for_mint(mint)
            if rv5m is not None and (K_SL * rv5m) > VOL_CAP_PCT:
                continue  # vol_cap gate is never skipped
        # Jupiter friction (use cached RT, skip live call for speed)
        cached_rt = row.get("round_trip_pct")
        if cached_rt is not None and cached_rt > FRICTION_GATE_MAX_RT:
            continue  # friction gate is never skipped
        count += 1
    return count


def maybe_fire_rank_entry(strategy: str, all_rows: list[dict], score_fn) -> str | None:
    """
    v1.12: Build tradeable set E, require |E|>=2, pick strategy=top-score,
    baseline=random from E\\{strategy}. Open both atomically.
    Writes selection_tick_log heartbeat every interval regardless of outcome.
    """
    if not SCORE_RANK_ENABLED:
        return None
    if strategy not in ("pullback_score_rank", "baseline_matched_pullback_score_rank"):
        return None
    now = time.time()
    last = _last_rank_entry.get(strategy, 0)
    if now - last < SCORE_RANK_INTERVAL_SEC:
        return None  # Not time yet
    _last_rank_entry[strategy] = now

    # ── Build tradeable set E ──────────────────────────────────────────────────
    eligible_rows = [r for r in all_rows if classify_lane(r) != "pumpfun_early"]
    pf_early_count = sum(1 for r in all_rows if classify_lane(r) == "pumpfun_early")
    rej_counts = {"lane_age": 0, "lane_liq": 0, "lane_vol": 0, "lane_pf_early": pf_early_count,
                  "anti_chase": 0, "friction": 0, "vol_cap": 0, "rug": 0, "jup_fail": 0, "pf_stability": 0}
    tradeable_set = []
    # v1.13: capture first stall example (token + reason) for diagnostics
    stall_example: tuple | None = None
    for r in eligible_rows:
        ok, reason = _check_tradeable(r)
        if ok:
            tradeable_set.append(r)
        else:
            sym = r.get("token_symbol", "?")
            if stall_example is None:
                stall_example = (sym, reason)
            if reason == "lane:age":
                rej_counts["lane_age"] += 1
            elif reason == "lane:liq":
                rej_counts["lane_liq"] += 1
            elif reason == "lane:vol":
                rej_counts["lane_vol"] += 1
            elif reason == "lane:pumpfun_early":
                rej_counts["lane_pf_early"] += 1
            elif reason.startswith("lane"):
                rej_counts["lane_age"] += 1  # fallback
            elif reason == "anti_chase":
                rej_counts["anti_chase"] += 1
            elif reason.startswith("jup"):
                rej_counts["jup_fail"] += 1
            elif reason.startswith("vol_cap"):
                rej_counts["vol_cap"] += 1
            elif reason.startswith("rug"):
                rej_counts["rug"] += 1
            elif reason.startswith("pf_stability"):
                rej_counts["pf_stability"] += 1
            else:
                rej_counts["friction"] += 1

    # ── Log diagnostics ────────────────────────────────────────────────────────
    if tradeable_set:
        scored = [(score_fn(r), r) for r in tradeable_set]
        scored.sort(key=lambda x: x[0], reverse=True)
        top3_str = "  ".join(
            f"{r.get('token_symbol','?')}(sc={sc:.2f} r_m5={r.get('r_m5') or 0:.2f}%)"
            for sc, r in scored[:3]
        )
        logger.info(
            f"RANK {strategy}: tradeable={len(tradeable_set)}/{len(eligible_rows)} "
            f"eligible={len(all_rows)} top-3=[{top3_str}] "
            f"rej=age:{rej_counts['lane_age']} liq:{rej_counts['lane_liq']} vol:{rej_counts['lane_vol']} pf_early:{rej_counts['lane_pf_early']} "
            f"anti_chase:{rej_counts['anti_chase']} jup:{rej_counts['jup_fail']} vol_cap:{rej_counts['vol_cap']} rug:{rej_counts['rug']} pf_stab:{rej_counts['pf_stability']}"
        )
    else:
        # Compute best_token/best_score/best_block_reason from eligible_rows for diagnostics
        _best_diag_token = None
        _best_diag_score = None
        _best_diag_block = None
        if eligible_rows:
            _scored_elig = sorted(
                [(score_fn(r), r) for r in eligible_rows],
                key=lambda x: x[0], reverse=True
            )
            _best_diag_score, _best_diag_row = _scored_elig[0]
            _best_diag_token = _best_diag_row.get("token_symbol", "?")
            _, _best_diag_block = _check_tradeable(_best_diag_row)
        logger.info(
            f"RANK {strategy}: NO TRADEABLE TOKENS "
            f"(eligible={len(eligible_rows)} universe={len(all_rows)} "
            f"best={_best_diag_token} sc={f'{_best_diag_score:.4f}' if _best_diag_score is not None else 'N/A'} block={_best_diag_block} "
            f"rej=age:{rej_counts['lane_age']} liq:{rej_counts['lane_liq']} vol:{rej_counts['lane_vol']} pf_early:{rej_counts['lane_pf_early']} "
            f"anti_chase:{rej_counts['anti_chase']} jup:{rej_counts['jup_fail']} vol_cap:{rej_counts['vol_cap']} rug:{rej_counts['rug']} pf_stab:{rej_counts['pf_stability']})"
        )
        # Near-miss top-5: show tokens closest to passing, sorted by liq_usd desc
        near_miss = sorted(eligible_rows, key=lambda r: r.get("liq_usd") or 0, reverse=True)[:5]
        for nm in near_miss:
            sym = nm.get("token_symbol", "?")
            age_h_nm = nm.get("age_hours") or 0
            liq_nm = nm.get("liq_usd") or 0
            vol_nm = nm.get("vol_h24") or 0
            r_m5_nm = nm.get("r_m5") or 0
            rv5m_nm = nm.get("rv_5m") or 0
            pair_ts = nm.get("pair_created_at") or nm.get("pairCreatedAt") or "?"
            logger.info(
                f"  NEAR-MISS {sym}: age={age_h_nm:.1f}h liq=${liq_nm:,.0f} "
                f"vol24h=${vol_nm:,.0f} r_m5={r_m5_nm:.2f}% rv5m={rv5m_nm:.3f}% "
                f"pairCreatedAt={pair_ts}"
            )
        # ── What-if gate counters (instrumentation only, no trading impact) ────
        _whatif = {
            "no_pf_stability": _count_tradeable_without(all_rows, "pf_stability"),
            "no_anti_chase":   _count_tradeable_without(all_rows, "anti_chase"),
            "no_pf_early":     _count_tradeable_without(all_rows, "pf_early"),
            "no_lane_liq":     _count_tradeable_without(all_rows, "lane_liq"),
            "no_lane_vol":     _count_tradeable_without(all_rows, "lane_vol"),
        }
        logger.info(
            f"RANK {strategy}: WHAT-IF gate relief: "
            f"no_pf_stab={_whatif['no_pf_stability']} no_anti_chase={_whatif['no_anti_chase']} "
            f"no_pf_early={_whatif['no_pf_early']} no_liq={_whatif['no_lane_liq']} no_vol={_whatif['no_lane_vol']}"
        )
        log_selection_tick(len(eligible_rows), 0, None, None, False, "no_tradeable_tokens", rej_counts, stall_example,
                           best_token=_best_diag_token, best_score=_best_diag_score, best_block_reason=_best_diag_block,
                           whatif=_whatif)
        return None
    # ── Require |E| >= 2 ──────────────────────────────────────────────────────
    if len(tradeable_set) < 2:
        only = tradeable_set[0].get("token_symbol", "?")
        logger.info(f"RANK {strategy}: |E|={len(tradeable_set)} < 2 — skipping (need baseline slot)")
        # What-if counters on tradeable_lt_2 ticks too
        _whatif = {
            "no_pf_stability": _count_tradeable_without(all_rows, "pf_stability"),
            "no_anti_chase":   _count_tradeable_without(all_rows, "anti_chase"),
            "no_pf_early":     _count_tradeable_without(all_rows, "pf_early"),
            "no_lane_liq":     _count_tradeable_without(all_rows, "lane_liq"),
            "no_lane_vol":     _count_tradeable_without(all_rows, "lane_vol"),
        }
        _bt_lt2, _bs_lt2, _bb_lt2 = _best_diag_for_best(scored[0][1], scored[0][0])
        log_selection_tick(len(eligible_rows), len(tradeable_set), only, scored[0][0], False, "tradeable_lt_2", rej_counts, stall_example,
                           best_token=_bt_lt2, best_score=_bs_lt2, best_block_reason=_bb_lt2,
                           whatif=_whatif)
        return None

    # ── Pick strategy = top-score, baseline = random from E\{strategy} ────────
    best_score, best = scored[0]
    best_mint = best.get("mint_address", "")
    baseline_pool = [r for r in tradeable_set if r.get("mint_address") != best_mint] or tradeable_set
    baseline_row = random.choice(baseline_pool)

    logger.info(
        f"RANK {strategy}: firing top-1 "
        f"{best.get('token_symbol','?')} ({best_mint[:8]}) "
        f"score={best_score:.4f} r_m5={best.get('r_m5') or 0:.2f}% "
        f"lane={classify_lane(best)} | baseline={baseline_row.get('token_symbol','?')}"
    )

    # ── Compute best-token diagnostics for all opened=0 ticks ─────────────────
    # (best scoring eligible token and its first failing gate — for logging only)
    def _best_diag_for_best(b_row, b_score):
        """Return (token, score, block_reason) for the top candidate."""
        tok = b_row.get("token_symbol", "?") if b_row else None
        sc  = b_score
        ok, blk = _check_tradeable(b_row) if b_row else (True, None)
        return tok, sc, (None if ok else blk)

    # ── MIN_SCORE_TO_TRADE gate (feature-flag, default None = OFF) ─────────────
    if MIN_SCORE_TO_TRADE is not None and best_score < MIN_SCORE_TO_TRADE:
        logger.info(
            f"RANK {strategy}: MIN_SCORE_TO_TRADE gate — "
            f"top_score={best_score:.4f} < threshold={MIN_SCORE_TO_TRADE:.4f}, skipping tick."
        )
        _bt, _bs, _bb = _best_diag_for_best(best, best_score)
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, False,
                           f"min_score_gate:{best_score:.4f}<{MIN_SCORE_TO_TRADE:.4f}",
                           rej_counts, best_token=_bt, best_score=_bs, best_block_reason=_bb)
        return None
    # ── Check position cap for strategy (baseline always exempt) ──────────────
    if not passes_position_cap(strategy):
        # v1.14: show which trade is holding the cap slot
        _cap_conn = get_conn()
        _cap_trade = _cap_conn.execute(
            "SELECT trade_id, run_id, token_symbol, entered_at FROM shadow_trades_v1 "
            "WHERE status='open' ORDER BY entered_at ASC LIMIT 1"
        ).fetchone()
        _cap_conn.close()
        if _cap_trade:
            from datetime import datetime as _dt3, timezone as _tz3
            _entered = _dt3.fromisoformat(_cap_trade["entered_at"].replace("Z", "+00:00"))
            _age_min = (_dt3.now(_tz3.utc) - _entered).total_seconds() / 60
            # P3: label whether blocker is current-run or stale cross-run
            _is_current_run = (_cap_trade["run_id"] == _RUN_ID)
            _cap_label = "current_run_pair" if _is_current_run else "STALE_CROSS_RUN (rollover missed?)"
            logger.info(
                f"RANK {strategy}: position cap reached — "
                f"blocking={_cap_trade['trade_id'][:8]} "
                f"token={_cap_trade['token_symbol']} "
                f"run={_cap_trade['run_id'][:8]} "
                f"age={_age_min:.1f}min "
                f"type={_cap_label}"
            )
        else:
            logger.info(f"RANK {strategy}: position cap reached — no open trade found (race?)")
        _bt, _bs, _bb = _best_diag_for_best(best, best_score)
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, False, "position_cap", rej_counts,
                           best_token=_bt, best_score=_bs, best_block_reason=_bb)
        return None
    # ── Open strategy trade ────────────────────────────────────────────
    try:
        tid = open_trade(strategy, best, entry_score=best_score)
    except Exception as _e:
        _bt, _bs, _bb = _best_diag_for_best(best, best_score)
        _reason = f"open_failed:{type(_e).__name__}:{_e}"
        logger.error(f"RANK {strategy}: strategy open_trade raised exception: {_e}")
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, False, _reason, rej_counts,
                           best_token=_bt, best_score=_bs, best_block_reason=_bb)
        return None
    if not tid:
        _bt, _bs, _bb = _best_diag_for_best(best, best_score)
        logger.warning(f"RANK {strategy}: strategy open_trade returned None unexpectedly")
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, False, "strategy_open_failed", rej_counts,
                           best_token=_bt, best_score=_bs, best_block_reason=_bb)
        return None
    # ── Open baseline (EXEMPT from all position caps) ─────────────────────
    baseline_strat = "baseline_matched_pullback_score_rank"
    try:
        btid = open_trade(baseline_strat, baseline_row, baseline_trigger_id=tid)
    except Exception as _e:
        _bt, _bs, _bb = _best_diag_for_best(best, best_score)
        _reason = f"open_failed:{type(_e).__name__}:{_e}"
        logger.error(f"RANK {strategy}: baseline open_trade raised exception: {_e}")
        # Atomic rollback
        try:
            conn = get_conn()
            conn.execute("DELETE FROM shadow_trades_v1 WHERE trade_id=?", (tid,))
            conn.commit(); conn.close()
            logger.info(f"RANK {strategy}: strategy trade {tid[:8]} deleted (atomic rollback OK)")
        except Exception as _re:
            logger.error(f"atomic rollback DELETE failed: {_re} — trade {tid[:8]} may be orphaned")
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, False, _reason, rej_counts,
                           best_token=_bt, best_score=_bs, best_block_reason=_bb)
        return None
    if not btid:
        # v1.13: TRUE ATOMIC ROLLBACK — delete the strategy trade so no orphaned rows exist
        logger.warning(
            f"RANK {strategy}: baseline open FAILED — ROLLING BACK strategy trade {tid[:8]} "
            f"(token={best.get('token_symbol','?')}) to maintain atomic pairing invariant"
        )
        try:
            conn = get_conn()
            conn.execute("DELETE FROM shadow_trades_v1 WHERE trade_id=?", (tid,))
            conn.commit()
            conn.close()
            logger.info(f"RANK {strategy}: strategy trade {tid[:8]} deleted (atomic rollback OK)")
        except Exception as e:
            logger.error(f"atomic rollback DELETE failed: {e} — trade {tid[:8]} may be orphaned")
        _bt, _bs, _bb = _best_diag_for_best(best, best_score)
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, False, "baseline_open_failed", rej_counts,
                           best_token=_bt, best_score=_bs, best_block_reason=_bb)
        return None
    else:
        logger.info(
            f"RANK {strategy}: PAIR OPENED strategy={tid[:8]} baseline={btid[:8]} "
            f"strategy_token={best.get('token_symbol','?')} baseline_token={baseline_row.get('token_symbol','?')}"
        )
        log_selection_tick(len(eligible_rows), len(tradeable_set), best.get("token_symbol"), best_score, True, "opened", rej_counts)
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
    # v1.19 (corrected): request raw quote data for native-to-native price mismatch check
    jup_result = get_jupiter_rt_estimate(mint, liq_b_for_jup, liq_q_for_jup, cpamm_valid=cpamm_valid, return_price=True)
    if isinstance(jup_result, tuple):
        jup_rt, jup_quote_data = jup_result
    else:
        jup_rt, jup_quote_data = jup_result, None  # fallback: shouldn't happen with return_price=True
    if jup_rt is None:
        logger.info(f"SKIP {strategy} {mint[:8]}: no Jupiter route")
        return None
    if jup_rt > FRICTION_GATE_MAX_RT:
        logger.info(f"SKIP {strategy} {mint[:8]}: Jupiter RT {jup_rt*100:.2f}% > gate {FRICTION_GATE_MAX_RT*100:.1f}%")
        return None
    # v1.19 (robust): native-to-native price mismatch check
    # Universe is SOL-quote only, so mint is always the base token and
    # dex_price_native = priceNative (SOL per token) directly.
    # Amounts cast to int (Jupiter returns strings). Decimal math (no float drift).
    # inputMint/outputMint from quote enforced to confirm SOL->token direction.
    from decimal import Decimal
    import time as _time
    dex_price_native  = float(row.get("price_native") or 0.0)  # SOL per token from DexScreener
    jup_exec_price_native    = None
    jup_exec_vs_dex_pct      = None
    price_mismatch_flag      = 0
    jup_implied_price        = None  # kept for DB column (now stores jup_exec_price_native)
    jup_price_unit_native_ok = 0     # 1 = native-to-native method used with real decimals
    if jup_quote_data is not None and dex_price_native > 0:
        try:
            in_lamports  = int(jup_quote_data["inAmount"])   # Jupiter returns strings
            out_raw      = int(jup_quote_data["outAmount"])  # Jupiter returns strings
            input_mint   = jup_quote_data.get("inputMint")
            output_mint  = jup_quote_data.get("outputMint")
        except (KeyError, ValueError, TypeError):
            in_lamports = out_raw = 0
            input_mint = output_mint = None
        # Enforce SOL->token direction (input=wSOL, output=mint being bought)
        if (
            input_mint in (WSOL_MINT, "So11111111111111111111111111111111111111111")
            and output_mint == mint
            and in_lamports > 0
            and out_raw > 0
        ):
            decimals = get_mint_decimals(mint)
            if decimals is not None:
                in_sol     = Decimal(in_lamports) / Decimal(10**9)
                out_tokens = Decimal(out_raw) / Decimal(10**decimals)
                if out_tokens > 0:
                    jup_exec_price_native    = float(in_sol / out_tokens)  # SOL per token
                    jup_exec_vs_dex_pct      = (jup_exec_price_native / dex_price_native) - 1.0
                    jup_implied_price        = jup_exec_price_native
                    jup_price_unit_native_ok = 1  # real decimals + direction enforced
                    # Flag mismatch only for large_cap_ray (most liquid; clearest signal)
                    if lane == "large_cap_ray" and abs(jup_exec_vs_dex_pct) > 0.02:
                        price_mismatch_flag = 1
                        route_plan = jup_quote_data.get("routePlan") or []
                        swap0 = (route_plan[0].get("swapInfo") if route_plan else {}) or {}
                        label = swap0.get("label", "?")
                        amm_k = swap0.get("ammKey", "?")
                        slot  = jup_quote_data.get("contextSlot", "?")
                        logger.info(
                            f"PRICE_MISMATCH {strategy} {row.get('token_symbol','?')} ({mint[:8]}): "
                            f"dex_native={dex_price_native:.10f} jup_exec_native={jup_exec_price_native:.10f} "
                            f"delta={jup_exec_vs_dex_pct*100:+.2f}% dec={decimals} "
                            f"label={label} amm={str(amm_k)[:12]} slot={slot}"
                        )
            else:
                # Decimals unknown — skip mismatch classification but keep trading
                price_mismatch_flag = 0
                jup_implied_price   = None

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
         run_id, git_commit, lane_at_entry, entry_score, mint_prefix,
         entry_jup_implied_price, price_mismatch, jup_price_unit_native_ok)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        _RUN_ID, _GIT_COMMIT, lane, entry_score, mint[:8],
        round(jup_implied_price, 8) if jup_implied_price else None, price_mismatch_flag,
        jup_price_unit_native_ok,
    ))
    conn.commit()
    conn.close()

    # Store adaptive thresholds in memory for fast exit checking
    _adaptive_thresholds[trade_id] = {"sl_pct": entry_sl, "tp_pct": entry_tp}

    _price_mm_note = (
        f" jup_vs_dex={jup_exec_vs_dex_pct*100:+.2f}% mm={price_mismatch_flag}"
        if jup_exec_vs_dex_pct is not None else ""
    )
    logger.info(
        f"OPEN {strategy} {row.get('token_symbol','?')} ({mint[:8]}...) "
        f"lane={lane} age={age_h:.1f}h liq=${liq_usd:,.0f} "
        f"jup_rt={jup_rt*100:.2f}% cpamm_rt={rt['total_friction']*100:.2f}% "
        f"SL={entry_sl:+.2f}% TP={entry_tp:+.2f}% rv5m={rv5m_entry:.4f}%"
        + _price_mm_note
        + (f" [triggered_by={baseline_trigger_id[:8]}]" if baseline_trigger_id else "")
        if rv5m_entry else
        f"OPEN {strategy} {row.get('token_symbol','?')} ({mint[:8]}...) "
        f"lane={lane} age={age_h:.1f}h liq=${liq_usd:,.0f} "
        f"jup_rt={jup_rt*100:.2f}% cpamm_rt={rt['total_friction']*100:.2f}% "
        f"SL={entry_sl:+.2f}% TP={entry_tp:+.2f}% rv5m=warmup"
        + _price_mm_note
        + (f" [triggered_by={baseline_trigger_id[:8]}]" if baseline_trigger_id else "")
    )
    return trade_id

def _compute_run_signature() -> str:
    """v1.16: Compute a stable sha256 hash of all strategy-defining parameters.
    Two runs with identical signatures used the same config and can be safely pooled.
    Excludes run_id, start_ts, git_commit (deployment metadata, not strategy config).
    """
    import json, hashlib
    sig_params = {
        "version": "v1.19",
        "mode": MODE,
        "sl_pct": EXIT_STOP_LOSS_PCT,
        "tp_pct": EXIT_TAKE_PROFIT_PCT,
        "timeout_min": EXIT_MAX_HOLD_MINUTES,
        "k_sl": K_SL,
        "k_tp": K_TP,
        "vol_cap_pct": VOL_CAP_PCT,
        "score_rank_interval_sec": SCORE_RANK_INTERVAL_SEC,
        "r_m5_chase_cap": R_M5_CHASE_CAP,
        "pf_mature_min_age_h": PF_MATURE_MIN_AGE_H,
        "pf_mature_rv5m_max": PF_MATURE_RV5M_MAX,
        "anti_chase_enabled": ANTI_CHASE_FILTER_ENABLED,
        "lane_pumpfun_early": "BLOCKED",
        "lane_pumpfun_mature": f"rv5m<={PF_MATURE_RV5M_MAX}",
        "lane_non_pumpfun_mature": "OK",
        "lane_large_cap_ray": "OK",
    }
    canonical = json.dumps(sig_params, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


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
    sig = _compute_run_signature()
    try:
        conn = get_conn()
        from datetime import datetime as _dt
        conn.execute("""
            INSERT OR IGNORE INTO run_registry
            (run_id, git_commit, start_ts, mode, version, lane_gates, key_params, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (_RUN_ID, _GIT_COMMIT, _dt.utcnow().isoformat(), MODE, "v1.19", lane_gates, key_params, sig))
        conn.commit()
        conn.close()
        logger.info(f"RUN_REGISTRY: registered run_id={_RUN_ID[:8]} version=v1.19 mode={MODE} signature={sig}")
    except Exception as e:
        logger.error(f"run_registry insert failed: {e}")

# ── v1.14: Rollover cleanup — close open trades from old run_ids ──────────
def rollover_cleanup():
    """On startup, mark all open trades from prior run_ids as rollover_close.
    These are excluded from PnL reports (exit_reason='rollover_close').
    """
    from datetime import datetime as _dt2
    conn = get_conn()
    stale = conn.execute("""
        SELECT trade_id, token_symbol, run_id, strategy, entered_at
        FROM shadow_trades_v1
        WHERE status = 'open' AND run_id != ?
    """, (_RUN_ID,)).fetchall()
    if not stale:
        logger.info("ROLLOVER: no stale open trades — clean start")
        conn.close()
        return
    now_iso = _dt2.utcnow().isoformat()
    for t in stale:
        entered_str = t["entered_at"].replace("Z", "+00:00")
        if "+" not in entered_str and entered_str.endswith("00:00") is False:
            entered_str = entered_str + "+00:00"
        try:
            entered = _dt2.fromisoformat(entered_str)
        except Exception:
            entered = _dt2.fromisoformat(t["entered_at"].replace("Z", "")).replace(tzinfo=__import__('datetime').timezone.utc)
        now_utc = _dt2.now(__import__('datetime').timezone.utc)
        age_min = (now_utc - entered).total_seconds() / 60
        conn.execute("""
            UPDATE shadow_trades_v1
            SET status='closed', exited_at=?, exit_reason='rollover_close',
                gross_pnl_pct=0.0, shadow_pnl_pct=0.0, shadow_pnl_pct_fee100=0.0
            WHERE trade_id=?
        """, (now_iso, t["trade_id"]))
        logger.info(
            f"ROLLOVER: closed stale trade {t['trade_id'][:8]} "
            f"token={t['token_symbol']} run={t['run_id'][:8]} "
            f"strategy={t['strategy']} age={age_min:.1f}min"
        )
    conn.commit()
    conn.close()
    logger.info(f"ROLLOVER: closed {len(stale)} stale open trade(s) from prior run_ids")

rollover_cleanup()

# ── CLOSE TRADE ──────────────────────────────────────────────────────────────
def close_trade(trade: dict, current: dict, reason: str, cross: dict | None = None, forced_close: int = 0):
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

    # v1.19: duration and poll count
    entered_at_str = trade.get("entered_at", now_iso)
    try:
        entered_dt = datetime.fromisoformat(entered_at_str.replace("Z", "+00:00"))
        duration_sec_val = round((now - entered_dt).total_seconds(), 1)
    except Exception:
        duration_sec_val = None
    poll_count_val = _poll_count.pop(trade["trade_id"], None)
    exit_reason_effective_val = "forced_pair_close" if forced_close else reason
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

    # v1.18: retrieve MFE/MAE from price path tracker
    mfe_mae_data = _mfe_mae.get(trade["trade_id"], {})
    ep_tracked = mfe_mae_data.get("entry_price") or entry_price
    max_p = mfe_mae_data.get("max_price")
    min_p = mfe_mae_data.get("min_price")
    # Include exit price in price path
    if max_p is None:
        max_p = exit_price
        min_p = exit_price
    else:
        if exit_price > max_p:
            max_p = exit_price
        if exit_price < min_p:
            min_p = exit_price
    # Compute MFE/MAE as decimal fractions from price path
    mfe_val = (max_p / ep_tracked) - 1.0   # decimal, e.g. 0.02 = +2%
    mae_val = (min_p / ep_tracked) - 1.0   # decimal, e.g. -0.015 = -1.5%
    # MFE net of two fee floors
    rt_floor = trade.get("entry_round_trip_pct") or 0.005
    mfe_net_dex_val      = mfe_val - (rt_floor + 0.006)   # vs DEX floor
    mfe_net_fee100_val   = mfe_val - (rt_floor + 0.010)   # vs fee100 floor

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
            mfe_gross_pct           = ?,
            mae_gross_pct           = ?,
            mfe_net_dex_pct         = ?,
            mfe_net_fee100_pct      = ?,
            max_price_seen          = ?,
            min_price_seen          = ?,
            duration_sec            = ?,
            poll_count              = ?,
            forced_close            = ?,
            exit_reason_effective   = ?,
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
        round(mfe_val, 6), round(mae_val, 6),
        round(mfe_net_dex_val, 6), round(mfe_net_fee100_val, 6),
        round(max_p, 8), round(min_p, 8),
        duration_sec_val, poll_count_val, forced_close, exit_reason_effective_val,
        trade["trade_id"],
    ))
    conn.commit()
    conn.close()
    # Clean up in-memory MFE/MAE state
    _mfe_mae.pop(trade["trade_id"], None)
    sym = trade.get('token_symbol', '?')
    mp  = trade.get('mint_prefix') or trade.get('mint_address', '?')[:8]
    logger.info(
        f"CLOSE {trade['strategy']} {sym}({mp}) "
        f"reason={exit_reason_effective_val} gross={gross_pnl_pct*100:+.4f}% "
        f"mfe={mfe_val*100:+.4f}% mae={mae_val*100:+.4f}% fee100={pnl_fee100*100:+.4f}% "
        f"dur={duration_sec_val}s polls={poll_count_val}"
    )
    # FAST_RISK_GATE: record FAST SL exits to fast_blacklist (always, even when gate is OFF)
    # Gate=OFF: records for observability; Gate=ON: actively blocks re-entry for 12h
    is_strategy_leg = not trade.get("strategy", "").startswith("baseline")
    if (is_strategy_leg
            and exit_reason_effective_val == "sl"
            and duration_sec_val is not None
            and duration_sec_val < 60):
        mint_addr = trade.get("mint_address", "")
        if mint_addr:
            add_to_fast_blacklist(
                mint_addr,
                reason=f"fast_sl:dur={duration_sec_val:.1f}s:polls={poll_count_val}"
            )

# # ── OVERSHOOT TRACKING ───────────────────────────────────────────────────
# Maps trade_id -> {"sl_crossed_at": ISO, "tp_crossed_at": ISO,
#                   "prev_poll_at": ISO, "prev_poll_pnl": float,
#                   "timeout_skipped": int}
_threshold_cross_times: dict[str, dict] = {}
# ── MFE/MAE TRACKING (v1.17) ─────────────────────────────────────────────────────
# Maps trade_id -> {"mfe": float, "mae": float}  (decimal fractions, same as gross_pnl_pct)
# Updated on every poll in check_exits; written to DB on close_trade.
_mfe_mae: dict[str, dict] = {}
# ── POLL COUNT TRACKING (v1.19) ──────────────────────────────────────────────────
# Maps trade_id -> int count of check_exits polls during hold.
# Written to DB on close_trade alongside duration_sec.
_poll_count: dict[str, int] = {}

# ── FORCED PAIR CLOSE (v1.19) ────────────────────────────────────────────────
def force_close_paired_baseline(strategy_trade_id: str, current_prices: dict):
    """
    After a strategy leg closes, immediately close its paired baseline trade
    (if still open) with exit_reason_effective='forced_pair_close'.
    current_prices: dict of mint_address -> price dict (from last fetch_current_price calls)
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM shadow_trades_v1
        WHERE baseline_trigger_id = ? AND status = 'open'
    """, (strategy_trade_id,)).fetchall()
    cols = [d[0] for d in conn.description]
    conn.close()
    for row in rows:
        baseline_trade = dict(zip(cols, row))
        mint = baseline_trade["mint_address"]
        current = current_prices.get(mint) or fetch_current_price(mint)
        if current is None:
            logger.warning(f"force_close_paired_baseline: no price for {mint[:8]}, skipping")
            continue
        cross = _threshold_cross_times.pop(baseline_trade["trade_id"], None)
        _adaptive_thresholds.pop(baseline_trade["trade_id"], None)
        logger.info(
            f"FORCED_PAIR_CLOSE baseline {baseline_trade.get('token_symbol','?')} "
            f"(triggered by strategy {strategy_trade_id[:8]} closing)"
        )
        close_trade(baseline_trade, current, "forced_pair_close", cross, forced_close=1)

# ── CHECK EXITS ───────────────────────────────────────────────────────────────
def check_exits(open_trades: list[dict]):
    now_utc = datetime.now(timezone.utc)
    _current_prices_cache: dict[str, dict] = {}  # v1.19: cache for force_close_paired_baseline
    for trade in open_trades:
        mint = trade["mint_address"]
        current = fetch_current_price(mint)
        if not current:
            continue
        _current_prices_cache[mint] = current  # v1.19: cache price for forced baseline close
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

        # v1.19: Increment poll count for this trade
        _poll_count[trade_id] = _poll_count.get(trade_id, 0) + 1
        # v1.18: Update MFE/MAE from price path (absolute USD prices)
        cur_price = current["price_usd"]
        if trade_id not in _mfe_mae:
            # Seed max/min to entry_price so MFE >= 0 always.
            # If price only falls, max_price stays at entry -> MFE = 0%.
            _mfe_mae[trade_id] = {
                "entry_price": entry_price,
                "max_price": entry_price,  # NOT cur_price — guarantees MFE >= 0
                "min_price": entry_price,  # NOT cur_price — MAE starts at 0 from entry
            }
        else:
            if cur_price > _mfe_mae[trade_id]["max_price"]:
                _mfe_mae[trade_id]["max_price"] = cur_price
            if cur_price < _mfe_mae[trade_id]["min_price"]:
                _mfe_mae[trade_id]["min_price"] = cur_price

        if gross_pnl_pct <= sl_threshold and "sl_crossed_at" not in cross:
            cross["sl_crossed_at"]  = now_utc.isoformat()
            cross["sl_prev_poll_at"]  = prev_at
            cross["sl_prev_poll_pnl"] = prev_pnl
        if gross_pnl_pct >= tp_threshold and "tp_crossed_at" not in cross:
            cross["tp_crossed_at"]  = now_utc.isoformat()
            cross["tp_prev_poll_at"]  = prev_at
            cross["tp_prev_poll_pnl"] = prev_pnl

        is_baseline = trade.get("baseline_trigger_id") is not None  # v1.19
        if hold_min >= HARD_MAX_HOLD_MINUTES:
            # Hard max hold — always exit regardless of timeout filter
            close_trade(trade, current, "timeout", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            if not is_baseline:
                force_close_paired_baseline(trade_id, _current_prices_cache)
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
            if not is_baseline:
                force_close_paired_baseline(trade_id, _current_prices_cache)
            continue
        if gross_pnl_pct >= tp_threshold:
            close_trade(trade, current, "tp", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            if not is_baseline:
                force_close_paired_baseline(trade_id, _current_prices_cache)
            continue
        if gross_pnl_pct <= sl_threshold:
            close_trade(trade, current, "sl", cross)
            _threshold_cross_times.pop(trade_id, None)
            _adaptive_thresholds.pop(trade_id, None)
            if not is_baseline:
                force_close_paired_baseline(trade_id, _current_prices_cache)
            continue
        if EXIT_LIQ_CLIFF:
            entry_k = trade.get("entry_k_invariant")
            exit_k  = current.get("k_invariant")
            if entry_k and exit_k:
                cliff = k_lp_cliff(entry_k, exit_k, LP_CLIFF_THRESHOLD)
                if cliff["lp_removal_flag"]:
                    # v1.18: lp_removal audit — re-quote Jupiter at trigger time
                    liq_b_jup = current.get("liq_base") or 0
                    liq_q_jup = current.get("liq_quote_sol") or 0
                    jup_route_ok = None
                    jup_rt_at_trigger = None
                    try:
                        jup_rt_at_trigger = get_jupiter_rt_estimate(
                            mint, liq_b_jup, liq_q_jup, cpamm_valid=True
                        )
                        jup_route_ok = 1 if jup_rt_at_trigger is not None else 0
                    except Exception:
                        jup_route_ok = 0
                    entry_liq = trade.get("entry_liq_usd") or 0
                    exit_liq  = current.get("liq_usd") or 0
                    liq_drop  = ((exit_liq - entry_liq) / entry_liq) if entry_liq > 0 else None
                    sym_lp    = trade.get("token_symbol", "?")
                    mp_lp     = trade.get("mint_prefix") or mint[:8]
                    try:
                        _lp_conn = get_conn()
                        _lp_conn.execute("""
                            INSERT INTO lp_removal_log
                            (logged_at, trade_id, run_id, mint_address, token_symbol, mint_prefix,
                             pool_type, venue, liq_before_usd, liq_after_usd, liq_pct_drop,
                             k_before, k_after, k_change_pct, jup_route_ok, jup_rt_pct, gross_pnl_pct)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            now_utc.isoformat(), trade_id, _RUN_ID, mint,
                            sym_lp, mp_lp,
                            trade.get("pool_type_at_entry"), trade.get("venue_at_entry"),
                            entry_liq, exit_liq,
                            round(liq_drop, 6) if liq_drop is not None else None,
                            entry_k, exit_k,
                            round(cliff["k_change_pct"], 6),
                            jup_route_ok,
                            round(jup_rt_at_trigger, 6) if jup_rt_at_trigger is not None else None,
                            round(gross_pnl_pct / 100.0, 6),
                        ))
                        _lp_conn.commit()
                        _lp_conn.close()
                    except Exception as _lp_err:
                        logger.warning(f"lp_removal_log insert failed: {_lp_err}")
                    logger.info(
                        f"LP_REMOVAL {sym_lp}({mp_lp}) k_drop={cliff['k_change_pct']*100:.1f}% "
                        f"liq_before=${entry_liq:,.0f} liq_after=${exit_liq:,.0f} "
                        f"jup_route={'OK' if jup_route_ok else 'FAIL'} "
                        f"jup_rt={jup_rt_at_trigger*100:.2f}%" if jup_rt_at_trigger else
                        f"LP_REMOVAL {sym_lp}({mp_lp}) k_drop={cliff['k_change_pct']*100:.1f}% "
                        f"liq_before=${entry_liq:,.0f} liq_after=${exit_liq:,.0f} jup_route=FAIL"
                    )
                    close_trade(trade, current, "lp_removal", cross)
                    _threshold_cross_times.pop(trade_id, None)
                    _adaptive_thresholds.pop(trade_id, None)
                    if not is_baseline:
                        force_close_paired_baseline(trade_id, _current_prices_cache)
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

                # ── Momentum strict (LOG-ONLY v1.16: bypasses atomic pairing, disabled) ──
                if should_enter_momentum_strict(row):
                    mom_signals += 1
                    # v1.16: open_trade disabled — pullback_score_rank is SOLE active strategy
                    logger.debug(f"[LOG-ONLY] momentum_strict signal: {row.get('token_symbol','?')} (not opened)")

                # ── Pullback strict (LOG-ONLY v1.16: bypasses atomic pairing, disabled) ──
                if mint in _pullback_pending:
                    # Confirmation stage
                    if should_confirm_pullback(row):
                        del _pullback_pending[mint]
                        pull_signals += 1
                        # v1.16: open_trade disabled — pullback_score_rank is SOLE active strategy
                        logger.debug(f"[LOG-ONLY] pullback_strict confirm: {row.get('token_symbol','?')} (not opened)")
                else:
                    # Initial signal stage
                    if should_enter_pullback_initial(row):
                        _pullback_pending[mint] = now_ts
                        pull_signals += 1
                        logger.debug(f"[LOG-ONLY] pullback_strict initial: {row.get('token_symbol','?')} ({mint[:8]}), awaiting confirmation")

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
