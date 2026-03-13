# Adverse Selection Audit — Fire-to-Entry Timing

> **Question:** Did late entry timing cause the PFM observer to fail?

## 1. Entry Jitter Distribution

Entry jitter = time between fire epoch and actual entry quote timestamp.

| Metric | Signal Entry Jitter | Control Entry Jitter |
|--------|--------------------:|---------------------:|
| mean | 11.4s | 11.9s |
| median | 7.0s | 8.0s |
| p10 | 4.0s | 4.0s |
| p90 | 12.0s | 12.0s |
| std | 54.7s | — |
| min | 2s | — |
| max | 787s | — |

## 2. Forward Quote Jitter Distribution

Forward jitter = time between due epoch (+5m) and actual forward quote timestamp.

| Metric | Signal Fwd Jitter | Control Fwd Jitter |
|--------|------------------:|-------------------:|
| mean | 7.0s | 7.9s |
| median | 5.0s | 6.0s |
| p90 | 9.0s | 9.0s |

## 3. Correlation: Entry Jitter vs Delta

- Pearson correlation (signal_entry_jitter vs delta_5m): **0.0037**
- Pearson correlation (control_entry_jitter vs delta_5m): **0.0042**

Interpretation: A strong negative correlation would indicate that late entry causes worse outcomes.

> **Finding:** Correlation is near zero. Entry timing does not meaningfully predict delta outcomes.

## 4. Jitter Bucket Analysis

| Bucket | n | Mean Delta | Median Delta | Win Rate | Mean Signal Net | Mean Control Net |
|--------|--:|----------:|-----------:|--------:|--------------:|--------------:|
| <=30s | 203 | 0.0078 | -0.0006 | 49.3% | -0.0224 | -0.0302 |
| >60s | 1 | 0.0236 | 0.0236 | 100.0% | -0.0049 | -0.0285 |

## 5. Verdict

**ENTRY TIMING: NOT A FACTOR.** High-jitter pairs actually outperform low-jitter pairs by 0.0158.

The median entry jitter is 7s. This is low — the observer enters promptly after the fire signal.
