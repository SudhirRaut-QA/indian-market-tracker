"""
Scheduler - Smart Market Hours Scheduling
==========================================

8 notification slots with context-appropriate data per time:

09:00 → Pre-open analysis (market preview)
09:08 → Pre-open final snapshot (IEP settled)
09:15 → Market open (first trade data + indices)
09:30 → Early session (FII/DII + sector moves)
11:00 → Mid-morning (full snapshot + delta vs 09:30)
15:35 → Market close (full snapshot + day delta)
18:00 → Post-market (FII/DII final + corporate actions)
21:00 → Evening digest (full summary + insider trading)
"""

import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import schedule

from . import config

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handle interrupt signals for graceful shutdown."""
    global _shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    _shutdown_requested = True


# Time-slot → what data to include
SLOT_CONFIG = {
    "09:00": {
        "label": "Pre-Open Preview",
        "include_preopen": True,
        "include_sectors": False,
        "include_options": False,
        "include_corporate": False,
        "include_insider": False,
    },
    "09:08": {
        "label": "Pre-Open Final",
        "include_preopen": True,
        "include_sectors": False,
        "include_options": False,
        "include_corporate": False,
        "include_insider": False,
    },
    "09:15": {
        "label": "Market Open",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "09:30": {
        "label": "Early Session",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "11:00": {
        "label": "Mid-Morning",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "15:35": {
        "label": "Market Close",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "18:00": {
        "label": "Post-Market",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": False,
        "include_corporate": True,
        "include_ipos": True,
        "include_insider": False,
        "include_block_deals": True,
        "include_bulk_deals": True,
    },
    "21:00": {
        "label": "Evening Digest",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": True,
        "include_block_deals": True,
        "include_bulk_deals": True,
    },
}


def is_weekday() -> bool:
    return datetime.now().weekday() < 5  # Mon=0 to Fri=4


def setup_schedule(run_fn: Callable):
    """
    Set up all scheduled jobs.
    
    run_fn should accept keyword args matching SLOT_CONFIG keys.
    """
    for time_str in config.NOTIFICATION_TIMES:
        slot_cfg = SLOT_CONFIG.get(time_str, {})
        label = slot_cfg.get("label", time_str)

        def make_job(t=time_str, cfg=slot_cfg, lbl=label):
            def job():
                if not is_weekday():
                    logger.info(f"Skipping {lbl} — weekend")
                    return
                logger.info(f"Running: {lbl} ({t})")
                try:
                    run_fn(
                        include_preopen=cfg.get("include_preopen", False),
                        include_sectors=cfg.get("include_sectors", True),
                        include_options=cfg.get("include_options", False),
                        include_corporate=cfg.get("include_corporate", False),
                        include_ipos=cfg.get("include_ipos", False),
                        include_insider=cfg.get("include_insider", False),
                        include_block_deals=cfg.get("include_block_deals", False),
                        include_bulk_deals=cfg.get("include_bulk_deals", False),
                        label=lbl,
                    )
                except Exception as e:
                    logger.error(f"Job {lbl} failed: {e}")
            return job

        schedule.every().day.at(time_str).do(make_job())
        logger.info(f"Scheduled: {label} at {time_str}")


def run_loop(run_for_minutes: Optional[int] = None):
    """Run the scheduler loop for specified duration or forever.
    
    Args:
        run_for_minutes: If set, scheduler will exit after this many minutes.
                        Useful for GitHub Actions windowed runs.
                        None = run forever.
    """
    global _shutdown_requested
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=run_for_minutes) if run_for_minutes else None
    
    if run_for_minutes:
        logger.info(f"Scheduler started for {run_for_minutes} minutes (until {end_time.strftime('%H:%M')} IST)")
    else:
        logger.info("Scheduler started in continuous mode")
    
    logger.info("Waiting for next job...")
    
    try:
        while not _shutdown_requested:
            schedule.run_pending()
            
            # Check if we've exceeded the time window
            if end_time and datetime.now() >= end_time:
                logger.info(f"Time window expired ({run_for_minutes} minutes elapsed)")
                break
            
            time.sleep(30)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    finally:
        logger.info("Scheduler shutdown complete")
        schedule.clear()
