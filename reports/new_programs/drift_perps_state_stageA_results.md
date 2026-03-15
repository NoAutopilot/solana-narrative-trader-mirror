# Drift Perps State Study — Stage A Results

**Program:** drift_perps_state_stageA
**Author:** Manus AI
**Date:** 2026-03-15

---

## 1. Overview

Twenty-seven hypothesis/horizon/cost combinations were tested across three hypotheses, three horizons (+15m, +1h, +4h), and three cost scenarios (0.02%, 0.05%, 0.10%). **Zero combinations passed all six gates.** The results are presented in full below with no hand-waving.

---

## 2. H1: Funding Dislocation — Full Results

The funding dislocation hypothesis tested whether extreme funding rate z-scores (|z| > 1.5) predict mean-reverting price moves. The signed return convention is: short when funding is extremely positive, long when extremely negative.

**N = 107 events** across all horizons (within 30-day oracle window).

| Horizon | Cost | W.Mean Gross | W.Mean Net | Median Gross | Median Net | % Pos | CI Mean Net | CI Med Net | Top-1 | Top-3 | Gates Failed |
|---------|------|-------------|------------|-------------|------------|-------|-------------|------------|-------|-------|--------------|
| +15m | 0.02% | +0.018% | -0.002% | +0.059% | +0.039% | 55.1% | [-0.073%, +0.066%] | [-0.053%, +0.080%] | 4.0% | 10.8% | G2, G4 |
| +15m | 0.05% | +0.018% | -0.032% | +0.059% | +0.009% | 55.1% | [-0.103%, +0.036%] | [-0.083%, +0.050%] | 4.0% | 10.8% | G2, G4 |
| +15m | 0.10% | +0.018% | -0.082% | +0.059% | -0.041% | 55.1% | [-0.153%, -0.014%] | [-0.133%, +0.000%] | 4.0% | 10.8% | G2, G3, G4 |
| +1h | 0.02% | -0.090% | -0.110% | -0.100% | -0.120% | 45.8% | [-0.242%, +0.014%] | [-0.223%, +0.029%] | 4.8% | 11.8% | G2, G3, G4 |
| +1h | 0.05% | -0.090% | -0.140% | -0.100% | -0.150% | 45.8% | [-0.272%, -0.016%] | [-0.253%, -0.001%] | 4.8% | 11.8% | G2, G3, G4 |
| +1h | 0.10% | -0.090% | -0.190% | -0.100% | -0.200% | 45.8% | [-0.322%, -0.066%] | [-0.303%, -0.051%] | 4.8% | 11.8% | G2, G3, G4 |
| +4h | 0.02% | -0.287% | -0.307% | -0.249% | -0.269% | 38.3% | [-0.571%, -0.051%] | [-0.608%, -0.129%] | 3.5% | 9.2% | G2, G3, G4 |
| +4h | 0.05% | -0.287% | -0.337% | -0.249% | -0.299% | 38.3% | [-0.601%, -0.081%] | [-0.638%, -0.159%] | 3.5% | 9.2% | G2, G3, G4 |
| +4h | 0.10% | -0.287% | -0.387% | -0.249% | -0.349% | 38.3% | [-0.651%, -0.131%] | [-0.688%, -0.209%] | 3.5% | 9.2% | G2, G3, G4 |

**Interpretation:** H1 shows no mean-reversion edge at any horizon. At +15m, the gross effect is near zero (0.018%). At +1h and +4h, the signed returns are **negative**, meaning the directional bet (fade the funding) actively loses money. The funding dislocation signal, if anything, predicts **continuation** rather than reversion — but even that effect is too small and noisy to be tradable. Concentration is low (good), but the signal itself is absent.

---

## 3. H2: Mark–Oracle Divergence — Full Results

The mark-oracle divergence hypothesis tested whether a meaningful spread between Drift's mark price TWAP and the Pyth oracle TWAP predicts reversion. The signed return convention is: short when mark > oracle, long when mark < oracle.

**N = 43 events** (within 30-day oracle window). All 43 events had negative spreads (mark below oracle), indicating a persistent structural discount.

