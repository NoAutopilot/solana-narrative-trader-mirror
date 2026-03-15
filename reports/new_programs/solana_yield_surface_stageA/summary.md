# Solana Yield Surface Map — Stage A Summary and Verdict

**Program:** solana_yield_surface_stageA
**Date:** 2026-03-15
**Author:** Manus AI
**Status:** COMPLETE — STAGE A VERDICT ISSUED

---

## Executive Summary

This program mapped every major Solana yield surface — native staking, liquid staking tokens, lending, LP pools, leveraged looping, JLP, delta-neutral strategies, emissions, and stablecoin yield — against real data collected in March 2026. Each opportunity was classified as BASE_CARRY, STRUCTURAL_ENHANCEMENT, SUBSIDY_HARVEST, or FAKE_YIELD, and scored on gross yield, fee drag, friction, believable net yield, risk, and risk-adjusted yield.

The findings are clear and sobering. The Solana yield landscape in March 2026 is dominated by a narrow band of base carry between 5.2% and 6.3% for qualifying (low-to-moderate risk) opportunities. The only materially higher yield comes from JLP at approximately 14.5% net, which carries substantial counterparty risk (risk score 4/5) and has already demonstrated a 36.6% price decline from its all-time high. Leveraged looping strategies advertise 34% yields but are classified as FAKE_YIELD because the headline number is a thin spread amplified by extreme leverage with liquidation risk. Delta-neutral strategies have collapsed to approximately 1.5% net yield, making them functionally dead. Emissions and points programs are pure speculation.

**The honest answer is that Solana's yield surface does not contain a compelling opportunity that justifies building a dedicated yield business around it, given the user's constraints.**

---

## Adversarial Analysis

### What the yield surface actually tells us

The entire Solana base yield layer — staking, LSTs, lending — is funded primarily by inflation, not by productive economic activity. The CryptoRank analysis from March 2026 found that Solana's inflation issuance exceeds fee revenue by $4.15 billion [1]. This means staking yield is a wealth transfer from non-stakers to stakers, not value creation. The yield is real in nominal terms, but it is not "earned" in the way that, say, lending interest from real borrowers is earned.

At a current inflation rate of 3.957% and a staking ratio of 68.13%, the gross staking yield is approximately 5.81% [2]. After validator commissions, net yield to delegators is 5.2-5.5% for bottom-tier LSTs and 6.1-6.4% for top-tier LSTs that capture MEV tips and trading fees [3]. The spread between the best and worst LST is only 1.07 percentage points. This is not a surface with large inefficiencies to exploit.

### Why the headline numbers are misleading

Three categories of Solana yield are systematically overstated in public-facing dashboards and marketing materials.

**Leveraged looping** is the most egregious offender. Kamino Multiply displays a 34.17% APY for JitoSOL/SOL looping at 12.5x leverage [4]. This number is the product of a staking-minus-borrow spread of approximately 0-2% multiplied by 12.5. The display does not prominently communicate that: (a) the spread can and does invert during volatility when SOL borrow rates spike; (b) a JitoSOL/SOL depeg of 2-3% triggers liquidation; and (c) the position requires active monitoring. At 3x leverage, the risk-adjusted yield (1.63%) is actually worse than simply staking SOL (5.40%). The leverage amplifies the headline but destroys the risk-adjusted return.

**JLP** is more honest but still misleading. The 17-20% APY from fee income is real, but JLP's price has fallen from $5.99 to $3.80 — a 36.6% decline [5]. A holder who entered at the peak has a net return of approximately -20% despite the fee income. JLP holders are the counterparty to perpetual futures traders. When traders collectively profit, JLP loses value. The fee income is compensation for bearing this risk, not a bonus on top of a stable asset. JLP is better understood as "selling insurance to leveraged traders" than as "earning yield."

**Emissions and points** are the most speculative category. Protocols display estimated APY figures that include the speculative value of unreleased tokens. These numbers can range from 10% to 50%+ but have no guaranteed conversion to real value. Many points programs in 2024-2025 resulted in token launches with disappointing prices, and several never launched tokens at all.

### Why the SOL price problem dominates everything

SOL traded at approximately $250 in January 2025 and approximately $87 in March 2026 — a decline of roughly 65% [6]. A staker earning 5.8% APY on SOL during this period earned approximately 5.8% in SOL terms while losing approximately 65% in USD terms. The net USD return was approximately -62%.

This single fact overwhelms every yield calculation in this report. No Solana yield strategy that is denominated in SOL can be evaluated independently of SOL price risk. The yield is real in SOL terms. But the question of whether to hold SOL at all is a directional market view, not a yield decision. If you are wrong about SOL's price direction, no yield strategy saves you. If you are right about SOL's price direction, the yield is a rounding error compared to the capital gain.

This means the yield surface analysis is only decision-relevant for someone who has already decided to hold SOL for other reasons and is asking: "Given that I am holding SOL anyway, what is the best way to earn yield on it?" For that person, the answer is straightforward and does not require a Stage B program.

### Why most "complex" strategies are worse than simple staking

The risk-adjusted yield ranking reveals a counterintuitive result: the simplest strategy (native SOL staking) has the highest risk-adjusted yield at 5.40%. Every more complex strategy either adds risk faster than it adds yield, or adds yield that is illusory.

Holding INF (Sanctum Infinity) at 6.1% net yield and 1.5 risk score produces a risk-adjusted yield of 4.07% — lower than native staking's 5.40%. The additional yield from INF's swap fee revenue (approximately 0.7% above native staking) does not fully compensate for the additional smart contract risk of the Sanctum protocol.

