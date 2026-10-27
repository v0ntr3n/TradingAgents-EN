#!/usr/bin/env python3
"""
Improved Hong Kong stock data acquisition tool
Fix API rate limiting and data fetching issues
"""

import time
import json
import os
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from tradingagents.config.runtime_settings import get_int
# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# New: Use unified data directory configuration
try:
    from utils.data_config import get_cache_dir
except Exception:
    # Fallback: in the project root directory data/cache/hk
    def get_cache_dir(subdir: Optional[str] = None, create: bool = True):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'cache')
        if subdir:
            base = os.path.join(base, subdir)
        if create:
            os.makedirs(base, exist_ok=True)
        return base


class ImprovedHKStockProvider:
    """改进的港股数据提供器"""
    
    def __init__(self):
        # Write cache files to a unified data cache directory to avoid contaminating the project root directory
        hk_cache_dir = get_cache_dir('hk')
        if hasattr(hk_cache_dir, 'joinpath'):  # Path
            self.cache_file = str(hk_cache_dir.joinpath('hk_stock_cache.json'))
        else:  # str
            self.cache_file = os.path.join(hk_cache_dir, 'hk_stock_cache.json')

        self.cache_ttl = get_int("TA_HK_CACHE_TTL_SECONDS", "ta_hk_cache_ttl_seconds", 3600 * 24)
        self.rate_limit_wait = get_int("TA_HK_RATE_LIMIT_WAIT_SECONDS", "ta_hk_rate_limit_wait_seconds", 5)
        self.last_request_time = 0

        # Built-in Hong Kong stock name mapping (avoiding API calls)
        self.hk_stock_names = {
            # Tencent department
            '0700.HK': '腾讯控股', '0700': '腾讯控股', '00700': '腾讯控股',
            
            # telecom operator
            '0941.HK': '中国移动', '0941': '中国移动', '00941': '中国移动',
            '0762.HK': '中国联通', '0762': '中国联通', '00762': '中国联通',
            '0728.HK': '中国电信', '0728': '中国电信', '00728': '中国电信',
            
            # bank
            '0939.HK': '建设银行', '0939': '建设银行', '00939': '建设银行',
            '1398.HK': '工商银行', '1398': '工商银行', '01398': '工商银行',
            '3988.HK': '中国银行', '3988': '中国银行', '03988': '中国银行',
            '0005.HK': '汇丰控股', '0005': '汇丰控股', '00005': '汇丰控股',
            
            # insurance
            '1299.HK': '友邦保险', '1299': '友邦保险', '01299': '友邦保险',
            '2318.HK': '中国平安', '2318': '中国平安', '02318': '中国平安',
            '2628.HK': '中国人寿', '2628': '中国人寿', '02628': '中国人寿',
            
            # Petrochemical industry
            '0857.HK': '中国石油', '0857': '中国石油', '00857': '中国石油',
            '0386.HK': '中国石化', '0386': '中国石化', '00386': '中国石化',
            
            # real estate
            '1109.HK': '华润置地', '1109': '华润置地', '01109': '华润置地',
            '1997.HK': '九龙仓置业', '1997': '九龙仓置业', '01997': '九龙仓置业',
            
            # Technology
            '9988.HK': '阿里巴巴', '9988': '阿里巴巴', '09988': '阿里巴巴',
            '3690.HK': '美团', '3690': '美团', '03690': '美团',
            '1024.HK': '快手', '1024': '快手', '01024': '快手',
            '9618.HK': '京东集团', '9618': '京东集团', '09618': '京东集团',
            
            # consumption
            '1876.HK': '百威亚太', '1876': '百威亚太', '01876': '百威亚太',
            '0291.HK': '华润啤酒', '0291': '华润啤酒', '00291': '华润啤酒',
            
            # Medicine
            '1093.HK': '石药集团', '1093': '石药集团', '01093': '石药集团',
            '0867.HK': '康师傅', '0867': '康师傅', '00867': '康师傅',
            
            # car
            '2238.HK': '广汽集团', '2238': '广汽集团', '02238': '广汽集团',
            '1211.HK': '比亚迪', '1211': '比亚迪', '01211': '比亚迪',
            
            # Aviation
            '0753.HK': '中国国航', '0753': '中国国航', '00753': '中国国航',
            '0670.HK': '中国东航', '0670': '中国东航', '00670': '中国东航',
            
            # steel
            '0347.HK': '鞍钢股份', '0347': '鞍钢股份', '00347': '鞍钢股份',
            
            # electricity
            '0902.HK': '华能国际', '0902': '华能国际', '00902': '华能国际',
            '0991.HK': '大唐发电', '0991': '大唐发电', '00991': '大唐发电'
        }
        
        self._load_cache()
    
    def _load_cache(self):
        """加载缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            else:
                self.cache = {}
        except Exception as e:
            logger.debug(f"📊 [Hong Kong stock cache] Failed to load cache: {e}")
            self.cache = {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            # Make sure the directory exists
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"📊 [Hong Kong stock cache] Failed to save cache: {e}")
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self.cache:
            return False

        cache_time = self.cache[key].get('timestamp', 0)
        return (time.time() - cache_time) < self.cache_ttl

    def _rate_limit(self):
        """Rate limiting: ensure there is sufficient time between requests"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.rate_limit_wait:
            wait_time = self.rate_limit_wait - time_since_last_request
            logger.debug(f"⏱️ [速率限制] 等待 {wait_time:.2f} 秒")
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def _normalize_hk_symbol(self, symbol: str) -> str:
        """标准化港股代码"""
        # Remove .HK suffix
        clean_symbol = symbol.replace('.HK', '').replace('.hk', '')
        
        # Complete to 5 digits
        if len(clean_symbol) == 4:
            clean_symbol = '0' + clean_symbol
        elif len(clean_symbol) == 3:
            clean_symbol = '00' + clean_symbol
        elif len(clean_symbol) == 2:
            clean_symbol = '000' + clean_symbol
        elif len(clean_symbol) == 1:
            clean_symbol = '0000' + clean_symbol
        
        return clean_symbol
    
    def get_company_name(self, symbol: str) -> str:
        """
        Get the name of Hong Kong stock company
        
        Args:
            symbol: Hong Kong stock code
            
        Returns:
            str: Company name
        """
        try:
            # Check cache
            cache_key = f"name_{symbol}"
            if self._is_cache_valid(cache_key):
                cached_name = self.cache[cache_key]['data']
                logger.debug(f"📊 [Hong Kong stock cache] Get company name from cache: {symbol} -> {cached_name}")
                return cached_name
            
            # Option 1: Use built-in mapping
            normalized_symbol = self._normalize_hk_symbol(symbol)
            
            # Try multiple format matches
            for format_symbol in [symbol, normalized_symbol, f"{normalized_symbol}.HK"]:
                if format_symbol in self.hk_stock_names:
                    company_name = self.hk_stock_names[format_symbol]
                    
                    # cache results
                    self.cache[cache_key] = {
                        'data': company_name,
                        'timestamp': time.time(),
                        'source': 'builtin_mapping'
                    }
                    self._save_cache()
                    
                    logger.debug(f"📊 [Hong Kong stock mapping] Get company name: {symbol} -> {company_name}")
                    return company_name
            
            # Option 2: Try AKShare API acquisition first (with rate limit protection)
            try:
                # Rate limit protection
                current_time = time.time()
                if current_time - self.last_request_time < self.rate_limit_wait:
                    wait_time = self.rate_limit_wait - (current_time - self.last_request_time)
                    logger.debug(f"📊 [港股API] 速率限制保护，等待 {wait_time:.1f} 秒")
                    time.sleep(wait_time)

                self.last_request_time = time.time()

                # Prioritize trying AKShare to obtain
                try:
                    # Directly use the akshare library to obtain it to avoid circular calls
                    logger.debug(f"📊 [Hong Kong stocks API] Prioritize using AKShare to obtain: {symbol}")

                    import akshare as ak
                    # Standardized code format (akshare requires 5-digit number format)
                    normalized_symbol = self._normalize_hk_symbol(symbol)

                    # Try to get real-time quotes of Hong Kong stocks (including names)
                    try:
                        # Use Sina Finance interface (more stable)
                        df = ak.stock_hk_spot()
                        if df is not None and not df.empty:
                            # Find matching stocks
                            matched = df[df['代码'] == normalized_symbol]
                            if not matched.empty:
                                # The column name returned by the Sina interface is 'Chinese name'
                                akshare_name = matched.iloc[0]['中文名称']
                                if akshare_name and not str(akshare_name).startswith('港股'):
                                    # Caching AKShare results
                                    self.cache[cache_key] = {
                                        'data': akshare_name,
                                        'timestamp': time.time(),
                                        'source': 'akshare_sina'
                                    }
                                    self._save_cache()

                                    logger.debug(f"📊 [Hong Kong stocks AKShare-Sina] Get company name: {symbol} -> {akshare_name}")
                                    return akshare_name
                    except Exception as e:
                        logger.debug(f"📊 [Hong Kong stocks AKShare-Sina] Failed to obtain real-time quotes: {e}")

                except Exception as e:
                    logger.debug(f"📊 [Hong Kong stocks AKShare] AKShare Failed to obtain: {e}")

                # Alternate: Try getting from the unified interface (including Yahoo Finance)
                from tradingagents.dataflows.interface import get_hk_stock_info_unified
                hk_info = get_hk_stock_info_unified(symbol)

                if hk_info and isinstance(hk_info, dict) and 'name' in hk_info:
                    api_name = hk_info['name']
                    if not api_name.startswith('港股'):
                        # Caching API results
                        self.cache[cache_key] = {
                            'data': api_name,
                            'timestamp': time.time(),
                            'source': 'unified_api'
                        }
                        self._save_cache()

                        logger.debug(f"📊 [Hong Kong stock market unification API] Get company name: {symbol} -> {api_name}")
                        return api_name

            except Exception as e:
                logger.debug(f"📊 [Hong Kong stocks API] API Failed to obtain: {e}")
            
            # Option 3: Generate friendly default names
            clean_symbol = self._normalize_hk_symbol(symbol)
            default_name = f"港股{clean_symbol}"
            
            # Cache default results (shorter TTL)
            self.cache[cache_key] = {
                'data': default_name,
                'timestamp': time.time() - self.cache_ttl + 3600,  # 1 Expires in hours
                'source': 'default'
            }
            self._save_cache()
            
            logger.debug(f"📊 [Hong Kong stocks default] Use default name: {symbol} -> {default_name}")
            return default_name
            
        except Exception as e:
            logger.error(f"❌ [Hong Kong stocks] Failed to get company name: {e}")
            clean_symbol = self._normalize_hk_symbol(symbol)
            return f"港股{clean_symbol}"
    
    def get_daily_data(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        Get daily data of Hong Kong stocks DataFrame

        Args:
            symbol: Hong Kong stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)

        Returns:
            pd.DataFrame: contains date, open, high, low, close, volume equal columns DataFrame
        """
        try:
            import akshare as ak
            from datetime import datetime, timedelta

            # standardized code
            normalized_symbol = self._normalize_hk_symbol(symbol)

            # Set default date
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

            logger.info(f"🔄 [AKShare-Sina] Get historical data of Hong Kong stocks DataFrame: {symbol} ({start_date} ~ {end_date})")

            # Use Sina Finance interface to obtain historical data
            df = ak.stock_hk_daily(symbol=normalized_symbol, adjust="qfq")

            if df is None or df.empty:
                logger.warning(f"⚠️ [AKShare-Sina] Return empty data: {symbol}")
                return pd.DataFrame()

            # Filter date range
            df['date'] = pd.to_datetime(df['date'])
            # Make sure start_date and end_date are datetime objects
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            mask = (df['date'] >= start_dt) & (df['date'] <= end_dt)
            df = df.loc[mask]

            if df.empty:
                logger.warning(f"⚠️ [AKShare-Sina] No data in date range: {symbol}")
                return pd.DataFrame()
            
            # Standardize column names to match unified interface
            # AKShare Return: date, open, high, low, close, volume, amount
            df = df.rename(columns={
                'date': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
                'amount': 'amount'
            })

            # Make sure the date column is in string format (YYYY-MM-DD)
            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            
            return df

        except Exception as e:
            logger.error(f"❌ [Hong Kong stocks] Failed to obtain daily data: {symbol} - {e}")
            return pd.DataFrame()

    def get_financial_indicators(self, symbol: str) -> Dict[str, Any]:
        """
        Get Hong Kong stock financial indicators

        Use AKShare s stock_financial_hk_analysis_indicator_em interface
        Get key financial metrics including EPS, BPS, ROE, ROA and more

        Args:
            symbol: Hong Kong stock code

        Returns:
            Dict: financial indicator data
        """
        try:
            import akshare as ak

            # standardized code
            normalized_symbol = self._normalize_hk_symbol(symbol)

            # Check cache
            cache_key = f"financial_{normalized_symbol}"
            if self._is_cache_valid(cache_key):
                logger.debug(f"📊 [Hong Kong stock financial indicators] Use caching: {normalized_symbol}")
                return self.cache[cache_key]['data']

            # rate limit
            self._rate_limit()

            logger.info(f"📊 [Hong Kong stock financial indicators] Get financial metrics: {normalized_symbol}")

            # Call AKShare interface
            df = ak.stock_financial_hk_analysis_indicator_em(symbol=normalized_symbol)

            if df is None or df.empty:
                logger.warning(f"⚠️ [Hong Kong stock financial indicators] No data obtained: {normalized_symbol}")
                return {}

            # Get the latest data
            latest = df.iloc[0]

            # Extract key indicators
            indicators = {
                # Basic information
                'report_date': str(latest.get('REPORT_DATE', '')),
                'fiscal_year': str(latest.get('FISCAL_YEAR', '')),

                # per share indicator
                'eps_basic': float(latest.get('BASIC_EPS', 0)) if pd.notna(latest.get('BASIC_EPS')) else None,
                'eps_diluted': float(latest.get('DILUTED_EPS', 0)) if pd.notna(latest.get('DILUTED_EPS')) else None,
                'eps_ttm': float(latest.get('EPS_TTM', 0)) if pd.notna(latest.get('EPS_TTM')) else None,
                'bps': float(latest.get('BPS', 0)) if pd.notna(latest.get('BPS')) else None,
                'per_netcash_operate': float(latest.get('PER_NETCASH_OPERATE', 0)) if pd.notna(latest.get('PER_NETCASH_OPERATE')) else None,

                # profitability indicator
                'roe_avg': float(latest.get('ROE_AVG', 0)) if pd.notna(latest.get('ROE_AVG')) else None,
                'roe_yearly': float(latest.get('ROE_YEARLY', 0)) if pd.notna(latest.get('ROE_YEARLY')) else None,
                'roa': float(latest.get('ROA', 0)) if pd.notna(latest.get('ROA')) else None,
                'roic_yearly': float(latest.get('ROIC_YEARLY', 0)) if pd.notna(latest.get('ROIC_YEARLY')) else None,
                'net_profit_ratio': float(latest.get('NET_PROFIT_RATIO', 0)) if pd.notna(latest.get('NET_PROFIT_RATIO')) else None,
                'gross_profit_ratio': float(latest.get('GROSS_PROFIT_RATIO', 0)) if pd.notna(latest.get('GROSS_PROFIT_RATIO')) else None,

                # revenue metrics
                'operate_income': float(latest.get('OPERATE_INCOME', 0)) if pd.notna(latest.get('OPERATE_INCOME')) else None,
                'operate_income_yoy': float(latest.get('OPERATE_INCOME_YOY', 0)) if pd.notna(latest.get('OPERATE_INCOME_YOY')) else None,
                'operate_income_qoq': float(latest.get('OPERATE_INCOME_QOQ', 0)) if pd.notna(latest.get('OPERATE_INCOME_QOQ')) else None,
                'gross_profit': float(latest.get('GROSS_PROFIT', 0)) if pd.notna(latest.get('GROSS_PROFIT')) else None,
                'gross_profit_yoy': float(latest.get('GROSS_PROFIT_YOY', 0)) if pd.notna(latest.get('GROSS_PROFIT_YOY')) else None,
                'holder_profit': float(latest.get('HOLDER_PROFIT', 0)) if pd.notna(latest.get('HOLDER_PROFIT')) else None,
                'holder_profit_yoy': float(latest.get('HOLDER_PROFIT_YOY', 0)) if pd.notna(latest.get('HOLDER_PROFIT_YOY')) else None,

                # Solvency Index
                'debt_asset_ratio': float(latest.get('DEBT_ASSET_RATIO', 0)) if pd.notna(latest.get('DEBT_ASSET_RATIO')) else None,
                'current_ratio': float(latest.get('CURRENT_RATIO', 0)) if pd.notna(latest.get('CURRENT_RATIO')) else None,

                # cash flow indicator
                'ocf_sales': float(latest.get('OCF_SALES', 0)) if pd.notna(latest.get('OCF_SALES')) else None,

                # data source
                'source': 'akshare_eastmoney',
                'data_count': len(df)
            }

            # cache data
            self.cache[cache_key] = {
                'data': indicators,
                'timestamp': time.time()
            }
            self._save_cache()

            logger.info(f"✅ [港股财务指标] 成功获取: {normalized_symbol}, 报告期: {indicators['report_date']}")
            return indicators

        except Exception as e:
            logger.error(f"❌ [Hong Kong stock financial indicators] Failed to obtain: {symbol} - {e}")
            return {}

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get basic information about Hong Kong stocks

        Args:
            symbol: Hong Kong stock code

        Returns:
            Dict: Hong Kong stock information
        """
        try:
            company_name = self.get_company_name(symbol)

            return {
                'symbol': symbol,
                'name': company_name,
                'currency': 'HKD',
                'exchange': 'HKG',
                'market': '港股',
                'source': 'improved_hk_provider'
            }
            
        except Exception as e:
            logger.error(f"❌ [Hong Kong stocks] Failed to obtain stock information: {e}")
            clean_symbol = self._normalize_hk_symbol(symbol)
            return {
                'symbol': symbol,
                'name': f'港股{clean_symbol}',
                'currency': 'HKD',
                'exchange': 'HKG',
                'market': '港股',
                'source': 'error',
                'error': str(e)
            }


