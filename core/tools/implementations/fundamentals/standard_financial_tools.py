"""Standard financial data capability tools.

These tools encapsulate core.skill_runtime.standard_financial_apis and expose structured and auditable common stock analysis data capabilities to Agent.
"""

import json
import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.skill_runtime.standard_financial_apis import (
    get_adjusted_price_series,
    get_capital_efficiency_trend,
    get_capital_flow_series,
    get_cashflow_quality_trend,
    get_chip_distribution_context,
    get_company_announcements,
    get_company_event_timeline,
    get_current_valuation_snapshot,
    get_debt_solvency_trend,
    get_drawdown_metrics,
    get_growth_quality_metrics,
    get_historical_financial_annual_series,
    get_historical_valuation_percentile,
    get_industry_fundamental_summary,
    get_industry_market_performance,
    get_business_segment_trend,
    get_margin_stability_metrics,
    get_peer_group,
    get_peer_relative_growth,
    get_peer_relative_quality,
    get_peer_relative_valuation,
    get_pledge_historical_series,
    get_pledge_risk_profile,
    get_portfolio_risk_profile,
    get_profitability_stability_metrics,
    get_return_series,
    get_risk_event_flags,
    get_security_master,
    get_shareholder_return_metrics,
    get_single_stock_risk_profile,
    get_technical_indicator_series,
    get_volatility_metrics,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _parse_metrics(metrics: Optional[str]) -> list[str] | None:
    if not metrics:
        return None
    items = [item.strip().lower() for item in str(metrics).replace("，", ",").split(",") if item.strip()]
    return items or None


def _parse_positions(positions_json: str) -> list[dict]:
    data = json.loads(positions_json or "[]")
    if isinstance(data, dict):
        data = data.get("positions") or []
    if not isinstance(data, list):
        raise ValueError("positions_json Must be an array of positions or a JSON object containing a positions field")
    return [item for item in data if isinstance(item, dict)]


@tool
@register_tool(
    tool_id="get_company_event_timeline_tool",
    name="公司公告监管事件时间线",
    description="Structured return to official announcement/regulatory event timeline; local announcement data takes precedence, using news agent to identify events when missing.",
    category="news",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when a timeline of events such as formal announcements, regulatory letters, penalties, shareholding reductions, pledges, litigation, dividend announcements, etc. is needed.",
    when_not_to_use="Not suitable for real-time news stream monitoring (use get_stock_news); not suitable for informal/social media anecdotes; not suitable for quantitative event studies (use get_event_study).",
    capability_tags=["event", "announcement", "regulatory"],
    tool_role_hint="specialized",
    returns="Returns a JSON string containing events, summary, coverage, and warnings.",
    example="get_company_event_timeline_tool(symbol='600519', lookback_days=365)",
    related_tools=["get_risk_event_flags_tool", "get_company_announcements_tool", "get_event_study", "get_stock_news"],
)
def get_company_event_timeline_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 365"] = 365,
    event_types: Annotated[str, "Comma separated event types, can be empty"] = "",
    limit: Annotated[int, "Maximum number of events returned, default 100"] = 100,
) -> str:
    """Get a timeline of company announcements/regulatory events.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 365
        event_types: Comma separated event types, can be empty
        limit: Maximum number of events returned, default 100

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_company_event_timeline`` of Returns ——
            status, symbol, window, data_source, events, summary(event_count/type_counts/high_severity_count),
            warnings
    """
    try:
        return _json_response(get_company_event_timeline(symbol, lookback_days=lookback_days, event_types=_parse_metrics(event_types), limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain company announcement regulatory event timeline: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain company announcement regulatory event timeline: {exc}"})


@tool
@register_tool(
    tool_id="get_business_segment_trend_tool",
    name="主营结构趋势",
    description="Structured return of main business segment revenue, gross profit, gross profit margin, revenue proportion, Top1/Top3 concentration and HHI trend.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "business_segment", "segment_revenue", "segment_margin", "revenue_mix",
        "product_mix", "regional_mix", "gross_margin", "segment_gross_margin",
        "concentration", "hhi", "top1_concentration", "top3_concentration",
        "business_structure", "revenue_composition", "diversification",
        "moat_analysis", "competitive_advantage", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "business_segment_analysis", "revenue_mix_trend", "concentration_analysis",
        "product_mix_analysis", "regional_mix_analysis", "diversification_assessment",
        "moat_analysis",
    ],
    when_to_use="Use it when you need to analyze the main business structure, changes in product/region revenue proportion, business concentration and gross profit margin structure.",
    returns="Returns a JSON string containing periods, concentration, coverage, and warnings.",
    example="get_business_segment_trend_tool(symbol='600519', years=5, segment_type='product')",
)
def get_business_segment_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "number of years, default 5"] = 5,
    segment_type: Annotated[str, "Division type, such as product/region/all"] = "product",
) -> str:
    """Obtain main business structure trends.

    Args:
        symbol: A stock code, such as 600519,000001
        years: number of years, default 5
        segment_type: Division type, such as product/region/all

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_business_segment_trend`` of Returns ——
            status, symbol, segment_type, periods, coverage(period_count/raw_segment_count), warnings
    """
    try:
        return _json_response(get_business_segment_trend(symbol, years=years, segment_type=segment_type))
    except Exception as exc:
        logger.error("Failed to obtain main business structure trend: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"主营结构趋势获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_shareholder_return_metrics_tool",
    name="股东回报指标",
    description="Structured returns dividend history, cash dividends per share, dividend yield, dividend continuity and free cash flow coverage context.",
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "shareholder_return", "dividend", "dividend_history", "cash_dividend",
        "dividend_yield", "dividend_continuity", "payout_ratio",
        "free_cashflow_coverage", "shareholder_value", "dividend_stability",
        "total_shareholder_return", "yield_analysis", "income_investing",
        "value_investing", "dividend_payout", "return_on_capital",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "dividend_analysis", "dividend_yield_assessment", "shareholder_return_analysis",
        "dividend_continuity_check", "free_cashflow_coverage_check",
        "income_investing", "value_investing",
    ],
    when_to_use="Use when you need to analyze dividends, dividend yield, shareholder returns, dividend stability, or cash flow coverage.",
    returns="Returns a JSON string containing records, annual, metrics, coverage, and warnings.",
    example="get_shareholder_return_metrics_tool(symbol='600519', years=5)",
)
def get_shareholder_return_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "number of years, default 5"] = 5,
) -> str:
    """Get shareholder return metrics.

    Args:
        symbol: A stock code, such as 600519,000001
        years: number of years, default 5

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_shareholder_return_metrics`` of Returns ——
            status, symbol, data_source, current_price, records, annual, metrics, coverage, warnings
    """
    try:
        return _json_response(get_shareholder_return_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain shareholder return indicator: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"股东回报指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_portfolio_risk_profile_tool",
    name="组合风险画像",
    description="Returns portfolio volatility, maximum drawdown, VaR, CVaR, industry exposure and concentration based on position JSON and price return series.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="Used when the user provides a position and requires portfolio risk, concentration, sector exposure, VaR or maximum drawdown.",
    when_not_to_use="Not suitable for single stock risk analysis (please use get_single_stock_risk_profile_tool); not suitable for scenarios without position data.",
    capability_tags=["portfolio", "risk_management", "var"],
    tool_role_hint="specialized",
    returns="Returns a JSON string containing positions, metrics, exposure, return_series, coverage, and warnings.",
    example="get_portfolio_risk_profile_tool(positions_json='[{\"symbol\":\"600519\",\"market_value\":100000}]')",
    related_tools=["get_correlation_matrix", "get_single_stock_risk_profile_tool", "get_cointegration_test"],
)
def get_portfolio_risk_profile_tool(
    positions_json: Annotated[str, "Position JSON array, the elements contain symbol/code and market_value or quantity*price"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is nearly one year"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum price samples, default 300"] = 300,
) -> str:
    """Obtain a portfolio risk profile.

    Args:
        positions_json: Position JSON array, the elements contain symbol/code and market_value or quantity*price
        start_date: Start date YYYY-MM-DD, default is nearly one year
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum price samples, default 300

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_portfolio_risk_profile`` of Returns ——
            status, window, positions, metrics, exposure, return_series, coverage, warnings
    """
    try:
        return _json_response(get_portfolio_risk_profile(_parse_positions(positions_json), start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain portfolio risk profile: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"组合风险画像获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_technical_indicator_series_tool",
    name="技术指标历史序列",
    description=(
        "Based on the standard price sequence structured calculation, historical indicators such as MA, MACD, RSI, KDJ, BOLL, ATR, OBV, and support pressure are calculated."
        "Here s Technical signals/trends It refers to the sequence of technical indicators of price and trading volume, not a financial risk signal, announcement event signal or Agent capability gap."
    ),
    category="technical",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need historical sequence of technical indicators, support pressure, ATR/BOLL/OBV or structured technical input, suitable for technical analysis, volume and price indicators and price trend judgment.",
    when_not_to_use="Not used for financial risk, cash flow risk, announcement event signals, fundamental quality or Agent Workshop capability gap analysis. If you only want current values ​​(not historical series), you should use get_technical_factor_bundle_tool; if you want a human-readable text analysis report, you should use get_technical_indicators.",
    capability_tags=["technical_indicators", "historical_series", "structured_data", "ma", "macd", "rsi", "kdj", "boll", "atr", "obv"],
    tool_role_hint="supporting",
    preferred_for=["技术指标历史序列", "回测数据准备", "结构化技术面输入"],
    returns="Returns a JSON string, including records, latest, summary, coverage, and warnings.",
    example="get_technical_indicator_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
    related_tools=["get_technical_factor_bundle_tool", "get_technical_indicators", "get_adjusted_price_series_tool"],
)
def get_technical_indicator_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is nearly one year"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    indicators: Annotated[str, "Comma separated indicators like ma,macd,rsi,kdj,boll,atr,obv,support_resistance"] = "ma,macd,rsi,kdj,boll,atr,obv,support_resistance",
    limit: Annotated[int, "Maximum number of items returned, default 300"] = 300,
) -> str:
    """Get the historical sequence of technical indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is nearly one year
        end_date: End date YYYY-MM-DD, default is today
        indicators: Comma separated indicators like ma,macd,rsi,kdj,boll,atr,obv,support_resistance
        limit: Maximum number of items returned, default 300

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_technical_indicator_series`` of Returns ——
            status, symbol, window, data_source, indicators, records, latest, summary, warnings
    """
    try:
        return _json_response(get_technical_indicator_series(symbol, start_date=start_date, end_date=end_date, indicators=_parse_metrics(indicators), limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain technical indicator historical sequence: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain technical indicator historical sequence: {exc}"})


@tool
@register_tool(
    tool_id="get_industry_market_performance_tool",
    name="行业市场表现",
    description="The structure returns the price rise and fall of peers in the industry where the target stock is located, industry earnings, proportion of risers and fallers, transaction volume, and industry capital flow context.",
    category="market",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "industry_performance", "industry_returns", "peer_performance",
        "market_breadth", "advance_decline", "industry_rotation",
        "industry_moneyflow", "sector_performance", "top_gainers", "top_losers",
        "industry_relative", "market_heat", "sector_rotation",
        "peer_comparison", "industry_trend",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "industry_performance_analysis", "sector_rotation_analysis",
        "industry_relative_performance", "market_breadth_check",
        "industry_moneyflow_analysis", "peer_performance_comparison",
    ],
    when_to_use="Use it when you need industry ups and downs, industry rotation, industry capital flows, and relative industry performance of target stocks.",
    returns="Returns a JSON string containing summary, top_gainers, top_losers, moneyflow, coverage, and warnings.",
    example="get_industry_market_performance_tool(symbol='600519', lookback_days=20, peer_limit=50)",
)
def get_industry_market_performance_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, can be empty"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    lookback_days: Annotated[int, "Number of days to look back, default 20"] = 20,
    peer_limit: Annotated[int, "Peer sample upper limit, default 100"] = 100,
) -> str:
    """Get industry market performance.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, can be empty
        end_date: End date YYYY-MM-DD, default is today
        lookback_days: Number of days to look back, default 20
        peer_limit: Peer sample upper limit, default 100

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_industry_market_performance`` of Returns ——
            status, symbol, industry, window, summary, top_gainers, top_losers, moneyflow,
            coverage, warnings
    """
    try:
        return _json_response(get_industry_market_performance(symbol, start_date=start_date, end_date=end_date, lookback_days=lookback_days, peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Industry market performance acquisition failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"行业市场表现获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_relative_growth_tool",
    name="同业成长分位",
    description="Structured returns the quantiles of revenue, net profit, operating cash flow, and free cash flow CAGR relative to peer samples.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "peer_comparison", "peer_growth", "industry_growth", "growth_percentile",
        "revenue_cagr", "net_profit_cagr", "operating_cashflow_cagr", "free_cashflow_cagr",
        "growth_benchmarking", "peer_relative", "same_industry_growth",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_growth_comparison", "industry_growth_percentile", "growth_benchmarking",
        "revenue_growth_peer_ranking", "profit_growth_peer_ranking",
        "moat_analysis", "competitive_advantage_assessment",
    ],
    when_to_use="Use it when you need to judge the relative position of growth among peers and make horizontal comparisons of growth quality.",
    returns="Returns a JSON string, including metrics, samples, coverage, and warnings.",
    example="get_peer_relative_growth_tool(symbol='600519', metrics='revenue_cagr,net_profit_cagr', years=5)",
)
def get_peer_relative_growth_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like revenue_cagr,net_profit_cagr,operating_cashflow_cagr,free_cashflow_cagr"] = "revenue_cagr,net_profit_cagr,operating_cashflow_cagr,free_cashflow_cagr",
    years: Annotated[int, "Year number of annual report, default 5, maximum 15"] = 5,
    peer_limit: Annotated[int, "Peer sample upper limit, default 50"] = 50,
) -> str:
    """Obtain peer growth scores.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like revenue_cagr,net_profit_cagr,operating_cashflow_cagr,free_cashflow_cagr
        years: Year number of annual report, default 5, maximum 15
        peer_limit: Peer sample upper limit, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_relative_growth`` of Returns ——
            status, symbol, industry, years, metrics, samples, coverage, warnings
    """
    try:
        return _json_response(get_peer_relative_growth(symbol, metrics=_parse_metrics(metrics), years=years, peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain peer growth score: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"同业成长分位获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_historical_financial_annual_series_tool",
    name="历史年报财务序列",
    description=(
        "Structured returns the financial series of annual reports of a single A-share in the last N years."
        "Suitable for scenarios such as long-term financial quality, profitability stability, cash flow quality, etc."
        "Avoid picking numbers from get_income_analysis s Markdown and mixed quarter series."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "historical_financials", "annual_series", "multi_year_financials",
        "financial_trend", "long_term_financials",
        "gross_margin", "gross_margin_trend", "operating_margin", "operating_margin_trend",
        "netprofit_margin", "profitability_trend",
        "revenue", "revenue_trend", "net_profit", "profit_trend",
        "roe", "roe_trend", "roa", "roic", "return_on_equity",
        "operating_cashflow", "free_cashflow", "cashflow_trend",
        "total_assets", "total_equity", "debt_to_assets", "balance_sheet",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "historical_financial_trend_analysis", "gross_margin_trend", "operating_margin_trend",
        "profitability_trend", "multi_year_financial_series", "revenue_trend",
        "moat_analysis", "competitive_advantage_assessment", "long_term_financial_quality",
    ],
    when_to_use=(
        "When Agent/Skill needs a complete annual report sequence of 5-10 years, revenue/net profit/ROE/operating cash flow long-term trend,"
        "It will be used first when looking at the multi-year trend of gross profit margin/operating profit margin, or when structured financial ledgers are needed as input for subsequent calculations."
    ),
    when_not_to_use="If you only want a text summary of the income statement for the most recent quarter, use get_income_analysis.",
    returns="Returns a JSON string, including records, coverage, and warnings; records are structured annual report fields in reverse order by year (including gross_margin/operating_margin/netprofit_margin/roe/revenue/net_profit, etc.).",
    example="get_historical_financial_annual_series_tool(symbol='600519', years=10)",
    related_tools=["get_profitability_stability_metrics_tool", "get_cashflow_quality_trend_tool", "get_income_analysis"],
)
def get_historical_financial_annual_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get structured historical annual report financial series.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_historical_financial_annual_series`` of Returns ——
            status, symbol, requested_years, records, coverage(requested_years/available_years/missing_years),
            warnings
    """
    try:
        return _json_response(get_historical_financial_annual_series(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain financial sequence of historical annual report: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain financial sequence of historical annual report: {exc}"})


@tool
@register_tool(
    tool_id="get_profitability_stability_metrics_tool",
    name="盈利稳定性指标",
    description=(
        "Calculate the mean, median, volatility and coefficient of variation of revenue, net profit, ROE, gross profit margin and year-on-year growth based on historical annual report sequences."
        "Suitable for profitability stability, long-term quality analysis, and revenue volatility assessment."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "profitability_stability", "financial_stability", "long_term_quality",
        "revenue_volatility", "revenue_stability", "revenue_fluctuation",
        "gross_margin_stability", "gross_margin_volatility",
        "roe_stability", "roe_persistence", "return_stability",
        "profit_volatility", "profit_stability",
        "coefficient_of_variation", "stddev", "growth_stability",
        "growth_volatility", "yoy_growth_stability",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "profitability_stability_analysis", "revenue_volatility", "revenue_stability",
        "revenue_fluctuation_analysis", "gross_margin_stability", "roe_persistence",
        "moat_analysis", "competitive_advantage_assessment", "long_term_quality_analysis",
    ],
    when_to_use="Use it when you need to quantify profitability stability, revenue volatility, ROE/gross profit margin sustainability, and long-term quality analysis.",
    when_not_to_use="Not used for valuation percentiles; please use get_historical_valuation_percentile_tool for valuation percentiles.",
    returns="Returns a JSON string containing metrics(Contains coefficient_of_variation), trend_series(Contains revenue_growth_yoy), coverage, warnings. ",
    example="get_profitability_stability_metrics_tool(symbol='600519', years=10)",
    related_tools=["get_historical_financial_annual_series_tool", "get_quality_factor_bundle_tool"],
)
def get_profitability_stability_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get structured earnings stability indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_profitability_stability_metrics`` of Returns ——
            status, symbol, years_used, coverage, metrics, trend_series, warnings
    """
    try:
        return _json_response(get_profitability_stability_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain profit stability indicator: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"盈利稳定性指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_cashflow_quality_trend_tool",
    name="现金流质量趋势",
    description=(
        "Calculate operating cash flow/net profit, free cash flow/net profit, operating cash flow rate, free cash flow rate and other trends based on historical annual report sequences."
        "It is suitable for judging profit content, cash flow stability, free cash flow quality, as well as cash flow deterioration signals such as declining operating cash flow and long-term negative free cash flow."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["cashflow_quality", "cashflow_deterioration", "earnings_quality", "free_cashflow", "operating_cashflow"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["cashflow_quality_analysis", "financial_risk_signal_detection", "earnings_quality_analysis"],
    when_to_use="It is used when structural indicators such as long-term cash flow quality, CFO/net profit, FCF/net profit, cash flow rate, operating cash flow decline, and long-term negative free cash flow are needed.",
    when_not_to_use="If you only want a textual summary of the cash flow statement, use get_cashflow_analysis.",
    returns="Returns a JSON string, including trend, summary, coverage, and warnings.",
    example="get_cashflow_quality_trend_tool(symbol='600519', years=10)",
    related_tools=["get_historical_financial_annual_series_tool", "get_growth_cashflow_factor_bundle_tool", "get_cashflow_analysis"],
)
def get_cashflow_quality_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Capture structured cash flow quality trends.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_cashflow_quality_trend`` of Returns ——
            status, symbol, years_used, coverage, trend, summary, warnings
    """
    try:
        return _json_response(get_cashflow_quality_trend(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain cash flow quality trend: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"现金流质量趋势获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_historical_valuation_percentile_tool",
    name="历史估值分位",
    description=(
        "Structured calculation of historical valuation quantiles such as PE_TTM, PB, PS_TTM, PCF_TTM, etc. supports specifying the number of years to look back."
        "Used as an alternative to the hidden 3-year text quantile output in get_stock_fundamentals_unified."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "valuation", "historical_valuation", "valuation_percentile",
        "pe_ttm", "pb", "ps_ttm", "pcf_ttm", "valuation_band",
        "valuation_range", "safety_margin", "valuation_channel",
        "historical_range", "percentile_rank", "valuation_analysis",
        "relative_valuation", "time_series", "valuation_metrics",
    ],
    tool_role_hint="primary",
    output_shape="structured_metrics",
    preferred_for=[
        "valuation_percentile", "historical_valuation_analysis",
        "valuation_band_analysis", "safety_margin_assessment",
        "pe_percentile", "pb_percentile", "ps_percentile",
        "valuation_channel_analysis",
    ],
    when_to_use="Used when historical PE/PB/PS/PCF quantile, valuation channel, safety margin or auditable valuation quantile data is required.",
    when_not_to_use="If you only need the current PE/PB snapshot, use get_current_valuation_snapshot_tool or get_value_factor_bundle_tool.",
    returns="Returns a JSON string, including window, data_source, metrics, and warnings; metrics includes current_value, median, percentile, and sample_count.",
    example="get_historical_valuation_percentile_tool(symbol='600519', metrics='pe_ttm,pb,ps_ttm', lookback_years=5)",
    related_tools=["get_current_valuation_snapshot_tool", "get_value_factor_bundle_tool", "get_stock_fundamentals_unified"],
)
def get_historical_valuation_percentile_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like pe_ttm,pb,ps_ttm,pcf_ttm"] = "pe_ttm,pb,ps_ttm",
    lookback_years: Annotated[int, "Number of years to look back, default 5, maximum 15"] = 5,
    as_of_date: Annotated[Optional[str], "Analysis date YYYY-MM-DD, default is today"] = None,
) -> str:
    """Get structured historical valuation quantiles.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like pe_ttm,pb,ps_ttm,pcf_ttm
        lookback_years: Number of years to look back, default 5, maximum 15
        as_of_date: Analysis date YYYY-MM-DD, default is today

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_historical_valuation_percentile`` of Returns ——
            status, symbol, window, data_source, metrics, warnings
    """
    try:
        return _json_response(
            get_historical_valuation_percentile(
                symbol,
                metrics=_parse_metrics(metrics),
                lookback_years=lookback_years,
                as_of_date=as_of_date,
            )
        )
    except Exception as exc:
        logger.error("Failed to obtain historical valuation quantile: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"历史估值分位获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_security_master_tool",
    name="证券主数据",
    description="Returns unified securities master data by stock code or stock name, including code, name, exchange, industry, listing status, ST mark, market capitalization, etc.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "security_master", "stock_metadata", "symbol_lookup", "stock_identity",
        "exchange_info", "listing_status", "industry_info", "market_cap",
        "st_flag", "basic_info", "security_info", "stock_basics",
        "ticker_lookup", "company_profile", "metadata",
    ],
    tool_role_hint="supporting",
    output_shape="structured_json",
    preferred_for=[
        "stock_identity_verification", "symbol_resolution", "basic_stock_info",
        "listing_status_check", "industry_lookup", "market_cap_lookup",
    ],
    when_to_use="It is used when the Agent needs to confirm the stock identity, code, name, industry, exchange, listing status, and basic metadata. Supports entering stock code or stock name.",
    returns="Returns a JSON string, including query, symbol, name, exchange, industry, listing_status, coverage, and warnings.",
    example="get_security_master_tool(symbol='600519') or get_security_master_tool(symbol='iFlytek')",
)
def get_security_master_tool(symbol: Annotated[str, "A Stock stock code or stock name, such as 600519, iFlytek, Kweichow Moutai"]) -> str:
    """Obtain securities master data.

    Args:
        symbol: A Stock stock code or stock name, such as 600519, iFlytek, Kweichow Moutai

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_security_master`` of Returns ——
            status, query, symbol, ts_code, name, exchange, industry, area, list_date,
            listing_status, is_st, market_cap, float_market_cap, data_source, coverage, warnings
    """
    try:
        return _json_response(get_security_master(symbol))
    except Exception as exc:
        logger.error("Failed to obtain securities master data: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"证券主数据获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_adjusted_price_series_tool",
    name="标准价格序列",
    description="Returns the normalized daily price series containing open/high/low/close/volume/amount/turnover_rate.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "price_series", "ohlcv", "daily_price", "adjusted_price", "kline",
        "candlestick", "volume", "turnover_rate", "market_data",
        "price_history", "time_series", "trading_data", "price_trend",
        "backtest_input", "ohlc",
    ],
    tool_role_hint="supporting",
    output_shape="structured_records",
    preferred_for=[
        "price_history_query", "kline_data", "backtest_data_preparation",
        "price_trend_analysis", "volume_analysis", "technical_analysis_input",
    ],
    when_to_use="Used when inputs for K-line sequence, price trend, and subsequent yield/volatility/retracement calculations are required.",
    returns="Returns a JSON string, including records, window, coverage, and warnings.",
    example="get_adjusted_price_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_adjusted_price_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the standard price series.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_adjusted_price_series`` of Returns ——
            status, symbol, period, adjustment, data_source, window, records, coverage, warnings
    """
    try:
        return _json_response(get_adjusted_price_series(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain standard price series: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"标准价格序列获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_return_series_tool",
    name="收益率序列",
    description="Structured returns of period-by-period return records, statistical summaries and coverage ratios for volatility calculation and backtest input.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "return_series", "daily_returns", "return_statistics",
        "return_distribution", "price_return", "risk_metrics",
        "volatility_input", "backtest_input", "return_history",
        "time_series", "return_analysis", "performance_measurement",
        "periodic_returns",
    ],
    tool_role_hint="supporting",
    output_shape="structured_records",
    preferred_for=[
        "return_series_analysis", "volatility_calculation", "backtest_input",
        "risk_metrics_calculation", "return_distribution_analysis",
        "performance_measurement",
    ],
    when_to_use="Use when return series, risk indicators, backtest inputs, or volatility calculation inputs are required.",
    returns="Returns a JSON string, including records, summary, coverage, and warnings.",
    example="get_return_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_return_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the return series.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_return_series`` of Returns ——
            status, symbol, period, window, records, summary, coverage, warnings
    """
    try:
        return _json_response(get_return_series(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain yield series: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"收益率序列获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_volatility_metrics_tool",
    name="波动率指标",
    description="Structured return daily volatility, annualized volatility and sample number indicators are used for individual stock price risk measurement and risk profiling.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "volatility", "annualized_volatility", "price_risk",
        "volatility_metrics", "risk_measurement", "return_volatility",
        "risk_metrics", "market_risk", "volatility_analysis",
        "standard_deviation", "price_volatility",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "volatility_analysis", "annualized_volatility_calculation",
        "price_risk_assessment", "risk_profile", "market_risk_measurement",
    ],
    when_to_use="Use it when you need to measure individual stock price risks, annualized fluctuations, and risk profiles.",
    returns="Returns a JSON string, including metrics, windows, and warnings.",
    example="get_volatility_metrics_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_volatility_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the volatility indicator.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_volatility_metrics`` of Returns ——
            status, symbol, period, window, metrics, warnings
    """
    try:
        return _json_response(get_volatility_metrics(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain volatility indicator: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"波动率指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_drawdown_metrics_tool",
    name="回撤指标",
    description="Structured return maximum retracement, retracement start and end dates and retracement sequence for downside risk assessment and backtesting.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "drawdown", "max_drawdown", "downside_risk", "drawdown_series",
        "peak_to_trough", "loss_analysis", "risk_metrics",
        "downside_deviation", "drawdown_duration", "recovery_analysis",
        "market_risk", "drawdown_recovery",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "max_drawdown_analysis", "downside_risk_assessment",
        "drawdown_analysis", "backtest_risk_metrics", "loss_analysis",
        "recovery_analysis",
    ],
    when_to_use="Use when you need to measure downside risk, maximum drawdowns, risk profiles, or backtest risk indicators.",
    returns="Returns a JSON string, including metrics, drawdown_series, and warnings.",
    example="get_drawdown_metrics_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_drawdown_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get the retracement indicator.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_drawdown_metrics`` of Returns ——
            status, symbol, period, window, metrics, drawdown_series, warnings
    """
    try:
        return _json_response(get_drawdown_metrics(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("回撤指标获取失败: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"回撤指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_current_valuation_snapshot_tool",
    name="当前估值快照",
    description=(
        "Structured returns a snapshot of current valuations such as PE/PB/PS/PEG/dividend yield/market capitalization."
        "The valuation indicator used for the current cross-section does not calculate historical quantiles, relative positions of peers, DCF target prices or complete valuation ranges."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "valuation", "current_valuation", "valuation_snapshot",
        "pe", "pb", "ps", "peg", "dividend_yield", "market_cap",
        "valuation_metrics", "valuation_analysis", "snapshot",
        "current_metrics", "relative_valuation", "valuation_snapshot",
    ],
    tool_role_hint="primary",
    output_shape="structured_metrics",
    preferred_for=[
        "current_valuation_snapshot", "pe_pb_snapshot", "valuation_quick_check",
        "market_cap_lookup", "dividend_yield_check", "valuation_metrics_lookup",
    ],
    when_to_use="Use when you only need a snapshot of valuation indicators such as current PE/PB/PS/PEG/dividend yield/market capitalization, rather than historical quantiles, peer comparisons or target price models.",
    when_not_to_use="Not used for historical valuation percentiles (with get_historical_valuation_percentile_tool), peer relative valuations (with get_peer_relative_valuation_tool), DCF/price target valuations, or financial quality/risk analyses.",
    returns="Returns a JSON string containing current_price, metrics, data_source, and warnings.",
    example="get_current_valuation_snapshot_tool(symbol='600519')",
)
def get_current_valuation_snapshot_tool(symbol: Annotated[str, "A stock code, such as 600519,000001"]) -> str:
    """Get a snapshot of the current valuation.

    Args:
        symbol: A stock code, such as 600519,000001

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_current_valuation_snapshot`` of Returns ——
            status, symbol, name, industry, trade_date, current_price, metrics, metric_sources,
            raw_metrics, data_source, warnings
    """
    try:
        return _json_response(get_current_valuation_snapshot(symbol))
    except Exception as exc:
        logger.error("Failed to obtain current valuation snapshot: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"当前估值快照获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_debt_solvency_trend_tool",
    name="偿债能力长期趋势",
    description="Structured return to long-term trends such as gearing ratio, current ratio, quick ratio, debt-to-equity ratio, operating cash flow debt coverage, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "solvency", "debt_solvency", "debt_to_assets", "current_ratio",
        "quick_ratio", "debt_to_equity", "financial_health", "leverage",
        "leverage_trend", "debt_coverage", "cashflow_debt_coverage",
        "balance_sheet", "financial_risk", "long_term_solvency",
        "liquidity_ratio", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_records",
    preferred_for=[
        "solvency_analysis", "leverage_trend_analysis",
        "financial_health_assessment", "debt_coverage_analysis",
        "liquidity_analysis", "financial_risk_assessment",
    ],
    when_to_use="Used when it is necessary to analyze financial health, solvency, and leverage trends.",
    returns="Returns a JSON string, including trend, summary, coverage, and warnings.",
    example="get_debt_solvency_trend_tool(symbol='600519', years=10)",
)
def get_debt_solvency_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Capture long-term trends in solvency.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_debt_solvency_trend`` of Returns ——
            status, symbol, years_used, coverage, trend, summary, warnings
    """
    try:
        return _json_response(get_debt_solvency_trend(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain long-term trend of solvency: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain long-term trend of solvency: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_group_tool",
    name="标准同行组",
    description="Returns standardized peer sample groups based on industry, including basic fields such as market capitalization, PE, PB, and ROE.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "peer_group", "peer_comparison", "industry_peers", "peers",
        "same_industry", "competitors", "peer_list", "industry_competition",
        "market_cap", "pe", "pb", "roe", "valuation",
        "moat_analysis", "competitive_advantage", "peer_benchmarking",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_group_construction", "peer_comparison", "industry_peer_analysis",
        "competitor_analysis", "moat_analysis", "competitive_advantage_assessment",
        "peer_benchmarking",
    ],
    when_to_use="It is used when it is necessary to construct peer samples, peer valuations or peer quality comparison preliminary data, and peer competition analysis.",
    returns="Returns a JSON string, including industry, peers, coverage, and warnings.",
    example="get_peer_group_tool(symbol='600519', limit=50)",
)
def get_peer_group_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    limit: Annotated[int, "The upper limit of the number of peers, default 50"] = 50,
) -> str:
    """Get the standard peer group.

    Args:
        symbol: A stock code, such as 600519,000001
        limit: The upper limit of the number of peers, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_group`` of Returns ——
            status, symbol, industry, peers, coverage(peer_count/limit), warnings
    """
    try:
        return _json_response(get_peer_group(symbol, limit=limit))
    except Exception as exc:
        logger.error("Standard peer group acquisition failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"标准同行组获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_relative_valuation_tool",
    name="同业相对估值",
    description=(
        "Structured returns the mean, median and quantile of PE/PB/PS relative to industry peers."
        "It is used for horizontal peer valuation comparison and industry relative position judgment, and is not used for historical valuation quantiles, DCF target prices or simple current valuation snapshots."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "peer_comparison", "peer_valuation", "industry_valuation", "valuation_percentile",
        "pe", "pb", "ps", "valuation_benchmarking", "peer_relative",
        "same_industry_valuation", "relative_valuation",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_valuation_comparison", "industry_valuation_percentile", "valuation_benchmarking",
        "pe_peer_ranking", "pb_peer_ranking", "ps_peer_ranking",
        "moat_analysis", "competitive_advantage_assessment",
    ],
    when_to_use="It is used when peer valuation comparison, relative position of industry valuation, and PE/PB/PS horizontal quantile are needed.",
    when_not_to_use="Not used for historical valuation quantile time series (with get_historical_valuation_percentile_tool), current valuation snapshots (with get_current_valuation_snapshot_tool), DCF/price target models, or quality factor analysis.",
    returns="Returns a JSON string containing industry, metrics, and warnings.",
    example="get_peer_relative_valuation_tool(symbol='600519', metrics='pe,pb,ps')",
)
def get_peer_relative_valuation_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like pe,pb,ps"] = "pe,pb,ps",
    peer_limit: Annotated[int, "Peer sample upper limit, default 200"] = 200,
) -> str:
    """Get peer relative valuations.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like pe,pb,ps
        peer_limit: Peer sample upper limit, default 200

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_relative_valuation`` of Returns ——
            status, symbol, industry, metrics, warnings
    """
    try:
        return _json_response(get_peer_relative_valuation(symbol, metrics=_parse_metrics(metrics), peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain peer relative valuation: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"同业相对估值获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_peer_relative_quality_tool",
    name="同业相对质量",
    description=(
        "Structured returns the position of quality or valuation quality metrics such as ROE/PB/PE relative to peers."
        "Here s quality Refers to the company s fundamental quality and peer relative quality, such as ROE, profitability, asset efficiency and partial valuation quality, not data quality, reporting quality, cash flow specific quality or technical signal quality."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "peer_comparison", "peer_quality", "industry_quality", "quality_percentile",
        "roe", "pb", "pe_ttm", "quality_benchmarking", "peer_relative",
        "same_industry_quality", "relative_quality", "profitability",
        "moat_analysis", "competitive_advantage",
    ],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=[
        "peer_quality_comparison", "industry_quality_percentile", "quality_benchmarking",
        "roe_peer_ranking", "profitability_peer_ranking",
        "moat_analysis", "competitive_advantage_assessment",
    ],
    when_to_use="It is used when it is necessary to judge the relative position of a company s fundamental quality indicators among its peers, such as horizontal comparisons of ROE, profitability, asset efficiency, and valuation quality.",
    when_not_to_use="Not used for data quality checks, report quality reviews, cash flow specific quality trends (with get_cashflow_quality_trend_tool) or technical indicator signal quality.",
    returns="Returns a JSON string containing industry, metrics, and warnings.",
    example="get_peer_relative_quality_tool(symbol='600519', metrics='roe,pb,pe_ttm')",
)
def get_peer_relative_quality_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    metrics: Annotated[str, "Comma separated indicators like roe,pb,pe_ttm"] = "roe,pb,pe_ttm",
    peer_limit: Annotated[int, "Peer sample upper limit, default 200"] = 200,
) -> str:
    """Obtain the relative quality of peers.

    Args:
        symbol: A stock code, such as 600519,000001
        metrics: Comma separated indicators like roe,pb,pe_ttm
        peer_limit: Peer sample upper limit, default 200

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_peer_relative_quality`` of Returns ——
            status, symbol, industry, metrics, warnings
    """
    try:
        return _json_response(get_peer_relative_quality(symbol, metrics=_parse_metrics(metrics), peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain peer relative quality: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"同业相对质量获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_company_announcements_tool",
    name="公司公告代理",
    description="Identify announcement records from recent news as a structured proxy capability before accessing announcement-specific data sources.",
    category="news",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need clues about company announcements, disclosures, financial reports, dividends, shareholding reductions, restructuring and other events.",
    when_not_to_use="Not suitable for formal announcement database query (please use get_company_event_timeline_tool); not suitable for general news analysis (please use get_stock_news).",
    capability_tags=["event", "announcement", "disclosure"],
    tool_role_hint="specialized",
    returns="Returns a JSON string containing announcements, coverage, and warnings.",
    example="get_company_announcements_tool(symbol='600519', lookback_days=365)",
    related_tools=["get_company_event_timeline_tool", "get_risk_event_flags_tool", "get_stock_news"],
)
def get_company_announcements_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 365"] = 365,
    limit: Annotated[int, "Return the upper limit of the number of items, default 50"] = 50,
) -> str:
    """Obtain company announcement agency records.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 365
        limit: Return the upper limit of the number of items, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_company_announcements`` of Returns ——
            status, symbol, window, announcements, coverage, warnings
    """
    try:
        return _json_response(get_company_announcements(symbol, lookback_days=lookback_days, limit=limit))
    except Exception as exc:
        logger.error("Company Announcement Failed to Obtain Agent: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"公司公告代理获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_risk_event_flags_tool",
    name="风险事件标记",
    description=(
        "Identify risk flags such as regulatory penalties, litigation, shareholding reductions, pledges, performance warnings, restructuring, and executive changes based on recent news headlines/summaries."
        "Here s Risk events/signals Refers to news and announcement event clues, not financial statement anomalies, cash flow deterioration, market fluctuation risks, technical buying and selling signals, or Agent capability gaps."
    ),
    category="news",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need to quickly determine whether there are recent regulatory penalties, lawsuits, shareholding reductions, pledges, performance warnings, restructuring and other major news/announcement event clues.",
    when_not_to_use="It is not suitable for in-depth analysis of financial risks, identification of cash flow anomalies, or detection of financial fraud signals; financial risk/financial report quality tools should be used for such needs. Not suitable for in-depth event quantitative analysis (please use get_event_study); not suitable for formal announcement query (please use get_company_event_timeline_tool); not suitable for general news browsing (please use get_stock_news).",
    capability_tags=["event", "risk", "regulatory"],
    tool_role_hint="specialized",
    returns="Returns a JSON string, including hit_flags, flags, news_count, and warnings.",
    example="get_risk_event_flags_tool(symbol='600519', lookback_days=180)",
    related_tools=["get_company_event_timeline_tool", "get_company_announcements_tool", "get_event_study", "get_stock_news"],
)
def get_risk_event_flags_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    lookback_days: Annotated[int, "Number of days to look back, default 180"] = 180,
    limit: Annotated[int, "The upper limit of the number of news items, default 50"] = 50,
) -> str:
    """Get the risk event tag.

    Args:
        symbol: A stock code, such as 600519,000001
        lookback_days: Number of days to look back, default 180
        limit: The upper limit of the number of news items, default 50

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_risk_event_flags`` of Returns ——
            status, symbol, window, news_count, hit_flags, flags, warnings
    """
    try:
        return _json_response(get_risk_event_flags(symbol, lookback_days=lookback_days, limit=limit))
    except Exception as exc:
        logger.error("Risk event tag acquisition failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"风险事件标记获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_margin_stability_metrics_tool",
    name="利润率稳定性指标",
    description="Structured return of long-term stability statistics of gross profit margin, net profit margin, operating profit margin, and expense ratio.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "margin_stability", "gross_margin_stability", "net_margin_stability",
        "operating_margin_stability", "expense_ratio", "expense_ratio_stability",
        "profitability_stability", "margin_trend", "margin_volatility",
        "moat_analysis", "competitive_advantage", "cost_control",
        "operating_efficiency", "margin_persistence",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "margin_stability_analysis", "gross_margin_persistence",
        "net_margin_stability", "expense_ratio_analysis", "moat_analysis",
        "competitive_advantage_assessment", "cost_control_assessment",
    ],
    when_to_use="Used when it is necessary to analyze profit margin stability, moat evidence, and expense control quality.",
    returns="Returns a JSON string containing trends, metrics, coverage, and warnings.",
    example="get_margin_stability_metrics_tool(symbol='600519', years=10)",
)
def get_margin_stability_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get profit margin stability indicators.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_margin_stability_metrics`` of Returns ——
            status, symbol, years_used, coverage, trend, metrics, warnings
    """
    try:
        return _json_response(get_margin_stability_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain profit margin stability indicator: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain profit margin stability indicator: {exc}"})


@tool
@register_tool(
    tool_id="get_capital_efficiency_trend_tool",
    name="资本效率趋势",
    description="Structured return to long-term trends in capital efficiency such as ROE, ROA, ROIC, asset turnover, equity multiplier, etc.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "capital_efficiency", "roe", "roa", "roic", "asset_turnover",
        "equity_multiplier", "dupont_analysis", "return_on_equity",
        "return_on_assets", "return_on_invested_capital",
        "operating_efficiency", "capital_allocation",
        "financial_efficiency", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_records",
    preferred_for=[
        "capital_efficiency_analysis", "dupont_decomposition",
        "roe_trend_analysis", "roa_trend_analysis", "roic_analysis",
        "operating_efficiency_assessment", "capital_allocation_analysis",
    ],
    when_to_use="Use it when you need to analyze capital utilization efficiency, DuPont dismantling basic indicators, and long-term operating efficiency.",
    returns="Returns a JSON string, including trend, summary, coverage, and warnings.",
    example="get_capital_efficiency_trend_tool(symbol='600519', years=10)",
)
def get_capital_efficiency_trend_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get capital efficiency trends.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_capital_efficiency_trend`` of Returns ——
            status, symbol, years_used, coverage, trend, summary, warnings
    """
    try:
        return _json_response(get_capital_efficiency_trend(symbol, years=years))
    except Exception as exc:
        logger.error("Capital efficiency trend acquisition failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"资本效率趋势获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_growth_quality_metrics_tool",
    name="成长质量指标",
    description="Structured returns revenue, net income, operating cash flow, free cash flow CAGR and annual growth stability.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "growth_quality", "revenue_cagr", "net_profit_cagr",
        "operating_cashflow_cagr", "free_cashflow_cagr", "growth_stability",
        "growth_volatility", "earnings_growth", "revenue_growth",
        "sustainable_growth", "growth_persistence", "cashflow_backed_growth",
        "quality_growth", "growth_consistency",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "growth_quality_analysis", "cagr_analysis", "growth_stability_assessment",
        "sustainable_growth_check", "cashflow_backed_growth_verification",
        "earnings_growth_quality",
    ],
    when_to_use="Use it when you need to judge the quality of growth, whether growth is supported by cash flow, and whether revenue and profit growth is stable.",
    returns="Returns a JSON string containing cagr, annual_growth, growth_stability, quality_flags, and warnings.",
    example="get_growth_quality_metrics_tool(symbol='600519', years=10)",
)
def get_growth_quality_metrics_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    years: Annotated[int, "Year number of annual report, default 10, maximum 15"] = 10,
) -> str:
    """Get growth quality metrics.

    Args:
        symbol: A stock code, such as 600519,000001
        years: Year number of annual report, default 10, maximum 15

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_growth_quality_metrics`` of Returns ——
            status, symbol, years_used, coverage, cagr, annual_growth, growth_stability,
            quality_flags, warnings
    """
    try:
        return _json_response(get_growth_quality_metrics(symbol, years=years))
    except Exception as exc:
        logger.error("Failed to obtain growth quality indicators: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"成长质量指标获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_single_stock_risk_profile_tool",
    name="个股风险画像",
    description="Based on the price sequence, risk profiles such as return distribution, annualized volatility, maximum drawdown, downward volatility, and daily ratio of positive and negative returns are returned.",
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "risk_profile", "single_stock_risk", "return_distribution",
        "annualized_volatility", "max_drawdown", "downside_volatility",
        "upside_ratio", "downside_ratio", "risk_metrics", "price_risk",
        "market_risk", "risk_assessment", "return_distribution_analysis",
        "downside_risk",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "single_stock_risk_profile", "price_risk_assessment",
        "return_distribution_analysis", "downside_risk_analysis",
        "volatility_assessment", "backtest_risk_context",
    ],
    when_to_use="Use when you need an individual stock risk profile, price risk, downside risk, or pre-backtest risk context.",
    returns="Returns a JSON string, including metrics, components, and warnings.",
    example="get_single_stock_risk_profile_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_single_stock_risk_profile_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is the past 3 years"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 1000"] = 1000,
) -> str:
    """Get a risk profile of individual stocks.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is the past 3 years
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 1000

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_single_stock_risk_profile`` of Returns ——
            status, symbol, period, window, metrics, components, warnings
    """
    try:
        return _json_response(get_single_stock_risk_profile(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain individual stock risk profile: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"个股风险画像获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_industry_fundamental_summary_tool",
    name="行业基本面摘要",
    description="Based on peer samples, return industry market capitalization, PE, PB, ROE and other fundamental statistics and top samples.",
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "industry_fundamental", "industry_summary", "industry_statistics",
        "industry_pe", "industry_pb", "industry_roe", "peer_statistics",
        "industry_valuation", "industry_quality", "top_peers",
        "market_cap_distribution", "peer_comparison", "industry_benchmark",
        "fundamental_summary",
    ],
    tool_role_hint="supporting",
    output_shape="structured_json",
    preferred_for=[
        "industry_fundamental_background", "peer_distribution_analysis",
        "industry_valuation_benchmark", "industry_quality_benchmark",
        "top_peer_identification", "industry_context",
    ],
    when_to_use="Used when industry fundamental background, peer sample distribution, industry valuation/quality statistical context is needed.",
    returns="Returns a JSON string containing industry, metrics, top_market_cap_peers, coverage, and warnings.",
    example="get_industry_fundamental_summary_tool(symbol='600519', peer_limit=100)",
)
def get_industry_fundamental_summary_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    peer_limit: Annotated[int, "Peer sample upper limit, default 100"] = 100,
) -> str:
    """Get a summary of industry fundamentals.

    Args:
        symbol: A stock code, such as 600519,000001
        peer_limit: Peer sample upper limit, default 100

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_industry_fundamental_summary`` of Returns ——
            status, symbol, industry, coverage, metrics, top_market_cap_peers, warnings
    """
    try:
        return _json_response(get_industry_fundamental_summary(symbol, peer_limit=peer_limit))
    except Exception as exc:
        logger.error("Failed to obtain industry fundamentals summary: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"行业基本面摘要获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_capital_flow_series_tool",
    name="个股资金流序列",
    description=(
        "Structured return of local stock capital flow sequence, including main net inflow, net inflow ratio, large order/small order net inflow and other fields."
        "Here s capital flow It refers to the flow of transaction funds and main capital behavior, not operating cash flow, investment cash flow, financing cash flow or free cash flow in financial statements."
    ),
    category="market",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "capital_flow", "money_flow", "main_force_flow", "institutional_flow",
        "large_order_flow", "small_order_flow", "net_inflow", "inflow_ratio",
        "trading_flow", "fund_flow", "market_behavior", "capital_behavior",
        "liquidity_analysis", "main_force_behavior", "time_series",
    ],
    tool_role_hint="specialized",
    output_shape="structured_records",
    preferred_for=[
        "capital_flow_analysis", "main_force_behavior_analysis",
        "fund_flow_trend", "large_order_flow_analysis",
        "market_behavior_evidence", "liquidity_analysis",
    ],
    when_to_use="Use it when you need to trade capital flow trends, main capital behavior, capital evidence, and large/small order net inflow structure. If the fund flow is not synchronized locally, no_data and reason will be returned.",
    when_not_to_use="Not used for financial statement cash flow quality, operating cash flow decline, negative free cash flow, or profit margin analysis; these needs should use get_cashflow_quality_trend_tool, get_cashflow_analysis, or get_growth_cashflow_factor_bundle_tool.",
    returns="Returns a JSON string, including records, summary, coverage, and warnings.",
    example="get_capital_flow_series_tool(symbol='600519', start_date='2024-01-01', end_date='2024-12-31')",
)
def get_capital_flow_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date YYYY-MM-DD, default is 180 days"] = None,
    end_date: Annotated[Optional[str], "End date YYYY-MM-DD, default is today"] = None,
    limit: Annotated[int, "Maximum number of items returned, default 120"] = 120,
) -> str:
    """Get the fund flow sequence of individual stocks.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date YYYY-MM-DD, default is 180 days
        end_date: End date YYYY-MM-DD, default is today
        limit: Maximum number of items returned, default 120

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_capital_flow_series`` of Returns ——
            status, symbol, window, data_source, records, summary, coverage, warnings
    """
    try:
        return _json_response(get_capital_flow_series(symbol, start_date=start_date, end_date=end_date, limit=limit))
    except Exception as exc:
        logger.error("Failed to obtain individual stock capital flow sequence: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"个股资金流序列获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_chip_distribution_context_tool",
    name="筹码分布上下文",
    description="The structure returns profit ratio, average cost, 70%/90% chip cost range and concentration.",
    category="market",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    capability_tags=[
        "chip_distribution", "profit_ratio", "average_cost", "cost_distribution",
        "chip_concentration", "cost_range", "holder_cost", "market_behavior",
        "chip_structure", "concentration_ratio", "profit_margin_distribution",
        "cost_basis", "holding_cost", "snapshot",
    ],
    tool_role_hint="specialized",
    output_shape="structured_metrics",
    preferred_for=[
        "chip_distribution_analysis", "cost_concentration_analysis",
        "profit_ratio_check", "average_cost_analysis",
        "support_resistance_from_cost", "market_behavior_analysis",
    ],
    when_to_use="It is used when evidence of market behavior such as chip distribution, cost concentration, and profit margin ratio is needed.",
    returns="Returns a JSON string, including metrics, data_source, and warnings.",
    example="get_chip_distribution_context_tool(symbol='600519', trade_date='2024-12-31')",
)
def get_chip_distribution_context_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    trade_date: Annotated[Optional[str], "Transaction date YYYY-MM-DD, default is today"] = None,
) -> str:
    """Get the chip distribution context.

    Args:
        symbol: A stock code, such as 600519,000001
        trade_date: Transaction date YYYY-MM-DD, default is today

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_chip_distribution_context`` of Returns ——
            status, symbol, trade_date, message, data_source, metrics, warnings
    """
    try:
        return _json_response(get_chip_distribution_context(symbol, trade_date=trade_date))
    except Exception as exc:
        logger.error("Failed to obtain chip distribution context: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"筹码分布上下文获取失败: {exc}"})


@tool
@register_tool(
    tool_id="get_pledge_risk_profile_tool",
    name="股权质押风险画像",
    description=(
        "Return to the equity pledge risk profile: total pledge ratio, unreleased pledge size, top pledge shareholders, recent pledge events, and risk level."
        "The data source preferentially uses the project s built-in Tushare/akshare data source, and there is no need for the user to specify the data source."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="It is used when it is necessary to analyze the equity pledge ratio, the pledge situation of major shareholders, the risk of pledge liquidation, and the pressure on the liquidation line.",
    when_not_to_use="Not suitable for non-pledged shareholder analysis (please use get_shareholder_return_metrics_tool); not suitable for general risk profiling (please use get_single_stock_risk_profile_tool).",
    capability_tags=["pledge", "shareholder", "risk"],
    tool_role_hint="specialized",
    returns="Returns a JSON string, including status, metrics (total_pledge_ratio/outstanding_amount, etc.), top_pledgers, recent_pledges, risk_level, warnings.",
    example="get_pledge_risk_profile_tool(symbol='600519')",
    related_tools=["get_risk_event_flags_tool", "get_shareholder_return_metrics_tool", "get_single_stock_risk_profile_tool"],
)
def get_pledge_risk_profile_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    source: Annotated[Optional[str], "Data source, automatically selected by default"] = None,
) -> str:
    """Obtain a portrait of equity pledge risk.

    Args:
        symbol: A stock code, such as 600519,000001
        source: Data source, automatically selected by default

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_pledge_risk_profile`` of Returns ——
            status, symbol, data_source, metrics(total_pledge_ratio/outstanding_pledge_amount_wan Wait),
            top_pledgers, recent_pledges, risk_level, warnings, data_source_status
    """
    try:
        return _json_response(get_pledge_risk_profile(symbol, source=source))
    except Exception as exc:
        logger.error("Failed to obtain equity pledge risk profile: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain equity pledge risk profile: {exc}"})


