#!/usr/bin/env python3
"""
who_family_pilot_v1 — Wallet/Deployer/Early-Buyer Feasibility Pilot

Gathers deployer wallet and early buyer data for 10 stronger and 10 weaker
tokens from the frozen 96-fire feature_tape_v2 artifact.

Uses Helius RPC (already configured on VPS) for on-chain lookups.
"""

import json
import os
import sys
import time
import requests
import sqlite3
from collections import Counter, defaultdict

# Config
HELIUS_RPC = os.environ.get("HELIUS_RPC_URL", "")
if not HELIUS_RPC:
    # Try loading from .env
    env_path = "/root/solana_trader/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("HELIUS_RPC_URL=REDACTED
                    HELIUS_RPC = line.strip().split("=", 1)[1]

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/root/solana_trader/reports/new_programs"
os.makedirs(OUT_DIR, exist_ok=True)

# Helius API base (extract API key from RPC URL)
HELIUS_API_KEY = HELIUS_RPC.split("api-key=REDACTED")[-1] if "api-key=REDACTED" in HELIUS_RPC else ""
HELIUS_API_BASE = f"https://api.helius.xyz/v0"

# ── SAMPLE DEFINITION ──────────────────────────────────────────────
# 10 stronger tokens (top quartile by avg +1h return, N >= 15)
# 10 weaker tokens (bottom quartile by avg +1h return, N >= 15)
# All are pumpfun tokens (ending in 'pump') for comparability

STRONGER = [
    ("MEMECARD", "ACc3ZBq1c9h7pofwn2J8b8bvRHvqMFwynVg8neLZpump"),
    ("NEO", "HL8i2d74iFZQGkpZ1eBzJQWbkU6bBmRUVJgMF2b6pump"),
    ("SMITH", "9e1wtawpbkrJGq3vLbPGBvpQFLfsPFtjai4D9eo9pump"),
    ("HAMSTER", "CXjctbA7ENQgZf1FnMLJJUGKp92gAJdMcyEhXeZppump"),
    ("EXPRESSION", "3VgL5HHqhmPJM1BJjZLo1e2CosM233zcL3HB3PiKpump"),
    ("LUFFY", "AZCyNKNLoEn4NCVr3NEReUFqTFjvC9ZgK6jk2SRnpump"),
    ("SHEEPAGENT", "Ec8w8C6ih21zhmFC4Qu1pD1UcAqgNuacGPoHNoM2pump"),
    ("MACROHARD", "DVZMdNkcET3852usHEi1e6WB9ShffZsxbkbW55eEpump"),
    ("Snorp", "4xJxk2RoT5i4zJGzu68Xwvke3EDvGbL5MadP9QiEpump"),
    ("SOS", "DpxKNEi3XVeRByaGqYKvz2w6E2PhPgBAqdayLcQEpump"),
]

WEAKER = [
    ("NORWOOD", "5ohCSjq8m9sNZefTPSSxXkQeQqf5RfR7gjJpeEZRpump"),
    ("Out", "GM9fN6X2izkr7NjF5esWfMtViJ6aqDKvJRTgfoAGpump"),
    ("SMORT", "BwCq8ehGpSgoeipHYd9DYtciNYPsA6k8bBEXNAQSpump"),
    ("WENDYS", "9xRZgabPKGBteGgnsoMHpXrd3NpKZ1uaYwKTd3gLpump"),
    ("$2", "DzMw8nmA5rnoRTTXGHCZaRp9EkMwG2anqY99XxiXpump"),
    ("01001000", "4ysWSPRkmqY6Y99SN86D2MBHXrvnR2358SaGb47Fpump"),
    ("NOTGAY", "uphcYhzNzLBQQcQdpsbQXTFSNApMuh1Y4Jp6KTYpump"),
    ("Distorted", "EPuZ1X6pPzac3ELPsT59LStmgaSr4kBJvaAbL15Fpump"),
    ("butthole", "DaTGaE6uhCfzz6Eh8hWQwL4yw3AJbXWbfvbeccdXJWED"),
    ("Life", "C4yDhKwkikpVGCQWD9BT2SJyHAtRFFnKPDM9Nyshpump"),
]

