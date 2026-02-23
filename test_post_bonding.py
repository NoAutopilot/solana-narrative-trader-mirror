#!/usr/bin/env python3
"""Post-bonding buy/sell test on a graduated Raydium token"""
import os, time, json, requests

# Load env
for line in open("trader_env.conf"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v

import live_executor as le
le.LIVE_ENABLED = True
le.LIVE_EXPERIMENT_DURATION_SEC = 0

api_key = le.PUMPPORTAL_API_KEY
test_mint = "8keKqLqfwFo1CMUpeaNNbbetJdNrBsJqZyiArH6Tbonk"
test_name = "United States Shekel1"

bal_before = le.get_wallet_balance_sol()
print(f"=== POST-BONDING BUY/SELL TEST ===")
print(f"Balance before: {bal_before} SOL")
print(f"API key length: {len(api_key)}")

# Direct PumpPortal API call with pool=pump-amm for graduated token
print(f"\nBuying 0.005 SOL of {test_name} with pool=pump-amm...")
payload = {
    "action": "buy",
    "mint": test_mint,
    "amount": 0.005,
    "denominatedInSol": True,
    "slippage": 20,
    "priorityFee": 0.0005,
    "pool": "pump-amm",
}
# PumpPortal expects api-key in the JSON body
payload["api-key"] = api_key

resp = requests.post(
    "https://pumpportal.fun/api/trade",
    headers={"Content-Type": "application/json"},
    json=payload,
    timeout=30
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")

if resp.status_code == 200:
    tx_sig = resp.text.strip().strip('"')
    print(f"\nBUY SUCCESS! TX: {tx_sig}")
    time.sleep(8)
    bal_mid = le.get_wallet_balance_sol()
    print(f"Balance after buy: {bal_mid} SOL")
    
    # Now sell with pool=pump-amm
    print(f"\nSelling 100% of {test_name} with pool=pump-amm...")
    sell_payload = {
        "action": "sell",
        "mint": test_mint,
        "amount": "100%",
        "denominatedInSol": False,
        "slippage": 20,
        "priorityFee": 0.0005,
        "pool": "pump-amm",
        "api-key": api_key
    }
    sell_resp = requests.post(
        "https://pumpportal.fun/api/trade",
        headers={"Content-Type": "application/json"},
        json=sell_payload,
        timeout=30
    )
    print(f"Sell status: {sell_resp.status_code}")
    print(f"Sell response: {sell_resp.text[:500]}")
    
    if sell_resp.status_code == 200:
        sell_tx = sell_resp.text.strip().strip('"')
        print(f"\nSELL SUCCESS! TX: {sell_tx}")
    else:
        print(f"\nSELL FAILED")
    
    time.sleep(5)
    bal_after = le.get_wallet_balance_sol()
    print(f"\nBalance after sell: {bal_after} SOL")
    print(f"Net cost of test: {bal_before - bal_after:.6f} SOL")
else:
    print(f"\nBUY FAILED: {resp.text[:500]}")
