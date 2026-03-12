# Next Phase Gate v1

**Generated:** 2026-03-12  
**Status:** ACTIVE — enforced for all live observer decisions  
**Rule:** No live observer may be launched unless all six gates below are satisfied. No exceptions.

---

## Overview

This document defines the exact quantitative and qualitative criteria that must be satisfied before any new live observer is approved for deployment. It is the final checkpoint between retrospective analysis and live deployment.

The gate exists because the program has already demonstrated that positive gross means, positive relative deltas, and even positive mean net-proxy values are insufficient evidence of a deployable edge. The median and the bootstrap confidence interval are the primary metrics, not the mean.

---

## The Six Promotion Gates

All six gates must pass simultaneously. A result that passes five of six gates is a NO.

### Gate 1 — Positive Mean Net-Proxy

The mean net-proxy return in the best bucket must be strictly positive.

> **Threshold:** mean_net_proxy > 0.000  
> **Measured on:** the best-performing tercile or quintile bucket (pre-specified in the experiment proposal)  
> **Formula:** mean(r_forward_Xm − round_trip_pct) > 0  
> **Prior best (benchmark_suite_v1):** +0.304% (r_m5, +5m, Track B subset)  
> **Note:** A new experiment must beat this benchmark to be considered novel evidence.

### Gate 2 — Positive Median Net-Proxy

The median net-proxy return in the best bucket must be strictly positive.

> **Threshold:** median_net_proxy > 0.000  
> **Measured on:** the same bucket as Gate 1  
> **Prior best (benchmark_suite_v1):** −0.513% (all candidates failed this gate)  
> **Note:** This gate has never been passed. It is the binding constraint. A positive mean with a negative median indicates an outlier-driven result, not a systematic edge.

### Gate 3 — Bootstrap 95% CI Lower Bound > 0

The lower bound of the bootstrap 95% confidence interval for the mean net-proxy must be strictly positive.

> **Threshold:** ci_lo > 0.000  
> **Bootstrap parameters:** 10,000 resamples, seed=42, percentile method  
> **Measured on:** the same bucket as Gates 1 and 2  
> **Prior best (benchmark_suite_v1):** all CIs cross zero  
> **Note:** A CI that crosses zero is consistent with the null hypothesis (no edge). Gate 3 requires the entire CI to be positive.

### Gate 4 — Acceptable Concentration

The top-1 contributor share must be below 25%, and the top-3 contributor share must be below 50%.

> **Thresholds:** top1_share < 0.25 AND top3_share < 0.50  
> **Measured on:** the same bucket as Gates 1–3  
> **Prior best (benchmark_suite_v1):** top-1 share ~3–5% (concentration was not the binding constraint)  
> **Note:** A result driven by one or three tokens is not a generalizable edge. It is token-specific volatility.

### Gate 5 — Conceptually Distinct from Abandoned Families

The proposed feature or signal must be demonstrably different from the abandoned momentum/reversion family (NG-001 through NG-005 in no_go_registry_v1.md).

> **Requirement:** The proposal must include a written explanation of how the new feature differs from r_m5, vol_accel_m5_vs_h1, txn_accel_m5_vs_h1, and the other abandoned features. The explanation must reference specific mechanistic differences, not just different column names.  
> **Examples of insufficient distinction:** "we use a different rolling window," "we use buys_m5 instead of buy_sell_ratio_m5," "we use the same features at a different horizon"  
> **Examples of sufficient distinction:** "we use trade-level urgency derived from individual transaction timestamps, not rolling aggregates," "we use cross-venue spread as a market-state gate, not a directional signal"

### Gate 6 — Non-Random Coverage, Generalizable to Full Universe

The feature must have coverage that is not systematically biased by venue, pool type, or any other non-random factor.

> **Requirement:** Coverage must be ≥ 80% of the full eligible universe, and the missing rows must not be concentrated in a specific venue or pool type.  
> **Known failure mode:** Track B features in feature_tape_v1 have 70–79% coverage, but the missing rows are entirely Orca and Meteora pools — this is non-random and makes the results non-generalizable.  
> **Acceptable missingness:** Random missingness due to API timeouts or transient data gaps, provided the rate is < 20% and is not correlated with venue, pool type, or outcome.

---

## Gate Evaluation Checklist

Use this checklist when evaluating any retrospective sweep result before making a live observer decision.

| Gate | Criterion | Value from sweep | Pass / Fail |
|------|-----------|-----------------|-------------|
| 1 | mean_net_proxy > 0 | | |
| 2 | median_net_proxy > 0 | | |
| 3 | bootstrap CI lo > 0 | | |
| 4 | top1_share < 0.25 AND top3_share < 0.50 | | |
| 5 | Conceptually distinct from NG-001 to NG-005 | | |
| 6 | Coverage ≥ 80%, non-random missingness | | |
| **Overall** | **All six pass?** | | **YES / NO** |

---

## Decision Protocol

Once a retrospective sweep is complete, the following protocol applies:

**If all six gates pass:** The experiment is approved for live observer deployment. A new entry must be added to EXPERIMENT_INDEX.md and a change manifest must be written before any code is deployed.

**If any gate fails:** The experiment is classified as NO NEW LIVE OBSERVER. The result is recorded in benchmark_suite_v1.md and no_go_registry_v1.md. No live observer is deployed.

**If Gate 2 (median) passes but Gate 3 (CI) fails:** The result is classified as CONDITIONAL — collect more data (target n ≥ 300 per bucket) and re-evaluate. Do not deploy a live observer until Gate 3 also passes.

**If Gate 6 (coverage) fails:** The result is classified as SUBSET-ONLY. It may be used as supporting evidence for a new collection effort targeting the missing venues, but it does not justify a live observer on its own.

---

## Current Gate Status (as of 2026-03-12)

No experiment has passed all six gates. The program is in Feature Acquisition v2 mode.

| Gate | Best result to date | Source |
|------|--------------------|----|
| 1 — Mean net > 0 | +0.304% | r_m5, +5m, Track B subset |
| 2 — Median net > 0 | −0.513% (FAIL) | all candidates |
| 3 — CI lo > 0 | CI crosses zero (FAIL) | all candidates |
| 4 — Concentration | top-1 ~3–5% (PASS) | all candidates |
| 5 — Distinct from abandoned | FAIL (all Track B features are momentum-adjacent) | all candidates |
| 6 — Non-random coverage | FAIL (Track B is subset-only) | all candidates |

**Gates 2, 3, 5, and 6 have never been passed.** Gate 2 (positive median) is the binding constraint.
