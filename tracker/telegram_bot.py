"""
Telegram Bot - Kid-Friendly Market Intelligence Messages
=========================================================

Formats complex market data into simple, emoji-rich messages
that even beginners can understand at a glance.

Message types:
1. FII/DII + Indices + Delta
2. Sector Heatmap + Top Movers
3. Options PCR Analysis
4. Commodities + Forex
5. Corporate Actions + Insider Trading
6. Pre-Open Analysis
7. Delta Alert (changes between snapshots)
"""

import logging
import os
import re
import html
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import requests

from . import config

logger = logging.getLogger(__name__)

# Telegram max message length
MAX_MSG_LEN = 4000


def _cr(val: float) -> str:
    """Format value in crores with sign."""
    if val >= 0:
        return f"+₹{abs(val):,.0f} Cr"
    return f"-₹{abs(val):,.0f} Cr"


def _pct(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _extract_dividend_amount(subject: str) -> float:
    """Extract dividend amount from subject string.

    Handles NSE and BSE format variations:
      'Interim Dividend - Rs 10 Per Share'        -> 10.0
      'Final Dividend - Re 1.50 Per Share'         -> 1.50
      'Dividend Rs. 5.25 per share'                -> 5.25
      'Dividend - Rs5/- per share'                 -> 5.0
      'Dividend - \u20b910 per share'                   -> 10.0
      'Dividend - INR 3.50 per share'              -> 3.50
      'Dividend @ Rs 8 per equity share'           -> 8.0
      'Dividend 2.50 per share'                    -> 2.50 (plain number)
    """
    if not subject:
        return 0.0

    amounts = _extract_dividend_amounts(subject)
    if not amounts:
        return 0.0
    return round(sum(amounts), 4)


def _extract_dividend_amounts(subject: str) -> List[float]:
    """Extract one or more dividend amounts from subject text.

    Supports multi-dividend lines such as:
    "Final dividend of Rs 20 per share and Special dividend of Rs 7.50 per share"
    → [20.0, 7.5]
    """
    if not subject:
        return []

    # Prefer strict "per share" patterns first to avoid unrelated numbers.
    strict_patterns = [
        r'(?:Rs|Re)\.?\s*([\d,]+(?:\.\d+)?)\s*(?:/-)?\s*per\s+(?:equity\s+)?share',
        r'\u20b9\s*([\d,]+(?:\.\d+)?)\s*per\s+(?:equity\s+)?share',
        r'INR\s*([\d,]+(?:\.\d+)?)\s*per\s+(?:equity\s+)?share',
        r'@\s*(?:Rs\.?\s*)?([\d,]+(?:\.\d+)?)\s*per\s+(?:equity\s+)?share',
    ]

    out: List[float] = []
    for pat in strict_patterns:
        for m in re.finditer(pat, subject, re.IGNORECASE):
            try:
                v = float(m.group(1).replace(',', ''))
            except (ValueError, IndexError, AttributeError):
                continue
            if 0 < v < 100_000:
                out.append(v)

    # Fallback: no strict match → retain legacy single-value behavior.
    if not out:
        fallback_patterns = [
            r'(?:Rs|Re)\.?\s*([\d,]+(?:\.\d+)?)',
            r'\u20b9\s*([\d,]+(?:\.\d+)?)',
            r'INR\s*([\d,]+(?:\.\d+)?)',
            r'([\d,]+(?:\.\d+)?)\s*per\s+(?:equity\s+|equity\s+share|share)',
        ]
        for pat in fallback_patterns:
            m = re.search(pat, subject, re.IGNORECASE)
            if not m:
                continue
            try:
                v = float(m.group(1).replace(',', ''))
            except (ValueError, IndexError, AttributeError):
                continue
            if 0 < v < 100_000:
                out = [v]
                break

    # De-dup close duplicates while preserving order.
    unique: List[float] = []
    for v in out:
        if not any(abs(v - u) < 1e-6 for u in unique):
            unique.append(v)
    return unique


def _parse_action_date(date_str: str):
    """Parse NSE/BSE corporate action dates from known formats."""
    if not date_str or date_str == "N/A":
        return None
    ds = str(date_str).strip()
    for fmt in (
        "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
        "%d %b %Y", "%d %B %Y", "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(ds, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _extract_buyback_price(subject: str) -> float:
    """Extract buyback offer price from subject like 'Buy Back @ Rs 1450 Per Share'."""
    import re as _re
    patterns = [
        r'@\s*Rs\.?\s*([\d,]+(?:\.\d+)?)',
        r'at\s+(?:not\s+exceeding\s+)?Rs\.?\s*([\d,]+(?:\.\d+)?)',
        r'price\s+of\s+Rs\.?\s*([\d,]+(?:\.\d+)?)',
        r'Rs\.?\s*([\d,]+(?:\.\d+)?)\s*per\s+(?:equity\s+)?share',
    ]
    for p in patterns:
        m = _re.search(p, subject, _re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except (ValueError, TypeError):
                continue
    return 0.0


def _action_category(subject: str) -> str:
    """Classify corporate action subject into a short category label."""
    s = subject.lower()
    if any(k in s for k in ("dividend", "interim div", "final div")):
        return "dividend"
    if any(k in s for k in ("bonus", "bonus issue")):
        return "bonus"
    if any(k in s for k in ("split", "sub-division", "subdivision")):
        return "split"
    if any(k in s for k in ("buyback", "buy back", "buy-back")):
        return "buyback"
    if any(k in s for k in ("rights issue", "rights entitlement")):
        return "rights"
    if any(k in s for k in ("amalgamation", "merger", "scheme of arrangement")):
        return "merger"
    if any(k in s for k in ("demerger", "de-merger", "spin-off")):
        return "demerger"
    if "interest" in s:
        return "interest"
    if any(k in s for k in ("agm", "annual general", "egm", "extraordinary")):
        return "agm"
    return "other"


def _div_type_tag(subject: str) -> str:
    """Extract dividend type from subject: Interim / Final / Special / Dividend."""
    s = subject.lower()
    if "interim" in s:
        return "Interim"
    if "final" in s:
        return "Final"
    if "special" in s:
        return "Special"
    return "Div"


def _yield_indicator(yield_pct: float) -> str:
    """Return emoji quality indicator for dividend yield."""
    if yield_pct >= 3.0:
        return "🟢"   # Excellent
    if yield_pct >= 1.5:
        return "🟡"   # Good
    if yield_pct >= 0.5:
        return "⚪"   # Average
    return "🔸"        # Low


def _build_annual_dividend_totals(data_dir: str) -> dict:
    """Scan ALL stored snapshots to sum dividends from the PREVIOUS complete year.

    Ann.Yield must use prior-year data (FY2025) to be meaningfully different from
    Yield (which uses the upcoming dividend). Never mixes in current-year data.

    Returns {symbol: {"total": float, "label": str}} for FY{prev_year} only.
    Returns {} if prior year has no data (shows no Ann.Yield in that case).
    Deduplication by (symbol, ex_date) — each payout counted once.
    """
    import json as _json
    from pathlib import Path as _Path

    def _parse_ex_year(date_str: str):
        """Return the 4-digit year from an ex_date string, or None."""
        if not date_str:
            return None
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).year
            except (ValueError, TypeError):
                continue
        return None

    today     = datetime.now()
    prev_year = today.year - 1
    snap_dir  = _Path(data_dir) / "snapshots"
    if not snap_dir.exists():
        return {}

    seen: set = set()
    prev_data: dict = {}  # Only collect {symbol: total_divs} for prev_year

    for sf in snap_dir.glob("snapshot_*.json"):
        try:
            data = _json.loads(sf.read_text(encoding="utf-8"))
            for a in data.get("corporate_actions") or []:
                if "dividend" not in a.get("subject", "").lower():
                    continue
                sym     = a.get("symbol", "")
                ex_date = a.get("ex_date", "")
                if not sym or not ex_date:
                    continue
                key = (sym, ex_date)
                if key in seen:
                    continue
                ex_year = _parse_ex_year(ex_date)
                if ex_year != prev_year:  # Only collect previous year
                    continue
                seen.add(key)
                div = _extract_dividend_amount(a.get("subject", ""))
                if div > 0:
                    prev_data[sym] = prev_data.get(sym, 0.0) + div
        except Exception:
            continue

    # Return FY{prev_year} data only; empty if no prior-year dividends exist
    return {sym: {"total": total, "label": f"FY{prev_year}"}
            for sym, total in prev_data.items()}


def _fetch_prior_year_dividend_total_online(symbol: str, year: int) -> float:
    """Fetch prior-year dividend total from Yahoo chart events as fallback.

    Tries NSE ticker first (<symbol>.NS), then BSE ticker (<symbol>.BO).
    Returns 0.0 when unavailable so local data remains the primary source.
    """
    if not symbol or year < 2000:
        return 0.0

    period1 = int(datetime(year, 1, 1).timestamp())
    period2 = int(datetime(year + 1, 1, 1).timestamp())
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }

    for suffix in (".NS", ".BO"):
        ticker = f"{symbol}{suffix}"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            resp = requests.get(
                url,
                params={
                    "period1": period1,
                    "period2": period2,
                    "interval": "1d",
                    "events": "div",
                    "includePrePost": "false",
                },
                headers=headers,
                timeout=2,
            )
            if resp.status_code != 200:
                continue

            payload = resp.json() or {}
            result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
            events = (result.get("events") or {}).get("dividends") or {}
            total = 0.0
            for evt in events.values():
                try:
                    amt = float((evt or {}).get("amount") or 0)
                    if amt > 0:
                        total += amt
                except (TypeError, ValueError):
                    continue
            if total > 0:
                return round(total, 4)
        except Exception:
            continue

    return 0.0


def _fill_missing_annual_totals_online(symbols: List[str], annual_totals: dict) -> dict:
    """Fill missing symbols in annual totals using online fallback (Yahoo)."""
    out = dict(annual_totals or {})
    prev_year = datetime.now().year - 1
    started_at = datetime.now()

    # Keep fallback lightweight to avoid delaying message delivery.
    unique_symbols: List[str] = []
    seen: set = set()
    for s in symbols:
        if not s or s in seen:
            continue
        seen.add(s)
        unique_symbols.append(s)

    for sym in unique_symbols[:6]:
        if (datetime.now() - started_at).total_seconds() > 10:
            break
        if not sym or sym in out:
            continue
        try:
            total = _fetch_prior_year_dividend_total_online(sym, prev_year)
            if total > 0:
                out[sym] = {"total": total, "label": f"FY{prev_year}"}
        except Exception:
            continue
    return out


def _emoji_pct(val: float) -> str:
    if val >= 2:
        return "🟢🟢"
    elif val >= 0.5:
        return "🟢"
    elif val > -0.5:
        return "⚪"
    elif val > -2:
        return "🔴"
    else:
        return "🔴🔴"


def _format_prev_time(timestamp_str: str) -> str:
    """Format ISO timestamp to readable time like (9:00 AM)."""
    if not timestamp_str:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        if os.name != "nt":
            return f" ({dt.strftime('%-I:%M %p')})"
        else:
            return f" ({dt.strftime('%I:%M %p').lstrip('0')})"
    except:
        return ""


def _vol(val: float) -> str:
    """Format volume in compact form (M for millions, K for thousands)."""
    if val >= 1e7:
        return f"{val / 1e7:.1f}Cr"
    elif val >= 1e6:
        return f"{val / 1e6:.1f}M"
    elif val >= 1e3:
        return f"{val / 1e3:.0f}K"
    else:
        return f"{int(val)}"


def _52w_position(current: float, low: float, high: float) -> str:
    """Calculate where current price sits in 52-week range.
    Returns percentage string like '85%' (85% from low to high).
    """
    if high == low or high == 0:
        return "N/A"
    position = ((current - low) / (high - low)) * 100
    return f"{position:.0f}%"


def _52w_emoji(current: float, low: float, high: float) -> str:
    """Emoji indicator for 52-week position."""
    if high == low or high == 0:
        return "⚪"
    position = ((current - low) / (high - low)) * 100
    if position >= 95:
        return "🔥"  # Near 52W high
    elif position >= 80:
        return "🟢"  # Strong zone
    elif position <= 5:
        return "💎"  # Near 52W low (potential value)
    elif position <= 20:
        return "🔵"  # Low zone
    else:
        return "⚪"  # Mid-range


# ══════════════════════════════════════════════════════════════════════════════
#  SLOT-AWARE & DEDUP HELPERS
# ══════════════════════════════════════════════════════════════════════════════

NSE_QUOTE_URL = "https://www.nseindia.com/get-quotes/equity?symbol="
_PREMARKET_SLOTS = {'09:00', '09:08'}
_EVENING_SLOT = '21:00'
_WATCHLIST_BUILD_SLOTS = {'09:15', '09:30', '11:00'}


def _nse_link(symbol: str, text: str = None) -> str:
    """Clickable NSE link for a stock symbol."""
    from urllib.parse import quote
    label = html.escape(str(text or symbol), quote=False)
    return f'<a href="{NSE_QUOTE_URL}{quote(symbol)}">{label}</a>'


# Sector display name map (full NSE name → compact readable label)
_SECTOR_DISPLAY = {
    "NIFTY 50":                  "Nifty 50",
    "NIFTY BANK":                "Bank",
    "NIFTY NEXT 50":             "Next 50",
    "NIFTY IT":                  "IT",
    "NIFTY AUTO":                "Auto",
    "NIFTY PHARMA":              "Pharma",
    "NIFTY METAL":               "Metal",
    "NIFTY ENERGY":              "Energy",
    "NIFTY FMCG":                "FMCG",
    "NIFTY REALTY":              "Realty",
    "NIFTY FINANCIAL SERVICES":  "Fin Svc",
    "NIFTY PSU BANK":            "PSU Bank",
    "NIFTY INDIA DEFENCE":       "Defence",
    "NIFTY OIL & GAS":           "Oil & Gas",
    "NIFTY COMMODITIES":         "Commod.",
    "NIFTY MIDCAP 50":           "Midcap 50",
    "NIFTY SMALLCAP 50":         "Smallcap 50",
}


def _sector_display(name: str) -> str:
    """Human-readable sector name (never returns bare '50')."""
    return _SECTOR_DISPLAY.get(name, name.replace("NIFTY ", "") or name)


def _dedup_stocks(stocks: List[Dict]) -> List[Dict]:
    """Deduplicate by symbol, merge sector names, keep best volume entry."""
    seen = {}
    for s in stocks:
        sym = s.get('symbol', '')
        if not sym:
            continue
        if sym not in seen:
            seen[sym] = dict(s)
            seen[sym]['_sectors'] = {s.get('sector', '')} if s.get('sector') else set()
        else:
            if s.get('sector'):
                seen[sym]['_sectors'].add(s['sector'])
            # Keep entry with highest volume
            if s.get('volume', 0) > seen[sym].get('volume', 0):
                bk = seen[sym]['_sectors']
                seen[sym] = dict(s)
                seen[sym]['_sectors'] = bk
                if s.get('sector'):
                    seen[sym]['_sectors'].add(s['sector'])
    result = list(seen.values())
    for r in result:
        secs = sorted(x for x in r.get('_sectors', set()) if x)
        r['_sectors_str'] = ', '.join(secs) if secs else ''
    return result


def _cap_label(symbol: str, sectors_data: Dict) -> str:
    """Cap category emoji: 🔵L=Large (top 100) 🟡M=Mid 🟠S=Small."""
    # Build membership sets in priority order
    in_large, in_mid, in_small = False, False, False
    for name, data in sectors_data.items():
        syms = {s['symbol'] for s in data.get('stocks', [])}
        if symbol not in syms:
            continue
        # NIFTY 50 + NIFTY NEXT 50 together = NIFTY 100 = Large Cap
        if name in ("NIFTY 50", "NIFTY NEXT 50"):
            in_large = True
        elif "MIDCAP" in name:
            in_mid = True
        elif "SMALLCAP" in name:
            in_small = True
    if in_large:
        return "🔵L"
    if in_mid:
        return "🟡M"
    if in_small:
        return "🟠S"
    return ""


def _show_fii_forex(slot_time: Optional[str]) -> bool:
    """Show FII/DII, Forex, Commodity Indices only at pre-market & 9 PM."""
    if not slot_time:
        return True
    return slot_time in _PREMARKET_SLOTS or slot_time == _EVENING_SLOT


def _stock_line(s: Dict, sectors_data: Dict = None, show_vol: bool = True) -> str:
    """Single stock line with clickable link, cap label, sectors."""
    sym = s.get('symbol', '')
    link = _nse_link(sym)
    ltp = f"₹{s['last']:,.1f}" if s.get('last') else "N/A"
    p = s.get('pct', 0)
    emoji = "🟢" if p >= 0 else "🔴"
    parts = [f"{emoji} {link} <b>{ltp}</b> ({_pct(p)})"]
    if sectors_data:
        cap = _cap_label(sym, sectors_data)
        if cap:
            parts.append(cap)
    if show_vol and s.get('volume', 0):
        parts.append(_vol(s['volume']))
    sec_str = s.get('_sectors_str', s.get('sector', ''))
    if sec_str:
        # Convert raw NSE names to readable display names
        display_secs = ', '.join(
            _sector_display(seg.strip())
            for seg in sec_str.split(',')
            if seg.strip()
        )
        parts.append(display_secs[:28])
    return " · ".join(parts)


def _market_mood(snapshot: Dict) -> str:
    """Simple market mood for a kid to understand."""
    indices = snapshot.get("indices") or {}
    nifty = indices.get("NIFTY 50", {})
    p = nifty.get("pct", 0)
    try:
        adv = int(nifty.get("advances", 0) or 0)
        dec = int(nifty.get("declines", 0) or 0)
    except (ValueError, TypeError):
        adv, dec = 0, 0
    vix_data = indices.get("INDIA VIX", {})
    vix_val = vix_data.get("last", 0) or 0
    vix_pct = vix_data.get("pct", 0) or 0  # daily % change — proves live data
    if p >= 1:
        mood = "🟢🟢 Strong Rally"
    elif p >= 0.3:
        mood = "🟢 Mildly Bullish"
    elif p > -0.3:
        mood = "⚪ Sideways"
    elif p > -1:
        mood = "🔴 Mildly Bearish"
    else:
        mood = "🔴🔴 Heavy Selling"
    # VIX label based on ABSOLUTE LEVEL + daily change shows it's live
    # India VIX: <13 calm, 13-18 normal, 18-24 elevated, 24+ high fear
    vix_chg_str = f" {vix_pct:+.1f}%" if vix_pct else ""
    vix_label = ""
    if vix_val >= 24:
        vix_label = f" | 😨 VIX {vix_val:.1f}{vix_chg_str} High Fear"
    elif vix_val >= 18:
        vix_label = f" | ⚠️ VIX {vix_val:.1f}{vix_chg_str} Elevated"
    elif vix_val >= 13:
        vix_label = f" | 😐 VIX {vix_val:.1f}{vix_chg_str} Normal"
    elif vix_val > 0:
        vix_label = f" | 😌 VIX {vix_val:.1f}{vix_chg_str} Calm"
    return f"{mood} ({adv}🟢 vs {dec}🔴){vix_label}"


def identify_watchlist(snapshot: Dict, count: int = 5) -> List[Dict]:
    """
    Pick the best intraday tracking stocks.

    Strategy:
    - Bullish market: highest momentum × volume (outperforming sectors first)
    - Bearish market: relative strength — stocks losing LESS than their sector
      on high volume (these hold up best and bounce hardest on reversal)
    - Always: penalise falling-knife stocks near 52W lows, prefer high value
    """
    sectors = snapshot.get("sectors") or {}
    indices = snapshot.get("indices") or {}
    if not sectors:
        return []

    nifty_pct = indices.get("NIFTY 50", {}).get("pct", 0) or 0
    is_bullish = nifty_pct >= 0

    all_stocks = []
    for name, data in sectors.items():
        sector_pct = data.get("index_pct", 0) or 0
        for s in data.get("stocks", []):
            all_stocks.append({**s, "sector": name, "sector_pct": sector_pct})

    deduped = _dedup_stocks(all_stocks)

    for s in deduped:
        val = s.get("value_cr", 0) or 0
        pct = s.get("pct", 0) or 0
        sector_pct = s.get("sector_pct", 0) or 0
        chg_30d = s.get("chg_30d", 0) or 0
        near_52l = s.get("near_52l", 999) or 999
        rs = pct - sector_pct   # relative strength vs sector

        if is_bullish:
            # Momentum play: positive move + outperforming sector + volume
            score = val * max(pct, 0.01) * (1.0 + max(rs, 0) * 0.1)
        else:
            # Defensive play: least damage, still liquid
            # rs > 0 means holding up BETTER than its sector (strong)
            score = val * (rs + 10) * max(1.0 + chg_30d / 200, 0.1)

        # Hard penalty: don't pick falling knives (at 52W low on a bad day)
        if isinstance(near_52l, (int, float)) and 0 < near_52l <= 2:
            score *= 0.15

        # Bonus: high liquidity stocks are easier to exit
        if val > 1000:
            score *= 1.3
        elif val > 500:
            score *= 1.1

        s["_score"] = score

    ranked = sorted(deduped, key=lambda x: x.get("_score", 0), reverse=True)
    picks = []
    for s in ranked[:count]:
        picks.append({
            "symbol": s["symbol"],
            "entry_ltp": s["last"],
            "entry_pct": s["pct"],
            "entry_volume": s.get("volume", 0),
            "cap": _cap_label(s["symbol"], sectors),
            "sectors": s.get("_sectors_str", s.get("sector", "")),
            "year_high": s.get("year_high", 0),
            "year_low": s.get("year_low", 0),
            "rs_vs_sector": round((s.get("pct", 0) or 0) - (s.get("sector_pct", 0) or 0), 2),
        })
    return picks


def format_watchlist_msg(snapshot: Dict, watchlist: List[Dict]) -> Optional[str]:
    """Track watchlist stocks with current LTP vs entry price."""
    if not watchlist:
        return None
    sectors = snapshot.get("sectors") or {}
    # Build symbol→current data map
    current = {}
    for name, data in sectors.items():
        for s in data.get("stocks", []):
            sym = s["symbol"]
            if sym not in current or s.get("volume", 0) > current[sym].get("volume", 0):
                current[sym] = s
    lines = ["<b>🎯 Watchlist Tracker</b>", ""]
    indices = snapshot.get("indices") or {}
    nifty_pct = indices.get("NIFTY 50", {}).get("pct", 0) or 0
    context = "Bearish day" if nifty_pct < -0.5 else ("Bullish day" if nifty_pct > 0.5 else "Flat day")
    # Pre-compute all_zero BEFORE the loop so we can use day pct for arrows on entry day.
    # all_zero = every entry was set to today's LTP (all vs-entry deltas are ~0%)
    all_zero = bool(watchlist) and all(
        abs((current.get(w["symbol"], {}).get("last", w["entry_ltp"]) - w["entry_ltp"])
            / w["entry_ltp"] * 100) < 0.05
        for w in watchlist if w.get("entry_ltp")
    )
    lines.append(f"<i>Tracking live · {context} (Nifty {nifty_pct:+.2f}%)</i>")
    lines.append("")
    any_data = False
    for i, w in enumerate(watchlist, 1):
        sym = w["symbol"]
        entry = w["entry_ltp"]
        cur_data = current.get(sym)
        if not cur_data:
            lines.append(f"{i}. {_nse_link(sym)} — No data")
            continue
        any_data = True
        cur_ltp = cur_data["last"]
        chg = ((cur_ltp - entry) / entry * 100) if entry else 0
        day_pct = cur_data.get("pct", 0) or 0
        # When all entries were just set, use day's pct for the arrow (honest direction)
        arrow_basis = day_pct if all_zero else chg
        if arrow_basis >= 2:
            sig = "🚀"
        elif arrow_basis >= 0.5:
            sig = "📈"
        elif arrow_basis > -0.5:
            sig = "➡️"
        elif arrow_basis > -2:
            sig = "📉"
        else:
            sig = "💥"
        cap = w.get("cap", "")
        # Show sectors using display names
        sec_raw = w.get("sectors", "")
        sec = ", ".join(_sector_display(s.strip()) for s in sec_raw.split(",") if s.strip())[:22]
        rs = w.get("rs_vs_sector", 0)
        rs_str = f" · RS {rs:+.1f}%" if rs != 0 else ""
        lines.append(
            f"{i}. {sig} {_nse_link(sym)} <b>₹{cur_ltp:,.1f}</b> "
            f"(entry ₹{entry:,.1f} → <b>{chg:+.2f}%</b>) "
            f"{cap} {sec}{rs_str}"
        )
        lines.append(
            f"   Vol: {_vol(cur_data.get('volume', 0))} · "
            f"Day: {_pct(cur_data.get('pct', 0))} · "
            f"H/L: ₹{cur_data.get('high', 0):,.1f}/₹{cur_data.get('low', 0):,.1f}"
        )
    if not any_data:
        return None
    lines.append("")
    # Summary — track wins, losses, and flat (within ±0.1%)
    # When all entries were just set (all 0.00%), use day's pct as proxy
    # all_zero already computed above (before the per-stock loop)
    if all_zero:
        # Use today's pct change from prev_close as the honest score
        # NOTE: parentheses around (... or 0) are critical — without them,
        # Python parses `x or 0 >= 1.0` as `x or (0 >= 1.0)` = `x or False`
        # which treats any non-zero pct as truthy → double-counts every stock.
        gains = sum(
            1 for w in watchlist
            if (current.get(w["symbol"], {}).get("pct", 0) or 0) >= 1.0
        )
        losses = sum(
            1 for w in watchlist
            if (current.get(w["symbol"], {}).get("pct", 0) or 0) <= -1.0
        )
        flat = len(watchlist) - gains - losses
        parts = []
        if gains:
            parts.append(f"{gains}🟢 up today")
        if flat:
            parts.append(f"{flat}⚪ flat today")
        if losses:
            parts.append(f"{losses}🔴 down today")
        lines.append(f"Score: {' · '.join(parts)} <i>(entry just set)</i>")
    else:
        gains = sum(1 for w in watchlist if current.get(w["symbol"], {}).get("last", 0) > w["entry_ltp"] * 1.001)
        losses = sum(1 for w in watchlist if current.get(w["symbol"], {}).get("last", 0) < w["entry_ltp"] * 0.999)
        flat = len(watchlist) - gains - losses
        parts = []
        if gains:
            parts.append(f"{gains}🟢 winning")
        if flat:
            parts.append(f"{flat}⚪ flat")
        if losses:
            parts.append(f"{losses}🔴 losing")
        lines.append(f"Score: {' · '.join(parts)}")
    return "\n".join(lines)


def format_weekly_toppers(snapshot: Dict, data_dir: str) -> Optional[str]:
    """Weekly watchlist performance — shows best/worst suggestions this week.
    
    Reads all daily watchlist files (Mon-Fri) and compares each
    stock's entry price to its closing LTP from the snapshot.
    Returns a formatted weekly leaderboard.
    """
    import glob
    from datetime import timedelta

    today = datetime.now().date()
    # Find start of this week (Monday)
    monday = today - timedelta(days=today.weekday())

    # Collect all watchlist files from this week
    watchlist_dir = os.path.join(data_dir, "watchlist")
    if not os.path.isdir(watchlist_dir):
        return None

    weekly_stocks = {}  # symbol → {entry, entry_date, current_ltp, pct_chg}
    sectors = snapshot.get("sectors") or {}
    current = {}
    for name, data in sectors.items():
        for s in data.get("stocks", []):
            if s["symbol"] not in current:
                current[s["symbol"]] = s

    for day_offset in range(7):
        dt = monday + timedelta(days=day_offset)
        if dt > today:
            break
        wl_file = os.path.join(watchlist_dir, f"{dt.isoformat()}.json")
        if not os.path.exists(wl_file):
            continue
        try:
            with open(wl_file, "r", encoding="utf-8") as f:
                day_wl = json.load(f)
            for w in day_wl:
                sym = w.get("symbol", "")
                entry = w.get("entry_ltp", 0)
                if not sym or not entry:
                    continue
                cur = current.get(sym, {}).get("last", 0)
                if not cur:
                    continue
                pct = ((cur - entry) / entry * 100)
                # Keep the earliest entry for this week
                if sym not in weekly_stocks:
                    weekly_stocks[sym] = {
                        "symbol": sym,
                        "entry": entry,
                        "entry_date": dt.strftime("%a %d"),
                        "current": cur,
                        "pct": pct,
                    }
                else:
                    # Also track if same stock was picked on multiple days
                    weekly_stocks[sym]["picks"] = weekly_stocks[sym].get("picks", 1) + 1
        except Exception:
            continue

    if not weekly_stocks:
        return None

    # Sort by performance
    ranked = sorted(weekly_stocks.values(), key=lambda x: x["pct"], reverse=True)

    lines = ["<b>📊 Weekly Watchlist Toppers</b>", ""]
    lines.append(f"<i>Week of {monday.strftime('%d %b')} — {min(today, monday + timedelta(days=4)).strftime('%d %b %Y')}</i>")
    lines.append("")

    # Top winners
    winners = [s for s in ranked if s["pct"] > 0.1]
    losers = [s for s in ranked if s["pct"] < -0.1]

    if winners:
        lines.append("<b>🏆 Best Performers:</b>")
        for i, s in enumerate(winners[:5], 1):
            medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
            picks_str = f" · {s.get('picks', 1)}× picked" if s.get("picks", 1) > 1 else ""
            lines.append(
                f"  {medal} {_nse_link(s['symbol'])} "
                f"<b>{s['pct']:+.2f}%</b> "
                f"(₹{s['entry']:,.1f} → ₹{s['current']:,.1f})"
                f"{picks_str}"
            )
        lines.append("")

    if losers:
        lines.append("<b>📉 Underperformers:</b>")
        for s in losers[-3:]:
            lines.append(
                f"  🔻 {_nse_link(s['symbol'])} "
                f"<b>{s['pct']:+.2f}%</b> "
                f"(₹{s['entry']:,.1f} → ₹{s['current']:,.1f})"
            )
        lines.append("")

    # Summary stats
    total = len(weekly_stocks)
    win_count = len(winners)
    loss_count = len(losers)
    avg_return = sum(s["pct"] for s in weekly_stocks.values()) / total if total else 0
    win_rate = (win_count / total * 100) if total else 0

    lines.append(f"<b>📈 Week Stats:</b> {total} stocks tracked")
    lines.append(f"  Win Rate: <b>{win_rate:.0f}%</b> ({win_count}W / {loss_count}L)")
    lines.append(f"  Avg Return: <b>{avg_return:+.2f}%</b>")

    if win_rate >= 60:
        lines.append("  💪 Strong week — our picks beat the market!")
    elif win_rate >= 40:
        lines.append("  📊 Mixed week — some winners, some losers.")
    else:
        lines.append("  ⚠️ Tough week for picks. Market conditions may need different strategy.")

    return "\n".join(lines)


def format_categorized_signals_msg(signals: Dict) -> str:
    """
    Phase 1: Format scored + categorised stock signals for Telegram.

    Categories:
      🚀 INTRADAY  — same-day momentum plays
      🔄 SWING     — 3-10 day hold
      💎 LONG-TERM — 6m+ value / compounder plays
    Plus: 🎯 Dividend Captures, ⚡ Volume Spikes
    """
    if not signals:
        return ""

    now_str  = datetime.now().strftime("%d %b %Y  %I:%M %p")
    fii_score = signals.get("fii_sentiment", 0)
    if fii_score >= 7:
        fii_label = "🟢 FII Bullish"
    elif fii_score >= 4:
        fii_label = "🟡 FII Neutral"
    else:
        fii_label = "🔴 FII Bearish"

    L = [
        f"<b>📊 Market Intelligence Report — {now_str}</b>",
        f"<i>Market Mood: {fii_label}</i>",
        "",
    ]

    # ── Category emoji + header ──────────────────────────────────────────────
    CATEGORY_META = {
        "INTRADAY":  ("🚀", "INTRADAY Plays", "Trade today, exit before close"),
        "SWING":     ("🔄", "SWING Plays",    "Hold 3-10 days"),
        "LONG-TERM": ("💎", "LONG-TERM Picks", "Hold 6 months+"),
    }

    for cat_key, (emoji, title, subtitle) in CATEGORY_META.items():
        stocks = signals.get(
            {"INTRADAY": "intraday", "SWING": "swing", "LONG-TERM": "long_term"}[cat_key], []
        )
        if not stocks:
            continue

        L.append(f"<b>{emoji} {title}</b>")
        L.append(f"<i>{subtitle}</i>")
        L.append("")

        for s in stocks:
            sym      = s.get("symbol", "")
            ltp      = s.get("ltp", 0)
            pct      = s.get("pct", 0)
            score    = s.get("score", 0)
            sector   = s.get("sector", "")
            trend    = s.get("trend", "")
            reasons  = s.get("reasons", [])
            vol_r    = s.get("vol_ratio", 0)
            pe_v     = s.get("pe", 0)
            deliv_v  = s.get("delivery_pct", 0)

            # Skip if no real data
            if not sym or ltp <= 0:
                continue

            pct_str    = f"{pct:+.1f}%" if pct else "—"
            trend_icon = {"UPTREND": "↗", "DOWNTREND": "↘", "SIDEWAYS": "→"}.get(trend, "→")
            vol_str    = f"Vol {vol_r:.1f}×" if vol_r > 0 else ""

            L.append(
                f"  <b>{sym}</b>  ₹{ltp:,.2f}  {pct_str}  {trend_icon}"
            )
            quality_bits = []
            if pe_v and pe_v > 0:
                quality_bits.append(f"PE {pe_v:.1f}")
            if deliv_v and deliv_v > 0:
                quality_bits.append(f"Del {deliv_v:.0f}%")

            L.append(
                f"  Score: <b>{score}/100</b> | {sector}"
                + (f" | {vol_str}" if vol_str else "")
                + (f" | {' | '.join(quality_bits)}" if quality_bits else "")
            )
            # Top 2 reasons — skip empty/zero ones
            clean_reasons = [r for r in reasons if r][:2]
            for r in clean_reasons:
                L.append(f"  • {r}")
            L.append("")

        L.append("")

    # ── Dividend Captures ────────────────────────────────────────────────────
    div_caps = signals.get("dividend_captures", [])
    if div_caps:
        L.append("<b>🎯 Dividend Capture Opportunities</b>")
        L.append("<i>Buy before ex-date to collect dividend</i>")
        L.append("")
        for d in div_caps:
            sym      = d.get("symbol", "")
            ltp      = d.get("ltp", 0)
            div_amt  = d.get("div_amount", 0)
            yield_p  = d.get("yield_pct", 0)
            ex_date  = d.get("ex_date", "")
            days     = d.get("days_left", 0)
            src      = d.get("source", "NSE")
            if not sym or ltp <= 0 or div_amt <= 0:
                continue
            urgency = "⚠️ TODAY" if days == 0 else (f"{days}d left" if days > 0 else "")
            L.append(
                f"  <b>{sym}</b> [{src}]  ₹{ltp:,.2f}"
            )
            L.append(
                f"  Div: ₹{div_amt:.2f} | Yield: <b>{yield_p:.2f}%</b>"
                f" | Ex: {ex_date} {urgency}"
            )
            L.append("")
        L.append("")

    # ── Volume Spikes ────────────────────────────────────────────────────────
    vol_spikes = signals.get("volume_spikes", [])
    if vol_spikes:
        L.append("<b>⚡ Volume Spikes (Unusual Activity)</b>")
        L.append("<i>High volume = institutional / smart money interest</i>")
        L.append("")
        for s in vol_spikes:
            sym  = s.get("symbol", "")
            ltp  = s.get("ltp", 0)
            pct  = s.get("pct", 0)
            volr = s.get("vol_ratio", 0)
            sec  = s.get("sector", "")
            if not sym or ltp <= 0:
                continue
            L.append(
                f"  <b>{sym}</b>  ₹{ltp:,.2f}  {pct:+.1f}%  |  {volr:.1f}× avg vol  |  {sec}"
            )
        L.append("")

    # ── Legend ───────────────────────────────────────────────────────────────
    L.append("─" * 36)
    L.append(
        "<i>Score 0-100 based on: momentum, 52W position, "
        "volume vs 5-day avg, PE, delivery%, FII sentiment, 7-day trend. "
        "Not financial advice — do your own research.</i>"
    )

    return "\n".join(L)


def format_phase2_predictive_msg(phase2: Dict) -> Optional[str]:
    """Format Phase 2 predictive analytics into a compact Telegram message."""
    if not phase2:
        return None

    levels = (phase2.get("momentum_levels") or {})
    leaders = levels.get("leaders") or []
    laggards = levels.get("laggards") or []

    rotation = (phase2.get("sector_rotation") or {})
    gaining = rotation.get("gaining") or []
    losing = rotation.get("losing") or []

    breakouts = phase2.get("breakout_tracker") or []
    flow = phase2.get("fii_dii_trend") or {}

    if not any([leaders, laggards, gaining, losing, breakouts, flow.get("prediction")]):
        return None

    now_str = datetime.now().strftime("%d %b %Y  %I:%M %p")
    L = [
        f"<b>🧠 Phase 2 Predictive View — {now_str}</b>",
        "<i>Historical momentum, sector rotation, breakout persistence, and flow trend</i>",
        "",
    ]

    if leaders:
        L.append("<b>📈 Momentum + Levels (Leaders)</b>")
        for x in leaders[:5]:
            sym = x.get("symbol", "")
            if not sym:
                continue
            L.append(
                f"  <b>{sym}</b>  5d:{x.get('mom_5d', 0):+.1f}% | "
                f"S:{x.get('support', 0):,.0f} R:{x.get('resistance', 0):,.0f} | "
                f"Room→R: {x.get('dist_to_res', 0):.1f}%"
            )
        L.append("")

    if laggards:
        L.append("<b>📉 Momentum Laggards (Mean-Reversion Watch)</b>")
        for x in laggards[:3]:
            sym = x.get("symbol", "")
            if not sym:
                continue
            L.append(f"  {sym}: 5d {x.get('mom_5d', 0):+.1f}% | S:{x.get('support', 0):,.0f}")
        L.append("")

    if gaining or losing:
        L.append("<b>🔄 Sector Rotation (5-day consistency)</b>")
        if gaining:
            top = gaining[0]
            L.append(
                f"  🟢 Into: <b>{top.get('sector','')}</b> "
                f"({top.get('avg_5d', 0):+.2f}% avg, {top.get('up_days', 0)}/{top.get('up_days', 0) + top.get('down_days', 0)} up days)"
            )
        if losing:
            top = losing[0]
            L.append(
                f"  🔴 Out of: <b>{top.get('sector','')}</b> "
                f"({top.get('avg_5d', 0):+.2f}% avg, {top.get('down_days', 0)}/{top.get('up_days', 0) + top.get('down_days', 0)} down days)"
            )
        L.append("")

    if breakouts:
        L.append("<b>🚨 52W Breakout Persistence (3+ days near high)</b>")
        for b in breakouts[:5]:
            sym = b.get("symbol", "")
            if not sym:
                continue
            L.append(
                f"  {sym}: {b.get('days', 0)}d near 52W high | "
                f"{b.get('near_52h', 0):.2f}% away | {b.get('pct', 0):+.1f}%"
            )
        L.append("")

    if flow:
        pred = flow.get("prediction", "UNKNOWN")
        note = flow.get("note", "")
        L.append("<b>💸 FII/DII 5-day Rolling Trend</b>")
        L.append(
            f"  Signal: <b>{pred}</b> | FII avg: ₹{flow.get('avg_fii_5d', 0):,.0f}Cr | "
            f"DII avg: ₹{flow.get('avg_dii_5d', 0):,.0f}Cr"
        )
        if note:
            L.append(f"  <i>{note}</i>")

    return "\n".join(L)


def format_phase3_global_msg(snapshot: Dict, fii_flow: Optional[Dict] = None) -> Optional[str]:
    """Format Phase 3 global sentiment and index cues."""
    gidx = snapshot.get("global_indices") or {}
    gs = snapshot.get("global_sentiment") or {}
    fg = gs.get("fear_greed") or {}
    macro = gs.get("macro") or {}
    forex = snapshot.get("forex") or {}

    if not (gidx or fg or macro):
        return None

    now_str = datetime.now().strftime("%d %b %Y  %I:%M %p")
    lines = [
        f"<b>🌍 Phase 3 Global Sentiment — {now_str}</b>",
        "<i>Global indices, risk sentiment, and macro drivers</i>",
        "",
    ]

    if gidx:
        lines.append("<b>🌐 Global Equity Cues</b>")
        ordered = ["S&P 500", "NASDAQ", "DOW", "NIKKEI", "HANG SENG", "FTSE"]
        headers = ["Index", "Last", "%Chg"]
        rows = []
        for name in ordered:
            d = gidx.get(name)
            if not d:
                continue
            rows.append([
                name,
                f"{float(d.get('last', 0) or 0):,.2f}",
                _pct(float(d.get("pct", 0) or 0)),
            ])
        if rows:
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=['left', 'right', 'right']))
            lines.append("</pre>")
            lines.append("")

    if fg:
        try:
            score = float(fg.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        rating = str(fg.get("rating", "") or "").strip().title()
        if score >= 75:
            fg_emoji = "🟢"
        elif score >= 55:
            fg_emoji = "🟡"
        elif score >= 45:
            fg_emoji = "⚪"
        elif score >= 25:
            fg_emoji = "🟠"
        else:
            fg_emoji = "🔴"
        lines.append("<b>😶‍🌫️ Fear & Greed</b>")
        lines.append(f"  {fg_emoji} Score: <b>{score:.1f}</b>/100 | {rating}")
        lines.append("")

    macro_parts = []
    dxy = (macro.get("DXY") or {})
    brent = (macro.get("BRENT") or {})
    if dxy:
        macro_parts.append(f"DXY {dxy.get('last', 0):,.2f} ({_pct(float(dxy.get('pct', 0) or 0))})")
    if brent:
        macro_parts.append(f"Brent ${brent.get('last', 0):,.2f} ({_pct(float(brent.get('pct', 0) or 0))})")
    if forex.get("usdinr"):
        macro_parts.append(f"USD/INR ₹{float(forex.get('usdinr', 0) or 0):.2f}")
    if macro_parts:
        lines.append("<b>🧭 Macro Drivers</b>")
        lines.append("  " + " | ".join(macro_parts))
        lines.append("")

    if fii_flow:
        pred = str(fii_flow.get("prediction", "UNKNOWN") or "UNKNOWN")
        avg_fii = float(fii_flow.get("avg_fii_5d", 0) or 0)
        avg_dii = float(fii_flow.get("avg_dii_5d", 0) or 0)
        note = str(fii_flow.get("note", "") or "")
        lines.append("<b>💸 FII/DII Rolling Bias (5d)</b>")
        lines.append(f"  Signal: <b>{pred}</b> | FII ₹{avg_fii:,.0f}Cr | DII ₹{avg_dii:,.0f}Cr")
        if note:
            lines.append(f"  <i>{note}</i>")

    return "\n".join(lines)


def format_phase4_ml_msg(phase4: Dict) -> Optional[str]:
    """Format Phase 4 ML-style prediction output for Telegram."""
    if not phase4:
        return None

    picks = phase4.get("top_stocks") or []
    sector_pred = phase4.get("sector_prediction") or {}
    if not picks and not sector_pred:
        return None

    now_str = datetime.now().strftime("%d %b %Y  %I:%M %p")
    lines = [
        f"<b>🤖 Phase 4 ML Prediction — {now_str}</b>",
        "<i>Next-session score model and sector outlook</i>",
        "",
    ]

    if picks:
        lines.append("<b>📌 Tomorrow Positive Signals (Top 5)</b>")
        headers = ["Sym", "Score", "5d%", "Volx", "52W Pos"]
        rows = []
        for p in picks[:5]:
            sym = str(p.get("symbol", "") or "")
            if not sym:
                continue
            near_h = p.get("near_52h")
            near_l = p.get("near_52l")
            pos_str = "Mid"
            if isinstance(near_h, (int, float)):
                pos_str = f"NearH {near_h:.1f}%"
            elif isinstance(near_l, (int, float)):
                pos_str = f"NearL {near_l:.1f}%"

            rows.append([
                sym,
                f"{float(p.get('score', 0) or 0):.1f}",
                _pct(float(p.get("five_day_return", 0) or 0)),
                f"{float(p.get('volume_ratio', 0) or 0):.2f}",
                pos_str,
            ])

        if rows:
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=["left", "right", "right", "right", "left"]))
            lines.append("</pre>")
            lines.append("  <i>Model: 0.3*5d_return + 0.2*volume_ratio + 0.3*52W_position + 0.2*FII_net</i>")
            lines.append("")

    if sector_pred:
        outlook = str(sector_pred.get("outlook", "NEUTRAL") or "NEUTRAL")
        score = float(sector_pred.get("score", 0) or 0)
        gavg = float(sector_pred.get("global_avg_pct", 0) or 0)
        fg_score = float(sector_pred.get("fear_greed_score", 50) or 50)
        fii_net = float(sector_pred.get("fii_net", 0) or 0)

        lines.append("<b>🏭 Sector Prediction</b>")
        lines.append(f"  Outlook: <b>{outlook}</b> | Composite: {score:+.2f}")
        lines.append(f"  Drivers: Global avg {_pct(gavg)} | Fear&Greed {fg_score:.1f} | FII ₹{fii_net:,.0f}Cr")

        leaders = sector_pred.get("likely_leaders") or []
        if leaders:
            lead_txt = ", ".join(
                f"{x.get('sector','')} ({x.get('model_score', 0):+.1f})"
                for x in leaders[:3]
                if x.get("sector")
            )
            if lead_txt:
                lines.append(f"  🟢 Likely leaders: {lead_txt}")

        laggards = sector_pred.get("likely_laggards") or []
        if laggards:
            lag_txt = ", ".join(
                f"{x.get('sector','')} ({x.get('model_score', 0):+.1f})"
                for x in laggards[:3]
                if x.get("sector")
            )
            if lag_txt:
                lines.append(f"  🔴 Likely laggards: {lag_txt}")

        data_note = sector_pred.get("data_note", "")
        if data_note:
            lines.append(f"  <i>⚠️ {data_note}</i>")

    # ── Accuracy & Portfolio P&L (rolling 5-session) ────────────────────
    accuracy = phase4.get("accuracy") or {}
    hit_rate = accuracy.get("rolling_hit_rate")
    sessions = accuracy.get("sessions_tracked", 0)
    if hit_rate is not None and sessions > 0:
        hits   = accuracy.get("hits", 0)
        misses = accuracy.get("misses", 0)
        filled = round(hit_rate / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)
        lines.append("")
        lines.append(f"<b>📈 Model Accuracy — {sessions}d rolling</b>")
        lines.append(f"  Hit rate: <b>{hit_rate:.1f}%</b>  [{bar}]")
        lines.append(f"  ✅ {hits} correct  ❌ {misses} wrong  (neutral ±0.5% excluded)")

        # Mini P&L table: last 8 actionable picks
        results = accuracy.get("session_results") or []
        actionable = [r for r in results if r.get("hit") is not None][-8:]
        if actionable:
            lines.append("  <i>Recent picks P&L:</i>")
            for r in actionable:
                sym   = r.get("symbol", "")
                pct   = r.get("pct_chg", 0)
                icon  = "✅" if r.get("hit") else "❌"
                ep    = r.get("entry_price", 0)
                cp    = r.get("current_price", 0)
                lines.append(
                    f"  {icon} {sym}  ₹{ep:,.1f}→₹{cp:,.1f}  <b>{pct:+.2f}%</b>"
                )

    return "\n".join(lines)


