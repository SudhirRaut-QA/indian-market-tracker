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

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

import requests
import urllib3

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

from . import config

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NSESession:
    """Manages authenticated session with NSE India.
    
    NSE uses Akamai Bot Manager which blocks datacenter IPs (GitHub Actions).
    curl_cffi impersonates Chrome's TLS fingerprint to bypass this.
    Falls back to plain requests for local/residential IPs.
    """

    # Headers for visiting the homepage (looks like real browser navigation)
    BROWSER_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8,"
                  "application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
    }

    # Headers for NSE API calls (XHR requests from the page)
    API_HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": config.NSE_BASE_URL + "/",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    # Only set User-Agent when NOT using curl_cffi (it sets its own)
    FALLBACK_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.session = None
        self._cookies_valid = False
        self._using_cffi = False
        self._create_session()

    def _create_session(self):
        """Create HTTP session with best available client."""
        if HAS_CURL_CFFI:
            self.session = cffi_requests.Session(impersonate="chrome")
            self._using_cffi = True
            logger.info("NSE session: curl_cffi (Chrome TLS impersonation)")
        else:
            self.session = requests.Session()
            self.session.headers.update({"User-Agent": self.FALLBACK_UA})
            self._using_cffi = False
            logger.info("NSE session: plain requests (curl_cffi not available)")
        self._cookies_valid = False

    def _init_cookies(self) -> bool:
        """Visit NSE homepage to get session cookies."""
        try:
            self._create_session()
            
            # For plain requests, set browser-like headers
            # curl_cffi handles headers via impersonation
            if not self._using_cffi:
                self.session.headers.update(self.BROWSER_HEADERS)
            
            req_kwargs = {"timeout": 20}
            if not self._using_cffi:
                req_kwargs["verify"] = False

            resp = self.session.get(config.NSE_BASE_URL, **req_kwargs)
            
            if resp.status_code == 200:
                cookie_count = len(self.session.cookies)
                self._cookies_valid = True
                logger.info(f"NSE cookies: {cookie_count} (status 200)")
                if cookie_count == 0:
                    logger.warning("Got 200 but 0 cookies — may be a challenge page")
                time.sleep(2)
                return True
            else:
                logger.warning(
                    f"NSE homepage returned {resp.status_code} "
                    f"(body starts: '{resp.text[:80].strip()}')"
                )
                return False
        except Exception as e:
            logger.error(f"Cookie init failed: {e}")
            return False

    def _ensure_session(self):
        """Ensure we have valid NSE session cookies."""
        if not self._cookies_valid:
            for attempt in range(config.NSE_MAX_RETRIES):
                logger.info(f"Session init attempt {attempt + 1}/{config.NSE_MAX_RETRIES}...")
                if self._init_cookies():
                    return True
                time.sleep(config.NSE_RETRY_DELAY * (attempt + 1))
            logger.error(
                f"Failed to establish NSE session after {config.NSE_MAX_RETRIES} attempts. "
                f"{'curl_cffi active' if self._using_cffi else 'INSTALL curl_cffi: pip install curl_cffi'}"
            )
            return False
        return True

    def api_get(self, url: str, params: dict = None) -> Optional[Any]:
        """Make authenticated GET request to NSE API."""
        if not self._ensure_session():
            return None

        for attempt in range(config.NSE_MAX_RETRIES):
            try:
                resp = self.session.get(
                    url, params=params, timeout=20,
                    headers=self.API_HEADERS,
                    verify=False if not self._using_cffi else True,
                )
                if resp.status_code == 200:
                    body = resp.text.strip()
                    if body.startswith(("[", "{")):
                        try:
                            return resp.json()
                        except ValueError:
                            logger.warning(f"Invalid JSON from {url}")
                            self._cookies_valid = False
                    else:
                        logger.warning(
                            f"Non-JSON response from {url} "
                            f"(len={len(body)}, starts='{body[:80]}')"
                        )
                        self._cookies_valid = False
                        self._ensure_session()
                elif resp.status_code in (401, 403):
                    logger.warning(f"Auth error {resp.status_code} for {url} — refreshing session")
                    self._cookies_valid = False
                    self._ensure_session()
                else:
                    logger.warning(f"Status {resp.status_code} for {url}")
            except Exception as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
                self._cookies_valid = False

            if attempt < config.NSE_MAX_RETRIES - 1:
                time.sleep(config.NSE_RETRY_DELAY * (attempt + 1))
        
        logger.error(f"All {config.NSE_MAX_RETRIES} retries failed for {url}")
        return None


