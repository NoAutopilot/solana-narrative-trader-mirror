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
    f"  b.trade_id AS b_id, b.token_symbol AS b_token, b.lane AS b_lane, "
    f"  b.exit_reason AS b_exit, b.run_id AS b_run, "
    f"  b.gross_pnl_pct AS b_gross, b.shadow_pnl_pct_fee100 AS b_fee100 "
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
    print(f"{'#':<3} {'s_run':<6} {'s_token':<10} {'b_token':<10} "
          f"{'entry':<20} {'s_exit':<9} {'b_exit':<9} "
          f"{'s_gross%':>9} {'b_gross%':>9} {'s_f100%':>8} {'b_f100%':>8} {'delta%':>8}")
    print("-" * 110)

    for i, p in enumerate(pairs, 1):
        sg = (p["s_gross"] or 0.0) * 100
        bg = (p["b_gross"] or 0.0) * 100
        sf = (p["s_fee100"] or 0.0) * 100
        bf = (p["b_fee100"] or 0.0) * 100
        delta = sf - bf
        run_short = p["s_run"][:6] if p["s_run"] else "?"
        print(f"{i:<3} {run_short:<6} {p['s_token']:<10} {p['b_token']:<10} "
              f"{(p['s_entered'] or '')[:19]:<20} "
              f"{p['s_exit']:<9} {p['b_exit']:<9} "
              f"{sg:>9.3f} {bg:>9.3f} {sf:>8.3f} {bf:>8.3f} {delta:>8.3f}")

    print("-" * 110)
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

# ── DECISION REPORT (n>=20) ────────────────────────────────────────────────
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
    for p in pairs:
        er_s = p["s_exit"] or "NULL"
        er_b = p["b_exit"] or "NULL"
        exit_map_s[er_s] = exit_map_s.get(er_s, 0) + 1
        exit_map_b[er_b] = exit_map_b.get(er_b, 0) + 1
    print(f"  {'leg':<10} {'exit_reason':<15} {'n':>4}")
    for er, cnt in sorted(exit_map_s.items(), key=lambda x: -x[1]):
        print(f"  {'strategy':<10} {er:<15} {cnt:>4}")
    for er, cnt in sorted(exit_map_b.items(), key=lambda x: -x[1]):
        print(f"  {'baseline':<10} {er:<15} {cnt:>4}")

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
