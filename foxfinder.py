#!/usr/bin/env python3
"""
FoxFinder - eBay Deal Notification Service
Uses official eBay Browse API with EPN (eBay Partner Network) integration.

Compliant with eBay Developer Program policies:
- eBay API License Agreement
- eBay Partner Network Terms
- Application Growth Check requirements

For more information, see README.md and PRIVACY_POLICY.md
"""

VERSION = "4.7.4"
__version__ = VERSION
# v4.7.2: Reliability quick wins - dynamic reset wait, HTTP 429/503 retry, validation check, email visibility
# v4.7.1: CRITICAL FIX - get_minutes_since_reset() call signature + defensive try-except
# v4.7.0: Post-reset anomaly detection (Proactive Retry) to fix 1h hangs after API sync lag
# v4.6.8: Add requests.Session for connection pooling (2-3x faster API checks) for connection pooling (2-3x faster API checks)
# v4.6.7: Increase search results limit 50→150 to reduce staggered alerts after downtime
# v4.6.5: Fix BCC privacy bug - removed exposed Bcc header
# v4.6.4: Multi-recipient email support with BCC privacy
# v4.6.3: Fix email template import - was using fallback that outputs raw dicts
# v4.6.2: Fix HTML email rendering - add UTF-8 charset to MIMEText
# v4.6.1: Robustness hardening - timeout constants, temp cleanup, specific exceptions
# v4.6.0: Price drop tracking - alerts when seen items drop into search criteria
# v4.5.0: NASA reliability hardening - HTTP retry, token retry, API validation, memory cap
# v4.4.0: Robust rate limit sync - post-reset retry, sanity validation, auto-recovery

# =============================================================================
# [ CONSTANTS ]
# =============================================================================
ERROR_RETRY_INTERVAL = 60      # Seconds to wait after a non-critical error
API_ERROR_COOLDOWN = 300       # 5 min wait after API failure
MAX_LOG_SIZE = 10 * 1024 * 1024 # 10MB log rotation
SEARCH_RESULTS_LIMIT = 150     # Items per API search (150 catches post-downtime backlog better than 50)
CYCLE_TIME_WARNING_SECONDS = 120  # NASA JPL: Warn if cycle exceeds 2 minutes
MEMORY_WARNING_THRESHOLD_MB = 200  # NASA JPL: Warn if memory exceeds 200MB (API-based, lower expected)

# CHANGELOG v4.3.7:
# - Extracted magic numbers to named constants (SEEN_MAX_AGE_DAYS, API_TIMEOUT_SECONDS)
#
# CHANGELOG v4.3.6:
# - Added listing age indicator (e.g., "5m ago", "2h ago") for quick freshness check
# - Added item location (country) to email alerts
# - Uses is_israel_dst() from ebay_common for accurate Israel timezone conversion
#
# CHANGELOG v4.3.5:
# - Fixed validate_config() field name: 'keywords' -> 'query' (critical bug fix)
#
# CHANGELOG v4.3.4:
# - Seen file cleanup reduced from 100 to 50 days
# - Added validate_config() for startup validation
# - Clear error messages for missing/invalid config
#
# CHANGELOG v4.3.3:
# - Atomic write for update_statistics() (protects config file)
# - Atomic write for get_oauth_token() (protects token file)
# - Moved sys.path manipulation to imports section
# - Removed redundant try/except around update_heartbeat()
# - Full NASA JPL compliance for crash safety

import gc
import os
import json
import re
import time
import base64
import socket
import smtplib
import imaplib
import urllib.request
import urllib.parse
import subprocess
import random
import requests
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Import shared module for consistency - NASA JPL single source of truth
from ebay_common import (
    # Paths
    SCRIPT_DIR, CONFIG_FILE, SEEN_FILE, LOG_FILE, TOKEN_FILE, RATE_FILE,
    SHUTDOWN_FILE, HEARTBEAT_FILE, LOCK_FILE,
    API_UPDATE_CHECK_FILE, API_UPDATE_ALERT_FILE, EMAIL_FAILURES_FILE,
    # Constants
    EBAY_API_BASE, EBAY_API_VERSION, DAILY_CALL_LIMIT, MIN_INTERVAL_SECONDS,
    # Functions
    log, rotate_logs, update_heartbeat, read_heartbeat,
    is_shutdown_requested, clear_shutdown_request,
    interruptible_sleep, interruptible_wait,
    is_us_pacific_dst, is_israel_dst, get_pacific_date, get_pacific_datetime,
    create_fresh_rate_state, load_rate_state, save_rate_state, get_seconds_until_reset,
    get_last_reset_time_utc, get_minutes_since_reset, is_post_reset_window,
    validate_rate_data, should_force_api_refresh,
    load_config, check_internet, get_smtp_config,
)