def format_weekend_global_msg(snapshot: Dict) -> Optional[str]:
    """Format global cues for Sunday evening → Monday open preview.

    Only uses data already present in the snapshot (global_indices +
    global_sentiment).  No NSE market data needed — markets are closed.
    """
    gidx = snapshot.get("global_indices") or {}
    gs   = snapshot.get("global_sentiment") or {}
    fg   = gs.get("fear_greed") or {}
    macro = gs.get("macro") or {}

    if not gidx and not fg:
        return None

    now_str = datetime.now().strftime("%d %b %Y  %I:%M %p")
    lines = [
        f"<b>🌍 Weekend Global Cues — {now_str}</b>",
        "<i>Monday morning market preview (NSE opens 09:15 IST)</i>",
        "",
    ]

    # Global equity table
    if gidx:
        lines.append("<b>📊 Global Equity (Friday close)</b>")
        for name, data in gidx.items():
            pct  = float(data.get("pct", 0) or 0)
            last = float(data.get("last", 0) or 0)
            icon = "🟢" if pct >= 0 else "🔴"
            lines.append(f"  {icon} {name:<14} {last:>10,.2f}  ({pct:+.2f}%)")
        lines.append("")

    # Fear & Greed
    fg_score = None
    if fg.get("score") is not None:
        fg_score = float(fg["score"])
        rating   = fg.get("rating", "")
        filled   = round(fg_score / 10)
        bar      = "🟩" * filled + "⬜" * (10 - filled)
        lines.append(f"<b>😨 Fear & Greed:</b>  {fg_score:.0f}/100 — <b>{rating}</b>")
        lines.append(f"  [{bar}]")
        lines.append("")

    # Macro drivers
    dxy   = macro.get("DXY") or {}
    brent = macro.get("BRENT") or {}
    if dxy or brent:
        lines.append("<b>🔍 Macro Drivers</b>")
        if dxy:
            d_pct = float(dxy.get("pct", 0) or 0)
            icon  = "🔺" if d_pct > 0 else "🔻"
            lines.append(f"  {icon} DXY (US Dollar Index):  {dxy.get('last', 0):.3f}  ({d_pct:+.2f}%)")
        if brent:
            b_pct = float(brent.get("pct", 0) or 0)
            icon  = "🔺" if b_pct > 0 else "🔻"
            lines.append(f"  {icon} Brent Crude:           ${brent.get('last', 0):.2f}  ({b_pct:+.2f}%)")
        lines.append("")

    # Composite outlook
    g_pcts     = [float(d.get("pct", 0) or 0) for d in gidx.values()]
    global_avg = sum(g_pcts) / len(g_pcts) if g_pcts else 0.0
    dxy_pct    = float(dxy.get("pct", 0) or 0) if dxy else 0.0

    if global_avg >= 0.4 and (fg_score or 50) >= 40 and dxy_pct <= 0.3:
        outlook = "🟢 Positive open expected"
        note    = "Global rally + neutral-to-greedy sentiment; watch FII flows at 09:00"
    elif global_avg <= -0.5 or (fg_score is not None and fg_score < 25):
        outlook = "🔴 Cautious open expected"
        note    = "Global weakness or extreme fear; avoid aggressive longs until 09:30"
    elif dxy_pct >= 0.5:
        outlook = "⚠️ Mixed — strong Dollar headwind"
        note    = "Rising DXY pressures EM inflows; FII selling likely; wait for direction"
    else:
        outlook = "⚪ Range-bound open likely"
        note    = "No strong cues; wait for FII data and Nifty futures gap direction"

    lines.append(f"<b>📋 Monday Outlook:</b>  {outlook}")
    lines.append(f"  <i>{note}</i>")

    return "\n".join(lines)


