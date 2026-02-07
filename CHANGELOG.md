# Changelog

All notable changes to FoxFinder are documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.13.0] - 2026-02-07

### Added
- **`--dry-run` Mode** — run one search cycle, print results to console, no email sent, no state files updated
  - Useful for testing config changes, validating searches, and debugging
  - Reports item counts and sample titles/prices per search
  - Uses 1 API call per enabled search (same as a normal cycle)

### Changed
- **DRY Refactoring: `_enrich_item()` helper** — extracted duplicated 40-line item enrichment block
  (timezone, shipping, seller, condition, image) from price-drop and new-listing paths into a single helper
- **DRY Refactoring: `gmail_cleanup_sent()`** — extracted duplicated Gmail IMAP Sent/Trash cleanup
  from `foxfinder.py:send_email_core` and `subscriber_manager.py:_send_to_single_recipient` into
  `ebay_common.py`
- **IMAP Provider Auto-Detect** — `get_imap_config()` in `ebay_common.py` auto-detects
  Gmail/Outlook/Yahoo IMAP hosts from sender email domain (mirrors existing SMTP auto-detect)
  - `check_confirmations()` in subscriber_manager.py now uses auto-detected IMAP host

### Version Bumps
- foxfinder.py: 4.12.1 → 4.13.0
- ebay_common.py: 1.2.1 → 1.3.0
- subscriber_manager.py: 1.1.0 → 1.1.1
- test_qa.py: updated version assertions to match current versions

---

## [4.12.1] - 2026-02-06

### Added
- **Per-Subscriber Search Preferences** — subscribers now receive only listings matching their searches
  - `searches` field: list of search names to subscribe to (empty = all products)
  - Filtering applied per-subscriber at send time via `send_to_subscriber()`
  - Subscribers with no search preferences receive all listings (backwards compatible)
- **Custom Invitation Message** — operator can include a personal note in invitation emails
  - `custom_message` field stored per subscriber
  - Rendered in a styled box with operator name header in the invitation email
  - XSS-safe: all user input HTML-escaped
- **Phone Number** — stored per subscriber for operator records / compliance
  - `phone` field: optional, stored as-is
- **Language Preference** — `en` (English) or `he` (Hebrew)
  - `language` field: defaults to `en`
  - Stored in subscriber record for future use
- **New CLI Arguments** (all used with `--invite`)
  - `--searches "Asus Loki,AMD 9950X"` — comma-separated search names
  - `--message "Hey David, check these out!"` — personal note in invitation
  - `--phone "+972-50-1234567"` — phone for operator records
  - `--lang en|he` — language preference (default: en)
- **"Your Alerts" Section** in invitation email showing subscribed searches
- `send_to_subscriber()` function in subscriber_manager.py for per-subscriber filtering

### Changed
- `send_to_all_subscribers()` now accepts raw listings + listing type instead of pre-built subject/body
- `format_invitation_email()` accepts `searches`, `custom_message`, `language` parameters
- `--list-subscribers` table now shows `LANG` and `SEARCHES` columns
- Main loop subscriber broadcasts now use per-subscriber filtered `send_to_all_subscribers(config, listings, type)`
- subscriber_manager.py version bumped to 1.1.0
- email_templates.py version bumped to 2.10.0
- foxfinder.py version bumped to 4.12.1

---

## [4.12.0] - 2026-02-06

### Added
- **Double Opt-In Subscriber Invitation System**
  - Email-based invitation flow: invite → CONFIRM reply → welcome email
  - IMAP inbox monitoring for CONFIRM/UNSUBSCRIBE replies (automated double opt-in)
  - Subscriber lifecycle: invited → confirmed → unsubscribed
  - Consent proof storage (GDPR Art. 7): consent text shown, confirmation timestamp, method
  - Beautiful invitation email matching FoxFinder's dark theme with eBay blue accents
  - Welcome email with consent receipt after confirmation
  - Unsubscribe confirmation email
- **CLI Commands** (argparse-based)
  - `--invite EMAIL NAME` — Send invitation email to a new subscriber
  - `--check-confirmations` — Process IMAP inbox for CONFIRM/UNSUBSCRIBE replies
  - `--list-subscribers` — Display all subscribers with status table
  - `--unsubscribe EMAIL` — Manually unsubscribe an email address
  - `--subscriber-status EMAIL` — Show detailed subscriber record
