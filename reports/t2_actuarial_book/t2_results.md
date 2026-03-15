# T2 Actuarial / Casino-Math Book Test — Results

**Program:** T2 Actuarial Book  
**Design version:** v3 (pre-registered 2026-03-15)  
**Run date:** 2026-03-15  
**Data source:** Yahoo Finance via Manus API  
**Test period:** 2025-03-01 to 2026-03-01  

---

## OVERALL VERDICT: FAIL

**Structures passing: 0 / 4**

---

## 1. Universe and Data

| Metric | Value |
|---|---|
| Tokens with 365d history | 44 |
| Unique tokens passing filter at least once | 24 |
| Total cohort entries (token × month) | 229 |
| Reconstitution dates | 12 (monthly, Mar 2025 – Feb 2026) |
| Mean tokens per cohort | 19 |
| Min tokens per cohort | 12 (Feb 2026) |
| Max tokens per cohort | 23 (May 2025) |

The universe is thin. Yahoo Finance covers only the most liquid and well-known Solana-ecosystem tokens — the top ~44 by global exchange listing. The full Solana long-tail (pump.fun tokens, sub-$5M tokens) is not accessible via this data source. This is a limitation acknowledged in the data section, but it is also a realistic constraint: the filter requires $200K 30-day ADV, which the long tail does not meet.

---

## 2. Filter Application

**Pre-registered filter (v3 design, applied point-in-time):**

- Minimum age: ≥ 90 days
- Minimum 30d ADV: ≥ $200,000 USD
- Minimum 90d ADV: ≥ $50,000 USD
- Volume consistency: ≥ 60% of days with volume
- No momentum, no price-change features

The filter excluded stablecoins, LSTs (treated as yield instruments, not speculative), and SOL itself. Tokens like MSOL, JITOSOL, BSOL, STSOL passed the filter and were included — they are liquid, have real volume, and are not stablecoins. This is correct per design.

---

## 3. Exit Structure Results

### 3.1 Summary Table (conservative cost = 0.50% round-trip)

| Structure | TP | SL | Mean | Median | % Positive | Sharpe | Verdict |
|---|---|---|---|---|---|---|---|
| E1 | +15% | -8% | +0.50% | -9.00% | 41.9% | 0.74 | **FAIL** |
| E2 | +20% | -10% | -0.47% | -11.00% | 36.2% | -0.57 | **FAIL** |
| E3 | +30% | -15% | -5.18% | -16.00% | 24.0% | -4.73 | **FAIL** |
| E4 | +20% | -7% | +0.71% | -8.00% | 34.1% | 0.96 | **FAIL** |
| B1 (60d hold) | — | — | -12.03% | -16.42% | 27.5% | -5.64 | benchmark |
| B2 (20d hold) | — | — | -0.05% | -1.32% | 42.8% | -0.03 | benchmark |

### 3.2 Multi-Cost Sensitivity (E1 and E4 — the two structures with positive mean)

| Structure | Cost Level | Mean | Median | % Positive | Sharpe |
|---|---|---|---|---|---|
| E1 | Optimistic (0.10%) | +0.90% | -8.60% | 41.9% | 1.34 |
| E1 | Base (0.30%) | +0.70% | -8.80% | 41.9% | 1.04 |
| E1 | **Conservative (0.50%)** | **+0.50%** | **-9.00%** | **41.9%** | **0.74** |
| E1 | Stress (1.00%) | -0.00% | -9.50% | 41.9% | -0.00 |
| E4 | Optimistic (0.10%) | +1.11% | -7.60% | 34.1% | 1.50 |
| E4 | Base (0.30%) | +0.91% | -7.80% | 34.1% | 1.23 |
| E4 | **Conservative (0.50%)** | **+0.71%** | **-8.00%** | **34.1%** | **0.96** |
| E4 | Stress (1.00%) | +0.21% | -8.50% | 34.1% | 0.29 |

E4 survives to stress cost on mean alone. But the median is -8% at every cost level. Mean is positive only because of outlier positions.

### 3.3 Exit Type Breakdown

