# Decision Memo: LCR Continuation Observer v1

**Date:** 2026-03-06  
**Run ID:** `0c5337dd-2488-4730-90b6-e371fd1e9511`  
**Classification:** SUPPORTED (relative) / NOT PROMOTABLE (absolute)  

## 1. Summary of Results (n=122)

The confirmatory run of the LCR Continuation Observer has reached its target (n=120) and definitively confirmed the hypothesis that `large_cap_ray` continuation signals hold a statistically significant edge over matched controls at a +5m horizon.

| Metric | Value |
|---|---|
| n_pairs_complete_5m | 122 |
| **mean delta +5m** | **+0.001227** |
| median delta +5m | +0.001031 |
| 95% CI (t=2.042) | **[+0.000497, +0.001957]** |
| % delta > 0 | 68.0% |

## 2. Decision Rationale

While the **relative** signal-minus-control delta is robust and the 95% CI lower bound is firmly positive (+0.000497), the **absolute** signal net markout remains negative.

- **ABSOLUTE SIGNAL MARKOUT — mean net +5m:** -0.012407
- **ABSOLUTE CONTROL MARKOUT — mean net +5m:** -0.013634

The signal is "less bad than control" in the current market environment. It is an effective ranking feature but not a standalone tradable edge for a long strategy.

## 3. Final Status

- **Strategy Promotion:** NO. The signal is not profitable as a standalone long strategy.
- **Observer Status:** STOPPED and ARCHIVED.
- **Next Action:** Read-only regime-filter sidecar analysis (`lcr_continuation_regime_filter_sidecar_v1`) to determine if specific market regimes flip absolute markout to positive.

## 4. Artifacts

- **DB:** `/root/solana_trader/data/observer_lcr_cont_v1.db`
- **Report:** `/root/solana_trader/checkpoint_report.py 120`
- **Learnings Ledger:** Entry 002 (Updated)
