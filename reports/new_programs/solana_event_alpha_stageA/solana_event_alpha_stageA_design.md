# Solana Event / Governance Alpha Pilot — Stage A: Design Document

**Program:** solana_event_alpha_stageA  
**Version:** v1 (pre-registered 2026-03-15)  
**Status:** LOCKED — no changes after data collection begins  

---

## 1. Primary Question

Do official Solana ecosystem events with explicit economic consequences create positive expected value after realistic costs over short holding windows?

---

## 2. Scope and Exclusions

### Included

An event qualifies for this dataset if and only if it satisfies **all five** of the following criteria:

1. **Official:** Announced by the protocol team, foundation, or governance system — not a third party, KOL, or community member.
2. **Timestamped:** The announcement has a verifiable, precise timestamp (to the hour at minimum).
3. **Economically concrete:** The event changes a specific, quantifiable parameter (rate, cap, threshold, emission, supply, fee) or executes a governance decision with a defined economic effect.
4. **Liquid asset linkage:** The event is directly linked to an asset that trades on at least one major CEX or DEX with ≥ $1M average daily volume.
5. **Specific mechanism:** The economic mechanism can be stated in one sentence — e.g., "increases borrowing cost for SOL by X bps" or "releases Y tokens to the market."

### Excluded (hard exclusions, no exceptions)

- Vague partnership announcements without specific economic terms
- Roadmap updates, feature previews, or "coming soon" posts
- Community governance discussions that have not passed
- KOL commentary, influencer posts, or secondary analysis
- Telegram/Discord community chat (announcement channels only)
- Events where the affected asset has < $1M ADV
- Events where the timestamp cannot be verified to within 1 hour
- Events where the economic mechanism is ambiguous or requires interpretation

---

## 3. Event Classes

| Class | Code | Description | Examples |
|---|---|---|---|
| Parameter change | PARAM | Change to a protocol parameter with direct economic effect | LTV change, borrow cap, fee tier, liquidation threshold, validator eligibility |
| Reward change | REWARD | Change to staking rewards, fee distribution, emissions, or incentive programs | Staking rate change, emissions on/off, points program with explicit start |
| Supply change | SUPPLY | Scheduled or executed token release, unlock, or treasury action | Token unlock, cliff release, treasury sale |
| Governance execution | GOV | Passed proposal with explicit execution time or timelock expiry | Timelocked action execution, blacklist/whitelist change, validator set change |

---

## 4. Source List (pre-registered, 10–20 sources)

| # | Source Name | Platform | Official URL | Rationale |
|---|---|---|---|---|
| S1 | Solana Foundation Announcements | Blog | https://solana.com/news | Foundation-level official announcements |
| S2 | Solana Governance Forum | Forum | https://forum.solana.com | Official on-chain governance proposals and votes |
| S3 | Marinade Finance Governance | Forum | https://forum.marinade.finance | Marinade MNDE governance: staking params, fee changes |
| S4 | Jito Network Blog | Blog | https://www.jito.network/blog | JitoSOL/JTO staking, MEV distribution, fee changes |
| S5 | Kamino Finance Announcements | Discord/Blog | https://app.kamino.finance / https://kamino.finance/blog | Borrow cap, LTV, fee tier changes for KMNO/lending |
| S6 | Jupiter Governance | Forum | https://vote.jup.ag | JUP governance: fee changes, emissions, buyback programs |
| S7 | Drift Protocol Announcements | Blog/Discord | https://www.drift.trade/blog | Perp market params, insurance fund, fee changes |
| S8 | Orca Governance | Forum | https://gov.orca.so | ORCA fee tier, emissions, pool parameter changes |
| S9 | Raydium Announcements | Blog | https://raydium.io/blog | RAY emissions, fee changes, pool launches |
| S10 | Pyth Network Announcements | Blog | https://pyth.network/blog | PYTH staking, governance, oracle fee changes |
| S11 | Token unlock calendars | Web | https://token.unlocks.app / https://vestlab.io | Scheduled SOL ecosystem token unlocks |
| S12 | Solana Foundation Validator Info | Docs | https://solana.com/staking | Validator commission, stake pool parameter changes |
| S13 | Sanctum Announcements | Blog/Discord | https://www.sanctum.so/blog | LST parameters, INF rebalancing, fee changes |
| S14 | Meteora Announcements | Blog | https://www.meteora.ag/blog | Pool parameters, emission changes, DLMM fee changes |

**Total: 14 sources.** All are official channels of the named protocols.

---

## 5. Historical Window

**Primary window:** 2025-09-15 to 2026-03-15 (180 days)  
**Fallback window:** 2025-12-15 to 2026-03-15 (90 days, if data collection is blocked for the full period)

