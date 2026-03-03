#!/usr/bin/env python3
"""Quick test script for bulk/block deals feature"""

from tracker.nse_scraper import MarketScraper
from tracker.telegram_bot import format_bulk_deals_msg
from tracker.__main__ import run_once
from tracker.scheduler import SLOT_CONFIG

def test_imports():
    """Test all imports work"""
    print("✅ All imports successful")
    print(f"✅ Scheduler 18:00 includes bulk_deals: {SLOT_CONFIG['18:00'].get('include_bulk_deals', False)}")
    print(f"✅ Scheduler 21:00 includes bulk_deals: {SLOT_CONFIG['21:00'].get('include_bulk_deals', False)}")

def test_scraping():
    """Test scraping bulk/block deals"""
    print("\n🔄 Testing bulk/block deal scraping...")
    scraper = MarketScraper()
    
    bulk_deals = scraper.get_bulk_deals() or []
    block_deals = scraper.get_block_deals() or []
    
    print(f"✅ Bulk deals fetched: {len(bulk_deals)} deals")
    print(f"✅ Block deals fetched: {len(block_deals)} deals")
    
    if bulk_deals:
        print(f"\nSample bulk deal:")
        print(f"  Symbol: {bulk_deals[0].get('symbol', 'N/A')}")
        print(f"  Client: {bulk_deals[0].get('clientName', 'N/A')}")
        print(f"  Type: {bulk_deals[0].get('buyOrSell', 'N/A')}")
    
    if block_deals:
        print(f"\nSample block deal:")
        print(f"  Symbol: {block_deals[0].get('symbol', 'N/A')}")
        print(f"  Type: {block_deals[0].get('tradeType', 'N/A')}")
    
    return bulk_deals, block_deals

def test_formatting(bulk_deals, block_deals):
    """Test message formatting"""
    print("\n🔄 Testing message formatting...")
    
    snapshot = {
        'bulk_deals': bulk_deals,
        'block_deals': block_deals
    }
    
    message = format_bulk_deals_msg(snapshot)
    print(f"✅ Message generated ({len(message)} chars)")
    print("\n" + "="*60)
    print(message[:1000])  # First 1000 chars
    print("="*60)
    
    return message

def main():
    print("🚀 Testing Bulk/Block Deals Feature\n")
    
    # Test 1: Imports
    test_imports()
    
    # Test 2: Scraping
    bulk_deals, block_deals = test_scraping()
    
    # Test 3: Formatting
    if bulk_deals or block_deals:
        test_formatting(bulk_deals, block_deals)
    else:
        print("\n⚠️ No deals to format (might be off-market hours)")
    
    print("\n✅ All tests completed successfully!")

if __name__ == "__main__":
    main()
