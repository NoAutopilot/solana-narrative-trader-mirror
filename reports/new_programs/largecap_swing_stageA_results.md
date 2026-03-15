# Large-Cap Swing Stage A — Results

**Date:** 2026-03-15  
**Experiment ID:** 010  
**Stage:** A (Event Study)  
**Verdict:** NO-GO

---

## Summary

Across all 18 signal / horizon / cost scenarios tested, **zero passed all eight promotion gates**. Neither pullback-in-uptrend nor breakout-from-consolidation entries show a robust, cost-adjusted edge in the large-cap Solana token universe over the study period.

---

## Signal 1: Pullback in Uptrend (N=108 events)

This signal fires when a token is in a rising 12-hour trend but has pulled back below its 4-hour SMA while remaining above the 12-hour SMA, with adequate volume.

### Results at 0.5% Cost (Most Favorable)

| Horizon | N | W.Mean Net (%) | Median Net (%) | % Positive | CI Mean Lo (%) | CI Mean Hi (%) | Top-1 Share | Top-3 Share | Gates Failed |
|---------|---|----------------|----------------|------------|----------------|----------------|-------------|-------------|-------------|
| +1h | 101 | -0.48 | -0.76 | 21.8% | -1.20 | +0.34 | 18.4% | 44.5% | G2, G3, G4, G5, G6 |
| +4h | 92 | -1.48 | -0.93 | 29.3% | -2.98 | -0.39 | 17.2% | 47.2% | G2, G3, G4, G5, G6 |
| +1d | 73 | -0.96 | -1.01 | 21.9% | -1.50 | -0.44 | 11.0% | 20.9% | G2, G3, G4, G5, G6 |

### Interpretation

The pullback-in-uptrend signal produces **consistently negative returns** at all horizons, even before costs. The gross winsorized mean is near zero at +1h (+0.02%) and negative at +4h (-0.98%) and +1d (-0.46%). After even the most favorable 0.5% cost assumption, all metrics are firmly negative.

The win rate is extremely low: only 21-29% of events produce a positive net return. The 95% bootstrap confidence interval for the mean net return includes zero only at +1h; at +4h and +1d, the entire interval is negative. This is not a marginal failure — the signal is a consistent loser.

The concentration metrics (top-1 share 11-18%, top-3 share 21-47%) are acceptable, meaning the results are not driven by a few outliers. The negative performance is broad-based.

### Results at Higher Costs

At 1.0% and 1.5% cost assumptions, all metrics deteriorate further. The best case (pullback +1h at 0.5% cost) already fails five of eight gates. There is no cost scenario under which this signal passes.

---

## Signal 2: Breakout from Consolidation (N=16 events)

This signal fires when a token breaks above its 12-hour high after a period of tight consolidation (<10% range), with a 2x volume surge.

### Results at 0.5% Cost (Most Favorable)

| Horizon | N | W.Mean Net (%) | Median Net (%) | % Positive | CI Mean Lo (%) | CI Mean Hi (%) | Top-1 Share | Top-3 Share | Gates Failed |
|---------|---|----------------|----------------|------------|----------------|----------------|-------------|-------------|-------------|
| +1h | 15 | -0.25 | +0.05 | 53.3% | -0.88 | +0.30 | 18.1% | 40.3% | G1, G2, G4, G5 |
| +4h | 15 | -0.49 | -0.39 | 26.7% | -0.95 | -0.09 | 24.5% | 49.4% | G1, G2, G3, G4, G5, G6 |
| +1d | 13 | -1.39 | -1.31 | 7.7% | -2.21 | -0.62 | 27.7% | 52.5% | G1, G2, G3, G4, G5, G6, G8 |

### Interpretation

The breakout signal has a **critically small sample** (N=15-16), which alone disqualifies it from the promotion gates (G1 requires N >= 20). Even setting aside the sample size issue, the results are poor.

The one mildly encouraging data point is the +1h median net of +0.05% at 0.5% cost, with a 53.3% win rate. However, the winsorized mean is negative (-0.25%), the bootstrap CI for the mean includes zero, and the CI for the median also includes zero. This is noise, not signal.

At +4h and +1d, the breakout signal produces large negative returns. The +1d results are particularly bad: -1.39% mean net, 7.7% win rate, and the top-3 contributors account for 52.5% of the P&L — a concentrated, losing pattern.

---

## Gate Summary (All 18 Scenarios)

| Gate | Description | Scenarios Passing |
|------|-------------|-------------------|
| G1 | N >= 20 | 9 / 18 (pullback only) |
| G2 | Winsorized mean net > 0 | 0 / 18 |
| G3 | Median net > 0 | 1 / 18 (breakout +1h @ 0.5%) |
| G4 | CI mean lower > 0 | 0 / 18 |
| G5 | CI median lower > 0 | 0 / 18 |
| G6 | % positive > 50% | 1 / 18 (breakout +1h @ 0.5%) |
| G7 | Top-1 share < 30% | 17 / 18 |
| G8 | Top-3 share < 50% | 15 / 18 |

The critical failures are G2 (mean profitability) and G4/G5 (statistical significance). No scenario achieves a positive winsorized mean net return. No scenario has a bootstrap confidence interval entirely above zero. The signals do not generate positive expected value after costs.

---

## Cross-Signal Comparison

| Metric | Pullback (best case) | Breakout (best case) |
|--------|---------------------|---------------------|
| Best horizon | +1h | +1h |
| Best cost | 0.5% | 0.5% |
| W.Mean Net | -0.48% | -0.25% |
| Median Net | -0.76% | +0.05% |
| Win Rate | 21.8% | 53.3% |
| CI Mean Lo | -1.20% | -0.88% |
| Sample Size | 101 | 15 |
| Verdict | FAIL (5 gates) | FAIL (4 gates) |

The breakout signal shows slightly less negative results than the pullback signal, but with a critically small sample. Neither signal is viable.

---

## Robustness Notes

1. **Even at zero cost**, the pullback signal would fail: the gross winsorized mean is +0.02% at +1h, -0.98% at +4h, and -0.46% at +1d. The signal itself has no edge before costs.

2. **The breakout signal at +1h has a positive gross mean** (+0.25%) but the sample is too small (N=15) for any statistical confidence, and the effect disappears at longer horizons.

3. **No horizon shows promise**: the pattern is not "the signal works at one horizon but not others." All horizons are negative for both signals.

4. **Concentration is not the problem**: the top-1 and top-3 shares are mostly within acceptable ranges. The failure is in the expected value, not in outlier dependence.

---

## Conclusion

The large-cap Solana token universe, as defined by point-in-time liquidity/volume/age gates, does not show a cost-adjusted edge for either pullback-in-uptrend or breakout-from-consolidation entries at +1h, +4h, or +1d horizons during the study period (March 9-15, 2026).

**Verdict: NO-GO for Stage B.**
