# T2 — Actuarial / Casino-Math Book Test: Updated Design (v2)

**Program:** t2_actuarial_book
**Date:** 2026-03-15
**Version:** 2 (guardrails added before execution)
**Author:** Manus AI
**Status:** PRE-REGISTERED — READY FOR EXECUTION

---

## What This Test Is

T2 asks a single distributional question: for tokens passing a simple, non-predictive quality filter, does the empirical payoff distribution of mechanical entries and fixed asymmetric exits produce positive expected value after realistic transaction costs? No prediction is required. No signal is being tested. The question is whether the aggregate distribution of outcomes across a large, non-selected token universe has the right shape to support a mechanical book with positive EV — the same logic a casino uses when designing a game.

This document is the pre-registered design. Every decision below is locked before any data is examined. Nothing may be changed after data collection begins except to add more conservative assumptions. Any deviation from this design must be documented explicitly and treated as a protocol violation.

---

## Guardrail 1 — Pre-Registered Quality Filter (Non-Predictive Only)

The quality filter defines the eligible token universe. It is applied once, before any analysis, and its parameters are fixed here. The filter contains only structural eligibility criteria. No momentum-like, trend-following, or predictive features are permitted.

**Permitted filter dimensions:**

| Dimension | Threshold | Rationale |
|-----------|-----------|-----------|
| Minimum age | ≥ 90 calendar days since first on-chain trade | Removes tokens too new to have a meaningful price history |
| Minimum market cap | ≥ $5M USD at filter date | Removes micro-cap tokens where price is dominated by single actors |
| Maximum market cap | ≤ $1B USD at filter date | Removes tokens large enough that the book's sizing would be negligible; also keeps the universe in the mid-cap range where distributional effects are more likely to be detectable |
| Minimum 30-day average daily volume | ≥ $100K USD | Removes illiquid tokens where exit assumptions are unrealistic |
| Minimum daily volume on ≥ 60% of trading days | Enforces consistent tradability, not just occasional spikes | Removes tokens with sporadic liquidity |
| Real tradability / non-honeypot screen | Token must have verifiable two-way trading history (buys and sells from multiple wallets) | Removes tokens where sells are blocked or heavily taxed |

**Explicitly prohibited filter features:**

The following are not permitted as filter criteria because they introduce predictive or momentum-like selection bias:

- Recent price performance (positive or negative)
- Recent volume trend (increasing or decreasing)
- Relative strength or momentum indicators
- Any feature derived from price change over any lookback window
- Social sentiment or narrative scoring
- Analyst ratings or external quality scores

**Filter application protocol:** The filter is applied at a single snapshot date (the start of the test period). Tokens that pass the filter at that date are included for the full test period, regardless of subsequent changes to their metrics. This prevents survivorship bias from re-filtering mid-period.

**Minimum universe size:** The filter must retain at least 100 tokens. If fewer than 100 tokens pass, the market cap range or volume threshold is widened by the minimum increment necessary to reach 100, and this adjustment is documented as a protocol note. If fewer than 50 tokens pass even after widening, the test is killed immediately (universe too thin for a distributional result).

---

## Guardrail 2 — Capped Exit Structures (3–4 Maximum, No Grid Search)

Exactly four exit structures are pre-registered. No additional structures may be tested. No grid search over exit parameters is permitted. The four structures are chosen to span a range of risk/reward profiles without optimizing for any particular historical period.

**Pre-registered exit structures:**

| Structure ID | Take-Profit | Stop-Loss | Payoff Ratio (gross) | Rationale |
|-------------|-------------|-----------|---------------------|-----------|
| E1 | +15% | −8% | 1.88 | Conservative asymmetry; realistic for mid-cap tokens |
| E2 | +20% | −10% | 2.00 | Moderate asymmetry; round numbers, no optimization |
| E3 | +30% | −15% | 2.00 | Wider targets; tests whether fat upside tails exist |
| E4 | +20% | −7% | 2.86 | Tighter stop; tests whether early exit improves distribution |

**Exit mechanics:** All exits are measured from the entry price. Entry is defined as the next-day open after the filter date (to avoid look-ahead bias on the entry day). Exits are triggered at the close of the first day the price touches the take-profit or stop-loss level intraday. If both levels are touched in the same day (gap scenario), the stop-loss is assumed to have triggered first (conservative assumption).

