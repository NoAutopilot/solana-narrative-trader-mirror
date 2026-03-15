# T2 — Actuarial / Casino-Math Book Test: Design v3

**Program:** t2_actuarial_book
**Date:** 2026-03-15
**Version:** 3 (structural ambiguity resolved before execution)
**Author:** Manus AI
**Status:** PRE-REGISTERED — READY FOR EXECUTION
**Supersedes:** t2_design_v2.md

---

## What Changed from v2

Version 2 left the test form ambiguous between a one-time cohort study and a rolling book, did not specify explicit benchmarks, did not document the point-in-time trustworthiness of each filter field, had concentration kill logic that was incomplete, and did not require the actuarial book to outperform simple benchmarks. Version 3 resolves all of these gaps. Every change is documented in the "What Changed" table at the end of this document.

---

## Section 1 — Test Form: ROLLING BOOK

**The test form is a ROLLING BOOK. This is locked.**

A single-cohort study would produce a result that is specific to one entry date and one market regime. The rolling book tests whether the distributional result is stable across multiple entry cohorts and multiple market conditions. This is the correct form for a test that claims to be about the structural shape of the payoff distribution, not about any particular moment in time.

### Rolling Book Specification

The book reconstitutes monthly. At each month-end reconstitution date, the quality filter is applied using only data available at that date (no look-ahead). Tokens passing the filter at that date are eligible for entry at the next trading day's open. Tokens that were in a prior cohort may re-enter if they still qualify. Positions from prior cohorts that are still open continue to run under their original exit rules; they are not closed at reconstitution.

| Parameter | Value |
|-----------|-------|
| Reconstitution cadence | Monthly (last trading day of each calendar month) |
| Filter application | Point-in-time only; no future data used |
| Entry timing | Next trading day open after each reconstitution date |
| Re-entry | Allowed if token still passes filter at reconstitution date |
| Overlapping positions | Allowed; a token may have multiple open positions from different cohorts |
| Exit rules | 4 pre-registered exit structures (E1–E4), unchanged from v2 |
| Maximum holding period | 60 calendar days from entry, unchanged from v2 |
| Gap rule | If TP and SL both triggered same day, SL assumed first (conservative) |

**Fallback to single cohort:** If the data pipeline cannot support monthly point-in-time filter application (e.g., because historical market cap or volume data is not available with point-in-time accuracy), the test falls back to a **SINGLE COHORT** design. This fallback must be declared explicitly at the start of execution, before any analysis is run, with a written explanation of which data field prevented rolling implementation. The single cohort design uses a single filter date at the start of the test period and holds all qualifying tokens for the full test period, with exits governed by the same 4 exit structures.

The rolling book is the preferred form. The single cohort is the fallback. Both are not run simultaneously. The choice is made once, before data collection, and documented.

---

## Section 2 — Benchmarks

Two benchmarks are pre-registered. The actuarial book must outperform both benchmarks on mean return and must not be materially worse on median return at the Conservative cost assumption. A result that does not beat both benchmarks does not advance to Stage B, regardless of whether it is positive in isolation.

### Benchmark B1 — Equal-Weight Buy-and-Hold (60 Calendar Days)

B1 applies the same quality filter as the actuarial book, enters all qualifying tokens at the same entry prices, and holds each position for exactly 60 calendar days with no exit rules. The position is closed at the 60-day close price. The same cost assumptions are applied (entry cost + exit cost at the relevant round-trip level). No stop-loss, no take-profit. This benchmark tests whether the actuarial book's exit structure adds any value over passive holding.

| Parameter | Value |
|-----------|-------|
| Universe | Same filtered universe as actuarial book |
| Entry | Same entry prices as actuarial book |
| Exit | Close at 60 calendar days from entry |
| Sizing | Equal weight, same as actuarial book |
| Costs | Same four cost levels (0.10%, 0.30%, 0.50%, 1.00%) |
| Metrics reported | Mean return, median return, % positive, concentration metrics, subperiod breakdown |

