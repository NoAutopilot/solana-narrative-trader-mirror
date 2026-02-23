#!/usr/bin/env python3
"""
P1 FIX: Time-gated exit strategy replacing the current trailing TP.

DATA-BACKED RATIONALE:
- 247/364 moonshots (68%) form between 30-45 seconds
- 69% of trailing_tp exits are LOSSES (activates on noise at 15%)
- Current trailing TP net PnL: only +2.17 SOL on 280 trades
- HENRY: shaken out at -8.4% by trailing TP, went on to +11,877%

NEW STRATEGY:
Phase 1 (0-45s):   HOLD. Hard SL at -50% only. Let moonshots form.
Phase 2 (45-90s):  Trailing TP at 50% activation, 25% trail. SL -30%.
Phase 3 (90-150s): Trailing TP at 30% activation, 15% trail. SL -25%.
Phase 4 (150s+):   Timeout exit at market price.

The take_profit at 100x (100.0) stays as the ultimate ceiling.
"""

import re

# ============================================================
# STEP 1: Update config/config.py with new parameters
# ============================================================
CONFIG = "/root/solana_trader/config/config.py"

with open(CONFIG, "r") as f:
    config_content = f.read()

# Replace the old trailing TP config with new time-gated config
old_config = """TRAILING_TP_ACTIVATE = 0.15  # Activate trailing TP at 15% gross gain    # Activate trailing TP at 20% profit
TRAILING_TP_DISTANCE = 0.08  # Trail 8% behind peak (tighter = captures more)    # Trail 10% behind peak"""

new_config = """# v5.0: Time-gated exit strategy (replaces flat trailing TP)
# Old values preserved as comments for rollback:
# TRAILING_TP_ACTIVATE = 0.15  # OLD: 15% gross activation
# TRAILING_TP_DISTANCE = 0.08  # OLD: 8% trail distance

# Legacy values (still imported by paper_trader for virtual strategies)
TRAILING_TP_ACTIVATE = 0.50   # Phase 2+ activation (raised from 0.15)
TRAILING_TP_DISTANCE = 0.25   # Phase 2 trail distance (raised from 0.08)

# Time-gated exit phases (seconds from entry)
EXIT_PHASE_1_END     = 45     # 0-45s: formation window, hold with wide SL
EXIT_PHASE_2_END     = 90     # 45-90s: trailing TP with wide trail
EXIT_PHASE_3_END     = 150    # 90-150s: trailing TP with tighter trail
# After phase 3: timeout exit

# Phase-specific parameters
PHASE_1_SL           = -0.50  # Very wide SL during formation (was -0.25)
PHASE_2_TRAIL_ACT    = 0.50   # Activate trailing at 50% gross
PHASE_2_TRAIL_DIST   = 0.25   # Trail 25% from peak
PHASE_2_SL           = -0.30  # SL during phase 2
PHASE_3_TRAIL_ACT    = 0.30   # Activate trailing at 30% gross
PHASE_3_TRAIL_DIST   = 0.15   # Trail 15% from peak
PHASE_3_SL           = -0.25  # SL during phase 3 (original SL)"""

if old_config in config_content:
    config_content = config_content.replace(old_config, new_config)
    print("OK: config.py updated with time-gated exit parameters")
else:
    print("FAIL: Could not find old trailing TP config")
    # Try a more flexible match
    if "TRAILING_TP_ACTIVATE = 0.15" in config_content:
        # Replace line by line
        config_content = config_content.replace(
            "TRAILING_TP_ACTIVATE = 0.15  # Activate trailing TP at 15% gross gain    # Activate trailing TP at 20% profit",
            new_config
        )
        config_content = config_content.replace(
            "TRAILING_TP_DISTANCE = 0.08  # Trail 8% behind peak (tighter = captures more)    # Trail 10% behind peak",
            ""
        )
        print("OK: config.py updated (flexible match)")

with open(CONFIG, "w") as f:
    f.write(config_content)

# ============================================================
# STEP 2: Update the imports in paper_trader.py
# ============================================================
PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    pt_content = f.read()

# Find the import line and add new config imports
old_import = """    TIMEOUT_MINUTES, PRICE_CHECK_INTERVAL, TRAILING_TP_ACTIVATE,
    TRAILING_TP_DISTANCE, VIRTUAL_STRATEGIES, DEXSCREENER_API_URL,"""

new_import = """    TIMEOUT_MINUTES, PRICE_CHECK_INTERVAL, TRAILING_TP_ACTIVATE,
    TRAILING_TP_DISTANCE, VIRTUAL_STRATEGIES, DEXSCREENER_API_URL,
    EXIT_PHASE_1_END, EXIT_PHASE_2_END, EXIT_PHASE_3_END,
    PHASE_1_SL, PHASE_2_TRAIL_ACT, PHASE_2_TRAIL_DIST, PHASE_2_SL,
    PHASE_3_TRAIL_ACT, PHASE_3_TRAIL_DIST, PHASE_3_SL,"""

if old_import in pt_content:
    pt_content = pt_content.replace(old_import, new_import)
    print("OK: paper_trader.py imports updated")
else:
    print("FAIL: Could not find import line in paper_trader.py")

