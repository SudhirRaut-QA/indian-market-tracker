# Dividend Tracker Workflow (Single Excel Output)

## Goal
Maintain one canonical Excel file only:
- `data/excel/upcoming_dividends_latest.xlsx`

## Requirements
- Windows with PowerShell
- Python 3.10+ (project currently uses `.venv`)
- Python packages installed from `requirements.txt`
- Internet access (for NSE/Screener/Moneycontrol fetches)

## Mandatory Files
Do not delete these files:
- `data/excel/rebuild_upcoming_dividends.py`
- `data/excel/open_live_dividends.bat`
- `data/excel/upcoming_dividends_seed.csv`
- `data/excel/upcoming_dividends_latest.csv`
- `data/excel/upcoming_dividends_latest.xlsx`

## Optional Support Files
- `data/excel/refresh_dividend_metrics.py`
- `data/excel/enable_excel_auto_refresh.ps1`

## One-Click Run (Recommended)
Run:
- `data/excel/open_live_dividends.bat`

What it does:
1. Rebuilds latest dividend data
2. Writes `upcoming_dividends_latest.csv`
3. Writes `upcoming_dividends_latest.xlsx`
4. Opens the latest Excel file

## Manual Run
From repo root:

```powershell
& ".venv/Scripts/python.exe" "data/excel/rebuild_upcoming_dividends.py"
```

## Snapshot Mode (Only if explicitly needed)
By default, the script keeps only latest files. To also create dated snapshots:

```powershell
& ".venv/Scripts/python.exe" "data/excel/rebuild_upcoming_dividends.py" --keep-dated-snapshot
```

## Reliability Rules Enforced
- Keeps only upcoming ex-dates within configured horizon
- Keeps only rows with numeric `Dividend_Rs > 0`
- Keeps only rows with numeric `LTP_INR > 0`
- Excludes known trust/distribution symbols (except explicit allowlist)

## Canonical Output Policy
Always use this file for analysis/trading review:
- `data/excel/upcoming_dividends_latest.xlsx`

If old dated files appear again, remove them unless snapshot mode was intentionally used.
