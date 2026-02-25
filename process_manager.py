#!/usr/bin/env python3
"""
ET Pipeline Process Manager
- Ensures exactly one instance of each service
- Auto-restarts on crash
- Uses lockfile to prevent duplicate managers
- Logs to logs/process_manager.log
"""
import os
import sys
import time
import signal
import subprocess
import logging
from pathlib import Path

WORKDIR = Path('/root/solana_trader')
LOCKFILE = WORKDIR / 'process_manager.pid'
LOGFILE = WORKDIR / 'logs' / 'process_manager.log'

SERVICES = [
    ('et_universe_scanner', 'et_universe_scanner.py', 'logs/et_universe_scanner.log'),
    ('et_microstructure',   'et_microstructure.py',   'logs/et_microstructure.log'),
    ('et_shadow_trader_v1',  'et_shadow_trader_v1.py',  'logs/et_shadow_trader_v1.log'),
    ('pf_graduation_stream','pf_graduation_stream.py', 'logs/pf_graduation_stream.log'),
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [process_manager] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(str(LOGFILE)),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger('process_manager')

def acquire_lock():
    if LOCKFILE.exists():
        try:
            old_pid = int(LOCKFILE.read_text().strip())
            os.kill(old_pid, 0)  # Check if process exists
            log.error(f'Process manager already running as PID {old_pid}, exiting')
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass  # Old PID is dead, take over
    LOCKFILE.write_text(str(os.getpid()))

def release_lock():
    try:
        LOCKFILE.unlink()
    except FileNotFoundError:
        pass

def kill_duplicates(script_name):
    """Kill all instances of a script, return True if any were running."""
    result = subprocess.run(
        ['pgrep', '-f', script_name],
        capture_output=True, text=True
    )
    pids = [int(p) for p in result.stdout.strip().split('\n') if p.strip()]
    if len(pids) > 1:
        log.warning(f'Dedup {script_name}: {len(pids)} instances, killing all')
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(2)
        return True
    elif len(pids) == 1:
        return False  # Exactly one, good
    return False  # None running

def is_running(script_name):
    result = subprocess.run(
        ['pgrep', '-f', script_name],
        capture_output=True, text=True
    )
    pids = [p for p in result.stdout.strip().split('\n') if p.strip()]
    return len(pids) == 1, len(pids)

def start_service(name, script, logfile):
    log_path = WORKDIR / logfile
    log.info(f'Starting {name}')
    with open(str(log_path), 'a') as lf:
        proc = subprocess.Popen(
            [sys.executable, str(WORKDIR / script)],
            cwd=str(WORKDIR),
            stdout=lf,
            stderr=lf,
            start_new_session=True
        )
    log.info(f'Started {name} PID={proc.pid}')
    return proc.pid

def ensure_service(name, script, logfile):
    running, count = is_running(script)
    if count == 0:
        start_service(name, script, logfile)
    elif count > 1:
        log.warning(f'{name}: {count} instances running, killing all and restarting')
        kill_duplicates(script)
        time.sleep(2)
        start_service(name, script, logfile)

def main():
    os.chdir(str(WORKDIR))
    acquire_lock()
    
    def handle_exit(sig, frame):
        log.info('Process manager shutting down')
        release_lock()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)
    
    log.info(f'Process manager started (PID={os.getpid()})')
    
    # Initial cleanup: kill any duplicates
    for name, script, logfile in SERVICES:
        kill_duplicates(script)
    time.sleep(3)
    
    # Main loop
    while True:
        for name, script, logfile in SERVICES:
            try:
                ensure_service(name, script, logfile)
            except Exception as e:
                log.error(f'Error managing {name}: {e}')
        time.sleep(30)

if __name__ == '__main__':
    main()
