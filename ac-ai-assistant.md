<!--  This file gives the AI assistant
     durable context about this repository so it doesn't have to re-read the
     codebase every chat. Safe to edit — your changes are respected and kept. -->

# Indian Market Tracker — Onboarding Document

## Overview

Indian Market Tracker is an automated NSE (National Stock Exchange of India) market intelligence system. It scrapes live market data from NSE India, analyses institutional flows, sector rotation, options sentiment, and technical setups, then delivers colour-coded summaries to a Telegram channel — 8 times per weekday during market hours (9 AM–9 PM IST).

The system is fully automated via GitHub Actions with two scheduled workflows (morning and afternoon sessions) and requires zero manual intervention once configured.

---

## Architecture

The system follows a pipeline architecture:

```
NSE India (Web) ─► nse_scraper ─► snapshot (JSON) ─► delta_engine ─► signal_detector
                                                                          │
                                                          trading_engine ◄─┘
                                                                │
                                    telegram_bot ◄──────────────┘
                                         │
                                    Telegram Channel
                                         │
                              google_drive_uploader / excel_manager (backup)
```

### Core Data Flow

1. **Scraping** (`tracker/nse_scraper.py`) — Fetches FII/DII flows, index data (21 indices), sector performance (16 sectors), options data (PCR, max pain) from NSE India using `curl_cffi` (to handle TLS fingerprinting).
2. **Snapshot Storage** (`data/snapshots/`) — Each fetch produces a timestamped JSON snapshot (`snapshot_YYYYMMDD_HHMMSS.json`).
3. **Delta Computation** (`tracker/delta_engine.py`) — Compares current snapshot to previous ones to detect changes, momentum, and rotations.
4. **Signal Detection** (`tracker/signal_detector.py`) — Identifies market conditions, sentiment, and potential setups.
5. **Trading Engine** (`tracker/trading_engine.py`) — Generates actionable setups (Pivot, CPR, VWAP) with a 5-dimensional confidence score (0–100): Trend × Volume × Technical × Market Harmony × Risk:Reward.
6. **Delivery** (`tracker/telegram_bot.py`) — Formats and sends structured Telegram messages.
7. **Backup** — Excel files and JSON snapshots are uploaded to Google Drive (`tracker/google_drive_uploader.py`).

---

## Key Directories & Files

| Path | Purpose |
|------|---------|
| `tracker/` | Main Python package (all core logic) |
| `tracker/__main__.py` | Entry point — run via `python -m tracker` |
| `tracker/config.py` | Configuration: API keys, thresholds, index lists |
| `tracker/nse_scraper.py` | NSE India data fetcher (handles anti-bot measures) |
| `tracker/delta_engine.py` | Computes deltas between market snapshots |
| `tracker/signal_detector.py` | Market signal / sentiment detection |
| `tracker/trading_engine.py` | Generates trading setups with confidence scoring |
| `tracker/trade_tracker.py` | Tracks recommended trades and outcomes |
| `tracker/telegram_bot.py` | Telegram message formatting and sending |
| `tracker/interactive_bot.py` | Interactive Telegram bot (command-based queries) |
| `tracker/scheduler.py` | Intra-day scheduling logic (8× per day) |
| `tracker/excel_manager.py` | Excel file read/write (openpyxl) |
| `tracker/google_drive_uploader.py` | Google Drive backup via service account |
| `data/snapshots/` | Timestamped JSON market snapshots |
| `data/snapshots/last_snapshot.json` | Symlink/copy of most recent snapshot |
| `data/daily/` | Daily aggregated JSON (e.g. `2026-03-01.json`) |
| `data/backup/` | ZIP archives of historical data |
| `data/excel/` | Excel workbooks + dividend workflow scripts |
| `data/trading/recs/` | Daily trading recommendations (JSON, date-keyed) |
| `data/trading/phase4_picks/` | Phase-4 trading picks |
| `data/watchlist/` | Daily watchlist JSONs |
| `data/feed_health.json` | Health/status of data feeds |
| `credentials/service-account.json` | Google Cloud service account for Drive API |
| `.github/workflows/morning_session.yml` | GitHub Actions: morning market session |
| `.github/workflows/afternoon_session.yml` | GitHub Actions: afternoon market session |
| `QUICKSTART.md` | Setup guide (zero to Telegram in 15 min) |
| `GLOSSARY.md` | Domain terminology (FII, VIX, PCR, Pivot, R:R, etc.) |
| `GOOGLE_DRIVE_SETUP.md` | Google Drive backup configuration |
| `SECURITY.md` | Secrets management policy |

### Dividend Workflow (Excel)

| File | Purpose |
|------|---------|
| `data/excel/DIVIDEND_WORKFLOW.md` | Process documentation |
| `data/excel/rebuild_upcoming_dividends.py` | Rebuilds dividend calendar |
| `data/excel/refresh_dividend_metrics.py` | Updates dividend metrics |
| `data/excel/upcoming_dividends_latest.csv` | Latest dividend data (CSV) |
| `data/excel/upcoming_dividends_latest.xlsx` | Latest dividend data (Excel) |
| `data/excel/open_live_dividends.bat` | Windows batch to open live view |
| `data/excel/enable_excel_auto_refresh.ps1` | PowerShell for Excel auto-refresh |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| HTTP Client | `requests` + `curl_cffi` (TLS fingerprint bypass for NSE) |
| Configuration | `python-dotenv` (environment variables) |
| Excel I/O | `openpyxl` |
| Scheduling | `schedule` library (in-process) |
| Cloud Backup | Google Drive API (`google-api-python-client`, `google-auth`) |
| Messaging | Telegram Bot API (direct HTTP, no wrapper library) |
| CI/CD | GitHub Actions (cron-scheduled workflows) |
| Data Format | JSON (snapshots, recs, watchlist), Excel/CSV (dividends) |

