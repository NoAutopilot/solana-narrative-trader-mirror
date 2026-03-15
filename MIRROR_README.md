# solana-narrative-trader — Public Audit Mirror

This is a **read-only, sanitized mirror** of the private canonical repository
`NoAutopilot/solana-narrative-trader`.

## Purpose
- Audit surface for reproducibility and code review
- All secrets, wallet keys, API keys, and environment files have been removed
- Database files and logs are excluded
- This mirror is **not** used for deployment; the VPS deploys from the private repo

## What is stripped
- `trader_env.conf` (API keys, wallet private key)
- All `.env` files
- All `.db` / `.db-journal` files
- `backups/`, `data/`, `logs/` directories
- `deployment_proof.json`, `.deployed_sha`
- Any `failure_memo_*.md` files

## Sync
This mirror is automatically updated on every push to `master` in the private repo.
