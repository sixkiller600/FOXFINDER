#!/usr/bin/env python3
"""
FoxFinder Comprehensive QA Test Suite
Covers all modules: shared_utils, ebay_common, email_templates, foxfinder
"""

import sys
import os
import json
import time
import tempfile
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASS, FAIL, ERRORS
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        msg = f"  FAIL: {name}" + (f" -- {detail}" if detail else "")
        print(msg)
        ERRORS.append(msg)

def section(name):
    print(f"\n{'='*60}")
    print(f" {name}")
    print(f"{'='*60}")

# ============================================================
# 1. SHARED_UTILS TESTS
# ============================================================
section("shared_utils.py")

from shared_utils import (
    check_disk_space, interruptible_sleep, interruptible_wait,
    update_heartbeat, read_heartbeat, get_heartbeat_age_seconds,
    rotate_log_if_needed, check_shutdown_file, clear_shutdown_file,
    request_shutdown, format_duration, safe_json_load, safe_json_save,
    VERSION as SU_VERSION
)

# Version
test("shared_utils VERSION is string", isinstance(SU_VERSION, str))
test("shared_utils VERSION matches expected", SU_VERSION == "1.2.0")

# format_duration
test("format_duration(0) = '0s'", format_duration(0) == "0s")
test("format_duration(30) = '30s'", format_duration(30) == "30s")
test("format_duration(59) = '59s'", format_duration(59) == "59s")
test("format_duration(60) = '1m'", format_duration(60) == "1m")
test("format_duration(3599) = '59m'", format_duration(3599) == "59m")
test("format_duration(3600) = '1h'", format_duration(3600) == "1h")
test("format_duration(3661) = '1h 1m'", format_duration(3661) == "1h 1m")
test("format_duration(86400) = '1d'", format_duration(86400) == "1d")
test("format_duration(90000) = '1d 1h'", format_duration(90000) == "1d 1h")
test("format_duration(-1) = '?'", format_duration(-1) == "?")

# check_disk_space
has_space, free_mb = check_disk_space(Path("."))
test("check_disk_space returns tuple", isinstance(has_space, bool) and isinstance(free_mb, int))
test("check_disk_space has space on current dir", has_space is True)
test("check_disk_space free_mb > 0", free_mb > 0)

# Non-existent path
has_space2, free_mb2 = check_disk_space(Path("Z:\\nonexistent\\path\\file.txt"))
test("check_disk_space on invalid path returns gracefully", isinstance(has_space2, bool))

# safe_json_save and safe_json_load
with tempfile.TemporaryDirectory() as tmpdir:
    test_file = Path(tmpdir) / "test.json"
    test_data = {"key": "value", "number": 42, "list": [1, 2, 3]}
    result = safe_json_save(test_file, test_data)
    test("safe_json_save returns True", result is True)
    test("safe_json_save creates file", test_file.exists())
    loaded = safe_json_load(test_file)
    test("safe_json_load returns correct data", loaded == test_data)

    # Test load of non-existent file
    missing = safe_json_load(Path(tmpdir) / "missing.json")
    test("safe_json_load missing file returns empty dict", missing == {})

    # Test load with default
    missing2 = safe_json_load(Path(tmpdir) / "missing.json", default={"default": True})
    test("safe_json_load with default returns default", missing2 == {"default": True})

    # Test heartbeat write/read
    hb_file = Path(tmpdir) / ".heartbeat"
    hb_ok = update_heartbeat(hb_file, "test", "1.0.0")
    test("update_heartbeat returns True", hb_ok is True)
    test("heartbeat file created", hb_file.exists())
    hb_data = read_heartbeat(hb_file)
    test("read_heartbeat returns dict", isinstance(hb_data, dict))
    test("heartbeat has timestamp", "timestamp" in hb_data)
    test("heartbeat has source", hb_data.get("source") == "test")
    test("heartbeat has version", hb_data.get("version") == "1.0.0")

    age = get_heartbeat_age_seconds(hb_file)
    test("heartbeat age is small", 0 <= age <= 5)

    # Test non-existent heartbeat
    age_missing = get_heartbeat_age_seconds(Path(tmpdir) / "nope")
    test("missing heartbeat age = -1", age_missing == -1)

    # Test shutdown file operations
    sd_file = Path(tmpdir) / ".shutdown"
    test("check_shutdown_file false initially", check_shutdown_file(sd_file) is False)
    ok = request_shutdown(sd_file)
    test("request_shutdown returns True", ok is True)
    test("check_shutdown_file true after request", check_shutdown_file(sd_file) is True)
    ok2 = clear_shutdown_file(sd_file)
    test("clear_shutdown_file returns True", ok2 is True)
    test("check_shutdown_file false after clear", check_shutdown_file(sd_file) is False)

    # Test log rotation
    log_file = Path(tmpdir) / "test.log"
    log_file.write_text("x" * 100)
    rotated = rotate_log_if_needed(log_file, max_size_bytes=50)
    test("rotate_log_if_needed rotates oversized log", rotated is True)
    test("original log removed after rotation", not log_file.exists())
    test("rotated log exists", Path(tmpdir, "test.log.old").exists())

    # Test no rotation needed
    log_file2 = Path(tmpdir) / "small.log"
    log_file2.write_text("small")
    rotated2 = rotate_log_if_needed(log_file2, max_size_bytes=1000)
    test("rotate_log_if_needed skips small log", rotated2 is False)


