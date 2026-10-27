"""
Agent configuration and metadata definition
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentCategory(str, Enum):
    """Agent category"""
    ANALYST = "analyst"       # analyst
    RESEARCHER = "researcher"  # researcher
    TRADER = "trader"         # research integrator
    RISK = "risk"             # risk assessment
    MANAGER = "manager"       # manager
    POST_PROCESSOR = "post_processor"  # post processor


class LicenseTier(str, Enum):
    """License level"""
    FREE = "free"           # Free version
    BASIC = "basic"         # Basic version
    PRO = "pro"             # Professional version
    ENTERPRISE = "enterprise"  # Enterprise Edition


class GrowthRole(str, Enum):
    """Growth Role Statement"""
    NONE = "none"
    EXTRACTOR = "extractor"
    REVIEWER = "reviewer"
    OPTIMIZER = "optimizer"


class GrowthMemoryScope(str, Enum):
    """Memory range reminder for growth products"""
    NONE = "none"
    OBJECT_TRACKING = "object_tracking"
    PATTERN = "pattern"
    RESEARCH_ASSET = "research_asset"


class GrowthReviewLevel(str, Enum):
    """Review level of development products"""
    AUTO_PENDING = "auto_pending"
    MANUAL_REQUIRED = "manual_required"


class GrowthSourceType(str, Enum):
    """Growth product source type"""
    NONE = "none"
    ANALYSIS_REPORT = "analysis_report"
    REVIEW_REPORT = "review_report"
    MANAGER_DECISION = "manager_decision"


class AgentMaturityLevel(str, Enum):
    """Agent Platform maturity level"""
    EXPERIMENTAL = "experimental"
    INTERNAL = "internal"
    STABLE = "stable"


class AgentInputMode(str, Enum):
    """Agent Input mode declaration"""
    STANDALONE = "standalone"
    UPSTREAM_DEPENDENT = "upstream-dependent"
    MIXED = "mixed"


class AgentDebugReplayMode(str, Enum):
    """Agent Debug replay mode"""
    DIRECT = "direct"
    REQUIRES_EXTRA_STATE = "requires_extra_state"
    REQUIRES_CHAIN_PREFILL = "requires_chain_prefill"


class AgentMaintenanceStatus(str, Enum):
    """Agent maintenance status statement"""
    MAINTAINED = "maintained"
    UNMAINTAINED = "unmaintained"
    DEPRECATED = "deprecated"  # 🔥 New: Deprecated and should not be referenced by new code


class AgentInputSource(str, Enum):
    """Agent Enter source statement"""
    REQUEST = "request"
    STATE = "state"
    CONTEXT = "context"


class AgentInput(BaseModel):
    """Agent input definition"""
    name: str
    type: str  # string, number, boolean, object, array
    description: str
    required: bool = True
    default: Optional[Any] = None
    source: AgentInputSource = AgentInputSource.REQUEST
    state_field: Optional[str] = None
    source_state_fields: List[str] = Field(default_factory=list)
    producer_hint: Optional[str] = None


class AgentOutput(BaseModel):
    """Agent output definition"""
    name: str
    type: str
    description: str


class ToolMetadata(BaseModel):
    """Tool metadata definition"""
    id: str                           # Tool unique identifier
    name: str                         # display name
    description: str                  # Description
    category: str                     # Tool category: market, news, social, fundamentals, etc.

    # Parameter definition
    parameters: List[Dict[str, Any]] = Field(default_factory=list)

    # Data source information
    data_source: str = ""             # Data source: yfinance, finnhub, reddit, etc.
    is_online: bool = True            # Do you need online access?

    # Configuration
    timeout: int = 30                 # Timeout (seconds)
    rate_limit: Optional[int] = None  # Frequency limit (calls per minute)

    # license
    license_tier: LicenseTier = LicenseTier.FREE

    # show
    icon: str = "🔧"
    color: str = "#95a5a6"


class AgentToolConfig(BaseModel):
    """Agent Tool configuration"""
    tool_id: str                      # Tools ID
    enabled: bool = True              # Whether to enable
    priority: int = 0                 # Priority (the higher the priority)
    config: Dict[str, Any] = Field(default_factory=dict)  # Tool specific configuration


class AgentMetadata(BaseModel):
    """
    Agent metadata - used for registration and discovery
    """
    id: str                          # unique identifier: market_analyst
    name: str                        # display name: market analyst
    description: str                 # Description
    category: AgentCategory          # Classification
    version: str = "1.0.0"

    # Input and output definition
    inputs: List[AgentInput] = Field(default_factory=list)
    outputs: List[AgentOutput] = Field(default_factory=list)

    # Tool configuration
    tools: List[str] = Field(default_factory=list)  # List of available tool IDs
    default_tools: List[str] = Field(default_factory=list)  # Tools enabled by default
    max_tool_calls: int = 3          # Maximum number of tool calls

    # license
    license_tier: LicenseTier = LicenseTier.FREE

    # Labels and icons
    tags: List[str] = Field(default_factory=list)
    icon: str = "🤖"
    color: str = "#3498db"

    # Depend on
    depends_on: List[str] = Field(default_factory=list)  # Other agents that depend on

    # 🆕 State layer IO definition
    reads_from: List[str] = Field(default_factory=list)  # Read the output fields of other Agents

    # 🆕 Workflow integration configuration
    requires_tools: bool = True       # Whether tool calling is required (False means direct execution)
    output_field: str = ""            # The field name output to state, such as "market_report"
    report_label: str = ""            # Report labels such as " [Market analysis]"
    show_in_reports: bool = True      # Whether to display the output of this agent in the analysis results report list
    node_name: str = ""               # Workflow node name, such as "Market Analyst"
    execution_order: int = 100        # Execution order (the smaller the value, the earlier it is executed)
    workflow_stage: str = ""          # Workflow stages:analyst/research/risk/manager/trader

    # 🆕 Growth Capability Statement
    growth_role: GrowthRole = GrowthRole.NONE
    growth_outputs: List[str] = Field(default_factory=list)
    memory_scope_hint: GrowthMemoryScope = GrowthMemoryScope.NONE
    review_level: GrowthReviewLevel = GrowthReviewLevel.MANUAL_REQUIRED
    growth_source_type: GrowthSourceType = GrowthSourceType.NONE

    # 🆕 Platform Governance Statement
    maturity_level: AgentMaturityLevel = AgentMaturityLevel.STABLE
    input_mode: AgentInputMode = AgentInputMode.STANDALONE
    debug_replay_mode: AgentDebugReplayMode = AgentDebugReplayMode.DIRECT
    maintenance_status: AgentMaintenanceStatus = AgentMaintenanceStatus.MAINTAINED
    callable_surfaces: List[str] = Field(default_factory=lambda: ["assistant", "workflow", "agent"])

    class Config:
        use_enum_values = True


class AgentConfig(BaseModel):
    """
    Agent runtime configuration
    
    NOTE: The llm_provider and llm_model fields are deprecated and should not be used.
    LLM The provider and model should be specified by the analysis process, not the Agent configuration.
    These fields are retained for backward compatibility, but are excluded when creating the Agent.
    """
    # LLM Configuration (deprecated and should not be used)
    llm_provider: Optional[str] = None  # 🔥 Change to Optional, default None, to avoid misleading
    llm_model: Optional[str] = None
    temperature: float = 0.2  # Recommended values for stock analysis: 0.2-0.3 (quick analysis), 0.1-0.2 (in-depth analysis)
    
    # Tool configuration
    online_tools: bool = True
    available_tools: List[str] = Field(default_factory=list)
    
    # Prompt word configuration
    prompt_template: Optional[str] = None  # Prompt word template to use ID
    prompt_variables: Dict[str, Any] = Field(default_factory=dict)
    
    # memory configuration
    memory_enabled: bool = True
    memory_type: str = "chromadb"  # chromadb, postgresql, none
    
    # Timeout configuration
    timeout: int = 60
    max_retries: int = 3
    
    # Debug configuration
    debug: bool = False
    log_level: str = "INFO"


# Predefined agent metadata
BUILTIN_AGENTS: Dict[str, AgentMetadata] = {
    "market_analyst": AgentMetadata(
        id="market_analyst",
        name="market analyst",
        description="Analyze market data, price movements and technical indicators",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📈",
        color="#2ecc71",
        tags=["technical analysis", "market data"],
        tools=["get_stock_market_data_unified", "get_YFin_data_online", "get_stockstats_indicators_report_online", "get_YFin_data", "get_stockstats_indicators_report"],
        default_tools=["get_stock_market_data_unified"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_date", type="string", description="transaction date"),
        ],
        outputs=[
            AgentOutput(name="market_report", type="string", description="Market analysis report"),
        ],
        # 🆕 Workflow configuration
        requires_tools=True,
        output_field="market_report",
        report_label=" [Technical analysis]",
        node_name="market analyst",
        execution_order=10,
        workflow_stage="analyst",  # 🔥 New: Analyst Stage
    ),
    "fundamentals_analyst": AgentMetadata(
        id="fundamentals_analyst",
        name="fundamental analyst",
        description="Analyze company financial data and fundamental indicators",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📊",
        color="#3498db",
        tags=["Fundamentals", "financial analysis"],
        tools=["get_stock_fundamentals_unified", "get_finnhub_company_insider_sentiment", "get_finnhub_company_insider_transactions", "get_simfin_balance_sheet", "get_simfin_cashflow", "get_simfin_income_stmt", "get_china_stock_data", "get_china_fundamentals"],
        default_tools=["get_stock_fundamentals_unified"],
        max_tool_calls=3,
        # 🆕 Workflow configuration
        requires_tools=True,
        output_field="fundamentals_report",
        report_label=" [Fundamental Analysis]",
        node_name="fundamental analyst",
        execution_order=40,
        workflow_stage="analyst",  # 🔥 New: Analyst Stage
    ),
    "news_analyst": AgentMetadata(
        id="news_analyst",
        name="news analyst",
        description="Analyze the impact of financial news and events",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📰",
        color="#9b59b6",
        tags=["News", "event driven"],
        tools=["get_stock_news_unified", "get_global_news_openai", "get_google_news", "get_finnhub_news", "get_reddit_news"],
        default_tools=["get_stock_news_unified"],
        max_tool_calls=3,
        # 🆕 Workflow configuration
        requires_tools=True,
        output_field="news_report",
        report_label=" [News Analysis]",
        node_name="news analyst",
        execution_order=30,
        workflow_stage="analyst",  # 🔥 New: Analyst Stage
    ),
    "social_analyst": AgentMetadata(
        id="social_analyst",
        name="social media analyst",
        description="Analyze social media sentiment and public opinion",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="💬",
        color="#e74c3c",
        tags=["sentiment analysis", "public opinion"],
        tools=["get_stock_sentiment_unified", "get_stock_news_openai", "get_reddit_stock_info"],
        default_tools=["get_stock_sentiment_unified"],
        max_tool_calls=3,
        # 🆕 Workflow configuration
        requires_tools=True,
        output_field="sentiment_report",
        report_label=" [Public opinion analysis]",
        node_name="social media analyst",
        execution_order=20,
        workflow_stage="analyst",  # 🔥 New: Analyst Stage
    ),
    "sector_analyst": AgentMetadata(
        id="sector_analyst",
        name="Industry/sector analyst",
        description="Analyze industry trends, sector rotations and industry comparisons",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        license_tier=LicenseTier.PRO,
        icon="🏭",
        color="#f39c12",
        tags=["Industry analysis", "sector rotation"],
        tools=["get_sector_performance", "get_industry_comparison"],
        default_tools=["get_sector_performance"],
        max_tool_calls=3,
        # 🆕 Workflow configuration (no tool invocation)
        requires_tools=False,
        output_field="sector_report",
        report_label=" [Industry sector analysis]",
        node_name="Sector Analyst",
        execution_order=5,  # Before technical analysis
        workflow_stage="analyst",  # 🔥 New: Analyst Stage
    ),
    "index_analyst": AgentMetadata(
        id="index_analyst",
        name="Market/Index Analyst",
        description="Analyze broad market indices, market conditions and systemic risks",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        license_tier=LicenseTier.PRO,
        icon="🌐",
        color="#1abc9c",
        tags=["Market", "Index", "Macro"],
        tools=["get_index_data", "get_market_overview"],
        default_tools=["get_index_data"],
        max_tool_calls=3,
        # 🆕 Workflow configuration (no tool invocation)
        requires_tools=False,
        output_field="index_report",
        report_label=" [Macro market analysis]",
        node_name="Market Analyst",
        execution_order=1,  # executed first
        workflow_stage="analyst",  # 🔥 New: Analyst Stage
    ),
    "bull_researcher": AgentMetadata(
        id="bull_researcher",
        name="Positive Evidence Researcher",
        description="Collate research evidence supporting optimistic interpretations from a positive perspective (output research observations and do not constitute investment advice)",
        category=AgentCategory.RESEARCHER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="🐂",
        color="#27ae60",
        tags=["Positive", "evidence"],
        tools=[],  # The researcher does not call the tool directly, it is based on analyst reports
        max_tool_calls=0,
        workflow_stage="research",  # 🔥 New: Research Phase
    ),
    "bear_researcher": AgentMetadata(
        id="bear_researcher",
        name="cautious evidence researcher",
        description="Collate research evidence supporting prudent interpretation from a cautious perspective (output research observations and do not constitute investment advice)",
        category=AgentCategory.RESEARCHER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="🐻",
        color="#c0392b",
        tags=["cautious", "evidence"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="research",  # 🔥 New: Research Phase
    ),
    "trader": AgentMetadata(
        id="trader",
        name="research integrator",
        description="Comprehensive research evidence from various dimensions and compiled into a summary of research observations (does not constitute investment advice)",
        category=AgentCategory.TRADER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="💰",
        color="#f1c40f",
        tags=["Integrate", "observe"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="trader",  # 🔥 New: Research Integration Phase
    ),
    "position_advisor": AgentMetadata(
        id="position_advisor",
        name="Position Researcher",
        description="Based on single stock analysis reports and position information, sort out position research and observation items (does not constitute investment advice)",
        category=AgentCategory.TRADER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="💼",
        color="#2980b9",
        tags=["Position", "research observation", "risk assessment"],
        tools=[],
        max_tool_calls=0,
        requires_tools=False,
        workflow_stage="trader",  # 🔥 New: Research Integration Phase
    ),
    "risky_analyst": AgentMetadata(
        id="risky_analyst",
        name="Highly Resilient Scenario Analyst",
        description="Collate research evidence under high elasticity scenarios and focus on potential profit space (outputting research observations does not constitute investment advice)",
        category=AgentCategory.RISK,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="🔥",
        color="#e74c3c",
        tags=["Scenario", "High elasticity", "Research"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="risk",  # 🔥 New: Risk Study Phase
    ),
    "safe_analyst": AgentMetadata(
        id="safe_analyst",
        name="Defense Scenario Analyst",
        description="Collate research evidence under defensive scenarios and focus on capital protection factors (output research observations and do not constitute investment advice)",
        category=AgentCategory.RISK,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="🛡️",
        color="#27ae60",
        tags=["Scenario", "defense", "Research"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="risk",  # 🔥 New: Risk Study Phase
    ),
    "neutral_analyst": AgentMetadata(
        id="neutral_analyst",
        name="Baseline Scenario Analyst",
        description="Collate research evidence under baseline scenarios and balance multiple perspectives (outputting research observations does not constitute investment advice)",
        category=AgentCategory.RISK,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="⚖️",
        color="#3498db",
        tags=["Scenario", "benchmark", "balance"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="risk",  # 🔥 New: Risk Study Phase
    ),
    "risk_manager": AgentMetadata(
        id="risk_manager",
        name="risk assessor",
        description="Comprehensive research evidence from each scenario and a summary of risk research observations (does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="👨‍⚖️",
        color="#9b59b6",
        tags=["risk", "Research", "Assessment"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="manager",  # 🔥 New: Evaluation Phase
    ),
    "research_manager": AgentMetadata(
        id="research_manager",
        name="research integrator",
        description="Comprehensive research evidence from multiple perspectives and compiled into a summary of research observations (does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="👔",
        color="#9b59b6",
        tags=["Integrate", "Research", "observe"],
        tools=[],
        max_tool_calls=0,
        workflow_stage="manager",  # 🔥 New: Evaluation Phase
    ),
    # ==================== Transaction review Agent ====================
    "timing_analyst": AgentMetadata(
        id="timing_analyst",
        name="Timing Researcher",
        description="Research observations to analyze entry and exit timings and evaluate trading timings (does not constitute investment advice)",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="⏰",
        color="#e67e22",
        tags=["Review", "timing", "Research"],
        tools=[
            "get_stock_market_data_unified",
            "get_stockstats_indicators_report",
            "get_trade_records",
            "build_trade_info",
            "get_market_snapshot_for_review"
        ],
        default_tools=[
            "get_stock_market_data_unified",
            "build_trade_info"
        ],
        max_tool_calls=5,
        requires_tools=False,
        output_field="timing_analysis",
        report_label=" [Timing analysis]",
        node_name="timing analyst",
        execution_order=10,
        workflow_stage="analyst",  # 🔥 Newly added: analyst stage (review process)
    ),
    "position_analyst": AgentMetadata(
        id="position_analyst",
        name="Position Analyst",
        description="Analyze research and observations on position management, and do not output execution suggestions such as adding or subtracting positions.",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📊",
        color="#3498db",
        tags=["Review", "position", "Money management"],
        tools=[
            "get_stock_market_data_unified",
            "get_trade_records",
            "build_trade_info",
            "get_account_info",
            "get_market_snapshot_for_review"
        ],
        default_tools=[
            "build_trade_info",
            "get_account_info"
        ],
        max_tool_calls=5,
        requires_tools=False,
        output_field="position_analysis",
        report_label=" [Position analysis]",
        node_name="Position Analyst",
        execution_order=20,
        workflow_stage="analyst",  # 🔥 Newly added: analyst stage (review process)
    ),
    "emotion_analyst": AgentMetadata(
        id="emotion_analyst",
        name="sentiment analyst",
        description="Analyze emotional operations and discipline execution in trading",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="🧠",
        color="#9b59b6",
        tags=["Review", "emotions", "discipline"],
        tools=[
            "get_stock_news_unified",
            "get_stock_sentiment_unified",
            "get_trade_records",
            "build_trade_info",
            "get_account_info"
        ],
        default_tools=[
            "build_trade_info",
            "get_account_info"
        ],
        max_tool_calls=5,
        requires_tools=True,
        output_field="emotion_analysis",
        report_label=" [Sentiment Analysis]",
        node_name="sentiment analyst",
        execution_order=30,
        workflow_stage="analyst",  # 🔥 Newly added: analyst stage (review process)
    ),
    "attribution_analyst": AgentMetadata(
        id="attribution_analyst",
        name="attribution analyst",
        description="Analyze the sources of income and distinguish the Alpha contribution of the market/industry/individual stocks",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="🎯",
        color="#1abc9c",
        tags=["Review", "attribution", "Alpha"],
        tools=[
            "get_stock_market_data_unified",
            "get_china_market_overview",
            "get_trade_records",
            "build_trade_info",
            "get_market_snapshot_for_review"
        ],
        default_tools=[
            "get_stock_market_data_unified",
            "build_trade_info"
        ],
        max_tool_calls=5,
        requires_tools=False,
        output_field="attribution_analysis",
        report_label=" [Attribution analysis]",
        node_name="attribution analyst",
        execution_order=40,
        workflow_stage="analyst",  # 🔥 Newly added: analyst stage (review process)
    ),
    "review_manager": AgentMetadata(
        id="review_manager",
        name="Review summary expert",
        description="Comprehensive all analysis dimensions to generate a complete review report and improvement suggestions",
        category=AgentCategory.MANAGER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📝",
        color="#2c3e50",
        tags=["Review", "Summary", "Suggestions"],
        tools=[
            "get_trade_records",
            "build_trade_info",
            "get_account_info",
            "get_market_snapshot_for_review"
        ],
        default_tools=[
            "build_trade_info",
            "get_account_info"
        ],
        max_tool_calls=5,
        requires_tools=True,
        output_field="review_summary",
        report_label=" [Review summary]",
        node_name="Review summary expert",
        execution_order=100,
        workflow_stage="manager",  # 🔥 Newly added: Manager stage (review process)
    ),
    # ==================== Position analysis Agent ====================
    "pa_technical": AgentMetadata(
        id="pa_technical",
        name="Position Technical Analyst",
        description="Analyze K-line trends, technical indicators, support and resistance levels, and evaluate technical status",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📈",
        color="#2ecc71",
        tags=["Position analysis", "technical aspect", "Trend"],
        tools=["get_stock_market_data_unified", "get_technical_indicators"],
        max_tool_calls=3,
        requires_tools=False,
        output_field="technical_analysis",
        report_label=" [Technical analysis]",
        node_name="technical analyst",
        execution_order=10,
        workflow_stage="analyst",  # 🔥 New: Analyst stage (position analysis process)
    ),
    "pa_fundamental": AgentMetadata(
        id="pa_fundamental",
        name="Fundamental Analyst",
        description="Analyze financial data, valuation levels, industry status, and evaluate fundamental value",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="📊",
        color="#3498db",
        tags=["Position analysis", "Fundamentals", "Valuation"],
        tools=["get_stock_fundamentals_unified", "get_stock_news_unified"],
        max_tool_calls=3,
        requires_tools=False,
        output_field="fundamental_analysis",
        report_label=" [Fundamental Analysis]",
        node_name="fundamental analyst",
        execution_order=20,
        workflow_stage="analyst",  # 🔥 New: Analyst stage (position analysis process)
    ),
    "pa_risk": AgentMetadata(
        id="pa_risk",
        name="Position risk assessor",
        description="Assess position risks, analyze position rationality, and provide reference for risk and return concerns",
        category=AgentCategory.ANALYST,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="⚠️",
        color="#e74c3c",
        tags=["Position analysis", "risk", "stop loss"],
        tools=["get_stock_market_data_unified", "get_china_market_overview", "get_stock_sentiment_unified"],
        max_tool_calls=3,
        requires_tools=False,
        output_field="risk_analysis",
        report_label=" [Risk Assessment]",
        node_name="risk assessor",
        execution_order=30,
        workflow_stage="analyst",  # 🔥 New: Analyst stage (position analysis process)
    ),
    "pa_advisor": AgentMetadata(
        id="pa_advisor",
        name="Position research integrator",
        description="Comprehensive technical aspects, fundamentals, and risk assessments, and a summary of position research and observations (does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        maintenance_status=AgentMaintenanceStatus.DEPRECATED,  # 🔥 v1 Deprecated, please use v2 version
        icon="💡",
        color="#9b59b6",
        tags=["Position analysis", "Research", "observe"],
        tools=[],
        max_tool_calls=0,
        requires_tools=False,
        output_field="action_advice",
        report_label=" [Position research and observation]",
        node_name="Position research integrator",
        execution_order=100,
        # 🆕 Read the output of other agents
        reads_from=["technical_analysis", "fundamental_analysis", "risk_analysis"],
        workflow_stage="manager",  # 🔥 Newly added: Research stage (position analysis process)
    ),
    # 🆕 v2.0 architectural Agent
    "market_analyst_v2": AgentMetadata(
        id="market_analyst_v2",
        name="market analyst v2",
        description="Analyze stock price trends, technical indicators and market data, and generate technical analysis reports",
        category=AgentCategory.ANALYST,
        icon="📈",
        color="#2ecc71",
        tags=["technical analysis", "market data", "v2.0"],
        tools=["get_stock_market_data_unified"],
        default_tools=["get_stock_market_data_unified"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="start_date", type="string", description="start date"),
            AgentInput(name="end_date", type="string", description="end date"),
        ],
        outputs=[
            AgentOutput(name="market_analysis", type="string", description="Market analysis report"),
        ],
        requires_tools=True,
        output_field="market_analysis",
        report_label=" [Market Analysis v2]",
        node_name="market analyst v2",
        execution_order=10,
        growth_role="extractor",
        growth_outputs=["market_analysis"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    ),
    "fundamentals_analyst_v2": AgentMetadata(
        id="fundamentals_analyst_v2",
        name="fundamental analyst v2",
        description="Analyze company financial data, profitability, growth and fundamental indicators, covering moat/competitive advantage assessment and management quality analysis",
        category=AgentCategory.ANALYST,
        icon="📊",
        color="#3498db",
        tags=["Fundamentals", "financial analysis", "v2.0"],
        tools=["get_stock_fundamentals_unified"],
        default_tools=["get_stock_fundamentals_unified"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="fundamentals_report", type="string", description="Fundamental Analysis Report"),
        ],
        requires_tools=True,
        output_field="fundamentals_report",
        report_label=" [Fundamental Analysis v2] ",
        node_name="fundamental analyst v2",
        execution_order=40,
        growth_role="extractor",
        growth_outputs=["fundamentals_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    ),
    "etf_analyst_v2": AgentMetadata(
        id="etf_analyst_v2",
        name="ETF analyst v2",
        description="Analyze ETF net worth, size, expense ratio, tracking error, and more. ETFs have no PE/PB/ROE and use indicators such as net worth, size, and tracking indexes.",
        category=AgentCategory.ANALYST,
        icon="📈",
        color="#27ae60",
        tags=["ETF", "fund", "net worth", "v2.0"],
        tools=["get_etf_fundamentals"],
        default_tools=["get_etf_fundamentals"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="ETF code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="fundamentals_report", type="string", description="ETF Analysis report (reuse fundamentals_report field)"),
        ],
        requires_tools=True,
        output_field="fundamentals_report",
        report_label=" [ETF Analysis v2]",
        node_name="ETF analyst v2",
        execution_order=40,
        growth_role="extractor",
        growth_outputs=["fundamentals_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    ),
    "news_analyst_v2": AgentMetadata(
        id="news_analyst_v2",
        name="news analyst v2",
        description="Analyze the impact of financial news, announcements and events on stocks, and assess news drivers and changes in market sentiment",
        category=AgentCategory.ANALYST,
        icon="📰",
        color="#9b59b6",
        tags=["News", "event driven", "v2.0"],
        tools=["get_stock_news_unified"],
        default_tools=["get_stock_news_unified"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="news_report", type="string", description="News analysis report"),
        ],
        requires_tools=True,
        output_field="news_report",
        report_label=" [News Analysis v2]",
        node_name="news analyst v2",
        execution_order=30,
        growth_role="extractor",
        growth_outputs=["news_report"],
        memory_scope_hint="object_tracking",
        review_level="manual_required",
        growth_source_type="analysis_report",
    ),
    "social_analyst_v2": AgentMetadata(
        id="social_analyst_v2",
        name="social media analyst v2",
        description="Analyze social media sentiment, public opinion trends and investor attention, and assess the potential impact of irrational factors on stock prices",
        category=AgentCategory.ANALYST,
        icon="💬",
        color="#e74c3c",
        tags=["sentiment analysis", "public opinion", "v2.0"],
        tools=["get_stock_sentiment_unified"],
        default_tools=["get_stock_sentiment_unified"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="sentiment_report", type="string", description="Social media sentiment analysis report"),
        ],
        requires_tools=True,
        output_field="sentiment_report",
        report_label=" [Public opinion analysis v2] ",
        node_name="social media analyst v2",
        execution_order=20,
        growth_role="extractor",
        growth_outputs=["sentiment_report"],
        memory_scope_hint="object_tracking",
        review_level="manual_required",
        growth_source_type="analysis_report",
    ),
    "index_analyst_v2": AgentMetadata(
        id="index_analyst_v2",
        name="Market Analyst v2.0",
        description="Analyze market index trends and evaluate the overall market environment, capital flow and technical aspects",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[
            "get_index_data",           # Index trends and moving averages
            "get_market_breadth",       # Market breadth (volume, market capitalization)
            "get_market_environment",   # Market environment (valuation, volatility)
            "identify_market_cycle",    # Market cycle identification
            "get_north_flow",           # Northbound capital flow
            "get_margin_trading",       # Balance of financing and financing
            "get_limit_stats",          # Price limit statistics
            "get_index_technical",      # Technical indicators (MACD/RSI/KDJ)
        ],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="index_report", type="string", description="Market analysis report"),
        ],
        requires_tools=True,
        output_field="index_report",
        report_label=" [Market analysis v2]",
        node_name="Market Analyst v2",
        execution_order=1,  # executed first
        growth_role="extractor",
        growth_outputs=["index_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    ),

    # 🆕 Chip distribution analyst Agent
    "chip_distribution_analyst_v2": AgentMetadata(
        id="chip_distribution_analyst_v2",
        name="Chip distribution analyst v2.0",
        description="Analyze stock chip distribution, evaluate profit ratio, average cost and chip concentration, and generate chip distribution analysis report",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        icon="🧮",
        color="#e74c3c",
        tags=["Chip distribution", "Holding cost", "Profit ratio", "v2.0"],
        tools=["get_chip_distribution"],
        default_tools=["get_chip_distribution"],
        max_tool_calls=3,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="chip_report", type="string", description="Chip distribution analysis report"),
        ],
        requires_tools=True,
        output_field="chip_report",
        report_label=" [Chip distribution analysis v2]",
        node_name="Chip distribution analyst v2",
        execution_order=15,
    ),

    # 🆕 Valuation Analyst Agent
    "valuation_analyst_v2": AgentMetadata(
        id="valuation_analyst_v2",
        name="Valuation Analyst v2.0",
        description="Analyze stock valuation levels, including PE/PB/PS/PEG and other indicators, historical valuation ranges, and comparison of valuations in the same industry, evaluate the rationality of the current valuation and give a reasonable valuation range",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        icon="💎",
        color="#9b59b6",
        tags=["Valuation analysis", "PE/PB", "DCF", "relative valuation", "v2.0"],
        tools=["get_stock_fundamentals_unified", "get_industry_valuation_comparison", "get_historical_valuation_range"],
        default_tools=["get_stock_fundamentals_unified"],
        max_tool_calls=5,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="valuation_method", type="string", description="Valuation method (PE/PB/DCF/comprehensive)", required=False, default="Comprehensive"),
        ],
        outputs=[
            AgentOutput(name="valuation_report", type="string", description="Valuation analysis report"),
            AgentOutput(name="fair_value_range", type="object", description="Reasonable valuation range (low/medium/high)"),
            AgentOutput(name="valuation_rating", type="string", description="Valuation rating (undervalued/reasonable/overvalued)"),
        ],
        requires_tools=True,
        output_field="valuation_report",
        report_label=" [Valuation analysis v2]",
        node_name="Valuation Analyst v2",
        execution_order=45,  # After fundamental analysis
        growth_role="extractor",
        growth_outputs=["valuation_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    ),

    # ── v2.0 Single Stock Analysis Extensions: Sectors/Debates/Decisions ──────────────────────────────

    "sector_analyst_v2": AgentMetadata(
        id="sector_analyst_v2",
        name="Sector Analyst v2.0",
        description="Analyze industry trends, sector rotation and peer comparison, and refine structural changes and risk sources",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_sector_analysis"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="sector_report", type="string", description="Sector analysis report"),
        ],
        requires_tools=True,
        output_field="sector_report",
        report_label=" [Sector analysis v2]",
        node_name="Sector Analyst v2",
        execution_order=5,
    ),

    "bull_researcher_v2": AgentMetadata(
        id="bull_researcher_v2",
        name="Optimistic Scenario Researcher v2.0",
        description="Construct an optimistic but restrained research argument based on existing materials, and refine the premise, evidence chain and observation signals",
        category=AgentCategory.RESEARCHER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False),
        ],
        outputs=[
            AgentOutput(name="bull_report", type="string", description="Optimistic Scenario Research Report"),
        ],
        requires_tools=False,
        output_field="bull_report",
        report_label=" [Optimistic Scenario Study v2]",
        node_name="Optimistic Scenario Researcher v2",
        execution_order=80,
    ),

    "bear_researcher_v2": AgentMetadata(
        id="bear_researcher_v2",
        name="Prudential Scenario Researcher v2.0",
        description="Construct a prudent research argument based on existing materials and refine risks, vulnerabilities and boundaries of judgment.",
        category=AgentCategory.RESEARCHER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False),
        ],
        outputs=[
            AgentOutput(name="bear_report", type="string", description="Prudential Scenario Research Report"),
        ],
        requires_tools=False,
        output_field="bear_report",
        report_label=" [Prudential Scenario Study v2]",
        node_name="Prudential Scenario Researcher v2",
        execution_order=85,
    ),

    "research_manager_v2": AgentMetadata(
        id="research_manager_v2",
        name="research integrator v2.0",
        description="Comprehensive research on optimistic and cautious scenarios to form a balanced summary of research observations (does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="bull_report", type="string", description="Optimistic Scenario Research Report"),
            AgentInput(name="bear_report", type="string", description="Prudential Scenario Research Report"),
        ],
        outputs=[
            AgentOutput(name="investment_advice", type="string", description="Summary of Balance Study Observations"),
        ],
        requires_tools=False,
        output_field="investment_advice",
        report_label=" [Balance Research Observation v2] ",
        node_name="research integrator v2",
        execution_order=90,
    ),

    "trader_v2": AgentMetadata(
        id="trader_v2",
        name="research integrator v2.0",
        description="Based on the comprehensive research evidence after risk review, a user version of the research briefing is compiled (does not constitute investment advice)",
        category=AgentCategory.TRADER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Summary of comprehensive research observations"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False),
            AgentInput(name="bull_report", type="string", description="Optimistic Scenario Research Report", required=False),
            AgentInput(name="bear_report", type="string", description="Prudential Scenario Research Report", required=False),
        ],
        outputs=[
            AgentOutput(name="trader_investment_plan", type="string", description="User version of research briefing (summary of research observations, does not constitute investment advice)"),
        ],
        requires_tools=False,
        output_field="trader_investment_plan",
        report_label=" [Research Brief v2]",
        node_name="research integrator v2",
        execution_order=200,
    ),

    # ── v2.0 Risk research and judgment expansion ──────────────────────────────────────────────

    "risky_analyst_v2": AgentMetadata(
        id="risky_analyst_v2",
        name="Highly Resilient Scenario Analyst v2.0",
        description="Review the research conclusions from the perspective of whether they can be revised upward, and identify strengthened catalysts, high-requirement prerequisites and additional verification signals",
        category=AgentCategory.RISK,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion"),
            AgentInput(name="bull_opinion", type="string", description="optimistic scenario view", required=False),
            AgentInput(name="bear_opinion", type="string", description="prudent situational view", required=False),
        ],
        outputs=[
            AgentOutput(name="risky_opinion", type="string", description="Highly resilient scenario perspective"),
        ],
        requires_tools=False,
        output_field="risky_opinion",
        report_label=" [Highly elastic risk assessment v2]",
        node_name="Highly Resilient Scenario Analyst v2",
        execution_order=100,
    ),

    "safe_analyst_v2": AgentMetadata(
        id="safe_analyst_v2",
        name="Defense Scenario Analyst v2.0",
        description="Review the research conclusions from the perspective that are most likely to fail, and identify fragile premises, risk sources and downward revision triggering conditions",
        category=AgentCategory.RISK,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion"),
            AgentInput(name="bull_opinion", type="string", description="optimistic scenario view", required=False),
            AgentInput(name="bear_opinion", type="string", description="prudent situational view", required=False),
        ],
        outputs=[
            AgentOutput(name="safe_opinion", type="string", description="defensive situational view"),
        ],
        requires_tools=False,
        output_field="safe_opinion",
        report_label=" [Defense risk assessment v2]",
        node_name="Defense Scenario Analyst v2",
        execution_order=105,
    ),

    "neutral_analyst_v2": AgentMetadata(
        id="neutral_analyst_v2",
        name="Baseline Scenario Analyst v2.0",
        description="Balance optimistic and cautious materials, determine the most stable baseline scenario at present, and identify consensus, conflict points and information gaps",
        category=AgentCategory.RISK,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion"),
            AgentInput(name="risky_opinion", type="string", description="Highly resilient scenario perspective", required=False),
            AgentInput(name="safe_opinion", type="string", description="defensive situational view", required=False),
        ],
        outputs=[
            AgentOutput(name="neutral_opinion", type="string", description="base case view"),
        ],
        requires_tools=False,
        output_field="neutral_opinion",
        report_label=" [Baseline Risk Assessment v2]",
        node_name="Baseline Scenario Analyst v2",
        execution_order=110,
    ),

    "risk_manager_v2": AgentMetadata(
        id="risk_manager_v2",
        name="risk assessor v2.0",
        description="Host the robustness review, integrate multiple perspectives, and formulate comprehensive research conclusions after the risk review (outputting research observations does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion"),
            AgentInput(name="risky_opinion", type="string", description="Highly resilient scenario perspective", required=False),
            AgentInput(name="safe_opinion", type="string", description="defensive situational view", required=False),
            AgentInput(name="neutral_opinion", type="string", description="base case view", required=False),
        ],
        outputs=[
            AgentOutput(name="risk_assessment", type="string", description="Robustness review and risk research observation"),
        ],
        requires_tools=False,
        output_field="risk_assessment",
        report_label=" [Risk study conclusion v2] ",
        node_name="risk assessor v2",
        execution_order=120,
    ),

    # ── v2.0 Position analysis ──────────────────────────────────────────────────

    "pa_technical_v2": AgentMetadata(
        id="pa_technical_v2",
        name="technical analyst v2.0",
        description="Analyze the technical aspects of held stocks, including K-line patterns, technical indicators, support and resistance levels",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_stock_market_data_unified"],
        inputs=[
            AgentInput(name="portfolio_data", type="string", description="Position data"),
        ],
        outputs=[
            AgentOutput(name="technical_analysis", type="string", description="Technical analysis results"),
        ],
        requires_tools=True,
        output_field="technical_analysis",
        node_name="technical analyst v2",
        execution_order=10,
        workflow_stage="analyst",
    ),

    "pa_fundamental_v2": AgentMetadata(
        id="pa_fundamental_v2",
        name="fundamental analyst v2.0",
        description="Analyze the fundamentals of held stocks, including financial data, valuation levels, and industry status",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="portfolio_data", type="string", description="Position data"),
        ],
        outputs=[
            AgentOutput(name="fundamental_analysis", type="string", description="Fundamental analysis results"),
        ],
        requires_tools=False,
        output_field="fundamental_analysis",
        node_name="fundamental analyst v2",
        execution_order=20,
        workflow_stage="analyst",
    ),

    "pa_risk_v2": AgentMetadata(
        id="pa_risk_v2",
        name="risk assessor v2.0",
        description="Assess position risk, including risk exposure, risk scenarios and volatility analysis",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="portfolio_data", type="string", description="Position data"),
        ],
        outputs=[
            AgentOutput(name="risk_analysis", type="string", description="Risk assessment results"),
        ],
        requires_tools=False,
        output_field="risk_analysis",
        node_name="risk assessor v2",
        execution_order=30,
        workflow_stage="analyst",
    ),

    "pa_advisor_v2": AgentMetadata(
        id="pa_advisor_v2",
        name="Position research integrator v2.0",
        description="Comprehensive analysis of various dimensions, sorting out position research observations and matters of concern (does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="portfolio_data", type="string", description="Position data"),
            AgentInput(name="technical_analysis", type="string", description="Technical analysis results", required=False),
            AgentInput(name="fundamental_analysis", type="string", description="Fundamental analysis results", required=False),
            AgentInput(name="risk_analysis", type="string", description="Risk assessment results", required=False),
        ],
        outputs=[
            AgentOutput(name="action_advice", type="string", description="Summary of position research observations"),
        ],
        requires_tools=False,
        output_field="action_advice",
        node_name="Position research integrator v2",
        execution_order=100,
        workflow_stage="manager",
    ),

    # ── v2.0 Review analysis ──────────────────────────────────────────────────

    "timing_analyst_v2": AgentMetadata(
        id="timing_analyst_v2",
        name="timing analyst v2.0",
        description="Review the basis for entry and exit, and evaluate the rationality of trading timing.",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="dict", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="dict", description="market data", required=False),
            AgentInput(name="benchmark_data", type="dict", description="Benchmark data", required=False),
        ],
        outputs=[
            AgentOutput(name="timing_analysis", type="string", description="Timing analysis results"),
        ],
        requires_tools=False,
        output_field="timing_analysis",
        node_name="timing analyst v2",
        execution_order=10,
        workflow_stage="analyst",
    ),

    "position_analyst_v2": AgentMetadata(
        id="position_analyst_v2",
        name="Position Analyst v2.0",
        description="The rationality of review position control and position change basis",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="dict", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="dict", description="market data", required=False),
            AgentInput(name="benchmark_data", type="dict", description="Benchmark data", required=False),
        ],
        outputs=[
            AgentOutput(name="position_analysis", type="string", description="Position analysis results"),
        ],
        requires_tools=False,
        output_field="position_analysis",
        node_name="Position Analyst v2",
        execution_order=20,
        workflow_stage="analyst",
    ),

    "emotion_analyst_v2": AgentMetadata(
        id="emotion_analyst_v2",
        name="sentiment analyst v2.0",
        description="Analyze emotional operations and discipline execution in trading",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="dict", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="dict", description="market data", required=False),
            AgentInput(name="benchmark_data", type="dict", description="Benchmark data", required=False),
        ],
        outputs=[
            AgentOutput(name="emotion_analysis", type="string", description="Sentiment analysis results"),
        ],
        requires_tools=False,
        output_field="emotion_analysis",
        node_name="sentiment analyst v2",
        execution_order=30,
        workflow_stage="analyst",
    ),

    "attribution_analyst_v2": AgentMetadata(
        id="attribution_analyst_v2",
        name="attribution analyst v2.0",
        description="Analyze the sources of income and distinguish the Alpha contribution and replicability of the market/industry/individual stocks",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="dict", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="dict", description="market data", required=False),
            AgentInput(name="benchmark_data", type="dict", description="Benchmark data", required=False),
        ],
        outputs=[
            AgentOutput(name="attribution_analysis", type="string", description="Attribution analysis results"),
        ],
        requires_tools=False,
        output_field="attribution_analysis",
        node_name="attribution analyst v2",
        execution_order=40,
        workflow_stage="analyst",
    ),

    "review_manager_v2": AgentMetadata(
        id="review_manager_v2",
        name="Review summary expert v2.0",
        description="Comprehensive all analysis dimensions to generate a complete review report and improvement directions",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="dict", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="dict", description="market data", required=False),
            AgentInput(name="benchmark_data", type="dict", description="Benchmark data", required=False),
            AgentInput(name="timing_analysis", type="string", description="Timing analysis results", required=False),
            AgentInput(name="position_analysis", type="string", description="Position analysis results", required=False),
            AgentInput(name="emotion_analysis", type="string", description="Sentiment analysis results", required=False),
            AgentInput(name="attribution_analysis", type="string", description="Attribution analysis results", required=False),
        ],
        outputs=[
            AgentOutput(name="review_summary", type="string", description="Review summary report"),
        ],
        requires_tools=False,
        output_field="review_summary",
        node_name="Review summary expert v2",
        execution_order=100,
        workflow_stage="manager",
    ),

    # 🆕 report generator Agent (Intelligent report generation)
    "report_generator_v2": AgentMetadata(
        id="report_generator_v2",
        name="report generator v2",
        description="Intelligent report generation Agent understands the analysis results and generates a formatted comprehensive report through LLM",
        category=AgentCategory.ANALYST,  # Changed to ANALYST (because of calling LLM)
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        icon="📝",
        color="#9b59b6",
        tags=["report", "generate", "Summary", "Smart", "v2.0"],
        tools=[],  # No tools required, just process existing data
        default_tools=[],
        max_tool_calls=0,
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code", required=False),
            AgentInput(name="analysis_date", type="string", description="Analysis date", required=False),
            AgentInput(name="report_style", type="string", description="Report style (concise/detailed/investor)", required=False),
        ],
        outputs=[
            AgentOutput(name="reports", type="dict", description="generated report dictionary"),
            AgentOutput(name="report_summary", type="string", description="Report Summary"),
        ],
        requires_tools=False,
        output_field="reports",
        report_label=" [Comprehensive Report]",
        node_name="report generator v2",
        execution_order=999,  # Last executed
    ),

    # 🆕 data preparer Agent (Smart data preparation)
    "data_preparer_v2": AgentMetadata(
        id="data_preparer_v2",
        name="data preparer v2",
        description="Intelligent data preparation Agent understands requirements through LLM and calls tools to obtain data, which is stored in context for subsequent use.",
        category=AgentCategory.ANALYST,  # Changed to ANALYST since it needs to be called LLM
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        icon="🔧",
        color="#3498db",
        tags=["data", "Prepare", "Smart", "v2.0"],
        tools=["market", "fundamentals", "news", "social"],  # Bind all data tools
        default_tools=["market", "fundamentals", "news", "social"],
        max_tool_calls=10,  # Allow multiple tool calls
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code", required=True),
            AgentInput(name="analysis_date", type="string", description="Analysis date", required=False),
            AgentInput(name="data_requirements", type="string", description="Data requirement description", required=False),
        ],
        outputs=[
            AgentOutput(name="context", type="string", description="Prepared data context"),
            AgentOutput(name="data_summary", type="string", description="Data summary"),
            AgentOutput(name="tools_used", type="array", description="List of tools used"),
        ],
        requires_tools=True,  # need tools
        output_field="context",
        report_label=" [Data preparation]",
        node_name="data preparer v2",
        execution_order=0,  # executed first
    ),
}

