# Next-Family Feature Acquisition Plan

**Date:** 2026-03-10  
**Status:** Design note only — no implementation  
**Context:** The momentum/direction family has been abandoned. This document defines the feature acquisition work needed before a new live observer can be designed.

---

## Current State

The existing observer schema stores the following pre-fire features per candidate row:

| Feature | Available | Notes |
|---|---|---|
| entry_r_m5 | Yes | Core momentum signal — family abandoned |
| entry_rv5m | Yes | Volatility proxy — weak, inconsistent |
| entry_range_5m | Yes | Intrabar range — weak, inconsistent |
| entry_vol_h1 | Yes | Volume proxy — consistent but no absolute edge |
| liquidity_usd | Yes | Market-state proxy — inconsistent |
| age_seconds | Yes | Market-state proxy — outlier-driven, no absolute edge |
| entry_price_impact_pct | Yes | Quote/impact proxy — weak, no absolute edge |

**Missing features** that are available in the scanner/microstructure pipeline but not stored in observer rows:

| Feature | Source table | Currently in observer rows? |
|---|---|---|
| buy_sell_ratio_m5 | microstructure_log | No |
| buys_m5 / sells_m5 | microstructure_log | No |
| txn_accel_m5_vs_h1 | microstructure_log | No |
| vol_accel_m5_vs_h1 | microstructure_log | No |
| avg_trade_usd_m5 | microstructure_log | No |
| liq_change_pct | microstructure_log | No |
| liq_cliff_flag | microstructure_log | No |
| jup_vs_cpamm_diff_pct | universe_snapshot | No |
| round_trip_pct | universe_snapshot | No |
| jup_slippage_pct | universe_snapshot | No |
| breadth_positive (cross-sectional) | Derived at fire time | Not computed |
| median_pool_r_m5 (cross-sectional) | Derived at fire time | Not computed |

---

## Candidate Feature Families

---

### Family A — Order-Flow / Imbalance / Urgency

**Hypothesis:** Tokens with strong buy-side dominance at fire time (high buy/sell ratio, positive signed flow, accelerating transaction rate) have higher probability of continued price appreciation at +5m.

**Rationale:** Buy/sell imbalance is a direct measure of demand pressure. Transaction acceleration captures urgency — a token being actively bought with increasing frequency is more likely to continue moving than one with flat or declining activity. This is orthogonal to momentum direction (r_m5) and tests whether the *quality* of the move matters, not just its sign.

#### Feature-by-Feature Assessment

| Feature | Currently available | Pre-fire safe? | Source | Capture method | Storage | Complexity | Expected value |
|---|---|---|---|---|---|---|---|
| buy_sell_ratio_m5 | **No** — in microstructure_log but not joined to observer rows | Yes | microstructure_log | Join at fire time using MAX(logged_at) <= fire_time per mint | Add column to observer schema | Low | **HIGH** — direct demand pressure signal |
| buys_m5 / sells_m5 (raw counts) | **No** | Yes | microstructure_log | Same join | Add columns | Low | Medium — redundant with ratio but useful for absolute volume |
| txn_accel_m5_vs_h1 | **No** — computed in microstructure_log but not stored in observer | Yes | microstructure_log | Join at fire time | Add column | Low | **HIGH** — acceleration is a leading indicator of urgency |
| vol_accel_m5_vs_h1 | **No** — same situation | Yes | microstructure_log | Join at fire time | Add column | Low | **HIGH** — volume acceleration confirms urgency |
| avg_trade_usd_m5 | **No** | Yes | microstructure_log | Join at fire time | Add column | Low | Medium — larger average trade size = more conviction |
| signed_flow_m5 (buys_m5 * vol_m5 - sells_m5 * vol_m5) | **No** — derivable | Yes | Derived from microstructure_log | Compute at join time | Add column | Low | **HIGH** — signed dollar flow is the cleanest imbalance measure |

**Priority: HIGH**

