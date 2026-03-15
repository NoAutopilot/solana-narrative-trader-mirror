# Drift Perps State Study — Stage A Design Document

**Program:** drift_perps_state_stageA
**Author:** Manus AI
**Date:** 2026-03-15
**Status:** Active — Stage A

---

## 1. Objective

This study determines whether structured state variables observable in the Drift Protocol perpetual futures market (SOL-PERP) contain any robust, cost-adjusted directional edge at short-to-medium horizons. It is a clean, adversarial event-study on Solana perps market structure, entirely independent of the closed spot-token signal programs (momentum/reversion, feature acquisition v2, large-cap swing, who-family pilot).

---

## 2. Primary Hypotheses

Three hypotheses are tested. No additional hypotheses will be added unless one of these is impossible to test and the blocker is documented.

### H1: Funding Dislocation

When the hourly funding rate on SOL-PERP is unusually stretched (positive or negative), does the oracle price mean-revert or continue over the subsequent +15m, +1h, and +4h horizons?

**State variable:** The z-score of the current funding rate relative to a trailing 72-hour (72-observation) rolling window of hourly funding rates. An "event" is triggered when the absolute z-score exceeds 1.5.

**Direction logic:** When funding is extremely positive (longs paying shorts), the hypothesis predicts downward mean-reversion (short bias). When funding is extremely negative (shorts paying longs), the hypothesis predicts upward mean-reversion (long bias). The signed forward return is computed accordingly: `signed_r = -sign(funding_z) * raw_r`.

### H2: Mark–Oracle Divergence

When the Drift AMM mark price meaningfully diverges from the Pyth oracle price, is there a tradable reversion edge?

**State variable:** The percentage spread `(mark - oracle) / oracle * 100` computed at each funding-rate observation timestamp using the `markPriceTwap` and `oraclePriceTwap` fields. An "event" is triggered when the absolute spread exceeds 0.10%.

**Direction logic:** When mark is above oracle (positive spread), the hypothesis predicts downward reversion (short bias). When mark is below oracle (negative spread), the hypothesis predicts upward reversion (long bias). The signed forward return is: `signed_r = -sign(spread) * raw_r`.

### H3: Liquidation / Stress State

After clusters of liquidation events, does the SOL-PERP market show a repeatable directional or mean-reverting response?

**State variable:** The count of liquidation events in the trailing 1-hour window at each hourly checkpoint. An "event" is triggered when the trailing-1h liquidation count exceeds the 90th percentile of all trailing-1h counts in the dataset.

**Direction logic:** Following a liquidation cluster, the hypothesis predicts upward mean-reversion (long bias), on the theory that forced selling creates temporary dislocations. The signed forward return is: `signed_r = raw_r` (long bias after stress).

---

## 3. Data Sources

All data is sourced from the Drift Protocol public Data API (`data.api.drift.trade`), which requires no authentication.

| Data Type | Endpoint | Resolution | Confirmed Depth |
|-----------|----------|------------|-----------------|
| Funding rates | `/market/SOL-PERP/fundingRates/{Y}/{M}/{D}` | 1 hour (24/day) | 90+ days |
| Oracle price | `/amm/oraclePrice?marketName=SOL-PERP&start=X&end=Y&samples=N` | ~4 min (11,000 max) | 30 days |
| Mark price TWAP | Embedded in funding rate records (`markPriceTwap` field) | 1 hour | 90+ days |
| Oracle price TWAP | Embedded in funding rate records (`oraclePriceTwap` field) | 1 hour | 90+ days |
| Liquidations | `/stats/liquidations` (paginated) | Event-level | Full history |
| Open interest | `/amm/openInterest?marketName=SOL-PERP&start=X&end=Y&samples=N` | ~43 min | 30 days |

**Forward returns** are computed from the oracle price time series at ~4-minute resolution, interpolated to the exact funding-rate timestamps.

**No data is fabricated.** If any source is unavailable at runtime, the affected hypothesis is marked BLOCKED.

