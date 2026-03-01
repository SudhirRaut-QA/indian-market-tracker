"""
Test Script for Indian Market Tracker
======================================

Run this script during market hours (Mon-Fri 9:15 AM - 3:30 PM IST) to test all features.

Usage:
    python test_tracker.py
"""

import subprocess
import sys
from datetime import datetime

def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Command: {cmd}")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=False,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print(f"\n✅ {description} - SUCCESS")
            return True
        else:
            print(f"\n❌ {description} - FAILED (exit code {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"\n⏱️ {description} - TIMEOUT (exceeded 120s)")
        return False
    except KeyboardInterrupt:
        print(f"\n⚠️ {description} - INTERRUPTED by user")
        return False
    except Exception as e:
        print(f"\n❌ {description} - ERROR: {e}")
        return False

def main():
    print(f"""
╔════════════════════════════════════════════════════════════╗
║   Indian Market Tracker v3.0 - Local Test Suite           ║
╚════════════════════════════════════════════════════════════╝

Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}

This will test all major features. Each test will:
- Fetch real market data from NSE
- Generate signals
- Send to Telegram
- Save to Excel and JSON

Press Ctrl+C at any time to skip a test.
""")
    
    input("Press Enter to start tests...")
    
    tests = [
        {
            "cmd": "python -m tracker --setup",
            "desc": "1. Setup Verification"
        },
        {
            "cmd": "python -m tracker --now --no-telegram --no-excel",
            "desc": "2. Quick Fetch (FII/DII + Indices only, no output)"
        },
        {
            "cmd": "python -m tracker --now",
            "desc": "3. Basic Run (with Telegram, with Excel)"
        },
        {
            "cmd": "python -m tracker --now --full",
            "desc": "4. Full Run (sectors, signals, options, commodities)"
        },
        {
            "cmd": "python -m tracker --now --corporate",
            "desc": "5. Corporate Actions + Insider Trading"
        },
    ]
    
    results = []
    
    for test in tests:
        success = run_command(test["cmd"], test["desc"])
        results.append((test["desc"], success))
    
    # Summary
    print(f"\n\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for desc, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {desc}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Ready to push to GitHub.")
    else:
        print("\n⚠️ Some tests failed. Review errors above.")
    
    print("\nNext Steps:")
    print("1. Check your Telegram for messages")
    print("2. Check data/excel/ for Excel files")
    print("3. Check data/snapshots/ for JSON files")
    print("4. If all looks good, proceed to GitHub push")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test suite interrupted by user. Exiting...")
        sys.exit(1)
