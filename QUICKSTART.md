# 🚀 Quickstart Guide

> Get your first Telegram market update in **15 minutes**. No coding experience required.

---

## 📋 What You Need Before Starting

| Requirement | Details |
|-------------|---------|
| 🐍 **Python 3.11+** | [Download here](https://python.org/downloads) |
| 📱 **Telegram account** | [telegram.org](https://telegram.org) |
| 💻 **Git** | [git-scm.com](https://git-scm.com) |
| 🌐 **GitHub account** | [github.com](https://github.com) (free) |

---

## 🗺️ Setup Roadmap

```
Step 1          Step 2          Step 3          Step 4          Step 5
   │               │               │               │               │
Download        Create          Configure       Run &           Automate
the code   →   Telegram    →   your .env   →   Test       →   with GitHub
               Bot                                              Actions
(5 min)       (3 min)         (2 min)         (2 min)         (5 min)
```

---

## Step 1 — Download the Code

```bash
# Clone the repository
git clone https://github.com/SudhirRaut-QA/indian-market-tracker.git

# Go into the folder
cd indian-market-tracker

# Install all required Python packages
pip install -r requirements.txt
```

> 💡 If `pip` is not found, try `pip3` or `python -m pip`

---

## Step 2 — Create a Telegram Bot (3 minutes)

A Telegram Bot is like a special account that can send and receive messages automatically.

### 2a. Create the bot

1. Open **Telegram** (phone or desktop)
2. Search for **`@BotFather`** — the official bot creator
3. Send him the message: `/newbot`
4. It will ask for a **name** → type anything (e.g., `My Market Bot`)
5. It will ask for a **username** → must end in `bot` (e.g., `my_market_2026_bot`)
6. BotFather replies with your **Bot Token** — looks like:
   ```
   1234567890:EXAMPLE_TOKEN_REPLACE_WITH_YOURS
   ```
7. **Copy this token and keep it safe.** Do NOT share it publicly!

### 2b. Get your Chat ID

1. Start a conversation with your new bot (search its username on Telegram and click `Start`)
2. Run this command in your terminal:
   ```bash
   python get_chat_id.py
   ```
3. It will show your **Chat ID** — a number like `123456789`

> 💡 **Group chat?** Add the bot to your group first, then run `get_chat_id.py`

---

## Step 3 — Configure Credentials

```bash
# Copy the template file
cp .env.example .env
```

Open `.env` in any text editor and fill in your values:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:EXAMPLE_TOKEN_REPLACE_WITH_YOURS
TELEGRAM_CHAT_ID=123456789

# Google Drive (optional — see GOOGLE_DRIVE_SETUP.md)
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=
```

> 🔒 **Security:** `.env` is listed in `.gitignore` — it will NEVER be uploaded to GitHub. Your token is safe.

---

## Step 4 — Test the Setup

### Verify configuration
```bash
python -m tracker --setup
```

Expected output:
```
✅ Telegram token: OK
✅ Telegram chat ID: OK
✅ NSE connection: OK
⭕ Google Drive: Not configured (optional)

Setup looks good! Run: python -m tracker --now
```

### Send your first test message
```bash
python -m tracker --now --full
```

Within 30 seconds, you should receive a Telegram message! 🎉

### Run just the trading engine (indices + setups)
```bash
python -m tracker --now
```

### Run pre-open analysis (best run before 9:15 AM IST)
```bash
python -m tracker --now --preopen
```

---

## Step 5 — Automate with GitHub Actions

This is the best part — **GitHub runs the bot for you, every day, for free.**

### 5a. Push to your GitHub

```bash
# Initialize git if needed
git init
git remote add origin https://github.com/YOUR_USERNAME/indian-market-tracker.git

# Push your code
git add .
git commit -m "Initial setup"
git push -u origin main
```

### 5b. Add GitHub Secrets

1. Go to your repository on GitHub.com
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add these:

| Secret Name | Value |
|-------------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from Step 2a |
| `TELEGRAM_CHAT_ID` | Your chat ID from Step 2b |

### 5c. Enable Actions

1. Click the **Actions** tab in your repository
2. Click **I understand my workflows, go ahead and enable them**
3. Done! ✅

**From tomorrow, you'll receive Telegram messages automatically at:**
- 09:00, 09:08, 09:15, 09:30, 11:00 IST (Morning Session)
- 15:35, 18:00, 21:00 IST (Afternoon Session)

---

## 🛠️ CLI Reference Card

```
COMMAND                                  WHAT IT DOES
────────────────────────────────────────────────────────────────────
python -m tracker --now                  Quick run — FII/DII + indices
python -m tracker --now --full           Everything — all data
python -m tracker --now --preopen        Pre-open market analysis
python -m tracker --now --corporate      Corporate actions + insider trades
python -m tracker --now --no-telegram    Skip Telegram (data only)
python -m tracker --now --no-excel       Skip Excel logging
python -m tracker --schedule             Run 8-slot daily scheduler locally
python -m tracker --setup                Verify your .env configuration
────────────────────────────────────────────────────────────────────
```

---

## 🐛 Troubleshooting

### ❌ "No module named tracker"
Make sure you are in the `indian-market-tracker` folder:
```bash
cd indian-market-tracker
python -m tracker --now
```

### ❌ "Telegram: Unauthorized" / "401"
Your Bot Token is wrong. Double-check `.env` — no extra spaces, no quotes around the token.

### ❌ "Telegram: Chat not found" / "400"
Your Chat ID is wrong. Re-run `python get_chat_id.py` after starting a conversation with the bot.

### ❌ "NSE connection failed" / "403"
NSE India occasionally blocks automated requests. The scraper uses TLS impersonation to work around this. If it still fails:
```bash
pip install --upgrade curl-cffi
```

### ❌ "Google Drive: File not found"
Your `GOOGLE_DRIVE_FOLDER_ID` may be wrong or the service account may not have access. See [GOOGLE_DRIVE_SETUP.md](GOOGLE_DRIVE_SETUP.md).

### ❌ GitHub Actions workflow not running
- Check if Actions is enabled (Settings → Actions → General)
- GitHub cron jobs can be delayed 5–30 min
- Trigger manually: Actions → select workflow → Run workflow

---

## 📅 Running Locally (No GitHub)

If you want to run it **on your own computer** instead of GitHub:

```bash
# Run the full scheduler — it fires all 8 slots throughout the day
python -m tracker --schedule

# Run just specific time slots
python -m tracker --schedule --slots "09:30,15:35,21:00"
```

> 💡 Your computer must be **on and connected** to the internet when each slot fires.

---

## 🔗 Next Steps

| I want to... | Go here |
|-------------|---------|
| Understand what "FII", "VIX", "PCR" mean | 📖 [GLOSSARY.md](GLOSSARY.md) |
| Set up Google Drive backup | ☁️ [GOOGLE_DRIVE_SETUP.md](GOOGLE_DRIVE_SETUP.md) |
| Understand the security model | 🔒 [SECURITY.md](SECURITY.md) |
| Add stocks to my watchlist | Send `/watchlist add SYMBOL PRICE` to your bot |