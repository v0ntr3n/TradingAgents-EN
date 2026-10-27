"""
Data models related to position research
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum
from bson import ObjectId
from .user import PyObjectId
from app.utils.timezone import now_tz


class PositionSource(str, Enum):
    """Position data source"""
    MANUAL = "manual"      # Manual entry
    IMPORT = "import"      # Batch import
    PAPER = "paper"        # Sync from simulated trading


class PortfolioAnalysisStatus(str, Enum):
    """Position research status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PositionAction(str, Enum):
    """Position research observation mapping (historical field names are for study and research reference only and do not constitute trading advice)"""
    ADD = "add"           # Optimistic/Add positions
    REDUCE = "reduce"     # Prudence/reduce positions
    HOLD = "hold"         # Neutral/Hold
    CLEAR = "clear"       # Prudence/Clearout


class CapitalTransactionType(str, Enum):
    """Fund transaction type"""
    INITIAL = "initial"       # Initial capital
    DEPOSIT = "deposit"       # Deposit
    WITHDRAW = "withdraw"     # Withdraw funds
    DIVIDEND = "dividend"     # Dividends
    ADJUSTMENT = "adjustment" # Manual adjustment


class PositionChangeType(str, Enum):
    """Position change type"""
    BUY = "buy"               # Buy (new position)
    ADD = "add"               # Add to position
    REDUCE = "reduce"         # Reduce positions
    SELL = "sell"             # Sell (clearance)
    ADJUST = "adjust"         # Adjustment (modification of cost price, etc.)


# ==================== Position change record model ====================

class PositionChange(BaseModel):
    """Position change record"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    position_id: Optional[str] = None          # Associated position ID (may be empty after liquidation)
    code: str                                  # Stock code
    name: str                                  # Stock name
    market: str                                # market
    currency: str = "CNY"                      # Currency
    change_type: PositionChangeType            # Change type

    # before change
    quantity_before: int = 0                   # Quantity before change
    cost_price_before: float = 0.0             # Cost price before changes
    cost_value_before: float = 0.0             # Cost amount before changes

    # After the change
    quantity_after: int = 0                    # Quantity after change
    cost_price_after: float = 0.0              # Cost price after change
    cost_value_after: float = 0.0              # Variable cost amount

    # Change amount
    quantity_change: int = 0                   # Quantity changes (positive numbers to buy/increase positions, negative numbers to reduce/sell positions)
    cash_change: float = 0.0                   # Fund changes (positive numbers release funds, negative numbers occupy funds)

    # If it is selling/reducing the position, record the selling price and profit and loss
    trade_price: Optional[float] = None        # transaction price
    realized_profit: Optional[float] = None    # Realized profit and loss

    description: Optional[str] = None          # Description/Remarks
    trade_time: Optional[datetime] = None      # Transaction time (the time when the actual transaction occurs, manually entered by the user)
    created_at: datetime = Field(default_factory=now_tz)  # record creation time

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

    @field_serializer('id')
    def serialize_id(self, v):
        return str(v) if v else None


class PositionChangeUpdate(BaseModel):
    """Single transaction modification request (used to correct input errors: quantity, unit price)"""
    quantity: int = Field(..., gt=0, description="Quantity (buy/increase position is a positive number, reduce position/sell is the quantity for this operation)")
    price: float = Field(..., gt=0, description="Unit price (buying price or selling price)")
    trade_time: Optional[datetime] = Field(None, description="trading hours")


class PositionChangeResponse(BaseModel):
    """Position change response"""
    id: str
    position_id: Optional[str] = None
    code: str
    name: str
    market: str
    currency: str
    change_type: str
    quantity_before: int
    cost_price_before: float
    cost_value_before: float
    quantity_after: int
    cost_price_after: float
    cost_value_after: float
    quantity_change: int
    cash_change: float
    trade_price: Optional[float] = None
    realized_profit: Optional[float] = None
    description: Optional[str] = None
    trade_time: Optional[datetime] = None  # Transaction time (the time when the actual transaction occurs)
    created_at: datetime  # record creation time


# ==================== Capital account data model ====================

class CapitalTransaction(BaseModel):
    """Fund transaction records"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    transaction_type: CapitalTransactionType
    amount: float                              # Amount (positive number is deposit, negative number is withdrawal)
    currency: str = "CNY"                      # Currency
    balance_before: float                      # balance before trade
    balance_after: float                       # Balance after transaction
    description: Optional[str] = None          # Description
    created_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

    @field_serializer('id')
    def serialize_id(self, v):
        return str(v) if v else None


