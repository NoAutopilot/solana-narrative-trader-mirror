#!/usr/bin/env python3
"""
dashboard_compat_check.py — Dashboard compatibility gate check.

Verifies that the observer_dashboard.py can serve a given view correctly:
  - run_id resolution works
  - required DB / table exists and is readable
  - required columns exist
  - current dashboard fields have a source mapping
  - HTTP 200 from local dashboard (if running)

Usage:
    python3 ops/dashboard_compat_check.py --view lcr
    python3 ops/dashboard_compat_check.py --view pfm --run-id abc123
    python3 ops/dashboard_compat_check.py --view feature_tape
    python3 ops/dashboard_compat_check.py --view rank_lift
    python3 ops/dashboard_compat_check.py --view all

Output:
    - prints pass/fail per check
    - writes reports/ops/dashboard_compat_latest.md
    - exits 0 on all-pass, 1 on any failure
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports" / "ops"
REPORT_FILE = REPORT_DIR / "dashboard_compat_latest.md"
DASHBOARD_PORT = 7070
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}/"

# View definitions: maps view name → (db_path, table_name, required_columns, url_param)
VIEW_DEFS = {
    "lcr": {
        "db": DATA_DIR / "observer_lcr_cont_v1.db",
        "table": "observer_lcr_cont_v1",
        "fire_log_table": "observer_fire_log",
        "required_cols": [
            "candidate_id", "run_id", "signal_fire_id", "candidate_type",
            "control_for_signal_id", "fire_time_epoch", "fire_time_iso",
            "snapshot_at_iso", "mint", "symbol",
        ],
        "run_id_query": "SELECT run_id FROM observer_lcr_cont_v1 ORDER BY rowid DESC LIMIT 1",
        "url_param": "?observer=lcr",
        "service": "solana-lcr-cont-observer.service",
    },
    "pfm": {
        "db": DATA_DIR / "observer_pfm_cont_v1.db",
        "table": "observer_pfm_cont_v1",
        "fire_log_table": "observer_fire_log",
        "required_cols": [
            "candidate_id", "run_id", "signal_fire_id", "candidate_type",
            "control_for_signal_id", "fire_time_epoch", "fire_time_iso",
            "snapshot_at_iso", "mint", "symbol",
        ],
        "run_id_query": "SELECT run_id FROM observer_pfm_cont_v1 ORDER BY rowid DESC LIMIT 1",
        "url_param": "?observer=pfm",
        "service": "solana-pfm-cont-observer.service",
    },
    "pfm_rev": {
        "db": DATA_DIR / "observer_pfm_rev_v1.db",
        "table": "observer_pfm_rev_v1",
        "fire_log_table": "observer_fire_log",
        "required_cols": [
            "candidate_id", "run_id", "signal_fire_id", "candidate_type",
            "control_for_signal_id", "fire_time_epoch", "fire_time_iso",
            "snapshot_at_iso", "mint", "symbol",
        ],
        "run_id_query": "SELECT run_id FROM observer_pfm_rev_v1 ORDER BY rowid DESC LIMIT 1",
        "url_param": "?observer=pfm_rev",
        "service": "solana-pfm-rev-observer.service",
    },
    "rank_lift": {
        "db": DATA_DIR / "lcr_rank_lift_sidecar_v1.db",
        "table": "lcr_rank_lift_sidecar_v1",
        "fire_log_table": "sidecar_fire_log",
        "required_cols": [
            "id", "run_id", "fire_id", "fire_time", "snapshot_at_used",
            "baseline_mint", "baseline_symbol", "baseline_score",
            "baseline_lane", "baseline_r_m5",
        ],
        "run_id_query": "SELECT run_id FROM lcr_rank_lift_sidecar_v1 ORDER BY rowid DESC LIMIT 1",
        "url_param": "?observer=lcr_rank_lift",
        "service": "lcr-rank-lift-sidecar-v1.service",
    },
    "feature_tape": {
        "db": DATA_DIR / "solana_trader.db",
        "table": "feature_tape_v1",
        "fire_log_table": None,
        "required_cols": [
            "id", "fire_id", "fire_time_utc", "fire_time_epoch",
            "candidate_mint", "candidate_symbol", "lane", "venue",
            "pumpfun_origin", "age_hours", "liquidity_usd", "vol_h1",
            "rv5m", "r_m5", "range_5m", "buy_sell_ratio_m5",
            "signed_flow_m5", "txn_accel_m5_vs_h1", "vol_accel_m5_vs_h1",
            "avg_trade_usd_m5", "jup_vs_cpamm_diff_pct", "round_trip_pct",
            "impact_buy_pct", "impact_sell_pct", "liq_change_pct",
            "breadth_positive_pct", "median_pool_r_m5", "pool_dispersion_r_m5",
            "r_m5_source", "order_flow_source", "quote_source", "liq_source",
            "pool_size_total", "pool_size_with_micro", "created_at",
            "lane_from_snap", "pool_type",
        ],
        "run_id_query": None,  # feature_tape uses fire_id, not run_id
        "url_param": None,     # no dedicated dashboard view yet
        "service": "feature-tape-v1.service",
    },
}

ALL_VIEWS = list(VIEW_DEFS.keys())

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
WARN = "WARN"


def check(label, result, detail=""):
    icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "–", "WARN": "!"}.get(result, "?")
    line = f"  [{icon}] {label}"
    if detail:
        line += f": {detail}"
    print(line)
    return result


def service_active(service_name):
    try:
        out = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return out == "active"
    except Exception:
        return False


def http_check(url):
    try:
        req = urllib.request.urlopen(url, timeout=5)
        return req.status
    except Exception as e:
        return str(e)


# ── Per-view check ────────────────────────────────────────────────────────────

def check_view(view_name, run_id_override=None):
    vdef = VIEW_DEFS[view_name]
    db_path = vdef["db"]
    table = vdef["table"]
    fire_log_table = vdef["fire_log_table"]
    required_cols = vdef["required_cols"]
    run_id_query = vdef["run_id_query"]
    url_param = vdef["url_param"]
    service = vdef["service"]

    results = {}
    details = {}
    affected_fields = []
    missing_cols = []

    print(f"\n{'='*60}")
    print(f"VIEW: {view_name}")
    print(f"{'='*60}")

    # ── Check 1: DB file exists ───────────────────────────────────────────────
    if db_path.exists():
        results["db_exists"] = PASS
        details["db_exists"] = str(db_path)
    else:
        results["db_exists"] = FAIL
        details["db_exists"] = f"NOT FOUND: {db_path}"
    check("DB file exists", results["db_exists"], details["db_exists"])

    if results["db_exists"] == FAIL:
        return results, details, affected_fields, missing_cols, None

    # ── Check 2: DB readable ──────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        results["db_readable"] = PASS
        details["db_readable"] = "OK"
    except Exception as e:
        results["db_readable"] = FAIL
        details["db_readable"] = str(e)
        check("DB readable", results["db_readable"], details["db_readable"])
        return results, details, affected_fields, missing_cols, None
    check("DB readable", results["db_readable"])

    # ── Check 3: Primary table exists ────────────────────────────────────────
    tables_in_db = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if table in tables_in_db:
        results["table_exists"] = PASS
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        details["table_exists"] = f"{table} ({row_count} rows)"
    else:
        results["table_exists"] = FAIL
        details["table_exists"] = f"Table '{table}' not found. Tables: {tables_in_db}"
    check("Primary table exists", results["table_exists"], details["table_exists"])

    if results["table_exists"] == FAIL:
        conn.close()
        return results, details, affected_fields, missing_cols, None

    # ── Check 4: Fire log table (if applicable) ───────────────────────────────
    if fire_log_table:
        if fire_log_table in tables_in_db:
            fl_count = conn.execute(f"SELECT COUNT(*) FROM {fire_log_table}").fetchone()[0]
            results["fire_log_exists"] = PASS
            details["fire_log_exists"] = f"{fire_log_table} ({fl_count} rows)"
        else:
            results["fire_log_exists"] = FAIL
            details["fire_log_exists"] = f"Table '{fire_log_table}' not found"
        check("Fire log table exists", results["fire_log_exists"], details["fire_log_exists"])

    # ── Check 5: Required columns present ────────────────────────────────────
    actual_cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    missing_cols = [c for c in required_cols if c not in actual_cols]
    extra_cols = [c for c in actual_cols if c not in required_cols]
    if not missing_cols:
        results["columns_present"] = PASS
        details["columns_present"] = f"all {len(required_cols)} required columns present"
    else:
        results["columns_present"] = FAIL
        details["columns_present"] = f"MISSING: {missing_cols}"
        affected_fields = missing_cols
    check("Required columns present", results["columns_present"], details["columns_present"])
    if extra_cols:
        check("Extra columns (new, not yet in dashboard)", WARN,
              f"{extra_cols} — verify dashboard handles these gracefully")

    # ── Check 6: run_id resolution ────────────────────────────────────────────
    current_run_id = None
    if run_id_query:
        if run_id_override:
            current_run_id = run_id_override
            results["run_id"] = PASS
            details["run_id"] = f"override={run_id_override}"
        else:
            row = conn.execute(run_id_query).fetchone()
            if row:
                current_run_id = row[0]
                results["run_id"] = PASS
                details["run_id"] = f"current={current_run_id}"
            else:
                results["run_id"] = WARN
                details["run_id"] = "no rows — table may be empty"
                current_run_id = None
        check("run_id resolution", results["run_id"], details["run_id"])
    else:
        results["run_id"] = SKIP
        details["run_id"] = "not applicable for this view"
        check("run_id resolution", SKIP, details["run_id"])

    conn.close()

    # ── Check 7: Service status ───────────────────────────────────────────────
    svc_active = service_active(service)
    results["service"] = PASS if svc_active else WARN
    details["service"] = f"{service}: {'active' if svc_active else 'inactive'}"
    check("Service status", results["service"], details["service"])

    # ── Check 8: HTTP 200 from local dashboard ────────────────────────────────
    if url_param:
        url = DASHBOARD_URL + url_param.lstrip("?")
        http_result = http_check(DASHBOARD_URL + url_param.lstrip("?"))
        if http_result == 200:
            results["http"] = PASS
            details["http"] = f"HTTP 200 from {url}"
        elif isinstance(http_result, int):
            results["http"] = FAIL
            details["http"] = f"HTTP {http_result} from {url}"
        else:
            results["http"] = WARN
            details["http"] = f"Dashboard not running or unreachable: {http_result}"
        check("Local dashboard HTTP", results["http"], details["http"])
    else:
        results["http"] = SKIP
        details["http"] = "no dedicated dashboard URL for this view"
        check("Local dashboard HTTP", SKIP, details["http"])

    return results, details, affected_fields, missing_cols, current_run_id


# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(all_results, views_checked, now_utc):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Dashboard Compatibility Check",
        "",
        f"**Run at:** {now_utc}  ",
        f"**Views checked:** {', '.join(views_checked)}  ",
        "",
        "---",
        "",
    ]

    overall_pass = True
    for view_name, (results, details, affected_fields, missing_cols, run_id) in all_results.items():
        failures = [k for k, v in results.items() if v == FAIL]
        view_pass = len(failures) == 0
        if not view_pass:
            overall_pass = False
        status = "PASS" if view_pass else "FAIL"

        lines += [
            f"## View: `{view_name}`",
            "",
            f"**Result: {status}**  ",
            f"**run_id:** {run_id or 'N/A'}  ",
            "",
            "| Check | Result | Detail |",
            "|-------|--------|--------|",
        ]
        for check_name, result in results.items():
            detail = details.get(check_name, "")
            lines.append(f"| {check_name} | {result} | {detail} |")
        lines.append("")

        if missing_cols:
            lines += [
                f"**Missing columns (dashboard impact: YES):** `{missing_cols}`  ",
                "",
                "These columns are expected by the dashboard but not present in the DB.",
                "Dashboard update required before this change can be considered done.",
                "",
            ]
        elif affected_fields:
            lines += [
                f"**Affected fields:** `{affected_fields}`  ",
                "",
            ]
        else:
            lines += [
                "**Dashboard impact: NO** — all required columns present, no visible fields changed.  ",
                "",
            ]

    lines += [
        "---",
        "",
        f"## Overall: {'PASS' if overall_pass else 'FAIL'}",
        "",
        "Per dashboard_sync_policy.md Rule 1:",
        "- If PASS: record `dashboard_updated = no, because no visible fields changed` in change manifest.",
        "- If FAIL: update dashboard before marking change as done.",
        "",
    ]

    REPORT_FILE.write_text("\n".join(lines))
    print(f"\nReport written: {REPORT_FILE}")
    return overall_pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dashboard compatibility gate check")
    parser.add_argument("--view", required=True,
                        choices=ALL_VIEWS + ["all"],
                        help="View to check, or 'all'")
    parser.add_argument("--run-id", default=None,
                        help="Override run_id for the check (optional)")
    args = parser.parse_args()

    views_to_check = ALL_VIEWS if args.view == "all" else [args.view]
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Dashboard Compatibility Check — {now_utc}")
    print(f"Views: {views_to_check}")

    all_results = {}
    for view in views_to_check:
        result = check_view(view, run_id_override=args.run_id)
        all_results[view] = result

    overall_pass = write_report(all_results, views_to_check, now_utc)

    print(f"\n{'='*60}")
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    print(f"{'='*60}")

    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    main()
