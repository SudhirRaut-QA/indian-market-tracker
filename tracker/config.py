"""
Configuration for Indian Market Tracker v3.0
==============================================
"""

import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

# =============================================================================
# TELEGRAM
# =============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =============================================================================
# SCHEDULE (IST, 24h format)
# =============================================================================
NOTIFICATION_TIMES = [
    "09:00",   # Pre-open session starts
    "09:08",   # Pre-open orders matched
    "09:15",   # Market opens — first tick
    "09:30",   # Settled after opening volatility
    "11:00",   # Mid-morning check
    "15:35",   # Post-closing snapshot
    "18:00",   # Provisional FII/DII
    "21:00",   # Final FII/DII + corporate actions
]

MARKET_DAYS = [0, 1, 2, 3, 4]  # Mon-Fri

# =============================================================================
# SECTORS TO TRACK (stock-level data)
# =============================================================================
SECTORS = {
    "NIFTY 50": "NIFTY%2050",
    "NIFTY BANK": "NIFTY%20BANK",
    "NIFTY IT": "NIFTY%20IT",
    "NIFTY AUTO": "NIFTY%20AUTO",
    "NIFTY PHARMA": "NIFTY%20PHARMA",
    "NIFTY METAL": "NIFTY%20METAL",
    "NIFTY ENERGY": "NIFTY%20ENERGY",
    "NIFTY FMCG": "NIFTY%20FMCG",
    "NIFTY REALTY": "NIFTY%20REALTY",
    "NIFTY FINANCIAL SERVICES": "NIFTY%20FINANCIAL%20SERVICES",
    "NIFTY PSU BANK": "NIFTY%20PSU%20BANK",
    "NIFTY INDIA DEFENCE": "NIFTY%20INDIA%20DEFENCE",
    "NIFTY OIL & GAS": "NIFTY%20OIL%20%26%20GAS",
    "NIFTY COMMODITIES": "NIFTY%20COMMODITIES",
    "NIFTY MIDCAP 50": "NIFTY%20MIDCAP%2050",
    "NIFTY SMALLCAP 50": "NIFTY%20SMALLCAP%2050",
}

# Key Indices to track (from allIndices API)
KEY_INDICES = [
    "NIFTY 50", "NIFTY BANK", "NIFTY NEXT 50", "NIFTY IT",
    "NIFTY FINANCIAL SERVICES", "NIFTY AUTO", "NIFTY PHARMA",
    "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY", "NIFTY FMCG",
    "NIFTY PSU BANK", "NIFTY INDIA DEFENCE",
    "NIFTY OIL & GAS", "NIFTY COMMODITIES",
    "NIFTY MIDCAP 50", "NIFTY SMALLCAP 50",
    "NIFTY200 MOMENTUM 30", "NIFTY HIGH BETA 50",
    "NIFTY100 LOW VOLATILITY 30",
    "INDIA VIX",
]

# Commodity ETF proxies
COMMODITY_ETFS = ["GOLDBEES", "SILVERBEES"]

# =============================================================================
# NSE
# =============================================================================
NSE_BASE_URL = "https://www.nseindia.com"
NSE_MAX_RETRIES = 3
NSE_RETRY_DELAY = 5

# =============================================================================
# EXTERNAL APIs
# =============================================================================
FOREX_API_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"

# =============================================================================
# ALERT THRESHOLDS
# =============================================================================
NEAR_52W_HIGH_PCT = 2.0    # Within 2% of 52-week high → breakout candidate
NEAR_52W_LOW_PCT = 2.0     # Within 2% of 52-week low → value pick
VOLUME_SPIKE_MULTIPLIER = 3 # 3x average → unusual volume
HIGH_DELIVERY_PCT = 60      # Above 60% → genuine buying
LOW_DELIVERY_PCT = 30       # Below 30% → speculative
BLOCK_DEAL_MIN_CR = 10      # Minimum ₹10 Cr for block deal alert

# =============================================================================
# DATA STORAGE STRATEGY
# =============================================================================
# Root data directory
DATA_DIR = PROJECT_ROOT / "data"

# JSON snapshots: data/snapshots/YYYY/MM/DD/snapshot_HHMMSS.json
SNAPSHOT_DIR = DATA_DIR / "snapshots"

# Monthly Excel workbooks: data/excel/market_tracker_YYYY_MM.xlsx
EXCEL_DIR = DATA_DIR / "excel"

# Legacy single Excel (for backward compat)
EXCEL_FILE = DATA_DIR / "market_tracker.xlsx"

# Daily summary JSONs: data/daily/YYYY-MM-DD.json
DAILY_DIR = DATA_DIR / "daily"

# Backup archives: data/backup/backup_YYYY_MM_DD.zip
BACKUP_DIR = DATA_DIR / "backup"

# Delta comparison file
DELTA_FILE = DATA_DIR / "last_snapshot.json"

def get_monthly_excel_path() -> Path:
    """Get single master Excel workbook path (appends all data)."""
    # Single continuous file - all data in one place
    return EXCEL_DIR / "market_tracker_master.xlsx"

def get_snapshot_dir() -> Path:
    """Get today's snapshot directory."""
    now = datetime.now()
    p = SNAPSHOT_DIR / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_daily_summary_path() -> Path:
    """Get today's daily summary path."""
    now = datetime.now()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    return DAILY_DIR / f"{now.strftime('%Y-%m-%d')}.json"

# =============================================================================
# LOGGING
# =============================================================================
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "tracker.log"
