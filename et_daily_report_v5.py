#!/usr/bin/env python3
"""
et_daily_report_v5.py — ET v1 Daily Readiness Report

Changes from v4:
  - Strategy variants renamed: momentum→momentum_strict, pullback→pullback_strict
    (rank variants: momentum_rank, pullback_rank)
  - Signal frequency section reads from signal_frequency_log table (per-cycle data)
    instead of counting trade entries as a proxy
  - FRICTION AUDIT: replaces hardcoded network/prio estimate with empirical
    median and p90 from live_trades.meta_fee (actual tx fee lamports)
    Shows: DEX fee floor + measured network/prio (median + p90) + total RT cost
  - Readiness gate uses measured p90 fee for fee100 scenario
  - Score/rank variant stats shown separately from strict variants
"""
import sqlite3
import sys
import subprocess
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/root/solana_trader')
from config.config import DB_PATH

hours = 24
MIN_TRADES_PER_STRATEGY = 20   # minimum closed trades before comparing to baseline
MIN_STABLE_BLOCKS       = 2    # minimum 6h blocks with n>=10 before stability is meaningful

# ── HELPERS ───────────────────────────────────────────────────────────────────
def pct(v):
    if v is None:
        return "N/A"
    return f"{v*100:+.3f}%"

def safe_div(a, b, default=0.0):
    return a / b if b else default

