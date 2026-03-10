# Preregistration Note — pfm_reversion_observer_v1

**Status: PREREGISTERED — NOT STARTED**
**Date registered: 2026-03-09**
**Trigger condition: Active PFM continuation run must be classified FALSIFY or FRAGILE/INCONCLUSIVE before this experiment may begin.**

---

## Motivation

The PFM continuation observer tests whether tokens with high recent momentum (`entry_r_m5 > 0`, signal) outperform tokens with low or negative momentum (`entry_r_m5 < 0`, control) over a +5 minute horizon. If this hypothesis is falsified or remains inconclusive, the natural counter-hypothesis is mean reversion: tokens with negative recent momentum may recover faster than tokens with positive momentum over the same horizon.

This observer is the structural inverse of the continuation observer. It uses the same framework, the same data collection infrastructure, and the same canonical reporting path.

---

## Hypothesis

> **H1:** Among matched token pairs at PumpFun continuation fires, the token with `entry_r_m5 < 0` (reversion signal) has a higher net markout at +5 minutes than the token with `entry_r_m5 >= 0` (reversion control), on average across fires.

Formally: `E[signal_net_5m - control_net_5m] > 0` where signal is defined as the lower-momentum token.

---

## Design

| Parameter | Value |
|---|---|
| Signal definition | `entry_r_m5 < 0` (negative 5-minute momentum at fire time) |
| Control definition | `entry_r_m5 >= 0` (non-negative 5-minute momentum at fire time) |
| Matching rule | Same as continuation observer: matched within the same fire event |
| Horizon | +5 minutes (primary), with +1m, +15m, +30m as secondary |
| Minimum n for classification | 50 completed pairs |
| DB table | `observer_pfm_reversion_v1` (new table, same schema as `observer_pfm_cont_v1`) |
| Observer script | `pfm_reversion_observer_v1.py` (to be created, modelled on continuation observer) |

---

## Activation Condition

This experiment **must not start** until:

1. The active PFM continuation run (`1677a7da`) is formally classified using the canonical report.
2. The classification is either `FALSIFY` or `FRAGILE / INCONCLUSIVE`.
3. If the continuation run is classified `SUPPORT` or `SUPPORTED AS RANKING FEATURE / NOT PROMOTABLE`, this experiment is deferred indefinitely.

---

## Analysis Plan

The canonical reporting script (`observer_report_pfm_cont_v1.py`) will be reused with `--run_id` pointing to the reversion run. The same three views (All Completed, Timing-Valid, Snapshot) and the same classification decision logic apply without modification.

---

## Constraints

- No implementation until activation condition is met.
- Observer logic must not be modified to accommodate this experiment.
- A new observer script and new DB table are required; these must not share state with the continuation observer.
- The regime filter sidecar (`pfm_continuation_regime_filter_sidecar_v1`) takes priority over this experiment if the continuation run is `FRAGILE / INCONCLUSIVE` rather than `FALSIFY`.

---

## Pre-specified Failure Modes

- If n < 50 after 7 calendar days of running, extend to 14 days before classifying.
- If the reversion signal also produces a negative mean delta, record as: "neither continuation nor reversion is supported at +5m; hypothesis space exhausted at this horizon."
