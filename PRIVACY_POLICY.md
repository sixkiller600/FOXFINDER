# FoxFinder Privacy Policy

**Last Updated:** January 2026
**Version:** 1.1.0

## Overview

FoxFinder is a personal eBay deal notification application that uses the **official eBay Browse API** exclusively to search for items matching your configured criteria. This application operates in full compliance with the eBay API License Agreement and eBay Partner Network Terms. This privacy policy explains what data is collected, how it's used, and your rights regarding that data.

**This policy is designed to be consistent with the [eBay Privacy Notice](https://www.ebay.com/help/policies/member-behaviour-policies/user-privacy-notice-privacy-policy?id=4260).**

## Data Controller

This application is operated as a personal tool. For privacy inquiries, contact the application operator directly.

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

## Data We Do NOT Collect

FoxFinder does **NOT** collect, store, or process:
- Personal information about eBay buyers or sellers
- eBay User IDs or passwords
- Payment or financial information
- Browsing history beyond item deduplication
- Seller performance statistics
- Market research data (average prices, category statistics)
- Any data for machine learning, AI training, or algorithmic modeling

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

## Contact

For privacy-related questions or data deletion requests, contact the application operator.

---

**eBay Disclaimer:** FoxFinder is an independent personal tool and is not affiliated with, endorsed by, or sponsored by eBay Inc. "eBay" is a registered trademark of eBay Inc. All eBay data is provided via the official eBay Browse API in compliance with eBay's terms of service.

---

*This privacy policy references eBay API License Agreement sections for compliance verification. For the complete agreement, visit: https://developer.ebay.com/join/api-license-agreement*