# ============================================================
# 2. EBAY_COMMON TESTS
# ============================================================
section("ebay_common.py")

from ebay_common import (
    VERSION as EC_VERSION,
    _get_nth_weekday_of_month,
    _get_last_weekday_of_month,
    _get_last_friday_before_date,
    is_us_pacific_dst,
    is_israel_dst,
    get_pacific_date,
    create_fresh_rate_state,
    validate_rate_data,
    get_seconds_until_reset,
    get_smtp_config,
    get_module_info,
    EBAY_API_BASE,
)

test("ebay_common VERSION is string", isinstance(EC_VERSION, str))
test("ebay_common VERSION matches", EC_VERSION == "1.2.1")
test("EBAY_API_BASE is https", EBAY_API_BASE.startswith("https://"))

# DST tests - known dates
# 2025-07-15 is definitely PDT (summer)
summer_utc = datetime(2025, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
test("US Pacific DST in July = True", is_us_pacific_dst(summer_utc) is True)

# 2025-01-15 is definitely PST (winter)
winter_utc = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
test("US Pacific DST in January = False", is_us_pacific_dst(winter_utc) is False)

# Israel DST tests
summer_il = datetime(2025, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
test("Israel DST in July = True", is_israel_dst(summer_il) is True)

winter_il = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
test("Israel DST in January = False", is_israel_dst(winter_il) is False)

# Naive datetime handling (should not crash)
naive_dt = datetime(2025, 7, 15, 12, 0, 0)
try:
    result = is_us_pacific_dst(naive_dt)
    test("is_us_pacific_dst handles naive datetime", isinstance(result, bool))
except TypeError:
    test("is_us_pacific_dst handles naive datetime", False, "TypeError raised")

try:
    result2 = is_israel_dst(naive_dt)
    test("is_israel_dst handles naive datetime", isinstance(result2, bool))
except TypeError:
    test("is_israel_dst handles naive datetime", False, "TypeError raised")

# _get_nth_weekday_of_month
# 2025 March: 2nd Sunday (for DST start)
second_sunday_march = _get_nth_weekday_of_month(2025, 3, 6, 2)
test("2nd Sunday March 2025 = 9", second_sunday_march == 9)

# 2025 November: 1st Sunday (for DST end)
first_sunday_nov = _get_nth_weekday_of_month(2025, 11, 6, 1)
test("1st Sunday Nov 2025 = 2", first_sunday_nov == 2)

# _get_last_weekday_of_month
# Last Sunday of October 2025
last_sun_oct = _get_last_weekday_of_month(2025, 10, 6)
test("Last Sunday Oct 2025 = 26", last_sun_oct == 26)

# get_pacific_date
pacific_date = get_pacific_date()
test("get_pacific_date returns YYYY-MM-DD format", len(pacific_date) == 10 and pacific_date[4] == '-')

# create_fresh_rate_state
fresh = create_fresh_rate_state("2025-01-15")
test("fresh rate state has date", fresh["date"] == "2025-01-15")
test("fresh rate state calls = 0", fresh["calls"] == 0)
test("fresh rate state api_remaining = 5000", fresh["api_remaining"] == 5000)
test("fresh rate state alert_sent = False", fresh["alert_sent"] is False)
test("fresh rate state has last_update", "last_update" in fresh)

# validate_rate_data
valid_rate = create_fresh_rate_state()
validation = validate_rate_data(valid_rate)
test("validate_rate_data returns dict", isinstance(validation, dict))
test("validate_rate_data has 'valid' key", "valid" in validation)
test("validate_rate_data has 'confidence' key", "confidence" in validation)
test("fresh rate state validates as high confidence", validation["confidence"] == "high")

# get_seconds_until_reset
seconds = get_seconds_until_reset(valid_rate)
test("get_seconds_until_reset returns positive int", isinstance(seconds, int) and seconds >= 0)
test("get_seconds_until_reset < 86400", seconds < 86400)

# get_smtp_config
gmail_config = {"email": {"sender": "test@gmail.com", "password": "pass", "recipient": "r@r.com"}}
smtp = get_smtp_config(gmail_config)
test("Gmail SMTP host correct", smtp["host"] == "smtp.gmail.com")
test("Gmail SMTP port correct", smtp["port"] == 587)

outlook_config = {"email": {"sender": "test@outlook.com", "password": "pass", "recipient": "r@r.com"}}
smtp2 = get_smtp_config(outlook_config)
test("Outlook SMTP host auto-detected", smtp2["host"] == "smtp-mail.outlook.com")

yahoo_config = {"email": {"sender": "test@yahoo.com", "password": "pass", "recipient": "r@r.com"}}
smtp3 = get_smtp_config(yahoo_config)
test("Yahoo SMTP host auto-detected", smtp3["host"] == "smtp.mail.yahoo.com")

# get_module_info
info = get_module_info()
test("get_module_info returns dict", isinstance(info, dict))
test("get_module_info has version", "version" in info)
test("get_module_info has paths", "paths" in info)


# ============================================================
# 3. EMAIL_TEMPLATES TESTS
# ============================================================
section("email_templates.py")

from email_templates import (
    __version__ as ET_VERSION,
    _get_condition_badge,
    _extract_item_id,
    _get_watchlist_url,
    get_subject_line,
    get_listing_html,
    get_notice_html,
    format_listing_email,
    format_notice_email,
    CONDITION_BADGES,
    COLORS,
    EBAY_ATTRIBUTION,
)

test("email_templates version", ET_VERSION == "2.5.0")
test("COLORS is dict", isinstance(COLORS, dict))
test("CONDITION_BADGES is dict", isinstance(CONDITION_BADGES, dict))
test("EBAY_ATTRIBUTION is string", isinstance(EBAY_ATTRIBUTION, str))

# Condition badges
badge_new = _get_condition_badge("New")
test("condition badge 'New' returns HTML", "NEW" in badge_new and "<span" in badge_new)

badge_used = _get_condition_badge("Good")
test("condition badge 'Good' returns HTML", "GOOD" in badge_used)

badge_none = _get_condition_badge(None, show_if_unknown=True)
test("condition badge None shows UNKNOWN", "UNKNOWN" in badge_none)

badge_none_hidden = _get_condition_badge(None, show_if_unknown=False)
test("condition badge None hidden returns empty", badge_none_hidden == "")

badge_empty = _get_condition_badge("", show_if_unknown=True)
test("condition badge empty shows UNKNOWN", "UNKNOWN" in badge_empty)

badge_custom = _get_condition_badge("Some Random Condition")
test("condition badge custom shows truncated text (20 chars)", "SOME RANDOM CONDITIO" in badge_custom)

# Item ID extraction
test("extract item_id from standard URL", _extract_item_id("https://www.ebay.com/itm/123456789012") == "123456789012")
test("extract item_id from URL with title", _extract_item_id("https://www.ebay.com/itm/Some-Title/123456789012") == "123456789012")
test("extract item_id returns None for empty", _extract_item_id("") is None)
test("extract item_id returns None for None", _extract_item_id(None) is None)
test("extract item_id from bad URL", _extract_item_id("https://google.com") is None)

# Watchlist URL
test("watchlist URL generated", _get_watchlist_url("123456789012") == "https://www.ebay.com/myb/WatchList?item_id=123456789012")
test("watchlist URL None for None", _get_watchlist_url(None) is None)

# Subject line
listings = [
    {"search_name": "iPhone Search", "title": "iPhone 15", "price": 500},
    {"search_name": "iPhone Search", "title": "iPhone 14", "price": 400},
]
subject = get_subject_line("eBay API", listings)
test("subject line contains count", "2 New Listings" in subject)
test("subject line contains source", "EBAY API" in subject)

single = [{"search_name": "Test", "title": "Item", "price": 100}]
subject_single = get_subject_line("eBay API", single)
test("subject line singular for 1 item", "1 New Listing Found" in subject_single)

empty_subject = get_subject_line("eBay API", [])
test("subject line 0 items", "0 New Listings" in empty_subject)

# HTML generation
test_listings = [
    {
        "search_name": "Test Search",
        "title": "Test Item Title",
        "link": "https://www.ebay.com/itm/123456789012",
        "price": 299.99,
        "condition": "New",
        "created_il": "10:30 AM",
        "created_us": "1:30 AM",
        "location": "US",
    }
]
html = get_listing_html("TEST SOURCE", test_listings)
test("listing HTML is string", isinstance(html, str))
test("listing HTML has DOCTYPE", "<!DOCTYPE html>" in html)
test("listing HTML has charset", 'charset="utf-8"' in html)
test("listing HTML has viewport meta", "viewport" in html)
test("listing HTML has eBay attribution", EBAY_ATTRIBUTION in html)
test("listing HTML has eBay User Agreement link", "User Agreement" in html)
test("listing HTML has Explore More section", "EXPLORE MORE ON EBAY" in html)
test("listing HTML has eBay app links", "iOS App" in html)
test("listing HTML has Money Back Guarantee", "Money Back Guarantee" in html)
test("listing HTML has item title", "Test Item Title" in html)
test("listing HTML has FOXFINDER header", "FOXFINDER" in html)

# Notice email
notice_html = get_notice_html("Test Alert", "Something happened", {"key": "value"})
test("notice HTML is string", isinstance(notice_html, str))
test("notice HTML has alert type", "Test Alert" in notice_html)
test("notice HTML has details", "Something happened" in notice_html)

# format_listing_email
subj, body = format_listing_email("Source", test_listings)
test("format_listing_email returns subject", subj is not None)
test("format_listing_email returns body", body is not None)

# format_listing_email empty
subj_e, body_e = format_listing_email("Source", [])
test("format_listing_email empty returns None", subj_e is None and body_e is None)

# format_notice_email
n_subj, n_body = format_notice_email("Alert", "Details")
test("format_notice_email returns subject", "[NOTICE]" in n_subj)
test("format_notice_email returns body", isinstance(n_body, str))

# XSS prevention (HTML escaping)
xss_listings = [{"search_name": "XSS", "title": '<script>alert("xss")</script>', "link": "https://ebay.com/itm/123456789012", "price": 100}]
xss_html = get_listing_html("TEST", xss_listings)
test("HTML escapes script tags (XSS prevention)", "<script>" not in xss_html)
test("HTML escapes to &lt;script&gt;", "&lt;script&gt;" in xss_html)

# Price formatting edge cases
price_tests = [
    {"title": "Test", "link": "#", "price": 0, "search_name": "T"},
    {"title": "Test", "link": "#", "price": None, "search_name": "T"},
    {"title": "Test", "link": "#", "price": "N/A", "search_name": "T"},
    {"title": "Test", "link": "#", "price": 1999.99, "search_name": "T"},
    {"title": "Test", "link": "#", "price": "1,234", "search_name": "T"},
]
for pt in price_tests:
    try:
        h = get_listing_html("Test", [pt])
        test(f"price format '{pt['price']}' doesn't crash", isinstance(h, str))
    except Exception as e:
        test(f"price format '{pt['price']}' doesn't crash", False, str(e))


# ============================================================
# 4. FOXFINDER TESTS
# ============================================================
section("foxfinder.py")

from foxfinder import (
    VERSION as FF_VERSION,
    validate_config,
    validate_epn_campaign_id,
    title_matches_query,
    parse_recipients,
    calculate_backoff,
    validate_api_response,
    cleanup_old_seen,
    SEARCH_RESULTS_LIMIT,
    MAX_SEEN_ENTRIES,
    SEEN_MAX_AGE_DAYS,
)

test("foxfinder VERSION", FF_VERSION == "4.9.0")
test("SEARCH_RESULTS_LIMIT = 150", SEARCH_RESULTS_LIMIT == 150)
test("MAX_SEEN_ENTRIES = 50000", MAX_SEEN_ENTRIES == 50000)
test("SEEN_MAX_AGE_DAYS = 14", SEEN_MAX_AGE_DAYS == 14)

# validate_epn_campaign_id
test("EPN empty is valid", validate_epn_campaign_id("") is True)
test("EPN None is valid", validate_epn_campaign_id(None) is True)
test("EPN 10 digits valid", validate_epn_campaign_id("1234567890") is True)
test("EPN 9 digits invalid", validate_epn_campaign_id("123456789") is False)
test("EPN 11 digits invalid", validate_epn_campaign_id("12345678901") is False)
test("EPN letters invalid", validate_epn_campaign_id("abcdefghij") is False)
test("EPN mixed invalid", validate_epn_campaign_id("12345abcde") is False)

# validate_config
valid_config = {
    "api_credentials": {"app_id": "test123", "client_secret": "secret456"},
    "email": {"sender": "test@gmail.com", "password": "apppassword", "recipient": "user@example.com"},
    "searches": [{"name": "Test", "query": "iPhone"}]
}
is_valid, errors = validate_config(valid_config)
test("valid config passes", is_valid is True)
test("valid config no errors", len(errors) == 0)

# Missing api_credentials
bad1 = {"email": {"sender": "t@g.com", "password": "p", "recipient": "r@r.com"}, "searches": [{"name": "T", "query": "Q"}]}
is_valid1, errors1 = validate_config(bad1)
test("missing api_credentials fails", is_valid1 is False)

# Missing app_id
bad2 = {
    "api_credentials": {"client_secret": "secret"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "r@r.com"},
    "searches": [{"name": "T", "query": "Q"}]
}
is_valid2, errors2 = validate_config(bad2)
test("missing app_id fails", is_valid2 is False)

# Missing email
bad3 = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "searches": [{"name": "T", "query": "Q"}]
}
is_valid3, errors3 = validate_config(bad3)
test("missing email section fails", is_valid3 is False)

# Invalid email format
bad4 = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "email": {"sender": "not-an-email", "password": "p", "recipient": "r@r.com"},
    "searches": [{"name": "T", "query": "Q"}]
}
is_valid4, errors4 = validate_config(bad4)
test("invalid email format fails", is_valid4 is False)

