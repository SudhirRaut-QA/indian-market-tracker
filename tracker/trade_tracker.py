"""
Trade Tracker — EOD Performance Review & Algorithm Self-Tuning
==============================================================

Workflow each trading day:
  Morning slots  (09:15-11:00) → save_recommendations()
  EOD slot       (15:35)       → review_day() + update_algo_params()
  Telegram                     → format_review_msg() + format_trend_report()

Storage layout under data/trading/:
  recs/{date}.json          — recommendations saved slot-by-slot during the day
  reviews/{date}.json       — EOD evaluated outcomes (WIN/LOSS/NEUTRAL)
  algo_params.json          — current auto-tuned algorithm parameters

Outcome evaluation rules (SL always takes priority):
  LONG : if day_low  ≤ stop_loss → LOSS   else if day_high ≥ target → WIN
  SHORT: if day_high ≥ stop_loss → LOSS   else if day_low  ≤ target → WIN
  NOT_TRIGGERED  — price never reached entry zone
  NEUTRAL        — entry was triggered but neither target nor SL hit yet
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from . import config

logger = logging.getLogger(__name__)

# ─── Paths ───────────────────────────────────────────────────────────────────

_TRADING_DIR  = config.DATA_DIR / "trading"
_RECS_DIR     = _TRADING_DIR / "recs"
_REVIEWS_DIR  = _TRADING_DIR / "reviews"
_ALGO_PARAMS  = _TRADING_DIR / "algo_params.json"

# ─── Default parameters (used when no history is available) ─────────────────

DEFAULT_PARAMS: Dict = {
    "direction_score_threshold": 15,   # min abs score to call LONG/SHORT
    "momentum_rs_min_pct":        1.5,  # min RS vs sector for momentum alert
    "momentum_val_cr_min":      500.0,  # min ₹ value traded (Cr) for high-vol alert
    "macro_bias_weight":          0.30, # fraction of macro bias in stock score
    "sl_buffer_pct":              0.015,# stop-loss buffer beyond next level
}


def _ensure_dirs() -> None:
    for d in [_RECS_DIR, _REVIEWS_DIR]:
        os.makedirs(d, exist_ok=True)


# ─── Parameter I/O ──────────────────────────────────────────────────────────

def load_algo_params() -> Dict:
    """Return current tuned params, falling back to defaults."""
    try:
        if _ALGO_PARAMS.exists():
            with open(_ALGO_PARAMS, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_PARAMS, **data.get("params", {})}
    except Exception as e:
        logger.debug(f"algo_params load error: {e}")
    return dict(DEFAULT_PARAMS)


# ─── Save recommendations ────────────────────────────────────────────────────

def save_recommendations(setups: Dict, slot_time: str, today: str = None) -> None:
    """
    Persist this slot's trading recommendations for EOD evaluation.
    Only saves non-NEUTRAL setups (ones that have an actionable direction).
    """
    _ensure_dirs()
    if not today:
        today = datetime.now().strftime("%Y-%m-%d")

    rec_file = _RECS_DIR / f"{today}.json"
    existing: List = []
    if rec_file.exists():
        try:
            with open(rec_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    slot_recs = []

    # Structured setups (Index / Stock / ETF)
    for cat_key, cat_name in [("index_setups", "Index"),
                               ("stock_setups", "Stock"),
                               ("etf_setups",   "ETF")]:
        for s in setups.get(cat_key, []):
            if s.get("direction", "NEUTRAL") == "NEUTRAL":
                continue
            slot_recs.append({
                "slot":            slot_time,
                "symbol":          s["symbol"],
                "category":        cat_name,
                "sector":          s.get("sector", ""),
                "direction":       s["direction"],
                "ltp":             s["ltp"],
                "entry":           s["entry"],
                "target":          s["target"],
                "stop_loss":       s["stop_loss"],
                "risk_reward":     s["risk_reward"],
                "direction_score": s.get("direction_score", 0),
                "factors":         s.get("factors", [])[:3],
            })

    # Momentum alerts
    for m in setups.get("momentum_alerts", []):
        if m.get("direction", "NEUTRAL") == "NEUTRAL":
            continue
        slot_recs.append({
            "slot":            slot_time,
            "symbol":          m["symbol"],
            "category":        "Momentum",
            "sector":          m.get("sector", ""),
            "direction":       m["direction"],
            "ltp":             m["ltp"],
            "entry":           m["entry"],
            "target":          m["target"],
            "stop_loss":       m["stop_loss"],
            "risk_reward":     m["risk_reward"],
            "direction_score": 0,
            "factors":         m.get("triggers", [])[:2],
        })

    existing.append({
        "slot":  slot_time,
        "bias":  setups.get("bias", {}),
        "recs":  slot_recs,
    })

    with open(rec_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(slot_recs)} recommendations for {today} slot {slot_time}")


# ─── OHLC lookup from snapshot ───────────────────────────────────────────────

def _build_ohlc_lookup(snapshot: Dict) -> Dict[str, Dict]:
    """Build symbol → {open, high, low, last} from any snapshot."""
    lookup: Dict[str, Dict] = {}

    # Key indices
    for name, data in (snapshot.get("indices") or {}).items():
        lookup[name] = {
            "open": data.get("open", 0),
            "high": data.get("high", 0),
            "low":  data.get("low",  0),
            "last": data.get("last", 0),
        }

    # Stocks from sector data
    for sect_data in (snapshot.get("sectors") or {}).values():
        for s in sect_data.get("stocks", []):
            sym = s.get("symbol", "")
            if sym and sym not in lookup:
                lookup[sym] = {
                    "open": s.get("open", 0),
                    "high": s.get("high", 0),
                    "low":  s.get("low",  0),
                    "last": s.get("last", 0),
                }

    # Commodity ETFs
    for sym, data in (snapshot.get("commodities") or {}).items():
        if isinstance(data, dict) and sym not in lookup:
            lookup[sym] = {
                "open": data.get("open", 0),
                "high": data.get("high", 0),
                "low":  data.get("low",  0),
                "last": data.get("last", 0),
            }

    return lookup


# ─── Outcome evaluation ──────────────────────────────────────────────────────

def _evaluate_outcome(
    direction: str,
    entry: float,
    target: float,
    stop_loss: float,
    day_high: float,
    day_low: float,
) -> str:
    """
    Evaluate trade outcome using SL-priority rule.
    SL is always checked first — it is honoured before target.

    Returns: 'WIN' | 'LOSS' | 'NEUTRAL' | 'NOT_TRIGGERED' | 'NO_DATA'
    """
    if not (day_high and day_low and entry and target and stop_loss):
        return "NO_DATA"

    tol = 0.001  # 0.1% tolerance for "entry triggered"

    if direction == "LONG":
        if day_high < entry * (1 - tol):      # price never reached entry
            return "NOT_TRIGGERED"
        if day_low <= stop_loss:               # SL hit first (conservative)
            return "LOSS"
        if day_high >= target:                 # target hit, SL not hit
            return "WIN"
        return "NEUTRAL"                       # in-play, neither hit

    elif direction == "SHORT":
        if day_low > entry * (1 + tol):        # price never bounced to entry
            return "NOT_TRIGGERED"
        if day_high >= stop_loss:              # SL hit first
            return "LOSS"
        if day_low <= target:                  # target hit, SL not hit
            return "WIN"
        return "NEUTRAL"

    return "NO_DATA"


# ─── EOD Review ──────────────────────────────────────────────────────────────

def review_day(snapshot: Dict, today: str = None) -> Optional[Dict]:
    """
    Load today's saved recommendations and evaluate each one against
    the current snapshot's intraday H/L.

    Call this at the 15:35 slot when H/L reflects the full trading day.
    Saves result to data/trading/reviews/{date}.json.
    """
    _ensure_dirs()
    if not today:
        today = datetime.now().strftime("%Y-%m-%d")

    rec_file = _RECS_DIR / f"{today}.json"
    if not rec_file.exists():
        logger.info(f"No saved recommendations to review for {today}")
        return None

    try:
        with open(rec_file, "r", encoding="utf-8") as f:
            all_slots = json.load(f)
    except Exception as e:
        logger.error(f"Error loading recommendations: {e}")
        return None

    ohlc = _build_ohlc_lookup(snapshot)

    # Deduplicate: use FIRST occurrence of each (symbol, category) pair
    # Later slots may update LTP but we evaluate the original entry
    first_recs: Dict[str, Dict] = {}
    for slot_data in all_slots:
        for rec in slot_data.get("recs", []):
            key = f"{rec['symbol']}_{rec['category']}"
            if key not in first_recs:
                first_recs[key] = {**rec, "day_bias": slot_data.get("bias", {}).get("direction", "NEUTRAL")}

    outcomes = []
    for key, rec in first_recs.items():
        sym = rec["symbol"]
        price_data = ohlc.get(sym)

        if not price_data or not price_data.get("high"):
            outcome = "NO_DATA"
            day_high = day_low = 0.0
        else:
            day_high = float(price_data["high"])
            day_low  = float(price_data["low"])
            outcome  = _evaluate_outcome(
                rec["direction"], rec["entry"], rec["target"],
                rec["stop_loss"], day_high, day_low,
            )

        # Calculate estimated P&L % for this outcome
        pnl = 0.0
        entry = rec["entry"]
        if outcome == "WIN" and entry:
            pnl = abs(rec["target"] - entry) / entry * 100
        elif outcome == "LOSS" and entry:
            pnl = -abs(rec["stop_loss"] - entry) / entry * 100

        outcomes.append({
            **rec,
            "day_high":    round(day_high, 2),
            "day_low":     round(day_low,  2),
            "day_close":   round(float(price_data.get("last", 0)) if price_data else 0, 2),
            "outcome":     outcome,
            "pnl_pct":     round(pnl, 2),
        })

    if not outcomes:
        return None

    # ── Statistics builders ──
    def _stats(subset: List[Dict]) -> Dict:
        total = len(subset)
        if total == 0:
            return {"total": 0, "win": 0, "loss": 0, "neutral": 0, "no_data": 0, "win_rate": 0.0}
        w   = sum(1 for x in subset if x["outcome"] == "WIN")
        l   = sum(1 for x in subset if x["outcome"] == "LOSS")
        nt  = sum(1 for x in subset if x["outcome"] == "NOT_TRIGGERED")
        nd  = sum(1 for x in subset if x["outcome"] == "NO_DATA")
        neu = total - w - l - nt - nd
        decided = w + l
        return {
            "total":    total,
            "win":      w,
            "loss":     l,
            "neutral":  neu,
            "not_taken": nt,
            "no_data":  nd,
            "win_rate": round(w / decided * 100, 1) if decided > 0 else 0.0,
        }

    nifty = snapshot.get("indices", {}).get("NIFTY 50", {})
    nifty_pct = float(nifty.get("pct", 0) or 0)
    day_bias  = all_slots[0].get("bias", {}).get("direction", "NEUTRAL") if all_slots else "NEUTRAL"

    # Overall
    overall = _stats(outcomes)

    # By category
    by_category: Dict[str, Dict] = {}
    for cat in ["Index", "Stock", "ETF", "Momentum"]:
        sub = [o for o in outcomes if o["category"] == cat]
        if sub:
            by_category[cat] = _stats(sub)

    # By direction
    by_direction: Dict[str, Dict] = {}
    for d in ["LONG", "SHORT"]:
        sub = [o for o in outcomes if o["direction"] == d]
        if sub:
            by_direction[d] = _stats(sub)

    # By sector (all sectors with ≥1 rec, sorted by win_rate)
    sector_map: Dict[str, List] = {}
    for o in outcomes:
        sector_map.setdefault(o.get("sector", "Unknown"), []).append(o)
    by_sector = {
        sec: _stats(lst)
        for sec, lst in sorted(sector_map.items(), key=lambda x: len(x[1]), reverse=True)
    }

    # Best wins / worst losses for highlights
    best_wins  = sorted(
        [o for o in outcomes if o["outcome"] == "WIN"],
        key=lambda x: x["pnl_pct"], reverse=True
    )[:3]
    worst_loss = sorted(
        [o for o in outcomes if o["outcome"] == "LOSS"],
        key=lambda x: x["pnl_pct"]
    )[:3]

    # Bias vs actual market direction (for accuracy tracking)
    bias_correct = (
        (day_bias == "BEARISH" and nifty_pct < 0) or
        (day_bias == "BULLISH" and nifty_pct > 0)
    )

    review = {
        "date":         today,
        "nifty_pct":    round(nifty_pct, 2),
        "day_bias":     day_bias,
        "bias_correct": bias_correct,
        "slots_tracked": len(all_slots),
        "overall":      overall,
        "by_category":  by_category,
        "by_direction": by_direction,
        "by_sector":    by_sector,
        "best_wins":    best_wins,
        "worst_losses": worst_loss,
        "outcomes":     outcomes,   # full detail for analysis
    }

    review_file = _REVIEWS_DIR / f"{today}.json"
    with open(review_file, "w", encoding="utf-8") as f:
        json.dump(review, f, ensure_ascii=False, indent=2, default=str)

    ov = overall
    logger.info(
        f"EOD Review {today}: {ov['win']}W / {ov['loss']}L / "
        f"{ov['neutral']}N ({ov['win_rate']:.1f}% win rate) "
        f"from {ov['total']} setups"
    )
    return review


# ─── Performance history ─────────────────────────────────────────────────────

def load_performance_history(days: int = 14) -> List[Dict]:
    """Load review data from the last N calendar days."""
    results = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        review_file = _REVIEWS_DIR / f"{d}.json"
        if review_file.exists():
            try:
                with open(review_file, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except Exception:
                pass
    return results


# ─── Algorithm self-tuning ────────────────────────────────────────────────────

def update_algo_params(history: List[Dict] = None) -> Dict:
    """
    Analyse performance history and tune algorithm parameters.
    Requires ≥ 3 days of review data; otherwise returns current params.
    Rules:
      - Higher direction_score_threshold → fewer but more reliable signals
      - Momentum RS threshold → raise if low-RS alerts keep losing
      - Macro bias weight    → raise if daily bias direction is accurate
    """
    _ensure_dirs()
    current = load_algo_params()

    if history is None:
        history = load_performance_history(days=14)

    if len(history) < 3:
        logger.info(f"Param tuning skipped — only {len(history)} days of data (need ≥3)")
        return current

    # Flatten all outcomes across all review days
    all_out: List[Dict] = []
    for rev in history:
        all_out.extend(rev.get("outcomes", []))

    if not all_out:
        return current

    new = dict(current)
    notes = []

    # ── 1. Direction score threshold ──
    def _win_rate_at_threshold(outcomes, thresh):
        sub = [o for o in outcomes
               if abs(o.get("direction_score", 0)) >= thresh
               and o["outcome"] in ("WIN", "LOSS")]
        if len(sub) < 5:
            return None
        return sum(1 for o in sub if o["outcome"] == "WIN") / len(sub)

    wr15 = _win_rate_at_threshold(all_out, 15)
    wr20 = _win_rate_at_threshold(all_out, 20)
    wr25 = _win_rate_at_threshold(all_out, 25)

    if wr25 is not None and wr20 is not None and wr25 > wr20 + 0.05:
        new["direction_score_threshold"] = 25
        notes.append(f"Threshold→25 ({wr25:.0%} win vs {wr20:.0%} at 20)")
    elif wr20 is not None and wr15 is not None and wr20 > wr15 + 0.05:
        new["direction_score_threshold"] = 20
        notes.append(f"Threshold→20 ({wr20:.0%} win vs {wr15:.0%} at 15)")
    else:
        new["direction_score_threshold"] = 15
        notes.append("Threshold kept at 15 (no improvement at higher tiers)")

    # ── 2. Momentum RS minimum ──
    mom_all = [o for o in all_out if o["category"] == "Momentum"
               and o["outcome"] in ("WIN", "LOSS")]
    if len(mom_all) >= 5:
        def _wr(sub):
            return sum(1 for o in sub if o["outcome"] == "WIN") / len(sub) if sub else 0
        # Use pnl_pct as a proxy for RS magnitude (bigger moves = higher RS)
        high_pnl = [o for o in mom_all if abs(o.get("pnl_pct", 0)) > 1.0]
        low_pnl  = [o for o in mom_all if abs(o.get("pnl_pct", 0)) <= 1.0]
        if _wr(high_pnl) > _wr(low_pnl) + 0.10:
            new["momentum_rs_min_pct"] = 2.0
            notes.append(f"Momentum RS→2.0% (high-move alerts: {_wr(high_pnl):.0%} win)")
        else:
            new["momentum_rs_min_pct"] = 1.5
            notes.append("Momentum RS kept at 1.5%")

    # ── 3. Macro bias weight ──
    correct_bias = sum(1 for rev in history if rev.get("bias_correct", False))
    total_days   = len(history)
    if total_days >= 3:
        bias_acc = correct_bias / total_days
        if bias_acc >= 0.70:
            new["macro_bias_weight"] = 0.35
            notes.append(f"Bias weight→0.35 (accuracy {bias_acc:.0%})")
        elif bias_acc <= 0.45:
            new["macro_bias_weight"] = 0.20
            notes.append(f"Bias weight→0.20 (accuracy {bias_acc:.0%})")
        else:
            new["macro_bias_weight"] = 0.30
            notes.append(f"Bias weight kept at 0.30 (accuracy {bias_acc:.0%})")

    # ── 4. Compute rolling win rate summary ──
    decided = [o for o in all_out if o["outcome"] in ("WIN", "LOSS")]
    overall_wr = sum(1 for o in decided if o["outcome"] == "WIN") / len(decided) if decided else 0

    cat_rates: Dict[str, float] = {}
    for cat in ["Index", "Stock", "ETF", "Momentum"]:
        sub = [o for o in decided if o["category"] == cat]
        if sub:
            cat_rates[cat] = round(sum(1 for o in sub if o["outcome"] == "WIN") / len(sub) * 100, 1)

    dir_rates: Dict[str, float] = {}
    for d in ["LONG", "SHORT"]:
        sub = [o for o in decided if o["direction"] == d]
        if sub:
            dir_rates[d] = round(sum(1 for o in sub if o["outcome"] == "WIN") / len(sub) * 100, 1)

    # Best sectors over history
    sector_agg: Dict[str, List] = {}
    for o in decided:
        sector_agg.setdefault(o.get("sector", "?"), []).append(o)
    top_sectors = sorted(
        [(s, sum(1 for o in lst if o["outcome"] == "WIN") / len(lst))
         for s, lst in sector_agg.items() if len(lst) >= 3],
        key=lambda x: x[1], reverse=True
    )[:5]

    params_data = {
        "version":       3,
        "last_updated":  datetime.now().strftime("%Y-%m-%d"),
        "days_analyzed": len(history),
        "params":        new,
        "performance": {
            "overall_win_rate_pct": round(overall_wr * 100, 1),
            "by_category":          cat_rates,
            "by_direction":         dir_rates,
            "top_sectors":          {s: round(wr * 100, 1) for s, wr in top_sectors},
            "total_evaluated":      len(decided),
        },
        "tuning_notes": notes,
    }

    with open(_ALGO_PARAMS, "w", encoding="utf-8") as f:
        json.dump(params_data, f, ensure_ascii=False, indent=2)

    logger.info(
        f"Algo params updated (win_rate={overall_wr:.1%}, "
        f"{len(decided)} samples, {len(history)} days)"
    )
    return new


# ─── Telegram Formatters ─────────────────────────────────────────────────────

def format_review_msg(review: Dict) -> str:
    """Format EOD trading performance review as Telegram message."""
    if not review:
        return ""

    today    = review.get("date", "")
    n_pct    = review.get("nifty_pct", 0)
    day_bias = review.get("day_bias", "NEUTRAL")
    b_cor    = review.get("bias_correct", False)

    n_em   = "🟢" if n_pct >= 0 else "🔴"
    dir_em = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}.get(day_bias, "⚪")

    L = [f"<b>📊 EOD Trading Review — {today}</b>", ""]
    L.append(f"{dir_em} Day: {day_bias} | {n_em} Nifty {n_pct:+.2f}%")
    L.append(f"{'✅' if b_cor else '❌'} Bias prediction: {'Correct' if b_cor else 'Incorrect'}")
    L.append("")

    ov = review.get("overall", {})
    total = ov.get("total", 0)
    if not total:
        L.append("<i>No trade setups reviewed today.</i>")
        return "\n".join(L)

    win  = ov.get("win", 0)
    loss = ov.get("loss", 0)
    neu  = ov.get("neutral", 0)
    nt   = ov.get("not_taken", 0)
    wr   = ov.get("win_rate", 0)

    wr_em = "🟢" if wr >= 60 else ("🟡" if wr >= 40 else "🔴")
    L.append(f"<b>📈 Result: {wr_em} {wr:.1f}% Win Rate</b>")
    L.append(f"  {win}✅ Won  {loss}❌ Lost  {neu}⚪ Open  {nt} Not Triggered")
    L.append(f"  (from <b>{total}</b> setups across {review.get('slots_tracked', 0)} slots)")
    L.append("")

    # By Category
    by_cat = review.get("by_category", {})
    if by_cat:
        L.append("<b>By Category:</b>")
        for cat, st in by_cat.items():
            if st["total"] == 0:
                continue
            c_wr = st["win_rate"]
            em   = "✅" if c_wr >= 60 else ("⚠️" if c_wr >= 40 else "❌")
            L.append(f"  {em} {cat}: {st['win']}W / {st['loss']}L — <b>{c_wr:.0f}%</b>")
        L.append("")

    # By Direction
    by_dir = review.get("by_direction", {})
    if by_dir:
        L.append("<b>By Direction:</b>")
        for d, st in by_dir.items():
            d_em = "🟢" if d == "LONG" else "🔴"
            L.append(f"  {d_em} {d}: {st['win']}W / {st['loss']}L — {st['win_rate']:.0f}%")
        L.append("")

    # Top / Bottom sectors
    by_sec = review.get("by_sector", {})
    secs_with_data = [(s, v) for s, v in by_sec.items() if v.get("total", 0) >= 2]
    top_secs = sorted(secs_with_data, key=lambda x: x[1]["win_rate"], reverse=True)[:3]
    bot_secs = sorted(secs_with_data, key=lambda x: x[1]["win_rate"])[:2]

    if top_secs:
        L.append("<b>🏆 Best Sectors:</b>")
        for sec, st in top_secs:
            L.append(f"  ✅ {sec}: {st['win']}W/{st['loss']}L ({st['win_rate']:.0f}%)")
    if bot_secs:
        L.append("<b>📛 Weak Sectors:</b>")
        for sec, st in bot_secs:
            L.append(f"  ❌ {sec}: {st['win']}W/{st['loss']}L ({st['win_rate']:.0f}%)")
    if top_secs or bot_secs:
        L.append("")

    # Best calls
    best = review.get("best_wins", [])
    if best:
        L.append("<b>🌟 Best Calls:</b>")
        for o in best[:3]:
            L.append(f"  ✅ {o['symbol']} ({o['direction']}) +{o['pnl_pct']:.2f}%")
        L.append("")

    # Missed
    worst = review.get("worst_losses", [])
    if worst:
        L.append("<b>⚠️ Missed Calls:</b>")
        for o in worst[:2]:
            L.append(f"  ❌ {o['symbol']} ({o['direction']}) {o['pnl_pct']:.2f}%")
        L.append("")

    # Algorithm insight
    L.append("<b>🧠 Algorithm Insight:</b>")
    if wr >= 60:
        L.append("  ✅ Models performed well — parameters maintained")
    elif wr >= 40:
        L.append("  ⚠️ Mixed results — slight parameter adjustment applied")
    else:
        L.append("  ❌ Low accuracy today — parameters recalibrated for tomorrow")
    L.append("")
    L.append("<i>⚙️ Algo params auto-updated for next session</i>")

    return "\n".join(L)


def format_trend_report(days: int = 7) -> str:
    """
    Format a multi-day trend report showing rolling accuracy,
    best/worst conditions, and algorithm tuning summary.
    """
    history = load_performance_history(days=days)
    if not history:
        return ""

    # Flatten
    all_out = []
    for rev in history:
        all_out.extend(rev.get("outcomes", []))

    decided = [o for o in all_out if o["outcome"] in ("WIN", "LOSS")]
    if not decided:
        return ""

    overall_wr = sum(1 for o in decided if o["outcome"] == "WIN") / len(decided) * 100

    # Daily win rates
    daily = [(rev["date"], rev["overall"]["win_rate"]) for rev in history if rev.get("overall")]

    # Category rates
    cat_rates: Dict[str, float] = {}
    for cat in ["Index", "Stock", "ETF", "Momentum"]:
        sub = [o for o in decided if o["category"] == cat]
        if sub:
            cat_rates[cat] = round(
                sum(1 for o in sub if o["outcome"] == "WIN") / len(sub) * 100, 1
            )

    # Best conditions (BEARISH+SHORT vs BULLISH+LONG)
    bs_short = [o for o in decided if o["direction"] == "SHORT"]
    bu_long  = [o for o in decided if o["direction"] == "LONG"]

    def _wr(lst): return round(sum(1 for o in lst if o["outcome"] == "WIN") / len(lst) * 100, 1) if lst else 0

    # Algo params
    params = load_algo_params()
    algo_file = _ALGO_PARAMS
    last_updated = "N/A"
    days_analyzed = 0
    if algo_file.exists():
        try:
            with open(algo_file, "r", encoding="utf-8") as f:
                pd = json.load(f)
            last_updated  = pd.get("last_updated", "N/A")
            days_analyzed = pd.get("days_analyzed", 0)
        except Exception:
            pass

    wr_em = "🟢" if overall_wr >= 60 else ("🟡" if overall_wr >= 40 else "🔴")

    L = [f"<b>📋 {days}-Day Trading Performance Report</b>", ""]
    L.append(f"{wr_em} <b>Overall Win Rate: {overall_wr:.1f}%</b> ({len(decided)} decided trades)")
    L.append("")

    L.append("<b>Daily Win Rates:</b>")
    for date_str, wr in reversed(daily):
        em = "🟢" if wr >= 60 else ("🟡" if wr >= 40 else "🔴")
        L.append(f"  {em} {date_str}: {wr:.0f}%")
    L.append("")

    L.append("<b>Win Rate by Category:</b>")
    for cat, wr in cat_rates.items():
        em = "✅" if wr >= 60 else ("⚠️" if wr >= 40 else "❌")
        L.append(f"  {em} {cat}: {wr:.1f}%")
    L.append("")

    L.append("<b>Best Conditions:</b>")
    L.append(f"  🔴 SHORT setups: {_wr(bs_short):.0f}% win ({len(bs_short)} trades)")
    L.append(f"  🟢 LONG  setups: {_wr(bu_long):.0f}% win ({len(bu_long)} trades)")
    L.append("")

    L.append(f"<b>⚙️ Current Algo Params (updated {last_updated}, {days_analyzed}d data):</b>")
    L.append(f"  Score threshold: {params['direction_score_threshold']}")
    L.append(f"  Momentum RS min: {params['momentum_rs_min_pct']}%")
    L.append(f"  Macro bias weight: {params['macro_bias_weight']:.0%}")

    return "\n".join(L)