| Horizon | Cost | W.Mean Gross | W.Mean Net | Median Gross | Median Net | % Pos | CI Mean Net | CI Med Net | Top-1 | Top-3 | Gates Failed |
|---------|------|-------------|------------|-------------|------------|-------|-------------|------------|-------|-------|--------------|
| +15m | 0.02% | +0.013% | -0.007% | +0.002% | -0.018% | 51.2% | [-0.102%, +0.086%] | [-0.111%, +0.073%] | 9.5% | 24.1% | G2, G3, G4 |
| +15m | 0.05% | +0.013% | -0.037% | +0.002% | -0.048% | 51.2% | [-0.132%, +0.056%] | [-0.141%, +0.043%] | 9.5% | 24.1% | G2, G3, G4 |
| +15m | 0.10% | +0.013% | -0.087% | +0.002% | -0.098% | 51.2% | [-0.182%, +0.006%] | [-0.191%, -0.007%] | 9.5% | 24.1% | G2, G3, G4 |
| +1h | 0.02% | +0.020% | +0.000% | -0.021% | -0.041% | 44.2% | [-0.140%, +0.141%] | [-0.163%, +0.096%] | 7.3% | 20.2% | G3, G4 |
| +1h | 0.05% | +0.020% | -0.030% | -0.021% | -0.071% | 44.2% | [-0.170%, +0.111%] | [-0.193%, +0.066%] | 7.3% | 20.2% | G2, G3, G4 |
| +1h | 0.10% | +0.020% | -0.080% | -0.021% | -0.121% | 44.2% | [-0.220%, +0.061%] | [-0.243%, +0.016%] | 7.3% | 20.2% | G2, G3, G4 |
| +4h | 0.02% | -0.148% | -0.168% | -0.123% | -0.143% | 46.5% | [-0.530%, +0.196%] | [-0.592%, +0.292%] | 6.4% | 17.3% | G2, G3, G4 |
| +4h | 0.05% | -0.148% | -0.198% | -0.123% | -0.173% | 46.5% | [-0.560%, +0.166%] | [-0.622%, +0.262%] | 6.4% | 17.3% | G2, G3, G4 |
| +4h | 0.10% | -0.148% | -0.248% | -0.123% | -0.223% | 46.5% | [-0.610%, +0.116%] | [-0.672%, +0.212%] | 6.4% | 17.3% | G2, G3, G4 |

**Interpretation:** H2 shows no reversion edge. The best case (+1h at 0.02% cost) has a winsorized mean net of essentially zero (+0.000%) with a wide CI spanning negative territory. The median is negative at every combination. The persistent one-directional spread (mark always below oracle) suggests a structural feature of the Drift AMM rather than a tradable dislocation. Concentration is borderline acceptable but irrelevant given the absent signal.

---

## 4. H3: Liquidation / Stress State — Full Results

The liquidation/stress hypothesis tested whether post-liquidation-cluster periods show a long-bias recovery. Due to the limited liquidation data depth (~12 hours), sample sizes are critically small.

| Horizon | Cost | N | W.Mean Gross | W.Mean Net | Median Gross | Median Net | % Pos | CI Mean Net | CI Med Net | Top-1 | Top-3 | Gates Failed |
|---------|------|---|-------------|------------|-------------|------------|-------|-------------|------------|-------|-------|--------------|
| +15m | 0.02% | 6 | -0.029% | -0.049% | -0.047% | -0.067% | 33.3% | [-0.111%, +0.022%] | [-0.135%, +0.056%] | 29.4% | 71.0% | G1, G2, G3, G4, G5 |
| +15m | 0.05% | 6 | -0.029% | -0.079% | -0.047% | -0.097% | 33.3% | [-0.141%, -0.008%] | [-0.165%, +0.026%] | 29.4% | 71.0% | G1, G2, G3, G4, G5 |
| +15m | 0.10% | 6 | -0.029% | -0.129% | -0.047% | -0.147% | 33.3% | [-0.191%, -0.058%] | [-0.215%, -0.024%] | 29.4% | 71.0% | G1, G2, G3, G4, G5 |
| +1h | 0.02% | 6 | +0.042% | +0.022% | +0.027% | +0.007% | 50.0% | [-0.099%, +0.145%] | [-0.150%, +0.209%] | 26.1% | 66.9% | G1, G4, G5 |
| +1h | 0.05% | 6 | +0.042% | -0.008% | +0.027% | -0.023% | 50.0% | [-0.129%, +0.115%] | [-0.180%, +0.179%] | 26.1% | 66.9% | G1, G2, G3, G4, G5 |
| +1h | 0.10% | 6 | +0.042% | -0.058% | +0.027% | -0.073% | 50.0% | [-0.179%, +0.065%] | [-0.230%, +0.129%] | 26.1% | 66.9% | G1, G2, G3, G4, G5 |
| +4h | 0.02% | 4 | +0.587% | +0.567% | +0.526% | +0.506% | 100% | [+0.202%, +0.935%] | [+0.130%, +1.134%] | 49.0% | 93.6% | G1, G5 |
| +4h | 0.05% | 4 | +0.587% | +0.537% | +0.526% | +0.476% | 100% | [+0.172%, +0.905%] | [+0.100%, +1.104%] | 49.0% | 93.6% | G1, G5 |
| +4h | 0.10% | 4 | +0.587% | +0.487% | +0.526% | +0.426% | 100% | [+0.122%, +0.855%] | [+0.050%, +1.054%] | 49.0% | 93.6% | G1, G5 |

