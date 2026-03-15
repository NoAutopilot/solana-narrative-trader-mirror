# No-Go Registry v1

**Generated:** 2026-03-12  
**Status:** ACTIVE — enforced for all future experiment proposals  
**Rule:** No new experiment may be launched from a no-go family unless the proposal explicitly states why the no-go does not apply, with specific evidence.

---

## How to Use This Registry

Before proposing any new experiment, check every entry below. If the proposed family or hypothesis is related to any entry, the proposal must include a section titled **"No-Go Override Justification"** that:

1. Identifies which no-go entry applies.
2. Explains specifically why the new proposal differs from the failed approach.
3. Provides evidence (e.g., new data source, different horizon, different lane) that the failure mode does not carry over.

A proposal without this section will be rejected if it touches a no-go family.

---

## Entry NG-001 — Momentum Continuation Family

**Family / Hypothesis:** Among tokens with positive recent 5-minute momentum (r_m5 > 0), the signal token outperforms a matched control at +5m.

**Branches tested:**
- LCR Continuation (`0c5337dd`): large_cap_ray lane, n=248
- PFM Continuation (`1677a7da`): pumpfun_mature lane, n=212

**Why it failed:**

The continuation hypothesis was tested across two distinct lanes and failed in both. The signal token (r_m5 > 0) did not outperform the control with positive absolute net markout at +5m in either lane. The mean delta was mildly positive in some sub-periods, but the absolute mean net markout was negative throughout, meaning the strategy loses money even when it "wins" relative to the control. The r_m5 feature is negatively correlated with +5m outcome in the lcr_cont signal population (ρ = −0.144, p = 0.010), confirming that recent positive momentum is not a directional edge at this horizon.

**Exact evidence:**
- LCR Continuation: mean signal net +5m negative, median negative, CI crosses zero
- PFM Continuation: mean signal net +5m negative, median negative, CI crosses zero
- Feature sweep (Track B, r_m5, +5m): mean net +0.304% in best bucket, but median net −0.514%, CI [−0.230%, +0.859%] crosses zero
- Feature sweep (Track B, r_m5, +15m winsorized): mean net +0.048%, median −0.514%
- Feature sweep (Track B, r_m5, +30m winsorized): mean net +4.83%, median +1.96% — but subset-only (Orca/Meteora excluded), CI not computed, and the FURY token (+34,070% at +15m) distorted the entire distribution

**What evidence would be required to reopen:**
- A new data source (not universe_snapshot r_m5) that measures momentum with materially different properties (e.g., trade-level urgency, cross-venue spread, order book imbalance)
- Positive median net-proxy (not just mean) in a full-coverage, non-subset sample
- Bootstrap 95% CI lower bound > 0
- Tested on a horizon and lane not previously covered (e.g., +1h, +4h, or a new lane)
- Explicit explanation of why the new feature avoids the negative correlation documented above

---

## Entry NG-002 — Mean Reversion Family

**Family / Hypothesis:** Among tokens with negative recent 5-minute momentum (r_m5 < 0), the signal token outperforms a matched control at +5m via mean reversion.

**Branch tested:**
- PFM Reversion (`99ed0fd1`): pumpfun_mature lane, n=208 complete pairs

**Why it failed:**

The reversion hypothesis was tested in the pumpfun_mature lane. The signal token (r_m5 < 0) lost less than the control on average (mean delta mildly positive), but both the signal and control lost money in absolute terms. Mean reversion did not produce positive absolute expected value at +5m. The pumpfun_mature lane has persistently negative mean markout at +5m regardless of the direction of the entry signal — this is a lane-level problem, not a signal-level problem.

**Exact evidence:**
- n=208 complete pairs
- mean signal net +5m: ~−0.030
- mean control net +5m: ~−0.035
- mean delta: mildly positive
- absolute net: negative throughout
- Both continuation and reversion branches in pumpfun_mature confirm the lane itself is the problem

**What evidence would be required to reopen:**
- A new lane where the mean markout is not persistently negative (i.e., the baseline is not already losing)
- A reversion signal based on a different feature than r_m5 (e.g., liquidity drawdown, spread widening, order flow reversal)
- Positive absolute mean net-proxy (not just relative delta)
- Positive median net-proxy
- Bootstrap 95% CI lower bound > 0

---

## Entry NG-003 — Age-Conditioned Continuation

**Family / Hypothesis:** Among pumpfun_mature tokens with r_m5 > 0, the oldest tercile (age > 53.8h) outperforms the non-old tercile at +5m due to reduced volatility and more stable price discovery.

**Branch tested:**
- Retrospective subgroup analysis on PFM Continuation data (`1677a7da`), n=71 old-tercile signal rows

**Why it failed:**

