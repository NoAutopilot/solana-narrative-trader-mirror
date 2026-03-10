# pfm_continuation_regime_filter_sidecar_v1 — Report

**Status: COMPLETE**
**Date: 2026-03-09**
**run_id: 1677a7da**
**Type: Read-only retrospective. No observer changes. No new runs.**

---

## Data Source

| Field | Value |
|---|---|
| PFM DB | `/root/solana_trader/data/observer_pfm_cont_v1.db` |
| Regime DB | `/root/solana_trader/data/solana_trader.db` → `microstructure_log` |
| Pool definition | `pumpfun_origin = 1`, within ±60s of `fire_time_epoch` |
| Total completed pairs | 211 |
| Pairs with pool data | 187 |
| Pairs without pool data | 24 (excluded from regime analysis) |

The 24 pairs without pool data correspond to fire times where no `microstructure_log` rows with `pumpfun_origin=1` existed within the ±60s window. These pairs are not excluded from the full-run canonical report; they are excluded only from the regime subgroup analysis.

---

## Regime Filter Definitions (Pre-specified, Immutable)

| Filter | Definition |
|---|---|
| `breadth_positive` | >60% of pumpfun_mature pool has `r_m5 > 0` at fire time |
| `median_r_m5_positive` | Median pool `r_m5 > 0` at fire time |
| `signal_r_m5_strong` | Signal's own `entry_r_m5` >= top-tercile cutoff of pool at fire time |
| `signal_r_m5_strong_q` | Signal's own `entry_r_m5` >= top-quintile cutoff (n_pool >= 15) |

---

## Subgroup Results

| Regime Group | n | mean_sig_net | median_sig_net | mean_ctl_net | mean_delta | median_delta | % delta>0 | 95% CI |
|---|---|---|---|---|---|---|---|---|
| ALL (with pool data) | 187 | −0.019372 | −0.033755 | −0.029641 | +0.010269 | −0.000637 | 49.2% | [−0.006735, +0.027274] |
| BREADTH_POSITIVE (>60%) | 13 | −0.033318 | −0.008696 | −0.014348 | −0.018971 | +0.031071 | 69.2% | [−0.104872, +0.066931] |
| BREADTH_NEGATIVE (<=60%) | 174 | −0.018330 | −0.034671 | −0.030784 | +0.012454 | −0.003852 | 47.7% | [−0.004651, +0.029559] |
| MEDIAN_R_M5_POSITIVE (>0) | 67 | −0.031047 | −0.031423 | −0.026898 | −0.004149 | −0.000513 | 49.3% | [−0.028541, +0.020243] |
| MEDIAN_R_M5_NEGATIVE (<=0) | 120 | −0.012853 | −0.034501 | −0.031172 | +0.018320 | −0.001504 | 49.2% | [−0.004345, +0.040984] |
| SIGNAL_R_M5_TOP_TERCILE | 185 | −0.018805 | −0.033649 | −0.028800 | +0.009994 | −0.000637 | 49.2% | [−0.007161, +0.027149] |
| SIGNAL_R_M5_BOT_TERCILE | 2 | −0.071769 | −0.071769 | −0.107474 | +0.035705 | +0.035705 | 50.0% | n/a (n=2) |
| SIGNAL_R_M5_TOP_QUINTILE | 153 | −0.017552 | −0.033755 | −0.025882 | +0.008330 | −0.006681 | 47.1% | [−0.011649, +0.028308] |
| SIGNAL_R_M5_BOT_QUINTILE | 34 | −0.027560 | −0.029527 | −0.046558 | +0.018998 | +0.010129 | 58.8% | [−0.007050, +0.045046] |
| BOTH_POSITIVE (breadth+median) | 13 | −0.033318 | −0.008696 | −0.014348 | −0.018971 | +0.031071 | 69.2% | [−0.104872, +0.066931] |

---

## Decision Rule Application

**CONDITIONALLY VIABLE** requires: `mean_sig_net > 0` AND `mean_delta > 0` AND `median_delta > 0`

No subgroup meets this bar. Mean signal net is negative in every subgroup without exception.

**RANKING FEATURE ONLY** requires: `mean_delta > 0` but `mean_sig_net <= 0`

Seven subgroups meet this bar. However, in every case the median delta is negative or near zero, and the CI lower bound is negative. The positive mean delta is driven by outliers (top_contributor_share is elevated in all subgroups).

The `SIGNAL_R_M5_BOT_QUINTILE` subgroup (n=34) is the closest to viable: mean_delta=+0.019, median_delta=+0.010, pct_pos=58.8%. However, mean_sig_net=−0.028, so the signal token still loses money in absolute terms. This subgroup also has a CI that crosses zero ([−0.007, +0.045]).

The `BREADTH_POSITIVE` subgroup (n=13) has the highest pct_pos (69.2%) and a positive median delta (+0.031), but mean_delta is negative (−0.019) and n=13 is too small to be actionable. The positive median with negative mean indicates a small number of large negative outliers dominating.

---

## Key Findings

The regime filters do not rescue PFM continuation into a conditionally viable signal. Across all subgroups:

1. Mean signal net is negative in every subgroup. The signal token loses money in absolute terms regardless of regime.
2. The positive mean delta observed in the full run is present in most subgroups but is driven by outliers, not a consistent edge.
3. The `median_r_m5_positive` filter actually makes results worse (mean_delta turns negative at −0.004), suggesting continuation is weaker during rising-pool regimes, not stronger.
4. The `breadth_negative` subgroup (n=174, 93% of pairs) shows the best mean delta (+0.012) but still has a negative median and a CI that crosses zero.
5. The `signal_r_m5_bot_quintile` subgroup is a statistical curiosity (mean_delta=+0.019, median=+0.010) but represents a reversion-like pattern within the continuation framework, not a continuation signal.

---

## Final Verdict

**`RANKING FEATURE ONLY`**

PFM continuation (r_m5 > 0 signal) is a ranking feature: it identifies tokens that lose less than their matched controls, on average. It does not identify tokens that gain in absolute terms. No regime filter tested here flips mean signal net positive. Continuation in PFM is not promotable to a live trading signal under any of the three pre-specified regime conditions.

---

## Next Steps (Per Preregistration)

Per the preregistration note for `pfm_reversion_observer_v1`:

- Activation condition: continuation classified FALSIFY or FRAGILE/INCONCLUSIVE. **Met.**
- Regime filter sidecar result: RANKING FEATURE ONLY (not CONDITIONALLY VIABLE). **Sidecar complete.**
- Therefore `pfm_reversion_observer_v1` is now eligible to be activated.

No implementation has been started. No observers have been changed.

---

*Generated: 2026-03-09. Source of truth: live DB. No code modified. No services restarted.*