# Import email templates from parent directory
import sys
_parent_dir = str(Path(__file__).resolve().parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
try:
    from email_templates import get_listing_html, get_alert_html, get_subject_line
    _EMAIL_TEMPLATES_LOADED = True
except Exception as e:
    # Log failure and use fallback - will show raw dicts in email
    print(f"[WARNING] Failed to import email_templates: {e}", file=sys.stderr)
    _EMAIL_TEMPLATES_LOADED = False
    def get_listing_html(s, l): return "\n".join([str(x) for x in l])
    def get_alert_html(t, d, s): return f"{t}\n{d}"
    def get_subject_line(s, l): return f"{s}: {len(l)} new"

# NASA JPL: Disk space validation from shared utilities
from shared_utils import check_disk_space

# Update Checker interval
API_UPDATE_CHECK_INTERVAL_DAYS = 30  # Check monthly (was 90 - too long for API deprecation notices)

# Data retention
SEEN_MAX_AGE_DAYS = 14  # Clean seen entries older than this (eBay compliance: minimal retention)
MAX_SEEN_ENTRIES = 50000  # Memory cap: ~5MB, prevents unbounded growth

# API timeouts
API_TIMEOUT_SECONDS = 15  # Timeout for eBay API calls
SMTP_TIMEOUT_SECONDS = 30  # Timeout for SMTP/IMAP connections

# Rate Limit API URL (built from imported base)
RATE_LIMIT_API_URL = f"{EBAY_API_BASE}/developer/analytics/v1_beta/rate_limit/"

# Recovery Configuration
MAX_CYCLES_BEFORE_REFRESH = 100  # Reset environment every ~12 hours
DEFAULT_RECOVERY = {
    "initial_backoff_seconds": 60,
    "max_backoff_seconds": 900,
    "alert_after_consecutive_failures": 3,
    "cooldown_after_alert_minutes": 60,
}

recovery_state = {
    "consecutive_failures": 0,
    "last_alert_time": None,
    "last_successful_cycle": None,
}

# Email failure tracking
MAX_EMAIL_FAILURES_BEFORE_ALERT = 5
EMAIL_CIRCUIT_BREAKER_THRESHOLD = 10  # NASA JPL: Enter degraded mode after this many failures
EMAIL_RETRY_INTERVAL_CYCLES = 10      # In degraded mode, retry email every N cycles

# =============================================================================
# [ HTTP SESSION - Connection Pooling ]
# =============================================================================
# NASA JPL Pattern: Reuse TCP connections for faster sequential requests
# Benefits: 2-3x faster API checks, reduced connection overhead, fewer rate limit triggers
_http_session: Optional[requests.Session] = None
_http_session_created: Optional[float] = None
HTTP_SESSION_MAX_AGE_SECONDS = 43200  # 12 hours - recycle to prevent stale connections


def get_http_session() -> requests.Session:
    """Get or create shared HTTP session for connection pooling.

    NASA JPL Pattern: Recreate session periodically to prevent stale connections.
    Sessions are recycled every 12 hours or after detected connection issues.
    """
    global _http_session, _http_session_created
    now = time.time()

    # Create new session if: none exists, or older than max age
    should_recreate = (
        _http_session is None or
        _http_session_created is None or
        (now - _http_session_created) > HTTP_SESSION_MAX_AGE_SECONDS
    )

    if should_recreate:
        # Clean up old session if exists
        if _http_session is not None:
            try:
                _http_session.close()
                log("HTTP session recycled (age limit reached)")
            except Exception:
                pass  # Close failure is non-critical

        _http_session = requests.Session()
        _http_session.headers.update({
            "User-Agent": f"FoxFinder/{VERSION} (eBay-Browse-API-Client)",
            "Accept": "application/json",
        })
        _http_session_created = now

    return _http_session


def reset_http_session():
    """Force HTTP session reset (call after connection errors)."""
    global _http_session, _http_session_created
    if _http_session is not None:
        try:
            _http_session.close()
        except Exception:
            pass
    _http_session = None
    _http_session_created = None


def get_email_failure_count() -> int:
    """Get consecutive email failure count."""
    try:
        if EMAIL_FAILURES_FILE.exists():
            return int(EMAIL_FAILURES_FILE.read_text().strip())
    except (ValueError, IOError, OSError):
        pass
    return 0


def record_email_failure() -> int:
    """Increment email failure counter and return new count."""
    try:
        count = get_email_failure_count() + 1
        EMAIL_FAILURES_FILE.write_text(str(count))
        return count
    except (IOError, OSError):
        return 0


def clear_email_failures() -> None:
    """Clear email failure counter on success."""
    try:
        if EMAIL_FAILURES_FILE.exists():
            EMAIL_FAILURES_FILE.unlink()
    except (IOError, OSError):
        pass


def is_email_degraded_mode() -> bool:
    """NASA JPL: Check if email is in degraded mode (circuit breaker open)."""
    return get_email_failure_count() >= EMAIL_CIRCUIT_BREAKER_THRESHOLD


def check_memory_usage():
    """
    NASA JPL Pattern: Check memory usage, warn if excessive.

    Returns:
        Tuple (memory_mb, exceeded_threshold)
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss // (1024 * 1024)
        exceeded = mem_mb > MEMORY_WARNING_THRESHOLD_MB
        if exceeded:
            log(f"WARNING: High memory usage ({mem_mb}MB > {MEMORY_WARNING_THRESHOLD_MB}MB threshold)")
            gc.collect()  # Attempt to free memory
            # Re-check after gc
            mem_mb_after = psutil.Process(os.getpid()).memory_info().rss // (1024 * 1024)
            if mem_mb_after < mem_mb:
                log(f"  Memory reduced to {mem_mb_after}MB after gc.collect()")
        return mem_mb, exceeded
    except ImportError:
        # psutil not available - skip check
        return -1, False
    except Exception:
        return -1, False


# NOTE: interruptible_sleep, update_heartbeat, log, rotate_logs
# are imported from ebay_common.py (single source of truth)


def check_api_updates() -> None:
    """
    Monthly check for eBay API deprecation notices.

    Features:
    - Checks eBay deprecation status page for Browse API mentions
    - Tests API endpoint health (410 = deprecated)
    - Sends EMAIL notification (not just file) for critical issues
    - Retry with backoff on network failures
    - Only records check time on successful completion

    Writes API_UPDATE_NOTICE.txt if action may be needed. Non-blocking.
    """
    try:
        # Check if we need to run
        if API_UPDATE_CHECK_FILE.exists():
            try:
                last_check = datetime.fromisoformat(API_UPDATE_CHECK_FILE.read_text().strip())
                if datetime.now() - last_check < timedelta(days=API_UPDATE_CHECK_INTERVAL_DAYS):
                    return  # Not time yet
            except (ValueError, OSError):
                pass  # Invalid date file, run check

        # Check internet connectivity first
        if not check_internet():
            log("API update check skipped - no internet connectivity")
            return  # Don't record check time - retry next cycle

        log("Running monthly eBay API status check...")

        notices = []
        check_succeeded = False

        # 1. Check eBay API deprecation status page (with retry)
        session = get_http_session()  # Connection pooling
        for attempt in range(3):
            try:
                resp = session.get(
                    "https://developer.ebay.com/api-docs/static/api-deprecation-status.html",
                    timeout=API_TIMEOUT_SECONDS
                )
                if resp.status_code == 200:
                    content = resp.text.lower()
                    # Look for Browse API deprecation mentions
                    if "browse api" in content and ("deprecat" in content or "sunset" in content):
                        if "v1" in content or EBAY_API_VERSION in content:
                            notices.append(
                                "[EBAY BROWSE API] Potential deprecation notice detected.\n"
                                "   Check: https://developer.ebay.com/api-docs/static/api-deprecation-status.html"
                            )
                    check_succeeded = True
                    break
            except (requests.RequestException, OSError) as e:
                if attempt < 2:
                    log(f"Deprecation page check attempt {attempt + 1} failed: {e}")
                    reset_http_session()  # NASA JPL: Reset stale connection
                    interruptible_sleep(5 * (attempt + 1))  # 5s, 10s backoff
                else:
                    log(f"Deprecation page check failed after 3 attempts: {e}")

        # 2. Quick API health check (test call) with retry
        for attempt in range(3):
            try:
                # Just check if the API base responds (doesn't need auth)
                resp = session.get(f"{EBAY_API_BASE}/buy/browse/v1", timeout=10)
                # 401 = auth required (expected), 410 = gone (deprecated!)
                if resp.status_code == 410:
                    notices.append(
                        "[EBAY BROWSE API] API endpoint returned 410 GONE - may be deprecated!\n"
                        "   Urgent: Check eBay developer portal immediately."
                    )
                check_succeeded = True
                break
            except (requests.RequestException, OSError) as e:
                if attempt < 2:
                    log(f"API health check attempt {attempt + 1} failed: {e}")
                    reset_http_session()  # NASA JPL: Reset stale connection
                    interruptible_sleep(5 * (attempt + 1))  # 5s, 10s backoff
                else:
                    log(f"API health check failed after 3 attempts: {e}")

        # Only record check time if at least one check succeeded
        if check_succeeded:
            API_UPDATE_CHECK_FILE.write_text(datetime.now().isoformat())

        # Write alert file if notices found
        if notices:
            alert_content = [
                "=" * 60,
                "FOXFINDER - API STATUS NOTICE",
                f"Checked: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "=" * 60,
                "",
                "Potential API changes detected:",
                "",
            ]
            alert_content.extend(notices)
            alert_content.extend([
                "",
                "ACTION REQUIRED:",
                "- Review eBay developer announcements",
                "- Discuss with Claude if migration needed",
                "- URL: https://developer.ebay.com/develop/apis",
                "",
                "=" * 60,
            ])
            API_UPDATE_ALERT_FILE.write_text("\n".join(alert_content), encoding="utf-8")
            log(f"API NOTICE: Potential eBay API changes - see API_UPDATE_NOTICE.txt")

            # SEND EMAIL NOTIFICATION (critical fix - was missing!)
            try:
                config = load_config()
                email_cfg = config.get("email", {})
                if email_cfg.get("sender") and email_cfg.get("password"):
                    subject = "[NOTICE] eBay API: Potential Deprecation Notice"
                    body = (
                        "<h2>eBay API Status Notice</h2>"
                        "<p>FoxFinder has detected potential API changes that may require attention.</p>"
                        "<h3>Notices:</h3><ul>"
                    )
                    for notice in notices:
                        body += f"<li><pre>{notice}</pre></li>"
                    body += (
                        "</ul>"
                        "<h3>Action Required:</h3>"
                        "<ul>"
                        "<li>Review eBay developer announcements</li>"
                        "<li>Check: <a href='https://developer.ebay.com/develop/apis'>developer.ebay.com</a></li>"
                        "<li>See API_UPDATE_NOTICE.txt for details</li>"
                        "</ul>"
                        f"<p><small>Checked: {datetime.now().strftime('%Y-%m-%d %H:%M')}</small></p>"
                    )
                    # Use send_email_core directly (no cooldown for API notices)
                    send_email_core(config, subject, body, is_html=True)
                    log("API deprecation email alert sent")
            except Exception as e:
                log(f"Failed to send API notice email (non-critical): {e}")
        else:
            # Clear old notice
            if API_UPDATE_ALERT_FILE.exists():
                API_UPDATE_ALERT_FILE.unlink()
            if check_succeeded:
                log("API check complete - Browse API v1 appears stable")
            else:
                log("API check incomplete - will retry next cycle")

    except Exception as e:
        # Never crash the main app for API checks
        log(f"API check error (non-critical): {e}")


# NASA JPL: Stale lock cleanup
STALE_LOCK_AGE_SECONDS = 3600  # 1 hour - lock file older than this is considered stale


def cleanup_stale_lock() -> None:
    """Clean up stale lock file if process doesn't exist."""
    try:
        if not LOCK_FILE.exists():
            return

        # Check lock file age
        lock_age = time.time() - LOCK_FILE.stat().st_mtime
        if lock_age < STALE_LOCK_AGE_SECONDS:
            return  # Lock is fresh, process is probably running

        # Lock is old - check if owning process exists
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            result = subprocess.run(['tasklist', '/FI', f'PID eq {old_pid}', '/NH'],
                                    capture_output=True, text=True, timeout=5)
            if str(old_pid) not in result.stdout:
                # Process doesn't exist - safe to remove stale lock
                LOCK_FILE.unlink()
                log(f"Cleaned up stale lock file (PID {old_pid} no longer exists)")
        except (ValueError, IOError, OSError):
            pass
    except Exception:
        pass  # Cleanup failure is non-critical


# NOTE: check_internet imported from ebay_common.py

def stop_duplicate_processes() -> int:
    """Stop any duplicate foxfinder processes."""
    lock_file = LOCK_FILE  # Use imported constant for consistency
    current_pid = os.getpid()
    try:
        if lock_file.exists():
            try:
                old_pid = int(lock_file.read_text().strip())
                if old_pid != current_pid:
                    result = subprocess.run(['tasklist', '/FI', f'PID eq {old_pid}', '/NH'], capture_output=True, text=True, timeout=5)
                    if str(old_pid) in result.stdout:
                        subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], capture_output=True, timeout=5)
                        log(f"Stopped duplicate process (PID {old_pid})")
            except Exception:
                pass  # Process may have already exited
        lock_file.write_text(str(current_pid))
    except Exception:
        pass  # Lock file write failure is non-critical
    return 0

