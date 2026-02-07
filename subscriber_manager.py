# -*- coding: utf-8 -*-
"""
FoxFinder Subscriber Manager
=============================
Email-based double opt-in subscriber lifecycle management.

Flow: invite_subscriber() → IMAP check_confirmations() → send_to_all_subscribers()

Stores subscriber records in foxfinder_subscribers.json alongside ebay_config.json.
Zero external dependencies (uses stdlib imaplib, email, smtplib).

Compliant with:
- GDPR (double opt-in, consent proof, right to erasure)
- Israeli Anti-Spam Law (Amendment 40)
- CAN-SPAM (physical address, opt-out mechanism)
"""

__version__ = "1.1.1"

import json
import imaplib
import email as email_lib
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from ebay_common import SCRIPT_DIR, log, get_smtp_config, get_imap_config, gmail_cleanup_sent

SUBSCRIBERS_FILE = SCRIPT_DIR / "foxfinder_subscribers.json"

# Consent text shown in invitation email (stored per subscriber for GDPR Art. 7 proof)
DEFAULT_CONSENT_TEXT = (
    "By replying CONFIRM, you agree to receive automated eBay deal alert emails from "
    "FoxFinder. These emails contain affiliate links and we may earn a commission from "
    "qualifying purchases. You may unsubscribe at any time by replying UNSUBSCRIBE."
)


def _load_subscribers() -> List[Dict[str, Any]]:
    """Load subscriber list from JSON file."""
    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, IOError, OSError) as e:
            log(f"WARNING: Failed to load subscribers: {e}")
    return []


def _save_subscribers(subscribers: List[Dict[str, Any]]) -> bool:
    """Save subscriber list to JSON file (atomic write)."""
    tmp_file = SUBSCRIBERS_FILE.with_suffix('.tmp')
    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(subscribers, f, indent=2, ensure_ascii=False)
        tmp_file.replace(SUBSCRIBERS_FILE)
        return True
    except (IOError, OSError) as e:
        log(f"ERROR: Failed to save subscribers: {e}")
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except OSError:
            pass
        return False


def _find_subscriber(subscribers: List[Dict], email_addr: str) -> Optional[Dict]:
    """Find a subscriber by email address (case-insensitive)."""
    email_lower = email_addr.lower().strip()
    for sub in subscribers:
        if sub.get('email', '').lower().strip() == email_lower:
            return sub
    return None


def _get_operator(config: Dict[str, Any]) -> Dict[str, str]:
    """Extract operator info from config, with safe defaults."""
    op = config.get('operator', {})
    return {
        'name': op.get('name', ''),
        'business_name': op.get('business_name', ''),
        'postal_address': op.get('postal_address', ''),
        'contact_email': op.get('contact_email', config.get('email', {}).get('sender', '')),
    }


def _send_to_single_recipient(config: Dict[str, Any], recipient_email: str,
                                subject: str, html_body: str) -> bool:
    """Send an HTML email to a single recipient via SMTP."""
    try:
        smtp_cfg = get_smtp_config(config)
        sender = smtp_cfg['sender']
        password = smtp_cfg['password']
        if not (sender and password and recipient_email):
            log("ERROR: Missing SMTP credentials for subscriber email")
            return False

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        server = smtplib.SMTP(smtp_cfg['host'], smtp_cfg['port'], timeout=30)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [recipient_email], msg.as_string())
        server.quit()

        # Gmail cleanup: delete from Sent Mail to keep inbox clean
        if smtp_cfg['host'] == 'smtp.gmail.com':
            gmail_cleanup_sent(sender, password, subject, timeout=30)

        log(f"Subscriber email sent: {subject} -> {recipient_email}")
        return True
    except (smtplib.SMTPException, OSError) as e:
        log(f"Failed to send subscriber email to {recipient_email}: {e}")
        return False


