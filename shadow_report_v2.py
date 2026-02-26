#!/usr/bin/env python3
"""
shadow_report_v2.py — Run-scoped and signature-pooled delta report for shadow trader.

MODES:
  STRICT (default):
    python3 shadow_report_v2.py --run_id 9a74d448
    Requires --run_id. Hard error without it. Reports on exactly one run.

  POOLED (explicit opt-in):
    python3 shadow_report_v2.py --combine_signature --signature abc123def456
    python3 shadow_report_v2.py --combine_signature --version v1.15
    python3 shadow_report_v2.py --combine_signature --version v1.15 --commit fd0aa68
    Pools ALL runs matching the given signature (or version+commit).
    ALWAYS prints the full list of included run_ids so you can verify.
    NEVER silently falls back to ALL runs.

GUARANTEES:
  - run_id=ALL is IMPOSSIBLE in both modes.
  - PnL stored as decimal fraction; displayed as % (x100 everywhere).
  - n_closed_pairs = join-based only (baseline_trigger_id join).
  - exit_reason='rollover_close' excluded from all PnL summaries.
  - missing_baseline=0 and invalid_pair=0 are checked and flagged.
"""

import sys
import sqlite3
import argparse
import random
import json
from datetime import datetime, timezone

DB = "/root/solana_trader/data/solana_trader.db"

# ── CLI ────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Shadow trader run-scoped report. --run_id is MANDATORY in strict mode."
)
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--run_id",
    help="STRICT MODE: exact run_id prefix to report on (required)")
group.add_argument("--combine_signature", action="store_true",
    help="POOLED MODE: pool all runs matching the given signature/version")

parser.add_argument("--signature",
    help="POOLED MODE: exact 16-char sha256 prefix from run_registry.signature")
parser.add_argument("--version",
    help="POOLED MODE: version string to match (e.g. v1.15)")
parser.add_argument("--commit",
    help="POOLED MODE: git_commit prefix to additionally filter by")
parser.add_argument("--mode", choices=["mini", "decision", "auto"], default="auto",
    help="mini=pair health (n>=3), decision=full (n>=20), auto=pick by n")
args = parser.parse_args()

# ── Validate pooled mode args ──────────────────────────────────────────────
if args.combine_signature:
    if not args.signature and not args.version:
        print("ERROR: --combine_signature requires either --signature or --version (or both).")
        print("  Example: --combine_signature --version v1.15")
        print("  Example: --combine_signature --signature abc123def456")
        sys.exit(1)

# ── DB ─────────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ── Resolve included run_ids ───────────────────────────────────────────────
POOL_MODE = args.combine_signature

if not POOL_MODE:
    # STRICT MODE — exactly one run_id
    rid_rows = conn.execute(
        "SELECT run_id, version, git_commit, start_ts, signature FROM run_registry "
        "WHERE run_id LIKE ? ORDER BY start_ts DESC LIMIT 1",
        (args.run_id + "%",)
    ).fetchall()
    if not rid_rows:
        print(f"ERROR: run_id '{args.run_id}' not found in run_registry. Aborting.")
        sys.exit(1)
    included_runs = [dict(r) for r in rid_rows]
    SCOPE_LABEL = f"STRICT run_id={included_runs[0]['run_id'][:8]}"

else:
    # POOLED MODE — find all runs matching signature or version+commit
    # Check if signature column exists
    cols = [r[1] for r in conn.execute("PRAGMA table_info(run_registry)").fetchall()]
    has_sig_col = "signature" in cols

    if args.signature:
        if not has_sig_col:
            print("ERROR: run_registry.signature column does not exist yet.")
            print("  Deploy v1.15 first to populate signatures, then use --combine_signature.")
            sys.exit(1)
        rid_rows = conn.execute(
            "SELECT run_id, version, git_commit, start_ts, signature FROM run_registry "
            "WHERE signature LIKE ? ORDER BY start_ts ASC",
            (args.signature + "%",)
        ).fetchall()
        SCOPE_LABEL = f"POOLED signature={args.signature}"
    else:
        # Match by version (and optionally commit)
        if args.commit:
            rid_rows = conn.execute(
                "SELECT run_id, version, git_commit, start_ts, signature FROM run_registry "
                "WHERE version=? AND git_commit LIKE ? ORDER BY start_ts ASC",
                (args.version, args.commit + "%")
            ).fetchall()
            SCOPE_LABEL = f"POOLED version={args.version} commit={args.commit[:8]}"
        else:
            rid_rows = conn.execute(
                "SELECT run_id, version, git_commit, start_ts, signature FROM run_registry "
                "WHERE version=? ORDER BY start_ts ASC",
                (args.version,)
            ).fetchall()
            SCOPE_LABEL = f"POOLED version={args.version}"

    if not rid_rows:
        print(f"ERROR: No runs found matching the given filter. Aborting.")
        sys.exit(1)

    included_runs = [dict(r) for r in rid_rows]

    # Safety check: if pooling by version only (no signature), warn if signatures differ
    if has_sig_col and not args.signature:
        sigs = set(r.get("signature") for r in included_runs if r.get("signature"))
        if len(sigs) > 1:
            print(f"WARNING: Pooling {len(included_runs)} runs with {len(sigs)} DIFFERENT signatures!")
            print("  This means the runs used different configs. Pooling may be unsafe.")
            print("  Signatures found:")
            for r in included_runs:
                print(f"    run_id={r['run_id'][:8]}  sig={r.get('signature','NULL')}")
            print("  Use --signature <SIG> to pool only identical-config runs.")
            print("  Proceeding anyway — check results carefully.")
        elif len(sigs) == 1:
            sig_val = list(sigs)[0]
            print(f"  Signature check: all {len(included_runs)} runs share signature={sig_val}  ✓ SAFE TO POOL")