def format_expert_opinion(snapshot: Dict, delta: Optional[Dict] = None) -> Optional[str]:
    """Actionable market analysis with specific sector and breadth insights."""
    indices = snapshot.get("indices") or {}
    sectors = snapshot.get("sectors") or {}
    if not indices:
        return None
    nifty = indices.get("NIFTY 50", {})
    bank = indices.get("NIFTY BANK", {})
    vix = indices.get("INDIA VIX", {})
    n_pct = nifty.get("pct", 0)
    b_pct = bank.get("pct", 0)
    v_pct = vix.get("pct", 0)
    v_last = vix.get("last", 0)
    lines = ["<b>🧠 Expert Take (Simple Analysis)</b>", ""]

    # 1. Market direction with breadth context
    try:
        adv = int(nifty.get("advances", 0) or 0)
        dec = int(nifty.get("declines", 0) or 0)
    except (ValueError, TypeError):
        adv, dec = 0, 0
    breadth_pct = adv / (adv + dec) * 100 if (adv + dec) > 0 else 50

    if n_pct >= 1:
        lines.append("📈 <b>Market is strongly UP today.</b> Buyers in control.")
        if breadth_pct >= 60:
            lines.append(f"   Broad rally ({adv} of {adv+dec} stocks green) — genuine strength.")
        else:
            lines.append(f"   ⚠ Index up but only {adv} of {adv+dec} stocks green — narrow rally, select stocks lifting index.")
    elif n_pct >= 0.3:
        lines.append("📈 <b>Market is mildly green.</b> Cautious optimism.")
        if breadth_pct >= 60:
            lines.append(f"   Healthy breadth ({adv}🟢 vs {dec}🔴) — broad participation.")
    elif n_pct > -0.3:
        lines.append("➡️ <b>Market is flat/sideways.</b> No clear direction.")
        if breadth_pct < 40:
            lines.append(f"   ⚠ More stocks declining ({dec}🔴 vs {adv}🟢) despite flat index — hidden weakness.")
        elif breadth_pct > 60:
            lines.append(f"   Midcaps/smallcaps doing better ({adv}🟢 vs {dec}🔴) while large caps flat.")
    elif n_pct > -1:
        lines.append("📉 <b>Market is down.</b> Sellers have some control.")
    else:
        lines.append("📉📉 <b>Market is in heavy selling.</b> Be cautious!")
    lines.append("")

    # 2. FII/DII reading
    fd = snapshot.get("fii_dii")
    if fd:
        fii_net = fd.get("fii", {}).get("net", 0)
        dii_net = fd.get("dii", {}).get("net", 0)
        if fii_net < -1000 and dii_net > 1000:
            lines.append("💰 <b>Foreign investors selling, but Indian institutions buying</b> "
                         "— DII providing support. Market has a safety net.")
        elif fii_net > 1000 and dii_net > 0:
            lines.append("💰 <b>Both FII & DII buying</b> — Very bullish signal!")
        elif fii_net < -1000 and dii_net < 0:
            lines.append("💰 <b>Both FII & DII selling</b> — Very bearish. Stay careful.")
        elif fii_net > 0:
            lines.append("💰 <b>Foreign investors buying</b> — Positive for market.")
        lines.append("")

    # 3. VIX (fear gauge — India VIX: <13 calm, 13-18 normal, 18-24 elevated, 24+ high)
    if v_last:
        # v_pct is the daily % change from NSE — shows VIX is live, not cached
        vix_chg = f" ({'+' if v_pct >= 0 else ''}{v_pct:.1f}% today)" if v_pct else ""
        if v_last >= 24:
            lines.append(f"😨 <b>VIX at {v_last:.1f}{vix_chg}</b> — High fear! Reduce position sizes, expect wild swings.")
        elif v_last >= 18:
            lines.append(f"😐 <b>VIX at {v_last:.1f}{vix_chg}</b> — Elevated volatility. Use tight stop-losses.")
        elif v_last >= 13:
            lines.append(f"😐 <b>VIX at {v_last:.1f}{vix_chg}</b> — Normal range. Market conditions healthy.")
        else:
            lines.append(f"😌 <b>VIX at {v_last:.1f}{vix_chg}</b> — Low fear. Market is calm.")
        lines.append("")

    # 4. Sector rotation — show top 2 and bottom 2 with context
    if sectors:
        sorted_sec = sorted(sectors.items(), key=lambda x: x[1].get("index_pct", 0), reverse=True)
        # Only show sectors with positive % as "flowing into"
        positive_secs = [s for s in sorted_sec if s[1].get("index_pct", 0) > 0]
        negative_secs = [s for s in sorted_sec if s[1].get("index_pct", 0) < 0]
        top2 = positive_secs[:2] if positive_secs else sorted_sec[:2]
        bot2 = negative_secs[-2:] if negative_secs else sorted_sec[-2:]
        if top2 and bot2:
            t_names = ", ".join(f"{s[0].replace('NIFTY ', '')} ({_pct(s[1].get('index_pct', 0))})" for s in top2)
            b_names = ", ".join(f"{s[0].replace('NIFTY ', '')} ({_pct(s[1].get('index_pct', 0))})" for s in bot2)
            if positive_secs:
                lines.append(f"🔄 <b>Money flowing into:</b> {t_names}")
            else:
                lines.append(f"🔄 <b>Least damage:</b> {t_names}")
            if negative_secs:
                lines.append(f"   <b>Money leaving:</b> {b_names}")
            else:
                lines.append(f"   <b>Lagging sectors:</b> {b_names}")

            # Sector spread insight
            spread = sorted_sec[0][1].get("index_pct", 0) - sorted_sec[-1][1].get("index_pct", 0)
            if spread > 3:
                lines.append("   💡 Large sector gap — strong rotation. Focus on leading sectors.")
            lines.append("")

    # 5. Actionable advice based on multiple factors
    lines.append("<b>📝 What should you do?</b>")
    high_vix = v_last and v_last >= 24
    elevated_vix = v_last and v_last >= 18

    if n_pct < -2:
        lines.append("• <i>Big fall day. If you own good stocks, HOLD. Don't panic.</i>")
        lines.append("• <i>If you want to buy, wait for market to stabilize first.</i>")
    elif n_pct < -0.5:
        lines.append("• <i>Red day but not alarming. Watch for support levels.</i>")
        if not high_vix:
            lines.append("• <i>Good companies on dip = potential buying opportunity.</i>")
    elif n_pct > 1.5:
        if high_vix:
            lines.append("• <i>Strong rally BUT VIX is high — could reverse fast. Book profits, don't add.</i>")
        else:
            lines.append("• <i>Strong rally! Don't chase. Book partial profits on holdings up 10%+.</i>")
    elif n_pct > 0.5:
        if high_vix:
            lines.append("• <i>Green day but VIX signals danger ahead. Reduce position sizes, keep stop-losses tight.</i>")
        elif breadth_pct >= 60:
            lines.append("• <i>Healthy green day with broad participation. Good for swing entries.</i>")
        else:
            lines.append("• <i>Green day but narrow rally. Be selective — buy only leaders.</i>")
    else:
        if elevated_vix:
            lines.append("• <i>Flat day with elevated VIX — avoid over-trading, wait for clear direction.</i>")
        else:
            lines.append("• <i>Normal day. Stick to your plan, avoid impulsive trades.</i>")
    lines.append("")
    lines.append("<i>⚠️ This is automated analysis, not financial advice.</i>")
    return "\n".join(lines)


