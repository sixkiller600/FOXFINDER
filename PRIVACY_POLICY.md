# FoxFinder Privacy Policy

**Last Updated:** February 2026
**Version:** 2.0.0

## Overview

FoxFinder is an eBay deal notification application that uses the **official eBay Browse API** exclusively to search for items matching configured criteria. This application operates in full compliance with the eBay API License Agreement, eBay Partner Network Terms, and applicable privacy laws including Israeli law. This privacy policy explains what data is collected, how it's used, and your rights regarding that data.

**This policy is designed to be consistent with the [eBay Privacy Notice](https://www.ebay.com/help/policies/member-behaviour-policies/user-privacy-notice-privacy-policy?id=4260).**

## Operation Modes

FoxFinder operates in two modes:

### Personal Use Mode
When the operator uses FoxFinder for their own deal notifications (sender and recipient are the same person), it functions as a personal tool exempt from commercial message regulations under Israeli law.

### Service Mode
When the operator provides notification services to clients:
- **The operator holds the eBay API credentials** - clients do not need their own eBay Developer accounts
- Clients subscribe through **manual one-on-one registration** with the operator
- Each client personally contacts the operator to subscribe (email, phone, or in-person)
- The operator maintains records of subscriber consent
- Full Israeli Anti-Spam Law compliance is automatically applied to all client notifications

## Data Controller

**Personal Use:** The individual operating the application for themselves.

**Service Mode:** The service operator who holds the eBay API credentials and manages client subscriptions. For privacy inquiries, contact the service operator directly.

## Data We Collect

### 1. eBay Listing Data
When FoxFinder searches eBay on your behalf, it temporarily stores:
- **Item IDs** - Unique identifiers for eBay listings
- **Item Titles** - Product names/descriptions
- **Prices** - Current listing prices
- **Listing URLs** - Links to eBay item pages
- **Seller Location** - General geographic location (country)
- **Listing Timestamps** - When items were listed

**Purpose:** To identify new listings and price changes, preventing duplicate notifications.

**Data Freshness:** In compliance with eBay API License Agreement Section 8.1(c), item listing data displayed or used by FoxFinder is never more than **6 hours old**. Data older than this threshold is automatically refreshed from eBay's API.

**Retention:** Item data is automatically deleted after **14 days** or when no longer needed for deduplication. Upon termination of the application or your participation in the eBay Developers Program, all eBay content will be deleted within **10 days**.

### 2. Configuration Data
Locally stored configuration includes:
- **Search Queries** - Your specified search terms
- **Price Ranges** - Min/max price filters
- **Email Settings** - Notification delivery addresses

**Purpose:** To execute searches according to your preferences.

**Retention:** Stored locally until you modify or delete it.

### 3. API Credentials
- **eBay App ID** - Your eBay Developer Program credentials
- **Client Secret** - Authentication token (stored locally, never transmitted except to eBay)

**Purpose:** To authenticate with eBay's API.

**Retention:** Stored locally. Deleted upon application removal.

## Subscriber Data (Service Mode Only)

When operating as a notification service for clients, the operator maintains:

### Subscriber Information
- **Email addresses** of subscribed clients (for notification delivery)
- **Consent records** documenting when and how each subscriber opted in
- **Search preferences** configured for each subscriber

**Collection Method:** Manual one-on-one registration. Subscribers personally contact the operator to request service. No automated sign-up or electronic registration forms.

**Consent Documentation:** The operator maintains records showing:
- Date of subscription request
- Method of contact (email, phone, in-person)
- Explicit consent to receive commercial notifications
- Acknowledgment of affiliate link disclosure

**Retention:** Subscriber data is retained until the subscriber opts out or requests deletion.

## Data We Do NOT Collect

FoxFinder does **NOT** collect, store, or process:
- Personal information about eBay buyers or sellers
- eBay User IDs or passwords
- Payment or financial information
- Browsing history beyond item deduplication
- Seller performance statistics
- Market research data (average prices, category statistics)
- Any data for machine learning, AI training, or algorithmic modeling
- Automated tracking of subscriber behavior or click patterns

## Prohibited Data Uses

In compliance with eBay API License Agreement Section 9, FoxFinder explicitly does NOT:
- Derive site-wide statistics or aggregate category data
- Calculate average selling prices or gross merchandise values
- Aggregate seller or buyer performance data
- Use data for competitive purposes against eBay
- Train artificial intelligence or machine learning models
- Share data with third-party AI systems
- Perform market research or price analysis

## How Data Is Used

1. **Search Execution** - Query eBay's Browse API for matching listings
2. **Deduplication** - Track seen items to avoid repeat notifications
3. **Price Drop Detection** - Detect when items drop into your price range
4. **Email Notifications** - Notify you about new matching items (with eBay attribution)

## Data Sharing

FoxFinder does **NOT** share your data with any third parties except:
- **eBay** - API requests are sent directly to eBay's servers
- **eBay Partner Network** - Affiliate tracking headers when configured
- **Email Provider** - Notifications are sent via your configured SMTP server

## Data Security

- All API communication uses HTTPS/TLS encryption
- Credentials are stored locally on your device only
- No data is transmitted to external servers (except eBay API and your email provider)
- Atomic file writes prevent data corruption
- Industry-standard technical and organizational measures protect stored data

## Your Rights

You have the right to:
1. **Access** - View all data stored by FoxFinder (check local files)
2. **Deletion** - Delete all stored data by removing configuration files
3. **Portability** - Export your configuration (JSON format)
4. **Modification** - Update or remove any stored data at any time

### How to Delete Your Data

1. Stop FoxFinder using "FoxFinder OFF"
2. Delete the following files:
   - `ebay_config.json` - Your configuration
   - `ebay_seen_api.json` - Seen item cache
   - `ebay_token.json` - OAuth tokens
   - `ebay_rate_limit.json` - Rate limit tracking

### Termination Cleanup

Upon termination of your use of FoxFinder or termination from the eBay Developers Program, all eBay Content and Personal Information will be destroyed within **ten (10) days**, in compliance with eBay API License Agreement Section 12.

## Third-Party Services

### eBay Browse API
FoxFinder uses the eBay Browse API. Your use is subject to:
- [eBay API License Agreement](https://developer.ebay.com/join/api-license-agreement)
- [eBay User Agreement](https://www.ebay.com/help/policies/member-behaviour-policies/user-agreement?id=4259)
- [eBay Privacy Notice](https://www.ebay.com/help/policies/member-behaviour-policies/user-privacy-notice-privacy-policy?id=4260)

### eBay Partner Network (If Configured)
When configured with EPN affiliate tracking:
- [eBay Partner Network Agreement](https://partnernetwork.ebay.com/legal/terms-and-conditions)
- Affiliate campaign ID is transmitted with API requests
- Revenue sharing applies per EPN terms

## Children's Privacy

FoxFinder is not intended for use by children under 18. We do not knowingly collect data from minors.

## Changes to This Policy

This privacy policy may be updated periodically. Significant changes will be noted in the application changelog.

## Compliance

This application is designed to comply with:
- eBay API License Agreement (including Section 8 data handling and Section 9 prohibited uses)
- eBay Developer Program policies
- eBay Partner Network Agreement (when applicable)
- GDPR (General Data Protection Regulation)
- CCPA (California Consumer Privacy Act)
- **Israeli Anti-Spam Law (Amendment 40 to Communications Law, 1982)**
- **Israeli Privacy Protection Law (PPL) 5741-1981**

---

## Israeli Law Compliance

### Amendment 40 (Anti-Spam Law) Compliance

FoxFinder complies with Israeli Amendment 40 to the Communications (Broadcasting and Telecommunications) Law, 1982, which regulates commercial electronic messages.

**Personal Use Exemption:**
When the email sender and recipient are the same person (self-notification), the application operates as a personal tool and is **exempt from commercial message requirements**. This is because:
- The "recipient" has implicitly consented by configuring the application
- No third party receives unsolicited commercial messages
- The application serves as a personal notification tool, not marketing software

**Service Mode - Full Compliance:**
When operating as a service for clients, FoxFinder implements full Israeli Anti-Spam Law compliance:

**Consent Mechanism:**
- **Manual one-on-one registration** - Each subscriber personally contacts the operator
- No automated or electronic sign-up process
- Operator documents consent for each subscriber
- Subscribers can opt out at any time by contacting the operator

**Message Compliance:**
When sending to client recipients, FoxFinder automatically applies:

| Requirement | Implementation |
|-------------|----------------|
| Subject line marking | Prefix "פרסומת" (Advertisement) added |
| Advertiser identification | Sender email clearly identified |
| Affiliate disclosure | "This email contains affiliate links" notice |
| Opt-out mechanism | Clear instructions to disable notifications |
| Content requirements | eBay attribution and legal links included |

**Penalties Awareness:**
Israeli law provides for fines up to 202,000 NIS for non-compliant commercial messages and allows individuals to claim 1,000 NIS per message without proving damages.

### Privacy Protection Law (PPL) 5741-1981 Compliance

FoxFinder complies with Israel's Privacy Protection Law:

| Requirement | Implementation |
|-------------|----------------|
| Data minimization | Only item data stored, no personal information |
| Purpose limitation | Data used only for deal notifications |
| Data retention limits | 14-day automatic deletion |
| Right of access | User can view all local JSON files |
| Right to deletion | Clear deletion instructions provided |
| Security measures | HTTPS only, local storage, atomic writes |
| No database registration required | Personal use tool with <10,000 records |

### EU Adequacy Status

Israel maintains EU adequacy status (reconfirmed January 2024), meaning data transfers from EU to Israel meet GDPR standards. FoxFinder's data handling practices are consistent with both Israeli and EU data protection requirements.

## Contact

For privacy-related questions or data deletion requests, contact the application operator.

---

**eBay Disclaimer:** FoxFinder is an independent personal tool and is not affiliated with, endorsed by, or sponsored by eBay Inc. "eBay" is a registered trademark of eBay Inc. All eBay data is provided via the official eBay Browse API in compliance with eBay's terms of service.

---

*This privacy policy references eBay API License Agreement sections for compliance verification. For the complete agreement, visit: https://developer.ebay.com/join/api-license-agreement*
