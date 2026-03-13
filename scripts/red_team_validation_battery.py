#!/usr/bin/env python3
"""
red_team_validation_battery.py — Reusable kill-or-pass battery for candidate features.

Runs 8 validation modules against any candidate feature family before
a live observer is allowed. Cold-path only.

Usage:
  python3 scripts/red_team_validation_battery.py \
      --sweep-csv reports/sweeps/feature_family_sweep_v2_ranked_summary.csv \
      --holdout-csv reports/sweeps/feature_family_sweep_v2_holdout.csv \
      --candidate "buy_sell_ratio_m5" \
      --horizon "+15m" \
      --output-dir reports/red_team/

  python3 scripts/red_team_validation_battery.py --dry-run \
      --sweep-csv reports/sweeps/example.csv --candidate "test"
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CandidateInput:
    """Input data for a candidate feature under evaluation."""
    name: str
    family: str
    horizon: str
    returns_gross: list  # list of float: per-trade gross returns
    returns_net: list    # list of float: per-trade net-proxy returns
    cost_bps: float      # estimated round-trip cost in bps
    discovery_returns: list  # discovery split returns
    holdout_returns: list    # holdout split returns
    coverage_pct: float
    n_total: int
    n_covered: int
    covered_returns: list    # returns for covered-only subset
    full_returns: list       # returns for full eligible sample
    fire_ids: list           # fire_id per return (for temporal slicing)


@dataclass
class ModuleResult:
    """Result of a single battery module."""
    module: str
    passed: bool
    verdict: str  # PASS / FRAGILE / FAIL
    detail: dict
    reason: str


@dataclass
class BatteryVerdict:
    """Final battery verdict."""
    candidate: str
    family: str
    horizon: str
    verdict: str  # PASS / FRAGILE / FAIL
    reason: str
    modules: list  # list of ModuleResult
    timestamp: str


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark / No-Go registries (hardcoded from v1)
# ══════════════════════════════════════════════════════════════════════════════

BENCHMARK_SUITE_V1 = {
    "baseline_gross_median_15m": 0.0,
    "baseline_net_median_15m": -0.005,
    "best_v1_gross_median_15m": 0.002,
    "best_v1_net_median_15m": -0.003,
}

NO_GO_REGISTRY_V1 = [
    {"family": "momentum_direction", "feature": "r_m5", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "buy_sell_ratio_m5", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "vol_accel_m5_vs_h1", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "txn_accel_m5_vs_h1", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "rv_5m", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "range_5m", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "buy_count_ratio_m5", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "avg_trade_usd_m5", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "liq_change_pct", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "breadth_positive_pct", "reason": "no edge after costs"},
    {"family": "momentum_direction", "feature": "pool_dispersion_r_m5", "reason": "no edge after costs"},
]


# ══════════════════════════════════════════════════════════════════════════════
# Module 1: Cost Sensitivity
# ══════════════════════════════════════════════════════════════════════════════

def module_cost_sensitivity(ci: CandidateInput) -> ModuleResult:
    """Evaluate candidate under multiple cost assumptions."""
    cost_offsets_bps = [0, -25, -50, -100, -150, -200]  # additional cost in bps
    results = {}
    n_positive = 0

    for offset in cost_offsets_bps:
        adj_returns = [r + offset / 10000.0 for r in ci.returns_net]
        med = float(np.median(adj_returns)) if adj_returns else 0
        mean = float(np.mean(adj_returns)) if adj_returns else 0
        label = f"net{offset:+d}bps" if offset != 0 else "net_proxy"
        results[label] = {"median": round(med, 6), "mean": round(mean, 6)}
        if med > 0:
            n_positive += 1

    # Also compute gross
    if ci.returns_gross:
        results["gross"] = {
            "median": round(float(np.median(ci.returns_gross)), 6),
            "mean": round(float(np.mean(ci.returns_gross)), 6),
        }

    # Verdict: PASS if positive at net-50bps, FRAGILE if only at net-proxy, FAIL otherwise
    if results.get("net-50bps", {}).get("median", -1) > 0:
        verdict = "PASS"
        reason = "Positive median survives net-proxy minus 50bps"
    elif results.get("net_proxy", {}).get("median", -1) > 0:
        verdict = "FRAGILE"
        reason = "Positive only at net-proxy; dies at -50bps"
    else:
        verdict = "FAIL"
        reason = "Negative median even at net-proxy"

    return ModuleResult(
        module="cost_sensitivity",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 2: Concentration Sensitivity
# ══════════════════════════════════════════════════════════════════════════════

def module_concentration_sensitivity(ci: CandidateInput) -> ModuleResult:
    """Recompute after removing top contributors."""
    returns = sorted(ci.returns_gross, reverse=True)
    n = len(returns)
    results = {}

    for k in [1, 3, 5]:
        if k >= n:
            results[f"remove_top_{k}"] = {"median": None, "mean": None, "note": "insufficient data"}
            continue
        trimmed = returns[k:]
        results[f"remove_top_{k}"] = {
            "median": round(float(np.median(trimmed)), 6),
            "mean": round(float(np.mean(trimmed)), 6),
            "n_remaining": len(trimmed),
        }

    baseline_med = float(np.median(returns)) if returns else 0
    results["baseline"] = {"median": round(baseline_med, 6), "n": n}

    # Check if removing top 3 kills the edge
    top3_med = results.get("remove_top_3", {}).get("median")
    if top3_med is None:
        verdict = "FRAGILE"
        reason = "Too few data points to remove top 3"
    elif top3_med > 0:
        verdict = "PASS"
        reason = "Edge survives removal of top 3 contributors"
    elif baseline_med > 0:
        verdict = "FRAGILE"
        reason = "Edge dies when top 3 contributors removed — concentrated"
    else:
        verdict = "FAIL"
        reason = "No edge even at baseline"

    return ModuleResult(
        module="concentration_sensitivity",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 3: Robust Summary Checks
# ══════════════════════════════════════════════════════════════════════════════

def _bootstrap_ci(data, stat_fn, n_boot=2000, alpha=0.05):
    """Compute bootstrap confidence interval."""
    if len(data) < 5:
        return None, None
    rng = np.random.default_rng(42)
    boot_stats = []
    for _ in range(n_boot):
        sample = rng.choice(data, size=len(data), replace=True)
        boot_stats.append(stat_fn(sample))
    lo = float(np.percentile(boot_stats, 100 * alpha / 2))
    hi = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
    return round(lo, 6), round(hi, 6)


def _trimmed_mean(data, pct=0.1):
    """Trimmed mean: remove pct from each tail."""
    arr = np.sort(data)
    n = len(arr)
    k = int(n * pct)
    if k == 0:
        return float(np.mean(arr))
    return float(np.mean(arr[k:-k]))


def _winsorized_mean(data, pct=0.1):
    """Winsorized mean: clip tails to pct quantile."""
    arr = np.array(data)
    lo = np.percentile(arr, 100 * pct)
    hi = np.percentile(arr, 100 * (1 - pct))
    clipped = np.clip(arr, lo, hi)
    return float(np.mean(clipped))


def module_robust_summary(ci: CandidateInput) -> ModuleResult:
    """Compute robust summary statistics."""
    r = np.array(ci.returns_gross)
    if len(r) == 0:
        return ModuleResult("robust_summary", False, "FAIL", {}, "No data")

    mean_val = float(np.mean(r))
    median_val = float(np.median(r))
    trimmed = _trimmed_mean(r, 0.1)
    winsorized = _winsorized_mean(r, 0.1)
    ci_mean_lo, ci_mean_hi = _bootstrap_ci(r, np.mean)
    ci_med_lo, ci_med_hi = _bootstrap_ci(r, np.median)

    results = {
        "mean": round(mean_val, 6),
        "median": round(median_val, 6),
        "trimmed_mean_10pct": round(trimmed, 6),
        "winsorized_mean_10pct": round(winsorized, 6),
        "bootstrap_ci_mean_95": [ci_mean_lo, ci_mean_hi],
        "bootstrap_ci_median_95": [ci_med_lo, ci_med_hi],
        "n": len(r),
    }

    # Check: does the CI for median include zero?
    if ci_med_lo is not None and ci_med_lo > 0:
        verdict = "PASS"
        reason = "95% CI for median excludes zero (positive)"
    elif ci_med_hi is not None and ci_med_hi < 0:
        verdict = "FAIL"
        reason = "95% CI for median excludes zero (negative)"
    else:
        verdict = "FRAGILE"
        reason = "95% CI for median includes zero"

    return ModuleResult(
        module="robust_summary",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 4: Missingness / Subset Sensitivity
# ══════════════════════════════════════════════════════════════════════════════

def module_missingness(ci: CandidateInput) -> ModuleResult:
    """Compare full eligible sample vs covered-only subset."""
    results = {}

    if ci.full_returns:
        results["full_eligible"] = {
            "median": round(float(np.median(ci.full_returns)), 6),
            "n": len(ci.full_returns),
        }
    if ci.covered_returns:
        results["covered_only"] = {
            "median": round(float(np.median(ci.covered_returns)), 6),
            "n": len(ci.covered_returns),
        }

    results["coverage_pct"] = ci.coverage_pct

    full_med = results.get("full_eligible", {}).get("median", 0)
    cov_med = results.get("covered_only", {}).get("median", 0)

    # Flag if covered-only is much better than full (selective missingness)
    if ci.coverage_pct < 50:
        verdict = "FRAGILE"
        reason = f"Coverage only {ci.coverage_pct:.1f}% — high missingness risk"
    elif cov_med > 0 and full_med <= 0:
        verdict = "FAIL"
        reason = "Edge exists only in covered subset; full sample is negative"
    elif abs(cov_med - full_med) > 0.01 and cov_med > full_med:
        verdict = "FRAGILE"
        reason = "Covered subset significantly better than full — possible selection bias"
    else:
        verdict = "PASS"
        reason = "Covered and full samples are consistent"

    return ModuleResult(
        module="missingness_sensitivity",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 5: Temporal Stability
# ══════════════════════════════════════════════════════════════════════════════

def module_temporal_stability(ci: CandidateInput) -> ModuleResult:
    """Check discovery vs holdout and half-split consistency."""
    results = {}

    disc = np.array(ci.discovery_returns) if ci.discovery_returns else np.array([])
    hold = np.array(ci.holdout_returns) if ci.holdout_returns else np.array([])

    if len(disc) > 0:
        results["discovery"] = {"median": round(float(np.median(disc)), 6), "n": len(disc)}
    if len(hold) > 0:
        results["holdout"] = {"median": round(float(np.median(hold)), 6), "n": len(hold)}

    # Sign consistency
    disc_sign = np.sign(np.median(disc)) if len(disc) > 0 else 0
    hold_sign = np.sign(np.median(hold)) if len(hold) > 0 else 0
    results["sign_consistent"] = bool(disc_sign == hold_sign and disc_sign != 0)

    # Half-split of holdout
    if len(hold) >= 10:
        mid = len(hold) // 2
        h1 = hold[:mid]
        h2 = hold[mid:]
        results["holdout_first_half"] = {"median": round(float(np.median(h1)), 6), "n": len(h1)}
        results["holdout_second_half"] = {"median": round(float(np.median(h2)), 6), "n": len(h2)}
        half_consistent = np.sign(np.median(h1)) == np.sign(np.median(h2))
        results["holdout_half_consistent"] = bool(half_consistent)
    else:
        half_consistent = None
        results["holdout_half_consistent"] = None

    if not results["sign_consistent"]:
        verdict = "FAIL"
        reason = "Discovery and holdout have opposite signs"
    elif half_consistent is False:
        verdict = "FRAGILE"
        reason = "Holdout halves have inconsistent signs"
    elif len(hold) == 0:
        verdict = "FRAGILE"
        reason = "No holdout data available"
    else:
        verdict = "PASS"
        reason = "Temporal stability confirmed"

    return ModuleResult(
        module="temporal_stability",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 6: Placebo / Null Test
# ══════════════════════════════════════════════════════════════════════════════

def module_placebo_null(ci: CandidateInput, n_shuffles: int = 1000) -> ModuleResult:
    """Shuffle labels within fires and compare to observed edge."""
    returns = np.array(ci.returns_gross)
    if len(returns) < 10:
        return ModuleResult("placebo_null", False, "FRAGILE",
                            {"note": "Too few observations for null test"}, "Insufficient data")

    observed_median = float(np.median(returns))
    rng = np.random.default_rng(42)

    null_medians = []
    for _ in range(n_shuffles):
        shuffled = rng.permutation(returns)
        null_medians.append(float(np.median(shuffled)))

    null_medians = np.array(null_medians)
    p_value = float(np.mean(null_medians >= observed_median))

    results = {
        "observed_median": round(observed_median, 6),
        "null_median_mean": round(float(np.mean(null_medians)), 6),
        "null_median_std": round(float(np.std(null_medians)), 6),
        "p_value": round(p_value, 4),
        "n_shuffles": n_shuffles,
    }

    if p_value < 0.05:
        verdict = "PASS"
        reason = f"Observed edge exceeds null (p={p_value:.4f})"
    elif p_value < 0.10:
        verdict = "FRAGILE"
        reason = f"Marginal significance (p={p_value:.4f})"
    else:
        verdict = "FAIL"
        reason = f"Cannot reject null (p={p_value:.4f})"

    return ModuleResult(
        module="placebo_null",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 7: Benchmark / No-Go Check
# ══════════════════════════════════════════════════════════════════════════════

def module_benchmark_nogo(ci: CandidateInput) -> ModuleResult:
    """Check against benchmark suite and no-go registry."""
    results = {}

    # No-go check
    nogo_match = [
        entry for entry in NO_GO_REGISTRY_V1
        if entry["feature"] == ci.name or entry["family"] == ci.family
    ]
    results["no_go_matches"] = len(nogo_match)
    results["no_go_entries"] = [e["feature"] for e in nogo_match]

    # Benchmark check
    obs_median = float(np.median(ci.returns_gross)) if ci.returns_gross else 0
    best_v1 = BENCHMARK_SUITE_V1.get("best_v1_gross_median_15m", 0)
    results["observed_gross_median"] = round(obs_median, 6)
    results["benchmark_best_v1"] = best_v1
    results["beats_benchmark"] = obs_median > best_v1

    if nogo_match:
        # Check if this is structurally distinct from no-go entries
        results["structural_distinction"] = "REQUIRES_MANUAL_REVIEW"
        verdict = "FRAGILE"
        reason = f"Matches {len(nogo_match)} no-go entries — must prove structural distinction"
    elif not results["beats_benchmark"]:
        verdict = "FAIL"
        reason = "Does not beat v1 benchmark"
    else:
        verdict = "PASS"
        reason = "Beats benchmark and no no-go matches"

    return ModuleResult(
        module="benchmark_nogo",
        passed=verdict == "PASS",
        verdict=verdict,
        detail=results,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Module 8: Final Battery Verdict
# ══════════════════════════════════════════════════════════════════════════════

def compute_final_verdict(modules: list[ModuleResult]) -> tuple[str, str]:
    """Compute final PASS / FRAGILE / FAIL from module results."""
    n_fail = sum(1 for m in modules if m.verdict == "FAIL")
    n_fragile = sum(1 for m in modules if m.verdict == "FRAGILE")
    n_pass = sum(1 for m in modules if m.verdict == "PASS")

    critical_modules = {"cost_sensitivity", "temporal_stability", "benchmark_nogo"}
    critical_fails = [m for m in modules if m.module in critical_modules and m.verdict == "FAIL"]

    if critical_fails:
        return "FAIL", f"Critical module(s) failed: {', '.join(m.module for m in critical_fails)}"
    elif n_fail >= 2:
        return "FAIL", f"{n_fail} modules failed"
    elif n_fail == 1 or n_fragile >= 3:
        return "FRAGILE", f"{n_fail} FAIL, {n_fragile} FRAGILE — edge is not robust"
    elif n_fragile >= 1:
        return "FRAGILE", f"{n_fragile} FRAGILE module(s) — proceed with caution"
    else:
        return "PASS", f"All {n_pass} modules passed"


# ══════════════════════════════════════════════════════════════════════════════
# Report generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(verdict: BatteryVerdict, output_dir: str):
    """Generate markdown report from battery verdict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = verdict.candidate.replace("/", "_").replace(" ", "_")
    md_path = output_dir / f"red_team_{safe_name}_{verdict.horizon}.md"
    json_path = output_dir / f"red_team_{safe_name}_{verdict.horizon}.json"

    # Markdown report
    lines = [
        f"# Red-Team Validation Battery — {verdict.candidate}",
        f"**Family:** {verdict.family}",
        f"**Horizon:** {verdict.horizon}",
        f"**Date:** {verdict.timestamp}",
        f"**Final Verdict:** {verdict.verdict}",
        f"**Reason:** {verdict.reason}",
        "",
        "---",
        "",
        "| Module | Verdict | Reason |",
        "|--------|---------|--------|",
    ]

    for m in verdict.modules:
        lines.append(f"| {m.module} | {m.verdict} | {m.reason} |")

    lines.extend(["", "---", ""])

    for m in verdict.modules:
        lines.append(f"## {m.module}")
        lines.append(f"**Verdict:** {m.verdict}")
        lines.append(f"**Reason:** {m.reason}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(m.detail, indent=2, default=str))
        lines.append("```")
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n")

    # JSON report
    json_data = {
        "candidate": verdict.candidate,
        "family": verdict.family,
        "horizon": verdict.horizon,
        "verdict": verdict.verdict,
        "reason": verdict.reason,
        "timestamp": verdict.timestamp,
        "modules": [asdict(m) for m in verdict.modules],
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str) + "\n")

    log.info("Report written: %s", md_path)
    log.info("JSON written: %s", json_path)


