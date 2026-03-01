# 🇮🇳 Indian Market Tracker

**Comprehensive NSE market intelligence with Telegram alerts.**

Track FII/DII flows, sector analysis, options PCR, commodities, forex, corporate actions, and insider trading — all in kid-friendly, easy-to-understand messages.

## Features

| Feature | Description |
|---------|-------------|
| 💰 FII/DII | Foreign & domestic institutional flows with buy/sell signals |
| 📈 21 Indices | NIFTY 50, Bank, IT, Defence, PSU Bank, Momentum, High Beta, etc. |
| 🏭 16 Sectors | Per-stock analysis with gainers, losers, volume leaders |
| 🎯 Smart Signals | 10 buy/sell indicators: 52W breakout, momentum, delivery%, institutional flow |
| 📊 Options PCR | Put-Call ratio for NIFTY & BANKNIFTY with max pain |
| 🥇 Commodities | Gold (GOLDBEES), Silver (SILVERBEES) ETF tracking |
| 💱 Forex | USD/INR, EUR, GBP, JPY rates |
| 📋 Corporate | Dividends, splits, rights, bonus issues with IPO tracking |
| 🔍 Insider Trading | PIT disclosures — who's buying/selling their own stock |
| 🔄 Delta Engine | Track changes between snapshots (flow reversals, big movers) |
| 📑 Excel Logger | Auto-logged to Excel with 7 colored sheets |
| 💬 Interactive Bot | Optional Telegram UI with inline keyboard buttons |
| 🛡️ Enterprise Reliability | Rate limiting, circuit breaker, exponential backoff, session stats |

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Setup
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID

# Verify everything works
python -m tracker --setup

# Run once (quick check)
python -m tracker --now

# Run with ALL data
python -m tracker --now --full

# Pre-open analysis (9:00-9:15 AM)
python -m tracker --now --preopen

# Corporate actions + insider trading
python -m tracker --now --corporate

# Start 8-slot daily scheduler
python -m tracker --schedule

# Scheduler with time window (3 hour morning run for GitHub Actions)
python -m tracker --schedule --run-for-minutes 180

# Interactive Telegram bot with inline buttons (long-running)
python -m tracker.interactive_bot

# Data only (no Telegram, no Excel)
python -m tracker --now --full --no-telegram --no-excel
```

## 🎯 Smart Signal Detection

The signal detector analyzes market snapshots and generates buy/sell/watch recommendations:

### Buy Signals (6 indicators):
- **52W Breakout**: Within 2% of 52-week high with volume
- **Oversold Bounce**: Price >5% above 52W low (reversal zone)
- **High Delivery%**: ≥70% delivery (institutional accumulation)
- **30D Momentum**: +15% gain in last 30 days
- **Sector Leader**: Top 3 in sector + outperforming sector avg
- **Institutional Buying**: Positive FII flow with NIFTY strength

### Sell Signals (4 indicators):
- **Distribution**: Price near 52W high but delivery% <40%
- **Failed Breakout**: Was near 52W high, now >3% below
- **Weak Momentum**: Negative 30D performance
- **Sector Laggard**: Bottom 3 in sector + underperforming

### Confidence Scoring:
- **Strong**: ≥3 indicators align (high conviction)
- **Moderate**: 2 indicators (watch closely)
- **Weak**: 1 indicator (early signal)

Signals are automatically included in Telegram messages when `--full` flag is used.

## 💬 Interactive Telegram Bot

For a mobile-friendly experience, run the interactive bot with inline keyboard:

```bash
python -m tracker.interactive_bot
```

**Features**:
- 📊 **Market Pulse**: View latest snapshot with sentiment scoring
- 🏭 **Sectors**: Browse all 16 sectors with stock-level details
- 📈 **Options PCR**: NIFTY/BANKNIFTY put-call ratios
- 🏆 **Commodities**: Gold/Silver ETF performance
- 🎯 **Buy/Sell Signals**: Smart trading recommendations with confidence
- 📡 **52W Alerts**: Stocks near 52-week highs/lows
- 🔄 **Refresh Data**: Trigger on-demand scrape

**Note**: Interactive bot requires long-running process (VPS/local deployment). For GitHub Actions, use standard scheduler which sends formatted messages without buttons.

## 🛡️ Enterprise Reliability

Corporate-grade reliability patterns ensure zero failures:

### Rate Limiting
- **Token bucket algorithm**: Max 30 API calls per 60 seconds
- Prevents NSE API bans and 429 errors
- Automatic queuing when limit reached

### Circuit Breaker
- **Failure threshold**: Opens after 5 consecutive failures
- **Recovery mode**: Half-open state tests after 60s timeout
- Prevents cascading failures and resource exhaustion

### Exponential Backoff
- Retry delay: `base_delay × 2^attempt` (1s → 2s → 4s → 8s)
- Respects `Retry-After` header for 429 responses
- Max 5 retries before giving up

### Session Statistics
```python
# At end of each run
stats = scraper.nse.get_stats()
# Output: "45 calls, 43 successful (95.6%), circuit: CLOSED"
```

All tracking automatically logged — no configuration needed.
```