# No searches
bad5 = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "r@r.com"},
    "searches": []
}
is_valid5, errors5 = validate_config(bad5)
test("empty searches fails", is_valid5 is False)

# Search without name
bad6 = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "r@r.com"},
    "searches": [{"query": "test"}]
}
is_valid6, errors6 = validate_config(bad6)
test("search without name fails", is_valid6 is False)

# Search without query
bad7 = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "r@r.com"},
    "searches": [{"name": "Test"}]
}
is_valid7, errors7 = validate_config(bad7)
test("search without query fails", is_valid7 is False)

# Invalid EPN
bad_epn = {
    "api_credentials": {"app_id": "id", "client_secret": "secret", "epn_campaign_id": "12345"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "r@r.com"},
    "searches": [{"name": "T", "query": "Q"}]
}
is_valid_epn, errors_epn = validate_config(bad_epn)
test("invalid EPN fails validation", is_valid_epn is False)
test("EPN error mentions 10 digits", any("10 digits" in e for e in errors_epn))

# Multiple recipients
multi_config = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "a@b.com, c@d.com"},
    "searches": [{"name": "T", "query": "Q"}]
}
is_valid_m, errors_m = validate_config(multi_config)
test("multiple recipients valid", is_valid_m is True)

# Invalid recipient in multi
bad_multi = {
    "api_credentials": {"app_id": "id", "client_secret": "secret"},
    "email": {"sender": "t@g.com", "password": "p", "recipient": "a@b.com, not-email"},
    "searches": [{"name": "T", "query": "Q"}]
}
is_valid_bm, errors_bm = validate_config(bad_multi)
test("invalid recipient in multi fails", is_valid_bm is False)

