# Recovery Protocol — Solana Narrative Trader

> **Purpose:** This document enables a brand-new Manus chat session — with zero prior context — to rebuild the entire trading system to its current state. Read this file FIRST if you are starting fresh.
>
> **Last updated:** 2026-02-23

---

## STEP 0: ORIENTATION (Read Before Doing Anything)

This is a Solana memecoin paper/live trading system that runs on pump.fun. It monitors RSS news feeds for narrative signals, buys tokens that match narratives, and exits via take-profit, stop-loss, or timeout. The system also runs a web dashboard (Manus webdev project) for monitoring.

**The two codebases:**

| Component | Location | GitHub Repo |
|-----------|----------|-------------|
| Trading system (paper_trader, live_executor, config) | `/home/ubuntu/solana_trader/` | `NoAutopilot/solana-narrative-trader` |
| Web dashboard (React + tRPC + SQLite reader) | `/home/ubuntu/solana-trading-dashboard/` | Manus webdev project `solana-trading-dashboard` |

**Critical files to read first:**

1. `OPERATING_PRINCIPLES.md` — The 8 principles that govern every decision
2. `RESEARCH_TRACKER.md` — Full experimental history across all sessions
3. `config/config.py` — Current trading parameters
4. This file (`RECOVERY.md`) — You are here

---

## STEP 1: CLONE THE TRADING SYSTEM

```bash
cd /home/ubuntu
gh repo clone NoAutopilot/solana-narrative-trader solana_trader
cd solana_trader
sudo pip3 install -r requirements.txt
sudo pip3 install python-dotenv websockets solders solana base58
```

---

## STEP 2: CREATE THE .env FILE

The `.env` file is NOT in GitHub (for security). Create it manually:

```bash
cat > /home/ubuntu/solana_trader/.env << 'EOF'
HELIUS_RPC_URL=REDACTED
WALLET_ADDRESS=REDACTED
SOLANA_PRIVATE_KEY=REDACTED
PUMPPORTAL_API_KEY=REDACTED
LIVE_ENABLED=false
LIVE_TRADE_SIZE_SOL=0.005
LIVE_SLIPPAGE_PCT=20
LIVE_PRIORITY_FEE=0.0001
EOF
```

**IMPORTANT:** `LIVE_ENABLED=false` means paper trading only. Do NOT change to `true` without explicit user instruction and sufficient wallet balance (~1 SOL minimum).

---

## STEP 3: RESTORE DATABASE FROM GITHUB BACKUP

The SQLite database is backed up to `backups/solana_trader_backup.db` in the GitHub repo.

```bash
cd /home/ubuntu/solana_trader
python3 backup_to_github.py --restore
```

If no backup exists (first time or backup was never run), initialize an empty database:

```bash
python3 -c "import database; database.init_db()"
```

---

## STEP 4: START THE PAPER TRADER

```bash
cd /home/ubuntu/solana_trader
mkdir -p logs
nohup python3 paper_trader.py > logs/paper_trader.log 2>&1 &
```

Verify it started:

```bash
sleep 10 && tail -20 logs/paper_trader.log
```

You should see: narrative scanning, token evaluations, entries, and exits. Confirm `Timeout: 5min` appears in the startup log.

---

## STEP 5: RESTORE THE WEB DASHBOARD

The dashboard is a Manus webdev project. If the project exists but the server is down:

```bash
# The webdev project should auto-restore from its last checkpoint
# Use webdev_check_status to verify
# Use webdev_restart_server if needed
```

If the project is completely gone, it needs to be re-initialized. The dashboard reads from the SQLite database at `/home/ubuntu/solana_trader/data/solana_trader.db` via a custom `sqliteReader.ts` module.

---

## STEP 6: VERIFY SYSTEM HEALTH

Run the health audit:

```bash
cd /home/ubuntu/solana_trader
python3 system_health_audit.py
```

This checks: RPC connectivity, wallet balance, wallet cleanliness, config values, data quality, outlier concentration, live executor readiness, and backup system presence.

**Expected results for paper-only mode:** All PASS except wallet balance (needs ~1 SOL for live trading).

---

## STEP 7: BACKUP DATA BEFORE SESSION ENDS

**This is critical.** Before ending any session, always back up the database:

```bash
cd /home/ubuntu/solana_trader
python3 backup_to_github.py
```

This copies the SQLite DB to `backups/` and pushes to GitHub. Without this, all trade data collected during the session is lost on sandbox reset.

---

## CURRENT SYSTEM STATE

### Trading Parameters (config/config.py)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| TIMEOUT_MINUTES | 5 | All moonshots close within 4.72 min; 15-min timeout wastes capital |
| TAKE_PROFIT_PCT | 0.30 (30%) | Moonshots blow past this between 10s price checks |
| STOP_LOSS_PCT | -0.25 (-25%) | Standard risk management |
| MAX_CONCURRENT_TRADES | 50 | With 5-min timeout, actual concurrent stays ~15-25 |
| TRADE_SIZE_SOL | 0.04 | Paper trade size |

