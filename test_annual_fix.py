"""Test that annual totals now return ONLY prior year, not current year fallback."""
import tracker.telegram_bot as tb
import json

# Check that _build_annual_dividend_totals NOW ONLY returns FY2025 (empty in 2026)
annual_totals = tb._build_annual_dividend_totals('data')
print(f'Annual totals returned: {len(annual_totals)} symbols')
if annual_totals:
    sample = list(annual_totals.items())[0]
    print(f'Sample: {sample}')
    print("   ^^ This is WRONG — should be empty since we started tracker in 2026")
else:
    print('✓ Empty (correct! — we have no 2025 snapshot data yet)')
print()

# Load a snapshot with dividends
snap = json.loads(open('data/snapshots/last_snapshot.json', encoding='utf-8').read())

# Check a specific dividend entry
divs = [a for a in snap.get('corporate_actions', []) if 'dividend' in a.get('subject', '').lower()]
if divs:
    d = divs[0]
    print('Example dividend record:')
    print(f'  Symbol: {d.get("symbol")}')
    print(f'  Subject: {d.get("subject")}')
    print(f'  Ex-Date: {d.get("ex_date")}')
    ltp = d.get('ltp')
    print(f'  LTP: {ltp}')
    
    # Extract dividend amount
    div_amt = tb._extract_dividend_amount(d.get('subject', ''))
    ltp_val = float(ltp or 0)
    if ltp_val > 0 and div_amt > 0:
        yield_pct = round(div_amt / ltp_val * 100, 2)
        print(f'  → Yield% = {div_amt} / {ltp_val} = {yield_pct}%')
        print(f'  → Ann.Yield% = would use FY2025 data = N/A (no 2025 data)')
        print()
        print('MEANING: Yield shows upcoming dividend pct, Ann.Yield is hidden until we have prior year data')