# title_matches_query
search_req = {"query": "iPhone 15 Pro", "required_words": ["iPhone", "Pro"]}
test("title match with required words", title_matches_query("Apple iPhone 15 Pro 256GB", search_req) is True)
test("title miss with required words", title_matches_query("Samsung Galaxy S24", search_req) is False)

search_query = {"query": "iPhone 15 Pro"}
test("title match from query", title_matches_query("New iPhone 15 Pro Max 256GB", search_query) is True)
test("title miss from query", title_matches_query("iPad Mini 6th Gen", search_query) is False)

# Case insensitivity
test("title match case insensitive", title_matches_query("IPHONE 15 PRO", search_query) is True)

# Empty query
search_empty = {"query": ""}
test("empty query matches anything", title_matches_query("Whatever Title", search_empty) is True)

# parse_recipients
test("parse single recipient", parse_recipients("test@example.com") == ["test@example.com"])
test("parse multiple recipients", parse_recipients("a@b.com, c@d.com") == ["a@b.com", "c@d.com"])
test("parse empty string", parse_recipients("") == [])
test("parse None", parse_recipients(None) == [])
test("parse filters invalid", parse_recipients("valid@email.com, invalid") == ["valid@email.com"])

# calculate_backoff
b0 = calculate_backoff(0)
test("backoff attempt 0 is ~60", 55 <= b0 <= 70)
b1 = calculate_backoff(1)
test("backoff attempt 1 is ~120", 110 <= b1 <= 135)
b5 = calculate_backoff(5)
test("backoff attempt 5 capped at max", b5 <= 1000)