class RealAccount(BaseModel):
    """User position capital account (real_accounts collection)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str

    # Multi-currency cash account
    cash: Dict[str, float] = Field(default_factory=lambda: {
        "CNY": 0.0,
        "HKD": 0.0,
        "USD": 0.0
    })

    # Initial funding record (used to calculate yield)
    initial_capital: Dict[str, float] = Field(default_factory=lambda: {
        "CNY": 0.0,
        "HKD": 0.0,
        "USD": 0.0
    })

    # Cumulative deposit
    total_deposit: Dict[str, float] = Field(default_factory=lambda: {
        "CNY": 0.0,
        "HKD": 0.0,
        "USD": 0.0
    })

    # Cumulative withdrawals
    total_withdraw: Dict[str, float] = Field(default_factory=lambda: {
        "CNY": 0.0,
        "HKD": 0.0,
        "USD": 0.0
    })

    # Account settings
    settings: Dict[str, Any] = Field(default_factory=lambda: {
        "default_market": "CN",
        "max_position_pct": 30.0,      # Maximum position ratio of a single stock
        "max_loss_pct": 10.0           # Maximum loss tolerance
    })

    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

    @field_serializer('id')
    def serialize_id(self, v):
        return str(v) if v else None


# ==================== Funding Account Request/Response Model ====================

class AccountInitRequest(BaseModel):
    """Initialize funding account request"""
    initial_capital: float = Field(..., gt=0, description="Initial funding amount")
    currency: str = Field("CNY", description="currency type")


class AccountTransactionRequest(BaseModel):
    """Fund transaction request (deposit/withdrawal)"""
    transaction_type: CapitalTransactionType
    amount: float = Field(..., gt=0, description="Amount (positive number)")
    currency: str = Field("CNY", description="currency type")
    description: Optional[str] = None


class AccountSettingsRequest(BaseModel):
    """Update account settings request"""
    max_position_pct: Optional[float] = Field(None, ge=5, le=100)
    max_loss_pct: Optional[float] = Field(None, ge=1, le=50)
    default_market: Optional[str] = None


class AccountSummary(BaseModel):
    """Account summary"""
    # Cash
    cash: Dict[str, float]
    # Initial capital
    initial_capital: Dict[str, float]
    # Cumulative deposit
    total_deposit: Dict[str, float]
    # Cumulative withdrawals
    total_withdraw: Dict[str, float]
    # net deposit = initial + Deposit - Withdraw
    net_capital: Dict[str, float]
    # Position market value
    positions_value: Dict[str, float]
    # total assets = Cash + Position market value
    total_assets: Dict[str, float]
    # income = Total Assets - Net Deposits
    profit: Dict[str, float]
    # Yield = Profit / Net deposit
    profit_pct: Dict[str, float]
    # Account settings
    settings: Dict[str, Any]


# ==================== Position data model ====================

class RealPosition(BaseModel):
    """User position data model (real_positions collection)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    code: str                              # Stock code
    name: Optional[str] = None             # Stock name
    market: str = "CN"                     # market: CN/HK/US
    currency: str = "CNY"                  # Currency: CNY/HKD/USD
    quantity: int                          # Position quantity
    cost_price: float                      # Cost price (before restoration, used for profit and loss calculation)
    original_avg_cost: Optional[float] = None  # Original average purchase price (unchanged for position reduction, used for investment evaluation)
    original_cost_price: Optional[float] = None  # Original cost price (actual transaction price without restoration of rights)
    price_adjust_type: Optional[str] = None     # Price restoration mark:None=Before restoration (default),"none"=Original unrestored rights
    buy_date: Optional[datetime] = None    # Purchase date
    industry: Optional[str] = None         # Industry
    notes: Optional[str] = None            # Remarks
    source: PositionSource = PositionSource.MANUAL
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