### Benchmark B2 — Equal-Weight Fixed Hold (20 Trading Days)

B2 applies the same quality filter, enters at the same prices, and holds each position for exactly 20 trading days (approximately one calendar month). This is a shorter fixed-hold benchmark that tests whether the actuarial book's exit structure adds value over a mechanical monthly rotation. The 20-trading-day hold period is chosen to approximate one calendar month and to align with the rolling book's reconstitution cadence.

| Parameter | Value |
|-----------|-------|
| Universe | Same filtered universe as actuarial book |
| Entry | Same entry prices as actuarial book |
| Exit | Close at 20 trading days from entry |
| Sizing | Equal weight, same as actuarial book |
| Costs | Same four cost levels |
| Metrics reported | Mean return, median return, % positive, concentration metrics, subperiod breakdown |

### Benchmark Pass Requirement

The actuarial book (under each of the 4 exit structures) must satisfy all of the following relative to both B1 and B2 at the Conservative (0.50%) cost level:

- **Mean return of actuarial book > mean return of B1 and B2** (book must beat passive holding on mean)
- **Median return of actuarial book ≥ median return of B1 and B2** (book must not be worse on median)
- **If median tie occurs:** the actuarial book must show clearly lower maximum drawdown or better concentration metrics than the benchmark to advance

A result where the actuarial book is positive but does not beat either benchmark is classified as a FAIL. A result where the actuarial book beats one benchmark but not the other is classified as PARTIAL and requires additional investigation.

---

## Section 3 — Filter Data Feasibility

Each filter field is documented below with its exact source, point-in-time trustworthiness, and whether it is exact or a proxy. If a field is not point-in-time trustworthy, the substitution is documented.

### Filter Field Assessment

| Field | Intended Use | Primary Source | Point-in-Time Trustworthy? | Exact or Proxy | Notes |
|-------|-------------|----------------|---------------------------|----------------|-------|
| Token age (days since first on-chain trade) | Exclude new tokens | Solana on-chain data via Birdeye or Helius historical API | **YES** — first trade date is immutable on-chain | Exact | First trade timestamp is a permanent on-chain record; no look-ahead risk |
| 30-day average daily volume (USD) | Liquidity floor | Birdeye historical OHLCV or DeFiLlama | **YES** — historical volume data is point-in-time if pulled from a time-series API | Exact | Must use the 30-day window ending on the filter date, not the current 30-day window |
| Volume consistency (≥ 60% of days with volume) | Tradability | Same as above | **YES** — derived from the same historical volume series | Exact | Computed from the same 30-day window |
| Real tradability / non-honeypot | Exclude non-tradable tokens | On-chain transaction data; RugCheck or equivalent | **YES** — historical transaction records are immutable | Proxy | RugCheck scores are heuristic; use as a filter, not as a quality signal |
| Market cap | Size filter | **NOT USED — see substitution below** | **NO** | N/A | See substitution |

### Market Cap Substitution

**Market cap is not used as a filter field.** Historical market cap data for Solana tokens is not reliably point-in-time trustworthy from public sources. Market cap requires both circulating supply and price at the filter date. Circulating supply data for Solana tokens is frequently incorrect, retroactively adjusted, or unavailable for historical dates from public APIs. Using market cap as a filter introduces a risk of look-ahead bias if the supply data is not genuinely point-in-time.

**Substitution:** Market cap is replaced by a **stricter volume floor** combined with an **FDV proxy**. The substitution is:

| Substitute Field | Threshold | Source | Point-in-Time Trustworthy? | Rationale |
|-----------------|-----------|--------|---------------------------|-----------|
| 30-day average daily volume (USD) | ≥ $200K USD (raised from $100K in v2) | Birdeye historical OHLCV | YES | Higher volume floor serves as a proxy for minimum market size; tokens with < $200K ADV are typically micro-cap |
| 90-day average daily volume (USD) | ≥ $50K USD | Same | YES | Secondary floor to exclude tokens with recent volume spikes but thin history |
| FDV at filter date (if available) | ≥ $10M USD | On-chain token supply × price at filter date | CONDITIONAL — only used if supply data is verifiable on-chain | Proxy | FDV is more reliable than circulating supply for Solana tokens because total supply is typically fixed at mint; used only if verifiable |