| Structure | Exit Type | Count | Mean Gross | Mean Net (conservative) |
|---|---|---|---|---|
| E1 | TP (hit +15%) | 91 (39.7%) | +13.5% | +13.0% |
| E1 | SL (hit -8%) | 119 (52.0%) | -8.0% | -9.0% |
| E1 | MAXHOLD (60d) | 18 (7.9%) | +1.2% | +0.7% |
| E1 | SL_FIRST | 1 | -8.0% | -9.0% |
| E4 | TP (hit +20%) | 72 (31.4%) | +17.9% | +17.4% |
| E4 | SL (hit -7%) | 138 (60.3%) | -7.0% | -8.0% |
| E4 | MAXHOLD (60d) | 18 (7.9%) | +1.8% | +1.3% |

**Key observation:** E1 has 52% SL rate and 40% TP rate. E4 has 60% SL rate and 31% TP rate. The mean is positive in E1/E4 only because the TP winners (when they hit) are large enough to offset the majority of SL losers. This is a lottery-ticket distribution, not an actuarial book.

---

## 4. Concentration Analysis

### 4.1 E1 Concentration

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Top-1 position share | 12.7% | — | flag |
| Top-3 position share | 38.1% | — | flag |
| Top-20 position share | 100% | < 80% | **KILL** |
| Top decile share | 280% | < 70% | **KILL** |
| Top-3 token share | 124% | < 15% | **KILL** |
| Top-10% token share | 84% | < 60% | **KILL** |
| Max single month share | 212% (Jul 2025) | < 35% | **KILL** |

The concentration numbers for E1 exceed 100% because the denominator (total PnL) is small and positive while a handful of positions are very large winners. The top-decile of positions accounts for 280% of total PnL — meaning the bottom 90% of positions collectively lost money, and the top 10% more than offset them. This is not a book. This is a lottery.

### 4.2 Top Tokens by PnL (E1)

| Token | Net PnL (sum across cohorts) |
|---|---|
| WIF-USD | +0.50 |
| MSOL-USD | +0.46 |
| STSOL-USD | +0.45 |
| BSOL-USD | +0.42 |
| FARTCOIN-USD | +0.41 |
| JITOSOL-USD | +0.41 |
| CHILLGUY-USD | +0.26 |
| ORCA-USD | +0.17 |

Note: MSOL, STSOL, BSOL, JITOSOL are all liquid staking tokens — they track SOL with low volatility. Their inclusion inflates the TP rate for the 15% target because they are slow-moving and simply held to MAXHOLD. WIF drove the largest single winner. FARTCOIN drove the largest single winner in E4.

---

## 5. Subperiod Stability

| Structure | SP1 (Mar–Jul 2025) | SP2 (Jul–Nov 2025) | SP3 (Nov 2025–Mar 2026) | Positive subperiods |
|---|---|---|---|---|
| E1 | mean=-7.28%, median=-11% | mean=+8.13%, median=+17.6% | mean=-4.84%, median=-11% | **1/3** |
| E2 | mean=-7.28%, median=-11% | mean=+8.13%, median=+17.6% | mean=-4.84%, median=-11% | **1/3** |
| E3 | mean=-12.0%, median=-16% | mean=+2.6%, median=-7.4% | mean=-9.5%, median=-16% | **0/3** |
| E4 | mean=-5.9%, median=-8% | mean=+8.7%, median=+17.4% | mean=-3.0%, median=-8% | **1/3** |
| B2 | mean=+5.2%, median=+2.1% | mean=+7.1%, median=+4.4% | mean=-14.3%, median=-14.5% | **2/3** |

**All four structures fail the subperiod stability requirement (≥ 2/3 positive).**

The pattern is stark: SP2 (Jul–Nov 2025) was positive for all structures. SP1 and SP3 were negative for all structures. The book's positive mean in E1/E4 is entirely explained by SP2. This is a regime artifact, not a stable distributional property.

**Notably, B2 (passive 20-day hold) also passes 2/3 subperiods** — meaning even the benchmark was positive in 2 of 3 periods. The book does not add value over passive holding in the one positive period (SP2), and is worse in the two negative periods.

