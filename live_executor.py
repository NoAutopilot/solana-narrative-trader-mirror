"""
Live Executor — PumpPortal Lightning API Integration
Handles real buy/sell execution alongside the paper trader.
All trades go through PumpPortal's Lightning Transaction API.
"""

import os
import time
import json
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("live_executor")

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY", "")
PUMPPORTAL_TRADE_URL = "https://pumpportal.fun/api/trade"
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")

LIVE_TRADE_SIZE_SOL = float(os.getenv("LIVE_TRADE_SIZE_SOL", "0.005"))
LIVE_SLIPPAGE_PCT = int(os.getenv("LIVE_SLIPPAGE_PCT", "20"))
LIVE_PRIORITY_FEE = float(os.getenv("LIVE_PRIORITY_FEE", "0.0001"))
LIVE_ENABLED = os.getenv("LIVE_ENABLED", "false").lower() == "true"

# Safety limits
MAX_SOL_PER_TRADE = 0.05          # Hard cap: never spend more than this per trade
MIN_WALLET_BALANCE_SOL = 0.01     # Stop trading if balance drops below this
MAX_LIVE_TRADES_PER_HOUR = 20     # Rate limit
MAX_TOTAL_LIVE_TRADES = 500       # Lifetime cap for safety

# Conviction filter
LIVE_CONVICTION_FILTER = os.getenv("LIVE_CONVICTION_FILTER", "all")

# Tracking
_live_trade_count = 0
_hourly_trade_times = []
_total_sol_spent = 0.0
_total_sol_received = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
#  WALLET BALANCE
# ═══════════════════════════════════════════════════════════════════════════════

def get_wallet_balance_sol():
    """Get current SOL balance of the trading wallet."""
    try:
        resp = requests.post(
            HELIUS_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [WALLET_ADDRESS]
            },
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            lamports = data.get("result", {}).get("value", 0)
            return lamports / 1_000_000_000
    except Exception as e:
        logger.error(f"Failed to get wallet balance: {e}")
    return None


