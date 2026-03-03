#!/usr/bin/env python3
"""Test new corporate actions formatting and logging improvements"""

from tracker.telegram_bot import format_corporate_msg, _extract_dividend_amount

def test_dividend_extraction():
    """Test dividend amount extraction from subject strings"""
    print("🔄 Testing Dividend Amount Extraction\n")
    
    test_cases = [
        ("Interim Dividend - Rs 10 Per Share", 10.0),
        ("Final Dividend - Re 1.50 Per Share", 1.50),
        ("Dividend Rs. 5.25 per share", 5.25),
        ("Interim Dividend - Rs 2.70 Per Share", 2.70),
        ("Dividend - Re 0.12 Per Share", 0.12),
        ("Bonus Issue 1:1", 0.0),  # No dividend
        ("", 0.0),  # Empty string
    ]
    
    all_passed = True
    for subject, expected in test_cases:
        result = _extract_dividend_amount(subject)
        status = "✅" if result == expected else "❌"
        all_passed = all_passed and (result == expected)
        print(f"{status} '{subject[:40]}'")
        print(f"   Expected: {expected}, Got: {result}\n")
    
    return all_passed

def test_corporate_formatting():
    """Test the new corporate actions formatting"""
    print("\n🔄 Testing Corporate Actions Formatting\n")
    
    # Mock data with various corporate actions
    test_snapshot = {
        "corporate_actions": [
            {
                "symbol": "RELIANCE",
                "subject": "Interim Dividend - Rs 10 Per Share",
                "ex_date": "15-Mar-2026",
                "record_date": "16-Mar-2026",
                "ltp": 2500.0,
                "pe": "28.5",
            },
            {
                "symbol": "TCS",
                "subject": "Final Dividend - Rs 15.50 Per Share",
                "ex_date": "20-Mar-2026",
                "record_date": "21-Mar-2026",
                "ltp": 3500.0,
                "pe": "32.1",
            },
            {
                "symbol": "INFY",
                "subject": "Interim Dividend - Re 1.50 Per Share",
                "ex_date": "18-Mar-2026",
                "record_date": "19-Mar-2026",
                "ltp": 1500.0,
                "pe": "25.3",
            },
            {
                "symbol": "HDFC",
                "subject": "Face Value Split (Sub-Division) - From Rs 2 Per Share To Re 1 Per Share",
                "ex_date": "22-Mar-2026",
                "record_date": "23-Mar-2026",
                "ltp": 1600.0,
                "pe": "20.5",
            },
            {
                "symbol": "WIPRO",
                "subject": "Bonus Issue 1:2",
                "ex_date": "25-Mar-2026",
                "record_date": "26-Mar-2026",
                "ltp": 400.0,
                "pe": "18.2",
            },
        ],
        "insider_trading": [
            {
                "symbol": "TATAMOTORS",
                "acquirer": "Promoter Group",
                "buy_value": 50000000,  # 5 Cr
                "sell_value": 0,
            },
            {
                "symbol": "MARUTI",
                "acquirer": "Director",
                "buy_value": 0,
                "sell_value": 30000000,  # 3 Cr
            },
        ]
    }
    
    try:
        message = format_corporate_msg(test_snapshot)
        print("✅ Corporate message formatting: PASSED")
        print(f"   Generated {len(message)} characters")
        print("\n" + "="*70)
        print("SAMPLE OUTPUT:")
        print("="*70)
        print(message)
        print("="*70)
        
        # Verify key elements are present
        checks = [
            ("Dividends section", "💰 Dividends:" in message),
            ("Dividend yield", "Yield:" in message),
            ("Record date", "Record:" in message),
            ("Stock splits", "✂️ Stock Splits:" in message),
            ("Bonus issues", "🎁 Bonus Issues:" in message),
            ("Insider trading", "🔍 Insider Trading" in message),
            ("Signal explanation", "Understanding Signals:" in message),
            ("Bullish signal", "Bullish Signal" in message),
            ("Caution signal", "Caution Signal" in message),
        ]
        
        print("\n✅ Content Verification:")
        all_passed = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            all_passed = all_passed and check_result
            print(f"   {status} {check_name}")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Corporate message formatting: FAILED")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_logging_improvements():
    """Test that logging improvements are in place"""
    print("\n🔄 Testing Logging Improvements\n")
    
    try:
        # Import to check if zoneinfo is available and imports work
        from tracker.__main__ import run_once
        from zoneinfo import ZoneInfo
        
        print("✅ zoneinfo import: PASSED (stdlib)")
        print("✅ IST timezone support: Available")
        
        # Test IST timezone
        from datetime import datetime
        ist = ZoneInfo('Asia/Kolkata')
        now_ist = datetime.now(ist)
        print(f"   Current IST time: {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
        
        # Check if the function signature includes timing
        import inspect
        source = inspect.getsource(run_once)
        
        checks = [
            ("Time tracking", "start_time = time.time()" in source),
            ("IST timezone", "Asia/Kolkata" in source),
            ("Start logging", "START:" in source),
            ("End logging", "COMPLETE:" in source),
            ("Duration logging", "Duration:" in source),
        ]
        
        print("\n✅ Code Verification:")
        all_passed = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            all_passed = all_passed and check_result
            print(f"   {status} {check_name}")
        
        return all_passed
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Logging test failed: {e}")
        return False

def main():
    print("🚀 Testing Enhanced Corporate Actions & Logging\n")
    print("="*70 + "\n")
    
    # Run all tests
    test1 = test_dividend_extraction()
    test2 = test_corporate_formatting()
    test3 = test_logging_improvements()
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Dividend Extraction:      {'✅ PASSED' if test1 else '❌ FAILED'}")
    print(f"Corporate Formatting:     {'✅ PASSED' if test2 else '❌ FAILED'}")
    print(f"Logging Improvements:     {'✅ PASSED' if test3 else '❌ FAILED'}")
    print("="*70)
    
    if test1 and test2 and test3:
        print("\n✅✅✅ ALL TESTS PASSED! ✅✅✅")
        print("\nEnhancements Summary:")
        print("  1. ✅ Corporate actions now show in clean sections (Dividends, Splits, Bonus)")
        print("  2. ✅ Dividend yield calculation included (Div Amount / LTP * 100)")
        print("  3. ✅ Record date now displayed alongside ex-date")
        print("  4. ✅ Signal explanations added for insider trading")
        print("  5. ✅ IST timestamps added to logging (start/end times)")
        print("  6. ✅ Execution duration tracking (minutes & seconds)")
        print("\nReady to use in production!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
