"""
Tool implementation module

All tools organized by category in subdirectories
"""

# Import all tools to trigger automatic registration
from .market.stock_market_data import get_stock_market_data_unified
from .fundamentals.stock_fundamentals import get_stock_fundamentals_unified
from .fundamentals.etf_fundamentals import get_etf_fundamentals
from .fundamentals.financial_tools import (
    get_income_analysis,
    get_balance_sheet_analysis,
    get_cashflow_analysis,
    get_dividend_data,
    get_main_business,
)
from .fundamentals.factor_bundle_tools import (
    get_fundamental_factor_snapshot_tool,
    get_growth_cashflow_factor_bundle_tool,
    get_quality_factor_bundle_tool,
    get_value_factor_bundle_tool,
)
from .fundamentals.standard_financial_tools import (
    get_cashflow_quality_trend_tool,
    get_historical_financial_annual_series_tool,
    get_historical_valuation_percentile_tool,
    get_profitability_stability_metrics_tool,
)
from .fundamentals.valuation_excel_tool import generate_valuation_excel_tool
from .news.stock_news import get_stock_news_unified
from .social.stock_sentiment import get_stock_sentiment_unified
from . import legacy_bridge

# Import market/index analysis tools
from .market.index_market_tools import (
    get_index_data,
    get_market_breadth,
    get_market_environment,
    identify_market_cycle,
)

# Import sector analysis tools
from .market.sector_market_tools import (
    get_sector_data,
    get_fund_flow_data,
    get_peer_comparison,
    analyze_sector,
)

# Import chip distribution analysis tool
from .market.chip_distribution_tools import (
    get_chip_distribution,
    get_chip_distribution_akshare_tool,
    get_chip_distribution_tushare_tool,
)

# Import market-wide batch screening tools
from .market.stock_screening_tool import screen_stocks_by_criteria
from .market.technical_factor_bundle_tool import get_technical_factor_bundle_tool

# Import batch profit stability verification tool
from .fundamentals.batch_profit_consistency import batch_check_profit_consistency

# Import valuation model tool
from .fundamentals.valuation.dcf_valuation import get_dcf_valuation
from .fundamentals.valuation.wacc_calculator import get_wacc_calculation

# Import risk scoring tool
from .risk.altman_zscore import get_altman_zscore
from .risk.piotroski_fscore import get_piotroski_fscore
from .risk.beneish_mscore import get_beneish_mscore
from .risk.earnings_quality import get_earnings_quality_score

# Import portfolio management tools
from .portfolio.performance_metrics import (
    get_beta_calculation,
    get_sharpe_ratio,
    get_var_calculation,
)

# Import technical analysis tools
from .technical.candlestick_patterns import get_candlestick_patterns
from .technical.crossover_signals import get_crossover_signals
from .technical.support_resistance import get_support_resistance_levels
from .technical.chart_patterns import get_chart_patterns
from .technical.fibonacci_tools import get_fibonacci_retracement

# Import P1 new tools
from .fundamentals.macro_tools import (
    get_macro_dashboard,
    get_yield_curve_analysis,
)
from .fundamentals.event_study import get_event_study
from .fundamentals.screening.multi_factor_screening import get_multi_factor_screening
from .fundamentals.valuation.comparable_valuation import get_comparable_company_valuation
from .risk.fraud_signals import get_financial_fraud_signals
from .portfolio.quant_tools import (
    get_efficient_frontier,
    get_monte_carlo_simulation,
    get_factor_attribution,
)

# A Class - Valuation Extension Tools
from .fundamentals.valuation.extended_valuation import (
    get_dcf_three_stage_valuation,
    get_ddm_valuation,
    get_residual_income_valuation,
    get_eva_valuation,
    get_fcff_fcfe_calculation,
    get_peg_valuation,
    get_graham_valuation,
    get_capm_cost_of_equity,
    get_growth_adjusted_valuation,
)

# A Class - Financial Risk Extension Tools
from .risk.extended_risk_models import (
    get_ohlson_oscore,
    get_receivables_quality,
    get_inventory_quality,
    get_liquidity_stress_test,
    get_debt_structure_analysis,
)

# A Class - Portfolio Extension Tool
from .portfolio.extended_performance import (
    get_sortino_ratio,
    get_treynor_ratio,
    get_information_ratio,
    get_calmar_ratio,
    get_jensen_alpha,
    get_portfolio_stress_test,
    get_scenario_analysis,
    get_brinson_attribution,
    get_sector_attribution,
)

# A Class - Advanced Technical Analysis Tools
from .technical.advanced_technical import (
    get_adx_trend_strength,
    get_macd_divergence,
    get_rsi_divergence,
    get_volume_price_divergence,
)
from .technical.volume_analysis import (
    get_vwap,
    get_obv_analysis,
    get_turnover_analysis,
    get_pivot_points,
    get_volume_profile,
    get_fibonacci_extension,
)

# A Class - Statistical Tools
from .fundamentals.statistical_tools import (
    get_correlation_matrix,
    get_cointegration_test,
    get_rolling_regression,
    get_normality_test,
    get_stationarity_test,
    get_garch_volatility,
)

# A Class-Filter Tool
from .fundamentals.screening.value_screening import (
    get_graham_screen,
    get_growth_stock_screen,
    get_dividend_stock_screen,
    get_turnaround_screen,
)

