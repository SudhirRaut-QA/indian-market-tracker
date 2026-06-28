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
import re
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

    # ── Phase 2: Predictive Analysis from Stored Data ───────────────────────

    def analyze_predictive(self, snapshot: Dict, data_dir: Optional[str] = None) -> Dict:
        """Phase 2 predictive analytics using stored historical snapshots."""
        out = {
            "momentum_levels": {"leaders": [], "laggards": []},
            "sector_rotation": {"gaining": [], "losing": []},
            "breakout_tracker": [],
            "fii_dii_trend": {
                "prediction": "UNKNOWN",
                "score": 0,
                "avg_fii_5d": 0.0,
                "avg_dii_5d": 0.0,
                "fii_trend_5d": 0.0,
                "dii_trend_5d": 0.0,
                "series": [],
                "note": "Not enough data",
            },
            "generated_at": datetime.now().isoformat(),
        }

        if not data_dir:
            return out

        daily = self._load_daily_snapshots(data_dir, max_days=45)
        if len(daily) < 3:
            return out

        stock_hist = self._build_stock_history(daily)
        sector_hist = self._build_sector_history(daily)
        fii_hist = self._build_fii_dii_history(daily)

        out["momentum_levels"] = self._compute_momentum_support_resistance(stock_hist)
        out["sector_rotation"] = self._compute_sector_rotation_consistency(sector_hist)
        out["breakout_tracker"] = self._compute_breakout_persistence(stock_hist)
        out["fii_dii_trend"] = self._compute_fii_dii_rolling_signal(fii_hist)
        return out

    def analyze_fii_dii_trend(self, data_dir: Optional[str] = None) -> Dict:
        """Compute only the 5-day rolling FII/DII signal from stored snapshots."""
        if not data_dir:
            return self._compute_fii_dii_rolling_signal([])
        daily = self._load_daily_snapshots(data_dir, max_days=45)
        fii_hist = self._build_fii_dii_history(daily)
        return self._compute_fii_dii_rolling_signal(fii_hist)

    # ── Phase 4: ML-style Prediction ───────────────────────────────────────

    def analyze_ml_prediction(self, snapshot: Dict, data_dir: Optional[str] = None) -> Dict:
        """Phase 4 prediction engine for next-session stock and sector outlook."""
        out = {
            "top_stocks": [],
            "sector_prediction": {
                "outlook": "NEUTRAL",
                "score": 0.0,
                "global_avg_pct": 0.0,
                "fear_greed_score": 50.0,
                "fii_net": 0.0,
                "likely_leaders": [],
                "likely_laggards": [],
            },
            "generated_at": datetime.now().isoformat(),
        }

        sectors = snapshot.get("sectors") or {}
        if not sectors:
            return out

        daily = self._load_daily_snapshots(data_dir, max_days=45) if data_dir else []
        stock_hist = self._build_stock_history(daily) if daily else {}
        sector_hist = self._build_sector_history(daily) if daily else {}
        profiles = self._build_historical_profiles(data_dir) if data_dir else {}

        fii_net = self._safe_float(((snapshot.get("fii_dii") or {}).get("fii") or {}).get("net", 0))
        fii_norm = self._clamp(fii_net / 3000.0, -1.0, 1.0)

        seen: set = set()
        scored: List[Dict] = []
        for sector_name, sector_data in sectors.items():
            for stock in sector_data.get("stocks", []):
                sym = stock.get("symbol", "")
                if not sym or sym in seen:
                    continue
                seen.add(sym)
                row = self._score_phase4_stock(stock, sector_name, stock_hist.get(sym) or [], profiles.get(sym) or {}, fii_norm)
                if row:
                    scored.append(row)

        positives = [x for x in scored if x.get("score", 0) >= 55]
        ranked = sorted(positives if positives else scored, key=lambda x: x.get("score", 0), reverse=True)
        out["top_stocks"] = ranked[:5]
        out["sector_prediction"] = self._predict_phase4_sectors(snapshot, sector_hist, fii_norm, fii_net)
        return out

    def _score_phase4_stock(
        self,
        stock: Dict,
        sector_name: str,
        history: List[Dict],
        profile: Dict,
        fii_norm: float,
    ) -> Optional[Dict]:
        """Apply Phase 4 stock model score.

        Score = 0.3*5d_return + 0.2*volume_ratio + 0.3*52W_position + 0.2*FII_net
        where all components are normalized to [-1, 1].
        """
        sym = stock.get("symbol", "")
        ltp = self._safe_float(stock.get("last", 0))
        if not sym or ltp <= 0:
            return None

        prices = [self._safe_float(x.get("last", 0)) for x in history if self._safe_float(x.get("last", 0)) > 0]
        if len(prices) >= 5:
            base_5d = prices[-5]
        elif prices:
            base_5d = prices[0]
        else:
            base_5d = 0.0

        if base_5d > 0:
            ret_5d = (ltp / base_5d - 1.0) * 100.0
        else:
            ret_5d = self._safe_float(stock.get("pct", 0))
        ret_norm = self._clamp(ret_5d / 12.0, -1.0, 1.0)

        avg_vol_5d = self._safe_float(profile.get("avg_vol_5d", 0.0))
        vol_today = self._safe_float(stock.get("volume", 0.0))
        vol_ratio = (vol_today / avg_vol_5d) if avg_vol_5d > 0 else 1.0
        vol_norm = self._clamp((vol_ratio - 1.0) / 1.5, -1.0, 1.0)

        near_h = self._safe_float(stock.get("near_52h", 999.0))
        near_l = self._safe_float(stock.get("near_52l", 999.0))
        pos_52w = self._phase4_52w_position_signal(near_h, near_l)

        raw = (ret_norm * 0.3) + (vol_norm * 0.2) + (pos_52w * 0.3) + (fii_norm * 0.2)
        score = round((raw + 1.0) * 50.0, 1)

        return {
            "symbol": sym,
            "sector": sector_name.replace("NIFTY ", "") or sector_name,
            "ltp": round(ltp, 2),
            "score": score,
            "raw_score": round(raw, 4),
            "five_day_return": round(ret_5d, 2),
            "volume_ratio": round(vol_ratio, 2),
            "near_52h": round(near_h, 2) if near_h < 998 else None,
            "near_52l": round(near_l, 2) if near_l < 998 else None,
        }

    def _predict_phase4_sectors(
        self,
        snapshot: Dict,
        sector_hist: Dict[str, List[float]],
        fii_norm: float,
        fii_net: float,
    ) -> Dict:
        """Predict likely sector leaders/laggards for next session."""
        gidx = snapshot.get("global_indices") or {}
        gs = snapshot.get("global_sentiment") or {}
        fg = gs.get("fear_greed") or {}

        g_pcts = [self._safe_float(v.get("pct", 0)) for v in gidx.values()]
        global_avg = statistics.mean(g_pcts) if g_pcts else 0.0
        global_norm = self._clamp(global_avg / 1.5, -1.0, 1.0)

        fg_score = self._safe_float(fg.get("score", 50.0))
        fg_norm = self._clamp((fg_score - 50.0) / 50.0, -1.0, 1.0)

        # Composite market context from global risk, fear-greed, and domestic FII flows.
        market_score = (global_norm * 0.4) + (fg_norm * 0.3) + (fii_norm * 0.3)

        if market_score >= 0.25:
            outlook = "BULLISH"
        elif market_score <= -0.25:
            outlook = "BEARISH"
        else:
            outlook = "NEUTRAL"

        momentum_by_sector: Dict[str, float] = {}
        if sector_hist:
            for sec, vals in sector_hist.items():
                if not vals:
                    continue
                recent = vals[-5:] if len(vals) >= 5 else vals
                momentum_by_sector[sec] = statistics.mean(recent)
        else:
            sectors = snapshot.get("sectors") or {}
            for sec_name, sec_data in sectors.items():
                momentum_by_sector[sec_name] = self._safe_float(sec_data.get("index_pct", 0))

        rows: List[Dict] = []
        for sec, mom in momentum_by_sector.items():
            mom_norm = self._clamp(mom / 1.5, -1.0, 1.0)
            sector_score = (mom_norm * 0.6) + (market_score * 0.4)
            rows.append({
                "sector": sec.replace("NIFTY ", "") or sec,
                "avg_5d": round(mom, 2),
                "model_score": round(sector_score * 100.0, 1),
            })

        leaders = sorted(rows, key=lambda x: x.get("model_score", 0), reverse=True)[:3]
        laggards = sorted(rows, key=lambda x: x.get("model_score", 0))[:3]

        # Flag data quality so downstream formatters can add context
        data_sources: List[str] = []
        if g_pcts:
            data_sources.append("global")
        if fg.get("score") is not None:
            data_sources.append("fear_greed")
        data_sources.append("fii")
        if len(data_sources) == 1:  # only FII available
            data_note = "Limited: sector prediction based on FII flows only (no global/sentiment data)"
        else:
            data_note = f"Sources: {', '.join(data_sources)}"

        return {
            "outlook": outlook,
            "score": round(market_score, 3),
            "global_avg_pct": round(global_avg, 2),
            "fear_greed_score": round(fg_score, 1),
            "fii_net": round(fii_net, 2),
            "likely_leaders": leaders,
            "likely_laggards": laggards,
            "data_note": data_note,
        }

    @staticmethod
    def _phase4_52w_position_signal(near_h: float, near_l: float) -> float:
        """Convert 52W position into momentum signal in [-1, 1]."""
        if near_h <= 2:
            return 1.0
        if near_h <= 5:
            return 0.6
        if near_h <= 10:
            return 0.25
        if near_l <= 5:
            return -1.0
        if near_l <= 10:
            return -0.6
        if near_l <= 20:
            return -0.3
        return 0.0

    @staticmethod
    def _clamp(val: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, val))

    @staticmethod
    def _safe_float(val: object, default: float = 0.0) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _load_daily_snapshots(data_dir: str, max_days: int = 45) -> List[Tuple[datetime.date, Dict]]:
        """Load one latest snapshot per day from snapshot_YYYYMMDD_HHMMSS.json files."""
        snap_dir = Path(data_dir) / "snapshots"
        if not snap_dir.exists():
            return []

        name_rx = re.compile(r"snapshot_(\d{8})_(\d{6})\.json$")
        latest_by_day: Dict[datetime.date, Tuple[datetime, Path]] = {}

        for sf in snap_dir.glob("snapshot_*.json"):
            m = name_rx.match(sf.name)
            if not m:
                continue
            try:
                ts = datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S")
            except ValueError:
                continue
            day = ts.date()
            prev = latest_by_day.get(day)
            if not prev or ts > prev[0]:
                latest_by_day[day] = (ts, sf)

        if not latest_by_day:
            return []

        days_sorted = sorted(latest_by_day.keys())[-max_days:]
        out: List[Tuple[datetime.date, Dict]] = []
        for d in days_sorted:
            _, sf = latest_by_day[d]
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    out.append((d, data))
            except Exception:
                continue
        return out

    @staticmethod
    def _build_stock_history(daily: List[Tuple[datetime.date, Dict]]) -> Dict[str, List[Dict]]:
        """Build per-symbol day-wise history from sector snapshots."""
        hist: Dict[str, List[Dict]] = {}
        for day, data in daily:
            sectors = data.get("sectors") or {}
            seen: set = set()
            for sector_data in sectors.values():
                for s in sector_data.get("stocks", []):
                    sym = s.get("symbol", "")
                    if not sym or sym in seen:
                        continue
                    seen.add(sym)
                    try:
                        last = float(s.get("last") or 0)
                    except (TypeError, ValueError):
                        last = 0.0
                    if last <= 0:
                        continue
                    try:
                        near_h = float(s.get("near_52h") or 999)
                    except (TypeError, ValueError):
                        near_h = 999.0
                    try:
                        pct = float(s.get("pct") or 0)
                    except (TypeError, ValueError):
                        pct = 0.0

                    hist.setdefault(sym, []).append({
                        "date": day,
                        "last": last,
                        "near_52h": near_h,
                        "pct": pct,
                    })
        return hist

    @staticmethod
    def _build_sector_history(daily: List[Tuple[datetime.date, Dict]]) -> Dict[str, List[float]]:
        """Build sector index % history from daily snapshots."""
        hist: Dict[str, List[float]] = {}
        for _, data in daily:
            sectors = data.get("sectors") or {}
            for sec_name, sec_data in sectors.items():
                try:
                    pct = float(sec_data.get("index_pct") or 0)
                except (TypeError, ValueError):
                    pct = 0.0
                hist.setdefault(sec_name, []).append(pct)
        return hist

    @staticmethod
    def _build_fii_dii_history(daily: List[Tuple[datetime.date, Dict]]) -> List[Dict]:
        """Build daily FII/DII net history from snapshots."""
        series: List[Dict] = []
        for day, data in daily:
            fd = data.get("fii_dii") or {}
            fii = (fd.get("fii") or {}).get("net", 0) or 0
            dii = (fd.get("dii") or {}).get("net", 0) or 0
            try:
                fii_val = float(fii)
            except (TypeError, ValueError):
                fii_val = 0.0
            try:
                dii_val = float(dii)
            except (TypeError, ValueError):
                dii_val = 0.0
            series.append({"date": day, "fii": fii_val, "dii": dii_val})
        return series

    @staticmethod
    def _compute_momentum_support_resistance(stock_hist: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """Compute 5-day momentum and 10-day support/resistance levels."""
        points: List[Dict] = []
        for sym, series in stock_hist.items():
            if len(series) < 5:
                continue
            prices = [x.get("last", 0) for x in series if x.get("last", 0) > 0]
            if len(prices) < 5:
                continue

            latest = prices[-1]
            base_5d = prices[-5]
            if latest <= 0 or base_5d <= 0:
                continue

            mom5 = (latest / base_5d - 1.0) * 100.0
            mom10 = None
            if len(prices) >= 10 and prices[-10] > 0:
                mom10 = (latest / prices[-10] - 1.0) * 100.0

            win = prices[-10:] if len(prices) >= 10 else prices
            support = min(win)
            resistance = max(win)
            dist_to_res = ((resistance - latest) / latest * 100.0) if latest > 0 else 0.0
            dist_to_sup = ((latest - support) / latest * 100.0) if latest > 0 else 0.0

            points.append({
                "symbol": sym,
                "ltp": round(latest, 2),
                "mom_5d": round(mom5, 2),
                "mom_10d": round(mom10, 2) if mom10 is not None else None,
                "support": round(support, 2),
                "resistance": round(resistance, 2),
                "dist_to_res": round(dist_to_res, 2),
                "dist_to_sup": round(dist_to_sup, 2),
            })

        if not points:
            return {"leaders": [], "laggards": []}

        leaders = sorted(points, key=lambda x: x["mom_5d"], reverse=True)[:5]
        laggards = sorted(points, key=lambda x: x["mom_5d"])[:5]
        return {"leaders": leaders, "laggards": laggards}

    @staticmethod
    def _compute_sector_rotation_consistency(sector_hist: Dict[str, List[float]]) -> Dict[str, List[Dict]]:
        """Detect sectors consistently gaining/losing over recent 5 sessions."""
        gaining: List[Dict] = []
        losing: List[Dict] = []

        for sec, vals in sector_hist.items():
            if len(vals) < 3:
                continue
            recent = vals[-5:] if len(vals) >= 5 else vals
            up_days = sum(1 for v in recent if v > 0)
            down_days = sum(1 for v in recent if v < 0)
            avg = statistics.mean(recent)

            streak = 0
            sign = 0
            for v in reversed(recent):
                cur = 1 if v > 0 else (-1 if v < 0 else 0)
                if sign == 0 and cur != 0:
                    sign = cur
                if cur == sign and cur != 0:
                    streak += 1
                else:
                    break

            row = {
                "sector": sec.replace("NIFTY ", ""),
                "avg_5d": round(avg, 2),
                "up_days": up_days,
                "down_days": down_days,
                "streak": streak if sign != 0 else 0,
                "streak_dir": "UP" if sign > 0 else ("DOWN" if sign < 0 else "FLAT"),
            }

            if up_days >= 3 and avg > 0.2:
                gaining.append(row)
            if down_days >= 3 and avg < -0.2:
                losing.append(row)

        gaining.sort(key=lambda x: x["avg_5d"], reverse=True)
        losing.sort(key=lambda x: x["avg_5d"])
        return {"gaining": gaining[:6], "losing": losing[:6]}

    @staticmethod
    def _compute_breakout_persistence(stock_hist: Dict[str, List[Dict]]) -> List[Dict]:
        """Track stocks staying near 52W high for 3+ consecutive days."""
        out: List[Dict] = []
        threshold = config.NEAR_52W_HIGH_PCT

        for sym, series in stock_hist.items():
            if len(series) < 3:
                continue
            recent = series[-5:] if len(series) >= 5 else series
            streak = 0
            for row in reversed(recent):
                near_h = row.get("near_52h", 999)
                if isinstance(near_h, (int, float)) and near_h <= threshold:
                    streak += 1
                else:
                    break
            if streak >= 3:
                last = recent[-1]
                out.append({
                    "symbol": sym,
                    "days": streak,
                    "near_52h": round(float(last.get("near_52h", 999) or 999), 2),
                    "ltp": round(float(last.get("last", 0) or 0), 2),
                    "pct": round(float(last.get("pct", 0) or 0), 2),
                })

        out.sort(key=lambda x: (-x["days"], x["near_52h"]))
        return out[:10]

    @staticmethod
    def _compute_fii_dii_rolling_signal(fii_hist: List[Dict]) -> Dict:
        """Compute 5-day rolling FII/DII trend and directional market bias."""
        if len(fii_hist) < 3:
            return {
                "prediction": "UNKNOWN",
                "score": 0,
                "avg_fii_5d": 0.0,
                "avg_dii_5d": 0.0,
                "fii_trend_5d": 0.0,
                "dii_trend_5d": 0.0,
                "series": [],
                "note": "Not enough FII/DII history",
            }

        recent = fii_hist[-5:] if len(fii_hist) >= 5 else fii_hist
        avg_fii = statistics.mean([x["fii"] for x in recent])
        avg_dii = statistics.mean([x["dii"] for x in recent])
        fii_trend = recent[-1]["fii"] - recent[0]["fii"]
        dii_trend = recent[-1]["dii"] - recent[0]["dii"]

        score = 0
        if avg_fii > 0:
            score += 2
        elif avg_fii < 0:
            score -= 2

        if avg_dii > 0:
            score += 1
        elif avg_dii < 0:
            score -= 1

        if fii_trend > 500:
            score += 1
        elif fii_trend < -500:
            score -= 1

        if score >= 3:
            pred = "BULLISH"
            note = "FII + DII support trend continuation"
        elif score >= 1:
            pred = "MILD BULLISH"
            note = "Domestic/foreign flows moderately supportive"
        elif score <= -3:
            pred = "BEARISH"
            note = "Sustained selling pressure in institutional flows"
        elif score <= -1:
            pred = "MILD BEARISH"
            note = "Flow headwinds, selective weakness likely"
        else:
            pred = "SIDEWAYS"
            note = "Mixed institutional flows, range-bound bias"

        # Magnitude override: heavy absolute FII flow dominates direction
        # even when trend-direction partially offsets the score.
        if avg_fii <= -2000 and pred in ("SIDEWAYS", "MILD BULLISH"):
            pred = "MILD BEARISH"
            note = f"Heavy FII net outflow (avg ₹{avg_fii:,.0f}Cr) overrides neutral trend"
        elif avg_fii >= 2000 and pred in ("SIDEWAYS", "MILD BEARISH"):
            pred = "MILD BULLISH"
            note = f"Heavy FII net inflow (avg ₹{avg_fii:,.0f}Cr) overrides neutral trend"

        return {
            "prediction": pred,
            "score": score,
            "avg_fii_5d": round(avg_fii, 2),
            "avg_dii_5d": round(avg_dii, 2),
            "fii_trend_5d": round(fii_trend, 2),
            "dii_trend_5d": round(dii_trend, 2),
            "series": [
                {
                    "date": x["date"].strftime("%d-%b") if hasattr(x.get("date"), "strftime") else str(x.get("date", "")),
                    "fii": round(float(x["fii"]), 2),
                    "dii": round(float(x["dii"]), 2),
                }
                for x in recent
            ],
            "note": note,
        }

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

        # Historical profiles per symbol (from stored snapshots)
        # trend: based on last 7 snapshots, avg_vol_5d: last 5 snapshots
        profiles = self._build_historical_profiles(data_dir) if data_dir else {}
        quality_lookup = snapshot.get("quality_lookup") or {}

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

                # Inject PE/delivery from bounded quote lookup when sector rows miss them.
                enriched_stock = dict(stock)
                q = quality_lookup.get(sym) or {}
                if (not enriched_stock.get("pe")) and q.get("pe"):
                    enriched_stock["pe"] = q.get("pe", 0)
                if (not enriched_stock.get("delivery_pct")) and q.get("delivery_pct"):
                    enriched_stock["delivery_pct"] = q.get("delivery_pct", 0)

                p = profiles.get(sym, {})
                scored = self._score_and_classify(
                    enriched_stock,
                    sector_name,
                    median_vol,
                    fii_score,
                    p.get("trend", "SIDEWAYS"),
                    p.get("avg_vol_5d", 0.0),
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
    def _build_historical_profiles(
        data_dir: str,
        trend_lookback: int = 7,
        vol_lookback: int = 5,
    ) -> Dict[str, Dict]:
        """
        Build per-symbol historical profile from stored snapshots.

        Returns:
          {
            "SBIN": {"trend": "UPTREND", "avg_vol_5d": 1234567.0},
            ...
          }

        Trend uses last 7 unique trading days (or fewer if unavailable).
        Avg volume uses last 5 unique trading days.
        Uses one latest snapshot per day to avoid inflating same-day data
        when multiple intraday snapshots exist for the same trading day.
        """
        snap_dir = Path(data_dir) / "snapshots"
        profiles: Dict[str, Dict] = {}
        max_lookback = max(trend_lookback, vol_lookback)

        # Deduplicate: keep only the latest snapshot per calendar day
        name_rx = re.compile(r"snapshot_(\d{8})_(\d{6})\.json$")
        latest_by_day: Dict[str, Path] = {}
        for sf in snap_dir.glob("snapshot_*.json"):
            m = name_rx.match(sf.name)
            if not m:
                continue
            day_str = m.group(1)
            existing = latest_by_day.get(day_str)
            if existing is None or sf.name > existing.name:
                latest_by_day[day_str] = sf

        # Sort days descending (most recent first) and cap at max_lookback days
        sorted_days = sorted(latest_by_day.keys(), reverse=True)[:max_lookback]
        daily_files = [latest_by_day[d] for d in sorted_days]

        # Collect price series per symbol (index 0 = most recent day)
        price_series: Dict[str, List[float]] = {}
        vol_series: Dict[str, List[float]] = {}
        for sf in daily_files:
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                for sector_data in data.get("sectors", {}).values():
                    for stock in sector_data.get("stocks", []):
                        sym = stock.get("symbol", "")
                        ltp = stock.get("last", 0)
                        if sym and ltp > 0:
                            price_series.setdefault(sym, []).append(ltp)
                        vol = stock.get("volume", 0) or 0
                        if sym and vol > 0:
                            vol_series.setdefault(sym, []).append(float(vol))
            except Exception:
                continue

        all_syms = set(price_series.keys()) | set(vol_series.keys())
        for sym in all_syms:
            prices = (price_series.get(sym) or [])[:trend_lookback]
            vols = (vol_series.get(sym) or [])[:vol_lookback]

            if len(prices) < 3:
                trend = "SIDEWAYS"
            else:
                # prices[0] = most recent, prices[-1] = oldest
                ups = sum(1 for i in range(len(prices) - 1) if prices[i] > prices[i + 1])
                downs = sum(1 for i in range(len(prices) - 1) if prices[i] < prices[i + 1])
                total = len(prices) - 1
                if total > 0 and ups / total >= 0.6:
                    trend = "UPTREND"
                elif total > 0 and downs / total >= 0.6:
                    trend = "DOWNTREND"
                else:
                    trend = "SIDEWAYS"

            avg_vol_5d = statistics.mean(vols) if vols else 0.0
            profiles[sym] = {
                "trend": trend,
                "avg_vol_5d": avg_vol_5d,
            }

        return profiles

    def _score_and_classify(
        self,
        stock: Dict,
        sector_name: str,
        median_vol: float,
        fii_score: float,
        trend: str,
        avg_vol_5d: float,
    ) -> Optional[Dict]:
        """
        Score a stock 0-100 and assign a trade category.

                Score breakdown:
                    Today momentum   0-20 pts   (pct)
                    30-day trend     0-15 pts   (chg_30d)
                    52W position     0-20 pts   (near_52h / near_52l)
                    Volume ratio     0-20 pts   (today vs stock 5d avg, fallback sector median)
                    Quality          0-15 pts   (PE + delivery%)
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
        pe = stock.get("pe", 0) or 0
        delivery_pct = stock.get("delivery_pct", 0) or 0

        if not sym or ltp <= 0:
            return None

        # 1. Today momentum (0-20)
        s_mom = max(0.0, min(20.0, (pct + 10.0) / 20.0 * 20.0))

        # 2. 30-day trend (0-15)
        s_30d = max(0.0, min(15.0, (chg30 + 20.0) / 40.0 * 15.0))

        # 3. 52W position (0-20)
        #    near_52h: % below 52W high (0 = AT 52W high → breakout zone)
        #    near_52l: % above 52W low  (0 = AT 52W low  → deep value)
        if near_h <= 3 and pct > 0:
            s_52w = 20.0          # breakout momentum
        elif near_h <= 8 and pct > 0:
            s_52w = 15.0          # approaching breakout
        elif near_l <= 5:
            s_52w = 16.0          # deep value zone
        elif near_l <= 15:
            s_52w = 12.0          # value zone
        else:
            s_52w = max(0.0, 8.0 - near_h * 0.15)  # general mid-range

        # 4. Volume ratio (0-20)
        #    Primary baseline: stock's own 5-day average volume.
        #    Fallback baseline: sector median volume.
        vol_base = avg_vol_5d if avg_vol_5d > 0 else median_vol
        vol_ratio = (volume / vol_base) if vol_base > 0 else 1.0
        s_vol = min(20.0, vol_ratio * 8.0)

        # 5. Quality score (0-15): PE + delivery%
        try:
            pe_val = float(pe)
        except (TypeError, ValueError):
            pe_val = 0.0

        if pe_val <= 0:
            s_pe = 4.0  # unknown PE -> neutral
        elif 5 <= pe_val <= 25:
            s_pe = 8.0
        elif pe_val <= 40:
            s_pe = 6.0
        else:
            s_pe = 3.0

        try:
            deliv_val = float(delivery_pct)
        except (TypeError, ValueError):
            deliv_val = 0.0

        if deliv_val <= 0:
            s_del = 4.0  # unknown delivery -> neutral
        elif deliv_val >= config.HIGH_DELIVERY_PCT:
            s_del = 7.0
        elif deliv_val >= 35:
            s_del = 5.0
        else:
            s_del = 2.0

        s_quality = min(15.0, s_pe + s_del)

        # 6. FII sentiment (0-10) — already 0-10
        s_fii = fii_score

        # Historical trend bonus / penalty
        if trend == "UPTREND":
            s_trend = 8.0
        elif trend == "DOWNTREND":
            s_trend = -8.0
        else:
            s_trend = 0.0

        raw_score = s_mom + s_30d + s_52w + s_vol + s_quality + s_fii + s_trend
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
            if avg_vol_5d > 0:
                reasons.append(f"Volume {vol_ratio:.1f}× 5-day avg — institutional interest")
            else:
                reasons.append(f"Volume {vol_ratio:.1f}× sector avg — institutional interest")
        if volume_spike:
            reasons.append(f"⚡ Volume spike {vol_ratio:.1f}× — possible breakout")
        if pe_val > 0 and pe_val <= 25:
            reasons.append(f"Healthy PE {pe_val:.1f}")
        elif pe_val > 40:
            reasons.append(f"High PE {pe_val:.1f} — valuation risk")
        if deliv_val > 0:
            reasons.append(f"Delivery {deliv_val:.0f}%")
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
            "pe":           round(pe_val, 2) if pe_val > 0 else 0,
            "delivery_pct": round(deliv_val, 2) if deliv_val > 0 else 0,
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

    # ── Phase 4 Accuracy Tracking ─────────────────────────────────────────

    @staticmethod
    def log_phase4_picks(picks: List[Dict], data_dir: str) -> None:
        """Persist today's Phase 4 top picks for next-session accuracy scoring.

        Writes data/trading/phase4_picks/YYYYMMDD.json with entry prices so
        tomorrow's run can compute realised P&L and hit-rate.
        """
        if not picks or not data_dir:
            return
        picks_dir = Path(data_dir) / "trading" / "phase4_picks"
        picks_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        out = [
            {
                "symbol":           p.get("symbol", ""),
                "entry_price":      float(p.get("ltp", 0) or 0),
                "score":            float(p.get("score", 0) or 0),
                "five_day_return":  float(p.get("five_day_return", 0) or 0),
                "entry_date":       today,
            }
            for p in picks
            if p.get("symbol") and (p.get("ltp", 0) or 0) > 0
        ]
        if not out:
            return
        path = picks_dir / f"{today}.json"
        try:
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Phase 4 picks logged ({today}): {[x['symbol'] for x in out]}")
        except Exception as e:
            logger.warning(f"Phase 4 picks log failed: {e}")

    @staticmethod
    def compute_phase4_accuracy(snapshot: Dict, data_dir: str) -> Dict:
        """Compare previously logged Phase 4 picks against today's closing prices.

        Returns a rolling 5-session accuracy summary:
          {
            "session_results":  [{date, symbol, entry_price, current_price, pct_chg, hit}],
            "rolling_hit_rate": 66.7,   # % over (hits + misses); None when < 3 data points
            "hits":             4,
            "misses":           2,
            "sessions_tracked": 3,
          }
        A pick is a *hit* when it gains ≥ +0.5% from entry; a *miss* when it falls ≤ -0.5%.
        Neutral (±0.5%) picks are excluded from the rate calculation.
        """
        if not data_dir:
            return {}
        picks_dir = Path(data_dir) / "trading" / "phase4_picks"
        if not picks_dir.exists():
            return {}

        # Build current-price lookup from today's snapshot sectors
        price_lookup: Dict[str, float] = {}
        for sec_data in (snapshot.get("sectors") or {}).values():
            for s in sec_data.get("stocks", []):
                sym = s.get("symbol", "")
                ltp = s.get("last", 0) or 0
                if sym and ltp > 0:
                    price_lookup[sym] = float(ltp)

        if not price_lookup:
            return {}

        # Load the last 5 pick files, excluding today (today's result not known yet)
        today = datetime.now().strftime("%Y%m%d")
        pick_files = sorted(
            [p for p in picks_dir.glob("*.json") if p.stem != today],
            reverse=True,
        )[:5]

        if not pick_files:
            return {}

        session_results: List[Dict] = []
        hits = misses = 0

        for pf in pick_files:
            try:
                saved = json.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                continue
            for entry in saved:
                sym = entry.get("symbol", "")
                entry_price = float(entry.get("entry_price", 0) or 0)
                cur_price = price_lookup.get(sym, 0)
                if not sym or entry_price <= 0 or cur_price <= 0:
                    continue
                pct_chg = round((cur_price - entry_price) / entry_price * 100, 2)
                if pct_chg >= 0.5:
                    hit: Optional[bool] = True
                    hits += 1
                elif pct_chg <= -0.5:
                    hit = False
                    misses += 1
                else:
                    hit = None  # neutral — not counted
                session_results.append({
                    "date":          pf.stem,
                    "symbol":        sym,
                    "entry_price":   entry_price,
                    "current_price": cur_price,
                    "pct_chg":       pct_chg,
                    "hit":           hit,
                })

        total = hits + misses
        hit_rate = round(hits / total * 100, 1) if total >= 3 else None

        return {
            "session_results":  session_results,
            "rolling_hit_rate": hit_rate,
            "hits":             hits,
            "misses":           misses,
            "sessions_tracked": len(pick_files),
        }


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