def _make_table(headers: List[str], rows: List[List[str]], align: Optional[List[str]] = None) -> str:
    """Create ASCII table with proper alignment for <pre> blocks.
    
    Args:
        headers: List of column headers
        rows: List of rows, each row is a list of cell values
        align: Optional alignment for each column ('left', 'right', 'center')
               Default is 'left' for all columns
    
    Returns:
        Formatted table string (without <pre> tags)
    """
    if not align:
        align = ['left'] * len(headers)
    
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))
    
    # Format rows
    lines = []
    header_line = []
    for i, (h, width, al) in enumerate(zip(headers, col_widths, align)):
        if al == 'right':
            header_line.append(h.rjust(width))
        elif al == 'center':
            header_line.append(h.center(width))
        else:
            header_line.append(h.ljust(width))
    lines.append("  ".join(header_line))
    
    # Add separator
    lines.append("  ".join(["-" * w for w in col_widths]))
    
    # Add data rows
    for row in rows:
        row_line = []
        for i, (cell, width, al) in enumerate(zip(row, col_widths, align)):
            if al == 'right':
                row_line.append(cell.rjust(width))
            elif al == 'center':
                row_line.append(cell.center(width))
            else:
                row_line.append(cell.ljust(width))
        lines.append("  ".join(row_line))
    
    return "\n".join(lines)


