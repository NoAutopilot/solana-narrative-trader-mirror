# Momentum / Direction Family — FINAL Closure Memo

**Date:** 2026-03-10  
**Decision:** FAMILY ABANDONED — NO NEW LIVE OBSERVERS WILL BE LAUNCHED FROM THIS FAMILY  
**Decided by:** User  

---

## Branch Summary

| Branch | run_id | n | Final Classification |
|---|---|---|---|
| LCR Continuation | `0c5337dd` | 248 | RANKING FEATURE ONLY / NOT PROMOTABLE |
| PFM Continuation | `1677a7da` | 212 | RANKING FEATURE ONLY / NOT PROMOTABLE |
| PFM Reversion | `99ed0fd1` | 208 | INCONCLUSIVE / ABANDONED |
| LCR Rank-Lift Sidecar | `bb7244cd` | 19 | NON-BINDING / LOW INCREMENTAL VALUE |
| Age-Conditioned Continuation (retrospective) | — | 71 | NO-GO — OUTLIER-DRIVEN / NOT STRONG ENOUGH |

---

## Branch Details

### LCR Continuation (`0c5337dd`)
**Hypothesis:** LCR-lane tokens with higher r_m5 (signal) outperform lower-r_m5 tokens (control) at +5m.  
**Result:** Positive relative delta (+0.001), but mean_signal_net = −0.011. CI crosses zero. Absolute net negative.  
**Classification:** RANKING FEATURE ONLY / NOT PROMOTABLE

### PFM Continuation (`1677a7da`)
**Hypothesis:** pumpfun_mature tokens with r_m5 > 0 (signal) outperform r_m5 < 0 (control) at +5m.  
**Result:** Mean delta = +0.008, but mean_signal_net = −0.022. CI crosses zero. Regime filter sidecar found no subgroup with positive absolute net.  
**Classification:** RANKING FEATURE ONLY / NOT PROMOTABLE

### PFM Reversion (`99ed0fd1`)
**Hypothesis:** pumpfun_mature tokens with most negative r_m5 (signal) outperform non-negative r_m5 (control) at +5m via mean reversion.  
**Result:** n=208 complete pairs. Mean_signal_net ≈ −0.030. Relative delta mildly positive but small. Absolute net never turned positive.  
**Classification:** INCONCLUSIVE / ABANDONED

### LCR Rank-Lift Sidecar (`bb7244cd`)
**Hypothesis:** Among large_cap_ray candidates with r_m5 > 0, the highest-scoring token outperforms the baseline top-1 at +5m.  
**Result:** 94.7% same-token rate. Only 1 distinct promotion in 19 fires. r_m5 > 0 gate almost never satisfied. Trigger-decomposition: 84% NO_FEATURE_IN_TOP3.  
**Classification:** NON-BINDING / LOW INCREMENTAL VALUE

### Age-Conditioned Continuation (retrospective check, 2026-03-10)
**Hypothesis:** Among pumpfun_mature tokens with r_m5 > 0, the oldest tercile (age > 53.8h) outperforms the non-old tercile at +5m.  
**Result:**
- n = 71 (passes)
- mean signal net +5m = +0.003 (passes)
- **median signal net +5m = −0.025 (FAILS)**
- mean delta +5m = +0.021 (passes)
- **median delta +5m = −0.001 (FAILS)**
- top contributor share = 12.1% (passes)
- 95% CI = [−0.006, +0.052] (crosses zero)
- Positive mean driven by outlier fires (Doom +0.627, BioLLM +0.460); same tokens appear in both top and bottom of distribution.

**Classification:** NO-GO — OUTLIER-DRIVEN / NOT STRONG ENOUGH

---

## Family Conclusion

The momentum/direction family was tested across five branches over approximately three weeks of live observation and retrospective analysis. In every branch, the absolute mean net markout at +5m was negative. Positive relative deltas (signal vs control) were observed in the continuation branches, but these represent loss reduction, not profitable edge. The reversion hypothesis did not confirm. The rank-lift sidecar found the feature trigger rate too low to be informative. The age-conditioned retrospective check produced a positive mean that is entirely outlier-driven — the median is negative, the CI crosses zero, and the same tokens drive both the best and worst outcomes.

> **"No new live observers will be launched from this family."**

---

## Durable Learnings (Final)

1. **Relative edge without positive absolute net is not a tradeable signal.** This was confirmed across five branches. A signal that loses less than its control is a ranking feature, not a directional edge.
2. **r_m5 continuation is not a directional edge at +5m.** It is a ranking feature at best, and is negatively correlated with outcome in the primary signal population (lcr_cont, ρ = −0.144, p = 0.010).
3. **Mean reversion was not confirmed either.** The reversion hypothesis (r_m5 < 0 signal) also failed to produce positive absolute net.
4. **Outlier sensitivity is the primary risk in small-n subgroup analysis.** The age-conditioned positive mean (+0.003) was entirely driven by 2–3 outlier tokens. Median and CI are the correct primary metrics.
5. **The +5m horizon may be structurally unfavorable for these token types.** All branches show negative mean net at +5m. A longer horizon (+15m, +30m) may be worth testing with new features.
6. **Feature acquisition is the next priority.** The true order-flow features (buy/sell imbalance, transaction acceleration, average trade size) are not stored in observer rows. These are the most plausible candidates for a genuinely new information family.

---

## Disposition

- All services stopped and disabled
- All DBs and logs retained on VPS
- No new observers to be started from this family
- No threshold tweaks, no continuation/reversion/rank-lift/age variants
- Next phase: feature acquisition design (see `reports/synthesis/next_family_feature_acquisition_plan.md`)