All features are already computed in the microstructure pipeline. Capture requires only adding a join step at fire time in the observer's candidate-building logic. No new data sources needed. Storage cost is minimal (6 additional float columns per candidate row).

**Lookahead risk:** None. All microstructure_log values are computed from data up to the log timestamp. The join uses MAX(logged_at) <= fire_time, which is already the B-strict pattern used for snapshot joins.

---

### Family B — Quote / Route Quality

**Hypothesis:** Tokens where the Jupiter quote closely tracks the CPAMM theoretical price (low jup_vs_cpamm_diff_pct) and where slippage is symmetric have better execution quality and are more likely to produce accurate markout estimates. Additionally, tokens with low round-trip cost are better candidates for short-horizon trading.

**Rationale:** The observer uses Jupiter quotes for both entry and forward markout. If the quote quality is poor (high slippage, large Jupiter-vs-CPAMM divergence), the markout estimate is noisy. Separately, tokens with low round-trip cost (tight spread, low impact) have a lower hurdle rate for positive net returns. This family tests whether route quality is a signal, not just a data-quality filter.

#### Feature-by-Feature Assessment

| Feature | Currently available | Pre-fire safe? | Source | Capture method | Storage | Complexity | Expected value |
|---|---|---|---|---|---|---|---|
| jup_vs_cpamm_diff_pct | **Partial** — in universe_snapshot but not joined to observer rows | Yes | universe_snapshot | Join on mint + snapshot_at | Add column | Low | **HIGH** — measures quote accuracy and pool health |
| round_trip_pct | **Partial** — in universe_snapshot | Yes | universe_snapshot | Same join | Add column | Low | **HIGH** — direct measure of execution cost |
| jup_slippage_pct | **No** — not stored anywhere currently | Yes | Jupiter API at fire time | Fetch at fire time (already done for entry quote) | Add column | Low | Medium — partially captured by entry_price_impact_pct |
| route_stability (quote variance across 2 calls) | **No** | Yes | Jupiter API | Requires 2 quote calls per candidate | Add column | Medium | Medium — useful but adds latency |
| cpamm_valid_flag | **Partial** — in universe_snapshot | Yes | universe_snapshot | Same join | Add column | Low | Medium — filter only, not a directional signal |

**Priority: MEDIUM**

jup_vs_cpamm_diff_pct and round_trip_pct are already in universe_snapshot and require only a join step. The key question is whether these are signals (predict outcome) or just quality filters (remove bad rows). The retrospective sweep found entry_price_impact_pct has a consistent positive tercile diff in pfm_cont and pfm_rev (+0.024, +0.028), suggesting lower-impact tokens do better. This family extends that finding.

**Lookahead risk:** None. All universe_snapshot values are captured before fire time.

---

### Family C — Market-State / Liquidity Dynamics

**Hypothesis:** Tokens experiencing active liquidity growth (positive liq_change_pct, no liq_cliff_flag) at fire time are in a healthier market-state and have better +5m outcomes. Cross-sectional breadth (fraction of tokens with positive r_m5 in the eligible pool) captures macro market stress.

**Rationale:** Liquidity dynamics are a leading indicator of pool health. A token with growing liquidity is attracting capital; one with declining liquidity may be in the early stages of a rug or exit. Cross-sectional breadth captures whether the broader market is risk-on or risk-off at fire time — a macro filter that could improve signal quality across all lanes.

#### Feature-by-Feature Assessment

