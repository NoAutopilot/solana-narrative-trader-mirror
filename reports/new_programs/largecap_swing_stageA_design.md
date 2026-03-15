# Large-Cap Swing Stage A — Design Document

**Date:** 2026-03-15  
**Program:** Large-Cap Swing  
**Stage:** A (Event Study — No Live Trading)  
**Experiment ID:** 010  
**Status:** IN PROGRESS

---

## Research Question

Does a dynamic, point-in-time large-cap Solana token universe show a robust net edge for either **pullback-in-uptrend** entries or **breakout-from-consolidation** entries at +1h, +4h, and +1d horizons, after accounting for round-trip costs of 0.5%, 1.0%, and 1.5%?

---

## What This Is NOT

This study is not a continuation of the dead public-data memecoin signal line (experiments 001-009). It differs in three fundamental ways:

| Dimension | Old Line (001-009) | This Study (010) |
|-----------|--------------------|--------------------|
| Universe | All memecoins / full scanner output | Established, larger-cap speculative tokens only |
| Horizon | +5m to +4h (mostly short) | +1h, +4h, +1d (slower) |
| Signal type | Cross-sectional feature ranking | Time-series technical patterns (pullback, breakout) |
| Entry logic | "Which token is best right now?" | "Is this token at a favorable entry point in its own history?" |

---

## Data Source

All data comes from the existing `universe_snapshot` table on the VPS, which contains 1-minute snapshots of all tokens tracked by the scanner.

| Parameter | Value |
|-----------|-------|
| Table | `universe_snapshot` in `/root/solana_trader/data/solana_trader.db` |
| Date range | 2026-03-09T17:00Z to 2026-03-15T02:38Z (~5.4 days) |
| Snapshot frequency | 1 minute |
| Distinct snapshot times | 6,529 |
| Total rows | 270,966 |
| Distinct tokens | 546 |
| Known gap | 2026-03-13T06:27Z to 2026-03-13T18:43Z (~12h) |

**No external API data is used.** No historical data is fabricated. The study uses only what the scanner actually recorded.

---

## Universe Construction (Point-in-Time)

The universe is constructed dynamically at each evaluation point. A token is a member of the "large-cap" universe at time `t` if and only if all of the following conditions are met **as of the snapshot at time `t`**:

| Gate | Threshold | Rationale |
|------|-----------|-----------|
| Liquidity | `liq_usd >= $100,000` | Ensures sufficient depth for meaningful entry/exit |
| 24h Volume | `vol_h24 >= $100,000` | Ensures active trading, not stale pools |
| Age | `age_hours >= 48` | Excludes new launches / pump-and-dump phase |
| Spam filter | `spam_flag = 0` | Excludes sub-$1 average trade tokens |
| Eligible | `eligible = 1` | Passes all existing scanner gates |

Membership is **not sticky**: a token that drops below any threshold exits the universe at that snapshot. A token that later recovers re-enters. This prevents survivorship bias.

**No hardcoded token list.** The universe is defined purely by the gates above, applied point-in-time.

---

## Hourly Bar Construction

From the 1-minute `universe_snapshot` data, hourly OHLCV bars are constructed for each token that is a universe member during that hour:

| Field | Definition |
|-------|-----------|
| `open` | `price_usd` at the first minute of the hour |
| `high` | `MAX(price_usd)` during the hour |
| `low` | `MIN(price_usd)` during the hour |
| `close` | `price_usd` at the last minute of the hour |
| `volume` | `MAX(vol_h1)` during the hour (cumulative field, take the latest reading) |
| `n_obs` | Count of 1-minute snapshots in the hour (quality filter: require >= 30) |

Hours with fewer than 30 observations are excluded (data quality gate). Hours during the known gap window are excluded entirely.

---

## Signal Definitions

### Signal 1: Pullback in Uptrend

A token is in a **pullback-in-uptrend** state at the close of hour `t` if:

1. **Uptrend**: The 12-hour simple moving average of close prices is rising (SMA_12h at `t` > SMA_12h at `t-4`)
2. **Pullback**: The close at `t` is below the 4-hour SMA (close < SMA_4h)
3. **Not collapsed**: The close is above the 12-hour SMA (close > SMA_12h) — the pullback is shallow, not a trend reversal
4. **Volume confirmation**: The hourly volume at `t` is at least 50% of the 12-hour average volume

This identifies tokens that are in a rising trend but have temporarily dipped, creating a potential mean-reversion entry.

