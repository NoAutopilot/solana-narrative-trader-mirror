# Preregistration Note — lcr_rank_lift_sidecar_v1
_Date: 2026-03-10T15:05Z_
_Status: AWAITING APPROVAL — NOT IMPLEMENTED_

---

## Preflight Results

### PREFLIGHT CHECK 1 — Candidate pool exists and is queryable

**Result: PARTIAL PASS / ISSUE FLAGGED**

The candidate pool is stored in `universe_snapshot` in `/root/solana_trader/data/solana_trader.db`. However, following the VPS resize and DB rebuild, the `lane` and `r_m5` columns in `universe_snapshot` are currently **NULL for all rows** (51,616 rows, all NULL). The scanner is writing snapshots but the lane classification and r_m5 computation are not being applied to the fresh DB.

The `microstructure_log` table (154,727 rows, actively writing) also has **no `lane` column**.

The historical observer data (`observer_lcr_cont_v1.db`) confirms that `large_cap_ray` lane candidates do exist and have `entry_r_m5` values — they were correctly populated before the resize. The lane assignment logic exists in `et_shadow_trader_v1.py` (line 1093: `return "large_cap_ray"` for `pumpfun_origin=0 AND age >= 30d`).

**Root cause:** The fresh `universe_snapshot` table was created without the migration that populates `lane` and `r_m5`. The scanner writes raw data but the lane/r_m5 enrichment step is not running against the new DB.

**Action required before implementation:** Confirm that `lane` and `r_m5` are being populated in `universe_snapshot` at the time of sidecar fire. If not, the sidecar must source these fields from `microstructure_log` with a lane derivation rule, or the enrichment must be restored.

### PREFLIGHT CHECK 2 — Baseline score field exists

**Result: PASS (with clarification)**

The live system uses `pullback_score_rank` as the sole active strategy. The score function is `score_pullback()` (line 1381 of `et_shadow_trader_v1.py`):

```
score = W_DEPTH*z_depth + W_VOL_ACCEL*vol_accel + W_BUY_RATIO*(buy_ratio-0.5) - W_PENALTY*risk_flags
```

This score is computed in-memory at fire time from `universe_snapshot` fields. It is **not stored** in the DB per-candidate. For the sidecar, the score must be recomputed from the snapshot fields at each fire time using the same formula.

All required input fields (`z_depth`, `vol_accel`, `buy_ratio`, `risk_flags`) are derivable from columns in `universe_snapshot` (specifically: `liq_usd`, `vol_m5`, `vol_h1`, `buys_m5`, `sells_m5`, `spam_flag`, `liq_cliff_flag`, `mint_authority_present`, `freeze_authority_present`).

### PREFLIGHT CHECK 3 — Score non-null coverage >= 95%

**Result: BLOCKED pending lane/r_m5 fix**

Cannot verify until `lane` and `r_m5` are populated in the live DB. Based on historical LCR observer data (n=702 rows across 24 runs), `entry_r_m5` was non-null for 100% of LCR candidates. Coverage is expected to be >=95% once the enrichment is restored.

### PREFLIGHT CHECK 4 — Pool density sufficient for top-K=3 comparison

**Result: PASS (based on historical data)**

From `observer_lcr_cont_v1.db`, the LCR lane (`large_cap_ray`) consistently had 5–15 eligible candidates per fire across all runs. Top-K=3 is well within the typical pool size. No fires had fewer than 3 eligible candidates in the historical record.

---

## Preflight Verdict

**CONDITIONAL PASS — one blocker must be resolved before implementation:**

> `lane` and `r_m5` must be confirmed as populated in `universe_snapshot` at sidecar fire time, OR the sidecar must be designed to derive lane and r_m5 from `microstructure_log` using the same logic as the scanner.

---

## Hypothesis

Within the existing scored candidate pool, promoting a candidate that has the LCR continuation feature:

> `lane = 'large_cap_ray' AND r_m5 > 0`

will improve the absolute executable +5m net markout of the selected token relative to the baseline top-1 by current `pullback_score`.

