#!/usr/bin/env python3
"""P0 FIX Part 2: Add exception class and update except handler."""

PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    content = f.read()

# 1. Add the _PhantomSellBlocked exception class before close_trade
old_def = 'def close_trade(trade_id, trade_info, exit_reason, pnl_pct, current_price_sol):'
new_def = '''class _PhantomSellBlocked(Exception):
    """Raised when a phantom sell is blocked by DB re-check."""
    pass

def close_trade(trade_id, trade_info, exit_reason, pnl_pct, current_price_sol):'''

if old_def in content:
    content = content.replace(old_def, new_def, 1)
    print("OK: _PhantomSellBlocked exception class added")
else:
    print("FAIL: Could not find close_trade definition")

# 2. Update the except block to catch _PhantomSellBlocked first
old_except = '''    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")
    del open_trades[trade_id]'''

new_except = '''    except _PhantomSellBlocked:
        pass  # Already handled — sell was skipped
    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")
    del open_trades[trade_id]'''

if old_except in content:
    content = content.replace(old_except, new_except, 1)
    print("OK: Exception handler updated for _PhantomSellBlocked")
else:
    print("FAIL: Could not find except block")

with open(PAPER_TRADER, "w") as f:
    f.write(content)

print("\nP0 fix complete.")
