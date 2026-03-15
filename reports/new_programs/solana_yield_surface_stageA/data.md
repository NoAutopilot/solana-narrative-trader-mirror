# Solana Yield Surface Map — Stage A Data Collection

**Program:** solana_yield_surface_stageA
**Date:** 2026-03-15
**Status:** COMPLETE

---

## Data Sources

| Source | Type | Date | URL |
|--------|------|------|-----|
| Sanctum Blog | LST yield rankings (10-epoch APY) | 2026-01-06 | sanctum.so/blog |
| StakingRewards | Native SOL staking APY | 2026-03-15 | stakingrewards.com |
| Helius | Validator staking rewards | 2026-03-15 | helius.dev/staking/rewards |
| Solana.com | Inflation schedule, staking basics | Evergreen | solana.com/learn |
| SolanaCompass | Inflation rate, tokenomics | 2026-03-15 | solanacompass.com/tokenomics |
| DeFiLlama | Kamino SOL pool APY, lending TVL | 2026-03-15 | defillama.com |
| DeFiRate | Lending protocol comparison | 2026-03-15 | defirate.com/lend |
| Kamino.com | Multiply vault displayed APYs | 2026-03-15 | kamino.com/multiply |
| Kamino Governance | Jito Market parameters, SOL rate caps | Various | gov.kamino.finance |
| CryptoRank | Solana inflation vs fee revenue analysis | 2026-03-11 | cryptorank.io |
| Reddit / X | JLP APY discussion, delta-neutral yields | Various | Various |
| CoinMarketCap | JLP price history | 2026-03-15 | coinmarketcap.com |
| Blockworks Research | DEX order flow, prop AMM dynamics | 2026-01-05 | blockworksresearch.com |

---

## Category 1: Native SOL Staking

Solana's inflation rate stands at 3.957% per year, declining 15% annually toward a 1.5% floor. With a staking ratio of 68.13%, the gross staking yield is approximately 3.96% / 0.6813 = 5.81%. After typical validator commissions of 5-10%, net yield to delegators is approximately 5.2-5.5%. Epoch rewards are paid every 2-3 days and auto-compound if left staked. Native staking requires a ~2-3 day unstaking period.

**Key data point:** The CryptoRank analysis (March 2026) found that Solana's inflation creates a $4.15B net loss — inflation issuance exceeds fee revenue. This means the majority of staking yield is funded by dilution of non-stakers, not by productive economic activity on the network.

---

## Category 2: Liquid Staking Tokens

Data from Sanctum's ranking (January 6, 2026) covering all LSTs with >1M SOL staked:

| Token | 10-Epoch APY | SOL Staked | Holders | Yield Source |
|-------|-------------|-----------|---------|--------------|
| INF (Sanctum Infinity) | 6.44% | 1.9M | 42,877 | Staking + LST swap fees |
| dSOL (Drift) | 6.36% | 1.7M | 5,102 | Staking + 100% validator fees |
| fwdSOL (Forward Industries) | 6.27% | 1.7M | 55 | Staking (institutional) |
| JupSOL (Jupiter) | 6.16% | 4.7M | 30,080 | Staking + MEV |
| mSOL (Marinade) | 6.10% | 3.4M | 148,663 | Staking (100+ validators) |
| bbSOL (Bybit) | 5.93% | 1.8M | 11,471 | Staking (exchange-backed) |
| JitoSOL (Jito) | 5.87% | 14.3M | 192,514 | Staking + MEV tips |
| bSOL (BlazeStake) | 5.79% | 1.0M | 57,197 | Staking (200+ validators) |
| dzSOL (DoubleZero) | 5.78% | 13.2M | 12,202 | Staking (fiber network) |
| JSOL (JPOOL) | 5.77% | 1.2M | 3,633 | Staking + MEV (bloXroute) |
| aeroSOL | 5.67% | 1.0M | 236 | Staking |
| vSOL (The Vault) | 5.55% | 1.5M | 6,547 | Staking |
| BNSOL (Binance) | 5.51% | 10.7M | 13,440 | Staking (exchange-backed) |
| xSHIN (Shinobi) | 5.37% | 1.0M | 101 | Staking |

The spread between the best LST (INF at 6.44%) and worst (xSHIN at 5.37%) is 1.07 percentage points. INF's premium comes from its dual revenue structure: staking rewards plus trading fees earned when users swap between LSTs in the Sanctum Infinity pool.

---

## Category 3: Lending Markets

Kamino Lend is the largest Solana lending protocol with $3.2B supplied and $1.2B borrowed (37.4% utilization). Jupiter Lend is second at $1.8B supplied.

| Protocol | Asset | Supply APY (current) | Supply APY (30d avg) | Borrow APY | TVL |
|----------|-------|---------------------|---------------------|------------|-----|
| Kamino | SOL | 9.59% (spike) | 5.36% | ~6-8% | $18.87M (SOL pool) |
| Kamino | USDC | ~4-6% | ~4-5% | ~6-10% | Large |
| marginfi | SOL | ~0.19% (base) + 5.81% staking | N/A | ~2.80% | N/A |
| Loopscale | USDC | 4.2% | N/A | N/A | $6.6M |
| Backpack | SOL | ~12% claimed | N/A | N/A | N/A |

**Critical observation:** The SOL supply rate on lending protocols (30d average ~5.36%) is lower than the native staking yield (~5.8-6.0%). This means lending SOL is strictly worse than staking it, unless the lending protocol also passes through staking yield (as marginfi does by combining base lending rate + staking APY).

---

## Category 4: LST LP Pools

LST-SOL liquidity pools have minimal impermanent loss because the assets are highly correlated (an LST tracks SOL price plus accrued staking yield). Fee income from these pools is typically low because the trading volume is modest relative to TVL.

