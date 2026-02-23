#!/usr/bin/env python3
"""
Forensic analysis: Why no live moonshots?
Compare live vs paper execution to find structural gaps.
"""
import sys
sys.path.insert(0, "/root/solana_trader")
import sqlite3
from datetime import datetime, timedelta

db = sqlite3.connect("/root/solana_trader/data/solana_trader.db")
db.row_factory = sqlite3.Row

print("=" * 70)
print("FORENSIC MOONSHOT ANALYSIS")
print("=" * 70)

# 1. Live trading window
live_start = db.execute("SELECT MIN(executed_at) FROM live_trades").fetchone()[0]
live_end = db.execute("SELECT MAX(executed_at) FROM live_trades").fetchone()[0]
print(f"\n1. LIVE TRADING WINDOW: {live_start} to {live_end}")

# 2. Paper moonshots during live window
print("\n2. PAPER MOONSHOTS DURING LIVE WINDOW")
print("-" * 50)
paper_moonshots = db.execute("""
    SELECT id, token_name, token_symbol, mint_address, trade_mode, 
           entered_at, exit_at, pnl_pct, pnl_sol, exit_reason,
           entry_sol, exit_sol
    FROM trades 
    WHERE pnl_pct > 1.0 
    AND exit_at >= ?
    ORDER BY pnl_pct DESC
""", (live_start,)).fetchall()

print(f"Total paper moonshots (>100% gain) since live start: {len(paper_moonshots)}")
for m in paper_moonshots:
    print(f"\n  {m['token_name']} ({m['trade_mode']}): +{m['pnl_pct']*100:.0f}% = +{m['pnl_sol']:.4f} SOL")
    print(f"    Entry: {m['entered_at']}, Exit: {m['exit_at']}, Reason: {m['exit_reason']}")
    
    # Check if this token had a live buy
    live_buy = db.execute(
        "SELECT * FROM live_trades WHERE mint_address=? AND action='buy'",
        (m['mint_address'],)
    ).fetchone()
    if live_buy:
        print(f"    LIVE BUY: YES, success={live_buy['success']}, tx={live_buy['tx_signature']}")
        live_sell = db.execute(
            "SELECT * FROM live_trades WHERE mint_address=? AND action='sell'",
            (m['mint_address'],)
        ).fetchone()
        if live_sell:
            live_pnl_pct = (live_sell['pnl_pct'] or 0) * 100
            print(f"    LIVE SELL: YES, pnl={live_sell['pnl_sol']:.4f} SOL ({live_pnl_pct:.1f}%)")
            print(f"    PAPER vs LIVE GAP: paper={m['pnl_pct']*100:.0f}% vs live={live_pnl_pct:.1f}%")
        else:
            print(f"    LIVE SELL: NO — position may still be open or sell failed")
    else:
        print(f"    LIVE BUY: NO")
        if m['trade_mode'] != 'proactive':
            print(f"    REASON: trade_mode={m['trade_mode']} (filtered out)")
        else:
            print(f"    REASON: UNKNOWN — proactive but no live buy! INVESTIGATE")

# 3. Proactive capture rate
print("\n3. PROACTIVE PAPER TRADES vs LIVE EXECUTION")
print("-" * 50)
proactive_paper = db.execute("""
    SELECT COUNT(*) FROM trades 
    WHERE trade_mode='proactive' AND entered_at >= ?
""", (live_start,)).fetchone()[0]
proactive_live = db.execute("SELECT COUNT(*) FROM live_trades WHERE action='buy'").fetchone()[0]
print(f"Proactive paper trades since live start: {proactive_paper}")
print(f"Live buys executed: {proactive_live}")
print(f"Capture rate: {proactive_live/max(proactive_paper,1)*100:.1f}%")

