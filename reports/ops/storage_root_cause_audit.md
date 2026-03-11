# Storage Root-Cause Audit
**reports/ops/storage_root_cause_audit.md**
as of 2026-03-11T16:45Z

> **Local durability only — off-box backup not configured.**

---

## 1. DISK USAGE SUMMARY

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1        24G   22G  2.0G  92%  /
```

**92% used — 2.0G free. Critical headroom.**

---

## 2. TOP-LEVEL BREAKDOWN

| Path | Size | % of Disk |
|---|---|---|
| /root/solana_trader/backups | **18 GB** | **75%** |
| /root/solana_trader/data | 277 MB | 1.1% |
| /root/solana_trader/logs | 240 MB | 1.0% |
| /root/solana_trader/.git | 17 MB | 0.07% |
| /var/log (journal) | 64 MB | 0.26% |
| All other | ~1.5 GB | 6.2% |

**The backup directory is the dominant consumer at 75% of total disk.**

---

## 3. BACKUP BREAKDOWN

| DB | Backup Files | Total Size | Notes |
|---|---|---|---|
| solana_trader | 82 .db files | **15 GB** | PRIMARY DRIVER — 241MB each, growing ~1.6MB/fire |
| post_bonding | 82 .db files | 2.3 GB | Static DB (no active writes) |
| observer_lcr_cont_v1 | 82 .db files | 57 MB | Archived — static |
| observer_pfm_cont_v1 | 81 .db files | 32 MB | Archived — static |
| observer_pfm_rev_v1 | 81 .db files | 16 MB | Archived — static |

**solana_trader.db alone accounts for 15 GB of backups.**

Current backup policy: every 15 minutes, retain 72h = 288 copies × 241 MB = **69 GB needed** (already hitting disk before 72h window fills).

Actual behavior: 82 copies on disk = ~34 hours of 15-min backups before disk fills.

**Estimated growth rate (before fix):**
- solana_trader.db grows ~1.6 MB per 15-min fire = ~6.4 MB/hour = **~154 MB/day of new data**
- Each backup copy = ~241 MB (full copy, not incremental)
- 96 copies/day × 241 MB = **~23 GB/day of backup writes**
- post_bonding.db is static but still copied every 15 min: 82 × 28 MB = 2.3 GB wasted

---

## 4. WHAT % OF DISK IS EACH CATEGORY?

| Category | Size | % of 24 GB |
|---|---|---|
| Backups (all) | 18 GB | **75%** |
| — solana_trader backups | 15 GB | **62%** |
| — post_bonding backups | 2.3 GB | 10% |
| — observer backups | 105 MB | 0.4% |
| Live DB data | 277 MB | 1.1% |
| Logs (app) | 240 MB | 1.0% |
| Git history | 17 MB | 0.07% |
| Journal | 64 MB | 0.26% |
| OS + other | ~3.4 GB | 14% |

**Data rows themselves are NOT a meaningful driver.** The live solana_trader.db is 243 MB. The problem is entirely the backup policy producing full uncompressed copies every 15 minutes.

---

## 5. GIT HYGIENE

Git is tracking backup artifacts:
```
backups/backup_info.txt
backups/solana_trader_backup.db-shm
backups/solana_trader_backup.db-wal
backups/sqlite/observer_lcr_cont_v1/*.meta.json (many)
backups/sqlite/observer_lcr_cont_v1/*.sha256 (many)
```

The `.db` files themselves are in `.gitignore` and are NOT tracked. However, `.meta.json` and `.sha256` sidecar files ARE tracked. These are small individually but accumulate.

Git history size: 17 MB (pack: 1.24 MiB) — not a significant driver.

---

## 6. ROOT CAUSE SUMMARY

| Root Cause | Severity | Notes |
|---|---|---|
| Uncompressed 15-min full backups of solana_trader.db | **CRITICAL** | 15 GB, growing ~23 GB/day |
| post_bonding.db backed up every 15 min (static DB) | HIGH | 2.3 GB wasted |
| 72h retention window too long for full uncompressed copies | HIGH | 288 copies × 241 MB = 69 GB needed |
| .meta.json and .sha256 files tracked in git | LOW | Small but accumulating |
| App logs (240 MB) | LOW | Not critical, manageable |
| Journal (64 MB, capped) | OK | Fixed in previous session |

---

## 7. FIXES APPLIED / PLANNED

See companion reports:
- `reports/ops/git_storage_hygiene.md` — git tracking fix
- `reports/ops/storage_health_latest.md` — current state + alerts

Retention and compression changes: applied in `ops/backup_sqlite.sh` (see Task 2/3 changes).

**Estimated growth rate AFTER fix:**
- Compressed backups: ~241 MB × 0.15 compression ratio ≈ **36 MB per copy**
- 15-min copies for 12h = 48 copies × 36 MB = 1.7 GB
- Hourly copies for 72h = 72 copies × 36 MB = 2.6 GB
- Daily copies for 7d = 7 copies × 36 MB = 252 MB
- post_bonding.db: 1 archive copy only = ~28 MB compressed
- Total solana_trader backups: ~4.6 GB (vs 15 GB before)
- **Savings: ~10 GB immediately, ~18 GB/day write reduction**
