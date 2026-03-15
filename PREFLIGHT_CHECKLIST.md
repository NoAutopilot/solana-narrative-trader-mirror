# Pre-Flight Checklist — Live Experiment

**Version:** v4.1 | **Last Updated:** 2026-02-23
**Principle:** Trust nothing, prove everything. Every item must be verified from the running system, not from memory.

---

## 1. WALLET STATE (on-chain verification required)

```bash
# Run this — do not skip
python3 -c "
import requests
HELIUS_RPC='https://mainnet.helius-rpc.com/?api-key=REDACTED'
WALLET='REDACTED_WALLET_ADDRESS'
# Balance
r = requests.post(HELIUS_RPC, json={'jsonrpc':'2.0','id':1,'method':'getBalance','params':[WALLET]}, timeout=10)
bal = r.json()['result']['value'] / 1e9
print(f'Wallet balance: {bal:.6f} SOL')
# Token accounts
r2 = requests.post(HELIUS_RPC, json={'jsonrpc':'2.0','id':1,'method':'getTokenAccountsByOwner','params':[WALLET,{'programId':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'},{'encoding':'jsonParsed'}]}, timeout=10)
accs = r2.json().get('result',{}).get('value',[])
nonzero = [a for a in accs if int(a['account']['data']['parsed']['info']['tokenAmount']['amount']) > 0]
print(f'Token accounts with balance: {len(nonzero)}')
print(f'Empty token accounts: {len(accs) - len(nonzero)}')
# Open live positions in DB
import sqlite3
db = sqlite3.connect('/root/solana_trader/data/solana_trader.db')
open_live = db.execute('''
    SELECT COUNT(*) FROM live_trades lt
    WHERE UPPER(lt.action) = \"BUY\" AND lt.success = 1
    AND NOT EXISTS (SELECT 1 FROM live_trades lt2 WHERE lt2.paper_trade_id = lt.paper_trade_id AND UPPER(lt2.action) = \"SELL\")
''').fetchone()[0]
print(f'Open live positions in DB: {open_live}')
"
```

**PASS criteria:**
- [ ] Wallet balance >= target deposit amount
- [ ] Token accounts with balance = 0
- [ ] Open live positions in DB = 0

---

## 2. ENV CONFIG VERIFICATION

**File:** `/root/solana_trader/trader_env.conf` (the ONLY source of truth for live config)

| Setting | Expected Value | Why |
|---|---|---|
| `LIVE_ENABLED` | `true` | Master switch |
| `LIVE_TRADE_SIZE_SOL` | `0.02` | Small bets, more runway |
| `LIVE_SLIPPAGE_PCT` | `20` | Standard for pump.fun |
| `LIVE_PRIORITY_FEE` | `0.0001` | Minimum priority |
| `LIVE_CONVICTION_FILTER` | `proactive_only` | CRITICAL: only proactive trades go live |
| `LIVE_BUY_POOL` | `smart` | v4.0+ smart routing |
| `MAX_LIVE_TRADES_PER_HOUR` | `100` | Rate limit |
| `MAX_CONCURRENT_LIVE_TRADES` | `15` | Position limit |
| `MAX_SOL_PER_TRADE` | `0.05` | Safety cap |
| `MIN_WALLET_BALANCE_SOL` | `0.01` | Reserve for rent |
| `LIVE_EXPERIMENT_DURATION_SEC` | `14400` | 4 hours (adjust per experiment) |

```bash
# Verify — read the actual file, don't trust memory
cat /root/solana_trader/trader_env.conf | grep -E "LIVE_|MAX_|MIN_"
```

- [ ] All values match expected table above
- [ ] **CONVICTION_FILTER is proactive_only** (check twice — this has been wrong before)

---

## 3. CODE VERSION

```bash
head -10 /root/solana_trader/live_executor.py
git -C /root/solana_trader log --oneline -3
```

- [ ] live_executor.py is v4.1 or later
- [ ] VPS code matches latest GitHub commit

---

## 4. SERVICE RESTART & VERIFICATION

