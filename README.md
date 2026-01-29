# FoxFinder

**Personal eBay Deal Notification Service using the Official Browse API**

FoxFinder is a personal deal notification application that uses the **official eBay Browse API** to search for items matching your criteria and send email notifications when new deals appear. Built with eBay API compliance in mind.

> **Compliance Note:** FoxFinder is designed from the ground up to comply with the eBay API License Agreement, eBay Developer Program policies, and eBay Partner Network Terms. See [COMPLIANCE_CHECKLIST.md](COMPLIANCE_CHECKLIST.md) for full details.

## Features

- **Deal Notifications** - Email notifications when items matching your criteria appear
- **Price Drop Notifications** - Notifies when previously seen items drop into your price range
- **Professional Emails** - HTML emails with proper eBay branding and attribution
- **Watchlist Integration** - One-click "Add to Watchlist" links for every item
- **eBay Ecosystem Links** - "Explore More on eBay" section with Today's Deals, Trending, and more
- **Mobile App Promotion** - Links to eBay iOS and Android apps in every email
- **Smart Rate Limiting** - API-synced quota management, never exceeds daily limits
- **Auto-Recovery** - Graceful error handling, automatic retry with backoff (max 2 retries per eBay policy)
- **EPN Integration** - Full eBay Partner Network affiliate tracking support
- **Status Dashboard** - Real-time API usage display

## Requirements

