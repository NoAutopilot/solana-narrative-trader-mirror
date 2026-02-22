# Key Findings from arXiv Paper: Predicting Pump.fun Token Success (Feb 2026)

## Core Insight
- Only ~0.6% of pump.fun tokens "graduate" (reach the bonding curve threshold)
- The paper treats graduation as a binary, protocol-defined outcome
- They build CONDITIONAL probability models: given current bonding curve state + behavioral variables

## What Predicts Success (their conditioning variables):
1. Bot/algorithmic trading intensity
2. Speed of liquidity accumulation (SOL locked per number of trades)
3. Early participation of historically successful traders
4. Identity and behavior of prolific token creators

## Key Finding:
"Fast accumulation of liquidity through a small number of trades is the strongest predictor of graduation"
- This means: tokens where a few big buyers push liquidity fast are more likely to succeed
- NOT tokens with lots of small retail buyers

## Implication for Our System:
- We're not tracking ANY of these signals
- We don't look at bonding curve state
- We don't track who is buying (smart money vs retail)
- We don't measure liquidity accumulation speed
- We're purely matching on token names to news headlines

## Pump.fun Stats:
- 0.4% of wallets made >$10k profit (Dune Analytics, Jan 2025)
- 294 wallets became millionaires out of 13.4M
- 42% lost money, 55% made under $500 (Jan 2026 PumpFun stats)
- 88% of Uniswap v2 tokens in late 2024 were manipulation schemes
