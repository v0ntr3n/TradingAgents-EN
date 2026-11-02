from __future__ import annotations
import sys as _sys
__path__ = []
_self_mod = _sys.modules[__name__]
for _sub in ['stock_models', 'user', 'config', 'analysis', 'agent_growth', 'analysis_preference', 'analysis_profile', 'capability_index', 'channel_config', 'email', 'notification', 'operation_log', 'portfolio', 'project_memory', 'prompt_injection_policy', 'report_template', 'review', 'screening']:
    _sys.modules[f"app.models.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === stock_models.py ===
"""
Stock data model - extension based on existing collection
Adoption plan B: Extend fields based on existing collections to maintain backward compatibility
"""
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object


def to_str_id(v: Any) -> str:
    """ObjectId Convert string tool function"""
    try:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v)
    except Exception:
        return ""


# Enumeration type definition
MarketType = Literal["CN", "HK", "US"]  # market type
ExchangeType = Literal["SZSE", "SSE", "SEHK", "NYSE", "NASDAQ"]  # exchange
StockStatus = Literal["L", "D", "P"]  # Listing status: L-Listing D-Delisting P-Suspension
CurrencyType = Literal["CNY", "HKD", "USD"]  # currency type


class MarketInfo(BaseModel):
    """Market information structure - new fields"""
    market: MarketType = Field(..., description="market identification")
    exchange: ExchangeType = Field(..., description="Exchange code")
    exchange_name: str = Field(..., description="Exchange name")
    currency: CurrencyType = Field(..., description="trading currency")
    timezone: str = Field(..., description="time zone")
    trading_hours: Optional[Dict[str, Any]] = Field(None, description="trading hours")


class TechnicalIndicators(BaseModel):
    """Technical indicator structure - classification expansion design"""
    # trend indicator
    trend: Optional[Dict[str, float]] = Field(None, description="trend indicator")
    # Oscillator  
    oscillator: Optional[Dict[str, float]] = Field(None, description="Oscillator")
    # channel indicator
    channel: Optional[Dict[str, float]] = Field(None, description="channel indicator")
    # volume indicator
    volume: Optional[Dict[str, float]] = Field(None, description="volume indicator")
    # volatility indicator
    volatility: Optional[Dict[str, float]] = Field(None, description="volatility indicator")
    # Custom indicators
    custom: Optional[Dict[str, Any]] = Field(None, description="Custom indicators")


class StockBasicInfoExtended(BaseModel):
    """
    Stock basic information extension model - based on the existing stock_basic_info collection
    Uniformly use symbol as the main stock code field
    """
    # === Standardized fields (Main fields) ===
    symbol: str = Field(..., description="6 stock code", pattern=r"^\d{6}$")
    full_symbol: str = Field(..., description="Complete standardized code(Such as 000001.SZ)")
    name: str = Field(..., description="Stock name")

    # === Compatible fields (Stay backwards compatible) ===
    code: Optional[str] = Field(None, description="6 stock code(Deprecated,Use symbol)")

    # === Basic information fields ===
    area: Optional[str] = Field(None, description="area")
    industry: Optional[str] = Field(None, description="Industry")
    market: Optional[str] = Field(None, description="Exchange name")
    list_date: Optional[str] = Field(None, description="Listing date")
    sse: Optional[str] = Field(None, description="plate")
    sec: Optional[str] = Field(None, description="Sector")
    source: Optional[str] = Field(None, description="Data source")
    updated_at: Optional[datetime] = Field(None, description="Update time")

    # market cap field
    total_mv: Optional[float] = Field(None, description="Total market capitalization(billion)")
    circ_mv: Optional[float] = Field(None, description="Circulation market value(billion)")

    # financial indicators
    pe: Optional[float] = Field(None, description="P/E ratio")
    pb: Optional[float] = Field(None, description="price to book ratio")
    pe_ttm: Optional[float] = Field(None, description="rolling price to earnings ratio")
    pb_mrq: Optional[float] = Field(None, description="Latest price-to-book ratio")
    roe: Optional[float] = Field(None, description="ROE")

    # trading indicators
    turnover_rate: Optional[float] = Field(None, description="turnover rate%")
    volume_ratio: Optional[float] = Field(None, description="Quantity ratio")

    # === extension fields ===
    name_en: Optional[str] = Field(None, description="English name")
    
    # Add market information
    market_info: Optional[MarketInfo] = Field(None, description="market information")
    
    # Add new standardized fields
    board: Optional[str] = Field(None, description="Sector standardization")
    industry_code: Optional[str] = Field(None, description="Industry code")
    sector: Optional[str] = Field(None, description="Standardization of the sector (GICS industry)")
    delist_date: Optional[str] = Field(None, description="Delisting date")
    status: Optional[StockStatus] = Field(None, description="Listing status")
    is_hs: Optional[bool] = Field(None, description="Is it subject to Shanghai-Shenzhen-Hong Kong Stock Connect?")

    # Add equity information
    total_shares: Optional[float] = Field(None, description="total share capital")
    float_shares: Optional[float] = Field(None, description="circulating capital")

    # Hong Kong stocks specific fields
    lot_size: Optional[int] = Field(None, description="Number of shares per lot (specific to Hong Kong stocks)")

    # currency field
    currency: Optional[CurrencyType] = Field(None, description="trading currency")
    
    # version control
    data_version: Optional[int] = Field(None, description="Data version")
    
    class Config:
        # Allow extra fields to maintain backward compatibility
        extra = "allow"
        # Sample data
        json_schema_extra = {
            "example": {
                # Standardized fields
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "name": "Ping An Bank",

                # Basic information
                "area": "Shenzhen",
                "industry": "bank",
                "market": "Shenzhen Stock Exchange",
                "sse": "motherboard",
                "total_mv": 2500.0,
                "pe": 5.2,
                "pb": 0.8,

                # extension fields
                "market_info": {
                    "market": "CN",
                    "exchange": "SZSE",
                    "exchange_name": "Shenzhen Stock Exchange",
                    "currency": "CNY",
                    "timezone": "Asia/Shanghai"
                },
                "status": "L",
                "data_version": 1
            }
        }


class MarketQuotesExtended(BaseModel):
    """
    Real-time quotation extension model - based on the existing market_quotes collection
    Uniformly use symbol as the main stock code field
    """
    # === Standardized fields (Main fields) ===
    symbol: str = Field(..., description="6 stock code", pattern=r"^\d{6}$")
    full_symbol: Optional[str] = Field(None, description="Complete standardized code")
    market: Optional[MarketType] = Field(None, description="market identification")

    # === Compatible fields (Stay backwards compatible) ===
    code: Optional[str] = Field(None, description="6 stock code(Deprecated,Use symbol)")

    # === Quote field ===
    close: Optional[float] = Field(None, description="closing price")
    pct_chg: Optional[float] = Field(None, description="Increase or decrease%")
    amount: Optional[float] = Field(None, description="Turnover")
    open: Optional[float] = Field(None, description="opening price")
    high: Optional[float] = Field(None, description="highest price")
    low: Optional[float] = Field(None, description="lowest price")
    pre_close: Optional[float] = Field(None, description="previous closing price")
    trade_date: Optional[str] = Field(None, description="transaction date")
    updated_at: Optional[datetime] = Field(None, description="Update time")
    
    # Added quotation field
    current_price: Optional[float] = Field(None, description="current price(Same as close)")
    change: Optional[float] = Field(None, description="Changes")
    volume: Optional[float] = Field(None, description="Volume")
    turnover_rate: Optional[float] = Field(None, description="turnover rate")
    volume_ratio: Optional[float] = Field(None, description="Quantity ratio")
    
    # Five levels of market conditions
    bid_prices: Optional[List[float]] = Field(None, description="Buy price 1-5")
    bid_volumes: Optional[List[float]] = Field(None, description="Buy 1-5 quantities")
    ask_prices: Optional[List[float]] = Field(None, description="Sell 1-5 price")
    ask_volumes: Optional[List[float]] = Field(None, description="Sell 1-5 quantities")
    
    # Timestamp
    timestamp: Optional[datetime] = Field(None, description="Quote timestamp")
    
    # Data source and version
    data_source: Optional[str] = Field(None, description="Data source")
    data_version: Optional[int] = Field(None, description="Data version")
    
    class Config:
        extra = "allow"
        json_schema_extra = {
            "example": {
                # Standardized fields
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "market": "CN",

                # Quote field
                "close": 12.65,
                "pct_chg": 1.61,
                "amount": 1580000000,
                "open": 12.50,
                "high": 12.80,
                "low": 12.30,
                "trade_date": "2024-01-15",

                # extension fields
                "current_price": 12.65,
                "change": 0.20,
                "volume": 125000000
            }
        }


# Response model related to database operations
class StockBasicInfoResponse(BaseModel):
    """Stock basic information API response model"""
    success: bool = True
    data: Optional[StockBasicInfoExtended] = None
    message: str = ""


class MarketQuotesResponse(BaseModel):
    """Real-time market API response model"""
    success: bool = True
    data: Optional[MarketQuotesExtended] = None
    message: str = ""


class StockListResponse(BaseModel):
    """Stock List API response model"""
    success: bool = True
    data: Optional[List[StockBasicInfoExtended]] = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    message: str = ""

# === user.py ===
"""
User data model
"""

from datetime import datetime, timezone
from app.utils.timezone import now_tz
from typing import Optional, Dict, Any, Annotated, List, Union
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, ConfigDict, field_serializer
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object