The window is fixed before data collection begins. No extension or contraction after events are reviewed.

---

## 6. Asset Universe

Only assets that meet **all** of the following at the time of the event:

- Listed on at least one major CEX (Binance, OKX, Bybit, Coinbase, Kraken) **or** trading on a Solana DEX with ≥ $1M average daily volume over the 30 days prior to the event
- Price data available via Yahoo Finance or CoinGecko for the event window
- Not a stablecoin (stablecoins have no meaningful price reaction to measure)

**Pre-approved liquid assets** (subject to ADV check at event time):

SOL, JTO, MNDE, KMNO, JUP, DRIFT, ORCA, RAY, PYTH, INF, WIF, BONK, JLP

Any other asset linked to a qualifying event must pass the ADV check before inclusion.

---

## 7. Time Windows

For each qualifying event, compute returns over the following windows where applicable:

| Window Code | Definition | Applicability |
|---|---|---|
| W1 | Announcement time to +1h | All events with announcement timestamp |
| W2 | Announcement time to +4h | All events with announcement timestamp |
| W3 | Announcement time to +1d (24h) | All events with announcement timestamp |
| W4 | Effective time to +1h | Events where effective time ≠ announcement time |
| W5 | Effective time to +4h | Events where effective time ≠ announcement time |

**Return definition:** (price at window end) / (price at window start) - 1, using the best available price (CEX mid or DEX TWAP). Raw return, not excess return.

**Cost adjustment:** Subtract pre-registered cost assumption from each raw return.

---

## 8. Cost Assumptions

| Scenario | Round-trip cost | Notes |
|---|---|---|
| Optimistic | 0.10% | CEX market order, tight spread, no slippage |
| Base | 0.25% | CEX market order, moderate spread |
| Conservative | 0.50% | DEX execution, moderate slippage |
| Stress | 1.00% | DEX execution, high slippage, adverse fill |

All pass/fail gates are evaluated at **conservative (0.50%)** cost. Optimistic and base are reported for context.

---

## 9. Pass / Fail Gates (per event class)

An event class **passes** if and only if **all five** of the following hold at conservative cost:

| Gate | Threshold | Rationale |
|---|---|---|
| G1: Sample size | N ≥ 10 events | Below 10, no statistical inference is possible |
| G2: Mean return | Mean net return > 0 | Positive expected value required |
| G3: Median return | Median net return > 0 | Median must confirm mean is not outlier-driven |
| G4: Benchmark advantage | Mean net return > random-date benchmark mean | Must beat random timing on same asset |
| G5: Concentration | Top-1 event share < 50% of total PnL | Result must not be driven by a single event |

An event class **fails** if any gate is not met.

The overall program verdict is:
- **GO** if ≥ 1 event class passes all five gates
- **NO-GO** if 0 event classes pass
- **BLOCKED** if the dataset cannot be constructed (insufficient events, data unavailable, timestamps unverifiable)

---

## 10. Kill Criteria (pre-registered)

The program closes immediately with verdict **BLOCKED** if:

- K1: Total qualifying events across all classes < 15 after applying inclusion rules
- K2: No liquid asset price data is available for ≥ 50% of qualifying events
- K3: ≥ 70% of events cannot be timestamped to within 1 hour

The program closes immediately with verdict **NO-GO** if:

- K4: No event class has N ≥ 10 (insufficient sample for any class)
- K5: All event classes fail G3 (median ≤ 0 at conservative cost)

---

## 11. Benchmark Construction

For each qualifying event, generate 20 random-date controls:

- Same asset as the event
- Same holding window as the event
- Random dates drawn from the same 180-day window, excluding ±3 days around the actual event
- Apply the same cost assumption

The benchmark mean and median are the average across all random-date controls for all events in the class.

---

## 12. Reporting Requirements

For each event class and overall, report:

- Event count (N)
- Mean net return (all windows, all cost levels)
- Median net return (all windows, all cost levels)
- % positive
- Top-1 event share of total PnL
- Top-3 event share of total PnL
- Benchmark mean and median (random-date)
- Benchmark advantage (event mean - benchmark mean)
- Pass/fail status per gate
- Overall verdict per class

---

## 13. Hard Rules

1. No changes to source list, event classes, windows, cost assumptions, or pass/fail gates after data collection begins.
2. Any event that does not clearly satisfy all five inclusion criteria is excluded — no borderline cases.
3. If a source is inaccessible (blocked, deleted, rate-limited), record as BLOCKED — do not substitute an unofficial source.
4. Do not recommend another Solana alpha-search program if this fails. This pilot is justified only because it uses a genuinely different information surface: upstream official event flow, not downstream price features.

---

*Design locked: 2026-03-15. Data collection begins after this document is committed.*
