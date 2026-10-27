#!/usr/bin/env python3
"""
Optimized A-share data acquisition tool
Integrate caching strategy and Tushare data interface to improve data acquisition efficiency
"""

import os
import time
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from typing import Optional, Dict, Any
from .cache import get_cache
from tradingagents.config.config_manager import config_manager

from tradingagents.config.runtime_settings import get_float, get_timezone_name
# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# Import the MongoDB cache adapter
from .cache.mongodb_cache_adapter import get_mongodb_cache_adapter, get_stock_data_with_fallback, get_financial_data_with_fallback


def _coerce_stock_info_text(stock_info: Any, symbol: str) -> str:
    """Compatible with different stock information return formats such as str/dict/tuple, and uniformly converged into parsable text."""
    payload = stock_info[0] if isinstance(stock_info, tuple) and stock_info else stock_info

    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        lines = [
            f"股票代码: {symbol}",
            f"股票名称: {payload.get('name', '未知')}",
            f"所属地区: {payload.get('area', '未知')}",
            f"所属行业: {payload.get('industry', '未知')}",
            f"上市市场: {payload.get('market', '未知')}",
            f"上市日期: {payload.get('list_date', '未知')}",
        ]
        if payload.get('current_price') is not None:
            lines.append(f"当前价格: {payload.get('current_price')}")
        if payload.get('change_pct') is not None:
            try:
                lines.append(f"涨跌幅: {float(payload.get('change_pct')):+.2f}%")
            except Exception:
                lines.append(f"涨跌幅: {payload.get('change_pct')}")
        if payload.get('volume') is not None:
            lines.append(f"成交量: {payload.get('volume')}")
        return "\n".join(lines)

    if payload in (None, ""):
        return ""
    return str(payload)


class OptimizedChinaDataProvider:
    """Optimized A-share data provider - integrated caching and Tushare data interface"""

    def __init__(self):
        self.cache = get_cache()
        self.config = config_manager.load_settings()
        self.last_api_call = 0
        self.min_api_interval = get_float("TA_CHINA_MIN_API_INTERVAL_SECONDS", "ta_china_min_api_interval_seconds", 0.5)

        logger.info(f"📊 Optimization of A-share data provider initialization completed")

    def _wait_for_rate_limit(self):
        """等待API限制"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call

        if time_since_last_call < self.min_api_interval:
            wait_time = self.min_api_interval - time_since_last_call
            time.sleep(wait_time)

        self.last_api_call = time.time()

    def _format_financial_data_to_fundamentals(self, financial_data: Dict[str, Any], symbol: str) -> str:
        """Convert MongoDB financial data to fundamental analysis format"""
        try:
            # Extract key financial indicators
            revenue = financial_data.get('total_revenue', 'N/A')
            net_profit = financial_data.get('net_profit', 'N/A')
            total_assets = financial_data.get('total_assets', 'N/A')
            total_equity = financial_data.get('total_equity', 'N/A')
            report_period = financial_data.get('report_period', 'N/A')

            # Format the value (if it is a number, add thousandths, otherwise display the original value)
            def format_number(value):
                if isinstance(value, (int, float)):
                    return f"{value:,.2f}"
                return str(value)

            revenue_str = format_number(revenue)
            net_profit_str = format_number(net_profit)
            total_assets_str = format_number(total_assets)
            total_equity_str = format_number(total_equity)

            # Calculate financial ratios
            roe = 'N/A'
            if isinstance(net_profit, (int, float)) and isinstance(total_equity, (int, float)) and total_equity != 0:
                roe = f"{(net_profit / total_equity * 100):.2f}%"

            roa = 'N/A'
            if isinstance(net_profit, (int, float)) and isinstance(total_assets, (int, float)) and total_assets != 0:
                roa = f"{(net_profit / total_assets * 100):.2f}%"

            # Formatted output
            fundamentals_report = f"""
# {symbol} 基本面数据分析

## 📊 财务概况
- **报告期**: {report_period}
- **营业收入**: {revenue_str} 元
- **净利润**: {net_profit_str} 元
- **总资产**: {total_assets_str} 元
- **股东权益**: {total_equity_str} 元

## 📈 财务比率
- **净资产收益率(ROE)**: {roe}
- **总资产收益率(ROA)**: {roa}

## 📝 数据说明
- 数据来源: MongoDB财务数据库
- 更新时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
- 数据类型: 同步财务数据
"""
            return fundamentals_report.strip()

        except Exception as e:
            logger.warning(f"⚠️ Failed to format financial data: {e}")
            return f"# {symbol} fundamental data\n\n❌ Data format failed: {str(e)}"

    def get_stock_data(self, symbol: str, start_date: str, end_date: str,
                      force_refresh: bool = False) -> str:
        """
        Obtain A-share data - use cache first

        Args:
            symbol: Stock code (6 digits)
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            force_refresh: Whether to force cache refresh

        Returns:
            Formatted stock data string
        """
        logger.info(f"📈 获取A股数据: {symbol} ({start_date} 到 {end_date})")

        # 1. Try to get from MongoDB first (if TA_USE_APP_CACHE is enabled)
        if not force_refresh:
            adapter = get_mongodb_cache_adapter()
            if adapter.use_app_cache:
                df = adapter.get_historical_data(symbol, start_date, end_date)
                if df is not None and not df.empty:
                    logger.info(f"📊 [数据来源: MongoDB] 使用MongoDB历史数据: {symbol} ({len(df)}条记录)")
                    return df.to_string()

        # 2. Check file cache (unless force refresh)
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                data_source="unified"  # Unified data source (Tushare/AKShare/BaoStock)
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ [Data source: File cache] Load A-share data from cache: {symbol}")
                    return cached_data

        # Cache miss, obtained from the unified data source interface
        logger.info(f"🌐 [Data source: API call] Obtain data from the unified data source interface: {symbol}")

        try:
            # API restriction of processing
            self._wait_for_rate_limit()

            # Call the unified data source interface (default is Tushare, supports alternate data sources)
            from .data_source_manager import get_china_stock_data_unified

            formatted_data = get_china_stock_data_unified(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )

            # Check if acquisition is successful
            if "❌" in formatted_data or "错误" in formatted_data:
                logger.error(f"❌ [Data source: API failed] Data source API call failed: {symbol}")
                # Try to get data from old cache
                old_cache = self._try_get_old_cache(symbol, start_date, end_date)
                if old_cache:
                    logger.info(f"📁 [Data source: Expired cache] Use expired cached data: {symbol}")
                    return old_cache

                # Generate backup data
                logger.warning(f"⚠️ [Data source: backup data] Generate backup data: {symbol}")
                return self._generate_fallback_data(symbol, start_date, end_date, "数据源API调用失败")

            # Save to cache
            self.cache.save_stock_data(
                symbol=symbol,
                data=formatted_data,
                start_date=start_date,
                end_date=end_date,
                data_source="unified"  # Use unified data source identification
            )

            logger.info(f"✅ [Data source: API Call successful] A Stock data obtained successfully: {symbol}")
            return formatted_data

        except Exception as e:
            error_msg = f"Tushare Data interface call exception: {str(e)}"
            logger.error(f"❌ {error_msg}")

            # Try to get data from old cache
            old_cache = self._try_get_old_cache(symbol, start_date, end_date)
            if old_cache:
                logger.info(f"📁 使用过期缓存数据: {symbol}")
                return old_cache

            # Generate backup data
            return self._generate_fallback_data(symbol, start_date, end_date, error_msg)

    def get_fundamentals_data(self, symbol: str, force_refresh: bool = False) -> str:
        """
        Obtain A-share fundamental data - use cache first

        Args:
            symbol: Stock code
            force_refresh: Whether to force cache refresh

        Returns:
            Formatted fundamental data string
        """
        logger.info(f"📊 获取A股基本面数据: {symbol}")

        # 1. Prioritize trying to get financial data from MongoDB (if TA_USE_APP_CACHE is enabled)
        if not force_refresh:
            adapter = get_mongodb_cache_adapter()
            if adapter.use_app_cache:
                financial_data = adapter.get_financial_data(symbol)
                if financial_data:
                    logger.info(f"💰 [Data source: MongoDB financial data] Using MongoDB financial data: {symbol}")
                    # Convert financial data to fundamental analysis format
                    return self._format_financial_data_to_fundamentals(financial_data, symbol)

        # 2. Check file cache (unless force refresh)
        if not force_refresh:
            # Find fundamental data cache
            for metadata_file in self.cache.metadata_dir.glob(f"*_meta.json"):
                try:
                    import json
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    if (metadata.get('symbol') == symbol and
                        metadata.get('data_type') == 'fundamentals' and
                        metadata.get('market_type') == 'china'):

                        cache_key = metadata_file.stem.replace('_meta', '')
                        if self.cache.is_cache_valid(cache_key, symbol=symbol, data_type='fundamentals'):
                            cached_data = self.cache.load_stock_data(cache_key)
                            if cached_data:
                                logger.info(f"⚡ [Data source: File cache] Load A-share fundamental data from cache: {symbol}")
                                return cached_data
                except Exception:
                    continue

        # Cache miss, generate fundamental analysis
        logger.debug(f"🔍 [Data source: Generate analysis] Generate A-share fundamental analysis: {symbol}")

        try:
            # Fundamental analysis only requires basic information and does not require complete historical transaction data.
            # Get basic stock information (company name, current price, etc.)
            stock_basic_info = self._get_stock_basic_info_only(symbol)

            # Generate fundamental analysis report
            fundamentals_data = self._generate_fundamentals_report(symbol, stock_basic_info)

            # Save to cache
            self.cache.save_fundamentals_data(
                symbol=symbol,
                fundamentals_data=fundamentals_data,
                data_source="unified_analysis"  # Unified data source analysis
            )

            logger.info(f"✅ [Data source: Analysis generated successfully] A Stock fundamental data generated successfully: {symbol}")
            return fundamentals_data

        except Exception as e:
            error_msg = f"基本面数据生成失败: {str(e)}"
            logger.error(f"❌ [Data source: Build failed] {error_msg}")
            logger.warning(f"⚠️ [Data source: backup data] Generate alternative fundamental data: {symbol}")
            return self._generate_fallback_fundamentals(symbol, error_msg)

    def _get_stock_basic_info_only(self, symbol: str) -> str:
        """
        Get basic stock information (for fundamental analysis only)
        Do not obtain historical transaction data, only obtain basic information such as company name, current price, etc.
        """
        logger.debug(f"📊 [基本面优化] 获取{symbol}基础信息（不含历史数据）")

        try:
            # Obtain basic stock information from the unified interface
            from .interface import get_china_stock_info_unified
            stock_info = _coerce_stock_info_text(get_china_stock_info_unified(symbol), symbol)

            # If the acquisition is successful, the basic information will be returned directly.
            if stock_info and "股票名称:" in stock_info:
                logger.debug(f"📊 [Fundamental optimization] successfully obtained{symbol}Basic information, no historical data required")
                return stock_info

            # If the basic information acquisition fails, try to obtain the most basic information from the cache.
            try:
                from tradingagents.config.runtime_settings import use_app_cache_enabled
                if use_app_cache_enabled(False):
                    from .cache.app_adapter import get_market_quote_dataframe
                    df_q = get_market_quote_dataframe(symbol)
                    if df_q is not None and not df_q.empty:
                        row_q = df_q.iloc[-1]
                        current_price = str(row_q.get('close', 'N/A'))
                        change_pct = f"{float(row_q.get('pct_chg', 0)):+.2f}%" if row_q.get('pct_chg') is not None else 'N/A'
                        volume = str(row_q.get('volume', 'N/A'))

                        # Construct basic information format
                        basic_info = f"""股票代码: {symbol}