The positive mean (+0.003455) is driven entirely by two tokens: Doom (+0.627) and BioLLM (+0.460). These same tokens appear in the worst rows as well, indicating token-specific volatility rather than a systematic age effect. The median signal net is −0.024952 and the median delta is −0.000637, both negative. The 95% CI [−0.006, +0.052] crosses zero. The subgroup n=71 is insufficient to override the family-level conclusion from 208+ pairs showing no absolute edge.

**Exact evidence:**
- n=71 (old-tercile signal rows)
- mean signal net +5m: +0.003455 (positive but outlier-driven)
- median signal net +5m: −0.024952
- mean delta +5m: +0.021214
- median delta +5m: −0.000637
- 95% CI: [−0.006, +0.052] — crosses zero
- top-1 contributor share: 12.1% (Doom token)
- Two tokens account for the entire positive mean

**What evidence would be required to reopen:**
- A new dataset where age is measured differently (e.g., time since first on-chain trade, not pair creation time)
- A lane where the baseline is not persistently negative
- n ≥ 150 in the age-conditioned subgroup
- Positive median net-proxy
- Bootstrap 95% CI lower bound > 0
- The two dominant outlier tokens (Doom, BioLLM) must not be the primary drivers

---

## Entry NG-004 — Rank-Lift Sidecar (Feature-Gated Promotion)

**Family / Hypothesis:** Among large_cap_ray candidates, a rank-lift sidecar that promotes the highest r_m5-scoring token (when r_m5 > 0) outperforms the baseline top-1 at +5m.

**Branch tested:**
- LCR Rank-Lift Sidecar (`bb7244cd`): large_cap_ray lane, n=19 fires

**Why it failed:**

The r_m5 > 0 gate was almost never satisfied in live market conditions: in 16 of 19 fires (84.2%), no large_cap_ray candidate had positive r_m5. Only 1 of 19 fires (5.3%) resulted in a distinct promotion. The retrospective sweep also confirmed that r_m5 continuation is negatively correlated with +5m outcome in the lcr_cont signal population (ρ = −0.144, p = 0.010), meaning the core assumption of the sidecar was wrong. The trigger rate was too low to evaluate at any reasonable sample size.

**Exact evidence:**
- n=19 fires total
- NO_FEATURE_IN_TOP3: 16/19 fires (84.2%) — gate not satisfied
- DISTINCT_PROMOTION: 1/19 fires (5.3%)
- mean lift +5m (all fires): −0.045
- mean lift +5m (distinct only): −0.227 (n=1, not interpretable)
- r_m5 continuation negatively correlated with outcome: ρ = −0.144, p = 0.010

**What evidence would be required to reopen:**
- A different feature gate with a pre-estimated trigger rate ≥ 20% in live conditions
- The gate feature must not be negatively correlated with the outcome in the signal population
- Pre-deployment trigger rate analysis is mandatory before any sidecar is deployed
- n ≥ 30 distinct promotions before any evaluation

---

## Entry NG-005 — Public-Data Long-Only Selection Line (Current Feature Families)

**Family / Hypothesis:** Features derived from public on-chain data (universe_snapshot, microstructure_log) can identify tokens that will produce positive net returns at +5m, +15m, or +30m horizons in a long-only selection framework.

**Branches tested:**
- Feature Tape v1 full-sample sweep: 10 Track A features × 3 horizons
- Feature Tape v1 subset-micro sweep: 7 Track B features × 3 horizons
- Total: 51 feature-horizon combinations tested

**Why it failed:**

No feature-horizon combination passes all six promotion gates simultaneously. The primary failure mode is that round-trip cost (~0.51%) consumes all gross alpha at +5m and +15m. At +30m, r_m5 (winsorized) shows positive mean and median net-proxy in the micro subset, but this result is subset-only (Orca/Meteora excluded), momentum-adjacent (same family as NG-001), and was distorted by the FURY token (+34,070% at +15m). The median across all features and horizons is zero or negative, indicating that the typical trade does not produce positive net returns.

**Exact evidence:**
- 51 feature-horizon combinations tested, 0 pass all six gates
- Best result: r_m5 at +30m (winsorized), mean net +4.83%, median net +1.96% — but subset-only and CI not computed
- Round-trip cost median: ~0.514%
- Gross median: 0.000% across virtually all features and horizons
- Feature sweep Track A: all 10 features SKIP at all horizons
- Feature sweep Track B: all 7 features SKIP at +5m and +15m; r_m5 conditional at +30m

**What evidence would be required to reopen:**
- A genuinely new data family not derived from universe_snapshot r_m5, vol_m5, or microstructure_log rolling windows
- Candidate families: trade-by-trade order flow / urgency, route / quote quality (multi-hop depth, freshness, spread), market-state gating
- Full-coverage (not subset-only) positive median net-proxy
- Bootstrap 95% CI lower bound > 0
- Tested on a holdout set not used during feature development

---

## Entry NG-006 — Feature Acquisition v2 (Full-Universe, Eligible-Only, Multi-Horizon)

