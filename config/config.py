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
PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"

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

# ── Trading Parameters ───────────────────────────────────────────────────────
TRADE_SIZE_SOL       = 0.04    # SOL per trade (paper)
MAX_CONCURRENT_TRADES = 50     # Max open positions
CONTROL_SAMPLE_RATE  = 0.15    # 15% of non-narrative tokens enter as control

# ── Exit Strategy (default) ──────────────────────────────────────────────────
TAKE_PROFIT_PCT = 100.0  # Effectively disabled — let trailing TP handle moonshots    # 30% take profit
STOP_LOSS_PCT        = -0.25   # 25% stop loss
TIMEOUT_MINUTES      = 2       # Close after 2 min (data: 100% winners close <2min, 96% of TP profit in <1min; saves capital)
PRICE_CHECK_INTERVAL = 10      # Seconds between price checks for open trades

# ── Trailing Take Profit ─────────────────────────────────────────────────────
TRAILING_TP_ACTIVATE = 0.15  # Activate trailing TP at 15% gross gain    # Activate trailing TP at 20% profit
TRAILING_TP_DISTANCE = 0.08  # Trail 8% behind peak (tighter = captures more)    # Trail 10% behind peak

# ── Virtual Exit Strategies ──────────────────────────────────────────────────
VIRTUAL_STRATEGIES = {
    "A_baseline":       {"tp": 0.30, "sl": -0.25, "timeout": 5},
    "B_tight_stop":     {"tp": 0.30, "sl": -0.15, "timeout": 5},
    "C_wider_profit":   {"tp": 0.50, "sl": -0.25, "timeout": 5},
    "D_scalper":        {"tp": 0.15, "sl": -0.10, "timeout": 5},
    "E_long_hold":      {"tp": 0.50, "sl": -0.30, "timeout": 10},
    "F_trailing_only":  {"tp": 1.00, "sl": -0.20, "timeout": 5, "trailing": True},
    "G_diamond_hands":  {"tp": 1.00, "sl": -0.35, "timeout": 10, "trailing": True},
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
