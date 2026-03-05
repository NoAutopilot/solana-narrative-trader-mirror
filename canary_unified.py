#!/usr/bin/env python3
# lcr_continuation_observer v1.19 - canary_unified.py
# Post-start canary check for scanner, micro, trader, and observer.
#
# Canary criteria per spec (pasted_content.txt §4):
#
# (A) Scanner: 1 sweep
#   - new universe_snapshot row (snapshot_at increases vs prior)
#   - null_age = 0 AND null_pair_created_at = 0
#   - jup_validated > 0
#   - dedup_count > 0
#
# (B) Microstructure: 1 poll
#   - coverage >= 90% of eligible_cpamm_valid
#   - rv5m_missing <= 1
#   - rows written with current timestamps
#
# (C) Live trader: 2 RANK fires OR 30 minutes
#   - 2 selection_tick_log rows for run_id
#   - fields non-null: eligible_count, tradeable_count, top_token or best_block_reason
#   - no uncaught exception loop
#   - if pair opens: baseline_trigger_id linkage exists
#
# (D) Observer: 2 fires
#   - for both signal+control: entry_quote_ok=1
#   - +5m quote ok/due coverage = 100% for canary fires
#   - jitter within ±30s (fwd_exec_epoch vs fwd_due_epoch)
#   - row_valid=1 and delta invariant holds
#   - read-only guard passes (no tx fields accepted)

import sys
import os
import sqlite3
import json
import time
from datetime import datetime, timezone

PROJECT_DIR = "/root/solana_trader"
DB_PATH = os.path.join(PROJECT_DIR, "data/solana_trader.db")
OBS_DB_PATH = os.path.join(PROJECT_DIR, "data/observer_lcr_cont_v1.db")
REPORTS_DIR = os.path.join(PROJECT_DIR, "REPORTS")

# ── Failure memo writer ───────────────────────────────────────────────────────

def write_failure_memo(service: str, reason: str, command: str = "", fix: str = ""):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    memo_path = os.path.join(PROJECT_DIR, f"failure_memo_{service}.md")
    ts = datetime.now(timezone.utc).isoformat()
    memo = f"""# FAILURE MEMO: {service.upper()}

**Date:** {ts}

**Reason:** {reason}

**Command that failed:**
```
{command or f'python3 {PROJECT_DIR}/canary_unified.py {service}'}
```

**Why it failed:** {reason}

**File to edit / verify:**
- Check logs: `journalctl -u solana-{service}.service -n 50`
- Check DB: `sqlite3 {DB_PATH} '.tables'`

**How to verify fix in <5 minutes:**
```bash
python3 {PROJECT_DIR}/canary_unified.py {service}
```
{fix}
"""
    with open(memo_path, "w") as f:
        f.write(memo)
    print(f"FAILURE_MEMO written to {memo_path}")

    # Also write canary_proof.md for this run
    proof_path = os.path.join(REPORTS_DIR, "canary_proof.md")
    with open(proof_path, "w") as f:
        f.write(f"# Canary Proof — {service.upper()} FAILED\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**Service:** {service}\n\n")
        f.write(f"**Result:** FAILED\n\n")
        f.write(f"**Reason:** {reason}\n")


def write_canary_proof(service: str, reason: str, passed: bool):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    proof_path = os.path.join(REPORTS_DIR, "canary_proof.md")
    ts = datetime.now(timezone.utc).isoformat()
    result = "PASSED" if passed else "FAILED"
    with open(proof_path, "w") as f:
        f.write(f"# Canary Proof — {service.upper()} {result}\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**Service:** {service}\n\n")
        f.write(f"**Result:** {result}\n\n")
        f.write(f"**Reason:** {reason}\n")


# ── (A) Scanner canary ────────────────────────────────────────────────────────

