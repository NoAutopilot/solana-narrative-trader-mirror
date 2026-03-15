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

## Entry 003 — PFM Reversion Observer (in progress)
**run_id:** `99ed0fd1`
**Family:** `pfm_reversion_observer_v1`
**Lane:** `pumpfun_mature`
**Direction:** reversion
**Classification:** `ACCUMULATING` (n=20 of 50 required for decision)

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with the most negative recent 5-minute momentum (`entry_r_m5 < 0`, signal) outperforms the token with non-negative momentum (`entry_r_m5 >= 0`, control) at a +5 minute horizon.

### Current metrics (ALL_COMPLETED_VIEW, n=20)

| Metric | Value |
|--------|-------|
| n_pairs_complete_5m | 20 |
| mean_delta_+5m | +0.003549 |
| median_delta_+5m | +0.003377 |
| mean_signal_net_+5m | −0.045398 |
| mean_control_net_+5m | −0.048946 |
| entry_coverage | 100% |
| row_valid | 100% |

### Notes
Early data quality is clean. Relative delta is mildly positive but n is too small for classification. Decision checkpoint at n=50.

---

## Entry 003 — PFM Reversion Observer (FINAL)
**run_id:** `99ed0fd1`
**Family:** `pfm_reversion_observer_v1`
**Lane:** `pumpfun_mature`
**Direction:** reversion
**Final classification:** `INCONCLUSIVE / ABANDONED`
**Stopped:** 2026-03-10T14:15Z

### Hypothesis tested
> Among matched token pairs in the `pumpfun_mature` lane, the token with the most negative recent 5-minute momentum (`entry_r_m5 < 0`, signal) outperforms the token with non-negative momentum (`entry_r_m5 >= 0`, control) at a +5 minute horizon via mean reversion.

### Final metrics (n=208 complete pairs)

| Metric | Value |
|---|---|
| n_pairs_complete_5m | 208 |
| mean_signal_net_+5m | ~−0.030 |
| mean_control_net_+5m | ~−0.035 |
| mean_delta_+5m | mildly positive |
| absolute net | negative throughout |

### Durable learnings
1. **Reversion hypothesis not confirmed.** The signal token lost less than the control on average, but both lost money. Mean reversion did not produce positive absolute expected value at +5m.
2. **The pumpfun_mature lane has persistently negative mean markout at +5m.** Both continuation and reversion branches confirm this. The lane itself is the problem, not the direction of the signal.
3. **Relative delta without positive absolute net is not a tradeable edge.** This reinforces Entry 001 learning #1.

---

## Entry 004 — LCR Rank-Lift Sidecar
**run_id:** `bb7244cd`
**Family:** `lcr_rank_lift_sidecar_v1`
**Lane:** `large_cap_ray`
**Direction:** rank-lift (feature selection over baseline scorer)
**Final classification:** `NON-BINDING / LOW INCREMENTAL VALUE`
**Stopped:** 2026-03-10T21:00Z

### Hypothesis tested
> Among large_cap_ray candidates with r_m5 > 0, the highest-scoring token (promoted choice) outperforms the baseline top-1 at +5m.

### Final metrics (n=19 fires)

| Metric | Value |
|---|---|
| n_fires_total | 19 |
| n_same_token | 18 (94.7%) |
| n_distinct_promotions | 1 (5.3%) |
| same_token_rate | 94.7% |
| mean_lift_+5m (all) | −0.045 |
| mean_lift_+5m (distinct only) | −0.227 (n=1, not interpretable) |

### Trigger decomposition
- NO_FEATURE_IN_TOP3: 16/19 fires (84.2%) — r_m5 > 0 gate not satisfied
- DISTINCT_PROMOTION: 1/19 fires (5.3%)
- BASELINE_ALREADY_FEATURED: 0/19 fires

