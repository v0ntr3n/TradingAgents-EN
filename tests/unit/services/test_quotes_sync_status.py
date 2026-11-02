#!/usr/bin/env python3
"""
Test the real-time market synchronization status function

Verify content:
1. Trading time judgment logic (including 30-minute buffer period after closing)
2. Status recording function
3. Status acquisition function
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

# Add project root directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.quotes_ingestion_service import QuotesIngestionService
from app.core.config import settings


def test_trading_time_logic():
    """Test transaction time judgment logic"""
    print("\n" + "=" * 80)
    print("test 1: Trading time judgment logic (including 30-minute buffer period after closing)")
    print("=" * 80)
    
    service = QuotesIngestionService()
    tz = ZoneInfo(settings.TIMEZONE)
    
    # test case
    test_cases = [
        ("09:00", False, "before opening"),
        ("09:30", True, "Open in the morning"),
        ("10:00", True, "Trading in the morning"),
        ("11:30", True, "Morning close"),
        ("12:00", False, "lunch break"),
        ("13:00", True, "Open in the afternoon"),
        ("14:00", True, "Trading in the afternoon"),
        ("15:00", True, "Closing time (beginning of buffer period)"),
        ("15:06", True, "6 minutes after the market closes (within the buffer period)"),
        ("15:12", True, "12 minutes after the market closes (within the buffer period)"),
        ("15:18", True, "18 minutes after the market closes (within the buffer period)"),
        ("15:30", True, "30 minutes after the market closes (end of buffer period)"),
        ("15:31", False, "31 minutes after the market closes (outside the buffer period)"),
        ("16:00", False, "1 hour after market close"),
    ]
    
    print("\n Test results:")
    print("-" * 80)
    
    all_passed = True
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
        
        print(f"{time_str:6s} | expected: {str(expected):5s} | actual: {str(result):5s} | {status} | {description}")
    
    print("-" * 80)
    if all_passed:
        print("✅ All test cases passed")
    else:
        print("❌ Some test cases failed")
    
    return all_passed


async def test_status_record_and_get():
    """Test status logging and retrieval functionality"""
    print("\n" + "=" * 80)
    print("test 2: Status recording and retrieval functions")
    print("=" * 80)
    
    service = QuotesIngestionService()
    
    # Test record status
    print("\n📝 Test record synchronization status...")
    await service._record_sync_status(
        success=True,
        source="tushare",
        records_count=5440,
        error_msg=None
    )
    print("✅ Status recorded successfully")
    
    # test get status
    print("\n📊 Test to get synchronization status...")
    status = await service.get_sync_status()
    
    print("\n Status information obtained:")
    print("-" * 80)
    for key, value in status.items():
        print(f"{key:20s}: {value}")
    print("-" * 80)
    
    # Verification status
    checks = [
        ("last_sync_time", lambda v: v is not None, "The last sync time should exist"),
        ("interval_seconds", lambda v: v == settings.QUOTES_INGEST_INTERVAL_SECONDS, "Sync interval should be correct"),
        ("interval_minutes", lambda v: v == settings.QUOTES_INGEST_INTERVAL_SECONDS / 60, "Sync interval (minutes) should be correct"),
        ("data_source", lambda v: v == "tushare", "The data source should be tushare"),
        ("success", lambda v: v is True, "The success status should be True"),
        ("records_count", lambda v: v == 5440, "The number of records should be 5440"),
        ("error_message", lambda v: v is None, "The error message should be None"),
    ]
    
    print("\n Verification results:")
    print("-" * 80)
    
    all_passed = True
    for key, check_func, description in checks:
        value = status.get(key)
        passed = check_func(value)
        status_str = "✅ Pass" if passed else "❌ failed"
        
        if not passed:
            all_passed = False
        
        print(f"{key:20s}: {status_str} | {description}")
    
    print("-" * 80)
    if all_passed:
        print("✅ All verification passed")
    else:
        print("❌ Partial verification failed")
    
    return all_passed


async def test_error_status():
    """Test error status logging"""
    print("\n" + "=" * 80)
    print("test 3: Error status record")
    print("=" * 80)
    
    service = QuotesIngestionService()
    
    # Log error status
    print("\n📝 Test logging error status...")
    await service._record_sync_status(
        success=False,
        source="akshare_eastmoney",
        records_count=0,
        error_msg="API Current limiting"
    )
    print("✅ Error status recorded successfully")
    
    # Get status
    print("\n📊 Test to get error status...")
    status = await service.get_sync_status()
    
    print("\n Error status information obtained:")
    print("-" * 80)
    for key, value in status.items():
        print(f"{key:20s}: {value}")
    print("-" * 80)
    
    # Verify error status
    checks = [
        ("success", lambda v: v is False, "The success status should be False"),
        ("records_count", lambda v: v == 0, "The number of records should be 0"),
        ("error_message", lambda v: v == "API Current limiting", "The error message should be correct"),
    ]
    
    print("\n Verification results:")
    print("-" * 80)
    
    all_passed = True
    for key, check_func, description in checks:
        value = status.get(key)
        passed = check_func(value)
        status_str = "✅ Pass" if passed else "❌ failed"
        
        if not passed:
            all_passed = False
        
        print(f"{key:20s}: {status_str} | {description}")
    
    print("-" * 80)
    if all_passed:
        print("✅ All verification passed")
    else:
        print("❌ Partial verification failed")
    
    return all_passed


async def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("Real-time market synchronization status function test")
    print("=" * 80)
    
    results = []
    
    # Test 1: Trading time judgment logic
    results.append(("Trading time judgment logic", test_trading_time_logic()))
    
    # Test 2: Status recording and acquisition
    results.append(("Status recording and retrieval", await test_status_record_and_get()))
    
    # Test 3: Error status logging
    results.append(("Error status record", await test_error_status()))
    
    # Summary
    print("\n" + "=" * 80)
    print("Test summary")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:30s} - {status}")
    
    print(f"\n Overall: {passed}/{total} Test passed")
    
    if passed == total:
        print("\n✅ All tests passed! Real-time market synchronization status function is normal")
        return 0
    else:
        print(f"\n❌ Yes {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

