"""
NSE Data Scraper - Comprehensive Market Intelligence
======================================================

Data sources (all verified working):
1. FII/DII aggregate         /api/fiidiiTradeReact
2. All market indices (135)  /api/allIndices
3. Market status             /api/marketStatus
4. Sector stock data         /api/equity-stockIndices?index=<SECTOR>
5. Pre-open data             /api/market-data-pre-open?key=NIFTY
6. Option chain (PCR)        /api/option-chain-indices?symbol=<SYMBOL>
7. Corporate actions         /api/corporates-corporateActions?index=equities
8. Insider trading (PIT)     /api/corporates-pit?index=equities
9. Stock quotes (ETFs)       /api/quote-equity?symbol=<SYMBOL>
10. USD/INR forex            External free API

CRITICAL NSE rules:
- Must visit homepage first for session cookies
- Must NOT set Accept-Encoding header
- Must NOT use HTTPAdapter/Retry
- 1-2s delays between calls
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import requests

from . import config

logger = logging.getLogger(__name__)


class NSESession:
    """Manages authenticated session with NSE India."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._cookies_valid = False

    def _init_cookies(self) -> bool:
        try:
            self.session = requests.Session()
            self.session.headers.update(self.HEADERS)
            resp = self.session.get(config.NSE_BASE_URL, timeout=15)
            if resp.status_code == 200:
                self._cookies_valid = True
                logger.info(f"NSE cookies: {len(self.session.cookies)}")
                time.sleep(1)
                return True
            return False
        except requests.RequestException as e:
            logger.error(f"Cookie init failed: {e}")
            return False

    def _ensure_session(self):
        if not self._cookies_valid:
            for attempt in range(config.NSE_MAX_RETRIES):
                if self._init_cookies():
                    return True
                time.sleep(config.NSE_RETRY_DELAY)
            return False
        return True

    def api_get(self, url: str, params: dict = None) -> Optional[Any]:
        if not self._ensure_session():
            return None

        for attempt in range(config.NSE_MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    body = resp.text.strip()
                    if body.startswith(("[", "{")):
                        try:
                            return resp.json()
                        except ValueError:
                            self._cookies_valid = False
                    else:
                        self._cookies_valid = False
                        self._ensure_session()
                elif resp.status_code in (401, 403):
                    self._cookies_valid = False
                    self._ensure_session()
                else:
                    logger.warning(f"Status {resp.status_code} for {url}")
            except requests.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
                self._cookies_valid = False

            if attempt < config.NSE_MAX_RETRIES - 1:
                time.sleep(config.NSE_RETRY_DELAY * (attempt + 1))
        return None


class MarketScraper:
    """Comprehensive NSE + external market data scraper."""

    def __init__(self):
        self.nse = NSESession()

    def _url(self, path: str) -> str:
        return f"{config.NSE_BASE_URL}{path}"

    # ── 1. FII/DII ──────────────────────────────────────────────────────────

    def get_fii_dii(self) -> Optional[Dict]:
        raw = self.nse.api_get(self._url("/api/fiidiiTradeReact"))
        if not raw:
            return None
        try:
            result = {"timestamp": datetime.now().isoformat(), "date": None,
                      "fii": {"buy": 0, "sell": 0, "net": 0},
                      "dii": {"buy": 0, "sell": 0, "net": 0}}
            for entry in raw:
                cat = entry.get("category", "").upper()
                buy = self._num(entry.get("buyValue", "0"))
                sell = self._num(entry.get("sellValue", "0"))
                net = self._num(entry.get("netValue", "0"))
                if not result["date"]:
                    result["date"] = entry.get("date", "")
                if "FII" in cat or "FPI" in cat:
                    result["fii"] = {"buy": buy, "sell": sell, "net": net}
                elif "DII" in cat:
                    result["dii"] = {"buy": buy, "sell": sell, "net": net}

            fii_n, dii_n = result["fii"]["net"], result["dii"]["net"]
            result["total_net"] = fii_n + dii_n
            if fii_n > 0 and dii_n > 0:
                result["signal"] = "Strong Bullish"
                result["interpretation"] = "Both FII & DII BUYING"
            elif fii_n > 0:
                result["signal"] = "FII Bullish"
                result["interpretation"] = "FII buying, DII selling — FII-led rally"
            elif dii_n > 0:
                result["signal"] = "DII Defensive"
                result["interpretation"] = "FII selling, DII buying — DII supporting"
            else:
                result["signal"] = "Bearish"
                result["interpretation"] = "Both FII & DII SELLING"
            logger.info(f"FII/DII: {result['date']}")
            return result
        except Exception as e:
            logger.error(f"FII/DII parse error: {e}")
            return None

    # ── 2. Market Indices ────────────────────────────────────────────────────

    def get_indices(self) -> Optional[Dict]:
        raw = self.nse.api_get(self._url("/api/allIndices"))
        if not raw:
            return None
        try:
            result = {}
            for idx in raw.get("data", []):
                name = idx.get("index", "")
                if name in config.KEY_INDICES:
                    result[name] = {
                        "last": idx.get("last", 0),
                        "change": idx.get("variation", 0),
                        "pct": idx.get("percentChange", 0),
                        "open": idx.get("open", 0),
                        "high": idx.get("high", 0),
                        "low": idx.get("low", 0),
                        "prev_close": idx.get("previousClose", 0),
                        "advances": idx.get("advances", 0),
                        "declines": idx.get("declines", 0),
                        "unchanged": idx.get("unchanged", 0),
                    }
            logger.info(f"Indices: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"Indices error: {e}")
            return None

    # ── 3. Market Status ─────────────────────────────────────────────────────

    def get_market_status(self) -> Optional[Dict]:
        raw = self.nse.api_get(self._url("/api/marketStatus"))
        if not raw:
            return None
        try:
            statuses = {}
            for m in raw.get("marketState", []):
                statuses[m.get("market", "")] = {
                    "status": m.get("marketStatus", ""),
                    "trade_date": m.get("tradeDate", ""),
                    "index": m.get("index", ""),
                    "last": m.get("last", 0),
                    "variation": m.get("variation", 0),
                    "pct": m.get("percentChange", 0),
                }
            return statuses
        except Exception as e:
            logger.error(f"Market status error: {e}")
            return None

    # ── 4. Sector Stocks ─────────────────────────────────────────────────────

    def get_sector_stocks(self, sector_name: str) -> Optional[Dict]:
        encoded = config.SECTORS.get(sector_name)
        if not encoded:
            return None
        raw = self.nse.api_get(self._url(f"/api/equity-stockIndices?index={encoded}"))
        if not raw:
            return None
        try:
            items = raw.get("data", [])
            if not items:
                return None
            idx_data = items[0]
            stocks = []
            for s in items[1:]:
                stocks.append({
                    "symbol": s.get("symbol", ""),
                    "last": s.get("lastPrice", 0),
                    "change": s.get("change", 0),
                    "pct": s.get("pChange", 0),
                    "open": s.get("open", 0),
                    "high": s.get("dayHigh", 0),
                    "low": s.get("dayLow", 0),
                    "prev_close": s.get("previousClose", 0),
                    "volume": s.get("totalTradedVolume", 0),
                    "value_cr": round(s.get("totalTradedValue", 0) / 1e7, 2),
                    "year_high": s.get("yearHigh", 0),
                    "year_low": s.get("yearLow", 0),
                    "near_52h": s.get("nearWKH", 0),
                    "near_52l": s.get("nearWKL", 0),
                    "chg_30d": s.get("perChange30d", 0),
                    "chg_365d": s.get("perChange365d", 0),
                })
            by_chg = sorted(stocks, key=lambda x: x["pct"], reverse=True)
            by_val = sorted(stocks, key=lambda x: x["value_cr"], reverse=True)
            by_vol = sorted(stocks, key=lambda x: x["volume"], reverse=True)
            return {
                "sector": sector_name,
                "timestamp": raw.get("timestamp", ""),
                "index_last": idx_data.get("lastPrice", 0) or idx_data.get("last", 0),
                "index_change": idx_data.get("change", 0) or idx_data.get("variation", 0),
                "index_pct": idx_data.get("pChange", 0) or idx_data.get("percentChange", 0),
                "count": len(stocks),
                "stocks": stocks,
                "gainers": by_chg[:5],
                "losers": list(reversed(by_chg[-5:])),
                "most_traded": by_val[:5],
                "most_volume": by_vol[:5],
            }
        except Exception as e:
            logger.error(f"Sector {sector_name} error: {e}")
            return None

    def get_all_sectors(self, names: List[str] = None, delay: float = 1.5) -> Dict:
        names = names or list(config.SECTORS.keys())
        results = {}
        for i, name in enumerate(names):
            try:
                d = self.get_sector_stocks(name)
                if d:
                    results[name] = d
            except Exception as e:
                logger.error(f"{name}: {e}")
            if i < len(names) - 1:
                time.sleep(delay)
        logger.info(f"Sectors: {len(results)}/{len(names)}")
        return results

    # ── 5. Pre-Open ──────────────────────────────────────────────────────────

    def get_preopen(self, key: str = "NIFTY") -> Optional[Dict]:
        raw = self.nse.api_get(self._url(f"/api/market-data-pre-open?key={key}"))
        if not raw:
            return None
        try:
            stocks = []
            for item in raw.get("data", []):
                m = item.get("metadata", {})
                stocks.append({
                    "symbol": m.get("symbol", ""),
                    "iep": m.get("iep", 0),
                    "change": m.get("change", 0),
                    "pct": m.get("pChange", 0),
                    "prev_close": m.get("previousClose", 0),
                    "final_qty": m.get("finalQuantity", 0),
                })
            by_chg = sorted(stocks, key=lambda x: x["pct"], reverse=True)
            return {
                "key": key, "timestamp": raw.get("timestamp", ""),
                "advances": raw.get("advances", 0),
                "declines": raw.get("declines", 0),
                "stocks": stocks,
                "gainers": by_chg[:5],
                "losers": list(reversed(by_chg[-5:])),
            }
        except Exception as e:
            logger.error(f"Pre-open error: {e}")
            return None

    # ── 6. Option Chain PCR ──────────────────────────────────────────────────

    def get_option_pcr(self, symbol: str = "NIFTY") -> Optional[Dict]:
        raw = self.nse.api_get(self._url(f"/api/option-chain-indices?symbol={symbol}"))
        if not raw:
            return None
        try:
            records = raw.get("records", {})
            data = records.get("data", [])
            if not data:
                return None
            ce_oi = pe_oi = ce_vol = pe_vol = 0
            ce_strikes, pe_strikes = [], []
            for item in data:
                strike = item.get("strikePrice", 0)
                if "CE" in item:
                    ce = item["CE"]
                    oi = ce.get("openInterest", 0)
                    vol = ce.get("totalTradedVolume", 0)
                    ce_oi += oi; ce_vol += vol
                    ce_strikes.append({"strike": strike, "oi": oi, "chg_oi": ce.get("changeinOpenInterest", 0)})
                if "PE" in item:
                    pe = item["PE"]
                    oi = pe.get("openInterest", 0)
                    vol = pe.get("totalTradedVolume", 0)
                    pe_oi += oi; pe_vol += vol
                    pe_strikes.append({"strike": strike, "oi": oi, "chg_oi": pe.get("changeinOpenInterest", 0)})

            pcr = pe_oi / ce_oi if ce_oi else 0
            vol_pcr = pe_vol / ce_vol if ce_vol else 0
            signal = "Bullish" if pcr > 1.0 else "Neutral" if pcr >= 0.7 else "Bearish"

            top_ce = sorted(ce_strikes, key=lambda x: x["oi"], reverse=True)[:5]
            top_pe = sorted(pe_strikes, key=lambda x: x["oi"], reverse=True)[:5]

            combined = {}
            for s in ce_strikes:
                combined[s["strike"]] = combined.get(s["strike"], 0) + s["oi"]
            for s in pe_strikes:
                combined[s["strike"]] = combined.get(s["strike"], 0) + s["oi"]
            max_pain = max(combined, key=combined.get, default=0) if combined else 0

            return {
                "symbol": symbol, "pcr_oi": round(pcr, 4),
                "pcr_vol": round(vol_pcr, 4), "signal": signal,
                "max_pain": max_pain,
                "ce_oi_total": ce_oi, "pe_oi_total": pe_oi,
                "top_ce": top_ce, "top_pe": top_pe,
            }
        except Exception as e:
            logger.error(f"OC {symbol} error: {e}")
            return None

    # ── 7. Corporate Actions ─────────────────────────────────────────────────

    def get_corporate_actions(self, days_range: int = 7) -> Optional[List[Dict]]:
        today = datetime.now()
        from_dt = (today - timedelta(days=days_range)).strftime("%d-%m-%Y")
        to_dt = (today + timedelta(days=days_range)).strftime("%d-%m-%Y")
        url = self._url(f"/api/corporates-corporateActions?index=equities&from_date={from_dt}&to_date={to_dt}")
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, list):
            return None
        try:
            actions = []
            for item in raw:
                actions.append({
                    "symbol": item.get("symbol", ""),
                    "company": item.get("comp", item.get("company", "")),
                    "subject": item.get("subject", ""),
                    "ex_date": item.get("exDate", ""),
                    "record_date": item.get("recDate", ""),
                    "bc_start": item.get("bcStartDate", ""),
                    "bc_end": item.get("bcEndDate", ""),
                })
            logger.info(f"Corporate actions: {len(actions)}")
            return actions
        except Exception as e:
            logger.error(f"Corp actions error: {e}")
            return None

    # ── 8. Insider Trading (PIT) ─────────────────────────────────────────────

    def get_insider_trading(self, days_range: int = 7) -> Optional[List[Dict]]:
        today = datetime.now()
        from_dt = (today - timedelta(days=days_range)).strftime("%d-%m-%Y")
        to_dt = today.strftime("%d-%m-%Y")
        url = self._url(f"/api/corporates-pit?index=equities&from_date={from_dt}&to_date={to_dt}")
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, dict):
            return None
        try:
            entries = raw.get("data", [])
            trades = []
            for item in entries:
                buy_val = self._num(item.get("buyValue", "0"))
                sell_val = self._num(item.get("sellValue", "0"))
                buy_qty = self._num(item.get("buyQuantity", "0"))
                sell_qty = self._num(item.get("sellQuantity", "0"))
                if buy_val == 0 and sell_val == 0:
                    continue  # Skip empty
                trades.append({
                    "symbol": item.get("symbol", ""),
                    "company": item.get("company", ""),
                    "acquirer": item.get("acqName", ""),
                    "relation": item.get("anex", ""),
                    "buy_qty": buy_qty,
                    "sell_qty": sell_qty,
                    "buy_value": buy_val,
                    "sell_value": sell_val,
                    "date": item.get("date", ""),
                })

            # Sort by value of transaction
            trades.sort(key=lambda x: max(x["buy_value"], x["sell_value"]), reverse=True)
            logger.info(f"Insider trades: {len(trades)}")
            return trades
        except Exception as e:
            logger.error(f"Insider trading error: {e}")
            return None

    # ── 9. Commodity ETF Quotes ──────────────────────────────────────────────

    def get_stock_quote(self, symbol: str) -> Optional[Dict]:
        """Fetch a single stock's quote (LTP, PE, 52W, volume, etc.)."""
        raw = self.nse.api_get(self._url(f"/api/quote-equity?symbol={symbol}"))
        if not raw:
            return None
        try:
            pi = raw.get("priceInfo", {})
            wk = pi.get("weekHighLow", {})
            info = raw.get("info", {})
            meta = raw.get("metadata", {})
            ind = raw.get("industryInfo", {})
            sec_info = raw.get("securityInfo", {})
            return {
                "symbol": symbol,
                "last": pi.get("lastPrice", 0),
                "change": pi.get("change", 0),
                "pct": pi.get("pChange", 0),
                "open": pi.get("open", 0),
                "high": pi.get("intraDayHighLow", {}).get("max", 0),
                "low": pi.get("intraDayHighLow", {}).get("min", 0),
                "prev_close": pi.get("previousClose", 0),
                "week52_high": wk.get("max", 0),
                "week52_low": wk.get("min", 0),
                "pe": meta.get("pdSymbolPe", 0) or sec_info.get("pe", 0),
                "sector": meta.get("industry", ind.get("industry", "")),
                "face_value": sec_info.get("faceValue", 0),
            }
        except Exception as e:
            logger.error(f"Stock quote {symbol} error: {e}")
            return None

    def enrich_corporate_actions(self, actions: List[Dict], max_enrich: int = 10) -> List[Dict]:
        """Enrich corporate actions with LTP, PE from stock quotes.
        Only enriches the first `max_enrich` actions to avoid too many API calls.
        """
        if not actions:
            return actions
        enriched = 0
        seen_symbols = set()
        quote_cache = {}
        for a in actions:
            sym = a.get("symbol", "")
            if not sym or enriched >= max_enrich:
                continue
            if sym in seen_symbols:
                # Reuse cached quote
                if sym in quote_cache:
                    q = quote_cache[sym]
                    a["ltp"] = q.get("last", 0)
                    a["pe"] = q.get("pe", 0)
                    a["week52_high"] = q.get("week52_high", 0)
                    a["week52_low"] = q.get("week52_low", 0)
                continue
            seen_symbols.add(sym)
            try:
                q = self.get_stock_quote(sym)
                if q:
                    quote_cache[sym] = q
                    a["ltp"] = q.get("last", 0)
                    a["pe"] = q.get("pe", 0)
                    a["week52_high"] = q.get("week52_high", 0)
                    a["week52_low"] = q.get("week52_low", 0)
                    enriched += 1
            except Exception as e:
                logger.warning(f"Enrich {sym}: {e}")
            time.sleep(1)
        logger.info(f"Enriched {enriched} corporate actions with LTP/PE")
        return actions

    def get_commodity_etfs(self) -> Dict:
        results = {}
        for symbol in config.COMMODITY_ETFS:
            raw = self.nse.api_get(self._url(f"/api/quote-equity?symbol={symbol}"))
            if raw:
                try:
                    pi = raw.get("priceInfo", {})
                    wk = pi.get("weekHighLow", {})
                    results[symbol] = {
                        "last": pi.get("lastPrice", 0),
                        "change": pi.get("change", 0),
                        "pct": pi.get("pChange", 0),
                        "open": pi.get("open", 0),
                        "high": pi.get("intraDayHighLow", {}).get("max", 0),
                        "low": pi.get("intraDayHighLow", {}).get("min", 0),
                        "prev_close": pi.get("previousClose", 0),
                        "week52_high": wk.get("max", 0),
                        "week52_low": wk.get("min", 0),
                    }
                except Exception as e:
                    logger.error(f"ETF {symbol} error: {e}")
            time.sleep(1)
        logger.info(f"Commodity ETFs: {len(results)}")
        return results

    # ── 10. USD/INR Forex ────────────────────────────────────────────────────

    def get_usdinr(self) -> Optional[Dict]:
        try:
            resp = requests.get(config.FOREX_API_URL, timeout=10)
            if resp.status_code == 200:
                d = resp.json()
                rates = d.get("usd", {})
                return {
                    "usdinr": round(rates.get("inr", 0), 4),
                    "usdeur": round(rates.get("eur", 0), 4),
                    "usdgbp": round(rates.get("gbp", 0), 4),
                    "usdjpy": round(rates.get("jpy", 0), 4),
                    "date": d.get("date", ""),
                }
        except Exception as e:
            logger.error(f"Forex API error: {e}")
        return None

    # ── FULL SNAPSHOT ────────────────────────────────────────────────────────

    def get_snapshot(
        self,
        include_sectors: bool = True,
        include_options: bool = True,
        include_preopen: bool = False,
        include_corporate: bool = False,
        include_insider: bool = False,
        sector_list: List[str] = None,
    ) -> Dict:
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "fii_dii": None, "indices": None, "market_status": None,
            "forex": None, "commodities": {},
            "sectors": {}, "option_chain": {},
            "preopen": None, "corporate_actions": None,
            "insider_trading": None, "errors": [],
        }

        # FII/DII
        try:
            snapshot["fii_dii"] = self.get_fii_dii()
            if not snapshot["fii_dii"]:
                snapshot["errors"].append("FII/DII unavailable")
        except Exception as e:
            snapshot["errors"].append(f"FII/DII: {e}")
        time.sleep(1.5)

        # Indices
        try:
            snapshot["indices"] = self.get_indices()
        except Exception as e:
            snapshot["errors"].append(f"Indices: {e}")
        time.sleep(1)

        # Market status
        try:
            snapshot["market_status"] = self.get_market_status()
        except Exception as e:
            snapshot["errors"].append(f"Status: {e}")
        time.sleep(1)

        # Forex
        try:
            snapshot["forex"] = self.get_usdinr()
        except Exception as e:
            snapshot["errors"].append(f"Forex: {e}")

        # Commodity ETFs
        try:
            snapshot["commodities"] = self.get_commodity_etfs()
        except Exception as e:
            snapshot["errors"].append(f"Commodities: {e}")
        time.sleep(1)

        # Sectors
        if include_sectors:
            priority = sector_list or list(config.SECTORS.keys())
            for name in priority:
                try:
                    d = self.get_sector_stocks(name)
                    if d:
                        snapshot["sectors"][name] = d
                except Exception as e:
                    snapshot["errors"].append(f"Sector {name}: {e}")
                time.sleep(1.5)

        # Options
        if include_options:
            for sym in ["NIFTY", "BANKNIFTY"]:
                try:
                    oc = self.get_option_pcr(sym)
                    if oc:
                        snapshot["option_chain"][sym] = oc
                except Exception as e:
                    snapshot["errors"].append(f"OC {sym}: {e}")
                time.sleep(1.5)

        # Pre-open
        if include_preopen:
            try:
                snapshot["preopen"] = self.get_preopen("NIFTY")
            except Exception as e:
                snapshot["errors"].append(f"Pre-open: {e}")
            time.sleep(1)

        # Corporate actions (daily, once in evening)
        if include_corporate:
            try:
                snapshot["corporate_actions"] = self.get_corporate_actions()
                # Enrich with LTP, PE from stock quotes
                if snapshot["corporate_actions"]:
                    snapshot["corporate_actions"] = self.enrich_corporate_actions(
                        snapshot["corporate_actions"], max_enrich=15
                    )
            except Exception as e:
                snapshot["errors"].append(f"Corp actions: {e}")
            time.sleep(1.5)

        # Insider trading (daily, once in evening)
        if include_insider:
            try:
                snapshot["insider_trading"] = self.get_insider_trading()
            except Exception as e:
                snapshot["errors"].append(f"Insider: {e}")

        logger.info(f"Snapshot complete ({len(snapshot['errors'])} errors)")
        return snapshot

    @staticmethod
    def _num(value) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            c = value.replace(",", "").replace("\u20b9", "").replace("(", "-").replace(")", "").strip()
            try:
                return float(c) if c else 0.0
            except ValueError:
                return 0.0
        return 0.0
