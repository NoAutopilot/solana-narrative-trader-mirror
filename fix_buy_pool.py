#!/usr/bin/env python3
"""Fix 2: Replace single-pool buy with fallback loop using line numbers."""

with open("/root/solana_trader/live_executor.py", "r") as f:
    lines = f.readlines()

# Lines 490-502 (0-indexed: 489-501) contain the old buy block
# We need to replace lines 491-502 (the logger.info through return result)
# Line 490 is "    try:" which we keep

new_buy_block = [
    '        pools_to_try = BUY_POOL_FALLBACK_ORDER if LIVE_BUY_POOL == "pump" else [LIVE_BUY_POOL]\n',
    '        signature = None\n',
    '        api_error = None\n',
    '        for buy_pool in pools_to_try:\n',
    '            logger.info(f"[LIVE BUY] Executing: {token_name} ({mint_address}) for {trade_amount} SOL pool={buy_pool}")\n',
    '            signature, api_error = _submit_trade(\n',
    '                "buy", mint_address,\n',
    '                pool=buy_pool,\n',
    '                amount=trade_amount,\n',
    '                denominatedInSol="true",\n',
    '            )\n',
    '            if api_error:\n',
    '                if "migrated" in str(api_error).lower() or "bonding curve" in str(api_error).lower() or "6024" in str(api_error):\n',
    '                    logger.warning(f"[LIVE BUY] {token_name}: pool={buy_pool} failed (migrated?), trying next...")\n',
    '                    continue\n',
    '                else:\n',
    '                    break\n',
    '            else:\n',
    '                break\n',
    '        if api_error:\n',
    '            result["error"] = api_error\n',
    '            _execution_metrics["buy_failures"] += 1\n',
    '            logger.error(f"[LIVE BUY FAILED] {token_name}: {api_error} (tried: {pools_to_try})")\n',
    '            return result\n',
]

# Find the exact line with "pool={LIVE_BUY_POOL}" in the logger.info
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'logger.info(f"[LIVE BUY] Executing:' in line and 'pool={LIVE_BUY_POOL}' in line:
        start_idx = i
    if start_idx is not None and end_idx is None:
        if '            return result' in line and i > start_idx:
            end_idx = i + 1
            break

if start_idx is not None and end_idx is not None:
    print(f"Found buy block at lines {start_idx+1}-{end_idx} (replacing {end_idx - start_idx} lines with {len(new_buy_block)} lines)")
    lines = lines[:start_idx] + new_buy_block + lines[end_idx:]
    print("FIX 2 ✅ Applied: buy pool fallback (pump -> pump-amm)")
else:
    print(f"FIX 2 ❌ Could not find buy block (start={start_idx}, end={end_idx})")

with open("/root/solana_trader/live_executor.py", "w") as f:
    f.writelines(lines)

print("Done.")
