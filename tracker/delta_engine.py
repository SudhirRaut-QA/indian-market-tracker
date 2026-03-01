"""
Delta Engine v3.0 - Snapshot Comparison & Intelligence
========================================================

Detects:
- FII/DII flow reversals (buying ↔ selling)
- Index level changes between snapshots
- Stock price/volume deltas across sectors
- Sector rotation (money flowing between sectors)
- 52-week proximity alerts (breakout/value picks)
- Currency impact explanations
- Pattern recognition (FII/DII multi-day trends)
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from . import config

logger = logging.getLogger(__name__)


def _safe_pct(old: float, new: float) -> float:
    if old == 0:
        return 0 if new == 0 else 100.0
    return round((new - old) / abs(old) * 100, 2)


def _classify_change(pct: float) -> str:
    if pct >= 3:
        return "🚀 Big Jump"
    elif pct >= 1:
        return "📈 Up"
    elif pct >= 0.1:
        return "↗️ Slightly Up"
    elif pct > -0.1:
        return "➡️ Flat"
    elif pct > -1:
        return "↘️ Slightly Down"
    elif pct > -3:
        return "📉 Down"
    else:
        return "💥 Big Drop"


def _flow_direction(net: float) -> str:
    if net > 500:
        return "Heavy Buying"
    elif net > 0:
        return "Buying"
    elif net > -500:
        return "Selling"
    else:
        return "Heavy Selling"


class DeltaEngine:
    """Computes differences between market snapshots with intelligence."""

    def __init__(self, delta_dir: str = None):
        self.delta_dir = delta_dir or str(config.SNAPSHOT_DIR)
        os.makedirs(self.delta_dir, exist_ok=True)

    def _snapshot_path(self) -> str:
        return os.path.join(self.delta_dir, "last_snapshot.json")

    def load_previous(self) -> Optional[Dict]:
        path = self._snapshot_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Load prev snapshot: {e}")
            return None

    def save_current(self, snapshot: Dict):
        path = self._snapshot_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"Snapshot saved: {path}")
        except Exception as e:
            logger.error(f"Save snapshot: {e}")

    def compute_delta(self, previous: Dict, current: Dict) -> Dict:
        delta = {
            "timestamp": datetime.now().isoformat(),
            "prev_time": previous.get("timestamp", ""),
            "curr_time": current.get("timestamp", ""),
            "fii_dii": self._delta_fii_dii(
                previous.get("fii_dii"), current.get("fii_dii")
            ),
            "indices": self._delta_indices(
                previous.get("indices"), current.get("indices")
            ),
            "sectors": self._delta_sectors(
                previous.get("sectors", {}), current.get("sectors", {})
            ),
            "commodities": self._delta_commodities(
                previous.get("commodities", {}), current.get("commodities", {})
            ),
            "forex": self._delta_forex(
                previous.get("forex"), current.get("forex")
            ),
            "sector_rotation": self._detect_sector_rotation(
                previous.get("sectors", {}), current.get("sectors", {})
            ),
            "market_context": self._generate_context(previous, current),
        }
        return delta

    # ── FII/DII Delta ───────────────────────────────────────────────────────

    def _delta_fii_dii(self, prev: Optional[Dict], curr: Optional[Dict]) -> Optional[Dict]:
        if not prev or not curr:
            return None

        fii_prev = prev.get("fii", {})
        fii_curr = curr.get("fii", {})
        dii_prev = prev.get("dii", {})
        dii_curr = curr.get("dii", {})

        fii_net_prev = fii_prev.get("net", 0)
        fii_net_curr = fii_curr.get("net", 0)
        dii_net_prev = dii_prev.get("net", 0)
        dii_net_curr = dii_curr.get("net", 0)

        # Detect flow reversals
        fii_reversal = None
        if fii_net_prev > 0 and fii_net_curr < 0:
            fii_reversal = "🔄 FII flipped: Was BUYING → Now SELLING"
        elif fii_net_prev < 0 and fii_net_curr > 0:
            fii_reversal = "🔄 FII flipped: Was SELLING → Now BUYING"

        dii_reversal = None
        if dii_net_prev > 0 and dii_net_curr < 0:
            dii_reversal = "🔄 DII flipped: Was BUYING → Now SELLING"
        elif dii_net_prev < 0 and dii_net_curr > 0:
            dii_reversal = "🔄 DII flipped: Was SELLING → Now BUYING"

        return {
            "fii_net_prev": fii_net_prev,
            "fii_net_curr": fii_net_curr,
            "fii_net_change": round(fii_net_curr - fii_net_prev, 2),
            "fii_direction_prev": _flow_direction(fii_net_prev),
            "fii_direction_curr": _flow_direction(fii_net_curr),
            "fii_reversal": fii_reversal,
            "dii_net_prev": dii_net_prev,
            "dii_net_curr": dii_net_curr,
            "dii_net_change": round(dii_net_curr - dii_net_prev, 2),
            "dii_direction_prev": _flow_direction(dii_net_prev),
            "dii_direction_curr": _flow_direction(dii_net_curr),
            "dii_reversal": dii_reversal,
            "signal_prev": prev.get("signal", ""),
            "signal_curr": curr.get("signal", ""),
        }

    # ── Index Delta ──────────────────────────────────────────────────────────

    def _delta_indices(self, prev: Optional[Dict], curr: Optional[Dict]) -> Optional[Dict]:
        if not prev or not curr:
            return None

        changes = {}
        for name in curr:
            if name not in prev:
                continue
            p, c = prev[name], curr[name]
            p_last = p.get("last", 0)
            c_last = c.get("last", 0)
            abs_chg = round(c_last - p_last, 2)
            pct_chg = _safe_pct(p_last, c_last)

            # Breadth ratio
            try:
                adv = int(c.get("advances", 0) or 0)
                dec = int(c.get("declines", 0) or 0)
            except (ValueError, TypeError):
                adv, dec = 0, 0
            breadth = round(adv / dec, 2) if dec > 0 else 0

            changes[name] = {
                "prev_last": p_last,
                "curr_last": c_last,
                "abs_change": abs_chg,
                "pct_change": pct_chg,
                "signal": _classify_change(pct_chg),
                "curr_pct_today": c.get("pct", 0),
                "breadth_ratio": breadth,
            }

        if changes:
            top_gain = max(changes.items(), key=lambda x: x[1]["pct_change"])
            top_lose = min(changes.items(), key=lambda x: x[1]["pct_change"])
            return {
                "changes": changes,
                "best": {"name": top_gain[0], **top_gain[1]},
                "worst": {"name": top_lose[0], **top_lose[1]},
            }
        return None

    # ── Sector Delta ─────────────────────────────────────────────────────────

    def _delta_sectors(self, prev: Dict, curr: Dict) -> Dict:
        deltas = {}
        for name in curr:
            if name not in prev:
                continue
            p = prev[name]
            c = curr[name]

            idx_chg = _safe_pct(
                p.get("index_last", 0),
                c.get("index_last", 0),
            )

            # Stock-level comparison
            p_stocks = {s["symbol"]: s for s in p.get("stocks", [])}
            c_stocks = {s["symbol"]: s for s in c.get("stocks", [])}

            movers = []
            for sym in c_stocks:
                if sym in p_stocks:
                    ps = p_stocks[sym]
                    cs = c_stocks[sym]
                    price_chg = _safe_pct(ps.get("last", 0), cs.get("last", 0))
                    vol_chg = _safe_pct(ps.get("volume", 0), cs.get("volume", 0))
                    if abs(price_chg) >= 1.0 or abs(vol_chg) >= 50:
                        movers.append({
                            "symbol": sym,
                            "price_prev": ps.get("last", 0),
                            "price_curr": cs.get("last", 0),
                            "price_chg_pct": price_chg,
                            "vol_prev": ps.get("volume", 0),
                            "vol_curr": cs.get("volume", 0),
                            "vol_chg_pct": vol_chg,
                            "signal": _classify_change(price_chg),
                        })

            movers.sort(key=lambda x: abs(x["price_chg_pct"]), reverse=True)

            deltas[name] = {
                "index_chg_pct": idx_chg,
                "index_signal": _classify_change(idx_chg),
                "movers": movers[:10],
                "movers_count": len(movers),
            }
        return deltas

    # ── Sector Rotation Detection ────────────────────────────────────────────

    def _detect_sector_rotation(self, prev: Dict, curr: Dict) -> Optional[Dict]:
        """Detect money flowing between sectors."""
        if not prev or not curr:
            return None

        prev_perf = {}
        curr_perf = {}

        for name in set(list(prev.keys()) + list(curr.keys())):
            if name in prev:
                prev_perf[name] = prev[name].get("index_pct", 0)
            if name in curr:
                curr_perf[name] = curr[name].get("index_pct", 0)

        if len(prev_perf) < 3 or len(curr_perf) < 3:
            return None

        # Sort by performance
        prev_sorted = sorted(prev_perf.items(), key=lambda x: x[1], reverse=True)
        curr_sorted = sorted(curr_perf.items(), key=lambda x: x[1], reverse=True)

        # Find rotation: previous worst → current best
        rotations = []
        prev_bottom = [name for name, _ in prev_sorted[-3:]]  # Worst 3 prev
        curr_top = [name for name, _ in curr_sorted[:3]]  # Best 3 curr

        for sector in prev_bottom:
            if sector in curr_top:
                rotations.append({
                    "sector": sector,
                    "prev_rank": next(
                        i for i, (n, _) in enumerate(prev_sorted) if n == sector
                    ) + 1,
                    "curr_rank": next(
                        i for i, (n, _) in enumerate(curr_sorted) if n == sector
                    ) + 1,
                    "prev_pct": prev_perf.get(sector, 0),
                    "curr_pct": curr_perf.get(sector, 0),
                    "signal": "🔄 Money flowing IN",
                })

        prev_top = [name for name, _ in prev_sorted[:3]]  # Best 3 prev
        curr_bottom = [name for name, _ in curr_sorted[-3:]]  # Worst 3 curr

        for sector in prev_top:
            if sector in curr_bottom:
                rotations.append({
                    "sector": sector,
                    "prev_rank": next(
                        i for i, (n, _) in enumerate(prev_sorted) if n == sector
                    ) + 1,
                    "curr_rank": next(
                        i for i, (n, _) in enumerate(curr_sorted) if n == sector
                    ) + 1,
                    "prev_pct": prev_perf.get(sector, 0),
                    "curr_pct": curr_perf.get(sector, 0),
                    "signal": "🔄 Money flowing OUT",
                })

        if not rotations:
            return None

        return {
            "rotations": rotations,
            "prev_best": prev_sorted[0][0] if prev_sorted else "",
            "curr_best": curr_sorted[0][0] if curr_sorted else "",
            "prev_worst": prev_sorted[-1][0] if prev_sorted else "",
            "curr_worst": curr_sorted[-1][0] if curr_sorted else "",
        }

    # ── Market Context / Explainer ───────────────────────────────────────────

    def _generate_context(self, previous: Dict, current: Dict) -> List[str]:
        """Generate 'why is this happening?' explanations."""
        insights = []

        curr_indices = current.get("indices", {})
        curr_sectors = current.get("sectors", {})
        curr_fii = current.get("fii_dii", {})
        curr_forex = current.get("forex", {})
        prev_forex = previous.get("forex", {})

        # VIX spike = fear
        vix = curr_indices.get("INDIA VIX", {})
        nifty = curr_indices.get("NIFTY 50", {})
        if vix.get("pct", 0) > 5 and nifty.get("pct", 0) < 0:
            insights.append(
                "⚠️ VIX spiked + NIFTY down = Fear rising, "
                "traders buying protection (put options)"
            )
        elif vix.get("pct", 0) < -5 and nifty.get("pct", 0) > 0:
            insights.append(
                "✅ VIX dropped + NIFTY up = Fear subsiding, "
                "confidence returning"
            )

        # Defensive rotation: Pharma/FMCG up while market down
        pharma_pct = curr_sectors.get("NIFTY PHARMA", {}).get("index_pct", 0)
        fmcg_pct = curr_sectors.get("NIFTY FMCG", {}).get("index_pct", 0)
        nifty_pct = nifty.get("pct", 0)
        if (pharma_pct > 0.5 or fmcg_pct > 0.5) and nifty_pct < -0.5:
            insights.append(
                "🛡️ Defensive rotation detected: Pharma/FMCG UP "
                "while market DOWN (money moving to safe sectors)"
            )

        # Bank vs IT rotation
        bank_pct = curr_sectors.get("NIFTY BANK", {}).get("index_pct", 0)
        it_pct = curr_sectors.get("NIFTY IT", {}).get("index_pct", 0)
        if bank_pct < -1 and it_pct > 1:
            insights.append(
                "🔄 Sector rotation: Banks DOWN → IT UP "
                "(often linked to rupee weakening)"
            )
        elif bank_pct > 1 and it_pct < -1:
            insights.append(
                "🔄 Sector rotation: IT DOWN → Banks UP "
                "(often linked to rupee strengthening)"
            )

        # Currency impact
        usdinr_curr = curr_forex.get("usdinr", 0)
        usdinr_prev = prev_forex.get("usdinr", 0)
        if usdinr_curr and usdinr_prev:
            fx_change = usdinr_curr - usdinr_prev
            if fx_change > 0.3:
                insights.append(
                    f"💱 ₹ weakened by {fx_change:.2f} → "
                    "Good for IT exports (TCS, Infy), "
                    "bad for oil importers"
                )
            elif fx_change < -0.3:
                insights.append(
                    f"💱 ₹ strengthened by {abs(fx_change):.2f} → "
                    "Bad for IT exports, "
                    "good for oil imports & inflation"
                )

        # FII selling + metal/energy up = commodity play
        fii_net = curr_fii.get("fii", {}).get("net", 0)
        metal_pct = curr_sectors.get("NIFTY METAL", {}).get("index_pct", 0)
        energy_pct = curr_sectors.get("NIFTY ENERGY", {}).get("index_pct", 0)
        if fii_net < -500 and (metal_pct > 1 or energy_pct > 1):
            insights.append(
                "🏭 FII selling but Metals/Energy UP = "
                "Commodity cycle play (global demand)"
            )

        # Strong breadth
        try:
            adv = int(nifty.get("advances", 0) or 0)
            dec = int(nifty.get("declines", 0) or 0)
        except (ValueError, TypeError):
            adv, dec = 0, 0
        if dec > 0:
            breadth = adv / dec
            if breadth > 3:
                insights.append(
                    f"📊 Very strong breadth ({adv} advances vs {dec} declines) "
                    "= broad-based buying"
                )
            elif breadth < 0.3:
                insights.append(
                    f"📊 Very weak breadth ({adv} advances vs {dec} declines) "
                    "= broad-based selling"
                )

        return insights

    # ── Commodity Delta ──────────────────────────────────────────────────────

    def _delta_commodities(self, prev: Dict, curr: Dict) -> Dict:
        deltas = {}
        for symbol in curr:
            if symbol not in prev:
                continue
            p_last = prev[symbol].get("last", 0)
            c_last = curr[symbol].get("last", 0)
            pct = _safe_pct(p_last, c_last)
            deltas[symbol] = {
                "prev": p_last, "curr": c_last,
                "pct": pct, "signal": _classify_change(pct),
            }
        return deltas

    # ── Forex Delta ──────────────────────────────────────────────────────────

    def _delta_forex(self, prev: Optional[Dict], curr: Optional[Dict]) -> Optional[Dict]:
        if not prev or not curr:
            return None
        p_rate = prev.get("usdinr", 0)
        c_rate = curr.get("usdinr", 0)
        chg = round(c_rate - p_rate, 4)
        return {
            "prev": p_rate, "curr": c_rate,
            "change": chg,
            "direction": (
                "₹ Weakened" if chg > 0
                else "₹ Strengthened" if chg < 0
                else "Unchanged"
            ),
        }

    # ── Full Delta Pipeline ──────────────────────────────────────────────────

    def process(self, current_snapshot: Dict) -> Tuple[Optional[Dict], bool]:
        """
        Load previous snapshot, compute delta, save current as new previous.
        Returns: (delta_dict or None, is_first_run: bool)
        """
        previous = self.load_previous()
        self.save_current(current_snapshot)

        if not previous:
            logger.info("First run — no previous snapshot for delta")
            return None, True

        delta = self.compute_delta(previous, current_snapshot)
        return delta, False
