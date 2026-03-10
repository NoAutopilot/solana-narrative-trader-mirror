# LEARNINGS LEDGER

Canonical record of completed experiments, their outcomes, and durable learnings.
Each entry is immutable once written. Append only.

---

## Entry 001 — PFM Continuation Observer
**run_id:** `1677a7da`
**Period:** 2026-03-07T01:15Z → 2026-03-09T06:28Z (≈53 hours)
**Service:** `solana-pfm-cont-observer.service` (stopped and disabled 2026-03-09T06:28Z)
**Final classification:** `RANKING FEATURE ONLY / NOT PROMOTABLE`

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with higher recent 5-minute momentum (`entry_r_m5 > 0`, signal) outperforms the token with lower momentum (`entry_r_m5 < 0`, control) at a +5 minute horizon.

### Final metrics (canonical View B, n=212)

| Metric | Value |
|---|---|
| n_pairs_complete_5m | 212 |
| mean_delta_+5m | +0.007804 |
| median_delta_+5m | +0.000057 |
| % delta > 0 | 50.0% (106/212) |
| 95% CI | [−0.007806, +0.023414] |
| mean_signal_net_+5m | −0.022255 |
| mean_control_net_+5m | −0.030059 |

### Data quality
All gates passed: entry_coverage=100%, 5m_coverage=100%, row_valid=100%, HTTP_429=0.

### Why not promotable
The signal token outperforms its control on average, but loses money in absolute terms (mean_signal_net = −0.022). The CI crosses zero. The median delta is near zero. The relative edge is real but not large enough or consistent enough to constitute a tradeable directional signal.

### Regime filter sidecar result
`pfm_continuation_regime_filter_sidecar_v1`: tested breadth_positive, median_r_m5_positive, signal_r_m5_strong (tercile + quintile) across 187 pairs with pool data. No subgroup produced mean_signal_net > 0. Verdict: `RANKING FEATURE ONLY`.

### Durable learnings
1. **Positive relative delta ≠ promotable signal.** A signal that loses less than its control is a ranking feature, not a directional edge. Promotion requires mean_signal_net > 0.
2. **Regime filters did not rescue continuation.** The breadth and median-r_m5 filters did not improve absolute signal net. The `median_r_m5_positive` filter actually worsened mean delta (−0.004 vs +0.010 baseline), suggesting continuation is weaker during rising-pool regimes.
3. **Outlier sensitivity is high.** top_contributor_share ≈ 0.038 across all subgroups; 54/212 pairs were outliers (|delta| ≥ 0.10). The mean is driven by a fat tail, not a consistent edge.
4. **Data quality infrastructure is solid.** The observer framework, canonical report script, and reconciliation tooling all worked correctly. The reporting discrepancy (dashboard vs reconciliation) was a sample-size snapshot issue, not a data bug.
5. **Reversion hypothesis is now the natural next test.** If continuation is a ranking feature, the inverse (r_m5 < 0 signal) may produce a reversion edge. This is the next preregistered experiment.

---

## Entry 002 — LCR Continuation Observer
**run_id:** `0c5337dd-2488-4730-90b6-e371fd1e9511` (primary; 2 additional runs pooled)
**Family:** `lcr_continuation_observer_v1`
**Lane:** `lcr`
**Direction:** continuation
**Final classification:** `SUPPORTED AS RANKING FEATURE / NOT PROMOTABLE`

### Hypothesis tested
> Among matched token pairs in the `lcr` lane, the token with higher recent momentum (signal) outperforms the token with lower momentum (control) at a +5 minute horizon.

### Final metrics (ALL_COMPLETED_VIEW, n=122 primary; n=286 pooled)

| Metric | Value (primary) | Value (pooled) |
|--------|----------------|----------------|
| n_pairs_complete_5m | 122 | 286 |
| mean_delta_+5m | +0.001238 | — |
| % delta > 0 | 62.5% | — |
| mean_signal_net_+5m | −0.010902 | — |
| mean_control_net_+5m | −0.012139 | — |

### Durable learnings
1. **LCR continuation shows a persistent positive relative delta** across multiple runs, but absolute signal net is negative in all runs. The edge is real as a ranking signal only.
2. **LCR continuation is not a standalone promotable long signal at +5m.**
3. **Next branch:** Test whether LCR continuation signal can be used as a filter or ranking layer on top of another entry criterion that produces positive absolute net.

---