**Maximum holding period:** 60 calendar days. If neither exit level is triggered within 60 days, the position is closed at the 60-day close price. This prevents positions from being held indefinitely and ensures the capital concurrency analysis (Guardrail 8) is bounded.

**No partial exits, no trailing stops, no time-based scaling.** The exit structure is fixed at entry.

---

## Guardrail 3 — Equal Sizing Only

All positions are sized equally. No dynamic sizing, no confidence weighting, no volatility scaling, no Kelly criterion, no position sizing based on any feature of the token.

**Sizing rule:** Each position receives exactly 1 unit of notional capital. All return calculations are expressed as percentage returns per position, then aggregated with equal weight. The book-level return is the simple arithmetic mean of all position returns in a given period.

**Rationale:** Dynamic sizing introduces a second optimization layer on top of the exit structure. If the test uses dynamic sizing, a positive result could be attributable to the sizing model rather than the distributional shape of the underlying token universe. Equal sizing isolates the distributional question cleanly.

**Capital normalization:** For capital concurrency analysis (Guardrail 8), positions are assumed to require 1 unit of capital each. The concurrent capital requirement at any point in time is the number of open positions multiplied by 1 unit.

---

## Guardrail 4 — Execution Realism

Transaction costs and slippage are applied explicitly. The test is run at four cost levels. A result is only considered robust if it survives at the conservative cost assumption.

**Cost assumption levels:**

| Level | Round-Trip Cost | Description |
|-------|----------------|-------------|
| Optimistic | 0.10% | Best-case: large-cap token, tight spread, no market impact |
| Base | 0.30% | Realistic: mid-cap token, normal spread, small size |
| Conservative | 0.50% | Realistic: mid-cap token, wider spread, moderate size |
| Stress | 1.00% | Worst-case: small-cap token, wide spread, or thin book |

**Pass requirement on cost sensitivity:** A result is considered robust only if the mean return per trade remains positive at the Conservative (0.50%) cost level. A result that is positive only at Optimistic or Base is flagged as cost-sensitive and does not constitute a pass.

**Slippage sensitivity:** In addition to the fixed cost levels above, a slippage sensitivity analysis is run for each exit structure. Slippage is modeled as an additional cost applied only to stop-loss exits (the scenario where the position is being closed under adverse conditions). The slippage assumption is 0.5% additional cost on stop-loss exits only. This is applied on top of the base round-trip cost.

**Exit liquidity sanity checks:** For each token in the universe, the assumed exit size is compared to the token's average daily volume. If the assumed exit size exceeds 1% of average daily volume, the position is flagged as liquidity-constrained. The fraction of positions that are liquidity-constrained is reported. If more than 20% of positions are liquidity-constrained at the base position size, the position size is reduced and the analysis is re-run at the smaller size.

---

## Guardrail 5 — Concentration Reporting

A positive mean return is not sufficient if it is driven by a small number of positions, tokens, or time periods. The following concentration metrics are computed and reported for every exit structure.

**Position-level concentration:**

- **Top-1 contributor share:** The fraction of total book PnL attributable to the single best-performing position. If this exceeds 10%, the result is flagged as top-heavy.
- **Top-3 contributor share:** The fraction of total book PnL attributable to the three best-performing positions. If this exceeds 25%, the result is flagged as top-heavy.
- **Top-decile share:** The fraction of total book PnL attributable to the top 10% of positions by individual return. A healthy distributional result should have top-decile share below 50%. If top-decile share exceeds 70%, the result is driven by outliers, not by the distribution, and does not constitute a pass.

**Token-level concentration:**

- **Share by token:** If any single token contributes more than 5% of total book PnL, it is flagged. If the top 3 tokens together contribute more than 15% of total book PnL, the result is flagged as token-concentrated.
- **Token contribution table:** A full table of PnL contribution by token is produced and included in the results.

**Time / regime concentration:**

- **Share by calendar month:** The fraction of total book PnL earned in each calendar month. If any single month contributes more than 30% of total book PnL, the result is flagged as regime-concentrated.
- **Share by market regime:** The test period is divided into up-trending, down-trending, and sideways regimes based on the SOL price index. The fraction of book PnL earned in each regime is reported. A result that is positive only in up-trending regimes is not a distributional result — it is a beta result.

**Concentration kill criteria:** If top-decile share exceeds 70% AND top-3 token share exceeds 15%, the result is classified as outlier-driven and the test fails regardless of mean return.