**Primary metric:**
`mean( net_markout_5m(feature_promoted_choice) - net_markout_5m(baseline_top1) )`

---

## Exact Sidecar Logic

### Candidate pool source
`universe_snapshot` filtered to `snapshot_at` within ±60s of fire time, `eligible=1`.

If `lane` is NULL in `universe_snapshot`, derive lane using:
- `pumpfun_origin=0 AND age_hours >= 720` → `large_cap_ray`

If `r_m5` is NULL in `universe_snapshot`, source from `microstructure_log` at closest `logged_at` within ±60s.

### Baseline score
Recompute `pullback_score` from snapshot fields using the same formula as `et_shadow_trader_v1.py`:
```python
score = W_DEPTH*z_depth + W_VOL_ACCEL*vol_accel + W_BUY_RATIO*(buy_ratio - 0.5) - W_PENALTY*risk_flags
```
Weights: `W_DEPTH`, `W_VOL_ACCEL`, `W_BUY_RATIO`, `W_PENALTY` read from live config.

### baseline_top1
Candidate with highest `pullback_score`. Tie-break: `mint_address` ascending.

### Feature set
Candidates where `lane = 'large_cap_ray' AND r_m5 > 0`.

### feature_promoted_choice
Among the top-K=3 baseline-ranked candidates, choose the highest-score candidate in the feature set. If none of the top-3 are in the feature set, fall back to `baseline_top1`.

### K value
**K = 3 (fixed, not tunable).**

### Recorded fields per fire
- `fire_id`, `fire_time`
- `baseline_top1_mint`, `baseline_top1_symbol`, `baseline_top1_score`, `baseline_top1_lane`, `baseline_top1_r_m5`
- `feature_choice_mint`, `feature_choice_symbol`, `feature_choice_score`, `feature_choice_lane`, `feature_choice_r_m5`
- `promoted` (1 if feature_choice != baseline_top1, else 0)
- `baseline_top1_entry_quote_ok`, `baseline_top1_net_5m`
- `feature_choice_entry_quote_ok`, `feature_choice_net_5m`
- `lift_5m = feature_choice_net_5m - baseline_top1_net_5m`
- `row_valid`, `invalid_reason`

### Special cases
- If `feature_promoted_choice == baseline_top1`: record `promoted=0`, `lift_5m=0`.
- If entry quote fails for either choice: `row_valid=0`.
- If +5m quote fails for either choice: `row_valid=0`.

---

## Quote Model
- Same Jupiter quote source as existing observers
- Same fixed notional (0.1 SOL)
- Same slippage assumptions
- Same jitter bounds (entry: ±30s, fwd: ±20s)

---

## Data Quality Gates
| Gate | Threshold | Action |
|---|---|---|
| entry_quote_coverage | < 95% | INVALIDATE run |
| +5m_quote_coverage | < 95% | INVALIDATE run |
| row_valid | < 100% | INVALIDATE run |
| timing jitter | outside bounds | row_valid=0 |

---

## Checkpoints
| n | Action |
|---|---|
| 10 | Health check only (coverage, jitter, row_valid) |
| 30 | Descriptive checkpoint (no classification) |
| 50 | First decision checkpoint |

---

## Decision Rules at n >= 50

| Classification | Condition |
|---|---|
| SUPPORTED | mean_lift > 0 AND median_lift > 0 AND CI_lower > 0 |
| FALSIFIED | mean_lift <= 0 AND median_lift <= 0 |
| FRAGILE / INCONCLUSIVE | All other cases |

---

## DB and Service Names
- DB: `/root/solana_trader/data/lcr_rank_lift_sidecar_v1.db`
- Table: `lcr_rank_lift_sidecar_v1`
- Service: `solana-lcr-rank-lift-sidecar.service`

---

## What Has NOT Been Implemented
- No sidecar script written
- No DB created
- No service created
- No observer code changed
- No scanner code changed
- No dashboard changed

**Awaiting approval before any implementation.**
