# FoxFinder - eBay API Compliance Checklist

**Application:** FoxFinder eBay Deal Notification Service
**Version:** 1.0.1
**API Used:** eBay Browse API (Buy APIs)
**Last Verified:** January 26, 2026
**Audit Level:** Exhaustive (Section 8 & 9 full compliance)

---

## Application Growth Check Requirements

### Technical Requirements

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ✅ **Uses Browse API (not deprecated Finding API)** | PASS | `foxfinder.py` line 1047 - uses `buy/browse/v1/item_summary/search` |
| ✅ **Max 2 retries for infrastructure errors** | PASS | `get_oauth_token()` line 972: `max_retries=2`, `search_ebay()` line 1047: `max_retries=2` |
| ✅ **Graceful error handling** | PASS | All API calls wrapped in try/except with proper logging |
| ✅ **Uses latest API version** | PASS | Browse API v1 (current production version) |
| ✅ **Efficient data retrieval** | PASS | Only requests necessary fields, uses pagination limits |
| ✅ **Implements caching** | PASS | `ebay_seen_api.json` deduplication cache |

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
| ✅ **X-EBAY-C-ENDUSERCTX header** | PASS | `foxfinder.py` line ~1060 - adds `affiliateCampaignId` |
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

# Verify EPN header support
grep -n "X-EBAY-C-ENDUSERCTX\|affiliateCampaignId" foxfinder.py

# Verify eBay branding in emails
grep -n "EBAY_ATTRIBUTION\|Powered by" email_templates.py

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

---

*This checklist documents FoxFinder's compliance with eBay API License Agreement requirements as of January 26, 2026. Audit performed using automated pattern scanning and manual code review.*
