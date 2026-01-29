#!/usr/bin/env python3
import sys
if sys.version_info < (3, 9):
    print("FoxFinder requires Python 3.9 or later.")
    print(f"You are running Python {sys.version_info.major}.{sys.version_info.minor}")
    print("Download the latest Python from https://www.python.org/downloads/")
    sys.exit(1)

"""
FoxFinder - eBay Deal Notification Service
Uses official eBay Browse API with EPN (eBay Partner Network) integration.

Compliant with eBay Developer Program policies:
- eBay API License Agreement
- eBay Partner Network Terms
- Application Growth Check requirements

For more information, see README.md and PRIVACY_POLICY.md
"""

VERSION = "4.9.0"
__version__ = VERSION
# See CHANGELOG.md for full version history.

# --- Constants ---
ERROR_RETRY_INTERVAL = 60
API_ERROR_COOLDOWN = 300
MAX_LOG_SIZE = 10 * 1024 * 1024
SEARCH_RESULTS_LIMIT = 150
CYCLE_TIME_WARNING_SECONDS = 120
MEMORY_WARNING_THRESHOLD_MB = 200

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
import urllib.error
import subprocess
import random
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from ebay_common import (
    SCRIPT_DIR, CONFIG_FILE, SEEN_FILE, LOG_FILE, TOKEN_FILE, RATE_FILE,
    SHUTDOWN_FILE, HEARTBEAT_FILE, LOCK_FILE, RUN_LOG_FILE,
    API_UPDATE_CHECK_FILE, API_UPDATE_ALERT_FILE, EMAIL_FAILURES_FILE,
    EBAY_API_BASE, EBAY_API_VERSION, DAILY_CALL_LIMIT, MIN_INTERVAL_SECONDS,
    log, rotate_logs, update_heartbeat, read_heartbeat,
    is_shutdown_requested, clear_shutdown_request,
    interruptible_sleep, interruptible_wait,
    is_us_pacific_dst, is_israel_dst, get_pacific_date, get_pacific_datetime,
    create_fresh_rate_state, load_rate_state, save_rate_state, get_seconds_until_reset,
    get_last_reset_time_utc, get_minutes_since_reset, is_post_reset_window,
    validate_rate_data, should_force_api_refresh,
    load_config, check_internet, get_smtp_config,
)

try:
    from email_templates import get_listing_html, get_alert_html, get_subject_line
    _EMAIL_TEMPLATES_LOADED = True
except Exception as e:
    print(f"[WARNING] Failed to import email_templates: {e}", file=sys.stderr)
    _EMAIL_TEMPLATES_LOADED = False
    def get_listing_html(s, l): return "\n".join([str(x) for x in l])
    def get_alert_html(t, d, s): return f"{t}\n{d}"
    def get_subject_line(s, l): return f"{s}: {len(l)} new"

from shared_utils import check_disk_space

API_UPDATE_CHECK_INTERVAL_DAYS = 30
SEEN_MAX_AGE_DAYS = 14
MAX_SEEN_ENTRIES = 50000
API_TIMEOUT_SECONDS = 15
SMTP_TIMEOUT_SECONDS = 30
RATE_LIMIT_API_URL = f"{EBAY_API_BASE}/developer/analytics/v1_beta/rate_limit/"

MAX_CYCLES_BEFORE_REFRESH = 100
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

MAX_EMAIL_FAILURES_BEFORE_ALERT = 5
EMAIL_CIRCUIT_BREAKER_THRESHOLD = 10
EMAIL_RETRY_INTERVAL_CYCLES = 10


def get_email_failure_count() -> int:
    try:
        if EMAIL_FAILURES_FILE.exists():
            return int(EMAIL_FAILURES_FILE.read_text().strip())
    except (ValueError, IOError, OSError):
        pass
    return 0


def record_email_failure() -> int:
    try:
        count = get_email_failure_count() + 1
        EMAIL_FAILURES_FILE.write_text(str(count))
        return count
    except (IOError, OSError):
        return 0


def clear_email_failures() -> None:
    try:
        if EMAIL_FAILURES_FILE.exists():
            EMAIL_FAILURES_FILE.unlink()
    except (IOError, OSError):
        pass


def is_email_degraded_mode() -> bool:
    return get_email_failure_count() >= EMAIL_CIRCUIT_BREAKER_THRESHOLD


def check_memory_usage():
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss // (1024 * 1024)
        exceeded = mem_mb > MEMORY_WARNING_THRESHOLD_MB
        if exceeded:
            log(f"WARNING: High memory usage ({mem_mb}MB > {MEMORY_WARNING_THRESHOLD_MB}MB threshold)")
            gc.collect()
            mem_mb_after = psutil.Process(os.getpid()).memory_info().rss // (1024 * 1024)
            if mem_mb_after < mem_mb:
                log(f"  Memory reduced to {mem_mb_after}MB after gc.collect()")
        return mem_mb, exceeded
    except ImportError:
        return -1, False
    except Exception:
        return -1, False


