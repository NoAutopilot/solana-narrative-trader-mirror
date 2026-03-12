# Experiment Proposal Template v1

**Version:** 1.0  
**Effective:** 2026-03-12  
**Status:** MANDATORY — all new experiment proposals must use this template  
**Rule:** A proposal that does not complete every section will not be approved for implementation.

---

## Instructions

Copy this template, fill in every section, and submit for review before writing any collection or analysis code. Sections marked **(REQUIRED)** must be completed in full. Sections marked **(if applicable)** may be marked N/A with a brief justification.

---

## Proposal Header

| Field | Value |
|-------|-------|
| **Proposal ID** | EP-XXX (assigned sequentially) |
| **Date** | YYYY-MM-DD |
| **Author** | |
| **Proposed experiment name** | |
| **Feature family** | (e.g., order-flow/urgency, route/quote-quality, market-state/gating) |
| **Experiment type** | (feature_tape / live_observer / retrospective_subgroup / sidecar) |
| **Estimated collection duration** | |
| **Estimated storage cost** | |

---

## Section 1 — Hypothesis (REQUIRED)

State the hypothesis in one sentence, in the form:

> "Among [population], [feature/condition] predicts [outcome] at [horizon] with positive net-proxy mean and positive net-proxy median."

Do not use vague language. The hypothesis must be falsifiable.

---

## Section 2 — No-Go Registry Check (REQUIRED)

List every entry in `no_go_registry_v1.md` that is related to this proposal. For each entry, explain specifically why this proposal differs and why the failure mode does not carry over.

If no entries apply, state: "No entries in no_go_registry_v1.md apply to this proposal. Justification: [reason]."

| No-Go Entry | Applies? | Override Justification |
|-------------|----------|----------------------|
| NG-001 Momentum Continuation | | |
| NG-002 Mean Reversion | | |
| NG-003 Age-Conditioned Continuation | | |
| NG-004 Rank-Lift Sidecar | | |
| NG-005 Public-Data Long-Only Selection Line | | |

---

## Section 3 — Dataset Index Check (REQUIRED)

List every dataset in `dataset_index_v1.md` that is relevant to this proposal. For each dataset, state whether it is being used as a source, as a benchmark, or as a validation set.

If an existing dataset already contains the features needed for this experiment, explain why new collection is required.

| Dataset | Role | Notes |
|---------|------|-------|
| feature_tape_v1 | | |
| feature_tape_v1_labels | | |
| universe_snapshot | | |
| microstructure_log | | |
| [new dataset if applicable] | | |

---

## Section 4 — Benchmark Suite Check (REQUIRED)

State the specific benchmark from `benchmark_suite_v1.md` that this experiment must beat. The benchmark is the best result from any prior experiment in the same feature family and horizon.

| Metric | Prior best (from benchmark_suite_v1) | Target for this experiment |
|--------|-------------------------------------|---------------------------|
| Mean net-proxy (best bucket) | | must exceed |
| Median net-proxy (best bucket) | | must be > 0 |
| Bootstrap 95% CI lower bound | | must be > 0 |
| Top-1 contributor share | | must be < 25% |

If this is a genuinely new feature family with no prior benchmark, state: "No prior benchmark exists for this family. Baseline is net_proxy = 0."

---

## Section 5 — Feature Definition (REQUIRED)

For each proposed feature, provide:

| Feature name | Formula / derivation | Source table(s) | No-lookahead rule | Expected coverage | Missingness risk |
|--------------|---------------------|-----------------|-------------------|-------------------|-----------------|
| | | | | | |

**No-lookahead rule:** For each feature, state explicitly:
- Entry timestamp used (must be ≤ fire_time)
- Forward timestamp used (must be > fire_time)
- Whether any forward-looking data is used in feature construction (must be NO)

---

## Section 6 — Label Definition (REQUIRED)

State the outcome label(s) to be used:

| Label | Formula | Source | Entry timestamp rule | Forward timestamp rule | Horizon |
|-------|---------|--------|---------------------|----------------------|---------|
| gross_return | (price_fwd / price_entry) - 1 | universe_snapshot | ts ≤ fire_time_epoch | ts > fire_time_epoch, within ±tolerance | |
| net_proxy | gross_return - round_trip_pct | feature_tape + universe_snapshot | | | |

If using a different label definition, justify the departure from the standard formula.

---

## Section 7 — Coverage Risk Assessment (REQUIRED)

State the expected coverage for each feature and the expected missingness pattern. If missingness is non-random (e.g., venue-correlated, like the Orca/Meteora gap in feature_tape_v1), state this explicitly and describe how it will be handled in analysis.

| Feature | Expected coverage | Missingness pattern | Non-random? | Handling |
|---------|------------------|--------------------|-----------|---------:|
| | | | | |

---

## Section 8 — Storage Estimate (REQUIRED)

| Item | Estimate |
|------|---------|
| Rows per fire | |
| Fires planned | |
| Bytes per row (estimated) | |
| Total raw storage | |
| Compressed storage (zstd, ~4:1 ratio) | |
| Impact on current disk usage | |
| Disk headroom after collection | |

If the estimated disk usage would bring the VPS above 70% used, a storage plan must be included.

---

## Section 9 — Promotion Gates (REQUIRED)

State explicitly which of the six promotion gates this experiment is designed to test, and what evidence would constitute a pass or fail for each gate.

| Gate | Description | Pass criterion | Fail criterion |
|------|-------------|---------------|---------------|
| 1 | Mean net-proxy > 0 in best bucket | mean_net > 0 | mean_net ≤ 0 |
| 2 | Median net-proxy > 0 in best bucket | median_net > 0 | median_net ≤ 0 |
| 3 | Bootstrap 95% CI lower bound > 0 | ci_lo > 0 | ci_lo ≤ 0 |
| 4 | Top-1 contributor share < 25% | top1_share < 0.25 | top1_share ≥ 0.25 |
| 5 | Conceptually distinct from abandoned families | [explain] | [explain] |
| 6 | Coverage is non-random and generalizable | [explain] | [explain] |

---

## Section 10 — Pre-Registration (REQUIRED)

State the exact analysis plan before any data is collected or examined. This section cannot be modified after collection begins.

The analysis plan must specify:
- Primary outcome metric (must be median net-proxy, not mean)
- Secondary outcome metrics
- Subgroup analyses planned (if any)
- Winsorization policy (default: p1/p99 for horizons > +5m)
- Bootstrap parameters (default: 10,000 resamples, seed=42)
- Minimum sample size required before any conclusion is drawn (default: n ≥ 150 per bucket)

---

## Section 11 — Abort Criteria (REQUIRED)

State the conditions under which this experiment will be stopped early:

| Condition | Action |
|-----------|--------|
| Disk usage exceeds 70% | Stop collection, run cleanup, resume only after disk is below 60% |
| Collection error rate > 5% per fire | Stop, diagnose, fix before resuming |
| [experiment-specific abort condition] | |

---

## Section 12 — No-Go Override Justification (if applicable)

If any no-go registry entry applies to this proposal, provide the full override justification here. This section is required if any entry in Section 2 is marked "Applies? = Yes."

---

## Section 13 — Implementation Notes (if applicable)

Brief notes on implementation approach. Do not include code here. Code is written only after the proposal is approved.

---

## Approval

| Role | Name | Date | Decision |
|------|------|------|---------|
| Proposer | | | Submitted |
| Reviewer | | | Approved / Rejected / Revise |

**If rejected:** State the reason and required revisions before resubmission.
