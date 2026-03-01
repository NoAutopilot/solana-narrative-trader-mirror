"""
Configuration — all constants, paths, and thresholds in one place.
"""

import os

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DB_PATH  = os.path.join(DATA_DIR, "solana_trader.db")

# ── PumpPortal WebSocket ─────────────────────────────────────────────────────
PUMPPORTAL_WS_URL = "<REDACTED_WSS>/api/data"

# ── Narrative Matching ───────────────────────────────────────────────────────
MIN_MATCH_SCORE        = 60      # Minimum score to consider a narrative match
MIN_NARRATIVE_SCORE    = 60      # Minimum narrative score to be "active"
NARRATIVE_SCAN_INTERVAL = 900    # Seconds between RSS scans (15 min)

# ── RSS Feed Sources ─────────────────────────────────────────────────────────
RSS_FEEDS = {
    "bbc":          "http://feeds.bbci.co.uk/news/rss.xml",
    "google_news":  "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "coindesk":     "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "hackernews":   "https://hnrss.org/frontpage",
}

# Source-specific velocity weights (crypto sources get a boost)
SOURCE_VELOCITY_WEIGHTS = {
    "coindesk":      1.2,
    "cointelegraph": 1.2,
    "bbc":           1.0,
    "google_news":   1.0,
    "hackernews":    0.9,
}

# ── Narrative Scoring ────────────────────────────────────────────────────────
VELOCITY_WEIGHT     = 0.4
MAX_VELOCITY_WEIGHT = 0.6
CROSS_SOURCE_BOOST  = 0.30   # +30% per additional source
CRYPTO_SOURCE_BOOST = 0.20   # +20% for crypto-specific sources

# Category durability (hours before expiry)
CATEGORY_DURABILITY = {
    "political":  72,
    "financial":  48,
    "tech":       48,
    "celebrity":  36,
    "sports":     24,
    "meme":       12,
    "default":    24,
}

# Category detection keywords
CATEGORY_KEYWORDS = {
    "political": ["trump", "biden", "congress", "senate", "election", "vote",
                  "president", "democrat", "republican", "government", "policy",
                  "tariff", "sanction", "supreme court", "legislation", "white house"],
    "celebrity": ["elon", "musk", "kanye", "kardashian", "celebrity", "influencer",
                  "rapper", "singer", "actor", "actress", "famous", "viral"],
    "sports":    ["nfl", "nba", "superbowl", "world cup", "championship", "playoff",
                  "olympics", "soccer", "football", "basketball", "baseball"],
    "financial": ["bitcoin", "ethereum", "crypto", "stock", "market", "fed",
                  "interest rate", "inflation", "recession", "bull", "bear",
                  "etf", "sec", "regulation", "defi"],
    "tech":      ["ai", "openai", "chatgpt", "apple", "google", "microsoft",
                  "nvidia", "chip", "semiconductor", "quantum", "robot"],
}

# ── Category Filter ─────────────────────────────────────────────────────────
# Categories with insufficient edge — excluded from proactive live trading
# celebrity: 6.2% win rate across 64 trades (Session 9 analysis)
# sports: 0.0% win rate across 4 trades (Session 9 analysis)
BLOCKED_CATEGORIES = ["celebrity", "sports"]

# ── Trading Parameters ───────────────────────────────────────────────────────
TRADE_SIZE_SOL       = 0.04    # SOL per trade (paper)
MAX_CONCURRENT_TRADES = 50     # Max open positions
CONTROL_SAMPLE_RATE  = 0.15    # 15% of non-narrative tokens enter as control

# ── Exit Strategy (default) ──────────────────────────────────────────────────
TAKE_PROFIT_PCT = 100.0  # Effectively disabled — let trailing TP handle moonshots    # 30% take profit
STOP_LOSS_PCT        = -0.25   # 25% stop loss
TIMEOUT_MINUTES      = 1       # Close after 1 min (Session 9: 47% win rate in 30-60s, drops to 7% after 2min)
PRICE_CHECK_INTERVAL = 10      # Seconds between price checks for open trades

