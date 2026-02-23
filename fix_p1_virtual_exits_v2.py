#!/usr/bin/env python3
"""Update check_virtual_exits with time-gated logic using line-based replacement."""

PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    lines = f.readlines()

# Find the "elif params.get("trailing"):" line in check_virtual_exits
# (not in check_exit, which also has trailing logic)
# check_virtual_exits starts at line 548, so look after that
target_line = None
for i, line in enumerate(lines):
    if i > 548 and 'elif params.get("trailing"):' in line:
        target_line = i
        break

if target_line is None:
    print("FAIL: Could not find trailing elif in check_virtual_exits")
    exit(1)

print(f"Found trailing elif at line {target_line + 1}")

# Find the end of the trailing block (next line at same or lower indentation that isn't blank)
# The trailing block is indented at 8 spaces (2 levels inside for loop)
# It ends at the blank line before "if age_sec >= params..."
end_line = target_line + 1
while end_line < len(lines):
    line = lines[end_line]
    stripped = line.rstrip()
    if stripped == '':
        end_line += 1
        continue
    # Check if this line is at the same indentation level as the elif (8 spaces)
    if line.startswith('        if age_sec') or line.startswith('        if exit_reason'):
        break
    end_line += 1

print(f"Trailing block ends at line {end_line + 1}")
print("Lines being replaced:")
for line in lines[target_line:end_line]:
    print(f"  {line.rstrip()}")

# New block: add time_gated BEFORE trailing
new_block = '''        elif params.get("time_gated"):
            # H_time_gated: phase-specific SL and trailing TP
            p = params  # shorthand
            if age_sec < p["phase1_end"]:
                # Phase 1: Formation window — only catastrophic SL
                if net_pnl_pct <= p["phase1_sl"]:
                    exit_reason = "stop_loss"
            elif age_sec < p["phase2_end"]:
                # Phase 2: Wide trailing
                if net_pnl_pct <= p["phase2_sl"]:
                    exit_reason = "stop_loss"
                elif gross_pnl_pct >= p["phase2_trail_act"]:
                    strat_state["trailing_active"] = True
                if strat_state["trailing_active"] and not exit_reason:
                    peak = strat_state["peak_price"]
                    dd = (current_price_sol - peak) / peak
                    if dd <= -p["phase2_trail_dist"]:
                        exit_reason = "trailing_tp"
            elif age_sec < p["phase3_end"]:
                # Phase 3: Tighter trailing
                if net_pnl_pct <= p["phase3_sl"]:
                    exit_reason = "stop_loss"
                elif gross_pnl_pct >= p["phase3_trail_act"]:
                    strat_state["trailing_active"] = True
                if strat_state["trailing_active"] and not exit_reason:
                    peak = strat_state["peak_price"]
                    dd = (current_price_sol - peak) / peak
                    if dd <= -p["phase3_trail_dist"]:
                        exit_reason = "trailing_tp"
            # Phase 4: timeout handled below
        elif params.get("trailing"):
            if gross_pnl_pct >= TRAILING_TP_ACTIVATE:
                strat_state["trailing_active"] = True
            if strat_state["trailing_active"]:
                peak = strat_state["peak_price"]
                dd = (current_price_sol - peak) / peak
                if dd <= -TRAILING_TP_DISTANCE:
                    exit_reason = "trailing_tp"
'''

# Replace lines
new_lines = lines[:target_line] + [new_block] + lines[end_line:]

with open(PAPER_TRADER, "w") as f:
    f.writelines(new_lines)

# Verify
import py_compile
try:
    py_compile.compile(PAPER_TRADER, doraise=True)
    print("\nOK: paper_trader.py compiles")
except Exception as e:
    print(f"\nFAIL: compile error: {e}")

with open(PAPER_TRADER, "r") as f:
    final = f.read()

if "H_time_gated: phase-specific SL and trailing TP" in final:
    print("OK: Time-gated virtual exit logic present")
else:
    print("FAIL: Time-gated logic not found in final file")

# Count how many strategy references
if 'params.get("time_gated")' in final:
    print("OK: time_gated check present in check_virtual_exits")
if 'params.get("trailing")' in final:
    print("OK: trailing check still present in check_virtual_exits")
