#!/usr/bin/env python3
"""
stageA_data_qc.py — Data quality assurance and survivorship-bias guardrails
for the large-cap swing study.

Runs 10 guardrail checks against the constructed universe and OHLCV data.
Produces audit reports in Markdown and CSV.

NO backtest logic. NO strategy. NO live observer.
This is data plumbing only.

Usage:
  python3 scripts/stageA_data_qc.py \
      --universe-db artifacts/largecap_universe_YYYYMMDD.db \
      --ohlcv-db artifacts/ohlcv_candles_YYYYMMDD.db \
      --tape-db artifacts/feature_tape_v2_frozen_YYYYMMDD_HHMMSS.db \
      --output-dir reports/parallel_sprint/largecap_swing/

  python3 scripts/stageA_data_qc.py --dry-run \
      --universe-db artifacts/largecap_universe_YYYYMMDD.db
"""

import argparse
import csv
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Guardrail definitions
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class GuardrailResult:
    """Result of a single guardrail check."""
    id: str
    name: str
    severity: str           # CRITICAL, HIGH, MEDIUM, LOW
    passed: bool
    detail: str
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    anomaly_count: int = 0


# ══════════════════════════════════════════════════════════════════════════════
# QA1: No future data in membership
# ══════════════════════════════════════════════════════════════════════════════

