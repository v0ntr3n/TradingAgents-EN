"""
System configuration related data model
"""

from datetime import datetime, timezone
from app.utils.timezone import now_tz
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum
from bson import ObjectId
from .user import PyObjectId


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
