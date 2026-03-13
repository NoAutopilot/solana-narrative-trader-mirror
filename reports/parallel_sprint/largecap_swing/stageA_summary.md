# Large-Cap Swing Study — Stage A Summary

**Date:** 2026-03-12
**Author:** Manus AI

---

## Verdict: DATA INSUFFICIENT

The existing data is insufficient to properly evaluate the large-cap swing hypothesis. The proxy analysis using +15m and +30m horizons shows the same structural pattern as the +5m analysis: positive gross means driven by tail events, zero gross medians, and negative net returns after realistic costs.

However, this does **not** definitively reject the swing hypothesis because:

1. **The proxy horizons are too short.** +15m and +30m are not swing horizons. The fundamental hypothesis of swing trading is that longer holding periods (+1h to +1d) allow the signal to develop while amortizing fixed transaction costs. The +15m/+30m data cannot test this.

2. **The universe is not filtered.** The sweep was run on the full candidate universe (including micro-cap, newly-launched tokens). The large-cap subset may have fundamentally different dynamics — lower volatility, more mean-reversion, lower costs — that are invisible in the full-universe sweep.

3. **The cost structure is different at longer horizons.** At +5m, the round-trip cost (~0.5%) is a large fraction of the expected gross return (~0.3-0.8%). At +1d, the expected gross return may be 5-20% for the best bucket, making the 0.5-1.5% cost a much smaller fraction. This cannot be evaluated without +1d labels.

## What the Existing Data Shows

The proxy analysis provides three useful signals:

- **Gross means increase with horizon** (from ~0.2-0.8% at +5m to ~0.4-0.9% at +30m for the best features). This is consistent with the swing hypothesis that longer horizons produce larger moves.

- **Gross medians remain zero.** This is the same structural problem as the +5m analysis. The typical candidate does not move in the predicted direction. If this pattern persists at +1h/+4h/+1d, the swing hypothesis is dead.

- **Outlier concentration increases with horizon.** The top-1 contributor share increases from ~3% at +5m to ~46-92% at +30m for some features. This means the longer-horizon results are even more tail-driven than the short-horizon results — a warning sign, not an encouraging one.

## Data Gaps Preventing a Definitive Answer

| Gap | What Is Needed | Effort |
|-----|---------------|--------|
| +1h / +4h / +1d labels | Extend `universe_snapshot` price history or use external price API | 1-2 days of new collection |
| Large-cap subset filter | Re-run sweep on `liq_usd > median AND age_hours > 24` subset | Requires raw row data (not available in sweep CSVs) |
| Intra-period drawdown | Record price path during holding period, not just endpoint | Requires new collection infrastructure |
| Multi-day collection | 24h collection captures only one market cycle; need 3-7 days minimum | 3-7 days of collection |

## Minimum Data Requirements Before Stage B

Before a Stage B study (full evaluation) can be conducted, the following minimum requirements must be met:

1. **Collection duration:** At least 384 fires (4 days) to capture multiple daily cycles.
2. **Horizon labels:** +1h, +4h, and +1d forward returns from a reliable price source.
3. **Universe filter:** Raw row-level data with `liquidity_usd` and `age_hours` for subsetting.
4. **Cost calibration:** Actual execution cost data (not CPAMM proxy) for at least 50 trades.
5. **Drawdown data:** Intra-period max drawdown for at least the +4h and +1d horizons.

## Honest Assessment

The large-cap swing hypothesis is **not yet falsified** but also **not supported** by the available data. The proxy analysis is weakly discouraging (zero medians, increasing outlier concentration), but the fundamental question — whether longer horizons and higher-liquidity tokens produce a different return structure — cannot be answered with +15m/+30m data on the full micro-cap universe.

**Should this branch be pursued?** Only if the cost of collecting the required data is low relative to the information value. The minimum viable data collection (384 fires with +1h/+4h/+1d labels) requires 4 days of collection time and modest engineering effort (extend the label derivation to longer horizons). This is a reasonable investment if the alternative is to stop the program entirely.

**However:** If Feature Acquisition v2 (order flow / urgency family) is proceeding, the swing study should be deprioritized. Running two parallel collection efforts increases operational complexity and dilutes focus. The recommended sequence is: (1) complete v2 collection and sweep, (2) if v2 fails, then evaluate the swing branch as a fallback.
