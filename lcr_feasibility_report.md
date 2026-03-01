# LCR Feasibility Report: `large_cap_ray` Research Lane

**Generated:** 2026-03-01 17:18 UTC

**Experiment Goal:** Test whether the `large_cap_ray` lane (existing, high-liquidity tokens on Raydium/Orca) is a more viable arena for the current strategy model than the `pumpfun_mature` lane.

**Methodology:** A 100-tick feasibility simulation was run against historical microstructure data from the last 30 days. The simulation used the exact same v1.25 strategy gates, with one single change: `ALLOWED_LANES` was set to `{"large_cap_ray"}` only.

---

## A. Feasibility Analysis

The `large_cap_ray` lane shows significantly higher feasibility than the current `pumpfun_mature` run.

| Metric                      | `large_cap_ray` (Simulated) | `pumpfun_mature` (Live, last 100 ticks) |
|:----------------------------|:---------------------------:|:---------------------------------------:|
| **% Ticks Tradeable >= 2**  | **36.0%**                   | 9.0%                                    |
| **% Ticks Tradeable >= 1**  | **65.0%**                   | 14.0%                                   |
| **Avg Tradeable / Tick**    | **1.54**                    | 0.33                                    |
| **Opens / 100 Fires**       | **65**                      | 6                                       |

**Primary Block Reasons (`large_cap_ray`):**

The main blockers are the hard economic gates, not strategy-specific logic. This indicates the universe is broad, but the strategy is selective.

| Reason         | % of Blocks |
|:---------------|------------:|
| `lane:vol_h1`  | 37.0%       |
| `lane:vol_24h` | 36.5%       |
| `lane:not_allowed` | 17.9%       |
| `rug`          | 6.8%        |
| `anti_chase`   | 1.6%        |

---

## B. Top Candidates

The candidate pool is dominated by well-known, high-liquidity tokens. The `rug:sell_ratio` block reason is a false positive for these tokens, as their high transaction volume can temporarily skew the 5-minute sell ratio during normal volatility.

| Symbol   | Venue   | Age (h) | Vol/h ($) | Liq ($)     | Tradeable Freq. | Top Block Reason      |
|:---------|:--------|--------:|----------:|------------:|:---------------:|:----------------------|
| **$WIF** | raydium | 19965   | 15,623    | 4,833,864   | 46%             | `rug:sell_ratio=1.00` |
| **BOME** | raydium | 17218   | 15,718    | 8,745,783   | 50%             | `rug:sell_ratio=1.00` |
| **POPCAT**| raydium | 19436   | 6,252     | 3,104,291   | 20%             | `rug:sell_ratio=1.00` |
| **Bonk** | orca    | 15848   | 343       | 882,146     | 77%             | `rug:sell_ratio=0.88` |
| **WETH** | orca    | 28551   | 995,109   | 6,994,796   | 58%             | `rug:sell_ratio=1.00` |
| **Pnut** | raydium | 11666   | 3,391     | 2,696,618   | 11%             | `lane:vol_24h`        |

---

## C. Decision

**VERDICT: PROCEED**

The `large_cap_ray` lane demonstrates materially better feasibility than the current `pumpfun_mature` run, meeting the decision rule criteria:

*   **`% ticks tradeable>=2`**: **36.0%** (vs. 9.0% for current run, target was >=15%)
*   **`Opens / 100 fires`**: **65** (vs. 6 for current run)

**Recommendation:** Proceed to a paired-delta evaluation on the `large_cap_ray` lane. This involves running the `et_shadow_trader_lcr.py` script live on the VPS to gather real-time performance data.
