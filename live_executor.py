"""
Live Executor — PumpPortal Lightning API Integration
Handles real buy/sell execution alongside the paper trader.
All trades go through PumpPortal's Lightning Transaction API.

v2: Added on-chain TX validation and pool retry for migrated tokens (error 6024).
v3: Audit fixes — env-configurable rate/lifetime/concurrent limits, pool="pump" for
    pre-bonding buys, enhanced failure/slippage/timing logging.
v3.2: Async buy verification — TX submits in ~1-2s, verification runs in background
     thread. Paper trader no longer blocks 12s per live buy.
"""

import os
import time
import json
import logging
import requests
import threading
from pnl_backfill import start_backfill_thread
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

# Safety limits — all env-configurable
MAX_SOL_PER_TRADE = float(os.getenv("MAX_SOL_PER_TRADE", "0.05"))
MIN_WALLET_BALANCE_SOL = float(os.getenv("MIN_WALLET_BALANCE_SOL", "0.01"))
MAX_LIVE_TRADES_PER_HOUR = int(os.getenv("MAX_LIVE_TRADES_PER_HOUR", "100"))
MAX_TOTAL_LIVE_TRADES = int(os.getenv("MAX_TOTAL_LIVE_TRADES", "5000"))
MAX_CONCURRENT_LIVE_TRADES = int(os.getenv("MAX_CONCURRENT_LIVE_TRADES", "15"))

# Conviction filter
LIVE_CONVICTION_FILTER = os.getenv("LIVE_CONVICTION_FILTER", "all")

# Buy pool routing: "pump" for pre-bonding (faster, no lookup latency)
LIVE_BUY_POOL = os.getenv("LIVE_BUY_POOL", "pump")
BUY_POOL_FALLBACK_ORDER = ["pump", "pump-amm"]  # Try pump first, fallback to pump-amm for migrated tokens

# On-chain validation settings
TX_CONFIRM_WAIT_SEC = 8           # Wait before checking TX on-chain
TX_CONFIRM_RETRIES = 5            # Number of retries for TX confirmation
TX_CONFIRM_RETRY_WAIT = 3         # Wait between retries

# Pool retry order for sells when bonding curve is complete (error 6024)
SELL_POOL_RETRY_ORDER = ["auto", "pump-amm", "raydium"]

# Time-bounded experiment: auto-halt after LIVE_EXPERIMENT_DURATION_SEC
# Set to 0 or unset to disable (no time limit)
LIVE_EXPERIMENT_DURATION_SEC = int(os.getenv("LIVE_EXPERIMENT_DURATION_SEC", "0"))
_live_start_time = None  # Set when first live trade executes
_live_halted_by_timer = False

# Tracking
_live_trade_count = 0
_hourly_trade_times = []
_total_sol_spent = 0.0
_total_sol_received = 0.0
_open_live_trades = set()  # Track currently open live trade IDs for concurrent limit

# Pending buy verifications — background thread checks these
_pending_buy_verifications = {}  # {paper_trade_id: {signature, mint, token_name, amount_sol, buy_start}}
_verification_lock = threading.Lock()

# ═══════════════════════════════════════════════════════════════════════════════
#  EXECUTION METRICS — collected for slippage/failure analysis
# ═══════════════════════════════════════════════════════════════════════════════

_execution_metrics = {
    "buy_attempts": 0,
    "buy_successes": 0,
    "buy_failures": 0,
    "buy_timeouts": 0,
    "sell_attempts": 0,
    "sell_successes": 0,
    "sell_failures": 0,
    "sell_timeouts": 0,
    "sell_pool_retries": 0,
    "sell_all_pools_failed": 0,
    "sell_ambiguous_confirmed": 0,
    "sell_ambiguous_failed": 0,
    "tx_confirm_times": [],       # List of (action, seconds) for TX confirmation
    "slippage_observations": [],  # List of (action, expected_sol, actual_sol_change)
    "failed_sell_details": [],    # List of {mint, token_name, error, pools_tried, timestamp}
}