LST-SOL LP pools produce approximately 6.3% net yield at a risk score of 2.0, for a risk-adjusted yield of 3.15%. The marginal trading fee income (0.5-2%) does not justify the additional smart contract exposure to the DEX.

The only strategy that produces a meaningfully higher absolute yield is JLP at 14.5% net, but its risk score of 4.0 brings the risk-adjusted yield to 3.63% — still below native staking. And JLP's demonstrated price decline shows that the risk score of 4.0 may even be generous.

### What about stablecoin yield?

Stablecoin yields on Solana range from 3.1% (sUSDe) to 5.0% (Kamino USDC lending). US Treasury bills currently yield approximately 4.0-4.5% with zero smart contract risk [7]. This means most Solana stablecoin yields are at or below the risk-free rate. The only Solana stablecoin yields that exceed T-bill rates do so by a margin (0.5-1.0%) that does not obviously compensate for smart contract risk, oracle risk, and utilization risk.

A rational yield-seeking operator with access to T-bills has no reason to deploy stablecoins into Solana DeFi unless they are also earning emissions or points, which are speculative and temporary.

---

## Stage A Verdict

### Do any opportunities pass the Stage A criteria?

Yes. Multiple opportunities pass the five-part test: native SOL staking, INF, mSOL, JitoSOL, and LST-SOL LP pools all have positive believable net yield, acceptable exitability, risk scores at or below 3, no dependence on temporary emissions, and are accessible to a human-sized operator.

### Does this justify a Stage B program?

**No.**

The opportunities that pass the criteria are all simple, well-understood, and do not require a dedicated research program to execute. The optimal strategy for someone who has decided to hold SOL is:

1. **Hold a top-tier LST** (INF at 6.44% gross, or JupSOL/mSOL at 6.1-6.2% gross) to earn staking yield while maintaining liquidity.
2. **Optionally LP the LST against SOL** on Orca or Meteora for a marginal 0.5-2% fee income, if comfortable with the additional smart contract exposure.
3. **Do not loop, do not leverage, do not chase emissions.**

This is a five-minute decision, not a research program. There is no edge to discover, no inefficiency to exploit, and no complexity that rewards deeper analysis. The yield surface is well-arbitraged, transparent, and narrow.

### What about JLP?

JLP is the only opportunity with a materially higher yield (14.5% net) than the base carry layer. It is a legitimate structural enhancement — the fee income from Jupiter's perpetual futures exchange is real and substantial. However, JLP fails the risk criterion (risk score 4/5) and has demonstrated significant price decline. A Stage B program focused on JLP would need to answer: "Can I time entry and exit to capture fee income while avoiding periods of trader profitability that erode JLP value?" This is essentially a market-timing question, which is a different kind of research than yield optimization.

If the user is interested in JLP specifically, a separate, narrowly scoped investigation into JLP's historical drawdown patterns and trader P&L dynamics would be more appropriate than a broad yield Stage B program.

### What about building a yield product for others?

The most interesting business opportunity in this space is not earning yield yourself but building tools or products that help others navigate the yield surface. The analysis in this report — classifying yields, computing risk-adjusted returns, identifying fake yield — is the kind of work that most retail participants do not do. A product that performs this analysis automatically and presents it clearly could have value. This connects to the "Research / Falsification / Anti-Bullshit Engine" arena identified in the Solana Profit Arena Map.

---

## Final Determination

| Question | Answer |
|----------|--------|
| Is there a compelling Solana yield opportunity? | No, for a dedicated yield business. Yes, for simple staking if already holding SOL. |
| Does Stage A recommend Stage B? | **NO** |
| Best simple action if holding SOL | Hold INF or JupSOL (6.1-6.4% gross yield) |
| Best complex action if risk-tolerant | JLP (14.5% net, but 4/5 risk and demonstrated drawdowns) |
| Worst action | Leveraged looping at 12.5x (FAKE_YIELD, liquidation risk) |
| Should you chase emissions/points? | No, unless you are already using the protocol for other reasons |
| Should you deploy stablecoins on Solana? | No, T-bills are better risk-adjusted |
| Is there a yield-adjacent business opportunity? | Yes — yield classification and risk analysis as a product |

---

## Recommended Next Move

Do not launch a Stage B yield optimization program. Instead, if the user is holding SOL, execute the simple strategy (hold a top-tier LST) and redirect research effort toward the higher-value arenas identified in the Profit Arena Map — specifically the Research/Falsification/Strategy Audit Service, which could incorporate yield surface analysis as one of its product offerings.

---

## References

[1]: CryptoRank, "Solana's Staggering $4.15B Loss: Inflation Outpaces Fee Revenue," March 2026. https://cryptorank.io/news/feed/218c3-solana-inflation-loss-analysis-kaiko

[2]: SolanaCompass, "Solana Tokenomics: Circulating Supply, Inflation Schedule." https://solanacompass.com/tokenomics

[3]: Sanctum, "Solana Liquid Staking Yields Ranked: Which LST Pays The Most In 2026," January 2026. https://sanctum.so/blog/solana-liquid-staking-yields-ranked-highest-paying-lsts-2026

[4]: Kamino Finance, Multiply page. https://kamino.com/multiply

[5]: CoinMarketCap, Jupiter Perps LP (JLP) price data. https://coinmarketcap.com/currencies/jupiter-perps-lp/

[6]: Various price sources; SOL price approximately $87 as of March 2026 per MetaMask, WazirX, and exchange data.

[7]: US Treasury yield curve; 3-month T-bill yield approximately 4.0-4.5% as of March 2026.
