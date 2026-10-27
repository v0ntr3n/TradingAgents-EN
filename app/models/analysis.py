"""
Analyze related data models
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum
from bson import ObjectId
from .user import PyObjectId
from app.utils.timezone import now_tz
from .agent_growth import TaskGrowthContext


class AnalysisStatus(str, Enum):
    """Analysis status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"  # Pending status (unfinished tasks after service restart)


class BatchStatus(str, Enum):
    """Batch status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisEngine(str, Enum):
    """Analysis engine type"""
    LEGACY = "legacy"       # old engine: TradingAgentsGraph
    UNIFIED = "unified"     # new engine: UnifiedAnalysisService + WorkflowEngine
    V2 = "v2"               # v2.0 engine: Using v2.0 workflow template


class AnalysisParameters(BaseModel):
    """Analyze parametric models

    Research depth description:
    - fast: 1 Level - Quick Analysis (2-4 minutes)
    - Basics: 2 Level - Basic Analysis (4-6 minutes)
    - Standard: 3 Level - Standard Analysis (6-10 minutes, recommended)
    - Depth: 4 Level - In-Depth Analysis (10-15 minutes)
    - Comprehensive: 5 Level - Comprehensive Analysis (15-25 minutes)

    Engine selection (AB test):
    - legacy: Use old engine TradingAgentsGraph (Default)
    - unified: Use the new unified engine WorkflowEngine (LangGraph dynamic build)
    """
    market_type: str = "A shares"
    analysis_date: Optional[datetime] = None
    research_depth: str = "Standard"  # Use level 3 standard analysis by default (recommended)
    selected_analysts: List[str] = Field(default_factory=lambda: ["market", "fundamentals", "news", "social"])
    custom_prompt: Optional[str] = None
    include_sentiment: bool = True
    include_risk: bool = True
    language: str = "zh-CN"
    # Model configuration
    quick_analysis_model: Optional[str] = "qwen-turbo"
    deep_analysis_model: Optional[str] = "qwen-max"
    # Engine selection (default uses v2.0 engine)
    engine: AnalysisEngine = Field(
        default=AnalysisEngine.V2,
        description="Analysis engine: v2=v2.0 Engine (recommended), unified=unified engine, legacy=Old engine (obsolete)"
    )
    # New engine workflow configuration
    workflow_id: Optional[str] = Field(
        default=None,
        description="Workflow ID (Only valid for unified engine), If not specified, the system default workflow will be used."
    )
    # Execution trajectory switch (single mission level)
    enable_trace: bool = Field(
        default=False,
        description="Whether to record the execution trace of this analysis (full text of Prompt, original return from LLM, verification results). It is turned off by default and can be turned on when troubleshooting problems."
    )


class AnalysisResult(BaseModel):
    """Analysis results model"""
    analysis_id: Optional[str] = None
    summary: Optional[str] = None
    recommendation: Optional[str] = None
    confidence_score: Optional[float] = None
    risk_level: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    detailed_analysis: Optional[Dict[str, Any]] = None
    charts: List[str] = Field(default_factory=list)
    tokens_used: int = 0
    execution_time: float = 0.0
    error_message: Optional[str] = None
    model_info: Optional[str] = None  # 🔥 Add model information fields


class AnalysisTask(BaseModel):
    """Analysis task model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    task_id: str = Field(..., description="Task unique identifier")
    batch_id: Optional[str] = None
    user_id: PyObjectId
    symbol: str = Field(..., description="6 stock code")
    stock_code: Optional[str] = Field(None, description="Stock code(Deprecated,Use symbol)")
    stock_name: Optional[str] = None
    status: AnalysisStatus = AnalysisStatus.PENDING

    progress: int = Field(default=0, ge=0, le=100, description="Task progress 0-100")

    # Timestamp
    created_at: datetime = Field(default_factory=now_tz)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # execution information
    worker_id: Optional[str] = None
    parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)
    result: Optional[AnalysisResult] = None
    
    # Retry mechanism
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


