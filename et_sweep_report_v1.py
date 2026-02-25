#!/usr/bin/env python3
"""
ET v1 Parameter Sweep Report — k_sl / k_tp Grid vs Matched Baseline
====================================================================
Evaluates what SL/TP multipliers would have produced the best EV
on the historical shadow_trades_v1 dataset.

For each (k_sl, k_tp) pair:
  - Recompute SL = -max(RT_floor + SL_BUFFER, k_sl * rv_5m_at_entry)
  - Recompute TP =  max(RT_floor + TP_EDGE,   k_tp * rv_5m_at_entry)
  - Simulate exit: would the trade have hit TP, SL, or timeout?
    Uses actual gross_pnl_pct as the realized outcome.
  - Compute mean EV (fee060), win%, and paired delta vs matched baseline

Note: This is a RETROSPECTIVE simulation. It cannot account for path-
dependent effects (e.g., a wider SL might have avoided a premature exit
that then recovered). It is a lower bound on the benefit of adaptive exits.
Treat as directional signal, not precise EV estimate.

Usage:
  python3 et_sweep_report_v1.py [--window 48] [--min-pairs 10]
"""
import sys
import sqlite3
import argparse
import statistics
import random
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/root/solana_trader")
from config.config import DB_PATH

# ── SWEEP GRID ────────────────────────────────────────────────────────────────
K_SL_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0]   # SL = k_sl * rv_5m
K_TP_VALUES = [2.0, 3.0, 4.0, 5.0, 6.0]   # TP = k_tp * rv_5m

SL_BUFFER   = 0.003   # 0.3% buffer above RT floor
TP_EDGE     = 0.015   # 1.5% edge buffer above RT floor
SL_FLOOR    = -2.0    # fixed floor (% gross)
TP_FLOOR    = +4.0    # fixed floor (% gross)
VOL_CAP_PCT = 4.5     # trades with k_sl*rv_5m > this would have been skipped

# Fee model
IMPACT_FRAC = 0.006   # 0.6% round-trip impact (median from data)
FEE_MED     = 0.006   # 0.6% fee tier

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, default=48, help="Hours of history to use (default: 48)")
    p.add_argument("--min-pairs", type=int, default=8, help="Min paired trades to show strategy (default: 8)")
    return p.parse_args()