---

## Guardrail 6 — Subperiod Stability

The full test period is divided into at least three subperiods of approximately equal length. The primary metrics (mean return, median return, EV, win rate) are computed independently for each subperiod. A result is only considered stable if it is positive in at least two of three subperiods.

**Subperiod definition:** Subperiods are defined by calendar date, not by number of trades. If the full test period is 12 months, the three subperiods are months 1-4, 5-8, and 9-12. If the full test period is 18 months, the three subperiods are months 1-6, 7-12, and 13-18.

**Subperiod pass requirement:** Mean return per trade must be positive in at least 2 of 3 subperiods at the Conservative (0.50%) cost level. A result that is positive in only 1 of 3 subperiods is not stable and does not constitute a pass.

**Subperiod reporting:** Results for each subperiod are reported in a table alongside the full-period results. The variance across subperiods (standard deviation of subperiod mean returns) is reported as a stability metric. High variance across subperiods indicates regime dependence.

---

## Guardrail 7 — Median Primacy

The median return per trade is reported alongside the mean return per trade for every exit structure and every subperiod. A positive mean with a non-positive median is not sufficient for a pass.

**Median pass requirement:** The median return per trade must be positive (after Conservative cost assumption) for the result to constitute a pass. A positive mean with a non-positive median indicates that the distribution is right-skewed by a small number of large winners, which is a concentration problem (see Guardrail 5) rather than a distributional result.

**Distribution reporting:** For each exit structure, the full distribution of per-trade returns is reported as a histogram with the following percentiles marked: 5th, 10th, 25th, 50th (median), 75th, 90th, 95th. The shape of the distribution — not just its mean and median — is part of the result.

**Skew and kurtosis:** Distribution skew and excess kurtosis are computed and reported. A result with skew > 2.0 is flagged as potentially outlier-driven and triggers additional concentration analysis.

**Joint pass requirement:** Both of the following must be true for a pass:
1. Mean return per trade > 0% at Conservative cost assumption
2. Median return per trade > 0% at Conservative cost assumption

If only one of these is true, the result is classified as PARTIAL and does not constitute a pass. A PARTIAL result triggers additional investigation before any Stage B decision.

---

## Guardrail 8 — Capital Concurrency and Operational Realism

The test reports the capital concurrency profile of the mechanical book: how many positions are open simultaneously at any point in time, and whether the resulting capital requirement and operational complexity are realistic for a human-scale operator.

**Concurrency metrics:**

- **Mean concurrent positions:** The average number of open positions at any point during the test period.
- **Maximum concurrent positions:** The peak number of open positions at any single point.
- **Concurrency distribution:** A histogram of daily concurrent position counts.
- **Capital utilization curve:** A time series of the fraction of total capital deployed on each day.

**Operational realism assessment:** The following questions are answered explicitly:

| Question | Threshold | Classification |
|----------|-----------|---------------|
| Mean concurrent positions | ≤ 20 | Operationally manageable for a human operator |
| Mean concurrent positions | 21-50 | Manageable with tooling; flag for discussion |
| Mean concurrent positions | > 50 | Requires automation; flag as operationally complex |
| Maximum concurrent positions | ≤ 50 | Acceptable |
| Maximum concurrent positions | > 100 | Requires significant capital and automation |
| Capital utilization | > 90% on average | Book is capital-constrained; sizing assumptions need review |
| Entry rate | > 10 new positions per day on average | Requires automated order management |

**Overlap analysis:** The test reports the fraction of positions that overlap in time (i.e., are open simultaneously). High overlap means the book's returns are correlated across positions, which reduces the effective sample size and makes the distributional result less reliable. If more than 50% of positions overlap with at least 5 other positions on average, the effective sample size is reported as adjusted downward accordingly.

**Minimum capital estimate:** Based on the concurrency analysis, the test reports the minimum capital required to run the book at the assumed position size without capital constraints. This is defined as the maximum concurrent positions multiplied by the assumed position size. If the minimum capital estimate exceeds $500K, the book is flagged as requiring institutional-scale capital for the assumed position size, and the analysis is re-run at a smaller position size.

---

## Full Pass/Fail Logic

A result constitutes a **PASS** (proceed to Stage B — paper trading of the mechanical book) if and only if **all** of the following are true:

