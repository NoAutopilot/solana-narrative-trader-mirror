# Meteora LP State Study — Stage B Summary

**Program:** meteora_lp_state_stageB  
**Date:** 2026-03-15  
**Experiment:** 014  
**Verdict:** NO-GO  
**Author:** Manus AI

---

## One-Line Verdict

> The Stage A H2 toxic-flow-filter +4h survivor is fully falsified. With 2.8× more events across a 2.5× broader pool universe, the signal reverses to a negative expected value at every threshold, in every robustness test, and in 70% of individual pools.

---

## What Was Tested

Stage B retested the sole Stage A survivor — the H2 Toxic Flow Filter at +4h horizon — using:

- **38 pools** (vs 15 in Stage A), selected from the top 120 active SOL-quote DLMM pools by fees_24h
- **2,365 events** (vs 844 in Stage A) at the primary 5% threshold
- An improved PnL model using fee/TVL ratio (rather than base_fee × estimated volume) and the exact AMM IL formula
- Eight mandatory robustness tests: tail removal (1% and 5%), pool exclusion (Memehouse and top pool), pool-level dispersion, coverage sensitivity, and threshold sensitivity at 3%, 5%, 7%, and 10%

---

## Key Numbers

| Metric | Stage A | Stage B | Change |
|--------|---------|---------|--------|
| Pools | 15 | 38 | +153% |
| Events | 844 | 2,365 | +180% |
| Winsorized mean | +1.033% | -0.278% | Reversed |
| Median | +0.080% | -0.083% | Reversed |
| CI lower bound | +0.580% | -0.325% | Reversed |
| Gates passed | 6/6 | 3/10 | Degraded |
| Thresholds passing | — | 0/4 | None |
| Pools positive median | — | 6/20 (30%) | Below threshold |

---

## Root Cause of Stage A False Positive

The Stage A positive result was driven by two Memehouse-SOL pools that were active for approximately one day each, generating anomalously high fee/TVL ratios (>5% per day). These pools contributed 35 events with mean net returns of +22–31%, which dominated the 844-event aggregate. These pools no longer exist in the active Meteora universe. The Stage A result was a false positive caused by survivorship of transient anomalous pools in a small sample.

---

## Implications

This is the sixth consecutive NO-GO result across all research programs in this cycle. The pattern across programs is consistent: Solana meme token / DeFi signals that appear positive in small samples do not replicate when the sample is expanded. The most likely explanation is that the Solana meme token space is:

1. Dominated by short-lived pools and tokens with anomalous early-life statistics
2. Highly non-stationary — what worked in one 24-hour window does not persist
3. Structurally adversarial to LP strategies due to toxic flow and rapid price moves

---

## Next Steps

No Stage C is warranted. The Meteora LP program is closed.

The operator should decide whether to:

**A)** Stop all research programs.  
**B)** Pursue a fundamentally different market structure (e.g., established CEX-listed tokens, cross-venue arbitrage, or structured products).  
**C)** Accept that the current data infrastructure (public APIs, no paid indexer) is insufficient for this market and invest in proper data before any further research.

---

## Artifacts

| File | Description |
|------|-------------|
| `reports/new_programs/meteora_lp_state_stageB_design.md` | Study design, PnL model, gates |
| `reports/new_programs/meteora_lp_state_stageB_data.md` | Data sources, pool universe, coverage |
| `reports/new_programs/meteora_lp_state_stageB_results.md` | Full results, all robustness tests |
| `reports/new_programs/meteora_lp_state_stageB_summary.md` | This document |

---

*End of Summary*