## Schedule (8 Daily Notifications)

| Time (IST) | What | Why | Workflow |
|-------------|------|-----|----------|
| 09:00 | Pre-Open Preview | See where stocks will open | Morning (3hr) |
| 09:08 | Pre-Open Final | IEP settled, final pre-open prices | Morning (3hr) |
| 09:15 | Market Open | First trades + index levels | Morning (3hr) |
| 09:30 | Early Session | FII/DII + sector moves start showing | Morning (3hr) |
| 11:00 | Mid-Morning | Full snapshot + delta vs morning | Morning (3hr) |
| 15:35 | Market Close | Closing snapshot + full day delta | Afternoon (6hr) |
| 18:00 | Post-Market | Final FII/DII + corporate actions | Afternoon (6hr) |
| 21:00 | Evening Digest | Full summary + insider trading | Afternoon (6hr) |

**GitHub Actions Strategy**:
- **Morning workflow** (08:45-11:45 IST): Runs for 180 minutes, covers 5 slots
- **Afternoon workflow** (15:30-21:30 IST): Runs for 360 minutes, covers 3 post-market slots
- Each workflow exits gracefully when time window expires

## Delta Engine (Change Tracking)

The delta engine compares each snapshot with the previous one:

- **FII/DII Reversals**: "Was BUYING → Now SELLING" alerts
- **Index Movements**: Which index moved most since last check
- **Stock Movers**: Price & volume changes between snapshots
- **Commodity & Forex**: Gold/Silver/USD movement tracking

## Project Structure

```
indian-market-tracker/
├── tracker/
│   ├── __init__.py          # Version
│   ├── __main__.py          # CLI entry point
│   ├── config.py            # All configuration
│   ├── nse_scraper.py       # NSE API + rate limiter + circuit breaker
│   ├── delta_engine.py      # Snapshot comparison engine
│   ├── signal_detector.py   # Buy/sell signal generation (10 indicators)
│   ├── telegram_bot.py      # Message formatting + sending
│   ├── interactive_bot.py   # Optional: inline keyboard UI
│   ├── excel_manager.py     # Excel logging (7 sheets)
│   └── scheduler.py         # 8-slot scheduler + windowed execution
├── .github/workflows/
│   ├── morning_tracker.yml  # 08:45 IST, 3-hour window
│   └── afternoon_tracker.yml # 15:30 IST, 6-hour window
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## GitHub Actions Setup

Two workflows provide full-day coverage with windowed execution:

### Morning Workflow (`morning_tracker.yml`)
- **Trigger**: 08:45 IST (03:15 UTC) Mon-Fri
- **Duration**: 180 minutes (3 hours)
- **Slots covered**: 09:00, 09:08, 09:15, 09:30, 11:00
- **Timeout**: 190 minutes safety buffer
- **Command**: `python -m tracker --schedule --run-for-minutes 180`

### Afternoon Workflow (`afternoon_tracker.yml`)
- **Trigger**: 15:30 IST (10:00 UTC) Mon-Fri
- **Duration**: 360 minutes (6 hours)
- **Slots covered**: 15:35, 18:00, 21:00
- **Timeout**: 360 minutes (full duration)
- **Command**: `python -m tracker --schedule --run-for-minutes 360`
- **Extras**: Daily backup at end of run

### Required Secrets
Add to your GitHub repo settings (Settings → Secrets → Actions):
- `TELEGRAM_BOT_TOKEN`: Your bot token from @BotFather
- `TELEGRAM_CHAT_ID`: Your chat ID (use @userinfobot)

### Features
- ✅ Auto-commit data updates to repo
- ✅ Artifact uploads (JSON snapshots + Excel)
- ✅ Manual workflow dispatch for testing
- ✅ Graceful shutdown when time window expires
- ✅ Python dependency caching for faster runs

**Why 2 workflows?** GitHub Actions has 6-hour timeout per job. Splitting into morning (3hr) and afternoon (6hr) ensures all 8 slots execute reliably without hitting limits.

## Alternative: Activepieces

**GitHub Actions** (included): Works great, but ±5 min timing variance on cron triggers.  
**Activepieces** (recommended for production): Exact timing, webhook triggers, visual workflow builder, longer execution windows.

## Data Sources

- **NSE India** (nseindia.com): FII/DII, indices, sectors, options, corporate actions, insider trading
- **Free Forex API** (jsdelivr.net): USD/INR and other currency rates
- **Commodity ETFs**: GOLDBEES (gold), SILVERBEES (silver) via NSE quotes