def validate_object_id(v: Any) -> ObjectId:
    """Verify ObjectId"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def serialize_object_id(v: ObjectId) -> str:
    """Serialize ObjectId to string"""
    return str(v)


# Create custom ObjectId type
PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


class AssistantSettings(BaseModel):
    """Assistant personalization"""
    name: str = Field(default="Analysis Assistant", description="Assistant name")
    tone: str = Field(default="professional", description="tone style: professional/friendly/concise")
    custom_instructions: str = Field(default="", description="User-defined instructions", max_length=500)


class UserPreferences(BaseModel):
    """User preferences"""
    # Assistant personalization
    assistant_settings: AssistantSettings = Field(default_factory=AssistantSettings)

    # Analyze preferences
    default_market: str = "A shares"
    default_depth: str = "3"  # 1-5 level, level 3 is standard analysis (recommended)
    default_analysts: List[str] = Field(default_factory=lambda: ["market analyst", "fundamental analyst"])
    auto_refresh: bool = True
    refresh_interval: int = 30  # seconds
    risk_preference: str = "neutral"  # Risk Appetite:conservative(conservative) / neutral(Neutral) / aggressive(Radical)

    # Appearance settings
    ui_theme: str = "light"
    sidebar_width: int = 240

    # language and region
    language: str = "zh-CN"

    # Notification settings
    notifications_enabled: bool = True
    email_notifications: Union[bool, Dict[str, Any]] = False  # Compatible with old boolean and new dictionary formats
    desktop_notifications: bool = True
    analysis_complete_notification: bool = True
    system_maintenance_notification: bool = True


class FavoriteStock(BaseModel):
    """Stock watch list information"""
    stock_code: str = Field(..., description="Stock code")
    stock_name: str = Field(..., description="Stock name")
    market: str = Field(..., description="market type")
    added_at: datetime = Field(default_factory=now_tz, description="Add time")
    tags: List[str] = Field(default_factory=list, description="User tag")
    notes: str = Field(default="", description="User remarks")
    alert_price_high: Optional[float] = Field(None, description="price cap reminder")
    alert_price_low: Optional[float] = Field(None, description="Price lower limit reminder")


class User(BaseModel):
    """user model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False
    is_admin: bool = False
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)
    last_login: Optional[datetime] = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    
    # Quotas and limits
    daily_quota: int = 1000
    concurrent_limit: int = 3
    
    # Statistics
    total_analyses: int = 0
    successful_analyses: int = 0
    failed_analyses: int = 0

    # Stock Watchlist
    favorite_stocks: List[FavoriteStock] = Field(default_factory=list, description="User stock watch list list")
    
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class UserCreate(BaseModel):
    """Create user request model"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    password: str = Field(..., min_length=6, max_length=100)


class UserUpdate(BaseModel):
    """Update user request model"""
    email: Optional[str] = Field(None, pattern=r'^[^@]+@[^@]+\.[^@]+$')
    preferences: Optional[UserPreferences] = None
    daily_quota: Optional[int] = None
    concurrent_limit: Optional[int] = None


class UserResponse(BaseModel):
    """User response model"""
    id: str
    username: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime]
    preferences: UserPreferences
    daily_quota: int
    concurrent_limit: int
    total_analyses: int
    successful_analyses: int
    failed_analyses: int

    @field_serializer('created_at', 'last_login')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class UserLogin(BaseModel):
    """User login request model"""
    username: str
    password: str


class UserSession(BaseModel):
    """User session model"""
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    @field_serializer('created_at', 'expires_at', 'last_activity')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    user: UserResponse

# === config.py ===
"""
System configuration related data model
"""

from datetime import datetime, timezone
from app.utils.timezone import now_tz
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object


class ModelProvider(str, Enum):
    """Large model provider enum"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ZHIPU = "zhipu"
    QWEN = "qwen"
    BAIDU = "baidu"
    TENCENT = "tencent"
    GEMINI = "gemini"
    GLM = "glm"
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    DASHSCOPE = "dashscope"
    GOOGLE = "google"
    SILICONFLOW = "siliconflow"
    OPENROUTER = "openrouter"
    CUSTOM_OPENAI = "custom_openai"
    QIANFAN = "qianfan"
    LOCAL = "local"

    # 🆕 aggregation channel
    AI302 = "302ai"              # 302.AI
    AIHUBMIX = "aihubmix"        # AIHubMix
    ONEAPI = "oneapi"            # One API
    NEWAPI = "newapi"            # New API
    FASTGPT = "fastgpt"          # FastGPT
    CUSTOM_AGGREGATOR = "custom_aggregator"  # Custom aggregation channels


class LLMProvider(BaseModel):
    """Large model manufacturer configuration"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str = Field(..., description="Manufacturer s unique identifier")
    display_name: str = Field(..., description="display name")
    description: Optional[str] = Field(None, description="Manufacturer description")
    website: Optional[str] = Field(None, description="Official website address")
    api_doc_url: Optional[str] = Field(None, description="API Document address")
    logo_url: Optional[str] = Field(None, description="Logo address")
    is_active: bool = Field(True, description="Whether to enable")
    supported_features: List[str] = Field(default_factory=list, description="Supported features")
    default_base_url: Optional[str] = Field(None, description="Default API address")
    api_key: Optional[str] = Field(None, description="API key")
    api_secret: Optional[str] = Field(None, description="API Key (required by some manufacturers)")
    embedding_model: Optional[str] = Field(None, description="Embedding Model name (if embedding function is supported)")
    test_model: Optional[str] = Field(None, description="Test model name (used to test API connection, if not filled in, use the system default value)")
    extra_config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration parameters")

    # 🆕 Aggregation channel support
    is_aggregator: bool = Field(default=False, description="Whether it is an aggregation channel (such as 302.AI, OpenRouter)")
    aggregator_type: Optional[str] = Field(None, description="Aggregation channel type (openai_compatible/custom)")
    model_name_format: Optional[str] = Field(None, description="Model name format (such as:{provider}/{model}) ")

    created_at: Optional[datetime] = Field(default_factory=now_tz)
    updated_at: Optional[datetime] = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class ModelInfo(BaseModel):
    """Model information"""
    name: str = Field(..., description="Model identification name")
    display_name: str = Field(..., description="Model display name")
    description: Optional[str] = Field(None, description="Model description")
    context_length: Optional[int] = Field(None, description="context length")
    max_tokens: Optional[int] = Field(None, description="Maximum number of output tokens")
    input_price_per_1k: Optional[float] = Field(None, description="Enter price(every 1K tokens)")
    output_price_per_1k: Optional[float] = Field(None, description="output price(every 1K tokens)")
    currency: str = Field(default="CNY", description="currency unit")
    is_deprecated: bool = Field(default=False, description="Is it obsolete?")
    release_date: Optional[str] = Field(None, description="Release date")
    capabilities: List[str] = Field(default_factory=list, description="Capability label(Such as: vision, function_calling)")

    # 🆕 Aggregation channel model mapping support
    original_provider: Optional[str] = Field(None, description="Original manufacturer logo (for aggregation channels)")
    original_model: Optional[str] = Field(None, description="Original manufacturer model name (used for capability mapping)")


class ModelCatalog(BaseModel):
    """Model catalog"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    provider: str = Field(..., description="Manufacturer s logo")
    provider_name: str = Field(..., description="Manufacturer display name")
    models: List[ModelInfo] = Field(default_factory=list, description="Model list")
    created_at: Optional[datetime] = Field(default_factory=now_tz)
    updated_at: Optional[datetime] = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class LLMProviderRequest(BaseModel):
    """Large model manufacturer request"""
    name: str = Field(..., description="Manufacturer s unique identifier")
    display_name: str = Field(..., description="display name")
    description: Optional[str] = Field(None, description="Manufacturer description")
    website: Optional[str] = Field(None, description="Official website address")
    api_doc_url: Optional[str] = Field(None, description="API Document address")
    logo_url: Optional[str] = Field(None, description="Logo address")
    is_active: bool = Field(True, description="Whether to enable")
    supported_features: List[str] = Field(default_factory=list, description="Supported features")
    default_base_url: Optional[str] = Field(None, description="Default API address")
    api_key: Optional[str] = Field(None, description="API key")
    api_secret: Optional[str] = Field(None, description="API Key (required by some manufacturers)")
    embedding_model: Optional[str] = Field(None, description="Embedding Model name (if embedding function is supported)")
    test_model: Optional[str] = Field(None, description="Test model name (used to test API connection, if not filled in, use the system default value)")
    extra_config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration parameters")

    # 🆕 Aggregation channel support
    is_aggregator: bool = Field(default=False, description="Whether it is an aggregation channel")
    aggregator_type: Optional[str] = Field(None, description="Aggregation channel type")
    model_name_format: Optional[str] = Field(None, description="Model name format")


class LLMProviderResponse(BaseModel):
    """Large model manufacturers respond"""
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    website: Optional[str] = None
    api_doc_url: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool
    supported_features: List[str]
    default_base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    embedding_model: Optional[str] = None
    test_model: Optional[str] = None
    extra_config: Dict[str, Any] = Field(default_factory=dict)

    # 🆕 Aggregation channel support
    is_aggregator: bool = False
    aggregator_type: Optional[str] = None
    model_name_format: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DataSourceType(str, Enum):
    """
    Data source type enumeration

    NOTE: This enum is kept in sync with tradingagents.constants.DataSourceCode
    When adding a new data source, please first register it in tradingagents/constants/data_sources.py
    """
    # cache data source
    MONGODB = "mongodb"

    # China market data source
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"

    # US stock data source
    FINNHUB = "finnhub"
    YAHOO_FINANCE = "yahoo_finance"
    ALPHA_VANTAGE = "alpha_vantage"
    IEX_CLOUD = "iex_cloud"

    # Professional data source
    WIND = "wind"
    CHOICE = "choice"
    QMT = "qmt"

    # Other data sources
    QUANDL = "quandl"
    LOCAL_FILE = "local_file"
    LOCAL = "local"  # Local data (users import via API)
    CUSTOM = "custom"


