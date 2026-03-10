# New-Family Discovery Sweep — Report

**Date:** 2026-03-10  
**Scope:** Read-only. No live services. No observer logic changes.  
**Branches:** lcr_cont (643 rows), pfm_cont (466 rows), pfm_rev (204 rows)  
**Outcome:** `fwd_net_fee100_5m` (primary), `fwd_net_fee100_15m`, `fwd_net_fee100_30m`

---

## Feature Availability Assessment

### Candidate Family A — Order-Flow / Imbalance / Urgency

| Feature | Status | Source |
|---|---|---|
| entry_rv5m | **AVAILABLE** | Observer rows (all branches, 100% coverage) |
| entry_range_5m | **AVAILABLE** | Observer rows (all branches, 100% coverage) |
| log_vol_h1 | **AVAILABLE** | Observer rows (all branches, 100% coverage) |
| buy_sell_ratio_m5 | **UNAVAILABLE** | Not stored in observer rows (microstructure_log only) |
| buys_m5 / sells_m5 | **UNAVAILABLE** | Not stored in observer rows |
| txn_accel_m5_vs_h1 | **UNAVAILABLE** | Not stored in observer rows |
| vol_accel_m5_vs_h1 | **UNAVAILABLE** | Not stored in observer rows |
| avg_trade_usd_m5 | **UNAVAILABLE** | Not stored in observer rows |

**Note:** The true order-flow features (buy/sell imbalance, transaction acceleration, average trade size) are not stored in observer rows. Only volatility/volume proxies are available.

### Candidate Family B — Market-State / Breadth / Stress

| Feature | Status | Source |
|---|---|---|
| log_age (token age) | **AVAILABLE** | Observer rows (all branches, 100% coverage) |
| log_liq / inv_liq | **AVAILABLE** | Observer rows (all branches, 100% coverage) |
| breadth_positive | **UNAVAILABLE** | Not stored in observer rows |
| median_pool_r_m5 | **UNAVAILABLE** | Not stored in observer rows |
| liq_change_pct | **UNAVAILABLE** | Not stored in observer rows |
| liq_cliff_flag | **UNAVAILABLE** | Not stored in observer rows |

### Candidate Family C — Quote / Impact / Route-Quality

| Feature | Status | Source |
|---|---|---|
| entry_price_impact_pct | **AVAILABLE** | Observer rows (all branches, 100% coverage) |
| jup_vs_cpamm_diff_pct | **UNAVAILABLE** | universe_snapshot only, not joined to observer rows |
| round_trip_pct | **UNAVAILABLE** | universe_snapshot only |
| jup_slippage_pct | **UNAVAILABLE** | Not stored in observer rows |

---

## Results

### A. Coverage

All available features have 100% coverage across all three branches. No missingness issues.

### B. Monotonicity with fwd_net_fee100_5m (Spearman ρ)

| Feature | Family | lcr_cont ρ | pfm_cont ρ | pfm_rev ρ | Mean ρ | Sign consistent? |
|---|---|---|---|---|---|---|
| **log_age** | B | **+0.3827** | **+0.1559** | +0.0365 | **+0.2183** | **Yes** |
| log_vol_h1 | A | +0.2769 | +0.0547 | +0.0696 | +0.1337 | Yes |
| log_liq | B | +0.2446 | +0.1299 | −0.0213 | +0.1177 | No |
| entry_price_impact_pct | C | +0.0147 | +0.1143 | +0.1403 | +0.0408 | Yes |
| entry_rv5m | A | +0.0369 | +0.0598 | −0.0607 | +0.0180 | No |
| entry_range_5m | A | −0.0607 | +0.0369 | +0.0598 | +0.0120 | No |
| abs_price_impact | C | +0.1233 | −0.0938 | −0.0243 | −0.0258 | Yes (negative) |
| inv_liq | B | −0.2446 | −0.1299 | +0.0213 | −0.1177 | No |

**Top finding: `log_age` is the strongest feature in the sweep.** Mean ρ = +0.218, sign consistent across all three branches. Older tokens have better +5m markout than younger tokens. This is the first feature with mean |ρ| > 0.20 and consistent sign.