股票名称: 未知公司
当前价格: {current_price}
涨跌幅: {change_pct}
成交量: {volume}"""
                        logger.debug(f"📊 [基本面优化] 从缓存构造{symbol}基础信息")
                        return basic_info
            except Exception as e:
                logger.debug(f"📊 [Fundamental optimization] Failed to obtain basic information from cache: {e}")

            # If all else fails, return the most basic information
            return f"股票代码: {symbol}\n股票名称: 未知公司\n当前价格: N/A\n涨跌幅: N/A\n成交量: N/A"

        except Exception as e:
            logger.warning(f"⚠️ [基本面优化] 获取{symbol}基础信息失败: {e}")
            return f"股票代码: {symbol}\n股票名称: 未知公司\n当前价格: N/A\n涨跌幅: N/A\n成交量: N/A"

    def _generate_fundamentals_report(self, symbol: str, stock_data: str, analysis_modules: str = "standard") -> str:
        """Generate realistic fundamental analysis reports based on stock data
        
        Args:
            symbol: Stock code
            stock_data: stock data
            analysis_modules: Analysis module level ("basic", "standard", "full", "detailed", "comprehensive")
        """

        # Add detailed ticker tracking logs
        logger.debug(f"🔍 [股票代码追踪] _generate_fundamentals_report 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
        logger.debug(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(symbol))}")
        logger.debug(f"🔍 [Stock symbol tracking] ticker character: {list(str(symbol))}")
        logger.debug(f"🔍 [Stock symbol tracking] The first 200 characters of the received stock data: {stock_data[:200] if stock_data else 'None'}")

        # Extract information from stock data
        company_name = "未知公司"
        current_price = "N/A"
        volume = "N/A"
        change_pct = "N/A"

        # First try to obtain basic stock information from the unified interface
        try:
            logger.debug(f"🔍 [股票代码追踪] 尝试获取{symbol}的基本信息...")
            from .interface import get_china_stock_info_unified
            stock_info = _coerce_stock_info_text(get_china_stock_info_unified(symbol), symbol)
            logger.debug(f"🔍 [Stock symbol tracking] Obtained stock information: {stock_info}")

            if "股票名称:" in stock_info:
                lines = stock_info.split('\n')
                for line in lines:
                    if "股票名称:" in line:
                        company_name = line.split(':')[1].strip()
                        logger.debug(f"🔍 [Stock symbol tracking] Get the stock name from the unified interface: {company_name}")
                        break
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain basic stock information: {e}")

        # If the current price/increase/volume is still missing and the app cache is enabled, read market_quotes directly to get the bottom line.
        try:
            if (current_price == "N/A" or change_pct == "N/A" or volume == "N/A"):
                from tradingagents.config.runtime_settings import use_app_cache_enabled  # type: ignore
                if use_app_cache_enabled(False):
                    from .cache.app_adapter import get_market_quote_dataframe
                    df_q = get_market_quote_dataframe(symbol)
                    if df_q is not None and not df_q.empty:
                        row_q = df_q.iloc[-1]
                        if current_price == "N/A" and row_q.get('close') is not None:
                            current_price = str(row_q.get('close'))
                            logger.debug(f"🔍 [Stock symbol tracking] Complete current price from market_quotes: {current_price}")
                        if change_pct == "N/A" and row_q.get('pct_chg') is not None:
                            try:
                                change_pct = f"{float(row_q.get('pct_chg')):+.2f}%"
                            except Exception:
                                change_pct = str(row_q.get('pct_chg'))
                            logger.debug(f"🔍 [Stock symbol tracking] Complement the changes from market_quotes: {change_pct}")
                        if volume == "N/A" and row_q.get('volume') is not None:
                            volume = str(row_q.get('volume'))
                            logger.debug(f"🔍 [Stock symbol tracking] Complete volume from market_quotes: {volume}")
        except Exception as _qe:
            logger.debug(f"🔍 [Stock symbol tracking] Failed to read market_quotes (ignored): {_qe}")

        # Then extract price information from stock data
        if "股票名称:" in stock_data:
            lines = stock_data.split('\n')
            for line in lines:
                if "股票名称:" in line and company_name == "未知公司":
                    company_name = line.split(':')[1].strip()
                elif "当前价格:" in line:
                    current_price = line.split(':')[1].strip()
                elif "最新价格:" in line or "💰 最新价格:" in line:
                    # Compatible with another template output
                    try:
                        current_price = line.split(':', 1)[1].strip().lstrip('¥').strip()
                    except Exception:
                        current_price = line.split(':')[-1].strip()
                elif "涨跌幅:" in line:
                    change_pct = line.split(':')[1].strip()
                elif "成交量:" in line:
                    volume = line.split(':')[1].strip()

        # Try to extract latest price information from stock data table
        if current_price == "N/A" and stock_data:
            try:
                lines = stock_data.split('\n')
                for i, line in enumerate(lines):
                    if "最新数据:" in line and i + 1 < len(lines):
                        # Find rows of data
                        for j in range(i + 1, min(i + 5, len(lines))):
                            data_line = lines[j].strip()
                            if data_line and not data_line.startswith('日期') and not data_line.startswith('-'):
                                # Try to parse the data row
                                parts = data_line.split()
                                if len(parts) >= 4:
                                    try:
                                        # Assume format: Date Stock Code Opening Closing Highest Lowest Trading Volume Trading Value...
                                        current_price = parts[3]  # closing price
                                        logger.debug(f"🔍 [Stock symbol tracking] Extract closing price from data table: {current_price}")
                                        break
                                    except (IndexError, ValueError):
                                        continue
                        break
            except Exception as e:
                logger.debug(f"🔍 [Stock symbol tracking] Failed to parse stock data table: {e}")

        # Determine the industry and basic information based on the stock code
        logger.debug(f"🔍 [Stock symbol tracking] Call _get_industry_info, passing in parameters: '{symbol}'")
        industry_info = self._get_industry_info(symbol)
        logger.debug(f"🔍 [Stock symbol tracking] _get_industry_info Return results: {industry_info}")

        # Attempts to obtain financial metrics, returning a simplified fundamentals report on failure
        logger.debug(f"🔍 [Stock symbol tracking] Call _estimate_financial_metrics, passing in parameters: '{symbol}'")
        try:
            financial_estimates = self._estimate_financial_metrics(symbol, current_price)
            logger.debug(f"🔍 [Stock symbol tracking] _estimate_financial_metrics Return results: {financial_estimates}")
        except Exception as e:
            logger.warning(f"⚠️ [fundamental analysis] Unable to get financial metrics: {e}")
            logger.info(f"📊 [fundamental analysis] Returns a simplified fundamentals report (without financial indicators)")

            # Returns a simplified fundamentals report (excluding financial metrics)
            simplified_report = f"""# 中国A股基本面分析报告 - {symbol} (简化版)

## 📊 基本信息
- **股票代码**: {symbol}
- **公司名称**: {company_name}
- **所属行业**: {industry_info.get('industry', '未知')}
- **当前价格**: {current_price}
- **涨跌幅**: {change_pct}
- **成交量**: {volume}

## 📈 行业分析
{industry_info.get('analysis', '暂无行业分析')}

## ⚠️ 数据说明
由于无法获取完整的财务数据，本报告仅包含基本价格信息和行业分析。
建议：
1. 查看公司最新财报获取详细财务数据
2. 关注行业整体走势
3. 结合技术分析进行综合判断

---
**生成时间**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
**数据来源**: 基础市场数据
"""
            return simplified_report.strip()

        logger.debug(f"🔍 [Stock symbol tracking] Start generating reports using ticker symbols: '{symbol}'")

        # Check data sources and generate corresponding descriptions
        data_source_note = ""
        data_source = financial_estimates.get('data_source', '')

        if any("（估算值）" in str(v) for v in financial_estimates.values() if isinstance(v, str)):
            data_source_note = "\n⚠️ **Data description**: Some financial indicators are estimates and it is recommended to analyze them in conjunction with the latest financial report data."
        elif data_source == "AKShare":
            data_source_note = "\n✅ **Data description**: Financial indicators are calculated based on AKShare real financial data"
        elif data_source == "Tushare":
            data_source_note = "\n✅ **Data description**: Financial indicators are calculated based on Tushare s real financial data"
        else:
            data_source_note = "\n✅ **Data description**: Financial indicators are calculated based on real financial data"

        # Adjust report content based on analysis module level
        logger.debug(f"🔍 [fundamental analysis] Using analysis module level: {analysis_modules}")
        
        if analysis_modules == "basic":
            # Basic model: only contains core financial indicators
            report = f"""# 中国A股基本面分析报告 - {symbol} (基础版)

## 📊 股票基本信息
- **股票代码**: {symbol}
- **股票名称**: {company_name}
- **当前股价**: {current_price}
- **涨跌幅**: {change_pct}
- **分析日期**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y年%m月%d日')}{data_source_note}

## 💰 核心财务指标
- **总市值**: {financial_estimates.get('total_mv', 'N/A')}
- **市盈率(PE)**: {financial_estimates.get('pe', 'N/A')}
- **市盈率TTM(PE_TTM)**: {financial_estimates.get('pe_ttm', 'N/A')}
- **市净率(PB)**: {financial_estimates.get('pb', 'N/A')}
- **净资产收益率(ROE)**: {financial_estimates.get('roe', 'N/A')}
- **资产负债率**: {financial_estimates.get('debt_ratio', 'N/A')}

## 💡 基础评估
- **基本面评分**: {financial_estimates['fundamental_score']}/10
- **风险等级**: {financial_estimates['risk_level']}

---
**重要声明**: 本报告基于公开数据和模型估算生成，仅供参考，不构成投资建议。
**数据来源**: {data_source if data_source else "多源数据"}数据接口
**生成时间**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""
        elif analysis_modules in ["standard", "full"]:
            # Standard/Full mode: includes detailed analysis
            report = f"""# 中国A股基本面分析报告 - {symbol}

## 📊 股票基本信息
- **股票代码**: {symbol}
- **股票名称**: {company_name}
- **所属行业**: {industry_info['industry']}
- **市场板块**: {industry_info['market']}
- **当前股价**: {current_price}
- **涨跌幅**: {change_pct}
- **成交量**: {volume}
- **分析日期**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y年%m月%d日')}{data_source_note}

## 💰 财务数据分析

### 估值指标
- **总市值**: {financial_estimates.get('total_mv', 'N/A')}
- **市盈率(PE)**: {financial_estimates.get('pe', 'N/A')}
- **市盈率TTM(PE_TTM)**: {financial_estimates.get('pe_ttm', 'N/A')}
- **市净率(PB)**: {financial_estimates.get('pb', 'N/A')}
- **市销率(PS)**: {financial_estimates.get('ps', 'N/A')}
- **股息收益率**: {financial_estimates.get('dividend_yield', 'N/A')}

### 盈利能力指标
- **净资产收益率(ROE)**: {financial_estimates['roe']}
- **总资产收益率(ROA)**: {financial_estimates['roa']}
- **毛利率**: {financial_estimates['gross_margin']}
- **净利率**: {financial_estimates['net_margin']}

### 财务健康度
- **资产负债率**: {financial_estimates['debt_ratio']}
- **流动比率**: {financial_estimates['current_ratio']}
- **速动比率**: {financial_estimates['quick_ratio']}
- **现金比率**: {financial_estimates['cash_ratio']}

## 📈 行业分析
{industry_info['analysis']}

## 🎯 投资价值评估
### 估值水平分析
{self._analyze_valuation(financial_estimates)}

### 成长性分析
{self._analyze_growth_potential(symbol, industry_info)}

## 💡 投资建议
- **基本面评分**: {financial_estimates['fundamental_score']}/10
- **估值吸引力**: {financial_estimates['valuation_score']}/10
- **成长潜力**: {financial_estimates['growth_score']}/10
- **风险等级**: {financial_estimates['risk_level']}

{self._generate_investment_advice(financial_estimates, industry_info)}

---
**重要声明**: 本报告基于公开数据和模型估算生成，仅供参考，不构成投资建议。
**数据来源**: {data_source if data_source else "多源数据"}数据接口
**生成时间**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""
        else:  # detailed, comprehensive
            # Detailed/Comprehensive mode: Contains the most complete analysis
            report = f"""# 中国A股基本面分析报告 - {symbol} (全面版)

## 📊 股票基本信息
- **股票代码**: {symbol}
- **股票名称**: {company_name}
- **所属行业**: {industry_info['industry']}
- **市场板块**: {industry_info['market']}
- **当前股价**: {current_price}
- **涨跌幅**: {change_pct}
- **成交量**: {volume}
- **分析日期**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y年%m月%d日')}{data_source_note}

## 💰 财务数据分析

### 估值指标
- **总市值**: {financial_estimates.get('total_mv', 'N/A')}
- **市盈率(PE)**: {financial_estimates.get('pe', 'N/A')}
- **市盈率TTM(PE_TTM)**: {financial_estimates.get('pe_ttm', 'N/A')}
- **市净率(PB)**: {financial_estimates.get('pb', 'N/A')}
- **市销率(PS)**: {financial_estimates.get('ps', 'N/A')}
- **股息收益率**: {financial_estimates.get('dividend_yield', 'N/A')}

### 盈利能力指标
- **净资产收益率(ROE)**: {financial_estimates.get('roe', 'N/A')}
- **总资产收益率(ROA)**: {financial_estimates.get('roa', 'N/A')}
- **毛利率**: {financial_estimates.get('gross_margin', 'N/A')}
- **净利率**: {financial_estimates.get('net_margin', 'N/A')}

### 财务健康度
- **资产负债率**: {financial_estimates['debt_ratio']}
- **流动比率**: {financial_estimates['current_ratio']}
- **速动比率**: {financial_estimates['quick_ratio']}
- **现金比率**: {financial_estimates['cash_ratio']}

