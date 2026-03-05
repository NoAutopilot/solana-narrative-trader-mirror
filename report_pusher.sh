#!/bin/bash
# report_pusher.sh — v1.19 Audit Infrastructure
# Automates report generation and pushing to GitHub.
#
# Auto-push frequency per spec §5:
#   - Observer:      every 4 fires (called from observer service)
#   - Trader:        every 4 RANK fires (hourly) + on exception + on stop
#   - Scanner/micro: every 30 minutes + on canary failure
#
# ALWAYS push immediately:
#   - preflight_proof.md
#   - canary_proof.md
#   - failure_memo.md (if any)
#
# Usage:
#   ./report_pusher.sh [observer|trader|scanner|stop|failure]
#   (default: runs full report cycle — called by cron every 30 min)

set -e

PROJECT_DIR="/root/solana_trader"
REPORT_SCRIPT="$PROJECT_DIR/observer_report_lcr_cont_v1.py"
REPORTS_DIR="$PROJECT_DIR/REPORTS"
REPO_DIR="$PROJECT_DIR"
TRIGGER="${1:-cron}"
LOG_PREFIX="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [report_pusher.sh]"

mkdir -p "$REPORTS_DIR"

echo "$LOG_PREFIX Running report pusher (trigger: $TRIGGER)..."

# ── Helper: stage and push if anything changed ────────────────────────────────
push_if_changed() {
    local commit_msg="$1"
    cd "$REPO_DIR"
    # Stage REPORTS/ and any failure/canary/preflight proof files
    git add REPORTS/ failure_memo_*.md canary_proof.md preflight_proof.md \
        deployment_proof.json .deployed_sha 2>/dev/null || true

    if git diff --cached --quiet; then
        echo "$LOG_PREFIX No changes to push."
        return 0
    fi

    git commit -m "$commit_msg"
    git push origin master
    echo "$LOG_PREFIX Pushed: $commit_msg"
}

# ── Always push: preflight_proof, canary_proof, failure_memo ─────────────────
push_priority_files() {
    cd "$REPO_DIR"
    local changed=false

    for f in preflight_proof.md canary_proof.md failure_memo_*.md; do
        if [ -f "$PROJECT_DIR/$f" ]; then
            git add "$PROJECT_DIR/$f" 2>/dev/null || true
            changed=true
        fi
    done
    # Also check REPORTS/
    git add REPORTS/canary_proof.md REPORTS/preflight_proof.md 2>/dev/null || true

    if git diff --cached --quiet; then
        return 0
    fi

    git commit -m "audit: push priority files (preflight/canary/failure) $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    git push origin master
    echo "$LOG_PREFIX Priority files pushed."
}

# ── Generate observer report ──────────────────────────────────────────────────
generate_observer_report() {
    local report_file="$REPORTS_DIR/LATEST_LCR_CONT_REPORT.md"
    echo "$LOG_PREFIX Generating observer report..."
    python3 "$REPORT_SCRIPT" > "$report_file" 2>&1 || {
        echo "$LOG_PREFIX Warning: report generation failed"
        return 1
    }
    echo "$LOG_PREFIX Observer report written: $report_file"
}

# ── Trigger-based logic ───────────────────────────────────────────────────────

case "$TRIGGER" in

    observer)
        # Called every 4 fires from observer service
        generate_observer_report
        push_if_changed "reports: observer 4-fire update $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        ;;

    trader)
        # Called every 4 RANK fires (hourly) from trader service
        push_if_changed "reports: trader 4-rank-fire update $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        ;;

    failure)
        # Called immediately on any canary failure or exception
        echo "$LOG_PREFIX Failure trigger — pushing priority files immediately..."
        push_priority_files
        ;;

    stop)
        # Called on service stop (ExecStopPost or manual)
        echo "$LOG_PREFIX Stop trigger — pushing all pending reports..."
        generate_observer_report || true
        push_if_changed "reports: service stop snapshot $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        push_priority_files
        ;;

    cron|*)
        # Default: called by cron every 30 minutes
        # Covers scanner/micro auto-push + general report refresh
        generate_observer_report || true

        # Push priority files first (canary/preflight/failure if any)
        push_priority_files

        # Then push full report
        push_if_changed "reports: scheduled 30m update $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        ;;

esac

echo "$LOG_PREFIX Report pusher complete (trigger: $TRIGGER)."
