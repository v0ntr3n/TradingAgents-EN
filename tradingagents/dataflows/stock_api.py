#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock data API interface
Provides a simple and easy-to-use stock data acquisition interface with a complete built-in downgrade mechanism
"""

from typing import Dict, List, Optional, Any
from .stock_data_service import get_stock_data_service

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

def get_stock_info(stock_code: str) -> Optional[Dict[str, Any]]:
    """
    Get basic information about a single stock
    
    Args:
        stock_code: Stock code (e.g. '000001') 
    
    Returns:
        Dict: Stock information, including code, name, market, category etc fields
              If the acquisition fails, a dictionary containing the error field is returned.
    
    Example:
        >>> info = get_stock_info('000001')
        >>> print(info['name'])  # output: Ping An Bank
    """
    service = get_stock_data_service()
    return service.get_stock_basic_info(stock_code)

def get_all_stocks() -> List[Dict[str, Any]]:
    """
    Get a list of all stocks
    
    Returns:
        List[Dict]: Stock list, each element contains basic stock information
                   If the acquisition fails, a dictionary containing the error field is returned.
    
    Example:
        >>> stocks = get_all_stocks()
        logger.info(f"share{len(stocks)}only stocks")
    """
    service = get_stock_data_service()
    result = service.get_stock_basic_info()
    
    if isinstance(result, list):
        return result
    elif isinstance(result, dict) and 'error' in result:
        return [result]  # Return error message
    else:
        return []

def get_stock_data(stock_code: str, start_date: str, end_date: str) -> str:
    """
    Get stock historical data (with downgrade mechanism)
    
    Args:
        stock_code: Stock code
        start_date: start date 'YYYY-MM-DD'
        end_date: end date 'YYYY-MM-DD'
    
    Returns:
        str: Formatted stock data reports
    
    Example:
        >>> data = get_stock_data('000001', '2024-01-01', '2024-01-31')
        >>> print(data)
    """
    service = get_stock_data_service()
    return service.get_stock_data_with_fallback(stock_code, start_date, end_date)

def search_stocks_by_name(name: str) -> List[Dict[str, Any]]:
    """
    Search stocks based on stock name (requires MongoDB support)
    
    Args:
        name: Stock name keywords
    
    Returns:
        List[Dict]: Matching stock list
    
    Example:
        >>> results = search_stocks_by_name('bank')
        >>> for stock in results:
        logger.info(f"{stock['code']}: {stock['name']}")
    """
    # This function requires MongoDB support and is temporarily implemented through the original method.
    try:
        from ..examples.stock_query_examples import EnhancedStockQueryService

        service = EnhancedStockQueryService()
        return service.query_stocks_by_name(name)
    except Exception as e:
        return [{'error': f'名称搜索功能不可用: {str(e)}'}]

def check_data_sources() -> Dict[str, Any]:
    """
    Check data source status
    
    Returns:
        Dict: Availability status of each data source
    
    Example:
        >>> status = check_data_sources()
        logger.info(f"MongoDB Available: {status['mongodb_available']}")
        logger.info(f"Unified data interface available: {status['unified_api_available']}")
    """
    service = get_stock_data_service()
    
    return {
        'mongodb_available': service.db_manager is not None and service.db_manager.mongodb_db is not None,
        'unified_api_available': True,  # Unified interface is always available
        'enhanced_fetcher_available': True,  # This is usually available
        'fallback_mode': service.db_manager is None or service.db_manager.mongodb_db is None,
        'recommendation': (
            "所有数据源正常" if service.db_manager and service.db_manager.mongodb_db 
            else "It is recommended to configure MongoDB for optimal performance, currently using Unified Data Interface degraded mode"
        )
    }