def invite_subscriber(config: Dict[str, Any], email_addr: str, name: str,
                      phone: str = "", language: str = "en",
                      searches: Optional[List[str]] = None,
                      custom_message: str = "") -> bool:
    """
    Send invitation email and record subscriber as 'invited'.

    Args:
        config: The full ebay_config dict
        email_addr: Subscriber email address
        name: Subscriber display name
        phone: Phone number for operator records (optional)
        language: Language preference, "en" or "he" (default "en")
        searches: List of search name strings to subscribe to (empty = all)
        custom_message: Personal note shown in invitation email (optional)

    Returns:
        True if invitation sent successfully
    """
    from email_templates import format_invitation_email

    # Validate language
    if language not in ("en", "he"):
        language = "en"

    subscribers = _load_subscribers()

    # Check if already exists
    existing = _find_subscriber(subscribers, email_addr)
    if existing:
        status = existing.get('status', 'unknown')
        if status == 'confirmed':
            log(f"Subscriber {email_addr} is already confirmed")
            print(f"Already confirmed: {email_addr}")
            return False
        elif status == 'invited':
            log(f"Re-sending invitation to {email_addr}")
            print(f"Re-sending invitation to: {email_addr}")
        elif status == 'unsubscribed':
            log(f"Re-inviting previously unsubscribed: {email_addr}")
            print(f"Re-inviting (was unsubscribed): {email_addr}")

    operator = _get_operator(config)
    consent_text = DEFAULT_CONSENT_TEXT

    subject, html_body = format_invitation_email(
        name, email_addr, operator, consent_text,
        searches=searches, custom_message=custom_message, language=language
    )

    if not _send_to_single_recipient(config, email_addr, subject, html_body):
        log(f"Failed to send invitation to {email_addr}")
        print(f"FAILED: Could not send invitation to {email_addr}")
        return False

    # Record or update subscriber
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        existing['status'] = 'invited'
        existing['name'] = name
        existing['phone'] = phone
        existing['language'] = language
        existing['searches'] = searches or []
        existing['custom_message'] = custom_message
        existing['invited_at'] = now
        existing['consent_text_shown'] = consent_text
        existing['confirmed_at'] = None
        existing['unsubscribed_at'] = None
        existing['unsubscribe_reason'] = None
    else:
        subscribers.append({
            'name': name,
            'email': email_addr.lower().strip(),
            'phone': phone,
            'language': language,
            'searches': searches or [],
            'custom_message': custom_message,
            'status': 'invited',
            'invited_at': now,
            'consent_text_shown': consent_text,
            'confirmed_at': None,
            'confirmation_method': None,
            'unsubscribed_at': None,
            'unsubscribe_reason': None,
        })

    _save_subscribers(subscribers)
    log(f"Invitation sent to {name} <{email_addr}>")
    print(f"OK: Invitation sent to {name} <{email_addr}>")
    return True