class DatabaseType(str, Enum):
    """Database type enum"""
    MONGODB = "mongodb"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    SQLITE = "sqlite"


class LLMConfig(BaseModel):
    """Large model configuration"""
    config_id: Optional[str] = Field(None, description="Model configuration is unique ID")
    provider: str = Field(default="openai", description="Supplier identification (supports dynamic addition)")
    model_name: str = Field(..., description="Model name/code")
    model_display_name: Optional[str] = Field(None, description="Model display name")
    api_key: Optional[str] = Field(None, description="API key(Optional, priority is given to obtaining configuration from the manufacturer.)")
    api_base: Optional[str] = Field(None, description="API Basics URL")
    max_tokens: int = Field(default=8000, description="Maximum number of tokens")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Temperature parameters (recommended for stock analysis: 0.2-0.3 for quick analysis, 0.1-0.2 for in-depth analysis)")
    timeout: int = Field(default=180, description="Request timeout(seconds)")
    retry_times: int = Field(default=3, description="Number of retries")
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="Inference model thinking depth (none/minimal/low/medium/high/xhigh/max), Only the Volcano Ark inference model supports"
    )
    enabled: bool = Field(default=True, description="Whether to enable")
    description: Optional[str] = Field(None, description="Configuration description")

    # New fields - configuration items from sidebar.py
    model_category: Optional[str] = Field(None, description="Model category(For OpenRouter etc.)")
    custom_endpoint: Optional[str] = Field(None, description="Custom endpoint URL")
    enable_memory: bool = Field(default=False, description="Enable memory function")
    enable_debug: bool = Field(default=False, description="Enable debug mode")
    priority: int = Field(default=0, description="priority")

    # Pricing configuration
    input_price_per_1k: Optional[float] = Field(None, description="Enter token price(per 1000 token)")
    output_price_per_1k: Optional[float] = Field(None, description="Output token price(per 1000 token)")
    currency: str = Field(default="CNY", description="currency unit(CNY/USD/EUR)")

    # 🆕 Model Capability Grading System
    capability_level: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Model capability level(1-5): 1=Basics, 2=Standard, 3=Advanced, 4=Professional, 5=flagship"
    )
    suitable_roles: List[str] = Field(
        default_factory=lambda: ["both"],
        description="Applicable roles: quick_analysis(Quick analysis), deep_analysis(In-depth analysis), both(suitable for both)"
    )
    features: List[str] = Field(
        default_factory=list,
        description="Model properties: tool_calling(Tool call), long_context(long context), reasoning(reasoning), vision(Vision), fast_response(fast), cost_effective(economy)"
    )
    recommended_depths: List[str] = Field(
        default_factory=lambda: ["fast", "Basics", "Standard"],
        description="Recommended level of analysis depth"
    )
    performance_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Performance indicators: speed(speed 1-5), cost(cost 1-5), quality(quality 1-5)"
    )
    created_at: Optional[datetime] = Field(default_factory=now_tz, description="creation time")
    updated_at: Optional[datetime] = Field(default_factory=now_tz, description="Update time")


class DataSourceConfig(BaseModel):
    """Data source configuration"""
    name: str = Field(..., description="Data source name")
    type: DataSourceType = Field(..., description="Data source type")
    api_key: Optional[str] = Field(None, description="API key")
    api_secret: Optional[str] = Field(None, description="API key")
    endpoint: Optional[str] = Field(None, description="API endpoint")
    timeout: int = Field(default=30, description="Request timeout(seconds)")
    rate_limit: int = Field(default=100, description="Request limit per minute")
    enabled: bool = Field(default=True, description="Whether to enable")
    priority: int = Field(default=0, description="Priority, the larger the number, the higher the priority.")
    config_params: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration parameters")
    description: Optional[str] = Field(None, description="Configuration description")
    # New field: Support market classification
    market_categories: Optional[List[str]] = Field(default_factory=list, description="Market category list")
    display_name: Optional[str] = Field(None, description="display name")
    provider: Optional[str] = Field(None, description="data provider")
    created_at: Optional[datetime] = Field(default_factory=now_tz, description="creation time")
    updated_at: Optional[datetime] = Field(default_factory=now_tz, description="Update time")


class DatabaseConfig(BaseModel):
    """Database configuration"""
    name: str = Field(..., description="Database name")
    type: DatabaseType = Field(..., description="Database type")
    host: str = Field(..., description="host address")
    port: int = Field(..., description="port number")
    username: Optional[str] = Field(None, description="Username")
    password: Optional[str] = Field(None, description="Password")
    database: Optional[str] = Field(None, description="Database name")
    connection_params: Dict[str, Any] = Field(default_factory=dict, description="Connection parameters")
    pool_size: int = Field(default=10, description="Connection pool size")
    max_overflow: int = Field(default=20, description="Maximum number of overflow connections")
    enabled: bool = Field(default=True, description="Whether to enable")
    description: Optional[str] = Field(None, description="Configuration description")


class MarketCategory(BaseModel):
    """Market classification configuration"""
    id: str = Field(..., description="Classification ID")
    name: str = Field(..., description="Category name")
    display_name: str = Field(..., description="display name")
    description: Optional[str] = Field(None, description="Classification description")
    enabled: bool = Field(default=True, description="Whether to enable")
    sort_order: int = Field(default=1, description="sort order")
    created_at: Optional[datetime] = Field(default_factory=now_tz, description="creation time")
    updated_at: Optional[datetime] = Field(default_factory=now_tz, description="Update time")


class DataSourceGrouping(BaseModel):
    """Data source grouping relationship"""
    data_source_name: str = Field(..., description="Data source name")
    market_category_id: str = Field(..., description="Market classification ID")
    priority: int = Field(default=0, description="Priority in this category")
    enabled: bool = Field(default=True, description="Whether to enable")
    source_type: str = Field(default="builtin", description="Data source type: builtin | mcp")
    created_at: Optional[datetime] = Field(default_factory=now_tz, description="creation time")
    updated_at: Optional[datetime] = Field(default_factory=now_tz, description="Update time")


class UsageRecord(BaseModel):
    """Usage records"""
    id: Optional[str] = Field(None, description="record ID")
    timestamp: str = Field(..., description="Timestamp")
    provider: str = Field(..., description="supplier")
    model_name: str = Field(..., description="Model name")
    input_tokens: int = Field(..., description="Enter the number of tokens")
    output_tokens: int = Field(..., description="Output the number of tokens")
    cost: float = Field(..., description="cost")
    currency: str = Field(default="CNY", description="currency unit")
    session_id: str = Field(..., description="session ID")
    analysis_type: str = Field(default="stock_analysis", description="Analysis type")
    stock_code: Optional[str] = Field(None, description="Stock code")


class UsageStatistics(BaseModel):
    """usage statistics"""
    total_requests: int = Field(default=0, description="Total requests")
    total_input_tokens: int = Field(default=0, description="Total number of input tokens")
    total_output_tokens: int = Field(default=0, description="Total number of output tokens")
    total_cost: float = Field(default=0.0, description="total cost (deprecated, use cost_by_currency)")
    cost_by_currency: Dict[str, float] = Field(default_factory=dict, description="Cost by currency")
    by_provider: Dict[str, Any] = Field(default_factory=dict, description="Statistics by supplier")
    by_model: Dict[str, Any] = Field(default_factory=dict, description="Statistics by model")
    by_date: Dict[str, Any] = Field(default_factory=dict, description="Statistics by date")


