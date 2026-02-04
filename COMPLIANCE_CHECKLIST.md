# FoxFinder - eBay API Compliance Checklist

**Application:** FoxFinder eBay Deal Notification Service
**Version:** 1.4.0 (v4.10.0 code)
**API Used:** eBay Browse API (Buy APIs)
**Last Verified:** February 4, 2026

---

## Operation Modes

FoxFinder supports two operation modes with different compliance requirements:

| Mode | Description | API Credentials | Israeli Compliance |
|------|-------------|-----------------|-------------------|
| **Personal Use** | Operator's own deal hunting | Operator's own | Exempt (self-notification) |
| **Service Model** | Notification service for clients | Operator's (shared) | Full compliance |

### Service Model Details

- **API Credentials:** Operator holds eBay API credentials; clients do not need their own
- **Subscription Method:** Manual one-on-one registration (personal contact with operator)
- **Consent Tracking:** Operator maintains documented consent records for all subscribers
- **Affiliate Revenue:** Operator earns EPN commissions on client purchases

---

## Technical Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| Uses Browse API (not deprecated Finding API) | PASS | Uses `buy/browse/v1/item_summary/search` |
| Max 2 retries for infrastructure errors | PASS | Both `get_oauth_token()` and `search_ebay()` use `max_retries=2` |
| Graceful error handling | PASS | All API calls wrapped in try/except |
| Uses latest API version | PASS | Browse API v1 |
| HTTP 429/503 handling | PASS | Exponential backoff implemented |
| FIXED_PRICE default | PASS | Buy It Now items by default per eBay requirement |
| EPN Campaign ID validation | PASS | Validates 10-digit format |
| Condition display | PASS | Shows badge, indicates when unknown |
| contextualLocation header | PASS | Included for shipping accuracy |
| itemEndDate check | PASS | Skips expired listings |
| estimatedAvailabilityStatus | PASS | Skips unavailable items |

### API Versions

| API | Version | Endpoint |
|-----|---------|----------|
| Browse API | v1 | `buy/browse/v1/item_summary/search` |
| OAuth | v1 | `identity/v1/oauth2/token` |
| Analytics | v1_beta | `developer/analytics/v1_beta/rate_limit` |

### newlyListed Sorting

FoxFinder uses `sort=newlyListed` because the app's purpose is to alert users to newly listed deals. Without this sort order, the application cannot fulfill its core function. This is documented in `search_ebay()` and disclosed in the Growth Check application.

---

## Data Handling (Section 8)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Data freshness ≤6 hours | PASS | Fetched fresh each cycle |
| Data retention ≤14 days | PASS | `SEEN_MAX_AGE_DAYS = 14` |
| 10-day termination cleanup | PASS | Documented in PRIVACY_POLICY.md |
| Atomic file writes | PASS | Uses temp + rename pattern |
| HTTPS/TLS only | PASS | All requests to `https://api.ebay.com` |

---

## Prohibited Uses (Section 9)

| Prohibition | Status | Verification |
|-------------|--------|--------------|
| No market research | COMPLIANT | No averages or aggregation |
| No site-wide statistics | COMPLIANT | Only user's configured searches |
| No AI/ML training | COMPLIANT | Prohibited in privacy policy |
| No competitive use | COMPLIANT | Personal notification only |
| No automated reselling | COMPLIANT | No auto-ordering |
| No User ID collection | COMPLIANT | No buyer/seller IDs stored |

### Price Drop Feature Clarification

The price drop notification tracks individual items the user has already seen. This is:
- NOT market research (no aggregation)
- NOT price modeling (no suggestions)
- Functionally identical to eBay's own Watchlist alerts

---

## EPN Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| X-EBAY-C-ENDUSERCTX header | PASS | Includes affiliateCampaignId and contextualLocation |
| 10-digit campaign ID | PASS | Validated in config |
| Affiliate link usage | PASS | Uses `itemAffiliateWebUrl` |

---

## Privacy & Branding

| Requirement | Status |
|-------------|--------|
| Privacy Policy | Included (PRIVACY_POLICY.md) |
| eBay Privacy Notice consistency | Stated in policy |
| Data deletion instructions | Included |
| eBay attribution in emails | "Powered by eBay Browse API" footer |
| eBay User Agreement link | Included in emails |
| eBay trademark disclaimer | Included |

---

## OWASP Security

