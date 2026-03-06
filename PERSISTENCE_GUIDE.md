# Persistence Guide — How to Survive Session Resets

> **Purpose:** Step-by-step instructions so that everything we've built continues working even when this Manus session ends, resets, or you start a new chat.

---

## What Survives a Session Reset

| Component | Survives? | Why |
|-----------|-----------|-----|
| **VPS paper trader** | ✅ YES | Runs on your DigitalOcean droplet, independent of Manus |
| **Trade data (VPS)** | ✅ YES | SQLite DB on VPS disk, hourly GitHub backups |
| **GitHub repo** | ✅ YES | All code + DB backups persist on GitHub |
| **Manus dashboard** | ⚠️ PARTIAL | The webdev project persists across sessions, but may need restart |
| **Sandbox files** | ❌ NO | `/home/ubuntu/` is wiped on sandbox reset |
| **Running processes** | ❌ NO | Any `nohup` processes in sandbox die on reset |
| **Installed packages** | ❌ NO | `pip install` in sandbox must be re-run |

---

## What You Need to Do (Nothing, Usually)

**If the VPS is running, you don't need to do anything.** The paper trader runs 24/7 as a systemd service with auto-restart, and the hourly cron pushes DB backups to GitHub.

The only time you need to act is if:
1. The VPS goes down (DigitalOcean outage or you destroy the droplet)
2. You want to view the dashboard in a new Manus session
3. You want to make code changes

---

## Step-by-Step: Starting a New Manus Session

### Step 1: Tell Manus What This Is

Paste this at the start of any new chat:

```
I have a Solana memecoin paper trading system. The code is at:
- GitHub: NoAutopilot/solana-narrative-trader
- VPS: 142.93.24.227 (root / 1987Foxsex)
- Dashboard: Manus webdev project "solana-trading-dashboard"

Read /home/ubuntu/solana_trader/RECOVERY.md first, then check VPS health.
If the repo isn't cloned yet, clone it: gh repo clone NoAutopilot/solana-narrative-trader /home/ubuntu/solana_trader
```

### Step 2: Manus Will Auto-Recover

A well-briefed Manus session will:
1. Clone the repo from GitHub
2. Read RECOVERY.md, OPERATING_PRINCIPLES.md, RESEARCH_TRACKER.md
3. Check VPS health via SSH
4. Copy latest DB from VPS to sandbox
5. Restart the dashboard if needed
6. Brief you on current state

### Step 3: Verify Everything

Ask Manus to run the validation script:
```
Run python3 validate_math_and_setup.py
```

This checks: DB integrity, fee model, VPS health, wallet, backups, and dashboard consistency.

---

## Step-by-Step: If VPS Goes Down

### Option A: Restart the VPS Service
```bash
# SSH into VPS
ssh root@142.93.24.227
# Password: 1987Foxsex

# Check and restart
systemctl status solana-trader
systemctl restart solana-trader
journalctl -u solana-trader -n 50
```

### Option B: Full VPS Rebuild
If the droplet is destroyed, create a new one and run:
```bash
# From Manus sandbox:
sshpass -p 'YOUR_NEW_PASSWORD' scp -o StrictHostKeyChecking=no /home/ubuntu/vps_deploy.sh root@NEW_IP:/root/
sshpass -p 'YOUR_NEW_PASSWORD' ssh -o StrictHostKeyChecking=no root@NEW_IP 'bash /root/vps_deploy.sh'
```

The deploy script installs everything, clones the repo, restores the DB from GitHub, and starts the service.

### Option C: Run Locally in Manus (Temporary)
If VPS is down and you need trades running NOW:
```bash
cd /home/ubuntu/solana_trader
python3 backup_to_github.py --restore  # Get latest DB
nohup python3 paper_trader.py > logs/paper_trader.log 2>&1 &
```

**Warning:** This only runs while the Manus session is active. Data will be lost if you don't backup before the session ends.

---

## Step-by-Step: Viewing the Dashboard