# global instance
_improved_hk_provider = None

def get_improved_hk_provider() -> ImprovedHKStockProvider:
    """获取改进的港股提供器实例"""
    global _improved_hk_provider
    if _improved_hk_provider is None:
        _improved_hk_provider = ImprovedHKStockProvider()
    return _improved_hk_provider


def get_hk_company_name_improved(symbol: str) -> str:
    """
    Get an improved version of Hong Kong stock company name
    
    Args:
        symbol: Hong Kong stock code
        
    Returns:
        str: Company name
    """
    provider = get_improved_hk_provider()
    return provider.get_company_name(symbol)


def get_hk_stock_info_improved(symbol: str) -> Dict[str, Any]:
    """
    Get an improved version of Hong Kong stock information

    Args:
        symbol: Hong Kong stock code

    Returns:
        Dict: Hong Kong stock information
    """
    provider = get_improved_hk_provider()
    return provider.get_stock_info(symbol)


def get_hk_financial_indicators(symbol: str) -> Dict[str, Any]:
    """
    Get Hong Kong stock financial indicators

    Args:
        symbol: Hong Kong stock code

    Returns:
        Dict: Financial indicator data, including:
            - eps_basic: basic earnings per share
            - eps_ttm: rolling EPS
            - bps: Net assets per share
            - roe_avg: average return on equity
            - roa: return on total assets
            - operate_income: operating income
            - operate_income_yoy: Operating income year-on-year growth rate
            - debt_asset_ratio: Asset-liability ratio
            Wait
    """
    provider = get_improved_hk_provider()
    return provider.get_financial_indicators(symbol)