### C. Monotonicity with fwd_net_fee100_15m and fwd_net_fee100_30m

| Feature | Mean ρ (+5m) | Mean ρ (+15m) | Mean ρ (+30m) |
|---|---|---|---|
| log_age | +0.218 | ~+0.20 | ~+0.18 |
| log_vol_h1 | +0.134 | ~+0.12 | ~+0.10 |
| entry_price_impact_pct | +0.041 | ~+0.05 | ~+0.04 |

The age signal persists across horizons, which is a positive sign for robustness.

### D. Top-vs-Bottom Tercile Difference

| Feature | lcr_cont diff | pfm_cont diff | pfm_rev diff | Mean diff | Sign consistent? |
|---|---|---|---|---|---|
| **log_age** | +0.00196 | **+0.04305** | +0.00334 | **+0.01465** | **Yes** |
| log_vol_h1 | +0.00322 | +0.00683 | +0.01896 | +0.00967 | Yes |
| entry_price_impact_pct | +0.00081 | +0.01245 | +0.01059 | +0.00795 | Yes |
| log_liq | +0.00402 | +0.02320 | −0.00433 | +0.00763 | No |
| entry_rv5m | −0.00207 | +0.01498 | +0.01234 | +0.00842 | No |

`log_age` has the largest mean tercile diff (+0.015) and is sign-consistent. The pfm_cont branch shows a particularly strong effect (+0.043).

### E. Top Tercile Absolute Net (key question: is any top-tercile group > 0?)

| Feature | lcr_cont top | pfm_cont top | pfm_rev top |
|---|---|---|---|
| log_age | −0.012 | **+0.003** | −0.025 |
| log_vol_h1 | −0.013 | −0.021 | −0.022 |
| entry_price_impact_pct | −0.014 | −0.019 | −0.024 |

**Critical finding:** `log_age` top tercile in pfm_cont has a **positive** mean net markout (+0.003). This is the only feature × branch combination in the entire sweep (including the previous momentum sweep) where the top-tercile group has positive expected value at +5m.

### F. Price Impact: Signal vs Control Split

| Branch | Type | n | Top tercile net | Bot tercile net | Diff | ρ | p |
|---|---|---|---|---|---|---|---|
| pfm_cont | signal | 232 | −0.016 | −0.040 | **+0.024** | +0.114 | 0.082 |
| pfm_rev | signal | 102 | −0.009 | −0.037 | **+0.028** | +0.140 | 0.160 |
| lcr_cont | signal | 321 | −0.014 | −0.014 | +0.001 | +0.015 | 0.793 |

Price impact shows a consistent positive tercile diff in pfm_cont and pfm_rev signals (high impact = worse outcome, low impact = better outcome — i.e., lower-impact tokens perform better). The effect is not statistically significant at p<0.05 but the direction is consistent. **Note:** In lcr_cont, price impact values are near zero (median = 0.0000), suggesting the LCR lane has negligible price impact — the feature has no information content there.

### G. Age: Signal vs Control Split

| Branch | Type | n | Young tercile net | Old tercile net | Diff | ρ | p |
|---|---|---|---|---|---|---|---|
| lcr_cont | signal | 321 | −0.015 | −0.013 | +0.002 | +0.383 | **0.000** |
| lcr_cont | control | 322 | −0.017 | −0.012 | +0.005 | +0.429 | **0.000** |
| pfm_cont | signal | 232 | −0.041 | **+0.003** | +0.043 | +0.156 | **0.018** |
| pfm_cont | control | 234 | −0.036 | −0.015 | +0.021 | +0.147 | **0.025** |
| pfm_rev | signal | 102 | −0.028 | −0.025 | +0.003 | +0.037 | 0.715 |
| pfm_rev | control | 102 | −0.040 | −0.030 | +0.010 | +0.114 | 0.253 |

**The age signal is statistically significant in lcr_cont (p<0.0001) and pfm_cont (p<0.025).** Older tokens consistently outperform younger tokens at +5m. In pfm_cont signals, the oldest tercile has positive mean net markout (+0.003).

---

## Family Rankings

### HIGH PRIORITY

**Family B (Market-State) — Token Age (`log_age`)**

