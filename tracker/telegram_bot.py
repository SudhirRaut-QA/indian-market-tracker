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


def _bar(val: float, width: int = 5) -> str:
    """Simple visual bar."""
    filled = int(min(abs(val), width))
    if val >= 0:
        return "▓" * filled + "░" * (width - filled)
    return "░" * (width - filled) + "▓" * filled


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

def format_fii_dii_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """FII/DII + Key Indices + Market Status."""
    now = datetime.now().strftime("%d %b %Y %-I:%M %p") if os.name != "nt" else datetime.now().strftime("%d %b %Y %I:%M %p")
    lines = [f"<b>📊 Market Pulse — {now}</b>", ""]

    # Market status
    status = snapshot.get("market_status", {})
    for mkt, info in status.items():
        st = info.get("status", "")
        if "Capital" in mkt or "Equit" in mkt:
            emoji = "🟢" if "Open" in st or "open" in st else "🔴" if "Close" in st else "🟡"
            lines.append(f"{emoji} {mkt}: <b>{st}</b>")

    lines.append("")

    # FII/DII
    fd = snapshot.get("fii_dii")
    if fd:
        sig = fd.get("signal", "")
        sig_emoji = {"Strong Bullish": "🐂🐂", "FII Bullish": "🐂", "DII Defensive": "🛡️", "Bearish": "🐻"}.get(sig, "❓")

        fii_date = fd.get('date', '')
        lines.append(f"<b>💰 FII/DII Activity</b> ({fii_date} — T+1 data)")
        lines.append(f"Signal: {sig_emoji} <b>{sig}</b>")
        lines.append(f"💡 {fd.get('interpretation', '')}")
        lines.append("")
        lines.append(f"🌍 FII: Buy {_cr(fd['fii']['buy'])} | Sell {_cr(fd['fii']['sell'])}")
        lines.append(f"   Net: <b>{_cr(fd['fii']['net'])}</b>")
        lines.append(f"🏠 DII: Buy {_cr(fd['dii']['buy'])} | Sell {_cr(fd['dii']['sell'])}")
        lines.append(f"   Net: <b>{_cr(fd['dii']['net'])}</b>")
        lines.append(f"📊 Total Net: <b>{_cr(fd.get('total_net', 0))}</b>")

        # Delta for FII/DII
        if delta and delta.get("fii_dii"):
            dd = delta["fii_dii"]
            lines.append("")
            lines.append("<b>🔄 Changes vs Last Check:</b>")
            if dd.get("fii_reversal"):
                lines.append(f"  ⚠️ {dd['fii_reversal']}")
            if dd.get("dii_reversal"):
                lines.append(f"  ⚠️ {dd['dii_reversal']}")
            lines.append(f"  FII Net: {_cr(dd['fii_net_prev'])} → {_cr(dd['fii_net_curr'])}")
            lines.append(f"  DII Net: {_cr(dd['dii_net_prev'])} → {_cr(dd['dii_net_curr'])}")

    lines.append("")

    # Key Indices
    indices = snapshot.get("indices", {})
    if indices:
        lines.append("<b>📈 Key Indices</b>")
        top5 = ["NIFTY 50", "NIFTY BANK", "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100"]
        for name in top5:
            if name in indices:
                idx = indices[name]
                e = _emoji_pct(idx.get("pct", 0))
                lines.append(f"{e} {name}: <b>{idx['last']:,.1f}</b> ({_pct(idx['pct'])})")
                adv, dec = idx.get("advances", 0), idx.get("declines", 0)
                if adv or dec:
                    lines.append(f"   🟢{adv} 🔴{dec}")

        # Trending indices
        trending = ["NIFTY PSU BANK", "NIFTY INDIA DEFENCE", "NIFTY COMMODITIES",
                     "NIFTY200 MOMENTUM 30", "NIFTY HIGH BETA 50", "NIFTY100 LOW VOLATILITY 30"]
        trend_list = []
        for name in trending:
            if name in indices:
                idx = indices[name]
                e = _emoji_pct(idx.get("pct", 0))
                short = name.replace("NIFTY ", "")
                trend_list.append(f"{e} {short}: {_pct(idx['pct'])}")
        if trend_list:
            lines.append("")
            lines.append("<b>🔥 Trending Sectors</b>")
            lines.extend(trend_list)

        # Index delta
        if delta and delta.get("indices"):
            id_d = delta["indices"]
            best = id_d.get("best", {})
            worst = id_d.get("worst", {})
            if best and worst:
                lines.append("")
                lines.append("<b>📊 Since Last Check:</b>")
                lines.append(f"  Best:  {best['name']} {best['signal']} ({_pct(best['pct_change'])})")
                lines.append(f"  Worst: {worst['name']} {worst['signal']} ({_pct(worst['pct_change'])})")

    return "\n".join(lines)


