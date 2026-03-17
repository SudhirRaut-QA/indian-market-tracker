# 📖 Glossary — Every Term Explained Simply

> **Goal:** After reading this page, even a 10-year-old should understand what each term in your Telegram messages means.
> No jargon. No assumptions. Just plain English with examples.

---

## 📋 Table of Contents

1. [Market Participants](#1--market-participants)
2. [Key Indices](#2--key-indices)
3. [Market Health Signals](#3--market-health-signals)
4. [Trading Terms](#4--trading-terms)
5. [Pivot & Support/Resistance Levels](#5--pivot--supportresistance-levels)
6. [Options Terms](#6--options-terms)
7. [Message Labels Explained](#7--message-labels-decoded)
8. [Frequently Asked Questions](#8--faq)

---

## 1. 🏦 Market Participants

### FII — Foreign Institutional Investors
**What it is:** Big foreign money — banks, hedge funds, pension funds from USA, Europe, etc.

**Simple analogy:** Imagine a very rich uncle from America who sometimes puts money into Indian companies. When he buys a lot, prices go up. When he sells, prices can fall.

**Why it matters:**
- FII **Buying** → Market often goes up 📈
- FII **Selling** → Market often comes under pressure 📉

```
💰 FII: BUYING ₹9,977 Cr  ✅  ← Foreign money flowing IN (bullish)
💰 FII: SELLING ₹5,200 Cr ⚠️  ← Foreign money flowing OUT (bearish)
```

> ⚠️ **Note:** FII data on NSE is reported with 1-day delay (T+1). Today's message shows yesterday's numbers.

---

### DII — Domestic Institutional Investors
**What it is:** Indian institutions — mutual funds, LIC, EPFO, insurance companies.

**Simple analogy:** These are big Indian companies that manage millions of people's savings (like your PF, insurance, SIP). They often buy when FII sells — they're like the "defenders" of the market.

**Key insight:** When FII sells and DII buys at the same time, the market stays stable. When both sell — that's trouble.

```
🏛️ DII: BUYING ₹8,200 Cr  ✅  ← Indian institutions supporting market
🏛️ DII: SELLING ₹2,100 Cr ⚠️  ← Unusual — means they are cautious too
```

---

## 2. 📈 Key Indices

### NIFTY 50
The top 50 biggest companies in India, combined into one number. Think of it as the "temperature of the big companies."

- **NIFTY goes up** → Most large companies are growing
- **NIFTY goes down** → Most large companies are falling

### BANK NIFTY
Top 12 banking stocks. Banks are very important — their health reflects the whole economy.

### INDIA VIX — The Fear Meter 😨
**Full name:** Volatility Index

**What it is:** Measures how **nervous** the market is. Higher VIX = more uncertainty = more danger.

| VIX Range | Mood | What It Means |
|-----------|------|--------------|
| **Below 13** | 😌 Calm | Market is relaxed, low risk |
| **13–18** | 😐 Normal | Typical day, no unusual fear |
| **18–24** | 😬 Elevated | Some nervousness, trade cautiously |
| **Above 24** | 😱 High Fear | Panic mode — high risk, expect big swings |

**Simple example:** Imagine VIX is like the weather forecast:
- VIX 10 = Sunny day ☀️ — go outside freely
- VIX 20 = Cloudy ⛅ — take a jacket
- VIX 30 = Thunderstorm ⛈️ — maybe stay home

---

### Other Indices You'll See

| Index | Tracks |
|-------|-------|
| NIFTY IT | Software companies (Infosys, TCS, Wipro) |
| NIFTY PHARMA | Medicine/healthcare companies |
| NIFTY AUTO | Car, bike manufacturers (Maruti, Tata Motors) |
| NIFTY METAL | Steel, aluminium companies (Tata Steel, SAIL) |
| NIFTY REALTY | Real estate companies |
| NIFTY PSU BANK | Government-owned banks (SBI, PNB) |
| NIFTY DEFENCE | Defence sector (HAL, BEL, Bharat Dynamics) |
| NIFTY FMCG | Daily use goods (HUL, Nestle, Britannia) |
| NIFTY MIDCAP 50 | Medium-sized companies (more growth potential, more risk) |
| NIFTY SMALLCAP 50 | Small companies (highest risk, highest reward potential) |
| NIFTY MOMENTUM 30 | Stocks moving the fastest upward recently |
| NIFTY HIGH BETA 50 | Stocks that move more than the market (amplified moves) |

---

## 3. 📊 Market Health Signals

### Market Breadth — How Wide Is the Rally?
**What it is:** Count of stocks that went UP vs DOWN today.

**Simple analogy:** If 30 students got good marks and 20 got bad marks — that's a "broad" good result. But if only 5 star students lifted the class average, that's a "narrow" result.

```
Breadth: 35 ▲ / 15 ▼ → Broad rally — most stocks rising (healthy)
Breadth: 12 ▲ / 38 ▼ → Narrow — only a few stocks pulling the index
```

**Ratio calculation:** `30 / (30 + 20) = 0.60` → 60% stocks advancing

| Breadth Ratio | Signal |
|--------------|--------|
| > 0.70 | 🟢 Very Bullish — broad participation |
| 0.55–0.70 | 🟡 Bullish — healthy rally |
| 0.45–0.55 | ⚪ Neutral |
| < 0.45 | 🔴 Bearish — more stocks falling |

---

### Market Bias — The Overall Verdict
A score the system calculates by combining:
- FII/DII direction (what big money is doing)
- Market breadth (how many stocks are rising)
- NIFTY % change today
- India VIX level

```
🟢 BULLISH  (score > +15)  → Good conditions to look for entries
🟡 NEUTRAL  (score -15 to +15) → Mixed signals, be selective
🔴 BEARISH  (score < -15)  → Caution, defensive stance
```

---

### Delta — What Changed?
**What it is:** Comparison between the previous snapshot and the current one.

Like comparing a photo of your room in the morning vs evening — the "delta" is what moved.

```
⚡ Delta Alert: FII was SELLING, now BUYING → Reversal — bullish signal
⚡ NIFTY: was 23,100 at 11:00, now 23,450 at 15:35 → +350 pts gain
```

---

## 4. 🎯 Trading Terms

### LTP — Last Traded Price
Simply the **most recent price** at which a stock was bought or sold.

---

### R:R — Risk-to-Reward Ratio
**The most important number in any trade setup.**

**Simple analogy:** You bet ₹10. If you win, you get ₹25. If you lose, you only lose ₹10. That's a 2.5:1 reward-to-risk — a great bet!

```
Entry:  ₹500 (you buy here)
Stop:   ₹490 (if it falls here, you exit — you lose ₹10)
Target: ₹525 (if it rises here, you exit — you gain ₹25)

Risk     = 500 - 490 = ₹10
Reward   = 525 - 500 = ₹25
R:R      = 25 / 10 = 2.5  ← Great! You risk 1 to make 2.5
```

| R:R | Quality |
|-----|---------|
| Below 1.0 | ❌ Skip — not worth the risk |
| 1.0–1.5 | ⚠️ Acceptable if signal is strong |
| 1.5–2.5 | ✅ Good trade |
| Above 2.5 | 🌟 Excellent setup |

> 🔒 **Our system only shows setups with R:R ≥ 1.0 for long/short and ≥ 0.8 for momentum.**

---

### LONG vs SHORT
- **LONG:** You buy a stock hoping it will rise. You profit when price goes UP.
- **SHORT:** You sell borrowed shares hoping price falls, then buy back cheaper. You profit when price goes DOWN.

In our Telegram messages:
```
⚡ INFY  LONG | Entry 1,820 | SL 1,790 | T 1,900 | R:R 2.7
   → Buy INFY at 1,820, place stop-loss at 1,790, target 1,900

⚡ SBIN  SHORT | Entry 780 | SL 795 | T 740 | R:R 2.7
   → Short SBIN at 780, stop if it goes above 795, target 740
```

---

### SL — Stop Loss
The price at which you **automatically exit** a bad trade to limit your loss.

**Think of it as a safety net:** You won't let a ₹500 trade turn into a ₹450 disaster. You set SL at ₹490 and sleep peacefully.

---

### Entry Zone
The recommended price range to enter a trade. If the stock is already far above this zone, the setup may no longer be valid.

---

### Momentum
A stock with **momentum** is moving fast in one direction with high volume — like a train that's already moving fast. These are often the best short-term trades.

---

## 5. 📐 Pivot & Support/Resistance Levels

### What Are Pivots?
**Pivot points** are price levels calculated from yesterday's High, Low, and Close. Traders all over the world use the same formulas, making these levels act as **magnets** — price tends to bounce or break at these points.

**Simple analogy:** Imagine a rubber ball on a staircase. It bounces at each step — those steps are like pivot levels.

```
Yesterday: High = 23,600 | Low = 23,100 | Close = 23,450

Pivot Point (PP) = (H + L + C) / 3 = 23,383

R1 = 23,666   ← Resistance 1 (first ceiling)
R2 = 23,883   ← Resistance 2 (bigger ceiling)
R3 = 24,166   ← Resistance 3 (major wall)

S1 = 23,166   ← Support 1 (first floor)
S2 = 22,883   ← Support 2 (bigger floor)
S3 = 22,600   ← Support 3 (major floor)
```

### The 4 Pivot Methods We Use

| Method | Best For | Special Feature |
|--------|----------|----------------|
| **Classic** | Intraday & swing | Most widely used worldwide |
| **Fibonacci** | Wave-based moves | 38.2%, 61.8% retracement levels |
| **Camarilla** | Intraday reversals | Tighter levels near price |
| **Woodie** | Trend-following | Gives more weight to close price |

### CPR — Central Pivot Range
A **zone** (not just a point) between 3 pivot calculations. When price is inside CPR, the market is undecided. When it cleanly breaks above or below, a direction is established.

```
CPR: 23,350 – 23,420  ← "No man's land" — wait for breakout
Price above CPR → Bullish bias
Price below CPR → Bearish bias
```

---

### VWAP — Volume Weighted Average Price
**What it is:** The average price where most trading happened today, weighted by how much traded at each price.

**Simple analogy:** If 1,000 people bought milk at ₹50 and 100 people bought at ₹55, the "true" average price is closer to ₹50 — that's VWAP.

```
Price > VWAP → Buyers in control (bullish intraday)
Price < VWAP → Sellers in control (bearish intraday)
```

Institutional traders (big funds) use VWAP to judge if they're getting a "good" price.

---

### Support & Resistance (S/R)

| Term | What It Means |
|------|--------------|
| **Support** | A price floor — buyers gather here, price tends to bounce up |
| **Resistance** | A price ceiling — sellers gather here, price tends to bounce down |
| **Breakout** | Price pushes through resistance with strong volume |
| **Breakdown** | Price falls through support with strong volume |

---

## 6. 📊 Options Terms

### PCR — Put-Call Ratio
**What it is:** Number of Put options ÷ Number of Call options outstanding.

**Simple analogy:**
- **Put options** = Insurance bought by people who think the market will fall
- **Call options** = Bets bought by people who think the market will rise

```
PCR = Puts ÷ Calls

PCR < 0.7   → Too many calls → Overconfident bulls → Market may fall
PCR 0.7–1.0 → Balanced → Healthy
PCR 1.0–1.3 → Moderate fear → Often a buying opportunity
PCR > 1.3   → Extreme fear → Often a contrarian BUY signal
```

**Remember:** When everyone is scared (high PCR), markets often bottom. When everyone is greedy (low PCR), markets often top.

---

### Max Pain
The price at which the **maximum number of options contracts expire worthless** — meaning option sellers (who are usually banks and institutions) make the most money.

Price often "gravitates" toward max pain as expiry approaches.

```
Max Pain: 23,500  ← Market may drift toward this level by Thursday expiry
```

---

### OI — Open Interest
The total number of futures/options contracts that are **currently open** (not yet settled). Rising OI means new money is entering the trade.

```
Rising OI + Rising Price → Strong uptrend (new longs added)
Rising OI + Falling Price → Strong downtrend (new shorts added)
Falling OI + Rising Price → Short covering (weak, may not sustain)
```

---

## 7. 💬 Message Labels Decoded

Here is how to read your Telegram messages:

### Market Overview Label
```
📊 NIFTY 50: 23,450  ▲ +1.1%  — BULLISH ✅
             └─LTP─┘  └─day%─┘  └─bias─┘
```

### FII/DII Flow Label
```
💰 FII: BUYING ₹9,977 Cr  ✅  [Equity]
🏛️ DII: BUYING ₹8,200 Cr  ✅  [Equity]
```

### Trading Setup Label
```
⚡ INFY   LONG | Entry: 1,820 | SL: 1,790 | T: 1,900 | R:R 2.7  [IT]
   └─sym─┘ └dir┘         └buy at┘    └exit if wrong┘  └target┘
```

### Watchlist Label
```
👁️ RELIANCE  LTP: 2,845  Entry: 2,800  +1.6% 🟢
   └─symbol─┘     └─now─┘       └─your price─┘   └─P&L─┘
```

### VIX Mood Line
```
😐 VIX: 16.2 (Normal) | 📊 Breadth: 32/50 green | 🎯 Bias: BULLISH
```

### Expert Opinion
```
🧠 Expert Opinion:
Direction confirmed by breadth (broad rally 32/50 green).
Top sectors: IT +2.1%, PHARMA +1.4% | Weak: REALTY -0.8%
Advice: Momentum favours longs. Trade IT/PHARMA setups with SL discipline.
VIX 16.2 = normal risk — standard position sizes.
```

---

## 8. ❓ FAQ

**Q: What does ₹Cr mean?**
Crore Rupees. 1 Crore = 10 million = 1,00,00,000. So ₹9,977 Cr = roughly ₹100 billion — massive amounts of money.

**Q: Why does FII data sometimes show yesterday's numbers?**
NSE publishes provisional FII/DII data with a 1-day delay. The 18:00 and 21:00 slots have updated numbers. Morning slots show the previous day's final figures.

**Q: What's the difference between Sector and Index?**
An **Index** is just a number (price level). A **Sector** is the group of companies. NIFTY IT (index) tracks the IT sector (companies like TCS, Infosys).

**Q: A trade setup shows Entry: 1,820 but stocks is at 1,845 now. Should I still buy?**
No — the setup is "stale." Entry zones are calculated at the time of the message. If price has moved significantly away from entry, the risk calculation is no longer valid.

**Q: What is Delivery %?**
When stocks are bought, some buyers take "delivery" (hold overnight) and some are just intraday traders. High delivery % (>60%) means genuine long-term buyers are accumulating — a bullish signal. Low delivery % (<25%) means mostly speculative, short-term activity.

**Q: What does 52-week High/Low mean?**
The highest and lowest price a stock traded at in the past 52 weeks (1 year):
- Near 52W High = Breakout zone — strong momentum
- Near 52W Low = Value zone — potential bounce (but also dangerous)

**Q: What is a Corporate Action?**
A company decision that affects its shares:
| Action | What Happens |
|--------|-------------|
| **Dividend** | Company pays you cash for holding shares |
| **Bonus** | Company gives you extra free shares (e.g., 1:1 = double your shares) |
| **Split** | Share price halved, you get double shares (value unchanged) |
| **Rights Issue** | Company offers you new shares at a discount |

**Q: What is Insider Trading (PIT)?**
When a company promoter (founder/owner) buys or sells their **own company's shares**, they must report it publicly. This is called PIT (Prevention of Insider Trading) disclosure. Promoters buying their own stock = strong confidence signal.

**Q: Why does the bot sometimes say "Market Closed"?**
NSE is closed on weekends, Indian public holidays (Diwali, Republic Day, etc.), and sometimes for market circuit breakers. The bot detects this and notifies you.

---

*📌 Missing a term? It might be in the message. Open an issue or ask `@your_bot /help`.*