### Durable learnings
1. **The r_m5 > 0 gate is almost never satisfied in live market conditions.** In 16 of 19 fires, no large_cap_ray candidate had positive r_m5. The feature trigger rate is too low to be informative.
2. **The retrospective sweep revealed that r_m5 continuation is negatively correlated with +5m outcome in the lcr_cont signal population** (ρ = −0.144, p = 0.010). The rank-lift sidecar's core assumption was wrong.
3. **A feature that rarely triggers cannot be evaluated.** At 5.3% trigger rate, reaching n=15 distinct promotions would require ~300 fires (~75 hours). Not worth the observation cost.
4. **Trigger rate must be estimated before deploying a rank-lift sidecar.** Pre-deployment analysis of how often the feature condition is satisfied in the live universe is necessary.

---

## Entry 005 — Momentum/Reversion Family — Final Synthesis
**Date:** 2026-03-10
**Decision:** FAMILY ABANDONED

### Branches covered
- LCR Continuation (`0c5337dd`): RANKING FEATURE ONLY / NOT PROMOTABLE
- PFM Continuation (`1677a7da`): RANKING FEATURE ONLY / NOT PROMOTABLE
- PFM Reversion (`99ed0fd1`): INCONCLUSIVE / ABANDONED
- LCR Rank-Lift Sidecar (`bb7244cd`): NON-BINDING / LOW INCREMENTAL VALUE

### Conclusion
> **"Current momentum/reversion family does not justify further live observers."**

### Durable learnings
1. **r_m5 continuation is not a directional edge at +5m.** It is a ranking feature at best, and is negatively correlated with outcome in the primary signal population (lcr_cont).
2. **Absolute mean net markout at +5m is negative across all branches and lanes tested.** The +5m horizon may be too short for these token types, or the signal family itself lacks edge.
3. **The only consistent cross-branch feature is entry_vol_h1** (positive ρ, consistent tercile diff), but it predicts loss reduction, not positive absolute expected value.
4. **New signal family required.** Next candidates: order-flow/imbalance, market-state/breadth, quote/impact/route-quality.

---

## Entry 006 — Age-Conditioned Continuation Retrospective Check
**Date:** 2026-03-10
**Type:** Retrospective subgroup analysis (read-only, no live observer)
**Source data:** PFM Continuation observer, run_id `1677a7da`
**Final classification:** `NO-GO — OUTLIER-DRIVEN / NOT STRONG ENOUGH`

### Hypothesis tested
> Among pumpfun_mature tokens with r_m5 > 0, the oldest tercile (age > 53.8h at fire time) outperforms the non-old tercile at +5m.

### Results (n=71 old-tercile signal rows)

| Metric | Value | GO/NO-GO |
|---|---|---|
| n | 71 | PASS (≥30) |
| mean signal net +5m | +0.003455 | PASS (>0) |
| median signal net +5m | −0.024952 | **FAIL** (<0) |
| mean delta +5m | +0.021214 | PASS (>0) |
| median delta +5m | −0.000637 | **FAIL** (<0) |
| top contributor share | 12.1% | PASS (<25%) |
| 95% CI | [−0.006, +0.052] | crosses zero |

### Durable learnings
1. **Positive mean driven entirely by outlier tokens.** Doom (+0.627) and BioLLM (+0.460) account for the positive mean. The same tokens appear in the worst rows too. This is token-specific volatility, not a systematic age effect.
2. **Median is the correct primary metric for fat-tailed distributions.** The mean is misleading here. Median signal net = −0.025 and median delta = −0.001 are the true central tendency.
3. **Subgroup analysis on n=71 is insufficient to override the family-level conclusion.** The positive mean is consistent with noise from a family that has already shown no absolute edge across 5 branches.

---

## Entry 007 — Momentum / Direction Family — FINAL Synthesis
**Date:** 2026-03-10
**Decision:** FAMILY ABANDONED

