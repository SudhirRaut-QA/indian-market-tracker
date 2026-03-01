"""
Telegram Bot v3.0 - Mobile-Optimized HTML Messages
=====================================================

Designed for Mi Note 9 (5.93" screen, ~38-40 chars wide).
Uses Telegram HTML tags: <b>, <i>, <u>, <code>, <pre>, <a>.
Compact formatting, emoji visual hierarchy.

Message types:
 1. Market Pulse   — FII/DII + Key Indices + Delta
 2. Sector Heatmap — Heatmap + Top Movers
 3. Options PCR    — NIFTY/BANKNIFTY analysis
 4. Commodities    — Gold/Silver + Forex
 5. Corporate      — Actions with LTP/PE/Yield
 6. Pre-Open       — Pre-market analysis
 7. Block/Bulk     — Institutional deals
 8. 52W Alerts     — Breakout/Value candidates
 9. Delta Alert    — Significant changes
10. Market Context — AI-like explanations
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

import requests

from . import config

logger = logging.getLogger(__name__)

MAX_MSG_LEN = 4000


# ═══ Helpers (compact for mobile) ═══════════════════════════════════════════

def _cr(val: float) -> str:
    """Crore value with sign, compact."""
    if abs(val) >= 1000:
        return f"{'+'if val>0 else ''}₹{val/1000:,.1f}K Cr"
    return f"{'+'if val>0 else ''}₹{abs(val):,.0f} Cr"


def _pct(val: float) -> str:
    return f"{'+'if val>=0 else ''}{val:.2f}%"


def _e(val: float) -> str:
    """Emoji for percentage."""
    if val >= 2: return "🟢🟢"
    if val >= 0.5: return "🟢"
    if val > -0.5: return "⚪"
    if val > -2: return "🔴"
    return "🔴🔴"


def _compact_num(val: float) -> str:
    """Compact large numbers: 1.5L, 2.3Cr."""
    if abs(val) >= 1e7:
        return f"₹{val/1e7:.1f}Cr"
    if abs(val) >= 1e5:
        return f"₹{val/1e5:.1f}L"
    if abs(val) >= 1e3:
        return f"₹{val/1e3:.1f}K"
    return f"₹{val:,.0f}"


def _ts() -> str:
    """Compact timestamp for mobile."""
    return datetime.now().strftime("%d %b %I:%M%p")


def _sentiment(snapshot: Dict) -> str:
    """Lightweight sentiment score for a one-line summary."""
    score = 0
    fd = snapshot.get("fii_dii")
    if fd:
        total_net = fd.get("total_net", 0)
        if total_net > 0:
            score += 1
        elif total_net < 0:
            score -= 1

    indices = snapshot.get("indices", {})
    nifty = indices.get("NIFTY 50")
    if nifty:
        pct = nifty.get("pct", 0)
        if pct > 0.2:
            score += 1
        elif pct < -0.2:
            score -= 1

        try:
            adv = int(nifty.get("advances", 0) or 0)
            dec = int(nifty.get("declines", 0) or 0)
        except (ValueError, TypeError):
            adv, dec = 0, 0
        if adv and dec:
            score += 1 if adv > dec else -1

    if score >= 2:
        return "Bullish"
    if score <= -2:
        return "Bearish"
    return "Neutral"


class TelegramBot:
    """Sends formatted HTML messages to Telegram."""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()
        self.session.trust_env = True

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.token or not self.chat_id:
            logger.warning("Telegram credentials not set")
            print(f"\n{'='*50}\n{text}\n{'='*50}")
            return False
        try:
            chunks = self._split(text)
            for chunk in chunks:
                resp = self.session.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    },
                    timeout=60,
                )
                if resp.status_code != 200:
                    err = resp.json().get("description", resp.text[:200])
                    logger.error(f"Telegram error: {err}")
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


# ═══════════════════════════════════════════════════════════════════════════
#  MESSAGE FORMATTERS (Mobile-Optimized HTML)
# ═══════════════════════════════════════════════════════════════════════════

def format_fii_dii_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """FII/DII + Key Indices — compact for mobile."""
    L = [f"<b>📊 Market Pulse</b> — {_ts()}", ""]

    # Market status (one-liner)
    status = snapshot.get("market_status", {})
    for mkt, info in status.items():
        st = info.get("status", "")
        if "Capital" in mkt or "Equit" in mkt:
            em = "🟢" if "open" in st.lower() else "🔴"
            L.append(f"{em} Market: <b>{st}</b>")
            break

    # FII/DII
    fd = snapshot.get("fii_dii")
    if fd:
        sig = fd.get("signal", "")
        sig_map = {
            "Strong Bullish": "🐂🐂",
            "FII Bullish": "🐂",
            "DII Defensive": "🛡️",
            "Bearish": "🐻",
        }
        L.append("")
        L.append(f"<b>💰 FII/DII</b> {sig_map.get(sig, '❓')} {sig}")
        L.append(f"<i>{fd.get('interpretation', '')}</i>")
        L.append("")

        fii = fd["fii"]
        dii = fd["dii"]
        # Compact table using monospace
        L.append("<code>")
        L.append(f"     {'Buy':>10} {'Sell':>10} {'Net':>10}")
        L.append(f"FII  {fii['buy']:>10,.0f} {fii['sell']:>10,.0f} {fii['net']:>10,.0f}")
        L.append(f"DII  {dii['buy']:>10,.0f} {dii['sell']:>10,.0f} {dii['net']:>10,.0f}")
        L.append(f"{'─'*38}")
        L.append(f"NET  {'':>10} {'':>10} {fd.get('total_net',0):>10,.0f}")
        L.append("</code>")

        # Delta
        if delta and delta.get("fii_dii"):
            dd = delta["fii_dii"]
            if dd.get("fii_reversal"):
                L.append(f"\n⚠️ {dd['fii_reversal']}")
            if dd.get("dii_reversal"):
                L.append(f"⚠️ {dd['dii_reversal']}")

    L.append("")
    L.append(f"<b>Sentiment:</b> {_sentiment(snapshot)}")

    # Key Indices
    indices = snapshot.get("indices", {})
    if indices:
        L.append("")
        L.append("<b>📈 Indices</b>")
        # Primary indices
        for name in ["NIFTY 50", "NIFTY BANK", "INDIA VIX"]:
            if name in indices:
                d = indices[name]
                pct = d.get("pct", 0)
                short = name.replace("NIFTY ", "")
                adv = d.get("advances", 0) or 0
                dec = d.get("declines", 0) or 0
                breadth = f" 🟢{adv}🔴{dec}" if adv or dec else ""
                L.append(
                    f"{_e(pct)} <b>{short}</b> "
                    f"{d['last']:,.1f} ({_pct(pct)}){breadth}"
                )

        L.append("")
        # Secondary indices (compact, 2 per line)
        secondary = [
            "NIFTY IT", "NIFTY PHARMA", "NIFTY METAL",
            "NIFTY AUTO", "NIFTY ENERGY", "NIFTY FMCG",
            "NIFTY PSU BANK", "NIFTY INDIA DEFENCE",
            "NIFTY MIDCAP 50", "NIFTY SMALLCAP 50",
        ]
        for name in secondary:
            if name in indices:
                d = indices[name]
                pct = d.get("pct", 0)
                short = name.replace("NIFTY ", "")
                L.append(f"{_e(pct)} {short}: {_pct(pct)}")

        # Best/worst delta
        if delta and delta.get("indices"):
            id_d = delta["indices"]
            b = id_d.get("best", {})
            w = id_d.get("worst", {})
            if b and w:
                L.append("")
                L.append("<b>🔄 Since Last:</b>")
                L.append(f"  ⬆️ {b['name']}: {_pct(b['pct_change'])}")
                L.append(f"  ⬇️ {w['name']}: {_pct(w['pct_change'])}")

    return "\n".join(L)


def format_sector_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """Sector heatmap + movers — mobile compact."""
    L = ["<b>🏭 Sectors</b>", ""]

    sectors = snapshot.get("sectors", {})
    if not sectors:
        return "<b>🏭 Sectors</b>\nNo data"

    # Heatmap sorted by performance
    sorted_s = sorted(
        sectors.items(),
        key=lambda x: x[1].get("index_pct", 0),
        reverse=True,
    )
    L.append("<b>Heatmap (% change)</b>")
    for name, data in sorted_s:
        pct = data.get("index_pct", 0)
        short = name.replace("NIFTY ", "")[:14]
        L.append(f"{_e(pct)} {short}: <b>{_pct(pct)}</b>")

    # Top gainers across sectors
    all_g = []
    all_l = []
    for name, data in sectors.items():
        sec = name.replace("NIFTY ", "")[:8]
        for s in data.get("gainers", [])[:2]:
            all_g.append({**s, "sec": sec})
        for s in data.get("losers", [])[:2]:
            all_l.append({**s, "sec": sec})

    if all_g:
        all_g.sort(key=lambda x: x["pct"], reverse=True)
        L.append("")
        L.append("<b>🟢 Top Gainers</b>")
        L.append("<code>")
        L.append(f"{'Symbol':<10} {'%':>7} {'LTP':>9}")
        for s in all_g[:6]:
            L.append(f"{s['symbol']:<10} {_pct(s['pct']):>7} {s['last']:>9.1f}")
        L.append("</code>")

    if all_l:
        all_l.sort(key=lambda x: x["pct"])
        L.append("")
        L.append("<b>🔴 Top Losers</b>")
        L.append("<code>")
        L.append(f"{'Symbol':<10} {'%':>7} {'LTP':>9}")
        for s in all_l[:6]:
            L.append(f"{s['symbol']:<10} {_pct(s['pct']):>7} {s['last']:>9.1f}")
        L.append("</code>")

    # High value traded
    all_v = []
    for name, data in sectors.items():
        for s in data.get("most_traded", [])[:2]:
            all_v.append(s)
    if all_v:
        all_v.sort(key=lambda x: x["value_cr"], reverse=True)
        L.append("")
        L.append("<b>💰 Top Value Traded</b>")
        L.append("<code>")
        L.append(f"{'Symbol':<10} {'ValCr':>7} {'%':>7}")
        for s in all_v[:5]:
            L.append(f"{s['symbol']:<10} {s['value_cr']:>7.0f} {_pct(s['pct']):>7}")
        L.append("</code>")

    # Delta movers
    if delta and delta.get("sectors"):
        movers = []
        for name, sd in delta["sectors"].items():
            sec = name.replace("NIFTY ", "")[:8]
            for m in sd.get("movers", [])[:2]:
                movers.append({**m, "sec": sec})
        if movers:
            movers.sort(key=lambda x: abs(x["price_chg_pct"]), reverse=True)
            L.append("")
            L.append("<b>🔄 Big Moves Since Last</b>")
            for m in movers[:6]:
                L.append(
                    f"  {m['signal']} {m['symbol']}: "
                    f"{_pct(m['price_chg_pct'])}"
                )

    return "\n".join(L)


def format_options_msg(snapshot: Dict) -> str:
    """Options PCR — compact mobile."""
    L = ["<b>📊 Options PCR</b>", ""]

    oc = snapshot.get("option_chain", {})
    if not oc:
        return "<b>📊 Options</b>\nNo data"

    for sym, data in oc.items():
        pcr = data.get("pcr_oi", 0)
        sig = data.get("signal", "")
        em = {"Bullish": "🐂", "Neutral": "😐", "Bearish": "🐻"}.get(sig, "❓")

        L.append(f"<b>{sym}</b> {em}")
        L.append("<code>")
        L.append(f"{'PCR':<6} {'Signal':<8} {'MaxPain':>8}")
        L.append(f"{pcr:>6.3f} {sig:<8} {data.get('max_pain',0):>8,.0f}")
        L.append("</code>")

        # Quick explanation
        if pcr > 1.2:
            L.append("<i>More PUTs → Market likely to go UP</i>")
        elif pcr > 0.7:
            L.append("<i>Balanced → Undecided</i>")
        else:
            L.append("<i>More CALLs → Caution, DOWN risk</i>")

        # Resistance & Support
        L.append("")
        top_ce = data.get("top_ce", [])[:3]
        top_pe = data.get("top_pe", [])[:3]
        if top_ce:
            res = " | ".join(f"{s['strike']:,.0f}" for s in top_ce)
            L.append(f"🔵 Resistance: {res}")
        if top_pe:
            sup = " | ".join(f"{s['strike']:,.0f}" for s in top_pe)
            L.append(f"🟠 Support: {sup}")

        # OI Buildup
        ce_bu = data.get("ce_buildup", [])[:2]
        pe_bu = data.get("pe_buildup", [])[:2]
        if ce_bu:
            L.append(
                "CE buildup: " +
                ", ".join(f"{s['strike']:,.0f}(+{s['chg_oi']:,})" for s in ce_bu)
            )
        if pe_bu:
            L.append(
                "PE buildup: " +
                ", ".join(f"{s['strike']:,.0f}(+{s['chg_oi']:,})" for s in pe_bu)
            )

        L.append("")

    return "\n".join(L)


def format_commodities_msg(snapshot: Dict, delta: Optional[Dict] = None) -> str:
    """Commodities + Forex — compact."""
    L = ["<b>🏆 Commodities &amp; Forex</b>", ""]

    comms = snapshot.get("commodities", {})
    if comms:
        names = {"GOLDBEES": "🥇 Gold", "SILVERBEES": "🥈 Silver"}
        for sym, data in comms.items():
            name = names.get(sym, sym)
            pct = data.get("pct", 0)
            L.append(
                f"{_e(pct)} {name}: <b>₹{data['last']:,.2f}</b> "
                f"({_pct(pct)})"
            )
            L.append(
                f"  52W: {data.get('week52_low',0):,.0f} — "
                f"{data.get('week52_high',0):,.0f}"
            )

    # Forex
    forex = snapshot.get("forex")
    if forex:
        L.append("")
        L.append("<b>💱 Forex</b>")
        L.append(f"🇺🇸🇮🇳 USD/INR: <b>₹{forex['usdinr']:.4f}</b>")
        if forex.get("usdeur"):
            L.append(f"🇺🇸🇪🇺 EUR: €{forex['usdeur']:.4f}")
        if forex.get("usdgbp"):
            L.append(f"🇺🇸🇬🇧 GBP: £{forex['usdgbp']:.4f}")

        if delta and delta.get("forex"):
            fd = delta["forex"]
            L.append(f"  {fd['direction']} ({fd['change']:+.4f})")

    return "\n".join(L)


def format_corporate_msg(snapshot: Dict) -> str:
    """Corporate actions + insider — enhanced with LTP/PE/yield."""
    L = ["<b>📋 Corporate Actions</b>", ""]

    actions = snapshot.get("corporate_actions", [])
    ipos = snapshot.get("ipos", [])
    if actions:
        L.append(f"<b>{len(actions)} actions found</b>")

        # Group by type
        divs = [a for a in actions if a.get("action_type") == "dividend"]
        splits = [a for a in actions if a.get("action_type") == "split"]
        bonus = [a for a in actions if a.get("action_type") == "bonus"]
        rights = [a for a in actions if a.get("action_type") == "rights"]
        buybacks = [a for a in actions if a.get("action_type") == "buyback"]
        results = [a for a in actions if a.get("action_type") == "results"]
        others = [a for a in actions if a.get("action_type") in ("other", "meeting")]

        if divs:
            L.append("")
            L.append("<b>💰 Dividends</b>")
            for a in divs[:8]:
                sym = a["symbol"]
                try:
                    ltp = float(a.get("ltp", 0) or 0)
                except (ValueError, TypeError):
                    ltp = 0
                try:
                    pe = float(a.get("pe_ratio", 0) or 0)
                except (ValueError, TypeError):
                    pe = 0
                try:
                    yld = float(a.get("dividend_yield", 0) or 0)
                except (ValueError, TypeError):
                    yld = 0
                try:
                    div_amt = float(a.get("dividend_amount", 0) or 0)
                except (ValueError, TypeError):
                    div_amt = 0
                ex = a.get("ex_date", "")

                line = f"  <b>{sym}</b>"
                if ltp:
                    line += f" ₹{ltp:,.1f}"
                if div_amt:
                    line += f" | ₹{div_amt}/sh"
                if yld:
                    line += f" | <b>{yld:.1f}%</b> yield"
                L.append(line)

                details = f"  📅 Ex: {ex}"
                rec = a.get("record_date", "")
                if rec:
                    details += f" | Rec: {rec}"
                if pe:
                    details += f" | PE: {pe:.1f}"
                try:
                    del_pct = float(a.get("delivery_pct", 0) or 0)
                except (ValueError, TypeError):
                    del_pct = 0
                if del_pct:
                    details += f" | Del: {del_pct:.0f}%"
                L.append(details)

        if splits:
            L.append("")
            L.append("<b>✂️ Splits</b>")
            for a in splits[:5]:
                subj = a["subject"][:45]
                ltp_str = f" ₹{a['ltp']:,.1f}" if a.get("ltp") else ""
                L.append(f"  <b>{a['symbol']}</b>{ltp_str}")
                L.append(f"  {subj}")
                details = f"  📅 Ex: {a.get('ex_date','')}"
                rec = a.get("record_date", "")
                if rec:
                    details += f" | Rec: {rec}"
                L.append(details)

        if bonus:
            L.append("")
            L.append("<b>🎁 Bonus</b>")
            for a in bonus[:5]:
                subj = a["subject"][:45]
                ltp_str = f" ₹{a['ltp']:,.1f}" if a.get("ltp") else ""
                L.append(f"  <b>{a['symbol']}</b>{ltp_str}")
                L.append(f"  {subj}")
                details = f"  📅 Ex: {a.get('ex_date','')}"
                rec = a.get("record_date", "")
                if rec:
                    details += f" | Rec: {rec}"
                L.append(details)

        if rights:
            L.append("")
            L.append("<b>📜 Rights Issues</b>")
            for a in rights[:3]:
                L.append(f"  <b>{a['symbol']}</b>: {a['subject'][:45]}")
                details = f"  📅 Ex: {a.get('ex_date','')}"
                rec = a.get("record_date", "")
                if rec:
                    details += f" | Rec: {rec}"
                L.append(details)

        if buybacks:
            L.append("")
            L.append("<b>🔙 Buybacks</b>")
            for a in buybacks[:3]:
                ltp_str = f" ₹{a['ltp']:,.1f}" if a.get("ltp") else ""
                L.append(f"  <b>{a['symbol']}</b>{ltp_str}: {a['subject'][:40]}")

        if results:
            L.append("")
            L.append("<b>📣 Results/Updates</b>")
            for a in results[:6]:
                L.append(f"  <b>{a['symbol']}</b>: {a['subject'][:60]}")

    else:
        L.append("No corporate actions this week")

    if ipos:
        L.append("")
        L.append(f"<b>🧾 IPOs</b> ({len(ipos)})")
        L.append("<code>")
        L.append(f"{'Name':<12} {'Start':>8} {'End':>8}")
        for i in ipos[:6]:
            name = (i.get("name") or i.get("symbol") or "").replace("IPO", "")[:12]
            L.append(f"{name:<12} {i.get('open','')[:8]:>8} {i.get('close','')[:8]:>8}")
        L.append("</code>")

    # Insider Trading
    insiders = snapshot.get("insider_trading", [])
    if insiders:
        L.append("")
        L.append(f"<b>🔍 Insider Trading</b> ({len(insiders)})")

        buys = [t for t in insiders if t["buy_value"] > t["sell_value"]][:4]
        sells = [t for t in insiders if t["sell_value"] > t["buy_value"]][:4]

        if buys:
            L.append("")
            L.append("🟢 <b>Insider Buys</b>")
            for t in buys:
                val = t["buy_value"]
                amt = _compact_num(val)
                L.append(
                    f"  {t['symbol']}: {amt} "
                    f"by {t['acquirer'][:25]}"
                )

        if sells:
            L.append("")
            L.append("🔴 <b>Insider Sells</b>")
            for t in sells:
                val = t["sell_value"]
                amt = _compact_num(val)
                L.append(
                    f"  {t['symbol']}: {amt} "
                    f"by {t['acquirer'][:25]}"
                )

    return "\n".join(L)


def format_preopen_msg(snapshot: Dict) -> str:
    """Pre-open market — compact."""
    po = snapshot.get("preopen")
    if not po:
        return "<b>🌅 Pre-Open</b>\nNo data"

    L = ["<b>🌅 Pre-Open</b>", ""]
    L.append(f"🟢 {po.get('advances',0)} | 🔴 {po.get('declines',0)}")
    L.append("")

    for s in po.get("gainers", [])[:5]:
        L.append(
            f"  🟢 {s['symbol']}: ₹{s['iep']:,.1f} "
            f"({_pct(s['pct'])})"
        )
    L.append("")
    for s in po.get("losers", [])[:5]:
        L.append(
            f"  🔴 {s['symbol']}: ₹{s['iep']:,.1f} "
            f"({_pct(s['pct'])})"
        )

    return "\n".join(L)


def format_block_bulk_msg(snapshot: Dict) -> str:
    """Block & Bulk deals — institutional activity."""
    L = ["<b>🏦 Institutional Deals</b>", ""]

    blocks = snapshot.get("block_deals", [])
    bulks = snapshot.get("bulk_deals", [])

    if blocks:
        L.append(f"<b>📦 Block Deals</b> ({len(blocks)})")
        for d in blocks[:8]:
            bs = "🟢" if "buy" in d.get("buy_sell", "").lower() else "🔴"
            L.append(
                f"  {bs} <b>{d['symbol']}</b> "
                f"₹{d['value_cr']:,.1f}Cr"
            )
            L.append(
                f"  {d['client'][:30]} @ ₹{d['price']:,.1f}"
            )

    if bulks:
        L.append("")
        L.append(f"<b>📊 Bulk Deals</b> ({len(bulks)})")
        for d in bulks[:8]:
            bs = "🟢" if "buy" in d.get("buy_sell", "").lower() else "🔴"
            L.append(
                f"  {bs} <b>{d['symbol']}</b> "
                f"₹{d['value_cr']:,.1f}Cr"
            )
            L.append(
                f"  {d['client'][:30]} @ ₹{d['price']:,.1f}"
            )

    if not blocks and not bulks:
        L.append("No block/bulk deals today")

    return "\n".join(L)


def format_52w_alerts_msg(snapshot: Dict) -> str:
    """52-week high/low proximity alerts."""
    alerts = snapshot.get("alerts", {})
    highs = alerts.get("near_52w_high", [])
    lows = alerts.get("near_52w_low", [])

    if not highs and not lows:
        return ""

    L = ["<b>📡 52-Week Alerts</b>", ""]

    if highs:
        L.append(f"<b>🚀 Near 52W HIGH</b> ({len(highs)})")
        L.append("<i>Potential breakout candidates</i>")
        for a in highs[:10]:
            L.append(
                f"  🟢 <b>{a['symbol']}</b> ₹{a['last']:,.1f} "
                f"({a['distance_pct']:.1f}% away)"
            )
            L.append(
                f"  52H: ₹{a['year_high']:,.1f} | "
                f"Today: {_pct(a.get('pct_today', 0))}"
            )

    if lows:
        L.append("")
        L.append(f"<b>💎 Near 52W LOW</b> ({len(lows)})")
        L.append("<i>Value pick candidates</i>")
        for a in lows[:10]:
            L.append(
                f"  🔴 <b>{a['symbol']}</b> ₹{a['last']:,.1f} "
                f"({a['distance_pct']:.1f}% away)"
            )
            L.append(
                f"  52L: ₹{a['year_low']:,.1f} | "
                f"Today: {_pct(a.get('pct_today', 0))}"
            )

    return "\n".join(L)


def format_context_msg(delta: Dict) -> str:
    """Market context / explainer from delta engine."""
    insights = delta.get("market_context", [])
    rotation = delta.get("sector_rotation")

    if not insights and not rotation:
        return ""

    L = ["<b>🧠 Market Intelligence</b>", ""]

    if insights:
        for insight in insights:
            L.append(insight)
            L.append("")

    if rotation:
        rotations = rotation.get("rotations", [])
        if rotations:
            L.append("<b>🔄 Sector Rotation</b>")
            for r in rotations:
                L.append(
                    f"  {r['signal']} <b>{r['sector']}</b> "
                    f"({_pct(r['prev_pct'])} → {_pct(r['curr_pct'])})"
                )

    return "\n".join(L)


def format_delta_alert(delta: Dict) -> Optional[str]:
    """Quick alert for significant changes."""
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
            pct = chg.get("pct_change", 0)
            if abs(pct) >= 1.0:
                alerts.append(
                    f"{chg['signal']} {name}: "
                    f"{_pct(pct)} since last"
                )

    if not alerts:
        return None

    L = ["<b>⚡ ALERT</b>", ""]
    for a in alerts[:8]:
        L.append(f"• {a}")

    # Add context
    context = delta.get("market_context", [])
    if context:
        L.append("")
        for c in context[:3]:
            L.append(c)

    return "\n".join(L)
