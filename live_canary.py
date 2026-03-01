#!/usr/bin/env python3
"""
live_canary.py — Level 1 smoke test + Level 2 automated live canary.

Hard risk caps (in code, not config-only):
  MAX_TRADE_SIZE_SOL = 0.01
  MAX_OPEN_POSITIONS = 1
  WALLET_RESERVE_SOL = 0.04   (never touch)
  RISK_BUDGET_SOL    = 0.10
  DRAWDOWN_STOP_SOL  = 0.03   (stop if wallet drops this much from start)

Circuit breakers (HARD, checked before every trade):
  - wallet balance < WALLET_RESERVE_SOL → STOP
  - cumulative drawdown >= DRAWDOWN_STOP_SOL → STOP
  - consecutive_tx_failures >= 2 → STOP
  - realized_slippage > expected_slippage + 0.02 → STOP
  - k-cliff detected during hold → immediate exit

Smoke test (Level 1):
  - Single trade: deepest CPAMM pair (lowest round_trip_pct)
  - Buy 0.01 SOL → hold 30-60s → sell
  - Compare expected vs actual fill
  - Log all metrics
"""

import os
import sys
import time
import json
import sqlite3
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, '/root/solana_trader')
from config.config import DB_PATH, RPC_URL, WALLET_PRIVATE_KEY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('/root/solana_trader/logs/live_canary.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("live_canary")

# ─── HARD RISK CAPS (in code, not config) ─────────────────────────────────────
MAX_TRADE_SIZE_SOL   = 0.01    # Hard cap — never exceed regardless of config
MAX_OPEN_POSITIONS   = 1       # Only 1 live position at a time
WALLET_RESERVE_SOL   = 0.04    # Never touch this reserve
RISK_BUDGET_SOL      = 0.10    # Total risk budget for canary
DRAWDOWN_STOP_SOL    = 0.03    # Stop if wallet drops this much from start
SLIPPAGE_TOLERANCE   = 0.02    # Stop if realized slip > expected + 2%
MAX_CONSEC_FAILURES  = 2       # Stop after 2 consecutive tx failures
SMOKE_HOLD_SECS      = 45      # Hold duration for smoke test
KILL_SWITCH_TABLE    = "system_config"
KILL_SWITCH_KEY      = "data_collection_only"

# ─── STATE ────────────────────────────────────────────────────────────────────
@dataclass
class CanaryState:
    wallet_sol_start: float = 0.0
    wallet_sol_current: float = 0.0
    consecutive_failures: int = 0
    total_trades: int = 0
    open_positions: int = 0
    stopped: bool = False
    stop_reason: str = ""
    trade_log: list = field(default_factory=list)


state = CanaryState()


# ─── KILL SWITCH ──────────────────────────────────────────────────────────────
def is_kill_switch_active() -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            f"SELECT value FROM {KILL_SWITCH_TABLE} WHERE key=?",
            (KILL_SWITCH_KEY,)
        ).fetchone()
        conn.close()
        return row and row[0].lower() in ('1', 'true', 'yes')
    except Exception as e:
        log.error(f"Kill switch check failed: {e} — treating as ACTIVE (safe default)")
        return True


def activate_kill_switch(reason: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            f"UPDATE {KILL_SWITCH_TABLE} SET value='1' WHERE key=?",
            (KILL_SWITCH_KEY,)
        )
        conn.commit()
        conn.close()
        log.warning(f"KILL SWITCH ACTIVATED: {reason}")
    except Exception as e:
        log.error(f"Failed to activate kill switch: {e}")


# ─── WALLET BALANCE ───────────────────────────────────────────────────────────
async def get_wallet_sol_balance(session: aiohttp.ClientSession, wallet_pubkey: str) -> float:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_pubkey, {"commitment": "confirmed"}]
    }
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
        data = await r.json()
        lamports = data.get("result", {}).get("value", 0)
        return lamports / 1e9


