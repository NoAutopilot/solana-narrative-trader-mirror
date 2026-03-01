"""
Post-Bonding Trader Configuration
──────────────────────────────────
Configuration for the graduated token (250k+ mcap) paper trading system.
Runs alongside the existing lottery-ticket paper trader.
"""
import os

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
LOGS_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs")
DB_PATH = os.path.join(DATA_DIR, "post_bonding.db")

# ── API Endpoints ────────────────────────────────────────────────────────────
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens/"
DEXSCREENER_PAIRS_URL = "https://api.dexscreener.com/latest/dex/pairs/solana/"
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search/"
DEXSCREENER_NEW_PAIRS_URL = "https://api.dexscreener.com/token-profiles/latest/v1"

# PumpPortal for graduation events
PUMPPORTAL_WS_URL = "<REDACTED_WSS>/api/data"

# Helius RPC for holder data
HELIUS_RPC_URL = os.environ.get(
    "HELIUS_RPC_URL",
    "https://mainnet.<REDACTED_HELIUS>/?api-key=<REDACTED>"
)

# ── Discovery Filters ────────────────────────────────────────────────────────
MIN_MCAP_USD = 250_000          # Minimum market cap to consider
MAX_MCAP_USD = 10_000_000       # Maximum market cap (avoid established tokens)
MIN_LIQUIDITY_USD = 50_000      # Minimum liquidity
MAX_PAIR_AGE_MINUTES = 120      # Only tokens that graduated in last 2 hours
MIN_VOLUME_5M_USD = 10_000      # Minimum 5-minute volume
MIN_TX_COUNT_5M = 50            # Minimum transactions in 5 minutes

# ── Paper Trading ────────────────────────────────────────────────────────────
TRADE_SIZE_SOL = 0.1            # Larger size than lottery (higher conviction)
MAX_CONCURRENT_TRADES = 20      # Per strategy variant
PRICE_CHECK_INTERVAL = 15       # Seconds between price checks

# ── Parallel Strategy Variants ───────────────────────────────────────────────
# All strategies are paper-traded simultaneously on every qualifying token.
# After 500+ trades per strategy, we compare to find the best approach.
STRATEGY_VARIANTS = {
    "A_momentum": {
        "description": "Volume acceleration + rising mcap",
        "tp_pct": 0.50,           # 50% take profit
        "sl_pct": -0.10,          # 10% stop loss
        "timeout_minutes": 30,
        "trailing_activate": 0.20,  # Activate trail at 20%
        "trailing_distance": 0.15,  # Trail 15% behind peak
        "entry_filter": "volume_acceleration",
    },
    "B_breakout": {
        "description": "Mcap breakout with volume confirmation",
        "tp_pct": 1.00,           # 100% take profit (let winners run)
        "sl_pct": -0.15,          # 15% stop loss
        "timeout_minutes": 60,
        "trailing_activate": 0.30,
        "trailing_distance": 0.20,
        "entry_filter": "breakout",
    },
    "C_conservative": {
        "description": "Growing holders + no dump detected",
        "tp_pct": 0.30,           # 30% take profit
        "sl_pct": -0.08,          # 8% stop loss (tight)
        "timeout_minutes": 15,
        "trailing_activate": 0.15,
        "trailing_distance": 0.10,
        "entry_filter": "holder_growth",
    },
    "D_aggressive": {
        "description": "Any graduation with volume — wide targets",
        "tp_pct": 2.00,           # 200% take profit (diamond hands)
        "sl_pct": -0.20,          # 20% stop loss
        "timeout_minutes": 120,
        "trailing_activate": 0.50,
        "trailing_distance": 0.25,
        "entry_filter": "any_graduated",
    },
    "E_scalper": {
        "description": "Fast in/out on initial momentum",
        "tp_pct": 0.15,           # 15% take profit
        "sl_pct": -0.05,          # 5% stop loss
        "timeout_minutes": 5,
        "trailing_activate": None,  # No trailing
        "trailing_distance": None,
        "entry_filter": "fast_momentum",
    },
}

# ── Data Collection ──────────────────────────────────────────────────────────
SNAPSHOT_INTERVAL = 30           # Price snapshot every 30 seconds
SNAPSHOT_DURATION_MINUTES = 30   # Track each token for 30 minutes
MAX_TRACKED_TOKENS = 100         # Max tokens being tracked simultaneously

# ── Rate Limiting ────────────────────────────────────────────────────────────
DEXSCREENER_RATE_LIMIT = 250     # Max requests per minute (leaving buffer from 300)
HELIUS_RATE_LIMIT = 50           # Conservative Helius rate limit per minute
