# Large-Cap Swing Study — Stage A Data Scaffold

**Date:** 2026-03-13
**Author:** Manus AI
**Status:** DATA PLUMBING ONLY — no backtest, no strategy logic, no live observer

---

## Purpose

This document specifies the data infrastructure required for a future dynamic-universe large-cap swing event study on Solana DEX tokens. The scaffold provides three components: a point-in-time universe constructor, a historical OHLCV fetch pipeline, and a data quality assurance layer with survivorship-bias guardrails. No analysis or strategy logic is included.

---

## 1. Point-in-Time Universe Constructor

### 1.1 Design Principle

The universe must be constructed using **only information available at each decision point**. A token's membership in the "large-cap" subset at time T is determined exclusively by data observable at or before T. No future information — including whether the token survived, gained liquidity, or was delisted — may influence membership at T.

### 1.2 Data Sources

The universe constructor draws from two existing tables in the VPS SQLite database:

| Source Table | Role | Available Fields |
|-------------|------|-----------------|
| `universe_snapshot` | Point-in-time scanner output at each 15m fire | `mint`, `snapshot_at`, `price_usd`, `liq_usd`, `vol_h24`, `fdv`, `market_cap`, `eligible`, `gate_reason`, `pool_type`, `age_hours` |
| `feature_tape_v2` | Enriched candidate rows with derived features | `candidate_mint`, `fire_time_utc`, `eligible`, `lane`, `liq_usd`, `vol_h24`, `age_hours`, `pool_type` |

No external API call is needed for universe construction. The scanner already captures point-in-time market cap, liquidity, and volume at each fire.

### 1.3 Membership Logic

A token qualifies for the large-cap swing universe at fire F if **all** of the following conditions hold at fire time:

| Gate | Field | Condition | Rationale |
|------|-------|-----------|-----------|
| G1 — Eligibility | `eligible` | `= 1` | Must pass all scanner gates (spam, impact, age, volume, liquidity) |
| G2 — Liquidity floor | `liq_usd` | `>= P75 of fire-level eligible universe` | Top-quartile liquidity ensures executable size |
| G3 — Volume floor | `vol_h24` | `> 0 AND >= P50 of fire-level eligible universe` | Active trading confirms real market |
| G4 — Age floor | `age_hours` | `>= 24` | Survived at least one full day; filters launch-day pump-and-dumps |
| G5 — Market cap floor | `fdv` or `market_cap` | `>= P50 of fire-level eligible universe` | Relative large-cap within the Solana micro-cap universe |

**Critical:** All percentile thresholds (P50, P75) are computed **within each fire's eligible universe**, not across the full dataset. This prevents look-ahead bias from using the global distribution.

### 1.4 Dynamic Membership

Membership is **not sticky**. A token that qualifies at fire F may not qualify at fire F+1 if its liquidity drops or a new token pushes it below the percentile threshold. This is by design — it models a realistic portfolio rebalancing scenario where the universe is refreshed every 15 minutes.

### 1.5 Expected Universe Size

Based on feature_tape_v2 fire 1 (38 total candidates, 36 eligible), applying G2-G5 would yield approximately 5-10 candidates per fire. Over 96 fires, this produces approximately 480-960 unique fire-token pairs. Over 384 fires (4-day collection), approximately 1,920-3,840 pairs — sufficient for a Stage A feasibility study.

---

## 2. Historical OHLCV Fetch Plan

### 2.1 Why OHLCV Is Needed

The existing `universe_snapshot` table captures a single price point per token per 15-minute fire. For swing analysis at +1h / +4h / +1d horizons, we need:

- **Intra-period price path** (not just endpoint return) to compute drawdown, volatility, and mean-reversion features
- **Volume profile** within the forward window to distinguish sustained moves from flash spikes
- **OHLCV candles** at 5m or 15m granularity within the forward window

### 2.2 Data Source Options

