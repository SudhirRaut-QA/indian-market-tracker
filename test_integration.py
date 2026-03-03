#!/usr/bin/env python3
"""Integration test for PE fix + Bulk/Block deals"""

from tracker.nse_scraper import MarketScraper
from tracker.telegram_bot import format_corporate_msg, format_bulk_deals_msg

def test_integration():
    """Test both PE formatting and bulk/block deals together"""
    print("🚀 Running Integration Test\n")
    
    # Test 1: PE Formatting Fix
    print("=" * 60)
    print("TEST 1: PE Formatting (String PE Values)")
    print("=" * 60)
    test_corporate = {
        "corporate_actions": [
            {
                "symbol": "RELIANCE",
                "subject": "Dividend",
                "purpose": ["Dividends"],
                "ex_date": "15-Mar-2026",
                "record_date": "16-Mar-2026",
                "details": "₹10 per share",
                "attachments": [],
                "ltp": 2500.50,
                "pe": "28.5",  # String PE (NSE format)
                "52w_high": 2800.0,
                "52w_low": 2200.0,
            }
        ],
        "timestamp": "2026-03-01 15:20:00"
    }
    
    try:
        corp_msg = format_corporate_msg(test_corporate)
        print("✅ Corporate actions formatting: PASSED")
        print(f"   Generated {len(corp_msg)} chars")
    except ValueError as e:
        if "Unknown format code" in str(e):
            print(f"❌ PE formatting bug: {e}")
            return False
        raise
    
    # Test 2: Bulk/Block Deals (Empty Data)
    print("\n" + "=" * 60)
    print("TEST 2: Bulk/Block Deals (Empty Data Handling)")
    print("=" * 60)
    test_deals_empty = {
        "bulk_deals": None,  # Test None handling
        "block_deals": [],   # Test empty list
    }
    
    try:
        deals_msg_empty = format_bulk_deals_msg(test_deals_empty)
        print("✅ Empty bulk/block deals: PASSED")
        print(f"   Generated {len(deals_msg_empty)} chars")
        assert "No large deals" in deals_msg_empty
    except Exception as e:
        print(f"❌ Empty data handling failed: {e}")
        return False
    
    # Test 3: Bulk/Block Deals (With Data)
    print("\n" + "=" * 60)
    print("TEST 3: Bulk/Block Deals (With Mock Data)")
    print("=" * 60)
    test_deals_data = {
        "bulk_deals": [
            {
                "symbol": "TCS",
                "client": "ABC Investments",
                "trade_type": "BUY",
                "qty": 100000,
                "price": 3500.0,
                "value_cr": 35.0,
                "date": "01-Mar-2026"
            },
            {
                "symbol": "INFY",
                "client": "XYZ Fund",
                "trade_type": "SELL",
                "qty": 50000,
                "price": 1500.0,
                "value_cr": 7.5,
                "date": "01-Mar-2026"
            }
        ],
        "block_deals": [
            {
                "symbol": "HDFC",
                "client": "PQR Institutional",
                "trade_type": "BUY",
                "qty": 200000,
                "price": 1600.0,
                "value_cr": 32.0,
                "date": "01-Mar-2026"
            }
        ]
    }
    
    try:
        deals_msg_data = format_bulk_deals_msg(test_deals_data)
        print("✅ Bulk/block deals with data: PASSED")
        print(f"   Generated {len(deals_msg_data)} chars")
        assert "Bulk Deals" in deals_msg_data
        assert "Block Deals" in deals_msg_data
        assert "TCS" in deals_msg_data
        assert "HDFC" in deals_msg_data
    except Exception as e:
        print(f"❌ Data formatting failed: {e}")
        return False
    
    # Test 4: Live API Calls
    print("\n" + "=" * 60)
    print("TEST 4: Live API Calls (Market Data)")
    print("=" * 60)
    scraper = MarketScraper()
    
    try:
        bulk = scraper.get_bulk_deals() or []
        block = scraper.get_block_deals() or []
        print(f"✅ Live API calls: PASSED")
        print(f"   Bulk deals: {len(bulk)}")
        print(f"   Block deals: {len(block)}")
        
        # Format live data
        live_snapshot = {
            "bulk_deals": bulk,
            "block_deals": block
        }
        live_msg = format_bulk_deals_msg(live_snapshot)
        print(f"✅ Live data formatting: PASSED")
        print(f"   Generated {len(live_msg)} chars")
        
    except Exception as e:
        print(f"❌ Live API test failed: {e}")
        return False
    
    return True

def main():
    success = test_integration()
    
    print("\n" + "=" * 60)
    if success:
        print("✅✅✅ ALL INTEGRATION TESTS PASSED! ✅✅✅")
        print("=" * 60)
        print("\nBoth fixes are working correctly:")
        print("  1. ✅ PE formatting bug fixed (handles string PE values)")
        print("  2. ✅ Bulk/Block deals feature working (handles None/empty/data)")
        print("\nReady to commit and deploy!")
    else:
        print("❌❌❌ INTEGRATION TESTS FAILED ❌❌❌")
        print("=" * 60)
        exit(1)

if __name__ == "__main__":
    main()
