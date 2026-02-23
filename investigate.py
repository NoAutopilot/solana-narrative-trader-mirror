import sqlite3, os, requests
from dotenv import load_dotenv
load_dotenv('/root/solana_trader/trader_env.conf')

WALLET = os.environ.get('WALLET_ADDRESS')
RPC = os.environ.get('HELIUS_RPC_URL')
conn = sqlite3.connect('/root/solana_trader/data/solana_trader.db')

# 1. ONE PIECE UNIVERSE
print('='*60)
print('1. ONE PIECE UNIVERSE TRADE')
print('='*60)
paper = conn.execute("SELECT id, trade_mode, token_name, status, pnl_sol, pnl_pct, entered_at FROM trades WHERE LOWER(token_name) LIKE '%one piece%' ORDER BY entered_at DESC").fetchall()
for p in paper:
    print(f'  PAPER: id={p[0]} mode={p[1]} name={p[2]} status={p[3]} pnl={p[4]:.4f} SOL ({p[5]:.1f}%) entered={p[6]}')

live = conn.execute("SELECT id, token_name, action, amount_sol, tx_signature, success, pnl_sol, live_fill_price_sol, executed_at FROM live_trades WHERE LOWER(token_name) LIKE '%one piece%' ORDER BY executed_at").fetchall()
if live:
    for l in live:
        sig_short = l[4][:30] if l[4] else 'None'
        print(f'  LIVE: id={l[0]} name={l[1]} action={l[2]} amount={l[3]} tx={sig_short}... success={l[5]} pnl={l[6]} fill={l[7]} at={l[8]}')
else:
    print('  NOT IN LIVE TRADES TABLE - PAPER ONLY')

# 2. WALLET
print('\n' + '='*60)
print('2. WALLET ADDRESS')
print('='*60)
print(f'  {WALLET}')
bal_resp = requests.post(RPC, json={'jsonrpc':'2.0','id':1,'method':'getBalance','params':[WALLET]}, timeout=10)
bal = bal_resp.json().get('result',{}).get('value',0) / 1e9
print(f'  Balance: {bal:.6f} SOL')

# 3. LIVE PERFORMANCE
print('\n' + '='*60)
print('3. LIVE PROACTIVE PERFORMANCE (since clean reset)')
print('='*60)
total_live = conn.execute("SELECT COUNT(*) FROM live_trades WHERE success=1").fetchone()[0]
buys = conn.execute("SELECT COUNT(*), COALESCE(SUM(ABS(live_fill_price_sol)),0) FROM live_trades WHERE action='buy' AND success=1 AND live_fill_price_sol IS NOT NULL").fetchone()
sells = conn.execute("SELECT COUNT(*), COALESCE(SUM(live_fill_price_sol),0), COALESCE(SUM(pnl_sol),0) FROM live_trades WHERE action='sell' AND success=1 AND live_fill_price_sol IS NOT NULL").fetchone()
winners = conn.execute("SELECT COUNT(*) FROM live_trades WHERE action='sell' AND pnl_sol > 0").fetchone()[0]
losers = conn.execute("SELECT COUNT(*) FROM live_trades WHERE action='sell' AND pnl_sol <= 0").fetchone()[0]
open_pos = conn.execute("SELECT COUNT(*) FROM live_trades WHERE action='buy' AND success=1 AND paper_trade_id NOT IN (SELECT paper_trade_id FROM live_trades WHERE action='sell')").fetchone()[0]

total_spent = buys[1]
total_received = sells[1]
paper_pnl = sells[2]
real_pnl = total_received - total_spent

print(f'  Total live TXs: {total_live}')
print(f'  Buys: {buys[0]} | Sells: {sells[0]} | Open: {open_pos}')
if (winners + losers) > 0:
    print(f'  Winners: {winners} | Losers: {losers} | Win rate: {winners/(winners+losers)*100:.1f}%')
print(f'  Total spent (on-chain): {total_spent:.6f} SOL')
print(f'  Total received (on-chain): {total_received:.6f} SOL')
print(f'  Real on-chain PnL: {real_pnl:+.6f} SOL')
print(f'  Paper PnL (same trades): {paper_pnl:+.6f} SOL')
print(f'  Gap: {real_pnl - paper_pnl:+.6f} SOL')

moonshots = conn.execute("SELECT token_name, pnl_pct, pnl_sol FROM live_trades WHERE action='sell' AND pnl_pct > 100").fetchall()
if moonshots:
    print(f'\n  MOONSHOTS (>100%):')
    for m in moonshots:
        print(f'    {m[0]}: {m[1]:+.1f}% ({m[2]:+.4f} SOL)')
else:
    print(f'\n  No moonshots yet')

best = conn.execute("SELECT token_name, pnl_sol, pnl_pct FROM live_trades WHERE action='sell' ORDER BY pnl_sol DESC LIMIT 3").fetchall()
worst = conn.execute("SELECT token_name, pnl_sol, pnl_pct FROM live_trades WHERE action='sell' ORDER BY pnl_sol ASC LIMIT 3").fetchall()
print(f'\n  Best trades:')
for b in best:
    print(f'    {b[0]}: {b[1]:+.6f} SOL ({b[2]:+.1f}%)')
print(f'  Worst trades:')
for w in worst:
    print(f'    {w[0]}: {w[1]:+.6f} SOL ({w[2]:+.1f}%)')

# Paper proactive baseline
pp = conn.execute("SELECT COUNT(*), SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN pnl_pct > 100 THEN 1 ELSE 0 END), AVG(pnl_pct) FROM trades WHERE trade_mode='proactive' AND status='closed' AND entered_at > datetime('now', '-24 hours')").fetchone()
if pp[0]:
    print(f'\n  --- Paper proactive baseline (24h) ---')
    print(f'  Trades: {pp[0]} | Win rate: {pp[1]/pp[0]*100:.1f}% | Moonshot rate: {pp[2]/pp[0]*100:.1f}% | Avg PnL: {pp[3]:+.1f}%')

# 4. TOKEN ACCOUNTS
print('\n' + '='*60)
print('4. TOKEN ACCOUNTS (for rent reclaim)')
print('='*60)
resp = requests.post(RPC, json={'jsonrpc':'2.0','id':1,'method':'getTokenAccountsByOwner','params':[WALLET,{'programId':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'},{'encoding':'jsonParsed'}]}, timeout=15)
accounts = resp.json().get('result',{}).get('value',[])
zero_bal = sum(1 for a in accounts if int(a['account']['data']['parsed']['info']['tokenAmount']['amount']) == 0)
nonzero = sum(1 for a in accounts if int(a['account']['data']['parsed']['info']['tokenAmount']['amount']) > 0)
print(f'  Total token accounts: {len(accounts)}')
print(f'  Zero balance (closeable): {zero_bal}')
print(f'  Non-zero (still holding): {nonzero}')
print(f'  Potential rent reclaim: ~{zero_bal * 0.00204:.4f} SOL')

conn.close()