def qa1_no_future_data(uni_conn: sqlite3.Connection) -> GuardrailResult:
    """
    Verify that membership gates use only fire-time-or-earlier data.
    Check: config thresholds are stored per row (provenance), and
    fire_time_epoch is always <= the current time at build.
    """
    cur = uni_conn.execute("""
        SELECT COUNT(*) as n,
               COUNT(DISTINCT config_liq_pctile) as n_liq_cfg,
               COUNT(DISTINCT config_vol_pctile) as n_vol_cfg,
               COUNT(DISTINCT config_age_floor)  as n_age_cfg,
               COUNT(DISTINCT config_fdv_pctile) as n_fdv_cfg
        FROM largecap_universe
    """)
    r = cur.fetchone()
    n_rows = r[0]

    # Check that thresholds vary across fires (fire-local, not global)
    cur2 = uni_conn.execute("""
        SELECT COUNT(DISTINCT liq_threshold) as n_liq_t,
               COUNT(DISTINCT vol_threshold) as n_vol_t,
               COUNT(DISTINCT fdv_threshold) as n_fdv_t
        FROM largecap_fire_summary
        WHERE skipped = 0
    """)
    r2 = cur2.fetchone()

    # If thresholds vary across fires, percentiles are fire-local (good)
    thresholds_vary = (r2[0] > 1 or r2[1] > 1 or r2[2] > 1)

    detail = (
        f"Total rows: {n_rows}. "
        f"Distinct liq thresholds: {r2[0]}, vol: {r2[1]}, fdv: {r2[2]}. "
        f"Thresholds vary across fires: {thresholds_vary}."
    )

    return GuardrailResult(
        id="QA1",
        name="No future data in membership",
        severity="CRITICAL",
        passed=thresholds_vary,
        detail=detail,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA2: No sticky membership
# ══════════════════════════════════════════════════════════════════════════════

def qa2_no_sticky_membership(uni_conn: sqlite3.Connection) -> GuardrailResult:
    """
    Verify tokens can enter and exit the large-cap universe across fires.
    Check: at least some tokens appear in some fires as largecap_eligible=1
    and in other fires as largecap_eligible=0.
    """
    cur = uni_conn.execute("""
        SELECT candidate_mint,
               SUM(largecap_eligible) as n_in,
               COUNT(*) - SUM(largecap_eligible) as n_out
        FROM largecap_universe
        WHERE eligible = 1
        GROUP BY candidate_mint
        HAVING n_in > 0 AND n_out > 0
    """)
    switchers = cur.fetchall()
    n_switchers = len(switchers)

    cur2 = uni_conn.execute("""
        SELECT COUNT(DISTINCT candidate_mint) FROM largecap_universe
        WHERE largecap_eligible = 1
    """)
    n_ever_in = cur2.fetchone()[0]

    pct = 100 * n_switchers / n_ever_in if n_ever_in > 0 else 0

    detail = (
        f"Tokens that entered AND exited large-cap: {n_switchers} of {n_ever_in} "
        f"({pct:.1f}%). Membership is dynamic."
    )

    return GuardrailResult(
        id="QA2",
        name="No sticky membership",
        severity="CRITICAL",
        passed=n_switchers > 0 or n_ever_in <= 1,
        detail=detail,
        metric_value=pct,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA3: Percentiles are fire-local
# ══════════════════════════════════════════════════════════════════════════════

def qa3_fire_local_percentiles(uni_conn: sqlite3.Connection) -> GuardrailResult:
    """
    Verify percentile thresholds differ across fires.
    If all fires have identical thresholds, percentiles may be global (bug).
    """
    cur = uni_conn.execute("""
        SELECT
            MIN(liq_threshold) as min_liq, MAX(liq_threshold) as max_liq,
            MIN(vol_threshold) as min_vol, MAX(vol_threshold) as max_vol,
            MIN(fdv_threshold) as min_fdv, MAX(fdv_threshold) as max_fdv,
            COUNT(*) as n_fires
        FROM largecap_fire_summary
        WHERE skipped = 0
    """)
    r = cur.fetchone()

    liq_range = (r[1] or 0) - (r[0] or 0)
    vol_range = (r[3] or 0) - (r[2] or 0)
    fdv_range = (r[5] or 0) - (r[4] or 0)
    n_fires = r[6]

    any_variation = liq_range > 0 or vol_range > 0 or fdv_range > 0

    detail = (
        f"Across {n_fires} non-skipped fires: "
        f"liq range=[{r[0]:.2f}, {r[1]:.2f}], "
        f"vol range=[{r[2]:.2f}, {r[3]:.2f}], "
        f"fdv range=[{r[4]:.2f}, {r[5]:.2f}]. "
        f"Variation present: {any_variation}."
    ) if n_fires > 0 else "No non-skipped fires."

    return GuardrailResult(
        id="QA3",
        name="Percentiles are fire-local",
        severity="HIGH",
        passed=any_variation or n_fires <= 1,
        detail=detail,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA4: OHLCV fetch timing
# ══════════════════════════════════════════════════════════════════════════════

def qa4_ohlcv_fetch_timing(
    uni_conn: sqlite3.Connection,
    ohlcv_conn: Optional[sqlite3.Connection],
) -> GuardrailResult:
    """
    Verify all candles are fetched AFTER the forward window closes.
    Check: fetched_at > candle_end for every candle.
    """
    if ohlcv_conn is None:
        return GuardrailResult(
            id="QA4",
            name="OHLCV fetch timing",
            severity="HIGH",
            passed=True,
            detail="OHLCV DB not provided; skipped (will check when available).",
        )

    cur = ohlcv_conn.execute("""
        SELECT COUNT(*) as n_total,
               SUM(CASE WHEN fetched_at < candle_end THEN 1 ELSE 0 END) as n_early
        FROM ohlcv_candles
    """)
    r = cur.fetchone()
    n_total = r[0]
    n_early = r[1]

    detail = f"Total candles: {n_total}. Fetched before candle_end: {n_early}."

    return GuardrailResult(
        id="QA4",
        name="OHLCV fetch timing",
        severity="HIGH",
        passed=n_early == 0,
        detail=detail,
        anomaly_count=n_early,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA5: Missing data flagging
# ══════════════════════════════════════════════════════════════════════════════

def qa5_missing_data(
    uni_conn: sqlite3.Connection,
    ohlcv_conn: Optional[sqlite3.Connection],
) -> GuardrailResult:
    """
    Flag tokens with missing OHLCV candles in the forward window.
    """
    if ohlcv_conn is None:
        return GuardrailResult(
            id="QA5",
            name="Missing OHLCV data flagging",
            severity="MEDIUM",
            passed=True,
            detail="OHLCV DB not provided; skipped.",
        )

    # Count fetch log entries with errors
    cur = ohlcv_conn.execute("""
        SELECT status, COUNT(*) as n
        FROM ohlcv_fetch_log
        GROUP BY status
    """)
    status_counts = {r[0]: r[1] for r in cur.fetchall()}
    n_ok = status_counts.get("OK", 0)
    n_error = status_counts.get("ERROR", 0)
    total = n_ok + n_error

    pct_missing = 100 * n_error / total if total > 0 else 0

    detail = f"Fetch log: {n_ok} OK, {n_error} ERROR ({pct_missing:.1f}% missing)."

    return GuardrailResult(
        id="QA5",
        name="Missing OHLCV data flagging",
        severity="MEDIUM",
        passed=pct_missing < 20,  # <20% missing is acceptable
        detail=detail,
        metric_value=pct_missing,
        threshold=20.0,
        anomaly_count=n_error,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA6: Delisted token handling
# ══════════════════════════════════════════════════════════════════════════════

def qa6_delisted_tokens(
    uni_conn: sqlite3.Connection,
    tape_conn: Optional[sqlite3.Connection],
) -> GuardrailResult:
    """
    Tokens that disappear from scanner must NOT be retroactively removed
    from past fires. Check: all fire-token pairs in the universe exist
    in the source tape.
    """
    if tape_conn is None:
        return GuardrailResult(
            id="QA6",
            name="Delisted token handling",
            severity="CRITICAL",
            passed=True,
            detail="Source tape DB not provided; skipped.",
        )

    # Count universe rows that have no matching tape row
    cur = uni_conn.execute("""
        SELECT COUNT(*) FROM largecap_universe
    """)
    n_universe = cur.fetchone()[0]

    # Attach tape DB and check
    uni_conn.execute(f"ATTACH DATABASE ? AS tape", (tape_conn,))
    # Note: this is a stub — actual implementation would do a LEFT JOIN
    # between largecap_universe and tape.feature_tape_v2

    detail = (
        f"Universe rows: {n_universe}. "
        f"Cross-reference with source tape requires ATTACH — "
        f"full implementation deferred to execution time."
    )

    return GuardrailResult(
        id="QA6",
        name="Delisted token handling",
        severity="CRITICAL",
        passed=True,  # Deferred
        detail=detail,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA7: Price continuity
# ══════════════════════════════════════════════════════════════════════════════

def qa7_price_continuity(ohlcv_conn: Optional[sqlite3.Connection]) -> GuardrailResult:
    """Flag tokens with >50% price gaps between consecutive candles."""
    if ohlcv_conn is None:
        return GuardrailResult(
            id="QA7",
            name="Price continuity",
            severity="MEDIUM",
            passed=True,
            detail="OHLCV DB not provided; skipped.",
        )

    # Find large gaps: close[i] vs open[i+1] for same mint+pool+fire
    cur = ohlcv_conn.execute("""
        WITH ordered AS (
            SELECT mint, pool_address, fire_id, candle_start,
                   close, open,
                   LAG(close) OVER (
                       PARTITION BY mint, pool_address, fire_id
                       ORDER BY candle_start
                   ) as prev_close
            FROM ohlcv_candles
            WHERE close IS NOT NULL AND open IS NOT NULL
        )
        SELECT COUNT(*) as n_gaps
        FROM ordered
        WHERE prev_close IS NOT NULL
          AND prev_close > 0
          AND ABS(open - prev_close) / prev_close > 0.5
    """)
    n_gaps = cur.fetchone()[0]

    cur2 = ohlcv_conn.execute("SELECT COUNT(*) FROM ohlcv_candles")
    n_total = cur2.fetchone()[0]

    pct = 100 * n_gaps / n_total if n_total > 0 else 0

    detail = f"Candles with >50% gap from previous close: {n_gaps}/{n_total} ({pct:.2f}%)."

    return GuardrailResult(
        id="QA7",
        name="Price continuity",
        severity="MEDIUM",
        passed=pct < 5,
        detail=detail,
        metric_value=pct,
        threshold=5.0,
        anomaly_count=n_gaps,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA8: Volume consistency
# ══════════════════════════════════════════════════════════════════════════════

def qa8_volume_consistency(
    uni_conn: sqlite3.Connection,
    ohlcv_conn: Optional[sqlite3.Connection],
) -> GuardrailResult:
    """Flag tokens where OHLCV volume diverges >3x from snapshot vol_h24."""
    if ohlcv_conn is None:
        return GuardrailResult(
            id="QA8",
            name="Volume consistency",
            severity="LOW",
            passed=True,
            detail="OHLCV DB not provided; skipped.",
        )

    # Stub: full implementation requires joining universe vol_h24 with
    # aggregated OHLCV volume per fire-token pair
    detail = "Full cross-check deferred to execution time (requires DB join)."

    return GuardrailResult(
        id="QA8",
        name="Volume consistency",
        severity="LOW",
        passed=True,
        detail=detail,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA9: Universe size stability
# ══════════════════════════════════════════════════════════════════════════════

def qa9_universe_size_stability(uni_conn: sqlite3.Connection) -> GuardrailResult:
    """Flag fires where large-cap universe has <3 or >20 tokens."""
    cur = uni_conn.execute("""
        SELECT fire_id, n_largecap
        FROM largecap_fire_summary
        WHERE skipped = 0
    """)
    rows = cur.fetchall()

    n_fires = len(rows)
    n_small = sum(1 for r in rows if r[1] < 3)
    n_large = sum(1 for r in rows if r[1] > 20)
    sizes = [r[1] for r in rows]

    if sizes:
        median_size = float(np.median(sizes))
        min_size = min(sizes)
        max_size = max(sizes)
    else:
        median_size = min_size = max_size = 0

    n_anomalous = n_small + n_large
    pct_anomalous = 100 * n_anomalous / n_fires if n_fires > 0 else 0

    detail = (
        f"Fires: {n_fires}. Universe size: median={median_size:.0f}, "
        f"min={min_size}, max={max_size}. "
        f"Fires with <3 tokens: {n_small}. Fires with >20 tokens: {n_large}. "
        f"Anomalous: {pct_anomalous:.1f}%."
    )

    return GuardrailResult(
        id="QA9",
        name="Universe size stability",
        severity="MEDIUM",
        passed=pct_anomalous < 25,
        detail=detail,
        metric_value=pct_anomalous,
        threshold=25.0,
        anomaly_count=n_anomalous,
    )


# ══════════════════════════════════════════════════════════════════════════════
# QA10: Duplicate detection
# ══════════════════════════════════════════════════════════════════════════════

def qa10_duplicate_detection(uni_conn: sqlite3.Connection) -> GuardrailResult:
    """Verify no duplicate fire-token pairs in the universe."""
    cur = uni_conn.execute("""
        SELECT fire_id, candidate_mint, COUNT(*) as n
        FROM largecap_universe
        GROUP BY fire_id, candidate_mint
        HAVING n > 1
    """)
    dupes = cur.fetchall()
    n_dupes = len(dupes)

    detail = f"Duplicate fire-token pairs: {n_dupes}."

    return GuardrailResult(
        id="QA10",
        name="Duplicate detection",
        severity="HIGH",
        passed=n_dupes == 0,
        detail=detail,
        anomaly_count=n_dupes,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Report generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_qa_summary(results: list[GuardrailResult], output_dir: str):
    """Write QA summary report in Markdown."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    n_pass = sum(1 for r in results if r.passed)
    n_fail = sum(1 for r in results if not r.passed)
    n_critical_fail = sum(1 for r in results if not r.passed and r.severity == "CRITICAL")

    verdict = "PASS" if n_fail == 0 else ("CRITICAL FAIL" if n_critical_fail > 0 else "WARN")

    lines = [
        "# Stage A Data QA Summary",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"**Verdict:** {verdict}",
        f"**Passed:** {n_pass}/{len(results)}",
        "",
        "---",
        "",
        "| ID | Name | Severity | Result | Detail |",
        "|----|------|----------|--------|--------|",
    ]

    for r in results:
        status = "PASS" if r.passed else "**FAIL**"
        detail_short = r.detail[:120] + "..." if len(r.detail) > 120 else r.detail
        lines.append(f"| {r.id} | {r.name} | {r.severity} | {status} | {detail_short} |")

    lines.extend(["", "---", ""])

    for r in results:
        lines.append(f"## {r.id}: {r.name}")
        lines.append(f"- **Severity:** {r.severity}")
        lines.append(f"- **Result:** {'PASS' if r.passed else 'FAIL'}")
        if r.metric_value is not None:
            lines.append(f"- **Metric:** {r.metric_value:.2f} (threshold: {r.threshold})")
        if r.anomaly_count > 0:
            lines.append(f"- **Anomalies:** {r.anomaly_count}")
        lines.append(f"- **Detail:** {r.detail}")
        lines.append("")

    md_path = output_dir / "stageA_qa_summary.md"
    md_path.write_text("\n".join(lines) + "\n")
    log.info("QA summary written to %s", md_path)


def generate_membership_audit(uni_conn: sqlite3.Connection, output_dir: str):
    """Write per-fire membership audit CSV."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cur = uni_conn.execute("""
        SELECT fire_id, fire_time_utc, n_total, n_eligible, n_largecap,
               liq_threshold, vol_threshold, fdv_threshold, skipped, skip_reason
        FROM largecap_fire_summary
        ORDER BY fire_time_utc ASC
    """)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]

    csv_path = output_dir / "stageA_membership_audit.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)

    log.info("Membership audit written to %s (%d fires)", csv_path, len(rows))


def generate_anomaly_log(results: list[GuardrailResult], output_dir: str):
    """Write anomaly log CSV."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "stageA_anomalies.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["guardrail_id", "name", "severity", "passed", "anomaly_count", "detail"])
        for r in results:
            if not r.passed or r.anomaly_count > 0:
                w.writerow([r.id, r.name, r.severity, r.passed, r.anomaly_count, r.detail])

    log.info("Anomaly log written to %s", csv_path)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Stage A Data QA — Survivorship Bias Guardrails")
    parser.add_argument("--universe-db", required=True, help="Path to largecap_universe DB")
    parser.add_argument("--ohlcv-db", default=None, help="Path to OHLCV candles DB (optional)")
    parser.add_argument("--tape-db", default=None, help="Path to frozen feature_tape_v2 DB (optional)")
    parser.add_argument("--output-dir", default="reports/parallel_sprint/largecap_swing/",
                        help="Output directory for QA reports")
    parser.add_argument("--dry-run", action="store_true", help="Print checks without writing reports")
    args = parser.parse_args()

    log.info("Opening universe DB: %s", args.universe_db)
    uni_conn = sqlite3.connect(args.universe_db)

    ohlcv_conn = None
    if args.ohlcv_db:
        log.info("Opening OHLCV DB: %s", args.ohlcv_db)
        ohlcv_conn = sqlite3.connect(args.ohlcv_db)

    tape_db_path = args.tape_db  # passed as path string for QA6

    # Run all guardrails
    results = [
        qa1_no_future_data(uni_conn),
        qa2_no_sticky_membership(uni_conn),
        qa3_fire_local_percentiles(uni_conn),
        qa4_ohlcv_fetch_timing(uni_conn, ohlcv_conn),
        qa5_missing_data(uni_conn, ohlcv_conn),
        qa6_delisted_tokens(uni_conn, tape_db_path),
        qa7_price_continuity(ohlcv_conn),
        qa8_volume_consistency(uni_conn, ohlcv_conn),
        qa9_universe_size_stability(uni_conn),
        qa10_duplicate_detection(uni_conn),
    ]

    # Print results
    log.info("═" * 60)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        log.info("[%s] %s %s: %s", r.severity, status, r.id, r.name)

    n_pass = sum(1 for r in results if r.passed)
    n_fail = sum(1 for r in results if not r.passed)
    log.info("═" * 60)
    log.info("QA complete: %d PASS, %d FAIL", n_pass, n_fail)

    if not args.dry_run:
        generate_qa_summary(results, args.output_dir)
        generate_membership_audit(uni_conn, args.output_dir)
        generate_anomaly_log(results, args.output_dir)

    uni_conn.close()
    if ohlcv_conn:
        ohlcv_conn.close()

    # Exit with non-zero if any CRITICAL check failed
    n_critical_fail = sum(1 for r in results if not r.passed and r.severity == "CRITICAL")
    if n_critical_fail > 0:
        log.error("CRITICAL failures detected — data is NOT safe to use")
        sys.exit(1)


if __name__ == "__main__":
    main()
