"""
Test request deduplication mechanism
Verify that concurrent requests do not result in duplicate API calls
"""
import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.foreign_stock_service import ForeignStockService


@pytest.mark.asyncio
async def test_concurrent_hk_quote_requests():
    """
    Test the deduplication mechanism for concurrent Hong Kong stock quotation requests
    
    Scenario:
    1. Initiate 10 requests for the same stock at the same time
    2. Verify there is only 1 actual API call
    3. All requests should return the same results
    """
    # Create service instance
    service = ForeignStockService(db=None)
    
    # Mock Data source priority
    async def mock_get_source_priority(market):
        return ['akshare']
    
    service._get_source_priority = mock_get_source_priority
    
    # Mock AKShare API Call (record the number of calls)
    call_count = 0
    
    def mock_get_hk_quote_from_akshare(code):
        nonlocal call_count
        call_count += 1
        # Simulate API latency
        import time
        time.sleep(0.1)
        return {
            'code': code,
            'name': 'Tencent Holdings',
            'price': 350.0,
            'open': 348.0,
            'high': 352.0,
            'low': 347.0,
            'volume': 1000000,
            'change_percent': 0.5,
            'trade_date': '2025-11-12',
            'currency': 'HKD'
        }
    
    service._get_hk_quote_from_akshare = mock_get_hk_quote_from_akshare

    # Make 10 requests simultaneously (using force_refresh=True Bypass caching)
    code = '00700'
    tasks = [service._get_hk_quote(code, force_refresh=True) for _ in range(10)]
    
    # Wait for all requests to complete
    results = await asyncio.gather(*tasks)
    
    # Verification results
    assert len(results) == 10, "should return 10 results"
    assert call_count == 1, f"The API should only be called once, but it was actually called{call_count}times"
    
    # Verify all results are the same
    for result in results:
        assert result['code'] == code
        assert result['price'] == 350.0
    
    print(f"✅ Test passed: 10 concurrent requests only triggered{call_count}API calls")


@pytest.mark.asyncio
async def test_concurrent_us_quote_requests():
    """
    Test the deduplication mechanism for concurrent U.S. stock quotation requests
    """
    service = ForeignStockService(db=None)
    
    # Mock Data source priority
    async def mock_get_source_priority(market):
        return ['yahoo_finance']
    
    service._get_source_priority = mock_get_source_priority
    
    # Mock yfinance API call
    call_count = 0
    
    def mock_get_us_quote_from_yfinance(code):
        nonlocal call_count
        call_count += 1
        import time
        time.sleep(0.1)
        return {
            'code': code,
            'name': 'Apple Inc.',
            'price': 180.0,
            'open': 179.0,
            'high': 181.0,
            'low': 178.5,
            'volume': 50000000,
            'change_percent': 0.56,
            'trade_date': '2025-11-12',
            'currency': 'USD'
        }
    
    service._get_us_quote_from_yfinance = mock_get_us_quote_from_yfinance

    # Make 10 requests simultaneously (using force_refresh=True Bypass caching)
    code = 'AAPL'
    tasks = [service._get_us_quote(code, force_refresh=True) for _ in range(10)]
    
    # Wait for all requests to complete
    results = await asyncio.gather(*tasks)
    
    # Verification results
    assert len(results) == 10
    assert call_count == 1, f"The API should only be called once, but it was actually called{call_count}times"
    
    for result in results:
        assert result['code'] == code
        assert result['price'] == 180.0
    
    print(f"✅ Test passed: 10 concurrent requests only triggered{call_count}API calls")


@pytest.mark.asyncio
async def test_different_stocks_no_blocking():
    """
    Testing requests for different stocks will not block each other
    """
    service = ForeignStockService(db=None)

    # Mock Data source priority
    async def mock_get_source_priority(market):
        return ['akshare']

    service._get_source_priority = mock_get_source_priority

    # Mock API call
    call_count = {}

    def mock_get_hk_quote_from_akshare(code):
        if code not in call_count:
            call_count[code] = 0
        call_count[code] += 1

        import time
        time.sleep(0.1)

        return {
            'code': code,
            'name': f'stocks{code}',
            'price': 100.0,
            'open': 99.0,
            'high': 101.0,
            'low': 98.0,
            'volume': 1000000,
            'change_percent': 1.0,
            'trade_date': '2025-11-12',
            'currency': 'HKD'
        }

    service._get_hk_quote_from_akshare = mock_get_hk_quote_from_akshare

    # Request 3 different stocks simultaneously, 5 concurrent requests per stock (using force_refresh=True Bypass caching)
    # Use a different ticker to avoid conflicts with previous tests
    codes = ['00001', '00002', '00003']
    tasks = []
    for code in codes:
        tasks.extend([service._get_hk_quote(code, force_refresh=True) for _ in range(5)])

    # Wait for all requests to complete
    results = await asyncio.gather(*tasks)

    # Verification results
    assert len(results) == 15  # 3 stocks × 5 requests

    # should only be called 1 time per stock API
    for code in codes:
        assert call_count.get(code, 0) == 1, f"stocks{code}The API should only be called once, but it was actually called{call_count.get(code, 0)}times"

    print(f"✅ The test passed: 5 concurrent requests for each of 3 different stocks, and each stock only triggered 1 API call.")


if __name__ == '__main__':
    # Run tests
    asyncio.run(test_concurrent_hk_quote_requests())
    asyncio.run(test_concurrent_us_quote_requests())
    asyncio.run(test_different_stocks_no_blocking())

