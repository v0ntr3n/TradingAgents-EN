"""
Market/index analysis tool function

Provides functions such as index trend analysis, market breadth analysis, and market environment assessment.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd

from core.tools.trade_date_policy import apply_stable_data_cutoff, build_stable_data_cutoff_note

logger = logging.getLogger(__name__)

MARGIN_CORE_EXCHANGES = ("SSE", "SZSE")
MARGIN_BSE_AVAILABLE_SINCE = "20211115"


def _clean_date_string(date_str: str) -> str:
    """Clean date string, remove possible time part"""
    if not date_str:
        return date_str
    return date_str.split()[0] if ' ' in date_str else date_str


def _format_compact_trade_date(trade_date: str) -> str:
    """Convert YYYYMMDD format to YYYY-MM-DD."""
    if not trade_date or len(trade_date) != 8 or not trade_date.isdigit():
        return trade_date
    return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"


def _get_required_margin_exchanges(trade_date: str) -> List[str]:
    """Returns the set of exchanges that should be covered by the two financial summaries based on date."""
    exchanges = list(MARGIN_CORE_EXCHANGES)
    if trade_date and trade_date >= MARGIN_BSE_AVAILABLE_SINCE:
        exchanges.append("BSE")
    return exchanges


def _get_margin_exchange_coverage(day_data: pd.DataFrame, trade_date: str) -> Dict[str, Any]:
    """Evaluate whether the two financial summaries on the specified trading day cover the required exchanges."""
    required_exchanges = _get_required_margin_exchanges(trade_date)

    if day_data is None or day_data.empty:
        return {
            "is_complete": False,
            "present_exchanges": [],
            "missing_exchanges": required_exchanges,
            "missing_exchange_column": False,
        }

    if "exchange_id" not in day_data.columns:
        return {
            "is_complete": False,
            "present_exchanges": [],
            "missing_exchanges": required_exchanges,
            "missing_exchange_column": True,
        }

    present_exchange_set = {
        str(exchange_id).strip()
        for exchange_id in day_data["exchange_id"].dropna().tolist()
        if str(exchange_id).strip()
    }
    present_exchanges = [
        exchange_id for exchange_id in required_exchanges if exchange_id in present_exchange_set
    ]
    missing_exchanges = [
        exchange_id for exchange_id in required_exchanges if exchange_id not in present_exchange_set
    ]

    return {
        "is_complete": not missing_exchanges,
        "present_exchanges": present_exchanges,
        "missing_exchanges": missing_exchanges,
        "missing_exchange_column": False,
    }

# cache manager
_cache = None

def _get_cache():
    """获取缓存管理器实例"""
    global _cache
    if _cache is None:
        try:
            from tradingagents.dataflows.cache import get_cache
            _cache = get_cache()
            logger.info("✅ Index Analysis Tool has caching enabled")
        except Exception as e:
            logger.warning(f"⚠️ 缓存系统不可用: {e}")
    return _cache

# Major Index Code
MAIN_INDICES = {
    '000001.SH': '上证指数',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
}


def _get_tushare_provider():
    """Delayed import acquisition Tushare Provider"""
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
    return get_tushare_provider()


async def _get_latest_trade_date(trade_date: str) -> str:
    """
    Get the latest available transaction date

    Obtain the data of the last 8 days at one time, and take the last valid transaction date

    Args:
        trade_date: original transaction date (YYYY-MM-DD or YYYYMMDD)

    Returns:
        Latest available transaction date (YYYYMMDD Format)
    """
    provider = _get_tushare_provider()
    # Clean date string, remove possible time part
    trade_date_clean = _clean_date_string(trade_date).replace('-', '')
    stable_trade_date = apply_stable_data_cutoff(trade_date_clean)
    if stable_trade_date != trade_date_clean:
        logger.info(f"🕖 {trade_date} If the stable data point has not yet been reached, fall back to {stable_trade_date}")
        trade_date_clean = stable_trade_date

    try:
        # Calculate date 8 days ago
        end_date = datetime.strptime(trade_date_clean, '%Y%m%d')
        start_date = end_date - timedelta(days=8)
        start_date_str = start_date.strftime('%Y%m%d')

        # Get the Shanghai Composite Index data for the last 8 days at one time
        df = await provider.get_index_daily(
            ts_code='000001.SH',
            start_date=start_date_str,
            end_date=trade_date_clean,
            use_cache=False  # No caching is used to ensure the latest data is obtained
        )

        if df is not None and not df.empty:
            # Sort by date, take the last item (latest trading day)
            df = df.sort_values('trade_date', ascending=False)
            latest_trade_date = str(df.iloc[0]['trade_date'])

            logger.debug(f"🔍 获取到 {len(df)} 个交易日，最新: {latest_trade_date}, 请求: {trade_date_clean}")

            if latest_trade_date != trade_date_clean:
                logger.info(f"📅 {trade_date} No data, use the latest trading day {latest_trade_date}")
            else:
                logger.debug(f"✅ {trade_date} 是有效交易日")

            return latest_trade_date

        # If neither is found, return the original date
        logger.warning(f"⚠️ Unable to find valid trading day, use original date {trade_date_clean}")
        return trade_date_clean

    except Exception as e:
        logger.error(f"❌ 获取最新交易日失败: {e}")
        return trade_date_clean


async def get_index_trend(
    trade_date: str,
    lookback_days: int = 60
) -> str:
    """
    Analyze major index trends
    
    Args:
        trade_date: transaction date
        lookback_days: Number of days to look back
    
    Returns:
        Index trend analysis report
    """
    provider = _get_tushare_provider()
    
    try:
        actual_trade_date = await _get_latest_trade_date(trade_date)
        actual_trade_date_formatted = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"

        # Calculate date range
        end_date = datetime.strptime(actual_trade_date, '%Y%m%d')
        start_date = end_date - timedelta(days=lookback_days + 30)
        start_date_str = start_date.strftime('%Y%m%d')
        end_date_str = actual_trade_date
        
        report_lines = [
            "📈 主要指数走势分析",
            "=" * 50,
            f"📅 分析日期: {actual_trade_date_formatted}",
            f"📆 回看周期: {lookback_days} 交易日",
            "",
            "【主要指数表现】",
        ]

        if actual_trade_date_formatted != _clean_date_string(trade_date):
            report_lines.insert(
                4,
                "说明: "
                + build_stable_data_cutoff_note(
                    _clean_date_string(trade_date),
                    actual_trade_date_formatted,
                    subject="Daily frequency data after the close of the day required for market analysis",
                ),
            )
            report_lines.insert(5, "")
        
        for index_code, index_name in MAIN_INDICES.items():
            daily_df = await provider.get_index_daily(
                ts_code=index_code,
                start_date=start_date_str,
                end_date=end_date_str
            )
            
            if daily_df is None or daily_df.empty:
                report_lines.append(f"  {index_name}: 暂无数据")
                continue
            
            # Sort by date
            daily_df = daily_df.sort_values('trade_date')
            
            if len(daily_df) < 5:
                report_lines.append(f"  {index_name}: 数据不足")
                continue
            
            # Calculate indicators
            latest = daily_df.iloc[-1]
            today_pct = latest.get('pct_chg', 0)
            close_price = latest.get('close', 0)
            
            # 5 Daily/20th/60th day increase and decrease
            pct_5d = ((close_price / daily_df.iloc[-5]['close']) - 1) * 100 if len(daily_df) >= 5 else 0
            pct_20d = ((close_price / daily_df.iloc[-20]['close']) - 1) * 100 if len(daily_df) >= 20 else 0
            
            # moving average position
            ma5 = daily_df['close'].tail(5).mean()
            ma20 = daily_df['close'].tail(20).mean() if len(daily_df) >= 20 else ma5
            ma60 = daily_df['close'].tail(60).mean() if len(daily_df) >= 60 else ma20
            
            # Trend judgment
            if close_price > ma5 > ma20 > ma60:
                trend = "📈 多头排列"
            elif close_price < ma5 < ma20 < ma60:
                trend = "📉 空头排列"
            else:
                trend = "📊 震荡整理"
            
            trend_icon = "🔴" if today_pct > 0 else "🟢" if today_pct < 0 else "⚪"
            
            report_lines.append(
                f"  {trend_icon} {index_name}({index_code}): {close_price:.2f}"
            )
            report_lines.append(
                f"      今日: {today_pct:+.2f}% | 5日: {pct_5d:+.2f}% | "
                f"20 day: {pct_20d:+.2f}% | {trend}"
            )
        
        return "\n".join(report_lines)
        
    except Exception as e:
        logger.error(f"指数走势分析失败: {e}")
        return f"❌ 指数走势分析失败: {e}"


async def get_market_breadth(trade_date: str) -> str:
    """
    Analyze market width (number of rising and falling stocks, daily limit and lower limit, etc.)

    Args:
        trade_date: transaction date

    Returns:
        Market Breadth Analysis Report
    """
    provider = _get_tushare_provider()

    try:
        # Get the latest available trading day
        trade_date_clean = await _get_latest_trade_date(trade_date)
        trade_date_formatted = f"{trade_date_clean[:4]}-{trade_date_clean[4:6]}-{trade_date_clean[6:8]}"

        report_lines = [
            "",
            "📊 市场宽度分析",
            "=" * 50,
            f"📅 日期: {trade_date_formatted}",
            "",
        ]

        # Use the daily_info API to get overall market statistics
        daily_info = await provider.get_daily_info(trade_date=trade_date_clean)

        if daily_info is not None and not daily_info.empty:
            # Extract data from Shanghai and Shenzhen markets
            sh_market = daily_info[daily_info['ts_code'] == 'SH_MARKET']
            sz_market = daily_info[daily_info['ts_code'] == 'SZ_MARKET']

            # Transaction statistics
            sh_amount = float(sh_market['amount'].iloc[0]) if len(sh_market) > 0 and 'amount' in sh_market.columns else 0
            sz_amount = float(sz_market['amount'].iloc[0]) if len(sz_market) > 0 and 'amount' in sz_market.columns else 0
            total_amount = sh_amount + sz_amount

            # Volume (handles NaN values)
            import pandas as pd
            sh_vol = float(sh_market['vol'].iloc[0]) if len(sh_market) > 0 and 'vol' in sh_market.columns and pd.notna(sh_market['vol'].iloc[0]) else 0
            sz_vol = float(sz_market['vol'].iloc[0]) if len(sz_market) > 0 and 'vol' in sz_market.columns and pd.notna(sz_market['vol'].iloc[0]) else 0
            total_vol = sh_vol + sz_vol

            # Number of listed companies
            sh_count = int(sh_market['com_count'].iloc[0]) if len(sh_market) > 0 and 'com_count' in sh_market.columns else 0
            sz_count = int(sz_market['com_count'].iloc[0]) if len(sz_market) > 0 and 'com_count' in sz_market.columns else 0
            total_count = sh_count + sz_count

            report_lines.append("【市场规模】")
            report_lines.append(f"  • 上市公司总数: {total_count} 家")
            report_lines.append(f"    - 上海市场: {sh_count} 家")
            report_lines.append(f"    - 深圳市场: {sz_count} 家")

            report_lines.append("")
            report_lines.append("【成交统计】")
            report_lines.append(f"  • 总成交额: {total_amount:.2f} 亿元")
            report_lines.append(f"    - 上海市场: {sh_amount:.2f} 亿元 ({sh_amount/total_amount*100:.1f}%)" if total_amount > 0 else "    - Shanghai market: 0.00 billion")
            report_lines.append(f"    - 深圳市场: {sz_amount:.2f} 亿元 ({sz_amount/total_amount*100:.1f}%)" if total_amount > 0 else "    - Shenzhen market: 0.00 billion")
            if total_vol > 0:
                report_lines.append(f"  • 总成交量: {total_vol:.2f} 亿股")

            if total_amount > 0:
                avg_amount_per_stock = total_amount / total_count if total_count > 0 else 0
                report_lines.append(f"  • 平均每家上市公司成交额: {avg_amount_per_stock:.2f} 亿元")
        else:
            # Plan 2: Get overall market data using daily_basic API
            daily_basic = await provider.get_daily_basic(trade_date=trade_date_clean)

            if daily_basic is not None and not daily_basic.empty:
                # Statistical market capitalization data
                total_mv = daily_basic['total_mv'].sum() / 100000000 if 'total_mv' in daily_basic.columns else 0
                avg_turnover = daily_basic['turnover_rate'].mean() if 'turnover_rate' in daily_basic.columns else 0
                stock_count = len(daily_basic)

                report_lines.append("【市场概况】")
                report_lines.append(f"  • 在交易股票数: {stock_count}")
                report_lines.append(f"  • 总市值: {total_mv:.2f} 万亿")
                report_lines.append(f"  • 平均换手率: {avg_turnover:.2f}%")
            else:
                report_lines.append("⚠️ No market statistics yet (higher Tushare points may be required)")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"市场宽度分析失败: {e}")
        return f"❌ 市场宽度分析失败: {e}"


async def get_market_environment(trade_date: str) -> str:
    """
    Assess market environment (volatility, change of hands, size, etc.)

    Args:
        trade_date: transaction date

    Returns:
        Market environment assessment report
    """
    provider = _get_tushare_provider()

    try:
        actual_trade_date = await _get_latest_trade_date(trade_date)
        trade_date_display = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"
        trade_date_clean = actual_trade_date

        report_lines = [
            "",
            "🌐 市场环境评估",
            "=" * 50,
            f"📅 日期: {trade_date_display}",
            "",
            "【指数运行快照】",
        ]

        if trade_date_display != _clean_date_string(trade_date):
            report_lines.append(f"说明: 输入日期 {trade_date} 无可用数据，已切换到最近交易日 {trade_date_display}")
            report_lines.append("")

        # Get a snapshot of major indices
        for index_code, index_name in list(MAIN_INDICES.items())[:3]:
            basic_df = await provider.get_index_dailybasic(
                ts_code=index_code,
                trade_date=trade_date_clean
            )

            if basic_df is None or basic_df.empty:
                report_lines.append(f"  {index_name}: 暂无快照数据")
                continue

            row = basic_df.iloc[0]
            turnover = row.get('turnover_rate', 'N/A')
            total_mv = row.get('total_mv', 0)
            total_mv_wan_yi = total_mv / 100000000 if total_mv else 0

            report_lines.append(f"  {index_name}:")
            report_lines.append(f"      换手率: {turnover}%")
            report_lines.append(f"      总市值: {total_mv_wan_yi:.2f} 万亿")

        # Volatility Snapshot
        report_lines.append("")
        report_lines.append("【波动率】")

        # Get recent data of Shanghai Composite Index to calculate volatility
        daily_df = await provider.get_index_daily(
            ts_code='000001.SH',
            start_date=(datetime.strptime(trade_date_clean, '%Y%m%d') - timedelta(days=30)).strftime('%Y%m%d'),
            end_date=trade_date_clean
        )

        if daily_df is not None and len(daily_df) >= 20:
            # Calculate 20-day volatility
            returns = daily_df['pct_chg'].dropna()
            volatility = returns.std() * (252 ** 0.5)  # annualized volatility
            report_lines.append(f"  • 20日年化波动率: {volatility:.2f}%")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"市场环境评估失败: {e}")
        return f"❌ 市场环境评估失败: {e}"


async def identify_market_cycle(trade_date: str) -> str:
    """
    Identify market cycles (bull/bear/concussive markets)

    Args:
        trade_date: transaction date

    Returns:
        Market cycle judgment report
    """
    provider = _get_tushare_provider()

    try:
        actual_trade_date = await _get_latest_trade_date(trade_date)
        actual_trade_date_formatted = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"
        end_date = datetime.strptime(actual_trade_date, '%Y%m%d')
        start_date = end_date - timedelta(days=365)  # One year data

        # Get Shanghai Composite Index data
        daily_df = await provider.get_index_daily(
            ts_code='000001.SH',
            start_date=start_date.strftime('%Y%m%d'),
            end_date=actual_trade_date
        )

        report_lines = [
            "",
            "🔄 市场周期判断",
            "=" * 50,
            f"📅 日期: {actual_trade_date_formatted}",
        ]

        if actual_trade_date_formatted != _clean_date_string(trade_date):
            report_lines.append(f"说明: 输入日期 {trade_date} 无可用数据，已切换到最近交易日 {actual_trade_date_formatted}")

        if daily_df is None or len(daily_df) < 60:
            report_lines.append("⚠️ Insufficient data to determine market cycles")
            return "\n".join(report_lines)

        daily_df = daily_df.sort_values('trade_date')

        current_close = daily_df.iloc[-1]['close']
        ma60 = daily_df['close'].tail(60).mean()
        ma120 = daily_df['close'].tail(120).mean() if len(daily_df) >= 120 else ma60
        ma250 = daily_df['close'].tail(250).mean() if len(daily_df) >= 250 else ma120

        # Calculate high and low points for the year
        year_high = daily_df['high'].max()
        year_low = daily_df['low'].min()
        position = (current_close - year_low) / (year_high - year_low) * 100 if year_high != year_low else 50

        # Cycle judgment
        if current_close > ma60 > ma120 > ma250:
            cycle = "价格位于多头排列区间 🐂"
        elif current_close < ma60 < ma120 < ma250:
            cycle = "价格位于空头排列区间 🐻"
        elif current_close > ma60 and current_close > ma120:
            cycle = "The price is above the short- and medium-term moving averages 📈"
        elif current_close < ma60 and current_close < ma120:
            cycle = "The price is below the short- and medium-term moving average 📉"
        else:
            cycle = "价格处于均线交错区间 📊"

        report_lines.append(f"  🎯 规则识别区间: {cycle}")
        report_lines.append(f"  📍 年内位置: {position:.1f}% (0%=年内低点, 100%=年内高点)")
        report_lines.append("  ℹ️ This result is a rule identification based on the relationship between the moving average and the position within the year, and does not represent trend confirmation.")
        report_lines.append("")
        report_lines.append("【均线系统】")
        report_lines.append(f"  • 当前价格: {current_close:.2f}")
        report_lines.append(f"  • MA60: {ma60:.2f} ({'↑' if current_close > ma60 else '↓'})")
        report_lines.append(f"  • MA120: {ma120:.2f} ({'↑' if current_close > ma120 else '↓'})")
        report_lines.append(f"  • MA250: {ma250:.2f} ({'↑' if current_close > ma250 else '↓'})")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"市场周期判断失败: {e}")
        return f"❌ 市场周期判断失败: {e}"


async def analyze_index(trade_date: str) -> str:
    """
    Comprehensive market analysis (IndexAnalyst main entrance)

    Integrate analysis from the four dimensions of index trend, market breadth, market environment, and market cycle

    Args:
        trade_date: transaction date

    Returns:
        Comprehensive market analysis report
    """
    try:
        # First get the latest available trading day
        actual_trade_date = await _get_latest_trade_date(trade_date)
        actual_trade_date_formatted = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"

        logger.info(f"📊 大盘分析使用交易日: {actual_trade_date_formatted}")

        # Obtain four analysis results in parallel
        trend_task = get_index_trend(actual_trade_date_formatted)
        breadth_task = get_market_breadth(actual_trade_date_formatted)
        env_task = get_market_environment(actual_trade_date_formatted)
        cycle_task = identify_market_cycle(actual_trade_date_formatted)

        trend_report, breadth_report, env_report, cycle_report = await asyncio.gather(
            trend_task, breadth_task, env_task, cycle_task
        )

        # Portfolio Report
        full_report = [
            "=" * 60,
            "🌐 大盘分析师综合报告",
            f"📅 分析日期: {actual_trade_date_formatted}",
            "=" * 60,
            "",
            trend_report,
            breadth_report,
            env_report,
            cycle_report,
            "",
            "=" * 60,
        ]

        stable_note = build_stable_data_cutoff_note(
            _clean_date_string(trade_date),
            actual_trade_date_formatted,
            subject="Daily frequency data after the close of the day required for market analysis",
        )
        if stable_note:
            full_report.insert(4, f"说明: {stable_note}")
            full_report.insert(5, "")

        return "\n".join(full_report)

    except Exception as e:
        logger.error(f"综合大盘分析失败: {e}")
        return f"❌ 综合大盘分析失败: {e}"


# ==================== Synchronous wrapper function ====================

def analyze_index_sync(trade_date: str) -> str:
    """analyze_index synchronized version of"""
    return asyncio.run(analyze_index(trade_date))


def get_index_trend_sync(trade_date: str, lookback_days: int = 60) -> str:
    """get_index_trend synchronized version of"""
    return asyncio.run(get_index_trend(trade_date, lookback_days))


def get_market_breadth_sync(trade_date: str) -> str:
    """get_market_breadth synchronized version of"""
    return asyncio.run(get_market_breadth(trade_date))


def get_market_environment_sync(trade_date: str) -> str:
    """get_market_environment synchronized version of"""
    return asyncio.run(get_market_environment(trade_date))


def identify_market_cycle_sync(trade_date: str) -> str:
    """identify_market_cycle synchronized version of"""
    return asyncio.run(identify_market_cycle(trade_date))


# ==================== Added market analysis tools ====================

async def get_north_flow(trade_date: str, lookback_days: int = 10) -> str:
    """
    Get northbound capital flow analysis

    Args:
        trade_date: transaction date (YYYY-MM-DD)
        lookback_days: Number of days to look back

    Returns:
        Northbound capital flow analysis report
    """
    provider = _get_tushare_provider()

    try:
        actual_trade_date = await _get_latest_trade_date(trade_date)
        actual_trade_date_formatted = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"
        end_date = datetime.strptime(actual_trade_date, '%Y%m%d')
        start_date = end_date - timedelta(days=lookback_days + 10)

        df = await provider.get_hsgt_moneyflow(
            start_date=start_date.strftime('%Y%m%d'),
            end_date=actual_trade_date
        )

        report_lines = [
            "",
            "💰 北向资金流向分析",
            "=" * 50,
            f"📅 日期: {actual_trade_date_formatted}",
            "",
        ]

        if actual_trade_date_formatted != _clean_date_string(trade_date):
            report_lines.append(f"说明: 输入日期 {trade_date} 无可用数据，已切换到最近交易日 {actual_trade_date_formatted}")
            report_lines.append("")

        if df is None or df.empty:
            report_lines.append("⚠️ No northbound funding data (may require higher Tushare points)")
            return "\n".join(report_lines)

        # Sort by date
        df = df.sort_values('trade_date', ascending=False)

        # 🔑 Make sure the numeric columns are of numeric type (according to Tushare documentation, these fields should be float)
        # Reference documentation:https://tushare.pro/document/2?doc_id=47
        # Tushare Returned data format: hgt/sgt/north_money are all float type (millions of yuan)
        numeric_cols = ['hgt', 'sgt', 'ggt_ss', 'ggt_sz', 'north_money', 'south_money']
        for col in numeric_cols:
            if col in df.columns:
                # First try converting directly to a numeric type
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except Exception:
                    # If the direct conversion fails, clean up the format errors first
                    # Handle possible format errors: if multiple decimal points are included or numbers are incorrectly concatenated
                    # For example "182490.64238444.93" -> Extract the first significant digit "182490.64"
                    def clean_numeric_value(val):
                        if pd.isna(val):
                            return 0.0
                        val_str = str(val).strip()
                        # Remove commas and spaces
                        val_str = val_str.replace(',', '').replace(' ', '')
                        # If it contains multiple decimal points, extract the first complete number
                        # Match pattern: optional minus sign + numbers + decimal point + Number (first complete number)
                        match = re.match(r'(-?\d+\.\d{1,2})', val_str)
                        if match:
                            return float(match.group(1))
                        # If there is no decimal point, try to match an integer
                        match = re.match(r'(-?\d+)', val_str)
                        if match:
                            return float(match.group(1))
                        return 0.0
                    
                    df[col] = df[col].apply(clean_numeric_value)
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Recalculate north_money and south_money (make sure to use the sanitized values)
        if 'hgt' in df.columns and 'sgt' in df.columns:
            df['north_money'] = df['hgt'].fillna(0) + df['sgt'].fillna(0)
        if 'ggt_ss' in df.columns and 'ggt_sz' in df.columns:
            df['south_money'] = df['ggt_ss'].fillna(0) + df['ggt_sz'].fillna(0)

        # Latest day's data
        latest = df.iloc[0]
        
        # 🔑 Safe conversion functions: Safely extract numeric values from a DataFrame
        def safe_float(value, default=0.0):
            """Safe conversion to floating point, handling possible format errors"""
            if value is None or pd.isna(value):
                return default
            try:
                # If it is already a numeric type, return it directly
                if isinstance(value, (int, float)):
                    return float(value)
                # If it is a pandas Series, take the first value
                if isinstance(value, pd.Series):
                    value = value.iloc[0] if len(value) > 0 else default
                    if pd.isna(value):
                        return default
                    return float(value)
                # If it is a string, clean it and convert it
                if isinstance(value, str):
                    value = value.strip()
                    # Handle format errors: remove extra decimal parts (e.g. "182490.64238444.93" -> "182490.64") 
                    value = re.sub(r'(\d+\.\d+)\.\d+', r'\1', value)
                    value = value.replace(',', '').replace(' ', '')
                return float(value)
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ 无法转换数值: {value} (类型: {type(value)}), 错误: {e}, 使用默认值 {default}")
                return default
        
        # 🔑 Use .iloc[0] Make sure to get a single value instead of Series
        hgt = safe_float(latest['hgt'] if 'hgt' in latest.index else 0)
        sgt = safe_float(latest['sgt'] if 'sgt' in latest.index else 0)
        north_money = safe_float(latest['north_money'] if 'north_money' in latest.index else 0)

        report_lines.append("【今日北向资金】")
        report_lines.append(f"  • 沪股通: {hgt/10000:.2f} 亿元")
        report_lines.append(f"  • 深股通: {sgt/10000:.2f} 亿元")
        flow_text = "净流入" if north_money > 0 else "净流出"
        report_lines.append(f"  • 北向合计: {abs(north_money)/10000:.2f} 亿元 ({flow_text})")

        # Statistics for the past N days
        if len(df) >= 5:
            # 🔑 Use the cleaned numeric column directly (already of float type)
            recent_5 = df.head(5)['north_money'].sum()
            report_lines.append("")
            report_lines.append("【近期趋势】")
            report_lines.append(f"  • 近5日累计: {recent_5/10000:.2f} 亿元")

            if len(df) >= 10:
                recent_10 = df.head(10)['north_money'].sum()
                report_lines.append(f"  • 近10日累计: {recent_10/10000:.2f} 亿元")

            # Number of consecutive inflow/outflow days
            consecutive = 0
            direction = "流入" if north_money > 0 else "流出"
            for _, row in df.iterrows():
                # 🔑 Use the cleaned value directly (already of float type)
                row_north_money = float(row['north_money']) if pd.notna(row['north_money']) else 0.0
                if (direction == "流入" and row_north_money > 0) or \
                   (direction == "流出" and row_north_money < 0):
                    consecutive += 1
                else:
                    break
            if consecutive > 1:
                report_lines.append(f"  • 连续{direction}: {consecutive} 天")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"北向资金分析失败: {e}")
        return f"❌ 北向资金分析失败: {e}"


async def get_margin_trading(trade_date: str, lookback_days: int = 10) -> str:
    """
    Obtain analysis of the balance of financing and financing

    Args:
        trade_date: transaction date (YYYY-MM-DD)
        lookback_days: Number of days to look back

    Returns:
        Financial balance analysis report
    """
    provider = _get_tushare_provider()

    try:
        actual_trade_date = await _get_latest_trade_date(trade_date)
        actual_trade_date_formatted = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"
        end_date = datetime.strptime(actual_trade_date, '%Y%m%d')
        start_date = end_date - timedelta(days=lookback_days + 10)

        df = await provider.get_margin_detail(
            start_date=start_date.strftime('%Y%m%d'),
            end_date=actual_trade_date
        )

        report_lines = [
            "",
            "📊 两融余额分析",
            "=" * 50,
            f"📅 日期: {actual_trade_date_formatted}",
            "",
        ]

        if actual_trade_date_formatted != _clean_date_string(trade_date):
            report_lines.append(f"说明: 输入日期 {trade_date} 无可用数据，已切换到最近交易日 {actual_trade_date_formatted}")
            report_lines.append("")

        if df is None or df.empty:
            report_lines.append("⚠️ There is currently no two-fusion data (higher Tushare points may be required)")
            return "\n".join(report_lines)

        # Sort by date and verify whether the requested trading day has complete transaction coverage
        df = df.copy()
        df['trade_date'] = df['trade_date'].astype(str)
        df = df.sort_values('trade_date', ascending=False)
        latest_date = str(df.iloc[0]['trade_date'])
        latest_data = df[df['trade_date'] == actual_trade_date]

        if latest_data.empty:
            report_lines.append("【数据完整性】")
            report_lines.append("  • Data status: Request no record on transaction day")
            report_lines.append(f"  • 请求交易日: {actual_trade_date_formatted}")
            report_lines.append(f"  • 接口最新返回日期: {_format_compact_trade_date(latest_date)}")
            report_lines.append("")
            report_lines.append("【使用限制】")
            report_lines.append("  • The two financial data for the requested trading day are currently not available.")
            report_lines.append("  • This should not be used to judge the balance level, single-day changes or the direction of leveraged funds.")
            report_lines.append("  • You can wait for Tushare to update the data of the day before doing the two-fusion analysis.")
            return "\n".join(report_lines)

        coverage = _get_margin_exchange_coverage(latest_data, actual_trade_date)
        if not coverage['is_complete']:
            present_exchanges = "、".join(coverage['present_exchanges']) if coverage['present_exchanges'] else "无"
            missing_exchanges = "、".join(coverage['missing_exchanges']) if coverage['missing_exchanges'] else "无"

            report_lines.append("【数据完整性】")
            report_lines.append("  • 数据状态: 不完整")
            report_lines.append(f"  • 已返回交易所: {present_exchanges}")
            report_lines.append(f"  • 缺失交易所: {missing_exchanges}")
            if coverage['missing_exchange_column']:
                report_lines.append("  • The interface does not return the exchange_id field and the exchange coverage cannot be confirmed.")
            report_lines.append("")
            report_lines.append("【使用限制】")
            report_lines.append("  • The current data only covers some exchanges and does not represent the coverage of the entire A-share market.")
            report_lines.append("  • This should not be used to judge the balance level, single-day changes or the direction of leveraged funds.")
            report_lines.append("  • Subsequent analysis should clearly label missing data and do not extrapolate it to abnormal fluctuations or leverage changes.")
            return "\n".join(report_lines)

        # Aggregate data
        rzye = latest_data['rzye'].sum() / 100000000  # Financing balance (100 million yuan)
        rqye = latest_data['rqye'].sum() / 100000000  # Securities lending balance (100 million yuan)
        rzrqye = latest_data['rzrqye'].sum() / 100000000 if 'rzrqye' in latest_data.columns else rzye + rqye

        report_lines.append("【今日两融余额】")
        report_lines.append(f"  • 融资余额: {rzye:.2f} 亿元")
        report_lines.append(f"  • 融券余额: {rqye:.2f} 亿元")
        report_lines.append(f"  • 两融余额: {rzrqye:.2f} 亿元")

        anomaly_messages = []

        # Calculate changes
        unique_dates = df['trade_date'].unique()
        if len(unique_dates) >= 2:
            prev_date = unique_dates[1]
            prev_data = df[df['trade_date'] == prev_date]
            prev_rzye = prev_data['rzye'].sum() / 100000000
            change = rzye - prev_rzye
            if abs(change) > max(rzye * 0.15, 1500):
                anomaly_messages.append("Single-day financing changes fluctuate too much compared to current balance")
            else:
                change_icon = "🔴" if change > 0 else "🟢"
                change_text = "增加" if change > 0 else "减少"
                report_lines.append(f"  • 融资变化: {change_icon} {abs(change):.2f} 亿元 ({change_text})")

        # recent trends
        if len(unique_dates) >= 5:
            first_date_data = df[df['trade_date'] == unique_dates[-1]]
            first_rzye = first_date_data['rzye'].sum() / 100000000
            total_change = rzye - first_rzye
            if abs(total_change) > max(rzye * 0.3, 3000):
                anomaly_messages.append(f"近{len(unique_dates)}日融资变化与当前余额相比波动过大")
            else:
                report_lines.append("")
                report_lines.append("【近期趋势】")
                report_lines.append(f"  • 近{len(unique_dates)}日融资变化: {total_change:.2f} 亿元")

        if anomaly_messages:
            report_lines.append("")
            report_lines.append("【字段一致性检查】")
            for message in anomaly_messages:
                report_lines.append(f"  • ⚠️ {message}")
            report_lines.append("  • There may be caliber differences or outliers in the change field, and we will not extend the interpretation of the leverage direction based on this for the time being.")

        if anomaly_messages:
            report_lines.append("")
            report_lines.append("【使用限制】")
            report_lines.append("  • Currently, only the balance value can be quoted, and the direction of funds should not be judged based on the abnormal change field.")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"两融余额分析失败: {e}")
        return f"❌ 两融余额分析失败: {e}"


async def get_limit_stats(trade_date: str) -> str:
    """
    Obtain price limit statistics and analysis of the number of companies rising and falling

    Args:
        trade_date: transaction date (YYYY-MM-DD)

    Returns:
        Analysis report on price limit and number of companies rising and falling
    """
    provider = _get_tushare_provider()

    try:
        trade_date_clean = trade_date.replace('-', '')

        # Get the latest available trading day
        actual_date = await _get_latest_trade_date(trade_date)
        actual_date_formatted = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"

        report_lines = [
            "",
            "📈 涨跌停与涨跌家数分析",
            "=" * 50,
            f"📅 日期: {actual_date_formatted}",
            "",
        ]

        # Get statistics on the number of stocks rising and falling
        stats = await provider.get_daily_stats(actual_date)

        if stats:
            report_lines.append("【涨跌家数】")
            report_lines.append(f"  • 上涨: {stats['up_count']} 家 ({stats['up_ratio']:.1f}%)")
            report_lines.append(f"  • 下跌: {stats['down_count']} 家 ({stats['down_ratio']:.1f}%)")
            report_lines.append(f"  • 平盘: {stats['flat_count']} 家")
            report_lines.append(f"  • 涨跌比: {stats['up_count']}:{stats['down_count']}")

            report_lines.append("")
            report_lines.append("【涨跌幅分布】")
            report_lines.append(f"  • 涨幅>5%: {stats['up_gt5']} 家")
            report_lines.append(f"  • 涨幅3-5%: {stats['up_3_5']} 家")
            report_lines.append(f"  • 跌幅>5%: {stats['down_gt5']} 家")
            report_lines.append(f"  • 跌幅3-5%: {stats['down_3_5']} 家")

            # Price distribution signal
            profit_stocks = stats['up_gt5'] + stats['up_3_5']
            loss_stocks = stats['down_gt5'] + stats['down_3_5']
            if profit_stocks > loss_stocks * 2:
                effect = "The number of stocks with the largest increase was significantly greater than the number of stocks with the largest decrease. 💰"
            elif profit_stocks > loss_stocks:
                effect = "The number of top gainers is greater than the number of top losers. 📊"
            elif loss_stocks > profit_stocks * 2:
                effect = "The number of stocks with the top decliners is significantly more than the stocks with the top gainers. ⚠️"
            else:
                effect = "The number of stocks with the largest increase or decrease is close to 📉"
            report_lines.append(f"  • {effect}")
        else:
            report_lines.append("⚠️ 暂无涨跌家数数据")

        # Try to get the price limit details
        limit_df = await provider.get_limit_list(actual_date)
        if limit_df is not None and not limit_df.empty:
            limit_up_df = limit_df[limit_df['limit'] == 'U']
            limit_down_df = limit_df[limit_df['limit'] == 'D']
            detail_lines = []

            if not limit_up_df.empty:
                detail_lines.append(f"  • 涨停: {len(limit_up_df)} 家")
                # Connected board statistics
                if 'up_stat' in limit_up_df.columns:
                    multi_board = limit_up_df[limit_up_df['up_stat'].str.contains('2|3|4|5|6|7|8|9', na=False)]
                    if len(multi_board) > 0:
                        detail_lines.append(f"  • 连板: {len(multi_board)} 家")

            if not limit_down_df.empty:
                detail_lines.append(f"  • 跌停: {len(limit_down_df)} 家")

            if detail_lines:
                report_lines.append("")
                report_lines.append("【涨跌停统计】")
                report_lines.extend(detail_lines)
        else:
            report_lines.append("")
            report_lines.append("【涨跌停统计】")
            report_lines.append("  • The detailed list of daily limit and price limit is temporarily unavailable, and the number of companies with daily limit and price limit cannot be confirmed.")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"涨跌停统计失败: {e}")
        return f"❌ 涨跌停统计失败: {e}"


async def get_index_technical(trade_date: str, lookback_days: int = 60) -> str:
    """
    Get Index Technical Indicator Analysis (MACD, RSI, KDJ) 

    Args:
        trade_date: transaction date (YYYY-MM-DD)
        lookback_days: Number of days to look back

    Returns:
        Index Technical Indicator Analysis Report
    """
    provider = _get_tushare_provider()

    try:
        actual_trade_date = await _get_latest_trade_date(trade_date)
        actual_trade_date_formatted = f"{actual_trade_date[:4]}-{actual_trade_date[4:6]}-{actual_trade_date[6:8]}"
        end_date = datetime.strptime(actual_trade_date, '%Y%m%d')
        start_date = end_date - timedelta(days=lookback_days + 30)

        report_lines = [
            "",
            "📉 指数技术指标分析",
            "=" * 50,
            f"📅 日期: {actual_trade_date_formatted}",
            "",
        ]

        if actual_trade_date_formatted != _clean_date_string(trade_date):
            report_lines.append(f"说明: 输入日期 {trade_date} 无可用数据，已切换到最近交易日 {actual_trade_date_formatted}")
            report_lines.append("")

        # Analyze the technical indicators of the Shanghai Composite Index
        index_code = '000001.SH'
        index_name = '上证指数'

        df = await provider.get_index_daily(
            ts_code=index_code,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=actual_trade_date
        )

        if df is None or len(df) < 30:
            report_lines.append("⚠️ Insufficient data to calculate technical indicators")
            return "\n".join(report_lines)

        df = df.sort_values('trade_date').reset_index(drop=True)

        # Calculate technical indicators
        close = df['close']

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = (dif - dea) * 2

        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # KDJ
        low_min = df['low'].rolling(window=9).min()
        high_max = df['high'].rolling(window=9).max()
        rsv = (close - low_min) / (high_max - low_min) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d

        # Get the latest value
        latest_dif = dif.iloc[-1]
        latest_dea = dea.iloc[-1]
        latest_macd = macd.iloc[-1]
        latest_rsi = rsi.iloc[-1]
        latest_k = k.iloc[-1]
        latest_d = d.iloc[-1]
        latest_j = j.iloc[-1]

        report_lines.append(f"【{index_name} 技术指标】")
        report_lines.append("")

        # MACD analysis
        report_lines.append("📊 MACD 指标:")
        report_lines.append(f"  • DIF: {latest_dif:.2f}")
        report_lines.append(f"  • DEA: {latest_dea:.2f}")
        report_lines.append(f"  • MACD柱: {latest_macd:.2f}")

        macd_signal = ""
        if latest_dif > latest_dea:
            if latest_dif > 0:
                macd_signal = "DIF Higher than DEA and above the zero axis 📈"
            else:
                macd_signal = "DIF Higher than DEA, but still below the zero axis 🔄"
        else:
            if latest_dif < 0:
                macd_signal = "DIF Below DEA and below the zero axis 📉"
            else:
                macd_signal = "DIF Below DEA, but still above the zero axis ⚠️"
        report_lines.append(f"  • 信号: {macd_signal}")

        # RSI analysis
        report_lines.append("")
        report_lines.append("📊 RSI 指标:")
        report_lines.append(f"  • RSI(14): {latest_rsi:.2f}")

        if latest_rsi > 80:
            rsi_signal = "In the range above 80, the value is on the high side 🔴"
        elif latest_rsi > 70:
            rsi_signal = "In the 70-80 range, close to high 📈"
        elif latest_rsi > 50:
            rsi_signal = "It is in the 50-70 range, above the dividing line between strength and weakness. 📊"
        elif latest_rsi > 30:
            rsi_signal = "In the 30-50 range, below the strength and weakness dividing line 📉"
        elif latest_rsi > 20:
            rsi_signal = "In the 20-30 range, close to low 📉"
        else:
            rsi_signal = "In the range below 20, the value is low 🟢"
        report_lines.append(f"  • 信号: {rsi_signal}")

        # KDJ analysis
        report_lines.append("")
        report_lines.append("📊 KDJ 指标:")
        report_lines.append(f"  • K: {latest_k:.2f}")
        report_lines.append(f"  • D: {latest_d:.2f}")
        report_lines.append(f"  • J: {latest_j:.2f}")

        if latest_k > latest_d and latest_j > 80:
            kdj_signal = "K Higher than D, the J value is in the range above 80 ⚠️"
        elif latest_k > latest_d:
            kdj_signal = "K Higher than D, the short-term arrangement is upward 📈"
        elif latest_k < latest_d and latest_j < 20:
            kdj_signal = "K Below D, the J value is in the range below 20 🔄"
        else:
            kdj_signal = "K Below D, the short-term arrangement is lower 📉"
        report_lines.append(f"  • 信号: {kdj_signal}")

        # Rule label summary
        report_lines.append("")
        report_lines.append("【指标规则标签】")
        upper_signals = 0
        lower_signals = 0

        if latest_dif > latest_dea:
            upper_signals += 1
        else:
            lower_signals += 1

        if latest_rsi > 50:
            upper_signals += 1
        else:
            lower_signals += 1

        if latest_k > latest_d:
            upper_signals += 1
        else:
            lower_signals += 1

        report_lines.append(f"  • 偏上规则标签数量: {upper_signals}/3")
        report_lines.append(f"  • 偏下规则标签数量: {lower_signals}/3")
        report_lines.append("  • Description: The above labels only describe the current rule position of the indicator and are not equivalent to market conclusions.")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"指数技术指标分析失败: {e}")
        return f"❌ Index technical indicator analysis failed: {e}"


# Synchronous wrapper function
def get_north_flow_sync(trade_date: str, lookback_days: int = 10) -> str:
    """get_north_flow synchronized version of"""
    return asyncio.run(get_north_flow(trade_date, lookback_days))


def get_margin_trading_sync(trade_date: str, lookback_days: int = 10) -> str:
    """get_margin_trading synchronized version of"""
    return asyncio.run(get_margin_trading(trade_date, lookback_days))


def get_limit_stats_sync(trade_date: str) -> str:
    """get_limit_stats synchronized version of"""
    return asyncio.run(get_limit_stats(trade_date))


def get_index_technical_sync(trade_date: str, lookback_days: int = 60) -> str:
    """get_index_technical synchronized version of"""
    return asyncio.run(get_index_technical(trade_date, lookback_days))

