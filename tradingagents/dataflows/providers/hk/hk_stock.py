"""
Hong Kong stock data acquisition tool
Provides the acquisition, processing and caching functions of Hong Kong stock data
"""

import pandas as pd
import numpy as np
import yfinance as yf
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tradingagents.config.runtime_settings import get_timezone_name
import requests
import os

import os

from tradingagents.config.runtime_settings import get_float, get_int
# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')



class HKStockProvider:
    """港股数据提供器"""

    def __init__(self):
        """初始化港股数据提供器"""
        self.last_request_time = 0
        self.min_request_interval = get_float("TA_HK_MIN_REQUEST_INTERVAL_SECONDS", "ta_hk_min_request_interval_seconds", 2.0)
        self.timeout = get_int("TA_HK_TIMEOUT_SECONDS", "ta_hk_timeout_seconds", 60)
        self.max_retries = get_int("TA_HK_MAX_RETRIES", "ta_hk_max_retries", 3)
        self.rate_limit_wait = get_int("TA_HK_RATE_LIMIT_WAIT_SECONDS", "ta_hk_rate_limit_wait_seconds", 60)

        # Build a session with proxy and UA, make sure yfinance uses proxy
        self.session = self._create_session()

        logger.info(f"🇭🇰 Hong Kong stock data provider initialization completed")

    def _create_session(self) -> requests.Session:
        """Create requests.Session with proxy and UA for reuse by yfinance"""
        try:
            session = requests.Session()

            # Agent: Prioritize reading environment variables (set uniformly by the backend)
            http_proxy = os.environ.get('HTTP_PROXY', '')
            https_proxy = os.environ.get('HTTPS_PROXY', '')
            proxies: Dict[str, str] = {}
            if http_proxy:
                proxies['http'] = http_proxy
            if https_proxy:
                proxies['https'] = https_proxy
            if proxies:
                session.proxies.update(proxies)
                logger.info(f"🌐 Use proxy access Yahoo Finance: {proxies}")
            else:
                logger.info("🌐 No proxy configured, direct access Yahoo Finance")

            # UA: Allows overriding through environment variables, uses common browser UAs by default and identifies the application
            ua = os.environ.get('TA_HTTP_USER_AGENT', '').strip() or (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/121.0 Safari/537.36 TradingAgentsCN/1.0'
            )
            session.headers.update({'User-Agent': ua})
            logger.info(f"🪪 使用UA: {ua}")
            return session
        except Exception as e:
            logger.warning(f"⚠️ Failed to create proxy session, using default session: {e}")
            return requests.Session()

    def _wait_for_rate_limit(self):
        """等待速率限制"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def get_stock_data(self, symbol: str, start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """
        Get historical data of Hong Kong stocks

        Args:
            symbol: Hong Kong stock code (Such as: 0700.HK)
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)

        Returns:
            DataFrame: Stock historical data
        """
        try:
            # Standardized Hong Kong Stock Code
            symbol = self._normalize_hk_symbol(symbol)

            # Set default date
            if not end_date:
                end_date = datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d')
            if not start_date:
                start_date = (datetime.now(ZoneInfo(get_timezone_name())) - timedelta(days=365)).strftime('%Y-%m-%d')

            logger.info(f"🇭🇰 获取港股数据: {symbol} ({start_date} 到 {end_date})")

            # Retry multiple times to get data
            for attempt in range(self.max_retries):
                try:
                    self._wait_for_rate_limit()

                    # Use yfinance to get data (without passing session parameter)
                    ticker = yf.Ticker(symbol)
                    data = ticker.history(
                        start=start_date,
                        end=end_date,
                        timeout=self.timeout
                    )

                    if not data.empty:
                        # Data preprocessing
                        data = data.reset_index()
                        data['Symbol'] = symbol

                        logger.info(f"✅ 港股数据获取成功: {symbol}, {len(data)}条记录")
                        return data
                    else:
                        logger.warning(f"⚠️ 港股数据为空: {symbol} (尝试 {attempt + 1}/{self.max_retries})")

                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ Failed to obtain Hong Kong stock data (try {attempt + 1}/{self.max_retries}): {error_msg}")

                    # Check if it is a frequency limit error
                    if "Rate limited" in error_msg or "Too Many Requests" in error_msg:
                        if attempt < self.max_retries - 1:
                            logger.info(f"⏳ 检测到频率限制，等待{self.rate_limit_wait}秒...")
                            time.sleep(self.rate_limit_wait)
                        else:
                            logger.error(f"❌ Frequency limit, skip retries")
                            break
                    else:
                        if attempt < self.max_retries - 1:
                            time.sleep(2 ** attempt)  # exponential backoff

            logger.error(f"❌ Obtaining Hong Kong stock data ultimately failed: {symbol}")
            return None

        except Exception as e:
            logger.error(f"❌ 港股数据获取异常: {e}")
            return None

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get basic information about Hong Kong stocks

        Args:
            symbol: Hong Kong stock code

        Returns:
            Dict: Basic stock information
        """
        try:
            symbol = self._normalize_hk_symbol(symbol)

            logger.info(f"🇭🇰 获取港股信息: {symbol}")

            self._wait_for_rate_limit()

            # Do not pass session parameters and let yfinance handle it by itself
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if info and 'symbol' in info:
                return {
                    'symbol': symbol,
                    'name': info.get('longName', info.get('shortName', f'港股{symbol}')),
                    'currency': info.get('currency', 'HKD'),
                    'exchange': info.get('exchange', 'HKG'),
                    'market_cap': info.get('marketCap'),
                    'sector': info.get('sector'),
                    'industry': info.get('industry'),
                    'source': 'yfinance_hk'
                }
            else:
                return {
                    'symbol': symbol,
                    'name': f'港股{symbol}',
                    'currency': 'HKD',
                    'exchange': 'HKG',
                    'source': 'yfinance_hk'
                }

        except Exception as e:
            logger.error(f"❌ 获取港股信息失败: {e}")
            return {
                'symbol': symbol,
                'name': f'港股{symbol}',
                'currency': 'HKD',
                'exchange': 'HKG',
                'source': 'unknown',
                'error': str(e)
            }

    def get_real_time_price(self, symbol: str) -> Optional[Dict]:
        """
        Get real-time prices of Hong Kong stocks

        Args:
            symbol: Hong Kong stock code

        Returns:
            Dict: Real-time price information (including stock name)
        """
        try:
            symbol = self._normalize_hk_symbol(symbol)

            self._wait_for_rate_limit()

            # Do not pass session parameters and let yfinance handle it by itself (new version of yfinance requires curl_cffi)
            ticker = yf.Ticker(symbol)

            # Get the latest historical data (1 day)
            data = ticker.history(period="1d", timeout=self.timeout)

            if not data.empty:
                latest = data.iloc[-1]

                # Try to get the stock name (from ticker.info)
                stock_name = f'港股{symbol}'
                try:
                    info = ticker.info
                    if info and 'longName' in info:
                        stock_name = info.get('longName', info.get('shortName', stock_name))
                except Exception:
                    # Fails silently, using default name
                    pass

                return {
                    'symbol': symbol,
                    'name': stock_name,  # Add stock name
                    'price': latest['Close'],
                    'open': latest['Open'],
                    'high': latest['High'],
                    'low': latest['Low'],
                    'volume': latest['Volume'],
                    'timestamp': data.index[-1].strftime('%Y-%m-%d %H:%M:%S'),
                    'currency': 'HKD'
                }
            else:
                return None

        except Exception as e:
            logger.error(f"❌ Failed to obtain real-time price of Hong Kong stocks: {e}")
            return None

    def _normalize_hk_symbol(self, symbol: str) -> str:
        """
        Standardized Hong Kong stock code format

        Yahoo Finance Expected format: 0700.HK (4 digits)
        Possible input formats:00700, 700, 0700, 0700.HK, 00700.HK

        Args:
            symbol: Original Hong Kong stock code

        Returns:
            str: Standardized Hong Kong stock code (format: 0700.HK)
        """
        if not symbol:
            return symbol

        symbol = str(symbol).strip().upper()

        # If there is already a .HK suffix, remove it first
        if symbol.endswith('.HK'):
            symbol = symbol[:-3]

        # If it is a pure number, normalize to 4 digits
        if symbol.isdigit():
            # Remove leading 0s, then pad to 4 digits
            clean_code = symbol.lstrip('0') or '0'  # If all are 0, keep one 0
            normalized_code = clean_code.zfill(4)
            return f"{normalized_code}.HK"

        return symbol

    def format_stock_data(self, symbol: str, data: pd.DataFrame, start_date: str, end_date: str) -> str:
        """
        Format Hong Kong stock data into text format (including technical indicators)

        Args:
            symbol: Stock code
            data: stock data DataFrame
            start_date: start date
            end_date: end date

        Returns:
            str: Formatted stock data text (contains technical indicators)
        """
        if data is None or data.empty:
            return f"❌ 无法获取港股 {symbol} 的数据"

        try:
            original_data_count = len(data)
            logger.info(f"📊 [港股技术指标] 开始计算技术指标，原始数据: {original_data_count}条")

            # Get basic stock information
            stock_info = self.get_stock_info(symbol)
            stock_name = stock_info.get('name', f'港股{symbol}')

            # Make sure the data is sorted by date
            if 'Date' in data.columns:
                data = data.sort_values('Date')
            else:
                data = data.sort_index()

            # Calculate moving average
            data['ma5'] = data['Close'].rolling(window=5, min_periods=1).mean()
            data['ma10'] = data['Close'].rolling(window=10, min_periods=1).mean()
            data['ma20'] = data['Close'].rolling(window=20, min_periods=1).mean()
            data['ma60'] = data['Close'].rolling(window=60, min_periods=1).mean()

            # Calculate RSI (Relative Strength Index)
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
            rs = gain / (loss.replace(0, np.nan))
            data['rsi'] = 100 - (100 / (1 + rs))

            # Calculate MACD
            ema12 = data['Close'].ewm(span=12, adjust=False).mean()
            ema26 = data['Close'].ewm(span=26, adjust=False).mean()
            data['macd_dif'] = ema12 - ema26
            data['macd_dea'] = data['macd_dif'].ewm(span=9, adjust=False).mean()
            data['macd'] = (data['macd_dif'] - data['macd_dea']) * 2

            # Calculate Bollinger Bands
            data['boll_mid'] = data['Close'].rolling(window=20, min_periods=1).mean()
            std = data['Close'].rolling(window=20, min_periods=1).std()
            data['boll_upper'] = data['boll_mid'] + 2 * std
            data['boll_lower'] = data['boll_mid'] - 2 * std

            # Only retain the last 3-5 days of data for display (reduce token consumption)
            display_rows = min(5, len(data))
            display_data = data.tail(display_rows)
            latest_data = data.iloc[-1]

            # 🔍 [debug log] Print raw data and technical indicators for the last 5 days
            logger.info(f"🔍 [港股技术指标详情] ===== 最近{display_rows}个交易日数据 =====")
            for i, (idx, row) in enumerate(display_data.iterrows(), 1):
                date_str = row.get('Date', idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx))
                logger.info(f"🔍 [港股技术指标详情] 第{i}天 ({date_str}):")
                logger.info(f"   价格: 开={row.get('Open', 0):.2f}, 高={row.get('High', 0):.2f}, 低={row.get('Low', 0):.2f}, 收={row.get('Close', 0):.2f}")
                logger.info(f"   MA: MA5={row.get('ma5', 0):.2f}, MA10={row.get('ma10', 0):.2f}, MA20={row.get('ma20', 0):.2f}, MA60={row.get('ma60', 0):.2f}")
                logger.info(f"   MACD: DIF={row.get('macd_dif', 0):.4f}, DEA={row.get('macd_dea', 0):.4f}, MACD={row.get('macd', 0):.4f}")
                logger.info(f"   RSI: {row.get('rsi', 0):.2f}")
                logger.info(f"   BOLL: 上={row.get('boll_upper', 0):.2f}, 中={row.get('boll_mid', 0):.2f}, 下={row.get('boll_lower', 0):.2f}")

            logger.info(f"🔍 [Details of Hong Kong stock technical indicators] ===== end of data details =====")

            # Formatted output contains all technical indicators and interpretations
            result = f"📊 {stock_name}({symbol}) - 港股技术分析数据\n"
            result += "=" * 60 + "\n\n"

            # Basic information
            result += "📈 基本信息\n"
            result += f"   代码: {symbol}\n"
            result += f"   名称: {stock_name}\n"
            result += f"   货币: 港币 (HKD)\n"
            result += f"   exchange: Hong Kong Exchange (HKG)\n"
            result += f"   数据期间: {start_date} 至 {end_date}\n"
            result += f"   交易天数: {len(data)}天\n\n"

            # latest price
            latest_price = latest_data['Close']
            result += "💰 最新价格\n"
            result += f"   收盘价: HK${latest_price:.2f}\n"
            result += f"   开盘价: HK${latest_data['Open']:.2f}\n"
            result += f"   最高价: HK${latest_data['High']:.2f}\n"
            result += f"   最低价: HK${latest_data['Low']:.2f}\n"
            result += f"   成交量: {latest_data['Volume']:,.0f}股\n\n"

            # moving average
            result += "📊 移动平均线 (MA)\n"
            ma5 = latest_data['ma5']
            ma10 = latest_data['ma10']
            ma20 = latest_data['ma20']
            ma60 = latest_data['ma60']

            if not pd.isna(ma5):
                ma5_diff = ((latest_price - ma5) / ma5) * 100
                ma5_pos = "上方" if latest_price > ma5 else "下方"
                result += f"   MA5: HK${ma5:.2f} (价格在MA5{ma5_pos} {abs(ma5_diff):.2f}%)\n"

            if not pd.isna(ma10):
                ma10_diff = ((latest_price - ma10) / ma10) * 100
                ma10_pos = "上方" if latest_price > ma10 else "下方"
                result += f"   MA10: HK${ma10:.2f} (价格在MA10{ma10_pos} {abs(ma10_diff):.2f}%)\n"

            if not pd.isna(ma20):
                ma20_diff = ((latest_price - ma20) / ma20) * 100
                ma20_pos = "上方" if latest_price > ma20 else "下方"
                result += f"   MA20: HK${ma20:.2f} (价格在MA20{ma20_pos} {abs(ma20_diff):.2f}%)\n"

            if not pd.isna(ma60):
                ma60_diff = ((latest_price - ma60) / ma60) * 100
                ma60_pos = "上方" if latest_price > ma60 else "下方"
                result += f"   MA60: HK${ma60:.2f} (价格在MA60{ma60_pos} {abs(ma60_diff):.2f}%)\n"

            # Determine moving average arrangement
            if not pd.isna(ma5) and not pd.isna(ma10) and not pd.isna(ma20):
                if ma5 > ma10 > ma20:
                    result += "   ✅ 均线呈多头排列\n\n"
                elif ma5 < ma10 < ma20:
                    result += "   ⚠️ 均线呈空头排列\n\n"
                else:
                    result += "   ➡️ 均线排列混乱\n\n"
            else:
                result += "\n"

            # MACD indicator
            result += "📉 MACD指标\n"
            macd_dif = latest_data['macd_dif']
            macd_dea = latest_data['macd_dea']
            macd = latest_data['macd']

            if not pd.isna(macd_dif) and not pd.isna(macd_dea):
                result += f"   DIF: {macd_dif:.4f}\n"
                result += f"   DEA: {macd_dea:.4f}\n"
                result += f"   MACD柱: {macd:.4f} ({'多头' if macd > 0 else '空头'})\n"

                # MACD Golden cross/dead cross detection
                if len(data) > 1:
                    prev_dif = data.iloc[-2]['macd_dif']
                    prev_dea = data.iloc[-2]['macd_dea']
                    curr_dif = latest_data['macd_dif']
                    curr_dea = latest_data['macd_dea']

                    if not pd.isna(prev_dif) and not pd.isna(prev_dea):
                        if prev_dif <= prev_dea and curr_dif > curr_dea:
                            result += "   ⚠️ MACD Golden cross signal (DIF crosses DEA)\n\n"
                        elif prev_dif >= prev_dea and curr_dif < curr_dea:
                            result += "   ⚠️ MACD Death cross signal (DIF crosses DEA below)\n\n"
                        else:
                            result += "\n"
                    else:
                        result += "\n"
                else:
                    result += "\n"
            else:
                result += "   Insufficient data to calculate MACD\n\n"

            # RSI indicator
            result += "📊 RSI指标\n"
            rsi = latest_data['rsi']

            if not pd.isna(rsi):
                result += f"   RSI(14): {rsi:.2f}"
                if rsi >= 70:
                    result += " (超买区域)\n\n"
                elif rsi <= 30:
                    result += " (超卖区域)\n\n"
                elif rsi >= 60:
                    result += " (接近超买区域)\n\n"
                elif rsi <= 40:
                    result += " (接近超卖区域)\n\n"
                else:
                    result += " (中性区域)\n\n"
            else:
                result += "   Insufficient data to calculate RSI\n\n"

            # Bollinger Bands
            result += "📐 布林带 (BOLL)\n"
            boll_upper = latest_data['boll_upper']
            boll_mid = latest_data['boll_mid']
            boll_lower = latest_data['boll_lower']

            if not pd.isna(boll_upper) and not pd.isna(boll_mid) and not pd.isna(boll_lower):
                result += f"   上轨: HK${boll_upper:.2f}\n"
                result += f"   中轨: HK${boll_mid:.2f}\n"
                result += f"   下轨: HK${boll_lower:.2f}\n"

                # Calculate the price's position within the Bollinger Bands
                boll_width = boll_upper - boll_lower
                if boll_width > 0:
                    boll_position = ((latest_price - boll_lower) / boll_width) * 100
                    result += f"   价格位置: {boll_position:.1f}%"

                    if boll_position >= 90:
                        result += " (接近上轨)\n\n"
                    elif boll_position <= 10:
                        result += " (接近下轨)\n\n"
                    else:
                        result += "\n\n"
                else:
                    result += "\n"
            else:
                result += "   Insufficient data to calculate Bollinger Bands\n\n"

            # Last trading day data
            result += "📅 最近交易日数据\n"
            for _, row in display_data.iterrows():
                if 'Date' in row:
                    date_str = row['Date'].strftime('%Y-%m-%d')
                else:
                    date_str = row.name.strftime('%Y-%m-%d')

                result += f"   {date_str}: "
                result += f"开盘HK${row['Open']:.2f}, "
                result += f"收盘HK${row['Close']:.2f}, "
                result += f"最高HK${row['High']:.2f}, "
                result += f"最低HK${row['Low']:.2f}, "
                result += f"成交量{row['Volume']:,.0f}\n"

            result += "\n Data source: Yahoo Finance (Hong Kong stocks)\n"

            logger.info(f"✅ [港股技术指标] 技术指标计算完成，展示最后{display_rows}天数据")

            return result

        except Exception as e:
            logger.error(f"❌ 格式化港股数据失败: {e}", exc_info=True)
            return f"❌ 港股数据格式化失败: {symbol}"


# Global provider instance
_hk_provider = None

def get_hk_stock_provider() -> HKStockProvider:
    """获取全局港股提供器实例"""
    global _hk_provider
    if _hk_provider is None:
        _hk_provider = HKStockProvider()
    return _hk_provider


def get_hk_stock_data(symbol: str, start_date: str = None, end_date: str = None) -> str:
    """
    Convenient function to obtain Hong Kong stock data

    Args:
        symbol: Hong Kong stock code
        start_date: start date
        end_date: end date

    Returns:
        str: Formatted Hong Kong stock data
    """
    provider = get_hk_stock_provider()
    data = provider.get_stock_data(symbol, start_date, end_date)
    return provider.format_stock_data(symbol, data, start_date, end_date)


def get_hk_stock_info(symbol: str) -> Dict:
    """
    Convenient function to obtain Hong Kong stock information

    Args:
        symbol: Hong Kong stock code

    Returns:
        Dict: Hong Kong stock information
    """
    provider = get_hk_stock_provider()
    return provider.get_stock_info(symbol)
