# Dashboard Sync Policy

**Version:** 1.0  
**Effective:** 2026-03-11  
**Scope:** All experiment-affecting changes to solana-narrative-trader  
**Enforcement:** Required release gate — no change is "done" without dashboard compatibility sign-off

---

## Purpose

Silent drift between experiment logic and the operator dashboard is a reliability hazard. When counters, sample definitions, labels, or health metrics change in code but not in the dashboard, the operator sees stale or misleading data without any warning. This policy eliminates that class of failure by making dashboard compatibility a required gate on every experiment-affecting commit.

The dashboard is a monitoring and operator-awareness tool. It does **not** produce canonical results — those come from report scripts. The dashboard must accurately reflect what the canonical reports compute.

---

## RULE 1 — No Change Is Complete Without a Dashboard Compatibility Check

No experiment-affecting change to an observer, sidecar, feature tape, report script, or sample/label/counter definition is considered complete until one of the following is recorded in the change manifest:

```
dashboard_updated = yes
```
or
```
dashboard_updated = no, because no visible fields changed
```

A change that lacks this field has not passed the release gate.

---

## RULE 2 — Explicit Sign-Off Required on Every Change

Every commit that touches experiment logic must include a change manifest at:

```
reports/ops/change_manifest_<YYYYMMDDTHHMMSSZ>.md
```

The manifest must contain all required fields (see Section 5). A commit without a manifest is incomplete.

---

## RULE 3 — Mandatory Dashboard Review Triggers

Dashboard review is **mandatory** (not optional) if any of the following change:

| Category | Examples |
|----------|---------|
| Run header fields | `run_id`, `deployed_sha`, `service_active`, `now_utc` |
| Counter / n definitions | `n_fires`, `n_candidates`, `n_distinct`, `n_control`, `n_signal` |
| Sample definitions | what qualifies as a signal candidate, control candidate, or fire |
| Health metrics | coverage pct, fill rate, error rate, sidecar_fire_log outcomes |
| Primary metric labels | `r_m5`, `liq_change_pct`, `rank_lift_pct`, `jup_vs_cpamm_diff_pct` |
| Latest-fires table columns | any column shown in the fires table |
| Warning conditions | thresholds, condition logic, warning text |
| Feature coverage fields | `pool_size_total`, `pool_size_with_micro`, missingness flags |
| Any field rendered in the dashboard | if it appears on screen, it must be checked |

If none of the above change, the reviewer may record `dashboard_updated = no, because no visible fields changed` and proceed.

---

## RULE 4 — Canonical Reports Are the Source of Truth

The dashboard reads from the same DB as the canonical reports but is **not** the canonical source. Final classification, performance conclusions, and experiment decisions must come from:

- `observer_report_lcr_cont_v1.py`
- `observer_report_pfm_cont_v1.py`
- `et_daily_report_v*.py`
- Feature tape analysis scripts

The dashboard is for real-time monitoring and operator awareness. It must not contradict the canonical reports, but it does not supersede them.

---

## RULE 5 — Minimal Dashboard Display Defaults

These defaults must be preserved in all future dashboard versions:

| Rule | Requirement |
|------|-------------|
| Labels | Explicit labels only — no generic "n" without context |
| Scope | Current run only by default; archived/stale runs clearly marked |
| Counting | All-fire vs distinct-only clearly labeled where both are shown |
| Layout | Health and coverage visible before performance metrics |
| Missing data | If a view is unsupported by current data, show that explicitly — never silently omit |

---

## Definition of Done (for any experiment-affecting change)

A change is **done** when all five conditions are met:

1. Code changed and committed
2. Canonical report still produces valid output
3. `ops/dashboard_compat_check.py --view <view>` passes (or blocker documented)
4. Dashboard updated **or** explicitly proven unaffected
5. Change manifest written to `reports/ops/change_manifest_<UTC>.md`

---

## Dashboard Views and Their DB Sources

| View (`?observer=`) | DB file | Primary table | Service |
|---------------------|---------|---------------|---------|
| `lcr` (default) | `observer_lcr_cont_v1.db` | `observer_lcr_cont_v1` | `solana-lcr-cont-observer.service` |
| `pfm` | `observer_pfm_cont_v1.db` | `observer_pfm_cont_v1` | `solana-pfm-cont-observer.service` |
| `pfm_rev` | `observer_pfm_rev_v1.db` | `observer_pfm_rev_v1` | `solana-pfm-rev-observer.service` |
| `lcr_rank_lift` | `lcr_rank_lift_sidecar_v1.db` | `lcr_rank_lift_sidecar_v1` | `lcr-rank-lift-sidecar-v1.service` |
| `feature_tape` | `solana_trader.db` | `feature_tape_v1` | bare process / `feature-tape-v1.service` |

All DBs live in `/root/solana_trader/data/`.  
Dashboard runs at `http://0.0.0.0:7070` (`observer_dashboard.py`).

---

## Tooling

| Tool | Path | Purpose |
|------|------|---------|
| Compatibility check | `ops/dashboard_compat_check.py` | Automated DB + route + column check |
| Latest compat result | `reports/ops/dashboard_compat_latest.md` | Written by compat check script |
| Change manifest | `reports/ops/change_manifest_<UTC>.md` | Required per-change sign-off |
| This policy | `reports/ops/dashboard_sync_policy.md` | Authoritative policy document |

---

*This policy applies to all contributors and automated agents working on this project.*
