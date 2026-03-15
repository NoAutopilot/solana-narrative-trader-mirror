# Drift Perps State Study — Stage A Data Document

**Program:** drift_perps_state_stageA
**Author:** Manus AI
**Date:** 2026-03-15

---

## 1. Data Sources Used

All data was sourced from the Drift Protocol public Data API at `data.api.drift.trade`. No authentication was required. No data was fabricated or simulated.

| Data Type | Endpoint | Records Fetched | Date Range |
|-----------|----------|-----------------|------------|
| Funding Rates | `/market/SOL-PERP/fundingRates/{Y}/{M}/{D}` | 2,164 | 2025-12-15 to 2026-03-15 (90 days) |
| Oracle Price | `/amm/oraclePrice` | 10,801 | 2026-02-13 to 2026-03-15 (30 days) |
| Liquidations | `/stats/liquidations` (paginated) | 2,100 | 2026-03-14 to 2026-03-15 (~12 hours) |
| Open Interest | `/amm/openInterest` | 997 | 2026-02-13 to 2026-03-15 (30 days) |

---

## 2. Data Quality and Limitations

**Funding rates** provided the deepest and most reliable history. Each day returned exactly 24 records (hourly funding periods), yielding 2,164 total observations across 90 days. Each record includes `fundingRate`, `markPriceTwap`, `oraclePriceTwap`, `cumulativeFundingRateLong`, `cumulativeFundingRateShort`, `periodRevenue`, and `baseAssetAmountWithAmm`. This is sufficient for both H1 (funding dislocation) and H2 (mark-oracle divergence) state variable construction.

**Oracle price** data was fetched at approximately 4-minute resolution (10,801 samples over 30 days). This serves as the price series for computing forward returns at all horizons. The 30-day depth is the binding constraint on the effective study period — funding rate events older than 30 days cannot have forward returns computed and are excluded from the analysis.

**Liquidation data** is the most significant limitation. The paginated `/stats/liquidations` endpoint returned only 2,100 records spanning approximately 12 hours (2026-03-14 14:40 to 2026-03-15 03:13). This is far shorter than the 30-day oracle price window, severely limiting H3. The API appears to retain only recent liquidation events, not a full historical archive.

**Open interest** data (997 points at ~43-minute resolution over 30 days) was fetched but not directly used as a primary state variable. It remains available for supplementary analysis.

---

## 3. Event Construction Summary

### H1: Funding Dislocation

The funding rate z-score was computed using a trailing 72-hour rolling window. Of 2,164 funding observations, 364 had an absolute z-score exceeding the 1.5 threshold. However, only 107 of these fell within the 30-day oracle price window and could have forward returns computed. The mean absolute z-score among triggered events was 2.07, with a maximum of 4.31. Approximately 62% of triggered events had positive z-scores (longs paying shorts).

### H2: Mark–Oracle Divergence

The mark-oracle spread was computed as `(markPriceTwap - oraclePriceTwap) / oraclePriceTwap * 100` at each funding rate observation. Of 2,164 observations, 171 had an absolute spread exceeding 0.10%. Only 43 fell within the oracle price window. Notably, 100% of triggered events had negative spreads (mark below oracle), indicating a persistent discount of the Drift mark price relative to the Pyth oracle during this period. The mean absolute spread was 0.130% with a maximum of 0.250%.

### H3: Liquidation / Stress State

Liquidation events were counted in trailing 1-hour windows at each funding rate checkpoint. Due to the limited liquidation history (~12 hours), only 6 checkpoints had any trailing liquidations, and the 90th percentile threshold was effectively 1 event. Only 4 of these 6 events had valid +4h forward returns. This sample size is far below the G1 minimum of 30 events.

| Hypothesis | Total Triggered | With Valid Returns (15m) | With Valid Returns (1h) | With Valid Returns (4h) |
|------------|----------------|--------------------------|-------------------------|-------------------------|
| H1: Funding Dislocation | 364 | 107 | 107 | 107 |
| H2: Mark-Oracle Divergence | 171 | 43 | 43 | 43 |
| H3: Liquidation/Stress | 6 | 6 | 6 | 4 |

---

## 4. What Was Blocked

The Drift Data API does not provide a deep historical archive of liquidation events. The `/stats/liquidations` endpoint appears to retain only the most recent ~12 hours of data. This makes H3 (Liquidation/Stress State) structurally underpowered. A full historical liquidation dataset would require either a custom on-chain indexer or a third-party data provider (e.g., Flipside, Dune Analytics), neither of which was available for this study.

No proxies were used. The liquidation data is real but insufficient.

---

## 5. No Fabricated Data

All prices, funding rates, and liquidation events are sourced directly from the Drift Protocol Data API. No synthetic data, simulated histories, or interpolated values were used. Forward returns are computed from the oracle price series using nearest-neighbor matching with a 5-minute tolerance window.

---

## References

[1]: https://data.api.drift.trade "Drift Protocol Data API"
[2]: https://docs.drift.trade/developers/data-api "Drift Data API Documentation"
