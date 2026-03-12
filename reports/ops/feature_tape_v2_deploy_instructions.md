# feature_tape_v2 — VPS Deployment Instructions

**Version:** post-audit rewrite (2026-03-12)
**Status:** Ready to deploy after GitHub push

---

## Prerequisites

Before running these commands, confirm:
- `feature_tape_v2` service (if running) is stopped
- The 3-fire sample (129 rows) has been discarded from `feature_tape_v2` table
- GitHub push from this session has completed (check commit SHA)

---

## Step 1 — Pull latest code on VPS

```bash
cd /root/solana_trader
git fetch origin
git pull origin master
```

Verify the new file is present:
```bash
ls -la /root/solana_trader/feature_tape_v2.py
python3 -m py_compile /root/solana_trader/feature_tape_v2.py && echo "SYNTAX OK"
```

---

## Step 2 — Discard the 3-fire sample

```bash
sqlite3 /root/solana_trader/data/solana_trader.db << 'SQL'
-- Verify what we're about to drop
SELECT COUNT(*), COUNT(DISTINCT fire_id) FROM feature_tape_v2;
-- Drop the old table (schema will be recreated by the new script)
DROP TABLE IF EXISTS feature_tape_v2;
DROP TABLE IF EXISTS feature_tape_v2_fire_log;
.quit
SQL
```

---

## Step 3 — Create the systemd service file

Create `/etc/systemd/system/solana-feature-tape-v2.service`:

```ini
[Unit]
Description=Solana Feature Tape v2 — read-only data collection service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/solana_trader
ExecStart=/usr/bin/python3 /root/solana_trader/feature_tape_v2.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

---

## Step 4 — Enable and start the service

```bash
systemctl daemon-reload
systemctl enable solana-feature-tape-v2.service
systemctl start solana-feature-tape-v2.service
systemctl status solana-feature-tape-v2.service
```

---

## Step 5 — First-fire proof (run after first fire completes)

The first fire will trigger at the next 15-minute boundary (:00, :15, :30, :45 UTC).

```bash
sqlite3 /root/solana_trader/data/solana_trader.db << 'SQL'
-- Row count and fire count
SELECT COUNT(*) as rows, COUNT(DISTINCT fire_id) as fires FROM feature_tape_v2;

-- Coverage check: no NULL lanes
SELECT COUNT(*) as null_lanes FROM feature_tape_v2 WHERE lane IS NULL;

-- Coverage by family
SELECT
  COUNT(*) as total_rows,
  SUM(CASE WHEN buys_m5 IS NOT NULL THEN 1 ELSE 0 END) as micro_rows,
  SUM(CASE WHEN jup_vs_cpamm_diff_pct IS NOT NULL THEN 1 ELSE 0 END) as quote_rows,
  SUM(CASE WHEN breadth_positive_pct IS NOT NULL THEN 1 ELSE 0 END) as breadth_rows,
  SUM(CASE WHEN pool_size_total IS NOT NULL THEN 1 ELSE 0 END) as pool_size_rows
FROM feature_tape_v2;

-- Lane distribution
SELECT lane, COUNT(*) as n FROM feature_tape_v2 GROUP BY lane ORDER BY n DESC;

-- Source flags
SELECT order_flow_source, COUNT(*) as n FROM feature_tape_v2 GROUP BY order_flow_source;

-- Fire log
SELECT * FROM feature_tape_v2_fire_log;
.quit
SQL
```

**Expected first-fire proof:**
- `null_lanes = 0` (every row has a derived lane)
- `micro_rows` > 0 (at least some mints have micro coverage)
- `quote_rows` ≈ total_rows (snapshot-native, ~100%)
- `breadth_rows` = total_rows (fire-level, identical across all rows)
- `pool_size_rows` = total_rows (never NULL)
- `order_flow_source` shows both `microstructure_log` and `missing` (non-random by venue)

---

## Step 6 — 10-fire health checkpoint

Run at fire 10 (~2h after restart):

```bash
sqlite3 /root/solana_trader/data/solana_trader.db << 'SQL'
SELECT
  COUNT(DISTINCT fire_id) as fires,
  COUNT(*) as rows,
  MIN(fire_time_utc) as first_fire,
  MAX(fire_time_utc) as last_fire,
  AVG(CASE WHEN buys_m5 IS NOT NULL THEN 1.0 ELSE 0.0 END) as micro_coverage_rate,
  AVG(CASE WHEN jup_vs_cpamm_diff_pct IS NOT NULL THEN 1.0 ELSE 0.0 END) as quote_coverage_rate
FROM feature_tape_v2;
.quit
SQL
```

---

## Target: 96 fires (~24h)

Collection runs continuously. At 96 fires, run the retrospective sweep on
+5m, +15m, +30m, +1h, +4h horizons. The +1d horizon requires ~48h maturation.

No live observers will be launched until all 6 promotion gates are passed.

---

*Generated 2026-03-12. See feature_tape_v2_source_map.md and feature_tape_v2_unavailable_fields.md for schema details.*
