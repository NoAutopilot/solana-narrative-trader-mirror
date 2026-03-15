# Meteora LP State Study — Stage B Results Document

**Program:** meteora_lp_state_stageB  
**Date:** 2026-03-15  
**Experiment:** 014  
**Author:** Manus AI

---

## 1. Core Result: H2 Toxic Flow Filter at +4h

The Stage A survivor was retested on the expanded 38-pool universe with the improved PnL model.

| Metric | Stage A (15 pools) | Stage B (38 pools) | Direction |
|--------|-------------------|-------------------|-----------|
| N events | 844 | 2,365 | +180% |
| Winsorized mean | +1.033% | **-0.278%** | Reversed |
| Median | +0.080% | **-0.083%** | Reversed |
| % Positive | 54.9% | **34.6%** | Reversed |
| CI mean [lo, hi] | [+0.580%, +2.909%] | **[-0.325%, -0.234%]** | Reversed |
| CI median [lo, hi] | [+0.078%, +0.082%] | **[-0.093%, -0.074%]** | Reversed |
| Top-1 share | 38.2% | 9.5% | Improved |
| Top-3 share | 67.4% | 20.5% | Improved |

**The Stage A survivor is fully reversed.** With 2.8× more events and a broader pool universe, the H2 toxic flow filter at +4h shows a **negative expected value** with a tight, entirely negative confidence interval.

---

## 2. Gate Results

| Gate | Criterion | Result | Pass? |
|------|-----------|--------|-------|
| G1 | N ≥ 50 | N = 2,365 | PASS |
| G2 | Winsorized mean > 0 | -0.278% | **FAIL** |
| G3 | Median > 0 | -0.083% | **FAIL** |
| G4 | CI lower > 0 | -0.325% | **FAIL** |
| G5 | Top-1 share < 25% | 9.5% | PASS |
| G6 | Top-3 share < 50% | 20.5% | PASS |
| G7a | Survives top-1% tail removal | -0.290% mean | **FAIL** |
| G7b | Survives top-5% tail removal | -0.339% mean | **FAIL** |
| G8a | Survives Memehouse exclusion | N/A (0 events) | N/A |
| G8b | Survives top-pool exclusion | -0.296% mean | **FAIL** |

**Gates passed: 3 / 10. Required: 10 / 10.**

---

## 3. Robustness Tests

### 3.1 Tail Removal

Removing the top 1% and top 5% of events by absolute value makes the result **worse**, not better. This indicates the positive tail events are not driving the result — the core distribution is negative.

| Test | N | Wins Mean | Median | CI Lo | Pass? |
|------|---|-----------|--------|-------|-------|
| Full sample | 2,365 | -0.278% | -0.083% | -0.325% | No |
| Excl top 1% | 2,342 | -0.290% | -0.086% | -0.337% | No |
| Excl top 5% | 2,247 | -0.339% | -0.095% | -0.386% | No |

### 3.2 Pool Exclusion

The Memehouse-SOL pools that drove the Stage A result are no longer present in the active pool universe. The top contributing pool in Stage B is U1-SOL (mean -0.022%, N=97), which is marginally negative. Excluding it makes the result slightly worse.

| Test | N | Wins Mean | Median | CI Lo | Pass? |
|------|---|-----------|--------|-------|-------|
| Full sample | 2,365 | -0.278% | -0.083% | -0.325% | No |
| Excl Memehouse | 2,365 | -0.278% | -0.083% | -0.325% | No (0 events) |
| Excl top pool (U1-SOL) | 2,268 | -0.296% | -0.090% | -0.346% | No |

### 3.3 Pool-Level Dispersion

Only 6 of 20 pools with N ≥ 10 show a positive median. The signal is not broadly distributed across the pool universe.

| Pool | N | Wins Mean | Median |
|------|---|-----------|--------|
| SOS-SOL | 80 | +1.76% | **+4.496%** |
| SHAPE-SOL | 148 | -0.38% | +0.011% |
| abcdefg-SOL | 140 | -0.53% | +0.046% |
| WhiteHouse-SOL | 160 | -0.62% | **+0.218%** |
| U1-SOL | 97 | +0.05% | +0.128% |
| LOLA-SOL | 95 | -0.13% | **+0.281%** |
| HeavyPulp-SOL | 38 | -5.75% | -1.329% |
| Punch-SOL | 178 | -0.26% | -0.083% |
| Buttcoin-SOL | 143 | -0.14% | -0.106% |
| PsyopAnime-SOL | 82 | -0.15% | -0.095% |
| WOJAK-SOL | 36 | -0.05% | -0.028% |
| Machi-SOL | 167 | -0.42% | -0.012% |
| PENGUIN-SOL | 117 | -0.13% | -0.102% |
| neet-SOL | 109 | -0.19% | -0.129% |
| KLED-SOL | 33 | -0.17% | -0.111% |
| testicle-SOL | 68 | -0.15% | -0.109% |
| Lobstar-SOL | 213 | -0.31% | -0.098% |
| WAR-SOL | 218 | -0.26% | -0.051% |
| STAR-SOL | 26 | -1.07% | -0.254% |
| gork-SOL | 192 | -1.04% | -0.233% |

**Pools positive median: 6 / 20 (30%). Required: ≥ 50%.**

SOS-SOL is the only pool showing a strong positive result (median +4.496%). This is a single-pool anomaly, not a broad signal.

### 3.4 Coverage Sensitivity

The Stage A result was driven by the Stage A pool subset. The 23 new pools added in Stage B are uniformly negative, confirming that the Stage A result was not representative.

| Pool Set | N | Wins Mean | Median |
|----------|---|-----------|--------|
| Stage A pool subset (approx) | 197 | +1.167% | -0.058% |
| Stage B new pools only | 2,168 | -0.313% | -0.088% |

Note: Even within the Stage A pool subset, the median is now -0.058%, suggesting that the Stage A pools themselves have deteriorated or that the Memehouse-SOL pools are no longer present.

### 3.5 Threshold Sensitivity

The result is negative and worsening at all four thresholds tested. Higher thresholds (more extreme toxic flow) produce worse results, not better.

| Threshold | N | Wins Mean | Median | CI Lo | Pass? |
|-----------|---|-----------|--------|-------|-------|
| 3% | 3,887 | -0.204% | -0.083% | -0.231% | No |
| 5% (primary) | 2,365 | -0.278% | -0.083% | -0.325% | No |
| 7% | 1,537 | -0.370% | -0.087% | -0.448% | No |
| 10% | 912 | -0.559% | -0.104% | -0.712% | No |

**Thresholds passing: 0 / 4.**

---

## 4. Diagnosis: Why Stage A Appeared Positive

The Stage A positive result was driven by two factors that do not represent a real edge:

1. **Memehouse-SOL pools (primary driver):** Two short-lived pools with 1 day of activity each contributed 35 events with mean net returns of +22–31%. These pools no longer exist in the active universe. Their extreme fee/TVL ratios (>5% per day) were anomalous and transient.

2. **Small pool universe (secondary factor):** With only 15 pools, the Stage A sample was dominated by the Memehouse-SOL anomaly. The 23 additional pools added in Stage B are uniformly negative, showing the Stage A universe was not representative.

The Stage A result was a **false positive caused by survivorship of anomalous short-lived pools** in a small sample.

---

## 5. Final Verdict

**VERDICT: NO-GO**

The H2 Toxic Flow Filter +4h hypothesis is falsified. The Stage A survivor does not replicate on a broader pool universe with a more conservative PnL model. The result is negative across all thresholds, all robustness tests, and 70% of individual pools.

---

*End of Results Document*
