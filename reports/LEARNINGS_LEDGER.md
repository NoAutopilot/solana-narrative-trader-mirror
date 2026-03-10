# LEARNINGS LEDGER

Canonical record of completed experiments, their outcomes, and durable learnings.
Each entry is immutable once written. Append only.

---

## Entry 001 — PFM Continuation Observer
**run_id:** `1677a7da`
**Period:** 2026-03-07T01:15Z → 2026-03-09T06:28Z (≈53 hours)
**Service:** `solana-pfm-cont-observer.service` (stopped and disabled 2026-03-09T06:28Z)
**Final classification:** `RANKING FEATURE ONLY / NOT PROMOTABLE`

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with higher recent 5-minute momentum (`entry_r_m5 > 0`, signal) outperforms the token with lower momentum (`entry_r_m5 < 0`, control) at a +5 minute horizon.

### Final metrics (canonical View B, n=212)

| Metric | Value |
|---|---|
| n_pairs_complete_5m | 212 |
| mean_delta_+5m | +0.007804 |
| median_delta_+5m | +0.000057 |
| % delta > 0 | 50.0% (106/212) |
| 95% CI | [−0.007806, +0.023414] |
| mean_signal_net_+5m | −0.022255 |
| mean_control_net_+5m | −0.030059 |

### Data quality
All gates passed: entry_coverage=100%, 5m_coverage=100%, row_valid=100%, HTTP_429=0.

### Why not promotable
The signal token outperforms its control on average, but loses money in absolute terms (mean_signal_net = −0.022). The CI crosses zero. The median delta is near zero. The relative edge is real but not large enough or consistent enough to constitute a tradeable directional signal.

### Regime filter sidecar result
`pfm_continuation_regime_filter_sidecar_v1`: tested breadth_positive, median_r_m5_positive, signal_r_m5_strong (tercile + quintile) across 187 pairs with pool data. No subgroup produced mean_signal_net > 0. Verdict: `RANKING FEATURE ONLY`.

### Durable learnings
1. **Positive relative delta ≠ promotable signal.** A signal that loses less than its control is a ranking feature, not a directional edge. Promotion requires mean_signal_net > 0.
2. **Regime filters did not rescue continuation.** The breadth and median-r_m5 filters did not improve absolute signal net. The `median_r_m5_positive` filter actually worsened mean delta (−0.004 vs +0.010 baseline), suggesting continuation is weaker during rising-pool regimes.
3. **Outlier sensitivity is high.** top_contributor_share ≈ 0.038 across all subgroups; 54/212 pairs were outliers (|delta| ≥ 0.10). The mean is driven by a fat tail, not a consistent edge.
4. **Data quality infrastructure is solid.** The observer framework, canonical report script, and reconciliation tooling all worked correctly. The reporting discrepancy (dashboard vs reconciliation) was a sample-size snapshot issue, not a data bug.
5. **Reversion hypothesis is now the natural next test.** If continuation is a ranking feature, the inverse (r_m5 < 0 signal) may produce a reversion edge. This is the next preregistered experiment.

---

## Entry 002 — LCR Continuation Observer
**run_id:** `0c5337dd-2488-4730-90b6-e371fd1e9511` (primary; 2 additional runs pooled)
**Family:** `lcr_continuation_observer_v1`
**Lane:** `lcr`
**Direction:** continuation
**Final classification:** `SUPPORTED AS RANKING FEATURE / NOT PROMOTABLE`

### Hypothesis tested
> Among matched token pairs in the `lcr` lane, the token with higher recent momentum (signal) outperforms the token with lower momentum (control) at a +5 minute horizon.

### Final metrics (ALL_COMPLETED_VIEW, n=122 primary; n=286 pooled)

| Metric | Value (primary) | Value (pooled) |
|--------|----------------|----------------|
| n_pairs_complete_5m | 122 | 286 |
| mean_delta_+5m | +0.001238 | — |
| % delta > 0 | 62.5% | — |
| mean_signal_net_+5m | −0.010902 | — |
| mean_control_net_+5m | −0.012139 | — |

### Durable learnings
1. **LCR continuation shows a persistent positive relative delta** across multiple runs, but absolute signal net is negative in all runs. The edge is real as a ranking signal only.
2. **LCR continuation is not a standalone promotable long signal at +5m.**
3. **Next branch:** Test whether LCR continuation signal can be used as a filter or ranking layer on top of another entry criterion that produces positive absolute net.

---

