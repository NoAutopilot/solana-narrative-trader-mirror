#!/usr/bin/env python3
"""
Backfill live trading data from on-chain wallet transaction history.
Uses Helius Enhanced Transactions API to pull all historical buys/sells.
"""

import os
import sys
import json
import time
import sqlite3
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

RPC = os.getenv("HELIUS_RPC_URL", "")
WALLET = os.getenv("WALLET_ADDRESS", "")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "solana_trader.db")

# Extract Helius API key from RPC URL
API_KEY = RPC.split("api-key=")[-1] if "api-key=" in RPC else ""
HELIUS_API = f"https://api.helius.xyz/v0"


def get_all_transactions(wallet, api_key, limit=100):
    """Fetch all transaction signatures for the wallet using Helius."""
    all_sigs = []
    before = None
    
    while True:
        url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={api_key}&limit={limit}"
        if before:
            url += f"&before={before}"
        
        print(f"  Fetching batch (before={before[:20] if before else 'start'})...")
        r = requests.get(url, timeout=30)
        
        if r.status_code != 200:
            print(f"  Error {r.status_code}: {r.text[:200]}")
            break
        
        txs = r.json()
        if not txs:
            break
        
        all_sigs.extend(txs)
        before = txs[-1].get("signature")
        
        print(f"  Got {len(txs)} transactions (total: {len(all_sigs)})")
        
        if len(txs) < limit:
            break
        
        time.sleep(0.5)  # Rate limiting
    
    return all_sigs


def parse_swap_transaction(tx, wallet):
    """Parse a Helius enhanced transaction to extract swap details."""
    result = {
        "signature": tx.get("signature", ""),
        "timestamp": tx.get("timestamp", 0),
        "type": tx.get("type", ""),
        "source": tx.get("source", ""),
        "fee_sol": tx.get("fee", 0) / 1e9 if tx.get("fee") else 0,
        "fee_lamports": tx.get("fee", 0),
    }
    
    # Parse token transfers to identify buys vs sells
    token_transfers = tx.get("tokenTransfers", [])
    native_transfers = tx.get("nativeTransfers", [])
    
    sol_in = 0  # SOL received by wallet
    sol_out = 0  # SOL sent from wallet
    tokens_in = []  # Tokens received
    tokens_out = []  # Tokens sent
    
    for nt in native_transfers:
        if nt.get("toUserAccount") == wallet:
            sol_in += nt.get("amount", 0) / 1e9
        if nt.get("fromUserAccount") == wallet:
            sol_out += nt.get("amount", 0) / 1e9
    
    for tt in token_transfers:
        token_info = {
            "mint": tt.get("mint", ""),
            "amount": tt.get("tokenAmount", 0),
            "from": tt.get("fromUserAccount", ""),
            "to": tt.get("toUserAccount", ""),
        }
        
        if tt.get("toUserAccount") == wallet:
            tokens_in.append(token_info)
        elif tt.get("fromUserAccount") == wallet:
            tokens_out.append(token_info)
    
    result["sol_in"] = sol_in
    result["sol_out"] = sol_out
    result["tokens_in"] = tokens_in
    result["tokens_out"] = tokens_out
    
    # Classify: BUY = SOL out, tokens in. SELL = tokens out, SOL in.
    if sol_out > 0.001 and tokens_in:
        result["action"] = "BUY"
        result["sol_amount"] = sol_out
        result["token_mint"] = tokens_in[0]["mint"]
        result["token_amount"] = tokens_in[0]["amount"]
    elif tokens_out and sol_in > 0.001:
        result["action"] = "SELL"
        result["sol_amount"] = sol_in
        result["token_mint"] = tokens_out[0]["mint"]
        result["token_amount"] = tokens_out[0]["amount"]
    elif tokens_out and tokens_in:
        # Token-to-token swap (rare on pump.fun)
        result["action"] = "SWAP"
        result["token_mint"] = tokens_in[0]["mint"] if tokens_in else tokens_out[0]["mint"]
    else:
        result["action"] = "OTHER"
    
    return result