| Pool | Venue | Estimated APY | TVL | Notes |
|------|-------|--------------|-----|-------|
| mSOL-JLP | Orca | 1.73% | $50.9K | Very low TVL and yield |
| SOL-JitoSOL | Orca/Meteora | ~6-8% | Varies | Staking yield + small fees |
| SOL-mSOL | Orca/Meteora | ~6-8% | Varies | Staking yield + small fees |
| Generic LST-SOL | Various | ~6.5-8% | Varies | Marginal improvement over holding LST |

The incremental yield from LP-ing an LST against SOL (versus simply holding the LST) is approximately 0.5-2% from trading fees, with the risk of smart contract exposure to the LP venue.

---

## Category 5: JLP (Jupiter Perpetuals LP)

JLP is the liquidity pool backing Jupiter's perpetual futures exchange. JLP holders earn 75% of all perps trading fees. Jupiter generates approximately $46.5M in monthly perps fees.

| Metric | Value | Source |
|--------|-------|--------|
| Displayed APY | 17-20% | Reddit (Aug 2025), Jupiter (Sep 2025) |
| TVL | $2B+ | Jupiter (Sep 2025) |
| Composition | SOL, BTC, ETH, USDC, USDT | Weighted basket |
| Price (current) | $3.80 | CoinMarketCap (Mar 2026) |
| Price (ATH) | $5.99 | CoinMarketCap |
| Price decline from ATH | -36.6% | Calculated |
| Fee source | 75% of Jupiter perps fees | Jupiter docs |

**Critical observation:** Despite the 17-20% APY from fee income, JLP's price has declined from $5.99 to $3.80 (a 36.6% loss). This means a holder who bought at the peak has lost far more in price depreciation than they earned in fees. JLP holders are the counterparty to perpetual futures traders — when traders profit, JLP loses value. The fee income is compensation for bearing this counterparty risk, not "free yield."

---

## Category 6: Leveraged / Looped Strategies

Kamino Multiply offers automated looping of JitoSOL/SOL positions with up to 12.5x leverage in the Jito Market (90% LTV).

| Parameter | Value |
|-----------|-------|
| Displayed APY | 34.17% |
| Max leverage | 12.5x |
| TVL | $4.76M |
| Mechanism | Deposit JitoSOL → borrow SOL → buy JitoSOL → repeat |
| Base spread | JitoSOL staking APY (~5.87%) minus SOL borrow rate (~4-6%) |
| Net spread per turn | ~0-2% |
| Leveraged yield | 0-2% x 12.5 = 0-25% |
| Liquidation trigger | JitoSOL/SOL depeg of ~2-3% |

**Critical observation:** The 34% displayed APY is the product of a thin spread (~0-2%) amplified by extreme leverage (12.5x). If the SOL borrow rate spikes above the JitoSOL staking rate (which happens during volatility), the spread inverts and the position bleeds money at 12.5x the rate. If JitoSOL depegs from SOL by even 2-3%, the position is liquidated. This is not a yield strategy — it is a leveraged bet on spread stability.

---

## Category 7: Emissions / Points / Airdrop Speculation

| Program | Status | Estimated Value | Notes |
|---------|--------|----------------|-------|
| Kamino points | Active (no token yet) | Speculative | KMNO mentioned but unclear |
| Meteora points | Active | Speculative | MET token launched but low value |
| Backpack airdrop | Speculative | Unknown | Exchange running points program |
| Sanctum CLOUD | Airdrop completed 2024 | N/A | Past event |
| Various protocol points | Active | 0-50%+ speculative | Depends entirely on token launch and price |

Emissions and points programs are by definition temporary. Their value is speculative until a token launches and has a market price. Many points programs never convert to meaningful value.

---

## Category 8: Stablecoin Yield

| Opportunity | APY | Source of Yield | Risk |
|-------------|-----|-----------------|------|
| USDC lending (Kamino) | 4-6% | Borrower interest | Smart contract, utilization |
| USDC lending (Loopscale) | 4.2% | Borrower interest | Smart contract, small TVL |
| sUSDe (Ethena on Solana) | ~3.5% | Funding rate arb | Basis risk, depeg risk |
| Perena stablecoin yield | ~15% | Unclear mechanism | High for stablecoin = suspicious |
| T-bill tokenized (sUSD etc) | 4-5% | US Treasury yield | Regulatory, redemption |

**Critical observation:** US Treasury bills currently yield approximately 4.0-4.5%. Any Solana stablecoin yield below this rate is strictly worse than holding T-bills (which have zero smart contract risk). Stablecoin yields above T-bill rates on Solana must be compensating for smart contract risk, utilization risk, or are subsidized.

---

## Category 9: Delta-Neutral Strategies

Delta-neutral strategies attempt to earn yield while hedging directional exposure. On Solana, this typically means holding a long spot position and shorting the same asset on a perps exchange, earning the funding rate.

| Strategy | Trailing 12M APY | Current 7d APY | Trend |
|----------|-----------------|----------------|-------|
| Solstice delta-neutral | 14.8% | ~3% | Compressing |
| YieldVault delta-neutral | ~8% | Unknown | Compressing |
| Generic funding rate arb | 6.2% (Q4 2024) → 1.1% (Q4 2025) | ~1-3% | Severely compressed |

Delta-neutral yields have collapsed from 6-15% in 2024 to 1-3% in early 2026. This compression is structural: as more capital enters the trade, funding rates normalize and the yield disappears. The "number every delta-neutral strategy doesn't want to show you" is that current yields barely exceed T-bill rates, with far more complexity and risk.
