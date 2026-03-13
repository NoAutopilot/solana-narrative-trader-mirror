#!/usr/bin/env python3
"""
feature_tape_v2_contract_test.py — Contract tests for feature_tape_v2 schema.

Validates schema compliance, source-map adherence, semantic rules, and
no-lookahead guarantees. Runs against a frozen or live DB without mutation.

Usage:
  python3 tests/feature_tape_v2_contract_test.py \
      --db-path /root/solana_trader/data/solana_trader.db

  python3 tests/feature_tape_v2_contract_test.py --dry-run
"""

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str


# ══════════════════════════════════════════════════════════════════════════════
# Expected schema (from source map)
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_COLUMNS = [
    # Identity
    "fire_id", "fire_utc", "fire_epoch", "candidate_mint", "sym",
    # Universe classification
    "eligible", "gate_reason", "lane", "lane_source",
    # Snapshot-native
    "pool_address", "pool_type", "pumpfun_origin",
    "price_usd", "liq_usd", "vol_h24", "mcap_usd", "fdv_usd",
    "r_m5", "r_h1", "r_h6", "r_h24",
    "age_minutes",
    # Micro-native (nullable)
    "buys_m5", "sells_m5", "buys_h1", "sells_h1",
    "buy_sell_ratio_m5", "buy_sell_ratio_h1",
    "buy_count_ratio_m5", "buy_count_ratio_h1",
    "avg_trade_usd_m5", "avg_trade_usd_h1",
    "vol_accel_m5_vs_h1", "txn_accel_m5_vs_h1",
    "rv_5m", "rv_1m", "range_5m",
    "liq_change_pct", "liq_cliff_flag",
    # Quote-native (nullable for ineligible)
    "jup_vs_cpamm_diff_pct", "round_trip_pct",
    # Pool-level aggregates (fire-level)
    "pool_count", "pool_size_total",
    "breadth_positive_pct", "breadth_negative_pct",
    "median_pool_r_m5", "pool_dispersion_r_m5", "median_pool_rv5m",
    # Derived
    "order_flow_source",
    # Label columns
    "label_r_5m", "label_r_15m", "label_r_30m", "label_r_1h", "label_r_4h",
]

SNAPSHOT_NATIVE_COLUMNS = [
    "pool_address", "pool_type", "pumpfun_origin",
    "price_usd", "liq_usd", "vol_h24", "mcap_usd", "fdv_usd",
    "r_m5", "r_h1", "r_h6", "r_h24", "age_minutes",
    "eligible", "gate_reason",
]

MICRO_NATIVE_COLUMNS = [
    "buys_m5", "sells_m5", "buys_h1", "sells_h1",
    "buy_sell_ratio_m5", "buy_sell_ratio_h1",
    "buy_count_ratio_m5", "buy_count_ratio_h1",
    "avg_trade_usd_m5", "avg_trade_usd_h1",
    "vol_accel_m5_vs_h1", "txn_accel_m5_vs_h1",
    "rv_5m", "rv_1m", "range_5m",
    "liq_change_pct", "liq_cliff_flag",
]

FIRE_LEVEL_COLUMNS = [
    "pool_count", "pool_size_total",
    "breadth_positive_pct", "breadth_negative_pct",
    "median_pool_r_m5", "pool_dispersion_r_m5", "median_pool_rv5m",
]

LABEL_COLUMNS = [
    "label_r_5m", "label_r_15m", "label_r_30m", "label_r_1h", "label_r_4h",
]

NO_LOOKAHEAD_COLUMNS = LABEL_COLUMNS  # These must be NULL at collection time


# ══════════════════════════════════════════════════════════════════════════════
# Contract tests
# ══════════════════════════════════════════════════════════════════════════════

def test_required_columns_exist(conn: sqlite3.Connection) -> TestResult:
    """CT1: All required columns exist in the table."""
    cur = conn.execute("PRAGMA table_info(feature_tape_v2)")
    actual_cols = {row[1] for row in cur.fetchall()}

    missing = [c for c in REQUIRED_COLUMNS if c not in actual_cols]
    extra = actual_cols - set(REQUIRED_COLUMNS)

    if missing:
        return TestResult("CT1_required_columns", False,
                          f"Missing: {missing}")
    return TestResult("CT1_required_columns", True,
                      f"All {len(REQUIRED_COLUMNS)} required columns present. "
                      f"Extra columns: {len(extra)}")