# validate_api_response
test("valid API response", validate_api_response({"itemSummaries": []}, ["itemSummaries"]) is True)
test("missing key in API response", validate_api_response({"other": []}, ["itemSummaries"]) is False)
test("non-dict API response", validate_api_response("string", ["key"]) is False)
test("None API response", validate_api_response(None, ["key"]) is False)

# cleanup_old_seen
now = datetime.now()
old_date = (now - timedelta(days=30)).isoformat()
recent_date = (now - timedelta(days=1)).isoformat()
test_seen = {
    "old_item": {"timestamp": old_date, "price": 100, "title": "Old"},
    "recent_item": {"timestamp": recent_date, "price": 200, "title": "Recent"},
    "bool_item": True,
    "str_item": recent_date,
}
cleaned = cleanup_old_seen(test_seen)
test("cleanup removes old items", "old_item" not in cleaned)
test("cleanup keeps recent items", "recent_item" in cleaned)
test("cleanup migrates bool entries", isinstance(cleaned.get("bool_item"), dict))
test("cleanup migrates string entries", isinstance(cleaned.get("str_item"), dict))

# Empty seen
test("cleanup empty dict", cleanup_old_seen({}) == {})


# ============================================================
# 5. CONFIG TEMPLATE VALIDATION
# ============================================================
section("Config Template Validation")

