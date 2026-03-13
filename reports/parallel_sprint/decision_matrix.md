# Decision Matrix — Parallel Sprint Synthesis

**Date:** 2026-03-12
**Author:** Manus AI

---

## Workstream Verdicts

| Workstream | Question | Verdict | Confidence |
|-----------|---------|---------|------------|
| 1. Retrospective Decision Pack | Why did the failed family fail? | **SIGNAL WEAK** | HIGH — supported by 4 independent analyses |
| 2. Feature Acquisition v2 QA | Can v2 be made scientifically strong? | **SAFE TO PROCEED** | MEDIUM — design is sound but execution risks remain |
| 3. Large-Cap Swing Study | Is a swing branch worth pursuing? | **DATA INSUFFICIENT** | HIGH — the data gap is real and cannot be resolved with proxy analysis |

---

## Cross-Workstream Comparison

### What Each Workstream Tells Us About the Next Step

**Workstream 1** establishes that the failure was not due to entry timing, wrong horizon, or wrong product form — it was fundamental signal weakness. This means any variant of the momentum/direction family (including longer horizons, different thresholds, or basket approaches) will fail for the same reason. The implication is clear: the next step must involve a **genuinely novel feature family**, not a refinement of the existing one.

**Workstream 2** confirms that the v2 pipeline design is sound. The holdout pipeline spec, promotion gates, and failure mode catalogue provide a rigorous framework for evaluating any new feature family. The critical finding is that Family 1 (order flow / urgency) is the only candidate with both high novelty and high signal plausibility. Family 2 (route / quote quality) extends a failed hypothesis and should be deprioritized. Family 3 (market-state gating) is only useful in combination with a working selection signal.

**Workstream 3** shows that the swing hypothesis cannot be evaluated with existing data. The proxy analysis is weakly discouraging (zero medians, increasing outlier concentration at longer horizons), but the fundamental question remains open. Importantly, the swing study requires 4+ days of new data collection with longer-horizon labels — a significant investment that should not be undertaken in parallel with v2 collection.

### Decision Framework

| Option | Evidence For | Evidence Against | Risk | Expected Value |
|--------|-------------|-----------------|------|----------------|
| 1. Proceed to Feature Acquisition v2 | Sound pipeline design; Family 1 has high novelty and plausibility; infrastructure is ready | Same Orca/Meteora coverage gap; RPC rate limits; signal may still be too weak | MEDIUM — 2-4 weeks of collection, modest engineering effort | MODERATE — genuinely novel signal family, but no guarantee of success |
| 2. Run large-cap swing study next | Hypothesis not yet falsified; different market structure at longer horizons | Proxy data is discouraging; requires 4+ days of new collection; zero medians at all tested horizons | HIGH — significant data collection effort with weak prior evidence | LOW — proxy analysis suggests same structural problem (tail-driven means, zero medians) |
| 3. Product-form pivot study | Basket simulation shows diversification reduces variance | Signal weakness is the binding constraint, not product form; no evidence that any product form fixes a weak signal | LOW (cheap to study) | VERY LOW — Workstream 1 conclusively ruled out product form as the issue |
| 4. Stop program | Clean exit; no further resource expenditure; infrastructure preserved for future use | Forfeits the option value of a genuinely novel feature family | ZERO | ZERO (but preserves capital) |

---

## Scoring Matrix

Each option is scored on five dimensions (1-5 scale, 5 = best):

| Dimension | v2 Implementation | Swing Study | Product Pivot | Stop |
|-----------|:-----------------:|:-----------:|:-------------:|:----:|
| Evidence strength | 3 | 1 | 1 | 5 |
| Novelty of approach | 5 | 3 | 1 | N/A |
| Resource efficiency | 4 | 2 | 4 | 5 |
| Expected information value | 4 | 2 | 1 | 0 |
| Downside risk | 3 | 2 | 4 | 5 |
| **Total** | **19** | **10** | **11** | **15** |

**Feature Acquisition v2 scores highest** (19/25) because it combines the strongest novelty, the best pipeline design, and the highest expected information value. Even if the signal fails, the holdout pipeline and gate framework produce durable research value.

**Stop program scores second** (15/25) because it has zero downside risk and preserves all capital. It is the rational choice if the decision-maker's prior on finding alpha in Solana DEX micro-caps is sufficiently low.

---

## Key Uncertainties

1. **Will the Orca/Meteora coverage gap persist?** If Helius or an alternative data source can close this gap, Family 1 coverage rises from ~65% to ~90%, significantly improving the generalisability of results.

2. **Is trade-level urgency a genuine alpha source in Solana DEX markets?** The hypothesis is well-established in traditional equity markets, but Solana DEX microstructure is fundamentally different (AMM-based, no order book, bot-dominated flow). The signal may not transfer.

3. **Will the v2 collection run without operational issues?** The v1 collection had a disk-space failure (20 fires lost). The v2 deployment includes mitigations, but operational risk remains.
