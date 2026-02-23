"""
Rent Reclaim — Close empty Token-2022 accounts to recover SOL rent.

Each pump.fun token buy creates a Token-2022 account that locks ~0.00207 SOL.
After selling 100% of tokens, the account is empty but still exists.
Closing it returns the rent to the wallet.

Usage:
  python3 rent_reclaim.py              # Sweep all empty accounts
  python3 rent_reclaim.py --dry-run    # Show what would be closed without executing
"""

import os
import sys
import json
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("rent_reclaim")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# Config
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "") or os.getenv("SOLANA_PRIVATE_KEY", "")

TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def get_empty_token_accounts():
    """Find all empty Token-2022 and SPL Token accounts in the wallet."""
    empty_accounts = []
    
    for program_id, program_name in [
        (TOKEN_2022_PROGRAM, "Token-2022"),
        (SPL_TOKEN_PROGRAM, "SPL Token"),
    ]:
        try:
            resp = requests.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    WALLET_ADDRESS,
                    {"programId": program_id},
                    {"encoding": "jsonParsed"}
                ]
            }, timeout=15)
            
            accounts = resp.json().get("result", {}).get("value", [])
            for acc in accounts:
                info = acc["account"]["data"]["parsed"]["info"]
                amount = int(info["tokenAmount"]["amount"])
                if amount == 0:
                    empty_accounts.append({
                        "pubkey": acc["pubkey"],
                        "mint": info["mint"],
                        "lamports": acc["account"]["lamports"],
                        "program": program_name,
                        "program_id": program_id,
                    })
        except Exception as e:
            logger.error(f"Error fetching {program_name} accounts: {e}")
    
    return empty_accounts


def close_account_via_rpc(token_account_pubkey, program_id):
    """
    Close a token account by building and sending a closeAccount instruction.
    Uses the solders/solana Python libraries.
    """
    try:
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.instruction import Instruction, AccountMeta
        from solders.transaction import Transaction
        from solders.message import Message
        from solders.hash import Hash
        import base58
        
        # Decode private key
        private_key_bytes = base58.b58decode(WALLET_PRIVATE_KEY)
        keypair = Keypair.from_bytes(private_key_bytes)
        owner_pubkey = keypair.pubkey()
        
        account_pubkey = Pubkey.from_string(token_account_pubkey)
        program_pubkey = Pubkey.from_string(program_id)
        
        # CloseAccount instruction (index 9 in SPL Token program)
        # Accounts: [account_to_close, destination (rent recipient), owner]
        close_ix = Instruction(
            program_id=program_pubkey,
            accounts=[
                AccountMeta(pubkey=account_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=owner_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=owner_pubkey, is_signer=True, is_writable=False),
            ],
            data=bytes([9]),  # CloseAccount instruction index
        )
        
        # Get recent blockhash
        resp = requests.post(HELIUS_RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}]
        }, timeout=10)
        blockhash_str = resp.json()["result"]["value"]["blockhash"]
        recent_blockhash = Hash.from_string(blockhash_str)
        
        # Build and sign transaction
        msg = Message.new_with_blockhash(
            [close_ix],
            owner_pubkey,
            recent_blockhash,
        )
        tx = Transaction.new_unsigned(msg)
        tx.sign([keypair], recent_blockhash)
        
        # Send transaction
        tx_bytes = bytes(tx)
        import base64
        tx_b64 = base64.b64encode(tx_bytes).decode("utf-8")
        
        resp = requests.post(HELIUS_RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [tx_b64, {"encoding": "base64", "skipPreflight": False}]
        }, timeout=30)
        
        result = resp.json()
        if "error" in result:
            return None, str(result["error"])
        
        tx_sig = result.get("result")
        return tx_sig, None
        
    except Exception as e:
        return None, str(e)


def sweep_empty_accounts(dry_run=False):
    """Close all empty token accounts and recover rent."""
    empty = get_empty_token_accounts()
    
    if not empty:
        logger.info("No empty token accounts found. Nothing to reclaim.")
        return 0, 0.0
    
    total_recoverable = sum(a["lamports"] for a in empty) / 1e9
    logger.info(f"Found {len(empty)} empty accounts with {total_recoverable:.6f} SOL in rent")
    
    if dry_run:
        for acc in empty:
            logger.info(f"  [DRY RUN] Would close: {acc['pubkey']} ({acc['program']}) — {acc['lamports']/1e9:.6f} SOL")
        return len(empty), total_recoverable
    
    closed = 0
    recovered = 0.0
    
    for acc in empty:
        logger.info(f"Closing {acc['pubkey']} ({acc['program']}, mint={acc['mint'][:16]}...)")
        
        tx_sig, error = close_account_via_rpc(acc["pubkey"], acc["program_id"])
        
        if tx_sig:
            closed += 1
            recovered += acc["lamports"] / 1e9
            logger.info(f"  SUCCESS: tx={tx_sig} — recovered {acc['lamports']/1e9:.6f} SOL")
            time.sleep(0.5)  # Rate limit between transactions
        else:
            logger.error(f"  FAILED: {error}")
    
    logger.info(f"\nSummary: closed {closed}/{len(empty)} accounts, recovered {recovered:.6f} SOL")
    return closed, recovered


def close_single_account(token_account_pubkey, program_id=TOKEN_2022_PROGRAM):
    """Close a single token account. Used by live_executor after sells."""
    tx_sig, error = close_account_via_rpc(token_account_pubkey, program_id)
    if tx_sig:
        logger.info(f"[RENT RECLAIM] Closed {token_account_pubkey[:16]}... — tx={tx_sig}")
        return True, tx_sig
    else:
        logger.warning(f"[RENT RECLAIM FAILED] {token_account_pubkey[:16]}...: {error}")
        return False, error


def find_token_account_for_mint(mint_address):
    """Find the token account pubkey for a given mint in the wallet."""
    for program_id in [TOKEN_2022_PROGRAM, SPL_TOKEN_PROGRAM]:
        try:
            resp = requests.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    WALLET_ADDRESS,
                    {"mint": mint_address},
                    {"encoding": "jsonParsed"}
                ]
            }, timeout=10)
            accounts = resp.json().get("result", {}).get("value", [])
            if accounts:
                info = accounts[0]["account"]["data"]["parsed"]["info"]
                amount = int(info["tokenAmount"]["amount"])
                return {
                    "pubkey": accounts[0]["pubkey"],
                    "amount": amount,
                    "program_id": program_id,
                    "lamports": accounts[0]["account"]["lamports"],
                }
        except Exception as e:
            logger.error(f"Error finding account for mint {mint_address}: {e}")
    return None


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        logger.info("=== DRY RUN MODE ===")
    
    # Get wallet balance before
    try:
        resp = requests.post(HELIUS_RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getBalance",
            "params": [WALLET_ADDRESS]
        }, timeout=10)
        balance_before = resp.json()["result"]["value"] / 1e9
        logger.info(f"Wallet balance before: {balance_before:.6f} SOL")
    except:
        balance_before = None
    
    closed, recovered = sweep_empty_accounts(dry_run=dry_run)
    
    if not dry_run and closed > 0:
        time.sleep(2)  # Wait for confirmation
        try:
            resp = requests.post(HELIUS_RPC_URL, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getBalance",
                "params": [WALLET_ADDRESS]
            }, timeout=10)
            balance_after = resp.json()["result"]["value"] / 1e9
            logger.info(f"Wallet balance after: {balance_after:.6f} SOL")
            if balance_before:
                logger.info(f"Net change: {balance_after - balance_before:+.6f} SOL")
        except:
            pass
