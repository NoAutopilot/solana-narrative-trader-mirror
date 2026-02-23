#!/usr/bin/env python3
"""
Force sell all stranded Token-2022 tokens and close accounts to reclaim rent.
These are from pre-reset trades where sells failed.
"""
import os
import sys
import time
import requests

sys.path.insert(0, '/root/solana_trader')
from dotenv import load_dotenv
load_dotenv('/root/solana_trader/trader_env.conf')

from live_executor import execute_sell

WALLET = os.environ.get('WALLET_ADDRESS')
RPC = os.environ.get('HELIUS_RPC_URL')

# Get all Token-2022 holdings
resp = requests.post(RPC, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'getTokenAccountsByOwner',
    'params': [WALLET, {'programId': 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'}, {'encoding': 'jsonParsed'}]
}, timeout=15)
accounts = resp.json().get('result', {}).get('value', [])

print(f"Found {len(accounts)} Token-2022 accounts to process")

total_recovered = 0
for i, a in enumerate(accounts):
    info = a['account']['data']['parsed']['info']
    mint = info['mint']
    amt = float(info['tokenAmount']['uiAmountString'])
    
    if amt <= 0:
        print(f"  [{i+1}/{len(accounts)}] {mint[:12]}... already empty, skipping")
        continue
    
    print(f"  [{i+1}/{len(accounts)}] Selling {amt:.2f} tokens of {mint[:12]}...")
    
    try:
        result = execute_sell(
            mint_address=mint,
            token_name=f"stranded_{mint[:8]}",
            sell_pct=100,
            paper_trade_id=-1
        )
        
        if result and result.get('success'):
            sol_received = result.get('sol_received', 0) or 0
            total_recovered += sol_received
            print(f"    SOLD: received {sol_received:.6f} SOL | tx={result.get('tx_signature', 'N/A')[:30]}...")
        else:
            error = result.get('error', 'unknown') if result else 'no result'
            print(f"    FAILED: {error}")
    except Exception as e:
        print(f"    ERROR: {e}")
    
    time.sleep(2)  # Rate limit

# Check final balance
bal = requests.post(RPC, json={'jsonrpc': '2.0', 'id': 1, 'method': 'getBalance', 'params': [WALLET]}, timeout=10)
final_bal = bal.json().get('result', {}).get('value', 0) / 1e9

print(f"\n{'='*50}")
print(f"Total SOL recovered from stranded tokens: {total_recovered:.6f}")
print(f"Final wallet balance: {final_bal:.6f} SOL")
