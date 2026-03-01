#!/usr/bin/env python3
"""
Insert backfilled on-chain data into the existing live_trades table.
Uses the raw JSON from backfill_from_chain.py and maps to the correct schema.
Properly handles zero-return sells (dead tokens).
"""

import os
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "solana_trader.db")
RAW_PATH = os.path.join(os.path.dirname(__file__), "data", "backfill_raw.json")
WALLET = "<REDACTED_WALLET_PUBKEY>"


def main():
    print("=" * 60)
    print("  BACKFILL INSERT (corrected schema)")
    print("=" * 60)
    
    with open(RAW_PATH) as f:
        raw = json.load(f)
    
    txs = raw["parsed_transactions"]
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Clear previous backfill attempts
    c.execute("DELETE FROM live_trades WHERE 1=1")
    conn.commit()
    
    # Classify all transactions
    buys = []
    sells_ok = []
    sells_zero = []
    
    for tx in txs:
        tokens_out = tx.get("tokens_out", [])
        tokens_in = tx.get("tokens_in", [])
        sol_in = tx.get("sol_in", 0)
        sol_out = tx.get("sol_out", 0)
        
        if sol_out > 0.001 and tokens_in:
            buys.append(tx)
        elif tokens_out and sol_in > 0.0001:
            sells_ok.append(tx)
        elif tokens_out and sol_in <= 0.0001:
            sells_zero.append(tx)
    
    all_sells = sells_ok + sells_zero
    
    # Build mint lookup for matching
    buy_by_mint = {}
    for tx in buys:
        m = tx["tokens_in"][0]["mint"]
        if m not in buy_by_mint:
            buy_by_mint[m] = []
        buy_by_mint[m].append(tx)
    
    sell_by_mint = {}
    for tx in all_sells:
        if tx.get("tokens_out"):
            m = tx["tokens_out"][0]["mint"]
            if m not in sell_by_mint:
                sell_by_mint[m] = []
            sell_by_mint[m].append(tx)
    
    # Insert BUY transactions
    inserted = 0
    for tx in buys:
        mint = tx["tokens_in"][0]["mint"]
        ts = datetime.fromtimestamp(tx["timestamp"], tz=timezone.utc).isoformat()
        
        try:
            c.execute("""INSERT OR IGNORE INTO live_trades 
                (mint_address, action, amount_sol, tx_signature, success, 
                 executed_at, paper_price_sol)
                VALUES (?, 'BUY', ?, ?, 1, ?, ?)""",
                (mint, tx["sol_out"], tx["signature"], ts, tx["sol_out"]))
            inserted += 1
        except Exception as e:
            print(f"  Error inserting BUY: {e}")
    
    # Insert SELL transactions with matched PnL
    for tx in all_sells:
        if not tx.get("tokens_out"):
            continue
        mint = tx["tokens_out"][0]["mint"]
        ts = datetime.fromtimestamp(tx["timestamp"], tz=timezone.utc).isoformat()
        sol_returned = tx.get("sol_in", 0)
        
        # Calculate PnL by matching to buy
        pnl_sol = None
        pnl_pct = None
        hold_time = None
        
        if mint in buy_by_mint:
            buy_tx = buy_by_mint[mint][0]
            sol_spent = buy_tx["sol_out"]
            pnl_sol = sol_returned - sol_spent
            pnl_pct = (sol_returned / sol_spent - 1) * 100 if sol_spent > 0 else -100
            hold_time = tx["timestamp"] - buy_tx["timestamp"]
        
        try:
            c.execute("""INSERT OR IGNORE INTO live_trades 
                (mint_address, action, amount_sol, tx_signature, success,
                 executed_at, live_fill_price_sol, pnl_sol, pnl_pct, hold_time_sec)
                VALUES (?, 'SELL', ?, ?, 1, ?, ?, ?, ?, ?)""",
                (mint, sol_returned, tx["signature"], ts, 
                 sol_returned, pnl_sol, pnl_pct, hold_time))
            inserted += 1
        except Exception as e:
            print(f"  Error inserting SELL: {e}")
    
    conn.commit()
    
    # Verify
    c.execute("SELECT COUNT(*) FROM live_trades")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM live_trades WHERE action='BUY'")
    buy_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM live_trades WHERE action='SELL'")
    sell_count = c.fetchone()[0]
    c.execute("SELECT SUM(pnl_sol) FROM live_trades WHERE action='SELL' AND pnl_sol IS NOT NULL")
    total_pnl = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM live_trades WHERE action='SELL' AND pnl_sol > 0")
    win_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM live_trades WHERE action='SELL' AND pnl_sol <= 0")
    loss_count = c.fetchone()[0]
    
    print(f"\n  Inserted: {inserted} records")
    print(f"  Total live_trades: {total}")
    print(f"    Buys: {buy_count}")
    print(f"    Sells: {sell_count}")
    print(f"  Wins: {win_count} | Losses: {loss_count}")
    print(f"  Total PnL: {total_pnl:.4f} SOL")
    
    conn.close()
    print(f"\n{'='*60}")
    print(f"  BACKFILL INSERT COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