---

## 6. Concurrency Analysis

| Structure | Mean concurrent | Max concurrent | P75 concurrent |
|---|---|---|---|
| E1 | 5.1 | 25 | 8.0 |
| E2 | 6.8 | 25 | 10.0 |
| E3 | 11.0 | 25 | 16.0 |
| E4 | 5.9 | 25 | 9.0 |

Concurrency is operationally manageable (mean 5–11 simultaneous positions). This is not a kill condition. Capital requirement is modest — at $1,000 per position, mean capital deployed is $5,000–$11,000. This is one of the few aspects of the design that would be practical.

---

## 7. Benchmark Comparison

| Structure | Beats B1 mean? | Beats B2 mean? | Beats B1 median? | Beats B2 median? |
|---|---|---|---|---|
| E1 | Yes (+12.5pp) | Yes (+0.55pp) | No (-7.6pp) | No (-7.9pp) |
| E2 | Yes (+11.6pp) | No (-0.42pp) | No (-9.7pp) | No (-9.7pp) |
| E3 | Yes (+6.9pp) | No (-5.2pp) | No (-14.6pp) | No (-14.7pp) |
| E4 | Yes (+12.7pp) | Yes (+0.76pp) | No (-6.7pp) | No (-6.7pp) |

E1 and E4 beat both benchmarks on mean. But they fail both benchmarks on median. The median of the book is -8% to -9%; the median of B2 (passive 20-day hold) is -1.3%. The book's median outcome is substantially worse than passive holding.

**The mean advantage over B2 is tiny (< 1pp) and disappears entirely at stress cost (1.00%).**

---

## 8. Fail Reason Summary

Every structure fails on multiple independent criteria:

| Fail Criterion | E1 | E2 | E3 | E4 |
|---|---|---|---|---|
| Mean ≤ 0 at conservative | — | FAIL | FAIL | — |
| Mean ≤ 0 at base | — | FAIL | FAIL | — |
| Median ≤ 0 | FAIL | FAIL | FAIL | FAIL |
| Outlier-driven (decile + top3 token) | FAIL | — | — | FAIL |
| Top-20 position share > 80% | FAIL | — | — | FAIL |
| Max single month > 35% | FAIL | — | — | FAIL |
| Sparse (top-10% token > 60%) | FAIL | — | — | FAIL |
| Subperiod stability < 2/3 | FAIL | FAIL | FAIL | FAIL |
| Fails to beat B2 mean | — | FAIL | FAIL | — |
| Median worse than B2 median | FAIL | FAIL | FAIL | FAIL |

---

## 9. Adversarial Interpretation

### What the positive mean in E1/E4 actually is

E1 and E4 show a positive mean at conservative cost. This is real in the data. The mechanism is: a minority of tokens (WIF, FARTCOIN, ZEREBRO, RENDER) had large upward moves in SP2 (Jul–Nov 2025) that hit the TP target. The majority of positions hit the SL.

This is not an actuarial book. An actuarial book requires:
- Positive median (most positions make money)
- Stability across regimes (not just one good quarter)
- PnL distributed across many positions (not concentrated in 3–5 tokens)

None of these conditions are met.

### What SP2 actually was

SP2 (Jul–Nov 2025) coincides with a Solana ecosystem recovery period. The positive mean in SP2 reflects beta exposure to a recovering market, not any structural distributional edge. The book in SP2 is essentially: "hold Solana tokens during a market recovery." B2 (passive hold) also shows +7.1% mean in SP2. The book's +8.1% in SP2 is not meaningfully better than passive.

### The LST contamination problem

MSOL, STSOL, BSOL, JITOSOL are liquid staking tokens. They pass the volume filter (they are genuinely liquid) but they behave differently from speculative tokens: they track SOL closely with low volatility and rarely hit the TP. Their inclusion in the universe inflates the MAXHOLD count and slightly improves the average MAXHOLD return. This is not a flaw in the design — they legitimately pass the filter — but it means the universe is not a pure speculative token universe.

### The median problem is structural