def check_api_updates() -> None:
    try:
        if API_UPDATE_CHECK_FILE.exists():
            try:
                last_check = datetime.fromisoformat(API_UPDATE_CHECK_FILE.read_text().strip())
                if datetime.now() - last_check < timedelta(days=API_UPDATE_CHECK_INTERVAL_DAYS):
                    return
            except (ValueError, OSError):
                pass
        if not check_internet():
            log("API update check skipped - no internet connectivity")
            return
        log("Running monthly eBay API status check...")
        notices = []
        check_succeeded = False
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    "https://developer.ebay.com/api-docs/static/api-deprecation-status.html",
                    headers={"User-Agent": f"FoxFinder/{VERSION}"}
                )
                with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
                    content = resp.read().decode('utf-8', errors='replace').lower()
                    if "browse api" in content and ("deprecat" in content or "sunset" in content):
                        if "v1" in content or EBAY_API_VERSION in content:
                            notices.append(
                                "[EBAY BROWSE API] Potential deprecation notice detected.\n"
                                "   Check: https://developer.ebay.com/api-docs/static/api-deprecation-status.html"
                            )
                    check_succeeded = True
                    break
            except (urllib.error.URLError, OSError) as e:
                if attempt < 2:
                    log(f"Deprecation page check attempt {attempt + 1} failed: {e}")
                    interruptible_sleep(5 * (attempt + 1))
                else:
                    log(f"Deprecation page check failed after 3 attempts: {e}")
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    f"{EBAY_API_BASE}/buy/browse/v1",
                    headers={"User-Agent": f"FoxFinder/{VERSION}"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    pass  # 200 OK means API is alive
                check_succeeded = True
                break
            except urllib.error.HTTPError as e:
                if e.code == 410:
                    notices.append(
                        "[EBAY BROWSE API] API endpoint returned 410 GONE - may be deprecated!\n"
                        "   Urgent: Check eBay developer portal immediately."
                    )
                check_succeeded = True
                break
            except (urllib.error.URLError, OSError) as e:
                if attempt < 2:
                    log(f"API health check attempt {attempt + 1} failed: {e}")
                    interruptible_sleep(5 * (attempt + 1))
                else:
                    log(f"API health check failed after 3 attempts: {e}")
        if check_succeeded:
            API_UPDATE_CHECK_FILE.write_text(datetime.now().isoformat())
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
                "- Check eBay migration guide if needed",
                "- URL: https://developer.ebay.com/develop/apis",
                "",
                "=" * 60,
            ])
            API_UPDATE_ALERT_FILE.write_text("\n".join(alert_content), encoding="utf-8")
            log(f"API NOTICE: Potential eBay API changes - see API_UPDATE_NOTICE.txt")
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
                    send_email_core(config, subject, body, is_html=True)
                    log("API deprecation email alert sent")
            except Exception as e:
                log(f"Failed to send API notice email: {e}")
        else:
            if API_UPDATE_ALERT_FILE.exists():
                API_UPDATE_ALERT_FILE.unlink()
            if check_succeeded:
                log("API check complete - Browse API v1 appears stable")
            else:
                log("API check incomplete - will retry next cycle")
    except Exception as e:
        log(f"API check error: {e}")


STALE_LOCK_AGE_SECONDS = 3600


def cleanup_stale_lock() -> None:
    try:
        if not LOCK_FILE.exists():
            return
        lock_age = time.time() - LOCK_FILE.stat().st_mtime
        if lock_age < STALE_LOCK_AGE_SECONDS:
            return
        if sys.platform != 'win32':
            # tasklist/taskkill are Windows-only; skip process check on other platforms
            LOCK_FILE.unlink()
            log("Cleaned up stale lock file (non-Windows: age exceeded)")
            return
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            result = subprocess.run(['tasklist', '/FI', f'PID eq {old_pid}', '/NH'],
                                    capture_output=True, text=True, timeout=5)
            if str(old_pid) not in result.stdout:
                LOCK_FILE.unlink()
                log(f"Cleaned up stale lock file (PID {old_pid} no longer exists)")
        except (ValueError, IOError, OSError):
            pass
    except Exception:
        pass


def stop_duplicate_processes() -> int:
    lock_file = LOCK_FILE
    current_pid = os.getpid()
    try:
        if lock_file.exists() and sys.platform == 'win32':
            try:
                old_pid = int(lock_file.read_text().strip())
                if old_pid != current_pid:
                    result = subprocess.run(['tasklist', '/FI', f'PID eq {old_pid}', '/NH'], capture_output=True, text=True, timeout=5)
                    if str(old_pid) in result.stdout:
                        subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], capture_output=True, timeout=5)
                        log(f"Stopped duplicate process (PID {old_pid})")
            except Exception:
                pass
        lock_file.write_text(str(current_pid))
    except Exception:
        pass
    return 0


def update_run_log(increment_alerts: bool = False) -> None:
    """
    Update internal run log for operational tracking (NOT market statistics).

    This tracks when the app last ran and how many notifications were sent.
    Written to a separate file (foxfinder_run_log.json) to keep the user's
    config file clean and read-only from the app's perspective.

    This is purely for the user's own operational awareness - NOT for:
    - Market research or price analysis
    - Category statistics or aggregation
    - Any data that would compete with eBay Terapeak
    """
    tmp_file = RUN_LOG_FILE.with_suffix('.tmp')
    try:
        run_log = {"_note": "Internal run tracking only", "last_run": None, "alerts_sent": 0, "last_alert": None}
        if RUN_LOG_FILE.exists():
            try:
                with open(RUN_LOG_FILE, 'r', encoding='utf-8') as f:
                    run_log = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_log["last_run"] = now
        if increment_alerts:
            run_log["alerts_sent"] = run_log.get("alerts_sent", 0) + 1
            run_log["last_alert"] = now
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(run_log, f, indent=4)
        tmp_file.replace(RUN_LOG_FILE)
    except (IOError, json.JSONDecodeError, OSError) as e:
        log(f"Run log update failed: {e}")
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except (IOError, OSError):
            pass


