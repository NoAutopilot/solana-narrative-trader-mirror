# Final Recommendation — Parallel Sprint

**Date:** 2026-03-12
**Author:** Manus AI

---

## Recommended Next Move

### **Proceed to Feature Acquisition v2 Implementation**

Specifically: implement Family 1 (trade-by-trade order flow / urgency) as the primary new feature family, using the holdout pipeline and promotion gates defined in Workstream 2.

**Why this option:**

The retrospective decision pack (Workstream 1) conclusively established that the failed momentum/direction family suffered from fundamental signal weakness — not late entry, wrong horizon, or wrong product form. This rules out any refinement of the existing features and demands a genuinely novel approach.

The v2 QA (Workstream 2) confirmed that the pipeline design is sound and that Family 1 (order flow / urgency) is the only candidate with both high novelty and high signal plausibility. The holdout pipeline spec provides a rigorous, pre-registered framework that prevents the most common failure modes (outlier-driven means, temporal clustering, multiple testing bias).

The large-cap swing study (Workstream 3) showed that the swing hypothesis cannot be evaluated with existing data and would require 4+ days of additional collection. The proxy analysis is weakly discouraging. This branch should be deferred, not pursued in parallel.

---

## Runner-Up Option

### **Stop Program**

If the decision-maker's prior on finding alpha in Solana DEX micro-caps is below ~20%, stopping is the rational choice. The infrastructure is preserved and can be reactivated if market conditions change or new data sources become available. The durable learnings from v1 (median gate, coverage gate, pre-registration discipline) have permanent value regardless of whether the program continues.

---

## Explicit "Do Not Do" List

1. **Do not re-run any variant of the momentum/direction family.** This includes continuation, reversion, age-conditioned, rank-lift, or horizon-extended variants. The family is exhausted.

2. **Do not implement Family 2 (route / quote quality).** It extends the same execution-quality hypothesis that already failed in v1 (`jup_vs_cpamm_diff_pct`, `round_trip_pct`, `impact_buy/sell_pct` — all SKIP).

3. **Do not run the large-cap swing study in parallel with v2 collection.** This dilutes focus and increases operational complexity. If v2 fails, the swing study becomes the fallback option.

4. **Do not launch any live observer before the holdout evaluation passes all 8 promotion gates.** No exceptions, no "close enough," no "we'll monitor it closely."

5. **Do not modify the promotion gates after seeing holdout data.** The gates are pre-registered. If the result is ambiguous, the holdout is consumed and a new collection run is required.

6. **Do not skip the paper-trading phase.** Before any real capital is deployed, the observer must run in paper-trading mode for at least 100 pairs to calibrate actual execution costs vs the CPAMM proxy.

---

## Evidence Still Missing Before Any New Live Observer

| Evidence Required | Source | Timeline |
|------------------|--------|----------|
| Family 1 features collected for 96+ fires | feature_tape_v2 + new order-flow collection script | 2-4 weeks |
| Discovery sweep passes all 8 promotion gates | Retrospective analysis on discovery set | +2h after collection |
| Holdout evaluation passes all 8 promotion gates | Single-pass evaluation on holdout set | +1h after discovery sweep |
| Actual execution cost calibration | Paper-trading phase (100+ pairs) | +1 week after holdout pass |
| Kill gates implemented in observer code | Engineering | +1 day |
| Orca/Meteora coverage gap assessment | Helius API evaluation | +1 day |

**Minimum time to live observer:** 3-5 weeks from today, assuming v2 collection starts immediately and all gates pass on the first attempt.

**Most likely outcome:** The v2 collection produces useful data but the signal does not pass all 8 promotion gates, leading to either (a) a refined collection with lessons learned, or (b) program stop. This is the expected outcome and is not a failure — it is the scientific process working correctly.

---

## Summary

The single best next step is to proceed with Feature Acquisition v2, focusing on Family 1 (order flow / urgency), using the pre-registered holdout pipeline and promotion gates. The infrastructure is ready, the pipeline design is sound, and the feature family is genuinely novel. The program should be prepared for the most likely outcome (signal does not pass gates) and have a clean exit path ready.
