"""
Paper Trader v4 — Solana Narrative Trading Engine
──────────────────────────────────────────────────
Core loop:
  1. Connect to PumpPortal WebSocket for new token events
  2. For each new token: rug filter → narrative match → trade decision
  3. Manage open positions: price checks, exit logic, virtual strategies
  4. Log everything for analysis

Rebuilt from surviving code + research tracker + operating principles.
"""

import os
import sys
import json
import time
import random
import logging
import signal
import threading
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import websocket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import (
    PUMPPORTAL_WS_URL, TRADE_SIZE_SOL, MAX_CONCURRENT_TRADES,
    CONTROL_SAMPLE_RATE, TAKE_PROFIT_PCT, STOP_LOSS_PCT,
    TIMEOUT_MINUTES, PRICE_CHECK_INTERVAL, TRAILING_TP_ACTIVATE,
    TRAILING_TP_DISTANCE, VIRTUAL_STRATEGIES, DEXSCREENER_API_URL,

    FEE_BUY_PCT, FEE_SELL_PCT, MIN_MATCH_SCORE,
    RUG_MIN_LIQUIDITY_SOL, RUG_MAX_DEV_HOLDING_PCT,
    DATA_DIR, LOGS_DIR
)
import database as db
from token_scanner import keyword_match_score
from narrative_monitor import NarrativeScanner, get_active_narratives
from proactive_narratives import (
    get_engine as get_proactive_engine,
    feed_narratives_to_engine,
)
from twitter_signal import check_twitter_signal
from live_executor import execute_buy, execute_sell, can_execute_live, get_live_stats, passes_conviction_filter, LIVE_TRADE_SIZE_SOL

# ── Logging (explicit handlers — basicConfig is stolen by narrative_monitor import) ──
os.makedirs(LOGS_DIR, exist_ok=True)
logger = logging.getLogger("paper_trader")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "paper_trader.log"))
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

# Also route live_executor and rent_reclaim logs to the same file
for child_name in ("live_executor", "rent_reclaim"):
    child_logger = logging.getLogger(child_name)
    child_logger.setLevel(logging.INFO)
    if not child_logger.handlers:
        child_logger.addHandler(fh)
        child_logger.addHandler(sh)

# ── State ────────────────────────────────────────────────────────────────────
open_trades = {}
virtual_positions = {}
seen_mints = set()
seen_names = set()  # Dedup by token name too — multiple people create same-name tokens
stats = {
    "tokens_seen": 0,
    "tokens_passed_rug": 0,
    "narrative_matches": 0,
    "control_entries": 0,
    "trades_opened": 0,
    "trades_closed": 0,
    "total_pnl_sol": 0.0,
    "session_start": datetime.utcnow().isoformat(),
}
shutdown_flag = threading.Event()

proactive_engine = get_proactive_engine()
STRATEGY_VERSION = "v4_rebuilt_twitter"

# Live execution tracking: maps paper_trade_id -> live buy result
# Rebuild from DB on startup so restarts don't lose open positions
def _rebuild_live_trade_map():
    """Rebuild live_trade_map from DB: find buys without matching sells."""
    _map = {}
    try:
        import sqlite3
        from config.config import DB_PATH as _DB_PATH
        _db = sqlite3.connect(_DB_PATH)
        _db.row_factory = sqlite3.Row
        rows = _db.execute("""
            SELECT lt.paper_trade_id, lt.mint_address, lt.token_name, lt.token_symbol,
                   lt.tx_signature, lt.executed_at
            FROM live_trades lt
            WHERE lt.action='buy' AND lt.success=1
            AND lt.paper_trade_id NOT IN (
                SELECT COALESCE(paper_trade_id, -1) FROM live_trades WHERE action='sell'
            )
        """).fetchall()
        for r in rows:
            _map[r['paper_trade_id']] = {
                'tx_signature': r['tx_signature'],
                'mint_address': r['mint_address'],
                'token_name': r['token_name'],
            }
        _db.close()
        if _map:
            logger.info(f"[LIVE] Rebuilt live_trade_map from DB: {len(_map)} open positions")
    except Exception as e:
        logger.warning(f"[LIVE] Could not rebuild live_trade_map: {e}")
    return _map