# Proactive trades that DIDN'T get live buys
proactive_no_live = db.execute("""
    SELECT t.id, t.token_name, t.mint_address, t.entered_at, t.pnl_pct, t.pnl_sol, t.exit_reason
    FROM trades t
    WHERE t.trade_mode='proactive' AND t.entered_at >= ?
    AND t.mint_address NOT IN (SELECT mint_address FROM live_trades WHERE action='buy')
    ORDER BY t.pnl_pct DESC
    LIMIT 15
""", (live_start,)).fetchall()

if proactive_no_live:
    print(f"\nTop proactive trades that MISSED live execution:")
    for t in proactive_no_live:
        pnl_str = f"+{t['pnl_pct']*100:.0f}%" if t['pnl_pct'] and t['pnl_pct'] > 0 else f"{(t['pnl_pct'] or 0)*100:.0f}%"
        print(f"  {t['token_name']}: {pnl_str} ({t['pnl_sol'] or 0:.4f} SOL) entered {t['entered_at']} exit={t['exit_reason']}")

# 4. Buy timing analysis
print("\n4. BUY TIMING: LIVE vs PAPER")
print("-" * 50)
timing_data = db.execute("""
    SELECT t.token_name, t.entered_at as paper_entry, lt.executed_at as live_entry,
           t.pnl_pct, t.pnl_sol
    FROM trades t
    JOIN live_trades lt ON t.mint_address = lt.mint_address AND lt.action='buy'
    WHERE t.trade_mode='proactive' AND t.entered_at >= ?
    ORDER BY t.entered_at DESC
""", (live_start,)).fetchall()

delays = []
for td in timing_data:
    try:
        pe = td['paper_entry'].replace('Z', '').replace('+00:00', '')
        le = td['live_entry'].replace('Z', '').replace('+00:00', '')
        paper_t = datetime.fromisoformat(pe)
        live_t = datetime.fromisoformat(le)
        delay = (live_t - paper_t).total_seconds()
        delays.append(delay)
        if abs(delay) > 5:
            print(f"  SLOW: {td['token_name']}: {delay:.1f}s delay (paper pnl={td['pnl_pct']*100:.0f}%)")
    except Exception as e:
        pass

if delays:
    print(f"\nBuy delay stats (live - paper):")
    print(f"  Avg: {sum(delays)/len(delays):.1f}s")
    print(f"  Min: {min(delays):.1f}s, Max: {max(delays):.1f}s")
    print(f"  Median: {sorted(delays)[len(delays)//2]:.1f}s")

# 5. Sell comparison for completed round trips
print("\n5. SELL PNL COMPARISON (LIVE vs PAPER)")
print("-" * 50)
sell_comparison = db.execute("""
    SELECT lb.token_name, lb.mint_address,
           lb.executed_at as live_buy_time, ls.executed_at as live_sell_time,
           ls.pnl_sol as live_pnl, ls.pnl_pct as live_pnl_pct,
           t.pnl_sol as paper_pnl, t.pnl_pct as paper_pnl_pct,
           t.exit_reason
    FROM live_trades lb
    JOIN live_trades ls ON lb.mint_address = ls.mint_address AND ls.action='sell'
    JOIN trades t ON lb.mint_address = t.mint_address AND t.trade_mode='proactive'
    WHERE lb.action='buy' AND lb.success=1
    ORDER BY (t.pnl_pct - COALESCE(ls.pnl_pct, 0)) DESC
    LIMIT 20
""").fetchall()

if sell_comparison:
    print(f"Completed round trips with paper match: {len(sell_comparison)}")
    
    big_gaps = [s for s in sell_comparison if s['paper_pnl_pct'] and s['paper_pnl_pct'] > 0.3]
    if big_gaps:
        print(f"\nTrades where paper was >30% but live was worse:")
        for sc in big_gaps:
            pp = (sc['paper_pnl_pct'] or 0) * 100
            lp = (sc['live_pnl_pct'] or 0) * 100
            print(f"  {sc['token_name']}: paper={pp:.0f}% vs live={lp:.1f}% (gap={pp-lp:.0f}%) reason={sc['exit_reason']}")

