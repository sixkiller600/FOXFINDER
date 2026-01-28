# FoxFinder - eBay API Compliance Checklist

**Application:** FoxFinder eBay Deal Notification Service
**Version:** 1.2.0 (v4.9.0 code)
**API Used:** eBay Browse API (Buy APIs)
**Last Verified:** January 28, 2026
**Audit Level:** Exhaustive (Section 8 & 9 full compliance + OWASP)

---

## Application Growth Check Requirements

### Technical Requirements

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ✅ **Uses Browse API (not deprecated Finding API)** | PASS | `foxfinder.py` - uses `buy/browse/v1/item_summary/search` |
| ✅ **Max 2 retries for infrastructure errors** | PASS | `get_oauth_token()`: `max_retries=2`, `search_ebay()`: `max_retries=2` |
| ✅ **Graceful error handling** | PASS | All API calls wrapped in try/except with proper logging |
| ✅ **Uses latest API version** | PASS | Browse API v1 (current production version) |
| ✅ **Efficient data retrieval** | PASS | Only requests necessary fields, uses pagination limits |
| ✅ **Implements caching** | PASS | `ebay_seen_api.json` deduplication cache |
| ✅ **HTTP 429/503 handling** | PASS | `search_ebay()` handles rate limits and server errors with exponential backoff |
| ✅ **Pagination resilience** | PASS | Handles varying result counts gracefully with logging |
| ✅ **FIXED_PRICE default** | PASS | Default filter for Buy It Now items (eBay requirement) |
| ✅ **EPN Campaign ID validation** | PASS | Validates 10-digit format in config validation |
| ✅ **Condition display** | PASS | Shows condition badge, indicates when unknown (eBay requirement) |
| ✅ **contextualLocation header** | PASS | X-EBAY-C-ENDUSERCTX includes `contextualLocation=country=US` |
| ✅ **itemEndDate check** | PASS | Skips listings with EndDate in the past (data freshness) |
| ✅ **estimatedAvailabilityStatus check** | PASS | Skips unavailable items (best practice) |

### API Versions Used

| API | Version | Endpoint | Purpose |
|-----|---------|----------|---------|
| **Browse API** | v1 | `buy/browse/v1/item_summary/search` | Search for items |
| **OAuth** | v1 | `identity/v1/oauth2/token` | Authentication |
| **Analytics** | v1_beta | `developer/analytics/v1_beta/rate_limit` | Rate limit checking |

### Business Requirement: newlyListed Sorting

FoxFinder uses `sort=newlyListed` in API calls. This is a **core business requirement** for the application's deal notification functionality:

- **Purpose:** Alert users to newly listed items matching their search criteria
- **Why Required:** Without this, users cannot be notified of new deals in time
- **Alternative:** Default "Best Match" sorting would defeat the application's purpose
- **Documentation:** Explicitly documented in `search_ebay()` function comments

This has been disclosed in the Growth Check application.

### Price Drop Notification Feature - Compliance Clarification

FoxFinder includes a price drop notification feature. This section clarifies why it is **fully compliant** with eBay API License Agreement Section 9 prohibitions:

**What the feature does:**
- Tracks price changes on items the individual user has **already encountered**
- Notifies the user when a specific saved item's price drops into their search criteria
- Stores only: item ID, last seen price, timestamp (14-day retention)

**Why this is NOT "market research" or "price modeling" (prohibited):**

| Prohibited Activity | FoxFinder Behavior | Status |
|---------------------|-------------------|--------|
| "Site-wide statistics" | Only processes user's configured searches | ✅ COMPLIANT |
| "Aggregate pricing data" | NO aggregation - individual item tracking only | ✅ COMPLIANT |
| "Price averaging or trending" | NO averaging or statistical analysis | ✅ COMPLIANT |
| "Suggest or model prices" | Does NOT suggest prices to sellers or buyers | ✅ COMPLIANT |
| "Category-wide analysis" | No category-level data collection | ✅ COMPLIANT |

**Functional equivalence to eBay features:**
This feature is functionally identical to eBay's own **Watchlist price drop alerts**:
- eBay Watchlist: "We'll email you when the price drops" on watched items
- FoxFinder: Notifies when a previously-seen item's price drops into range

**Conclusion:** Price drop notifications are a standard e-commerce feature (Amazon, eBay, and others offer this). FoxFinder's implementation tracks individual items only, performs no aggregation or analysis, and does not model or suggest prices.

### Data Handling Requirements (Section 8)

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ✅ **Data freshness ≤6 hours for listings** | PASS | Data fetched fresh each cycle, never cached for display |
| ✅ **Data retention policy** | PASS | `SEEN_MAX_AGE_DAYS = 14` (line 120) |
| ✅ **10-day termination cleanup** | PASS | Documented in PRIVACY_POLICY.md |
| ✅ **Atomic file writes** | PASS | Uses temp file + rename pattern (`shared_utils.py`) |
| ✅ **HTTPS/TLS for all API calls** | PASS | All requests use `https://api.ebay.com` |

