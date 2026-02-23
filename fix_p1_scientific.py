#!/usr/bin/env python3
"""
P1 SCIENTIFIC APPROACH: 
1. Revert check_exit() to original trailing TP logic
2. Add "H_time_gated" as a new virtual strategy in config
3. Update check_virtual_exits() to support time-gated logic for strategy H

This follows the principle: "Every change creates a before/after. Control groups mandatory."
"""

# ============================================================
# STEP 1: Revert check_exit() to original
# ============================================================
PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    lines = f.readlines()

# Find the current (time-gated) check_exit function
start_line = None
end_line = None
for i, line in enumerate(lines):
    if line.startswith("def check_exit(trade_info, current_price_sol):"):
        start_line = i
    elif start_line is not None and (line.startswith("class ") or (line.startswith("def ") and i > start_line)):
        end_line = i
        break

if start_line is None:
    print("FAIL: Could not find check_exit function")
    exit(1)

print(f"Found check_exit at lines {start_line+1}-{end_line}")

# The original check_exit function (pre-v5.0)
original_check_exit = '''def check_exit(trade_info, current_price_sol):
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
    return False, None, net_pnl_pct

'''

# Replace
new_lines = lines[:start_line] + [original_check_exit] + lines[end_line:]

with open(PAPER_TRADER, "w") as f:
    f.writelines(new_lines)

print("OK: check_exit reverted to original trailing TP logic")

# ============================================================
# STEP 2: Add H_time_gated to VIRTUAL_STRATEGIES in config
# ============================================================
CONFIG = "/root/solana_trader/config/config.py"

with open(CONFIG, "r") as f:
    config_content = f.read()

# Add H_time_gated strategy to VIRTUAL_STRATEGIES
old_strategies = '''    "G_diamond_hands":  {"tp": 1.00, "sl": -0.35, "timeout": 10, "trailing": True},
}'''

new_strategies = '''    "G_diamond_hands":  {"tp": 1.00, "sl": -0.35, "timeout": 10, "trailing": True},
    "H_time_gated":    {"tp": 100.0, "sl": -0.50, "timeout": 2.5, "time_gated": True,
                         "phase1_end": 45, "phase1_sl": -0.50,
                         "phase2_end": 90, "phase2_trail_act": 0.50, "phase2_trail_dist": 0.25, "phase2_sl": -0.30,
                         "phase3_end": 150, "phase3_trail_act": 0.30, "phase3_trail_dist": 0.15, "phase3_sl": -0.25},
}'''

if old_strategies in config_content:
    config_content = config_content.replace(old_strategies, new_strategies)
    print("OK: H_time_gated added to VIRTUAL_STRATEGIES")
else:
    print("FAIL: Could not find VIRTUAL_STRATEGIES closing brace")

# Also revert the trailing TP config values to original
# (they were changed by the earlier P1 fix)
# Find the v5.0 block and revert to original values
if "v5.0: Time-gated exit strategy" in config_content:
    # Find and replace the entire v5.0 config block
    import re
    # Match from the v5.0 comment to PHASE_3_SL line
    pattern = r'# v5\.0: Time-gated exit strategy.*?PHASE_3_SL\s*=\s*-0\.25\s*#[^\n]*'
    replacement = """TRAILING_TP_ACTIVATE = 0.15  # Activate trailing TP at 15% gross gain
TRAILING_TP_DISTANCE = 0.08  # Trail 8% behind peak"""
    config_content = re.sub(pattern, replacement, config_content, flags=re.DOTALL)
    print("OK: Reverted trailing TP config to original values (0.15/0.08)")
else:
    print("SKIP: No v5.0 config block found (already original)")

with open(CONFIG, "w") as f:
    f.write(config_content)

# ============================================================
# STEP 3: Remove the extra imports that were added for time-gated
# ============================================================
with open(PAPER_TRADER, "r") as f:
    pt_content = f.read()

# Remove the extra import lines
extra_imports = """    EXIT_PHASE_1_END, EXIT_PHASE_2_END, EXIT_PHASE_3_END,
    PHASE_1_SL, PHASE_2_TRAIL_ACT, PHASE_2_TRAIL_DIST, PHASE_2_SL,
    PHASE_3_TRAIL_ACT, PHASE_3_TRAIL_DIST, PHASE_3_SL,"""

if extra_imports in pt_content:
    pt_content = pt_content.replace(extra_imports, "")
    print("OK: Removed extra time-gated imports from paper_trader.py")
else:
    print("SKIP: Extra imports not found")

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

# ============================================================
# STEP 5: Verify the revert
# ============================================================
with open(PAPER_TRADER, "r") as f:
    content = f.read()

if "v5.0: Time-gated exit strategy" in content:
    print("WARNING: Time-gated check_exit still present!")
else:
    print("OK: check_exit is back to original trailing TP logic")

if "TRAILING_TP_ACTIVATE" in content and "TRAILING_TP_DISTANCE" in content:
    print("OK: Original trailing TP variables still referenced")

with open(CONFIG, "r") as f:
    cfg = f.read()

if "H_time_gated" in cfg:
    print("OK: H_time_gated virtual strategy is configured")
if "time_gated" in cfg:
    print("OK: time_gated flag present in H_time_gated config")

print("\n=== STEP 1-3 COMPLETE ===")
print("Next: Update check_virtual_exits() to support time-gated logic for H_time_gated")