If FDV data is not verifiable for a given token, the token is included if it passes the volume floors. The volume floors are the primary size proxy. FDV is a secondary check applied only where data quality is confirmed.

**Documentation requirement:** At execution time, the data source for each filter field is recorded in the data collection log with the pull date and API version. Any token where a filter field value is estimated rather than directly observed is flagged in the universe table.

---

## Section 4 — Concentration Kill Logic (Strengthened)

The concentration kill logic from v2 is retained and the following additional kill conditions are added. Any single kill condition is sufficient to fail the test, regardless of other results.

### Full Concentration Kill Conditions

| Kill Condition | Threshold | Source |
|---------------|-----------|--------|
| Top-decile share (v2) | > 70% of total PnL from top 10% of positions | v2 |
| Top-3 token share (v2) | > 15% of total PnL from top 3 tokens | v2 |
| Single month share (v2) | > 30% of total PnL from any one calendar month | v2 — tightened to 30% |
| **Top-20 position share (new)** | **> 80% of total PnL from top 20 positions** | v3 |
| **Single month share (tightened)** | **> 35% of total PnL from any one calendar month** | v3 — note: the 30% flag from v2 is retained as a flag; 35% is the kill threshold |
| **Token family / narrative cluster dominance (new)** | See definition below | v3 |
| **Sparse token participation (new)** | See definition below | v3 |

### Token Family / Narrative Cluster Definition

A token family or narrative cluster is defined as a group of tokens that share a common on-chain characteristic or market narrative that is likely to cause correlated price behavior. For the purposes of this test, the following cluster types are identified:

| Cluster Type | Definition | Detection Method |
|-------------|------------|-----------------|
| DeFi governance tokens | Tokens whose primary function is governance of a DeFi protocol | Manual classification at filter date |
| Meme / community tokens | Tokens with no stated utility beyond community or speculation | Manual classification at filter date |
| AI-themed tokens | Tokens marketed primarily around AI or machine learning narratives | Manual classification at filter date |
| Gaming / GameFi tokens | Tokens associated with on-chain gaming protocols | Manual classification at filter date |
| Infrastructure / L2 tokens | Tokens associated with Solana infrastructure or scaling | Manual classification at filter date |

**Cluster kill condition:** If tokens from a single cluster type contribute more than 40% of total book PnL, and the cluster represents fewer than 30% of the total token universe, the result is classified as cluster-concentrated and the test fails. This prevents a result that is actually "AI tokens had a good run" from being reported as a distributional result.

**If cluster analysis is not feasible:** If manual classification of the token universe is not completed before execution (e.g., due to universe size exceeding 300 tokens), cluster analysis is omitted and this omission is documented explicitly. The omission does not invalidate the test, but the result is flagged as lacking cluster concentration verification, and the token contribution table must be reviewed manually before any Stage B decision.

### Sparse Participation Kill Condition

The test fails if token-level PnL participation is too sparse to constitute a distributional result. Specifically: if more than 60% of total book PnL is attributable to fewer than 10% of the tokens in the universe, the result is classified as sparse and the test fails. This is distinct from the top-decile position share check (which is position-level) — this check is token-level and asks whether the result is broad across the token universe, not just across individual trades.

---

## Section 5 — Execution and Price Path Assumptions

All price path assumptions are stated explicitly and applied consistently throughout.

### Data Frequency

**Daily OHLC data is used for entry and exit testing.** Intraday tick data is not used. This is a deliberate conservative choice: daily OHLC is more widely available, more reliable for historical Solana token data, and less susceptible to data quality issues than intraday data. The cost of this choice is that same-bar ambiguity must be resolved pessimistically (see below).

