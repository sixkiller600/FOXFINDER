"""
FoxFinder - Shared Utilities Module
===================================
NASA JPL Level Reliability - Shared patterns for:
- FoxFinder eBay Deal Notification Service (foxfinder.py)

Maintains single source of truth for common functionality.

v1.2.0: Standalone release for FoxFinder
"""

import time
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

VERSION = "1.2.0"
__version__ = VERSION

# =============================================================================
# DISK SPACE CHECK - NASA JPL Pattern
# =============================================================================

# Minimum free disk space for safe writes (in MB)
MIN_DISK_SPACE_MB = 100


def check_disk_space(path: Path, min_mb: int = MIN_DISK_SPACE_MB) -> Tuple[bool, int]:
    """
    NASA JPL Pattern: Check disk space before critical writes.

    Prevents silent data corruption when disk is full.
    Should be called before atomic write operations.

    Args:
        path: Path to check (uses its drive/filesystem)
        min_mb: Minimum required free space in MB (default 100MB)

    Returns:
        Tuple (has_space: bool, free_mb: int)

    Example:
        has_space, free_mb = check_disk_space(CONFIG_FILE)
        if not has_space:
            log(f"WARNING: Low disk space ({free_mb}MB), skipping write")
            return False
    """
    try:
        # Get the directory to check (parent if path is a file)
        check_path = path.parent if path.is_file() or not path.exists() else path
        if not check_path.exists():
            check_path = Path(path.anchor)  # Fallback to drive root

        usage = shutil.disk_usage(check_path)
        free_mb = usage.free // (1024 * 1024)
        return free_mb >= min_mb, free_mb
    except (OSError, AttributeError):
        # If we can't check, assume OK (fail-open for non-critical check)
        return True, -1

# =============================================================================
# NASA JPL INTERRUPTIBLE OPERATIONS
# =============================================================================

def interruptible_sleep(
    seconds: float,
    shutdown_check: Callable[[], bool],
    check_interval: float = 1.0
) -> bool:
    """
    NASA JPL Pattern: Sleep that can be interrupted by shutdown signal.

    Instead of blocking for the full duration, checks shutdown flag periodically.
    This allows graceful shutdown to work within check_interval seconds.

    Args:
        seconds: Total time to sleep
        shutdown_check: Callable that returns True if shutdown requested
        check_interval: How often to check for shutdown (default 1s)

    Returns:
        True if interrupted by shutdown, False if completed normally
    """
    elapsed = 0.0
    while elapsed < seconds:
        if shutdown_check():
            return True  # Interrupted
        sleep_time = min(check_interval, seconds - elapsed)
        time.sleep(sleep_time)
        elapsed += sleep_time
    return False  # Completed normally


def interruptible_wait(
    condition_func: Callable[[], bool],
    shutdown_check: Callable[[], bool],
    timeout_seconds: float,
    check_interval: float = 0.5,
    description: str = "condition"
) -> Tuple[bool, bool]:
    """
    NASA JPL Pattern: Wait for a condition with shutdown awareness.

    Args:
        condition_func: Callable that returns True when condition is met
        shutdown_check: Callable that returns True if shutdown requested
        timeout_seconds: Maximum time to wait
        check_interval: How often to check condition and shutdown
        description: For logging purposes

    Returns:
        Tuple (condition_met: bool, interrupted: bool)
    """
    elapsed = 0.0
    while elapsed < timeout_seconds:
        if shutdown_check():
            return False, True  # Not met, interrupted
        try:
            if condition_func():
                return True, False  # Met, not interrupted
        except Exception:
            pass  # Condition check failed, keep waiting
        time.sleep(check_interval)
        elapsed += check_interval
    return False, False  # Timeout, not interrupted


# =============================================================================
# HEARTBEAT MANAGEMENT
# =============================================================================

def update_heartbeat(
    heartbeat_file: Path,
    source: str,
    version: str,
    extra_data: Optional[dict] = None
) -> bool:
    """
    Update heartbeat file with JSON status for health checks.

    Standard heartbeat format:
    {
        "timestamp": <unix_timestamp>,
        "source": "<component_name>",
        "datetime": "<ISO_format>",
        "version": "<version_string>",
        ...extra_data
    }

    Args:
        heartbeat_file: Path to heartbeat file
        source: Component identifier (e.g., "foxfinder", "deal_notifier")
        version: Version string
        extra_data: Optional additional key-value pairs

    Returns:
        True if successful, False otherwise
    """
    try:
        data = {
            'timestamp': time.time(),
            'source': source,
            'datetime': datetime.now().isoformat(),
            'version': version
        }
        if extra_data:
            data.update(extra_data)
        heartbeat_file.write_text(json.dumps(data), encoding='utf-8')
        return True
    except Exception:
        return False


