#!/usr/bin/env python3
"""
System Health Audit — Adversarial check against Operating Principles
Verifies the trading system is in proper working order for live deployment.
"""

import os
import sys
import json
import time
import sqlite3
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "solana_trader.db")
RPC = os.getenv("HELIUS_RPC_URL", "")
WALLET = os.getenv("WALLET_ADDRESS", "")
PUMPPORTAL_KEY = os.getenv("PUMPPORTAL_API_KEY", "")

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"
INFO = "ℹ️  INFO"

results = []

def check(name, status, detail):
    results.append((name, status, detail))
    print(f"  {status}: {name}")
    if detail:
        print(f"         {detail}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ============================================================
# 1. INFRASTRUCTURE HEALTH
# ============================================================
section("1. INFRASTRUCTURE HEALTH")

# Check DB exists and is readable
if os.path.exists(DB_PATH):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades")
        total = c.fetchone()[0]
        check("Database accessible", PASS, f"{total} trades in DB")
    except Exception as e:
        check("Database accessible", FAIL, str(e))
        conn = None
else:
    check("Database accessible", FAIL, f"DB not found at {DB_PATH}")
    conn = None

# Check RPC connectivity
try:
    r = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":"getHealth"}, timeout=10)
    health = r.json().get("result")
    if health == "ok":
        check("Helius RPC connection", PASS, "Health: ok")
    else:
        check("Helius RPC connection", WARN, f"Health: {health}")
except Exception as e:
    check("Helius RPC connection", FAIL, str(e))

# Check wallet balance
try:
    r = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[WALLET]}, timeout=10)
    balance = r.json()["result"]["value"] / 1e9
    if balance >= 0.5:
        check("Wallet balance for live trading", PASS, f"{balance:.4f} SOL")
    elif balance >= 0.1:
        check("Wallet balance for live trading", WARN, f"{balance:.4f} SOL — minimum viable but tight")
    else:
        check("Wallet balance for live trading", FAIL, f"{balance:.4f} SOL — insufficient for live trading (need ~1 SOL)")
except Exception as e:
    check("Wallet balance for live trading", FAIL, str(e))

# Check wallet is clean (no stuck tokens)
try:
    r = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":"getTokenAccountsByOwner",
        "params":[WALLET, {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}, {"encoding":"jsonParsed"}]}, timeout=10)
    accounts = r.json()["result"]["value"]
    with_tokens = [a for a in accounts if int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) > 0]
    if len(with_tokens) == 0:
        check("Wallet clean (no stuck tokens)", PASS, f"{len(accounts)} accounts, 0 with tokens")
    else:
        check("Wallet clean (no stuck tokens)", FAIL, f"{len(with_tokens)} accounts still hold tokens")
except Exception as e:
    check("Wallet clean (no stuck tokens)", FAIL, str(e))

# Check PumpPortal API key
if PUMPPORTAL_KEY and len(PUMPPORTAL_KEY) > 20:
    check("PumpPortal API key configured", PASS, f"Key length: {len(PUMPPORTAL_KEY)}")
else:
    check("PumpPortal API key configured", FAIL, "Missing or too short")

# Check paper trader process
import subprocess
try:
    result = subprocess.run(["pgrep", "-f", "paper_trader"], capture_output=True, text=True)
    if result.stdout.strip():
        pids = result.stdout.strip().split("\n")
        check("Paper trader running", PASS, f"PID(s): {', '.join(pids)}")
    else:
        check("Paper trader running", FAIL, "No paper_trader process found")
except:
    check("Paper trader running", WARN, "Could not check process status")


# ============================================================
# 2. CONFIGURATION AUDIT
# ============================================================
section("2. CONFIGURATION AUDIT")

# Check config.py for 5-min timeout
config_path = os.path.join(os.path.dirname(__file__), "config", "config.py")
try:
    with open(config_path) as f:
        config_text = f.read()
    
    # Parse TIMEOUT_MINUTES
    import re
    timeout_match = re.search(r'TIMEOUT_MINUTES\s*=\s*(\d+)', config_text)
    if timeout_match:
        timeout = int(timeout_match.group(1))
        if timeout == 5:
            check("Timeout set to 5 minutes", PASS, f"TIMEOUT_MINUTES = {timeout}")
        else:
            check("Timeout set to 5 minutes", FAIL, f"TIMEOUT_MINUTES = {timeout} (should be 5)")
    
    # Parse TAKE_PROFIT_PCT
    tp_match = re.search(r'TAKE_PROFIT_PCT\s*=\s*([\d.]+)', config_text)
    if tp_match:
        tp = float(tp_match.group(1))
        check("Take profit configured", INFO, f"TAKE_PROFIT_PCT = {tp} ({tp*100}%)")
    
    # Parse STOP_LOSS_PCT
    sl_match = re.search(r'STOP_LOSS_PCT\s*=\s*([-\d.]+)', config_text)
    if sl_match:
        sl = float(sl_match.group(1))
        check("Stop loss configured", INFO, f"STOP_LOSS_PCT = {sl} ({sl*100}%)")
    
    # Parse MAX_CONCURRENT_TRADES
    max_match = re.search(r'MAX_CONCURRENT_TRADES\s*=\s*(\d+)', config_text)
    if max_match:
        max_trades = int(max_match.group(1))
        check("Max concurrent trades", INFO, f"MAX_CONCURRENT_TRADES = {max_trades}")
    
    # Check LIVE_ENABLED in .env
    live_enabled = os.getenv("LIVE_ENABLED", "false").lower()
    if live_enabled == "false":
        check("Live trading disabled (safe for testing)", PASS, f"LIVE_ENABLED = {live_enabled}")
    else:
        check("Live trading ENABLED", WARN, f"LIVE_ENABLED = {live_enabled} — real money at risk!")