def check_confirmations(config: Dict[str, Any]) -> int:
    """
    Check IMAP inbox for CONFIRM/UNSUBSCRIBE replies from subscribers.

    Connects to Gmail IMAP, searches for UNSEEN messages, matches sender
    against known subscribers, processes CONFIRM or UNSUBSCRIBE actions.

    Args:
        config: The full ebay_config dict

    Returns:
        Number of actions processed
    """
    from email_templates import format_confirmation_email, format_unsubscribe_email

    smtp_cfg = get_smtp_config(config)
    sender = smtp_cfg['sender']
    password = smtp_cfg['password']
    if not (sender and password):
        log("Cannot check confirmations: missing email credentials")
        return 0

    subscribers = _load_subscribers()
    if not subscribers:
        return 0

    # Build lookup: email -> subscriber record
    sub_lookup = {}
    for sub in subscribers:
        sub_lookup[sub.get('email', '').lower().strip()] = sub

    actions_processed = 0

    try:
        imap_cfg = get_imap_config(config)
        imap = imaplib.IMAP4_SSL(imap_cfg['host'], timeout=30)
        imap.login(sender, password)
        imap.select("INBOX")

        # Search for UNSEEN messages
        _, msg_nums = imap.search(None, "UNSEEN")
        if not msg_nums[0]:
            imap.logout()
            return 0

        for msg_num in msg_nums[0].split():
            try:
                _, msg_data = imap.fetch(msg_num, "(RFC822)")
                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)

                # Extract sender
                from_header = msg.get("From", "")
                # Parse "Name <email>" or bare "email"
                if '<' in from_header and '>' in from_header:
                    reply_email = from_header.split('<')[1].split('>')[0].lower().strip()
                else:
                    reply_email = from_header.lower().strip()

                # Check if sender is a known subscriber
                sub = sub_lookup.get(reply_email)
                if not sub:
                    continue  # Not from a subscriber, skip

                # Extract body text
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            try:
                                body_text = part.get_payload(decode=True).decode('utf-8', errors='replace')
                            except Exception:
                                pass
                            break
                else:
                    try:
                        body_text = msg.get_payload(decode=True).decode('utf-8', errors='replace')
                    except Exception:
                        pass

                body_upper = body_text.strip().upper()
                # Also check subject line for CONFIRM/UNSUBSCRIBE
                subject_upper = (msg.get("Subject", "") or "").upper()
                combined = body_upper + " " + subject_upper

                operator = _get_operator(config)

                if "UNSUBSCRIBE" in combined:
                    # Process unsubscribe
                    if sub['status'] != 'unsubscribed':
                        sub['status'] = 'unsubscribed'
                        sub['unsubscribed_at'] = datetime.now(timezone.utc).isoformat()
                        sub['unsubscribe_reason'] = 'email_reply'

                        unsub_subject, unsub_body = format_unsubscribe_email(reply_email, operator)
                        _send_to_single_recipient(config, reply_email, unsub_subject, unsub_body)

                        log(f"Subscriber UNSUBSCRIBED: {reply_email}")
                        actions_processed += 1

                elif "CONFIRM" in combined:
                    # Process confirmation
                    if sub['status'] == 'invited':
                        sub['status'] = 'confirmed'
                        sub['confirmed_at'] = datetime.now(timezone.utc).isoformat()
                        sub['confirmation_method'] = 'email_reply'

                        confirm_subject, confirm_body = format_confirmation_email(
                            sub.get('name', ''), reply_email, operator
                        )
                        _send_to_single_recipient(config, reply_email, confirm_subject, confirm_body)

                        log(f"Subscriber CONFIRMED: {reply_email}")
                        actions_processed += 1

            except Exception as e:
                log(f"Error processing message {msg_num}: {e}")
                continue

        imap.logout()

    except (imaplib.IMAP4.error, OSError) as e:
        log(f"IMAP check error: {e}")
        return actions_processed

    if actions_processed > 0:
        _save_subscribers(subscribers)
        log(f"Processed {actions_processed} subscriber action(s)")

    return actions_processed


def unsubscribe(email_addr: str, reason: str = "manual") -> bool:
    """
    Unsubscribe a subscriber by email address.

    Args:
        email_addr: The subscriber's email
        reason: Reason for unsubscribe (manual, email_reply, etc.)

    Returns:
        True if subscriber was found and unsubscribed
    """
    subscribers = _load_subscribers()
    sub = _find_subscriber(subscribers, email_addr)
    if not sub:
        print(f"Not found: {email_addr}")
        return False

    if sub['status'] == 'unsubscribed':
        print(f"Already unsubscribed: {email_addr}")
        return False

    sub['status'] = 'unsubscribed'
    sub['unsubscribed_at'] = datetime.now(timezone.utc).isoformat()
    sub['unsubscribe_reason'] = reason

    _save_subscribers(subscribers)
    log(f"Subscriber manually unsubscribed: {email_addr}")
    print(f"OK: Unsubscribed {email_addr}")
    return True


