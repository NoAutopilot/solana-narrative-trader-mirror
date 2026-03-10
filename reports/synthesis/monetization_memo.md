# Monetization Memo — Cross-Run Synthesis
_Generated: 2026-03-10T14:18Z_

---

## What the data shows

All three observer branches (LCR continuation, PFM continuation, PFM reversion) share the same structural pattern:

- Positive relative delta (signal outperforms control) at +5m and sometimes +15m
- Negative absolute signal net at all horizons
- CI crossing zero in all branches
- No branch meets the full SUPPORT criteria (mean>0, median>0, CI lower>0)

This is consistent across both signal directions in the pumpfun_mature lane and the large_cap_anchor lane.

---

## Realistic next uses

### 1. Regime filter (highest priority)
The relative edge may be real but diluted by unfavorable market regimes.
A read-only retrospective sidecar testing breadth_positive and median_r_m5_positive
filters on the existing data could identify whether a regime-conditioned subgroup
has CI lower > 0. This was already attempted for PFM continuation and found no
qualifying subgroup — but has not been tested for LCR or PFM reversion.

**Verdict:** Low expected value given prior negative result on PFM continuation.
Only worth attempting if a specific regime hypothesis is pre-specified.

### 2. Ranking feature
The signal consistently ranks above the control on a relative basis.
This could be used as a tiebreaker or weighting input in a multi-signal
selection framework — not as a standalone entry signal.

**Verdict:** Viable as a component feature. Does not require a new observer.
Can be implemented as a scoring weight in the existing scanner.

### 3. Relative-value spread
If both legs could be executed simultaneously (long signal, short control),
the positive relative delta would translate to a real P&L edge.
This requires on-chain short infrastructure (e.g., perp or borrow market),
which is not currently available for pumpfun_mature tokens.

**Verdict:** Not currently executable. Revisit if short infrastructure becomes available.

### 4. Abandon family
If the ranking feature use case is not worth implementing and no regime filter
produces a qualifying subgroup, the pumpfun_mature momentum family should be
closed and resources redirected to a structurally different hypothesis
(e.g., different lane, different signal type, different horizon).

**Verdict:** Reasonable default if ranking feature is not prioritized.

---

## Recommended decision

1. Implement ranking feature weighting in scanner (low effort, no new observer).
2. Do NOT run additional live observers in the pumpfun_mature momentum family
   until a new structural hypothesis is identified.
3. If a new hypothesis is identified, preregister it before implementation.

