#!/bin/bash
# Automated GitHub backup for solana_trader
# Pushes all changes to the private repo

cd /home/ubuntu/solana_trader || exit 1

# Add all changes
git add -A

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) No changes to backup"
    exit 0
fi

# Commit with timestamp
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
git commit -m "auto-backup: ${TIMESTAMP}"

# Push to GitHub
git push origin master

echo "${TIMESTAMP} Backup complete"
