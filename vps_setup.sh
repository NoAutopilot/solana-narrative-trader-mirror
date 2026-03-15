#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Solana Narrative Trader — VPS Setup Script
# Run this on a fresh Ubuntu 22.04 VPS (Hetzner CX22 recommended)
# ═══════════════════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  Solana Narrative Trader — VPS Setup"
echo "═══════════════════════════════════════════════════════════"

# 1. System dependencies
echo "[1/6] Installing system dependencies..."
sudo apt-get update -y && sudo apt-get install -y python3 python3-pip git screen

# 2. Clone the repo
echo "[2/6] Cloning repository..."
cd ~
if [ -d "solana_trader" ]; then
    echo "  Directory exists, pulling latest..."
    cd solana_trader && git pull origin master && cd ~
else
    git clone https://github.com/NoAutopilot/solana-narrative-trader.git solana_trader
fi

# 3. Install Python dependencies
echo "[3/6] Installing Python dependencies..."
cd ~/solana_trader
pip3 install -r requirements.txt
pip3 install python-dotenv

# 4. Create .env file
echo "[4/6] Creating .env file..."
cat > ~/solana_trader/.env << 'EOF'
# ── Helius RPC ──
HELIUS_RPC_URL=REDACTED

# ── Wallet ──
WALLET_ADDRESS=REDACTED
SOLANA_PRIVATE_KEY=REDACTED

# ── PumpPortal Lightning API ──
PUMPPORTAL_API_KEY=REDACTED

# ── Live Trading (OFF by default — paper only) ──
LIVE_ENABLED=false
LIVE_TRADE_SIZE_SOL=0.005
LIVE_SLIPPAGE_PCT=20
LIVE_PRIORITY_FEE=0.0001
EOF

# 5. Create data and logs directories
echo "[5/6] Creating directories..."
mkdir -p ~/solana_trader/data
mkdir -p ~/solana_trader/logs

# 6. Create systemd service for auto-restart on reboot
echo "[6/6] Creating systemd service..."
sudo tee /etc/systemd/system/solana-trader.service > /dev/null << EOF
[Unit]
Description=Solana Narrative Trader
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/solana_trader
ExecStart=/usr/bin/python3 $HOME/solana_trader/supervisor.py
Restart=always
RestartSec=10
Environment=HOME=$HOME

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable solana-trader
sudo systemctl start solana-trader

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  SETUP COMPLETE"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Status:    sudo systemctl status solana-trader"
echo "  Logs:      journalctl -u solana-trader -f"
echo "  Stop:      sudo systemctl stop solana-trader"
echo "  Restart:   sudo systemctl restart solana-trader"
echo ""
echo "  Dashboard: http://<YOUR_VPS_IP>:5050"
echo ""
echo "  Config:    ~/solana_trader/config/config.py"
echo "  Database:  ~/solana_trader/data/solana_trader.db"
echo "  Env:       ~/solana_trader/.env"
echo ""
echo "  LIVE TRADING IS OFF. To enable:"
echo "  1. Edit .env: LIVE_ENABLED=true"
echo "  2. sudo systemctl restart solana-trader"
echo ""
echo "  Current settings:"
echo "  - Timeout: 5 minutes (optimized)"
echo "  - TP: 30% | SL: -25%"
echo "  - Trade size: 0.04 SOL (paper)"
echo "  - Max concurrent: 50"
echo "═══════════════════════════════════════════════════════════"
