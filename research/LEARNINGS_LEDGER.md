# LEARNINGS LEDGER

All entries are factual and run-scoped. No prose beyond what is needed to understand the result.

---

## Entry 001 — LCR Continuation (EXP-20260303-lcr-continuation)

**Status:** SUPPORTIVE / REPLICATION REQUIRED
**run_id:** `70adb2c2-da3c-4832-a3ef-b74ba591f5f6`
**Span:** 2026-03-03T21:30Z → 2026-03-05T02:30Z (~1.21 days)
**Reclassified:** 2026-03-05 (was incorrectly marked PROMOTE)

**What was tested:**
Large-cap-ray tokens with positive 5-minute momentum (r_m5 >= 0) as signal, matched against negative-momentum controls from the same fire. Primary metric: mean signal-minus-control net markout at +5m.

**Primary metric result (n=87 complete pairs, drop-failed baseline):**

| metric | value |
|---|---|
| mean delta_5m | +0.001643 |
| median delta_5m | +0.001160 |
| % delta > 0 | 65.5% |
| 95% CI | [+0.000582, +0.002703] |
| mean signal net +5m | -0.011924 (absolute loss) |
| mean control net +5m | -0.013566 (absolute loss) |

**Why NOT promoted:**
1. Absolute signal net markout is negative (-1.19%) — this is not a deployable edge.
2. Data-quality preregistration not fully met: +5m coverage = 94.6% (threshold: ≥95%).
3. Count reconciliation gap: n_signals=98 but due=92 (6 excluded due to entry_quote_ok=0).

**Count reconciliation (n_signals=98 vs due=92):**
6 signals have `fwd_due_epoch_5m = NULL` because `entry_quote_ok = 0` — the entry quote failed so no forward quote was ever scheduled. These are correctly excluded from the coverage denominator. The 6 tokens were: FWOG (×3), $WIF, POPCAT (×2), WETH. All entry failures occurred in the first ~9 hours of the run. This is a known data-quality pattern (entry quote failures propagate to no forward quote scheduled) and is not a bug.

**Failed +5m quote investigation (5 pairs, all both-sides failed):**

| Fire time | Signal token | Control token | Failure cause |
|---|---|---|---|
| 2026-03-03T22:15Z | CHILLGUY | FWOG | HTTP 429 rate limit |
| 2026-03-03T23:45Z | FWOG | POPCAT | HTTP 429 rate limit |
| 2026-03-04T00:15Z | FWOG | Pnut | HTTP 429 rate limit |
| 2026-03-04T05:45Z | $WIF | BOME | HTTP 429 rate limit |
| 2026-03-04T13:45Z | JUP | $WIF | HTTP 429 rate limit |

All 5 failures are **both-sides** (signal and control both failed at the same fire). Cause is exclusively HTTP 429 (Jupiter API rate limiting). Failures are **not clustered by token** (5 different signal tokens, 5 different control tokens). Failures are **not clustered by venue** (4 raydium, 1 orca). Failures are **not clustered in time** (spread across 15+ hours). No systematic bias is evident — rate-limit failures appear random with respect to the hypothesis.

**Sensitivity check (fragility assessment):**

| Assumption | n | mean delta | median delta | 95% CI | CI lower > 0? |
|---|---|---|---|---|---|
| A1: drop failed (baseline) | 87 | +0.001643 | +0.001160 | [+0.000582, +0.002703] | YES |
| A2: failed = 0 | 92 | +0.001553 | +0.000813 | [+0.000547, +0.002559] | YES |
| A3: failed = worst non-outlier (−0.010705) | 92 | +0.000971 | +0.000813 | [−0.000197, +0.002140] | NO (barely) |

Result is robust under A1 and A2. Under A3 (worst-case), the CI lower bound crosses zero by a small margin (−0.000197). The effect is not fragile to random failures but is fragile to the worst-case assumption — which is expected given small n and the fact that worst-case is an extreme pessimistic bound.

**Conclusion:** Candidate effect. Positive and consistent signal-minus-control delta. Not deployable. Requires one clean confirmatory run with ≥95% coverage and fully reconciled counts.

**Next action:** Run EXP-20260305-lcr-continuation-confirmatory (same rules, new run_id, require ≥95% coverage).

---

## Entry 002 — LCR Continuation Confirmatory (EXP-20260305-lcr-continuation-conf)

**Status:** SUPPORTED (relative) / NOT PROMOTABLE (absolute)
**run_id:** `0c5337dd-2488-4730-90b6-e371fd1e9511`
**Date:** 2026-03-06

**Result Summary (n=122):**
- **mean delta +5m:** +0.001227
- **median delta +5m:** +0.001031
- **95% CI:** [+0.000497, +0.001957]
- **% delta > 0:** 68.0%
- **mean signal net +5m:** -0.012407
- **mean control net +5m:** -0.013634

**Interpretation:**
The hypothesis is confirmed: `large_cap_ray` continuation signals hold a statistically significant relative edge over matched controls. However, absolute markout remains negative across the entire dataset. The signal is a valid ranking feature but not a standalone tradable edge for a long strategy in the observed market environment.

**Decision:**
STOPPED and ARCHIVED. Not promotable as a standalone long strategy.

---

## Entry 003 — LCR Continuation Regime Sidecar v1

**Status:** COMPLETED (Read-only)
**Date:** 2026-03-06

**Goal:**
Test if specific `large_cap_ray` market regimes flip absolute signal net +5m to positive using the Entry 002 dataset.

**Regime Analysis (n=122):**
| Regime Group | n | s_net_mn | s_net_md | c_net_mn | d_mn | d_md | d>0 |
|---|---|---|---|---|---|---|---|
| ALL | 122 | -0.012407 | -0.012286 | -0.013634 | +0.001227 | +0.001031 | 68.0% |
| BREADTH_POS (>60%) | 21 | -0.012178 | -0.011066 | -0.013431 | +0.001253 | +0.002064 | 76.2% |
| MEDIAN_POS (>0) | 38 | -0.012160 | -0.012183 | -0.013577 | +0.001418 | +0.002000 | 68.4% |
| BOTH_POS | 21 | -0.012178 | -0.011066 | -0.013431 | +0.001253 | +0.002064 | 76.2% |

**Conclusion:**
No tested regime subgroup produced a positive absolute signal net +5m. While the relative delta improved slightly in positive breadth/median regimes, the absolute edge remains deeply negative.

**Decision:**
Continuation is confirmed as a ranking feature only. No standalone strategy promotion is supported even under regime filtering.

---

## Entry 004 — LCR Reversion (EXP-20260305-lcr-reversion)

**Status:** DESIGNED / NOT STARTED
**Charter:** `research/experiments/EXP-20260305-lcr-reversion/charter.md`
**Not started until:** Explicit user approval.
