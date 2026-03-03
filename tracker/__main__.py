"""
Indian Market Tracker - CLI Entry Point
=========================================

Usage:
  python -m tracker --now              # Run once with defaults
  python -m tracker --now --full       # Run with ALL data
  python -m tracker --now --preopen    # Pre-open only
  python -m tracker --schedule         # Start scheduler (8 daily slots)
  python -m tracker --now --no-telegram --no-excel  # Data only (print)
  python -m tracker --setup            # Verify setup
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
from .telegram_bot import (
    TelegramBot, format_fii_dii_msg, format_sector_msg,
    format_options_msg, format_commodities_msg, format_corporate_msg,
    format_preopen_msg, format_delta_alert,
)
from .excel_manager import ExcelManager
from .google_drive_uploader import GoogleDriveUploader


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
    include_insider: bool = False,
    send_telegram: bool = True,
    save_excel: bool = True,
    save_json: bool = True,
    label: str = "Manual Run",
):
    """Run a single data collection + notification cycle."""
    logger.info(f"=== {label} ===")

    scraper = MarketScraper()
    delta_engine = DeltaEngine()
    bot = TelegramBot()
    excel = ExcelManager()

    # 1. Collect snapshot
    logger.info("Collecting market snapshot...")
    snapshot = scraper.get_snapshot(
        include_sectors=include_sectors,
        include_options=include_options,
        include_preopen=include_preopen,
        include_corporate=include_corporate,
        include_insider=include_insider,
    )

    if snapshot.get("errors"):
        logger.warning(f"Errors: {snapshot['errors']}")

    # 2. Compute delta
    delta, is_first = delta_engine.process(snapshot)
    if is_first:
        logger.info("First run — no delta comparison available yet")

    # 3. Save JSON snapshot
    if save_json:
        os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(config.SNAPSHOT_DIR, f"snapshot_{ts}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"JSON saved: {json_path}")

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

        # Main message: FII/DII + Indices
        if snapshot.get("fii_dii") or snapshot.get("indices"):
            messages.append(("📊 Market Pulse", format_fii_dii_msg(snapshot, delta)))

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
        if (include_corporate or include_insider) and (snapshot.get("corporate_actions") or snapshot.get("insider_trading")):
            messages.append(("📋 Corporate", format_corporate_msg(snapshot)))

        for name, msg in messages:
            logger.info(f"Sending: {name}")
            bot.send(msg)

    # 5. Log to Excel
    if save_excel:
        excel.log_snapshot(snapshot, delta)

    # 6. Upload to Google Drive (best-effort, never blocks tracker)
    try:
        drive = GoogleDriveUploader()
        if drive.enabled:
            excel_dir = str(config.EXCEL_DIR)
            uploaded = drive.upload_excel_files(excel_dir, drive_name=config.DRIVE_EXCEL_NAME)
            if uploaded:
                logger.info(f"Google Drive: updated {config.DRIVE_EXCEL_NAME}")
    except KeyboardInterrupt:
        logger.warning("Google Drive upload interrupted")
    except Exception as e:
        logger.warning(f"Google Drive upload skipped: {e}")

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

    logger.info(f"Complete: {', '.join(parts)}")
    return snapshot


def verify_setup():
    """Check that all dependencies and credentials are working."""
    print("\n=== Indian Market Tracker - Setup Verification ===\n")

    # Check env vars
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    print(f"Telegram Bot Token: {'✅ Set' if token else '❌ Not set'}")
    print(f"Telegram Chat ID:   {'✅ Set' if chat_id else '❌ Not set'}")

    # Check dependencies
    deps = ["requests", "openpyxl", "schedule", "dotenv"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"Package {dep}: ✅")
        except ImportError:
            print(f"Package {dep}: ❌ Not installed")

    # Test NSE connection
    print("\nTesting NSE connection...")
    scraper = MarketScraper()
    status = scraper.get_market_status()
    if status:
        print("NSE Connection: ✅")
        for mkt, info in status.items():
            print(f"  {mkt}: {info.get('status', 'Unknown')}")
    else:
        print("NSE Connection: ❌")

    # Test Forex API
    print("\nTesting Forex API...")
    forex = scraper.get_usdinr()
    if forex:
        print(f"USD/INR: ✅ ₹{forex['usdinr']}")
    else:
        print("USD/INR: ❌")

    print("\n=== Setup complete ===")


def main():
    parser = argparse.ArgumentParser(
        description="Indian Market Tracker - Comprehensive NSE Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tracker --now                    Quick check (FII/DII + indices)
  python -m tracker --now --full             Everything (sectors, options, corporate, insider)
  python -m tracker --now --preopen          Pre-open market analysis
  python -m tracker --now --corporate        Include corporate actions + insider trading
  python -m tracker --schedule               Start 8-slot daily scheduler
  python -m tracker --now --no-telegram      Data only, no Telegram
  python -m tracker --setup                  Verify configuration
        """,
    )

    parser.add_argument("--now", action="store_true", help="Run once immediately")
    parser.add_argument("--schedule", action="store_true", help="Start scheduler (8 daily slots)")
    parser.add_argument("--run-for-minutes", type=int, default=0,
                        help="Auto-exit scheduler after N minutes (0 = forever)")
    parser.add_argument("--slots", type=str, default="",
                        help="Comma-separated slot times to schedule (e.g. '09:00,09:15,11:00')")
    parser.add_argument("--catch-up", action="store_true",
                        help="Run one snapshot immediately on late start")
    parser.add_argument("--setup", action="store_true", help="Verify setup and connections")

    # Data flags
    parser.add_argument("--full", action="store_true", help="Include ALL data sources")
    parser.add_argument("--sectors", action="store_true", help="Include sector analysis")
    parser.add_argument("--options", action="store_true", help="Include options PCR")
    parser.add_argument("--preopen", action="store_true", help="Include pre-open data")
    parser.add_argument("--corporate", action="store_true", help="Include corporate actions")
    parser.add_argument("--insider", action="store_true", help="Include insider trading")

    # Output flags
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram messages")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel logging")
    parser.add_argument("--no-json", action="store_true", help="Skip JSON snapshot")

    args = parser.parse_args()

    if args.setup:
        verify_setup()
        return

    if args.schedule:
        from .scheduler import setup_schedule, run_loop
        slots = [s.strip() for s in args.slots.split(",") if s.strip()] or None
        setup_schedule(run_once, slots=slots)
        run_loop(
            run_for_minutes=args.run_for_minutes,
            run_immediately=args.catch_up,
            run_fn=run_once,
        )
        return

    if args.now:
        inc_sectors = args.full or args.sectors
        inc_options = args.full or args.options
        inc_preopen = args.preopen
        inc_corporate = args.full or args.corporate
        inc_insider = args.full or args.insider or args.corporate

        run_once(
            include_sectors=inc_sectors,
            include_options=inc_options,
            include_preopen=inc_preopen,
            include_corporate=inc_corporate,
            include_insider=inc_insider,
            send_telegram=not args.no_telegram,
            save_excel=not args.no_excel,
            save_json=not args.no_json,
        )
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
