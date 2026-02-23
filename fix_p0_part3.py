#!/usr/bin/env python3
"""P0 FIX Part 3: Add _PhantomSellBlocked catch at the outer except level."""

PAPER_TRADER = "/root/solana_trader/paper_trader.py"

with open(PAPER_TRADER, "r") as f:
    content = f.read()

old = '''    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")
    del open_trades[trade_id]'''

new = '''    except _PhantomSellBlocked:
        pass  # Already logged — sell was correctly skipped
    except Exception as e:
        logger.error(f"[LIVE SELL ERROR] {trade_info['name']}: {e}")
    del open_trades[trade_id]'''

# Only replace the FIRST occurrence (the one in close_trade)
if old in content:
    content = content.replace(old, new, 1)
    print("OK: Outer except handler updated for _PhantomSellBlocked")
else:
    print("FAIL: Could not find outer except block")

with open(PAPER_TRADER, "w") as f:
    f.write(content)
