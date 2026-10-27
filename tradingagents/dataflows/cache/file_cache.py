#!/usr/bin/env python3
"""
Stock Data Cache Manager
Supports local caching of stock data, reduces API calls, and improves response speed
"""

import os
import json
import pickle
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Union, List
import hashlib

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


class StockDataCache:
    """Stock data cache manager - supports US stock and A-share data cache optimization"""

    def __init__(self, cache_dir: str = None):
        """
        Initialize cache manager

        Args:
            cache_dir: Cache directory path, default is tradingagents/dataflows/data_cache
        """
        if cache_dir is None:
            # Get the directory where the current file is located
            current_dir = Path(__file__).parent
            cache_dir = current_dir / "data_cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Create subcategory - by market
        self.us_stock_dir = self.cache_dir / "us_stocks"
        self.china_stock_dir = self.cache_dir / "china_stocks"
        self.us_news_dir = self.cache_dir / "us_news"
        self.china_news_dir = self.cache_dir / "china_news"
        self.us_fundamentals_dir = self.cache_dir / "us_fundamentals"
        self.china_fundamentals_dir = self.cache_dir / "china_fundamentals"
        self.metadata_dir = self.cache_dir / "metadata"

        # Create all directories
        for dir_path in [self.us_stock_dir, self.china_stock_dir, self.us_news_dir,
                        self.china_news_dir, self.us_fundamentals_dir,
                        self.china_fundamentals_dir, self.metadata_dir]:
            dir_path.mkdir(exist_ok=True)

        # Cache configuration - set different ones for different markets TTL
        self.cache_config = {
            'us_stock_data': {
                'ttl_hours': 2,  # U.S. stock data is cached for 2 hours (taking into account API restrictions)
                'max_files': 1000,
                'description': '美股历史数据'
            },
            'china_stock_data': {
                'ttl_hours': 1,  # A Stock data cache for 1 hour (high real-time requirements)
                'max_files': 1000,
                'description': 'A股历史数据'
            },
            'us_news': {
                'ttl_hours': 6,  # U.S. stock news cache for 6 hours
                'max_files': 500,
                'description': '美股新闻数据'
            },
            'china_news': {
                'ttl_hours': 4,  # A Stock news cached for 4 hours
                'max_files': 500,
                'description': 'A股新闻数据'
            },
            'us_fundamentals': {
                'ttl_hours': 24,  # U.S. stock fundamental data cached for 24 hours
                'max_files': 200,
                'description': '美股基本面数据'
            },
            'china_fundamentals': {
                'ttl_hours': 12,  # A Stock fundamental data cached for 12 hours
                'max_files': 200,
                'description': 'A股基本面数据'
            }
        }

        # Content length limit configuration (file cache has no limit by default)
        self.content_length_config = {
            'max_content_length': int(os.getenv('MAX_CACHE_CONTENT_LENGTH', '50000')),  # 50K character
            'long_text_providers': ['dashscope', 'openai', 'google'],  # Providers that support long text
            'enable_length_check': os.getenv('ENABLE_CACHE_LENGTH_CHECK', 'false').lower() == 'true'  # File caching is not limited by default
        }

        logger.info(f"📁 The cache manager initialization is completed and the cache directory: {self.cache_dir}")
        logger.info(f"🗄️ Database cache manager initialization completed")
        logger.info(f"   美股数据: ✅ 已配置")
        logger.info(f"   A股数据: ✅ 已配置")

    def _determine_market_type(self, symbol: str) -> str:
        """根据股票代码确定市场类型"""
        import re

        # Determine whether it is China A-share (6 digits)
        if re.match(r'^\d{6}$', str(symbol)):
            return 'china'
        else:
            return 'us'

    def _check_provider_availability(self) -> List[str]:
        """检查可用的LLM提供商"""
        available_providers = []
        
        # Check DashScope
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        if dashscope_key and dashscope_key.strip():
            available_providers.append('dashscope')
        
        # Check OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and openai_key.strip():
            # Simple format checking
            if openai_key.startswith('sk-') and len(openai_key) >= 40:
                available_providers.append('openai')
        
        # Check Google AI
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key and google_key.strip():
            available_providers.append('google')
        
        # Check Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key and anthropic_key.strip():
            available_providers.append('anthropic')
        
        return available_providers

    def should_skip_cache_for_content(self, content: str, data_type: str = "unknown") -> bool:
        """
        Determine whether to skip caching because the content is too long
        
        Args:
            content: Content to cache
            data_type: Data type (for logging)
        
        Returns:
            bool: Should caching be skipped
        """
        # If length checking is not enabled, return directly False
        if not self.content_length_config['enable_length_check']:
            return False
        
        # Check content length
        content_length = len(content)
        max_length = self.content_length_config['max_content_length']
        
        if content_length <= max_length:
            return False
        
        # The content is too long, check if there is an available long text processing provider
        available_providers = self._check_provider_availability()
        long_text_providers = self.content_length_config['long_text_providers']
        
        # Find available long text providers
        available_long_providers = [p for p in available_providers if p in long_text_providers]
        
        if not available_long_providers:
            logger.warning(f"⚠️ 内容过长({content_length:,}字符 > {max_length:,}字符)且无可用长文本提供商，跳过{data_type}缓存")
            logger.info(f"💡 可用提供商: {available_providers}")
            logger.info(f"💡 长文本提供商: {long_text_providers}")
            return True
        else:
            logger.info(f"✅ 内容较长({content_length:,}字符)但有可用长文本提供商({available_long_providers})，继续缓存")
            return False
    
    def _generate_cache_key(self, data_type: str, symbol: str, **kwargs) -> str:
        """生成缓存键"""
        # Create a string containing all parameters
        params_str = f"{data_type}_{symbol}"
        for key, value in sorted(kwargs.items()):
            params_str += f"_{key}_{value}"
        
        # Use MD5 to generate a short unique identifier
        cache_key = hashlib.md5(params_str.encode()).hexdigest()[:12]
        return f"{symbol}_{data_type}_{cache_key}"
    
    def _get_cache_path(self, data_type: str, cache_key: str, file_format: str = "json", symbol: str = None) -> Path:
        """Get cache file path - supports market classification"""
        if symbol:
            market_type = self._determine_market_type(symbol)
        else:
            # Try to extract market type from cache key
            market_type = 'us' if not cache_key.startswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9')) else 'china'

        # Select catalog based on data type and market type
        if data_type == "stock_data":
            base_dir = self.china_stock_dir if market_type == 'china' else self.us_stock_dir
        elif data_type == "news":
            base_dir = self.china_news_dir if market_type == 'china' else self.us_news_dir
        elif data_type == "fundamentals":
            base_dir = self.china_fundamentals_dir if market_type == 'china' else self.us_fundamentals_dir
        else:
            base_dir = self.cache_dir

        return base_dir / f"{cache_key}.{file_format}"
    
    def _get_metadata_path(self, cache_key: str) -> Path:
        """获取元数据文件路径"""
        return self.metadata_dir / f"{cache_key}_meta.json"
    
    def _save_metadata(self, cache_key: str, metadata: Dict[str, Any]):
        """保存元数据"""
        metadata_path = self._get_metadata_path(cache_key)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)  # Make sure the directory exists
        metadata['cached_at'] = datetime.now().isoformat()
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def _load_metadata(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """加载元数据"""
        metadata_path = self._get_metadata_path(cache_key)
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠️ 加载元数据失败: {e}")
            return None
    
    def is_cache_valid(self, cache_key: str, max_age_hours: int = None, symbol: str = None, data_type: str = None) -> bool:
        """Check cache is valid - supports smart TTL configuration"""
        metadata = self._load_metadata(cache_key)
        if not metadata:
            return False

        # If TTL is not specified, it is automatically determined based on the data type and market
        if max_age_hours is None:
            if symbol and data_type:
                market_type = self._determine_market_type(symbol)
                cache_type = f"{market_type}_{data_type}"
                max_age_hours = self.cache_config.get(cache_type, {}).get('ttl_hours', 24)
            else:
                # Get information from metadata
                symbol = metadata.get('symbol', '')
                data_type = metadata.get('data_type', 'stock_data')
                market_type = self._determine_market_type(symbol)
                cache_type = f"{market_type}_{data_type}"
                max_age_hours = self.cache_config.get(cache_type, {}).get('ttl_hours', 24)

        # 🔑 Make sure max_age_hours is an integer (maybe a string in the config file)
        try:
            max_age_hours = int(max_age_hours)
        except (ValueError, TypeError):
            logger.warning(f"⚠️ max_age_hours 无效: {max_age_hours}, 使用默认值24小时")
            max_age_hours = 24

        cached_at = datetime.fromisoformat(metadata['cached_at'])
        age = datetime.now() - cached_at

        is_valid = age.total_seconds() < max_age_hours * 3600

        if is_valid:
            market_type = self._determine_market_type(metadata.get('symbol', ''))
            cache_type = f"{market_type}_{metadata.get('data_type', 'stock_data')}"
            desc = self.cache_config.get(cache_type, {}).get('description', '数据')
            logger.info(f"✅ 缓存有效: {desc} - {metadata.get('symbol')} (剩余 {max_age_hours - age.total_seconds()/3600:.1f}h)")

        return is_valid
    
    def save_stock_data(self, symbol: str, data: Union[pd.DataFrame, str],
                       start_date: str = None, end_date: str = None,
                       data_source: str = "unknown") -> str:
        """
        Save stock data to cache - supports classified storage of US stocks and A shares

        Args:
            symbol: Stock code
            data: Stock data (DataFrame or String)
            start_date: start date
            end_date: end date
            data_source: data source (e.g. "tdx", "yfinance", "finnhub") 

        Returns:
            cache_key: cache key
        """
        # Check content length to see if cache needs to be skipped
        content_to_check = str(data)
        if self.should_skip_cache_for_content(content_to_check, "股票数据"):
            # Generates a dummy cache key but does not actually save it
            market_type = self._determine_market_type(symbol)
            cache_key = self._generate_cache_key("stock_data", symbol,
                                               start_date=start_date,
                                               end_date=end_date,
                                               source=data_source,
                                               market=market_type,
                                               skipped=True)
            logger.info(f"🚫 Stock data is skipped from cache due to too long content: {symbol} -> {cache_key}")
            return cache_key

        market_type = self._determine_market_type(symbol)
        cache_key = self._generate_cache_key("stock_data", symbol,
                                           start_date=start_date,
                                           end_date=end_date,
                                           source=data_source,
                                           market=market_type)

        # save data
        if isinstance(data, pd.DataFrame):
            cache_path = self._get_cache_path("stock_data", cache_key, "csv", symbol)
            cache_path.parent.mkdir(parents=True, exist_ok=True)  # Make sure the directory exists
            data.to_csv(cache_path, index=True)
        else:
            cache_path = self._get_cache_path("stock_data", cache_key, "txt", symbol)
            cache_path.parent.mkdir(parents=True, exist_ok=True)  # Make sure the directory exists
            with open(cache_path, 'w', encoding='utf-8') as f:
                f.write(str(data))

        # Save metadata
        metadata = {
            'symbol': symbol,
            'data_type': 'stock_data',
            'market_type': market_type,
            'start_date': start_date,
            'end_date': end_date,
            'data_source': data_source,
            'file_path': str(cache_path),
            'file_format': 'csv' if isinstance(data, pd.DataFrame) else 'txt',
            'content_length': len(content_to_check)
        }
        self._save_metadata(cache_key, metadata)

        # Get description information
        cache_type = f"{market_type}_stock_data"
        desc = self.cache_config.get(cache_type, {}).get('description', '股票数据')
        logger.info(f"💾 {desc}已缓存: {symbol} ({data_source}) -> {cache_key}")
        return cache_key
    
    def load_stock_data(self, cache_key: str) -> Optional[Union[pd.DataFrame, str]]:
        """从缓存加载股票数据"""
        metadata = self._load_metadata(cache_key)
        if not metadata:
            return None
        
        cache_path = Path(metadata['file_path'])
        if not cache_path.exists():
            return None
        
        try:
            if metadata['file_format'] == 'csv':
                return pd.read_csv(cache_path, index_col=0)
            else:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            logger.error(f"⚠️ 加载缓存数据失败: {e}")
            return None
    
    def find_cached_stock_data(self, symbol: str, start_date: str = None,
                              end_date: str = None, data_source: str = None,
                              max_age_hours: int = None) -> Optional[str]:
        """
        Find matching cached data - supports smart market category lookups

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            data_source: data source
            max_age_hours: Maximum cache time (hours), use smart configuration when None

        Returns:
            cache_key: Returns the cache key if a valid cache is found, otherwise None
        """
        market_type = self._determine_market_type(symbol)

        # If TTL is not specified, smart configuration is used
        if max_age_hours is None:
            cache_type = f"{market_type}_stock_data"
            max_age_hours = self.cache_config.get(cache_type, {}).get('ttl_hours', 24)

        # Generate lookup key
        search_key = self._generate_cache_key("stock_data", symbol,
                                            start_date=start_date,
                                            end_date=end_date,
                                            source=data_source,
                                            market=market_type)

        # Check for exact match
        if self.is_cache_valid(search_key, max_age_hours, symbol, 'stock_data'):
            desc = self.cache_config.get(f"{market_type}_stock_data", {}).get('description', '数据')
            logger.info(f"🎯 找到精确匹配的{desc}: {symbol} -> {search_key}")
            return search_key

        # If there is no exact match, look for partial matches (other caches of the same ticker)
        for metadata_file in self.metadata_dir.glob(f"*_meta.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                if (metadata.get('symbol') == symbol and
                    metadata.get('data_type') == 'stock_data' and
                    metadata.get('market_type') == market_type and
                    (data_source is None or metadata.get('data_source') == data_source)):

                    cache_key = metadata_file.stem.replace('_meta', '')
                    if self.is_cache_valid(cache_key, max_age_hours, symbol, 'stock_data'):
                        desc = self.cache_config.get(f"{market_type}_stock_data", {}).get('description', '数据')
                        logger.info(f"📋 找到部分匹配的{desc}: {symbol} -> {cache_key}")
                        return cache_key
            except Exception:
                continue

        desc = self.cache_config.get(f"{market_type}_stock_data", {}).get('description', '数据')
        logger.error(f"❌ 未找到有效的{desc}缓存: {symbol}")
        return None
    
    def save_news_data(self, symbol: str, news_data: str, 
                      start_date: str = None, end_date: str = None,
                      data_source: str = "unknown") -> str:
        """保存新闻数据到缓存"""
        # Check content length to see if cache needs to be skipped
        if self.should_skip_cache_for_content(news_data, "新闻数据"):
            # Generates a dummy cache key but does not actually save it
            cache_key = self._generate_cache_key("news", symbol,
                                               start_date=start_date,
                                               end_date=end_date,
                                               source=data_source,
                                               skipped=True)
            logger.info(f"🚫 News data is skipped from cache due to too long content: {symbol} -> {cache_key}")
            return cache_key

        cache_key = self._generate_cache_key("news", symbol,
                                           start_date=start_date,
                                           end_date=end_date,
                                           source=data_source)
        
        cache_path = self._get_cache_path("news", cache_key, "txt")
        cache_path.parent.mkdir(parents=True, exist_ok=True)  # Make sure the directory exists
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(news_data)
        
        metadata = {
            'symbol': symbol,
            'data_type': 'news',
            'start_date': start_date,
            'end_date': end_date,
            'data_source': data_source,
            'file_path': str(cache_path),
            'file_format': 'txt',
            'content_length': len(news_data)
        }
        self._save_metadata(cache_key, metadata)
        
        logger.info(f"📰 新闻数据已缓存: {symbol} ({data_source}) -> {cache_key}")
        return cache_key
    
    def save_fundamentals_data(self, symbol: str, fundamentals_data: str,
                              data_source: str = "unknown") -> str:
        """保存基本面数据到缓存"""
        # Check content length to see if cache needs to be skipped
        if self.should_skip_cache_for_content(fundamentals_data, "基本面数据"):
            # Generates a dummy cache key but does not actually save it
            market_type = self._determine_market_type(symbol)
            cache_key = self._generate_cache_key("fundamentals", symbol,
                                               source=data_source,
                                               market=market_type,
                                               date=datetime.now().strftime("%Y-%m-%d"),
                                               skipped=True)
            logger.info(f"🚫 Fundamental data is skipped from cache due to too long content: {symbol} -> {cache_key}")
            return cache_key

        market_type = self._determine_market_type(symbol)
        cache_key = self._generate_cache_key("fundamentals", symbol,
                                           source=data_source,
                                           market=market_type,
                                           date=datetime.now().strftime("%Y-%m-%d"))
        
        cache_path = self._get_cache_path("fundamentals", cache_key, "txt", symbol)
        cache_path.parent.mkdir(parents=True, exist_ok=True)  # Make sure the directory exists
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(fundamentals_data)
        
        metadata = {
            'symbol': symbol,
            'data_type': 'fundamentals',
            'data_source': data_source,
            'market_type': market_type,
            'file_path': str(cache_path),
            'file_format': 'txt',
            'content_length': len(fundamentals_data)
        }
        self._save_metadata(cache_key, metadata)
        
        desc = self.cache_config.get(f"{market_type}_fundamentals", {}).get('description', '基本面数据')
        logger.info(f"💼 {desc}已缓存: {symbol} ({data_source}) -> {cache_key}")
        return cache_key
    
    def load_fundamentals_data(self, cache_key: str) -> Optional[str]:
        """从缓存加载基本面数据"""
        metadata = self._load_metadata(cache_key)
        if not metadata:
            return None
        
        cache_path = Path(metadata['file_path'])
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"⚠️ Failed to load fundamental cache data: {e}")
            return None
    
    def find_cached_fundamentals_data(self, symbol: str, data_source: str = None,
                                    max_age_hours: int = None) -> Optional[str]:
        """
        Find matching fundamental cache data
        
        Args:
            symbol: Stock code
            data_source: data source (e.g. "openai", "finnhub") 
            max_age_hours: Maximum cache time (hours), use smart configuration when None
        
        Returns:
            cache_key: Returns the cache key if a valid cache is found, otherwise None
        """
        market_type = self._determine_market_type(symbol)
        
        # If TTL is not specified, smart configuration is used
        if max_age_hours is None:
            cache_type = f"{market_type}_fundamentals"
            max_age_hours = self.cache_config.get(cache_type, {}).get('ttl_hours', 24)
        
        # 🔑 Make sure max_age_hours is an integer (maybe a string in the config file)
        try:
            max_age_hours = int(max_age_hours)
        except (ValueError, TypeError):
            logger.warning(f"⚠️ max_age_hours 无效: {max_age_hours}, 使用默认值24小时")
            max_age_hours = 24
        
        # Find matching cache
        for metadata_file in self.metadata_dir.glob(f"*_meta.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                if (metadata.get('symbol') == symbol and
                    metadata.get('data_type') == 'fundamentals' and
                    metadata.get('market_type') == market_type and
                    (data_source is None or metadata.get('data_source') == data_source)):
                    
                    cache_key = metadata_file.stem.replace('_meta', '')
                    if self.is_cache_valid(cache_key, max_age_hours, symbol, 'fundamentals'):
                        desc = self.cache_config.get(f"{market_type}_fundamentals", {}).get('description', '基本面数据')
                        logger.info(f"🎯 找到匹配的{desc}缓存: {symbol} ({data_source}) -> {cache_key}")
                        return cache_key
            except Exception:
                continue
        
        desc = self.cache_config.get(f"{market_type}_fundamentals", {}).get('description', '基本面数据')
        logger.error(f"❌ 未找到有效的{desc}缓存: {symbol} ({data_source})")
        return None
    
    def clear_old_cache(self, max_age_days: int = 7):
        """清理过期缓存"""
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        cleared_count = 0
        
        for metadata_file in self.metadata_dir.glob("*_meta.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                cached_at = datetime.fromisoformat(metadata['cached_at'])
                if cached_at < cutoff_time:
                    # Delete data files
                    data_file = Path(metadata['file_path'])
                    if data_file.exists():
                        data_file.unlink()
                    
                    # Delete metadata files
                    metadata_file.unlink()
                    cleared_count += 1
                    
            except Exception as e:
                logger.warning(f"⚠️ 清理缓存时出错: {e}")
        
        logger.info(f"🧹 已清理 {cleared_count} 个过期缓存文件")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            'total_files': 0,
            'stock_data_count': 0,
            'news_count': 0,
            'fundamentals_count': 0,
            'total_size': 0,  # Bytes
            'total_size_mb': 0,  # MB (reserved for compatibility)
            'skipped_count': 0  # New: Number of caches to skip
        }

        total_size_bytes = 0

        # Statistics of cached files with metadata
        metadata_files_count = 0
        for metadata_file in self.metadata_dir.glob("*_meta.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                data_type = metadata.get('data_type', 'unknown')
                if data_type == 'stock_data':
                    stats['stock_data_count'] += 1
                elif data_type == 'news':
                    stats['news_count'] += 1
                elif data_type == 'fundamentals':
                    stats['fundamentals_count'] += 1

                # Check for skipped cache (no actual file)
                data_file = Path(metadata.get('file_path', ''))
                if not data_file.exists():
                    stats['skipped_count'] += 1
                else:
                    # Calculate file size (bytes)
                    file_size = data_file.stat().st_size
                    total_size_bytes += file_size

                stats['total_files'] += 1
                metadata_files_count += 1

            except Exception:
                continue

        # If there is no metadata file, the files in the cache directory will be counted directly (compatible with old cache)
        if metadata_files_count == 0:
            logger.info("📊 No metadata file found, directly count the files in the cache directory")

            # Count files in each directory
            for stock_dir, data_type in [
                (self.us_stock_dir, 'us_stock'),
                (self.china_stock_dir, 'china_stock'),
                (self.us_news_dir, 'us_news'),
                (self.china_news_dir, 'china_news'),
                (self.us_fundamentals_dir, 'us_fundamentals'),
                (self.china_fundamentals_dir, 'china_fundamentals')
            ]:
                if stock_dir.exists():
                    for file_path in stock_dir.glob("*"):
                        if file_path.is_file():
                            try:
                                file_size = file_path.stat().st_size
                                total_size_bytes += file_size
                                stats['total_files'] += 1

                                # Classified by type
                                if 'stock' in data_type:
                                    stats['stock_data_count'] += 1
                                elif 'news' in data_type:
                                    stats['news_count'] += 1
                                elif 'fundamentals' in data_type:
                                    stats['fundamentals_count'] += 1
                            except Exception:
                                continue

        stats['total_size'] = total_size_bytes  # Bytes
        stats['total_size_mb'] = round(total_size_bytes / (1024 * 1024), 2)  # MB
        return stats

    def get_content_length_config_status(self) -> Dict[str, Any]:
        """获取内容长度配置状态"""
        available_providers = self._check_provider_availability()
        long_text_providers = self.content_length_config['long_text_providers']
        available_long_providers = [p for p in available_providers if p in long_text_providers]
        
        return {
            'enabled': self.content_length_config['enable_length_check'],
            'max_content_length': self.content_length_config['max_content_length'],
            'max_content_length_formatted': f"{self.content_length_config['max_content_length']:,}字符",
            'long_text_providers': long_text_providers,
            'available_providers': available_providers,
            'available_long_providers': available_long_providers,
            'has_long_text_support': len(available_long_providers) > 0,
            'will_skip_long_content': self.content_length_config['enable_length_check'] and len(available_long_providers) == 0
        }


# Global cache instance
_cache_instance = None

def get_cache() -> StockDataCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = StockDataCache()
    return _cache_instance