class PositionSnapshot(BaseModel):
    """Position snapshot (for analytical reporting)"""
    code: str
    name: Optional[str] = None
    market: str = "CN"
    quantity: int
    cost_price: float
    original_avg_cost: Optional[float] = None  # Average original purchase price (optional)
    original_cost_price: Optional[float] = None  # Original cost price (actual transaction price without restoration of rights)
    price_adjust_type: Optional[str] = None     # Price restoration mark
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    industry: Optional[str] = None
    holding_days: Optional[int] = None
    # Funding related (optional, for risk analysis)
    total_capital: Optional[float] = None          # Total user funds
    position_pct: Optional[float] = None           # Position proportion (%)
    # Fund occupation related
    cost_value: Optional[float] = None             # Amount of funds occupied (cost price*quantity)
    cost_pct: Optional[float] = None               # Fund occupation ratio (% of total assets)


class AccountSnapshot(BaseModel):
    """Funding account snapshot (for analytical reporting)"""
    total_assets: float = 0.0                      # Total assets (cash+Position market value)
    cash: float = 0.0                              # Cash available
    positions_value: float = 0.0                   # Position market value
    position_ratio: float = 0.0                    # Position ratio (position market value/total assets %)
    cash_ratio: float = 0.0                        # Cash ratio (%)
    initial_capital: float = 0.0                   # Initial capital
    net_capital: float = 0.0                       # Net invested capital
    total_profit: float = 0.0                      # Total profit and loss
    total_profit_pct: float = 0.0                  # Total return (%)
    currency: str = "CNY"                          # major currencies


class PortfolioSnapshot(BaseModel):
    """Portfolio position snapshot"""
    total_positions: int = 0
    total_value: float = 0.0
    total_cost: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    positions: List[PositionSnapshot] = Field(default_factory=list)
    # Fund account information
    account: Optional[AccountSnapshot] = None

    # Alias attribute, used for compatibility
    @property
    def total_market_value(self) -> float:
        """Total market capitalization (alias)"""
        return self.total_value

    @property
    def total_unrealized_pnl(self) -> float:
        """Total floating profit and loss (alias)"""
        return self.unrealized_pnl

    @property
    def total_unrealized_pnl_pct(self) -> float:
        """Total floating profit and loss percentage (alias)"""
        return self.unrealized_pnl_pct


# ==================== Analysis results model ====================

class IndustryDistribution(BaseModel):
    """Industry distribution"""
    industry: str
    value: float
    percentage: float
    count: int


class ConcentrationAnalysis(BaseModel):
    """concentration analysis"""
    stock_count: int = 0            # Number of stocks held
    top1_pct: float = 0.0           # The largest share of positions
    top3_pct: float = 0.0           # The proportion of the top three holdings
    top5_pct: float = 0.0           # The proportion of the top five holdings
    hhi_index: float = 0.0          # Herfindahl index
    industry_count: int = 0         # Number of industries involved


class AIAnalysisResult(BaseModel):
    """AI Analyze results"""
    summary: str = ""                          # Analysis summary
    strengths: List[str] = Field(default_factory=list)   # Advantages
    weaknesses: List[str] = Field(default_factory=list)  # Disadvantages
    suggestions: List[str] = Field(default_factory=list) # Suggestions
    detailed_report: str = ""                  # Detailed report