def get_token_balance(mint_address):
    """Get token balance for a specific mint in the wallet."""
    try:
        resp = requests.post(
            HELIUS_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    WALLET_ADDRESS,
                    {"mint": mint_address},
                    {"encoding": "jsonParsed"}
                ]
            },
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            accounts = data.get("result", {}).get("value", [])
            if accounts:
                info = accounts[0]["account"]["data"]["parsed"]["info"]
                amount = int(info["tokenAmount"]["amount"])
                decimals = info["tokenAmount"]["decimals"]
                return amount / (10 ** decimals)
    except Exception as e:
        logger.error(f"Failed to get token balance for {mint_address}: {e}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  SAFETY CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def _check_rate_limit():
    """Enforce hourly trade rate limit."""
    global _hourly_trade_times
    now = time.time()
    _hourly_trade_times = [t for t in _hourly_trade_times if now - t < 3600]
    if len(_hourly_trade_times) >= MAX_LIVE_TRADES_PER_HOUR:
        logger.warning(f"Rate limit hit: {len(_hourly_trade_times)} trades in last hour")
        return False
    return True


def _check_lifetime_cap():
    """Enforce lifetime trade cap."""
    global _live_trade_count
    if _live_trade_count >= MAX_TOTAL_LIVE_TRADES:
        logger.warning(f"Lifetime cap hit: {_live_trade_count} total live trades")
        return False
    return True


def passes_conviction_filter(trade_mode, twitter_signal=None, category=None):
    """
    Check if a trade passes the conviction filter for live execution.
    Paper trading continues for ALL trades regardless.
    
    Filters:
      - 'all': execute every trade live (original behavior)
      - 'narrative_only': only narrative and proactive modes
      - 'high_conviction': narrative/proactive + tweets>=15 + has_kol
    """
    filt = LIVE_CONVICTION_FILTER
    
    if filt == "all":
        return True, "No filter"
    
    if filt == "narrative_only":
        if trade_mode in ("narrative", "proactive"):
            return True, "Narrative/proactive mode"
        return False, f"Control trade filtered (mode={trade_mode})"
    
    if filt == "high_conviction":
        # Must be narrative or proactive
        if trade_mode not in ("narrative", "proactive"):
            return False, f"Control trade filtered (mode={trade_mode})"
        
        # Must have twitter signal with tweets>=15 and has_kol
        if not twitter_signal:
            return False, "No twitter signal data"
        
        tweet_count = twitter_signal.get("tweet_count", 0) if isinstance(twitter_signal, dict) else 0
        has_kol = twitter_signal.get("has_kol", False) if isinstance(twitter_signal, dict) else False
        
        if tweet_count < 15:
            return False, f"Low tweet count ({tweet_count}<15)"
        if not has_kol:
            return False, "No KOL engagement"
        
        return True, f"High conviction: tweets={tweet_count}, kol=True"
    
    # Unknown filter, default to all
    return True, f"Unknown filter '{filt}', defaulting to all"


def can_execute_live():
    """Check all safety conditions before executing a live trade."""
    if not LIVE_ENABLED:
        return False, "Live trading disabled"

    if not PUMPPORTAL_API_KEY:
        return False, "No PumpPortal API key"

    if not _check_rate_limit():
        return False, "Rate limit exceeded"

    if not _check_lifetime_cap():
        return False, "Lifetime trade cap exceeded"

    # Check wallet balance
    balance = get_wallet_balance_sol()
    if balance is None:
        return False, "Could not fetch wallet balance"

    if balance < MIN_WALLET_BALANCE_SOL:
        return False, f"Wallet balance too low: {balance:.4f} SOL < {MIN_WALLET_BALANCE_SOL}"

    if balance < LIVE_TRADE_SIZE_SOL + LIVE_PRIORITY_FEE + 0.001:
        return False, f"Insufficient balance for trade: {balance:.4f} SOL"

    return True, "OK"


# ═══════════════════════════════════════════════════════════════════════════════
#  TRADE EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def execute_buy(mint_address, token_name="", amount_sol=None):
    """
    Execute a live BUY via PumpPortal Lightning API.
    
    Returns:
        dict with keys: success, tx_signature, error, amount_sol, timestamp
    """
    global _live_trade_count, _total_sol_spent

    result = {
        "success": False,
        "tx_signature": None,
        "error": None,
        "amount_sol": 0,
        "timestamp": datetime.utcnow().isoformat(),
        "type": "buy",
        "mint": mint_address,
        "token_name": token_name,
    }

    # Safety checks
    can_trade, reason = can_execute_live()
    if not can_trade:
        result["error"] = reason
        logger.warning(f"[LIVE BUY BLOCKED] {token_name}: {reason}")
        return result

    trade_amount = amount_sol or LIVE_TRADE_SIZE_SOL
    if trade_amount > MAX_SOL_PER_TRADE:
        trade_amount = MAX_SOL_PER_TRADE
        logger.warning(f"Trade amount capped to {MAX_SOL_PER_TRADE} SOL")

    result["amount_sol"] = trade_amount

    try:
        logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL")

        resp = requests.post(
            f"{PUMPPORTAL_TRADE_URL}?api-key={PUMPPORTAL_API_KEY}",
            data={
                "action": "buy",
                "mint": mint_address,
                "amount": trade_amount,
                "denominatedInSol": "true",
                "slippage": LIVE_SLIPPAGE_PCT,
                "priorityFee": LIVE_PRIORITY_FEE,
                "pool": "auto",
            },
            timeout=30
        )

        data = resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}: {resp.text}"}

        if isinstance(data, dict) and "error" in data:
            result["error"] = str(data["error"])
            logger.error(f"[LIVE BUY FAILED] {token_name}: {data['error']}")
        elif isinstance(data, dict) and "signature" in data:
            result["success"] = True
            result["tx_signature"] = data["signature"]
            _live_trade_count += 1
            _hourly_trade_times.append(time.time())
            _total_sol_spent += trade_amount
            logger.info(f"[LIVE BUY SUCCESS] {token_name}: tx={data['signature']}")
        elif isinstance(data, str):
            # PumpPortal sometimes returns just the signature as a string
            result["success"] = True
            result["tx_signature"] = data
            _live_trade_count += 1
            _hourly_trade_times.append(time.time())
            _total_sol_spent += trade_amount
            logger.info(f"[LIVE BUY SUCCESS] {token_name}: tx={data}")
        else:
            result["error"] = f"Unexpected response: {data}"
            logger.error(f"[LIVE BUY UNKNOWN] {token_name}: {data}")

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out (30s)"
        logger.error(f"[LIVE BUY TIMEOUT] {token_name}")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[LIVE BUY ERROR] {token_name}: {e}")

    return result


