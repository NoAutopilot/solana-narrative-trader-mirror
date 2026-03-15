# Solana Event / Governance Alpha — Stage A Results

**Program:** solana_event_alpha_stageA  
**Design version:** v1 (pre-registered)  
**Execution date:** 2026-03-15  
**Data sources:** Yahoo Finance (OHLCV), Kamino Governance Forum, Jito Forum, Jupiter DAO, Marinade Blog, DeFiLlama, Tokenomist  
**Test window:** 2025-09-15 to 2026-03-15 (180 days)

---

## VERDICT: BLOCKED

**Kill criterion triggered:** K1 — Only 14 qualifying events identified (pre-registered threshold: ≥ 15).

This is a hard stop. The dataset is too small to distinguish signal from noise. No pass/fail analysis is valid at N = 14 across three classes. Stage B is not warranted on this evidence.

---

## 1. Event Dataset

A total of 14 events were identified from official sources across three pre-registered classes. All events are verified from primary sources (governance forums, official blogs, on-chain announcements). No inferred or secondary-source events were included.

| ID | Class | Date | Asset | Mechanism |
|---|---|---|---|---|
| SC-001 | SUPPLY_CHANGE | 2025-09-28 | JUP | 53.47M JUP unlocked (monthly vesting) |
| SC-002 | SUPPLY_CHANGE | 2025-10-28 | JUP | 53.47M JUP unlocked (monthly vesting) |
| SC-003 | SUPPLY_CHANGE | 2025-11-28 | JUP | 53.47M JUP unlocked (monthly vesting) |
| SC-004 | SUPPLY_CHANGE | 2025-12-28 | JUP | 53.47M JUP unlocked (monthly vesting) |
| SC-005 | SUPPLY_CHANGE | 2026-01-28 | JUP | 53.47M JUP unlocked (monthly vesting) |
| SC-006 | SUPPLY_CHANGE | 2026-02-28 | JUP | 53.47M JUP unlocked (monthly vesting) |
| RW-001 | REWARD_CHANGE | 2025-11-07 | KMNO | Kamino Season 5 start: 100M KMNO over 3 months |
| RW-002 | REWARD_CHANGE | 2025-09-15 | MNDE | MIP-13 activated: 50% of fees to MNDE buybacks |
| RW-003 | REWARD_CHANGE | 2026-01-29 | MNDE | Dynamic Commission for Validators launched |
| RW-004 | REWARD_CHANGE | 2025-10-02 | KMNO | CASH Growth Initiative: new KMNO incentive program |
| RW-005 | REWARD_CHANGE | 2025-12-12 | PYTH | Pyth Reserve: protocol revenue → monthly PYTH buybacks |
| GV-001 | GOVERNANCE_EXECUTION | 2025-10-28 | JTO | JIP-26 passed: 50K JitoSOL to CSD for JTO buybacks |
| GV-002 | GOVERNANCE_EXECUTION | 2025-12-22 | JTO | JIP-31 passed: BAM Early Adopter Subsidy from fees |
| GV-003 | GOVERNANCE_EXECUTION | 2026-02-23 | JUP | Net-Zero Emissions vote: 700M Jupuary airdrop cancelled |

**Class distribution:** SUPPLY_CHANGE: 6, REWARD_CHANGE: 5, GOVERNANCE_EXECUTION: 3.

**Why only 14 events?** The 180-day window (Sep 15 2025 – Mar 15 2026) is a bear market period for Solana DeFi. Governance activity slows in downtrends. The pre-registered inclusion criteria (must be from official primary sources, must have a defined economic mechanism, must affect a liquid token with ≥ 90 days of price history) excluded:

- PYTH unlock (May 2025 — outside window; next is May 2026 — outside window)
- JTO monthly unlocks (daily linear vest — too small per event to qualify as discrete event)
- Raydium/Orca parameter changes (no official governance forum with timestamped proposals)
- Validator commission changes (too frequent, no single event date)
- Protocol upgrades without tokenomic mechanism

---

## 2. Raw Price Results

All prices from Yahoo Finance daily close data. Returns computed from close on event date to close on event date + N days.