ALL_TOKENS = [(s, m, "stronger") for s, m in STRONGER] + [(s, m, "weaker") for s, m in WEAKER]

# ── HELPER FUNCTIONS ───────────────────────────────────────────────

def helius_rpc_call(method, params):
    """Make a JSON-RPC call to Helius."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    resp = requests.post(HELIUS_RPC, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def helius_api_call(endpoint, params=None):
    """Make a REST API call to Helius."""
    url = f"{HELIUS_API_BASE}/{endpoint}?api-key=REDACTED{HELIUS_API_KEY}"
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()

def get_mint_authority(mint_address):
    """Get the mint authority (deployer) for a token."""
    try:
        result = helius_rpc_call("getAccountInfo", [
            mint_address,
            {"encoding": "jsonParsed"}
        ])
        if result.get("result") and result["result"].get("value"):
            data = result["result"]["value"]["data"]
            if isinstance(data, dict) and "parsed" in data:
                info = data["parsed"]["info"]
                return {
                    "mint_authority": info.get("mintAuthority"),
                    "freeze_authority": info.get("freezeAuthority"),
                    "supply": info.get("supply"),
                    "decimals": info.get("decimals"),
                }
        return None
    except Exception as e:
        print(f"  Error getting mint authority for {mint_address}: {e}")
        return None

def get_early_signatures(mint_address, limit=50):
    """Get the earliest transaction signatures for a token mint address."""
    try:
        # Get signatures in reverse chronological order, then we'll take the oldest
        all_sigs = []
        before = None
        for _ in range(5):  # Max 5 pages
            params = [mint_address, {"limit": 1000}]
            if before:
                params[1]["before"] = before
            result = helius_rpc_call("getSignaturesForAddress", params)
            sigs = result.get("result", [])
            if not sigs:
                break
            all_sigs.extend(sigs)
            before = sigs[-1]["signature"]
            if len(sigs) < 1000:
                break
            time.sleep(0.2)
        
        # Sort by slot (ascending) to get earliest
        all_sigs.sort(key=lambda x: x.get("slot", 0))
        return all_sigs[:limit]  # Return earliest 50
    except Exception as e:
        print(f"  Error getting signatures for {mint_address}: {e}")
        return []

def parse_transactions_helius(signatures):
    """Use Helius parsed transaction API to get transaction details."""
    if not signatures:
        return []
    
    sig_list = [s["signature"] for s in signatures[:100]]  # Max 100 per call
    try:
        url = f"{HELIUS_API_BASE}/transactions?api-key=REDACTED{HELIUS_API_KEY}"
        resp = requests.post(url, json={"transactions": sig_list}, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Error parsing transactions: {e}")
        return []

def extract_early_buyers(parsed_txns, mint_address):
    """Extract unique buyer wallets from parsed transactions."""
    buyers = []
    seen = set()
    
    for txn in parsed_txns:
        if not isinstance(txn, dict):
            continue
        
        # Check for SWAP or TRANSFER type
        txn_type = txn.get("type", "")
        fee_payer = txn.get("feePayer", "")
        timestamp = txn.get("timestamp", 0)
        
        # Look at token transfers
        token_transfers = txn.get("tokenTransfers", [])
        for tt in token_transfers:
            if tt.get("mint") == mint_address:
                to_addr = tt.get("toUserAccount", "")
                from_addr = tt.get("fromUserAccount", "")
                amount = tt.get("tokenAmount", 0)
                
                # A "buy" is receiving the token
                if to_addr and to_addr not in seen and amount > 0:
                    buyers.append({
                        "wallet": to_addr,
                        "timestamp": timestamp,
                        "amount": amount,
                        "txn_type": txn_type,
                        "fee_payer": fee_payer,
                        "signature": txn.get("signature", ""),
                    })
                    seen.add(to_addr)
        
        # Also check native transfers and account data for swap patterns
        if txn_type in ("SWAP", "TOKEN_MINT") and fee_payer and fee_payer not in seen:
            # The fee payer of a swap is likely the buyer
            for tt in token_transfers:
                if tt.get("mint") == mint_address and tt.get("toUserAccount") == fee_payer:
                    if fee_payer not in seen:
                        buyers.append({
                            "wallet": fee_payer,
                            "timestamp": timestamp,
                            "amount": tt.get("tokenAmount", 0),
                            "txn_type": txn_type,
                            "fee_payer": fee_payer,
                            "signature": txn.get("signature", ""),
                        })
                        seen.add(fee_payer)
    
    # Sort by timestamp
    buyers.sort(key=lambda x: x["timestamp"])
    return buyers

# ── MAIN EXECUTION ─────────────────────────────────────────────────

print("=" * 70)
print("WHO FAMILY PILOT v1 — Data Gathering")
print("=" * 70)
print(f"Helius RPC: {'configured' if HELIUS_RPC else 'MISSING'}")
print(f"Helius API key: {'configured' if HELIUS_API_KEY else 'MISSING'}")
print(f"Tokens to process: {len(ALL_TOKENS)}")
print()

results = []

for i, (symbol, mint, group) in enumerate(ALL_TOKENS):
    print(f"[{i+1}/{len(ALL_TOKENS)}] {symbol} ({group}) — {mint[:16]}...")
    
    token_data = {
        "symbol": symbol,
        "mint": mint,
        "group": group,
    }
    
    # 1. Get mint authority (deployer)
    mint_info = get_mint_authority(mint)
    if mint_info:
        token_data["mint_authority"] = mint_info.get("mint_authority")
        token_data["freeze_authority"] = mint_info.get("freeze_authority")
        token_data["supply"] = mint_info.get("supply")
        token_data["decimals"] = mint_info.get("decimals")
        ma = mint_info.get('mint_authority') or 'None'
        print(f"  Mint authority: {str(ma)[:16]}...")
    else:
        token_data["mint_authority"] = None
        print(f"  Mint authority: FAILED")
    
    time.sleep(0.3)
    
    # 2. Get early transaction signatures
    early_sigs = get_early_signatures(mint, limit=50)
    token_data["total_sigs_found"] = len(early_sigs)
    print(f"  Early signatures: {len(early_sigs)}")
    
    time.sleep(0.3)
    
    # 3. Parse transactions via Helius API
    if early_sigs:
        parsed = parse_transactions_helius(early_sigs)
        token_data["parsed_txns"] = len(parsed)
        print(f"  Parsed transactions: {len(parsed)}")
        
        # 4. Extract early buyers
        buyers = extract_early_buyers(parsed, mint)
        token_data["early_buyers"] = buyers
        token_data["n_early_buyers"] = len(buyers)
        token_data["first_10_buyers"] = [b["wallet"] for b in buyers[:10]]
        token_data["first_20_buyers"] = [b["wallet"] for b in buyers[:20]]
        print(f"  Early buyers found: {len(buyers)}")
        
        if buyers:
            print(f"  First buyer: {buyers[0]['wallet'][:16]}... at {buyers[0]['timestamp']}")
    else:
        token_data["parsed_txns"] = 0
        token_data["early_buyers"] = []
        token_data["n_early_buyers"] = 0
        token_data["first_10_buyers"] = []
        token_data["first_20_buyers"] = []
    
    results.append(token_data)
    time.sleep(0.5)
    print()

# ── SAVE RAW DATA ──────────────────────────────────────────────────

# Save full results (without large buyer lists for readability)
output_summary = []
for r in results:
    summary = {k: v for k, v in r.items() if k != "early_buyers"}
    output_summary.append(summary)

with open(f"{OUT_DIR}/who_family_pilot_v1_raw_data.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print("=" * 70)
print("DATA GATHERING COMPLETE")
print("=" * 70)

# ── ANALYSIS ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("ANALYSIS")
print("=" * 70)

# A) DEPLOYER RECIDIVISM
print("\n--- A) DEPLOYER RECIDIVISM ---")
stronger_deployers = [r["mint_authority"] for r in results if r["group"] == "stronger" and r["mint_authority"]]
weaker_deployers = [r["mint_authority"] for r in results if r["group"] == "weaker" and r["mint_authority"]]

# For pumpfun tokens, mint authority is typically revoked (set to None or the pumpfun program)
# Check if any deployers appear in both groups
all_deployers = stronger_deployers + weaker_deployers
deployer_counts = Counter(all_deployers)
repeat_deployers = {d: c for d, c in deployer_counts.items() if c > 1}

print(f"  Stronger deployers found: {len(stronger_deployers)}")
print(f"  Weaker deployers found: {len(weaker_deployers)}")
print(f"  Unique deployers: {len(set(all_deployers))}")
print(f"  Repeat deployers: {len(repeat_deployers)}")
for d, c in repeat_deployers.items():
    groups = [r["symbol"] + f"({r['group']})" for r in results if r["mint_authority"] == d]
    print(f"    {d[:16]}... appears {c}x: {', '.join(groups)}")

# B) EARLY-BUYER OVERLAP
print("\n--- B) EARLY-BUYER OVERLAP ---")

def compute_overlap(group_results, n_buyers=10):
    """Compute pairwise overlap of first N buyers between tokens in a group."""
    overlaps = []
    tokens = [(r["symbol"], set(r[f"first_{n_buyers}_buyers"][:n_buyers])) for r in group_results if r[f"first_{n_buyers}_buyers"]]
    
    for i in range(len(tokens)):
        for j in range(i+1, len(tokens)):
            sym_i, buyers_i = tokens[i]
            sym_j, buyers_j = tokens[j]
            if buyers_i and buyers_j:
                overlap = len(buyers_i & buyers_j)
                union = len(buyers_i | buyers_j)
                jaccard = overlap / union if union > 0 else 0
                overlaps.append({
                    "token_a": sym_i,
                    "token_b": sym_j,
                    "overlap_count": overlap,
                    "jaccard": jaccard,
                    "set_a_size": len(buyers_i),
                    "set_b_size": len(buyers_j),
                })
    return overlaps

stronger_results = [r for r in results if r["group"] == "stronger"]
weaker_results = [r for r in results if r["group"] == "weaker"]

for n in [10, 20]:
    print(f"\n  First {n} buyers overlap:")
    s_overlaps = compute_overlap(stronger_results, n)
    w_overlaps = compute_overlap(weaker_results, n)
    
    s_avg_overlap = sum(o["overlap_count"] for o in s_overlaps) / len(s_overlaps) if s_overlaps else 0
    w_avg_overlap = sum(o["overlap_count"] for o in w_overlaps) / len(w_overlaps) if w_overlaps else 0
    s_avg_jaccard = sum(o["jaccard"] for o in s_overlaps) / len(s_overlaps) if s_overlaps else 0
    w_avg_jaccard = sum(o["jaccard"] for o in w_overlaps) / len(w_overlaps) if w_overlaps else 0
    
    print(f"    Stronger group: avg overlap = {s_avg_overlap:.2f}, avg Jaccard = {s_avg_jaccard:.4f} ({len(s_overlaps)} pairs)")
    print(f"    Weaker group:   avg overlap = {w_avg_overlap:.2f}, avg Jaccard = {w_avg_jaccard:.4f} ({len(w_overlaps)} pairs)")
    
    # Cross-group overlap
    cross_overlaps = []
    for sr in stronger_results:
        for wr in weaker_results:
            sb = set(sr[f"first_{n}_buyers"][:n])
            wb = set(wr[f"first_{n}_buyers"][:n])
            if sb and wb:
                overlap = len(sb & wb)
                union = len(sb | wb)
                cross_overlaps.append({
                    "stronger": sr["symbol"],
                    "weaker": wr["symbol"],
                    "overlap_count": overlap,
                    "jaccard": overlap / union if union > 0 else 0,
                })
    
    cross_avg = sum(o["overlap_count"] for o in cross_overlaps) / len(cross_overlaps) if cross_overlaps else 0
    cross_jaccard = sum(o["jaccard"] for o in cross_overlaps) / len(cross_overlaps) if cross_overlaps else 0
    print(f"    Cross-group:    avg overlap = {cross_avg:.2f}, avg Jaccard = {cross_jaccard:.4f} ({len(cross_overlaps)} pairs)")

# C) SMART-MONEY CONCENTRATION
print("\n--- C) SMART-MONEY CONCENTRATION ---")

def buyer_concentration(buyers_list, top_n=3):
    """Compute concentration of early buyers by amount."""
    if not buyers_list:
        return {"top1_pct": None, "top3_pct": None, "hhi": None}
    
    amounts = [b["amount"] for b in buyers_list if b["amount"] > 0]
    if not amounts:
        return {"top1_pct": None, "top3_pct": None, "hhi": None}
    
    total = sum(amounts)
    sorted_amounts = sorted(amounts, reverse=True)
    
    top1_pct = sorted_amounts[0] / total * 100 if total > 0 else 0
    top3_pct = sum(sorted_amounts[:3]) / total * 100 if total > 0 else 0
    
    # HHI
    shares = [a / total for a in amounts]
    hhi = sum(s**2 for s in shares) * 10000
    
    return {"top1_pct": round(top1_pct, 1), "top3_pct": round(top3_pct, 1), "hhi": round(hhi, 0)}

print(f"  {'Token':<15} {'Group':<10} {'Buyers':<8} {'Top1%':<8} {'Top3%':<8} {'HHI':<8}")
print(f"  {'-'*15} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

for r in results:
    conc = buyer_concentration(r["early_buyers"][:20])
    r["concentration"] = conc
    print(f"  {r['symbol']:<15} {r['group']:<10} {r['n_early_buyers']:<8} "
          f"{conc['top1_pct'] or 'N/A':<8} {conc['top3_pct'] or 'N/A':<8} {conc['hhi'] or 'N/A':<8}")

# D) NULL / PLACEBO COMPARISON
print("\n--- D) NULL / PLACEBO COMPARISON ---")
import random
random.seed(42)

# Shuffled grouping baseline: randomly assign tokens to "stronger" and "weaker"
# and recompute overlap metrics
N_SHUFFLES = 1000
shuffle_overlaps_10 = []
shuffle_overlaps_20 = []

all_first_10 = [(r["symbol"], set(r["first_10_buyers"][:10])) for r in results if r["first_10_buyers"]]
all_first_20 = [(r["symbol"], set(r["first_20_buyers"][:20])) for r in results if r["first_20_buyers"]]

for _ in range(N_SHUFFLES):
    # Shuffle and split
    shuffled_10 = list(all_first_10)
    random.shuffle(shuffled_10)
    group_a = shuffled_10[:10]
    group_b = shuffled_10[10:]
    
    # Compute within-group overlap for group_a
    overlaps = []
    for i in range(len(group_a)):
        for j in range(i+1, len(group_a)):
            if group_a[i][1] and group_a[j][1]:
                overlap = len(group_a[i][1] & group_a[j][1])
                overlaps.append(overlap)
    if overlaps:
        shuffle_overlaps_10.append(sum(overlaps) / len(overlaps))

for _ in range(N_SHUFFLES):
    shuffled_20 = list(all_first_20)
    random.shuffle(shuffled_20)
    group_a = shuffled_20[:10]
    group_b = shuffled_20[10:]
    
    overlaps = []
    for i in range(len(group_a)):
        for j in range(i+1, len(group_a)):
            if group_a[i][1] and group_a[j][1]:
                overlap = len(group_a[i][1] & group_a[j][1])
                overlaps.append(overlap)
    if overlaps:
        shuffle_overlaps_20.append(sum(overlaps) / len(overlaps))

# Actual stronger-group overlap
actual_s10 = compute_overlap(stronger_results, 10)
actual_s20 = compute_overlap(stronger_results, 20)
actual_s10_avg = sum(o["overlap_count"] for o in actual_s10) / len(actual_s10) if actual_s10 else 0
actual_s20_avg = sum(o["overlap_count"] for o in actual_s20) / len(actual_s20) if actual_s20 else 0

if shuffle_overlaps_10:
    null_mean_10 = sum(shuffle_overlaps_10) / len(shuffle_overlaps_10)
    null_std_10 = (sum((x - null_mean_10)**2 for x in shuffle_overlaps_10) / len(shuffle_overlaps_10)) ** 0.5
    z_10 = (actual_s10_avg - null_mean_10) / null_std_10 if null_std_10 > 0 else 0
    pct_above_10 = sum(1 for x in shuffle_overlaps_10 if x >= actual_s10_avg) / len(shuffle_overlaps_10) * 100
    print(f"  First-10 overlap: actual stronger = {actual_s10_avg:.3f}, null mean = {null_mean_10:.3f}, z = {z_10:.2f}, p(null >= actual) = {pct_above_10:.1f}%")

if shuffle_overlaps_20:
    null_mean_20 = sum(shuffle_overlaps_20) / len(shuffle_overlaps_20)
    null_std_20 = (sum((x - null_mean_20)**2 for x in shuffle_overlaps_20) / len(shuffle_overlaps_20)) ** 0.5
    z_20 = (actual_s20_avg - null_mean_20) / null_std_20 if null_std_20 > 0 else 0
    pct_above_20 = sum(1 for x in shuffle_overlaps_20 if x >= actual_s20_avg) / len(shuffle_overlaps_20) * 100
    print(f"  First-20 overlap: actual stronger = {actual_s20_avg:.3f}, null mean = {null_mean_20:.3f}, z = {z_20:.2f}, p(null >= actual) = {pct_above_20:.1f}%")

# Save analysis results
analysis = {
    "deployer_recidivism": {
        "stronger_deployers": len(stronger_deployers),
        "weaker_deployers": len(weaker_deployers),
        "unique_deployers": len(set(all_deployers)),
        "repeat_deployers": len(repeat_deployers),
        "repeat_details": {d[:16]: c for d, c in repeat_deployers.items()},
    },
    "early_buyer_overlap": {
        "first_10": {
            "stronger_avg": round(actual_s10_avg, 3),
            "weaker_avg": round(sum(o["overlap_count"] for o in compute_overlap(weaker_results, 10)) / max(len(compute_overlap(weaker_results, 10)), 1), 3),
            "null_mean": round(null_mean_10, 3) if shuffle_overlaps_10 else None,
            "z_score": round(z_10, 2) if shuffle_overlaps_10 else None,
            "p_value_pct": round(pct_above_10, 1) if shuffle_overlaps_10 else None,
        },
        "first_20": {
            "stronger_avg": round(actual_s20_avg, 3),
            "weaker_avg": round(sum(o["overlap_count"] for o in compute_overlap(weaker_results, 20)) / max(len(compute_overlap(weaker_results, 20)), 1), 3),
            "null_mean": round(null_mean_20, 3) if shuffle_overlaps_20 else None,
            "z_score": round(z_20, 2) if shuffle_overlaps_20 else None,
            "p_value_pct": round(pct_above_20, 1) if shuffle_overlaps_20 else None,
        },
    },
    "concentration": {
        "stronger": [{"symbol": r["symbol"], **r["concentration"]} for r in results if r["group"] == "stronger"],
        "weaker": [{"symbol": r["symbol"], **r["concentration"]} for r in results if r["group"] == "weaker"],
    },
}

with open(f"{OUT_DIR}/who_family_pilot_v1_analysis.json", "w") as f:
    json.dump(analysis, f, indent=2)

print(f"\nAll data saved to {OUT_DIR}/")
print("Done.")