# ── Trailing Take Profit ─────────────────────────────────────────────────────
TRAILING_TP_ACTIVATE = 0.15  # Activate trailing TP at 15% gross gain
TRAILING_TP_DISTANCE = 0.08  # Trail 8% behind peak

# ── Virtual Exit Strategies ──────────────────────────────────────────────────
VIRTUAL_STRATEGIES = {
    "A_baseline":       {"tp": 0.30, "sl": -0.25, "timeout": 5},
    "B_tight_stop":     {"tp": 0.30, "sl": -0.15, "timeout": 5},
    "C_wider_profit":   {"tp": 0.50, "sl": -0.25, "timeout": 5},
    "D_scalper":        {"tp": 0.15, "sl": -0.10, "timeout": 5},
    "E_long_hold":      {"tp": 0.50, "sl": -0.30, "timeout": 10},
    "F_trailing_only":  {"tp": 1.00, "sl": -0.20, "timeout": 5, "trailing": True},
    "G_diamond_hands":  {"tp": 1.00, "sl": -0.35, "timeout": 10, "trailing": True},
    "H_time_gated":    {"tp": 100.0, "sl": -0.50, "timeout": 2.5, "time_gated": True,
                         "phase1_end": 45, "phase1_sl": -0.50,
                         "phase2_end": 90, "phase2_trail_act": 0.50, "phase2_trail_dist": 0.25, "phase2_sl": -0.30,
                         "phase3_end": 150, "phase3_trail_act": 0.30, "phase3_trail_dist": 0.15, "phase3_sl": -0.25},
    "I_letsbonk":      {"tp": 1.00, "sl": -0.25, "timeout": 1.5, "trailing": True,
                         "note": "letsbonk.fun platform filter — 85.7% win rate n=7 Session 9"},
}

# ── Rug Filter Thresholds ───────────────────────────────────────────────────
RUG_MIN_LIQUIDITY_SOL   = 0.5    # Minimum initial liquidity
RUG_MAX_DEV_HOLDING_PCT = 0.90   # Max dev wallet holding
RUG_MIN_HOLDERS         = 1      # Minimum holder count at entry
RUG_MAX_SUPPLY_TOP_PCT  = 0.95   # Max % of supply in top wallet

# ── Price API ────────────────────────────────────────────────────────────────
# DexScreener for price lookups (free, no auth)
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens/"

# ── Fee Model ────────────────────────────────────────────────────────────────
FEE_BUY_PCT  = 0.04   # 4% buy fee (pump.fun + slippage)
FEE_SELL_PCT = 0.04   # 4% sell fee (pump.fun + slippage)
TOTAL_FEE_PCT = FEE_BUY_PCT + FEE_SELL_PCT  # 8% round trip

# ── Flask Dashboard ──────────────────────────────────────────────────────────
DASHBOARD_PORT = 5050
DASHBOARD_HOST = "0.0.0.0"

# Jupiter API
JUPITER_API_KEY = _os.getenv("JUPITER_API_KEY")
JUPITER_BASE_URL = "https://<REDACTED_JUP>"

# ── Live Trading Credentials (loaded from environment) ──────────────────────
import os as _os

def _validate_env_vars():
    # These are only required for live trading, not for reporting/analysis
    if _os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true":
        required = ["JUPITER_API_KEY", "HELIUS_RPC_URL", "WALLET_PRIVATE_KEY"]
        missing = [v for v in required if not _os.getenv(v)]
        if missing:
            raise ValueError(f"Missing required environment variables for live trading: {', '.join(missing)}")

_validate_env_vars()
RPC_URL             = _os.getenv("HELIUS_RPC_URL")
WALLET_PRIVATE_KEY  = _os.getenv("WALLET_PRIVATE_KEY")
WALLET_PUBKEY       = _os.getenv('WALLET_PUBKEY', '<REDACTED_WALLET_PUBKEY>')