is_graceful_shutdown = is_shutdown_requested
clear_shutdown_signal = clear_shutdown_request


def calculate_backoff(attempt: int) -> int:
    base = DEFAULT_RECOVERY["initial_backoff_seconds"]
    max_b = DEFAULT_RECOVERY["max_backoff_seconds"]
    backoff = min(max_b, base * (2 ** attempt))
    jitter = backoff * 0.1 * random.random()
    return int(backoff + jitter)


def increment_rate_counter(count: int = 1) -> Dict[str, Any]:
    today = get_pacific_date()
    rate_data = load_rate_state()
    if rate_data.get("date") != today:
        log(f"Day changed during operation, creating fresh rate state for {today}")
        rate_data = create_fresh_rate_state(today)
    rate_data["calls"] += count
    api_remaining = rate_data.get("api_remaining", 5000)
    rate_data["api_remaining"] = max(0, api_remaining - count)
    rate_data["last_update"] = datetime.now(timezone.utc).isoformat()
    validation = validate_rate_data(rate_data)
    if validation["confidence"] == "low":
        log(f"WARNING: Rate data confidence is low after increment: {validation['issues']}")
    save_rate_state(rate_data)
    return rate_data


def fetch_rate_limits_from_api(token: str) -> Dict[str, Any]:
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(RATE_LIMIT_API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode())
            rate_limits = data.get("rateLimits", [])
            browse_limit = None
            for rl in rate_limits:
                api_name = rl.get("apiName", "")
                if "browse" in api_name.lower() or "buy" in api_name.lower():
                    resources = rl.get("resources", [])
                    for res in resources:
                        if res.get("name") == "buy.browse":
                            rates = res.get("rates", [])
                            for rate in rates:
                                if rate.get("timeWindow") == 86400:
                                    browse_limit = rate
                                    break
                            if browse_limit:
                                break
                if browse_limit:
                    break
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
                    "reset": browse_limit.get("reset"),
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
    rate_data = load_rate_state()
    today = get_pacific_date()
    if rate_data.get("date") != today:
        log(f"New day detected ({today}), resetting rate state")
        rate_data = create_fresh_rate_state(today)
    should_check = force
    check_reason = "forced" if force else ""
    if not should_check:
        force_needed, reason = should_force_api_refresh(rate_data)
        if force_needed:
            should_check = True
            check_reason = reason
            log(f"Forcing API refresh: {reason}")
    if not should_check:
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
        in_post_reset = is_post_reset_window(10)
        max_attempts = 3 if in_post_reset else 1
        retry_delay = 60
        best_result = None
        for attempt in range(max_attempts):
            if attempt > 0:
                log(f"Post-reset verification retry {attempt + 1}/{max_attempts} (waiting {retry_delay}s)")
                time.sleep(retry_delay)
            api_result = fetch_rate_limits_from_api(token)
            if not api_result.get("success"):
                log(f"API check failed: {api_result.get('error')}")
                continue
            if in_post_reset:
                remaining = api_result.get("remaining", 0)
                limit = api_result.get("limit", 5000)
                minutes_since = get_minutes_since_reset()
                if remaining < limit * 0.5 and minutes_since < 15:
                    log(f"WARNING: Unexpected API response {minutes_since:.0f}m after reset: "
                        f"{remaining}/{limit} remaining. May be stale data.")
                    if attempt < max_attempts - 1:
                        continue
                if best_result is None or remaining > best_result.get("remaining", 0):
                    best_result = api_result
            else:
                best_result = api_result
                break
        if best_result and best_result.get("success"):
            limit = best_result.get("limit", 5000)
            remaining = best_result.get("remaining", 0)
            implied_usage = limit - remaining
            rate_data["api_limit"] = limit
            rate_data["api_remaining"] = remaining
            rate_data["reset_time_utc"] = best_result.get("reset")
            rate_data["last_api_check"] = datetime.now(timezone.utc).isoformat()
            rate_data["last_update"] = datetime.now(timezone.utc).isoformat()
            old_calls = rate_data["calls"]
            if abs(old_calls - implied_usage) > 10:
                log(f"Syncing local calls: {old_calls} -> {implied_usage} (API remaining: {remaining})")
                rate_data["calls"] = implied_usage
            rate_data["data_verified"] = True
            rate_data["verification_time"] = datetime.now(timezone.utc).isoformat()
            log(f"API sync complete: {remaining}/{limit} remaining, "
                f"calls={implied_usage}, resets at {best_result.get('reset')}")
        else:
            log("API sync failed after all attempts, using local tracking")
            rate_data["data_verified"] = False
    validation = validate_rate_data(rate_data)
    if not validation["valid"]:
        log(f"WARNING: Rate data issues: {', '.join(validation['issues'])}")
    save_rate_state(rate_data)
    return rate_data


