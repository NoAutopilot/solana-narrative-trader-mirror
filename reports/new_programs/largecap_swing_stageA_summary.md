# Large-Cap Swing Stage A — Summary

**Date:** 2026-03-15  
**Experiment ID:** 010  
**Program:** Large-Cap Swing  
**Verdict:** NO-GO

---

## One-Paragraph Summary

A point-in-time event study tested whether established, larger-cap Solana tokens (25 tokens meeting dynamic liquidity, volume, and age gates) show a cost-adjusted edge under pullback-in-uptrend or breakout-from-consolidation entries at +1h, +4h, and +1d horizons. Using 5.4 days of 1-minute scanner data (271K snapshots, 1,634 hourly bars, 124 signal events), the study found **no viable signal at any horizon or cost scenario**. Zero of 18 tested combinations passed all eight promotion gates. The pullback signal (N=108) produced negative returns even before costs. The breakout signal (N=16) was too small to evaluate and showed no edge at longer horizons. The program is closed at Stage A with a NO-GO recommendation.

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Universe tokens | 25 (point-in-time, dynamic) |
| Data window | 5.4 days (2026-03-09 to 2026-03-15) |
| Hourly bars | 1,634 |
| Pullback events | 108 |
| Breakout events | 16 |
| Scenarios tested | 18 (2 signals x 3 horizons x 3 costs) |
| Scenarios passing all gates | **0** |
| Best-case net return | -0.25% (breakout +1h @ 0.5% cost) |
| Best-case win rate | 53.3% (breakout +1h @ 0.5% cost, N=15) |

---

## Verdict: NO-GO

Neither signal produces a positive expected value after costs. The pullback signal is a consistent loser across all horizons. The breakout signal has an insufficient sample and no edge at +4h or +1d. There is no basis to proceed to Stage B.

---

## Limitations and Caveats

The study covers only 5.4 days in a single market regime. It is possible that these signals work in other market conditions (strong bull trend, higher volatility periods) or with a different universe definition. However, the results are not marginal — they are clearly negative. A longer dataset would increase confidence but is unlikely to reverse the direction of the findings.

The +1d horizon is particularly underpowered (N=73 for pullback, N=13 for breakout). A study with 30+ days of data would be needed to make a definitive statement about +1d performance.

---

## What Was Learned

1. **Large-cap Solana tokens are mean-reverting on short horizons, but not in a tradeable way.** The pullback signal captures tokens that dip and then... continue to dip. The "uptrend" as measured by a 12-hour SMA does not reliably predict continuation.

2. **Breakouts from consolidation are rare in this universe.** Only 16 events in 5.4 days across 25 tokens. The consolidation-then-breakout pattern may be more characteristic of smaller, less liquid tokens.

3. **Costs dominate.** Even at the most favorable 0.5% round-trip assumption, no signal is profitable. The gross returns are near zero or negative, meaning the signals have no edge even in a frictionless world.

4. **The point-in-time universe construction worked correctly.** Dynamic membership, no survivorship bias, no hardcoded winners. This methodology can be reused for future studies.

---

## Files Produced

| File | Path |
|------|------|
| Design document | `reports/new_programs/largecap_swing_stageA_design.md` |
| Data report | `reports/new_programs/largecap_swing_stageA_data.md` |
| Full results | `reports/new_programs/largecap_swing_stageA_results.md` |
| This summary | `reports/new_programs/largecap_swing_stageA_summary.md` |
| Results CSV | `reports/new_programs/largecap_swing_stageA_results.csv` |
| Events CSV | `reports/new_programs/largecap_swing_stageA_events.csv` |
| Universe stats | `reports/new_programs/largecap_swing_stageA_universe_stats.json` |
| Verdict file | `reports/new_programs/largecap_swing_stageA_verdict.txt` |

---

## Disposition

This program line (Large-Cap Swing) is **closed at Stage A**. No Stage B is recommended. The experiment should be registered in the no-go registry and experiment index.

Remaining option from `post_v2_options.md`:
- **Option C**: Brand-new program around wallet/deployer/early-buyer signals (not yet evaluated)
- **Option A**: Stop all research programs
