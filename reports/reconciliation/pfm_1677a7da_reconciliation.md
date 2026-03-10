# PFM Run 1677a7da — Reconciliation Report

**Audit only. No code changes. No restarts. No strategy classification.**
**Run classification: UNRESOLVED / REPORT INCONSISTENT** *(pending resolution of sample-size discrepancy)*

---

## 1. DB Path + Table Name + Schema Mapping

| Field | Value |
|---|---|
| `db_path` | `/root/solana_trader/data/observer_pfm_cont_v1.db` |
| `table_name` | `observer_pfm_cont_v1` |
| Total rows (all runs) | 468 |
| Rows for run `1677a7da` | 408 (204 signal + 204 control) |

### Column Mapping

| Logical Field | Actual Column Name |
|---|---|
| Fire ID | `signal_fire_id` |
| Run ID | `run_id` |
| Candidate type | `candidate_type` (`signal` / `control`) |
| Signal/control link | `candidate_id` (signal) → `control_for_signal_id` (control) |
| Entry timestamp | `entry_quote_ts_epoch` |
| Entry quote ok | `entry_quote_ok` |
| +5m due epoch | `fwd_due_epoch_5m` |
| +5m quote timestamp | `fwd_quote_ts_epoch_5m` |
| +5m quote ok | `fwd_quote_ok_5m` |
| Net markout +5m | `fwd_net_fee100_5m` |
| Row valid | `row_valid` |
| Invalid reason | `invalid_reason` |

---

## 2. Pair Export Summary

The CSV `pfm_1677a7da_all_pairs.csv` was produced by joining signal and control rows on `signal_fire_id`, filtering to rows where **both** `fwd_quote_ok_5m = 1`, ordered by `fire_time_epoch ASC`.

| Metric | Value |
|---|---|
| Total completed +5m pairs exported | **204** |
| n_fail_5m (within exported set) | **0** |
| row_invalid count | **0** |
| Outlier pairs (`|delta| >= 0.10`) | **50** |

The DB currently contains **204** complete pairs for run `1677a7da`. The dashboard snapshot that showed `n=67` was taken at an earlier point in time when only 67 pairs had completed.

---

## 3. Set A Metrics — ALL COMPLETED (n=204)

**Definition:** All rows in the exported CSV where both signal and control have `fwd_quote_ok_5m = 1`. This is the full current state of the run.

| Metric | Value |
|---|---|
| n | 204 |
| mean_delta_5m | **+0.007901** |
| median_delta_5m | **−0.000575** |
| pct_delta_positive | **49.5%** |
| std_delta_5m | 0.110720 |
| 95% CI (t-based) | [−0.007384, +0.023185] |
| outlier_count (`|d| >= 0.10`) | 50 |
| top_contributor_share | 0.0403 |
| trimmed_mean (10%) | +0.000762 |
| winsorized_mean (10%) | +0.003383 |
| bootstrap 95% CI (mean) | [−0.007072, +0.023502] |
| bootstrap 95% CI (median) | [−0.013085, +0.009818] |
| sign_test p-value (vs 50%) | 0.9442 |

---

## 4. Set B Metrics — TIMING-VALID COMPLETED (n=203)

**Pre-registered definition (applied before looking at results):**
A pair is timing-valid if ALL of the following hold:
- `signal_row_valid = 1`
- `control_row_valid = 1`
- `signal_entry_quote_ok = 1`
- `control_entry_quote_ok = 1`
- `signal_fwd_quote_ok_5m = 1`
- `control_fwd_quote_ok_5m = 1`
- `abs(signal_fwd_jitter_5m_sec) <= 20`
- `abs(control_fwd_jitter_5m_sec) <= 20`

One pair was excluded from Set A due to a fwd jitter > 20s on one leg.

| Metric | Value |
|---|---|
| n | 203 |
| mean_delta_5m | **+0.007823** |
| median_delta_5m | **−0.000637** |
| pct_delta_positive | **49.3%** |
| std_delta_5m | 0.110988 |
| 95% CI (t-based) | [−0.007537, +0.023183] |
| outlier_count (`|d| >= 0.10`) | 50 |
| top_contributor_share | 0.0404 |
| trimmed_mean (10%) | +0.000622 |
| winsorized_mean (10%) | +0.003283 |
| bootstrap 95% CI (mean) | [−0.007062, +0.023315] |
| bootstrap 95% CI (median) | [−0.013953, +0.009038] |
| sign_test p-value (vs 50%) | 0.8884 |

