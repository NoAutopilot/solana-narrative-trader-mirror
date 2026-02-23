#!/usr/bin/env python3
"""
Fix 1: Make execute_sell fire-and-forget (async verification like execute_buy).
Fix 2: Add buy pool fallback for migrated tokens.

Reads live_executor.py, applies patches, writes back.
"""

with open("/root/solana_trader/live_executor.py", "r") as f:
    lines = f.readlines()

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: Replace synchronous sell verification with async
# ═══════════════════════════════════════════════════════════════════════════════

# The replacement block as raw lines (no f-strings to avoid escaping issues)
ASYNC_SELL_BLOCK = [
    '            # ── FIRE-AND-FORGET: return immediately, verify in background ──\n',
    '            submit_elapsed = time.time() - sell_start\n',
    '            result["success"] = True  # Optimistic\n',
    '            result["tx_signature"] = signature\n',
    '            result["confirm_time_sec"] = round(submit_elapsed, 2)\n',
    '            result["sol_received"] = None  # Filled by backfill thread\n',
    '            _execution_metrics["sell_successes"] += 1\n',
    '            logger.info(f"[LIVE SELL SUBMITTED] {token_name}: tx={signature} submit_time={submit_elapsed:.1f}s (async verify)")\n',
    '\n',
    '            # Background verification thread\n',
    '            def _bg_verify_sell(_sig=signature, _tname=token_name, _mint=mint_address, _ptid=paper_trade_id, _start=sell_start, _sp=sell_pct):\n',
    '                try:\n',
    '                    confirmed, on_chain_error, sol_change = _verify_tx_on_chain(_sig)\n',
    '                    confirm_elapsed = time.time() - _start\n',
    '                    _execution_metrics["tx_confirm_times"].append(("sell", confirm_elapsed))\n',
    '                    if confirmed:\n',
    '                        if sol_change and sol_change > 0:\n',
    '                            global _total_sol_received\n',
    '                            _total_sol_received += sol_change\n',
    '                        logger.info(f"[LIVE SELL CONFIRMED] {_tname}: tx={_sig} sol_received={sol_change} confirm={confirm_elapsed:.1f}s")\n',
    '                        if _ptid is not None and sol_change is not None:\n',
    '                            try:\n',
    '                                from database import Database\n',
    '                                _db = Database()\n',
    '                                _db.update_live_trade_fill(paper_trade_id=_ptid, action="sell", sol_change=sol_change, slippage_pct=0)\n',
    '                            except Exception as e:\n',
    '                                logger.warning(f"[LIVE SELL FILL UPDATE FAILED] {_tname}: {e}")\n',
    '                    else:\n',
    '                        _execution_metrics["sell_successes"] -= 1\n',
    '                        _execution_metrics["sell_failures"] += 1\n',
    '                        logger.error(f"[LIVE SELL ON-CHAIN FAIL] {_tname}: {on_chain_error} tx={_sig}")\n',
    '                    if _sp == 100:\n',
    '                        _try_reclaim_rent(_mint, _tname)\n',
    '                except Exception as e:\n',
    '                    logger.warning(f"[LIVE SELL VERIFY ERROR] {_tname}: {e}")\n',
    '\n',
    '            threading.Thread(target=_bg_verify_sell, daemon=True).start()\n',
    '\n',
    '            if paper_trade_id is not None:\n',
    '                _open_live_trades.discard(paper_trade_id)\n',
    '            result["pools_tried"] = pools_tried\n',
    '            return result\n',
    '\n',
]

output = []
i = 0
in_sell_func = False
found_validate = False
skip_mode = False

while i < len(lines):
    line = lines[i]
    
    # Track when we enter execute_sell
    if "def execute_sell(" in line:
        in_sell_func = True
    # Track when we leave execute_sell (next top-level function)
    elif in_sell_func and not line.startswith(" ") and not line.startswith("\n") and not line.startswith("#"):
        if line.strip().startswith("def "):
            in_sell_func = False
    
    # Find the "# Validate on-chain" comment inside execute_sell
    if in_sell_func and not found_validate and line.strip() == "# Validate on-chain":
        found_validate = True
        # Insert the async replacement
        output.extend(ASYNC_SELL_BLOCK)
        # Now skip everything until "except requests.exceptions.Timeout"
        skip_mode = True
        i += 1
        continue
    
    if skip_mode:
        stripped = line.strip()
        if stripped.startswith("except requests.exceptions.Timeout"):
            skip_mode = False
            output.append(line)
        i += 1
        continue
    
    output.append(line)
    i += 1