### Prohibited Uses Compliance (Section 9)

| Prohibition | Status | Verification |
|-------------|--------|--------------|
| ✅ **No market research** | COMPLIANT | App does not calculate averages or aggregate data |
| ✅ **No site-wide statistics** | COMPLIANT | Only processes user's configured searches |
| ✅ **No AI/ML training** | COMPLIANT | Explicitly prohibited in PRIVACY_POLICY.md |
| ✅ **No competitive use** | COMPLIANT | Personal deal notification only |
| ✅ **No automated reselling** | COMPLIANT | Does not auto-order or cross-platform list |
| ✅ **No User ID collection** | COMPLIANT | Does not store buyer/seller identities |

### EPN (eBay Partner Network) Requirements

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ✅ **X-EBAY-C-ENDUSERCTX header** | PASS | Includes `affiliateCampaignId` AND `contextualLocation` |
| ✅ **contextualLocation for shipping** | PASS | `contextualLocation=country=US` for delivery estimates |
| ✅ **10-digit campaign ID support** | PASS | Config template includes `epn_campaign_id` field |
| ✅ **Affiliate link generation** | PASS | Returns `itemAffiliateWebUrl` when EPN configured |

### Privacy & Documentation Requirements

| Requirement | Status | File |
|-------------|--------|------|
| ✅ **Privacy Policy** | PASS | `PRIVACY_POLICY.md` |
| ✅ **Consistent with eBay Privacy Notice** | PASS | Explicitly stated in privacy policy |
| ✅ **User data deletion instructions** | PASS | `PRIVACY_POLICY.md` "How to Delete Your Data" |
| ✅ **Third-party service disclosure** | PASS | eBay API, EPN, and email provider disclosed |
| ✅ **GDPR compliance** | PASS | Data minimization, retention limits, user rights |
| ✅ **eBay trademark disclaimer** | PASS | Footer in `PRIVACY_POLICY.md` and `README.md` |

### Branding Requirements

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ✅ **eBay attribution in emails** | PASS | `email_templates.py` includes eBay branding footer |
| ✅ **Links to eBay User Agreement** | PASS | Included in email footer |
| ✅ **Clear "powered by eBay" attribution** | PASS | Email footer states "Powered by eBay Browse API" |

### OWASP Top 10 Security Compliance (2021)

eBay requires applications to follow OWASP secure coding principles. FoxFinder compliance:

| OWASP Category | Status | Implementation |
|----------------|--------|----------------|
| **A01:2021 - Broken Access Control** | N/A | Personal use app, no multi-user access control |
| **A02:2021 - Cryptographic Failures** | ✅ PASS | TLS-only API connections, OAuth2 tokens |
| **A03:2021 - Injection** | ✅ PASS | No SQL, parameterized API calls, no user input in queries |
| **A04:2021 - Insecure Design** | ✅ PASS | Minimal attack surface, no exposed ports/services |
| **A05:2021 - Security Misconfiguration** | ✅ PASS | Config validation, no default credentials |
| **A06:2021 - Vulnerable Components** | ✅ PASS | Minimal dependencies (requests only), standard library |
| **A07:2021 - Auth Failures** | ✅ PASS | OAuth2 tokens only, no password storage |
| **A08:2021 - Data Integrity Failures** | ✅ PASS | HTTPS-only API calls, atomic file writes |
| **A09:2021 - Logging Failures** | ✅ PASS | Comprehensive logging without sensitive data |
| **A10:2021 - SSRF** | ✅ PASS | Only contacts `api.ebay.com` (hardcoded) |

**Security Design Principles:**
- No external network listeners (client-only)
- Credentials stored in local config file (user-controlled)
- No credential transmission except to eBay API
- Atomic file operations prevent data corruption

### eBay Ecosystem Integration (Value-Add Features)

| Feature | Status | Implementation |
|---------|--------|----------------|
| ✅ **Watchlist deep links** | IMPLEMENTED | Each item includes [WATCH] link to add to eBay Watchlist |
| ✅ **"Explore More on eBay" section** | IMPLEMENTED | Links to Today's Deals, Trending, Electronics, Global Deals |
| ✅ **eBay Mobile App promotion** | IMPLEMENTED | iOS and Android app store links in every email |
| ✅ **EPN affiliate tracking** | IMPLEMENTED | All item links use `itemAffiliateWebUrl` when configured |

**Business Value to eBay:**
- Drives additional traffic beyond individual item notifications
- Encourages Watchlist usage (increases platform engagement)
- Promotes eBay mobile app adoption
- EPN tracking ensures revenue sharing on conversions

---