## 📈 行业分析

### 行业地位
{industry_info['analysis']}

### 竞争优势
- **市场份额**: {industry_info['market_share']}
- **品牌价值**: {industry_info['brand_value']}
- **技术优势**: {industry_info['tech_advantage']}

## 🎯 投资价值评估

### 估值水平分析
{self._analyze_valuation(financial_estimates)}

### 成长性分析
{self._analyze_growth_potential(symbol, industry_info)}

### 风险评估
{self._analyze_risks(symbol, financial_estimates, industry_info)}

## 💡 投资建议

### 综合评分
- **基本面评分**: {financial_estimates['fundamental_score']}/10
- **估值吸引力**: {financial_estimates['valuation_score']}/10
- **成长潜力**: {financial_estimates['growth_score']}/10
- **风险等级**: {financial_estimates['risk_level']}

### 操作建议
{self._generate_investment_advice(financial_estimates, industry_info)}

### 绝对估值
- **DCF估值**：基于现金流贴现的内在价值
- **资产价值**：净资产重估价值
- **分红收益率**：股息回报分析

## 风险分析
### 系统性风险
- **宏观经济风险**：经济周期对公司的影响
- **政策风险**：行业政策变化的影响
- **市场风险**：股市波动对估值的影响

### 非系统性风险
- **经营风险**：公司特有的经营风险
- **财务风险**：债务结构和偿债能力风险
- **管理风险**：管理层变动和决策风险

## 投资建议
### 综合评价
基于以上分析，该股票的投资价值评估：

**优势：**
- A股市场上市公司，监管相对完善
- 具备一定的市场地位和品牌价值
- 财务信息透明度较高

**风险：**
- 需要关注宏观经济环境变化
- 行业竞争加剧的影响
- 政策调整对业务的潜在影响

### 操作建议
- **投资策略**：建议采用价值投资策略，关注长期基本面
- **仓位建议**：根据风险承受能力合理配置仓位
- **关注指标**：重点关注ROE、PE、现金流等核心指标

---
**重要声明**: 本报告基于公开数据和模型估算生成，仅供参考，不构成投资建议。
实际投资决策请结合最新财报数据和专业分析师意见。