class SystemConfig(BaseModel):
    """System configuration model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    config_name: str = Field(..., description="Configuration name")
    config_type: str = Field(..., description="Configuration type")
    
    # Large model configuration
    llm_configs: List[LLMConfig] = Field(default_factory=list, description="Large model configuration list")
    default_llm: Optional[str] = Field(None, description="Default large model")
    
    # Data source configuration
    data_source_configs: List[DataSourceConfig] = Field(default_factory=list, description="Data source configuration list")
    
    # Database configuration
    database_configs: List[DatabaseConfig] = Field(default_factory=list, description="Database configuration list")
    
    # System settings
    system_settings: Dict[str, Any] = Field(default_factory=dict, description="System settings")
    
    # metadata
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)
    created_by: Optional[PyObjectId] = Field(None, description="Creator")
    updated_by: Optional[PyObjectId] = Field(None, description="Updater")
    version: int = Field(default=1, description="Configuration version")
    is_active: bool = Field(default=True, description="Whether to activate")
    
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


# API request/response model

class LLMConfigRequest(BaseModel):
    """Large model configuration request"""
    config_id: Optional[str] = None
    provider: str = Field(..., description="Supplier identification (supports dynamic addition)")
    model_name: str
    model_display_name: Optional[str] = None  # New: Model display name
    api_key: Optional[str] = None  # Optional, priority is given to obtaining configuration from the manufacturer.
    api_base: Optional[str] = None
    max_tokens: int = 8000
    temperature: float = 0.2  # Recommended values for stock analysis: 0.2-0.3 (quick analysis), 0.1-0.2 (in-depth analysis)
    timeout: int = 180  # Default timeout changed to 180 seconds
    retry_times: int = 3
    reasoning_effort: Optional[str] = None  # Inference model thinking about deep control
    enabled: bool = True
    description: Optional[str] = None

    # Add new fields to match the front end
    enable_memory: bool = False
    enable_debug: bool = False
    priority: int = 0
    model_category: Optional[str] = None

    # Pricing configuration
    input_price_per_1k: Optional[float] = None
    output_price_per_1k: Optional[float] = None
    currency: str = "CNY"

    # 🆕 Model Capability Grading System
    capability_level: int = Field(default=2, ge=1, le=5)
    suitable_roles: List[str] = Field(default_factory=lambda: ["both"])
    features: List[str] = Field(default_factory=list)
    recommended_depths: List[str] = Field(default_factory=lambda: ["fast", "Basics", "Standard"])
    performance_metrics: Optional[Dict[str, Any]] = None


class DataSourceConfigRequest(BaseModel):
    """Data source configuration request"""
    name: str
    type: DataSourceType
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    endpoint: Optional[str] = None
    timeout: int = 30
    rate_limit: int = 100
    enabled: bool = True
    priority: int = 0
    config_params: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    # Add new field
    market_categories: Optional[List[str]] = Field(default_factory=list)
    display_name: Optional[str] = None
    provider: Optional[str] = None


class MarketCategoryRequest(BaseModel):
    """Market Classification Request"""
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    enabled: bool = True
    sort_order: int = 1


class DataSourceGroupingRequest(BaseModel):
    """Data source grouping request"""
    data_source_name: str
    market_category_id: str
    priority: int = 0
    enabled: bool = True
    source_type: str = "builtin"


class DataSourceOrderRequest(BaseModel):
    """Data source sort request"""
    data_sources: List[Dict[str, Any]] = Field(..., description="Sorted data source list")


class DatabaseConfigRequest(BaseModel):
    """Database configuration request"""
    name: str
    type: DatabaseType
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    connection_params: Dict[str, Any] = Field(default_factory=dict)
    pool_size: int = 10
    max_overflow: int = 20
    enabled: bool = True
    description: Optional[str] = None


class SystemConfigResponse(BaseModel):
    """System configuration response"""
    config_name: str
    config_type: str
    llm_configs: List[LLMConfig]
    default_llm: Optional[str]
    data_source_configs: List[DataSourceConfig]
    database_configs: List[DatabaseConfig]
    system_settings: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int
    is_active: bool

    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class ConfigTestRequest(BaseModel):
    """Configure test requests"""
    config_type: str = Field(..., description="Configuration type: llm/datasource/database")
    config_data: Dict[str, Any] = Field(..., description="Configuration data")


class ConfigTestResponse(BaseModel):
    """Configure test response"""
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    response_time: Optional[float] = None

# === analysis.py ===
"""
Analyze related data models
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
from app.utils.timezone import now_tz


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

# === agent_growth.py ===
"""
Agent Growth related data model
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
from pydantic import BaseModel, ConfigDict, Field
from app.utils.timezone import now_tz


class GrowthMemoryScope(str, Enum):
    """Boundary classification of long-term growth memory"""
    TASK_TEMP = "task_temp"
    OBJECT_TRACKING = "object_tracking"
    USER_PREFERENCE = "user_preference"
    RESEARCH_ASSET = "research_asset"
    PATTERN = "pattern"


class GrowthMemoryStatus(str, Enum):
    """Memory entry status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class GrowthReviewLevel(str, Enum):
    """Audit level"""
    AUTO_PENDING = "auto_pending"
    MANUAL_REQUIRED = "manual_required"


class GrowthSuggestionStatus(str, Enum):
    """Suggestion status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class GrowthSuggestionType(str, Enum):
    """Growth advice types"""
    MEMORY_PROMOTION = "memory_promotion"
    RESEARCH_ASSET_PROMOTION = "research_asset_promotion"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    WATCH_RULE_SUGGESTION = "watch_rule_suggestion"


class GrowthEvidenceRef(BaseModel):
    """Growth Evidence Citations"""
    type: str
    id: str
    label: Optional[str] = None


class AgentGrowthMemoryItem(BaseModel):
    """Growth memory items"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    memory_id: str
    user_id: str
    scope: GrowthMemoryScope
    status: GrowthMemoryStatus = GrowthMemoryStatus.PENDING
    review_level: GrowthReviewLevel = GrowthReviewLevel.MANUAL_REQUIRED

    source_type: str
    source_id: str
    task_type: Optional[str] = None
    workflow_id: Optional[str] = None

    object_type: Optional[str] = None
    object_key: Optional[str] = None

    title: str
    summary: str = ""
    content: str
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    evidence_refs: List[GrowthEvidenceRef] = Field(default_factory=list)

    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat() if dt else None},
    )


class AgentGrowthSuggestion(BaseModel):
    """Growth advice items"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    suggestion_id: str
    user_id: str
    suggestion_type: GrowthSuggestionType
    status: GrowthSuggestionStatus = GrowthSuggestionStatus.PENDING

    source_type: str
    source_id: str
    task_type: Optional[str] = None
    workflow_id: Optional[str] = None
    object_type: Optional[str] = None
    object_key: Optional[str] = None

    title: str
    summary: str
    suggested_action: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    source_refs: List[GrowthEvidenceRef] = Field(default_factory=list)

    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None
    dismissed_by: Optional[str] = None
    dismissed_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat() if dt else None},
    )


class TaskGrowthContext(BaseModel):
    """Task-level growth extraction summary"""
    memory_items_count: int = 0
    suggestions_count: int = 0
    memory_item_ids: List[str] = Field(default_factory=list)
    suggestion_ids: List[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=now_tz)
    source_type: str = "unified_analysis_task"
    source_id: Optional[str] = None

    model_config = ConfigDict(
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

# === analysis_preference.py ===
"""
Analyze Preference Data Model
"""

from datetime import datetime
from typing import Optional, Any, Annotated
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, ConfigDict
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
from app.utils.timezone import now_tz


def validate_object_id(v: Any) -> ObjectId:
    """Verify ObjectId"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def serialize_object_id(v: ObjectId) -> str:
    """Serialize ObjectId to string"""
    return str(v)


# Create custom ObjectId type
PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


class AnalysisPreference(BaseModel):
    """Analytical preference model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId = Field(..., description="User ID")
    preference_type: str = Field(..., description="Preference type: aggressive, neutral, conservative")
    risk_level: float = Field(default=0.5, ge=0.0, le=1.0, description="risk level 0.0-1.0")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="confidence threshold 0.0-1.0")
    position_size_multiplier: float = Field(default=1.0, ge=0.5, le=2.0, description="Position multiple 0.5-2.0")
    decision_speed: str = Field(default="normal", description="decision speed: fast, normal, slow")
    is_default: bool = Field(default=False, description="Is it the default preference?")
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    updated_at: datetime = Field(default_factory=now_tz, description="Update time")
    
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class AnalysisPreferenceCreate(BaseModel):
    """Create preference request"""
    preference_type: str
    risk_level: float = 0.5
    confidence_threshold: float = 0.7
    position_size_multiplier: float = 1.0
    decision_speed: str = "normal"
    is_default: bool = False


class AnalysisPreferenceUpdate(BaseModel):
    """Update preference request"""
    risk_level: Optional[float] = None
    confidence_threshold: Optional[float] = None
    position_size_multiplier: Optional[float] = None
    decision_speed: Optional[str] = None
    is_default: Optional[bool] = None


class AnalysisPreferenceResponse(BaseModel):
    """preferred response"""
    id: str
    user_id: str
    preference_type: str
    risk_level: float
    confidence_threshold: float
    position_size_multiplier: float
    decision_speed: str
    is_default: bool
    created_at: str
    updated_at: str


# === analysis_profile.py ===
"""
Industry/Stock Analysis Configuration Data Model

For context-aware prompt word injection:
- IndustryAnalysisProfile: Industry-level analysis dimensions (such as banks focusing on NIM, NPL ratio)
- StockAnalysisProfile: Dimensions of individual stock-level analysis (for example, BYD focuses on monthly sales and DM-i proportion)
"""

from datetime import datetime
from typing import Optional, List, Any, Annotated
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, ConfigDict
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
from app.utils.timezone import now_tz


def validate_object_id(v: Any) -> ObjectId:
    """Verify ObjectId"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def serialize_object_id(v: ObjectId) -> str:
    """Serialize ObjectId to string"""
    return str(v)


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


class AnalysisDimension(BaseModel):
    """Analysis Dimensions"""
    name: str = Field(..., description="Dimension name, such as'net interest margin(NIM)'")
    description: str = Field(..., description="Dimension description, such as'Bank core profitability indicators'")
    importance: str = Field(default="high", description="importance: critical, high, medium, low")
    data_source: str = Field(default="fundamentals", description="Data source: fundamentals, news, technical, mixed")


class IndustryAnalysisProfile(BaseModel):
    """Industry analysis configuration"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    industry: str = Field(..., description="Industry name (aligned with the industry field of stock_basic_info)")
    display_name: str = Field(default="", description="Industry display name")
    analysis_dimensions: List[AnalysisDimension] = Field(default_factory=list, description="Industry core analysis dimensions")
    analysis_focus: str = Field(default="", description="Industry analysis highlights")
    key_metrics: List[str] = Field(default_factory=list, description="List of key indicators")
    comparable_companies: List[str] = Field(default_factory=list, description="Comparable companies in the industry")
    source: str = Field(default="system", description="Source: system, ai_generated, user")
    is_active: bool = Field(default=True, description="Whether to enable")
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    updated_at: datetime = Field(default_factory=now_tz, description="Update time")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class StockAnalysisProfile(BaseModel):
    """Individual stock analysis configuration (covering industry default configuration)"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    stock_symbol: str = Field(..., description="Stock code, such as 002594.SZ")
    company_name: str = Field(default="", description="Company name")
    industry: str = Field(default="", description="Industry")
    analysis_dimensions: List[AnalysisDimension] = Field(default_factory=list, description="Exclusive analysis dimensions for individual stocks")
    special_notes: str = Field(default="", description="Special instructions for individual stocks")
    source: str = Field(default="user", description="Source: system, ai_generated, user")
    is_active: bool = Field(default=True, description="Whether to enable")
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    updated_at: datetime = Field(default_factory=now_tz, description="Update time")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


