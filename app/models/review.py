"""
Transaction review data model
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId

from app.utils.timezone import now_tz


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        return {"type": "string"}


class ReviewType(str, Enum):
    """Review type"""
    SINGLE_TRADE = "single_trade"      # Single transaction review
    COMPLETE_TRADE = "complete_trade"  # Complete transaction review (buy to sell)
    PERIODIC = "periodic"              # Periodic review


class PeriodType(str, Enum):
    """Periodic review cycle type"""
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class ReviewStatus(str, Enum):
    """Review status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ==================== Transaction information related models ====================

class TradeRecord(BaseModel):
    """transaction history"""
    trade_id: Optional[str] = None
    side: str                           # buy/sell
    quantity: int
    price: float
    amount: float = 0.0
    commission: float = 0.0
    timestamp: str
    pnl: float = 0.0                    # Realized profit and loss (when selling)


class TradeInfo(BaseModel):
    """Transaction information summary"""
    code: str
    name: Optional[str] = None
    market: str = "CN"
    currency: str = "CNY"
    trades: List[TradeRecord] = Field(default_factory=list)
    
    # Aggregate data
    total_buy_quantity: int = 0
    total_buy_amount: float = 0.0
    avg_buy_price: float = 0.0
    total_sell_quantity: int = 0
    total_sell_amount: float = 0.0
    avg_sell_price: float = 0.0
    
    # Profit and loss
    realized_pnl: float = 0.0           # Realized profit and loss (part sold)
    realized_pnl_pct: float = 0.0       # Realized profit and loss percentage
    unrealized_pnl: float = 0.0         # 🆕 Unrealized profit and loss (position portion)
    unrealized_pnl_pct: float = 0.0     # 🆕 Unrealized profit and loss percentage
    total_commission: float = 0.0

    # Position status
    is_holding: bool = False            # 🆕 Are you still holding a position?
    current_price: Optional[float] = None  # 🆕 Current price (when the position is open)
    remaining_quantity: int = 0         # 🆕 Remaining position quantity

    # Position period
    first_buy_date: Optional[str] = None
    last_sell_date: Optional[str] = None
    holding_days: int = 0


class MarketSnapshot(BaseModel):
    """Market data snapshot"""
    # Quotes at the time of purchase
    buy_date_open: Optional[float] = None
    buy_date_high: Optional[float] = None
    buy_date_low: Optional[float] = None
    buy_date_close: Optional[float] = None
    
    # Quotes when selling
    sell_date_open: Optional[float] = None
    sell_date_high: Optional[float] = None
    sell_date_low: Optional[float] = None
    sell_date_close: Optional[float] = None
    
    # Quotes during the position period
    period_high: Optional[float] = None
    period_high_date: Optional[str] = None
    period_low: Optional[float] = None
    period_low_date: Optional[str] = None
    
    # Best buying and selling point
    optimal_buy_price: Optional[float] = None
    optimal_sell_price: Optional[float] = None
    
    # K Line data (for chart display)
    kline_data: List[dict] = Field(default_factory=list)


# ==================== AI Analysis results model ====================

class AITradeReview(BaseModel):
    """AI Transaction review results

    Scoring system description:
    - overall_score: Overall rating = (timing_score + position_score + emotion_score + attribution_score) / 4
    - timing_score: Timing score (buy and sell timing)
    - position_score: Position Rating (Position Management)
    - emotion_score: Emotion and Discipline Score (Emotional Control + Discipline enforcement)
    - attribution_score: Attribution scoring (revenue source analysis)
    - discipline_score: Deprecated, retained for backwards compatibility only (discipline evaluation has been merged into emotion_score)
    """
    overall_score: int = Field(0, ge=0, le=100, description="Overall rating")
    timing_score: int = Field(0, ge=0, le=100, description="timing score")
    position_score: int = Field(0, ge=0, le=100, description="Position score")
    emotion_score: int = Field(0, ge=0, le=100, description="Emotion and Discipline Score (Emotional Control 50% + Discipline enforcement 50%)")
    attribution_score: int = Field(0, ge=0, le=100, description="Attribution score")
    discipline_score: int = Field(0, ge=0, le=100, description="[Deprecated] Discipline score (merged into emotion_score, retained for compatibility only)")

    summary: str = ""                                # Summary
    strengths: List[str] = Field(default_factory=list)  # Things done well
    weaknesses: List[str] = Field(default_factory=list) # areas for improvement
    suggestions: List[str] = Field(default_factory=list) # Compatible with old field names, the actual semantics are review improvements

    timing_analysis: str = ""                        # Timing analysis details
    position_analysis: str = ""                      # Position analysis details
    emotion_analysis: str = ""                       # Sentiment analysis details
    attribution_analysis: str = ""                   # Attribution analysis details

    # Income comparison
    actual_pnl: float = 0.0                          # Actual income
    optimal_pnl: float = 0.0                         # Theoretical optimal return
    missed_profit: float = 0.0                       # missed gains
    avoided_loss: float = 0.0                        # Avoided losses

    # 🆕 Trading plan execution status (when a trading plan is associated)
    plan_adherence: Optional[str] = None             # Where plans are executed well
    plan_deviation: Optional[str] = None             # deviation from plan


# ==================== Review report model ====================

