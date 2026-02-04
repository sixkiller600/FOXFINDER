# -*- coding: utf-8 -*-
"""
FoxFinder Email Templates
=========================
Professional HTML email templates for eBay deal notifications.

Features:
- Clean, mobile-responsive design
- eBay-compliant attribution
- Dual timezone display (IL/US Pacific)
- Item age indicators
- Price formatting with proper currency symbols
- Israeli Anti-Spam Law (Amendment 40) compliance for third-party recipients
"""
import html
import re
from datetime import datetime

__version__ = "2.8.0"
# v2.8.0: EPN affiliate disclosure in header (above the fold) per eBay requirements
# v2.7.1: Fix opt-out notice for service model clients
# v2.7.0: Israeli Anti-Spam Law (Amendment 40) compliance
#         - Add "פרסומת" prefix for third-party recipients
#         - Add affiliate disclosure and opt-out instructions
#         - Self-notification exemption (sender == recipient)
# v2.6.0: Add thumbnail, shipping cost, seller feedback to listing rows
# v2.5.0: eBay Growth Check - "CONDITION UNKNOWN" instead of "N/A" for clarity
# v2.4.0: eBay Growth Check - show condition badge when item is not new
# v2.3.0: Add eBay ecosystem links (Today's Deals, Trending, Mobile App)
# v2.2.0: Add watchlist deep links for one-click "Add to Watchlist"
# v2.1.0: Add eBay Money Back Guarantee link
# v2.0.0: Complete redesign with eBay-compliant branding
# v1.0.0: Initial release with basic HTML templates

# Color scheme - professional dark theme
COLORS = {
    'bg_dark': '#000',
    'bg_container': '#111',
    'bg_header': '#0a0a0a',
    'bg_row': '#0d0d0d',
    'bg_row_alt': '#1a1a1a',
    'bg_update': '#1a1a00',
    'border': '#333',
    'border_accent': '#0f0',
    'text_white': '#fff',
    'text_gray': '#666',
    'text_light': '#ccc',
    'text_dark': '#444',
    'text_green': '#0f0',
    'text_yellow': '#ff0',
    'text_cyan': '#0ff',
    'text_link': '#4af',
    'ebay_blue': '#0064d2',  # Official eBay blue
}

# eBay branding (required for API compliance)
EBAY_ATTRIBUTION = "Powered by eBay Browse API"
EBAY_LINK = "https://www.ebay.com"
EBAY_USER_AGREEMENT = "https://www.ebay.com/help/policies/member-behaviour-policies/user-agreement?id=4259"

# Israeli Anti-Spam Law (Amendment 40) Compliance
# These are only added when sending to third-party recipients (not self-notifications)
ISRAELI_AD_PREFIX = "פרסומת"  # Hebrew for "Advertisement" - required by Israeli law
AFFILIATE_DISCLOSURE = "This email contains affiliate links. We may earn a commission from qualifying purchases."
OPT_OUT_NOTICE = "To stop receiving notifications, reply to this email or contact the service operator."

# Operation Mode Detection
# FoxFinder supports two modes:
#
# 1. PERSONAL USE (Self-Notification)
#    - Operator sends notifications to themselves
#    - Sender == Recipient (or matches exempt email below)
#    - EXEMPT from Israeli Anti-Spam Law (personal use, not commercial)
#
# 2. SERVICE MODEL (Client Notifications)
#    - Operator provides service to clients using THEIR OWN API credentials
#    - Clients do NOT need eBay Developer accounts
#    - Clients subscribe via manual one-on-one registration with operator
#    - FULL Israeli Anti-Spam Law compliance automatically applied:
#      - "פרסומת" prefix in subject line
#      - Affiliate disclosure in footer
#      - Opt-out instructions included
#
# The is_self_notification() function determines which mode applies.
SELF_NOTIFICATION_EXEMPT_EMAIL = "ofirlevi@tutanota.com"

# eBay ecosystem links (drives traffic to eBay platform)
EBAY_DEALS = "https://www.ebay.com/deals"
EBAY_TRENDING = "https://www.ebay.com/trending"
EBAY_APP_IOS = "https://apps.apple.com/app/ebay/id282614216"
EBAY_APP_ANDROID = "https://play.google.com/store/apps/details?id=com.ebay.mobile"