**Family / Hypothesis:** An expanded feature set of 42 features derived from universe_snapshot and microstructure_log — including order-flow ratios, trade acceleration, microstructure volatility, Jupiter vs CPAMM spread, round-trip cost, price impact, breadth, and cross-pool dispersion — can identify tokens that will produce positive net returns at +5m, +15m, +30m, +1h, or +4h horizons in a long-only selection framework on Solana memecoins.

**Branches tested:**
- Feature Tape v2 full-sample sweep: 42 features x 5 horizons = 210 combinations
- Feature Tape v2 subset-micro sweep: 42 features x 5 horizons = 210 combinations
- Discovery/holdout split: 72/24 fires (75/25)

**Why it failed:**
No feature-horizon combination passed all eight promotion gates (G1-G8) in the discovery sample. The dominant failure modes were G2 (median net-proxy negative), G3/G4 (confidence interval crosses zero), and G5 (win rate below threshold). The best-bucket net proxy was consistently negative or near zero across all features and horizons. The median return in the top quintile was indistinguishable from the population median at every horizon. Round-trip cost (~0.51%) continues to consume all gross alpha at short horizons, and no feature identifies tokens with sufficient gross alpha at longer horizons to overcome this cost.

**Exact evidence:**
- 210 feature-horizon combinations tested, 0 pass all 8 gates
- Dataset: 4,065 eligible rows across 96 fires (2026-03-12T21:45Z to 2026-03-14T09:30Z)
- Best result at +5m: r_m5_micro, mean net -0.135%, median net -0.509% — FAIL (G4)
- Best result at +1h: liquidity_usd, mean net -0.389%, median net -0.517% — FAIL (G4)
- Best result at +4h: round_trip_pct, mean net -0.389%, median net -0.517% — FAIL (G4)
- Win rate across all features: 9-13% (well below 20% threshold)
- jup_vs_cpamm_diff_pct coverage: 64.7% eligible (structural null, not a bug)
- 12h data gap applied per-horizon exclusions; results unchanged with or without gap rows

**What evidence would be required to reopen:**
- A genuinely new data source not derived from universe_snapshot or microstructure_log (e.g., wallet-level flow, deployer behavior, social sentiment, cross-chain bridge data)
- A different market structure (e.g., established tokens with deeper liquidity, not memecoins)
- Pre-registered hypothesis with theoretical basis for why the new source should predict returns
- Full-coverage positive median net-proxy in discovery
- Bootstrap 95% CI lower bound > 0
- Holdout confirmation on a dataset not used during feature development
- Do NOT re-run the same 42 features with minor parameter changes

---

## NG-007 — Large-Cap Swing Stage A (Experiment 010)

| Field | Value |
|-------|-------|
| Date | 2026-03-15 |
| Program | Large-Cap Swing |
| Universe | 25 tokens, point-in-time (liq >= $100k, vol_h24 >= $100k, age >= 48h) |
| Signals | Pullback in uptrend (N=108), Breakout from consolidation (N=16) |
| Horizons | +1h, +4h, +1d |
| Cost scenarios | 0.5%, 1.0%, 1.5% |
| Scenarios tested | 18 |
| Scenarios passing | 0 |
| Root cause | Both signals produce negative expected value before costs. No edge exists in this universe/signal/horizon combination. |
| Disposition | Closed at Stage A. No Stage B. |

---

## NG-008 — Wallet / Deployer / Early-Buyer Signal Family

| Field | Value |
|-------|-------|
| Program | who_family_pilot_v1 |
| Experiment | 011 |
| Date closed | 2026-03-15 |
| Verdict | NO-GO |
| Kill reason | Anti-signal on primary hypothesis (z = -3.12); deployer identification blocked for pumpfun tokens; poor data feasibility |
| Best result | Stronger tokens showed LESS early-buyer overlap than random (z = -3.12, p = 100%) |
| Sample | 20 tokens (10 stronger, 10 weaker) from frozen 96-fire artifact |
| Data gaps | 0/20 deployer wallets identified; only 11/20 tokens yielded early buyer data |
| Recommendation | Do not pursue. No evidence of signal; structural data blockers. |

---

## NG-009: Drift Perps State Study — Stage A

| Field | Value |
|-------|-------|
| Date | 2026-03-15 |
| Experiment | 012 |
| Hypothesis | Funding dislocation, mark-oracle divergence, liquidation/stress in Drift SOL-PERP |
| Combinations Tested | 27 (3 hypotheses × 3 horizons × 3 costs) |
| Passing | 0 |
| Best Result | H3 +4h: +0.567% net, but N=4 and top-1=49% |
| Kill Reason | No edge in adequately-powered hypotheses (H1, H2). H3 underpowered (N=4) with extreme concentration. |
| Artifacts | reports/new_programs/drift_perps_state_stageA_*.md |