---

## 4. Horizons

Primary decision horizons:

| Horizon | Offset | Use |
|---------|--------|-----|
| +15m | 900 seconds | Primary |
| +1h | 3,600 seconds | Primary |
| +4h | 14,400 seconds | Primary |

If +1d data is available with sufficient depth, it will be included as an exploratory appendix only, not a primary decision horizon.

---

## 5. Cost Scenarios

Drift SOL-PERP charges 0.035% taker fee and provides -0.002% maker rebate. The study uses three cost scenarios representing round-trip (entry + exit) costs:

| Scenario | Round-Trip Cost | Rationale |
|----------|----------------|-----------|
| Optimistic | 0.02% | Maker entry + maker exit with rebate |
| Baseline | 0.05% | Mixed maker/taker execution |
| Conservative | 0.10% | Full taker both legs plus slippage |

These replace the user's initial 0.02% / 0.05% / 0.10% suggestions, which happen to align with realistic Drift fee structures.

---

## 6. Output Metrics

For each hypothesis / horizon / cost scenario combination, the following metrics are computed:

| Metric | Definition |
|--------|------------|
| N | Number of events in the bucket |
| Winsorized Mean Gross | Mean of signed forward returns, winsorized at 1st/99th percentile |
| Winsorized Mean Net | Winsorized mean gross minus round-trip cost |
| Median Gross | Median of signed forward returns |
| Median Net | Median gross minus round-trip cost |
| % Positive | Fraction of events with positive signed forward return |
| Bootstrap CI (Mean Net) | 95% CI from 5,000 bootstrap resamples of mean net |
| Bootstrap CI (Median Net) | 95% CI from 5,000 bootstrap resamples of median net |
| Top-1 Share | Fraction of total gross PnL contributed by the single largest event |
| Top-3 Share | Fraction of total gross PnL contributed by the three largest events |

---

## 7. Pass / Fail Gates

A hypothesis/horizon/cost combination passes **only if all** of the following are satisfied:

| Gate | Criterion |
|------|-----------|
| G1: Sample Size | N >= 30 events |
| G2: Mean Net | Winsorized mean net > 0 |
| G3: Median Net | Median net > 0 |
| G4: CI Lower | Bootstrap CI lower bound for mean net > 0 |
| G5: Concentration | Top-1 share < 25% AND top-3 share < 50% |
| G6: Distinction | Result is structurally distinct from the dead spot-token families |

---

## 8. Kill Criteria

The study is killed (verdict = NO-GO) if:

1. Zero hypothesis/horizon/cost combinations pass all gates.
2. All passing combinations have N < 50 and marginal CIs.
3. The surviving signal is structurally equivalent to momentum/reversion or feature-tape ideas from prior programs.

The study is marked BLOCKED if:

1. A critical data source is unavailable or returns insufficient history.
2. Forward return computation is impossible due to missing price data.

---

## 9. Study Period

The study uses the maximum available data depth:

- Funding rates: 90 days (2025-12-15 to 2026-03-14)
- Oracle price for forward returns: 30 days (2026-02-13 to 2026-03-14)
- Liquidations: full available history

The binding constraint is the oracle price series (30 days). Events from the funding rate history that fall outside the oracle price window cannot have forward returns computed and are excluded. This limits the effective study period to approximately 30 days.

---

## 10. Relationship to Prior Programs

This study is entirely independent of:

| Prior Program | Why This Is Different |
|---------------|----------------------|
| Momentum/Reversion | Spot meme tokens, not perps; no funding/mark-oracle state |
| Feature Acquisition v2 | Spot microstructure features, not perps state variables |
| Large-Cap Swing | Spot price patterns, not derivatives market structure |
| Who Family Pilot | On-chain wallet analysis, not market state |

The state variables tested here (funding rate z-score, mark-oracle spread, liquidation clustering) are structurally distinct from any feature family in the prior programs.
