# Age-Stratified Observer — NO-GO Note
**Date:** 2026-03-10
**Status:** REJECTED

## 1. Decision Summary
The proposed `pfm_age_stratified_cont_v1` observer is **not approved** for live launch. 

## 2. Reason for Rejection
- **Not Sufficiently New:** `log_age` is a known feature within the existing momentum/direction family. Launching it would violate the family closure agreement.
- **Evidence Fragility:** The positive mean (+0.003) observed in the retrospective sweep is marginal and does not override the failure of the prior age-conditioned robustness check, which showed negative medians and a 95% CI crossing zero.
- **Outlier Dependency:** The signal quality is heavily dependent on a small number of volatile tokens rather than a systematic, repeatable effect.
- **Strategic Focus:** The highest expected value lies in acquiring truly orthogonal information families (order-flow, quote-quality, market-state), not in further variants of the current feature set.

## 3. Conclusion
“No new live observer is approved from the current feature set.”