def format_sector_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """Sector heatmap + top movers per sector."""
    lines = ["<b>🏭 Sector Analysis</b>", ""]

    sectors = snapshot.get("sectors", {})
    if not sectors:
        lines.append("No sector data available")
        return "\n".join(lines)

    # Sector heatmap
    lines.append("<b>📊 Sector Heatmap (by index %)</b>")
    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1].get("index_pct", 0), reverse=True)
    for name, data in sorted_sectors:
        pct = data.get("index_pct", 0)
        e = _emoji_pct(pct)
        short = name.replace("NIFTY ", "")
        lines.append(f"{e} {short}: <b>{_pct(pct)}</b> ({data.get('count', 0)} stocks)")

    # Top movers across all sectors
    lines.append("")
    lines.append("<b>🏆 Top Gainers (all sectors)</b>")
    all_gainers = []
    all_losers = []
    for name, data in sectors.items():
        for s in data.get("gainers", [])[:3]:
            all_gainers.append({**s, "sector": name.replace("NIFTY ", "")})
        for s in data.get("losers", [])[:3]:
            all_losers.append({**s, "sector": name.replace("NIFTY ", "")})

    all_gainers.sort(key=lambda x: x["pct"], reverse=True)
    for s in all_gainers[:8]:
        lines.append(f"  🟢 {s['symbol']}: {_pct(s['pct'])} (₹{s['last']:,.1f}) [{s['sector']}]")

    lines.append("")
    lines.append("<b>📉 Top Losers (all sectors)</b>")
    all_losers.sort(key=lambda x: x["pct"])
    for s in all_losers[:8]:
        lines.append(f"  🔴 {s['symbol']}: {_pct(s['pct'])} (₹{s['last']:,.1f}) [{s['sector']}]")

    # High volume stocks
    lines.append("")
    lines.append("<b>📊 Highest Value Traded</b>")
    all_traded = []
    for name, data in sectors.items():
        for s in data.get("most_traded", [])[:3]:
            all_traded.append({**s, "sector": name.replace("NIFTY ", "")})
    all_traded.sort(key=lambda x: x["value_cr"], reverse=True)
    for s in all_traded[:5]:
        lines.append(f"  💰 {s['symbol']}: ₹{s['value_cr']:,.0f} Cr ({_pct(s['pct'])})")

    # Delta: stock movers between snapshots
    if delta and delta.get("sectors"):
        movers_all = []
        for name, sd in delta["sectors"].items():
            for m in sd.get("movers", [])[:3]:
                movers_all.append({**m, "sector": name.replace("NIFTY ", "")})
        if movers_all:
            movers_all.sort(key=lambda x: abs(x["price_chg_pct"]), reverse=True)
            lines.append("")
            lines.append("<b>🔄 Big Movers Since Last Check</b>")
            for m in movers_all[:8]:
                lines.append(f"  {m['signal']} {m['symbol']}: {_pct(m['price_chg_pct'])} (₹{m['price_prev']:.1f}→₹{m['price_curr']:.1f})")

    return "\n".join(lines)


def format_options_msg(snapshot: Dict) -> str:
    """Option chain PCR analysis."""
    lines = ["<b>📊 Options Analysis</b>", ""]

    oc = snapshot.get("option_chain", {})
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


def format_commodities_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """Commodities + Forex."""
    lines = ["<b>🏆 Commodities & Forex</b>", ""]

    # Commodity ETFs
    comms = snapshot.get("commodities", {})
    if comms:
        lines.append("<b>🥇 Commodity ETFs</b>")
        names = {
            "KOTAKGOLD": "Gold (Kotak)",
            "ICICIGOLD": "Gold (ICICI)",
            "SILVERBEES": "Silver",
            "LIQUIDBEES": "Liquid",
        }
        for sym, data in comms.items():
            e = _emoji_pct(data.get("pct", 0))
            name = names.get(sym, sym)
            lines.append(f"{e} {name} ({sym}): <b>₹{data['last']:,.2f}</b> ({_pct(data['pct'])})")
            lines.append(f"   52W: ₹{data.get('week52_low', 0):,.2f} — ₹{data.get('week52_high', 0):,.2f}")
        lines.append("")

    # Commodity indices
    indices = snapshot.get("indices", {})
    commodity_indices = ["NIFTY COMMODITIES", "NIFTY OIL & GAS", "NIFTY ENERGY"]
    for name in commodity_indices:
        if name in indices:
            idx = indices[name]
            e = _emoji_pct(idx.get("pct", 0))
            short = name.replace("NIFTY ", "")
            lines.append(f"{e} {short}: <b>{idx['last']:,.1f}</b> ({_pct(idx['pct'])})")

    lines.append("")

    # Forex
    forex = snapshot.get("forex")
    if forex:
        lines.append("<b>💱 Currency Rates</b>")
        lines.append(f"🇺🇸→🇮🇳 USD/INR: <b>₹{forex['usdinr']:.4f}</b>")
        if forex.get("usdeur"):
            lines.append(f"🇺🇸→🇪🇺 USD/EUR: €{forex['usdeur']:.4f}")
        if forex.get("usdgbp"):
            lines.append(f"🇺🇸→🇬🇧 USD/GBP: £{forex['usdgbp']:.4f}")

        # Forex delta
        if delta and delta.get("forex"):
            fd = delta["forex"]
            lines.append(f"   {fd['direction']} ({fd['change']:+.4f})")

    return "\n".join(lines)


