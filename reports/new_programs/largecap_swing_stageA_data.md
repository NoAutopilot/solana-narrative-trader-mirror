# Large-Cap Swing Stage A — Data Report

**Date:** 2026-03-15  
**Experiment ID:** 010  
**Stage:** A (Event Study)

---

## Data Source

All data was extracted from the `universe_snapshot` table in the live VPS database (`/root/solana_trader/data/solana_trader.db`). No external APIs, no fabricated data, no historical backfill from third-party sources.

The `universe_snapshot` table is populated by `et_universe_scanner.py`, which queries on-chain DEX pool state every minute. Each row records the price, liquidity, volume, age, and other metrics for a token at a specific point in time.

---

## Raw Data Summary

| Metric | Value |
|--------|-------|
| Total snapshot rows loaded | 271,288 |
| Distinct tokens in raw data | 546 |
| Date range | 2026-03-09T17:00Z to 2026-03-15T02:38Z |
| Snapshot frequency | 1 minute |
| Distinct snapshot times | ~6,530 |

---

## Point-in-Time Universe Construction

The large-cap universe was constructed dynamically at each snapshot using the following gates, applied point-in-time (not retroactively):

| Gate | Threshold |
|------|-----------|
| Liquidity | `liq_usd >= $100,000` |
| 24h Volume | `vol_h24 >= $100,000` |
| Age | `age_hours >= 48` |
| Spam filter | `spam_flag = 0` |
| Eligible | `eligible = 1` |

No hardcoded token list was used. Membership is dynamic: tokens enter when they meet all gates and exit when they fail any gate.

| Metric | Value |
|--------|-------|
| Universe rows after gates | 94,344 |
| Distinct tokens in universe | 25 |
| Rows after gap exclusion | 94,344 (gap rows were already excluded by scanner downtime) |

The 25 qualifying tokens represent the established, larger-cap segment of the Solana speculative token ecosystem during this period. They include tokens such as BOME, WETH, WIF, POPCAT, Fartcoin, Pnut, WBTC, FWOG, RAY, mSOL, CHILLGUY, ORCA, Bonk, and JUP.

---

## Hourly Bar Construction

Hourly OHLCV bars were constructed from the 1-minute snapshots. Each bar requires at least 30 observations within the hour to pass the data quality gate.

| Metric | Value |
|--------|-------|
| Total hourly bars | 1,634 |
| Distinct tokens with bars | 24 |
| Hour range | 2026-03-09T17:00 to 2026-03-15T02:00 |
| Bars per token (median) | ~68 |
| Bars per token (range) | 16 to 126 |

---

## Gap Handling

The scanner experienced a 12-hour outage from 2026-03-13T06:27Z to 2026-03-13T18:43Z. During this window, no snapshots were recorded, so no hourly bars exist for those hours. This is handled naturally: the gap hours simply have no data, so no signals can fire during or immediately after the gap (the 12-hour lookback window is contaminated).

The gap reduces the effective sample by approximately 12 hours of potential signal events across all tokens.

---

## Technical Indicator Computation

After constructing hourly bars, the following indicators were computed per token:

| Indicator | Window | Purpose |
|-----------|--------|---------|
| SMA_4h | 4 hours | Short-term trend for pullback detection |
| SMA_12h | 12 hours | Medium-term trend for uptrend confirmation |
| SMA_12h_lag4 | SMA_12h shifted 4 hours | Trend direction (rising/falling) |
| Vol_SMA_12h | 12 hours | Volume baseline for confirmation |
| High_12h | 12-hour rolling max | Breakout level |
| Low_12h | 12-hour rolling min | Range floor |
| Range_12h_pct | (High_12h - Low_12h) / SMA_12h | Consolidation detection |

Bars with incomplete lookback windows (first 12 hours of each token's history) were excluded, leaving **1,297 bars with valid indicators**.

---

## Signal Events Detected

| Signal | Events | Distinct Tokens |
|--------|--------|-----------------|
| Pullback in uptrend | 108 | Multiple |
| Breakout from consolidation | 16 | Multiple |
| **Total** | **124** | — |

The pullback signal fires more frequently because the conditions are less restrictive (shallow dip in a rising trend). The breakout signal requires a tight consolidation range (<10%) followed by a volume-confirmed breakout, which is a rarer pattern.

---

## Forward Return Coverage

| Horizon | Valid Returns | Coverage |
|---------|-------------|----------|
| +1h | 116 / 124 | 93.5% |
| +4h | 107 / 124 | 86.3% |
| +1d | 86 / 124 | 69.4% |

Missing forward returns occur when the token does not have a valid hourly bar at the required future time (end of dataset, gap contamination, or token exiting the universe).

---

## Data Limitations

1. **Short history**: 5.4 days provides a limited sample window. The results reflect one specific market regime (March 9-15, 2026) and should not be generalized.

2. **Single data source**: All prices come from the scanner's `price_usd` field, which is derived from on-chain DEX pool reserves. There is no cross-validation against a second price source.

3. **Gap contamination**: The 12-hour gap on March 13 reduces the effective sample by approximately 10-15% and eliminates signal events that would have fired during that window.

4. **+1d horizon is underpowered**: With only ~4 complete days of data after the lookback window, the +1d forward returns have very few independent observations. The +1d results should be treated as directional only.

5. **No market-cap data**: The universe is defined by liquidity and volume, not market capitalization. This is a proxy for "large-cap" within the DEX ecosystem, but it is not equivalent to a traditional market-cap screen.
