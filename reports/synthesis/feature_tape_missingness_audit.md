# Feature Tape v1 — Missingness Root-Cause Audit
**Track B**
n_rows: 1,756 | n_fires: 42 | as of 2026-03-11T11:00Z

---

## 1. OVERALL MISSINGNESS (per-candidate r_m5 from microstructure_log)

| Status | n_rows | % |
|---|---|---|
| r_m5 present (micro found) | 1,353 | 77.1% |
| r_m5 missing (no micro in 60s window) | 403 | 22.9% |

---

## 2. ROOT CAUSE: POOL TYPE IS THE PRIMARY DRIVER

| Pool Type | Micro Present | Micro Missing | Total | % Present |
|---|---|---|---|---|
| pumpswap | 1,082 | 0 | 1,082 | **100.0%** |
| raydium | 239 | 91 | 330 | 72.4% |
| orca | 32 | 205 | 237 | **13.5%** |
| meteora | 0 | 63 | 63 | **0.0%** |

**Key finding:** The microstructure scanner covers PumpSwap tokens at 100% but covers Orca at only 13.5% and Meteora at 0%. This is not a timing issue — it is a scanner scope issue. The scanner does not poll Orca or Meteora pools for microstructure data.

---

## 3. BY INFERRED LANE

| Lane | Micro Present | Micro Missing | Total | % Present |
|---|---|---|---|---|
| other_pumpswap (mature_pumpswap) | 1,082 | 0 | 1,082 | 100.0% |
| large_cap_ray | 239 | 91 | 330 | 72.4% |
| other_orca | 32 | 205 | 237 | 13.5% |
| other_meteora | 0 | 63 | 63 | 0.0% |

---

## 4. BY AGE AND LIQUIDITY

**Age bucket:** Missingness is NOT driven by age. All age buckets within PumpSwap show 100% coverage. The apparent age/liquidity effect seen in earlier reports was a confound — older/higher-liquidity tokens are more likely to be on Orca/Meteora/Raydium, which have lower scanner coverage.

**Liquidity bucket:**
| Liquidity | Micro Present | Total | % Present |
|---|---|---|---|
| < 10k | 81 | 81 | 100.0% |
| 10k–50k | 616 | 616 | 100.0% |
| 50k–200k | 363 | 363 | 100.0% |
| 200k+ | 328 | 696 | 47.1% |

Tokens with liquidity > 200k have 47.1% coverage. This is because high-liquidity tokens are more likely to be on Raydium/Orca/Meteora (lower scanner coverage), not because the scanner fails on high-liquidity tokens per se.

---

## 5. DO MISSING TOKENS EVER APPEAR IN MICRO LOG?

| Status | Distinct Tokens | Rows |
|---|---|---|
| in_micro_log_at_some_point | 5 | 161 |
| never_in_micro_log | 5 | 198 |

Of the tokens missing micro at fire time:
- ~161 rows belong to tokens that DO appear in the micro log at other times (timing miss — the token was not polled in the 60s window at fire time)
- ~198 rows belong to tokens that NEVER appear in the micro log (scanner scope miss — Orca/Meteora tokens not covered)

---

## 6. BIAS ASSESSMENT

**Is missingness random?** **NO — it is structurally biased by pool type.**

Any analysis using micro-derived features (r_m5, buy_sell_ratio_m5, signed_flow_m5, txn_accel_m5_vs_h1, vol_accel_m5_vs_h1, avg_trade_usd_m5) will:
- Have **complete coverage** for PumpSwap tokens
- Have **partial coverage** (~72%) for Raydium tokens
- Have **near-zero coverage** for Orca and Meteora tokens

This means micro-derived feature analysis will be **biased toward PumpSwap and Raydium tokens** and will systematically exclude Orca/Meteora tokens from any micro-based signal evaluation.

---

## 7. RECOMMENDATION

**For the planned new-family sweep:**
- Micro-derived features (order-flow, urgency) can be evaluated on PumpSwap + Raydium subsets only
- Orca and Meteora tokens must be excluded from micro-feature analysis or treated as a separate stratum
- Quote/route features (jup_vs_cpamm_diff_pct, round_trip_pct, impact_buy_pct) are available for ALL pool types and are not affected by this bias

**For scanner improvement (future, not now):**
- Extending the microstructure scanner to cover Orca and Meteora pools would eliminate this bias
- This is a data acquisition task, not a model task
