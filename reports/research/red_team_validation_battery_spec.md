# Red-Team Validation Battery v1 — Specification

**Date:** 2026-03-13
**Status:** Pre-registered (cold-path only)
**Script:** `scripts/red_team_validation_battery.py`

---

## Purpose

The Red-Team Validation Battery is a reusable kill-or-pass gate that every candidate feature family must survive before a live observer is allowed. It is designed to be adversarial: the default outcome is FAIL. A candidate must actively prove robustness across 7 independent modules.

---

## Modules

| # | Module | Severity | What It Tests |
|---|--------|----------|---------------|
| 1 | Cost Sensitivity | Critical | Does the edge survive under progressively worse cost assumptions? |
| 2 | Concentration Sensitivity | High | Does the edge survive after removing top contributors? |
| 3 | Robust Summary Checks | High | Are mean, median, trimmed mean, and bootstrap CIs consistent? |
| 4 | Missingness / Subset Sensitivity | High | Is the edge driven by selective coverage (survivorship bias)? |
| 5 | Temporal Stability | Critical | Is the sign consistent across discovery, holdout, and half-splits? |
| 6 | Placebo / Null Test | High | Is the observed edge larger than a label-shuffled null? |
| 7 | Benchmark / No-Go Check | Critical | Does it beat v1 benchmarks and avoid no-go registry entries? |

---

## Module Details

### 1. Cost Sensitivity

Evaluates the candidate under 7 cost assumptions:

| Scenario | Description |
|----------|-------------|
| gross | No cost deduction |
| net_proxy | Base cost estimate |
| net_proxy - 25bps | +0.25% additional cost |
| net_proxy - 50bps | +0.50% additional cost |
| net_proxy - 100bps | +1.00% additional cost |
| net_proxy - 150bps | +1.50% additional cost |
| net_proxy - 200bps | +2.00% additional cost |

**PASS:** Positive median survives at net-proxy minus 50bps.
**FRAGILE:** Positive only at net-proxy; dies at -50bps.
**FAIL:** Negative median even at net-proxy.

### 2. Concentration Sensitivity

Recomputes edge after removing top contributors:

| Removal | Description |
|---------|-------------|
| Top 1 | Remove single best trade |
| Top 3 | Remove 3 best trades |
| Top 5 | Remove 5 best trades |

**PASS:** Edge survives removal of top 3 contributors.
**FRAGILE:** Edge dies when top 3 removed (concentrated).
**FAIL:** No edge even at baseline.

### 3. Robust Summary Checks

Computes 6 summary statistics:

- Mean
- Median
- Trimmed mean (10%)
- Winsorized mean (10%)
- Bootstrap CI for mean (95%, 2000 resamples)
- Bootstrap CI for median (95%, 2000 resamples)

**PASS:** 95% CI for median excludes zero (positive).
**FRAGILE:** CI includes zero.
**FAIL:** CI excludes zero (negative).

### 4. Missingness / Subset Sensitivity

Compares three populations:

- Full eligible sample (all eligible rows, including those without feature coverage)
- Covered subset only (rows where the feature is non-null)
- Any subset-only family (if applicable)

**PASS:** Covered and full samples are consistent.
**FRAGILE:** Coverage < 50%, or covered subset significantly better than full.
**FAIL:** Edge exists only in covered subset; full sample is negative.

### 5. Temporal Stability

Checks 3 temporal dimensions:

- Discovery vs holdout sign consistency
- First half vs second half of holdout
- Day-slice stability (if sufficient data)

**PASS:** All temporal checks consistent.
**FRAGILE:** Holdout halves inconsistent, or no holdout data.
**FAIL:** Discovery and holdout have opposite signs.

### 6. Placebo / Null Test

Runs 1000 label shuffles within time blocks:

- Shuffles return labels across trades within the same fire
- Computes null distribution of medians
- Reports p-value: fraction of null medians >= observed

**PASS:** p < 0.05 (observed edge exceeds null).
**FRAGILE:** 0.05 <= p < 0.10 (marginal).
**FAIL:** p >= 0.10 (cannot reject null).

### 7. Benchmark / No-Go Check

Two sub-checks:

**Benchmark gate:** Candidate must beat `benchmark_suite_v1` best gross median.
**No-go gate:** Candidate must not match any entry in `no_go_registry_v1` (11 entries) unless it can prove structural distinction.

**PASS:** Beats benchmark and no no-go matches.
**FRAGILE:** Matches no-go entries (must prove structural distinction).
**FAIL:** Does not beat v1 benchmark.

---

## Final Verdict Logic

| Condition | Verdict |
|-----------|---------|
| Any critical module (cost, temporal, benchmark) FAIL | **FAIL** |
| 2+ modules FAIL | **FAIL** |
| 1 FAIL or 3+ FRAGILE | **FRAGILE** |
| 1-2 FRAGILE | **FRAGILE** |
| All PASS | **PASS** |

---

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| Ranked summary CSV | `reports/sweeps/feature_family_sweep_v2_ranked_summary.csv` | Yes |
| Holdout CSV | `reports/sweeps/feature_family_sweep_v2_holdout.csv` | Optional |
| Labeled tape DB | `artifacts/feature_tape_v2_frozen_*.db` | Preferred |
| benchmark_suite_v1 | Hardcoded in script | Built-in |
| no_go_registry_v1 | Hardcoded in script (11 entries) | Built-in |

---

## Outputs

| File | Format | Content |
|------|--------|---------|
| `reports/red_team/red_team_{candidate}_{horizon}.md` | Markdown | Full battery report |
| `reports/red_team/red_team_{candidate}_{horizon}.json` | JSON | Machine-readable results |

---

## Usage

```bash
# Run battery for a specific candidate
python3 scripts/red_team_validation_battery.py \
    --sweep-csv reports/sweeps/feature_family_sweep_v2_ranked_summary.csv \
    --holdout-csv reports/sweeps/feature_family_sweep_v2_holdout.csv \
    --candidate "buy_sell_ratio_m5" \
    --horizon "+15m" \
    --output-dir reports/red_team/

# Dry run
python3 scripts/red_team_validation_battery.py --dry-run \
    --sweep-csv reports/sweeps/example.csv --candidate "test"
```