# eBay official condition grading badges (shows eBay's trusted condition system)
# Maps API condition values to display badges with appropriate styling
CONDITION_BADGES = {
    # eBay Certified Refurbished Program (premium tier)
    'certified - refurbished': ('CERTIFIED REFURBISHED', '#0064d2', '#fff'),  # eBay blue
    'certified refurbished': ('CERTIFIED REFURBISHED', '#0064d2', '#fff'),
    # eBay Refurbished tiers
    'excellent - refurbished': ('EXCELLENT REFURBISHED', '#0064d2', '#fff'),
    'very good - refurbished': ('VERY GOOD REFURBISHED', '#0064d2', '#fff'),
    'good - refurbished': ('GOOD REFURBISHED', '#0064d2', '#fff'),
    # Standard conditions
    'new': ('NEW', '#00a650', '#fff'),  # Green for new
    'brand new': ('NEW', '#00a650', '#fff'),
    'new with tags': ('NEW WITH TAGS', '#00a650', '#fff'),
    'new without tags': ('NEW NO TAGS', '#00a650', '#fff'),
    'new with box': ('NEW WITH BOX', '#00a650', '#fff'),
    'new without box': ('NEW NO BOX', '#00a650', '#fff'),
    'new other': ('NEW OTHER', '#4caf50', '#fff'),
    'new other (see details)': ('NEW OTHER', '#4caf50', '#fff'),
    # Used conditions
    'like new': ('LIKE NEW', '#2196f3', '#fff'),  # Blue
    'seller refurbished': ('SELLER REFURB', '#9c27b0', '#fff'),  # Purple
    'manufacturer refurbished': ('MFR REFURB', '#9c27b0', '#fff'),
    'very good': ('VERY GOOD', '#ff9800', '#000'),  # Orange
    'good': ('GOOD', '#ff9800', '#000'),
    'acceptable': ('ACCEPTABLE', '#795548', '#fff'),  # Brown
    # Parts/repair
    'for parts or not working': ('FOR PARTS', '#f44336', '#fff'),  # Red
    'for parts': ('FOR PARTS', '#f44336', '#fff'),
}


def is_self_notification(sender: str, recipients: list) -> bool:
    """
    Check if this is a self-notification (exempt from Israeli Anti-Spam Law).

    Israeli Anti-Spam Law (Amendment 40) regulates commercial messages sent to
    THIRD PARTIES. Self-notifications where the sender is also the sole recipient
    are exempt as they constitute personal use, not commercial advertising.

    Args:
        sender: The email sender address
        recipients: List of recipient email addresses

    Returns:
        True if this is a self-notification (exempt from commercial compliance)
    """
    if not sender or not recipients:
        return False

    sender_lower = sender.lower().strip()

    # Check if all recipients are the sender themselves
    for recipient in recipients:
        recipient_lower = recipient.lower().strip()
        if recipient_lower != sender_lower:
            # Also check against known self-notification email
            if recipient_lower != SELF_NOTIFICATION_EXEMPT_EMAIL.lower():
                return False  # Has third-party recipient

    return True  # All recipients are self


def _get_condition_badge(condition, show_if_unknown=True):
    """
    Generate HTML badge for eBay's official condition grading.

    eBay Growth Check compliance: "Must indicate when the item is not new"
    - If condition is known and not new, we display the badge
    - If condition is unknown/missing, we show "CONDITION N/A" per compliance

    Args:
        condition: The condition string from eBay API
        show_if_unknown: If True, show "CONDITION N/A" badge when condition missing
    """
    if not condition:
        if show_if_unknown:
            # eBay Growth Check compliance: explicitly indicate when condition is unknown
            # "Must indicate when the item is not new" - clearer than "N/A"
            return f'<span style="display: inline-block; padding: 2px 5px; margin-top: 3px; font-size: 9px; font-weight: bold; background: {COLORS["text_dark"]}; color: #999; border-radius: 2px; letter-spacing: 0.5px;">CONDITION UNKNOWN</span>'
        return ""

    condition_lower = str(condition).lower().strip()

    # Look up in badge mapping
    if condition_lower in CONDITION_BADGES:
        label, bg_color, text_color = CONDITION_BADGES[condition_lower]
    else:
        # Default styling for unknown conditions - still show it
        label = condition.upper()[:20]
        bg_color = COLORS['text_gray']
        text_color = '#fff'

    return f'<span style="display: inline-block; padding: 2px 5px; margin-top: 3px; font-size: 9px; font-weight: bold; background: {bg_color}; color: {text_color}; border-radius: 2px; letter-spacing: 0.5px;">{html.escape(label)}</span>'