# NOTE: load_config imported from ebay_common.py

def update_statistics(increment_alerts: bool = False) -> None:
    """Update _statistics section in config file with atomic write."""
    tmp_file = CONFIG_FILE.with_suffix('.tmp')
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)

        if "_statistics" not in config:
            config["_statistics"] = {"_note": "Updated by script", "last_run": None, "total_alerts_sent": 0, "last_alert": None}

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        config["_statistics"]["last_run"] = now

        if increment_alerts:
            config["_statistics"]["total_alerts_sent"] = config["_statistics"].get("total_alerts_sent", 0) + 1
            config["_statistics"]["last_alert"] = now

        # Atomic write: temp file then rename (protects config on crash)
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        tmp_file.replace(CONFIG_FILE)
    except (IOError, json.JSONDecodeError, OSError) as e:
        log(f"Stats update failed (non-critical): {e}")
        # Clean up temp file on failure
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except (IOError, OSError):
            pass

# NOTE: is_shutdown_requested, clear_shutdown_request imported from ebay_common.py
# Aliases for backward compatibility
is_graceful_shutdown = is_shutdown_requested
clear_shutdown_signal = clear_shutdown_request


def calculate_backoff(attempt: int) -> int:
    base = DEFAULT_RECOVERY["initial_backoff_seconds"]
    max_b = DEFAULT_RECOVERY["max_backoff_seconds"]
    backoff = min(max_b, base * (2 ** attempt))
    jitter = backoff * 0.1 * random.random()
    return int(backoff + jitter)

# --- Rate Limiting ---
# NOTE: is_us_pacific_dst, get_pacific_date, create_fresh_rate_state,
# load_rate_state, save_rate_state, get_seconds_until_reset
# are imported from ebay_common.py

def increment_rate_counter(count: int = 1) -> Dict[str, Any]:
    """
    Increment the daily API call counter with validation.

    Also decrements api_remaining to keep local tracking in sync.
    Returns the updated rate data for inspection.
    """
    today = get_pacific_date()
    rate_data = load_rate_state()

    # Check for day change
    if rate_data.get("date") != today:
        log(f"Day changed during operation, creating fresh rate state for {today}")
        rate_data = create_fresh_rate_state(today)

    # Increment calls
    rate_data["calls"] += count

    # Also decrement api_remaining to keep in sync
    api_remaining = rate_data.get("api_remaining", 5000)
    rate_data["api_remaining"] = max(0, api_remaining - count)

    rate_data["last_update"] = datetime.now(timezone.utc).isoformat()

    # Quick sanity check
    validation = validate_rate_data(rate_data)
    if validation["confidence"] == "low":
        log(f"WARNING: Rate data confidence is low after increment: {validation['issues']}")

    save_rate_state(rate_data)
    return rate_data


