# Failure Modes — Feature Acquisition v2

**Date:** 2026-03-12
**Author:** Manus AI

---

## Purpose

This document catalogues the most likely failure modes at three stages: (1) silent collection failures in feature_tape_v2, (2) false positives in retrospective sweeps, and (3) live observer failures after passing gates. Each failure mode includes detection method and mitigation.

---

## Category 1: Silent Collection Failures (Top 5)

### F1.1 — Timestamp Mismatch Causing Empty Joins

**Description:** The snapshot query uses `isoformat()` string comparison against `snapshot_at`. If the scanner changes its timestamp format (e.g., drops the `+00:00` suffix, switches to epoch, or changes precision), the query silently returns zero rows. All snapshot-native fields become NULL, but the row is still written with micro-only data or all-NULL data.

**Detection:** Monitor `quote_source` field — if it shifts from `universe_snapshot` to `missing` for >50% of rows in a fire, the timestamp format has changed.

**Mitigation:** The 10-fire health checkpoint should verify that `quote_coverage >= 90%`. If it drops below 80%, halt collection and investigate.

### F1.2 — Micro Lookback Window Too Narrow

**Description:** `MICRO_LOOKBACK_S = 60` means the micro row must be within 60 seconds before fire time. If the microstructure scanner runs on a different schedule or experiences delays, micro rows may fall outside this window. All micro-native fields become NULL (correctly), but coverage drops silently.

**Detection:** Monitor `coverage_ratio_micro` per fire. If it drops below 60% consistently (vs the expected 70-80%), the lookback window may be too narrow.

**Mitigation:** Consider widening to 120s if micro coverage drops. Document the change as a schema amendment.

### F1.3 — Database Lock Contention

**Description:** The VPS runs multiple services writing to the same SQLite database (scanner, microstructure, feature_tape_v2). SQLite allows only one writer at a time. If the scanner holds a write lock during the feature_tape_v2 collection window, the feature tape may timeout or fail silently.

**Detection:** Monitor `duration_s` in `feature_tape_v2_fire_log`. If it exceeds 30s (vs typical ~0.02s), lock contention is occurring.

**Mitigation:** Use WAL mode (`PRAGMA journal_mode=WAL`) which allows concurrent reads during writes. Verify WAL is enabled on the VPS database.

### F1.4 — Lane Derivation Drift

**Description:** The `derive_lane()` function parses `gate_reason` strings from the scanner. If the scanner changes its gate_reason format (e.g., from "spam_flag" to "spam_detected" or "SPAM"), the lane derivation silently falls through to the `ineligible` catch-all. Rows are still written but with incorrect lane classification.

**Detection:** Monitor lane distribution per fire. If `ineligible` count increases suddenly while `spam_filtered` or other specific lanes decrease, the gate_reason format has changed.

**Mitigation:** Log a warning when `derive_lane()` falls through to the catch-all. Add the scanner's gate_reason vocabulary to the source_map documentation.

### F1.5 — Disk Space Exhaustion (Repeat of v1 Failure)

**Description:** The VPS disk filled during the v1 collection run (2026-03-11, 11:15-15:45 UTC gap, 20 fires lost). The same failure can recur if database backups, logs, or other services consume disk space.

**Detection:** The deploy instructions include a disk space check. The 10-fire checkpoint should verify `df -h` shows >2 GB free.

**Mitigation:** Implement automated log rotation. Set up a cron job to alert when disk usage exceeds 80%. The backup compression/retention policy from v1 should be active.

---

## Category 2: False Positives in Retrospective Sweeps (Top 3)

### F2.1 — Outlier-Driven Mean with Zero Median

**Description:** This is the exact failure mode of the v1 sweep. A single extreme-move token (e.g., FURY at +34,070%) inflates the mean net-proxy while the median remains zero. The mean passes the gate, but the effect is not robust.

**Detection:** The promotion gate requires BOTH mean > 0 AND median > 0 (G1 + G2). Additionally, G6 (top-1 contributor share < 0.30) catches single-token dominance.

**Mitigation:** Already addressed by the gate design. The key is to enforce the median gate strictly — no exceptions, no "close enough."

### F2.2 — Temporal Clustering of Signal

**Description:** The signal may be concentrated in a specific time window (e.g., 2 hours of high volatility) rather than distributed across the full collection period. If the discovery set happens to contain this window, the sweep passes, but the holdout (which may not contain such a window) fails — or worse, the holdout also contains a similar window by chance, and the signal appears robust but is actually regime-specific.