### All branches
| Branch | run_id | n | Classification |
|---|---|---|---|
| LCR Continuation | `0c5337dd` | 248 | RANKING FEATURE ONLY / NOT PROMOTABLE |
| PFM Continuation | `1677a7da` | 212 | RANKING FEATURE ONLY / NOT PROMOTABLE |
| PFM Reversion | `99ed0fd1` | 208 | INCONCLUSIVE / ABANDONED |
| LCR Rank-Lift Sidecar | `bb7244cd` | 19 | NON-BINDING / LOW INCREMENTAL VALUE |
| Age-Conditioned Continuation (retro) | — | 71 | NO-GO — OUTLIER-DRIVEN |

### Exact conclusion
> **"No new live observers will be launched from this family."**

### Durable learnings
1. Relative edge without positive absolute net is not a tradeable signal.
2. r_m5 continuation is not a directional edge at +5m (negatively correlated in lcr_cont, ρ=−0.144, p=0.010).
3. Mean reversion was not confirmed either.
4. Outlier sensitivity is the primary risk in small-n subgroup analysis — median and CI are the correct primary metrics.
5. The +5m horizon may be structurally unfavorable for these token types.
6. Feature acquisition is the next priority: buy/sell imbalance, transaction acceleration, average trade size are not currently stored in observer rows.

---

## Entry 008 — Feature Tape v1 / Public-Data Long-Only Selection Line

**run_id:** `feature_tape_v1_2026_03_11`  
**Family:** `feature_tape_v1` (public-data long-only selection)  
**Direction:** long-only selection (no matched-pair control)  
**Final classification:** `CLOSED — NO NEW LIVE OBSERVER`  
**Date:** 2026-03-12

### Hypothesis tested

> Pre-fire features derived from public on-chain data (liquidity, volume, microstructure, quote/route quality, pool composition) can identify candidate tokens with positive net-proxy returns at +5m, +15m, or +30m horizons.

### Final metrics (96 fires, 4,081 rows, 3,943 analysis rows after disk-gap exclusion)

| Track | Features | Horizons | Best net mean (winsorized) | Best net median | Verdict |
|-------|---------|---------|---------------------------|-----------------|---------|
| A (full-sample) | 10 features, 100% coverage | +5m, +15m, +30m | +0.910% (breadth, +30m) | −0.400% | ALL SKIP |
| B (subset-only) | 7 features, ~78% coverage | +5m, +15m, +30m | +4.815% (r_m5, +30m, winsorized) | +1.440% | SKIP — subset-only, momentum-adjacent, CI uncomputed |

### Why not promotable

Track A fails at all horizons. Round-trip transaction costs (~0.51%) consume all gross alpha. Gross return distributions are right-skewed: means are positive in the best bucket for some features, but medians are uniformly zero or negative, indicating the mean is driven by rare large-move events rather than a consistent per-trade edge.

Track B contains one combination — `r_m5` at +30m (winsorized) — with both positive mean and positive median net-proxy. However, this result is subset-only (Orca/Meteora excluded, ~22% of universe missing non-randomly), momentum-adjacent (same structural family as the abandoned momentum observer), and the bootstrap CI was not computed for the winsorized run. This is insufficient evidence for a new live observer.

An extreme outlier (FURY token, +34,070% at +15m) dominated raw means at +15m and +30m, confirming that the median gate is essential and that the market's return distribution is highly fat-tailed.

### Durable learnings