except Exception as e:
    check("Config file readable", FAIL, str(e))


# ============================================================
# 3. DATA QUALITY AUDIT (Principle 2: Scientific Data Collection)
# ============================================================
section("3. DATA QUALITY AUDIT")

if conn:
    c = conn.cursor()
    
    # Total trades
    c.execute("SELECT COUNT(*) FROM trades")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM trades WHERE status='closed'")
    closed = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM trades WHERE status='open'")
    open_t = c.fetchone()[0]
    
    check("Trade count", INFO, f"Total: {total}, Closed: {closed}, Open: {open_t}")
    
    # Sample size check (Principle 2)
    if closed >= 100:
        check("Sample size for conclusions (n>=100)", PASS, f"n={closed}")
    elif closed >= 50:
        check("Sample size for conclusions (n>=100)", WARN, f"n={closed} — preliminary only, need 100+")
    else:
        check("Sample size for conclusions (n>=100)", FAIL, f"n={closed} — too small for any conclusions")
    
    # Check trade modes (control group exists?)
    c.execute("SELECT trade_mode, COUNT(*) FROM trades GROUP BY trade_mode")
    modes = dict(c.fetchall())
    if "control" in modes and modes.get("control", 0) > 0:
        check("Control group present (Principle 2)", PASS, f"Modes: {dict(modes)}")
    else:
        check("Control group present (Principle 2)", FAIL, f"No control group! Modes: {dict(modes)}")
    
    # Check PnL concentration (Principle 3: outlier test)
    c.execute("SELECT pnl_sol FROM trades WHERE status='closed' ORDER BY pnl_sol DESC")
    pnls = [r[0] for r in c.fetchall() if r[0] is not None]
    if pnls:
        total_pnl = sum(pnls)
        top1_pnl = pnls[0] if pnls else 0
        top3_pnl = sum(pnls[:3])
        top5_pnl = sum(pnls[:5])
        
        without_top1 = total_pnl - top1_pnl
        without_top3 = total_pnl - top3_pnl
        without_top5 = total_pnl - top5_pnl
        
        check("Total PnL", INFO, f"+{total_pnl:.4f} SOL")
        
        if total_pnl > 0 and without_top1 > 0:
            check("Outlier test: remove top 1", PASS, f"Still profitable: +{without_top1:.4f} SOL")
        elif total_pnl > 0:
            pct = (top1_pnl / total_pnl * 100) if total_pnl > 0 else 0
            check("Outlier test: remove top 1", FAIL, f"Unprofitable without top trade! Top 1 = {pct:.0f}% of PnL")
        
        if total_pnl > 0 and without_top3 > 0:
            check("Outlier test: remove top 3", PASS, f"Still profitable: +{without_top3:.4f} SOL")
        elif total_pnl > 0:
            pct = (top3_pnl / total_pnl * 100) if total_pnl > 0 else 0
            check("Outlier test: remove top 3", FAIL, f"Unprofitable without top 3! Top 3 = {pct:.0f}% of PnL")
        
        if total_pnl > 0 and without_top5 > 0:
            check("Outlier test: remove top 5", PASS, f"Still profitable: +{without_top5:.4f} SOL")
        elif total_pnl > 0:
            pct = (top5_pnl / total_pnl * 100) if total_pnl > 0 else 0
            check("Outlier test: remove top 5", FAIL, f"Unprofitable without top 5! Top 5 = {pct:.0f}% of PnL")
    
    # Win rate
    c.execute("SELECT COUNT(*) FROM trades WHERE status='closed' AND pnl_sol > 0")
    wins = c.fetchone()[0]
    if closed > 0:
        wr = wins / closed * 100
        check("Win rate", INFO, f"{wr:.1f}% ({wins}/{closed})")
    
    # Check timeout exits are at 5 min (not 15)
    c.execute("""SELECT exit_reason, COUNT(*), AVG(hold_minutes) 
                 FROM trades WHERE status='closed' 
                 GROUP BY exit_reason""")
    exit_reasons = c.fetchall()
    for reason, count, avg_hold in exit_reasons:
        if reason == "timeout":
            if avg_hold and avg_hold <= 6:
                check("Timeout exits at 5 min", PASS, f"Avg hold for timeouts: {avg_hold:.1f} min (n={count})")
            elif avg_hold:
                check("Timeout exits at 5 min", WARN, f"Avg hold for timeouts: {avg_hold:.1f} min (n={count}) — expected ~5")
        check(f"Exit reason: {reason}", INFO, f"n={count}, avg hold={avg_hold:.1f} min" if avg_hold else f"n={count}")
    
    # Check for data gaps
    c.execute("SELECT MIN(entered_at), MAX(entered_at) FROM trades")
    min_t, max_t = c.fetchone()
    if min_t and max_t:
        check("Data time range", INFO, f"From {min_t} to {max_t}")