@register_tool(
    tool_id="get_pledge_historical_series_tool",
    name="股权质押历史趋势",
    description=(
        "Returns the equity pledge trend data of a single A-share within a specified time period, supporting statistics by year/quarter/month."
        "Including the pledge ratio at the end of each cycle, the number of outstanding shares, the number of active pledges, and the automatically assessed trend direction (improvement/deterioration/stable)."
        "The data source preferentially uses the project s built-in Tushare/akshare data source, and there is no need for the user to specify the data source."
    ),
    category="fundamentals",
    is_online=True,
    auto_register=True,
    timeout_tier="medium",
    when_to_use="It is used when it is necessary to analyze the historical change trend of equity pledge ratio, determine whether pledge risk is improving or deteriorating, and compare pledge data by time period. Supports customization of start and end dates and statistical granularity.",
    when_not_to_use="Not suitable for querying the current pledge snapshot (please use get_pledge_risk_profile_tool); not suitable for non-pledge shareholder analysis.",
    capability_tags=["pledge", "shareholder", "risk", "trend", "historical"],
    tool_role_hint="specialized",
    returns="Returns a JSON string, including status, period (statistical period), start_date, end_date, series (period array, including period/pledge_ratio/outstanding_pledge_amount_wan, etc.), trend_assessment (trend direction assessment), and warnings.",
    example="get_pledge_historical_series_tool(symbol='600519', start_date='2021-01-01', end_date='2024-12-31', period='year')",
    related_tools=["get_pledge_risk_profile_tool", "get_single_stock_risk_profile_tool", "get_risk_event_flags_tool"],
)
def get_pledge_historical_series_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"],
    start_date: Annotated[Optional[str], "Start date, YYYY-MM-DD format, choose one of years"] = None,
    end_date: Annotated[Optional[str], "End date, YYYY-MM-DD format, default is today"] = None,
    years: Annotated[Optional[int], "Last N years, convenient parameter, alternative to start_date, default is 3 years"] = None,
    period: Annotated[Optional[str], "Statistical period: year/quarter/month, default year"] = "year",
    source: Annotated[Optional[str], "Data source, automatically selected by default"] = None,
) -> str:
    """Get the historical trend of equity pledge.

    Args:
        symbol: A stock code, such as 600519,000001
        start_date: Start date, YYYY-MM-DD format, choose one of years
        end_date: End date, YYYY-MM-DD format, default is today
        years: Last N years, convenient parameter, alternative to start_date, default is 3 years
        period: Statistical period: year/quarter/month, default year
        source: Data source, automatically selected by default

    Returns:
        str: JSON string. The parsed field structure is the same as
            ``core.skill_runtime.standard_financial_apis.get_pledge_historical_series`` of Returns ——
            status, symbol, data_source, period, start_date, end_date, period_count, series,
            trend_assessment(direction/change_pct/summary), warnings
    """
    try:
        return _json_response(get_pledge_historical_series(
            symbol, start_date=start_date, end_date=end_date,
            years=years, period=period, source=source
        ))
    except Exception as exc:
        logger.error("Failed to obtain historical trend of equity pledge: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain historical trend of equity pledge: {exc}"})