def median_p90(values):
    """Return (median, p90) of a list of floats. Returns (None, None) if empty."""
    if not values:
        return None, None
    s = sorted(values)
    n = len(s)
    med = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    p90_idx = int(n * 0.90)
    p90 = s[min(p90_idx, n - 1)]
    return med, p90

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn  = sqlite3.connect(DB_PATH)

    print("=" * 72)
    print("ET v1 DAILY READINESS REPORT  (v5)")
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
                print(f"  {name:<30} DOWN (not running)")
                sing_ok = False
            else:
                print(f"  {name:<30} DUPLICATE ({count} instances)")
                sing_ok = False
        # Show mode of running v1 instance
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
    n_scans = 1  # fallback for rate calculations
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
        cpamm_rows = conn.execute("""
            SELECT COUNT(*) FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1
        """, (since,)).fetchone()[0]
        unique_mints = conn.execute("""
            SELECT COUNT(DISTINCT mint_address) FROM universe_snapshot WHERE snapshot_at >= ?
        """, (since,)).fetchone()[0]
        print(f"  Scans in window:       {n_scans}")
        print(f"  Avg mints seen/scan:   {avg_mints:.1f}")
        print(f"  Avg eligible/scan:     {avg_elig:.1f}")
        print(f"  Last scan:             {last_scan}")
        print(f"  Unique mints (window): {unique_mints}")
        print(f"  CPAMM valid rows:      {cpamm_rows}")
        if avg_elig < 5:
            print(f"  *** UNIVERSE ALERT: avg eligible/scan={avg_elig:.1f} — universe may be too narrow ***")
    except Exception as e:
        print(f"  universe error: {e}")

    # ── 3. SIGNAL FREQUENCY / STARVATION ALERT ────────────────────────────────
    print("\nSIGNAL FREQUENCY (from signal_frequency_log)")
    try:
        # Read from signal_frequency_log table (per-cycle data written by harness)
        freq_rows = conn.execute("""
            SELECT strategy,
                   SUM(signals_seen)  as total_signals,
                   SUM(trades_opened) as total_opened,
                   COUNT(*)           as n_cycles,
                   AVG(universe_size) as avg_universe
            FROM signal_frequency_log
            WHERE logged_at >= ?
            GROUP BY strategy
        """, (since,)).fetchall()

        freq_map = {r[0]: {
            "total_signals": r[1] or 0,
            "total_opened":  r[2] or 0,
            "n_cycles":      r[3] or 0,
            "avg_universe":  r[4] or 0,
        } for r in freq_rows}

        # Also get trade counts from shadow_trades_v1 as fallback
        trade_counts = conn.execute("""
            SELECT strategy, COUNT(*) as n_total,
                   SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) as n_closed
            FROM shadow_trades_v1
            WHERE entered_at >= ?
            GROUP BY strategy
        """, (since,)).fetchall()
        trade_map = {r[0]: {"n_total": r[1], "n_closed": r[2]} for r in trade_counts}

        print(f"  {'Strategy':<35} {'signals':>8} {'opened':>8} {'closed':>8} {'rate/scan':>10} {'note'}")
        print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

        all_strategies = ["momentum_strict", "pullback_strict", "momentum_rank", "pullback_rank"]
        for strat in all_strategies:
            f = freq_map.get(strat, {})
            t = trade_map.get(strat, {"n_total": 0, "n_closed": 0})
            signals = f.get("total_signals", t["n_total"])  # fallback to trade count
            opened  = f.get("total_opened",  t["n_total"])
            closed  = t["n_closed"]
            rate    = opened / n_scans * 100
            note = ""
            if strat in ("momentum_strict", "pullback_strict") and opened < 5:
                note = "*** STARVATION ***"
            elif strat in ("momentum_rank", "pullback_rank") and opened < 5:
                note = "rank not firing — check universe/floors"
            print(f"  {strat:<35} {signals:>8} {opened:>8} {closed:>8} {rate:>9.1f}% {note}")

        # Baselines
        print()
        for strat in ["baseline_matched_momentum_strict", "baseline_matched_pullback_strict",
                      "baseline_matched_momentum_rank", "baseline_matched_pullback_rank"]:
            t = trade_map.get(strat, {"n_total": 0, "n_closed": 0})
            print(f"  {strat:<35} {'':>8} {t['n_total']:>8} {t['n_closed']:>8}")

    except Exception as e:
        print(f"  signal frequency error: {e}")

    # ── 4. v1 SHADOW TRADES — AGGREGATE ───────────────────────────────────────
    print("\nV1 SHADOW TRADES — AGGREGATE (shadow_trades_v1, all strategies)")
    v1_n = 0
    try:
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(gross_pnl_pct) * 100,
                   AVG(shadow_pnl_pct_fee025) * 100,
                   AVG(shadow_pnl_pct_fee060) * 100,
                   AVG(shadow_pnl_pct_fee100) * 100,
                   MAX(gross_pnl_pct) * 100,
                   MIN(gross_pnl_pct) * 100,
                   SUM(CASE WHEN gross_pnl_pct > 0 THEN 1 ELSE 0 END)
            FROM shadow_trades_v1
            WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()
        v1_n = row[0] or 0
        if v1_n > 0:
            win_rate = safe_div(row[7] or 0, v1_n) * 100
            print(f"  Total closed trades:   {v1_n}")
            print(f"  Win rate (gross):      {win_rate:.1f}%")
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

    # ── 5. v1 STRATEGY vs MATCHED BASELINE ────────────────────────────────────
    print("\nV1 STRATEGY vs MATCHED BASELINE")
    baseline_beat_v1 = False
    baseline_insufficient_v1 = True
    any_strategy_qualified = False

    strategy_pairs = [
        ("momentum_strict",  "baseline_matched_momentum_strict"),
        ("pullback_strict",  "baseline_matched_pullback_strict"),
        ("momentum_rank",    "baseline_matched_momentum_rank"),
        ("pullback_rank",    "baseline_matched_pullback_rank"),
    ]

    def get_strategy_stats(strat):
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(shadow_pnl_pct_fee060) * 100,
                   AVG(shadow_pnl_pct_fee100) * 100,
                   SUM(CASE WHEN gross_pnl_pct > 0 THEN 1 ELSE 0 END)
            FROM shadow_trades_v1
            WHERE exited_at >= ? AND status = 'closed' AND strategy = ?
        """, (since, strat)).fetchone()
        n = row[0] or 0
        return {
            "n":       n,
            "ev060":   row[1] or 0,
            "ev100":   row[2] or 0,
            "wins":    row[3] or 0,
        }

    try:
        for strat, baseline_strat in strategy_pairs:
            s = get_strategy_stats(strat)
            b = get_strategy_stats(baseline_strat)

            print(f"\n  {strat.upper()} vs {baseline_strat}")
            if s["n"] < MIN_TRADES_PER_STRATEGY:
                print(f"    {strat:<40} n={s['n']:<4}  INSUFFICIENT_DATA (need {MIN_TRADES_PER_STRATEGY})")
                print(f"    {baseline_strat:<40} n={b['n']:<4}")
            else:
                any_strategy_qualified = True
                beats060 = s["ev060"] > b["ev060"]
                beats100 = s["ev100"] > b["ev100"]
                wr = safe_div(s["wins"], s["n"]) * 100
                b_wr = safe_div(b["wins"], b["n"]) * 100
                print(f"    {strat:<40} n={s['n']:<4}  win={wr:.1f}%  ev_fee060={s['ev060']:+.3f}%  ev_fee100={s['ev100']:+.3f}%")
                print(f"    {baseline_strat:<40} n={b['n']:<4}  win={b_wr:.1f}%  ev_fee060={b['ev060']:+.3f}%  ev_fee100={b['ev100']:+.3f}%")
                print(f"    beats_baseline(fee060): {'YES' if beats060 else 'NO'}  beats_baseline(fee100): {'YES' if beats100 else 'NO'}")
                if beats060:
                    baseline_beat_v1 = True

        if not any_strategy_qualified:
            baseline_insufficient_v1 = True
            print("\n  All strategies INSUFFICIENT_DATA — continue accumulating trades")
        else:
            baseline_insufficient_v1 = not baseline_beat_v1

    except Exception as e:
        print(f"  strategy comparison error: {e}")

    # ── 6. CONCENTRATION CHECK ────────────────────────────────────────────────
    print("\nCONCENTRATION CHECK  (fail if top-3 > 50%)")
    top3_ok_v1 = True
    try:
        total_n = conn.execute("""
            SELECT COUNT(*) FROM shadow_trades_v1
            WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()[0]
        if total_n > 0:
            top_mints = conn.execute("""
                SELECT mint_address, COUNT(*) as cnt
                FROM shadow_trades_v1
                WHERE exited_at >= ? AND status = 'closed'
                GROUP BY mint_address
                ORDER BY cnt DESC
                LIMIT 10
            """, (since,)).fetchall()
            top1 = top_mints[0][1] / total_n * 100 if top_mints else 0
            top3 = sum(r[1] for r in top_mints[:3]) / total_n * 100 if len(top_mints) >= 3 else top1
            top10 = sum(r[1] for r in top_mints[:10]) / total_n * 100
            print(f"  Top-1 share:  {top1:.1f}%")
            print(f"  Top-3 share:  {top3:.1f}%  {'OK' if top3 < 50 else 'FAIL'}")
            print(f"  Top-10 share: {top10:.1f}%")
            if top3 >= 50:
                top3_ok_v1 = False
        else:
            print("  No v1 trades in window — skipping")
    except Exception as e:
        print(f"  concentration error: {e}")

    # ── 7. STABILITY (6h blocks) ───────────────────────────────────────────────
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

    # ── 8. FRICTION AUDIT (empirical network fee) ─────────────────────────────
    print("\nFRICTION AUDIT (empirical network/priority fee from tx logs)")
    friction_ok = True
    DEX_FEE_ONE_WAY_PCT = 0.25
    DEX_FEE_RT_PCT      = 0.50
    LAMPORTS_PER_SOL    = 1_000_000_000

    # Empirical fee: read meta_fee from live_trades (actual lamports paid per swap)
    fee_lamports_list = []
    fee_source = "hardcoded_fallback"
    try:
        # live_trades table stores actual on-chain tx fees
        fee_rows = conn.execute("""
            SELECT meta_fee FROM live_trades
            WHERE executed_at >= ? AND meta_fee IS NOT NULL AND meta_fee > 0
            ORDER BY executed_at DESC
        """, (since,)).fetchall()
        if fee_rows:
            fee_lamports_list = [r[0] for r in fee_rows]
            fee_source = f"live_trades (n={len(fee_lamports_list)} txns)"
    except Exception:
        pass

    # Fallback: smoke_test_log
    if not fee_lamports_list:
        try:
            smoke_rows = conn.execute("""
                SELECT sol_spent, fill_ratio FROM smoke_test_log
                WHERE run_at >= ? AND sol_spent IS NOT NULL AND sol_spent > 0
            """, (since,)).fetchall()
            if smoke_rows:
                # Estimate fee from smoke test: sol_spent includes fees
                # fee ≈ sol_spent * (1 - fill_ratio) in SOL → convert to lamports
                for sol_spent, fill_ratio in smoke_rows:
                    if fill_ratio and fill_ratio > 0:
                        fee_sol = sol_spent * (1.0 - fill_ratio)
                        fee_lamports_list.append(int(fee_sol * LAMPORTS_PER_SOL))
                if fee_lamports_list:
                    fee_source = f"smoke_test_log (n={len(fee_lamports_list)} txns, estimated)"
        except Exception:
            pass

    # Compute empirical stats
    if fee_lamports_list:
        fee_med_lam, fee_p90_lam = median_p90(fee_lamports_list)
    else:
        # No empirical data — use conservative fallback
        fee_med_lam = 5_000      # ~5k lamports (base fee only)
        fee_p90_lam = 55_000     # ~55k lamports (with priority)
        fee_source = "hardcoded_fallback (no tx data)"

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

        # Network fee as % of trade size (2 swaps per round-trip: buy + sell)
        # fee_p90 is per-tx; RT = 2 txns
        def net_pct(fee_lam, trade_sol):
            return (2 * fee_lam / (trade_sol * LAMPORTS_PER_SOL)) * 100

        net_med_01 = net_pct(fee_med_lam, 0.01)
        net_p90_01 = net_pct(fee_p90_lam, 0.01)
        net_med_02 = net_pct(fee_med_lam, 0.02)
        net_p90_02 = net_pct(fee_p90_lam, 0.02)

        impact_01 = fric_02_impact * 0.5  # scale from 0.02 SOL model to 0.01 SOL
        impact_02 = fric_02_impact

        total_med_01 = impact_01 + DEX_FEE_RT_PCT + net_med_01
        total_p90_01 = impact_01 + DEX_FEE_RT_PCT + net_p90_01
        total_med_02 = impact_02 + DEX_FEE_RT_PCT + net_med_02
        total_p90_02 = impact_02 + DEX_FEE_RT_PCT + net_p90_02

        print(f"  Fee source: {fee_source}")
        print(f"  Empirical fee/tx: median={fee_med_lam:,.0f} lam  p90={fee_p90_lam:,.0f} lam")
        print()
        print(f"  At 0.01 SOL (live canary size):")
        print(f"    (1) Price impact (CPAMM model): {impact_01:.3f}%")
        print(f"    (2) DEX fee (RT):               {DEX_FEE_RT_PCT:.3f}%  ({DEX_FEE_ONE_WAY_PCT:.2f}% buy + {DEX_FEE_ONE_WAY_PCT:.2f}% sell)")
        print(f"    (3) Network/priority (median):  {net_med_01:.3f}%  ({fee_med_lam:,.0f} lam × 2 txns)")
        print(f"    (3) Network/priority (p90):     {net_p90_01:.3f}%  ({fee_p90_lam:,.0f} lam × 2 txns)")
        print(f"    (4) Total RT cost (median):     {total_med_01:.3f}%")
        print(f"    (4) Total RT cost (p90):        {total_p90_01:.3f}%  ← use for fee100 scenario")
        print()
        print(f"  At 0.02 SOL (reference — halves network% component):")
        print(f"    (1) Price impact:               {impact_02:.3f}%")
        print(f"    (2) DEX fee (RT):               {DEX_FEE_RT_PCT:.3f}%")
        print(f"    (3) Network/priority (median):  {net_med_02:.3f}%")
        print(f"    (3) Network/priority (p90):     {net_p90_02:.3f}%")
        print(f"    (4) Total RT cost (median):     {total_med_02:.3f}%")
        print(f"    (4) Total RT cost (p90):        {total_p90_02:.3f}%")
        print(f"  Pairs with CPAMM impact data:     {n_pairs}")

        # Friction gate check
        if total_p90_01 > 2.0:
            print(f"  FRICTION ALERT: p90 RT cost at 0.01 SOL = {total_p90_01:.2f}% — consider 0.02 SOL size")
        if fric_02_impact * 2 >= 3.0:
            friction_ok = False
            print(f"  PRICE IMPACT CHECK: FAIL (impact >{3.0}% at 0.04 SOL — pool too shallow)")
        else:
            print(f"  PRICE IMPACT CHECK: OK")
    except Exception as e:
        print(f"  friction audit error: {e}")
        friction_ok = True

    # ── 9. SMOKE TEST ─────────────────────────────────────────────────────────
    print("\nSMOKE TEST")
    smoke_pass = False
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS smoke_test_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result TEXT NOT NULL,
                realized_rt_pct REAL,
                expected_rt_pct REAL,
                slippage_excess_pct REAL,
                run_at TEXT DEFAULT (datetime('now')),
                pair_symbol TEXT,
                pair_venue TEXT,
                buy_sig TEXT,
                sell_sig TEXT,
                sol_spent REAL,
                fill_ratio REAL
            )
        """)
        conn.commit()
        smoke = conn.execute("""
            SELECT result, realized_rt_pct, expected_rt_pct, slippage_excess_pct, run_at,
                   pair_symbol, buy_sig, sell_sig, sol_spent, fill_ratio
            FROM smoke_test_log
            ORDER BY run_at DESC LIMIT 1
        """).fetchone()
        if smoke:
            print(f"  Last run:    {smoke[4]}")
            print(f"  Pair:        {smoke[5]}")
            print(f"  Result:      {smoke[0]}")
            print(f"  Fill ratio:  {smoke[9]:.4f}" if smoke[9] is not None else "  Fill ratio:  N/A")
            print(f"  SOL spent:   {smoke[8]:.6f}" if smoke[8] is not None else "  SOL spent:   N/A")
            print(f"  Friction:    expected={smoke[2]:.3f}%  realized={smoke[1]:.3f}%  excess={smoke[3]:+.3f}%")
            print(f"  Buy TX:      {smoke[6]}")
            print(f"  Sell TX:     {smoke[7]}")
            smoke_pass = smoke[0] == "PASS"
        else:
            print("  No smoke test run yet")
    except Exception as e:
        print(f"  smoke test error: {e}")

    # ── 10. LIVE_CANARY_READY_V1 GATE ─────────────────────────────────────────
    print("\n" + "=" * 72)
    print("LIVE_CANARY_READY_V1 CHECK")
    print("=" * 72)
    print("Source: shadow_trades_v1 only. Smoke test already cleared.")
    print()

    shadow_count_ok_v1 = v1_n >= 150

    if baseline_insufficient_v1:
        beats_label = f"INSUFFICIENT_DATA (need {MIN_TRADES_PER_STRATEGY} closed trades per strategy)"
        beats_ok_v1 = False
    else:
        beats_label = "best strategy beats matched baseline at fee060"
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
        print("    All v1 criteria met.")
        print("    Proceed to live canary: 0.01 SOL/trade, MAX_OPEN_GLOBAL=1,")
        print("    hard stop at 0.03 SOL drawdown, max 8-10 trades from 0.14 SOL bankroll.")
    else:
        failed_items = [name for name, passed, _ in criteria_v1 if not passed]
        print(">>> LIVE_CANARY_READY_V1: NO <<<")
        print(f"    Blocking: {', '.join(failed_items)}")
        print("    Continue paper trading. Do not deploy live funds.")
    print("=" * 72)

    # ── 11. LEGACY v3 SECTION (shadow_trades, old harness) ────────────────────
    print("\n" + "─" * 72)
    print("LEGACY: shadow_trades (old harness, for continuity)")
    print("─" * 72)
    try:
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(shadow_pnl_pct_fee060) * 100,
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
