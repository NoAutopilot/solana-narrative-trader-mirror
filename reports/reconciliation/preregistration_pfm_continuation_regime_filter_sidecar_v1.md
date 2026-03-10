# Preregistration Note — pfm_continuation_regime_filter_sidecar_v1

**Status: PREREGISTERED — NOT STARTED**
**Date registered: 2026-03-09**
**Prerequisite: Active PFM continuation run (1677a7da) must be classified first.**

---

## Motivation

The active PFM continuation run (run_id `1677a7da`) shows a positive mean delta (+0.007) but a negative median (−0.001) and a CI that crosses zero. The signal net is negative (−0.023), meaning the signal token loses money in absolute terms even though it loses less than the control. This pattern is consistent with a regime-dependent effect: continuation momentum may only be a valid signal during periods of broad market upward movement, and may be noise or noise-dominated during flat or negative-breadth regimes.

The goal of this sidecar is to test whether applying a fire-time regime filter — using only variables already present in the DB at fire time — can produce a sub-sample where (a) mean delta remains positive, (b) median delta turns positive, and (c) mean signal net turns positive.

---

## Hypothesis

> **H1:** Among PFM continuation fires where the market regime at fire time is positive (breadth or momentum filter), the mean delta +5m is positive, the median delta +5m is positive, and the mean signal net +5m is positive.

This is a sub-group hypothesis. It is not a new experiment; it is a retrospective filter applied to the existing run data, then prospectively validated on future fires.

---

## Candidate Regime Filters

The following filters are candidates. All must use only variables already recorded in the DB at fire time (i.e., columns already present in `observer_pfm_cont_v1`). No new data sources may be introduced.

| Filter ID | Definition | Column(s) Required |
|---|---|---|
| `breadth_positive` | >60% of the candidate pool at fire time has `entry_r_m5 > 0` | `entry_r_m5` (per-row, same fire epoch) |
| `median_r_m5_positive` | Median `entry_r_m5` across all candidates at fire time > 0 | `entry_r_m5` |
| `signal_r_m5_strong` | Signal's own `entry_r_m5 > 0` (weakest filter, included as baseline) | `entry_r_m5` |

Any additional filter must be documented here before implementation and must use only columns already in the schema.

---

## Analysis Plan

**Step 1 — Retrospective filter application**
Apply each candidate filter to the existing 206 completed pairs for run `1677a7da`. For each filter, compute View B metrics (mean, median, % > 0, CI, mean_sig, mean_ctl) on the filtered sub-sample and on the excluded complement.

**Step 2 — Selection rule**
Select at most one filter for prospective use. Selection criterion: the filter that produces the highest mean delta with a positive median and a CI lower bound > −0.02, applied to a sub-sample of n ≥ 30. If no filter meets this criterion, the sidecar is abandoned.

**Step 3 — Prospective validation**
If a filter is selected, tag future fires in the existing observer with the regime flag (read-only sidecar, no change to observer logic). Collect the next 50 prospective fires. Classify using the same canonical decision logic.

---

## Constraints

- No changes to `pfm_continuation_observer_v1.py`.
- No new DB tables required for the retrospective phase.
- The sidecar may add a read-only annotation column or a separate sidecar table for prospective tagging only.
- The filter must be computable at fire time from data already in the DB.
- This experiment does not begin until the active PFM continuation run is classified.

---

## Pre-specified Failure Modes

- If retrospective n < 30 for any filter sub-sample, that filter is disqualified.
- If the selected filter's retrospective mean delta is driven by fewer than 3 outlier pairs (top_contributor_share > 0.30), it is disqualified.
- If no filter produces a positive median, the sidecar is abandoned and the result is recorded as: "regime filtering does not rescue PFM continuation."

---

## Output

A single report file:
`reports/pfm_continuation_regime_filter_sidecar_v1/retrospective_filter_results.md`

Containing: filter-by-filter metrics table, selected filter (or abandonment note), and prospective plan.