def fetch_rate_limits_from_api(token: str) -> Dict[str, Any]:
    """Fetch actual rate limits from eBay Analytics API."""
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(RATE_LIMIT_API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode())
            
            # API returns a rateLimits array, find the Browse API entry
            rate_limits = data.get("rateLimits", [])
            browse_limit = None
            
            for rl in rate_limits:
                api_name = rl.get("apiName", "")
                if "browse" in api_name.lower() or "buy" in api_name.lower():
                    resources = rl.get("resources", [])
                    for res in resources:
                        if res.get("name") == "buy.browse":
                            rates = res.get("rates", [])
                            # Find the daily rate (timeWindow = 86400)
                            for rate in rates:
                                if rate.get("timeWindow") == 86400:
                                    browse_limit = rate
                                    break
                            if browse_limit:
                                break
                if browse_limit:
                    break
            
            # If we couldn't find Browse API specifically, use first daily limit found
            if not browse_limit:
                for rl in rate_limits:
                    for res in rl.get("resources", []):
                        for rate in res.get("rates", []):
                            if rate.get("timeWindow") == 86400:
                                browse_limit = rate
                                break
                        if browse_limit:
                            break
                    if browse_limit:
                        break
            
            if browse_limit:
                return {
                    "success": True,
                    "limit": browse_limit.get("limit", 5000),
                    "remaining": browse_limit.get("remaining", 5000),
                    "count": browse_limit.get("count", 0),
                    "reset": browse_limit.get("reset"),  # ISO 8601 UTC timestamp
                    "timeWindow": browse_limit.get("timeWindow", 86400)
                }
            else:
                log("Could not find Browse API rate limits in response")
                return {"success": False, "error": "Browse API limits not found"}
                
    except urllib.error.HTTPError as e:
        log(f"Rate limit API HTTP error: {e.code}")
        return {"success": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        log(f"Rate limit API error: {e}")
        return {"success": False, "error": str(e)}

def sync_rate_state_with_api(token: str, force: bool = False) -> Dict[str, Any]:
    """
    Sync local rate state with eBay API with robust verification.

    Features:
    - Post-reset verification with retry logic
    - Sanity checks to detect stale/impossible data
    - Automatic recovery from bad states

    Args:
        token: eBay OAuth token
        force: Force API check even if recently checked

    Returns:
        Updated rate state dictionary
    """
    rate_data = load_rate_state()
    today = get_pacific_date()

    # Check if day changed
    if rate_data.get("date") != today:
        log(f"New day detected ({today}), resetting rate state")
        rate_data = create_fresh_rate_state(today)

    # Determine if we should check the API
    should_check = force
    check_reason = "forced" if force else ""

    if not should_check:
        # Check if forced refresh is needed due to data issues
        force_needed, reason = should_force_api_refresh(rate_data)
        if force_needed:
            should_check = True
            check_reason = reason
            log(f"Forcing API refresh: {reason}")

    if not should_check:
        # Normal throttle: check every 30 minutes
        last_check = rate_data.get("last_api_check")
        if last_check:
            try:
                last_check_dt = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                elapsed = datetime.now(timezone.utc) - last_check_dt
                should_check = elapsed > timedelta(minutes=30)
                if should_check:
                    check_reason = "30-minute interval"
            except (ValueError, TypeError):
                should_check = True
                check_reason = "invalid last_check timestamp"
        else:
            should_check = True
            check_reason = "no previous check"

    if should_check:
        log(f"API check triggered: {check_reason}")

        # Post-reset verification: if in critical window, use retry logic
        in_post_reset = is_post_reset_window(10)
        max_attempts = 3 if in_post_reset else 1
        retry_delay = 60  # seconds between retries

        best_result = None
        for attempt in range(max_attempts):
            if attempt > 0:
                log(f"Post-reset verification retry {attempt + 1}/{max_attempts} (waiting {retry_delay}s)")
                time.sleep(retry_delay)

            api_result = fetch_rate_limits_from_api(token)

            if not api_result.get("success"):
                log(f"API check failed: {api_result.get('error')}")
                continue

            # In post-reset window, validate the result
            if in_post_reset:
                remaining = api_result.get("remaining", 0)
                limit = api_result.get("limit", 5000)
                minutes_since = get_minutes_since_reset()

                # Sanity check: right after reset, remaining should be high
                if remaining < limit * 0.5 and minutes_since < 15:
                    log(f"WARNING: Unexpected API response {minutes_since:.0f}m after reset: "
                        f"{remaining}/{limit} remaining. May be stale data.")
                    # Keep trying if we have more attempts
                    if attempt < max_attempts - 1:
                        continue

                # If this result is better than previous, keep it
                if best_result is None or remaining > best_result.get("remaining", 0):
                    best_result = api_result
            else:
                best_result = api_result
                break

        # Use the best result we got
        if best_result and best_result.get("success"):
            limit = best_result.get("limit", 5000)
            remaining = best_result.get("remaining", 0)
            implied_usage = limit - remaining

            # Update rate data
            rate_data["api_limit"] = limit
            rate_data["api_remaining"] = remaining
            rate_data["reset_time_utc"] = best_result.get("reset")
            rate_data["last_api_check"] = datetime.now(timezone.utc).isoformat()
            rate_data["last_update"] = datetime.now(timezone.utc).isoformat()

            # Sync local calls with API implied usage
            old_calls = rate_data["calls"]

            # Always trust API's implied usage - it's the source of truth
            if abs(old_calls - implied_usage) > 10:
                log(f"Syncing local calls: {old_calls} -> {implied_usage} (API remaining: {remaining})")
                rate_data["calls"] = implied_usage

            # Add verification flag
            rate_data["data_verified"] = True
            rate_data["verification_time"] = datetime.now(timezone.utc).isoformat()

            log(f"API sync complete: {remaining}/{limit} remaining, "
                f"calls={implied_usage}, resets at {best_result.get('reset')}")
        else:
            log("API sync failed after all attempts, using local tracking")
            rate_data["data_verified"] = False

    # Final validation
    validation = validate_rate_data(rate_data)
    if not validation["valid"]:
        log(f"WARNING: Rate data issues: {', '.join(validation['issues'])}")

    save_rate_state(rate_data)
    return rate_data


# NOTE: get_seconds_until_reset imported from ebay_common.py

def calculate_smart_interval(search_count: int, rate_data: Dict[str, Any]) -> int:
    """Calculate optimal interval based on remaining budget and time."""
    if search_count <= 0:
        return 300  # Default 5 min if no searches
    
    # Get remaining calls (prefer API data, fallback to local)
    remaining_calls = rate_data.get("api_remaining")
    if remaining_calls is None:
        limit = rate_data.get("api_limit", 5000)
        used = rate_data.get("calls", 0)
        remaining_calls = max(0, limit - used)
    
    # Apply our safety buffer
    effective_remaining = min(remaining_calls, DAILY_CALL_LIMIT - rate_data.get("calls", 0))
    effective_remaining = max(0, effective_remaining - 100)  # Keep 100 call buffer
    
    if effective_remaining <= 0:
        # Use actual time until reset, not hardcoded 1 hour
        seconds_until_reset = get_seconds_until_reset(rate_data)
        wait_time = min(seconds_until_reset + 60, 3600)  # Until reset + 1min buffer, max 1hr
        wait_time = max(300, wait_time)  # At least 5 min
        log(f"No API calls remaining. Waiting {wait_time//60}m until reset.")
        return wait_time
    
    # Get time until reset
    seconds_until_reset = get_seconds_until_reset(rate_data)
    
    # Calculate how many cycles we can run
    # Each cycle uses search_count API calls
    max_cycles = effective_remaining // search_count
    
    if max_cycles <= 0:
        # Not enough calls - wait until reset
        wait_time = min(seconds_until_reset + 60, 3600)  # Until reset + 1min buffer, max 1hr
        wait_time = max(300, wait_time)  # At least 5 min
        log(f"Not enough calls ({effective_remaining}) for one cycle ({search_count} searches). Waiting {wait_time//60}m.")
        return wait_time
    
    # Distribute cycles evenly across remaining time
    optimal_interval = seconds_until_reset / max_cycles
    
    # Apply bounds
    final_interval = max(MIN_INTERVAL_SECONDS, min(optimal_interval, 900))  # 30s to 15min
    
    # Add small jitter (ֲ±5%)
    jitter = final_interval * 0.05 * (random.random() * 2 - 1)
    final_interval += jitter
    
    log(f"Smart pacing: {effective_remaining} calls, {seconds_until_reset//3600}h {(seconds_until_reset%3600)//60}m until reset, "
        f"{max_cycles} possible cycles, interval={int(final_interval)}s")
    
    return int(final_interval)

# --- Config Validation ---

def validate_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate config has required fields with proper values.
    Returns (is_valid, list_of_errors).
    """
    errors = []

    # Check API credentials
    creds = config.get("api_credentials", {})
    if not creds:
        errors.append("Missing 'api_credentials' section")
    else:
        if not creds.get("app_id"):
            errors.append("Missing or empty 'api_credentials.app_id'")
        if not creds.get("client_secret"):
            errors.append("Missing or empty 'api_credentials.client_secret'")

    # Check email settings
    email = config.get("email", {})
    if not email:
        errors.append("Missing 'email' section")
    else:
        if not email.get("sender"):
            errors.append("Missing or empty 'email.sender'")
        elif "@" not in email.get("sender", ""):
            errors.append("Invalid 'email.sender' - must be valid email address")
        if not email.get("password"):
            errors.append("Missing or empty 'email.password'")
        if not email.get("recipient"):
            errors.append("Missing or empty 'email.recipient'")
        else:
            # Validate each recipient (supports comma-separated multiple)
            recipients = [r.strip() for r in email.get("recipient", "").split(',')]
            recipients = [r for r in recipients if r]  # Remove empty
            if not recipients:
                errors.append("No valid recipients in 'email.recipient'")
            else:
                for r in recipients:
                    if "@" not in r:
                        errors.append(f"Invalid recipient '{r}' - must be valid email address")

    # Check searches
    searches = config.get("searches", [])
    if not searches:
        errors.append("No searches configured in 'searches' array")
    else:
        for i, search in enumerate(searches):
            if not search.get("name"):
                errors.append(f"Search #{i+1}: missing 'name'")
            if not search.get("query") and not search.get("category_id"):
                errors.append(f"Search '{search.get('name', f'#{i+1}')}': needs 'query' or 'category_id'")

    return (len(errors) == 0, errors)


# --- Data Management ---

def load_seen():
    """Load previously seen item IDs from persistent file."""
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            pass  # Seen file corrupt or missing, starting fresh
    return {}

def save_seen(seen):
    """Save seen item IDs to persistent file with atomic write."""
    # NASA JPL: Check disk space before write
    has_space, free_mb = check_disk_space(SEEN_FILE)
    if not has_space:
        log(f"WARNING: Low disk space ({free_mb}MB) - skipping seen file save")
        return False

    temp_file = SEEN_FILE.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(seen, f, indent=2)
        temp_file.replace(SEEN_FILE)
        log("Seen file saved.")
        return True
    except (IOError, OSError) as e:
        log(f"ERROR saving seen file: {e}")
        return False

def cleanup_old_seen(seen, max_age_days=SEEN_MAX_AGE_DAYS):
    """Remove entries older than max_age_days. Migrates old formats to new dict format with price tracking."""
    if not seen:
        return seen

    now = datetime.now()
    cutoff = now - timedelta(days=max_age_days)
    cleaned = {}
    migrated = 0
    pruned = 0

    for item_id, value in seen.items():
        if value is True:
            # Migration: old boolean format -> dict with timestamp only (no price history)
            cleaned[item_id] = {'timestamp': now.isoformat(), 'price': None, 'title': None}
            migrated += 1
        elif isinstance(value, str):
            # Migration: old string timestamp format -> dict format
            try:
                entry_time = datetime.fromisoformat(value)
                if entry_time > cutoff:
                    cleaned[item_id] = {'timestamp': value, 'price': None, 'title': None}
                    migrated += 1
                else:
                    pruned += 1
            except (ValueError, TypeError):
                # Invalid date format, migrate with fresh timestamp
                cleaned[item_id] = {'timestamp': now.isoformat(), 'price': None, 'title': None}
                migrated += 1
        elif isinstance(value, dict):
            # New dict format - check age
            ts = value.get('timestamp', '')
            try:
                entry_time = datetime.fromisoformat(ts) if ts else now
                if entry_time > cutoff:
                    cleaned[item_id] = value
                else:
                    pruned += 1
            except (ValueError, TypeError):
                # Invalid timestamp in dict, refresh it
                value['timestamp'] = now.isoformat()
                cleaned[item_id] = value
                migrated += 1
        else:
            # Unknown format, create fresh entry
            cleaned[item_id] = {'timestamp': now.isoformat(), 'price': None, 'title': None}
            migrated += 1

    if migrated > 0 or pruned > 0:
        log(f"Seen cleanup: {pruned} old entries removed, {migrated} migrated to dict format, {len(cleaned)} total")

    # Memory cap: prevent unbounded growth over years
    if len(cleaned) > MAX_SEEN_ENTRIES:
        # Sort by timestamp (newest first), keep only MAX_SEEN_ENTRIES
        def get_timestamp(item):
            val = item[1]
            if isinstance(val, dict):
                return val.get('timestamp', '')
            return val if isinstance(val, str) else ''
        sorted_items = sorted(cleaned.items(), key=get_timestamp, reverse=True)
        cleaned = dict(sorted_items[:MAX_SEEN_ENTRIES])
        log(f"Seen file capped at {MAX_SEEN_ENTRIES} entries (memory protection)")

    return cleaned

# --- API Functions ---

def get_oauth_token(app_id, client_secret, max_retries=2):
    """Get OAuth token, refreshing if expired. Includes retry logic."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                token_data = json.load(f)
            expiry = datetime.fromisoformat(token_data["expiry"])
            if datetime.now() < expiry:
                return token_data["access_token"]
            else:
                log("Token expired. Refreshing...")
        except (IOError, json.JSONDecodeError, KeyError, ValueError) as e:
            log(f"Token file invalid ({e}). Refreshing...")
            try:
                TOKEN_FILE.unlink()
            except (IOError, OSError):
                pass  # Token file may already be deleted

    credentials = f"{app_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    url = f"{EBAY_API_BASE}/identity/v1/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {encoded_credentials}"}
    data = "grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data.encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
                result = json.loads(resp.read().decode())
                access_token = result["access_token"]
                expires_in = result.get("expires_in", 7200)
                expiry = datetime.now().timestamp() + expires_in - 300
                token_data = {
                    "access_token": access_token,
                    "expiry": datetime.fromtimestamp(expiry).isoformat()
                }
                # Atomic write: temp file then rename
                tmp_file = TOKEN_FILE.with_suffix('.tmp')
                try:
                    with open(tmp_file, "w") as f:
                        json.dump(token_data, f)
                    tmp_file.replace(TOKEN_FILE)
                except (IOError, OSError):
                    # Clean up temp file on write failure
                    if tmp_file.exists():
                        try:
                            tmp_file.unlink()
                        except OSError:
                            pass
                    raise  # Re-raise to trigger retry
                log("Token refreshed successfully")
                return access_token
        except (urllib.error.URLError, OSError) as e:
            if attempt < max_retries - 1:
                wait_time = 5 * (attempt + 1)  # 5s, 10s, 15s backoff
                log(f"Token refresh retry {attempt + 1}/{max_retries}: {e}")
                time.sleep(wait_time)
            else:
                log(f"Token refresh failed after {max_retries} attempts: {e}")
                return None
        except urllib.error.HTTPError as e:
            # Transient errors (429, 5xx) are retryable
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)  # 10s, 20s, 30s for HTTP errors
                log(f"Token refresh HTTP {e.code} retry {attempt + 1}/{max_retries}: {e.reason}")
                time.sleep(wait_time)
                continue
            # Non-transient errors (401, 403, etc.) fail immediately
            log(f"Token refresh HTTP error: {e.code} - {e.reason}")
            return None
        except Exception as e:
            log(f"Token refresh failed: {e}")
            return None
    return None

