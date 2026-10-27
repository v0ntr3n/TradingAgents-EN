"""
Seed process definition

Predefined analysis templates as a deterministic floor mechanism.
Each seed process contains:
- id: unique identifier
- name: display name
- description: Semantic description (for LLM matching)
- steps: Predefined tool calling steps (with placeholders)
- extensible: Whether to allow LLM append steps

Issue 1: Code embedded, similar BUILTIN_TOOLS
Phase 2: Migrate to MongoDB analysis_flow_templates collection
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SeedFlowStep(BaseModel):
    """Seed Process Steps Template"""
    tool: str = Field(..., description="Tools ID")
    args_template: Dict[str, str] = Field(default_factory=dict, description="Parameter template, support {ticker} {curr_date} {trade_date} placeholder")
    intent: str = Field("", description="Step intention description")
    depends_on: List[int] = Field(default_factory=list, description="Dependent step index (0-based)")


class SeedFlow(BaseModel):
    """Seed process definition"""
    id: str = Field(..., description="unique identifier")
    name: str = Field(..., description="display name")
    description: str = Field(..., description="Semantic description for LLM matching")
    steps: List[SeedFlowStep] = Field(default_factory=list)
    extensible: bool = Field(True, description="Whether to allow LLM append steps")


# ============================================================
# Built-in seed process
# ============================================================

BUILTIN_SEED_FLOWS: Dict[str, SeedFlow] = {

    "earnings_disclosure_date": SeedFlow(
        id="earnings_disclosure_date",
        name="Financial report disclosure time inquiry",
        description="Query the disclosure time of a company s financial reports over the years and infer the approximate disclosure window of the current year s annual report",
        steps=[
            SeedFlowStep(
                tool="get_stock_fundamentals_unified",
                args_template={"ticker": "{ticker}", "curr_date": "{curr_date}"},
                intent="Get financial data, view reporting periods and disclosures",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_stock_news_unified",
                args_template={"ticker": "{ticker}", "curr_date": "{curr_date}"},
                intent="Query financial report scheduled disclosure announcement",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "stock_overview": SeedFlow(
        id="stock_overview",
        name="Comprehensive overview of individual stocks",
        description="Comprehensive quick overview of individual stocks, obtain comprehensive information such as fundamentals, market trends, news, etc., and quickly understand the overall situation of a stock",
        steps=[
            SeedFlowStep(
                tool="get_stock_fundamentals_unified",
                args_template={"ticker": "{ticker}", "curr_date": "{curr_date}"},
                intent="Obtain fundamental data (PE/PB/ROE/revenue, etc.)",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_stock_market_data_unified",
                args_template={"ticker": "{ticker}", "start_date": "{curr_date}", "end_date": "{curr_date}"},
                intent="Get recent market trends and trading volumes",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_stock_news_unified",
                args_template={"ticker": "{ticker}", "curr_date": "{curr_date}"},
                intent="Get the latest news",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_technical_indicators",
                args_template={"ticker": "{ticker}", "indicators": "macd,rsi_14,boll,kdj", "end_date": "{curr_date}"},
                intent="Obtain technical indicators (MACD/RSI/KDJ) to determine short-term trends",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "sector_screening": SeedFlow(
        id="sector_screening",
        name="Sector analysis",
        description="Sector analysis and stock selection within the sector, check the market trends, leading constituent stocks, capital flows of a certain sector, and analyze investment opportunities in the sector",
        steps=[
            SeedFlowStep(
                tool="analyze_sector_by_name",
                args_template={"sector_name": "{sector_name}", "trade_date": "{trade_date}"},
                intent="Comprehensive analysis of sector trends, leading component stocks and capital flows",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "event_impact": SeedFlow(
        id="event_impact",
        name="Event Impact Analysis",
        description="Analysis of the impact of specific events on relevant stocks or sectors, such as policy changes, RRR cuts and interest rate cuts, industry events, etc.",
        steps=[
            SeedFlowStep(
                tool="get_stock_news_unified",
                args_template={"ticker": "{ticker}", "curr_date": "{curr_date}"},
                intent="Get news and announcements about events",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_sector_data",
                args_template={"ticker": "{ticker}", "trade_date": "{trade_date}"},
                intent="Obtain performance data for affected sectors",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_stock_market_data_unified",
                args_template={"ticker": "{ticker}", "start_date": "{curr_date}", "end_date": "{curr_date}"},
                intent="Obtain market changes of affected stocks",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "peer_comparison": SeedFlow(
        id="peer_comparison",
        name="Comparison with peers",
        description="Comparative analysis of companies in the same industry, comparing the fundamentals, valuations, and trends of two or more companies",
        steps=[
            SeedFlowStep(
                tool="get_peer_comparison",
                args_template={"ticker": "{ticker}", "trade_date": "{trade_date}"},
                intent="Get peer stock list and comparison data",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_stock_fundamentals_unified",
                args_template={"ticker": "{ticker}", "curr_date": "{curr_date}"},
                intent="Get fundamental details of major companies",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "concept_stock_analysis": SeedFlow(
        id="concept_stock_analysis",
        name="Concept stock analysis",
        description="Query the constituent stocks and leading stocks of the concept sector, and analyze the investment opportunities of concept stocks, such as what are the XX concept stocks and the leading XX concept stocks",
        steps=[
            SeedFlowStep(
                tool="get_sector_constituents",
                args_template={"sector_name": "{sector_name}", "trade_date": "{trade_date}", "top_n": "20"},
                intent="Get the list of concept sector constituent stocks and market capitalization rankings to find the leading stocks",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_sector_daily",
                args_template={"sector_name": "{sector_name}", "trade_date": "{trade_date}"},
                intent="Get the recent trends, rises and falls of the concept sector index",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "stock_technical_analysis": SeedFlow(
        id="stock_technical_analysis",
        name="Technical analysis of individual stocks",
        description="Technical analysis of individual stocks, check MACD, RSI, KDJ, BOLL and other technical indicators and K-line trends to determine buying and selling signals and trends",
        steps=[
            SeedFlowStep(
                tool="get_technical_indicators",
                args_template={"ticker": "{ticker}", "indicators": "macd,rsi_14,boll,kdj", "end_date": "{curr_date}"},
                intent="Get technical indicators such as MACD/RSI/KDJ/BOLL to determine trends and overbought and oversold conditions",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_stock_market_data_unified",
                args_template={"ticker": "{ticker}", "start_date": "{curr_date}", "end_date": "{curr_date}"},
                intent="Get recent K-line trend and trading volume data",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "market_overview": SeedFlow(
        id="market_overview",
        name="Market analysis",
        description="Market trend analysis, overall market environment assessment, how the market is doing today, market sentiment judgment, price limit statistics",
        steps=[
            SeedFlowStep(
                tool="get_china_market_overview",
                args_template={"curr_date": "{curr_date}"},
                intent="Get an overview of major index prices (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, Science and Technology 50)",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_limit_stats",
                args_template={"trade_date": "{trade_date}"},
                intent="Obtain the number of rising and falling companies and the number of rising and falling companies, and evaluate the market s money-making effect.",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_fund_flow_data",
                args_template={"trade_date": "{trade_date}"},
                intent="Obtain the ranking of sector capital flows and understand the hot sectors",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),

    "north_flow_analysis": SeedFlow(
        id="north_flow_analysis",
        name="Northbound Fund Analysis",
        description="Analysis of northbound capital flows, foreign capital trends, Shanghai-Shenzhen-Hong Kong Stock Connect capital inflows and outflows, and what foreign capital is buying",
        steps=[
            SeedFlowStep(
                tool="get_north_flow",
                args_template={"trade_date": "{trade_date}"},
                intent="Get northbound net inflow/outflow data and trends",
                depends_on=[],
            ),
            SeedFlowStep(
                tool="get_china_market_overview",
                args_template={"curr_date": "{curr_date}"},
                intent="Obtain market index trends and analyze the impact of foreign capital on the market",
                depends_on=[],
            ),
        ],
        extensible=True,
    ),
}


def get_seed_flow(flow_id: str) -> Optional[SeedFlow]:
    """Get seed process based on ID"""
    return BUILTIN_SEED_FLOWS.get(flow_id)


def list_seed_flows() -> List[SeedFlow]:
    """Get all seed processes"""
    return list(BUILTIN_SEED_FLOWS.values())

