#!/usr/bin/env python3
"""Test PE formatting bug fix"""

from tracker.nse_scraper import MarketScraper
from tracker.telegram_bot import format_corporate_msg

def test_pe_formatting():
    """Test that PE values (which NSE returns as strings) are formatted correctly"""
    print("🔄 Testing PE formatting fix...")
    
    # Test with mock data that simulates NSE's string PE values
    test_actions = [
        {
            "symbol": "TEST1",
            "subject": "Board Meeting",
            "purpose": ["Dividends"],
            "ex_date": "01-Mar-2026",
            "record_date": "02-Mar-2026",
            "details": "Test dividend",
            "attachments": [],
            "ltp": 100.50,
            "pe": "28.5",  # String PE like NSE returns
            "52w_high": 120.0,
            "52w_low": 80.0,
        },
        {
            "symbol": "TEST2",
            "subject": "AGM",
            "purpose": ["Annual General Meeting"],
            "ex_date": "05-Mar-2026",
            "record_date": "06-Mar-2026",
            "details": "Annual meeting",
            "attachments": [],
            "ltp": 250.75,
            "pe": "15.2",  # String PE
            "52w_high": 300.0,
            "52w_low": 200.0,
        },
        {
            "symbol": "TEST3",
            "subject": "Split",
            "purpose": ["Stock Split"],
            "ex_date": "10-Mar-2026",
            "record_date": "11-Mar-2026",
            "details": "2:1 split",
            "attachments": [],
            "ltp": 500.0,
            "pe": None,  # No PE (some stocks don't have PE)
            "52w_high": 550.0,
            "52w_low": 400.0,
        }
    ]
    
    snapshot = {
        "corporate_actions": test_actions,
        "timestamp": "2026-03-01 15:15:00"
    }
    
    try:
        message = format_corporate_msg(snapshot)
        print("✅ PE formatting successful!")
        print(f"✅ Message generated ({len(message)} chars)")
        print("\n" + "="*60)
        print(message[:800])  # First 800 chars
        print("="*60)
        return True
    except ValueError as e:
        if "Unknown format code 'f'" in str(e):
            print(f"❌ PE formatting bug still exists: {e}")
            return False
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    print("🚀 Testing PE Formatting Bug Fix\n")
    
    success = test_pe_formatting()
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Tests failed!")
        exit(1)

if __name__ == "__main__":
    main()