| Source | Endpoint | Granularity | Rate Limit | Auth | Cost |
|--------|----------|-------------|------------|------|------|
| **DexScreener** (existing) | `/dex/pairs/{chainId}/{pairAddress}` | Current only; no historical candles | 300/min | None | Free |
| **Birdeye** | `/defi/ohlcv/pair` or `/defi/ohlcv` | 1m, 5m, 15m, 1h, 1d | 100/min (free), 1000/min (paid) | API key | Free tier available; $49/mo starter |
| **Jupiter Price API** | `/v6/price` | Current only; no candles | Generous | None | Free |
| **Helius DAS** (existing) | RPC-based | No OHLCV; token metadata only | Per-plan | API key | Already provisioned |
| **GeckoTerminal** | `/api/v2/networks/solana/pools/{address}/ohlcv` | 1m, 5m, 15m, 1h, 4h, 1d | 30/min | None | Free |

### 2.3 Recommended Fetch Strategy

**Primary:** GeckoTerminal (free, no auth, 15m candles available, pool-address-based).

**Fallback:** Birdeye (if GeckoTerminal rate limits are too restrictive for bulk fetch).

**Fetch plan:**

1. For each fire-token pair in the large-cap universe, record the `pool_address` (already in `universe_snapshot`)
2. After the forward window matures (e.g., +4h after fire), fetch OHLCV candles from fire_time to fire_time + 4h
3. Store candles in a new `ohlcv_candles` table (see schema below)
4. Compute derived labels (forward return, max drawdown, intra-period volatility) from the candle data

**Fetch timing:** OHLCV fetch is a **cold-path batch job** run after collection completes and labels mature. It is NOT a real-time feed. This avoids rate-limit pressure and ensures all data is available before fetch.

### 2.4 OHLCV Storage Schema

```sql
CREATE TABLE IF NOT EXISTS ohlcv_candles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_session   TEXT NOT NULL,          -- batch session ID
    mint            TEXT NOT NULL,
    pool_address    TEXT NOT NULL,
    candle_start    TEXT NOT NULL,          -- ISO 8601 UTC
    candle_end      TEXT NOT NULL,
    interval_s      INTEGER NOT NULL,       -- 300 for 5m, 900 for 15m
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume_usd      REAL,
    source          TEXT NOT NULL,          -- 'geckoterminal' or 'birdeye'
    fetched_at      TEXT NOT NULL,
    UNIQUE(mint, pool_address, candle_start, interval_s)
);
```

### 2.5 Rate-Limit Budget

| Source | Rate | Tokens/fire | Fires | Candles/token/horizon | Total requests | Time at limit |
|--------|------|-------------|-------|----------------------|----------------|---------------|
| GeckoTerminal | 30/min | 10 | 96 | 1 (paginated) | ~960 | ~32 min |
| GeckoTerminal | 30/min | 10 | 384 | 1 (paginated) | ~3,840 | ~128 min |
| Birdeye (free) | 100/min | 10 | 384 | 1 | ~3,840 | ~38 min |

All budgets are feasible for a batch job. No real-time pressure.

---

## 3. Point-in-Time Market-Cap / Volume Membership Logic

### 3.1 Percentile Computation

At each fire F, the membership percentiles are computed from the **eligible universe at that fire only**:

```python
# Pseudocode — executed per fire
eligible_rows = [r for r in fire_rows if r.eligible == 1]
liq_p75 = np.percentile([r.liq_usd for r in eligible_rows], 75)
vol_p50 = np.percentile([r.vol_h24 for r in eligible_rows if r.vol_h24 > 0], 50)
fdv_p50 = np.percentile([r.fdv for r in eligible_rows if r.fdv > 0], 50)

largecap_universe = [
    r for r in eligible_rows
    if r.liq_usd >= liq_p75
    and r.vol_h24 >= vol_p50
    and r.age_hours >= 24
    and (r.fdv >= fdv_p50 or r.market_cap >= fdv_p50)
]
```

### 3.2 Membership Columns

The universe builder adds the following columns to each row:

| Column | Type | Description |
|--------|------|-------------|
| `largecap_eligible` | INTEGER | 1 if passes all G1-G5 gates at this fire; 0 otherwise |
| `liq_pctile_fire` | REAL | Percentile rank of this token's `liq_usd` within fire-level eligible universe |
| `vol_pctile_fire` | REAL | Percentile rank of this token's `vol_h24` within fire-level eligible universe |
| `fdv_pctile_fire` | REAL | Percentile rank of this token's `fdv` within fire-level eligible universe |
| `fire_eligible_count` | INTEGER | Total eligible tokens at this fire (denominator for percentiles) |
| `fire_largecap_count` | INTEGER | Tokens passing G1-G5 at this fire |

