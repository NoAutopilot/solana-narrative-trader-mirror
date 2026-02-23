#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("/root/solana_trader/data/solana_trader.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== TOO MUCH WINNING - PAPER TRADES ===")
trades = c.execute("SELECT * FROM trades WHERE token_name LIKE '%Too Much Winning%' ORDER BY entered_at DESC").fetchall()
for t in trades:
    d = dict(t)
    print(f"ID: {d['id']}")
    print(f"  Name: {d['token_name']} ({d['token_symbol']})")
    print(f"  Mint: {d['mint_address']}")
    print(f"  Mode: {d['trade_mode']}")
    print(f"  Entry: {d['entered_at']}")
    print(f"  Exit: {d['exit_at']}")
    print(f"  Entry price: {d['entry_price_usd']}")
    print(f"  Exit price: {d['exit_price_usd']}")
    print(f"  PnL SOL: {d['pnl_sol']}")
    print(f"  PnL pct (raw ratio): {d['pnl_pct']}")
    print(f"  PnL pct (actual): {d['pnl_pct']*100:.1f}%")
    print(f"  Exit reason: {d['exit_reason']}")
    
    # Check if exit price is a bonding curve cap
    ep = d['exit_price_usd']
    if ep and 3.0e-06 < ep < 4.5e-06:
        print(f"  *** BONDING CURVE CAP EXIT (exit price {ep:.3e}) ***")
    
    mint = d["mint_address"]
    lives = c.execute("SELECT * FROM live_trades WHERE mint_address=?", (mint,)).fetchall()
    if lives:
        print(f"  LIVE TRADES:")
        for l in lives:
            ld = dict(l)
            print(f"    {ld['action']} | {ld['amount_sol']} SOL | success={ld['success']} | error={ld['error']} | tx={ld['tx_signature']}")
    else:
        print(f"  NO LIVE TRADES")
    print()

# Also check: how many paper trades during the live experiment period have phantom PnL?
print("=== PHANTOM PNL DURING LIVE EXPERIMENT (since 22:19 UTC) ===")
phantoms = c.execute("""
    SELECT token_name, pnl_sol, pnl_pct*100, exit_price_usd, mint_address, trade_mode, exit_reason
    FROM trades 
    WHERE status='closed' 
    AND entered_at > '2026-02-23T22:19:00'
    AND exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06
    AND pnl_pct > 1.0
    ORDER BY pnl_sol DESC
""").fetchall()
total_phantom = 0
for p in phantoms:
    total_phantom += p[1]
    # Check if live trade exists
    live = c.execute("SELECT success FROM live_trades WHERE mint_address=? AND action='buy'", (p[4],)).fetchone()
    live_status = f"live_buy={'OK' if live and live[0]==1 else 'FAIL' if live else 'NONE'}"
    print(f"  {p[0]:30s} | +{p[1]:.2f} SOL | {p[2]:.0f}% | {p[5]} | {p[6]} | {live_status}")

print(f"\nTotal phantom PnL during experiment: {total_phantom:.2f} SOL")

conn.close()
