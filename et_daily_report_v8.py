#!/usr/bin/env python3
"""
et_daily_report_v8.py — ET v1 Daily Readiness Report (Decision-Grade)

v8 additions:
  - ROBUST PAIRED DELTA: median, %d>0 (win rate on delta), trimmed mean (drop top/bottom 10%)
    in addition to mean + bootstrap 95% CI
  - BUCKETED ANALYSIS: paired delta by r_m5 quartile, vol_accel quartile, age bucket
    Shows where signal works vs fails (even if aggregate is negative)
  - TAIL-RISK ATTRIBUTION: worst 5 trades with lane/age/liq/filter flags/exit_reason
    Computes % of negative paired delta from tail losses
  - FILTER REJECTION AUDIT: shows filter_rejection_log counts by filter_name
    (sell_ratio_spike, vol_h1_spike, liq_drop_proxy)
"""
import argparse
import sqlite3
import sys
import subprocess
import json
import urllib.request
import math
from datetime import datetime, timezone, timedelta
import random
from statistics import mean, stdev

sys.path.insert(0, '/root/solana_trader')
from config.config import DB_PATH

_parser = argparse.ArgumentParser(description="ET v1 Daily Readiness Report")
_parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours (default: 24)")
_args = _parser.parse_args()
hours = _args.hours
MIN_TRADES_PER_STRATEGY = 20
MIN_STABLE_BLOCKS       = 2
SL_THRESHOLD_PCT        = -0.02   # -2% SL — trades worse than 2x this are poll-gap suspects
TP_THRESHOLD_PCT        =  0.04   # +4% TP
TRADE_SIZE_SOL          = 0.01
LAMPORTS_PER_SOL        = 1_000_000_000
DEX_FEE_RT_PCT          = 0.50
SOLANA_RPC              = "https://api.<REDACTED_SOLANA>"

# ── HELPERS ───────────────────────────────────────────────────────────────────
def pct(v, decimals=3):
    if v is None: return "N/A"
    return f"{v*100:+.{decimals}f}%"

def safe_div(a, b, default=0.0):
    return a / b if b else default

def median_p90(values):
    if not values: return None, None
    s = sorted(values)
    n = len(s)
    med = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    p90 = s[min(int(n * 0.90), n - 1)]
    return med, p90

def bootstrap_ci(deltas, n_boot=2000, ci=0.95):
    """Return (mean, lower_ci, upper_ci) via bootstrap. Returns (None,None,None) if <3 samples."""
    if len(deltas) < 3:
        return None, None, None
    rng = random.Random(42)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(deltas) for _ in range(len(deltas))]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(n_boot * (1 - ci) / 2)]
    hi = means[int(n_boot * (1 - (1 - ci) / 2))]
    return sum(deltas) / len(deltas), lo, hi

def robust_stats(values):
    """
    Compute robust statistics for a list of floats.
    Returns dict with: n, mean, median, pct_positive, trimmed_mean, stdev
    trimmed_mean drops top and bottom 10% (min 3 samples after trim).
    """
    if not values:
        return {"n": 0, "mean": None, "median": None, "pct_positive": None,
                "trimmed_mean": None, "stdev": None}
    n = len(values)
    s = sorted(values)
    med = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    pct_pos = sum(1 for v in values if v > 0) / n * 100
    mu = sum(values) / n
    sd = stdev(values) if n >= 2 else None
    # Trimmed mean: drop top/bottom 10% (at least 1 each side)
    trim_k = max(1, int(n * 0.10))
    trimmed = s[trim_k:-trim_k] if n >= 3 and len(s[trim_k:-trim_k]) >= 1 else s
    tmean = sum(trimmed) / len(trimmed) if trimmed else mu
    return {"n": n, "mean": mu, "median": med, "pct_positive": pct_pos,
            "trimmed_mean": tmean, "stdev": sd}