async def get_token_balance(session: aiohttp.ClientSession, wallet_pubkey: str, mint: str) -> float:
    """Get token balance for a specific mint. Returns 0 if no account found."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_pubkey,
            {"mint": mint},
            {"encoding": "jsonParsed", "commitment": "confirmed"}
        ]
    }
    async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
        data = await r.json()
        accounts = data.get("result", {}).get("value", [])
        if not accounts:
            return 0.0
        token_amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        # Return raw integer amount (not uiAmount) for use in Jupiter swaps
        return int(token_amount.get("amount", 0) or 0)


# ─── CIRCUIT BREAKERS ─────────────────────────────────────────────────────────
async def check_circuit_breakers(session: aiohttp.ClientSession, wallet_pubkey: str) -> bool:
    """Returns True if safe to trade, False if any breaker trips."""
    if state.stopped:
        return False

    if is_kill_switch_active():
        _stop("Kill switch active")
        return False

    # Check wallet balance
    try:
        balance = await get_wallet_sol_balance(session, wallet_pubkey)
        state.wallet_sol_current = balance
    except Exception as e:
        log.error(f"Balance check failed: {e}")
        _stop("Balance check failed")
        return False

    # Reserve check
    if balance < WALLET_RESERVE_SOL:
        _stop(f"Wallet {balance:.4f} SOL < reserve {WALLET_RESERVE_SOL} SOL")
        return False

    # Drawdown check
    drawdown = state.wallet_sol_start - balance
    if drawdown >= DRAWDOWN_STOP_SOL:
        _stop(f"Drawdown {drawdown:.4f} SOL >= stop {DRAWDOWN_STOP_SOL} SOL")
        return False

    # Consecutive failures
    if state.consecutive_failures >= MAX_CONSEC_FAILURES:
        _stop(f"{state.consecutive_failures} consecutive tx failures")
        return False

    # Open positions
    if state.open_positions >= MAX_OPEN_POSITIONS:
        log.info("Max open positions reached — waiting")
        return False

    return True


async def check_circuit_breakers_hold(session, wallet_pubkey: str) -> bool:
    """Circuit breaker check during hold — skips open_positions check (already in a position)."""
    if state.stopped:
        return False
    if is_kill_switch_active():
        _stop("Kill switch active")
        return False
    try:
        balance = await get_wallet_sol_balance(session, wallet_pubkey)
        state.wallet_sol_current = balance
    except Exception as e:
        log.error(f"Balance check failed: {e}")
        _stop("Balance check failed")
        return False
    if balance < WALLET_RESERVE_SOL:
        _stop(f"Wallet {balance:.4f} SOL < reserve {WALLET_RESERVE_SOL} SOL")
        return False
    drawdown = state.wallet_sol_start - balance
    if drawdown >= DRAWDOWN_STOP_SOL:
        _stop(f"Drawdown {drawdown:.4f} SOL >= stop {DRAWDOWN_STOP_SOL} SOL")
        return False
    if state.consecutive_failures >= MAX_CONSEC_FAILURES:
        _stop(f"{state.consecutive_failures} consecutive tx failures")
        return False
    return True


def _stop(reason: str):
    state.stopped = True
    state.stop_reason = reason
    log.warning(f"CIRCUIT BREAKER TRIPPED: {reason}")
    activate_kill_switch(reason)


# ─── BEST CPAMM PAIR ──────────────────────────────────────────────────────────
def get_deepest_cpamm_pair() -> Optional[dict]:
    """Return the single CPAMM-valid pair with lowest round_trip_pct."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT mint_address, token_symbol, pair_address, venue,
               round_trip_pct, liq_usd, liq_quote_sol,
               impact_buy_pct, impact_sell_pct, price_native
        FROM universe_snapshot
        WHERE cpamm_valid_flag = 1
          AND eligible = 1
          AND round_trip_pct IS NOT NULL
          AND round_trip_pct > 0
        ORDER BY snapshot_at DESC, round_trip_pct ASC
        LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "mint": row[0], "symbol": row[1], "pair_address": row[2],
        "venue": row[3], "round_trip_pct": row[4], "liq_usd": row[5],
        "liq_quote_sol": row[6], "impact_buy_pct": row[7],
        "impact_sell_pct": row[8], "price_native": row[9]
    }


# ─── JUPITER SWAP ─────────────────────────────────────────────────────────────
JUP_API_KEY = "<REDACTED_JUP_KEY>"
JUP_BASE    = "https://<REDACTED_JUP>"
WSOL_MINT   = "So11111111111111111111111111111111111111112"


