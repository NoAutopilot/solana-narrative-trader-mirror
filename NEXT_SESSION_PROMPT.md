# Solana ET Trader — Session Handoff Prompt
**Last updated:** 2026-02-25 ~16:45 UTC  
**GitHub:** `NoAutopilot/solana-narrative-trader` commit `9866331` (branch: master)  
**VPS:** `root@142.93.24.227` | `/root/solana_trader/`  
**DB:** `/root/solana_trader/data/solana_trader.db`  
**Service:** `solana-trader.service` (systemd → supervisor.py)

---

## How to Resume

```bash
ssh root@142.93.24.227
cd /root/solana_trader
python3 et_daily_report_v6.py
```

---

## System State

### Processes (managed by `solana-trader.service` via `supervisor.py`)
| Process | Script | Status |
|---|---|---|
| universe_scanner | et_universe_scanner.py (v1.1) | Running |
| microstructure | et_microstructure.py | Running |
| shadow_trader_v1 | et_shadow_trader_v1.py | Running |
| pf_graduation | pf_graduation_stream.py | Running |

**Old harness (`et_shadow_trader.py`) — RETIRED.** Removed from supervisor.py.

### Jupiter API
- Endpoint: `api.jup.ag/ultra/v1/order` + `x-api-key` header ✅
- Startup health check: `JUP_HEALTH: OK` logged on each restart
- Real RT quotes confirmed active (~0.21% for Fartcoin)

### Universe
41 eligible tokens per scan: 20 large-cap + up to 25 PumpSwap graduated (DexScreener, refreshed 30min).

---

## ET v1 Strategy Variants

| Variant | Type | Entry Conditions |
|---|---|---|
| `momentum_strict` | Strict | r_m5≥0.8%, buy_ratio≥0.6, vol_accel≥1.5, avg_trade≥$100 |
| `pullback_strict` | Strict | r_h1≥2.0%, r_m5≤-0.6% + confirm r_m5≥-0.3% within 75s |
| `momentum_rank` | Score/rank | top-1 per 30min, floors: r_m5≥0, buy_ratio≥0.25, vol_accel≥0.20 |
| `pullback_rank` | Score/rank | top-1 per 30min, floors: r_h1≥0.5%, r_m5≤0, buy_ratio≥0.25 |

Exits (unified): TP +4.0% / SL -2.0% / Timeout 12min / LP cliff 5% k-drop  
Each variant has matched baseline: `baseline_matched_{variant}`

---

## Report v6 Findings (2026-02-25 16:35 UTC, 112 closed trades)

### Per-Variant Status
| Variant | n_closed | vs Baseline | Status |
|---|---|---|---|
| momentum_strict | 17 | N/A | INSUFFICIENT_DATA |
| pullback_strict | 17 | N/A | INSUFFICIENT_DATA |
| momentum_rank | 21 | DOES NOT BEAT (unpaired: -1.39% vs +0.25%) | QUALIFIED but failing |
| pullback_rank | 14 | N/A | INSUFFICIENT_DATA |

### Exit Reason Breakdown — Critical Findings
1. **SL overshoot is systemic**: avg SL exit = -4% to -6% gross vs -2% threshold
   - Worst case: TripleT token dropped -14% in 14 seconds (poll gap = 15s)
   - Root cause: exit monitor polls every 15s — too slow for pump.fun tokens
2. **Timeout wins are fee-negative**: avg timeout gross = 0.06% to 1.28% — below 0.64% RT floor
3. **TP exits are the only profitable exits**: avg +5% to +26% gross

### Friction Audit (corrected)
- Smoke test: 0.000014 SOL spent = **fees paid** (not trade size) = 7,092 lam/tx
- **Corrected total RT floor at 0.01 SOL: ~0.64%** (DEX 0.50% + network 0.14%)
- Previous report showed 0.503% — was undercounting network fee

### LIVE_CANARY_READY_V1: NO
Blocking: n_closed=112 (need 150), momentum_rank does not beat baseline, other strategies INSUFFICIENT_DATA.

---

## Action Items (Priority Order)

