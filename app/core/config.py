from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import os
import sys
import warnings

# Legacy env var aliases (deprecated): map API_HOST/PORT/DEBUG -> HOST/PORT/DEBUG
_LEGACY_ENV_ALIASES = {
    "API_HOST": "HOST",
    "API_PORT": "PORT",
    "API_DEBUG": "DEBUG",
}
for _legacy, _new in _LEGACY_ENV_ALIASES.items():
    if _new not in os.environ and _legacy in os.environ:
        os.environ[_new] = os.environ[_legacy]
        warnings.warn(
            f"Environment variable {_legacy} is deprecated; use {_new} instead.",
            DeprecationWarning,
            stacklevel=2,
        )

class Settings(BaseSettings):
    # Basic configuration
    DEBUG: bool = Field(default=True)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
    )
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["*"])

    # MongoDB Configuration
    MONGODB_HOST: str = Field(default="localhost")
    MONGODB_PORT: int = Field(default=27017)
    MONGODB_USERNAME: str = Field(default="")
    MONGODB_PASSWORD: str = Field(default="")
    MONGODB_DATABASE: str = Field(default="tradingagents")
    MONGODB_AUTH_SOURCE: str = Field(default="admin")
    MONGO_MAX_CONNECTIONS: int = Field(default=100)
    MONGO_MIN_CONNECTIONS: int = Field(default=10)
    # MongoDB Timeout parameter (milliseconds) - for processing large amounts of historical data
    MONGO_CONNECT_TIMEOUT_MS: int = Field(default=30000)  # Connection timeout: 30 seconds (was 10 seconds)
    MONGO_SOCKET_TIMEOUT_MS: int = Field(default=60000)   # Socket timeout: 60 seconds (was 20 seconds)
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = Field(default=5000)  # Server selection timeout: 5 seconds

    @property
    def MONGO_URI(self) -> str:
        """build MongoDB URI"""
        if self.MONGODB_USERNAME and self.MONGODB_PASSWORD:
            return f"mongodb://{self.MONGODB_USERNAME}:{self.MONGODB_PASSWORD}@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DATABASE}?authSource={self.MONGODB_AUTH_SOURCE}"
        else:
            return f"mongodb://{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_DATABASE}"

    @property
    def MONGO_DB(self) -> str:
        """Get database name"""
        return self.MONGODB_DATABASE

    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = Field(default=0)
    REDIS_MAX_CONNECTIONS: int = Field(default=20)
    REDIS_RETRY_ON_TIMEOUT: bool = Field(default=True)

    @property
    def REDIS_URL(self) -> str:
        """build Redis URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # JWT Configuration
    JWT_SECRET: str = Field(default="change-me-in-production")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)

    # Queue configuration
    QUEUE_MAX_SIZE: int = Field(default=10000)
    QUEUE_VISIBILITY_TIMEOUT: int = Field(default=300)  # 5 minutes
    QUEUE_MAX_RETRIES: int = Field(default=3)
    WORKER_HEARTBEAT_INTERVAL: int = Field(default=30)  # 30 seconds


    # Queue polling/cleaning interval (seconds)
    QUEUE_POLL_INTERVAL_SECONDS: float = Field(default=1.0)
    QUEUE_CLEANUP_INTERVAL_SECONDS: float = Field(default=60.0)

    # Concurrency control
    DEFAULT_USER_CONCURRENT_LIMIT: int = Field(default=3)
    GLOBAL_CONCURRENT_LIMIT: int = Field(default=50)
    DEFAULT_DAILY_QUOTA: int = Field(default=1000)

    # rate limit
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    DEFAULT_RATE_LIMIT: int = Field(default=100)  # Requests per minute

    # Log configuration
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    LOG_FILE: str = Field(default="logs/tradingagents.log")

    # Agent configuration
    # Used to configure domain names that need to bypass the proxy (domestic data source)
    # Multiple domain names separated by commas
    # ⚠️ Windows Wildcards are not supported *, Full domain name must be used
    # Detailed description: docs/proxy_configuration.md
    PROXY_ENABLED: bool = Field(default=False)  # Agent main switch, closed by default
    HTTP_PROXY: str = Field(default="")
    HTTPS_PROXY: str = Field(default="")
    NO_PROXY: str = Field(
        default="localhost,127.0.0.1,eastmoney.com,push2.eastmoney.com,82.push2.eastmoney.com,82.push2delay.eastmoney.com,gtimg.cn,sinaimg.cn,api.tushare.pro,baostock.com"
    )

    # File upload configuration
    MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024)  # 10MB
    UPLOAD_DIR: str = Field(default="uploads")

    # Cache configuration
    CACHE_TTL: int = Field(default=3600)  # 1 hours
    SCREENING_CACHE_TTL: int = Field(default=1800)  # 30 minutes

    # Security configuration
    BCRYPT_ROUNDS: int = Field(default=12)
    SESSION_EXPIRE_HOURS: int = Field(default=24)
    CSRF_SECRET: str = Field(default="change-me-csrf-secret")

    # External service configuration
    STOCK_DATA_API_URL: str = Field(default="")
    STOCK_DATA_API_KEY: str = Field(default="")

    # Update check service configuration
    # API base address for checking updates and downloading update packages. If left blank, the default official website will be used.
    # It can be configured as a test domain name when used for testing, for example: https://test.example.com/api
    UPDATE_CHECK_BASE_URL: str = Field(
        default="https://www.tradingagentscn.com/api",
        description="Update check API base URL (empty = use default)"
    )
    UPDATE_CHECK_CHANNEL: str = Field(
        default="stable",
        description="Update release channel: stable or test"
    )

    # Authorization service configuration (TradingAgents Account Service)
    # ⚠️ NOTE: LICENSE_SERVICE_URL has been removed, the validation server address is hardcoded in core/licensing/validator.py
    # This prevents users from setting up fake servers by modifying environment variables to bypass license verification.
    LICENSE_SERVICE_TIMEOUT: int = Field(default=10, description="Authorization service request timed out(seconds)")
    LICENSE_CACHE_TTL: int = Field(default=300, description="Authorization information cache time(seconds)")

    # SSE Configuration
    SSE_POLL_TIMEOUT_SECONDS: float = Field(default=1.0)
    SSE_HEARTBEAT_INTERVAL_SECONDS: int = Field(default=10)
    SSE_TASK_MAX_IDLE_SECONDS: int = Field(default=300)
    SSE_BATCH_POLL_INTERVAL_SECONDS: float = Field(default=2.0)
    SSE_BATCH_MAX_IDLE_SECONDS: int = Field(default=600)


    # Monitoring configuration
    METRICS_ENABLED: bool = Field(default=True)
    HEALTH_CHECK_INTERVAL: int = Field(default=60)  # 60 seconds

    # Agent Execute trajectory acquisition (P1: machine-readable execution trace)
    AGENT_EXECUTION_TRACE_ENABLED: bool = Field(
        default=False,
        description="Enable Agent execution trace collection (write to MongoDB agent_execution_traces collection). It is turned off by default. It can be turned on when troubleshooting problems, or it can be turned on once through the enable_trace parameter of the analysis task."
    )

    # Agent assert(P2: Reflection lesson upgraded to executable assertion)
    AGENT_ASSERTION_ENABLED: bool = Field(
        default=True,
        description="Enable Agent assertion execution (load and execute assertions from the agent_assertions collection)"
    )
    AGENT_ASSERTION_CACHE_TTL_SECONDS: int = Field(
        default=60,
        description="Assert the in-process cache TTL (seconds) to avoid checking every execution MongoDB"
    )


    # Configure the source of truth (Option A):file|db|hybrid
    # - file: Based on file/env (recommended, production default)
    # - db: Subject to the database (only compatible with older versions, not recommended)
    # - hybrid: File/env takes priority, DB is used as a backup
    CONFIG_SOT: str = Field(default="file")


    # Basic information synchronization task configuration (configurable scheduling)
    SYNC_STOCK_BASICS_ENABLED: bool = Field(default=True)
    # Prefer using CRON expressions, e.g. "30 6 * * *" means daily 06:30
    SYNC_STOCK_BASICS_CRON: str = Field(default="")
    # If CRON is not provided, a simple time string is used "HH:MM" (24 Hourly format)
    SYNC_STOCK_BASICS_TIME: str = Field(default="06:30")
    # time zone
    TIMEZONE: str = Field(default="Asia/Shanghai")

    # Real-time market information warehousing task
    QUOTES_INGEST_ENABLED: bool = Field(default=True)
    QUOTES_INGEST_INTERVAL_SECONDS: int = Field(
        default=360,
        description="Real-time quotation collection interval (seconds). Default 360 seconds (6 minutes), recommended by free users>=300 seconds, paid users can set 5-60 seconds"
    )
    # During the market break/start the bottom-up (fill in the last snapshot)
    QUOTES_BACKFILL_ON_STARTUP: bool = Field(default=True)
    QUOTES_BACKFILL_ON_OFFHOURS: bool = Field(default=True)

    # Stop loss reminder scan task
    STOP_LOSS_ALERT_ENABLED: bool = Field(default=True, description="Enable stop loss reminder scan task")
    STOP_LOSS_ALERT_INTERVAL_SECONDS: int = Field(default=600, description="Stop loss reminder scanning interval (seconds)")
    STOP_LOSS_ALERT_NEAR_PCT: float = Field(default=0.02, description="Judgment ratio close to stop loss line (default 2%)")
    STOP_LOSS_ALERT_COOLDOWN_MINUTES: int = Field(default=180, description="Cooling time for repeated reminders in the same status (minutes)")

    # Real-time market interface rotation configuration
    QUOTES_ROTATION_ENABLED: bool = Field(
        default=True,
        description="Enable interface rotation mechanism (Tushare → AKShare Oriental Fortune → AKShare Sina Finance)"
    )
    QUOTES_TUSHARE_HOURLY_LIMIT: int = Field(
        default=2,
        description="Tushare rt_k Limit on the number of interface calls per hour (2 for free users, paid users can set higher)"
    )
    QUOTES_AUTO_DETECT_TUSHARE_PERMISSION: bool = Field(
        default=True,
        description="Automatically detect Tushare rt_k interface permissions, and paying users automatically switch to high-frequency mode (5 seconds)"
    )

    # Tushare Basic configuration
    TUSHARE_TOKEN: str = Field(default="", description="Tushare API Token")
    TUSHARE_ENABLED: bool = Field(default=True, description="Enable Tushare data source")
    TUSHARE_TIER: str = Field(default="standard", description="Tushare Points level (free/basic/standard/premium/vip)")
    TUSHARE_RATE_LIMIT_SAFETY_MARGIN: float = Field(default=0.8, ge=0.1, le=1.0, description="Rate limiting safety margin")

    # ==================== JD Cloud Cooperation Edition Configuration ====================
    # Pass JDYUN_MODE=true Enable JD Cloud cooperation version mode
    # After enabling, LLM and data source configuration are read from the environment variables injected by JD Cloud Platform:
    # - OPENAI_API_BASE: JD Cloud Model Service Address
    # - OPENAI_API_KEY: JD Cloud API Key
    # - OPENAI_MODEL: Default dialogue model (GLM-5/GLM-5.1/GLM-5.2/DeepSeek-V4-Flash)
    # - EMBEDDING_MODEL: Embedding Model (default Qwen3-Embedding-8B)
    # - TUSHARE_TOKEN: Tushare data source Token
    JDYUN_MODE: bool = Field(default=False, description="JD Cloud Cooperation Edition Mode Switch")

    # ==================== Development environment license skip switch ====================
    # only if DEBUG=True and LICENSE_SKIP_PRO_CHECK=true Effective when:
    # All PRO functions (workflow, advanced courses, etc.) are directly available to the currently logged in user to facilitate local development and testing.
    # production environment (DEBUG=False) Even if it is set to true by mistake, it will not take effect, ensuring that the license verification is not bypassed.
    LICENSE_SKIP_PRO_CHECK: bool = Field(default=False, description="Development mode skips PRO License verification (only DEBUG=True effective when)")

    # Tushare Unified data synchronization configuration
    TUSHARE_UNIFIED_ENABLED: bool = Field(default=True)
    TUSHARE_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_BASIC_INFO_SYNC_CRON: str = Field(default="0 2 * * *")  # 2 a.m. every day
    TUSHARE_QUOTES_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_QUOTES_SYNC_CRON: str = Field(default="*/5 9-15 * * 1-5")  # Trading time every 5 minutes
    TUSHARE_HISTORICAL_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_HISTORICAL_SYNC_CRON: str = Field(default="0 18 * * 1-5")  # 18:00 on weekdays
    TUSHARE_FINANCIAL_SYNC_ENABLED: bool = Field(default=True)
    TUSHARE_FINANCIAL_SYNC_CRON: str = Field(default="0 3 * * 0")  # Sunday 3am
    TUSHARE_STATUS_CHECK_ENABLED: bool = Field(default=True)
    TUSHARE_STATUS_CHECK_CRON: str = Field(default="0 * * * *")  # hourly
    
    # Tushare Real-time market synchronization task every hour (free users can only call it once per hour)
    TUSHARE_REALTIME_QUOTES_HOURLY_ENABLED: bool = Field(default=True, description="Enable hourly synchronization of Tushare real-time quotes (free users can only call once per hour)")
    TUSHARE_REALTIME_QUOTES_HOURLY_CRON: str = Field(default="31 * * * *", description="Real-time market synchronization CRON expression every hour (executed at 31 minutes every hour)")

    # Stock watch list A-share data synchronization task configuration
    FAVORITES_DATA_SYNC_ENABLED: bool = Field(default=True, description="Enable stock watch list A-share data synchronization")
    FAVORITES_DATA_SYNC_CRON: str = Field(default="0 19 * * 1-5", description="Stock watch list A-share data synchronization CRON expression (7 p.m. on trading days)")

    # Technical indicator materialization task configuration
    TECHNICAL_INDICATORS_MATERIALIZATION_ENABLED: bool = Field(default=True, description="Enable technical indicator materialization task")
    TECHNICAL_INDICATORS_MATERIALIZATION_CRON: str = Field(default="20 18 * * 1-5", description="Technical indicator materialized CRON expression (default trading day 18:20) ")

    # External channel no topic conversation precipitation task
    IM_TOPIC_DIGEST_ENABLED: bool = Field(default=True, description="Enable external sessions to periodically drop into research topics")
    IM_TOPIC_DIGEST_CRON: str = Field(default="30 22 * * *", description="External session precipitation CRON expression, default daily 22:30")
    IM_TOPIC_DIGEST_MIN_MESSAGES: int = Field(default=6, ge=2, le=100, description="The minimum number of new messages required to trigger precipitation")
    IM_TOPIC_DIGEST_LOOKBACK_LIMIT: int = Field(default=20, ge=6, le=200, description="The maximum number of messages read per precipitation")

    # Tushare Data initialization configuration
    TUSHARE_INIT_HISTORICAL_DAYS: int = Field(default=365, ge=1, le=3650, description="Initialize historical data days")
    TUSHARE_INIT_BATCH_SIZE: int = Field(default=100, ge=10, le=1000, description="Initialize batch size")
    TUSHARE_INIT_AUTO_START: bool = Field(default=False, description="Automatically check and initialize data when the application starts")

    # AKShare Unified data synchronization configuration
    AKSHARE_UNIFIED_ENABLED: bool = Field(default=True, description="Enable AKShare unified data synchronization")
    AKSHARE_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True, description="Enable basic information synchronization")
    AKSHARE_BASIC_INFO_SYNC_CRON: str = Field(default="0 3 * * *", description="Basic information synchronization CRON expression")  # 3 a.m. every day
    AKSHARE_QUOTES_SYNC_ENABLED: bool = Field(default=True, description="Enable market synchronization")
    AKSHARE_QUOTES_SYNC_CRON: str = Field(default="*/30 9-15 * * 1-5", description="Market synchronization CRON expression")  # Trading hours every 30 minutes (to avoid frequency limits)
    AKSHARE_HISTORICAL_SYNC_ENABLED: bool = Field(default=True, description="Enable historical data synchronization")
    AKSHARE_HISTORICAL_SYNC_CRON: str = Field(default="0 18 * * 1-5", description="Historical data synchronization CRON expression")  # 18:00 on weekdays
    AKSHARE_FINANCIAL_SYNC_ENABLED: bool = Field(default=True, description="Enable financial data synchronization")
    AKSHARE_FINANCIAL_SYNC_CRON: str = Field(default="0 4 * * 0", description="Financial data synchronization CRON expression")  # Sunday 4am
    AKSHARE_STATUS_CHECK_ENABLED: bool = Field(default=True, description="Enable status checking")
    AKSHARE_STATUS_CHECK_CRON: str = Field(default="30 * * * *", description="Status check CRON expression")  # 30 minutes per hour

    # ETF Data synchronization configuration (full amount for the first time, and subsequent increments based on the latest warehousing date)
    ETF_SYNC_ENABLED: bool = Field(default=True, description="Enable ETF data sync")
    ETF_SYNC_CRON: str = Field(default="0 4 * * 1-5", description="ETF Synchronous CRON expressions")  # 4 a.m. on weekdays
    ETF_SYNC_DAYS: int = Field(default=30, ge=1, le=365, description="ETF Number of days to force synchronization back (used in force/manual mode)")
    ETF_SYNC_ITEM_TIMEOUT_SECONDS: int = Field(default=60, ge=5, le=600, description="ETF Single target daily line capture timeout (seconds)")

    # Official industry data (obtained from the official website URL to avoid AKShare polling and banning)
    OFFICIAL_INDUSTRY_DATA_URL: Optional[str] = Field(
        default=None,
        description="A Stock industry data JSON URL, format: {\"600519\":\"Liquor\",\"000001\":\"bank\"} or [{\"code\":\"600519\",\"industry\":\"Liquor\"}]"
    )

    # AKShare Data initialization configuration
    AKSHARE_INIT_HISTORICAL_DAYS: int = Field(default=365, ge=1, le=3650, description="Initialize historical data days")
    AKSHARE_INIT_BATCH_SIZE: int = Field(default=100, ge=10, le=1000, description="Initialize batch size")
    AKSHARE_INIT_AUTO_START: bool = Field(default=False, description="Automatically check and initialize data when the application starts")

    # ==================== Analyst data acquisition configuration ====================

    # Market analyst data range configuration
    # Default 60 days: can cover all common technical indicators such as MA60 (MA5/10/20/60, MACD, RSI, BOLL) 
    MARKET_ANALYST_LOOKBACK_DAYS: int = Field(default=60, ge=5, le=365, description="Market analysis lookback days (for technical analysis)")

    # ==================== BaoStock Unified data synchronization configuration ====================

    # BaoStock Unified data synchronization master switch
    BAOSTOCK_UNIFIED_ENABLED: bool = Field(default=True, description="Enable BaoStock unified data synchronization")

    # BaoStock Data synchronization task configuration
    BAOSTOCK_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True, description="Enable basic information synchronization")
    BAOSTOCK_BASIC_INFO_SYNC_CRON: str = Field(default="0 4 * * *", description="Basic information synchronization CRON expression")  # 4 a.m. every day
    BAOSTOCK_DAILY_QUOTES_SYNC_ENABLED: bool = Field(default=True, description="Enable daily K-line synchronization (note: BaoStock does not support real-time market conditions)")
    BAOSTOCK_DAILY_QUOTES_SYNC_CRON: str = Field(default="0 18 * * 1-5", description="Daily K-line synchronization CRON expression")  # After the close of business days 16:00
    BAOSTOCK_HISTORICAL_SYNC_ENABLED: bool = Field(default=True, description="Enable historical data synchronization")
    BAOSTOCK_HISTORICAL_SYNC_CRON: str = Field(default="0 18 * * 1-5", description="Historical data synchronization CRON expression")  # 18:00 on weekdays
    BAOSTOCK_STATUS_CHECK_ENABLED: bool = Field(default=True, description="Enable status checking")
    BAOSTOCK_STATUS_CHECK_CRON: str = Field(default="45 * * * *", description="Status check CRON expression")  # 45 minutes per hour

    # BaoStock Data initialization configuration
    BAOSTOCK_INIT_HISTORICAL_DAYS: int = Field(default=365, ge=1, le=3650, description="Initialize historical data days")
    BAOSTOCK_INIT_BATCH_SIZE: int = Field(default=50, ge=10, le=500, description="Initialize batch size")
    BAOSTOCK_INIT_AUTO_START: bool = Field(default=False, description="Automatically check and initialize data when the application starts")

    # ==================== QMT Unified data synchronization configuration ====================
    QMT_UNIFIED_ENABLED: bool = Field(default=False, description="Enable QMT unified data synchronization (requires QMT trading terminal to run)")
    QMT_BASIC_INFO_SYNC_ENABLED: bool = Field(default=True, description="Enable QMT basic information synchronization")
    QMT_BASIC_INFO_SYNC_CRON: str = Field(default="0 7 * * 1-5", description="QMT Basic information synchronization CRON expression, default working day is 7 o clock")
    QMT_QUOTES_SYNC_ENABLED: bool = Field(default=False, description="Enable QMT real-time market synchronization")
    QMT_QUOTES_SYNC_CRON: str = Field(default="*/10 9-15 * * 1-5", description="QMT Real-time market synchronization CRON expression, default trading time every 10 minutes")
    QMT_HISTORICAL_SYNC_ENABLED: bool = Field(default=False, description="Enable QMT historical data synchronization")
    QMT_HISTORICAL_SYNC_CRON: str = Field(default="0 18 * * 1-5", description="QMT Historical data synchronization CRON expression, default trading day 18:00")
    QMT_FINANCIAL_SYNC_ENABLED: bool = Field(default=False, description="Enable QMT financial data synchronization")
    QMT_FINANCIAL_SYNC_CRON: str = Field(default="0 4 * * 0", description="QMT Financial data synchronization CRON expression, default is 4 o clock on Sunday")
    QMT_STATUS_CHECK_ENABLED: bool = Field(default=True, description="Enable QMT status checking")
    QMT_STATUS_CHECK_CRON: str = Field(default="15 * * * *", description="QMT Status check CRON expression, default 15 minutes per hour")
    QMT_TOKEN: str = Field(default="", description="QMT Market service token (optional, used for VIP or independent market connection)")
    QMT_DATA_DIR: str = Field(default="", description="QMT Local data directory (optional)")
    QMT_LISTEN_PORT: int = Field(default=0, description="QMT Listening port, 0 means automatic selection")
    QMT_LISTEN_PORT_RANGE: str = Field(default="58620-58650", description="QMT Listening port range")
    QMT_INIT_MARKETS: str = Field(default="SH,SZ,BJ", description="QMT Initialize market list, comma separated")
    QMT_KLINE_MIRROR_MARKETS: str = Field(default="", description="QMT K Full market list, separated by commas")
    QMT_ALLOW_OPTIMIZE_ADDRESSES: str = Field(default="", description="QMT Quotation preferred server list, separated by commas")
    QMT_START_LOCAL_SERVICE: bool = Field(default=False, description="Whether to start the local service when initializing QMT")
    QMT_KLINE_MIRROR_ENABLED: bool = Field(default=False, description="Whether to enable QMT K-line full push")
    QMT_AUTO_DOWNLOAD_HISTORY: bool = Field(default=True, description="Automatically supplement historical data before reading QMT K-line")
    QMT_AUTO_DOWNLOAD_FINANCIAL: bool = Field(default=False, description="Automatically download financial data before reading QMT financial data")
    QMT_AUTO_DOWNLOAD_SECTOR: bool = Field(default=False, description="Automatically download sector data before reading the QMT stock list (off by default to avoid stuck)")

    # BaoStock Configuration
    ENABLE_BAOSTOCK: bool = Field(default=True, description="Whether to enable BaoStock data source (synchronized stock list, daily quotes, valuation data, etc.)")
    QMT_HISTORY_START_TIME: str = Field(default="", description="QMT Historical data automatic download start date YYYYMMDD")
    QMT_HISTORICAL_SYNC_DAYS: int = Field(default=365, ge=1, le=3650, description="QMT Historical data synchronization days")
    QMT_HISTORICAL_BATCH_SIZE: int = Field(default=100, ge=1, le=1000, description="QMT Historical data synchronization batch size")
    QMT_FINANCIAL_BATCH_SIZE: int = Field(default=50, ge=1, le=500, description="QMT Financial data synchronization batch size")

    # Data directory configuration
    TRADINGAGENTS_DATA_DIR: str = Field(default="./data")

    @property
    def log_dir(self) -> str:
        """Get log directory"""
        return os.path.dirname(self.LOG_FILE)

    # ==================== Hong Kong stock data configuration ====================

    # Hong Kong stock data source configuration (obtain on demand+cache mode)
    HK_DATA_CACHE_HOURS: int = Field(default=24, ge=1, le=168, description="Hong Kong stock data cache duration (hours)")
    HK_DEFAULT_DATA_SOURCE: str = Field(default="yfinance", description="Default data source for Hong Kong stocks (yfinance/akshare)")

    # ==================== US stock data configuration ====================

    # U.S. stock data source configuration (obtain on demand+cache mode)
    US_DATA_CACHE_HOURS: int = Field(default=24, ge=1, le=168, description="U.S. stock data cache duration (hours)")
    US_DEFAULT_DATA_SOURCE: str = Field(default="yfinance", description="Default data source for US stocks (yfinance/finnhub)")

    # ===== News data synchronization service configuration =====
    NEWS_SYNC_ENABLED: bool = Field(default=True)
    NEWS_SYNC_CRON: str = Field(default="0 */2 * * *")  # every 2 hours
    NEWS_SYNC_HOURS_BACK: int = Field(default=24)
    NEWS_SYNC_MAX_PER_SOURCE: int = Field(default=50)

    # ===== Stock watch list timing analysis configuration =====
    WATCHLIST_ANALYSIS_ENABLED: bool = Field(default=False, description="Enable scheduled analysis of stock watchlists")
    WATCHLIST_ANALYSIS_CRON: str = Field(default="0 8 * * 1-5", description="Regularly analyze CRON expressions, default is 8 a.m. on weekdays")

    # ===== SMTP Email configuration =====
    SMTP_ENABLED: bool = Field(default=False, description="Enable email notifications")
    SMTP_HOST: str = Field(default="smtp.qq.com", description="SMTP Server address")
    SMTP_PORT: int = Field(default=587, description="SMTP port")
    SMTP_USERNAME: str = Field(default="", description="SMTP Username")
    SMTP_PASSWORD: str = Field(default="", description="SMTP Password or authorization code")
    SMTP_FROM_EMAIL: str = Field(default="", description="Sender s email")
    SMTP_FROM_NAME: str = Field(default="TradingAgents-CN", description="Sender name")
    SMTP_USE_TLS: bool = Field(default=True, description="Use TLS encryption")
    SMTP_USE_SSL: bool = Field(default=False, description="Use SSL encryption")

    # Email sending restrictions
    EMAIL_DAILY_LIMIT: int = Field(default=100, description="Maximum number of emails sent per user per day")
    EMAIL_RATE_LIMIT: int = Field(default=10, description="Maximum number of emails sent per minute")

    @property
    def is_production(self) -> bool:
        """Is it a production environment?"""
        return not self.DEBUG

    _DEFAULT_SECRETS = frozenset({
        # Historical defaults
        "change-me-in-production",
        "change-me-csrf-secret",
        # .env.example / .env.docker Predictable placeholders in (placeholders are not real keys and are prohibited from direct use)
        "your-super-secret-jwt-key-change-in-production",
        "your-csrf-secret-key-change-in-production",
        "docker-jwt-secret-key-change-in-production-2024",
        "docker-csrf-secret-key-change-in-production-2024",
        # Unsafe default values in JD Cloud docker-compose must be prohibited from being used in production environments
        "jdyun-jwt-secret-key-change-in-production-2024",
        "jdyun-csrf-secret-key-change-in-production-2024",
        # Added placeholder (to prevent users from directly copying .env.example without modifying it)
        "PLEASE_CHANGE_JWT_SECRET_USE_openssl_rand_base64_48",
        "PLEASE_CHANGE_CSRF_SECRET_USE_openssl_rand_base64_48",
    })

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if not self.DEBUG:
            if self.JWT_SECRET in self._DEFAULT_SECRETS:
                print(
                    "\n!!! FATAL: JWT_SECRET is still the default value. "
                    "Set a strong random secret in .env before running in production.\n",
                    file=sys.stderr,
                )
                sys.exit(1)
            if self.CSRF_SECRET in self._DEFAULT_SECRETS:
                print(
                    "\n!!! FATAL: CSRF_SECRET is still the default value. "
                    "Set a strong random secret in .env before running in production.\n",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            if self.JWT_SECRET in self._DEFAULT_SECRETS:
                warnings.warn(
                    "JWT_SECRET is using the default value. "
                    "This is acceptable in DEBUG mode only.",
                    stacklevel=2,
                )
        if "*" in self.ALLOWED_ORIGINS and not self.DEBUG:
            print(
                "\n!!! FATAL: ALLOWED_ORIGINS contains '*' in production. "
                "Specify explicit origins in .env.\n",
                file=sys.stderr,
            )
            sys.exit(1)
        return self

    # Ignore any extra environment variables present in .env or process env
    # Supports specifying different .env files through the DOTENV_FILE environment variable (such as .env.jdyun for JD Cloud mode)
    _env_file = os.getenv("DOTENV_FILE", ".env")
    model_config = SettingsConfigDict(env_file=_env_file, env_file_encoding="utf-8", extra="ignore")

settings = Settings()

# 🔧 Automatically set proxy configuration to environment variables (only when proxy is enabled)
# In this way, the requests library can read directly os.environ['HTTP_PROXY'] Wait
if settings.PROXY_ENABLED:
    if settings.HTTP_PROXY:
        os.environ['HTTP_PROXY'] = settings.HTTP_PROXY
        os.environ['http_proxy'] = settings.HTTP_PROXY  # Lowercase version (required by some libraries)
    if settings.HTTPS_PROXY:
        os.environ['HTTPS_PROXY'] = settings.HTTPS_PROXY
        os.environ['https_proxy'] = settings.HTTPS_PROXY  # lower case version
else:
    # 🔧 The proxy is not enabled, clear the proxy settings in the environment variables (to avoid system proxy interference)
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]

# 🔧 NO_PROXY Always set (domestic data sources do not use proxies)
if settings.NO_PROXY:
    os.environ['NO_PROXY'] = settings.NO_PROXY
    os.environ['no_proxy'] = settings.NO_PROXY  # lower case version


def get_settings() -> Settings:
    """Get configuration instance"""
    return settings