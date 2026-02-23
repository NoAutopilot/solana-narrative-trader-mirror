#!/usr/bin/env python3
"""
P0 FIX: Phantom sell bug — add DB re-check before executing live sell.

The race condition:
1. execute_buy() returns {success: True} optimistically
2. paper_trader.py adds to live_trade_map
3. Background thread discovers on-chain failure, updates DB success=0
4. But live_trade_map is NOT updated (different scope)
5. Paper exits → sell attempted for tokens we never bought

Fix: Before executing sell, re-check DB to confirm buy actually succeeded.
"""
import re

PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    content = f.read()

# Find the sell trigger block and add a DB re-check
old_sell_block = """    # ── LIVE SELL (if we have a live position) ──
    try:
        if trade_id in live_trade_map:
            live_buy = live_trade_map[trade_id]
            sell_result = execute_sell("""

new_sell_block = """    # ── LIVE SELL (if we have a live position) ──
    try:
        if trade_id in live_trade_map:
            # v5.0 P0 FIX: Re-check DB before selling to catch async buy failures
            # Background verification may have marked buy as failed after live_trade_map was set
            try:
                import sqlite3 as _sq3_check
                from config.config import DB_PATH as _db_check_path
                _check_conn = _sq3_check.connect(_db_check_path)
                _buy_row = _check_conn.execute(
                    "SELECT success FROM live_trades WHERE paper_trade_id = ? AND UPPER(action) = 'BUY'",
                    (trade_id,)
                ).fetchone()
                _check_conn.close()
                if _buy_row and _buy_row[0] != 1:
                    logger.warning(
                        f"[PHANTOM SELL BLOCKED] {trade_info['name']}: buy was marked failed "
                        f"by async verification (success={_buy_row[0]}). Skipping live sell."
                    )
                    del live_trade_map[trade_id]
                    # Skip the sell entirely — jump to cleanup
                    raise _PhantomSellBlocked()
            except _PhantomSellBlocked:
                raise
            except Exception as _check_err:
                logger.warning(f"[PHANTOM SELL CHECK] DB check failed: {_check_err}, proceeding with sell")
            
            live_buy = live_trade_map[trade_id]
            sell_result = execute_sell("""

# Also need to add the exception class before the function
# Find the close_trade function definition to add the exception class before it
old_close_def = "def close_trade(trade_id, trade_info, exit_reason, current_price_sol, pnl_sol, pnl_pct):"
new_close_def = """class _PhantomSellBlocked(Exception):
    \"\"\"Raised when a phantom sell is blocked by DB re-check.\"\"\"
    pass

def close_trade(trade_id, trade_info, exit_reason, current_price_sol, pnl_sol, pnl_pct):"""

# Also need to catch _PhantomSellBlocked in the except block
old_except = """    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")
    del open_trades[trade_id]"""

new_except = """    except _PhantomSellBlocked:
        pass  # Already handled above — just skip the sell
    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")
    del open_trades[trade_id]"""

if old_sell_block in content:
    content = content.replace(old_sell_block, new_sell_block)
    print("✅ Sell block patched with DB re-check")
else:
    print("❌ Could not find sell block to patch")
    
if old_close_def in content:
    content = content.replace(old_close_def, new_close_def, 1)
    print("✅ _PhantomSellBlocked exception class added")
else:
    print("❌ Could not find close_trade definition")

if old_except in content:
    content = content.replace(old_except, new_except)
    print("✅ Exception handler updated")
else:
    print("❌ Could not find except block to patch")

with open(PAPER_TRADER, "w") as f:
    f.write(content)

print("\nP0 fix applied to paper_trader.py")
