#!/usr/bin/env python3
"""Quick check of eBay's actual rate limit status."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ebay_common import load_config, get_pacific_date
from foxfinder import get_oauth_token, fetch_rate_limits_from_api

def main():
    print("=" * 50)
    print("eBay Rate Limit Check")
    print("=" * 50)

    config = load_config()
    if not config:
        print("ERROR: Could not load config")
        return

    print(f"\nPacific date: {get_pacific_date()}")

    api_creds = config.get("api_credentials", {})
    app_id = api_creds.get("app_id")
    client_secret = api_creds.get("client_secret")
    if not app_id or not client_secret:
        print("ERROR: Missing app_id or client_secret in config")
        return

    print("\nGetting fresh token...")
    token = get_oauth_token(app_id, client_secret)
    if not token:
        print("ERROR: Could not get token")
        return

    print("Querying eBay API for current rate limits...")
    result = fetch_rate_limits_from_api(token)

    print(f"\nResult: {result}")

    if result.get("success"):
        print(f"\n--- eBay Reports ---")
        print(f"Limit:     {result.get('limit', 'N/A')}")
        print(f"Remaining: {result.get('remaining', 'N/A')}")
        print(f"Used:      {result.get('limit', 0) - result.get('remaining', 0)}")
        print(f"Reset at:  {result.get('reset', 'N/A')}")
    else:
        print(f"\nAPI Error: {result.get('error')}")

if __name__ == "__main__":
    main()
