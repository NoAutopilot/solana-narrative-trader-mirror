# Archive Memo — pfm_reversion_observer_v1
**run_id:** 99ed0fd1
**stopped:** 2026-03-10T14:16:11 UTC
**service:** solana-pfm-rev-observer.service — STOPPED + DISABLED

---

## Final Metrics (n=102 complete pairs)

| Metric | Value |
|---|---|
| n_fires_total | 104 |
| n_pairs_complete_5m | 102 |
| n_invalid | 0 |
| entry_coverage | 100% |
| fwd_5m_coverage | 100% |
| row_valid | 100% |
| mean_delta_+5m | +0.004516 |
| median_delta_+5m | −0.000460 |
| % delta > 0 | 48.5% (49/101 at checkpoint) |
| 95% CI | [−0.012337, +0.021368] |
| mean_signal_net_+5m | −0.030402 |
| mean_control_net_+5m | −0.034918 |
| trimmed_mean (10%) | +0.003182 |
| outlier_count | 19 |
| top_contributor_share | 0.0548 |

---

## Signal / Control Definition

- **signal:** lane = pumpfun_mature AND r_m5 < 0 (most negative in pool)
- **control:** lane = pumpfun_mature AND r_m5 >= 0 (nearest match by r_m5 distance)

---

## Decision Criteria Applied

| Criterion | Required | Result |
|---|---|---|
| mean delta > 0 | YES | PASS (+0.004516) |
| median delta > 0 | YES | FAIL (−0.000460) |
| CI lower > 0 | YES | FAIL (−0.012337) |
| trimmed mean > 0 | YES | PASS (+0.003182) |
| mean signal net > 0 | YES (for PROMOTABLE) | FAIL (−0.030402) |

---

## Final Classification

**FRAGILE / INCONCLUSIVE**

Mean delta is weakly positive and trimmed mean confirms the direction is not purely driven by outliers. However, the median has flipped negative at n=101, the CI lower bound remains negative, and absolute signal net is negative throughout. The relative edge is not robust enough to justify further live accumulation or promotion.

---

## Relationship to PFM Continuation

Both PFM continuation (run_id: 1677a7da) and PFM reversion (run_id: 99ed0fd1) show the same structural pattern: weak positive relative delta, negative absolute signal net, CI crossing zero. This is consistent across both signal directions in the pumpfun_mature lane, suggesting the lane itself may not provide a promotable edge at this notional size and horizon.

---

## Next Steps

Per preregistration: no new observer branches until cross-run synthesis is complete. See synthesis reports for horizon matrix and monetization memo.
