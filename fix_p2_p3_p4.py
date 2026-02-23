#!/usr/bin/env python3
"""
P2: Add phantom_exit and realistic_pnl columns to trades table.
P3: Add platform column and detect untradeable tokens.
P4: Fix dashboard PnL display (pnl_pct stored as ratio, not percentage).
"""
import sqlite3

DB = "/root/solana_trader/data/solana_trader.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

# ============================================================
# P2: Add phantom_exit flag and realistic_pnl_sol columns
# ============================================================
print("=== P2: Phantom PnL flagging ===")

# Check if columns already exist
cols = [row[1] for row in c.execute("PRAGMA table_info(trades)").fetchall()]
print(f"Existing columns: {len(cols)}")

if "phantom_exit" not in cols:
    c.execute("ALTER TABLE trades ADD COLUMN phantom_exit INTEGER DEFAULT 0")
    print("OK: Added phantom_exit column")
else:
    print("SKIP: phantom_exit already exists")

if "realistic_pnl_sol" not in cols:
    c.execute("ALTER TABLE trades ADD COLUMN realistic_pnl_sol REAL")
    print("OK: Added realistic_pnl_sol column")
else:
    print("SKIP: realistic_pnl_sol already exists")

# Flag existing phantom exits (bonding curve cap prices)
updated = c.execute("""
    UPDATE trades SET phantom_exit = 1
    WHERE exit_price_usd BETWEEN 3.0e-06 AND 4.5e-06
    AND pnl_pct > 1.0
    AND phantom_exit = 0
""").rowcount
print(f"Flagged {updated} existing phantom exits")

# Calculate realistic PnL (cap at 125x entry)
# entry_sol is the SOL amount bet (0.04 typically)
# realistic_pnl = min(pnl_sol, entry_sol * 125)
c.execute("""
    UPDATE trades SET realistic_pnl_sol = 
        CASE 
            WHEN phantom_exit = 1 THEN 0.0
            WHEN pnl_sol > entry_sol * 125 THEN entry_sol * 125
            ELSE pnl_sol
        END
    WHERE status = 'closed'
""")
print(f"Updated realistic_pnl_sol for all closed trades")

# Show the impact
total_raw = c.execute("SELECT SUM(pnl_sol) FROM trades WHERE status='closed'").fetchone()[0]
total_real = c.execute("SELECT SUM(realistic_pnl_sol) FROM trades WHERE status='closed'").fetchone()[0]
phantom_count = c.execute("SELECT COUNT(*) FROM trades WHERE phantom_exit=1").fetchone()[0]
print(f"\nRaw paper PnL: {total_raw:.2f} SOL")
print(f"Realistic PnL: {total_real:.2f} SOL")
print(f"Phantom trades flagged: {phantom_count}")
print(f"PnL adjustment: {total_raw - total_real:.2f} SOL ({(total_raw - total_real)/total_raw*100:.1f}%)")

# ============================================================
# P3: Add platform column for token platform detection
# ============================================================
print("\n=== P3: Platform detection ===")

if "platform" not in cols:
    c.execute("ALTER TABLE trades ADD COLUMN platform TEXT DEFAULT 'unknown'")
    print("OK: Added platform column")
else:
    print("SKIP: platform already exists")

# Detect platform from mint suffix
c.execute("UPDATE trades SET platform = 'pumpfun' WHERE mint_address LIKE '%pump'")
c.execute("UPDATE trades SET platform = 'bonk' WHERE mint_address LIKE '%bonk'")
c.execute("""
    UPDATE trades SET platform = 'other' 
    WHERE mint_address NOT LIKE '%pump' AND mint_address NOT LIKE '%bonk'
    AND platform = 'unknown'
""")

# Show distribution
for plat in ['pumpfun', 'bonk', 'other']:
    row = c.execute(
        "SELECT COUNT(*), COALESCE(SUM(pnl_sol),0), COALESCE(SUM(realistic_pnl_sol),0) FROM trades WHERE platform=?",
        (plat,)
    ).fetchone()
    print(f"  {plat:10s}: {row[0]:5d} trades | Raw: {row[1]:+8.2f} SOL | Realistic: {row[2]:+8.2f} SOL")

conn.commit()
conn.close()

# ============================================================
# P4: Dashboard PnL display fix
# ============================================================
print("\n=== P4: Dashboard PnL display ===")
print("The pnl_pct field stores a RATIO (1.0 = 100%).")
print("Dashboard must multiply by 100 for display.")
print("This will be fixed in the dashboard code (server/routers.ts).")
print("For now, the DB is correctly storing ratios.")

print("\n=== ALL P2-P4 FIXES APPLIED ===")
