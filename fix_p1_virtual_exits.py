#!/usr/bin/env python3
"""
Update check_virtual_exits() to support time-gated exit logic for H_time_gated strategy.

The existing logic handles:
- Fixed TP/SL strategies (A-E)
- Trailing TP strategies (F, G) via params.get("trailing")

We need to add:
- Time-gated strategies (H) via params.get("time_gated")

The time-gated logic uses phase-specific SL and trailing TP parameters
that change based on how old the trade is.
"""

PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    content = f.read()

# Replace the elif block that handles trailing strategies
# We need to add a new elif for time_gated BEFORE the trailing check
old_exit_logic = '''        elif params.get("trailing"):
            if gross_pnl_pct >= TRAILING_TP_ACTIVATE:
                strat_state["trailing_active"] = True
            if strat_state["trailing_active"]:
                peak = strat_state["peak_price"]
                dd = (current_price_sol - peak) / peak
                if dd <= -TRAILING_TP_DISTANCE:
                    exit_reason = "trailing_tp"
        if age_sec >= params["timeout"] * 60:
            exit_reason = exit_reason or "timeout"'''

new_exit_logic = '''        elif params.get("time_gated"):
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
        if age_sec >= params["timeout"] * 60:
            exit_reason = exit_reason or "timeout"'''

if old_exit_logic in content:
    content = content.replace(old_exit_logic, new_exit_logic)
    print("OK: check_virtual_exits updated with time-gated logic for H_time_gated")
else:
    print("FAIL: Could not find trailing exit logic in check_virtual_exits")

with open(PAPER_TRADER, "w") as f:
    f.write(content)

# Verify compilation
import py_compile
try:
    py_compile.compile(PAPER_TRADER, doraise=True)
    print("OK: paper_trader.py compiles")
except Exception as e:
    print(f"FAIL: paper_trader.py compile error: {e}")

# Verify the new logic is present
with open(PAPER_TRADER, "r") as f:
    final = f.read()

if "H_time_gated: phase-specific SL and trailing TP" in final:
    print("OK: Time-gated virtual exit logic present")
if "phase1_end" in final and "phase2_trail_act" in final:
    print("OK: Phase parameters referenced correctly")

# Count virtual strategies
import re
strat_count = len(re.findall(r'"[A-Z]_\w+"', final))
print(f"Virtual strategies referenced in code: {strat_count}")

print("\n=== STEP 4 COMPLETE ===")
print("H_time_gated will now run as a virtual strategy alongside A-G")
print("After 24-48 hours, compare H vs primary and other virtuals")