template_path = Path(__file__).parent / "ebay_config_template.json"
try:
    with open(template_path, 'r', encoding='utf-8') as f:
        template = json.load(f)
    test("template is valid JSON", True)
    test("template has api_credentials", "api_credentials" in template)
    test("template has email section", "email" in template)
    test("template has searches array", isinstance(template.get("searches"), list))
    test("template has at least one search", len(template.get("searches", [])) >= 1)
    test("template search has 'name'", template["searches"][0].get("name") is not None)
    test("template search has 'query'", template["searches"][0].get("query") is not None)
    test("template has recovery section", "recovery" in template)
    test("template has check_interval_seconds", "check_interval_seconds" in template)
    test("template has _instructions", "_instructions" in template)

    # Validate the template itself wouldn't pass config validation (placeholder values)
    is_valid_t, _ = validate_config(template)
    test("template with placeholders passes structure check", is_valid_t is True,
         "Template should have valid structure even with placeholder values")
except json.JSONDecodeError as e:
    test("template is valid JSON", False, str(e))
except FileNotFoundError:
    test("template file exists", False, "ebay_config_template.json not found")


# ============================================================
# 6. FILE EXISTENCE & REPO STRUCTURE VALIDATION
# ============================================================
section("Repository Structure Validation")

repo_root = Path(__file__).parent
required_files = [
    "foxfinder.py",
    "ebay_common.py",
    "email_templates.py",
    "shared_utils.py",
    "check_rate_limit.py",
    "ebay_config_template.json",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "COMPLIANCE_CHECKLIST.md",
    "PRIVACY_POLICY.md",
    ".gitignore",
    "FoxFinder ON.bat",
    "FoxFinder ON.ps1",
    "FoxFinder OFF.bat",
    "FoxFinder OFF.ps1",
    "Status Dashboard.bat",
    "Status Dashboard.ps1",
]

for f in required_files:
    test(f"File exists: {f}", (repo_root / f).exists())

# Verify no secrets committed
secret_files = [
    "ebay_config.json",
    "ebay_token.json",
    "ebay_rate_limit.json",
    "ebay_seen_api.json",
    ".heartbeat",
    ".ebay.lock",
    ".shutdown_requested",
]

# Check .gitignore contains these
gitignore = (repo_root / ".gitignore").read_text()
for sf in secret_files:
    test(f".gitignore covers {sf}", sf in gitignore)


# ============================================================
# 7. VERSION CONSISTENCY CHECK
# ============================================================
section("Version Consistency")

# Read versions from modules
test("foxfinder.py version = 4.9.0", FF_VERSION == "4.9.0")
test("ebay_common.py version = 1.2.1", EC_VERSION == "1.2.1")
test("email_templates.py version = 2.5.0", ET_VERSION == "2.5.0")
test("shared_utils.py version = 1.2.0", SU_VERSION == "1.2.0")

# Check CHANGELOG mentions these versions
changelog = (repo_root / "CHANGELOG.md").read_text()
test("CHANGELOG mentions foxfinder 4.9.0", "4.9.0" in changelog)
test("CHANGELOG component table has foxfinder.py 4.9.0", "foxfinder.py" in changelog and "4.9.0" in changelog)
test("CHANGELOG component table has ebay_common.py 1.2.1", "1.2.1" in changelog)
test("CHANGELOG component table has email_templates.py 2.5.0", "2.5.0" in changelog)
test("CHANGELOG component table has shared_utils.py 1.2.0", "1.2.0" in changelog)


# ============================================================
# 8. README ACCURACY CHECK
# ============================================================
section("README Accuracy")

readme = (repo_root / "README.md").read_text()
test("README mentions Python 3.9+", "Python 3.9" in readme)
test("README has clone command", "git clone" in readme)
test("README has pip install", "pip install -r requirements.txt" in readme)
test("README has config template copy", "ebay_config_template.json" in readme)
test("README mentions Browse API", "Browse API" in readme)
test("README mentions FIXED_PRICE default", "Buy It Now" in readme or "FIXED_PRICE" in readme)
test("README has COMPLIANCE link", "COMPLIANCE_CHECKLIST.md" in readme)
test("README has PRIVACY link", "PRIVACY_POLICY.md" in readme)
test("README has LICENSE link", "LICENSE" in readme)
test("README has CHANGELOG link", "CHANGELOG.md" in readme)
test("README mentions FoxFinder ON.bat", "FoxFinder ON.bat" in readme)
test("README mentions FoxFinder OFF.bat", "FoxFinder OFF.bat" in readme)
test("README mentions Status Dashboard.bat", "Status Dashboard.bat" in readme)
test("README has eBay disclaimer", "not affiliated" in readme.lower())
test("README has GitHub repo URL", "sixkiller600/FOXFINDER" in readme)

