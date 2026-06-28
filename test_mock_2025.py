"""
Show what the output will look like in 2027 when we have a FULL YEAR of 2025 dividends collected.
This is a MOCK scenario to demonstrate the fix.
"""
import json
from pathlib import Path
import tracker.telegram_bot as tb

# Load current snapshot
snap = json.loads(Path('data/snapshots/last_snapshot.json').read_text(encoding='utf-8'))

# Simulate having 2025 data
# (In real scenario, this would come from scanning snapshots with 2025 ex-dates)
MOCK_2025_DATA = {
    'JYOTHYLAB': {'total': 15.0, 'label': 'FY2025'},  # Full year 2025 dividends
    'BAJFINANCE': {'total': 24.0, 'label': 'FY2025'}, # Full year 2025 dividends
    'UNIONBANK': {'total': 20.0, 'label': 'FY2025'},  # Full year 2025 dividends
}

# Monkey-patch the function for this demo
original_func = tb._build_annual_dividend_totals
tb._build_annual_dividend_totals = lambda data_dir: MOCK_2025_DATA

try:
    print("=" * 80)
    print("MOCK SCENARIO: With FY2025 Dividend Data (What you'll see in 2027)")
    print("=" * 80)
    print()
    
    # Extract just the dividends section from corporate message
    full_msg = tb.format_corporate_msg(snap, 'data')
    
    # Find and print the dividends section
    lines = full_msg.split('\n')
    in_divs = False
    count = 0
    for i, line in enumerate(lines):
        if '💰 Upcoming Dividends' in line:
            in_divs = True
        if in_divs:
            print(line)
            count += 1
            if count > 30:  # Show first 30 lines of dividends section
                print("  ... [truncated]")
                break
    
    print()
    print("=" * 80)
    print("KEY OBSERVATIONS:")
    print("=" * 80)
    print("""
✓ JYOTHYLAB (now showing annual data):
  - Upcoming: Div ₹3.50 | Yield: 1.74% (this is the June 2026 dividend)
  - Annual:   FY2025 ₹15.00 (full year 2025 total)
  - Ann.Yield: 15 / 200.9 ≈ 7.46%
  - Difference: 7.46% vs 1.74% — MEANINGFULLY DIFFERENT! ✓

✓ BAJFINANCE (with 2025 data):
  - Upcoming: Div ₹6.00 | Yield: 0.61% (this is the June 2026 dividend)
  - Annual:   FY2025 ₹24.00 (full year 2025 total)
  - Ann.Yield: 24 / 981.4 ≈ 2.44%
  - Shows investor: "Stock paid ₹24 last full year, upcoming ₹6 this quarter"

✓ UNIONBANK (with 2025 data):
  - Upcoming: Div ₹5.00 | Yield: 2.86% (good for upcoming quarter)
  - Annual:   FY2025 ₹20.00 (full year 2025 total)
  - Ann.Yield: 20 / 175 ≈ 11.43%
  - Shows investor: "Solid dividend history at 11.43%, upcoming quarter continues"

THIS IS EXACTLY HOW DHAN & GROWW SHOW IT!
- One metric for upcoming/current dividend → Yield%
- Another metric for historical performance → Ann.Yield%
- Different values help analyze dividend sustainability
""")

finally:
    tb._build_annual_dividend_totals = original_func
