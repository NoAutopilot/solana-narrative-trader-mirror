# Solana Yield Surface Map — Stage A Results

**Program:** solana_yield_surface_stageA
**Date:** 2026-03-15
**Status:** COMPLETE

---

## Unified Yield Surface Table

The table below scores every major Solana yield surface on a consistent framework. Gross yield is the advertised or observable headline rate. Fee drag captures management fees, protocol fees, and swap costs. Friction estimate captures slippage, unstaking delays, impermanent loss, and rate variability. Believable net yield is gross minus fee drag minus friction. Risk score ranges from 1 (lowest) to 5 (highest). Risk-adjusted yield divides believable net yield by risk score.

| # | Opportunity | Classification | Gross Yield | Fee Drag | Friction Est. | Believable Net Yield | Risk Score (1-5) | Risk-Adj Yield | Exitability | Verdict |
|---|-------------|---------------|-------------|----------|---------------|---------------------|-----------------|----------------|-------------|---------|
| 1 | Native SOL staking | BASE_CARRY | 5.8% | 0.3% (validator commission above minimum) | 0.1% (unstaking delay) | 5.4% | 1 | 5.40% | 2-3 days | BASELINE |
| 2 | Top LST (INF) | STRUCTURAL_ENHANCEMENT | 6.44% | 0.1% (protocol fee) | 0.2% (swap friction) | 6.1% | 1.5 | 4.07% | Instant (via Sanctum) | MARGINAL IMPROVEMENT |
| 3 | Mid LST (JitoSOL) | BASE_CARRY | 5.87% | 0.1% | 0.1% | 5.67% | 1.5 | 3.78% | Instant (deep liquidity) | BASELINE |
| 4 | Mid LST (mSOL) | BASE_CARRY | 6.10% | 0.1% | 0.1% | 5.90% | 1.5 | 3.93% | Instant | BASELINE |
| 5 | Bottom LST (BNSOL) | BASE_CARRY | 5.51% | 0.2% (exchange fee) | 0.1% | 5.21% | 2 | 2.61% | Exchange-dependent | WORSE THAN BASELINE |
| 6 | SOL lending (Kamino supply) | BASE_CARRY | 5.36% (30d avg) | 0.1% | 0.3% (utilization risk, rate volatility) | 4.96% | 2 | 2.48% | Instant (if utilization allows) | WORSE THAN STAKING |
| 7 | USDC lending (Kamino) | BASE_CARRY | 5.0% | 0.1% | 0.3% | 4.60% | 2 | 2.30% | Instant | COMPARABLE TO T-BILLS WITH MORE RISK |
| 8 | USDC lending (Loopscale) | BASE_CARRY | 4.2% | 0.1% | 0.2% | 3.90% | 2.5 | 1.56% | Depends on TVL | WORSE THAN T-BILLS |
| 9 | LST-SOL LP (Orca/Meteora) | STRUCTURAL_ENHANCEMENT | 7.0% | 0.2% (LP fees) | 0.5% (smart contract, IL residual) | 6.30% | 2 | 3.15% | Instant | MARGINAL OVER LST ALONE |
| 10 | JLP (Jupiter Perps LP) | STRUCTURAL_ENHANCEMENT | 18.0% | 0.5% (entry/exit fees) | 3.0% (counterparty loss, price decline) | 14.50% | 4 | 3.63% | Instant (deep liquidity) | REAL BUT DANGEROUS |
| 11 | JitoSOL/SOL loop 3x | FAKE_YIELD | 8.0% | 0.3% | 2.0% (rate inversion risk, depeg) | 5.70% | 3.5 | 1.63% | Requires unwind | FAKE — RISK-ADJUSTED WORSE THAN STAKING |
| 12 | JitoSOL/SOL loop 12.5x | FAKE_YIELD | 34.0% | 0.5% | 15.0% (liquidation, rate inversion, depeg) | 18.50% | 5 | 3.70% | Liquidation risk | FAKE — HEADLINE IS MISLEADING |
| 13 | Delta-neutral (funding arb) | STRUCTURAL_ENHANCEMENT | 3.0% (current) | 0.5% (exchange fees) | 1.0% (basis risk, execution) | 1.50% | 3 | 0.50% | Days (unwind positions) | DEAD — YIELDS COLLAPSED |
| 14 | Emissions / points farming | SUBSIDY_HARVEST | 0-50%+ | 0% | High (speculative, may be zero) | Unknown | 4 | Unknown | Varies | PURE SPECULATION |
| 15 | Stablecoin yield (sUSDe) | BASE_CARRY | 3.5% | 0.1% | 0.3% (depeg risk) | 3.10% | 2.5 | 1.24% | Instant | WORSE THAN T-BILLS |
| 16 | T-bill tokenized (sUSD) | BASE_CARRY | 4.3% | 0.1% | 0.1% (redemption) | 4.10% | 1.5 | 2.73% | Days | REFERENCE RATE |
| 17 | Backpack SOL staking + lending | SUBSIDY_HARVEST | 12.0% | 0.2% | 1.0% (promotional, may change) | 10.80% | 3 | 3.60% | Exchange-dependent | LIKELY TEMPORARY |