def _try_reclaim_rent(mint_address, token_name=""):
    """Attempt to close the empty token account after a sell to reclaim rent."""
    try:
        from rent_reclaim import find_token_account_for_mint, close_single_account
        import time as _time
        _time.sleep(2)  # Wait for sell to finalize
        
        acc = find_token_account_for_mint(mint_address)
        if acc and acc["amount"] == 0:
            success, result = close_single_account(acc["pubkey"], acc["program_id"])
            if success:
                rent_sol = acc["lamports"] / 1e9
                logger.info(f"[RENT RECLAIM] {token_name}: recovered {rent_sol:.6f} SOL — tx={result}")
                return rent_sol
            else:
                logger.debug(f"[RENT RECLAIM] {token_name}: failed — {result}")
        elif acc:
            logger.debug(f"[RENT RECLAIM] {token_name}: account not empty yet (amount={acc['amount']})")
    except Exception as e:
        logger.debug(f"[RENT RECLAIM] {token_name}: error — {e}")
    return 0.0


def execute_sell(mint_address, token_name="", sell_pct=100):
    """
    Execute a live SELL via PumpPortal Lightning API.
    Sells a percentage of tokens held.
    After a successful 100% sell, attempts to close the empty token account to reclaim rent.
    
    Returns:
        dict with keys: success, tx_signature, error, timestamp, rent_reclaimed
    """
    global _total_sol_received

    result = {
        "success": False,
        "tx_signature": None,
        "error": None,
        "timestamp": datetime.utcnow().isoformat(),
        "type": "sell",
        "mint": mint_address,
        "token_name": token_name,
        "sell_pct": sell_pct,
    }

    if not LIVE_ENABLED:
        result["error"] = "Live trading disabled"
        return result

    if not PUMPPORTAL_API_KEY:
        result["error"] = "No PumpPortal API key"
        return result

    try:
        logger.info(f"[LIVE SELL] Executing: {token_name} ({mint_address}) — {sell_pct}%")

        resp = requests.post(
            f"{PUMPPORTAL_TRADE_URL}?api-key={PUMPPORTAL_API_KEY}",
            data={
                "action": "sell",
                "mint": mint_address,
                "amount": f"{sell_pct}%",
                "denominatedInSol": "false",
                "slippage": LIVE_SLIPPAGE_PCT,
                "priorityFee": LIVE_PRIORITY_FEE,
                "pool": "auto",
            },
            timeout=30
        )

        data = resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}: {resp.text}"}

        if isinstance(data, dict) and "error" in data:
            result["error"] = str(data["error"])
            logger.error(f"[LIVE SELL FAILED] {token_name}: {data['error']}")
        elif isinstance(data, dict) and "signature" in data:
            result["success"] = True
            result["tx_signature"] = data["signature"]
            logger.info(f"[LIVE SELL SUCCESS] {token_name}: tx={data['signature']}")
        elif isinstance(data, str):
            result["success"] = True
            result["tx_signature"] = data
            logger.info(f"[LIVE SELL SUCCESS] {token_name}: tx={data}")
        else:
            result["error"] = f"Unexpected response: {data}"
            logger.error(f"[LIVE SELL UNKNOWN] {token_name}: {data}")

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out (30s)"
        logger.error(f"[LIVE SELL TIMEOUT] {token_name}")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[LIVE SELL ERROR] {token_name}: {e}")

    # Attempt rent reclaim after successful 100% sell
    result["rent_reclaimed"] = 0.0
    if result["success"] and sell_pct == 100:
        result["rent_reclaimed"] = _try_reclaim_rent(mint_address, token_name)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def get_live_stats():
    """Get current live trading statistics."""
    balance = get_wallet_balance_sol()
    return {
        "enabled": LIVE_ENABLED,
        "wallet_address": WALLET_ADDRESS,
        "wallet_balance_sol": balance,
        "trade_size_sol": LIVE_TRADE_SIZE_SOL,
        "slippage_pct": LIVE_SLIPPAGE_PCT,
        "priority_fee": LIVE_PRIORITY_FEE,
        "total_live_trades": _live_trade_count,
        "trades_last_hour": len([t for t in _hourly_trade_times if time.time() - t < 3600]),
        "total_sol_spent": _total_sol_spent,
        "total_sol_received": _total_sol_received,
        "max_trades_per_hour": MAX_LIVE_TRADES_PER_HOUR,
        "max_total_trades": MAX_TOTAL_LIVE_TRADES,
        "min_balance": MIN_WALLET_BALANCE_SOL,
        "conviction_filter": LIVE_CONVICTION_FILTER,
    }