# Compatibility functions: imported for compatibility with old akshare_utils
def get_hk_stock_data_akshare(symbol: str, start_date: str = None, end_date: str = None):
    """
    Compatibility function: Use AKShare Sina Finance interface to obtain historical data of Hong Kong stocks

    Args:
        symbol: Hong Kong stock code
        start_date: start date
        end_date: end date

    Returns:
        Hong Kong stock data (formatted string)
    """
    try:
        import pandas as pd
        from datetime import datetime, timedelta

        # Get provider instance
        provider = get_improved_hk_provider()
        
        # Use get_daily_data to get data
        df = provider.get_daily_data(symbol, start_date, end_date)

        if df is None or df.empty:
            logger.warning(f"⚠️ [AKShare-Sina] Return empty data: {symbol}")
            return f"❌ 无法获取港股{symbol}的历史数据"

        # 🔥 Add pre_close field (taken from previous day's close)
        # AKShare The pre_close field is not returned and needs to be calculated manually.
        df['pre_close'] = df['close'].shift(1)

        # Calculate the increase and decrease amount and the increase and decrease margin
        df['change'] = df['close'] - df['pre_close']
        df['pct_change'] = (df['change'] / df['pre_close'] * 100).round(2)

        # 🔥 Use unified technical indicator calculation functions
        from tradingagents.tools.analysis.indicators import add_all_indicators
        df = add_all_indicators(df, close_col='close', high_col='high', low_col='low')

        # 🔥 Get financial metrics and calculate PE,PB
        financial_indicators = provider.get_financial_indicators(symbol)

        # Formatted output (contains price data and technical indicators)
        latest = df.iloc[-1]
        current_price = latest['close']

        # Calculate PE,PB
        pe_ratio = None
        pb_ratio = None
        financial_section = ""

        if financial_indicators:
            eps_ttm = financial_indicators.get('eps_ttm')
            bps = financial_indicators.get('bps')

            if eps_ttm and eps_ttm > 0:
                pe_ratio = current_price / eps_ttm

            if bps and bps > 0:
                pb_ratio = current_price / bps

            # Build the financial metrics section (handle None values)
            def format_value(value, format_str=".2f", suffix="", default="N/A"):
                """Format values, handle None case"""
                if value is None:
                    return default
                try:
                    return f"{value:{format_str}}{suffix}"
                except:
                    return default

            financial_section = f"""
### 财务指标（最新报告期：{financial_indicators.get('report_date', 'N/A')}）
**估值指标**:
- PE (市盈率): {f'{pe_ratio:.2f}' if pe_ratio else 'N/A'} (当前价 / EPS_TTM)
- PB (市净率): {f'{pb_ratio:.2f}' if pb_ratio else 'N/A'} (当前价 / BPS)

**每股指标**:
- 基本每股收益 (EPS): HK${format_value(financial_indicators.get('eps_basic'))}
- 滚动每股收益 (EPS_TTM): HK${format_value(financial_indicators.get('eps_ttm'))}
- 每股净资产 (BPS): HK${format_value(financial_indicators.get('bps'))}
- 每股经营现金流: HK${format_value(financial_indicators.get('per_netcash_operate'))}

**盈利能力**:
- 净资产收益率 (ROE): {format_value(financial_indicators.get('roe_avg'), suffix='%')}
- 总资产收益率 (ROA): {format_value(financial_indicators.get('roa'), suffix='%')}
- 净利率: {format_value(financial_indicators.get('net_profit_ratio'), suffix='%')}
- 毛利率: {format_value(financial_indicators.get('gross_profit_ratio'), suffix='%')}

**营收情况**:
- 营业收入: {format_value(financial_indicators.get('operate_income') / 1e8 if financial_indicators.get('operate_income') else None, suffix=' 亿港元')}
- 营收同比增长: {format_value(financial_indicators.get('operate_income_yoy'), suffix='%')}
- 归母净利润: {format_value(financial_indicators.get('holder_profit') / 1e8 if financial_indicators.get('holder_profit') else None, suffix=' 亿港元')}
- 净利润同比增长: {format_value(financial_indicators.get('holder_profit_yoy'), suffix='%')}

**偿债能力**:
- 资产负债率: {format_value(financial_indicators.get('debt_asset_ratio'), suffix='%')}
- 流动比率: {format_value(financial_indicators.get('current_ratio'))}
"""

        result = f"""## 港股历史数据 ({symbol})
**数据源**: AKShare (新浪财经)
**日期范围**: {start_date} ~ {end_date}
**数据条数**: {len(df)} 条

### 最新价格信息
- 最新价: HK${latest['close']:.2f}
- 昨收: HK${latest['pre_close']:.2f}
- 涨跌额: HK${latest['change']:.2f}
- 涨跌幅: {latest['pct_change']:.2f}%
- 最高: HK${latest['high']:.2f}
- 最低: HK${latest['low']:.2f}
- 成交量: {latest['volume']:,.0f}

### 技术指标（最新值）
**移动平均线**:
- MA5: HK${latest['ma5']:.2f}
- MA10: HK${latest['ma10']:.2f}
- MA20: HK${latest['ma20']:.2f}
- MA60: HK${latest['ma60']:.2f}

**MACD指标**:
- DIF: {latest['macd_dif']:.2f}
- DEA: {latest['macd_dea']:.2f}
- MACD: {latest['macd']:.2f}

**RSI指标**:
- RSI(14): {latest['rsi']:.2f}

**布林带**:
- 上轨: HK${latest['boll_upper']:.2f}
- 中轨: HK${latest['boll_mid']:.2f}
- 下轨: HK${latest['boll_lower']:.2f}
{financial_section}
### 最近10个交易日价格
{df[['date', 'open', 'high', 'low', 'close', 'pre_close', 'change', 'pct_change', 'volume']].tail(10).to_string(index=False)}

### 数据统计
- 最高价: HK${df['high'].max():.2f}
- 最低价: HK${df['low'].min():.2f}
- 平均收盘价: HK${df['close'].mean():.2f}
- 总成交量: {df['volume'].sum():,.0f}
"""

        logger.info(f"✅ [AKShare-新浪] 港股历史数据获取成功: {symbol} ({len(df)}条)")
        return result

    except Exception as e:
        logger.error(f"❌ [AKShare-Sina] Failed to obtain historical data of Hong Kong stocks: {symbol} - {e}")
        return f"❌ 港股{symbol}历史数据获取失败: {str(e)}"


