#!/bin/bash
set -e
cd /root/solana_trader

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: Fire-and-forget sells
# Replace the synchronous _verify_tx_on_chain block in execute_sell with async
# ═══════════════════════════════════════════════════════════════════════════════

# Create a Python script to do the precise replacement
cat > /tmp/fix_sell.py << 'PYEOF'
import re

with open("/root/solana_trader/live_executor.py", "r") as f:
    lines = f.readlines()

# Find the line "            # Validate on-chain" in the execute_sell function
# (after the ambiguous handling block, around line 689)
# Replace everything from there to the "break" after LIVE SELL SUCCESS

output = []
i = 0
in_sell_func = False
found_validate = False
skip_until_break = False

while i < len(lines):
    line = lines[i]
    
    # Track when we're in execute_sell
    if "def execute_sell(" in line:
        in_sell_func = True
    elif in_sell_func and line.strip().startswith("def ") and "execute_sell" not in line:
        in_sell_func = False
    
    # Find the "# Validate on-chain" comment inside execute_sell
    if in_sell_func and not found_validate and line.strip() == "# Validate on-chain":
        found_validate = True
        # Insert the fire-and-forget replacement
        indent = "            "
        output.append(f"{indent}# ── FIRE-AND-FORGET: return immediately, verify in background ──\n")
        output.append(f"{indent}submit_elapsed = time.time() - sell_start\n")
        output.append(f"{indent}result['success'] = True  # Optimistic\n")
        output.append(f"{indent}result['tx_signature'] = signature\n")
        output.append(f"{indent}result['confirm_time_sec'] = round(submit_elapsed, 2)\n")
        output.append(f"{indent}result['sol_received'] = None  # Filled by backfill thread\n")
        output.append(f"{indent}_execution_metrics['sell_successes'] += 1\n")
        output.append(f"{indent}logger.info(f'[LIVE SELL SUBMITTED] {token_name}: tx={signature} submit_time={submit_elapsed:.1f}s (async verify)')\n")
        output.append(f"\n")
        output.append(f"{indent}# Background verification thread\n")
        output.append(f"{indent}def _bg_verify_sell(_sig=signature, _tname=token_name, _mint=mint_address, _ptid=paper_trade_id, _start=sell_start, _sp=sell_pct):\n")
        output.append(f"{indent}    try:\n")
        output.append(f"{indent}        confirmed, on_chain_error, sol_change = _verify_tx_on_chain(_sig)\n")
        output.append(f"{indent}        confirm_elapsed = time.time() - _start\n")
        output.append(f"{indent}        _execution_metrics['tx_confirm_times'].append(('sell', confirm_elapsed))\n")
        output.append(f"{indent}        if confirmed:\n")
        output.append(f"{indent}            if sol_change and sol_change > 0:\n")
        output.append(f"{indent}                global _total_sol_received\n")
        output.append(f"{indent}                _total_sol_received += sol_change\n")
        output.append(f"{indent}            logger.info(f'[LIVE SELL CONFIRMED] {{_tname}}: tx={{_sig}} sol_received={{sol_change}} confirm={{confirm_elapsed:.1f}}s')\n")
        output.append(f"{indent}            if _ptid is not None and sol_change is not None:\n")
        output.append(f"{indent}                try:\n")
        output.append(f"{indent}                    from database import Database\n")
        output.append(f"{indent}                    _db = Database()\n")
        output.append(f"{indent}                    _db.update_live_trade_fill(paper_trade_id=_ptid, action='sell', sol_change=sol_change, slippage_pct=0)\n")
        output.append(f"{indent}                except Exception as e:\n")
        output.append(f"{indent}                    logger.warning(f'[LIVE SELL FILL UPDATE FAILED] {{_tname}}: {{e}}')\n")
        output.append(f"{indent}        else:\n")
        output.append(f"{indent}            _execution_metrics['sell_successes'] -= 1\n")
        output.append(f"{indent}            _execution_metrics['sell_failures'] += 1\n")
        output.append(f"{indent}            logger.error(f'[LIVE SELL ON-CHAIN FAIL] {{_tname}}: {{on_chain_error}} tx={{_sig}}')\n")
        output.append(f"{indent}        if _sp == 100:\n")
        output.append(f"{indent}            _try_reclaim_rent(_mint, _tname)\n")
        output.append(f"{indent}    except Exception as e:\n")
        output.append(f"{indent}        logger.warning(f'[LIVE SELL VERIFY ERROR] {{_tname}}: {{e}}')\n")
        output.append(f"\n")
        output.append(f"{indent}threading.Thread(target=_bg_verify_sell, daemon=True).start()\n")
        output.append(f"\n")
        output.append(f"{indent}if paper_trade_id is not None:\n")
        output.append(f"{indent}    _open_live_trades.discard(paper_trade_id)\n")
        output.append(f"{indent}result['pools_tried'] = pools_tried\n")
        output.append(f"{indent}return result\n")
        output.append(f"\n")
        
        # Now skip all lines until we hit the "break" after LIVE SELL SUCCESS or the except block
        # We need to skip: the old verify block, the confirmed/not confirmed branches
        # Skip until we see "except requests.exceptions.Timeout"
        skip_until_break = True
        i += 1
        continue
    
    if skip_until_break:
        # Skip lines until we hit "except requests.exceptions.Timeout" or "except Exception"
        stripped = line.strip()
        if stripped.startswith("except requests.exceptions.Timeout"):
            skip_until_break = False
            output.append(line)
        i += 1
        continue
    
    output.append(line)
    i += 1

