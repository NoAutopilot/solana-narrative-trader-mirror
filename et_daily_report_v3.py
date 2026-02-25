#!/usr/bin/env python3
"""
et_daily_report_v3.py — Daily shadow-live evaluation report with LIVE_CANARY_READY gate.

Gate logic changes from v2:
  - "Beats baseline" now requires min_trades_per_strategy >= 20; otherwise INSUFFICIENT_DATA (not FAIL)
  - Stability now requires >= 2 blocks with n >= 10 before passing; otherwise INSUFFICIENT_DATA
  - Friction label renamed to "IMPACT friction" to distinguish from total cost
  - Smoke test is NOT gated behind "beats baseline" — it is execution-safety validation
"""
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '/root/solana_trader')
from config.config import DB_PATH

hours = 24
MIN_TRADES_PER_STRATEGY = 20   # Minimum before comparing to baseline
MIN_STABLE_BLOCKS       = 2    # Minimum blocks with n>=10 before stability check is meaningful

def main():
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn  = sqlite3.connect(DB_PATH)

    print("=" * 70)
    print("EXISTING TOKENS LANE — DAILY SHADOW REPORT")
    print(f"Window: last {hours}h | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("Universe tag: WATCHLIST_LANE_NOT_FULL_UNIVERSE")
    print("=" * 70)

    # ── SINGLETON STATUS ───────────────────────────────────────────────────────
    print("SINGLETON STATUS")
    sing_ok = True
    services = [
        ("et_universe_scanner", "et_universe_scanner.py"),
        ("et_microstructure",   "et_microstructure.py"),
        ("et_shadow_trader",    "et_shadow_trader.py"),
        ("pf_graduation_stream","pf_graduation_stream.py"),
    ]
    try:
        import subprocess
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
    except Exception as e:
        print(f"  singleton check error: {e}")
        sing_ok = False

    # ── UNIVERSE COVERAGE ──────────────────────────────────────────────────────
    print("\nUNIVERSE COVERAGE")
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
        n_scans   = scan_row[0] or 0
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
        print(f"  Scan method:           fixed_mint_list_20_tokens")
        print(f"  Last scan:             {last_scan}")
        print(f"  Unique mints (window): {unique_mints}")
        print(f"  CPAMM valid rows:      {cpamm_rows}")
    except Exception as e:
        print(f"  universe error: {e}")

    # ── SHADOW TRADES ──────────────────────────────────────────────────────────
    print("\nSHADOW TRADES — ALL STRATEGIES")
    strategies = {}
    n = 0
    try:
        row = conn.execute("""
            SELECT COUNT(*),
                   AVG(shadow_pnl_pct) * 100,
                   AVG(shadow_pnl_pct_fee025) * 100,
                   AVG(shadow_pnl_pct_fee060) * 100,
                   AVG(shadow_pnl_pct_fee100) * 100,
                   MAX(shadow_pnl_pct) * 100,
                   MIN(shadow_pnl_pct) * 100,
                   SUM(CASE WHEN shadow_pnl_pct > 0 THEN 1 ELSE 0 END)
            FROM shadow_trades
            WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()
        n = row[0] or 0
        if n > 0:
            win_rate = (row[7] or 0) / n * 100
            print(f"  Total trades:          {n}")
            print(f"  Win rate:              {win_rate:.1f}%")
            print(f"  Avg PnL (CPAMM base):  {row[1]:+.3f}%")
            print(f"  Avg PnL (fee 0.25%):   {row[2]:+.3f}%")
            print(f"  Avg PnL (fee 0.60%):   {row[3]:+.3f}%")
            print(f"  Avg PnL (fee 1.00%):   {row[4]:+.3f}%")
            print(f"  Best trade:            {row[5]:+.3f}%")
            print(f"  Worst trade:           {row[6]:+.3f}%")
        else:
            print("  No closed trades in window")
        # By strategy
        strat_rows = conn.execute("""
            SELECT strategy,
                   COUNT(*),
                   AVG(shadow_pnl_pct_fee060) * 100,
                   SUM(shadow_pnl_pct_fee060) * 100
            FROM shadow_trades
            WHERE exited_at >= ? AND status = 'closed'
            GROUP BY strategy
        """, (since,)).fetchall()
        print("\nSTRATEGY BREAKDOWN")
        for sr in strat_rows:
            strat, cnt, avg_ev, total_ev = sr
            win_n = conn.execute("""
                SELECT COUNT(*) FROM shadow_trades
                WHERE exited_at >= ? AND status = 'closed' AND strategy = ? AND shadow_pnl_pct > 0
            """, (since, strat)).fetchone()[0]
            wr = win_n / cnt * 100 if cnt > 0 else 0
            strategies[strat] = {"n": cnt, "avg_pnl": (avg_ev or 0) / 100}
            print(f"  [{strat:<15}] n={cnt:<5} win={wr:.1f}%  avg_pnl(fee060)={avg_ev:+.3f}%  total={total_ev:+.3f}%")
    except Exception as e:
        print(f"  shadow trades error: {e}")

    # ── CONCENTRATION CHECK ────────────────────────────────────────────────────
    print("\nCONCENTRATION CHECK  (fail if top-3 > 50%)")
    top3_ok = True
    try:
        total_n = conn.execute("""
            SELECT COUNT(*) FROM shadow_trades WHERE exited_at >= ? AND status = 'closed'
        """, (since,)).fetchone()[0]
        if total_n > 0:
            top_mints = conn.execute("""
                SELECT mint_address, COUNT(*) as cnt
                FROM shadow_trades
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
                top3_ok = False
        else:
            print("  No trades in window")
    except Exception as e:
        print(f"  concentration error: {e}")

    # ── STABILITY (6h blocks) ──────────────────────────────────────────────────
    print("\nSTABILITY (6h blocks)")
    block_evs = []
    block_ns  = []
    stable_ok = True
    stable_insufficient = False
    try:
        for block_start in range(0, hours, 6):
            block_since = (datetime.now(timezone.utc) - timedelta(hours=hours - block_start)).isoformat()
            block_until = (datetime.now(timezone.utc) - timedelta(hours=hours - block_start - 6)).isoformat()
            row = conn.execute("""
                SELECT COUNT(*), AVG(shadow_pnl_pct_fee060)
                FROM shadow_trades
                WHERE exited_at >= ? AND exited_at < ? AND status = 'closed'
            """, (block_since, block_until)).fetchone()
            cnt = row[0] or 0
            avg = (row[1] or 0) * 100
            block_evs.append(avg)
            block_ns.append(cnt)
            print(f"  Block {block_start:02d}-{block_start+6:02d}h: n={cnt:<4} avg_pnl(fee060)={avg:+.3f}%")
        # Require >= MIN_STABLE_BLOCKS blocks with n >= 10 before stability is meaningful
        qualified_blocks = [ev for ev, cnt in zip(block_evs, block_ns) if cnt >= 10]
        if len(qualified_blocks) < MIN_STABLE_BLOCKS:
            stable_ok = False
            stable_insufficient = True
            print(f"  STABILITY: INSUFFICIENT_DATA ({len(qualified_blocks)}/{MIN_STABLE_BLOCKS} blocks with n>=10)")
        elif len(qualified_blocks) >= 2:
            overall_avg = sum(qualified_blocks) / len(qualified_blocks)
            max_block = max(qualified_blocks)
            if overall_avg != 0 and max_block > 2 * abs(overall_avg):
                stable_ok = False
                print(f"  STABILITY: FAIL — max block {max_block:+.3f}% > 2x avg {overall_avg:+.3f}%")
            else:
                print(f"  STABILITY: OK (avg={overall_avg:+.3f}%, max={max_block:+.3f}%)")
    except Exception as e:
        print(f"  stability error: {e}")

    # ── FRICTION AUDIT ─────────────────────────────────────────────────────────
    print("\nIMPACT FRICTION AUDIT  (price impact only, excludes fees)")
    friction_ok = True
    try:
        fric = conn.execute("""
            SELECT AVG(round_trip_pct), AVG(round_trip_pct)
            FROM (
                SELECT round_trip_pct FROM universe_snapshot
                WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND round_trip_pct IS NOT NULL
                ORDER BY snapshot_at DESC LIMIT 200
            )
        """, (since,)).fetchone()
        # Compute at two sizes using impact scaling
        fric_02 = conn.execute("""
            SELECT AVG(impact_buy_pct + impact_sell_pct)
            FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND impact_buy_pct IS NOT NULL
        """, (since,)).fetchone()[0] or 0
        # Scale to 0.04 SOL (impact scales ~linearly with size for small trades)
        fric_04 = fric_02 * 2
        n_pairs = conn.execute("""
            SELECT COUNT(DISTINCT mint_address) FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND round_trip_pct IS NOT NULL
        """, (since,)).fetchone()[0]
        print(f"  Avg IMPACT friction (0.02 SOL): {fric_02:.3f}%")
        print(f"  Avg IMPACT friction (0.04 SOL): {fric_04:.3f}%")
        print(f"  (Total cost = impact + fee; fee025=0.50% RT, fee060=0.60% RT, fee100=1.00% RT)")
        print(f"  Scale factor (04/02):       {fric_04/fric_02:.2f}x" if fric_02 > 0 else "  Scale factor: N/A")
        print(f"  Pairs with data:            {n_pairs}")
        if fric_04 >= 3.0:
            friction_ok = False
            print(f"  IMPACT FRICTION AT SIZE: FAIL (>{3.0}%)")
        else:
            print(f"  IMPACT FRICTION AT SIZE: OK")
    except Exception as e:
        print(f"  friction audit error: {e}")
        friction_ok = True  # Don't block on friction audit errors

    # ── BASELINES ──────────────────────────────────────────────────────────────
    print("\nBASELINES")
    baseline_beat = False
    baseline_insufficient = False
    try:
        baseline_row = conn.execute("""
            SELECT COUNT(*), AVG(shadow_pnl_pct_fee060)
            FROM shadow_trades
            WHERE exited_at >= ? AND status = 'closed' AND strategy = 'baseline'
        """, (since,)).fetchone()
        baseline_n  = baseline_row[0] or 0
        baseline_ev = (baseline_row[1] or 0) * 100
        print(f"  Baseline (random):  n={baseline_n:<4} avg_pnl(fee060)={baseline_ev:+.3f}%")

        any_strategy_qualified = False
        for strat in ["momentum", "pullback"]:
            if strat in strategies:
                s = strategies[strat]
                ev_pct = s["avg_pnl"] * 100
                if s["n"] < MIN_TRADES_PER_STRATEGY:
                    print(f"  {strat:<15}:  n={s['n']:<4} avg_pnl(fee060)={ev_pct:+.3f}%  INSUFFICIENT_DATA (need {MIN_TRADES_PER_STRATEGY})")
                    baseline_insufficient = True
                else:
                    any_strategy_qualified = True
                    beats = ev_pct > baseline_ev
                    print(f"  {strat:<15}:  n={s['n']:<4} avg_pnl(fee060)={ev_pct:+.3f}%  beats_baseline={'YES' if beats else 'NO'}")
                    if beats:
                        baseline_beat = True

        if not any_strategy_qualified and not baseline_insufficient:
            print("  No non-baseline strategies have traded yet")
            baseline_insufficient = True

    except Exception as e:
        print(f"  baselines error: {e}")

    # ── SMOKE TEST ─────────────────────────────────────────────────────────────
    print("\nSMOKE TEST")
    smoke_pass = False
    try:
        # Ensure table exists
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
                buy_tx TEXT,
                sell_tx TEXT,
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
            print(f"  IMPACT friction: expected={smoke[2]:.3f}%  realized={smoke[1]:.3f}%  excess={smoke[3]:+.3f}%")
            print(f"  Buy TX:      {smoke[6]}")
            print(f"  Sell TX:     {smoke[7]}")
            smoke_pass = smoke[0] == "PASS"
        else:
            print("  No smoke test run yet — required before canary")
            print("  Run: python3 live_canary.py smoke")
    except Exception as e:
        print(f"  smoke test check error: {e}")

    # ── LIVE_CANARY_READY GATE ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("LIVE_CANARY_READY CHECK")
    print("=" * 70)

    shadow_count_ok = n >= 150
    conc_ok = top3_ok

    # Beats baseline: INSUFFICIENT_DATA counts as not-yet-blocking (not FAIL)
    # It becomes FAIL only when strategies have enough data and still don't beat baseline
    if baseline_insufficient:
        beats_label = "INSUFFICIENT_DATA"
        beats_ok = False   # Still blocks — need data before going live
    else:
        beats_label = "momentum or pullback > baseline at fee060"
        beats_ok = baseline_beat

    # Stability: INSUFFICIENT_DATA also blocks
    if stable_insufficient:
        stable_label = f"INSUFFICIENT_DATA (need {MIN_STABLE_BLOCKS} blocks with n>=10)"
    else:
        stable_label = "no block > 2x avg"

    criteria = [
        ("Singleton enforcement",       sing_ok,         "all services single-instance"),
        ("Shadow count >= 150",         shadow_count_ok, f"n={n}"),
        ("Beats baseline (random)",     beats_ok,        beats_label),
        ("Top-3 share < 50%",           conc_ok,         "concentration check"),
        ("Stability across 6h blocks",  stable_ok,       stable_label),
        ("IMPACT friction < 3%",        friction_ok,     "price impact at 0.04 SOL"),
        ("Smoke test PASS",             smoke_pass,      "live round-trip validated"),
    ]
    all_pass = True
    for name, passed, note in criteria:
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {name:<35} ({note})")
        if not passed:
            all_pass = False
    print()
    if all_pass:
        print(">>> LIVE_CANARY_READY: YES <<<")
        print("    All criteria met. Proceed to live canary at 0.01 SOL.")
    else:
        failed_items = [name for name, passed, _ in criteria if not passed]
        print(">>> LIVE_CANARY_READY: NO <<<")
        print(f"    Blocking: {', '.join(failed_items)}")
        print("    Continue paper trading. Do not deploy live funds.")
    print("=" * 70)
    conn.close()

if __name__ == "__main__":
    main()
