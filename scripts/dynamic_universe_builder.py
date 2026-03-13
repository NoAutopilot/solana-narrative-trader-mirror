#!/usr/bin/env python3
"""
dynamic_universe_builder.py — Point-in-time large-cap universe constructor.

Reads feature_tape_v2 (frozen snapshot) and constructs a per-fire large-cap
universe using ONLY information available at each fire time.

NO backtest logic. NO strategy. NO live observer.
This is data plumbing only.

Usage (after dataset freeze):
  python3 scripts/dynamic_universe_builder.py \
      --db-path artifacts/feature_tape_v2_frozen_YYYYMMDD_HHMMSS.db \
      --output-db artifacts/largecap_universe_YYYYMMDD.db \
      --output-csv reports/parallel_sprint/largecap_swing/largecap_universe.csv

  python3 scripts/dynamic_universe_builder.py --dry-run \
      --db-path artifacts/feature_tape_v2_frozen_YYYYMMDD_HHMMSS.db
"""

import argparse
import csv
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
# Configuration — membership gates
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MembershipConfig:
    """Point-in-time membership gates for the large-cap swing universe."""
    # G1: eligible must be 1 (enforced by query filter)
    # G2: liquidity percentile within fire-level eligible universe
    liq_percentile: float = 75.0
    # G3: volume floor — must be > 0 AND >= this percentile
    vol_percentile: float = 50.0
    # G4: minimum age in hours
    age_floor_hours: float = 24.0
    # G5: FDV/market-cap percentile within fire-level eligible universe
    fdv_percentile: float = 50.0
    # Minimum eligible tokens per fire to compute meaningful percentiles
    min_eligible_per_fire: int = 5


DEFAULT_CONFIG = MembershipConfig()

# ══════════════════════════════════════════════════════════════════════════════
# Schema for the output universe table
# ══════════════════════════════════════════════════════════════════════════════

CREATE_UNIVERSE_TABLE = """
CREATE TABLE IF NOT EXISTS largecap_universe (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fire_id             TEXT NOT NULL,
    fire_time_utc       TEXT NOT NULL,
    fire_time_epoch     INTEGER NOT NULL,
    candidate_mint      TEXT NOT NULL,
    symbol              TEXT,
    pool_address        TEXT,
    pool_type           TEXT,
    lane                TEXT,

    -- Point-in-time membership data (all from fire time)
    eligible            INTEGER NOT NULL,
    liq_usd             REAL,
    vol_h24             REAL,
    fdv                 REAL,
    market_cap          REAL,
    age_hours           REAL,
    price_usd           REAL,

    -- Fire-level percentile ranks (computed per fire)
    liq_pctile_fire     REAL,
    vol_pctile_fire     REAL,
    fdv_pctile_fire     REAL,

    -- Fire-level universe stats
    fire_eligible_count INTEGER,
    fire_largecap_count INTEGER,

    -- Membership decision
    largecap_eligible   INTEGER NOT NULL,   -- 1 = passes G1-G5; 0 = fails
    gate_fail_reason    TEXT,               -- NULL if passes; reason if fails

    -- Provenance
    config_liq_pctile   REAL NOT NULL,
    config_vol_pctile   REAL NOT NULL,
    config_age_floor    REAL NOT NULL,
    config_fdv_pctile   REAL NOT NULL,

    UNIQUE(fire_id, candidate_mint)
);
"""

CREATE_FIRE_SUMMARY_TABLE = """
CREATE TABLE IF NOT EXISTS largecap_fire_summary (
    fire_id             TEXT PRIMARY KEY,
    fire_time_utc       TEXT NOT NULL,
    fire_time_epoch     INTEGER NOT NULL,
    n_total             INTEGER NOT NULL,
    n_eligible          INTEGER NOT NULL,
    n_largecap          INTEGER NOT NULL,
    liq_threshold       REAL,
    vol_threshold       REAL,
    fdv_threshold       REAL,
    skipped             INTEGER NOT NULL DEFAULT 0,
    skip_reason         TEXT
);
"""


# ══════════════════════════════════════════════════════════════════════════════
# Core logic
# ══════════════════════════════════════════════════════════════════════════════

