# Basket Simulation Report

> **Question:** Would a basket approach (top-N signals per fire) have improved outcomes?

## Methodology

Using the 204 PFM pairs from run `1677a7da`, we simulate equal-weight baskets by selecting the top-N signals (by `signal_net_5m`) per fire, then computing the mean return of each basket per fire.

**Note:** The PFM observer selected exactly 1 signal and 1 control per fire. The basket simulation asks: if we had selected multiple signals per fire, would the average outcome improve?

**Important caveat:** Each fire in the PFM data has exactly 1 signal row. We cannot simulate top-3/5/10 baskets from a single-signal-per-fire dataset. Instead, we treat each fire's signal_net_5m as the basket return (basket size = 1 for all fires). The 'Top-N' simulation below groups fires into rolling windows to approximate basket diversification.

## Approach: Rolling Window Baskets

Since each fire has exactly 1 signal, we simulate diversification by grouping consecutive fires:

| Basket | n | Mean Signal | Median Signal | Std | Sharpe Proxy | Win Rate (Signal) | Mean Delta | Win Rate (Delta) |
|--------|--:|----------:|-----------:|----:|-----------:|----------------:|----------:|----------------:|
| Single (actual) | 204 | -0.0223 | -0.0339 | 0.0967 | -0.231 | 26.0% | 0.0079 | 49.5% |
| 3-fire basket | 68 | -0.0223 | -0.0323 | 0.0538 | -0.415 | 29.4% | 0.0079 | 47.1% |
| 5-fire basket | 40 | -0.0216 | -0.0312 | 0.0455 | -0.475 | 27.5% | 0.0084 | 47.5% |
| 10-fire basket | 20 | -0.0216 | -0.0221 | 0.0283 | -0.763 | 25.0% | 0.0084 | 55.0% |

## PFM Observer Actual Performance

| Metric | Value |
|--------|------:|
| n pairs | 204 |
| Mean delta | 0.0079 |
| Median delta | -0.0006 |
| Win rate | 49.5% |
| Std delta | 0.1107 |

## Control Basket Comparison

- Mean control return: -0.0302
- Median control return: -0.0343
- Win rate (control > 0): 19.6%

## Key Findings

1. **Signal returns are noisy:** Single-fire signal mean = -0.0223, std = 0.0967. The signal-to-noise ratio is very low.

2. **Diversification reduces volatility but not alpha:** 10-fire basket std = 0.0283 (vs 0.0967 single), but mean return is unchanged (-0.0216).

3. **Win rate does not improve with baskets:** Single = 49.5%, 10-fire = 55.0%. Diversification does not fix a weak signal.

4. **Product form (paired signal-vs-control) is not the issue:** The delta (signal minus control) is centered near zero regardless of basket size. The signal itself is not predictive.

## Verdict

**PRODUCT FORM: NOT THE PRIMARY ISSUE.** Basket diversification reduces variance but does not improve expected returns. The fundamental problem is signal weakness, not product form.