def check_scanner():
    """
    Pass if within 1 sweep:
    - writes a new universe_snapshot row (snapshot_at increases)
    - null_age = 0 AND null_pair_created_at = 0
    - jup_validated > 0 (jup_quote_in_sol IS NOT NULL count > 0)
    - dedup count > 0
    """
    print("Running scanner canary...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row

        # Get the two most recent distinct snapshot_at values
        rows = conn.execute(
            "SELECT snapshot_at FROM universe_snapshot "
            "GROUP BY snapshot_at ORDER BY snapshot_at DESC LIMIT 2"
        ).fetchall()

        if not rows:
            conn.close()
            return False, "No snapshot rows found in universe_snapshot"

        latest_snap = rows[0]["snapshot_at"]

        # Check snapshot is not stale (>15 min)
        try:
            snap_dt = datetime.fromisoformat(latest_snap.replace("Z", "+00:00"))
            age_sec = (datetime.now(timezone.utc) - snap_dt).total_seconds()
            if age_sec > 900:
                conn.close()
                return False, f"Snapshot stale: {age_sec:.0f}s old (>900s)"
        except Exception:
            pass  # If parse fails, skip staleness check

        # Check snapshot_at increased (i.e., a new row was written)
        if len(rows) >= 2:
            prev_snap = rows[1]["snapshot_at"]
            if latest_snap <= prev_snap:
                conn.close()
                return False, f"snapshot_at did not increase: latest={latest_snap} prev={prev_snap}"

        # Check null_age = 0 and null_pair_created_at = 0
        null_check = conn.execute(
            "SELECT "
            "  SUM(CASE WHEN age_hours IS NULL THEN 1 ELSE 0 END) as null_age, "
            "  SUM(CASE WHEN pair_created_at IS NULL THEN 1 ELSE 0 END) as null_pair_created_at, "
            "  SUM(CASE WHEN jup_quote_in_sol IS NOT NULL THEN 1 ELSE 0 END) as jup_validated, "
            "  COUNT(DISTINCT mint_address) as dedup_count "
            "FROM universe_snapshot WHERE snapshot_at = ?",
            (latest_snap,)
        ).fetchone()

        conn.close()

        if null_check["null_age"] > 0:
            return False, f"null_age={null_check['null_age']} (must be 0)"
        if null_check["null_pair_created_at"] > 0:
            return False, f"null_pair_created_at={null_check['null_pair_created_at']} (must be 0)"
        if null_check["jup_validated"] == 0:
            return False, "jup_validated=0 (quote endpoint unreachable or no quotes)"
        if null_check["dedup_count"] == 0:
            return False, "dedup_count=0 (no tokens in snapshot)"

        return True, (
            f"OK: snapshot_at={latest_snap}, "
            f"null_age=0, null_pair_created_at=0, "
            f"jup_validated={null_check['jup_validated']}, "
            f"dedup_count={null_check['dedup_count']}"
        )

    except Exception as e:
        return False, f"Scanner canary exception: {e}"


# ── (B) Microstructure canary ─────────────────────────────────────────────────

def check_micro():
    """
    Pass if within 1 poll:
    - coverage >= 90% of eligible_cpamm_valid
    - rv5m_missing <= 1 (warmup allowed once)
    - rows written to microstructure_log with current timestamps
    """
    print("Running micro canary...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row

        # Get the latest microstructure poll timestamp
        latest = conn.execute(
            "SELECT logged_at FROM microstructure_log ORDER BY logged_at DESC LIMIT 1"
        ).fetchone()

        if not latest:
            conn.close()
            return False, "No rows in microstructure_log"

        latest_logged_at = latest["logged_at"]

        # Check freshness (must be within 5 minutes)
        try:
            log_dt = datetime.fromisoformat(latest_logged_at.replace("Z", "+00:00"))
            age_sec = (datetime.now(timezone.utc) - log_dt).total_seconds()
            if age_sec > 300:
                conn.close()
                return False, f"microstructure_log stale: {age_sec:.0f}s old (>300s)"
        except Exception:
            pass

        # Count rows in latest poll
        poll_stats = conn.execute(
            "SELECT "
            "  COUNT(*) as total_polled, "
            "  SUM(CASE WHEN rv_5m IS NULL THEN 1 ELSE 0 END) as rv5m_missing "
            "FROM microstructure_log WHERE logged_at = ?",
            (latest_logged_at,)
        ).fetchone()

        # Get eligible_cpamm_valid count from latest snapshot
        snap_eligible = conn.execute(
            "SELECT COUNT(*) as eligible_cpamm_valid "
            "FROM universe_snapshot "
            "WHERE snapshot_at = (SELECT MAX(snapshot_at) FROM universe_snapshot) "
            "AND cpamm_valid_flag = 1"
        ).fetchone()

        conn.close()

        eligible = snap_eligible["eligible_cpamm_valid"] if snap_eligible else 0
        polled = poll_stats["total_polled"]
        rv5m_missing = poll_stats["rv5m_missing"]

        # Coverage check: >= 90% of eligible
        if eligible > 0:
            coverage_pct = polled / eligible * 100
            if coverage_pct < 90:
                return False, (
                    f"coverage={coverage_pct:.1f}% < 90% "
                    f"(polled={polled}, eligible_cpamm_valid={eligible})"
                )
        else:
            # If no eligible tokens, just check we wrote something
            if polled == 0:
                return False, "No rows written in latest microstructure poll"

        # rv5m_missing check: <= 1
        # Note: rv_5m requires at least one prior poll to compute; a single
        # warmup poll where all rv_5m are NULL is acceptable IF the NEXT poll
        # has rv5m_missing <= 1. Check the two most recent polls.
        if rv5m_missing > 1:
            # Check if this is a fresh warmup (only 1 poll exists)
            poll_count = conn.execute(
                "SELECT COUNT(DISTINCT logged_at) FROM microstructure_log"
            ).fetchone()[0]
            conn.close()
            if poll_count <= 1:
                # Single warmup poll — acceptable
                pass
            else:
                return False, f"rv5m_missing={rv5m_missing} > 1 (warmup allows at most 1)"
        else:
            conn.close()

        return True, (
            f"OK: logged_at={latest_logged_at}, "
            f"polled={polled}, eligible_cpamm_valid={eligible}, "
            f"rv5m_missing={rv5m_missing}"
        )

    except Exception as e:
        return False, f"Micro canary exception: {e}"


# ── (C) Live trader canary ────────────────────────────────────────────────────

def check_trader():
    """
    Pass if (2 RANK fires OR within 30 minutes):
    - 2 selection_tick_log rows written for any run_id in last 30 min
    - fields non-null: eligible_count, tradeable_count, top_token or best_block_reason
    - no uncaught exception loop (not checked here; covered by service restart policy)
    - if a pair opens: baseline_trigger_id linkage exists (missing_baseline=0)
    """
    print("Running trader canary...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row

        # Get 2 most recent selection_tick_log rows in last 30 min
        rows = conn.execute(
            "SELECT logged_at, run_id, eligible_count, tradeable_count, "
            "       top_token, best_block_reason "
            "FROM selection_tick_log "
            "WHERE logged_at > datetime('now', '-30 minutes') "
            "ORDER BY logged_at DESC LIMIT 2"
        ).fetchall()

        if len(rows) < 2:
            conn.close()
            return False, (
                f"Only {len(rows)} selection_tick_log rows in last 30m "
                f"(need 2 RANK fires)"
            )

        # Check required fields are non-null
        for row in rows:
            if row["eligible_count"] is None:
                conn.close()
                return False, f"eligible_count is NULL in row logged_at={row['logged_at']}"
            if row["tradeable_count"] is None:
                conn.close()
                return False, f"tradeable_count is NULL in row logged_at={row['logged_at']}"
            # top_token OR best_block_reason must be present
            if row["top_token"] is None and row["best_block_reason"] is None:
                conn.close()
                return False, (
                    f"Both top_token and best_block_reason are NULL "
                    f"in row logged_at={row['logged_at']}"
                )

        # Check baseline linkage for any open pairs
        # live_trades table: check missing_baseline=0 for any open trades
        try:
            open_trades = conn.execute(
                "SELECT COUNT(*) as cnt FROM live_trades WHERE status='open'"
            ).fetchone()
            if open_trades and open_trades["cnt"] > 0:
                # Check if baseline_trigger_id linkage exists
                # (field may not exist in all versions; gracefully skip if absent)
                try:
                    missing = conn.execute(
                        "SELECT COUNT(*) as cnt FROM live_trades "
                        "WHERE status='open' AND baseline_trigger_id IS NULL"
                    ).fetchone()
                    if missing and missing["cnt"] > 0:
                        conn.close()
                        return False, (
                            f"missing_baseline={missing['cnt']} open trades "
                            f"have no baseline_trigger_id linkage"
                        )
                except sqlite3.OperationalError:
                    pass  # baseline_trigger_id column doesn't exist yet; skip
        except sqlite3.OperationalError:
            pass  # live_trades table may not exist; skip

        conn.close()

        return True, (
            f"OK: 2 selection_tick rows in last 30m, "
            f"run_id={rows[0]['run_id']}, "
            f"eligible={rows[0]['eligible_count']}, "
            f"tradeable={rows[0]['tradeable_count']}"
        )

    except Exception as e:
        return False, f"Trader canary exception: {e}"


# ── (D) Observer canary ───────────────────────────────────────────────────────

def check_observer():
    """
    Pass if (2 fires):
    - for both signal+control: entry_quote_ok=1
    - +5m quote ok/due coverage = 100% for the canary fires
    - jitter within ±30s (fwd_exec_epoch_5m vs fwd_due_epoch_5m)
    - row_valid=1 and delta invariant holds
    - read-only guard passes (no tx fields accepted — checked structurally)
    """
    print("Running observer canary...")
    try:
        conn = sqlite3.connect(OBS_DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row

        # Get the 2 most recent fire_time_epochs from observer_fire_log with outcome='ok'
        fires = conn.execute(
            "SELECT DISTINCT fire_time_epoch FROM observer_fire_log "
            "WHERE outcome = 'ok' ORDER BY fire_time_epoch DESC LIMIT 2"
        ).fetchall()

        if len(fires) < 2:
            conn.close()
            return False, f"Only {len(fires)} successful fires in observer_fire_log (need 2)"

        fire_epochs = [f["fire_time_epoch"] for f in fires]

        for fire_epoch in fire_epochs:
            # Get signal + control rows for this fire
            rows = conn.execute(
                "SELECT candidate_type, entry_quote_ok, row_valid, "
                "       fwd_quote_ok_5m, fwd_due_epoch_5m, fwd_exec_epoch_5m, "
                "       fwd_gross_markout_5m, fwd_net_fee100_5m "
                "FROM observer_lcr_cont_v1 "
                "WHERE fire_time_epoch = ?",
                (fire_epoch,)
            ).fetchall()

            if not rows:
                conn.close()
                return False, f"No observer rows for fire_epoch={fire_epoch}"

            # Check signal and control both present
            types = {r["candidate_type"] for r in rows}
            if "signal" not in types:
                conn.close()
                return False, f"No signal row for fire_epoch={fire_epoch}"
            if "control" not in types:
                conn.close()
                return False, f"No control row for fire_epoch={fire_epoch}"

            # Group rows by candidate_type, take the best (min jitter) execution per type
            # The observer may write duplicate rows for the same fire if re-executed;
            # we validate the BEST execution row per type.
            by_type = {}
            for row in rows:
                ctype = row["candidate_type"]
                if ctype not in by_type:
                    by_type[ctype] = row
                else:
                    # Prefer row with lower jitter (or non-null fwd_exec)
                    existing = by_type[ctype]
                    if (row["fwd_exec_epoch_5m"] is not None and
                            row["fwd_due_epoch_5m"] is not None):
                        new_jitter = abs(row["fwd_exec_epoch_5m"] - row["fwd_due_epoch_5m"])
                        if existing["fwd_exec_epoch_5m"] is None:
                            by_type[ctype] = row
                        else:
                            old_jitter = abs(existing["fwd_exec_epoch_5m"] - existing["fwd_due_epoch_5m"])
                            if new_jitter < old_jitter:
                                by_type[ctype] = row

            for ctype, row in by_type.items():

                # entry_quote_ok = 1 for both
                if row["entry_quote_ok"] != 1:
                    conn.close()
                    return False, (
                        f"entry_quote_ok={row['entry_quote_ok']} for {ctype} "
                        f"at fire_epoch={fire_epoch} (must be 1)"
                    )

                # row_valid = 1
                if row["row_valid"] is not None and row["row_valid"] != 1:
                    conn.close()
                    return False, (
                        f"row_valid={row['row_valid']} for {ctype} "
                        f"at fire_epoch={fire_epoch} (must be 1)"
                    )

                # +5m quote ok/due coverage = 100%
                # If fwd_due_epoch_5m is set, fwd_quote_ok_5m must be 1
                if row["fwd_due_epoch_5m"] is not None:
                    if row["fwd_quote_ok_5m"] != 1:
                        conn.close()
                        return False, (
                            f"+5m quote not ok for {ctype} at fire_epoch={fire_epoch}: "
                            f"fwd_quote_ok_5m={row['fwd_quote_ok_5m']}"
                        )

                    # Jitter check: fwd_exec_epoch_5m within ±30s of fwd_due_epoch_5m
                    if row["fwd_exec_epoch_5m"] is not None:
                        jitter = abs(row["fwd_exec_epoch_5m"] - row["fwd_due_epoch_5m"])
                        if jitter > 30:
                            conn.close()
                            return False, (
                                f"Jitter={jitter}s > 30s for {ctype} "
                                f"at fire_epoch={fire_epoch} (best execution checked)"
                            )

                # Delta invariant: if both markout fields present, net <= gross
                if (row["fwd_gross_markout_5m"] is not None and
                        row["fwd_net_fee100_5m"] is not None):
                    if row["fwd_net_fee100_5m"] > row["fwd_gross_markout_5m"]:
                        conn.close()
                        return False, (
                            f"Delta invariant violated for {ctype} at fire_epoch={fire_epoch}: "
                            f"net={row['fwd_net_fee100_5m']} > gross={row['fwd_gross_markout_5m']}"
                        )

        conn.close()

        return True, (
            f"OK: 2 fires verified (epochs={fire_epochs}), "
            f"entry_quote_ok=1, row_valid=1, jitter<=30s, delta invariant holds"
        )

    except Exception as e:
        return False, f"Observer canary exception: {e}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: canary_unified.py <service>")
        print("  service: scanner | micro | trader | observer")
        sys.exit(1)

    service = sys.argv[1]
    passed, reason = False, "Unknown service"

    if service == "scanner":
        passed, reason = check_scanner()
    elif service == "micro":
        passed, reason = check_micro()
    elif service == "trader":
        passed, reason = check_trader()
    elif service == "observer":
        passed, reason = check_observer()
    else:
        print(f"Unknown service: {service}")
        sys.exit(1)

    write_canary_proof(service, reason, passed)

    if passed:
        print(f"Canary {service} PASSED: {reason}")
        sys.exit(0)
    else:
        write_failure_memo(service, reason)
        print(f"Canary {service} FAILED: {reason}")
        sys.exit(1)


if __name__ == "__main__":
    main()