### What Has Been Proven

1. **System can detect and trade tokens in real-time** — [PROVEN IN PAPER]
2. **Exit strategy matters more than entry signal** — [PROVEN IN PAPER]
3. **Moonshots are the profit engine** — power law distribution, top 3 trades = 100% of PnL
4. **Winners exit fast (<5 min), losers bleed slowly** — [PROVEN IN PAPER, n=2108]
5. **Post-migration selling works** — [PROVEN ON-CHAIN, 5/5 sells via pool=auto]
6. **Twitter engagement does NOT predict PnL** — [PROVEN, p>0.05]
7. **First-mover advantage does NOT exist** — [PROVEN]
8. **5-min timeout captures 100% of moonshots** — [PROVEN IN PAPER, n=4 moonshots]
9. **5-min timeout reduces concurrent positions from ~46 to ~16** — [PROVEN IN PAPER]

### What Is NOT Proven

1. **Narrative matching adds value over random** — p=0.09, not significant
2. **Cost model accuracy for real trading** — paper vs live gap is massive
3. **Multi-day robustness** — need 48+ hours continuous data
4. **Profitability after fees** — 8-15% round-trip fees destroy most winners
5. **Scalability of trade size** — slippage is nonlinear on pump.fun bonding curve

### Key Risk: Outlier Dependence

The system's profitability depends entirely on rare moonshot events. Remove the top 3 trades and the system is net negative. This is a **lottery ticket strategy**, not a consistent edge. The operating principles require acknowledging this honestly.

---

## WALLET STATUS

| Detail | Value |
|--------|-------|
| Address | REDACTED_WALLET_ADDRESS |
| Expected balance | ~0.005 SOL (after all cleanup) |
| Token accounts | 0 (fully cleaned) |
| Live trading history | -0.205 SOL net (177 trades, 14.1% win rate) |
| Paper trading history | +67+ SOL (dominated by 3-4 moonshots) |

---

## AVAILABLE SCRIPTS

| Script | Purpose | Usage |
|--------|---------|-------|
| `paper_trader.py` | Main trading engine | `python3 paper_trader.py` |
| `live_executor.py` | On-chain buy/sell via PumpPortal | Called by paper_trader when LIVE_ENABLED=true |
| `backup_to_github.py` | Backup DB to GitHub | `python3 backup_to_github.py` |
| `backup_to_github.py --restore` | Restore DB from GitHub | `python3 backup_to_github.py --restore` |
| `system_health_audit.py` | Full system health check | `python3 system_health_audit.py` |
| `burn_and_close.py` | Burn dead tokens + reclaim rent | `python3 burn_and_close.py` |
| `rent_reclaim.py` | Close empty token accounts | `python3 rent_reclaim.py` |
| `force_close_api.py` | HTTP API for force-closing positions | `python3 force_close_api.py` |
| `supervisor.py` | Process supervisor for paper_trader | `python3 supervisor.py` |

---

## USER CONTEXT

The user is building this as a research project to explore whether narrative-driven memecoin trading can be profitable. They value:

1. **Honesty over optimism** — never present paper PnL as real profitability
2. **Scientific rigor** — every claim must have data, every finding must survive adversarial testing
3. **Practical progress** — features should answer questions, not just look impressive
4. **Data persistence** — they have lost data twice to sandbox resets; always backup before session end
5. **Simplicity** — they don't have a separate server yet (planning Hetzner VPS at $4.35/mo for 24/7 operation)

---

## NEXT STEPS (as of last session)

1. **User is setting up a Hetzner VPS** for 24/7 paper trading — `vps_setup.sh` is in the repo
2. **Need 48+ hours of continuous data** with the 5-min timeout to validate the pattern
3. **Do NOT enable live trading** until wallet has ~1 SOL and the 5-min timeout pattern is validated over multiple days
4. **Run `system_health_audit.py`** at the start of every session to verify system state

---

## RECOVERY CHECKLIST

Use this checklist when starting from a completely fresh chat:

- [ ] Read this file (RECOVERY.md)
- [ ] Read OPERATING_PRINCIPLES.md
- [ ] Read RESEARCH_TRACKER.md
- [ ] Clone repo: `gh repo clone NoAutopilot/solana-narrative-trader solana_trader`
- [ ] Install deps: `sudo pip3 install -r requirements.txt && sudo pip3 install python-dotenv websockets solders solana base58`
- [ ] Create .env file (see Step 2)
- [ ] Restore DB: `python3 backup_to_github.py --restore`
- [ ] Start paper trader: `nohup python3 paper_trader.py > logs/paper_trader.log 2>&1 &`
- [ ] Run health audit: `python3 system_health_audit.py`
- [ ] Check/restart dashboard: `webdev_check_status` / `webdev_restart_server`
- [ ] Tell user: "System restored. Here's the current state: [summary from health audit]"