class AnalysisBatch(BaseModel):
    """Analyze batch models"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    batch_id: str = Field(..., description="Batch unique identifier")
    user_id: PyObjectId
    title: str = Field(..., description="Batch title")
    description: Optional[str] = None
    status: BatchStatus = BatchStatus.PENDING
    
    # Task statistics
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    progress: int = Field(default=0, ge=0, le=100, description="overall progress 0-100")
    
    # Timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Configuration parameters
    parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)
    
    # summary of results
    results_summary: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True
    )


class StockInfo(BaseModel):
    """stock information model"""
    symbol: str = Field(..., description="6 stock code")
    code: Optional[str] = Field(None, description="Stock code(Deprecated,Use symbol)")
    name: str = Field(..., description="Stock name")
    market: str = Field(..., description="market type")
    industry: Optional[str] = None
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    price: Optional[float] = None
    change_percent: Optional[float] = None


# API request/response model

class SingleAnalysisRequest(BaseModel):
    """Single stock analysis request"""
    symbol: Optional[str] = Field(None, description="6 stock code")
    stock_code: Optional[str] = Field(None, description="Stock code(Deprecated,Use symbol)")
    parameters: Optional[AnalysisParameters] = None

    def get_symbol(self) -> str:
        """Get stock code(Compatible with old fields)"""
        return self.symbol or self.stock_code or ""


class BatchAnalysisRequest(BaseModel):
    """Batch analysis requests"""
    title: str = Field(..., description="Batch title")
    description: Optional[str] = None
    symbols: Optional[List[str]] = Field(None, min_items=1, max_items=10, description="List of stock symbols (up to 10)")
    stock_codes: Optional[List[str]] = Field(None, min_items=1, max_items=10, description="Stock code list(Deprecated,Use symbols, up to 10)")
    parameters: Optional[AnalysisParameters] = None

    def get_symbols(self) -> List[str]:
        """Get a list of stock symbols(Compatible with old fields)"""
        return self.symbols or self.stock_codes or []


class AnalysisTaskResponse(BaseModel):
    """Analyze task responses"""
    task_id: str
    batch_id: Optional[str]
    symbol: str
    stock_code: Optional[str] = None  # Compatible fields
    stock_name: Optional[str]
    status: AnalysisStatus
    progress: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[AnalysisResult]

    @field_serializer('created_at', 'started_at', 'completed_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class AnalysisBatchResponse(BaseModel):
    """Analyze batch responses"""
    batch_id: str
    title: str
    description: Optional[str]
    status: BatchStatus
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    progress: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    parameters: AnalysisParameters

    @field_serializer('created_at', 'started_at', 'completed_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class AnalysisHistoryQuery(BaseModel):
    """Analyze historical query parameters"""
    status: Optional[AnalysisStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    symbol: Optional[str] = None
    stock_code: Optional[str] = None  # Compatible fields
    batch_id: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    def get_symbol(self) -> Optional[str]:
        """Get stock code(Compatible with old fields)"""
        return self.symbol or self.stock_code


# ==================== Unified analysis task model (v2.0) ====================

class AnalysisTaskType(str, Enum):
    """Analysis task type

    Supports multiple analysis processes, each type corresponds to a workflow template
    """
    STOCK_ANALYSIS = "stock_analysis"           # Stock analysis (complete TradingAgents process)
    ETF_ANALYSIS = "etf_analysis"               # ETF Analysis (simplifying the process)
    POSITION_ANALYSIS = "position_analysis"     # Position analysis
    TRADE_REVIEW = "trade_review"               # Transaction review
    PORTFOLIO_HEALTH = "portfolio_health"       # Portfolio health analysis
    RISK_ASSESSMENT = "risk_assessment"         # risk assessment
    MARKET_OVERVIEW = "market_overview"         # Market overview
    SECTOR_ANALYSIS = "sector_analysis"         # Sector analysis
    # More types can be expanded in the future...


class UnifiedAnalysisTask(BaseModel):
    """Unified analysis task model (v2.0)

    Design goals:
    1. Supports a variety of analysis processes (stock analysis, position analysis, transaction review, etc.)
    2. Unified task management and status tracking
    3. Flexible parameter configuration and engine selection
    4. Backwards compatible with existing systems

    Usage example:
        # Stock analysis tasks
        task = UnifiedAnalysisTask(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params={
                "symbol": "000858",
                "market_type": "cn",
                "research_depth": "Standard"
            }
        )

        # Position analysis task
        task = UnifiedAnalysisTask(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            task_type=AnalysisTaskType.POSITION_ANALYSIS,
            task_params={
                "position_id": "pos_123",
                "research_depth": "Depth"
            }
        )
    """
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    task_id: str = Field(..., description="Task unique identifier")
    user_id: PyObjectId = Field(..., description="User ID")

    # Task type and parameters
    task_type: AnalysisTaskType = Field(..., description="Task type")
    task_params: Dict[str, Any] = Field(default_factory=dict, description="Task parameters (JSON format, different according to task_type)")

    # Execute configuration
    workflow_id: Optional[str] = Field(None, description="Workflow ID (if using a workflow engine)")
    engine_type: str = Field("auto", description="Engine type: auto(automatic selection)/workflow(workflow engine)/legacy(old engine)/llm(direct LLM)")
    preference_type: str = Field("neutral", description="Analyze preferences: aggressive(Radical)/neutral(Neutral)/conservative(conservative)")

    # status and progress
    status: AnalysisStatus = Field(default=AnalysisStatus.PENDING, description="Task status")
    progress: int = Field(default=0, ge=0, le=100, description="Task progress 0-100")
    current_step: Optional[str] = Field(None, description="Current execution step (short name)")
    message: Optional[str] = Field(None, description="Detailed description of current step")

    # result
    result: Optional[Dict[str, Any]] = Field(None, description="Analysis results (JSON format)")
    growth_context: Optional[TaskGrowthContext] = Field(None, description="Summary of growth extraction results")

    # metadata
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    started_at: Optional[datetime] = Field(None, description="start time")
    completed_at: Optional[datetime] = Field(None, description="completion time")
    execution_time: float = Field(default=0.0, description="Execution time (seconds)")

    # Error handling
    error_message: Optional[str] = Field(None, description="error message")
    retry_count: int = Field(default=0, description="Number of retries")
    max_retries: int = Field(default=3, description="Maximum number of retries")

    # Resource usage
    tokens_used: int = Field(default=0, description="Number of Tokens used")
    cost: float = Field(default=0.0, description="Cost (yuan)")

    # Batch information (optional)
    batch_id: Optional[str] = Field(None, description="Batch ID (if it belongs to a batch task)")

    # Work node information (optional)
    worker_id: Optional[str] = Field(None, description="execution node ID")

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={
            ObjectId: str,
            datetime: lambda dt: dt.isoformat() if dt else None
        }
    )

    @field_serializer('created_at', 'started_at', 'completed_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """serialized datetime"""
        if dt:
            return dt.isoformat()
        return None
