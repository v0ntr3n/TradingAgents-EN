"""
工具配置和元数据定义
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolCategory(str, Enum):
    """工具类别"""
    MARKET = "market"           # market data
    FUNDAMENTALS = "fundamentals"  # fundamental data
    NEWS = "news"               # news data
    SOCIAL = "social"           # social media data
    TECHNICAL = "technical"     # technical analysis
    CHINA = "china"             # China market data
    TRADE_REVIEW = "trade_review"  # Transaction review
    ASSISTANT_OPS = "assistant_ops"  # Assistant operations (analysis triggering, report query, scheduled tasks, stock watch list management)
    SCREENING = "screening"     # Screening tools (batch screening, profit verification)
    UTILITY = "utility"         # Universal tools (Skill extension)
    KNOWLEDGE = "knowledge"     # Knowledge-based (Skill extension)
    MCP = "mcp"                 # MCP external tools
    EXTERNAL = "external"       # AI generated external Skill


class ToolTimeoutTier(str, Enum):
    """Tool timeout stratification: divided into light/medium/heavy based on execution time"""
    LIGHT = "light"    # DB Queries, list operations, etc. (15 seconds)
    MEDIUM = "medium"  # External API call (45 seconds)
    HEAVY = "heavy"    # Child Agent/Workflow Engine Execution (180 seconds)


TOOL_TIMEOUT_SECONDS: Dict[str, int] = {
    ToolTimeoutTier.LIGHT: 15,
    ToolTimeoutTier.MEDIUM: 45,
    ToolTimeoutTier.HEAVY: 180,
}


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None  # list of optional values


class ToolMetadata(BaseModel):
    """Tool metadata (aligned with Skill metadata, supports Function Calling)"""
    id: str                           # Tool unique identifier
    name: str                         # display name
    description: str                  # Description
    category: ToolCategory            # Tool category
    
    # Parameter definition
    parameters: List[ToolParameter] = Field(default_factory=list)
    
    # Source identification
    source: str = "builtin"           # builtin / generated / mcp / skill
    
    # Data source information
    data_source: str = ""             # Data source
    is_online: bool = True            # Do you need online access?
    # Data source processing method label (for Skill Workshop LLM to determine whether supplementary data sources are needed):
    #   "self_contained" - The tool is self-contained and has internally encapsulated data source calls (project data access layer / direct external API / hybrid multi-source / pure calculation / legacy bridge), which can be called directly by LLM
    #   "local_only"     - The tool only checks local MongoDB. If there is no local data, LLM may need to adjust external data sources to supplement it.
    #   "partial"        - The tool covers some requirements, and LLM may need to supplement other data sources or calculations
    data_source_handling: str = "self_contained"
    
    # Configuration
    timeout: int = 30                 # Timeout (seconds)—— Old fields, retained for compatibility
    timeout_tier: str = ToolTimeoutTier.MEDIUM  # Timeout layering:light / medium / heavy
    rate_limit: Optional[int] = None  # Frequency limit (calls per minute)
    
    # show
    icon: str = "🔧"
    color: str = "#95a5a6"
    
    # Function Calling Enhanced fields (aligned with Skill)
    when_to_use: str = ""             # When to use this tool
    when_not_to_use: str = ""         # Scenarios that should not be used
    returns: str = ""                 # Return value description
    example: str = ""                 # Call example
    related_tools: List[str] = Field(default_factory=list)  # Related tools
    limitations: str = ""             # Restrictions
    fc_enabled: bool = True           # Whether to enable Function Calling

    # Agent Builder Tool routing metadata: Used to distinguish primary, specialized, supplementary, general and downgraded tools.
    capability_tags: List[str] = Field(default_factory=list)
    tool_role_hint: str = ""          # primary / specialized / supporting / generic / fallback
    output_shape: str = ""            # structured_metrics / structured_records / report / text
    preferred_for: List[str] = Field(default_factory=list)
    not_replacement_for: List[str] = Field(default_factory=list)
    
    class Config:
        use_enum_values = True


# Built-in tool metadata
BUILTIN_TOOLS: Dict[str, ToolMetadata] = {
    # === Market data tools ===
    "get_stock_market_data_unified": ToolMetadata(
        id="get_stock_market_data_unified",
        name="统一市场数据",
        description="Obtain historical market data of stocks, including opening price, closing price, highest price, lowest price, trading volume, etc. Data can be expanded to include technical indicators. Supports A-shares, Hong Kong stocks, and US stocks.",
        category=ToolCategory.MARKET,
        data_source="yfinance/tushare",
        is_online=True,
        icon="📈",
        color="#2ecc71",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (supports A shares, Hong Kong stocks, and US stocks)", required=True),
            ToolParameter(name="start_date", type="string", description="Start date, format: YYYY-MM-DD. Note: The system automatically expands to the configured number of lookback days (usually 365 days), you only need to pass the analysis date", required=True),
            ToolParameter(name="end_date", type="string", description="End date, format: YYYY-MM-DD. Usually the same as start_date, just pass the current analysis date", required=True),
        ],
        when_to_use="Use it when you need to analyze stock price trends, trading volume, and historical K-line data. It is called when users inquire about the stock s rise and fall, recent trends, and historical data required for technical analysis.",
        when_not_to_use="Does not include the latest real-time price (needs to be combined with the market interface); does not include financial data (get_stock_fundamentals_unified should be used); is not suitable for fundamental risk detection such as goodwill impairment/abnormal accounts receivable/cash flow quality/risk events.",
        returns="Returns a market sequence containing open/high/low/close/volume and other fields, which may include technical indicators.(MA/MACD/RSI Wait). Financial accounts (goodwill, receivables turnover, cash flow details, etc.) are not included.",
        example="get_stock_market_data_unified(ticker='600519', start_date='2024-01-01', end_date='2024-12-31')",
        related_tools=["get_technical_indicators", "get_stock_fundamentals_unified"],
        capability_tags=["price", "volume", "ohlcv", "technical_indicators", "market_data"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["价格走势分析", "成交量分析", "技术指标计算"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "cashflow_quality", "risk_event_detection"],
    ),
    # ❌ Deleted: get_YFin_data_online (not implemented, use get_yfin_data_online_legacy)
    # ❌ Deleted: get_YFin_data (not implemented, use get_yfin_data_legacy)
    # ❌ Deleted: get_stockstats_indicators_report_online (not implemented, use get_stockstats_indicators_report_online_legacy)
    # ❌ Deleted: get_stockstats_indicators_report (not implemented, use get_stockstats_indicators_report_legacy)
    
    # === Fundamental Data Tools ===
    "get_stock_fundamentals_unified": ToolMetadata(
        id="get_stock_fundamentals_unified",
        name="统一基本面数据",
        description="Get core financial metrics for a stock, including price-to-earnings ratios(PE), price to book ratio(PB), ROE(ROE), Revenue growth rate, net profit growth rate, gross profit margin, asset-liability ratio, etc. The data source is the latest financial report.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="finnhub/simfin",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (supports A shares, Hong Kong stocks, and US stocks)", required=True),
            ToolParameter(name="start_date", type="string", description="Start date, format:YYYY-MM-DD", required=False),
            ToolParameter(name="end_date", type="string", description="End date, format:YYYY-MM-DD", required=False),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=False),
        ],
        when_to_use="Use it when you need to judge the fundamentals, valuation level, and financial status of a stock. It is called when users ask whether the valuation is expensive, whether the fundamentals are good, and whether the financial health is good.",
        when_not_to_use="It is not suitable for judging short-term trends (get_technical_indicators should be used); it does not include real-time prices (the market interface should be used); it is not suitable for special detection of goodwill impairment/accounts receivable anomalies/risk events.",
        returns="Returns a dictionary containing fields such as pe/pb/roe/revenue growth rate/profit growth rate/gross profit margin/asset-liability ratio. Excludes goodwill, accounts receivable turnover/aging details, and goodwill impairment history.",
        example="get_stock_fundamentals_unified(ticker='600519')",
        related_tools=["get_stock_market_data_unified", "get_peer_comparison"],
        capability_tags=["valuation", "profitability", "growth", "financial_health", "overview"],
        tool_role_hint="generic",
        output_shape="structured_metrics",
        preferred_for=["基本面快速概览", "估值水平判断", "核心财务指标查询"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "risk_event_detection", "cashflow_quality"],
    ),
    # ❌ Deleted: get_finnhub_company_insider_sentiment (not implemented, use get_finnhub_company_insider_sentiment_legacy)
    # ❌ Deleted: get_finnhub_company_insider_transactions (not implemented, use get_finnhub_company_insider_transactions_legacy)
    # ❌ Deleted: get_simfin_balance_sheet (not implemented, use get_simfin_balance_sheet_legacy)
    # ❌ Deleted: get_simfin_cashflow (not implemented, use get_simfin_cashflow_legacy)
    # ❌ Deleted: get_simfin_income_stmt (not implemented, use get_simfin_income_stmt_legacy)

    # === Specialized financial analysis tools (Tushare data) ===
    "get_income_analysis": ToolMetadata(
        id="get_income_analysis",
        name="利润表分析",
        description="Analyze core income statement indicators and multi-period trends of stocks such as revenue, profit, expenses, etc. The data source is Tushare income statement and financial indicators.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 600519, 000001)", required=True),
            ToolParameter(name="periods", type="integer", description="Number of analysis periods (most recent quarters), default 8", required=False, default=8),
        ],
        when_to_use="Used when users ask about revenue and profit growth, profit trends, and profitability. Such as'How is Moutai s revenue and profit growth?', 'Profit trends in recent years', 'What is the gross profit margin and net profit margin?'. ",
        when_not_to_use="Not applicable to asset and liability analysis (get_balance_sheet_analysis should be used); not applicable to cash flow analysis (get_cashflow_analysis should be used); not applicable to goodwill impairment/accounts receivable anomaly/risk event detection.",
        returns="Returns an income statement analysis report in Markdown format, including an overview of the latest period s revenue/profit/gross profit margin/net profit margin/expense structure, a multi-period revenue and profit trend table, and profitability trends. Excludes goodwill impairment and accounts receivable turnover/aging analysis.",
        example="get_income_analysis(ticker='600519', periods=8)",
        related_tools=["get_balance_sheet_analysis", "get_cashflow_analysis", "get_stock_fundamentals_unified"],
        capability_tags=["revenue", "profit", "margin", "expense_structure", "earnings_trend"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["利润趋势分析", "盈利能力评估", "费用结构分析"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "risk_event_detection", "cashflow_quality"],
    ),
    "get_balance_sheet_analysis": ToolMetadata(
        id="get_balance_sheet_analysis",
        name="资产负债表分析",
        description="Analyze the asset-liability structure, solvency, and financial health of the stock. Including asset-liability ratio, current ratio, quick ratio, etc.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="🏦",
        color="#2ecc71",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 600519, 000001)", required=True),
            ToolParameter(name="periods", type="integer", description="Number of analysis periods (most recent quarters), default 8", required=False, default=8),
        ],
        when_to_use="Used when users ask about debt-to-asset ratio, financial health, solvency, and cash reserves. Such as'Is the asset-liability ratio high?', 'Are cash reserves sufficient?', 'Is financial security'. ",
        when_not_to_use="Not suitable for profit analysis (get_income_analysis should be used); not suitable for cash flow analysis (get_cashflow_analysis should be used); not suitable for goodwill impairment risk assessment (this tool does not return the goodwill field); not suitable for accounts receivable anomaly detection (this tool only returns the balance of accounts receivable, and does not perform in-depth analysis of turnover rate/aging/bad debt coverage).",
        returns="Returns a balance sheet analysis report in Markdown format, including total assets, total liabilities, net assets, monetary funds, accounts receivable, inventory, fixed assets, goodwill (annual report data, quarterly reports may be empty), goodwill/net asset ratio, asset-liability ratio, current ratio, quick ratio, cash ratio, equity multiplier, current assets/non-current assets ratio, and multi-period asset trend table.",
        example="get_balance_sheet_analysis(ticker='600519', periods=8)",
        related_tools=["get_income_analysis", "get_cashflow_analysis", "get_stock_fundamentals_unified"],
        capability_tags=["solvency", "liquidity", "asset_structure", "debt_ratio", "goodwill"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["偿债能力评估", "流动性分析", "资产负债结构概览", "商誉规模查询（年报）"],
        not_replacement_for=["accounts_receivable_anomaly", "cashflow_quality", "profit_analysis"],
    ),
    "get_cashflow_analysis": ToolMetadata(
        id="get_cashflow_analysis",
        name="现金流量表分析",
        description="Analyze the operating/investing/financing cash flow of stocks and evaluate the health of cash flow and profit content. Contains free cash flow estimates.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="💰",
        color="#f39c12",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 600519, 000001)", required=True),
            ToolParameter(name="periods", type="integer", description="Number of analysis periods (most recent quarters), default 8", required=False, default=8),
        ],
        when_to_use="Used when users ask about operating cash flow, free cash flow, profit content, and whether cash flow is healthy. Such as'Is the operating cash flow good?', 'Is Free Cash Flow Generous?', 'How is the profit quality?'. ",
        when_not_to_use="Not applicable to profit analysis (get_income_analysis should be used); not applicable to asset and liability analysis (get_balance_sheet_analysis should be used); not applicable to goodwill impairment/accounts receivable anomaly/risk event detection.",
        returns="Returns a cash flow analysis report in Markdown format, including three categories of cash flow (operating/investing/financing) status, free cash flow estimation, cash flow quality assessment, and multi-period trends. Goodwill, accounts receivable turnover/aging, and risk event labels are not included.",
        example="get_cashflow_analysis(ticker='600519', periods=8)",
        related_tools=["get_income_analysis", "get_balance_sheet_analysis", "get_stock_fundamentals_unified"],
        capability_tags=["cashflow", "fcf", "operating_cashflow", "earnings_quality"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["现金流健康度评估", "利润含金量分析", "自由现金流估算"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "risk_event_detection"],
    ),
    "get_goodwill_analysis": ToolMetadata(
        id="get_goodwill_analysis",
        name="商誉分析",
        description="Analyze the size, proportion and change trend of goodwill of stocks, and assess the risk of goodwill impairment. Extract the goodwill field from the annual report balance sheet and calculate the goodwill/net assets ratio and year-on-year change.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="💎",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 002230, 600519, 000001)", required=True),
            ToolParameter(name="years", type="integer", description="Number of years to look back, default is 5 years", required=False, default=5),
        ],
        when_to_use="Used when users inquire about goodwill impairment risk, goodwill scale, and goodwill proportion. Such as'Is the goodwill high?', 'Is the risk of goodwill impairment significant?', 'What is the ratio of goodwill to net assets?'. ⚠️ This tool specifically extracts goodwill data from annual reports, and does not cause missing data due to null values in quarterly reports like balance sheet analysis.",
        when_not_to_use="Not suitable for profit analysis (should use get_income_analysis); not suitable for cash flow analysis (should use get_cashflow_analysis); not suitable for accounts receivable anomaly detection.",
        returns="Returns a goodwill analysis report in Markdown format, including the latest annual goodwill amount, goodwill/net assets ratio, goodwill/total assets ratio, risk signal (red/yellow/green), multi-year trend table, impairment signal detection (year-on-year decrease>20%automatically marked).",
        example="get_goodwill_analysis(ticker='002230', years=5)",
        related_tools=["get_balance_sheet_analysis", "get_risk_event_flags_tool", "get_financial_risk_factors"],
        capability_tags=["goodwill", "acquisition_premium", "impairment_risk", "annual_report"],
        tool_role_hint="specialized",
        output_shape="report",
        preferred_for=["商誉减值风险评估", "商誉规模查询", "商誉/净资产比率检查"],
        not_replacement_for=["profit_analysis", "accounts_receivable_anomaly", "cashflow_quality"],
    ),
    "get_dupont_analysis": ToolMetadata(
        id="get_dupont_analysis",
        name="杜邦分析",
        description="Conduct DuPont analysis on the stock and break down ROE into three factors (net interest rate×asset turnover rate×equity multiplier) and five factors (tax burden×interest burden×operating profit margin×asset turnover rate×Equity multiplier), supports multi-year trend comparison and identifies the core drivers of ROE.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="🔍",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 600519, 000001, 002230)", required=True),
            ToolParameter(name="years", type="integer", description="Number of years to look back, default is 5 years", required=False, default=5),
        ],
        when_to_use="Used when users ask about ROE breakdown, DuPont analysis, and earnings quality. Such as'ROE How did Gao do it?', 'DuPont analyzes', 'Does profit depend on profit margin or leverage?', 'How efficient is asset turnover?'. ",
        when_not_to_use="Not suitable for single-period profit query (get_income_analysis should be used); not suitable for valuation (get_value_factor_bundle_tool should be used).",
        returns="Returns the DuPont analysis report in Markdown format, including a three-factor breakdown table+ROE Verification, judgment of ROE driving factors (profit margin/turnover rate/leverage), five-factor disassembly (if operating profit data is available), and multi-year trend tables.",
        example="get_dupont_analysis(ticker='600519', years=5)",
        related_tools=["get_income_analysis", "get_balance_sheet_analysis", "get_stock_fundamentals_unified"],
        capability_tags=["roe_decomposition", "profitability", "asset_efficiency", "financial_leverage", "dupont"],
        tool_role_hint="specialized",
        output_shape="report",
        preferred_for=["ROE拆解", "杜邦分析", "盈利质量评估", "经营效率分析"],
        not_replacement_for=["valuation", "cashflow_analysis", "goodwill_impairment"],
    ),
    "get_dividend_data": ToolMetadata(
        id="get_dividend_data",
        name="分红送股数据",
        description="Obtain the historical dividend and share record of the stock, including cash dividend per share, bonus share conversion ratio, dividend year, implementation progress, etc. need Tushare 2000+ Points authority.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="🎁",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 600519, 000001)", required=True),
            ToolParameter(name="years", type="integer", description="Query the dividend records in recent years, default 5", required=False, default=5),
        ],
        when_to_use="Used when the user inquires about dividend status, dividend rate, bonus share conversion, and dividend ratio. Such as'Dividend distribution in recent years', 'What is the dividend rate?', 'What about the dividend ratio?', 'Are there any bonus shares?'. ",
        when_not_to_use="Not suitable for profit analysis (get_income_analysis should be used); not suitable for quick overview of fundamentals (get_stock_fundamentals_unified should be used); not suitable for risk detection such as goodwill impairment/accounts receivable anomalies/cash flow quality/risk events.",
        returns="Returns a dividend and share report in Markdown format, including dividend overview, annual dividend details (pre-tax/after-tax dividend, bonus share, transfer to increase, ex-rights date), and dividend trend judgment. Goodwill, accounts receivable turnover, cash flow details, and risk event labels are not included.",
        example="get_dividend_data(ticker='600519', years=5)",
        related_tools=["get_income_analysis", "get_stock_fundamentals_unified"],
        capability_tags=["dividend", "split", "dividend_yield", "shareholder_return"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["分红历史查询", "股息率分析", "股东回报评估"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "cashflow_quality", "risk_event_detection"],
    ),
    "get_main_business": ToolMetadata(
        id="get_main_business",
        name="主营业务构成",
        description="Obtain the main business revenue structure of the stock, and display the revenue, cost, gross profit margin and proportion of each business line by product/region dimension.",
        category=ToolCategory.FUNDAMENTALS,
        data_source="tushare",
        is_online=True,
        icon="🏢",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code, 6 digits (such as 600519, 000001)", required=True),
            ToolParameter(name="periods", type="integer", description="Number of analysis periods (the most recent reporting periods), default 4", required=False, default=4),
        ],
        when_to_use="Used when users ask about the main business structure, revenue source structure, and proportion of each product line. Such as'What is the main business', 'Income source composition', 'Which product contributes the most'. ",
        when_not_to_use="Not suitable for profit trend analysis (get_income_analysis should be used); not suitable for comprehensive fundamental overview (get_stock_fundamentals_unified should be used); not suitable for risk detection such as goodwill impairment/accounts receivable anomalies/cash flow quality/risk events.",
        returns="Returns the main business composition report in Markdown format, displaying the revenue, cost, gross profit margin and proportion of each business/product grouped by reporting period. Goodwill, accounts receivable turnover/aging, cash flow details, and risk event labels are not included.",
        example="get_main_business(ticker='600519', periods=4)",
        related_tools=["get_income_analysis", "get_stock_fundamentals_unified"],
        capability_tags=["revenue_composition", "business_segment", "product_mix", "regional_breakdown"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["收入结构分析", "业务分部评估", "产品/地区占比查询"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "cashflow_quality", "risk_event_detection"],
    ),

    # === News data tools ===
    "get_stock_news_unified": ToolMetadata(
        id="get_stock_news_unified",
        name="统一新闻数据",
        description="Get the latest news related to designated stocks, including company announcements, industry trends, policy impacts, etc. Supports A-shares, Hong Kong stocks, and US stocks.",
        category=ToolCategory.NEWS,
        data_source="finnhub/google",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (supports A shares, Hong Kong stocks, and US stocks)", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to know the news, good and bad news about a certain stock or event. Called when the user asks what news happened and what are the good and bad news.",
        when_not_to_use="Not suitable for searching news by keywords (some data sources support keywords); does not include social media discussions (get_stock_sentiment_unified should be used).",
        returns="Returns a news list, each containing fields such as title, summary, release time, source, etc.",
        example="get_stock_news_unified(ticker='600519', curr_date='2024-12-31')",
        related_tools=["get_stock_sentiment_unified", "get_stock_fundamentals_unified"],
    ),
    # ❌ Deleted: get_global_news_openai (not implemented, use get_global_news_openai_legacy)
    # ❌ Deleted: get_google_news (not implemented, use get_google_news_legacy)
    # ❌ Deleted: get_finnhub_news (not implemented, use get_finnhub_news_legacy)
    # ❌ Deleted: get_reddit_news (not implemented, use get_reddit_news_legacy)

    # === social media tools ===
    "get_stock_sentiment_unified": ToolMetadata(
        id="get_stock_sentiment_unified",
        name="统一情绪分析",
        description="Get the discussion sentiment and popularity of stocks on social media (such as Snowball, Stock Bar, Reddit, etc.). Used to understand market sentiment and retail investor attention.",
        category=ToolCategory.SOCIAL,
        data_source="reddit/twitter",
        is_online=True,
        icon="💬",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (supports A shares, Hong Kong stocks, and US stocks)", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to understand market sentiment, retail investor attention, and public opinion. It is called when users ask how popular the stock discussion is and what the market sentiment is.",
        when_not_to_use="Not suitable for getting news (get_stock_news_unified should be used); sentiment data has lag.",
        returns="Returns sentiment indicators, discussion popularity, positive and negative ratio, etc.",
        example="get_stock_sentiment_unified(ticker='600519', curr_date='2024-12-31')",
        related_tools=["get_stock_news_unified", "get_stock_market_data_unified"],
    ),
    # ❌ Deleted: get_stock_news_openai (not implemented, use get_stock_news_openai_legacy)
    # ❌ Deleted: get_reddit_stock_info (not implemented, use get_reddit_stock_info_legacy)

    # === china market tools ===
    # ❌ Deleted: get_china_stock_data (not implemented, please use get_stock_market_data_unified)
    # ❌ Deleted: get_china_fundamentals (not implemented, use get_stock_fundamentals_unified)
    # ❌ Deleted: get_sector_performance (not implemented, use get_sector_data instead)
    # ❌ Deleted: get_industry_comparison (not implemented, use get_peer_comparison instead)
    "get_index_data": ToolMetadata(
        id="get_index_data",
        name="指数数据",
        description="Obtain the historical market prices and moving average trends of major indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, Science and Technology Innovation 50, etc.). Used to analyze the technical aspects of the market.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📈",
        color="#1abc9c",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="lookback_days", type="integer", description="Number of days to look back, default is 60 days", required=False, default=60),
        ],
        when_to_use="Use it when you need index historical trends, moving average data, and market technical analysis. It is called when users inquire about the trend of the Shanghai Composite Index and the recent performance of the GEM.",
        when_not_to_use="Not available for individual stocks; use get_china_market_overview for a quick overview.",
        returns="Returns the major index market sequence, including opening high and low closing, trading volume, moving average, etc.",
        example="get_index_data(trade_date='2024-12-31', lookback_days=60)",
        related_tools=["get_china_market_overview", "get_index_technical", "get_market_overview"],
    ),
    "get_market_overview": ToolMetadata(
        id="get_market_overview",
        name="市场概览",
        description="Get an overview of the overall market environment, including comprehensive data such as major index trends, statistics on the number of rising and falling stocks, capital flows, market sentiment, etc. Suitable for judging the market environment.",
        category=ToolCategory.MARKET,
        data_source="multiple",
        is_online=True,
        icon="🌍",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to understand the market environment, the overall market performance, the number of rising and falling stocks, and the flow of funds. It is called when users ask how the market is and whether the market is good or not.",
        when_not_to_use="Not suitable for single stock analysis; not suitable for sector detailed data (get_sector_data should be used).",
        returns="Return to market overview data, including index rise and fall, number of gainers and losers, capital flow, etc.",
        example="get_market_overview(trade_date='2024-12-31')",
        related_tools=["get_china_market_overview", "get_index_data", "get_limit_stats"],
    ),
    # Added market analysis tools
    "get_north_flow": ToolMetadata(
        id="get_north_flow",
        name="北向资金流向",
        description="Obtain data on the northbound capital (foreign capital) flow of Shanghai-Shenzhen-Hong Kong Stock Connect, including net inflow/outflow, Shanghai-Hong Kong Stock Connect, and Shenzhen-Hong Kong Stock Connect details. Used to analyze foreign investment trends.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="💰",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="lookback_days", type="integer", description="Number of days to look back, default is 10 days", required=False, default=10),
        ],
        when_to_use="Use it when you need to know the movement of northbound funds and whether foreign capital flows in/out. Called when users inquire about northbound funds and foreign investment trends.",
        when_not_to_use="Not applicable to individual stock capital flows; not applicable to two-way financing (get_margin_trading should be used).",
        returns="Return to the northbound net inflow/outflow sequence, including Shanghai Stock Connect and Shenzhen Stock Connect.",
        example="get_north_flow(trade_date='2024-12-31')",
        related_tools=["get_margin_trading", "get_fund_flow_data", "get_market_overview"],
    ),
    "get_margin_trading": ToolMetadata(
        id="get_margin_trading",
        name="两融余额",
        description="Obtain margin data and securities lending balance data, and analyze the trends of leveraged funds (margin buying, securities lending and selling). Reflects market sentiment and leverage levels.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="lookback_days", type="integer", description="Number of days to look back, default is 10 days", required=False, default=10),
        ],
        when_to_use="Use it when you need to understand margin trading, leveraged fund trends, and market risk preferences. Called when the user inquires about the financing data and financing balance.",
        when_not_to_use="Not applicable to northbound funds (get_north_flow should be used); not applicable to individual stock fund flows.",
        returns="Returns the financing balance sequence, including financing balance, securities lending balance and their changes.",
        example="get_margin_trading(trade_date='2024-12-31')",
        related_tools=["get_north_flow", "get_fund_flow_data"],
    ),
    "get_limit_stats": ToolMetadata(
        id="get_limit_stats",
        name="涨跌停统计",
        description="Obtain statistics on the number of companies that have risen and fallen, and the number of companies that have risen and fallen, which can be used to evaluate market sentiment and the effect of making money. Higher daily limits usually indicate an active market.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📈",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to evaluate market sentiment, money-making effects, and the ratio of rising and falling stocks. It is called when the user asks how much the daily limit is today and what the market sentiment is.",
        when_not_to_use="Not applicable to single stock price limit information; not applicable to index data.",
        returns="Returns the number of companies with daily limit, the number of companies with lower limit, the number of companies with rise/fall, etc.",
        example="get_limit_stats(trade_date='2024-12-31')",
        related_tools=["get_market_overview", "get_market_breadth"],
    ),
    "get_index_technical": ToolMetadata(
        id="get_index_technical",
        name="指数技术指标",
        description="Obtain the technical indicators of major indexes (MACD, RSI, KDJ, etc.) and analyze the technical trends and signals of the market.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📉",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="lookback_days", type="integer", description="Number of days to look back, default is 60 days", required=False, default=60),
        ],
        when_to_use="Use it when you need to analyze the technical aspects of the market and the status of the index MACD/RSI/KDJ. Called when users inquire about the technical aspects of the Shanghai Composite Index and the RSI of the market.",
        when_not_to_use="Not applicable to individual stock technical indicators (get_technical_indicators should be used); not applicable to index market conditions (get_index_data should be used).",
        returns="Returns the index technical indicator sequence, such as macd, rsi, kdj, etc.",
        example="get_index_technical(trade_date='2024-12-31')",
        related_tools=["get_index_data", "get_technical_indicators", "get_market_overview"],
    ),
    "get_market_breadth": ToolMetadata(
        id="get_market_breadth",
        name="市场宽度",
        description="Analyze market width, including trading volume distribution, market capitalization distribution, rise and fall breadth, etc., to evaluate market health.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to analyze market breadth, trading volume structure, and distribution of increases and decreases. For advanced market environment analysis.",
        when_not_to_use="For a quick overview use get_market_overview; not suitable for single stock analysis.",
        returns="Returns data related to market width, including trading volume, rise and fall distribution, etc.",
        example="get_market_breadth(trade_date='2024-12-31')",
        related_tools=["get_market_overview", "get_limit_stats", "get_market_environment"],
    ),
    "get_market_environment": ToolMetadata(
        id="get_market_environment",
        name="市场环境",
        description="Comprehensive assessment of the market environment, including valuation levels, volatility, sentiment indicators, etc., to determine whether it is suitable to participate.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="🌐",
        color="#1abc9c",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="交易日期", required=True),
        ],
        when_to_use="Use it when you need to comprehensively evaluate the market environment, whether the valuation is reasonable, and the level of volatility. Used for timing and positioning recommendations.",
        when_not_to_use="Not suitable for single stock valuations (get_stock_fundamentals_unified should be used); for a quick overview use get_market_overview.",
        returns="Returns market environment assessment data, including valuation, volatility, etc.",
        example="get_market_environment(trade_date='2024-12-31')",
        related_tools=["identify_market_cycle", "get_market_overview", "get_market_breadth"],
    ),
    "identify_market_cycle": ToolMetadata(
        id="identify_market_cycle",
        name="市场周期识别",
        description="Identify the current cycle stage of the market (such as bull market, bear market, shock, etc.), which can be used as a reference for timing strategies.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="🔄",
        color="#e67e22",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="交易日期", required=True),
        ],
        when_to_use="Use it when you need to determine what stage the current market is in, a bull market or a bear market. Used for timing and positioning recommendations.",
        when_not_to_use="Not suitable for individual stock analysis; not suitable for short-term forecasting.",
        returns="Return to market cycle stage judgment and basis.",
        example="identify_market_cycle(trade_date='2024-12-31')",
        related_tools=["get_market_environment", "get_market_overview"],
    ),
    
    # === Automotive Industry Data Tools ===
    "get_auto_brand_monthly_sales": ToolMetadata(
        id="get_auto_brand_monthly_sales",
        name="汽车品牌月度销量",
        description="Query the sales of all models of a specified car brand in a certain month (Dongchedi national monthly sales list), and return the model ranking, monthly sales, price range and ranking changes.",
        category=ToolCategory.MARKET,
        data_source="dongchedi",
        is_online=True,
        icon="🚗",
        color="#e67e22",
        parameters=[
            ToolParameter(name="brand", type="string", description="Car brand name, such as Ask the world  BYD  ideal car , Support fuzzy matching", required=True),
            ToolParameter(name="month", type="string", description="Statistical month, format YYYYMM (such as 202608); it can also be passed as 500 (last half year)/1000 (last year) aggregation; if left blank, the latest complete month will be taken", required=False, default=""),
        ],
        when_to_use="It is used when you need to know the monthly sales of a certain car brand (or its models) and judge the terminal sales prosperity of the vehicle manufacturer. Suitable for research on the fundamentals and prosperity of stocks related to the automobile industry chain (complete vehicles/parts). Can be used for horizontal comparison of sales of multiple brands.",
        when_not_to_use="Does not provide stock price, valuation or financial data (get_stock_fundamentals_unified should be used); does not cover the full caliber of non-passenger vehicles (e.g. commercial vehicles, trucks); does not apply to non-automotive industries.",
        returns="Return to markdown report: total brand sales + Detailed list of car models (ranking/model/monthly sales/price range/last ranking/ranking changes), sorted by car model sales ranking.",
        example="get_auto_brand_monthly_sales(brand='Ask the world', month='202608')",
        related_tools=["get_sector_data", "get_stock_fundamentals_unified"],
        limitations="The data comes from the public list of Dianchedi, covering the retail sales of passenger car models; the list only includes models with sales, and models with extremely low sales or unlisted models may be missing.",
        capability_tags=["auto_sales", "brand_sales", "monthly_sales", "auto_industry", "dongchedi"],
        tool_role_hint="specialized",
        output_shape="report",
        preferred_for=["汽车品牌月度销量查询", "品牌旗下车型销量对比", "整车厂商销量跟踪"],
        not_replacement_for=["price_volume_analysis", "financial_statement_analysis"],
    ),

    # === Sector analysis tools ===
    "get_sector_data": ToolMetadata(
        id="get_sector_data",
        name="板块数据",
        description="Obtain performance data of the industry/sector to which the stock belongs, including sector gains and losses, capital flow, performance of individual stocks within the sector, etc. Used to analyze industry trends and sector rotation.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (such as 000001 or 000001.SZ)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="lookback_days", type="integer", description="Number of days to look back, default is 20 days", required=False, default=20),
        ],
        when_to_use="Use it when you know the specific stock code and need to know the performance of the sector to which the stock belongs. Note: This tool requires a ticker (ticker), if the user only mentions the sector/concept name without specifying individual stocks, analyze_sector_by_name or get_sector_daily should be used in preference (they accept the sector name keyword directly).",
        when_not_to_use="When the user only asks about sector trends but does not mention specific stocks, do not use this tool (use analyze_sector_by_name instead); it is not suitable for the overall market (get_market_overview should be used).",
        returns="Returns sector performance data, including rise and fall, capital flow, leader within the sector, etc.",
        example="get_sector_data(ticker='600519', trade_date='2024-12-31')",
        related_tools=["get_peer_comparison", "get_fund_flow_data", "analyze_sector",
                       "analyze_sector_by_name", "get_sector_daily"],
    ),
    "get_fund_flow_data": ToolMetadata(
        id="get_fund_flow_data",
        name="板块资金流向",
        description="Obtain capital flow data of industry sectors and concept sectors, and analyze the ranking of sectors with net inflows and outflows of main funds. What is returned is the capital flow at the sector level (not at the individual stock level), including the top industry sectors and the top concept sectors. Supports single-day snapshot and multi-day cumulative aggregation modes.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="💰",
        color="#3498db",
        parameters=[
            ToolParameter(name="trade_date", type="string", description="Closing date of transaction, format:YYYY-MM-DD", required=True),
            ToolParameter(name="top_n", type="integer", description="Returns the first N sections, default 10", required=False, default=10),
            ToolParameter(name="lookback_days", type="integer",
                         description="Number of days to look back:1=Snapshot of the day only,7=Cumulatively in the past week,30=Accumulated over the past month. User asked'Last week/month'The corresponding number of days should be passed. Default 1",
                         required=False, default=1),
        ],
        when_to_use="When the user asks'Which sectors have the most capital inflows?', 'Sector net capital inflow ranking', 'Hot sectors', 'Fund flow'when used. If the user asks'Sector rotation in the last week/month', Lookback_days should be set to 7 or 30 to obtain multi-day cumulative data. Returns the capital flow ranking in two dimensions: industry sector and concept sector.",
        when_not_to_use="Not applicable to northbound funds (get_north_flow should be used); not applicable to individual stock level capital flows; not applicable to margin financing data (get_margin_trading should be used).",
        returns="Single-day mode: Returns the day s sector capital flow ranking (sector name, net inflow of 100 million yuan, increase or decrease, leading stocks). Multi-day mode: Returns the cumulative net inflow ranking (sector name, cumulative net inflow in billions of yuan, average daily net inflow, net inflow days/total days, average increase or decrease), and can analyze sector rotation trends and capital continuity.",
        example="get_fund_flow_data(trade_date='2026-02-13', top_n=10, lookback_days=30)",
        related_tools=["get_sector_data", "get_north_flow", "get_margin_trading",
                       "analyze_sector_by_name", "get_sector_daily"],
    ),
    "get_peer_comparison": ToolMetadata(
        id="get_peer_comparison",
        name="同业对比",
        description="Obtain comparative data on stocks in the same industry and analyze the relative position of individual stocks in the industry. Support multi-dimensional comparison: valuation(PE/PB), Growth, market value, etc.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📈",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (such as 000001 or 000001.SZ)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="top_n", type="integer", description="Returns the top N peer stocks, default 10", required=False, default=10),
        ],
        when_to_use="Use it when you need to compare stocks in the same industry, understand the position of individual stocks in the industry, and select stocks. It is called when users ask which is better, Moutai or Wuliangye, and which stocks are in the same sector.",
        when_not_to_use="Not suitable for cross-industry comparison; not suitable for in-depth analysis of single stocks; not suitable for fundamental risk detection such as goodwill impairment/abnormal accounts receivable/cash flow quality/risk events.",
        returns="Return to peer stock list and comparison data, including valuation and market indicators such as PE, PB, market capitalization, increase and decrease. Goodwill, accounts receivable turnover, cash flow details, and risk event labels are not included.",
        example="get_peer_comparison(ticker='600519', trade_date='2024-12-31', top_n=10)",
        related_tools=["get_sector_data", "get_stock_fundamentals_unified"],
        capability_tags=["peer_comparison", "valuation", "market_cap", "sector_ranking"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["同业估值对比", "行业排名", "选股筛选"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "cashflow_quality", "risk_event_detection"],
    ),
    "analyze_sector": ToolMetadata(
        id="analyze_sector",
        name="综合板块分析",
        description="Comprehensive analysis of the sectors to which stocks belong, aggregating sector performance, capital flows, peer comparisons, etc., to provide one-stop sector analysis.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="🔍",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (such as 000001 or 000001.SZ)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="When it is necessary to conduct a complete sector analysis of a certain stock and combine the sectors+Peers+funds are used. Alternative to multiple calls to get_sector_data and get_peer_comparison.",
        when_not_to_use="Use get_sector_data when you only need data from a single sector; use get_peer_comparison when you only need peer comparison.",
        returns="Returns comprehensive sector analysis results, including sector performance, capital flow, peer comparison, etc.",
        example="analyze_sector(ticker='600519', trade_date='2024-12-31')",
        related_tools=["get_sector_data", "get_peer_comparison", "get_fund_flow_data",
                       "analyze_sector_by_name"],
    ),

    # === Section level tools (use the section name as the entry, no ticker required) ===
    "search_sector": ToolMetadata(
        id="search_sector",
        name="板块搜索",
        description="Search A-share sectors (industry/concept/region) by name keywords and return matching sector lists and codes. Support fuzzy matching, such as search'Xiaomi'can be found'Xiaomi concept'and'Xiaomi car'. ",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="🔍",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="keyword", type="string", description="Sector name keywords (such as photovoltaic, semiconductor, liquor, Xiaomi, Huawei)", required=True),
            ToolParameter(name="sector_type", type="string", description="Section type: N=Industry (including concept sections), S=statistical concepts, R=Region, default N", required=False, default="N"),
        ],
        when_to_use="Use it when you need to find the section code, confirm whether the section exists, or fuzzy search the section name. It is usually used as a pre-step for other section tools, but get_sector_daily/get_sector_constituents/analyze_sector_by_name has been automatically searched internally, and generally does not need to be called separately.",
        when_not_to_use="There is no need to tune this tool first and then tune analyze_sector_by_name, which has built-in search. Not suitable for obtaining sector quotes or constituent stocks (corresponding tools should be used).",
        returns="Returns a list of matching sections, including section codes(ts_code), Sector name, number of constituent stocks.",
        example="search_sector(keyword='Xiaomi', sector_type='N')",
        related_tools=["get_sector_daily", "get_sector_constituents", "analyze_sector_by_name"],
    ),
    "get_sector_daily": ToolMetadata(
        id="get_sector_daily",
        name="板块行情",
        description="Obtain the daily market data of the sector index (by sector name), including closing price, increase or decrease, trading volume, turnover rate, total market value, etc. Directly reflects the overall trend of the sector, without the need to query individual stocks one by one.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📊",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="sector_name", type="string", description="Sector name keywords (such as photovoltaics, semiconductors, liquor, Xiaomi cars)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="lookback_days", type="integer", description="Number of days to look back, default is 20 days", required=False, default=20),
        ],
        when_to_use="When the user asks'XX How is the sector/concept/industry trending recently?', 'XX How much has the sector risen?'when used. Sectors have their own index prices (increase and decrease, trading volume, turnover rate). You can directly adjust this tool to get the overall trend of the sector, without the need to query individual stock prices one by one.",
        when_not_to_use="It is not suitable for querying the list of sector constituent stocks (get_sector_constituents should be used); it is not suitable for individual stock quotes (get_stock_market_data_unified should be used). If you need one-stop sector analysis (market trends+Constituent stocks+funds), it is more efficient to use analyze_sector_by_name.",
        returns="Return to the sector index market report, including the latest closing price, increase or decrease, trading volume, turnover rate, total market value, and a summary of recent trends.",
        example="get_sector_daily(sector_name='Xiaomi car', trade_date='2026-02-13')",
        related_tools=["search_sector", "get_sector_constituents", "analyze_sector_by_name", "get_fund_flow_data"],
    ),
    "get_sector_constituents": ToolMetadata(
        id="get_sector_constituents",
        name="板块成分股",
        description="Get the list of sector constituent stocks and their market capitalization and valuation rankings (by sector name). Used to check which stocks are in a certain industry/concept sector and who are the leading stocks.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📋",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="sector_name", type="string", description="Sector name keywords (such as photovoltaics, semiconductors, liquor, Xiaomi cars)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="top_n", type="integer", description="Returns the top N constituent stocks (sorted by market capitalization), default 15", required=False, default=15),
        ],
        when_to_use="When the user asks'XX What are concept stocks?', 'XX Sector leading stocks', 'XX Concept stock list'when used. Just pass in the concept keywords directly, no ticker is needed.",
        when_not_to_use="Not suitable for viewing the overall trend of the sector (get_sector_daily should be used); if you need market information+Components together, use analyze_sector_by_name.",
        returns="Returns the list of sector constituent stocks, including stock code, name, market value, PE/PB valuation, etc., sorted by market value.",
        example="get_sector_constituents(sector_name='Xiaomi car', trade_date='2026-02-13', top_n=15)",
        related_tools=["search_sector", "get_sector_daily", "analyze_sector_by_name"],
    ),
    "analyze_sector_by_name": ToolMetadata(
        id="analyze_sector_by_name",
        name="板块综合分析（按名称）",
        description="Conduct one-stop comprehensive analysis by sector name, integrating sector index trends (increase/loss/trading volume/turnover rate), leading constituent stocks, and market-wide capital flows. One call to answer'XX What about sectors/concepts?'problems without having to call other tools multiple times.",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="🏷️",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="sector_name", type="string", description="Sector name keywords (such as photovoltaic, semiconductor, liquor, Xiaomi Auto, Huawei Concept)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="When the user asks'XX How about the sector/concept/industry?', 'XX Concept stock trends', 'XX Sector investment opportunities', 'XX Industry prospects'priority when using. This is the preferred one-stop tool for sector analysis, returning sector quotes in one call+leading stocks+Fund flow to avoid wasting tool rounds with multiple calls.",
        when_not_to_use="It is not suitable for in-depth analysis of individual stocks (individual stock tools should be used); if you only need the list of constituent stocks without market prices, you can use get_sector_constituents alone.",
        returns="Return to the comprehensive analysis report of the sector, including: sector index prices (closing price, increase or decrease, trading volume, turnover rate, market capitalization), recent trends, list of leading constituent stocks (sorted by market capitalization), and ranking of capital flows of all market sectors.",
        example="analyze_sector_by_name(sector_name='Xiaomi car', trade_date='2026-02-13')",
        related_tools=["search_sector", "get_sector_daily", "get_sector_constituents", "get_fund_flow_data"],
    ),

    # === Technical indicator tools ===
    "get_technical_indicators": ToolMetadata(
        id="get_technical_indicators",
        name="统一技术指标分析",
        description="Get various technical indicators of stocks, including MACD, RSI, KDJ, Bollinger Bands(BOLL)wait. Used to determine short-term trends, buying and selling signals, overbought and oversold. Supports A-shares/Hong Kong stocks/US stocks.",
        category=ToolCategory.TECHNICAL,
        data_source="multiple",
        is_online=True,
        icon="📉",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (supports A shares, Hong Kong stocks, and US stocks)", required=True),
            ToolParameter(name="indicators", type="string", description="List of technical indicators, separated by commas, such as 'macd,rsi_14,boll,kdj'", required=True),
            ToolParameter(name="start_date", type="string", description="Start date, format: YYYY-MM-DD. Usually the year before the analysis date to ensure there is enough data to calculate the indicator", required=False),
            ToolParameter(name="end_date", type="string", description="End date, format: YYYY-MM-DD. Usually the date of analysis", required=False),
        ],
        when_to_use="Use it when you need to judge short-term stock trends, technical signals, overbought and oversold. Called when the user asks about the technical situation and the status of MACD/RSI/KDJ.",
        when_not_to_use="Not suitable for fundamental analysis (get_stock_fundamentals_unified should be used); not suitable for macro market environment (get_market_overview should be used); not suitable for fundamental risk detection such as goodwill impairment/abnormal accounts receivable/cash flow quality/risk events.",
        returns="Returns the numerical sequence of each technical indicator, such as macd/macd_signal/rsi/kdj, etc. Financial accounts (goodwill, receivables turnover, cash flow, etc.) and risk event labels are not included.",
        example="get_technical_indicators(ticker='600519', indicators='macd,rsi_14,kdj')",
        related_tools=["get_stock_market_data_unified", "get_stock_fundamentals_unified"],
        capability_tags=["macd", "rsi", "kdj", "bollinger", "technical_analysis"],
        tool_role_hint="supporting",
        output_shape="report",
        preferred_for=["短期走势判断", "买卖信号识别", "超买超卖评估"],
        not_replacement_for=["goodwill_impairment", "accounts_receivable_anomaly", "cashflow_quality", "risk_event_detection"],
    ),
    
    # === china market tools ===
    "get_china_market_overview": ToolMetadata(
        id="get_china_market_overview",
        name="中国市场概览",
        description="Get an overview of the major indexes in China s stock market, including Shanghai Composite Index, Shenzhen Composite Component Index, GEM Index, Science and Technology Innovation 50, etc. Contains increases and decreases and brief trends.",
        category=ToolCategory.CHINA,
        data_source="tushare",
        is_online=True,
        icon="🇨🇳",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to quickly understand the performance of the A-share market and the rise and fall of major indexes. It is called when users ask how the market is doing today and how much the Shanghai Composite Index has risen.",
        when_not_to_use="Does not contain individual stock data; does not contain sector data (get_sector_data should be used).",
        returns="Returns the main index quotes, including index code, increase or decrease, closing price, etc.",
        example="get_china_market_overview(curr_date='2024-12-31')",
        related_tools=["get_market_overview", "get_index_data"],
    ),
    
    # === Transaction review tool ===
    "get_trade_records": ToolMetadata(
        id="get_trade_records",
        name="获取交易记录",
        description="Obtain transaction records from the database and support user positions(position_changes)and simulated trading(paper_trades)",
        category=ToolCategory.TRADE_REVIEW,
        data_source="database",
        is_online=False,
        timeout_tier=ToolTimeoutTier.LIGHT,
        data_source_handling="local_only",
        icon="📋",
        color="#95a5a6",
        parameters=[
            ToolParameter(name="user_id", type="string", description="用户ID", required=True),
            ToolParameter(name="trade_ids", type="array", description="交易ID列表", required=True),
            ToolParameter(name="source", type="string", description="data source: 'real'(User positions) or 'paper'(simulated trading)", required=False, default="real"),
        ],
    ),
    "build_trade_info": ToolMetadata(
        id="build_trade_info",
        name="构建交易信息",
        description="Build a complete transaction information object from transaction records, including statistical data and time information",
        category=ToolCategory.TRADE_REVIEW,
        data_source="internal",
        is_online=False,
        timeout_tier=ToolTimeoutTier.LIGHT,
        icon="🔧",
        color="#95a5a6",
        parameters=[
            ToolParameter(name="trade_records", type="array", description="交易记录列表", required=True),
            ToolParameter(name="code", type="string", description="股票代码（可选）", required=False),
        ],
    ),
    "get_account_info": ToolMetadata(
        id="get_account_info",
        name="获取账户信息",
        description="Obtain the user s capital account information, including cash, market value of positions, total assets, etc.",
        category=ToolCategory.TRADE_REVIEW,
        data_source="database",
        is_online=False,
        timeout_tier=ToolTimeoutTier.LIGHT,
        data_source_handling="local_only",
        icon="💳",
        color="#95a5a6",
        parameters=[
            ToolParameter(name="user_id", type="string", description="用户ID", required=True),
        ],
    ),
    "get_market_snapshot_for_review": ToolMetadata(
        id="get_market_snapshot_for_review",
        name="获取市场快照",
        description="Obtain K-line data and market snapshots during the trading period for review analysis",
        category=ToolCategory.TRADE_REVIEW,
        data_source="multiple",
        is_online=True,
        icon="📸",
        color="#95a5a6",
        parameters=[
            ToolParameter(name="code", type="string", description="股票代码", required=True),
            ToolParameter(name="market", type="string", description="market: 'CN'(A shares) or 'US'(US stocks)", required=True),
            ToolParameter(name="start_date", type="string", description="start date YYYY-MM-DD", required=False),
            ToolParameter(name="end_date", type="string", description="end date YYYY-MM-DD", required=False),
        ],
    ),
    
    # === Legacy Tools (compatible with legacy interfaces)===
    # News
    "get_reddit_news_legacy": ToolMetadata(
        id="get_reddit_news_legacy",
        name="Reddit global news (Legacy)",
        description="Get global news aggregation on Reddit (legacy interface)",
        category=ToolCategory.NEWS,
        data_source="reddit",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_finnhub_news_legacy": ToolMetadata(
        id="get_finnhub_news_legacy",
        name="Finnhub financial news (Legacy)",
        description="Get news about a specific stock from Finnhub (legacy interface)",
        category=ToolCategory.NEWS,
        data_source="finnhub",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="start_date", type="string", description="Start date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="end_date", type="string", description="End date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_google_news_legacy": ToolMetadata(
        id="get_google_news_legacy",
        name="Google News search (Legacy)",
        description="Search news for specific keywords through Google News (old interface)",
        category=ToolCategory.NEWS,
        data_source="google",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="query", type="string", description="搜索关键词", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_realtime_stock_news_legacy": ToolMetadata(
        id="get_realtime_stock_news_legacy",
        name="Live stock news (Legacy)",
        description="Get real-time news analysis of stocks (old version interface)",
        category=ToolCategory.NEWS,
        data_source="multiple",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_stock_news_openai_legacy": ToolMetadata(
        id="get_stock_news_openai_legacy",
        name="OpenAI Stock news analysis (Legacy)",
        description="Obtain and analyze stock news using the OpenAI interface (legacy interface)",
        category=ToolCategory.NEWS,
        data_source="openai",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_global_news_openai_legacy": ToolMetadata(
        id="get_global_news_openai_legacy",
        name="OpenAI Macro News Analysis (Legacy)",
        description="Obtain and analyze macroeconomic news using the OpenAI interface (legacy interface)",
        category=ToolCategory.NEWS,
        data_source="openai",
        is_online=True,
        icon="📰",
        color="#9b59b6",
        parameters=[
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    
    # social-emotional
    "get_reddit_stock_info_legacy": ToolMetadata(
        id="get_reddit_stock_info_legacy",
        name="Reddit stock discussion (Legacy)",
        description="Get discussion information about a specific stock on Reddit (legacy interface)",
        category=ToolCategory.SOCIAL,
        data_source="reddit",
        is_online=True,
        icon="💬",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_chinese_social_sentiment_legacy": ToolMetadata(
        id="get_chinese_social_sentiment_legacy",
        name="Chinese social sentiment (Legacy)",
        description="Get stock sentiment from Chinese social media (Xueqiu, Stock Bar, etc.) (old version interface)",
        category=ToolCategory.SOCIAL,
        data_source="chinese_social",
        is_online=True,
        icon="💬",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    
    # Market conditions
    "get_china_market_overview_legacy": ToolMetadata(
        id="get_china_market_overview_legacy",
        name="China market overview (Legacy)",
        description="Get an overview of major Chinese stock market indexes (old version interface)",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📈",
        color="#2ecc71",
        parameters=[
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_yfin_data_legacy": ToolMetadata(
        id="get_yfin_data_legacy",
        name="Yahoo Finance data (Legacy)",
        description="Get stock price data from Yahoo Finance (legacy interface)",
        category=ToolCategory.MARKET,
        data_source="yfinance",
        is_online=False,
        icon="📈",
        color="#2ecc71",
        parameters=[
            ToolParameter(name="symbol", type="string", description="股票代码", required=True),
            ToolParameter(name="start_date", type="string", description="Start date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="end_date", type="string", description="End date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_yfin_data_online_legacy": ToolMetadata(
        id="get_yfin_data_online_legacy",
        name="Yahoo Finance real time data (Legacy)",
        description="Get real-time stock price data from Yahoo Finance (legacy interface)",
        category=ToolCategory.MARKET,
        data_source="yfinance",
        is_online=True,
        icon="📈",
        color="#2ecc71",
        parameters=[
            ToolParameter(name="symbol", type="string", description="股票代码", required=True),
            ToolParameter(name="start_date", type="string", description="Start date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="end_date", type="string", description="End date, format:YYYY-MM-DD", required=True),
        ],
    ),
    
    # Technical analysis
    "get_stockstats_indicators_report_legacy": ToolMetadata(
        id="get_stockstats_indicators_report_legacy",
        name="Technical indicator report (Stockstats/Legacy)",
        description="Generate analysis reports for specific technical indicators (old version interface)",
        category=ToolCategory.TECHNICAL,
        data_source="stockstats",
        is_online=False,
        icon="📉",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="symbol", type="string", description="股票代码", required=True),
            ToolParameter(name="indicator", type="string", description="技术指标名称", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="look_back_days", type="integer", description="The number of days to look back, the default is 30 days", required=False, default=30),
        ],
    ),
    "get_stockstats_indicators_report_online_legacy": ToolMetadata(
        id="get_stockstats_indicators_report_online_legacy",
        name="Real-time technical indicator reporting (Stockstats/Online/Legacy)",
        description="Generate real-time analysis reports of specific technical indicators (old version interface)",
        category=ToolCategory.TECHNICAL,
        data_source="stockstats",
        is_online=True,
        icon="📉",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="symbol", type="string", description="股票代码", required=True),
            ToolParameter(name="indicator", type="string", description="技术指标名称", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
            ToolParameter(name="look_back_days", type="integer", description="The number of days to look back, the default is 30 days", required=False, default=30),
        ],
    ),
    
    # Fundamentals
    "get_finnhub_company_insider_sentiment_legacy": ToolMetadata(
        id="get_finnhub_company_insider_sentiment_legacy",
        name="insider sentiment (Finnhub/Legacy)",
        description="Get the trading sentiment of company insiders (old version interface)",
        category=ToolCategory.FUNDAMENTALS,
        data_source="finnhub",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_finnhub_company_insider_transactions_legacy": ToolMetadata(
        id="get_finnhub_company_insider_transactions_legacy",
        name="insider trading (Finnhub/Legacy)",
        description="Obtain specific transaction records of company insiders (old version interface)",
        category=ToolCategory.FUNDAMENTALS,
        data_source="finnhub",
        is_online=True,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_simfin_income_stmt_legacy": ToolMetadata(
        id="get_simfin_income_stmt_legacy",
        name="income statement (SimFin/Legacy)",
        description="Get company income statement data (old version interface)",
        category=ToolCategory.FUNDAMENTALS,
        data_source="simfin",
        is_online=False,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="freq", type="string", description="Frequency: 'Q'(quarter) or 'A'(annual)", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_simfin_balance_sheet_legacy": ToolMetadata(
        id="get_simfin_balance_sheet_legacy",
        name="balance sheet (SimFin/Legacy)",
        description="Get company balance sheet data (old version interface)",
        category=ToolCategory.FUNDAMENTALS,
        data_source="simfin",
        is_online=False,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="freq", type="string", description="Frequency: 'Q'(quarter) or 'A'(annual)", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),
    "get_simfin_cashflow_legacy": ToolMetadata(
        id="get_simfin_cashflow_legacy",
        name="cash flow statement (SimFin/Legacy)",
        description="Get company cash flow statement data (old version interface)",
        category=ToolCategory.FUNDAMENTALS,
        data_source="simfin",
        is_online=False,
        icon="📊",
        color="#3498db",
        parameters=[
            ToolParameter(name="ticker", type="string", description="股票代码", required=True),
            ToolParameter(name="freq", type="string", description="Frequency: 'Q'(quarter) or 'A'(annual)", required=True),
            ToolParameter(name="curr_date", type="string", description="Current date, format:YYYY-MM-DD", required=True),
        ],
    ),

    # === Chip distribution tool ===
    "get_chip_distribution": ToolMetadata(
        id="get_chip_distribution",
        name="筹码分布",
        description="Obtain stock chip distribution data and analyze profit ratio, average cost and chip concentration. Data source: AkShare (preferred)→ Tushare (spare).",
        category=ToolCategory.MARKET,
        data_source="akshare/tushare",
        is_online=True,
        icon="📊",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (such as 000001 or 000001.SZ)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="It is used when users need to understand the distribution of stock chips, position cost structure, profit ratio, and hold-up distribution. Called when analyzing market games, main costs, and support pressure.",
        when_not_to_use="Not suitable for analyzing real-time price movements (get_stock_market_data_unified should be used); does not contain financial data (fundamental tools should be used).",
        returns="Returns the chip distribution analysis report, including profit ratio, average cost, 90%/70% chip interval and concentration index.",
        example="get_chip_distribution(ticker='000001', trade_date='2024-01-05')",
        related_tools=["get_stock_market_data_unified", "get_technical_indicators"],
    ),
    "get_chip_distribution_akshare": ToolMetadata(
        id="get_chip_distribution_akshare",
        name="Chip distribution(AkShare)",
        description="Obtain stock chip distribution data (free data source) through the AkShare Oriental Wealth Data Interface.",
        category=ToolCategory.MARKET,
        data_source="akshare",
        is_online=True,
        icon="📊",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (such as 000001 or 000001.SZ)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to use free data sources to obtain A-share chip distribution data.",
        returns="Returns a JSON string containing fields such as profit ratio, average cost, chip concentration, etc.",
    ),
    "get_chip_distribution_tushare": ToolMetadata(
        id="get_chip_distribution_tushare",
        name="Chip distribution(Tushare)",
        description="Obtain stock chip distribution data through Tushare official API (requires 5000 points permission).",
        category=ToolCategory.MARKET,
        data_source="tushare",
        is_online=True,
        icon="📊",
        color="#e74c3c",
        parameters=[
            ToolParameter(name="ticker", type="string", description="Stock code (such as 000001 or 000001.SZ)", required=True),
            ToolParameter(name="trade_date", type="string", description="Transaction date, format:YYYY-MM-DD", required=True),
        ],
        when_to_use="Use it when you need to use Tushare official data to obtain A-share chip distribution data (5,000 points required).",
        returns="Returns a JSON string containing profit ratio, weighted average cost, and each percentile cost price.",
    ),
}

