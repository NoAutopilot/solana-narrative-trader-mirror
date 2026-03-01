#!/usr/bin/env python3
"""
Corrected backfill: Use actual on-chain pre/post balance changes
instead of Helius parsed sol_in/sol_out which was missing SOL returns.
"""
import json
import requests
import time
import sqlite3
from datetime import datetime, timezone

WALLET = "<REDACTED_WALLET_PUBKEY>"
RPC = "https://mainnet.<REDACTED_HELIUS>/?api-key=<REDACTED>"

def get_tx_balance_change(sig):
    """Get the actual SOL balance change for our wallet from on-chain data."""
    resp = requests.post(RPC, json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'getTransaction',
        'params': [sig, {'encoding': 'jsonParsed', 'maxSupportedTransactionVersion': 0}]
    })
    data = resp.json()
    if 'result' not in data or not data['result']:
        return None
    
    result = data['result']
    meta = result.get('meta', {})
    
    # Find our wallet's index in the account keys
    accounts = result.get('transaction', {}).get('message', {}).get('accountKeys', [])
    wallet_idx = None
    for i, acc in enumerate(accounts):
        pubkey = acc.get('pubkey', acc) if isinstance(acc, dict) else acc
        if pubkey == WALLET:
            wallet_idx = i
            break
    
    if wallet_idx is None:
        return None
    
    pre_bal = meta.get('preBalances', [])
    post_bal = meta.get('postBalances', [])
    fee = meta.get('fee', 0)
    err = meta.get('err')
    
    if wallet_idx < len(pre_bal) and wallet_idx < len(post_bal):
        pre_sol = pre_bal[wallet_idx] / 1e9
        post_sol = post_bal[wallet_idx] / 1e9
        net_change = post_sol - pre_sol  # includes fee
        gross_change = net_change + (fee / 1e9)  # exclude fee
        return {
            'pre_sol': pre_sol,
            'post_sol': post_sol,
            'net_change': net_change,
            'gross_change': gross_change,
            'fee_sol': fee / 1e9,
            'error': err
        }
    return None

