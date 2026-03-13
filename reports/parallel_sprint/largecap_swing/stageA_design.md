# Large-Cap Swing Study — Stage A Design

**Date:** 2026-03-12
**Author:** Manus AI
**Status:** DESIGN ONLY — no implementation until data gaps are filled

---

## Objective

Determine whether a slower-horizon (+1h / +4h / +1d), higher-liquidity subset of the Solana DEX candidate universe exhibits exploitable return patterns that are distinct from the failed momentum/direction family tested at +5m/+15m/+30m.

## Universe Definition

In the Solana DEX context, "large-cap" is relative. The candidate universe from `feature_tape_v1` consists of micro-cap tokens with median liquidity of approximately $5,000-$50,000 and median age of a few hours. A "large-cap" subset within this universe would be defined by the following point-in-time filters:

| Filter | Threshold | Rationale |
|--------|-----------|----------|
| `liquidity_usd` | > median of fire-level universe | Top-half liquidity at fire time |
| `age_hours` | > 24h | Survived at least one full day; filters out pump-and-dump launches |
| `vol_h24` | > 0 | Must have non-zero 24h volume (confirms active trading) |
| `eligible` | = 1 | Must pass scanner eligibility gates |

**Point-in-time construction:** All filters are applied using data available at fire time only. No future information (e.g., whether the token survived to the next day) is used. The universe is reconstructed independently at each fire, which prevents survivorship bias.

**Estimated universe size:** Based on feature_tape_v1 data (~40 candidates per fire), the large-cap subset would contain approximately 10-15 candidates per fire after applying the age and liquidity filters. Over 96 fires, this produces approximately 960-1,440 rows — marginal but sufficient for a Stage A feasibility study.

## Feature Candidates for Swing

The following features are candidates for the swing study. They are deliberately chosen to be **distinct from the failed momentum/direction family** (r_m5, buy_sell_ratio_m5, vol_accel_m5_vs_h1, etc.):

| Feature | Hypothesis | Distinction from Failed Family |
|---------|-----------|-------------------------------|
| `age_hours` | Older tokens have more stable price dynamics; mean-reversion is more likely | Not a momentum feature; captures maturity |
| `liquidity_usd` | Higher-liquidity tokens have lower transaction costs and more efficient pricing | Not a direction feature; captures market structure |
| `vol_h24` | 24h volume captures sustained interest vs flash-in-the-pan activity | Longer lookback than any v1 feature |
| `pool_type` | Different AMM designs (Raydium CPMM vs Orca CLMM vs Meteora DLMM) may have different return dynamics | Structural feature, not directional |
| `round_trip_pct` | Lower-cost tokens may have better net returns at longer horizons | Cost feature, not signal feature |

## Horizon Labels

The target horizons for the swing study are:

| Horizon | Label | Status |
|---------|-------|--------|
| +1h | `r_forward_1h` | **NOT AVAILABLE** — feature_tape_v1 only has +5m/+15m/+30m |
| +4h | `r_forward_4h` | **NOT AVAILABLE** |
| +1d | `r_forward_1d` | **NOT AVAILABLE** |
| +15m (proxy) | `r_forward_15m` | Available from feature_tape_v1 sweep |
| +30m (proxy) | `r_forward_30m` | Available from feature_tape_v1 sweep |

> **Critical data gap:** The +1h, +4h, and +1d horizon labels do not exist in the current dataset. The +15m and +30m sweep results are used as proxies in the Stage A results below, but they are **not representative of swing-horizon dynamics**. A proper Stage A study requires new data collection with longer-horizon labels.

## Cost Structure

| Cost Scenario | Round-Trip Cost | Rationale |
|--------------|----------------|----------|
| Optimistic | 0.5% | CPAMM-based proxy (current `round_trip_pct` median) |
| Base | 1.0% | Includes slippage, priority fees, failed txn costs |
| Conservative | 1.5% | Includes MEV, worst-case slippage, congestion fees |

At longer horizons, the cost is amortized over a larger expected move, which is the fundamental hypothesis of the swing approach: even if the per-trade cost is the same, the gross return at +4h or +1d may be large enough to absorb it.

## What Is Missing for a Proper Stage A

1. **+1h / +4h / +1d forward return labels.** These require either (a) extending the `universe_snapshot` price history to 24+ hours after each fire, or (b) using an external price API (Birdeye, DexScreener) to backfill longer-horizon prices.

2. **Large-cap universe filter applied to raw data.** The current sweep CSVs are computed on the full candidate universe, not the large-cap subset. A proper Stage A requires re-running the sweep on the filtered subset.

3. **Holding-period risk metrics.** At +4h and +1d horizons, max drawdown during the holding period matters. The current data only has point-in-time forward returns, not intra-period price paths.

4. **Overnight / weekend effects.** Solana DEX markets trade 24/7, but activity patterns differ by time of day. A 24-hour collection window may not capture the full range of market regimes.
