#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock data API interface
Provides a convenient stock data acquisition interface and supports a complete downgrade mechanism
"""

import sys
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# Add dataflows directory to path
dataflows_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dataflows')
if dataflows_path not in sys.path:
    sys.path.append(dataflows_path)

# Import unified log system
from tradingagents.utils.logging_init import get_logger

try:
    from stock_data_service import get_stock_data_service

    SERVICE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Stock data service is unavailable: {e}")
    SERVICE_AVAILABLE = False

def get_stock_info(stock_code: str) -> Dict[str, Any]:
    """
    Get basic information about a single stock
    
    Args:
        stock_code: Stock code (e.g. '000001') 
    
    Returns:
        Dict: Basic stock information
    
    Example:
        >>> info = get_stock_info('000001')
        >>> print(info['name'])  # Ping An Bank
    """
    if not SERVICE_AVAILABLE:
        return {
            'error': 'Stock data service is unavailable',
            'code': stock_code,
            'suggestion': 'Please check service configuration'
        }
    
    service = get_stock_data_service()
    result = service.get_stock_basic_info(stock_code)
    
    if result is None:
        return {
            'error': f'No stock found{stock_code}information',
            'code': stock_code,
            'suggestion': 'Please check if the stock code is correct'
        }
    
    return result

def get_all_stocks() -> List[Dict[str, Any]]:
    """
    Get basic information on all stocks
    
    Returns:
        List[Dict]: List of basic information for all stocks
    
    Example:
        >>> stocks = get_all_stocks()
        logger.info(f"share{len(stocks)}only stocks")
    """
    if not SERVICE_AVAILABLE:
        return [{
            'error': 'Stock data service is unavailable',
            'suggestion': 'Please check service configuration'
        }]
    
    service = get_stock_data_service()
    result = service.get_stock_basic_info()
    
    if result is None or (isinstance(result, dict) and 'error' in result):
        return [{
            'error': 'Unable to get stock list',
            'suggestion': 'Please check network connection and database configuration'
        }]
    
    return result if isinstance(result, list) else [result]

def get_stock_data(stock_code: str, start_date: str = None, end_date: str = None) -> str:
    """
    Get stock historical data (with downgrade mechanism)
    
    Args:
        stock_code: Stock code
        start_date: Start date (format: YYYY-MM-DD), default is 30 days ago
        end_date: End date (format: YYYY-MM-DD), default is today
    
    Returns:
        str: String representation of stock data or error message
    
    Example:
        >>> data = get_stock_data('000001', '2024-01-01', '2024-01-31')
        >>> print(data)
    """
    if not SERVICE_AVAILABLE:
        return "❌ Stock data service is unavailable, please check service configuration"
    
    # Set default date
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    service = get_stock_data_service()
    return service.get_stock_data_with_fallback(stock_code, start_date, end_date)

def search_stocks(keyword: str) -> List[Dict[str, Any]]:
    """
    Search stocks based on keywords
    
    Args:
        keyword: Search keywords (stock symbol or part of name)
    
    Returns:
        List[Dict]: List of matching stock information
    
    Example:
        >>> results = search_stocks('Peace')
        >>> for stock in results:
        logger.info(f"{stock["code']}: {stock['name']}")
    """
    all_stocks = get_all_stocks()
    
    if not all_stocks or (len(all_stocks) == 1 and 'error' in all_stocks[0]):
        return all_stocks
    
    # Search for matching stocks
    matches = []
    keyword_lower = keyword.lower()
    
    for stock in all_stocks:
        if 'error' in stock:
            continue
            
        code = stock.get('code', '').lower()
        name = stock.get('name', '').lower()
        
        if keyword_lower in code or keyword_lower in name:
            matches.append(stock)
    
    return matches

def get_market_summary() -> Dict[str, Any]:
    """
    Get market overview information
    
    Returns:
        Dict: market statistics
    
    Example:
        >>> summary = get_market_summary()
        logger.info(f"Number of stocks on the Shanghai Stock Exchange: {summary["shanghai_count']}")
    """
    all_stocks = get_all_stocks()
    
    if not all_stocks or (len(all_stocks) == 1 and 'error' in all_stocks[0]):
        return {
            'error': 'Unable to get market data',
            'suggestion': 'Please check network connection and database configuration'
        }
    
    # Statistical market information
    shanghai_count = 0
    shenzhen_count = 0
    category_stats = {}
    
    for stock in all_stocks:
        if 'error' in stock:
            continue
            
        market = stock.get('market', '')
        category = stock.get('category', 'unknown')
        
        if market == 'Shanghai':
            shanghai_count += 1
        elif market == 'Shenzhen':
            shenzhen_count += 1
        
        category_stats[category] = category_stats.get(category, 0) + 1
    
    return {
        'total_count': len([s for s in all_stocks if 'error' not in s]),
        'shanghai_count': shanghai_count,
        'shenzhen_count': shenzhen_count,
        'category_stats': category_stats,
        'data_source': all_stocks[0].get('source', 'unknown') if all_stocks else 'unknown',
        'updated_at': datetime.now().isoformat()
    }

def check_service_status() -> Dict[str, Any]:
    """
    Check service status
    
    Returns:
        Dict: Service status information
    
    Example:
        >>> status = check_service_status()
        logger.info(f"MongoDB Status: {status["mongodb_status']}")
    """
    if not SERVICE_AVAILABLE:
        return {
            'service_available': False,
            'error': 'Stock data service is unavailable',
            'suggestion': 'Please check service configuration and dependencies'
        }
    
    service = get_stock_data_service()
    
    # Check MongoDB status
    mongodb_status = 'disconnected'
    if service.db_manager:
        try:
            # Try checking the connection status of the database manager
            if hasattr(service.db_manager, 'is_mongodb_available') and service.db_manager.is_mongodb_available():
                mongodb_status = 'connected'
            elif hasattr(service.db_manager, 'mongodb_client') and service.db_manager.mongodb_client:
                # Try executing a simple query to test the connection
                service.db_manager.mongodb_client.admin.command('ping')
                mongodb_status = 'connected'
            else:
                mongodb_status = 'unavailable'
        except Exception:
            mongodb_status = 'error'
    
    # Check Unified Data Interface Status
    unified_api_status = 'unavailable'
    try:
        # Try to get a stock information to test the unified interface
        test_result = service.get_stock_basic_info('000001')
        if test_result and 'error' not in test_result:
            unified_api_status = 'available'
        else:
            unified_api_status = 'limited'
    except Exception:
        unified_api_status = 'error'
    
    return {
        'service_available': True,
        'mongodb_status': mongodb_status,
        'unified_api_status': unified_api_status,
        'data_sources_available': ['tushare', 'akshare', 'baostock'],
        'fallback_available': True,
        'checked_at': datetime.now().isoformat()
    }

# Convenience alias functions
get_stock = get_stock_info  # Alias
get_stocks = get_all_stocks  # Alias
search = search_stocks  # Alias
status = check_service_status  # Alias

if __name__ == '__main__':
    # Simple command line test
    logger.debug(f"🔍 Stock data API testing")
    logger.info(f"=" * 50)
    
    # Check service status
    logger.info(f"\n📊 Service status check:")
    status_info = check_service_status()
    for key, value in status_info.items():
        logger.info(f"  {key}: {value}")
    
    # Test to obtain single stock information
    logger.info(f"\n🏢 Get Ping An Bank information:")
    stock_info = get_stock_info('000001')
    if 'error' not in stock_info:
        logger.info(f"  code: {stock_info.get('code')}")
        logger.info(f"  Name: {stock_info.get('name')}")
        logger.info(f"  market: {stock_info.get('market')}")
        logger.info(f"  Category: {stock_info.get('category')}")
        logger.info(f"  data source: {stock_info.get('source')}")
    else:
        logger.error(f"  Error: {stock_info.get('error')}")
    
    # Test search functionality
    logger.debug(f"\n🔍 Search'Peace'Related stocks:")
    search_results = search_stocks('Peace')
    for i, stock in enumerate(search_results[:3]):  # Show only first 3 results
        if 'error' not in stock:
            logger.info(f"  {i+1}. {stock.get('code')}")

    # Test market overview
    logger.info(f"\n📈 Market overview:")
    summary = get_market_summary()
    if 'error' not in summary:
        logger.info(f"  Total number of shares: {summary.get('total_count')}")
        logger.info(f"  Shanghai stock market: {summary.get('shanghai_count')}")
        logger.info(f"  Shenzhen stock market: {summary.get('shenzhen_count')}")
        logger.info(f"  data source: {summary.get('data_source')}")
    else:
        logger.error(f"  Error: {summary.get('error')}")