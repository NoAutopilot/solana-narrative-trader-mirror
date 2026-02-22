# Research Notes: What Actually Works in Pump.fun Trading

## Key Findings from External Research

### Ave.ai (tested 30+ tools, hundreds of trades):
- Meme coin trading = attention arbitrage. You trade emotion and narrative, not fundamentals.
- Two schools: tech-driven (follow whales, buy high) vs market-driven (predict attention, buy low)
- **Twitter scraping is the #1 strategy** — catching CA drops and shill surges in real-time
- Smart money tools are LAGGING indicators — by the time whales buy, you're exit liquidity
- The "composite signal" approach: stack Twitter momentum + fresh token renaming + KOL first tweets + Telegram shill surge + smart money inflow. When 3+ align, probability spikes.
- **Alpha decay is real** — the more people use a strategy, the faster it loses edge
- Celebrity/mainstream CA drops = cleanest alpha (2x-10x in minutes)
- Post-hype fair launches = more scalable (narrative breaks, THEN fair launch appears)

### Reddit consensus (r/solana):
- "The only people who make constant profit are insider groups who work together with devs"
- Copy trading is a trap — whales know you're copying them, you're their exit liquidity
- "99% of people who profit hold established ones for months — anything else is pure gambling"
- Key advice: $5 per trade not $50, take notes, build a system over time

### Bitquery slippage analysis:
- Most trades have <10 bps slippage, but extreme tails hit 5000+ bps
- Sandwich attacks are confirmed on pump.fun — bots front-run trades
- Stable tokens (moonpig, Costco) had ~15-30 bps average slippage
- Volatile tokens (catwifmask) had 62+ bps average with 5000+ bps outliers
- **Implication: our 8% fee model may be optimistic for low-liquidity tokens**

### Academic research:
- Only 0.4% of pump.fun wallets realize gains (from legal analysis paper)
- Market manipulation is systematic: wash trading bots + social media trolling bots
- Copy trading has a multi-agent adversarial dynamic — bots manipulate copy traders

## What This Means for Our System

### Our current approach (RSS → narrative → keyword match → buy):
- We're doing a SLOW version of Twitter scraping (RSS feeds update every 15 min)
- We're matching on token NAMES, not contract addresses or social signals
- We have zero social signal integration (no Twitter, no Telegram, no KOL tracking)
- We're not tracking smart money flow at all
- We're buying at random timing relative to the narrative (could be hours late)

### What profitable traders actually do differently:
1. **Speed**: Real-time Twitter/social monitoring, not 15-min RSS
2. **Precision**: Track specific CAs, not fuzzy keyword matching on token names
3. **Social proof**: KOL mentions, Telegram shill count, Twitter engagement metrics
4. **Smart money confirmation**: Check if known profitable wallets are buying
5. **Selectivity**: Only trade when 3+ signals converge, not on any keyword match
6. **Position sizing**: $5-10 per trade, not $50 (we're at 0.04 SOL ≈ $6, this is right)