- Python 3.9+
- eBay Developer Account ([developer.ebay.com](https://developer.ebay.com))
- eBay Partner Network Account (recommended for production access)
- Gmail/SMTP account for notifications

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/sixkiller600/FOXFINDER.git
cd FOXFINDER
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Copy the template and add your credentials:

```bash
cp ebay_config_template.json ebay_config.json
```

Edit `ebay_config.json`:

```json
{
    "api_credentials": {
        "app_id": "YOUR_EBAY_APP_ID",
        "client_secret": "YOUR_CLIENT_SECRET",
        "epn_campaign_id": "YOUR_EPN_CAMPAIGN_ID"
    },
    "email": {
        "sender": "your.email@gmail.com",
        "password": "your-app-password",
        "recipient": "notify@example.com"
    },
    "searches": [
        {
            "name": "Example Search",
            "query": "iPhone 15 Pro",
            "min_price": 500,
            "max_price": 800
        }
    ]
}
```

### 4. Run

```bash
python foxfinder.py
```

Or use the provided control scripts:
- **FoxFinder ON.bat** - Start the notification service
- **FoxFinder OFF.bat** - Stop gracefully (completes current cycle)
- **Status Dashboard.bat** - View service status and API usage

## Configuration

### API Credentials

1. Go to [developer.ebay.com](https://developer.ebay.com)
2. Create an application in the Developer Portal
3. Copy your **App ID** (Client ID) and **Client Secret**
4. Join [eBay Partner Network](https://partnernetwork.ebay.com) for production access and affiliate revenue

### EPN (eBay Partner Network) Setup

1. Register at [partnernetwork.ebay.com](https://partnernetwork.ebay.com)
2. Create a campaign and copy your 10-digit Campaign ID
3. Add `epn_campaign_id` to your config file
4. All generated links will include affiliate tracking

### Email Setup (Gmail)

1. Enable 2-Factor Authentication on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Use the 16-character app password (not your regular password)

### Search Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | string | required | Display name for the search |
| `query` | string | required | eBay search query |
| `min_price` | number | 0 | Minimum price filter |
| `max_price` | number | 999999 | Maximum price filter |
| `condition` | string | any | `new`, `used`, `refurbished`, `any` |
| `include_auctions` | boolean | **false** | Include auction items (default: Buy It Now only) |
| `free_shipping_only` | boolean | false | Only free shipping items |
| `exclude_words` | array | [] | Words to exclude from results |
| `required_words` | array | [] | Words that must appear in title |
| `enabled` | boolean | true | Enable/disable this search |

> **Note:** Per eBay Growth Check requirements, FoxFinder defaults to **Buy It Now (FIXED_PRICE) items only**. Set `"include_auctions": true` to also see auction listings.

## eBay API Compliance

FoxFinder is designed to comply with eBay Developer Program requirements:

| Requirement | Status |
|-------------|--------|
| Uses Browse API (not deprecated Finding API) | Yes |
| Max 2 retries for infrastructure errors | Yes |
| Graceful error handling | Yes |
| Data retention ≤14 days | Yes |
| Data freshness compliance (≤6 hours) | Yes |
| EPN affiliate tracking support | Yes |
| eBay attribution in notifications | Yes |
| Privacy policy included | Yes |
| No market research/AI training | Yes |

**Full compliance details:** [COMPLIANCE_CHECKLIST.md](COMPLIANCE_CHECKLIST.md)

**Privacy policy:** [PRIVACY_POLICY.md](PRIVACY_POLICY.md)

## Project Structure

```
foxfinder/
├── foxfinder.py              # Main application script
├── ebay_common.py            # Shared utilities (heartbeat, logging)
├── email_templates.py        # HTML email templates with eBay branding
├── shared_utils.py           # General utilities (atomic writes)
├── check_rate_limit.py       # Rate limit checker utility
├── test_qa.py                # Comprehensive QA test suite
├── ebay_config.json          # Your configuration (gitignored)
├── ebay_config_template.json # Configuration template
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── CHANGELOG.md              # Version history and release notes
├── PRIVACY_POLICY.md         # Privacy policy
├── COMPLIANCE_CHECKLIST.md   # eBay API compliance documentation
├── LICENSE                   # MIT License
├── FoxFinder ON.bat          # Start notification service (batch wrapper)
├── FoxFinder ON.ps1          # Start notification service (PowerShell)
├── FoxFinder OFF.bat         # Stop notification service (batch wrapper)
├── FoxFinder OFF.ps1         # Stop notification service (PowerShell)
├── Status Dashboard.bat      # View status and API usage (batch wrapper)
└── Status Dashboard.ps1      # View status and API usage (PowerShell)
```


## Testing

FoxFinder includes a comprehensive QA test suite that covers all modules:

```bash
python test_qa.py
```

This validates:
- All module imports and syntax
- `shared_utils` functions (disk space, heartbeat, JSON I/O, log rotation, shutdown)
- `ebay_common` functions (DST calculations, rate limiting, config, SMTP auto-detect)
- `email_templates` functions (HTML generation, XSS prevention, condition badges, watchlist links)
- `foxfinder` functions (config validation, title matching, EPN validation, seen cleanup)
- Config template structure and validity
- Repository file structure completeness
- Version consistency across modules and CHANGELOG
- README accuracy (all referenced files exist, links valid)
- Compliance and privacy document completeness
- Edge cases (Unicode, long titles, large datasets)

## Troubleshooting

### "Token refresh failed"
- Verify your App ID and Client Secret are correct
- Check that your eBay developer account is active
- Ensure you're using production credentials (not sandbox)

### "No internet connectivity"
- FoxFinder will automatically retry when connection is restored
- Check your firewall settings for api.ebay.com access

### "Rate limit exceeded"
- Wait for daily reset (midnight Pacific Time)
- Reduce number of searches or increase check interval

### Emails not sending
- Verify Gmail App Password is correct (16 characters, no spaces)
- Check that sender email matches the App Password account
- Ensure "Less secure apps" is not the issue (use App Passwords instead)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## License

MIT License - See [LICENSE](LICENSE)

## Acknowledgments

- eBay Developer Program for the Browse API
- eBay Partner Network for affiliate integration

## Disclaimer

FoxFinder is an independent personal tool and is not affiliated with, endorsed by, or sponsored by eBay Inc. "eBay" is a registered trademark of eBay Inc. All eBay data is provided via the official eBay Browse API in compliance with eBay's terms of service.

---

**Questions?** Open an issue or check the [eBay Developer Forums](https://community.ebay.com/t5/Developer-Forums/ct-p/developergroup).