INCLUDED_RUN_IDS = [r["run_id"] for r in included_runs]
RID = INCLUDED_RUN_IDS[0]  # primary run for single-run metadata

# ── Header ─────────────────────────────────────────────────────────────────
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print("=" * 70)
print("SHADOW TRADER RUN-SCOPED REPORT")
print("=" * 70)
print(f"  scope     : {SCOPE_LABEL}")
print(f"  generated : {now_utc}")
print(f"  dataset   : {len(INCLUDED_RUN_IDS)} run(s) — NO silent ALL")
print()
print("  INCLUDED RUNS:")
for r in included_runs:
    sig_str = r.get("signature") or "NULL (pre-v1.15)"
    print(f"    run_id={r['run_id'][:8]}  version={r.get('version','?'):<6}  "
          f"commit={str(r.get('git_commit') or '')[:8]:<8}  "
          f"sig={sig_str:<16}  started={r.get('start_ts','?')[:19]}")
print("=" * 70)

# ── SQL IN clause helper ───────────────────────────────────────────────────
def in_clause(ids):
    return "(" + ",".join("?" * len(ids)) + ")"

# ── P0.2: PnL scaling proof — 5 sample rows ────────────────────────────────
print("\nP0.2 — PnL SCALING PROOF (stored decimal -> displayed %)")
print("-" * 70)
q = (
    "SELECT trade_id, token_symbol, strategy, gross_pnl_pct, shadow_pnl_pct_fee100 "
    "FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} "
    "AND status='closed' AND exit_reason != 'rollover_close' LIMIT 5"
)
samples = conn.execute(q, INCLUDED_RUN_IDS).fetchall()
if samples:
    print(f"  {'trade_id':<10} {'token':<10} {'gross_decimal':>14} {'gross_pct%':>12} "
          f"{'fee100_decimal':>15} {'fee100_pct%':>12}")
    for s in samples:
        gd = s["gross_pnl_pct"] or 0.0
        fd = s["shadow_pnl_pct_fee100"] or 0.0
        print(f"  {s['trade_id'][:8]:<10} {s['token_symbol']:<10} "
              f"{gd:>14.6f} {gd*100:>11.4f}% {fd:>15.6f} {fd*100:>11.4f}%")
else:
    print("  No closed non-rollover trades yet for included runs.")

# ── FEE FLOOR TRANSPARENCY ────────────────────────────────────────────────
print("\nFEE FLOOR TRANSPARENCY")
print("-" * 70)
print(f"  fee100 formula : gross_pnl_pct - (entry_round_trip_pct + 0.01)")
print(f"  fixed component: 1.00% (0.01 decimal) — identical for strategy and baseline")
print(f"  cpamm_impact   : per-trade buy+sell slippage (stored as entry_round_trip_pct)")
print(f"  Applied IDENTICALLY to strategy and baseline legs")
# Show actual RT costs for closed trades
rt_rows = conn.execute(
    f"SELECT "
    f"  CASE WHEN strategy LIKE 'baseline%' THEN 'baseline' ELSE 'strategy' END AS leg, "
    f"  AVG(entry_round_trip_pct)*100 as avg_rt, "
    f"  MIN(entry_round_trip_pct)*100 as min_rt, "
    f"  MAX(entry_round_trip_pct)*100 as max_rt, "
    f"  COUNT(*) as n "
    f"FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} "
    f"AND status='closed' AND exit_reason != 'rollover_close' "
    f"GROUP BY CASE WHEN strategy LIKE 'baseline%' THEN 'baseline' ELSE 'strategy' END",
    INCLUDED_RUN_IDS
).fetchall()
if rt_rows:
    print(f"\n  {'leg':<12} {'n':>4} {'avg_rt%':>9} {'min_rt%':>9} {'max_rt%':>9}")
    for r in rt_rows:
        print(f"  {r['leg']:<12} {r['n']:>4} {r['avg_rt']:>8.4f}% {r['min_rt']:>8.4f}% {r['max_rt']:>8.4f}%")
