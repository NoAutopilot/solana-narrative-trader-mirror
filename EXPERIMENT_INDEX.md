# EXPERIMENT INDEX

Canonical index of all observer experiments. One row per run_id.
Status values: ACTIVE | ARCHIVED | PREREGISTERED | ABANDONED

---

| # | Name | run_id | Status | Start | End | n | Classification | Memo |
|---|---|---|---|---|---|---|---|---|
| 001 | pfm_continuation_observer_v1 (pilot A) | `2ce4ff81` | ARCHIVED | 2026-03-06T17:30Z | 2026-03-06T19:15Z | 8 | INSUFFICIENT DATA | — |
| 002 | pfm_continuation_observer_v1 (pilot B) | `2a439616` | ARCHIVED | 2026-03-06T19:15Z | 2026-03-07T00:30Z | 22 | INSUFFICIENT DATA | `archive_memo_pfm_2a439616.md` |
| 003 | pfm_continuation_observer_v1 (main run) | `1677a7da` | ARCHIVED | 2026-03-07T01:15Z | 2026-03-09T06:28Z | 212 | RANKING FEATURE ONLY / NOT PROMOTABLE | `archive_memo_pfm_1677a7da.md` |
| 004 | pfm_reversion_observer_v1 | `99ed0fd1` | ARCHIVED | 2026-03-09T06:28Z | 2026-03-10T14:15Z | 208 | INCONCLUSIVE / ABANDONED | `momentum_direction_family_FINAL_closure.md` |
| 005 | lcr_continuation_observer_v1 (primary) | `0c5337dd` | ARCHIVED | 2026-02-xx | 2026-03-06T21:15Z | 248 | RANKING FEATURE ONLY / NOT PROMOTABLE | `momentum_direction_family_FINAL_closure.md` |
| 006 | lcr_rank_lift_sidecar_v1 | `bb7244cd` | ARCHIVED | 2026-03-10T16:30Z | 2026-03-10T21:00Z | 19 | NON-BINDING / LOW INCREMENTAL VALUE | `lcr_rank_lift_sidecar_v1_closure_memo.md` |
| 007 | age_conditioned_continuation (retrospective) | — | ARCHIVED | 2026-03-10 | 2026-03-10 | 71 | NO-GO — OUTLIER-DRIVEN / NOT STRONG ENOUGH | `momentum_direction_family_FINAL_closure.md` |
| 008 | feature_tape_v1 (public-data long-only sweep) | `feature_tape_v1_2026_03_11` | ARCHIVED | 2026-03-11T00:45Z | 2026-03-12T06:15Z | 4,081 rows / 100 fires | CLOSED — NO NEW LIVE OBSERVER | `feature_tape_v1_closure_memo.md` |
| 009 | feature_tape_v2 (full-universe, eligible-only analysis) | `feature_tape_v2_2026_03_12` | ARCHIVED | 2026-03-12T21:34Z | 2026-03-14T15:00Z | 4,222 rows / 96 fires (118 at stop) | CLOSED — NO NEW LIVE OBSERVER | `feature_tape_v2_FINAL_closure.md` |

---

## Sidecar Index

| # | Name | Parent run_id | Status | Verdict | Report |
|---|---|---|---|---|---|
| S001 | pfm_continuation_regime_filter_sidecar_v1 | `1677a7da` | COMPLETE | RANKING FEATURE ONLY | `pfm_regime_filter_sidecar_v1_report.md` |
| S002 | lcr_rank_lift_sidecar_v1 | `0c5337dd` | ARCHIVED | NON-BINDING / LOW INCREMENTAL VALUE | `lcr_rank_lift_sidecar_v1_closure_memo.md` |

---

## Family Index

| Family | Branches | Status | Final Verdict | Memo |
|---|---|---|---|---|
| Momentum / Direction | LCR Cont, PFM Cont, PFM Rev, LCR Rank-Lift, Age-Conditioned Retro | **ABANDONED** | No new live observers will be launched from this family | `momentum_direction_family_FINAL_closure.md` |
| Public-Data Long-Only Selection | Feature Tape v1 (17 features, +5m/+15m/+30m) | **ABANDONED** | No new live observers from current dataset or feature family | `feature_tape_v1_closure_memo.md` |
| Feature Acquisition v2 | Feature Tape v2 (42 features tested, full-universe, eligible-only analysis) | **ABANDONED** | No new live observers from this feature space | `feature_tape_v2_FINAL_closure.md` |

---

## Current Phase

**Feature Acquisition v2 — Data Collection** (Path B selected)

`feature_tape_v2` is actively collecting on VPS. No live observer is approved. The autopilot will run the final sweep after 96 fires + label maturity and produce a PROCEED/PIVOT/STOP recommendation.

See `reports/research/CURRENT_STATE.md` for authoritative current state.
See `reports/research/DECISION_TREE_v1.md` for all allowed next moves.

---

### 010 — Large-Cap Swing Stage A
| Field | Value |
|-------|-------|
| Family | Large-Cap Swing |
| Status | CLOSED / NO-GO |
| Date | 2026-03-15 |
| Universe | 25 tokens, point-in-time dynamic |
| Signals | Pullback in uptrend, Breakout from consolidation |
| Key result | 0/18 scenarios passed. Negative expected value before costs. |
| Artifacts | reports/new_programs/largecap_swing_stageA_*.md |
