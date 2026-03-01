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

import logging
from datetime import datetime
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