1. **Round-trip cost is the binding constraint at short horizons.** At ~0.51% round-trip (CPAMM-based), a feature must produce a best-bucket gross mean well above 0.51% *and* a positive gross median to survive to a positive net-proxy median. No feature in the current family achieves this consistently.
2. **Median is the correct primary gate, not mean.** The gross return distribution in this market is highly right-skewed. A positive mean net-proxy with a zero or negative median indicates an outlier-driven effect, not a deployable edge.
3. **Non-random missingness in Track B invalidates generalisation.** The Orca/Meteora micro coverage gap is correlated with pool type and liquidity tier. Results from the micro-derived subset cannot be generalised to the full candidate universe without first closing the coverage gap.
4. **The momentum/direction family is exhausted.** Continuation, reversion, age-conditioned, rank-lift, and feature-tape-based momentum variants have all been tested. None produced a deployable edge. This family is permanently closed.
5. **The infrastructure built is durable.** The observer framework, feature tape pipeline, label derivation system, backup/compression/retention stack, dashboard sync policy, and GitHub workflow are all production-quality and reusable for any future feature acquisition effort.
6. **Winsorization is mandatory for fat-tailed distributions.** Raw means at +15m and +30m were dominated by a single 340x event. All future retrospective sweeps must report both raw and winsorized (p1/p99) statistics, with the winsorized result as the primary decision input.

---

## Entry 009 — Feature Tape v2 / Feature Acquisition v2 Phase Start

**run_id:** `feature_tape_v2_2026_03_12`
**Family:** `feature_tape_v2` (full-universe collection, eligible-only analysis)
**Direction:** data collection phase — no live observer
**Final classification:** `IN PROGRESS — DATA COLLECTION`
**Date started:** 2026-03-12

### What was built

Feature Tape v2 is a clean rewrite of the v1 tape, fixing all schema bugs identified in the post-v1 audit. It collects 62 columns per fire across the full scanned universe (eligible + ineligible tokens), with eligible-only rows designated as the primary analysis scope.

Key fixes over v1:

| Bug | Fix |
|-----|-----|
| `lane` always NULL | Derived at collection time from `eligible + gate_reason + pool_type` |
| Pool breadth/dispersion wrong | Computed from micro `r_m5`/`rv_5m`, not from snapshot |
| Micro NULLs stored as 0 | All micro-native fields are NULL when no micro row exists |
| Timestamp mismatch | Queries use `isoformat()` strings matching `+00:00` format in DB |
| 9 unavailable 1m-window columns | Removed entirely |

### Semantic rules ratified

1. `lane` = universe_category (not strategy lane)
2. `eligible` + `gate_reason` are explicit columns
3. Primary analysis = eligible-only; secondary = full-universe (audit)
4. Quote nulls are expected for ineligible rows
5. Market-state field scope split deferred to v3

### Durable learnings

1. **Build all cold-path infra before any data collection.** The v1 tape was collected before holdout design, benchmark pre-registration, or contract tests existed. All v2 infra was built and committed before the first fire.
2. **Pre-register everything before looking at data.** Holdout split (75/25), promotion gates (8), kill gates (6), and benchmark ceiling are all committed to GitHub before any sweep is run.
3. **Lane derivation must happen at collection time.** Relying on a source column that is always NULL silently corrupts all downstream stratification.
4. **Full-universe collection + eligible-only analysis is the correct design.** Collecting ineligible rows costs nothing and enables audit views. Restricting analysis to eligible rows prevents spam/noise from contaminating model discovery.

---

## Entry 010 — Research Memory Layer + Runbook Shipped

**run_id:** `infra_2026_03_13`
**Family:** `infrastructure`
**Direction:** documentation + process
**Final classification:** `COMPLETE`
**Date:** 2026-03-13

### What was shipped

A complete project runbook and state bundle was built and committed to GitHub.

| File | Purpose |
|------|---------|
| `reports/research/CURRENT_STATE.md` | Authoritative current state |
| `reports/research/OPERATOR_RUNBOOK_v1.md` | Step-by-step procedures |
| `reports/research/DECISION_TREE_v1.md` | All outcomes and allowed moves |
| `reports/research/ARTIFACT_MAP_v1.md` | Every file mapped to purpose |
| `reports/research/COMMAND_INDEX_v1.md` | Exact one-liner commands |
| `scripts/build_status_packet.py` | Read-only status packet generator |

### Durable learnings

