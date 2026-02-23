#!/usr/bin/env python3
"""Phase 3: Comprehensive issue quantification and strategy simulation."""
import sqlite3
import json

DB = "/root/solana_trader/data/solana_trader.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=" * 70)
print("COMPREHENSIVE ISSUE & STRATEGY ANALYSIS")
print("=" * 70)

# ============================================================
# ISSUE 1: Phantom PnL from bonding curve cap exits
# ============================================================
print("\n" + "=" * 70)
print("ISSUE 1: PHANTOM PNL (Bonding Curve Cap Exits)")
print("=" * 70)

# These are trades where exit_price is at the bonding curve cap
# They represent prices that are NOT tradeable on-chain
cap_trades = c.execute("""
    SELECT token_name, pnl_sol, pnl_pct*100, exit_price_usd, mint_address,
           entry_price_usd, hold_minutes, trade_mode
    FROM trades 
    WHERE status='closed' 
    AND exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06
    AND pnl_pct > 1.0
    ORDER BY pnl_sol DESC
""").fetchall()

print(f"Total phantom trades: {len(cap_trades)}")
print(f"Total phantom PnL: {sum(t[1] for t in cap_trades):.2f} SOL")
print(f"Avg phantom PnL: {sum(t[2] for t in cap_trades)/len(cap_trades):.0f}%")

# What's the REAL total PnL?
total_pnl = c.execute("SELECT SUM(pnl_sol) FROM trades WHERE status='closed'").fetchone()[0]
real_pnl = total_pnl - sum(t[1] for t in cap_trades)
print(f"\nTotal paper PnL (with phantoms): {total_pnl:.2f} SOL")
print(f"Total paper PnL (without phantoms): {real_pnl:.2f} SOL")
print(f"Phantom inflation: {sum(t[1] for t in cap_trades)/total_pnl*100:.1f}% of reported PnL")

# ============================================================
# ISSUE 2: Trailing TP shakeout problem
# ============================================================
print("\n" + "=" * 70)
print("ISSUE 2: TRAILING TP SHAKEOUT (the HENRY problem)")
print("=" * 70)

# 190/277 trailing_tp exits are negative
# The trailing TP activates at 15% gross, trails 8%
# This means it triggers on initial volatility noise

trailing_neg = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp' AND pnl_pct < 0
""").fetchone()
trailing_pos = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp' AND pnl_pct >= 0
""").fetchone()
trailing_total = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol)
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp'
""").fetchone()

print(f"Total trailing_tp exits: {trailing_total[0]}")
print(f"  Negative: {trailing_neg[0]} ({trailing_neg[0]/trailing_total[0]*100:.0f}%) | PnL: {trailing_neg[1]:+.2f} SOL | Avg: {trailing_neg[2]:+.1f}%")
print(f"  Positive: {trailing_pos[0]} ({trailing_pos[0]/trailing_total[0]*100:.0f}%) | PnL: {trailing_pos[1]:+.2f} SOL | Avg: {trailing_pos[2]:+.1f}%")
print(f"  Net PnL: {trailing_total[1]:+.2f} SOL")
print(f"\nProblem: 69% of trailing_tp exits are LOSSES")
print(f"The trailing TP is destroying value, not protecting it")

# ============================================================
# ISSUE 3: Platform routing failures
# ============================================================
print("\n" + "=" * 70)
print("ISSUE 3: PLATFORM ROUTING FAILURES")
print("=" * 70)

# Check all failed buys
failed_buys = c.execute("""
    SELECT token_name, mint_address, error, executed_at
    FROM live_trades WHERE action='buy' AND success=0
    ORDER BY executed_at
""").fetchall()
print(f"Total failed buys: {len(failed_buys)}")
for f in failed_buys:
    suffix = f[1][-4:] if f[1] else "????"
    print(f"  {f[0]:30s} | suffix={suffix} | {f[2][:60]}")

# Check what platforms paper is trading that live can't
print("\nPaper trades by platform (mint suffix):")
for suffix in ['pump', 'bonk']:
    cnt = c.execute(f"SELECT COUNT(*) FROM trades WHERE status='closed' AND mint_address LIKE '%{suffix}'").fetchone()[0]
    pnl = c.execute(f"SELECT SUM(pnl_sol) FROM trades WHERE status='closed' AND mint_address LIKE '%{suffix}'").fetchone()[0]
    print(f"  {suffix}: {cnt} trades, {pnl:+.2f} SOL")

other = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol) FROM trades 
    WHERE status='closed' 
    AND mint_address NOT LIKE '%pump' 
    AND mint_address NOT LIKE '%bonk'
""").fetchone()
print(f"  other: {other[0]} trades, {other[1]:+.2f} SOL")

