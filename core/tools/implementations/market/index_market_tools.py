"""
Market/index analysis tools

Provides index trend analysis, market breadth analysis and other functions
These tools are for IndexAnalystV2 analysts
"""

import logging
from typing import Annotated
from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_analysis_data_source

logger = logging.getLogger(__name__)


def _resolve_market_analysis_source() -> str:
    """Get the data source that should be used by the current market analysis tool."""
    current_source = get_current_analysis_data_source()
    if current_source == "qmt":
        return "qmt"
    return "tushare"


def _is_tushare_available() -> bool:
    """Check if Tushare data source is available."""
    try:
        from app.services.data_sources.tushare_adapter import TushareAdapter
        return TushareAdapter().is_available()
    except Exception:
        return False


def _is_qmt_available() -> bool:
    """Check if the QMT data source is available."""
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        return QMTAdapter().is_available()
    except Exception:
        return False


def _qmt_fallback_index_trend(trade_date: str, lookback_days: int = 60) -> str:
    """QMT Downgrade: Get trend data for major indices."""
    try:
        from core.tools.qmt_market_tools import get_market_overview_qmt_sync
        report = get_market_overview_qmt_sync(trade_date, lookback_days)
        # Extract the exponential trend section from the full report
        lines = report.split("\n")
        result_lines = ["📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)", ""]
        capture = False
        for line in lines:
            if "主要指数趋势" in line:
                capture = True
            if capture:
                result_lines.append(line)
                if line.strip().startswith("##") and "主要指数趋势" not in line:
                    break
        captured = "\n".join(result_lines)
        return captured if len(captured) > 50 else report
    except Exception as e:
        return f"⚠️ Tushare Unavailable, QMT downgrade failed to obtain index data.: {e}"


def _qmt_fallback_market_breadth(trade_date: str) -> str:
    """QMT Downgrade: Use a snapshot of the entire market to represent the number of rising and falling stocks."""
    try:
        from core.tools.qmt_market_tools import get_market_overview_qmt_sync
        report = get_market_overview_qmt_sync(trade_date, 5)
        lines = report.split("\n")
        result_lines = ["📊 The following data is based on QMT snapshot agent metrics (degraded data when Tushare is unavailable)", ""]
        capture = False
        for line in lines:
            if "市场快照代理" in line:
                capture = True
            if capture:
                result_lines.append(line)
                if line.strip().startswith("##") and "市场快照代理" not in line:
                    break
        captured = "\n".join(result_lines)
        return captured if len(captured) > 50 else report
    except Exception as e:
        return f"⚠️ Tushare Not available, QMT downgrade to obtain market width also failed: {e}"


def _qmt_fallback_technical(trade_date: str, lookback_days: int = 60) -> str:
    """QMT Downgrade: Calculate technical indicators through index K-line."""
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        from statistics import median as _median

        adapter = QMTAdapter()
        if not adapter.is_available():
            return "⚠️ Tushare Not available, QMT is not available, and technical indicator data cannot be obtained."

        index_codes = {
            "000001.SH": "上证指数",
            "399006.SZ": "创业板指",
            "000300.SH": "沪深300",
        }

        result_lines = [
            "📊 Index technical indicators (based on QMT K-line calculation, downgraded data when Tushare is unavailable)",
            "",
        ]

        for code, name in index_codes.items():
            items = adapter.get_kline(code, period="day", limit=max(lookback_days, 60) + 5)
            if not items:
                result_lines.append(f"- {name}: 暂无数据")
                continue

            closes = []
            for item in items:
                c = item.get("close")
                if c is not None:
                    try:
                        closes.append(float(c))
                    except (TypeError, ValueError):
                        pass

            if len(closes) < 20:
                result_lines.append(f"- {name}: 数据不足")
                continue

            # Calculate MA
            ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else None
            ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
            ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None

            # Calculate RSI(14)
            rsi = None
            if len(closes) >= 15:
                gains, losses = [], []
                for i in range(-14, 0):
                    diff = closes[i] - closes[i - 1]
                    gains.append(max(diff, 0))
                    losses.append(max(-diff, 0))
                avg_gain = sum(gains) / 14
                avg_loss = sum(losses) / 14
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                else:
                    rsi = 100

            # Trend judgment
            latest = closes[-1]
            trend = "数据不足"
            if ma5 and ma10 and ma20 and ma60:
                if latest > ma5 > ma20 > ma60:
                    trend = "多头排列"
                elif latest < ma5 < ma20 < ma60:
                    trend = "空头排列"
                else:
                    trend = "震荡整理"

            ma60_str = f"{ma60:.2f}" if ma60 else "-"
            rsi_str = f"{rsi:.1f}" if rsi else "-"
            result_lines.append(
                f"- {name}: 最新 {latest:.2f} | MA5={ma5:.2f} MA20={ma20:.2f} MA60={ma60_str} | "
                f"RSI(14)={rsi_str} | {trend}"
            )

        return "\n".join(result_lines)
    except Exception as e:
        return f"⚠️ Tushare Not available, QMT downgrade failed to obtain technical indicators.: {e}"


