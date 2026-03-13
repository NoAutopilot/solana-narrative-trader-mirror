# Feature Tape v2 — Semantic Rules (Ratified)

**Date:** 2026-03-12
**Author:** Manus AI
**Status:** RATIFIED — effective immediately

---

## Collection Scope

Feature Tape v2 is ratified as a **FULL-UNIVERSE** collection. Every row returned by the `universe_snapshot` query at fire time is collected, regardless of `eligible` status. This includes eligible candidates, spam-filtered rows, impact-filtered rows, age-filtered rows, and all other ineligible rows.

This decision is final and does not require re-evaluation at the 10-fire checkpoint.

---

## Primary vs Secondary Analysis Scope

| Scope | Filter | Use |
|-------|--------|-----|
| **Primary (default)** | `eligible = 1` | All feature sweeps, model discovery, promotion gate evaluation, holdout evaluation |
| **Secondary (audit)** | No filter (full universe) | Coverage reports, lane distribution monitoring, data quality audits, missingness analysis |

All future sweep scripts, notebooks, and reports must default to `WHERE eligible = 1` unless explicitly stated otherwise. Full-universe results are secondary audit views only and must be clearly labelled as such.

---

## Semantic Rule 1: `lane` Is `universe_category`

The `lane` column in `feature_tape_v2` is a **universe category** (venue-state classification), not a strategy lane. It encodes:

| `lane` value | Meaning | `eligible` |
|-------------|---------|-----------|
| `pumpswap_live` | Eligible, PumpSwap venue | 1 |
| `raydium_live` | Eligible, Raydium venue | 1 |
| `orca_live` | Eligible, Orca venue | 1 |
| `meteora_live` | Eligible, Meteora venue | 1 |
| `other_live` | Eligible, unknown venue | 1 |
| `spam_filtered` | Ineligible, spam gate | 0 |
| `impact_filtered` | Ineligible, impact/slippage gate | 0 |
| `age_filtered` | Ineligible, age gate | 0 |
| `vol_filtered` | Ineligible, volume gate | 0 |
| `liq_filtered` | Ineligible, liquidity gate | 0 |
| `ineligible` | Ineligible, other/unknown gate | 0 |

The column is **not renamed** in the schema (to avoid a breaking change during active collection), but all documentation and reports must refer to it as `universe_category` in prose. The `lane_source` column remains `derived_at_collection`.

A canonical strategy lane (e.g., `momentum_breakout`, `mean_reversion`) does not yet exist in the system and will be defined separately if and when a deployable signal is found.

---

## Semantic Rule 2: `eligible` and `gate_reason` Are Explicit Columns

**Status: CONFIRMED PRESENT**

Both columns exist in the `feature_tape_v2` CREATE TABLE schema and are populated for every row:

```sql
eligible    INTEGER,    -- 1 = passed all scanner gates; 0 = failed at least one
gate_reason TEXT,       -- NULL if eligible=1; scanner-provided reason string if eligible=0
```

These columns are sourced directly from `universe_snapshot.eligible` and `universe_snapshot.gate_reason` at collection time. They are the authoritative filter columns for the primary/secondary scope split defined above.

**No patch required. No restart required.**

---

## Semantic Rule 3: Dual Coverage Reporting

All future coverage reports must show both scopes:

```
Coverage Report — Fire {fire_id}
  Full universe:    {n_total} rows, {n_micro}/{n_total} micro ({pct_micro}%)
  Eligible only:    {n_eligible} rows, {n_micro_eligible}/{n_eligible} micro ({pct_micro_eligible}%)
```

The eligible-only coverage is the primary metric for promotion gate G8 (coverage >= 70%).

---

## Semantic Rule 4: Quote/Route Null Semantics

`jup_vs_cpamm_diff_pct`, `round_trip_pct`, `impact_buy_pct`, `impact_sell_pct`, and `impact_asymmetry_pct` are expected to be NULL for ineligible rows. This is because the scanner skips the Jupiter quote call for rows that fail the spam or early-exit gates.

All future analysis must document this explicitly:

> Quote/route features are NULL for ineligible rows by design. Coverage statistics for these features must be computed on the eligible-only subset.

---

## Semantic Rule 5: Market-State Field Scope (Future)

The current fire-level market-state aggregates (`breadth_positive_pct`, `breadth_negative_pct`, `median_pool_r_m5`, `pool_dispersion_r_m5`, `median_pool_rv5m`) are computed from **all micro-covered rows** regardless of eligibility. The pool-level aggregates (`pool_liquidity_median`, `pool_vol_h1_median`, `pool_size_total`) are computed from **all snapshot rows**.

In a future schema revision (v3 or later), these should be split into:

| Field suffix | Scope | Example |
|-------------|-------|---------|
| `_all` | All scanned rows | `breadth_positive_pct_all` |
| `_eligible` | Eligible rows only | `breadth_positive_pct_eligible` |

This split is **deferred** — it is not implemented in v2 and does not require a patch. The current all-universe aggregates are acceptable for the v2 collection run because they serve as market-state context, not selection features.

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-03-12 | Initial ratification: full-universe scope, 5 semantic rules | Manus AI |