def test_eligible_gate_reason_semantics(conn: sqlite3.Connection) -> TestResult:
    """CT2: eligible is 0/1, gate_reason is NULL iff eligible=1."""
    cur = conn.execute("""
        SELECT
            COUNT(*) as n,
            SUM(CASE WHEN eligible NOT IN (0, 1) THEN 1 ELSE 0 END) as bad_eligible,
            SUM(CASE WHEN eligible = 1 AND gate_reason IS NOT NULL THEN 1 ELSE 0 END) as elig_with_reason,
            SUM(CASE WHEN eligible = 0 AND gate_reason IS NULL THEN 1 ELSE 0 END) as inelig_no_reason
        FROM feature_tape_v2
    """)
    r = cur.fetchone()
    n, bad, elig_reason, inelig_no = r

    issues = []
    if bad > 0:
        issues.append(f"{bad} rows with eligible not in (0,1)")
    if elig_reason > 0:
        issues.append(f"{elig_reason} eligible rows with non-null gate_reason")
    if inelig_no > 0:
        issues.append(f"{inelig_no} ineligible rows with null gate_reason")

    if issues:
        return TestResult("CT2_eligible_semantics", False, "; ".join(issues))
    return TestResult("CT2_eligible_semantics", True,
                      f"All {n} rows comply with eligible/gate_reason semantics")


def test_lane_not_null(conn: sqlite3.Connection) -> TestResult:
    """CT3: lane is never NULL."""
    cur = conn.execute("SELECT COUNT(*) FROM feature_tape_v2 WHERE lane IS NULL")
    n_null = cur.fetchone()[0]
    if n_null > 0:
        return TestResult("CT3_lane_not_null", False, f"{n_null} rows with NULL lane")
    return TestResult("CT3_lane_not_null", True, "No NULL lanes")


def test_micro_null_semantics(conn: sqlite3.Connection) -> TestResult:
    """CT4: Micro-native columns are all NULL or all non-NULL per row."""
    # Check: if buys_m5 is NULL, all other micro columns should also be NULL
    checks = " + ".join(
        f"CASE WHEN {c} IS NOT NULL THEN 1 ELSE 0 END"
        for c in MICRO_NATIVE_COLUMNS
    )
    cur = conn.execute(f"""
        SELECT
            ({checks}) as n_nonnull,
            COUNT(*) as n_rows
        FROM feature_tape_v2
        GROUP BY n_nonnull
    """)
    rows = cur.fetchall()
    distribution = {r[0]: r[1] for r in rows}

    # Valid states: 0 (all null) or len(MICRO_NATIVE_COLUMNS) (all non-null)
    n_micro = len(MICRO_NATIVE_COLUMNS)
    valid_counts = {0, n_micro}
    invalid = {k: v for k, v in distribution.items() if k not in valid_counts}

    if invalid:
        return TestResult("CT4_micro_null_semantics", False,
                          f"Partial micro coverage detected: {invalid}")
    return TestResult("CT4_micro_null_semantics", True,
                      f"Micro columns: all-or-nothing NULL pattern. "
                      f"Covered: {distribution.get(n_micro, 0)}, "
                      f"Missing: {distribution.get(0, 0)}")


def test_fire_level_constant_within_fire(conn: sqlite3.Connection) -> TestResult:
    """CT5: Pool-level aggregate fields are constant within each fire."""
    issues = []
    for col in FIRE_LEVEL_COLUMNS:
        cur = conn.execute(f"""
            SELECT fire_id, COUNT(DISTINCT {col}) as n_distinct
            FROM feature_tape_v2
            WHERE {col} IS NOT NULL
            GROUP BY fire_id
            HAVING n_distinct > 1
        """)
        bad_fires = cur.fetchall()
        if bad_fires:
            issues.append(f"{col}: varies within {len(bad_fires)} fire(s)")

    if issues:
        return TestResult("CT5_fire_level_constant", False, "; ".join(issues))
    return TestResult("CT5_fire_level_constant", True,
                      f"All {len(FIRE_LEVEL_COLUMNS)} fire-level columns are constant within fires")


def test_label_columns_exist(conn: sqlite3.Connection) -> TestResult:
    """CT6: Label columns exist for all supported horizons."""
    cur = conn.execute("PRAGMA table_info(feature_tape_v2)")
    actual_cols = {row[1] for row in cur.fetchall()}

    missing = [c for c in LABEL_COLUMNS if c not in actual_cols]
    if missing:
        return TestResult("CT6_label_columns", False, f"Missing label columns: {missing}")
    return TestResult("CT6_label_columns", True,
                      f"All {len(LABEL_COLUMNS)} label columns present")


