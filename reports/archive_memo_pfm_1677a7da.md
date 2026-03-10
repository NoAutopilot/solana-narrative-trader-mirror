# Final Decision Memo — PFM Continuation Observer
# run_id: 1677a7da

**Status: ARCHIVED**
**Service stopped: 2026-03-09T06:28:16 UTC**
**Service disabled: yes (will not restart on reboot)**
**Decision date: 2026-03-09**

---

## Final Canonical Metrics (View B — All Completed)

| Metric | Value |
|---|---|
| run_id | `1677a7da` |
| n_fires_total | 212 |
| n_pairs_complete_5m | 212 |
| n_fail_5m | 0 |
| row_valid | 212/212 (100%) |
| mean_delta_+5m | **+0.007804** |
| median_delta_+5m | **+0.000057** |
| % delta > 0 | 50.0% (106/212) |
| 95% CI | [−0.007806, +0.023414] |
| mean_signal_net_+5m | **−0.022255** |
| mean_control_net_+5m | **−0.030059** |
| outlier_count (|d|>=0.10) | 54 |
| top_contributor_share | 0.0383 |

---

## Final Classification

**`RANKING FEATURE ONLY / NOT PROMOTABLE`**

The PFM continuation signal (r_m5 > 0) produces a positive mean delta relative to its matched control (r_m5 < 0), but the signal token loses money in absolute terms (mean_signal_net = −0.022). The CI crosses zero. The median delta is near zero (+0.000057). No regime filter tested in the `pfm_continuation_regime_filter_sidecar_v1` produced a subgroup where mean signal net turned positive.

---

## Reason for Closure

1. Continuation did not produce a robust standalone edge. Mean delta is positive but CI crosses zero and the median is near zero.
2. Regime filter sidecar found no tested subgroup where mean signal net +5m became positive. All 10 subgroups showed negative mean signal net.
3. Continuation rescue work is low expected value. The signal is a relative ranking feature, not a directional trading signal.

---

## Regime Filter Sidecar Summary

Sidecar: `pfm_continuation_regime_filter_sidecar_v1`
Verdict: `RANKING FEATURE ONLY`
Filters tested: breadth_positive, median_r_m5_positive, signal_r_m5_strong (tercile + quintile)
Pairs with pool data: 187/212
Result: No subgroup met CONDITIONALLY VIABLE criteria (mean_sig_net > 0 AND mean_delta > 0 AND median_delta > 0).

---

## Data Quality

All data quality gates passed throughout the run:
- entry_quote_coverage: 100%
- conditional_5m_coverage: 100%
- HTTP 429 errors: 0
- row_valid: 100%

---

*Archived by: Manus AI. No code modified. Service stopped cleanly via SIGTERM.*