# B Class - Macrocycle Tools
from .fundamentals.macro_cycle_tools import (
    get_economic_cycle_position,
    get_monetary_environment,
    get_sector_rotation_signals,
)

# B Class - Bond Instrument
from .fundamentals.bond_tools import (
    get_bond_yield_calculation,
    get_credit_spread_analysis,
    get_bond_duration_convexity,
)

# B Class - Enhancement Tools
from .fundamentals.dividend_enhancement import (
    get_dividend_valuation_context,
    get_industry_valuation_distribution,
)
from .fundamentals.cashflow_enhancement import (
    get_cashflow_quality_deep,
    get_earnings_surprise_analysis,
)

__all__ = [
    'get_stock_market_data_unified',
    'get_stock_fundamentals_unified',
    'get_stock_news_unified',
    'get_stock_sentiment_unified',
    # Special financial analysis tools
    'get_income_analysis',
    'get_balance_sheet_analysis',
    'get_cashflow_analysis',
    'get_dividend_data',
    'get_main_business',
    'get_value_factor_bundle_tool',
    'get_quality_factor_bundle_tool',
    'get_growth_cashflow_factor_bundle_tool',
    'get_fundamental_factor_snapshot_tool',
    'get_historical_financial_annual_series_tool',
    'get_profitability_stability_metrics_tool',
    'get_cashflow_quality_trend_tool',
    'get_historical_valuation_percentile_tool',
    'get_technical_factor_bundle_tool',
    # Market/index analysis tools
    'get_index_data',
    'get_market_breadth',
    'get_market_environment',
    'identify_market_cycle',
    # Sector analysis tools
    'get_sector_data',
    'get_fund_flow_data',
    'get_peer_comparison',
    'analyze_sector',
    # Chip distribution analysis tool
    'get_chip_distribution',
    'get_chip_distribution_akshare_tool',
    'get_chip_distribution_tushare_tool',
    # Market-wide batch screening tool
    'screen_stocks_by_criteria',
    # Batch profit stability verification tool
    'batch_check_profit_consistency',
    # Valuation Model Tools
    'get_dcf_valuation',
    'get_wacc_calculation',
    # Risk scoring tool
    'get_altman_zscore',
    'get_piotroski_fscore',
    'get_beneish_mscore',
    'get_earnings_quality_score',
    # Portfolio Management Tools
    'get_beta_calculation',
    'get_sharpe_ratio',
    'get_var_calculation',
    # Advanced Tools for Technical Analysis
    'get_candlestick_patterns',
    'get_crossover_signals',
    'get_support_resistance_levels',
    'get_chart_patterns',
    'get_fibonacci_retracement',
    # P1-Macro/Events/Stock Picking
    'get_macro_dashboard',
    'get_yield_curve_analysis',
    'get_event_study',
    'get_multi_factor_screening',
    # P1-Valuation/Risk
    'get_comparable_company_valuation',
    'get_financial_fraud_signals',
    # P1-Combinatorial quantification
    'get_efficient_frontier',
    'get_monte_carlo_simulation',
    'get_factor_attribution',
    # A Class-ValuationExtension
    'get_dcf_three_stage_valuation',
    'get_ddm_valuation',
    'get_residual_income_valuation',
    'get_eva_valuation',
    'get_fcff_fcfe_calculation',
    'get_peg_valuation',
    'get_graham_valuation',
    'get_capm_cost_of_equity',
    'get_growth_adjusted_valuation',
    # A Class - Financial Risk Extension
    'get_ohlson_oscore',
    'get_receivables_quality',
    'get_inventory_quality',
    'get_liquidity_stress_test',
    'get_debt_structure_analysis',
    # A Class-combination extension
    'get_sortino_ratio',
    'get_treynor_ratio',
    'get_information_ratio',
    'get_calmar_ratio',
    'get_jensen_alpha',
    'get_portfolio_stress_test',
    'get_scenario_analysis',
    'get_brinson_attribution',
    'get_sector_attribution',
    # A Class - Advanced Technical Analysis
    'get_adx_trend_strength',
    'get_macd_divergence',
    'get_rsi_divergence',
    'get_volume_price_divergence',
    'get_vwap',
    'get_obv_analysis',
    'get_turnover_analysis',
    'get_pivot_points',
    'get_volume_profile',
    'get_fibonacci_extension',
    # A Class - Statistics
    'get_correlation_matrix',
    'get_cointegration_test',
    'get_rolling_regression',
    'get_normality_test',
    'get_stationarity_test',
    'get_garch_volatility',
    # A Class-Filter
    'get_graham_screen',
    'get_growth_stock_screen',
    'get_dividend_stock_screen',
    'get_turnaround_screen',
    # B Class - Macro Cycle
    'get_economic_cycle_position',
    'get_monetary_environment',
    'get_sector_rotation_signals',
    # B Class-Bond
    'get_bond_yield_calculation',
    'get_credit_spread_analysis',
    'get_bond_duration_convexity',
    # B class-enhancement
    'get_dividend_valuation_context',
    'get_industry_valuation_distribution',
    'get_cashflow_quality_deep',
    'get_earnings_surprise_analysis',
]

