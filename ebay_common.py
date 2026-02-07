#!/usr/bin/env python3
"""
FoxFinder - eBay Common Module

Shared code for foxfinder.py and status dashboard.
Handles logging, heartbeat, shutdown signals, and rate limiting.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

# Import disk space check if available
try:
    from shared_utils import check_disk_space
    _HAS_DISK_CHECK = True
except ImportError:
    _HAS_DISK_CHECK = False
    def check_disk_space(path, min_mb=100):
        return True, -1

# Try to import zoneinfo for system-maintained DST rules (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
    HAS_ZONEINFO = True
except ImportError:
    HAS_ZONEINFO = False

# Version

VERSION = "1.3.0"
__version__ = VERSION
# v1.3.0: Added gmail_cleanup_sent() and get_imap_config() shared functions
# v1.2.1: Fixed naive datetime bug - tzinfo check moved before branching (prevents TypeError)
# v1.2.0: DST functions use zoneinfo (system-maintained) with fallback to hardcoded rules
# v1.1.0: Robust rate limit system - post-reset validation, sanity checks, retry logic

# CHANGELOG v1.2.0:
# - is_us_pacific_dst() uses zoneinfo("America/Los_Angeles") when available
# - is_israel_dst() uses zoneinfo("Asia/Jerusalem") when available
# - Falls back to hardcoded rules if zoneinfo unavailable (Python <3.9)
# - Rate limit reset times now adapt to DST law changes automatically
#
# CHANGELOG v1.0.4:
# - check_internet() uses specific exceptions (requests.RequestException, OSError)
#
# CHANGELOG v1.0.2:
# - Atomic write pattern for update_heartbeat() (temp+rename)
# - Atomic write pattern for save_rate_state() (temp+rename)
# - Atomic writes for crash safety

# Paths

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "ebay_config.json"
SEEN_FILE = SCRIPT_DIR / "ebay_seen_api.json"
LOG_FILE = SCRIPT_DIR / "foxfinder.log"
TOKEN_FILE = SCRIPT_DIR / "ebay_token.json"
RATE_FILE = SCRIPT_DIR / "ebay_rate_limit.json"
SHUTDOWN_FILE = SCRIPT_DIR / ".shutdown_requested"
HEARTBEAT_FILE = SCRIPT_DIR / ".heartbeat"
LOCK_FILE = SCRIPT_DIR / ".ebay.lock"

# Run log (operational tracking, separate from user config)
RUN_LOG_FILE = SCRIPT_DIR / "foxfinder_run_log.json"

# Update Checker
API_UPDATE_CHECK_FILE = SCRIPT_DIR / ".last_api_update_check"
API_UPDATE_ALERT_FILE = SCRIPT_DIR / "API_UPDATE_NOTICE.txt"

# Email failure tracking
EMAIL_FAILURES_FILE = SCRIPT_DIR / ".email_failures"

# Constants

# eBay API
EBAY_API_BASE = "https://api.ebay.com"
EBAY_API_VERSION = "v1"

# Rate limiting
DAILY_CALL_LIMIT = 4500  # Buffer below 5000 hard limit
MIN_INTERVAL_SECONDS = 30

# Log rotation
LOG_MAX_SIZE_MB = 10

# Logging

def log(message: str, log_file: Path = None, verbose: bool = True) -> None:
    """
    Thread-safe logging with timestamp.

    Args:
        message: Message to log
        log_file: Optional log file path (defaults to LOG_FILE)
        verbose: Whether to print to console
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"

    if log_file is None:
        log_file = LOG_FILE

    # Write to file
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (IOError, OSError):
        pass

    # Print to console
    if verbose:
        try:
            print(line, flush=True)
        except (UnicodeEncodeError, OSError):
            try:
                safe_line = line.encode('ascii', errors='replace').decode('ascii')
                print(safe_line, flush=True)
            except (UnicodeEncodeError, OSError):
                pass