1. **A project without a runbook is not a project — it is a personal notebook.** The runbook is what makes the system transferable and auditable.
2. **Decision trees prevent scope creep.** Enumerating all allowed next moves in advance makes it impossible to drift into unapproved experiments.
3. **The artifact map is the most underrated document.** Without it, the repo becomes a graveyard of files with no clear ownership or purpose.

---

## Entry 011 — Feature Tape v2 / Feature Acquisition v2 — FINAL Closure

**run_id:** `feature_tape_v2_2026_03_12`
**Family:** `feature_acquisition_v2`
**Direction:** long-only selection
**Final classification:** `CLOSED — NO NEW LIVE OBSERVER`
**Date:** 2026-03-15

### Hypothesis tested

An expanded feature set of 42 features derived from public on-chain data (universe_snapshot + microstructure_log) — covering order flow, trade acceleration, microstructure volatility, Jupiter routing quality, price impact, breadth, and cross-pool dispersion — can identify tokens with positive forward returns at horizons from +5m to +4h.

### Final metrics (96 fires, 4,065 eligible rows, 210 feature-horizon combinations)

| Metric | Value |
|--------|-------|
| Features tested | 42 (of 62 columns; 2 skipped) |
| Horizons tested | +5m, +15m, +30m, +1h, +4h |
| Feature-horizon combinations | 210 |
| Discovery passes | 0 |
| Holdout passes | 0 |
| Best win rate (any feature, any horizon) | ~13% |
| Median net-proxy (top quintile, typical) | -0.5% |

### Why not promotable

The signal is fundamentally weak. No feature separates future winners from the population at any horizon. The top-quintile bucket for every feature has a negative or zero median net-proxy. Round-trip cost (~0.51%) consumes all gross alpha at short horizons, and no feature identifies tokens with sufficient gross alpha at longer horizons.

### Durable learnings

1. **The public on-chain feature space is exhausted for memecoin long-only selection.** Three separate programs (momentum observers, feature tape v1, feature tape v2) have now tested overlapping and distinct features from the same two source tables. The consistent result is no viable signal. This is not a sample size issue — it is a fundamental absence of predictive power in the available data.

2. **Expanding the feature set from 17 to 42 features did not help.** Adding microstructure features (rv_5m, rv_1m, range_5m), Jupiter routing quality (jup_vs_cpamm_diff_pct), price impact (impact_buy_pct, impact_sell_pct), breadth (breadth_positive_pct), and cross-pool dispersion (pool_dispersion_r_m5) produced no improvement over the simpler v1 feature set. The additional complexity added noise, not signal.

3. **Extending horizons from +5m/+15m/+30m to include +1h and +4h did not help.** Longer horizons did not reveal hidden signal. The +4h results are weaker than +5m, not stronger, suggesting that the noise-to-signal ratio increases with time in this market.

4. **Full-universe collection with eligible-only analysis is confirmed as the correct design.** The 157 ineligible rows (3.7%) were correctly excluded from primary analysis. No signal was hiding in the ineligible population.

5. **Automated pipeline infrastructure (autopilot, freeze, sweep scripts) works but requires operational attention.** The autopilot did not complete autonomously due to the scanner gap. Manual intervention was required. The sweep scripts had timestamp format bugs (datetime() vs epoch) and column name mismatches (mint vs mint_address). Future programs should include integration tests against a frozen test DB before deployment.

6. **Disk management must be part of the operational plan.** Backup accumulation filled the disk to 100% within 24 hours of the 96-fire threshold. Retention policies must be configured and tested before any multi-day collection run.

---

### Entry 012 — Large-Cap Swing Stage A (2026-03-15)

**Context:** Tested pullback-in-uptrend and breakout-from-consolidation entries on a point-in-time large-cap Solana token universe (25 tokens, liq >= $100k, vol_h24 >= $100k, age >= 48h) at +1h/+4h/+1d horizons.