| Feature | Currently available | Pre-fire safe? | Source | Capture method | Storage | Complexity | Expected value |
|---|---|---|---|---|---|---|---|
| liq_change_pct | **No** — in microstructure_log but not joined to observer | Yes | microstructure_log | Join at fire time | Add column | Low | **HIGH** — liquidity growth is a direct health signal |
| liq_cliff_flag | **No** — same | Yes | microstructure_log | Join at fire time | Add column | Low | Medium — binary filter, not a continuous signal |
| liq_prev_usd | **No** — same | Yes | microstructure_log | Join at fire time | Add column | Low | Low — redundant with liq_change_pct |
| breadth_positive_pct (cross-sectional) | **No** — not computed anywhere | Yes | Derived from universe_snapshot at fire time | Compute fraction of eligible tokens with r_m5 > 0 at each fire | New derived column | Medium | **HIGH** — macro regime filter; could explain variance across all branches |
| median_pool_r_m5 (cross-sectional) | **No** — not computed | Yes | Derived from universe_snapshot | Same computation | New derived column | Medium | Medium — similar to breadth but continuous |
| cross_sectional_dispersion_r_m5 | **No** — not computed | Yes | Derived from universe_snapshot | Std dev of r_m5 across eligible pool | New derived column | Medium | Medium — captures market stress/volatility |

**Priority: MEDIUM**

liq_change_pct and liq_cliff_flag are already in microstructure_log and require only a join step (same as Family A). The cross-sectional breadth features require a new computation at each fire time — the observer would need to query the universe_snapshot for all eligible tokens at fire time and compute the aggregate. This is a moderate complexity addition but has high potential value as a macro regime filter.

**Lookahead risk:** None. All values are derived from data available at or before fire time.

---

## Ranked Summary

| Priority | Family | Key features | Capture complexity | Expected value | Blocking issue |
|---|---|---|---|---|---|
| **HIGH** | A — Order-Flow / Imbalance | buy_sell_ratio_m5, txn_accel_m5_vs_h1, vol_accel_m5_vs_h1, signed_flow_m5 | **Low** — join to microstructure_log | **High** — direct demand pressure, orthogonal to r_m5 | None — data already exists |
| **MEDIUM** | B — Quote / Route Quality | jup_vs_cpamm_diff_pct, round_trip_pct | **Low** — join to universe_snapshot | Medium — extends price impact finding | None — data already exists |
| **MEDIUM** | C — Market-State / Liquidity | liq_change_pct, breadth_positive_pct | Low (liq) / Medium (breadth) | High (breadth as regime filter) | Breadth requires new computation at fire time |

---

## Implementation Sequence (when approved)

**Step 1 — Schema extension (no observer logic change)**  
Add the following columns to the observer candidate row at collection time:
- From microstructure_log join: `buy_sell_ratio_m5`, `txn_accel_m5_vs_h1`, `vol_accel_m5_vs_h1`, `avg_trade_usd_m5`, `signed_flow_m5`, `liq_change_pct`, `liq_cliff_flag`
- From universe_snapshot join: `jup_vs_cpamm_diff_pct`, `round_trip_pct`, `cpamm_valid_flag`

**Step 2 — Breadth computation (new derived feature)**  
At each fire time, query universe_snapshot for all eligible tokens and compute:
- `breadth_positive_pct` = fraction with r_m5 > 0
- `median_pool_r_m5` = median r_m5 across eligible pool
- `cross_sectional_dispersion_r_m5` = std dev of r_m5

**Step 3 — Run one full observer cycle with extended schema**  
Collect n ≥ 200 rows with the new features before designing a new observer hypothesis.

**Step 4 — Retrospective sweep on new features**  
Apply the same sweep methodology (coverage, monotonicity, tercile analysis) to the new features. Only proceed to a live observer if a feature clears the bar: positive absolute EV in top tercile, consistent sign, CI lower > 0.

---

## Decision Rule

A new live observer may be designed only after:
1. Schema extension is implemented and validated
2. At least 200 rows are collected with the new features
3. A retrospective sweep finds at least one feature with:
   - top-tercile mean signal net > 0
   - consistent sign across available branches
   - CI lower > 0 in the target stratum

If no feature clears that bar after the sweep, the program remains paused until new data sources or hypotheses are identified.

---

## What Is NOT Being Proposed

- No new live observer at this time
- No changes to the scanner or strategy
- No changes to the dashboard
- No new continuation, reversion, or rank-lift variants
- No threshold tweaks on existing features