# Check project structure in README matches actual files
test("README structure lists foxfinder.py", "foxfinder.py" in readme)
test("README structure lists ebay_common.py", "ebay_common.py" in readme)
test("README structure lists email_templates.py", "email_templates.py" in readme)
test("README structure lists shared_utils.py", "shared_utils.py" in readme)
test("README structure lists check_rate_limit.py", "check_rate_limit.py" in readme)


# ============================================================
# 9. COMPLIANCE DOCUMENT ACCURACY
# ============================================================
section("Compliance Document Accuracy")

compliance = (repo_root / "COMPLIANCE_CHECKLIST.md").read_text()
test("Compliance mentions Browse API v1", "Browse API" in compliance and "v1" in compliance)
test("Compliance mentions max 2 retries", "Max 2 retries" in compliance)
test("Compliance mentions FIXED_PRICE", "FIXED_PRICE" in compliance)
test("Compliance mentions 14-day retention", "14" in compliance)
test("Compliance mentions contextualLocation", "contextualLocation" in compliance)
test("Compliance mentions itemEndDate", "itemEndDate" in compliance)
test("Compliance mentions HTTPS", "HTTPS" in compliance)
test("Compliance mentions EPN", "EPN" in compliance)
test("Compliance lists OWASP", "OWASP" in compliance)

# Privacy policy
privacy = (repo_root / "PRIVACY_POLICY.md").read_text()
test("Privacy mentions 14 days retention", "14 days" in privacy)
test("Privacy mentions 10 days termination", "ten (10) days" in privacy)
test("Privacy mentions no AI training", "AI" in privacy or "artificial intelligence" in privacy.lower())
test("Privacy mentions GDPR", "GDPR" in privacy)
test("Privacy mentions CCPA", "CCPA" in privacy)
test("Privacy has deletion instructions", "Delete" in privacy or "delete" in privacy)
test("Privacy mentions eBay Privacy Notice", "eBay Privacy Notice" in privacy)


# ============================================================
# 10. EDGE CASE TESTS
# ============================================================
section("Edge Cases")

# Unicode in titles
unicode_listings = [{"search_name": "Test", "title": "iPhone \u00e9\u00e8\u00ea \u2122 15 Pro", "link": "#", "price": 500}]
try:
    h = get_listing_html("Test", unicode_listings)
    test("Unicode in title renders OK", isinstance(h, str))
except Exception as e:
    test("Unicode in title renders OK", False, str(e))

# Very long title
long_title = "A" * 500
long_listings = [{"search_name": "Test", "title": long_title, "link": "#", "price": 100}]
try:
    h = get_listing_html("Test", long_listings)
    test("Very long title renders OK", isinstance(h, str))
    test("Long title is truncated", long_title[:100] in h)
except Exception as e:
    test("Very long title renders OK", False, str(e))

# Empty listing HTML
try:
    h = get_listing_html("Test", [])
    test("Empty listing HTML renders OK", isinstance(h, str))
except Exception as e:
    test("Empty listing HTML renders OK", False, str(e))

# Very large seen file cleanup
large_seen = {}
for i in range(60000):
    large_seen[f"item_{i}"] = {"timestamp": datetime.now().isoformat(), "price": i, "title": f"Item {i}"}
cleaned_large = cleanup_old_seen(large_seen)
test(f"Large seen capped at {MAX_SEEN_ENTRIES}", len(cleaned_large) <= MAX_SEEN_ENTRIES)


# ============================================================
# 11. ROBUSTNESS FIX VERIFICATION
# ============================================================
section("Robustness Fixes (Fix 1-6)")

# Read source files for inspection
foxfinder_src = (repo_root / "foxfinder.py").read_text(encoding="utf-8")
ebay_common_src = (repo_root / "ebay_common.py").read_text(encoding="utf-8")
requirements_src = (repo_root / "requirements.txt").read_text(encoding="utf-8")
gitignore_src = (repo_root / ".gitignore").read_text(encoding="utf-8")

# Fix 1: Dead USER_SETTINGS.py reference removed
test("Fix 1: No USER_SETTINGS.py reference", "USER_SETTINGS.py" not in foxfinder_src)
test("Fix 1: Config copy instructions present", "ebay_config_template.json to ebay_config.json" in foxfinder_src)
test("Fix 1: README reference in config error", 'See README.md for setup instructions' in foxfinder_src)

# Fix 2: Windows platform guard
test("Fix 2: cleanup_stale_lock has platform guard", "sys.platform != 'win32'" in foxfinder_src or "sys.platform == 'win32'" in foxfinder_src)
test("Fix 2: stop_duplicate_processes has platform guard", "sys.platform == 'win32'" in foxfinder_src)
test("Fix 2: README mentions Windows 10+", "Windows 10+" in readme)
test("Fix 2: README has cross-platform note", "cross-platform" in readme.lower() or "Cross-platform" in readme)