**Detection:** Compute per-fire mean net-proxy and check for temporal autocorrelation. If >50% of the total positive contribution comes from <10% of fires, the signal is temporally clustered.

**Mitigation:** Add a temporal concentration gate: no single 4-hour block should contribute >40% of the total positive net-proxy. This is not currently in the promotion gates and should be added.

### F2.3 — Non-Random Missingness Biasing Results

**Description:** The Orca/Meteora micro coverage gap means that micro-native features are only evaluated on Raydium/PumpSwap pools. If these pools have systematically different return distributions (e.g., higher volatility, more momentum), the sweep results are biased upward for micro-native features.

**Detection:** Compare the return distribution of micro-covered vs micro-missing rows using snapshot-native features (which are available for both). If the distributions differ significantly, the micro-native results are biased.

**Mitigation:** The promotion gate requires coverage >= 70% (G8). Additionally, the holdout evaluation should report the coverage-conditional results: "among micro-covered rows, the net-proxy is X; among all rows using snapshot fallback, the net-proxy is Y." If X >> Y, the signal is venue-specific, not general.

---

## Category 3: Live Observer Failures After Passing Gates (Top 2)

### F3.1 — Execution Slippage Exceeding Proxy Cost

**Description:** The net-proxy uses CPAMM-based `round_trip_pct` as the cost estimate. Actual execution on Solana DEXes involves additional costs: MEV (sandwich attacks), failed transaction fees, slippage beyond the CPAMM model, and priority fees during congestion. If actual costs exceed the proxy by even 0.1-0.2%, a marginally positive signal becomes negative in practice.

**Detection:** The live observer should record actual execution prices and compare to the CPAMM-based entry/exit prices. If `actual_cost - proxy_cost > 0.1%` consistently, the proxy is too optimistic.

**Mitigation:** Before live deployment, run a "paper trading" phase where the observer records intended trades but does not execute them. Compare intended prices to actual market prices at the intended execution time. If the cost gap exceeds 0.2%, the observer should not go live.

### F3.2 — Signal Decay / Regime Change

**Description:** The signal identified in the retrospective sweep may be specific to the market conditions during the collection period. Solana DEX market microstructure changes rapidly — new AMM designs, new token launch patterns, changes in MEV activity, and shifts in retail/bot trading ratios can all invalidate a signal within days.

**Detection:** The kill gates (K1-K6) are designed to catch this. Specifically, K3 (win rate < 45% after 100 pairs) and K1 (cumulative mean delta < -1.0% after 50 pairs) will trigger if the signal has decayed.

**Mitigation:** The observer should have a built-in "refresh" mechanism: after 200 pairs, re-evaluate the signal against the original promotion gates using only the live data. If the live data no longer passes the gates, the observer should auto-pause and flag for review. This is not a kill (which is permanent) but a pause (which can be resumed after investigation).

---

## Summary Table

| ID | Category | Failure Mode | Severity | Detection | Mitigation Status |
|----|----------|-------------|----------|-----------|-------------------|
| F1.1 | Collection | Timestamp mismatch | HIGH | quote_source monitoring | Implemented in health checks |
| F1.2 | Collection | Micro lookback too narrow | MEDIUM | coverage_ratio_micro | Documented, adjustable |
| F1.3 | Collection | DB lock contention | MEDIUM | duration_s monitoring | WAL mode recommended |
| F1.4 | Collection | Lane derivation drift | LOW | Lane distribution monitoring | Warning logging recommended |
| F1.5 | Collection | Disk space exhaustion | HIGH | df -h checks | Cron alert recommended |
| F2.1 | Sweep | Outlier-driven mean | HIGH | G1+G2+G6 gates | Implemented in gate design |
| F2.2 | Sweep | Temporal clustering | MEDIUM | Per-fire concentration | **NOT YET IN GATES — add** |
| F2.3 | Sweep | Non-random missingness bias | HIGH | Coverage-conditional reporting | Partially addressed by G8 |
| F3.1 | Live | Execution slippage | HIGH | Actual vs proxy cost tracking | Paper trading phase recommended |
| F3.2 | Live | Signal decay | HIGH | Kill gates K1-K6 | Implemented; refresh mechanism recommended |
