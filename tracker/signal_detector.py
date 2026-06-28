"""
Signal Detector - Buy/Sell Signal Generation
==============================================

Analyzes market data to generate actionable buy/sell signals based on:
- Technical indicators (52W proximity, volume, delivery%)
- Institutional flows (FII/DII patterns)
- Sector rotation and momentum
- Risk/reward scoring

Signal Confidence Levels:
- 🔥 Strong: 3+ indicators aligned
- ⚡ Moderate: 2 indicators aligned  
- 💡 Weak: 1 indicator present
"""

import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config

logger = logging.getLogger(__name__)


class SignalDetector:
    """Detects buy/sell signals from market snapshot data."""
    
    def __init__(self):
        self.buy_signals = []
        self.sell_signals = []
        self.watch_signals = []
    
    def analyze(self, snapshot: Dict, delta: Optional[Dict] = None) -> Dict:
        """
        Analyze snapshot and generate trading signals.
        
        Returns:
            {
                "buy": [{"symbol": "TCS", "confidence": "Strong", "reasons": [...]}],
                "sell": [{"symbol": "INFY", "confidence": "Moderate", "reasons": [...]}],
                "watch": [{"symbol": "WIPRO", "type": "Breakout Watch", "reasons": [...]}],
            }
        """
        self.buy_signals = []
        self.sell_signals = []
        self.watch_signals = []
        
        # Analyze stocks in all sectors
        sectors = snapshot.get("sectors", {})
        for sector_name, sector_data in sectors.items():
            stocks = sector_data.get("stocks", [])
            for stock in stocks:
                self._analyze_stock(stock, sector_name, sector_data, delta)
        
        # Analyze sector rotation opportunities
        if delta:
            self._analyze_sector_rotation(snapshot, delta)
        
        # Sort by confidence
        self.buy_signals.sort(key=lambda x: self._confidence_score(x["confidence"]), reverse=True)
        self.sell_signals.sort(key=lambda x: self._confidence_score(x["confidence"]), reverse=True)
        
        return {
            "buy": self.buy_signals[:15],  # Top 15 buy signals
            "sell": self.sell_signals[:15],
            "watch": self.watch_signals[:10],
            "generated_at": datetime.now().isoformat(),
        }
    
    def _analyze_stock(
        self, 
        stock: Dict, 
        sector_name: str, 
        sector_data: Dict,
        delta: Optional[Dict]
    ):
        """Analyze individual stock for signals."""
        symbol = stock.get("symbol", "")
        if not symbol:
            return
        
        reasons_buy = []
        reasons_sell = []
        reasons_watch = []
        
        # Extract metrics
        pct = stock.get("pct", 0)
        volume = stock.get("volume", 0)
        near_52h = stock.get("near_52h", 999)
        near_52l = stock.get("near_52l", 999)
        last = stock.get("last", 0)
        year_high = stock.get("year_high", 0)
        year_low = stock.get("year_low", 0)
        chg_30d = stock.get("chg_30d", 0)
        chg_365d = stock.get("chg_365d", 0)
        
        # Check delivery% if available (needs enrichment)
        delivery_pct = stock.get("delivery_pct", 0)
        
        # ==== BUY SIGNALS ====
        
        # 1. 52W HIGH BREAKOUT (near breakout + positive momentum)
        if near_52h is not None and isinstance(near_52h, (int, float)) and 0 < near_52h <= config.NEAR_52W_HIGH_PCT:
            if pct > 0:
                reasons_buy.append(f"Near 52W high ({near_52h:.1f}% away) with upward momentum")
            else:
                reasons_watch.append(f"Near 52W high ({near_52h:.1f}% away) – waiting for breakout")
        
        # 2. OVERSOLD REVERSAL (near 52W low + today's bounce)
        if near_52l is not None and isinstance(near_52l, (int, float)) and 0 < near_52l <= config.NEAR_52W_LOW_PCT:
            if pct > 2:
                reasons_buy.append(f"Strong bounce from 52W low (up {pct:.1f}% today)")
            elif pct > 0:
                reasons_watch.append(f"Near 52W low ({near_52l:.1f}% away) – value opportunity")
        
        # 3. HIGH DELIVERY % (genuine buying, not speculation)
        if delivery_pct >= config.HIGH_DELIVERY_PCT and pct > 0:
            reasons_buy.append(f"High delivery {delivery_pct:.0f}% – genuine accumulation")
        
        # 4. STRONG 30-DAY MOMENTUM (consistent uptrend)
        if chg_30d > 10 and pct > 0:
            reasons_buy.append(f"Strong 30d momentum (+{chg_30d:.1f}%)")
        
        # 5. SECTOR LEADER (top gainer in strong sector)
        sector_pct = sector_data.get("index_pct", 0)
        gainers = sector_data.get("gainers", [])
        if gainers and gainers[0].get("symbol") == symbol and sector_pct > 1:
            reasons_buy.append(f"Sector leader in strong {sector_name.replace('NIFTY ', '')} (+{sector_pct:.1f}%)")
        
        # 6. FROM DELTA: Big institutional buying signals
        if delta:
            sector_delta = delta.get("sectors", {}).get(sector_name, {})
            movers = sector_delta.get("movers", [])
            for m in movers:
                if m.get("symbol") == symbol and m.get("signal", "").startswith("🟢"):
                    reasons_buy.append(f"Recent surge: {m.get('signal', '')}")
        
        # ==== SELL SIGNALS ====
        
        # 1. DISTRIBUTION (low delivery% with price up – weak hands)
        if delivery_pct > 0 and delivery_pct < config.LOW_DELIVERY_PCT and pct < -1:
            reasons_sell.append(f"Distribution detected (low {delivery_pct:.0f}% delivery)")
        
        # 2. BREAKDOWN FROM 52W HIGH (was near high, now falling)
        if near_52h is not None and 2 < near_52h <= 5 and pct < -2:
            reasons_sell.append(f"Failed breakout – down {abs(pct):.1f}% from 52W high")
        
        # 3. WEAK 30-DAY MOMENTUM (sustained decline)
        if chg_30d < -10 and pct < 0:
            reasons_sell.append(f"Weak 30d momentum ({chg_30d:.1f}%)")
        
        # 4. SECTOR LAGGARD (bottom loser in weak sector)
        losers = sector_data.get("losers", [])
        if losers and losers[0].get("symbol") == symbol and sector_pct < -1:
            reasons_sell.append(f"Sector laggard in weak {sector_name.replace('NIFTY ', '')} ({sector_pct:.1f}%)")
        
        # Generate signals
        if len(reasons_buy) >= 2:
            confidence = "Strong" if len(reasons_buy) >= 3 else "Moderate"
            self.buy_signals.append({
                "symbol": symbol,
                "sector": sector_name.replace("NIFTY ", ""),
                "ltp": last,
                "change_pct": pct,
                "confidence": confidence,
                "reasons": reasons_buy,
            })
        
        if len(reasons_sell) >= 2:
            confidence = "Strong" if len(reasons_sell) >= 3 else "Moderate"
            self.sell_signals.append({
                "symbol": symbol,
                "sector": sector_name.replace("NIFTY ", ""),
                "ltp": last,
                "change_pct": pct,
                "confidence": confidence,
                "reasons": reasons_sell,
            })
        
        if reasons_watch and not reasons_buy and not reasons_sell:
            self.watch_signals.append({
                "symbol": symbol,
                "sector": sector_name.replace("NIFTY ", ""),
                "ltp": last,
                "type": "Breakout Watch" if "52W high" in str(reasons_watch) else "Value Watch",
                "reasons": reasons_watch,
            })
    
    def _analyze_sector_rotation(self, snapshot: Dict, delta: Dict):
        """Detect sector rotation opportunities."""
        rotation = delta.get("sector_rotation", {})
        if not rotation:
            return
        
        # Money flowing INTO sectors (BUY opportunity)
        for rot in rotation:
            if "INTO" in rot:
                # Extract sector name
                parts = rot.split("INTO")
                if len(parts) == 2:
                    target_sector = parts[1].strip()
                    self.watch_signals.append({
                        "symbol": f"SECTOR:{target_sector}",
                        "sector": target_sector,
                        "ltp": 0,
                        "type": "Sector Rotation",
                        "reasons": [rot],
                    })
    
    @staticmethod
    def _confidence_score(confidence: str) -> int:
        """Convert confidence to numeric score for sorting."""
        return {"Strong": 3, "Moderate": 2, "Weak": 1}.get(confidence, 0)

    # ── Phase 1: Scored + Categorised Signals ────────────────────────────────

    def analyze_with_categories(
        self,
        snapshot: Dict,
        delta: Optional[Dict] = None,
        data_dir: Optional[str] = None,
    ) -> Dict:
        """
        Full scored analysis with trade categories.

        Returns dict with keys:
          intraday, swing, long_term, dividend_captures,
          volume_spikes, top_overall, fii_sentiment, generated_at
        """
        sectors = snapshot.get("sectors", {})
        if not sectors:
            return {
                "intraday": [], "swing": [], "long_term": [],
                "dividend_captures": [], "volume_spikes": [], "top_overall": [],
                "fii_sentiment": 0, "generated_at": datetime.now().isoformat(),
            }

        # FII sentiment score (0-10)
        fii_score = self._get_fii_score(snapshot)

        # Sector median volumes (for volume-ratio calculation)
        sector_medians = self._compute_sector_volume_medians(sectors)

        # Historical price trends per symbol (from stored snapshots)
        trends = self._build_historical_trends(data_dir) if data_dir else {}

        # Score every stock across all sectors; deduplicate by symbol
        seen_symbols: set = set()
        all_scored: List[Dict] = []

        for sector_name, sector_data in sectors.items():
            median_vol = sector_medians.get(sector_name, 0)
            for stock in sector_data.get("stocks", []):
                sym = stock.get("symbol", "")
                if not sym or sym in seen_symbols:
                    continue
                seen_symbols.add(sym)
                scored = self._score_and_classify(
                    stock, sector_name, median_vol, fii_score,
                    trends.get(sym, "SIDEWAYS"),
                )
                if scored:
                    all_scored.append(scored)

        # Sort by score descending
        all_scored.sort(key=lambda x: x["score"], reverse=True)

        # Categorise (pick top N per category, no overlap)
        intraday   = [s for s in all_scored if s["category"] == "INTRADAY"][:5]
        swing      = [s for s in all_scored if s["category"] == "SWING"][:7]
        long_term  = [s for s in all_scored if s["category"] == "LONG-TERM"][:7]
        vol_spikes = [s for s in all_scored if s.get("volume_spike")][:5]

        # Dividend captures from corporate actions
        div_captures = self._get_dividend_captures(snapshot)

        return {
            "intraday":         intraday,
            "swing":            swing,
            "long_term":        long_term,
            "dividend_captures": div_captures,
            "volume_spikes":    vol_spikes,
            "top_overall":      all_scored[:10],
            "fii_sentiment":    fii_score,
            "generated_at":     datetime.now().isoformat(),
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_sector_volume_medians(sectors: Dict) -> Dict[str, float]:
        """Return {sector_name: median_volume} for volume-ratio calculation."""
        result: Dict[str, float] = {}
        for name, data in sectors.items():
            vols = [s.get("volume", 0) for s in data.get("stocks", []) if s.get("volume", 0) > 0]
            result[name] = statistics.median(vols) if vols else 0
        return result

    @staticmethod
    def _get_fii_score(snapshot: Dict) -> float:
        """Return FII sentiment score 0-10 (10 = heavy FII buying)."""
        fii_data = snapshot.get("fii_dii", {})
        fii_net  = (fii_data.get("fii") or {}).get("net", 0) or 0
        if fii_net >= 1000:
            return 10.0
        if fii_net >= 0:
            return 7.0
        if fii_net >= -1000:
            return 4.0
        return 0.0

    @staticmethod
    def _build_historical_trends(data_dir: str, lookback: int = 5) -> Dict[str, str]:
        """
        Load the last `lookback` snapshots with sector data and compute
        a simple trend label per symbol: UPTREND / DOWNTREND / SIDEWAYS.
        """
        snap_dir = Path(data_dir) / "snapshots"
        snap_files = sorted(snap_dir.glob("snapshot_*.json"))
        trends: Dict[str, str] = {}

        # Collect price series per symbol
        price_series: Dict[str, List[float]] = {}
        count = 0
        for sf in reversed(snap_files):
            if count >= lookback:
                break
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                for sector_data in data.get("sectors", {}).values():
                    for stock in sector_data.get("stocks", []):
                        sym = stock.get("symbol", "")
                        ltp = stock.get("last", 0)
                        if sym and ltp > 0:
                            price_series.setdefault(sym, []).append(ltp)
                count += 1
            except Exception:
                continue

        # Determine trend from price series (most-recent first → reverse)
        for sym, prices in price_series.items():
            if len(prices) < 3:
                trends[sym] = "SIDEWAYS"
                continue
            # prices[0] = most recent, prices[-1] = oldest
            ups   = sum(1 for i in range(len(prices) - 1) if prices[i] > prices[i + 1])
            downs = sum(1 for i in range(len(prices) - 1) if prices[i] < prices[i + 1])
            total = len(prices) - 1
            if ups / total >= 0.6:
                trends[sym] = "UPTREND"
            elif downs / total >= 0.6:
                trends[sym] = "DOWNTREND"
            else:
                trends[sym] = "SIDEWAYS"
        return trends

    def _score_and_classify(
        self,
        stock: Dict,
        sector_name: str,
        median_vol: float,
        fii_score: float,
        trend: str,
    ) -> Optional[Dict]:
        """
        Score a stock 0-100 and assign a trade category.

        Score breakdown:
          Today momentum   0-25 pts   (pct)
          30-day trend     0-20 pts   (chg_30d)
          52W position     0-25 pts   (near_52h / near_52l)
          Volume ratio     0-20 pts   (volume vs sector median)
          FII sentiment    0-10 pts   (market-wide modifier)
        """
        sym    = stock.get("symbol", "")
        ltp    = stock.get("last",    0)
        pct    = stock.get("pct",     0) or 0
        chg30  = stock.get("chg_30d", 0) or 0
        chg365 = stock.get("chg_365d", 0) or 0
        near_h = stock.get("near_52h", 999) or 999
        near_l = stock.get("near_52l", 999) or 999
        volume = stock.get("volume",  0)  or 0

        if not sym or ltp <= 0:
            return None

        # 1. Today momentum (0-25)
        s_mom = max(0.0, min(25.0, (pct + 10.0) / 20.0 * 25.0))

        # 2. 30-day trend (0-20)
        s_30d = max(0.0, min(20.0, (chg30 + 20.0) / 40.0 * 20.0))

        # 3. 52W position (0-25)
        #    near_52h: % below 52W high (0 = AT 52W high → breakout zone)
        #    near_52l: % above 52W low  (0 = AT 52W low  → deep value)
        if near_h <= 3 and pct > 0:
            s_52w = 25.0          # breakout momentum
        elif near_h <= 8 and pct > 0:
            s_52w = 18.0          # approaching breakout
        elif near_l <= 5:
            s_52w = 20.0          # deep value zone
        elif near_l <= 15:
            s_52w = 14.0          # value zone
        else:
            s_52w = max(0.0, 10.0 - near_h * 0.2)  # general mid-range

        # 4. Volume ratio (0-20)
        vol_ratio = (volume / median_vol) if median_vol > 0 else 1.0
        s_vol = min(20.0, vol_ratio * 8.0)

        # 5. FII sentiment (0-10) — already 0-10
        s_fii = fii_score

        # Historical trend bonus / penalty
        if trend == "UPTREND":
            s_trend = 8.0
        elif trend == "DOWNTREND":
            s_trend = -8.0
        else:
            s_trend = 0.0

        raw_score = s_mom + s_30d + s_52w + s_vol + s_fii + s_trend
        score = max(0, min(100, round(raw_score)))

        # ── Category classification ──
        volume_spike = vol_ratio >= 2.0 and pct > 0

        # INTRADAY: strong same-day momentum + volume
        if pct >= 2.0 and vol_ratio >= 1.5 and score >= 55:
            category = "INTRADAY"
        elif pct >= 1.5 and near_h <= 3 and vol_ratio >= 1.2 and score >= 50:
            category = "INTRADAY"  # pre-breakout play

        # LONG-TERM: value or consistent compounder
        elif (0 < near_l <= 20 and chg365 < -5) or (chg365 >= 20 and chg30 >= 3):
            category = "LONG-TERM"

        # SWING: moderate momentum + 30d positive + above-avg volume
        elif pct >= 0.5 and chg30 >= 2 and vol_ratio >= 1.1 and score >= 45:
            category = "SWING"

        else:
            category = "WATCH"    # not strong enough to trade yet

        # Build reasons list (only real, non-zero conditions)
        reasons: List[str] = []
        if pct > 0:
            reasons.append(f"Today +{pct:.1f}%")
        elif pct < 0:
            reasons.append(f"Today {pct:.1f}%")
        if near_h <= 5 and pct > 0:
            reasons.append(f"Near 52W high (only {near_h:.1f}% away — breakout zone)")
        if 0 < near_l <= 20:
            reasons.append(f"Near 52W low ({near_l:.1f}% above — value zone)")
        if chg30 > 5:
            reasons.append(f"30d momentum +{chg30:.1f}%")
        elif chg30 < -10:
            reasons.append(f"30d trend weak {chg30:.1f}%")
        if vol_ratio >= 1.5:
            reasons.append(f"Volume {vol_ratio:.1f}× sector avg — institutional interest")
        if volume_spike:
            reasons.append(f"⚡ Volume spike {vol_ratio:.1f}× — possible breakout")
        if trend == "UPTREND":
            reasons.append("Multi-day uptrend confirmed")
        elif trend == "DOWNTREND":
            reasons.append("Multi-day downtrend — caution")
        if chg365 >= 20:
            reasons.append(f"1-year compounder +{chg365:.1f}%")
        if chg365 < -20:
            reasons.append(f"Beaten down {chg365:.1f}% in 1yr — recovery candidate")

        return {
            "symbol":       sym,
            "ltp":          ltp,
            "pct":          pct,
            "chg_30d":      chg30,
            "chg_365d":     chg365,
            "sector":       sector_name.replace("NIFTY ", "") or sector_name,
            "score":        score,
            "category":     category,
            "trend":        trend,
            "vol_ratio":    round(vol_ratio, 2),
            "volume_spike": volume_spike,
            "reasons":      reasons,
        }

    @staticmethod
    def _get_dividend_captures(snapshot: Dict) -> List[Dict]:
        """
        Find dividend capture opportunities:
        ex_date within next 5 days, yield > 0.5%, ltp > 0.
        """
        actions = snapshot.get("corporate_actions") or []
        today   = datetime.now().date()
        cutoff  = today + timedelta(days=5)
        captures: List[Dict] = []

        for a in actions:
            if "dividend" not in a.get("subject", "").lower():
                continue
            ex_str = a.get("ex_date", "")
            ex_date = None
            for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    ex_date = datetime.strptime(ex_str, fmt).date()
                    break
                except (ValueError, TypeError):
                    continue
            if not ex_date or not (today <= ex_date <= cutoff):
                continue

            ltp = float(a.get("ltp") or 0)
            if ltp <= 0:
                continue

            # Extract dividend amount from subject
            import re
            match = re.search(
                r'(?:Rs\.?|Re\.?)\s*([\d.]+)\s*(?:/|-|per)\s*(?:share|shr)',
                a.get("subject", ""), re.IGNORECASE,
            )
            div_amt = float(match.group(1)) if match else 0.0
            if div_amt <= 0:
                continue

            yield_pct = round(div_amt / ltp * 100, 2)
            if yield_pct < 0.5:
                continue

            days_left = (ex_date - today).days
            captures.append({
                "symbol":     a.get("symbol", ""),
                "ltp":        ltp,
                "div_amount": div_amt,
                "yield_pct":  yield_pct,
                "ex_date":    ex_str,
                "days_left":  days_left,
                "source":     a.get("source", "NSE"),
            })

        captures.sort(key=lambda x: x["yield_pct"], reverse=True)
        return captures[:8]


def format_signals_msg(signals: Dict) -> str:
    """Format trading signals into compact Telegram message."""
    L = ["<b>📊 Trading Signals</b>", ""]
    
    buy = signals.get("buy", [])
    sell = signals.get("sell", [])
    watch = signals.get("watch", [])
    
    if buy:
        L.append(f"<b>🟢 BUY Signals ({len(buy)})</b>")
        L.append("")
        for s in buy[:10]:
            conf_em = "🔥" if s["confidence"] == "Strong" else "⚡"
            L.append(f"{conf_em} <b>{s['symbol']}</b> ₹{s['ltp']:,.1f} ({s['change_pct']:+.1f}%)")
            L.append(f"  <i>{s['sector']}</i> | {s['confidence']}")
            for i, r in enumerate(s['reasons'][:3], 1):
                L.append(f"  {i}. {r}")
            L.append("")
    else:
        L.append("<b>🟢 BUY Signals</b>")
        L.append("No strong buy signals at this time")
        L.append("")
    
    if sell:
        L.append(f"<b>🔴 SELL Signals ({len(sell)})</b>")
        L.append("")
        for s in sell[:10]:
            conf_em = "🔥" if s["confidence"] == "Strong" else "⚡"
            L.append(f"{conf_em} <b>{s['symbol']}</b> ₹{s['ltp']:,.1f} ({s['change_pct']:+.1f}%)")
            L.append(f"  <i>{s['sector']}</i> | {s['confidence']}")
            for i, r in enumerate(s['reasons'][:3], 1):
                L.append(f"  {i}. {r}")
            L.append("")
    
    if watch:
        L.append(f"<b>👀 Watch List ({len(watch)})</b>")
        for w in watch[:8]:
            if "SECTOR:" in w.get("symbol", ""):
                L.append(f"  📍 {w['type']}: {w['reasons'][0]}")
            else:
                L.append(f"  💡 {w['symbol']} – {w['type']}")
        L.append("")
    
    L.append(f"<i>Generated: {datetime.now().strftime('%I:%M%p')}</i>")
    
    return "\n".join(L)
