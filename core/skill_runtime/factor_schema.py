"""P0 Unified field definition and output schema for fundamental factors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Dict, List, Literal


FactorBundleId = Literal["value_core", "quality_core", "growth_cashflow_core", "technical_core"]
SchemaDataType = Literal["number", "string", "boolean"]
DataQualityTier = Literal["standard", "cautious"]
CalculationMode = Literal["direct", "fallback", "derived", "ratio", "peer_stat", "period_compare", "composite_score", "time_series"]
WarningCategory = Literal["fallback_used", "proxy_used", "low_sample_size", "precision_degraded"]
TaxEstimationStrategy = Literal["profit_based_clamped_0_35_else_fixed_25"]
PeriodSelectionStrategy = Literal[
    "current_period_only",
    "same_period_last_year",
    "same_period_n_years_3",
    "previous_available_period",
]
SemanticTag = Literal[
    "fallback_chain",
    "denominator_guard",
    "unit_conversion",
    "conservative_proxy",
    "availability_guard",
]


COND_INDUSTRY_PEER_SAMPLE_COUNT_GE_5 = "industry_peer_sample_count >= 5"
COND_TOTAL_EQUITY_NON_ZERO = "total_equity != 0"
COND_NET_PROFIT_YOY_POSITIVE = "net_profit_yoy > 0"
COND_NET_PROFIT_YOY_NON_ZERO = "net_profit_yoy != 0"
COND_COMPARISON_PERIOD_AVAILABLE = "comparison_period available"
COND_PRIOR_PERIOD_METRIC_NON_ZERO = "prior_period_metric != 0"
COND_BASE_PERIOD_AVAILABLE = "base_period available"
COND_CURRENT_VALUE_POSITIVE = "current_value > 0"
COND_BASE_VALUE_POSITIVE = "base_value > 0"
COND_INVESTED_CAPITAL_POSITIVE = "invested_capital > 0"
COND_NET_PROFIT_NON_ZERO = "net_profit != 0"
COND_TOTAL_ASSETS_NON_ZERO = "total_assets != 0"
COND_TOTAL_LIAB_NON_ZERO = "total_liab != 0"
COND_INTEREST_EXPENSE_POSITIVE = "interest_expense > 0"
COND_INVENTORIES_NON_ZERO = "inventories != 0"
COND_ACCOUNTS_RECEIV_NON_ZERO = "accounts_receiv != 0"
COND_MARKET_CAP_NON_ZERO = "market_cap != 0"
COND_REVENUE_BASE_NON_ZERO = "revenue_base != 0"
COND_PREVIOUS_PERIOD_AVAILABLE = "previous_period available"
COND_ALL_REQUIRED_SIGNAL_INPUTS_AVAILABLE = "all_required_signal_inputs available"
COND_SALES_CURRENT_NON_ZERO = "sales_current != 0"
COND_SALES_PREVIOUS_NON_ZERO = "sales_previous != 0"
COND_TOTAL_ASSETS_CURRENT_NON_ZERO = "total_assets_current != 0"
COND_TOTAL_ASSETS_PREVIOUS_NON_ZERO = "total_assets_previous != 0"
COND_TOTAL_LIAB_PREVIOUS_NON_ZERO = "total_liab_previous != 0"
COND_DEPRECIATION_PLUS_FIXED_ASSETS_CURRENT_NON_ZERO = "depreciation_plus_fixed_assets_current != 0"
COND_DEPRECIATION_PLUS_FIXED_ASSETS_PREVIOUS_NON_ZERO = "depreciation_plus_fixed_assets_previous != 0"
COND_SGA_PREVIOUS_NON_ZERO = "sga_previous != 0"
COND_GROSS_MARGIN_CURRENT_NON_ZERO = "gross_margin_current != 0"
COND_ASSET_QUALITY_PREVIOUS_NON_ZERO = "asset_quality_previous != 0"
COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE = "technical_lookback_window available"

WARN_PE_TTM_FALLBACK_TO_PE = "pe_ttm fallback_to pe"
WARN_PB_FALLBACK_TO_PB_MRQ = "pb fallback_to pb_mrq"
WARN_PB_MRQ_ESTIMATED_FROM_MARKET_CAP_AND_EQUITY = "pb_mrq estimated_from market_cap_and_total_equity"
WARN_PS_TTM_FALLBACK_TO_PS = "ps_ttm fallback_to ps"
WARN_DIVIDEND_YIELD_FALLBACK_TO_FINANCIAL_FIELD = "dividend_yield fallback_to financial_field"
WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5 = "industry_peer_sample_count < 5"
WARN_NET_PROFIT_TTM_FALLBACK_TO_NET_PROFIT_OR_NET_INCOME = "net_profit_ttm fallback_to net_profit_or_net_income"
WARN_ROIC_MONEY_CAP_MISSING_AS_ZERO = "roic money_cap_missing_assumed_zero"
WARN_FCF_CONSERVATIVE_PROXY_USED = "fcf conservative_proxy_used"
WARN_INTEREST_COVERAGE_FALLBACK_TO_RAW_INTEREST_EXPENSE = "interest_coverage fallback_to raw_interest_expense"
WARN_INVENTORY_TURNOVER_COST_PROXY_USED = "inventory_turnover cost_proxy_used"
WARN_NET_CASH_POSITION_PROXY_TOTAL_NCL_USED = "net_cash_position proxy_total_ncl_used"


@dataclass(frozen=True)
class FactorFieldSchema:
    field_name: str
    display_name: str
    bundle: FactorBundleId
    data_type: SchemaDataType
    unit: str
    description: str
    screening_unit: str | None = None
    source_priority: List[str] | None = None
    data_quality_tier: DataQualityTier = "standard"
    calculation_mode: CalculationMode = "direct"
    tax_estimation_strategy: TaxEstimationStrategy | None = None
    period_selection_strategy: PeriodSelectionStrategy | None = None
    minimum_input_groups: List[List[str]] | None = None
    minimum_computable_conditions: List[str] | None = None
    warning_conditions: List[str] | None = None
    warning_categories: List[WarningCategory] | None = None
    semantic_tags: List[SemanticTag] | None = None
    included_in_screening: bool = True
    included_in_snapshot: bool = True

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


P0_VALUE_FIELDS: List[str] = [
    "pe",
    "pe_ttm",
    "pb",
    "pb_mrq",
    "ps_ttm",
    "dividend_yield",
    "peg",
    "industry_pe_median",
    "industry_pb_median",
]

P0_QUALITY_FIELDS: List[str] = [
    "roe",
    "roa",
    "gross_margin",
    "netprofit_margin",
    "debt_to_assets",
    "assets_to_eqt",
    "current_ratio",
    "quick_ratio",
    "cash_ratio",
    "roic",
    "cash_conversion",
    "accrual_ratio",
    "asset_turnover",
    "gross_profit_to_assets",
    "interest_coverage",
    "inventory_turnover",
    "receivable_turnover",
    "net_cash_position",
    "piotroski_f_score",
    "altman_z_score",
    "beneish_m_score",
]

P0_GROWTH_CASHFLOW_FIELDS: List[str] = [
    "revenue_yoy",
    "net_profit_yoy",
    "oper_profit_yoy",
    "revenue_cagr_3y",
    "profit_cagr_3y",
    "revenue_ttm",
    "net_profit_ttm",
    "n_cashflow_act",
    "fcf",
    "fcf_yield",
    "fcf_margin",
    "ocf_yield",
    "net_working_capital",
    "working_capital_change",
]

P0_SNAPSHOT_ONLY_FIELDS: List[str] = [
    "industry_pe_median",
    "industry_pb_median",
]

P0_PUBLIC_SCREENING_FIELDS: List[str] = sorted(
    set(P0_VALUE_FIELDS + P0_QUALITY_FIELDS + P0_GROWTH_CASHFLOW_FIELDS) - set(P0_SNAPSHOT_ONLY_FIELDS)
)

TECHNICAL_FACTOR_FIELDS: List[str] = [
    "ma20",
    "ma60",
    "rsi14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "dif",
    "dea",
    "macd_hist",
]

TECHNICAL_PUBLIC_SCREENING_FIELDS: List[str] = [
    "ma20",
    "rsi14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "dif",
    "dea",
    "macd_hist",
]


P0_SOURCE_PRIORITY_BY_FIELD: Dict[str, List[str]] = {
    "pe": ["basic_info.pe", "market_quotes.pe"],
    "pe_ttm": ["basic_info.pe_ttm", "basic_info.pe", "market_quotes.pe"],
    "pb": ["basic_info.pb", "pb_mrq"],
    "pb_mrq": ["basic_info.pb_mrq", "market_quotes.total_mv|basic_info.total_mv|basic_info.market_cap", "latest_financial.total_equity"],
    "ps_ttm": ["basic_info.ps_ttm", "basic_info.ps"],
    "dividend_yield": ["basic_info.dividend_yield", "latest_financial.financial_indicators.dividend_yield", "latest_financial.dividend_yield"],
    "peg": ["pe_ttm", "net_profit_yoy"],
    "industry_pe_median": ["basic_info.industry", "industry_peer.pe_ttm|pe"],
    "industry_pb_median": ["basic_info.industry", "industry_peer.pb|pb_mrq"],
    "roe": ["latest_financial.roe", "latest_financial.financial_indicators.roe", "latest_financial.financial_indicators.roe_avg"],
    "roa": ["latest_financial.roa", "latest_financial.financial_indicators.roa"],
    "gross_margin": ["latest_financial.gross_margin", "latest_financial.financial_indicators.grossprofit_margin", "latest_financial.financial_indicators.gross_margin"],
    "netprofit_margin": ["latest_financial.netprofit_margin", "latest_financial.financial_indicators.netprofit_margin"],
    "debt_to_assets": ["latest_financial.debt_to_assets", "latest_financial.financial_indicators.debt_to_assets"],
    "assets_to_eqt": ["latest_financial.assets_to_eqt", "latest_financial.financial_indicators.assets_to_eqt"],
    "current_ratio": ["latest_financial.current_ratio", "latest_financial.financial_indicators.current_ratio"],
    "quick_ratio": ["latest_financial.quick_ratio", "latest_financial.financial_indicators.quick_ratio"],
    "cash_ratio": ["latest_financial.cash_ratio", "latest_financial.financial_indicators.cash_ratio"],
    "roic": ["latest_financial.ebit|oper_profit|operating_profit", "latest_financial.total_equity", "latest_financial.total_liab", "latest_financial.money_cap", "latest_financial.total_profit|net_profit"],
    "cash_conversion": ["latest_financial.n_cashflow_act", "latest_financial.net_profit|net_income"],
    "accrual_ratio": ["latest_financial.net_profit|net_income", "latest_financial.n_cashflow_act", "latest_financial.total_assets"],
    "asset_turnover": ["latest_financial.revenue_ttm|revenue|oper_rev", "latest_financial.total_assets"],
    "gross_profit_to_assets": ["latest_financial.revenue_ttm|revenue|oper_rev", "latest_financial.gross_margin", "latest_financial.total_assets"],
    "interest_coverage": ["latest_financial.ebit|oper_profit|operating_profit", "latest_financial.fin_exp", "raw_data.income_statement.int_exp|fin_exp_int_exp"],
    "inventory_turnover": ["latest_financial.oper_cost", "latest_financial.revenue_ttm|revenue|oper_rev", "latest_financial.gross_margin", "latest_financial.inventories"],
    "receivable_turnover": ["latest_financial.revenue_ttm|revenue|oper_rev", "latest_financial.accounts_receiv"],
    "net_cash_position": ["latest_financial.money_cap", "latest_financial.total_ncl", "latest_financial.total_liab|total_cur_liab", "latest_financial.total_assets"],
    "piotroski_f_score": ["latest_financial+previous_financial.period_records", "roa|n_cashflow_act|current_ratio|gross_margin|asset_turnover"],
    "altman_z_score": ["latest_financial.total_assets|total_liab|total_cur_assets|total_cur_liab|ebit|revenue", "market_quotes.total_mv|basic_info.total_mv|basic_info.market_cap", "raw_data.balance_sheet.undistr_porfit"],
    "beneish_m_score": ["latest_financial+previous_financial.period_records", "revenue|accounts_receiv|oper_cost|total_assets|total_cur_assets|fix_assets|n_cashflow_act", "raw_data depreciation/amortization/expense fields"],
    "revenue_yoy": ["financial_records.latest.revenue|oper_rev", "financial_records.prior_same_period.revenue|oper_rev"],
    "net_profit_yoy": ["financial_records.latest.net_profit|net_income", "financial_records.prior_same_period.net_profit|net_income"],
    "oper_profit_yoy": ["financial_records.latest.oper_profit|operating_profit|ebit", "financial_records.prior_same_period.oper_profit|operating_profit|ebit"],
    "revenue_cagr_3y": ["financial_records.latest.revenue_ttm|revenue|oper_rev", "financial_records.base_3y.revenue_ttm|revenue|oper_rev"],
    "profit_cagr_3y": ["financial_records.latest.net_profit_ttm|net_profit|net_income", "financial_records.base_3y.net_profit_ttm|net_profit|net_income"],
    "revenue_ttm": ["latest_financial.revenue_ttm"],
    "net_profit_ttm": ["latest_financial.net_profit_ttm", "latest_financial.net_profit", "latest_financial.net_income"],
    "n_cashflow_act": ["latest_financial.n_cashflow_act", "latest_financial.cashflow_statement.n_cashflow_act"],
    "fcf": ["latest_financial.n_cashflow_act", "latest_financial.n_cashflow_inv_act"],
    "fcf_yield": ["market_quotes.total_mv", "basic_info.total_mv", "basic_info.market_cap"],
    "fcf_margin": ["fcf", "latest_financial.revenue_ttm|revenue|oper_rev"],
    "ocf_yield": ["market_quotes.total_mv", "basic_info.total_mv", "basic_info.market_cap"],
    "net_working_capital": ["latest_financial.total_cur_assets", "latest_financial.total_cur_liab"],
    "working_capital_change": ["latest_financial.total_cur_assets|total_cur_liab", "previous_financial.total_cur_assets|total_cur_liab"],
}

TECHNICAL_SOURCE_PRIORITY_BY_FIELD: Dict[str, List[str]] = {
    "ma20": ["stock_technical_indicators.ma20", "stock_daily_quotes.close"],
    "ma60": ["stock_daily_quotes.close"],
    "rsi14": ["stock_technical_indicators.rsi14", "stock_daily_quotes.close"],
    "kdj_k": ["stock_technical_indicators.kdj_k", "stock_daily_quotes.high|low|close"],
    "kdj_d": ["stock_technical_indicators.kdj_d", "stock_daily_quotes.high|low|close"],
    "kdj_j": ["stock_technical_indicators.kdj_j", "stock_daily_quotes.high|low|close"],
    "dif": ["stock_technical_indicators.dif", "stock_daily_quotes.close"],
    "dea": ["stock_technical_indicators.dea", "stock_daily_quotes.close"],
    "macd_hist": ["stock_technical_indicators.macd_hist", "stock_daily_quotes.close"],
}


P0_FACTOR_FIELD_SCHEMA: Dict[str, FactorFieldSchema] = {
    "pe": FactorFieldSchema("pe", "P/E ratio", "value_core", "number", "times", "Static P/E ratio.", source_priority=["basic_info.pe", "market_quotes.pe"], minimum_input_groups=[["pe"]]),
    "pe_ttm": FactorFieldSchema("pe_ttm", "rolling price to earnings ratio", "value_core", "number", "times", "Rolling P/E ratio.", source_priority=["basic_info.pe_ttm", "basic_info.pe", "market_quotes.pe"], calculation_mode="fallback", minimum_input_groups=[["pe_ttm"], ["pe"]], warning_conditions=[WARN_PE_TTM_FALLBACK_TO_PE], warning_categories=["fallback_used"], semantic_tags=["fallback_chain"]),
    "pb": FactorFieldSchema("pb", "price to book ratio", "value_core", "number", "times", "Price to Book Ratio.", source_priority=["basic_info.pb", "pb_mrq"], calculation_mode="fallback", minimum_input_groups=[["pb"], ["pb_mrq"]], warning_conditions=[WARN_PB_FALLBACK_TO_PB_MRQ], warning_categories=["fallback_used"], semantic_tags=["fallback_chain"]),
    "pb_mrq": FactorFieldSchema("pb_mrq", "Latest price-to-book ratio", "value_core", "number", "times", "The latest caliber price-to-book ratio.", source_priority=["basic_info.pb_mrq", "market_quotes.total_mv|basic_info.total_mv|basic_info.market_cap", "latest_financial.total_equity"], calculation_mode="ratio", minimum_input_groups=[["pb_mrq"], ["total_mv|market_cap", "total_equity"]], minimum_computable_conditions=[COND_TOTAL_EQUITY_NON_ZERO], warning_conditions=[WARN_PB_MRQ_ESTIMATED_FROM_MARKET_CAP_AND_EQUITY], warning_categories=["proxy_used"], semantic_tags=["fallback_chain", "conservative_proxy"]),
    "ps_ttm": FactorFieldSchema("ps_ttm", "rolling price-to-sales ratio", "value_core", "number", "times", "Rolling price-to-sales ratio.", source_priority=["basic_info.ps_ttm", "basic_info.ps"], calculation_mode="fallback", minimum_input_groups=[["ps_ttm"], ["ps"]], warning_conditions=[WARN_PS_TTM_FALLBACK_TO_PS], warning_categories=["fallback_used"], semantic_tags=["fallback_chain"]),
    "dividend_yield": FactorFieldSchema("dividend_yield", "dividend yield", "value_core", "number", "%", "Last 12 months dividend yield.", source_priority=["basic_info.dividend_yield", "latest_financial.financial_indicators.dividend_yield", "latest_financial.dividend_yield"], calculation_mode="fallback", minimum_input_groups=[["dividend_yield"], ["financial_indicators.dividend_yield"]], warning_conditions=[WARN_DIVIDEND_YIELD_FALLBACK_TO_FINANCIAL_FIELD], warning_categories=["fallback_used"], semantic_tags=["fallback_chain"]),
    "peg": FactorFieldSchema("peg", "PEG", "value_core", "number", "times/%", "PE TTM Ratio to net profit growth rate.", calculation_mode="ratio", minimum_input_groups=[["pe_ttm", "net_profit_yoy"], ["pe", "net_profit_yoy"]], minimum_computable_conditions=[COND_NET_PROFIT_YOY_POSITIVE, COND_NET_PROFIT_YOY_NON_ZERO], semantic_tags=["fallback_chain", "availability_guard"]),
    "industry_pe_median": FactorFieldSchema("industry_pe_median", "Industry PE median", "value_core", "number", "times", "Industry benchmark for horizontal comparison.", calculation_mode="peer_stat", minimum_input_groups=[["industry", "pe_ttm"], ["industry", "pe"]], warning_conditions=[WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5], warning_categories=["low_sample_size"], semantic_tags=["availability_guard"], included_in_screening=False),
    "industry_pb_median": FactorFieldSchema("industry_pb_median", "Industry Median PB", "value_core", "number", "times", "Industry benchmark for horizontal comparison.", calculation_mode="peer_stat", minimum_input_groups=[["industry", "pb"], ["industry", "pb_mrq"]], warning_conditions=[WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5], warning_categories=["low_sample_size"], included_in_screening=False),
    "roe": FactorFieldSchema("roe", "ROE", "quality_core", "number", "%", "ROE.", minimum_input_groups=[["roe"]]),
    "roa": FactorFieldSchema("roa", "return on total assets", "quality_core", "number", "%", "Return on total assets.", minimum_input_groups=[["roa"]]),
    "gross_margin": FactorFieldSchema("gross_margin", "Gross profit margin", "quality_core", "number", "%", "gross profit margin.", minimum_input_groups=[["gross_margin"]]),
    "netprofit_margin": FactorFieldSchema("netprofit_margin", "net profit margin", "quality_core", "number", "%", "Net profit margin.", minimum_input_groups=[["netprofit_margin"]]),
    "debt_to_assets": FactorFieldSchema("debt_to_assets", "Asset-liability ratio", "quality_core", "number", "%", "Total liabilities/total assets.", minimum_input_groups=[["debt_to_assets"]]),
    "assets_to_eqt": FactorFieldSchema("assets_to_eqt", "equity multiplier", "quality_core", "number", "times", "Total assets/shareholders equity.", minimum_input_groups=[["assets_to_eqt"]]),
    "current_ratio": FactorFieldSchema("current_ratio", "current ratio", "quality_core", "number", "times", "Current assets/current liabilities.", minimum_input_groups=[["current_ratio"]]),
    "quick_ratio": FactorFieldSchema("quick_ratio", "quick ratio", "quality_core", "number", "times", "Quick ratio.", minimum_input_groups=[["quick_ratio"]]),
    "cash_ratio": FactorFieldSchema("cash_ratio", "cash ratio", "quality_core", "number", "times", "Cash Ratio.", minimum_input_groups=[["cash_ratio"]]),
    "roic": FactorFieldSchema("roic", "return on invested capital", "quality_core", "number", "%", "Conservative agent caliber ROIC.", calculation_mode="ratio", tax_estimation_strategy="profit_based_clamped_0_35_else_fixed_25", minimum_input_groups=[["ebit|oper_profit|operating_profit", "total_equity", "total_liab"]], minimum_computable_conditions=[COND_INVESTED_CAPITAL_POSITIVE], warning_conditions=[WARN_ROIC_MONEY_CAP_MISSING_AS_ZERO], warning_categories=["precision_degraded"], semantic_tags=["fallback_chain", "conservative_proxy"]),
    "cash_conversion": FactorFieldSchema("cash_conversion", "Profit to cash conversion rate", "quality_core", "number", "times", "Operating cash flow/net profit.", calculation_mode="ratio", minimum_input_groups=[["n_cashflow_act", "net_profit|net_income"]], minimum_computable_conditions=[COND_NET_PROFIT_NON_ZERO], semantic_tags=["availability_guard"]),
    "accrual_ratio": FactorFieldSchema("accrual_ratio", "accruals ratio", "quality_core", "number", "%", "(Net Profit - Operating Cash Flow)/total assets.", calculation_mode="ratio", minimum_input_groups=[["net_profit|net_income", "n_cashflow_act", "total_assets"]], minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO], semantic_tags=["denominator_guard", "unit_conversion"]),
    "asset_turnover": FactorFieldSchema("asset_turnover", "asset turnover rate", "quality_core", "number", "times", "Operating income/total assets.", calculation_mode="ratio", minimum_input_groups=[["revenue_ttm|revenue|oper_rev", "total_assets"]], minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO], semantic_tags=["denominator_guard"]),
    "gross_profit_to_assets": FactorFieldSchema("gross_profit_to_assets", "Gross profit/total assets", "quality_core", "number", "%", "Gross profit relative to total asset efficiency.", calculation_mode="ratio", minimum_input_groups=[["revenue_ttm|revenue|oper_rev", "gross_margin", "total_assets"]], minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO], semantic_tags=["denominator_guard", "unit_conversion"]),
    "interest_coverage": FactorFieldSchema("interest_coverage", "interest coverage ratio", "quality_core", "number", "times", "EBIT/Interest Expenses.", calculation_mode="ratio", minimum_input_groups=[["ebit|oper_profit|operating_profit", "fin_exp"], ["ebit|oper_profit|operating_profit", "raw_data.income_statement.int_exp|fin_exp_int_exp"]], minimum_computable_conditions=[COND_INTEREST_EXPENSE_POSITIVE], warning_conditions=[WARN_INTEREST_COVERAGE_FALLBACK_TO_RAW_INTEREST_EXPENSE], warning_categories=["fallback_used"], semantic_tags=["fallback_chain", "availability_guard"]),
    "inventory_turnover": FactorFieldSchema("inventory_turnover", "Inventory turnover", "quality_core", "number", "times", "Operating cost/inventory balance agency.", calculation_mode="ratio", minimum_input_groups=[["oper_cost", "inventories"], ["revenue_ttm|revenue|oper_rev", "gross_margin", "inventories"]], minimum_computable_conditions=[COND_INVENTORIES_NON_ZERO], warning_conditions=[WARN_INVENTORY_TURNOVER_COST_PROXY_USED], warning_categories=["proxy_used"], semantic_tags=["fallback_chain", "denominator_guard"]),
    "receivable_turnover": FactorFieldSchema("receivable_turnover", "Receivables turnover ratio", "quality_core", "number", "times", "Operating Income/Balance Receivable Agency.", calculation_mode="ratio", minimum_input_groups=[["revenue_ttm|revenue|oper_rev", "accounts_receiv"]], minimum_computable_conditions=[COND_ACCOUNTS_RECEIV_NON_ZERO], semantic_tags=["denominator_guard"]),
    "net_cash_position": FactorFieldSchema("net_cash_position", "net cash position", "quality_core", "number", "%", "(money_cap-total_ncl)/total_assets agent.", calculation_mode="ratio", minimum_input_groups=[["money_cap", "total_ncl", "total_assets"], ["money_cap", "total_liab", "total_cur_liab", "total_assets"]], minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO], warning_conditions=[WARN_NET_CASH_POSITION_PROXY_TOTAL_NCL_USED], warning_categories=["proxy_used"], semantic_tags=["fallback_chain", "conservative_proxy"]),
    "piotroski_f_score": FactorFieldSchema("piotroski_f_score", "Piotroski F-Score", "quality_core", "number", "points", "9 financial signal score.", data_quality_tier="cautious", calculation_mode="composite_score", minimum_input_groups=[["latest_period", "comparison_period", "roa", "n_cashflow_act", "current_ratio", "gross_margin", "asset_turnover"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_ALL_REQUIRED_SIGNAL_INPUTS_AVAILABLE]),
    "altman_z_score": FactorFieldSchema("altman_z_score", "Altman Z-Score", "quality_core", "number", "points", "Financial Distress Score.", data_quality_tier="cautious", calculation_mode="composite_score", minimum_input_groups=[["total_assets", "total_liab", "total_cur_assets", "total_cur_liab", "ebit", "revenue", "market_value_proxy", "undistr_porfit"]], minimum_computable_conditions=[COND_TOTAL_ASSETS_NON_ZERO, COND_TOTAL_LIAB_NON_ZERO]),
    "beneish_m_score": FactorFieldSchema("beneish_m_score", "Beneish M-Score", "quality_core", "number", "points", "Earnings manipulation risk score.", data_quality_tier="cautious", calculation_mode="composite_score", minimum_input_groups=[["latest_period", "comparison_period", "revenue", "accounts_receiv", "oper_cost", "total_assets", "total_cur_assets", "fix_assets", "n_cashflow_act", "depreciation_current", "depreciation_previous"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_SALES_CURRENT_NON_ZERO, COND_SALES_PREVIOUS_NON_ZERO, COND_TOTAL_ASSETS_CURRENT_NON_ZERO, COND_TOTAL_ASSETS_PREVIOUS_NON_ZERO, COND_TOTAL_LIAB_PREVIOUS_NON_ZERO, COND_DEPRECIATION_PLUS_FIXED_ASSETS_CURRENT_NON_ZERO, COND_DEPRECIATION_PLUS_FIXED_ASSETS_PREVIOUS_NON_ZERO, COND_SGA_PREVIOUS_NON_ZERO, COND_GROSS_MARGIN_CURRENT_NON_ZERO, COND_ASSET_QUALITY_PREVIOUS_NON_ZERO]),
    "revenue_yoy": FactorFieldSchema("revenue_yoy", "Year-on-year revenue", "growth_cashflow_core", "number", "%", "Revenue for this period increased compared with the same period last year.", calculation_mode="period_compare", period_selection_strategy="same_period_last_year", minimum_input_groups=[["latest_period.revenue|oper_rev", "prior_same_period.revenue|oper_rev"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_PRIOR_PERIOD_METRIC_NON_ZERO]),
    "net_profit_yoy": FactorFieldSchema("net_profit_yoy", "Net profit year-on-year", "growth_cashflow_core", "number", "%", "Net profit for this period increased compared with the same period last year.", calculation_mode="period_compare", period_selection_strategy="same_period_last_year", minimum_input_groups=[["latest_period.net_profit|net_income", "prior_same_period.net_profit|net_income"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_PRIOR_PERIOD_METRIC_NON_ZERO]),
    "oper_profit_yoy": FactorFieldSchema("oper_profit_yoy", "Operating profit year-on-year", "growth_cashflow_core", "number", "%", "Operating profit for this period increased compared with the same period last year.", calculation_mode="period_compare", period_selection_strategy="same_period_last_year", minimum_input_groups=[["latest_period.oper_profit|operating_profit|ebit", "prior_same_period.oper_profit|operating_profit|ebit"]], minimum_computable_conditions=[COND_COMPARISON_PERIOD_AVAILABLE, COND_PRIOR_PERIOD_METRIC_NON_ZERO]),
    "revenue_cagr_3y": FactorFieldSchema("revenue_cagr_3y", "Three-year revenue compound growth rate", "growth_cashflow_core", "number", "%", "Calculated based on the caliber three years ago in the same quarter.", calculation_mode="period_compare", period_selection_strategy="same_period_n_years_3", minimum_input_groups=[["latest_period.revenue_ttm|revenue|oper_rev", "base_3y_period.revenue_ttm|revenue|oper_rev"]], minimum_computable_conditions=[COND_BASE_PERIOD_AVAILABLE, COND_CURRENT_VALUE_POSITIVE, COND_BASE_VALUE_POSITIVE]),
    "profit_cagr_3y": FactorFieldSchema("profit_cagr_3y", "Three-year profit compound growth rate", "growth_cashflow_core", "number", "%", "Calculated based on the caliber three years ago in the same quarter.", calculation_mode="period_compare", period_selection_strategy="same_period_n_years_3", minimum_input_groups=[["latest_period.net_profit_ttm|net_profit|net_income", "base_3y_period.net_profit_ttm|net_profit|net_income"]], minimum_computable_conditions=[COND_BASE_PERIOD_AVAILABLE, COND_CURRENT_VALUE_POSITIVE, COND_BASE_VALUE_POSITIVE]),
    "revenue_ttm": FactorFieldSchema("revenue_ttm", "rolling revenue", "growth_cashflow_core", "number", "Yuan", "Revenue for the last four quarters.", period_selection_strategy="current_period_only", minimum_input_groups=[["revenue_ttm"]]),
    "net_profit_ttm": FactorFieldSchema("net_profit_ttm", "rolling net profit", "growth_cashflow_core", "number", "Yuan", "net profit in the last four quarters.", source_priority=["latest_financial.net_profit_ttm", "latest_financial.net_profit", "latest_financial.net_income"], calculation_mode="fallback", minimum_input_groups=[["net_profit_ttm"], ["net_profit"], ["net_income"]], warning_conditions=[WARN_NET_PROFIT_TTM_FALLBACK_TO_NET_PROFIT_OR_NET_INCOME], warning_categories=["fallback_used"], semantic_tags=["fallback_chain"]),
    "n_cashflow_act": FactorFieldSchema("n_cashflow_act", "Net operating cash flow", "growth_cashflow_core", "number", "Yuan", "Net cash flow from operating activities.", period_selection_strategy="current_period_only", minimum_input_groups=[["n_cashflow_act"]]),
    "fcf": FactorFieldSchema("fcf", "free cash flow", "growth_cashflow_core", "number", "Yuan", "Operating cash flow plus investing cash flow proxy.", calculation_mode="derived", minimum_input_groups=[["n_cashflow_act", "n_cashflow_inv_act"]], warning_conditions=[WARN_FCF_CONSERVATIVE_PROXY_USED], warning_categories=["proxy_used"], semantic_tags=["conservative_proxy"]),
    "fcf_yield": FactorFieldSchema("fcf_yield", "free cash flow yield", "growth_cashflow_core", "number", "%", "Free cash flow/total market capitalization.", source_priority=["market_quotes.total_mv", "basic_info.total_mv", "basic_info.market_cap"], calculation_mode="ratio", minimum_input_groups=[["fcf", "total_mv|market_cap"]], minimum_computable_conditions=[COND_MARKET_CAP_NON_ZERO], semantic_tags=["unit_conversion"]),
    "fcf_margin": FactorFieldSchema("fcf_margin", "free cash flow rate", "growth_cashflow_core", "number", "%", "Free cash flow/operating income.", calculation_mode="ratio", minimum_input_groups=[["fcf", "revenue_ttm"], ["fcf", "revenue"], ["fcf", "oper_rev"]], minimum_computable_conditions=[COND_REVENUE_BASE_NON_ZERO], semantic_tags=["fallback_chain"]),
    "ocf_yield": FactorFieldSchema("ocf_yield", "operating cash flow yield", "growth_cashflow_core", "number", "%", "Operating cash flow/total market capitalization.", source_priority=["market_quotes.total_mv", "basic_info.total_mv", "basic_info.market_cap"], calculation_mode="ratio", minimum_input_groups=[["n_cashflow_act", "total_mv|market_cap"]], minimum_computable_conditions=[COND_MARKET_CAP_NON_ZERO], semantic_tags=["unit_conversion"]),
    "net_working_capital": FactorFieldSchema("net_working_capital", "net working capital", "growth_cashflow_core", "number", "Yuan", "Current assets minus current liabilities.", screening_unit="billion", calculation_mode="derived", period_selection_strategy="current_period_only", minimum_input_groups=[["total_cur_assets", "total_cur_liab"]]),
    "working_capital_change": FactorFieldSchema("working_capital_change", "working capital changes", "growth_cashflow_core", "number", "Yuan", "The difference in net working capital between the two most recent periods.", screening_unit="billion", calculation_mode="period_compare", period_selection_strategy="previous_available_period", minimum_input_groups=[["latest_period.total_cur_assets", "latest_period.total_cur_liab", "previous_period.total_cur_assets", "previous_period.total_cur_liab"]], minimum_computable_conditions=[COND_PREVIOUS_PERIOD_AVAILABLE], semantic_tags=["availability_guard"]),
}

P0_FACTOR_FIELD_SCHEMA = {
    name: schema if schema.source_priority else replace(schema, source_priority=list(P0_SOURCE_PRIORITY_BY_FIELD.get(name, [])))
    for name, schema in P0_FACTOR_FIELD_SCHEMA.items()
}

TECHNICAL_FACTOR_FIELD_SCHEMA: Dict[str, FactorFieldSchema] = {
    "ma20": FactorFieldSchema("ma20", "20 daily moving average", "technical_core", "number", "Yuan", "20 Moving average of closing prices on a trading day.", source_priority=["stock_technical_indicators.ma20", "stock_daily_quotes.close"], calculation_mode="time_series", minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "ma60": FactorFieldSchema("ma60", "60 daily moving average", "technical_core", "number", "Yuan", "60 Moving average of closing prices on a trading day.", source_priority=["stock_daily_quotes.close"], calculation_mode="time_series", minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=False, included_in_snapshot=False),
    "rsi14": FactorFieldSchema("rsi14", "RSI indicator", "technical_core", "number", "", "14 Daily Relative Strength Index.", source_priority=["stock_technical_indicators.rsi14", "stock_daily_quotes.close"], calculation_mode="time_series", minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "kdj_k": FactorFieldSchema("kdj_k", "KDJ-K", "technical_core", "number", "", "KDJ Indicator K value.", source_priority=["stock_technical_indicators.kdj_k", "stock_daily_quotes.high|low|close"], calculation_mode="time_series", minimum_input_groups=[["high", "low", "close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "kdj_d": FactorFieldSchema("kdj_d", "KDJ-D", "technical_core", "number", "", "KDJ Indicator D value.", source_priority=["stock_technical_indicators.kdj_d", "stock_daily_quotes.high|low|close"], calculation_mode="time_series", minimum_input_groups=[["high", "low", "close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "kdj_j": FactorFieldSchema("kdj_j", "KDJ-J", "technical_core", "number", "", "KDJ Indicator J value.", source_priority=["stock_technical_indicators.kdj_j", "stock_daily_quotes.high|low|close"], calculation_mode="time_series", minimum_input_groups=[["high", "low", "close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "dif": FactorFieldSchema("dif", "MACD-DIF", "technical_core", "number", "", "MACD The difference between fast and slow lines.", source_priority=["stock_technical_indicators.dif", "stock_daily_quotes.close"], calculation_mode="time_series", minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "dea": FactorFieldSchema("dea", "MACD-DEA", "technical_core", "number", "", "MACD signal line.", source_priority=["stock_technical_indicators.dea", "stock_daily_quotes.close"], calculation_mode="time_series", minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
    "macd_hist": FactorFieldSchema("macd_hist", "MACD bar chart", "technical_core", "number", "", "MACD Histogram values.", source_priority=["stock_technical_indicators.macd_hist", "stock_daily_quotes.close"], calculation_mode="time_series", minimum_input_groups=[["close"]], minimum_computable_conditions=[COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE], semantic_tags=["availability_guard"], included_in_screening=True, included_in_snapshot=True),
}

ALL_FACTOR_FIELD_SCHEMA: Dict[str, FactorFieldSchema] = {
    **P0_FACTOR_FIELD_SCHEMA,
    **TECHNICAL_FACTOR_FIELD_SCHEMA,
}


def get_factor_field_schema(field_name: str) -> FactorFieldSchema | None:
    """Query the factor field schema by field name.

    Args:
        field_name: factor field name (e.g. "pe_ttm" / "roe" / "ma20") 

    Returns:
        FactorFieldSchema | None: Hit field Schema object; returned if not registered None
    """
    return ALL_FACTOR_FIELD_SCHEMA.get(field_name)


def list_bundle_fields(bundle: FactorBundleId) -> List[str]:
    """Returns a list of field names contained in the specified factor bundle.

    Args:
        bundle: bundle Identity, optional values:"value_core" / "quality_core" / "growth_cashflow_core"
             (The remaining values fall back to the growth_cashflow_core field set)

    Returns:
        list[str]: The list of field names contained in this bundle
    """
    if bundle == "value_core":
        return list(P0_VALUE_FIELDS)
    if bundle == "quality_core":
        return list(P0_QUALITY_FIELDS)
    return list(P0_GROWTH_CASHFLOW_FIELDS)


def get_p0_snapshot_schema() -> Dict[str, object]:
    """Returns the overall Schema description of the P0 factor snapshot.

    Returns:
        dict: Field description——
            bundles: Collection of fields for each bundle
                — value_core: list[str], Value core field name list
                — quality_core: list[str], Quality core field name list
                — growth_cashflow_core: list[str], List of core field names for growth and cash flow
            snapshot_only_fields: list[str], List of field names used only for snapshots
            public_screening_fields: list[str], Publicly filter the list of available field names
            technical_fields: list[str], Technical factor field name list
            technical_public_screening_fields: list[str], Technical factors public filter field name list
            fields: dict[str, dict], Mapping of all field names to field Schema dict
    """
    return {
        "bundles": {
            "value_core": list(P0_VALUE_FIELDS),
            "quality_core": list(P0_QUALITY_FIELDS),
            "growth_cashflow_core": list(P0_GROWTH_CASHFLOW_FIELDS),
        },
        "snapshot_only_fields": list(P0_SNAPSHOT_ONLY_FIELDS),
        "public_screening_fields": list(P0_PUBLIC_SCREENING_FIELDS),
        "technical_fields": list(TECHNICAL_FACTOR_FIELDS),
        "technical_public_screening_fields": list(TECHNICAL_PUBLIC_SCREENING_FIELDS),
        "fields": {name: schema.to_dict() for name, schema in ALL_FACTOR_FIELD_SCHEMA.items()},
    }


__all__ = [
    "ALL_FACTOR_FIELD_SCHEMA",
    "CalculationMode",
    "FactorFieldSchema",
    "DataQualityTier",
    "PeriodSelectionStrategy",
    "P0_FACTOR_FIELD_SCHEMA",
    "P0_GROWTH_CASHFLOW_FIELDS",
    "P0_PUBLIC_SCREENING_FIELDS",
    "P0_QUALITY_FIELDS",
    "P0_SNAPSHOT_ONLY_FIELDS",
    "P0_SOURCE_PRIORITY_BY_FIELD",
    "P0_VALUE_FIELDS",
    "SemanticTag",
    "TECHNICAL_FACTOR_FIELD_SCHEMA",
    "TECHNICAL_FACTOR_FIELDS",
    "TECHNICAL_PUBLIC_SCREENING_FIELDS",
    "TECHNICAL_SOURCE_PRIORITY_BY_FIELD",
    "TaxEstimationStrategy",
    "WarningCategory",
    "COND_ACCOUNTS_RECEIV_NON_ZERO",
    "COND_ALL_REQUIRED_SIGNAL_INPUTS_AVAILABLE",
    "COND_ASSET_QUALITY_PREVIOUS_NON_ZERO",
    "COND_BASE_PERIOD_AVAILABLE",
    "COND_BASE_VALUE_POSITIVE",
    "COND_COMPARISON_PERIOD_AVAILABLE",
    "COND_CURRENT_VALUE_POSITIVE",
    "COND_DEPRECIATION_PLUS_FIXED_ASSETS_CURRENT_NON_ZERO",
    "COND_DEPRECIATION_PLUS_FIXED_ASSETS_PREVIOUS_NON_ZERO",
    "COND_GROSS_MARGIN_CURRENT_NON_ZERO",
    "COND_INDUSTRY_PEER_SAMPLE_COUNT_GE_5",
    "COND_INTEREST_EXPENSE_POSITIVE",
    "COND_INVENTORIES_NON_ZERO",
    "COND_INVESTED_CAPITAL_POSITIVE",
    "COND_MARKET_CAP_NON_ZERO",
    "COND_NET_PROFIT_NON_ZERO",
    "COND_NET_PROFIT_YOY_NON_ZERO",
    "COND_NET_PROFIT_YOY_POSITIVE",
    "COND_PREVIOUS_PERIOD_AVAILABLE",
    "COND_PRIOR_PERIOD_METRIC_NON_ZERO",
    "COND_REVENUE_BASE_NON_ZERO",
    "COND_SALES_CURRENT_NON_ZERO",
    "COND_SALES_PREVIOUS_NON_ZERO",
    "COND_SGA_PREVIOUS_NON_ZERO",
    "COND_TECHNICAL_LOOKBACK_WINDOW_AVAILABLE",
    "COND_TOTAL_ASSETS_CURRENT_NON_ZERO",
    "COND_TOTAL_ASSETS_NON_ZERO",
    "COND_TOTAL_ASSETS_PREVIOUS_NON_ZERO",
    "COND_TOTAL_EQUITY_NON_ZERO",
    "COND_TOTAL_LIAB_NON_ZERO",
    "COND_TOTAL_LIAB_PREVIOUS_NON_ZERO",
    "WARN_DIVIDEND_YIELD_FALLBACK_TO_FINANCIAL_FIELD",
    "WARN_FCF_CONSERVATIVE_PROXY_USED",
    "WARN_INDUSTRY_PEER_SAMPLE_COUNT_LT_5",
    "WARN_INTEREST_COVERAGE_FALLBACK_TO_RAW_INTEREST_EXPENSE",
    "WARN_INVENTORY_TURNOVER_COST_PROXY_USED",
    "WARN_NET_CASH_POSITION_PROXY_TOTAL_NCL_USED",
    "WARN_NET_PROFIT_TTM_FALLBACK_TO_NET_PROFIT_OR_NET_INCOME",
    "WARN_PB_FALLBACK_TO_PB_MRQ",
    "WARN_PB_MRQ_ESTIMATED_FROM_MARKET_CAP_AND_EQUITY",
    "WARN_PE_TTM_FALLBACK_TO_PE",
    "WARN_PS_TTM_FALLBACK_TO_PS",
    "WARN_ROIC_MONEY_CAP_MISSING_AS_ZERO",
    "get_factor_field_schema",
    "get_p0_snapshot_schema",
    "list_bundle_fields",
]