def quartile_buckets(pairs_data, key_fn, label):
    """
    Split pairs_data into 4 quartile buckets by key_fn(row).
    pairs_data: list of (strategy_pnl, baseline_pnl, key_value) tuples.
    Returns list of (bucket_label, deltas_list) sorted by key.
    """
    # Filter out None key values
    valid = [(s, b, key_fn(s, b, k)) for s, b, k in pairs_data if k is not None]
    if len(valid) < 4:
        return []
    vals = sorted(set(k for _, _, k in valid))
    n = len(valid)
    q1 = sorted(valid, key=lambda x: x[2])
    # Split into 4 roughly equal groups by key value
    chunk = max(1, n // 4)
    buckets = []
    for i in range(4):
        start = i * chunk
        end = (i + 1) * chunk if i < 3 else n
        group = q1[start:end]
        if not group:
            continue
        k_min = group[0][2]
        k_max = group[-1][2]
        deltas = [s - b for s, b, _ in group]
        buckets.append((f"Q{i+1} [{k_min:+.2f},{k_max:+.2f}]", deltas))
    return buckets

def rpc_get_meta_fee(sig):
    """Fetch meta.fee (lamports) for a tx signature via Solana RPC. Returns int or None."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
    }).encode()
    req = urllib.request.Request(
        SOLANA_RPC, data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        result = data.get("result")
        if result is None:
            return None
        return result.get("meta", {}).get("fee")
    except Exception:
        return None

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn  = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 72)
    print("ET v1 DAILY READINESS REPORT  (v7.1 — lane-separated)")
    print(f"Window: last {hours}h | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("Source: shadow_trades_v1 | Strategies: strict + rank variants")
    print("=" * 72)

    # ── 1. SINGLETON STATUS ────────────────────────────────────────────────────
    print("\nSINGLETON STATUS")
    sing_ok = True
    services = [
        ("et_universe_scanner",     "et_universe_scanner.py"),
        ("et_microstructure",       "et_microstructure.py"),
        ("et_shadow_trader_v1",     "et_shadow_trader_v1.py"),
        ("pf_graduation_stream",    "pf_graduation_stream.py"),
    ]
    try:
        for name, script in services:
            result = subprocess.run(["pgrep", "-f", script], capture_output=True, text=True)
            pids = [p for p in result.stdout.strip().split("\n") if p]
            count = len(pids)
            if count == 1:
                print(f"  {name:<30} OK")
            elif count == 0:
                print(f"  {name:<30} DOWN")
                sing_ok = False
            else:
                print(f"  {name:<30} DUPLICATE ({count})")
                sing_ok = False
        try:
            mode_result = subprocess.run(
                ["grep", "-m1", "^MODE =", "/root/solana_trader/et_shadow_trader_v1.py"],
                capture_output=True, text=True
            )
            mode_line = mode_result.stdout.strip()
            if mode_line:
                mode_val = mode_line.split('=', 1)[1].strip().strip('"').strip("'")
                print(f"  v1 mode:                       {mode_val}")
        except Exception:
            pass
    except Exception as e:
        print(f"  singleton check error: {e}")
        sing_ok = False

    # ── 2. UNIVERSE COVERAGE ──────────────────────────────────────────────────
    print("\nUNIVERSE COVERAGE")
    n_scans = 1
    try:
        scan_row = conn.execute("""
            SELECT COUNT(DISTINCT snapshot_at), AVG(cnt), AVG(elig_cnt), MAX(snapshot_at)
            FROM (
                SELECT snapshot_at,
                       COUNT(*) as cnt,
                       SUM(CASE WHEN eligible=1 THEN 1 ELSE 0 END) as elig_cnt
                FROM universe_snapshot
                WHERE snapshot_at >= ?
                GROUP BY snapshot_at
            )
        """, (since,)).fetchone()
        n_scans   = max(scan_row[0] or 1, 1)
        avg_mints = scan_row[1] or 0
        avg_elig  = scan_row[2] or 0
        last_scan = scan_row[3] or "N/A"
        unique_mints = conn.execute("""
            SELECT COUNT(DISTINCT mint_address) FROM universe_snapshot WHERE snapshot_at >= ?
        """, (since,)).fetchone()[0]
        print(f"  Scans in window:       {n_scans}")
        print(f"  Avg mints seen/scan:   {avg_mints:.1f}")
        print(f"  Avg eligible/scan:     {avg_elig:.1f}")
        print(f"  Last scan:             {last_scan}")
        print(f"  Unique mints (window): {unique_mints}")
        if avg_elig < 5:
            print(f"  *** UNIVERSE ALERT: avg eligible/scan={avg_elig:.1f} ***")
    except Exception as e:
        print(f"  universe error: {e}")

    # ── 3. SIGNAL FREQUENCY ────────────────────────────────────────────────────
    print("\nSIGNAL FREQUENCY (from signal_frequency_log)")
    try:
        freq_rows = conn.execute("""
            SELECT strategy,
                   SUM(signals_seen)  as total_signals,
                   SUM(trades_opened) as total_opened,
                   COUNT(*)           as n_cycles
            FROM signal_frequency_log
            WHERE logged_at >= ?
            GROUP BY strategy
        """, (since,)).fetchall()
        freq_map = {r[0]: {"total_signals": r[1] or 0, "total_opened": r[2] or 0, "n_cycles": r[3] or 0}
                    for r in freq_rows}
        trade_counts = conn.execute("""
            SELECT strategy, COUNT(*) as n_total,
                   SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) as n_closed
            FROM shadow_trades_v1
            WHERE entered_at >= ?
            GROUP BY strategy
        """, (since,)).fetchall()
        trade_map = {r[0]: {"n_total": r[1], "n_closed": r[2]} for r in trade_counts}

        print(f"  {'Strategy':<35} {'signals':>8} {'opened':>8} {'closed':>8} {'rate/scan':>10}")
        print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
        for strat in ["momentum_strict", "pullback_strict", "momentum_rank", "pullback_rank"]:
            f = freq_map.get(strat, {})
            t = trade_map.get(strat, {"n_total": 0, "n_closed": 0})
            signals = f.get("total_signals", t["n_total"])
            opened  = f.get("total_opened",  t["n_total"])
            closed  = t["n_closed"]
            rate    = opened / n_scans * 100
            note = ""
            if strat in ("momentum_strict", "pullback_strict") and opened < 5:
                note = "*** STARVATION ***"
            elif strat in ("momentum_rank", "pullback_rank") and opened < 5:
                note = "rank not firing"
            print(f"  {strat:<35} {signals:>8} {opened:>8} {closed:>8} {rate:>9.1f}%  {note}")
        print()
        for strat in ["baseline_matched_momentum_strict", "baseline_matched_pullback_strict",
                      "baseline_matched_momentum_rank",   "baseline_matched_pullback_rank"]:
            t = trade_map.get(strat, {"n_total": 0, "n_closed": 0})
            print(f"  {strat:<35} {'':>8} {t['n_total']:>8} {t['n_closed']:>8}")
    except Exception as e:
        print(f"  signal frequency error: {e}")

    # ── 4. EXIT REASON BREAKDOWN ───────────────────────────────────────────────
    print("\nEXIT REASON BREAKDOWN (per variant)")
    print(f"  {'Strategy':<30} {'exit':<12} {'n':>4}  {'avg_gross':>10}  {'avg_fee060':>10}  note")
    print(f"  {'-'*30} {'-'*12} {'-'*4}  {'-'*10}  {'-'*10}  ----")
    try:
        exits = conn.execute("""
            SELECT strategy, exit_reason, COUNT(*) as n,
                   AVG(gross_pnl_pct)*100       as avg_gross,
                   AVG(shadow_pnl_pct_fee060)*100 as avg_fee060
            FROM shadow_trades_v1
            WHERE status='closed' AND entered_at >= ?
            GROUP BY strategy, exit_reason
            ORDER BY strategy, exit_reason
        """, (since,)).fetchall()
        for r in exits:
            strat, reason, n, avg_g, avg_f = r
            note = ""
            if reason == "timeout" and avg_g is not None and avg_g < 0.5:
                note = "⚠ timeout wins < 0.5% gross — won't clear fees"
            elif reason == "sl" and avg_g is not None and avg_g < SL_THRESHOLD_PCT * 100 * 1.5:
                note = "⚠ SL overshoot suspected"
            print(f"  {strat:<30} {reason:<12} {n:>4}  {avg_g:>+9.3f}%  {avg_f:>+9.3f}%  {note}")
    except Exception as e:
        print(f"  exit breakdown error: {e}")

    # ── 5. WORST TRADE DETAIL ──────────────────────────────────────────────────
    print("\nWORST TRADE DETAIL")
    try:
        worst = conn.execute("""
            SELECT trade_id, strategy, token_symbol, mint_address,
                   entered_at, exited_at,
                   entry_price_usd, exit_price_usd,
                   gross_pnl_pct, shadow_pnl_pct_fee060, shadow_pnl_pct_fee100,
                   exit_reason, entry_jup_rt_pct, entry_round_trip_pct, mode,
                   sl_threshold_crossed_at, exit_overshoot_pct, exit_overshoot_sec
            FROM shadow_trades_v1
            WHERE gross_pnl_pct IS NOT NULL
            ORDER BY gross_pnl_pct ASC LIMIT 1
        """).fetchone()
        if worst:
            w = dict(worst)
            pnl_g = (w["gross_pnl_pct"] or 0) * 100
            sl_thresh = SL_THRESHOLD_PCT * 100
            duration_s = None
            try:
                t_in  = datetime.fromisoformat(w["entered_at"])
                t_out = datetime.fromisoformat(w["exited_at"])
                duration_s = (t_out - t_in).total_seconds()
            except Exception:
                pass
            print(f"  trade_id:     {w['trade_id']}")
            print(f"  strategy:     {w['strategy']}")
            print(f"  token:        {w['token_symbol']}  ({w['mint_address'][:12]}...)")
            print(f"  entered_at:   {w['entered_at']}")
            print(f"  exited_at:    {w['exited_at']}")
            if duration_s is not None:
                print(f"  duration:     {duration_s:.0f}s")
            print(f"  entry_price:  ${w['entry_price_usd']:.6f}")
            print(f"  exit_price:   ${w['exit_price_usd']:.6f}")
            print(f"  gross_pnl:    {pnl_g:+.3f}%")
            print(f"  pnl_fee060:   {(w['shadow_pnl_pct_fee060'] or 0)*100:+.3f}%")
            print(f"  exit_reason:  {w['exit_reason']}")
            print(f"  jup_rt_pct:   {(w['entry_jup_rt_pct'] or 0)*100:.4f}%")
            print(f"  mode:         {w['mode']}")
            # Overshoot detail (new columns from v1.4+ harness)
            if w.get("sl_threshold_crossed_at"):
                print(f"  sl_crossed_at:{w['sl_threshold_crossed_at']}")
            if w.get("exit_overshoot_pct") is not None:
                print(f"  overshoot_pct:{w['exit_overshoot_pct']:+.4f}%  (negative = past SL)")
            if w.get("exit_overshoot_sec") is not None:
                print(f"  overshoot_sec:{w['exit_overshoot_sec']:.1f}s  (delay from threshold cross to exit)")
            # Legacy overshoot flag for old trades without new columns
            if w.get("exit_overshoot_pct") is None and pnl_g < sl_thresh * 1.5:
                print(f"  *** POLL-GAP OVERSHOOT (legacy): pnl={pnl_g:+.1f}% vs SL={sl_thresh:+.1f}% — exit fired {abs(pnl_g/sl_thresh):.1f}x past threshold ***")
        else:
            print("  No closed trades yet")
    except Exception as e:
        print(f"  worst trade error: {e}")

    # ── 5b. OVERSHOOT AUDIT ────────────────────────────────────────────────────
    print("\nOVERSHOOT AUDIT (SL/TP exit quality)")
    try:
        # Check if new overshoot columns exist
        cols = [r[1] for r in conn.execute("PRAGMA table_info(shadow_trades_v1)").fetchall()]
        has_overshoot_cols = "exit_overshoot_pct" in cols
        if has_overshoot_cols:
            rows_os = conn.execute("""
                SELECT exit_reason,
                       COUNT(*) as n,
                       AVG(gross_pnl_pct)*100 as avg_gross,
                       AVG(exit_overshoot_pct) as avg_overshoot_pct,
                       AVG(exit_overshoot_sec) as avg_overshoot_sec,
                       MIN(exit_overshoot_pct) as worst_overshoot_pct,
                       MAX(exit_overshoot_sec) as worst_overshoot_sec
                FROM shadow_trades_v1
                WHERE status='closed'
                  AND exit_reason IN ('sl','tp')
                  AND exit_overshoot_pct IS NOT NULL
                  AND exited_at >= ?
                GROUP BY exit_reason
            """, (since,)).fetchall()
            if rows_os:
                print(f"  {'exit':<8} {'n':>4}  {'avg_gross':>10}  {'avg_overshoot':>14}  {'avg_delay_s':>12}  {'worst_overshoot':>16}  note")
                print(f"  {'-'*8} {'-'*4}  {'-'*10}  {'-'*14}  {'-'*12}  {'-'*16}")
                for r in rows_os:
                    reason, n, avg_g, avg_os, avg_sec, worst_os, worst_sec = r
                    avg_os   = avg_os   or 0.0
                    avg_sec  = avg_sec  or 0.0
                    worst_os = worst_os or 0.0
                    worst_sec= worst_sec or 0.0
                    note = ""
                    if reason == "sl" and avg_os < -0.5:
                        note = f"  ⚠ avg overshoot {avg_os:+.2f}% past SL — poll gap"
                    elif reason == "sl" and avg_os >= -0.5:
                        note = f"  ✓ SL overshoot under control"
                    elif reason == "tp" and avg_os > 0.5:
                        note = f"  ⚠ TP overshoot {avg_os:+.2f}% — slippage at exit"
                    print(f"  {reason:<8} {n:>4}  {avg_g:>+10.2f}%  {avg_os:>+13.2f}%  {avg_sec:>11.1f}s  {worst_os:>+15.2f}%  {note}")

            # Poll-gap detail: prev/curr poll at first threshold cross
            has_prev_poll = "prev_poll_pnl_pct" in cols
            if has_prev_poll:
                pg_rows = conn.execute("""
                    SELECT exit_reason, COUNT(*) as n,
                           AVG(prev_poll_pnl_pct)*100 as avg_prev_pnl,
                           AVG(curr_poll_pnl_pct)*100 as avg_curr_pnl,
                           AVG(curr_poll_pnl_pct - prev_poll_pnl_pct)*100 as avg_gap
                    FROM shadow_trades_v1
                    WHERE status='closed' AND exit_reason IN ('sl','tp')
                      AND prev_poll_pnl_pct IS NOT NULL AND curr_poll_pnl_pct IS NOT NULL
                      AND exited_at >= ?
                    GROUP BY exit_reason
                """, (since,)).fetchall()
                if pg_rows:
                    print(f"  Poll-gap (prev→curr at threshold cross):")
                    for r in pg_rows:
                        reason, n, avg_prev, avg_curr, avg_gap = r
                        print(f"    {reason}: n={n} avg_prev={avg_prev:+.2f}% avg_curr={avg_curr:+.2f}% avg_gap={avg_gap:+.2f}%")

            # Timeout skipped count
            has_ts = "timeout_skipped_count" in cols
            if has_ts:
                ts_rows = conn.execute("""
                    SELECT strategy, SUM(timeout_skipped_count) as total_skipped,
                           COUNT(*) as n_closed
                    FROM shadow_trades_v1
                    WHERE status='closed' AND exited_at >= ?
                    GROUP BY strategy
                    HAVING total_skipped > 0
                """, (since,)).fetchall()
                if ts_rows:
                    print(f"  Timeout filter (extended holds):")
                    for r in ts_rows:
                        strat_name, total_skipped, n_closed = r
                        print(f"    {strat_name}: {total_skipped} timeout skips across {n_closed} closed trades")
            else:
                print("  No SL/TP exits with overshoot data yet (new columns active — accumulating)")
        else:
            # Fallback: estimate overshoot from gross_pnl vs threshold
            rows_os = conn.execute("""
                SELECT exit_reason,
                       COUNT(*) as n,
                       AVG(gross_pnl_pct)*100 as avg_gross,
                       AVG(gross_pnl_pct*100 - ?) as avg_overshoot
                FROM shadow_trades_v1
                WHERE status='closed' AND exit_reason='sl' AND exited_at >= ?
                GROUP BY exit_reason
            """, (SL_THRESHOLD_PCT * 100, since)).fetchall()
            if rows_os:
                for r in rows_os:
                    reason, n, avg_g, avg_os = r
                    avg_os = avg_os or 0.0
                    note = "⚠ poll-gap suspected" if avg_os < -0.5 else "✓ within range"
                    print(f"  SL exits: n={n}, avg_gross={avg_g:+.2f}%, avg_overshoot={avg_os:+.2f}% — {note}")
                    print(f"  (Legacy estimate — upgrade to harness v1.4+ for precise overshoot_sec)")
            else:
                print("  No SL exits in window")
    except Exception as e:
        print(f"  overshoot audit error: {e}")

    # ── 6. V1 AGGREGATE ───────────────────────────────────────────────────────
    print("\nV1 SHADOW TRADES — AGGREGATE (all strategies, last 24h)")
    v1_n = 0
    try:
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(gross_pnl_pct)*100,
                   AVG(shadow_pnl_pct_fee025)*100,
                   AVG(shadow_pnl_pct_fee060)*100,
                   AVG(shadow_pnl_pct_fee100)*100,
                   MAX(gross_pnl_pct)*100,
                   MIN(gross_pnl_pct)*100,
                   SUM(CASE WHEN gross_pnl_pct > 0 THEN 1 ELSE 0 END)
            FROM shadow_trades_v1
            WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()
        v1_n = row[0] or 0
        if v1_n > 0:
            win_rate = safe_div(row[7] or 0, v1_n) * 100
            print(f"  Total closed trades:   {v1_n}")
            print(f"  Win rate (gross):      {win_rate:.1f}%  ← note: irrelevant if timeout wins < fee floor")
            print(f"  Avg PnL (gross):       {row[1]:+.3f}%")
            print(f"  Avg PnL (fee025):      {row[2]:+.3f}%")
            print(f"  Avg PnL (fee060):      {row[3]:+.3f}%")
            print(f"  Avg PnL (fee100):      {row[4]:+.3f}%")
            print(f"  Best trade (gross):    {row[5]:+.3f}%")
            print(f"  Worst trade (gross):   {row[6]:+.3f}%")
        else:
            print("  No closed v1 trades in window")
    except Exception as e:
        print(f"  v1 aggregate error: {e}")

    # ── 7. PER-VARIANT PAIRED DELTA vs MATCHED BASELINE ───────────────────────
    print("\nPER-VARIANT PAIRED DELTA vs MATCHED BASELINE")
    print("  (paired delta = strategy_pnl - baseline_pnl at same entry timestamp)")
    baseline_beat_v1       = False
    baseline_insufficient_v1 = True
    any_strategy_qualified = False

    strategy_pairs = [
        ("momentum_strict",  "baseline_matched_momentum_strict"),
        ("pullback_strict",  "baseline_matched_pullback_strict"),
        ("momentum_rank",    "baseline_matched_momentum_rank"),
        ("pullback_rank",    "baseline_matched_pullback_rank"),
    ]

    def get_variant_stats(strat):
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(shadow_pnl_pct_fee060)*100,
                   AVG(shadow_pnl_pct_fee100)*100,
                   SUM(CASE WHEN gross_pnl_pct > 0 THEN 1 ELSE 0 END),
                   AVG(gross_pnl_pct)*100
            FROM shadow_trades_v1
            WHERE exited_at >= ? AND status='closed' AND strategy=?
        """, (since, strat)).fetchone()
        n = row[0] or 0
        return {"n": n, "ev060": row[1] or 0, "ev100": row[2] or 0,
                "wins": row[3] or 0, "ev_gross": row[4] or 0}

    def get_paired_deltas_full(strat, baseline_strat):
        """
        Match strategy trades to baseline trades by baseline_trigger_id.
        Returns list of (s_pnl060, b_pnl060, s_pnl100, b_pnl100,
                          s_r_m5, s_vol_accel, s_age_h) tuples.
        """
        pairs = conn.execute("""
            SELECT s.shadow_pnl_pct_fee060, b.shadow_pnl_pct_fee060,
                   s.shadow_pnl_pct_fee100, b.shadow_pnl_pct_fee100,
                   s.entry_r_m5, s.entry_vol_accel, s.age_at_entry_h
            FROM shadow_trades_v1 s
            JOIN shadow_trades_v1 b ON b.baseline_trigger_id = s.trade_id
            WHERE s.strategy = ? AND b.strategy = ?
              AND s.status = 'closed' AND b.status = 'closed'
              AND s.exited_at >= ?
        """, (strat, baseline_strat, since)).fetchall()
        return [
            (r[0], r[1], r[2], r[3], r[4], r[5], r[6])
            for r in pairs
            if r[0] is not None and r[1] is not None
        ]

    try:
        for strat, baseline_strat in strategy_pairs:
            s = get_variant_stats(strat)
            b = get_variant_stats(baseline_strat)
            print(f"\n  ── {strat.upper()} vs {baseline_strat} ──")

            if s["n"] < MIN_TRADES_PER_STRATEGY:
                print(f"    {strat:<42} n={s['n']:<3}  INSUFFICIENT_DATA (need {MIN_TRADES_PER_STRATEGY})")
                print(f"    {baseline_strat:<42} n={b['n']:<3}")
                print(f"    Paired delta: N/A")
                continue

            any_strategy_qualified = True
            wr  = safe_div(s["wins"], s["n"]) * 100
            b_wr = safe_div(b["wins"], b["n"]) * 100
            print(f"    {strat:<42} n={s['n']:<3}  win={wr:.0f}%  ev_gross={s['ev_gross']:+.3f}%  ev_fee060={s['ev060']:+.3f}%  ev_fee100={s['ev100']:+.3f}%")
            print(f"    {baseline_strat:<42} n={b['n']:<3}  win={b_wr:.0f}%  ev_gross={b['ev_gross']:+.3f}%  ev_fee060={b['ev060']:+.3f}%  ev_fee100={b['ev100']:+.3f}%")

            full_pairs = get_paired_deltas_full(strat, baseline_strat)
            deltas_060 = [(r[0] - r[1]) * 100 for r in full_pairs]
            deltas_100 = [(r[2] - r[3]) * 100 for r in full_pairs if r[2] is not None and r[3] is not None]

            if deltas_060:
                # ── Robust stats ──────────────────────────────────────────────────
                rs060 = robust_stats(deltas_060)
                rs100 = robust_stats(deltas_100) if deltas_100 else {}
                m060, lo060, hi060 = bootstrap_ci(deltas_060)
                m100, lo100, hi100 = bootstrap_ci(deltas_100) if deltas_100 else (None, None, None)
                beats060 = m060 is not None and m060 > 0
                beats100 = m100 is not None and m100 > 0
                ci_str060 = f"[{lo060:+.3f}%, {hi060:+.3f}%]" if lo060 is not None else "N/A"
                ci_str100 = f"[{lo100:+.3f}%, {hi100:+.3f}%]" if lo100 is not None else "N/A"

                print(f"    n_pairs={len(deltas_060)}")
                print(f"    Paired delta (fee060):")
                print(f"      mean={m060:+.3f}%  95%CI={ci_str060}")
                print(f"      median={rs060['median']:+.3f}%  trimmed_mean={rs060['trimmed_mean']:+.3f}%")
                print(f"      %delta>0 (strategy beats baseline): {rs060['pct_positive']:.0f}%")
                if rs060['stdev'] is not None:
                    print(f"      stdev={rs060['stdev']:.3f}%")
                if deltas_100:
                    print(f"    Paired delta (fee100):")
                    print(f"      mean={m100:+.3f}%  95%CI={ci_str100}")
                    if rs100.get('median') is not None:
                        print(f"      median={rs100['median']:+.3f}%  trimmed_mean={rs100['trimmed_mean']:+.3f}%")
                        print(f"      %delta>0: {rs100['pct_positive']:.0f}%")

                verdict060 = "BEATS BASELINE" if beats060 else "DOES NOT BEAT BASELINE"
                verdict100 = "BEATS BASELINE" if beats100 else "DOES NOT BEAT BASELINE"
                print(f"    fee060: {verdict060}  |  fee100: {verdict100}")
                if lo060 is not None and lo060 > 0:
                    print(f"    *** STRONG EDGE: CI lower bound > 0 at fee060 ***")
                elif beats060:
                    print(f"    Edge positive but CI crosses zero — need more data to confirm")
                if beats060:
                    baseline_beat_v1 = True

                # ── Bucketed analysis by r_m5 quartile ────────────────────────────
                r_m5_pairs = [(r[0]*100, r[1]*100, r[4]) for r in full_pairs if r[4] is not None]
                if len(r_m5_pairs) >= 8:
                    print(f"    Bucketed by entry r_m5 (momentum at entry):")
                    r_m5_sorted = sorted(r_m5_pairs, key=lambda x: x[2])
                    chunk = max(1, len(r_m5_sorted) // 4)
                    for qi in range(4):
                        start = qi * chunk
                        end = (qi + 1) * chunk if qi < 3 else len(r_m5_sorted)
                        group = r_m5_sorted[start:end]
                        if not group:
                            continue
                        k_min, k_max = group[0][2], group[-1][2]
                        d = [s - b for s, b, _ in group]
                        rs = robust_stats(d)
                        verdict = "✓" if rs['mean'] is not None and rs['mean'] > 0 else "✗"
                        print(f"      Q{qi+1} r_m5=[{k_min:+.1f}%,{k_max:+.1f}%] n={rs['n']} "
                              f"mean={rs['mean']:+.3f}% median={rs['median']:+.3f}% "
                              f"%>0={rs['pct_positive']:.0f}% {verdict}")

                # ── Bucketed analysis by vol_accel quartile ───────────────────────
                va_pairs = [(r[0]*100, r[1]*100, r[5]) for r in full_pairs if r[5] is not None]
                if len(va_pairs) >= 8:
                    print(f"    Bucketed by entry vol_accel (volume acceleration):")
                    va_sorted = sorted(va_pairs, key=lambda x: x[2])
                    chunk = max(1, len(va_sorted) // 4)
                    for qi in range(4):
                        start = qi * chunk
                        end = (qi + 1) * chunk if qi < 3 else len(va_sorted)
                        group = va_sorted[start:end]
                        if not group:
                            continue
                        k_min, k_max = group[0][2], group[-1][2]
                        d = [s - b for s, b, _ in group]
                        rs = robust_stats(d)
                        verdict = "✓" if rs['mean'] is not None and rs['mean'] > 0 else "✗"
                        print(f"      Q{qi+1} vol_accel=[{k_min:.2f},{k_max:.2f}] n={rs['n']} "
                              f"mean={rs['mean']:+.3f}% median={rs['median']:+.3f}% "
                              f"%>0={rs['pct_positive']:.0f}% {verdict}")

                # ── Bucketed analysis by age bucket ─────────────────────────────
                age_pairs = [(r[0]*100, r[1]*100, r[6]) for r in full_pairs if r[6] is not None]
                if len(age_pairs) >= 4:
                    print(f"    Bucketed by token age at entry:")
                    age_buckets = [
                        ("4-12h",   [p for p in age_pairs if 4  <= p[2] < 12]),
                        ("12-48h",  [p for p in age_pairs if 12 <= p[2] < 48]),
                        ("48-168h", [p for p in age_pairs if 48 <= p[2] < 168]),
                        ("168h+",   [p for p in age_pairs if p[2] >= 168]),
                    ]
                    for bucket_name, group in age_buckets:
                        if len(group) < 3:
                            continue
                        d = [s - b for s, b, _ in group]
                        rs = robust_stats(d)
                        verdict = "✓" if rs['mean'] is not None and rs['mean'] > 0 else "✗"
                        print(f"      age={bucket_name:<8} n={rs['n']} "
                              f"mean={rs['mean']:+.3f}% median={rs['median']:+.3f}% "
                              f"%>0={rs['pct_positive']:.0f}% {verdict}")

            else:
                print(f"    Paired delta: no matched pairs found (baseline_trigger_id not set)")
                # Fallback: unpaired comparison
                beats060 = s["ev060"] > b["ev060"]
                beats100 = s["ev100"] > b["ev100"]
                print(f"    Unpaired: beats_baseline(fee060)={'YES' if beats060 else 'NO'}  beats_baseline(fee100)={'YES' if beats100 else 'NO'}")
                if beats060:
                    baseline_beat_v1 = True

        if not any_strategy_qualified:
            baseline_insufficient_v1 = True
            print("\n  All strategies INSUFFICIENT_DATA — continue accumulating trades")
        else:
            baseline_insufficient_v1 = not baseline_beat_v1

    except Exception as e:
        print(f"  strategy comparison error: {e}")

    # ── 8. CONCENTRATION CHECK ────────────────────────────────────────────────
    print("\nCONCENTRATION CHECK  (fail if top-3 > 50%)")
    top3_ok_v1 = True
    try:
        total_n = conn.execute("""
            SELECT COUNT(*) FROM shadow_trades_v1
            WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()[0]
        if total_n > 0:
            top_mints = conn.execute("""
                SELECT token_symbol, mint_address, COUNT(*) as cnt
                FROM shadow_trades_v1
                WHERE exited_at >= ? AND status = 'closed'
                GROUP BY mint_address
                ORDER BY cnt DESC LIMIT 10
            """, (since,)).fetchall()
            top1 = top_mints[0][2] / total_n * 100 if top_mints else 0
            top3 = sum(r[2] for r in top_mints[:3]) / total_n * 100 if len(top_mints) >= 3 else top1
            top10 = sum(r[2] for r in top_mints[:10]) / total_n * 100
            print(f"  Top-1 share:  {top1:.1f}%  ({top_mints[0][0] if top_mints else 'N/A'})")
            print(f"  Top-3 share:  {top3:.1f}%  {'OK' if top3 < 50 else 'FAIL'}")
            print(f"  Top-10 share: {top10:.1f}%")
            if top3 >= 50:
                top3_ok_v1 = False
        else:
            print("  No v1 trades in window")
    except Exception as e:
        print(f"  concentration error: {e}")

    # ── 9. STABILITY (6h blocks) ───────────────────────────────────────────────
    print("\nSTABILITY (6h blocks, v1 trades)")
    block_evs = []
    block_ns  = []
    stable_ok_v1 = True
    stable_insufficient_v1 = False
    try:
        for block_start in range(0, hours, 6):
            block_since = (datetime.now(timezone.utc) - timedelta(hours=hours - block_start)).isoformat()
            block_until = (datetime.now(timezone.utc) - timedelta(hours=hours - block_start - 6)).isoformat()
            row = conn.execute("""
                SELECT COUNT(*), AVG(shadow_pnl_pct_fee060)
                FROM shadow_trades_v1
                WHERE exited_at >= ? AND exited_at < ? AND status = 'closed'
            """, (block_since, block_until)).fetchone()
            cnt = row[0] or 0
            avg = (row[1] or 0) * 100
            block_evs.append(avg)
            block_ns.append(cnt)
            print(f"  Block {block_start:02d}-{block_start+6:02d}h: n={cnt:<4} avg_pnl(fee060)={avg:+.3f}%")
        qualified_blocks = [ev for ev, cnt in zip(block_evs, block_ns) if cnt >= 10]
        if len(qualified_blocks) < MIN_STABLE_BLOCKS:
            stable_ok_v1 = False
            stable_insufficient_v1 = True
            print(f"  STABILITY: INSUFFICIENT_DATA ({len(qualified_blocks)}/{MIN_STABLE_BLOCKS} blocks with n>=10)")
        else:
            overall_avg = sum(qualified_blocks) / len(qualified_blocks)
            max_block = max(qualified_blocks)
            if overall_avg != 0 and max_block > 2 * abs(overall_avg):
                stable_ok_v1 = False
                print(f"  STABILITY: FAIL — max block {max_block:+.3f}% > 2x avg {overall_avg:+.3f}%")
            else:
                print(f"  STABILITY: OK (avg={overall_avg:+.3f}%, max={max_block:+.3f}%)")
    except Exception as e:
        print(f"  stability error: {e}")

    # ── 10. FRICTION AUDIT (empirical — RPC backfill) ─────────────────────────
    print("\nFRICTION AUDIT (empirical network/priority fee)")
    friction_ok = True
    fee_lamports_list = []
    fee_source = "hardcoded_fallback"

    # Primary: live_trades.meta_fee
    try:
        fee_rows = conn.execute("""
            SELECT meta_fee FROM live_trades
            WHERE executed_at >= ? AND meta_fee IS NOT NULL AND meta_fee > 0
        """, (since,)).fetchall()
        if fee_rows:
            fee_lamports_list = [r[0] for r in fee_rows]
            fee_source = f"live_trades (n={len(fee_lamports_list)} txns)"
    except Exception:
        pass

    # Fallback: smoke_test_log — backfill via RPC if needed
    if not fee_lamports_list:
        try:
            smoke_row = conn.execute("""
                SELECT buy_sig, sell_sig, sol_spent FROM smoke_test_log
                ORDER BY rowid DESC LIMIT 1
            """).fetchone()
            if smoke_row:
                buy_sig, sell_sig, sol_spent = smoke_row
                rpc_fees = []
                for sig in [buy_sig, sell_sig]:
                    if sig:
                        fee = rpc_get_meta_fee(sig)
                        if fee and fee > 0:
                            rpc_fees.append(fee)

                if rpc_fees:
                    fee_lamports_list = rpc_fees
                    fee_source = f"smoke_test_log RPC backfill (n={len(rpc_fees)} txns)"
                    # Backfill into smoke_test_log if column exists
                    try:
                        conn.execute("ALTER TABLE smoke_test_log ADD COLUMN meta_fee_buy INTEGER")
                        conn.execute("ALTER TABLE smoke_test_log ADD COLUMN meta_fee_sell INTEGER")
                        conn.commit()
                    except Exception:
                        pass  # columns may already exist
                    try:
                        if len(rpc_fees) >= 2:
                            conn.execute("""
                                UPDATE smoke_test_log SET meta_fee_buy=?, meta_fee_sell=?
                                WHERE rowid = (SELECT MAX(rowid) FROM smoke_test_log)
                            """, (rpc_fees[0], rpc_fees[1]))
                        elif len(rpc_fees) == 1:
                            conn.execute("""
                                UPDATE smoke_test_log SET meta_fee_buy=?
                                WHERE rowid = (SELECT MAX(rowid) FROM smoke_test_log)
                            """, (rpc_fees[0],))
                        conn.commit()
                    except Exception:
                        pass
                elif sol_spent and sol_spent > 0:
                    # sol_spent IS the fees (not trade size) — use directly
                    # 0.000014 SOL total for 2 txns = 7000 lam each
                    fee_per_tx_lam = int(sol_spent * LAMPORTS_PER_SOL / 2)
                    fee_lamports_list = [fee_per_tx_lam, fee_per_tx_lam]
                    fee_source = f"smoke_test_log sol_spent (estimated, {fee_per_tx_lam} lam/tx)"
        except Exception as e:
            pass

    # Hardcoded fallback
    if not fee_lamports_list:
        fee_lamports_list = [5000, 5000]
        fee_source = "hardcoded_fallback (5000 lam/tx)"

    fee_med_lam, fee_p90_lam = median_p90(fee_lamports_list)

    try:
        fric_02_impact = conn.execute("""
            SELECT AVG(impact_buy_pct + impact_sell_pct)
            FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND impact_buy_pct IS NOT NULL
        """, (since,)).fetchone()[0] or 0
        n_pairs = conn.execute("""
            SELECT COUNT(DISTINCT mint_address) FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND impact_buy_pct IS NOT NULL
        """, (since,)).fetchone()[0]

        def net_pct(fee_lam, trade_sol):
            return (2 * fee_lam / (trade_sol * LAMPORTS_PER_SOL)) * 100

        net_med_01 = net_pct(fee_med_lam, 0.01)
        net_p90_01 = net_pct(fee_p90_lam, 0.01)
        net_med_02 = net_pct(fee_med_lam, 0.02)
        net_p90_02 = net_pct(fee_p90_lam, 0.02)
        impact_01  = fric_02_impact * 0.5
        impact_02  = fric_02_impact
        total_med_01 = impact_01 + DEX_FEE_RT_PCT + net_med_01
        total_p90_01 = impact_01 + DEX_FEE_RT_PCT + net_p90_01
        total_med_02 = impact_02 + DEX_FEE_RT_PCT + net_med_02
        total_p90_02 = impact_02 + DEX_FEE_RT_PCT + net_p90_02

        print(f"  Fee source:              {fee_source}")
        print(f"  Empirical fee/tx:        median={fee_med_lam:,.0f} lam  p90={fee_p90_lam:,.0f} lam")
        print(f"  (Note: sol_spent=0.000014 SOL in smoke test = fees paid, ~7000 lam/tx)")
        print()
        print(f"  At 0.01 SOL (live canary size):")
        print(f"    (1) Price impact (CPAMM): {impact_01:.3f}%")
        print(f"    (2) DEX fee (RT):         {DEX_FEE_RT_PCT:.3f}%  (0.25% buy + 0.25% sell)")
        print(f"    (3) Network/prio (median):{net_med_01:.3f}%  ({fee_med_lam:,.0f} lam × 2 txns)")
        print(f"    (3) Network/prio (p90):   {net_p90_01:.3f}%  ({fee_p90_lam:,.0f} lam × 2 txns)")
        print(f"    (4) Total RT (median):    {total_med_01:.3f}%")
        print(f"    (4) Total RT (p90):       {total_p90_01:.3f}%  ← fee100 scenario")
        print()
        print(f"  At 0.02 SOL (halves network% component):")
        print(f"    (1) Price impact:         {impact_02:.3f}%")
        print(f"    (2) DEX fee (RT):         {DEX_FEE_RT_PCT:.3f}%")
        print(f"    (3) Network/prio (median):{net_med_02:.3f}%")
        print(f"    (3) Network/prio (p90):   {net_p90_02:.3f}%")
        print(f"    (4) Total RT (median):    {total_med_02:.3f}%")
        print(f"    (4) Total RT (p90):       {total_p90_02:.3f}%")
        print(f"  CPAMM pairs with impact data: {n_pairs}")

        if total_p90_01 > 2.0:
            print(f"  FRICTION ALERT: p90 RT={total_p90_01:.2f}% at 0.01 SOL — consider 0.02 SOL size")
        if fric_02_impact * 2 >= 3.0:
            friction_ok = False
            print(f"  PRICE IMPACT CHECK: FAIL (impact >{3.0}% at 0.04 SOL)")
        else:
            print(f"  PRICE IMPACT CHECK: OK")
    except Exception as e:
        print(f"  friction audit error: {e}")

    # ── 11. SMOKE TEST ────────────────────────────────────────────────────────
    print("\nSMOKE TEST")
    smoke_pass = False
    try:
        smoke = conn.execute("""
            SELECT result, realized_rt_pct, expected_rt_pct, slippage_excess_pct, run_at,
                   pair_symbol, buy_sig, sell_sig, sol_spent, fill_ratio
            FROM smoke_test_log
            ORDER BY run_at DESC LIMIT 1
        """).fetchone()
        if smoke:
            smoke = dict(smoke)
            print(f"  Last run:    {smoke['run_at']}")
            print(f"  Pair:        {smoke['pair_symbol']}")
            print(f"  Result:      {smoke['result']}")
            print(f"  Fill ratio:  {smoke['fill_ratio']:.4f}" if smoke['fill_ratio'] is not None else "  Fill ratio:  N/A")
            sol_spent = smoke['sol_spent']
            if sol_spent is not None:
                lam_total = int(sol_spent * LAMPORTS_PER_SOL)
                lam_per_tx = lam_total // 2
                net_rt_pct = (lam_total / (TRADE_SIZE_SOL * LAMPORTS_PER_SOL)) * 100
                print(f"  SOL spent (fees): {sol_spent:.6f} SOL = {lam_total:,} lam total ({lam_per_tx:,} lam/tx)")
                print(f"  Network RT cost:  {net_rt_pct:.4f}% of 0.01 SOL trade")
                print(f"  Total RT floor:   DEX {DEX_FEE_RT_PCT:.2f}% + network {net_rt_pct:.4f}% = {DEX_FEE_RT_PCT + net_rt_pct:.4f}%")
            print(f"  Friction:    expected={smoke['expected_rt_pct']:.3f}%  realized={smoke['realized_rt_pct']:.3f}%  excess={smoke['slippage_excess_pct']:+.3f}%")
            print(f"  Buy TX:      {smoke['buy_sig']}")
            print(f"  Sell TX:     {smoke['sell_sig']}")
            smoke_pass = smoke['result'] == "PASS"
        else:
            print("  No smoke test run yet")
    except Exception as e:
        print(f"  smoke test error: {e}")

    # ── 12. LIVE_CANARY_READY_V1 GATE ─────────────────────────────────────────
    print("\n" + "=" * 72)
    print("LIVE_CANARY_READY_V1 CHECK")
    print("=" * 72)
    print("Source: shadow_trades_v1 only. Smoke test already cleared.")
    print()

    shadow_count_ok_v1 = v1_n >= 150

    if baseline_insufficient_v1:
        beats_label = f"INSUFFICIENT_DATA (need {MIN_TRADES_PER_STRATEGY} closed per strategy)"
        beats_ok_v1 = False
    else:
        beats_label = "best strategy beats matched baseline at fee060 (paired delta)"
        beats_ok_v1 = baseline_beat_v1

    if stable_insufficient_v1:
        stable_label = f"INSUFFICIENT_DATA (need {MIN_STABLE_BLOCKS} blocks with n>=10)"
    else:
        stable_label = "no block > 2x avg"

    criteria_v1 = [
        ("Singleton enforcement",           sing_ok,              "all services single-instance"),
        ("Smoke test PASS",                 smoke_pass,           "execution safety cleared"),
        ("v1 shadow count >= 150",          shadow_count_ok_v1,   f"n_closed={v1_n}"),
        ("Beats matched baseline (fee060)", beats_ok_v1,          beats_label),
        ("Top-3 share < 50%",               top3_ok_v1,           "concentration check"),
        ("Stability across 6h blocks",      stable_ok_v1,         stable_label),
        ("IMPACT friction < 3%",            friction_ok,          "price impact at 0.04 SOL"),
    ]

    all_pass_v1 = True
    for name, passed, note in criteria_v1:
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {name:<40} ({note})")
        if not passed:
            all_pass_v1 = False

    print()
    if all_pass_v1:
        print(">>> LIVE_CANARY_READY_V1: YES <<<")
        print("    All v1 criteria met. Proceed to live canary.")
    else:
        failed_items = [name for name, passed, _ in criteria_v1 if not passed]
        print(">>> LIVE_CANARY_READY_V1: NO <<<")
        print(f"    Blocking: {', '.join(failed_items)}")
        print("    Continue paper trading. Do not deploy live funds.")
    print("=" * 72)

    # ── 12b. LANE-SEPARATED PAIRED DELTA ─────────────────────────────────────
    print("\n" + "─" * 72)
    print("LANE-SEPARATED PAIRED DELTA  (strategy vs matched baseline, by lane)")
    print("─" * 72)
    print("  Lanes: large_cap | mature_raydium | mature_pumpswap")
    print("  Hard gates enforced: age>=4h, liq>=$100k, vol24h>=$250k")
    try:
        lanes = conn.execute("""
            SELECT DISTINCT lane FROM shadow_trades_v1
            WHERE lane IS NOT NULL AND status='closed'
            ORDER BY lane
        """).fetchall()
        lanes = [r[0] for r in lanes]
        if not lanes:
            print("  No lane-tagged trades yet (new column — accumulating)")
        else:
            for lane_name in lanes:
                print(f"\n  LANE: {lane_name.upper()}")
                for strat, baseline_strat in strategy_pairs:
                    pairs = conn.execute("""
                        SELECT s.shadow_pnl_pct_fee060, b.shadow_pnl_pct_fee060,
                               s.shadow_pnl_pct_fee100, b.shadow_pnl_pct_fee100
                        FROM shadow_trades_v1 s
                        JOIN shadow_trades_v1 b ON b.baseline_trigger_id = s.trade_id
                        WHERE s.strategy = ? AND b.strategy = ?
                          AND s.lane = ?
                          AND s.status = 'closed' AND b.status = 'closed'
                          AND s.exited_at >= ?
                    """, (strat, baseline_strat, lane_name, since)).fetchall()
                    n_pairs = len([r for r in pairs if r[0] is not None and r[1] is not None])
                    if n_pairs < 3:
                        print(f"    {strat:<32} vs baseline: n_pairs={n_pairs} (need >=3)")
                        continue
                    d060 = [(r[0] - r[1]) * 100 for r in pairs if r[0] is not None and r[1] is not None]
                    d100 = [(r[2] - r[3]) * 100 for r in pairs if r[2] is not None and r[3] is not None]
                    m060, lo060, hi060 = bootstrap_ci(d060)
                    m100, lo100, hi100 = bootstrap_ci(d100)
                    ci060 = f"[{lo060:+.3f}%, {hi060:+.3f}%]" if lo060 is not None else "N/A"
                    ci100 = f"[{lo100:+.3f}%, {hi100:+.3f}%]" if lo100 is not None else "N/A"
                    verdict = "BEATS" if (m060 is not None and m060 > 0) else "LAGS"
                    print(f"    {strat:<32} n={n_pairs:<3} delta060={m060:+.3f}% {ci060}  delta100={m100:+.3f}%  [{verdict}]")
    except Exception as e:
        print(f"  lane-separated section error: {e}")

    # ── 13. TAIL-RISK ATTRIBUTION ─────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("TAIL-RISK ATTRIBUTION  (worst 5 trades, all strategies)")
    print("─" * 72)
    try:
        worst5 = conn.execute("""
            SELECT token_symbol, strategy, gross_pnl_pct*100, shadow_pnl_pct_fee060*100,
                   exit_reason, lane, age_at_entry_h, liq_usd_at_entry,
                   entry_r_m5, entry_r_h1, entered_at, exited_at
            FROM shadow_trades_v1
            WHERE status='closed' AND exited_at >= ?
            ORDER BY gross_pnl_pct ASC LIMIT 5
        """, (since,)).fetchall()
        total_neg_pnl = conn.execute("""
            SELECT SUM(shadow_pnl_pct_fee060)
            FROM shadow_trades_v1
            WHERE status='closed' AND exited_at >= ? AND shadow_pnl_pct_fee060 < 0
        """, (since,)).fetchone()[0] or 0
        tail_sum = sum((r[3] or 0) for r in worst5 if (r[3] or 0) < 0)
        tail_pct = (tail_sum / total_neg_pnl * 100) if total_neg_pnl != 0 else 0
        print(f"  Tail-5 share of all negative PnL: {tail_pct:.1f}%")
        print(f"  {'Symbol':<10} {'Strategy':<24} {'Gross':>7} {'fee060':>7} {'Exit':<12} {'Lane':<18} {'Age_h':>6} {'Liq$':>10}")
        for r in worst5:
            sym, strat, gross, f060, exit_r, lane, age_h, liq, r_m5, r_h1, ent, ext = r
            lane_s = (lane or 'unknown')[:16]
            age_s  = f"{age_h:.1f}" if age_h is not None else "N/A"
            liq_s  = f"${liq:,.0f}" if liq is not None else "N/A"
            print(f"  {(sym or '?'):<10} {(strat or '?'):<24} {gross:>+7.2f}% {(f060 or 0):>+7.2f}% {(exit_r or '?'):<12} {lane_s:<18} {age_s:>6} {liq_s:>10}")
    except Exception as e:
        print(f"  tail-risk error: {e}")

    # ── 14. FILTER REJECTION AUDIT (v1.7) ────────────────────────────────────
    print("\n" + "─" * 72)
    print("FILTER REJECTION AUDIT  (crash/rug filters, v1.7)")
    print("─" * 72)
    try:
        frl_rows = conn.execute("""
            SELECT filter_name, COUNT(*) as cnt,
                   COUNT(DISTINCT mint_address) as unique_tokens
            FROM filter_rejection_log
            WHERE logged_at >= ?
            GROUP BY filter_name
            ORDER BY cnt DESC
        """, (since,)).fetchall()
        if not frl_rows:
            print("  No filter rejections logged yet (v1.7 filters not yet active or no triggers)")
        else:
            total_rej = sum(r[1] for r in frl_rows)
            print(f"  Total rejections in window: {total_rej}")
            print(f"  {'Filter':<22} {'Count':>6} {'UniqueTokens':>13}")
            for r in frl_rows:
                print(f"  {r[0]:<22} {r[1]:>6} {r[2]:>13}")
            # Top rejected tokens
            top_rej = conn.execute("""
                SELECT token_symbol, COUNT(*) as cnt, filter_name
                FROM filter_rejection_log
                WHERE logged_at >= ?
                GROUP BY mint_address
                ORDER BY cnt DESC LIMIT 5
            """, (since,)).fetchall()
            if top_rej:
                print(f"  Top rejected tokens:")
                for r in top_rej:
                    print(f"    {(r[0] or '?'):<12} rejected {r[1]}x  (last_filter={r[2]})")
    except Exception as e:
        print(f"  filter rejection audit error: {e}")

    # ── 15. LEGACY ────────────────────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("LEGACY: shadow_trades (old harness, for continuity)")
    print("─" * 72)
    try:
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(shadow_pnl_pct_fee060)*100,
                   SUM(CASE WHEN shadow_pnl_pct > 0 THEN 1 ELSE 0 END)
            FROM shadow_trades
            WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()
        n_old = row[0] or 0
        ev_old = row[1] or 0
        wr_old = safe_div(row[2] or 0, n_old) * 100
        print(f"  Closed trades (24h):  {n_old}")
        print(f"  Win rate:             {wr_old:.1f}%")
        print(f"  Avg PnL (fee060):     {ev_old:+.3f}%")
        print(f"  Note: old harness retired — no new trades expected")
    except Exception as e:
        print(f"  legacy section error: {e}")

    conn.close()

if __name__ == "__main__":
    main()