# ═══════════════════════════════════════════════════════════════════════════════
#  ON-CHAIN TX VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _verify_tx_on_chain(signature, wait_sec=TX_CONFIRM_WAIT_SEC, retries=TX_CONFIRM_RETRIES):
    """
    Verify a transaction actually succeeded on-chain.
    PumpPortal returns a signature even when the TX fails on-chain.
    
    Returns:
        (confirmed: bool, error: str|None, sol_change: float|None)
        - confirmed: True if TX succeeded on-chain
        - error: Error description if TX failed
        - sol_change: Change in SOL balance for the wallet (positive = received)
    """
    if not HELIUS_RPC_URL or not signature:
        return True, None, None  # Can't verify, assume success
    
    confirm_start = time.time()
    time.sleep(wait_sec)
    
    for attempt in range(retries):
        try:
            resp = requests.post(
                HELIUS_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        signature,
                        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                    ]
                },
                timeout=10
            )
            data = resp.json()
            result = data.get("result")
            
            if result:
                confirm_elapsed = time.time() - confirm_start
                meta = result.get("meta", {})
                err = meta.get("err")
                
                if err:
                    # Parse specific error codes
                    error_desc = _parse_on_chain_error(err)
                    return False, error_desc, None
                
                # TX succeeded — calculate SOL change
                pre_balances = meta.get("preBalances", [])
                post_balances = meta.get("postBalances", [])
                sol_change = None
                if pre_balances and post_balances:
                    sol_change = (post_balances[0] - pre_balances[0]) / 1e9
                
                return True, None, sol_change
            
            # TX not found yet, retry
            if attempt < retries - 1:
                logger.debug(f"TX {signature[:20]}... not found, retry {attempt+1}/{retries}")
                time.sleep(TX_CONFIRM_RETRY_WAIT)
                
        except Exception as e:
            logger.debug(f"TX verification error: {e}")
            if attempt < retries - 1:
                time.sleep(TX_CONFIRM_RETRY_WAIT)
    
    # Could not confirm — return uncertain
    logger.warning(f"TX {signature[:20]}... could not be confirmed after {retries} retries")
    return True, None, None  # Assume success if we can't verify (don't block trading)


def _parse_on_chain_error(err):
    """Parse on-chain error into human-readable description."""
    if isinstance(err, dict) and "InstructionError" in err:
        idx, detail = err["InstructionError"]
        if isinstance(detail, dict) and "Custom" in detail:
            code = detail["Custom"]
            known_errors = {
                6024: "BondingCurveComplete — token migrated to AMM",
                6000: "NotAuthorized",
                6001: "AlreadyInitialized",
                6003: "TooMuchSolRequired",
                6004: "TooLittleSolReceived",
            }
            desc = known_errors.get(code, f"Custom error {code}")
            return f"InstructionError[{idx}]: {desc}"
        return f"InstructionError[{idx}]: {detail}"
    return str(err)


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
        logger.warning(f"Rate limit hit: {len(_hourly_trade_times)} trades in last hour (limit={MAX_LIVE_TRADES_PER_HOUR})")
        return False
    return True


def _check_lifetime_cap():
    """Enforce lifetime trade cap."""
    global _live_trade_count
    if _live_trade_count >= MAX_TOTAL_LIVE_TRADES:
        logger.warning(f"Lifetime cap hit: {_live_trade_count} total live trades (limit={MAX_TOTAL_LIVE_TRADES})")
        return False
    return True


def _check_concurrent_limit():
    """Enforce max concurrent open live trades."""
    if len(_open_live_trades) >= MAX_CONCURRENT_LIVE_TRADES:
        logger.warning(f"Concurrent limit hit: {len(_open_live_trades)} open (limit={MAX_CONCURRENT_LIVE_TRADES})")
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
        if trade_mode == "narrative":
            return True, "Narrative mode"
        return False, f"Non-narrative trade filtered (mode={trade_mode})"
    
    if filt == "proactive_only":
        if trade_mode == "proactive":
            return True, "Proactive mode"
        return False, f"Non-proactive trade filtered (mode={trade_mode})"
    
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


def _check_experiment_timer():
    """Check if the time-bounded experiment has expired. Sells are always allowed."""
    global _live_halted_by_timer
    if LIVE_EXPERIMENT_DURATION_SEC <= 0:
        return True  # No time limit
    if _live_start_time is None:
        return True  # Haven't started yet
    elapsed = time.time() - _live_start_time
    if elapsed >= LIVE_EXPERIMENT_DURATION_SEC:
        if not _live_halted_by_timer:
            _live_halted_by_timer = True
            remaining_open = len(_open_live_trades)
            logger.warning(
                f"[LIVE EXPERIMENT] Time limit reached ({LIVE_EXPERIMENT_DURATION_SEC}s / "
                f"{LIVE_EXPERIMENT_DURATION_SEC/3600:.1f}h). No new buys. "
                f"{remaining_open} open positions will still be sold when paper exits trigger."
            )
        return False
    return True