else:
    print("  No closed trades yet — RT cost data unavailable.")

# ── P1: INTEGRITY CHECKS ───────────────────────────────────────────────────
print("\nP1 — INTEGRITY CHECKS")
print("-" * 70)

n_strat = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND strategy NOT LIKE 'baseline%'",
    INCLUDED_RUN_IDS
).fetchone()[0]

n_base = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND strategy LIKE 'baseline%'",
    INCLUDED_RUN_IDS
).fetchone()[0]

n_missing_baseline = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 s "
    f"WHERE s.run_id IN {in_clause(INCLUDED_RUN_IDS)} "
    f"AND s.strategy NOT LIKE 'baseline%' "
    f"AND NOT EXISTS ("
    f"  SELECT 1 FROM shadow_trades_v1 b "
    f"  WHERE b.baseline_trigger_id = s.trade_id "
    f"  AND b.run_id IN {in_clause(INCLUDED_RUN_IDS)}"
    f")",
    INCLUDED_RUN_IDS + INCLUDED_RUN_IDS
).fetchone()[0]

n_invalid = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND invalid_pair=1",
    INCLUDED_RUN_IDS
).fetchone()[0]

n_rollover = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND exit_reason='rollover_close'",
    INCLUDED_RUN_IDS
).fetchone()[0]

print(f"  strategy trades (non-baseline) : {n_strat}")
print(f"  baseline trades                : {n_base}")
print(f"  missing_baseline               : {n_missing_baseline}  "
      f"{'OK' if n_missing_baseline == 0 else 'ALERT — atomic pairing may have failed'}")
print(f"  invalid_pair total             : {n_invalid}  "
      f"{'OK' if n_invalid == 0 else 'ALERT — check harness logs'}")
print(f"  rollover_close excluded        : {n_rollover}  (not counted in any PnL summary)")

# ── P0.3: JOIN-BASED CLOSED PAIRS ─────────────────────────────────────────
print("\nP0.3 — JOIN-BASED CLOSED PAIR COUNTING")
print("-" * 70)

pairs_q = (
    f"SELECT "
    f"  s.trade_id AS s_id, s.token_symbol AS s_token, s.strategy AS s_strat, "
    f"  s.lane AS s_lane, s.entered_at AS s_entered, s.exited_at AS s_exited, "
    f"  s.exit_reason AS s_exit, s.run_id AS s_run, "
    f"  s.gross_pnl_pct AS s_gross, s.shadow_pnl_pct_fee100 AS s_fee100, "
    f"  s.entry_score AS s_score, "
    f"  s.mfe_gross_pct AS s_mfe, s.mae_gross_pct AS s_mae, "
    f"  s.mfe_net_dex_pct AS s_mfe_net_dex, s.mfe_net_fee100_pct AS s_mfe_net_fee100, "
    f"  s.max_price_seen AS s_max_price, s.min_price_seen AS s_min_price, "
    f"  s.entry_price_usd AS s_entry_price, "
    f"  s.mint_address AS s_mint, s.mint_prefix AS s_mint_prefix, "
    f"  s.entry_round_trip_pct AS s_rt, "
    f"  s.duration_sec AS s_dur, s.poll_count AS s_polls, "
    f"  s.exit_reason_effective AS s_exit_eff, s.price_mismatch AS s_price_mm, "
    f"  s.entry_jup_implied_price AS s_jup_price, "
    f"  b.trade_id AS b_id, b.token_symbol AS b_token, b.lane AS b_lane, "
    f"  b.exit_reason AS b_exit, b.exit_reason_effective AS b_exit_eff, "
    f"  b.forced_close AS b_forced, b.duration_sec AS b_dur, b.poll_count AS b_polls, "
    f"  b.run_id AS b_run, "
    f"  b.gross_pnl_pct AS b_gross, b.shadow_pnl_pct_fee100 AS b_fee100, "
    f"  b.mfe_gross_pct AS b_mfe, b.mae_gross_pct AS b_mae "
    f"FROM shadow_trades_v1 s "
    f"JOIN shadow_trades_v1 b "
    f"  ON b.baseline_trigger_id = s.trade_id "
    f"  AND b.run_id IN {in_clause(INCLUDED_RUN_IDS)} "
    f"WHERE s.run_id IN {in_clause(INCLUDED_RUN_IDS)} "
    f"  AND s.status = 'closed' "
    f"  AND b.status = 'closed' "
    f"  AND s.strategy NOT LIKE 'baseline%' "
    f"  AND s.exit_reason != 'rollover_close' "
    f"  AND b.exit_reason != 'rollover_close' "
    f"ORDER BY s.exited_at ASC"
)
pairs = conn.execute(pairs_q, INCLUDED_RUN_IDS + INCLUDED_RUN_IDS).fetchall()
n_pairs = len(pairs)