def match_buys_and_sells(parsed_txs):
    """Match buy and sell transactions by token mint to reconstruct trades."""
    buys = {}  # mint -> list of buys
    sells = {}  # mint -> list of sells
    
    for tx in parsed_txs:
        if tx["action"] == "BUY":
            mint = tx["token_mint"]
            if mint not in buys:
                buys[mint] = []
            buys[mint].append(tx)
        elif tx["action"] == "SELL":
            mint = tx["token_mint"]
            if mint not in sells:
                sells[mint] = []
            sells[mint].append(tx)
    
    trades = []
    all_mints = set(list(buys.keys()) + list(sells.keys()))
    
    for mint in all_mints:
        buy_list = sorted(buys.get(mint, []), key=lambda x: x["timestamp"])
        sell_list = sorted(sells.get(mint, []), key=lambda x: x["timestamp"])
        
        trade = {
            "token_mint": mint,
            "buys": buy_list,
            "sells": sell_list,
            "total_sol_in": sum(b["sol_amount"] for b in buy_list),
            "total_sol_out": sum(s["sol_amount"] for s in sell_list),
            "total_fees": sum(b["fee_sol"] for b in buy_list) + sum(s["fee_sol"] for s in sell_list),
            "buy_count": len(buy_list),
            "sell_count": len(sell_list),
            "first_buy_time": buy_list[0]["timestamp"] if buy_list else None,
            "last_sell_time": sell_list[-1]["timestamp"] if sell_list else None,
        }
        
        if trade["total_sol_in"] > 0:
            trade["pnl_sol"] = trade["total_sol_out"] - trade["total_sol_in"]
            trade["pnl_pct"] = (trade["total_sol_out"] / trade["total_sol_in"] - 1) * 100
            trade["slippage_and_fees_pct"] = trade["total_fees"] / trade["total_sol_in"] * 100
        else:
            trade["pnl_sol"] = trade["total_sol_out"]
            trade["pnl_pct"] = 0
            trade["slippage_and_fees_pct"] = 0
        
        if trade["first_buy_time"] and trade["last_sell_time"]:
            trade["hold_seconds"] = trade["last_sell_time"] - trade["first_buy_time"]
            trade["status"] = "closed"
        elif trade["first_buy_time"]:
            trade["hold_seconds"] = None
            trade["status"] = "open_or_abandoned"
        else:
            trade["hold_seconds"] = None
            trade["status"] = "sell_only"
        
        trades.append(trade)
    
    return trades