class PortfolioAnalysisReport(BaseModel):
    """Position research report (portfolio_analysis_reports collection)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    analysis_id: str                           # only research ID
    user_id: str
    analysis_type: str = "portfolio_health"    # Research Type
    analysis_date: str                         # Study date YYYY-MM-DD
    timestamp: datetime = Field(default_factory=now_tz)
    
    # Position snapshot
    portfolio_snapshot: PortfolioSnapshot = Field(default_factory=PortfolioSnapshot)
    
    # Research results
    health_score: float = 0.0                  # health score 0-100
    risk_level: str = "in"                     # risk level: low/medium/high
    industry_distribution: List[IndustryDistribution] = Field(default_factory=list)
    concentration_analysis: ConcentrationAnalysis = Field(default_factory=ConcentrationAnalysis)
    
    # AI Research
    ai_analysis: AIAnalysisResult = Field(default_factory=AIAnalysisResult)
    
    # execution information
    status: PortfolioAnalysisStatus = PortfolioAnalysisStatus.PENDING
    execution_time: float = 0.0
    tokens_used: int = 0
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


# ==================== API request/response model ====================

class PositionCreate(BaseModel):
    """Create a position request"""
    code: str = Field(..., description="Stock code")
    name: Optional[str] = Field(None, description="Stock name")
    market: str = Field("CN", description="market: CN/HK/US")
    quantity: int = Field(..., gt=0, description="Position quantity")
    cost_price: float = Field(..., gt=0, description="cost price")
    buy_date: Optional[datetime] = Field(None, description="Purchase date")
    notes: Optional[str] = Field(None, description="Remarks")


class PositionUpdate(BaseModel):
    """Update position request"""
    name: Optional[str] = None
    quantity: Optional[int] = Field(None, gt=0)
    cost_price: Optional[float] = Field(None, gt=0)
    buy_date: Optional[datetime] = None
    notes: Optional[str] = None


class PositionOperationType(str, Enum):
    """Position operation type"""
    ADD = "add"              # Add to position
    REDUCE = "reduce"        # Reduce positions
    DIVIDEND = "dividend"    # dividend
    SPLIT = "split"          # stock split
    MERGE = "merge"          # partnership
    ADJUST = "adjust"        # Adjust cost price


class PositionOperationRequest(BaseModel):
    """Position operation request"""
    operation_type: PositionOperationType = Field(..., description="Operation type")
    code: str = Field(..., description="Stock code")
    market: str = Field("CN", description="market: CN/HK/US")
    # Add/reduce position parameters
    quantity: Optional[int] = Field(None, gt=0, description="Quantity")
    price: Optional[float] = Field(None, gt=0, description="price")
    # Dividend parameters
    dividend_amount: Optional[float] = Field(None, ge=0, description="Dividend amount")
    # Stock split/consolidation parameters
    ratio: Optional[str] = Field(None, description="proportion, such as 2:1")
    # Adjust cost price parameters
    new_cost_price: Optional[float] = Field(None, gt=0, description="new cost price")
    # Common parameters
    operation_date: Optional[datetime] = Field(None, description="Operation date")
    notes: Optional[str] = Field(None, description="Remarks")


class PositionImport(BaseModel):
    """Import positions in batches"""
    positions: List[PositionCreate] = Field(..., min_length=1, max_length=50)


class QMTPositionImportRequest(BaseModel):
    """QMT Position coverage synchronization request"""
    account_id: str = Field(..., description="QMT Fund account")
    account_type: str = Field("STOCK", description="QMT Account type, such as STOCK/CREDIT")


class PortfolioAnalysisRequest(BaseModel):
    """Position research request"""
    include_paper: bool = Field(True, description="Whether to include simulated trading positions")
    research_depth: str = Field("Standard", description="Research depth")


class PositionResponse(BaseModel):
    """Position response"""
    id: str
    code: str
    name: Optional[str] = None
    market: str
    currency: str
    quantity: int
    cost_price: float
    original_avg_cost: Optional[float] = None  # Original average purchase price (unchanged for position reduction, used for investment evaluation)
    original_cost_price: Optional[float] = None  # Original cost price (actual transaction price without restoration of rights)
    price_adjust_type: Optional[str] = None     # Price restoration mark:None=Before regaining power,"none"=Original unrestored rights
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    buy_date: Optional[datetime] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    source: str
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at', 'buy_date')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        if dt:
            return dt.isoformat()
        return None


class PortfolioStatsResponse(BaseModel):
    """Position statistics response"""
    total_positions: int = 0
    total_value: float = 0.0
    total_cost: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    industry_distribution: List[IndustryDistribution] = Field(default_factory=list)
    market_distribution: Dict[str, float] = Field(default_factory=dict)


class PortfolioAnalysisResponse(BaseModel):
    """Position Research Response"""
    analysis_id: str
    status: PortfolioAnalysisStatus
    health_score: float = 0.0
    risk_level: str = "in"
    portfolio_snapshot: PortfolioSnapshot
    industry_distribution: List[IndustryDistribution] = Field(default_factory=list)
    concentration_analysis: ConcentrationAnalysis = Field(default_factory=ConcentrationAnalysis)
    ai_analysis: AIAnalysisResult = Field(default_factory=AIAnalysisResult)
    execution_time: float = 0.0
    created_at: datetime

    @field_serializer('created_at')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat()


# ==================== Single stock position research model ====================

class PositionAnalysisRequest(BaseModel):
    """Single Stock Position Research Request"""
    research_depth: str = "Standard"              # Research depth: Fast/Standard/Deep
    include_add_position: bool = True        # Whether to include position addition observation
    target_profit_pct: float = 20.0          # Target rate of return (%)
    # Related to the total amount of funds (used for risk research)
    total_capital: Optional[float] = Field(None, description="Total amount of investment funds")
    max_position_pct: float = Field(30.0, description="Maximum position ratio of a single stock (%)")
    max_loss_pct: float = Field(10.0, description="Maximum acceptable loss ratio (%)")

    # Investment preferences (for workflow engine selection of research style)
    risk_tolerance: str = Field("medium", description="risk appetite: low/medium/high")
    investment_horizon: str = Field("medium", description="investment period: short(short term)/medium(center line)/long(long term)")
    analysis_focus: str = Field("comprehensive", description="Analysis focus: technical(technical aspect)/fundamental(Fundamentals)/comprehensive(Comprehensive)")

    # Position type (differentiate between simulated trading and user positions)
    position_type: str = Field("real", description="Position type: real(User positions)/simulated(simulated trading)")


class PositionAnalysisByCodeRequest(BaseModel):
    """Analyze position requests by ticker (aggregate all positions in the same stock)"""
    code: str = Field(..., description="Stock code")
    market: str = Field("CN", description="market: CN/HK/US")
    research_depth: str = "Standard"
    include_add_position: bool = True
    target_profit_pct: float = 20.0
    total_capital: Optional[float] = None
    max_position_pct: float = 30.0
    max_loss_pct: float = 10.0

    # Investment preferences (for workflow engine selection of analysis style)
    risk_tolerance: str = Field("medium", description="risk appetite: low/medium/high")
    investment_horizon: str = Field("medium", description="investment period: short/medium/long")
    analysis_focus: str = Field("comprehensive", description="Analysis focus: technical/fundamental/comprehensive")

    # Position type
    position_type: str = Field("real", description="Position type: real/simulated")

    # Single stock analysis options
    use_stock_analysis: bool = Field(
        True,
        description="Whether to use the single stock analysis report as a reference.True: If there is a cached report, use it; if not, skip it;False: Do not use single stock analysis reports"
    )


class PriceTarget(BaseModel):
    """Price focus target (for study and research reference only, does not constitute trading advice)"""
    stop_loss_price: Optional[float] = None      # Risk focus price (historical field name)
    stop_loss_pct: Optional[float] = None        # risk concern ratio
    take_profit_price: Optional[float] = None    # Revenue focus price (historical field name)
    take_profit_pct: Optional[float] = None      # Revenue focus ratio
    breakeven_price: Optional[float] = None      # return price


class PositionRiskMetrics(BaseModel):
    """Position risk indicators"""
    position_pct: Optional[float] = None          # Position proportion (%)
    position_value: Optional[float] = None        # Position market value
    max_loss_amount: Optional[float] = None       # Maximum possible loss amount
    max_loss_impact_pct: Optional[float] = None   # Impact of maximum loss on total funds (%)
    available_add_amount: Optional[float] = None  # Amount that can be added (based on the maximum position limit)
    risk_level: str = "unknown"                   # risk level: low/medium/high/critical
    risk_summary: str = ""                        # Risk overview


class PositionUserView(BaseModel):
    """User version display model of position research"""
    conclusion: str = ""                          # One sentence conclusion
    position_context: str = ""                    # Description of the impact of holding positions
    key_points: List[str] = Field(default_factory=list)      # core basis
    risk_focus: List[str] = Field(default_factory=list)      # Risk warning
    watch_items: List[str] = Field(default_factory=list)     # Follow-up observation points
    uncertainty_note: str = ""                   # uncertainty statement


class PositionAppendixSection(BaseModel):
    """Position study appendix segmented content"""
    key: str
    title: str
    content: str = ""


class PositionAnalysisResult(BaseModel):
    """AI analysis results of single stock positions"""
    action: PositionAction = PositionAction.HOLD    # Research conclusion tendency mapping (historical field name)
    action_reason: str = ""                         # Reasons for research and observation
    confidence: float = 0.0                         # Confidence 0-100
    price_targets: PriceTarget = Field(default_factory=PriceTarget)
    risk_assessment: str = ""                       # risk review
    opportunity_assessment: str = ""                # opportunity assessment
    suggested_quantity: Optional[int] = None        # Recommended number of operations (obsolete, fixed at 0)
    suggested_amount: Optional[float] = None        # Recommended operation amount (obsolete, fixed at 0)
    detailed_analysis: str = ""                     # Detailed analysis
    # Risk indicators (calculated based on total funds)
    risk_metrics: Optional[PositionRiskMetrics] = None
    user_view: PositionUserView = Field(default_factory=PositionUserView)
    appendix_sections: List[PositionAppendixSection] = Field(default_factory=list)

    # Workflow engine extension fields
    summary: str = ""                               # Analysis summary (combining the results of each agent)
    recommendation: str = ""                        # Study Observation Details (Study Observer Output)
    source: str = "legacy"                          # Analyze sources: legacy(Old version LLM)/workflow_engine_v2(workflow engine)


class PositionAnalysisReport(BaseModel):
    """Single stock position research report (position_analysis_reports collection)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    analysis_id: str
    user_id: str
    position_id: str                               # Related positions ID

    # Position snapshot (optional, may be empty if research fails)
    position_snapshot: Optional[PositionSnapshot] = None

    # Research results
    status: PortfolioAnalysisStatus = PortfolioAnalysisStatus.PENDING
    ai_analysis: PositionAnalysisResult = Field(default_factory=PositionAnalysisResult)

    # Associated single-strand research task ID (new in Scheme 2)
    stock_analysis_task_id: Optional[str] = Field(None, description="Associated single-strand research tasks ID")

    # metadata
    execution_time: float = 0.0
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda v: v.isoformat()}
    )


class PositionAnalysisResponse(BaseModel):
    """Single Stock Position Research Response"""
    analysis_id: str
    position_id: str
    code: str
    name: Optional[str] = None
    status: str
    action: str = "hold"
    action_reason: str = ""
    confidence: float = 0.0
    price_targets: PriceTarget = Field(default_factory=PriceTarget)
    risk_assessment: str = ""
    opportunity_assessment: str = ""
    detailed_analysis: str = ""
    appendix_sections: List[PositionAppendixSection] = Field(default_factory=list)
    execution_time: float = 0.0
    created_at: str = ""
