<div align="center">

# 🇮🇳 Indian Market Tracker

**NSE Market Intelligence · Automated · Delivered to Telegram**

[![Morning Session](https://img.shields.io/github/actions/workflow/status/SudhirRaut-QA/indian-market-tracker/morning_session.yml?label=Morning%20Session&logo=github&logoColor=white)](https://github.com/SudhirRaut-QA/indian-market-tracker/actions)
[![Afternoon Session](https://img.shields.io/github/actions/workflow/status/SudhirRaut-QA/indian-market-tracker/afternoon_session.yml?label=Afternoon%20Session&logo=github&logoColor=white)](https://github.com/SudhirRaut-QA/indian-market-tracker/actions)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Delivers%20via-Telegram-26A5E4?logo=telegram)](https://telegram.org)
[![NSE Data](https://img.shields.io/badge/Data%20Source-NSE%20India-orange)](https://nseindia.com)
[![Security](https://img.shields.io/badge/Secrets-Env%20Only%20%E2%9C%85-brightgreen)](SECURITY.md)

> *Your personal stock market assistant — 8 smart Telegram updates every weekday, fully automated.*

</div>

---

## 🗺️ Documentation Hub

> **New here? Start with QUICKSTART → then read GLOSSARY for terminology.**

| 📄 Document | 📝 What's Inside |
|-------------|-----------------|
| 🚀 **[QUICKSTART.md](QUICKSTART.md)** | Zero-to-Telegram in 15 minutes — step-by-step setup |
| 📖 **[GLOSSARY.md](GLOSSARY.md)** | Every term explained simply (FII, VIX, PCR, Pivot, R:R...) |
| ☁️ **[GOOGLE_DRIVE_SETUP.md](GOOGLE_DRIVE_SETUP.md)** | Auto-backup Excel & JSON to Google Drive |
| 🔒 **[SECURITY.md](SECURITY.md)** | How secrets are managed, what's safe to commit |

---

## 🤔 What Does This Do? (Simple Version)

Think of this as a **robot news reporter** that watches the stock market all day and texts you a summary.

```
  NSE India Website                          Your Telegram Phone
 ┌───────────────────┐                      ┌──────────────────────────────┐
 │  Who is buying?   │                      │  📊 Market: BULLISH ✅        │
 │  Which sectors    │  ───► Indian  ───►   │  💰 FII Buying ₹9,977 Cr     │
 │  are moving?      │      Market          │  📈 NIFTY +1.1% (23,450)     │
 │  How risky is     │      Tracker         │  🔥 Hot Sector: IT +2.1%     │
 │  the market?      │                      │  ⚡ Setup: INFY LONG R:R 2.1  │
 │  Any big news?    │                      │  😐 VIX 21.6 — Stay cautious │
 └───────────────────┘                      └──────────────────────────────┘
         ↑                                              ↑
   Checked 8× daily                         Sent automatically, no action needed
   Mon–Fri, 9AM–9PM IST
```

**In plain English:** Every weekday, this bot
1. Fetches live data from NSE India (the official stock exchange website)
2. Analyses it — who is buying, who is selling, how risky the market is
3. Sends you a clean, colour-coded Telegram message with what to watch

---

## ✨ Features

| Feature | What You Get | Why It Matters |
|---------|-------------|----------------|
| 💰 **FII / DII Flows** | Foreign & domestic institution buy/sell amounts | Big money direction = market direction |
| 📈 **21 Indices** | NIFTY 50, Bank, IT, Defence, PSU Bank, Midcap... | See which segments are strong or weak |
| 🏭 **16 Sectors** | Top gainers, losers, volume leaders per sector | Find where money is rotating |
| 📊 **Options PCR** | Put-Call ratio + max pain for NIFTY & BANKNIFTY | Gauge market sentiment objectively |
| 🧭 **Trading Engine** | Pivot, CPR, VWAP setups with 5-dim confidence score (0–100) | Actionable setups filtered by quality, not just signal count |
| 🎯 **Confidence Scoring** | Trend × Volume × Technical × Market Harmony × R:R | Only high-conviction setups recommended |
| 👁️ **On Watch Section** | Near-threshold setups when market is quiet | Never see an empty setups page — always has monitor candidates |
| 🔥 **Momentum Scanner** | RS-ranked stocks with volume confirmation | Catch breakouts before they run |
| 👁️ **Watchlist Tracker** | Live P&L vs entry price; honest proxy on day of entry | Know if you should hold, add, or exit |
| 🧠 **Expert Opinion** | AI-style market verdict with VIX live change % | Understand fear level trajectory, not just a static number |
| 🤖 **Self-Tuning Algo** | EOD review auto-adjusts confidence floor, sector blacklist | Gets smarter every trading day |
| 🥇 **Commodities** | Gold & Silver ETF prices (TATAGOLD, TATSILV) | Hedge signals and inflation gauge |
| 💱 **Forex** | USD/INR, EUR/INR, GBP/INR, JPY/INR | Impact on IT, pharma, export stocks |
| 📋 **Corporate Actions** | Multi-source: NSE + BSE + NSE Board Meetings + NSE Announcements; Dividends with yield% & annual totals, splits, rights, bonuses | Never miss an important date — 90+ upcoming events per run |
| 📡 **MCX Price Drivers** | Global commodity futures — Gold, Silver, Crude Oil, Natural Gas (via Yahoo Finance spark) | Context for metal/energy stocks and MCX-linked trades |
| 🩺 **Feed Health Monitor** | Per-source live status (🟢 ok / 🟡 no-data / 🔴 error) persisted to `feed_health.json` and shown in every corporate Telegram message | Know instantly which data is fresh vs degraded |
| 🔍 **Insider Trading** | PIT disclosures — who's buying their own stock | Promoters buying = confidence signal |
| � **Bulk & Block Deals** | Large trades (>0.5% equity in one shot) by institutions | Spot smart-money accumulation or distribution |
| 🌐 **Global Indices** | S&P 500, NASDAQ, Dow Jones, Nikkei 225, Hang Seng, FTSE 100 (via Yahoo Finance) | Pre-market global cues — see what drove overnight moves |
| 😱 **Fear & Greed Index** | CNN composite sentiment (0=Extreme Fear, 100=Extreme Greed) | Contrarian indicator — high greed = caution, high fear = opportunity |
| 🎯 **Phase 4 Signal Intelligence** | Multi-factor sector scoring (FII flows + global cues + sentiment) → Top 3 stock picks per session | Prioritise your watch with quantified conviction |
| 📈 **Phase 4 Accuracy Tracker** | Rolling 5-session hit-rate with P&L table (entry→current, %) | Know if the system's picks are actually working |
| 🌍 **Weekend Global Report** | Sunday 21:00 IST — global equity, Fear & Greed, DXY + Brent composite outlook | Monday morning edge: see what Asia and the US did over the weekend |
| �🔄 **Delta Engine** | Snapshot comparison — what changed since last check | Spot reversals and accelerations |
| 📑 **Excel Logger** | All data auto-saved to 7 colour-coded sheets | Your own offline analytics database |
| ☁️ **Google Drive** | Auto-upload after every run | Cloud backup, accessible anywhere |

---

## 🏗️ How It Works (Architecture)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     GITHUB ACTIONS (Cloud)                          │
│  ┌────────────────────────┐    ┌───────────────────────────────┐   │
│  │   Morning Session      │    │   Afternoon Session           │   │
│  │   09:00–11:00 IST      │    │   15:35–21:00 IST             │   │
│  │   (02:30 UTC cron)     │    │   (09:42 UTC cron)            │   │
│  └──────────┬─────────────┘    └────────────┬──────────────────┘   │
│             └──────────────┬────────────────┘                       │
│                            ▼                                        │
│              ┌─────────────────────────┐                           │
│              │   python -m tracker     │                           │
│              │   --schedule --slots    │                           │
│              └────────────┬────────────┘                           │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
            ┌───────────────▼───────────────┐
            │         tracker/              │
            │  ┌──────────────────────┐     │
            │  │  nse_scraper.py      │◄────┼─── NSE India API
            │  │  (Live market data)  │◄────┼─── BSE India API (TLS)
            │  │                      │◄────┼─── Yahoo Finance (MCX drivers)
            │  │                      │◄────┼─── Forex API
            │  └──────────┬───────────┘     │
            │             ▼                 │
            │  ┌──────────────────────┐     │
            │  │  trading_engine.py   │     │
            │  │  (Pivot, VWAP, Bias) │     │
            │  └──────────┬───────────┘     │
            │             ▼                 │
            │  ┌──────────────────────┐     │
            │  │  signal_detector.py  │     │
            │  │  (Phase 1-4 Signals) │     │
            │  └──────────┬───────────┘     │
            │             ▼                 │
            │  ┌──────────────────────┐     │
            │  │  delta_engine.py     │     │
            │  │  (What changed?)     │     │
            │  └──────────┬───────────┘     │
            │             ▼                 │
            │  ┌──────────────────────┐     │
            │  │  telegram_bot.py     │────►├─── 📱 Telegram
            │  │  (Format & Send)     │     │
            │  └──────────────────────┘     │
            │  ┌──────────────────────┐     │
            │  │  excel_manager.py    │────►├─── 📊 Excel File
            │  └──────────────────────┘     │
            │  ┌──────────────────────┐     │
            │  │  google_drive_       │────►└─── ☁️ Google Drive
            │  │  uploader.py         │
            │  └──────────────────────┘
            └───────────────────────────────┘
```

---

## ⚡ Quick Start

> 📋 **Full setup guide:** [QUICKSTART.md](QUICKSTART.md)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your credentials
cp .env.example .env
# Edit .env — add your Telegram bot token and chat ID

# 3. Verify everything works
python -m tracker --setup

# 4. Run once to test
python -m tracker --now --full

# 5. Start the scheduler (runs all 8 daily slots)
python -m tracker --schedule
```

### CLI Reference

```
python -m tracker --now                            Quick fetch (FII + indices)
python -m tracker --now --full                     Full run (all data)
python -m tracker --now --preopen                  Pre-open market analysis
python -m tracker --now --corporate                Corporate actions (fast — skips indices)
python -m tracker --now --corporate --full         Corporate + full market data
python -m tracker --now --no-telegram --no-excel   Data only (JSON snapshot)
python -m tracker --schedule                       8-slot daily scheduler
python -m tracker --setup                          Verify configuration
```

---

## 🕐 Daily Schedule (8 Slots, Mon–Fri)

```
IST     UTC      Slot               What You Receive
──────  ───────  ─────────────────  ─────────────────────────────────────────
09:00   03:30    Pre-Open Preview   Early orders, IEP estimates, gap direction
09:08   03:38    Pre-Open Final     Settled pre-open prices before bell
09:15   03:45    Market Open        First prints, index direction, big movers
09:30   04:00    Early Session      FII/DII flows + sector + options PCR
11:00   05:30    Mid-Morning        Full snapshot + delta (what changed?)
15:35   10:05    Market Close       Day's closing snapshot + Phase 4 picks logged
18:00   12:30    Post-Market        Provisional FII/DII (fresh) + corporate actions
21:00   15:30    Evening Digest     Final data + global indices (live US session) + watchlist
──────  ───────  ─────────────────  ─────────────────────────────────────────
Sun     15:30    Weekend Global     S&P/NASDAQ/Nikkei/Hang Seng + Fear & Greed + Monday preview
──────  ───────  ─────────────────  ─────────────────────────────────────────
```

---

## ☁️ GitHub Actions (Fully Automated — No Server Needed!)

The repo includes **2 GitHub Actions workflows** that run automatically every weekday:

```
.github/workflows/
├── morning_session.yml     ← 09:00–11:00 IST (5 slots)
└── afternoon_session.yml   ← 15:35–21:00 IST (3 slots)
```

### Setup in 3 Steps

**Step 1 — Fork the repo** (or push to your GitHub)

**Step 2 — Add secrets** (`Settings → Secrets and variables → Actions`):

| Secret Name | Where to Get It | Required? |
|-------------|----------------|-----------|
| `TELEGRAM_BOT_TOKEN` | Message @BotFather on Telegram | ✅ Yes |
| `TELEGRAM_CHAT_ID` | Run `python get_chat_id.py` | ✅ Yes |
| `GOOGLE_DRIVE_FOLDER_ID` | From your Drive folder URL | ⭕ Optional |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Cloud Console | ⭕ Optional |

**Step 3 — Enable Actions** in your fork → it runs automatically!

> ⚠️ **GitHub cron has ±5–20 min variance.** For exchange-precise timing, run locally or use a VPS with crontab.

---

## 📁 Project Structure

```
indian-market-tracker/
│
├── 📂 tracker/                    Core Python package
│   ├── __main__.py                CLI entry point  (python -m tracker)
│   ├── config.py                  All settings, thresholds, sector lists
│   ├── nse_scraper.py             Fetches data from NSE India + Forex API
│   ├── trading_engine.py          Pivot levels, CPR, VWAP, bias scoring, setups
│   ├── delta_engine.py            Snapshot comparison — detects changes
│   ├── telegram_bot.py            Formats and sends all Telegram messages
│   ├── excel_manager.py           Writes 7-sheet Excel workbook
│   ├── google_drive_uploader.py   Uploads Excel/JSON to Google Drive
│   ├── scheduler.py               Runs the 8-slot daily schedule
│   ├── signal_detector.py         52-week levels, delivery, volume signals
│   ├── trade_tracker.py           Logs recommendations, EOD review, auto-tunes
│   └── interactive_bot.py        Telegram command handler (/watchlist, /help)
│
├── 📂 .github/workflows/          Automation
│   ├── morning_session.yml        Runs 09:00–11:00 IST slots
│   └── afternoon_session.yml      Runs 15:35–21:00 IST slots
│
├── 📂 credentials/                🔒 GITIGNORED — never committed
│   └── service-account.json       Google service account key
│
├── 📂 data/                       Auto-generated runtime data
│   ├── excel/market_tracker.xlsx  Excel workbook (all history)
│   ├── excel/upcoming_dividends_latest.xlsx  Dividend tracker with yield & PE
│   ├── excel/rebuild_upcoming_dividends.py   Rebuild dividend Excel from NSE
│   ├── excel/DIVIDEND_WORKFLOW.md            One-click dividend workflow docs
│   ├── feed_health.json           Per-source feed status (updated every run)
│   └── snapshots/                 JSON snapshots for delta comparison
│
├── .env                           🔒 GITIGNORED — your secrets go here
├── .env.example                   Template — copy to .env
├── .gitignore                     Protects credentials and .env from git
├── requirements.txt               Python package dependencies
├── setup.py                       Interactive first-time setup wizard
├── get_chat_id.py                 Helper to find your Telegram chat ID
│
├── 📖 README.md                   ← You are here
├── 📖 QUICKSTART.md               Step-by-step beginner setup
├── 📖 GLOSSARY.md                 All terms explained simply
├── 📖 GOOGLE_DRIVE_SETUP.md       Cloud backup setup
└── 📖 SECURITY.md                 Secret management guide
```

---

## 🔒 Security Design

This project is **public on GitHub** — here is exactly what is and isn't safe:

| Item | In Git? | Why Safe? |
|------|---------|-----------|
| `tracker/*.py` | ✅ Yes | Source code only — no secrets embedded |
| `.env.example` | ✅ Yes | Template with placeholder values only |
| `data/snapshots/last_snapshot.json` | ✅ Yes | Public market data only |
| `.env` | ❌ **Gitignored** | Contains your real token — never committed |
| `credentials/*.json` | ❌ **Gitignored** | Service account keys — never committed |
| GitHub Secrets | 🔐 Encrypted | Only available inside Actions, never in logs |

**All secrets flow in via environment variables** — zero hardcoded credentials anywhere.

> 📋 Full details: [SECURITY.md](SECURITY.md)

---

## 📊 Data Sources

| Source | Data Provided |
|--------|--------------|
| [NSE India](https://www.nseindia.com) | FII/DII, 21 indices, 16 sectors, options chain, corporate actions, insider trading, bulk/block deals, pre-open |
| [Yahoo Finance](https://finance.yahoo.com) (spark API) | Global indices (S&P 500, NASDAQ, Dow Jones, Nikkei 225, Hang Seng, FTSE 100), DXY Dollar Index, Brent Crude, Gold, Silver, Natural Gas futures |
| [CNN Fear & Greed](https://production.dataviz.cnn.io/index/fearandgreed/current) | US market sentiment score (0–100) — Extreme Fear → Greed |
| [Fawaz Currency API](https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json) | USD/INR, EUR/INR, GBP/INR, JPY/INR |
| NSE Quote API | TATAGOLD, TATSILV, GOLDBEES, LIQUIDBEES ETF prices |

---

## 🆕 Recent Enhancements (Jun 2026)

### Phase 1–4 Signal Intelligence

| Phase | Enhancement | Detail |
|-------|-------------|--------|
| **Phase 1** | FII/DII Rolling Signal | Historical profiling with daily-dedup (snapshot counting fixed), magnitude override at ±₹2,000 Cr threshold |
| **Phase 2** | Bulk & Block Deals | Large institutional trades tracked alongside insider PIT disclosures |
| **Phase 3** | Global Intelligence | S&P 500, NASDAQ, Dow, Nikkei, Hang Seng, FTSE via Yahoo Finance; CNN Fear & Greed; DXY + Brent macro overlay |
| **Phase 4** | Sector Prediction & Picks | Multi-factor sector scoring → Top 3 stock picks with entry price, score, 5-day return projection |
| **Add-on** | Accuracy Feedback Loop | `log_phase4_picks` + `compute_phase4_accuracy` — rolling hit-rate bar, P&L per pick, 5-session window |
| **Add-on** | Weekend Global Report | Sunday 21:00 IST slot — global equity table, Fear & Greed bar, composite outlook emoji |
| **Critical Fix** | Cache-Mode Staleness | 18:00/21:00 cache slots now always refresh FII/DII + global indices + sentiment (was silently 5 h+ stale) |

### Trader-Grade Algorithm

| Enhancement | Detail |
|-------------|--------|
| **5-Dim Confidence Score (0–100)** | Every setup scored: Trend(25) + Volume(20) + Technical(25) + Market Harmony(20) + R:R(10). Only confident setups recommended. |
| **Smart Entry Logic** | Refuses to enter if stock already moved >3.5% from pivot (chasing filter). |
| **Position Sizing** | Position size adjusts by VIX level, R:R ratio and confidence score. Higher fear = smaller position. |
| **Sector Blacklist** | Sectors with <30% win rate are auto-blacklisted by the EOD review. No more bad-sector setups. |
| **On Watch Section** | When fewer than 2 LONG or SHORT setups pass the threshold, a monitoring sub-section auto-populates using threshold−15. Users always see candidates. |
| **Self-Tuning Confidence Floor** | EOD auto-tunes: floor drops to 45 if win rate >60%, rises to 60 if win rate <40%. |

### Data Accuracy & Display

| Fix | Detail |
|-----|--------|
| **VIX shows daily change %** | `VIX 25.5 (+5.2% today)` — proves the value is live from NSE, not cached. |
| **52W Low × SHORT contradiction fixed** | Near 52W low is a LONG reversal zone, not a short setup. Shorts near 52W low lose −15 confidence pts. |
| **52W Low labels** | Labeled `Potential Reversal — LONG only, not SHORT` with explicit warning in signal page. |
| **Watchlist score on day of entry** | Entry-day score now uses stock's day pct change (proxy), not the meaningless 0.00% vs entry. Shows `3🟢 up today (entry just set)`. |

---

## 🙋 FAQ

**Q: Do I need to pay for anything?**
All data sources are free. GitHub Actions free tier (2,000 min/month) is sufficient.

**Q: Will it work if I am not in India?**
Yes! GitHub Actions runs in the cloud. Your timezone does not matter.

**Q: Is the data real-time?**
NSE data is delayed ~15 minutes per NSE's public API policy. Pre-market data is real-time.

**Q: Can I add my own stocks to the watchlist?**
Yes — message `/watchlist add SYMBOL PRICE` to your Telegram bot.

**Q: What happens on market holidays?**
The scheduler runs but NSE returns no data — the bot sends a "Market Closed" notice.

**Q: I see `R:R 2.1` in a message — what does that mean?**
Risk-to-Reward ratio. See 📖 [GLOSSARY.md](GLOSSARY.md) for all terms explained simply.

---

<div align="center">

Made with ❤️ for Indian retail investors · Data from [NSE India](https://nseindia.com)

</div>