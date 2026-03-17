# 🔒 Security Guide

> This repository is **publicly visible on GitHub**. This document explains exactly what is safe to commit, what must never be committed, and how all credentials are handled.

---

## 🛡️ Security Model Overview

```
─────────────────────────────────────────────────────────────────────
  SECRET              STORAGE             ACCESSED VIA
─────────────────────────────────────────────────────────────────────
  Telegram Bot Token  .env (local)        os.getenv("TELEGRAM_BOT_TOKEN")
                      GitHub Secret       ${{ secrets.TELEGRAM_BOT_TOKEN }}

  Telegram Chat ID    .env (local)        os.getenv("TELEGRAM_CHAT_ID")
                      GitHub Secret       ${{ secrets.TELEGRAM_CHAT_ID }}

  Google Drive ID     .env (local)        os.getenv("GOOGLE_DRIVE_FOLDER_ID")
                      GitHub Secret       ${{ secrets.GOOGLE_DRIVE_FOLDER_ID }}

  Service Account     credentials/*.json  File path in .env (gitignored)
  JSON Key            GitHub Secret       Inline JSON string from secret
─────────────────────────────────────────────────────────────────────
```

**Key principle:** Zero hardcoded credentials anywhere in source code. All secrets enter via environment variables.

---

## ✅ What Is Safe in This Public Repo

| File / Folder | Safe? | Reason |
|---------------|-------|--------|
| `tracker/*.py` | ✅ Yes | Zero embedded secrets — all use `os.getenv()` |
| `.env.example` | ✅ Yes | Only placeholder values like `your_bot_token_here` |
| `.github/workflows/*.yml` | ✅ Yes | Uses `${{ secrets.* }}` — GitHub encrypts and injects at runtime |
| `data/snapshots/last_snapshot.json` | ✅ Yes | Public stock market data only |
| `requirements.txt`, `README.md`, etc. | ✅ Yes | No credentials |
| `image.png` | ✅ Yes | Screenshot/diagram only |

---

## ❌ What Must NEVER Be Committed

| File | Why Dangerous | Protection |
|------|--------------|------------|
| `.env` | Contains your real Telegram token and chat ID | `.gitignore` entry |
| `credentials/*.json` | Google service account private key | `.gitignore` entry — entire folder blocked |
| Any `*service-account*.json` | Private key for Google Cloud | `.gitignore` entry |
| Any `*token*.json` | OAuth refresh tokens | `.gitignore` entry |

### Verify Protection Is Active

```bash
# These commands should return NOTHING — if they return file names, you have a problem!
git ls-files credentials/
git ls-files .env
git ls-files | grep -i "token\|secret\|key\.json"
```

---

## 🔑 GitHub Secrets — Safe Setup

GitHub Secrets are **encrypted at rest** and only available inside Actions workflow context. They are:
- Never printed in logs (GitHub masks them automatically)
- Never accessible to forks running pull request workflows
- Only accessible in the same repo's workflows

### How to Add Secrets

1. Go to your repo on GitHub.com
2. Navigate: **Settings → Secrets and variables → Actions**
3. Click **New repository secret**
4. Add each secret:

| Secret | Value Pattern | Example |
|--------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | `numbers:letters` | `7412853291:AAF8_abc...` |
| `TELEGRAM_CHAT_ID` | Integer | `123456789` or `-987654321` (group) |
| `GOOGLE_DRIVE_FOLDER_ID` | Alphanumeric | `1a2b3c4d5e6f7g8h...` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON string | `{"type":"service_account",...}` |

> ⚠️ **For `GOOGLE_SERVICE_ACCOUNT_JSON`:** Open your downloaded JSON file, copy **all content** (one line), paste as the secret value.

---

## 🔍 Security Audit Checklist

Run this before every push:

```bash
# 1. No real credentials in tracked files
git ls-files | ForEach-Object { Select-String -Path $_ -Pattern "(?i)[0-9]{8,10}:[A-Za-z0-9_-]{35}" }
# Expected: no output

# 2. .env is NOT tracked
git ls-files .env
# Expected: no output

# 3. credentials/ is NOT tracked  
git ls-files credentials/
# Expected: no output

# 4. No private_key patterns
git ls-files | ForEach-Object { Select-String -Path $_ -Pattern "BEGIN (RSA )?PRIVATE KEY" }
# Expected: no output
```

---

## 🚨 If You Accidentally Committed a Secret

**Act immediately — the git history is public!**

### Step 1 — Revoke the token NOW
- **Telegram:** Message @BotFather → `/revoke` → select your bot → get new token
- **Google Service Account:** Go to Google Cloud Console → IAM → Service Accounts → delete the key → create a new one

### Step 2 — Remove from git history
```bash
# Install git-filter-repo (recommended over BFG)
pip install git-filter-repo

# Remove the specific file
git filter-repo --path credentials/service-account.json --invert-paths

# Force push (this rewrites history — others need to re-clone)
git push origin main --force
```

### Step 3 — Update secrets everywhere
- Update your `.env` with new values
- Update GitHub Secrets with new values

> ⚠️ **Assumption that deleting is enough is wrong.** GitHub caches content and web scrapers archive repos continuously. Always revoke the old credential first.

---

## 📋 .gitignore Verification

Current protection in `.gitignore`:

```
# Secrets & credentials
.env
credentials/
```

This blocks:
- `.env` — your local secrets file
- `credentials/` — the entire folder with service account JSONs

**If you store credentials elsewhere**, add that path to `.gitignore` too.

---

## 🔐 Principle of Least Privilege

| Component | What It Can Access | What It Cannot |
|-----------|-------------------|----------------|
| Telegram Bot | Send/receive messages in 1 chat | Access other chats, read other bots |
| Google Service Account | Upload/read files in 1 specific Drive folder | Access rest of Google Drive, Gmail, etc. |
| GitHub Actions | Read repo, write to `data/` folder | Access your secrets directly |
| NSE Scraper | Read public NSE website | No authentication, no account needed |

---

*Last security audit: March 2026 — All clear ✅*