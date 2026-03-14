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
from datetime import datetime
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
    
    Examples:
      'Interim Dividend - Rs 10 Per Share' -> 10.0
      'Final Dividend - Re 1.50 Per Share' -> 1.50
      'Dividend Rs. 5.25 per share' -> 5.25
    """
    import re
    if not subject:
        return 0.0
    
    # Match patterns like "Rs 10", "Re 1.50", "Rs. 5.25"
    patterns = [
        r'Rs\.?\s*(\d+(?:\.\d+)?)',  # Rs 10, Rs. 10.5
        r'Re\.?\s*(\d+(?:\.\d+)?)',  # Re 1, Re. 1.5
    ]
    
    for pattern in patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue
    return 0.0


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
    return f'<a href="{NSE_QUOTE_URL}{quote(symbol)}">{text or symbol}</a>'


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
    vix_pct = vix_data.get("pct", 0)
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
    fear = ""
    if vix_pct > 5:
        fear = " | 😨 Fear spike"
    elif vix_pct < -3:
        fear = " | 😌 Calm"
    return f"{mood} ({adv}🟢 vs {dec}🔴){fear}"


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
        if chg >= 2:
            sig = "🚀"
        elif chg >= 0.5:
            sig = "📈"
        elif chg > -0.5:
            sig = "➡️"
        elif chg > -2:
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
    # Summary
    gains = sum(1 for w in watchlist if current.get(w["symbol"], {}).get("last", 0) > w["entry_ltp"])
    losses = len(watchlist) - gains
    lines.append(f"Score: {gains}🟢 winning · {losses}🔴 losing")
    return "\n".join(lines)


def format_expert_opinion(snapshot: Dict, delta: Optional[Dict] = None) -> Optional[str]:
    """Simple market analysis any beginner can understand."""
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
    # 1. Market direction
    if n_pct >= 1:
        lines.append("📈 <b>Market is strongly UP today.</b> Buyers in control.")
    elif n_pct >= 0.3:
        lines.append("📈 <b>Market is mildly green.</b> Cautious optimism.")
    elif n_pct > -0.3:
        lines.append("➡️ <b>Market is flat/sideways.</b> No clear direction.")
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
    # 3. VIX (fear gauge)
    if v_last:
        if v_last > 20:
            lines.append(f"😨 <b>VIX at {v_last:.1f}</b> — High fear. Market is volatile. Don't panic-sell.")
        elif v_last > 15:
            lines.append(f"😐 <b>VIX at {v_last:.1f}</b> — Moderate fear. Normal caution.")
        else:
            lines.append(f"😌 <b>VIX at {v_last:.1f}</b> — Low fear. Market is calm.")
        lines.append("")
    # 4. Sector rotation
    if sectors:
        sorted_sec = sorted(sectors.items(), key=lambda x: x[1].get("index_pct", 0), reverse=True)
        best_sec = sorted_sec[0] if sorted_sec else None
        worst_sec = sorted_sec[-1] if sorted_sec else None
        if best_sec and worst_sec:
            b_name = best_sec[0].replace("NIFTY ", "")
            b_val = best_sec[1].get("index_pct", 0)
            w_name = worst_sec[0].replace("NIFTY ", "")
            w_val = worst_sec[1].get("index_pct", 0)
            lines.append(f"🔄 <b>Money rotating:</b> {b_name} ({_pct(b_val)}) best, "
                         f"{w_name} ({_pct(w_val)}) worst.")
            lines.append("")
    # 5. Simple advice
    lines.append("<b>📝 What should you do?</b>")
    if n_pct < -2:
        lines.append("• <i>Big fall day. If you own good stocks, HOLD. Don't panic.</i>")
        lines.append("• <i>If you want to buy, wait for market to stabilize first.</i>")
    elif n_pct < -0.5:
        lines.append("• <i>Red day but not alarming. Watch for support levels.</i>")
        lines.append("• <i>Good companies on dip = potential buying opportunity.</i>")
    elif n_pct > 1:
        lines.append("• <i>Strong green day! Don't chase — book partial profits.</i>")
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
        lines.append("<i>💎 Near 52-Week Low (Value Zone):</i>")
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
                name[:12],
                f"₹{data['last']:,.0f}",
                _pct(data['pct']),
                f"₹{data.get('week52_low', 0):,.0f}",
                f"₹{data.get('week52_high', 0):,.0f}",
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
            rows[0][2] = f"{fd['direction']} {fd['change']:+.4f}"
        
        table = _make_table(headers, rows, align=['left', 'right', 'left'])
        lines.append("<pre>")
        lines.append(table)
        lines.append("</pre>")
    elif forex and not show_extras:
        lines.append(f"💱 USD/INR: <b>₹{forex['usdinr']:.4f}</b> <i>(detail at 9 PM)</i>")

    return "\n".join(lines)


def format_corporate_msg(snapshot: Dict) -> str:
    """Corporate actions + insider trading. Only shows UPCOMING events (future ex-dates)."""
    lines = ["<b>📋 Corporate Actions & Insider Trading</b>", ""]

    today = datetime.now().date()

    def _parse_date(date_str):
        """Parse NSE date formats: '13-Mar-2026' or '06-03-2026'."""
        if not date_str or date_str == 'N/A':
            return None
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        return None

    def _is_upcoming(action):
        """Return True only if ex_date is today or in the future."""
        ex = _parse_date(action.get('ex_date', ''))
        return ex is not None and ex >= today

    # Corporate actions — FILTER to upcoming only
    actions = snapshot.get("corporate_actions")
    if actions:
        upcoming = [a for a in actions if _is_upcoming(a)]
        if upcoming:
            lines.append(f"<b>📌 Upcoming Corporate Actions ({len(upcoming)} events)</b>")
            lines.append("")

            dividends = [a for a in upcoming if "dividend" in a.get("subject", "").lower()]
            splits = [a for a in upcoming if "split" in a.get("subject", "").lower()]
            bonus = [a for a in upcoming if "bonus" in a.get("subject", "").lower()]
            others = [a for a in upcoming if a not in dividends and a not in splits and a not in bonus]
            
            if dividends:
                lines.append("<b>💰 Upcoming Dividends:</b>")
                for a in dividends[:8]:
                    sym = a.get('symbol', '')
                    subject = a.get('subject', '')
                    ex_date = a.get('ex_date', 'N/A')
                    ltp = a.get('ltp', 0)
                    pe = a.get('pe', 0)
                    div_amt = _extract_dividend_amount(subject)
                    try:
                        ltp_val = float(ltp) if ltp else 0
                        pe_val = float(pe) if pe else 0
                        yield_pct = (div_amt / ltp_val * 100) if (ltp_val and div_amt) else 0
                    except (ValueError, TypeError):
                        ltp_val, pe_val, yield_pct = 0, 0, 0
                    ltp_str = f"₹{ltp_val:,.0f}" if ltp_val else "—"
                    pe_str = f"{pe_val:.1f}" if pe_val else "—"
                    div_str = f"₹{div_amt:.2f}" if div_amt else "—"
                    yield_str = f"{yield_pct:.2f}%" if yield_pct else "—"
                    link = _nse_link(sym)
                    lines.append(f"  {link} | LTP: {ltp_str} | PE: {pe_str}")
                    lines.append(f"  Dividend: {div_str} | Yield: {yield_str}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")
            
            if splits:
                lines.append("<b>✂️ Upcoming Stock Splits:</b>")
                for a in splits[:5]:
                    sym = a.get('symbol', '')
                    subject = a.get('subject', '')[:60]
                    ex_date = a.get('ex_date', 'N/A')
                    ltp = a.get('ltp', 0)
                    try:
                        ltp_val = float(ltp) if ltp else 0
                    except (ValueError, TypeError):
                        ltp_val = 0
                    ltp_str = f"₹{ltp_val:,.0f}" if ltp_val else "—"
                    lines.append(f"  {_nse_link(sym)} | LTP: {ltp_str}")
                    lines.append(f"  {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")
            
            if bonus:
                lines.append("<b>🎁 Upcoming Bonus Issues:</b>")
                for a in bonus[:5]:
                    sym = a.get('symbol', '')
                    subject = a.get('subject', '')[:60]
                    ex_date = a.get('ex_date', 'N/A')
                    ltp = a.get('ltp', 0)
                    try:
                        ltp_val = float(ltp) if ltp else 0
                    except (ValueError, TypeError):
                        ltp_val = 0
                    ltp_str = f"₹{ltp_val:,.0f}" if ltp_val else "—"
                    lines.append(f"  {_nse_link(sym)} | LTP: {ltp_str}")
                    lines.append(f"  {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")
            
            if others:
                lines.append("<b>📋 Other Actions:</b>")
                for a in others[:3]:
                    sym = a.get('symbol', '')
                    subject = a.get('subject', '')[:60]
                    ex_date = a.get('ex_date', 'N/A')
                    lines.append(f"  {_nse_link(sym)} — {subject}")
                    lines.append(f"  📅 Ex-Date: <b>{ex_date}</b>")
                    lines.append("")

            if not (dividends or splits or bonus or others):
                lines.append("<i>No upcoming corporate actions</i>")
        else:
            lines.append("<i>No upcoming corporate actions in the next 7 days</i>")
    else:
        lines.append("<i>No corporate actions data available</i>")

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


def format_preopen_msg(snapshot: Dict) -> str:
    """Pre-open market analysis."""
    po = snapshot.get("preopen")
    if not po:
        return "<b>🌅 Pre-Open Market</b>\n\nPre-open data not available"

    lines = ["<b>🌅 Pre-Open Market Analysis</b>", ""]
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
        lines.append("<b>💎 Near 52-Week Low (Value Zone):</b>")
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
