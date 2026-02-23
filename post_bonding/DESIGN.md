# Post-Bonding System Design

## Architecture

The post-bonding system runs as a SEPARATE process alongside the existing paper_trader.
It uses its own SQLite database to avoid any interference with the lottery-ticket system.

### Components:
1. `post_bonding_trader.py` — Main process: discovers graduated tokens, collects signals, paper trades
2. `post_bonding_config.py` — Configuration for the post-bonding system
3. Database: `/root/solana_trader/data/post_bonding.db` — Separate from main DB

### Discovery Method:
- DexScreener API: Poll `/latest/dex/tokens/` for Solana tokens
- Filter: mcap >= 250k, pair age < 60 minutes, volume > threshold
- Also: PumpPortal WebSocket already shows graduation events — can tap into that

### Parallel Strategy Variants (paper trade all simultaneously):
Each discovered token gets paper-entered under MULTIPLE strategy variants to find the best approach.

| Strategy | Entry Signal | TP | SL | Timeout | Trail |
|---|---|---|---|---|---|
| A_momentum | Volume > 2x avg, mcap rising | 50% | -10% | 30min | 15% from peak |
| B_breakout | Mcap crosses 250k with volume spike | 100% | -15% | 60min | 20% from peak |
| C_conservative | Holder count growing + no dump detected | 30% | -8% | 15min | 10% from peak |
| D_aggressive | Any graduation + volume > threshold | 200% | -20% | 120min | 25% from peak |
| E_scalper | Fast price increase in first 2 min post-grad | 15% | -5% | 5min | None |

### Data Collection (Phase 1 — always on):
For EVERY graduated token, regardless of whether we paper-trade it:
- Price snapshots every 30s for 30 minutes
- Volume in 1-min buckets
- Holder count at 1, 5, 10, 30 min (if Helius rate allows)
- Creator wallet activity (sell detection)
- Peak price and time to peak

### Signal Set:
1. Volume acceleration (DexScreener: 5m volume vs 1m volume)
2. Price momentum (positive candle streak)
3. Holder growth rate (Helius getTokenLargestAccounts)
4. Top holder concentration (top 10 holders % of supply)
5. Creator dump detection (large sells from creator wallet)
6. Mcap threshold crossings (250k, 500k, 1M)

### Database Schema:
- `graduated_tokens` — every token that graduates, with signal data
- `post_bonding_trades` — paper trades with strategy variant
- `price_snapshots` — time series price data for analysis