# ============================================================
# STEP 3: Replace check_exit function with time-gated version
# ============================================================
old_check_exit = '''def check_exit(trade_info, current_price_sol):
    """Check if a trade should exit. Returns (should_exit, reason, pnl_pct)."""
    entry_price = trade_info["entry_price_sol"]
    if entry_price <= 0 or current_price_sol is None:
        return False, None, 0
    gross_pnl_pct = (current_price_sol - entry_price) / entry_price
    net_pnl_pct = gross_pnl_pct - FEE_BUY_PCT - FEE_SELL_PCT
    if current_price_sol > trade_info["peak_price_sol"]:
        trade_info["peak_price_sol"] = current_price_sol
    if net_pnl_pct >= TAKE_PROFIT_PCT:
        return True, "take_profit", net_pnl_pct
    if net_pnl_pct <= STOP_LOSS_PCT:
        return True, "stop_loss", net_pnl_pct
    if gross_pnl_pct >= TRAILING_TP_ACTIVATE:
        trade_info["trailing_active"] = True
    if trade_info["trailing_active"]:
        peak = trade_info["peak_price_sol"]
        dd = (current_price_sol - peak) / peak
        if dd <= -TRAILING_TP_DISTANCE:
            return True, "trailing_tp", net_pnl_pct
    age = (datetime.utcnow() - trade_info["entry_time"]).total_seconds()
    if age >= TIMEOUT_MINUTES * 60:
        return True, "timeout", net_pnl_pct
    return False, None, net_pnl_pct'''

new_check_exit = '''def check_exit(trade_info, current_price_sol):
    """
    v5.0: Time-gated exit strategy.
    
    Phase 1 (0-45s):   HOLD. Hard SL at -50% only. Let moonshots form.
    Phase 2 (45-90s):  Trailing TP at 50% activation, 25% trail. SL -30%.
    Phase 3 (90-150s): Trailing TP at 30% activation, 15% trail. SL -25%.
    Phase 4 (150s+):   Timeout exit at market price.
    
    Take profit at 100x stays as ultimate ceiling across all phases.
    """
    entry_price = trade_info["entry_price_sol"]
    if entry_price <= 0 or current_price_sol is None:
        return False, None, 0
    gross_pnl_pct = (current_price_sol - entry_price) / entry_price
    net_pnl_pct = gross_pnl_pct - FEE_BUY_PCT - FEE_SELL_PCT
    if current_price_sol > trade_info["peak_price_sol"]:
        trade_info["peak_price_sol"] = current_price_sol
    age = (datetime.utcnow() - trade_info["entry_time"]).total_seconds()
    
    # Ultimate ceiling: take profit at 100x (always active)
    if net_pnl_pct >= TAKE_PROFIT_PCT:
        return True, "take_profit", net_pnl_pct
    
    # ── PHASE 1: Formation window (0 to EXIT_PHASE_1_END seconds) ──
    if age < EXIT_PHASE_1_END:
        # Only exit on catastrophic loss — let moonshots form
        if net_pnl_pct <= PHASE_1_SL:
            return True, "stop_loss", net_pnl_pct
        return False, None, net_pnl_pct
    
    # ── PHASE 2: Wide trailing (EXIT_PHASE_1_END to EXIT_PHASE_2_END) ──
    if age < EXIT_PHASE_2_END:
        if net_pnl_pct <= PHASE_2_SL:
            return True, "stop_loss", net_pnl_pct
        if gross_pnl_pct >= PHASE_2_TRAIL_ACT:
            trade_info["trailing_active"] = True
        if trade_info["trailing_active"]:
            peak = trade_info["peak_price_sol"]
            dd = (current_price_sol - peak) / peak
            if dd <= -PHASE_2_TRAIL_DIST:
                return True, "trailing_tp", net_pnl_pct
        return False, None, net_pnl_pct
    
    # ── PHASE 3: Tighter trailing (EXIT_PHASE_2_END to EXIT_PHASE_3_END) ──
    if age < EXIT_PHASE_3_END:
        if net_pnl_pct <= PHASE_3_SL:
            return True, "stop_loss", net_pnl_pct
        if gross_pnl_pct >= PHASE_3_TRAIL_ACT:
            trade_info["trailing_active"] = True
        if trade_info["trailing_active"]:
            peak = trade_info["peak_price_sol"]
            dd = (current_price_sol - peak) / peak
            if dd <= -PHASE_3_TRAIL_DIST:
                return True, "trailing_tp", net_pnl_pct
        return False, None, net_pnl_pct
    
    # ── PHASE 4: Timeout ──
    return True, "timeout", net_pnl_pct'''

if old_check_exit in pt_content:
    pt_content = pt_content.replace(old_check_exit, new_check_exit)
    print("OK: check_exit function replaced with time-gated version")
else:
    print("FAIL: Could not find check_exit function")

with open(PAPER_TRADER, "w") as f:
    f.write(pt_content)

# ============================================================
# STEP 4: Verify compilation
# ============================================================
import py_compile
try:
    py_compile.compile(CONFIG, doraise=True)
    print("OK: config.py compiles")
except Exception as e:
    print(f"FAIL: config.py compile error: {e}")

try:
    py_compile.compile(PAPER_TRADER, doraise=True)
    print("OK: paper_trader.py compiles")
except Exception as e:
    print(f"FAIL: paper_trader.py compile error: {e}")

print("\nP1 fix complete. New time-gated exit strategy deployed.")
print("Phase 1 (0-45s): Hold, SL -50%")
print("Phase 2 (45-90s): Trail 50%/25%, SL -30%")
print("Phase 3 (90-150s): Trail 30%/15%, SL -25%")
print("Phase 4 (150s+): Timeout")