```bash
# Restart
systemctl restart solana-trader

# Wait
sleep 30

# Verify clean startup
journalctl -u solana-trader --since "1 min ago" --no-pager

# Verify runtime config matches env file
curl -s http://localhost:5050/api/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
checks = {
    'trade_size_sol': 0.02,
    'conviction_filter': 'proactive_only',
    'buy_pool': 'smart',
    'experiment_duration_sec': 14400,
    'experiment_halted': False,
    'enabled': True,
    'emergency_halted': False,
    'open_live_trades': 0,
}
all_pass = True
for k, expected in checks.items():
    actual = d.get(k)
    status = 'PASS' if actual == expected else 'FAIL'
    if status == 'FAIL': all_pass = False
    print(f'  [{status}] {k}: expected={expected} actual={actual}')
print(f'\nOVERALL: {\"ALL PASS\" if all_pass else \"FAILED — DO NOT PROCEED\"}')"
```

- [ ] No errors in startup logs
- [ ] ALL config checks pass
- [ ] **If ANY check fails: DO NOT PROCEED. Fix and re-run.**

---

## 5. POST-FIRST-BUY HEALTH CHECK (run 2-3 minutes after experiment starts)

```bash
# Confirm live buys are happening
grep "LIVE BUY" /root/solana_trader/logs/paper_trader.log | tail -5

# Confirm they're all proactive (not narrative or control)
grep "LIVE BUY" /root/solana_trader/logs/paper_trader.log | grep -v "proactive" | head -5
# ^ This should return NOTHING. If it returns lines, STOP IMMEDIATELY.

# Check wallet balance is decreasing as expected
curl -s http://localhost:5050/api/status | python3 -c "
import sys, json; d = json.load(sys.stdin)
print(f'Balance: {d[\"wallet_balance_sol\"]:.4f} SOL')
print(f'Live trades: {d[\"total_live_trades\"]}')
print(f'SOL spent: {d[\"total_sol_spent\"]:.4f}')
print(f'Experiment elapsed: {d.get(\"experiment_elapsed_sec\", 0):.0f}s')
print(f'Experiment halted: {d[\"experiment_halted\"]}')"
```

- [ ] Live buys appearing in logs
- [ ] ALL live buys are proactive mode
- [ ] Wallet balance decreasing by ~0.02 per trade
- [ ] Experiment timer is running

---

## 6. ONGOING MONITORING (check every 30 minutes)

```bash
python3 -c "
import sqlite3, json, requests
from datetime import datetime, timedelta

db = sqlite3.connect('/root/solana_trader/data/solana_trader.db')

# Live stats
live = db.execute('''
    SELECT COUNT(*) as total,
           SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as success,
           SUM(CASE WHEN UPPER(action)=\"BUY\" AND success=1 THEN amount_sol ELSE 0 END) as spent,
           SUM(CASE WHEN UPPER(action)=\"SELL\" AND success=1 THEN amount_sol ELSE 0 END) as received
    FROM live_trades
    WHERE executed_at > datetime('now', '-4 hours')
''').fetchone()
print(f'=== LIVE (last 4h) ===')
print(f'Total TXs: {live[0]} | Successful: {live[1]}')
print(f'SOL spent: {live[2] or 0:.4f} | SOL received: {live[3] or 0:.4f} | Net: {(live[3] or 0) - (live[2] or 0):+.4f}')

# Buy success rate
buys = db.execute('''
    SELECT COUNT(*) as total, SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as ok
    FROM live_trades WHERE UPPER(action)=\"BUY\" AND executed_at > datetime('now', '-4 hours')
''').fetchone()
sell_s = db.execute('''
    SELECT COUNT(*) as total, SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as ok
    FROM live_trades WHERE UPPER(action)=\"SELL\" AND executed_at > datetime('now', '-4 hours')
''').fetchone()
print(f'Buy success: {buys[1] or 0}/{buys[0]} | Sell success: {sell_s[1] or 0}/{sell_s[0]}')

# Check for stuck positions (buy success=1 but no sell, older than 5 min)
stuck = db.execute('''
    SELECT COUNT(*) FROM live_trades lt
    WHERE UPPER(lt.action)=\"BUY\" AND lt.success=1
    AND lt.executed_at < datetime('now', '-5 minutes')
    AND NOT EXISTS (SELECT 1 FROM live_trades lt2 WHERE lt2.paper_trade_id=lt.paper_trade_id AND UPPER(lt2.action)=\"SELL\")
''').fetchone()[0]
print(f'Stuck positions (>5min): {stuck}')

# Conviction filter leak check
leak = db.execute('''
    SELECT t.trade_mode, COUNT(*) FROM trades t
    JOIN live_trades lt ON lt.paper_trade_id=t.id AND UPPER(lt.action)=\"BUY\"
    WHERE t.entered_at > datetime('now', '-4 hours')
    AND t.trade_mode != 'proactive'
    GROUP BY t.trade_mode
''').fetchall()
if leak:
    print(f'ALERT: CONVICTION FILTER LEAK: {leak}')
else:
    print(f'Conviction filter: clean (proactive only)')

# Wallet
r = requests.post('https://mainnet.helius-rpc.com/?api-key=REDACTED',
    json={'jsonrpc':'2.0','id':1,'method':'getBalance','params':['REDACTED_WALLET_ADDRESS']}, timeout=10)
bal = r.json()['result']['value'] / 1e9
print(f'Wallet balance: {bal:.4f} SOL')
"
```

