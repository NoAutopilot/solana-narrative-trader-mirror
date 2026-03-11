# Off-Box Restore Proof

**Status: BLOCKED — credentials not yet provided**
**Date:** 2026-03-11T18:54 UTC
**Remote:** not configured

---

## Blocker

No off-box credentials have been provided. `/etc/solana_trader.env` exists (mode 600)
but `RCLONE_REMOTE` is not set.

Off-box restore proof cannot be executed until a remote is configured.

## What is ready

| Component | Status |
|-----------|--------|
| rclone v1.73.2 | Installed on VPS |
| `/etc/solana_trader.env` | Created (mode 600, root:root) — awaiting credentials |
| `/root/solana_trader/ops/offbox_sync.sh` | Deployed, tested (blocked exit, exit=0) |
| `/root/solana_trader/ops/offbox_restore_proof.sh` | Deployed, runs automatically once credentials set |
| `post_collection_ops.sh` | Updated to call offbox_sync.sh + offbox_restore_proof.sh at step 11 |

## To unblock

1. Follow `/root/solana_trader/reports/ops/offbox_setup_instructions.md`
2. Fill in `/etc/solana_trader.env` with R2 or B2 credentials
3. Run: `rclone config create solana_backups_remote ...` (exact command in setup instructions)
4. Run: `/root/solana_trader/ops/offbox_sync.sh`
5. Run: `/root/solana_trader/ops/offbox_restore_proof.sh`

This report will be overwritten with full proof once credentials are configured.

## Preferred option

**Cloudflare R2** — zero egress fees, free tier covers this workload (~2 GB steady state).
See setup instructions for exact steps.
