# Solana ET Trader — Session Handoff Prompt (v1.5)
**Last updated:** 2026-02-25 ~18:00 UTC  
**GitHub:** `NoAutopilot/solana-narrative-trader` @ commit `fa60b77`  
**VPS:** `root@142.93.24.227` | Service: `solana-trader.service`  
**DB:** `/root/solana_trader/data/solana_trader.db` → table `shadow_trades_v1`

---

## How to Resume

```bash
ssh root@142.93.24.227
cd /root/solana_trader
python3 et_daily_report_v7.py
```

---

## System State

### Processes (managed by `solana-trader.service` via `supervisor.py`)
| Process | Script | Status |
|---|---|---|
| universe_scanner | et_universe_scanner.py (v1.1) | Running |
| microstructure | et_microstructure.py | Running |
| shadow_trader_v1 | et_shadow_trader_v1.py (v1.5) | Running |
| pf_graduation | pf_graduation_stream.py | Running |

**Old harness (`et_shadow_trader.py`) — RETIRED.**

### Jupiter API
- Endpoint: `api.jup.ag/ultra/v1/order` + `x-api-key` header ✅
- Startup health check: `JUP_HEALTH: OK` logged on each restart
- Real RT quotes confirmed active (~0.21–0.23% for pumpswap tokens)

### Universe
75 eligible tokens per scan: 20 large-cap + ~55 PumpSwap graduated (DexScreener, refreshed 30min).

---

## ET v1 Strategy Variants

| Variant | Type | Entry Conditions |
|---|---|---|
| `momentum_strict` | Strict | r_m5≥0.8%, buy_ratio≥0.6, vol_accel≥1.5, avg_trade≥$100 |
| `pullback_strict` | Strict | r_h1≥2.0%, r_m5≤-0.6% + confirm r_m5≥-0.3% within 75s |
| `momentum_rank` | Score/rank | top-1 per 30min, floors: r_m5≥0, buy_ratio≥0.25, vol_accel≥0.20 |
| `pullback_rank` | Score/rank | top-1 per 30min, floors: r_h1≥0.5%, r_m5≤0, buy_ratio≥0.25 |

Exits (unified): TP +4.0% / SL -2.0% / Timeout 12min / Hard max 30min / LP cliff 5% k-drop  
Each variant has matched baseline: `baseline_matched_{variant}`

---

## v1.5 Changes (This Session)

1. **Poll-gap diagnosis columns**: `prev_poll_at`, `prev_poll_pnl_pct`, `curr_poll_at`, `curr_poll_pnl_pct` — stored at first threshold cross. Separates poll-gap delay from execution latency.
2. **Hard max hold**: `HARD_MAX_HOLD_MINUTES = 30` — absolute cap, overrides timeout filter. Prevents indefinite holds.
3. **Timeout skipped count**: `timeout_skipped_count` per trade — counts how many timeout checks were skipped by the filter.
4. **Report v7 fixes**: Correct paired delta join direction (`b.baseline_trigger_id = s.trade_id`), poll-gap detail section, timeout_skipped per strategy.

---

## Report v7 Findings (2026-02-25 18:00 UTC, 141 closed trades)

### Friction Floor (final)
| Component | Value |
|---|---|
| DEX fee (RT) | 0.500% |
| Network/prio (RPC backfill) | 0.142% (7,092 lam/tx) |
| **Total RT floor at 0.01 SOL** | **0.644%** |
| Total RT floor at 0.02 SOL | 0.576% |

### Overshoot Audit (v1.5 data — new columns active)
- **SL exits**: avg overshoot = -3.07%, avg_delay = **0.6s** ✅
- **Worst trade**: NIRE -19.87% in 2s (0.9s detection) — genuine fast crash, not poll-gap
- **Conclusion**: The exit mechanism is working. Overshoot is genuine fast crashes on pump.fun tokens, not a polling problem.

