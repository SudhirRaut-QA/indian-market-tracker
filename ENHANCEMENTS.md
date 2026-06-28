# 🚀 Enhancements & Feature Deep-Dive

> What makes this tracker smarter than a simple price alert?
> This page explains the advanced features — the Trading Engine, Self-Learning System, Delta Engine, and more.

---

## 📑 Table of Contents

1. [Trading Engine](#-trading-engine)
2. [Market Bias Score](#-market-bias-score)
3. [Intraday Trading Setups](#-intraday-trading-setups)
4. [Momentum Scanner](#-momentum-scanner)
5. [Delta Engine](#-delta-engine)
6. [Self-Learning EOD Review](#-self-learning-eod-review)
7. [Expert Opinion Engine](#-expert-opinion-engine)
8. [Pre-Open Analysis](#-pre-open-analysis)

---

## ⚙️ Trading Engine

**File**: `tracker/trading_engine.py`

The trading engine is the analytical brain of the tracker. It runs on every fetch cycle and produces:

1. A **market bias score** (BULLISH / BEARISH / NEUTRAL with a number)
2. **Intraday trading setups** for NIFTY, BANKNIFTY, and watchlist stocks
3. A **momentum stock list** with entry/SL/target

### How Pivot Confluence Works

The engine calculates 4 sets of pivot levels from yesterday's OHLC data:

```
Yesterday: High=23,600  Low=23,100  Close=23,450

Classic:    PP=23,383  R1=23,666  S1=23,100
Fibonacci:  PP=23,383  R1=23,574  S1=23,192
Camarilla:  H4=23,512  L4=23,388
Woodie:     PP=23,383  R1=23,616  S1=23,033
```

Then it finds price zones where **multiple methods agree** (confluence). A level with 3-4 methods agreeing is much more reliable than one supported by a single method.

---

### Algo Parameters (Self-Tunable)

The trading engine has configurable parameters in `ALGO_PARAMS`:

```python
ALGO_PARAMS = {
    "min_setup_rr":           1.0,   # Only show setups with R:R >= 1.0
    "momentum_rs_min_pct":    1.5,   # Momentum stock RS must beat NIFTY by 1.5%
    "momentum_val_cr_min":  500.0,   # Minimum ₹500 Cr daily turnover
    "macro_bias_weight":      0.30,  # How much macro bias affects setup score
}
```

These parameters are auto-tuned by the self-learning system after market close.

---

## 📊 Market Bias Score

**The bias score is a -100 to +100 number calculated from 5 inputs:**

```
┌─────────────────────────────────────────────────────────────┐
│                    BIAS SCORE FORMULA                       │
├─────────────────────┬────────────┬───────────────────────── │
│  Signal             │  Weight    │  Condition               │
├─────────────────────┼────────────┼───────────────────────── │
│  FII Buying         │  +15 pts   │  Net buy > ₹500 Cr       │
│  FII Selling        │  -15 pts   │  Net sell > ₹500 Cr      │
│  DII Buying         │  +10 pts   │  Net buy > ₹500 Cr       │
│  DII Selling        │  -10 pts   │  Net sell > ₹500 Cr      │
│  NIFTY > +1%        │  +20 pts   │  Strong green day        │
│  NIFTY +0.3 to +1%  │  +10 pts   │  Mild green day          │
│  NIFTY -0.3 to -1%  │  -10 pts   │  Mild red day            │
│  NIFTY < -1%        │  -20 pts   │  Strong red day          │
│  Breadth ≥ 60%      │  +20 pts   │  Broad advance           │
│  Breadth < 40%      │  -20 pts   │  Broad decline           │
│  VIX < 13           │  +15 pts   │  Calm market             │
│  VIX 13-18          │    0 pts   │  Normal                  │
│  VIX 18-24          │  -10 pts   │  Elevated                │
│  VIX > 24           │  -20 pts   │  High fear               │
└─────────────────────┴────────────┴───────────────────────── ┘

  Score > +15  →  🐂 BULLISH
  Score < -15  →  🐻 BEARISH
  -15 to +15   →  😐 NEUTRAL
```

### Why These Weights?

- **FII** is capped at ±15 (not ±20) because FII data lags by T+1 — it shows yesterday's numbers during the day
- **Breadth** gets the most weight (±20) because it's real-time and the most honest signal of market health
- **NIFTY%** uses two tiers (+10 for mild, +20 for strong moves) to avoid rewarding insignificant moves equally with large ones

---

## 🎯 Intraday Trading Setups

For each setup, the engine outputs:

```
NIFTY 50 | Bias: BULLISH (+25)
📥 Entry:      23,380  (above CPR, near Classic R1 confluence)
🛡️ Stop-Loss:  23,280  (below pivot support)
🎯 Target:     23,580  (at R2 — Fib + Classic agreement)
📐 R:R:         2.0   (risk ₹100, target ₹200)
🔗 Confluences: 3/4 methods agree at target
```

### R:R Target Extension

If the initial nearest target (R1) gives a poor R:R (< 1.0), the engine automatically extends the target to R2 (for LONG) or S2 (for SHORT):

```
Without extension:  Entry=23,380  SL=23,280  Target=R1=23,420  R:R=0.4  ❌ Never shown
With extension:     Entry=23,380  SL=23,280  Target=R2=23,580  R:R=2.0  ✅ Shown
```

**Only setups with R:R ≥ 1.0 appear in Telegram messages.**

---

## 🔥 Momentum Scanner

Scans all sector stocks for momentum candidates every session.

### Criteria for a Stock to Appear as Momentum Alert:

1. **Relative Strength** ≥ 1.5% above NIFTY's day % change
2. **Volume** ≥ ₹500 Cr turnover today
3. **R:R** ≥ 0.8 on the generated setup
4. **Positive day** (price change > 0%)

### Output (max 6 per message):

```
🔥 Momentum Alerts
RELIANCE  ₹2,940  ▲+2.1%  RS+1.1%  Entry 2,938  SL 2,890  T 3,020  R:R 1.7
INFOSYS   ₹1,792  ▲+1.8%  RS+0.8%  Entry 1,790  SL 1,755  T 1,855  R:R 1.9
```

Capped at 6 to prevent message overflow in Telegram.

---

## 🔄 Delta Engine

**File**: `tracker/delta_engine.py`

The delta engine compares the current snapshot with the previous one (saved in `data/snapshots/`).

### What it detects:

| Signal | Threshold | Meaning |
|--------|-----------|---------|
| **FII flow reversal** | Direction change | Was buying → now selling (big alert!) |
| **Index surge** | ±0.5% since last snapshot | Rapid intraday move |
| **Volume spike** | > 2× average | Unusual activity in a stock |
| **PCR shift** | ±0.2 move | Sentiment change in options market |
| **VIX spike** | > 5% in a session | Sudden anxiety |

### Example Delta Message:

```
📊 What Changed Since 9:30 AM
  ⚠️  NIFTY: -0.3% (was flat, now sliding)
  🔄 FII: Reversed to SELLING (was buying at open)
  📈 HDFC: Volume 3x normal — strong accumulation
  🔻 PCR: 1.2 → 0.9 (sentiment turning cautious)
```

---

## 🧠 Self-Learning EOD Review

**File**: `tracker/trade_tracker.py`

After market close (3:30 PM), the tracker reviews its own recommendations from the day.

### How it works:

1. **Morning**: `save_recommendations()` stores all setups (entry, SL, target) to JSON
2. **Evening**: `review_day()` fetches closing prices and checks:
   - Did the trade reach target? (Win)
   - Did it hit stop-loss? (Loss)
   - Neither? (Neutral)
3. **Auto-tune**: Based on win/loss rate, it adjusts `ALGO_PARAMS`:
   - Win rate > 60%: Accept looser R:R (lower `min_setup_rr`)
   - Win rate < 40%: Tighten criteria (raise `min_setup_rr`, `momentum_rs_min_pct`)
   - Many false signals: Reduce macro bias weight

### Config Auto-Tuning Rules:

```
Win Rate > 60% for 5 consecutive days:
  → min_setup_rr: 1.0 → 0.9 (slightly looser — we're on a good streak)

Win Rate < 40%:
  → min_setup_rr: 1.0 → 1.2 (tighter — too many false signals)
  → momentum_rs_min_pct: 1.5 → 2.0 (higher bar for momentum)

Too many macro overrides:
  → macro_bias_weight: 0.30 → 0.20 (trust technical signals more)
```

> This makes the system gradually smarter over time by learning from its own mistakes.

---

## 💬 Expert Opinion Engine

Every Telegram message ends with an "Expert Opinion" section, generated algorithmically:

### What it analyses:

1. **Bias Direction** (BULLISH / BEARISH / NEUTRAL)
2. **Market Breadth** — is it a broad or narrow move?
3. **Sector Rotation** — which 2 sectors are leading, which 2 are lagging?
4. **VIX level** — what level of caution is warranted?
5. **FII/DII alignment** — are the big players agreeing or diverging?

### Example Output:

```
🤖 Expert Opinion
Market: BULLISH | Broad rally (38/50 advancing)
Leading: IT (+1.8%), DEFENCE (+1.2%)
Lagging: REALTY (-1.1%), METAL (-0.5%)
Spread: 3.0% — significant sector rotation

📌 Advice: Broad advance with 3 of 4 macro signals bullish.
Consider adding exposure in IT and DEFENCE.
Avoid REALTY and METAL until momentum returns.
VIX 21.6 (elevated) — use defined stop-losses.
```

---

## 🌅 Pre-Open Analysis

**Runs at 9:00 AM and 9:08 AM IST only.** After 9:20 AM IST, the pre-open module is disabled to avoid serving stale data mid-session.

### What Pre-Open Shows:

- **IEP** (Indicative Equilibrium Price) — where stocks are expected to open based on pending orders
- **Pre-open volume** — how much demand exists before 9:15 AM
- **Gapper stocks** — stocks with large bid-ask gaps (expected to open with a jump or drop)

### Why the 9:20 AM Cutoff?

Pre-open data is only meaningful before the market opens. After 9:20 AM, the market is live and real prices replace the indicative ones. The tracker enforces this cutoff regardless of which slot triggered it.

---

## 📊 Excel Logger (7 Sheets)

**File**: `tracker/excel_manager.py`

Every tracker run appends a row to `data/excel/market_tracker.xlsx`:

| Sheet | Colour | Content |
|-------|--------|---------|
| Summary | 🟦 Blue | NIFTY, BANKNIFTY, FII/DII, VIX, bias score |
| Indices | 🟩 Green | All 21 indices with High, Low, Close, % change |
| Sectors | 🟨 Yellow | All 16 sectors — top 3 gainers, top 3 losers |
| FII/DII | 🟧 Orange | Buy value, sell value, net flow, prev comparison |
| Options | 🟪 Purple | PCR, max pain, total OI for NIFTY & BANKNIFTY |
| Corporate | 🔵 Teal | Upcoming dividends, splits, bonuses |
| Insider | 🔴 Red | PIT disclosures — insider name, shares, value |

---

*Last updated: March 2026*