# === Request/Response model ===

class AnalysisDimensionCreate(BaseModel):
    """Create an analysis dimension request"""
    name: str
    description: str
    importance: str = "high"
    data_source: str = "fundamentals"


class IndustryProfileCreate(BaseModel):
    """Create an industry configuration request"""
    industry: str
    display_name: str = ""
    analysis_dimensions: List[AnalysisDimensionCreate] = []
    analysis_focus: str = ""
    key_metrics: List[str] = []
    comparable_companies: List[str] = []
    source: str = "user"


class IndustryProfileUpdate(BaseModel):
    """Update Industry Configuration Request"""
    display_name: Optional[str] = None
    analysis_dimensions: Optional[List[AnalysisDimensionCreate]] = None
    analysis_focus: Optional[str] = None
    key_metrics: Optional[List[str]] = None
    comparable_companies: Optional[List[str]] = None
    is_active: Optional[bool] = None


class StockProfileCreate(BaseModel):
    """Create a stock allocation request"""
    stock_symbol: str
    company_name: str = ""
    industry: str = ""
    analysis_dimensions: List[AnalysisDimensionCreate] = []
    special_notes: str = ""
    source: str = "user"


class StockProfileUpdate(BaseModel):
    """Update individual stock allocation request"""
    company_name: Optional[str] = None
    industry: Optional[str] = None
    analysis_dimensions: Optional[List[AnalysisDimensionCreate]] = None
    special_notes: Optional[str] = None
    is_active: Optional[bool] = None


class IndustryProfileResponse(BaseModel):
    """Industry configuration response"""
    id: str
    industry: str
    display_name: str
    analysis_dimensions: List[AnalysisDimension]
    analysis_focus: str
    key_metrics: List[str]
    comparable_companies: List[str]
    source: str
    is_active: bool
    created_at: str
    updated_at: str


class StockProfileResponse(BaseModel):
    """Individual stock allocation response"""
    id: str
    stock_symbol: str
    company_name: str
    industry: str
    analysis_dimensions: List[AnalysisDimension]
    special_notes: str
    source: str
    is_active: bool
    created_at: str
    updated_at: str


# === capability_index.py ===
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CapabilityDocument(BaseModel):
    capability_id: str = Field(..., description="Ability unique identifier")
    registry_tool_id: Optional[str] = Field(default=None, description="If it can be bound, the corresponding registry tool_id")
    source_type: str = Field(..., description="builtin_tool / mcp_tool / skill / external_skill")
    status: str = Field(default="active", description="active / draft / disabled")
    bindable: bool = Field(default=False, description="Can it be directly bound?")
    fc_enabled: bool = Field(default=True, description="Is it allowed? function calling")
    category: str = Field(default="", description="Ability classification")
    name: str = Field(default="", description="display name")
    label: str = Field(default="", description="Tags for UI/prompt display")
    description: str = Field(default="", description="Capability description")
    when_to_use: str = Field(default="", description="Applicable scenarios")
    when_not_to_use: str = Field(default="", description="Not applicable scenarios")
    returns: str = Field(default="", description="Return structure description")
    related_tools: List[str] = Field(default_factory=list, description="Relevant abilities")
    coverage_terms: List[str] = Field(default_factory=list, description="Domain coverage keywords")
    retrieval_text: str = Field(default="", description="Write the search text to the vector library")
    data_source: str = Field(default="", description="underlying data source")
    capability_tags: List[str] = Field(default_factory=list, description="Structured capability tags")
    tool_role_hint: str = Field(default="", description="Tool role tips:primary/specialized/supporting/generic/fallback")
    output_shape: str = Field(default="", description="Output form: structured_metrics/report/text, etc.")
    preferred_for: List[str] = Field(default_factory=list, description="Preferred capability primitives")
    not_replacement_for: List[str] = Field(default_factory=list, description="Irreplaceable capability primitives")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class CapabilitySearchHit(BaseModel):
    capability: CapabilityDocument
    score: float = Field(default=0.0, description="Similarity score, the larger the score, the more relevant it is")


class CapabilityIndexSyncResult(BaseModel):
    collection_name: str
    fingerprint: str
    total_documents: int = 0
    indexed_documents: int = 0
    skipped_documents: int = 0
    vector_backend: str = ""
    sync_mode: str = "full_rebuild"

# === channel_config.py ===
"""
Channel push configuration data model

Supported channel types:
- feishu     Feishu custom robot Webhook
- dingtalk   DingTalk custom robot Webhook
- wechatwork Enterprise WeChat custom robot Webhook
- email      Mail (reuse existing SMTP configuration)
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    """Channel type"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECHATWORK = "wechatwork"
    EMAIL = "email"


# Supported event types
EVENT_TYPES = [
    "analysis_complete",   # Analysis completed
    "alert",               # early warning
    "skill_gap",           # tool gap perception
    "system",              # System notification
]

CHANNEL_TYPE_NAMES = {
    ChannelType.FEISHU: "Feishu",
    ChannelType.DINGTALK: "DingTalk",
    ChannelType.WECHATWORK: "Enterprise WeChat",
    ChannelType.EMAIL: "Mail",
}


class ChannelConfig(BaseModel):
    """Channel configuration"""
    channel_id: str
    type: ChannelType
    name: str
    enabled: bool = True
    webhook_url: Optional[str] = None      # Webhook channel
    email_address: Optional[str] = None   # Email channel
    events: List[str] = Field(default_factory=lambda: ["analysis_complete", "alert"])
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ChannelConfigCreate(BaseModel):
    """Create channel configuration request"""
    type: ChannelType
    name: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    webhook_url: Optional[str] = None
    email_address: Optional[str] = None
    events: List[str] = Field(default_factory=lambda: ["analysis_complete", "alert"])


class ChannelConfigUpdate(BaseModel):
    """Update channel configuration request"""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    email_address: Optional[str] = None
    events: Optional[List[str]] = None


class TestSendRequest(BaseModel):
    """Test push request"""
    title: str = "TradingAgents-CN Test notification"
    content: str = "This is a test message, if you receive this message, the channel is configured correctly."


# === email.py ===
"""
Email notification related data model
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.utils.timezone import now_tz


class EmailStatus(str, Enum):
    """Email sending status"""
    PENDING = "pending"      # To be sent
    SENDING = "sending"      # Sending
    SENT = "sent"           # Sent
    FAILED = "failed"       # Sending failed
    CANCELLED = "cancelled" # Canceled


class EmailType(str, Enum):
    """Email type"""
    SINGLE_ANALYSIS = "single_analysis"      # Single stock analysis results
    BATCH_ANALYSIS = "batch_analysis"        # Batch analysis summary
    SCHEDULED_ANALYSIS = "scheduled_analysis" # Regular analysis report
    IMPORTANT_SIGNAL = "important_signal"    # Important signal warning
    SYSTEM_NOTIFICATION = "system_notification" # System notification
    TEST_EMAIL = "test_email"                # test email


class EmailNotificationSettings(BaseModel):
    """Email notification settings"""
    enabled: bool = False                    # main switch
    email_address: Optional[str] = None      # Receiving email address (can be different from the registered email address)
    
    # Notification type switch
    single_analysis: bool = True             # Single stock analysis results
    batch_analysis: bool = True              # Batch analysis summary
    scheduled_analysis: bool = True          # Regular analysis report
    important_signals: bool = True           # Important signal warning
    system_notifications: bool = False       # System notification
    
    # Send time preference
    quiet_hours_enabled: bool = False        # Whether to enable do not disturb period
    quiet_hours_start: str = "22:00"         # Do not disturb start time
    quiet_hours_end: str = "08:00"           # Do not disturb end time
    
    # Email format preferences
    format: str = "html"                     # html / text
    include_charts: bool = False             # Whether to include charts (not supported yet)
    language: str = "zh"                     # Email language


class EmailRecord(BaseModel):
    """Email sending record"""
    id: Optional[str] = Field(default=None, alias="_id")
    
    # Basic information
    user_id: str
    to_email: str
    subject: str
    template_name: str
    
    # Email type
    email_type: EmailType
    
    # Linked data
    reference_id: Optional[str] = None   # Associated analysis report ID, etc.
    reference_type: Optional[str] = None # analysis_report/scheduled_task Wait
    
    # Send status
    status: EmailStatus = EmailStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    
    # Timestamp
    created_at: datetime = Field(default_factory=now_tz)
    sent_at: Optional[datetime] = None
    
    # error message
    error_message: Optional[str] = None
    
    # metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True


class EmailRecordCreate(BaseModel):
    """Create mail record request"""
    user_id: str
    to_email: str
    subject: str
    template_name: str
    email_type: EmailType
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EmailSettingsUpdate(BaseModel):
    """Update mail settings request"""
    enabled: Optional[bool] = None
    email_address: Optional[str] = None
    single_analysis: Optional[bool] = None
    batch_analysis: Optional[bool] = None
    scheduled_analysis: Optional[bool] = None
    important_signals: Optional[bool] = None
    system_notifications: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    format: Optional[str] = None
    language: Optional[str] = None


class SMTPConfig(BaseModel):
    """SMTP Configuration"""
    host: str
    port: int = 587
    username: str
    password: str
    from_email: str
    from_name: str = "TradingAgents-CN"
    use_tls: bool = True
    use_ssl: bool = False


# === notification.py ===
"""
Notification Data Model (MongoDB + Pydantic) 
"""
from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field, field_serializer
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
from app.utils.timezone import now_tz

# Simple tools:ObjectId -> str

def to_str_id(v: Any) -> str:
    try:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v)
    except Exception:
        return ""


NotificationType = Literal['analysis', 'alert', 'system']
NotificationStatus = Literal['unread', 'read']


class NotificationCreate(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[Literal['info','success','warning','error']] = None
    metadata: Optional[Dict[str, Any]] = None


class NotificationDB(BaseModel):
    id: Optional[str] = Field(default=None)
    user_id: str
    type: NotificationType
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    severity: Optional[Literal['info','success','warning','error']] = 'info'
    status: NotificationStatus = 'unread'
    created_at: datetime = Field(default_factory=now_tz)
    metadata: Optional[Dict[str, Any]] = None


class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    title: str
    content: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    status: NotificationStatus
    created_at: datetime

    @field_serializer('created_at')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class NotificationList(BaseModel):
    items: List[NotificationOut]
    total: int = 0
    page: int = 1
    page_size: int = 20



# === operation_log.py ===
"""
Operation log data model
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_serializer
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object