# 6. Failed buys
print("\n6. FAILED LIVE BUYS")
print("-" * 50)
failed_count = db.execute("SELECT COUNT(*) FROM live_trades WHERE action='buy' AND success=0").fetchone()[0]
success_count = db.execute("SELECT COUNT(*) FROM live_trades WHERE action='buy' AND success=1").fetchone()[0]
print(f"Successful: {success_count}, Failed: {failed_count}, Rate: {success_count/max(success_count+failed_count,1)*100:.0f}%")

failed = db.execute(
    "SELECT token_name, error, executed_at FROM live_trades WHERE action='buy' AND success=0 ORDER BY executed_at DESC LIMIT 10"
).fetchall()
for f in failed:
    print(f"  {f['token_name']}: {f['error']}")

# 7. Current status
print("\n7. CURRENT STATUS")
print("-" * 50)
total_buys = db.execute("SELECT COUNT(*) FROM live_trades WHERE action='buy' AND success=1").fetchone()[0]
total_sells = db.execute("SELECT COUNT(*) FROM live_trades WHERE action='sell'").fetchone()[0]
realized_pnl = db.execute("SELECT SUM(pnl_sol) FROM live_trades WHERE action='sell'").fetchone()[0] or 0
print(f"Successful buys: {total_buys}")
print(f"Sells: {total_sells}")
print(f"Realized PnL: {realized_pnl:.4f} SOL")

# 8. Expected vs actual moonshot rate
print("\n8. EXPECTED vs ACTUAL MOONSHOT RATE")
print("-" * 50)
total_proactive = db.execute("SELECT COUNT(*) FROM trades WHERE trade_mode='proactive'").fetchone()[0]
proactive_moonshots = db.execute("SELECT COUNT(*) FROM trades WHERE trade_mode='proactive' AND pnl_pct > 1.0").fetchone()[0]
moonshot_rate = proactive_moonshots / max(total_proactive, 1)
print(f"Paper proactive moonshot rate (all time): {moonshot_rate*100:.1f}% ({proactive_moonshots}/{total_proactive})")
print(f"Live trades completed: {total_buys}")
print(f"Expected moonshots at paper rate: {total_buys * moonshot_rate:.1f}")
print(f"Actual live moonshots (>100%): 0")
prob_zero = (1 - moonshot_rate) ** total_buys
print(f"P(0 moonshots in {total_buys} trades): {prob_zero*100:.1f}%")

# 9. Check if the TP change is affecting things — trades that hit >15% but didn't moonshot
print("\n9. TRAILING TP BEHAVIOR CHECK")
print("-" * 50)
# Check live trades that had positive paper PnL
positive_paper = db.execute("""
    SELECT t.token_name, t.pnl_pct as paper_pnl, ls.pnl_pct as live_pnl, t.exit_reason
    FROM trades t
    JOIN live_trades ls ON t.mint_address = ls.mint_address AND ls.action='sell'
    WHERE t.trade_mode='proactive' AND t.entered_at >= ? AND t.pnl_pct > 0.15
    ORDER BY t.pnl_pct DESC
""", (live_start,)).fetchall()

if positive_paper:
    print(f"Trades where paper gained >15% (trailing TP zone):")
    for pp in positive_paper:
        paper_p = (pp['paper_pnl'] or 0) * 100
        live_p = (pp['live_pnl'] or 0) * 100
        print(f"  {pp['token_name']}: paper={paper_p:.0f}% live={live_p:.1f}% reason={pp['exit_reason']}")
else:
    print("No trades hit >15% in paper during live window")

# 10. Check concurrent position count — are we hitting the limit?
print("\n10. CONCURRENT POSITION CHECK")
print("-" * 50)
open_positions = db.execute("""
    SELECT COUNT(*) FROM live_trades lb
    WHERE lb.action='buy' AND lb.success=1
    AND lb.mint_address NOT IN (SELECT mint_address FROM live_trades WHERE action='sell')
""").fetchone()[0]
print(f"Currently open live positions: {open_positions}")

db.close()
print("\n" + "=" * 70)
