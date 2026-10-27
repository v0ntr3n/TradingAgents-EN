"""Skill Runtime factor directory.

Put the current warehouse Already have data + Already helper + Indicators have been achieved Common factors that can stabilize support
Organized into a structured directory for reuse in the following scenarios:

1. Quick selection when implementing skills manually
2. Whitelist constraints for generative skills
3. When workflow/Agent requires capability gap analysis, give priority to reusing ready-made factors
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Dict, List, Literal, Optional

from .factor_schema import (
    COND_ACCOUNTS_RECEIV_NON_ZERO,
    COND_ALL_REQUIRED_SIGNAL_INPUTS_AVAILABLE,
    COND_ASSET_QUALITY_PREVIOUS_NON_ZERO,
    COND_BASE_PERIOD_AVAILABLE,
    COND_BASE_VALUE_POSITIVE,
    COND_COMPARISON_PERIOD_AVAILABLE,
    COND_CURRENT_VALUE_POSITIVE,
    COND_DEPRECIATION_PLUS_FIXED_ASSETS_CURRENT_NON_ZERO,
    COND_DEPRECIATION_PLUS_FIXED_ASSETS_PREVIOUS_NON_ZERO,
    COND_GROSS_MARGIN_CURRENT_NON_ZERO,
    COND_INDUSTRY_PEER_SAMPLE_COUNT_GE_5,
    COND_INTEREST_EXPENSE_POSITIVE,
    COND_INVENTORIES_NON_ZERO,
    COND_INVESTED_CAPITAL_POSITIVE,
    COND_MARKET_CAP_NON_ZERO,
    COND_NET_PROFIT_NON_ZERO,
    COND_NET_PROFIT_YOY_NON_ZERO,
    COND_NET_PROFIT_YOY_POSITIVE,
    COND_PREVIOUS_PERIOD_AVAILABLE,
    COND_PRIOR_PERIOD_METRIC_NON_ZERO,
    COND_REVENUE_BASE_NON_ZERO,
    COND_SALES_CURRENT_NON_ZERO,
    COND_SALES_PREVIOUS_NON_ZERO,
    COND_SGA_PREVIOUS_NON_ZERO,
    COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE,
    COND_TOTAL_ASSETS_CURRENT_NON_ZERO,
    COND_TOTAL_ASSETS_NON_ZERO,
    COND_TOTAL_ASSETS_PREVIOUS_NON_ZERO,
    COND_TOTAL_EQUITY_NON_ZERO,
    COND_TOTAL_LIAB_NON_ZERO,
    COND_TOTAL_LIAB_PREVIOUS_NON_ZERO,
    P0_FACTOR_FIELD_SCHEMA,
    P0_SOURCE_PRIORITY_BY_FIELD,
    TECHNICAL_FACTOR_FIELD_SCHEMA,
    WARN_DIVIDEND_YIELD_FALLBACK_TO_FINANCIAL_FIELD,
    WARN_FCF_CONSERVATIVE_PROXY_USED,
    WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5,
    WARN_INTEREST_COVERAGE_FALLBACK_TO_RAW_INTEREST_EXPENSE,
    WARN_INVENTORY_TURNOVER_COST_PROXY_USED,
    WARN_NET_CASH_POSITION_PROXY_TOTAL_NCL_USED,
    WARN_NET_PROFIT_TTM_FALLBACK_TO_NET_PROFIT_OR_NET_INCOME,
    WARN_PB_FALLBACK_TO_PB_MRQ,
    WARN_PB_MRQ_ESTIMATED_FROM_MARKET_CAP_AND_EQUITY,
    WARN_PE_TTM_FALLBACK_TO_PE,
    WARN_PS_TTM_FALLBACK_TO_PS,
    WARN_ROIC_MONEY_CAP_MISSING_AS_ZERO,
    list_bundle_fields,
)


SCHEMA_TAG_BY_CONTRACT_CATEGORY = {
    "fallback_chain": "fallback_chain",
    "denominator_guards": "denominator_guard",
    "unit_conversions": "unit_conversion",
    "conservative_proxies": "conservative_proxy",
    "availability_constraints": "availability_guard",
}


FactorCategory = Literal[
    "valuation",
    "quality",
    "growth",
    "cashflow",
    "momentum",
    "technical",
    "trading",
    "risk",
]

ImplementationLevel = Literal[
    "ready",
    "derived",
    "time_series",
    "cautious",
]


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    display_name: str
    category: FactorCategory
    description: str
    implementation_level: ImplementationLevel
    primary_sources: List[str] = field(default_factory=list)
    helper_functions: List[str] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)
    formula: Optional[str] = None
    fallback_rules: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeSemanticContract:
    direct_fields: List[str] = field(default_factory=list)
    source_priority: List[str] = field(default_factory=list)
    fallback_chain: List[str] = field(default_factory=list)
    denominator_guards: List[str] = field(default_factory=list)
    unit_conversions: List[str] = field(default_factory=list)
    conservative_proxies: List[str] = field(default_factory=list)
    availability_constraints: List[str] = field(default_factory=list)
    tax_estimation_strategy: str | None = None
    period_selection_strategy: str | None = None
    minimum_input_groups: List[List[str]] = field(default_factory=list)
    minimum_computable_conditions: List[str] = field(default_factory=list)
    warning_conditions: List[str] = field(default_factory=list)
    warning_categories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _missing_text_fragments(notes: List[str], expected_fragments: List[str]) -> List[str]:
    combined = "\n".join(notes)
    return [fragment for fragment in expected_fragments if fragment not in combined]


COMMON_FACTOR_CATALOG: Dict[str, FactorDefinition] = {
    "pe": FactorDefinition(
        factor_id="pe",
        display_name="P/E ratio",
        category="valuation",
        description="Static P/E ratio is suitable for horizontal valuation comparisons.",
        implementation_level="ready",
        primary_sources=["stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_basic_info", "get_market_quotes"],
        required_fields=["pe"],
        fallback_rules=["If basic_info.pe is missing, try market_quotes.pe"],
    ),
    "pe_ttm": FactorDefinition(
        factor_id="pe_ttm",
        display_name="rolling price to earnings ratio",
        category="valuation",
        description="Preferred PE valuation master field.",
        implementation_level="ready",
        primary_sources=["stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_valuation_context", "get_stock_basic_info"],
        required_fields=["pe_ttm"],
        fallback_rules=["Fallback to when missing pe"],
    ),
    "pb": FactorDefinition(
        factor_id="pb",
        display_name="price to book ratio",
        category="valuation",
        description="Suitable for valuation comparison in financial, cyclical, and asset-heavy industries.",
        implementation_level="ready",
        primary_sources=["stock_basic_info"],
        helper_functions=["get_stock_valuation_context", "get_stock_basic_info"],
        required_fields=["pb"],
        fallback_rules=["Fallback to when missing pb_mrq"],
    ),
    "pb_mrq": FactorDefinition(
        factor_id="pb_mrq",
        display_name="Latest price-to-book ratio",
        category="valuation",
        description="The latest caliber PB can be used as the fallback field of PB.",
        implementation_level="ready",
        primary_sources=["stock_basic_info", "stock_financial_periods", "market_quotes"],
        helper_functions=["get_stock_basic_info", "get_stock_financial_periods", "get_market_quotes"],
        required_fields=["pb_mrq|total_mv", "total_equity"],
        fallback_rules=["If basic_info.pb_mrq is missing, fallback to the latest conservative estimate of total_mv / total_equity."],
        warnings=["When using total_mv / total_equity backfill, it is a conservative estimate in the latest period."],
    ),
    "ps_ttm": FactorDefinition(
        factor_id="ps_ttm",
        display_name="rolling price-to-sales ratio",
        category="valuation",
        description="Suitable for companies with unstable profits but comparable revenue.",
        implementation_level="ready",
        primary_sources=["stock_basic_info"],
        helper_functions=["get_stock_valuation_context", "get_stock_basic_info"],
        required_fields=["ps_ttm"],
        fallback_rules=["Fallback to when missing ps"],
    ),
    "dividend_yield": FactorDefinition(
        factor_id="dividend_yield",
        display_name="dividend yield",
        category="valuation",
        description="Suitable for screening high-dividend, defensive assets.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["dividend_yield|financial_indicators.dividend_yield"],
        fallback_rules=["Basic_info.dividend_yield is used first. If missing, it falls back to the latest financial period financial_indicators.dividend_yield or period top-level dividend_yield."],
    ),
    "peg": FactorDefinition(
        factor_id="peg",
        display_name="PEG",
        category="valuation",
        description="PE TTM The ratio to the year-on-year growth rate of net profit.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods", "stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_financial_periods", "get_stock_basic_info", "get_market_quotes"],
        required_fields=["pe_ttm|pe", "net_profit_yoy"],
        formula="pe_ttm / net_profit_yoy",
        fallback_rules=["pe_ttm Fallback to pe when missing."],
        warnings=["It is only calculated when the year-on-year net profit is positive and non-zero, otherwise it returns a null value."],
    ),
    "industry_pe_median": FactorDefinition(
        factor_id="industry_pe_median",
        display_name="Industry PE median",
        category="valuation",
        description="Benchmark valuations used for cross-industry comparisons.",
        implementation_level="derived",
        primary_sources=["stock_basic_info"],
        helper_functions=["summarize_industry_valuation", "get_stock_basic_info"],
        required_fields=["industry", "pe_ttm|pe"],
        formula="summarize_industry_valuation(industry, metric='pe')['median']",
        warnings=["Industry sample number recommendations >= 5, The sample is too small for reference only"],
    ),
    "industry_pb_median": FactorDefinition(
        factor_id="industry_pb_median",
        display_name="Industry Median PB",
        category="valuation",
        description="Used for horizontal comparison in asset-heavy industries.",
        implementation_level="derived",
        primary_sources=["stock_basic_info"],
        helper_functions=["summarize_industry_valuation", "get_stock_basic_info"],
        required_fields=["industry", "pb|pb_mrq"],
        formula="summarize_industry_valuation(industry, metric='pb')['median']",
    ),
    "roe": FactorDefinition(
        factor_id="roe",
        display_name="ROE",
        category="quality",
        description="Core earnings quality indicators.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["roe"],
    ),
    "roa": FactorDefinition(
        factor_id="roa",
        display_name="return on total assets",
        category="quality",
        description="Measure asset efficiency.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["roa"],
    ),
    "gross_margin": FactorDefinition(
        factor_id="gross_margin",
        display_name="Gross profit margin",
        category="quality",
        description="Measure product/business bargaining power.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["gross_margin"],
    ),
    "netprofit_margin": FactorDefinition(
        factor_id="netprofit_margin",
        display_name="net profit margin",
        category="quality",
        description="Measures the ability to convert revenue into profit.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["netprofit_margin"],
    ),
    "debt_to_assets": FactorDefinition(
        factor_id="debt_to_assets",
        display_name="Asset-liability ratio",
        category="risk",
        description="Financial leverage and debt repayment pressure indicators.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["debt_to_assets"],
    ),
    "assets_to_eqt": FactorDefinition(
        factor_id="assets_to_eqt",
        display_name="equity multiplier",
        category="risk",
        description="The leverage ratio of total assets to shareholders equity.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["assets_to_eqt"],
    ),
    "current_ratio": FactorDefinition(
        factor_id="current_ratio",
        display_name="current ratio",
        category="risk",
        description="Short-term solvency indicator.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["current_ratio"],
    ),
    "quick_ratio": FactorDefinition(
        factor_id="quick_ratio",
        display_name="quick ratio",
        category="risk",
        description="Short-term solvency after excluding inventories.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["quick_ratio"],
    ),
    "cash_ratio": FactorDefinition(
        factor_id="cash_ratio",
        display_name="cash ratio",
        category="risk",
        description="The most conservative short-term solvency.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["cash_ratio"],
    ),
    "net_working_capital": FactorDefinition(
        factor_id="net_working_capital",
        display_name="net working capital",
        category="cashflow",
        description="Current assets less current liabilities measure operating buffers.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["total_cur_assets", "total_cur_liab"],
        formula="total_cur_assets - total_cur_liab",
    ),
    "revenue_ttm": FactorDefinition(
        factor_id="revenue_ttm",
        display_name="rolling revenue",
        category="growth",
        description="Suitable as a baseline for growth scale.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue_ttm"],
    ),
    "net_profit_ttm": FactorDefinition(
        factor_id="net_profit_ttm",
        display_name="rolling net profit",
        category="growth",
        description="Growth stock profit scale baseline.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["net_profit_ttm|net_profit|net_income"],
        fallback_rules=["Use net_profit_ttm in preference, falling back to net_profit or net_income if missing."],
    ),
    "piotroski_f_score": FactorDefinition(
        factor_id="piotroski_f_score",
        display_name="Piotroski F-Score",
        category="quality",
        description="Quality score based on 9-point financial signals from the last two periods.",
        implementation_level="cautious",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["roa", "n_cashflow_act", "current_ratio", "gross_margin", "asset_turnover"],
        warnings=["Rely on comparable financial records in the last two periods; missing comparison periods or key fields should be considered cautious output."],
    ),
    "altman_z_score": FactorDefinition(
        factor_id="altman_z_score",
        display_name="Altman Z-Score",
        category="risk",
        description="Financial Distress Risk Score.",
        implementation_level="cautious",
        primary_sources=["stock_financial_periods", "stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_financial_periods", "get_stock_basic_info", "get_market_quotes"],
        required_fields=["total_assets", "total_liab", "total_cur_assets", "total_cur_liab", "ebit", "revenue"],
        warnings=["Depending on the caliber of retained earnings, EBIT and market capitalization, if a key component is missing or the denominator is abnormal, a null value should be returned with a diagnosis."],
    ),
    "beneish_m_score": FactorDefinition(
        factor_id="beneish_m_score",
        display_name="Beneish M-Score",
        category="risk",
        description="Earnings manipulation risk identification score.",
        implementation_level="cautious",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue", "accounts_receiv", "oper_cost", "total_assets", "total_cur_assets", "fix_assets", "n_cashflow_act"],
        warnings=["Strongly dependent on the original depreciation, amortization and expense fields of the last two periods, the current true coverage may be affected by the completeness of raw_data."],
    ),
    "n_cashflow_act": FactorDefinition(
        factor_id="n_cashflow_act",
        display_name="Net operating cash flow",
        category="cashflow",
        description="Core indicators of cash flow quality.",
        implementation_level="ready",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["n_cashflow_act"],
    ),
    "revenue_yoy": FactorDefinition(
        factor_id="revenue_yoy",
        display_name="Year-on-year revenue",
        category="growth",
        description="The latest reporting period shows year-on-year revenue growth compared to the same quarter last year.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue|oper_rev", "Same quarter reporting period last year"],
        formula="(Revenue for the current period - revenue for the same quarter last year) / Revenue in the same quarter last year",
        warnings=["Returns NULL if the reporting period for the same quarter of the previous year is missing or the base period is 0."],
    ),
    "net_profit_yoy": FactorDefinition(
        factor_id="net_profit_yoy",
        display_name="Net profit year-on-year",
        category="growth",
        description="The latest reporting period shows a year-on-year growth rate of net profit compared to the same quarter last year.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["net_profit|net_income", "Same quarter reporting period last year"],
        formula="(Net profit for the current period - net profit for the same quarter last year) / Net profit in the same quarter last year",
        warnings=["Returns NULL if the reporting period for the same quarter of the previous year is missing or the base period is 0."],
    ),
    "oper_profit_yoy": FactorDefinition(
        factor_id="oper_profit_yoy",
        display_name="Operating profit year-on-year",
        category="growth",
        description="The year-on-year growth rate of operating profit in the latest reporting period compared to the same quarter last year.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["oper_profit|operating_profit|ebit", "Same quarter reporting period last year"],
        formula="(Operating profit for the current period - operating profit for the same quarter last year) / Operating profit in the same quarter last year",
        warnings=["Returns NULL if the reporting period for the same quarter of the previous year is missing or the base period is 0."],
    ),
    "revenue_cagr_3y": FactorDefinition(
        factor_id="revenue_cagr_3y",
        display_name="Three-year compound growth rate of revenue",
        category="growth",
        description="Three-year revenue CAGR compared to same quarter three years ago.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue_ttm|revenue|oper_rev", "Reporting period three years ago in the same quarter"],
        formula="(Revenue_t/Revenue_t-3)^(1/3) - 1",
        warnings=["A null value is returned if the reporting period three years ago in the same quarter is missing, the base period is non-positive, or the current value is non-positive."],
    ),
    "profit_cagr_3y": FactorDefinition(
        factor_id="profit_cagr_3y",
        display_name="Three-year compound growth rate of net profit",
        category="growth",
        description="Three-year net profit CAGR in the same quarter compared to three years ago.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["net_profit_ttm|net_profit|net_income", "Reporting period three years ago in the same quarter"],
        formula="(Net profit_t / net profit_t-3)^(1/3) - 1",
        warnings=["A null value is returned if the reporting period three years ago in the same quarter is missing, the base period is non-positive, or the current value is non-positive."],
    ),
    "roic": FactorDefinition(
        factor_id="roic",
        display_name="return on invested capital",
        category="quality",
        description="Operating profit approximates ROIC, a conservative proxy for EBIT.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["ebit|oper_profit|operating_profit", "total_equity", "total_liab"],
        formula="NOPAT / (total_equity + total_liab - money_cap)",
        fallback_rules=["The tax rate is first estimated based on total_profit and net_profit. If missing, the default tax rate of 25% is used.", "money_cap If missing, treat it as 0."],
        warnings=["The current implementation uses the latest period caliber and a conservative proxy, not strictly average invested capital ROIC."],
    ),
    "cash_conversion": FactorDefinition(
        factor_id="cash_conversion",
        display_name="Profit to cash conversion rate",
        category="cashflow",
        description="The conversion ability of operating cash flow relative to net profit.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["n_cashflow_act", "net_profit|net_income"],
        formula="n_cashflow_act / net_profit",
        warnings=["Returns null if net profit is missing or 0."],
    ),
    "accrual_ratio": FactorDefinition(
        factor_id="accrual_ratio",
        display_name="accruals ratio",
        category="quality",
        description="Deviation between net profit and operating cash flow.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["net_profit|net_income", "n_cashflow_act", "total_assets"],
        formula="(net_profit - n_cashflow_act) / total_assets",
        warnings=["Currently, the latest total assets are used as the denominator and the percentage is output, not the average total assets."],
    ),
    "asset_turnover": FactorDefinition(
        factor_id="asset_turnover",
        display_name="asset turnover rate",
        category="quality",
        description="The turnover efficiency of operating income relative to total assets.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue_ttm|revenue|oper_rev", "total_assets"],
        formula="revenue_base / total_assets",
        warnings=["Currently, the latest total assets are used as the denominator, not the average total assets."],
    ),
    "gross_profit_to_assets": FactorDefinition(
        factor_id="gross_profit_to_assets",
        display_name="gross profit to assets ratio",
        category="quality",
        description="Efficiency indicator of gross profit relative to total assets.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue_ttm|revenue|oper_rev", "gross_margin", "total_assets"],
        formula="revenue_base * gross_margin / total_assets",
        warnings=["Currently, the latest total assets are used as the denominator and the percentage is output, not the average total assets."],
    ),
    "interest_coverage": FactorDefinition(
        factor_id="interest_coverage",
        display_name="interest coverage ratio",
        category="risk",
        description="EBIT Coverage of interest charges.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["ebit|oper_profit|operating_profit", "fin_exp|raw_data.income_statement.int_exp"],
        formula="ebit / interest_expense",
        fallback_rules=["Prefer ebit/fin_exp.", "When fin_exp <= 0 fallback to int_exp or fin_exp_int_exp in raw income."],
        warnings=["Returns NULL when the interest charge is missing, non-positive, or cannot be backfilled from raw_data."],
    ),
    "inventory_turnover": FactorDefinition(
        factor_id="inventory_turnover",
        display_name="Inventory turnover",
        category="quality",
        description="Turnover efficiency of operating costs relative to inventory balance.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["oper_cost|revenue_ttm|revenue|oper_rev", "inventories"],
        formula="cost_base / inventories",
        fallback_rules=["oper_cost When missing, allows revenue_base and gross_margin to be used to infer cost proxies."],
        warnings=["Currently the latest inventory balance is used instead of the average inventory balance."],
    ),
    "receivable_turnover": FactorDefinition(
        factor_id="receivable_turnover",
        display_name="Accounts receivable turnover ratio",
        category="quality",
        description="The turnover efficiency of operating income relative to the latest accounts receivable balance.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["revenue_ttm|revenue|oper_rev", "accounts_receiv"],
        formula="revenue_base / accounts_receiv",
        warnings=["Currently the latest receivable balance is used instead of the average receivable balance."],
    ),
    "net_cash_position": FactorDefinition(
        factor_id="net_cash_position",
        display_name="net cash position",
        category="risk",
        description="A conservative net cash measure of monetary funds relative to a proxy for debt and total assets.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["money_cap", "total_assets", "total_ncl|total_liab|total_cur_liab"],
        formula="(money_cap - debt_proxy) / total_assets",
        fallback_rules=["Use total_ncl in preference.", "When total_ncl is missing, the fallback is total_liab - total_cur_liab."],
        warnings=["The current output is the conservative agent caliber percentage."],
    ),
    "fcf": FactorDefinition(
        factor_id="fcf",
        display_name="free cash flow",
        category="cashflow",
        description="Conservative proxy measure of free cash flow.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["n_cashflow_act", "n_cashflow_inv_act"],
        formula="n_cashflow_act + n_cashflow_inv_act",
        warnings=["At present, it is not strictly a matter of capital expenditure; n_cashflow_act + n_cashflow_inv_act conservative agent."],
    ),
    "fcf_yield": FactorDefinition(
        factor_id="fcf_yield",
        display_name="free cash flow yield",
        category="valuation",
        description="The rate of return on free cash flow relative to total market capitalization.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods", "stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_financial_periods", "get_stock_basic_info", "get_market_quotes"],
        required_fields=["fcf", "total_mv|market_cap"],
        formula="fcf / total_mv",
        warnings=["The market capitalization field is currently converted on a billion-yuan basis, and free cash flow is calculated on a yuan basis."],
    ),
    "fcf_margin": FactorDefinition(
        factor_id="fcf_margin",
        display_name="free cash flow rate",
        category="cashflow",
        description="The ratio of free cash flow to revenue.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["fcf", "revenue_ttm|revenue|oper_rev"],
        formula="fcf / revenue_base",
        fallback_rules=["The current revenue will be given priority using revenue_ttm, and if it is missing, it will fall back to single-period revenue/oper_rev."],
    ),
    "ocf_yield": FactorDefinition(
        factor_id="ocf_yield",
        display_name="operating cash flow yield",
        category="valuation",
        description="The return rate of operating cash flow relative to total market capitalization.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods", "stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_financial_periods", "get_stock_basic_info", "get_market_quotes"],
        required_fields=["n_cashflow_act", "total_mv|market_cap"],
        formula="n_cashflow_act / total_mv",
        warnings=["The market capitalization field is currently converted based on the caliber of 100 million yuan."],
    ),
    "working_capital_change": FactorDefinition(
        factor_id="working_capital_change",
        display_name="working capital changes",
        category="cashflow",
        description="The difference in net working capital between the two most recent periods.",
        implementation_level="derived",
        primary_sources=["stock_financial_periods"],
        helper_functions=["get_stock_financial_periods"],
        required_fields=["The last two issues total_cur_assets", "The last two issues total_cur_liab"],
        formula="net_working_capital_t - net_working_capital_t-1",
        warnings=["A null value is returned if any of the most recent two periods of current assets/current liabilities is missing."],
    ),
    "pct_chg": FactorDefinition(
        factor_id="pct_chg",
        display_name="Increase or decrease",
        category="momentum",
        description="Latest daily rise and fall.",
        implementation_level="ready",
        primary_sources=["market_quotes", "stock_daily_quotes"],
        helper_functions=["get_market_quotes", "get_stock_daily_quotes"],
        required_fields=["pct_chg"],
    ),
    "turnover_rate": FactorDefinition(
        factor_id="turnover_rate",
        display_name="turnover rate",
        category="trading",
        description="Trading activity indicator.",
        implementation_level="ready",
        primary_sources=["stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_basic_info", "get_market_quotes"],
        required_fields=["turnover_rate"],
    ),
    "volume_ratio": FactorDefinition(
        factor_id="volume_ratio",
        display_name="Quantity ratio",
        category="trading",
        description="Short-term volume increase/reduction intensity.",
        implementation_level="ready",
        primary_sources=["stock_basic_info", "market_quotes"],
        helper_functions=["get_stock_basic_info", "get_market_quotes"],
        required_fields=["volume_ratio"],
    ),
    "ma20": FactorDefinition(
        factor_id="ma20",
        display_name="20 daily moving average",
        category="technical",
        description="Short to medium term trend baseline.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["close"],
        formula="MA(close, 20)",
        warnings=["At least 20 trading days of historical market conditions."],
    ),
    "ma60": FactorDefinition(
        factor_id="ma60",
        display_name="60 daily moving average",
        category="technical",
        description="Mid-term trend baseline.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["close"],
        formula="MA(close, 60)",
        warnings=["At least 60 trading days of historical market conditions."],
    ),
    "rsi14": FactorDefinition(
        factor_id="rsi14",
        display_name="RSI14",
        category="technical",
        description="Commonly used overbought and oversold indicators.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["close"],
        formula="RSI(close, 14)",
        warnings=["At least 14 trading days of historical market conditions."],
    ),
    "kdj_k": FactorDefinition(
        factor_id="kdj_k",
        display_name="KDJ-K",
        category="technical",
        description="KDJ Stochastic indicator K value.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["high", "low", "close"],
        formula="KDJ(high, low, close).k",
        warnings=["At least 9 trading days of high and low closing sequences."],
    ),
    "kdj_d": FactorDefinition(
        factor_id="kdj_d",
        display_name="KDJ-D",
        category="technical",
        description="KDJ Stochastic indicator D value.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["high", "low", "close"],
        formula="KDJ(high, low, close).d",
        warnings=["At least 9 trading days of high and low closing sequences."],
    ),
    "kdj_j": FactorDefinition(
        factor_id="kdj_j",
        display_name="KDJ-J",
        category="technical",
        description="KDJ Stochastic J value.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["high", "low", "close"],
        formula="KDJ(high, low, close).j",
        warnings=["At least 9 trading days of high and low closing sequences."],
    ),
    "dif": FactorDefinition(
        factor_id="dif",
        display_name="MACD-DIF",
        category="technical",
        description="MACD The difference between fast and slow lines.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["close"],
        formula="MACD(close).dif",
        warnings=["At least 26 trading days of historical market conditions."],
    ),
    "dea": FactorDefinition(
        factor_id="dea",
        display_name="MACD-DEA",
        category="technical",
        description="MACD signal line.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["close"],
        formula="MACD(close).dea",
        warnings=["At least 26 trading days of historical market conditions."],
    ),
    "macd_hist": FactorDefinition(
        factor_id="macd_hist",
        display_name="MACD bar chart",
        category="technical",
        description="MACD The degree of momentum diffusion.",
        implementation_level="time_series",
        primary_sources=["stock_daily_quotes"],
        helper_functions=["get_stock_daily_quotes", "compute_many"],
        required_fields=["close"],
        formula="MACD(close).hist",
        warnings=["At least 26 trading days of historical market conditions."],
    ),
}


P0_BUNDLE_FACTOR_PACKS: Dict[str, List[str]] = {
    "value_core": list_bundle_fields("value_core"),
    "quality_core": list_bundle_fields("quality_core"),
    "growth_cashflow_core": list_bundle_fields("growth_cashflow_core"),
}


RECOMMENDED_FACTOR_PACKS: Dict[str, List[str]] = {
    **P0_BUNDLE_FACTOR_PACKS,
    "growth_core": list(P0_BUNDLE_FACTOR_PACKS["growth_cashflow_core"]),
    "technical_core": [
        "ma20",
        "ma60",
        "rsi14",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "dif",
        "dea",
        "macd_hist",
    ],
    "liquidity_core": [
        "pct_chg",
        "turnover_rate",
        "volume_ratio",
    ],
}


FACTOR_RUNTIME_SEMANTIC_CONTRACTS: Dict[str, RuntimeSemanticContract] = {
    "pe": RuntimeSemanticContract(direct_fields=["pe"], source_priority=["basic_info.pe", "market_quotes.pe"], minimum_input_groups=[["pe"]]),
    "pe_ttm": RuntimeSemanticContract(direct_fields=["pe_ttm"], source_priority=["basic_info.pe_ttm", "basic_info.pe", "market_quotes.pe"], fallback_chain=["pe"], minimum_input_groups=[["pe_ttm"], ["pe"]], warning_conditions=[WARN_PE_TTM_FALLBACK_TO_PE], warning_categories=["fallback_used"]),
    "pb": RuntimeSemanticContract(direct_fields=["pb"], source_priority=["basic_info.pb", "pb_mrq"], fallback_chain=["pb_mrq"], minimum_input_groups=[["pb"], ["pb_mrq"]], warning_conditions=[WARN_PB_FALLBACK_TO_PB_MRQ], warning_categories=["fallback_used"]),
    "pb_mrq": RuntimeSemanticContract(
        direct_fields=["pb_mrq|total_mv", "total_equity"],
        source_priority=["basic_info.pb_mrq", "market_quotes.total_mv|basic_info.total_mv|basic_info.market_cap", "latest_financial.total_equity"],
        fallback_chain=["total_mv / total_equity"],
        conservative_proxies=["Conservative estimate"],
        minimum_input_groups=[["pb_mrq"], ["total_mv|market_cap", "total_equity"]],
        minimum_computable_conditions=[COND_TOTAL_EQUITY_NON_ZERO],
        warning_conditions=[WARN_PB_MRQ_ESTIMATED_FROM_MARKET_CAP_AND_EQUITY],
        warning_categories=["proxy_used"],
    ),
    "ps_ttm": RuntimeSemanticContract(direct_fields=["ps_ttm"], source_priority=["basic_info.ps_ttm", "basic_info.ps"], fallback_chain=["ps"], minimum_input_groups=[["ps_ttm"], ["ps"]], warning_conditions=[WARN_PS_TTM_FALLBACK_TO_PS], warning_categories=["fallback_used"]),
    "dividend_yield": RuntimeSemanticContract(
        direct_fields=["dividend_yield|financial_indicators.dividend_yield"],
        source_priority=["basic_info.dividend_yield", "latest_financial.financial_indicators.dividend_yield", "latest_financial.dividend_yield"],
        fallback_chain=[
            "basic_info.dividend_yield",
            "financial_indicators.dividend_yield",
            "period top layer dividend_yield",
        ],
        minimum_input_groups=[["dividend_yield"], ["financial_indicators.dividend_yield"]],
        warning_conditions=[WARN_DIVIDEND_YIELD_FALLBACK_TO_FINANCIAL_FIELD],
        warning_categories=["fallback_used"],
    ),
    "peg": RuntimeSemanticContract(
        direct_fields=["pe_ttm|pe", "net_profit_yoy"],
        fallback_chain=["pe_ttm Fallback to when missing pe"],
        availability_constraints=["Net profit is positive year-on-year and not 0"],
        minimum_input_groups=[["pe_ttm", "net_profit_yoy"], ["pe", "net_profit_yoy"]],
        minimum_computable_conditions=[COND_NET_PROFIT_YOY_POSITIVE, COND_NET_PROFIT_YOY_NON_ZERO],
    ),
    "industry_pe_median": RuntimeSemanticContract(
        direct_fields=["industry", "pe_ttm|pe"],
        availability_constraints=["Industry sample number recommendations >= 5"],
        minimum_input_groups=[["industry", "pe_ttm"], ["industry", "pe"]],
        warning_conditions=[WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5],
        warning_categories=["low_sample_size"],
    ),
    "industry_pb_median": RuntimeSemanticContract(direct_fields=["industry", "pb|pb_mrq"], minimum_input_groups=[["industry", "pb"], ["industry", "pb_mrq"]], warning_conditions=[WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5], warning_categories=["low_sample_size"]),
    "roe": RuntimeSemanticContract(direct_fields=["roe"], minimum_input_groups=[["roe"]]),
    "roa": RuntimeSemanticContract(direct_fields=["roa"], minimum_input_groups=[["roa"]]),
    "gross_margin": RuntimeSemanticContract(direct_fields=["gross_margin"], minimum_input_groups=[["gross_margin"]]),
    "netprofit_margin": RuntimeSemanticContract(direct_fields=["netprofit_margin"], minimum_input_groups=[["netprofit_margin"]]),
    "debt_to_assets": RuntimeSemanticContract(direct_fields=["debt_to_assets"], minimum_input_groups=[["debt_to_assets"]]),
    "assets_to_eqt": RuntimeSemanticContract(direct_fields=["assets_to_eqt"], minimum_input_groups=[["assets_to_eqt"]]),
    "current_ratio": RuntimeSemanticContract(direct_fields=["current_ratio"], minimum_input_groups=[["current_ratio"]]),
    "quick_ratio": RuntimeSemanticContract(direct_fields=["quick_ratio"], minimum_input_groups=[["quick_ratio"]]),
    "cash_ratio": RuntimeSemanticContract(direct_fields=["cash_ratio"], minimum_input_groups=[["cash_ratio"]]),
    "net_working_capital": RuntimeSemanticContract(direct_fields=["total_cur_assets", "total_cur_liab"], period_selection_strategy="current_period_only", minimum_input_groups=[["total_cur_assets", "total_cur_liab"]]),
    "revenue_ttm": RuntimeSemanticContract(direct_fields=["revenue_ttm"], period_selection_strategy="current_period_only", minimum_input_groups=[["revenue_ttm"]]),
    "net_profit_ttm": RuntimeSemanticContract(
        direct_fields=["net_profit_ttm|net_profit|net_income"],
        source_priority=["latest_financial.net_profit_ttm", "latest_financial.net_profit", "latest_financial.net_income"],
        fallback_chain=["net_profit_ttm", "net_profit", "net_income"],
        minimum_input_groups=[["net_profit_ttm"], ["net_profit"], ["net_income"]],
        warning_conditions=[WARN_NET_PROFIT_TTM_FALLBACK_TO_NET_PROFIT_OR_NET_INCOME],
        warning_categories=["fallback_used"],
    ),
    "piotroski_f_score": RuntimeSemanticContract(direct_fields=["roa", "n_cashflow_act", "current_ratio", "gross_margin", "asset_turnover"], minimum_input_groups=[["latest_period", "comparison_period", "roa", "n_cashflow_act", "current_ratio", "gross_margin", "asset_turnover"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_ALL_REQUIRED_SIGNAL_INPUTS_AVAILABLE]),
    "altman_z_score": RuntimeSemanticContract(direct_fields=["total_assets", "total_liab", "total_cur_assets", "total_cur_liab", "ebit", "revenue"], minimum_input_groups=[["total_assets", "total_liab", "total_cur_assets", "total_cur_liab", "ebit", "revenue", "market_value_proxy", "undistr_porfit"]], minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO, COND_TOTAL_LIAB_NON_ZERO]),
    "beneish_m_score": RuntimeSemanticContract(direct_fields=["revenue", "accounts_receiv", "oper_cost", "total_assets", "total_cur_assets", "fix_assets", "n_cashflow_act"], minimum_input_groups=[["latest_period", "comparison_period", "revenue", "accounts_receiv", "oper_cost", "total_assets", "total_cur_assets", "fix_assets", "n_cashflow_act", "depreciation_current", "depreciation_previous"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_SALES_CURRENT_NON_ZERO, COND_SALES_PREVIOUS_NON_ZERO, COND_TOTAL_ASSETS_CURRENT_NON_ZERO, COND_TOTAL_ASSETS_PREVIOUS_NON_ZERO, COND_TOTAL_LIAB_PREVIOUS_NON_ZERO, COND_DEPRECIATION_PLUS_FIXED_ASSETS_CURRENT_NON_ZERO, COND_DEPRECIATION_PLUS_FIXED_ASSETS_PREVIOUS_NON_ZERO, COND_SGA_PREVIOUS_NON_ZERO, COND_GROSS_MARGIN_CURRENT_NON_ZERO, COND_ASSET_QUALITY_PREVIOUS_NON_ZERO]),
    "n_cashflow_act": RuntimeSemanticContract(direct_fields=["n_cashflow_act"], period_selection_strategy="current_period_only", minimum_input_groups=[["n_cashflow_act"]]),
    "revenue_yoy": RuntimeSemanticContract(direct_fields=["revenue|oper_rev", "Same quarter reporting period last year"], period_selection_strategy="same_period_last_year", minimum_input_groups=[["latest_period.revenue|oper_rev", "prior_same_period.revenue|oper_rev"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_PRIOR_PERIOD_METRIC_NON_ZERO]),
    "net_profit_yoy": RuntimeSemanticContract(direct_fields=["net_profit|net_income", "Same quarter reporting period last year"], period_selection_strategy="same_period_last_year", minimum_input_groups=[["latest_period.net_profit|net_income", "prior_same_period.net_profit|net_income"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_PRIOR_PERIOD_METRIC_NON_ZERO]),
    "oper_profit_yoy": RuntimeSemanticContract(direct_fields=["oper_profit|operating_profit|ebit", "Same quarter reporting period last year"], period_selection_strategy="same_period_last_year", minimum_input_groups=[["latest_period.oper_profit|operating_profit|ebit", "prior_same_period.oper_profit|operating_profit|ebit"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_PRIOR_PERIOD_METRIC_NON_ZERO]),
    "revenue_cagr_3y": RuntimeSemanticContract(direct_fields=["revenue_ttm|revenue|oper_rev", "Reporting period three years ago in the same quarter"], period_selection_strategy="same_period_n_years_3", minimum_input_groups=[["latest_period.revenue_ttm|revenue|oper_rev", "base_3y_period.revenue_ttm|revenue|oper_rev"]], minimum_computable_conditions=[COND_BASE_PERIOD_AVAILABLE, COND_CURRENT_VALUE_POSITIVE, COND_BASE_VALUE_POSITIVE]),
    "profit_cagr_3y": RuntimeSemanticContract(direct_fields=["net_profit_ttm|net_profit|net_income", "Reporting period three years ago in the same quarter"], period_selection_strategy="same_period_n_years_3", minimum_input_groups=[["latest_period.net_profit_ttm|net_profit|net_income", "base_3y_period.net_profit_ttm|net_profit|net_income"]], minimum_computable_conditions=[COND_BASE_PERIOD_AVAILABLE, COND_CURRENT_VALUE_POSITIVE, COND_BASE_VALUE_POSITIVE]),
    "roic": RuntimeSemanticContract(
        direct_fields=["ebit|oper_profit|operating_profit", "total_equity", "total_liab"],
        fallback_chain=["total_profit Estimate with net_profit", "25% Default tax rate", "money_cap If missing, treat it as 0"],
        conservative_proxies=["Average invested capital"],
        tax_estimation_strategy="profit_based_clamped_0_35_else_fixed_25",
        minimum_input_groups=[["ebit|oper_profit|operating_profit", "total_equity", "total_liab"]],
        minimum_computable_conditions=[COND_INVESTED_CAPITAL_POSITIVE],
        warning_conditions=[WARN_ROIC_MONEY_CAP_MISSING_AS_ZERO],
        warning_categories=["precision_degraded"],
    ),
    "cash_conversion": RuntimeSemanticContract(
        direct_fields=["n_cashflow_act", "net_profit|net_income"],
        availability_constraints=["If the net profit is missing or 0, a null value is returned."],
        minimum_input_groups=[["n_cashflow_act", "net_profit|net_income"]],
        minimum_computable_conditions=[COND_NET_PROFIT_NON_ZERO],
    ),
    "accrual_ratio": RuntimeSemanticContract(
        direct_fields=["net_profit|net_income", "n_cashflow_act", "total_assets"],
        denominator_guards=["Latest total assets as denominator"],
        unit_conversions=["Percentage"],
        minimum_input_groups=[["net_profit|net_income", "n_cashflow_act", "total_assets"]],
        minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO],
    ),
    "asset_turnover": RuntimeSemanticContract(
        direct_fields=["revenue_ttm|revenue|oper_rev", "total_assets"],
        denominator_guards=["Latest total assets as denominator", "Not average total assets"],
        minimum_input_groups=[["revenue_ttm|revenue|oper_rev", "total_assets"]],
        minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO],
    ),
    "gross_profit_to_assets": RuntimeSemanticContract(
        direct_fields=["revenue_ttm|revenue|oper_rev", "gross_margin", "total_assets"],
        denominator_guards=["Latest total assets as denominator"],
        unit_conversions=["Percentage"],
        minimum_input_groups=[["revenue_ttm|revenue|oper_rev", "gross_margin", "total_assets"]],
        minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO],
    ),
    "interest_coverage": RuntimeSemanticContract(
        direct_fields=["ebit|oper_profit|operating_profit", "fin_exp|raw_data.income_statement.int_exp"],
        fallback_chain=["ebit / fin_exp", "fin_exp <= 0", "int_exp", "fin_exp_int_exp"],
        availability_constraints=["Missing interest charges", "Incorrect", "raw_data"],
        minimum_input_groups=[["ebit|oper_profit|operating_profit", "fin_exp"], ["ebit|oper_profit|operating_profit", "raw_data.income_statement.int_exp|fin_exp_int_exp"]],
        minimum_computable_conditions=[COND_INTEREST_EXPENSE_POSITIVE],
        warning_conditions=[WARN_INTEREST_COVERAGE_FALLBACK_TO_RAW_INTEREST_EXPENSE],
        warning_categories=["fallback_used"],
    ),
    "inventory_turnover": RuntimeSemanticContract(
        direct_fields=["oper_cost|revenue_ttm|revenue|oper_rev", "inventories"],
        fallback_chain=["oper_cost When missing", "gross_margin"],
        denominator_guards=["Latest inventory balance", "Not the average inventory balance"],
        minimum_input_groups=[["oper_cost", "inventories"], ["revenue_ttm|revenue|oper_rev", "gross_margin", "inventories"]],
        minimum_computable_conditions=[COND_INVENTORIES_NON_ZERO],
        warning_conditions=[WARN_INVENTORY_TURNOVER_COST_PROXY_USED],
        warning_categories=["proxy_used"],
    ),
    "receivable_turnover": RuntimeSemanticContract(
        direct_fields=["revenue_ttm|revenue|oper_rev", "accounts_receiv"],
        denominator_guards=["Latest accounts receivable balance", "Not the average balance receivable"],
        minimum_input_groups=[["revenue_ttm|revenue|oper_rev", "accounts_receiv"]],
        minimum_computable_conditions=[COND_ACCOUNTS_RECEIV_NON_ZERO],
    ),
    "net_cash_position": RuntimeSemanticContract(
        direct_fields=["money_cap", "total_assets", "total_ncl|total_liab|total_cur_liab"],
        fallback_chain=["total_ncl", "total_liab - total_cur_liab"],
        conservative_proxies=["Conservative agent caliber percentage"],
        minimum_input_groups=[["money_cap", "total_ncl", "total_assets"], ["money_cap", "total_liab", "total_cur_liab", "total_assets"]],
        minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO],
        warning_conditions=[WARN_NET_CASH_POSITION_PROXY_TOTAL_NCL_USED],
        warning_categories=["proxy_used"],
    ),
    "fcf": RuntimeSemanticContract(
        direct_fields=["n_cashflow_act", "n_cashflow_inv_act"],
        conservative_proxies=["n_cashflow_act + n_cashflow_inv_act", "conservative agent"],
        minimum_input_groups=[["n_cashflow_act", "n_cashflow_inv_act"]],
        warning_conditions=[WARN_FCF_CONSERVATIVE_PROXY_USED],
        warning_categories=["proxy_used"],
    ),
    "fcf_yield": RuntimeSemanticContract(
        direct_fields=["fcf", "total_mv|market_cap"],
        source_priority=["market_quotes.total_mv", "basic_info.total_mv", "basic_info.market_cap"],
        unit_conversions=["Billion dollar caliber conversion", "yuan caliber"],
        minimum_input_groups=[["fcf", "total_mv|market_cap"]],
        minimum_computable_conditions=[COND_MARKET_CAP_NON_ZERO],
    ),
    "fcf_margin": RuntimeSemanticContract(
        direct_fields=["fcf", "revenue_ttm|revenue|oper_rev"],
        fallback_chain=["revenue_ttm", "revenue/oper_rev"],
        minimum_input_groups=[["fcf", "revenue_ttm"], ["fcf", "revenue"], ["fcf", "oper_rev"]],
        minimum_computable_conditions=[COND_REVENUE_BASE_NON_ZERO],
    ),
    "ocf_yield": RuntimeSemanticContract(
        direct_fields=["n_cashflow_act", "total_mv|market_cap"],
        source_priority=["market_quotes.total_mv", "basic_info.total_mv", "basic_info.market_cap"],
        unit_conversions=["Billion dollar caliber conversion"],
        minimum_input_groups=[["n_cashflow_act", "total_mv|market_cap"]],
        minimum_computable_conditions=[COND_MARKET_CAP_NON_ZERO],
    ),
    "working_capital_change": RuntimeSemanticContract(
        direct_fields=["The last two issues total_cur_assets", "The last two issues total_cur_liab"],
        availability_constraints=["The last two issues", "Current assets/current liabilities"],
        period_selection_strategy="previous_available_period",
        minimum_input_groups=[["latest_period.total_cur_assets", "latest_period.total_cur_liab", "previous_period.total_cur_assets", "previous_period.total_cur_liab"]],
        minimum_computable_conditions=[COND_PREVIOUS_PERIOD_AVAILABLE],
    ),
    "ma20": RuntimeSemanticContract(direct_fields=["close"], source_priority=["stock_technical_indicators.ma20", "stock_daily_quotes.close"], availability_constraints=["At least 20 trading days of historical market conditions"], minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "ma60": RuntimeSemanticContract(direct_fields=["close"], source_priority=["stock_daily_quotes.close"], availability_constraints=["At least 60 trading days of historical market conditions"], minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "rsi14": RuntimeSemanticContract(direct_fields=["close"], source_priority=["stock_technical_indicators.rsi14", "stock_daily_quotes.close"], availability_constraints=["At least 14 trading days of historical market conditions"], minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "kdj_k": RuntimeSemanticContract(direct_fields=["high", "low", "close"], source_priority=["stock_technical_indicators.kdj_k", "stock_daily_quotes.high|low|close"], availability_constraints=["At least 9 trading days of high and low closing sequences"], minimum_input_groups=[["high", "low", "close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "kdj_d": RuntimeSemanticContract(direct_fields=["high", "low", "close"], source_priority=["stock_technical_indicators.kdj_d", "stock_daily_quotes.high|low|close"], availability_constraints=["At least 9 trading days of high and low closing sequences"], minimum_input_groups=[["high", "low", "close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "kdj_j": RuntimeSemanticContract(direct_fields=["high", "low", "close"], source_priority=["stock_technical_indicators.kdj_j", "stock_daily_quotes.high|low|close"], availability_constraints=["At least 9 trading days of high and low closing sequences"], minimum_input_groups=[["high", "low", "close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "dif": RuntimeSemanticContract(direct_fields=["close"], source_priority=["stock_technical_indicators.dif", "stock_daily_quotes.close"], availability_constraints=["At least 26 trading days of historical market conditions"], minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "dea": RuntimeSemanticContract(direct_fields=["close"], source_priority=["stock_technical_indicators.dea", "stock_daily_quotes.close"], availability_constraints=["At least 26 trading days of historical market conditions"], minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
    "macd_hist": RuntimeSemanticContract(direct_fields=["close"], source_priority=["stock_technical_indicators.macd_hist", "stock_daily_quotes.close"], availability_constraints=["At least 26 trading days of historical market conditions"], minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE]),
}

FACTOR_RUNTIME_SEMANTIC_CONTRACTS = {
    name: contract if contract.source_priority else replace(contract, source_priority=list(P0_SOURCE_PRIORITY_BY_FIELD.get(name, [])))
    for name, contract in FACTOR_RUNTIME_SEMANTIC_CONTRACTS.items()
}


def get_factor_definition(factor_id: str) -> Optional[FactorDefinition]:
    """Query the factor definitions in the universal factor catalog by factor_id.

    Args:
        factor_id: factor identifier (e.g. "pe_ttm" / "roe") , Leading and trailing whitespace will be removed internally

    Returns:
        Optional[FactorDefinition]: Hit factor definition object; returned if not registered None
    """
    return COMMON_FACTOR_CATALOG.get(str(factor_id).strip())


def list_factor_definitions(category: Optional[FactorCategory] = None) -> List[Dict[str, object]]:
    """Lists factor definitions in the common factors catalog (sorted by category and factor_id).

    Args:
        category: Optional factor category filtering, default is None (no filtering)

    Returns:
        list[dict]: Factor definition dict list, element structure is given by FactorDefinition.to_dict() decide, press
            (category, factor_id) Sort in ascending order
    """
    items = list(COMMON_FACTOR_CATALOG.values())
    if category:
        items = [item for item in items if item.category == category]
    return [item.to_dict() for item in sorted(items, key=lambda item: (item.category, item.factor_id))]


def get_factor_pack(pack_id: str) -> List[Dict[str, object]]:
    """Get a list of factor definitions within a recommended factor pack by pack_id.

    Args:
        pack_id: factor package identifier (e.g. "value_core" / "quality_core" / "growth_cashflow_core" /
            "technical_core" / "liquidity_core") , Leading and trailing whitespace will be removed internally

    Returns:
        list[dict]: of all registered factors in this pack to_dict() Result list;
            If it is not configured or none of the factors are registered, an empty list will be returned.
    """
    factor_ids = RECOMMENDED_FACTOR_PACKS.get(str(pack_id).strip(), [])
    return [COMMON_FACTOR_CATALOG[factor_id].to_dict() for factor_id in factor_ids if factor_id in COMMON_FACTOR_CATALOG]


def infer_recommended_factor_packs(
    text: str = "",
    *,
    category: str = "",
    expected_fields: Optional[List[str]] = None,
) -> List[str]:
    """Infer a list of recommended factor packs based on natural language text, categories, or desired fields.

    Args:
        text: Natural language requirement description, default is ""
        category: Category keyword, default is ""
        expected_fields: List of expected factor field names, default is None

    Returns:
        list[str]: Recommended pack_id list, possible element values:
            "value_core" / "quality_core" / "growth_cashflow_core" /
            "technical_core" / "liquidity_core"; Remove duplicates in hit order
    """
    normalized = " ".join([
        str(text or "").lower(),
        str(category or "").lower(),
        " ".join(str(field).lower() for field in (expected_fields or []) if str(field).strip()),
    ])

    pack_ids: List[str] = []

    if any(keyword in normalized for keyword in ["Valuation", "valuation", "pe", "pb", "ps", "peg", "dividend yield", "peers", "peer"]):
        pack_ids.append("value_core")
    if any(keyword in normalized for keyword in ["peg", "Net profit growth", "profit growth", "earnings growth"]):
        pack_ids.append("growth_cashflow_core")
    if any(keyword in normalized for keyword in ["quality", "quality", "roe", "roa", "Gross profit margin", "net profit margin", "Debt ratio", "current ratio", "financial health"]):
        pack_ids.append("quality_core")
    if any(keyword in normalized for keyword in ["growth", "growth", "cash flow", "cashflow", "Revenue", "net profit", "fcf", "ttm", "Year-on-year", "cagr"]):
        pack_ids.append("growth_cashflow_core")
    if any(keyword in normalized for keyword in ["technology", "technical", "ma", "moving average", "rsi", "kdj", "macd", "momentum", "momentum"]):
        pack_ids.append("technical_core")
    if any(keyword in normalized for keyword in ["turnover rate", "Quantity ratio", "Increase or decrease", "Active trading", "Liquidity", "liquidity", "turnover", "volume_ratio", "pct_chg"]):
        pack_ids.append("liquidity_core")

    for field_name in expected_fields or []:
        normalized_field = str(field_name).strip()
        if not normalized_field:
            continue
        for pack_id, factor_ids in RECOMMENDED_FACTOR_PACKS.items():
            if normalized_field in factor_ids and pack_id not in pack_ids:
                pack_ids.append(pack_id)

    return list(dict.fromkeys(pack_ids))


def select_relevant_factor_definitions(
    text: str = "",
    *,
    category: str = "",
    expected_fields: Optional[List[str]] = None,
    max_items: int = 16,
) -> List[Dict[str, object]]:
    """Select relevant factor definitions based on requirement text/category/expect fields, returning at most max_items items.

    Args:
        text: Natural language requirement description, default is ""
        category: Category keyword, default is ""
        expected_fields: List of expected factor field names, default is None
        max_items: Maximum number of entries returned, default is 16

    Returns:
        list[dict]: selected factor to_dict() As a result, the element structure is given by FactorDefinition.to_dict() decide;
            Selection order: first expected_fields hits the field, then infer_recommended_factor_packs hits the field,
            Finally, press fallback category to save; the total number does not exceed max_items
    """
    selected_ids: List[str] = []

    for field_name in expected_fields or []:
        normalized_field = str(field_name).strip()
        if normalized_field in COMMON_FACTOR_CATALOG and normalized_field not in selected_ids:
            selected_ids.append(normalized_field)

    for pack_id in infer_recommended_factor_packs(text, category=category, expected_fields=expected_fields):
        for factor_id in RECOMMENDED_FACTOR_PACKS.get(pack_id, []):
            if factor_id in COMMON_FACTOR_CATALOG and factor_id not in selected_ids:
                selected_ids.append(factor_id)

    if not selected_ids:
        normalized = f"{text} {category}".lower()
        fallback_categories: List[str] = []
        if any(keyword in normalized for keyword in ["Valuation", "valuation", "pe", "pb", "peg", "ps"]):
            fallback_categories.append("valuation")
        if any(keyword in normalized for keyword in ["quality", "quality", "roe", "roa", "Gross profit margin", "net profit margin"]):
            fallback_categories.append("quality")
        if any(keyword in normalized for keyword in ["technology", "technical", "rsi", "macd", "kdj", "ma"]):
            fallback_categories.append("technical")
        if any(keyword in normalized for keyword in ["growth", "growth", "cash flow", "cashflow", "Year-on-year", "fcf"]):
            fallback_categories.extend(["growth", "cashflow"])
        if any(keyword in normalized for keyword in ["turnover rate", "Quantity ratio", "Increase or decrease", "liquidity", "turnover"]):
            fallback_categories.append("trading")

        for item in list_factor_definitions():
            factor_id = str(item.get("factor_id") or "").strip()
            factor_category = str(item.get("category") or "").strip()
            if factor_id and factor_category in fallback_categories and factor_id not in selected_ids:
                selected_ids.append(factor_id)

    return [COMMON_FACTOR_CATALOG[factor_id].to_dict() for factor_id in selected_ids[:max_items] if factor_id in COMMON_FACTOR_CATALOG]


def build_factor_catalog_prompt_context(
    text: str = "",
    *,
    category: str = "",
    expected_fields: Optional[List[str]] = None,
    max_items: int = 16,
) -> str:
    """Constructs factor catalog context text for skill generation prompts.

    Args:
        text: Natural language requirement description, default is ""
        category: Category keyword, default is ""
        expected_fields: List of expected factor field names, default is None
        max_items: Select the factor upper limit, the default is 16

    Returns:
        str: Multi-line prompt text; contains recommended pack, helper/bundle prompts, available factor list, and generation constraints;
            If no factors are hit and there is no pack, an empty string is returned ""
    """
    factor_items = select_relevant_factor_definitions(
        text,
        category=category,
        expected_fields=expected_fields,
        max_items=max_items,
    )
    pack_ids = infer_recommended_factor_packs(
        text,
        category=category,
        expected_fields=expected_fields,
    )

    if not factor_items and not pack_ids:
        return ""

    lines: List[str] = [
        "Common analysis factor whitelist for current demand hits:",
        "- These factors have been registered in the runtime catalog and should be reused first when generating Skills. Do not create your own synonymous fields or create a new set of calibers.",
    ]
    if pack_ids:
        lines.append(f"- Recommended factor packs: {', '.join(pack_ids)}")

    helper_hints: List[str] = []
    if "value_core" in pack_ids:
        helper_hints.extend(["get_stock_valuation_context", "get_value_factor_bundle", "summarize_industry_valuation"])
    if "quality_core" in pack_ids:
        helper_hints.extend(["get_quality_factor_bundle", "get_fundamental_factor_snapshot"])
    if "growth_cashflow_core" in pack_ids:
        helper_hints.extend(["get_growth_cashflow_factor_bundle", "get_fundamental_factor_snapshot"])
    if "technical_core" in pack_ids:
        helper_hints.extend(["get_stock_daily_quotes", "compute_many"])
    if helper_hints:
        lines.append(f"- Priority helper/bundle: {', '.join(list(dict.fromkeys(helper_hints)))}")

    lines.append("- Available factors: ")
    for item in factor_items:
        factor_id = str(item.get("factor_id") or "").strip()
        display_name = str(item.get("display_name") or factor_id).strip()
        implementation_level = str(item.get("implementation_level") or "").strip()
        helpers = ", ".join(item.get("helper_functions") or [])
        formula = str(item.get("formula") or "").strip()
        description = str(item.get("description") or "").strip()
        line = f"  - {factor_id} ({display_name}) | level={implementation_level}"
        if helpers:
            line += f" | helpers={helpers}"
        if formula:
            line += f" | formula={formula}"
        elif description:
            line += f" | {description}"
        lines.append(line)

    lines.extend([
        "- If the requirement is only the reading, combination or fixed formula calculation of these whitelist factors, it is priority to implement it as a deterministic skill instead of inventing new underlying factors.",
        "- If expected_output.fields involves factor fields, the factor_id already in the catalog is preferred as the output field name.",
    ])
    return "\n".join(lines)


def build_factor_implementation_outline(factor_ids: List[str]) -> Dict[str, object]:
    """Build an implementation profile summary based on a set of factor_ids.

    Args:
        factor_ids: List of factor identifiers; those not registered in COMMON_FACTOR_CATALOG will be ignored

    Returns:
        dict: Field description——
            factor_ids: list[str], Hit and expanded factor_id list
            collections: list[str], Name of the data set involved (in ascending order with deduplication)
            helpers: list[str], Involved helper function names (in ascending order without duplicates)
            implementation_levels: list[str], Implementation levels involved (ascending order with deduplication)
            warnings: list[str], Alarm text for all factors (retaining repeat order)
    """
    selected: List[FactorDefinition] = []
    for factor_id in factor_ids:
        factor = get_factor_definition(factor_id)
        if factor:
            selected.append(factor)

    return {
        "factor_ids": [factor.factor_id for factor in selected],
        "collections": sorted({source for factor in selected for source in factor.primary_sources}),
        "helpers": sorted({helper for factor in selected for helper in factor.helper_functions}),
        "implementation_levels": sorted({factor.implementation_level for factor in selected}),
        "warnings": [warning for factor in selected for warning in factor.warnings],
    }


def validate_factor_catalog_schema_alignment() -> Dict[str, List[Dict[str, str]]]:
    """Verify the consistency of P0 factor schema and COMMON_FACTOR_CATALOG.

    Returns:
        dict: Field description——
            mismatches: list[dict], schema with catalog data_quality_tier / implementation_level
                Inconsistent entries, per element field:
                — field: Field name
                — catalog_implementation_level: catalog registered in implementation_level
                — schema_data_quality_tier: schema registered in data_quality_tier
            missing_catalog_entries: list[dict], schema Fields that are registered but not registered in catalog
                — field: Field name
                — reason: Missing explanation
            missing_cautious_catalog_entries: list[dict], schema Fields marked as cautious but not registered in catalog
                — field: Field name
                — expected_implementation_level: Expectation Level ("cautious") 
                — reason: Missing explanation
    """
    mismatches: List[Dict[str, str]] = []
    missing_catalog_entries: List[Dict[str, str]] = []
    missing_cautious_catalog_entries: List[Dict[str, str]] = []

    for field_name, schema in P0_FACTOR_FIELD_SCHEMA.items():
        catalog_entry = COMMON_FACTOR_CATALOG.get(field_name)
        if catalog_entry is None:
            missing_catalog_entries.append(
                {
                    "field": field_name,
                    "reason": "schema The field has been registered, but factor_catalog has not.",
                }
            )
            if schema.data_quality_tier == "cautious":
                missing_cautious_catalog_entries.append(
                    {
                        "field": field_name,
                        "expected_implementation_level": "cautious",
                        "reason": "schema Marked as cautious, but factor_catalog has not yet registered this field.",
                    }
                )
            continue

        expected_tier = "cautious" if catalog_entry.implementation_level == "cautious" else "standard"
        if expected_tier != schema.data_quality_tier:
            mismatches.append(
                {
                    "field": field_name,
                    "catalog_implementation_level": catalog_entry.implementation_level,
                    "schema_data_quality_tier": schema.data_quality_tier,
                }
            )

    return {
        "mismatches": mismatches,
        "missing_catalog_entries": missing_catalog_entries,
        "missing_cautious_catalog_entries": missing_cautious_catalog_entries,
    }


def validate_technical_factor_catalog_schema_alignment() -> Dict[str, List[Dict[str, str]]]:
    """Verify the consistency of the technical factor schema with COMMON_FACTOR_CATALOG.

    Returns:
        dict: Field description——
            mismatches: list[dict], catalog Categories inconsistent with expected technical entries, per element field:
                — field: Field name
                — catalog_category: catalog Category registered in
                — expected_category: Expected Category ("technical") 
            missing_catalog_entries: list[dict], technical schema Fields that are registered but not registered in catalog
                — field: Field name
                — reason: Missing explanation
    """
    mismatches: List[Dict[str, str]] = []
    missing_catalog_entries: List[Dict[str, str]] = []

    for field_name in TECHNICAL_FACTOR_FIELD_SCHEMA.keys():
        catalog_entry = COMMON_FACTOR_CATALOG.get(field_name)
        if catalog_entry is None:
            missing_catalog_entries.append(
                {
                    "field": field_name,
                    "reason": "technical schema The field has been registered, but factor_catalog has not.",
                }
            )
            continue

        if catalog_entry.category != "technical":
            mismatches.append(
                {
                    "field": field_name,
                    "catalog_category": catalog_entry.category,
                    "expected_category": "technical",
                }
            )

    return {
        "mismatches": mismatches,
        "missing_catalog_entries": missing_catalog_entries,
    }


def validate_factor_pack_schema_alignment() -> Dict[str, List[Dict[str, object]]]:
    """Verify that RECOMMENDED_FACTOR_PACKS is aligned with the schema bundle field set.

    Returns:
        dict: Field description——
            mismatches: list[dict], pack The fieldset is inconsistent with the schema bundle entry, per element field:
                — pack_id: pack logo("value_core" / "quality_core" /
                    "growth_cashflow_core" / "growth_core"）
                — expected_fields: list[str], List of expected field names
                — actual_fields: list[str], List of actual registered field names
                — missing_fields: list[str], Missing field name
                — extra_fields: list[str], redundant field name
    """
    mismatches: List[Dict[str, object]] = []
    expected_packs = {
        "value_core": list_bundle_fields("value_core"),
        "quality_core": list_bundle_fields("quality_core"),
        "growth_cashflow_core": list_bundle_fields("growth_cashflow_core"),
        "growth_core": list_bundle_fields("growth_cashflow_core"),
    }

    for pack_id, expected_fields in expected_packs.items():
        actual_fields = RECOMMENDED_FACTOR_PACKS.get(pack_id, [])
        if actual_fields != expected_fields:
            mismatches.append(
                {
                    "pack_id": pack_id,
                    "expected_fields": expected_fields,
                    "actual_fields": actual_fields,
                    "missing_fields": [field for field in expected_fields if field not in actual_fields],
                    "extra_fields": [field for field in actual_fields if field not in expected_fields],
                }
            )

    return {"mismatches": mismatches}


def validate_factor_catalog_source_alignment() -> Dict[str, List[Dict[str, object]]]:
    """Verify that the legacy data source (stock_financial_data / get_stock_financial_data) is still referenced in the catalog.

    Returns:
        dict: Field description——
            legacy_source_refs: list[dict], Still referencing the field entries of the legacy data source, per element field:
                — field: Field name
                — legacy_sources: list[str], Hit legacy data source name ("stock_financial_data") 
                — legacy_helpers: list[str], hit legacy helper name ("get_stock_financial_data") 
    """
    legacy_source_refs: List[Dict[str, object]] = []

    for field_name in P0_FACTOR_FIELD_SCHEMA.keys():
        catalog_entry = COMMON_FACTOR_CATALOG.get(field_name)
        if catalog_entry is None:
            continue

        legacy_sources = [
            source for source in catalog_entry.primary_sources if source == "stock_financial_data"
        ]
        legacy_helpers = [
            helper for helper in catalog_entry.helper_functions if helper == "get_stock_financial_data"
        ]
        if legacy_sources or legacy_helpers:
            legacy_source_refs.append(
                {
                    "field": field_name,
                    "legacy_sources": legacy_sources,
                    "legacy_helpers": legacy_helpers,
                }
            )

    return {"legacy_source_refs": legacy_source_refs}


def validate_factor_catalog_runtime_semantic_alignment() -> Dict[str, List[Dict[str, object]]]:
    """Verify the consistency of the P0 schema field with the runtime semantic contract / catalog.

    Returns:
        dict: Field description——
            missing_contract_entries: list[dict], schema Registered but runtime semantic contract
                Unregistered fields, element fields:
                — field: Field name
                — reason: Missing explanation
            mismatches: list[dict], contract Text fragment missing entry in catalog, element field:
                — field: Field name
                — missing_direct_fields: list[str], catalog.required_fields Missing contract.direct_fields fragment in
                — missing_fallback_chain: list[str], catalog.fallback_rules Missing contract.fallback_chain fragment in
                — missing_denominator_guards: list[str], catalog.warnings Missing contract.denominator_guards fragment in
                — missing_unit_conversions: list[str], catalog.warnings Missing contract.unit_conversions fragment in
                — missing_conservative_proxies: list[str], catalog.warnings Missing contract.conservative_proxies fragment in
                — missing_availability_constraints: list[str], catalog.warnings Missing contract.availability_constraints fragment in
    """
    missing_contract_entries: List[Dict[str, object]] = []
    mismatches: List[Dict[str, object]] = []

    for field_name in P0_FACTOR_FIELD_SCHEMA.keys():
        if field_name not in FACTOR_RUNTIME_SEMANTIC_CONTRACTS:
            missing_contract_entries.append(
                {
                    "field": field_name,
                    "reason": "schema The field has been registered, but the runtime semantic contract has not.",
                }
            )

    for field_name in P0_FACTOR_FIELD_SCHEMA.keys():
        contract = FACTOR_RUNTIME_SEMANTIC_CONTRACTS.get(field_name)
        if contract is None:
            continue
        catalog_entry = COMMON_FACTOR_CATALOG.get(field_name)
        if catalog_entry is None:
            mismatches.append(
                {
                    "field": field_name,
                    "missing_entry": True,
                }
            )
            continue

        missing_direct_fields = _missing_text_fragments(catalog_entry.required_fields, contract.direct_fields)
        missing_fallback_chain = _missing_text_fragments(catalog_entry.fallback_rules, contract.fallback_chain)
        missing_denominator_guards = _missing_text_fragments(catalog_entry.warnings, contract.denominator_guards)
        missing_unit_conversions = _missing_text_fragments(catalog_entry.warnings, contract.unit_conversions)
        missing_conservative_proxies = _missing_text_fragments(catalog_entry.warnings, contract.conservative_proxies)
        missing_availability_constraints = _missing_text_fragments(catalog_entry.warnings, contract.availability_constraints)

        if (
            missing_direct_fields
            or missing_fallback_chain
            or missing_denominator_guards
            or missing_unit_conversions
            or missing_conservative_proxies
            or missing_availability_constraints
        ):
            mismatches.append(
                {
                    "field": field_name,
                    "missing_direct_fields": missing_direct_fields,
                    "missing_fallback_chain": missing_fallback_chain,
                    "missing_denominator_guards": missing_denominator_guards,
                    "missing_unit_conversions": missing_unit_conversions,
                    "missing_conservative_proxies": missing_conservative_proxies,
                    "missing_availability_constraints": missing_availability_constraints,
                }
            )

    return {
        "missing_contract_entries": missing_contract_entries,
        "mismatches": mismatches,
    }


def validate_technical_factor_catalog_runtime_semantic_alignment() -> Dict[str, List[Dict[str, object]]]:
    """Verify the consistency of the technical factor schema field with the runtime semantic contract / catalog.

    Returns:
        dict: Field description——
            missing_contract_entries: list[dict], technical schema Registered but contract unregistered fields, element fields:
                — field: Field name
                — reason: Missing explanation
            mismatches: list[dict], contract Text fragment missing entry in catalog, element field:
                — field: Field name
                — missing_direct_fields: list[str], catalog.required_fields Missing contract.direct_fields fragment in
                — missing_availability_constraints: list[str], catalog.warnings Missing contract.availability_constraints fragment in
    """
    missing_contract_entries: List[Dict[str, object]] = []
    mismatches: List[Dict[str, object]] = []

    for field_name in TECHNICAL_FACTOR_FIELD_SCHEMA.keys():
        if field_name not in FACTOR_RUNTIME_SEMANTIC_CONTRACTS:
            missing_contract_entries.append(
                {
                    "field": field_name,
                    "reason": "technical schema The field has been registered, but the runtime semantic contract has not.",
                }
            )

    for field_name in TECHNICAL_FACTOR_FIELD_SCHEMA.keys():
        contract = FACTOR_RUNTIME_SEMANTIC_CONTRACTS.get(field_name)
        catalog_entry = COMMON_FACTOR_CATALOG.get(field_name)
        if contract is None or catalog_entry is None:
            continue

        missing_direct_fields = _missing_text_fragments(catalog_entry.required_fields, contract.direct_fields)
        missing_availability_constraints = _missing_text_fragments(catalog_entry.warnings, contract.availability_constraints)
        if missing_direct_fields or missing_availability_constraints:
            mismatches.append(
                {
                    "field": field_name,
                    "missing_direct_fields": missing_direct_fields,
                    "missing_availability_constraints": missing_availability_constraints,
                }
            )

    return {
        "missing_contract_entries": missing_contract_entries,
        "mismatches": mismatches,
    }


def validate_factor_schema_semantic_alignment() -> Dict[str, List[Dict[str, object]]]:
    """Verify P0 factor schema and runtime semantic contract in source_priority /
    minimum_input_groups / minimum_computable_conditions / warning Equal-dimensional consistency.

    Returns:
        dict: Field description——
            missing_schema_fields: list[dict], contract Fields registered but not registered in schema, element fields:
                — field: Field name
                — reason: Missing explanation
            missing_source_priority_entries: list[dict], Missing fields on either side of source_priority, element fields:
                — field: Field name
                — schema_source_priority: list[str]
                — contract_source_priority: list[str]
            missing_minimum_input_group_entries: list[dict], Missing fields on either side of minimum_input_groups, element fields:
                — field: Field name
                — schema_minimum_input_groups: list[list[str]]
                — contract_minimum_input_groups: list[list[str]]
            missing_minimum_computable_condition_entries: list[dict], Fields that require a computable condition but are missing on either side, element fields:
                — field: Field name
                — schema_minimum_computable_conditions: list[str]
                — contract_minimum_computable_conditions: list[str]
            missing_warning_condition_entries: list[dict], Fields that require a warning condition but are missing on either side, element fields:
                — field: Field name
                — schema_warning_conditions: list[str]
                — contract_warning_conditions: list[str]
            missing_warning_category_entries: list[dict], Fields that require the warning category but are missing on either side, element fields:
                — field: Field name
                — schema_warning_categories: list[str]
                — contract_warning_categories: list[str]
            mismatches: list[dict], schema Items inconsistent with contract dimensions, element fields:
                — field: Field name
                — missing_semantic_tags: list[str], missing semantic tags
                — schema_source_priority / contract_source_priority: list[str]
                — source_priority_mismatch: bool
                — schema_tax_estimation_strategy / contract_tax_estimation_strategy: str
                — tax_estimation_strategy_mismatch: bool
                — schema_period_selection_strategy / contract_period_selection_strategy: str
                — period_selection_strategy_mismatch: bool
                — schema_minimum_input_groups / contract_minimum_input_groups: list[list[str]]
                — minimum_input_groups_mismatch: bool
                — schema_minimum_computable_conditions / contract_minimum_computable_conditions: list[str]
                — minimum_computable_conditions_mismatch: bool
                — schema_warning_conditions / contract_warning_conditions: list[str]
                — warning_conditions_mismatch: bool
                — schema_warning_categories / contract_warning_categories: list[str]
                — warning_categories_mismatch: bool
                — schema_calculation_mode: str
                — requires_non_direct_mode: bool, Whether to require non-direct computing mode
    """
    missing_schema_fields: List[Dict[str, object]] = []
    missing_source_priority_entries: List[Dict[str, object]] = []
    missing_minimum_input_group_entries: List[Dict[str, object]] = []
    missing_minimum_computable_condition_entries: List[Dict[str, object]] = []
    missing_warning_condition_entries: List[Dict[str, object]] = []
    missing_warning_category_entries: List[Dict[str, object]] = []
    mismatches: List[Dict[str, object]] = []

    for field_name in P0_FACTOR_FIELD_SCHEMA.keys():
        contract = FACTOR_RUNTIME_SEMANTIC_CONTRACTS.get(field_name)
        if contract is None:
            continue
        schema = P0_FACTOR_FIELD_SCHEMA.get(field_name)
        if schema is None:
            missing_schema_fields.append(
                {
                    "field": field_name,
                    "reason": "runtime semantic contract Registered, but factor_schema does not yet have this field.",
                }
            )
            continue

        if not schema.source_priority or not contract.source_priority:
            missing_source_priority_entries.append(
                {
                    "field": field_name,
                    "schema_source_priority": list(schema.source_priority or []),
                    "contract_source_priority": list(contract.source_priority or []),
                }
            )

        if not schema.minimum_input_groups or not contract.minimum_input_groups:
            missing_minimum_input_group_entries.append(
                {
                    "field": field_name,
                    "schema_minimum_input_groups": list(schema.minimum_input_groups or []),
                    "contract_minimum_input_groups": list(contract.minimum_input_groups or []),
                }
            )

        requires_minimum_computable_conditions = any(
            [
                schema.data_quality_tier == "cautious",
                schema.period_selection_strategy in {"same_period_last_year", "same_period_n_years_3", "previous_available_period"},
                bool(contract.denominator_guards),
            ]
        )
        if requires_minimum_computable_conditions and (
            not schema.minimum_computable_conditions or not contract.minimum_computable_conditions
        ):
            missing_minimum_computable_condition_entries.append(
                {
                    "field": field_name,
                    "schema_minimum_computable_conditions": list(schema.minimum_computable_conditions or []),
                    "contract_minimum_computable_conditions": list(contract.minimum_computable_conditions or []),
                }
            )

        requires_warning_conditions = any(
            [
                schema.calculation_mode == "fallback",
                bool(contract.conservative_proxies),
                bool(contract.warning_conditions),
            ]
        )
        if requires_warning_conditions and (not schema.warning_conditions or not contract.warning_conditions):
            missing_warning_condition_entries.append(
                {
                    "field": field_name,
                    "schema_warning_conditions": list(schema.warning_conditions or []),
                    "contract_warning_conditions": list(contract.warning_conditions or []),
                }
            )

        if requires_warning_conditions and (not schema.warning_categories or not contract.warning_categories):
            missing_warning_category_entries.append(
                {
                    "field": field_name,
                    "schema_warning_categories": list(schema.warning_categories or []),
                    "contract_warning_categories": list(contract.warning_categories or []),
                }
            )

        schema_tags = set(schema.semantic_tags or [])
        missing_tags: List[str] = []
        for contract_attr, schema_tag in SCHEMA_TAG_BY_CONTRACT_CATEGORY.items():
            if getattr(contract, contract_attr) and schema_tag not in schema_tags:
                missing_tags.append(schema_tag)

        source_priority_mismatch = list(schema.source_priority or []) != list(contract.source_priority or [])
        tax_estimation_strategy_mismatch = schema.tax_estimation_strategy != contract.tax_estimation_strategy
        period_selection_strategy_mismatch = schema.period_selection_strategy != contract.period_selection_strategy
        minimum_input_groups_mismatch = list(schema.minimum_input_groups or []) != list(contract.minimum_input_groups or [])
        minimum_computable_conditions_mismatch = list(schema.minimum_computable_conditions or []) != list(contract.minimum_computable_conditions or [])
        warning_conditions_mismatch = list(schema.warning_conditions or []) != list(contract.warning_conditions or [])
        warning_categories_mismatch = list(schema.warning_categories or []) != list(contract.warning_categories or [])

        expected_direct_mode = any(
            [
                contract.fallback_chain,
                contract.denominator_guards,
                contract.unit_conversions,
                contract.conservative_proxies,
                contract.availability_constraints,
            ]
        )
        calculation_mode_mismatch = expected_direct_mode and schema.calculation_mode == "direct"

        if missing_tags or calculation_mode_mismatch or tax_estimation_strategy_mismatch or period_selection_strategy_mismatch or minimum_input_groups_mismatch or minimum_computable_conditions_mismatch or warning_conditions_mismatch or warning_categories_mismatch:
            mismatches.append(
                {
                    "field": field_name,
                    "missing_semantic_tags": missing_tags,
                    "schema_source_priority": list(schema.source_priority or []),
                    "contract_source_priority": list(contract.source_priority or []),
                    "source_priority_mismatch": source_priority_mismatch,
                    "schema_tax_estimation_strategy": schema.tax_estimation_strategy,
                    "contract_tax_estimation_strategy": contract.tax_estimation_strategy,
                    "tax_estimation_strategy_mismatch": tax_estimation_strategy_mismatch,
                    "schema_period_selection_strategy": schema.period_selection_strategy,
                    "contract_period_selection_strategy": contract.period_selection_strategy,
                    "period_selection_strategy_mismatch": period_selection_strategy_mismatch,
                    "schema_minimum_input_groups": list(schema.minimum_input_groups or []),
                    "contract_minimum_input_groups": list(contract.minimum_input_groups or []),
                    "minimum_input_groups_mismatch": minimum_input_groups_mismatch,
                    "schema_minimum_computable_conditions": list(schema.minimum_computable_conditions or []),
                    "contract_minimum_computable_conditions": list(contract.minimum_computable_conditions or []),
                    "minimum_computable_conditions_mismatch": minimum_computable_conditions_mismatch,
                    "schema_warning_conditions": list(schema.warning_conditions or []),
                    "contract_warning_conditions": list(contract.warning_conditions or []),
                    "warning_conditions_mismatch": warning_conditions_mismatch,
                    "schema_warning_categories": list(schema.warning_categories or []),
                    "contract_warning_categories": list(contract.warning_categories or []),
                    "warning_categories_mismatch": warning_categories_mismatch,
                    "schema_calculation_mode": schema.calculation_mode,
                    "requires_non_direct_mode": calculation_mode_mismatch,
                }
            )

        elif source_priority_mismatch:
            mismatches.append(
                {
                    "field": field_name,
                    "missing_semantic_tags": [],
                    "schema_source_priority": list(schema.source_priority or []),
                    "contract_source_priority": list(contract.source_priority or []),
                    "source_priority_mismatch": True,
                    "schema_tax_estimation_strategy": schema.tax_estimation_strategy,
                    "contract_tax_estimation_strategy": contract.tax_estimation_strategy,
                    "tax_estimation_strategy_mismatch": False,
                    "schema_period_selection_strategy": schema.period_selection_strategy,
                    "contract_period_selection_strategy": contract.period_selection_strategy,
                    "period_selection_strategy_mismatch": False,
                    "schema_minimum_input_groups": list(schema.minimum_input_groups or []),
                    "contract_minimum_input_groups": list(contract.minimum_input_groups or []),
                    "minimum_input_groups_mismatch": False,
                    "schema_minimum_computable_conditions": list(schema.minimum_computable_conditions or []),
                    "contract_minimum_computable_conditions": list(contract.minimum_computable_conditions or []),
                    "minimum_computable_conditions_mismatch": False,
                    "schema_warning_conditions": list(schema.warning_conditions or []),
                    "contract_warning_conditions": list(contract.warning_conditions or []),
                    "warning_conditions_mismatch": False,
                    "schema_warning_categories": list(schema.warning_categories or []),
                    "contract_warning_categories": list(contract.warning_categories or []),
                    "warning_categories_mismatch": False,
                    "schema_calculation_mode": schema.calculation_mode,
                    "requires_non_direct_mode": False,
                }
            )

    return {
        "missing_schema_fields": missing_schema_fields,
        "missing_source_priority_entries": missing_source_priority_entries,
        "missing_minimum_input_group_entries": missing_minimum_input_group_entries,
        "missing_minimum_computable_condition_entries": missing_minimum_computable_condition_entries,
        "missing_warning_condition_entries": missing_warning_condition_entries,
        "missing_warning_category_entries": missing_warning_category_entries,
        "mismatches": mismatches,
    }


def validate_technical_factor_schema_semantic_alignment() -> Dict[str, List[Dict[str, object]]]:
    """Check technology factor schema and runtime semantic contract in source_priority /
    minimum_input_groups / minimum_computable_conditions Dimensional consistency.

    Returns:
        dict: Field description——
            missing_schema_fields: list[dict], technical schema The field is not registered with the entry of contract, element field:
                — field: Field name
                — reason: Missing explanation
            missing_source_priority_entries: list[dict], Missing fields on either side of source_priority, element fields:
                — field: Field name
                — schema_source_priority: list[str]
                — contract_source_priority: list[str]
            missing_minimum_input_group_entries: list[dict], Missing fields on either side of minimum_input_groups, element fields:
                — field: Field name
                — schema_minimum_input_groups: list[list[str]]
                — contract_minimum_input_groups: list[list[str]]
            missing_minimum_computable_condition_entries: list[dict], Missing fields on either side of minimum_computable_conditions, element fields:
                — field: Field name
                — schema_minimum_computable_conditions: list[str]
                — contract_minimum_computable_conditions: list[str]
            mismatches: list[dict], schema Inconsistent entry with contract, element field:
                — field: Field name
                — schema_source_priority: list[str]
                — contract_source_priority: list[str]
                — schema_minimum_input_groups: list[list[str]]
                — contract_minimum_input_groups: list[list[str]]
                — schema_minimum_computable_conditions: list[str]
                — contract_minimum_computable_conditions: list[str]
    """
    missing_schema_fields: List[Dict[str, object]] = []
    missing_source_priority_entries: List[Dict[str, object]] = []
    missing_minimum_input_group_entries: List[Dict[str, object]] = []
    missing_minimum_computable_condition_entries: List[Dict[str, object]] = []
    mismatches: List[Dict[str, object]] = []

    for field_name, schema in TECHNICAL_FACTOR_FIELD_SCHEMA.items():
        contract = FACTOR_RUNTIME_SEMANTIC_CONTRACTS.get(field_name)
        if contract is None:
            missing_schema_fields.append(
                {
                    "field": field_name,
                    "reason": "technical runtime semantic contract Not registered yet.",
                }
            )
            continue

        if not schema.source_priority or not contract.source_priority:
            missing_source_priority_entries.append(
                {
                    "field": field_name,
                    "schema_source_priority": list(schema.source_priority or []),
                    "contract_source_priority": list(contract.source_priority or []),
                }
            )

        if not schema.minimum_input_groups or not contract.minimum_input_groups:
            missing_minimum_input_group_entries.append(
                {
                    "field": field_name,
                    "schema_minimum_input_groups": list(schema.minimum_input_groups or []),
                    "contract_minimum_input_groups": list(contract.minimum_input_groups or []),
                }
            )

        if not schema.minimum_computable_conditions or not contract.minimum_computable_conditions:
            missing_minimum_computable_condition_entries.append(
                {
                    "field": field_name,
                    "schema_minimum_computable_conditions": list(schema.minimum_computable_conditions or []),
                    "contract_minimum_computable_conditions": list(contract.minimum_computable_conditions or []),
                }
            )

        if (
            list(schema.source_priority or []) != list(contract.source_priority or [])
            or list(schema.minimum_input_groups or []) != list(contract.minimum_input_groups or [])
            or list(schema.minimum_computable_conditions or []) != list(contract.minimum_computable_conditions or [])
        ):
            mismatches.append(
                {
                    "field": field_name,
                    "schema_source_priority": list(schema.source_priority or []),
                    "contract_source_priority": list(contract.source_priority or []),
                    "schema_minimum_input_groups": list(schema.minimum_input_groups or []),
                    "contract_minimum_input_groups": list(contract.minimum_input_groups or []),
                    "schema_minimum_computable_conditions": list(schema.minimum_computable_conditions or []),
                    "contract_minimum_computable_conditions": list(contract.minimum_computable_conditions or []),
                }
            )

    return {
        "missing_schema_fields": missing_schema_fields,
        "missing_source_priority_entries": missing_source_priority_entries,
        "missing_minimum_input_group_entries": missing_minimum_input_group_entries,
        "missing_minimum_computable_condition_entries": missing_minimum_computable_condition_entries,
        "mismatches": mismatches,
    }


__all__ = [
    "COMMON_FACTOR_CATALOG",
    "FACTOR_RUNTIME_SEMANTIC_CONTRACTS",
    "P0_BUNDLE_FACTOR_PACKS",
    "RECOMMENDED_FACTOR_PACKS",
    "FactorDefinition",
    "RuntimeSemanticContract",
    "build_factor_implementation_outline",
    "validate_factor_catalog_schema_alignment",
    "validate_factor_catalog_runtime_semantic_alignment",
    "validate_technical_factor_catalog_schema_alignment",
    "validate_technical_factor_catalog_runtime_semantic_alignment",
    "validate_factor_schema_semantic_alignment",
    "validate_technical_factor_schema_semantic_alignment",
    "validate_factor_catalog_source_alignment",
    "validate_factor_pack_schema_alignment",
    "get_factor_definition",
    "get_factor_pack",
    "list_factor_definitions",
]