def rotate_logs() -> bool:
    """
    Simple log rotation: if > LOG_MAX_SIZE_MB, rename to .old and start fresh.

    Returns:
        True if rotation occurred, False otherwise
    """
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_SIZE_MB * 1024 * 1024:
            old_log = LOG_FILE.with_suffix(".log.old")
            if old_log.exists():
                old_log.unlink()
            LOG_FILE.rename(old_log)
            log("Active log rotated (exceeded size limit)")
            return True
    except (IOError, OSError):
        pass
    return False


# Heartbeat

def update_heartbeat(source: str = "foxfinder", version: str = VERSION) -> None:
    """
    Update heartbeat file with JSON status for health checks.
    Uses atomic write pattern (temp+rename) for crash safety.

    Args:
        source: Identifier for what's updating (foxfinder/status)
        version: Version string to include (defaults to module VERSION)
    """
    try:
        data = {
            'timestamp': time.time(),
            'source': source,
            'datetime': datetime.now().isoformat(),
            'version': version,
        }
        # Atomic write: temp file then rename
        tmp_file = HEARTBEAT_FILE.with_suffix('.tmp')
        tmp_file.write_text(json.dumps(data), encoding='utf-8')
        tmp_file.replace(HEARTBEAT_FILE)
    except (IOError, OSError):
        pass  # Non-critical


def read_heartbeat() -> Optional[Dict[str, Any]]:
    """Read heartbeat file and return data with age."""
    try:
        if HEARTBEAT_FILE.exists():
            data = json.loads(HEARTBEAT_FILE.read_text(encoding='utf-8'))
            data['age_seconds'] = time.time() - data.get('timestamp', 0)
            return data
    except (IOError, json.JSONDecodeError, KeyError):
        pass
    return None


# Shutdown

def is_shutdown_requested() -> bool:
    """Check if graceful shutdown has been requested."""
    return SHUTDOWN_FILE.exists()


def request_shutdown() -> bool:
    """
    Create shutdown request file.

    Returns:
        True if file was created successfully
    """
    try:
        SHUTDOWN_FILE.write_text(datetime.now().isoformat(), encoding='utf-8')
        log("Shutdown requested")
        return True
    except (IOError, OSError):
        return False


def clear_shutdown_request() -> bool:
    """
    Clear the shutdown signal file.

    Returns:
        True if file was cleared, False otherwise
    """
    try:
        if SHUTDOWN_FILE.exists():
            SHUTDOWN_FILE.unlink()
            log("Cleared shutdown signal")
            return True
    except (IOError, OSError):
        pass
    return False


# --- Interruptible Operations ---

def interruptible_sleep(seconds: float, check_interval: float = 1.0) -> bool:
    """
    Sleep that checks for shutdown requests periodically.
    Returns True if interrupted, False if completed.
    """
    elapsed = 0.0
    while elapsed < seconds:
        if is_shutdown_requested():
            return True  # Interrupted
        sleep_time = min(check_interval, seconds - elapsed)
        time.sleep(sleep_time)
        elapsed += sleep_time
    return False  # Completed normally


def interruptible_wait(
    condition_func,
    timeout_seconds: float,
    check_interval: float = 0.5,
    description: str = "condition"
) -> Tuple[bool, bool]:
    """
    Wait for condition_func() to return True, checking for shutdown.
    Returns (condition_met, was_interrupted).
    """
    elapsed = 0.0
    while elapsed < timeout_seconds:
        if is_shutdown_requested():
            return False, True  # Not met, interrupted
        try:
            if condition_func():
                return True, False  # Met, not interrupted
        except Exception:
            pass  # Condition check failed, keep waiting
        time.sleep(check_interval)
        elapsed += check_interval
    return False, False  # Timeout, not interrupted


# Rate Limiting

def _get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> int:
    """
    Get the nth occurrence of a weekday in a given month.

    Args:
        year: Year
        month: Month (1-12)
        weekday: 0=Monday, 6=Sunday
        n: 1=first, 2=second, etc.

    Returns:
        Day of month (1-31)
    """
    first_day = datetime(year, month, 1)
    first_weekday = first_day.weekday()
    days_until = (weekday - first_weekday) % 7
    first_occurrence = 1 + days_until
    return first_occurrence + (n - 1) * 7


