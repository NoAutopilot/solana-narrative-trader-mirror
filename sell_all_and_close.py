#!/usr/bin/env python3
"""
sell_all_and_close.py
Sells all non-zero SPL token positions via Jupiter, then closes empty token accounts.
"""
import sys, base58, requests, time, base64
sys.path.insert(0, '/root/solana_trader')
from config.config import RPC_URL, WALLET_PRIVATE_KEY, JUPITER_API_KEY
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
WSOL_MINT = "So11111111111111111111111111111111111111112"
JUP_BASE = "https://<REDACTED_JUP>"

raw = base58.b58decode(WALLET_PRIVATE_KEY)
keypair = Keypair.from_bytes(raw)
wallet = str(keypair.pubkey())
print(f"Wallet: {wallet}")

def rpc(method, params):
    r = requests.post(RPC_URL, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=30)
    r.raise_for_status()
    return r.json()

def get_sol_balance():
    return rpc("getBalance", [wallet, {"commitment": "confirmed"}])["result"]["value"] / LAMPORTS_PER_SOL

def get_open_positions():
    res = rpc("getTokenAccountsByOwner", [
        wallet,
        {"programId": TOKEN_PROGRAM_ID},
        {"encoding": "jsonParsed", "commitment": "confirmed"}
    ])
    positions = []
    for acct in res["result"]["value"]:
        info = acct["account"]["data"]["parsed"]["info"]
        raw_amt = int(info["tokenAmount"]["amount"])
        lamports = acct["account"].get("lamports", 2039280)
        if raw_amt > 0 and info["mint"] != WSOL_MINT:
            positions.append({
                "account": acct["pubkey"],
                "mint": info["mint"],
                "raw_amount": raw_amt,
                "ui_amount": info["tokenAmount"]["uiAmount"],
                "lamports": lamports
            })
    return positions

def get_empty_accounts():
    res = rpc("getTokenAccountsByOwner", [
        wallet,
        {"programId": TOKEN_PROGRAM_ID},
        {"encoding": "jsonParsed", "commitment": "confirmed"}
    ])
    empty = []
    for acct in res["result"]["value"]:
        info = acct["account"]["data"]["parsed"]["info"]
        raw_amt = int(info["tokenAmount"]["amount"])
        lamports = acct["account"].get("lamports", 2039280)
        if raw_amt == 0 and info["mint"] != WSOL_MINT:
            empty.append({
                "account": acct["pubkey"],
                "mint": info["mint"],
                "lamports": lamports
            })
    return empty

def jupiter_quote(input_mint, output_mint, amount, slippage_bps=100):
    headers = {"Authorization": f"Bearer {JUPITER_API_KEY}"}
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false"
    }
    r = requests.get(f"{JUP_BASE}/v6/quote", params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

def jupiter_swap_tx(quote_response):
    headers = {"Authorization": f"Bearer {JUPITER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "quoteResponse": quote_response,
        "userPublicKey": wallet,
        "wrapAndUnwrapSol": True,
        "prioritizationFeeLamports": 20000,
        "dynamicComputeUnitLimit": True
    }
    r = requests.post(f"{JUP_BASE}/v6/swap", json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

def sign_and_send(swap_tx_b64):
    tx_bytes = base64.b64decode(swap_tx_b64)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    signed = VersionedTransaction(tx.message, [keypair])
    signed_b64 = base64.b64encode(bytes(signed)).decode()
    result = rpc("sendTransaction", [signed_b64, {
        "encoding": "base64",
        "skipPreflight": False,
        "maxRetries": 3
    }])
    if "error" in result:
        return None, result["error"]
    return result["result"], None

def close_token_account(account_pubkey, retries=3):
    from solders.instruction import Instruction, AccountMeta
    from solders.hash import Hash
    from solders.message import MessageV0

    account_pk = Pubkey.from_string(account_pubkey)
    wallet_pk = keypair.pubkey()
    token_program_pk = Pubkey.from_string(TOKEN_PROGRAM_ID)

    close_ix = Instruction(
        program_id=token_program_pk,
        accounts=[
            AccountMeta(pubkey=account_pk, is_signer=False, is_writable=True),
            AccountMeta(pubkey=wallet_pk, is_signer=False, is_writable=True),
            AccountMeta(pubkey=wallet_pk, is_signer=True, is_writable=False),
        ],
        data=bytes([9])
    )

    for attempt in range(retries):
        # Fetch a fresh blockhash each attempt
        bh_resp = rpc("getLatestBlockhash", [{"commitment": "finalized"}])
        bh = bh_resp["result"]["value"]["blockhash"]
        msg = MessageV0.try_compile(
            payer=wallet_pk,
            instructions=[close_ix],
            address_lookup_table_accounts=[],
            recent_blockhash=Hash.from_string(bh)
        )
        tx = VersionedTransaction(msg, [keypair])
        tx_b64 = base64.b64encode(bytes(tx)).decode()
        result = rpc("sendTransaction", [tx_b64, {
            "encoding": "base64",
            "skipPreflight": True,   # skip simulation to avoid blockhash race
            "maxRetries": 5
        }])
        if "error" in result:
            err_msg = str(result["error"])
            if "BlockhashNotFound" in err_msg and attempt < retries - 1:
                time.sleep(1)
                continue
            return None, result["error"]
        return result["result"], None
    return None, "Max retries exceeded"

# ── MAIN ────────────────────────────────────────────────────────────────────
print(f"\nSOL balance before: {get_sol_balance():.6f}")

# Step 1: Sell all open positions
positions = get_open_positions()
print(f"\nFound {len(positions)} open token positions to sell:")
for p in positions:
    print(f"  {p['account'][:20]}... mint={p['mint'][:8]}... amount={p['ui_amount']}")

sold = 0
for p in positions:
    print(f"\nSelling {p['ui_amount']} of {p['mint'][:8]}...")
    try:
        quote = jupiter_quote(p["mint"], WSOL_MINT, p["raw_amount"], slippage_bps=200)
        out_sol = int(quote.get("outAmount", 0)) / LAMPORTS_PER_SOL
        print(f"  Quote: {out_sol:.6f} SOL out")
        swap_data = jupiter_swap_tx(quote)
        sig, err = sign_and_send(swap_data["swapTransaction"])
        if err:
            print(f"  SELL FAILED: {err}")
        else:
            print(f"  SELL TX: {sig}")
            sold += 1
        time.sleep(1)
    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\nSold {sold}/{len(positions)} positions")
time.sleep(3)

# Step 2: Close empty accounts (including newly emptied ones)
print("\nFetching empty accounts to close...")
empty = get_empty_accounts()
print(f"Found {len(empty)} empty accounts ({sum(a['lamports'] for a in empty)/LAMPORTS_PER_SOL:.6f} SOL reclaimable)")

closed = 0
for acct in empty:
    print(f"  Closing {acct['account'][:20]}... ({acct['lamports']/LAMPORTS_PER_SOL:.6f} SOL)")
    sig, err = close_token_account(acct["account"])
    if err:
        print(f"    CLOSE FAILED: {err}")
    else:
        print(f"    CLOSE TX: {sig}")
        closed += 1
    time.sleep(0.5)

print(f"\nClosed {closed}/{len(empty)} accounts")
time.sleep(3)

print(f"\nSOL balance after: {get_sol_balance():.6f}")
print("Done.")