if found_validate:
    print("FIX 1 ✅ Applied: fire-and-forget sells (replaced synchronous verification)")
else:
    print("FIX 1 ❌ Could not find '# Validate on-chain' in execute_sell")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: Buy pool fallback
# ═══════════════════════════════════════════════════════════════════════════════

content = "".join(output)

# Find and replace the single-pool buy submission
OLD_BUY_LINES = [
    '        logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL pool={LIVE_BUY_POOL}")',
    '        signature, api_error = _submit_trade(',
    '            "buy", mint_address,',
    '            pool=LIVE_BUY_POOL,',
    '            amount=trade_amount,',
    '            denominatedInSol="true",',
    '        )',
    '        if api_error:',
    '            result["error"] = api_error',
    '            _execution_metrics["buy_failures"] += 1',
    '            logger.error(f"[LIVE BUY FAILED] {token_name}: {api_error}")',
    '            return result',
]

NEW_BUY_LINES = [
    '        pools_to_try = BUY_POOL_FALLBACK_ORDER if LIVE_BUY_POOL == "pump" else [LIVE_BUY_POOL]',
    '        signature = None',
    '        api_error = None',
    '        for buy_pool in pools_to_try:',
    '            logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL pool={buy_pool}")',
    '            signature, api_error = _submit_trade(',
    '                "buy", mint_address,',
    '                pool=buy_pool,',
    '                amount=trade_amount,',
    '                denominatedInSol="true",',
    '            )',
    '            if api_error:',
    '                if "migrated" in str(api_error).lower() or "bonding curve" in str(api_error).lower() or "6024" in str(api_error):',
    '                    logger.warning(f"[LIVE BUY] {token_name}: pool={buy_pool} failed (migrated?), trying next...")',
    '                    continue',
    '                else:',
    '                    break',
    '            else:',
    '                break',
    '        if api_error:',
    '            result["error"] = api_error',
    '            _execution_metrics["buy_failures"] += 1',
    '            logger.error(f"[LIVE BUY FAILED] {token_name}: {api_error} (tried: {pools_to_try})")',
    '            return result',
]

old_buy_block = "\n".join(OLD_BUY_LINES) + "\n"
new_buy_block = "\n".join(NEW_BUY_LINES) + "\n"

if old_buy_block in content:
    content = content.replace(old_buy_block, new_buy_block)
    print("FIX 2 ✅ Applied: buy pool fallback (pump -> pump-amm)")
else:
    # Try with flexible whitespace matching
    print("FIX 2 ⚠️  Exact match failed, trying flexible approach...")
    # Check if the key line exists
    if 'pool=LIVE_BUY_POOL,' in content and 'BUY_POOL_FALLBACK_ORDER' not in content:
        # Manual line-by-line replacement
        new_lines = content.split('\n')
        result_lines = []
        skip_buy = False
        buy_fixed = False
        for j, l in enumerate(new_lines):
            if not buy_fixed and 'logger.info(f"[LIVE BUY] Executing:' in l and 'pool={LIVE_BUY_POOL}' in l:
                # Found the start of the buy block
                result_lines.extend(NEW_BUY_LINES)
                skip_buy = True
                buy_fixed = True
                continue
            if skip_buy:
                if 'return result' in l and '_execution_metrics["buy_failures"]' in new_lines[j-1]:
                    skip_buy = False
                    continue
                continue
            result_lines.append(l)
        if buy_fixed:
            content = '\n'.join(result_lines)
            print("FIX 2 ✅ Applied via flexible matching")
        else:
            print("FIX 2 ❌ Could not find buy block")
    elif 'BUY_POOL_FALLBACK_ORDER' in content:
        print("FIX 2 ✅ Already applied (BUY_POOL_FALLBACK_ORDER exists)")
    else:
        print("FIX 2 ❌ Could not find buy block")

with open("/root/solana_trader/live_executor.py", "w") as f:
    f.write(content)

print("\nDone. Restart service to activate: systemctl restart solana-trader")