**Interpretation:** H3 at +4h shows the only positive mean and median net returns in the entire study, with CIs that exclude zero. However, this result fails on two critical gates: **sample size (N=4)** and **concentration (top-1 = 49%, top-3 = 94%)**. With only 4 events, all from a 12-hour window, this is not a tradable signal — it is a single market episode. The 100% win rate across 4 events is a statistical artifact of extreme small-sample noise, not evidence of an edge.

---

## 5. Gate Summary

| Hypothesis | Horizon | Cost | G1 | G2 | G3 | G4 | G5 | G6 | Pass |
|------------|---------|------|----|----|----|----|----|----|------|
| H1 Funding | +15m | 0.02% | PASS | FAIL | PASS | FAIL | PASS | PASS | **FAIL** |
| H1 Funding | +15m | 0.05% | PASS | FAIL | PASS | FAIL | PASS | PASS | **FAIL** |
| H1 Funding | +15m | 0.10% | PASS | FAIL | FAIL | FAIL | PASS | PASS | **FAIL** |
| H1 Funding | +1h | all | PASS | FAIL | FAIL | FAIL | PASS | PASS | **FAIL** |
| H1 Funding | +4h | all | PASS | FAIL | FAIL | FAIL | PASS | PASS | **FAIL** |
| H2 Spread | +15m | all | PASS | FAIL | FAIL | FAIL | PASS | PASS | **FAIL** |
| H2 Spread | +1h | 0.02% | PASS | PASS | FAIL | FAIL | PASS | PASS | **FAIL** |
| H2 Spread | +1h | 0.05%+ | PASS | FAIL | FAIL | FAIL | PASS | PASS | **FAIL** |
| H2 Spread | +4h | all | PASS | FAIL | FAIL | FAIL | PASS | PASS | **FAIL** |
| H3 Liq | +15m | all | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | **FAIL** |
| H3 Liq | +1h | 0.02% | FAIL | PASS | PASS | FAIL | FAIL | PASS | **FAIL** |
| H3 Liq | +1h | 0.05%+ | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | **FAIL** |
| H3 Liq | +4h | all | FAIL | PASS | PASS | PASS | FAIL | PASS | **FAIL** |

**Total passing: 0 / 27**

---

## 6. Comparison to Prior Programs

| Program | Combinations Tested | Passing | Best Net Return | Verdict |
|---------|--------------------:|--------:|----------------:|---------|
| Feature Acquisition v2 | 210 | 0 | n/a | NO-GO |
| Large-Cap Swing A | 18 | 0 | -0.25% (breakout +1h) | NO-GO |
| Who Family Pilot v1 | n/a | n/a | anti-signal (z=-3.12) | NO-GO |
| **Drift Perps State A** | **27** | **0** | **+0.567% (H3 +4h, N=4)** | **NO-GO** |

The Drift study produced the only positive net return in any program (H3 +4h), but on a sample of 4 events from a single 12-hour window. This does not constitute materially stronger evidence than any prior program.