class OperationLogCreate(BaseModel):
    """Create operation log request"""
    action_type: str = Field(..., description="Operation type")
    action: str = Field(..., description="Operation description")
    details: Optional[Dict[str, Any]] = Field(None, description="Details")
    success: bool = Field(True, description="Is it successful?")
    error_message: Optional[str] = Field(None, description="error message")
    duration_ms: Optional[int] = Field(None, description="Operation time consuming(milliseconds)")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="user agent")
    session_id: Optional[str] = Field(None, description="session ID")


class OperationLogResponse(BaseModel):
    """Operation log response"""
    id: str = Field(..., description="Log ID")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    action_type: str = Field(..., description="Operation type")
    action: str = Field(..., description="Operation description")
    details: Optional[Dict[str, Any]] = Field(None, description="Details")
    success: bool = Field(..., description="Is it successful?")
    error_message: Optional[str] = Field(None, description="error message")
    duration_ms: Optional[int] = Field(None, description="Operation time consuming(milliseconds)")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="user agent")
    session_id: Optional[str] = Field(None, description="session ID")
    timestamp: datetime = Field(..., description="Operating time")
    created_at: datetime = Field(..., description="creation time")

    @field_serializer('timestamp', 'created_at')
    def serialize_datetime(self, dt: datetime, _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class OperationLogQuery(BaseModel):
    """Operation log query parameters"""
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Quantity per page")
    start_date: Optional[str] = Field(None, description="start date")
    end_date: Optional[str] = Field(None, description="end date")
    action_type: Optional[str] = Field(None, description="Operation type")
    success: Optional[bool] = Field(None, description="Is it successful?")
    keyword: Optional[str] = Field(None, description="keyword search")
    user_id: Optional[str] = Field(None, description="User ID")


class OperationLogListResponse(BaseModel):
    """Operation log list response"""
    success: bool = Field(True, description="Is it successful?")
    data: Dict[str, Any] = Field(..., description="response data")
    message: str = Field("Operation successful", description="response message")


class OperationLogStats(BaseModel):
    """Operation log statistics"""
    total_logs: int = Field(..., description="Total number of logs")
    success_logs: int = Field(..., description="Number of successful logs")
    failed_logs: int = Field(..., description="Number of failed logs")
    success_rate: float = Field(..., description="success rate")
    action_type_distribution: Dict[str, int] = Field(..., description="Operation type distribution")
    hourly_distribution: List[Dict[str, Any]] = Field(..., description="Hourly distribution")


class OperationLogStatsResponse(BaseModel):
    """Operation log statistics response"""
    success: bool = Field(True, description="Is it successful?")
    data: OperationLogStats = Field(..., description="Statistics")
    message: str = Field("Obtaining statistics successfully", description="response message")


class ClearLogsRequest(BaseModel):
    """Clear log request"""
    days: Optional[int] = Field(None, description="Keep the logs of the last N days. If not uploaded, all logs will be cleared.")
    action_type: Optional[str] = Field(None, description="Only clear logs of specified types")


class ClearLogsResponse(BaseModel):
    """Clear log response"""
    success: bool = Field(True, description="Is it successful?")
    data: Dict[str, Any] = Field(..., description="Clear results")
    message: str = Field("Cleared log successfully", description="response message")


# Operation type constant
class ActionType:
    """Operation type constant"""
    STOCK_ANALYSIS = "stock_analysis"
    CONFIG_MANAGEMENT = "config_management"
    CACHE_OPERATION = "cache_operation"
    DATA_IMPORT = "data_import"
    DATA_EXPORT = "data_export"
    SYSTEM_SETTINGS = "system_settings"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_MANAGEMENT = "user_management"  # 🔧 Add user management operation type
    DATABASE_OPERATION = "database_operation"
    SCREENING = "screening"
    REPORT_GENERATION = "report_generation"


# Operation type mapping
ACTION_TYPE_NAMES = {
    ActionType.STOCK_ANALYSIS: "stock analysis",
    ActionType.CONFIG_MANAGEMENT: "Configuration management",
    ActionType.CACHE_OPERATION: "Caching operations",
    ActionType.DATA_IMPORT: "Data import",
    ActionType.DATA_EXPORT: "Data export",
    ActionType.SYSTEM_SETTINGS: "System settings",
    ActionType.USER_LOGIN: "User login",
    ActionType.USER_LOGOUT: "User logout",
    ActionType.USER_MANAGEMENT: "User management",  # 🔧 Add user management operation type name
    ActionType.DATABASE_OPERATION: "Database operations",
    ActionType.SCREENING: "stock screen",
    ActionType.REPORT_GENERATION: "Report generation",
}


def convert_objectid_to_str(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ObjectId in MongoDB document to string"""
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

# === portfolio.py ===
"""
Data models related to position research
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object
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

# === project_memory.py ===
"""L4 A data model of item long-term memory."""


from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


DEFAULT_PROJECT_MEMORY_PROJECT_ID = "tradingagents-cn"


class ProjectMemoryCategory(str, Enum):
    PROJECT_RULE = "project_rule"
    GOVERNANCE_CONSTRAINT = "governance_constraint"
    ANALYSIS_OUTPUT_CONSTRAINT = "analysis_output_constraint"
    RESEARCH_TEMPLATE = "research_template"


class ProjectMemoryItem(BaseModel):
    memory_id: str
    project_id: str = DEFAULT_PROJECT_MEMORY_PROJECT_ID
    memory_key: str
    title: str
    content: str
    category: str
    priority: int = 100
    active: bool = True
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_by: str = ""


class ProjectMemoryUpsertRequest(BaseModel):
    memory_key: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=4000)
    category: ProjectMemoryCategory
    project_id: str = Field(default=DEFAULT_PROJECT_MEMORY_PROJECT_ID, min_length=1, max_length=80)
    priority: int = Field(default=100, ge=1, le=999)
    active: bool = True
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# === prompt_injection_policy.py ===
"""
Prompt Inject strategy data model

press Agent + Scenario fine control context injection rules:
- Whether to inject industry/stock portraits
- Injection granularity (none/summary/full)
- Whether to inherit the industry portrait (individual stock scenario)
- Does it come with ability blocks?
- Which field to inject into the template
"""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict

from app.utils.timezone import now_tz


class PromptInjectionPolicy(BaseModel):
    """
    Prompt Injection strategy
    
    Corresponding design documents §7.2, Control how different Agents inject context in different scenarios.
    """
    agent_type: str = Field(..., description="Agent Type, such as analysts_v2")
    agent_name: str = Field(..., description="Agent name, such as market_analyst_v2")
    scope: str = Field(
        default="general",
        description="scene: general / industry / stock"
    )
    enabled: bool = Field(default=True, description="Whether to enable")
    injection_mode: str = Field(
        default="summary",
        description="Injection granularity: none / summary / full"
    )
    inherit_industry_for_stock: bool = Field(
        default=True,
        description="Whether to inherit industry portraits when analyzing individual stocks"
    )
    include_capability_block: bool = Field(
        default=True,
        description="Whether to include a capability boundary description block"
    )
    include_external_gap_notice: bool = Field(
        default=True,
        description="Whether it comes with external dependency reminder"
    )
    include_comparable_companies: bool = Field(
        default=True,
        description="Whether to inject comparable companies"
    )
    inject_position: str = Field(
        default="analysis_requirements",
        description="Which template field to inject into: system_prompt / analysis_requirements / constraints"
    )
    version: int = Field(default=1, description="version number")
    created_at: Optional[datetime] = Field(default_factory=now_tz)
    updated_at: Optional[datetime] = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True)


# === Request/Response model ===

class PromptInjectionPolicyCreate(BaseModel):
    """Create policy request"""
    agent_type: str = Field(..., description="Agent Type")
    agent_name: str = Field(..., description="Agent Name")
    scope: str = Field(default="general", description="scene")
    enabled: bool = True
    injection_mode: str = "summary"
    inherit_industry_for_stock: bool = True
    include_capability_block: bool = True
    include_external_gap_notice: bool = True
    include_comparable_companies: bool = True
    inject_position: str = "analysis_requirements"


class PromptInjectionPolicyUpdate(BaseModel):
    """Update policy request (all fields optional)"""
    enabled: Optional[bool] = None
    injection_mode: Optional[str] = None
    inherit_industry_for_stock: Optional[bool] = None
    include_capability_block: Optional[bool] = None
    include_external_gap_notice: Optional[bool] = None
    include_comparable_companies: Optional[bool] = None
    inject_position: Optional[str] = None