| ID | Asset | Date | p0 | p1d | p3d | p7d | net_1d | net_7d |
|---|---|---|---|---|---|---|---|---|
| SC-001 | JUP | 2025-09-28 | $0.0009 | $0.0009 | $0.0009 | $0.0010 | +0.0% | +17.2% |
| SC-002 | JUP | 2025-10-28 | $0.0009 | $0.0009 | $0.0007 | $0.0007 | −0.5% | −28.1% |
| SC-003 | JUP | 2025-11-28 | $0.0006 | $0.0006 | $0.0006 | $0.0007 | −0.5% | +5.4% |
| SC-004 | JUP | 2025-12-28 | $0.0007 | $0.0007 | $0.0007 | $0.0007 | −0.5% | +0.1% |
| SC-005 | JUP | 2026-01-28 | $0.0006 | $0.0006 | $0.0005 | $0.0005 | −0.5% | −27.1% |
| SC-006 | JUP | 2026-02-28 | $0.0002 | $0.0002 | $0.0002 | $0.0002 | −0.5% | −1.4% |
| RW-001 | KMNO | 2025-11-07 | $0.0612 | $0.0599 | $0.0594 | $0.0564 | −2.6% | −8.4% |
| RW-002 | MNDE | 2025-09-15 | $0.1613 | $0.1644 | $0.1505 | $0.1385 | +1.4% | −14.6% |
| RW-003 | MNDE | 2026-01-29 | $0.0357 | $0.0336 | $0.0283 | $0.0246 | −5.9% | −31.8% |
| RW-004 | KMNO | 2025-10-02 | $0.0767 | $0.0800 | $0.0785 | $0.0718 | +3.8% | −6.8% |
| RW-005 | PYTH | 2025-12-12 | $0.0638 | $0.0653 | $0.0621 | $0.0581 | +1.8% | −9.3% |
| GV-001 | JTO | 2025-10-28 | $1.0573 | $1.0598 | $0.9543 | $0.7656 | −0.2% | −28.1% |
| GV-002 | JTO | 2025-12-22 | $0.3562 | $0.3574 | $0.3848 | $0.3848 | −0.4% | +7.5% |
| GV-003 | JUP | 2026-02-23 | $0.0002 | $0.0002 | $0.0002 | $0.0002 | −0.5% | +10.2% |

*All net returns shown at conservative cost (0.50% round-trip).*

---

## 3. Class-Level Metrics

### SUPPLY_CHANGE (N = 6, JUP monthly unlocks)

| Window | Mean Net | Median Net | % Positive | Benchmark Mean | Beats Bench? |
|---|---|---|---|---|---|
| 1d | −1.04% | −1.47% | 33% | +33.2% | No |
| 3d | −3.28% | −5.96% | 33% | +33.9% | No |
| 7d | −5.66% | −0.67% | 50% | +32.2% | No |

**Interpretation:** JUP monthly unlocks show no consistent directional signal. The benchmark mean is anomalously positive (+33%) because the benchmark period includes the Sep-Oct 2025 JUP rally, which happened to be the dominant regime. The event dates themselves are spread across a declining trend. There is no evidence of a systematic unlock-related price reaction in either direction.

The 7d window shows 50% positive — coin flip. The mean is negative at every window. The benchmark massively outperforms, meaning any directional trade on JUP during this period was better served by random entry than by waiting for unlock dates.

**Verdict for class:** NO SIGNAL.

---

### REWARD_CHANGE (N = 5)

| Window | Mean Net | Median Net | % Positive | Benchmark Mean | Beats Bench? |
|---|---|---|---|---|---|
| 1d | −0.36% | +1.43% | 60% | −1.64% | Yes |
| 3d | −4.01% | −0.19% | 40% | −3.19% | No |
| 7d | −14.19% | −9.33% | 0% | −6.21% | No |

**Interpretation:** The 1d window shows a positive median (+1.43%) and beats the benchmark — the only window across any class where this occurs. However:

1. N = 5 is far below the G1 threshold of 10. This is not a valid sample.
2. The 7d window shows 0% positive and −14.19% mean — every reward change event was followed by a 7-day decline.
3. The benchmark mean at 7d is also negative (−6.21%), confirming this is a bear market artifact, not an event effect.
4. The apparent 1d positive median is driven by two events (RW-002 MNDE +1.4%, RW-004 KMNO +3.8%) that both reversed sharply within 7 days.

**Verdict for class:** INSUFFICIENT SAMPLE. The 1d positive median is a data artifact, not a tradeable signal.

---

### GOVERNANCE_EXECUTION (N = 3)

| Window | Mean Net | Median Net | % Positive | Benchmark Mean | Beats Bench? |
|---|---|---|---|---|---|
| 1d | −1.44% | −0.27% | 0% | −1.11% | No |
| 3d | −0.65% | +1.11% | 67% | −4.81% | Yes |
| 7d | −3.44% | +7.54% | 67% | −6.98% | Yes |

**Interpretation:** The 3d and 7d windows show a positive median and beat the benchmark. At first glance this looks interesting. However:

1. N = 3 is trivially small. Three events cannot establish any pattern.
2. The positive median at 7d is driven entirely by GV-003 (JUP Net-Zero Emissions, +10.2%). One event out of three.
3. GV-001 (JTO JIP-26 buyback) was −28.1% at 7d — the largest single loss in the dataset. This is the event with the strongest theoretical positive mechanism (buyback funded by 100% of protocol revenue), and it was the worst performer.
4. The benchmark mean at 7d is −6.98%, making it easy to beat. This is a low bar.

