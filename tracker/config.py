"""
Configuration for Indian Market Tracker
=========================================
"""

import os
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
# Pre-market + Market hours + Post-market
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
COMMODITY_ETFS = [
    "TATAGOLD",     # Tata Gold Exchange Traded Fund
    "TATSILV",      # Tata Silver Exchange Traded Fund  
    "GOLDBEES",     # Nippon India Gold ETF (backup/liquidity check)
    "LIQUIDBEES",   # Nippon India Liquid ETF (money market indicator)
]

# =============================================================================
# SIGNAL DETECTOR THRESHOLDS
# =============================================================================
NEAR_52W_HIGH_PCT = 2.0   # Within 2% of 52-week high → breakout zone
NEAR_52W_LOW_PCT = 5.0    # Within 5% of 52-week low → value zone
HIGH_DELIVERY_PCT = 60.0  # Delivery % above this = genuine accumulation
LOW_DELIVERY_PCT = 25.0   # Delivery % below this = speculative

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
# DATA STORAGE
# =============================================================================
DATA_DIR = PROJECT_ROOT / "data"
EXCEL_DIR = DATA_DIR / "excel"
EXCEL_FILE = EXCEL_DIR / "market_tracker.xlsx"
DRIVE_EXCEL_NAME = "market_tracker.xlsx"  # Permanent name for Google Drive
SNAPSHOT_DIR = DATA_DIR / "snapshots"   # JSON snapshots for delta comparison
# Note: DeltaEngine saves last_snapshot.json inside SNAPSHOT_DIR

# =============================================================================
# LOGGING
# =============================================================================
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "tracker.log"
