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
    f"  COALESCE(s.jup_price_unit_native_ok, 0) AS s_native_ok, "
    f"  b.trade_id AS b_id, b.token_symbol AS b_token, b.lane AS b_lane, "
    f"  b.exit_reason AS b_exit, b.exit_reason_effective AS b_exit_eff, "
    f"  b.forced_close AS b_forced, b.duration_sec AS b_dur, b.poll_count AS b_polls, "
    f"  b.run_id AS b_run, "
    f"  b.gross_pnl_pct AS b_gross, b.shadow_pnl_pct_fee100 AS b_fee100, "
    f"  b.mfe_gross_pct AS b_mfe, b.mae_gross_pct AS b_mae, "
    f"  rr.git_commit AS s_commit, rr.signature AS s_sig "
    f"FROM shadow_trades_v1 s "
    f"LEFT JOIN run_registry rr ON rr.run_id = s.run_id "
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

# last_exit timestamp for the included runs
_last_exit_row = conn.execute(
    f"SELECT MAX(exited_at) FROM shadow_trades_v1 "
    f"WHERE run_id IN {in_clause(INCLUDED_RUN_IDS)} AND status='closed'",
    INCLUDED_RUN_IDS
).fetchone()
_last_exit = (_last_exit_row[0] or "none")[:19] if _last_exit_row else "none"
print(f"  n_closed_pairs (join-based) : {n_pairs}")
print(f"  last_exit                   : {_last_exit} UTC")
print(f"  strategy still open         : {n_strat_open}")
print(f"  baseline still open         : {n_base_open}")

# ── Closed pairs by signature (split-sample check) ────────────────────────
print("\n  CLOSED PAIRS BY SIGNATURE (split-sample check):")
_sig_rows = conn.execute("""
    SELECT
        COALESCE(rr.signature, 'NULL') AS sig,
        COALESCE(rr.git_commit, '?')   AS git_commit,
        COUNT(*) / 2.0                 AS approx_pairs_closed,
        MAX(st.exited_at)              AS last_exit
    FROM shadow_trades_v1 st
    LEFT JOIN run_registry rr ON rr.run_id = st.run_id
    WHERE rr.version = 'v1.19'
      AND st.status  = 'closed'
      AND st.exit_reason != 'rollover_close'
    GROUP BY rr.signature, rr.git_commit
    ORDER BY last_exit DESC
""").fetchall()
if _sig_rows:
    print(f"  {'sig':<18} {'commit':<10} {'approx_pairs':>13} {'last_exit':<22}")
    for _sr in _sig_rows:
        print(f"  {str(_sr['sig'])[:18]:<18} {str(_sr['git_commit'])[:8]:<10} "
              f"{_sr['approx_pairs_closed']:>13.1f} {str(_sr['last_exit'] or '')[:19]:<22}")