**Verdict for class:** INSUFFICIENT SAMPLE. Three events prove nothing. The apparent outperformance is driven by one positive outlier and one massive negative outlier that cancel each other out in the mean.

---

## 4. Concentration Analysis

| Class | Top-1 share (7d abs PnL) | Interpretation |
|---|---|---|
| SUPPLY_CHANGE | 21.7% | Moderate — SC-001 (+17.2%) dominates positive side |
| REWARD_CHANGE | 24.1% | Moderate — but all events negative at 7d |
| GOVERNANCE_EXECUTION | 22.3% | Low concentration by share, but N=3 so meaningless |

Concentration is not the binding constraint here. Sample size is.

---

## 5. Kill Criterion Analysis

| Kill | Criterion | Status | Value |
|---|---|---|---|
| K1 | N < 15 total events | **TRIGGERED** | N = 14 |
| K2 | > 50% events from single source | Not triggered | Max = 43% (JUP unlocks) |
| K3 | > 50% events from single asset | Not triggered | Max = 50% (JUP, 7 events) |
| K4 | No class has N ≥ 10 | Would trigger independently | Max class N = 6 |
| K5 | Data quality < 80% | Not triggered | 100% price coverage |

**K1 and K4 both trigger.** The dataset fails on sample size alone, before any signal analysis is relevant.

---

## 6. Adversarial Assessment

### Why the dataset is this small

The 180-day window was chosen to be long enough to capture multiple event cycles while remaining recent enough to be relevant. The problem is that Solana DeFi governance in a bear market produces fewer qualifying events than in a bull market. Specifically:

- **JUP dominates SUPPLY_CHANGE.** Six of the six supply change events are the same token (JUP) with the same mechanism (monthly unlock). This is not six independent data points — it is one recurring event observed six times. The pre-registered design allowed this, but it means the SUPPLY_CHANGE class is effectively a single-asset time series, not a cross-sectional event study.
- **REWARD_CHANGE events are sparse.** Only five qualifying events exist because most protocols either (a) did not change reward structures during this period, or (b) changed them too gradually (no single announcement date) to qualify.
- **GOVERNANCE_EXECUTION is extremely sparse.** Only three events with clear on-chain execution dates and liquid token exposure. Most governance activity either affects non-liquid tokens or has no clear price mechanism.

### Why the apparent signals are not real

The REWARD_CHANGE 1d positive median and the GOVERNANCE_EXECUTION 7d positive median both fail for the same reason: the events are not independent, the sample is too small, and the apparent outperformance is driven by one or two outliers in a declining market where the benchmark is also negative.

The most striking finding is **GV-001 (JTO JIP-26 buyback)**. This was the event with the strongest theoretical positive mechanism — a DAO vote to use 100% of protocol revenue for JTO buybacks, funded by 50,000 JitoSOL (~$12.5M). If governance execution events had any positive price effect, this should have been the clearest example. Instead, JTO fell −28.1% in the 7 days following the announcement. This is not evidence that the buyback was bad — it is evidence that macro and sector forces overwhelm any governance-level signal at this sample size and in this regime.

### The fundamental problem with this approach

Event-driven alpha on Solana governance requires:
1. A large enough universe of qualifying events (this program found 14 in 180 days)
2. Events that are not already priced in before announcement (governance forums are public)
3. A liquid, shortable market for the affected assets (JTO, KMNO, MNDE have thin perps markets)
4. A regime where governance news can move prices (bear markets suppress all token-specific news)

None of these four conditions are fully satisfied in the current environment.

---

## 7. What Would Change the Verdict

The BLOCKED verdict could be revisited under the following conditions:

1. **Extend the window to 12 months (Sep 2024 – Sep 2025)** — this would capture the bull market period and likely yield 30–50 qualifying events. The pre-registered design would need to be updated with a new window declaration before data collection.

2. **Add new event classes** — specifically, protocol fee switch events (where a protocol activates fee collection for the first time) and major listing events (where a Solana token lists on a major CEX). Both classes have clearer price mechanisms and more historical examples.

3. **Relax the "official primary source" requirement** — allowing well-documented secondary sources (e.g., Messari governance reports) would add 5–10 events. However, this introduces verification risk and should be declared before data collection.

None of these changes should be made retroactively. If the window or event classes are changed, the design must be re-registered and the full data collection process repeated.

---

## 8. Final Verdict

**BLOCKED — K1 triggered (N = 14, threshold = 15).**

The program cannot issue a GO or NO-GO verdict on this evidence. The dataset is too small to distinguish signal from noise. The apparent positive signals in REWARD_CHANGE (1d) and GOVERNANCE_EXECUTION (3d, 7d) are not statistically meaningful at N = 5 and N = 3 respectively.

The data does not support proceeding to Stage B. It also does not definitively falsify the hypothesis — it simply cannot test it at this sample size.

**Recommended next action:** See summary document for options.
