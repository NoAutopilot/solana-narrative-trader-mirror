# Dataset Index v1

**Generated:** 2026-03-12  
**Status:** ACTIVE — updated when new datasets are created or archived  
**Purpose:** Canonical map of all reusable research datasets. Answers "what do we already have?" before any new collection is proposed.

---

## Overview

All datasets reside on the VPS at `/root/solana_trader/data/solana_trader.db` unless otherwise noted. The database uses WAL mode with 15-minute backup cadence (compressed, zstd). Off-box backup is configured but pending credentials.

---

## Dataset 1 — feature_tape_v1

| Field | Value |
|-------|-------|
| **Table** | `feature_tape_v1` |
| **DB path** | `/root/solana_trader/data/solana_trader.db` |
| **Row count** | 4,081 |
| **Fires** | 100 (96 collected + 4 from post-completion fires) |
| **Date range** | 2026-03-11T00:45Z → 2026-03-12T05:15Z |
| **Coverage** | 97.7% labeled (38 rows excluded: disk-gap fires 11:15–15:45 UTC on 2026-03-11) |
| **Provenance manifest** | `reports/synthesis/feature_tape_v1_run_manifest.json` |

**Schema summary (39 columns):** Identity (fire_id, fire_time_utc, fire_time_epoch, candidate_mint, candidate_symbol), timing (snapshot_at_used, micro_ts_used), classification (lane, venue, pool_type, pumpfun_origin), fundamentals (age_hours, liquidity_usd, vol_h1), microstructure (rv5m, r_m5, range_5m, buy_sell_ratio_m5, signed_flow_m5, txn_accel_m5_vs_h1, vol_accel_m5_vs_h1, avg_trade_usd_m5), quote/route (jup_vs_cpamm_diff_pct, round_trip_pct, impact_buy_pct, impact_sell_pct), liquidity (liq_change_pct), pool stats (breadth_positive_pct, median_pool_r_m5, pool_dispersion_r_m5, pool_size_total, pool_size_with_micro), source flags.

**Missingness caveats:** Microstructure features (r_m5, buy_sell_ratio_m5, etc.) are missing for ~21–29% of rows due to Orca and Meteora pools having no microstructure_log coverage. This missingness is non-random (venue-correlated) and must be flagged in any analysis using Track B features.

**Label definitions:** See Dataset 2 (feature_tape_v1_labels).

**Valid uses:** Feature family sweeps, retrospective analysis of pre-fire features vs. short-horizon outcomes, coverage audits, missingness analysis.

**Invalid uses:** Do not use for live signal generation. Do not use Track B features as if they represent the full universe. Do not use the 38 disk-gap rows for any labeled analysis.

---

## Dataset 2 — feature_tape_v1_labels

| Field | Value |
|-------|-------|
| **Table** | `feature_tape_v1_labels` |
| **DB path** | `/root/solana_trader/data/solana_trader.db` |
| **Row count** | 4,081 |
| **Label coverage** | 100% rows have a label record; 97.7% have a non-missing label |
| **Horizons** | +5m, +15m, +30m |
| **Label source** | `universe_snapshot.price_usd` (primary); `microstructure_log.price_usd` (fallback, not used in practice) |

**Label formula:**

> `gross_return_Xm = (price_at_fire_plus_Xm / price_at_fire) - 1`  
> `net_proxy_Xm = gross_return_Xm - round_trip_pct`  
> Entry price: latest universe_snapshot row with ts ≤ fire_time_epoch (within 60s lookback)  
> Forward price: closest universe_snapshot row to fire_time_epoch + offset, strictly after fire, within ±tolerance (90s for +5m, 120s for +15m, 180s for +30m)

**Missingness caveats:** 38 rows have `label_quality = missing_disk_gap` (fires during the 11:15–15:45 UTC disk-full event on 2026-03-11). These must be excluded from all primary denominators. An additional ~2.2% of rows have `label_quality = missing` due to mints that dropped out of scanner scope between fire and T+Xm.

**Valid uses:** Feature sweep analysis, horizon comparison, robustness checks.

**Invalid uses:** Do not use net_proxy as a true net return — it excludes fees, gas, and actual slippage. Do not use missing_disk_gap rows in any analysis.

---

## Dataset 3 — universe_snapshot (Live, Growing)

| Field | Value |
|-------|-------|
| **Table** | `universe_snapshot` |
| **DB path** | `/root/solana_trader/data/solana_trader.db` |
| **Row count** | ~166,462 (as of 2026-03-12T06:35Z, growing at ~1 row/min/mint) |
| **Date range** | 2026-03-09T17:00Z → present |
| **Cadence** | 1 row per minute per eligible mint |
| **Coverage** | 100% price_usd populated; quote/route fields populated for ~95% of rows |