def load_trades(window_h: int) -> list[dict]:
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_h)).isoformat()
    c = conn.cursor()
    c.execute("""
        SELECT t.*,
               m.rv_5m as rv5m_latest
        FROM shadow_trades_v1 t
        LEFT JOIN (
            SELECT mint_address, rv_5m,
                   ROW_NUMBER() OVER (PARTITION BY mint_address ORDER BY logged_at DESC) as rn
            FROM microstructure_log
            WHERE rv_5m IS NOT NULL
        ) m ON t.mint_address = m.mint_address AND m.rn = 1
        WHERE t.status = 'closed'
          AND t.entered_at >= ?
        ORDER BY t.entered_at
    """, (cutoff,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def simulate_exit(gross_pnl_pct: float, sl: float, tp: float, rt_floor: float) -> tuple[str, float]:
    """
    Retrospective simulation: given the actual gross outcome and hypothetical SL/TP,
    determine what the exit would have been.

    Returns (exit_reason, simulated_gross_pnl_pct).

    Limitations:
    - We only know the final gross_pnl_pct, not the intrabar path.
    - If gross < sl: assume SL was hit (possibly with overshoot, use actual gross).
    - If gross > tp: assume TP was hit (use tp as the exit, not actual gross).
    - Otherwise: timeout at actual gross.
    """
    if gross_pnl_pct <= sl:
        return "sl", gross_pnl_pct   # SL hit; actual gross includes overshoot
    if gross_pnl_pct >= tp:
        return "tp", tp               # TP hit; cap at TP (don't get more)
    return "timeout", gross_pnl_pct  # Neither; exit at actual

def compute_pnl_fee060(gross: float, rt_floor: float) -> float:
    """Compute fee060 PnL from gross."""
    return gross - (rt_floor * 100 + FEE_MED * 100)

def bootstrap_ci(values: list[float], n_boot: int = 500, ci: float = 0.95) -> tuple[float, float]:
    """Bootstrap confidence interval for the mean."""
    if len(values) < 3:
        return float("nan"), float("nan")
    boot_means = []
    for _ in range(n_boot):
        sample = [random.choice(values) for _ in range(len(values))]
        boot_means.append(statistics.mean(sample))
    boot_means.sort()
    lo_idx = int((1 - ci) / 2 * n_boot)
    hi_idx = int((1 + ci) / 2 * n_boot)
    return boot_means[lo_idx], boot_means[hi_idx]

def run_sweep(trades: list[dict], strategy: str, min_pairs: int) -> list[dict]:
    """
    For each (k_sl, k_tp) pair, simulate exits and compute EV vs matched baseline.
    Returns list of result dicts sorted by mean_delta descending.
    """
    strat_trades = [t for t in trades if t["strategy"] == strategy and not t["strategy"].startswith("baseline_")]
    baseline_strat = f"baseline_matched_{strategy}"
    baseline_trades = {t["baseline_trigger_id"]: t for t in trades if t["strategy"] == baseline_strat and t.get("baseline_trigger_id")}

    if len(strat_trades) < min_pairs:
        return []

    results = []

    for k_sl in K_SL_VALUES:
        for k_tp in K_TP_VALUES:
            if k_tp <= k_sl:
                continue  # TP must be wider than SL

            strategy_evs   = []
            baseline_evs   = []
            deltas         = []
            n_vol_skipped  = 0
            exit_counts    = {"sl": 0, "tp": 0, "timeout": 0}

            for trade in strat_trades:
                gross      = (trade.get("gross_pnl_pct") or 0) * 100
                rt_floor   = (trade.get("entry_round_trip_pct") or 0.006)
                rv5m       = trade.get("entry_rv5m") or trade.get("rv5m_latest")

                # Compute adaptive SL/TP
                if rv5m is not None and rv5m > 0:
                    sl = -max(rt_floor * 100 + SL_BUFFER * 100, k_sl * rv5m)
                    tp =  max(rt_floor * 100 + TP_EDGE * 100,   k_tp * rv5m)
                    # Vol no-trade check
                    if k_sl * rv5m > VOL_CAP_PCT:
                        n_vol_skipped += 1
                        continue
                else:
                    # No rv5m: use fixed floors
                    sl = SL_FLOOR
                    tp = TP_FLOOR

                # Clamp
                sl = max(sl, -10.0)
                tp = min(tp, 20.0)

                exit_reason, sim_gross = simulate_exit(gross, sl, tp, rt_floor)
                exit_counts[exit_reason] += 1
                strat_ev = compute_pnl_fee060(sim_gross, rt_floor)
                strategy_evs.append(strat_ev)

                # Matched baseline: always fixed exits (baseline doesn't use adaptive)
                btrade = baseline_trades.get(trade.get("trade_id"))
                if btrade:
                    b_gross = (btrade.get("gross_pnl_pct") or 0) * 100
                    b_rt    = (btrade.get("entry_round_trip_pct") or 0.006)
                    b_exit, b_sim_gross = simulate_exit(b_gross, SL_FLOOR, TP_FLOOR, b_rt)
                    baseline_ev = compute_pnl_fee060(b_sim_gross, b_rt)
                    baseline_evs.append(baseline_ev)
                    deltas.append(strat_ev - baseline_ev)

            if len(strategy_evs) < min_pairs:
                continue

            mean_ev     = statistics.mean(strategy_evs)
            median_ev   = statistics.median(strategy_evs)
            win_pct     = sum(1 for v in strategy_evs if v > 0) / len(strategy_evs) * 100
            mean_delta  = statistics.mean(deltas) if deltas else float("nan")
            ci_lo, ci_hi = bootstrap_ci(deltas) if deltas else (float("nan"), float("nan"))

            results.append({
                "k_sl":         k_sl,
                "k_tp":         k_tp,
                "n":            len(strategy_evs),
                "n_pairs":      len(deltas),
                "n_vol_skip":   n_vol_skipped,
                "mean_ev":      mean_ev,
                "median_ev":    median_ev,
                "win_pct":      win_pct,
                "mean_delta":   mean_delta,
                "ci_lo":        ci_lo,
                "ci_hi":        ci_hi,
                "exit_sl_pct":  exit_counts["sl"] / len(strategy_evs) * 100,
                "exit_tp_pct":  exit_counts["tp"] / len(strategy_evs) * 100,
                "exit_to_pct":  exit_counts["timeout"] / len(strategy_evs) * 100,
            })

    results.sort(key=lambda r: r["mean_delta"], reverse=True)
    return results

def print_sweep(strategy: str, results: list[dict]):
    if not results:
        print(f"\n{strategy}: insufficient data (< min_pairs)")
        return

    print(f"\n{'='*80}")
    print(f"PARAMETER SWEEP: {strategy}")
    print(f"{'='*80}")
    print(f"{'k_sl':>5} {'k_tp':>5} {'n':>4} {'n_pairs':>7} {'mean_ev':>9} {'med_ev':>8} {'win%':>6} "
          f"{'mean_Δ':>8} {'CI_lo':>7} {'CI_hi':>7} {'%SL':>5} {'%TP':>5} {'%TO':>5} {'vol_skip':>8}")
    print("-"*100)

    for r in results:
        ci_lo = f"{r['ci_lo']:+.2f}" if r['ci_lo'] == r['ci_lo'] else "  N/A"
        ci_hi = f"{r['ci_hi']:+.2f}" if r['ci_hi'] == r['ci_hi'] else "  N/A"
        flag = " ◄ BEST" if results.index(r) == 0 else ""
        flag_ci = " [CI>0]" if r['ci_lo'] > 0 else ""
        print(
            f"{r['k_sl']:>5.1f} {r['k_tp']:>5.1f} {r['n']:>4} {r['n_pairs']:>7} "
            f"{r['mean_ev']:>+8.3f}% {r['median_ev']:>+7.3f}% {r['win_pct']:>5.1f}% "
            f"{r['mean_delta']:>+7.3f}% {ci_lo:>7} {ci_hi:>7} "
            f"{r['exit_sl_pct']:>4.0f}% {r['exit_tp_pct']:>4.0f}% {r['exit_to_pct']:>4.0f}% "
            f"{r['n_vol_skip']:>8}{flag}{flag_ci}"
        )

    # Summary
    best = results[0]
    print(f"\nBest config: k_sl={best['k_sl']} k_tp={best['k_tp']} "
          f"mean_Δ={best['mean_delta']:+.3f}% CI=[{best['ci_lo']:+.2f}%, {best['ci_hi']:+.2f}%]")
    if best["ci_lo"] > 0:
        print("  → CI lower bound > 0: STATISTICALLY SIGNIFICANT positive edge")
    elif best["mean_delta"] > 0:
        print("  → Positive mean delta but CI crosses 0: directional signal, not confirmed")
    else:
        print("  → No configuration beats matched baseline")

def print_rv5m_distribution(trades: list[dict]):
    """Show the distribution of rv_5m at entry across all strategy trades."""
    rv_vals = [t.get("entry_rv5m") for t in trades
               if t.get("entry_rv5m") is not None and not t["strategy"].startswith("baseline_")]
    if not rv_vals:
        print("\nrv_5m distribution: no data yet (microstructure v1.8 not yet running)")
        return

    rv_vals.sort()
    n = len(rv_vals)
    print(f"\n{'='*60}")
    print(f"rv_5m AT ENTRY DISTRIBUTION (n={n})")
    print(f"{'='*60}")
    print(f"  min:    {min(rv_vals):.4f}%")
    print(f"  p25:    {rv_vals[n//4]:.4f}%")
    print(f"  median: {rv_vals[n//2]:.4f}%")
    print(f"  p75:    {rv_vals[3*n//4]:.4f}%")
    print(f"  p90:    {rv_vals[int(0.9*n)]:.4f}%")
    print(f"  max:    {max(rv_vals):.4f}%")
    print(f"\n  Implied SL at K_SL=2.0:")
    for pct in [25, 50, 75, 90]:
        rv = rv_vals[int(pct/100*n)]
        sl = -max(0.006*100 + 0.3, 2.0 * rv)
        tp =  max(0.006*100 + 1.5, 4.0 * rv)
        print(f"    p{pct}: rv={rv:.4f}% → SL={sl:+.2f}% TP={tp:+.2f}%")

    # Vol no-trade filter impact
    n_hot = sum(1 for v in rv_vals if 2.0 * v > VOL_CAP_PCT)
    print(f"\n  Vol no-trade filter (K_SL=2.0, cap={VOL_CAP_PCT}%): "
          f"would skip {n_hot}/{n} = {n_hot/n*100:.0f}% of entries")

def print_conditional_drift(trades: list[dict], strategy: str):
    """
    Show mean post-entry drift bucketed by signal strength in sigma units (r_m5 / rv_5m).
    This is the 'measure conditional drift vs signal strength' from the spec.
    """
    strat_trades = [t for t in trades
                    if t["strategy"] == strategy
                    and t.get("entry_rv5m") is not None
                    and t.get("entry_rv5m", 0) > 0
                    and t.get("entry_r_m5") is not None]

    if len(strat_trades) < 5:
        return

    # Compute sigma units
    for t in strat_trades:
        rv = t["entry_rv5m"]
        r_m5 = t["entry_r_m5"] or 0
        t["_sigma"] = r_m5 / rv if rv > 0 else 0
        t["_gross"] = (t.get("gross_pnl_pct") or 0) * 100

    strat_trades.sort(key=lambda t: t["_sigma"])
    n = len(strat_trades)
    q_size = max(n // 4, 1)

    print(f"\n  Conditional drift by signal strength (r_m5/rv_5m sigma) — {strategy}:")
    print(f"  {'Quartile':>10} {'sigma_range':>20} {'n':>4} {'mean_gross':>11} {'win%':>6}")
    for q in range(4):
        lo = q * q_size
        hi = (q + 1) * q_size if q < 3 else n
        bucket = strat_trades[lo:hi]
        sigmas = [t["_sigma"] for t in bucket]
        grosses = [t["_gross"] for t in bucket]
        win_pct = sum(1 for g in grosses if g > 0) / len(grosses) * 100
        print(
            f"  Q{q+1:>9} [{min(sigmas):>+5.1f}σ, {max(sigmas):>+5.1f}σ] "
            f"{len(bucket):>4} {statistics.mean(grosses):>+10.3f}% {win_pct:>5.1f}%"
        )

def main():
    args = parse_args()
    random.seed(42)

    print("=" * 80)
    print(f"ET v1 PARAMETER SWEEP REPORT — k_sl/k_tp Grid vs Matched Baseline")
    print(f"Window: {args.window}h | Min pairs: {args.min_pairs}")
    print(f"Grid: k_sl={K_SL_VALUES} | k_tp={K_TP_VALUES}")
    print(f"Vol cap: {VOL_CAP_PCT}% (skip if K_SL*rv_5m > cap)")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 80)

    trades = load_trades(args.window)
    n_total = len(trades)
    n_strat = sum(1 for t in trades if not t["strategy"].startswith("baseline_"))
    n_base  = sum(1 for t in trades if t["strategy"].startswith("baseline_"))
    n_rv5m  = sum(1 for t in trades if t.get("entry_rv5m") is not None)

    print(f"\nData: {n_total} closed trades | {n_strat} strategy | {n_base} baseline | {n_rv5m} with rv_5m")

    if n_rv5m == 0:
        print("\nNOTE: No rv_5m data at entry yet. The microstructure v1.8 collector")
        print("must run for at least 5 minutes before rv_5m values are populated.")
        print("Sweep will use fixed SL/TP floors for all trades (same as v1.7 behavior).")
        print("Re-run this report after 24h of v1.8 data accumulation.")

    # rv_5m distribution
    print_rv5m_distribution(trades)

    # Sweep for each strategy
    strategies = ["momentum_strict", "pullback_strict", "momentum_rank", "pullback_rank"]
    for strategy in strategies:
        results = run_sweep(trades, strategy, args.min_pairs)
        print_sweep(strategy, results)
        print_conditional_drift(trades, strategy)

    # Best config across all strategies
    print(f"\n{'='*80}")
    print("CROSS-STRATEGY BEST CONFIGS")
    print(f"{'='*80}")
    for strategy in strategies:
        results = run_sweep(trades, strategy, args.min_pairs)
        if results:
            best = results[0]
            ci_str = f"[{best['ci_lo']:+.2f}%, {best['ci_hi']:+.2f}%]"
            confirmed = "CONFIRMED" if best["ci_lo"] > 0 else "unconfirmed"
            print(f"  {strategy:<30} k_sl={best['k_sl']} k_tp={best['k_tp']} "
                  f"mean_Δ={best['mean_delta']:+.3f}% CI={ci_str} ({confirmed})")
        else:
            print(f"  {strategy:<30} insufficient data")

    print(f"\n{'='*80}")
    print("CAVEATS")
    print(f"{'='*80}")
    print("  1. Retrospective simulation: path-dependent effects not captured.")
    print("     A wider SL may have prevented premature exits that later recovered.")
    print("     True benefit of adaptive exits is likely HIGHER than shown here.")
    print("  2. rv_5m at entry is only available for trades opened after v1.8 deploy.")
    print("     Older trades use fixed floors (k_sl/k_tp have no effect on them).")
    print("  3. Vol no-trade filter removes high-vol entries from the strategy sample.")
    print("     This changes the composition of the sample, not just the exit policy.")
    print("  4. Bootstrap CI with n<30 is approximate. Treat as directional signal.")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