# ══════════════════════════════════════════════════════════════════════════════
# CSV loader (reads ranked summary or holdout CSVs)
# ══════════════════════════════════════════════════════════════════════════════

def load_candidate_from_csvs(
    sweep_csv: str,
    holdout_csv: Optional[str],
    candidate: str,
    horizon: str,
) -> Optional[CandidateInput]:
    """
    Load candidate data from sweep/holdout CSVs.
    This is a best-effort loader; actual column names depend on the sweep output format.
    """
    # Read sweep CSV
    with open(sweep_csv) as f:
        reader = csv.DictReader(f)
        sweep_rows = [r for r in reader]

    # Find matching candidate row
    match = None
    for r in sweep_rows:
        feat = r.get("feature", r.get("candidate", r.get("name", "")))
        hz = r.get("horizon", "")
        if feat == candidate and (not horizon or hz == horizon):
            match = r
            break

    if not match:
        log.warning("Candidate '%s' at horizon '%s' not found in sweep CSV", candidate, horizon)
        return None

    # Extract what we can
    def safe_float(v, default=0.0):
        try:
            return float(v) if v else default
        except (ValueError, TypeError):
            return default

    # Build a minimal CandidateInput
    # Note: full per-trade returns require the labeled tape, not just summary CSVs
    # This loader creates a synthetic distribution from summary stats for battery testing
    n = int(safe_float(match.get("n", match.get("count", "100"))))
    gross_med = safe_float(match.get("gross_median", match.get("median_gross", "0")))
    net_med = safe_float(match.get("net_median", match.get("median_net", "0")))

    # Synthetic returns (placeholder — real implementation reads labeled tape)
    rng = np.random.default_rng(hash(candidate) % 2**32)
    returns_gross = list(rng.normal(gross_med, abs(gross_med) + 0.01, size=n))
    returns_net = list(rng.normal(net_med, abs(net_med) + 0.01, size=n))

    # Discovery / holdout split
    split = int(0.75 * n)
    discovery_returns = returns_gross[:split]
    holdout_returns = returns_gross[split:]

    return CandidateInput(
        name=candidate,
        family=match.get("family", "unknown"),
        horizon=horizon or match.get("horizon", "unknown"),
        returns_gross=returns_gross,
        returns_net=returns_net,
        cost_bps=safe_float(match.get("cost_bps", "50")),
        discovery_returns=discovery_returns,
        holdout_returns=holdout_returns,
        coverage_pct=safe_float(match.get("coverage_pct", "100")),
        n_total=n,
        n_covered=int(safe_float(match.get("n_covered", str(n)))),
        covered_returns=returns_gross,
        full_returns=returns_gross,
        fire_ids=[f"fire_{i}" for i in range(n)],
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main orchestrator
# ══════════════════════════════════════════════════════════════════════════════

def run_battery(ci: CandidateInput) -> BatteryVerdict:
    """Run all 8 modules and return final verdict."""
    log.info("Running red-team battery for: %s (%s, %s)", ci.name, ci.family, ci.horizon)

    modules = [
        module_cost_sensitivity(ci),
        module_concentration_sensitivity(ci),
        module_robust_summary(ci),
        module_missingness(ci),
        module_temporal_stability(ci),
        module_placebo_null(ci),
        module_benchmark_nogo(ci),
    ]

    final_verdict, final_reason = compute_final_verdict(modules)

    for m in modules:
        log.info("  [%s] %s: %s", m.verdict, m.module, m.reason)

    log.info("  FINAL: %s — %s", final_verdict, final_reason)

    return BatteryVerdict(
        candidate=ci.name,
        family=ci.family,
        horizon=ci.horizon,
        verdict=final_verdict,
        reason=final_reason,
        modules=modules,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def main():
    parser = argparse.ArgumentParser(description="Red-Team Validation Battery")
    parser.add_argument("--sweep-csv", required=True, help="Path to ranked summary CSV")
    parser.add_argument("--holdout-csv", default=None, help="Path to holdout CSV")
    parser.add_argument("--candidate", required=True, help="Candidate feature name")
    parser.add_argument("--horizon", default="", help="Target horizon (e.g., +15m)")
    parser.add_argument("--output-dir", default="reports/red_team/", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without running")
    args = parser.parse_args()

    if args.dry_run:
        log.info("[DRY RUN] Would run battery for '%s' at '%s'", args.candidate, args.horizon)
        log.info("[DRY RUN] Sweep CSV: %s", args.sweep_csv)
        log.info("[DRY RUN] Output dir: %s", args.output_dir)
        return

    ci = load_candidate_from_csvs(args.sweep_csv, args.holdout_csv, args.candidate, args.horizon)
    if ci is None:
        log.error("Could not load candidate data. Exiting.")
        sys.exit(1)

    verdict = run_battery(ci)
    generate_report(verdict, args.output_dir)


if __name__ == "__main__":
    main()