The median is negative at every cost level for every structure. This means: **if you run this book, you will lose money on more than half your positions.** The positive mean requires the winners to be large enough to offset the losers. In a real trading environment, this requires perfect execution on winners (hitting TP before reversal) and accepting the full SL on losers. Slippage on TP exits is not modeled here — in practice, TP exits on illiquid tokens often execute below the target price.

---

## 10. Data Limitations and Caveats

1. **Universe coverage:** Yahoo Finance covers ~44 Solana tokens. The true Solana liquid universe (tokens with $200K+ 30d ADV) likely includes 80–150 tokens. The missing tokens are primarily mid-cap Solana-native tokens not listed on major CEXes. This may bias results in either direction.

2. **Volume data quality:** Yahoo Finance volume for crypto tokens aggregates across exchanges but may miss DEX volume. The 30d ADV filter may be slightly understated.

3. **Point-in-time filter:** The filter is applied using data available at the reconstitution date. This is correct per design. However, Yahoo Finance does not provide historical market cap data, so the market cap filter from v2 was replaced with a volume proxy. This is documented in v3 design.

4. **Entry price:** Entry is at the next-day open after the reconstitution date. Yahoo Finance open prices are reliable for liquid tokens but may have gaps for less-liquid tokens.

5. **Exit simulation:** SL/TP is simulated using daily high/low. Intraday order of high vs. low is unknown; when both SL and TP are hit on the same day, SL is assumed first (conservative). This is correct per design.

---

## 11. Final Verdict

```
T2 ACTUARIAL BOOK TEST
OVERALL VERDICT: FAIL
Structures passing: 0 / 4

PRIMARY FAILURE MODE: Regime artifact + outlier concentration
  - Positive mean exists only in SP2 (Jul–Nov 2025)
  - Positive mean is driven by 3–5 tokens per structure
  - Median is negative at every cost level for every structure
  - Subperiod stability: 1/3 positive for all structures

SECONDARY FAILURE MODE: Benchmark failure
  - Mean advantage over B2 is < 1pp at conservative cost
  - Median is 7–9pp worse than B2 median
  - The book does not add value over passive holding

WHAT THIS MEANS:
  The hypothesis — that a quality-filtered equal-weight rolling book
  of Solana tokens with TP/SL exits has positive actuarial EV —
  is NOT supported by the data.

  The distributional shape is: majority of positions lose a fixed
  amount (SL), minority of positions gain a variable amount (TP).
  The mean is positive only when the minority gains are large enough
  to offset the majority losses. This requires favorable market
  conditions (SP2) and concentrated winners (3–5 tokens).

  This is not a business. This is beta exposure with extra steps.

NEXT STEP:
  Per the pre-registered protocol, a FAIL verdict means:
  Do not proceed to Stage B.
  Do not refine the filter.
  Do not adjust exit parameters.
  Record the result and move to the next candidate test.
```

---

## 12. Output Files

| File | Description |
|---|---|
| `run_output/run_log_yf.txt` | Full execution log |
| `run_output/verdict.txt` | Machine-readable verdict |
| `run_output/verdict_by_structure_yf.csv` | Per-structure verdict with all metrics |
| `run_output/metrics_full_yf.csv` | Full metrics table across all structures and cost levels |
| `run_output/subperiod_breakdown_yf.csv` | Subperiod metrics for all structures |
| `run_output/concentration_table_yf.csv` | Concentration metrics for all structures |
| `run_output/cohort_table_yf.csv` | All cohort entries (token × month × entry price) |
| `run_output/trades_E{1-4}_yf.csv` | Trade-level results for each exit structure |
| `run_output/trades_B1_yf.csv` | Benchmark B1 trade-level results |
| `run_output/trades_B2_yf.csv` | Benchmark B2 trade-level results |
| `run_output/historical_cache_yf.json` | Cached historical price/volume data |
| `run_output/token_pnl_top10_E{1-4}_yf.csv` | Top-10 tokens by PnL for each structure |
| `run_output/exit_breakdown_E{1-4}_yf.csv` | Exit type breakdown for each structure |
