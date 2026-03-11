# Off-Box Backup Setup Instructions

**Project:** solana-narrative-trader  
**VPS:** 142.93.24.227  
**rclone remote name:** `solana_backups_remote`  
**Credential file:** `/etc/solana_trader.env` (mode 600, root-owned)  
**Sync script:** `/root/solana_trader/ops/offbox_sync.sh`  
**Status as of 2026-03-11:** Credentials not yet provided — VPS is ready, rclone v1.73.2 installed.

---

## Priority 1 — Cloudflare R2 (Preferred)

Cloudflare R2 has **zero egress fees** and a free tier of 10 GB storage / 1 million Class A operations per month. It is the preferred target for this workload (compressed backups ~2 GB steady state).

### Step 1 — Create R2 bucket

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Navigate to **R2 Object Storage** → **Create bucket**
3. Bucket name: `solana-trader-backups` (or any name you choose)
4. Location: auto (or nearest region)
5. Note your **Account ID** from the R2 overview page (format: `abc123def456...`, 32 hex chars)

### Step 2 — Create R2 API token

1. In R2 → **Manage R2 API tokens** → **Create API token**
2. Permissions: **Object Read & Write** (scope to the bucket above)
3. Note the values:
   - **Access Key ID** (format: `abc123...`, ~32 chars)
   - **Secret Access Key** (format: `xyz789...`, ~64 chars)
   - **Endpoint URL**: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

### Step 3 — Write credentials to VPS

SSH into the VPS as root and run:

```bash
cat > /etc/solana_trader.env << 'EOF'
# Off-box backup credentials — root-owned, mode 600
# DO NOT commit to git

# Cloudflare R2
RCLONE_REMOTE=solana_backups_remote:solana-trader-backups/sqlite
CF_R2_ACCOUNT_ID=<YOUR_ACCOUNT_ID>
CF_R2_ACCESS_KEY_ID=<YOUR_ACCESS_KEY_ID>
CF_R2_SECRET_ACCESS_KEY=<YOUR_SECRET_ACCESS_KEY>
CF_R2_ENDPOINT=https://<YOUR_ACCOUNT_ID>.r2.cloudflarestorage.com
CF_R2_BUCKET=solana-trader-backups
EOF
chmod 600 /etc/solana_trader.env
chown root:root /etc/solana_trader.env
```

### Step 4 — Configure rclone remote

```bash
source /etc/solana_trader.env

rclone config create solana_backups_remote s3 \
  provider Cloudflare \
  access_key_id "$CF_R2_ACCESS_KEY_ID" \
  secret_access_key "$CF_R2_SECRET_ACCESS_KEY" \
  endpoint "$CF_R2_ENDPOINT" \
  acl private \
  no_check_bucket true

# Verify
rclone lsd solana_backups_remote:
```

### Step 5 — Verify and run first sync

```bash
/root/solana_trader/ops/offbox_sync.sh
```

Expected output: lists uploaded `.db.zst`, `.sha256`, `.meta.json` files and exits 0.

---

## Priority 2 — Backblaze B2 (Fallback)

Backblaze B2 charges $0.006/GB/month storage and $0.01/GB egress (first 1 GB/day free). Acceptable fallback if R2 is unavailable.

### Step 1 — Create B2 bucket

1. Log in to [secure.backblaze.com](https://secure.backblaze.com)
2. Navigate to **B2 Cloud Storage** → **Buckets** → **Create a Bucket**
3. Bucket name: `solana-trader-backups` (must be globally unique — append a suffix if taken)
4. Files in bucket: **Private**
5. Note the **Bucket ID** and **Endpoint** (format: `s3.us-west-004.backblazeb2.com`)

### Step 2 — Create application key

1. **Account** → **App Keys** → **Add a New Application Key**
2. Name: `solana-trader-vps`
3. Access: **Read and Write**, scoped to your bucket
4. Note:
   - **keyID** (format: `abc123...`)
   - **applicationKey** (shown only once — copy immediately)

### Step 3 — Write credentials to VPS

```bash
cat > /etc/solana_trader.env << 'EOF'
# Off-box backup credentials — root-owned, mode 600
# DO NOT commit to git

# Backblaze B2
RCLONE_REMOTE=solana_backups_remote:solana-trader-backups/sqlite
B2_KEY_ID=<YOUR_KEY_ID>
B2_APPLICATION_KEY=<YOUR_APPLICATION_KEY>
B2_BUCKET=solana-trader-backups
B2_ENDPOINT=<YOUR_ENDPOINT>   # e.g. s3.us-west-004.backblazeb2.com
EOF
chmod 600 /etc/solana_trader.env
chown root:root /etc/solana_trader.env
```

### Step 4 — Configure rclone remote

```bash
source /etc/solana_trader.env

rclone config create solana_backups_remote s3 \
  provider Backblaze \
  access_key_id "$B2_KEY_ID" \
  secret_access_key "$B2_APPLICATION_KEY" \
  endpoint "$B2_ENDPOINT" \
  acl private

# Verify
rclone lsd solana_backups_remote:
```

### Step 5 — Verify and run first sync

```bash
/root/solana_trader/ops/offbox_sync.sh
```

---

## Emergency Stopgap — GitHub Releases (NOT PRIMARY)

> **STOPGAP ONLY — NOT PRIMARY BACKUP**  
> Use only if R2 and B2 are both unavailable. GitHub Releases has a 2 GB per-file limit and is not designed for automated backup workflows. Off-box restore from GitHub requires manual steps.

If needed, compressed backups can be uploaded as release assets:

```bash
# Requires: gh CLI authenticated, repo exists
LATEST=$(ls /root/solana_trader/backups/sqlite/solana_trader/*.db.zst | sort | tail -1)
TAG="backup-$(date -u +%Y%m%dT%H%M%SZ)"
gh release create "$TAG" "$LATEST" "${LATEST}.sha256" "${LATEST}.meta.json" \
  --repo <YOUR_REPO> \
  --title "DB Backup $TAG" \
  --notes "Emergency stopgap backup — not primary" \
  --prerelease
```

This is **not** configured automatically and must never replace a proper object-store target.

---

## Summary Table

| Provider       | Cost (steady ~2GB) | Egress | Setup effort | Status       |
|----------------|--------------------|--------|--------------|--------------|
| Cloudflare R2  | Free (< 10GB)      | Free   | Low          | **Preferred** |
| Backblaze B2   | ~$0.01/mo          | $0.01/GB (1GB/day free) | Low | Fallback |
| GitHub Releases | Free              | Free   | Medium       | Stopgap only |

---

## Config Reference

| Item                  | Value                                              |
|-----------------------|----------------------------------------------------|
| rclone remote name    | `solana_backups_remote`                            |
| Credential file       | `/etc/solana_trader.env` (mode 600, root:root)     |
| rclone config file    | `/root/.config/rclone/rclone.conf` (auto-written)  |
| Sync script           | `/root/solana_trader/ops/offbox_sync.sh`           |
| Restore proof         | `/root/solana_trader/reports/ops/offbox_restore_proof.md` |
| RCLONE_REMOTE env var | `solana_backups_remote:<bucket>/sqlite`            |

**Security rules:**
- `/etc/solana_trader.env` must remain mode 600, owned by root
- rclone config is written by `rclone config create` and stored in `/root/.config/rclone/rclone.conf` — also root-only
- No credentials appear in scripts, systemd units, logs, or git
