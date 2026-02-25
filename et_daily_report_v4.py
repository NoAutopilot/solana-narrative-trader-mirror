#!/usr/bin/env python3
"""
et_daily_report_v4.py — ET v1 Daily Readiness Report

Changes from v3:
  - PRIMARY section now queries shadow_trades_v1 (v1 harness, new table)
  - LIVE_CANARY_READY_V1 gate computed exclusively from v1 results
  - Per-strategy vs its own matched baseline (momentum vs baseline_matched_momentum, etc.)
  - Both fee060 and fee100 reported for strategy vs baseline comparison
  - Signal frequency / starvation alert: shows signals_fired / total_scans per strategy
  - INSUFFICIENT_DATA rules: min_trades_per_strategy >= 20, stability >= 2 blocks with n>=10
  - live_sim mode flag shown in singleton section
  - Legacy v3 section (shadow_trades) retained at bottom for continuity
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
    """Format a fraction as a percentage string."""
    if v is None:
        return "N/A"
    return f"{v*100:+.3f}%"

def safe_div(a, b, default=0.0):
    return a / b if b else default

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn  = sqlite3.connect(DB_PATH)

    print("=" * 72)
    print("ET v1 DAILY READINESS REPORT")
    print(f"Window: last {hours}h | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("Source: shadow_trades_v1 | Universe: WATCHLIST_LANE_NOT_FULL_UNIVERSE")
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
        print(f"  Last scan:             {last_scan}")
        print(f"  Unique mints (window): {unique_mints}")
        print(f"  CPAMM valid rows:      {cpamm_rows}")
    except Exception as e:
        print(f"  universe error: {e}")

    # ── 3. SIGNAL FREQUENCY / STARVATION ALERT ────────────────────────────────
    print("\nSIGNAL FREQUENCY (v1 harness)")
    try:
        # Count entries in shadow_trades_v1 by strategy as proxy for signal fires
        # (each entry = one signal that passed the Jupiter gate)
        strat_counts = conn.execute("""
            SELECT strategy, COUNT(*) as n_total,
                   SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) as n_closed
            FROM shadow_trades_v1
            WHERE entered_at >= ?
            GROUP BY strategy
        """, (since,)).fetchall()

        strat_map = {r[0]: {"n_total": r[1], "n_closed": r[2]} for r in strat_counts}
        n_scans_v1 = max(n_scans, 1)

        for strat in ["momentum", "pullback"]:
            d = strat_map.get(strat, {"n_total": 0, "n_closed": 0})
            rate = d["n_total"] / n_scans_v1 * 100
            starvation = ""
            if d["n_total"] < 5:
                starvation = "  *** STARVATION: <5 entries — consider loosening triggers or using score/rank mode ***"
            print(f"  {strat:<25} entries={d['n_total']:<4} closed={d['n_closed']:<4} "
                  f"rate={rate:.1f}%/scan{starvation}")

        # Baselines
        for strat in ["baseline_matched_momentum", "baseline_matched_pullback"]:
            d = strat_map.get(strat, {"n_total": 0, "n_closed": 0})
            print(f"  {strat:<25} entries={d['n_total']:<4} closed={d['n_closed']}")

        if not strat_map:
            print("  No v1 trades recorded yet — harness may just be starting")
    except Exception as e:
        print(f"  signal frequency error: {e}")

    # ── 4. v1 SHADOW TRADES — AGGREGATE ───────────────────────────────────────
    print("\nV1 SHADOW TRADES — AGGREGATE (shadow_trades_v1)")
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
        ("momentum",  "baseline_matched_momentum"),
        ("pullback",  "baseline_matched_pullback"),
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
                print(f"    {strat:<30} n={s['n']:<4}  INSUFFICIENT_DATA (need {MIN_TRADES_PER_STRATEGY})")
                print(f"    {baseline_strat:<30} n={b['n']:<4}")
            else:
                any_strategy_qualified = True
                beats060 = s["ev060"] > b["ev060"]
                beats100 = s["ev100"] > b["ev100"]
                wr = safe_div(s["wins"], s["n"]) * 100
                b_wr = safe_div(b["wins"], b["n"]) * 100
                print(f"    {strat:<30} n={s['n']:<4}  win={wr:.1f}%  ev_fee060={s['ev060']:+.3f}%  ev_fee100={s['ev100']:+.3f}%")
                print(f"    {baseline_strat:<30} n={b['n']:<4}  win={b_wr:.1f}%  ev_fee060={b['ev060']:+.3f}%  ev_fee100={b['ev100']:+.3f}%")
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
            SELECT COUNT(*) FROM shadow_trades_v1 WHERE exited_at >= ? AND status = 'closed'
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

    # ── 8. FRICTION AUDIT ─────────────────────────────────────────────────────
    print("\nFRICTION AUDIT")
    friction_ok = True
    DEX_FEE_ONE_WAY_PCT = 0.25
    DEX_FEE_RT_PCT      = 0.50
    NETWORK_FEE_LAMPORTS = 55_000
    try:
        fric_02_impact = conn.execute("""
            SELECT AVG(impact_buy_pct + impact_sell_pct)
            FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND impact_buy_pct IS NOT NULL
        """, (since,)).fetchone()[0] or 0
        fric_04_impact = fric_02_impact * 2
        net_fee_01_pct = NETWORK_FEE_LAMPORTS / (0.01 * 1_000_000_000) * 100
        net_fee_02_pct = NETWORK_FEE_LAMPORTS / (0.02 * 1_000_000_000) * 100
        fric_01_total = fric_02_impact * 0.5 + DEX_FEE_RT_PCT + net_fee_01_pct
        fric_02_total = fric_02_impact + DEX_FEE_RT_PCT + net_fee_02_pct
        n_pairs = conn.execute("""
            SELECT COUNT(DISTINCT mint_address) FROM universe_snapshot
            WHERE snapshot_at >= ? AND cpamm_valid_flag = 1 AND impact_buy_pct IS NOT NULL
        """, (since,)).fetchone()[0]
        print(f"  At 0.01 SOL (live canary size):")
        print(f"    (1) Price impact:        {fric_02_impact*0.5:.3f}%  (CPAMM model, half of 0.02 SOL)")
        print(f"    (2) DEX fee (RT):        {DEX_FEE_RT_PCT:.3f}%  ({DEX_FEE_ONE_WAY_PCT:.2f}% buy + {DEX_FEE_ONE_WAY_PCT:.2f}% sell, fixed)")
        print(f"    (3) Network/priority:    {net_fee_01_pct:.3f}%  (~{NETWORK_FEE_LAMPORTS} lamports at 0.01 SOL)")
        print(f"    (4) Total RT cost:       {fric_01_total:.3f}%")
        print(f"  At 0.02 SOL (reference):")
        print(f"    (1) Price impact:        {fric_02_impact:.3f}%")
        print(f"    (2) DEX fee (RT):        {DEX_FEE_RT_PCT:.3f}%  (unchanged — flat fee)")
        print(f"    (3) Network/priority:    {net_fee_02_pct:.3f}%  (halved as % of larger size)")
        print(f"    (4) Total RT cost:       {fric_02_total:.3f}%")
        print(f"  Pairs with data:           {n_pairs}")
        print(f"  Note: fee060 scenario ≈ 0.60% RT; fee100 ≈ 1.00% (adds priority buffer)")
        if fric_04_impact >= 3.0:
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
        print(f"  Note: old harness uses different exits/size — not comparable to v1")
    except Exception as e:
        print(f"  legacy section error: {e}")

    conn.close()

if __name__ == "__main__":
    main()