The Manus dashboard project (`solana-trading-dashboard`) should persist across sessions. If it doesn't load:

1. Ask Manus to check: `webdev_check_status`
2. If server is down: `webdev_restart_server`
3. If project is gone: Manus can restore from the last checkpoint
4. The dashboard needs the SQLite DB at `/home/ubuntu/solana_trader/data/solana_trader.db` — copy from VPS if missing

---

## Step-by-Step: Making Code Changes

1. **Edit on sandbox**, test locally
2. **Push to GitHub**: `cd /home/ubuntu/solana_trader && git add -A && git commit -m "description" && git push`
3. **Update VPS**: SSH in and `cd /root/solana_trader && git pull && systemctl restart solana-trader`
4. **Backup DB first** if the VPS has been collecting data: the hourly cron handles this, but you can force it with `python3 backup_to_github.py`

---

## Data Safety Layers

Your data is protected by **four independent backup layers**:

```
Layer 1: VPS live DB          → /root/solana_trader/data/solana_trader.db
         (most current, updates every second)

Layer 2: GitHub hourly backup → backups/solana_trader_backup.db
         (cron: every hour on the hour)

Layer 3: S3 backup            → solana-trader-backups/solana_trader_latest.db
         (triggered by supervisor.py on VPS)

Layer 4: Dashboard restore    → tRPC endpoint system.restoreDb
         (pulls from S3, accessible via dashboard UI)
```

**To lose all data, ALL FOUR would need to fail simultaneously.** This is extremely unlikely.

---

## Credentials Reference

| Service | Credential | Value |
|---------|-----------|-------|
| VPS SSH | root@142.93.24.227 | Password: `1987Foxsex` |
| Helius RPC | API Key | `REDACTED_HELIUS_API_KEY` |
| Wallet | Address | `REDACTED_WALLET_ADDRESS` |
| PumpPortal | API Key | `a38bc654-2b7e-4e99-b12c-f5dca52ce468` |
| GitHub | Repo | `NoAutopilot/solana-narrative-trader` |

**Security note:** The VPS password is in this document and in chat history. You should change it:
```bash
ssh root@142.93.24.227
passwd
# Enter new password twice
```
Then update RECOVERY.md and this guide with the new password.

---

## Quick Health Check (Copy-Paste This)

Run this in any Manus session to get a full status:

```bash
# 1. VPS status
sshpass -p '1987Foxsex' ssh -o StrictHostKeyChecking=no root@142.93.24.227 'systemctl is-active solana-trader && python3 -c "import sqlite3; c=sqlite3.connect(\"/root/solana_trader/data/solana_trader.db\"); t=c.execute(\"SELECT COUNT(*) FROM trades\").fetchone()[0]; p=c.execute(\"SELECT COALESCE(SUM(pnl_sol),0) FROM trades WHERE status=\\\"closed\\\"\").fetchone()[0]; print(f\"VPS: {t} trades, PnL: {p:.4f} SOL\"); c.close()" && uptime'

# 2. Wallet balance
python3 -c "import requests; r=requests.post('https://mainnet.helius-rpc.com/?api-key=REDACTED', json={'jsonrpc':'2.0','id':1,'method':'getBalance','params':['REDACTED_WALLET_ADDRESS']}); print(f\"Wallet: {r.json()['result']['value']/1e9:.6f} SOL\")"

# 3. Last GitHub backup
gh api repos/NoAutopilot/solana-narrative-trader/commits?per_page=1 --jq '.[0].commit.message'
```

---

## The Bottom Line

**Your system is now resilient.** The VPS runs independently of Manus. Data backs up hourly to GitHub. The code is version-controlled. Even if Manus, the VPS, or GitHub individually fail, the other two can rebuild everything.

The only thing that can't be automatically recovered is **this conversation's context** — the reasoning, decisions, and experimental findings. That's why RECOVERY.md, OPERATING_PRINCIPLES.md, and RESEARCH_TRACKER.md exist: they capture the institutional knowledge so any new session can pick up where we left off.
