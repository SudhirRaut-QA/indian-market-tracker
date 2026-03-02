# Indian Market Tracker

Comprehensive NSE market intelligence delivered via Telegram.

Tracks FII/DII flows, 21 indices, 16 sectors, options PCR, commodities, forex, corporate actions, and insider trading — formatted as clean, easy-to-read messages.

---

## Features

| Feature | Description |
|---------|-------------|
| 💰 FII/DII | Foreign & domestic institutional flows with buy/sell signals |
| 📈 21 Indices | NIFTY 50, Bank, IT, Defence, PSU Bank, Momentum, High Beta, etc. |
| 🏭 16 Sectors | Per-stock analysis with gainers, losers, volume leaders |
| 📊 Options PCR | Put-Call ratio for NIFTY & BANKNIFTY with max pain |
| 🥇 Commodities | Gold (GOLDBEES), Silver (SILVERBEES) ETF tracking |
| 💱 Forex | USD/INR, EUR, GBP, JPY rates |
| 📋 Corporate | Dividends, splits, rights, bonus issues |
| 🔍 Insider Trading | PIT disclosures — who's buying/selling their own stock |
| 🔄 Delta Engine | Snapshot comparison — flow reversals, big movers |
| 📑 Excel Logger | Auto-logged to Excel with 7 colored sheets |
| ☁️ Google Drive | Auto-upload Excel/JSON to Google Drive (Shared Drive) |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env → add Telegram bot token, chat ID

# 3. Verify setup
python -m tracker --setup

# 4. Run once
python -m tracker --now

# 5. Start local scheduler (8 daily slots)
python -m tracker --schedule
```

### CLI Options

```
python -m tracker --now                          # Quick fetch (FII/DII + indices)
python -m tracker --now --full                   # Everything (sectors, options, corporate, insider)
python -m tracker --now --preopen                # Pre-open market analysis
python -m tracker --now --corporate              # Corporate actions + insider trading
python -m tracker --now --no-telegram --no-excel # Data only (JSON snapshot)
python -m tracker --schedule                     # 8-slot daily scheduler
python -m tracker --setup                        # Verify configuration
```

---

## Schedule (8 Daily Slots — Mon-Fri)

| IST | UTC | Slot | Data |
|-----|-----|------|------|
| 09:00 | 03:30 | Pre-Open Preview | Pre-open orders |
| 09:08 | 03:38 | Pre-Open Final | IEP settled |
| 09:15 | 03:45 | Market Open | First trades + indices |
| 09:30 | 04:00 | Early Session | FII/DII + sectors + options |
| 11:00 | 05:30 | Mid-Morning | Full snapshot + delta |
| 15:35 | 10:05 | Market Close | Closing snapshot + day delta |
| 18:00 | 12:30 | Post-Market | FII/DII final + corporate actions |
| 21:00 | 15:30 | Evening Digest | Full summary + insider trading |

---

## GitHub Actions (Automated)

The included workflow (`.github/workflows/market_tracker.yml`) runs **8 cron jobs** automatically on weekdays. Each slot triggers `python -m tracker --now` with the appropriate flags.

### Setup GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat/group ID |
| `GOOGLE_DRIVE_FOLDER_ID` | *(optional)* Shared Drive folder ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | *(optional)* Full JSON content of service account key |

> **Note**: GitHub Actions cron has ±5-20 min variance. For exact timing, use Activepieces or a VPS with crontab.

### Manual Trigger

You can also trigger manually from **Actions → Indian Market Tracker → Run workflow** and pick a run mode.

---

## Google Drive Backup (Optional)

Auto-uploads Excel and JSON snapshots to Google Drive after each run.

### Setup

1. Create a **Shared Drive** (Team Drive) in Google Workspace
2. Create a service account in Google Cloud Console → download JSON key
3. Share the Shared Drive folder with the service account email
4. Add folder ID and credentials path to `.env`

> **Important**: As of Sep 2024, Google does **not** allow service accounts to upload to personal Google Drive folders. You must use a **Shared Drive** or OAuth2 delegation.

See [GOOGLE_DRIVE_SETUP.md](GOOGLE_DRIVE_SETUP.md) for detailed instructions.

---

## Project Structure

```
indian-market-tracker/
├── tracker/
│   ├── __init__.py              # Version
│   ├── __main__.py              # CLI entry point
│   ├── config.py                # Configuration
│   ├── nse_scraper.py           # NSE API + forex data
│   ├── delta_engine.py          # Snapshot comparison
│   ├── telegram_bot.py          # Message formatting + sending
│   ├── excel_manager.py         # Excel logging (7 sheets)
│   ├── google_drive_uploader.py # Google Drive upload
│   ├── scheduler.py             # 8-slot daily scheduler
│   └── signal_detector.py       # Signal analysis
├── .github/workflows/
│   └── market_tracker.yml       # 8 cron-triggered GitHub Actions
├── credentials/                 # Service account JSON (gitignored)
├── data/                        # Generated data (gitignored)
├── setup.py                     # Interactive setup wizard
├── get_chat_id.py               # Telegram chat ID helper
├── test_tracker.py              # Local test suite
├── test_google_drive.py         # Google Drive connection test
├── list_drive_files.py          # List files in Drive folder
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Data Sources

| Source | What |
|--------|------|
| [NSE India](https://www.nseindia.com) | FII/DII, indices, sectors, options, corporate actions, insider trading |
| [Forex API](https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json) | USD/INR and currency rates |
| NSE Quote API | GOLDBEES, SILVERBEES commodity ETF prices |