n_strat_open = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND status='open' AND strategy NOT LIKE 'baseline%'",
    INCLUDED_RUN_IDS
).fetchone()[0]
n_base_open = conn.execute(
    f"SELECT COUNT(*) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND status='open' AND strategy LIKE 'baseline%'",
    INCLUDED_RUN_IDS
).fetchone()[0]

print(f"  n_closed_pairs (join-based) : {n_pairs}")
print(f"  strategy still open         : {n_strat_open}")
print(f"  baseline still open         : {n_base_open}")

# ── Decide mode ────────────────────────────────────────────────────────────
mode = args.mode
if mode == "auto":
    if n_pairs >= 20:
        mode = "decision"
    elif n_pairs >= 3:
        mode = "mini"
    else:
        mode = "none"

print(f"\n  Mode selected: {mode.upper()} (n_pairs={n_pairs})")

if n_pairs == 0:
    print("\n  No closed pairs yet. Re-run when n_closed_pairs >= 3.")
    conn.close()
    sys.exit(0)

# ── Shared delta computation ───────────────────────────────────────────────
deltas = []
for p in pairs:
    sf = (p["s_fee100"] or 0.0) * 100
    bf = (p["b_fee100"] or 0.0) * 100
    deltas.append(sf - bf)

def bootstrap_ci(data, n_boot=5000, seed=42):
    random.seed(seed)
    n = len(data)
    means = sorted(
        sum(random.choice(data) for _ in range(n)) / n
        for _ in range(n_boot)
    )
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]

