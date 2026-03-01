"""
Test Live Execution — Single small trade to verify the PumpPortal Lightning API works.
This buys a tiny amount of a known pump.fun token, then immediately sells it.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from live_executor import (
    get_wallet_balance_sol, get_token_balance,
    execute_buy, execute_sell, can_execute_live, get_live_stats
)

def main():
    print("=" * 60)
    print("LIVE EXECUTION TEST")
    print("=" * 60)

    # 1. Check wallet balance
    balance = get_wallet_balance_sol()
    print(f"\n1. Wallet balance: {balance:.6f} SOL")
    if balance is None or balance < 0.01:
        print("   ABORT: Balance too low or unavailable")
        return

    # 2. Check safety gates
    can_trade, reason = can_execute_live()
    print(f"\n2. Can execute live: {can_trade} ({reason})")
    if not can_trade:
        print("   ABORT: Safety check failed")
        return

    # 3. Print live stats
    stats = get_live_stats()
    print(f"\n3. Live stats:")
    print(f"   Enabled: {stats['enabled']}")
    print(f"   Trade size: {stats['trade_size_sol']} SOL")
    print(f"   Slippage: {stats['slippage_pct']}%")
    print(f"   Priority fee: {stats['priority_fee']} SOL")

    # 4. Find a recent pump.fun token to test with
    # We'll use the PumpPortal websocket to get a fresh token
    import websocket as ws
    import threading

    test_mint = None
    test_name = None

    def on_message(wsapp, message):
        nonlocal test_mint, test_name
        try:
            data = json.loads(message)
            if data.get("mint"):
                test_mint = data["mint"]
                test_name = data.get("name", "Unknown")
                wsapp.close()
        except:
            pass

    def on_open(wsapp):
        wsapp.send(json.dumps({"method": "subscribeNewToken"}))

    print(f"\n4. Connecting to PumpPortal to find a fresh token...")
    wsapp = ws.WebSocketApp(
        "<REDACTED_WSS>/api/data",
        on_message=on_message,
        on_open=on_open,
    )
    ws_thread = threading.Thread(target=wsapp.run_forever, kwargs={"ping_interval": 20})
    ws_thread.daemon = True
    ws_thread.start()

    # Wait up to 30 seconds for a token
    for i in range(30):
        if test_mint:
            break
        time.sleep(1)

    if not test_mint:
        print("   ABORT: No token found in 30 seconds")
        return

    print(f"   Found: {test_name} ({test_mint[:16]}...)")

    # 5. Execute a tiny buy (0.001 SOL — absolute minimum)
    test_amount = 0.001  # Use minimum possible for testing
    print(f"\n5. Executing BUY: {test_amount} SOL of {test_name}...")
    buy_result = execute_buy(
        mint_address=test_mint,
        token_name=test_name,
        amount_sol=test_amount
    )
    print(f"   Success: {buy_result['success']}")
    print(f"   TX: {buy_result.get('tx_signature', 'N/A')}")
    if buy_result.get('error'):
        print(f"   Error: {buy_result['error']}")

    if not buy_result['success']:
        print("\n   BUY FAILED — stopping test")
        return

    # 6. Wait a moment, check token balance
    print(f"\n6. Waiting 5 seconds for confirmation...")
    time.sleep(5)
    token_balance = get_token_balance(test_mint)
    print(f"   Token balance: {token_balance}")

    # 7. Execute sell (100% of tokens)
    print(f"\n7. Executing SELL: 100% of {test_name}...")
    sell_result = execute_sell(
        mint_address=test_mint,
        token_name=test_name,
        sell_pct=100
    )
    print(f"   Success: {sell_result['success']}")
    print(f"   TX: {sell_result.get('tx_signature', 'N/A')}")
    if sell_result.get('error'):
        print(f"   Error: {sell_result['error']}")

    # 8. Final balance check
    print(f"\n8. Waiting 5 seconds for sell confirmation...")
    time.sleep(5)
    final_balance = get_wallet_balance_sol()
    print(f"   Starting balance: {balance:.6f} SOL")
    print(f"   Final balance:    {final_balance:.6f} SOL")
    print(f"   Net cost:         {balance - final_balance:.6f} SOL")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