## Application Growth Check Form Preparation

### Estimated API Usage (Required in Application)

```
Daily Volume: ~1500-3000 calls
  - OAuth token refresh: ~20 calls/day
  - Browse API searches: ~1400-2900 calls/day
  - Rate limit checks: ~50 calls/day

Hourly Peak: ~200-300 calls
  - During high-activity hours (searches every 2-5 minutes)

APIs Used:
  - OAuth Token API (identity.api.ebay.com)
  - Browse API - item_summary/search endpoint
```

### Business Model Description (Required in Application)

```
FoxFinder is a personal deal notification tool that:
1. Searches eBay listings matching user-configured search criteria
2. Sends email notifications when new items are found
3. Tracks price drops on previously seen items
4. Uses EPN affiliate tracking for all generated links

Value Proposition:
- Helps users find deals faster than manual searching
- Reduces time spent manually checking eBay
- Provides price drop notifications for wishlist items

Revenue Model (via EPN):
- Affiliate commissions from purchases made through notification links
```

---

## Files Included for Review

| File | Purpose |
|------|---------|
| `foxfinder.py` | Main application (API calls, rate limiting) |
| `ebay_common.py` | Shared utilities (heartbeat, logging) |
| `email_templates.py` | Notification templates with eBay branding |
| `PRIVACY_POLICY.md` | Required privacy documentation |
| `README.md` | User documentation |
| `ebay_config_template.json` | Configuration template (no secrets) |
| `requirements.txt` | Dependencies |

---

## Verification Commands

```bash
# Verify max_retries=2 in code
grep -n "max_retries" foxfinder.py

# Verify data retention setting
grep -n "SEEN_MAX_AGE_DAYS" foxfinder.py

# Verify EPN header support with contextualLocation
grep -n "X-EBAY-C-ENDUSERCTX\|contextualLocation\|affiliateCampaignId" foxfinder.py

# Verify itemEndDate check (data freshness)
grep -n "itemEndDate" foxfinder.py

# Verify estimatedAvailabilityStatus check
grep -n "estimatedAvailabilityStatus" foxfinder.py

# Verify eBay branding in emails
grep -n "EBAY_ATTRIBUTION\|Powered by" email_templates.py

# Verify condition display compliance
grep -n "CONDITION UNKNOWN" email_templates.py

# Verify Python syntax
python -m py_compile foxfinder.py ebay_common.py email_templates.py
```

---

## Contact for Growth Check Review

When submitting Application Growth Check:
- **Subject Line:** "Buy API Production Access (YOUR_EBAY_USER_ID)"
- **Include:** EPN user ID, sandbox testing instructions, this compliance checklist

---

## Automated Compliance Audit Results

The following patterns were programmatically scanned for in the complete codebase. All checks passed:

### Section 8 - Data Handling Patterns
| Pattern Scanned | Result |
|-----------------|--------|
| Market research data aggregation (average, aggregate, GMV) | ✅ NONE FOUND |
| Bulk data export/download functionality | ✅ NONE FOUND |
| User ID collection (seller ID, buyer ID) | ✅ NONE FOUND |
| Price history/modeling storage | ✅ NONE FOUND |
| Data caching beyond freshness requirements | ✅ NONE FOUND |

### Section 9 - Prohibited Use Patterns
| Pattern Scanned | Result |
|-----------------|--------|
| Automated data extraction terms | ✅ NONE FOUND |
| Browser automation libraries | ✅ NONE FOUND |
| AI/ML training references | ✅ NONE FOUND |
| Price manipulation automation | ✅ NONE FOUND |
| Competitive use language | ✅ NONE FOUND |
| Account manipulation patterns | ✅ NONE FOUND |
| Policy evasion patterns | ✅ NONE FOUND |
| Unsolicited bulk communication | ✅ NONE FOUND |
| Content embedding/mirroring | ✅ NONE FOUND |

### Code Quality Audit
| Check | Result |
|-------|--------|
| Python syntax validation | ✅ ALL FILES PASS |
| Hardcoded credentials | ✅ NONE FOUND |
| TODO/FIXME markers | ✅ NONE FOUND |
| Consistent branding (FoxFinder) | ✅ VERIFIED |
| eBay attribution in emails | ✅ VERIFIED |
| max_retries=2 enforcement | ✅ VERIFIED |
| SEEN_MAX_AGE_DAYS=14 | ✅ VERIFIED |
| contextualLocation header | ✅ VERIFIED |
| itemEndDate expiration check | ✅ VERIFIED |
| estimatedAvailabilityStatus check | ✅ VERIFIED |
| Condition badge (UNKNOWN text) | ✅ VERIFIED |

---

*This checklist documents FoxFinder's compliance with eBay API License Agreement requirements as of January 26, 2026. Audit performed using automated pattern scanning and manual code review.*