**数据来源**: {data_source if data_source else "多源数据"}数据接口 + 基本面分析模型
**生成时间**: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""

        return report

    def _get_industry_info(self, symbol: str) -> dict:
        """Obtain industry information based on stock codes (priority to using real data from the database)"""

        # Add detailed ticker tracking logs
        logger.debug(f"🔍 [股票代码追踪] _get_industry_info 接收到的股票代码: '{symbol}' (类型: {type(symbol)})")
        logger.debug(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(symbol))}")
        logger.debug(f"🔍 [Stock symbol tracking] ticker character: {list(str(symbol))}")

        # First try to get real industry information from the database
        try:
            from .cache.app_adapter import get_basics_from_cache
            doc = get_basics_from_cache(symbol)
            if doc:
                # Only record key fields to avoid printing the complete document
                logger.debug(f"🔍 [Stock symbol tracking] Obtain basic information from the database: code={doc.get('code')}, name={doc.get('name')}, industry={doc.get('industry')}")

                # Standardize industries and sectors (avoid"Small and medium-sized board/GEM"Segment values are mistakenly used as industries)
                board_labels = {'主板', '中小板', '创业板', '科创板'}
                raw_industry = (doc.get('industry') or doc.get('industry_name') or '').strip()
                sec_or_cat = (doc.get('sec') or doc.get('category') or '').strip()
                market_val = (doc.get('market') or '').strip()
                industry_val = raw_industry or sec_or_cat or '未知'

                # If the industry field is a sector name, use it for market; industry uses a more detailed classification (sec/category) instead
                if raw_industry in board_labels:
                    if not market_val:
                        market_val = raw_industry
                    if sec_or_cat:
                        industry_val = sec_or_cat
                    logger.debug(f"🔧 [字段归一化] industry原值='{raw_industry}' → 行业='{industry_val}', 市场/板块='{market_val}'")

                # Build industry information
                info = {
                    "industry": industry_val or '未知',
                    "market": market_val or doc.get('market', '未知'),
                    "type": self._get_market_type_by_code(symbol)
                }

                logger.debug(f"🔍 [Stock symbol tracking] Industry information obtained from database: {info}")

                # Add detailed analysis of special stocks
                if symbol in self._get_special_stocks():
                    info.update(self._get_special_stocks()[symbol])
                else:
                    info.update({
                        "analysis": f"该股票属于{info['industry']}行业，在{info['market']}上市交易。",
                        "market_share": "待分析",
                        "brand_value": "待评估",
                        "tech_advantage": "待分析"
                    })

                return info

        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain industry information from database: {e}")

        # Alternative: Use code prefix determination (but correct industry/market mapping)
        logger.debug(f"🔍 [Stock symbol tracking] Use alternative solutions, based on code prefix judgment")
        code_prefix = symbol[:3]
        logger.debug(f"🔍 [Stock symbol tracking] Extracted code prefix: '{code_prefix}'")

        # Revised mapping table: distinguishing between industries and market sectors
        market_map = {
            "000": {"market": "主板", "exchange": "深圳证券交易所", "type": "综合"},
            "001": {"market": "主板", "exchange": "深圳证券交易所", "type": "综合"},
            "002": {"market": "主板", "exchange": "深圳证券交易所", "type": "成长型"},  # 002 The beginning is now also the motherboard
            "003": {"market": "创业板", "exchange": "深圳证券交易所", "type": "创新型"},
            "300": {"market": "创业板", "exchange": "深圳证券交易所", "type": "高科技"},
            "600": {"market": "主板", "exchange": "上海证券交易所", "type": "大盘蓝筹"},
            "601": {"market": "主板", "exchange": "上海证券交易所", "type": "大盘蓝筹"},
            "603": {"market": "主板", "exchange": "上海证券交易所", "type": "中小盘"},
            "688": {"market": "科创板", "exchange": "上海证券交易所", "type": "科技创新"},
        }

        market_info = market_map.get(code_prefix, {
            "market": "未知市场",
            "exchange": "未知交易所",
            "type": "综合"
        })

        info = {
            "industry": "未知",  # It is impossible to accurately determine the specific industry from the code prefix
            "market": market_info["market"],
            "type": market_info["type"]
        }

        # Special stock details
        special_stocks = self._get_special_stocks()
        if symbol in special_stocks:
            info.update(special_stocks[symbol])
        else:
            info.update({
                "analysis": f"该股票在{info['market']}上市交易，具体行业信息需要进一步查询。",
                "market_share": "待分析",
                "brand_value": "待评估",
                "tech_advantage": "待分析"
            })

        return info

    def _get_market_type_by_code(self, symbol: str) -> str:
        """根据股票代码判断市场类型"""
        code_prefix = symbol[:3]
        type_map = {
            "000": "综合", "001": "综合", "002": "成长型", "003": "创新型",
            "300": "高科技", "600": "大盘蓝筹", "601": "大盘蓝筹",
            "603": "中小盘", "688": "科技创新"
        }
        return type_map.get(code_prefix, "综合")

    def _get_special_stocks(self) -> dict:
        """获取特殊股票的详细信息"""
        return {
            "000001": {
                "industry": "银行业",
                "analysis": "Ping An Bank is China s leading joint-stock commercial bank with significant advantages in retail banking business.",
                "market_share": "股份制银行前列",
                "brand_value": "知名金融品牌",
                "tech_advantage": "金融科技创新领先"
            },
            "600036": {
                "industry": "银行业",
                "analysis": "China Merchants Bank is a high-quality joint-stock bank in China, leading in retail banking and wealth management businesses.",
                "market_share": "股份制银行龙头",
                "brand_value": "优质银行品牌",
                "tech_advantage": "数字化银行先锋"
            },
            "000002": {
                "industry": "房地产",
                "analysis": "Vanke A is a leading company in China s real estate industry and has a leading position in the field of residential development.",
                "market_share": "房地产行业前三",
                "brand_value": "知名地产品牌",
                "tech_advantage": "绿色建筑技术"
            },
            "002475": {
                "industry": "元器件",
                "analysis": "Luxshare Precision is the world s leading precision manufacturing service provider, mainly engaged in the R&D and manufacturing of connectors, acoustics, wireless charging and other products.",
                "market_share": "消费电子连接器龙头",
                "brand_value": "精密制造知名品牌",
                "tech_advantage": "精密制造技术领先"
            }
        }

    def _estimate_financial_metrics(self, symbol: str, current_price: str) -> dict:
        """Obtain real financial indicators (obtained from MongoDB, AKShare, Tushare, throw an exception if failed)"""

        # Extract price value
        try:
            price_value = float(current_price.replace('¥', '').replace(',', ''))
        except:
            price_value = 10.0  # Default value

        # Try to get real financial data
        real_metrics = self._get_real_financial_metrics(symbol, price_value)
        if real_metrics:
            logger.info(f"✅ 使用真实财务数据: {symbol}")
            return real_metrics

        # If the real data cannot be obtained, an exception is thrown
        error_msg = f"无法获取股票 {symbol} 的财务数据。已尝试所有数据源（MongoDB、AKShare、Tushare）均失败。"
        logger.error(f"❌ {error_msg}")
        raise ValueError(error_msg)

    def _get_real_financial_metrics(self, symbol: str, price_value: float) -> dict:
        """Get real financial indicators - use database cache first, then use API"""
        try:
            # 🔥 Prioritize getting real-time stock prices from market_quotes and replacing the incoming price_value
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            db_client = None

            if db_manager.is_mongodb_available():
                try:
                    db_client = db_manager.get_mongodb_client()
                    db = db_client['tradingagents']

                    # Standardized stock code is 6 digits
                    code6 = symbol.replace('.SH', '').replace('.SZ', '').zfill(6)

                    # Get real-time stock prices from market_quotes
                    quote = db.market_quotes.find_one({"code": code6})
                    if quote and quote.get("close"):
                        realtime_price = float(quote.get("close"))
                        logger.info(f"✅ 从 market_quotes 获取实时股价: {code6} = {realtime_price}元 (原价格: {price_value}元)")
                        price_value = realtime_price
                    else:
                        logger.info(f"⚠️ market_quotes 中未找到{code6}的实时股价，使用传入价格: {price_value}元")
                except Exception as e:
                    logger.warning(f"⚠️ 从 market_quotes 获取实时股价失败: {e}，使用传入价格: {price_value}元")
            else:
                logger.info(f"⚠️ MongoDB 不可用，使用传入价格: {price_value}元")

            # Priority 1: Get normalized financial data from the MongoDB stock_financial_data collection
            from tradingagents.config.runtime_settings import use_app_cache_enabled
            if use_app_cache_enabled(False):
                logger.info(f"🔍 优先从 MongoDB stock_financial_data 集合获取{symbol}财务数据")

                # Get standardized financial data directly from MongoDB
                from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter
                adapter = get_mongodb_cache_adapter()
                financial_data = adapter.get_financial_data(symbol)

                if financial_data:
                    logger.info(f"✅ [财务数据] 从 stock_financial_data 集合获取{symbol}财务数据")
                    # Parse MongoDB standardized financial data
                    metrics = self._parse_mongodb_financial_data(financial_data, price_value)
                    if metrics:
                        logger.info(f"✅ MongoDB Financial data parsing is successful and indicators are returned")
                        return metrics
                    else:
                        logger.warning(f"⚠️ MongoDB Financial data parsing failed")
                else:
                    logger.info(f"🔄 MongoDB not found{symbol}Financial data, try to get it from AKShare API")
            else:
                logger.info(f"🔄 数据库缓存未启用，直接从AKShare API获取{symbol}财务数据")

            # Second priority: Get from AKShare API
            from .providers.china.akshare import get_akshare_provider
            import asyncio

            akshare_provider = get_akshare_provider()

            if akshare_provider.connected:
                # AKShare get_financial_data is an asynchronous method and needs to be run using asyncio
                loop = asyncio.get_event_loop()
                financial_data = loop.run_until_complete(akshare_provider.get_financial_data(symbol))

                if financial_data and any(not v.empty if hasattr(v, 'empty') else bool(v) for v in financial_data.values()):
                    logger.info(f"✅ AKShare Financial data obtained successfully: {symbol}")
                    # Get basic stock information (also an asynchronous method)
                    stock_info = loop.run_until_complete(akshare_provider.get_stock_basic_info(symbol))

                    # Parsing AKShare financial data
                    logger.debug(f"🔧 Call AKShare parsing function, stock price: {price_value}")
                    metrics = self._parse_akshare_financial_data(financial_data, stock_info, price_value)
                    logger.debug(f"🔧 AKShare Parse results: {metrics}")
                    if metrics:
                        logger.info(f"✅ AKShare The parsing is successful and the indicator is returned.")
                        # Cache raw financial data to database (instead of parsed metrics)
                        self._cache_raw_financial_data(symbol, financial_data, stock_info)
                        return metrics
                    else:
                        logger.warning(f"⚠️ AKShare Parsing failed, return None")
                else:
                    logger.warning(f"⚠️ AKShare Not obtained{symbol}financial data, try Tushare")
            else:
                logger.warning(f"⚠️ AKShare Not connected, try Tushare")

            # Third priority: Use Tushare data source
            logger.info(f"🔄 使用Tushare备用数据源获取{symbol}财务数据")
            from .providers.china.tushare import get_tushare_provider
            import asyncio

            provider = get_tushare_provider()
            if not provider.is_available():
                logger.debug(f"Tushare API Client 未就绪，无法获取{symbol}真实财务数据")
                return None

            # Get financial data (asynchronous method)
            loop = asyncio.get_event_loop()
            financial_data = loop.run_until_complete(provider.get_financial_data(symbol))
            if not financial_data:
                logger.debug(f"未获取到{symbol}的财务数据")
                return None

            # Get basic stock information (asynchronous method)
            stock_info = loop.run_until_complete(provider.get_stock_basic_info(symbol))

            # Parsing Tushare Financial Data
            metrics = self._parse_financial_data(financial_data, stock_info, price_value)
            if metrics:
                # Cache raw financial data to database
                self._cache_raw_financial_data(symbol, financial_data, stock_info)
                return metrics

        except Exception as e:
            logger.debug(f"获取{symbol}真实财务数据失败: {e}")

        return None

    def _parse_mongodb_financial_data(self, financial_data: dict, price_value: float) -> dict:
        """Parse MongoDB normalized financial data into metrics"""
        try:
            logger.debug(f"📊 [financial data] Start parsing MongoDB financial data, including fields: {list(financial_data.keys())}")

            metrics = {}

            # MongoDB The financial_data is a flat structure that directly contains all financial indicators
            # No longer nested {balance_sheet, income_statement, ...} structure

            # Extract metrics directly from financial_data
            latest_indicators = financial_data

            # ROE - ROE (Add scope validation)
            roe = latest_indicators.get('roe') or latest_indicators.get('roe_waa')
            if roe is not None and str(roe) != 'nan' and roe != '--':
                try:
                    roe_val = float(roe)
                    # ROE Typically between -100% and 100%, extreme cases may exceed
                    if -200 <= roe_val <= 200:
                        metrics["roe"] = f"{roe_val:.1f}%"
                    else:
                        logger.warning(f"⚠️ ROE 数据异常: {roe_val}，超出合理范围 [-200%, 200%]，设为 N/A")
                        metrics["roe"] = "N/A"
                except (ValueError, TypeError):
                    metrics["roe"] = "N/A"
            else:
                metrics["roe"] = "N/A"

            # ROA - return on total assets (Add scope validation)
            roa = latest_indicators.get('roa') or latest_indicators.get('roa2')
            if roa is not None and str(roa) != 'nan' and roa != '--':
                try:
                    roa_val = float(roa)
                    # ROA Typically between -50% and 50%
                    if -100 <= roa_val <= 100:
                        metrics["roa"] = f"{roa_val:.1f}%"
                    else:
                        logger.warning(f"⚠️ ROA 数据异常: {roa_val}，超出合理范围 [-100%, 100%]，设为 N/A")
                        metrics["roa"] = "N/A"
                except (ValueError, TypeError):
                    metrics["roa"] = "N/A"
            else:
                metrics["roa"] = "N/A"

            # Gross profit margin - give priority to using the percentage caliber grossprofit_margin, and then fall back gross_margin
            gross_margin_val = None
            raw_data = financial_data.get('raw_data') if isinstance(financial_data.get('raw_data'), dict) else {}
            raw_indicator_list = raw_data.get('financial_indicators') or []
            gross_margin_candidates = [
                latest_indicators.get('grossprofit_margin'),
                latest_indicators.get('gross_margin'),
            ]
            for record in raw_indicator_list:
                gross_margin_candidates.extend([
                    record.get('grossprofit_margin'),
                    record.get('gross_margin'),
                ])

            for candidate in gross_margin_candidates:
                if candidate is None or str(candidate) == 'nan' or candidate == '--':
                    continue
                try:
                    candidate_val = float(candidate)
                except (ValueError, TypeError):
                    continue

                if -100 <= candidate_val <= 100:
                    gross_margin_val = candidate_val
                    break

                logger.warning(f"⚠️ 毛利率数据异常: {candidate_val}，超出合理范围 [-100%, 100%]，继续尝试其他口径")

            if gross_margin_val is not None:
                metrics["gross_margin"] = f"{gross_margin_val:.1f}%"
            else:
                metrics["gross_margin"] = "N/A"

            # Net Profit Margin - Added Range Validation
            net_margin = latest_indicators.get('netprofit_margin')
            if net_margin is not None and str(net_margin) != 'nan' and net_margin != '--':
                try:
                    net_margin_val = float(net_margin)
                    # Validation range: Net profit margin should be between -100% and 100%
                    if -100 <= net_margin_val <= 100:
                        metrics["net_margin"] = f"{net_margin_val:.1f}%"
                    else:
                        logger.warning(f"⚠️ 净利率数据异常: {net_margin_val}，超出合理范围 [-100%, 100%]，设为 N/A")
                        metrics["net_margin"] = "N/A"
                except (ValueError, TypeError):
                    metrics["net_margin"] = "N/A"
            else:
                metrics["net_margin"] = "N/A"

            # Compute PE/PB - Prioritize real-time computation, downgrade to static data
            # Get both PE and PE_TTM indicators at the same time
            pe_value = None
            pe_ttm_value = None
            pb_value = None
            is_loss_stock = False  # 🔥 Mark whether it is a losing stock

            try:
                # Prioritize real-time computing
                from tradingagents.dataflows.realtime_metrics import get_pe_pb_with_fallback
                from tradingagents.config.database_manager import get_database_manager

                db_manager = get_database_manager()
                if db_manager.is_mongodb_available():
                    client = db_manager.get_mongodb_client()
                    # Extract stock symbol from symbol
                    stock_code = latest_indicators.get('code') or latest_indicators.get('symbol', '').replace('.SZ', '').replace('.SH', '')

                    logger.info(f"📊 [PE计算] 开始计算股票 {stock_code} 的PE/PB")

                    if stock_code:
                        logger.info(f"📊 [PE Compute - Tier 1] Try real-time calculations PE/PB (Stock code: {stock_code})")

                        # Get real time PE/PB
                        realtime_metrics = get_pe_pb_with_fallback(stock_code, client)

                        if realtime_metrics:
                            # Get market capitalization data (save first)
                            market_cap = realtime_metrics.get('market_cap')
                            if market_cap is not None and market_cap > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["total_mv"] = f"{market_cap:.2f}亿元{realtime_tag}"
                                logger.info(f"✅ [总市值获取成功] 总市值={market_cap:.2f}亿元 | 实时={is_realtime}")

                            # Use real-time PE (dynamic price-to-earnings ratio)
                            pe_value = realtime_metrics.get('pe')
                            if pe_value is not None and pe_value > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["pe"] = f"{pe_value:.1f}倍{realtime_tag}"

                                # Detailed log
                                price = realtime_metrics.get('price', 'N/A')
                                market_cap_log = realtime_metrics.get('market_cap', 'N/A')
                                source = realtime_metrics.get('source', 'unknown')
                                updated_at = realtime_metrics.get('updated_at', 'N/A')

                                logger.info(f"✅ [PE计算-第1层成功] PE={pe_value:.2f}倍 | 来源={source} | 实时={is_realtime}")
                                logger.info(f"   └─ 计算数据: 股价={price}元, 市值={market_cap_log}亿元, 更新时间={updated_at}")
                            elif pe_value is None:
                                # 🔥 PE If None, check whether it is a losing stock
                                pe_ttm_check = latest_indicators.get('pe_ttm')
                                # pe_ttm is None,<= 0, 'nan', '--' Everyone thinks it is a loss-making stock
                                if pe_ttm_check is None or pe_ttm_check <= 0 or str(pe_ttm_check) == 'nan' or pe_ttm_check == '--':
                                    is_loss_stock = True
                                    logger.info(f"⚠️ [PE Compute - Tier 1] PE is None and pe_ttm={pe_ttm_check}, Confirmed as a loss-making stock")

                            # Use real-time PE_TTM (TTM price-to-earnings ratio)
                            pe_ttm_value = realtime_metrics.get('pe_ttm')
                            if pe_ttm_value is not None and pe_ttm_value > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["pe_ttm"] = f"{pe_ttm_value:.1f}倍{realtime_tag}"
                                logger.info(f"✅ [PE_TTM计算-第1层成功] PE_TTM={pe_ttm_value:.2f}倍 | 来源={source} | 实时={is_realtime}")
                            elif pe_ttm_value is None and not is_loss_stock:
                                # 🔥 PE_TTM If None, check again whether it is a losing stock
                                pe_ttm_check = latest_indicators.get('pe_ttm')
                                # pe_ttm is None,<= 0, 'nan', '--' Everyone thinks it is a loss-making stock
                                if pe_ttm_check is None or pe_ttm_check <= 0 or str(pe_ttm_check) == 'nan' or pe_ttm_check == '--':
                                    is_loss_stock = True
                                    logger.info(f"⚠️ [PE_TTM Compute - Tier 1] PE_TTM is None and pe_ttm={pe_ttm_check}, Confirmed as a loss-making stock")

                            # Use real-time PB
                            pb_value = realtime_metrics.get('pb')
                            if pb_value is not None and pb_value > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["pb"] = f"{pb_value:.2f}倍{realtime_tag}"
                                logger.info(f"✅ [PB计算-第1层成功] PB={pb_value:.2f}倍 | 来源={realtime_metrics.get('source')} | 实时={is_realtime}")
                        else:
                            # 🔥 Check whether the return is due to loss None
                            # Get pe_ttm from stock_basic_info to determine whether there is a loss
                            pe_ttm_static = latest_indicators.get('pe_ttm')
                            # pe_ttm is None,<= 0, 'nan', '--' Everyone thinks it is a loss-making stock
                            if pe_ttm_static is None or pe_ttm_static <= 0 or str(pe_ttm_static) == 'nan' or pe_ttm_static == '--':
                                is_loss_stock = True
                                logger.info(f"⚠️ [PE Compute - Tier 1 failed] Losing stocks detected (pe_ttm={pe_ttm_static}) , Skip downgrade calculation")
                            else:
                                logger.warning(f"⚠️ [PE Compute - Tier 1 failed] Real-time calculations return empty results, and downgrade calculations will be attempted.")

            except Exception as e:
                logger.warning(f"⚠️ [PE Compute - Layer 1 Exception] Real-time calculation failed: {e}, Will try to downgrade the calculation")

            # If real-time calculation fails, try to get total market cap from latest_indicators
            if "total_mv" not in metrics:
                logger.info(f"📊 [Total Market Cap - Tier 2] Try to get from stock_basic_info")
                total_mv_static = latest_indicators.get('total_mv')
                if total_mv_static is not None and total_mv_static > 0:
                    metrics["total_mv"] = f"{total_mv_static:.2f}亿元"
                    logger.info(f"✅ [Total Market Cap - Tier 2 Success] Total market capitalization={total_mv_static:.2f}billion (Source: stock_basic_info)")
                else:
                    # Try to calculate from money_cap (10,000 yuan to 100 million yuan)
                    money_cap = latest_indicators.get('money_cap')
                    if money_cap is not None and money_cap > 0:
                        total_mv_yi = money_cap / 10000
                        metrics["total_mv"] = f"{total_mv_yi:.2f}亿元"
                        logger.info(f"✅ [Total Market Cap - Tier 3 Success] Total market capitalization={total_mv_yi:.2f}billion (Convert from money_cap)")
                    else:
                        metrics["total_mv"] = "N/A"
                        logger.warning(f"⚠️ [Total Market Cap - All Failed] No total market capitalization data available")

            # If real-time calculation fails, try traditional calculation method
            if pe_value is None:
                # 🔥 If it has been confirmed that it is a loss-making stock, directly set the PE to N/A and no longer attempt the downgrade calculation.
                if is_loss_stock:
                    metrics["pe"] = "N/A"
                    logger.info(f"⚠️ [PE Calculation-Lossing Stocks] It has been confirmed as a loss-making stock, PE is set to N/A, and the second level calculation is skipped.")
                else:
                    logger.info(f"📊 [PE Compute - Tier 2] Try using market cap/net profit calculation")

                    net_profit = latest_indicators.get('net_profit')

                    # 🔥 Key fix: Check if net profit is positive (PE is not calculated for loss-making stocks)
                    if net_profit and net_profit > 0:
                        try:
                            # Use market cap/net profit calculation PE
                            money_cap = latest_indicators.get('money_cap')
                            if money_cap and money_cap > 0:
                                pe_calculated = money_cap / net_profit
                                metrics["pe"] = f"{pe_calculated:.1f}倍"
                                logger.info(f"✅ [PE计算-第2层成功] PE={pe_calculated:.2f}倍")
                                logger.info(f"   └─ 计算公式: 市值({money_cap}万元) / 净利润({net_profit}万元)")
                            else:
                                logger.warning(f"⚠️ [PE Compute - Layer 2 failed] Market cap is invalid: {money_cap}, Try Tier 3")

                                # Third level downgrade: directly use the pe field in latest_indicators (only when it is a positive number)
                                pe_static = latest_indicators.get('pe')
                                if pe_static is not None and str(pe_static) != 'nan' and pe_static != '--':
                                    try:
                                        pe_float = float(pe_static)
                                        # 🔥 Only accept positive numbers PE
                                        if pe_float > 0:
                                            metrics["pe"] = f"{pe_float:.1f}倍"
                                            logger.info(f"✅ [PE Compute - Tier 3 Success] Use static PE: {metrics['pe']}")
                                            logger.info(f"   └─ Data source: stock_basic_info.pe")
                                        else:
                                            metrics["pe"] = "N/A"
                                            logger.info(f"⚠️ [PE Calculation - Tier 3 Skip] Static PE is negative or zero (loss-making stocks): {pe_float}")
                                    except (ValueError, TypeError):
                                        metrics["pe"] = "N/A"
                                        logger.error(f"❌ [PE Compute - Layer 3 failed] Static PE format error: {pe_static}")
                                else:
                                    metrics["pe"] = "N/A"
                                    logger.error(f"❌ [PE Calculate - all failed] No PE data available")
                        except (ValueError, TypeError, ZeroDivisionError) as e:
                            metrics["pe"] = "N/A"
                            logger.error(f"❌ [PE Compute - Layer 2 Exceptions] Calculation failed: {e}")
                    elif net_profit and net_profit < 0:
                        # 🔥 Loss-making stocks: PE is set to N/A
                        metrics["pe"] = "N/A"
                        logger.info(f"⚠️ [PE Calculation-Lossing Stocks] Net profit is negative ({net_profit}million), PE is set to N/A")
                    else:
                        logger.warning(f"⚠️ [PE Compute - Tier 2 Skip] Net profit is invalid: {net_profit}, Try Tier 3")

                        # Third level downgrade: directly use the pe field in latest_indicators (only when it is a positive number)
                        pe_static = latest_indicators.get('pe')
                        if pe_static is not None and str(pe_static) != 'nan' and pe_static != '--':
                            try:
                                pe_float = float(pe_static)
                                # 🔥 Only accept positive numbers PE
                                if pe_float > 0:
                                    metrics["pe"] = f"{pe_float:.1f}倍"
                                    logger.info(f"✅ [PE Compute - Tier 3 Success] Use static PE: {metrics['pe']}")
                                    logger.info(f"   └─ Data source: stock_basic_info.pe")
                                else:
                                    metrics["pe"] = "N/A"
                                    logger.info(f"⚠️ [PE Calculation - Tier 3 Skip] Static PE is negative or zero (loss-making stocks): {pe_float}")
                            except (ValueError, TypeError):
                                metrics["pe"] = "N/A"
                                logger.error(f"❌ [PE Compute - Layer 3 failed] Static PE format error: {pe_static}")
                        else:
                            metrics["pe"] = "N/A"
                            logger.error(f"❌ [PE Calculate - all failed] No PE data available")

            # If PE_TTM is not obtained, try to obtain it from static data
            if pe_ttm_value is None:
                # 🔥 If it has been confirmed that it is a loss stock, directly set PE_TTM to N/A
                if is_loss_stock:
                    metrics["pe_ttm"] = "N/A"
                    logger.info(f"⚠️ [PE_TTM Calculation-Lossing Stocks] Confirmed as a loss-making stock, PE_TTM is set to N/A")
                else:
                    logger.info(f"📊 [PE_TTM Compute - Tier 2] Try to get from static data")
                    pe_ttm_static = latest_indicators.get('pe_ttm')
                    if pe_ttm_static is not None and str(pe_ttm_static) != 'nan' and pe_ttm_static != '--':
                        try:
                            pe_ttm_float = float(pe_ttm_static)
                            # 🔥 Only positive PE_TTM is accepted (PE_TTM is not displayed for losing stocks)
                            if pe_ttm_float > 0:
                                metrics["pe_ttm"] = f"{pe_ttm_float:.1f}倍"
                                logger.info(f"✅ [PE_TTM Compute - Layer 2 Success] Use static PE_TTM: {metrics['pe_ttm']}")
                                logger.info(f"   └─ Data source: stock_basic_info.pe_ttm")
                            else:
                                metrics["pe_ttm"] = "N/A"
                                logger.info(f"⚠️ [PE_TTM Compute - Tier 2 Skip] Static PE_TTM is negative or zero (loss-making stocks): {pe_ttm_float}")
                        except (ValueError, TypeError):
                            metrics["pe_ttm"] = "N/A"
                            logger.error(f"❌ [PE_TTM Compute - Layer 2 failed] Static PE_TTM format error: {pe_ttm_static}")
                    else:
                        metrics["pe_ttm"] = "N/A"
                        logger.warning(f"⚠️ [PE_TTM Calculate - all failed] No PE_TTM data available")

            if pb_value is None:
                total_equity = latest_indicators.get('total_hldr_eqy_exc_min_int')
                if total_equity and total_equity > 0:
                    try:
                        # Use market cap/net assets calculation PB
                        money_cap = latest_indicators.get('money_cap')
                        if money_cap and money_cap > 0:
                            # Note the unit conversion: money_cap is ten thousand yuan, total_equity is yuan
                            # PB = Market value(Ten thousand yuan) * 10000 / net worth(Yuan)
                            pb_calculated = (money_cap * 10000) / total_equity
                            metrics["pb"] = f"{pb_calculated:.2f}倍"
                            logger.info(f"✅ [PB计算-第2层成功] PB={pb_calculated:.2f}倍")
                            logger.info(f"   └─ 计算公式: 市值{money_cap}万元 * 10000 / 净资产{total_equity}元 = {metrics['pb']}")
                        else:
                            # Third level downgrade: directly use the pb field in latest_indicators
                            pb_static = latest_indicators.get('pb') or latest_indicators.get('pb_mrq')
                            if pb_static is not None and str(pb_static) != 'nan' and pb_static != '--':
                                try:
                                    metrics["pb"] = f"{float(pb_static):.2f}倍"
                                    logger.info(f"✅ [PB Compute - Tier 3 Success] Use static PB: {metrics['pb']}")
                                    logger.info(f"   └─ Data source: stock_basic_info.pb")
                                except (ValueError, TypeError):
                                    metrics["pb"] = "N/A"
                            else:
                                metrics["pb"] = "N/A"
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        logger.error(f"❌ [PB Compute - Layer 2 Exceptions] Calculation failed: {e}")
                        metrics["pb"] = "N/A"
                else:
                    # Third level downgrade: directly use the pb field in latest_indicators
                    pb_static = latest_indicators.get('pb') or latest_indicators.get('pb_mrq')
                    if pb_static is not None and str(pb_static) != 'nan' and pb_static != '--':
                        try:
                            metrics["pb"] = f"{float(pb_static):.2f}倍"
                            logger.info(f"✅ [PB Compute - Tier 3 Success] Use static PB: {metrics['pb']}")
                            logger.info(f"   └─ Data source: stock_basic_info.pb")
                        except (ValueError, TypeError):
                            metrics["pb"] = "N/A"
                    else:
                        metrics["pb"] = "N/A"

            # Asset-liability ratio
            debt_ratio = latest_indicators.get('debt_to_assets')
            if debt_ratio is not None and str(debt_ratio) != 'nan' and debt_ratio != '--':
                try:
                    metrics["debt_ratio"] = f"{float(debt_ratio):.1f}%"
                except (ValueError, TypeError):
                    metrics["debt_ratio"] = "N/A"
            else:
                metrics["debt_ratio"] = "N/A"

            # Calculate PS - Price to Sales Ratio (using TTM Operating Income)
            # Priority is given to using TTM operating income, if not then single period operating income is used
            revenue_ttm = latest_indicators.get('revenue_ttm')
            revenue = latest_indicators.get('revenue')

            # Choose which operating income data to use
            revenue_for_ps = revenue_ttm if revenue_ttm and revenue_ttm > 0 else revenue
            revenue_type = "TTM" if revenue_ttm and revenue_ttm > 0 else "单期"

            if revenue_for_ps and revenue_for_ps > 0:
                try:
                    # Use market cap/operating income calculation PS
                    money_cap = latest_indicators.get('money_cap')
                    if money_cap and money_cap > 0:
                        ps_calculated = money_cap / revenue_for_ps
                        metrics["ps"] = f"{ps_calculated:.2f}倍"
                        logger.debug(f"✅ 计算PS({revenue_type}): 市值{money_cap}万元 / 营业收入{revenue_for_ps}万元 = {metrics['ps']}")
                    else:
                        metrics["ps"] = "N/A"
                except (ValueError, TypeError, ZeroDivisionError):
                    metrics["ps"] = "N/A"
            else:
                metrics["ps"] = "N/A"

            # Dividend Yield - Temporarily set to N/A, dividend data required
            metrics["dividend_yield"] = "N/A"
            metrics["current_ratio"] = latest_indicators.get('current_ratio', 'N/A')
            metrics["quick_ratio"] = latest_indicators.get('quick_ratio', 'N/A')
            metrics["cash_ratio"] = latest_indicators.get('cash_ratio', 'N/A')

            # Add rating field (use default value)
            metrics["fundamental_score"] = 7.0  # Default ratings based on real data
            metrics["valuation_score"] = 6.5
            metrics["growth_score"] = 7.0
            metrics["risk_level"] = "中等"

            logger.info(f"✅ MongoDB 财务数据解析成功: ROE={metrics.get('roe')}, ROA={metrics.get('roa')}, 毛利率={metrics.get('gross_margin')}, 净利率={metrics.get('net_margin')}")
            return metrics

        except Exception as e:
            logger.error(f"❌ MongoDB Financial data parsing failed: {e}", exc_info=True)
            return None

    def _parse_akshare_financial_data(self, financial_data: dict, stock_info: dict, price_value: float) -> dict:
        """Parsing AKShare financial data into metrics"""
        try:
            # Get the latest financial data
            balance_sheet = financial_data.get('balance_sheet', [])
            income_statement = financial_data.get('income_statement', [])
            cash_flow = financial_data.get('cash_flow', [])
            main_indicators = financial_data.get('main_indicators')

            # main_indicators May be a DataFrame or list(to_dict('records') result)
            if main_indicators is None:
                logger.warning("AKShare Key financial indicators are empty")
                return None

            # Check if it is empty
            if isinstance(main_indicators, list):
                if not main_indicators:
                    logger.warning("AKShare The list of key financial indicators is empty")
                    return None
                # List format:[{indicator: value, ...}, ...]
                # Convert to DataFrame for unified processing
                import pandas as pd
                main_indicators = pd.DataFrame(main_indicators)
            elif hasattr(main_indicators, 'empty') and main_indicators.empty:
                logger.warning("AKShare Main financial indicators DataFrame is empty")
                return None

            # main_indicators It is a DataFrame and needs to be converted to dictionary format for easy search.
            # Get the latest data column (column 3, index 2)
            latest_col = main_indicators.columns[2] if len(main_indicators.columns) > 2 else None
            if not latest_col:
                logger.warning("AKShare Key financial indicators are missing data columns")
                return None

            logger.info(f"📅 Period using AKShare latest data: {latest_col}")

            # Create a mapping of metric names to values
            indicators_dict = {}
            for _, row in main_indicators.iterrows():
                indicator_name = row['指标']
                value = row[latest_col]
                indicators_dict[indicator_name] = value

            logger.debug(f"AKShare Number of main financial indicators: {len(indicators_dict)}")

            # Calculate financial indicators
            metrics = {}

            # 🔥 Prioritize trying to use real-time PE/PB calculations (consistent with MongoDB parsing)
            pe_value = None
            pe_ttm_value = None
            pb_value = None

            try:
                # Get stock code
                stock_code = stock_info.get('code', '').replace('.SH', '').replace('.SZ', '').zfill(6)
                if stock_code:
                    logger.info(f"📊 [AKShare-PE Compute - Tier 1] Try using real-time PE/PB calculations: {stock_code}")

                    from tradingagents.config.database_manager import get_database_manager
                    from tradingagents.dataflows.realtime_metrics import get_pe_pb_with_fallback

                    db_manager = get_database_manager()
                    if db_manager.is_mongodb_available():
                        client = db_manager.get_mongodb_client()

                        # Get real time PE/PB
                        realtime_metrics = get_pe_pb_with_fallback(stock_code, client)

                        if realtime_metrics:
                            # Get total market capitalization
                            market_cap = realtime_metrics.get('market_cap')
                            if market_cap is not None and market_cap > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["total_mv"] = f"{market_cap:.2f}亿元{realtime_tag}"
                                logger.info(f"✅ [AKShare-总市值获取成功] 总市值={market_cap:.2f}亿元 | 实时={is_realtime}")

                            # Use real-time PE
                            pe_value = realtime_metrics.get('pe')
                            if pe_value is not None and pe_value > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["pe"] = f"{pe_value:.1f}倍{realtime_tag}"
                                logger.info(f"✅ [AKShare-PE计算-第1层成功] PE={pe_value:.2f}倍 | 来源={realtime_metrics.get('source')} | 实时={is_realtime}")

                            # Use real-time PE_TTM
                            pe_ttm_value = realtime_metrics.get('pe_ttm')
                            if pe_ttm_value is not None and pe_ttm_value > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["pe_ttm"] = f"{pe_ttm_value:.1f}倍{realtime_tag}"
                                logger.info(f"✅ [AKShare-PE_TTM计算-第1层成功] PE_TTM={pe_ttm_value:.2f}倍")

                            # Use real-time PB
                            pb_value = realtime_metrics.get('pb')
                            if pb_value is not None and pb_value > 0:
                                is_realtime = realtime_metrics.get('is_realtime', False)
                                realtime_tag = " (实时)" if is_realtime else ""
                                metrics["pb"] = f"{pb_value:.2f}倍{realtime_tag}"
                                logger.info(f"✅ [AKShare-PB计算-第1层成功] PB={pb_value:.2f}倍")
                        else:
                            logger.warning(f"⚠️ [AKShare-PE Compute - Tier 1 failed] Real-time calculations return empty results, and downgrade calculations will be attempted.")
            except Exception as e:
                logger.warning(f"⚠️ [AKShare-PE Compute - Layer 1 Exception] Real-time calculation failed: {e}, Will try to downgrade the calculation")

            # Get ROE - directly from the indicator
            roe_value = indicators_dict.get('净资产收益率(ROE)')
            if roe_value is not None and str(roe_value) != 'nan' and roe_value != '--':
                try:
                    roe_val = float(roe_value)
                    # ROE Usually in percentage form
                    metrics["roe"] = f"{roe_val:.1f}%"
                    logger.debug(f"✅ 获取ROE: {metrics['roe']}")
                except (ValueError, TypeError):
                    metrics["roe"] = "N/A"
            else:
                metrics["roe"] = "N/A"

            # If real-time calculation fails, try to get total market cap from stock_info
            if "total_mv" not in metrics:
                logger.info(f"📊 [AKShare-Total Market Cap - Tier 2] Try to get from stock_info")
                total_mv_static = stock_info.get('total_mv')
                if total_mv_static is not None and total_mv_static > 0:
                    metrics["total_mv"] = f"{total_mv_static:.2f}亿元"
                    logger.info(f"✅ [AKShare-总市值-第2层成功] 总市值={total_mv_static:.2f}亿元")
                else:
                    metrics["total_mv"] = "N/A"
                    logger.warning(f"⚠️ [AKShare-Total Market Cap - All Failed] No total market capitalization data available")

            # 🔥 If real-time calculation fails, fall back to traditional calculation method
            if pe_value is None:
                logger.info(f"📊 [AKShare-PE Compute - Tier 2] Try using the share price/EPS calculation")

                # Calculate PE - Prefer TTM data
                # Try to calculate from main_indicators DataFrame TTM EPS
                ttm_eps = None
                try:
                    # main_indicators Is a DataFrame containing multiple periods of data
                    # try to calculate TTM EPS
                    if '基本每股收益' in main_indicators['指标'].values:
                        # Extract all period data of basic earnings per share
                        eps_row = main_indicators[main_indicators['指标'] == '基本每股收益']
                        if not eps_row.empty:
                            # Get all numeric columns (excluding'indicator'column)
                            value_cols = [col for col in eps_row.columns if col != '指标']

                            # Build DataFrame for TTM calculation
                            import pandas as pd
                            eps_data = []
                            for col in value_cols:
                                eps_val = eps_row[col].iloc[0]
                                if eps_val is not None and str(eps_val) != 'nan' and eps_val != '--':
                                    eps_data.append({'报告期': col, '基本每股收益': eps_val})

                            if len(eps_data) >= 2:
                                eps_df = pd.DataFrame(eps_data)
                                # Use the TTM calculation function
                                from scripts.sync_financial_data import _calculate_ttm_metric
                                ttm_eps = _calculate_ttm_metric(eps_df, '基本每股收益')
                                if ttm_eps:
                                    logger.info(f"✅ 计算 TTM EPS: {ttm_eps:.4f} 元")
                except Exception as e:
                    logger.debug(f"Calculating TTM EPS failed: {e}")

                # Calculated using TTM EPS or Single Period EPS PE
                eps_for_pe = ttm_eps if ttm_eps else None
                pe_type = "TTM" if ttm_eps else "单期"

                if not eps_for_pe:
                    # Downgrade to single issue EPS
                    eps_value = indicators_dict.get('基本每股收益')
                    if eps_value is not None and str(eps_value) != 'nan' and eps_value != '--':
                        try:
                            eps_for_pe = float(eps_value)
                        except (ValueError, TypeError):
                            pass

                if eps_for_pe and eps_for_pe > 0:
                    pe_val = price_value / eps_for_pe
                    metrics["pe"] = f"{pe_val:.1f}倍"
                    logger.info(f"✅ [AKShare-PE计算-第2层成功] PE({pe_type}): 股价{price_value} / EPS{eps_for_pe:.4f} = {metrics['pe']}")
                elif eps_for_pe and eps_for_pe <= 0:
                    metrics["pe"] = "N/A（亏损）"
                    logger.warning(f"⚠️ [AKShare-PE Compute - Layer 2 failed] losing stocks,EPS={eps_for_pe}")
                else:
                    metrics["pe"] = "N/A"
                    logger.error(f"❌ [AKShare-PE Calculate - all failed] No EPS data available")

            # 🔥 If real-time PB calculation fails, downgrade to traditional calculation method
            if pb_value is None:
                logger.info(f"📊 [AKShare-PB Compute - Tier 2] Try using stock price/BPS calculation")

                # Get net assets per share - used in calculations PB
                bps_value = indicators_dict.get('每股净资产_最新股数')
                if bps_value is not None and str(bps_value) != 'nan' and bps_value != '--':
                    try:
                        bps_val = float(bps_value)
                        if bps_val > 0:
                            # Calculate PB = Stock price / Net assets per share
                            pb_val = price_value / bps_val
                            metrics["pb"] = f"{pb_val:.2f}倍"
                            logger.info(f"✅ [AKShare-PB Compute - Layer 2 Success] PB: stock price{price_value} / BPS{bps_val} = {metrics['pb']}")
                        else:
                            metrics["pb"] = "N/A"
                            logger.warning(f"⚠️ [AKShare-PB Compute - Layer 2 failed] BPS Invalid: {bps_val}")
                    except (ValueError, TypeError) as e:
                        metrics["pb"] = "N/A"
                        logger.error(f"❌ [AKShare-PB Compute - Layer 2 Exceptions] {e}")
                else:
                    metrics["pb"] = "N/A"
                    logger.error(f"❌ [AKShare-PB Calculate - all failed] No BPS data available")

            # Try to get other metrics
            # return on total assets(ROA)
            roa_value = indicators_dict.get('总资产报酬率')
            if roa_value is not None and str(roa_value) != 'nan' and roa_value != '--':
                try:
                    roa_val = float(roa_value)
                    metrics["roa"] = f"{roa_val:.1f}%"
                except (ValueError, TypeError):
                    metrics["roa"] = "N/A"
            else:
                metrics["roa"] = "N/A"

            # Gross profit margin
            gross_margin_value = indicators_dict.get('毛利率')
            if gross_margin_value is not None and str(gross_margin_value) != 'nan' and gross_margin_value != '--':
                try:
                    gross_margin_val = float(gross_margin_value)
                    metrics["gross_margin"] = f"{gross_margin_val:.1f}%"
                except (ValueError, TypeError):
                    metrics["gross_margin"] = "N/A"
            else:
                metrics["gross_margin"] = "N/A"

            # net sales profit margin
            net_margin_value = indicators_dict.get('销售净利率')
            if net_margin_value is not None and str(net_margin_value) != 'nan' and net_margin_value != '--':
                try:
                    net_margin_val = float(net_margin_value)
                    metrics["net_margin"] = f"{net_margin_val:.1f}%"
                except (ValueError, TypeError):
                    metrics["net_margin"] = "N/A"
            else:
                metrics["net_margin"] = "N/A"

            # Asset-liability ratio
            debt_ratio_value = indicators_dict.get('资产负债率')
            if debt_ratio_value is not None and str(debt_ratio_value) != 'nan' and debt_ratio_value != '--':
                try:
                    debt_ratio_val = float(debt_ratio_value)
                    metrics["debt_ratio"] = f"{debt_ratio_val:.1f}%"
                except (ValueError, TypeError):
                    metrics["debt_ratio"] = "N/A"
            else:
                metrics["debt_ratio"] = "N/A"

            # current ratio
            current_ratio_value = indicators_dict.get('流动比率')
            if current_ratio_value is not None and str(current_ratio_value) != 'nan' and current_ratio_value != '--':
                try:
                    current_ratio_val = float(current_ratio_value)
                    metrics["current_ratio"] = f"{current_ratio_val:.2f}"
                except (ValueError, TypeError):
                    metrics["current_ratio"] = "N/A"
            else:
                metrics["current_ratio"] = "N/A"

            # quick ratio
            quick_ratio_value = indicators_dict.get('速动比率')
            if quick_ratio_value is not None and str(quick_ratio_value) != 'nan' and quick_ratio_value != '--':
                try:
                    quick_ratio_val = float(quick_ratio_value)
                    metrics["quick_ratio"] = f"{quick_ratio_val:.2f}"
                except (ValueError, TypeError):
                    metrics["quick_ratio"] = "N/A"
            else:
                metrics["quick_ratio"] = "N/A"

            # Calculate PS - Price to Sales ratio (preferred using TTM operating income)
            # Trying to calculate TTM operating income from main_indicators DataFrame
            ttm_revenue = None
            try:
                if '营业收入' in main_indicators['指标'].values:
                    revenue_row = main_indicators[main_indicators['指标'] == '营业收入']
                    if not revenue_row.empty:
                        value_cols = [col for col in revenue_row.columns if col != '指标']

                        import pandas as pd
                        revenue_data = []
                        for col in value_cols:
                            rev_val = revenue_row[col].iloc[0]
                            if rev_val is not None and str(rev_val) != 'nan' and rev_val != '--':
                                revenue_data.append({'报告期': col, '营业收入': rev_val})

                        if len(revenue_data) >= 2:
                            revenue_df = pd.DataFrame(revenue_data)
                            from scripts.sync_financial_data import _calculate_ttm_metric
                            ttm_revenue = _calculate_ttm_metric(revenue_df, '营业收入')
                            if ttm_revenue:
                                logger.info(f"✅ 计算 TTM 营业收入: {ttm_revenue:.2f} 万元")
            except Exception as e:
                logger.debug(f"Calculating TTM operating income failed: {e}")

            # Calculate PS
            revenue_for_ps = ttm_revenue if ttm_revenue else None
            ps_type = "TTM" if ttm_revenue else "单期"

            if not revenue_for_ps:
                # Downgraded to single-period operating income
                revenue_value = indicators_dict.get('营业收入')
                if revenue_value is not None and str(revenue_value) != 'nan' and revenue_value != '--':
                    try:
                        revenue_for_ps = float(revenue_value)
                    except (ValueError, TypeError):
                        pass

            if revenue_for_ps and revenue_for_ps > 0:
                # Get total share capital and calculate market capitalization
                total_share = stock_info.get('total_share') if stock_info else None
                if total_share and total_share > 0:
                    # Market value (10,000 yuan)= Stock price (yuan)× Total share capital (10,000 shares)
                    market_cap = price_value * total_share
                    ps_val = market_cap / revenue_for_ps
                    metrics["ps"] = f"{ps_val:.2f}倍"
                    logger.info(f"✅ 计算PS({ps_type}): 市值{market_cap:.2f}万元 / 营业收入{revenue_for_ps:.2f}万元 = {metrics['ps']}")
                else:
                    metrics["ps"] = "N/A（无总股本数据）"
                    logger.warning(f"⚠️ Unable to calculate PS: Missing total share capital data")
            else:
                metrics["ps"] = "N/A"

            # Supplement the default values of other indicators
            metrics.update({
                "dividend_yield": "待查询",
                "cash_ratio": "待分析"
            })

            # Rating (simplified rating based on AKShare data)
            fundamental_score = self._calculate_fundamental_score(metrics, stock_info)
            valuation_score = self._calculate_valuation_score(metrics)
            growth_score = self._calculate_growth_score(metrics, stock_info)
            risk_level = self._calculate_risk_level(metrics, stock_info)

            metrics.update({
                "fundamental_score": fundamental_score,
                "valuation_score": valuation_score,
                "growth_score": growth_score,
                "risk_level": risk_level,
                "data_source": "AKShare"
            })

            logger.info(f"✅ AKShare Financial data parsed successfully: PE={metrics['pe']}, PB={metrics['pb']}, ROE={metrics['roe']}")
            return metrics

        except Exception as e:
            logger.error(f"❌ AKShare Financial data parsing failed: {e}")
            return None

    def _parse_financial_data(self, financial_data: dict, stock_info: dict, price_value: float) -> dict:
        """解析财务数据为指标"""
        try:
            # Get the latest financial data
            balance_sheet = financial_data.get('balance_sheet', [])
            income_statement = financial_data.get('income_statement', [])
            cash_flow = financial_data.get('cash_flow', [])

            if not (balance_sheet or income_statement):
                return None

            latest_balance = balance_sheet[0] if balance_sheet else {}
            latest_income = income_statement[0] if income_statement else {}
            latest_cash = cash_flow[0] if cash_flow else {}

            # Calculate financial indicators
            metrics = {}

            # Basic data
            total_assets = latest_balance.get('total_assets', 0) or 0
            total_liab = latest_balance.get('total_liab', 0) or 0
            total_equity = latest_balance.get('total_hldr_eqy_exc_min_int', 0) or 0

            # Calculate TTM operating income and net profit
            # Tushare income_statement The data for are cumulative values (from the beginning of the year to the reporting period)
            # Need to use TTM formula calculation
            ttm_revenue = None
            ttm_net_income = None

            try:
                if len(income_statement) >= 2:
                    # Prepare data for TTM calculations
                    import pandas as pd

                    # Build operating income DataFrame
                    revenue_data = []
                    for stmt in income_statement:
                        end_date = stmt.get('end_date')
                        revenue = stmt.get('total_revenue')
                        if end_date and revenue is not None:
                            revenue_data.append({'报告期': str(end_date), '营业收入': float(revenue)})

                    if len(revenue_data) >= 2:
                        revenue_df = pd.DataFrame(revenue_data)
                        from scripts.sync_financial_data import _calculate_ttm_metric
                        ttm_revenue = _calculate_ttm_metric(revenue_df, '营业收入')
                        if ttm_revenue:
                            logger.info(f"✅ Tushare 计算 TTM 营业收入: {ttm_revenue:.2f} 万元")

                    # Build net profit DataFrame
                    profit_data = []
                    for stmt in income_statement:
                        end_date = stmt.get('end_date')
                        profit = stmt.get('n_income')
                        if end_date and profit is not None:
                            profit_data.append({'报告期': str(end_date), '净利润': float(profit)})

                    if len(profit_data) >= 2:
                        profit_df = pd.DataFrame(profit_data)
                        ttm_net_income = _calculate_ttm_metric(profit_df, '净利润')
                        if ttm_net_income:
                            logger.info(f"✅ Tushare 计算 TTM 净利润: {ttm_net_income:.2f} 万元")
            except Exception as e:
                logger.warning(f"⚠️ Tushare TTM Calculation failed: {e}")

            # Downgrade to single period data
            total_revenue = ttm_revenue if ttm_revenue else (latest_income.get('total_revenue', 0) or 0)
            net_income = ttm_net_income if ttm_net_income else (latest_income.get('n_income', 0) or 0)
            operate_profit = latest_income.get('operate_profit', 0) or 0

            revenue_type = "TTM" if ttm_revenue else "单期"
            profit_type = "TTM" if ttm_net_income else "单期"

            # Get actual total share capital to calculate market capitalization
            # Get it from stock_info first. If not, accurate valuation indicators cannot be calculated.
            total_share = stock_info.get('total_share') if stock_info else None

            if total_share and total_share > 0:
                # Market value (yuan)= Stock price (yuan)× Total share capital (10,000 shares)× 10000
                market_cap = price_value * total_share * 10000
                market_cap_yi = market_cap / 100000000  # Convert to 100 million yuan
                metrics["total_mv"] = f"{market_cap_yi:.2f}亿元"
                logger.info(f"✅ [Tushare-总市值计算成功] 总市值={market_cap_yi:.2f}亿元 (股价{price_value}元 × 总股本{total_share}万股)")
            else:
                logger.error(f"❌ {stock_info.get('code', 'Unknown')} Total share capital cannot be obtained and accurate valuation indicators cannot be calculated.")
                market_cap = None
                metrics["total_mv"] = "N/A"

            # Calculate various indicators (only calculated when accurate market capitalization is available)
            if market_cap:
                # PE Ratio (TTM Net Profit preferred)
                if net_income > 0:
                    pe_ratio = market_cap / (net_income * 10000)  # Convert units
                    metrics["pe"] = f"{pe_ratio:.1f}倍"
                    logger.info(f"✅ Tushare 计算PE({profit_type}): 市值{market_cap/100000000:.2f}亿元 / 净利润{net_income:.2f}万元 = {pe_ratio:.1f}倍")
                else:
                    metrics["pe"] = "N/A（亏损）"

                # PB Ratio (net assets use the latest data, which is relatively accurate)
                if total_equity > 0:
                    pb_ratio = market_cap / (total_equity * 10000)
                    metrics["pb"] = f"{pb_ratio:.2f}倍"
                else:
                    metrics["pb"] = "N/A"

                # PS Ratio (TTM operating income preferred)
                if total_revenue > 0:
                    ps_ratio = market_cap / (total_revenue * 10000)
                    metrics["ps"] = f"{ps_ratio:.1f}倍"
                    logger.info(f"✅ Tushare 计算PS({revenue_type}): 市值{market_cap/100000000:.2f}亿元 / 营业收入{total_revenue:.2f}万元 = {ps_ratio:.1f}倍")
                else:
                    metrics["ps"] = "N/A"
            else:
                # Total share capital cannot be obtained and valuation indicators cannot be calculated.
                metrics["pe"] = "N/A（无总股本数据）"
                metrics["pb"] = "N/A（无总股本数据）"
                metrics["ps"] = "N/A（无总股本数据）"

            # ROE
            if total_equity > 0 and net_income > 0:
                roe = (net_income / total_equity) * 100
                metrics["roe"] = f"{roe:.1f}%"
            else:
                metrics["roe"] = "N/A"

            # ROA
            if total_assets > 0 and net_income > 0:
                roa = (net_income / total_assets) * 100
                metrics["roa"] = f"{roa:.1f}%"
            else:
                metrics["roa"] = "N/A"

            # net profit margin
            if total_revenue > 0 and net_income > 0:
                net_margin = (net_income / total_revenue) * 100
                metrics["net_margin"] = f"{net_margin:.1f}%"
            else:
                metrics["net_margin"] = "N/A"

            # Asset-liability ratio
            if total_assets > 0:
                debt_ratio = (total_liab / total_assets) * 100
                metrics["debt_ratio"] = f"{debt_ratio:.1f}%"
            else:
                metrics["debt_ratio"] = "N/A"

            # Other indicators are set to default values
            metrics.update({
                "dividend_yield": "待查询",
                "gross_margin": "待计算",
                "current_ratio": "待计算",
                "quick_ratio": "待计算",
                "cash_ratio": "待分析"
            })

            # Rating (simplified rating based on real data)
            fundamental_score = self._calculate_fundamental_score(metrics, stock_info)
            valuation_score = self._calculate_valuation_score(metrics)
            growth_score = self._calculate_growth_score(metrics, stock_info)
            risk_level = self._calculate_risk_level(metrics, stock_info)

            metrics.update({
                "fundamental_score": fundamental_score,
                "valuation_score": valuation_score,
                "growth_score": growth_score,
                "risk_level": risk_level
            })

            return metrics

        except Exception as e:
            logger.error(f"解析财务数据失败: {e}")
            return None

    def _calculate_fundamental_score(self, metrics: dict, stock_info: dict) -> float:
        """计算基本面评分"""
        score = 5.0  # Basic points

        # ROE Rating
        roe_str = metrics.get("roe", "N/A")
        if roe_str != "N/A":
            try:
                roe = float(roe_str.replace("%", ""))
                if roe > 15:
                    score += 1.5
                elif roe > 10:
                    score += 1.0
                elif roe > 5:
                    score += 0.5
            except:
                pass

        # Net profit margin score
        net_margin_str = metrics.get("net_margin", "N/A")
        if net_margin_str != "N/A":
            try:
                net_margin = float(net_margin_str.replace("%", ""))
                if net_margin > 20:
                    score += 1.0
                elif net_margin > 10:
                    score += 0.5
            except:
                pass

        return min(score, 10.0)

    def _calculate_valuation_score(self, metrics: dict) -> float:
        """计算估值评分"""
        score = 5.0  # Basic points

        # PE Rating
        pe_str = metrics.get("pe", "N/A")
        if pe_str != "N/A" and "亏损" not in pe_str:
            try:
                pe = float(pe_str.replace("倍", ""))
                if pe < 15:
                    score += 2.0
                elif pe < 25:
                    score += 1.0
                elif pe > 50:
                    score -= 1.0
            except:
                pass

        # PB Rating
        pb_str = metrics.get("pb", "N/A")
        if pb_str != "N/A":
            try:
                pb = float(pb_str.replace("倍", ""))
                if pb < 1.5:
                    score += 1.0
                elif pb < 3:
                    score += 0.5
                elif pb > 5:
                    score -= 0.5
            except:
                pass

        return min(max(score, 1.0), 10.0)

    def _calculate_growth_score(self, metrics: dict, stock_info: dict) -> float:
        """计算成长性评分"""
        score = 6.0  # Basic points

        # Adjust according to industry
        industry = stock_info.get('industry', '')
        if '科技' in industry or '软件' in industry or '互联网' in industry:
            score += 1.0
        elif '银行' in industry or '保险' in industry:
            score -= 0.5

        return min(max(score, 1.0), 10.0)

    def _calculate_risk_level(self, metrics: dict, stock_info: dict) -> str:
        """计算风险等级"""
        # Asset-liability ratio
        debt_ratio_str = metrics.get("debt_ratio", "N/A")
        if debt_ratio_str != "N/A":
            try:
                debt_ratio = float(debt_ratio_str.replace("%", ""))
                if debt_ratio > 70:
                    return "较高"
                elif debt_ratio > 50:
                    return "中等"
                else:
                    return "较低"
            except:
                pass

        # Based on industry judgment
        industry = stock_info.get('industry', '')
        if '银行' in industry:
            return "中等"
        elif '科技' in industry or '创业板' in industry:
            return "较高"

        return "中等"



    def _analyze_valuation(self, financial_estimates: dict) -> str:
        """分析估值水平"""
        valuation_score = financial_estimates['valuation_score']

        if valuation_score >= 8:
            return "The current valuation level is relatively reasonable and has certain investment value. The price-to-earnings ratio and price-to-book ratio are relatively low, and the margin of safety is high."
        elif valuation_score >= 6:
            return "The valuation level is moderate, and it is necessary to comprehensively judge the investment value based on fundamentals and growth."
        else:
            return "The current valuation is on the high side, so investment needs to be cautious. It is recommended to wait for a better buying opportunity."

    def _analyze_growth_potential(self, symbol: str, industry_info: dict) -> str:
        """分析成长潜力"""
        if symbol.startswith(('000001', '600036')):
            return "The overall growth of the banking industry is stable, benefiting from economic development and financial deepening. Digital transformation and wealth management business are the main growth points."
        elif symbol.startswith('300'):
            return "GEM companies usually have higher growth potential, but are also accompanied by higher risks. It is necessary to pay attention to technological innovation and market expansion capabilities."
        else:
            return "Growth potential needs to be combined with specific industry and company fundamental analysis. It is recommended to pay attention to industry development trends and company competitive advantages."

    def _analyze_risks(self, symbol: str, financial_estimates: dict, industry_info: dict) -> str:
        """分析投资风险"""
        risk_level = financial_estimates['risk_level']

        risk_analysis = f"**风险等级**: {risk_level}\n\n"

        if symbol.startswith(('000001', '600036')):
            risk_analysis += """**Main risks**:
- The impact of changes in the interest rate environment on net interest margin
- Credit asset quality risk
- Risks of regulatory policy changes
- The impact of macroeconomic downturn on the banking industry"""
        elif symbol.startswith('300'):
            risk_analysis += """**Main risks**:
- Risks of technological upgrading
- Risks of intensifying market competition
- Valuations fluctuate greatly
- Performance uncertainty is high"""
        else:
            risk_analysis += """**Main risks**:
- Industry cyclical risks
- Changes in the macroeconomic environment
- Market competition risk
- Policy adjustment risk"""

        return risk_analysis

    def _generate_investment_advice(self, financial_estimates: dict, industry_info: dict) -> str:
        """生成投资建议"""
        fundamental_score = financial_estimates['fundamental_score']
        valuation_score = financial_estimates['valuation_score']
        growth_score = financial_estimates['growth_score']

        total_score = (fundamental_score + valuation_score + growth_score) / 3

        if total_score >= 7.5:
            return """**investment advice**: 🟢 **buy**
- Good fundamentals, reasonable valuation, and good investment value
- It is recommended to build positions in batches and hold them for the long term.
- Suitable for value investors and conservative investors"""
        elif total_score >= 6.0:
            return """**investment advice**: 🟡 **wait and see**
- Fundamentals are average, need further observation
- You can test with small positions and wait for a better opportunity
- Suitable for experienced investors"""
        else:
            return """**investment advice**: 🔴 **Avoid**
- The current risk is high and investment is not recommended
- It is recommended to wait for fundamentals to improve or valuations to fall back.
- Investors with lower risk tolerance should avoid"""

    def _try_get_old_cache(self, symbol: str, start_date: str, end_date: str) -> Optional[str]:
        """Try to get expired cached data as backup"""
        try:
            # Find any relevant caches, regardless of TTL
            for metadata_file in self.cache.metadata_dir.glob(f"*_meta.json"):
                try:
                    import json

                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    if (metadata.get('symbol') == symbol and
                        metadata.get('data_type') == 'stock_data' and
                        metadata.get('market_type') == 'china'):

                        cache_key = metadata_file.stem.replace('_meta', '')
                        cached_data = self.cache.load_stock_data(cache_key)
                        if cached_data:
                            return cached_data + "\n\n⚠️ Note: Using expired cached data"
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def _generate_fallback_data(self, symbol: str, start_date: str, end_date: str, error_msg: str) -> str:
        """生成备用数据"""
        return f"""# {symbol} A股数据获取失败

## ❌ 错误信息
{error_msg}

## 📊 模拟数据（仅供演示）
- 股票代码: {symbol}
- 股票名称: 模拟公司
- 数据期间: {start_date} 至 {end_date}
- 模拟价格: ¥{random.uniform(10, 50):.2f}
- 模拟涨跌: {random.uniform(-5, 5):+.2f}%

## ⚠️ 重要提示
由于数据接口限制或网络问题，无法获取实时数据。
建议稍后重试或检查网络连接。

生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""

    def _generate_fallback_fundamentals(self, symbol: str, error_msg: str) -> str:
        """生成备用基本面数据"""
        return f"""# {symbol} A Stock fundamental analysis fails

