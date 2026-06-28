"""Show how the Telegram message will render with the fix."""
import json
from pathlib import Path
import tracker.telegram_bot as tb

# Load latest snapshot
snap = json.loads(Path('data/snapshots/last_snapshot.json').read_text(encoding='utf-8'))

# Format corporate message
msg1 = tb.format_corporate_msg(snap, 'data')
print("=" * 70)
print("TELEGRAM MESSAGE 1: Corporate Actions Summary")
print("=" * 70)
print(msg1)
print()
print()

# Format dividends table
msg2 = tb.format_corporate_dividends_table_msg(snap)
print("=" * 70)
print("TELEGRAM MESSAGE 2: All Dividends Table")
print("=" * 70)
print(msg2)
print()
print()

# Explanation
print("=" * 70)
print("WHAT CHANGED:")
print("=" * 70)
print("""
✓ BEFORE (BUG):
  - Yield: ₹3.50 / ₹200.9 = 1.74% ✓ Correct
  - Ann.Yield: ₹3.50 / ₹200.9 = 1.74% ✗ WRONG (same as Yield!)
  
✓ AFTER (FIXED):
  - Yield: ₹3.50 / ₹200.9 = 1.74% ✓ Upcoming dividend % (correct)
  - Ann.Yield: [NOT SHOWN] ✓ Correct (no prior year data exists yet)
  
WHY THE CHANGE:
- Ann.Yield should ONLY use FY2025 (prior complete year)
- Never mixes in current 2026 data
- Once we reach 2027, Ann.Yield will show full FY2025 total (e.g., ₹15)
- Then Ann.Yield% = ₹15 / ₹200.9 ≈ 7.46% — meaningfully different from 1.74%!

This matches how Dhan & Groww show these separately!
""")
