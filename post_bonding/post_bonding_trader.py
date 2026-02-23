#!/usr/bin/env python3
"""
Post-Bonding Paper Trader
─────────────────────────
Discovers tokens graduating from pump.fun bonding curve via PumpPortal WebSocket,
tracks their price evolution on DexScreener, and paper-trades qualifying tokens
(250k+ mcap) under 5 parallel strategy variants.

Discovery Flow:
  1. PumpPortal WS → migration event (token graduates at ~$30k mcap)
  2. Add to watchlist, poll DexScreener for price/volume
  3. When token crosses 250k mcap with volume → enter paper trades
  4. Manage positions with strategy-specific TP/SL/trailing/timeout

Runs alongside the existing lottery-ticket paper trader on the VPS.

Operating Principles Applied:
  1. Trust nothing — all strategies paper-traded, no real capital
  2. Scientific data collection — parallel variants = built-in A/B test
  3. Small bets — 0.1 SOL paper size
  4. Maintain the thread — separate DB, clear logging
  5. Progress over activity — collecting data to answer: "which strategy works?"
"""
import os
import sys
import json
import time
import logging
import signal
import threading
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import websocket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_bonding_config import (
    DEXSCREENER_API_URL, PUMPPORTAL_WS_URL,
    MIN_MCAP_USD, MAX_MCAP_USD, MIN_LIQUIDITY_USD,
    MIN_VOLUME_5M_USD, MIN_TX_COUNT_5M,
    TRADE_SIZE_SOL, MAX_CONCURRENT_TRADES, PRICE_CHECK_INTERVAL,
    STRATEGY_VARIANTS, SNAPSHOT_INTERVAL, SNAPSHOT_DURATION_MINUTES,
    MAX_TRACKED_TOKENS, DEXSCREENER_RATE_LIMIT,
    LOGS_DIR, DATA_DIR,
)
import post_bonding_db as db

# ── Logging ──────────────────────────────────────────────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)
logger = logging.getLogger("post_bonding")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "post_bonding.log"))
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)

# ── State ────────────────────────────────────────────────────────────────────
seen_mints = set()          # All mints we've ever seen (from DB + WS)
watchlist = {}              # mint -> {discovered_at, data...} — tokens being tracked pre-entry
open_trades = {}            # trade_id -> {strategy, mint, entry_price, ...}
shutdown_flag = False
ws_connected = False
api_calls_this_minute = 0
api_minute_start = time.time()
stats = {
    "migrations_received": 0,
    "tokens_watched": 0,
    "tokens_qualified": 0,
    "trades_opened": 0,
    "trades_closed": 0,
    "api_calls": 0,
    "errors": 0,
    "started_at": datetime.utcnow().isoformat(),
}


