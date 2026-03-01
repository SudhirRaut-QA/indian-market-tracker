# Excel Data Storage - How It Works

## 📊 Single Master File Approach

All your market data is stored in **ONE continuous Excel file**: `market_tracker_master.xlsx`

### File Location
```
data/excel/market_tracker_master.xlsx
```

### How Data is Appended

Each time the tracker runs:

1. **Dashboard Sheet**: Overwrites with latest snapshot (current view)
2. **All Other Sheets**: Appends new rows (historical data)

This means:
- ✅ All historical data in ONE place
- ✅ No need to jump between monthly files
- ✅ Easy to analyze trends over time
- ✅ Single file to download/share

---

## 📈 Sheet Structure

### Dashboard (Latest Snapshot Only)
- Shows current market state
- Overwrites each run
- Use for quick glance

### Historical Sheets (Continuous Append)

#### FII_DII Sheet
```
| Log Date   | Slot      | Timestamp       | FII Net | DII Net | ...
|------------|-----------|-----------------|---------|---------|
| 2026-03-01 | 09:00 AM  | 2026-03-01 9:00 | +1234   | -567    | ...
| 2026-03-01 | 09:30 AM  | 2026-03-01 9:30 | +2345   | -678    | ...
| 2026-03-01 | 11:00 AM  | 2026-03-01 11:00| +3456   | -789    | ...
| 2026-03-01 | 03:35 PM  | 2026-03-01 15:35| +4567   | -890    | ...
```

Each run adds a new row with that time's data.

#### Indices Sheet
```
| Log Date   | Slot      | Index      | Last    | Change | % Change | ...
|------------|-----------|------------|---------|--------|----------|
| 2026-03-01 | 09:00 AM  | NIFTY 50   | 22456.7 | +123.4 | +0.55%   | ...
| 2026-03-01 | 09:30 AM  | NIFTY 50   | 22478.2 | +144.9 | +0.65%   | ...
```

#### Sectors Sheet
```
| Log Date   | Slot      | Sector     | Change% | Gainers | Losers | ...
|------------|-----------|------------|---------|---------|--------|
| 2026-03-01 | 09:00 AM  | IT         | +1.23%  | 25      | 8      | ...
| 2026-03-01 | 09:30 AM  | IT         | +1.45%  | 28      | 5      | ...
```

All other sheets (Commodities, Forex, Options, Corporate, etc.) work the same way.

---

## 🎯 Benefits

### For Analysis
- **Trend Analysis**: See FII/DII flow patterns over weeks/months
- **Index Comparison**: Compare morning vs evening performance
- **Sector Rotation**: Track which sectors are gaining/losing
- **Historical Reference**: Look back at any date/time

### For Sharing
- **Single File**: Just share `market_tracker_master.xlsx`
- **Complete History**: All data included
- **Google Drive**: Automatically updated in Drive after each run

### For Storage
- **Organized**: One file, multiple sheets
- **Filterable**: Use Excel filters on any column
- **Sortable**: Sort by date, slot, sector, etc.
- **Searchable**: Find specific dates/stocks easily

---

## 📁 File Size Management

### Expected Growth
- **Per Run**: ~50-100 KB of new data
- **Daily (8 runs)**: ~400-800 KB
- **Monthly**: ~12-24 MB
- **Yearly**: ~150-300 MB

### Tips for Large Files
1. **Use Filters**: Filter by date range to view specific periods
2. **Pivot Tables**: Create summaries without loading all rows
3. **Yearly Archives**: After 1 year, archive and start fresh
4. **Power Query**: For advanced analysis of large datasets

---

## 🔄 Data Update Logic

The tracker uses "upsert" logic (update or insert):

### Unique Keys
- **FII_DII, Indices, Sectors**: `(Date, Slot)`
- **Corporate Actions**: `(Symbol, Ex-Date, Type)`
- **Insider Trading**: `(Symbol, Person, Date)`

### Behavior
- If key exists → **Update** that row
- If key doesn't exist → **Append** new row

This prevents duplicate entries for the same time slot.

---

## 📊 Example Timeline

**Day 1 - Morning Run (9:00 AM)**
- File created: `market_tracker_master.xlsx`
- FII_DII sheet: 1 row added
- Indices sheet: 21 rows added (one per index)
- Sectors sheet: 16 rows added (one per sector)

**Day 1 - Next Run (9:30 AM)**
- Same file opened
- FII_DII sheet: 2nd row added (now 2 total)
- Indices sheet: 21 more rows (now 42 total)
- Sectors sheet: 16 more rows (now 32 total)

**Day 1 - End of Day (8 runs total)**
- FII_DII: 8 rows (one per slot)
- Indices: 168 rows (8 × 21 indices)
- Sectors: 128 rows (8 × 16 sectors)

**After 1 Month (30 days × 8 runs = 240 runs)**
- FII_DII: 240 rows
- Indices: 5,040 rows
- Sectors: 3,840 rows
- **Still one file!**

---

## 🚀 Google Drive Integration

With Google Drive enabled:

1. Each run uploads `market_tracker_master.xlsx`
2. Drive replaces the old version (keeps history)
3. You always have the latest data in Drive
4. Can access from anywhere (phone, tablet, laptop)
5. Can share Drive folder with others

---

## 🛠️ How to Use

### View Today's Summary
- Open `market_tracker_master.xlsx`
- Go to **Dashboard** sheet
- See latest snapshot

### Analyze Historical Data
- Open `market_tracker_master.xlsx`
- Go to any data sheet (FII_DII, Indices, etc.)
- Use Excel filters to select date range
- Create charts/pivot tables

### Compare Time Periods
```excel
Filter by:
- Date: 2026-03-01 to 2026-03-07
- Slot: "09:00 AM" and "03:35 PM"
- Analyze: Morning vs Evening patterns
```

### Track Specific Stock
```excel
In Stocks sheet:
- Filter Symbol column: "RELIANCE"
- See all historical data for that stock
- Create price chart
```

---

## ❓ FAQ

**Q: Won't the file get too large?**  
A: After 1 year, it will be ~300 MB. Excel can handle up to 1 million rows per sheet, so you're fine for years.

**Q: Can I archive old data?**  
A: Yes! After 1 year, rename the file to `market_tracker_2026.xlsx` and let it create a fresh `market_tracker_master.xlsx`.

**Q: What if I want to start fresh?**  
A: Just delete `market_tracker_master.xlsx`. Next run will create a new one.

**Q: Can I have monthly files AND master file?**  
A: The code now only creates master file. Old monthly files won't be created anymore.

**Q: How do I open large Excel files faster?**  
A: Use Power Query or Python/Pandas to analyze. Or filter to specific date ranges.

---

## ✅ Summary

- **ONE file** for all data: `market_tracker_master.xlsx`
- **Continuous append**: Each run adds rows, never deletes
- **Historical analysis**: All past data in one place
- **Easy sharing**: Single file to share/upload
- **Google Drive**: Auto-synced after each run
- **No manual work**: Everything appends automatically

Your data is now in one place, always growing, never scattered! 🎉
