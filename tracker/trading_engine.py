"""
Trading Engine - Intraday Support/Resistance & Trade Setup Generator
=====================================================================

Multi-pivot confluence analysis for indices, stocks, and ETFs.
Uses 4 pivot methods (Classic, Fibonacci, Camarilla, Woodie) plus CPR.
When 2-3+ methods agree on a level, the zone has the highest reliability.

Factors scored:
  - Pivot Confluence (mathematical S/R levels)
  - VWAP estimate (volume-weighted average price)
  - FII/DII directional bias
  - VIX risk gauge
  - Market breadth (advance/decline ratio)
  - 30-day / 365-day momentum
  - 52-week proximity (breakout / breakdown zones)
  - Relative strength vs sector / index
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from . import config

logger = logging.getLogger(__name__)

_ALGO_PARAMS_FILE = config.DATA_DIR / "trading" / "algo_params.json"

_DEFAULT_PARAMS = {
    "direction_score_threshold": 15,
    "momentum_rs_min_pct":        1.5,
    "momentum_val_cr_min":      500.0,
    "macro_bias_weight":          0.30,
    "sl_buffer_pct":              0.015,
    "confidence_floor":          50,    # min 0-100 confidence to show a setup
    "sector_blacklist":          [],    # sectors with consistently poor win rates
    "top_trigger_types":         [],    # trigger types ranked by historical win rate
}


def _load_trading_params() -> dict:
    """Load auto-tuned params from disk, falling back to defaults."""
    try:
        if _ALGO_PARAMS_FILE.exists():
            with open(_ALGO_PARAMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**_DEFAULT_PARAMS, **data.get("params", {})}
    except Exception as e:
        logger.debug(f"algo_params load error: {e}")
    return dict(_DEFAULT_PARAMS)

# Sector display map (matches telegram_bot.py)
_SECTOR_DISPLAY = {
    "NIFTY 50": "Nifty 50", "NIFTY BANK": "Bank", "NIFTY NEXT 50": "Next 50",
    "NIFTY IT": "IT", "NIFTY AUTO": "Auto", "NIFTY PHARMA": "Pharma",
    "NIFTY METAL": "Metal", "NIFTY ENERGY": "Energy", "NIFTY FMCG": "FMCG",
    "NIFTY REALTY": "Realty", "NIFTY FINANCIAL SERVICES": "Fin Svc",
    "NIFTY PSU BANK": "PSU Bank", "NIFTY INDIA DEFENCE": "Defence",
    "NIFTY OIL & GAS": "Oil & Gas", "NIFTY COMMODITIES": "Commod.",
    "NIFTY MIDCAP 50": "Midcap 50", "NIFTY SMALLCAP 50": "Smallcap 50",
}


def _sector_display(name: str) -> str:
    return _SECTOR_DISPLAY.get(name, name.replace("NIFTY ", "") or name)


# ─── Pivot Calculators ──────────────────────────────────────────────────────

def _classic_pivots(h: float, l: float, c: float) -> Dict:
    """Standard floor-trader pivots (most widely used)."""
    p = (h + l + c) / 3
    return {
        "P": round(p, 2),
        "R1": round(2 * p - l, 2),
        "R2": round(p + (h - l), 2),
        "R3": round(h + 2 * (p - l), 2),
        "S1": round(2 * p - h, 2),
        "S2": round(p - (h - l), 2),
        "S3": round(l - 2 * (h - p), 2),
    }


def _fibonacci_pivots(h: float, l: float, c: float) -> Dict:
    """Fibonacci retracement pivots."""
    p = (h + l + c) / 3
    r = h - l
    return {
        "P": round(p, 2),
        "R1": round(p + 0.382 * r, 2),
        "R2": round(p + 0.618 * r, 2),
        "R3": round(p + r, 2),
        "S1": round(p - 0.382 * r, 2),
        "S2": round(p - 0.618 * r, 2),
        "S3": round(p - r, 2),
    }


def _camarilla_pivots(h: float, l: float, c: float) -> Dict:
    """Camarilla pivots – best for intraday reversal trades."""
    r = h - l
    return {
        "P": round((h + l + c) / 3, 2),
        "R1": round(c + r * 1.1 / 12, 2),
        "R2": round(c + r * 1.1 / 6, 2),
        "R3": round(c + r * 1.1 / 4, 2),
        "R4": round(c + r * 1.1 / 2, 2),
        "S1": round(c - r * 1.1 / 12, 2),
        "S2": round(c - r * 1.1 / 6, 2),
        "S3": round(c - r * 1.1 / 4, 2),
        "S4": round(c - r * 1.1 / 2, 2),
    }


def _woodie_pivots(h: float, l: float, c: float) -> Dict:
    """Woodie pivots (extra weight on close)."""
    p = (h + l + 2 * c) / 4
    return {
        "P": round(p, 2),
        "R1": round(2 * p - l, 2),
        "R2": round(p + (h - l), 2),
        "S1": round(2 * p - h, 2),
        "S2": round(p - (h - l), 2),
    }


def _cpr(h: float, l: float, c: float) -> Dict:
    """Central Pivot Range – narrow CPR = trending day."""
    p = (h + l + c) / 3
    bc = (h + l) / 2
    tc = (p - bc) + p
    width_pct = abs(tc - bc) / p * 100 if p else 0
    return {
        "pivot": round(p, 2),
        "tc": round(max(tc, bc), 2),    # top of CPR
        "bc": round(min(tc, bc), 2),    # bottom of CPR
        "width_pct": round(width_pct, 2),
    }


def _estimate_vwap(volume: float, value_cr: float) -> float:
    """Estimate VWAP from aggregate volume and value traded."""
    if volume and value_cr and volume > 0:
        return round(value_cr * 1e7 / volume, 2)
    return 0.0


# ─── Multi-Factor Confidence Scorer ─────────────────────────────────────────

def _stock_confidence_score(
    pct: float,
    chg_30d: float,
    chg_365d: float,
    value_cr: float,
    near_52h: float,
    near_52l: float,
    sector_pct: float,
    ltp: float,
    pivot: float,
    vwap: float,
    cpr_width_pct: float,
    direction: str,   # LONG / SHORT / NEUTRAL
    rr_ratio: float,
    bias_score: int,  # market bias -100 to +100
    vix_val: float,
) -> Tuple[int, List[str]]:
    """
    Score a trade setup on 5 dimensions (0-100 total).
    Returns (score, evidence_list).

    Dim 1 — Trend Quality   (0-25 pts): Aligns with medium/long-term trend
    Dim 2 — Volume Quality  (0-20 pts): Institutional-grade interest
    Dim 3 — Technical Setup (0-25 pts): Pivot, VWAP, CPR, 52W position
    Dim 4 — Market Harmony  (0-20 pts): Market bias and sector alignment
    Dim 5 — Risk Quality    (0-10 pts): R:R ratio strength
    """
    score = 0
    evidence = []

    # ── Dim 1: Trend Quality ──────────────────────────────────────────────
    trend_pts = 0
    if direction == "LONG":
        if chg_30d > 0 and chg_365d > 0:
            trend_pts += 10
            evidence.append("Trend ↑ (30d & 1Y aligned)")
        elif chg_30d > 0:
            trend_pts += 5
            evidence.append("30d uptrend ↑")
        if chg_30d > 10:
            trend_pts += 5
            evidence.append(f"Strong 30d momentum +{chg_30d:.0f}%")
        if sector_pct > 0 and pct > 0:
            trend_pts += 5
            evidence.append("Sector & stock both green")
        elif pct > 0:
            trend_pts += 2
            evidence.append("Stock leading sector")
    elif direction == "SHORT":
        if chg_30d < 0 and chg_365d < 0:
            trend_pts += 10
            evidence.append("Trend ↓ (30d & 1Y aligned)")
        elif chg_30d < 0:
            trend_pts += 5
            evidence.append("30d downtrend ↓")
        if chg_30d < -10:
            trend_pts += 5
            evidence.append(f"Strong 30d decline {chg_30d:.0f}%")
        if sector_pct < 0 and pct < 0:
            trend_pts += 5
            evidence.append("Sector & stock both red")
        elif pct < 0:
            trend_pts += 2
            evidence.append("Stock leading sector down")
    score += min(trend_pts, 25)

    # ── Dim 2: Volume Quality ─────────────────────────────────────────────
    vol_pts = 0
    if value_cr >= 1000:
        vol_pts = 20
        evidence.append(f"Very high volume ₹{value_cr:,.0f}Cr")
    elif value_cr >= 500:
        vol_pts = 15
        evidence.append(f"High volume ₹{value_cr:,.0f}Cr")
    elif value_cr >= 200:
        vol_pts = 10
        evidence.append(f"Above-avg volume ₹{value_cr:,.0f}Cr")
    elif value_cr >= 50:
        vol_pts = 5
    score += min(vol_pts, 20)

    # ── Dim 3: Technical Setup ────────────────────────────────────────────
    tech_pts = 0
    if direction == "LONG":
        if pivot > 0 and ltp > pivot:
            tech_pts += 5
            evidence.append("Price above pivot ✓")
        if vwap > 0 and ltp > vwap:
            tech_pts += 5
            evidence.append("Price above VWAP ✓")
        # Near 52W high = breakout zone (strong momentum signal)
        if isinstance(near_52h, (int, float)) and 0 < near_52h <= 2:
            tech_pts += 10
            evidence.append(f"Breakout zone! {near_52h:.1f}% to 52W high")
        elif isinstance(near_52h, (int, float)) and 0 < near_52h <= 5:
            tech_pts += 5
            evidence.append(f"Near 52W high ({near_52h:.1f}%)")
        # 52W low reversal (requires strong up move today)
        if isinstance(near_52l, (int, float)) and 0 < near_52l <= 3 and pct > 1.5:
            tech_pts += 5
            evidence.append(f"Strong reversal from 52W low")
        if cpr_width_pct < 0.3:
            tech_pts += 5
            evidence.append("Narrow CPR → trending day")
    elif direction == "SHORT":
        if pivot > 0 and ltp < pivot:
            tech_pts += 5
            evidence.append("Price below pivot ✓")
        if vwap > 0 and ltp < vwap:
            tech_pts += 5
            evidence.append("Price below VWAP ✓")
        # Near 52W HIGH = better breakdown location
        if isinstance(near_52h, (int, float)) and 0 < near_52h <= 3:
            tech_pts += 8
            evidence.append(f"Near 52W high — short at resistance")
        # Near 52W LOW = value zone, NOT a short setup — penalise heavily
        if isinstance(near_52l, (int, float)) and 0 < near_52l <= 5:
            tech_pts -= 15   # strong penalty: don't short what's already near bottom
            evidence.append(f"⚠ Near 52W low — risky short ({near_52l:.1f}% above low)")
        if cpr_width_pct < 0.3:
            tech_pts += 5
            evidence.append("Narrow CPR → trending day")
    score += max(0, min(tech_pts, 25))

    # ── Dim 4: Market Harmony ─────────────────────────────────────────────
    mkt_pts = 0
    if direction == "LONG" and bias_score >= 30:
        mkt_pts += 10
        evidence.append("Market strongly bullish")
    elif direction == "LONG" and bias_score >= 10:
        mkt_pts += 5
    elif direction == "SHORT" and bias_score <= -30:
        mkt_pts += 10
        evidence.append("Market strongly bearish")
    elif direction == "SHORT" and bias_score <= -10:
        mkt_pts += 5

    if direction == "LONG" and sector_pct > 0.5:
        mkt_pts += 5
        evidence.append(f"Sector positive ({sector_pct:+.1f}%)")
    elif direction == "SHORT" and sector_pct < -0.5:
        mkt_pts += 5
        evidence.append(f"Sector negative ({sector_pct:+.1f}%)")

    # VIX penalty: high fear = reduce confidence for LONG
    if vix_val >= 24 and direction == "LONG":
        mkt_pts -= 5
        evidence.append(f"VIX {vix_val:.1f} (fear — caution)")
    elif vix_val < 13 and direction == "LONG":
        mkt_pts += 5
        evidence.append(f"VIX {vix_val:.1f} (low fear — ideal)")
    score += max(0, min(mkt_pts, 20))

    # ── Dim 5: Risk Quality ───────────────────────────────────────────────
    if rr_ratio >= 3.0:
        score += 10
        evidence.append(f"Excellent R:R {rr_ratio:.1f}")
    elif rr_ratio >= 2.0:
        score += 8
        evidence.append(f"Good R:R {rr_ratio:.1f}")
    elif rr_ratio >= 1.5:
        score += 5
        evidence.append(f"R:R {rr_ratio:.1f}")
    elif rr_ratio >= 1.0:
        score += 2

    score = max(0, min(100, score))
    label = (
        "🌟 Premium" if score >= 70 else
        "⚡ Good"    if score >= 50 else
        "💡 Low"     if score >= 35 else
        "❌ Weak"
    )
    return score, label, evidence[:5]   # cap evidence to 5 items


def _position_sizing(vix_val: float, rr_ratio: float, confidence: int) -> str:
    """Suggest position sizing based on VIX, R:R and confidence."""
    # Base capital risk per trade
    if confidence >= 70 and rr_ratio >= 2.0 and vix_val < 18:
        return "Full position (2% capital risk)"
    elif confidence >= 50 and rr_ratio >= 1.5 and vix_val < 24:
        return "Half position (1% capital risk)"
    elif vix_val >= 24:
        return "Micro position only (0.5% capital risk, high VIX)"
    else:
        return "Quarter position (0.5% capital risk)"


# ─── Confluence Finder ──────────────────────────────────────────────────────

def _find_confluence_zones(
    pivots: Dict[str, Dict], ltp: float, tolerance_pct: float = 0.3
) -> List[Dict]:
    """
    Group levels from all pivot methods that fall within tolerance_pct of
    each other.  Zones where 3+ methods agree are marked Strong.
    """
    # Collect all named levels
    levels = []  # [(value, method, label)]
    for method, pvt in pivots.items():
        for label, val in pvt.items():
            if label in ("width_pct",):
                continue
            if isinstance(val, (int, float)) and val > 0:
                levels.append((val, method, label))

    levels.sort(key=lambda x: x[0])

    # Cluster nearby levels
    zones = []
    used = set()
    for i, (val, m, lab) in enumerate(levels):
        if i in used:
            continue
        cluster = [(val, m, lab)]
        used.add(i)
        for j in range(i + 1, len(levels)):
            if j in used:
                continue
            if abs(levels[j][0] - val) / val * 100 <= tolerance_pct:
                cluster.append(levels[j])
                used.add(j)

        # Determine zone type (support or resistance relative to LTP)
        avg = sum(c[0] for c in cluster) / len(cluster)
        zone_type = "Resistance" if avg > ltp else "Support"
        distance_pct = (avg - ltp) / ltp * 100 if ltp else 0

        strength = "Strong" if len(cluster) >= 3 else ("Moderate" if len(cluster) >= 2 else "Standard")
        methods = list({c[1] for c in cluster})
        labels = [f"{c[1]}:{c[2]}" for c in cluster]

        zones.append({
            "level": round(avg, 2),
            "type": zone_type,
            "strength": strength,
            "methods_count": len(cluster),
            "methods": methods,
            "labels": labels,
            "distance_pct": round(distance_pct, 2),
        })

    # Sort by distance from LTP
    zones.sort(key=lambda z: abs(z["distance_pct"]))
    return zones


# ─── Market Bias Scorer ─────────────────────────────────────────────────────

def _market_bias(snapshot: Dict) -> Dict:
    """Score overall market direction from multiple factors (-100 to +100)."""
    score = 0
    reasons = []

    # 1. FII/DII  (T+1 data — treat as context, not dominant signal)
    fd = snapshot.get("fii_dii", {})
    fii_net = fd.get("fii", {}).get("net", 0) or 0
    dii_net = fd.get("dii", {}).get("net", 0) or 0
    if fii_net > 500:
        score += 15
        reasons.append(f"FII buying ₹{fii_net:,.0f}Cr")
    elif fii_net < -500:
        score -= 15
        reasons.append(f"FII selling ₹{abs(fii_net):,.0f}Cr")
    if dii_net > 500:
        score += 10
        reasons.append(f"DII buying ₹{dii_net:,.0f}Cr")

    # 2. VIX  (India VIX ranges: <13 calm, 13-18 normal, 18-24 elevated, 24+ high fear)
    indices = snapshot.get("indices", {})
    vix = indices.get("INDIA VIX", {})
    vix_val = vix.get("last", 0) or 0
    if isinstance(vix_val, (int, float)):
        if vix_val < 13:
            score += 15
            reasons.append(f"Low VIX {vix_val:.1f} (calm)")
        elif vix_val < 18:
            pass  # Normal range — no bias shift
        elif vix_val < 24:
            score -= 10
            reasons.append(f"Elevated VIX {vix_val:.1f} (caution)")
        else:
            score -= 20
            reasons.append(f"High VIX {vix_val:.1f} (fear)")

    # 3. Breadth
    n50 = indices.get("NIFTY 50", {})
    try:
        adv = int(n50.get("advances", 0))
        dec = int(n50.get("declines", 0))
    except (ValueError, TypeError):
        adv, dec = 0, 0
    if adv + dec > 0:
        ratio = adv / (adv + dec)
        if ratio >= 0.6:
            score += 20
            reasons.append(f"Breadth {adv}:{dec} (bullish)")
        elif ratio <= 0.4:
            score -= 20
            reasons.append(f"Breadth {adv}:{dec} (bearish)")

    # 4. NIFTY 50 day trend  (strongest real-time signal)
    n50_pct = n50.get("pct", 0) or 0
    if isinstance(n50_pct, (int, float)):
        if n50_pct > 1.0:
            score += 20
            reasons.append(f"NIFTY +{n50_pct:.1f}% today")
        elif n50_pct > 0.3:
            score += 10
            reasons.append(f"NIFTY +{n50_pct:.1f}% today")
        elif n50_pct < -1.0:
            score -= 20
            reasons.append(f"NIFTY {n50_pct:.1f}% today")
        elif n50_pct < -0.3:
            score -= 10
            reasons.append(f"NIFTY {n50_pct:.1f}% today")

    # 5. Options PCR
    oc = snapshot.get("option_chain", {})
    nifty_oc = oc.get("NIFTY", {})
    pcr = nifty_oc.get("pcr_oi", 0) or 0
    if isinstance(pcr, (int, float)) and pcr > 0:
        if pcr > 1.2:
            score += 10
            reasons.append(f"PCR {pcr:.2f} (puts heavy → bullish)")
        elif pcr < 0.8:
            score -= 10
            reasons.append(f"PCR {pcr:.2f} (calls heavy → bearish)")

    # Clamp
    score = max(-100, min(100, score))
    if score > 20:
        direction = "BULLISH"
    elif score < -20:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return {"score": score, "direction": direction, "reasons": reasons}


# ─── Index / Stock / ETF Setup Generator ────────────────────────────────────

def _generate_setup(
    symbol: str,
    category: str,   # "Index", "Stock", "ETF"
    ohlc: Dict,       # {open, high, low, last/close, prev_close}
    volume: float,
    value_cr: float,
    pct: float,
    chg_30d: float,
    chg_365d: float,
    near_52h: float,
    near_52l: float,
    sector: str,
    sector_pct: float,
    bias: Dict,
    vix_val: float = 0.0,
    score_threshold: int = 15,
    macro_weight: float = 0.30,
    confidence_floor: int = 50,
    sector_blacklist: list = None,
) -> Optional[Dict]:
    """Generate a complete trade setup for one instrument."""
    # Skip blacklisted sectors
    if sector_blacklist and sector in sector_blacklist:
        return None

    h = ohlc.get("high", 0) or 0
    l = ohlc.get("low", 0) or 0
    c = ohlc.get("last", 0) or ohlc.get("close", 0) or 0
    if not all([h, l, c]):
        return None

    # Compute all pivots
    classic = _classic_pivots(h, l, c)
    fib = _fibonacci_pivots(h, l, c)
    cam = _camarilla_pivots(h, l, c)
    woodie = _woodie_pivots(h, l, c)
    cpr = _cpr(h, l, c)
    vwap = _estimate_vwap(volume, value_cr)

    all_pivots = {
        "Classic": classic,
        "Fibonacci": fib,
        "Camarilla": cam,
        "Woodie": woodie,
    }

    # Find confluence zones
    zones = _find_confluence_zones(all_pivots, c)

    # Nearest support and resistance
    supports = [z for z in zones if z["type"] == "Support"]
    resistances = [z for z in zones if z["type"] == "Resistance"]
    best_support = supports[0] if supports else None
    best_resist = resistances[0] if resistances else None

    # ── Trade direction logic ──
    # Combine market bias with individual stock factors
    stock_score = 0
    factors = []

    # Market bias contribution
    stock_score += bias["score"] * macro_weight

    # Momentum
    if isinstance(chg_30d, (int, float)):
        if chg_30d > 5:
            stock_score += 15
            factors.append(f"30d +{chg_30d:.0f}%")
        elif chg_30d < -5:
            stock_score -= 15
            factors.append(f"30d {chg_30d:.0f}%")

    # 52W position
    if isinstance(near_52h, (int, float)) and 0 < near_52h <= 3:
        stock_score += 10
        factors.append("Near 52W high")
    elif isinstance(near_52l, (int, float)) and 0 < near_52l <= 5:
        stock_score -= 5
        factors.append("Near 52W low")

    # Relative strength: stock vs sector
    if isinstance(pct, (int, float)) and isinstance(sector_pct, (int, float)):
        rs = pct - sector_pct
        if rs > 1.5:
            stock_score += 10
            factors.append(f"Outperforming sector by {rs:+.1f}%")
        elif rs < -1.5:
            stock_score -= 10
            factors.append(f"Underperforming sector by {rs:.1f}%")

    # Today's price action relative to pivot
    if c > classic["P"]:
        stock_score += 5
        factors.append("Trading above pivot")
    else:
        stock_score -= 5
        factors.append("Trading below pivot")

    # VWAP position
    if vwap > 0:
        if c > vwap:
            stock_score += 5
            factors.append("Above VWAP")
        else:
            stock_score -= 5
            factors.append("Below VWAP")

    # CPR width
    cpr_note = ""
    if cpr["width_pct"] < 0.3:
        cpr_note = "Narrow CPR → trending day expected"
    elif cpr["width_pct"] > 1.0:
        cpr_note = "Wide CPR → sideways/rangebound"

    # Direction
    if stock_score > score_threshold:
        direction = "LONG"
    elif stock_score < -score_threshold:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    # ── Entry / Target / Stop Loss ──
    # Trader rule: never chase a stock that has already moved >3% from pivot.
    # LONG: prefer entering within 1.5% of support — not at the top of a spike.
    # SHORT: prefer entering within 1.5% of resistance — not at the bottom of a dump.
    already_moved_far = abs(pct) > 3.5  # stock already ran hard today

    if direction == "LONG":
        if c >= classic["P"]:
            if already_moved_far:
                # Enter at next pullback to pivot (don't chase the spike)
                entry = round(classic["P"] * 1.002, 2)
            else:
                entry = round(c, 2)
            s1 = best_support["level"] if best_support else classic["S1"]
            stop_loss = round(min(s1, classic["P"] * 0.997), 2)
            target = best_resist["level"] if best_resist else classic["R1"]
            _risk = abs(entry - stop_loss) or 1
            if abs(target - entry) / _risk < 1.2:
                target = classic["R2"]
        else:
            # Price below pivot but LONG bias → wait for pivot reclaim
            entry = round(classic["P"] * 1.001, 2)
            stop_loss = best_support["level"] if best_support else classic["S1"]
            target = best_resist["level"] if best_resist else classic["R1"]
            _risk = abs(entry - stop_loss) or 1
            if abs(target - entry) / _risk < 1.2:
                target = classic["R2"]
    elif direction == "SHORT":
        if c <= classic["P"]:
            if already_moved_far:
                # Don't short at the bottom — wait for bounce to resistance
                entry = round(classic["P"] * 0.999, 2)
            else:
                bounce_entry = c + (classic["P"] - c) * 0.25
                r1 = best_resist["level"] if best_resist else classic["R1"]
                entry = round(min(bounce_entry, r1 * 0.999), 2)
            stop_loss = round(max(
                best_resist["level"] if best_resist else classic["R1"],
                classic["P"] * 1.002
            ), 2)
            target = best_support["level"] if best_support else classic["S1"]
            _risk = abs(entry - stop_loss) or 1
            if abs(target - entry) / _risk < 1.2:
                target = classic["S2"]
        else:
            # Price above pivot but SHORT bias → wait for pivot breakdown
            entry = round(classic["P"] * 0.999, 2)
            stop_loss = best_resist["level"] if best_resist else classic["R1"]
            target = best_support["level"] if best_support else classic["S1"]
            _risk = abs(entry - stop_loss) or 1
            if abs(target - entry) / _risk < 1.2:
                target = classic["S2"]
    else:
        entry = classic["P"]
        stop_loss = classic["S1"] if c >= classic["P"] else classic["R1"]
        target = classic["R1"] if c >= classic["P"] else classic["S1"]

    risk = abs(entry - stop_loss) if entry != stop_loss else 1
    reward = abs(target - entry) if target != entry else 1
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0

    # ── Confidence Score ──
    confidence_score, confidence_label, confidence_evidence = _stock_confidence_score(
        pct=pct, chg_30d=chg_30d, chg_365d=chg_365d, value_cr=value_cr,
        near_52h=near_52h, near_52l=near_52l, sector_pct=sector_pct,
        ltp=c, pivot=classic["P"], vwap=vwap,
        cpr_width_pct=cpr["width_pct"], direction=direction,
        rr_ratio=rr_ratio, bias_score=bias.get("score", 0),
        vix_val=vix_val,
    )

    # Skip setups that don't meet the confidence floor (except for indices)
    if category != "Index" and direction != "NEUTRAL" and confidence_score < confidence_floor:
        return None

    # ── Position sizing ──
    pos_size = _position_sizing(vix_val, rr_ratio, confidence_score)

    return {
        "symbol": symbol,
        "category": category,
        "sector": sector,
        "ltp": c,
        "open": ohlc.get("open", 0),
        "high": h,
        "low": l,
        "prev_close": ohlc.get("prev_close", 0),
        "pct": pct,
        "volume": volume,
        "value_cr": value_cr,
        # Pivots
        "classic_pivot": classic["P"],
        "classic_r1": classic["R1"],
        "classic_r2": classic["R2"],
        "classic_s1": classic["S1"],
        "classic_s2": classic["S2"],
        "fib_r1": fib["R1"],
        "fib_s1": fib["S1"],
        "cam_r3": cam["R3"],
        "cam_s3": cam["S3"],
        # CPR
        "cpr_tc": cpr["tc"],
        "cpr_bc": cpr["bc"],
        "cpr_width_pct": cpr["width_pct"],
        "cpr_note": cpr_note,
        # VWAP
        "vwap": vwap,
        # Confluence
        "zones": zones[:8],
        "best_support": best_support,
        "best_resistance": best_resist,
        # Trade setup
        "direction": direction,
        "direction_score": round(stock_score, 1),
        "factors": factors,
        "entry": entry,
        "target": target,
        "stop_loss": stop_loss,
        "risk_reward": rr_ratio,
        # Confidence system
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "confidence_evidence": confidence_evidence,
        "position_size": pos_size,
        "already_moved_far": already_moved_far,
    }


# ─── Public API ──────────────────────────────────────────────────────────────

def generate_intraday_setups(snapshot: Dict) -> Dict:
    """
    Analyse the full snapshot and produce intraday trade setups for:
      - Key indices (NIFTY 50, BANK NIFTY)
      - Top 3 stocks per sector (by traded value)
      - Commodity ETFs
      - On-Watch: near-threshold setups when main setups are sparse

    Returns:
        {
            "bias": {...},
            "index_setups": [...],
            "stock_setups": [...],
            "etf_setups": [...],
            "on_watch": [...],   # near-threshold setups to monitor
            "generated_at": "...",
        }
    """
    params = _load_trading_params()
    score_threshold = int(params["direction_score_threshold"])
    macro_weight    = float(params["macro_bias_weight"])
    rs_min          = float(params["momentum_rs_min_pct"])
    val_min         = float(params["momentum_val_cr_min"])

    bias = _market_bias(snapshot)
    indices = snapshot.get("indices", {})
    sectors = snapshot.get("sectors", {})
    commodities = snapshot.get("commodities", {})

    # Extract VIX absolute level for confidence scoring
    vix_val = float(indices.get("INDIA VIX", {}).get("last", 0) or 0)

    # Sector blacklist and confidence floor from learned params
    sector_blacklist = params.get("sector_blacklist", [])
    confidence_floor = int(params.get("confidence_floor", 50))

    index_setups = []
    stock_setups = []
    etf_setups = []

    # ── Index setups ──
    for idx_name in ("NIFTY 50", "NIFTY BANK"):
        data = indices.get(idx_name, {})
        if not data:
            continue
        setup = _generate_setup(
            symbol=idx_name,
            category="Index",
            ohlc=data,
            volume=0,
            value_cr=0,
            pct=data.get("pct", 0),
            chg_30d=0,
            chg_365d=0,
            near_52h=0,
            near_52l=0,
            sector="INDEX",
            sector_pct=data.get("pct", 0),
            bias=bias,
            vix_val=vix_val,
            score_threshold=score_threshold,
            macro_weight=macro_weight,
            confidence_floor=0,   # always show index levels
            sector_blacklist=[],
        )
        if setup:
            index_setups.append(setup)

    # ── Stock setups: top 3 per sector by value traded ──
    seen_symbols = set()
    for sect_name, sdata in sectors.items():
        stocks = sdata.get("stocks", [])
        sector_pct = sdata.get("index_pct", 0) or 0
        disp_sector = _sector_display(sect_name)
        # Already sorted by value_cr desc in most cases; ensure sort
        ranked = sorted(stocks, key=lambda s: s.get("value_cr", 0) or 0, reverse=True)
        for s in ranked[:3]:
            sym = s.get("symbol", "")
            if sym in seen_symbols or not sym:
                continue
            seen_symbols.add(sym)
            setup = _generate_setup(
                symbol=sym,
                category="Stock",
                ohlc=s,
                volume=s.get("volume", 0) or 0,
                value_cr=s.get("value_cr", 0) or 0,
                pct=s.get("pct", 0) or 0,
                chg_30d=s.get("chg_30d", 0) or 0,
                chg_365d=s.get("chg_365d", 0) or 0,
                near_52h=s.get("near_52h", 0) or 0,
                near_52l=s.get("near_52l", 0) or 0,
                sector=disp_sector,
                sector_pct=sector_pct,
                bias=bias,
                vix_val=vix_val,
                score_threshold=score_threshold,
                macro_weight=macro_weight,
                confidence_floor=confidence_floor,
                sector_blacklist=sector_blacklist,
            )
            if setup:
                stock_setups.append(setup)

    # Sort stock setups: highest confidence first, then strongest directional score
    stock_setups.sort(
        key=lambda s: (s.get("confidence_score", 0), abs(s["direction_score"])),
        reverse=True
    )

    # ── ETF setups ──
    for etf_sym, edata in commodities.items():
        if not isinstance(edata, dict):
            continue
        # Skip LIQUIDBEES (money-market, no intraday opportunity)
        if etf_sym == "LIQUIDBEES":
            continue
        setup = _generate_setup(
            symbol=etf_sym,
            category="ETF",
            ohlc={
                "high": edata.get("high", 0),
                "low": edata.get("low", 0),
                "last": edata.get("last", 0),
                "open": edata.get("open", 0),
                "prev_close": edata.get("prev_close", 0),
            },
            volume=0,
            value_cr=0,
            pct=edata.get("pct", 0) or 0,
            chg_30d=0,
            chg_365d=0,
            near_52h=0,
            near_52l=0,
            sector="COMMODITY",
            sector_pct=0,
            bias=bias,
            vix_val=vix_val,
            score_threshold=score_threshold,
            macro_weight=macro_weight,
            confidence_floor=0,   # always show ETFs
            sector_blacklist=[],
        )
        if setup:
            etf_setups.append(setup)

    # ── On-Watch setups: collect near-threshold if main setups are sparse ──
    # Run again at lower confidence floor (confidence_floor - 15) to populate
    # an "On Watch" section when main actionable setups are very few
    on_watch = []
    main_longs = [s for s in stock_setups if s["direction"] == "LONG"]
    main_shorts = [s for s in stock_setups if s["direction"] == "SHORT"]
    if len(main_longs) < 2 or len(main_shorts) < 2:
        watch_floor = max(30, confidence_floor - 15)
        watch_seen = {s["symbol"] for s in stock_setups}
        for sect_name, sdata in sectors.items():
            sect_pct = sdata.get("index_pct", 0) or 0
            disp_sector = _sector_display(sect_name)
            if disp_sector in sector_blacklist:
                continue
            ranked = sorted(sdata.get("stocks", []), key=lambda s: s.get("value_cr", 0) or 0, reverse=True)
            for s in ranked[:5]:  # look at top 5 per sector for watch
                sym = s.get("symbol", "")
                if sym in watch_seen or not sym:
                    continue
                setup = _generate_setup(
                    symbol=sym, category="Stock", ohlc=s,
                    volume=s.get("volume", 0) or 0,
                    value_cr=s.get("value_cr", 0) or 0,
                    pct=s.get("pct", 0) or 0,
                    chg_30d=s.get("chg_30d", 0) or 0,
                    chg_365d=s.get("chg_365d", 0) or 0,
                    near_52h=s.get("near_52h", 0) or 0,
                    near_52l=s.get("near_52l", 0) or 0,
                    sector=disp_sector, sector_pct=sect_pct,
                    bias=bias, vix_val=vix_val,
                    score_threshold=score_threshold,
                    macro_weight=macro_weight,
                    confidence_floor=watch_floor,
                    sector_blacklist=sector_blacklist,
                )
                if setup and setup["direction"] != "NEUTRAL" and setup["risk_reward"] >= 1.0:
                    watch_seen.add(sym)
                    on_watch.append(setup)
        on_watch.sort(key=lambda s: s.get("confidence_score", 0), reverse=True)
        on_watch = on_watch[:4]  # max 4 on-watch picks

    return {
        "bias": bias,
        "index_setups": index_setups,
        "stock_setups": stock_setups[:20],  # Top 20 by confidence
        "etf_setups": etf_setups,
        "on_watch": on_watch,
        "momentum_alerts": _find_momentum_stocks(
            snapshot, bias,
            rs_min=rs_min, val_min=val_min,
            vix_val=vix_val,
            confidence_floor=confidence_floor,
            sector_blacklist=sector_blacklist,
        ),
        "generated_at": datetime.now().isoformat(),
    }


# ─── Momentum Scanner ────────────────────────────────────────────────────────

def _find_momentum_stocks(snapshot: Dict, bias: Dict,
                          rs_min: float = 1.5, val_min: float = 500,
                          vix_val: float = 0.0,
                          confidence_floor: int = 50,
                          sector_blacklist: list = None) -> List[Dict]:
    """
    Scan ALL stocks for notable intraday momentum / reversal setups.

    Looks for:
      1. Outperformers: up 2%+ today while market is down (hidden strength)
      2. High-volume movers: value_cr > 500 Cr with >3% absolute move
      3. Near 52W high breakouts with positive momentum
      4. Near 52W low potential bounces (requires green day: pct > 1)
      5. Relative strength leaders with substantial volume
    """
    sector_blacklist = sector_blacklist or []
    sectors = snapshot.get("sectors", {})
    nifty_pct = snapshot.get("indices", {}).get("NIFTY 50", {}).get("pct", 0) or 0
    results = []
    seen = set()

    for sect_name, sdata in sectors.items():
        sector_pct = sdata.get("index_pct", 0) or 0
        disp = _sector_display(sect_name)

        # Skip blacklisted sectors
        if disp in sector_blacklist:
            continue

        for s in sdata.get("stocks", []):
            sym = s.get("symbol", "")
            if sym in seen or not sym:
                continue
            ltp = s.get("last", 0) or 0
            pct = s.get("pct", 0) or 0
            val = s.get("value_cr", 0) or 0
            near_52h = s.get("near_52h", 999) or 999
            near_52l = s.get("near_52l", 999) or 999
            chg_30d = s.get("chg_30d", 0) or 0
            chg_365d = s.get("chg_365d", 0) or 0
            rs = pct - sector_pct

            triggers = []

            # 1. Outperformer in a down market (hidden strength — most reliable)
            if nifty_pct < -0.5 and pct > rs_min:
                triggers.append(f"Outperformer: +{pct:.1f}% vs index {nifty_pct:.1f}%")

            # 2. High-volume large mover (either direction, but with clean setup)
            if val > val_min and abs(pct) > 3:
                triggers.append(f"High vol mover: {pct:+.1f}% on ₹{val:,.0f}Cr")

            # 3. 52W high breakout attempt
            if isinstance(near_52h, (int, float)) and 0 < near_52h <= 1.5 and pct > 0:
                triggers.append(f"52W high breakout zone ({near_52h:.1f}% to high)")

            # 4. Reversal from 52W low (needs strong green day)
            if isinstance(near_52l, (int, float)) and 0 < near_52l <= 2 and pct > 2:
                triggers.append(f"Bounce from 52W low ({near_52l:.1f}% above low)")

            # 5. Relative strength leader in sector (RS > 2%)
            if rs > 2 and val > 100:
                triggers.append(f"RS vs sector: {rs:+.1f}%")

            if not triggers:
                continue

            seen.add(sym)

            # Quick entry/exit using classic pivots
            h = s.get("high", ltp * 1.02) or ltp * 1.02
            lo = s.get("low", ltp * 0.98) or ltp * 0.98
            if h == lo:
                continue

            cl = _classic_pivots(h, lo, ltp)
            already_moved_far = abs(pct) > 3.5
            if pct > 0:
                direction = "LONG"
                if already_moved_far:
                    entry = round(cl["P"] * 1.001, 2)  # wait for pullback
                else:
                    entry = round(ltp, 2)
                stop_loss = round(min(cl["S1"], ltp * 0.985), 2)
                target = round(max(cl["R1"], ltp * 1.015), 2)
                # extend target if R:R < 1.2
                _risk = abs(entry - stop_loss) or 1
                if abs(target - entry) / _risk < 1.2:
                    target = round(max(cl["R2"], ltp * 1.025), 2)
            else:
                direction = "SHORT"
                if already_moved_far:
                    entry = round(cl["P"] * 0.999, 2)  # wait for bounce
                else:
                    entry = round(ltp + (cl["P"] - ltp) * 0.2, 2)
                stop_loss = round(max(cl["R1"], ltp * 1.015), 2)
                target = round(min(cl["S1"], ltp * 0.985), 2)
                _risk = abs(entry - stop_loss) or 1
                if abs(target - entry) / _risk < 1.2:
                    target = round(min(cl["S2"], ltp * 0.975), 2)

            risk = abs(entry - stop_loss)
            reward = abs(target - entry)
            rr = round(reward / risk, 2) if risk > 0 else 0

            # Confidence scoring for momentum picks
            conf_score, conf_label, conf_ev = _stock_confidence_score(
                pct=pct, chg_30d=chg_30d, chg_365d=chg_365d, value_cr=val,
                near_52h=near_52h, near_52l=near_52l, sector_pct=sector_pct,
                ltp=ltp, pivot=cl["P"], vwap=0,
                cpr_width_pct=1.0,  # unknown for momentum picks
                direction=direction, rr_ratio=rr,
                bias_score=bias.get("score", 0), vix_val=vix_val,
            )

            # Skip low-confidence momentum picks
            if conf_score < confidence_floor:
                continue

            results.append({
                "symbol": sym,
                "sector": disp,
                "ltp": ltp,
                "pct": pct,
                "value_cr": val,
                "near_52h": near_52h,
                "near_52l": near_52l,
                "rs_vs_sector": round(rs, 2),
                "direction": direction,
                "entry": entry,
                "target": target,
                "stop_loss": stop_loss,
                "risk_reward": rr,
                "triggers": triggers,
                "trigger_type": triggers[0].split(":")[0] if triggers else "Unknown",
                "confidence_score": conf_score,
                "confidence_label": conf_label,
                "confidence_evidence": conf_ev,
                "position_size": _position_sizing(vix_val, rr, conf_score),
                "pivot": cl["P"],
                "s1": cl["S1"],
                "r1": cl["R1"],
                "already_moved_far": already_moved_far,
            })

    # Sort: by confidence score first, then momentum strength
    results.sort(key=lambda x: (x["confidence_score"], abs(x["pct"])), reverse=True)
    return results[:15]


# ─── Telegram Formatter ─────────────────────────────────────────────────────

def _strength_emoji(s: str) -> str:
    if s == "Strong":
        return "🔥"
    if s == "Moderate":
        return "⚡"
    return "💡"


def _dir_emoji(d: str) -> str:
    if d == "LONG":
        return "🟢"
    if d == "SHORT":
        return "🔴"
    return "⚪"


def _nse_link(symbol: str) -> str:
    """Clickable NSE quote link."""
    from urllib.parse import quote
    clean = symbol.replace("NIFTY ", "").replace(" ", "%20")
    url = f"https://www.nseindia.com/get-quotes/equity?symbol={quote(symbol, safe='')}"
    return f'<a href="{url}">{symbol}</a>'


def format_trading_msg(setups: Dict) -> str:
    """Format intraday trading setups as a Telegram message."""
    if not setups:
        return ""
    L = []

    bias = setups.get("bias", {})
    direction = bias.get("direction", "NEUTRAL")
    score = bias.get("score", 0)
    reasons = bias.get("reasons", [])

    dir_em = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}.get(direction, "⚪")
    L.append(f"<b>📐 Intraday Trading Setups</b>")
    L.append("")
    L.append(f"{dir_em} <b>Market Bias: {direction}</b> (score {score:+d}/100)")
    for r in reasons[:4]:
        L.append(f"  • {r}")
    L.append("")

    # ── Index levels ──
    idx_setups = setups.get("index_setups", [])
    if idx_setups:
        L.append("<b>━━ Index Levels ━━</b>")
        for s in idx_setups:
            _append_setup_block(L, s, show_link=False)
        L.append("")

    # ── Top Stock Setups (only actionable R:R >= 1.0 AND confidence >= floor) ──
    stk = setups.get("stock_setups", [])
    if stk:
        longs = [s for s in stk if s["direction"] == "LONG" and s["risk_reward"] >= 1.0][:5]
        shorts = [s for s in stk if s["direction"] == "SHORT" and s["risk_reward"] >= 1.0][:5]

        if longs:
            L.append(f"<b>━━ 🟢 LONG Setups ({len(longs)}) ━━</b>")
            for s in longs:
                _append_compact_line(L, s)
            L.append("")

        if shorts:
            L.append(f"<b>━━ 🔴 SHORT Setups ({len(shorts)}) ━━</b>")
            for s in shorts:
                _append_compact_line(L, s)
            L.append("")

    # ── ETF setups ──
    etf = setups.get("etf_setups", [])
    if etf:
        L.append("<b>━━ Commodity ETFs ━━</b>")
        for s in etf:
            de = _dir_emoji(s["direction"])
            L.append(f"{de} <b>{s['symbol']}</b> ₹{s['ltp']:,.2f} ({s['pct']:+.2f}%)")
            L.append(f"  Pivot {s['classic_pivot']:,.2f} | S1 {s['classic_s1']:,.2f} | R1 {s['classic_r1']:,.2f}")
            if s["direction"] != "NEUTRAL":
                L.append(f"  ▶ Entry {s['entry']:,.2f} | Target {s['target']:,.2f} | SL {s['stop_loss']:,.2f}")
        L.append("")

    # ── On Watch (near-threshold setups to monitor) ──
    on_watch = setups.get("on_watch", [])
    if on_watch:
        L.append("<b>━━ 👁 On Watch (Near Threshold) ━━</b>")
        L.append("<i>Below confidence floor — monitor for entry trigger</i>")
        L.append("")
        for s in on_watch:
            de = _dir_emoji(s["direction"])
            link = _nse_link(s["symbol"])
            conf = s.get("confidence_label", "")
            L.append(f"{de} {link} ₹{s['ltp']:,.1f} ({s['pct']:+.1f}%) <i>{s['sector']}</i>  {conf}")
            L.append(f"  Watch entry: {s['entry']:,.1f} | Target: {s['target']:,.1f} | SL: {s['stop_loss']:,.1f} | R:R {s['risk_reward']:.1f}")
            if s.get("confidence_evidence"):
                L.append(f"  <i>{' · '.join(s['confidence_evidence'][:2])}</i>")
        L.append("")

    # ── Momentum Alerts ──
    momentum = setups.get("momentum_alerts", [])
    if momentum:
        L.append("<b>━━ ⚡ Momentum Alerts ━━</b>")
        L.append("<i>Dynamic picks filtered by confidence score</i>")
        L.append("")
        shown = [s for s in momentum if s["risk_reward"] >= 1.0][:6]
        for s in shown:
            de = _dir_emoji(s["direction"])
            link = _nse_link(s["symbol"])
            conf = s.get("confidence_label", "")
            warn = " ⚠️ wait for pullback" if s.get("already_moved_far") else ""
            L.append(f"{de} {link} ₹{s['ltp']:,.1f} ({s['pct']:+.1f}%) <i>{s['sector']}</i>  {conf}")
            L.append(f"  📍 {s['triggers'][0]}{warn}")
            L.append(
                f"  Entry {s['entry']:,.1f} → Target {s['target']:,.1f} | "
                f"SL {s['stop_loss']:,.1f} | R:R {s['risk_reward']:.1f}"
            )
            if s.get("position_size"):
                L.append(f"  📊 {s['position_size']}")
        L.append("")

    if not any([idx_setups,
                [s for s in stk if s["risk_reward"] >= 1.0] if stk else [],
                on_watch, momentum, etf]):
        L.append("<i>No high-confidence setups today — market too uncertain. Check On Watch section.</i>")
        L.append("")

    L.append("<i>⚠ Levels are mathematical projections, not guaranteed outcomes.</i>")
    L.append(f"<i>Generated: {datetime.now().strftime('%I:%M %p IST')}</i>")
    return "\n".join(L)


def _append_setup_block(L: list, s: Dict, show_link: bool = True):
    """Append a detailed setup block for an index."""
    de = _dir_emoji(s["direction"])
    name = _nse_link(s["symbol"]) if show_link else f"<b>{s['symbol']}</b>"
    L.append(f"{de} {name}  ₹{s['ltp']:,.1f} ({s['pct']:+.1f}%)")

    # CPR
    cpr_note = s.get("cpr_note", "")
    L.append(f"  CPR: {s['cpr_bc']:,.1f} – {s['cpr_tc']:,.1f} ({s['cpr_width_pct']:.2f}%)")
    if cpr_note:
        L.append(f"  <i>{cpr_note}</i>")

    # Key levels
    L.append(f"  Pivot {s['classic_pivot']:,.1f} | VWAP {s['vwap']:,.1f}" if s["vwap"] else f"  Pivot {s['classic_pivot']:,.1f}")

    # Confluence zones (top 4)
    zones = s.get("zones", [])
    supports = [z for z in zones if z["type"] == "Support"][:2]
    resists = [z for z in zones if z["type"] == "Resistance"][:2]

    sup_strs = [f"{_strength_emoji(z['strength'])}{z['level']:,.1f}" for z in supports]
    res_strs = [f"{_strength_emoji(z['strength'])}{z['level']:,.1f}" for z in resists]
    L.append(f"  Support: {' → '.join(sup_strs) if sup_strs else '—'}")
    L.append(f"  Resistance: {' → '.join(res_strs) if res_strs else '—'}")

    # Trade
    if s["direction"] != "NEUTRAL":
        L.append(f"  ▶ Entry {s['entry']:,.1f} | Target {s['target']:,.1f} | SL {s['stop_loss']:,.1f}  (R:R {s['risk_reward']:.1f})")
    L.append("")


def _append_compact_line(L: list, s: Dict):
    """Compact setup block for a stock."""
    de = _dir_emoji(s["direction"])
    link = _nse_link(s["symbol"])
    rr = s["risk_reward"]
    conf = s.get("confidence_label", "")
    warn = " ⚠️ <i>already moved far — wait for pullback</i>" if s.get("already_moved_far") else ""
    L.append(
        f"{de} {link} ₹{s['ltp']:,.1f} ({s['pct']:+.1f}%) "
        f"<i>{s['sector']}</i>  {conf}"
    )
    L.append(
        f"  Entry {s['entry']:,.1f} → Target {s['target']:,.1f} | "
        f"SL {s['stop_loss']:,.1f} | R:R {rr:.1f}"
    )
    if s.get("position_size"):
        L.append(f"  📊 {s['position_size']}{warn}")
    elif warn:
        L.append(f"  {warn.strip()}")
    # Key factors (top 2)
    if s.get("confidence_evidence"):
        L.append(f"  <i>{'  ·  '.join(s['confidence_evidence'][:2])}</i>")
    elif s.get("factors"):
        L.append(f"  <i>{' · '.join(s['factors'][:3])}</i>")