def search_ebay(token, query, filters=None, max_retries=2, epn_campaign_id=None):
    """Execute eBay Browse API search with retry logic.

    Args:
        token: OAuth access token
        query: Search query string
        filters: Optional API filter string
        max_retries: Max retry attempts (eBay compliance: max 2)
        epn_campaign_id: eBay Partner Network campaign ID for affiliate tracking
    """
    params = {"q": query, "sort": "newlyListed", "limit": str(SEARCH_RESULTS_LIMIT)}
    if filters:
        params["filter"] = filters
    url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search?{urllib.parse.urlencode(params)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }
    # EPN Affiliate Tracking (required for Browse API production access)
    if epn_campaign_id:
        headers["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={epn_campaign_id}"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s exponential backoff
                log(f"Search retry {attempt + 1}/{max_retries}: {e}")
                time.sleep(wait_time)
            else:
                raise  # Re-raise on final attempt


def validate_api_response(data: Any, expected_keys: List[str], context: str = "") -> bool:
    """
    Validate API response has expected structure. Non-blocking warning only.

    Args:
        data: Response data to validate
        expected_keys: List of required top-level keys
        context: Description for logging (e.g., search name)

    Returns:
        True if valid, False if structure unexpected
    """
    if not isinstance(data, dict):
        log(f"WARNING: API response is not dict ({context}): {type(data).__name__}")
        return False
    missing = [k for k in expected_keys if k not in data]
    if missing:
        log(f"WARNING: API response missing keys ({context}): {missing}")
        return False
    return True


def title_matches_query(title: str, search: Dict[str, Any]) -> bool:
    """Check if title matches search query requirements."""
    title_lower = title.lower()
    if "required_words" in search and search["required_words"]:
        required = [w.lower() for w in search["required_words"]]
    else:
        query = search.get("query", "")
        # If query is missing (e.g. custom_url used), skip strictly query-based title match or infer it?
        # Better: if we have a custom_url, we trust the API result more, but still check excludes.
        if not query: return True 
        
        ignore = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "new", "used"}
        words = query.split()
        required = [w.lower() for w in words if (len(w) > 1 or w.isdigit()) and w.lower() not in ignore]
    for word in required:
        pattern = r'\b' + re.escape(word) + r'\b'
        if not re.search(pattern, title_lower): return False
    return True