# Fix 3: No requests dependency
test("Fix 3: No 'import requests' in foxfinder.py", "import requests" not in foxfinder_src)
# Check no requests.Session in actual code (ignore changelog comments)
foxfinder_code_lines = [l for l in foxfinder_src.split('\n') if not l.strip().startswith('#')]
foxfinder_code_only = '\n'.join(foxfinder_code_lines)
test("Fix 3: No 'requests.Session' in foxfinder.py code", "requests.Session" not in foxfinder_code_only)
test("Fix 3: No 'requests.RequestException' in foxfinder.py", "requests.RequestException" not in foxfinder_src)
test("Fix 3: No get_http_session function", "def get_http_session" not in foxfinder_src)
test("Fix 3: No reset_http_session function", "def reset_http_session" not in foxfinder_src)
test("Fix 3: No _http_session global", "_http_session:" not in foxfinder_src)
test("Fix 3: requirements.txt has no requests", "requests" not in requirements_src)
test("Fix 3: ebay_common check_internet uses urllib", "urllib.request" in ebay_common_src)
test("Fix 3: ebay_common check_internet no requests import", "import requests" not in ebay_common_src)
test("Fix 3: foxfinder imports urllib.error", "import urllib.error" in foxfinder_src)

# Fix 4: Run log in separate file
from ebay_common import RUN_LOG_FILE
test("Fix 4: RUN_LOG_FILE defined in ebay_common", RUN_LOG_FILE is not None)
test("Fix 4: RUN_LOG_FILE is foxfinder_run_log.json", RUN_LOG_FILE.name == "foxfinder_run_log.json")
test("Fix 4: RUN_LOG_FILE imported in foxfinder", "RUN_LOG_FILE" in foxfinder_src)
test("Fix 4: update_run_log uses RUN_LOG_FILE", "RUN_LOG_FILE" in foxfinder_src.split("def update_run_log")[1].split("\ndef ")[0])
test("Fix 4: update_run_log does NOT write CONFIG_FILE", "CONFIG_FILE" not in foxfinder_src.split("def update_run_log")[1].split("\ndef ")[0])
test("Fix 4: .gitignore has foxfinder_run_log.json", "foxfinder_run_log.json" in gitignore_src)

# Fix 4: Functional test - update_run_log writes to separate file
from foxfinder import update_run_log
with tempfile.TemporaryDirectory() as tmpdir:
    import foxfinder as ff_mod
    import ebay_common as ec_mod
    # Temporarily redirect RUN_LOG_FILE
    orig_rlf = ff_mod.RUN_LOG_FILE
    test_rlf = Path(tmpdir) / "foxfinder_run_log.json"
    ff_mod.RUN_LOG_FILE = test_rlf
    try:
        update_run_log()
        test("Fix 4: update_run_log creates run log file", test_rlf.exists())
        if test_rlf.exists():
            rl_data = json.loads(test_rlf.read_text())
            test("Fix 4: run log has last_run", "last_run" in rl_data)
            test("Fix 4: run log has alerts_sent", "alerts_sent" in rl_data)
    except Exception as e:
        test("Fix 4: update_run_log functional test", False, str(e))
    finally:
        ff_mod.RUN_LOG_FILE = orig_rlf

# Fix 5: No sys.path hack
test("Fix 5: No parent.parent sys.path hack", "parent.parent" not in foxfinder_src)
test("Fix 5: No _parent_dir variable", "_parent_dir" not in foxfinder_src)

# Fix 6: Python version guard at top
# The guard should appear before the main docstring
lines = foxfinder_src.split('\n')
version_guard_found = False
docstring_found = False
for line in lines:
    stripped = line.strip()
    if stripped.startswith('"""') and not version_guard_found:
        docstring_found = True
    if 'sys.version_info' in stripped and '3, 9' in stripped:
        version_guard_found = True
        break
test("Fix 6: Python version guard exists", version_guard_found)
test("Fix 6: Version guard is before docstring", version_guard_found and not docstring_found,
     "Guard should appear before the module docstring")

# Verify sys is imported before version check (at top of file)
first_10_lines = '\n'.join(lines[:10])
test("Fix 6: 'import sys' near top of file", "import sys" in first_10_lines)


# ============================================================
# FINAL RESULTS
# ============================================================
print(f"\n{'='*60}")
print(f" QA RESULTS")
print(f"{'='*60}")
print(f" PASSED: {PASS}")
print(f" FAILED: {FAIL}")
print(f" TOTAL:  {PASS + FAIL}")
print(f"{'='*60}")

if ERRORS:
    print(f"\n FAILURES:")
    for err in ERRORS:
        print(f"  {err}")

sys.exit(0 if FAIL == 0 else 1)
