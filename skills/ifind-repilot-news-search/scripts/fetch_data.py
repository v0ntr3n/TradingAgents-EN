#!/usr/bin/env python3
"""
Financial information natural language script
Query all market financial information fragments through natural language

Usage:
    python fetch_data.py "Federal Reserve Interest Rate Policy"
"""

import sys
import json
from datetime import datetime
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_BASE_URL = "https://repilot.51ifind.com/"
SKILL_CODE = "news_query"
CONFIG_DIR = Path.home() / ".config" / "ifind-repilot"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config():
    """Read configuration file"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Configuration file {CONFIG_FILE} The format is invalid, please check whether the JSON format is correct", file=sys.stderr)
        return {}


def get_base_url():
    """get base URL"""
    config = get_config()
    return config.get("base_url", DEFAULT_BASE_URL).rstrip("/")


def validate_date_format(date_str: str) -> bool:
    """Verify that the date format is YYYY-MM-DDTHH:MM:SS and the value is valid"""
    try:
        datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        return True
    except ValueError:
        return False


def get_token():
    """Get certified token"""
    config = get_config()
    token = config.get("auth_token")
    if not token:
        raise ValueError(f"Please configure auth_token first, refer to {CONFIG_FILE}")
    return token


def fetch_data(query: str, start_date: str = None, end_date: str = None) -> dict:
    """
    Query financial information data

    Args:
        query: query sentence
        start_date: Start date in the format YYYY-MM-DDTHH:MM:SS (For example 2025-01-01T00:00:00)
        end_date: End date in the format YYYY-MM-DDTHH:MM:SS (For example 2026-01-01T00:00:00)

    Returns:
        API Returned JSON data

    Raises:
        ValueError: Invalid parameters or authentication failure
        RuntimeError: API call failed
    """
    if not query or not query.strip():
        raise ValueError("query Parameter cannot be empty")

    if start_date and not validate_date_format(start_date):
        raise ValueError(f"start_date Invalid format, should be YYYY-MM-DDTHH:MM:SS, For example 2025-01-01T00:00:00")

    if end_date and not validate_date_format(end_date):
        raise ValueError(f"end_date Invalid format, should be YYYY-MM-DDTHH:MM:SS, For example 2026-01-01T00:00:00")

    token = get_token()
    base_url = get_base_url()

    params = {"query": query, "skillCode": SKILL_CODE}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    query_string = urllib.parse.urlencode(params)
    url = f"{base_url}/research_pilot_service/openapi/skills/open/search/news?{query_string}"

    request = urllib.request.Request(url)
    request.add_header("Authorization", token)
    request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API HTTP Error: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Response JSON parsing failed: {e}")

    if result.get("status_code") != 0:
        error_msg = result.get("status_msg", "unknown error")
        raise RuntimeError(f"API Return failure: {error_msg}")

    return result


def check_token():
    """Check token configuration status"""
    config = get_config()

    print("Token Check:")
    print("-" * 40)

    if config.get("auth_token"):
        print("√ auth_token configured")
        return True
    else:
        print("× auth_token Not configured")
        print(f"\n Please run: python fetch_data.py --set-token <your_token>")
        print(f"or create manually {CONFIG_FILE}:")
        print(f'  mkdir -p {CONFIG_DIR}')
        print(f'  echo \'{{"auth_token": "your_token_here"}}\' > {CONFIG_FILE}')
        return False


def set_config(key: str, value: str):
    """Set configuration items"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config = get_config()
    config[key] = value

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"saved to {CONFIG_FILE}")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_data.py <query sentence>", file=sys.stderr)
        print("      python fetch_data.py --check-token", file=sys.stderr)
        print("      python fetch_data.py --set-token <token>", file=sys.stderr)
        print("      python fetch_data.py --set-url <url>", file=sys.stderr)
        print("      python fetch_data.py --start-date <date> --end-date <date> <query sentence>", file=sys.stderr)
        print("      python fetch_data.py <query sentence> --start-date <date> --end-date <date>", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--check-token":
        check_token()
        sys.exit(0)

    if sys.argv[1] == "--set-token":
        if len(sys.argv) < 3:
            print("Error: Please provide token value", file=sys.stderr)
            print("Usage: python fetch_data.py --set-token <token>", file=sys.stderr)
            sys.exit(1)
        set_config("auth_token", sys.argv[2])
        sys.exit(0)

    if sys.argv[1] == "--set-url":
        if len(sys.argv) < 3:
            print("Error: Please provide url value", file=sys.stderr)
            print("Usage: python fetch_data.py --set-url <url>", file=sys.stderr)
            sys.exit(1)
        set_config("base_url", sys.argv[2])
        sys.exit(0)

    # Parse date parameters and query statements
    start_date = None
    end_date = None
    query_parts = []

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--start-date":
            if i + 1 >= len(sys.argv):
                print("Error: --start-date requires a date value", file=sys.stderr)
                sys.exit(1)
            start_date = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--end-date":
            if i + 1 >= len(sys.argv):
                print("Error: --end-date requires a date value", file=sys.stderr)
                sys.exit(1)
            end_date = sys.argv[i + 1]
            i += 2
        else:
            query_parts.append(sys.argv[i])
            i += 1

    query = " ".join(query_parts)

    if not query:
        print("Error: Query query cannot be empty", file=sys.stderr)
        sys.exit(1)

    try:
        result = fetch_data(query, start_date, end_date)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()