**Finding:** Neither signal produces positive expected value, even gross (before costs). The pullback signal has a gross mean near zero at +1h and negative at longer horizons. The breakout signal has too few events (N=16) and no edge beyond +1h. Simple technical patterns (SMA-based pullback, range breakout) do not capture exploitable inefficiencies in established Solana DEX tokens.

**Implication:** Time-series technical signals on larger-cap Solana tokens are unlikely to be productive. The remaining untested direction is wallet/deployer/early-buyer signals (Option C from post_v2_options.md), which would require on-chain transaction data rather than price/volume data.

---

### Entry 013 — Wallet Signal Family Is Not a Free Lunch (2026-03-15)

The "who" family (deployer recidivism, early-buyer overlap, smart-money concentration) is often cited as the next frontier after price/feature signals fail. The who_family_pilot_v1 tested this directly and found:

1. **Deployer identification is structurally blocked** for pumpfun tokens. Mint authority is revoked upon graduation, and extracting the original deployer requires custom transaction parsing infrastructure.

2. **Early-buyer overlap is anti-correlated with performance.** Stronger tokens showed zero first-10 buyer overlap (z = -3.12 vs null). This suggests that indiscriminate buying (same wallets buying everything) is associated with weaker outcomes, not stronger ones.

3. **Concentration metrics are uninformative.** No meaningful difference between winner and loser groups.

4. **The Helius Enhanced API misses many pumpfun-era transactions**, making early buyer extraction unreliable without custom indexing.

**Lesson:** Do not assume that "more exotic data = more signal." The wallet family requires heavy infrastructure investment with no prior evidence of payoff. The pilot produced the clearest negative result of any program to date.

---

### Entry 014 — Drift Perps State Study (2026-03-15)

**Finding:** Drift SOL-PERP funding rate z-scores, mark-oracle TWAP spreads, and liquidation clusters do not produce a cost-adjusted edge at +15m, +1h, or +4h horizons. Funding dislocation predicts continuation (not reversion) but the effect is too small to trade. Mark-oracle spread is structurally one-directional (persistent discount), not a tradable dislocation. Liquidation data from the Drift API is limited to ~12 hours of history, making H3 structurally untestable without a custom indexer.

**Implication:** Derivatives market structure on Drift does not offer a simple state-based signal any more than spot microstructure did. The research program has now tested spot momentum, spot microstructure, spot swing, wallet/deployer, and perps state — all NO-GO. The Solana token trading signal search is exhausted across all tested families.

---

## Entry 015 -- Meteora LP State Study Stage A

**Date:** 2026-03-15
**Program:** meteora_lp_state_stageA

**Finding:** H2 toxic flow filter at +4h passes all gates (N=844, wins_mean=+1.033%). Fee income exceeds IL proxy in 68.7% of toxic-flow events. Launch pools (H3) are systematically bad for LPs. Median LP proxy is negative in most non-toxic states.

**Key learning:** Median is the right primary metric for LP proxy studies. The toxic-flow filter is counterintuitive but mechanically sound: large price moves generate large volume, which generates large fee income.

**Action:** Stage B requires exact LP PnL data (Helius/Bitquery paid API). Do not act on Stage A proxy result alone.

---

## Entry 016 — Meteora LP Stage B: Small-Sample False Positives in DeFi Research

**Date:** 2026-03-15  
**Experiment:** 014

Stage A produced a false positive (H2 toxic flow +4h, N=844, mean +1.033%) driven by two Memehouse-SOL pools with anomalous 1-day lifespans and >5%/day fee/TVL ratios. Stage B with 38 pools and 2,365 events fully reversed the result (mean -0.278%, CI entirely negative).

**Lesson:** In Solana DeFi research, small pool universes (<20 pools) are highly susceptible to false positives from transient anomalous pools. Any Stage A result must be treated as a hypothesis, not a finding, until replicated on a 3× broader universe. The minimum viable pool universe for Meteora DLMM research is ≥30 pools with ≥30 days of history each.
