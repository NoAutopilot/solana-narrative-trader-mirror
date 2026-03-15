# Meteora LP State Study — Stage B Data Document

**Program:** meteora_lp_state_stageB  
**Date:** 2026-03-15  
**Experiment:** 014  
**Author:** Manus AI

---

## 1. Data Sources

All data is sourced from two public, unauthenticated APIs:

| Source | Endpoint | Data Type | Coverage |
|--------|----------|-----------|----------|
| Meteora DLMM API | `dlmm-api.meteora.ag/pair/all` | Pool state (TVL, fees_24h, base_fee, max_fee) | Current snapshot only |
| GeckoTerminal API | `api.geckoterminal.com/api/v2/networks/solana/pools/{addr}/ohlcv/hour` | Hourly OHLCV | Up to 500 bars (~21 days) per pool |

---

## 2. Pool Universe Construction

### 2.1 Candidate Pool Selection

The Meteora DLMM API returned 137,901 total pools as of 2026-03-15T00:29Z. The following filters were applied sequentially:

| Filter | Criterion | Pools Remaining |
|--------|-----------|-----------------|
| SOL-quote only | mint_x or mint_y = SOL | ~8,400 |
| Not blacklisted / hidden | is_blacklisted=False, hide=False | ~7,200 |
| Active fee generation | fees_24h > $50 | ~400 |
| Minimum liquidity | liquidity > $5,000 | 138 |
| Top by fees_24h | Ranked, top 120 taken | 120 |
| GeckoTerminal coverage | OHLCV data available | 42 |
| Minimum history | ≥ 48 hourly bars | 38 |

**Final Stage B universe: 38 pools** (vs 15 in Stage A).

### 2.2 Pool Type Breakdown

| Pool Type | Base Fee Criterion | Count |
|-----------|-------------------|-------|
| Standard | base_fee < 1% | 8 |
| Elevated | 1% ≤ base_fee < 2% | 15 |
| Launch | base_fee ≥ 2% | 15 |

### 2.3 Data Depth

| Metric | Value |
|--------|-------|
| Total hourly bars across all pools | ~12,400 |
| Median bars per pool | ~320 (~13 days) |
| Minimum bars per pool | 48 (2 days) |
| Maximum bars per pool | 500 (~21 days) |
| Date range | ~2026-02-22 to 2026-03-15 |

### 2.4 Coverage Improvement vs Stage A

Stage A used 15 pools from the top 60 by fees_24h. Stage B expanded to 42 candidate pools (top 120), of which 38 met the minimum history requirement. This represents a **2.5× increase in pool coverage** and a **2.8× increase in total events** (2,365 vs 844).

---

## 3. PnL Model Components

### 3.1 Fee Accrual Estimate

The fee accrual proxy uses the current-state fee/TVL ratio from the Meteora API:

```
fee_tvl_h1 = fees_24h / (tvl × 24)
fee_4h_pct = fee_tvl_h1 × 4
```

This represents the fraction of TVL earned as fees per 4-hour holding period, based on current-state fee generation rates. This is a **proxy**, not exact LP fee income, because:

- The fee/TVL ratio is current-state, not historical
- Dynamic fee multipliers (which can be 2–10× base fee during high volatility) are not captured
- TVL changes during the holding period are not modeled

### 3.2 Impermanent Loss Estimate

The exact constant-product AMM IL formula is applied:

```
il = |2 × sqrt(1 + r) / (1 + r) - 1 + 1/(1 + r) - 1|
```

where `r` is the price return over the +4h horizon. This is a **proxy** for DLMM concentrated liquidity IL because:

- DLMM IL depends on bin range and whether the price remains in range
- For positions that go out of range, IL can exceed the constant-product estimate
- For positions that stay in range, IL is similar to constant-product

### 3.3 Operational Friction

A flat 0.10% (0.001) friction is applied per deployment, representing entry and exit swap costs plus slippage. This is more conservative than Stage A (0.06%).

### 3.4 Net LP Proxy

```
net_lp_proxy = fee_4h_pct - il_4h - 0.001
```

---

## 4. Event Detection

**Signal:** Toxic flow event = hourly bar where |ret_1h| > 5%

**Forward return:** Price change from close[i] to close[i+4] (4 hours)

**Minimum look-ahead:** Each event requires 4 bars ahead, so the last 4 bars of each pool are excluded from event detection.

| Threshold | Total Events |
|-----------|-------------|
| 3% | 3,887 |
| 5% (primary) | 2,365 |
| 7% | 1,537 |
| 10% | 912 |

---

## 5. Key Difference from Stage A

The most important data difference between Stage A and Stage B is the **Memehouse-SOL pool situation**:

- In Stage A, two Memehouse-SOL pools contributed 35 events with mean net +22–31%, heavily skewing the aggregate result positive.
- In Stage B, the Meteora API no longer lists any Memehouse-SOL pool meeting the activity filters. These pools appear to have been short-lived (1 day of activity) and are no longer active.
- This means the Stage A survivor was substantially driven by a transient pool that no longer exists.

---

*End of Data Document*