def can_execute_live():
    """Check all safety conditions before executing a live trade."""
    if _emergency_halted:
        return False, "EMERGENCY HALT ACTIVE"
    if not LIVE_ENABLED:
        return False, "Live trading disabled"

    if not PUMPPORTAL_API_KEY:
        return False, "No PumpPortal API key"

    if not _check_rate_limit():
        return False, "Rate limit exceeded"

    if not _check_lifetime_cap():
        return False, "Lifetime trade cap exceeded"

    if not _check_concurrent_limit():
        return False, "Concurrent trade limit exceeded"

    if not _check_experiment_timer():
        elapsed = time.time() - _live_start_time if _live_start_time else 0
        return False, f"Experiment time limit reached ({elapsed:.0f}s / {LIVE_EXPERIMENT_DURATION_SEC}s)"

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

def _submit_trade(action, mint_address, pool="auto", **extra_params):
    """
    Submit a trade to PumpPortal Lightning API.
    Returns (response_data, error_string).
    """
    params = {
        "action": action,
        "mint": mint_address,
        "slippage": LIVE_SLIPPAGE_PCT,
        "priorityFee": LIVE_PRIORITY_FEE,
        "pool": pool,
        **extra_params,
    }
    
    resp = requests.post(
        f"{PUMPPORTAL_TRADE_URL}?api-key={PUMPPORTAL_API_KEY}",
        data=params,
        timeout=30
    )
    
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    
    data = resp.json()
    
    if isinstance(data, dict) and ("error" in data or "errors" in data):
        err = data.get("error") or data.get("errors", "Unknown error")
        # Empty errors list [] is NOT an error — PumpPortal sometimes returns this on success
        if isinstance(err, list) and len(err) == 0:
            pass  # Fall through to signature check
        else:
            return None, str(err)
    
    if isinstance(data, dict) and "signature" in data:
        return data["signature"], None
    
    if isinstance(data, str) and len(data) > 40:
        return data, None  # Raw signature string
    
    # If we get here with an empty errors list and no signature, the sell may have gone through
    # Return a special marker so the caller can check the wallet
    if isinstance(data, dict) and isinstance(data.get("errors"), list) and len(data["errors"]) == 0:
        return "AMBIGUOUS_NO_SIGNATURE", None
    
    return None, f"Unexpected response: {data}"


