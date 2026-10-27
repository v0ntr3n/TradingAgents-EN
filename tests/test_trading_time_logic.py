#!/usr/bin/env python3
"""
Test the trading time judgment logic (including the 30-minute buffer period after closing)

This test does not require a database connection, only the core logic is tested
"""

import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.quotes_ingestion_service import QuotesIngestionService
from app.core.config import settings


def test_trading_time_logic():
    """Test transaction time judgment logic"""
    print("\n" + "=" * 80)
    print("test: Trading time judgment logic (including 30-minute buffer period after closing)")
    print("=" * 80)
    
    service = QuotesIngestionService()
    tz = ZoneInfo(settings.TIMEZONE)
    
    # test case
    test_cases = [
        ("09:00", False, "before opening"),
        ("09:29", False, "1 minute before opening"),
        ("09:30", True, "Open in the morning"),
        ("10:00", True, "Trading in the morning"),
        ("11:30", True, "Morning close"),
        ("11:31", False, "Lunch break begins"),
        ("12:00", False, "lunch break"),
        ("12:59", False, "before lunch break ends"),
        ("13:00", True, "Open in the afternoon"),
        ("14:00", True, "Trading in the afternoon"),
        ("14:55", True, "5 minutes before closing"),
        ("15:00", True, "Closing time (beginning of buffer period)✨"),
        ("15:06", True, "6 minutes after market close (1st synchronization opportunity)✨"),
        ("15:12", True, "12 minutes after market close (2nd synchronization opportunity)✨"),
        ("15:18", True, "18 minutes after the close (3rd synchronization opportunity)✨"),
        ("15:24", True, "24 minutes after market close (4th synchronization opportunity)✨"),
        ("15:30", True, "30 minutes after the market closes (end of buffer period)✨"),
        ("15:31", False, "31 minutes after the market closes (outside the buffer period)"),
        ("16:00", False, "1 hour after market close"),
    ]
    
    print("\n Test results:")
    print("-" * 80)
    print(f"{'time':^8} | {'expected':^6} | {'actual':^6} | {'Status':^8} | {'Description'}")
    print("-" * 80)
    
    all_passed = True
    buffer_period_tests = []
    
    for time_str, expected, description in test_cases:
        # Create test time (using today's date + specified time)
        now = datetime.now(tz)
        hour, minute = map(int, time_str.split(":"))
        test_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Make sure it is a working day (Monday to Friday)
        if test_time.weekday() >= 5:
            # If it is a weekend, adjust to Monday
            days_to_monday = 7 - test_time.weekday()
            test_time = test_time.replace(day=test_time.day + days_to_monday)
        
        result = service._is_trading_time(test_time)
        status = "✅ Pass" if result == expected else "❌ failed"
        
        if result != expected:
            all_passed = False
        
        # Mark buffer period test
        if "✨" in description:
            buffer_period_tests.append((time_str, result, expected))
        
        print(f"{time_str:^8} | {str(expected):^6} | {str(result):^6} | {status:^8} | {description}")
    
    print("-" * 80)
    
    # Summary
    if all_passed:
        print("\n✅ All test cases pass!")
    else:
        print("\n❌ Some test cases failed")
    
    # Buffer period test summary
    print("\n" + "=" * 80)
    print("Summary of post-closing buffer period testing")
    print("=" * 80)
    print(f"\n Configured sync interval: {settings.QUOTES_INGEST_INTERVAL_SECONDS} seconds ({settings.QUOTES_INGEST_INTERVAL_SECONDS / 60} minutes)")
    print(f"Buffer period length: 30 minutes (15:00-15:30)")
    print(f"Theoretical synchronization times: {30 * 60 // settings.QUOTES_INGEST_INTERVAL_SECONDS} times")
    
    print("\n Synchronization opportunities during the buffer period:")
    for i, (time_str, result, expected) in enumerate(buffer_period_tests, 1):
        status = "✅" if result == expected else "❌"
        print(f"  {status} No.{i}opportunity: {time_str} - {'Can be synchronized' if result else 'Can t sync'}")
    
    print("\n💡 Description:")
    print("  - The closing time is 15:00")
    print("  - The buffer period is extended to 15:30, add 30 minutes")
    print(f"  - Assume that the synchronization interval is {settings.QUOTES_INGEST_INTERVAL_SECONDS / 60} minutes")
    print(f"  - Can be carried out during the buffer period {30 * 60 // settings.QUOTES_INGEST_INTERVAL_SECONDS} sub-sync")
    print("  - Greatly reduces the risk of missing the closing price!")
    
    return all_passed


if __name__ == "__main__":
    success = test_trading_time_logic()
    sys.exit(0 if success else 1)

