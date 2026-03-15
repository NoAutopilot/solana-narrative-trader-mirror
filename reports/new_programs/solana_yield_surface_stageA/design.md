# Solana Yield Surface Map — Stage A Design

**Program:** solana_yield_surface_stageA
**Date:** 2026-03-15
**Status:** IN PROGRESS

---

## Primary Question

Across the main Solana yield surfaces, where is the highest gross yield, believable net yield, and risk-adjusted yield? Which opportunities are base carry, structural enhancement, subsidy harvest, or fake yield?

## Universe

| Category | Examples | Data Source |
|----------|----------|-------------|
| Base staking | Native SOL delegation | Solana explorer, StakeWiz |
| Liquid staking | mSOL, JitoSOL, bSOL, jitoSOL, Sanctum LSTs | Protocol sites, DeFiLlama |
| LST LP pools | SOL-mSOL, SOL-JitoSOL pools on Orca/Meteora/Raydium | DEX dashboards, DeFiLlama |
| Lending | Kamino, marginfi, Drift, Solend | Protocol dashboards |
| Emissions / boosted | Active reward programs on any of the above | Protocol announcements |
| Levered / looped | Borrow SOL → stake → re-borrow loops | Computed from lending + staking rates |

## Classification Framework

Each opportunity is classified into exactly one category:

**BASE_CARRY** — Yield comes from native protocol mechanics (staking rewards, lending interest from real borrowers). Low complexity, low hidden risk. This is "the yield the chain actually produces."

**STRUCTURAL_ENHANCEMENT** — Yield is improved through a structural mechanism (e.g., MEV tips via JitoSOL, LST arbitrage) that has a believable, non-temporary basis. Higher than base carry but not dependent on emissions.

**FAKE_YIELD** — Yield appears high but collapses after accounting for costs, slippage, impermanent loss, reward decay, or hidden risks. The advertised number is misleading.

**SUBSIDY_HARVEST** — Yield depends materially on temporary token emissions or incentive programs. May be positive today but has a known or likely expiration date.

## Scoring Framework

For each opportunity:

1. **Gross Yield (annualized %)** — The advertised or observable headline rate.
2. **Fee Drag (annualized %)** — Management fees, protocol fees, swap fees.
3. **Friction Estimate (annualized %)** — Slippage on entry/exit, unstaking delays, IL proxy.
4. **Believable Net Yield = Gross - Fee Drag - Friction Estimate**
5. **Risk Score (1-5)** — 1 = lowest risk (native staking), 5 = highest risk (complex looping with liquidation exposure).
6. **Risk-Adjusted Yield = Believable Net Yield / Risk Score** — Higher is better.

## Pass/Fail Logic

Stage A recommends Stage B if and only if at least one opportunity:
- Has believable net yield > 0% after conservative friction estimates
- Has acceptable exitability (can exit within 1-3 days without >1% slippage)
- Has risk score <= 3
- Does not depend solely on temporary emissions
- Is realistically capturable by a human-sized operator (no HFT, no massive capital)

## Deliverables

1. `design.md` — This document
2. `data.md` — Raw data collection with sources
3. `results.md` — Unified yield surface table with all scores
4. `summary.md` — Adversarial analysis and Stage A verdict
