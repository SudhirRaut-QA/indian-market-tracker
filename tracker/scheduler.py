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
import time
from datetime import datetime
from typing import Callable

import schedule

from . import config

logger = logging.getLogger(__name__)


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
        "include_insider": False,
    },
    "21:00": {
        "label": "Evening Digest",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": True,
        "include_insider": True,
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
                        include_insider=cfg.get("include_insider", False),
                        label=lbl,
                    )
                except Exception as e:
                    logger.error(f"Job {lbl} failed: {e}")
            return job

        schedule.every().day.at(time_str).do(make_job())
        logger.info(f"Scheduled: {label} at {time_str}")


def run_loop(run_for_minutes: int = 0):
    """
    Run the scheduler loop.
    
    Args:
        run_for_minutes: Exit after this many minutes (0 = run forever).
    """
    if run_for_minutes > 0:
        logger.info(f"Scheduler started. Will run for {run_for_minutes} minutes.")
    else:
        logger.info("Scheduler started. Running until stopped.")
    
    start_time = time.time()
    deadline = start_time + (run_for_minutes * 60) if run_for_minutes > 0 else None
    
    while True:
        schedule.run_pending()
        
        if deadline and time.time() >= deadline:
            logger.info(f"Scheduler reached {run_for_minutes}-minute limit. Exiting.")
            break
        
        time.sleep(30)