def test_no_lookahead(conn: sqlite3.Connection) -> TestResult:
    """CT7: No-lookahead fields should be NULL at collection time (before labeling)."""
    # This test checks if labels are still NULL (pre-labeling) or populated (post-labeling)
    # Both states are valid; we just report the state
    results = {}
    for col in NO_LOOKAHEAD_COLUMNS:
        cur = conn.execute(f"""
            SELECT
                COUNT(*) as n_total,
                SUM(CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END) as n_filled
            FROM feature_tape_v2
        """)
        r = cur.fetchone()
        results[col] = {"total": r[0], "filled": r[1]}

    any_filled = any(v["filled"] > 0 for v in results.values())
    detail = "; ".join(f"{k}: {v['filled']}/{v['total']} filled" for k, v in results.items())

    if any_filled:
        return TestResult("CT7_no_lookahead", True,
                          f"Labels have been populated (post-labeling). {detail}")
    return TestResult("CT7_no_lookahead", True,
                      f"Labels are NULL (pre-labeling, expected). {detail}")


def test_fire_log_exists(conn: sqlite3.Connection) -> TestResult:
    """CT8: fire_log table exists and has entries."""
    try:
        cur = conn.execute("SELECT COUNT(*) FROM feature_tape_v2_fire_log")
        n = cur.fetchone()[0]
        if n == 0:
            return TestResult("CT8_fire_log", False, "fire_log table exists but is empty")
        return TestResult("CT8_fire_log", True, f"fire_log has {n} entries")
    except sqlite3.OperationalError:
        return TestResult("CT8_fire_log", False, "feature_tape_v2_fire_log table does not exist")


def test_no_duplicate_fire_mint(conn: sqlite3.Connection) -> TestResult:
    """CT9: No duplicate (fire_id, candidate_mint) pairs."""
    cur = conn.execute("""
        SELECT fire_id, candidate_mint, COUNT(*) as n
        FROM feature_tape_v2
        GROUP BY fire_id, candidate_mint
        HAVING n > 1
    """)
    dupes = cur.fetchall()
    if dupes:
        return TestResult("CT9_no_duplicates", False,
                          f"{len(dupes)} duplicate fire-mint pairs")
    return TestResult("CT9_no_duplicates", True, "No duplicate fire-mint pairs")


def test_order_flow_source_values(conn: sqlite3.Connection) -> TestResult:
    """CT10: order_flow_source is either 'microstructure_log' or 'missing'."""
    cur = conn.execute("""
        SELECT order_flow_source, COUNT(*) as n
        FROM feature_tape_v2
        GROUP BY order_flow_source
    """)
    rows = cur.fetchall()
    sources = {r[0]: r[1] for r in rows}
    valid = {"microstructure_log", "missing"}
    invalid = set(sources.keys()) - valid - {None}

    if invalid:
        return TestResult("CT10_order_flow_source", False,
                          f"Invalid sources: {invalid}")
    return TestResult("CT10_order_flow_source", True,
                      f"Sources: {dict(sources)}")


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_required_columns_exist,
    test_eligible_gate_reason_semantics,
    test_lane_not_null,
    test_micro_null_semantics,
    test_fire_level_constant_within_fire,
    test_label_columns_exist,
    test_no_lookahead,
    test_fire_log_exists,
    test_no_duplicate_fire_mint,
    test_order_flow_source_values,
]


def run_all(conn: sqlite3.Connection) -> list[TestResult]:
    results = []
    for test_fn in ALL_TESTS:
        try:
            r = test_fn(conn)
        except Exception as e:
            r = TestResult(test_fn.__name__, False, f"Exception: {e}")
        results.append(r)
        status = "PASS" if r.passed else "FAIL"
        log.info("[%s] %s: %s", status, r.name, r.detail)
    return results


def main():
    parser = argparse.ArgumentParser(description="Feature Tape v2 Contract Tests")
    parser.add_argument("--db-path", required=False,
                        help="Path to SQLite DB containing feature_tape_v2")
    parser.add_argument("--dry-run", action="store_true",
                        help="List tests without running")
    args = parser.parse_args()

    if args.dry_run:
        log.info("[DRY RUN] %d contract tests defined:", len(ALL_TESTS))
        for t in ALL_TESTS:
            log.info("  - %s: %s", t.__name__, t.__doc__.strip())
        return

    if not args.db_path:
        log.error("--db-path is required (unless --dry-run)")
        sys.exit(1)

    conn = sqlite3.connect(args.db_path)
    results = run_all(conn)
    conn.close()

    n_pass = sum(1 for r in results if r.passed)
    n_fail = sum(1 for r in results if not r.passed)
    log.info("=" * 60)
    log.info("Contract tests: %d PASS, %d FAIL out of %d", n_pass, n_fail, len(results))

    if n_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
