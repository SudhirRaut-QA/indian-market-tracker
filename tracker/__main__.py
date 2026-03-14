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
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from . import config
from .nse_scraper import MarketScraper
from .delta_engine import DeltaEngine
from .telegram_bot import (
    TelegramBot, format_fii_dii_msg, format_sector_msg,
    format_options_msg, format_commodities_msg, format_corporate_msg,
    format_preopen_msg, format_delta_alert, format_bulk_deals_msg,
    identify_watchlist, format_watchlist_msg, format_expert_opinion,
)
from .excel_manager import ExcelManager
from .trading_engine import generate_intraday_setups, format_trading_msg
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
    include_bulk_deals: bool = False,
    send_telegram: bool = True,
    save_excel: bool = True,
    save_json: bool = True,
    label: str = "Manual Run",
    use_cache: bool = False,
    slot_time: str = None,
):
    """Run a single data collection + notification cycle.
    
    Args:
        use_cache: If True, use cached market data (indices, sectors, FII/DII) from last 
                   snapshot and only scrape fresh forex/corporate data. Useful for evening 
                   slots when NSE API is unavailable.
    """
    # Start timing and get IST timestamp
    start_time = time.time()
    ist = ZoneInfo('Asia/Kolkata')
    start_ist = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S IST")
    
    logger.info("=" * 70)
    logger.info(f"START: {label}")
    logger.info(f"Time: {start_ist}")
    if use_cache:
        logger.info("🗂 Mode: CACHE (using saved market data + fresh forex/corporate)")
    logger.info("=" * 70)

    scraper = MarketScraper()
    delta_engine = DeltaEngine()
    bot = TelegramBot()
    excel = ExcelManager()

    # 1. Collect snapshot (with cache mode support)
    if use_cache:
        # Load cached market data
        cached = delta_engine.load_previous()
        if cached:
            logger.info(f"✓ Loaded cached snapshot from {cached.get('timestamp', 'unknown')}")
            snapshot = cached.copy()
            
            # Scrape only fresh data (forex, corporate, insider, bulk deals)
            logger.info("Collecting fresh forex and corporate data...")
            fresh = scraper.get_snapshot(
                include_sectors=False,
                include_options=False,
                include_preopen=False,
                include_corporate=include_corporate,
                include_insider=include_insider,
                include_bulk_deals=include_bulk_deals,
            )
            
            # Merge fresh data into cached snapshot
            if fresh.get("forex"):
                snapshot["forex"] = fresh["forex"]
            if fresh.get("corporate_actions"):
                snapshot["corporate_actions"] = fresh["corporate_actions"]
            if fresh.get("insider_trading"):
                snapshot["insider_trading"] = fresh["insider_trading"]
            if fresh.get("bulk_deals"):
                snapshot["bulk_deals"] = fresh["bulk_deals"]
            if fresh.get("block_deals"):
                snapshot["block_deals"] = fresh["block_deals"]
            
            # Update timestamp
            snapshot["timestamp"] = start_ist
            logger.info("✓ Merged fresh data with cached snapshot")
        else:
            logger.warning("⚠ No cached data available, falling back to live scraping")
            use_cache = False  # Fall back to normal mode
    
    if not use_cache:
        # Normal mode: scrape everything fresh
        logger.info("Collecting market snapshot...")
        snapshot = scraper.get_snapshot(
            include_sectors=include_sectors,
            include_options=include_options,
            include_preopen=include_preopen,
            include_corporate=include_corporate,
            include_insider=include_insider,
            include_bulk_deals=include_bulk_deals,
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

    # 3b. Generate trading setups (used by both Telegram and Excel)
    trading_setups = None
    if include_sectors and snapshot.get("sectors"):
        trading_setups = generate_intraday_setups(snapshot)
        logger.info(f"Trading setups: {len(trading_setups.get('index_setups', []))} index, "
                     f"{len(trading_setups.get('stock_setups', []))} stock, "
                     f"{len(trading_setups.get('etf_setups', []))} ETF")

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

        # Main message: FII/DII + Indices (slot-aware)
        if snapshot.get("fii_dii") or snapshot.get("indices"):
            messages.append(("📊 Market Pulse", format_fii_dii_msg(snapshot, delta, slot_time=slot_time)))

        # Sectors
        if include_sectors and snapshot.get("sectors"):
            messages.append(("🏭 Sectors", format_sector_msg(snapshot, delta)))

        # Watchlist: identify in early slots, track in later ones
        watchlist_file = os.path.join(str(config.DATA_DIR), "watchlist",
                                      datetime.now().strftime("%Y-%m-%d") + ".json")
        os.makedirs(os.path.dirname(watchlist_file), exist_ok=True)
        watchlist = None
        if include_sectors and snapshot.get("sectors"):
            # Check if watchlist exists for today
            if os.path.exists(watchlist_file):
                try:
                    with open(watchlist_file, "r", encoding="utf-8") as wf:
                        watchlist = json.load(wf)
                    logger.info(f"Watchlist loaded: {len(watchlist)} stocks")
                except Exception:
                    watchlist = None

            # Build watchlist if not yet created (early slots with sector data)
            if not watchlist:
                watchlist = identify_watchlist(snapshot, count=5)
                if watchlist:
                    with open(watchlist_file, "w", encoding="utf-8") as wf:
                        json.dump(watchlist, wf, ensure_ascii=False, indent=2)
                    logger.info(f"Watchlist created: {[w['symbol'] for w in watchlist]}")

            # Send watchlist tracking message
            if watchlist:
                wl_msg = format_watchlist_msg(snapshot, watchlist)
                if wl_msg:
                    messages.append(("🎯 Watchlist", wl_msg))

        # Options
        if include_options and snapshot.get("option_chain"):
            messages.append(("📊 Options", format_options_msg(snapshot)))

        # Commodities + Forex (slot-aware)
        if snapshot.get("commodities") or snapshot.get("forex"):
            messages.append(("🏆 Commodities", format_commodities_msg(snapshot, delta, slot_time=slot_time)))

        # Corporate + Insider
        if (include_corporate or include_insider) and (snapshot.get("corporate_actions") or snapshot.get("insider_trading")):
            messages.append(("📋 Corporate", format_corporate_msg(snapshot)))

        # Bulk & Block Deals
        if include_bulk_deals and (snapshot.get("bulk_deals") or snapshot.get("block_deals")):
            messages.append(("💼 Deals", format_bulk_deals_msg(snapshot)))

        # Expert Opinion (in slots with sector data)
        if include_sectors and snapshot.get("sectors"):
            expert_msg = format_expert_opinion(snapshot, delta)
            if expert_msg:
                messages.append(("🧠 Expert", expert_msg))

        # Intraday Trading Setups
        if trading_setups:
            trading_msg = format_trading_msg(trading_setups)
            if trading_msg:
                messages.append(("📐 Trading", trading_msg))

        for name, msg in messages:
            logger.info(f"Sending: {name}")
            bot.send(msg)

    # 5. Log to Excel
    if save_excel:
        excel.log_snapshot(snapshot, delta, trading_setups=trading_setups)

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
    if snapshot.get("bulk_deals"):
        parts.append(f"{len(snapshot['bulk_deals'])} bulk deals")
    if snapshot.get("block_deals"):
        parts.append(f"{len(snapshot['block_deals'])} block deals")

    # End timing and calculate duration
    end_time = time.time()
    elapsed = end_time - start_time
    end_ist = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Format elapsed time
    if elapsed < 60:
        elapsed_str = f"{elapsed:.1f}s"
    else:
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        elapsed_str = f"{mins}m {secs}s"
    
    logger.info("=" * 70)
    logger.info(f"COMPLETE: {', '.join(parts)}")
    logger.info(f"End Time: {end_ist}")
    logger.info(f"Duration: {elapsed_str}")
    logger.info("=" * 70)
    
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
    parser.add_argument("--bulk-deals", action="store_true", help="Include bulk & block deals")

    # Output flags
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram messages")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel logging")
    parser.add_argument("--no-json", action="store_true", help="Skip JSON snapshot")

    args = parser.parse_args()

    if args.setup:
        verify_setup()
        return

    if args.schedule:
        from .scheduler import run_loop
        slots = [s.strip() for s in args.slots.split(",") if s.strip()] or None
        run_loop(
            run_for_minutes=args.run_for_minutes,
            run_immediately=args.catch_up,
            run_fn=run_once,
            slots=slots,
        )
        return

    if args.now:
        inc_sectors = args.full or args.sectors
        inc_options = args.full or args.options
        inc_preopen = args.preopen
        inc_corporate = args.full or args.corporate
        inc_insider = args.full or args.insider or args.corporate
        inc_bulk_deals = args.full or args.bulk_deals

        run_once(
            include_sectors=inc_sectors,
            include_options=inc_options,
            include_preopen=inc_preopen,
            include_corporate=inc_corporate,
            include_insider=inc_insider,
            include_bulk_deals=inc_bulk_deals,
            send_telegram=not args.no_telegram,
            save_excel=not args.no_excel,
            save_json=not args.no_json,
        )
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
