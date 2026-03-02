#!/usr/bin/env python3
"""
lcr_continuation_observer_v1.py
================================
READ-ONLY sidecar observer. No trades. No state changes. No wallet access.
No private keys required. Only reads from main DB + calls Jupiter QUOTE endpoint.

Hypothesis:
  large_cap_ray continuation (r_m5 > 0) beats matched large_cap_ray controls
  on executable net forward markout at +5m using Jupiter quotes.

Preregistered rules:
  - Signal:  top-1 candidate per fire with MAX(entry_r_m5), lane=large_cap_ray, r_m5>0
  - Control: nearest match from same fire with r_m5<=0, deterministic distance metric
  - Horizons: +1m, +5m, +15m, +30m
  - Quote source: Jupiter lite-api, fixed 0.01 SOL notional, slippageBps=50
  - Primary metric: mean signal-minus-control net_fee100 at +5m

DO NOT MODIFY THIS FILE'S LOGIC. It is a frozen preregistered observer.
"""

import sqlite3
import uuid
import time
import math
import logging
import sys
import os
import json
import hashlib
import requests
from datetime import datetime, timezone

# ── CONFIG (frozen) ──────────────────────────────────────────────────────────
VERSION             = "lcr_continuation_observer_v1"
DB_PATH             = "/root/solana_trader/data/solana_trader.db"
OBS_DB_PATH         = "/root/solana_trader/data/observer_lcr_cont_v1.db"
FIRE_INTERVAL_SEC   = 900          # 15-minute cadence
MICRO_WINDOW_SEC    = 120          # microstructure must be within 120s of fire_time
FIXED_NOTIONAL_SOL  = 0.01
LAMPORTS_IN         = 10_000_000   # 0.01 SOL in lamports
WSOL_MINT           = "So11111111111111111111111111111111111111112"
SLIPPAGE_BPS        = 50
JUP_ULTRA_URL       = "https://api.jup.ag/ultra/v1/order"
JUP_TIMEOUT_SEC     = 10
JUP_RETRY_DELAYS    = [2, 5, 10]  # seconds between retries on transient errors
JUP_API_KEY         = os.environ.get("JUPITER_API_KEY", "")  # required for Ultra API
FEE_RATE            = 0.01         # 1% fee for net_fee100 calculation
HORIZONS            = [60, 300, 900, 1800]   # +1m, +5m, +15m, +30m in seconds
HORIZON_LABELS      = ["1m", "5m", "15m", "30m"]

# Lane classification constants (must match et_shadow_trader_lcr.py exactly)
LCR_MIN_AGE_H       = 24 * 30     # 30 days in hours
PF_MATURE_MIN_AGE_H = 24.0

# Age buckets (preregistered)
def age_bucket(age_seconds: float) -> str:
    h = age_seconds / 3600.0
    if h < 1:      return "<1h"
    if h < 4:      return "1-4h"
    if h < 24:     return "4h-24h"
    if h < 168:    return "1-7d"
    return "7d+"

# Liquidity buckets (preregistered)
def liq_bucket(liq_usd: float) -> str:
    if liq_usd < 10_000:   return "<10k"
    if liq_usd < 50_000:   return "10k-50k"
    if liq_usd < 200_000:  return "50k-200k"
    return "200k+"

# Vol_h1 buckets (preregistered)
def vol_h1_bucket(vol: float) -> str:
    if vol < 100_000:  return "<100k"
    if vol < 1_000_000: return "100k-1M"
    return "1M+"

# ── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/root/solana_trader/logs/observer_lcr_cont_v1.log", mode="a"),
    ]
)
log = logging.getLogger(VERSION)

# ── RUN ID ───────────────────────────────────────────────────────────────────
RUN_ID = str(uuid.uuid4())
log.info(f"=== {VERSION} starting | run_id={RUN_ID} ===")
log.info(f"DB_PATH={DB_PATH}  OBS_DB_PATH={OBS_DB_PATH}")
log.info(f"Fixed notional: {FIXED_NOTIONAL_SOL} SOL ({LAMPORTS_IN} lamports) | slippageBps={SLIPPAGE_BPS}")

