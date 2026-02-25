# Solana Trader — Session Handoff Prompt
**Last updated:** 2026-02-25 ~15:40 UTC  
**GitHub commit:** `491c7fb` (NoAutopilot/solana-narrative-trader, branch: master)  
**VPS:** `root@142.93.24.227` (DigitalOcean)  
**Working dir:** `/root/solana_trader/`  
**DB:** `/root/solana_trader/data/solana_trader.db`  
**Service:** `solana-trader.service` (systemd → supervisor.py)

---

## How to Resume

```bash
ssh root@142.93.24.227
cd /root/solana_trader
python3 et_daily_report_v5.py
```

---

## System State

### Processes (managed by `solana-trader.service` via `supervisor.py`)
| Process | Script | Status |
|---|---|---|
| universe_scanner | et_universe_scanner.py | Running — v1.1 (two lanes) |
| microstructure | et_microstructure_scanner.py | Running — 15s cycle |
| shadow_trader_v1 | et_shadow_trader_v1.py | Running — Jupiter ultra active |
| pf_graduation | pf_graduation_stream.py | Running |
| flask_dashboard | flask_dashboard.py | Running |

**Old harness (`et_shadow_trader.py`) — RETIRED.** Removed from supervisor.py. Will not respawn.

---

## ET v1 Playbook (Current Spec)

### Strategy Variants (4 active + 4 baselines)
| Variant | Type | Entry Conditions |
|---|---|---|
| `momentum_strict` | Strict | r_m5≥0.8%, buy_ratio≥0.6, vol_accel≥1.5, avg_trade≥$100 |
| `pullback_strict` | Strict | r_h1≥2.0%, r_m5≤-0.6% + confirm r_m5≥-0.3% within 75s |
| `momentum_rank` | Score/rank | top-1 per 30min, floors: r_m5≥0, buy_ratio≥0.25, vol_accel≥0.20 |
| `pullback_rank` | Score/rank | top-1 per 30min, floors: r_h1≥0.5%, r_m5≤0, buy_ratio≥0.25 |

Each variant has a matched baseline: `baseline_matched_{variant}` (random eligible token, same timestamp).

### Exits (unified)
TP: +4.0% / SL: -2.0% / Timeout: 12min / LP cliff: 5% k-drop

### Position Caps
`MAX_OPEN_PER_STRATEGY = 1` (research_mode, no global cap)

---

## Trade Accumulation (as of 15:32 UTC 2026-02-25)

| Strategy | Total | Closed | Gap to n≥20 |
|---|---|---|---|
| `momentum_rank` | 19 | 18 | **1 more needed** |
| `pullback_rank` | 12 | 11 | 9 more needed |
| `momentum_strict` | 9 | 9 | 11 more needed |
| `pullback_strict` | 1 | 1 | 19 more needed |

**LIVE_CANARY_READY_V1 = NO** (INSUFFICIENT_DATA — awaiting n≥20 per strategy)

---

## Key Changes This Session

### 1. Jupiter API — Fixed (was 401, now active)
- **Old endpoint:** `/v6/quote` (retired) + `Bearer` header → 401
- **New endpoint:** `/ultra/v1/order` + `x-api-key` header → 200 ✅
- **RT calculation:** `2 * priceImpactPct + platform_fee_rt` (from `feeBps`)
- **Startup health check:** `JUP_HEALTH: OK` logged on startup
- **Pool-type-aware fallback:** `cpamm_valid=False` → blocks trade when Jupiter unavailable
- **Actual RT confirmed:** ~0.21% for Fartcoin (CPAMM overestimated at 0.50%)

### 2. Universe Expansion — Fixed (7 tokens → 41 eligible)
- **Lane 1:** Established top-20 large-cap (unchanged)
- **Lane 2 (NEW):** PumpSwap graduated tokens — DexScreener `/search?q=pumpswap` + `/token-profiles/latest/v1`, refreshed every 30 min, age 1h–7d, vol_h24≥$5k, liq_usd≥$2k, top-50 by vol
- **DISCOVERY_RULE version:** v1.1

