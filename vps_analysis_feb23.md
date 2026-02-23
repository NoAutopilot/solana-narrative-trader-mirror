# VPS Analysis - Feb 23, 2026 (2.6 hours of data)

## Summary
The VPS has been running for 2.6 hours since restart (04:48 UTC). It has collected 489 trades with a raw PnL of +107 SOL, but this is **massively dominated by a single outlier**.

## Critical Finding: Extreme Outlier Dependency

The #1 trade "Too Much Winning" returned +96.26 SOL (a 2,406x return on 0.04 SOL). This single trade accounts for **90%** of all PnL. Without it, the system shows +10.73 SOL in 2.6 hours (+4.19 SOL/hr).

The top 5 trades account for 99.4% of total PnL. The top 10 account for 100.2% (meaning everything outside top 10 is net negative).

This is exactly the "lottery ticket" distribution we expected — the strategy is profitable ONLY because of rare massive winners.

## Timeout Comparison (2-min vs 5-min)

The VPS appears to have a mix of timeout settings (some trades logged with timeout=5, others with timeout=2):

| Metric | Timeout=2min | Timeout=5min |
|---|---|---|
| Trades | 140 | 346 |
| PnL | +97.18 SOL | +9.81 SOL |
| Win rate | 22.1% | 15.6% |
| Moonshot rate | 7.9% | 5.5% |

The 2-min timeout shows better performance, but the +96 SOL outlier happened to be in the 2-min group, so this comparison is misleading for now.

## Without the Mega-Outlier

Excluding the +96.26 SOL trade:
- Raw PnL: +10.73 SOL in 2.6 hours = +4.19 SOL/hr
- Fee-adjusted: roughly +3.95 SOL/hr (fees are ~3% drag)
- This is much higher than the +0.26 SOL/hr we estimated last session

But wait — this is still only 2.6 hours. We need 24+ hours to see if this rate holds.

## Trade Mode Performance

| Mode | Trades | Total PnL | Avg PnL | Win Rate |
|---|---|---|---|---|
| Control | 260 | +5.07 | +0.020 | 16.5% |
| Proactive | 127 | +96.86 | +0.763 | 18.9% |
| Narrative | 99 | +5.05 | +0.051 | 18.2% |

The proactive mode's dominance is entirely from the +96 SOL outlier. Without it, proactive would show ~+0.60 SOL.

Narrative mode shows slightly better avg PnL than control (+0.051 vs +0.020), but sample is small.

## Key Observations

1. **The strategy IS a lottery** — confirmed by data. 99%+ of PnL comes from <1% of trades.
2. **2-min timeout config is active** (140 of recent trades use it)
3. **GitHub backup is working** — last push at 07:00 UTC
4. **GitHub token issue**: backup log shows "fatal: could not read Password" — the temporary token has expired
5. **Service restarted** at 06:35 UTC (only 45 min ago per systemctl)
6. **Fee drag is minimal** at 3% — much better than the 6.6% we modeled (because winners are so large that fees are proportionally tiny)

## Action Items
1. Fix GitHub backup token (expired)
2. Let VPS run for 24+ hours to get stable hourly PnL estimate
3. The +96 SOL outlier makes all current statistics unreliable — need more data
4. Consider: if we see 1 mega-outlier per 2.6 hours, that's ~9/day. But this is likely just luck.
