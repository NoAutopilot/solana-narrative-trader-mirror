# feature_tape_v2 — Column Source Map

**Version:** v2 (post-audit)
**Audit date:** 2026-03-12
**Source tables audited:** `universe_snapshot`, `microstructure_log`

---

## Classification Key

| Code | Meaning |
|------|---------|
| `snapshot_native` | Column exists directly in `universe_snapshot` |
| `micro_native` | Column exists directly in `microstructure_log` |
| `derived_from_snapshot` | Computed from one or more `universe_snapshot` columns |
| `derived_from_micro` | Computed from one or more `microstructure_log` columns |
| `unavailable_in_current_phase` | No source table supports this field; excluded from v2 |

---

## Identity / Context Fields

| Column | Classification | Source Detail |
|--------|---------------|---------------|
| `fire_id` | `derived_from_snapshot` | SHA256 of fire_time_utc; generated at collection time |
| `fire_time_utc` | `derived_from_snapshot` | Aligned 15-min boundary; computed at collection time |
| `fire_time_epoch` | `derived_from_snapshot` | Unix timestamp of fire_time_utc |
| `candidate_mint` | `snapshot_native` | `universe_snapshot.mint_address` |
| `candidate_symbol` | `snapshot_native` | `universe_snapshot.token_symbol` |
| `snapshot_at_used` | `snapshot_native` | `universe_snapshot.snapshot_at` of the row used |
| `micro_ts_used` | `micro_native` | `microstructure_log.logged_at` of the row used; NULL if no micro row |
| `created_at` | `derived_from_snapshot` | Python datetime at write time |

---

## Classification / Lane Fields

| Column | Classification | Source Detail | Notes |
|--------|---------------|---------------|-------|
| `lane` | `derived_from_snapshot` | Derived from `eligible` + `gate_reason` + `pool_type` at collection time | `lane` column in `universe_snapshot` is **always NULL** — never populated by scanner. Must be derived. |
| `lane_source` | `derived_from_snapshot` | Always `"derived_at_collection"` | Indicates lane was computed, not stored |
| `venue` | `snapshot_native` | `universe_snapshot.venue` | |
| `pool_type` | `snapshot_native` | `universe_snapshot.pool_type` | |
| `pumpfun_origin` | `snapshot_native` | `universe_snapshot.pumpfun_origin` | |
| `eligible` | `snapshot_native` | `universe_snapshot.eligible` | Used as lane input |
| `gate_reason` | `snapshot_native` | `universe_snapshot.gate_reason` | Used as lane input |

**Lane derivation logic (canonical):**
```
if eligible == 1:
    if pool_type == 'pumpswap':  lane = 'pumpswap_live'
    elif pool_type == 'raydium':  lane = 'raydium_live'
    elif pool_type == 'orca':     lane = 'orca_live'
    elif pool_type == 'meteora':  lane = 'meteora_live'
    else:                         lane = 'other_live'
elif gate_reason is not None and 'spam' in gate_reason:
    lane = 'spam_filtered'
else:
    lane = 'ineligible'
```

---

## Fundamentals

| Column | Classification | Source Detail |
|--------|---------------|---------------|
| `age_hours` | `snapshot_native` | `universe_snapshot.age_hours` |
| `liquidity_usd` | `snapshot_native` | `universe_snapshot.liq_usd` |
| `vol_h1` | `snapshot_native` | `universe_snapshot.vol_h1` |
| `vol_h24` | `snapshot_native` | `universe_snapshot.vol_h24` |
| `price_usd` | `snapshot_native` | `universe_snapshot.price_usd` |
| `r_m5_snap` | `snapshot_native` | `universe_snapshot.r_m5` (rolling 5m return from snapshot) |
| `r_h1_snap` | `snapshot_native` | `universe_snapshot.r_h1` |

---

## Family A — Order-Flow / Urgency

All 5m-window order-flow fields are sourced from `microstructure_log` only. They are NULL when no micro row exists within the allowed lookback window.

| Column | Classification | Source Detail | NULL when |
|--------|---------------|---------------|-----------|
| `buys_m5` | `micro_native` | `microstructure_log.buys_m5` | No micro row |
| `sells_m5` | `micro_native` | `microstructure_log.sells_m5` | No micro row |
| `buys_h1` | `micro_native` | `microstructure_log.buys_h1` | No micro row |
| `sells_h1` | `micro_native` | `microstructure_log.sells_h1` | No micro row |
| `buy_sell_ratio_m5` | `micro_native` | `microstructure_log.buy_sell_ratio_m5` | No micro row |
| `buy_sell_ratio_h1` | `micro_native` | `microstructure_log.buy_sell_ratio_h1` | No micro row |
| `buy_count_ratio_m5` | `micro_native` | `microstructure_log.buy_count_ratio_m5` | No micro row |
| `buy_count_ratio_h1` | `micro_native` | `microstructure_log.buy_count_ratio_h1` | No micro row |
| `avg_trade_usd_m5` | `micro_native` | `microstructure_log.avg_trade_usd_m5` | No micro row |
| `avg_trade_usd_h1` | `micro_native` | `microstructure_log.avg_trade_usd_h1` | No micro row |
| `vol_accel_m5_vs_h1` | `micro_native` | `microstructure_log.vol_accel_m5_vs_h1` | No micro row |
| `txn_accel_m5_vs_h1` | `micro_native` | `microstructure_log.txn_accel_m5_vs_h1` | No micro row |
| `r_m5_micro` | `micro_native` | `microstructure_log.r_m5` | No micro row |
| `rv_5m` | `micro_native` | `microstructure_log.rv_5m` | No micro row |
| `rv_1m` | `micro_native` | `microstructure_log.rv_1m` | No micro row |
| `range_5m` | `micro_native` | `microstructure_log.range_5m` | No micro row |