### Per-Variant Paired Delta (CORRECT join direction)
| Variant | n_pairs | delta_fee060 | delta_fee100 | Verdict |
|---|---|---|---|---|
| `momentum_strict` | 15 | -1.68% | -1.68% | DOES NOT BEAT |
| `pullback_strict` | 10 | -1.27% | -1.27% | DOES NOT BEAT |
| `momentum_rank` | 13 | -2.27% | -2.27% | DOES NOT BEAT |
| `pullback_rank` | — | INSUFFICIENT_DATA (n=19) | — | — |

**All strategies currently underperform their random baselines.** Entry signals are adding negative value vs random selection.

### Exit Breakdown
- **Timeout exits**: avg gross = +0.06% to +1.28% — below 0.644% RT floor → net negative (timeout filter now active)
- **SL exits**: avg gross = -4.55% to -6.77% — genuine fast crashes (0.6s detection confirms)
- **TP exits**: avg gross = +4.46% to +16.40% — profitable, but rare (2–6 per strategy)

### LIVE_CANARY_READY_V1: NO
Blocking: `n_closed=141 < 150`, no strategy beats matched baseline.

---

## P0 Actions for Next Session (in order)

### 1. Run report and check trade accumulation
```bash
cd /root/solana_trader && python3 et_daily_report_v7.py
```

### 2. Check if pullback_rank crossed n>=20
```bash
python3 -c "
import sqlite3
from config.config import DB_PATH
conn = sqlite3.connect(DB_PATH)
for s in ['momentum_strict','pullback_strict','momentum_rank','pullback_rank']:
    n = conn.execute('SELECT COUNT(*) FROM shadow_trades_v1 WHERE strategy=? AND status=\"closed\"', (s,)).fetchone()[0]
    print(f'{s}: n={n}')
"
```

### 3. Interpret the paired delta results
After n≥20 per variant, check if any strategy beats its baseline under fee100.
- If **paired delta > 0 under fee100**: entry signal has edge — proceed to stability check
- If **paired delta still negative**: entry signal needs redesign, not more exit tuning

### 4. Consider token age filter (if SL overshoot persists)
The worst trades are pump.fun tokens with age < 2h. Consider:
```python
# In et_universe_scanner.py, add to pumpswap filter:
token_age_hours = (now - created_at).total_seconds() / 3600
if token_age_hours < 4:  # skip tokens < 4h old
    continue
```

### 5. Consider SL widening (if whipsaw is the issue)
If most SL exits are legitimate fast crashes (not rugs), widen SL from -2% to -3%:
```python
# In config/config.py:
SL_THRESHOLD_PCT = -0.03  # was -0.02
```

---

## GO/NO-GO Rules (unchanged)
```
min_closed_trades(strategy) >= 20        → else INSUFFICIENT_DATA
strategy beats matched baseline (fee100) → paired delta mean > 0
stability: >=2 six-hour blocks n>=10     → else INSUFFICIENT_DATA
concentration top-3 < 50%               → else CONCENTRATED
smoke test: PASS ✅                      → already done
```
**LIVE_CANARY_READY_V1 = YES** only when ALL above are met.  
No live canary with 0.14 SOL bankroll until gate passes.

---

## Key Files

| File | Purpose |
|---|---|
| `et_shadow_trader_v1.py` (v1.5) | Main v1 harness — adaptive polling, poll-gap columns, hard max hold |
| `et_universe_scanner.py` (v1.1) | Universe scanner — large-cap + pumpswap lanes |
| `et_daily_report_v7.py` | **USE THIS** — overshoot audit, paired delta (correct join), exit breakdown |
| `et_microstructure.py` | 15s price/volume scanner |
| `supervisor.py` | Systemd-managed process supervisor (v1 only) |
| `config/config.py` | JUPITER_API_KEY, DB_PATH, TRADE_SIZE_SOL |

---

## Wallet
- Live: **0.14 SOL** (DO NOT touch until GO/NO-GO met)
- Paper trade size: 0.01 SOL (virtual)
- Mode: `research_mode`