with open("/root/solana_trader/live_executor.py", "w") as f:
    f.writelines(output)

print(f"Fix 1 applied: replaced {sum(1 for _ in output)} lines total")
print(f"Found validate block: {found_validate}")
PYEOF

python3 /tmp/fix_sell.py

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: Buy pool fallback
# Replace single-pool buy with retry loop
# ═══════════════════════════════════════════════════════════════════════════════

cat > /tmp/fix_buy.py << 'PYEOF'
with open("/root/solana_trader/live_executor.py", "r") as f:
    content = f.read()

# Replace the single-pool buy block with a fallback loop
old_block = '''        logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL pool={LIVE_BUY_POOL}")
        signature, api_error = _submit_trade(
            "buy", mint_address,
            pool=LIVE_BUY_POOL,
            amount=trade_amount,
            denominatedInSol="true",
        )
        if api_error:
            result["error"] = api_error
            _execution_metrics["buy_failures"] += 1
            logger.error(f"[LIVE BUY FAILED] {token_name}: {api_error}")
            return result'''

new_block = '''        pools_to_try = BUY_POOL_FALLBACK_ORDER if LIVE_BUY_POOL == "pump" else [LIVE_BUY_POOL]
        signature = None
        api_error = None
        for buy_pool in pools_to_try:
            logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL pool={buy_pool}")
            signature, api_error = _submit_trade(
                "buy", mint_address,
                pool=buy_pool,
                amount=trade_amount,
                denominatedInSol="true",
            )
            if api_error:
                if "migrated" in str(api_error).lower() or "bonding curve" in str(api_error).lower() or "6024" in str(api_error):
                    logger.warning(f"[LIVE BUY] {token_name}: pool={buy_pool} failed (migrated?), trying next...")
                    continue
                else:
                    break
            else:
                break
        if api_error:
            result["error"] = api_error
            _execution_metrics["buy_failures"] += 1
            logger.error(f"[LIVE BUY FAILED] {token_name}: {api_error} (tried: {pools_to_try})")
            return result'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Fix 2 applied: buy pool fallback")
else:
    print("Fix 2: exact block not found, trying with flexible whitespace...")
    # Try with regex for flexible whitespace
    import re
    pattern = r'(\s+)logger\.info\(f"\[LIVE BUY\] Executing:.*?pool=\{LIVE_BUY_POOL\}"\)\n\s+signature, api_error = _submit_trade\(\n\s+"buy", mint_address,\n\s+pool=LIVE_BUY_POOL,\n\s+amount=trade_amount,\n\s+denominatedInSol="true",\n\s+\)\n\s+if api_error:\n\s+result\["error"\] = api_error\n\s+_execution_metrics\["buy_failures"\] \+= 1\n\s+logger\.error\(f"\[LIVE BUY FAILED\].*?\n\s+return result'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        indent = match.group(1)
        replacement = f'''{indent}pools_to_try = BUY_POOL_FALLBACK_ORDER if LIVE_BUY_POOL == "pump" else [LIVE_BUY_POOL]
{indent}signature = None
{indent}api_error = None
{indent}for buy_pool in pools_to_try:
{indent}    logger.info(f"[LIVE BUY] Executing: {{token_name}} ({{mint_address}}) for {{trade_amount}} SOL pool={{buy_pool}}")
{indent}    signature, api_error = _submit_trade(
{indent}        "buy", mint_address,
{indent}        pool=buy_pool,
{indent}        amount=trade_amount,
{indent}        denominatedInSol="true",
{indent}    )
{indent}    if api_error:
{indent}        if "migrated" in str(api_error).lower() or "bonding curve" in str(api_error).lower() or "6024" in str(api_error):
{indent}            logger.warning(f"[LIVE BUY] {{token_name}}: pool={{buy_pool}} failed (migrated?), trying next...")
{indent}            continue
{indent}        else:
{indent}            break
{indent}    else:
{indent}        break
{indent}if api_error:
{indent}    result["error"] = api_error
{indent}    _execution_metrics["buy_failures"] += 1
{indent}    logger.error(f"[LIVE BUY FAILED] {{token_name}}: {{api_error}} (tried: {{pools_to_try}})")
{indent}    return result'''
        content = content[:match.start()] + replacement + content[match.end():]
        print("Fix 2 applied via regex: buy pool fallback")
    else:
        print("Fix 2 FAILED: could not find buy block")

with open("/root/solana_trader/live_executor.py", "w") as f:
    f.write(content)
PYEOF

python3 /tmp/fix_buy.py

echo "=== ALL FIXES APPLIED ==="