def signal_handler(sig, frame):
    global shutdown_flag
    logger.info("Shutdown signal received, closing gracefully...")
    shutdown_flag = True


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ── Rate Limiting ────────────────────────────────────────────────────────────
def rate_limited_request(url, timeout=10):
    """Make a rate-limited GET request to DexScreener."""
    global api_calls_this_minute, api_minute_start

    now = time.time()
    if now - api_minute_start >= 60:
        api_calls_this_minute = 0
        api_minute_start = now

    if api_calls_this_minute >= DEXSCREENER_RATE_LIMIT:
        wait_time = 60 - (now - api_minute_start)
        if wait_time > 0:
            logger.debug(f"Rate limit reached, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
            api_calls_this_minute = 0
            api_minute_start = time.time()

    try:
        resp = requests.get(url, timeout=timeout)
        api_calls_this_minute += 1
        stats["api_calls"] += 1
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            logger.warning("DexScreener 429 rate limit, backing off 30s")
            time.sleep(30)
            return None
        else:
            return None
    except Exception as e:
        logger.error(f"Request error: {e}")
        stats["errors"] += 1
        return None


# ── DexScreener Data Fetch ───────────────────────────────────────────────────
def fetch_token_data(mint_address):
    """Fetch full token data from DexScreener."""
    url = f"{DEXSCREENER_API_URL}{mint_address}"
    data = rate_limited_request(url, timeout=8)
    if not data or "pairs" not in data or not data["pairs"]:
        return None

    # Use the pair with the most liquidity (prefer pumpswap over pumpfun)
    pairs = data["pairs"]
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol_pairs:
        return None

    # Prefer pairs with actual liquidity
    pairs_with_liq = [p for p in sol_pairs if (p.get("liquidity", {}) or {}).get("usd", 0) > 0]
    if pairs_with_liq:
        pair = max(pairs_with_liq, key=lambda p: (p.get("liquidity", {}) or {}).get("usd", 0))
    else:
        pair = sol_pairs[0]

    mcap = pair.get("marketCap") or pair.get("fdv") or 0
    liquidity = (pair.get("liquidity", {}) or {}).get("usd", 0) or 0
    volume_5m = (pair.get("volume", {}) or {}).get("m5", 0) or 0
    volume_1h = (pair.get("volume", {}) or {}).get("h1", 0) or 0
    volume_24h = (pair.get("volume", {}) or {}).get("h24", 0) or 0

    txns = pair.get("txns", {}) or {}
    txns_5m = txns.get("m5", {}) or {}
    buys_5m = txns_5m.get("buys", 0) or 0
    sells_5m = txns_5m.get("sells", 0) or 0
    tx_count_5m = buys_5m + sells_5m

    pair_created = pair.get("pairCreatedAt")
    pair_age_minutes = None
    if pair_created:
        try:
            created_dt = datetime.utcfromtimestamp(pair_created / 1000)
            pair_age_minutes = (datetime.utcnow() - created_dt).total_seconds() / 60
        except Exception:
            pass

    volume_acceleration = volume_5m / (volume_1h / 12) if volume_1h > 0 else 0
    buy_sell_ratio = buys_5m / max(sells_5m, 1)

    return {
        "mint_address": mint_address,
        "token_name": pair.get("baseToken", {}).get("name", "Unknown"),
        "token_symbol": pair.get("baseToken", {}).get("symbol", "???"),
        "pair_address": pair.get("pairAddress"),
        "dex_id": pair.get("dexId"),
        "mcap_usd": mcap,
        "liquidity_usd": liquidity,
        "price_usd": float(pair.get("priceUsd", 0) or 0),
        "price_native": float(pair.get("priceNative", 0) or 0),
        "volume_5m_usd": volume_5m,
        "volume_1h_usd": volume_1h,
        "volume_24h_usd": volume_24h,
        "tx_count_5m": tx_count_5m,
        "tx_buys_5m": buys_5m,
        "tx_sells_5m": sells_5m,
        "pair_age_minutes": pair_age_minutes,
        "volume_acceleration": volume_acceleration,
        "buy_sell_ratio": buy_sell_ratio,
    }


# ── PumpPortal WebSocket ────────────────────────────────────────────────────
def on_ws_message(ws, message):
    """Handle PumpPortal WebSocket messages (migration events)."""
    global ws_connected
    try:
        data = json.loads(message)

        # Skip subscription confirmations
        if "message" in data:
            logger.info(f"WS: {data['message']}")
            return

        # Migration event
        if data.get("txType") == "migrate":
            mint = data.get("mint")
            pool = data.get("pool", "unknown")
            sig = data.get("signature", "")

            if mint and mint not in seen_mints:
                seen_mints.add(mint)
                stats["migrations_received"] += 1

                # Add to watchlist for DexScreener tracking
                watchlist[mint] = {
                    "discovered_at": datetime.utcnow(),
                    "pool": pool,
                    "signature": sig,
                    "checks": 0,
                    "qualified": False,
                    "entered": False,
                }

                logger.info(
                    f"MIGRATION #{stats['migrations_received']}: {mint[:20]}... "
                    f"| pool={pool} | watchlist={len(watchlist)}"
                )

    except Exception as e:
        logger.error(f"WS message error: {e}")


def on_ws_open(ws):
    global ws_connected
    ws_connected = True
    ws.send(json.dumps({"method": "subscribeMigration"}))
    logger.info("WebSocket connected, subscribed to migration events")


def on_ws_error(ws, error):
    global ws_connected
    ws_connected = False
    logger.error(f"WebSocket error: {error}")


def on_ws_close(ws, close_status_code, close_msg):
    global ws_connected
    ws_connected = False
    logger.warning(f"WebSocket closed: {close_status_code} {close_msg}")


def websocket_thread():
    """Maintain persistent WebSocket connection to PumpPortal."""
    while not shutdown_flag:
        try:
            logger.info("Connecting to PumpPortal WebSocket...")
            ws = websocket.WebSocketApp(
                PUMPPORTAL_WS_URL,
                on_message=on_ws_message,
                on_open=on_ws_open,
                on_error=on_ws_error,
                on_close=on_ws_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            logger.error(f"WebSocket thread error: {e}")

        if not shutdown_flag:
            logger.info("WebSocket reconnecting in 5s...")
            time.sleep(5)

    logger.info("WebSocket thread stopped")


# ── Entry Filters ────────────────────────────────────────────────────────────
def passes_entry_filter(token_data, filter_name):
    """Check if a token passes a specific strategy's entry filter."""
    vol_accel = token_data.get("volume_acceleration", 0)
    buy_sell = token_data.get("buy_sell_ratio", 0)
    mcap = token_data.get("mcap_usd", 0)
    tx_count = token_data.get("tx_count_5m", 0)
    liq = token_data.get("liquidity_usd", 0)

    # All strategies require minimum mcap and liquidity
    if mcap < MIN_MCAP_USD or liq < MIN_LIQUIDITY_USD:
        return False

    if filter_name == "volume_acceleration":
        return vol_accel > 2.0 and buy_sell > 1.2

    elif filter_name == "breakout":
        return vol_accel > 1.5 and buy_sell > 1.5 and tx_count > 100

    elif filter_name == "holder_growth":
        return buy_sell > 1.3 and vol_accel > 1.0

    elif filter_name == "any_graduated":
        return True  # Already passed mcap/liq filters above

    elif filter_name == "fast_momentum":
        return vol_accel > 3.0 and tx_count > 150 and buy_sell > 1.5

    return False


# ── Paper Trading Logic ──────────────────────────────────────────────────────
def enter_trades(token_data):
    """Paper-enter a token under all qualifying strategy variants."""
    entries = 0

    for strategy_name, strategy_config in STRATEGY_VARIANTS.items():
        if shutdown_flag:
            break

        # Check concurrent trade limit per strategy
        strategy_open = [t for t in open_trades.values() if t["strategy"] == strategy_name]
        if len(strategy_open) >= MAX_CONCURRENT_TRADES:
            continue

        # Check entry filter
        filter_name = strategy_config.get("entry_filter", "any_graduated")
        if not passes_entry_filter(token_data, filter_name):
            continue

        trade_data = {
            "mint_address": token_data["mint_address"],
            "token_name": token_data.get("token_name"),
            "token_symbol": token_data.get("token_symbol"),
            "strategy": strategy_name,
            "entered_at": datetime.utcnow().isoformat(),
            "entry_price_usd": token_data.get("price_usd"),
            "entry_price_native": token_data.get("price_native"),
            "entry_mcap_usd": token_data.get("mcap_usd"),
            "entry_sol": TRADE_SIZE_SOL,
            "volume_5m_at_entry": token_data.get("volume_5m_usd"),
            "holder_count_at_entry": token_data.get("holder_count"),
            "buy_sell_ratio_at_entry": token_data.get("buy_sell_ratio"),
            "strategy_params": strategy_config,
        }

        trade_id = db.open_trade(trade_data)
        if trade_id:
            open_trades[trade_id] = {
                "id": trade_id,
                "strategy": strategy_name,
                "mint_address": token_data["mint_address"],
                "pair_address": token_data.get("pair_address"),
                "token_name": token_data.get("token_name"),
                "entry_price_native": token_data.get("price_native", 0),
                "entry_sol": TRADE_SIZE_SOL,
                "entered_at": datetime.utcnow(),
                "config": strategy_config,
                "peak_price": token_data.get("price_native", 0),
                "peak_pnl_pct": 0,
            }
            entries += 1
            stats["trades_opened"] += 1

    if entries > 0:
        logger.info(
            f"ENTER: {token_data.get('token_name', '?')} ({token_data.get('token_symbol', '?')}) "
            f"| mcap=${token_data.get('mcap_usd', 0):,.0f} | liq=${token_data.get('liquidity_usd', 0):,.0f} "
            f"| vol5m=${token_data.get('volume_5m_usd', 0):,.0f} "
            f"| {entries} strategy variants"
        )

    return entries


def check_exit(trade_id, trade_info, current_price_native):
    """Check if a trade should be exited based on its strategy."""
    if current_price_native is None or current_price_native <= 0:
        return None, None

    entry_price = trade_info["entry_price_native"]
    if entry_price <= 0:
        return None, None

    config = trade_info["config"]
    pnl_pct = (current_price_native - entry_price) / entry_price

    # Update peak tracking
    if current_price_native > trade_info["peak_price"]:
        trade_info["peak_price"] = current_price_native
        trade_info["peak_pnl_pct"] = pnl_pct
        db.update_peak(trade_id, current_price_native, pnl_pct)

    # Check stop loss
    if pnl_pct <= config["sl_pct"]:
        return "stop_loss", pnl_pct

    # Check take profit (hard TP)
    if pnl_pct >= config["tp_pct"]:
        return "take_profit", pnl_pct

    # Check trailing take profit
    trailing_activate = config.get("trailing_activate")
    trailing_distance = config.get("trailing_distance")
    if trailing_activate is not None and trailing_distance is not None:
        if trade_info["peak_pnl_pct"] >= trailing_activate:
            drawdown_from_peak = trade_info["peak_pnl_pct"] - pnl_pct
            if drawdown_from_peak >= trailing_distance:
                return "trailing_tp", pnl_pct

    # Check timeout
    age = (datetime.utcnow() - trade_info["entered_at"]).total_seconds()
    if age >= config["timeout_minutes"] * 60:
        return "timeout", pnl_pct

    return None, pnl_pct


# ── Watchlist Monitor Thread ─────────────────────────────────────────────────
def watchlist_monitor():
    """
    Thread that monitors the watchlist of recently graduated tokens.
    Polls DexScreener for price data and enters trades when tokens qualify.
    Also collects price snapshots for data analysis.
    """
    logger.info("Watchlist monitor started")

    while not shutdown_flag:
        try:
            now = datetime.utcnow()
            mints_to_remove = []

            for mint, info in list(watchlist.items()):
                if shutdown_flag:
                    break

                age_minutes = (now - info["discovered_at"]).total_seconds() / 60

                # Stop tracking after SNAPSHOT_DURATION_MINUTES
                if age_minutes > SNAPSHOT_DURATION_MINUTES:
                    mints_to_remove.append(mint)
                    continue

                # Don't check too frequently — every 30 seconds
                info["checks"] = info.get("checks", 0) + 1

                # Fetch current data from DexScreener
                token_data = fetch_token_data(mint)
                if not token_data:
                    continue

                # Store price snapshot
                db.insert_price_snapshot(mint, {
                    "snapshot_at": now.isoformat(),
                    "price_usd": token_data.get("price_usd"),
                    "price_native": token_data.get("price_native"),
                    "mcap_usd": token_data.get("mcap_usd"),
                    "volume_5m_usd": token_data.get("volume_5m_usd"),
                    "liquidity_usd": token_data.get("liquidity_usd"),
                    "tx_buys_5m": token_data.get("tx_buys_5m"),
                    "tx_sells_5m": token_data.get("tx_sells_5m"),
                })

                # Store/update graduated token record
                token_data["discovered_at"] = info["discovered_at"].isoformat()
                db.insert_graduated_token(token_data)

                # Update peak tracking
                current_mcap = token_data.get("mcap_usd", 0)
                db.update_graduated_token(mint, {
                    "peak_mcap_usd": max(current_mcap, 0),
                    f"mcap_at_{int(age_minutes)}m": current_mcap,
                })

                # Check if token qualifies for paper trading
                if not info.get("entered") and current_mcap >= MIN_MCAP_USD:
                    liq = token_data.get("liquidity_usd", 0)
                    vol5m = token_data.get("volume_5m_usd", 0)

                    if liq >= MIN_LIQUIDITY_USD:
                        info["qualified"] = True
                        info["entered"] = True
                        stats["tokens_qualified"] += 1

                        logger.info(
                            f"QUALIFIED: {token_data.get('token_name', '?')} "
                            f"| mcap=${current_mcap:,.0f} | liq=${liq:,.0f} "
                            f"| vol5m=${vol5m:,.0f} "
                            f"| age={age_minutes:.1f}min post-graduation"
                        )

                        # Enter paper trades
                        enter_trades(token_data)

            # Clean up expired watchlist entries
            for mint in mints_to_remove:
                watchlist.pop(mint, None)
                db.update_graduated_token(mint, {"tracking_complete": 1})

            # Trim watchlist if too large
            if len(watchlist) > MAX_TRACKED_TOKENS:
                oldest = sorted(watchlist.items(), key=lambda x: x[1]["discovered_at"])
                for mint, _ in oldest[:len(watchlist) - MAX_TRACKED_TOKENS]:
                    watchlist.pop(mint, None)

        except Exception as e:
            logger.error(f"Watchlist monitor error: {e}\n{traceback.format_exc()}")
            stats["errors"] += 1

        # Sleep between watchlist scans (rate limit aware)
        # With 100 tokens in watchlist, each needing 1 API call per 30s = ~200 calls/min
        # DexScreener limit is 300/min, so we need to pace ourselves
        sleep_time = max(SNAPSHOT_INTERVAL, len(watchlist) * 0.3)
        for _ in range(int(sleep_time)):
            if shutdown_flag:
                break
            time.sleep(1)

    logger.info("Watchlist monitor stopped")


# ── Position Management Thread ───────────────────────────────────────────────
def position_manager():
    """Thread that monitors open positions and executes exits."""
    logger.info("Position manager started")

    while not shutdown_flag:
        try:
            if not open_trades:
                time.sleep(PRICE_CHECK_INTERVAL)
                continue

            # Get unique mints from open trades
            mint_to_trades = defaultdict(list)
            for trade_id, trade_info in list(open_trades.items()):
                mint_to_trades[trade_info["mint_address"]].append((trade_id, trade_info))

            # Fetch current prices
            trades_to_close = []
            for mint, trade_list in mint_to_trades.items():
                if shutdown_flag:
                    break

                token_data = fetch_token_data(mint)
                if not token_data:
                    # Check if trade has been open too long without price data
                    for trade_id, trade_info in trade_list:
                        age = (datetime.utcnow() - trade_info["entered_at"]).total_seconds()
                        if age > trade_info["config"]["timeout_minutes"] * 60 * 2:
                            trades_to_close.append((trade_id, trade_info, "timeout_no_price", 0, {}))
                    continue

                current_price = token_data["price_native"]

                for trade_id, trade_info in trade_list:
                    exit_reason, pnl_pct = check_exit(trade_id, trade_info, current_price)
                    if exit_reason:
                        trades_to_close.append((trade_id, trade_info, exit_reason, pnl_pct, token_data))

            # Close trades
            for trade_id, trade_info, exit_reason, pnl_pct, token_data in trades_to_close:
                entry_sol = trade_info["entry_sol"]
                pnl_sol = entry_sol * (pnl_pct if pnl_pct else 0)
                hold_minutes = (datetime.utcnow() - trade_info["entered_at"]).total_seconds() / 60

                exit_data = {
                    "exit_at": datetime.utcnow().isoformat(),
                    "exit_price_usd": token_data.get("price_usd"),
                    "exit_price_native": token_data.get("price_native"),
                    "exit_mcap_usd": token_data.get("mcap_usd"),
                    "pnl_sol": pnl_sol,
                    "pnl_pct": pnl_pct,
                    "hold_minutes": hold_minutes,
                    "exit_reason": exit_reason,
                    "peak_price": trade_info["peak_price"],
                    "peak_pnl_pct": trade_info["peak_pnl_pct"],
                }

                db.close_trade(trade_id, exit_data)
                open_trades.pop(trade_id, None)
                stats["trades_closed"] += 1

                logger.info(
                    f"EXIT [{trade_info['strategy']}]: {trade_info.get('token_name', '?')} "
                    f"| {exit_reason} | PnL: {pnl_sol:+.4f} SOL ({(pnl_pct or 0):+.1%}) "
                    f"| Hold: {hold_minutes:.1f}min | Peak: {trade_info['peak_pnl_pct']:+.1%}"
                )

        except Exception as e:
            logger.error(f"Position manager error: {e}\n{traceback.format_exc()}")
            stats["errors"] += 1

        time.sleep(PRICE_CHECK_INTERVAL)

    logger.info("Position manager stopped")


# ── Stats Reporter ───────────────────────────────────────────────────────────
def stats_reporter():
    """Periodically log system stats."""
    while not shutdown_flag:
        try:
            db_stats = db.get_stats()
            uptime_hrs = (datetime.utcnow() - datetime.fromisoformat(stats["started_at"])).total_seconds() / 3600

            logger.info(
                f"STATS | Uptime: {uptime_hrs:.1f}h | WS: {'connected' if ws_connected else 'DISCONNECTED'} | "
                f"Migrations: {stats['migrations_received']} | Watchlist: {len(watchlist)} | "
                f"Qualified: {stats['tokens_qualified']} | "
                f"Trades: {db_stats['total_trades']} ({db_stats['open_trades']} open) | "
                f"API: {stats['api_calls']} | Errors: {stats['errors']}"
            )

            for strategy, data in sorted(db_stats.get("pnl_by_strategy", {}).items()):
                logger.info(
                    f"  {strategy}: {data['trades']} trades, "
                    f"PnL: {data['pnl']:+.4f} SOL, "
                    f"Win rate: {data['win_rate']:.1f}%"
                )

        except Exception as e:
            logger.error(f"Stats reporter error: {e}")

        # Report every 5 minutes
        for _ in range(30):
            if shutdown_flag:
                break
            time.sleep(10)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    global shutdown_flag
    logger.info("=" * 70)
    logger.info("Post-Bonding Paper Trader v1.0")
    logger.info("=" * 70)
    logger.info(f"Strategies: {list(STRATEGY_VARIANTS.keys())}")
    logger.info(f"Trade size: {TRADE_SIZE_SOL} SOL | Max concurrent: {MAX_CONCURRENT_TRADES}/strategy")
    logger.info(f"Entry threshold: mcap >= ${MIN_MCAP_USD:,} | liq >= ${MIN_LIQUIDITY_USD:,}")
    logger.info(f"Tracking: {SNAPSHOT_DURATION_MINUTES}min per token | Max {MAX_TRACKED_TOKENS} tokens")
    logger.info("=" * 70)

    # Initialize database
    db.init_db()

    # Load previously seen mints
    seen_mints.update(db.get_seen_mints())
    logger.info(f"Loaded {len(seen_mints)} previously seen mints")

    # Reload open trades from DB
    for trade in db.get_open_trades():
        try:
            params = json.loads(trade["strategy_params"]) if trade["strategy_params"] else {}
        except Exception:
            params = STRATEGY_VARIANTS.get(trade["strategy"], {})

        open_trades[trade["id"]] = {
            "id": trade["id"],
            "strategy": trade["strategy"],
            "mint_address": trade["mint_address"],
            "pair_address": None,
            "token_name": trade.get("token_name"),
            "entry_price_native": trade["entry_price_native"] or 0,
            "entry_sol": trade["entry_sol"],
            "entered_at": datetime.fromisoformat(trade["entered_at"]),
            "config": params,
            "peak_price": trade.get("peak_price", 0) or 0,
            "peak_pnl_pct": trade.get("peak_pnl_pct", 0) or 0,
        }
    logger.info(f"Reloaded {len(open_trades)} open trades from DB")

    # Start threads
    threads = [
        threading.Thread(target=websocket_thread, daemon=True, name="ws_thread"),
        threading.Thread(target=watchlist_monitor, daemon=True, name="watchlist_monitor"),
        threading.Thread(target=position_manager, daemon=True, name="position_manager"),
        threading.Thread(target=stats_reporter, daemon=True, name="stats_reporter"),
    ]

    for t in threads:
        t.start()
        logger.info(f"Started thread: {t.name}")

    # Main thread just keeps alive and handles shutdown
    try:
        while not shutdown_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_flag = True

    logger.info("Shutting down...")
    logger.info(f"Final stats: {json.dumps(stats, indent=2)}")

    # Wait for threads to finish
    for t in threads:
        t.join(timeout=5)

    logger.info("Post-Bonding Paper Trader stopped")


if __name__ == "__main__":
    main()
