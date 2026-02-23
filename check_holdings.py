import sqlite3, os, requests
from dotenv import load_dotenv
load_dotenv('/root/solana_trader/trader_env.conf')
WALLET = os.environ.get('WALLET_ADDRESS')
RPC = os.environ.get('HELIUS_RPC_URL')

# Get all Token-2022 holdings
resp = requests.post(RPC, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'getTokenAccountsByOwner',
    'params': [WALLET, {'programId': 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'}, {'encoding': 'jsonParsed'}]
}, timeout=15)
accounts = resp.json().get('result', {}).get('value', [])

conn = sqlite3.connect('/root/solana_trader/data/solana_trader.db')

print("Token holdings vs live_trades:")
for a in accounts:
    info = a['account']['data']['parsed']['info']
    mint = info['mint']
    amt = info['tokenAmount']['uiAmountString']
    
    buys = conn.execute("SELECT token_name, executed_at FROM live_trades WHERE mint_address=? AND action='buy'", (mint,)).fetchall()
    sells = conn.execute("SELECT token_name, executed_at, success FROM live_trades WHERE mint_address=? AND action='sell'", (mint,)).fetchall()
    
    name = buys[0][0] if buys else "unknown"
    buy_time = buys[0][1][:19] if buys else "none"
    sell_count = len(sells)
    sell_success = sum(1 for s in sells if s[2])
    
    status = "OPEN" if not sells else f"SOLD({sell_success}/{sell_count})"
    print(f"  {name[:30]:30s} | {status:12s} | tokens={float(amt):>12.2f} | buy={buy_time}")

# Open positions in DB
open_live = conn.execute("""
    SELECT lt.token_name, lt.mint_address, lt.executed_at 
    FROM live_trades lt 
    WHERE lt.action='buy' AND lt.success=1
    AND lt.paper_trade_id NOT IN (SELECT paper_trade_id FROM live_trades WHERE action='sell')
""").fetchall()
print(f"\nOpen positions in DB: {len(open_live)}")
for o in open_live:
    print(f"  {o[0]}: {o[2]}")

# Also check the backup JSON for pre-reset trades
import json
try:
    with open('/root/solana_trader/data/live_trades_backup_pre_proactive.json') as f:
        backup = json.load(f)
    backup_mints = set()
    for t in backup:
        if t.get('action') == 'buy' and t.get('mint_address'):
            backup_mints.add(t['mint_address'])
    
    current_mints = set(a['account']['data']['parsed']['info']['mint'] for a in accounts)
    pre_reset_held = backup_mints & current_mints
    if pre_reset_held:
        print(f"\nPre-reset tokens still held: {len(pre_reset_held)}")
        for m in pre_reset_held:
            name = [t['token_name'] for t in backup if t.get('mint_address') == m and t.get('action') == 'buy']
            print(f"  {name[0] if name else 'unknown'}: {m[:12]}...")
except Exception as e:
    print(f"\nCould not check backup: {e}")

conn.close()
