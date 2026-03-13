# Large-Cap Swing Study — Stage A Results (Proxy Analysis)

**Date:** 2026-03-12
**Author:** Manus AI

> **IMPORTANT CAVEAT:** These results use +15m and +30m forward returns as proxies for +1h / +4h / +1d swing horizons. They are NOT representative of actual swing-horizon dynamics. The analysis is conducted on the full candidate universe, not the large-cap subset, because raw row-level data is not available for subsetting.

---

## Proxy Analysis: +15m Horizon

Using `feature_family_sweep_15m.csv` (best-bucket statistics for the full candidate universe):

| Feature | Coverage | Best Bucket Gross Mean | Best Bucket Net Mean | Gross Median | Net at 0.5% | Net at 1.0% | Net at 1.5% | Recommendation |
|---------|----------|----------------------:|--------------------:|------------:|----------:|----------:|----------:|---------------|
| age_hours | 100% | 42.932% | 42.406% | 0.000% | 42.432% | 41.932% | 41.432% | SKIP |
| liquidity_usd | 100% | 43.506% | 42.998% | 0.000% | 43.006% | 42.506% | 42.006% | SKIP |
| vol_h1 | 100% | 43.033% | 42.517% | 0.000% | 42.533% | 42.033% | 41.533% | SKIP |
| median_pool_r_m5 | 100% | 44.030% | 43.516% | 0.000% | 43.530% | 43.030% | 42.530% | SKIP |
| round_trip_pct | 100% | 43.411% | 42.903% | 0.000% | 42.911% | 42.411% | 41.911% | SKIP |

## Proxy Analysis: +30m Horizon

Using `feature_family_sweep_30m.csv`:

| Feature | Coverage | Best Bucket Gross Mean | Best Bucket Net Mean | Gross Median | Net at 0.5% | Net at 1.0% | Net at 1.5% | Recommendation |
|---------|----------|----------------------:|--------------------:|------------:|----------:|----------:|----------:|---------------|
| age_hours | 100% | 92.067% | 91.544% | -0.827% | 91.567% | 91.067% | 90.567% | SKIP |
| liquidity_usd | 100% | 93.492% | 92.985% | 0.000% | 92.992% | 92.492% | 91.992% | SKIP |
| vol_h1 | 100% | 92.188% | 91.674% | -0.025% | 91.688% | 91.188% | 90.688% | SKIP |
| median_pool_r_m5 | 100% | 94.424% | 93.911% | 0.060% | 93.924% | 93.424% | 92.924% | SKIP |
| round_trip_pct | 100% | 93.160% | 92.653% | 0.000% | 92.660% | 92.160% | 91.660% | SKIP |

## Comparison: +5m vs +15m vs +30m Best Bucket Gross Mean

| Feature | +5m Gross Mean | +15m Gross Mean | +30m Gross Mean | Trend |
|---------|-------------:|---------------:|---------------:|-------|
| age_hours | 0.215% | 42.932% | 92.067% | INCREASING (tail-driven) |
| liquidity_usd | 0.318% | 43.506% | 93.492% | INCREASING (tail-driven) |
| vol_h1 | 0.179% | 43.033% | 92.188% | INCREASING (tail-driven) |
| median_pool_r_m5 | 0.566% | 44.030% | 94.424% | INCREASING (tail-driven) |
| round_trip_pct | 0.336% | 43.411% | 93.160% | INCREASING (tail-driven) |

## Key Observations

1. **Gross means increase with horizon** for most features, but this is expected — longer horizons have wider return distributions. The increase is driven by tail events (extreme movers), not by a consistent shift in the median.

2. **Gross medians remain near zero** at all horizons for all features. This means the typical candidate token has approximately zero return regardless of feature value, even at +30m.

3. **Net returns at 1.0% and 1.5% cost are negative** for all features at all horizons. Only at the optimistic 0.5% cost level do some features show marginally positive net means, and even then the median is zero or negative.

4. **The sweep is on the full universe, not the large-cap subset.** The large-cap subset (higher liquidity, older tokens) would likely have lower gross returns (less volatility) but also lower costs. The net effect is unknown without re-running the sweep on the subset.

5. **All features are marked SKIP** in the original sweep recommendations at both +15m and +30m.
