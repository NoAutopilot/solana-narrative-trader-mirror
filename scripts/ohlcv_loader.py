#!/usr/bin/env python3
"""
ohlcv_loader.py — Batch-fetch historical OHLCV candles for large-cap universe tokens.

Cold-path batch job. Runs AFTER collection completes and labels mature.
Does NOT run in real time. Does NOT modify any live table.

Data sources (in priority order):
  1. GeckoTerminal API (free, no auth, pool-address-based)
  2. Birdeye API (requires API key, higher rate limits)

Usage (after universe is built):
  python3 scripts/ohlcv_loader.py \
      --universe-db artifacts/largecap_universe_YYYYMMDD.db \
      --output-db artifacts/ohlcv_candles_YYYYMMDD.db \
      --source geckoterminal \
      --interval 15m \
      --horizon 4h

  python3 scripts/ohlcv_loader.py --dry-run \
      --universe-db artifacts/largecap_universe_YYYYMMDD.db
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # Will fail at runtime with a clear message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FetchConfig:
    """OHLCV fetch configuration."""
    source: str = "geckoterminal"       # 'geckoterminal' or 'birdeye'
    interval: str = "15m"               # candle interval
    horizon: str = "4h"                 # forward window to fetch
    chain: str = "solana"
    rate_limit_per_min: int = 28        # stay under 30/min for GeckoTerminal
    retry_max: int = 3
    retry_delay_s: float = 5.0
    birdeye_api_key: Optional[str] = None

    @property
    def interval_seconds(self) -> int:
        mapping = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
        return mapping.get(self.interval, 900)

    @property
    def horizon_seconds(self) -> int:
        mapping = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
        return mapping.get(self.horizon, 14400)


# ══════════════════════════════════════════════════════════════════════════════
# OHLCV storage schema
# ══════════════════════════════════════════════════════════════════════════════

CREATE_OHLCV_TABLE = """
CREATE TABLE IF NOT EXISTS ohlcv_candles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_session   TEXT NOT NULL,
    mint            TEXT NOT NULL,
    pool_address    TEXT NOT NULL,
    fire_id         TEXT NOT NULL,
    candle_start    TEXT NOT NULL,
    candle_end      TEXT NOT NULL,
    interval_s      INTEGER NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume_usd      REAL,
    source          TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    UNIQUE(mint, pool_address, fire_id, candle_start, interval_s)
);
"""

CREATE_FETCH_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS ohlcv_fetch_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_session   TEXT NOT NULL,
    mint            TEXT NOT NULL,
    pool_address    TEXT NOT NULL,
    fire_id         TEXT NOT NULL,
    status          TEXT NOT NULL,
    candles_fetched INTEGER DEFAULT 0,
    error_message   TEXT,
    fetched_at      TEXT NOT NULL
);
"""


# ══════════════════════════════════════════════════════════════════════════════
# Data source adapters
# ══════════════════════════════════════════════════════════════════════════════

