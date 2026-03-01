# GitHub Setup Guide

## Step 1: Initialize Git Repository

```powershell
# Navigate to project directory
cd "c:\Users\1000040225\OneDrive - Air Canada\Automation scripts\Learning\shetkari-sahayata\indian-market-tracker"

# Initialize git (if not already done)
git init

# Check current status
git status
```

## Step 2: Create .gitignore (Already exists)

Your `.gitignore` should exclude:
- `.env` (contains secrets - never commit!)
- `data/` (large datasets)
- `__pycache__/`
- `*.pyc`

Verify:
```powershell
cat .gitignore
```

## Step 3: Create GitHub Repository

### Option A: Using GitHub Website (Recommended)
1. Go to https://github.com/new
2. Repository name: `indian-market-tracker`
3. Description: `Comprehensive NSE market intelligence with Telegram alerts, FII/DII tracking, signal detection, and enterprise reliability`
4. Choose **Private** (your Telegram token will be in commit history)
5. **Do NOT** initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"

### Option B: Using GitHub CLI
```powershell
# Install GitHub CLI if not installed
winget install --id GitHub.cli

# Login
gh auth login

# Create private repository
gh repo create indian-market-tracker --private --source=. --remote=origin --description="Comprehensive NSE market intelligence with Telegram alerts"
```

## Step 4: Commit and Push

```powershell
# Add all files
git add .

# Check what will be committed
git status

# Verify .env is NOT staged (should be in .gitignore)
# If you see .env listed, do: git reset .env

# Create first commit
git commit -m "Initial commit: Indian Market Tracker v3.0 with enterprise features

Features:
- FII/DII tracking with institutional flow analysis
- 21 indices and 16 sectors monitoring
- Smart signal detection (10 buy/sell indicators)
- Interactive Telegram bot with inline keyboards
- Enterprise reliability (rate limiter, circuit breaker, exponential backoff)
- Windowed scheduler for GitHub Actions
- Delta engine for change tracking
- Excel logging with 7 colored sheets
- Corporate actions and insider trading
- Options PCR and commodities tracking"

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/indian-market-tracker.git

# Push to GitHub
git push -u origin main

# If it fails with "main" branch, try "master"
git branch -M main
git push -u origin main
```

## Step 5: Configure GitHub Secrets

After pushing, configure secrets for GitHub Actions:

1. Go to your repository on GitHub: `https://github.com/YOUR_USERNAME/indian-market-tracker`
2. Click **Settings** tab
3. In left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**

Add these two secrets:

### Secret 1: TELEGRAM_BOT_TOKEN
- Name: `TELEGRAM_BOT_TOKEN`
- Value: `8647581713:AAGHE_S3n9rFs4gYaZXXlP1aqkalZ4b125c`
- Click "Add secret"

### Secret 2: TELEGRAM_CHAT_ID
- Name: `TELEGRAM_CHAT_ID`
- Value: `-5254240205`
- Click "Add secret"

## Step 6: Enable GitHub Actions

1. Go to **Actions** tab in your repository
2. Click "I understand my workflows, go ahead and enable them"
3. You should see two workflows:
   - `Market Tracker - Morning Session`
   - `Market Tracker - Afternoon & Evening Session`

## Step 7: Test Workflows Manually

Before waiting for scheduled runs, test manually:

1. Go to **Actions** tab
2. Click on "Market Tracker - Morning Session"
3. Click "Run workflow" dropdown (right side)
4. Select branch: `main`
5. Click "Run workflow" button
6. Watch the logs in real-time
7. Check your Telegram for messages
8. Repeat for "Afternoon & Evening Session"

## Step 8: Monitor Scheduled Runs

Workflows will now run automatically:
- **Morning**: Mon-Fri at 08:45 IST (03:15 UTC)
- **Afternoon**: Mon-Fri at 15:30 IST (10:00 UTC)

Check:
- GitHub Actions tab for execution logs
- Telegram for messages
- Repository commits for data updates

## Troubleshooting

### Issue: .env file was committed
```powershell
# Remove from git tracking
git rm --cached .env

# Ensure .gitignore contains .env
echo ".env" >> .gitignore

# Commit the fix
git add .gitignore
git commit -m "Remove .env from tracking"
git push
```

### Issue: Authentication failed
```powershell
# Set up GitHub Personal Access Token
# Go to: https://github.com/settings/tokens
# Generate new token (classic) with 'repo' scope
# Use token as password when pushing
```

### Issue: Workflows not running
- Check if Actions are enabled (Settings → Actions → Allow all actions)
- Verify secrets are set correctly (no extra spaces)
- Check workflow file syntax (Actions tab shows errors)

## Best Practices

1. **Never commit .env** - Always keep secrets in GitHub Secrets
2. **Use private repository** - Your token is sensitive
3. **Review commits** - Check what files are being committed
4. **Monitor Actions** - First few runs may need adjustments
5. **Check Telegram** - Verify messages are arriving correctly

## Next Steps After Push

1. Wait for next scheduled run (Monday 08:45 IST)
2. Monitor GitHub Actions logs
3. Verify data commits are happening
4. Check Telegram for all 8 daily updates
5. Review Excel files in data/excel/ (committed to repo)

---

**Need Help?**
- GitHub Actions docs: https://docs.github.com/en/actions
- Telegram Bot API: https://core.telegram.org/bots/api
- NSE India: https://www.nseindia.com