## ❌ error message
{error_msg}

## 📊 Basic information
- Stock code: {symbol}
- analysis status: Data acquisition failed
- Suggestions: Try again later or check network connection

Generation time: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""


# global instance
_china_data_provider = None

def get_optimized_china_data_provider() -> OptimizedChinaDataProvider:
    """Get the global A-share data provider instance"""
    global _china_data_provider
    if _china_data_provider is None:
        _china_data_provider = OptimizedChinaDataProvider()
    return _china_data_provider


def get_china_stock_data_cached(symbol: str, start_date: str, end_date: str,
                               force_refresh: bool = False) -> str:
    """
    Convenient function to obtain A-share data

    Args:
        symbol: Stock code (6 digits)
        start_date: start date (YYYY-MM-DD)
        end_date: end date (YYYY-MM-DD)
        force_refresh: Whether to force cache refresh

    Returns:
        Formatted stock data string
    """
    provider = get_optimized_china_data_provider()
    return provider.get_stock_data(symbol, start_date, end_date, force_refresh)


def get_china_fundamentals_cached(symbol: str, force_refresh: bool = False) -> str:
    """
    Convenient function to obtain A-share fundamental data

    Args:
        symbol: Stock code (6 digits)
        force_refresh: Whether to force cache refresh

    Returns:
        Formatted fundamental data string
    """
    provider = get_optimized_china_data_provider()
    return provider.get_fundamentals_data(symbol, force_refresh)