class TradeReviewReport(BaseModel):
    """Transaction review report (trade_reviews collection)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    review_id: str
    user_id: str
    review_type: ReviewType = ReviewType.COMPLETE_TRADE
    
    # transaction information
    trade_info: TradeInfo = Field(default_factory=TradeInfo)
    
    # Market data snapshot
    market_snapshot: MarketSnapshot = Field(default_factory=MarketSnapshot)
    
    # AI Analyze results
    ai_review: AITradeReview = Field(default_factory=AITradeReview)
    
    # Status and metadata
    status: ReviewStatus = ReviewStatus.PENDING
    error_message: Optional[str] = None
    execution_time: float = 0.0
    
    # Case related
    is_case_study: bool = False
    tags: List[str] = Field(default_factory=list)
    source: str = Field(default="paper", description="data source: paper(simulated trading) or position(Position operation)")

    # Trading plan association
    trading_system_id: Optional[str] = Field(None, description="Associated trading plans ID")
    trading_system_name: Optional[str] = Field(None, description="Associated trading plan name")

    created_at: datetime = Field(default_factory=now_tz)
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda v: v.isoformat()}
    )


# ==================== Staged review model ====================

class TradingStatistics(BaseModel):
    """Transaction statistics"""
    total_trades: int = 0                # total number of transactions
    winning_trades: int = 0              # Profit times
    losing_trades: int = 0               # Number of losses
    win_rate: float = 0.0                # winning rate

    total_pnl: float = 0.0               # Total profit and loss
    avg_profit: float = 0.0              # average profit
    avg_loss: float = 0.0                # average loss
    profit_loss_ratio: float = 0.0       # profit-loss ratio

    max_single_profit: float = 0.0       # Maximum single profit
    max_single_loss: float = 0.0         # Maximum single loss
    max_drawdown: float = 0.0            # maximum drawdown

    avg_holding_days: float = 0.0        # Average holding days
    total_commission: float = 0.0        # total handling fee


class AIPeriodicReview(BaseModel):
    """AI Phased review results"""
    overall_score: int = Field(0, ge=0, le=100)
    summary: str = ""

    trading_style: str = ""              # Trading style analysis
    common_mistakes: List[str] = Field(default_factory=list)   # Common mistakes
    improvement_areas: List[str] = Field(default_factory=list) # Review and improvement directions
    action_plan: List[str] = Field(default_factory=list)       # Compatible with old field names, the actual semantics are subsequent observations

    best_trade: Optional[str] = None     # Best Trading Analysis
    worst_trade: Optional[str] = None    # Worst trade analysis


class TradeSummaryItem(BaseModel):
    """transaction summary item"""
    code: str
    name: Optional[str] = None
    side: str
    quantity: int
    price: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    timestamp: str


class PeriodicReviewReport(BaseModel):
    """Periodic review report (periodic_reviews collection)"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    review_id: str
    user_id: str

    # Review cycle
    period_type: PeriodType = PeriodType.MONTH
    period_start: datetime
    period_end: datetime

    # data source: paper(simulated trading) or position(Position operation)
    source: str = "paper"

    # Transaction statistics
    statistics: TradingStatistics = Field(default_factory=TradingStatistics)

    # Summary of transaction details
    trades_summary: List[TradeSummaryItem] = Field(default_factory=list)

    # AI analysis
    ai_review: AIPeriodicReview = Field(default_factory=AIPeriodicReview)

    # Status and metadata
    status: ReviewStatus = ReviewStatus.PENDING
    error_message: Optional[str] = None
    execution_time: float = 0.0

    created_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda v: v.isoformat()}
    )


# ==================== API request/response model ====================

class CreateTradeReviewRequest(BaseModel):
    """Create a transaction review request"""
    trade_ids: List[str] = Field(..., min_length=1, description="List of transaction IDs to be reviewed")
    review_type: ReviewType = ReviewType.COMPLETE_TRADE
    code: Optional[str] = Field(None, description="Stock symbol (inferred from transaction records if not provided)")
    source: str = Field("paper", description="data source: paper(simulated trading) or position(Position operation)")
    trading_system_id: Optional[str] = Field(None, description="The associated trading plan ID, if provided then checked against the trading plan rules")
    use_workflow: Optional[bool] = Field(None, description="Whether to use workflow engine (v2.0). None means use environment variable settings")


class CreatePeriodicReviewRequest(BaseModel):
    """Create a staged review request"""
    period_type: PeriodType = PeriodType.MONTH
    start_date: str = Field(..., description="start date YYYY-MM-DD")
    end_date: str = Field(..., description="end date YYYY-MM-DD")
    source: str = Field("paper", description="data source: paper(simulated trading) or position(Position operation)")


class SaveAsCaseRequest(BaseModel):
    """Save as case request"""
    review_id: str
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    source: Optional[str] = Field(None, description="data source: paper(simulated trading) or position(Position operation), If not provided, it will be read from the review report.")


class TradeReviewResponse(BaseModel):
    """Transaction review response"""
    review_id: str
    status: ReviewStatus
    trade_info: Optional[TradeInfo] = None
    ai_review: Optional[AITradeReview] = None
    market_snapshot: Optional[MarketSnapshot] = None
    execution_time: float = 0.0
    created_at: Optional[datetime] = None


class PeriodicReviewResponse(BaseModel):
    """Phased review response"""
    review_id: str
    status: ReviewStatus
    period_type: PeriodType
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    statistics: Optional[TradingStatistics] = None
    ai_review: Optional[AIPeriodicReview] = None
    execution_time: float = 0.0
    created_at: Optional[datetime] = None


class ReviewListItem(BaseModel):
    """Review list items"""
    review_id: str
    review_type: str
    code: Optional[str] = None
    name: Optional[str] = None
    realized_pnl: float = 0.0
    overall_score: int = 0
    status: str
    is_case_study: bool = False
    created_at: Optional[datetime] = None