### Signal 2: Breakout from Consolidation

A token is in a **breakout-from-consolidation** state at the close of hour `t` if:

1. **Prior consolidation**: The 12-hour price range (max high - min low) / SMA_12h is less than 10% — the token was range-bound
2. **Breakout**: The close at `t` exceeds the 12-hour high (close > max high of prior 12 hours)
3. **Volume surge**: The hourly volume at `t` is at least 2x the 12-hour average volume
4. **Not a gap artifact**: The prior hour's close exists and is within 5% of the current hour's open

This identifies tokens breaking out of a tight range with volume confirmation.

---

## Lookback Requirements

Both signals require 12 hours of prior hourly bars. Given the data starts at 2026-03-09T17:00Z, the earliest signal can fire at approximately 2026-03-10T05:00Z. The 12-hour gap on March 13 means signals cannot fire from approximately 06:00Z to ~07:00Z on March 14 (12h lookback window contaminated by gap).

---

## Forward Return Horizons

For each signal event, the forward return is computed as:

```
r_forward_h = (price_at_t+h / price_at_t) - 1
```

where `price_at_t` is the close price at the signal hour, and `price_at_t+h` is the close price `h` hours later.

| Horizon | Hours Forward | Feasibility |
|---------|--------------|-------------|
| +1h | 1 | **Full** — ample data |
| +4h | 4 | **Adequate** — reduced sample near end of dataset and around gap |
| +1d | 24 | **Underpowered** — only ~4 complete days; will report but flag as low-confidence |

---

## Cost Scenarios

Each forward return is evaluated under three round-trip cost assumptions:

| Scenario | Round-Trip Cost | Net Return |
|----------|----------------|------------|
| Low | 0.5% | `r_forward - 0.005` |
| Medium | 1.0% | `r_forward - 0.010` |
| High | 1.5% | `r_forward - 0.015` |

---

## Output Metrics

For each signal / horizon / cost scenario combination (2 signals x 3 horizons x 3 costs = 18 cells):

| Metric | Definition |
|--------|-----------|
| Sample size (N) | Number of signal events with valid forward return |
| Winsorized mean gross | Mean of gross returns, winsorized at 1st/99th percentile |
| Winsorized mean net | Mean of net returns (after cost), winsorized at 1st/99th percentile |
| Median gross | Median of gross forward returns |
| Median net | Median of net forward returns |
| % positive (net) | Fraction of events with positive net return |
| Bootstrap CI mean net | 95% bootstrap confidence interval for mean net return (10,000 resamples) |
| Bootstrap CI median net | 95% bootstrap confidence interval for median net return (10,000 resamples) |
| Top-1 contributor share | Fraction of total gross P&L contributed by the single best event |
| Top-3 contributor share | Fraction of total gross P&L contributed by the three best events |

---

## Promotion Gates

A signal/horizon/cost scenario is considered a **GO** for Stage B only if ALL of the following hold:

| Gate | Criterion |
|------|-----------|
| G1 | N >= 20 |
| G2 | Winsorized mean net > 0 |
| G3 | Median net > 0 |
| G4 | Bootstrap CI lower bound for mean net > 0 |
| G5 | Bootstrap CI lower bound for median net > 0 |
| G6 | % positive (net) > 50% |
| G7 | Top-1 contributor share < 30% |
| G8 | Top-3 contributor share < 50% |

If no scenario passes all 8 gates: **NO-GO for Stage B.**

---

## Known Limitations

1. **Short history**: 5.4 days is a very small sample for swing trading analysis. Results should be treated as preliminary / directional, not definitive.
2. **Single market regime**: The dataset covers one week in March 2026. Results may not generalize to other market conditions.
3. **Gap contamination**: The 12-hour gap on March 13 reduces the effective sample, especially for +4h and +1d horizons.
4. **+1d horizon is underpowered**: With only ~4 complete days, the +1d results will have very few observations and wide confidence intervals.
5. **No external validation**: All data comes from one scanner. Price accuracy depends on the scanner's price_usd field.

---

## Files Produced

| File | Purpose |
|------|---------|
| `reports/new_programs/largecap_swing_stageA_design.md` | This document |
| `reports/new_programs/largecap_swing_stageA_data.md` | Data extraction and universe construction report |
| `reports/new_programs/largecap_swing_stageA_results.md` | Full event-study results with all metrics |
| `reports/new_programs/largecap_swing_stageA_summary.md` | Verdict: GO / NO-GO / BLOCKED |