---

## 5. Dashboard Reproduction

The dashboard (`observer_dashboard.py`) loads all rows for the active `run_id` via:

```python
rows = conn.execute(
    "SELECT * FROM observer_pfm_cont_v1 WHERE run_id=?", (run_id,)
).fetchall()
```

It then builds `ok_pairs` by matching `ctrl_map[s['candidate_id']]` where both `fwd_quote_ok_5m = 1`, and computes `mean(deltas)` over all such pairs.

**Reproduced using exact dashboard logic against current DB:**

| Metric | Value |
|---|---|
| n_ok_pairs (dashboard logic, current) | 204 |
| mean_delta (all 204, dashboard logic) | **+0.007901** |
| mean_delta (first 67, dashboard logic) | **+0.012646** ✓ |

The dashboard snapshot value of `+0.012646` at `n=67` is **confirmed correct** — it was computed from the first 67 completed pairs as of the time of the snapshot, using the correct dashboard logic.

---

## 6. Prior Reconciliation Report Reproduction

The prior reconciliation report (`pfm_reconciliation.py`) used a **manually transcribed** subset of 65 pairs parsed from truncated SSH terminal output. It did not query the DB directly with a deterministic SQL join. The row set was incomplete and contained transcription errors, resulting in a different sample.

**Reproduced using prior reconciliation data:**

| Metric | Value |
|---|---|
| n (prior reconciliation) | 65 (truncated/transcribed) |
| mean_delta (prior reconciliation) | **+0.007893** |

---

## 7. Exact Cause of Discrepancy

> **Different rows / same formula.**

The dashboard value (`+0.012646`) was computed from the **first 67 chronologically ordered completed pairs** at the time of the snapshot. The prior reconciliation report (`+0.007893`) was computed from a **different 65-row subset** that was manually transcribed from truncated SSH output and did not match the actual first 67 pairs from the DB.

Both used `mean(signal_net_5m - control_net_5m)`. The formula was identical. The row sets differed. The dashboard number is the correct one for `n=67`. The current full-run mean is `+0.007901` at `n=204`.

---

## 8. A1 / A2 / A3 Sensitivity Proof

Within the exported CSV (all 204 complete pairs), `n_fail_included = 0` by construction — every row has `fwd_quote_ok_5m = 1` for both legs. Therefore no imputation is possible or required.

| Sensitivity Test | Definition | Value |
|---|---|---|
| A1 (drop failed) | Exclude rows where `fwd_quote_ok_5m = 0` | **+0.007901** |
| A2 (failed = 0) | Replace failed delta with 0.0 | **+0.007901** |
| A3 (failed = worst non-outlier) | Replace failed delta with worst `|d| < 0.10` | **+0.007901** |

`worst_non_outlier_delta = −0.098758`

**IDENTITY HOLDS: A1 = A2 = A3.** This is mathematically required when `n_fail = 0`. Any prior report showing A1 ≠ A2 ≠ A3 was a **report bug** caused by computing sensitivity tests over a different (incomplete) row set that incorrectly included rows with missing data.

---

## 9. Final Audit Verdict

| Claim | Verdict |
|---|---|
| Dashboard `mean_delta = +0.012646` at `n=67` | **DASHBOARD CORRECT** — confirmed by DB reproduction |
| Reconciliation report `mean_delta = +0.007893` | **RECONCILIATION REPORT WRONG** — used a different, incomplete row set (65 manually transcribed rows ≠ first 67 DB rows) |
| A1 ≠ A2 ≠ A3 in prior report | **REPORT BUG** — caused by incorrect row set, not a real sensitivity effect |
| Current full-run mean (n=204) | **+0.007901** — this is the correct current value |

**Overall verdict: MIXED / DIFFERENT SAMPLE DEFINITIONS**

The dashboard was correct for its snapshot. The reconciliation report used a different and incorrect sample. The current authoritative number from the DB is `mean_delta = +0.007901` at `n=204`.

---

*Report generated: 2026-03-08. Source of truth: DB at `/root/solana_trader/data/observer_pfm_cont_v1.db`. No code was modified. No services were restarted.*
