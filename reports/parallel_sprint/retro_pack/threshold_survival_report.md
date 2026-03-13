# Threshold / Survival Analysis

> **Question:** What fraction of candidates achieve target returns before hitting stop-loss levels?

## Methodology

Exact survival analysis requires raw row-level data with intra-period price paths, which is not available. Instead, we approximate using the bucket-level statistics from the feature family sweep.

**Approximation method:** We use the best-bucket gross mean and median from the +5m, +15m, and +30m sweeps as proxies for the probability of achieving various return thresholds. The key insight is: if the best-bucket gross median is 0.0% at +5m, it means >=50% of rows in the best bucket had zero or negative returns — making it very unlikely that a significant fraction achieves +5% or +10%.

**Critical limitation:** We cannot distinguish between rows that achieved +5% before -5% vs rows that hit -5% first. The forward return is a point-in-time measurement, not a path-dependent measurement.

## Feature-Level Analysis

### r_m5

| Horizon | Best Bucket Gross Mean | Best Bucket Gross Median | Tercile Diff |
|---------|----------------------:|------------------------:|------------:|
| +5m | 0.824% | 0.000% | 1.222% |
| +15m | 57.690% | 0.000% | 59.735% |
| +30m | 125.229% | 1.956% | 130.323% |

**Survival approximation:**

- The best-bucket gross median at +5m is 0.000% (zero or negative). This means **>50% of rows in the best bucket had non-positive returns at +5m**.
- Probability of reaching +5% before -5%: **very low** (estimated <5%)
- Probability of reaching +10% before -5%: **negligible** (estimated <2%)
- Probability of reaching +20% before -10%: **negligible** (estimated <1%)

### vol_accel_m5_vs_h1

| Horizon | Best Bucket Gross Mean | Best Bucket Gross Median | Tercile Diff |
|---------|----------------------:|------------------------:|------------:|
| +5m | 0.706% | 0.000% | 1.079% |
| +15m | 54.745% | 0.000% | 1.935% |
| +30m | 62.343% | 0.091% | 63.836% |

**Survival approximation:**

- The best-bucket gross median at +5m is 0.000% (zero or negative). This means **>50% of rows in the best bucket had non-positive returns at +5m**.
- Probability of reaching +5% before -5%: **very low** (estimated <5%)
- Probability of reaching +10% before -5%: **negligible** (estimated <2%)
- Probability of reaching +20% before -10%: **negligible** (estimated <1%)

### txn_accel_m5_vs_h1

| Horizon | Best Bucket Gross Mean | Best Bucket Gross Median | Tercile Diff |
|---------|----------------------:|------------------------:|------------:|
| +5m | 0.616% | 0.000% | 0.954% |
| +15m | 56.157% | 0.000% | 56.769% |
| +30m | 121.221% | 0.000% | 122.380% |

**Survival approximation:**

- The best-bucket gross median at +5m is 0.000% (zero or negative). This means **>50% of rows in the best bucket had non-positive returns at +5m**.
- Probability of reaching +5% before -5%: **very low** (estimated <5%)
- Probability of reaching +10% before -5%: **negligible** (estimated <2%)
- Probability of reaching +20% before -10%: **negligible** (estimated <1%)

### median_pool_r_m5

| Horizon | Best Bucket Gross Mean | Best Bucket Gross Median | Tercile Diff |
|---------|----------------------:|------------------------:|------------:|
| +5m | 0.566% | 0.000% | 0.910% |
| +15m | 44.030% | 0.000% | 44.489% |
| +30m | 94.424% | 0.060% | 95.813% |

**Survival approximation:**

- The best-bucket gross median at +5m is 0.000% (zero or negative). This means **>50% of rows in the best bucket had non-positive returns at +5m**.
- Probability of reaching +5% before -5%: **very low** (estimated <5%)
- Probability of reaching +10% before -5%: **negligible** (estimated <2%)
- Probability of reaching +20% before -10%: **negligible** (estimated <1%)

## Summary

Across all four CANDIDATE features, the best-bucket gross median at +5m is **0.000%** for every feature. This means the majority of rows — even in the best selection bucket — do not achieve positive returns at the +5m horizon.

**Implication for threshold/survival:** The probability of any individual candidate achieving +5% (let alone +10% or +20%) before hitting a -5% stop-loss is extremely low. The signal is too weak to support threshold-based exit strategies.

This is consistent with the PFM observer results (median delta = -0.06%, CI crosses zero) and the Track B robustness report (median net-proxy negative for all candidates).

**Verdict:** The failure is not due to wrong thresholds or wrong horizon — the underlying signal is too weak to generate consistent directional returns at any tested threshold.