**Schema summary (42 columns):** snapshot_at, mint_address, token_symbol, pair_address, venue, pool_type, eligible, gate_reason, liq_usd, liq_quote_sol, liq_base, k_invariant, vol_h24, vol_h1, vol_m5, price_usd, price_native, buys_m5, sells_m5, buy_count_ratio_m5, avg_trade_usd_m5, spam_flag, impact_buy_pct, impact_sell_pct, round_trip_pct, jup_quote fields, pair_created_at, age_hours, received_at, price_from_reserves, price_vs_dex_pct_diff, cpamm_valid_flag, pumpfun_origin, lane, r_m5, r_h1, r_h6, r_h24.

**Valid uses:** Forward price lookup for label derivation, snapshot-based feature extraction, liquidity and volume analysis, pool-level aggregate computation.

**Invalid uses:** Do not use r_m5 from universe_snapshot as a forward label (it is a rolling window, not a point-in-time return). Do not use for intra-minute analysis.

---

## Dataset 4 — microstructure_log (Live, Growing)

| Field | Value |
|-------|-------|
| **Table** | `microstructure_log` |
| **DB path** | `/root/solana_trader/data/solana_trader.db` |
| **Row count** | ~505,907 (as of 2026-03-12T06:35Z, growing at ~15s cadence per tracked mint) |
| **Cadence** | ~1 row per 15 seconds per tracked mint |
| **Coverage** | Raydium and PumpSwap pools only; Orca and Meteora have no coverage |

**Missingness caveat:** Orca (~14% of eligible universe) and Meteora (~0%) have no microstructure_log rows. This is a scanner scope gap, not a data quality issue. Any analysis using microstructure_log features must explicitly note this non-random missingness.

**Valid uses:** Order-flow feature extraction (buys_m5, sells_m5, buy_sell_ratio, avg_trade_usd, vol_accel, txn_accel, liq_change_pct), high-frequency price lookup for label derivation.

**Invalid uses:** Do not generalise microstructure_log-derived features to the full universe without noting the Orca/Meteora gap.

---

## Dataset 5 — Archived Observer Exports

| Observer | run_id | DB path | Row count | Date range | Status |
|----------|--------|---------|-----------|------------|--------|
| LCR Continuation | `0c5337dd` | `/root/solana_trader/observer_lcr_cont_v1.db` | ~248 signal/control pairs | 2026-03-08 → 2026-03-10 | ARCHIVED |
| PFM Continuation | `1677a7da` | `/root/solana_trader/observer_pfm_cont_v1.db` | ~212 signal/control pairs | 2026-03-08 → 2026-03-10 | ARCHIVED |
| PFM Reversion | `99ed0fd1` | (embedded in pfm_cont_v1.db) | ~208 pairs | 2026-03-09 → 2026-03-10 | ARCHIVED |
| LCR Rank-Lift Sidecar | `bb7244cd` | (embedded in lcr_cont_v1.db) | 19 fires | 2026-03-10 | ARCHIVED |

These DBs are static (no new writes). One immutable local snapshot is retained per the backup policy. They are valid for retrospective subgroup analysis only.

---

## Dataset 6 — Canonical Sweep Outputs

| File | Description | Rows | Status |
|------|-------------|------|--------|
| `reports/synthesis/feature_family_sweep_full_sample.csv` | Track A +5m sweep | 10 features | FINAL |
| `reports/synthesis/feature_family_sweep_subset_micro.csv` | Track B +5m sweep | 7 features | FINAL |
| `reports/synthesis/feature_family_sweep_ranked_summary.csv` | All 17 features ranked | 17 features | FINAL |
| `reports/synthesis/feature_family_sweep_15m_winsorized.csv` | Track A+B +15m winsorized | 17 features | FINAL |
| `reports/synthesis/feature_family_sweep_30m_winsorized.csv` | Track A+B +30m winsorized | 17 features | FINAL |
| `reports/synthesis/trackb_robustness_report.md` | Bootstrap CI for r_m5 and vol_accel | 2 features | FINAL |
| `reports/research/benchmark_suite_v1.csv` | All benchmarks consolidated | 29 rows | FINAL |

---

## Dataset 7 — feature_tape_v2 (In Progress)

| Field | Value |
|-------|-------|
| **Table** | `feature_tape_v2` |
| **DB path** | `/root/solana_trader/data/solana_trader.db` |
| **Row count** | 0 (collection started 2026-03-12T19:00Z, first fire pending) |
| **Planned horizons** | +5m, +15m, +30m, +1h, +4h, +1d |
| **Feature families** | Order-flow/urgency (Family A), Route/quote quality (Family B), Market-state/gating (Family C) |
| **Status** | COLLECTING — do not use for analysis until ≥ 96 fires |

**Valid uses:** After ≥ 96 fires, use for Feature Acquisition v2 retrospective sweep.

**Invalid uses:** Do not use for any analysis until collection target is reached. Do not use as a substitute for feature_tape_v1 in existing analyses.
