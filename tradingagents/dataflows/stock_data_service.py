#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified stock data acquisition service
realize MongoDB -> Tushare Complete degradation mechanism for data interfaces
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

try:
    from tradingagents.config.database_manager import get_database_manager
    DATABASE_MANAGER_AVAILABLE = True
except ImportError:
    DATABASE_MANAGER_AVAILABLE = False

try:
    import sys
    import os
    # Add utils directory to path
    utils_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'utils')
    if utils_path not in sys.path:
        sys.path.append(utils_path)
    from enhanced_stock_list_fetcher import enhanced_fetch_stock_list
    ENHANCED_FETCHER_AVAILABLE = True
except ImportError:
    ENHANCED_FETCHER_AVAILABLE = False

logger = logging.getLogger(__name__)

class StockDataService:
    """
    Unified stock data acquisition service
    Implement a complete downgrade mechanism:MongoDB -> Tushare Data interface -> cache -> Error handling
    """
    
    def __init__(self):
        self.db_manager = None
        self._init_services()
    
    def _init_services(self):
        """初始化服务"""
        # Try to initialize the database manager
        if DATABASE_MANAGER_AVAILABLE:
            try:
                self.db_manager = get_database_manager()
                if self.db_manager.is_mongodb_available():
                    logger.info(f"✅ MongoDB Connection successful")
                else:
                    logger.error(f"⚠️ MongoDB Connection failed, other data source will be used")
            except Exception as e:
                logger.error(f"⚠️ Database manager initialization failed: {e}")
                self.db_manager = None
    
    def get_stock_basic_info(self, stock_code: str = None) -> Optional[Dict[str, Any]]:
        """
        Get basic stock information (single stock or all stocks)
        
        Args:
            stock_code: Stock code, if None returns all stocks
        
        Returns:
            Dict: Basic stock information
        """
        logger.info(f"📊 获取股票基础信息: {stock_code or '全部股票'}")
        
        # 1. Get it from MongoDB first
        if self.db_manager and self.db_manager.is_mongodb_available():
            try:
                result = self._get_from_mongodb(stock_code)
                if result:
                    logger.info(f"✅ 从MongoDB获取成功: {len(result) if isinstance(result, list) else 1}条记录")
                    return result
            except Exception as e:
                logger.error(f"⚠️ MongoDB Query failed: {e}")
        
        # 2. Downgrade to boost getter
        logger.info(f"🔄 MongoDB Not available, downgraded to enhanced getter")
        if ENHANCED_FETCHER_AVAILABLE:
            try:
                result = self._get_from_enhanced_fetcher(stock_code)
                if result:
                    logger.info(f"✅ 从增强获取器获取成功: {len(result) if isinstance(result, list) else 1}条记录")
                    # Try caching to MongoDB if available
                    self._cache_to_mongodb(result)
                    return result
            except Exception as e:
                logger.error(f"⚠️ Enhanced getter query failed: {e}")
        
        # 3. The final downgrade option
        logger.error(f"❌ 所有数据源都不可用")
        return self._get_fallback_data(stock_code)
    
    def _get_from_mongodb(self, stock_code: str = None) -> Optional[Dict[str, Any]]:
        """从MongoDB获取数据"""
        try:
            mongodb_client = self.db_manager.get_mongodb_client()
            if not mongodb_client:
                return None

            db = mongodb_client[self.db_manager.mongodb_config["database"]]
            collection = db['stock_basic_info']

            if stock_code:
                # Get a single stock
                result = collection.find_one({'code': stock_code})
                return result if result else None
            else:
                # Get all stocks
                cursor = collection.find({})
                results = list(cursor)
                return results if results else None

        except Exception as e:
            logger.error(f"MongoDB查询失败: {e}")
            return None
    
    def _get_from_enhanced_fetcher(self, stock_code: str = None) -> Optional[Dict[str, Any]]:
        """从增强获取器获取数据"""
        try:
            if stock_code:
                # Get individual stock information - use the enhanced getter to get all stocks and then filter
                stock_df = enhanced_fetch_stock_list(
                    type_='stock',
                    enable_server_failover=True,
                    max_retries=3
                )
                
                if stock_df is not None and not stock_df.empty:
                    # Find a specific stock code
                    stock_row = stock_df[stock_df['code'] == stock_code]
                    if not stock_row.empty:
                        row = stock_row.iloc[0]
                        return {
                            'code': row.get('code', stock_code),
                            'name': row.get('name', ''),
                            'market': row.get('market', self._get_market_name(stock_code)),
                            'category': row.get('category', self._get_stock_category(stock_code)),
                            'source': 'enhanced_fetcher',
                            'updated_at': datetime.now().isoformat()
                        }
                    else:
                        # If not found, return to basic information
                        return {
                            'code': stock_code,
                            'name': '',
                            'market': self._get_market_name(stock_code),
                            'category': self._get_stock_category(stock_code),
                            'source': 'enhanced_fetcher',
                            'updated_at': datetime.now().isoformat()
                        }
            else:
                # Get a list of all stocks
                stock_df = enhanced_fetch_stock_list(
                    type_='stock',
                    enable_server_failover=True,
                    max_retries=3
                )
                
                if stock_df is not None and not stock_df.empty:
                    # Convert to list of dictionaries
                    results = []
                    for _, row in stock_df.iterrows():
                        results.append({
                            'code': row.get('code', ''),
                            'name': row.get('name', ''),
                            'market': row.get('market', ''),
                            'category': row.get('category', ''),
                            'source': 'enhanced_fetcher',
                            'updated_at': datetime.now().isoformat()
                        })
                    return results
                    
        except Exception as e:
            logger.error(f"增强获取器查询失败: {e}")
            return None
    
    def _cache_to_mongodb(self, data: Any) -> bool:
        """Cache data to MongoDB"""
        if not self.db_manager or not self.db_manager.mongodb_db:
            return False
        
        try:
            collection = self.db_manager.mongodb_db['stock_basic_info']
            
            if isinstance(data, list):
                # Batch insert
                for item in data:
                    collection.update_one(
                        {'code': item['code']},
                        {'$set': item},
                        upsert=True
                    )
                logger.info(f"💾 已缓存{len(data)}条记录到MongoDB")
            elif isinstance(data, dict):
                # Single insert
                collection.update_one(
                    {'code': data['code']},
                    {'$set': data},
                    upsert=True
                )
                logger.info(f"💾 已缓存股票{data['code']}到MongoDB")
            
            return True
            
        except Exception as e:
            logger.error(f"Cache to MongoDB fails: {e}")
            return False
    
    def _get_fallback_data(self, stock_code: str = None) -> Dict[str, Any]:
        """最后的降级数据"""
        if stock_code:
            return {
                'code': stock_code,
                'name': f'股票{stock_code}',
                'market': self._get_market_name(stock_code),
                'category': '未知',
                'source': 'fallback',
                'updated_at': datetime.now().isoformat(),
                'error': '所有数据源都不可用'
            }
        else:
            return {
                'error': 'Unable to get stock list, please check network connection and database configuration',
                'suggestion': 'Please ensure that MongoDB is configured or the network connection is normal to access the Tushare data interface'
            }
    
    def _get_market_name(self, stock_code: str) -> str:
        """根据股票代码判断市场"""
        if stock_code.startswith(('60', '68', '90')):
            return '上海'
        elif stock_code.startswith(('00', '30', '20')):
            return '深圳'
        else:
            return '未知'
    
    def _get_stock_category(self, stock_code: str) -> str:
        """根据股票代码判断类别"""
        if stock_code.startswith('60'):
            return '沪市主板'
        elif stock_code.startswith('68'):
            return '科创板'
        elif stock_code.startswith('00'):
            return '深市主板'
        elif stock_code.startswith('30'):
            return '创业板'
        elif stock_code.startswith('20'):
            return '深市B股'
        else:
            return '其他'
    
    def get_stock_data_with_fallback(self, stock_code: str, start_date: str, end_date: str) -> str:
        """
        Get stock data (with downgrade mechanism)
        This is an enhancement to the existing get_china_stock_data function
        """
        logger.info(f"📊 获取股票数据: {stock_code} ({start_date} 到 {end_date})")
        
        # First make sure basic stock information is available
        stock_info = self.get_stock_basic_info(stock_code)
        if stock_info and 'error' in stock_info:
            return f"❌ 无法获取股票{stock_code}的基础信息: {stock_info.get('error', '未知错误')}"
        
        # Call the unified Chinese stock data interface
        try:
            from .interface import get_china_stock_data_unified

            return get_china_stock_data_unified(stock_code, start_date, end_date)
        except Exception as e:
            return f"❌ 获取股票数据失败: {str(e)}\n\n💡 建议：\n1. 检查网络连接\n2. 确认股票代码格式正确\n3. 检查MongoDB配置"

# Global service instance
_stock_data_service = None

def get_stock_data_service() -> StockDataService:
    """Get the stock data service instance (single case mode)"""
    global _stock_data_service
    if _stock_data_service is None:
        _stock_data_service = StockDataService()
    return _stock_data_service