"""
Excel Manager - Market Data Logger
====================================

Logs all scraped data to Excel with multiple sheets:
- FII_DII: Daily FII/DII data with running totals
- Indices: Daily index values
- Sectors: Daily sector performance
- Commodities: Gold, Silver, Oil ETF prices
- Forex: USD/INR daily
- Corporate: Actions log
- Insider: Insider trading log
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from . import config

logger = logging.getLogger(__name__)

# Styles
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


def _get_wb(path: str) -> Workbook:
    if os.path.exists(path):
        return load_workbook(path)
    return Workbook()


def _header_row(ws, cols: List[str], row: int = 1):
    for i, col in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        cell.border = THIN_BORDER


def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 3, 30)


class ExcelManager:
    """Manages Excel workbook for market data logging."""

    def __init__(self, path: str = None):
        self.path = path or config.EXCEL_FILE
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Also ensure excel dir exists
        os.makedirs(config.EXCEL_DIR, exist_ok=True)

    def log_snapshot(self, snapshot: Dict, delta: Optional[Dict] = None):
        try:
            wb = _get_wb(self.path)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            date = datetime.now().strftime("%Y-%m-%d")

            self._log_fii_dii(wb, snapshot, ts)
            self._log_indices(wb, snapshot, ts)
            self._log_sectors(wb, snapshot, ts)
            self._log_commodities(wb, snapshot, ts)
            self._log_forex(wb, snapshot, ts)

            if snapshot.get("corporate_actions"):
                self._log_corporate(wb, snapshot, date)
            if snapshot.get("insider_trading"):
                self._log_insider(wb, snapshot, date)

            # Remove default sheet if empty
            if "Sheet" in wb.sheetnames:
                ws = wb["Sheet"]
                if ws.max_row == 1 and ws.max_column == 1 and not ws.cell(1, 1).value:
                    wb.remove(ws)

            wb.save(self.path)
            logger.info(f"Excel saved: {self.path}")
        except Exception as e:
            logger.error(f"Excel save error: {e}")

    def _log_fii_dii(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "FII_DII"
        fd = snapshot.get("fii_dii")
        if not fd:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Timestamp", "Date", "FII Buy (Cr)", "FII Sell (Cr)", "FII Net (Cr)",
                "DII Buy (Cr)", "DII Sell (Cr)", "DII Net (Cr)",
                "Total Net (Cr)", "Signal", "Interpretation",
            ])
        else:
            ws = wb[name]

        row = ws.max_row + 1
        vals = [
            ts, fd.get("date", ""),
            fd["fii"]["buy"], fd["fii"]["sell"], fd["fii"]["net"],
            fd["dii"]["buy"], fd["dii"]["sell"], fd["dii"]["net"],
            fd.get("total_net", 0), fd.get("signal", ""), fd.get("interpretation", ""),
        ]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=i, value=v)
            cell.border = THIN_BORDER
            # Color net values
            if i in (5, 8, 9) and isinstance(v, (int, float)):
                cell.fill = GREEN_FILL if v > 0 else RED_FILL if v < 0 else PatternFill()
        _auto_width(ws)

    def _log_indices(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "Indices"
        indices = snapshot.get("indices")
        if not indices:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Timestamp", "Index", "Last", "Change", "% Change",
                "Open", "High", "Low", "Prev Close",
                "Advances", "Declines",
            ])
        else:
            ws = wb[name]

        for idx_name, data in indices.items():
            row = ws.max_row + 1
            vals = [
                ts, idx_name, data["last"], data["change"], data["pct"],
                data["open"], data["high"], data["low"], data["prev_close"],
                data.get("advances", 0), data.get("declines", 0),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
                if i == 5 and isinstance(v, (int, float)):
                    cell.fill = GREEN_FILL if v > 0 else RED_FILL if v < 0 else PatternFill()

    def _log_sectors(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "Sectors"
        sectors = snapshot.get("sectors")
        if not sectors:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Timestamp", "Sector", "Index Last", "Index %",
                "Stocks", "Top Gainer", "G %", "Top Loser", "L %",
            ])
        else:
            ws = wb[name]

        for sect_name, data in sectors.items():
            row = ws.max_row + 1
            g = data.get("gainers", [{}])[0] if data.get("gainers") else {}
            l = data.get("losers", [{}])[0] if data.get("losers") else {}
            vals = [
                ts, sect_name, data.get("index_last", 0), data.get("index_pct", 0),
                data.get("count", 0), g.get("symbol", ""), g.get("pct", 0),
                l.get("symbol", ""), l.get("pct", 0),
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER

    def _log_commodities(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "Commodities"
        comms = snapshot.get("commodities")
        if not comms:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Timestamp", "Symbol", "Last", "Change", "% Change",
                "52W High", "52W Low",
            ])
        else:
            ws = wb[name]

        for sym, data in comms.items():
            row = ws.max_row + 1
            vals = [
                ts, sym, data["last"], data["change"], data["pct"],
                data.get("week52_high", 0), data.get("week52_low", 0),
            ]
            for i, v in enumerate(vals, 1):
                ws.cell(row=row, column=i, value=v).border = THIN_BORDER

    def _log_forex(self, wb: Workbook, snapshot: Dict, ts: str):
        name = "Forex"
        forex = snapshot.get("forex")
        if not forex:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, ["Timestamp", "USD/INR", "USD/EUR", "USD/GBP", "USD/JPY", "API Date"])
        else:
            ws = wb[name]

        row = ws.max_row + 1
        vals = [
            ts, forex.get("usdinr", 0), forex.get("usdeur", 0),
            forex.get("usdgbp", 0), forex.get("usdjpy", 0), forex.get("date", ""),
        ]
        for i, v in enumerate(vals, 1):
            ws.cell(row=row, column=i, value=v).border = THIN_BORDER

    def _log_corporate(self, wb: Workbook, snapshot: Dict, date: str):
        name = "Corporate"
        actions = snapshot.get("corporate_actions", [])
        if not actions:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Symbol", "Company", "Subject",
                "Ex-Date", "Record Date",
            ])
        else:
            ws = wb[name]

        for a in actions:
            row = ws.max_row + 1
            vals = [
                date, a["symbol"], a["company"], a["subject"],
                a["ex_date"], a.get("record_date", ""),
            ]
            for i, v in enumerate(vals, 1):
                ws.cell(row=row, column=i, value=v).border = THIN_BORDER

    def _log_insider(self, wb: Workbook, snapshot: Dict, date: str):
        name = "Insider"
        trades = snapshot.get("insider_trading", [])
        if not trades:
            return

        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _header_row(ws, [
                "Log Date", "Symbol", "Company", "Acquirer", "Relation",
                "Buy Value", "Sell Value", "Trade Date",
            ])
        else:
            ws = wb[name]

        # Only log top 20 by value
        for t in trades[:20]:
            row = ws.max_row + 1
            vals = [
                date, t["symbol"], t["company"], t["acquirer"],
                t.get("relation", ""), t["buy_value"], t["sell_value"], t["date"],
            ]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=i, value=v)
                cell.border = THIN_BORDER