### Same-Bar Ambiguity Resolution

When using daily OHLC data, it is not possible to determine the intraday order of events within a single trading day. The following rules apply:

- **If the daily high touches the take-profit level and the daily low touches the stop-loss level on the same day:** the stop-loss is assumed to have triggered first. The position is closed at the stop-loss price. This is the most conservative assumption and is applied without exception.
- **If only the take-profit level is touched intraday:** the position is closed at the take-profit price at the close of that day.
- **If only the stop-loss level is touched intraday:** the position is closed at the stop-loss price at the close of that day.
- **No assumption of fills better than the threshold price.** The take-profit fill is assumed at exactly the take-profit price, not better. The stop-loss fill is assumed at exactly the stop-loss price, not better (i.e., no slippage improvement on stop-loss exits beyond the conservative assumption).

### Entry Assumption

Entry is at the next trading day's open after the filter date. No same-day entry is assumed. No assumption of fills better than the open price. If the open price is not available for a given token on a given day (e.g., no trading occurred), the entry is deferred to the next day with trading activity, and this deferral is documented.

### Stop-Loss Precedence

Stop-loss precedence is in place and unconditional. If both TP and SL are touched on the same day, SL is assumed to trigger first. This rule cannot be overridden by any other consideration.

### Close-Based Execution

Exit fills are assumed at the close of the day the threshold is touched, not at the intraday touch price. This is conservative by design: in practice, a limit order at the take-profit level would fill at the touch price, not the close. Using the close price for exits understates take-profit returns and is therefore a conservative assumption that biases against false positives.

---

## Section 6 — Updated Pass / Fail Logic

The pass logic from v2 is retained and the benchmark outperformance requirement is added. A result must satisfy all v2 pass criteria AND the benchmark outperformance requirement to advance.

### Full Pass Criteria (all must be true)

| Criterion | Requirement | Source |
|-----------|-------------|--------|
| Universe size | ≥ 100 tokens pass quality filter | v2 |
| Exit structure coverage | Result holds for ≥ 3 of 4 exit structures | v2 |
| Sizing | Equal sizing applied throughout | v2 |
| Cost robustness — mean | Mean return > 0% at Conservative (0.50%) cost | v2 |
| Cost robustness — slippage | Mean return > 0% after 0.50% additional slippage on SL exits | v2 |
| Concentration — decile | Top-decile position share ≤ 70% | v2 |
| Concentration — token | Top-3 token share ≤ 15% | v2 |
| Concentration — month | No single month > 35% of total PnL | v3 (tightened) |
| Concentration — top-20 | Top-20 positions ≤ 80% of total PnL | v3 (new) |
| Concentration — cluster | No single cluster type > 40% of PnL if < 30% of universe | v3 (new) |
| Concentration — participation | ≥ 10% of tokens contribute ≥ 40% of PnL (not sparse) | v3 (new) |
| Subperiod stability | Mean return > 0% in ≥ 2 of 3 subperiods at Conservative cost | v2 |
| Median primacy | Median return per trade > 0% at Conservative cost | v2 |
| Concurrency | Mean concurrent positions ≤ 50 | v2 |
| **Benchmark B1 outperformance** | **Mean return of book > mean return of B1 at Conservative cost** | v3 (new) |
| **Benchmark B2 outperformance** | **Mean return of book > mean return of B2 at Conservative cost** | v3 (new) |
| **Benchmark median** | **Median return of book ≥ median return of both B1 and B2** | v3 (new) |

### Fail Criteria (any one sufficient)