def calculate_smart_interval(search_count: int, rate_data: Dict[str, Any]) -> int:
    if search_count <= 0:
        return 300
    remaining_calls = rate_data.get("api_remaining")
    if remaining_calls is None:
        limit = rate_data.get("api_limit", 5000)
        used = rate_data.get("calls", 0)
        remaining_calls = max(0, limit - used)
    effective_remaining = min(remaining_calls, DAILY_CALL_LIMIT - rate_data.get("calls", 0))
    effective_remaining = max(0, effective_remaining - 100)
    if effective_remaining <= 0:
        seconds_until_reset = get_seconds_until_reset(rate_data)
        wait_time = min(seconds_until_reset + 60, 3600)
        wait_time = max(300, wait_time)
        log(f"No API calls remaining. Waiting {wait_time//60}m until reset.")
        return wait_time
    seconds_until_reset = get_seconds_until_reset(rate_data)
    max_cycles = effective_remaining // search_count
    if max_cycles <= 0:
        wait_time = min(seconds_until_reset + 60, 3600)
        wait_time = max(300, wait_time)
        log(f"Not enough calls ({effective_remaining}) for one cycle ({search_count} searches). Waiting {wait_time//60}m.")
        return wait_time
    optimal_interval = seconds_until_reset / max_cycles
    final_interval = max(MIN_INTERVAL_SECONDS, min(optimal_interval, 900))
    jitter = final_interval * 0.05 * (random.random() * 2 - 1)
    final_interval += jitter
    log(f"Smart pacing: {effective_remaining} calls, {seconds_until_reset//3600}h {(seconds_until_reset%3600)//60}m until reset, "
        f"{max_cycles} possible cycles, interval={int(final_interval)}s")
    return int(final_interval)


def validate_epn_campaign_id(campaign_id: str) -> bool:
    """Validate EPN Campaign ID format (must be 10 digits per eBay requirements)."""
    if not campaign_id:
        return True  # Optional field
    return campaign_id.isdigit() and len(campaign_id) == 10


def validate_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors = []
    creds = config.get("api_credentials", {})
    if not creds:
        errors.append("Missing 'api_credentials' section")
    else:
        if not creds.get("app_id"):
            errors.append("Missing or empty 'api_credentials.app_id'")
        if not creds.get("client_secret"):
            errors.append("Missing or empty 'api_credentials.client_secret'")
        # EPN Campaign ID validation (eBay requires 10 digits)
        epn_id = creds.get("epn_campaign_id", "")
        if epn_id and not validate_epn_campaign_id(epn_id):
            errors.append(f"Invalid 'epn_campaign_id' ({epn_id}) - must be exactly 10 digits")
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
            recipients = [r.strip() for r in email.get("recipient", "").split(',')]
            recipients = [r for r in recipients if r]
            if not recipients:
                errors.append("No valid recipients in 'email.recipient'")
            else:
                for r in recipients:
                    if "@" not in r:
                        errors.append(f"Invalid recipient '{r}' - must be valid email address")
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


def load_seen():
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            pass
    return {}


def save_seen(seen):
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
    if not seen:
        return seen
    now = datetime.now()
    cutoff = now - timedelta(days=max_age_days)
    cleaned = {}
    migrated = 0
    pruned = 0
    for item_id, value in seen.items():
        if value is True:
            cleaned[item_id] = {'timestamp': now.isoformat(), 'price': None, 'title': None}
            migrated += 1
        elif isinstance(value, str):
            try:
                entry_time = datetime.fromisoformat(value)
                if entry_time > cutoff:
                    cleaned[item_id] = {'timestamp': value, 'price': None, 'title': None}
                    migrated += 1
                else:
                    pruned += 1
            except (ValueError, TypeError):
                cleaned[item_id] = {'timestamp': now.isoformat(), 'price': None, 'title': None}
                migrated += 1
        elif isinstance(value, dict):
            ts = value.get('timestamp', '')
            try:
                entry_time = datetime.fromisoformat(ts) if ts else now
                if entry_time > cutoff:
                    cleaned[item_id] = value
                else:
                    pruned += 1
            except (ValueError, TypeError):
                value['timestamp'] = now.isoformat()
                cleaned[item_id] = value
                migrated += 1
        else:
            cleaned[item_id] = {'timestamp': now.isoformat(), 'price': None, 'title': None}
            migrated += 1
    if migrated > 0 or pruned > 0:
        log(f"Seen cleanup: {pruned} old entries removed, {migrated} migrated to dict format, {len(cleaned)} total")
    if len(cleaned) > MAX_SEEN_ENTRIES:
        def get_timestamp(item):
            val = item[1]
            if isinstance(val, dict):
                return val.get('timestamp', '')
            return val if isinstance(val, str) else ''
        sorted_items = sorted(cleaned.items(), key=get_timestamp, reverse=True)
        cleaned = dict(sorted_items[:MAX_SEEN_ENTRIES])
        log(f"Seen file capped at {MAX_SEEN_ENTRIES} entries (memory protection)")
    return cleaned