| Criterion | Requirement |
|-----------|-------------|
| G1: Universe size | ≥ 100 tokens pass the quality filter |
| G2: Exit structure | Result holds for ≥ 3 of 4 pre-registered exit structures |
| G3: Sizing | Equal sizing only (no dynamic sizing applied) |
| G4: Cost robustness | Mean return > 0% at Conservative (0.50%) cost assumption |
| G4: Slippage | Mean return > 0% after additional 0.5% slippage on stop-loss exits |
| G5: Concentration — decile | Top-decile share ≤ 70% |
| G5: Concentration — token | Top-3 token share ≤ 15% |
| G5: Concentration — regime | No single month contributes > 30% of total PnL |
| G6: Subperiod stability | Mean return > 0% in ≥ 2 of 3 subperiods at Conservative cost |
| G7: Median | Median return per trade > 0% at Conservative cost assumption |
| G8: Concurrency | Mean concurrent positions ≤ 50 (manageable with tooling) |

A result constitutes a **FAIL** (close the line) if any of the following are true:

- Mean return ≤ 0% at Base (0.30%) cost assumption
- Median return ≤ 0% at Conservative cost assumption
- Result holds for fewer than 2 of 4 exit structures
- Top-decile share > 70% AND top-3 token share > 15% (outlier-driven)
- Result is positive in only 1 of 3 subperiods
- Universe < 50 tokens after filter (too thin)

A result is classified as **PARTIAL** (requires additional investigation before Stage B decision) if:

- Mean return > 0% but median return ≤ 0%
- Result holds for exactly 2 of 4 exit structures
- Result is positive in exactly 2 of 3 subperiods but with high variance
- Concurrency > 50 mean positions (operationally complex but not disqualifying)

---

## Immediate Kill Criteria (Stop Analysis Immediately)

The following conditions trigger an immediate stop and close of the line, regardless of any other results:

1. The quality filter cannot be defined without reference to future outcomes (look-ahead bias detected)
2. The positive EV result depends on a single exit structure that was clearly the best-fit to the data (overfitting signal — note: this cannot happen if the design is followed, since exit structures are pre-registered)
3. The positive EV result disappears entirely at 0.30% round-trip cost
4. The positive EV result is driven by fewer than 20 positions (not a distributional result)
5. A data error is discovered that affects more than 10% of the universe (analysis must be restarted with corrected data)

---

## What Changes from v1 Design

The following changes were made from the original T2 specification in `external_feedback_top3.md`:

| Change | v1 | v2 |
|--------|----|----|
| Quality filter | Described conceptually | Fully pre-registered with explicit thresholds and prohibited features |
| Exit structures | "3-4 maximum" | Exactly 4, fully pre-registered with specific levels |
| Sizing | "Equal sizing" | Explicitly prohibited: dynamic sizing, confidence weighting, Kelly |
| Cost assumptions | "Multiple levels" | Four specific levels (0.10%, 0.30%, 0.50%, 1.00%) with pass requirement at 0.50% |
| Slippage | "Sensitivity" | Explicit: 0.5% additional on stop-loss exits only |
| Exit liquidity | "Sanity checks" | Explicit: flag if exit size > 1% of ADV; re-run at smaller size if > 20% flagged |
| Concentration | "Top-1, top-3, top-decile, token, day/regime" | All five dimensions with explicit kill thresholds |
| Subperiod stability | "At least 2, preferably 3" | Exactly 3 subperiods; must be positive in ≥ 2 of 3 |
| Median requirement | "Median must matter as much as mean" | Explicit joint pass requirement: both mean AND median > 0% |
| Concurrency | "Show concurrent positions" | Full concurrency metrics with operational realism thresholds and minimum capital estimate |
| Pass/fail logic | Described qualitatively | Full table of 11 pass criteria and 6 fail criteria |
| Kill criteria | Listed | Numbered list of 5 immediate kill conditions |

---

## Execution Checklist

Before running any analysis, confirm the following are locked:

- [ ] Quality filter parameters recorded in this document (done above)
- [ ] Exit structure parameters recorded in this document (done above)
- [ ] Cost assumption levels recorded in this document (done above)
- [ ] Subperiod boundaries defined before data is examined
- [ ] All pass/fail thresholds recorded before data is examined
- [ ] Data source and pull date recorded at time of collection
- [ ] No changes to filter, exit structures, or thresholds after data collection begins

Any deviation from the above must be documented as a protocol note with explicit justification. Undocumented deviations invalidate the result.