def main():
    with open('data/backfill_raw.json') as f:
        raw = json.load(f)
    
    txs = raw['parsed_transactions']
    
    # Separate buys and sells based on our original classification
    buys = [tx for tx in txs if tx.get('action') == 'BUY' or 
            (tx.get('tokens_in') and tx.get('sol_out', 0) > 0.001)]
    sells = [tx for tx in txs if tx.get('tokens_out') and len(tx.get('tokens_out', [])) > 0]
    
    # Also include the "OTHER" type that we now know are sells
    others_that_are_sells = [tx for tx in txs if tx.get('action') == 'OTHER' and 
                              tx.get('tokens_out') and tx.get('source') in ('PUMP_FUN', 'PUMP_AMM')]
    
    all_sells = sells + [s for s in others_that_are_sells if s not in sells]
    
    print(f"Total TXs: {len(txs)}")
    print(f"Buys identified: {len(buys)}")
    print(f"Sells identified: {len(all_sells)}")
    print()
    
    # Re-check ALL sells with on-chain balance data
    print("Re-checking all sells with on-chain balance changes...")
    print("(This will take a few minutes due to RPC rate limits)")
    print()
    
    corrected_sells = []
    batch_size = 5
    
    for i, tx in enumerate(all_sells):
        sig = tx['signature']
        
        if i > 0 and i % batch_size == 0:
            time.sleep(0.5)  # Rate limit
        
        if i % 20 == 0:
            print(f"  Processing sell {i+1}/{len(all_sells)}...")
        
        balance = get_tx_balance_change(sig)
        
        if balance:
            corrected = {
                'signature': sig,
                'timestamp': tx['timestamp'],
                'source': tx.get('source', 'UNKNOWN'),
                'original_sol_in': tx.get('sol_in', 0),
                'actual_gross_change': balance['gross_change'],
                'actual_net_change': balance['net_change'],
                'fee_sol': balance['fee_sol'],
                'tokens_out': tx.get('tokens_out', []),
                'error': balance['error']
            }
            corrected_sells.append(corrected)
        else:
            print(f"  WARN: Could not fetch TX {sig[:20]}...")
    
    # Now also re-check buys
    print(f"\nRe-checking all buys with on-chain balance changes...")
    corrected_buys = []
    
    for i, tx in enumerate(buys):
        sig = tx['signature']
        
        if i > 0 and i % batch_size == 0:
            time.sleep(0.5)
        
        if i % 20 == 0:
            print(f"  Processing buy {i+1}/{len(buys)}...")
        
        balance = get_tx_balance_change(sig)
        
        if balance:
            corrected = {
                'signature': sig,
                'timestamp': tx['timestamp'],
                'source': tx.get('source', 'UNKNOWN'),
                'original_sol_out': tx.get('sol_out', 0),
                'actual_gross_change': balance['gross_change'],
                'actual_net_change': balance['net_change'],
                'fee_sol': balance['fee_sol'],
                'tokens_in': tx.get('tokens_in', []),
                'token_mint': tx.get('token_mint', ''),
                'error': balance['error']
            }
            corrected_buys.append(corrected)
        else:
            print(f"  WARN: Could not fetch TX {sig[:20]}...")
    
    # Save corrected data
    corrected_data = {
        'wallet': WALLET,
        'correction_date': datetime.now(timezone.utc).isoformat(),
        'corrected_buys': corrected_buys,
        'corrected_sells': corrected_sells,
    }
    
    with open('data/backfill_corrected.json', 'w') as f:
        json.dump(corrected_data, f, indent=2)
    
    # Analysis
    print("\n" + "=" * 60)
    print("  CORRECTED ON-CHAIN ACCOUNTING")
    print("=" * 60)
    
    total_buy_cost = sum(abs(b['actual_gross_change']) for b in corrected_buys if b['actual_gross_change'] < 0)
    total_sell_return = sum(s['actual_gross_change'] for s in corrected_sells if s['actual_gross_change'] > 0)
    total_fees = sum(b['fee_sol'] for b in corrected_buys) + sum(s['fee_sol'] for s in corrected_sells)
    
    zero_return_sells = [s for s in corrected_sells if s['actual_gross_change'] <= 0]
    positive_sells = [s for s in corrected_sells if s['actual_gross_change'] > 0]
    
    print(f"Total buys: {len(corrected_buys)}")
    print(f"Total buy cost: {total_buy_cost:.6f} SOL")
    print(f"Avg buy cost: {total_buy_cost/len(corrected_buys):.6f} SOL")
    print()
    print(f"Total sells: {len(corrected_sells)}")
    print(f"Sells returning SOL: {len(positive_sells)}")
    print(f"Sells returning 0 or negative: {len(zero_return_sells)}")
    print(f"Total sell returns: {total_sell_return:.6f} SOL")
    print()
    print(f"Gross PnL: {total_sell_return - total_buy_cost:+.6f} SOL")
    print(f"Total fees: {total_fees:.6f} SOL")
    print(f"Net PnL: {total_sell_return - total_buy_cost - total_fees:+.6f} SOL")
    print()
    
    # Sell return distribution
    sell_returns = sorted([s['actual_gross_change'] for s in corrected_sells], reverse=True)
    print("Sell return distribution:")
    print(f"  > 0.01 SOL: {len([s for s in sell_returns if s > 0.01])}")
    print(f"  0.005-0.01: {len([s for s in sell_returns if 0.005 <= s < 0.01])}")
    print(f"  0.001-0.005: {len([s for s in sell_returns if 0.001 <= s < 0.005])}")
    print(f"  0-0.001: {len([s for s in sell_returns if 0 < s < 0.001])}")
    print(f"  Exactly 0: {len([s for s in sell_returns if s == 0])}")
    print(f"  Negative: {len([s for s in sell_returns if s < 0])}")
    print()
    
    # Top 10 sells
    print("Top 10 sell returns:")
    for i, s in enumerate(sell_returns[:10]):
        print(f"  {i+1}. {s:+.6f} SOL")
    
    # Win/loss with correct data
    # Match buys to sells by token mint
    print()
    print("=" * 60)
    print("  TRADE-LEVEL P&L (matched buys to sells)")
    print("=" * 60)
    
    # Group buys by token mint
    buy_by_mint = {}
    for b in corrected_buys:
        mint = b.get('token_mint', '')
        if not mint and b.get('tokens_in'):
            mint = b['tokens_in'][0].get('mint', '')
        if mint:
            if mint not in buy_by_mint:
                buy_by_mint[mint] = []
            buy_by_mint[mint].append(b)
    
    # Group sells by token mint
    sell_by_mint = {}
    for s in corrected_sells:
        if s.get('tokens_out'):
            mint = s['tokens_out'][0].get('mint', '')
            if mint:
                if mint not in sell_by_mint:
                    sell_by_mint[mint] = []
                sell_by_mint[mint].append(s)
    
    # Match and calculate PnL per trade
    trades = []
    for mint in buy_by_mint:
        buy_cost = sum(abs(b['actual_gross_change']) for b in buy_by_mint[mint])
        sell_return = sum(s['actual_gross_change'] for s in sell_by_mint.get(mint, []) if s['actual_gross_change'] > 0)
        pnl = sell_return - buy_cost
        pnl_pct = (sell_return / buy_cost - 1) * 100 if buy_cost > 0 else 0
        trades.append({
            'mint': mint,
            'buy_cost': buy_cost,
            'sell_return': sell_return,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'n_buys': len(buy_by_mint[mint]),
            'n_sells': len(sell_by_mint.get(mint, []))
        })
    
    trades.sort(key=lambda x: x['pnl'], reverse=True)
    
    winners = [t for t in trades if t['pnl'] > 0]
    losers = [t for t in trades if t['pnl'] <= 0]
    
    print(f"Total matched trades: {len(trades)}")
    print(f"Winners: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
    print(f"Losers: {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")
    print()
    
    print("Top 10 winners:")
    for t in winners[:10]:
        print(f"  {t['mint'][:20]}... | cost={t['buy_cost']:.4f} | return={t['sell_return']:.4f} | PnL={t['pnl']:+.4f} ({t['pnl_pct']:+.0f}%)")
    
    print()
    print("Worst 10 losers:")
    for t in losers[:10]:
        loss_pct = (t['sell_return'] / t['buy_cost'] * 100) if t['buy_cost'] > 0 else 0
        print(f"  {t['mint'][:20]}... | cost={t['buy_cost']:.4f} | return={t['sell_return']:.4f} | kept={loss_pct:.0f}%")
    
    # The key question: what % of buy cost do losers typically recover?
    loser_recovery = []
    for t in losers:
        if t['buy_cost'] > 0:
            recovery = t['sell_return'] / t['buy_cost']
            loser_recovery.append(recovery)
    
    if loser_recovery:
        avg_recovery = sum(loser_recovery) / len(loser_recovery)
        print(f"\nAvg loser recovery: {avg_recovery*100:.1f}% of buy cost")
        print(f"Median loser recovery: {sorted(loser_recovery)[len(loser_recovery)//2]*100:.1f}%")
        zero_recovery = len([r for r in loser_recovery if r < 0.01])
        print(f"Losers with <1% recovery: {zero_recovery} ({zero_recovery/len(loser_recovery)*100:.0f}%)")
        partial_recovery = len([r for r in loser_recovery if 0.01 <= r < 0.5])
        print(f"Losers with 1-50% recovery: {partial_recovery} ({partial_recovery/len(loser_recovery)*100:.0f}%)")
        good_recovery = len([r for r in loser_recovery if r >= 0.5])
        print(f"Losers with 50%+ recovery: {good_recovery} ({good_recovery/len(loser_recovery)*100:.0f}%)")

if __name__ == "__main__":
    main()