## Entry 003 — PFM Reversion Observer v1
**run_id:** `99ed0fd1`
**Period:** 2026-03-09T06:38Z → 2026-03-10T14:16Z
**Service:** `solana-pfm-rev-observer.service` (stopped and disabled 2026-03-10T14:16Z)
**Final classification:** `FRAGILE / INCONCLUSIVE`

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with the most negative recent 5-minute momentum (`entry_r_m5 < 0`, signal) outperforms the token with non-negative momentum (`entry_r_m5 >= 0`, control) at a +5 minute horizon.

### Final metrics (ALL_COMPLETED_VIEW, n=102)

| Metric | Value |
|---|---|
| n_pairs_complete_5m | 102 |
| mean_delta_+5m | +0.004516 |
| median_delta_+5m | −0.000460 |
| % delta > 0 | 48.5% (49/101) |
| 95% CI | [−0.012337, +0.021368] |
| mean_signal_net_+5m | −0.030402 |
| mean_control_net_+5m | −0.034918 |
| trimmed_mean (10%) | +0.003182 |
| outlier_count | 19 |
| top_contributor_share | 0.0548 |

### Data quality
All gates passed: entry_coverage=100%, 5m_coverage=100%, row_valid=100%, HTTP_429=0.

### Why fragile / inconclusive
Mean and trimmed mean are positive, but median flipped negative at n=101. CI lower bound remains negative throughout. Absolute signal net is negative at all horizons. Does not meet SUPPORT criteria (mean>0, median>0, CI lower>0).

### Durable learnings
1. **Inverting signal direction does not rescue the pumpfun_mature lane.** Both continuation (r_m5 > 0) and reversion (r_m5 < 0) show the same structural pattern: weak positive relative delta, negative absolute signal net, CI crossing zero.
2. **The +15m and +30m horizons show stronger relative signal for reversion** (mean_delta +0.020 and +0.041, median positive), but CI still crosses zero and outlier count is high. These horizons warrant attention in future experiments but are not sufficient for promotion at n=102.
3. **The pumpfun_mature lane appears to be a ranking-feature-only environment** at the tested notional size and horizons. The lane-level characteristic, not signal direction, may be the binding constraint.

---

## Entry 004 — Cross-Run Synthesis
**date:** 2026-03-10T14:18Z
**branches:** LCR continuation, PFM continuation, PFM reversion

### Horizon matrix (ALL_COMPLETED, key reliable horizons)

| Branch | Horizon | mean_delta | median_delta | CI lower | sig_net | Verdict |
|---|---|---|---|---|---|---|
| LCR Cont | +1m | +0.001162 | +0.000550 | +0.000515 | −0.012354 | SUPPORTED (relative) |
| LCR Cont | +5m | +0.001227 | +0.001031 | +0.000517 | −0.012407 | SUPPORTED (relative) |
| LCR Cont | +15m | — | — | — | — | OUTLIER-DOMINATED (discard) |
| LCR Cont | +30m | — | — | — | — | OUTLIER-DOMINATED (discard) |
| PFM Cont | +5m | +0.007804 | +0.000057 | −0.007363 | −0.022255 | FRAGILE POSITIVE |
| PFM Cont | +15m | +0.013678 | +0.002645 | −0.013336 | −0.036008 | FRAGILE POSITIVE |
| PFM Rev | +15m | +0.019543 | +0.017480 | −0.013141 | −0.019373 | FRAGILE POSITIVE |
| PFM Rev | +30m | +0.041068 | +0.038958 | −0.007770 | −0.011460 | FRAGILE POSITIVE |

### Cross-branch finding
All three branches share the same structural pattern: positive relative delta, negative absolute signal net, CI crossing zero. No branch is promotable as a standalone entry signal. The LCR lane is the only branch with CI lower > 0 (at +1m and +5m).

### Monetization options (ranked)
1. **Ranking feature weighting in scanner** — viable, low effort, no new observer needed.
2. **Regime filter sidecar** — low expected value given prior negative result on PFM continuation.
3. **Relative-value spread** — not currently executable (no short infrastructure).
4. **Abandon family** — reasonable default if ranking feature is not prioritized.

### Structural notes
- The pumpfun_mature lane consistently produces negative absolute signal net across all tested momentum directions and horizons. This is likely a lane-level characteristic.
- The LCR lane shows a cleaner and more robust relative signal at short horizons. If a new hypothesis is pursued, the LCR lane is a better starting point.
- Outlier contamination at longer horizons (+15m, +30m) is a recurring issue. Future observers should preregister an outlier gate before accumulation begins.

---