live_trade_map = _rebuild_live_trade_map()


# ═══════════════════════════════════════════════════════════════════════════════
#  RUG FILTER
# ═══════════════════════════════════════════════════════════════════════════════

def passes_rug_filter(token_data):
    """Basic rug pull filter. Returns (passed, reason)."""
    sol_in_curve = token_data.get("vSolInBondingCurve", 0)
    if sol_in_curve and sol_in_curve < RUG_MIN_LIQUIDITY_SOL:
        return False, f"low_liquidity_{sol_in_curve:.2f}"

    initial_buy = token_data.get("initialBuy", 0)
    token_amount = token_data.get("tokenAmount", 0)
    if token_amount and initial_buy:
        dev_pct = initial_buy / token_amount if token_amount > 0 else 0
        if dev_pct > RUG_MAX_DEV_HOLDING_PCT:
            return False, f"dev_holding_{dev_pct:.0%}"

    return True, "passed"


# ═══════════════════════════════════════════════════════════════════════════════
#  NARRATIVE MATCHING
# ═══════════════════════════════════════════════════════════════════════════════

def match_token_to_narratives(token_name, token_symbol, narratives):
    """Match a token against active narratives. Returns (best_match, score)."""
    best_match = None
    best_score = 0
    for n in narratives:
        keyword = n.get("keyword", "")
        score = keyword_match_score(token_name, token_symbol, keyword)
        if score > best_score:
            best_score = score
            best_match = n
    return best_match, best_score


def evaluate_token(token_data, narratives):
    """
    Full evaluation: proactive → reactive → control → skip.
    Returns (decision, details_dict).
    """
    name = token_data.get("name", "Unknown")
    symbol = token_data.get("symbol", "???")

    # 1. Proactive check (fast path)
    proactive_match = proactive_engine.check_token(name, symbol)
    if proactive_match and proactive_match.get("match_score", 0) >= MIN_MATCH_SCORE:
        return "proactive", {
            "match_type": "proactive",
            "match_score": proactive_match["match_score"],
            "narrative_keyword": proactive_match["event_keyword"],
            "category": proactive_match.get("category", "default"),
            "trigger_keyword": proactive_match.get("trigger_keyword", ""),
            "trigger_age_min": proactive_match.get("trigger_age_min", 0),
        }

    # 2. Reactive narrative matching
    best_match, best_score = match_token_to_narratives(name, symbol, narratives)
    if best_match and best_score >= MIN_MATCH_SCORE:
        return "narrative", {
            "match_type": "reactive",
            "match_score": best_score,
            "narrative_keyword": best_match.get("keyword", ""),
            "category": best_match.get("category", "default"),
            "narrative_score": best_match.get("score", 0),
            "narrative_velocity": best_match.get("velocity", 0),
        }

    # 3. Control group sampling
    if random.random() < CONTROL_SAMPLE_RATE:
        return "control", {
            "match_type": "control",
            "match_score": 0,
            "narrative_keyword": "",
            "category": "control",
        }

    return "skip", {}


# ═══════════════════════════════════════════════════════════════════════════════
#  PRICE FETCHING
# ═══════════════════════════════════════════════════════════════════════════════

