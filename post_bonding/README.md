# Post-Bonding Paper Trader

Parallel paper trading system for tokens that have graduated from pump.fun's bonding curve (250k+ mcap).

## Architecture

1. **PumpPortal WebSocket** → Listens for `migration` events (token graduation)
2. **Watchlist Monitor** → Tracks graduated tokens via DexScreener API for 30 minutes
3. **Entry Logic** → When a token crosses $250k mcap with $50k+ liquidity, enters paper trades
4. **5 Strategy Variants** → A/B testing different TP/SL/trailing/timeout parameters
5. **Position Manager** → Monitors open trades and executes exits

## Strategy Variants

| Strategy | TP | SL | Trailing | Timeout | Entry Filter |
|---|---|---|---|---|---|
| A_momentum | +100% | -30% | Activate 50%, Distance 20% | 15min | Volume acceleration > 2x |
| B_breakout | +200% | -25% | Activate 80%, Distance 30% | 30min | Breakout pattern |
| C_conservative | +50% | -15% | Activate 30%, Distance 10% | 10min | Holder growth |
| D_aggressive | +500% | -40% | Activate 150%, Distance 40% | 60min | Any graduated |
| E_scalper | +30% | -10% | None | 5min | Fast momentum |

## Files

- `post_bonding_config.py` — Configuration and strategy parameters
- `post_bonding_db.py` — SQLite database for trades, tokens, and price snapshots
- `post_bonding_trader.py` — Main trader process (systemd service)

## Deployment

Runs as `post-bonding.service` alongside the existing `solana-trader.service` on the VPS.

```bash
systemctl status post-bonding.service
journalctl -u post-bonding.service -f
```

## Data Collection

Even when no tokens qualify for paper trading (most don't reach 250k), the system collects:
- Graduation events (mint, pool, timestamp)
- Price snapshots every ~30 seconds for 30 minutes post-graduation
- Peak mcap tracking for each graduated token

This data answers: "What % of graduated tokens reach 250k? How fast? What signals predict it?"
