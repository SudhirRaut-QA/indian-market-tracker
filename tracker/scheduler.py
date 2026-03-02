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
    """Check if today is a weekday in IST."""
    ist_now = datetime.now(IST)
    return ist_now.weekday() < 5  # Mon=0 to Fri=4


class JobTimeout(Exception):
    """Raised when a job exceeds its timeout."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for job timeout."""
    raise JobTimeout("Job execution exceeded timeout")


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
                
                # Set 10-minute timeout for each job (max time for data collection)
                job_start = time.time()
                job_timeout = 600  # 10 minutes
                
                try:
                    # Try to set alarm signal (Unix only)
                    if hasattr(signal, 'SIGALRM'):
                        signal.signal(signal.SIGALRM, timeout_handler)
                        signal.alarm(job_timeout)
                    
                    run_fn(
                        include_preopen=cfg.get("include_preopen", False),
                        include_sectors=cfg.get("include_sectors", True),
                        include_options=cfg.get("include_options", False),
                        include_corporate=cfg.get("include_corporate", False),
                        include_insider=cfg.get("include_insider", False),
                        label=lbl,
                    )
                    
                    # Cancel alarm if job completed
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                        
                except JobTimeout:
                    logger.error(f"Job {lbl} exceeded {job_timeout}s timeout - terminated")
                except Exception as e:
                    logger.error(f"Job {lbl} failed: {e}")
                finally:
                    # Always cancel alarm
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                    
                    elapsed = time.time() - job_start
                    logger.info(f"Job {lbl} completed in {elapsed:.1f}s")
            return job

        schedule.every().day.at(time_str).do(make_job())
        logger.info(f"Scheduled: {label} at {time_str}")


def run_loop(run_for_minutes: int = 0):
    """Run the scheduler loop with proper timeout handling.
    
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
        # Check deadline BEFORE running jobs or sleeping
        if deadline and time.time() >= deadline:
            elapsed = (time.time() - start_time) / 60
            logger.info(f"Scheduler reached {run_for_minutes}-minute limit ({elapsed:.1f}m elapsed). Exiting.")
            break
        
        # Run any pending scheduled jobs
        schedule.run_pending()
        
        # Check deadline again after jobs complete (in case a job took a long time)
        if deadline and time.time() >= deadline:
            elapsed = (time.time() - start_time) / 60
            logger.info(f"Scheduler reached deadline after job completion ({elapsed:.1f}m). Exiting.")
            break
        
        # Sleep for 30 seconds before next check
        time.sleep(30)