**Snapshot fallback fields** (available even without micro row):

| Column | Classification | Source Detail |
|--------|---------------|---------------|
| `buys_m5_snap` | `snapshot_native` | `universe_snapshot.buys_m5` |
| `sells_m5_snap` | `snapshot_native` | `universe_snapshot.sells_m5` |
| `buy_count_ratio_m5_snap` | `snapshot_native` | `universe_snapshot.buy_count_ratio_m5` |
| `avg_trade_usd_m5_snap` | `snapshot_native` | `universe_snapshot.avg_trade_usd_m5` |
| `order_flow_source` | `derived_from_snapshot` | `"microstructure_log"` or `"universe_snapshot_fallback"` or `"missing"` |

---

## Family B — Route / Quote Quality

| Column | Classification | Source Detail | NULL when |
|--------|---------------|---------------|-----------|
| `jup_vs_cpamm_diff_pct` | `snapshot_native` | `universe_snapshot.jup_vs_cpamm_diff_pct` | Rare: quote sweep failed |
| `round_trip_pct` | `snapshot_native` | `universe_snapshot.round_trip_pct` | Rare: quote sweep failed |
| `impact_buy_pct` | `snapshot_native` | `universe_snapshot.impact_buy_pct` | Rare: quote sweep failed |
| `impact_sell_pct` | `snapshot_native` | `universe_snapshot.impact_sell_pct` | Rare: quote sweep failed |
| `impact_asymmetry_pct` | `derived_from_snapshot` | `impact_buy_pct - impact_sell_pct` | When either impact is NULL |
| `quote_source` | `derived_from_snapshot` | Always `"universe_snapshot"` | — |

---

## Family C — Market-State / Gating

| Column | Classification | Source Detail | NULL when |
|--------|---------------|---------------|-----------|
| `liq_change_pct` | `micro_native` | `microstructure_log.liq_change_pct` | No micro row |
| `liq_cliff_flag` | `micro_native` | `microstructure_log.liq_cliff_flag` | No micro row |
| `pool_size_total` | `derived_from_snapshot` | COUNT of snapshot rows at fire time for all candidates | Never NULL |
| `pool_size_with_micro` | `derived_from_micro` | COUNT of micro rows at fire time for all candidates | Never NULL (may be 0) |
| `coverage_ratio_micro` | `derived_from_micro` | `pool_size_with_micro / pool_size_total` | Never NULL |
| `breadth_positive_pct` | `derived_from_micro` | Fraction of micro-covered mints with `r_m5 > 0` | NULL if `pool_size_with_micro == 0` |
| `breadth_negative_pct` | `derived_from_micro` | Fraction of micro-covered mints with `r_m5 < 0` | NULL if `pool_size_with_micro == 0` |
| `median_pool_r_m5` | `derived_from_micro` | Median `r_m5` across all micro-covered mints at fire | NULL if `pool_size_with_micro == 0` |
| `pool_dispersion_r_m5` | `derived_from_micro` | Std dev of `r_m5` across all micro-covered mints at fire | NULL if `pool_size_with_micro < 2` |
| `median_pool_rv5m` | `derived_from_micro` | Median `rv_5m` across all micro-covered mints at fire | NULL if `pool_size_with_micro == 0` |
| `pool_liquidity_median` | `derived_from_snapshot` | Median `liq_usd` across all snapshot candidates at fire | Never NULL |
| `pool_vol_h1_median` | `derived_from_snapshot` | Median `vol_h1` across all snapshot candidates at fire | Never NULL |
| `liq_source` | `derived_from_micro` | `"microstructure_log"` or `"missing"` | — |

**Fire-level aggregate rule:** `breadth_positive_pct`, `breadth_negative_pct`, `median_pool_r_m5`, `pool_dispersion_r_m5`, `median_pool_rv5m` are computed once per fire and written identically to all rows in that fire.

---

## Unavailable in Current Phase

See `feature_tape_v2_unavailable_fields.md` for full details.

| Column | Reason |
|--------|--------|
| `buy_count_1m` | No 1m count aggregates in any source table |
| `sell_count_1m` | No 1m count aggregates in any source table |
| `buy_usd_1m` | No 1m USD aggregates in any source table |
| `sell_usd_1m` | No 1m USD aggregates in any source table |
| `signed_flow_1m` | No 1m signed flow in any source table |
| `buy_sell_ratio_1m` | No 1m ratio in any source table |
| `avg_trade_usd_1m` | No 1m avg trade in any source table |
| `txn_accel_m1_vs_h1` | No 1m txn count in any source table |
| `vol_accel_m1_vs_h1` | No 1m vol in any source table |
| `median_trade_usd_5m` | Not stored in microstructure_log |
| `max_trade_usd_5m` | Not stored in microstructure_log |
| `signed_flow_5m` | Not stored in microstructure_log (only buy/sell counts and ratios) |

---

*Generated by audit on 2026-03-12. Source tables: `universe_snapshot` (171,731 rows), `microstructure_log` (502,589 rows).*
