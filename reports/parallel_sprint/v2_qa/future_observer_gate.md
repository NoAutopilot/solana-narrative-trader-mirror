# Future Observer Gate — Pre-Registered Promotion and Kill Thresholds

**Date:** 2026-03-12
**Author:** Manus AI
**Status:** PRE-REGISTERED — written before any v2 holdout data is examined

---

## Purpose

This document defines the exact numeric thresholds that a future live observer must pass to be promoted from retrospective sweep to live deployment, and the exact conditions that trigger immediate kill of a live observer. These thresholds are based on lessons from the failed PFM observer (run `1677a7da`) and the feature_tape_v1 closure.

---

## Lessons from the Failed PFM Observer

The PFM continuation observer (run `1677a7da`, n=204 pairs) failed because:

1. **Mean was positive but median was negative.** Mean delta = +0.79%, median delta = -0.06%. The positive mean was driven by tail events (outlier tokens with extreme moves), not consistent per-trade alpha.

2. **CI crossed zero.** Bootstrap 95% CI for mean = [-0.71%, +2.35%]. The CI for median = [-1.31%, +0.98%]. Neither bound was strictly positive.

3. **Sign test was non-significant.** p = 0.94, indicating no evidence that the signal outperforms the control more than 50% of the time.

4. **Win rate was coin-flip.** 49.5% of pairs had positive delta — indistinguishable from random.

These failures define the promotion bar: a future observer must clear all four failure modes simultaneously.

---

## Promotion Gates (ALL must pass)

A feature is promoted from discovery sweep to holdout evaluation if it passes all of the following on the **discovery set**:

| Gate | Threshold | Rationale |
|------|-----------|-----------|
| G1: Mean net-proxy (winsorized p1/p99) | > 0 | Basic positive expectation |
| G2: Median net-proxy (winsorized p1/p99) | > 0 | Ensures effect is not outlier-driven |
| G3: Bootstrap 95% CI lower bound (mean) | > 0 | Statistical significance at 5% level |
| G4: Bootstrap 95% CI lower bound (median) | > -0.001 | Median must be at least non-negative within CI |
| G5: Win rate (pct_positive_net) | > 52% | Must beat coin-flip by a meaningful margin |
| G6: Top-1 contributor share | < 0.30 | No single token drives the result |
| G7: Top-3 contributor share | < 0.50 | No small cluster drives the result |
| G8: Coverage | >= 70% of candidate universe | Sufficient generalisability |

A feature that passes all 8 gates on discovery is then evaluated on the **holdout set** with the same gates. If it passes all 8 gates on holdout, it is promoted to live observer design.

### Multiple Testing Correction

If K features are evaluated on the holdout, the significance threshold for G3 and G4 is adjusted:

- For K <= 3: no correction needed (pre-registered feature list)
- For K = 4-5: Bonferroni correction (divide alpha by K, i.e., 95% CI becomes 98.75% CI for K=5)
- For K > 5: the discovery sweep is too broad; reduce feature list before holdout evaluation

---

## Kill Gates (ANY triggers immediate kill)

A live observer is immediately killed if any of the following conditions are met during live operation:

| Kill Gate | Threshold | Evaluation Window | Rationale |
|-----------|-----------|------------------|-----------|
| K1: Cumulative mean delta | < -1.0% | After 50 pairs | Losing money consistently |
| K2: Cumulative median delta | < -0.5% | After 50 pairs | Median confirms systematic loss |
| K3: Win rate | < 45% | After 100 pairs | Significantly worse than coin-flip |
| K4: Maximum drawdown (cumulative) | < -5.0% | Any time | Capital preservation |
| K5: Consecutive losses | > 15 | Any time | Streak indicates regime change |
| K6: Single-pair loss | < -20% | Any time | Risk management failure |

### Kill Gate Evaluation Schedule

| Pairs Completed | Gates Evaluated |
|----------------|----------------|
| 0-49 | K4, K5, K6 only (insufficient sample for statistical gates) |
| 50-99 | K1, K2, K4, K5, K6 |
| 100+ | All gates (K1-K6) |

---

## Promotion-to-Live Checklist

Before a live observer is launched, the following must be confirmed:

- [ ] Feature passes all 8 promotion gates on discovery set
- [ ] Feature passes all 8 promotion gates on holdout set (with multiple testing correction if applicable)
- [ ] Pre-registration document is committed to GitHub before holdout evaluation
- [ ] Kill gates are implemented in the observer code (not just documented)
- [ ] Observer service has automatic kill-switch triggered by K1-K6
- [ ] Dashboard displays live kill-gate status
- [ ] Backup and retention policy is active
- [ ] No changes to scanner, feature collection, or label derivation since holdout evaluation

---

## What This Gate Does NOT Cover

This gate covers the statistical evidence required for promotion. It does not cover:

- **Execution risk:** The net-proxy uses CPAMM-based round-trip cost, which may underestimate actual execution costs (slippage, MEV, failed transactions).
- **Capacity risk:** The signal may not scale to meaningful position sizes.
- **Regime risk:** The signal may be specific to the market conditions during the collection period.
- **Operational risk:** Service failures, API outages, database corruption.

These risks must be addressed separately before any real capital is deployed.
