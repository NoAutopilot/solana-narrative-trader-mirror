#!/usr/bin/env python3
"""
Burn dead tokens and close their Token-2022 accounts to reclaim rent.
Handles the "Non-native account can only be closed if its balance is zero" error
by first burning all tokens, then closing the account.
"""

import os
import sys
import time
import struct
import base64
import requests
import base58
from dotenv import load_dotenv

load_dotenv()

HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "") or os.getenv("SOLANA_PRIVATE_KEY", "")
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def burn_and_close(token_account_pubkey, mint_address, amount, program_id=TOKEN_2022_PROGRAM):
    """Burn all tokens in an account, then close it to reclaim rent."""
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta
    from solders.transaction import Transaction
    from solders.message import Message
    from solders.hash import Hash

    private_key_bytes = base58.b58decode(PRIVATE_KEY)
    keypair = Keypair.from_bytes(private_key_bytes)
    owner_pubkey = keypair.pubkey()

    account_pubkey = Pubkey.from_string(token_account_pubkey)
    mint_pubkey = Pubkey.from_string(mint_address)
    program_pubkey = Pubkey.from_string(program_id)

    # Burn instruction (index 8 in SPL Token / Token-2022)
    # Data: [8] + [amount as u64 little-endian]
    burn_data = bytes([8]) + struct.pack("<Q", amount)
    burn_ix = Instruction(
        program_id=program_pubkey,
        accounts=[
            AccountMeta(pubkey=account_pubkey, is_signer=False, is_writable=True),  # account
            AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=True),     # mint
            AccountMeta(pubkey=owner_pubkey, is_signer=True, is_writable=False),    # owner
        ],
        data=burn_data,
    )

    # CloseAccount instruction (index 9)
    close_ix = Instruction(
        program_id=program_pubkey,
        accounts=[
            AccountMeta(pubkey=account_pubkey, is_signer=False, is_writable=True),
            AccountMeta(pubkey=owner_pubkey, is_signer=False, is_writable=True),
            AccountMeta(pubkey=owner_pubkey, is_signer=True, is_writable=False),
        ],
        data=bytes([9]),
    )

    # Get recent blockhash
    resp = requests.post(HELIUS_RPC_URL, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getLatestBlockhash",
        "params": [{"commitment": "finalized"}]
    }, timeout=10)
    blockhash_str = resp.json()["result"]["value"]["blockhash"]
    recent_blockhash = Hash.from_string(blockhash_str)

    # Build TX with both instructions: burn then close
    msg = Message.new_with_blockhash(
        [burn_ix, close_ix],
        owner_pubkey,
        recent_blockhash,
    )
    tx = Transaction.new_unsigned(msg)
    tx.sign([keypair], recent_blockhash)

    # Send
    tx_bytes = bytes(tx)
    tx_b64 = base64.b64encode(tx_bytes).decode("utf-8")

    resp = requests.post(HELIUS_RPC_URL, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "sendTransaction",
        "params": [tx_b64, {"encoding": "base64", "skipPreflight": False}]
    }, timeout=30)

    result = resp.json()
    if "error" in result:
        return None, result["error"]
    return result.get("result"), None


def main():
    RPC = HELIUS_RPC_URL
    WALLET = WALLET_ADDRESS

    # Get starting balance
    r = requests.post(RPC, json={'jsonrpc': '2.0', 'id': 1, 'method': 'getBalance', 'params': [WALLET]})
    start_sol = r.json()['result']['value'] / 1e9
    print(f"Starting balance: {start_sol:.6f} SOL")

    # Get all Token-2022 accounts with tokens
    r = requests.post(RPC, json={
        'jsonrpc': '2.0', 'id': 2,
        'method': 'getTokenAccountsByOwner',
        'params': [WALLET, {'programId': TOKEN_2022_PROGRAM}, {'encoding': 'jsonParsed'}]
    })
    accounts = r.json()['result']['value']
    with_tokens = [a for a in accounts if int(a['account']['data']['parsed']['info']['tokenAmount']['amount']) > 0]

    print(f"Accounts with tokens to burn+close: {len(with_tokens)}")

    for acc in with_tokens:
        pubkey = acc['pubkey']
        info = acc['account']['data']['parsed']['info']
        mint = info['mint']
        amount = int(info['tokenAmount']['amount'])
        rent = acc['account']['lamports'] / 1e9

        print(f"\n  Account: {pubkey[:25]}...")
        print(f"  Mint:    {mint[:25]}...")
        print(f"  Tokens:  {amount}")
        print(f"  Rent:    {rent:.6f} SOL")

        sig, err = burn_and_close(pubkey, mint, amount)
        if sig:
            print(f"  SUCCESS: {sig}")
        else:
            print(f"  FAILED:  {err}")
        time.sleep(3)

    # Final balance
    time.sleep(5)
    r = requests.post(RPC, json={'jsonrpc': '2.0', 'id': 1, 'method': 'getBalance', 'params': [WALLET]})
    end_sol = r.json()['result']['value'] / 1e9

    # Remaining accounts
    r = requests.post(RPC, json={
        'jsonrpc': '2.0', 'id': 2,
        'method': 'getTokenAccountsByOwner',
        'params': [WALLET, {'programId': TOKEN_2022_PROGRAM}, {'encoding': 'jsonParsed'}]
    })
    remaining = r.json()['result']['value']

    print(f"\n=== RESULTS ===")
    print(f"Starting: {start_sol:.6f} SOL")
    print(f"Ending:   {end_sol:.6f} SOL")
    print(f"Reclaimed: {end_sol - start_sol:.6f} SOL")
    print(f"Remaining accounts: {len(remaining)}")


if __name__ == "__main__":
    main()