| Criterion | Threshold |
|-----------|-----------|
| Mean return at Base cost | ≤ 0% at 0.30% round-trip |
| Median return at Conservative cost | ≤ 0% |
| Exit structure coverage | Holds for < 2 of 4 structures |
| Top-decile + top-3 token | Top-decile > 70% AND top-3 token > 15% |
| Top-20 position share | > 80% of total PnL |
| Single month share | > 35% of total PnL |
| Cluster concentration | Single cluster > 40% of PnL and < 30% of universe |
| Sparse participation | > 60% of PnL from < 10% of tokens |
| Subperiod stability | Positive in only 1 of 3 subperiods |
| Universe size | < 50 tokens after filter |
| **Benchmark B1** | **Book mean ≤ B1 mean at Conservative cost** |
| **Benchmark B2** | **Book mean ≤ B2 mean at Conservative cost** |

### Partial Classification (additional investigation before Stage B)

A PARTIAL result is declared if the book is positive in isolation but fails one or more benchmark comparisons, or if the median tie condition applies. A PARTIAL result does not advance to Stage B automatically. It requires a written assessment of whether the partial failure is a data artifact, a regime artifact, or a genuine structural weakness.

---

## Section 7 — Why This Version Is Cleaner

**Test form:** T2 is a rolling book. It reconstitutes monthly, applies the filter point-in-time, and accumulates positions across multiple cohorts over the full test period. It is not a cohort study. This choice was made because a cohort study produces a result that is specific to one entry date and one market regime. The rolling book tests whether the distributional result holds across multiple entry points and multiple market conditions, which is the correct test for a claim about structural payoff distribution.

**Benchmark:** The actuarial book is judged against two simple benchmarks — equal-weight buy-and-hold for 60 days (B1) and equal-weight fixed hold for 20 trading days (B2). Both use the same filtered universe and the same cost assumptions. The book must outperform both benchmarks on mean return and must not be worse on median return. This requirement exists because a positive result in isolation could simply mean that Solana tokens had a good run during the test period. The benchmarks control for this: if the book cannot beat passive holding of the same universe, the exit structure is adding no value and the result is not interesting.

**Why this makes the result less gameable and less likely to become another false positive:** Three specific design choices reduce the risk of a false positive. First, the rolling book prevents the result from being a single-period artifact — a result that is positive in only one of three subperiods fails. Second, the benchmark requirement prevents the result from being a beta artifact — a result that is positive but does not beat passive holding of the same universe fails. Third, the concentration kill logic prevents the result from being an outlier artifact — a result driven by a small number of positions, tokens, or a single market regime fails. A result that survives all three of these filters is genuinely more likely to reflect a structural property of the payoff distribution than any prior test in this program history.

---

## Changes from v2 to v3

| Item | v2 | v3 |
|------|----|----|
| Test form | Ambiguous (cohort or rolling implied) | Locked: ROLLING BOOK with monthly reconstitution |
| Fallback | Not specified | Explicit: SINGLE COHORT if rolling data not available |
| Benchmarks | None | B1 (60-day buy-and-hold) and B2 (20-trading-day fixed hold) |
| Pass logic | Positive in isolation | Must outperform B1 and B2 on mean; not worse on median |
| Market cap filter | Used as filter field | Removed — not point-in-time trustworthy |
| Volume floor | $100K 30d ADV | Raised to $200K 30d ADV + $50K 90d ADV as market cap substitute |
| FDV | Not mentioned | Added as secondary size check where verifiable |
| Filter data documentation | Not specified | Full table: source, point-in-time trustworthiness, exact vs proxy |
| Top-20 position kill | Not present | Added: kill if top-20 positions > 80% of PnL |
| Single month kill | 30% flag | 35% kill threshold (30% remains a flag) |
| Cluster kill | Not present | Added: kill if single cluster > 40% of PnL and < 30% of universe |
| Sparse participation kill | Not present | Added: kill if > 60% of PnL from < 10% of tokens |
| Data frequency | Not specified | Explicitly: daily OHLC only |
| Same-bar ambiguity | Not specified | Explicitly: resolved pessimistically (SL assumed first) |
| Fill assumption | Not specified | Explicitly: no fills better than threshold; close-based exit |
| "Why cleaner" section | Not present | Added |
