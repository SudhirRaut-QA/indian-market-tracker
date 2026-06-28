import csv
import glob
import re
import time
import argparse
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_screener_html(text: str):
    ltp = None
    pe = None
    divy = None

    m = re.search(r"Current Price\s*₹\s*([0-9,]+(?:\.[0-9]+)?)", text)
    if m:
        ltp = float(m.group(1).replace(",", ""))

    m = re.search(r"Stock P/E\s*([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        pe = float(m.group(1))

    m = re.search(r"Dividend Yield\s*([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if m:
        divy = float(m.group(1))

    if ltp is None and pe is None and divy is None:
        return None
    return {"ltp": ltp, "pe": pe, "divy": divy, "source": "Screener (latest close)"}


def parse_screener(symbol: str):
    urls = (
        f"https://www.screener.in/company/{symbol}/",
        f"https://www.screener.in/company/{symbol}/consolidated/",
    )
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                continue
            parsed = _parse_screener_html(resp.text)
            if parsed is not None:
                return parsed
        except Exception:
            continue
    return None


def parse_yahoo(symbol: str):
    # Fallback for symbols where screener path mapping may fail.
    for suffix in (".NS", ".BO"):
        url = f"https://finance.yahoo.com/quote/{symbol}{suffix}/"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                continue
            text = resp.text

            ltp = None
            pe = None
            divy = None

            m = re.search(r'"regularMarketPrice":\{"raw":([0-9]+(?:\.[0-9]+)?)', text)
            if m:
                ltp = float(m.group(1))

            m = re.search(r'"trailingPE":\{"raw":([0-9]+(?:\.[0-9]+)?)', text)
            if m:
                pe = float(m.group(1))

            m = re.search(r'"dividendYield":\{"raw":([0-9]+(?:\.[0-9]+)?)', text)
            if m:
                divy = float(m.group(1)) * 100.0

            if ltp is None and pe is None and divy is None:
                continue
            return {"ltp": ltp, "pe": pe, "divy": divy, "source": f"Yahoo {suffix} (latest available)"}
        except Exception:
            continue
    return None


def fmt_num(x, decimals=2):
    if x is None:
        return ""
    return f"{x:.{decimals}f}"


def resolve_csv_path(explicit_path: str | None):
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        return path

    candidates = sorted(
        glob.glob(str(SCRIPT_DIR / "upcoming_dividends_full_*.csv")),
        key=lambda p: Path(p).stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No upcoming_dividends_full_*.csv found in data/excel")
    return Path(candidates[0])


def clean_note(note: str):
    note = (note or "").strip()
    if not note:
        return ""

    removable_markers = (
        "Screener (latest close)",
        "Yahoo .NS (latest available)",
        "Yahoo .BO (latest available)",
        "Quote unresolved from Screener/Yahoo in current session",
    )
    parts = [p.strip() for p in note.split(";") if p.strip()]
    parts = [p for p in parts if not any(marker in p for marker in removable_markers)]
    return "; ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Refresh quote fields in dividend CSV")
    parser.add_argument("--csv", dest="csv_path", help="Path to CSV file to refresh")
    parser.add_argument("--sleep", dest="sleep_sec", type=float, default=0.35, help="Delay between symbol fetches")
    args = parser.parse_args()

    csv_path = resolve_csv_path(args.csv_path)

    rows = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        for row in reader:
            rows.append(row)

    for i, row in enumerate(rows, start=1):
        symbol = (row.get("Symbol") or "").strip()
        if not symbol:
            continue

        data = parse_screener(symbol)
        if data is None:
            data = parse_yahoo(symbol)

        if data is not None:
            base_note = clean_note(row.get("Notes", ""))
            if data.get("ltp") is not None:
                row["LTP_INR"] = fmt_num(data["ltp"], 2)
            if data.get("divy") is not None:
                row["Dividend_Yield_Percent"] = fmt_num(data["divy"], 2)
            if data.get("pe") is not None:
                row["PE_Ratio"] = fmt_num(data["pe"], 2)
            src = data.get("source", "")
            row["Notes"] = f"{base_note}; {src}" if base_note else src
        else:
            # Keep unresolved values explicit with reason.
            if row.get("LTP_INR", "").strip().upper() in ("NA", ""):
                row["LTP_INR"] = "UNAVAILABLE"
            if row.get("Dividend_Yield_Percent", "").strip().upper() in ("NA", ""):
                row["Dividend_Yield_Percent"] = "UNAVAILABLE"
            if row.get("PE_Ratio", "").strip().upper() in ("NA", ""):
                row["PE_Ratio"] = "UNAVAILABLE"
            note = clean_note(row.get("Notes", ""))
            unresolved = "Quote unresolved from Screener/Yahoo in current session"
            row["Notes"] = f"{note}; {unresolved}" if note else unresolved

        # Be polite to sources.
        time.sleep(max(0.0, args.sleep_sec))

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"UPDATED_CSV:{csv_path}")


if __name__ == "__main__":
    main()