- **Main Loop Integration**
  - Auto-check IMAP for subscriber replies every 5 cycles
  - Auto-forward new listing and price drop emails to all active subscribers
  - Graceful fallback: subscriber features disabled if module missing
- **Operator Identification** in config (CAN-SPAM compliance)
  - `operator.name`, `operator.postal_address`, `operator.contact_email`
  - Included in all subscriber email footers

### New File
- `subscriber_manager.py` v1.0.0 — Subscriber lifecycle management (zero new dependencies)
- `foxfinder_subscribers.json` — Subscriber data store (created on first invite)

### Changed
- foxfinder.py version bumped to 4.12.0
- email_templates.py version bumped to 2.9.0
- `ebay_config.json` / template: added `operator` section
- CLI now uses `argparse` (backwards compatible: `--validate` and bare run still work)

### Legal Compliance
- **GDPR**: Double opt-in, consent proof stored per subscriber, right to unsubscribe
- **Israeli Amendment 40**: "פרסומת" prefix, one-time invitation statement, sender ID
- **CAN-SPAM**: Physical postal address, immediate opt-out processing, accurate headers
- **eBay EPN**: "Ad - Contains affiliate links" above the fold in invitation email

---

## [4.11.0] - 2026-02-04

### Added
- **EPN Affiliate Disclosure in Header** - Per eBay Partner Network requirements
  - "Ad - Contains affiliate links" now appears in email header, above the fold
  - Disclosure visible before any affiliate links (not buried in footer)
  - Complies with FTC, ASA, and eBay Partner Network disclosure policies
  - Shows on ALL emails (EPN disclosure is separate from Israeli commercial law)

### Changed
- email_templates.py version bumped to 2.8.0

---

## [4.10.1] - 2026-02-04

### Fixed
- Opt-out notice now appropriate for service model clients: "reply to this email or contact the service operator"
- Previous wording referenced config access which service clients don't have

### Changed
- email_templates.py version bumped to 2.7.1

---

## [4.10.0] - 2026-02-04

### Added
- **Dual Operation Mode Support**
  - **Personal Use Mode**: Operator's own deal hunting (exempt from commercial compliance)
  - **Service Model**: Notification service for clients with full Israeli compliance
- **Israeli Anti-Spam Law (Amendment 40) compliance**
  - Self-notification exemption: emails to yourself are exempt from commercial compliance
  - Client notifications automatically get "פרסומת" (Advertisement) prefix in subject
  - Affiliate disclosure footer for client recipients
  - Opt-out instructions in email footer