def get_oauth_token(app_id, client_secret, max_retries=2):
    """Get OAuth token, refreshing if expired. Includes retry logic."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
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
                pass

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
                tmp_file = TOKEN_FILE.with_suffix('.tmp')
                try:
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(token_data, f)
                    tmp_file.replace(TOKEN_FILE)
                except (IOError, OSError):
                    if tmp_file.exists():
                        try:
                            tmp_file.unlink()
                        except OSError:
                            pass
                    raise
                log("Token refreshed successfully")
                return access_token
        except (urllib.error.URLError, OSError) as e:
            if attempt < max_retries - 1:
                wait_time = 5 * (attempt + 1)
                log(f"Token refresh retry {attempt + 1}/{max_retries}: {e}")
                time.sleep(wait_time)
            else:
                log(f"Token refresh failed after {max_retries} attempts: {e}")
                return None
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)
                log(f"Token refresh HTTP {e.code} retry {attempt + 1}/{max_retries}: {e.reason}")
                time.sleep(wait_time)
                continue
            log(f"Token refresh HTTP error: {e.code} - {e.reason}")
            return None
        except Exception as e:
            log(f"Token refresh failed: {e}")
            return None
    return None


def search_ebay(token, query, filters=None, max_retries=2, epn_campaign_id=None):
    """
    Search eBay Browse API with compliance-grade error handling.

    Note on sorting: We use sort=newlyListed as this is core to FoxFinder's
    deal notification functionality. This is documented as a business requirement
    for the eBay Growth Check application. Without this, the app cannot fulfill
    its primary purpose of alerting users to newly listed deals.
    """
    params = {"q": query, "sort": "newlyListed", "limit": str(SEARCH_RESULTS_LIMIT)}
    if filters:
        params["filter"] = filters
    url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search?{urllib.parse.urlencode(params)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"
    }
    # eBay Growth Check: X-EBAY-C-ENDUSERCTX header with affiliateCampaignId and contextualLocation
    # contextualLocation is strongly recommended by eBay for shipping estimate accuracy
    if epn_campaign_id:
        headers["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={epn_campaign_id},contextualLocation=country=US"
    else:
        headers["X-EBAY-C-ENDUSERCTX"] = "contextualLocation=country=US"
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
                result = json.loads(resp.read().decode())
                # Pagination resilience: handle varying result counts gracefully
                actual_count = len(result.get("itemSummaries", []))
                total_available = result.get("total", 0)
                if actual_count < SEARCH_RESULTS_LIMIT and actual_count < total_available:
                    log(f"NOTE: Received {actual_count} items (requested {SEARCH_RESULTS_LIMIT}, {total_available} total)")
                return result
        except urllib.error.HTTPError as e:
            # eBay compliance: proper handling of rate limit and server errors
            if e.code == 429:
                # Rate limited - back off significantly per eBay guidelines
                wait_time = 60 * (attempt + 1)
                log(f"Rate limited (HTTP 429). Backing off {wait_time}s...")
                time.sleep(wait_time)
                if attempt < max_retries - 1:
                    continue
                raise
            elif e.code in (500, 502, 503, 504) and attempt < max_retries - 1:
                # Infrastructure errors - retry with exponential backoff (max 2 per eBay policy)
                wait_time = 2 ** attempt
                log(f"Server error (HTTP {e.code}), retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                continue
            else:
                raise
        except (urllib.error.URLError, OSError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                log(f"Search retry {attempt + 1}/{max_retries}: {e}")
                time.sleep(wait_time)
            else:
                raise


def validate_api_response(data: Any, expected_keys: List[str], context: str = "") -> bool:
    if not isinstance(data, dict):
        log(f"WARNING: API response is not dict ({context}): {type(data).__name__}")
        return False
    missing = [k for k in expected_keys if k not in data]
    if missing:
        log(f"WARNING: API response missing keys ({context}): {missing}")
        return False
    return True


def title_matches_query(title: str, search: Dict[str, Any]) -> bool:
    title_lower = title.lower()
    if "required_words" in search and search["required_words"]:
        required = [w.lower() for w in search["required_words"]]
    else:
        query = search.get("query", "")
        if not query: return True
        ignore = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "new", "used"}
        words = query.split()
        required = [w.lower() for w in words if (len(w) > 1 or w.isdigit()) and w.lower() not in ignore]
    for word in required:
        pattern = r'\b' + re.escape(word) + r'\b'
        if not re.search(pattern, title_lower): return False
    return True


def check_search_api(token: str, search: Dict[str, Any], seen: Dict[str, Any], epn_campaign_id: str = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    query = search.get("query")
    if not query:
        return [], []
    api_filters = []
    condition = search.get("condition", "").lower()
    condition_map = {
        "new": "{1000}",
        "new_open_box": "{1000|1500}",
        "refurbished": "{2000|2500}",
        "used": "{3000|4000|5000|6000}",
        "used_good": "{3000|4000|5000}",
        "any_not_broken": "{1000|1500|2000|2500|3000|4000|5000|6000}",
    }
    if condition in condition_map:
        api_filters.append(f"conditionIds:{condition_map[condition]}")
    elif condition == "any" or not condition:
        pass
    min_p = search.get("min_price", 0)
    max_p = search.get("max_price", 999999)
    if min_p > 0 or max_p < 999999:
        effective_max = int(max_p * 1.15) if max_p < 999999 else max_p
        if min_p > 0 and effective_max < 999999:
            api_filters.append(f"price:[{min_p}..{effective_max}]")
        elif min_p > 0:
            api_filters.append(f"price:[{min_p}..]")
        elif effective_max < 999999:
            api_filters.append(f"price:[..{effective_max}]")
        api_filters.append("priceCurrency:USD")
    # eBay Growth Check compliance: Default to FIXED_PRICE (Buy It Now) items
    # Partners must filter for FIXED_PRICE buying options unless explicitly allowing auctions
    # Backwards compatibility: support both include_auctions (new) and buy_it_now_only (legacy)
    if "include_auctions" in search:
        include_auctions_api = search.get("include_auctions", False)
    elif "buy_it_now_only" in search:
        # Legacy: buy_it_now_only=false means include_auctions=true
        include_auctions_api = not search.get("buy_it_now_only", True)
    else:
        include_auctions_api = False  # Default: FIXED_PRICE only (eBay compliance)
    if not include_auctions_api:
        api_filters.append("buyingOptions:{FIXED_PRICE}")
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
    if not validate_api_response(result, ["itemSummaries"], context=search.get("name", query)):
        log(f"Skipping malformed API response for: {search.get('name', query)}")
        return [], []
    items = result.get("itemSummaries", [])
    new_listings: List[Dict[str, Any]] = []
    price_drops: List[Dict[str, Any]] = []
    name = search["name"]
    min_p = search.get("min_price", 0)
    max_p = search.get("max_price", float("inf"))
    exclude = [w.lower() for w in search.get("exclude_words", [])]
    # Reuse include_auctions_api from API filter logic (already computed above with backwards compat)
    # bin_only = True means filter out auction-only items in post-processing
    bin_only = not include_auctions_api

    def make_seen_entry(price_val, title_val):
        return {'timestamp': datetime.now().isoformat(), 'price': price_val, 'title': title_val}

    for item in items:
        item_id = item.get("itemId", "")
        if not item_id:
            continue
        title = item.get("title", "")

        # eBay Growth Check: Skip listings that have ended (data freshness requirement)
        # "If the item has an EndDate in the past, the listing should not be pulled in"
        item_end_date = item.get("itemEndDate")
        if item_end_date:
            try:
                end_dt = datetime.fromisoformat(item_end_date.replace('Z', '+00:00'))
                if end_dt < datetime.now(timezone.utc):
                    continue  # Skip ended listings per eBay requirement
            except (ValueError, TypeError):
                pass  # If date parsing fails, proceed with item

        # eBay Growth Check: Skip unavailable items (best practice)
        availability_status = item.get("estimatedAvailabilityStatus")
        if availability_status and availability_status not in ("IN_STOCK", "LIMITED_QUANTITY", None):
            continue  # Skip items marked as unavailable
        link = item.get("itemAffiliateWebUrl") or item.get("itemWebUrl", "")
        price_info = item.get("price", {})
        price: Optional[float] = None
        if price_info:
            try:
                price = float(price_info.get("value", 0))
            except (ValueError, TypeError):
                pass
        if item_id in seen:
            # Check if price dropped into range (like eBay's Watchlist alerts)
            seen_entry = seen[item_id]
            old_price = None
            if isinstance(seen_entry, dict):
                old_price = seen_entry.get('price')
            if price is not None and old_price is not None and price < old_price:
                effective_max = max_p * 1.15 if "BEST_OFFER" in item.get("buyingOptions", []) else max_p
                was_out_of_range = old_price < min_p or old_price > effective_max
                now_in_range = min_p <= price <= effective_max
                if now_in_range and was_out_of_range:
                    if any(w in title.lower() for w in exclude):
                        seen[item_id] = make_seen_entry(price, title)
                        continue
                    buying_options = item.get("buyingOptions", [])
                    has_best_offer = "BEST_OFFER" in buying_options
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
                    # eBay Growth Check: Must indicate when item is not new - include condition
                    item_condition = item.get("condition", "")
                    price_drops.append({
                        "search_name": name, "title": title, "link": link,
                        "price": price, "old_price": old_price,
                        "best_offer": has_best_offer, "id": item_id,
                        "created_il": created_israel, "created_us": created_usa,
                        "listing_age": listing_age, "location": item_location,
                        "condition": item_condition
                    })
                    seen[item_id] = make_seen_entry(price, title)
            elif price is not None:
                seen[item_id] = make_seen_entry(price, title)
            continue
        if not title or len(title) < 5:
            seen[item_id] = make_seen_entry(price, title)
            continue
        if not title_matches_query(title, search):
            seen[item_id] = make_seen_entry(price, title)
            continue
        if any(w in title.lower() for w in exclude):
            seen[item_id] = make_seen_entry(price, title)
            continue
        buying_options = item.get("buyingOptions", [])
        has_best_offer = "BEST_OFFER" in buying_options
        is_auction = "AUCTION" in buying_options
        if bin_only and is_auction and "FIXED_PRICE" not in buying_options:
            seen[item_id] = make_seen_entry(price, title)
            continue
        if price is not None:
            effective_max = max_p * 1.15 if has_best_offer else max_p
            if price < min_p or price > effective_max:
                seen[item_id] = make_seen_entry(price, title)
                continue
        created_utc = item.get("itemCreationDate", "")
        created_israel = ""
        created_usa = ""
        listing_age = ""
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
        # eBay Growth Check: Must indicate when item is not new - include condition field
        item_condition = item.get("condition", "")
        new_listings.append({"search_name": name, "title": title, "link": link, "price": price, "best_offer": has_best_offer, "id": item_id, "created_il": created_israel, "created_us": created_usa, "listing_age": listing_age, "location": item_location, "condition": item_condition})
        seen[item_id] = make_seen_entry(price, title)
    return new_listings, price_drops


def parse_recipients(recipient_str: str) -> List[str]:
    if not recipient_str:
        return []
    recipients = [r.strip() for r in recipient_str.split(',')]
    recipients = [r for r in recipients if r and '@' in r]
    return recipients


def send_email_core(config: Dict[str, Any], subject: str, body: str, is_html: bool = False) -> bool:
    if is_email_degraded_mode():
        log(f"Email circuit breaker OPEN ({get_email_failure_count()} failures) - skipping email")
        return False
    try:
        smtp_cfg = get_smtp_config(config)
        sender = smtp_cfg['sender']
        password = smtp_cfg['password']
        recipients = parse_recipients(smtp_cfg['recipient'])
        if not (sender and password and recipients):
            return False
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = sender
        msg["Subject"] = subject
        if is_html:
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(MIMEText(body, "plain", "utf-8"))
        server = smtplib.SMTP(smtp_cfg['host'], smtp_cfg['port'], timeout=SMTP_TIMEOUT_SECONDS)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())
        server.quit()
        if smtp_cfg['host'] == 'smtp.gmail.com':
            try:
                imap = imaplib.IMAP4_SSL("imap.gmail.com", timeout=SMTP_TIMEOUT_SECONDS)
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
            except Exception as imap_err:
                log(f"IMAP cleanup failed (email still sent): {imap_err}")
        log(f"Email sent: {subject} ({len(recipients)} recipient(s))")
        clear_email_failures()
        return True
    except (smtplib.SMTPException, socket.error, socket.timeout, OSError) as e:
        failure_count = record_email_failure()
        log(f"Failed to send email (failure #{failure_count}): {e}")
        if failure_count >= MAX_EMAIL_FAILURES_BEFORE_ALERT:
            log(f"WARNING: {failure_count} consecutive email failures - check email configuration!")
        return False


def send_alert_email(config: Dict[str, Any], alert_type: str, details: str = "") -> bool:
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
    display_list = []
    for l in listings:
        bo_tag = " [OBO]" if l.get('best_offer') else ""
        l['title'] = f"{l.get('title','')}{bo_tag}"
        display_list.append(l)
    subject = get_subject_line("eBay API", display_list)
    html_body = get_listing_html("eBay API", display_list)
    if send_email_core(config, subject, html_body, is_html=True):
        update_run_log(increment_alerts=True)
    else:
        log(f"EMAIL FAILED: {len(listings)} new listing(s) NOT sent!")


def send_price_drop_email(config: Dict[str, Any], price_drops: List[Dict[str, Any]]) -> None:
    if not price_drops:
        return
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
        update_run_log(increment_alerts=True)
        log(f"Price drop notification sent: {count} items")
    else:
        log(f"EMAIL FAILED: {count} price drop(s) NOT sent!")


def run_foxfinder() -> None:
    log("=" * 50)
    log(f"FoxFinder v{VERSION} starting (Smart Pacing)")
    if _EMAIL_TEMPLATES_LOADED:
        log("Email templates: loaded from email_templates.py")
    else:
        log("WARNING: Email templates NOT loaded - using fallback (raw dicts)")
    rotate_logs()
    cleanup_stale_lock()
    stop_duplicate_processes()
    clear_shutdown_signal()
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
        log("Please copy ebay_config_template.json to ebay_config.json and fill in your credentials.")
        log("See README.md for setup instructions.")
        log("=" * 50)
        return
    log("Config validation passed")
    check_api_updates()
    rate_data = load_rate_state()
    today = get_pacific_date()
    if rate_data.get("date") == today:
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
        log(f"STARTUP: New day detected ({today}), starting fresh")
        rate_data = create_fresh_rate_state(today)
        save_rate_state(rate_data)
    seen = load_seen()
    log(f"Loaded {len(seen)} previously seen items")
    cycle_count = 0
    config = load_config()
    while True:
        try:
            if is_graceful_shutdown():
                log("Graceful shutdown requested. Saving state and exiting...")
                save_seen(seen)
                save_rate_state(load_rate_state())
                clear_shutdown_signal()
                log("State saved. Goodbye!")
                return
            if not check_internet():
                log("No internet. Waiting 60s...")
                if interruptible_sleep(ERROR_RETRY_INTERVAL, check_interval=1.0):
                    log("Shutdown during connectivity wait. Exiting...")
                    return
                continue
            if cycle_count >= MAX_CYCLES_BEFORE_REFRESH:
                log("Maintenance: Refreshing environment...")
                gc.collect()
                cycle_count = 0
            if cycle_count % 10 == 0:
                check_memory_usage()
                stop_duplicate_processes()
                seen = cleanup_old_seen(seen, max_age_days=SEEN_MAX_AGE_DAYS)
                save_seen(seen)
                gc.collect()
            config = load_config()
            creds = config.get("api_credentials", {})
            app_id = creds.get("app_id")
            client_secret = creds.get("client_secret")
            epn_campaign_id = creds.get("epn_campaign_id")
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
            token = get_oauth_token(app_id, client_secret)
            if token is None:
                log("Failed to get OAuth token. Waiting 60s before retry...")
                if interruptible_sleep(ERROR_RETRY_INTERVAL, check_interval=1.0):
                    log("Shutdown during token retry wait. Exiting...")
                    return
                continue
            rate_data = sync_rate_state_with_api(token)
            if rate_data.get("calls", 0) >= DAILY_CALL_LIMIT:
                if not rate_data.get("alert_sent"):
                    send_alert_email(config, "RATE LIMIT REACHED",
                        f"Daily API quota of {DAILY_CALL_LIMIT} hit. Pausing until reset.")
                    rate_data["alert_sent"] = True
                    save_rate_state(rate_data)
                seconds_until_reset = get_seconds_until_reset(rate_data)
                wait_time = min(seconds_until_reset + 60, 3600)
                log(f"Daily limit reached. Sleeping {wait_time//60}m until reset...")
                if interruptible_sleep(wait_time, check_interval=30.0):
                    log("Shutdown during rate limit wait. Exiting...")
                    save_seen(seen)
                    return
                continue
            final_wait = calculate_smart_interval(search_count, rate_data)
            try:
                minutes_since_reset = get_minutes_since_reset()
                remaining = rate_data.get("api_remaining", 5000)
                implied_usage = 5000 - remaining
                max_possible = (search_count * 4 * max(1, minutes_since_reset)) + 200
                if minutes_since_reset >= 2 and minutes_since_reset < 60 and implied_usage > max_possible:
                    log(f"SYNC ANOMALY: {implied_usage} calls > possible {max_possible} in {minutes_since_reset:.1f}m.")
                    log("Ignoring smart pacing (1h+). Forcing rapid retry (120s) to catch quota reset.")
                    final_wait = 120
            except Exception as e:
                log(f"Anomaly detection skipped: {e}")
            update_heartbeat()
            cycle_start_time = time.time()
            all_new = []
            all_price_drops = []
            for search in searches:
                if not search.get("enabled", True):
                    continue
                try:
                    new_l, price_drops = check_search_api(token, search, seen, epn_campaign_id)
                    all_new.extend(new_l)
                    all_price_drops.extend(price_drops)
                    increment_rate_counter(1)
                except Exception as e:
                    log(f"Search '{search.get('name', '?')}' failed: {e}")
                time.sleep(0.5)
            rate_data = load_rate_state()
            calls_today = rate_data.get("calls", 0)
            if all_new:
                for item in all_new:
                    log(f"Found: [{item.get('id')}] {item.get('title')}")
                log(f"Found {len(all_new)} new listings. Calls today: {calls_today}")
                send_email(config, all_new)
                save_seen(seen)
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
            cycle_duration = time.time() - cycle_start_time
            if cycle_duration > CYCLE_TIME_WARNING_SECONDS:
                log(f"WARNING: Slow cycle detected ({cycle_duration:.0f}s > {CYCLE_TIME_WARNING_SECONDS}s threshold)")
            recovery_state["consecutive_failures"] = 0
            recovery_state["last_successful_cycle"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cycle_count += 1
            update_run_log()
            log(f"Next check in {int(final_wait)}s (Smart pacing: {search_count} searches)")
            sleep_chunk = 30
            remaining = final_wait
            while remaining > 0:
                chunk = min(sleep_chunk, remaining)
                if interruptible_sleep(chunk, check_interval=1.0):
                    log("Shutdown detected during sleep. Exiting...")
                    save_seen(seen)
                    clear_shutdown_signal()
                    return
                update_heartbeat()
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


def run_validate() -> int:
    """Validate configuration and environment without running the service."""
    print(f"FoxFinder v{VERSION} - Configuration Validator")
    print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print("=" * 50)

    # Check config file exists
    if not CONFIG_FILE.exists():
        print(f"FAIL: Config file not found: {CONFIG_FILE}")
        print("  -> Copy ebay_config_template.json to ebay_config.json")
        return 1
    print(f"OK:   Config file: {CONFIG_FILE}")

    # Load and validate config
    config = load_config()
    if not config:
        print("FAIL: Config file is not valid JSON")
        return 1
    print("OK:   Config file is valid JSON")

    is_valid, errors = validate_config(config)
    if not is_valid:
        print(f"FAIL: Config validation ({len(errors)} error(s)):")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK:   Config validation passed")

    # Summarize searches
    searches = config.get("searches", [])
    enabled = [s for s in searches if s.get("enabled", True)]
    print(f"OK:   {len(enabled)}/{len(searches)} searches enabled")

    # Check EPN
    epn = config.get("api_credentials", {}).get("epn_campaign_id", "")
    if epn:
        print(f"OK:   EPN Campaign ID configured ({epn[:4]}...)")
    else:
        print("INFO: EPN Campaign ID not set (optional)")

    # Check email templates
    if _EMAIL_TEMPLATES_LOADED:
        print("OK:   Email templates loaded")
    else:
        print("WARN: Email templates NOT loaded (using fallback)")

    # Check connectivity
    print("      Checking eBay API connectivity...")
    if check_internet():
        print("OK:   eBay API reachable")
    else:
        print("WARN: eBay API not reachable (no internet?)")

    # Check runtime files
    print("=" * 50)
    print("Runtime files:")
    for name, path in [
        ("Seen items", SEEN_FILE),
        ("Rate state", RATE_FILE),
        ("Token", TOKEN_FILE),
        ("Heartbeat", HEARTBEAT_FILE),
        ("Lock", LOCK_FILE),
    ]:
        if path.exists():
            print(f"  EXISTS: {name} ({path.name})")
        else:
            print(f"  ABSENT: {name} ({path.name})")

    print("=" * 50)
    print("RESULT: Configuration is valid. Ready to run.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--validate", "-v"):
        sys.exit(run_validate())
    try:
        run_foxfinder()
    except KeyboardInterrupt:
        log("Stopped by user")
    except Exception as e:
        log(f"Fatal: {e}")
        config = load_config()
        send_alert_email(config, "Unrecoverable Crash", str(e))