### P0 — Fix SL overshoot: tighten exit poll interval
**File:** `et_shadow_trader_v1.py` → `monitor_and_exit()` function  
**Change:** `time.sleep(15)` → `time.sleep(4)` (3-5s recommended)  
This is the highest-leverage fix. A 14s poll gap on a pump.fun token caused a -14% loss vs -2% SL.

### P1 — Set baseline_trigger_id for paired delta
**File:** `et_shadow_trader_v1.py` → `open_trade()` function  
After inserting the baseline trade, store its `trade_id` back into the strategy trade's `baseline_trigger_id` column.  
Without this, the paired delta query returns no pairs and falls back to unpaired comparison.

First run the migration:
```python
import sqlite3
conn = sqlite3.connect('/root/solana_trader/data/solana_trader.db')
try:
    conn.execute("ALTER TABLE shadow_trades_v1 ADD COLUMN baseline_trigger_id TEXT")
    conn.commit()
    print("Added baseline_trigger_id column")
except Exception as e:
    print(f"Already exists or error: {e}")
conn.close()
```

### P2 — Evaluate timeout exit policy
Timeouts average +0.06% to +1.28% gross — not clearing the 0.64% RT floor.  
Options:
1. Extend timeout from 12min to 20min (give TP more time to hit)
2. Add trailing stop after +2% to lock in partial gains
3. Accept timeouts as noise and focus on TP/SL ratio improvement

### P3 — pullback_strict signal starvation
17 closed trades after a full day. r_h1 >= 2.0% is too strict for current market.  
Consider lowering to 1.5% after 24h of data:
```python
PULLBACK_R_H1_MIN = 1.5  # was 2.0
```

### P4 — Fix universe scanner Jupiter check (minor, non-blocking)
`check_jupiter_available()` in `et_universe_scanner.py` still uses old URL.  
Fix: update to `/ultra/v1/order` with `x-api-key` header.

---

## GO/NO-GO Rules (unchanged)
```
min_closed_trades(strategy) >= 20        → else INSUFFICIENT_DATA
strategy beats matched baseline (fee060) → paired delta mean > 0
stability: >=2 six-hour blocks n>=10     → else INSUFFICIENT_DATA
concentration top-3 < 50%               → else CONCENTRATED
smoke test: PASS ✅                      → already done
```
**LIVE_CANARY_READY_V1 = YES** only when ALL above are met.  
No live canary with 0.14 SOL bankroll until gate passes.

---

## Quick Diagnostic Commands

```bash
# Run daily report
cd /root/solana_trader && python3 et_daily_report_v6.py

# Check processes
ps aux | grep -E 'shadow_trader|universe|microstructure|supervisor' | grep -v grep

# Check v1 harness log
tail -30 /root/solana_trader/logs/et_shadow_trader_v1.log

# Check trade counts
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/solana_trader/data/solana_trader.db')
rows = conn.execute('SELECT strategy, COUNT(*), SUM(CASE WHEN status=\"closed\" THEN 1 ELSE 0 END) FROM shadow_trades_v1 GROUP BY strategy').fetchall()
for r in rows: print(f'{r[0]}: total={r[1]}, closed={r[2]}')
"

# Restart service
systemctl restart solana-trader.service
```

---

## Key Files

| File | Purpose |
|---|---|
| `et_shadow_trader_v1.py` | Main v1 harness — Jupiter ultra, 4 strategy variants |
| `et_universe_scanner.py` | Universe scanner v1.1 — large-cap + pumpswap lanes |
| `et_daily_report_v6.py` | **USE THIS** — paired delta, exit breakdown, RPC fee, worst trade |
| `et_microstructure.py` | 15s price/volume scanner |
| `supervisor.py` | Systemd-managed process supervisor (v1 only) |
| `config/config.py` | JUPITER_API_KEY, DB_PATH, TRADE_SIZE_SOL |

---

## Wallet
- Live: **0.14 SOL** (DO NOT touch until GO/NO-GO met)
- Paper trade size: 0.01 SOL (virtual)
- Mode: research_mode