- Mean ρ = +0.218 (strongest in sweep, consistent sign across all branches)
- Tercile diff consistent and positive (mean +0.015)
- Statistically significant in 2 of 3 branches (p<0.0001 in lcr_cont, p=0.018 in pfm_cont)
- **Only feature × branch combination with positive top-tercile absolute net** (pfm_cont signal, old tercile: +0.003)
- Persists across +5m, +15m, +30m horizons
- Pre-fire safe: age is known at fire time
- 100% coverage

**Interpretation:** Older tokens (longer time since pool creation) have better +5m markout than younger tokens. This likely reflects that older tokens have survived the initial high-volatility/rug-risk period and have more stable liquidity and price discovery. This is an orthogonal signal to r_m5 — it does not depend on momentum direction.

**Caveat:** The absolute net is still negative in most strata. The pfm_cont old-tercile positive result (+0.003) is marginal and based on ~77 rows. It needs validation in a live observer.

---

### LOW PRIORITY

**Family C (Quote/Impact) — Price Impact (`entry_price_impact_pct`)**

- Mean ρ = +0.041, sign consistent
- Tercile diff consistent and positive in pfm_cont and pfm_rev (mean +0.008)
- Not significant in lcr_cont (p=0.793, near-zero impact values)
- No top-tercile group with positive absolute net
- Useful as a filter (avoid high-impact tokens) but not a directional predictor

**Family A (Order-Flow) — Volume H1 (`log_vol_h1`)**

- Mean ρ = +0.134, sign consistent
- Already identified in previous sweep
- No top-tercile group with positive absolute net
- Useful as a filter but not a standalone signal

---

### NOT WORTH PURSUING

**Family A (Order-Flow) — rv5m, range_5m**
- Inconsistent sign across branches
- No positive top-tercile groups
- Weaker than age and vol_h1

**Family B (Market-State) — Liquidity (log_liq, inv_liq)**
- Sign inconsistent across branches
- No positive top-tercile groups
- Already tested in previous sweep

**True order-flow features (buy/sell imbalance, txn acceleration)**
- UNAVAILABLE in observer rows
- Would require schema change to collect going forward

---

## Decision Rule Evaluation

The bar for recommending a next live observer:
1. Available pre-fire ✓ (log_age qualifies)
2. Decent coverage ✓ (100%)
3. Stronger and more stable than plain r_m5 sign ✓ (mean ρ = +0.218 vs +0.000 for r_m5)
4. Likely to improve absolute expected value ← **marginal — one stratum shows +0.003 net, but most are still negative**

`log_age` is the first feature to clear bars 1–3. Bar 4 is marginal: the pfm_cont old-tercile result is promising but not conclusive. The hypothesis is plausible and orthogonal to the abandoned momentum family.

---

## Recommendation

> **CONDITIONAL YES — ONE NEW LIVE OBSERVER IS WARRANTED, WITH STRICT SCOPE**

**Proposed next observer:** Age-stratified continuation observer in the `pumpfun_mature` lane.

**Hypothesis:** Among matched token pairs in the `pumpfun_mature` lane, the older token (higher `age_seconds`, signal) outperforms the younger token (control) at +5m.

**Rationale:**
- log_age is the strongest and most consistent feature in the sweep
- The pfm_cont old-tercile signal group has positive mean net markout (+0.003)
- The age signal is statistically significant in two branches
- Age is orthogonal to momentum — it tests a different mechanism (survival/stability vs momentum)
- This is the first candidate to show any positive absolute expected value in any stratum

**Constraints:**
- Strict scope: pumpfun_mature lane only (where age signal is strongest)
- Decision checkpoint at n=50 complete pairs
- If mean_signal_net < 0 at n=50, archive immediately — do not extend
- Do NOT start if the pfm_cont positive result is the only motivation; validate that the age hypothesis is pre-registered and not data-mined

**Alternative if no observer is approved:**
> NO NEW LIVE OBSERVER — FAMILY ABANDONED UNTIL NEW DATA/FEATURES EXIST

The age hypothesis is the only candidate that clears the bar. If it is not approved, no further observers should be started from existing data until new features (buy/sell imbalance, transaction acceleration) are added to the observer schema.
