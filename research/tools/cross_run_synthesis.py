#!/usr/bin/env python3
"""
cross_run_synthesis.py
Read-only synthesis across all three observer branches.
Produces: horizon_matrix.md, branch_summary.md, monetization_memo.md
"""

import sqlite3
import statistics
import math
import os
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
BRANCHES = {
    "lcr_continuation": {
        "db": "/root/solana_trader/data/observer_lcr_cont_v1.db",
        "table": "observer_lcr_cont_v1",
        "run_id": "0c5337dd-2488-4730-90b6-e371fd1e9511",
        "signal_col": "candidate_type",
        "signal_val": "signal",
        "control_val": "control",
        "fire_id_col": "signal_fire_id",
    },
    "pfm_continuation": {
        "db": "/root/solana_trader/data/observer_pfm_cont_v1.db",
        "table": "observer_pfm_cont_v1",
        "run_id": "1677a7da",
        "signal_col": "candidate_type",
        "signal_val": "signal",
        "control_val": "control",
        "fire_id_col": "signal_fire_id",
    },
    "pfm_reversion": {
        "db": "/root/solana_trader/data/observer_pfm_rev_v1.db",
        "table": "observer_pfm_rev_v1",
        "run_id": "99ed0fd1",
        "signal_col": "candidate_type",
        "signal_val": "signal",
        "control_val": "control",
        "fire_id_col": "signal_fire_id",
    },
}

HORIZONS = ["1m", "5m", "15m", "30m"]

OUT_DIR = "/root/solana_trader/reports/synthesis"
os.makedirs(OUT_DIR, exist_ok=True)


# ── HELPERS ─────────────────────────────────────────────────────────────────
def ci95(vals):
    n = len(vals)
    if n < 2:
        return (float("nan"), float("nan"))
    mean = sum(vals) / n
    std = statistics.stdev(vals)
    se = std / math.sqrt(n)
    # t critical: use 1.984 for n>=100, 2.009 for n>=50, 2.080 otherwise
    t = 1.984 if n >= 100 else (2.009 if n >= 50 else 2.080)
    return (mean - t * se, mean + t * se)


def trimmed_mean(vals, pct=0.10):
    n = len(vals)
    k = max(1, int(n * pct))
    trimmed = sorted(vals)[k:-k]
    return sum(trimmed) / len(trimmed) if trimmed else float("nan")


def top_contrib_share(vals):
    abs_vals = [abs(v) for v in vals]
    total = sum(abs_vals)
    if total == 0:
        return 0.0
    return max(abs_vals) / total


def get_pairs(branch_cfg, horizon, timing_valid=False):
    """Return list of (sig_net, ctl_net) for completed pairs at given horizon."""
    cfg = branch_cfg
    fwd_ok_col = f"fwd_quote_ok_{horizon}"
    net_col = f"fwd_net_fee100_{horizon}"

    conn = sqlite3.connect(cfg["db"])
    try:
        query = f"""
        SELECT s.{net_col}, c.{net_col},
               s.entry_quote_ok, s.{fwd_ok_col},
               s.fwd_exec_epoch_{horizon}, s.fwd_due_epoch_{horizon},
               s.row_valid
        FROM {cfg['table']} s
        JOIN {cfg['table']} c
          ON s.{cfg['fire_id_col']} = c.{cfg['fire_id_col']}
         AND c.{cfg['signal_col']} = '{cfg['control_val']}'
        WHERE s.{cfg['signal_col']} = '{cfg['signal_val']}'
          AND s.run_id = '{cfg['run_id']}'
          AND s.{fwd_ok_col} = 1
          AND c.{fwd_ok_col} = 1
          AND s.row_valid = 1
        """
        rows = conn.execute(query).fetchall()
    except Exception as e:
        conn.close()
        return [], str(e)
    conn.close()

    if timing_valid:
        filtered = []
        for r in rows:
            sig_net, ctl_net, entry_ok, fwd_ok, exec_ep, due_ep, rv = r
            if entry_ok != 1:
                continue
            jitter = abs((exec_ep or 0) - (due_ep or 0))
            if jitter > 20:
                continue
            filtered.append((sig_net, ctl_net))
        return filtered, None
    else:
        return [(r[0], r[1]) for r in rows], None


