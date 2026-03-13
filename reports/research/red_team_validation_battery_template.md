# Red-Team Validation Battery — Report Template

> This template is auto-populated by `scripts/red_team_validation_battery.py`.
> Do not fill manually. Shown here for review of expected output format.

---

**Candidate:** `{candidate_name}`
**Family:** `{family}`
**Horizon:** `{horizon}`
**Date:** `{timestamp}`
**Final Verdict:** `{PASS | FRAGILE | FAIL}`
**Reason:** `{final_reason}`

---

## Summary Table

| Module | Verdict | Reason |
|--------|---------|--------|
| cost_sensitivity | {verdict} | {reason} |
| concentration_sensitivity | {verdict} | {reason} |
| robust_summary | {verdict} | {reason} |
| missingness_sensitivity | {verdict} | {reason} |
| temporal_stability | {verdict} | {reason} |
| placebo_null | {verdict} | {reason} |
| benchmark_nogo | {verdict} | {reason} |

---

## Module 1: Cost Sensitivity

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Scenario | Median | Mean |
|----------|--------|------|
| gross | {value} | {value} |
| net_proxy | {value} | {value} |
| net-25bps | {value} | {value} |
| net-50bps | {value} | {value} |
| net-100bps | {value} | {value} |
| net-150bps | {value} | {value} |
| net-200bps | {value} | {value} |

---

## Module 2: Concentration Sensitivity

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Removal | Median | Mean | N Remaining |
|---------|--------|------|-------------|
| baseline | {value} | — | {n} |
| remove_top_1 | {value} | {value} | {n} |
| remove_top_3 | {value} | {value} | {n} |
| remove_top_5 | {value} | {value} | {n} |

---

## Module 3: Robust Summary Checks

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Statistic | Value |
|-----------|-------|
| Mean | {value} |
| Median | {value} |
| Trimmed mean (10%) | {value} |
| Winsorized mean (10%) | {value} |
| Bootstrap CI mean (95%) | [{lo}, {hi}] |
| Bootstrap CI median (95%) | [{lo}, {hi}] |
| N | {n} |

---

## Module 4: Missingness / Subset Sensitivity

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Population | Median | N |
|------------|--------|---|
| Full eligible | {value} | {n} |
| Covered only | {value} | {n} |
| Coverage % | {value} | — |

---

## Module 5: Temporal Stability

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Split | Median | N | Sign |
|-------|--------|---|------|
| Discovery | {value} | {n} | {+/-} |
| Holdout | {value} | {n} | {+/-} |
| Holdout first half | {value} | {n} | {+/-} |
| Holdout second half | {value} | {n} | {+/-} |
| Sign consistent | {yes/no} | — | — |

---

## Module 6: Placebo / Null Test

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Metric | Value |
|--------|-------|
| Observed median | {value} |
| Null median (mean) | {value} |
| Null median (std) | {value} |
| p-value | {value} |
| N shuffles | {n} |

---

## Module 7: Benchmark / No-Go Check

**Verdict:** `{verdict}`
**Reason:** `{reason}`

| Check | Result |
|-------|--------|
| Observed gross median | {value} |
| Benchmark best v1 | {value} |
| Beats benchmark | {yes/no} |
| No-go matches | {count} |
| No-go entries matched | {list} |

---

## Final Verdict

**{PASS | FRAGILE | FAIL}**

**Reason:** `{final_reason}`

**Decision:**
- PASS → Candidate may proceed to live observer (subject to remaining gates)
- FRAGILE → Candidate requires manual review and additional evidence before proceeding
- FAIL → Candidate is killed. Do not proceed. Log in no-go registry if novel.