def execute_buy(mint_address, token_name="", amount_sol=None, paper_trade_id=None):
    """
    Execute a live BUY via PumpPortal Lightning API.
    Validates TX on-chain after submission.
    
    Returns:
        dict with keys: success, tx_signature, error, amount_sol, timestamp,
                        confirm_time_sec, sol_change
    """
    global _live_trade_count, _total_sol_spent

    _execution_metrics["buy_attempts"] += 1
    buy_start = time.time()

    result = {
        "success": False,
        "tx_signature": None,
        "error": None,
        "amount_sol": 0,
        "timestamp": datetime.utcnow().isoformat(),
        "type": "buy",
        "mint": mint_address,
        "token_name": token_name,
        "confirm_time_sec": None,
        "sol_change": None,
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

    # Start experiment timer on first live buy
    global _live_start_time
    if _live_start_time is None and LIVE_EXPERIMENT_DURATION_SEC > 0:
        _live_start_time = time.time()
        logger.info(
            f"[LIVE EXPERIMENT] Timer started. Will halt new buys after "
            f"{LIVE_EXPERIMENT_DURATION_SEC}s ({LIVE_EXPERIMENT_DURATION_SEC/3600:.1f}h). "
            f"Open positions will still be sold normally."
        )

    try:
        pools_to_try = BUY_POOL_FALLBACK_ORDER if LIVE_BUY_POOL == "pump" else [LIVE_BUY_POOL]
        signature = None
        api_error = None
        for buy_pool in pools_to_try:
            logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL pool={buy_pool}")
            signature, api_error = _submit_trade(
                "buy", mint_address,
                pool=buy_pool,
                amount=trade_amount,
                denominatedInSol="true",
            )
            if api_error:
                if "migrated" in str(api_error).lower() or "bonding curve" in str(api_error).lower() or "6024" in str(api_error):
                    logger.warning(f"[LIVE BUY] {token_name}: pool={buy_pool} failed (migrated?), trying next...")
                    continue
                else:
                    break
            else:
                break
        if api_error:
            result["error"] = api_error
            _execution_metrics["buy_failures"] += 1
            logger.error(f"[LIVE BUY FAILED] {token_name}: {api_error} (tried: {pools_to_try})")
            return result

        # TX submitted successfully — return immediately, verify in background
        submit_elapsed = time.time() - buy_start
        result["tx_signature"] = signature
        result["success"] = True  # Optimistic: assume success, bg thread will flag failures
        result["confirm_time_sec"] = round(submit_elapsed, 2)
        
        _live_trade_count += 1
        _hourly_trade_times.append(time.time())
        _total_sol_spent += trade_amount
        _execution_metrics["buy_successes"] += 1
        if paper_trade_id is not None:
            _open_live_trades.add(paper_trade_id)
        
        logger.info(f"[LIVE BUY SUBMITTED] {token_name}: tx={signature} submit_time={submit_elapsed:.1f}s (async verify starting)")
        
        # Launch background verification thread
        def _bg_verify_buy():
            try:
                confirmed, on_chain_error, sol_change = _verify_tx_on_chain(signature)
                confirm_elapsed = time.time() - buy_start
                _execution_metrics["tx_confirm_times"].append(("buy", confirm_elapsed))
                
                if sol_change is not None:
                    _execution_metrics["slippage_observations"].append(("buy", -trade_amount, sol_change))
                    slippage_pct = ((abs(sol_change) - trade_amount) / trade_amount * 100) if trade_amount > 0 else 0
                    logger.info(f"[LIVE BUY VERIFIED] {token_name}: confirmed={confirmed} sol_change={sol_change:.6f} slippage={slippage_pct:+.1f}% confirm={confirm_elapsed:.1f}s")
                
                if not confirmed:
                    # TX failed on-chain — log it, adjust metrics
                    _execution_metrics["buy_successes"] -= 1
                    _execution_metrics["buy_failures"] += 1
                    if paper_trade_id is not None:
                        _open_live_trades.discard(paper_trade_id)
                    logger.error(f"[LIVE BUY ON-CHAIN FAIL] {token_name}: {on_chain_error} tx={signature} (detected async)")
                else:
                    logger.info(f"[LIVE BUY CONFIRMED] {token_name}: tx={signature} confirm={confirm_elapsed:.1f}s sol_change={sol_change}")
                    # Update DB with actual on-chain fill data
                    if paper_trade_id is not None and sol_change is not None:
                        try:
                            from database import Database
                            _db = Database()
                            actual_spent = abs(sol_change)
                            slippage = ((actual_spent - trade_amount) / trade_amount * 100) if trade_amount > 0 else 0
                            _db.update_live_trade_fill(
                                paper_trade_id=paper_trade_id,
                                action="buy",
                                sol_change=sol_change,
                                slippage_pct=slippage,
                            )
                            logger.info(f"[LIVE BUY FILL UPDATED] {token_name}: actual_spent={actual_spent:.6f} slippage={slippage:+.1f}%")
                        except Exception as e:
                            logger.warning(f"[LIVE BUY FILL UPDATE FAILED] {token_name}: {e}")
            except Exception as e:
                logger.warning(f"[LIVE BUY VERIFY ERROR] {token_name}: {e}")
        
        threading.Thread(target=_bg_verify_buy, daemon=True).start()

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out (30s)"
        _execution_metrics["buy_timeouts"] += 1
        logger.error(f"[LIVE BUY TIMEOUT] {token_name}")
    except Exception as e:
        result["error"] = str(e)
        _execution_metrics["buy_failures"] += 1
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


def execute_sell(mint_address, token_name="", sell_pct=100, paper_trade_id=None):
    """
    Execute a live SELL via PumpPortal Lightning API.
    Validates TX on-chain after submission.
    If TX fails with error 6024 (BondingCurveComplete), retries with different pool routing.
    After a successful 100% sell, attempts to close the empty token account to reclaim rent.
    
    Returns:
        dict with keys: success, tx_signature, error, timestamp, rent_reclaimed,
                        sol_received, confirm_time_sec, pools_tried
    """
    global _total_sol_received

    _execution_metrics["sell_attempts"] += 1
    sell_start = time.time()
    pools_tried = []

    result = {
        "success": False,
        "tx_signature": None,
        "error": None,
        "timestamp": datetime.utcnow().isoformat(),
        "type": "sell",
        "mint": mint_address,
        "token_name": token_name,
        "sell_pct": sell_pct,
        "sol_received": None,
        "confirm_time_sec": None,
        "pools_tried": [],
    }

    if not LIVE_ENABLED:
        result["error"] = "Live trading disabled"
        return result

    if not PUMPPORTAL_API_KEY:
        result["error"] = "No PumpPortal API key"
        return result

    pools_to_try = list(SELL_POOL_RETRY_ORDER)
    last_error = None

    for pool in pools_to_try:
        pools_tried.append(pool)
        try:
            logger.info(f"[LIVE SELL] Executing: {token_name} ({mint_address}) — {sell_pct}% pool={pool}")

            signature, api_error = _submit_trade(
                "sell", mint_address, pool=pool,
                amount=f"{sell_pct}%",
                denominatedInSol="false",
            )

            if api_error:
                # API-level error (pool not found, etc.) — try next pool
                last_error = api_error
                _execution_metrics["sell_pool_retries"] += 1
                logger.warning(f"[LIVE SELL] {token_name}: pool={pool} API error: {api_error}")
                continue

            # Handle ambiguous response (empty errors list, no signature)
            # PumpPortal sometimes returns {"errors":[]} when the sell actually succeeded
            if signature == "AMBIGUOUS_NO_SIGNATURE":
                logger.info(f"[LIVE SELL] {token_name}: pool={pool} returned ambiguous response, checking wallet...")
                time.sleep(3)  # Wait for TX to finalize
                try:
                    from rent_reclaim import find_token_account_for_mint
                    acc = find_token_account_for_mint(mint_address)
                    if acc is None or acc["amount"] == 0:
                        # Tokens are gone — the sell succeeded!
                        result["success"] = True
                        result["tx_signature"] = "ambiguous_but_confirmed"
                        result["sol_received"] = None  # Unknown exact amount
                        result["confirm_time_sec"] = round(time.time() - sell_start, 2)
                        _execution_metrics["sell_successes"] += 1
                        _execution_metrics["sell_ambiguous_confirmed"] += 1
                        logger.info(f"[LIVE SELL SUCCESS] {token_name}: ambiguous response but tokens gone from wallet (pool={pool})")
                        break
                    else:
                        logger.info(f"[LIVE SELL] {token_name}: tokens still in wallet ({acc['amount']}), trying next pool...")
                        last_error = "Ambiguous response, tokens still in wallet"
                        _execution_metrics["sell_ambiguous_failed"] += 1
                        _execution_metrics["sell_pool_retries"] += 1
                        continue
                except Exception as e:
                    logger.warning(f"[LIVE SELL] {token_name}: wallet check failed: {e}, trying next pool...")
                    last_error = f"Ambiguous response, wallet check failed: {e}"
                    _execution_metrics["sell_pool_retries"] += 1
                    continue

            # ── FIRE-AND-FORGET: return immediately, verify in background ──
            submit_elapsed = time.time() - sell_start
            result["success"] = True  # Optimistic
            result["tx_signature"] = signature
            result["confirm_time_sec"] = round(submit_elapsed, 2)
            result["sol_received"] = None  # Filled by backfill thread
            _execution_metrics["sell_successes"] += 1
            logger.info(f"[LIVE SELL SUBMITTED] {token_name}: tx={signature} submit_time={submit_elapsed:.1f}s (async verify)")

            # Background verification thread
            def _bg_verify_sell(_sig=signature, _tname=token_name, _mint=mint_address, _ptid=paper_trade_id, _start=sell_start, _sp=sell_pct):
                try:
                    confirmed, on_chain_error, sol_change = _verify_tx_on_chain(_sig)
                    confirm_elapsed = time.time() - _start
                    _execution_metrics["tx_confirm_times"].append(("sell", confirm_elapsed))
                    if confirmed:
                        if sol_change and sol_change > 0:
                            global _total_sol_received
                            _total_sol_received += sol_change
                        logger.info(f"[LIVE SELL CONFIRMED] {_tname}: tx={_sig} sol_received={sol_change} confirm={confirm_elapsed:.1f}s")
                        if _ptid is not None and sol_change is not None:
                            try:
                                from database import Database
                                _db = Database()
                                _db.update_live_trade_fill(paper_trade_id=_ptid, action="sell", sol_change=sol_change, slippage_pct=0)
                            except Exception as e:
                                logger.warning(f"[LIVE SELL FILL UPDATE FAILED] {_tname}: {e}")
                    else:
                        _execution_metrics["sell_successes"] -= 1
                        _execution_metrics["sell_failures"] += 1
                        logger.error(f"[LIVE SELL ON-CHAIN FAIL] {_tname}: {on_chain_error} tx={_sig}")
                    if _sp == 100:
                        _try_reclaim_rent(_mint, _tname)
                except Exception as e:
                    logger.warning(f"[LIVE SELL VERIFY ERROR] {_tname}: {e}")

            threading.Thread(target=_bg_verify_sell, daemon=True).start()

            if paper_trade_id is not None:
                _open_live_trades.discard(paper_trade_id)
            result["pools_tried"] = pools_tried
            return result

        except requests.exceptions.Timeout:
            last_error = "Request timed out (30s)"
            _execution_metrics["sell_timeouts"] += 1
            logger.error(f"[LIVE SELL TIMEOUT] {token_name} pool={pool}")
            continue
        except Exception as e:
            last_error = str(e)
            _execution_metrics["sell_failures"] += 1
            logger.error(f"[LIVE SELL ERROR] {token_name} pool={pool}: {e}")
            continue

    result["pools_tried"] = pools_tried

    if not result["success"] and not result["error"]:
        result["error"] = f"All pools failed: {last_error}"
        _execution_metrics["sell_all_pools_failed"] += 1
        # Log detailed failure for post-analysis
        _execution_metrics["failed_sell_details"].append({
            "mint": mint_address,
            "token_name": token_name,
            "error": last_error,
            "pools_tried": pools_tried,
            "timestamp": datetime.utcnow().isoformat(),
        })
        logger.error(f"[LIVE SELL ALL POOLS FAILED] {token_name}: {last_error} pools_tried={pools_tried}")

    # Remove from open trades tracking
    if paper_trade_id is not None:
        _open_live_trades.discard(paper_trade_id)

    # Attempt rent reclaim after successful 100% sell
    result["rent_reclaimed"] = 0.0
    if result["success"] and sell_pct == 100:
        result["rent_reclaimed"] = _try_reclaim_rent(mint_address, token_name)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def get_live_stats():
    """Get current live trading statistics including execution metrics."""
    balance = get_wallet_balance_sol()
    
    # Calculate average TX confirm times
    buy_confirms = [t for a, t in _execution_metrics["tx_confirm_times"] if a == "buy"]
    sell_confirms = [t for a, t in _execution_metrics["tx_confirm_times"] if a == "sell"]
    avg_buy_confirm = sum(buy_confirms) / len(buy_confirms) if buy_confirms else 0
    avg_sell_confirm = sum(sell_confirms) / len(sell_confirms) if sell_confirms else 0
    
    return {
        "enabled": LIVE_ENABLED,
        "wallet_address": WALLET_ADDRESS,
        "wallet_balance_sol": balance,
        "trade_size_sol": LIVE_TRADE_SIZE_SOL,
        "slippage_pct": LIVE_SLIPPAGE_PCT,
        "priority_fee": LIVE_PRIORITY_FEE,
        "buy_pool": LIVE_BUY_POOL,
        "total_live_trades": _live_trade_count,
        "open_live_trades": len(_open_live_trades),
        "trades_last_hour": len([t for t in _hourly_trade_times if time.time() - t < 3600]),
        "total_sol_spent": _total_sol_spent,
        "total_sol_received": _total_sol_received,
        "max_trades_per_hour": MAX_LIVE_TRADES_PER_HOUR,
        "max_total_trades": MAX_TOTAL_LIVE_TRADES,
        "max_concurrent_trades": MAX_CONCURRENT_LIVE_TRADES,
        "min_balance": MIN_WALLET_BALANCE_SOL,
        "conviction_filter": LIVE_CONVICTION_FILTER,
        # Experiment timer
        "experiment_duration_sec": LIVE_EXPERIMENT_DURATION_SEC,
        "experiment_start_time": _live_start_time,
        "experiment_elapsed_sec": round(time.time() - _live_start_time, 1) if _live_start_time else 0,
        "experiment_remaining_sec": max(0, round(LIVE_EXPERIMENT_DURATION_SEC - (time.time() - _live_start_time), 1)) if (_live_start_time and LIVE_EXPERIMENT_DURATION_SEC > 0) else None,
        "experiment_halted": _live_halted_by_timer,
        # Execution metrics
        "execution_metrics": {
            "buy_attempts": _execution_metrics["buy_attempts"],
            "buy_successes": _execution_metrics["buy_successes"],
            "buy_failures": _execution_metrics["buy_failures"],
            "buy_timeouts": _execution_metrics["buy_timeouts"],
            "buy_success_rate": (_execution_metrics["buy_successes"] / _execution_metrics["buy_attempts"] * 100) if _execution_metrics["buy_attempts"] > 0 else 0,
            "sell_attempts": _execution_metrics["sell_attempts"],
            "sell_successes": _execution_metrics["sell_successes"],
            "sell_failures": _execution_metrics["sell_failures"],
            "sell_timeouts": _execution_metrics["sell_timeouts"],
            "sell_pool_retries": _execution_metrics["sell_pool_retries"],
            "sell_all_pools_failed": _execution_metrics["sell_all_pools_failed"],
            "sell_ambiguous_confirmed": _execution_metrics["sell_ambiguous_confirmed"],
            "sell_success_rate": (_execution_metrics["sell_successes"] / _execution_metrics["sell_attempts"] * 100) if _execution_metrics["sell_attempts"] > 0 else 0,
            "avg_buy_confirm_sec": round(avg_buy_confirm, 2),
            "avg_sell_confirm_sec": round(avg_sell_confirm, 2),
            "failed_sell_count": len(_execution_metrics["failed_sell_details"]),
            "recent_failed_sells": _execution_metrics["failed_sell_details"][-5:],  # Last 5 failures
            "slippage_observations_count": len(_execution_metrics["slippage_observations"]),
        },
        # Async verification status
        "pending_verifications": len(_pending_buy_verifications),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  EMERGENCY KILL SWITCH — halt buys + dump all open positions
# ═══════════════════════════════════════════════════════════════════════════════
_emergency_halted = False

def emergency_kill_switch():
    """
    Emergency kill switch: immediately halt all new buys and sell all open positions.
    Returns dict with results of each sell attempt.
    """
    global _emergency_halted, _live_halted_by_timer, LIVE_ENABLED
    
    _emergency_halted = True
    _live_halted_by_timer = True  # Also trigger the timer halt
    LIVE_ENABLED = False  # Disable live trading entirely
    
    logger.critical("[EMERGENCY] Kill switch activated! Halting all buys and dumping positions.")
    
    results = {
        "halted": True,
        "timestamp": datetime.utcnow().isoformat(),
        "sells": [],
        "errors": [],
    }
    
    # Get all open live positions from DB
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "data", "solana_trader.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Find all open trades that have live buys
        open_live = conn.execute("""
            SELECT DISTINCT lt.mint_address, lt.token_name, t.id as paper_trade_id
            FROM live_trades lt
            JOIN trades t ON lt.paper_trade_id = t.id
            WHERE t.status = 'open' 
            AND UPPER(lt.action) = 'BUY' 
            AND lt.success = 1
            AND lt.paper_trade_id NOT IN (
                SELECT paper_trade_id FROM live_trades 
                WHERE UPPER(action) = 'SELL' AND success = 1
            )
        """).fetchall()
        
        conn.close()
        
        logger.critical(f"[EMERGENCY] Found {len(open_live)} open live positions to dump")
        
        for row in open_live:
            mint = row["mint_address"]
            name = row["token_name"]
            paper_id = row["paper_trade_id"]
            
            logger.critical(f"[EMERGENCY] Selling {name} ({mint})")
            try:
                sell_result = execute_sell(
                    mint_address=mint,
                    token_name=name,
                    sell_pct=100,
                    paper_trade_id=paper_id
                )
                results["sells"].append({
                    "mint": mint,
                    "token_name": name,
                    "success": sell_result.get("success", False),
                    "tx": sell_result.get("tx_signature"),
                    "error": sell_result.get("error"),
                    "sol_received": sell_result.get("sol_received"),
                })
            except Exception as e:
                logger.error(f"[EMERGENCY] Failed to sell {name}: {e}")
                results["errors"].append({"mint": mint, "token_name": name, "error": str(e)})
    except Exception as e:
        logger.error(f"[EMERGENCY] DB error during kill switch: {e}")
        results["errors"].append({"error": f"DB error: {str(e)}"})
    
    return results

def is_emergency_halted():
    return _emergency_halted