# ============================================================
# 4. LIVE TRADING READINESS (Principle 7 & 8)
# ============================================================
section("4. LIVE TRADING READINESS")

# Fee model check
check("Fee model", INFO, "8% round-trip minimum, 15-25% conservative estimate for low-liquidity tokens")

# Check if live_executor.py exists and has sell routing
live_exec_path = os.path.join(os.path.dirname(__file__), "live_executor.py")
if os.path.exists(live_exec_path):
    with open(live_exec_path) as f:
        le_text = f.read()
    
    if "pool" in le_text and "auto" in le_text:
        check("Live executor: pool=auto routing", PASS, "Post-migration sell routing configured")
    else:
        check("Live executor: pool=auto routing", FAIL, "Missing pool=auto — post-migration sells will fail")
    
    if "execute_sell" in le_text:
        check("Live executor: sell function", PASS, "execute_sell found")
    else:
        check("Live executor: sell function", FAIL, "No sell function!")
    
    if "execute_buy" in le_text:
        check("Live executor: buy function", PASS, "execute_buy found")
    else:
        check("Live executor: buy function", FAIL, "No buy function!")
else:
    check("Live executor exists", FAIL, "live_executor.py not found!")

# Check rent_reclaim exists
reclaim_path = os.path.join(os.path.dirname(__file__), "rent_reclaim.py")
if os.path.exists(reclaim_path):
    check("Rent reclaim script", PASS, "rent_reclaim.py found")
else:
    check("Rent reclaim script", FAIL, "rent_reclaim.py not found — stuck tokens won't be cleaned up")

# Check backup system
backup_path = os.path.join(os.path.dirname(__file__), "backup_to_github.py")
if os.path.exists(backup_path):
    check("GitHub backup script", PASS, "backup_to_github.py found")
else:
    check("GitHub backup script", WARN, "No backup script — data loss risk on reset")

# Check burn_and_close
burn_path = os.path.join(os.path.dirname(__file__), "burn_and_close.py")
if os.path.exists(burn_path):
    check("Burn & close script", PASS, "burn_and_close.py found")
else:
    check("Burn & close script", WARN, "No burn_and_close.py — dead tokens can't be cleaned")


# ============================================================
# 5. ADVERSARIAL CHECKLIST STATUS
# ============================================================
section("5. ADVERSARIAL CHECKLIST STATUS (Principle 3)")

print("""
  These require manual evaluation with sufficient data:
  
  [ ] Outlier test: Remove top 1,3,5 trades — does system still profit?
  [ ] Time-window test: Profit across each 4-hour block?
  [ ] Selectivity test: >70% token rejection rate?
  [ ] Coverage test: Metrics cover >90% of trades?
  [ ] Fee test: Profitable after 8-15% fees?
  [ ] Sample size: n>100 per group?
  [ ] Multi-test agreement: Parametric + non-parametric + bootstrap agree?
  [ ] Simulation-reality gap: Virtual PnL within 2x of actual?
  [ ] On-chain verification: Every profit traceable to Solscan TX?
  [x] Bonding curve: Post-migration selling proven (5/5)
  [ ] Falsification conditions stated for each finding?
  [ ] Base rate comparison: Better than random token selection?
""")

# ============================================================
# SUMMARY
# ============================================================
section("SUMMARY")

passes = sum(1 for _, s, _ in results if s == PASS)
fails = sum(1 for _, s, _ in results if s == FAIL)
warns = sum(1 for _, s, _ in results if s == WARN)
infos = sum(1 for _, s, _ in results if s == INFO)

print(f"\n  {PASS}: {passes}")
print(f"  {FAIL}: {fails}")
print(f"  {WARN}: {warns}")
print(f"  {INFO}: {infos}")

if fails > 0:
    print(f"\n  ❌ SYSTEM NOT READY FOR LIVE TRADING — {fails} critical issue(s)")
    print("\n  Failed checks:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"    - {name}: {detail}")
else:
    print(f"\n  ✅ All critical checks passed")

if warns > 0:
    print(f"\n  Warnings:")
    for name, status, detail in results:
        if status == WARN:
            print(f"    - {name}: {detail}")

if conn:
    conn.close()
