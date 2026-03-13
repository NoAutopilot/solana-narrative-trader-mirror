# Feature Tape v2 — Contract Specification

**Date:** 2026-03-13
**Script:** `tests/feature_tape_v2_contract_test.py`

---

## Purpose

Contract tests verify that the feature_tape_v2 table conforms to its documented schema, semantic rules, and no-lookahead guarantees. They run against a frozen or live DB without any mutation. They are the first gate before any sweep or analysis script touches the data.

---

## Contract Tests

| ID | Test | What It Checks | Severity |
|----|------|----------------|----------|
| CT1 | required_columns | All 62 required columns exist | CRITICAL |
| CT2 | eligible_semantics | eligible is 0/1; gate_reason NULL iff eligible=1 | CRITICAL |
| CT3 | lane_not_null | lane is never NULL (derived at collection) | HIGH |
| CT4 | micro_null_semantics | Micro columns are all-NULL or all-non-NULL per row | HIGH |
| CT5 | fire_level_constant | Pool aggregates are constant within each fire | HIGH |
| CT6 | label_columns | All 5 label columns exist (+5m through +4h) | CRITICAL |
| CT7 | no_lookahead | Labels are NULL pre-labeling, populated post-labeling | INFO |
| CT8 | fire_log | fire_log table exists and has entries | MEDIUM |
| CT9 | no_duplicates | No duplicate (fire_id, candidate_mint) pairs | CRITICAL |
| CT10 | order_flow_source | Values are 'microstructure_log' or 'missing' only | MEDIUM |

---

## Column Categories

### Identity (5 columns)
`fire_id`, `fire_utc`, `fire_epoch`, `candidate_mint`, `sym`

### Universe Classification (4 columns)
`eligible`, `gate_reason`, `lane`, `lane_source`

### Snapshot-Native (14 columns)
`pool_address`, `pool_type`, `pumpfun_origin`, `price_usd`, `liq_usd`, `vol_h24`, `mcap_usd`, `fdv_usd`, `r_m5`, `r_h1`, `r_h6`, `r_h24`, `age_minutes`

### Micro-Native (17 columns, nullable)
`buys_m5`, `sells_m5`, `buys_h1`, `sells_h1`, `buy_sell_ratio_m5`, `buy_sell_ratio_h1`, `buy_count_ratio_m5`, `buy_count_ratio_h1`, `avg_trade_usd_m5`, `avg_trade_usd_h1`, `vol_accel_m5_vs_h1`, `txn_accel_m5_vs_h1`, `rv_5m`, `rv_1m`, `range_5m`, `liq_change_pct`, `liq_cliff_flag`

### Quote-Native (2 columns, nullable for ineligible)
`jup_vs_cpamm_diff_pct`, `round_trip_pct`

### Fire-Level Aggregates (7 columns, constant within fire)
`pool_count`, `pool_size_total`, `breadth_positive_pct`, `breadth_negative_pct`, `median_pool_r_m5`, `pool_dispersion_r_m5`, `median_pool_rv5m`

### Derived (1 column)
`order_flow_source`

### Labels (5 columns, NULL until labeled)
`label_r_5m`, `label_r_15m`, `label_r_30m`, `label_r_1h`, `label_r_4h`

---

## Semantic Rules Enforced

1. `lane` = universe_category (not strategy lane)
2. `eligible` + `gate_reason` are explicit and consistent
3. Micro columns follow all-or-nothing NULL pattern
4. Fire-level columns are constant within fire
5. Labels are no-lookahead (NULL at collection time)
6. No duplicate fire-mint pairs
7. order_flow_source is a closed enum

---

## Usage

```bash
# Run against live DB
python3 tests/feature_tape_v2_contract_test.py \
    --db-path /root/solana_trader/data/solana_trader.db

# Run against frozen artifact
python3 tests/feature_tape_v2_contract_test.py \
    --db-path artifacts/feature_tape_v2_frozen_20260313_214500.db

# Dry run (list tests only)
python3 tests/feature_tape_v2_contract_test.py --dry-run
```