- **Service Model Documentation**
  - Operator holds eBay API credentials (clients don't need their own)
  - Manual one-on-one client registration process
  - Consent tracking requirements for subscribers
- `is_self_notification()` function in email_templates.py to detect personal vs. service mode
- Israeli Privacy Protection Law (PPL) 5741-1981 compliance documentation
- Comprehensive Israeli compliance section in PRIVACY_POLICY.md
- Israeli compliance tables in COMPLIANCE_CHECKLIST.md

### Changed
- README.md: Added Operation Modes section explaining Personal Use vs Service Model
- PRIVACY_POLICY.md: Version 2.0.0 with service model and subscriber data sections
- COMPLIANCE_CHECKLIST.md: Version 1.4.0 with service model compliance details
- email_templates.py version bumped to 2.7.0
- `get_subject_line()` now accepts `is_self_notif` parameter
- `get_listing_html()` now accepts `is_self_notif` parameter
- `send_email()` and `send_price_drop_email()` now check recipient type

### Legal
- **Personal Use**: Self-notifications (sender == recipient) exempt from commercial compliance
- **Service Model**: Full Israeli Anti-Spam Law compliance for all client notifications
- Manual one-on-one registration satisfies Israeli consent requirements
- Operator's API credentials serve all clients (standard EPN affiliate model)
- Exempt email: ofirlevi@tutanota.com (configurable in email_templates.py)

---

## [4.9.1] - 2026-01-29

### Added
- Thumbnail images in email notifications (from Browse API `image.imageUrl`)
- Shipping cost display: "FREE SHIPPING" or "Ship: $X.XX" (from `shippingOptions`)
- Seller feedback percentage and score in listing rows (from `seller` object)
- State/province in item location (e.g., "California, US" instead of just "US")

## [4.9.0] - 2026-01-28

### Added
- `contextualLocation` header for improved shipping estimate accuracy (eBay recommendation)
- `itemEndDate` check to skip expired listings (eBay data freshness requirement)
- `estimatedAvailabilityStatus` check to skip unavailable items
- Enhanced price drop feature compliance documentation

### Changed
- X-EBAY-C-ENDUSERCTX header now includes `contextualLocation=country=US`
- Condition badge text changed from "N/A" to "UNKNOWN" for clarity

## [4.8.3] - 2026-01-28

### Changed
- Renamed `update_statistics` to `update_run_log` to avoid "statistics" terminology
  (eBay prohibits "site-wide statistics" - clarified this is operational logging only)

## [4.8.2] - 2026-01-27

### Fixed
- **CRITICAL**: API filter now respects `buy_it_now_only` legacy config field
- `buyingOptions:{FIXED_PRICE}` filter backwards compatibility

## [4.8.1] - 2026-01-27

### Fixed
- **CRITICAL**: Pass condition field to email templates (eBay requirement)
- Added backwards compatibility for `buy_it_now_only` config field

## [4.8.0] - 2026-01-26

### Added
- HTTP 429/503 retry handling in `search_ebay()`
- EPN Campaign ID validation (10 digits)
- Pagination resilience for varying result counts
- Documented `newlyListed` sort as business requirement

### Changed
- Default to `FIXED_PRICE` (eBay requires this for Buy API partners)

## [4.7.5] - 2026-01-25

### Fixed
- Missing UTF-8 encoding in token file I/O

## [4.7.4] - 2026-01-25

### Added
- Dynamic reset wait
- HTTP 429/503 retry
- Validation check
- Email visibility improvements

## [4.7.1] - 2026-01-24

### Fixed
- **CRITICAL**: `get_minutes_since_reset()` call signature
- Added defensive try-except blocks

## [4.7.0] - 2026-01-24

### Added
- Post-reset anomaly detection (Proactive Retry)
- Fixes 1-hour hangs after API sync lag

## [4.6.8] - 2026-01-23

### Added
- `requests.Session` for connection pooling (2-3x faster API checks)

## [4.6.7] - 2026-01-23

### Changed
- Increased search results limit 50→150 to reduce staggered alerts after downtime

## [4.6.5] - 2026-01-22

### Fixed
- BCC privacy bug - removed exposed Bcc header

## [4.6.4] - 2026-01-22

### Added
- Multi-recipient email support with BCC privacy

## [4.6.3] - 2026-01-21

### Fixed
- Email template import - was using fallback that outputs raw dicts

## [4.6.2] - 2026-01-21

### Fixed
- HTML email rendering - add UTF-8 charset to MIMEText

## [4.6.1] - 2026-01-21

### Added
- Timeout constants
- Temp file cleanup
- Specific exception handling

## [4.6.0] - 2026-01-20

### Added
- Price drop tracking - alerts when seen items drop into search criteria

## [4.5.0] - 2026-01-19

### Added
- Reliability improvements
- HTTP retry logic
- Token retry logic
- API validation
- Memory cap protection

## [4.4.0] - 2026-01-18

### Added
- Robust rate limit sync
- Post-reset retry logic
- Sanity validation
- Auto-recovery

---

## Component Versions

| Component | Version | Description |
|-----------|---------|-------------|
| `foxfinder.py` | 4.13.0 | Main application |
| `subscriber_manager.py` | 1.1.1 | Subscriber lifecycle management |
| `email_templates.py` | 2.10.0 | Email templates |
| `ebay_common.py` | 1.3.0 | Shared utilities |
| `shared_utils.py` | 1.2.0 | Utility functions |

---

*For compliance documentation, see [COMPLIANCE_CHECKLIST.md](COMPLIANCE_CHECKLIST.md)*