def read_heartbeat(heartbeat_file: Path) -> Optional[dict]:
    """
    Read and parse a heartbeat file.

    Args:
        heartbeat_file: Path to heartbeat file

    Returns:
        Parsed heartbeat data dict, or None if unavailable
    """
    try:
        if heartbeat_file.exists():
            return json.loads(heartbeat_file.read_text(encoding='utf-8'))
    except Exception:
        pass
    return None


def get_heartbeat_age_seconds(heartbeat_file: Path) -> int:
    """
    Get age of heartbeat in seconds.

    Args:
        heartbeat_file: Path to heartbeat file

    Returns:
        Age in seconds, or -1 if file doesn't exist or can't be read
    """
    try:
        data = read_heartbeat(heartbeat_file)
        if data and 'timestamp' in data:
            return int(time.time() - data['timestamp'])
        # Fallback to file mtime if no timestamp in content
        if heartbeat_file.exists():
            return int(time.time() - heartbeat_file.stat().st_mtime)
    except Exception:
        pass
    return -1


# =============================================================================
# LOG ROTATION
# =============================================================================

def rotate_log_if_needed(log_file: Path, max_size_bytes: int = 5 * 1024 * 1024) -> bool:
    """
    Rotate log file if it exceeds max size.

    Renames current log to .log.old (replacing any existing .old file).

    Args:
        log_file: Path to log file
        max_size_bytes: Max size before rotation (default 5MB)

    Returns:
        True if rotation occurred, False otherwise
    """
    try:
        if log_file.exists() and log_file.stat().st_size > max_size_bytes:
            backup = log_file.with_suffix('.log.old')
            if backup.exists():
                backup.unlink()
            log_file.rename(backup)
            return True
    except Exception:
        pass
    return False


# =============================================================================
# SHUTDOWN FILE MANAGEMENT
# =============================================================================

def check_shutdown_file(shutdown_file: Path) -> bool:
    """
    Check if shutdown has been requested via file.

    Args:
        shutdown_file: Path to shutdown request file

    Returns:
        True if shutdown requested, False otherwise
    """
    return shutdown_file.exists()


def clear_shutdown_file(shutdown_file: Path) -> bool:
    """
    Clear shutdown request file.

    Args:
        shutdown_file: Path to shutdown request file

    Returns:
        True if cleared (or didn't exist), False on error
    """
    try:
        if shutdown_file.exists():
            shutdown_file.unlink()
        return True
    except Exception:
        return False


def request_shutdown(shutdown_file: Path) -> bool:
    """
    Create shutdown request file.

    Args:
        shutdown_file: Path to shutdown request file

    Returns:
        True if created, False on error
    """
    try:
        shutdown_file.touch()
        return True
    except Exception:
        return False


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_duration(seconds: int) -> str:
    """
    Format duration in human-readable form.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "5s", "3m", "2h", "1d 5h"
    """
    if seconds < 0:
        return "?"
    elif seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h" if hours else f"{days}d"


def safe_json_load(file_path: Path, default: dict = None) -> dict:
    """
    Safely load JSON file with fallback to default.

    Args:
        file_path: Path to JSON file
        default: Default value if file missing or invalid

    Returns:
        Loaded dict or default
    """
    if default is None:
        default = {}
    try:
        if file_path.exists():
            return json.loads(file_path.read_text(encoding='utf-8'))
    except Exception:
        pass
    return default


def safe_json_save(file_path: Path, data: dict, indent: int = 2) -> bool:
    """
    Safely save dict to JSON file using atomic write pattern.

    NASA JPL Pattern: Write to temp file, then rename (atomic on most filesystems).
    Prevents data corruption if process interrupted mid-write.

    Args:
        file_path: Path to JSON file
        data: Dict to save
        indent: JSON indentation (default 2)

    Returns:
        True if successful, False otherwise
    """
    try:
        temp_file = file_path.with_suffix('.tmp')
        temp_file.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding='utf-8')
        temp_file.replace(file_path)
        return True
    except Exception:
        # Clean up temp file if it exists
        try:
            temp_file = file_path.with_suffix('.tmp')
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass
        return False