class TelegramBot:
    """Sends formatted messages to Telegram."""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.token or not self.chat_id:
            logger.warning("Telegram credentials not set")
            print(f"\n{'='*50}\n{text}\n{'='*50}")
            return False
        try:
            # Split long messages
            chunks = self._split(text)
            for chunk in chunks:
                resp = requests.post(
                    f"{self.api_url}/sendMessage",
                    json={"chat_id": self.chat_id, "text": chunk,
                          "parse_mode": parse_mode, "disable_web_page_preview": True},
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.error(f"Telegram send failed: {resp.text}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    def _split(self, text: str) -> List[str]:
        if len(text) <= MAX_MSG_LEN:
            return [text]
        lines = text.split("\n")
        chunks, cur = [], ""
        for line in lines:
            if len(cur) + len(line) + 1 > MAX_MSG_LEN:
                chunks.append(cur)
                cur = line
            else:
                cur += "\n" + line if cur else line
        if cur:
            chunks.append(cur)
        return chunks


# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE FORMATTERS
# ══════════════════════════════════════════════════════════════════════════════

def format_fii_dii_msg(snapshot: Dict, delta: Optional[Dict] = None, slot_time: str = None) -> str:
    """FII/DII + Key Indices + Market Status. Slot-aware: FII/DII only at pre-market & 9 PM."""
    now = datetime.now().strftime("%d %b %Y %-I:%M %p") if os.name != "nt" else datetime.now().strftime("%d %b %Y %I:%M %p")
    lines = [f"<b>📊 Market Pulse — {now}</b>", ""]

    # Market mood (one-liner)
    lines.append(f"🌡️ {_market_mood(snapshot)}")
    lines.append("")

    # Market status
    status = snapshot.get("market_status", {})
    if status:
        for mkt, info in status.items():
            if not info or not isinstance(info, dict):
                continue
            st = info.get("status", "")
            if not st or not isinstance(st, str):
                continue
            if "Capital" in mkt or "Equit" in mkt:
                emoji = "🟢" if "Open" in st or "open" in st else "🔴" if "Close" in st else "🟡"
                lines.append(f"{emoji} {mkt}: <b>{st}</b>")
        lines.append("")

    # FII/DII — only at pre-market and 9 PM
    fd = snapshot.get("fii_dii")
    show_fii = _show_fii_forex(slot_time)

    if fd and show_fii:
        sig = fd.get("signal", "")
        sig_emoji = {"Strong Bullish": "🐂🐂", "FII Bullish": "🐂", "DII Defensive": "🛡️", "Bearish": "🐻"}.get(sig, "❓")
        fii_date = fd.get('date', '')
        lines.append(f"<b>💰 FII/DII Activity</b> ({fii_date} — T+1 data)")
        lines.append(f"Signal: {sig_emoji} <b>{sig}</b>")
        lines.append(f"💡 {fd.get('interpretation', '')}")
        lines.append("")

        headers = ["", "Buy", "Sell", "Net"]
        rows = [
            ["🌍 FII", _cr(fd['fii']['buy']), _cr(-abs(fd['fii']['sell'])), _cr(fd['fii']['net'])],
            ["🏠 DII", _cr(fd['dii']['buy']), _cr(-abs(fd['dii']['sell'])), _cr(fd['dii']['net'])]
        ]
        table = _make_table(headers, rows, align=['left', 'right', 'right', 'right'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
        lines.append(f"📊 <b>Total Net: {_cr(fd.get('total_net', 0))}</b>")

        # Delta — smart unchanged handling
        if delta and delta.get("fii_dii"):
            dd = delta["fii_dii"]
            fii_changed = abs(dd.get('fii_net_change', 0)) > 0.01
            dii_changed = abs(dd.get('dii_net_change', 0)) > 0.01
            if fii_changed or dii_changed or dd.get("fii_reversal") or dd.get("dii_reversal"):
                prev_time_str = _format_prev_time(delta.get("prev_time", ""))
                lines.append("")
                lines.append(f"<b>🔄 Changes vs Last Check{prev_time_str}:</b>")
                if dd.get("fii_reversal"):
                    lines.append(f"  ⚠️ {dd['fii_reversal']}")
                if dd.get("dii_reversal"):
                    lines.append(f"  ⚠️ {dd['dii_reversal']}")
                if fii_changed:
                    lines.append(f"  FII Net: {_cr(dd['fii_net_prev'])} → {_cr(dd['fii_net_curr'])}")
                if dii_changed:
                    lines.append(f"  DII Net: {_cr(dd['dii_net_prev'])} → {_cr(dd['dii_net_curr'])}")
        lines.append("")
    elif fd and not show_fii:
        # Brief FII/DII summary in non-FII slots
        sig = fd.get("signal", "")
        sig_emoji = {"Strong Bullish": "🐂🐂", "FII Bullish": "🐂", "DII Defensive": "🛡️", "Bearish": "🐻"}.get(sig, "❓")
        lines.append(f"💰 FII/DII: {sig_emoji} {sig} (FII {_cr(fd['fii']['net'])} | DII {_cr(fd['dii']['net'])})")
        lines.append("")

    # Key Indices (always shown)
    indices = snapshot.get("indices") or {}
    if indices:
        lines.append("<b>📈 Key Indices</b>")
        top_indices = ["NIFTY 50", "NIFTY BANK", "NIFTY NEXT 50", "NIFTY MIDCAP 50", "NIFTY SMALLCAP 50"]
        for name in top_indices:
            if name in indices:
                idx = indices[name]
                e = _emoji_pct(idx.get("pct", 0))
                lines.append(f"{e} {name}: <b>{idx['last']:,.1f}</b> ({_pct(idx['pct'])})")
                try:
                    adv = int(idx.get("advances", 0) or 0)
                    dec = int(idx.get("declines", 0) or 0)
                except (ValueError, TypeError):
                    adv, dec = 0, 0
                if adv or dec:
                    lines.append(f"   🟢{adv} 🔴{dec}")

        # Trending thematic indices
        trending = ["NIFTY PSU BANK", "NIFTY INDIA DEFENCE", "NIFTY COMMODITIES",
                     "NIFTY200 MOMENTUM 30", "NIFTY HIGH BETA 50", "NIFTY100 LOW VOLATILITY 30"]
        trend_list = []
        for name in trending:
            if name in indices:
                idx = indices[name]
                e = _emoji_pct(idx.get("pct", 0))
                short = name.replace("NIFTY ", "").replace("100 ", "")
                trend_list.append(f"{e} {short}: {_pct(idx['pct'])}")
        if trend_list:
            lines.append("")
            lines.append("<b>🔥 Thematic Indices</b>")
            lines.extend(trend_list)

        # Index delta — skip flat comparisons
        if delta and delta.get("indices"):
            id_d = delta["indices"]
            best = id_d.get("best", {})
            worst = id_d.get("worst", {})
            if best and worst:
                b_pct = best.get('pct_change', 0)
                w_pct = worst.get('pct_change', 0)
                if abs(b_pct) >= 0.05 or abs(w_pct) >= 0.05:
                    prev_time_str = _format_prev_time(delta.get("prev_time", ""))
                    lines.append("")
                    lines.append(f"<b>📊 Since Last Check{prev_time_str}:</b>")
                    lines.append(f"  Best:  {best['name']} {best['signal']} ({_pct(b_pct)})")
                    lines.append(f"  Worst: {worst['name']} {worst['signal']} ({_pct(w_pct)})")
                else:
                    lines.append("")
                    lines.append("<i>📊 Indices unchanged since last check</i>")

    return "\n".join(lines)


def format_sector_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """Sector heatmap + top movers (deduplicated, with clickable links)."""
    lines = ["<b>🏭 Sector Analysis</b>", ""]

    sectors = snapshot.get("sectors") or {}
    if not sectors:
        lines.append("No sector data available")
        return "\n".join(lines)

    # Sector heatmap
    lines.append("<b>📊 Sector Heatmap</b>")
    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1].get("index_pct", 0), reverse=True)
    for name, data in sorted_sectors:
        pct = data.get("index_pct", 0)
        e = _emoji_pct(pct)
        disp = _sector_display(name)
        lines.append(f"{e} <b>{disp}</b>: {_pct(pct)} ({data.get('count', 0)} stocks)")

    # Collect and DEDUPLICATE gainers/losers across all sectors
    all_gainers = []
    all_losers = []
    for name, data in sectors.items():
        sector_disp = _sector_display(name)
        for s in data.get("gainers", [])[:3]:
            all_gainers.append({**s, "sector": sector_disp})
        for s in data.get("losers", [])[:3]:
            all_losers.append({**s, "sector": sector_disp})

    # Deduplicate and sort
    all_gainers = _dedup_stocks(all_gainers)
    all_gainers.sort(key=lambda x: x.get("pct", 0), reverse=True)
    all_losers = _dedup_stocks(all_losers)
    all_losers.sort(key=lambda x: x.get("pct", 0))

    # Top Gainers — clickable
    lines.append("")
    lines.append("<b>🏆 Top Gainers</b>")
    for s in all_gainers[:6]:
        lines.append(f"  {_stock_line(s, sectors)}")

    # Top Losers — clickable
    lines.append("")
    lines.append("<b>📉 Top Losers</b>")
    for s in all_losers[:6]:
        lines.append(f"  {_stock_line(s, sectors)}")

    # Highest Value Traded (already deduplicated)
    lines.append("")
    lines.append("<b>💰 Highest Value Traded</b>")
    all_traded = []
    for name, data in sectors.items():
        for s in data.get("most_traded", [])[:3]:
            all_traded.append({**s, "sector": _sector_display(name)})
    
    all_traded = _dedup_stocks(all_traded)
    all_traded.sort(key=lambda x: x.get("value_cr", 0), reverse=True)
    
    for s in all_traded[:5]:
        sym = s['symbol']
        w52_emoji = _52w_emoji(s['last'], s.get('year_low', 0), s.get('year_high', 0))
        w52_pos = _52w_position(s['last'], s.get('year_low', 0), s.get('year_high', 0))
        lines.append(
            f"  {_nse_link(sym)} <b>₹{s['last']:,.0f}</b> ({_pct(s['pct'])}) "
            f"Vol:{_vol(s.get('volume', 0))} Val:₹{s.get('value_cr', 0):,.0f}Cr "
            f"{w52_emoji}{w52_pos}"
        )

    # 52-Week Alerts — DEDUPLICATED
    lines.append("")
    lines.append("<b>🎯 52-Week Alerts</b>")
    all_stocks_raw = []
    for name, data in sectors.items():
        for s in data.get("stocks", []):
            all_stocks_raw.append({**s, "sector": _sector_display(name)})
    all_stocks = _dedup_stocks(all_stocks_raw)
    
    near_high = []
    near_low = []
    for s in all_stocks:
        yh, yl = s.get('year_high', 0), s.get('year_low', 0)
        if yh == 0 or yl == 0 or yh == yl:
            continue
        rng = yh - yl
        pos_pct = ((s['last'] - yl) / rng) * 100
        if pos_pct >= 95:
            near_high.append({**s, 'pos_pct': pos_pct})
        elif pos_pct <= 5:
            near_low.append({**s, 'pos_pct': pos_pct})
    
    near_high = sorted(near_high, key=lambda x: x['pos_pct'], reverse=True)[:5]
    near_low = sorted(near_low, key=lambda x: x['pos_pct'])[:5]
    
    if near_high:
        lines.append("<i>🔥 Near 52-Week High (Breakout Zone):</i>")
        for s in near_high:
            dist = ((s['year_high'] - s['last']) / s['last']) * 100
            lines.append(
                f"  {_nse_link(s['symbol'])} ₹{s['last']:,.1f} → "
                f"52W High ₹{s['year_high']:,.1f} ({dist:+.1f}% away)"
            )
    
    if near_low:
        lines.append("<i>💎 Near 52-Week Low (Potential Reversal — LONG only, not SHORT):</i>")
        for s in near_low:
            dist = ((s['last'] - s['year_low']) / s['last']) * 100
            lines.append(
                f"  {_nse_link(s['symbol'])} ₹{s['last']:,.1f} → "
                f"52W Low ₹{s['year_low']:,.1f} ({dist:+.1f}% above)"
            )
    
    if not near_high and not near_low:
        lines.append("<i>No stocks near 52-week extremes currently</i>")

    # Delta: Big Movers — DEDUPLICATED
    if delta and delta.get("sectors"):
        movers_raw = []
        for name, sd in delta["sectors"].items():
            for m in sd.get("movers", [])[:3]:
                movers_raw.append({**m, "sector": _sector_display(name)})
        # Dedup movers by symbol
        seen_movers = {}
        for m in movers_raw:
            sym = m.get("symbol", "")
            if sym not in seen_movers or abs(m.get("price_chg_pct", 0)) > abs(seen_movers[sym].get("price_chg_pct", 0)):
                seen_movers[sym] = m
        movers_unique = sorted(seen_movers.values(), key=lambda x: abs(x.get("price_chg_pct", 0)), reverse=True)
        if movers_unique:
            prev_time_str = _format_prev_time(delta.get("prev_time", ""))
            lines.append("")
            lines.append(f"<b>🔄 Big Movers Since Last Check{prev_time_str}</b>")
            for m in movers_unique[:6]:
                lines.append(
                    f"  {m['signal']} {_nse_link(m['symbol'])}: "
                    f"{_pct(m['price_chg_pct'])} (₹{m['price_prev']:.1f}→₹{m['price_curr']:.1f})"
                )

    return "\n".join(lines)


def format_options_msg(snapshot: Dict) -> str:
    """Option chain PCR analysis."""
    lines = ["<b>📊 Options Analysis</b>", ""]

    oc = snapshot.get("option_chain") or {}
    if not oc:
        lines.append("No options data available")
        return "\n".join(lines)

    for sym, data in oc.items():
        pcr = data.get("pcr_oi", 0)
        sig = data.get("signal", "")
        emoji = {"Bullish": "🐂", "Neutral": "😐", "Bearish": "🐻"}.get(sig, "❓")

        lines.append(f"<b>{sym}</b>")
        lines.append(f"PCR (OI): <b>{pcr:.3f}</b> {emoji} {sig}")
        lines.append(f"PCR (Vol): {data.get('pcr_vol', 0):.3f}")
        lines.append(f"Max Pain: <b>{data.get('max_pain', 0):,.0f}</b>")
        lines.append("")

        # Simple explanation
        if pcr > 1.2:
            lines.append(f"💡 <i>More PUTS than CALLS → traders expect market to go UP</i>")
        elif pcr > 0.7:
            lines.append(f"💡 <i>Balanced → market is UNDECIDED</i>")
        else:
            lines.append(f"💡 <i>More CALLS than PUTS → traders expect market to go DOWN</i>")
        lines.append("")

        # Top strikes
        lines.append("Top CALL OI (Resistance):")
        for s in data.get("top_ce", [])[:3]:
            lines.append(f"  🔵 {s['strike']:,.0f}: OI {s['oi']:,} (Δ{s['chg_oi']:+,})")
        lines.append("Top PUT OI (Support):")
        for s in data.get("top_pe", [])[:3]:
            lines.append(f"  🟠 {s['strike']:,.0f}: OI {s['oi']:,} (Δ{s['chg_oi']:+,})")
        lines.append("")

    return "\n".join(lines)


def format_commodities_msg(snapshot: Dict, delta: Optional[Dict] = None, slot_time: str = None) -> str:
    """Commodities + Forex. Forex & Commodity Indices only at pre-market & 9 PM."""
    lines = ["<b>🏆 Commodities & Forex</b>", ""]
    show_extras = _show_fii_forex(slot_time)

    # Commodity ETFs — always shown
    comms = snapshot.get("commodities") or {}
    if comms:
        lines.append("<b>🥇 Commodity ETFs</b>")
        names = {
            "TATAGOLD": "Gold (Tata)",
            "TATSILV": "Silver (Tata)",
            "GOLDBEES": "Gold (Nippon)",
            "LIQUIDBEES": "Liquid ETF",
        }
        headers = ["Commodity", "LTP", "%Chg", "52W Low", "52W High", "Position"]
        rows = []
        for sym, data in comms.items():
            name = names.get(sym, sym)
            w52_pos = _52w_position(data['last'], data.get('week52_low', 0), data.get('week52_high', 0))
            w52_emoji = _52w_emoji(data['last'], data.get('week52_low', 0), data.get('week52_high', 0))
            rows.append([
                name[:16],
                f"₹{data['last']:,.2f}",
                _pct(data['pct']),
                f"₹{data.get('week52_low', 0):,.2f}",
                f"₹{data.get('week52_high', 0):,.2f}",
                f"{w52_emoji}{w52_pos}"
            ])
        table = _make_table(headers, rows, align=['left', 'right', 'right', 'right', 'right', 'center'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
        lines.append("")

    # Commodity Indices — only at pre-market & 9 PM
    if show_extras:
        indices = snapshot.get("indices") or {}
        commodity_indices = ["NIFTY COMMODITIES", "NIFTY OIL & GAS", "NIFTY ENERGY"]
        comm_idx_list = []
        for name in commodity_indices:
            if name in indices:
                idx = indices[name]
                comm_idx_list.append((name.replace("NIFTY ", ""), idx['last'], idx['pct']))
        
        if comm_idx_list:
            lines.append("<b>📈 Commodity Indices</b>")
            headers = ["Index", "Level", "%Change"]
            rows = []
            for name, last, pct in comm_idx_list:
                rows.append([name, f"{last:,.0f}", _pct(pct)])
            table = _make_table(headers, rows, align=['left', 'right', 'right'])
            lines.append("<pre>")
            lines.append(table)
            lines.append("</pre>")
            lines.append("")

    # MCX-linked global commodity drivers (always shown when available)
    mcx = snapshot.get("mcx_drivers") or {}
    if mcx:
        lines.append("<b>⚙️ MCX Driver Proxies</b>")
        headers = ["Contract", "Last", "%Chg"]
        rows = []
        for _, item in mcx.items():
            rows.append([
                item.get("name", ""),
                f"{item.get('last', 0):,.2f}",
                _pct(float(item.get("pct", 0) or 0)),
            ])
        table = _make_table(headers, rows, align=['left', 'right', 'right'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
        lines.append("<i>These are global futures proxies used as MCX sentiment drivers</i>")
        lines.append("")

    # Phase 3 macro expansion: DXY + Brent alongside USD/INR
    gs = snapshot.get("global_sentiment") or {}
    macro = gs.get("macro") or {}
    dxy = (macro.get("DXY") or {})
    brent = (macro.get("BRENT") or {})
    if dxy or brent:
        lines.append("<b>🧭 Macro Watch</b>")
        headers = ["Metric", "Last", "%Chg"]
        rows = []
        if dxy:
            rows.append([
                "DXY",
                f"{float(dxy.get('last', 0) or 0):,.2f}",
                _pct(float(dxy.get('pct', 0) or 0)),
            ])
        if brent:
            rows.append([
                "Brent",
                f"${float(brent.get('last', 0) or 0):,.2f}",
                _pct(float(brent.get('pct', 0) or 0)),
            ])
        if rows:
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=['left', 'right', 'right']))
            lines.append("</pre>")
            lines.append("")

    # Forex — only at pre-market & 9 PM
    forex = snapshot.get("forex")
    if forex and show_extras:
        lines.append("<b>💱 Currency Rates</b>")
        headers = ["Pair", "Rate", "Change"]
        rows = [["USD/INR", f"₹{forex['usdinr']:.4f}", ""]]
        
        if forex.get("usdeur"):
            rows.append(["USD/EUR", f"€{forex['usdeur']:.4f}", ""])
        if forex.get("usdgbp"):
            rows.append(["USD/GBP", f"£{forex['usdgbp']:.4f}", ""])

        if delta and delta.get("forex"):
            fd = delta["forex"]
            if fd["change"] != 0:  # suppress 'Unchanged +0.0000' — same API snapshot between runs
                rows[0][2] = f"{fd['direction']} {fd['change']:+.4f}"
        
        table = _make_table(headers, rows, align=['left', 'right', 'left'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
    elif forex and not show_extras:
        lines.append(f"💱 USD/INR: <b>₹{forex['usdinr']:.4f}</b> <i>(detail at 9 PM)</i>")

    return "\n".join(lines)


def format_corporate_msg(snapshot: Dict, data_dir: str = None) -> str:
    """Corporate actions + insider trading. Only shows UPCOMING events (today → +21 days),
    skips any row where all key data is 0/null/blank."""
    lines = ["<b>📋 Corporate Actions & Insider Trading</b>", ""]

    today = datetime.now().date()
    cutoff = today + timedelta(days=21)

    def _is_upcoming(action):
        """Return True only if ex_date is today or within next 21 days."""
        ex = _parse_action_date(action.get('ex_date', ''))
        return ex is not None and today <= ex <= cutoff

    def _source_badge(action):
        src = action.get('source', 'NSE')
        return f"[{src}]" if src else "[NSE]"

    # Corporate actions — filter to upcoming 21 days only
    actions = snapshot.get("corporate_actions")
    src_counts = snapshot.get("corporate_sources") or {}
    if src_counts:
        src_text = ", ".join(f"{k}:{v}" for k, v in sorted(src_counts.items()))
        lines.append(f"<i>Live Sources → {src_text}</i>")
        lines.append("")

    health = snapshot.get("feed_health") or {}
    if health:
        lines.append("<b>🩺 Feed Health</b>")
        status_map = {
            "ok": "🟢 ok",
            "no-data": "🟡 no-data",
            "error": "🔴 error",
        }
        rows = []
        for key in ("NSE_CA", "BSE_CA", "NSE_BM", "NSE_ANN", "NSE_ER", "DIV_CSV", "MCX_DRV"):
            h = health.get(key) or {}
            status = str(h.get("status", "-")).strip() or "-"
            status_disp = status_map.get(status, status)
            cnt = int(h.get("last_count", 0) or 0)
            succ = str(h.get("last_success", "") or "")
            succ_disp = succ[11:19] if len(succ) >= 19 else (succ[:19] if succ else "-")
            rows.append([key, status_disp, str(cnt), succ_disp])
        table = _make_table(["Feed", "Status", "Count", "Last OK"], rows, align=['left', 'left', 'right', 'left'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
        lines.append("")

    mcx = snapshot.get("mcx_drivers") or {}
    if mcx:
        lines.append("<b>⚙️ MCX Price Drivers</b>")
        headers = ["Contract", "Last", "%Chg"]
        rows = []
        for _, item in mcx.items():
            rows.append([
                item.get("name", ""),
                f"{item.get('last', 0):,.2f}",
                _pct(float(item.get("pct", 0) or 0)),
            ])
        table = _make_table(headers, rows, align=['left', 'right', 'right'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
        lines.append("")
    if actions:
        upcoming = [a for a in actions if _is_upcoming(a)]
        if upcoming:
            lines.append(f"<b>📌 Upcoming Corporate Actions — Next 21 Days ({len(upcoming)} events)</b>")
            lines.append("")

            dividends = [a for a in upcoming if "dividend" in a.get("subject", "").lower()]
            buybacks  = [a for a in upcoming if _action_category(a.get("subject", "")) == "buyback"]
            splits    = [a for a in upcoming if "split"    in a.get("subject", "").lower()]
            bonus     = [a for a in upcoming if "bonus"    in a.get("subject", "").lower()]
            others    = [a for a in upcoming
                         if a not in dividends and a not in buybacks and a not in splits and a not in bonus]

            if dividends:
                # Build annual dividend totals from stored snapshots (zero API calls)
                annual_totals: dict = {}
                if data_dir:
                    try:
                        annual_totals = _build_annual_dividend_totals(data_dir)
                    except Exception:
                        pass

                # For symbols shown in this message, backfill missing FY totals from internet.
                # Local snapshot data remains the source of truth when available.
                def _src_rank(src: str) -> int:
                    s = str(src or "").upper()
                    if "NSE" in s and "ANN" not in s:
                        return 4
                    if "BSE" in s:
                        return 3
                    if "ANN" in s:
                        return 2
                    if "CSV" in s:
                        return 1
                    return 0

                # De-duplicate same dividend event across NSE/BSE/ANN rows and
                # prefer entries with amount+LTP to keep Yield values usable.
                dedup: Dict[tuple, Dict[str, Any]] = {}
                for d in dividends:
                    sym = str(d.get("symbol", "") or "").strip().upper()
                    ex_raw = str(d.get("ex_date", "") or "").strip()
                    if not sym or not ex_raw:
                        continue
                    parts = _extract_dividend_amounts(str(d.get("subject", "") or ""))
                    div_amt = round(sum(parts), 4)
                    key = (sym, ex_raw, div_amt)
                    try:
                        ltp = float(d.get("ltp") or 0)
                    except (ValueError, TypeError):
                        ltp = 0.0
                    cur = dedup.get(key)
                    if not cur:
                        dedup[key] = d
                        continue
                    cur_parts = _extract_dividend_amounts(str(cur.get("subject", "") or ""))
                    cur_div = round(sum(cur_parts), 4)
                    try:
                        cur_ltp = float(cur.get("ltp") or 0)
                    except (ValueError, TypeError):
                        cur_ltp = 0.0
                    cur_score = (1 if cur_div > 0 else 0, 1 if cur_ltp > 0 else 0, _src_rank(cur.get("source", "")))
                    new_score = (1 if div_amt > 0 else 0, 1 if ltp > 0 else 0, _src_rank(d.get("source", "")))
                    if new_score > cur_score:
                        dedup[key] = d

                preview_divs = list(dedup.values())

                def _div_sort_key(x: Dict[str, Any]):
                    exd = _parse_action_date(x.get('ex_date', '')) or today
                    parts = _extract_dividend_amounts(str(x.get("subject", "") or ""))
                    div_amt = round(sum(parts), 4)
                    try:
                        ltp = float(x.get("ltp") or 0)
                    except (ValueError, TypeError):
                        ltp = 0.0
                    y = (div_amt / ltp * 100) if (div_amt > 0 and ltp > 0) else -1.0
                    return (exd, -y, str(x.get("symbol", "")))

                preview_divs.sort(key=_div_sort_key)

                fallback_symbols = [
                    d.get("symbol", "") for d in preview_divs[:25] if d.get("symbol", "")
                ]
                if fallback_symbols:
                    try:
                        annual_totals = _fill_missing_annual_totals_online(fallback_symbols, annual_totals)
                    except Exception:
                        pass

                lines.append("<b>💰 Upcoming Dividends:</b>")
                lines.append("<i>Yield = this div \u00f7 LTP | Ann.Yield = prior-year total \u00f7 LTP</i>")
                lines.append("")
                shown = 0
                high_yield_rows = []
                for a in preview_divs:
                    sym      = a.get('symbol', '')
                    subject  = a.get('subject', '')
                    ex_date  = a.get('ex_date', '')
                    badge    = _source_badge(a)
                    try:
                        ltp_val = float(a.get('ltp') or 0)
                    except (ValueError, TypeError):
                        ltp_val = 0.0
                    try:
                        pe_val = float(a.get('pe') or 0)
                    except (ValueError, TypeError):
                        pe_val = 0.0
                    div_parts = _extract_dividend_amounts(subject)
                    div_amt   = round(sum(div_parts), 4)
                    div_type  = _div_type_tag(subject)
                    yield_pct = round(div_amt / ltp_val * 100, 2) if (ltp_val > 0 and div_amt > 0) else 0.0

                    # Annual dividend for this symbol (from stored snapshots)
                    annual_div   = 0.0
                    annual_label = ""
                    ann_raw      = annual_totals.get(sym)
                    if isinstance(ann_raw, dict):
                        annual_div   = float(ann_raw.get("total", 0) or 0)
                        annual_label = ann_raw.get("label", "Annual")
                    elif ann_raw:
                        annual_div   = float(ann_raw)
                        annual_label = "Annual"
                    annual_yield = round(annual_div / ltp_val * 100, 2) if (ltp_val > 0 and annual_div > 0) else 0.0

                    # "Per ₹1000 invested" metric — intuitive for retail investors
                    per_1000 = round(div_amt / ltp_val * 1000, 2) if (ltp_val > 0 and div_amt > 0) else 0.0

                    # Skip row if we have no useful data at all
                    if not sym or not ex_date:
                        continue
                    # Skip amount-less rows to avoid noisy entries with no yield context.
                    if div_amt == 0:
                        continue

                    # Build display strings (never show "—" for zero values — skip the field)
                    ltp_str      = f"₹{ltp_val:,.2f}" if ltp_val else None
                    pe_str       = f"PE:{pe_val:.1f}" if pe_val > 0 else None
                    div_str      = f"₹{div_amt:.2f}" if div_amt else None
                    # Yield: show N/A when div is known but LTP is missing (can't calculate)
                    yield_str    = f"{yield_pct:.2f}%" if yield_pct > 0 else ("N/A" if (div_amt > 0 and ltp_val == 0) else None)
                    yind         = _yield_indicator(yield_pct) if yield_pct > 0 else ""
                    per1k_str    = f"₹{per_1000:.2f}/₹1k" if per_1000 else None
                    # Annual: show whenever historical total exists (prev year preferred)
                    annual_str   = f"₹{annual_div:.2f}" if annual_div > 0 else None
                    ann_yld_str  = f"{annual_yield:.2f}%" if annual_yield else None

                    link = _nse_link(sym)
                    # Line 1: symbol, LTP, PE (if available)
                    line1_parts = [f"  {link} <i>{badge}</i>"]
                    if ltp_str:
                        line1_parts.append(f"LTP: <b>{ltp_str}</b>")
                    if pe_str:
                        line1_parts.append(pe_str)
                    lines.append(" | ".join(line1_parts))

                    # Line 2: dividend amount, yield (or N/A if no LTP), per-1000 metric
                    line2_parts = []
                    if div_str:
                        if len(div_parts) > 1:
                            pieces = "+".join(f"{x:g}" for x in div_parts)
                            line2_parts.append(f"{div_type}: <b>{div_str}</b> (₹{pieces})")
                        else:
                            line2_parts.append(f"{div_type}: <b>{div_str}</b>")
                    if yield_str:
                        yield_display = f"Yield: <b>{yield_str}{yind}</b>" if yield_str != "N/A" else "Yield: <i>N/A (no LTP)</i>"
                        line2_parts.append(yield_display)
                    if per1k_str:
                        line2_parts.append(per1k_str)
                    if line2_parts:
                        lines.append("  " + " | ".join(line2_parts))

                    # Line 3: annual total labelled with year (e.g. FY2025 or 2026 YTD)
                    line3_parts = []
                    if annual_str and annual_label:
                        line3_parts.append(f"{annual_label}: ₹{annual_div:.2f}")
                    if ann_yld_str:
                        line3_parts.append(f"Ann.Yield: {ann_yld_str}")
                    if line3_parts:
                        lines.append("  📊 " + " | ".join(line3_parts))

                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")

                    if yield_pct >= 2.0 and ltp_val > 0:
                        high_yield_rows.append({
                            "symbol": sym,
                            "yield": yield_pct,
                            "div": div_amt,
                            "ltp": ltp_val,
                            "date": ex_date,
                            "source": badge,
                        })

                    shown += 1
                    if shown >= 10:
                        remaining = len(dividends) - shown
                        if remaining > 0:
                            lines.append(
                                f"  <i>... and {remaining} more dividend actions "
                                f"(see 📄 All Dividends message below)</i>"
                            )
                            lines.append("")
                        break

                if high_yield_rows:
                    lines.append("<b>⭐ High-Yield Dividends (Yield > 2%)</b>")
                    for row in sorted(high_yield_rows, key=lambda x: x["yield"], reverse=True)[:8]:
                        lines.append(
                            f"  ⭐ {_nse_link(row['symbol'])} <i>{row['source']}</i> | "
                            f"Yield <b>{row['yield']:.2f}%</b> | Div ₹{row['div']:.2f} | "
                            f"LTP ₹{row['ltp']:.2f} | Ex {row['date']}"
                        )
                    lines.append("")

            if splits:
                lines.append("<b>✂️ Upcoming Stock Splits:</b>")
                for a in sorted(splits, key=lambda x: _parse_action_date(x.get('ex_date','')) or today)[:5]:
                    sym     = a.get('symbol', '')
                    subject = a.get('subject', '')[:120]
                    ex_date = a.get('ex_date', '')
                    badge   = _source_badge(a)
                    if not sym or not ex_date:
                        continue
                    try:
                        ltp_val = float(a.get('ltp') or 0)
                    except (ValueError, TypeError):
                        ltp_val = 0.0
                    ltp_str = f"₹{ltp_val:,.2f}" if ltp_val else "—"
                    lines.append(f"  {_nse_link(sym)} <i>{badge}</i> | LTP: {ltp_str}")
                    lines.append(f"  {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")

            if bonus:
                lines.append("<b>🎁 Upcoming Bonus Issues:</b>")
                for a in sorted(bonus, key=lambda x: _parse_action_date(x.get('ex_date','')) or today)[:5]:
                    sym     = a.get('symbol', '')
                    subject = a.get('subject', '')[:120]
                    ex_date = a.get('ex_date', '')
                    badge   = _source_badge(a)
                    if not sym or not ex_date:
                        continue
                    try:
                        ltp_val = float(a.get('ltp') or 0)
                    except (ValueError, TypeError):
                        ltp_val = 0.0
                    ltp_str = f"₹{ltp_val:,.2f}" if ltp_val else "—"
                    lines.append(f"  {_nse_link(sym)} <i>{badge}</i> | LTP: {ltp_str}")
                    lines.append(f"  {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")

            if buybacks:
                lines.append("<b>🏷️ Upcoming Buybacks:</b>")
                # Consolidate best-known values per (symbol, ex-date) across sources.
                # NSE often has the event row while announcement row may carry richer text.
                bb_best: Dict[tuple, Dict[str, float]] = {}
                for x in buybacks:
                    k = (x.get("symbol", ""), x.get("ex_date", ""))
                    if not all(k):
                        continue
                    try:
                        x_ltp = float(x.get("ltp") or 0)
                    except (ValueError, TypeError):
                        x_ltp = 0.0
                    try:
                        x_offer = float(x.get("offer_price") or x.get("buyback_price") or 0)
                    except (ValueError, TypeError):
                        x_offer = 0.0
                    if x_offer <= 0:
                        x_offer = _extract_buyback_price(str(x.get("subject", "") or ""))
                    cur = bb_best.get(k, {"ltp": 0.0, "offer": 0.0})
                    bb_best[k] = {
                        "ltp": max(cur.get("ltp", 0.0), x_ltp),
                        "offer": max(cur.get("offer", 0.0), x_offer),
                    }

                for a in sorted(buybacks, key=lambda x: _parse_action_date(x.get('ex_date', '')) or today)[:6]:
                    sym = a.get('symbol', '')
                    subject = a.get('subject', '')[:140]
                    ex_date = a.get('ex_date', '')
                    badge = _source_badge(a)
                    if not sym or not ex_date:
                        continue
                    best = bb_best.get((sym, ex_date), {})
                    try:
                        ltp_val = float(best.get("ltp") or a.get('ltp') or 0)
                    except (ValueError, TypeError):
                        ltp_val = 0.0
                    try:
                        offer = float(best.get("offer") or a.get("offer_price") or a.get("buyback_price") or 0)
                    except (ValueError, TypeError):
                        offer = 0.0
                    if offer <= 0:
                        offer = _extract_buyback_price(subject)
                    premium_pct = ((offer - ltp_val) / ltp_val * 100) if (offer > 0 and ltp_val > 0) else 0.0
                    lines.append(f"  {_nse_link(sym)} <i>{badge}</i>")
                    if offer > 0 and ltp_val > 0:
                        lines.append(
                            f"  Offer: <b>₹{offer:,.2f}</b> | LTP: ₹{ltp_val:,.2f} | "
                            f"Premium: <b>{premium_pct:+.2f}%</b>"
                        )
                    elif offer > 0:
                        lines.append(f"  Offer: <b>₹{offer:,.2f}</b> | LTP: —")
                    elif ltp_val > 0:
                        lines.append(f"  Offer: <i>N/A (not in exchange feed)</i> | LTP: ₹{ltp_val:,.2f}")
                    else:
                        lines.append("  Offer: <i>N/A (not in exchange feed)</i> | LTP: —")
                    lines.append(f"  {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")

            if others:
                lines.append("<b>📋 Other Actions:</b>")
                for a in sorted(others, key=lambda x: _parse_action_date(x.get('ex_date','')) or today)[:3]:
                    sym     = a.get('symbol', '')
                    subject = a.get('subject', '')[:120]
                    ex_date = a.get('ex_date', '')
                    badge   = _source_badge(a)
                    if not sym or not ex_date:
                        continue
                    lines.append(f"  {_nse_link(sym)} <i>{badge}</i> — {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")

            # If ALL sections ended up empty after null-filtering
            total_shown = sum(1 for l in lines if "Ex-Date:" in l)
            if total_shown == 0:
                lines.append("<i>No upcoming corporate actions with complete data</i>")
        else:
            lines.append("<i>No upcoming corporate actions in the next 21 days</i>")
    else:
        lines.append("<i>No corporate actions data available</i>")

    earnings = snapshot.get("earnings_calendar") or []
    if earnings:
        lines.append("")
        lines.append(f"<b>🧾 Upcoming Earnings (Next 21 Days): {len(earnings)}</b>")
        headers = ["Symbol", "Date", "Purpose", "Src"]
        rows = []
        for e in earnings[:12]:
            rows.append([
                str(e.get("symbol", ""))[:12],
                str(e.get("date", ""))[:11],
                str(e.get("purpose", ""))[:28],
                str(e.get("source", "NSE-ER"))[:7],
            ])
        table = _make_table(headers, rows, align=['left', 'left', 'left', 'left'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
        if len(earnings) > 12:
            lines.append(f"<i>... and {len(earnings)-12} more earnings events</i>")

    lines.append("")
    lines.append("─" * 40)
    lines.append("")

    # Insider trading
    insiders = snapshot.get("insider_trading")
    if insiders:
        lines.append(f"<b>🔍 Insider Trading ({len(insiders)} trades)</b>")
        lines.append("<i>When promoters/directors buy or sell in their own company</i>")
        lines.append("")
        lines.append("<b>📖 Understanding Signals:</b>")
        lines.append("  🟢 <b>Bullish Signal</b>: Insider buying = confidence in company")
        lines.append("  🔴 <b>Caution Signal</b>: Insider selling = possible concerns")
        lines.append("  ⚠️ Large insider trades often precede major price moves")
        lines.append("")

        big_buys = sorted([t for t in insiders if t["buy_value"] > t["sell_value"]], 
                         key=lambda x: x["buy_value"], reverse=True)[:5]
        big_sells = sorted([t for t in insiders if t["sell_value"] > t["buy_value"]], 
                          key=lambda x: x["sell_value"], reverse=True)[:5]

        if big_buys:
            lines.append("🟢 <b>Top Insider Buys (Bullish Signal):</b>")
            headers = ["Symbol", "Buyer", "Value"]
            rows = []
            for t in big_buys:
                val = t["buy_value"]
                if val >= 1e7:
                    val_str = f"₹{val/1e7:.1f}Cr"
                else:
                    val_str = f"₹{val/1e5:.1f}L"
                rows.append([
                    t['symbol'][:10],
                    t['acquirer'][:20],
                    val_str
                ])
            table = _make_table(headers, rows, align=['left', 'left', 'right'])
            lines.append("<pre>")
            lines.append(table)
            lines.append("</pre>")
            lines.append("")

        if big_sells:
            lines.append("🔴 <b>Top Insider Sells (Caution Signal):</b>")
            headers = ["Symbol", "Seller", "Value"]
            rows = []
            for t in big_sells:
                val = t["sell_value"]
                if val >= 1e7:
                    val_str = f"₹{val/1e7:.1f}Cr"
                else:
                    val_str = f"₹{val/1e5:.1f}L"
                rows.append([
                    t['symbol'][:10],
                    t['acquirer'][:20],
                    val_str
                ])
            table = _make_table(headers, rows, align=['left', 'left', 'right'])
            lines.append("<pre>")
            lines.append(table)
            lines.append("</pre>")
            lines.append("")

        lines.append("💡 <i>Insider buying = Bullish | Insider selling = Caution</i>")
    else:
        lines.append("No insider trading data this week")

    return "\n".join(lines)


def format_corporate_dividends_table_msg(snapshot: Dict) -> Optional[str]:
    """Compact table with all upcoming dividend actions (today → +21 days).

    Telegram does not support native collapsible sections, so this provides
    a scrollable full list as a follow-up message.
    """
    today = datetime.now().date()
    cutoff = today + timedelta(days=21)

    actions = snapshot.get("corporate_actions") or []
    if not actions:
        return (
            "<b>📄 All Upcoming Dividends (0)</b>\n"
            "<i>No dividend actions found in the next 21 days from current live sources.</i>"
        )

    def _src_rank(src: str) -> int:
        s = str(src or "").upper()
        if "NSE" in s and "ANN" not in s:
            return 4
        if "BSE" in s:
            return 3
        if "ANN" in s:
            return 2
        if "CSV" in s:
            return 1
        return 0

    # Build unique dividend events and prefer rows with richer price data.
    # Announcement-only rows often lack amounts and can create noisy "-" values.
    by_event: Dict[tuple, Dict[str, Any]] = {}
    for a in actions:
        subject = str(a.get("subject", "") or "")
        if "dividend" not in subject.lower():
            continue
        exd = _parse_action_date(a.get("ex_date", ""))
        if not exd or exd < today or exd > cutoff:
            continue

        div_parts = _extract_dividend_amounts(subject)
        div = round(sum(div_parts), 4)
        if div <= 0:
            # Hide amount-less rows to avoid confusing dashes in the all-dividends table.
            continue

        sym = (a.get("symbol") or "").strip().upper()
        if not sym:
            continue

        try:
            ltp = float(a.get("ltp") or 0)
        except (ValueError, TypeError):
            ltp = 0.0
        yld = (div / ltp * 100) if (div > 0 and ltp > 0) else None

        evt_key = (sym, exd.isoformat(), round(div, 4))
        cur = by_event.get(evt_key)
        candidate = {
            "sym": sym,
            "exd": exd,
            "div": div,
            "div_parts": div_parts,
            "ltp": ltp,
            "yield": yld,
            "source": a.get("source", "NSE"),
        }
        if not cur:
            by_event[evt_key] = candidate
            continue

        cur_score = (
            1 if cur.get("yield") is not None else 0,
            1 if (cur.get("ltp") or 0) > 0 else 0,
            _src_rank(cur.get("source", "")),
        )
        new_score = (
            1 if candidate.get("yield") is not None else 0,
            1 if (candidate.get("ltp") or 0) > 0 else 0,
            _src_rank(candidate.get("source", "")),
        )
        if new_score > cur_score:
            by_event[evt_key] = candidate

    events = list(by_event.values())
    if not events:
        return (
            "<b>📄 All Upcoming Dividends (0)</b>\n"
            "<i>No dividend actions with amount details available for the next 21 days.</i>"
        )

    events.sort(
        key=lambda e: (
            e["exd"],
            -(e["yield"] if e["yield"] is not None else -1.0),
            e["sym"],
        )
    )

    rows: List[List[str]] = []
    for e in events:
        div_str = f"₹{e['div']:.2f}"
        if len(e.get("div_parts") or []) > 1:
            div_str = f"₹{e['div']:.2f}({len(e['div_parts'])}x)"
        rows.append([
            e["sym"][:12],
            e["exd"].strftime("%d-%b"),
            div_str,
            f"{e['yield']:.2f}" if e["yield"] is not None else "NA",
        ])

    # Keep message under Telegram's 4096-char hard limit while preserving valid HTML.
    total_rows = len(rows)
    max_rows = total_rows
    msg = ""
    while max_rows > 0:
        shown_rows = rows[:max_rows]
        table = _make_table(
            ["Symbol", "Ex-Date", "Div", "Yield%"],
            shown_rows,
            align=["left", "left", "right", "right"],
        )
        table = html.escape(table, quote=False)

        high_yield = [e for e in events if (e.get("yield") or 0) >= 2.0]
        hy_line = ""
        if high_yield:
            top = sorted(high_yield, key=lambda x: x.get("yield") or 0, reverse=True)[:8]
            hy_line = "<b>Yield ≥ 2%:</b> " + ", ".join(
                f"<b>{html.escape(x['sym'])}</b> ({x['yield']:.2f}%)" for x in top if x.get("yield") is not None
            )

        lines = [
            f"<b>📄 All Upcoming Dividends ({total_rows})</b>",
            "<i>Sorted by Ex-Date, then highest yield first for each date.</i>",
            hy_line,
            "",
            "<pre>",
            table,
            "</pre>",
        ]
        if max_rows < total_rows:
            lines.append(f"<i>Showing first {max_rows}/{total_rows} rows (Telegram length limit).</i>")

        msg = "\n".join(lines)
        if len(msg) <= MAX_MSG_LEN:
            return msg

        max_rows -= 8

    return "<b>📄 All Upcoming Dividends</b>\n<i>Dividend table unavailable due formatting size constraints.</i>"


def format_preopen_msg(snapshot: Dict) -> str:
    """Pre-open market analysis."""
    po = snapshot.get("preopen")
    if not po:
        return "<b>🌅 Pre-Open Market</b>\n\nPre-open data not available"

    lines = ["<b>🌅 Pre-Open Market Analysis</b>", ""]

    # India VIX context for pre-market risk framing
    vix = (snapshot.get("indices") or {}).get("INDIA VIX", {})
    if vix:
        try:
            vix_last = float(vix.get("last", 0) or 0)
            vix_pct = float(vix.get("pct", 0) or 0)
        except (TypeError, ValueError):
            vix_last, vix_pct = 0.0, 0.0
        if vix_last > 0:
            if vix_last >= 24:
                risk = "High Fear"
            elif vix_last >= 18:
                risk = "Elevated"
            elif vix_last >= 13:
                risk = "Normal"
            else:
                risk = "Calm"
            lines.append(f"<b>😶 India VIX:</b> {vix_last:.2f} ({_pct(vix_pct)}) • {risk}")
            lines.append("")

    # Global cues before Indian market open
    gidx = snapshot.get("global_indices") or {}
    if gidx:
        parts = []
        for name in ("S&P 500", "NASDAQ", "DOW", "NIKKEI", "HANG SENG", "FTSE"):
            d = gidx.get(name)
            if not d:
                continue
            parts.append(f"{name}:{_pct(float(d.get('pct', 0) or 0))}")
        if parts:
            lines.append("<b>🌍 Global Cues:</b>")
            lines.append("  " + " | ".join(parts[:4]))
            if len(parts) > 4:
                lines.append("  " + " | ".join(parts[4:]))
            lines.append("")

    fg = ((snapshot.get("global_sentiment") or {}).get("fear_greed") or {})
    if fg:
        try:
            score = float(fg.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        rating = str(fg.get("rating", "") or "").title()
        lines.append(f"<b>😶‍🌫️ Fear & Greed:</b> {score:.1f}/100 ({rating})")
        lines.append("")

    lines.append(f"Advances: 🟢 {po.get('advances', 0)} | Declines: 🔴 {po.get('declines', 0)}")
    lines.append("")

    gainers = po.get("gainers", [])
    losers = po.get("losers", [])

    if gainers:
        lines.append("<b>🟢 Pre-Open Gainers:</b>")
        for s in gainers[:5]:
            lines.append(f"  {_nse_link(s['symbol'])} ₹{s['iep']:,.1f} ({_pct(s['pct'])})")

    if losers:
        lines.append("")
        lines.append("<b>🔴 Pre-Open Losers:</b>")
        for s in losers[:5]:
            lines.append(f"  {_nse_link(s['symbol'])} ₹{s['iep']:,.1f} ({_pct(s['pct'])})")

    lines.append("")
    lines.append("💡 <i>Pre-open shows where stocks will start trading today</i>")
    return "\n".join(lines)


def format_52w_alerts_msg(snapshot: Dict) -> Optional[str]:
    """Standalone 52-week alerts message (used by interactive_bot)."""
    sectors = snapshot.get("sectors") or {}
    if not sectors:
        return None

    all_stocks = []
    for name, data in sectors.items():
        for s in data.get("stocks", []):
            s_copy = {**s, "sector": name.replace("NIFTY ", "")}
            all_stocks.append(s_copy)

    near_high, near_low = [], []
    for s in all_stocks:
        yh, yl = s.get("year_high", 0), s.get("year_low", 0)
        if yh == 0 or yl == 0 or yh == yl:
            continue
        pos = ((s["last"] - yl) / (yh - yl)) * 100
        if pos >= 95:
            near_high.append({**s, "pos_pct": pos})
        elif pos <= 5:
            near_low.append({**s, "pos_pct": pos})

    if not near_high and not near_low:
        return None

    lines = ["<b>🎯 52-Week Alerts</b>", ""]
    if near_high:
        near_high.sort(key=lambda x: x["pos_pct"], reverse=True)
        lines.append("<b>🔥 Near 52-Week High (Breakout Zone):</b>")
        headers = ["Symbol", "LTP", "52W High", "Dist", "Sector"]
        rows = []
        for s in near_high[:10]:
            dist = ((s["year_high"] - s["last"]) / s["last"]) * 100
            rows.append([
                s["symbol"][:10], f"₹{s['last']:,.1f}",
                f"₹{s['year_high']:,.1f}", f"{dist:+.1f}%",
                s["sector"][:12],
            ])
        lines.append("<pre>")
        lines.append(_make_table(headers, rows, align=["left", "right", "right", "right", "left"]))
        lines.append("</pre>")
        lines.append("")

    if near_low:
        near_low.sort(key=lambda x: x["pos_pct"])
        lines.append("<b>💎 Near 52-Week Low (Potential Reversal — LONG bias only):</b>")
        lines.append("<i>⚠ These are value zones for reversal. Do NOT short near 52W lows.</i>")
        headers = ["Symbol", "LTP", "52W Low", "Dist", "Sector"]
        rows = []
        for s in near_low[:10]:
            dist = ((s["last"] - s["year_low"]) / s["last"]) * 100
            rows.append([
                s["symbol"][:10], f"₹{s['last']:,.1f}",
                f"₹{s['year_low']:,.1f}", f"{dist:+.1f}%",
                s["sector"][:12],
            ])
        lines.append("<pre>")
        lines.append(_make_table(headers, rows, align=["left", "right", "right", "right", "left"]))
        lines.append("</pre>")

    return "\n".join(lines)


def format_bulk_deals_msg(snapshot: Dict) -> str:
    """Bulk & Block Deals - Large off-market and on-exchange trades.
    
    Analysis includes:
    - Client accumulation/distribution patterns
    - Stock-wise buy vs sell pressure
    - Institutional vs retail participation signals
    """
    lines = ["<b>💼 Bulk & Block Deals</b>", ""]
    
    bulk_deals = snapshot.get("bulk_deals") or []
    block_deals = snapshot.get("block_deals") or []
    
    if not bulk_deals and not block_deals:
        lines.append("No large deals reported today")
        return "\n".join(lines)
    
    # === BULK DEALS (off-market) ===
    if bulk_deals:
        lines.append(f"<b>📦 Bulk Deals ({len(bulk_deals)})</b>")
        lines.append("<i>Off-market large volume trades (>0.5% of shares)</i>")
        lines.append("")
        
        # Separate buys and sells
        buys = [d for d in bulk_deals if d["trade_type"] == "BUY"]
        sells = [d for d in bulk_deals if d["trade_type"] == "SELL"]
        
        # Accumulation analysis
        symbol_net = {}
        for d in bulk_deals:
            sym = d["symbol"]
            val = d["value_cr"] if d["trade_type"] == "BUY" else -d["value_cr"]
            symbol_net[sym] = symbol_net.get(sym, 0) + val
        
        # Top buys
        if buys:
            lines.append(f"<b>🟢 Top Bulk Buys ({len(buys)} deals):</b>")
            headers = ["Symbol", "Client", "Qty", "Price", "Value"]
            rows = []
            for d in buys[:8]:
                client = d["client"][:20]
                if len(d["client"]) > 20:
                    client += "..."
                rows.append([
                    d["symbol"][:10],
                    client,
                    _vol(d["qty"]),
                    f"₹{d['price']:,.1f}",
                    f"₹{d['value_cr']:.1f}Cr"
                ])
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=["left", "left", "right", "right", "right"]))
            lines.append("</pre>")
            lines.append("")
        
        # Top sells
        if sells:
            lines.append(f"<b>🔴 Top Bulk Sells ({len(sells)} deals):</b>")
            headers = ["Symbol", "Client", "Qty", "Price", "Value"]
            rows = []
            for d in sells[:8]:
                client = d["client"][:20]
                if len(d["client"]) > 20:
                    client += "..."
                rows.append([
                    d["symbol"][:10],
                    client,
                    _vol(d["qty"]),
                    f"₹{d['price']:,.1f}",
                    f"₹{d['value_cr']:.1f}Cr"
                ])
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=["left", "left", "right", "right", "right"]))
            lines.append("</pre>")
            lines.append("")
        
        # Net accumulation by symbol
        top_acc = sorted(symbol_net.items(), key=lambda x: x[1], reverse=True)[:5]
        top_dist = sorted(symbol_net.items(), key=lambda x: x[1])[:5]
        
        if top_acc and top_acc[0][1] > 0:
            lines.append("<b>📊 Most Accumulated (Net Buying):</b>")
            for sym, net_val in top_acc:
                if net_val > 0:
                    lines.append(f"  🟢 {sym}: +₹{net_val:.1f}Cr")
            lines.append("")
        
        if top_dist and top_dist[0][1] < 0:
            lines.append("<b>📊 Most Distributed (Net Selling):</b>")
            for sym, net_val in top_dist:
                if net_val < 0:
                    lines.append(f"  🔴 {sym}: ₹{net_val:.1f}Cr")
            lines.append("")
    
    # === BLOCK DEALS (on-exchange) ===
    if block_deals:
        lines.append(f"<b>🏛️ Block Deals ({len(block_deals)})</b>")
        lines.append("<i>Large institutional trades on exchange (>₹10Cr)</i>")
        lines.append("")
        
        # Separate buys and sells
        b_buys = [d for d in block_deals if d["trade_type"] == "BUY"]
        b_sells = [d for d in block_deals if d["trade_type"] == "SELL"]
        
        # Top block buys
        if b_buys:
            lines.append(f"<b>🟢 Top Block Buys ({len(b_buys)} deals):</b>")
            headers = ["Symbol", "Client", "Qty", "Price", "Value"]
            rows = []
            for d in b_buys[:8]:
                client = d["client"][:20]
                if len(d["client"]) > 20:
                    client += "..."
                rows.append([
                    d["symbol"][:10],
                    client,
                    _vol(d["qty"]),
                    f"₹{d['price']:,.1f}",
                    f"₹{d['value_cr']:.1f}Cr"
                ])
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=["left", "left", "right", "right", "right"]))
            lines.append("</pre>")
            lines.append("")
        
        # Top block sells
        if b_sells:
            lines.append(f"<b>🔴 Top Block Sells ({len(b_sells)} deals):</b>")
            headers = ["Symbol", "Client", "Qty", "Price", "Value"]
            rows = []
            for d in b_sells[:8]:
                client = d["client"][:20]
                if len(d["client"]) > 20:
                    client += "..."
                rows.append([
                    d["symbol"][:10],
                    client,
                    _vol(d["qty"]),
                    f"₹{d['price']:,.1f}",
                    f"₹{d['value_cr']:.1f}Cr"
                ])
            lines.append("<pre>")
            lines.append(_make_table(headers, rows, align=["left", "left", "right", "right", "right"]))
            lines.append("</pre>")
            lines.append("")
    
    # === ANALYSIS & PREDICTION ===
    lines.append("<b>🔮 Analysis & Signals:</b>")
    
    # Combine all deals for analysis
    all_deals = (bulk_deals or []) + (block_deals or [])
    
    if all_deals:
        # Stock-level buy/sell ratio
        stock_pressure = {}
        for d in all_deals:
            sym = d["symbol"]
            if sym not in stock_pressure:
                stock_pressure[sym] = {"buy": 0, "sell": 0}
            if d["trade_type"] == "BUY":
                stock_pressure[sym]["buy"] += d["value_cr"]
            else:
                stock_pressure[sym]["sell"] += d["value_cr"]
        
        # Find stocks with strong buying pressure
        strong_buys = []
        strong_sells = []
        for sym, pressure in stock_pressure.items():
            buy, sell = pressure["buy"], pressure["sell"]
            total = buy + sell
            if total > 5:  # Minimum ₹5Cr total activity
                buy_ratio = buy / total if total else 0
                if buy_ratio >= 0.75:  # 75%+ buying
                    strong_buys.append((sym, buy, sell, buy_ratio))
                elif buy_ratio <= 0.25:  # 75%+ selling
                    strong_sells.append((sym, buy, sell, buy_ratio))
        
        if strong_buys:
            lines.append("<b>🐂 Strong Buying Pressure (Bullish):</b>")
            strong_buys.sort(key=lambda x: x[1], reverse=True)
            for sym, buy, sell, ratio in strong_buys[:5]:
                lines.append(f"  💚 {sym}: Buy ₹{buy:.1f}Cr vs Sell ₹{sell:.1f}Cr ({ratio*100:.0f}% buy)")
        
        if strong_sells:
            lines.append("<b>🐻 Strong Selling Pressure (Bearish):</b>")
            strong_sells.sort(key=lambda x: x[2], reverse=True)
            for sym, buy, sell, ratio in strong_sells[:5]:
                lines.append(f"  ❤️ {sym}: Sell ₹{sell:.1f}Cr vs Buy ₹{buy:.1f}Cr ({(1-ratio)*100:.0f}% sell)")
        
        if not strong_buys and not strong_sells:
            lines.append("  ⚖️ Balanced activity - no clear directional bias")
        
        # Total money flow
        total_buy = sum(d["value_cr"] for d in all_deals if d["trade_type"] == "BUY")
        total_sell = sum(d["value_cr"] for d in all_deals if d["trade_type"] == "SELL")
        
        lines.append("")
        lines.append(f"<b>💰 Overall Flow:</b>")
        lines.append(f"  Buy: ₹{total_buy:.1f}Cr | Sell: ₹{total_sell:.1f}Cr")
        if total_buy > total_sell * 1.2:
            lines.append(f"  ✅ <b>Net Bullish</b> - institutional buying dominates")
        elif total_sell > total_buy * 1.2:
            lines.append(f"  ⚠️ <b>Net Bearish</b> - institutional selling dominates")
        else:
            lines.append(f"  ➡️ <b>Neutral</b> - balanced activity")
    else:
        lines.append("  No deals to analyze")
    
    lines.append("")
    lines.append("<i>💡 Bulk deals show client-level accumulation/distribution patterns</i>")
    lines.append("<i>💡 Block deals indicate institutional positioning</i>")
    
    return "\n".join(lines)


def format_delta_alert(delta: Dict) -> Optional[str]:
    """Quick alert when significant changes detected."""
    if not delta:
        return None

    alerts = []

    # FII/DII reversals
    fd = delta.get("fii_dii")
    if fd:
        if fd.get("fii_reversal"):
            alerts.append(fd["fii_reversal"])
        if fd.get("dii_reversal"):
            alerts.append(fd["dii_reversal"])

    # Big index moves (deduplicated — indices are unique by name)
    idx = delta.get("indices", {})
    if idx:
        # Group by significance: show biggest movers first
        big_moves = []
        for name, chg in idx.get("changes", {}).items():
            pct_chg = chg.get("pct_change", 0)
            if abs(pct_chg) >= 1.0:
                big_moves.append((name, chg))
        big_moves.sort(key=lambda x: abs(x[1].get("pct_change", 0)), reverse=True)
        for name, chg in big_moves[:10]:
            alerts.append(f"{chg['signal']} {name}: {_pct(chg['pct_change'])} since last check")

    if not alerts:
        return None

    lines = ["<b>⚡ ALERT: Significant Changes!</b>", ""]
    lines.extend(alerts)
    return "\n".join(lines)