## Entry 003 — PFM Reversion Observer (in progress)
**run_id:** `99ed0fd1`
**Family:** `pfm_reversion_observer_v1`
**Lane:** `pumpfun_mature`
**Direction:** reversion
**Classification:** `ACCUMULATING` (n=20 of 50 required for decision)

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with the most negative recent 5-minute momentum (`entry_r_m5 < 0`, signal) outperforms the token with non-negative momentum (`entry_r_m5 >= 0`, control) at a +5 minute horizon.

### Current metrics (ALL_COMPLETED_VIEW, n=20)

| Metric | Value |
|--------|-------|
| n_pairs_complete_5m | 20 |
| mean_delta_+5m | +0.003549 |
| median_delta_+5m | +0.003377 |
| mean_signal_net_+5m | −0.045398 |
| mean_control_net_+5m | −0.048946 |
| entry_coverage | 100% |
| row_valid | 100% |

### Notes
Early data quality is clean. Relative delta is mildly positive but n is too small for classification. Decision checkpoint at n=50.

---

## Entry 003 — PFM Reversion Observer (FINAL)
**run_id:** `99ed0fd1`
**Family:** `pfm_reversion_observer_v1`
**Lane:** `pumpfun_mature`
**Direction:** reversion
**Final classification:** `INCONCLUSIVE / ABANDONED`
**Stopped:** 2026-03-10T14:15Z

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with the most negative recent 5-minute momentum (`entry_r_m5 < 0`, signal) outperforms the token with non-negative momentum (`entry_r_m5 >= 0`, control) at a +5 minute horizon via mean reversion.

### Final metrics (n=208 complete pairs)

| Metric | Value |
|---|---|
| n_pairs_complete_5m | 208 |
| mean_signal_net_+5m | ~−0.030 |
| mean_control_net_+5m | ~−0.035 |
| mean_delta_+5m | mildly positive |
| absolute net | negative throughout |

### Durable learnings
1. **Reversion hypothesis not confirmed.** The signal token lost less than the control on average, but both lost money. Mean reversion did not produce positive absolute expected value at +5m.
2. **The pumpfun_mature lane has persistently negative mean markout at +5m.** Both continuation and reversion branches confirm this. The lane itself is the problem, not the direction of the signal.
3. **Relative delta without positive absolute net is not a tradeable edge.** This reinforces Entry 001 learning #1.

---

## Entry 004 — LCR Rank-Lift Sidecar
**run_id:** `bb7244cd`
**Family:** `lcr_rank_lift_sidecar_v1`
**Lane:** `large_cap_ray`
**Direction:** rank-lift (feature selection over baseline scorer)
**Final classification:** `NON-BINDING / LOW INCREMENTAL VALUE`
**Stopped:** 2026-03-10T21:00Z

### Hypothesis tested
> Among large_cap_ray candidates with r_m5 > 0, the highest-scoring token (promoted choice) outperforms the baseline top-1 at +5m.

### Final metrics (n=19 fires)

| Metric | Value |
|---|---|
| n_fires_total | 19 |
| n_same_token | 18 (94.7%) |
| n_distinct_promotions | 1 (5.3%) |
| same_token_rate | 94.7% |
| mean_lift_+5m (all) | −0.045 |
| mean_lift_+5m (distinct only) | −0.227 (n=1, not interpretable) |

### Trigger decomposition
- NO_FEATURE_IN_TOP3: 16/19 fires (84.2%) — r_m5 > 0 gate not satisfied
- DISTINCT_PROMOTION: 1/19 fires (5.3%)
- BASELINE_ALREADY_FEATURED: 0/19 fires

### Durable learnings
1. **The r_m5 > 0 gate is almost never satisfied in live market conditions.** In 16 of 19 fires, no large_cap_ray candidate had positive r_m5. The feature trigger rate is too low to be informative.
2. **The retrospective sweep revealed that r_m5 continuation is negatively correlated with +5m outcome in the lcr_cont signal population** (ρ = −0.144, p = 0.010). The rank-lift sidecar's core assumption was wrong.
3. **A feature that rarely triggers cannot be evaluated.** At 5.3% trigger rate, reaching n=15 distinct promotions would require ~300 fires (~75 hours). Not worth the observation cost.
4. **Trigger rate must be estimated before deploying a rank-lift sidecar.** Pre-deployment analysis of how often the feature condition is satisfied in the live universe is necessary.

---

