# Meteora LP State Study — Stage B Design Document

**Program:** meteora_lp_state_stageB  
**Date:** 2026-03-15  
**Experiment:** 014  
**Author:** Manus AI  
**Purpose:** Falsification / verification of the Stage A H2 toxic-flow-filter +4h survivor.

---

## 1. Survivor Being Tested

Stage A produced exactly one combination that passed all six gates:

> **H2 Toxic Flow Filter at +4h**  
> Definition: \|1h price return\| > 5% (toxic flow event)  
> Metric: LP PnL proxy at +4h horizon  
> Stage A result: N=844, wins_mean=+1.033%, median=+0.080%, CI=[+0.580%, +2.909%]

Stage B tests only this survivor. No new hypotheses are introduced.

---

## 2. Improved PnL Model

### 2.1 Stage A Limitations

The Stage A LP proxy had four known weaknesses:

| Weakness | Impact |
|----------|--------|
| Fee proxy used base fee only | Underestimates fee income in volatile periods (dynamic fee can be 2–10× base) |
| IL proxy used constant-product AMM formula | May over- or under-estimate DLMM concentrated liquidity IL |
| TVL was current-state, not historical | TVL at event time is unknown; current TVL may differ materially |
| +15m was interpolated from +1h | Not directly observable; Stage B drops +15m |

### 2.2 Stage B PnL Model Components

Stage B uses an upgraded three-component model. All components are explicitly labeled by approximation level.

**Component 1: Fee Accrual Estimate**

| Item | Detail |
|------|--------|
| Formula | `fee_est = fee_tvl_h1 × n_bars × tvl_usd` where `fee_tvl_h1` is the current-state fee/TVL ratio per hour from the Meteora API |
| Source | Meteora DLMM API `pair/all` endpoint |
| Approximation level | **Proxy** — fee/TVL ratio is current-state, not historical. For pools with stable TVL and volume, this is a reasonable estimate. For pools with rapidly changing TVL, it may be off by 2–5×. |
| Improvement over Stage A | Uses fee/TVL ratio (which incorporates actual volume) rather than base_fee × estimated_volume. More accurate for high-volume pools. |
| Known blind spots | Dynamic fee multiplier not captured. TVL changes during holding period not captured. |

**Component 2: Adverse Selection / IL Estimate**

| Item | Detail |
|------|--------|
| Formula | `il_est = 2 × (sqrt(1 + r) - 1)² / (1 + r)` where r = price return over horizon. This is the exact constant-product AMM IL formula, not the second-order approximation. |
| Source | Standard AMM IL formula, applied as conservative proxy for DLMM |
| Approximation level | **Proxy** — DLMM concentrated liquidity IL depends on bin range and whether the price stays in range. For a position that goes out of range, IL can be higher. For a position that stays in range, IL is similar to constant-product. |
| Improvement over Stage A | Exact IL formula (not second-order approximation). Capped at 100% (not 50%). |
| Known blind spots | Bin range assumption. Out-of-range behavior. |

**Component 3: Operational Friction**

| Item | Detail |
|------|--------|
| Formula | `friction = 0.10%` per deployment (entry + exit) |
| Source | Conservative estimate based on Meteora DLMM typical swap fees (0.04–0.25%) plus slippage |
| Approximation level | **Estimate** — actual friction depends on pool liquidity depth and position size |
| Improvement over Stage A | Increased from 0.06% to 0.10% (more conservative) |

**Net LP Proxy:**
```
net_lp_proxy = fee_est - il_est - 0.001
```

### 2.3 Approximation Level Summary

This model is a **proxy**, not exact LP PnL. Exact LP PnL requires position-level on-chain data (Helius/Bitquery paid API). The proxy is an improvement over Stage A in fee estimation and IL formula precision, but remains subject to TVL uncertainty and bin-range assumptions.

---

## 3. Pool Universe

**Stage A:** 15 pools (from top 60 by fees_24h, GeckoTerminal coverage)  
**Stage B:** 42 pools (from top 120 by fees_24h, GeckoTerminal coverage)

Pool type breakdown (Stage B):

| Type | Definition | Count |
|------|-----------|-------|
| Standard | base_fee < 1% | ~12 |
| Elevated | 1% ≤ base_fee < 2% | ~15 |
| Launch | base_fee ≥ 2% | ~15 |

Minimum history requirement: ≥ 48 bars (2 days) per pool to be included in analysis.

---

## 4. Toxic Flow Filter Definition

**Primary definition (Stage A survivor):** \|ret_1h\| > 5%

**Sensitivity band (Task 4E):** Test at 3%, 5%, 7%, 10% thresholds. If the result only survives at one narrow threshold, verdict = NO-GO.

---

## 5. Pass/Fail Gates

All six Stage A gates apply. Stage B adds two additional gates:

| Gate | Criterion | Rationale |
|------|-----------|-----------|
| G1 | N ≥ 50 (raised from 30) | Stricter sample requirement |
| G2 | Winsorized mean > 0 | Positive expected value |
| G3 | Median > 0 | Majority of events profitable |
| G4 | CI lower bound > 0 | Statistical confidence |
| G5 | Top-1 share < 25% | No single event dominance |
| G6 | Top-3 share < 50% | No small cluster dominance |
| **G7** | **Survives top-5% tail removal** | **Robustness to extreme events** |
| **G8** | **Survives Memehouse-SOL exclusion** | **Not driven by one anomalous pool** |

---

## 6. Kill Criteria

Stage B verdict = **NO-GO** if any of the following:

1. Core result (H2 toxic +4h) fails any gate G1–G8
2. Signal only survives at one threshold (e.g., only at 5%, not at 3% or 7%)
3. Signal driven by ≤ 2 pools (pool-level dispersion fails)
4. Winsorized mean or median turns negative after tail removal
5. CI lower bound ≤ 0 after tail removal or pool exclusion

Stage B verdict = **GO** only if all gates pass and signal survives all robustness tests.

---

## 7. Operational Reality Check (Task 5)

If the signal survives, the following questions must be answered before any Stage C design:

1. Can toxic flow state be identified in real time (latency requirement)?
2. What capital size assumptions are embedded in the proxy?
3. What operational frictions remain unmodeled?
4. What would Stage C need to prove?

---

*End of Design Document*