class MarketScraper:
    """Comprehensive NSE + external market data scraper."""

    def __init__(self):
        self.nse = NSESession()

    def _url(self, path: str) -> str:
        return f"{config.NSE_BASE_URL}{path}"

    def _feed_health_path(self) -> Path:
        return Path(config.DATA_DIR) / "feed_health.json"

    def _load_feed_health_state(self) -> Dict[str, Dict]:
        p = self._feed_health_path()
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_feed_health_state(self, state: Dict[str, Dict]) -> None:
        p = self._feed_health_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Feed health save failed: {e}")

    def _mark_feed_health(
        self,
        state: Dict[str, Dict],
        key: str,
        status: str,
        count: int = 0,
        message: str = "",
    ) -> None:
        now_iso = datetime.now().isoformat()
        prev = state.get(key, {}) if isinstance(state.get(key, {}), dict) else {}
        item = {
            "status": status,
            "last_attempt": now_iso,
            "last_count": int(count or 0),
            "last_success": prev.get("last_success", ""),
            "message": message,
        }
        if status == "ok" and count > 0:
            item["last_success"] = now_iso
        state[key] = item

    @staticmethod
    def _parse_action_date(date_str: str) -> Optional[datetime]:
        """Parse exchange action dates across NSE/BSE format variants."""
        if not date_str:
            return None
        ds = str(date_str).strip()
        for fmt in (
            "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
            "%d %b %Y", "%d %B %Y", "%d-%B-%Y", "%Y%m%d",
            "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y",
        ):
            try:
                return datetime.strptime(ds, fmt)
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _extract_buyback_offer_from_text(text: str) -> float:
        """Extract buyback offer price from subject/announcement text."""
        if not text:
            return 0.0
        pats = (
            r'@\s*Rs\.?\s*([\d,]+(?:\.\d+)?)',
            r'at\s+(?:not\s+exceeding\s+)?Rs\.?\s*([\d,]+(?:\.\d+)?)',
            r'price\s+of\s+Rs\.?\s*([\d,]+(?:\.\d+)?)',
            r'Rs\.?\s*([\d,]+(?:\.\d+)?)\s*per\s+(?:equity\s+)?share',
        )
        for pat in pats:
            m = re.search(pat, text, re.IGNORECASE)
            if not m:
                continue
            try:
                return float(m.group(1).replace(",", ""))
            except (ValueError, TypeError):
                continue
        return 0.0

    def _extract_future_date_from_text(
        self,
        text: str,
        today: datetime,
        cutoff: datetime,
    ) -> Optional[datetime]:
        """Extract first upcoming date from free text within [today, cutoff]."""
        if not text:
            return None

        cleaned = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", str(text), flags=re.IGNORECASE)
        candidates: List[datetime] = []

        patterns = (
            r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
            r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b",
            r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
            r"\b[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}\b",
            r"\b[A-Za-z]{3,9}\s+\d{1,2}\s+\d{4}\b",
        )
        for pat in patterns:
            for m in re.finditer(pat, cleaned):
                raw = m.group(0).replace(",", " ")
                dt = self._parse_action_date(raw)
                if not dt:
                    continue
                if today.date() <= dt.date() <= cutoff.date():
                    candidates.append(dt)

        if not candidates:
            return None
        return min(candidates)

    @staticmethod
    def _corporate_action_key(action: Dict) -> tuple:
        """Stable dedup key that preserves distinct same-day actions.

        Uses normalized full subject (not just prefix) so events like
        multiple dividends on the same ex-date are not collapsed.
        """
        symbol = str(action.get("symbol", "") or "").strip().upper()
        ex_date = str(action.get("ex_date", "") or "").strip()
        record_date = str(action.get("record_date", "") or "").strip()
        subject = re.sub(r"\s+", " ", str(action.get("subject", "") or "")).strip().lower()
        # Keep source out of key so same event across NSE/BSE can be merged and
        # displayed with a combined source tag.
        return (symbol, ex_date, record_date, subject)

    def _load_dividend_actions_from_csv(self, days_ahead: int = 21, max_age_hours: int = 36) -> List[Dict]:
        """Fallback corporate-dividend rows from local CSV if fresh enough.

        The CSV is used only as a supplementary source when exchange APIs miss
        certain rows. Freshness guard prevents stale carry-forward data.
        """
        import csv as csv_mod

        csv_path = config.DATA_DIR / "excel" / "upcoming_dividends_latest.csv"
        if not csv_path.exists():
            return []

        # Freshness guard
        try:
            mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
            age_hours = (datetime.now() - mtime).total_seconds() / 3600
            if age_hours > max_age_hours:
                logger.info(
                    f"Dividend CSV fallback skipped (stale {age_hours:.1f}h > {max_age_hours}h): {csv_path}"
                )
                return []
        except Exception:
            return []

        today = datetime.now().date()
        cutoff = today + timedelta(days=days_ahead)
        out: List[Dict] = []

        try:
            with open(csv_path, encoding="utf-8") as f:
                for row in csv_mod.DictReader(f):
                    sym = str(row.get("Symbol", "") or "").strip().upper()
                    if not sym:
                        continue
                    ex_raw = str(row.get("Ex_Date", "") or "").strip()
                    ex_dt = self._parse_action_date(ex_raw)
                    if not ex_dt:
                        continue
                    ex_date = ex_dt.date()
                    if ex_date < today or ex_date > cutoff:
                        continue

                    try:
                        div = float(str(row.get("Dividend_INR", "0") or "0").replace(",", ""))
                    except (TypeError, ValueError):
                        div = 0.0
                    try:
                        ltp = float(str(row.get("LTP_INR", "0") or "0").replace(",", ""))
                    except (TypeError, ValueError):
                        ltp = 0.0
                    try:
                        pe = float(str(row.get("PE_Ratio", "0") or "0").replace(",", ""))
                    except (TypeError, ValueError):
                        pe = 0.0

                    div_type = str(row.get("Dividend_Type", "") or "Dividend").strip()
                    if div > 0:
                        subject = f"{div_type} Dividend - Rs {div:g} Per Share"
                    else:
                        subject = f"{div_type} Dividend"

                    out.append({
                        "symbol": sym,
                        "company": str(row.get("Company", "") or "").strip(),
                        "subject": subject,
                        "ex_date": ex_dt.strftime("%d-%b-%Y"),
                        "record_date": "",
                        "bc_start": "",
                        "bc_end": "",
                        "source": "DIV-CSV",
                        "ltp": ltp,
                        "pe": pe,
                    })
        except Exception as e:
            logger.warning(f"Dividend CSV fallback load failed: {e}")
            return []

        logger.info(f"Dividend CSV fallback rows: {len(out)}")
        return out

    def _load_cached_corporate_actions(self, max_age_hours: int = 72) -> List[Dict]:
        """Fallback: load recent corporate actions from last_snapshot.json.

        Freshness guard avoids pulling very old rows when live feeds are degraded.
        """
        try:
            p = Path(config.SNAPSHOT_DIR) / "last_snapshot.json"
            if not p.exists():
                return []
            if max_age_hours > 0:
                age_hours = (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 3600
                if age_hours > max_age_hours:
                    logger.info(
                        f"Cached corporate fallback skipped (stale {age_hours:.1f}h > {max_age_hours}h): {p}"
                    )
                    return []
            data = json.loads(p.read_text(encoding="utf-8"))
            actions = data.get("corporate_actions") or []
            logger.info(f"Cached corporate actions fallback: {len(actions)}")
            return actions
        except Exception as e:
            logger.warning(f"Cached corporate fallback failed: {e}")
            return []

    # ── 1. FII/DII ──────────────────────────────────────────────────────────

    def get_fii_dii(self) -> Optional[Dict]:
        raw = self.nse.api_get(self._url("/api/fiidiiTradeReact"))
        if not raw:
            logger.warning("FII/DII API returned no data (NSE may be blocking or API unavailable)")
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
            logger.warning("Indices API returned no data (NSE may be blocking or API unavailable)")
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
            return result if result else None
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
                last_p = s.get("lastPrice", 0) or 0
                year_high = s.get("yearHigh", 0) or 0
                year_low = s.get("yearLow", 0) or 0
                pe_raw = s.get("pdSymbolPe") or s.get("pe") or s.get("PE")
                deliv_raw = (
                    s.get("deliveryToTradedQuantity")
                    or s.get("deliveryToTradedQty")
                    or s.get("deliveryQtyToTradedQty")
                )
                pe_val = self._num(pe_raw)
                delivery_pct = self._num(deliv_raw)
                if not (0 < delivery_pct <= 100):
                    delivery_pct = 0.0
                # nearWKH/nearWKL are often absent/0 in the bulk sector API
                # response even when the stock IS near its 52W level.
                # Always compute from yearHigh/yearLow as authoritative source.
                near_h = round((year_high - last_p) / last_p * 100, 2) if last_p and year_high > last_p else 0
                near_l = round((last_p - year_low) / year_low * 100, 2) if last_p and year_low and last_p > year_low else 0
                stocks.append({
                    "symbol": s.get("symbol", ""),
                    "last": last_p,
                    "change": s.get("change", 0),
                    "pct": s.get("pChange", 0),
                    "open": s.get("open", 0),
                    "high": s.get("dayHigh", 0),
                    "low": s.get("dayLow", 0),
                    "prev_close": s.get("previousClose", 0),
                    "volume": s.get("totalTradedVolume", 0),
                    "value_cr": round(s.get("totalTradedValue", 0) / 1e7, 2),
                    "year_high": year_high,
                    "year_low": year_low,
                    "near_52h": near_h,
                    "near_52l": near_l,
                    "chg_30d": s.get("perChange30d", 0),
                    "chg_365d": s.get("perChange365d", 0),
                    "pe": round(pe_val, 2) if pe_val > 0 else 0,
                    "delivery_pct": round(delivery_pct, 2) if delivery_pct > 0 else 0,
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

    def get_corporate_actions(self, days_ahead: int = 21) -> Optional[List[Dict]]:
        """Fetch NSE corporate actions from today to today+days_ahead."""
        today = datetime.now()
        from_dt = today.strftime("%d-%m-%Y")
        to_dt = (today + timedelta(days=days_ahead)).strftime("%d-%m-%Y")
        url = self._url(f"/api/corporates-corporateActions?index=equities&from_date={from_dt}&to_date={to_dt}")
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, list):
            return None
        try:
            actions = []
            for item in raw:
                subject = item.get("subject", "")
                subj_l = str(subject or "").lower()
                offer_price = (
                    self._extract_buyback_offer_from_text(str(subject or ""))
                    if ("buyback" in subj_l or "buy back" in subj_l or "buy-back" in subj_l)
                    else 0.0
                )
                actions.append({
                    "symbol": item.get("symbol", ""),
                    "company": item.get("comp", item.get("company", "")),
                    "subject": subject,
                    "ex_date": item.get("exDate", ""),
                    "record_date": item.get("recDate", ""),
                    "bc_start": item.get("bcStartDate", ""),
                    "bc_end": item.get("bcEndDate", ""),
                    "source": "NSE",
                    "offer_price": offer_price if offer_price > 0 else 0.0,
                })
            logger.info(f"NSE corporate actions: {len(actions)}")
            return actions
        except Exception as e:
            logger.error(f"Corp actions error: {e}")
            return None

    def get_nse_board_meetings(self, days_ahead: int = 21) -> Optional[List[Dict]]:
        """Fetch NSE board meetings/events and map to corporate-action-like rows."""
        today = datetime.now()
        from_dt = today.strftime("%d-%m-%Y")
        to_dt = (today + timedelta(days=days_ahead)).strftime("%d-%m-%Y")
        url = self._url(
            f"/api/corporate-board-meetings?index=equities&from_date={from_dt}&to_date={to_dt}"
        )
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, list):
            return []
        try:
            actions = []
            for item in raw:
                symbol = str(item.get("symbol", "") or "").strip().upper()
                company = str(item.get("company", "") or item.get("comp", "")).strip()
                purpose = str(item.get("bmPurpose", "") or item.get("purpose", "")).strip()
                meeting_date = str(item.get("bmDate", "") or item.get("date", "")).strip()
                if not symbol or not purpose or not meeting_date:
                    continue
                actions.append({
                    "symbol": symbol,
                    "company": company,
                    "subject": f"Board Meeting - {purpose}",
                    "ex_date": meeting_date,
                    "record_date": "",
                    "bc_start": "",
                    "bc_end": "",
                    "source": "NSE-BM",
                })
            logger.info(f"NSE board meetings: {len(actions)}")
            return actions
        except Exception as e:
            logger.warning(f"NSE board meetings error: {e}")
            return []

    def get_nse_major_announcements(self, days_ahead: int = 21, lookback_days: int = 120) -> Optional[List[Dict]]:
        """Fetch NSE announcements and derive upcoming corporate-action rows.

        NSE announcement API is announcement-date oriented (not ex-date oriented),
        so we read a recent lookback window and then extract upcoming action dates
        from explicit fields or attachment text.
        """
        today = datetime.now()
        cutoff = today + timedelta(days=days_ahead)
        from_dt = (today - timedelta(days=max(lookback_days, 21))).strftime("%d-%m-%Y")
        to_dt = today.strftime("%d-%m-%Y")
        url = self._url(
            f"/api/corporate-announcements?index=equities&from_date={from_dt}&to_date={to_dt}"
        )
        raw = self.nse.api_get(url)
        if not raw:
            return []

        if isinstance(raw, dict):
            rows = raw.get("data") or raw.get("announcements") or []
        elif isinstance(raw, list):
            rows = raw
        else:
            rows = []
        if not isinstance(rows, list):
            return []

        keywords = (
            "dividend", "buyback", "buy back", "bonus", "split", "sub-division",
            "rights", "demerger", "merger", "amalgamation", "board meeting",
            "financial results", "results",
        )
        actions: List[Dict] = []
        try:
            for item in rows:
                symbol = str(
                    item.get("symbol") or item.get("sm_name") or item.get("symbolName") or ""
                ).strip().upper()
                company = str(item.get("company") or item.get("comp") or item.get("sm_name") or "").strip()
                subject = str(
                    item.get("subject") or item.get("desc") or item.get("headline") or ""
                ).strip()
                detail_text = str(item.get("attchmntText") or "").strip()
                combined = f"{subject} {detail_text}".strip()
                ex_date = str(
                    item.get("exDate") or item.get("ex_date") or item.get("date") or item.get("an_dt") or ""
                ).strip()
                rec_date = str(item.get("recDate") or item.get("record_date") or "").strip()
                if not symbol or not subject:
                    continue
                subj_l = combined.lower()
                if not any(k in subj_l for k in keywords):
                    continue

                ex_dt = self._parse_action_date(ex_date) if ex_date else None
                rec_dt = self._parse_action_date(rec_date) if rec_date else None

                if not ex_dt:
                    ex_dt = self._extract_future_date_from_text(combined, today, cutoff)
                if not rec_dt and detail_text:
                    rec_hint = "" if "record" not in detail_text.lower() else detail_text
                    rec_dt = self._extract_future_date_from_text(rec_hint, today, cutoff)

                action_dt = ex_dt or rec_dt
                if not action_dt:
                    continue
                if action_dt.date() < today.date() or action_dt.date() > cutoff.date():
                    continue

                ex_out = (ex_dt or rec_dt).strftime("%d-%b-%Y") if (ex_dt or rec_dt) else ""
                rec_out = rec_dt.strftime("%d-%b-%Y") if rec_dt else ""
                offer_price = self._extract_buyback_offer_from_text(combined)

                refined_subject = detail_text if detail_text else subject
                if offer_price > 0 and ("buyback" in subj_l or "buy back" in subj_l):
                    refined_subject = f"Buy Back @ Rs {offer_price:g} Per Share"

                actions.append({
                    "symbol": symbol,
                    "company": company,
                    "subject": f"Announcement - {refined_subject[:220]}",
                    "ex_date": ex_out,
                    "record_date": rec_out,
                    "bc_start": "",
                    "bc_end": "",
                    "source": "NSE-ANN",
                    "offer_price": offer_price if offer_price > 0 else 0.0,
                })
            logger.info(f"NSE major announcements: {len(actions)}")
            return actions
        except Exception as e:
            logger.warning(f"NSE major announcements error: {e}")
            return []

    def get_nse_earnings_calendar(self, days_ahead: int = 21) -> Optional[List[Dict]]:
        """Fetch upcoming earnings/results events from NSE endpoints."""
        today = datetime.now()
        cutoff = today + timedelta(days=days_ahead)
        from_dt = today.strftime("%d-%m-%Y")
        to_dt = cutoff.strftime("%d-%m-%Y")

        def _parse_dt(s: str) -> Optional[datetime]:
            if not s:
                return None
            for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
                try:
                    return datetime.strptime(str(s).strip(), fmt)
                except (ValueError, TypeError):
                    continue
            return None

        endpoints = [
            self._url(f"/api/corporates-financial-results?index=equities&from_date={from_dt}&to_date={to_dt}"),
            self._url(f"/api/corporate-financial-results?index=equities&from_date={from_dt}&to_date={to_dt}"),
        ]
        out: Dict[tuple, Dict] = {}
        for url in endpoints:
            raw = self.nse.api_get(url)
            if not raw:
                continue
            rows = raw.get("data", []) if isinstance(raw, dict) else raw
            if not isinstance(rows, list):
                continue
            for item in rows:
                symbol = str(item.get("symbol") or item.get("sm_name") or "").strip().upper()
                company = str(item.get("company") or item.get("comp") or item.get("sm_name") or "").strip()
                purpose = str(
                    item.get("purpose")
                    or item.get("subject")
                    or item.get("bmPurpose")
                    or item.get("desc")
                    or "Financial Results"
                ).strip()
                event_date_raw = str(
                    item.get("resultDate")
                    or item.get("bmDate")
                    or item.get("date")
                    or item.get("an_dt")
                    or item.get("meetingDate")
                    or ""
                ).strip()
                if not symbol:
                    continue
                dt = _parse_dt(event_date_raw)
                if not dt or dt.date() < today.date() or dt.date() > cutoff.date():
                    continue
                key = (symbol, dt.strftime("%d-%b-%Y"), purpose[:40].lower())
                out[key] = {
                    "symbol": symbol,
                    "company": company,
                    "purpose": purpose,
                    "date": dt.strftime("%d-%b-%Y"),
                    "source": "NSE-ER",
                }
        events = list(out.values())
        logger.info(f"NSE earnings calendar: {len(events)}")
        return events

    def get_bse_corporate_actions(self, days_ahead: int = 21) -> Optional[List[Dict]]:
        """Fetch BSE corporate actions for upcoming window with live fallback windows.

        Reliability strategy:
        1) Preferred live window: today -> today+days_ahead
        2) Fallback lookbacks: today-7 / today-30
        3) Re-filter strictly to upcoming [today, today+days_ahead] to avoid stale rows
        """
        def _parse_bse_date(s: str) -> Optional[datetime]:
            return self._parse_action_date(s)

        def _extract_items(raw_json) -> List[Dict]:
            if isinstance(raw_json, list):
                return raw_json
            if isinstance(raw_json, dict):
                items = (
                    raw_json.get("Table")
                    or raw_json.get("table")
                    or raw_json.get("data")
                    or raw_json.get("Data")
                    or raw_json.get("results")
                    or raw_json.get("Results")
                    or []
                )
                return items if isinstance(items, list) else []
            return []

        def _fetch_bse_items(from_dt: str, to_dt: str, use_session: bool = False) -> List[Dict]:
            url = (
                "https://api.bseindia.com/BseIndiaAPI/api/CorporateAction/w"
                f"?strType=C&scripcode=&Category=&Fdate={from_dt}&Tdate={to_dt}"
            )
            # BSE probe confirmed: plain requests returns '{}' (empty, 2 bytes) — BSE
            # now blocks without a real Chrome TLS fingerprint. Use curl_cffi if available.
            def _bse_get(target_url: str, sess=None) -> Optional[requests.Response]:
                if HAS_CURL_CFFI:
                    try:
                        if sess is None:
                            return cffi_requests.get(
                                target_url, headers=headers, timeout=15,
                                impersonate="chrome131", verify=False,
                            )
                        return sess.get(
                            target_url, headers=headers, timeout=15,
                            impersonate="chrome131",
                        )
                    except Exception as ce:
                        logger.warning(f"curl_cffi BSE get failed: {ce}")
                # plain requests fallback
                try:
                    return requests.get(target_url, headers=headers, timeout=12, verify=False)
                except Exception:
                    return None

            if not use_session:
                resp = _bse_get(url)
                if not resp or resp.status_code != 200:
                    logger.warning(
                        f"BSE direct returned {resp.status_code if resp else 'None'} for {from_dt}->{to_dt}"
                    )
                    return []
                items = _extract_items(resp.json())
                if items:
                    return items
                logger.info(f"BSE direct: empty response for {from_dt}->{to_dt} (trying warm session)")

            # Warm up: visit BSE homepage to get real cookies, then call data API.
            if HAS_CURL_CFFI:
                cffi_sess = cffi_requests.Session()
                for warm in ("https://www.bseindia.com/", "https://www.bseindia.com/corporates/"):
                    try:
                        cffi_sess.get(warm, headers=headers, timeout=10,
                                      impersonate="chrome131", verify=False)
                    except Exception:
                        pass
                resp = _bse_get(url, sess=cffi_sess)
            else:
                sess = requests.Session()
                for warm in ("https://www.bseindia.com/", "https://www.bseindia.com/corporates/"):
                    try:
                        sess.get(warm, headers=headers, timeout=10, verify=False)
                    except Exception:
                        pass
                resp = _bse_get(url, sess=sess)

            if not resp or resp.status_code != 200:
                logger.warning(
                    f"BSE warm session returned {resp.status_code if resp else 'None'} for {from_dt}->{to_dt}"
                )
                return []
            return _extract_items(resp.json())

        today = datetime.now()
        cutoff = today + timedelta(days=days_ahead)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.bseindia.com/",
            "Origin": "https://www.bseindia.com",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }
        try:
            windows = [
                (today, cutoff),
                (today - timedelta(days=7), cutoff),
                (today - timedelta(days=30), cutoff),
            ]
            merged_by_key: Dict[tuple, Dict] = {}
            for w_from, w_to in windows:
                # BSE API accepts DD/MM/YYYY — YYYYMMDD returns empty {}
                from_dt = w_from.strftime("%d/%m/%Y")
                to_dt = w_to.strftime("%d/%m/%Y")
                items = _fetch_bse_items(from_dt, to_dt, use_session=False)
                if not items:
                    items = _fetch_bse_items(from_dt, to_dt, use_session=True)
                if not items:
                    logger.info(f"BSE corporate actions: 0 for {from_dt}->{to_dt}")
                    continue

                for item in items:
                    symbol = (
                        item.get("short_name") or item.get("ShortName") or
                        item.get("SCRIP_ID") or item.get("SecurityCode") or
                        item.get("SC_CODE") or str(item.get("SCRIP_CD", ""))
                    )
                    company = (
                        item.get("SLONGNAME") or item.get("LongName") or
                        item.get("companyname") or ""
                    )
                    subject = (
                        item.get("PURPOSE") or item.get("purpose") or
                        item.get("Subject") or ""
                    )
                    ex_date = (
                        item.get("EX_DATE") or item.get("Ex_Date") or
                        item.get("exDate") or ""
                    )
                    rec_date = (
                        item.get("REC_DT") or item.get("Rec_Date") or
                        item.get("recDate") or ""
                    )
                    if not symbol or not subject:
                        continue

                    ex_dt = _parse_bse_date(str(ex_date).strip())
                    # Freshness guard: include only upcoming events in requested horizon.
                    if not ex_dt or ex_dt.date() < today.date() or ex_dt.date() > cutoff.date():
                        continue

                    norm_ex = ex_dt.strftime("%d-%b-%Y")
                    action = {
                        "symbol": str(symbol).strip().upper(),
                        "company": str(company).strip(),
                        "subject": str(subject).strip(),
                        "ex_date": norm_ex,
                        "record_date": str(rec_date).strip(),
                        "bc_start": "",
                        "bc_end": "",
                        "source": "BSE",
                        "offer_price": self._extract_buyback_offer_from_text(str(subject or "")),
                    }
                    key = (
                        action["symbol"],
                        action["ex_date"],
                        re.sub(r"\s+", " ", action["subject"]).strip().lower(),
                    )
                    merged_by_key[key] = action

            actions = list(merged_by_key.values())
            logger.info(f"BSE corporate actions: {len(actions)} (live fallback windows)")
            return actions
        except Exception as e:
            logger.warning(f"BSE corp actions error: {e}")
            return None

    # ── 8. Bulk/Block Deals ──────────────────────────────────────────────────

    def get_bulk_deals(self) -> Optional[List[Dict]]:
        """Get today's bulk deals (off-market large volume trades)."""
        raw = self.nse.api_get(self._url("/api/snapshot-capital-market-largedeal"))
        if not raw or not isinstance(raw, dict):
            return None
        try:
            deals = []
            for item in raw.get("BULKDEAL", []):
                deals.append({
                    "symbol": item.get("symbol", ""),
                    "client": item.get("clientName", ""),
                    "trade_type": "BUY" if "BUY" in item.get("action", "").upper() else "SELL",
                    "qty": self._num(item.get("quantity", "0")),
                    "price": self._num(item.get("tradePrice", "0")),
                    "value_cr": round(self._num(item.get("quantity", "0")) * self._num(item.get("tradePrice", "0")) / 1e7, 2),
                    "date": item.get("date", ""),
                })
            # Sort by value
            deals.sort(key=lambda x: x["value_cr"], reverse=True)
            logger.info(f"Bulk deals: {len(deals)}")
            return deals
        except Exception as e:
            logger.error(f"Bulk deals error: {e}")
            return None

    def get_block_deals(self) -> Optional[List[Dict]]:
        """Get today's block deals (large institutional trades on exchange)."""
        raw = self.nse.api_get(self._url("/api/block-deal"))
        if not raw or not isinstance(raw, list):
            return None
        try:
            deals = []
            for item in raw:
                deals.append({
                    "symbol": item.get("symbol", ""),
                    "client": item.get("clientName", ""),
                    "trade_type": "BUY" if "BUY" in item.get("dealType", "").upper() else "SELL",
                    "qty": self._num(item.get("quantity", "0")),
                    "price": self._num(item.get("tradePrice", "0")),
                    "value_cr": round(self._num(item.get("quantity", "0")) * self._num(item.get("tradePrice", "0")) / 1e7, 2),
                    "date": item.get("dealDate", ""),
                })
            # Sort by value
            deals.sort(key=lambda x: x["value_cr"], reverse=True)
            logger.info(f"Block deals: {len(deals)}")
            return deals
        except Exception as e:
            logger.error(f"Block deals error: {e}")
            return None

    # ── 9. Insider Trading (PIT) ─────────────────────────────────────────────

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

    @staticmethod
    def _extract_delivery_pct_from_quote_raw(raw: Dict) -> float:
        """Extract delivery% from quote-equity payload when available."""
        candidates = [
            ((raw.get("securityWiseDP") or {}).get("deliveryToTradedQuantity")),
            ((raw.get("securityWiseDP") or {}).get("deliveryToTradedQty")),
            (((raw.get("marketDeptOrderBook") or {}).get("tradeInfo") or {}).get("deliveryToTradedQuantity")),
            (((raw.get("marketDeptOrderBook") or {}).get("tradeInfo") or {}).get("deliveryToTradedQty")),
            ((raw.get("metadata") or {}).get("deliveryToTradedQuantity")),
        ]
        for c in candidates:
            if c is None:
                continue
            try:
                v = float(str(c).replace(",", "").strip())
            except (TypeError, ValueError):
                continue
            if 0 < v <= 100:
                return round(v, 2)
        return 0.0

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
            # PE can be string or float from NSE API
            pe_val = meta.get("pdSymbolPe") or sec_info.get("pe", 0)
            delivery_pct = self._extract_delivery_pct_from_quote_raw(raw)
            try:
                pe_float = float(pe_val) if pe_val else 0.0
            except (ValueError, TypeError):
                pe_float = 0.0
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
                "pe": pe_float,
                "delivery_pct": delivery_pct,
                "sector": meta.get("industry", ind.get("industry", "")),
                "face_value": sec_info.get("faceValue", 0),
            }
        except Exception as e:
            logger.error(f"Stock quote {symbol} error: {e}")
            return None

    def _get_sector_stock_lookup(self, sectors: Dict) -> Dict[str, Dict]:
        """Build symbol→quote dict from already-fetched sector data (no API calls)."""
        lookup: Dict[str, Dict] = {}
        for sector_data in sectors.values():
            for stock in sector_data.get("stocks", []):
                sym = stock.get("symbol", "")
                if sym and sym not in lookup:
                    lookup[sym] = {
                        "last": stock.get("last", 0),
                        "pct":  stock.get("pct", 0),
                        "pe":   stock.get("pe", 0) or 0,
                        "delivery_pct": stock.get("delivery_pct", 0) or 0,
                        "week52_high": stock.get("year_high", 0),
                        "week52_low":  stock.get("year_low", 0),
                    }
        return lookup

    def _get_stock_quote_fast(self, symbol: str) -> Optional[Dict]:
        """One-shot quote fetch — NO retry, NO session re-auth on 403.
        Returns None immediately if session is known-bad (avoids retry storm).
        """
        # Bail immediately if session is known-bad — no retries, no delays
        if not self.nse._cookies_valid:
            return None
        try:
            url = self._url(f"/api/quote-equity?symbol={symbol}")
            resp = self.nse.session.get(
                url, timeout=8,
                headers=self.nse.API_HEADERS,
                verify=False if not self.nse._using_cffi else True,
            )
            if resp.status_code != 200:
                return None   # skip silently — do NOT re-auth
            body = resp.text.strip()
            if not body.startswith(("{", "[")):
                return None
            raw = resp.json()
            pi   = raw.get("priceInfo", {})
            wk   = pi.get("weekHighLow", {})
            meta = raw.get("metadata", {})
            sec  = raw.get("securityInfo", {})
            pe_raw = meta.get("pdSymbolPe") or sec.get("pe", 0)
            delivery_pct = self._extract_delivery_pct_from_quote_raw(raw)
            try:
                pe_float = float(str(pe_raw).replace(",", "")) if pe_raw else 0.0
            except (ValueError, TypeError):
                pe_float = 0.0
            return {
                "last":        pi.get("lastPrice", 0),
                "pct":         pi.get("pChange", 0),
                "pe":          pe_float,
                "delivery_pct": delivery_pct,
                "week52_high": wk.get("max", 0),
                "week52_low":  wk.get("min", 0),
            }
        except Exception:
            return None

    def _build_quality_lookup_from_quotes(self, sectors: Dict, max_symbols: int = 24) -> Dict[str, Dict]:
        """Build symbol→{pe, delivery_pct} lookup for top liquid names.

        Keeps API calls bounded and only enriches where quality fields are missing.
        """
        if not sectors or max_symbols <= 0:
            return {}

        best_by_symbol: Dict[str, Dict] = {}
        for sector_data in sectors.values():
            for s in sector_data.get("stocks", []):
                sym = s.get("symbol", "")
                if not sym:
                    continue
                cur = best_by_symbol.get(sym)
                if not cur or (s.get("value_cr", 0) or 0) > (cur.get("value_cr", 0) or 0):
                    best_by_symbol[sym] = {
                        "value_cr": float(s.get("value_cr", 0) or 0),
                        "volume": float(s.get("volume", 0) or 0),
                    }

        ranked = sorted(
            best_by_symbol.items(),
            key=lambda kv: (kv[1].get("value_cr", 0), kv[1].get("volume", 0)),
            reverse=True,
        )
        if not ranked:
            return {}

        out: Dict[str, Dict] = {}
        for sym, _ in ranked[:max_symbols]:
            q = self._get_stock_quote_fast(sym)
            if not q:
                continue
            pe = float(q.get("pe", 0) or 0)
            delivery_pct = float(q.get("delivery_pct", 0) or 0)
            if pe <= 0 and delivery_pct <= 0:
                continue
            out[sym] = {
                "pe": round(pe, 2) if pe > 0 else 0.0,
                "delivery_pct": round(delivery_pct, 2) if delivery_pct > 0 else 0.0,
            }
            time.sleep(0.2)

        if out:
            logger.info(f"Quality lookup via quote API: {len(out)}/{min(len(ranked), max_symbols)} symbols")
        return out

    def enrich_corporate_actions(
        self,
        actions: List[Dict],
        max_api_calls: int = 8,
        sector_data: Dict = None,
        prebuilt_lookup: Dict = None,
    ) -> List[Dict]:
        """Enrich corporate actions with LTP / PE / 52W data.

        Strategy (fast-first, no timeout):
        1. prebuilt_lookup (sector + NIFTY 500 already merged by caller)
        2. Sector data passed directly (legacy path)
        3. Quote API (one-shot, no re-auth) → adds PE for top max_api_calls symbols.
        """
        if not actions:
            return actions

        # Step 1: use pre-built lookup (fastest — no API calls)
        if prebuilt_lookup:
            sector_lookup = prebuilt_lookup
            logger.info(f"Enrichment: using prebuilt lookup ({len(sector_lookup)} symbols)")
        else:
            sector_lookup = self._get_sector_stock_lookup(sector_data or {})
            logger.info(f"Sector lookup: {len(sector_lookup)} symbols available for enrichment")

        for a in actions:
            sym = a.get("symbol", "")
            if sym and sym in sector_lookup:
                q = sector_lookup[sym]
                a.setdefault("ltp",          q["last"])
                a.setdefault("pct",          q["pct"])
                a.setdefault("week52_high",  q["week52_high"])
                a.setdefault("week52_low",   q["week52_low"])

        # Step 2: fetch PE via fast quote API — ONLY if session is healthy
        # and prebuilt_lookup doesn't already cover most symbols.
        corp_syms = {a.get("symbol", "") for a in actions}
        covered_by_lookup = corp_syms & set(sector_lookup.keys())
        # Skip API calls entirely when prebuilt lookup covers ≥50% of symbols
        # (avoids 403 retry storm when NSE session is in bad state)
        effective_max = 0 if (prebuilt_lookup and len(covered_by_lookup) >= len(corp_syms) * 0.5) else max_api_calls
        if effective_max == 0:
            logger.info("Skipping PE API calls — prebuilt lookup has sufficient coverage")

        # Prioritise dividend actions that still have pe=0
        need_pe = [
            a for a in actions
            if a.get("symbol") and not a.get("pe") and
               "dividend" in a.get("subject", "").lower()
        ]
        other_need = [
            a for a in actions
            if a.get("symbol") and not a.get("pe") and
               a not in need_pe
        ]
        candidates = need_pe + other_need

        api_calls = 0
        seen: set = set()
        cache: Dict[str, Dict] = {}
        for a in candidates:
            sym = a.get("symbol", "")
            if not sym:
                continue
            if sym in cache:
                q = cache[sym]
                a["ltp"]         = q["last"]
                a["pct"]         = q["pct"]
                a["pe"]          = q["pe"]
                a["week52_high"] = q["week52_high"]
                a["week52_low"]  = q["week52_low"]
                continue
            if sym in seen or api_calls >= effective_max:
                continue
            seen.add(sym)
            q = self._get_stock_quote_fast(sym)
            if q:
                cache[sym] = q
                a["ltp"]         = q["last"]
                a["pct"]         = q["pct"]
                a["pe"]          = q["pe"]
                a["week52_high"] = q["week52_high"]
                a["week52_low"]  = q["week52_low"]
                api_calls += 1
                time.sleep(0.5)

        enriched_count = sum(1 for a in actions if a.get("ltp"))
        logger.info(
            f"Enrichment done: {enriched_count}/{len(actions)} with LTP, "
            f"{api_calls} API calls made"
        )
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

    def _get_dividend_csv_lookup(self) -> Dict[str, Dict]:
        """Read LTP + PE from upcoming_dividends_latest.csv (built by rebuild script).
        This is the fastest, most reliable enrichment source — zero API calls.
        """
        import csv as csv_mod
        csv_path = config.DATA_DIR / "excel" / "upcoming_dividends_latest.csv"
        lookup: Dict[str, Dict] = {}
        if not csv_path.exists():
            return lookup
        try:
            with open(csv_path, encoding="utf-8") as f:
                for row in csv_mod.DictReader(f):
                    sym = row.get("Symbol", "").strip()
                    try:
                        ltp = float(str(row.get("LTP_INR", "0") or "0").replace(",", ""))
                        pe  = float(str(row.get("PE_Ratio",  "0") or "0").replace(",", ""))
                    except (ValueError, TypeError):
                        ltp, pe = 0.0, 0.0
                    if sym and ltp > 0:
                        lookup[sym] = {"last": ltp, "pct": 0.0, "pe": pe,
                                       "week52_high": 0.0, "week52_low": 0.0}
            logger.info(f"CSV enrichment lookup: {len(lookup)} symbols")
        except Exception as e:
            logger.warning(f"CSV enrichment error: {e}")
        return lookup

    def _get_yahoo_quotes_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch LTP from Yahoo Finance spark API for NSE symbols.

        Uses /v8/finance/spark — no authentication needed.
        Filters out non-equity symbols (bonds, etc.) automatically.
        """
        if not symbols:
            return {}
        # Filter to plausible NSE equity symbols: alpha-start, ≤20 chars.
        # Allow '&' and '-' (e.g., M&M, M&MFIN, L&TFH).
        equity_syms = [
            s for s in symbols
            if s and s[0].isalpha() and len(s) <= 20 and re.match(r"^[A-Za-z][A-Za-z0-9&.-]*$", s)
        ]
        if not equity_syms:
            return {}
        lookup: Dict[str, Dict] = {}
        from urllib.parse import quote as _url_quote

        def _yf_sym(sym: str) -> str:
            return f"{_url_quote(sym, safe='')}.NS"

        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        batch_size = 20   # Yahoo Finance spark supports ~20 symbols reliably
        for i in range(0, len(equity_syms), batch_size):
            batch   = equity_syms[i : i + batch_size]
            yf_syms = ",".join(_yf_sym(s) for s in batch)
            url     = (
                "https://query1.finance.yahoo.com/v8/finance/spark"
                f"?symbols={yf_syms}&range=1d&interval=1d&includePrePost=false"
            )
            try:
                resp = requests.get(
                    url, timeout=15, verify=False,
                    headers={"User-Agent": ua, "Accept": "application/json"},
                )
                if resp.status_code == 400:
                    # Try even smaller sub-batches on 400
                    for sub_start in range(0, len(batch), 10):
                        sub = batch[sub_start : sub_start + 10]
                        sub_url = (
                            "https://query1.finance.yahoo.com/v8/finance/spark"
                            f"?symbols={','.join(_yf_sym(s) for s in sub)}"
                            "&range=1d&interval=1d&includePrePost=false"
                        )
                        try:
                            r2 = requests.get(sub_url, timeout=10, verify=False,
                                              headers={"User-Agent": ua})
                            if r2.status_code == 200:
                                for yf_sym, item in r2.json().items():
                                    nse_sym = yf_sym.replace(".NS", "")
                                    closes  = item.get("close") or []
                                    ltp     = float(closes[-1]) if closes else 0.0
                                    prev    = float(item.get("chartPreviousClose") or 0)
                                    pct     = round((ltp - prev) / prev * 100, 2) if prev > 0 else 0.0
                                    if nse_sym and ltp > 0:
                                        lookup[nse_sym] = {
                                            "last": ltp, "pct": pct,
                                            "pe": 0.0, "week52_high": 0.0, "week52_low": 0.0,
                                        }
                        except Exception:
                            pass
                        time.sleep(0.2)
                    continue
                if resp.status_code != 200:
                    logger.warning(f"Yahoo spark returned {resp.status_code}")
                    continue
                for yf_sym, item in resp.json().items():
                    nse_sym = yf_sym.replace(".NS", "").replace(".BO", "")
                    closes  = item.get("close") or []
                    ltp     = float(closes[-1]) if closes else 0.0
                    prev    = float(item.get("chartPreviousClose") or 0)
                    pct     = round((ltp - prev) / prev * 100, 2) if prev > 0 else 0.0
                    if nse_sym and ltp > 0:
                        lookup[nse_sym] = {
                            "last": ltp, "pct": pct,
                            "pe": 0.0, "week52_high": 0.0, "week52_low": 0.0,
                        }
            except Exception as e:
                logger.warning(f"Yahoo spark batch failed: {e}")
            if i + batch_size < len(equity_syms):
                time.sleep(0.3)
        logger.info(f"Yahoo Finance spark enrichment: {len(lookup)}/{len(equity_syms)} symbols")
        return lookup

    def _get_mcx_driver_quotes(self) -> Dict[str, Dict]:
        """Fetch global commodity futures proxies that often drive MCX-linked stocks.

        Probe confirmed: range=1d returns empty close[] on weekends/off-hours.
        range=5d always returns the last few closes — use the most recent.
        chartPreviousClose is used for % change when prev close is available.
        """
        mapping = {
            "GC=F": "Gold Futures",
            "SI=F": "Silver Futures",
            "CL=F": "Crude Oil Futures",
            "NG=F": "Natural Gas Futures",
        }
        syms = ",".join(mapping.keys())
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
        hdr = {"User-Agent": ua, "Accept": "application/json"}
        out: Dict[str, Dict] = {}
        try:
            # range=5d gives last N closes even on weekends/holidays
            url = (
                "https://query1.finance.yahoo.com/v8/finance/spark"
                f"?symbols={syms}&range=5d&interval=1d&includePrePost=false"
            )
            resp = requests.get(url, timeout=12, verify=False, headers=hdr)
            if resp.status_code == 200:
                raw = resp.json()
                for sym, item in raw.items():
                    if not isinstance(item, dict):
                        continue
                    closes = [c for c in (item.get("close") or []) if c is not None]
                    prev_close = item.get("chartPreviousClose")
                    if not closes:
                        # Try to fall back to chartPreviousClose alone
                        if prev_close:
                            closes = [float(prev_close)]
                        else:
                            continue
                    last = float(closes[-1])
                    # Use second-to-last as prev if chartPreviousClose not set
                    prev = float(prev_close) if prev_close else (float(closes[-2]) if len(closes) >= 2 else 0.0)
                    pct = round((last - prev) / prev * 100, 2) if prev > 0 else 0.0
                    out[sym] = {
                        "name": mapping.get(sym, sym),
                        "last": round(last, 3),
                        "pct": pct,
                    }
            if out:
                logger.info(f"MCX driver proxies via spark-5d: {len(out)}")
                return out

            # Fallback: per-symbol chart endpoint (no auth, reliable)
            for sym in mapping:
                try:
                    r = requests.get(
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d",
                        headers=hdr, timeout=10, verify=False,
                    )
                    if r.status_code == 200:
                        meta = r.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
                        last = float(meta.get("regularMarketPrice") or 0)
                        prev = float(meta.get("previousClose") or meta.get("chartPreviousClose") or 0)
                        pct = round((last - prev) / prev * 100, 2) if (last > 0 and prev > 0) else 0.0
                        if last > 0:
                            out[sym] = {"name": mapping[sym], "last": round(last, 3), "pct": pct}
                except Exception:
                    pass
            if out:
                logger.info(f"MCX driver proxies via chart: {len(out)}")
                return out

            # Vendor fallback (non-Yahoo): Stooq commodity futures feed
            stooq_map = {
                "gc.f": "Gold Futures",
                "si.f": "Silver Futures",
                "cl.f": "Crude Oil Futures",
                "ng.f": "Natural Gas Futures",
            }
            stooq_syms = ",".join(stooq_map.keys())
            stooq_url = (
                "https://stooq.com/q/l/?s="
                f"{stooq_syms}&f=sd2t2ohlcv&h&e=csv"
            )
            stooq_resp = requests.get(
                stooq_url,
                timeout=12,
                verify=False,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv"},
            )
            if stooq_resp.status_code == 200 and stooq_resp.text.strip():
                import csv as _csv
                rows = _csv.DictReader(stooq_resp.text.splitlines())
                for row in rows:
                    sym = str(row.get("Symbol", "")).strip().lower()
                    if sym not in stooq_map:
                        continue
                    try:
                        close_v = float(row.get("Close") or 0)
                        open_v = float(row.get("Open") or 0)
                    except (ValueError, TypeError):
                        continue
                    if close_v <= 0:
                        continue
                    pct_v = round((close_v - open_v) / open_v * 100, 2) if open_v > 0 else 0.0
                    out[sym.upper()] = {
                        "name": stooq_map[sym],
                        "last": close_v,
                        "pct": pct_v,
                    }
            logger.info(f"MCX driver proxies: {len(out)}")
        except Exception as e:
            logger.warning(f"MCX proxy quotes error: {e}")
        return out

    def _get_yahoo_spark_quotes(self, symbols: List[str], range_: str = "5d", interval: str = "1d") -> Dict[str, Dict]:
        """Fetch Yahoo spark quotes for symbols and return normalized map.

        Returns: {symbol: {last, prev, pct}}
        """
        if not symbols:
            return {}

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        try:
            resp = requests.get(
                config.YAHOO_SPARK_URL,
                params={
                    "symbols": ",".join(symbols),
                    "range": range_,
                    "interval": interval,
                    "includePrePost": "false",
                },
                headers=headers,
                timeout=12,
                verify=False,
            )
            if resp.status_code != 200:
                logger.warning(f"Yahoo spark quote fetch returned {resp.status_code}")
                return {}

            raw = resp.json() if isinstance(resp.json(), dict) else {}
            out: Dict[str, Dict] = {}
            for sym, item in raw.items():
                if not isinstance(item, dict):
                    continue
                closes = [c for c in (item.get("close") or []) if c is not None]
                if not closes:
                    continue
                last = float(closes[-1])
                prev_raw = item.get("chartPreviousClose")
                prev = float(prev_raw) if prev_raw else (float(closes[-2]) if len(closes) >= 2 else 0.0)
                pct = round((last - prev) / prev * 100, 2) if prev > 0 else 0.0
                out[sym] = {
                    "last": round(last, 4),
                    "prev": round(prev, 4) if prev > 0 else 0.0,
                    "pct": pct,
                }
            return out
        except Exception as e:
            logger.warning(f"Yahoo spark quotes error: {e}")
            return {}

    def get_global_indices(self) -> Dict[str, Dict]:
        """Fetch key global equity indices via Yahoo spark."""
        symbol_map = config.GLOBAL_INDEX_SYMBOLS
        raw = self._get_yahoo_spark_quotes(list(symbol_map.values()), range_="5d", interval="1d")
        out: Dict[str, Dict] = {}
        for name, sym in symbol_map.items():
            q = raw.get(sym)
            if not q:
                continue
            out[name] = {
                "symbol": sym,
                "last": q.get("last", 0.0),
                "pct": q.get("pct", 0.0),
            }
        logger.info(f"Global indices: {len(out)}/{len(symbol_map)}")
        return out

    def get_global_sentiment(self) -> Dict[str, Any]:
        """Fetch Fear & Greed + macro drivers (DXY, Brent)."""
        out: Dict[str, Any] = {
            "fear_greed": None,
            "macro": {},
        }

        # CNN Fear & Greed (free endpoint)
        fg_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cnn.com/markets/fear-and-greed",
            "Origin": "https://www.cnn.com",
        }
        try:
            fg_resp = requests.get(
                config.CNN_FEAR_GREED_URL,
                headers=fg_headers,
                timeout=10,
                verify=False,
            )
            if fg_resp.status_code == 200:
                fg = fg_resp.json() if isinstance(fg_resp.json(), dict) else {}
                score = fg.get("score")
                rating = fg.get("rating", "")
                prev_close = fg.get("previous_close")
                if isinstance(score, (int, float)):
                    out["fear_greed"] = {
                        "score": round(float(score), 2),
                        "rating": str(rating or "").strip(),
                        "previous_close": float(prev_close) if isinstance(prev_close, (int, float)) else None,
                        "timestamp": fg.get("timestamp", ""),
                    }
            else:
                logger.warning(f"Fear & Greed endpoint returned {fg_resp.status_code}")
        except Exception as e:
            logger.warning(f"Fear & Greed fetch failed: {e}")

        # DXY + Brent from Yahoo
        macro_map = config.GLOBAL_MACRO_SYMBOLS
        macro_raw = self._get_yahoo_spark_quotes(list(macro_map.values()), range_="5d", interval="1d")
        for name, sym in macro_map.items():
            q = macro_raw.get(sym)
            if not q:
                continue
            out["macro"][name] = {
                "symbol": sym,
                "last": q.get("last", 0.0),
                "pct": q.get("pct", 0.0),
            }

        return out

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

    def _get_nifty500_lookup(self) -> Dict[str, Dict]:
        """Fetch NIFTY 500 stocks in a single API call — used as enrichment fallback.
        Returns symbol→{last, pct, week52_high, week52_low} dict.
        """
        url = self._url("/api/equity-stockIndices?index=NIFTY%20500")
        raw = self.nse.api_get(url)
        if not raw or not isinstance(raw, dict):
            logger.warning("NIFTY 500 enrichment lookup failed")
            return {}
        lookup: Dict[str, Dict] = {}
        try:
            for item in raw.get("data", []):
                sym = item.get("symbol", "")
                ltp = item.get("lastPrice", 0) or 0
                if sym and ltp > 0:
                    lookup[sym] = {
                        "last":        float(ltp),
                        "pct":         item.get("pChange", 0) or 0,
                        "week52_high": item.get("yearHigh", 0) or 0,
                        "week52_low":  item.get("yearLow",  0) or 0,
                    }
            logger.info(f"NIFTY 500 enrichment lookup: {len(lookup)} symbols")
        except Exception as e:
            logger.warning(f"NIFTY 500 lookup parse error: {e}")
        return lookup

    # ── FULL SNAPSHOT ────────────────────────────────────────────────────────

    def get_snapshot(
        self,
        include_sectors: bool = True,
        include_options: bool = True,
        include_preopen: bool = False,
        include_corporate: bool = False,
        include_insider: bool = False,
        include_bulk_deals: bool = False,
        sector_list: List[str] = None,
        include_core: bool = True,
    ) -> Dict:
        feed_health = self._load_feed_health_state()
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "fii_dii": None, "indices": None, "market_status": None,
            "forex": None, "commodities": {},
            "mcx_drivers": {},
            "global_indices": {},
            "global_sentiment": {},
            "quality_lookup": {},
            "sectors": {}, "option_chain": {},
            "preopen": None, "corporate_actions": None,
            "corporate_sources": {},
            "earnings_calendar": [],
            "feed_health": {},
            "insider_trading": None, "bulk_deals": None, "block_deals": None,
            "errors": [],
        }

        if include_core:
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

            # Global phase-3 cues (US/Asia/Europe + fear/greed + DXY/Brent)
            try:
                snapshot["global_indices"] = self.get_global_indices()
            except Exception as e:
                snapshot["errors"].append(f"Global indices: {e}")

            try:
                snapshot["global_sentiment"] = self.get_global_sentiment()
            except Exception as e:
                snapshot["errors"].append(f"Global sentiment: {e}")

            # Commodity ETFs
            try:
                snapshot["commodities"] = self.get_commodity_etfs()
            except Exception as e:
                snapshot["errors"].append(f"Commodities: {e}")
            try:
                snapshot["mcx_drivers"] = self._get_mcx_driver_quotes()
                if snapshot["mcx_drivers"]:
                    self._mark_feed_health(feed_health, "MCX_DRV", "ok", len(snapshot["mcx_drivers"]))
                else:
                    self._mark_feed_health(feed_health, "MCX_DRV", "no-data", 0)
            except Exception as e:
                snapshot["errors"].append(f"MCX drivers: {e}")
                self._mark_feed_health(feed_health, "MCX_DRV", "error", 0, str(e))
            time.sleep(1)

        # In corporate-only mode include_core=False, still fetch MCX drivers
        # so corporate Telegram message can include key commodity-price drivers.
        if include_corporate and not snapshot.get("mcx_drivers"):
            try:
                snapshot["mcx_drivers"] = self._get_mcx_driver_quotes()
                if snapshot["mcx_drivers"]:
                    self._mark_feed_health(feed_health, "MCX_DRV", "ok", len(snapshot["mcx_drivers"]))
                else:
                    self._mark_feed_health(feed_health, "MCX_DRV", "no-data", 0)
            except Exception as e:
                snapshot["errors"].append(f"MCX drivers: {e}")
                self._mark_feed_health(feed_health, "MCX_DRV", "error", 0, str(e))

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

            # Enrich PE/Delivery% for top liquid symbols (bounded API calls)
            try:
                snapshot["quality_lookup"] = self._build_quality_lookup_from_quotes(
                    snapshot.get("sectors", {}),
                    max_symbols=24,
                )
            except Exception as e:
                snapshot["errors"].append(f"Quality lookup: {e}")

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

        # Corporate actions (daily, once in evening) — NSE + BSE merged
        if include_corporate:
            try:
                nse_actions = self.get_corporate_actions() or []
                self._mark_feed_health(feed_health, "NSE_CA", "ok" if nse_actions else "no-data", len(nse_actions))
                nse_board = self.get_nse_board_meetings() or []
                self._mark_feed_health(feed_health, "NSE_BM", "ok" if nse_board else "no-data", len(nse_board))
                nse_ann = self.get_nse_major_announcements() or []
                self._mark_feed_health(feed_health, "NSE_ANN", "ok" if nse_ann else "no-data", len(nse_ann))
                nse_earnings = self.get_nse_earnings_calendar() or []
                self._mark_feed_health(feed_health, "NSE_ER", "ok" if nse_earnings else "no-data", len(nse_earnings))
                time.sleep(1)
                bse_actions = self.get_bse_corporate_actions() or []
                self._mark_feed_health(feed_health, "BSE_CA", "ok" if bse_actions else "no-data", len(bse_actions))
                csv_actions = self._load_dividend_actions_from_csv(days_ahead=21, max_age_hours=36) or []
                self._mark_feed_health(feed_health, "DIV_CSV", "ok" if csv_actions else "no-data", len(csv_actions))
                # Deduplicate by (symbol, ex_date, subject-prefix)
                seen_keys: Dict[tuple, int] = {}
                merged = []
                for a in nse_actions + nse_board + nse_ann + bse_actions + csv_actions:
                    key = self._corporate_action_key(a)
                    idx = seen_keys.get(key)
                    if idx is None:
                        seen_keys[key] = len(merged)
                        merged.append(a)
                    else:
                        # Preserve dual-source visibility for overlapping records.
                        existing = merged[idx]
                        src_existing = str(existing.get("source", "NSE") or "NSE")
                        src_new = str(a.get("source", "NSE") or "NSE")
                        src_parts = {s.strip() for s in src_existing.split("+") if s.strip()}
                        src_parts.add(src_new)
                        existing["source"] = "+".join(sorted(src_parts))
                snapshot["corporate_actions"] = merged if merged else None
                snapshot["earnings_calendar"] = nse_earnings

                # Live feed safeguard: fill upcoming dividend/buyback gaps from
                # last recent snapshot when exchanges temporarily miss rows.
                cached_actions = self._load_cached_corporate_actions(max_age_hours=72)
                if cached_actions:
                    merged_keys = {self._corporate_action_key(x) for x in merged}
                    patched = 0
                    for ca in cached_actions:
                        subj_l = str(ca.get("subject", "") or "").lower()
                        if not any(k in subj_l for k in ("dividend", "buyback", "buy back", "buy-back")):
                            continue
                        ex_dt = self._parse_action_date(str(ca.get("ex_date", "") or ""))
                        if not ex_dt or ex_dt.date() < today.date() or ex_dt.date() > cutoff.date():
                            continue
                        key = self._corporate_action_key(ca)
                        if key in merged_keys:
                            continue
                        row = dict(ca)
                        src = str(row.get("source", "CACHE") or "CACHE")
                        row["source"] = f"{src}+CACHE" if "CACHE" not in src else src
                        merged.append(row)
                        merged_keys.add(key)
                        patched += 1
                    if patched:
                        logger.info(f"Corporate gap-fill from cache: +{patched} rows")

                source_counts: Dict[str, int] = {}
                for row in merged:
                    src = str(row.get("source", "NSE") or "NSE")
                    source_counts[src] = source_counts.get(src, 0) + 1
                if nse_earnings:
                    source_counts["NSE-ER"] = len(nse_earnings)
                snapshot["corporate_sources"] = source_counts
                logger.info(
                    f"Corporate merged: NSE={len(nse_actions)} NSE-BM={len(nse_board)} "
                    f"NSE-ANN={len(nse_ann)} NSE-ER={len(nse_earnings)} BSE={len(bse_actions)} CSV={len(csv_actions)} "
                    f"final={len(merged)}"
                )
                if not snapshot["corporate_actions"]:
                    # Live-only guarantee: do not inject stale cached corporate data.
                    snapshot["errors"].append("Corporate actions: live sources returned no data")
                # ── Enrichment: build symbol→LTP lookup ──────────────────────
                # Priority: sector data → Yahoo Finance spark → NIFTY 500 bulk → CSV
                enrich_lookup = self._get_sector_stock_lookup(
                    snapshot.get("sectors", {})
                )
                corp_symbols = {a.get("symbol", "") for a in (merged or [])}
                covered = corp_symbols & set(enrich_lookup.keys())

                # Always try Yahoo Finance spark (fast, reliable, no auth)
                uncovered = [s for s in corp_symbols if s and s not in enrich_lookup]
                if uncovered:
                    logger.info(
                        f"Sector covers {len(covered)}/{len(corp_symbols)} — "
                        f"fetching {len(uncovered)} symbols from Yahoo Finance"
                    )
                    yf_lookup = self._get_yahoo_quotes_batch(uncovered)
                    enrich_lookup = {**yf_lookup, **enrich_lookup}  # sector wins
                    time.sleep(0.5)

                # If still many uncovered, try NIFTY 500 (one NSE bulk call)
                still_uncovered = corp_symbols - set(enrich_lookup.keys())
                if len(still_uncovered) > len(corp_symbols) * 0.3:
                    logger.info(f"Trying NIFTY 500 for {len(still_uncovered)} remaining")
                    n500 = self._get_nifty500_lookup()
                    enrich_lookup = {**n500, **enrich_lookup}
                    time.sleep(1)

                # CSV as last resort (covers recently rebuilt dividend list)
                csv_lk = self._get_dividend_csv_lookup()
                enrich_lookup = {**csv_lk, **enrich_lookup}  # live data wins over CSV
                # Enrich using the combined lookup
                if snapshot["corporate_actions"]:
                    snapshot["corporate_actions"] = self.enrich_corporate_actions(
                        snapshot["corporate_actions"],
                        sector_data=None,
                        prebuilt_lookup=enrich_lookup,
                    )
            except Exception as e:
                snapshot["errors"].append(f"Corp actions: {e}")
                self._mark_feed_health(feed_health, "NSE_CA", "error", 0, str(e))
                self._mark_feed_health(feed_health, "BSE_CA", "error", 0, str(e))
            time.sleep(1.5)

        # Insider trading (daily, once in evening)
        if include_insider:
            try:
                snapshot["insider_trading"] = self.get_insider_trading()
            except Exception as e:
                snapshot["errors"].append(f"Insider: {e}")

        # Bulk & block deals (same-day trades, check once per day)
        if include_bulk_deals:
            try:
                snapshot["bulk_deals"] = self.get_bulk_deals()
            except Exception as e:
                snapshot["errors"].append(f"Bulk deals: {e}")
            time.sleep(1.5)
            try:
                snapshot["block_deals"] = self.get_block_deals()
            except Exception as e:
                snapshot["errors"].append(f"Block deals: {e}")

        snapshot["feed_health"] = feed_health
        self._save_feed_health_state(feed_health)

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