def get_token_price(mint_address):
    """Get current token price from DexScreener. Returns (price_usd, price_sol)."""
    try:
        resp = requests.get(f"{DEXSCREENER_API_URL}{mint_address}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                pair = pairs[0]
                price_usd = float(pair.get("priceUsd", 0))
                price_native = float(pair.get("priceNative", 0))
                return price_usd, price_native
    except Exception as e:
        logger.debug(f"Price fetch failed for {mint_address}: {e}")
    return None, None


def estimate_entry_price(token_data):
    """Estimate entry price from PumpPortal create event data."""
    v_sol = token_data.get("vSolInBondingCurve", 0)
    v_tokens = token_data.get("vTokensInBondingCurve", 0)
    if v_sol and v_tokens and v_tokens > 0:
        return v_sol / v_tokens

    market_cap_sol = token_data.get("marketCapSol", 0)
    if market_cap_sol and market_cap_sol > 0:
        return market_cap_sol / 1_000_000_000

    return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
#  TRADE ENTRY
# ═══════════════════════════════════════════════════════════════════════════════

def enter_trade(token_data, decision, details, narratives):
    """Open a paper trade position."""
    if len(open_trades) >= MAX_CONCURRENT_TRADES:
        logger.debug("Max concurrent trades reached, skipping")
        return None

    mint = token_data.get("mint", "")
    name = token_data.get("name", "Unknown")
    symbol = token_data.get("symbol", "???")

    # Dedup: don't trade the same mint twice
    if mint in open_trades or mint in {t.get("mint") for t in open_trades.values()}:
        logger.debug(f"Already trading {name} (same mint), skipping")
        return None

    # Dedup: don't trade the same token name twice (people create duplicates)
    name_key = name.strip().lower()
    if name_key in seen_names:
        logger.debug(f"Already traded token named '{name}', skipping duplicate")
        return None
    seen_names.add(name_key)

    entry_price_sol = estimate_entry_price(token_data)

    if entry_price_sol <= 0:
        logger.debug(f"Could not estimate entry price for {name}, skipping")
        return None

    entry_sol = TRADE_SIZE_SOL
    narrative_keyword = details.get("narrative_keyword", "")

    # Narrative age
    narrative_age = None
    if narrative_keyword:
        for n in narratives:
            if n.get("keyword") == narrative_keyword:
                detected = n.get("detected_at", "")
                if detected:
                    try:
                        age_sec = (datetime.utcnow() - datetime.fromisoformat(detected)).total_seconds()
                        narrative_age = round(age_sec / 60, 1)
                    except:
                        pass
                break

    # Twitter signal (observation only)
    twitter_signal = None
    try:
        twitter_signal = check_twitter_signal(
            token_name=name,
            token_symbol=symbol,
            narrative_keyword=narrative_keyword if narrative_keyword else None
        )
        logger.info(f"[Twitter] {name}: {twitter_signal['tweet_count']} tweets, "
                    f"engagement={twitter_signal['total_engagement']}, "
                    f"kol={twitter_signal['has_kol']}")
    except Exception as e:
        logger.warning(f"[Twitter] Signal check failed for {name}: {e}")

    # Log the trade
    trade_id = db.log_trade(
        mint_address=mint,
        token_name=name,
        token_symbol=symbol,
        entry_price_sol=entry_price_sol,
        entry_sol=entry_sol,
        trade_mode=decision,
        decision_reason=json.dumps(details),
        category=details.get("category", "default"),
        narrative_keyword=narrative_keyword,
        narrative_age=narrative_age,
        strategy_version=STRATEGY_VERSION,
        strategy_params=json.dumps({
            "tp": TAKE_PROFIT_PCT,
            "sl": STOP_LOSS_PCT,
            "timeout": TIMEOUT_MINUTES,
        }),
        twitter_signal_data=twitter_signal,
    )

    if not trade_id:
        logger.error(f"Failed to log trade for {name}")
        return None

    trade_info = {
        "trade_id": trade_id,
        "mint": mint,
        "name": name,
        "symbol": symbol,
        "entry_price_sol": entry_price_sol,
        "entry_sol": entry_sol,
        "entry_time": datetime.utcnow(),
        "decision": decision,
        "category": details.get("category", "default"),
        "peak_price_sol": entry_price_sol,
        "trailing_active": False,
    }
    open_trades[trade_id] = trade_info

    # Initialize virtual strategies
    virtual_positions[trade_id] = {}
    for strat_name in VIRTUAL_STRATEGIES:
        virtual_positions[trade_id][strat_name] = {
            "active": True,
            "peak_price": entry_price_sol,
            "trailing_active": False,
        }

    stats["trades_opened"] += 1
    if decision in ("narrative", "proactive"):
        stats["narrative_matches"] += 1
    elif decision == "control":
        stats["control_entries"] += 1

    logger.info(
        f"[ENTRY] {decision.upper()} | {name} ({symbol}) | "
        f"price={entry_price_sol:.12f} SOL | "
        f"cat={details.get('category', '?')} | "
        f"score={details.get('match_score', 0)} | "
        f"tw={twitter_signal['tweet_count'] if twitter_signal else '?'} | "
        f"open={len(open_trades)}"
    )

    # ── LIVE EXECUTION (parallel, non-blocking) ──
    try:
        # Check conviction filter first (before safety checks to avoid unnecessary RPC calls)
        passes, filter_reason = passes_conviction_filter(
            trade_mode=decision,
            twitter_signal=twitter_signal,
            category=details.get("category", "default"),
        )
        if not passes:
            logger.debug(f"[LIVE FILTER] {name}: {filter_reason}")
        else:
            can_trade, reason = can_execute_live()
            if can_trade:
                live_result = execute_buy(mint_address=mint, token_name=name, paper_trade_id=trade_id)
                db.log_live_trade(
                    paper_trade_id=trade_id,
                    mint_address=mint,
                    token_name=name,
                    token_symbol=symbol,
                    action="buy",
                    amount_sol=live_result.get("amount_sol", 0),
                    tx_signature=live_result.get("tx_signature"),
                    success=live_result.get("success", False),
                    error=live_result.get("error"),
                    paper_price_sol=entry_price_sol,
                )
                if live_result.get("success"):
                    live_trade_map[trade_id] = live_result
                    trade_info["live_buy"] = live_result
                    logger.info(f"[LIVE BUY] {name}: tx={live_result.get('tx_signature')}")
                else:
                    logger.warning(f"[LIVE BUY FAILED] {name}: {live_result.get('error')}")
            else:
                logger.debug(f"[LIVE SKIP] {name}: {reason}")
    except Exception as e:
        logger.error(f"[LIVE BUY ERROR] {name}: {e}")

    return trade_id


# ═══════════════════════════════════════════════════════════════════════════════
#  TRADE EXIT
# ═══════════════════════════════════════════════════════════════════════════════

def check_exit(trade_info, current_price_sol):
    """Check if a trade should exit. Returns (should_exit, reason, pnl_pct)."""
    entry_price = trade_info["entry_price_sol"]
    if entry_price <= 0 or current_price_sol is None:
        return False, None, 0
    gross_pnl_pct = (current_price_sol - entry_price) / entry_price
    net_pnl_pct = gross_pnl_pct - FEE_BUY_PCT - FEE_SELL_PCT
    if current_price_sol > trade_info["peak_price_sol"]:
        trade_info["peak_price_sol"] = current_price_sol
    if net_pnl_pct >= TAKE_PROFIT_PCT:
        return True, "take_profit", net_pnl_pct
    if net_pnl_pct <= STOP_LOSS_PCT:
        return True, "stop_loss", net_pnl_pct
    if gross_pnl_pct >= TRAILING_TP_ACTIVATE:
        trade_info["trailing_active"] = True
    if trade_info["trailing_active"]:
        peak = trade_info["peak_price_sol"]
        dd = (current_price_sol - peak) / peak
        if dd <= -TRAILING_TP_DISTANCE:
            return True, "trailing_tp", net_pnl_pct
    age = (datetime.utcnow() - trade_info["entry_time"]).total_seconds()
    if age >= TIMEOUT_MINUTES * 60:
        return True, "timeout", net_pnl_pct
    return False, None, net_pnl_pct

class _PhantomSellBlocked(Exception):
    """Raised when a phantom sell is blocked by DB re-check."""
    pass

def close_trade(trade_id, trade_info, exit_reason, pnl_pct, current_price_sol):
    """Close a trade and log the exit."""
    entry_sol = trade_info["entry_sol"]
    pnl_sol = entry_sol * pnl_pct
    hold_time_sec = (datetime.utcnow() - trade_info["entry_time"]).total_seconds()

    db.close_trade(
        trade_id=trade_id,
        exit_price_sol=current_price_sol,
        exit_reason=exit_reason,
        pnl_sol=pnl_sol,
        pnl_pct=pnl_pct,
        hold_time_sec=hold_time_sec,
    )

    stats["trades_closed"] += 1
    stats["total_pnl_sol"] += pnl_sol

    logger.info(
        f"[EXIT] {exit_reason.upper()} | {trade_info['name']} ({trade_info['symbol']}) | "
        f"pnl={pnl_sol:+.4f} SOL ({pnl_pct:+.1%}) | "
        f"hold={hold_time_sec:.0f}s | total={stats['total_pnl_sol']:+.4f}"
    )

    # ── LIVE SELL (if we have a live position) ──
    try:
        if trade_id in live_trade_map:
            # v5.0 P0 FIX: Re-check DB before selling to catch async buy failures
            # Background verification may have marked buy as failed after live_trade_map was set
            try:
                import sqlite3 as _sq3_check
                from config.config import DB_PATH as _db_check_path
                _check_conn = _sq3_check.connect(_db_check_path)
                _buy_row = _check_conn.execute(
                    "SELECT success FROM live_trades WHERE paper_trade_id = ? AND UPPER(action) = 'BUY'",
                    (trade_id,)
                ).fetchone()
                _check_conn.close()
                if _buy_row and _buy_row[0] != 1:
                    logger.warning(
                        f"[PHANTOM SELL BLOCKED] {trade_info['name']}: buy was marked failed "
                        f"by async verification (success={_buy_row[0]}). Skipping live sell."
                    )
                    del live_trade_map[trade_id]
                    # Skip the sell entirely — jump to cleanup
                    raise _PhantomSellBlocked()
            except _PhantomSellBlocked:
                raise
            except Exception as _check_err:
                logger.warning(f"[PHANTOM SELL CHECK] DB check failed: {_check_err}, proceeding with sell")
            
            live_buy = live_trade_map[trade_id]
            sell_result = execute_sell(
                mint_address=trade_info["mint"],
                token_name=trade_info["name"],
                sell_pct=100,
                paper_trade_id=trade_id
            )
            # Use actual on-chain sell proceeds if available, fall back to paper estimate
            buy_amount = live_buy.get("amount_sol", LIVE_TRADE_SIZE_SOL)
            sol_received = sell_result.get("sol_received")  # Actual SOL from on-chain verification
            
            if sol_received is not None and sol_received > 0:
                # REAL on-chain data available
                returned_sol = sol_received
                live_pnl = returned_sol - buy_amount
                live_pnl_pct = live_pnl / buy_amount if buy_amount > 0 else 0
                logger.info(f"[LIVE SELL PNL] {trade_info['name']}: REAL on-chain — received={returned_sol:.6f} buy={buy_amount:.4f} pnl={live_pnl:+.6f} SOL ({live_pnl_pct:+.1%})")
            else:
                # Fallback to paper estimate (sol_received unavailable)
                returned_sol = buy_amount * (1 + pnl_pct) if pnl_pct else 0
                live_pnl = returned_sol - buy_amount
                live_pnl_pct = pnl_pct
                logger.info(f"[LIVE SELL PNL] {trade_info['name']}: PAPER ESTIMATE — no on-chain data, using paper pnl={live_pnl:+.6f} SOL")
            
            db.log_live_trade(
                paper_trade_id=trade_id,
                mint_address=trade_info["mint"],
                token_name=trade_info["name"],
                token_symbol=trade_info["symbol"],
                action="sell",
                amount_sol=round(returned_sol, 6),
                tx_signature=sell_result.get("tx_signature"),
                success=sell_result.get("success", False),
                error=sell_result.get("error"),
                paper_price_sol=current_price_sol,
                pnl_sol=round(live_pnl, 6),
                pnl_pct=round(live_pnl_pct, 6) if live_pnl_pct else pnl_pct,
                hold_time_sec=hold_time_sec,
            )
            if sell_result.get("success"):
                logger.info(f"[LIVE SELL] {trade_info['name']}: tx={sell_result.get('tx_signature')}")
            else:
                logger.warning(f"[LIVE SELL FAILED] {trade_info['name']}: {sell_result.get('error')}")
            del live_trade_map[trade_id]
    except _PhantomSellBlocked:
        pass  # Already logged — sell was correctly skipped
    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")

    del open_trades[trade_id]
    if trade_id in virtual_positions:
        del virtual_positions[trade_id]


def check_virtual_exits(trade_id, trade_info, current_price_sol):
    """Check virtual strategy exits for a trade."""
    if trade_id not in virtual_positions:
        return

    entry_price = trade_info["entry_price_sol"]
    if entry_price <= 0 or current_price_sol is None:
        return

    age_sec = (datetime.utcnow() - trade_info["entry_time"]).total_seconds()

    for strat_name, strat_state in virtual_positions[trade_id].items():
        if not strat_state["active"]:
            continue

        params = VIRTUAL_STRATEGIES[strat_name]
        gross_pnl_pct = (current_price_sol - entry_price) / entry_price
        net_pnl_pct = gross_pnl_pct - FEE_BUY_PCT - FEE_SELL_PCT

        if current_price_sol > strat_state["peak_price"]:
            strat_state["peak_price"] = current_price_sol

        exit_reason = None

        if net_pnl_pct >= params["tp"]:
            exit_reason = "take_profit"
        elif net_pnl_pct <= params["sl"]:
            exit_reason = "stop_loss"
        elif params.get("time_gated"):
            # H_time_gated: phase-specific SL and trailing TP
            p = params  # shorthand
            if age_sec < p["phase1_end"]:
                # Phase 1: Formation window — only catastrophic SL
                if net_pnl_pct <= p["phase1_sl"]:
                    exit_reason = "stop_loss"
            elif age_sec < p["phase2_end"]:
                # Phase 2: Wide trailing
                if net_pnl_pct <= p["phase2_sl"]:
                    exit_reason = "stop_loss"
                elif gross_pnl_pct >= p["phase2_trail_act"]:
                    strat_state["trailing_active"] = True
                if strat_state["trailing_active"] and not exit_reason:
                    peak = strat_state["peak_price"]
                    dd = (current_price_sol - peak) / peak
                    if dd <= -p["phase2_trail_dist"]:
                        exit_reason = "trailing_tp"
            elif age_sec < p["phase3_end"]:
                # Phase 3: Tighter trailing
                if net_pnl_pct <= p["phase3_sl"]:
                    exit_reason = "stop_loss"
                elif gross_pnl_pct >= p["phase3_trail_act"]:
                    strat_state["trailing_active"] = True
                if strat_state["trailing_active"] and not exit_reason:
                    peak = strat_state["peak_price"]
                    dd = (current_price_sol - peak) / peak
                    if dd <= -p["phase3_trail_dist"]:
                        exit_reason = "trailing_tp"
            # Phase 4: timeout handled below
        elif params.get("trailing"):
            if gross_pnl_pct >= TRAILING_TP_ACTIVATE:
                strat_state["trailing_active"] = True
            if strat_state["trailing_active"]:
                peak = strat_state["peak_price"]
                dd = (current_price_sol - peak) / peak
                if dd <= -TRAILING_TP_DISTANCE:
                    exit_reason = "trailing_tp"
        if age_sec >= params["timeout"] * 60:
            exit_reason = exit_reason or "timeout"

        if exit_reason:
            strat_state["active"] = False
            pnl_sol = trade_info["entry_sol"] * net_pnl_pct
            db.log_virtual_exit(
                trade_id=trade_id,
                strategy_name=strat_name,
                exit_reason=exit_reason,
                exit_price_sol=current_price_sol,
                pnl_sol=pnl_sol,
                pnl_pct=net_pnl_pct,
                hold_time_sec=age_sec,
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  POSITION MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

def monitor_positions():
    """Background thread: check prices and exits for open trades."""
    logger.info("Position monitor started")
    while not shutdown_flag.is_set():
        try:
            if not open_trades:
                time.sleep(PRICE_CHECK_INTERVAL)
                continue

            trade_ids = list(open_trades.keys())
            for trade_id in trade_ids:
                if trade_id not in open_trades:
                    continue
                trade_info = open_trades[trade_id]
                _, current_price_sol = get_token_price(trade_info["mint"])

                if current_price_sol is None or current_price_sol <= 0:
                    age = (datetime.utcnow() - trade_info["entry_time"]).total_seconds()
                    if age >= TIMEOUT_MINUTES * 60 * 2:
                        close_trade(trade_id, trade_info, "timeout_no_price",
                                    -FEE_BUY_PCT - FEE_SELL_PCT, 0)
                    continue

                check_virtual_exits(trade_id, trade_info, current_price_sol)

                should_exit, exit_reason, pnl_pct = check_exit(trade_info, current_price_sol)
                if should_exit:
                    close_trade(trade_id, trade_info, exit_reason, pnl_pct, current_price_sol)

                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Position monitor error: {e}\n{traceback.format_exc()}")

        time.sleep(PRICE_CHECK_INTERVAL)

    logger.info("Position monitor stopped")


# ═══════════════════════════════════════════════════════════════════════════════
#  WEBSOCKET HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

def on_ws_message(ws, message):
    """Handle incoming WebSocket messages from PumpPortal."""
    try:
        data = json.loads(message)
        if not isinstance(data, dict):
            return

        mint = data.get("mint", "")
        if not mint or mint in seen_mints:
            return
        seen_mints.add(mint)

        if len(seen_mints) > 50000:
            excess = list(seen_mints)[:25000]
            for m in excess:
                seen_mints.discard(m)

        stats["tokens_seen"] += 1
        name = data.get("name", "Unknown")
        symbol = data.get("symbol", "???")

        passed, reason = passes_rug_filter(data)
        if not passed:
            logger.debug(f"[RUG] {name} ({symbol}): {reason}")
            return
        stats["tokens_passed_rug"] += 1

        narratives = get_active_narratives()
        decision, details = evaluate_token(data, narratives)

        if decision == "skip":
            return

        enter_trade(data, decision, details, narratives)

    except Exception as e:
        logger.error(f"WS message error: {e}\n{traceback.format_exc()}")


def on_ws_error(ws, error):
    logger.error(f"WebSocket error: {error}")


def on_ws_close(ws, close_status_code, close_msg):
    logger.warning(f"WebSocket closed: {close_status_code} {close_msg}")


def on_ws_open(ws):
    logger.info("WebSocket connected to PumpPortal")
    payload = {"method": "subscribeNewToken"}
    ws.send(json.dumps(payload))
    logger.info("Subscribed to new token events")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def print_status():
    """Print periodic status to log."""
    while not shutdown_flag.is_set():
        time.sleep(300)
        if shutdown_flag.is_set():
            break
        active_narratives = get_active_narratives()
        ps = proactive_engine.get_stats()
        live = get_live_stats()
        live_bal = live.get('wallet_balance_sol') or 0
        logger.info(
            f"[STATUS] seen={stats['tokens_seen']} | "
            f"rug_pass={stats['tokens_passed_rug']} | "
            f"narr={stats['narrative_matches']} | "
            f"ctrl={stats['control_entries']} | "
            f"open={len(open_trades)} | "
            f"closed={stats['trades_closed']} | "
            f"pnl={stats['total_pnl_sol']:+.4f} | "
            f"narratives={len(active_narratives)} | "
            f"triggers={ps.get('active_triggers', 0)} | "
            f"LIVE: {live['total_live_trades']} trades, bal={live_bal:.4f} SOL"
        )


def graceful_shutdown(signum, frame):
    logger.info(f"Signal {signum} received, shutting down...")
    shutdown_flag.set()


def main():
    db.init_db()
    logger.info("=" * 60)
    logger.info(f"Paper Trader {STRATEGY_VERSION} starting")
    logger.info(f"Trade size: {TRADE_SIZE_SOL} SOL | Max concurrent: {MAX_CONCURRENT_TRADES}")
    logger.info(f"TP: {TAKE_PROFIT_PCT:.0%} | SL: {STOP_LOSS_PCT:.0%} | Timeout: {TIMEOUT_MINUTES}min")
    logger.info(f"Control rate: {CONTROL_SAMPLE_RATE:.0%} | Fees: {FEE_BUY_PCT+FEE_SELL_PCT:.0%} RT")
    live = get_live_stats()
    if live["enabled"]:
        logger.info(f"LIVE TRADING ENABLED | wallet={live['wallet_address'][:8]}... | "
                    f"balance={live['wallet_balance_sol']:.4f} SOL | "
                    f"size={live['trade_size_sol']} SOL/trade | "
                    f"slippage={live['slippage_pct']}%")
    else:
        logger.info("LIVE TRADING DISABLED (paper only)")
    logger.info("=" * 60)

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    # ── Load orphaned open trades from DB (survive restarts) ──
    orphaned = db.get_open_trades()
    loaded = 0
    for row in orphaned:
        tid = row["id"]
        entered_at_str = row.get("entered_at", "")
        try:
            entry_time = datetime.fromisoformat(entered_at_str)
        except Exception:
            entry_time = datetime.utcnow()
        open_trades[tid] = {
            "mint": row["mint_address"],
            "name": row.get("token_name", "?"),
            "symbol": row.get("token_symbol", "?"),
            "entry_price_sol": row.get("entry_price_usd", 0),  # stored in entry_price_usd col
            "entry_sol": row.get("entry_sol", TRADE_SIZE_SOL),
            "entry_time": entry_time,
            "decision": row.get("trade_mode", "control"),
            "category": row.get("category", "default"),
            "peak_price_sol": row.get("entry_price_usd", 0),
            "trailing_active": False,
        }
        # Also initialize virtual strategies for loaded trades
        virtual_positions[tid] = {}
        for strat_name in VIRTUAL_STRATEGIES:
            virtual_positions[tid][strat_name] = {
                "active": True,
                "peak_price": row.get("entry_price_usd", 0),
                "trailing_active": False,
            }
        loaded += 1
    if loaded:
        logger.info(f"Loaded {loaded} orphaned open trades from DB")

    def on_narratives_scanned(narratives):
        feed_narratives_to_engine(proactive_engine, narratives)

    scanner = NarrativeScanner(on_scan_callback=on_narratives_scanned)
    scanner.start_background()

    time.sleep(5)
    active = get_active_narratives()
    ps = proactive_engine.get_stats()
    logger.info(f"Initial: {len(active)} narratives, {ps.get('active_triggers', 0)} triggers")

    monitor_thread = threading.Thread(target=monitor_positions, daemon=True)
    monitor_thread.start()

    status_thread = threading.Thread(target=print_status, daemon=True)
    status_thread.start()

    while not shutdown_flag.is_set():
        try:
            logger.info("Connecting to PumpPortal WebSocket...")
            ws = websocket.WebSocketApp(
                PUMPPORTAL_WS_URL,
                on_open=on_ws_open,
                on_message=on_ws_message,
                on_error=on_ws_error,
                on_close=on_ws_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)

            if shutdown_flag.is_set():
                break
            logger.warning("WebSocket disconnected, reconnecting in 5s...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"WS connection error: {e}")
            if shutdown_flag.is_set():
                break
            time.sleep(10)

    logger.info("Shutting down...")
    scanner.stop()
    for trade_id, trade_info in list(open_trades.items()):
        close_trade(trade_id, trade_info, "shutdown", -FEE_BUY_PCT - FEE_SELL_PCT, 0)
    logger.info(f"Final: {json.dumps(stats, indent=2)}")
    logger.info("Paper trader stopped.")


if __name__ == "__main__":
    main()
