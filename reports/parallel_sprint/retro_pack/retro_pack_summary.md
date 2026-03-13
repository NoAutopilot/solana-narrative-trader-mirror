# Retrospective Decision Pack — Summary

> **Question:** Was the failed family doomed because of weak signal, late entry timing, wrong horizon, or wrong product form?

## Evidence Matrix

| Hypothesis | Evidence | Verdict |
|-----------|---------|--------|
| **Late Entry** | Median entry jitter = 7s; correlation with delta = 0.0037; no bucket effect | **REJECTED** — timing is not a factor |
| **Weak Signal** | Best-bucket gross median = 0.000% at +5m for ALL candidates; PFM median delta = -0.06%; CI crosses zero; sign test p=0.94 | **CONFIRMED** — primary cause |
| **Wrong Horizon** | +15m and +30m sweeps show same pattern (median = 0, mean driven by tails); no evidence that longer horizons fix the signal | **REJECTED** — longer horizons do not help |
| **Wrong Product Form** | Basket simulation shows diversification reduces variance but not alpha; paired design is not the issue | **REJECTED** — product form is not the cause |

## Classification

### **SIGNAL WEAK**

The failed momentum/direction family (r_m5, buy_sell_ratio_m5, vol_accel_m5_vs_h1, txn_accel_m5_vs_h1, liq_change_pct) does not contain sufficient predictive signal to overcome transaction costs in the Solana DEX micro-cap environment.

**Supporting evidence:**

1. **Sweep results:** Every candidate feature has a best-bucket gross median of 0.000% at +5m. The positive mean returns are entirely driven by tail events (outlier tokens with extreme moves). The median row — the typical outcome — is flat or negative after costs.

2. **PFM observer:** n=204 pairs, mean delta = +0.79% (positive but noisy), median delta = -0.06% (negative). The 95% CI = [-0.74%, +2.32%] crosses zero. The sign test p-value = 0.94 (no evidence of directional skill).

3. **Track B robustness:** r_m5 and vol_accel_m5_vs_h1 passed the mean-net-proxy gate but failed the median gate. The effect is mean-driven by tail events, not robust.

4. **Entry timing:** Not a factor. Median entry jitter is moderate and uncorrelated with outcomes.

5. **Horizon:** Not a factor. The +15m and +30m sweeps show the same pattern (zero median, positive mean from tails).

## Implications

- The momentum/direction feature family should be **permanently retired** from the candidate list.
- Any new feature family must demonstrate a **positive median** (not just positive mean) in the retrospective sweep.
- The pre-registration gate requiring median net-proxy > 0 was correct and should be retained.
- The next step should focus on **genuinely novel feature families** (order flow urgency, route quality, market-state gating) that are conceptually distinct from the tested momentum/direction features.
