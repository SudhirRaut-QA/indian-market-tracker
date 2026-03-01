"""
Indian Market Tracker v3.0 - CLI Entry Point
===============================================

Usage:
  python -m tracker --now                    Quick (FII/DII + Indices)
  python -m tracker --now --full             Everything
  python -m tracker --now --preopen          Pre-open only
  python -m tracker --now --corporate        Corporate + Insider
  python -m tracker --now --deals            Block + Bulk deals
  python -m tracker --schedule               Start scheduler
  python -m tracker --now --no-telegram      Data only, no Telegram
  python -m tracker --backup                 Create zip backup
  python -m tracker --stats                  Show storage stats
  python -m tracker --setup                  Verify setup
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from . import config
from .nse_scraper import MarketScraper
from .delta_engine import DeltaEngine
from .signal_detector import SignalDetector, format_signals_msg
from .telegram_bot import (
    TelegramBot,
    format_fii_dii_msg,
    format_sector_msg,
    format_options_msg,
    format_commodities_msg,
    format_corporate_msg,
    format_preopen_msg,
    format_block_bulk_msg,
    format_52w_alerts_msg,
    format_context_msg,
    format_delta_alert,
)
from .excel_manager import ExcelManager, BackupManager
from .google_drive_uploader import GoogleDriveUploader, format_drive_summary


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tracker")


def run_once(
    include_sectors: bool = True,
    include_options: bool = True,
    include_preopen: bool = False,
    include_corporate: bool = False,
    include_ipos: bool = False,
    include_insider: bool = False,
    include_block_deals: bool = False,
    include_bulk_deals: bool = False,
    enrich_corporate: bool = True,
    send_telegram: bool = True,
    save_excel: bool = True,
    save_json: bool = True,
    save_daily: bool = True,
    label: str = "Manual Run",
):
    """Run a single data collection + notification cycle."""
    logger.info(f"=== {label} ===")

    if include_corporate and not include_ipos:
        include_ipos = True

    scraper = MarketScraper()
    delta_engine = DeltaEngine()
    signal_detector = SignalDetector()
    bot = TelegramBot()
    excel = ExcelManager()
    backup = BackupManager()
    drive = GoogleDriveUploader()

    # 1. Collect snapshot
    logger.info("Collecting market snapshot...")
    snapshot = scraper.get_snapshot(
        include_sectors=include_sectors,
        include_options=include_options,
        include_preopen=include_preopen,
        include_corporate=include_corporate,
        include_ipos=include_ipos,
        include_insider=include_insider,
        include_block_deals=include_block_deals,
        include_bulk_deals=include_bulk_deals,
        enrich_corporate=enrich_corporate,
    )

    if snapshot.get("errors"):
        logger.warning(f"Errors: {snapshot['errors']}")

    # 2. Compute delta
    delta, is_first = delta_engine.process(snapshot)
    if is_first:
        logger.info("First run — no delta comparison available yet")
    
    # 3. Generate trading signals (if sectors included)
    signals = None
    if include_sectors and snapshot.get("sectors"):
        try:
            signals = signal_detector.analyze(snapshot, delta)
            logger.info(f"Signals: {len(signals.get('buy', []))} buy, {len(signals.get('sell', []))} sell")
        except Exception as e:
            logger.error(f"Signal detection error: {e}")

    # 3. Save JSON snapshot (organized by date)
    if save_json:
        snap_dir = config.get_snapshot_dir()
        ts = datetime.now().strftime("%H%M%S")
        json_path = snap_dir / f"snapshot_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"JSON: {json_path}")

    # 4. Send Telegram messages
    if send_telegram:
        messages = []

        # Delta alert (if significant changes)
        if delta:
            alert = format_delta_alert(delta)
            if alert:
                messages.append(("⚡ Alert", alert))

        # Pre-open (only during pre-market)
        if include_preopen and snapshot.get("preopen"):
            messages.append(("🌅 Pre-Open", format_preopen_msg(snapshot)))

        # Main: FII/DII + Indices
        if snapshot.get("fii_dii") or snapshot.get("indices"):
            messages.append(("📊 Pulse", format_fii_dii_msg(snapshot, delta)))

        # Sectors
        if include_sectors and snapshot.get("sectors"):
            messages.append(("🏭 Sectors", format_sector_msg(snapshot, delta)))

        # Options
        if include_options and snapshot.get("option_chain"):
            messages.append(("📊 Options", format_options_msg(snapshot)))

        # Commodities + Forex
        if snapshot.get("commodities") or snapshot.get("forex"):
            messages.append(("🏆 Commodities", format_commodities_msg(snapshot, delta)))

        # Corporate + Insider
        if (include_corporate or include_insider) and (
            snapshot.get("corporate_actions") or snapshot.get("insider_trading")
        ):
            messages.append(("📋 Corporate", format_corporate_msg(snapshot)))

        # Block/Bulk deals
        if (include_block_deals or include_bulk_deals) and (
            snapshot.get("block_deals") or snapshot.get("bulk_deals")
        ):
            messages.append(("🏦 Deals", format_block_bulk_msg(snapshot)))

        # 52W Alerts
        alerts = snapshot.get("alerts", {})
        if alerts.get("near_52w_high") or alerts.get("near_52w_low"):
            msg = format_52w_alerts_msg(snapshot)
            if msg:
                messages.append(("📡 52W", msg))

        # Market intelligence / context
        if delta:
            ctx = format_context_msg(delta)
            if ctx:
                messages.append(("🧠 Context", ctx))
        
        # Trading signals (if generated)
        if signals:
            sig_msg = format_signals_msg(signals)
            if sig_msg:
                messages.append(("📊 Signals", sig_msg))

        for name, msg in messages:
            logger.info(f"Sending: {name}")
            bot.send(msg)

    # 5. Log to Excel
    if save_excel:
        excel.log_snapshot(snapshot, delta, label)

    # 6. Save daily summary
    if save_daily:
        backup.save_daily_summary(snapshot)
    
    # 7. Upload to Google Drive (if configured)
    excel_uploaded = 0
    snapshots_uploaded = 0
    if drive.enabled:
        try:
            # Upload Excel files
            if save_excel:
                excel_uploaded = drive.upload_excel_files(config.EXCEL_DIR)
                logger.info(f"Google Drive: {excel_uploaded} Excel file(s) uploaded")
            
            # Upload recent snapshots
            if save_json:
                snapshots_uploaded = drive.upload_snapshots(config.SNAPSHOT_DIR, max_files=5)
                logger.info(f"Google Drive: {snapshots_uploaded} snapshot(s) uploaded")
            
            # Add Drive summary to Telegram
            if send_telegram and (excel_uploaded > 0 or snapshots_uploaded > 0):
                drive_msg = format_drive_summary(drive, excel_uploaded, snapshots_uploaded)
                if drive_msg:
                    bot.send(drive_msg)
        except Exception as e:
            logger.error(f"Google Drive upload error: {e}")

    # Summary
    parts = []
    if snapshot.get("fii_dii"):
        parts.append("FII/DII")
    if snapshot.get("indices"):
        parts.append(f"{len(snapshot['indices'])} indices")
    if snapshot.get("sectors"):
        total_stocks = sum(s.get("count", 0) for s in snapshot["sectors"].values())
        parts.append(f"{len(snapshot['sectors'])} sectors ({total_stocks} stocks)")
    if snapshot.get("option_chain"):
        parts.append("Options")
    if snapshot.get("commodities"):
        parts.append("Commodities")
    if snapshot.get("forex"):
        parts.append("Forex")
    if snapshot.get("corporate_actions"):
        parts.append(f"{len(snapshot['corporate_actions'])} corp actions")
    if snapshot.get("insider_trading"):
        parts.append(f"{len(snapshot['insider_trading'])} insider trades")
    if snapshot.get("block_deals"):
        parts.append(f"{len(snapshot['block_deals'])} block deals")
    if snapshot.get("bulk_deals"):
        parts.append(f"{len(snapshot['bulk_deals'])} bulk deals")

    alerts = snapshot.get("alerts", {})
    n_52h = len(alerts.get("near_52w_high", []))
    n_52l = len(alerts.get("near_52w_low", []))
    if n_52h or n_52l:
        parts.append(f"52W alerts: {n_52h}H/{n_52l}L")

    logger.info(f"Complete: {', '.join(parts)}")
    return snapshot


def verify_setup():
    """Check setup and connections."""
    print("\n=== Indian Market Tracker v3.0 - Setup ===\n")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    print(f"Bot Token: {'✅' if token else '❌ Not set'}")
    print(f"Chat ID:   {'✅' if chat_id else '❌ Not set'}")

    deps = ["requests", "openpyxl", "schedule", "dotenv"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"{dep}: ✅")
        except ImportError:
            print(f"{dep}: ❌")

    print("\nTesting NSE...")
    scraper = MarketScraper()
    status = scraper.get_market_status()
    if status:
        print("NSE: ✅")
        for mkt, info in status.items():
            print(f"  {mkt}: {info.get('status', '?')}")
    else:
        print("NSE: ❌")

    print("\nTesting Forex...")
    forex = scraper.get_usdinr()
    if forex:
        print(f"USD/INR: ✅ ₹{forex['usdinr']}")
    else:
        print("USD/INR: ❌")

    print("\nData dirs:")
    for name, path in [
        ("Snapshots", config.SNAPSHOT_DIR),
        ("Excel", config.EXCEL_DIR),
        ("Daily", config.DAILY_DIR),
        ("Backup", config.BACKUP_DIR),
    ]:
        print(f"  {name}: {path}")

    print("\n=== Done ===")


def run_backup():
    """Create backup and show stats."""
    bm = BackupManager()
    print("\n=== Backup ===")
    path = bm.create_backup()
    if path:
        print(f"Created: {path}")
    else:
        print("No data to backup")

    stats = bm.get_storage_stats()
    print("\n=== Storage ===")
    for name, s in stats.items():
        print(f"  {name}: {s['files']} files, {s['size_mb']:.1f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Indian Market Tracker v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tracker --now                    Quick (FII/DII + indices)
  python -m tracker --now --full             All data sources
  python -m tracker --now --preopen          Pre-open analysis
  python -m tracker --now --corporate        Corporate + insider
  python -m tracker --now --deals            Block + bulk deals
  python -m tracker --now --full --deals     Everything including deals
  python -m tracker --schedule               Start 8-slot scheduler
  python -m tracker --now --no-telegram      Data only
  python -m tracker --backup                 Zip backup + stats
  python -m tracker --stats                  Storage statistics
  python -m tracker --setup                  Verify config
        """,
    )

    parser.add_argument("--now", action="store_true", help="Run once immediately")
    parser.add_argument("--schedule", action="store_true", help="Start scheduler")
    parser.add_argument("--setup", action="store_true", help="Verify setup")
    parser.add_argument("--backup", action="store_true", help="Create backup")
    parser.add_argument("--stats", action="store_true", help="Storage stats")

    # Data flags
    parser.add_argument("--full", action="store_true", help="All data sources")
    parser.add_argument("--sectors", action="store_true", help="Sector analysis")
    parser.add_argument("--options", action="store_true", help="Options PCR")
    parser.add_argument("--preopen", action="store_true", help="Pre-open data")
    parser.add_argument("--corporate", action="store_true", help="Corporate actions")
    parser.add_argument("--insider", action="store_true", help="Insider trading")
    parser.add_argument("--deals", action="store_true", help="Block + bulk deals")

    # Output flags
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel")
    parser.add_argument("--no-json", action="store_true", help="Skip JSON")

    args = parser.parse_args()

    if args.setup:
        verify_setup()
        return

    if args.backup:
        run_backup()
        return

    if args.stats:
        bm = BackupManager()
        stats = bm.get_storage_stats()
        print("\n=== Storage Stats ===")
        for name, s in stats.items():
            print(f"  {name}: {s['files']} files, {s['size_mb']:.1f} MB")
        return

    if args.schedule:
        from .scheduler import setup_schedule, run_loop
        
        # Check for --run-for-minutes flag
        run_minutes = None
        if "--run-for-minutes" in sys.argv:
            try:
                idx = sys.argv.index("--run-for-minutes")
                run_minutes = int(sys.argv[idx + 1])
                logger.info(f"Scheduler will run for {run_minutes} minutes")
            except (IndexError, ValueError):
                logger.error("--run-for-minutes requires integer value")
                return
        
        setup_schedule(run_once)
        run_loop(run_for_minutes=run_minutes)
        return

    if args.now:
        inc_sectors = args.full or args.sectors
        inc_options = args.full or args.options
        inc_preopen = args.preopen
        inc_corporate = args.full or args.corporate
        inc_insider = args.full or args.insider or args.corporate
        inc_block = args.deals
        inc_bulk = args.deals

        run_once(
            include_sectors=inc_sectors,
            include_options=inc_options,
            include_preopen=inc_preopen,
            include_corporate=inc_corporate,
            include_insider=inc_insider,
            include_block_deals=inc_block,
            include_bulk_deals=inc_bulk,
            send_telegram=not args.no_telegram,
            save_excel=not args.no_excel,
            save_json=not args.no_json,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
