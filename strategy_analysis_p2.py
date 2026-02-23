#!/usr/bin/env python3
"""Phase 2: Moonshot trajectory analysis and optimal exit timing."""
import sqlite3
import json

DB = "/root/solana_trader/data/solana_trader.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=" * 70)
print("PHASE 2: MOONSHOT TRAJECTORY & OPTIMAL EXIT ANALYSIS")
print("=" * 70)

# 1. The core question: trailing_tp activates at 15% gross, trails 8%.
# 69% of trailing_tp exits are NEGATIVE. This means the activation threshold
# is too low - it's triggering on noise, not signal.

# Let's look at what the PEAK price was for trailing_tp trades that ended negative
print("\n=== PEAK PRICE ANALYSIS FOR NEGATIVE TRAILING_TP ===")
print("(These trades activated trailing at 15%+ gross, then fell)")
# We don't have peak_price in the DB directly, but we can estimate:
# If trailing activated at 15% gross, and trail distance is 8%,
# and the trade ended at X%, then peak was approximately:
# exit_price = peak * (1 - 0.08), so peak = exit_price / 0.92
# But we know gross PnL at exit = net PnL + 8% fees
# So gross at exit = pnl_pct + 0.08

neg_trailing = c.execute("""
    SELECT pnl_pct, pnl_sol, token_name, hold_minutes, entry_price_usd, exit_price_usd
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp' AND pnl_pct < 0
    ORDER BY pnl_pct
""").fetchall()

print(f"  Total negative trailing_tp: {len(neg_trailing)}")
for t in neg_trailing[:5]:
    gross_at_exit = t[0] + 0.08  # net + fees
    # peak_gross = (gross_at_exit + 0.08) / 0.92  # approximate
    # Actually: trailing triggers when price drops 8% from peak
    # So exit_price = peak * 0.92
    # gross_at_exit = (exit_price - entry) / entry = (peak*0.92 - entry) / entry
    # peak_gross = (gross_at_exit / 0.92 + 1) - 1... let me just compute
    if t[4] and t[5] and t[4] > 0:
        exit_mult = t[5] / t[4]
        peak_mult = exit_mult / 0.92  # peak was 8% higher than exit
        peak_gain = (peak_mult - 1) * 100
        print(f"    {t[2]:30s} | Exit: {t[0]*100:+.1f}% | Est peak: +{peak_gain:.0f}% | Hold: {t[3]:.1f}min")

# 2. Compare: what happens to tokens AFTER trailing_tp exit?
# We can't know directly, but we CAN look at tokens that had BOTH
# a trailing_tp exit AND later re-entered (if any)
print("\n=== TOKENS WITH MULTIPLE TRADES (re-entry after exit) ===")
multi = c.execute("""
    SELECT mint_address, COUNT(*) as cnt, 
           GROUP_CONCAT(exit_reason) as reasons,
           GROUP_CONCAT(ROUND(pnl_pct*100,1)) as pnls,
           token_name
    FROM trades WHERE status='closed'
    GROUP BY mint_address
    HAVING cnt > 1
    ORDER BY cnt DESC
    LIMIT 10
""").fetchall()
for m in multi:
    print(f"  {m[4]:30s} | {m[1]} trades | Reasons: {m[2]} | PnLs: {m[3]}%")

# 3. The REAL question: what's the optimal trailing TP configuration?
# Let's simulate different parameters on our historical data
print("\n=== SIMULATED EXIT STRATEGIES ON HISTORICAL DATA ===")
print("(Using take_profit trades as ground truth for tokens that DID moon)")

# For each take_profit trade, we know the entry and exit price
# The exit price represents the peak (or near-peak) the paper trader saw
# We can simulate: what if we had different trailing TP settings?

tp_trades = c.execute("""
    SELECT entry_price_usd, exit_price_usd, pnl_pct, pnl_sol, hold_minutes, token_name
    FROM trades WHERE status='closed' AND exit_reason='take_profit' AND pnl_pct > 0.30
    AND exit_price_usd < 3.0e-06
""").fetchall()

print(f"\n  Real moonshot trades (>30%, excluding cap exits): {len(tp_trades)}")
print(f"  Total PnL from these: {sum(t[3] for t in tp_trades):.2f} SOL")

# 4. What if we removed trailing TP entirely and just used fixed TP + timeout?
print("\n=== WHAT IF: NO TRAILING TP (just TP + SL + timeout) ===")
# Current trailing_tp trades that were positive would have been caught by timeout or TP
# Current trailing_tp trades that were negative would have gone to timeout or SL instead
trailing_all = c.execute("""
    SELECT pnl_pct, pnl_sol, hold_minutes, exit_reason
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp'
""").fetchall()

# If trailing TP didn't exist, these trades would continue to timeout (2min) or SL (-25%)
# The negative ones (avg -13.8%) would likely hit SL (-25%) or timeout
# The positive ones would likely hit TP (100%) or timeout with gains
print(f"  Current trailing_tp total PnL: {sum(t[1] for t in trailing_all):+.2f} SOL")
print(f"  Negative trailing_tp PnL: {sum(t[1] for t in trailing_all if t[0] < 0):+.2f} SOL")
print(f"  Positive trailing_tp PnL: {sum(t[1] for t in trailing_all if t[0] >= 0):+.2f} SOL")
print()
print("  If we REMOVED trailing TP:")
print("  - 190 negative trades would go to timeout/SL instead")
print("  - Some might recover (like HENRY did)")
print("  - Some would hit SL at -25% (worse than current -13.8% avg)")
print("  - Net effect depends on how many recover vs how many bleed more")