# ── OBSERVER DB SETUP ─────────────────────────────────────────────────────────
def init_observer_db():
    con = sqlite3.connect(OBS_DB_PATH)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS observer_lcr_cont_v1 (
        candidate_id            TEXT    PRIMARY KEY,
        run_id                  TEXT    NOT NULL,
        signal_fire_id          TEXT    NOT NULL,
        candidate_type          TEXT    NOT NULL,   -- 'signal' or 'control'
        control_for_signal_id   TEXT,               -- NULL for signal rows
        fire_time_epoch         INTEGER NOT NULL,
        fire_time_iso           TEXT    NOT NULL,
        snapshot_at_iso         TEXT,
        mint                    TEXT    NOT NULL,
        symbol                  TEXT,
        lane                    TEXT,
        venue                   TEXT,
        venue_family            TEXT,
        pumpfun_origin          INTEGER,
        age_seconds             REAL,
        age_bucket              TEXT,
        liquidity_usd           REAL,
        liquidity_bucket        TEXT,
        entry_vol_h1            REAL,
        vol_h1_bucket           TEXT,
        entry_r_m5              REAL,
        entry_rv5m              REAL,
        entry_range_5m          REAL,
        control_match_distance  REAL,
        quote_source            TEXT    DEFAULT 'Jupiter',
        fixed_notional_sol      REAL    DEFAULT 0.01,
        slippage_bps            INTEGER DEFAULT 50,
        entry_quote_ok          INTEGER,
        entry_out_amount_raw    INTEGER,
        entry_price_ref         REAL,
        entry_price_impact_pct  REAL,
        entry_quote_err         TEXT,
        fwd_quote_ok_1m         INTEGER,
        fwd_sol_out_lamports_1m INTEGER,
        fwd_gross_markout_1m    REAL,
        fwd_net_fee100_1m       REAL,
        fwd_quote_err_1m        TEXT,
        fwd_quote_ok_5m         INTEGER,
        fwd_sol_out_lamports_5m INTEGER,
        fwd_gross_markout_5m    REAL,
        fwd_net_fee100_5m       REAL,
        fwd_quote_err_5m        TEXT,
        fwd_quote_ok_15m        INTEGER,
        fwd_sol_out_lamports_15m INTEGER,
        fwd_gross_markout_15m   REAL,
        fwd_net_fee100_15m      REAL,
        fwd_quote_err_15m       TEXT,
        fwd_quote_ok_30m        INTEGER,
        fwd_sol_out_lamports_30m INTEGER,
        fwd_gross_markout_30m   REAL,
        fwd_net_fee100_30m      REAL,
        fwd_quote_err_30m       TEXT,
        created_at_iso          TEXT    NOT NULL,
        updated_at_iso          TEXT    NOT NULL
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_fire_type
        ON observer_lcr_cont_v1(run_id, signal_fire_id, candidate_type);

    CREATE INDEX IF NOT EXISTS idx_obs_run_fire
        ON observer_lcr_cont_v1(run_id, fire_time_epoch);

    CREATE TABLE IF NOT EXISTS observer_fire_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          TEXT    NOT NULL,
        signal_fire_id  TEXT    NOT NULL,
        fire_time_epoch INTEGER NOT NULL,
        fire_time_iso   TEXT    NOT NULL,
        outcome         TEXT    NOT NULL,   -- 'ok', 'no_signal', 'no_control', 'error'
        note            TEXT,
        created_at_iso  TEXT    NOT NULL
    );
    """)
    con.commit()
    con.close()
    log.info(f"Observer DB initialized: {OBS_DB_PATH}")

# ── LANE CLASSIFICATION (mirrors et_shadow_trader_lcr.py exactly) ─────────────
def classify_lane(age_h: float, pumpfun_origin: int, venue: str) -> str:
    venue_l = (venue or "").lower()
    on_pumpswap = "pumpswap" in venue_l
    if pumpfun_origin:
        return "pumpfun_mature" if age_h >= PF_MATURE_MIN_AGE_H else "pumpfun_early"
    if on_pumpswap and age_h >= PF_MATURE_MIN_AGE_H:
        return "mature_pumpswap"
    if on_pumpswap:
        return "pumpfun_early"
    if age_h >= LCR_MIN_AGE_H:
        return "large_cap_ray"
    return "non_pumpfun_mature"

def venue_family(venue: str) -> str:
    v = (venue or "").lower()
    if "meteora" in v: return "meteora"
    if "raydium" in v: return "raydium"
    if "orca"    in v: return "orca"
    if "pumpswap" in v: return "pumpswap"
    return v.split("_")[0] if v else "unknown"

# ── CANDIDATE POOL ────────────────────────────────────────────────────────────
def get_candidate_pool(fire_epoch: int) -> list[dict]:
    """
    Returns all large_cap_ray eligible candidates for this fire, joined with
    their most recent microstructure row within MICRO_WINDOW_SEC of fire_time.
    Uses epoch ints only — no sqlite datetime() string comparisons.
    """
    fire_iso = datetime.fromtimestamp(fire_epoch, tz=timezone.utc).isoformat()
    micro_lo  = fire_epoch - MICRO_WINDOW_SEC
    micro_hi  = fire_epoch

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Get the latest snapshot at or before fire_time
    cur.execute("""
        SELECT MAX(snapshot_at) AS snap_at
        FROM universe_snapshot
        WHERE snapshot_at <= ?
    """, (fire_iso,))
    row = cur.fetchone()
    snap_at = row["snap_at"] if row else None
    if not snap_at:
        con.close()
        return []

    # Get all eligible tokens from that snapshot
    cur.execute("""
        SELECT u.mint_address, u.token_symbol, u.venue, u.age_hours,
               u.liq_usd, u.vol_h1, u.pool_type, u.spam_flag
        FROM universe_snapshot u
        WHERE u.snapshot_at = ?
          AND u.eligible = 1
    """, (snap_at,))
    snap_rows = cur.fetchall()

    candidates = []
    for s in snap_rows:
        age_h      = s["age_hours"] or 0.0
        pf_origin  = 0   # will be overridden from micro
        venue_str  = s["venue"] or ""

        # Classify lane using snapshot data first (pf_origin from micro below)
        # We'll re-classify after joining micro
        mint = s["mint_address"]

        # Get latest microstructure row within window (epoch comparison)
        # logged_at is ISO string; convert to epoch in Python
        cur.execute("""
            SELECT m.r_m5, m.rv_5m, m.range_5m, m.vol_h1, m.liq_usd,
                   m.pumpfun_origin, m.venue, m.logged_at
            FROM microstructure_log m
            WHERE m.mint_address = ?
              AND m.logged_at <= ?
              AND m.logged_at >= ?
            ORDER BY m.logged_at DESC
            LIMIT 1
        """, (mint, fire_iso,
              datetime.fromtimestamp(micro_lo, tz=timezone.utc).isoformat()))
        micro = cur.fetchone()
        if not micro:
            continue   # no recent microstructure — skip

        pf_origin  = micro["pumpfun_origin"] or 0
        venue_str  = micro["venue"] or venue_str
        r_m5       = micro["r_m5"]
        rv5m       = micro["rv_5m"]
        range_5m   = micro["range_5m"]
        vol_h1     = micro["vol_h1"] or s["vol_h1"] or 0.0
        liq_usd    = micro["liq_usd"] or s["liq_usd"] or 0.0

        if r_m5 is None:
            continue   # no momentum data — skip

        lane = classify_lane(age_h, pf_origin, venue_str)
        if lane != "large_cap_ray":
            continue   # only large_cap_ray candidates

        age_sec = age_h * 3600.0
        candidates.append({
            "mint":           mint,
            "symbol":         s["token_symbol"],
            "lane":           lane,
            "venue":          venue_str,
            "venue_family":   venue_family(venue_str),
            "pumpfun_origin": pf_origin,
            "age_seconds":    age_sec,
            "age_bucket":     age_bucket(age_sec),
            "liquidity_usd":  liq_usd,
            "liq_bucket":     liq_bucket(liq_usd),
            "entry_vol_h1":   vol_h1,
            "vol_h1_bucket":  vol_h1_bucket(vol_h1),
            "entry_r_m5":     r_m5,
            "entry_rv5m":     rv5m,
            "entry_range_5m": range_5m,
            "snapshot_at":    snap_at,
        })

    con.close()
    return candidates

# ── SIGNAL & CONTROL SELECTION ────────────────────────────────────────────────
def select_signal(pool: list[dict]) -> dict | None:
    signals = [c for c in pool if c["entry_r_m5"] > 0]
    if not signals:
        return None
    # Top-1 by MAX(entry_r_m5), tie-break by lexicographically smallest mint
    return sorted(signals, key=lambda c: (-c["entry_r_m5"], c["mint"]))[0]

def select_control(pool: list[dict], signal: dict) -> dict | None:
    controls = [c for c in pool if c["entry_r_m5"] <= 0]
    if not controls:
        return None

    def distance(c: dict) -> float:
        liq_s = signal["liquidity_usd"] or 1.0
        liq_c = c["liquidity_usd"] or 1.0
        vol_s = signal["entry_vol_h1"] or 1.0
        vol_c = c["entry_vol_h1"] or 1.0
        d1 = abs(math.log(max(liq_c, 1)) - math.log(max(liq_s, 1)))
        d2 = abs(math.log(max(vol_c, 1)) - math.log(max(vol_s, 1)))
        d3 = 1.0 if c["age_bucket"]    != signal["age_bucket"]    else 0.0
        d4 = 1.0 if c["pumpfun_origin"] != signal["pumpfun_origin"] else 0.0
        d5 = 1.0 if c["venue_family"]  != signal["venue_family"]  else 0.0
        return d1 + d2 + d3 + d4 + d5

    ranked = sorted(controls, key=lambda c: (distance(c), c["mint"]))
    best = ranked[0]
    best["_match_distance"] = distance(best)
    return best

# ── JUPITER QUOTE ─────────────────────────────────────────────────────────────
def _jup_ultra_get(input_mint: str, output_mint: str, amount: int) -> dict:
    """Shared Jupiter Ultra GET with retry on transient errors."""
    if not JUP_API_KEY:
        return {"ok": False, "data": None, "err": "JUPITER_API_KEY not set"}
    headers   = {"x-api-key": JUP_API_KEY}
    params    = {"inputMint": input_mint, "outputMint": output_mint, "amount": amount}
    last_err  = ""
    for attempt, delay in enumerate([0] + JUP_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            r = requests.get(JUP_ULTRA_URL, params=params, headers=headers,
                             timeout=JUP_TIMEOUT_SEC)
            if r.status_code == 200:
                return {"ok": True, "data": r.json(), "err": None}
            last_err = f"HTTP {r.status_code}: {r.text[:120]}"
            if r.status_code in (429, 500, 502, 503):
                continue   # retry on transient errors
            return {"ok": False, "data": None, "err": last_err}
        except Exception as e:
            last_err = str(e)[:200]
    return {"ok": False, "data": None, "err": last_err}

def jup_buy_quote(mint: str) -> dict:
    """Buy: SOL -> token via Ultra API. Returns dict with ok, out_amount, price_impact, err."""
    res = _jup_ultra_get(WSOL_MINT, mint, LAMPORTS_IN)
    if not res["ok"]:
        return {"ok": 0, "out_amount": None, "price_impact": None,
                "price_ref": None, "err": res["err"]}
    data       = res["data"]
    out_amount = int(data.get("outAmount", 0))
    impact     = float(data.get("priceImpactPct", 0) or 0)
    price_ref  = LAMPORTS_IN / out_amount if out_amount > 0 else None
    return {"ok": 1, "out_amount": out_amount, "price_impact": impact,
            "price_ref": price_ref, "err": None}

def jup_sell_quote(mint: str, token_amount: int) -> dict:
    """Sell: token -> SOL via Ultra API. Returns dict with ok, sol_out_lamports, err."""
    res = _jup_ultra_get(mint, WSOL_MINT, token_amount)
    if not res["ok"]:
        return {"ok": 0, "sol_out": None, "err": res["err"]}
    sol_out = int(res["data"].get("outAmount", 0))
    return {"ok": 1, "sol_out": sol_out, "err": None}

def compute_markout(sol_out_lamports: int | None) -> tuple[float | None, float | None]:
    """Returns (gross_markout, net_fee100) or (None, None) if missing."""
    if sol_out_lamports is None:
        return None, None
    gross = (sol_out_lamports / LAMPORTS_IN) - 1.0
    net   = gross - FEE_RATE
    return gross, net

# ── DB WRITE ──────────────────────────────────────────────────────────────────
def upsert_candidate(row: dict):
    con = sqlite3.connect(OBS_DB_PATH)
    cur = con.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cur.execute("""
        INSERT INTO observer_lcr_cont_v1 (
            candidate_id, run_id, signal_fire_id, candidate_type, control_for_signal_id,
            fire_time_epoch, fire_time_iso, snapshot_at_iso,
            mint, symbol, lane, venue, venue_family, pumpfun_origin,
            age_seconds, age_bucket, liquidity_usd, liquidity_bucket,
            entry_vol_h1, vol_h1_bucket,
            entry_r_m5, entry_rv5m, entry_range_5m,
            control_match_distance,
            quote_source, fixed_notional_sol, slippage_bps,
            entry_quote_ok, entry_out_amount_raw, entry_price_ref,
            entry_price_impact_pct, entry_quote_err,
            created_at_iso, updated_at_iso
        ) VALUES (
            :candidate_id, :run_id, :signal_fire_id, :candidate_type, :control_for_signal_id,
            :fire_time_epoch, :fire_time_iso, :snapshot_at_iso,
            :mint, :symbol, :lane, :venue, :venue_family, :pumpfun_origin,
            :age_seconds, :age_bucket, :liquidity_usd, :liquidity_bucket,
            :entry_vol_h1, :vol_h1_bucket,
            :entry_r_m5, :entry_rv5m, :entry_range_5m,
            :control_match_distance,
            :quote_source, :fixed_notional_sol, :slippage_bps,
            :entry_quote_ok, :entry_out_amount_raw, :entry_price_ref,
            :entry_price_impact_pct, :entry_quote_err,
            :created_at_iso, :updated_at_iso
        )
        ON CONFLICT(run_id, signal_fire_id, candidate_type) DO UPDATE SET
            updated_at_iso = excluded.updated_at_iso
    """, {**row, "created_at_iso": now_iso, "updated_at_iso": now_iso})
    con.commit()
    con.close()

def update_fwd_quote(candidate_id: str, label: str, sol_out: int | None,
                     gross: float | None, net: float | None,
                     ok: int, err: str | None):
    con = sqlite3.connect(OBS_DB_PATH)
    cur = con.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cur.execute(f"""
        UPDATE observer_lcr_cont_v1 SET
            fwd_quote_ok_{label}          = ?,
            fwd_sol_out_lamports_{label}  = ?,
            fwd_gross_markout_{label}     = ?,
            fwd_net_fee100_{label}        = ?,
            fwd_quote_err_{label}         = ?,
            updated_at_iso                = ?
        WHERE candidate_id = ?
    """, (ok, sol_out, gross, net, err, now_iso, candidate_id))
    con.commit()
    con.close()

def log_fire(signal_fire_id: str, fire_epoch: int, fire_iso: str,
             outcome: str, note: str = ""):
    con = sqlite3.connect(OBS_DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO observer_fire_log
            (run_id, signal_fire_id, fire_time_epoch, fire_time_iso, outcome, note, created_at_iso)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (RUN_ID, signal_fire_id, fire_epoch, fire_iso, outcome, note,
          datetime.now(timezone.utc).isoformat()))
    con.commit()
    con.close()

# ── FORWARD QUOTE SCHEDULER ───────────────────────────────────────────────────
# Pending forward quotes: list of (target_epoch, candidate_id, mint, token_amount, label)
_pending_fwd: list[tuple[int, str, str, int, str]] = []

def schedule_fwd_quotes(candidate_id: str, mint: str, token_amount: int,
                        fire_epoch: int):
    for sec, label in zip(HORIZONS, HORIZON_LABELS):
        target = fire_epoch + sec
        _pending_fwd.append((target, candidate_id, mint, token_amount, label))

def process_pending_fwd(now_epoch: int):
    """Execute any forward quotes whose target time has passed."""
    still_pending = []
    for (target, cid, mint, amount, label) in _pending_fwd:
        if now_epoch >= target:
            q = jup_sell_quote(mint, amount)
            gross, net = compute_markout(q["sol_out"])
            update_fwd_quote(cid, label, q["sol_out"], gross, net,
                             q["ok"], q["err"])
            gross_str = f"{gross:.4f}" if gross is not None else "N/A"
            net_str   = f"{net:.4f}"   if net   is not None else "N/A"
            log.info(f"  fwd_{label} | {mint[:8]}... | ok={q['ok']} | "
                     f"gross={gross_str} | net={net_str}")
        else:
            still_pending.append((target, cid, mint, amount, label))
    _pending_fwd.clear()
    _pending_fwd.extend(still_pending)

# ── FIRE LOGIC ────────────────────────────────────────────────────────────────
def run_fire(fire_epoch: int):
    fire_iso = datetime.fromtimestamp(fire_epoch, tz=timezone.utc).isoformat()
    # Deterministic fire ID: YYYYMMDD_HHMM UTC of 15-min bucket start
    dt = datetime.fromtimestamp(fire_epoch, tz=timezone.utc)
    signal_fire_id = dt.strftime("%Y%m%d_%H%M")

    log.info(f"--- FIRE {signal_fire_id} (epoch={fire_epoch}) ---")

    pool = get_candidate_pool(fire_epoch)
    log.info(f"  Candidate pool: {len(pool)} large_cap_ray tokens")

    if not pool:
        log.info("  No candidates — skipping fire")
        log_fire(signal_fire_id, fire_epoch, fire_iso, "no_signal", "empty pool")
        return

    signal = select_signal(pool)
    if not signal:
        log.info("  No signal (no r_m5 > 0) — skipping fire")
        log_fire(signal_fire_id, fire_epoch, fire_iso, "no_signal", "no r_m5>0")
        return

    control = select_control(pool, signal)
    if not control:
        log.info("  No control available — skipping fire")
        log_fire(signal_fire_id, fire_epoch, fire_iso, "no_control",
                 f"signal={signal['mint'][:8]}")
        return

    log.info(f"  Signal:  {signal['mint'][:8]}... ({signal['symbol']}) "
             f"r_m5={signal['entry_r_m5']:.4f}")
    log.info(f"  Control: {control['mint'][:8]}... ({control['symbol']}) "
             f"r_m5={control['entry_r_m5']:.4f} "
             f"dist={control.get('_match_distance', 0):.3f}")

    signal_id  = str(uuid.uuid4())
    control_id = str(uuid.uuid4())

    # Entry quotes
    sq = jup_buy_quote(signal["mint"])
    cq = jup_buy_quote(control["mint"])
    log.info(f"  Entry quotes: signal_ok={sq['ok']} out={sq['out_amount']} | "
             f"control_ok={cq['ok']} out={cq['out_amount']}")

    # Persist signal row
    upsert_candidate({
        "candidate_id":           signal_id,
        "run_id":                 RUN_ID,
        "signal_fire_id":         signal_fire_id,
        "candidate_type":         "signal",
        "control_for_signal_id":  None,
        "fire_time_epoch":        fire_epoch,
        "fire_time_iso":          fire_iso,
        "snapshot_at_iso":        signal.get("snapshot_at"),
        "mint":                   signal["mint"],
        "symbol":                 signal["symbol"],
        "lane":                   signal["lane"],
        "venue":                  signal["venue"],
        "venue_family":           signal["venue_family"],
        "pumpfun_origin":         signal["pumpfun_origin"],
        "age_seconds":            signal["age_seconds"],
        "age_bucket":             signal["age_bucket"],
        "liquidity_usd":          signal["liquidity_usd"],
        "liquidity_bucket":       signal["liq_bucket"],
        "entry_vol_h1":           signal["entry_vol_h1"],
        "vol_h1_bucket":          signal["vol_h1_bucket"],
        "entry_r_m5":             signal["entry_r_m5"],
        "entry_rv5m":             signal["entry_rv5m"],
        "entry_range_5m":         signal["entry_range_5m"],
        "control_match_distance": None,
        "quote_source":           "Jupiter",
        "fixed_notional_sol":     FIXED_NOTIONAL_SOL,
        "slippage_bps":           SLIPPAGE_BPS,
        "entry_quote_ok":         sq["ok"],
        "entry_out_amount_raw":   sq["out_amount"],
        "entry_price_ref":        sq.get("price_ref"),
        "entry_price_impact_pct": sq.get("price_impact"),
        "entry_quote_err":        sq["err"],
    })

    # Persist control row
    upsert_candidate({
        "candidate_id":           control_id,
        "run_id":                 RUN_ID,
        "signal_fire_id":         signal_fire_id,
        "candidate_type":         "control",
        "control_for_signal_id":  signal_id,
        "fire_time_epoch":        fire_epoch,
        "fire_time_iso":          fire_iso,
        "snapshot_at_iso":        control.get("snapshot_at"),
        "mint":                   control["mint"],
        "symbol":                 control["symbol"],
        "lane":                   control["lane"],
        "venue":                  control["venue"],
        "venue_family":           control["venue_family"],
        "pumpfun_origin":         control["pumpfun_origin"],
        "age_seconds":            control["age_seconds"],
        "age_bucket":             control["age_bucket"],
        "liquidity_usd":          control["liquidity_usd"],
        "liquidity_bucket":       control["liq_bucket"],
        "entry_vol_h1":           control["entry_vol_h1"],
        "vol_h1_bucket":          control["vol_h1_bucket"],
        "entry_r_m5":             control["entry_r_m5"],
        "entry_rv5m":             control["entry_rv5m"],
        "entry_range_5m":         control["entry_range_5m"],
        "control_match_distance": control.get("_match_distance"),
        "quote_source":           "Jupiter",
        "fixed_notional_sol":     FIXED_NOTIONAL_SOL,
        "slippage_bps":           SLIPPAGE_BPS,
        "entry_quote_ok":         cq["ok"],
        "entry_out_amount_raw":   cq["out_amount"],
        "entry_price_ref":        cq.get("price_ref"),
        "entry_price_impact_pct": cq.get("price_impact"),
        "entry_quote_err":        cq["err"],
    })

    # Schedule forward quotes (only if entry quote succeeded)
    if sq["ok"] and sq["out_amount"]:
        schedule_fwd_quotes(signal_id, signal["mint"], sq["out_amount"], fire_epoch)
    if cq["ok"] and cq["out_amount"]:
        schedule_fwd_quotes(control_id, control["mint"], cq["out_amount"], fire_epoch)

    log_fire(signal_fire_id, fire_epoch, fire_iso, "ok",
             f"signal={signal['mint'][:8]} control={control['mint'][:8]}")

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def next_fire_epoch(now_epoch: int) -> int:
    """Round up to next 15-minute boundary."""
    return ((now_epoch // FIRE_INTERVAL_SEC) + 1) * FIRE_INTERVAL_SEC

def main():
    init_observer_db()
    log.info(f"Observer ready. Waiting for first 15-min fire...")

    last_fire_epoch = 0

    while True:
        now_epoch = int(time.time())

        # Process any pending forward quotes
        process_pending_fwd(now_epoch)

        # Check if it's time for a new fire
        current_bucket = (now_epoch // FIRE_INTERVAL_SEC) * FIRE_INTERVAL_SEC
        if current_bucket > last_fire_epoch:
            try:
                run_fire(current_bucket)
                last_fire_epoch = current_bucket
            except Exception as e:
                log.error(f"Fire error: {e}", exc_info=True)

        time.sleep(10)   # poll every 10 seconds

if __name__ == "__main__":
    main()
