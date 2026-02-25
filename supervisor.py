"""
Supervisor — Process Watchdog
─────────────────────────────
Monitors paper_trader.py and restarts it if it crashes.
Also monitors flask_dashboard.py.

Usage: python3 supervisor.py
"""

import os
import sys
import time
import signal
import subprocess
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SUPERVISOR] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "supervisor.log")),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("supervisor")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MANAGED_PROCESSES = {
    "paper_trader": {
        "cmd": [sys.executable, os.path.join(BASE_DIR, "paper_trader.py")],
        "restart_delay": 10,
        "max_restarts_per_hour": 10,
    },
    "et_universe_scanner": {
        "cmd": [sys.executable, os.path.join(BASE_DIR, "et_universe_scanner.py")],
        "restart_delay": 15,
        "max_restarts_per_hour": 6,
    },
    "et_microstructure": {
        "cmd": [sys.executable, os.path.join(BASE_DIR, "et_microstructure.py")],
        "restart_delay": 15,
        "max_restarts_per_hour": 6,
    },
    "et_shadow_trader_v1": {
        "cmd": [sys.executable, os.path.join(BASE_DIR, "et_shadow_trader_v1.py")],
        "restart_delay": 15,
        "max_restarts_per_hour": 6,
    },
    "pf_graduation_stream": {
        "cmd": [sys.executable, os.path.join(BASE_DIR, "pf_graduation_stream.py")],
        "restart_delay": 20,
        "max_restarts_per_hour": 6,
    },
    "flask_dashboard": {
        "cmd": [sys.executable, os.path.join(BASE_DIR, "flask_dashboard.py")],
        "restart_delay": 5,
        "max_restarts_per_hour": 20,
    },
}

processes = {}
restart_counts = {}
shutdown_flag = False


def kill_existing(name):
    """Kill any existing process with the same script name to prevent duplicates."""
    script_name = f"{name}.py"
    try:
        result = subprocess.run(
            ["pgrep", "-f", script_name], capture_output=True, text=True
        )
        pids = [int(p) for p in result.stdout.strip().split() if p.strip()]
        my_pid = os.getpid()
        for pid in pids:
            if pid != my_pid:
                logger.info(f"Killing existing {name} (PID {pid})")
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    except Exception:
        pass


def start_process(name):
    config = MANAGED_PROCESSES[name]
    log_file = os.path.join(LOGS_DIR, f"{name}.log")
    # Kill any existing instance first
    kill_existing(name)
    time.sleep(1)
    logger.info(f"Starting {name}...")
    try:
        with open(log_file, "a") as lf:
            proc = subprocess.Popen(
                config["cmd"], stdout=lf, stderr=subprocess.STDOUT, cwd=BASE_DIR,
            )
        processes[name] = proc
        logger.info(f"{name} started (PID {proc.pid})")
        return proc
    except Exception as e:
        logger.error(f"Failed to start {name}: {e}")
        return None


def check_restart_limit(name):
    config = MANAGED_PROCESSES[name]
    now = time.time()
    if name not in restart_counts:
        restart_counts[name] = []
    restart_counts[name] = [t for t in restart_counts[name] if now - t < 3600]
    if len(restart_counts[name]) >= config["max_restarts_per_hour"]:
        logger.error(f"{name} exceeded {config['max_restarts_per_hour']} restarts/hour.")
        return False
    restart_counts[name].append(now)
    return True


def handle_shutdown(signum, frame):
    global shutdown_flag
    logger.info(f"Signal {signum}, shutting down all processes...")
    shutdown_flag = True
    for name, proc in processes.items():
        if proc and proc.poll() is None:
            logger.info(f"Terminating {name} (PID {proc.pid})")
            proc.terminate()
    for name, proc in processes.items():
        if proc:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    sys.exit(0)


def acquire_lock():
    """Prevent multiple supervisors from running."""
    pid_file = os.path.join(BASE_DIR, "supervisor.pid")
    # Check if another supervisor is running
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)  # Check if process exists
            logger.error(f"Another supervisor is already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # Old process is dead, take over
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    return pid_file


def main():
    logger.info("=" * 50)
    logger.info("Supervisor starting")
    logger.info(f"Managing: {list(MANAGED_PROCESSES.keys())}")
    logger.info("=" * 50)

    pid_file = acquire_lock()
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    for name in MANAGED_PROCESSES:
        start_process(name)

    while not shutdown_flag:
        time.sleep(5)
        for name, config in MANAGED_PROCESSES.items():
            proc = processes.get(name)
            if proc is None or proc.poll() is not None:
                exit_code = proc.returncode if proc else "never started"
                logger.warning(f"{name} exited (code={exit_code})")
                if check_restart_limit(name):
                    delay = config["restart_delay"]
                    logger.info(f"Restarting {name} in {delay}s...")
                    time.sleep(delay)
                    start_process(name)
                else:
                    logger.error(f"{name} restart limit hit, cooldown 5 min...")
                    time.sleep(300)
                    restart_counts[name] = []
                    start_process(name)

    logger.info("Supervisor stopped.")


if __name__ == "__main__":
    main()