# 5. What about a HIGHER activation threshold?
print("\n=== WHAT IF: HIGHER TRAILING TP ACTIVATION ===")
# If we set activation at 30% instead of 15%:
# Trades that peaked between 15-30% would NOT activate trailing
# They'd go to timeout instead, potentially recovering
# Trades that peaked above 30% would still get trailing protection

# Count trailing_tp trades by estimated peak
print("  Estimated peak gain for trailing_tp trades:")
trailing_with_prices = c.execute("""
    SELECT pnl_pct, entry_price_usd, exit_price_usd, pnl_sol, token_name
    FROM trades WHERE status='closed' AND exit_reason='trailing_tp'
    AND entry_price_usd > 0 AND exit_price_usd > 0
""").fetchall()

peak_buckets = {'15-20%': 0, '20-30%': 0, '30-50%': 0, '50-100%': 0, '100%+': 0}
peak_pnl_buckets = {'15-20%': 0, '20-30%': 0, '30-50%': 0, '50-100%': 0, '100%+': 0}
for t in trailing_with_prices:
    exit_mult = t[2] / t[1]
    peak_mult = exit_mult / 0.92
    peak_pct = (peak_mult - 1) * 100
    if peak_pct < 20:
        peak_buckets['15-20%'] += 1
        peak_pnl_buckets['15-20%'] += t[3]
    elif peak_pct < 30:
        peak_buckets['20-30%'] += 1
        peak_pnl_buckets['20-30%'] += t[3]
    elif peak_pct < 50:
        peak_buckets['30-50%'] += 1
        peak_pnl_buckets['30-50%'] += t[3]
    elif peak_pct < 100:
        peak_buckets['50-100%'] += 1
        peak_pnl_buckets['50-100%'] += t[3]
    else:
        peak_buckets['100%+'] += 1
        peak_pnl_buckets['100%+'] += t[3]

for k in peak_buckets:
    print(f"    Peak {k:8s}: {peak_buckets[k]:4d} trades | PnL: {peak_pnl_buckets[k]:+.2f} SOL")

# 6. Time-based analysis: when do moonshots happen?
print("\n=== TIME TO MOONSHOT (>100% gain) ===")
moonshots = c.execute("""
    SELECT hold_minutes, pnl_pct*100, pnl_sol, token_name, exit_reason
    FROM trades WHERE status='closed' AND pnl_pct > 1.0
    ORDER BY hold_minutes
""").fetchall()
print(f"  Total moonshots (>100%): {len(moonshots)}")
time_dist = {
    '<30s': len([m for m in moonshots if m[0] < 0.5]),
    '30-45s': len([m for m in moonshots if 0.5 <= m[0] < 0.75]),
    '45-60s': len([m for m in moonshots if 0.75 <= m[0] < 1.0]),
    '1-2min': len([m for m in moonshots if 1.0 <= m[0] < 2.0]),
    '2min+': len([m for m in moonshots if m[0] >= 2.0]),
}
for k, v in time_dist.items():
    print(f"    {k:8s}: {v:4d} moonshots")

# 7. The elephant in the room: bonding curve cap exits
print("\n=== BONDING CURVE CAP EXIT ANALYSIS ===")
cap = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100
    FROM trades WHERE status='closed' 
    AND exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06
    AND pnl_pct > 1.0
""").fetchone()
print(f"  Cap exits (>100% gain, price 3-4.5e-06): {cap[0]} trades")
print(f"  Total phantom PnL: {cap[1]:.2f} SOL")
print(f"  Avg PnL: {cap[2]:.0f}%")

non_cap = c.execute("""
    SELECT COUNT(*), SUM(pnl_sol), AVG(pnl_pct)*100
    FROM trades WHERE status='closed' 
    AND pnl_pct > 1.0
    AND (exit_price_usd < 3.0e-06 OR exit_price_usd > 4.5e-06 OR exit_price_usd IS NULL)
""").fetchone()
print(f"  Real moonshots: {non_cap[0]} trades")
print(f"  Real moonshot PnL: {non_cap[1]:.2f} SOL")
print(f"  Avg PnL: {non_cap[2]:.0f}%")

# 8. What's the actual win rate excluding phantom trades?
print("\n=== REAL WIN RATE (excluding phantom cap exits) ===")
total_real = c.execute("""
    SELECT COUNT(*) FROM trades WHERE status='closed'
    AND NOT (exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06 AND pnl_pct > 1.0)
""").fetchone()[0]
wins_real = c.execute("""
    SELECT COUNT(*) FROM trades WHERE status='closed' AND pnl_pct > 0
    AND NOT (exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06 AND pnl_pct > 1.0)
""").fetchone()[0]
print(f"  Total trades (excl phantom): {total_real}")
print(f"  Winning trades: {wins_real}")
print(f"  Win rate: {wins_real/total_real*100:.1f}%")

real_pnl = c.execute("""
    SELECT SUM(pnl_sol) FROM trades WHERE status='closed'
    AND NOT (exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06 AND pnl_pct > 1.0)
""").fetchone()[0]
print(f"  Real total PnL: {real_pnl:.2f} SOL")

conn.close()
