# Discovery Method Findings

## PumpPortal Migration Events
- `subscribeMigration` works — gives us real-time graduation events
- Events contain: signature, mint, txType="migrate", pool="pump-amm"
- Events arrive every ~1-2 minutes (2 in ~2 minutes)
- Graduated tokens start at ~$30k mcap (not 250k!)
- They're on pumpswap/pumpfun DEX initially

## Key Insight: 250k is NOT graduation mcap
- Tokens graduate from bonding curve at ~$30k mcap
- 250k mcap is a LATER milestone — tokens need to pump 8x post-graduation to reach it
- This means we need TWO approaches:
  1. **Catch at graduation** (~30k) and track which ones reach 250k (data collection)
  2. **Enter at 250k+** when momentum confirms (the actual strategy)

## Revised Architecture
- Listen to PumpPortal migration events for ALL graduations
- Track each graduated token's price via DexScreener
- When a token crosses 250k mcap with volume, THEN enter paper trades
- This gives us the full picture: graduation → 250k journey data

## DexScreener Data Quality
- Pairs show up immediately on DexScreener after graduation
- Price, volume, tx counts all available
- pumpswap pairs have liquidity data; pumpfun pairs show $0 liquidity
- Use pumpswap pair for price data (it has real liquidity)

## Filter Adjustments Needed
- Lower MIN_MCAP to $50k for data collection (track everything)
- Keep 250k threshold for paper trade ENTRY
- Add a "watch" state between discovery and trade entry