def _tushare_unavailable_msg(dimensions: str) -> str:
    """Tushare Unified prompt when QMT is unavailable and cannot be replaced."""
    return (
        f"⚠️ The Tushare data source is currently unavailable,{dimensions}The data is only provided by Tushare, QMT does not support this dimension."
        f"Please give priority to the QMT market analysis data returned by the get_market_analysis tool."
    )


@tool
@register_tool(
    tool_id="get_index_data",
    name="指数数据",
    description="Obtain major index data (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.) and analyze market trends and trends",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["index_data", "index_trend", "market_trend", "moving_average", "main_index"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["index_trend_analysis", "market_direction_assessment", "moving_average_analysis"],
)
def get_index_data(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60
) -> str:
    """
    Get major index data and trend analysis

    Analyze the trends of major indexes such as Shanghai Composite Index, Shenzhen Composite Component Index, ChiNext Index, CSI 300, and CSI 500,
    Including today s rise and fall, the 5th/20th day s rise and fall, moving average position and trend judgment.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back, used to calculate moving averages and trends (default 60 days)

    Returns:
        str: Index trend analysis report
    """
    try:
        from core.tools.index_tools import get_index_trend_sync
        return get_index_trend_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取指数数据失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to obtain index data, try QMT downgrade")
            return _qmt_fallback_index_trend(trade_date, lookback_days)
        return f"❌ 获取指数数据失败: {e}"


@tool
@register_tool(
    tool_id="get_market_breadth",
    name="市场宽度",
    description="Analyze the market width to evaluate the overall participation sentiment, and return structured participation indicators such as the number of rising companies, the number of falling companies, the number of daily limit, the number of lower limit, the ratio of rise and fall, and market temperature.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_breadth", "market_sentiment", "advance_decline", "limit_up_down", "participation"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["market_breadth_analysis", "market_sentiment_assessment", "participation_level_evaluation"],
)
def get_market_breadth(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Analyze market breadth

    Count the number of rising and falling companies, the number of daily limit and lower limit, trading volume distribution, etc., and evaluate the overall market participation and sentiment.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Market Breadth Analysis Report
    """
    try:
        from core.tools.index_tools import get_market_breadth_sync
        return get_market_breadth_sync(trade_date)
    except Exception as e:
        logger.error(f"获取市场宽度失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to get market width, try QMT downgrade")
            return _qmt_fallback_market_breadth(trade_date)
        return f"❌ 获取市场宽度失败: {e}"


@tool
@register_tool(
    tool_id="get_market_environment",
    name="市场环境",
    description="Comprehensively evaluate the multi-dimensional status of the market environment and return comprehensive market environment indicator data such as volatility, turnover rate, turnover, market size, market temperature labels, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_environment", "market_overview", "volatility", "turnover", "market_scale"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["market_environment_assessment", "comprehensive_market_evaluation", "volatility_analysis"],
)
def get_market_environment(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Comprehensive assessment of market environment

    Integrate multi-dimensional data such as fluctuations, turnover and market size to provide a comprehensive assessment of the market environment.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Comprehensive assessment report on market environment
    """
    try:
        from core.tools.index_tools import get_market_environment_sync
        return get_market_environment_sync(trade_date)
    except Exception as e:
        logger.error(f"获取市场环境失败: {e}")
        # Tushare Attempts QMT downgrade on failure (returns to QMT Overview as an alternative)
        if _is_qmt_available():
            logger.info("Tushare Failed to obtain market environment, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
                report = get_market_overview_qmt_enhanced(trade_date, 60)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取市场环境失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取市场环境失败: {e}"


@tool
@register_tool(
    tool_id="identify_market_cycle",
    name="市场周期识别",
    description="Identify the cycle stage the current market is in, and return cycle judgment results such as bull market/bear market/concussion cycle stage labels, trend intensity, judgment basis and confidence level.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_cycle", "cycle_identification", "bull_bear", "regime_detection", "market_phase"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["market_cycle_identification", "regime_classification", "bull_bear_assessment"],
)
def identify_market_cycle(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Identify market cycles

    Identify the current cycle stage of the market based on technical indicators and market data.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Market cycle analysis report
    """
    try:
        from core.tools.index_tools import identify_market_cycle_sync
        return identify_market_cycle_sync(trade_date)
    except Exception as e:
        logger.error(f"识别市场周期失败: {e}")
        # Tushare Attempt QMT downgrade on failure (based on exponential trend judgment period)
        if _is_qmt_available():
            logger.info("Tushare Failure to identify market cycles, attempt QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
                report = get_market_overview_qmt_enhanced(trade_date, 60)
                return (
                    "📊 Market cycle identification (based on QMT enhanced analysis, downgrade analysis when Tushare is unavailable)\n\n"
                    "⚠️ Note: This downgrade analysis is based on exponential trends, moving average alignments and MACD signals and is not as comprehensive as the Tushare version.\n\n"
                    f"{report}"
                )
            except Exception as qmt_e:
                return f"❌ 识别市场周期失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 识别市场周期失败: {e}"


@tool
@register_tool(
    tool_id="get_market_overview",
    name="市场概览",
    description="Get an overview of the overall market environment, including comprehensive data such as index trends, rise and fall statistics, capital flows, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_overview", "market_environment", "market_breadth", "capital_flow", "market_sentiment"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["overall_market_overview", "comprehensive_market_analysis", "market_environment_snapshot"],
)
def get_market_overview(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Get an overall market overview

    Comprehensive multi-dimensional data provides an overview of the overall market environment, including:
    - Major index trends
    - Statistics on the number of stocks rising and falling
    - Fund flow situation
    - Market Sentiment Assessment

    This is an alias for get_market_environment and provides the same comprehensive market analysis.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Market Overview Analysis Report
    """
    try:
        from core.tools.index_tools import get_market_environment_sync
        return get_market_environment_sync(trade_date)
    except Exception as e:
        logger.error(f"获取市场概览失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to get market overview, trying QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
                report = get_market_overview_qmt_enhanced(trade_date, 60)
                return f"📊 The following data is based on QMT market caliber (downgraded data when Tushare is unavailable)\n\n{report}"
            except Exception as qmt_e:
                return f"❌ 获取市场概览失败: Tushare={e}, QMT降级={qmt_e}"
        return f"❌ 获取市场概览失败: {e}"


@tool
@register_tool(
    tool_id="get_market_analysis",
    name="统一大盘分析",
    description="Automatically select the QMT or Tushare path based on the current analysis data source and return unified market analysis results.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["market_analysis", "market_overview", "unified_analysis", "data_source_routing", "comprehensive_market"],
    tool_role_hint="general",
    output_shape="markdown",
    preferred_for=["unified_market_analysis", "multi_source_market_overview", "comprehensive_market_report"],
)
def get_market_analysis(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60
) -> str:
    """The unified market analysis tool automatically routes according to the current data source (QMT or Tushare) and returns the integrated market analysis report.

    Args:
        trade_date: transaction date, format YYYY-MM-DD
        lookback_days: Number of days to look back, default 60

    Returns:
        str: Markdown format of the market analysis report, which is composed of multiple sections. The sections include —
            ## Index trend: index market and trend analysis
            ## Market breadth: number of rising and falling firms, distribution of rising and falling limits
            ## Market environment: Comprehensive market environment assessment
            ## Market Cycle: Market Cycle Phase Identification
            ## Northbound Funds: Northbound Fund Flows from Shanghai-Shenzhen-Hong Kong Stock Connect
            ## Balance of margin financing and securities lending: changes in balance of margin financing and securities lending
            ## Statistics on price limit and price limit: Statistics on number of companies with price limit and price limit
            ## Index technical aspects: MACD/RSI/KDJ and other technical indicators
        QMT Or when Tushare fails, it returns "❌" Error description string at the beginning
    """
    source = _resolve_market_analysis_source()

    if source == "qmt":
        try:
            from core.tools.qmt_market_tools import get_market_overview_qmt_enhanced
            return get_market_overview_qmt_enhanced(trade_date, lookback_days)
        except Exception as e:
            logger.error(f"QMT 大盘分析失败: {e}")
            # QMT try when failed Tushare
            if _is_tushare_available():
                logger.info("QMT Market analysis failed, try to downgrade Tushare")
                try:
                    from core.tools.index_tools import get_market_environment_sync
                    return get_market_environment_sync(trade_date)
                except Exception as ts_e:
                    return f"❌ Market analysis failed: QMT={e}, Tushare={ts_e}"
            return f"❌ QMT Market analysis failed: {e}"

    sections = []
    tool_calls = [
        ("指数趋势", lambda: get_index_data.invoke({"trade_date": trade_date, "lookback_days": lookback_days})),
        ("市场宽度", lambda: get_market_breadth.invoke({"trade_date": trade_date})),
        ("市场环境", lambda: get_market_environment.invoke({"trade_date": trade_date})),
        ("市场周期", lambda: identify_market_cycle.invoke({"trade_date": trade_date})),
        ("北向资金", lambda: get_north_flow.invoke({"trade_date": trade_date, "lookback_days": min(lookback_days, 10)})),
        ("两融余额", lambda: get_margin_trading.invoke({"trade_date": trade_date, "lookback_days": min(lookback_days, 10)})),
        ("涨跌停统计", lambda: get_limit_stats.invoke({"trade_date": trade_date})),
        ("指数技术面", lambda: get_index_technical.invoke({"trade_date": trade_date, "lookback_days": lookback_days})),
    ]

    for title, producer in tool_calls:
        try:
            content = producer()
        except Exception as exc:
            logger.error(f"统一大盘分析组装失败 [{title}]: {exc}")
            content = f"❌ {title} 获取失败: {exc}"
        sections.append(f"## {title}\n{content}")

    return "\n\n".join(sections)


# ==================== Added market analysis tools ====================

@tool
@register_tool(
    tool_id="get_north_flow",
    name="北向资金流向",
    description="Obtain the northbound capital flow data of Shanghai-Shenzhen-Hong Kong Stock Connect and analyze foreign investment trends, and return foreign investment structured data such as net purchases, cumulative positions, industry distribution, active stocks, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["north_flow", "capital_flow", "foreign_capital", "stock_connect", "liquidity"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["northbound_capital_analysis", "foreign_investor_sentiment", "liquidity_assessment"],
)
def get_north_flow(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 10 days"] = 10
) -> str:
    """
    Get northbound capital flow analysis

    Analyze the inflows and outflows of Shanghai-Hong Kong Stock Connect and Shenzhen-Hong Kong Stock Connect, and assess the attitude of foreign investors.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 10 days)

    Returns:
        str: Northbound capital flow analysis report
    """
    try:
        from core.tools.index_tools import get_north_flow_sync
        return get_north_flow_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取北向资金失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("北向资金")
        return f"❌ 获取北向资金失败: {e}"


@tool
@register_tool(
    tool_id="get_margin_trading",
    name="两融余额",
    description="Obtain margin financing and securities lending balance data and identify abnormal fields, and return margin financing balance indicator data such as margin financing balance, securities lending balance, margin purchase amount, and balance change trend.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["margin_trading", "financing_balance", "securities_lending", "leverage", "margin_balance"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["margin_balance_analysis", "leverage_level_assessment", "financing_lending_monitoring"],
)
def get_margin_trading(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 10 days"] = 10
) -> str:
    """
    Obtain analysis of the balance of financing and financing

    Describe margin balance levels and identify anomalies or caliber conflicts in changing fields.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 10 days)

    Returns:
        str: Financial balance analysis report
    """
    try:
        from core.tools.index_tools import get_margin_trading_sync
        return get_margin_trading_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取两融余额失败: {e}")
        if not _is_tushare_available():
            return _tushare_unavailable_msg("两融余额")
        return f"❌ 获取两融余额失败: {e}"


@tool
@register_tool(
    tool_id="get_limit_stats",
    name="涨跌停统计",
    description="Obtain the statistics of the number of companies with daily limit and the number of companies with rise and fall, describe the rise and fall distribution, and return the statistical data of rise and fall distribution such as the number of companies with daily limit/lower limit, price ratio, height of connecting board, and board explosion rate.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["limit_stats", "limit_up_down", "advance_decline", "price_distribution", "market_breadth"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["limit_up_down_statistics", "market_breadth_assessment", "price_distribution_analysis"],
)
def get_limit_stats(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"]
) -> str:
    """
    Obtain statistics on price limits and number of companies rising and falling

    Count the number of companies with price limits, the number of companies with price increases, and distribution of price changes, and output factual data for induction by the upper-layer model.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)

    Returns:
        str: Analysis report on price limit and number of companies rising and falling
    """
    try:
        from core.tools.index_tools import get_limit_stats_sync
        return get_limit_stats_sync(trade_date)
    except Exception as e:
        logger.error(f"获取涨跌停统计失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to obtain price limit statistics, try QMT downgrade")
            try:
                from core.tools.qmt_market_tools import get_limit_stats_qmt_sync
                return get_limit_stats_qmt_sync(trade_date)
            except Exception as qmt_e:
                return f"❌ 获取涨跌停统计失败: Tushare={e}, QMT降级={qmt_e}"
        if not _is_tushare_available():
            return _tushare_unavailable_msg("涨跌停统计")
        return f"❌ 获取涨跌停统计失败: {e}"


@tool
@register_tool(
    tool_id="get_index_technical",
    name="指数技术指标",
    description="Obtain index technical indicators and rule labels, and return technical indicator data such as MACD/RSI/KDJ numerical sequences, golden cross and dead cross signals, trend labels, etc.",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["index_technical", "technical_indicators", "technical_analysis", "macd", "rsi", "kdj"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["index_technical_analysis", "index_momentum_assessment", "index_signal_detection"],
)
def get_index_technical(
    trade_date: Annotated[str, "Transaction date, format:YYYY-MM-DD"],
    lookback_days: Annotated[int, "Number of days to look back, default is 60 days"] = 60
) -> str:
    """
    Get analysis of index technical indicators

    Calculate the MACD, RSI, KDJ and other technical indicators of the Shanghai Composite Index, and return the indicator values ​​and lightweight rule labels.

    Args:
        trade_date: Transaction date (format: YYYY-MM-DD)
        lookback_days: Number of days to look back (default 60 days)

    Returns:
        str: Index Technical Indicator Report
    """
    try:
        from core.tools.index_tools import get_index_technical_sync
        return get_index_technical_sync(trade_date, lookback_days)
    except Exception as e:
        logger.error(f"获取指数技术指标失败: {e}")
        # Tushare QMT downgrade attempt on failure
        if _is_qmt_available():
            logger.info("Tushare Failed to obtain technical indicators, try QMT downgrade")
            return _qmt_fallback_technical(trade_date, lookback_days)
        return f"❌ Failed to obtain index technical indicators: {e}"