**STOP CONDITIONS (halt immediately if any occur):**
- [ ] Conviction filter leak (non-proactive trade sent to live)
- [ ] Buy success rate < 80%
- [ ] Stuck positions > 3
- [ ] Wallet draining faster than expected (> 0.02 SOL per trade average)
- [ ] Any unexpected error patterns in logs

---

## 7. POST-EXPERIMENT REVIEW

After experiment timer expires (or manual halt):

```bash
# Full accounting
python3 -c "
import sqlite3, requests
db = sqlite3.connect('/root/solana_trader/data/solana_trader.db')

# Get experiment window
first = db.execute('SELECT MIN(executed_at) FROM live_trades WHERE executed_at > datetime(\"now\", \"-5 hours\")').fetchone()[0]
last = db.execute('SELECT MAX(executed_at) FROM live_trades WHERE executed_at > datetime(\"now\", \"-5 hours\")').fetchone()[0]
print(f'Experiment window: {first} to {last}')

# Trades
buys = db.execute('SELECT COUNT(*), SUM(amount_sol) FROM live_trades WHERE UPPER(action)=\"BUY\" AND success=1 AND executed_at > datetime(\"now\", \"-5 hours\")').fetchone()
sells = db.execute('SELECT COUNT(*), SUM(amount_sol) FROM live_trades WHERE UPPER(action)=\"SELL\" AND success=1 AND executed_at > datetime(\"now\", \"-5 hours\")').fetchone()
print(f'Buys: {buys[0]} for {buys[1] or 0:.4f} SOL')
print(f'Sells: {sells[0]} for {sells[1] or 0:.4f} SOL')
print(f'Net PnL: {(sells[1] or 0) - (buys[1] or 0):+.4f} SOL')

# Moonshots captured?
moonshots = db.execute('''
    SELECT lt.token_name, lt.pnl_sol, lt.pnl_pct, t.exit_reason
    FROM live_trades lt JOIN trades t ON t.id = lt.paper_trade_id
    WHERE UPPER(lt.action)=\"SELL\" AND lt.success=1 AND lt.pnl_sol > 0.02
    AND lt.executed_at > datetime(\"now\", \"-5 hours\")
    ORDER BY lt.pnl_sol DESC LIMIT 10
''').fetchall()
print(f'\nMoonshots (pnl > 0.02 SOL): {len(moonshots)}')
for m in moonshots:
    print(f'  {m[0]}: {m[1]:+.4f} SOL ({m[2]:+.1%}) exit={m[3]}')

# On-chain balance
r = requests.post('https://mainnet.helius-rpc.com/?api-key=REDACTED',
    json={'jsonrpc':'2.0','id':1,'method':'getBalance','params':['REDACTED_WALLET_ADDRESS']}, timeout=10)
bal = r.json()['result']['value'] / 1e9
print(f'\nFinal wallet balance: {bal:.4f} SOL')
"
```

---

## HISTORY OF MISTAKES (why this checklist exists)

| Date | Mistake | Root Cause | Checklist Item |
|---|---|---|---|
| 2026-02-21 | Ran live with narrative_only filter | Env config not verified after edit | Step 2, Step 4 |
| 2026-02-21 | Second attempt also had wrong filter | Same — didn't verify API output | Step 4 (curl check) |
| 2026-02-23 | Bonk tokens sent to wrong pool | No bonk pool support | Step 3 (v4.1 check) |
| 2026-02-23 | 5 stuck positions from phantom buys | bg verify didn't update DB | Step 3 (v4.1 check) |