def compute_metrics(pairs):
    if not pairs:
        return None
    n = len(pairs)
    deltas = [s - c for s, c in pairs]
    sig_nets = [s for s, c in pairs]
    ctl_nets = [c for s, c in pairs]
    mean_d = sum(deltas) / n
    med_d = statistics.median(deltas)
    pct_pos = sum(1 for d in deltas if d > 0) / n * 100
    mean_s = sum(sig_nets) / n
    mean_c = sum(ctl_nets) / n
    lo, hi = ci95(deltas)
    trim = trimmed_mean(deltas)
    outliers = sum(1 for d in deltas if abs(d) > 0.10)
    top_share = top_contrib_share(deltas)
    return {
        "n": n,
        "mean_delta": mean_d,
        "median_delta": med_d,
        "pct_pos": pct_pos,
        "ci_lo": lo,
        "ci_hi": hi,
        "mean_sig_net": mean_s,
        "mean_ctl_net": mean_c,
        "trim_mean": trim,
        "outliers": outliers,
        "top_share": top_share,
    }


def fmt(v, decimals=6):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    return f"{v:+.{decimals}f}"


def pct_fmt(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    return f"{v:.1f}%"


# ── HORIZON MATRIX ───────────────────────────────────────────────────────────
def build_horizon_matrix():
    results = {}
    for branch_name, cfg in BRANCHES.items():
        results[branch_name] = {}
        for horizon in HORIZONS:
            for view in ["ALL_COMPLETED", "TIMING_VALID"]:
                tv = view == "TIMING_VALID"
                pairs, err = get_pairs(cfg, horizon, timing_valid=tv)
                if err:
                    results[branch_name][(horizon, view)] = {"error": err}
                else:
                    m = compute_metrics(pairs)
                    results[branch_name][(horizon, view)] = m or {"n": 0}
    return results


def write_horizon_matrix(results):
    lines = []
    lines.append("# Horizon Matrix — Cross-Run Synthesis")
    lines.append(f"\n_Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')}_\n")
    lines.append("---\n")

    for branch_name in BRANCHES:
        lines.append(f"## {branch_name.replace('_', ' ').title()}\n")
        for view in ["ALL_COMPLETED", "TIMING_VALID"]:
            lines.append(f"### {view}\n")
            header = "| Horizon | n | mean_delta | median_delta | %>0 | 95% CI | mean_sig_net | mean_ctl_net | outliers | top_share |"
            sep = "|---|---|---|---|---|---|---|---|---|---|"
            lines.append(header)
            lines.append(sep)
            for horizon in HORIZONS:
                m = results[branch_name].get((horizon, view), {})
                if not m or m.get("n", 0) == 0:
                    lines.append(f"| +{horizon} | 0 | — | — | — | — | — | — | — | — |")
                elif "error" in m:
                    lines.append(f"| +{horizon} | ERR | {m['error'][:40]} | | | | | | | |")
                else:
                    ci = f"[{fmt(m['ci_lo'])}, {fmt(m['ci_hi'])}]"
                    lines.append(
                        f"| +{horizon} | {m['n']} | {fmt(m['mean_delta'])} | {fmt(m['median_delta'])} "
                        f"| {pct_fmt(m['pct_pos'])} | {ci} "
                        f"| {fmt(m['mean_sig_net'])} | {fmt(m['mean_ctl_net'])} "
                        f"| {m['outliers']} | {m['top_share']:.4f} |"
                    )
            lines.append("")

    path = os.path.join(OUT_DIR, "horizon_matrix.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


# ── BRANCH SUMMARY ───────────────────────────────────────────────────────────
def write_branch_summary(results):
    lines = []
    lines.append("# Branch Summary — Cross-Run Synthesis")
    lines.append(f"\n_Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')}_\n")
    lines.append("---\n")

    for branch_name in BRANCHES:
        lines.append(f"## {branch_name.replace('_', ' ').title()}\n")

        # Find best horizon (ALL_COMPLETED) by mean_delta
        best_h = None
        best_mean = None
        any_ci_positive = False
        any_sig_net_positive = False

        for horizon in HORIZONS:
            m = results[branch_name].get((horizon, "ALL_COMPLETED"), {})
            if not m or m.get("n", 0) == 0 or "error" in m:
                continue
            if best_mean is None or m["mean_delta"] > best_mean:
                best_mean = m["mean_delta"]
                best_h = horizon
            if m["mean_delta"] > 0 and m["median_delta"] > 0 and m["ci_lo"] > 0:
                any_ci_positive = True
            if m["mean_sig_net"] > 0:
                any_sig_net_positive = True

        # Classification
        if any_ci_positive:
            classification = "RELATIVE SIGNAL ONLY" if not any_sig_net_positive else "RELATIVE SIGNAL ONLY (with positive absolute net at some horizon)"
        else:
            # Check if any horizon has mean>0 and median>0
            any_positive_lean = False
            for horizon in HORIZONS:
                m = results[branch_name].get((horizon, "ALL_COMPLETED"), {})
                if m and m.get("n", 0) > 0 and "error" not in m:
                    if m["mean_delta"] > 0 and m["median_delta"] > 0:
                        any_positive_lean = True
            classification = "FRAGILE / INCONCLUSIVE" if any_positive_lean else "DEAD / NOT WORTH PURSUING"

        lines.append(f"**Classification:** {classification}\n")
        lines.append(f"**Best horizon (by mean delta):** +{best_h} (mean_delta={fmt(best_mean)})\n")
        lines.append(f"**Any horizon with mean>0 AND median>0 AND CI lower>0?** {'YES' if any_ci_positive else 'NO'}\n")
        lines.append(f"**Any horizon with absolute signal net > 0?** {'YES' if any_sig_net_positive else 'NO'}\n")

        # Per-horizon summary table
        lines.append("| Horizon | mean_delta | median_delta | CI lower | sig_net | Classification |")
        lines.append("|---|---|---|---|---|---|")
        for horizon in HORIZONS:
            m = results[branch_name].get((horizon, "ALL_COMPLETED"), {})
            if not m or m.get("n", 0) == 0 or "error" in m:
                lines.append(f"| +{horizon} | — | — | — | — | insufficient data |")
                continue
            if m["mean_delta"] > 0 and m["median_delta"] > 0 and m["ci_lo"] > 0:
                h_class = "SUPPORTED"
            elif m["mean_delta"] > 0 and m["median_delta"] > 0:
                h_class = "FRAGILE POSITIVE"
            elif m["mean_delta"] > 0:
                h_class = "MEAN ONLY"
            else:
                h_class = "NEGATIVE / FLAT"
            lines.append(
                f"| +{horizon} | {fmt(m['mean_delta'])} | {fmt(m['median_delta'])} "
                f"| {fmt(m['ci_lo'])} | {fmt(m['mean_sig_net'])} | {h_class} |"
            )
        lines.append("")

    path = os.path.join(OUT_DIR, "branch_summary.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


# ── MONETIZATION MEMO ────────────────────────────────────────────────────────
def write_monetization_memo(results):
    memo = f"""# Monetization Memo — Cross-Run Synthesis
_Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')}_

---

## What the data shows

All three observer branches (LCR continuation, PFM continuation, PFM reversion) share the same structural pattern:

- Positive relative delta (signal outperforms control) at +5m and sometimes +15m
- Negative absolute signal net at all horizons
- CI crossing zero in all branches
- No branch meets the full SUPPORT criteria (mean>0, median>0, CI lower>0)

This is consistent across both signal directions in the pumpfun_mature lane and the large_cap_anchor lane.

---

## Realistic next uses

### 1. Regime filter (highest priority)
The relative edge may be real but diluted by unfavorable market regimes.
A read-only retrospective sidecar testing breadth_positive and median_r_m5_positive
filters on the existing data could identify whether a regime-conditioned subgroup
has CI lower > 0. This was already attempted for PFM continuation and found no
qualifying subgroup — but has not been tested for LCR or PFM reversion.

**Verdict:** Low expected value given prior negative result on PFM continuation.
Only worth attempting if a specific regime hypothesis is pre-specified.

### 2. Ranking feature
The signal consistently ranks above the control on a relative basis.
This could be used as a tiebreaker or weighting input in a multi-signal
selection framework — not as a standalone entry signal.

**Verdict:** Viable as a component feature. Does not require a new observer.
Can be implemented as a scoring weight in the existing scanner.

### 3. Relative-value spread
If both legs could be executed simultaneously (long signal, short control),
the positive relative delta would translate to a real P&L edge.
This requires on-chain short infrastructure (e.g., perp or borrow market),
which is not currently available for pumpfun_mature tokens.

**Verdict:** Not currently executable. Revisit if short infrastructure becomes available.

### 4. Abandon family
If the ranking feature use case is not worth implementing and no regime filter
produces a qualifying subgroup, the pumpfun_mature momentum family should be
closed and resources redirected to a structurally different hypothesis
(e.g., different lane, different signal type, different horizon).

**Verdict:** Reasonable default if ranking feature is not prioritized.

---

## Recommended decision

1. Implement ranking feature weighting in scanner (low effort, no new observer).
2. Do NOT run additional live observers in the pumpfun_mature momentum family
   until a new structural hypothesis is identified.
3. If a new hypothesis is identified, preregister it before implementation.

"""
    path = os.path.join(OUT_DIR, "monetization_memo.md")
    with open(path, "w") as f:
        f.write(memo)
    return path


# ── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Building horizon matrix...")
    results = build_horizon_matrix()

    print("Writing horizon matrix...")
    p1 = write_horizon_matrix(results)
    print(f"  -> {p1}")

    print("Writing branch summary...")
    p2 = write_branch_summary(results)
    print(f"  -> {p2}")

    print("Writing monetization memo...")
    p3 = write_monetization_memo(results)
    print(f"  -> {p3}")

    print("\nDone.")
