# Indian Market Tracker - Enhancement Roadmap

## 🎯 Phase 1: Data Depth Enhancements (Easy Wins)

### 1. **52-Week High/Low Proximity Alerts** ⭐⭐⭐
**Why**: Stocks near 52W high = breakout candidates, near 52W low = value picks
**Implementation**: Already have `nearWKH`, `nearWKL` fields in sector data
```python
# In telegram_bot.py - add to sector message
for stock in sector_stocks:
    if stock['near_52h'] and stock['near_52h'] < 2:  # Within 2% of 52W high
        alerts.append(f"🚀 {stock['symbol']} near 52-week HIGH!")
    if stock['near_52l'] and stock['near_52l'] < 2:  # Near 52W low
        alerts.append(f"💎 {stock['symbol']} near 52-week LOW (value pick?)")
```

### 2. **Unusual Volume Detection** ⭐⭐⭐
**Why**: High volume = institutional activity or news event
**Implementation**: Compare today's volume vs 30-day average
```python
# Add to nse_scraper.py get_sector_stocks()
# NSE already provides these fields, we just need to use them:
avg_vol = stock.get('totalTradedVolume') / 30  # Simplified
if today_vol > avg_vol * 3:
    flag_as_unusual_volume()
```

### 3. **Delivery vs Intraday Percentage** ⭐⭐
**Why**: High delivery % = genuine buying (not speculation)
**Available at**: `/api/quote-equity?symbol=<SYMBOL>` → `deliveryToTradedQuantity`
```python
# Add to stock detail fetch
delivery_pct = response['deliveryToTradedQuantity']
if delivery_pct > 70:
    signal = "Strong hands buying (long-term investors)"
elif delivery_pct < 30:
    signal = "Intraday traders (speculation)"
```

### 4. **Sector Rotation Tracker** ⭐⭐⭐
**Why**: Shows where smart money is moving
**Implementation**: Track sector performance over 1W, 1M, 3M
```python
# In delta_engine.py - add weekly/monthly snapshots
# Compare: Which sector was worst last week, best this week = rotation signal
if prev_week_worst_sector == curr_week_best_sector:
    alert("🔄 Sector Rotation: Money moving into {sector}!")
```

---

## 🎯 Phase 2: Advanced Institutional Tracking

### 5. **Block Deals** ⭐⭐⭐
**Endpoint**: `/api/block-deal` (verified working in old research)
**Why**: Large institutional buys/sells (₹10Cr+ transactions)
```python
def get_block_deals():
    # Returns: symbol, client, qty, price, value
    # Flag if same stock has multiple block buys = accumulation
```

### 6. **Bulk Deals** ⭐⭐⭐
**Endpoint**: `/api/bulk-deal-data`
**Why**: 0.5%+ stake changes (operators, large investors)

### 7. **FII/DII Stock-Level Proxy** ⭐⭐
**Logic**: Combine high volume + price up + delivery % high = likely FII/DII buying
```python
def detect_institutional_buying(stock):
    if (stock['volume'] > avg * 3 and 
        stock['pct'] > 3 and 
        stock['delivery_pct'] > 60):
        return "🐋 Possible institutional buying"
```

---

## 🎯 Phase 3: Options Intelligence

### 8. **FII DII Option Activity** ⭐⭐⭐
**Endpoint**: `/api/fo-participant-oi-data` (futures/options participant-wise OI)
**Why**: Track FII/DII activity in F&O (derivatives = directional bets)

### 9. **Option Chain Heatmap** ⭐⭐
**Implementation**: Visualize CE/PE OI at each strike
```python
# Show strikes with max pain, high OI buildup
"Resistance: 25500 (High CALL OI - selling pressure)"
"Support: 24800 (High PUT OI - buying support)"
```

### 10. **IV Crush Alert** ⭐⭐
**Logic**: If option IV (implied volatility) drops suddenly = event passed
```python
if prev_iv > 25 and curr_iv < 15:
    alert("Option premiums crashed - event risk gone")
```

---

## 🎯 Phase 4: Macro Context

### 11. **Global Market Sentiment** ⭐⭐
**Data**: US indices (S&P500, Nasdaq via Yahoo Finance free API)
**Why**: Indian markets follow US overnight moves
```python
def get_us_indices():
    # S&P500, Nasdaq, Dow from Yahoo Finance
    if sp500_change < -2:
        context = "US markets down 2%+ → Indian market may open weak"
```