# 🔥 Global cache: cache all Hong Kong stock data of AKShare
_akshare_hk_spot_cache = {
    'data': None,
    'timestamp': None,
    'ttl': 600  # Cache for 10 minutes (refer to the cache duration of real-time U.S. stock market quotes)
}

# 🔥 Asynchronous lock: prevent multiple asynchronous tasks from being called at the same time AKShare API
# Note: The synchronized function get_hk_stock_info_akshare still uses the thread lock, but will be called in the thread pool
import threading
import asyncio
_akshare_hk_spot_lock = threading.Lock()  # for synchronous functions
_akshare_hk_spot_async_lock = None  # Lazy initialization of asynchronous locks

def _get_async_lock():
    """获取异步锁（延迟初始化）"""
    global _akshare_hk_spot_async_lock
    if _akshare_hk_spot_async_lock is None:
        _akshare_hk_spot_async_lock = asyncio.Lock()
    return _akshare_hk_spot_async_lock


async def get_hk_stock_info_akshare_async(symbol: str) -> Dict[str, Any]:
    """
    Asynchronous version: directly use akshare to obtain Hong Kong stock information (avoiding circular calls)
    🔥 Use global cache + Asynchronous lock to avoid repeated calls ak.stock_hk_spot()
    🔥 Execute synchronous AKShare calls in the thread pool to avoid blocking the event loop

    Args:
        symbol: Hong Kong stock code

    Returns:
        Dict: Hong Kong stock information
    """
    try:
        import akshare as ak
        from datetime import datetime

        # standardized code
        provider = get_improved_hk_provider()
        normalized_symbol = provider._normalize_hk_symbol(symbol)

        # Try getting real-time quotes from akshare
        try:
            # 🔥 Use asynchronous locks to protect AKShare API calls (to prevent concurrency leading to bans)
            # Strategy:
            # 1. Use async lock (wait up to 10 seconds)
            # 2. After acquiring the lock, first check whether the cache has been updated by other tasks
            # 3. If the cache is valid, use it directly; otherwise, call it in the thread pool API

            async_lock = _get_async_lock()
            
            try:
                # Try to acquire an asynchronous lock, wait up to 10 seconds
                await asyncio.wait_for(async_lock.acquire(), timeout=10.0)
                logger.info(f"✅ [AKShare Asynchronous lock] Lock acquired")
            except asyncio.TimeoutError:
                # Timeout, return error
                logger.error(f"⏰ [AKShare Asynchronous lock] Timeout for acquiring lock (10 seconds), give up")
                raise Exception("AKShare API Call timeout (occupied by other tasks)")

            try:
                # After acquiring the lock, check whether the cache has been updated by other tasks
                now = datetime.now()
                cache = _akshare_hk_spot_cache

                if cache['data'] is not None and cache['timestamp'] is not None:
                    elapsed = (now - cache['timestamp']).total_seconds()
                    if elapsed <= cache['ttl']:
                        # The cache is valid (maybe it was just updated by other tasks)
                        logger.info(f"⚡ [AKShare Caching-Async] Use cached data ({elapsed:.1f}seconds ago, may be updated by other tasks)")
                        df = cache['data']
                    else:
                        # The cache expires and the API needs to be called (executed in the thread pool to avoid blocking)
                        logger.info(f"🔄 [AKShare Caching-Async] Cache Expiration ({elapsed:.1f}seconds ago), call the API refresh in the thread pool")
                        # 🔥 Execute synchronous AKShare calls in the thread pool to avoid blocking the event loop
                        df = await asyncio.wait_for(
                            asyncio.to_thread(ak.stock_hk_spot),
                            timeout=30.0  # 30 seconds timeout
                        )
                        cache['data'] = df
                        cache['timestamp'] = now
                        logger.info(f"✅ [AKShare缓存-异步] 已缓存 {len(df)} 只港股数据")
                else:
                    # Cache is empty, first call (executed in thread pool)
                    logger.info(f"🔄 [AKShare Caching-Async] Obtain Hong Kong stock data for the first time (executed in the thread pool)")
                    df = await asyncio.wait_for(
                        asyncio.to_thread(ak.stock_hk_spot),
                        timeout=30.0  # 30 seconds timeout
                    )
                    cache['data'] = df
                    cache['timestamp'] = now
                    logger.info(f"✅ [AKShare缓存-异步] 已缓存 {len(df)} 只港股数据")

            finally:
                # Release asynchronous lock
                async_lock.release()
                logger.info(f"🔓 [AKShare Asynchronous lock] Lock released")

            # Find target stocks from cached data
            if df is not None and not df.empty:
                matched = df[df['代码'] == normalized_symbol]
                if not matched.empty:
                    row = matched.iloc[0]

                    # Helper Functions: Convert Numeric Values Safely
                    def safe_float(value):
                        try:
                            if value is None or value == '' or (isinstance(value, float) and value != value):  # NaN check
                                return None
                            return float(value)
                        except:
                            return None

                    def safe_int(value):
                        try:
                            if value is None or value == '' or (isinstance(value, float) and value != value):  # NaN check
                                return None
                            return int(value)
                        except:
                            return None

                    return {
                        'symbol': symbol,
                        'name': row['中文名称'],  # List of Sina interfaces
                        'price': safe_float(row.get('最新价')),
                        'open': safe_float(row.get('今开')),
                        'high': safe_float(row.get('最高')),
                        'low': safe_float(row.get('最低')),
                        'volume': safe_int(row.get('成交量')),
                        'change_percent': safe_float(row.get('涨跌幅')),
                        'currency': 'HKD',
                        'exchange': 'HKG',
                        'market': '港股',
                        'source': 'akshare_sina'
                    }
        except Exception as e:
            logger.debug(f"📊 [Hong Kong stocks AKShare-Sina-Asynchronous] Failed to obtain: {e}")

        # If failed, return basic information
        return {
            'symbol': symbol,
            'name': f'港股{normalized_symbol}',
            'currency': 'HKD',
            'exchange': 'HKG',
            'market': '港股',
            'source': 'akshare_fallback'
        }

    except Exception as e:
        logger.error(f"❌ [Hong Kong stocks AKShare-Sina-Asynchronous] Failed to obtain information: {e}")
        return {
            'symbol': symbol,
            'name': f'港股{symbol}',
            'currency': 'HKD',
            'exchange': 'HKG',
            'market': '港股',
            'source': 'error',
            'error': str(e)
        }