# === report_template.py ===
"""
report template model

Supports configuring different report formats and output structures for different workflows.
Each workflow can be associated with a report template, which defines the report format produced by the workflow.

Usage scenarios:
- Preliminary process: concise pass/fail judgment report
- In-Depth Analysis: Detailed Investment Analysis Report
- Position Check: Position Risk Assessment Report
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, *args, **kwargs):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, *args, **kwargs):
        return {"type": "string"}


class OutputField(BaseModel):
    """Report output field definitions"""
    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field type: string, number, boolean, array, object")
    description: str = Field("", description="Field description")
    required: bool = Field(True, description="Is it required?")
    default: Optional[Any] = Field(None, description="Default value")
    # For string types, you can define enumeration values
    enum: Optional[List[str]] = Field(None, description="Enumeration values (string type only)")
    # For number types, a range can be defined
    min_value: Optional[float] = Field(None, description="Minimum value (number type only)")
    max_value: Optional[float] = Field(None, description="Maximum value (number type only)")


class ReportTemplate(BaseModel):
    """
    report template model
    
    Define the report output format of the workflow, including:
    - Output field definition (output_schema)
    - Report generation prompt word (generator_prompt)
    - Summary and presentation configuration
    """
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    
    # Basic information
    template_id: str = Field(..., description="template unique identifier")
    name: str = Field(..., description="Template name")
    description: str = Field("", description="Template description")
    
    # Associated workflows
    workflow_id: str = Field(..., description="Associated workflows ID")
    
    # Output structure definition
    output_schema: List[OutputField] = Field(
        default_factory=list, 
        description="Report output field definitions"
    )
    
    # Report Generator Prompt Words
    generator_prompt: str = Field(
        "", 
        description="Prompt word template for LLM generated reports, available using {agent_outputs} equal variables"
    )
    
    # summary configuration
    summary_fields: List[str] = Field(
        default_factory=list,
        description="List of fields used to generate the summary"
    )
    
    # Display configuration
    display_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Front-end display configuration (field order, style, etc.)"
    )
    
    # Status
    status: str = Field("active", description="Status: active, inactive")
    
    # metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = Field(None, description="Creator user ID")
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ReportTemplateCreate(BaseModel):
    """Create report template request"""
    template_id: str
    name: str
    description: str = ""
    workflow_id: str
    output_schema: List[OutputField] = Field(default_factory=list)
    generator_prompt: str = ""
    summary_fields: List[str] = Field(default_factory=list)
    display_config: Dict[str, Any] = Field(default_factory=dict)


class ReportTemplateUpdate(BaseModel):
    """Update report template request"""
    name: Optional[str] = None
    description: Optional[str] = None
    output_schema: Optional[List[OutputField]] = None
    generator_prompt: Optional[str] = None
    summary_fields: Optional[List[str]] = None
    display_config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class ReportTemplateResponse(BaseModel):
    """report template response"""
    id: str
    template_id: str
    name: str
    description: str
    workflow_id: str
    output_schema: List[OutputField]
    generator_prompt: str
    summary_fields: List[str]
    display_config: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


# === review.py ===
"""
Transaction review data model
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
    errors = object

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


