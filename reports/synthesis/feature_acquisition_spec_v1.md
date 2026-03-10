# Feature Acquisition Specification v1
**Date:** 2026-03-10
**Goal:** Collect pre-fire features for orthogonal information families.

---

## 1. Candidate Feature Families

### A. Order-Flow / Imbalance / Urgency
*Strongest candidate for finding true alpha. Measures the signed direction and velocity of market participation.*

| Feature | Source | Fire-Time Safe? | Schema Location | Complexity |
| :--- | :--- | :--- | :--- | :--- |
| **buy_sell_ratio_m5** | `microstructure_log` | YES | `observer_candidates` | LOW (join) |
| **signed_flow_m5** | `microstructure_log` | YES | `observer_candidates` | LOW (join) |
| **txn_accel_m5_vs_h1** | `microstructure_log` | YES | `observer_candidates` | LOW (join) |
| **vol_accel_m5_vs_h1** | `microstructure_log` | YES | `observer_candidates` | LOW (join) |
| **avg_trade_usd_m5** | `microstructure_log` | YES | `observer_candidates` | LOW (join) |

### B. Quote / Route Quality
*Measures market depth and route stability. Critical for identifying hidden costs and toxic flow.*

| Feature | Source | Fire-Time Safe? | Schema Location | Complexity |
| :--- | :--- | :--- | :--- | :--- |
| **jup_vs_cpamm_diff_pct**| `universe_snapshot` | YES | `observer_candidates` | LOW (join) |
| **round_trip_pct** | `universe_snapshot` | YES | `observer_candidates` | LOW (join) |
| **impact_buy_pct** | `universe_snapshot` | YES | `observer_candidates` | LOW (join) |
| **impact_sell_pct** | `universe_snapshot` | YES | `observer_candidates` | LOW (join) |

### C. Market-State / Liquidity Dynamics
*Measures the broader market environment and liquidity changes.*

| Feature | Source | Fire-Time Safe? | Schema Location | Complexity |
| :--- | :--- | :--- | :--- | :--- |
| **liq_change_pct** | `microstructure_log` | YES | `observer_candidates` | LOW (join) |
| **breadth_positive_pct** | `microstructure_log` | YES | `observer_candidates` | MEDIUM (agg) |
| **median_pool_r_m5** | `microstructure_log` | YES | `observer_candidates` | MEDIUM (agg) |

---

## 2. Implementation Notes
- **Data Source:** All features listed above are currently stored in `microstructure_log` or `universe_snapshot` on the VPS.
- **Acquisition Method:** Extend the observer's `get_candidates()` logic to perform a left-join to the relevant tables at fire time, using the latest available record for each mint address.
- **Coverage Risk:** High coverage (95%+) is expected as these tables are populated on the same cadence as the observer.

---

## 3. Next Decision Gate
“No new live observer will be launched until the new features are captured and a retrospective sweep shows at least one feature family with:
- positive mean signal net
- positive mean delta
- non-negative median
- acceptable concentration
- good coverage”
