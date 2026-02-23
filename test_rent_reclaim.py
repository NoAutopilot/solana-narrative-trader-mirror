#!/usr/bin/env python3
"""Test rent reclaim on recently sold tokens."""
import sys
sys.path.insert(0, "/root/solana_trader")
from rent_reclaim import find_token_account_for_mint, close_single_account
import sqlite3

conn = sqlite3.connect("/root/solana_trader/data/solana_trader.db")
rows = conn.execute(
    "SELECT DISTINCT mint_address, token_name FROM live_trades WHERE action='SELL' ORDER BY executed_at DESC LIMIT 10"
).fetchall()
conn.close()

total_reclaimed = 0
for mint, name in rows:
    print(f"Checking: {name} ({mint[:12]}...)")
    acc = find_token_account_for_mint(mint)
    if acc:
        amt = acc["amount"]
        lamports = acc["lamports"]
        print(f"  Account found: amount={amt}, lamports={lamports}")
        if amt == 0:
            success, result = close_single_account(acc["pubkey"], acc["program_id"])
            if success:
                rent = lamports / 1e9
                total_reclaimed += rent
                print(f"  CLOSED! Recovered {rent:.6f} SOL")
            else:
                print(f"  Close failed: {result}")
        else:
            print(f"  NOT EMPTY (amount={amt}) — sell may not have drained fully")
    else:
        print(f"  No account found (already closed)")

print(f"\nTotal reclaimed: {total_reclaimed:.6f} SOL")
