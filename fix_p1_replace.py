#!/usr/bin/env python3
"""P1 FIX: Replace check_exit function using line-based approach."""

PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    lines = f.readlines()

# Find the start and end of check_exit function
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
print(f"Old function ({end_line - start_line} lines):")
for line in lines[start_line:end_line]:
    print(f"  {line.rstrip()}")

new_function = '''def check_exit(trade_info, current_price_sol):
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
    
    # ── PHASE 1: Formation window (0 to 45 seconds) ──
    if age < EXIT_PHASE_1_END:
        # Only exit on catastrophic loss — let moonshots form
        if net_pnl_pct <= PHASE_1_SL:
            return True, "stop_loss", net_pnl_pct
        return False, None, net_pnl_pct
    
    # ── PHASE 2: Wide trailing (45 to 90 seconds) ──
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
    
    # ── PHASE 3: Tighter trailing (90 to 150 seconds) ──
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
    return True, "timeout", net_pnl_pct
'''

# Replace the old function with the new one
new_lines = lines[:start_line] + [new_function] + lines[end_line:]

with open(PAPER_TRADER, "w") as f:
    f.writelines(new_lines)

# Verify compilation
import py_compile
try:
    py_compile.compile(PAPER_TRADER, doraise=True)
    print("\nOK: paper_trader.py compiles with new check_exit")
except Exception as e:
    print(f"\nFAIL: compile error: {e}")

# Show the new function location
with open(PAPER_TRADER, "r") as f:
    for i, line in enumerate(f):
        if "v5.0: Time-gated exit strategy" in line:
            print(f"New check_exit found at line {i+1}")
            break