class GeckoTerminalAdapter:
    """
    Fetch OHLCV from GeckoTerminal API.
    Endpoint: GET /api/v2/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}
    Docs: https://www.geckoterminal.com/dex-api
    """
    BASE_URL = "https://api.geckoterminal.com/api/v2"

    # GeckoTerminal timeframe mapping
    TIMEFRAME_MAP = {
        "1m": "minute",
        "5m": "minute",
        "15m": "minute",
        "1h": "hour",
        "4h": "hour",
        "1d": "day",
    }

    AGGREGATE_MAP = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 1,
        "4h": 4,
        "1d": 1,
    }

    def __init__(self, config: FetchConfig):
        self.config = config
        self.session = requests.Session() if requests else None
        self.session.headers.update({"Accept": "application/json"})

    def fetch_candles(
        self,
        pool_address: str,
        start_epoch: int,
        end_epoch: int,
    ) -> list[dict]:
        """
        Fetch OHLCV candles for a pool within a time range.
        Returns list of candle dicts.
        """
        if not self.session:
            raise RuntimeError("requests library not installed")

        timeframe = self.TIMEFRAME_MAP.get(self.config.interval, "minute")
        aggregate = self.AGGREGATE_MAP.get(self.config.interval, 15)

        url = (
            f"{self.BASE_URL}/networks/{self.config.chain}/pools/"
            f"{pool_address}/ohlcv/{timeframe}"
        )
        params = {
            "aggregate": aggregate,
            "before_timestamp": end_epoch,
            "limit": 1000,  # max per request
            "currency": "usd",
        }

        candles = []
        for attempt in range(self.config.retry_max):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 429:
                    # Rate limited — back off
                    wait = self.config.retry_delay_s * (attempt + 1)
                    log.warning("Rate limited, waiting %.1fs", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()

                ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                for c in ohlcv_list:
                    # GeckoTerminal format: [timestamp, open, high, low, close, volume]
                    if len(c) >= 6:
                        ts = int(c[0])
                        if ts >= start_epoch and ts <= end_epoch:
                            candles.append({
                                "candle_start": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                                "candle_end": datetime.fromtimestamp(
                                    ts + self.config.interval_seconds, timezone.utc
                                ).isoformat(),
                                "interval_s": self.config.interval_seconds,
                                "open": float(c[1]) if c[1] else None,
                                "high": float(c[2]) if c[2] else None,
                                "low": float(c[3]) if c[3] else None,
                                "close": float(c[4]) if c[4] else None,
                                "volume_usd": float(c[5]) if c[5] else None,
                            })
                break  # success

            except Exception as e:
                if attempt < self.config.retry_max - 1:
                    log.warning("Fetch attempt %d failed: %s", attempt + 1, e)
                    time.sleep(self.config.retry_delay_s)
                else:
                    raise

        return sorted(candles, key=lambda c: c["candle_start"])


class BirdeyeAdapter:
    """
    Fetch OHLCV from Birdeye API.
    Endpoint: GET /defi/ohlcv
    Requires API key.
    """
    BASE_URL = "https://public-api.birdeye.so"

    INTERVAL_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1H",
        "4h": "4H",
        "1d": "1D",
    }

    def __init__(self, config: FetchConfig):
        self.config = config
        if not config.birdeye_api_key:
            raise ValueError("Birdeye API key required. Set --birdeye-key or BIRDEYE_API_KEY env var.")
        self.session = requests.Session() if requests else None
        self.session.headers.update({
            "Accept": "application/json",
            "X-API-KEY": config.birdeye_api_key,
        })

    def fetch_candles(
        self,
        mint: str,
        start_epoch: int,
        end_epoch: int,
    ) -> list[dict]:
        """Fetch OHLCV candles for a token mint within a time range."""
        if not self.session:
            raise RuntimeError("requests library not installed")

        interval = self.INTERVAL_MAP.get(self.config.interval, "15m")
        url = f"{self.BASE_URL}/defi/ohlcv"
        params = {
            "address": mint,
            "type": interval,
            "time_from": start_epoch,
            "time_to": end_epoch,
        }

        candles = []
        for attempt in range(self.config.retry_max):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 429:
                    wait = self.config.retry_delay_s * (attempt + 1)
                    log.warning("Rate limited, waiting %.1fs", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()

                for c in data.get("data", {}).get("items", []):
                    ts = int(c.get("unixTime", 0))
                    if ts >= start_epoch and ts <= end_epoch:
                        candles.append({
                            "candle_start": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                            "candle_end": datetime.fromtimestamp(
                                ts + self.config.interval_seconds, timezone.utc
                            ).isoformat(),
                            "interval_s": self.config.interval_seconds,
                            "open": c.get("o"),
                            "high": c.get("h"),
                            "low": c.get("l"),
                            "close": c.get("c"),
                            "volume_usd": c.get("v"),
                        })
                break

            except Exception as e:
                if attempt < self.config.retry_max - 1:
                    log.warning("Fetch attempt %d failed: %s", attempt + 1, e)
                    time.sleep(self.config.retry_delay_s)
                else:
                    raise

        return sorted(candles, key=lambda c: c["candle_start"])


# ══════════════════════════════════════════════════════════════════════════════
# Core fetch orchestrator
# ══════════════════════════════════════════════════════════════════════════════

def get_fetch_targets(universe_db: str) -> list[dict]:
    """
    Get unique (fire_id, mint, pool_address, fire_time_epoch) pairs
    from the large-cap universe where largecap_eligible = 1.
    """
    conn = sqlite3.connect(universe_db)
    cur = conn.execute("""
        SELECT DISTINCT fire_id, candidate_mint, pool_address, fire_time_epoch
        FROM largecap_universe
        WHERE largecap_eligible = 1
        ORDER BY fire_time_epoch ASC
    """)
    targets = [
        {"fire_id": r[0], "mint": r[1], "pool_address": r[2], "fire_epoch": r[3]}
        for r in cur.fetchall()
    ]
    conn.close()
    return targets


def run_fetch(
    targets: list[dict],
    config: FetchConfig,
    output_db: str,
    fetch_session: str,
    dry_run: bool = False,
):
    """Fetch OHLCV candles for all targets."""
    log.info("Fetch targets: %d", len(targets))
    log.info("Source: %s, interval: %s, horizon: %s", config.source, config.interval, config.horizon)

    if dry_run:
        # Estimate time
        est_minutes = len(targets) / config.rate_limit_per_min
        log.info("[DRY RUN] Estimated fetch time: %.1f minutes at %d req/min",
                 est_minutes, config.rate_limit_per_min)
        return

    # Initialize adapter
    if config.source == "geckoterminal":
        adapter = GeckoTerminalAdapter(config)
    elif config.source == "birdeye":
        adapter = BirdeyeAdapter(config)
    else:
        raise ValueError(f"Unknown source: {config.source}")

    # Initialize output DB
    out_conn = sqlite3.connect(output_db)
    out_conn.execute(CREATE_OHLCV_TABLE)
    out_conn.execute(CREATE_FETCH_LOG_TABLE)

    now_utc = datetime.now(timezone.utc).isoformat()
    request_count = 0
    window_start = time.monotonic()

    for i, target in enumerate(targets):
        # Rate limiting
        request_count += 1
        if request_count >= config.rate_limit_per_min:
            elapsed = time.monotonic() - window_start
            if elapsed < 60:
                sleep_time = 60 - elapsed + 1
                log.info("Rate limit pause: %.1fs", sleep_time)
                time.sleep(sleep_time)
            request_count = 0
            window_start = time.monotonic()

        fire_epoch = target["fire_epoch"]
        start_epoch = fire_epoch
        end_epoch = fire_epoch + config.horizon_seconds

        try:
            if config.source == "geckoterminal":
                candles = adapter.fetch_candles(target["pool_address"], start_epoch, end_epoch)
            else:
                candles = adapter.fetch_candles(target["mint"], start_epoch, end_epoch)

            # Write candles
            for c in candles:
                out_conn.execute("""
                    INSERT OR IGNORE INTO ohlcv_candles (
                        fetch_session, mint, pool_address, fire_id,
                        candle_start, candle_end, interval_s,
                        open, high, low, close, volume_usd,
                        source, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fetch_session, target["mint"], target["pool_address"], target["fire_id"],
                    c["candle_start"], c["candle_end"], c["interval_s"],
                    c["open"], c["high"], c["low"], c["close"], c["volume_usd"],
                    config.source, now_utc,
                ))

            # Log success
            out_conn.execute("""
                INSERT INTO ohlcv_fetch_log (
                    fetch_session, mint, pool_address, fire_id,
                    status, candles_fetched, fetched_at
                ) VALUES (?, ?, ?, ?, 'OK', ?, ?)
            """, (fetch_session, target["mint"], target["pool_address"],
                  target["fire_id"], len(candles), now_utc))

            if (i + 1) % 50 == 0:
                out_conn.commit()
                log.info("Progress: %d/%d (%.1f%%)", i + 1, len(targets),
                         100 * (i + 1) / len(targets))

        except Exception as e:
            log.error("Failed: mint=%s fire=%s: %s", target["mint"][:12], target["fire_id"][:8], e)
            out_conn.execute("""
                INSERT INTO ohlcv_fetch_log (
                    fetch_session, mint, pool_address, fire_id,
                    status, error_message, fetched_at
                ) VALUES (?, ?, ?, ?, 'ERROR', ?, ?)
            """, (fetch_session, target["mint"], target["pool_address"],
                  target["fire_id"], str(e), now_utc))

    out_conn.commit()
    out_conn.close()

    log.info("═" * 60)
    log.info("OHLCV fetch complete: %d targets processed", len(targets))


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Batch OHLCV Loader for Large-Cap Universe")
    parser.add_argument("--universe-db", required=True, help="Path to largecap_universe DB")
    parser.add_argument("--output-db", default=None, help="Output OHLCV database path")
    parser.add_argument("--source", default="geckoterminal", choices=["geckoterminal", "birdeye"])
    parser.add_argument("--interval", default="15m", help="Candle interval (1m, 5m, 15m, 1h)")
    parser.add_argument("--horizon", default="4h", help="Forward window (5m, 15m, 30m, 1h, 4h, 1d)")
    parser.add_argument("--birdeye-key", default=None, help="Birdeye API key")
    parser.add_argument("--rate-limit", type=int, default=28, help="Requests per minute")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without fetching")
    args = parser.parse_args()

    config = FetchConfig(
        source=args.source,
        interval=args.interval,
        horizon=args.horizon,
        rate_limit_per_min=args.rate_limit,
        birdeye_api_key=args.birdeye_key or os.environ.get("BIRDEYE_API_KEY"),
    )

    targets = get_fetch_targets(args.universe_db)
    fetch_session = f"ohlcv_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    if args.dry_run:
        log.info("[DRY RUN] %d fetch targets from %s", len(targets), args.universe_db)
        run_fetch(targets, config, "", fetch_session, dry_run=True)
    else:
        if not args.output_db:
            args.output_db = f"artifacts/ohlcv_candles_{datetime.now(timezone.utc).strftime('%Y%m%d')}.db"
        Path(args.output_db).parent.mkdir(parents=True, exist_ok=True)
        run_fetch(targets, config, args.output_db, fetch_session, dry_run=False)


if __name__ == "__main__":
    main()
