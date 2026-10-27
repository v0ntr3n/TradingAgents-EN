"""Normalization factor bundle tool."""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.skill_runtime import (
    get_fundamental_factor_snapshot,
    get_growth_cashflow_factor_bundle,
    get_quality_factor_bundle,
    get_value_factor_bundle,
)
from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


@tool
@register_tool(
    tool_id="get_value_factor_bundle_tool",
    name="价值因子包",
    description=(
        "Returns the stock s value_core package of standardized value factors."
        "Suitable for one-time acquisition of valuation indicators such as PE, PE_TTM, PB, PB_MRQ, PS_TTM, dividend yield, PEG, industry PE/PB median, etc."
        "It also comes with missing factors, rollback warnings and calculation instructions."
        "Here s Value/Valuation Factor is a cross-sectional valuation input and does not directly generate DCF price targets, historical valuation quantiles or full investment ratings."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "It is used when the Agent needs to make valuation judgments, preliminary screening of cheap/expensive, horizontal comparison of PE/PB/PEG, and industry valuation comparison."
        "If the need is to obtain a collection of value indicators instead of reading a certain original field individually, bind this tool first."
    ),
    when_not_to_use=(
        "Not suitable for analysis of income statement trends, solvency, and cash flow quality;"
        "It is also not suitable for making technical judgments, DCF target prices or historical valuation points. If you need quality factor, please use get_quality_factor_bundle_tool."
        "If you need growth/cash flow, please use get_growth_cashflow_factor_bundle_tool, if you need historical percentile, please use get_historical_valuation_percentile_tool."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol, name, industry, current_price,bundle=value_core, "
        "factors、factor_warnings、industry_samples、calculation_notes、missing_factors。"
        "factors The key fields include pe, pe_ttm, pb, pb_mrq, ps_ttm, divided_yield, peg, industry_pe_median, industry_pb_median."
    ),
    example="get_value_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_quality_factor_bundle_tool",
        "get_growth_cashflow_factor_bundle_tool",
        "get_fundamental_factor_snapshot_tool",
        "get_peer_comparison",
    ],
)
def get_value_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get a package of standardized value factors.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            bundle: Factor package identifier, fixed to "value_core"
            factors: dict value factor set——
                — pe: P/E ratio
                — pe_ttm: TTM P/E ratio
                — pb: price to book ratio
                — pb_mrq: MRQ price to book ratio
                — ps_ttm: TTM price to sales ratio
                — dividend_yield: dividend yield
                — peg: PEG
                — industry_pe_median: Industry PE median
                — industry_pb_median: Industry PB median
            factor_warnings: dict Factor alarm information
            industry_samples: dict Number of industry samples——
                — pe_count: PE Number of samples
                — pb_count: PB Number of samples
            calculation_notes: list[str] Calculation instructions
            missing_factors: list[str] Missing factor list
            message: Error message (only status="error" exist)
    """
    try:
        return _json_response(get_value_factor_bundle(symbol))
    except Exception as exc:
        logger.error("Failed to obtain value factor package: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"获取价值因子包失败: {exc}"})


@tool
@register_tool(
    tool_id="get_quality_factor_bundle_tool",
    name="质量因子包",
    description=(
        "Returns the stock s quality_core package of standardized quality factors."
        "Suitable for obtaining ROE, ROA, gross profit margin, net profit margin, asset-liability ratio, current ratio, ROIC,"
        "Quality metrics such as cash conversion ratio, accrual ratio, interest coverage ratio, Piotroski F-Score, Altman Z-Score, Beneish M-Score and more."
        "Here s quality Refers to company fundamentals and financial statement quality, not data quality, reporting quality, technical signal quality, or product quality."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "When the Agent needs to judge the company s profit quality, financial health, debt solvency, profit content,"
        "Used when dealing with earnings manipulation risk or financial distress risk."
        "If you want to directly get a set of quality indicators for scoring, screening or report generation, bind this tool first."
    ),
    when_not_to_use=(
        "It is not suitable for judging whether the valuation is expensive or not, nor is it suitable for outputting technical indicators such as MA, RSI, and MACD."
        "Not used for data quality inspection, report quality review, technical signal quality or short-term capital flow analysis."
        "If you need the valuation factor, please use get_value_factor_bundle_tool. If you need the technical factor, please use get_technical_factor_bundle_tool."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol,bundle=quality_core, factors, factor_diagnostics, "
        "factor_warnings、calculation_notes、missing_factors。"
        "factors The key fields include roe, roa, gross_margin, netprofit_margin, debt_to_assets, current_ratio, quick_ratio, cash_ratio,"
        "roic、cash_conversion、accrual_ratio、asset_turnover、gross_profit_to_assets、interest_coverage、inventory_turnover、"
        "receivable_turnover、net_cash_position、piotroski_f_score、altman_z_score、beneish_m_score。"
    ),
    example="get_quality_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_value_factor_bundle_tool",
        "get_growth_cashflow_factor_bundle_tool",
        "get_fundamental_factor_snapshot_tool",
    ],
)
def get_quality_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get a package of standardized quality factors.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            bundle: Factor package identifier, fixed to "quality_core"
            factors: dict quality factor set——
                — roe: ROE
                — roa: return on total assets
                — gross_margin: Gross profit margin
                — netprofit_margin: net profit margin
                — debt_to_assets: Asset-liability ratio
                — assets_to_eqt: equity multiplier
                — current_ratio: current ratio
                — quick_ratio: quick ratio
                — cash_ratio: cash ratio
                — roic: return on invested capital
                — cash_conversion: Cash conversion ratio (operating cash flow/net profit)
                — accrual_ratio: Accrual profit ratio (%)
                — asset_turnover: total asset turnover ratio
                — gross_profit_to_assets: Gross profit/total assets (%)
                — interest_coverage: interest coverage ratio
                — inventory_turnover: Inventory turnover
                — receivable_turnover: Accounts receivable turnover ratio
                — net_cash_position: net cash position
                — piotroski_f_score: Piotroski F-Score
                — altman_z_score: Altman Z-Score
                — beneish_m_score: Beneish M-Score
            factor_diagnostics: dict Factor diagnostic information
            factor_warnings: dict Factor alarm information
            calculation_notes: list[str] Calculation instructions
            missing_factors: list[str] Missing factor list
            message: Error message (only status="error" exist)
    """
    try:
        return _json_response(get_quality_factor_bundle(symbol))
    except Exception as exc:
        logger.error("Failed to obtain quality factor package: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"获取质量因子包失败: {exc}"})


@tool
@register_tool(
    tool_id="get_growth_cashflow_factor_bundle_tool",
    name="成长现金流因子包",
    description=(
        "Returns the growth_cashflow_core package of standardized growth/cashflow factors for the stock."
        "Suitable for obtaining year-on-year revenue, year-on-year net profit, year-on-year operating profit, three-year CAGR, TTM revenue, TTM net profit,"
        "Operating cash flow, free cash flow, free cash flow yield, operating cash flow yield, net working capital and other indicators."
        "It can be used to analyze deterioration of cash flow, identify continued decline in operating cash flow, identify long-term negative free cash flow, and judge the quality of cash income."
        "Profit content assessment, financial risk signal identification and growth quality analysis."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=["growth_analysis", "cashflow_quality", "cashflow_deterioration", "operating_cashflow", "free_cashflow", "financial_risk"],
    tool_role_hint="specialized",
    output_shape="structured_json",
    preferred_for=["cashflow_quality_analysis", "financial_risk_signal_detection", "growth_quality_analysis", "valuation_analysis"],
    when_to_use=(
        "When the Agent needs to judge the company s growth rate, cash flow hematopoietic ability, free cash flow quality,"
        "Whether operating cash flow continues to decline, whether free cash flow is negative for a long time, whether the quality of cash income deteriorates,"
        "Used when working capital changes. Ideal for front-loading growth analysis, cash flow health analysis, cash flow deterioration risk identification, and PEG/growth valuation."
    ),
    when_not_to_use=(
        "It is not suitable for separate valuation multiple comparisons, nor is it suitable for technical timing."
        "The cash flow here is operating/free cash flow based on financial statements and is not used to inquire about main capital flow, northbound capital, transaction capital flow or short-term trading capital."
        "If the target is valuation fields such as PE/PB/dividend rate, use get_value_factor_bundle_tool first."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol,bundle=growth_cashflow_core, factors, factor_warnings, "
        "calculation_notes、missing_factors。"
        "factors The key fields include revenue_yoy, net_profit_yoy, oper_profit_yoy, revenue_cagr_3y, profit_cagr_3y,"
        "revenue_ttm、net_profit_ttm、n_cashflow_act、fcf、fcf_yield、fcf_margin、ocf_yield、net_working_capital、working_capital_change。"
    ),
    example="get_growth_cashflow_factor_bundle_tool(symbol='600519')",
    related_tools=[
        "get_value_factor_bundle_tool",
        "get_quality_factor_bundle_tool",
        "get_fundamental_factor_snapshot_tool",
    ],
)
def get_growth_cashflow_factor_bundle_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get the standardized growth/cash flow factor package.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            bundle: Factor package identifier, fixed to "growth_cashflow_core"
            factors: dict Growth/cash flow factor set——
                — revenue_yoy: Year-on-year revenue growth rate
                — net_profit_yoy: Net profit year-on-year growth rate
                — oper_profit_yoy: Operating profit year-on-year growth rate
                — revenue_cagr_3y: Revenue for 3 years CAGR
                — profit_cagr_3y: Net profit for 3 years CAGR
                — revenue_ttm: TTM Revenue
                — net_profit_ttm: TTM net profit
                — n_cashflow_act: operating cash flow
                — fcf: free cash flow
                — fcf_yield: Free cash flow yield (%)
                — fcf_margin: Free cash flow margin (%)
                — ocf_yield: Operating cash flow yield (%)
                — total_cur_assets: current assets
                — total_cur_liab: current liabilities
                — net_working_capital: net working capital
                — working_capital_change: working capital changes
            factor_warnings: dict Factor alarm information
            calculation_notes: list[str] Calculation instructions
            missing_factors: list[str] Missing factor list
            message: Error message (only status="error" exist)
    """
    try:
        return _json_response(get_growth_cashflow_factor_bundle(symbol))
    except Exception as exc:
        logger.error("Failed to obtain growth cash flow factor package: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain growth cash flow factor package: {exc}"})


@tool
@register_tool(
    tool_id="get_fundamental_factor_snapshot_tool",
    name="标准化基本面因子快照",
    description=(
        "Returns a snapshot of the total normalized fundamental factors for a single A-share stock."
        "This is an aggregation tool that will provide three factor packages: value_core, quality_core, and growth_cashflow_core at the same time."
        "It is suitable for Agent to obtain most common fundamental indicators after one binding without the need to call multiple tools separately."
    ),
    category="fundamentals",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "When the Agent needs to obtain a complete snapshot of fundamental factors at one time for comprehensive analysis, report generation, preliminary screening,"
        "Or it can be used later when doing multi-dimensional interpretation in Prompt."
    ),
    when_not_to_use=(
        "If the Agent only cares about a certain type of indicators, it should first bind narrower bundle tools to avoid taking too many irrelevant fields."
        "For example, if you only do valuation, use get_value_factor_bundle_tool, and if you only do financial quality, use get_quality_factor_bundle_tool."
    ),
    returns=(
        "Returns a JSON string, the structure contains symbol, name, industry, current_price, report_period, data_source,"
        "factors、factor_diagnostics、factor_warnings、missing_factors、bundles。"
        "bundles The following groups are grouped by value_core, quality_core, and growth_cashflow_core, which are suitable for direct consumption by Agent."
    ),
    example="get_fundamental_factor_snapshot_tool(symbol='600519')",
    related_tools=[
        "get_value_factor_bundle_tool",
        "get_quality_factor_bundle_tool",
        "get_growth_cashflow_factor_bundle_tool",
    ],
)
def get_fundamental_factor_snapshot_tool(
    symbol: Annotated[str, "A stock code, such as 600519,000001"]
) -> str:
    """Get a snapshot of normalized fundamental factors.

    Args:
        symbol: A stock stock code, such as "600519", "000001"

    Returns:
        str: JSON String, field description——
            status: status (only in case of exception) "error") 
            symbol: Standardized stock code
            name: Stock name
            industry: Industry
            current_price: current price
            report_period: reporting period
            data_source: Data source
            factors: dict All factors after combining (value_core + quality_core + growth_cashflow_core) 
            factor_diagnostics: dict Combined factor diagnostic information
            factor_warnings: dict Merged factor alarm information
            missing_factors: list[str] Merged list of missing factors (deduplication sorting)
            bundles: dict three factor package grouping——
                — value_core: dict Value factor package (the structure is the same as that returned by get_value_factor_bundle_tool)
                — quality_core: dict Quality factor package (the structure is the same as that returned by get_quality_factor_bundle_tool)
                — growth_cashflow_core: dict Growth cash flow factor package (the structure is the same as that returned by get_growth_cashflow_factor_bundle_tool)
            message: Error message (only status="error" exist)
    """
    try:
        snapshot = get_fundamental_factor_snapshot(symbol)
        return _json_response(snapshot)
    except Exception as exc:
        logger.error("Normalized fundamental factor snapshot acquisition failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"获取基本面因子快照失败: {exc}"})


__all__ = [
    "get_value_factor_bundle_tool",
    "get_quality_factor_bundle_tool",
    "get_growth_cashflow_factor_bundle_tool",
    "get_fundamental_factor_snapshot_tool",
]