def _extract_item_id(url):
    """Extract eBay item ID from URL for watchlist deep linking."""
    if not url:
        return None
    # Pattern: /itm/123456789 or /itm/Title/123456789
    match = re.search(r'/itm/(?:[^/]+/)?(\d{10,14})', url)
    if match:
        return match.group(1)
    # Pattern: item_id in query string
    match = re.search(r'[?&]item[_]?id=(\d{10,14})', url, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _get_watchlist_url(item_id):
    """Generate eBay watchlist deep link URL."""
    if item_id:
        return f"https://www.ebay.com/myb/WatchList?item_id={item_id}"
    return None


def _build_email_wrapper(header_html, body_html, footer_text, border_color=None, is_self_notif=True):
    """
    Build complete HTML email with eBay-compliant branding.

    Israeli Anti-Spam Law (Amendment 40) Compliance:
    When is_self_notif=False (third-party recipients), adds:
    - Affiliate disclosure
    - Opt-out instructions
    - Legal compliance footer

    Args:
        header_html: HTML for email header
        body_html: HTML for email body
        footer_text: Text for footer
        border_color: Optional border color override
        is_self_notif: If True, skip commercial compliance (personal use)
    """
    border = border_color or COLORS['border_accent']

    # "Explore More on eBay" section - drives additional platform traffic
    explore_section = f'''
    <div style="padding: 12px 15px; background: {COLORS['bg_row_alt']}; border-top: 1px solid {COLORS['border']};">
        <div style="color: {COLORS['text_gray']}; font-size: 10px; letter-spacing: 1px; margin-bottom: 8px;">EXPLORE MORE ON EBAY</div>
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            <a href="{EBAY_DEALS}" style="color: {COLORS['ebay_blue']}; text-decoration: none; font-size: 11px; padding: 4px 8px; border: 1px solid {COLORS['border']}; border-radius: 3px;">Today's Deals</a>
            <a href="{EBAY_TRENDING}" style="color: {COLORS['ebay_blue']}; text-decoration: none; font-size: 11px; padding: 4px 8px; border: 1px solid {COLORS['border']}; border-radius: 3px;">Trending</a>
            <a href="{EBAY_LINK}/b/Electronics/bn_702988" style="color: {COLORS['ebay_blue']}; text-decoration: none; font-size: 11px; padding: 4px 8px; border: 1px solid {COLORS['border']}; border-radius: 3px;">Electronics</a>
            <a href="{EBAY_LINK}/globaldeals" style="color: {COLORS['ebay_blue']}; text-decoration: none; font-size: 11px; padding: 4px 8px; border: 1px solid {COLORS['border']}; border-radius: 3px;">Global Deals</a>
        </div>
    </div>'''

    # eBay Mobile App promotion - promotes eBay ecosystem
    app_section = f'''
    <div style="padding: 10px 15px; background: {COLORS['bg_header']}; border-top: 1px solid {COLORS['border']}; text-align: center;">
        <div style="color: {COLORS['text_gray']}; font-size: 10px; margin-bottom: 6px;">Shop faster with the eBay App</div>
        <a href="{EBAY_APP_IOS}" style="color: {COLORS['text_light']}; text-decoration: none; font-size: 10px; margin-right: 10px;">iOS App</a>
        <span style="color: {COLORS['text_dark']};">|</span>
        <a href="{EBAY_APP_ANDROID}" style="color: {COLORS['text_light']}; text-decoration: none; font-size: 10px; margin-left: 10px;">Android App</a>
    </div>'''

    # eBay Money Back Guarantee - promotes buyer confidence
    guarantee_section = f'''
    <div style="padding: 8px 15px; background: {COLORS['bg_row']}; border-top: 1px solid {COLORS['border']}; text-align: center;">
        <a href="https://www.ebay.com/help/policies/ebay-money-back-guarantee-policy/ebay-money-back-guarantee?id=4210" style="color: {COLORS['text_gray']}; text-decoration: none; font-size: 10px;">Shop with confidence - eBay Money Back Guarantee</a>
    </div>'''

    # eBay attribution footer (required for compliance)
    ebay_footer = f'''
    <div style="text-align: center; padding: 10px 15px; background: {COLORS['bg_row_alt']}; border-top: 1px solid {COLORS['border']};">
        <a href="{EBAY_LINK}" style="color: {COLORS['ebay_blue']}; text-decoration: none; font-size: 11px;">{EBAY_ATTRIBUTION}</a>
        <span style="color: {COLORS['text_dark']}; font-size: 10px;"> | </span>
        <a href="{EBAY_USER_AGREEMENT}" style="color: {COLORS['text_gray']}; text-decoration: none; font-size: 10px;">eBay User Agreement</a>
    </div>'''

    # Israeli Anti-Spam Law (Amendment 40) compliance footer
    # Only shown for third-party recipients (not self-notifications)
    israeli_compliance_footer = ""
    if not is_self_notif:
        israeli_compliance_footer = f'''
    <div style="padding: 12px 15px; background: {COLORS['bg_header']}; border-top: 1px solid {COLORS['border']};">
        <div style="color: {COLORS['text_gray']}; font-size: 9px; line-height: 1.5;">
            <strong style="color: {COLORS['text_light']};">Affiliate Disclosure:</strong> {html.escape(AFFILIATE_DISCLOSURE)}<br>
            <strong style="color: {COLORS['text_light']};">Opt-Out:</strong> {html.escape(OPT_OUT_NOTICE)}<br>
            <span style="color: {COLORS['text_dark']};">Israeli Anti-Spam Law (Amendment 40) compliant. eBay Partner Network affiliate.</span>
        </div>
    </div>'''

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        @media screen and (max-width: 480px) {{
            .container {{ width: 100% !important; padding: 0 !important; }}
            .header-title {{ font-size: 18px !important; }}
            td {{ padding: 8px 6px !important; }}
            .item-title {{ font-size: 12px !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 10px; background: {COLORS['bg_dark']}; font-family: monospace;">
<div class="container" style="max-width: 500px; margin: 0 auto; background: {COLORS['bg_container']}; border: 2px solid {border};">
    {header_html}
    {body_html}
    {explore_section}
    {app_section}
    {guarantee_section}
    {ebay_footer}
    {israeli_compliance_footer}
    <div style="background: {COLORS['bg_header']}; padding: 8px 15px; border-top: 1px solid {COLORS['border']};">
        <div style="color: {COLORS['text_dark']}; font-size: 9px;">{html.escape(footer_text)}</div>
    </div>
</div>
</body>
</html>'''


def get_subject_line(source_name, listings, is_self_notif=True):
    """
    Generate email subject line.

    Israeli Anti-Spam Law (Amendment 40) Compliance:
    When sending to third-party recipients (not self-notifications),
    the subject line must be prefixed with "פרסומת" (Advertisement).

    Args:
        source_name: The source identifier (e.g., "eBay API")
        listings: List of listing dictionaries
        is_self_notif: If True, this is a self-notification (exempt from commercial law)
                       If False, adds "פרסומת" prefix for Israeli compliance
    """
    count = len(listings) if listings else 0

    # Extract unique search names
    search_terms = []
    seen = set()
    source_name_lower = source_name.lower().strip()

    for item in (listings or []):
        search_name = (item.get('search_name') or '').strip()
        search_name_lower = search_name.lower()
        if search_name and search_name not in seen and search_name_lower != source_name_lower:
            seen.add(search_name)
            words = search_name.split()[:2]
            search_terms.append(' '.join(words))

    base = f"[{source_name.upper()}] {count} New Listing{'s' if count != 1 else ''} Found"

    if search_terms:
        if len(search_terms) == 1:
            subject = f"{base} [{search_terms[0]}]"
        else:
            subject = f"{base} [MULTIPLE]"
    else:
        subject = base

    # Israeli Anti-Spam Law: Add "פרסומת" prefix for third-party recipients
    if not is_self_notif:
        subject = f"{ISRAELI_AD_PREFIX}: {subject}"

    return subject


def get_listing_html(source_name, listings, updated_listings=None, source_url=None, is_self_notif=True):
    """
    Generate HTML email body for listings.

    Args:
        source_name: The source identifier
        listings: List of new listings
        updated_listings: List of updated listings (price drops, etc.)
        source_url: Optional source URL
        is_self_notif: If True, skip commercial compliance footer (personal use)
    """
    all_l = list(listings or [])
    upd = list(updated_listings or [])
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = "".join([_build_listing_row(i, False) for i in all_l] +
                   [_build_listing_row(i, True) for i in upd])

    # EPN Affiliate Disclosure - ALWAYS shown per eBay Partner Network requirements
    # Must be "above the fold" near promotional content, not buried in footer
    affiliate_notice = f'<div style="color: {COLORS["text_gray"]}; font-size: 9px; margin-top: 6px; font-style: italic;">Ad - Contains affiliate links</div>'

    header = f'''
    <div style="background: {COLORS['bg_header']}; padding: 12px 15px; border-bottom: 2px solid {COLORS['border_accent']};">
        <div style="color: {COLORS['text_green']}; font-size: 10px; letter-spacing: 2px;">FOXFINDER</div>
        <div class="header-title" style="color: {COLORS['text_white']}; font-size: 20px; font-weight: bold; margin-top: 5px;">{html.escape(source_name.upper())}</div>
        <div style="color: {COLORS['text_gray']}; font-size: 11px; margin-top: 4px;">{ts} | {len(all_l)+len(upd)} items</div>
        {affiliate_notice}
    </div>'''

    body = f'''
    <table style="width: 100%; border-collapse: collapse; background: {COLORS['bg_row']};">
        <tr style="background: {COLORS['bg_row_alt']}; border-bottom: 1px solid {COLORS['border']};">
            <td style="padding: 6px 8px; color: {COLORS['text_gray']}; font-size: 9px;">ITEM</td>
            <td style="padding: 6px 8px; color: {COLORS['text_gray']}; font-size: 9px; text-align: right;">PRICE</td>
        </tr>
        {rows}
    </table>'''

    return _build_email_wrapper(header, body, "FOXFINDER AUTO-NOTIFICATION", is_self_notif=is_self_notif)


def _build_listing_row(item, is_update=False):
    """Build a single listing row for the email table."""
    raw_link = item.get('link', '#')
    link = html.escape(raw_link)
    title = item.get('title', '')
    display_text = str(title)[:100] if title else link.split("/")[-1][:8]

    # Price formatting
    p = item.get('price', '---')
    p_str = "---"
    if p and str(p) not in ['N/A', 'None', '---']:
        sym = "$"
        if isinstance(p, (int, float)):
            p_str = f"{sym}{p:,.0f}"
        else:
            p_s = str(p)
            if re.match(r'^[\d,]+\.?\d*$', p_s.replace(',', '')):
                try:
                    val = float(p_s.replace(',', ''))
                    p_str = f"{sym}{val:,.0f}"
                except ValueError:
                    p_str = p_s
            else:
                nums = "".join(re.findall(r'\d+', p_s.replace(',', '')))
                if nums:
                    p_str = f"{sym}{int(nums):,}"
                else:
                    p_str = p_s

    bg = f'background: {COLORS["bg_update"]};' if is_update else ''
    txt_c = COLORS['text_yellow'] if is_update else COLORS['text_link']

    # Time/location info
    time_parts = []
    created_il = item.get('created_il', '')
    created_us = item.get('created_us', '')
    location = item.get('location', '')

    if created_il:
        time_parts.append(f"IL: {created_il}")
    if created_us:
        time_parts.append(f"US: {created_us}")

    time_line = " | ".join(time_parts) if time_parts else ""
    location_line = f"[LOC] {location}" if location else ""

    # Condition badge (eBay official grading)
    condition = item.get('condition', '')
    condition_badge = _get_condition_badge(condition)

    # Shipping cost display
    shipping_cost = item.get('shipping_cost', '')
    shipping_html = ""
    if shipping_cost == "FREE":
        shipping_html = f'<div style="font-size: 9px; color: #00a650; margin-top: 2px; font-weight: bold;">FREE SHIPPING</div>'
    elif shipping_cost:
        shipping_html = f'<div style="font-size: 9px; color: {COLORS["text_gray"]}; margin-top: 2px;">Ship: {html.escape(shipping_cost)}</div>'

    # Seller feedback display
    seller_pct = item.get('seller_feedback_pct', '')
    seller_score = item.get('seller_feedback_score', '')
    seller_html = ""
    if seller_pct and seller_score:
        seller_html = f'<div style="font-size: 9px; color: {COLORS["text_gray"]}; margin-top: 2px;">Seller: {html.escape(str(seller_pct))}% ({html.escape(str(seller_score))})</div>'

    info_html = ""
    if condition_badge:
        info_html += f'<div style="margin-top: 3px;">{condition_badge}</div>'
    if shipping_html:
        info_html += shipping_html
    if seller_html:
        info_html += seller_html
    if time_line:
        info_html += f'<div style="font-size: 9px; color: {COLORS["text_cyan"]}; margin-top: 3px;">{html.escape(time_line)}</div>'
    if location_line:
        info_html += f'<div style="font-size: 9px; color: {COLORS["text_gray"]}; margin-top: 2px;">{html.escape(location_line)}</div>'

    # Generate watchlist link if item ID can be extracted
    item_id = _extract_item_id(raw_link)
    watchlist_url = _get_watchlist_url(item_id)
    watch_link_html = ""
    if watchlist_url:
        watch_link_html = f' <a href="{html.escape(watchlist_url)}" style="color: {COLORS["text_cyan"]}; text-decoration: none; font-size: 10px;">[WATCH]</a>'

    # Thumbnail image
    image_url = item.get('image_url', '')
    thumb_html = ""
    if image_url:
        thumb_html = f'<img src="{html.escape(image_url)}" alt="" width="60" height="60" style="float: left; margin-right: 8px; margin-bottom: 4px; border-radius: 3px; background: #222;">'

    return f'''
    <tr style="border-bottom: 1px solid {COLORS['border']}; {bg}">
        <td style="padding: 10px 8px; vertical-align: top;">
            {thumb_html}<a href="{link}" style="color: {txt_c}; text-decoration: none; font-size: 13px; line-height: 1.3; display: block;">{html.escape(display_text)}</a>{info_html}
        </td>
        <td style="padding: 10px 8px; text-align: right; vertical-align: top; white-space: nowrap;">
            <div style="color: {COLORS['text_green']}; font-weight: bold; font-size: 15px;">{html.escape(p_str)}</div>
            <a href="{link}" style="color: {COLORS['text_gray']}; text-decoration: none; font-size: 10px;">[VIEW]</a>{watch_link_html}
        </td>
    </tr>'''


def format_listing_email(source_name, new_ads, updated_ads=None, source_url=None, is_self_notif=True):
    """
    Format complete listing email (subject + body).

    Args:
        source_name: The source identifier
        new_ads: List of new listings
        updated_ads: List of updated listings
        source_url: Optional source URL
        is_self_notif: If True, skip commercial compliance (personal use)
                       If False, add Israeli Anti-Spam Law compliance
    """
    all_n = list(new_ads or [])
    all_u = list(updated_ads or [])
    if not all_n and not all_u:
        return None, None
    return (
        get_subject_line(source_name, all_n + all_u, is_self_notif=is_self_notif),
        get_listing_html(source_name, all_n, all_u, source_url=source_url, is_self_notif=is_self_notif)
    )


def format_notice_email(notice_type, details, stats=None):
    """Format system notice email (subject + body)."""
    return f"[NOTICE] {notice_type}", get_notice_html(notice_type, details, stats)


def get_notice_html(notice_type, details, stats=None):
    """Generate HTML for system notice emails (status updates, errors, etc.)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    stats_html = ""
    if stats:
        stats_html = f'''
        <div style="margin-top: 10px; padding: 8px; background: {COLORS['bg_row_alt']}; border-left: 2px solid {COLORS['text_yellow']};">
            <div style="color: {COLORS['text_gray']}; font-size: 10px;">STATS</div>
            <div style="color: {COLORS['text_light']}; font-size: 11px; margin-top: 4px;">
                {html.escape(str(stats))}
            </div>
        </div>'''

    header = f'''
    <div style="background: {COLORS['bg_header']}; padding: 12px 15px; border-bottom: 2px solid #f00;">
        <div style="color: #f00; font-size: 10px; letter-spacing: 2px;">FOXFINDER NOTICE</div>
        <div style="color: {COLORS['text_white']}; font-size: 18px; font-weight: bold; margin-top: 5px;">{html.escape(str(notice_type))}</div>
        <div style="color: {COLORS['text_gray']}; font-size: 11px; margin-top: 4px;">{ts}</div>
    </div>'''

    body = f'''
    <div style="padding: 15px; background: {COLORS['bg_row']};">
        <div style="color: {COLORS['text_light']}; font-size: 13px; line-height: 1.5;">
            {html.escape(str(details))}
        </div>
        {stats_html}
    </div>'''

    return _build_email_wrapper(header, body, "FOXFINDER SYSTEM NOTICE", border_color='#f00')


# Backward compatibility alias (deprecated)
get_alert_html = get_notice_html
