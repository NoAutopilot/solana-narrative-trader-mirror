# Drift Perps State Study — Stage A Summary

**Program:** drift_perps_state_stageA
**Author:** Manus AI
**Date:** 2026-03-15

---

## Study Summary

This study tested whether structured state variables in the Drift Protocol SOL-PERP perpetual futures market contain any robust, cost-adjusted directional edge at short-to-medium horizons. Three hypotheses were evaluated across three horizons and three cost scenarios, yielding 27 total combinations.

**All data was sourced from the Drift Protocol public Data API.** No data was fabricated. The effective study period was 30 days (constrained by oracle price history), with funding rate data available for 90 days.

---

## Key Findings

**H1 (Funding Dislocation)** was the best-powered hypothesis with 107 events. The mean-reversion signal is absent. At +15m, the gross effect is near zero (+0.018%). At +1h and +4h, the signed returns are negative, meaning the funding-fade trade actively loses money. Extreme funding rates on Drift SOL-PERP predict continuation, not reversion — but even the continuation effect is too small and noisy to exploit.

**H2 (Mark-Oracle Divergence)** had 43 events, all with negative spreads (mark below oracle). This persistent one-directional spread suggests a structural feature of the Drift AMM pricing mechanism rather than a tradable dislocation. No reversion edge was detected at any horizon.

**H3 (Liquidation/Stress)** was severely underpowered with only 6 events (4 at +4h) due to the Drift API retaining only ~12 hours of liquidation history. The +4h results showed positive returns (mean net +0.567%, CI above zero), but this is a single market episode with extreme concentration (top-1 share = 49%). It fails the sample size gate (N=4 vs. required 30) and concentration gate decisively.

---

## Gate Results

| Metric | Value |
|--------|-------|
| Total combinations tested | 27 |
| Combinations passing all gates | 0 |
| Best-case net return | +0.567% (H3 +4h, N=4, fails G1 and G5) |
| Best adequately-powered net return | -0.002% (H1 +15m at 0.02% cost, N=107) |

No hypothesis/horizon/cost combination passed all six gates simultaneously.

---

## Comparison to Prior Programs

This is the fifth research program evaluated. None have produced a viable signal.

| Program | Core Idea | Best Evidence | Verdict |
|---------|-----------|---------------|---------|
| Momentum/Reversion | Spot meme token momentum | No edge after costs | NO-GO |
| Feature Acquisition v2 | Spot microstructure features | 0/210 passed discovery | NO-GO |
| Large-Cap Swing A | Spot pullback/breakout | Negative EV after costs | NO-GO |
| Who Family Pilot v1 | Deployer/buyer overlap | Anti-signal (z=-3.12) | NO-GO |
| **Drift Perps State A** | **Perps state variables** | **0/27 passed all gates** | **NO-GO** |

The Drift study does not provide a materially stronger reason to continue than any prior program. The only positive result (H3 +4h) is built on 4 events from a single 12-hour window and cannot be distinguished from noise.

---

## Blockers Encountered

The primary blocker was the limited depth of the Drift liquidation history API, which retains only ~12 hours of events. A full historical liquidation dataset would require a custom on-chain indexer or third-party data provider. However, even if H3 were fully powered, the H1 and H2 results (which are adequately powered) show no edge, suggesting that Drift SOL-PERP state variables do not contain a simple tradable signal at these horizons.

---

## Verdict

> **NO-GO**

There is no basis for Stage B. Zero combinations passed all gates. The adequately-powered hypotheses (H1 and H2) show no edge. The underpowered hypothesis (H3) cannot be evaluated with available data and does not justify the investment of building a custom liquidation indexer given the negative results from H1 and H2.

This research line is closed.
