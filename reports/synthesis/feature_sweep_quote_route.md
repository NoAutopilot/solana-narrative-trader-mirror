# Feature Sweep: Quote / Route Quality Family
**Track A — Full-Coverage Features**
run_id: feature_tape_v1 (bb7244cd clean run)
n_rows: 1,756 | n_fires: 42 | as of 2026-03-11T11:00Z

---

## IMPORTANT SCOPE NOTE

feature_tape_v1 does **not** store forward outcomes (net_5m, delta_5m).
This report analyzes **distributional and structural properties** of the quote/route features only.
Monotonicity with forward returns cannot be assessed until a forward-outcome join is available.

---

## 1. COVERAGE

| Feature | Coverage | Source |
|---|---|---|
| jup_vs_cpamm_diff_pct | 100.0% | universe_snapshot |
| round_trip_pct | 100.0% | universe_snapshot |
| impact_buy_pct | 100.0% | universe_snapshot |
| impact_sell_pct | 100.0% | universe_snapshot |

All four features have perfect coverage. No missingness.

---

## 2. DISTRIBUTIONS

| Feature | n | Mean | Median | Std | P25 | P75 |
|---|---|---|---|---|---|---|
| jup_vs_cpamm_diff_pct | 1,756 | 0.2684 | 0.2660 | 0.0177 | 0.2529 | 0.2780 |
| round_trip_pct | 1,756 | 0.0052 | 0.0051 | 0.0002 | 0.0050 | 0.0052 |
| impact_buy_pct | 1,756 | 0.0026 | 0.0026 | 0.0001 | 0.0025 | 0.0026 |
| impact_sell_pct | 1,756 | 0.0026 | 0.0026 | 0.0001 | 0.0025 | 0.0026 |

**Observations:**
- `round_trip_pct`, `impact_buy_pct`, `impact_sell_pct` are extremely tight distributions with very low variance. They are essentially a function of liquidity and pool type — not independent signals.
- `jup_vs_cpamm_diff_pct` has more variance (std=0.0177) and is the most structurally interesting feature.

---

## 3. TERCILE ANALYSIS

| Feature | Bottom Tercile Mean | Top Tercile Mean | Tercile Diff |
|---|---|---|---|
| jup_vs_cpamm_diff_pct | 0.2517 | 0.2883 | **+0.0367** |
| round_trip_pct | 0.0050 | 0.0054 | +0.0004 |
| impact_buy_pct | 0.0025 | 0.0027 | +0.0002 |
| impact_sell_pct | 0.0025 | 0.0027 | +0.0002 |

The tercile spread for `jup_vs_cpamm_diff_pct` is meaningful (+3.67pp). For the other three features, the spread is negligible.

---

## 4. BY LANE (inferred from pool_type + pumpfun_origin)

**jup_vs_cpamm_diff_pct:**
| Lane | n | Mean | Median |
|---|---|---|---|
| other_pumpswap (mature_pumpswap) | 1,082 | 0.2776 | 0.2752 |
| large_cap_ray | 330 | 0.2526 | 0.2524 |
| other_orca | 237 | 0.2521 | 0.2521 |
| other_meteora | 63 | 0.2520 | 0.2520 |

PumpSwap tokens have materially higher Jupiter-vs-CPAMM spread (~2.5pp higher than other venues). This is structural — PumpSwap pools have lower liquidity depth and the Jupiter router finds a larger arbitrage gap.

**round_trip_pct / impact_buy_pct / impact_sell_pct:** All near-identical across lanes. These are essentially constant for a given liquidity level.

---

## 5. CORRELATIONS WITH LIQUIDITY AND AGE

| Feature | rho_liquidity | p | rho_age | p | rho_vol_h1 | p |
|---|---|---|---|---|---|---|
| jup_vs_cpamm_diff_pct | **-0.880** | <0.001 | -0.764 | <0.001 | +0.146 | <0.001 |
| round_trip_pct | **-0.995** | <0.001 | -0.800 | <0.001 | +0.101 | <0.001 |
| impact_buy_pct | **-0.994** | <0.001 | -0.803 | <0.001 | +0.107 | <0.001 |
| impact_sell_pct | **-0.994** | <0.001 | -0.801 | <0.001 | +0.098 | <0.001 |

**Critical finding:** `round_trip_pct`, `impact_buy_pct`, and `impact_sell_pct` are almost perfectly correlated with liquidity (rho = -0.994 to -0.995). They are not independent features — they are essentially a monotone transformation of liquidity_usd. Using them as features in a model would be nearly identical to using liquidity directly.

`jup_vs_cpamm_diff_pct` has a strong but not perfect correlation with liquidity (rho = -0.880) and retains some independent variance, particularly driven by pool_type (PumpSwap vs others).

---

## 6. ASSESSMENT

| Feature | Independent Signal? | Usable as Selection Feature? | Notes |
|---|---|---|---|
| jup_vs_cpamm_diff_pct | **YES** (partial) | Possibly — but no forward outcome yet | Mostly a function of liquidity + pool_type; PumpSwap premium is structural |
| round_trip_pct | NO | No — redundant with liquidity | rho_liq = -0.995 |
| impact_buy_pct | NO | No — redundant with liquidity | rho_liq = -0.994 |
| impact_sell_pct | NO | No — redundant with liquidity | rho_liq = -0.994 |

**Bottom line:** The quote/route quality family as currently captured provides **one potentially useful feature** (`jup_vs_cpamm_diff_pct`) and **three redundant features** that are near-perfect proxies for liquidity. Forward outcome data is required before any of these can be evaluated as selection signals.

---

## 7. RECOMMENDATION

**HOLD — FORWARD OUTCOME DATA REQUIRED**

The quote/route features are structurally clean and fully covered, but they cannot be evaluated as selection signals without forward return data. The feature_tape_v1 collection must be extended to capture net_5m outcomes (or joined to a forward price table) before a meaningful sweep can be run.

`jup_vs_cpamm_diff_pct` is the only candidate worth testing further. The other three are redundant with liquidity and should be dropped from future model consideration unless a specific non-liquidity use case is identified.