def backfill_to_db(trades, parsed_txs, db_path):
    """Write the backfilled data to the live_trades table."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Check existing live_trades schema
    c.execute("PRAGMA table_info(live_trades)")
    columns = [col[1] for col in c.fetchall()]
    
    if not columns:
        print("  live_trades table doesn't exist — creating it")
        c.execute("""CREATE TABLE IF NOT EXISTS live_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_mint TEXT,
            token_name TEXT,
            action TEXT,
            sol_amount REAL,
            token_amount REAL,
            tx_signature TEXT UNIQUE,
            timestamp TEXT,
            timestamp_unix INTEGER,
            fee_sol REAL,
            status TEXT,
            pnl_sol REAL,
            pnl_pct REAL,
            hold_seconds INTEGER,
            total_sol_in REAL,
            total_sol_out REAL,
            total_fees REAL,
            buy_count INTEGER,
            sell_count INTEGER,
            source TEXT DEFAULT 'backfill_from_chain'
        )""")
    
    # Insert individual transactions
    inserted = 0
    for tx in parsed_txs:
        if tx["action"] in ("BUY", "SELL"):
            try:
                c.execute("""INSERT OR IGNORE INTO live_trades 
                    (token_mint, action, sol_amount, token_amount, tx_signature, 
                     timestamp, timestamp_unix, fee_sol, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tx.get("token_mint", ""),
                     tx["action"],
                     tx.get("sol_amount", 0),
                     tx.get("token_amount", 0),
                     tx["signature"],
                     datetime.fromtimestamp(tx["timestamp"], tz=timezone.utc).isoformat(),
                     tx["timestamp"],
                     tx["fee_sol"],
                     "backfill_from_chain"))
                inserted += 1
            except Exception as e:
                print(f"  Error inserting tx {tx['signature'][:20]}: {e}")
    
    conn.commit()
    print(f"  Inserted {inserted} transaction records")
    
    # Also save the reconstructed trades summary
    c.execute("""CREATE TABLE IF NOT EXISTS backfill_trade_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_mint TEXT,
        status TEXT,
        total_sol_in REAL,
        total_sol_out REAL,
        total_fees REAL,
        pnl_sol REAL,
        pnl_pct REAL,
        hold_seconds INTEGER,
        buy_count INTEGER,
        sell_count INTEGER,
        first_buy_time INTEGER,
        last_sell_time INTEGER,
        backfill_date TEXT
    )""")
    
    for t in trades:
        c.execute("""INSERT INTO backfill_trade_summary
            (token_mint, status, total_sol_in, total_sol_out, total_fees,
             pnl_sol, pnl_pct, hold_seconds, buy_count, sell_count,
             first_buy_time, last_sell_time, backfill_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (t["token_mint"], t["status"], t["total_sol_in"], t["total_sol_out"],
             t["total_fees"], t["pnl_sol"], t["pnl_pct"], t["hold_seconds"],
             t["buy_count"], t["sell_count"], t["first_buy_time"],
             t["last_sell_time"], datetime.now(timezone.utc).isoformat()))
    
    conn.commit()
    conn.close()
    print(f"  Saved {len(trades)} trade summaries")


def main():
    print("=" * 60)
    print("  BACKFILL FROM ON-CHAIN DATA")
    print("=" * 60)
    
    print(f"\nWallet: {WALLET}")
    print(f"Database: {DB_PATH}")
    
    # Step 1: Fetch all transactions
    print(f"\n--- Step 1: Fetching all wallet transactions ---")
    all_txs = get_all_transactions(WALLET, API_KEY)
    print(f"  Total transactions: {len(all_txs)}")
    
    if not all_txs:
        print("  No transactions found!")
        return
    
    # Step 2: Parse each transaction
    print(f"\n--- Step 2: Parsing transactions ---")
    parsed = []
    for tx in all_txs:
        p = parse_swap_transaction(tx, WALLET)
        parsed.append(p)
    
    # Categorize
    actions = {}
    for p in parsed:
        a = p["action"]
        actions[a] = actions.get(a, 0) + 1
    
    print(f"  Transaction types: {actions}")
    
    buys = [p for p in parsed if p["action"] == "BUY"]
    sells = [p for p in parsed if p["action"] == "SELL"]
    
    print(f"  Buys: {len(buys)}")
    print(f"  Sells: {len(sells)}")
    
    # Step 3: Show sample data
    print(f"\n--- Step 3: Sample transactions ---")
    for p in parsed[:5]:
        if p["action"] in ("BUY", "SELL"):
            ts = datetime.fromtimestamp(p["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {p['action']} | {p.get('sol_amount', 0):.4f} SOL | fee: {p['fee_sol']:.6f} | {ts} | {p['signature'][:30]}...")
    
    # Step 4: Match buys and sells into trades
    print(f"\n--- Step 4: Matching buys and sells into trades ---")
    trades = match_buys_and_sells(parsed)
    
    closed = [t for t in trades if t["status"] == "closed"]
    abandoned = [t for t in trades if t["status"] == "open_or_abandoned"]
    sell_only = [t for t in trades if t["status"] == "sell_only"]
    
    print(f"  Reconstructed trades: {len(trades)}")
    print(f"    Closed (buy+sell): {len(closed)}")
    print(f"    Open/abandoned (buy only): {len(abandoned)}")
    print(f"    Sell only (no matching buy): {len(sell_only)}")
    
    # Step 5: Summary stats
    print(f"\n--- Step 5: Trade Summary ---")
    total_sol_in = sum(t["total_sol_in"] for t in trades)
    total_sol_out = sum(t["total_sol_out"] for t in trades)
    total_fees = sum(t["total_fees"] for t in trades)
    total_pnl = total_sol_out - total_sol_in
    
    print(f"  Total SOL deployed: {total_sol_in:.4f}")
    print(f"  Total SOL returned: {total_sol_out:.4f}")
    print(f"  Total TX fees: {total_fees:.4f}")
    print(f"  Net PnL (before fees): {total_pnl:.4f}")
    print(f"  Net PnL (after fees): {total_pnl - total_fees:.4f}")
    
    if closed:
        print(f"\n  Closed trade details:")
        wins = 0
        for t in sorted(closed, key=lambda x: x["first_buy_time"]):
            ts = datetime.fromtimestamp(t["first_buy_time"], tz=timezone.utc).strftime("%m/%d %H:%M")
            hold = f"{t['hold_seconds']}s" if t["hold_seconds"] else "?"
            pnl_str = f"+{t['pnl_pct']:.1f}%" if t["pnl_pct"] >= 0 else f"{t['pnl_pct']:.1f}%"
            status = "WIN" if t["pnl_sol"] > 0 else "LOSS"
            if t["pnl_sol"] > 0:
                wins += 1
            print(f"    {ts} | {t['token_mint'][:20]}... | in={t['total_sol_in']:.4f} out={t['total_sol_out']:.4f} | {pnl_str} | hold={hold} | fees={t['total_fees']:.6f} | {status}")
        
        print(f"\n  Win rate: {wins}/{len(closed)} ({wins/len(closed)*100:.1f}%)")
    
    if abandoned:
        print(f"\n  Abandoned/open positions (bought but never sold):")
        for t in abandoned:
            ts = datetime.fromtimestamp(t["first_buy_time"], tz=timezone.utc).strftime("%m/%d %H:%M")
            print(f"    {ts} | {t['token_mint'][:20]}... | deployed={t['total_sol_in']:.4f} SOL | buys={t['buy_count']}")
    
    # Step 6: Backfill to database
    print(f"\n--- Step 6: Writing to database ---")
    backfill_to_db(trades, parsed, DB_PATH)
    
    # Step 7: Save raw data to JSON for reference
    output_path = os.path.join(os.path.dirname(__file__), "data", "backfill_raw.json")
    with open(output_path, "w") as f:
        json.dump({
            "wallet": WALLET,
            "backfill_date": datetime.now(timezone.utc).isoformat(),
            "total_transactions": len(all_txs),
            "parsed_transactions": parsed,
            "reconstructed_trades": trades,
            "summary": {
                "total_sol_in": total_sol_in,
                "total_sol_out": total_sol_out,
                "total_fees": total_fees,
                "net_pnl": total_pnl,
                "closed_trades": len(closed),
                "abandoned_trades": len(abandoned),
            }
        }, f, indent=2, default=str)
    print(f"  Raw data saved to {output_path}")
    
    print(f"\n{'='*60}")
    print(f"  BACKFILL COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