# Add caching method in OptimizedChinaDataProvider class
def _add_financial_cache_methods():
    """Add financial data caching method to OptimizedChinaDataProvider class"""

    def _get_cached_raw_financial_data(self, symbol: str) -> dict:
        """Get raw financial data from database cache"""
        try:
            from .cache.app_adapter import get_mongodb_client
            client = get_mongodb_client()
            if not client:
                logger.debug(f"📊 [financial cache] MongoDB Client is unavailable")
                return None

            db = client.get_database('tradingagents')

            # First priority: reading from the stock_financial_data collection (persistent data synchronized by scheduled tasks)
            stock_financial_collection = db.stock_financial_data

            # Try using symbol or code field query (compatible with different synchronization services)
            financial_doc = stock_financial_collection.find_one({
                '$or': [
                    {'symbol': symbol},
                    {'code': symbol}
                ]
            }, sort=[('updated_at', -1)])

            if financial_doc:
                logger.info(f"✅ [财务数据] 从 stock_financial_data 集合获取{symbol}财务数据")
                # Convert database documents to financial data format
                financial_data = {}

                # Extract various financial data
                # First priority: Check the raw_data field (structure used by Tushare synchronization service)
                if 'raw_data' in financial_doc and isinstance(financial_doc['raw_data'], dict):
                    raw_data = financial_doc['raw_data']
                    # Mapping field name: cashflow_statement is used in raw_data, we need cash_flow
                    if 'balance_sheet' in raw_data and raw_data['balance_sheet']:
                        financial_data['balance_sheet'] = raw_data['balance_sheet']
                    if 'income_statement' in raw_data and raw_data['income_statement']:
                        financial_data['income_statement'] = raw_data['income_statement']
                    if 'cashflow_statement' in raw_data and raw_data['cashflow_statement']:
                        financial_data['cash_flow'] = raw_data['cashflow_statement']  # Pay attention to field name mapping
                    if 'financial_indicators' in raw_data and raw_data['financial_indicators']:
                        financial_data['main_indicators'] = raw_data['financial_indicators']  # Pay attention to field name mapping
                    if 'main_business' in raw_data and raw_data['main_business']:
                        financial_data['main_business'] = raw_data['main_business']

                # Second priority: Check the financial_data nested field
                elif 'financial_data' in financial_doc and isinstance(financial_doc['financial_data'], dict):
                    nested_data = financial_doc['financial_data']
                    if 'balance_sheet' in nested_data:
                        financial_data['balance_sheet'] = nested_data['balance_sheet']
                    if 'income_statement' in nested_data:
                        financial_data['income_statement'] = nested_data['income_statement']
                    if 'cash_flow' in nested_data:
                        financial_data['cash_flow'] = nested_data['cash_flow']
                    if 'main_indicators' in nested_data:
                        financial_data['main_indicators'] = nested_data['main_indicators']

                # Third priority: read directly from the document root level
                else:
                    if 'balance_sheet' in financial_doc and financial_doc['balance_sheet']:
                        financial_data['balance_sheet'] = financial_doc['balance_sheet']
                    if 'income_statement' in financial_doc and financial_doc['income_statement']:
                        financial_data['income_statement'] = financial_doc['income_statement']
                    if 'cash_flow' in financial_doc and financial_doc['cash_flow']:
                        financial_data['cash_flow'] = financial_doc['cash_flow']
                    if 'main_indicators' in financial_doc and financial_doc['main_indicators']:
                        financial_data['main_indicators'] = financial_doc['main_indicators']

                if financial_data:
                    logger.info(f"📊 [financial data] successfully extracted{symbol}financial data, including fields: {list(financial_data.keys())}")
                    return financial_data
                else:
                    logger.warning(f"⚠️ [财务数据] {symbol}的 stock_financial_data 记录存在但无有效财务数据字段")
            else:
                logger.debug(f"📊 [财务数据] stock_financial_data 集合中未找到{symbol}的记录")

            # Second priority: reading from the financial_data_cache collection (temporary cache)
            collection = db.financial_data_cache

            # Find cached raw financial data
            cache_doc = collection.find_one({
                'symbol': symbol,
                'cache_type': 'raw_financial_data'
            }, sort=[('updated_at', -1)])

            if cache_doc:
                # Check if cache is expired (24 hours)
                from datetime import datetime, timedelta
                cache_time = cache_doc.get('updated_at')
                if cache_time and datetime.now() - cache_time < timedelta(hours=24):
                    financial_data = cache_doc.get('financial_data', {})
                    if financial_data:
                        logger.info(f"✅ [财务缓存] 从 financial_data_cache 获取{symbol}原始财务数据")
                        return financial_data
                else:
                    logger.debug(f"📊 [财务缓存] {symbol}原始财务数据缓存已过期")
            else:
                logger.debug(f"📊 [财务缓存] 未找到{symbol}原始财务数据缓存")

        except Exception as e:
            logger.debug(f"📊 [财务缓存] 获取{symbol}原始财务数据缓存失败: {e}")

        return None

    def _get_cached_stock_info(self, symbol: str) -> dict:
        """Get basic stock information from database cache"""
        try:
            from .cache.app_adapter import get_mongodb_client
            client = get_mongodb_client()
            if not client:
                return {}

            db = client.get_database('tradingagents')
            collection = db.stock_basic_info

            # Find basic stock information
            doc = collection.find_one({'code': symbol})
            if doc:
                return {
                    'symbol': symbol,
                    'name': doc.get('name', ''),
                    'industry': doc.get('industry', ''),
                    'market': doc.get('market', ''),
                    'source': 'database_cache'
                }
        except Exception as e:
            logger.debug(f"📊 获取{symbol}股票基本信息缓存失败: {e}")

        return {}

    def _restore_financial_data_format(self, cached_data: dict) -> dict:
        """Restore cached financial data to DataFrame format"""
        try:
            import pandas as pd
            restored_data = {}

            for key, value in cached_data.items():
                if isinstance(value, list) and value:  # If it is data in list format
                    # Convert back DataFrame
                    restored_data[key] = pd.DataFrame(value)
                else:
                    restored_data[key] = value

            return restored_data
        except Exception as e:
            logger.debug(f"📊 Failed to restore financial data format: {e}")
            return cached_data

    def _cache_raw_financial_data(self, symbol: str, financial_data: dict, stock_info: dict):
        """Cache raw financial data to database"""
        try:
            from tradingagents.config.runtime_settings import use_app_cache_enabled
            if not use_app_cache_enabled(False):
                logger.debug(f"📊 [financial cache] App cache is not enabled, skip cache saving")
                return

            from .cache.app_adapter import get_mongodb_client
            client = get_mongodb_client()
            if not client:
                logger.debug(f"📊 [financial cache] MongoDB Client is unavailable")
                return

            db = client.get_database('tradingagents')
            collection = db.financial_data_cache

            from datetime import datetime

            # Convert DataFrame to serializable format
            serializable_data = {}
            for key, value in financial_data.items():
                if hasattr(value, 'to_dict'):  # pandas DataFrame
                    serializable_data[key] = value.to_dict('records')
                else:
                    serializable_data[key] = value

            cache_doc = {
                'symbol': symbol,
                'cache_type': 'raw_financial_data',
                'financial_data': serializable_data,
                'stock_info': stock_info,
                'updated_at': datetime.now()
            }

            # Update or insert using upsert
            collection.replace_one(
                {'symbol': symbol, 'cache_type': 'raw_financial_data'},
                cache_doc,
                upsert=True
            )

            logger.info(f"✅ [财务缓存] {symbol}原始财务数据已缓存到数据库")

        except Exception as e:
            logger.debug(f"📊 [财务缓存] 缓存{symbol}原始财务数据失败: {e}")

    # Add method to class
    OptimizedChinaDataProvider._get_cached_raw_financial_data = _get_cached_raw_financial_data
    OptimizedChinaDataProvider._get_cached_stock_info = _get_cached_stock_info
    OptimizedChinaDataProvider._restore_financial_data_format = _restore_financial_data_format
    OptimizedChinaDataProvider._cache_raw_financial_data = _cache_raw_financial_data

# Add execution method
_add_financial_cache_methods()
