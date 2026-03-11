# Dashboard Compatibility Check

**Run at:** 2026-03-11T19:14:43Z  
**Views checked:** lcr, pfm, pfm_rev, rank_lift, feature_tape  

---

## View: `lcr`

**Result: PASS**  
**run_id:** 95b3ad8a-30fb-4f22-9d97-641f77c60c1b  

| Check | Result | Detail |
|-------|--------|--------|
| db_exists | PASS | /root/solana_trader/data/observer_lcr_cont_v1.db |
| db_readable | PASS | OK |
| table_exists | PASS | observer_lcr_cont_v1 (702 rows) |
| fire_log_exists | PASS | observer_fire_log (418 rows) |
| columns_present | PASS | all 10 required columns present |
| run_id | PASS | current=95b3ad8a-30fb-4f22-9d97-641f77c60c1b |
| service | WARN | solana-lcr-cont-observer.service: inactive |
| http | WARN | Dashboard not running or unreachable: HTTP Error 404: NOT FOUND |

**Dashboard impact: NO** — all required columns present, no visible fields changed.  

## View: `pfm`

**Result: PASS**  
**run_id:** 1677a7da  

| Check | Result | Detail |
|-------|--------|--------|
| db_exists | PASS | /root/solana_trader/data/observer_pfm_cont_v1.db |
| db_readable | PASS | OK |
| table_exists | PASS | observer_pfm_cont_v1 (484 rows) |
| fire_log_exists | PASS | observer_fire_log (243 rows) |
| columns_present | PASS | all 10 required columns present |
| run_id | PASS | current=1677a7da |
| service | WARN | solana-pfm-cont-observer.service: inactive |
| http | WARN | Dashboard not running or unreachable: HTTP Error 404: NOT FOUND |

**Dashboard impact: NO** — all required columns present, no visible fields changed.  

## View: `pfm_rev`

**Result: PASS**  
**run_id:** 99ed0fd1  

| Check | Result | Detail |
|-------|--------|--------|
| db_exists | PASS | /root/solana_trader/data/observer_pfm_rev_v1.db |
| db_readable | PASS | OK |
| table_exists | PASS | observer_pfm_rev_v1 (208 rows) |
| fire_log_exists | PASS | observer_fire_log (118 rows) |
| columns_present | PASS | all 10 required columns present |
| run_id | PASS | current=99ed0fd1 |
| service | WARN | solana-pfm-rev-observer.service: inactive |
| http | WARN | Dashboard not running or unreachable: HTTP Error 404: NOT FOUND |

**Dashboard impact: NO** — all required columns present, no visible fields changed.  

## View: `rank_lift`

**Result: PASS**  
**run_id:** bb7244cd  

| Check | Result | Detail |
|-------|--------|--------|
| db_exists | PASS | /root/solana_trader/data/lcr_rank_lift_sidecar_v1.db |
| db_readable | PASS | OK |
| table_exists | PASS | lcr_rank_lift_sidecar_v1 (19 rows) |
| fire_log_exists | PASS | sidecar_fire_log (0 rows) |
| columns_present | PASS | all 10 required columns present |
| run_id | PASS | current=bb7244cd |
| service | WARN | lcr-rank-lift-sidecar-v1.service: inactive |
| http | WARN | Dashboard not running or unreachable: HTTP Error 404: NOT FOUND |

**Dashboard impact: NO** — all required columns present, no visible fields changed.  

## View: `feature_tape`

**Result: PASS**  
**run_id:** N/A  

| Check | Result | Detail |
|-------|--------|--------|
| db_exists | PASS | /root/solana_trader/data/solana_trader.db |
| db_readable | PASS | OK |
| table_exists | PASS | feature_tape_v1 (2247 rows) |
| columns_present | PASS | all 37 required columns present |
| run_id | SKIP | not applicable for this view |
| service | WARN | feature-tape-v1.service: inactive |
| http | SKIP | no dedicated dashboard URL for this view |

**Dashboard impact: NO** — all required columns present, no visible fields changed.  

---

## Overall: PASS

Per dashboard_sync_policy.md Rule 1:
- If PASS: record `dashboard_updated = no, because no visible fields changed` in change manifest.
- If FAIL: update dashboard before marking change as done.
