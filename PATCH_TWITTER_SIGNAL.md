# Twitter Signal Integration Patch for paper_trader.py

**Purpose:** Log Twitter buzz data for every trade entry (observation only — does NOT change trading behavior).

**Files already updated:**
- `twitter_signal.py` — NEW module, fully tested
- `database.py` — `log_trade()` now accepts `twitter_signal_data` kwarg, `twitter_signal_data` TEXT column added via safe migration

**What needs to change in `paper_trader.py`:**

## Step 1: Add import at the top of paper_trader.py

```python
# Add near the other imports at the top of the file:
from twitter_signal import check_twitter_signal
```

## Step 2: Find the trade entry section

Look for where `log_trade()` is called. It will look something like:

```python
trade_id = database.log_trade(
    evaluation_id=eval_id,
    mint_address=mint,
    token_name=name,
    token_symbol=symbol,
    entry_price_usd=price,
    entry_sol=entry_sol,
    tx_signature=tx_sig,
    simulation=True,
    trade_mode=trade_mode,
    narrative_age=narrative_age,
    category=category,
    strategy_version=strategy_version,
    strategy_params=strategy_params
)
```

## Step 3: Add Twitter signal check BEFORE log_trade()

Insert this block right before the `log_trade()` call:

```python
# --- Twitter signal logging (observation only) ---
try:
    twitter_signal = check_twitter_signal(
        token_name=name,
        token_symbol=symbol,
        narrative_keyword=best_narrative_keyword  # or whatever var holds the matched narrative
    )
    logger.info(f"[Twitter] {name}: {twitter_signal['tweet_count']} tweets, "
                f"engagement={twitter_signal['total_engagement']}, "
                f"kol={twitter_signal['has_kol']}")
except Exception as e:
    twitter_signal = None
    logger.warning(f"[Twitter] Signal check failed for {name}: {e}")
```

## Step 4: Pass twitter_signal to log_trade()

Add the `twitter_signal_data` parameter to the existing `log_trade()` call:

```python
trade_id = database.log_trade(
    evaluation_id=eval_id,
    mint_address=mint,
    token_name=name,
    token_symbol=symbol,
    entry_price_usd=price,
    entry_sol=entry_sol,
    tx_signature=tx_sig,
    simulation=True,
    trade_mode=trade_mode,
    narrative_age=narrative_age,
    category=category,
    strategy_version=strategy_version,
    strategy_params=strategy_params,
    twitter_signal_data=twitter_signal  # <-- ADD THIS LINE
)
```

## Step 5: Run init_db() to add the column

```bash
cd /home/ubuntu/solana_trader && python3 -c "from database import init_db; init_db()"
```

## Step 6: Restart paper trader

```bash
# Find and kill current paper trader
ps aux | grep paper_trader | grep -v grep | awk '{print $2}' | xargs kill
sleep 2
# Restart (adjust path as needed)
cd /home/ubuntu/solana_trader && nohup python3 paper_trader.py >> logs/paper_trader.log 2>&1 &
```

## Verification

After a few trades, check that twitter_signal_data is being logged:

```sql
SELECT id, token_name, twitter_signal_data 
FROM trades 
WHERE twitter_signal_data IS NOT NULL 
ORDER BY id DESC LIMIT 5;
```

## Rate Limiting Note

The Twitter API is rate-limited to 1 call per 3 seconds in `twitter_signal.py`. Each trade entry makes up to 2 API calls (token name + narrative keyword). This adds ~6 seconds of latency per trade entry. Since we're paper trading and not racing for speed, this is acceptable. For live trading, this should be made async.