def update_subscriber(email_addr: str, phone: Optional[str] = None,
                      language: Optional[str] = None,
                      searches: Optional[List[str]] = None,
                      custom_message: Optional[str] = None) -> bool:
    """
    Update subscriber fields without re-sending the invitation email.

    Only non-None arguments are updated. Pass an empty list for searches
    to reset to "all", or a list of names to set specific searches.

    Args:
        email_addr: The subscriber's email
        phone: New phone (or None to keep current)
        language: New language "en"/"he" (or None to keep current)
        searches: New search list (or None to keep current)
        custom_message: New message (or None to keep current)

    Returns:
        True if subscriber was found and updated
    """
    subscribers = _load_subscribers()
    sub = _find_subscriber(subscribers, email_addr)
    if not sub:
        print(f"Not found: {email_addr}")
        return False

    changed = []
    if phone is not None:
        sub['phone'] = phone
        changed.append('phone')
    if language is not None:
        if language in ('en', 'he'):
            sub['language'] = language
            changed.append('language')
        else:
            print(f"WARNING: Invalid language '{language}', ignoring (must be 'en' or 'he')")
    if searches is not None:
        sub['searches'] = searches
        changed.append('searches')
    if custom_message is not None:
        sub['custom_message'] = custom_message
        changed.append('custom_message')

    if not changed:
        print(f"No fields to update for {email_addr}")
        return False

    _save_subscribers(subscribers)
    log(f"Subscriber updated ({', '.join(changed)}): {email_addr}")
    print(f"OK: Updated {email_addr} [{', '.join(changed)}]")
    return True


def get_active_subscribers() -> List[Dict[str, Any]]:
    """Return list of confirmed, non-unsubscribed subscribers."""
    subscribers = _load_subscribers()
    return [s for s in subscribers if s.get('status') == 'confirmed']


def list_all_subscribers() -> List[Dict[str, Any]]:
    """Return all subscribers with their current status."""
    return _load_subscribers()


def get_subscriber_status(email_addr: str) -> Optional[Dict[str, Any]]:
    """Get a single subscriber's full record."""
    subscribers = _load_subscribers()
    return _find_subscriber(subscribers, email_addr)


def send_to_subscriber(config: Dict[str, Any], subscriber: Dict[str, Any],
                       all_listings: List[Dict[str, Any]],
                       listing_type: str = "new") -> bool:
    """
    Send filtered listings to a single subscriber based on their search preferences.

    Args:
        config: The full ebay_config dict
        subscriber: The subscriber record dict
        all_listings: All listings found in this cycle
        listing_type: "new" or "price_drop" (controls subject format)

    Returns:
        True if email was sent successfully
    """
    from email_templates import get_subject_line, get_listing_html

    recipient = subscriber.get('email', '')
    if not recipient:
        return False

    # Filter listings by subscriber's search preferences
    sub_searches = subscriber.get('searches', [])
    if sub_searches:
        # Normalize search names for matching (case-insensitive)
        sub_searches_lower = [s.lower().strip() for s in sub_searches]
        filtered = [item for item in all_listings
                    if (item.get('search_name', '') or '').lower().strip() in sub_searches_lower]
    else:
        # Empty searches = receive all listings
        filtered = list(all_listings)

    if not filtered:
        return False  # Don't send empty email

    # Generate subject and body for this subscriber
    if listing_type == "price_drop":
        count = len(filtered)
        subject = f"\u05e4\u05e8\u05e1\u05d5\u05de\u05ea: [eBay API] PRICE DROP: {count} ITEM{'S' if count > 1 else ''} NOW IN RANGE"
        source_name = "eBay PRICE DROPS"
    else:
        subject = get_subject_line("eBay API", filtered, is_self_notif=False)
        source_name = "eBay API"

    html_body = get_listing_html(source_name, filtered, is_self_notif=False)
    return _send_to_single_recipient(config, recipient, subject, html_body)


def send_to_all_subscribers(config: Dict[str, Any],
                            all_listings: List[Dict[str, Any]],
                            listing_type: str = "new") -> int:
    """
    Send per-subscriber filtered emails to all active (confirmed) subscribers.

    Each subscriber receives only listings matching their search preferences.
    Subscribers with no search preferences receive all listings.

    Args:
        config: The full ebay_config dict
        all_listings: Raw listing dicts with 'search_name' field
        listing_type: "new" or "price_drop" (controls subject format)

    Returns:
        Number of emails successfully sent
    """
    active = get_active_subscribers()
    if not active:
        return 0

    if not all_listings:
        return 0

    sent_count = 0
    for sub in active:
        if send_to_subscriber(config, sub, all_listings, listing_type):
            sent_count += 1

    if sent_count > 0:
        log(f"Subscriber broadcast: {sent_count}/{len(active)} emails sent ({listing_type})")

    return sent_count