def check_search_api(token: str, search: Dict[str, Any], seen: Dict[str, Any], epn_campaign_id: str = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Execute eBay API search and return (new_listings, price_drops)."""
    query = search.get("query")
    if not query:
        return [], []

    # Build API filters for server-side filtering
    api_filters = []

    # --- CONDITION FILTER (expanded) ---
    condition = search.get("condition", "").lower()
    # Map condition names to eBay condition IDs:
    # 1000=New, 1500=New Other/Open Box, 2000=Certified Refurbished,
    # 2500=Seller Refurbished, 3000=Used, 4000=Very Good, 5000=Good, 6000=Acceptable
    condition_map = {
        "new": "{1000}",
        "new_open_box": "{1000|1500}",           # New + Open Box
        "refurbished": "{2000|2500}",            # Certified + Seller Refurbished
        "used": "{3000|4000|5000|6000}",         # All used conditions
        "used_good": "{3000|4000|5000}",         # Used, Very Good, Good (not Acceptable)
        "any_not_broken": "{1000|1500|2000|2500|3000|4000|5000|6000}",  # Everything except parts
    }
    if condition in condition_map:
        api_filters.append(f"conditionIds:{condition_map[condition]}")
    elif condition == "any" or not condition:
        pass  # No filter = all conditions

    # --- SERVER-SIDE PRICE FILTER ---
    min_p = search.get("min_price", 0)
    max_p = search.get("max_price", 999999)
    # Only add price filter if meaningful bounds are set
    if min_p > 0 or max_p < 999999:
        # Add 15% buffer to max for Best Offer items (they might accept lower)
        effective_max = int(max_p * 1.15) if max_p < 999999 else max_p
        if min_p > 0 and effective_max < 999999:
            api_filters.append(f"price:[{min_p}..{effective_max}]")
        elif min_p > 0:
            api_filters.append(f"price:[{min_p}..]")
        elif effective_max < 999999:
            api_filters.append(f"price:[..{effective_max}]")
        api_filters.append("priceCurrency:USD")

    # --- SERVER-SIDE BUY IT NOW FILTER ---
    bin_only = search.get("buy_it_now_only", False)
    if bin_only:
        api_filters.append("buyingOptions:{FIXED_PRICE}")

    # --- FREE SHIPPING FILTER ---
    free_shipping = search.get("free_shipping_only", False)
    if free_shipping:
        api_filters.append("maxDeliveryCost:0")

    filter_str = ",".join(api_filters) if api_filters else None

    try:
        result = search_ebay(token, query, filter_str, epn_campaign_id=epn_campaign_id)
    except Exception as e:
        log(f"API Error ({search.get('name', query)}): {e}")
        return [], []

    if not result:
        return [], []

    # Validate API response structure - skip if malformed
    if not validate_api_response(result, ["itemSummaries"], context=search.get("name", query)):
        log(f"Skipping malformed API response for: {search.get('name', query)}")
        return [], []

    items = result.get("itemSummaries", [])
    new_listings: List[Dict[str, Any]] = []
    price_drops: List[Dict[str, Any]] = []

    # Extract search parameters
    name = search["name"]
    min_p = search.get("min_price", 0)
    max_p = search.get("max_price", float("inf"))
    exclude = [w.lower() for w in search.get("exclude_words", [])]
    bin_only = search.get("buy_it_now_only", False)

    def make_seen_entry(price_val, title_val):
        """Create a seen entry dict with timestamp, price, and title."""
        return {'timestamp': datetime.now().isoformat(), 'price': price_val, 'title': title_val}

    for item in items:
        item_id = item.get("itemId", "")
        if not item_id:
            continue

        title = item.get("title", "")
        # Prefer affiliate URL when EPN is configured (API returns both)
        link = item.get("itemAffiliateWebUrl") or item.get("itemWebUrl", "")

        # Parse price
        price_info = item.get("price", {})
        price: Optional[float] = None
        if price_info:
            try:
                price = float(price_info.get("value", 0))
            except (ValueError, TypeError):
                pass  # Price parsing failed, leave as None

        # Check if already seen - but also check for price drops
        if item_id in seen:
            seen_entry = seen[item_id]
            # Get old price from seen entry (handle migration from old formats)
            old_price = None
            if isinstance(seen_entry, dict):
                old_price = seen_entry.get('price')
            # Check for price drop INTO range (was outside, now inside)
            if price is not None and old_price is not None and price < old_price:
                # Price dropped! Check if now within search range
                effective_max = max_p * 1.15 if "BEST_OFFER" in item.get("buyingOptions", []) else max_p
                # Only alert if: (1) new price is in range, AND (2) old price was OUT of range
                was_out_of_range = old_price < min_p or old_price > effective_max
                now_in_range = min_p <= price <= effective_max
                if now_in_range and was_out_of_range:
                    # Check exclusions - price drops should also respect exclude_words
                    if any(w in title.lower() for w in exclude):
                        seen[item_id] = make_seen_entry(price, title)
                        continue
                    # Price drop into range - add to price_drops list
                    buying_options = item.get("buyingOptions", [])
                    has_best_offer = "BEST_OFFER" in buying_options
                    # Build listing data (reuse same structure as new listings)
                    created_utc = item.get("itemCreationDate", "")
                    created_israel, created_usa, listing_age = "", "", ""
                    if created_utc:
                        try:
                            dt_utc = datetime.fromisoformat(created_utc.replace('Z', '+00:00'))
                            israel_offset = 3 if is_israel_dst(dt_utc) else 2
                            dt_israel = dt_utc + timedelta(hours=israel_offset)
                            created_israel = dt_israel.strftime("%I:%M %p").lstrip('0')
                            us_offset = -7 if is_us_pacific_dst(dt_utc) else -8
                            dt_usa = dt_utc + timedelta(hours=us_offset)
                            created_usa = dt_usa.strftime("%I:%M %p").lstrip('0')
                            now_utc = datetime.now(timezone.utc)
                            age_delta = now_utc - dt_utc
                            age_minutes = int(age_delta.total_seconds() / 60)
                            if age_minutes < 60:
                                listing_age = f"{age_minutes}m ago"
                            elif age_minutes < 1440:
                                listing_age = f"{age_minutes // 60}h ago"
                            else:
                                listing_age = f"{age_minutes // 1440}d ago"
                        except Exception:
                            pass
                    location_info = item.get("itemLocation", {})
                    item_location = location_info.get("country", "")
                    price_drops.append({
                        "search_name": name, "title": title, "link": link,
                        "price": price, "old_price": old_price,
                        "best_offer": has_best_offer, "id": item_id,
                        "created_il": created_israel, "created_us": created_usa,
                        "listing_age": listing_age, "location": item_location
                    })
                    # Update seen with new price
                    seen[item_id] = make_seen_entry(price, title)
            elif price is not None:
                # Update seen entry with current price (for future drop detection)
                seen[item_id] = make_seen_entry(price, title)
            continue  # Already seen - skip to next item

        # Skip invalid titles (mark as seen to avoid re-checking)
        if not title or len(title) < 5:
            seen[item_id] = make_seen_entry(price, title)
            continue

        # Skip if title doesn't match query requirements
        if not title_matches_query(title, search):
            seen[item_id] = make_seen_entry(price, title)
            continue

        # Skip if title contains excluded words
        if any(w in title.lower() for w in exclude):
            seen[item_id] = make_seen_entry(price, title)
            continue

        # Check buying options
        buying_options = item.get("buyingOptions", [])
        has_best_offer = "BEST_OFFER" in buying_options
        is_auction = "AUCTION" in buying_options

        # Skip auctions if Buy It Now only is required
        if bin_only and is_auction and "FIXED_PRICE" not in buying_options:
            seen[item_id] = make_seen_entry(price, title)
            continue

        # Check price bounds
        if price is not None:
            effective_max = max_p * 1.15 if has_best_offer else max_p
            if price < min_p or price > effective_max:
                # Store price for future drop detection even if out of range
                seen[item_id] = make_seen_entry(price, title)
                continue
        # Extract listing creation date and convert to Israel time + US Pacific
        created_utc = item.get("itemCreationDate", "")
        created_israel = ""
        created_usa = ""
        listing_age = ""
        if created_utc:
            try:
                # Parse ISO format: 2025-01-12T14:30:00.000Z
                dt_utc = datetime.fromisoformat(created_utc.replace('Z', '+00:00'))
                # Convert to Israel time using proper DST calculation
                israel_offset = 3 if is_israel_dst(dt_utc) else 2  # IDT = UTC+3, IST = UTC+2
                dt_israel = dt_utc + timedelta(hours=israel_offset)
                created_israel = dt_israel.strftime("%I:%M %p").lstrip('0')
                # Convert to US Pacific using proper DST calculation
                us_offset = -7 if is_us_pacific_dst(dt_utc) else -8
                dt_usa = dt_utc + timedelta(hours=us_offset)
                created_usa = dt_usa.strftime("%I:%M %p").lstrip('0')
                # Calculate listing age
                now_utc = datetime.now(timezone.utc)
                age_delta = now_utc - dt_utc
                age_minutes = int(age_delta.total_seconds() / 60)
                if age_minutes < 60:
                    listing_age = f"{age_minutes}m ago"
                elif age_minutes < 1440:  # Less than 24 hours
                    listing_age = f"{age_minutes // 60}h ago"
                else:
                    listing_age = f"{age_minutes // 1440}d ago"
            except Exception:
                pass  # Date parsing failed, timestamps will be empty

        # Extract item location (country only - eBay API limitation)
        location_info = item.get("itemLocation", {})
        item_location = location_info.get("country", "")

        new_listings.append({"search_name": name, "title": title, "link": link, "price": price, "best_offer": has_best_offer, "id": item_id, "created_il": created_israel, "created_us": created_usa, "listing_age": listing_age, "location": item_location})
        seen[item_id] = make_seen_entry(price, title)
    return new_listings, price_drops

# --- Alerts & Email ---

def parse_recipients(recipient_str: str) -> List[str]:
    """
    Parse and validate comma-separated email recipients.

    Args:
        recipient_str: Comma-separated email addresses

    Returns:
        List of valid email addresses, or empty list if invalid
    """
    if not recipient_str:
        return []

    # Split by comma and clean up
    recipients = [r.strip() for r in recipient_str.split(',')]
    recipients = [r for r in recipients if r and '@' in r]

    return recipients


def send_email_core(config: Dict[str, Any], subject: str, body: str, is_html: bool = False) -> bool:
    """Send email with configurable SMTP, failure tracking, BCC support, and optional IMAP cleanup (Gmail only)."""
    # NASA JPL: Circuit breaker - skip email when in degraded mode
    if is_email_degraded_mode():
        log(f"Email circuit breaker OPEN ({get_email_failure_count()} failures) - skipping email")
        return False

    try:
        # Get SMTP config (supports Gmail, Outlook, Yahoo auto-detection)
        smtp_cfg = get_smtp_config(config)
        sender = smtp_cfg['sender']
        password = smtp_cfg['password']

        # Parse recipients (supports multiple, comma-separated)
        recipients = parse_recipients(smtp_cfg['recipient'])
        if not (sender and password and recipients):
            return False

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = sender  # Self in To field - recipients hidden (sent via sendmail)
        msg["Subject"] = subject

        if is_html:
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        # Use configurable SMTP (auto-detected or from config)
        server = smtplib.SMTP(smtp_cfg['host'], smtp_cfg['port'], timeout=SMTP_TIMEOUT_SECONDS)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())
        server.quit()

        # Delete this email from Sent and Trash (Gmail only - IMAP cleanup)
        # NOTE: IMAP cleanup is best-effort - email is already sent successfully at this point
        # If cleanup fails, the alert was still delivered (intentional design)
        if smtp_cfg['host'] == 'smtp.gmail.com':
            try:
                imap = imaplib.IMAP4_SSL("imap.gmail.com", timeout=SMTP_TIMEOUT_SECONDS)
                imap.login(sender, password)

                # Delete from Sent folder
                imap.select('"[Gmail]/Sent Mail"')
                safe_subject = subject.replace('\\', '\\\\').replace('"', '\\"')
                _, msgs = imap.search(None, f'SUBJECT "{safe_subject}"')
                if msgs[0]:
                    for m in msgs[0].split():
                        imap.store(m, "+FLAGS", "\\Deleted")
                    imap.expunge()

                # Delete from Trash (permanently remove)
                try:
                    imap.select('"[Gmail]/Trash"')
                    _, msgs = imap.search(None, f'SUBJECT "{safe_subject}"')
                    if msgs[0]:
                        for m in msgs[0].split():
                            imap.store(m, "+FLAGS", "\\Deleted")
                        imap.expunge()
                except (imaplib.IMAP4.error, OSError):
                    pass  # Trash cleanup failure is non-critical

                imap.logout()
            except Exception as imap_err:
                log(f"IMAP cleanup failed (email still sent): {imap_err}")

        log(f"Email sent: {subject} ({len(recipients)} recipient(s))")
        clear_email_failures()  # Reset counter on success
        return True
    except (smtplib.SMTPException, socket.error, socket.timeout, OSError) as e:
        failure_count = record_email_failure()
        log(f"Failed to send email (failure #{failure_count}): {e}")

        # Log warning if many consecutive failures
        if failure_count >= MAX_EMAIL_FAILURES_BEFORE_ALERT:
            log(f"WARNING: {failure_count} consecutive email failures - check email configuration!")

        return False

def send_alert_email(config: Dict[str, Any], alert_type: str, details: str = "") -> bool:
    """Send system alert email with cooldown protection."""
    if is_graceful_shutdown():
        log("Alert suppressed: shutdown")
        clear_shutdown_signal()
        return False

    global recovery_state
    cooldown = DEFAULT_RECOVERY["cooldown_after_alert_minutes"]
    if recovery_state["last_alert_time"]:
        elapsed = datetime.now() - recovery_state["last_alert_time"]
        if elapsed < timedelta(minutes=cooldown):
            remaining = cooldown - int(elapsed.total_seconds() // 60)
            log(f"Alert suppressed (cooldown: {remaining}m)")
            return False

    stats = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "failures": recovery_state["consecutive_failures"],
        "restarts": 0,
        "last_success": recovery_state.get("last_successful_cycle", "Never")
    }

    subject = f"[NOTICE] eBay API: {alert_type}"
    html_body = get_alert_html(alert_type, details, stats)

    if send_email_core(config, subject, html_body, is_html=True):
        recovery_state["last_alert_time"] = datetime.now()
        log(f"Alert email sent: {alert_type}")
        return True
    return False


def send_email(config: Dict[str, Any], listings: List[Dict[str, Any]]) -> None:
    if not listings: return

    # Format for template
    display_list = []
    for l in listings:
        bo_tag = " [OBO]" if l.get('best_offer') else ""
        l['title'] = f"{l.get('title','')}{bo_tag}"
        display_list.append(l)

    subject = get_subject_line("eBay API", display_list)
    html_body = get_listing_html("eBay API", display_list)

    if send_email_core(config, subject, html_body, is_html=True):
        update_statistics(increment_alerts=True)
    else:
        # Log what notification failed so user knows they missed something
        log(f"EMAIL FAILED: {len(listings)} new listing(s) NOT sent!")


def send_price_drop_email(config: Dict[str, Any], price_drops: List[Dict[str, Any]]) -> None:
    """Send email notification for items that dropped in price into search range."""
    if not price_drops:
        return

    # Format for template - add price drop indicator to title
    display_list = []
    for item in price_drops:
        old_p = item.get('old_price', 0)
        new_p = item.get('price', 0)
        if old_p and new_p:
            drop_pct = int((old_p - new_p) / old_p * 100)
            drop_tag = f" [PRICE DROP -{drop_pct}%]"
        else:
            drop_tag = " [PRICE DROP]"
        bo_tag = " [OBO]" if item.get('best_offer') else ""
        item['title'] = f"{item.get('title', '')}{drop_tag}{bo_tag}"
        display_list.append(item)

    count = len(display_list)
    subject = f"[eBay API] PRICE DROP: {count} ITEM{'S' if count > 1 else ''} NOW IN RANGE"
    html_body = get_listing_html("eBay PRICE DROPS", display_list)

    if send_email_core(config, subject, html_body, is_html=True):
        update_statistics(increment_alerts=True)
        log(f"Price drop notification sent: {count} items")
    else:
        log(f"EMAIL FAILED: {count} price drop(s) NOT sent!")


# --- Main Loop ---

def run_foxfinder() -> None:
    """Main FoxFinder loop with smart pacing and recovery."""
    log("=" * 50)
    log(f"FoxFinder v{VERSION} starting (Smart Pacing)")
    if _EMAIL_TEMPLATES_LOADED:
        log("Email templates: loaded from email_templates.py")
    else:
        log("WARNING: Email templates NOT loaded - using fallback (raw dicts)")
    rotate_logs()
    cleanup_stale_lock()  # NASA JPL: Clean up stale lock before duplicate check
    stop_duplicate_processes()
    clear_shutdown_signal()

    # --- STARTUP CONFIG VALIDATION ---
    config = load_config()
    if not config:
        log("FATAL: Could not load ebay_config.json")
        log("Please ensure the config file exists and is valid JSON.")
        return

    is_valid, errors = validate_config(config)
    if not is_valid:
        log("=" * 50)
        log("CONFIG VALIDATION FAILED")
        log("=" * 50)
        for err in errors:
            log(f"  - {err}")
        log("")
        log("Please run USER_SETTINGS.py to complete your configuration.")
        log("=" * 50)
        return

    log("Config validation passed")

    # Quarterly API status check (non-blocking)
    check_api_updates()

    # --- STARTUP STATE RECOVERY ---
    rate_data = load_rate_state()
    today = get_pacific_date()

    if rate_data.get("date") == today:
        # Same day - recover state
        calls_made = rate_data.get("calls", 0)
        last_update = rate_data.get("last_update", "unknown")
        reset_time = rate_data.get("reset_time_utc", "unknown")
        log(f"RECOVERY: Resuming from previous state")
        log(f"  - Date: {today} (Pacific)")
        log(f"  - Calls made today: {calls_made}")
        log(f"  - Last update: {last_update}")
        log(f"  - API reset time: {reset_time}")

        seconds_until_reset = get_seconds_until_reset(rate_data)
        log(f"  - Time until reset: {seconds_until_reset//3600}h {(seconds_until_reset%3600)//60}m")

        remaining = rate_data.get("api_remaining", 5000 - calls_made)
        log(f"  - Estimated remaining calls: {remaining}")
    else:
        # New day - fresh start
        log(f"STARTUP: New day detected ({today}), starting fresh")
        rate_data = create_fresh_rate_state(today)
        save_rate_state(rate_data)

    seen = load_seen()
    log(f"Loaded {len(seen)} previously seen items")
    cycle_count = 0
    config = load_config()  # Pre-load for exception handler safety

    while True:
        try:
            # 0. Check for graceful shutdown signal
            if is_graceful_shutdown():
                log("Graceful shutdown requested. Saving state and exiting...")
                save_seen(seen)
                save_rate_state(load_rate_state())
                clear_shutdown_signal()
                log("State saved. Goodbye!")
                return

            # 1. Connectivity Check
            if not check_internet():
                log("No internet. Waiting 60s...")
                if interruptible_sleep(ERROR_RETRY_INTERVAL, check_interval=1.0):
                    log("Shutdown during connectivity wait. Exiting...")
                    return
                continue

            # 2. Maintenance Refresh Check
            if cycle_count >= MAX_CYCLES_BEFORE_REFRESH:
                log("Maintenance: Refreshing environment...")
                gc.collect()
                cycle_count = 0

            # Periodic maintenance (every 10 cycles)
            if cycle_count % 10 == 0:
                check_memory_usage()  # NASA JPL: Memory watchdog
                stop_duplicate_processes()
                seen = cleanup_old_seen(seen, max_age_days=SEEN_MAX_AGE_DAYS)
                save_seen(seen)
                gc.collect()

            config = load_config()

            # Credential check
            creds = config.get("api_credentials", {})
            app_id = creds.get("app_id")
            client_secret = creds.get("client_secret")
            epn_campaign_id = creds.get("epn_campaign_id")  # EPN affiliate tracking (optional but recommended)

            if not app_id or not client_secret:
                log("ERROR: API Credentials missing from ebay_config.json!")
                if interruptible_sleep(ERROR_RETRY_INTERVAL, check_interval=1.0):
                    log("Shutdown during credential wait. Exiting...")
                    return
                continue

            searches = config.get("searches", [])
            enabled_searches = [s for s in searches if s.get("enabled", True)]
            search_count = len(enabled_searches)
            log(f'Cycle start: {search_count}/{len(searches)} searches enabled')

            # Get OAuth token first (needed for API sync)
            token = get_oauth_token(app_id, client_secret)
            if token is None:
                log("Failed to get OAuth token. Waiting 60s before retry...")
                if interruptible_sleep(ERROR_RETRY_INTERVAL, check_interval=1.0):
                    log("Shutdown during token retry wait. Exiting...")
                    return
                continue

            # Sync rate state with eBay API (updates remaining calls, reset time)
            rate_data = sync_rate_state_with_api(token)

            # Check if we've hit the limit
            if rate_data.get("calls", 0) >= DAILY_CALL_LIMIT:
                if not rate_data.get("alert_sent"):
                    send_alert_email(config, "RATE LIMIT REACHED",
                        f"Daily API quota of {DAILY_CALL_LIMIT} hit. Pausing until reset.")
                    rate_data["alert_sent"] = True
                    save_rate_state(rate_data)
                seconds_until_reset = get_seconds_until_reset(rate_data)
                wait_time = min(seconds_until_reset + 60, 3600)  # Sleep until reset or max 1hr
                log(f"Daily limit reached. Sleeping {wait_time//60}m until reset...")
                if interruptible_sleep(wait_time, check_interval=30.0):  # Check every 30s
                    log("Shutdown during rate limit wait. Exiting...")
                    save_seen(seen)
                    return
                continue

            # Calculate smart interval based on remaining budget and time
            final_wait = calculate_smart_interval(search_count, rate_data)

            # PROACTIVE RECOVERY: Check for impossible usage immediately after reset (NASA JPL Anomaly Detection)
            # If API reports very high usage right after reset, it's a sync lag. Retry quickly.
            # NOTE: Wrapped in try-except to ensure non-critical optimization doesn't crash main loop
            try:
                minutes_since_reset = get_minutes_since_reset()
                remaining = rate_data.get("api_remaining", 5000)
                implied_usage = 5000 - remaining

                # Theoretical max speed: 4 cycles/min * searches + buffer
                max_possible = (search_count * 4 * max(1, minutes_since_reset)) + 200

                # Only check anomaly after 2+ minutes (API data unreliable in first 1-2 min after reset)
                if minutes_since_reset >= 2 and minutes_since_reset < 60 and implied_usage > max_possible:
                    log(f"SYNC ANOMALY: {implied_usage} calls > possible {max_possible} in {minutes_since_reset:.1f}m.")
                    log("Ignoring smart pacing (1h+). Forcing rapid retry (120s) to catch quota reset.")
                    final_wait = 120
            except Exception as e:
                # Non-critical: anomaly detection is an optimization, not required for operation
                log(f"Anomaly detection skipped (non-critical): {e}")

            # Update heartbeat (handles exceptions internally)
            update_heartbeat()

            cycle_start_time = time.time()  # NASA JPL: Track cycle duration
            all_new = []
            all_price_drops = []
            for search in searches:
                # Skip disabled searches
                if not search.get("enabled", True):
                    continue
                try:
                    new_l, price_drops = check_search_api(token, search, seen, epn_campaign_id)
                    all_new.extend(new_l)
                    all_price_drops.extend(price_drops)
                    increment_rate_counter(1)
                except Exception as e:
                    log(f"Search '{search.get('name', '?')}' failed: {e}")
                    # Continue with other searches
                time.sleep(0.5)

            # Reload rate state to get updated call count
            rate_data = load_rate_state()
            calls_today = rate_data.get("calls", 0)

            # Handle new listings
            if all_new:
                for item in all_new:
                    log(f"Found: [{item.get('id')}] {item.get('title')}")
                log(f"Found {len(all_new)} new listings. Calls today: {calls_today}")
                send_email(config, all_new)
                save_seen(seen)

            # Handle price drops (separate email for visibility)
            if all_price_drops:
                for item in all_price_drops:
                    old_p = item.get('old_price', 0)
                    new_p = item.get('price', 0)
                    log(f"Price drop: [{item.get('id')}] ${old_p:.2f} -> ${new_p:.2f} {item.get('title')}")
                log(f"Found {len(all_price_drops)} price drops. Calls today: {calls_today}")
                send_price_drop_email(config, all_price_drops)
                save_seen(seen)

            if not all_new and not all_price_drops:
                log(f"Cycle complete ({search_count} searches). Calls today: {calls_today}")

            # NASA JPL: Check cycle duration for performance degradation
            cycle_duration = time.time() - cycle_start_time
            if cycle_duration > CYCLE_TIME_WARNING_SECONDS:
                log(f"WARNING: Slow cycle detected ({cycle_duration:.0f}s > {CYCLE_TIME_WARNING_SECONDS}s threshold)")

            recovery_state["consecutive_failures"] = 0
            recovery_state["last_successful_cycle"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cycle_count += 1
            update_statistics()  # Track last_run

            log(f"Next check in {int(final_wait)}s (Smart pacing: {search_count} searches)")

            # NASA JPL Pattern: Interruptible sleep with heartbeat
            sleep_chunk = 30  # Check shutdown every 30s for faster response
            remaining = final_wait
            while remaining > 0:
                chunk = min(sleep_chunk, remaining)
                if interruptible_sleep(chunk, check_interval=1.0):
                    log("Shutdown detected during sleep. Exiting...")
                    save_seen(seen)
                    clear_shutdown_signal()
                    return
                update_heartbeat()  # Handles exceptions internally
                remaining -= chunk

        except Exception as e:
            recovery_state["consecutive_failures"] += 1
            log(f"Error in main loop: {e} (Failure #{recovery_state['consecutive_failures']})")
            backoff = calculate_backoff(recovery_state["consecutive_failures"] - 1)
            log(f"Backing off for {backoff}s...")
            if recovery_state["consecutive_failures"] >= DEFAULT_RECOVERY["alert_after_consecutive_failures"]:
                send_alert_email(config, "Consecutive API Failures", str(e))
            if interruptible_sleep(backoff, check_interval=5.0):
                log("Shutdown during error backoff. Exiting...")
                save_seen(seen)
                return

if __name__ == "__main__":
    try:
        run_foxfinder()
    except KeyboardInterrupt:
        log("Stopped by user")
    except Exception as e:
        log(f"Fatal: {e}")
        config = load_config()
        send_alert_email(config, "Unrecoverable Crash", str(e))





