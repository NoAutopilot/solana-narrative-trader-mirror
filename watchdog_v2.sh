#!/bin/bash
# Watchdog v2 for ET pipeline services
# Uses PID lockfile to prevent duplicate instances
# Usage: bash watchdog_v2.sh &

WORKDIR=/root/solana_trader
LOCKFILE=$WORKDIR/watchdog.pid
LOG=$WORKDIR/logs/watchdog.log

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $1" >> $LOG; }

# Single-instance enforcement via lockfile
if [ -f "$LOCKFILE" ]; then
    OLD_PID=$(cat "$LOCKFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Watchdog already running as PID $OLD_PID, exiting"
        exit 0
    fi
fi
echo $$ > "$LOCKFILE"
trap "rm -f $LOCKFILE; exit" INT TERM EXIT

log "Watchdog v2 started (PID=$$)"

# Kill all extra instances of a script, keep only the oldest
dedup_service() {
    local script=$1
    local pids=($(pgrep -f "$script" | sort -n))
    if [ ${#pids[@]} -gt 1 ]; then
        log "Dedup $script: ${#pids[@]} instances -> keeping oldest PID ${pids[0]}"
        for pid in "${pids[@]:1}"; do
            kill "$pid" 2>/dev/null
        done
    fi
}

# Ensure exactly one instance of a service is running
ensure_running() {
    local script=$1
    local logfile=$2
    local count=$(pgrep -cf "$script" 2>/dev/null || echo 0)
    if [ "$count" -eq 0 ]; then
        log "RESTART $script"
        cd $WORKDIR && nohup python3 "$script" >> "$logfile" 2>&1 &
        sleep 2
    elif [ "$count" -gt 1 ]; then
        dedup_service "$script"
    fi
}

# Initial dedup pass
sleep 3
dedup_service "et_universe_scanner.py"
dedup_service "et_microstructure.py"
dedup_service "et_shadow_trader.py"
dedup_service "pf_graduation_stream.py"
log "Initial dedup complete"

# Main loop: check every 30s
while true; do
    ensure_running "et_universe_scanner.py" "$WORKDIR/logs/et_universe_scanner.log"
    ensure_running "et_microstructure.py"   "$WORKDIR/logs/et_microstructure.log"
    ensure_running "et_shadow_trader.py"    "$WORKDIR/logs/et_shadow_trader.log"
    ensure_running "pf_graduation_stream.py" "$WORKDIR/logs/pf_graduation_stream.log"
    sleep 30
done