---

## Classification Summary

### BASE_CARRY (Yield from native protocol mechanics)

Seven opportunities fall into this category: native SOL staking, the mid-tier and bottom-tier LSTs, SOL lending, USDC lending, stablecoin yield products, and tokenized T-bills. These represent the yield that the Solana ecosystem actually produces through inflation issuance and borrower demand. The range is narrow: 3.1% to 5.9% believable net yield. None of these are exciting. All of them are real.

The critical insight is that the entire base carry layer on Solana is funded primarily by inflation, not by fee revenue. The CryptoRank analysis showing a $4.15B net inflation loss confirms this. Staking yield is a transfer from non-stakers to stakers, not value creation. In a declining SOL price environment (SOL fell from approximately $250 to $87 over 2025-2026), a 5.8% staking yield is irrelevant against a 65% price decline.

### STRUCTURAL_ENHANCEMENT (Yield improved through a non-temporary mechanism)

Four opportunities qualify: INF (Sanctum Infinity), LST-SOL LP pools, JLP, and delta-neutral strategies. INF earns a genuine premium from LST swap fees. LST-SOL LP pools earn marginal trading fees on top of staking yield. JLP earns substantial fees from perpetual futures trading. Delta-neutral strategies earn funding rate differentials.

Of these, only JLP offers a meaningfully higher yield than base carry (14.5% believable net versus 5-6% for staking). However, JLP's 36.6% price decline from its all-time high demonstrates that the fee income is compensation for real counterparty risk, not free money. Delta-neutral strategies have collapsed to approximately 1.5% believable net yield, making them essentially dead as a yield source.

### FAKE_YIELD (Advertised yield is misleading)

The leveraged looping strategies (JitoSOL/SOL at 3x and 12.5x) are classified as fake yield. The headline numbers (8% at 3x, 34% at 12.5x) are products of thin spreads amplified by leverage. At 3x leverage, the risk-adjusted yield (1.63%) is worse than simply staking SOL (5.40%). At 12.5x leverage, the liquidation risk is so extreme that the position is better understood as a leveraged bet on spread stability than as a yield strategy. The 34% headline is particularly misleading because it assumes the staking-borrow spread remains positive and stable, which it does not during volatility.

### SUBSIDY_HARVEST (Yield depends on temporary incentives)

Emissions and points farming, along with promotional rates like Backpack's claimed 12% APY, fall into this category. These yields are real in the sense that tokens or promotional rates exist today, but they have known or likely expiration dates. Points programs may never convert to meaningful value. Promotional rates will normalize. Building a yield strategy around subsidies is building on sand.

---

## Risk-Adjusted Yield Ranking

Sorted by risk-adjusted yield (believable net yield divided by risk score), descending:

| Rank | Opportunity | Believable Net Yield | Risk Score | Risk-Adj Yield | Classification |
|------|-------------|---------------------|------------|----------------|---------------|
| 1 | Native SOL staking | 5.40% | 1.0 | 5.40% | BASE_CARRY |
| 2 | INF (Sanctum Infinity) | 6.10% | 1.5 | 4.07% | STRUCTURAL_ENHANCEMENT |
| 3 | mSOL (Marinade) | 5.90% | 1.5 | 3.93% | BASE_CARRY |
| 4 | JitoSOL | 5.67% | 1.5 | 3.78% | BASE_CARRY |
| 5 | JitoSOL/SOL loop 12.5x | 18.50% | 5.0 | 3.70% | FAKE_YIELD |
| 6 | JLP (Jupiter Perps LP) | 14.50% | 4.0 | 3.63% | STRUCTURAL_ENHANCEMENT |
| 7 | Backpack SOL staking | 10.80% | 3.0 | 3.60% | SUBSIDY_HARVEST |
| 8 | LST-SOL LP | 6.30% | 2.0 | 3.15% | STRUCTURAL_ENHANCEMENT |
| 9 | T-bill tokenized | 4.10% | 1.5 | 2.73% | BASE_CARRY |
| 10 | Bottom LST (BNSOL) | 5.21% | 2.0 | 2.61% | BASE_CARRY |
| 11 | SOL lending (Kamino) | 4.96% | 2.0 | 2.48% | BASE_CARRY |
| 12 | USDC lending (Kamino) | 4.60% | 2.0 | 2.30% | BASE_CARRY |
| 13 | JitoSOL/SOL loop 3x | 5.70% | 3.5 | 1.63% | FAKE_YIELD |
| 14 | USDC lending (Loopscale) | 3.90% | 2.5 | 1.56% | BASE_CARRY |
| 15 | Stablecoin yield (sUSDe) | 3.10% | 2.5 | 1.24% | BASE_CARRY |
| 16 | Delta-neutral | 1.50% | 3.0 | 0.50% | STRUCTURAL_ENHANCEMENT |
| 17 | Emissions / points | Unknown | 4.0 | Unknown | SUBSIDY_HARVEST |

---

## Pass/Fail Assessment

The Stage A pass criteria require at least one opportunity with:

1. Believable net yield > 0% after conservative friction estimates
2. Acceptable exitability (exit within 1-3 days without >1% slippage)
3. Risk score <= 3
4. No sole dependence on temporary emissions
5. Realistic for a human-sized operator

**Assessment against criteria:**

| Criterion | Native SOL Staking | INF | mSOL | JitoSOL | JLP | LST-SOL LP |
|-----------|-------------------|-----|------|---------|-----|-----------|
| Net yield > 0% | PASS (5.4%) | PASS (6.1%) | PASS (5.9%) | PASS (5.67%) | PASS (14.5%) | PASS (6.3%) |
| Exitability | PASS (2-3 days) | PASS (instant) | PASS (instant) | PASS (instant) | PASS (instant) | PASS (instant) |
| Risk score <= 3 | PASS (1.0) | PASS (1.5) | PASS (1.5) | PASS (1.5) | FAIL (4.0) | PASS (2.0) |
| Not emission-dependent | PASS | PASS | PASS | PASS | PASS | PASS |
| Human-sized operator | PASS | PASS | PASS | PASS | PASS | PASS |
| **All criteria met** | **YES** | **YES** | **YES** | **YES** | **NO** | **YES** |

Multiple opportunities pass all five criteria. However, the yields are modest: 5.4% to 6.3% for the qualifying opportunities. The only opportunity with materially higher yield (JLP at 14.5%) fails the risk criterion.

---

## The SOL Price Problem

Every SOL-denominated yield surface carries an enormous implicit risk that the yield tables above do not capture: SOL price volatility.

SOL traded at approximately $250 in January 2025 and approximately $87 in March 2026 — a decline of roughly 65%. A staker earning 5.8% APY on SOL during this period earned approximately 5.8% in SOL terms while losing approximately 65% in USD terms. The net USD return was approximately -62%.

This is the single most important fact in the entire yield surface analysis. No Solana yield strategy that is denominated in SOL can be evaluated independently of SOL price risk. The yield is real in SOL terms. The question is whether SOL price risk is acceptable.

For a yield-focused operator, this means:

**If you are SOL-bullish:** Staking or holding an LST is the simplest and most risk-efficient way to earn yield on your SOL position. The incremental yield from more complex strategies (LP, lending, looping) is small relative to the directional SOL bet you are already making.

**If you are SOL-neutral or bearish:** No SOL-denominated yield strategy makes sense. The stablecoin yields on Solana (3-6%) do not compensate for smart contract risk when T-bills yield 4-4.5% with zero smart contract risk. The only Solana-specific yield worth considering is JLP, which has meaningful counterparty risk.

**If you want yield without SOL price exposure:** You should not be looking at Solana yield surfaces at all. T-bills, money market funds, or Ethereum-based stablecoin yields are more appropriate.