# === screening.py ===
"""
Data models related to stock screening
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from core.skill_runtime.factor_schema import P0_PUBLIC_SCREENING_FIELDS, get_factor_field_schema


class OperatorType(str, Enum):
    """filter operator type"""
    GT = ">"           # greater than
    LT = "<"           # less than
    GTE = ">="         # Greater than or equal to
    LTE = "<="         # less than or equal to
    EQ = "=="          # equal to
    NE = "!="          # not equal to
    BETWEEN = "between"  # interval
    IN = "in"          # included in
    NOT_IN = "not_in"  # not included in
    CONTAINS = "contains"  # string contains
    CROSS_UP = "cross_up"    # Technical Indicators: Crossing Up
    CROSS_DOWN = "cross_down"  # Technical Indicators: Crossing Down


class FieldType(str, Enum):
    """Field type"""
    BASIC = "basic"        # Basic information fields
    TECHNICAL = "technical"  # Technical indicator field
    FUNDAMENTAL = "fundamental"  # fundamental fields


class ScreeningCondition(BaseModel):
    """single filter"""
    field: str = Field(..., description="Field name")
    operator: OperatorType = Field(..., description="Operator")
    value: Union[float, int, str, List[Union[float, int, str]]] = Field(..., description="filter value")
    field_type: Optional[FieldType] = Field(None, description="Field type")
    
    class Config:
        use_enum_values = True


class ScreeningRequest(BaseModel):
    """Filter requests"""
    market: str = Field("CN", description="Market:CN/HK/US")
    date: Optional[str] = Field(None, description="Trading date YYYY-MM-DD, the default is the latest")
    adj: str = Field("qfq", description="Restoration caliber:qfq/hfq/none")
    
    # Filter criteria
    conditions: List[ScreeningCondition] = Field(default_factory=list, description="filter list")
    
    # Sorting and paging
    order_by: Optional[List[Dict[str, str]]] = Field(None, description="Sorting conditions")
    limit: int = Field(50, ge=1, le=500, description="Return quantity limit")
    offset: int = Field(0, ge=0, description="offset")
    
    # Optimization options
    use_database_optimization: bool = Field(True, description="Whether to use database optimization")


class ScreeningResponse(BaseModel):
    """Filter responses"""
    total: int = Field(..., description="total quantity")
    items: List[Dict[str, Any]] = Field(..., description="Filter results")
    took_ms: Optional[int] = Field(None, description="Time consuming(milliseconds)")
    optimization_used: Optional[str] = Field(None, description="Optimization methods used")
    source: Optional[str] = Field(None, description="data source")


class FieldInfo(BaseModel):
    """Field information"""
    name: str = Field(..., description="Field name")
    display_name: str = Field(..., description="display name")
    field_type: FieldType = Field(..., description="Field type")
    data_type: str = Field(..., description="data type: number/string/date")
    description: str = Field("", description="Field description")
    unit: Optional[str] = Field(None, description="unit")
    
    # Statistics for numeric fields
    min_value: Optional[float] = Field(None, description="minimum value")
    max_value: Optional[float] = Field(None, description="maximum value")
    avg_value: Optional[float] = Field(None, description="average")
    
    # Optional values for enumeration fields
    available_values: Optional[List[str]] = Field(None, description="list of optional values")
    
    # Supported operators
    supported_operators: List[OperatorType] = Field(default_factory=list, description="Supported operators")


class FieldStatistics(BaseModel):
    """Field statistics"""
    field: str = Field(..., description="Field name")
    count: int = Field(..., description="Valid data quantity")
    min_value: Optional[float] = Field(None, description="minimum value")
    max_value: Optional[float] = Field(None, description="maximum value")
    avg_value: Optional[float] = Field(None, description="average")
    median_value: Optional[float] = Field(None, description="median")
    std_value: Optional[float] = Field(None, description="standard deviation")


_NUMERIC_OPERATORS = [
    OperatorType.GT,
    OperatorType.LT,
    OperatorType.GTE,
    OperatorType.LTE,
    OperatorType.BETWEEN,
]
_STRING_OPERATORS = [
    OperatorType.EQ,
    OperatorType.NE,
    OperatorType.IN,
    OperatorType.NOT_IN,
    OperatorType.CONTAINS,
]
_BOOLEAN_OPERATORS = [OperatorType.EQ, OperatorType.NE]


def _get_supported_operators(data_type: str) -> List[OperatorType]:
    if data_type == "number":
        return list(_NUMERIC_OPERATORS)
    if data_type == "boolean":
        return list(_BOOLEAN_OPERATORS)
    return list(_STRING_OPERATORS)


def _build_p0_screening_field_info() -> Dict[str, "FieldInfo"]:
    field_info_map: Dict[str, FieldInfo] = {}
    for field_name in P0_PUBLIC_SCREENING_FIELDS:
        schema = get_factor_field_schema(field_name)
        if schema is None:
            continue
        field_info_map[field_name] = FieldInfo(
            name=schema.field_name,
            display_name=schema.display_name,
            field_type=FieldType.FUNDAMENTAL,
            data_type=schema.data_type,
            description=schema.description,
            unit=schema.screening_unit or schema.unit or None,
            supported_operators=_get_supported_operators(schema.data_type),
        )
    return field_info_map


def _dedupe_fields(fields: List[str]) -> List[str]:
    return list(dict.fromkeys(fields))


# Predefined field information
BASIC_FIELDS_INFO = {
    "keyword": FieldInfo(
        name="keyword",
        display_name="keywords",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Stock code or name",
        supported_operators=[OperatorType.CONTAINS]
    ),
    "symbol": FieldInfo(
        name="symbol",
        display_name="Stock code",
        field_type=FieldType.BASIC,
        data_type="string",
        description="6 stock code",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN, OperatorType.CONTAINS]
    ),
    "code": FieldInfo(  # Compatible with old fields
        name="code",
        display_name="Stock code(Deprecated)",
        field_type=FieldType.BASIC,
        data_type="string",
        description="6 stock code(Deprecated,Use symbol)",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN, OperatorType.CONTAINS]
    ),
    "name": FieldInfo(
        name="name",
        display_name="Stock name",
        field_type=FieldType.BASIC,
        data_type="string",
        description="stock abbreviation",
        supported_operators=[OperatorType.CONTAINS, OperatorType.EQ, OperatorType.NE]
    ),
    "industry": FieldInfo(
        name="industry",
        display_name="Industry",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Shenwan Industry Classification",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN, OperatorType.CONTAINS]
    ),
    "area": FieldInfo(
        name="area",
        display_name="Region",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Company registration area",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN]
    ),
    "market": FieldInfo(
        name="market",
        display_name="Market",
        field_type=FieldType.BASIC,
        data_type="string",
        description="trading market",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN]
    ),
    "total_mv": FieldInfo(
        name="total_mv",
        display_name="Total market capitalization",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Total market capitalization",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "circ_mv": FieldInfo(
        name="circ_mv",
        display_name="Circulation market value",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Circulation market value",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pe": FieldInfo(
        name="pe",
        display_name="P/E ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="P/E ratio(PE)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pb": FieldInfo(
        name="pb",
        display_name="price to book ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="price to book ratio(PB)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pe_ttm": FieldInfo(
        name="pe_ttm",
        display_name="rolling price to earnings ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="rolling price to earnings ratio(PE TTM)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "ps_ttm": FieldInfo(
        name="ps_ttm",
        display_name="rolling price-to-sales ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="rolling price-to-sales ratio(PS TTM)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pb_mrq": FieldInfo(
        name="pb_mrq",
        display_name="Latest price-to-book ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Latest price-to-book ratio(PB MRQ)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "roe": FieldInfo(
        name="roe",
        display_name="ROE",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="ROE(The latest issue,%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "roa": FieldInfo(
        name="roa",
        display_name="return on total assets",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="return on total assets(ROA, %)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "gross_margin": FieldInfo(
        name="gross_margin",
        display_name="Gross profit margin",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="gross sales profit margin(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "netprofit_margin": FieldInfo(
        name="netprofit_margin",
        display_name="net profit margin",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="net sales profit margin(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "debt_to_assets": FieldInfo(
        name="debt_to_assets",
        display_name="Asset-liability ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Asset-liability ratio(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "assets_to_eqt": FieldInfo(
        name="assets_to_eqt",
        display_name="equity multiplier",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="equity multiplier(Total assets/shareholders equity)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "current_ratio": FieldInfo(
        name="current_ratio",
        display_name="current ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="current ratio(Current assets/current liabilities)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "quick_ratio": FieldInfo(
        name="quick_ratio",
        display_name="quick ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="quick ratio",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "cash_ratio": FieldInfo(
        name="cash_ratio",
        display_name="cash ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="cash ratio",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "dividend_yield": FieldInfo(
        name="dividend_yield",
        display_name="dividend yield",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Dividend rate in the last 12 months(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "peg": FieldInfo(
        name="peg",
        display_name="PEG",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="PEG=PE TTM/Net profit year-on-year growth rate",
        unit="times/%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "roic": FieldInfo(
        name="roic",
        display_name="return on invested capital",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="ROIC(Conservative agency caliber,%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "cash_conversion": FieldInfo(
        name="cash_conversion",
        display_name="Profit to cash conversion rate",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Operating cash flow/net profit",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "accrual_ratio": FieldInfo(
        name="accrual_ratio",
        display_name="accruals ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="(Net Profit - Operating Cash Flow)/Total assets, percentage output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "asset_turnover": FieldInfo(
        name="asset_turnover",
        display_name="asset turnover rate",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Revenue/total assets, currently using the latest conservative proxy for total assets",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "gross_profit_to_assets": FieldInfo(
        name="gross_profit_to_assets",
        display_name="gross profit to assets ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Gross profit/total assets, percentage output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "interest_coverage": FieldInfo(
        name="interest_coverage",
        display_name="interest coverage ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="oper_profit/fin_exp conservative agency caliber",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "inventory_turnover": FieldInfo(
        name="inventory_turnover",
        display_name="Inventory turnover",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Operating costs/inventory, current conservative proxy using latest inventory balance",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "receivable_turnover": FieldInfo(
        name="receivable_turnover",
        display_name="Accounts receivable turnover ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Revenue/Accounts Receivable, currently using the latest accounts receivable balance conservative proxy",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "net_cash_position": FieldInfo(
        name="net_cash_position",
        display_name="net cash position",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="(money_cap-total_ncl)/total_assets Conservative proxy for , percent output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "piotroski_f_score": FieldInfo(
        name="piotroski_f_score",
        display_name="Piotroski F-Score",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="9-point quality score based on financial signals from the last two periods",
        unit="points",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "altman_z_score": FieldInfo(
        name="altman_z_score",
        display_name="Altman Z-Score",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Financial distress risk score, currently using retained earnings and EBIT calibers in raw_data",
        unit="points",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "beneish_m_score": FieldInfo(
        name="beneish_m_score",
        display_name="Beneish M-Score",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Earnings manipulation risk score, based on the 8-index model of the last two periods",
        unit="points",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "revenue_ttm": FieldInfo(
        name="revenue_ttm",
        display_name="rolling revenue",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Rolling 12-month operating income",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "revenue_yoy": FieldInfo(
        name="revenue_yoy",
        display_name="Year-on-year revenue",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Year-on-year revenue growth rate for the latest reporting period compared to the same quarter last year",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "revenue_cagr_3y": FieldInfo(
        name="revenue_cagr_3y",
        display_name="Three-year compound growth rate of revenue",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Three-year revenue compared with three years ago in the same quarter CAGR",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "net_profit_ttm": FieldInfo(
        name="net_profit_ttm",
        display_name="rolling net profit",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Rolling 12-month net profit",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "net_profit_yoy": FieldInfo(
        name="net_profit_yoy",
        display_name="Net profit year-on-year",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="The year-on-year growth rate of net profit in the latest reporting period compared to the same quarter last year",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "profit_cagr_3y": FieldInfo(
        name="profit_cagr_3y",
        display_name="Three-year compound growth rate of net profit",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Three-year net profit compared to three years ago in the same quarter CAGR",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "oper_profit_yoy": FieldInfo(
        name="oper_profit_yoy",
        display_name="Operating profit year-on-year",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="The year-on-year growth rate of operating profit in the latest reporting period compared with the same quarter last year",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "n_cashflow_act": FieldInfo(
        name="n_cashflow_act",
        display_name="operating cash flow",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Net cash flow from operating activities",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "fcf": FieldInfo(
        name="fcf",
        display_name="free cash flow",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="free cash flow(Conservative agency caliber)=operating cash flow+investment cash flow",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "fcf_yield": FieldInfo(
        name="fcf_yield",
        display_name="free cash flow yield",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="free cash flow yield(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "fcf_margin": FieldInfo(
        name="fcf_margin",
        display_name="free cash flow rate",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Free cash flow/revenue, % output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "ocf_yield": FieldInfo(
        name="ocf_yield",
        display_name="operating cash flow yield",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Operating cash flow/total market capitalization, percentage output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "report_period": FieldInfo(
        name="report_period",
        display_name="financial reporting period",
        field_type=FieldType.FUNDAMENTAL,
        data_type="string",
        description="The latest financial report reporting period, such as 20250930",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN]
    ),
    "net_working_capital": FieldInfo(
        name="net_working_capital",
        display_name="net working capital",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="net working capital(billion)=Current assets - current liabilities",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "working_capital_change": FieldInfo(
        name="working_capital_change",
        display_name="working capital changes",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Changes in net working capital in the last two periods",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "is_st": FieldInfo(
        name="is_st",
        display_name="ST Status",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Whether it is ST or*ST stocks",
        supported_operators=[OperatorType.EQ, OperatorType.NE]
    ),
    "turnover_rate": FieldInfo(
        name="turnover_rate",
        display_name="turnover rate",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="turnover rate",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "volume_ratio": FieldInfo(
        name="volume_ratio",
        display_name="Quantity ratio",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="Quantity ratio",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),

    # Price data field (now in the view and can be queried directly from the database)
    "close": FieldInfo(
        name="close",
        display_name="closing price",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="latest closing price",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pct_chg": FieldInfo(
        name="pct_chg",
        display_name="Increase or decrease",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="Increase or decrease",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "amount": FieldInfo(
        name="amount",
        display_name="Turnover",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="Turnover",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "volume": FieldInfo(
        name="volume",
        display_name="Volume",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="Volume",
        unit="hand",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),

    # Technical indicator field
    "ma20": FieldInfo(
        name="ma20",
        display_name="20 daily moving average",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="20 daily moving average",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "rsi14": FieldInfo(
        name="rsi14",
        display_name="RSI indicator",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="14 Daily Relative Strength Index",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "kdj_k": FieldInfo(
        name="kdj_k",
        display_name="KDJ-K",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="KDJ Index K value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "kdj_d": FieldInfo(
        name="kdj_d",
        display_name="KDJ-D",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="KDJ Index D value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "kdj_j": FieldInfo(
        name="kdj_j",
        display_name="KDJ-J",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="KDJ Index J value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "dif": FieldInfo(
        name="dif",
        display_name="MACD-DIF",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="MACD Indicator DIF value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "dea": FieldInfo(
        name="dea",
        display_name="MACD-DEA",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="MACD Indicator DEA value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "macd_hist": FieldInfo(
        name="macd_hist",
        display_name="MACD bar chart",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="MACD Histogram value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
}


# P0 Public fundamental fields are uniformly derived from factor_schema to avoid drift with runtime/schema.
BASIC_FIELDS_INFO.update(_build_p0_screening_field_info())


SCREENING_FINANCIAL_CATEGORY_FIELDS = _dedupe_fields(
    ["total_mv", "circ_mv", *P0_PUBLIC_SCREENING_FIELDS, "report_period", "is_st"]
)


# === __init__.py ===
"""
Data model module
"""

# Import stock data model

__all__ = [
    "StockBasicInfoExtended",
    "MarketQuotesExtended",
    "MarketInfo",
    "TechnicalIndicators",
    "StockBasicInfoResponse",
    "MarketQuotesResponse",
    "StockListResponse",
    "MarketType",
    "ExchangeType",
    "CurrencyType",
    "StockStatus"
]