def get_fires(conn: sqlite3.Connection) -> list[dict]:
    """Get all distinct fires from feature_tape_v2, ordered by time."""
    cur = conn.execute("""
        SELECT DISTINCT fire_id, fire_time_utc, fire_time_epoch
        FROM feature_tape_v2
        ORDER BY fire_time_epoch ASC
    """)
    return [{"fire_id": r[0], "fire_time_utc": r[1], "fire_time_epoch": r[2]} for r in cur.fetchall()]


def get_fire_rows(conn: sqlite3.Connection, fire_id: str) -> list[dict]:
    """Get all rows for a single fire."""
    cur = conn.execute("""
        SELECT
            fire_id, fire_time_utc, fire_time_epoch,
            candidate_mint, sym, pool_address, pool_type, lane,
            eligible, liq_usd, vol_h24, fdv, market_cap, age_hours, price_usd
        FROM feature_tape_v2
        WHERE fire_id = ?
    """, (fire_id,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def compute_percentile(values: list[float], pct: float) -> Optional[float]:
    """Compute percentile from a list of non-null values."""
    clean = [v for v in values if v is not None and v > 0]
    if not clean:
        return None
    return float(np.percentile(clean, pct))


def percentile_rank(value: Optional[float], values: list[float]) -> Optional[float]:
    """Compute the percentile rank of a value within a list."""
    if value is None:
        return None
    clean = sorted([v for v in values if v is not None and v > 0])
    if not clean:
        return None
    rank = sum(1 for v in clean if v <= value)
    return round(100.0 * rank / len(clean), 2)


def evaluate_membership(
    row: dict,
    liq_threshold: Optional[float],
    vol_threshold: Optional[float],
    fdv_threshold: Optional[float],
    config: MembershipConfig,
) -> tuple[bool, Optional[str]]:
    """
    Evaluate whether a single row passes all membership gates.
    Returns (passes, fail_reason).
    """
    # G1: eligible
    if row.get("eligible") != 1:
        return False, "G1_not_eligible"

    # G2: liquidity
    liq = row.get("liq_usd")
    if liq is None or liq_threshold is None or liq < liq_threshold:
        return False, f"G2_liq_below_P{config.liq_percentile:.0f}"

    # G3: volume
    vol = row.get("vol_h24")
    if vol is None or vol <= 0:
        return False, "G3_vol_zero_or_null"
    if vol_threshold is not None and vol < vol_threshold:
        return False, f"G3_vol_below_P{config.vol_percentile:.0f}"

    # G4: age
    age = row.get("age_hours")
    if age is None or age < config.age_floor_hours:
        return False, f"G4_age_below_{config.age_floor_hours:.0f}h"

    # G5: FDV / market cap
    fdv = row.get("fdv") or row.get("market_cap")
    if fdv is None or fdv <= 0:
        return False, "G5_fdv_null_or_zero"
    if fdv_threshold is not None and fdv < fdv_threshold:
        return False, f"G5_fdv_below_P{config.fdv_percentile:.0f}"

    return True, None


def build_universe_for_fire(
    fire: dict,
    rows: list[dict],
    config: MembershipConfig,
) -> tuple[list[dict], dict]:
    """
    Build the large-cap universe for a single fire.
    Returns (universe_rows, fire_summary).
    """
    fire_id = fire["fire_id"]
    n_total = len(rows)

    # Filter to eligible rows for percentile computation
    eligible_rows = [r for r in rows if r.get("eligible") == 1]
    n_eligible = len(eligible_rows)

    fire_summary = {
        "fire_id": fire_id,
        "fire_time_utc": fire["fire_time_utc"],
        "fire_time_epoch": fire["fire_time_epoch"],
        "n_total": n_total,
        "n_eligible": n_eligible,
        "n_largecap": 0,
        "liq_threshold": None,
        "vol_threshold": None,
        "fdv_threshold": None,
        "skipped": 0,
        "skip_reason": None,
    }

    # Skip if too few eligible rows for meaningful percentiles
    if n_eligible < config.min_eligible_per_fire:
        fire_summary["skipped"] = 1
        fire_summary["skip_reason"] = f"n_eligible={n_eligible} < min={config.min_eligible_per_fire}"
        # Still produce rows but all marked largecap_eligible=0
        universe_rows = []
        for r in rows:
            universe_rows.append({
                **r,
                "liq_pctile_fire": None,
                "vol_pctile_fire": None,
                "fdv_pctile_fire": None,
                "fire_eligible_count": n_eligible,
                "fire_largecap_count": 0,
                "largecap_eligible": 0,
                "gate_fail_reason": "fire_skipped_too_few_eligible",
                "config_liq_pctile": config.liq_percentile,
                "config_vol_pctile": config.vol_percentile,
                "config_age_floor": config.age_floor_hours,
                "config_fdv_pctile": config.fdv_percentile,
            })
        return universe_rows, fire_summary

    # Compute fire-level percentile thresholds
    liq_values = [r["liq_usd"] for r in eligible_rows if r.get("liq_usd")]
    vol_values = [r["vol_h24"] for r in eligible_rows if r.get("vol_h24") and r["vol_h24"] > 0]
    fdv_values = [(r.get("fdv") or r.get("market_cap")) for r in eligible_rows
                  if (r.get("fdv") or r.get("market_cap")) and (r.get("fdv") or r.get("market_cap")) > 0]

    liq_threshold = compute_percentile(liq_values, config.liq_percentile)
    vol_threshold = compute_percentile(vol_values, config.vol_percentile)
    fdv_threshold = compute_percentile(fdv_values, config.fdv_percentile)

    fire_summary["liq_threshold"] = liq_threshold
    fire_summary["vol_threshold"] = vol_threshold
    fire_summary["fdv_threshold"] = fdv_threshold

    # Evaluate each row
    universe_rows = []
    n_largecap = 0

    for r in rows:
        passes, reason = evaluate_membership(r, liq_threshold, vol_threshold, fdv_threshold, config)
        if passes:
            n_largecap += 1

        universe_rows.append({
            **r,
            "liq_pctile_fire": percentile_rank(r.get("liq_usd"), liq_values),
            "vol_pctile_fire": percentile_rank(r.get("vol_h24"), vol_values),
            "fdv_pctile_fire": percentile_rank(r.get("fdv") or r.get("market_cap"), fdv_values),
            "fire_eligible_count": n_eligible,
            "fire_largecap_count": n_largecap,  # will be updated below
            "largecap_eligible": 1 if passes else 0,
            "gate_fail_reason": reason,
            "config_liq_pctile": config.liq_percentile,
            "config_vol_pctile": config.vol_percentile,
            "config_age_floor": config.age_floor_hours,
            "config_fdv_pctile": config.fdv_percentile,
        })

    # Backfill correct largecap count for all rows in this fire
    for ur in universe_rows:
        ur["fire_largecap_count"] = n_largecap

    fire_summary["n_largecap"] = n_largecap
    return universe_rows, fire_summary


def write_to_db(out_conn: sqlite3.Connection, universe_rows: list[dict], fire_summary: dict):
    """Write universe rows and fire summary to the output database."""
    for r in universe_rows:
        out_conn.execute("""
            INSERT OR REPLACE INTO largecap_universe (
                fire_id, fire_time_utc, fire_time_epoch,
                candidate_mint, symbol, pool_address, pool_type, lane,
                eligible, liq_usd, vol_h24, fdv, market_cap, age_hours, price_usd,
                liq_pctile_fire, vol_pctile_fire, fdv_pctile_fire,
                fire_eligible_count, fire_largecap_count,
                largecap_eligible, gate_fail_reason,
                config_liq_pctile, config_vol_pctile, config_age_floor, config_fdv_pctile
            ) VALUES (
                :fire_id, :fire_time_utc, :fire_time_epoch,
                :candidate_mint, :sym, :pool_address, :pool_type, :lane,
                :eligible, :liq_usd, :vol_h24, :fdv, :market_cap, :age_hours, :price_usd,
                :liq_pctile_fire, :vol_pctile_fire, :fdv_pctile_fire,
                :fire_eligible_count, :fire_largecap_count,
                :largecap_eligible, :gate_fail_reason,
                :config_liq_pctile, :config_vol_pctile, :config_age_floor, :config_fdv_pctile
            )
        """, r)

    out_conn.execute("""
        INSERT OR REPLACE INTO largecap_fire_summary (
            fire_id, fire_time_utc, fire_time_epoch,
            n_total, n_eligible, n_largecap,
            liq_threshold, vol_threshold, fdv_threshold,
            skipped, skip_reason
        ) VALUES (
            :fire_id, :fire_time_utc, :fire_time_epoch,
            :n_total, :n_eligible, :n_largecap,
            :liq_threshold, :vol_threshold, :fdv_threshold,
            :skipped, :skip_reason
        )
    """, fire_summary)


def write_to_csv(csv_path: str, universe_rows: list[dict]):
    """Append universe rows to CSV."""
    if not universe_rows:
        return
    fieldnames = [
        "fire_id", "fire_time_utc", "candidate_mint", "sym", "pool_type", "lane",
        "eligible", "liq_usd", "vol_h24", "fdv", "age_hours", "price_usd",
        "liq_pctile_fire", "vol_pctile_fire", "fdv_pctile_fire",
        "fire_eligible_count", "fire_largecap_count",
        "largecap_eligible", "gate_fail_reason",
    ]
    write_header = not Path(csv_path).exists() or Path(csv_path).stat().st_size == 0
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerows(universe_rows)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Point-in-time Large-Cap Universe Builder")
    parser.add_argument("--db-path", required=True, help="Path to frozen feature_tape_v2 database")
    parser.add_argument("--output-db", default=None, help="Output SQLite database path")
    parser.add_argument("--output-csv", default=None, help="Output CSV path")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--liq-pctile", type=float, default=75.0, help="Liquidity percentile gate")
    parser.add_argument("--vol-pctile", type=float, default=50.0, help="Volume percentile gate")
    parser.add_argument("--age-floor", type=float, default=24.0, help="Minimum age in hours")
    parser.add_argument("--fdv-pctile", type=float, default=50.0, help="FDV percentile gate")
    args = parser.parse_args()

    config = MembershipConfig(
        liq_percentile=args.liq_pctile,
        vol_percentile=args.vol_pctile,
        age_floor_hours=args.age_floor,
        fdv_percentile=args.fdv_pctile,
    )

    log.info("Opening source database: %s", args.db_path)
    src_conn = sqlite3.connect(args.db_path)

    fires = get_fires(src_conn)
    log.info("Found %d fires", len(fires))

    out_conn = None
    if args.output_db and not args.dry_run:
        out_conn = sqlite3.connect(args.output_db)
        out_conn.execute(CREATE_UNIVERSE_TABLE)
        out_conn.execute(CREATE_FIRE_SUMMARY_TABLE)

    total_rows = 0
    total_largecap = 0
    total_skipped_fires = 0

    for fire in fires:
        rows = get_fire_rows(src_conn, fire["fire_id"])
        universe_rows, fire_summary = build_universe_for_fire(fire, rows, config)

        n_lc = sum(1 for r in universe_rows if r["largecap_eligible"] == 1)
        total_rows += len(universe_rows)
        total_largecap += n_lc
        if fire_summary["skipped"]:
            total_skipped_fires += 1

        if args.dry_run:
            log.info(
                "Fire %s: %d total, %d eligible, %d largecap%s",
                fire["fire_id"][:8],
                fire_summary["n_total"],
                fire_summary["n_eligible"],
                n_lc,
                " [SKIPPED]" if fire_summary["skipped"] else "",
            )
        else:
            if out_conn:
                write_to_db(out_conn, universe_rows, fire_summary)
            if args.output_csv:
                write_to_csv(args.output_csv, universe_rows)

    if out_conn:
        out_conn.commit()
        out_conn.close()

    src_conn.close()

    log.info("═" * 60)
    log.info("Universe build complete")
    log.info("  Fires: %d (%d skipped)", len(fires), total_skipped_fires)
    log.info("  Total rows: %d", total_rows)
    log.info("  Large-cap eligible: %d (%.1f%%)", total_largecap,
             100 * total_largecap / total_rows if total_rows else 0)
    log.info("  Config: liq_P%.0f, vol_P%.0f, age>=%.0fh, fdv_P%.0f",
             config.liq_percentile, config.vol_percentile,
             config.age_floor_hours, config.fdv_percentile)


if __name__ == "__main__":
    main()