def is_us_pacific_dst(dt_utc: datetime) -> bool:
    """
    Correctly determine if US Pacific Time is in DST.
    Uses system timezone data (zoneinfo) when available, falls back to hardcoded rules.
    US DST: 2nd Sunday of March 2:00 AM to 1st Sunday of November 2:00 AM (local time)

    Args:
        dt_utc: datetime in UTC timezone

    Returns:
        True if DST is in effect, False otherwise
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

    # Best: Use zoneinfo (Python 3.9+) - system-maintained DST rules
    if HAS_ZONEINFO:
        try:
            pacific_tz = ZoneInfo("America/Los_Angeles")
            pacific_time = dt_utc.astimezone(pacific_tz)
            # Check if DST is in effect by comparing UTC offset
            # PDT = UTC-7 (DST), PST = UTC-8 (standard)
            offset_hours = pacific_time.utcoffset().total_seconds() / 3600
            return offset_hours == -7  # PDT
        except Exception:
            pass  # Fall through to hardcoded logic

    # Hardcoded rules for Python <3.9
    year = dt_utc.year
    month = dt_utc.month

    # Quick checks for months clearly in or out of DST
    if month < 3 or month > 11:
        return False
    if 3 < month < 11:
        return True

    # March: DST starts 2nd Sunday at 2:00 AM PST (10:00 AM UTC)
    if month == 3:
        dst_start_day = _get_nth_weekday_of_month(year, 3, 6, 2)  # 6=Sunday, 2nd
        dst_start_utc = datetime(year, 3, dst_start_day, 10, 0, 0, tzinfo=timezone.utc)
        return dt_utc >= dst_start_utc

    # November: DST ends 1st Sunday at 2:00 AM PDT (9:00 AM UTC)
    if month == 11:
        dst_end_day = _get_nth_weekday_of_month(year, 11, 6, 1)  # 6=Sunday, 1st
        dst_end_utc = datetime(year, 11, dst_end_day, 9, 0, 0, tzinfo=timezone.utc)
        return dt_utc < dst_end_utc

    return False


def _get_last_weekday_of_month(year: int, month: int, weekday: int) -> int:
    """
    Get the last occurrence of a weekday in a given month.

    Args:
        year: Year
        month: Month (1-12)
        weekday: 0=Monday, 4=Friday, 6=Sunday

    Returns:
        Day of month (1-31)
    """
    # Get the last day of the month
    if month == 12:
        last_day = 31
    else:
        next_month = datetime(year, month + 1, 1)
        last_day = (next_month - timedelta(days=1)).day

    # Find the last occurrence of the weekday
    last_date = datetime(year, month, last_day)
    days_back = (last_date.weekday() - weekday) % 7
    return last_day - days_back


def _get_last_friday_before_date(year: int, month: int, day: int) -> int:
    """
    Get the last Friday before (or on) a specific date.

    Args:
        year: Year
        month: Month (1-12)
        day: Day of month

    Returns:
        Day of month for the last Friday before the given date
    """
    ref_date = datetime(year, month, day)
    days_back = (ref_date.weekday() - 4) % 7  # 4 = Friday
    if days_back == 0 and ref_date.weekday() != 4:
        days_back = 7  # If ref_date is not Friday, go back to previous Friday
    result_date = ref_date - timedelta(days=days_back)
    return result_date.day


def is_israel_dst(dt_utc: datetime) -> bool:
    """
    Correctly determine if Israel Time is in DST.
    Uses system timezone data (zoneinfo) when available, falls back to hardcoded rules.
    Israel DST: Last Friday before April 2 at 02:00 to last Sunday of October at 02:00 (local time)

    Args:
        dt_utc: datetime in UTC timezone

    Returns:
        True if DST is in effect (IDT, UTC+3), False otherwise (IST, UTC+2)
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)

    # Best: Use zoneinfo (Python 3.9+) - system-maintained DST rules
    if HAS_ZONEINFO:
        try:
            israel_tz = ZoneInfo("Asia/Jerusalem")
            israel_time = dt_utc.astimezone(israel_tz)
            # Check if DST is in effect by comparing UTC offset
            # IDT = UTC+3 (DST), IST = UTC+2 (standard)
            offset_hours = israel_time.utcoffset().total_seconds() / 3600
            return offset_hours == 3  # IDT
        except Exception:
            pass  # Fall through to hardcoded logic

    # Hardcoded rules for Python <3.9
    year = dt_utc.year
    month = dt_utc.month

    # Quick checks for months clearly in or out of DST
    if month < 3 or month > 10:
        return False
    if 4 < month < 10:
        return True

    # March: DST might start (last Friday before April 2)
    if month == 3:
        # Last Friday before April 2 could be in March (March 26-31) or April 1
        dst_start_day = _get_last_friday_before_date(year, 4, 1)
        # If the Friday is in March
        if dst_start_day > 25:  # It's in late March
            # DST starts at 02:00 local (IST = UTC+2), so 00:00 UTC
            dst_start_utc = datetime(year, 3, dst_start_day, 0, 0, 0, tzinfo=timezone.utc)
            return dt_utc >= dst_start_utc
        return False

    # April: DST might have just started
    if month == 4:
        dst_start_day = _get_last_friday_before_date(year, 4, 1)
        if dst_start_day == 1:
            # DST starts April 1 at 02:00 local (IST = UTC+2), so 00:00 UTC
            dst_start_utc = datetime(year, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
            return dt_utc >= dst_start_utc
        return True  # If Friday was in March, we're already in DST

    # October: DST ends last Sunday at 02:00 local (IDT = UTC+3), so 23:00 UTC Saturday
    if month == 10:
        dst_end_day = _get_last_weekday_of_month(year, 10, 6)  # 6 = Sunday
        # DST ends at 02:00 local IDT, which is 23:00 UTC the night before (Saturday)
        dst_end_utc = datetime(year, 10, dst_end_day - 1, 23, 0, 0, tzinfo=timezone.utc)
        return dt_utc < dst_end_utc

    return False


def get_pacific_date() -> str:
    """Get current date in US Pacific timezone with correct DST handling."""
    utc_now = datetime.now(timezone.utc)
    is_dst = is_us_pacific_dst(utc_now)
    offset = 7 if is_dst else 8  # PDT = UTC-7, PST = UTC-8
    pacific_now = utc_now - timedelta(hours=offset)
    return pacific_now.strftime("%Y-%m-%d")


def create_fresh_rate_state(date_str: str = None) -> Dict[str, Any]:
    """
    Create a new rate state for a fresh day.

    Args:
        date_str: Optional date string, defaults to current Pacific date

    Returns:
        Fresh rate state dictionary
    """
    if date_str is None:
        date_str = get_pacific_date()
    return {
        "date": date_str,
        "calls": 0,
        "alert_sent": False,
        "reset_time_utc": None,
        "last_api_check": None,
        "last_update": datetime.now(timezone.utc).isoformat(),
        "api_limit": 5000,
        "api_remaining": 5000
    }


def load_rate_state() -> Dict[str, Any]:
    """Load rate state from persistent file with migration support."""
    if RATE_FILE.exists():
        try:
            with open(RATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Add missing fields from older versions
            if "reset_time_utc" not in data:
                data["reset_time_utc"] = None
            if "last_api_check" not in data:
                data["last_api_check"] = None
            if "last_update" not in data:
                data["last_update"] = datetime.now(timezone.utc).isoformat()
            if "api_limit" not in data:
                data["api_limit"] = 5000
            if "api_remaining" not in data:
                data["api_remaining"] = 5000 - data.get("calls", 0)
            return data
        except (IOError, json.JSONDecodeError) as e:
            log(f"Error loading rate state: {e}")
    return create_fresh_rate_state()


def save_rate_state(rate_data: Dict[str, Any]) -> bool:
    """
    Save rate state to persistent file with atomic write and retry.

    Args:
        rate_data: Rate state dictionary to save

    Returns:
        True if saved successfully, False otherwise
    """
    # Check disk space
    has_space, free_mb = check_disk_space(RATE_FILE)
    if not has_space:
        log(f"WARNING: Low disk space ({free_mb}MB) - skipping rate state save")
        return False

    tmp_file = RATE_FILE.with_suffix('.tmp')
    for attempt in range(3):
        try:
            # Atomic write: temp file then rename
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(rate_data, f, indent=2)
            tmp_file.replace(RATE_FILE)
            return True
        except (IOError, OSError) as e:
            if attempt < 2:
                time.sleep(0.5)
            else:
                log(f"ERROR saving rate state after 3 attempts: {e}")
                # Remove temp file
                try:
                    if tmp_file.exists():
                        tmp_file.unlink()
                except (IOError, OSError):
                    pass
    return False


def get_seconds_until_reset(rate_data: Dict[str, Any]) -> int:
    """
    Calculate seconds until API quota resets.

    Args:
        rate_data: Rate state dictionary

    Returns:
        Seconds until reset
    """
    reset_time = rate_data.get("reset_time_utc")

    if reset_time:
        try:
            reset_dt = datetime.fromisoformat(reset_time.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = (reset_dt - now).total_seconds()
            if diff > 0:
                return int(diff)
        except (ValueError, TypeError) as e:
            log(f"Error parsing reset time: {e}")

    # Calculate time until midnight Pacific
    utc_now = datetime.now(timezone.utc)
    is_dst = is_us_pacific_dst(utc_now)
    reset_hour_utc = 7 if is_dst else 8

    next_reset = utc_now.replace(hour=reset_hour_utc, minute=0, second=0, microsecond=0)
    if utc_now.hour >= reset_hour_utc:
        next_reset += timedelta(days=1)

    return int((next_reset - utc_now).total_seconds())


def get_pacific_datetime() -> datetime:
    """Get current datetime in Pacific timezone (DST-aware)."""
    utc_now = datetime.now(timezone.utc)
    is_dst = is_us_pacific_dst(utc_now)
    offset = 7 if is_dst else 8
    return utc_now - timedelta(hours=offset)


def get_last_reset_time_utc() -> datetime:
    """Get the UTC time of the most recent daily reset (midnight Pacific)."""
    utc_now = datetime.now(timezone.utc)
    is_dst = is_us_pacific_dst(utc_now)
    reset_hour_utc = 7 if is_dst else 8  # Midnight Pacific in UTC

    last_reset = utc_now.replace(hour=reset_hour_utc, minute=0, second=0, microsecond=0)
    if utc_now.hour < reset_hour_utc:
        # We haven't hit today's reset yet, so last reset was yesterday
        last_reset -= timedelta(days=1)

    return last_reset


def get_minutes_since_reset() -> float:
    """Get minutes elapsed since the last daily reset."""
    last_reset = get_last_reset_time_utc()
    elapsed = datetime.now(timezone.utc) - last_reset
    return elapsed.total_seconds() / 60


def is_post_reset_window(window_minutes: int = 10) -> bool:
    """Check if we're in the critical window right after reset.

    This is the danger zone where eBay may return stale/cached data.
    """
    return get_minutes_since_reset() < window_minutes


def validate_rate_data(rate_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate rate data for sanity and detect stale/impossible states.

    Returns dict with:
        valid: bool - True if data passes all checks
        issues: list - Description of any problems found
        confidence: str - 'high', 'medium', 'low'
    """
    issues = []
    confidence = "high"

    calls = rate_data.get("calls", 0)
    api_remaining = rate_data.get("api_remaining", 5000)
    api_limit = rate_data.get("api_limit", 5000)
    last_update = rate_data.get("last_update")

    # Calculate implied usage from API
    implied_usage = api_limit - api_remaining

    # Check 1: Calls vs API mismatch
    # Allow some drift (up to 50 calls) due to timing
    if abs(calls - implied_usage) > 50:
        issues.append(f"Local calls ({calls}) != API implied ({implied_usage})")
        confidence = "medium"

    # Check 2: Too many calls for time since reset
    minutes_since_reset = get_minutes_since_reset()
    # Max realistic rate: ~2 calls per minute (with 21 searches, 30 sec each)
    max_possible_calls = int(minutes_since_reset * 2) + 100  # +100 buffer

    if calls > max_possible_calls and minutes_since_reset < 60:
        issues.append(f"Impossible: {calls} calls in {minutes_since_reset:.0f} min (max ~{max_possible_calls})")
        confidence = "low"

    # Check 3: Low remaining right after reset
    if minutes_since_reset < 30 and api_remaining < api_limit * 0.5:
        issues.append(f"Anomaly: Only {api_remaining} remaining just {minutes_since_reset:.0f} min after reset")
        confidence = "low"

    # Check 4: Data freshness
    if last_update:
        try:
            last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            update_age_minutes = (datetime.now(timezone.utc) - last_update_dt).total_seconds() / 60
            if update_age_minutes > 60:
                issues.append(f"Stale data: last update {update_age_minutes:.0f} min ago")
                confidence = "medium" if confidence == "high" else confidence
        except (ValueError, TypeError):
            pass

    # Check 5: Reset boundary crossed since last update
    if last_update:
        try:
            last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            last_reset = get_last_reset_time_utc()
            if last_update_dt < last_reset:
                issues.append("Data is from before the last reset!")
                confidence = "low"
        except (ValueError, TypeError):
            pass

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "confidence": confidence,
        "minutes_since_reset": minutes_since_reset
    }


def should_force_api_refresh(rate_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Determine if we should force an API refresh, overriding normal throttle.

    Returns:
        (should_refresh, reason)
    """
    validation = validate_rate_data(rate_data)

    # Force refresh if data confidence is low
    if validation["confidence"] == "low":
        return True, f"Low confidence data: {', '.join(validation['issues'])}"

    # Force refresh if in post-reset window and data looks anomalous
    if is_post_reset_window(10):
        api_remaining = rate_data.get("api_remaining", 5000)
        api_limit = rate_data.get("api_limit", 5000)
        if api_remaining < api_limit * 0.8:  # Less than 80% remaining right after reset
            return True, f"Post-reset window with anomalous remaining ({api_remaining}/{api_limit})"

    # Force refresh if we crossed a reset boundary since last check
    last_check = rate_data.get("last_api_check")
    if last_check:
        try:
            last_check_dt = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
            last_reset = get_last_reset_time_utc()
            if last_check_dt < last_reset:
                return True, "Reset boundary crossed since last API check"
        except (ValueError, TypeError):
            pass

    return False, ""


# Config

_cached_config: Optional[Dict[str, Any]] = None


def backup_config_daily() -> None:
    """Create daily rotating backup of config (keeps last 3 days)."""
    try:
        if not CONFIG_FILE.exists():
            return

        backup_dir = SCRIPT_DIR / "config_backups"
        backup_dir.mkdir(exist_ok=True)

        # Daily backup filename
        today = datetime.now().strftime("%Y-%m-%d")
        backup_file = backup_dir / f"ebay_config.{today}.bak"

        # Only backup once per day
        if not backup_file.exists():
            import shutil
            shutil.copy2(CONFIG_FILE, backup_file)
            log(f"Config backup created: {backup_file.name}")

            # Cleanup old backups (keep last 3)
            backups = sorted(backup_dir.glob("ebay_config.*.bak"), reverse=True)
            for old_backup in backups[3:]:
                old_backup.unlink()
                log(f"Removed old backup: {old_backup.name}")
    except Exception as e:
        log(f"Config backup failed: {e}")


def load_config() -> Dict[str, Any]:
    """Load config with fallback to last known good config."""
    global _cached_config
    try:
        backup_config_daily()
        with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)
        _cached_config = config  # Cache successful load
        return config
    except (IOError, json.JSONDecodeError) as e:
        log(f'ERROR loading config: {e}')
        if _cached_config:
            log('Using cached config from last successful load')
            return _cached_config
        return {}


# Connectivity

def check_internet() -> bool:
    """Connectivity check using eBay API endpoint."""
    import urllib.request
    import urllib.error

    try:
        # Only contact eBay - this app should only communicate with eBay
        req = urllib.request.Request("https://api.ebay.com", method="HEAD")
        urllib.request.urlopen(req, timeout=5)
        return True
    except (urllib.error.URLError, OSError):
        return False


# SMTP

def get_smtp_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get SMTP configuration from config file.
    Falls back to Gmail defaults if not specified.
    Auto-detects Outlook/Yahoo from sender email domain.
    """
    email_cfg = config.get("email", {})

    # Check for SMTP override in config
    smtp_host = email_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = email_cfg.get("smtp_port", 587)

    # Auto-detect from email domain if not specified
    sender = email_cfg.get("sender", "")
    if sender and smtp_host == "smtp.gmail.com":
        domain = sender.split('@')[-1].lower() if '@' in sender else ""
        if 'outlook' in domain or 'hotmail' in domain or 'live' in domain:
            smtp_host = "smtp-mail.outlook.com"
            smtp_port = 587
        elif 'yahoo' in domain:
            smtp_host = "smtp.mail.yahoo.com"
            smtp_port = 587

    return {
        'host': smtp_host,
        'port': smtp_port,
        'sender': sender,
        'password': email_cfg.get("password", ""),
        'recipient': email_cfg.get("recipient", "")
    }


def get_imap_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get IMAP configuration, auto-detecting provider from sender email domain."""
    sender = config.get("email", {}).get("sender", "")
    domain = sender.split('@')[-1].lower() if '@' in sender else ""
    if 'outlook' in domain or 'hotmail' in domain or 'live' in domain:
        return {'host': 'outlook.office365.com', 'port': 993}
    elif 'yahoo' in domain:
        return {'host': 'imap.mail.yahoo.com', 'port': 993}
    return {'host': 'imap.gmail.com', 'port': 993}


def gmail_cleanup_sent(sender: str, password: str, subject: str, timeout: int = 30) -> None:
    """Delete sent email from Gmail Sent Mail and Trash to keep inbox clean.

    Silently returns on any error (non-critical cleanup operation).
    """
    import imaplib
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", timeout=timeout)
        imap.login(sender, password)
        imap.select('"[Gmail]/Sent Mail"')
        safe_subject = subject.replace('\\', '\\\\').replace('"', '\\"')
        _, msgs = imap.search(None, f'SUBJECT "{safe_subject}"')
        if msgs[0]:
            for m in msgs[0].split():
                imap.store(m, "+FLAGS", "\\Deleted")
            imap.expunge()
        try:
            imap.select('"[Gmail]/Trash"')
            _, msgs = imap.search(None, f'SUBJECT "{safe_subject}"')
            if msgs[0]:
                for m in msgs[0].split():
                    imap.store(m, "+FLAGS", "\\Deleted")
                imap.expunge()
        except (imaplib.IMAP4.error, OSError):
            pass
        imap.logout()
    except Exception:
        pass  # Non-critical cleanup


# Module Info

def get_module_info() -> Dict[str, Any]:
    """Get info about this module."""
    return {
        'version': VERSION,
        'paths': {
            'config': str(CONFIG_FILE),
            'seen': str(SEEN_FILE),
            'log': str(LOG_FILE),
            'token': str(TOKEN_FILE),
            'rate': str(RATE_FILE),
            'heartbeat': str(HEARTBEAT_FILE),
        }
    }
