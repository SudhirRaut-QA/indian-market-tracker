"""
Delta Engine - Snapshot Comparison & Change Tracking
=====================================================

Compares current snapshot vs previous snapshot to detect:
- FII/DII flow reversals (was buying → now selling)
- Index level changes between snapshots
- Stock price/volume deltas
- Position changes (new entries, exits)
- Insider trading changes
- Corporate action alerts

Output is a "delta report" with kid-friendly signals.
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
    """Computes differences between market snapshots."""

    def __init__(self, delta_dir: str = None):
        self.delta_dir = delta_dir or config.SNAPSHOT_DIR
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
            "fii_dii": self._delta_fii_dii(previous.get("fii_dii"), current.get("fii_dii")),
            "indices": self._delta_indices(previous.get("indices"), current.get("indices")),
            "sectors": self._delta_sectors(previous.get("sectors", {}), current.get("sectors", {})),
            "commodities": self._delta_commodities(previous.get("commodities", {}), current.get("commodities", {})),
            "forex": self._delta_forex(previous.get("forex"), current.get("forex")),
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
            changes[name] = {
                "prev_last": p_last,
                "curr_last": c_last,
                "abs_change": abs_chg,
                "pct_change": pct_chg,
                "signal": _classify_change(pct_chg),
                "curr_pct_today": c.get("pct", 0),
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
            "direction": "₹ Weakened" if chg > 0 else "₹ Strengthened" if chg < 0 else "Unchanged",
        }

    # ── Convenience: Full Delta Pipeline ─────────────────────────────────────

    def process(self, current_snapshot: Dict) -> Tuple[Optional[Dict], bool]:
        """
        Load previous snapshot, compute delta, save current as new previous.

        Returns:
            (delta_dict or None, is_first_run: bool)
        """
        previous = self.load_previous()
        self.save_current(current_snapshot)

        if not previous:
            logger.info("First run — no previous snapshot for delta")
            return None, True

        delta = self.compute_delta(previous, current_snapshot)
        return delta, False
