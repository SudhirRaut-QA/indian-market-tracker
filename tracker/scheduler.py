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

NOTE: All times are IST. GitHub Actions must set TZ=Asia/Kolkata.
"""

import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, List

import schedule

from . import config

logger = logging.getLogger(__name__)

# Indian Standard Time offset: UTC + 5:30
IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    """Get current time in IST. Uses TZ env var if set, else explicit offset."""
    return datetime.now(IST)


def is_weekday() -> bool:
    """Check if today is a weekday in IST."""
    return _now_ist().weekday() < 5  # Mon=0 to Fri=4


# Time-slot → what data to include
SLOT_CONFIG = {
    "09:00": {
        "label": "Pre-Open Preview",
        "slot_time": "09:00",
        "include_preopen": True,
        "include_sectors": False,
        "include_options": False,
        "include_corporate": False,
        "include_insider": False,
    },
    "09:08": {
        "label": "Pre-Open Final",
        "slot_time": "09:08",
        "include_preopen": True,
        "include_sectors": False,
        "include_options": False,
        "include_corporate": False,
        "include_insider": False,
    },
    "09:15": {
        "label": "Market Open",
        "slot_time": "09:15",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "09:30": {
        "label": "Early Session",
        "slot_time": "09:30",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "11:00": {
        "label": "Mid-Morning",
        "slot_time": "11:00",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "15:35": {
        "label": "Market Close",
        "slot_time": "15:35",
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": False,
        "include_insider": False,
    },
    "18:00": {
        "label": "Post-Market",
        "slot_time": "18:00",
        "use_cache": True,
        "include_preopen": False,
        "include_sectors": True,
        "include_options": False,
        "include_corporate": True,
        "include_insider": False,
        "include_bulk_deals": True,
    },
    "21:00": {
        "label": "Evening Digest",
        "slot_time": "21:00",
        "use_cache": True,
        "include_preopen": False,
        "include_sectors": True,
        "include_options": True,
        "include_corporate": True,
        "include_insider": True,
        "include_bulk_deals": True,
    },
}


class JobTimeout(Exception):
    """Raised when a job exceeds its timeout."""
    pass


def _timeout_handler(signum, frame):
    raise JobTimeout("Job execution exceeded timeout")


def _run_job_safe(run_fn: Callable, cfg: dict, label: str, on_complete: Optional[Callable] = None):
    """Execute a single job with timeout protection and error handling."""
    if not is_weekday():
        logger.info(f"Skipping {label} — weekend")
        return

    now_ist = _now_ist().strftime("%H:%M:%S")
    logger.info(f"▶ Running: {label} at {now_ist} IST")

    job_start = time.time()
    job_timeout = 600  # 10 minutes max per job

    try:
        # Set alarm on Unix (GitHub Actions is Linux)
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(job_timeout)

        run_fn(
            include_preopen=cfg.get("include_preopen", False),
            include_sectors=cfg.get("include_sectors", True),
            include_options=cfg.get("include_options", False),
            include_corporate=cfg.get("include_corporate", False),
            include_insider=cfg.get("include_insider", False),
            include_bulk_deals=cfg.get("include_bulk_deals", False),
            send_telegram=cfg.get("send_telegram", True),
            save_excel=cfg.get("save_excel", True),
            save_json=cfg.get("save_json", True),
            use_cache=cfg.get("use_cache", False),
            label=label,
            slot_time=cfg.get("slot_time", None),
        )
    except JobTimeout:
        logger.error(f"✖ Job {label} exceeded {job_timeout}s timeout — terminated")
    except Exception as e:
        logger.error(f"✖ Job {label} failed: {e}", exc_info=True)
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        elapsed = time.time() - job_start
        logger.info(f"✔ Job {label} finished in {elapsed:.1f}s")
        
        # Notify completion
        if on_complete:
            on_complete()


def setup_schedule(run_fn: Callable, slots: Optional[list] = None, completion_tracker: Optional[dict] = None) -> List[str]:
    """
    Set up scheduled jobs.

    Args:
        run_fn: Function to call for each slot (accepts keyword args).
        slots:  List of time strings to schedule (e.g. ["09:00","09:30"]).
                If None, schedules ALL slots in NOTIFICATION_TIMES.
        completion_tracker: Dict with 'completed' and 'jobs_to_track' keys for tracking.
    
    Returns:
        List of time strings that were scheduled.
    """
    # Clear any previously scheduled jobs (important for re-setup)
    schedule.clear()

    times_to_schedule = slots if slots else config.NOTIFICATION_TIMES

    for time_str in times_to_schedule:
        slot_cfg = SLOT_CONFIG.get(time_str, {})
        label = slot_cfg.get("label", time_str)

        def make_job(t=time_str, cfg=slot_cfg, lbl=label):
            def job():
                def on_complete():
                    if completion_tracker:
                        completion_tracker['completed'] += 1
                        if t in completion_tracker['jobs_to_track']:
                            completion_tracker['jobs_to_track'].remove(t)
                _run_job_safe(run_fn, cfg, lbl, on_complete=on_complete)
            return job

        schedule.every().day.at(time_str).do(make_job())
        logger.info(f"  📌 Scheduled: {label} at {time_str} IST")

    logger.info(f"Total slots: {len(times_to_schedule)}")
    return list(times_to_schedule)


def run_loop(run_for_minutes: int = 0, run_immediately: bool = False,
             run_fn: Optional[Callable] = None, slots: Optional[List[str]] = None):
    """Run the scheduler loop with proper timeout and late-start handling.

    Args:
        run_for_minutes: Exit after this many minutes (0 = run forever).
        run_immediately: If True, run ALL missed slots NOW before waiting.
        run_fn:          The run function to execute for each slot.
        slots:           List of slot times to schedule (if None, schedules all).
    """
    if run_fn is None:
        logger.error("❌ run_fn is required for scheduler")
        return
    
    # Track job completion for early exit
    completed_jobs = 0
    jobs_to_track = set()
    completion_tracker = {
        'completed': completed_jobs,
        'jobs_to_track': jobs_to_track
    }
    
    # Set up scheduled jobs with completion tracking
    scheduled_slots = setup_schedule(run_fn, slots=slots, completion_tracker=completion_tracker)
    total_jobs = len(scheduled_slots)
    jobs_to_track.update(scheduled_slots)
    
    ist_start = _now_ist().strftime("%H:%M:%S %Z")
    if run_for_minutes > 0:
        logger.info(f"Scheduler started at {ist_start}. Will run for {run_for_minutes} minutes.")
    else:
        logger.info(f"Scheduler started at {ist_start}. Running until stopped.")


    # ── Late-start catch-up: run ALL missed slots immediately ──
    if run_immediately:
        now = _now_ist()
        now_hm = now.strftime("%H:%M")
        
        # Find all scheduled slots that have already passed
        missed = [s for s in sorted(scheduled_slots) if s <= now_hm]
        
        if missed:
            logger.info(f"🚨 Catch-up mode: {len(missed)} missed slot(s) detected")
            logger.info(f"   Missed: {', '.join(missed)}")
            logger.info(f"   Running all missed slots now...")
            
            for slot_time in missed:
                if slot_time in SLOT_CONFIG:
                    cfg = SLOT_CONFIG[slot_time]
                    label = cfg.get("label", slot_time) + " (catch-up)"
                    logger.info(f"   ▶ Catching up: {label}")
                    
                    def on_complete():
                        completion_tracker['completed'] += 1
                        if slot_time in completion_tracker['jobs_to_track']:
                            completion_tracker['jobs_to_track'].remove(slot_time)
                    
                    _run_job_safe(run_fn, cfg, label, on_complete=on_complete)
            
            logger.info(f"✅ Catch-up complete. Resuming normal schedule...")
        else:
            logger.info("No missed slots to catch up on.")

    start_time = time.time()
    deadline = start_time + (run_for_minutes * 60) if run_for_minutes > 0 else None

    while True:
        # Check if all scheduled jobs completed (early exit)
        if total_jobs > 0 and completion_tracker['completed'] >= total_jobs:
            elapsed = (time.time() - start_time) / 60
            logger.info(f"✅ All {total_jobs} scheduled jobs completed in {elapsed:.1f}m. Exiting early.")
            break

        # Check deadline BEFORE running jobs
        if deadline and time.time() >= deadline:
            elapsed = (time.time() - start_time) / 60
            logger.info(f"⏱ Scheduler reached {run_for_minutes}-minute limit ({elapsed:.1f}m). Exiting.")
            break

        # Run any pending scheduled jobs
        schedule.run_pending()

        # Check deadline AFTER jobs (in case a job took a long time)
        if deadline and time.time() >= deadline:
            elapsed = (time.time() - start_time) / 60
            logger.info(f"⏱ Scheduler reached deadline after job ({elapsed:.1f}m). Exiting.")
            break

        time.sleep(30)
