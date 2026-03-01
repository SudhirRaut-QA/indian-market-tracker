"""
Excel Manager v3.0 - Market Data Logger with Backup Strategy
===============================================================

Storage Strategy:
- MASTER Excel workbook: data/excel/market_tracker_master.xlsx
  Single continuous file with ALL data (appends each run)
- Daily JSON snapshots: data/snapshots/YYYY/MM/DD/snapshot_HHMMSS.json
- Daily summary: data/daily/YYYY-MM-DD.json (end-of-day aggregate)
- Backup archive: data/backup/backup_YYYY_MM_DD.zip

Sheets in master workbook (all data appends to same file):
 1. Dashboard      — Latest snapshot summary (overwrites each run)
 2. FII_DII        — ALL FII/DII data (one row per run, never deleted)
 3. Indices        — ALL index values (historical log)
 4. Sectors        — ALL sector data (timestamped entries)
 5. Stocks         — Individual stock data from sectors
 6. Commodities    — ALL commodity prices (historical)
 7. Forex          — ALL forex rates (historical)
 8. Options        — ALL PCR, max pain, OI data
 9. Corporate      — Actions log (dividends, splits, bonus)
10. Insider        — Insider trading (PIT) log
11. Block_Deals    — Block deal transactions
12. Bulk_Deals     — Bulk deal transactions
13. Alerts_52W     — 52-week high/low proximity alerts

Data Retention: All sheets append data continuously. Dashboard is the only
sheet that gets overwritten each run. All other sheets keep historical data.
"""

import json
import logging
import os
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.utils import get_column_letter

from . import config

logger = logging.getLogger(__name__)

# ─── Styles ──────────────────────────────────────────────────────────────────

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
SUB_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
SUB_HEADER_FONT = Font(color="FFFFFF", bold=True, size=9)
GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
YELLOW_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
BLUE_FILL = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
BOLD_FONT = Font(bold=True, size=10)
TITLE_FONT = Font(bold=True, size=14, color="1F4E79")


def _get_wb(path: str) -> Workbook:
    """Load existing workbook or create new."""
    if os.path.exists(path):
        return load_workbook(path)
    return Workbook()


def _header_row(ws, cols: List[str], row: int = 1, fill=None, font=None):
    """Write styled header row."""
    fill = fill or HEADER_FILL
    font = font or HEADER_FONT
    for i, col in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=col)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = THIN_BORDER


def _auto_width(ws, min_width: int = 8, max_width: int = 35):
    """Auto-fit column widths (handles merged cells)."""
    for col in ws.columns:
        max_len = 0
        col_letter = None
        for cell in col:
            try:
                if col_letter is None and hasattr(cell, 'column_letter'):
                    col_letter = cell.column_letter
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        if col_letter:
            ws.column_dimensions[col_letter].width = max(
                min_width, min(max_len + 3, max_width)
            )


def _write_cell(ws, row, col, value, fill=None, font=None, fmt=None):
    """Write a styled cell."""
    cell = ws.cell(row=row, column=col, value=value)
    cell.border = THIN_BORDER
    if fill:
        cell.fill = fill
    if font:
        cell.font = font
    if fmt:
        cell.number_format = fmt
    return cell


def _color_cell(cell, value):
    """Color cell green/red based on positive/negative value."""
    if isinstance(value, (int, float)):
        if value > 0:
            cell.fill = GREEN_FILL
        elif value < 0:
            cell.fill = RED_FILL


def _ensure_date_slot_columns(ws, headers: List[str]):
    """Ensure Log Date + Slot columns exist and headers are aligned."""
    if ws.cell(row=1, column=1).value != "Log Date" or ws.cell(row=1, column=2).value != "Slot":
        ws.insert_cols(1, 2)
    if ws.max_column < len(headers):
        ws.insert_cols(ws.max_column + 1, len(headers) - ws.max_column)
    _header_row(ws, headers)


def _upsert_row(ws, key_cols: List[int], key_vals: List[Any], start_row: int = 2) -> int:
    """Find a row by key values; return row index for update or append."""
    for r in range(start_row, ws.max_row + 1):
        if all(ws.cell(row=r, column=c).value == v for c, v in zip(key_cols, key_vals)):
            return r
    return ws.max_row + 1


