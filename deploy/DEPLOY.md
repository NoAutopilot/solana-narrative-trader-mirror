# Deployment Guide

## Environment Setup

All secrets are loaded from `/root/solana_trader/trader_env.conf` via systemd `EnvironmentFile`.
This file is **never committed to the repo**.

### First-time setup

```bash
# 1. Copy the example env file
cp .env.example /root/solana_trader/trader_env.conf

# 2. Fill in real values (rotate all keys before use if the repo was ever public)
nano /root/solana_trader/trader_env.conf

# 3. Restrict permissions
chmod 600 /root/solana_trader/trader_env.conf

# 4. Install the systemd service
cp deploy/solana-trader.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable solana-trader
systemctl start solana-trader
```

### Key rotation checklist (required if repo was ever public)

- [ ] Rotate Helius API key at https://dashboard.helius.dev
- [ ] Rotate Jupiter API key at https://portal.jup.ag
- [ ] Rotate PumpPortal API key at https://pumpportal.fun
- [ ] Move all funds to a fresh wallet (old private key is burned)
- [ ] Update `/root/solana_trader/trader_env.conf` with new keys
- [ ] Restart the service: `systemctl restart solana-trader`

### Startup validation

The strategy will fail fast on startup if `LIVE_TRADING_ENABLED=true` and any required
environment variable is missing. Check `journalctl -u solana-trader -f` for errors.