### 3.3 No Sticky Membership

A token's `largecap_eligible` status is recomputed at every fire. There is no "once in, always in" rule. This prevents survivorship bias where tokens that later fail are retroactively excluded from the universe.

---

## 4. Data QA / Survivorship-Bias Guardrails

### 4.1 Guardrail Taxonomy

| ID | Guardrail | Check | Severity |
|----|-----------|-------|----------|
| QA1 | No future data in membership | Verify all membership gates use only fire-time-or-earlier data | CRITICAL |
| QA2 | No sticky membership | Verify token can enter and exit large-cap universe across fires | CRITICAL |
| QA3 | Percentiles are fire-local | Verify percentile thresholds differ across fires | HIGH |
| QA4 | OHLCV fetch timing | Verify all candles are fetched AFTER the forward window closes | HIGH |
| QA5 | Missing data flagging | Flag tokens with missing OHLCV candles in the forward window | MEDIUM |
| QA6 | Delisted token handling | Tokens that disappear from scanner must NOT be retroactively removed from past fires | CRITICAL |
| QA7 | Price continuity | Flag tokens with >50% price gaps between consecutive candles | MEDIUM |
| QA8 | Volume consistency | Flag tokens where OHLCV volume diverges >3x from snapshot vol_h24 | LOW |
| QA9 | Universe size stability | Flag fires where large-cap universe has <3 or >20 tokens | MEDIUM |
| QA10 | Duplicate detection | Verify no duplicate fire-token pairs in the universe | HIGH |

### 4.2 Survivorship Bias — Specific Risks

**Risk 1: Conditioning on future survival.** If the universe is constructed using tokens that "survived" to the end of the study period, tokens that crashed and disappeared are excluded. The point-in-time constructor prevents this by using only fire-time data.

**Risk 2: Backfill bias.** If OHLCV data is fetched from an API that backfills or adjusts historical candles, the data may not reflect what was observable in real time. Mitigation: fetch from DexScreener/GeckoTerminal which report raw on-chain data without adjustment.

**Risk 3: Selection on the dependent variable.** If the large-cap filter uses `vol_h24` and the study measures forward volume-weighted returns, the filter and the label are correlated. Mitigation: the study must test features that are **not** the membership criteria themselves.

**Risk 4: Percentile leakage.** If percentiles are computed across the full dataset rather than per-fire, future fires influence past membership. The fire-local percentile computation prevents this.

### 4.3 QA Script Outputs

The `stageA_data_qc.py` script produces:

| Output | Path | Description |
|--------|------|-------------|
| QA summary | `reports/parallel_sprint/largecap_swing/stageA_qa_summary.md` | Pass/fail for each guardrail |
| Membership audit | `reports/parallel_sprint/largecap_swing/stageA_membership_audit.csv` | Per-fire universe size, entry/exit counts |
| OHLCV coverage | `reports/parallel_sprint/largecap_swing/stageA_ohlcv_coverage.csv` | Per-token candle completeness |
| Anomaly log | `reports/parallel_sprint/largecap_swing/stageA_anomalies.csv` | Flagged rows with QA violations |

---

## 5. Script Inventory

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/dynamic_universe_builder.py` | Construct point-in-time large-cap universe from feature_tape_v2 | STUB |
| `scripts/ohlcv_loader.py` | Batch-fetch OHLCV candles from GeckoTerminal/Birdeye | STUB |
| `scripts/stageA_data_qc.py` | Run all QA guardrails and produce audit reports | STUB |

All scripts are stubs. They define interfaces, schemas, and logic flow but do **not** execute against live data or APIs.

---

## 6. Execution Prerequisites

Before running the data scaffold against real data, the following must be true:

1. `feature_tape_v2` collection has completed (>= 96 fires, ideally 384)
2. All primary labels (+5m through +4h) have matured
3. Dataset has been frozen via `ops/feature_tape_v2_freeze_dataset.sh`
4. GeckoTerminal or Birdeye API access has been verified (a single test fetch)
5. The holdout pipeline for the primary feature study has completed (the swing study is a **fallback**, not a parallel track)

---

## 7. Non-Goals

This scaffold explicitly does **not** include:

- Backtest logic or return computation
- Strategy parameters or trading rules
- Live observer design
- Position sizing or risk management
- Any modification to the running collector or scanner