else:
    print("  (no closed v1.19 trades found)")

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
    def _is_prefix_bug(p):
        return (
            p["s_max_price"] is not None
            and p["s_entry_price"] is not None
            and p["s_entry_price"] > 0
            and p["s_max_price"] < p["s_entry_price"]
        )
    # All-rows set: exclude only pre-fix bug rows (keep price_mismatch rows)
    pairs_with_mfe_all_rows = [p for p in pairs_with_mfe_all if not _is_prefix_bug(p)]
    # No-mismatch set: also exclude price_mismatch=1 rows
    pairs_with_mfe = [p for p in pairs_with_mfe_all_rows if not p["s_price_mm"]]
    n_mfe_total      = len(pairs_with_mfe_all)
    n_mfe_excl_prefix = sum(1 for p in pairs_with_mfe_all if _is_prefix_bug(p))
    n_mfe_excl_mm    = sum(1 for p in pairs_with_mfe_all_rows if p["s_price_mm"])
    n_mfe_all_rows   = len(pairs_with_mfe_all_rows)
    n_mfe            = len(pairs_with_mfe)
    if n_mfe_total == 0:
        print("  No MFE/MAE data yet (requires v1.17+ trades; columns are NULL for older rows).")
        print("  Once v1.18 is deployed and trades close, this section will populate.")
    else:
        excl_note = f"  ({n_mfe_excl_prefix} pre-fix excluded)" if n_mfe_excl_prefix else ""
        print(f"  all_rows n / total_n  : {n_mfe_all_rows} / {n_mfe_total}{excl_note}")
        print(f"  no_mismatch n         : {n_mfe} ({n_mfe_excl_mm} price_mismatch rows excluded)")
        if n_mfe_all_rows == 0:
            print("  All MFE rows are excluded (pre-fix bug). No valid data to aggregate yet.")
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
        # Helper to compute and print aggregate stats for a given set of pairs
        def _print_mfe_aggregate(label: str, pset: list):
            if not pset:
                print(f"  {label}: no data")
                return
            ff, mfe_p, mae_p, mfe_nd, mfe_nf = [], [], [], [], []
            above_025 = above_100 = 0
            for p in pset:
                rt_dec = p["s_rt"] if p["s_rt"] is not None else 0.005
                fee_floor = rt_dec * 100 + 1.00
                mfe = (p["s_mfe"] or 0.0) * 100
                mae = (p["s_mae"] or 0.0) * 100
                ff.append(fee_floor); mfe_p.append(mfe); mae_p.append(mae)
                mfe_nd.append(p["s_mfe_net_dex"] * 100 if p["s_mfe_net_dex"] is not None else mfe - (rt_dec * 100 + 0.60))
                mfe_nf.append(p["s_mfe_net_fee100"] * 100 if p["s_mfe_net_fee100"] is not None else mfe - fee_floor)
                if mfe >= fee_floor + 0.25: above_025 += 1
                if mfe >= fee_floor + 1.00: above_100 += 1
            n = len(pset)
            print(f"\n  AGGREGATE — {label} ({n} pairs):")
            print(f"  avg fee_floor (RT+1%)          : {sum(ff)/n:+.4f}%")
            print(f"  avg MFE gross (strategy leg)   : {sum(mfe_p)/n:+.4f}%")
            print(f"  avg MAE gross (strategy leg)   : {sum(mae_p)/n:+.4f}%")
            print(f"  avg MFE_net vs DEX floor (RT+0.6%): {sum(mfe_nd)/n:+.4f}%")
            print(f"  avg MFE_net vs fee100 floor (RT+1%): {sum(mfe_nf)/n:+.4f}%")
            print(f"  % MFE >= floor+0.25%           : {100*above_025/n:.1f}%  ({above_025}/{n})")
            print(f"  % MFE >= floor+1.00%           : {100*above_100/n:.1f}%  ({above_100}/{n})")
            print(f"  MFE/MAE by lane (strategy leg):")
            lane_map: dict = {}
            for p in pset:
                ln = p["s_lane"] or "unknown"
                lane_map.setdefault(ln, {"mfe": [], "mae": []})
                lane_map[ln]["mfe"].append((p["s_mfe"] or 0.0) * 100)
                lane_map[ln]["mae"].append((p["s_mae"] or 0.0) * 100)
            for ln, vals in sorted(lane_map.items(), key=lambda x: -len(x[1]["mfe"])):
                print(f"    {ln:<28} n={len(vals['mfe']):>3}  avg_MFE={sum(vals['mfe'])/len(vals['mfe']):+.4f}%  avg_MAE={sum(vals['mae'])/len(vals['mae']):+.4f}%")

        if n_mfe_all_rows > 0:
            _print_mfe_aggregate("ALL ROWS (incl. price_mismatch)", pairs_with_mfe_all_rows)
        if n_mfe > 0:
            _print_mfe_aggregate("NO MISMATCH (price_mismatch=0)", pairs_with_mfe)

    # ── MFE MONETIZABILITY BY COHORT ─────────────────────────────────────────
    # Answers: was profit ever available (signal/horizon problem) or just not captured (exit problem)?
    if n_mfe > 0:
        print(f"\n5b) MFE MONETIZABILITY BY COHORT")
        print("-" * 70)
        print(f"  Key: mfe_net_fee100 = MFE_gross - (RT_pct + 1.0%)  [net of full fee floor]")
        print(f"  >0   = profit was available at some point during the trade")
        print(f"  >0.25% = meaningful profit window existed")
        print()

        def _mfe_monetizability(label: str, pset: list):
            """Print monetizability stats for a cohort subset (must have s_mfe != None)."""
            valid = [p for p in pset if p["s_mfe"] is not None and not _is_prefix_bug(p) and not p["s_price_mm"]]
            n_v = len(valid)
            if n_v == 0:
                print(f"  {label}: no valid MFE data")
                return
            mfe_nf_vals = []
            mae_g_vals  = []
            for p in valid:
                rt_dec    = p["s_rt"] if p["s_rt"] is not None else 0.005
                fee_floor = rt_dec * 100 + 1.00
                mfe_gross = (p["s_mfe"] or 0.0) * 100
                mae_gross = (p["s_mae"] or 0.0) * 100
                mfe_nf    = (p["s_mfe_net_fee100"] * 100
                             if p["s_mfe_net_fee100"] is not None
                             else mfe_gross - fee_floor)
                mfe_nf_vals.append(mfe_nf)
                mae_g_vals.append(mae_gross)
            pct_gt0    = 100 * sum(1 for v in mfe_nf_vals if v > 0)    / n_v
            pct_gt025  = 100 * sum(1 for v in mfe_nf_vals if v > 0.25) / n_v
            avg_mfe_nf = sum(mfe_nf_vals) / n_v
            avg_mae_g  = sum(mae_g_vals)  / n_v
            print(f"  {label} (n={n_v}):")
            print(f"    % mfe_net_fee100 > 0      : {pct_gt0:.1f}%  ({sum(1 for v in mfe_nf_vals if v > 0)}/{n_v})")
            print(f"    % mfe_net_fee100 > +0.25% : {pct_gt025:.1f}%  ({sum(1 for v in mfe_nf_vals if v > 0.25)}/{n_v})")
            print(f"    avg mfe_net_fee100        : {avg_mfe_nf:+.4f}%")
            print(f"    avg mae_gross             : {avg_mae_g:+.4f}%")
            if pct_gt0 >= 60 and avg_mfe_nf > 0:
                diag = "EXIT PROBLEM — profit available but not captured (improve exit timing)"
            elif pct_gt0 < 40:
                diag = "SIGNAL/HORIZON PROBLEM — profit rarely available (improve entry or hold time)"
            else:
                diag = "MIXED — some profit available; both signal quality and exit timing matter"
            print(f"    Diagnosis: {diag}")

        # Build cohorts matching sensitivity summaries A/B/C
        _mfe_monetizability("A) FULL", pairs_with_mfe)
        nofast_mfe = [p for p in pairs_with_mfe
                      if not (isinstance(p["s_dur"], (int, float)) and p["s_dur"] < 60)]
        _mfe_monetizability("B) NO-FAST", nofast_mfe)
        # C) HIGH-SCORE + NO-FAST (top tercile)
        pws_e = [p for p in pairs_with_mfe if p["s_score"] is not None]
        if len(pws_e) >= 6:
            scores_e2 = sorted(p["s_score"] for p in pws_e)
            t2_e2 = scores_e2[2 * len(scores_e2) // 3]
            high_nofast_mfe = [p for p in nofast_mfe
                               if p["s_score"] is not None and p["s_score"] > t2_e2]
            _mfe_monetizability(f"C) HIGH-SCORE+NO-FAST (score>{t2_e2:.2f})", high_nofast_mfe)
        else:
            print("  C) HIGH-SCORE+NO-FAST: insufficient score data")

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
        buckets      = {"low": [], "mid": [], "high": []}
        bucket_strat  = {"low": [], "mid": [], "high": []}  # strategy_fee100
        bucket_base   = {"low": [], "mid": [], "high": []}  # baseline_fee100
        for p in pairs_with_score:
            sc = p["s_score"]
            sf = (p["s_fee100"] or 0.0) * 100
            bf = (p["b_fee100"] or 0.0) * 100
            delta = sf - bf
            bkt = "low" if sc <= t1 else ("mid" if sc <= t2 else "high")
            buckets[bkt].append(delta)
            bucket_strat[bkt].append(sf)
            bucket_base[bkt].append(bf)
        n_low  = len(buckets["low"])
        n_mid  = len(buckets["mid"])
        n_high = len(buckets["high"])
        print(f"  Score range: [{min(scores_sorted):.4f}, {max(scores_sorted):.4f}]")
        print(f"  Tercile thresholds: t1={t1:.4f}  t2={t2:.4f}")
        print(f"  Bucket counts: n_low={n_low}  n_mid={n_mid}  n_high={n_high}  (total={n_low+n_mid+n_high})")
        print(f"  {'bucket':<8} {'n':>4} {'avg_strat_f100%':>16} {'avg_base_f100%':>16} {'avg_delta_f100%':>16} {'%delta>0':>10}")
        avgs = []
        for bucket in ["low", "mid", "high"]:
            ds = buckets[bucket]
            if ds:
                avg   = sum(ds) / len(ds)
                s_avg = sum(bucket_strat[bucket]) / len(bucket_strat[bucket])
                b_avg = sum(bucket_base[bucket])  / len(bucket_base[bucket])
                ppos  = 100 * sum(1 for x in ds if x > 0) / len(ds)
                print(f"  {bucket:<8} {len(ds):>4} {s_avg:>+15.4f}% {b_avg:>+15.4f}% {avg:>+15.4f}% {ppos:>9.1f}%")
                avgs.append(avg)
            else:
                print(f"  {bucket:<8} {0:>4} {'N/A':>15} {'N/A':>15} {'N/A':>15}")
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
    # Absolute profitability
    strat_fee100_vals = [(p["s_fee100"] or 0.0) * 100 for p in pairs]
    base_fee100_vals  = [(p["b_fee100"] or 0.0) * 100 for p in pairs]
    mean_strat_abs = sum(strat_fee100_vals) / len(strat_fee100_vals)
    mean_base_abs  = sum(base_fee100_vals)  / len(base_fee100_vals)
    print(f"  n_pairs         : {n}")
    print(f"  mean strategy_fee100% : {mean_strat_abs:+.4f}%  (net of RT+1% floor)")
    print(f"  mean baseline_fee100% : {mean_base_abs:+.4f}%")
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

    # ── FAST classification ────────────────────────────────────────────────────
    fast_pairs  = [p for p in pairs if isinstance(p["s_dur"], (int, float)) and p["s_dur"] < 60]
    nofast_pairs = [p for p in pairs if not (isinstance(p["s_dur"], (int, float)) and p["s_dur"] < 60)]
    n_fast   = len(fast_pairs)
    n_nofast = len(nofast_pairs)

    # ── FAST token frequency ──────────────────────────────────────────────────
    from collections import Counter
    fast_tok_counts = Counter(p["s_token"] for p in fast_pairs)
    print(f"\n  FAST EXITS (strategy duration_sec < 60s): {n_fast} of {n} pairs")
    if n_fast > 0:
        freq_str = "  ".join(f"{tok}={cnt}" for tok, cnt in fast_tok_counts.most_common())
        print(f"  FAST token frequency: {freq_str}")

    # ── Helper: compute and print one sensitivity block ───────────────────────
    def _print_sensitivity(label: str, subset: list, indent: str = "  "):
        if len(subset) < 3:
            print(f"{indent}{label} (n={len(subset)}): insufficient pairs for CI.")
            return
        deltas = [(p["s_fee100"] or 0.0)*100 - (p["b_fee100"] or 0.0)*100 for p in subset]
        s_abs  = sum((p["s_fee100"] or 0.0)*100 for p in subset) / len(subset)
        b_abs  = sum((p["b_fee100"] or 0.0)*100 for p in subset) / len(subset)
        mn, med, pct = summary_stats(deltas)
        ci_lo, ci_hi = bootstrap_ci(deltas)
        trim_k = max(1, int(len(deltas) * 0.10))
        trimmed = sorted(deltas)[trim_k:-trim_k] if len(deltas) > 2*trim_k else deltas
        tm = sum(trimmed)/len(trimmed) if trimmed else float("nan")
        if ci_lo > 0:   verdict = "POSITIVE EDGE"
        elif ci_hi < 0: verdict = "NEGATIVE EDGE"
        else:           verdict = "INCONCLUSIVE"
        print(f"{indent}{label} (n={len(subset)})")
        print(f"{indent}  mean strategy_fee100% : {s_abs:+.4f}%")
        print(f"{indent}  mean baseline_fee100% : {b_abs:+.4f}%")
        print(f"{indent}  mean delta    : {mn:+.4f}%")
        print(f"{indent}  median delta  : {med:+.4f}%")
        print(f"{indent}  trimmed mean  : {tm:+.4f}%  (n={len(trimmed)})")
        print(f"{indent}  %delta > 0    : {pct:.1f}%")
        print(f"{indent}  95% CI        : [{ci_lo:+.4f}%, {ci_hi:+.4f}%]")
        print(f"{indent}  VERDICT       : {verdict}")

    # ── 4-way sensitivity summaries ───────────────────────────────────────────
    print(f"\n" + "-" * 70)
    print("SENSITIVITY SUMMARIES")
    print("-" * 70)

    # A) Full dataset
    _print_sensitivity("A) FULL DATASET", pairs)

    # B) NO-FAST
    _print_sensitivity("B) NO-FAST", nofast_pairs)

    # C) NO-FAST + SAME COMMIT (modal/most-recent commit in current sig)
    commit_counts = Counter(p["s_commit"][:8] for p in pairs if p["s_commit"])
    if commit_counts:
        modal_commit = commit_counts.most_common(1)[0][0]
        same_commit_nofast = [p for p in nofast_pairs
                              if p["s_commit"] and p["s_commit"][:8] == modal_commit]
        print(f"  (C uses modal commit={modal_commit}, n_all_pairs_in_commit="
              f"{sum(1 for p in pairs if p['s_commit'] and p['s_commit'][:8]==modal_commit)})")
        _print_sensitivity("C) NO-FAST + SAME COMMIT", same_commit_nofast)
    else:
        print("  C) NO-FAST + SAME COMMIT: no commit data available.")

    # D) NO-FAST + LAST 6 HOURS
    from datetime import datetime, timezone, timedelta
    cutoff_6h = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    last6h_nofast = [p for p in nofast_pairs
                     if p["s_entered"] and str(p["s_entered"]) >= cutoff_6h]
    _print_sensitivity("D) NO-FAST + LAST 6H", last6h_nofast)
    # E) HIGH-SCORE + NO-FAST (top tercile by entry_score, strategy duration >= 60s)
    pairs_with_score_e = [p for p in pairs if p["s_score"] is not None]
    if len(pairs_with_score_e) >= 6:
        scores_e = sorted(p["s_score"] for p in pairs_with_score_e)
        t2_e = scores_e[2 * len(scores_e) // 3]  # top tercile threshold
        high_nofast = [p for p in nofast_pairs
                       if p["s_score"] is not None and p["s_score"] > t2_e]
        print(f"  (E uses top-tercile threshold={t2_e:.4f}, "
              f"n_high_all={sum(1 for p in pairs_with_score_e if p['s_score'] > t2_e)}")
        _print_sensitivity("E) HIGH-SCORE + NO-FAST", high_nofast)
    else:
        print("  E) HIGH-SCORE + NO-FAST: insufficient pairs for score tercile split.")
    # ── FAST ATTRIBUTION (by token and by lane) ───────────────────────────────
    if n_fast > 0:
        print(f"\n" + "-" * 70)
        print("FAST ATTRIBUTION")
        print("-" * 70)
        from collections import Counter
        tok_total   = Counter(p["s_token"] for p in pairs)
        tok_fast    = Counter(p["s_token"] for p in fast_pairs)
        lane_total  = Counter(p["s_lane"]  for p in pairs)
        lane_fast   = Counter(p["s_lane"]  for p in fast_pairs)
        print("  By token:")
        print(f"    {'token':<12} {'n_fast':>7} {'n_total':>8} {'fast_rate':>10}")
        for tok in sorted(tok_total, key=lambda t: -tok_fast.get(t, 0)):
            nf = tok_fast.get(tok, 0)
            nt = tok_total[tok]
            print(f"    {tok:<12} {nf:>7} {nt:>8} {nf/nt*100:>9.1f}%")
        print("  By lane:")
        print(f"    {'lane':<20} {'n_fast':>7} {'n_total':>8} {'fast_rate':>10}")
        for lane in sorted(lane_total, key=lambda l: -lane_fast.get(l, 0)):
            nf = lane_fast.get(lane, 0)
            nt = lane_total[lane]
            print(f"    {lane:<20} {nf:>7} {nt:>8} {nf/nt*100:>9.1f}%")

    # ── FAST PRE-ENTRY FEATURE ATTRIBUTION (prospective gate analysis) ────────
    if n_fast > 0 and n_nofast > 0:
        print(f"\n" + "-" * 70)
        print("FAST PRE-ENTRY FEATURE ATTRIBUTION (FAST vs NO-FAST)")
        print("-" * 70)
        print("  Goal: find a prospective gate that predicts FAST risk at entry time.")
        print()
        # Fetch entry features for ALL closed strategy legs in scope
        all_run_ids = list(set(p["s_run"] for p in pairs))
        in_r2 = "(" + ",".join("?"*len(all_run_ids)) + ")"
        feat_rows = conn.execute(
            f"SELECT trade_id, token_symbol, mint_address, lane, entry_score, "
            f"duration_sec, entry_rv5m, entry_r_m5, entry_buy_count_ratio, "
            f"entry_vol_accel, entry_jup_rt_pct "
            f"FROM shadow_trades_v1 "
            f"WHERE run_id IN {in_r2} "
            f"AND strategy NOT LIKE 'baseline%' AND status='closed' "
            f"AND exit_reason != 'rollover_close'",
            all_run_ids
        ).fetchall()
        fast_feat  = [r for r in feat_rows if r["duration_sec"] is not None and r["duration_sec"] < 60]
        nofast_feat = [r for r in feat_rows if r["duration_sec"] is None or r["duration_sec"] >= 60]

        def _feat_stats(rows, col):
            vals = [r[col] for r in rows if r[col] is not None]
            if not vals: return float("nan"), float("nan"), len(vals)
            vals.sort()
            med = vals[len(vals)//2]
            return sum(vals)/len(vals), med, len(vals)

        features = [
            ("entry_rv5m",            "rv5m (5m realized vol)",     True,  100.0),  # scale to %
            ("entry_r_m5",            "r_m5 (5m return)",           False, 100.0),
            ("entry_buy_count_ratio", "buy_ratio (buys/total)",     False, 1.0),
            ("entry_vol_accel",       "vol_accel",                  False, 1.0),
            ("entry_jup_rt_pct",      "jup_rt_pct (round-trip)",   True,  100.0),
            ("entry_score",           "score",                      False, 1.0),
        ]
        print(f"  {'Feature':<28} {'FAST mean':>11} {'FAST med':>9} {'NOFAST mean':>12} {'NOFAST med':>11} {'n_F':>5} {'n_NF':>6}")
        print(f"  {'-'*82}")
        gate_candidates = []  # (feature, direction, threshold, separation_score)
        for col, label, higher_is_riskier, scale in features:
            fm, fmed, fn = _feat_stats(fast_feat, col)
            nm, nmed, nn = _feat_stats(nofast_feat, col)
            fm_s  = fm  * scale if fm  == fm  else float("nan")
            fmed_s= fmed* scale if fmed== fmed else float("nan")
            nm_s  = nm  * scale if nm  == nm  else float("nan")
            nmed_s= nmed* scale if nmed== nmed else float("nan")
            fm_str   = f"{fm_s:+.3f}"   if fm_s  == fm_s  else "N/A"
            fmed_str = f"{fmed_s:+.3f}" if fmed_s == fmed_s else "N/A"
            nm_str   = f"{nm_s:+.3f}"   if nm_s  == nm_s  else "N/A"
            nmed_str = f"{nmed_s:+.3f}" if nmed_s == nmed_s else "N/A"
            print(f"  {label:<28} {fm_str:>11} {fmed_str:>9} {nm_str:>12} {nmed_str:>11} {fn:>5} {nn:>6}")
            # Collect gate candidate if separation is meaningful
            if fm == fm and nm == nm and abs(fm - nm) > 0:
                sep = abs(fm - nm) / (abs(nm) + 1e-9)
                gate_candidates.append((col, label, higher_is_riskier, fm, nm, scale, sep))
        print()
        # Threshold scan: for each feature, find the threshold that best separates FAST from NO-FAST
        # using a simple accuracy metric (% correctly classified)
        print(f"  PROSPECTIVE GATE SCAN (best single-feature threshold):")
        print(f"  {'Feature':<28} {'direction':<10} {'threshold':>12} {'accuracy':>10} {'n_FAST_blocked':>15} {'n_NOFAST_blocked':>17}")
        print(f"  {'-'*95}")
        best_gates = []
        for col, label, higher_is_riskier, fm, nm, scale, sep in sorted(gate_candidates, key=lambda x: -x[6])[:6]:
            all_vals = [(r[col], r["duration_sec"]) for r in feat_rows
                        if r[col] is not None and r["duration_sec"] is not None]
            if not all_vals: continue
            col_vals = sorted(set(v for v, _ in all_vals))
            # Sample up to 20 candidate thresholds evenly
            step = max(1, len(col_vals) // 20)
            candidates = col_vals[::step]
            best_acc, best_thr, best_nfb, best_nnfb = 0, None, 0, 0
            for thr in candidates:
                if higher_is_riskier:
                    # gate: block if feature >= thr
                    n_fast_blocked  = sum(1 for v, d in all_vals if v >= thr and d < 60)
                    n_nofast_blocked= sum(1 for v, d in all_vals if v >= thr and d >= 60)
                    n_fast_pass     = sum(1 for v, d in all_vals if v <  thr and d < 60)
                    n_nofast_pass   = sum(1 for v, d in all_vals if v <  thr and d >= 60)
                else:
                    # gate: block if feature <= thr
                    n_fast_blocked  = sum(1 for v, d in all_vals if v <= thr and d < 60)
                    n_nofast_blocked= sum(1 for v, d in all_vals if v <= thr and d >= 60)
                    n_fast_pass     = sum(1 for v, d in all_vals if v >  thr and d < 60)
                    n_nofast_pass   = sum(1 for v, d in all_vals if v >  thr and d >= 60)
                total = len(all_vals)
                acc = (n_fast_blocked + n_nofast_pass) / total if total > 0 else 0
                if acc > best_acc:
                    best_acc, best_thr, best_nfb, best_nnfb = acc, thr, n_fast_blocked, n_nofast_blocked
            if best_thr is not None:
                direction = ">= thr" if higher_is_riskier else "<= thr"
                thr_disp = f"{best_thr*scale:.4f}"
                print(f"  {label:<28} {direction:<10} {thr_disp:>12} {best_acc*100:>9.1f}% {best_nfb:>15} {best_nnfb:>17}")
                best_gates.append((label, direction, best_thr, best_acc, best_nfb, best_nnfb))
        if best_gates:
            top = best_gates[0]
            print(f"\n  Best single gate: '{top[0]}' {top[1]} {top[2]:.4f}")
            print(f"  Would block {top[4]}/{n_fast} FAST trades ({100*top[4]/n_fast:.0f}%) at cost of {top[5]}/{n_nofast} NO-FAST trades ({100*top[5]/n_nofast:.0f}%)")
            print(f"  Use this to set FAST_RISK_GATE threshold at n=50 decision point.")

    # ── FAST PAIRS DETAIL TABLE ───────────────────────────────────────────────
    if n_fast > 0:
        print(f"\n" + "-" * 70)
        print(f"FAST PAIRS DETAIL (strategy duration_sec < 60s, n={n_fast})")
        print("-" * 70)
        hdr = (f"  {'entered_at':<20} {'s_tok(mint)':<18} {'b_tok':<12} "
               f"{'s_dur':>6} {'s_pol':>5} {'s_exit':<10} {'b_exit':<10} "
               f"{'s_f100%':>8} {'b_f100%':>8} {'delta%':>8} "
               f"{'lane':<16} {'score':>7} {'run':<8} {'commit':<10} {'sig':<18}")
        print(hdr)
        print("-" * len(hdr))
        for p in fast_pairs:
            s_tok = f"{p['s_token']}({(p['s_mint_prefix'] or (p['s_mint'] or '')[:8])[:8]})"
            sf    = (p["s_fee100"] or 0.0) * 100
            bf    = (p["b_fee100"] or 0.0) * 100
            delta = sf - bf
            s_exit = p["s_exit_eff"] or p["s_exit"] or "?"
            b_exit = p["b_exit_eff"] or p["b_exit"] or "?"
            commit_s = str(p["s_commit"] or "")[:8]
            sig_s    = str(p["s_sig"]   or "")[:16]
            run_s    = str(p["s_run"]   or "")[:8]
            print(f"  {str(p['s_entered'] or '')[:19]:<20} {s_tok:<18} {str(p['b_token'] or ''):<12} "
                  f"{(p['s_dur'] or 0):>6.1f} {(p['s_polls'] or 0):>5} {s_exit:<10} {b_exit:<10} "
                  f"{sf:>+8.4f}% {bf:>+8.4f}% {delta:>+8.4f}% "
                  f"{str(p['s_lane'] or ''):<16} {(p['s_score'] or 0):>7.3f} "
                  f"{run_s:<8} {commit_s:<10} {sig_s:<18}")

    # ── FAST DIAGNOSTICS TABLE ──────────────────────────────────────────────────
    if n_fast > 0:
        print(f"\n" + "=" * 70)
        print(f"FAST EXIT DIAGNOSTICS (strategy duration_sec < 60s, n={n_fast})")
        print("=" * 70)
        print("Goal: identify which entry features predict FAST risk.")
        print()
        # Fetch full entry feature data for FAST strategy legs
        fast_mints = [p["s_mint"] for p in fast_pairs if p["s_mint"]]
        fast_run_ids = list(set(p["s_run"] for p in fast_pairs))
        # Build IN clause
        in_m = "(" + ",".join("?"*len(fast_mints)) + ")"
        in_r = "(" + ",".join("?"*len(fast_run_ids)) + ")"
        fast_rows = conn.execute(
            f"SELECT trade_id, token_symbol, mint_address, mint_prefix, lane, entry_score, "
            f"duration_sec, poll_count, "
            f"entry_rv5m, entry_r_m5, entry_buy_count_ratio, entry_vol_accel, "
            f"entry_jup_rt_pct, entry_price_native, entry_jup_implied_price, price_mismatch, "
            f"jup_price_unit_native_ok, "
            f"exit_reason, gross_pnl_pct, shadow_pnl_pct_fee100, "
            f"baseline_trigger_id "
            f"FROM shadow_trades_v1 "
            f"WHERE mint_address IN {in_m} AND run_id IN {in_r} "
            f"AND strategy NOT LIKE 'baseline%' AND duration_sec < 60 AND status='closed'",
            fast_mints + fast_run_ids
        ).fetchall()
        n_fast_native_ok = sum(1 for fr in fast_rows
                               if fr["jup_price_unit_native_ok"] == 1)
        print(f"  FAST rows with jup_price_unit_native_ok=1: {n_fast_native_ok}/{len(fast_rows)}")
        print(f"  (mm_pct analysis below is only meaningful for native_ok=1 rows)")
        # Print header
        print(f"  {'#':<3} {'token(mint)':<18} {'lane':<16} {'score':>7} {'dur_s':>6} {'polls':>5} "
              f"{'rv5m':>7} {'r_m5':>7} {'buy_r':>7} {'vol_ac':>7} "
              f"{'jup_rt':>7} {'dex_nat':>12} {'jup_nat':>12} {'mm_pct':>8} {'mm':>3} {'nat':>4} "
              f"{'exit':<8} {'gross%':>8} {'f100%':>8} {'delta%':>8}")
        print("-" * 155)
        for i, fr in enumerate(fast_rows, 1):
            # Find matching baseline delta
            fr_run = fr["run_id"][:8] if "run_id" in fr.keys() else ""
            fp = next((p for p in fast_pairs
                       if p["s_mint"] == fr["mint_address"]
                       and (not fr_run or p["s_run"][:8] == fr_run)), None)
            delta_str = f"{((fp['s_fee100'] or 0)*100 - (fp['b_fee100'] or 0)*100):+.4f}%" if fp else "N/A"
            dex_nat = fr["entry_price_native"]
            jup_nat = fr["entry_jup_implied_price"]
            if dex_nat and jup_nat and dex_nat > 0:
                mm_pct = (jup_nat / dex_nat - 1) * 100
                mm_pct_str = f"{mm_pct:+.2f}%"
            else:
                mm_pct_str = "N/A"
            tok_disp = f"{fr['token_symbol']}({(fr['mint_prefix'] or fr['mint_address'] or '')[:8]})"
            nat_ok = fr["jup_price_unit_native_ok"] if "jup_price_unit_native_ok" in fr.keys() else None
            nat_str = str(nat_ok) if nat_ok is not None else "?"
            print(f"  {i:<3} {tok_disp:<18} {(fr['lane'] or '?'):<16} "
                  f"{(fr['entry_score'] or 0):>7.3f} {(fr['duration_sec'] or 0):>6.1f} {(fr['poll_count'] or 0):>5} "
                  f"{(fr['entry_rv5m'] or 0)*100:>6.3f}% {(fr['entry_r_m5'] or 0):>7.3f} "
                  f"{(fr['entry_buy_count_ratio'] or 0):>7.4f} {(fr['entry_vol_accel'] or 0):>7.4f} "
                  f"{(fr['entry_jup_rt_pct'] or 0)*100:>6.3f}% "
                  f"{(dex_nat or 0):.4e} {(jup_nat or 0):.4e} "
                  f"{mm_pct_str:>8} {(fr['price_mismatch'] or 0):>3} {nat_str:>4} "
                  f"{(fr['exit_reason'] or '?'):<8} {(fr['gross_pnl_pct'] or 0)*100:>+7.4f}% "
                  f"{(fr['shadow_pnl_pct_fee100'] or 0)*100:>+7.4f}% {delta_str:>8}")
        print()
        print("  NOTE: rv_1m and range_5m not stored in DB — use entry_rv5m as proxy.")
        print("  NOTE: entry_jup_implied_price = jup_exec_price_native (SOL/token) post v1.19 fix.")

# ── n=50 VERDICT GRID ────────────────────────────────────────────────────────
if n_pairs >= 20:  # show grid from n=20 onwards so it is always visible
    print("\n" + "=" * 70)
    print(f"DECISION GRID (n={n_pairs}{'  -- n>=50 DECISION POINT' if n_pairs >= 50 else '  ... waiting for n=50'})")
    print("=" * 70)
    print("  mean_strat = mean(strategy_fee100%)  [net of RT+1% floor; >0 = actually profitable]")
    print("  mean_delta = mean(strategy - baseline)  CI = 95% bootstrap")
    print()

    def _cohort_stats(cohort_pairs):
        """Return (mean_strat, mean_base, mean_delta, ci_lo, ci_hi, n) for a list of pairs."""
        n = len(cohort_pairs)
        if n == 0:
            nan = float("nan")
            return nan, nan, nan, nan, nan, 0
        deltas   = [(p["s_fee100"] or 0.0)*100 - (p["b_fee100"] or 0.0)*100 for p in cohort_pairs]
        s_means  = [(p["s_fee100"] or 0.0)*100 for p in cohort_pairs]
        b_means  = [(p["b_fee100"] or 0.0)*100 for p in cohort_pairs]
        mean_s   = sum(s_means) / n
        mean_b   = sum(b_means) / n
        mean_d   = sum(deltas)  / n
        ci_lo, ci_hi = bootstrap_ci(deltas) if n >= 3 else (float("nan"), float("nan"))
        return mean_s, mean_b, mean_d, ci_lo, ci_hi, n

    def yn(cond): return "YES" if cond else "NO "

    # A) Full sample
    cohort_a = pairs
    # B) No-FAST (strategy duration_sec >= 60s)
    cohort_b = [p for p in pairs if not (isinstance(p["s_dur"], (int, float)) and p["s_dur"] < 60)]
    # C) No-FAST + native_price_ok=1 only
    cohort_c = [p for p in cohort_b if p["s_native_ok"] == 1]
    # D) HIGH-SCORE + NO-FAST (top tercile by entry_score)
    pws_grid = [p for p in pairs if p["s_score"] is not None]
    if len(pws_grid) >= 6:
        scores_grid = sorted(p["s_score"] for p in pws_grid)
        t2_grid = scores_grid[2 * len(scores_grid) // 3]
        cohort_d = [p for p in cohort_b if p["s_score"] is not None and p["s_score"] > t2_grid]
        cohort_d_label = f"D) HIGH-SCORE+NO-FAST (>{t2_grid:.2f})"
    else:
        cohort_d = []
        cohort_d_label = "D) HIGH-SCORE+NO-FAST (no score data)"
        t2_grid = float("nan")

    ms_a, mb_a, md_a, ci_lo_a, ci_hi_a, n_a = _cohort_stats(cohort_a)
    ms_b, mb_b, md_b, ci_lo_b, ci_hi_b, n_b = _cohort_stats(cohort_b)
    ms_c, mb_c, md_c, ci_lo_c, ci_hi_c, n_c = _cohort_stats(cohort_c)
    ms_d, mb_d, md_d, ci_lo_d, ci_hi_d, n_d = _cohort_stats(cohort_d)

    hdr = (f"  {'Cohort':<42} {'n':>4}  {'mean_strat%':>12} {'mean_delta%':>12}  "
           f"{'95% CI':>24}  {'CI>0?':>5}  {'strat>0?':>8}")
    print(hdr)
    print("-" * 120)
    def _row(label, n, ms, mb, md, ci_lo, ci_hi):
        if ci_lo != ci_lo:  # nan
            ci_str, ci_pos = "[N/A]", "N/A"
        else:
            ci_str = f"[{ci_lo:+.2f}%, {ci_hi:+.2f}%]"
            ci_pos = yn(ci_lo > 0)
        strat_pos = yn(ms > 0) if ms == ms else "N/A"
        ms_str = f"{ms:>+10.4f}%" if ms == ms else "      N/A"
        md_str = f"{md:>+10.4f}%" if md == md else "      N/A"
        return (f"  {label:<42} {n:>4}  {ms_str:>12} {md_str:>12}  {ci_str:>24}  {ci_pos:>5}  {strat_pos:>8}")
    print(_row("A) Full sample",                  n_a, ms_a, mb_a, md_a, ci_lo_a, ci_hi_a))
    print(_row("B) No-FAST (dur>=60s)",           n_b, ms_b, mb_b, md_b, ci_lo_b, ci_hi_b))
    print(_row("C) No-FAST + native_price_ok=1",  n_c, ms_c, mb_c, md_c, ci_lo_c, ci_hi_c))
    print(_row(cohort_d_label,                    n_d, ms_d, mb_d, md_d, ci_lo_d, ci_hi_d))
    print("=" * 120)
    # Decision guidance
    if n_pairs >= 50:
        print()
        print("  n=50 DECISION RULES:")
        print(f"  [1] Enable MIN_SCORE_TO_TRADE if: cohort D CI>0 AND cohort D strat>0")
        d_ci_ok  = (ci_lo_d == ci_lo_d and ci_lo_d > 0)
        d_str_ok = (ms_d == ms_d and ms_d > 0)
        print(f"      -> CI>0: {yn(d_ci_ok)}   strat>0: {yn(d_str_ok)}")
        print(f"  [2] Enable FAST_RISK_GATE if: FAST pre-entry feature scan shows accuracy >= 70%")
        print(f"  [3] Deploy EXACTLY ONE flag change under a new signature for clean A/B test.")
        if n_d >= 5 and d_ci_ok and d_str_ok:
            print(f"  *** RECOMMENDATION: Enable MIN_SCORE_TO_TRADE = {t2_grid:.2f} (top-tercile threshold) ***")
        elif n_d >= 5 and d_ci_ok and not d_str_ok:
            print(f"  *** RECOMMENDATION: Delta positive but strat still negative -- consider FAST_RISK_GATE first ***")
        else:
            print(f"  *** RECOMMENDATION: Inconclusive -- extend run or review FAST gate ***")
    else:
        pairs_needed = 50 - n_pairs
        print(f"  NOTE: {pairs_needed} more pairs needed to reach n=50 decision point.")
    if n_c < 10:
        print(f"  NOTE: cohort C has only n={n_c} pairs -- CI will be wide until more native_ok=1 trades accumulate.")
print("\n" + "=" * 70)
conn.close()