| Category | Status |
|----------|--------|
| A01 - Broken Access Control | N/A (personal app) |
| A02 - Cryptographic Failures | PASS - TLS only |
| A03 - Injection | PASS - No SQL, parameterized calls |
| A04 - Insecure Design | PASS - No exposed ports |
| A05 - Security Misconfiguration | PASS - Config validation |
| A06 - Vulnerable Components | PASS - Minimal deps |
| A07 - Auth Failures | PASS - OAuth2 only |
| A08 - Data Integrity | PASS - HTTPS, atomic writes |
| A09 - Logging Failures | PASS - No sensitive data logged |
| A10 - SSRF | PASS - Only contacts api.ebay.com |

---

## eBay Ecosystem Features

- Watchlist deep links in every notification
- "Explore More on eBay" section (Today's Deals, Trending)
- eBay Mobile App links (iOS/Android)
- EPN tracking on all item links

---

## Estimated API Usage

```
Daily: ~1500-3000 calls
  - Token refresh: ~20/day
  - Searches: ~1400-2900/day
  - Rate limit checks: ~50/day

Peak: ~200-300 calls/hour
```

---

## Israeli Anti-Spam Law (Amendment 40) Compliance

FoxFinder implements conditional compliance based on operation mode.

### Personal Use Mode (Exempt)

| Condition | Status | Notes |
|-----------|--------|-------|
| Sender == Recipient check | PASS | `is_self_notification()` function |
| Exempt email configured | PASS | `ofirlevi@tutanota.com` |
| Personal use classification | PASS | No third-party marketing |

**Legal Basis:** Israeli Anti-Spam Law targets unsolicited commercial messages to third parties. Self-configured notifications to oneself are personal use, not commercial advertising.

### Service Model Compliance (Full)

**User Subscription Process:**

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Opt-in consent method | PASS | Manual one-on-one registration |
| No automated sign-up | PASS | Personal contact required |
| Consent documentation | PASS | Operator maintains records |
| Opt-out mechanism | PASS | Contact operator to unsubscribe |
| Consent before sending | PASS | No notifications until registered |

**Subscription Process:**
1. Potential subscriber contacts operator directly (email, phone, or in-person)
2. Operator explains service including affiliate disclosure
3. Subscriber provides explicit consent to receive commercial notifications
4. Operator documents consent and adds subscriber email to configuration
5. Subscriber can opt out at any time by contacting operator

**Why All Users Opt In:**
- No passive discovery or automatic enrollment
- Every subscriber must personally contact the operator
- Explicit consent obtained before any notifications sent
- Operator maintains documented consent records

**Message Compliance (Service Model):**

When sending to client subscribers:

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Subject line: "פרסומת" prefix | PASS | Added automatically in `get_subject_line()` |
| Advertiser identification | PASS | Sender email in From header |
| Affiliate disclosure | PASS | Footer: "This email contains affiliate links..." |
| Opt-out instructions | PASS | Footer: "To stop receiving notifications..." |
| eBay attribution | PASS | "Powered by eBay Browse API" footer |
| Legal links | PASS | eBay User Agreement link |

### Penalties Awareness

| Violation Type | Maximum Penalty |
|----------------|-----------------|
| Sending without consent | 202,000 NIS (~€50,000) |
| Content/form violations | 67,300 NIS (~€16,000) |
| Statutory damages per message | 1,000 NIS (~€250) |

---

## Israeli Privacy Protection Law (PPL) Compliance

| Requirement | Status | Notes |
|-------------|--------|-------|
| Data minimization | PASS | Only item IDs, titles, prices, URLs |
| No personal data collection | PASS | No buyer/seller PII stored |
| Purpose limitation | PASS | Data used only for notifications |
| Retention limit (14 days) | PASS | `SEEN_MAX_AGE_DAYS = 14` |
| Right of access | PASS | User can view local JSON files |
| Right to deletion | PASS | Instructions in PRIVACY_POLICY.md |
| Security (HTTPS/TLS) | PASS | All API calls encrypted |
| Local storage only | PASS | No cloud transmission |
| Database registration | N/A | Personal tool, <10,000 records |

### EU Adequacy Alignment

Israel maintains EU adequacy status (reconfirmed January 2024). FoxFinder's practices align with both Israeli PPL and GDPR requirements.

---

## Files for Review

| File | Purpose |
|------|---------|
| foxfinder.py | Main application |
| ebay_common.py | Shared utilities |
| email_templates.py | Email templates with eBay branding |
| PRIVACY_POLICY.md | Privacy documentation |
| README.md | User documentation |
| ebay_config_template.json | Config template |

---

## Verification

```bash
grep -n "max_retries" foxfinder.py
grep -n "SEEN_MAX_AGE_DAYS" foxfinder.py
grep -n "contextualLocation" foxfinder.py
python -m py_compile foxfinder.py ebay_common.py email_templates.py
```

---

*Compliance verified January 29, 2026*