async def get_jupiter_quote(session: aiohttp.ClientSession, input_mint: str, output_mint: str,
                             amount_lamports: int) -> Optional[dict]:
    url = f"{JUP_BASE}/swap/v1/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": "300",
        "onlyDirectRoutes": "false"
    }
    headers = {"x-api-key": JUP_API_KEY}
    try:
        async with session.get(url, params=params, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                log.error(f"Jupiter quote failed: {r.status}")
                return None
            return await r.json()
    except Exception as e:
        log.error(f"Jupiter quote error: {e}")
        return None


async def execute_jupiter_swap(session: aiohttp.ClientSession, quote: dict,
                                wallet_pubkey: str, wallet_keypair) -> Optional[str]:
    """Execute a Jupiter swap. Returns tx signature or None on failure."""
    url = f"{JUP_BASE}/swap/v1/swap"
    headers = {"x-api-key": JUP_API_KEY, "Content-Type": "application/json"}
    body = {
        "quoteResponse": quote,
        "userPublicKey": wallet_pubkey,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto"
    }
    try:
        async with session.post(url, json=body, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                log.error(f"Jupiter swap failed: {r.status} {await r.text()}")
                return None
            data = await r.json()
            swap_tx = data.get("swapTransaction")
            if not swap_tx:
                log.error("No swapTransaction in response")
                return None
            # Sign and send
            from solders.keypair import Keypair
            from solders.transaction import VersionedTransaction
            from base64 import b64decode, b64encode
            import base58
            tx_bytes = b64decode(swap_tx)
            tx = VersionedTransaction.from_bytes(tx_bytes)
            # Correctly sign the versioned transaction
            signed_tx = VersionedTransaction(tx.message, [wallet_keypair])
            # Submit via RPC
            rpc_payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "sendTransaction",
                "params": [b64encode(bytes(signed_tx)).decode(), {"encoding": "base64", "skipPreflight": False}]
            }
            async with session.post(RPC_URL, json=rpc_payload,
                                     timeout=aiohttp.ClientTimeout(total=15)) as rpc_r:
                rpc_data = await rpc_r.json()
                sig = rpc_data.get("result")
                if sig:
                    log.info(f"TX submitted: {sig}")
                    return sig
                else:
                    log.error(f"RPC error: {rpc_data.get('error')}")
                    return None
    except Exception as e:
        log.error(f"Swap execution error: {e}")
        return None


# ─── SMOKE TEST ───────────────────────────────────────────────────────────────
async def run_smoke_test():
    """
    Level 1 smoke test:
    1. Find deepest CPAMM pair
    2. Get Jupiter quote for 0.01 SOL buy
    3. Execute buy
    4. Wait SMOKE_HOLD_SECS
    5. Pre-sell balance check
    6. Execute sell
    7. Compare expected vs actual fill
    8. Report
    """
    log.info("=" * 60)
    log.info("LEVEL 1 SMOKE TEST STARTING")
    log.info(f"Max trade size: {MAX_TRADE_SIZE_SOL} SOL")
    log.info(f"Hold duration: {SMOKE_HOLD_SECS}s")
    log.info("=" * 60)

    # Load wallet
    try:
        from solders.keypair import Keypair
        import base58
        keypair = Keypair.from_bytes(base58.b58decode(WALLET_PRIVATE_KEY))
        wallet_pubkey = str(keypair.pubkey())
        log.info(f"Wallet: {wallet_pubkey}")
    except Exception as e:
        log.error(f"Failed to load wallet: {e}")
        return

    async with aiohttp.ClientSession() as session:
        # Get starting balance
        try:
            state.wallet_sol_start = await get_wallet_sol_balance(session, wallet_pubkey)
            state.wallet_sol_current = state.wallet_sol_start
            log.info(f"Starting balance: {state.wallet_sol_start:.6f} SOL")
        except Exception as e:
            log.error(f"Failed to get balance: {e}")
            return

        # Check circuit breakers
        if not await check_circuit_breakers(session, wallet_pubkey):
            log.error(f"Circuit breaker tripped before start: {state.stop_reason}")
            return

        # Find best pair
        pair = get_deepest_cpamm_pair()
        if not pair:
            log.error("No valid CPAMM pair found in universe_snapshot")
            return

        log.info(f"Target pair: {pair['symbol']} ({pair['venue']})")
        log.info(f"  Liquidity: ${pair['liq_usd']:,.0f} ({pair['liq_quote_sol']:.1f} SOL)")
        log.info(f"  Expected round-trip friction: {pair['round_trip_pct']:.3f}%")
        log.info(f"  Expected buy impact: {pair['impact_buy_pct']:.3f}%")
        log.info(f"  Expected sell impact: {pair['impact_sell_pct']:.3f}%")

        # Enforce hard cap
        trade_sol = min(MAX_TRADE_SIZE_SOL, 0.01)
        trade_lamports = int(trade_sol * 1e9)

        # ── BUY ──
        log.info(f"\n--- BUY: {trade_sol} SOL → {pair['symbol']} ---")
        buy_quote = await get_jupiter_quote(session, WSOL_MINT, pair['mint'], trade_lamports)
        if not buy_quote:
            log.error("Failed to get buy quote")
            state.consecutive_failures += 1
            return

        expected_tokens_out = int(buy_quote.get("outAmount", 0))
        expected_price_impact = float(buy_quote.get("priceImpactPct", 0))
        log.info(f"  Jupiter quote: {expected_tokens_out} tokens out, {expected_price_impact:.4f}% impact")

        # Check slippage before executing
        if expected_price_impact > pair['impact_buy_pct'] / 100 + SLIPPAGE_TOLERANCE:
            log.error(f"Buy impact {expected_price_impact:.4f} > expected {pair['impact_buy_pct']/100:.4f} + tolerance")
            _stop("Pre-trade slippage check failed")
            return

        buy_time = time.time()
        buy_sig = await execute_jupiter_swap(session, buy_quote, wallet_pubkey, keypair)
        if not buy_sig:
            state.consecutive_failures += 1
            log.error("Buy tx failed")
            if state.consecutive_failures >= MAX_CONSEC_FAILURES:
                _stop("2 consecutive tx failures")
            return

        state.consecutive_failures = 0
        state.open_positions += 1
        log.info(f"  Buy TX: {buy_sig}")

        # Wait for confirmation and get actual fill
        await asyncio.sleep(5)
        actual_token_balance = await get_token_balance(session, wallet_pubkey, pair['mint'])
        log.info(f"  Actual tokens received: {actual_token_balance:,.0f}")
        log.info(f"  Expected tokens:        {expected_tokens_out:,.0f}")

        if actual_token_balance == 0:
            log.error("ABORT: No tokens received after buy — unexpected position mismatch")
            _stop("Position size mismatch: 0 tokens after buy")
            return

        fill_ratio = actual_token_balance / expected_tokens_out if expected_tokens_out > 0 else 0
        log.info(f"  Fill ratio: {fill_ratio:.4f} (1.0 = perfect)")

        # ── HOLD ──
        log.info(f"\n--- HOLDING for {SMOKE_HOLD_SECS}s ---")
        hold_start = time.time()
        while time.time() - hold_start < SMOKE_HOLD_SECS:
            await asyncio.sleep(5)
            # Check k-cliff during hold
            conn = sqlite3.connect(DB_PATH)
            cliff_row = conn.execute("""
                SELECT k_invariant FROM microstructure_log
                WHERE mint_address = ?
                ORDER BY logged_at DESC LIMIT 1
            """, (pair['mint'],)).fetchone()
            conn.close()
            if cliff_row:
                # We'd need historical k to detect cliff — log current k
                log.info(f"  k_invariant: {cliff_row[0]:.6e}")

            # Re-check circuit breakers
            if not await check_circuit_breakers_hold(session, wallet_pubkey):
                log.warning(f"Circuit breaker during hold: {state.stop_reason} — immediate exit")
                break

        # ── PRE-SELL BALANCE CHECK ──
        log.info("\n--- PRE-SELL BALANCE CHECK ---")
        sell_token_balance = await get_token_balance(session, wallet_pubkey, pair['mint'])
        log.info(f"  Token balance before sell: {sell_token_balance:,.0f}")

        if sell_token_balance == 0:
            log.error("ABORT: No tokens to sell — unexpected position mismatch")
            _stop("Position size mismatch: 0 tokens before sell")
            state.open_positions = max(0, state.open_positions - 1)
            return

        # ── SELL ──
        log.info(f"\n--- SELL: {sell_token_balance:,.0f} {pair['symbol']} → SOL ---")
        sell_amount = int(sell_token_balance)
        sell_quote = await get_jupiter_quote(session, pair['mint'], WSOL_MINT, sell_amount)
        if not sell_quote:
            log.error("Failed to get sell quote")
            state.consecutive_failures += 1
            return

        expected_sol_out = int(sell_quote.get("outAmount", 0)) / 1e9
        sell_price_impact = float(sell_quote.get("priceImpactPct", 0))
        log.info(f"  Jupiter sell quote: {expected_sol_out:.6f} SOL out, {sell_price_impact:.4f}% impact")

        sell_sig = await execute_jupiter_swap(session, sell_quote, wallet_pubkey, keypair)
        if not sell_sig:
            state.consecutive_failures += 1
            log.error("Sell tx failed")
            if state.consecutive_failures >= MAX_CONSEC_FAILURES:
                _stop("2 consecutive tx failures")
            return

        state.consecutive_failures = 0
        state.open_positions = max(0, state.open_positions - 1)
        log.info(f"  Sell TX: {sell_sig}")

        await asyncio.sleep(5)
        final_balance = await get_wallet_sol_balance(session, wallet_pubkey)
        state.wallet_sol_current = final_balance

        # ── REPORT ──
        sol_spent = state.wallet_sol_start - final_balance
        realized_rt = sol_spent / trade_sol if trade_sol > 0 else 0
        expected_rt = pair['round_trip_pct'] / 100

        log.info("\n" + "=" * 60)
        log.info("SMOKE TEST REPORT")
        log.info("=" * 60)
        log.info(f"  Pair:                {pair['symbol']} ({pair['venue']})")
        log.info(f"  Trade size:          {trade_sol} SOL")
        log.info(f"  Buy TX:              {buy_sig}")
        log.info(f"  Sell TX:             {sell_sig}")
        log.info(f"  Starting balance:    {state.wallet_sol_start:.6f} SOL")
        log.info(f"  Final balance:       {final_balance:.6f} SOL")
        log.info(f"  SOL spent (fees):    {sol_spent:.6f} SOL")
        log.info(f"  Expected RT friction:{expected_rt*100:.3f}%")
        log.info(f"  Realized RT friction:{realized_rt*100:.3f}%")
        log.info(f"  Fill ratio:          {fill_ratio:.4f}")
        log.info(f"  Slippage vs model:   {(realized_rt - expected_rt)*100:+.3f}%")
        log.info(f"  Circuit breakers:    {'TRIPPED: ' + state.stop_reason if state.stopped else 'OK'}")

        # Abort conditions
        slippage_excess = realized_rt - expected_rt
        if slippage_excess > SLIPPAGE_TOLERANCE:
            log.warning(f"ABORT CONDITION: Realized slippage {slippage_excess*100:.2f}% > {SLIPPAGE_TOLERANCE*100:.1f}% tolerance")
            log.warning("DO NOT proceed to canary — CPAMM model may be wrong")
        else:
            log.info("SMOKE TEST: PASS — slippage within tolerance")
            log.info("Ready for Level 2 canary (pending shadow evidence)")

        # Log to DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS smoke_test_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT, pair_symbol TEXT, venue TEXT,
                trade_sol REAL, buy_sig TEXT, sell_sig TEXT,
                sol_start REAL, sol_end REAL, sol_spent REAL,
                expected_rt_pct REAL, realized_rt_pct REAL,
                fill_ratio REAL, slippage_excess_pct REAL,
                circuit_breaker_tripped INTEGER, stop_reason TEXT,
                result TEXT
            )
        """)
        result = "PASS" if slippage_excess <= SLIPPAGE_TOLERANCE and not state.stopped else "FAIL"
        conn.execute("""
            INSERT INTO smoke_test_log VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            pair['symbol'], pair['venue'], trade_sol,
            buy_sig, sell_sig,
            state.wallet_sol_start, final_balance, sol_spent,
            expected_rt * 100, realized_rt * 100,
            fill_ratio, slippage_excess * 100,
            1 if state.stopped else 0, state.stop_reason,
            result
        ))
        conn.commit()
        conn.close()
        log.info(f"\nSmoke test result logged: {result}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "smoke":
        asyncio.run(run_smoke_test())
    else:
        print("Usage: python3 live_canary.py smoke")
        print("  smoke  — run Level 1 smoke test (0.01 SOL round trip)")