# ============================================================
# ISSUE 4: Phantom sell bug (race condition)
# ============================================================
print("\n" + "=" * 70)
print("ISSUE 4: PHANTOM SELL BUG (optimistic buy → async fail → stale sell)")
print("=" * 70)
print("Root cause: execute_buy returns success=True optimistically")
print("Background thread later finds on-chain failure")
print("But live_trade_map in paper_trader.py is NOT updated")
print("So paper_trader still triggers sell for tokens never bought")
print()
phantom_sells = c.execute("""
    SELECT b.token_name, b.error as buy_error, s.amount_sol as sell_amount, s.error as sell_error
    FROM live_trades b
    JOIN live_trades s ON b.paper_trade_id = s.paper_trade_id AND s.action='sell'
    WHERE b.action='buy' AND b.success=0
""").fetchall()
print(f"Phantom sell attempts: {len(phantom_sells)}")
for p in phantom_sells:
    print(f"  {p[0]}: buy_error={p[1][:50]}... sell_amount={p[2]:.2f} SOL")

# ============================================================
# STRATEGY SIMULATION: What if we changed exit parameters?
# ============================================================
print("\n" + "=" * 70)
print("STRATEGY SIMULATIONS")
print("=" * 70)

# Current config: TP=100% (disabled), SL=-25%, timeout=2min, trailing=15%/8%
# The data shows:
# - ALL profitable trades happen in 30-60 second window
# - 247/364 moonshots (>100%) happen in 30-45 seconds
# - Trailing TP destroys value (69% negative exits)
# - timeout trades break even (+2.49 SOL on 2893 trades)

# Simulation 1: Remove trailing TP entirely
print("\n--- Simulation 1: REMOVE trailing TP ---")
print("Current trailing_tp PnL: +2.12 SOL (277 trades)")
print("If removed: these trades go to timeout or SL instead")
print("  190 negative trades (avg -13.8%) → likely timeout at ~0% or SL at -25%")
print("  87 positive trades (avg +89%) → likely still caught by TP or timeout")
print("  HENRY-type tokens: would stay in position, potentially capturing moonshots")
print("  Risk: some would bleed to -25% SL instead of exiting at -13.8%")

# Simulation 2: Higher trailing TP activation (50% instead of 15%)
print("\n--- Simulation 2: Raise trailing activation to 50% ---")
trailing_by_peak = c.execute("""
    SELECT pnl_pct, entry_price_usd, exit_price_usd, pnl_sol
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp'
    AND entry_price_usd > 0 AND exit_price_usd > 0
""").fetchall()

would_not_activate = 0
would_not_activate_pnl = 0
for t in trailing_by_peak:
    exit_mult = t[2] / t[1]
    peak_mult = exit_mult / 0.92
    peak_gross = (peak_mult - 1)
    if peak_gross < 0.50:  # Would not activate at 50% threshold
        would_not_activate += 1
        would_not_activate_pnl += t[3]

print(f"  Trades that would NOT activate trailing (peak < 50%): {would_not_activate}")
print(f"  PnL from those trades: {would_not_activate_pnl:+.2f} SOL")
print(f"  These would go to timeout/SL instead → potential HENRY recovery")

# Simulation 3: Wider trail distance (20% instead of 8%)
print("\n--- Simulation 3: Widen trail distance to 20% ---")
print("  Current: sell when price drops 8% from peak")
print("  Proposed: sell when price drops 20% from peak")
print("  Effect: more room for volatility, fewer shakeouts")
print("  Risk: give back more profit on trades that do peak")

# Simulation 4: Time-based exit tiers
print("\n--- Simulation 4: Time-based exit tiers ---")
print("  Observation: 247/364 moonshots happen in 30-45 seconds")
print("  Proposed:")
print("    0-30s: Hold no matter what (moonshots are forming)")
print("    30-60s: Trailing TP with WIDE trail (30% from peak)")
print("    60-120s: Tighter trailing (15% from peak)")
print("    120s+: Timeout exit")

# ============================================================
# THE REAL NUMBERS: What matters for live trading
# ============================================================
print("\n" + "=" * 70)
print("LIVE EXPERIMENT 2 SUMMARY")
print("=" * 70)

print("Duration: ~20 minutes (stopped early for investigation)")
print("Wallet: 0.6424 → 0.4984 SOL (-0.1440 SOL, -22.4%)")
print(f"Successful round trips: 30")
print(f"Real net PnL: -0.1916 SOL")
print(f"Failed buys: 2 (EMPOROR TRUMP - LaunchLab, Too Much Winning - on-chain MinSell)")
print(f"Phantom sell attempts: 1 (Too Much Winning)")
print(f"Moonshots captured live: 0")
print(f"Moonshots in paper during same period: HENRY (+11,877%), EMPOROR TRUMP (+13,173%)")
print()
print("KEY INSIGHT: Even with perfect execution, the current exit strategy")
print("would have missed HENRY (trailing_tp shakeout) and EMPOROR TRUMP")
print("(LaunchLab platform not supported by PumpPortal).")

conn.close()