def get_hk_stock_info_akshare(symbol: str) -> Dict[str, Any]:
    """
    Synchronous version: directly use akshare to obtain Hong Kong stock information (avoiding circular calls)
    🔥 Use global cache + Thread lock to avoid repeated calls ak.stock_hk_spot()
    ⚠️ Note: This function is synchronous, if called in an asynchronous environment, you should use get_hk_stock_info_akshare_async

    Args:
        symbol: Hong Kong stock code

    Returns:
        Dict: Hong Kong stock information
    """
    try:
        import akshare as ak
        from datetime import datetime

        # standardized code
        provider = get_improved_hk_provider()
        normalized_symbol = provider._normalize_hk_symbol(symbol)

        # Try getting real-time quotes from akshare
        try:
            # 🔥 Use a mutex to protect AKShare API calls (to prevent concurrency leading to bans)
            # Strategy:
            # 1. Try to acquire the lock (wait up to 10 seconds to reduce blocking time)
            # 2. After acquiring the lock, first check whether the cache has been updated by other threads
            # 3. If the cache is valid, use it directly; otherwise call API

            thread_id = threading.current_thread().name
            logger.info(f"🔒 [AKShare锁-{thread_id}] 尝试获取锁...")

            # Try to acquire the lock, wait up to 10 seconds (reduce blocking time)
            lock_acquired = _akshare_hk_spot_lock.acquire(timeout=10)

            if not lock_acquired:
                # Timeout, return error
                logger.error(f"⏰ [AKShare锁-{thread_id}] 获取锁超时（10秒），放弃")
                raise Exception("AKShare API Call timeout (occupied by other threads)")

            try:
                logger.info(f"✅ [AKShare锁-{thread_id}] 已获取锁")

                # After acquiring the lock, check whether the cache has been updated by other threads
                now = datetime.now()
                cache = _akshare_hk_spot_cache

                if cache['data'] is not None and cache['timestamp'] is not None:
                    elapsed = (now - cache['timestamp']).total_seconds()
                    if elapsed <= cache['ttl']:
                        # The cache is valid (maybe it was just updated by other threads)
                        logger.info(f"⚡ [AKShare缓存-{thread_id}] 使用缓存数据（{elapsed:.1f}秒前，可能由其他线程更新）")
                        df = cache['data']
                    else:
                        # The cache has expired and needs to be called API
                        logger.info(f"🔄 [AKShare缓存-{thread_id}] 缓存过期（{elapsed:.1f}秒前），调用 API 刷新")
                        df = ak.stock_hk_spot()
                        cache['data'] = df
                        cache['timestamp'] = now
                        logger.info(f"✅ [AKShare缓存-{thread_id}] 已缓存 {len(df)} 只港股数据")
                else:
                    # Cache is empty, first call
                    logger.info(f"🔄 [AKShare缓存-{thread_id}] 首次获取港股数据")
                    df = ak.stock_hk_spot()
                    cache['data'] = df
                    cache['timestamp'] = now
                    logger.info(f"✅ [AKShare缓存-{thread_id}] 已缓存 {len(df)} 只港股数据")

            finally:
                # release lock
                _akshare_hk_spot_lock.release()
                logger.info(f"🔓 [AKShare锁-{thread_id}] 已释放锁")

            # Find target stocks from cached data
            if df is not None and not df.empty:
                matched = df[df['代码'] == normalized_symbol]
                if not matched.empty:
                    row = matched.iloc[0]

                    # Helper Functions: Convert Numeric Values Safely
                    def safe_float(value):
                        try:
                            if value is None or value == '' or (isinstance(value, float) and value != value):  # NaN check
                                return None
                            return float(value)
                        except:
                            return None

                    def safe_int(value):
                        try:
                            if value is None or value == '' or (isinstance(value, float) and value != value):  # NaN check
                                return None
                            return int(value)
                        except:
                            return None

                    return {
                        'symbol': symbol,
                        'name': row['中文名称'],  # List of Sina interfaces
                        'price': safe_float(row.get('最新价')),
                        'open': safe_float(row.get('今开')),
                        'high': safe_float(row.get('最高')),
                        'low': safe_float(row.get('最低')),
                        'volume': safe_int(row.get('成交量')),
                        'change_percent': safe_float(row.get('涨跌幅')),
                        'currency': 'HKD',
                        'exchange': 'HKG',
                        'market': '港股',
                        'source': 'akshare_sina'
                    }
        except Exception as e:
            logger.debug(f"📊 [Hong Kong stocks AKShare-Sina] Failed to obtain: {e}")

        # If failed, return basic information
        return {
            'symbol': symbol,
            'name': f'港股{normalized_symbol}',
            'currency': 'HKD',
            'exchange': 'HKG',
            'market': '港股',
            'source': 'akshare_fallback'
        }

    except Exception as e:
        logger.error(f"❌ [Hong Kong stocks AKShare-Sina] Failed to obtain information: {e}")
        return {
            'symbol': symbol,
            'name': f'港股{symbol}',
            'currency': 'HKD',
            'exchange': 'HKG',
            'market': '港股',
            'source': 'error',
            'error': str(e)
        }