### 12. **Currency Impact** ⭐⭐
**Implementation**: USD/INR change → explain impact
```python
if usdinr_up > 0.5:
    msg = "₹ weakened → Good for IT exports (TCS, Infy), bad for importers"
elif usdinr_down > 0.5:
    msg = "₹ strengthened → Bad for IT exports, good for oil imports"
```

### 13. **Crude Oil Tracking** ⭐
**Data**: Brent crude (via commodity API)
**Why**: India imports 85% oil → affects inflation, OMCs, aviation

---

## 🎯 Phase 5: Smart Alerts (Kid-Friendly Insights)

### 14. **"Why is this happening?" Explainer** ⭐⭐⭐
**Implementation**: Rule-based context generation
```python
if pharma_up and nifty_down:
    explain("Pharma UP when market DOWN = Defensive sector rotation")
if vix_up > 10 and nifty_down:
    explain("VIX spiked = Fear is high, traders buying protection")
if bank_down and it_up:
    explain("Money rotating: Banks → IT (sector rotation)")
```

### 15. **Momentum Score** ⭐⭐
**Logic**: Combine 1D, 1W, 1M performance → single 0-100 score
```python
momentum_score = (
    0.5 * today_pct + 
    0.3 * week_pct + 
    0.2 * month_pct
)
if momentum_score > 80: "🔥 Super Strong"
elif momentum_score < 20: "❄️ Weak, avoid"
```

### 16. **Peer Comparison** ⭐⭐
**Implementation**: Compare stock vs sector avg, vs top 3 peers
```python
if INFY_pct > NIFTY_IT_avg + 2:
    msg = "Infosys outperforming IT sector avg by 2%+"
```

---

## 🎯 Phase 6: Historical Intelligence

### 17. **Weekly/Monthly Summary** ⭐⭐⭐
**Implementation**: Aggregate 5 days of snapshots → weekly report
```python
weekly_report = {
    "fii_net_week": sum of 5 days,
    "best_sector_week": highest gainer,
    "worst_sector_week": biggest loser,
    "most_volatile_stocks": top 10 by stdev,
}
# Auto-send every Saturday 10 AM
```

### 18. **Pattern Recognition** ⭐⭐
**Logic**: Detect common patterns
```python
if fii_selling_3_days_straight and dii_buying_3_days:
    alert("Pattern: FII selling, DII supporting (common before reversals)")
```

---

## 🎯 Prioritized Implementation Order

### **Week 1** (Quick Wins):
1. ✅ 52-week proximity alerts (data already available)
2. ✅ Unusual volume detection
3. ✅ Delivery % tracking
4. ✅ Sector rotation logic in delta engine

### **Week 2** (Institutional):
5. Block deals API
6. Bulk deals API
7. FII/DII F&O participant data

### **Week 3** (Context):
8. US market sentiment (Yahoo Finance)
9. Currency impact explainer
10. "Why is this happening?" rules

### **Week 4** (Polish):
11. Weekly summary automation
12. Momentum scoring
13. Pattern recognition

---

## 📊 Data Fields Already Available (Not Using Fully)

From your current NSE scraper, these fields exist but aren't highlighted:

| Field | Current | Enhancement |
|-------|---------|-------------|
| `near_52h`, `near_52l` | ✅ Fetched | ❌ Not alerted | Add proximity alerts |
| `chg_30d`, `chg_365d` | ✅ Fetched | ❌ Not shown | Show momentum trends |
| `yearHigh`, `yearLow` | ✅ Fetched | ❌ Basic use | Calculate % from ATH/ATL |
| `advances`, `declines` | ✅ Shown | ✅ Good | Add breadth ratio (adv/dec) |
| `changeinOpenInterest` | ✅ In options | ⚠️ Partial | Add OI buildup alerts |

---

## 🚀 Most Impactful = **Least Effort**

**Top 3 to implement NOW:**
1. **52W proximity alerts** (5 lines of code, huge value)
2. **Block deals** (new endpoint, easy to add)
3. **Sector rotation tracker** (extend delta engine)

These give you:
- Stock picking signals (52W high breakouts)
- Institutional activity (block deals)
- Market regime changes (rotation)

Would you like me to implement any of these? I can add top 3 in the next 10 minutes! 🚀
