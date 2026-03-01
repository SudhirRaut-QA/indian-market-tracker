"""
NSE Data Scraper v3.0 - Comprehensive Market Intelligence
============================================================

Data sources (all verified working):
 1. FII/DII aggregate          /api/fiidiiTradeReact
 2. All market indices (135)   /api/allIndices
 3. Market status              /api/marketStatus
 4. Sector stock data          /api/equity-stockIndices?index=<SECTOR>
 5. Pre-open data              /api/market-data-pre-open?key=NIFTY
 6. Option chain (PCR)         /api/option-chain-indices?symbol=<SYMBOL>
 7. Corporate actions          /api/corporates-corporateActions?index=equities
 8. Insider trading (PIT)      /api/corporates-pit?index=equities
 9. Stock quotes (ETFs/LTP)    /api/quote-equity?symbol=<SYMBOL>
10. USD/INR forex              External free API
11. Block deals                /api/block-deal
12. Bulk deals                 /api/bulk-deal-data

CRITICAL NSE rules:
- Must visit homepage first for session cookies
- Must NOT set Accept-Encoding header
- Must NOT use HTTPAdapter/Retry
- 1-2s delays between calls
"""

import logging
import re
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import requests

from . import config

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls."""
    
    def __init__(self, max_calls: int = 30, time_window: int = 60):
        """Allow max_calls within time_window seconds."""
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
    
    def wait_if_needed(self):
        """Block if rate limit exceeded."""
        now = time.time()
        
        # Remove calls outside time window
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()
        
        # Check if at limit
        if len(self.calls) >= self.max_calls:
            sleep_time = self.time_window - (now - self.calls[0])
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self.calls.clear()
        
        self.calls.append(now)


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    def call(self, func, *args, **kwargs):
        """Execute function through circuit breaker."""
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = "half-open"
                logger.info("Circuit breaker: HALF-OPEN (testing)")
            else:
                raise Exception("Circuit breaker OPEN - too many failures")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
                logger.info("Circuit breaker: CLOSED (recovered)")
            return result
        
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.failures >= self.failure_threshold:
                self.state = "open"
                logger.error(f"Circuit breaker: OPEN ({self.failures} failures)")
            
            raise e


class NSESession:
    """Manages authenticated session with NSE India (enterprise-grade)."""

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
        self.rate_limiter = RateLimiter(max_calls=30, time_window=60)
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        self.api_call_count = 0
        self.successful_calls = 0
        self.failed_calls = 0

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
        """Execute API call with rate limiting, circuit breaker, exponential backoff."""
        if not self._ensure_session():
            return None
        
        self.api_call_count += 1
        
        # Rate limiting
        self.rate_limiter.wait_if_needed()
        
        # Try through circuit breaker
        try:
            return self.circuit_breaker.call(self._do_api_call, url, params)
        except Exception as e:
            logger.error(f"Circuit breaker protected call failed: {e}")
            return None
    
    def _do_api_call(self, url: str, params: dict = None) -> Optional[Any]:
        """Actual API call with exponential backoff."""
        for attempt in range(config.NSE_MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=15)
                
                if resp.status_code == 200:
                    body = resp.text.strip()
                    if body.startswith(("[", "{")):
                        try:
                            self.successful_calls += 1
                            return resp.json()
                        except ValueError:
                            self._cookies_valid = False
                    else:
                        self._cookies_valid = False
                        self._ensure_session()
                
                elif resp.status_code in (401, 403):
                    logger.warning(f"Auth error {resp.status_code}, refreshing session")
                    self._cookies_valid = False
                    self._ensure_session()
                
                elif resp.status_code == 429:
                    # Rate limited by server
                    wait_time = int(resp.headers.get("Retry-After", 30))
                    logger.warning(f"Server rate limit hit, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                
                else:
                    logger.warning(f"Status {resp.status_code} for {url}")
            
            except requests.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}/{config.NSE_MAX_RETRIES}")
            
            except requests.RequestException as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
                self._cookies_valid = False
            
            # Exponential backoff
            if attempt < config.NSE_MAX_RETRIES - 1:
                backoff_time = config.NSE_RETRY_DELAY * (2 ** attempt)
                logger.info(f"Backing off {backoff_time}s before retry")
                time.sleep(backoff_time)
        
        self.failed_calls += 1
        return None
    
    def get_stats(self) -> Dict:
        """Get session statistics."""
        return {
            "total_calls": self.api_call_count,
            "successful": self.successful_calls,
            "failed": self.failed_calls,
            "success_rate": f"{(self.successful_calls/self.api_call_count*100) if self.api_call_count > 0 else 0:.1f}%",
            "circuit_breaker_state": self.circuit_breaker.state,
        }


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

    # ── 4. Sector Stocks (with 52W & volume alerts) ──────────────────────────

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
            near_52h_alerts = []
            near_52l_alerts = []

            for s in items[1:]:
                stock = {
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
                }
                stocks.append(stock)

                # 52-week proximity alerts
                n52h = stock["near_52h"]
                n52l = stock["near_52l"]
                if n52h and isinstance(n52h, (int, float)) and 0 < n52h <= config.NEAR_52W_HIGH_PCT:
                    near_52h_alerts.append({
                        "symbol": stock["symbol"],
                        "last": stock["last"],
                        "year_high": stock["year_high"],
                        "distance_pct": round(n52h, 2),
                        "pct_today": stock["pct"],
                    })
                if n52l and isinstance(n52l, (int, float)) and 0 < n52l <= config.NEAR_52W_LOW_PCT:
                    near_52l_alerts.append({
                        "symbol": stock["symbol"],
                        "last": stock["last"],
                        "year_low": stock["year_low"],
                        "distance_pct": round(n52l, 2),
                        "pct_today": stock["pct"],
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
                "near_52w_high": sorted(near_52h_alerts, key=lambda x: x["distance_pct"]),
                "near_52w_low": sorted(near_52l_alerts, key=lambda x: x["distance_pct"]),
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
                    ce_strikes.append({
                        "strike": strike, "oi": oi,
                        "chg_oi": ce.get("changeinOpenInterest", 0),
                        "iv": ce.get("impliedVolatility", 0),
                    })
                if "PE" in item:
                    pe = item["PE"]
                    oi = pe.get("openInterest", 0)
                    vol = pe.get("totalTradedVolume", 0)
                    pe_oi += oi; pe_vol += vol
                    pe_strikes.append({
                        "strike": strike, "oi": oi,
                        "chg_oi": pe.get("changeinOpenInterest", 0),
                        "iv": pe.get("impliedVolatility", 0),
                    })

            pcr = pe_oi / ce_oi if ce_oi else 0
            vol_pcr = pe_vol / ce_vol if ce_vol else 0
            signal = "Bullish" if pcr > 1.0 else "Neutral" if pcr >= 0.7 else "Bearish"

            top_ce = sorted(ce_strikes, key=lambda x: x["oi"], reverse=True)[:5]
            top_pe = sorted(pe_strikes, key=lambda x: x["oi"], reverse=True)[:5]

            # OI buildup alerts
            ce_buildup = sorted(ce_strikes, key=lambda x: x["chg_oi"], reverse=True)[:3]
            pe_buildup = sorted(pe_strikes, key=lambda x: x["chg_oi"], reverse=True)[:3]

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
                "ce_buildup": ce_buildup, "pe_buildup": pe_buildup,
            }
        except Exception as e:
            logger.error(f"OC {symbol} error: {e}")
            return None

    # ── 7. Corporate Actions (Enhanced with LTP/PE/Yield) ────────────────────

    def get_corporate_actions(self, days_range: int = 7) -> Optional[List[Dict]]:
        today = datetime.now()
        from_dt = (today - timedelta(days=days_range)).strftime("%d-%m-%Y")
        to_dt = (today + timedelta(days=days_range)).strftime("%d-%m-%Y")
        url = self._url(
            f"/api/corporates-corporateActions?index=equities"
            f"&from_date={from_dt}&to_date={to_dt}"
        )
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, list):
            return None
        try:
            actions = []
            for item in raw:
                action = {
                    "symbol": item.get("symbol", ""),
                    "company": item.get("comp", item.get("company", "")),
                    "subject": item.get("subject", ""),
                    "ex_date": item.get("exDate", ""),
                    "record_date": item.get("recDate", ""),
                    "bc_start": item.get("bcStartDate", ""),
                    "bc_end": item.get("bcEndDate", ""),
                    "purpose": item.get("purpose", ""),
                    "face_value": self._num(item.get("faceVal", "0")),
                }

                # Parse dividend amount from subject
                subject_lower = action["subject"].lower()
                div_amount = self._parse_dividend(subject_lower)
                if div_amount:
                    action["dividend_amount"] = div_amount
                    action["action_type"] = "dividend"
                elif "result" in subject_lower:
                    action["action_type"] = "results"
                elif "split" in subject_lower:
                    action["action_type"] = "split"
                elif "bonus" in subject_lower:
                    action["action_type"] = "bonus"
                elif "right" in subject_lower:
                    action["action_type"] = "rights"
                elif "buyback" in subject_lower:
                    action["action_type"] = "buyback"
                elif "agm" in subject_lower or "egm" in subject_lower:
                    action["action_type"] = "meeting"
                else:
                    action["action_type"] = "other"

                actions.append(action)
            logger.info(f"Corporate actions: {len(actions)}")
            return actions
        except Exception as e:
            logger.error(f"Corp actions error: {e}")
            return None

    def enrich_corporate_actions(
        self, actions: List[Dict], max_quotes: int = 15
    ) -> List[Dict]:
        """Fetch LTP, PE, delivery% for corporate action stocks."""
        if not actions:
            return actions

        # Unique symbols only, limit API calls
        symbols_seen = set()
        symbols_to_fetch = []
        for a in actions:
            sym = a["symbol"]
            if sym not in symbols_seen:
                symbols_seen.add(sym)
                symbols_to_fetch.append(sym)

        symbols_to_fetch = symbols_to_fetch[:max_quotes]
        quote_cache = {}

        for sym in symbols_to_fetch:
            quote = self.get_stock_quote(sym)
            if quote:
                quote_cache[sym] = quote
            time.sleep(1)

        # Enrich each action
        for a in actions:
            q = quote_cache.get(a["symbol"])
            if q:
                a["ltp"] = q.get("ltp", 0)
                a["pct_change"] = q.get("pct", 0)
                a["pe_ratio"] = q.get("pe", 0)
                a["sector"] = q.get("sector", "")
                a["delivery_pct"] = q.get("delivery_pct", 0)
                a["week52_high"] = q.get("week52_high", 0)
                a["week52_low"] = q.get("week52_low", 0)
                a["market_cap_cr"] = q.get("market_cap_cr", 0)

                # Calculate dividend yield
                div_amt = a.get("dividend_amount", 0)
                ltp = a.get("ltp", 0)
                if div_amt and ltp and ltp > 0:
                    a["dividend_yield"] = round((div_amt / ltp) * 100, 2)

        logger.info(f"Enriched {len(quote_cache)} corporate action stocks")
        return actions

    # ── 8. Insider Trading (PIT) ─────────────────────────────────────────────

    def get_insider_trading(self, days_range: int = 7) -> Optional[List[Dict]]:
        today = datetime.now()
        from_dt = (today - timedelta(days=days_range)).strftime("%d-%m-%Y")
        to_dt = today.strftime("%d-%m-%Y")
        url = self._url(
            f"/api/corporates-pit?index=equities"
            f"&from_date={from_dt}&to_date={to_dt}"
        )
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, dict):
            return None

    # ── 8b. IPOs (Mainboard) ───────────────────────────────────────────────

    def get_ipos(self) -> Optional[List[Dict]]:
        """Fetch IPO list (best-effort; endpoint may change)."""
        url = self._url("/api/ipo-current-issue")
        raw = self.nse.api_get(url)
        if not raw:
            return None

        try:
            data = raw.get("data", raw)
            if not isinstance(data, list):
                return None
            ipos = []
            for item in data:
                name = item.get("companyName") or item.get("name") or item.get("symbol")
                ipos.append({
                    "name": name or "",
                    "symbol": item.get("symbol", ""),
                    "open": item.get("issueStartDate", ""),
                    "close": item.get("issueEndDate", ""),
                    "price": item.get("issuePrice", ""),
                    "lot": item.get("lotSize", ""),
                    "status": item.get("status", ""),
                    "board": item.get("boardType", ""),
                })

            # Prefer mainboard when board info is present
            main = [i for i in ipos if "main" in (i.get("board", "") or "").lower()]
            return main or ipos
        except Exception as e:
            logger.error(f"IPO parse error: {e}")
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
                    continue
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

            trades.sort(key=lambda x: max(x["buy_value"], x["sell_value"]), reverse=True)
            logger.info(f"Insider trades: {len(trades)}")
            return trades
        except Exception as e:
            logger.error(f"Insider trading error: {e}")
            return None

    # ── 9. Commodity ETF Quotes ──────────────────────────────────────────────

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
            session = requests.Session()
            session.trust_env = True
            resp = session.get(config.FOREX_API_URL, timeout=60)
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

    # ── 11. Block Deals ──────────────────────────────────────────────────────

    def get_block_deals(self) -> Optional[List[Dict]]:
        """Large institutional transactions (typically 10Cr+ trades)."""
        raw = self.nse.api_get(self._url("/api/block-deal"))
        if not raw:
            return None
        try:
            deals = []
            data = raw.get("data", raw) if isinstance(raw, dict) else raw
            if not isinstance(data, list):
                data = []
            for item in data:
                qty = self._num(item.get("quantity", item.get("qty", "0")))
                price = self._num(item.get("tradePrice", item.get("price", "0")))
                value_cr = round((qty * price) / 1e7, 2) if qty and price else 0

                deals.append({
                    "symbol": item.get("symbol", item.get("securityName", "")),
                    "client": item.get("clientName", item.get("name", "")),
                    "buy_sell": item.get("buySell", item.get("buyOrSell", "")),
                    "quantity": qty,
                    "price": price,
                    "value_cr": value_cr,
                    "date": item.get("dealDate", item.get("date", "")),
                })

            deals.sort(key=lambda x: x["value_cr"], reverse=True)
            logger.info(f"Block deals: {len(deals)}")
            return deals
        except Exception as e:
            logger.error(f"Block deals error: {e}")
            return None

    # ── 12. Bulk Deals ───────────────────────────────────────────────────────

    def get_bulk_deals(self) -> Optional[List[Dict]]:
        """0.5%+ stake changes (operators, large investors)."""
        raw = self.nse.api_get(self._url("/api/bulk-deal-data"))
        if not raw:
            return None
        try:
            deals = []
            data = raw.get("data", raw) if isinstance(raw, dict) else raw
            if not isinstance(data, list):
                data = []
            for item in data:
                qty = self._num(item.get("quantity", item.get("qty", "0")))
                price = self._num(item.get("tradePrice", item.get("wAvgPrice", "0")))
                value_cr = round((qty * price) / 1e7, 2) if qty and price else 0

                deals.append({
                    "symbol": item.get("symbol", item.get("securityName", "")),
                    "client": item.get("clientName", item.get("name", "")),
                    "buy_sell": item.get("buySell", item.get("buyOrSell", "")),
                    "quantity": qty,
                    "price": price,
                    "value_cr": value_cr,
                    "date": item.get("dealDate", item.get("date", "")),
                })

            deals.sort(key=lambda x: x["value_cr"], reverse=True)
            logger.info(f"Bulk deals: {len(deals)}")
            return deals
        except Exception as e:
            logger.error(f"Bulk deals error: {e}")
            return None

    # ── 13. Individual Stock Quote ───────────────────────────────────────────

    def get_stock_quote(self, symbol: str) -> Optional[Dict]:
        """Get LTP, PE, delivery%, market cap for a single stock."""
        raw = self.nse.api_get(self._url(f"/api/quote-equity?symbol={symbol}"))
        if not raw:
            return None
        try:
            pi = raw.get("priceInfo", {})
            meta = raw.get("metadata", {})
            info = raw.get("info", {})
            sec_info = raw.get("securityInfo", {})
            wk = pi.get("weekHighLow", {})

            # PE ratio from industry info
            pe = 0
            industry_info = raw.get("industryInfo", {})
            if industry_info:
                pe = industry_info.get("pe", 0)
            # Fallback: try metadata
            if not pe:
                pe = meta.get("pdSectorPe", 0)

            # Delivery percentage
            delivery_pct = 0
            security_wise = raw.get("securityWiseDP", {})
            if security_wise:
                delivery_pct = self._num(
                    str(security_wise.get("deliveryToTradedQuantity", "0"))
                )

            # Market cap
            market_cap_cr = 0
            if sec_info:
                issued_size = self._num(str(sec_info.get("issuedSize", 0)))
                ltp = pi.get("lastPrice", 0)
                if issued_size and ltp:
                    market_cap_cr = round((issued_size * ltp) / 1e7, 2)

            return {
                "symbol": symbol,
                "ltp": pi.get("lastPrice", 0),
                "change": pi.get("change", 0),
                "pct": pi.get("pChange", 0),
                "open": pi.get("open", 0),
                "high": pi.get("intraDayHighLow", {}).get("max", 0),
                "low": pi.get("intraDayHighLow", {}).get("min", 0),
                "prev_close": pi.get("previousClose", 0),
                "week52_high": wk.get("max", 0),
                "week52_low": wk.get("min", 0),
                "pe": pe,
                "delivery_pct": delivery_pct,
                "sector": meta.get("industry", info.get("industry", "")),
                "series": meta.get("series", ""),
                "market_cap_cr": market_cap_cr,
                "face_value": self._num(str(sec_info.get("faceValue", "0"))),
            }
        except Exception as e:
            logger.error(f"Quote {symbol} error: {e}")
            return None

    # ── FULL SNAPSHOT ────────────────────────────────────────────────────────

    def get_snapshot(
        self,
        include_sectors: bool = True,
        include_options: bool = True,
        include_preopen: bool = False,
        include_corporate: bool = False,
        include_ipos: bool = False,
        include_insider: bool = False,
        include_block_deals: bool = False,
        include_bulk_deals: bool = False,
        enrich_corporate: bool = True,
        sector_list: List[str] = None,
    ) -> Dict:
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "fii_dii": None, "indices": None, "market_status": None,
            "forex": None, "commodities": {},
            "sectors": {}, "option_chain": {},
            "preopen": None, "corporate_actions": None,
            "ipos": None, "insider_trading": None,
            "block_deals": None, "bulk_deals": None,
            "alerts": {
                "near_52w_high": [], "near_52w_low": [],
            },
            "errors": [],
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

        # Sectors (with 52W alerts)
        if include_sectors:
            priority = sector_list or [
                "NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY AUTO",
                "NIFTY PHARMA", "NIFTY METAL", "NIFTY PSU BANK",
                "NIFTY INDIA DEFENCE", "NIFTY OIL & GAS",
            ]
            for name in priority:
                try:
                    d = self.get_sector_stocks(name)
                    if d:
                        snapshot["sectors"][name] = d
                        # Collect 52W alerts
                        for alert in d.get("near_52w_high", []):
                            alert["sector"] = name
                            snapshot["alerts"]["near_52w_high"].append(alert)
                        for alert in d.get("near_52w_low", []):
                            alert["sector"] = name
                            snapshot["alerts"]["near_52w_low"].append(alert)
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

        # Corporate actions (enriched with LTP/PE/yield)
        if include_corporate:
            try:
                actions = self.get_corporate_actions()
                if actions and enrich_corporate:
                    actions = self.enrich_corporate_actions(actions)
                snapshot["corporate_actions"] = actions
            except Exception as e:
                snapshot["errors"].append(f"Corp actions: {e}")
            time.sleep(1.5)

        # IPOs
        if include_ipos:
            try:
                snapshot["ipos"] = self.get_ipos()
            except Exception as e:
                snapshot["errors"].append(f"IPOs: {e}")
            time.sleep(1)

        # Insider trading
        if include_insider:
            try:
                snapshot["insider_trading"] = self.get_insider_trading()
            except Exception as e:
                snapshot["errors"].append(f"Insider: {e}")
            time.sleep(1)

        # Block deals
        if include_block_deals:
            try:
                snapshot["block_deals"] = self.get_block_deals()
            except Exception as e:
                snapshot["errors"].append(f"Block deals: {e}")
            time.sleep(1)

        # Bulk deals
        if include_bulk_deals:
            try:
                snapshot["bulk_deals"] = self.get_bulk_deals()
            except Exception as e:
                snapshot["errors"].append(f"Bulk deals: {e}")

        logger.info(f"Snapshot complete ({len(snapshot['errors'])} errors)")
        return snapshot

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _num(value) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            c = (value.replace(",", "").replace("\u20b9", "")
                 .replace("(", "-").replace(")", "").strip())
            try:
                return float(c) if c else 0.0
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def _parse_dividend(subject: str) -> float:
        """Extract dividend amount from corporate action subject text."""
        patterns = [
            r'rs\.?\s*([\d.]+)',
            r're\.?\s*([\d.]+)',
            r'\u20b9\s*([\d.]+)',
            r'([\d.]+)\s*(?:per\s+share|/\-)',
        ]
        for pat in patterns:
            m = re.search(pat, subject)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
        return 0
