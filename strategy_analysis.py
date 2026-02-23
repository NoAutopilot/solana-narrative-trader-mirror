#!/usr/bin/env python3
"""Comprehensive exit strategy analysis for the Solana trading bot."""
import sqlite3
import json

DB = "/root/solana_trader/data/solana_trader.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=" * 70)
print("PHASE 1: EXIT STRATEGY ANALYSIS")
print("=" * 70)

# 1. Distribution of exit reasons
print("\n=== EXIT REASON DISTRIBUTION ===")
rows = c.execute("""
    SELECT exit_reason, COUNT(*) as cnt, 
           SUM(pnl_sol) as total_pnl,
           AVG(pnl_pct) as avg_pnl_pct,
           AVG(hold_minutes) as avg_hold
    FROM trades WHERE status='closed'
    GROUP BY exit_reason ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[0]:15s} | {r[1]:5d} trades | PnL: {r[2]:+8.2f} SOL | Avg: {r[3]*100:+8.1f}% | Hold: {r[4]:.1f}min")

# 2. Trailing TP PnL distribution
print("\n=== TRAILING_TP EXIT PNL DISTRIBUTION ===")
trailing = c.execute("""
    SELECT pnl_pct, pnl_sol, token_name, hold_minutes
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp'
    ORDER BY pnl_pct
""").fetchall()

buckets = {
    'negative': [t for t in trailing if t[0] < 0],
    '0-10%': [t for t in trailing if 0 <= t[0] < 0.10],
    '10-30%': [t for t in trailing if 0.10 <= t[0] < 0.30],
    '30-100%': [t for t in trailing if 0.30 <= t[0] < 1.0],
    '100%+': [t for t in trailing if t[0] >= 1.0],
}
for name, trades in buckets.items():
    if trades:
        total = sum(t[1] for t in trades)
        avg = sum(t[0] for t in trades) / len(trades) * 100
        print(f"  {name:12s} | {len(trades):4d} trades | PnL: {total:+8.2f} SOL | Avg: {avg:+.1f}%")

# 3. The HENRY problem: trailing_tp that ended negative
print("\n=== TRAILING_TP TRADES THAT ENDED NEGATIVE (the HENRY problem) ===")
neg = buckets['negative']
print(f"  Count: {len(neg)}")
print(f"  Total PnL lost: {sum(t[1] for t in neg):.2f} SOL")
if neg:
    print(f"  Avg PnL: {sum(t[0] for t in neg)/len(neg)*100:.1f}%")
    print(f"  Examples:")
    for t in neg[:10]:
        print(f"    {t[2]:30s} | PnL: {t[0]*100:+.1f}% | Hold: {t[3]:.1f}min")

# 4. Take profit analysis - what price multiple do moonshots reach?
print("\n=== TAKE_PROFIT TRADES - PRICE MULTIPLES ===")
tp_trades = c.execute("""
    SELECT token_name, entry_price_usd, exit_price_usd, pnl_pct, pnl_sol, hold_minutes
    FROM trades WHERE status='closed' AND exit_reason='take_profit'
    ORDER BY pnl_pct DESC
""").fetchall()
print(f"  Total take_profit trades: {len(tp_trades)}")
print(f"  Total PnL: {sum(t[4] for t in tp_trades):.2f} SOL")

# Separate bonding curve cap exits from real exits
cap_exits = [t for t in tp_trades if t[2] and 3.0e-06 < t[2] < 4.5e-06]
real_exits = [t for t in tp_trades if t not in cap_exits]
print(f"\n  Bonding curve cap exits (phantom): {len(cap_exits)} trades, {sum(t[4] for t in cap_exits):.2f} SOL")
print(f"  Real take_profit exits: {len(real_exits)} trades, {sum(t[4] for t in real_exits):.2f} SOL")

if real_exits:
    print(f"\n  Real TP exit PnL distribution:")
    for t in real_exits[:15]:
        mult = t[2]/t[1] if t[1] and t[1] > 0 else 0
        print(f"    {t[0]:30s} | {mult:.1f}x | PnL: {t[3]*100:+.1f}% | {t[4]:+.2f} SOL | {t[5]:.1f}min")

# 5. Stop loss analysis
print("\n=== STOP_LOSS TRADES ===")
sl_trades = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100, AVG(hold_minutes)
    FROM trades WHERE status='closed' AND exit_reason='stop_loss'
""").fetchone()
print(f"  Count: {sl_trades[0]}")
print(f"  Total PnL: {sl_trades[1]:.2f} SOL")
print(f"  Avg PnL: {sl_trades[2]:.1f}%")
print(f"  Avg hold: {sl_trades[3]:.1f}min")

# 6. Timeout analysis
print("\n=== TIMEOUT TRADES ===")
to_trades = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100, AVG(hold_minutes)
    FROM trades WHERE status='closed' AND exit_reason='timeout'
""").fetchone()
print(f"  Count: {to_trades[0]}")
print(f"  Total PnL: {to_trades[1]:.2f} SOL")
print(f"  Avg PnL: {to_trades[2]:.1f}%")
print(f"  Avg hold: {to_trades[3]:.1f}min")

# 7. KEY QUESTION: For tokens that eventually moonshotted (>30% gain at some point),
# what was the price trajectory in the first 2 minutes?
# We can approximate by looking at tokens where take_profit fired vs trailing_tp
print("\n=== HOLD TIME vs PNL FOR ALL PROFITABLE TRADES ===")
profitable = c.execute("""
    SELECT hold_minutes, pnl_pct, pnl_sol, exit_reason, token_name
    FROM trades WHERE status='closed' AND pnl_pct > 0
    ORDER BY hold_minutes
""").fetchall()
time_buckets = {
    '0-15s': [t for t in profitable if t[0] < 0.25],
    '15-30s': [t for t in profitable if 0.25 <= t[0] < 0.5],
    '30-60s': [t for t in profitable if 0.5 <= t[0] < 1.0],
    '1-2min': [t for t in profitable if 1.0 <= t[0] < 2.0],
    '2min+': [t for t in profitable if t[0] >= 2.0],
}
for name, trades in time_buckets.items():
    if trades:
        total = sum(t[2] for t in trades)
        avg = sum(t[1] for t in trades) / len(trades) * 100
        print(f"  {name:8s} | {len(trades):4d} trades | PnL: {total:+8.2f} SOL | Avg: {avg:+.1f}%")

# 8. Proactive vs other modes
print("\n=== PROACTIVE MODE PERFORMANCE ===")
for mode in ['proactive', 'narrative', 'control']:
    row = c.execute("""
        SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100,
               SUM(CASE WHEN pnl_pct > 0.30 THEN 1 ELSE 0 END) as moonshots
        FROM trades WHERE status='closed' AND trade_mode=?
    """, (mode,)).fetchone()
    if row[0]:
        ms_rate = row[3]/row[0]*100 if row[0] else 0
        print(f"  {mode:12s} | {row[0]:5d} trades | PnL: {row[1]:+8.2f} SOL | Avg: {row[2]:+.1f}% | Moonshots: {row[3]} ({ms_rate:.1f}%)")

conn.close()