class ExcelManager:
    """Manages single master Excel workbook - appends all data continuously."""

    def __init__(self, path: str = None):
        # Single master file for all data
        self.master_path = str(config.get_monthly_excel_path())  # Now returns master file
        self.legacy_path = str(config.EXCEL_FILE)
        os.makedirs(os.path.dirname(self.master_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.legacy_path) or ".", exist_ok=True)

    def log_snapshot(self, snapshot: Dict, delta: Optional[Dict] = None, slot_label: str = "Manual Run"):
        """Log all snapshot data to master Excel workbook (appends to existing data)."""
        try:
            wb = _get_wb(self.master_path)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            date_str = datetime.now().strftime("%Y-%m-%d")

            # Core data sheets
            self._log_dashboard(wb, snapshot, delta, ts)
            self._log_fii_dii(wb, snapshot, ts, date_str, slot_label)
            self._log_indices(wb, snapshot, ts, date_str, slot_label)
            self._log_sectors(wb, snapshot, ts, date_str, slot_label)
            self._log_stocks(wb, snapshot, ts)
            self._log_commodities(wb, snapshot, ts, date_str, slot_label)
            self._log_forex(wb, snapshot, ts, date_str, slot_label)

            # Options
            if snapshot.get("option_chain"):
                self._log_options(wb, snapshot, ts, date_str, slot_label)

            # Corporate & Insider
            if snapshot.get("corporate_actions"):
                self._log_corporate(wb, snapshot, date_str)
            if snapshot.get("insider_trading"):
                self._log_insider(wb, snapshot, date_str)

            # Block & Bulk deals
            if snapshot.get("block_deals"):
                self._log_block_deals(wb, snapshot, date_str)
            if snapshot.get("bulk_deals"):
                self._log_bulk_deals(wb, snapshot, date_str)

            # 52W alerts
            if snapshot.get("alerts"):
                self._log_52w_alerts(wb, snapshot, ts)

            # Remove default "Sheet" if empty
            if "Sheet" in wb.sheetnames:
                ws = wb["Sheet"]
                if ws.max_row == 1 and ws.max_column == 1 and not ws.cell(1, 1).value:
                    wb.remove(ws)

            wb.save(self.master_path)
            logger.info(f"Excel saved: {self.master_path} (data appended)")

        except Exception as e:
            logger.error(f"Excel save error: {e}", exc_info=True)

    # ── Dashboard (Summary) ──────────────────────────────────────────────────

    def _log_dashboard(self, wb: Workbook, snapshot: Dict, delta: Optional[Dict], ts: str):
        name = "Dashboard"
        if name in wb.sheetnames:
            wb.remove(wb[name])
        ws = wb.create_sheet(name, 0)

        # Title
        ws.cell(row=1, column=1, value="Indian Market Tracker").font = TITLE_FONT
        ws.cell(row=2, column=1, value=f"Last Updated: {ts}").font = Font(size=10, italic=True)
        ws.merge_cells("A1:F1")
        ws.merge_cells("A2:F2")

        row = 4

        # == FII/DII Summary ==
        fd = snapshot.get("fii_dii")
        if fd:
            ws.cell(row=row, column=1, value="FII/DII Activity").font = BOLD_FONT
            ws.cell(row=row, column=1).fill = BLUE_FILL
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1

            labels = ["", "Buy (Cr)", "Sell (Cr)", "Net (Cr)", "Signal", "Date"]
            for i, l in enumerate(labels, 1):
                _write_cell(ws, row, i, l, fill=SUB_HEADER_FILL, font=SUB_HEADER_FONT)
            row += 1

            fii = fd.get("fii", {})
            _write_cell(ws, row, 1, "FII/FPI", font=BOLD_FONT)
            _write_cell(ws, row, 2, fii.get("buy", 0), fmt="#,##0")
            _write_cell(ws, row, 3, fii.get("sell", 0), fmt="#,##0")
            c = _write_cell(ws, row, 4, fii.get("net", 0), fmt="#,##0")
            _color_cell(c, fii.get("net", 0))
            _write_cell(ws, row, 5, fd.get("signal", ""))
            _write_cell(ws, row, 6, fd.get("date", ""))
            row += 1

            dii = fd.get("dii", {})
            _write_cell(ws, row, 1, "DII", font=BOLD_FONT)
            _write_cell(ws, row, 2, dii.get("buy", 0), fmt="#,##0")
            _write_cell(ws, row, 3, dii.get("sell", 0), fmt="#,##0")
            c = _write_cell(ws, row, 4, dii.get("net", 0), fmt="#,##0")
            _color_cell(c, dii.get("net", 0))
            row += 1

            _write_cell(ws, row, 1, "TOTAL NET", font=BOLD_FONT)
            c = _write_cell(ws, row, 4, fd.get("total_net", 0), fmt="#,##0", font=BOLD_FONT)
            _color_cell(c, fd.get("total_net", 0))
            row += 2

        # == Key Indices ==
        indices = snapshot.get("indices")
        if indices:
            ws.cell(row=row, column=1, value="Key Indices").font = BOLD_FONT
            ws.cell(row=row, column=1).fill = BLUE_FILL
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1

            cols = ["Index", "Last", "Change", "% Change", "Adv", "Dec"]
            for i, c in enumerate(cols, 1):
                _write_cell(ws, row, i, c, fill=SUB_HEADER_FILL, font=SUB_HEADER_FONT)
            row += 1

            # Show top indices
            top_indices = ["NIFTY 50", "NIFTY BANK", "INDIA VIX", "NIFTY IT",
                           "NIFTY PHARMA", "NIFTY METAL", "NIFTY MIDCAP 50"]
            for idx_name in top_indices:
                if idx_name in indices:
                    d = indices[idx_name]
                    short = idx_name.replace("NIFTY ", "")
                    _write_cell(ws, row, 1, short, font=BOLD_FONT)
                    _write_cell(ws, row, 2, d["last"], fmt="#,##0.00")
                    c = _write_cell(ws, row, 3, d["change"], fmt="#,##0.00")
                    _color_cell(c, d["change"])
                    c = _write_cell(ws, row, 4, d["pct"], fmt="0.00%")
                    _color_cell(c, d["pct"])
                    _write_cell(ws, row, 5, d.get("advances", 0))
                    _write_cell(ws, row, 6, d.get("declines", 0))
                    row += 1
            row += 1

        # == Commodities & Forex ==
        comms = snapshot.get("commodities")
        forex = snapshot.get("forex")
        if comms or forex:
            ws.cell(row=row, column=1, value="Commodities & Forex").font = BOLD_FONT
            ws.cell(row=row, column=1).fill = BLUE_FILL
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1

            if comms:
                for sym, d in comms.items():
                    _write_cell(ws, row, 1, sym, font=BOLD_FONT)
                    _write_cell(ws, row, 2, d["last"], fmt="#,##0.00")
                    c = _write_cell(ws, row, 3, d.get("pct", 0), fmt="0.00%")
                    _color_cell(c, d.get("pct", 0))
                    _write_cell(ws, row, 4, f"52H: {d.get('week52_high', 0)}")
                    _write_cell(ws, row, 5, f"52L: {d.get('week52_low', 0)}")
                    row += 1

            if forex:
                _write_cell(ws, row, 1, "USD/INR", font=BOLD_FONT)
                _write_cell(ws, row, 2, forex.get("usdinr", 0), fmt="#,##0.0000")
                _write_cell(ws, row, 3, forex.get("date", ""))
                row += 1
            row += 1

        # == 52W Alerts ==
        alerts = snapshot.get("alerts", {})
        h52 = alerts.get("near_52w_high", [])
        l52 = alerts.get("near_52w_low", [])
        if h52 or l52:
            ws.cell(row=row, column=1, value="52-Week Alerts").font = BOLD_FONT
            ws.cell(row=row, column=1).fill = YELLOW_FILL
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1

            for a in h52[:5]:
                _write_cell(ws, row, 1, f"NEAR 52W HIGH", fill=GREEN_FILL)
                _write_cell(ws, row, 2, a["symbol"], font=BOLD_FONT)
                _write_cell(ws, row, 3, a["last"], fmt="#,##0.00")
                _write_cell(ws, row, 4, f"52H: {a['year_high']}")
                _write_cell(ws, row, 5, f"{a['distance_pct']}% away")
                row += 1

            for a in l52[:5]:
                _write_cell(ws, row, 1, f"NEAR 52W LOW", fill=RED_FILL)
                _write_cell(ws, row, 2, a["symbol"], font=BOLD_FONT)
                _write_cell(ws, row, 3, a["last"], fmt="#,##0.00")
                _write_cell(ws, row, 4, f"52L: {a['year_low']}")
                _write_cell(ws, row, 5, f"{a['distance_pct']}% away")
                row += 1

        _auto_width(ws)

    # ── FII/DII Detail ───────────────────────────────────────────────────────

    def _log_fii_dii(self, wb: Workbook, snapshot: Dict, ts: str, date_str: str, slot_label: str):
        name = "FII_DII"
        fd = snapshot.get("fii_dii")
        if not fd:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Slot", "Timestamp", "Date",
                "FII Buy (Cr)", "FII Sell (Cr)", "FII Net (Cr)",
                "DII Buy (Cr)", "DII Sell (Cr)", "DII Net (Cr)",
                "Total Net (Cr)", "Signal", "Interpretation",
            ])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = "A1:M1"
        else:
            ws = wb[name]
            _ensure_date_slot_columns(ws, [
                "Log Date", "Slot", "Timestamp", "Date",
                "FII Buy (Cr)", "FII Sell (Cr)", "FII Net (Cr)",
                "DII Buy (Cr)", "DII Sell (Cr)", "DII Net (Cr)",
                "Total Net (Cr)", "Signal", "Interpretation",
            ])

        row = _upsert_row(ws, [1, 2], [date_str, slot_label])
        vals = [
            date_str, slot_label, ts, fd.get("date", ""),
            fd["fii"]["buy"], fd["fii"]["sell"], fd["fii"]["net"],
            fd["dii"]["buy"], fd["dii"]["sell"], fd["dii"]["net"],
            fd.get("total_net", 0), fd.get("signal", ""), fd.get("interpretation", ""),
        ]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=i, value=v)
            cell.border = THIN_BORDER
            if i in (7, 10, 11) and isinstance(v, (int, float)):
                _color_cell(cell, v)
        _auto_width(ws)

    # ── Indices Detail ───────────────────────────────────────────────────────

    def _log_indices(self, wb: Workbook, snapshot: Dict, ts: str, date_str: str, slot_label: str):
        name = "Indices"
        indices = snapshot.get("indices")
        if not indices:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Slot", "Timestamp", "Index", "Last", "Change", "% Change",
                "Open", "High", "Low", "Prev Close",
                "Advances", "Declines", "Breadth Ratio",
            ])
            ws.freeze_panes = "C2"
            ws.auto_filter.ref = "A1:N1"
        else:
            ws = wb[name]
            _ensure_date_slot_columns(ws, [
                "Log Date", "Slot", "Timestamp", "Index", "Last", "Change", "% Change",
                "Open", "High", "Low", "Prev Close",
                "Advances", "Declines", "Breadth Ratio",
            ])

        for idx_name, data in indices.items():
            row = _upsert_row(ws, [1, 2, 4], [date_str, slot_label, idx_name])
            try:
                adv = int(data.get("advances", 0) or 0)
                dec = int(data.get("declines", 0) or 0)
            except (ValueError, TypeError):
                adv, dec = 0, 0
            breadth = round(adv / dec, 2) if dec > 0 else 0

            vals = [
                date_str, slot_label, ts, idx_name, data["last"], data["change"], data["pct"],
                data["open"], data["high"], data["low"], data["prev_close"],
                adv, dec, breadth,
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                if i == 7 and isinstance(v, (int, float)):
                    _color_cell(cell, v)

    # ── Sectors Summary ──────────────────────────────────────────────────────

    def _log_sectors(self, wb: Workbook, snapshot: Dict, ts: str, date_str: str, slot_label: str):
        name = "Sectors"
        sectors = snapshot.get("sectors")
        if not sectors:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Slot", "Timestamp", "Sector", "Index Last", "Index %",
                "Stocks", "Top Gainer", "G %", "Top Loser", "L %",
                "Near 52H Count", "Near 52L Count",
                "30d Chg (Avg)", "1Y Chg (Avg)",
            ])
            ws.freeze_panes = "C2"
        else:
            ws = wb[name]
            _ensure_date_slot_columns(ws, [
                "Log Date", "Slot", "Timestamp", "Sector", "Index Last", "Index %",
                "Stocks", "Top Gainer", "G %", "Top Loser", "L %",
                "Near 52H Count", "Near 52L Count",
                "30d Chg (Avg)", "1Y Chg (Avg)",
            ])

        for sect_name, data in sectors.items():
            row = _upsert_row(ws, [1, 2, 4], [date_str, slot_label, sect_name])
            g = data.get("gainers", [{}])[0] if data.get("gainers") else {}
            l = data.get("losers", [{}])[0] if data.get("losers") else {}

            # Average momentum
            all_stocks = data.get("stocks", [])
            avg_30d = 0
            avg_365d = 0
            if all_stocks:
                vals_30 = [s.get("chg_30d", 0) for s in all_stocks if s.get("chg_30d")]
                vals_365 = [s.get("chg_365d", 0) for s in all_stocks if s.get("chg_365d")]
                avg_30d = round(sum(vals_30) / len(vals_30), 2) if vals_30 else 0
                avg_365d = round(sum(vals_365) / len(vals_365), 2) if vals_365 else 0

            vals = [
                date_str, slot_label, ts, sect_name, data.get("index_last", 0), data.get("index_pct", 0),
                data.get("count", 0), g.get("symbol", ""), g.get("pct", 0),
                l.get("symbol", ""), l.get("pct", 0),
                len(data.get("near_52w_high", [])),
                len(data.get("near_52w_low", [])),
                avg_30d, avg_365d,
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                if i == 6 and isinstance(v, (int, float)):
                    _color_cell(cell, v)

    # ── Individual Stocks ────────────────────────────────────────────────────

    def _log_stocks(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "Stocks"
        sectors = snapshot.get("sectors")
        if not sectors:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Timestamp", "Sector", "Symbol", "Last", "Change", "% Change",
                "Volume", "Value (Cr)", "52W High", "52W Low",
                "Near 52H %", "Near 52L %", "30d %", "1Y %",
            ])
            ws.freeze_panes = "D2"
            ws.auto_filter.ref = "A1:N1"
        else:
            ws = wb[name]

        for sect_name, data in sectors.items():
            short = sect_name.replace("NIFTY ", "")
            for s in data.get("stocks", []):
                row = ws.max_row + 1
                vals = [
                    ts, short, s["symbol"], s["last"], s["change"], s["pct"],
                    s["volume"], s["value_cr"], s["year_high"], s["year_low"],
                    s.get("near_52h", 0), s.get("near_52l", 0),
                    s.get("chg_30d", 0), s.get("chg_365d", 0),
                ]
                for i, v in enumerate(vals, 1):
                    cell = ws.cell(row=row, column=i, value=v)
                    cell.border = THIN_BORDER
                    if i == 6 and isinstance(v, (int, float)):
                        _color_cell(cell, v)

    # ── Commodities ──────────────────────────────────────────────────────────

    def _log_commodities(self, wb: Workbook, snapshot: Dict, ts: str, date_str: str, slot_label: str):
        name = "Commodities"
        comms = snapshot.get("commodities")
        if not comms:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Slot", "Timestamp", "Symbol", "Last", "Change", "% Change",
                "52W High", "52W Low",
            ])
            ws.freeze_panes = "C2"
        else:
            ws = wb[name]
            _ensure_date_slot_columns(ws, [
                "Log Date", "Slot", "Timestamp", "Symbol", "Last", "Change", "% Change",
                "52W High", "52W Low",
            ])

        for sym, data in comms.items():
            row = _upsert_row(ws, [1, 2, 4], [date_str, slot_label, sym])
            vals = [
                date_str, slot_label, ts, sym, data["last"], data["change"], data["pct"],
                data.get("week52_high", 0), data.get("week52_low", 0),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                if i == 7 and isinstance(v, (int, float)):
                    _color_cell(cell, v)

    # ── Forex ────────────────────────────────────────────────────────────────

    def _log_forex(self, wb: Workbook, snapshot: Dict, ts: str, date_str: str, slot_label: str):
        name = "Forex"
        forex = snapshot.get("forex")
        if not forex:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Slot", "Timestamp", "USD/INR", "USD/EUR", "USD/GBP", "USD/JPY", "API Date",
            ])
            ws.freeze_panes = "A2"
        else:
            ws = wb[name]
            _ensure_date_slot_columns(ws, [
                "Log Date", "Slot", "Timestamp", "USD/INR", "USD/EUR", "USD/GBP", "USD/JPY", "API Date",
            ])

        row = _upsert_row(ws, [1, 2], [date_str, slot_label])
        vals = [
            date_str, slot_label, ts, forex.get("usdinr", 0), forex.get("usdeur", 0),
            forex.get("usdgbp", 0), forex.get("usdjpy", 0), forex.get("date", ""),
        ]
        for i, v in enumerate(vals, 1):
            ws.cell(row=row, column=i, value=v).border = THIN_BORDER

    # ── Options ──────────────────────────────────────────────────────────────

    def _log_options(self, wb: Workbook, snapshot: Dict, ts: str, date_str: str, slot_label: str):
        name = "Options"
        oc = snapshot.get("option_chain")
        if not oc:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Slot", "Timestamp", "Symbol", "PCR (OI)", "PCR (Vol)", "Signal",
                "Max Pain", "CE OI Total", "PE OI Total",
                "Top CE Strike", "Top PE Strike",
            ])
            ws.freeze_panes = "C2"
        else:
            ws = wb[name]
            _ensure_date_slot_columns(ws, [
                "Log Date", "Slot", "Timestamp", "Symbol", "PCR (OI)", "PCR (Vol)", "Signal",
                "Max Pain", "CE OI Total", "PE OI Total",
                "Top CE Strike", "Top PE Strike",
            ])

        for sym, data in oc.items():
            row = _upsert_row(ws, [1, 2, 4], [date_str, slot_label, sym])
            top_ce_str = ", ".join(f"{s['strike']}" for s in data.get("top_ce", [])[:3])
            top_pe_str = ", ".join(f"{s['strike']}" for s in data.get("top_pe", [])[:3])
            vals = [
                date_str, slot_label, ts, sym, data.get("pcr_oi", 0), data.get("pcr_vol", 0),
                data.get("signal", ""), data.get("max_pain", 0),
                data.get("ce_oi_total", 0), data.get("pe_oi_total", 0),
                top_ce_str, top_pe_str,
            ]
            for i, v in enumerate(vals, 1):
                ws.cell(row=row, column=i, value=v).border = THIN_BORDER

    # ── Corporate Actions (Enhanced) ─────────────────────────────────────────

    def _log_corporate(self, wb: Workbook, snapshot: Dict, date_str: str):
        name = "Corporate"
        actions = snapshot.get("corporate_actions", [])
        if not actions:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Type", "Symbol", "Company", "Subject",
                "Ex-Date", "Record Date", "BC Start", "BC End",
                "LTP", "% Change", "PE Ratio", "Div Amount",
                "Div Yield %", "52W High", "52W Low", "Delivery %",
            ])
            ws.freeze_panes = "D2"
            ws.auto_filter.ref = "A1:Q1"
        else:
            ws = wb[name]

        for a in actions:
            row = ws.max_row + 1
            vals = [
                date_str,
                a.get("action_type", "other"),
                a["symbol"],
                a["company"][:40],
                a["subject"][:60],
                a["ex_date"],
                a.get("record_date", ""),
                a.get("bc_start", ""),
                a.get("bc_end", ""),
                a.get("ltp", ""),
                a.get("pct_change", ""),
                a.get("pe_ratio", ""),
                a.get("dividend_amount", ""),
                a.get("dividend_yield", ""),
                a.get("week52_high", ""),
                a.get("week52_low", ""),
                a.get("delivery_pct", ""),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                # Highlight high yield dividends
                if i == 14 and isinstance(v, (int, float)) and v > 3:
                    cell.fill = GREEN_FILL
        _auto_width(ws)

    # ── Insider Trading ──────────────────────────────────────────────────────

    def _log_insider(self, wb: Workbook, snapshot: Dict, date_str: str):
        name = "Insider"
        trades = snapshot.get("insider_trading", [])
        if not trades:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Symbol", "Company", "Acquirer", "Relation",
                "Buy Value", "Sell Value", "Net Value", "Trade Date",
            ])
            ws.freeze_panes = "C2"
            ws.auto_filter.ref = "A1:I1"
        else:
            ws = wb[name]

        for t in trades[:30]:
            row = ws.max_row + 1
            net_val = t["buy_value"] - t["sell_value"]
            vals = [
                date_str, t["symbol"], t["company"][:30], t["acquirer"][:30],
                t.get("relation", ""), t["buy_value"], t["sell_value"],
                net_val, t["date"],
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                if i == 8 and isinstance(v, (int, float)):
                    _color_cell(cell, v)

    # ── Block Deals ──────────────────────────────────────────────────────────

    def _log_block_deals(self, wb: Workbook, snapshot: Dict, date_str: str):
        name = "Block_Deals"
        deals = snapshot.get("block_deals", [])
        if not deals:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Symbol", "Client", "Buy/Sell",
                "Quantity", "Price", "Value (Cr)", "Deal Date",
            ])
            ws.freeze_panes = "C2"
        else:
            ws = wb[name]

        for d in deals:
            row = ws.max_row + 1
            vals = [
                date_str, d["symbol"], d["client"][:40], d["buy_sell"],
                d["quantity"], d["price"], d["value_cr"], d["date"],
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                if i == 4:
                    cell.fill = GREEN_FILL if "buy" in str(v).lower() else RED_FILL

    # ── Bulk Deals ───────────────────────────────────────────────────────────

    def _log_bulk_deals(self, wb: Workbook, snapshot: Dict, date_str: str):
        name = "Bulk_Deals"
        deals = snapshot.get("bulk_deals", [])
        if not deals:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Symbol", "Client", "Buy/Sell",
                "Quantity", "Price", "Value (Cr)", "Deal Date",
            ])
            ws.freeze_panes = "C2"
        else:
            ws = wb[name]

        for d in deals:
            row = ws.max_row + 1
            vals = [
                date_str, d["symbol"], d["client"][:40], d["buy_sell"],
                d["quantity"], d["price"], d["value_cr"], d["date"],
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER

    # ── 52W Alerts ───────────────────────────────────────────────────────────

    def _log_52w_alerts(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "Alerts_52W"
        alerts = snapshot.get("alerts", {})
        highs = alerts.get("near_52w_high", [])
        lows = alerts.get("near_52w_low", [])
        if not highs and not lows:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Timestamp", "Alert Type", "Symbol", "Sector",
                "LTP", "52W Level", "Distance %", "Today %",
            ])
            ws.freeze_panes = "C2"
        else:
            ws = wb[name]

        for a in highs:
            row = ws.max_row + 1
            vals = [
                ts, "NEAR 52W HIGH", a["symbol"], a.get("sector", ""),
                a["last"], a["year_high"], a["distance_pct"], a.get("pct_today", 0),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
            ws.cell(row=row, column=2).fill = GREEN_FILL

        for a in lows:
            row = ws.max_row + 1
            vals = [
                ts, "NEAR 52W LOW", a["symbol"], a.get("sector", ""),
                a["last"], a["year_low"], a["distance_pct"], a.get("pct_today", 0),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
            ws.cell(row=row, column=2).fill = RED_FILL


# ═════════════════════════════════════════════════════════════════════════════
# BACKUP & ARCHIVAL
# ═════════════════════════════════════════════════════════════════════════════

class BackupManager:
    """Handles data backup, archival, and daily summaries."""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.backup_dir = config.BACKUP_DIR
        self.daily_dir = config.DAILY_DIR
        self.snapshot_dir = config.SNAPSHOT_DIR

    def save_daily_summary(self, snapshot: Dict):
        """Save end-of-day summary as a compact JSON."""
        try:
            self.daily_dir.mkdir(parents=True, exist_ok=True)
            path = config.get_daily_summary_path()

            summary = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "timestamp": snapshot.get("timestamp", ""),
            }

            # FII/DII
            fd = snapshot.get("fii_dii")
            if fd:
                summary["fii_dii"] = {
                    "fii_net": fd["fii"]["net"],
                    "dii_net": fd["dii"]["net"],
                    "total_net": fd.get("total_net", 0),
                    "signal": fd.get("signal", ""),
                }

            # Top indices
            indices = snapshot.get("indices", {})
            if indices:
                summary["indices"] = {}
                for name in ["NIFTY 50", "NIFTY BANK", "INDIA VIX"]:
                    if name in indices:
                        summary["indices"][name] = {
                            "last": indices[name]["last"],
                            "pct": indices[name]["pct"],
                        }

            # Sector summary
            sectors = snapshot.get("sectors", {})
            if sectors:
                summary["sector_performance"] = {}
                for name, data in sectors.items():
                    summary["sector_performance"][name] = {
                        "index_pct": data.get("index_pct", 0),
                        "stocks_count": data.get("count", 0),
                        "near_52h": len(data.get("near_52w_high", [])),
                        "near_52l": len(data.get("near_52w_low", [])),
                    }

            # Forex
            forex = snapshot.get("forex")
            if forex:
                summary["forex"] = {"usdinr": forex.get("usdinr", 0)}

            # Commodities
            comms = snapshot.get("commodities", {})
            if comms:
                summary["commodities"] = {
                    sym: {"last": d["last"], "pct": d["pct"]}
                    for sym, d in comms.items()
                }

            # Alert counts
            alerts = snapshot.get("alerts", {})
            summary["alert_counts"] = {
                "near_52w_high": len(alerts.get("near_52w_high", [])),
                "near_52w_low": len(alerts.get("near_52w_low", [])),
            }

            # Corporate actions count
            if snapshot.get("corporate_actions"):
                summary["corporate_actions_count"] = len(snapshot["corporate_actions"])

            # Write
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Daily summary saved: {path}")
            return str(path)

        except Exception as e:
            logger.error(f"Daily summary error: {e}")
            return None

    def create_backup(self, days_old: int = 0) -> Optional[str]:
        """Create zip backup of data directory.

        Args:
            days_old: 0 = backup today's data, >0 = backup data from N days ago
        """
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            target_date = datetime.now() - timedelta(days=days_old)
            date_str = target_date.strftime("%Y_%m_%d")
            zip_name = f"backup_{date_str}.zip"
            zip_path = self.backup_dir / zip_name

            if zip_path.exists():
                logger.info(f"Backup already exists: {zip_path}")
                return str(zip_path)

            files_to_backup = []

            # Daily summary
            daily_path = self.daily_dir / f"{target_date.strftime('%Y-%m-%d')}.json"
            if daily_path.exists():
                files_to_backup.append(daily_path)

            # Snapshots for the target date
            snap_dir = (self.snapshot_dir / target_date.strftime("%Y")
                        / target_date.strftime("%m") / target_date.strftime("%d"))
            if snap_dir.exists():
                for f in snap_dir.glob("*.json"):
                    files_to_backup.append(f)

            # Monthly Excel (always include current month's)
            excel_path = config.get_monthly_excel_path()
            if excel_path.exists():
                files_to_backup.append(excel_path)

            if not files_to_backup:
                logger.warning(f"No files to backup for {date_str}")
                return None

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fp in files_to_backup:
                    arcname = str(fp.relative_to(self.data_dir))
                    zf.write(fp, arcname)

            size_mb = zip_path.stat().st_size / (1024 * 1024)
            logger.info(f"Backup created: {zip_path} ({size_mb:.1f} MB, {len(files_to_backup)} files)")
            return str(zip_path)

        except Exception as e:
            logger.error(f"Backup error: {e}")
            return None

    def cleanup_old_snapshots(self, keep_days: int = 30):
        """Remove snapshot JSON files older than N days."""
        try:
            cutoff = datetime.now() - timedelta(days=keep_days)
            removed = 0
            for year_dir in self.snapshot_dir.glob("*"):
                if not year_dir.is_dir():
                    continue
                for month_dir in year_dir.glob("*"):
                    if not month_dir.is_dir():
                        continue
                    for day_dir in month_dir.glob("*"):
                        if not day_dir.is_dir():
                            continue
                        try:
                            dir_date = datetime.strptime(
                                f"{year_dir.name}-{month_dir.name}-{day_dir.name}",
                                "%Y-%m-%d"
                            )
                            if dir_date < cutoff:
                                shutil.rmtree(day_dir)
                                removed += 1
                        except ValueError:
                            pass

            logger.info(f"Cleaned up {removed} old snapshot directories (>{keep_days} days)")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def get_storage_stats(self) -> Dict:
        """Get data storage statistics."""
        stats = {}
        try:
            # Count files and sizes per directory
            for name, path in [
                ("snapshots", self.snapshot_dir),
                ("excel", config.EXCEL_DIR),
                ("daily", self.daily_dir),
                ("backup", self.backup_dir),
            ]:
                if path.exists():
                    files = list(path.rglob("*"))
                    file_count = sum(1 for f in files if f.is_file())
                    total_size = sum(f.stat().st_size for f in files if f.is_file())
                    stats[name] = {
                        "files": file_count,
                        "size_mb": round(total_size / (1024 * 1024), 2),
                    }
                else:
                    stats[name] = {"files": 0, "size_mb": 0}
        except Exception as e:
            logger.error(f"Stats error: {e}")

        return stats