def format_corporate_msg(snapshot: Dict) -> str:
    """Corporate actions + insider trading."""
    lines = ["<b>📋 Corporate Actions & Insider Trading</b>", ""]

    # Corporate actions
    actions = snapshot.get("corporate_actions")
    if actions:
        lines.append(f"<b>📌 Corporate Actions ({len(actions)} items)</b>")

        dividends = [a for a in actions if "dividend" in a.get("subject", "").lower()]
        splits = [a for a in actions if "split" in a.get("subject", "").lower()]
        rights = [a for a in actions if "right" in a.get("subject", "").lower()]
        bonus = [a for a in actions if "bonus" in a.get("subject", "").lower()]
        others = [a for a in actions if a not in dividends + splits + rights + bonus]

        if dividends:
            lines.append("")
            lines.append("💰 <b>Dividends:</b>")
            for a in dividends[:5]:
                lines.append(f"  {a['symbol']}: {a['subject'][:60]}")
                lines.append(f"  📅 Ex-Date: {a['ex_date']}")

        if splits:
            lines.append("")
            lines.append("✂️ <b>Stock Splits:</b>")
            for a in splits[:5]:
                lines.append(f"  {a['symbol']}: {a['subject'][:60]}")
                lines.append(f"  📅 Ex-Date: {a['ex_date']}")

        if rights:
            lines.append("")
            lines.append("📜 <b>Rights Issues:</b>")
            for a in rights[:5]:
                lines.append(f"  {a['symbol']}: {a['subject'][:60]}")

        if bonus:
            lines.append("")
            lines.append("🎁 <b>Bonus Issues:</b>")
            for a in bonus[:5]:
                lines.append(f"  {a['symbol']}: {a['subject'][:60]}")

        if others:
            lines.append("")
            lines.append("📎 <b>Other Actions:</b>")
            for a in others[:3]:
                lines.append(f"  {a['symbol']}: {a['subject'][:60]}")
    else:
        lines.append("No corporate actions this week")

    lines.append("")

    # Insider trading
    insiders = snapshot.get("insider_trading")
    if insiders:
        lines.append(f"<b>🔍 Insider Trading ({len(insiders)} trades)</b>")
        lines.append("<i>Who is buying/selling their own company stock?</i>")
        lines.append("")

        big_buys = [t for t in insiders if t["buy_value"] > t["sell_value"]][:5]
        big_sells = [t for t in insiders if t["sell_value"] > t["buy_value"]][:5]

        if big_buys:
            lines.append("🟢 <b>Top Insider Buys (Bullish Signal):</b>")
            for t in big_buys:
                val = t["buy_value"]
                unit = "Cr" if val >= 1e7 else "L"
                amt = val / 1e7 if val >= 1e7 else val / 1e5
                lines.append(f"  {t['symbol']}: ₹{amt:,.1f} {unit} by {t['acquirer'][:30]}")
            lines.append("")

        if big_sells:
            lines.append("🔴 <b>Top Insider Sells (Caution Signal):</b>")
            for t in big_sells:
                val = t["sell_value"]
                unit = "Cr" if val >= 1e7 else "L"
                amt = val / 1e7 if val >= 1e7 else val / 1e5
                lines.append(f"  {t['symbol']}: ₹{amt:,.1f} {unit} by {t['acquirer'][:30]}")

        lines.append("")
        lines.append("💡 <i>Insiders buying = they think price will go UP</i>")
        lines.append("💡 <i>Insiders selling = could be profit-booking or concern</i>")
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
            lines.append(f"  {s['symbol']}: ₹{s['iep']:,.1f} ({_pct(s['pct'])})")

    if losers:
        lines.append("")
        lines.append("<b>🔴 Pre-Open Losers:</b>")
        for s in losers[:5]:
            lines.append(f"  {s['symbol']}: ₹{s['iep']:,.1f} ({_pct(s['pct'])})")

    lines.append("")
    lines.append("💡 <i>Pre-open shows where stocks will start trading today</i>")
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

    # Big index moves
    idx = delta.get("indices", {})
    if idx:
        for name, chg in idx.get("changes", {}).items():
            if abs(chg.get("pct_change", 0)) >= 1.0:
                alerts.append(f"{chg['signal']} {name}: {_pct(chg['pct_change'])} since last check")

    if not alerts:
        return None

    lines = ["<b>⚡ ALERT: Significant Changes Detected!</b>", ""]
    lines.extend(alerts)
    return "\n".join(lines)