### 3. Score/Rank Fallback — Active and firing
- Uses ALL eligible tokens (no cpamm_valid_flag filter)
- 30min interval per strategy
- Confirmed firing: momentum_rank (Fartcoin, $WIF), pullback_rank (Pnut, BOME)

### 4. Daily Report v5 — Empirical fee measurement
- Reads `live_trades.meta_fee` (lamports) for median/p90 network cost
- Falls back to smoke_test_log, then hardcoded if no tx data
- Shows fee breakdown: DEX (0.50% RT) + network/prio (measured) + total at 0.01 and 0.02 SOL

---

## Next Session Priorities

### P0 — Check accumulation and run report
```bash
python3 et_daily_report_v5.py
```
Expected: `momentum_rank` hits n_closed≥20 within next 1-2 rank cycles (~30-60 min).

### P1 — If pullback_strict still <5 trades after 24h
Lower r_h1 floor from 2.0% to 1.5% in `et_shadow_trader_v1.py`:
```python
PULLBACK_R_H1_MIN = 1.5  # was 2.0
```

### P2 — Fix universe scanner Jupiter check (minor, non-blocking)
`check_jupiter_available()` in `et_universe_scanner.py` still uses old URL.
Fix: update to `/ultra/v1/order` with `x-api-key` header.

### P3 — Once n_closed ≥ 20 per strategy
1. Run `et_daily_report_v5.py` and check `LIVE_CANARY_READY_V1`
2. Inspect MFE/MAE distribution
3. Check concentration (top-3 tokens < 50%)
4. Check stability (≥2 six-hour blocks with n≥10)

---

## GO/NO-GO Rules (from user)
```
min_closed_trades(strategy) >= 20        → else INSUFFICIENT_DATA
strategy beats matched baseline (fee100) → else NO-GO
stability: >=2 six-hour blocks n>=10     → else INSUFFICIENT_DATA
concentration top-3 < 50%               → else CONCENTRATED
smoke test: PASS ✅                      → already done
```
**LIVE_CANARY_READY_V1 = YES** only when ALL above are met.
No automated live canary with 0.14 SOL bankroll until gate passes.

---

## Quick Diagnostic Commands

```bash
# Check processes
ps aux | grep -E 'shadow_trader|universe|microstructure|supervisor' | grep -v grep

# Check v1 harness log
tail -30 /root/solana_trader/logs/et_shadow_trader_v1.log

# Check universe scanner log
tail -20 /root/solana_trader/logs/et_universe_scanner.log

# Check trade counts
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/solana_trader/data/solana_trader.db')
rows = conn.execute('SELECT strategy, COUNT(*), SUM(CASE WHEN status=\"closed\" THEN 1 ELSE 0 END) FROM shadow_trades_v1 GROUP BY strategy').fetchall()
for r in rows: print(f'{r[0]}: total={r[1]}, closed={r[2]}')
"

# Run daily report
cd /root/solana_trader && python3 et_daily_report_v5.py

# Restart service
systemctl restart solana-trader.service
```

---

## Key Files

| File | Purpose |
|---|---|
| `et_shadow_trader_v1.py` | Main v1 harness — Jupiter ultra, 4 strategy variants |
| `et_universe_scanner.py` | Universe scanner v1.1 — two lanes (large-cap + pumpswap) |
| `et_daily_report_v5.py` | **USE THIS** — empirical fee + all 4 variants + signal freq |
| `et_microstructure_scanner.py` | 15s price/volume scanner |
| `supervisor.py` | Systemd-managed process supervisor |
| `config/config.py` | JUPITER_API_KEY, DB_PATH, TRADE_SIZE_SOL |
| `cpamm_math.py` | CPAMM math helpers |

---

## Wallet
- Live: **0.14 SOL** (DO NOT touch until GO/NO-GO met)
- Paper trade size: 0.01 SOL (virtual)
- Mode: research_mode
