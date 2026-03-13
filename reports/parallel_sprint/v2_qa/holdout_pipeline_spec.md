# Holdout Pipeline Specification — Feature Acquisition v2

**Date:** 2026-03-12
**Author:** Manus AI
**Status:** PRE-REGISTERED — written before any v2 data is examined

---

## Purpose

This document defines the exact discovery/holdout split, minimum sample sizes, temporal split rules, and holdout integrity constraints for any retrospective sweep conducted on `feature_tape_v2` data. These rules are pre-registered and must not be modified after the holdout boundary is set.

---

## Collection Parameters

Feature Tape v2 collects approximately 38-50 rows per fire at 15-minute intervals (fires at :00, :15, :30, :45 UTC). The target collection run is 96 fires (~24 hours), producing approximately 3,600-4,800 rows.

---

## Discovery / Holdout Split

### Temporal Split Rule

The split is strictly temporal — no random sampling, no stratified sampling. All fires before the split point are discovery; all fires after are holdout. This prevents any form of temporal leakage.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Discovery set | First 72 fires (75%) | ~18 hours of data, ~2,700-3,600 rows |
| Holdout set | Last 24 fires (25%) | ~6 hours of data, ~900-1,200 rows |
| Split boundary | Fire 73 (by chronological order) | Clean temporal boundary |
| Gap between sets | 0 fires | No gap needed — features are strictly pre-fire |

### Why 75/25 and Not 80/20 or 50/50

A 75/25 split balances discovery power against holdout reliability. With ~40 rows per fire, the holdout set contains approximately 960 rows — enough for bootstrap CIs with reasonable width. A 50/50 split would reduce discovery power unnecessarily. An 80/20 split would leave only ~768 holdout rows, which is marginal for stable bootstrap estimates.

### Minimum Sample Size for Valid Sweep

| Metric | Minimum | Rationale |
|--------|---------|-----------|
| Discovery rows | 2,000 | Enough for tercile/quintile bucketing with n >= 400 per bucket |
| Holdout rows | 750 | Enough for bootstrap CI with width < 1% at 95% confidence |
| Discovery fires | 50 | Enough for fire-level diversity across time-of-day and market regimes |
| Holdout fires | 20 | Enough for out-of-sample temporal diversity |
| Micro-covered rows (holdout) | 500 | Enough for micro-native feature evaluation |

If any minimum is not met, the sweep is invalid and must not be used for promotion decisions.

---

## Holdout Integrity Constraints

### What Constitutes a "Clean" Holdout

1. **No parameter tuning after split.** All feature selection, bucket boundaries, threshold choices, and cost assumptions must be fixed using discovery data only. The holdout is evaluated exactly once with the pre-registered parameters.

2. **No peeking.** No summary statistics, distributions, or any information from the holdout set may be examined before the final evaluation. This includes row counts, feature distributions, and label distributions.

3. **No feature engineering on holdout.** Any new features or transformations must be defined on the discovery set. The holdout set is processed with the identical pipeline.

4. **No multiple testing correction bypass.** If multiple features are evaluated on the holdout, the promotion bar must account for multiple comparisons (Bonferroni or Holm-Bonferroni correction).

5. **Single evaluation.** The holdout is used exactly once. If the result is ambiguous, the holdout is consumed — a new collection run is required for further evaluation.

### Pre-Registration Checklist

Before the holdout evaluation begins, the following must be documented:

- [ ] Feature list (exact column names)
- [ ] Bucket boundaries (tercile/quintile cutoffs from discovery)
- [ ] Cost assumption (round_trip_pct or fixed cost)
- [ ] Net-proxy formula
- [ ] Promotion thresholds (from `future_observer_gate.md`)
- [ ] Kill thresholds (from `future_observer_gate.md`)
- [ ] Number of features being tested (for multiple testing correction)

---

## Label Derivation

### Forward Return Labels

Labels are derived from `universe_snapshot.price_usd` at fire_time + horizon:

| Horizon | Label Column | Source |
|---------|-------------|--------|
| +5m | r_forward_5m | price at fire+300s / price at fire - 1 |
| +15m | r_forward_15m | price at fire+900s / price at fire - 1 |
| +30m | r_forward_30m | price at fire+1800s / price at fire - 1 |

### Net-Proxy Formula

```
net_proxy = r_forward_Xm - round_trip_pct
```

Where `round_trip_pct = impact_buy_pct + impact_sell_pct` (CPAMM-based, from `universe_snapshot`). This is a proxy — actual execution costs vary by venue, size, and timing.

### Label Quality Gates

Rows are excluded from the sweep if:

- Forward price snapshot is missing (no snapshot within +/- 60s of target time)
- Forward price snapshot jitter exceeds 60s
- Entry price snapshot is missing
- `label_quality` is `missing` or `missing_disk_gap`

---

## Timeline

| Milestone | Fires | Elapsed Time | Action |
|-----------|-------|-------------|--------|
| Collection start | 0 | 0h | Service starts |
| First-fire proof | 1 | 15m | Verify schema, lane, coverage |
| 10-fire checkpoint | 10 | 2.5h | Verify collection health |
| Discovery set complete | 72 | 18h | Begin discovery sweep |
| Collection complete | 96 | 24h | Holdout set available |
| Discovery sweep | — | +2h after fire 72 | Feature selection, bucket boundaries |
| Holdout evaluation | — | +1h after discovery sweep | Single-pass evaluation |
| Promotion decision | — | +30m after holdout | GO / NO-GO |

---

## Failure Modes Specific to the Holdout Pipeline

1. **Insufficient holdout rows.** If collection drops below 750 holdout rows (due to service interruption, disk issues, or scanner failure), the holdout is invalid. Mitigation: extend collection to 128 fires (32 hours) to ensure adequate holdout size.

2. **Temporal non-stationarity.** If market conditions change dramatically between discovery and holdout periods (e.g., SOL price crash, network outage), the holdout may not be representative. Mitigation: document market conditions at split boundary; if conditions are extreme, flag the holdout as potentially non-representative.

3. **Discovery overfitting.** If many features are tested in discovery and only the best is promoted to holdout, the holdout evaluation is biased. Mitigation: limit discovery to at most 5 candidate features; apply Bonferroni correction for multiple testing.