---

## Build / Test / Run

### Prerequisites

- Python 3.11+
- Telegram Bot Token + Chat ID
- (Optional) Google Cloud service account JSON for Drive backup

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Environment Variables

Secrets are managed via environment variables (never committed). Expected vars (based on SECURITY.md and code patterns):

- `TELEGRAM_BOT_TOKEN` — Telegram bot API token
- `TELEGRAM_CHAT_ID` — Target chat/channel ID
- `GOOGLE_SERVICE_ACCOUNT_JSON` — (or file at `credentials/service-account.json`)

Use a `.env` file locally (loaded by `python-dotenv`).

### Run Locally

```bash
python -m tracker
```

This invokes `tracker/__main__.py`, which likely starts the scheduler for periodic scraping and reporting.

### Utility Scripts

| Script | Purpose |
|--------|---------|
| `get_chat_id.py` | Retrieve your Telegram chat ID |
| `list_drive_files.py` | List files in configured Google Drive folder |
| `reset_snapshot.py` | Reset/clear snapshot state |
| `create_mock_2025_snapshot.py` | Generate mock snapshot for testing |
| `show_ann_yield_working.py` | Debug annual yield calculation |

### GitHub Actions (Automated)

Two workflows run on cron schedules (Mon–Fri, IST market hours):

- **`.github/workflows/morning_session.yml`** — Morning session updates
- **`.github/workflows/afternoon_session.yml`** — Afternoon session updates

These are the primary production execution paths. Secrets are configured in the GitHub repository settings.

---

## Testing Approach

Tests are ad-hoc scripts at the repository root (no formal test framework like pytest detected):

| Test File | Focus |
|-----------|-------|
| `test_annual_dividend_fix.py` | Annual dividend yield calculation fix |
| `test_annual_fix.py` | Related annual calculation fix |
| `test_djml.py` | Testing against `debug_djml.json` data |
| `test_mock_2025.py` | Testing with mock 2025 snapshot data |
| `test_telegram_fix.py` | Telegram message formatting fix |
| `create_mock_2025_snapshot.py` | Generates `data/snapshots/snapshot_test_2025data.json` |

Run tests individually:

```bash
python test_telegram_fix.py
python test_mock_2025.py
```

There is no `pytest.ini`, `tox.ini`, or test runner configuration — tests are standalone verification scripts.

---

## Coding Standards & Conventions

- **Secrets**: Environment variables only. No API keys, tokens, or credentials in code or committed files. See `SECURITY.md`.
- **Snapshot naming**: `snapshot_YYYYMMDD_HHMMSS.json` — consistent timestamp format.
- **Daily data**: `YYYY-MM-DD.json` (ISO date).
- **Package structure**: All core logic in `tracker/` package; entry point is `tracker/__main__.py`.
- **No external Telegram SDK**: Telegram Bot API is called directly via HTTP (using `requests`).
- **`curl_cffi`**: Used instead of plain `requests` for NSE endpoints that require browser-like TLS fingerprints.
- **Data persistence**: JSON files in `data/` directory tree; no database.

---

## Important Notes & Gotchas

1. **NSE Anti-Bot Measures**: NSE India blocks standard Python HTTP clients. The project uses `curl_cffi` which impersonates browser TLS fingerprints. If NSE changes their anti-bot measures, `nse_scraper.py` will break first.

2. **Market Hours Only**: The system is designed for IST weekdays 9 AM–9 PM. Running outside these hours will produce stale or empty data from NSE.

3. **`credentials/service-account.json`**: This file is in the repo tree but should contain only the structure/placeholder — actual credentials should be injected via CI secrets or kept local-only. Verify this is not exposing real credentials.

4. **No Database**: All state is stored in flat JSON files under `data/`. Snapshots accumulate over time and are not automatically pruned (backups are ZIP'd to `data/backup/`).

5. **Duplicate README**: Both `README.md` and `readme.md` exist with identical content — likely a case-sensitivity artifact on case-insensitive file systems.

6. **Excel Workflow is Windows-Oriented**: The `open_live_dividends.bat` and `enable_excel_auto_refresh.ps1` scripts target Windows environments; the dividend Excel workflow assumes local Windows + Excel.

7. **`setup.py` exists** but no `pyproject.toml` — the package can be installed in editable mode (`pip install -e .`) but distribution metadata may be minimal.

8. **Snapshot Volume**: The `data/snapshots/` directory grows continuously (100+ files visible). For long-running deployments, consider periodic archival or cleanup.

9. **GitHub Actions Timezone**: Workflow cron schedules use UTC; IST offsets (UTC+5:30) must be accounted for in the YAML cron expressions.

10. **Trading Recommendations are Informational**: The trading engine produces setups with confidence scores but these are analytical outputs, not order execution. There is no broker integration.