def summary_stats(d):
    n = len(d)
    mean = sum(d) / n
    sd = sorted(d)
    median = sd[n // 2] if n % 2 == 1 else (sd[n//2-1] + sd[n//2]) / 2
    pct_pos = 100.0 * sum(1 for x in d if x > 0) / n
    return mean, median, pct_pos

# ── MINI-REPORT (n>=3) ─────────────────────────────────────────────────────
if mode in ("mini", "decision"):
    print("\n" + "=" * 70)
    print(f"PAIR HEALTH MINI-REPORT ({SCOPE_LABEL}, join-based)")
    print("=" * 70)
    print(f"{'#':<3} {'s_run':<6} {'s_token(mint)':<18} {'b_token':<10} "
          f"{'entry':<20} {'s_exit':<14} {'b_exit':<18} "
          f"{'s_dur':>6} {'s_pol':>5} {'s_gross%':>9} {'b_gross%':>9} {'s_f100%':>8} {'b_f100%':>8} {'delta%':>8} {'flag':<6}")
    print("-" * 140)
    fast_exit_flags = []
    price_mm_flags = []
    for i, p in enumerate(pairs, 1):
        sg = (p["s_gross"] or 0.0) * 100
        bg = (p["b_gross"] or 0.0) * 100
        sf = (p["s_fee100"] or 0.0) * 100
        bf = (p["b_fee100"] or 0.0) * 100
        delta = sf - bf
        run_short = p["s_run"][:6] if p["s_run"] else "?"
        mp = p["s_mint_prefix"] or (p["s_mint"] or "")[:8] if p["s_mint_prefix"] or p["s_mint"] else "?"
        s_tok_display = f"{p['s_token']}({mp})"
        s_exit_eff = p["s_exit_eff"] or p["s_exit"] or "?"
        b_exit_eff = p["b_exit_eff"] or p["b_exit"] or "?"
        s_dur = p["s_dur"] if p["s_dur"] is not None else "-"
        s_pol = p["s_polls"] if p["s_polls"] is not None else "-"
        flag = ""
        if p["s_price_mm"]:
            flag += "MM "
            price_mm_flags.append(i)
        if isinstance(s_dur, (int, float)) and s_dur < 60:
            flag += "FAST"
            fast_exit_flags.append(i)
        print(f"{i:<3} {run_short:<6} {s_tok_display:<18} {p['b_token']:<10} "
              f"{(p['s_entered'] or '')[:19]:<20} "
              f"{s_exit_eff:<14} {b_exit_eff:<18} "
              f"{str(s_dur):>6} {str(s_pol):>5} "
              f"{sg:>9.3f} {bg:>9.3f} {sf:>8.3f} {bf:>8.3f} {delta:>8.3f} {flag:<6}")
    print("-" * 140)
    if fast_exit_flags:
        print(f"  FAST flag: pairs {fast_exit_flags} had strategy duration_sec < 60s — may indicate SL at first poll")
    if price_mm_flags:
        print(f"  MM flag  : pairs {price_mm_flags} had price_mismatch=1 at entry — excluded from MFE/MAE analysis")
    print(f"\n  INTEGRITY: missing_baseline={n_missing_baseline} "
          f"invalid_pair={n_invalid} rollover_excluded={n_rollover}")
    print(f"  PnL SCALE: stored as decimal, displayed as % (x100). Verified in P0.2.")

    n = len(deltas)
    mean_d, median_d, pct_pos = summary_stats(deltas)
    print(f"\n  DELTA SUMMARY (fee100, strategy - baseline, in %):")
    print(f"    n_pairs    : {n}")
    print(f"    mean delta : {mean_d:+.4f}%")
    print(f"    median     : {median_d:+.4f}%")
    print(f"    %delta>0   : {pct_pos:.1f}%")

    if n >= 3:
        ci_lo, ci_hi = bootstrap_ci(deltas)
        print(f"    95% CI     : [{ci_lo:+.4f}%, {ci_hi:+.4f}%]")
        if ci_lo < 0 < ci_hi:
            ci_note = "CI crosses zero — insufficient evidence of edge"
        elif ci_lo > 0:
            ci_note = "CI entirely positive — strategy outperforming baseline"
        else:
            ci_note = "CI entirely negative — strategy underperforming baseline"
        print(f"    CI note    : {ci_note}")

# ── SECTIONS 5+6: MFE/MAE + SCORE MONOTONICITY (n>=3, mini and decision) ────────
if mode in ("mini", "decision"):
    # ── SECTION 5: MFE/MAE ANALYSIS (v1.18) ─────────────────────────────────────
    print("\n5) MFE/MAE ANALYSIS (v1.18+ price-path trades only)")
    print("-" * 70)
    # v1.18: use max_price_seen/min_price_seen for proof; fall back to mfe_gross_pct for v1.17 rows
    # All rows that have any MFE data
    pairs_with_mfe_all = [p for p in pairs if p["s_mfe"] is not None]
    # Exclude pre-fix rows: max_price_seen < entry_price_usd means MFE init bug
    # Also exclude price_mismatch=1 rows (DEX price vs Jupiter diverged at entry)
    pairs_with_mfe = [
        p for p in pairs_with_mfe_all
        if not (
            p["s_max_price"] is not None
            and p["s_entry_price"] is not None
            and p["s_entry_price"] > 0
            and p["s_max_price"] < p["s_entry_price"]
        )
        and not p["s_price_mm"]
    ]
    n_mfe_total = len(pairs_with_mfe_all)
    n_mfe_excl_prefix = sum(
        1 for p in pairs_with_mfe_all
        if p["s_max_price"] is not None
        and p["s_entry_price"] is not None
        and p["s_entry_price"] > 0
        and p["s_max_price"] < p["s_entry_price"]
    )
    n_mfe_excl_mm = sum(1 for p in pairs_with_mfe_all if p["s_price_mm"])
    n_mfe_excl  = n_mfe_total - len(pairs_with_mfe)
    n_mfe       = len(pairs_with_mfe)
    if n_mfe_total == 0:
        print("  No MFE/MAE data yet (requires v1.17+ trades; columns are NULL for older rows).")
        print("  Once v1.18 is deployed and trades close, this section will populate.")
    else:
        excl_parts = []
        if n_mfe_excl_prefix:
            excl_parts.append(f"{n_mfe_excl_prefix} pre-fix (max_price < entry)")
        if n_mfe_excl_mm:
            excl_parts.append(f"{n_mfe_excl_mm} price_mismatch")
        excl_note = f"  (excluded: {', '.join(excl_parts)})" if excl_parts else ""
        print(f"  mfe_valid_n / total_n : {n_mfe} / {n_mfe_total}{excl_note}")
        if n_mfe == 0:
            print("  All MFE rows are excluded. No valid data to aggregate yet.")
    if n_mfe > 0:
        # Proof table: 5 sample trades showing price path
        proof_rows = [p for p in pairs_with_mfe if p["s_max_price"] is not None][:5]
        if proof_rows:
            print(f"  PRICE PATH PROOF (sample, max 5 rows):")
            print(f"    {'trade_id':<10} {'token(mint)':<18} {'entry_price':>12} {'max_price':>12} {'min_price':>12} {'MFE%':>8} {'MAE%':>8}")
            print(f"    {'-'*82}")
            for p in proof_rows:
                ep  = p["s_entry_price"] or 0.0
                mxp = p["s_max_price"] or ep
                mnp = p["s_min_price"] or ep
                mfe_chk = (mxp / ep - 1.0) * 100 if ep > 0 else 0.0
                mae_chk = (mnp / ep - 1.0) * 100 if ep > 0 else 0.0
                mp2 = p["s_mint_prefix"] or (p["s_mint"] or "")[:8] if p["s_mint_prefix"] or p["s_mint"] else "?"
                tok2 = f"{p['s_token']}({mp2})"
                print(f"    {p['s_id'][:8]:<10} {tok2:<18} {ep:>12.8f} {mxp:>12.8f} {mnp:>12.8f} {mfe_chk:>7.4f}% {mae_chk:>7.4f}%")
            print(f"    Formula: MFE = max_price/entry_price - 1  |  MAE = min_price/entry_price - 1")
        print(f"\n  AGGREGATE ({n_mfe} pairs):")
        fee_floors = []
        mfe_pcts = []
        mae_pcts = []
        mfe_net_dex_pcts = []
        mfe_net_fee100_pcts = []
        mfe_above_floor_025 = 0
        mfe_above_floor_100 = 0
        for p in pairs_with_mfe:
            rt_dec = p["s_rt"] if p["s_rt"] is not None else 0.005
            fee_floor = rt_dec * 100 + 1.00   # % units
            mfe = (p["s_mfe"] or 0.0) * 100
            mae = (p["s_mae"] or 0.0) * 100
            fee_floors.append(fee_floor)
            mfe_pcts.append(mfe)
            mae_pcts.append(mae)
            # MFE_net vs two floors (from stored columns if available, else compute)
            if p["s_mfe_net_dex"] is not None:
                mfe_net_dex_pcts.append(p["s_mfe_net_dex"] * 100)
            else:
                mfe_net_dex_pcts.append(mfe - (rt_dec * 100 + 0.60))
            if p["s_mfe_net_fee100"] is not None:
                mfe_net_fee100_pcts.append(p["s_mfe_net_fee100"] * 100)
            else:
                mfe_net_fee100_pcts.append(mfe - fee_floor)
            if mfe >= fee_floor + 0.25:
                mfe_above_floor_025 += 1
            if mfe >= fee_floor + 1.00:
                mfe_above_floor_100 += 1
        avg_fee_floor       = sum(fee_floors) / len(fee_floors)
        avg_mfe             = sum(mfe_pcts) / len(mfe_pcts)
        avg_mae             = sum(mae_pcts) / len(mae_pcts)
        avg_mfe_net_dex     = sum(mfe_net_dex_pcts) / len(mfe_net_dex_pcts)
        avg_mfe_net_fee100  = sum(mfe_net_fee100_pcts) / len(mfe_net_fee100_pcts)
        print(f"  avg fee_floor (RT+1%)          : {avg_fee_floor:+.4f}%")
        print(f"  avg MFE gross (strategy leg)   : {avg_mfe:+.4f}%")
        print(f"  avg MAE gross (strategy leg)   : {avg_mae:+.4f}%")
        print(f"  avg MFE_net vs DEX floor (RT+0.6%): {avg_mfe_net_dex:+.4f}%")
        print(f"  avg MFE_net vs fee100 floor (RT+1%): {avg_mfe_net_fee100:+.4f}%")
        print(f"  % MFE >= floor+0.25%           : {100*mfe_above_floor_025/n_mfe:.1f}%  ({mfe_above_floor_025}/{n_mfe})")
        print(f"  % MFE >= floor+1.00%           : {100*mfe_above_floor_100/n_mfe:.1f}%  ({mfe_above_floor_100}/{n_mfe})")
        print(f"\n  MFE/MAE by lane (strategy leg):")
        lane_mfe_map = {}
        for p in pairs_with_mfe:
            lane = p["s_lane"] or "unknown"
            mfe = (p["s_mfe"] or 0.0) * 100
            mae = (p["s_mae"] or 0.0) * 100
            if lane not in lane_mfe_map:
                lane_mfe_map[lane] = {"mfe": [], "mae": []}
            lane_mfe_map[lane]["mfe"].append(mfe)
            lane_mfe_map[lane]["mae"].append(mae)
        for lane, vals in sorted(lane_mfe_map.items(), key=lambda x: -len(x[1]["mfe"])):
            avg_m = sum(vals["mfe"]) / len(vals["mfe"])
            avg_a = sum(vals["mae"]) / len(vals["mae"])
            print(f"    {lane:<28} n={len(vals['mfe']):>3}  avg_MFE={avg_m:+.4f}%  avg_MAE={avg_a:+.4f}%")

    # ── SECTION 6: SCORE MONOTONICITY ───────────────────────────────────────────────
    print("\n6) SCORE MONOTONICITY (entry_score terciles)")
    print("-" * 70)
    pairs_with_score = [p for p in pairs if p["s_score"] is not None]
    n_score = len(pairs_with_score)
    if n_score < 6:
        print(f"  Insufficient score data: {n_score} pairs with entry_score (need >=6 for terciles).")
        if n_score == 0:
            print("  entry_score not yet populated — check that v1.17 is running.")
    else:
        scores_sorted = sorted(p["s_score"] for p in pairs_with_score)
        t1 = scores_sorted[len(scores_sorted) // 3]
        t2 = scores_sorted[2 * len(scores_sorted) // 3]
        buckets = {"low": [], "mid": [], "high": []}
        for p in pairs_with_score:
            sc = p["s_score"]
            sf = (p["s_fee100"] or 0.0) * 100
            bf = (p["b_fee100"] or 0.0) * 100
            delta = sf - bf
            if sc <= t1:
                buckets["low"].append(delta)
            elif sc <= t2:
                buckets["mid"].append(delta)
            else:
                buckets["high"].append(delta)
        print(f"  Score range: [{min(scores_sorted):.4f}, {max(scores_sorted):.4f}]")
        print(f"  Tercile thresholds: t1={t1:.4f}  t2={t2:.4f}")
        print(f"  {'bucket':<8} {'n':>4} {'avg_delta_fee100%':>18} {'%delta>0':>10}")
        avgs = []
        for bucket in ["low", "mid", "high"]:
            ds = buckets[bucket]
            if ds:
                avg = sum(ds) / len(ds)
                ppos = 100 * sum(1 for x in ds if x > 0) / len(ds)
                print(f"  {bucket:<8} {len(ds):>4} {avg:>17.4f}% {ppos:>9.1f}%")
                avgs.append(avg)
            else:
                print(f"  {bucket:<8} {0:>4} {'N/A':>17}")
                avgs.append(float("nan"))
        if len(avgs) == 3 and all(not (a != a) for a in avgs):
            if avgs[0] < avgs[1] < avgs[2]:
                mono = "MONOTONE INCREASING ✓ (higher score -> better delta)"
            elif avgs[0] > avgs[1] > avgs[2]:
                mono = "MONOTONE DECREASING ✗ (higher score -> worse delta)"
            else:
                mono = "NON-MONOTONE — no clear score-delta relationship"
        else:
            mono = "INDETERMINATE — insufficient data in one or more terciles"
        print(f"  Verdict: {mono}")

# ── SECTION 7: LP_REMOVAL AUDIT (n>=3, mini and decision) ────────────────────
if mode in ("mini", "decision"):
    print("\n7) LP_REMOVAL AUDIT")
    print("-" * 70)
    # Check if lp_removal_log table exists
    has_lp_log = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='lp_removal_log'"
    ).fetchone()[0]
    if not has_lp_log:
        print("  lp_removal_log table not yet created (requires v1.18+ harness).")
        # Fall back to summarizing from shadow_trades_v1
        lp_exits = [p for p in pairs if p["s_exit"] == "lp_removal"]
        print(f"  lp_removal exits in pairs: {len(lp_exits)} of {n_pairs}")
        if lp_exits:
            print(f"  (No trigger context available until v1.18 is deployed)")
    else:
        lp_rows = conn.execute(
            f"SELECT * FROM lp_removal_log WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} "
            f"ORDER BY logged_at ASC",
            INCLUDED_RUN_IDS
        ).fetchall()
        n_lp = len(lp_rows)
        print(f"  Total lp_removal events logged: {n_lp}")
        if n_lp == 0:
            print("  No lp_removal events yet in this run.")
        else:
            n_jup_ok   = sum(1 for r in lp_rows if r["jup_route_ok"] == 1)
            n_jup_fail = sum(1 for r in lp_rows if r["jup_route_ok"] == 0)
            n_jup_null = sum(1 for r in lp_rows if r["jup_route_ok"] is None)
            avg_k_drop = sum(r["k_change_pct"] or 0 for r in lp_rows) / n_lp * 100
            avg_liq_drop = [r["liq_pct_drop"] for r in lp_rows if r["liq_pct_drop"] is not None]
            avg_liq_drop_pct = (sum(avg_liq_drop) / len(avg_liq_drop) * 100) if avg_liq_drop else None
            print(f"  Jupiter route at trigger  : OK={n_jup_ok}  FAIL={n_jup_fail}  NULL={n_jup_null}")
            print(f"  avg k_change_pct at trigger: {avg_k_drop:.2f}%")
            if avg_liq_drop_pct is not None:
                print(f"  avg liq_pct_drop at trigger: {avg_liq_drop_pct:.2f}%")
            print(f"\n  Per-event detail (max 10):")
            print(f"    {'logged_at':<20} {'token(mint)':<18} {'k_drop%':>8} {'liq_bef$':>10} {'liq_aft$':>10} {'jup_rt':>8} {'jup_ok':>7} {'gross%':>8}")
            print(f"    {'-'*95}")
            for r in lp_rows[:10]:
                sym_r = r["token_symbol"] or "?"
                mp_r  = r["mint_prefix"] or (r["mint_address"] or "")[:8]
                tok_r = f"{sym_r}({mp_r})"
                k_d   = (r["k_change_pct"] or 0) * 100
                lb    = r["liq_before_usd"] or 0
                la    = r["liq_after_usd"] or 0
                jrt   = r["jup_rt_pct"]
                jok   = "OK" if r["jup_route_ok"] == 1 else ("FAIL" if r["jup_route_ok"] == 0 else "NULL")
                gp    = (r["gross_pnl_pct"] or 0) * 100
                jrt_s = f"{jrt*100:.3f}%" if jrt is not None else "N/A"
                print(f"    {(r['logged_at'] or '')[:19]:<20} {tok_r:<18} {k_d:>7.2f}% {lb:>10,.0f} {la:>10,.0f} {jrt_s:>8} {jok:>7} {gp:>7.4f}%")
            if n_lp > 10:
                print(f"    ... ({n_lp - 10} more rows not shown)")

# ── DECISION REPORT (n>=20) ────────────────────────────────────────────────────
if mode == "decision":
    print("\n" + "=" * 70)
    print(f"DECISION REPORT (n={n_pairs}, {SCOPE_LABEL})")
    print("=" * 70)

    # Lane breakdown
    print("\n2) LANE BREAKDOWN")
    print("-" * 70)
    lane_map = {}
    for p in pairs:
        lane = p["s_lane"] or "unknown"
        sf = (p["s_fee100"] or 0.0) * 100
        bf = (p["b_fee100"] or 0.0) * 100
        if lane not in lane_map:
            lane_map[lane] = []
        lane_map[lane].append(sf - bf)
    for lane, ds in sorted(lane_map.items(), key=lambda x: -len(x[1])):
        lmean = sum(ds) / len(ds)
        print(f"  lane={lane:<25} n={len(ds):>3}  avg_delta_fee100={lmean:+.4f}%")

    # Exit reason breakdown
    print("\n3) EXIT REASON BREAKDOWN")
    print("-" * 70)
    exit_map_s = {}
    exit_map_b = {}
    n_forced = 0
    for p in pairs:
        er_s = p["s_exit_eff"] or p["s_exit"] or "NULL"
        er_b = p["b_exit_eff"] or p["b_exit"] or "NULL"
        exit_map_s[er_s] = exit_map_s.get(er_s, 0) + 1
        exit_map_b[er_b] = exit_map_b.get(er_b, 0) + 1
        if p["b_forced"]:
            n_forced += 1
    print(f"  {'leg':<10} {'exit_reason_effective':<22} {'n':>4}")
    for er, cnt in sorted(exit_map_s.items(), key=lambda x: -x[1]):
        print(f"  {'strategy':<10} {er:<22} {cnt:>4}")
    for er, cnt in sorted(exit_map_b.items(), key=lambda x: -x[1]):
        print(f"  {'baseline':<10} {er:<22} {cnt:>4}")
    if n_forced:
        print(f"\n  NOTE: {n_forced} baseline leg(s) labeled forced_pair_close (strategy exited early, baseline closed at same price)")
    else:
        print(f"  NOTE: forced_pair_close=0 (all baseline legs ran to their own exit condition)")

    # Concentration check
    print("\n4) CONCENTRATION CHECK (top-5 token contribution)")
    print("-" * 70)
    token_deltas = {}
    for p in pairs:
        tok = p["s_token"]
        sf = (p["s_fee100"] or 0.0) * 100
        bf = (p["b_fee100"] or 0.0) * 100
        token_deltas[tok] = token_deltas.get(tok, 0) + (sf - bf)
    total_abs = sum(abs(v) for v in token_deltas.values())
    sorted_toks = sorted(token_deltas.items(), key=lambda x: abs(x[1]), reverse=True)
    top3_abs = sum(abs(v) for _, v in sorted_toks[:3])
    conc_pct = (top3_abs / total_abs * 100) if total_abs > 0 else 0.0
    print(f"  top-3 token concentration: {conc_pct:.1f}% of total |delta|")
    for tok, dv in sorted_toks[:5]:
        n_tok = sum(1 for p in pairs if p["s_token"] == tok)
        print(f"    {tok:<15} n={n_tok}  cumulative_delta={dv:+.4f}%")

    # Trimmed mean (drop top/bottom 10%)
    n = len(deltas)
    trim_k = max(1, int(n * 0.10))
    trimmed = sorted(deltas)[trim_k:-trim_k] if n > 2 * trim_k else deltas
    trimmed_mean = sum(trimmed) / len(trimmed) if trimmed else float("nan")

    # Final verdict
    mean_d, median_d, pct_pos = summary_stats(deltas)
    ci_lo, ci_hi = bootstrap_ci(deltas)

    print("\n" + "=" * 70)
    print("DECISION SUMMARY")
    print("=" * 70)
    print(f"  n_pairs         : {n}")
    print(f"  mean delta      : {mean_d:+.4f}%  (fee100, strategy - baseline)")
    print(f"  median delta    : {median_d:+.4f}%")
    print(f"  trimmed mean    : {trimmed_mean:+.4f}%  (10% trim each side, n={len(trimmed)})")
    print(f"  %delta > 0      : {pct_pos:.1f}%")
    print(f"  95% CI          : [{ci_lo:+.4f}%, {ci_hi:+.4f}%]")
    if ci_lo > 0:
        verdict = "POSITIVE EDGE — CI entirely above zero. Consider extending run."
    elif ci_hi < 0:
        verdict = "NEGATIVE EDGE — CI entirely below zero. Strategy underperforming."
    else:
        verdict = "INCONCLUSIVE — CI crosses zero. Need more pairs or parameter review."
    print(f"  VERDICT         : {verdict}")

print("\n" + "=" * 70)
conn.close()