## Entry 005 — Momentum/Reversion Family — Final Synthesis
**Date:** 2026-03-10
**Decision:** FAMILY ABANDONED

### Branches covered
- LCR Continuation (`0c5337dd`): RANKING FEATURE ONLY / NOT PROMOTABLE
- PFM Continuation (`1677a7da`): RANKING FEATURE ONLY / NOT PROMOTABLE
- PFM Reversion (`99ed0fd1`): INCONCLUSIVE / ABANDONED
- LCR Rank-Lift Sidecar (`bb7244cd`): NON-BINDING / LOW INCREMENTAL VALUE

### Conclusion
> **"Current momentum/reversion family does not justify further live observers."**

### Durable learnings
1. **r_m5 continuation is not a directional edge at +5m.** It is a ranking feature at best, and is negatively correlated with outcome in the primary signal population (lcr_cont).
2. **Absolute mean net markout at +5m is negative across all branches and lanes tested.** The +5m horizon may be too short for these token types, or the signal family itself lacks edge.
3. **The only consistent cross-branch feature is entry_vol_h1** (positive ρ, consistent tercile diff), but it predicts loss reduction, not positive absolute expected value.
4. **New signal family required.** Next candidates: order-flow/imbalance, market-state/breadth, quote/impact/route-quality.

---

## Entry 006 — Age-Conditioned Continuation Retrospective Check
**Date:** 2026-03-10
**Type:** Retrospective subgroup analysis (read-only, no live observer)
**Source data:** PFM Continuation observer, run_id `1677a7da`
**Final classification:** `NO-GO — OUTLIER-DRIVEN / NOT STRONG ENOUGH`

### Hypothesis tested
> Among pumpfun_mature tokens with r_m5 > 0, the oldest tercile (age > 53.8h at fire time) outperforms the non-old tercile at +5m.

### Results (n=71 old-tercile signal rows)

| Metric | Value | GO/NO-GO |
|---|---|---|
| n | 71 | PASS (≥30) |
| mean signal net +5m | +0.003455 | PASS (>0) |
| median signal net +5m | −0.024952 | **FAIL** (<0) |
| mean delta +5m | +0.021214 | PASS (>0) |
| median delta +5m | −0.000637 | **FAIL** (<0) |
| top contributor share | 12.1% | PASS (<25%) |
| 95% CI | [−0.006, +0.052] | crosses zero |

### Durable learnings
1. **Positive mean driven entirely by outlier tokens.** Doom (+0.627) and BioLLM (+0.460) account for the positive mean. The same tokens appear in the worst rows too. This is token-specific volatility, not a systematic age effect.
2. **Median is the correct primary metric for fat-tailed distributions.** The mean is misleading here. Median signal net = −0.025 and median delta = −0.001 are the true central tendency.
3. **Subgroup analysis on n=71 is insufficient to override the family-level conclusion.** The positive mean is consistent with noise from a family that has already shown no absolute edge across 5 branches.

---

## Entry 007 — Momentum / Direction Family — FINAL Synthesis
**Date:** 2026-03-10
**Decision:** FAMILY ABANDONED

### All branches
| Branch | run_id | n | Classification |
|---|---|---|---|
| LCR Continuation | `0c5337dd` | 248 | RANKING FEATURE ONLY / NOT PROMOTABLE |
| PFM Continuation | `1677a7da` | 212 | RANKING FEATURE ONLY / NOT PROMOTABLE |
| PFM Reversion | `99ed0fd1` | 208 | INCONCLUSIVE / ABANDONED |
| LCR Rank-Lift Sidecar | `bb7244cd` | 19 | NON-BINDING / LOW INCREMENTAL VALUE |
| Age-Conditioned Continuation (retro) | — | 71 | NO-GO — OUTLIER-DRIVEN |

### Exact conclusion
> **"No new live observers will be launched from this family."**

### Durable learnings
1. Relative edge without positive absolute net is not a tradeable signal.
2. r_m5 continuation is not a directional edge at +5m (negatively correlated in lcr_cont, ρ=−0.144, p=0.010).
3. Mean reversion was not confirmed either.
4. Outlier sensitivity is the primary risk in small-n subgroup analysis — median and CI are the correct primary metrics.
5. The +5m horizon may be structurally unfavorable for these token types.
6. Feature acquisition is the next priority: buy/sell imbalance, transaction acceleration, average trade size are not currently stored in observer rows.

---
