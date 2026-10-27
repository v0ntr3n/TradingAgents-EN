"""
Simplified stock analysis service
Directly call existing TradingAgents analysis functions
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import sys

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Initialize TradingAgents log system
from tradingagents.utils.logging_init import init_logging
init_logging()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from app.models.analysis import (
    AnalysisTask, AnalysisStatus, SingleAnalysisRequest, AnalysisParameters
)
from app.models.user import PyObjectId
from app.models.notification import NotificationCreate
from bson import ObjectId
from app.core.database import get_mongo_db
from app.services.config_service import ConfigService
from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
from app.services.redis_progress_tracker import RedisProgressTracker, get_progress_by_id
from app.services.progress_log_handler import register_analysis_tracker, unregister_analysis_tracker

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")

# Research depth level → Volcano Ark reasoning model thinking budget (reasoning_effort seven levels: none/minimal/low/medium/high/xhigh/max)
# Gear mapping only as default: reasoning_effort explicitly set in DB model configuration takes precedence (see trading_graph merge logic)
RESEARCH_DEPTH_REASONING_EFFORT = {
    "快速": "minimal",
    "基础": "low",
    "标准": "medium",
    "深度": "high",
    "全面": "xhigh",
}

# Obtain basic stock information (used to supplement the display name)
try:
    from tradingagents.dataflows.data_source_manager import get_data_source_manager
    _data_source_manager = get_data_source_manager()
    def _get_stock_info_safe(stock_code: str):
        """Secure encapsulation of obtaining basic stock information"""
        return _data_source_manager.get_stock_basic_info(stock_code)
except Exception:
    _get_stock_info_safe = None

try:
    from tradingagents.config.database_manager import get_mongodb_client, get_database_manager
except Exception:
    get_mongodb_client = None
    get_database_manager = None

# Setup log
logger = logging.getLogger("app.services.simple_analysis_service")

# Configure service instance
config_service = ConfigService()


def _is_cn_etf_symbol(code: Optional[str]) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _get_cached_security_name(code: Optional[str]) -> Optional[str]:
    if not code or get_mongodb_client is None:
        return None

    code_str = str(code).strip().zfill(6)

    try:
        client = get_mongodb_client()
        if not client:
            return None

        db_name = "tradingagents"
        if get_database_manager is not None:
            try:
                db_name = get_database_manager().mongodb_config.get("database", "tradingagents")
            except Exception:
                pass

        db = client[db_name]

        if _is_cn_etf_symbol(code_str):
            doc = db["etf_basic_info"].find_one(
                {"code": code_str},
                {"name": 1, "fund_name": 1, "etf_name": 1, "symbol": 1, "_id": 0}
            )
            if doc:
                return doc.get("name") or doc.get("fund_name") or doc.get("etf_name")

        doc = db["stock_basic_info"].find_one(
            {"$or": [{"code": code_str}, {"symbol": code_str}]},
            {"name": 1, "stock_name": 1, "_id": 0}
        )
        if doc:
            return doc.get("name") or doc.get("stock_name")
    except Exception as e:
        logger.debug(f"Failed to read cache name (ignored): {code_str} - {e}")

    return None


async def get_provider_by_model_name(model_name: str, preferred_provider: Optional[str] = None) -> str:
    """
    Find the corresponding supplier from the database configuration based on the model name (asynchronous version)

    Args:
        model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

    Returns:
        str: Supplier name, e.g. 'dashscope', 'openai' Wait
    """
    try:
        # Get system configuration from configuration service
        system_config = await config_service.get_system_config()
        if not system_config or not system_config.llm_configs:
            logger.warning(f"⚠️ System configuration is empty, using default vendor mapping")
            return _get_default_provider_by_model(model_name)

        normalized_provider = str(preferred_provider or "").strip().lower()

        # Find matching model in LLM configuration
        for llm_config in system_config.llm_configs:
            if llm_config.model_name != model_name:
                continue
            provider = llm_config.provider.value if hasattr(llm_config.provider, 'value') else str(llm_config.provider)
            if normalized_provider and str(provider).lower() != normalized_provider:
                continue
            logger.info(f"✅ 从数据库找到模型 {model_name} 的供应商: {provider}")
            return provider

        # If not found in database, use default mapping
        logger.warning(f"⚠️ 数据库中未找到模型 {model_name}，使用默认映射")
        return _get_default_provider_by_model(model_name)

    except Exception as e:
        logger.error(f"❌ 查找模型供应商失败: {e}")
        return _get_default_provider_by_model(model_name)


def get_provider_by_model_name_sync(model_name: str, preferred_provider: Optional[str] = None) -> str:
    """
    Find the corresponding supplier from the database configuration based on the model name (synchronized version)

    Args:
        model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

    Returns:
        str: Supplier name, e.g. 'dashscope', 'openai' Wait
    """
    provider_info = get_provider_and_url_by_model_sync(model_name, preferred_provider=preferred_provider)
    return provider_info["provider"]


def get_provider_and_url_by_model_sync(
    model_name: str,
    preferred_provider: Optional[str] = None,
    preferred_config_id: Optional[str] = None,
) -> dict:
    """
    Find the corresponding vendor and API URL (sync version) from the database configuration based on the model name

    Args:
        model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

    Returns:
        dict: {"provider": "google", "backend_url": "https://...", "api_key": "xxx"}
    """
    try:
        # Direct query using synchronous MongoDB client
        from pymongo import MongoClient
        from app.core.config import settings
        import os

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]

        # Query the latest active configuration
        configs_collection = db.system_configs
        doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

        # 🔧 Parse old format "provider::model_name" (Such as jdyun::GLM-5) 
        if "::" in model_name:
            parsed_provider, parsed_model = model_name.split("::", 1)
            if not preferred_provider:
                preferred_provider = parsed_provider
            model_name = parsed_model
            logger.info(f"🔧 [Synchronous query] Parse old format model names: {parsed_provider}::{parsed_model} → provider={preferred_provider}, model={model_name}")

        # 🔧 Jingdong Cloud mode: directly use environment variable configuration and skip database query
        from app.core.jdyun import (
            is_jdyun_mode, get_jdyun_api_base, get_jdyun_api_key,
            get_jdyun_default_model, JDYUN_PROVIDER_NAME,
        )
        if is_jdyun_mode():
            api_base = get_jdyun_api_base()
            api_key = get_jdyun_api_key()
            if api_base and api_key:
                effective_model = model_name if model_name else get_jdyun_default_model()
                logger.info(f"🔧 [Jingdong cloud model] Use JD Cloud configuration: model={effective_model}, api_base={api_base}")
                return {
                    "provider": JDYUN_PROVIDER_NAME,
                    "backend_url": api_base,
                    "api_key": api_key,
                }

        normalized_provider = str(preferred_provider or "").strip().lower()
        normalized_config_id = str(preferred_config_id or "").strip()

        def _build_provider_result(config_dict: dict) -> dict:
            provider = str(config_dict.get("provider") or "").strip().lower()
            api_base = config_dict.get("api_base")
            model_api_key = config_dict.get("api_key")

            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider})

            from app.utils.api_key_utils import is_valid_api_key

            api_key = None
            api_key_source = None
            logger.info(f"🔍 [同步查询] 模型 {config_dict.get('model_name')} API Key 获取流程:")

            if provider_doc and provider_doc.get("api_key"):
                provider_api_key = provider_doc["api_key"]
                logger.info(f"   - in factory configuration api_key: {'valuable' if provider_api_key else 'empty'}")
                if is_valid_api_key(provider_api_key):
                    api_key = provider_api_key.strip()
                    api_key_source = "厂家配置"
                    logger.info("✅ [Synchronous query] ✅ Use the API Key configured by the manufacturer (priority 1)")
                else:
                    logger.warning("⚠️ [Synchronous query] The API Key configured by the manufacturer is invalid (may be a placeholder or null value)")
            else:
                logger.info(f"   - 厂家配置: {'存在但无API Key' if provider_doc else '不存在'}")

            if not api_key:
                logger.info(f"   - in model configuration api_key: {'valuable' if model_api_key else 'empty'}")
                if is_valid_api_key(model_api_key):
                    api_key = model_api_key.strip()
                    api_key_source = "模型配置"
                    logger.info("✅ [Synchronous query] ✅ Use the API Key configured by the model (Priority 2, alternative)")

            if not api_key:
                env_api_key = _get_env_api_key_for_provider(provider)
                logger.info(f"   - in environment variables api_key: {'valuable' if env_api_key else 'empty'}")
                if env_api_key:
                    api_key = env_api_key
                    api_key_source = "环境变量"
                    logger.info("✅ [Synchronous query] ✅ API Key using environment variables (Priority 3)")
                else:
                    logger.warning(f"⚠️ [Synchronous query] ❌ not found {provider} API Key (no manufacturer configuration, model configuration, environment variables)")

            if api_key_source:
                logger.info(f"✅ [Synchronous query] The final API Key source used: {api_key_source}")

            if api_base:
                backend_url = api_base
                logger.info(f"✅ [同步查询] 模型 {config_dict.get('model_name')} 使用自定义 API: {api_base}")
            elif provider_doc and provider_doc.get("default_base_url"):
                backend_url = provider_doc["default_base_url"]
                logger.info(f"✅ [同步查询] 模型 {config_dict.get('model_name')} 使用厂家默认 API: {backend_url}")
            else:
                backend_url = _get_default_backend_url(provider)
                logger.warning(f"⚠️ [同步查询] 厂家 {provider} 没有配置 default_base_url，使用硬编码默认值")

            return {
                "provider": provider,
                "backend_url": backend_url,
                "api_key": api_key,
            }

        if doc and "llm_configs" in doc:
            llm_configs = doc["llm_configs"]
            fallback_config = None

            if normalized_config_id:
                exact_config = next(
                    (
                        config_dict
                        for config_dict in llm_configs
                        if str(config_dict.get("config_id") or "").strip() == normalized_config_id
                        and config_dict.get("enabled", True)
                    ),
                    None,
                )
                if exact_config is not None:
                    result = _build_provider_result(exact_config)
                    client.close()
                    return result

            for config_dict in llm_configs:
                if config_dict.get("model_name") != model_name:
                    continue

                provider = str(config_dict.get("provider") or "").strip().lower()
                if fallback_config is None:
                    fallback_config = config_dict
                if normalized_provider and provider != normalized_provider:
                    continue
                result = _build_provider_result(config_dict)
                client.close()
                return result

            if fallback_config is not None:
                logger.warning(f"⚠️ [同步查询] 模型 {model_name} 未找到 provider={normalized_provider or '-'} 的精确配置，回退到同名模型的首个配置")
                result = _build_provider_result(fallback_config)
                client.close()
                return result

        client.close()

        # If the model configuration is not found in the database, the default mapping is used
        logger.warning(f"⚠️ [Synchronous query] Model not found in database {model_name}, Use default mapping")
        provider = _get_default_provider_by_model(model_name)

        # Try to get default_base_url and API Key
        try:
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider})

            backend_url = _get_default_backend_url(provider)
            api_key = None

            # 🔥 Import API Key verification function
            from app.utils.api_key_utils import is_valid_api_key
            
            if provider_doc:
                if provider_doc.get("default_base_url"):
                    backend_url = provider_doc["default_base_url"]
                    logger.info(f"✅ [Synchronous query] Use manufacturer {provider} of default_base_url: {backend_url}")

                if provider_doc.get("api_key"):
                    provider_api_key = provider_doc["api_key"]
                    # 🔥 Use is_valid_api_key to verify factory configuration API Key
                    if is_valid_api_key(provider_api_key):
                        api_key = provider_api_key.strip()
                        logger.info(f"✅ [同步查询] 使用厂家 {provider} 的 API Key")

            # If there is no API Key in the manufacturer configuration, try to obtain it from the environment variable
            if not api_key:
                api_key = _get_env_api_key_for_provider(provider)
                if api_key:
                    logger.info(f"✅ [Synchronous query] using environment variables API Key")

            client.close()
            return {
                "provider": provider,
                "backend_url": backend_url,
                "api_key": api_key
            }
        except Exception as e:
            logger.warning(f"⚠️ [Synchronous query] Unable to query manufacturer configuration: {e}")

        # Finally fallback to hardcoded default URLs and environment variables API Key
        return {
            "provider": provider,
            "backend_url": _get_default_backend_url(provider),
            "api_key": _get_env_api_key_for_provider(provider)
        }

    except Exception as e:
        logger.error(f"❌ [Synchronous query] Failed to find model supplier: {e}")
        provider = _get_default_provider_by_model(model_name)

        # Try to get default_base_url and API Key
        try:
            from pymongo import MongoClient
            from app.core.config import settings

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider})

            backend_url = _get_default_backend_url(provider)
            api_key = None

            # 🔥 Import API Key verification function
            from app.utils.api_key_utils import is_valid_api_key
            
            if provider_doc:
                if provider_doc.get("default_base_url"):
                    backend_url = provider_doc["default_base_url"]
                    logger.info(f"✅ [Synchronous query] Use manufacturer {provider} of default_base_url: {backend_url}")

                if provider_doc.get("api_key"):
                    provider_api_key = provider_doc["api_key"]
                    # 🔥 Use is_valid_api_key to verify factory configuration API Key
                    if is_valid_api_key(provider_api_key):
                        api_key = provider_api_key.strip()
                        logger.info(f"✅ [同步查询] 使用厂家 {provider} 的 API Key")

            # If there is no API Key in the manufacturer configuration, try to obtain it from the environment variable
            if not api_key:
                api_key = _get_env_api_key_for_provider(provider)

            client.close()
            return {
                "provider": provider,
                "backend_url": backend_url,
                "api_key": api_key
            }
        except Exception as e2:
            logger.warning(f"⚠️ [Synchronous query] Unable to query manufacturer configuration: {e2}")

        # Finally fallback to hardcoded default URLs and environment variables API Key
        return {
            "provider": provider,
            "backend_url": _get_default_backend_url(provider),
            "api_key": _get_env_api_key_for_provider(provider)
        }


def _get_env_api_key_for_provider(provider: str) -> str:
    """
    Get the specified vendor from an environment variable API Key

    Args:
        provider: Supplier name, e.g. 'google', 'dashscope' Wait

    Returns:
        str: API Key, Return if not found None
    """
    import os

    env_key_map = {
        "google": "GOOGLE_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "qianfan": "QIANFAN_API_KEY",
        "302ai": "AI302_API_KEY",
    }

    env_key_name = env_key_map.get(provider.lower())
    if env_key_name:
        api_key = os.getenv(env_key_name)
        # 🔥 Use is_valid_api_key to verify the environment variable API Key
        from app.utils.api_key_utils import is_valid_api_key
        if is_valid_api_key(api_key):
            return api_key.strip()

    return None


def _get_default_backend_url(provider: str) -> str:
    """
    Returns the default based on supplier name backend_url

    Args:
        provider: Supplier name, e.g. 'google', 'dashscope' Wait

    Returns:
        str: default backend_url
    """
    default_urls = {
        "google": "https://generativelanguage.googleapis.com/v1beta",
        "dashscope": "https://dashscope.aliyuncs.com/api/v1",
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com",
        "anthropic": "https://api.anthropic.com",
        "openrouter": "https://openrouter.ai/api/v1",
        "qianfan": "https://qianfan.baidubce.com/v2",
        "302ai": "https://api.302.ai/v1",
    }

    url = default_urls.get(provider, "https://dashscope.aliyuncs.com/compatible-mode/v1")
    logger.info(f"🔧 [默认URL] {provider} -> {url}")
    return url


def _get_default_provider_by_model(model_name: str) -> str:
    """
    Returns the default supplier mapping based on model name
    This is a fallback solution used when a database query fails
    """
    # Default mapping of model names to vendors
    # ⚠️ Note: This is only a fallback solution and should be obtained from the database configuration first.
    model_provider_map = {
        # Ali Bailian (DashScope)
        'qwen-turbo': 'dashscope',
        'qwen-plus': 'dashscope',
        'qwen-max': 'dashscope',
        'qwen-plus-latest': 'dashscope',
        'qwen-max-longcontext': 'dashscope',

        # OpenAI
        'gpt-3.5-turbo': 'openai',
        'gpt-4': 'openai',
        'gpt-4-turbo': 'openai',
        'gpt-4o': 'openai',
        'gpt-4o-mini': 'openai',

        # Google
        'gemini-pro': 'google',
        'gemini-2.0-flash': 'google',
        'gemini-2.0-flash-thinking-exp': 'google',

        # DeepSeek
        'deepseek-chat': 'deepseek',
        'deepseek-coder': 'deepseek',

        # Wisdom spectrum AI
        'glm-4': 'zhipu',
        'glm-3-turbo': 'zhipu',
        'chatglm3-6b': 'zhipu'
    }

    provider = model_provider_map.get(model_name, 'dashscope')  # By default, Ali Bailian is used.
    logger.info(f"🔧 使用默认映射: {model_name} -> {provider}")
    return provider


def _load_model_config_from_db(model_name: str) -> dict:
    """
    Read model configuration parameters from the database (max_tokens, temperature, timeout, reasoning_effort etc.)

    Args:
        model_name: Model name

    Returns:
        dict: Model configuration dictionary, such as {"max_tokens": 4000, "temperature": 0.7, "reasoning_effort": "low"}
    """
    try:
        from pymongo import MongoClient
        from app.core.config import settings

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        configs_collection = db.system_configs
        doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

        if doc and "llm_configs" in doc:
            for config_dict in doc["llm_configs"]:
                if config_dict.get("model_name") == model_name:
                    result = {
                        "max_tokens": config_dict.get("max_tokens", 4000),
                        "temperature": config_dict.get("temperature", 0.7),
                        "timeout": config_dict.get("timeout", 180),
                        "retry_times": config_dict.get("retry_times", 3),
                        "api_base": config_dict.get("api_base"),
                    }
                    # 🔧 Volcano Ark inference model support reasoning_effort
                    if config_dict.get("reasoning_effort"):
                        result["reasoning_effort"] = config_dict["reasoning_effort"]
                        logger.info(f"🔧 [模型配置] {model_name} reasoning_effort={result['reasoning_effort']}")
                    else:
                        logger.info(f"🔧 [模型配置] {model_name} reasoning_effort 未设置")
                    client.close()
                    return result

        client.close()
        return {}
    except Exception as e:
        logger.warning(f"⚠️ 读取模型配置失败: {e}")
        return {}


def create_analysis_config(
    research_depth,  # Support numbers(1-5)or string("fast", "Standard", "Depth")
    selected_analysts: list,
    quick_model: str,
    deep_model: str,
    llm_provider: str,
    market_type: str = "A股",
    quick_model_config: dict = None,  # New: Full configuration of fast models
    deep_model_config: dict = None    # New: Complete configuration of deep models
) -> dict:
    """
    Create analysis configuration - supports numeric grades and Chinese grades

    Args:
        research_depth: Research depth, supporting numbers(1-5)or chinese("fast", "Basics", "Standard", "Depth", "Comprehensive")
        selected_analysts: List of selected analysts
        quick_model: Quickly analyze models
        deep_model: Deep analysis model
        llm_provider: LLM supplier
        market_type: market type
        quick_model_config: Complete configuration of fast model (including max_tokens, temperature, timeout, etc.)
        deep_model_config: Complete configuration of the deep model (including max_tokens, temperature, timeout, etc.)

    Returns:
        dict: Complete analysis configuration
    """
    # 🔍 [Debugging] Record the original parameters received
    logger.info(f"🔍 [配置创建] 接收到的research_depth参数: {research_depth} (类型: {type(research_depth).__name__})")

    # Mapping of numerical grades to Chinese grades
    numeric_to_chinese = {
        1: "快速",
        2: "基础",
        3: "标准",
        4: "深度",
        5: "全面"
    }

    # Standardization Research Depth: Support Numeric Input
    if isinstance(research_depth, (int, float)):
        research_depth = int(research_depth)
        if research_depth in numeric_to_chinese:
            chinese_depth = numeric_to_chinese[research_depth]
            logger.info(f"🔢 [等级转换] 数字等级 {research_depth} → 中文等级 '{chinese_depth}'")
            research_depth = chinese_depth
        else:
            logger.warning(f"⚠️ 无效的数字等级: {research_depth}，使用默认标准分析")
            research_depth = "标准"
    elif isinstance(research_depth, str):
        # If it is a number in string form, convert it to an integer
        if research_depth.isdigit():
            numeric_level = int(research_depth)
            if numeric_level in numeric_to_chinese:
                chinese_depth = numeric_to_chinese[numeric_level]
                logger.info(f"🔢 [等级转换] 字符串数字 '{research_depth}' → 中文等级 '{chinese_depth}'")
                research_depth = chinese_depth
            else:
                logger.warning(f"⚠️ Invalid string numeric level: {research_depth}, Analyze using default criteria")
                research_depth = "标准"
        # If you are already at Chinese level, use it directly
        elif research_depth in ["快速", "基础", "标准", "深度", "全面"]:
            logger.info(f"📝 [Level confirmation] Use Chinese level: '{research_depth}'")
        else:
            logger.warning(f"⚠️ 未知的研究深度: {research_depth}，使用默认标准分析")
            research_depth = "标准"
    else:
        logger.warning(f"⚠️ Invalid research depth type: {type(research_depth)}, Analyze using default criteria")
        research_depth = "标准"

    # Starting from DEFAULT_CONFIG, completely copy the logic of the web directory
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = llm_provider
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model

    # Adjust configuration based on research depth - 5 levels supported (consistent with web interface)
    if research_depth == "快速":
        # 1 Level - Quick Analysis
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        config["memory_enabled"] = False  # Disable memory for speed
        config["online_tools"] = True  # Use online tools uniformly to avoid various problems with offline tools
        logger.info(f"🔧 [1级-快速分析] {market_type}使用统一工具，确保数据源正确和稳定性")
        logger.info(f"🔧 [1 Level-Quick Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "基础":
        # 2 Level - Basic Analysis
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [2级-基础分析] {market_type}使用在线工具，获取最新数据")
        logger.info(f"🔧 [2 Level-Basic Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "标准":
        # 3 Level - Standard Analysis (recommended)
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [3级-标准分析] {market_type}平衡速度和质量（推荐）")
        logger.info(f"🔧 [3 Level-Standard Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "深度":
        # 4 Level - In-Depth Analysis
        config["max_debate_rounds"] = 2
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [4级-深度分析] {market_type}多轮辩论，深度研究")
        logger.info(f"🔧 [4 Level-depth analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    elif research_depth == "全面":
        # 5 Level - Comprehensive Analysis
        config["max_debate_rounds"] = 3
        config["max_risk_discuss_rounds"] = 3
        config["memory_enabled"] = True
        config["online_tools"] = True
        logger.info(f"🔧 [5级-全面分析] {market_type}最全面的分析，最高质量")
        logger.info(f"🔧 [5 Level - Comprehensive Analysis] Using user-configured models: quick={quick_model}, deep={deep_model}")

    else:
        # Use standard analysis by default
        logger.warning(f"⚠️ 未知的研究深度: {research_depth}，使用标准分析")
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 2
        config["memory_enabled"] = True
        config["online_tools"] = True

    # 🔧 A1: Research depth level → reasoning_effort Think about budget defaults
    # Only the Volcano Ark inference model takes effect when injected into the graph layer; when the DB model configuration is explicitly set, the DB shall prevail.
    config["depth_reasoning_effort"] = RESEARCH_DEPTH_REASONING_EFFORT.get(research_depth, "medium")

    # 🔧 Get backend_url and API Key (Priority: Model Configuration > Factory configuration > environment variables)
    try:
        # 1️⃣ Priority is obtained from the database (including the api_base and API Key of the model configuration and the manufacturer's default_base_url and API Key)
        quick_provider_info = get_provider_and_url_by_model_sync(quick_model)
        deep_provider_info = get_provider_and_url_by_model_sync(deep_model)

        config["backend_url"] = quick_provider_info["backend_url"]
        config["quick_api_key"] = quick_provider_info.get("api_key")  # 🔥 Save quick model API Key
        config["deep_api_key"] = deep_provider_info.get("api_key")    # 🔥 Save the depth model API Key

        logger.info(f"✅ Configured using database backend_url: {quick_provider_info['backend_url']}")
        logger.info(f"   来源: 模型 {quick_model} 的配置或厂家 {quick_provider_info['provider']} 的默认地址")
        logger.info(f"🔑 quick model API Key: {'configured' if config['quick_api_key'] else 'Not configured (environment variables will be used)'}")
        logger.info(f"🔑 deep model API Key: {'configured' if config['deep_api_key'] else 'Not configured (environment variables will be used)'}")
    except Exception as e:
        logger.warning(f"⚠️  Unable to get backend_url and API Key: {e}")
        # 2️⃣ Fallback to hardcoded default URL, API Key will be read from environment variables
        if llm_provider == "dashscope":
            config["backend_url"] = "https://dashscope.aliyuncs.com/api/v1"
        elif llm_provider == "deepseek":
            config["backend_url"] = "https://api.deepseek.com"
        elif llm_provider == "openai":
            config["backend_url"] = "https://api.openai.com/v1"
        elif llm_provider == "google":
            config["backend_url"] = "https://generativelanguage.googleapis.com/v1beta"
        elif llm_provider == "qianfan":
            config["backend_url"] = "https://aip.baidubce.com"
        else:
            # 🔧 Unknown manufacturer, try to get the manufacturer's information from the database default_base_url
            logger.warning(f"⚠️  未知厂家 {llm_provider}，尝试从数据库获取配置")
            try:
                from pymongo import MongoClient
                from app.core.config import settings

                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                providers_collection = db.llm_providers
                provider_doc = providers_collection.find_one({"name": llm_provider})

                if provider_doc and provider_doc.get("default_base_url"):
                    config["backend_url"] = provider_doc["default_base_url"]
                    logger.info(f"✅ Get custom manufacturer from database {llm_provider} of backend_url: {config['backend_url']}")
                else:
                    # If it's not in the database either, use the OpenAI compatible format as a last resort fallback
                    config["backend_url"] = "https://api.openai.com/v1"
                    logger.warning(f"⚠️  Manufacturer not found in database {llm_provider} configuration, using the default OpenAI endpoint")

                client.close()
            except Exception as e2:
                logger.error(f"❌ 查询数据库失败: {e2}，使用默认 OpenAI 端点")
                config["backend_url"] = "https://api.openai.com/v1"

        logger.info(f"⚠️  Use fallback backend_url: {config['backend_url']}")

    # Add analyst configuration
    config["selected_analysts"] = selected_analysts
    config["debug"] = False

    # 🔧 Add research_depth to the configuration to enable tool functions to access analysis-level information
    config["research_depth"] = research_depth

    # 🔧 Add model configuration parameters (max_tokens, temperature, timeout, retry_times)
    if quick_model_config:
        config["quick_model_config"] = quick_model_config
        logger.info(f"🔧 [Quick model configuration] max_tokens={quick_model_config.get('max_tokens')}, "
                   f"temperature={quick_model_config.get('temperature')}, "
                   f"timeout={quick_model_config.get('timeout')}, "
                   f"retry_times={quick_model_config.get('retry_times')}")

    if deep_model_config:
        config["deep_model_config"] = deep_model_config
        logger.info(f"🔧 [Deep model configuration] max_tokens={deep_model_config.get('max_tokens')}, "
                   f"temperature={deep_model_config.get('temperature')}, "
                   f"timeout={deep_model_config.get('timeout')}, "
                   f"retry_times={deep_model_config.get('retry_times')}")

    logger.info(f"📋 ========== Creating analysis configuration is complete ==========")
    logger.info(f"   🎯 研究深度: {research_depth}")
    logger.info(f"   🔥 辩论轮次: {config['max_debate_rounds']}")
    logger.info(f"   🧠 推理思考预算: {config['depth_reasoning_effort']}（火山方舟推理模型生效，DB显式配置优先）")
    logger.info(f"   ⚖️ 风险讨论轮次: {config['max_risk_discuss_rounds']}")
    logger.info(f"   💾 记忆功能: {config['memory_enabled']}")
    logger.info(f"   🌐 在线工具: {config['online_tools']}")
    logger.info(f"   🤖 LLM供应商: {llm_provider}")
    logger.info(f"   ⚡ 快速模型: {config['quick_think_llm']}")
    logger.info(f"   🧠 深度模型: {config['deep_think_llm']}")
    logger.info(f"📋 ========================================")

    return config


class SimpleAnalysisService:
    """简化的股票分析服务类"""

    def __init__(self):
        self._trading_graph_cache = {}
        self.memory_manager = get_memory_state_manager()

        # Progress tracker cache
        self._progress_trackers: Dict[str, RedisProgressTracker] = {}

        # 🔧 Create a shared thread pool to support concurrent execution of multiple analysis tasks
        # By default, up to 3 analysis tasks can be executed simultaneously (can be adjusted according to server resources)
        import concurrent.futures
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)

        logger.info(f"🔧 [Service initialization] SimpleAnalysisService Example ID: {id(self)}")
        logger.info(f"🔧 [Service initialization] Memory manager instance ID: {id(self.memory_manager)}")
        logger.info(f"🔧 [Service initialization] Maximum number of concurrent thread pools: 3")

        # Set up the WebSocket manager
        # Simple stock name caching to reduce duplicate queries
        self._stock_name_cache: Dict[str, str] = {}

        # Set up the WebSocket manager
        try:
            from app.services.websocket_manager import get_websocket_manager
            self.memory_manager.set_websocket_manager(get_websocket_manager())
        except ImportError:
            logger.warning("⚠️ WebSocket Manager is unavailable")

    async def _update_progress_async(self, task_id: str, progress: int, message: str):
        """Asynchronous update progress (memory and MongoDB)"""
        try:
            # Update memory
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=progress,
                message=message,
                current_step=message
            )

            # update MongoDB
            from app.core.database import get_mongo_db
            from datetime import datetime
            db = get_mongo_db()
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "progress": progress,
                        "current_step": message,
                        "message": message,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            logger.debug(f"✅ [Asynchronous updates] Updated memory and MongoDB: {progress}%")
        except Exception as e:
            logger.warning(f"⚠️ [Asynchronous updates] failed: {e}")

    def _resolve_stock_name(self, code: Optional[str]) -> str:
        """解析股票名称（带缓存）"""
        if not code:
            return ""
        # hit cache
        if code in self._stock_name_cache:
            return self._stock_name_cache[code]
        name = None
        try:
            name = _get_cached_security_name(code)
            if name:
                self._stock_name_cache[code] = name
                return name

            if _get_stock_info_safe:
                info = _get_stock_info_safe(code)
                if isinstance(info, dict):
                    name = info.get("name")
        except Exception as e:
            logger.warning(f"⚠️ 获取股票名称失败: {code} - {e}")
        if not name:
            name = f"{'ETF' if _is_cn_etf_symbol(code) else 'stocks'}{code}"
        # write cache
        self._stock_name_cache[code] = name
        return name

    def _enrich_stock_names(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Complete stock names for task list(Update in place)"""
        try:
            for t in tasks:
                code = t.get("stock_code") or t.get("stock_symbol")
                name = t.get("stock_name")
                if not name and code:
                    t["stock_name"] = self._resolve_stock_name(code)
        except Exception as e:
            logger.warning(f"⚠️ Exception occurred when completing stock name: {e}")
        return tasks

    def _convert_user_id(self, user_id: str) -> PyObjectId:
        """Convert string user ID to PyObjectId"""
        try:
            logger.info(f"🔄 开始转换用户ID: {user_id} (类型: {type(user_id)})")

            # If you are an admin user, use a fixed ObjectId
            if user_id == "admin":
                admin_object_id = ObjectId("507f1f77bcf86cd799439011")
                logger.info(f"🔄 Convert admin user ID: {user_id} -> {admin_object_id}")
                return PyObjectId(admin_object_id)
            else:
                # Try converting the string to ObjectId
                object_id = ObjectId(user_id)
                logger.info(f"🔄 转换用户ID: {user_id} -> {object_id}")
                return PyObjectId(object_id)
        except Exception as e:
            logger.error(f"❌ 用户ID转换失败: {user_id} -> {e}")
            # If the conversion fails, generate a new ObjectId
            new_object_id = ObjectId()
            logger.warning(f"⚠️ 生成新的用户ID: {new_object_id}")
            return PyObjectId(new_object_id)

    def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
        """Get or create a TradingAgents instance — Deactivated

        v3.0 The old TradingAgentsGraph engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService._get_trading_graph deactivated,"
            "TradingAgentsGraph No longer instantiated."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        # 🔧 [Concurrency safety] Create new instances every time to avoid sharing state among multiple threads
        # Caching is no longer used because TradingAgentsGraph has mutable instance variables
        logger.info(f"🔧 Create a new TradingAgents instance (concurrent safe mode)...")

        trading_graph = TradingAgentsGraph(
            selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
            debug=config.get("debug", False),
            config=config
        )

        logger.info(f"✅ TradingAgents Instance created successfully (instance ID: {id(trading_graph)}) ")

        return trading_graph

    async def create_analysis_task(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """Create an analysis task (return immediately, do not perform analysis)"""
        try:
            # Generate tasks ID
            task_id = str(uuid.uuid4())

            # 🔧 Use get_symbol() Method to get the stock code (compatible with symbol and stock_code fields)
            stock_code = request.get_symbol()
            if not stock_code:
                raise ValueError("股票代码不能为空")

            logger.info(f"📝 创建分析任务: {task_id} - {stock_code}")
            logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

            # Create task state in memory
            task_state = await self.memory_manager.create_task(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,
                parameters=request.parameters.model_dump() if request.parameters else {},
                stock_name=(self._resolve_stock_name(stock_code) if hasattr(self, '_resolve_stock_name') else None),
            )

            logger.info(f"✅ 任务状态已创建: {task_state.task_id}")

            # Immediately verify whether the task can be queried
            verify_task = await self.memory_manager.get_task(task_id)
            if verify_task:
                logger.info(f"✅ 任务创建验证成功: {verify_task.task_id}")
            else:
                logger.error(f"❌ Task creation verification failed: Unable to query the newly created task {task_id}")

            # Complete the stock name and write the initial record to the database task document
            code = stock_code
            name = self._resolve_stock_name(code) if hasattr(self, '_resolve_stock_name') else f"股票{code}"

            try:
                db = get_mongo_db()
                result = await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$setOnInsert": {
                        "task_id": task_id,
                        "user_id": user_id,
                        "stock_code": code,
                        "stock_symbol": code,
                        "stock_name": name,
                        "status": "pending",
                        "progress": 0,
                        "created_at": datetime.utcnow(),
                    }},
                    upsert=True
                )

                if result.upserted_id or result.matched_count > 0:
                    logger.info(f"✅ Task saved to MongoDB: {task_id}")
                else:
                    logger.warning(f"⚠️ MongoDB Exception in saving result: matched={result.matched_count}, upserted={result.upserted_id}")

            except Exception as e:
                logger.error(f"❌ Writing to MongoDB fails when creating a task: {e}")
                # Errors should not be ignored here as no MongoDB record will cause the status query to fail
                # But in order not to affect task execution, we record the error but continue execution
                import traceback
                logger.error(f"❌ MongoDB Save detailed errors: {traceback.format_exc()}")

            # 🔥 Add the task to the Redis queue and let the Worker process it
            try:
                from app.services.queue_service import get_queue_service
                queue_service = get_queue_service()

                # Prepare queue parameters
                queue_params = request.parameters.model_dump() if request.parameters else {}
                queue_params["engine"] = "legacy"  # Marked as legacy engine

                # 🔍 Debugging: print queue parameters
                logger.info(f"🔍 [DEBUG] Enqueue parameters: {queue_params}")

                # Join the team
                await queue_service.enqueue_task(
                    user_id=user_id,
                    symbol=stock_code,
                    params=queue_params,
                    task_id=task_id
                )
                logger.info(f"✅ 任务已加入队列: {task_id}")
            except Exception as e:
                logger.error(f"❌ 任务入队失败: {e}")
                import traceback
                logger.error(f"❌ 入队详细错误: {traceback.format_exc()}")

            return {
                "task_id": task_id,
                "status": "pending",
                "message": "The task has been created and is waiting to be executed"
            }

        except Exception as e:
            logger.error(f"❌ 创建分析任务失败: {e}")
            raise

    async def create_and_execute_analysis_v2(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """Create and perform stock analysis v2.0 - using the Unified Task Engine

        Advantages:
        - Support multi-engine switching (workflow/legacy/llm)
        - Unified task management and progress tracking
        - Automatically select the best engine
        - Tasks can be queried and canceled

        Args:
            user_id: User ID
            request: Analysis request

        Returns:
            Task information dictionary
        """
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType
        from app.models.user import PyObjectId

        # Get stock code
        stock_code = request.get_symbol()
        if not stock_code:
            raise ValueError("股票代码不能为空")

        logger.info(f"🚀 [stock analysis v2.0] Analysis using Unified Task Engine: {stock_code}")

        # Prepare task parameters
        task_params = {
            "symbol": stock_code,
            "market_type": request.parameters.market_type if request.parameters else "cn",
            "analysis_date": request.parameters.analysis_date if request.parameters else None,
            "research_depth": request.parameters.research_depth if request.parameters else "normal"
        }

        # If there are other parameters, add them too
        if request.parameters:
            params_dict = request.parameters.model_dump()
            task_params.update(params_dict)

        # Use unified task engine
        task_service = get_task_analysis_service()

        try:
            # Get the engine type (obtained from parameters, default auto)
            engine_type = "auto"
            preference_type = "neutral"

            if request.parameters:
                engine_type = getattr(request.parameters, "engine_type", "auto")
                preference_type = getattr(request.parameters, "preference_type", "neutral")

            # Create and execute tasks
            task = await task_service.create_and_execute_task(
                user_id=PyObjectId(user_id),
                task_type=AnalysisTaskType.STOCK_ANALYSIS,
                task_params=task_params,
                engine_type=engine_type,
                preference_type=preference_type
            )

            logger.info(f"✅ [股票分析v2.0] 分析完成: {stock_code}, 任务ID: {task.task_id}")

            # Return task information (compatible with existing API format)
            return {
                "task_id": task.task_id,
                "status": task.status,
                "message": "分析完成" if task.status == "completed" else "分析失败",
                "result": task.result,
                "execution_time": task.execution_time,
                "error_message": task.error_message
            }

        except Exception as e:
            logger.error(f"❌ [stock analysis v2.0] Analysis failed: {stock_code} - {e}", exc_info=True)
            raise

    async def execute_analysis_background(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest
    ):
        """Perform analysis tasks in the background — Deactivated

        v3.0 Since the old version of the legacy engine has been deactivated, the queue worker should use the v2 engine branch.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService.execute_analysis_background deactivated,"
            "task_id=%s The v2 engine (thread_worker s engine='v2' branch)."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % task_id
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        # 🔧 Use get_symbol() Method to get the stock code (compatible with symbol and stock_code fields)
        stock_code = request.get_symbol()

        # Add the outermost exception capture to ensure that all exceptions are logged
        try:
            logger.info(f"🎯🎯🎯 [ENTRY] execute_analysis_background method is called: {task_id}")
            logger.info(f"🎯🎯🎯 [ENTRY] user_id={user_id}, stock_code={stock_code}")
        except Exception as entry_error:
            print(f"❌❌❌ [CRITICAL] Logging failed: {entry_error}")
            import traceback
            traceback.print_exc()

        progress_tracker = None
        try:
            logger.info(f"🚀 Start performing analysis tasks in the background: {task_id}")

            # 🔍 Verify that the stock code exists
            logger.info(f"🔍 开始验证股票代码: {stock_code}")
            from tradingagents.utils.stock_validator import prepare_stock_data_async
            from datetime import datetime

            # Get market type
            market_type = request.parameters.market_type if request.parameters else "A股"

            # Get analysis date and convert to string format
            analysis_date = request.parameters.analysis_date if request.parameters else None
            if analysis_date:
                # If it is a datetime object, convert it to a string
                if isinstance(analysis_date, datetime):
                    analysis_date = analysis_date.strftime('%Y-%m-%d')
                # If it is a string, make sure it is formatted correctly
                elif isinstance(analysis_date, str):
                    # Try to parse and reformat to ensure the format is consistent
                    try:
                        parsed_date = datetime.strptime(analysis_date, '%Y-%m-%d')
                        analysis_date = parsed_date.strftime('%Y-%m-%d')
                    except ValueError:
                        # If the format is wrong, use today
                        analysis_date = datetime.now().strftime('%Y-%m-%d')
                        logger.warning(f"⚠️ Parse date format is incorrect, use today: {analysis_date}")

            # 🔥 Use the asynchronous version and await directly to avoid event loop conflicts
            validation_result = await prepare_stock_data_async(
                stock_code=stock_code,
                market_type=market_type,
                period_days=30,
                analysis_date=analysis_date
            )

            if not validation_result.is_valid:
                error_msg = f"❌ 股票代码验证失败: {validation_result.error_message}"
                logger.error(error_msg)
                logger.error(f"💡 建议: {validation_result.suggestion}")

                # Build user-friendly error messages
                user_friendly_error = (
                    f"❌ 股票代码无效\n\n"
                    f"{validation_result.error_message}\n\n"
                    f"💡 {validation_result.suggestion}"
                )

                # Update task status is failed
                await self.memory_manager.update_task_status(
                    task_id=task_id,
                    status=AnalysisStatus.FAILED,
                    progress=0,
                    error_message=user_friendly_error
                )

                # Update MongoDB status
                await self._update_task_status(
                    task_id,
                    AnalysisStatus.FAILED,
                    0,
                    error_message=user_friendly_error
                )

                return

            logger.info(f"✅ 股票代码验证通过: {stock_code} - {validation_result.stock_name}")
            logger.info(f"📊 市场类型: {validation_result.market_type}")
            logger.info(f"📈 历史数据: {'有' if validation_result.has_historical_data else '无'}")
            logger.info(f"📋 基本信息: {'有' if validation_result.has_basic_info else '无'}")

            # Create a Redis progress tracker in the thread pool (avoid blocking the event loop)
            def create_progress_tracker():
                """在线程中创建进度跟踪器"""
                logger.info(f"📊 [thread] Create a progress tracker: {task_id}")
                tracker = RedisProgressTracker(
                    task_id=task_id,
                    analysts=request.parameters.selected_analysts or ["market", "fundamentals"],
                    research_depth=request.parameters.research_depth or "标准",
                    llm_provider="dashscope"
                )
                logger.info(f"✅ [thread] Progress tracker created: {task_id}")
                return tracker

            progress_tracker = await asyncio.to_thread(create_progress_tracker)

            # Cache progress tracker
            self._progress_trackers[task_id] = progress_tracker

            # Register to log monitoring
            register_analysis_tracker(task_id, progress_tracker)

            # Initialization progress (executed in thread)
            await asyncio.to_thread(
                progress_tracker.update_progress,
                {
                    "progress_percentage": 10,
                    "last_message": "🚀 开始股票分析"
                }
            )

            # Update status is running
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="分析开始...",
                current_step="initialization"
            )

            # Synchronously update MongoDB status
            await self._update_task_status(task_id, AnalysisStatus.PROCESSING, 10)

            # Data preparation phase (executed in thread)
            await asyncio.to_thread(
                progress_tracker.update_progress,
                {
                    "progress_percentage": 20,
                    "last_message": "🔧 检查环境配置"
                }
            )
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=20,
                message="准备分析数据...",
                current_step="data_preparation"
            )

            # Synchronously update MongoDB status
            await self._update_task_status(task_id, AnalysisStatus.PROCESSING, 20)

            # Perform actual analysis
            result = await self._execute_analysis_sync(task_id, user_id, request, progress_tracker)

            # Mark progress tracker complete (execute in thread)
            await asyncio.to_thread(progress_tracker.mark_completed)

            # Save analysis results to files and databases
            try:
                logger.info(f"💾 开始保存分析结果: {task_id}")
                await self._save_analysis_results_complete(task_id, result)
                logger.info(f"✅ 分析结果保存完成: {task_id}")
            except Exception as save_error:
                logger.error(f"❌ 保存分析结果失败: {task_id} - {save_error}")
                # Failure to save does not affect the analysis completion status

            # 🔍 Debugging: Examine the data about to be saved to memory result
            logger.info(f"🔍 [DEBUG] The result key that will be saved to memory: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] to be saved to memory decision: {bool(result.get('decision'))}")
            if result.get('decision'):
                logger.info(f"🔍 [DEBUG] The decision content to be saved: {result['decision']}")

            # Update status is complete
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="分析完成",
                current_step="completed",
                result_data=result
            )

            # Synchronously update MongoDB status to complete
            await self._update_task_status(task_id, AnalysisStatus.COMPLETED, 100)

            # Create notification: Analysis completed (Option B:REST+SSE) 
            try:
                from app.services.notifications_service import get_notifications_service
                svc = get_notifications_service()
                summary = str(result.get("summary", ""))[:120]
                await svc.create_and_publish(
                    payload=NotificationCreate(
                        user_id=str(user_id),
                        type='analysis',
                        title=f"{request.stock_code} 分析完成",
                        content=summary,
                        link=f"/stocks/{request.stock_code}",
                        source='analysis'
                    )
                )
            except Exception as notif_err:
                logger.warning(f"⚠️ Failed to create notification(ignore): {notif_err}")

            # Send email notifications (if user has enabled email notifications) with PDF report
            try:
                from app.services.email_service import get_email_service
                from app.models.email import EmailType

                # Generate PDF attachment
                attachments = None
                try:
                    from app.utils.report_exporter import ReportExporter
                    from app.utils.report_formatter import extract_reports_from_state

                    report_exporter = ReportExporter()
                    if report_exporter.weasyprint_available or report_exporter.pdfkit_available:
                        # Extract report build document from state
                        state = result.get("state", {})
                        reports = extract_reports_from_state(state)

                        if reports:
                            # Build report document
                            stock_code = request.stock_code
                            stock_name = result.get("stock_name", stock_code)
                            analysis_date = result.get("analysis_date", "")

                            report_doc = {
                                "stock_symbol": stock_code,
                                "stock_name": stock_name,
                                "analysis_date": analysis_date,
                                "recommendation": result.get("recommendation", ""),
                                "confidence_score": result.get("confidence_score", 0),
                                "risk_level": result.get("risk_level", "中等"),
                                "reports": reports,
                                "decision": result.get("decision", {})
                            }

                            pdf_content = report_exporter.generate_pdf_report(report_doc)
                            if pdf_content:
                                filename = f"{stock_code}_{analysis_date}_分析报告.pdf"
                                attachments = [(filename, pdf_content, "application/pdf")]
                                logger.info(f"📄 PDF report generated: {filename} ({len(pdf_content)} bytes)")
                except Exception as pdf_err:
                    logger.warning(f"⚠️ PDF Build failed(Email will be sent without attachments): {pdf_err}")

                email_service = get_email_service()
                await email_service.send_analysis_email(
                    user_id=str(user_id),
                    email_type=EmailType.SINGLE_ANALYSIS,
                    template_name="single_analysis",
                    template_data={
                        "stock_code": request.stock_code,
                        "stock_name": result.get("stock_name", request.stock_code),
                        "analysis_date": result.get("analysis_date", ""),
                        "summary": result.get("summary", ""),
                        "recommendation": result.get("recommendation", ""),
                        "confidence_score": result.get("confidence_score", 0),
                        "risk_level": result.get("risk_level", "中等"),
                        "key_points": result.get("key_points", []),
                        "detail_url": f"{request.stock_code}"
                    },
                    reference_id=task_id,
                    attachments=attachments  # Comes with PDF report
                )
                logger.info(f"📧 Attempted to send analysis completion email: {task_id}")
            except Exception as email_err:
                logger.warning(f"⚠️ Failed to send email notification(ignore): {email_err}")

            logger.info(f"✅ 后台分析任务完成: {task_id}")

        except Exception as e:
            logger.error(f"❌ 后台分析任务失败: {task_id} - {e}")

            # Format error messages into user-friendly prompts
            from ..utils.error_formatter import ErrorFormatter

            # Gather contextual information
            error_context = {}
            if hasattr(request, 'parameters') and request.parameters:
                if hasattr(request.parameters, 'quick_model'):
                    error_context['model'] = request.parameters.quick_model
                if hasattr(request.parameters, 'deep_model'):
                    error_context['model'] = request.parameters.deep_model

            # Formatting error
            formatted_error = ErrorFormatter.format_error(str(e), error_context)

            # Build user-friendly error messages
            user_friendly_error = (
                f"{formatted_error['title']}\n\n"
                f"{formatted_error['message']}\n\n"
                f"💡 {formatted_error['suggestion']}"
            )

            # Marking progress tracker failed
            if progress_tracker:
                progress_tracker.mark_failed(user_friendly_error)

            # Update status is failed
            await self.memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0,
                message="分析失败",
                current_step="failed",
                error_message=user_friendly_error
            )

            # Synchronous update of MongoDB status is failed
            await self._update_task_status(task_id, AnalysisStatus.FAILED, 0, user_friendly_error)
        finally:
            # Clean progress tracker cache
            if task_id in self._progress_trackers:
                del self._progress_trackers[task_id]

            # Log out from log monitoring
            unregister_analysis_tracker(task_id)

    async def _execute_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: Optional[RedisProgressTracker] = None
    ) -> Dict[str, Any]:
        """Synchronous execution of analysis (running in a shared thread pool)— Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService._execute_analysis_sync deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % task_id
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        # 🔧 Use a shared thread pool to support concurrent execution of multiple tasks
        # No longer create a new thread pool every time to avoid serial execution
        loop = asyncio.get_event_loop()
        stock_code = request.get_symbol()  # 🔑 Fix: use get_symbol() method
        logger.info(f"🚀 [thread pool] Submit analysis tasks to the shared thread pool: {task_id} - {stock_code}")
        result = await loop.run_in_executor(
            self._thread_pool,  # Use shared thread pool
            self._run_analysis_sync,
            task_id,
            user_id,
            request,
            progress_tracker
        )
        logger.info(f"✅ [thread pool] Analysis task execution completed: {task_id}")
        return result

    def _run_analysis_sync(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker: Optional[RedisProgressTracker] = None
    ) -> Dict[str, Any]:
        """Specific implementation of synchronous execution analysis — Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] SimpleAnalysisService._run_analysis_sync deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % task_id
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            # 🔑 Key: Extract the stock symbol at the beginning of the method (compatible with symbol and stock_code fields)
            stock_code = request.get_symbol()

            # Reinitialize the logging system in a thread
            from tradingagents.utils.logging_init import init_logging, get_logger
            init_logging()
            thread_logger = get_logger('analysis_thread')

            thread_logger.info(f"🔄 [thread pool] Start performing analysis: {task_id} - {stock_code}")
            logger.info(f"🔄 [thread pool] Start performing analysis: {task_id} - {stock_code}")

            # 🔧 Calculate accurate progress based on step weights of RedisProgressTracker
            # Basic preparation stage (10%): 0.03 + 0.02 + 0.01 + 0.02 + 0.02 = 0.10
            # Step index 0-4 corresponds 0-10%

            # Asynchronous update progress (called in the thread pool)
            def update_progress_sync(progress: int, message: str, step: str):
                """在线程池中同步更新进度"""
                try:
                    # Also updates the Redis progress tracker
                    if progress_tracker:
                        progress_tracker.update_progress({
                            "progress_percentage": progress,
                            "last_message": message
                        })

                    # 🔥 Use synchronous methods to update memory and MongoDB to avoid event loop conflicts
                    # 1. Update task state in memory (using new event loop)
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            self.memory_manager.update_task_status(
                                task_id=task_id,
                                status=TaskStatus.RUNNING,
                                progress=progress,
                                message=message,
                                current_step=step
                            )
                        )
                    finally:
                        loop.close()

                    # 2. Update MongoDB (use synchronous client to avoid event loop conflicts)
                    from pymongo import MongoClient
                    from app.core.config import settings
                    from datetime import datetime

                    sync_client = MongoClient(settings.MONGO_URI)
                    sync_db = sync_client[settings.MONGO_DB]

                    sync_db.analysis_tasks.update_one(
                        {"task_id": task_id},
                        {
                            "$set": {
                                "progress": progress,
                                "current_step": step,
                                "message": message,
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    sync_client.close()

                except Exception as e:
                    logger.warning(f"⚠️ 进度更新失败: {e}")

            # Configuration phase - corresponding steps 3 "⚙️ Parameter settings" (6-8%)
            update_progress_sync(7, "⚙️ 配置分析参数", "configuration")

            # 🆕 Intelligent model selection logic
            from app.services.model_capability_service import get_model_capability_service
            capability_service = get_model_capability_service()

            research_depth = request.parameters.research_depth if request.parameters else "标准"

            # 1. Check if the frontend has a model specified
            if (request.parameters and
                hasattr(request.parameters, 'quick_analysis_model') and
                hasattr(request.parameters, 'deep_analysis_model') and
                request.parameters.quick_analysis_model and
                request.parameters.deep_analysis_model):

                # Use the model specified by the front end
                quick_model = request.parameters.quick_analysis_model
                deep_model = request.parameters.deep_analysis_model

                logger.info(f"📝 [Analysis Services] user specified model: quick={quick_model}, deep={deep_model}")

                # Verify that the model is suitable
                validation = capability_service.validate_model_pair(
                    quick_model, deep_model, research_depth
                )

                if not validation["valid"]:
                    # Log warning
                    for warning in validation["warnings"]:
                        logger.warning(warning)

                    # If the model is not suitable, automatically switch to the recommended model
                    logger.info(f"🔄 Automatically switch to recommended models...")
                    quick_model, deep_model = capability_service.recommend_models_for_depth(
                        research_depth
                    )
                    logger.info(f"✅ Switched: quick={quick_model}, deep={deep_model}")
                else:
                    # Even if the verification passes, a warning message is logged
                    for warning in validation["warnings"]:
                        logger.info(warning)
                    logger.info(f"✅ The model selected by the user is verified passed: quick={quick_model}, deep={deep_model}")

            else:
                # 2. Automatic recommendation model
                quick_model, deep_model = capability_service.recommend_models_for_depth(
                    research_depth
                )
                logger.info(f"🤖 Automatic recommendation model: quick={quick_model}, deep={deep_model}")

            # 🔧 Find the corresponding suppliers and suppliers based on the fast model and deep model respectively. API URL
            quick_provider_info = get_provider_and_url_by_model_sync(quick_model)
            deep_provider_info = get_provider_and_url_by_model_sync(deep_model)

            quick_provider = quick_provider_info["provider"]
            deep_provider = deep_provider_info["provider"]
            quick_backend_url = quick_provider_info["backend_url"]
            deep_backend_url = deep_provider_info["backend_url"]

            logger.info(f"🔍 [供应商查找] 快速模型 {quick_model} 对应的供应商: {quick_provider}")
            logger.info(f"🔍 [API address] Quick model usage backend_url: {quick_backend_url}")
            logger.info(f"🔍 [供应商查找] 深度模型 {deep_model} 对应的供应商: {deep_provider}")
            logger.info(f"🔍 [API address] Deep model usage backend_url: {deep_backend_url}")

            # Check if two models are from the same manufacturer
            if quick_provider == deep_provider:
                logger.info(f"✅ [Supplier verification] Both models are from the same manufacturer: {quick_provider}")
            else:
                logger.info(f"✅ [混合模式] 快速模型({quick_provider}) 和 深度模型({deep_provider}) 来自不同厂家")

            # Get market type
            market_type = request.parameters.market_type if request.parameters else "A股"
            logger.info(f"📊 [market type] Use market type: {market_type}")

            # 🔧 Read model configuration parameters from the database (max_tokens, temperature, timeout, reasoning_effort etc.)
            quick_model_config = _load_model_config_from_db(quick_model)
            deep_model_config = _load_model_config_from_db(deep_model)
            if quick_model_config:
                logger.info(f"🔧 [快速模型配置] {quick_model_config}")
            if deep_model_config:
                logger.info(f"🔧 [深度模型配置] {deep_model_config}")

            # Create analysis configurations (supports mixed mode)
            config = create_analysis_config(
                research_depth=research_depth,
                selected_analysts=request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=quick_provider,  # Suppliers who primarily use rapid models
                market_type=market_type,  # Market type using front-end delivery
                quick_model_config=quick_model_config,
                deep_model_config=deep_model_config,
            )

            # 🔧 Add mixed mode configuration
            config["quick_provider"] = quick_provider
            config["deep_provider"] = deep_provider
            config["quick_backend_url"] = quick_backend_url
            config["deep_backend_url"] = deep_backend_url
            config["backend_url"] = quick_backend_url  # Stay backwards compatible

            # 🔍 Validate models in configuration
            logger.info(f"🔍 [Model validation] Quick model in configuration: {config.get('quick_think_llm')}")
            logger.info(f"🔍 [Model validation] Deep model in configuration: {config.get('deep_think_llm')}")
            logger.info(f"🔍 [Model validation] LLM provider in configuration: {config.get('llm_provider')}")

            # Initializing the analysis engine - corresponding steps 4 "🚀 Start the engine" (8-10%)
            update_progress_sync(9, "🚀 初始化AI分析引擎", "engine_initialization")
            trading_graph = self._get_trading_graph(config)

            # 🔍 Verify configuration in TradingGraph instance
            logger.info(f"🔍 [Engine verification] TradingGraph Quick model in configuration: {trading_graph.config.get('quick_think_llm')}")
            logger.info(f"🔍 [Engine verification] TradingGraph Deep model in configuration: {trading_graph.config.get('deep_think_llm')}")

            # Prepare data for analysis
            start_time = datetime.now()

            # 🔧 Use the parsed date passed by the front end, or the current date if not available
            if request.parameters and hasattr(request.parameters, 'analysis_date') and request.parameters.analysis_date:
                # The front end is passed a datetime object or string
                if isinstance(request.parameters.analysis_date, datetime):
                    analysis_date = request.parameters.analysis_date.strftime("%Y-%m-%d")
                elif isinstance(request.parameters.analysis_date, str):
                    analysis_date = request.parameters.analysis_date
                else:
                    analysis_date = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"📅 Use the analysis date specified by the front end: {analysis_date}")
            else:
                analysis_date = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"📅 Use current date as analysis date: {analysis_date}")

            # 🔧 Intelligent date range processing: get the last 10 days of data and automatically handle weekends/holidays
            # This ensures that data for the last trading day is available even on weekends or holidays
            from tradingagents.utils.dataflow_utils import get_trading_date_range
            data_start_date, data_end_date = get_trading_date_range(analysis_date, lookback_days=10)

            logger.info(f"📅 分析目标日期: {analysis_date}")
            logger.info(f"📅 数据查询范围: {data_start_date} 至 {data_end_date} (最近10天)")
            logger.info(f"💡 Description: Get 10 days of data to automatically handle weekends, holidays and data delays")

            # Start analysis - 10% progress, about to enter the analyst stage
            # Note: Do not manually set the progress too high and let graph_progress_callback update the actual analysis progress.
            update_progress_sync(10, "🤖 开始多智能体协作分析", "agent_analysis")

            # Start an asynchronous task to simulate progress updates
            import threading
            import time

            def simulate_progress():
                """Simulate TradingAgents internal progress"""
                try:
                    if not progress_tracker:
                        return

                    # Analyst stage - dynamically adjusted based on the number of analysts selected
                    analysts = request.parameters.selected_analysts if request.parameters else ["market", "fundamentals"]

                    # Simulation Analyst Execution
                    for i, analyst in enumerate(analysts):
                        time.sleep(15)  # About 15 seconds per analyst
                        if analyst == "market":
                            progress_tracker.update_progress("📊 市场分析师正在分析")
                        elif analyst == "fundamentals":
                            progress_tracker.update_progress("💼 基本面分析师正在分析")
                        elif analyst == "news":
                            progress_tracker.update_progress("📰 新闻分析师正在分析")
                        elif analyst == "social":
                            progress_tracker.update_progress("💬 Social media analysts are analyzing")

                    # research team stage
                    time.sleep(10)
                    progress_tracker.update_progress("🐂 Active evidence researcher constructs argument")

                    time.sleep(8)
                    progress_tracker.update_progress("🐻 Cautious Evidence Researchers Identify Risks")

                    # Multi-scenario research phases - determine research rounds based on 5 levels
                    research_depth = request.parameters.research_depth if request.parameters else "标准"
                    if research_depth == "快速":
                        debate_rounds = 1
                    elif research_depth == "基础":
                        debate_rounds = 1
                    elif research_depth == "标准":
                        debate_rounds = 1
                    elif research_depth == "深度":
                        debate_rounds = 2
                    elif research_depth == "全面":
                        debate_rounds = 3
                    else:
                        debate_rounds = 1  # Default

                    for round_num in range(debate_rounds):
                        time.sleep(12)
                        progress_tracker.update_progress(f"🎯 多情景研究 第{round_num+1}轮")

                    time.sleep(8)
                    progress_tracker.update_progress("👔 研究整合员形成共识")

                    # research integrator stage
                    time.sleep(10)
                    progress_tracker.update_progress("💼 研究整合员整理简报")

                    # risk management stage
                    time.sleep(8)
                    progress_tracker.update_progress("🔥 高弹性情景风险评估")

                    time.sleep(6)
                    progress_tracker.update_progress("🛡️ 防御情景风险评估")

                    time.sleep(6)
                    progress_tracker.update_progress("⚖️ 基准情景风险评估")

                    time.sleep(8)
                    progress_tracker.update_progress("🎯 风险评估师制定策略")

                    # final stage
                    time.sleep(5)
                    progress_tracker.update_progress("📡 信号处理")

                except Exception as e:
                    logger.warning(f"⚠️ 进度模拟失败: {e}")

            # Start the progress simulation thread
            progress_thread = threading.Thread(target=simulate_progress, daemon=True)
            progress_thread.start()

            # Define a progress callback function to receive the real-time progress of LangGraph
            # Node progress mapping table (corresponding to the step weight of RedisProgressTracker)
            node_progress_map = {
                # analyst stage (10% → 45%)
                "📊 市场分析师": 27.5,      # 10% + 17.5% (Assume 2 analysts)
                "💼 基本面分析师": 45,       # 10% + 35%
                "📰 新闻分析师": 27.5,       # If there are 3 analysts
                "💬 社交媒体分析师": 27.5,   # If there are 4 analysts
                # multi-scenario research phase (45% → 70%)
                "🐂 积极证据研究员": 51.25,      # 45% + 6.25%
                "🐻 谨慎证据研究员": 57.5,       # 45% + 12.5%
                "👔 研究经理": 70,           # 45% + 25%
                # Research integration stage (70% → 78%)
                "🧩 研究整合员汇总": 78,         # 70% + 8%
                # risk scenario research phase (78% → 93%)
                "🔥 高弹性情景研究": 81.75,    # 78% + 3.75%
                "🛡️ 防御情景研究": 85.5,    # 78% + 7.5%
                "⚖️ 基准情景研究": 89.25,   # 78% + 11.25%
                "👔 风险评估师": 93,           # 78% + 15%
                # final stage (93% → 100%)
                "📊 生成报告": 97,           # 93% + 4%
            }

            def graph_progress_callback(message: str):
                """Receive progress updates from LangGraph

                Maps directly to progress percentage based on node name, ensuring consistency with the step weight of RedisProgressTracker
                Note: Only update when the progress increases to avoid overwriting the virtual step progress of RedisProgressTracker
                """
                try:
                    logger.info(f"🎯🎯🎯 [Graph progress callback is called] message={message}")
                    if not progress_tracker:
                        logger.warning(f"⚠️ progress_tracker If None, progress cannot be updated")
                        return

                    # Find the progress percentage corresponding to the node
                    progress_pct = node_progress_map.get(message)

                    if progress_pct is not None:
                        # Get the current progress (using the progress_data attribute)
                        current_progress = progress_tracker.progress_data.get('progress_percentage', 0)

                        # Only update when progress increases to avoid overwriting the progress of dummy steps
                        if int(progress_pct) > current_progress:
                            # Update Redis progress tracker
                            progress_tracker.update_progress({
                                'progress_percentage': int(progress_pct),
                                'last_message': message
                            })
                            logger.info(f"📊 [Graph Progress] Progress updated: {current_progress}% → {int(progress_pct)}% - {message}")

                            # 🔥 Simultaneously update memory and MongoDB
                            try:
                                import asyncio
                                from datetime import datetime

                                # Try to get the currently running event loop
                                try:
                                    loop = asyncio.get_running_loop()
                                    # If inside the event loop, use create_task
                                    asyncio.create_task(
                                        self._update_progress_async(task_id, int(progress_pct), message)
                                    )
                                    logger.debug(f"✅ [Graph Progress] Asynchronous update task submitted: {int(progress_pct)}%")
                                except RuntimeError:
                                    # There is no running event loop, use synchronous update MongoDB
                                    from pymongo import MongoClient
                                    from app.core.config import settings

                                    # Create a synchronous MongoDB client
                                    sync_client = MongoClient(settings.MONGO_URI)
                                    sync_db = sync_client[settings.MONGO_DB]

                                    # Synchronous updates MongoDB
                                    sync_db.analysis_tasks.update_one(
                                        {"task_id": task_id},
                                        {
                                            "$set": {
                                                "progress": int(progress_pct),
                                                "current_step": message,
                                                "message": message,
                                                "updated_at": datetime.utcnow()
                                            }
                                        }
                                    )
                                    sync_client.close()

                                    # Update memory asynchronously (create a new event loop)
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        loop.run_until_complete(
                                            self.memory_manager.update_task_status(
                                                task_id=task_id,
                                                status=TaskStatus.RUNNING,
                                                progress=int(progress_pct),
                                                message=message,
                                                current_step=message
                                            )
                                        )
                                    finally:
                                        loop.close()

                                    logger.debug(f"✅ [Graph Progress] Memory and MongoDB: {int(progress_pct)}%")
                            except Exception as sync_err:
                                logger.warning(f"⚠️ [Graph Progress] Synchronous update failed: {sync_err}")
                        else:
                            # The progress is not increased, only the message is updated
                            progress_tracker.update_progress({
                                'last_message': message
                            })
                            logger.info(f"📊 [Graph Progress] Progress unchanged({current_progress}% >= {int(progress_pct)}%), Update message only: {message}")
                    else:
                        # Unknown node, only update messages
                        logger.warning(f"⚠️ [Graph Progress] unknown node: {message}, Update message only")
                        progress_tracker.update_progress({
                            'last_message': message
                        })

                except Exception as e:
                    logger.error(f"❌ Graph Progress callback failed: {e}", exc_info=True)

            logger.info(f"🚀 Prepare to call trading_graph.propagate,progress_callback={graph_progress_callback}")

            # Perform the actual analysis, passing progress callbacks and task_id
            try:
                from tradingagents.agents.utils.agent_context import AgentContext
                ctx = AgentContext(user_id=str(user_id))
                logger.info(f"[diagnose] inject AgentContext(simple) task_id={task_id} user_id={user_id} symbol={stock_code} date={analysis_date}")
            except Exception:
                ctx = None
                logger.info(f"[diagnose] inject AgentContext(simple) failed, continue without context")

            state, decision = trading_graph.propagate(
                stock_code,  # 🔑 Fix: use stock_code variable instead request.stock_code
                analysis_date,
                progress_callback=graph_progress_callback,
                task_id=task_id,
                agent_context=(ctx.__dict__ if ctx else None)
            )

            logger.info(f"✅ trading_graph.propagate Execution completed")

            # 🔍 Debugging: Check the structure of the decision
            logger.info(f"🔍 [DEBUG] Decision Type: {type(decision)}")
            logger.info(f"🔍 [DEBUG] Decision content: {decision}")
            if isinstance(decision, dict):
                logger.info(f"🔍 [DEBUG] Decision key: {list(decision.keys())}")
            elif hasattr(decision, '__dict__'):
                logger.info(f"🔍 [DEBUG] Decision Properties: {list(vars(decision).keys())}")

            # Processing results
            if progress_tracker:
                progress_tracker.update_progress("📊 处理分析结果")
            update_progress_sync(90, "处理分析结果...", "result_processing")

            execution_time = (datetime.now() - start_time).total_seconds()

            # Extract reports field from state
            reports = {}
            try:
                # Prioritize dynamic extraction from structured_reports generated by the engine
                structured_reports = state.get('structured_reports', {}) if isinstance(state, dict) else {}
                if isinstance(structured_reports, dict) and structured_reports:
                    for field, entry in structured_reports.items():
                        if isinstance(entry, dict) and entry.get("success") and entry.get("content"):
                            content = entry["content"]
                            if isinstance(content, str) and len(content.strip()) > 10:
                                reports[field] = content.strip()
                else:
                    # Fallback: derivation from report_manifest
                    manifest = state.get('report_manifest', []) if isinstance(state, dict) else []
                    if manifest:
                        for m in manifest:
                            field = m.get("field")
                            if field:
                                value = state.get(field)
                                if isinstance(value, str) and len(value.strip()) > 10:
                                    reports[field] = value.strip()
                    if not reports:
                        # Final fallback: legacy hardcoded lists
                        report_fields = [
                            'index_report',
                            'sector_report',
                            'market_report',
                            'sentiment_report',
                            'news_report',
                            'fundamentals_report',
                            'chip_report',
                            'investment_plan',
                            'trader_investment_plan',
                            'final_trade_decision'
                        ]

                        from app.utils.report_formatter import _convert_json_to_markdown

                        for field in report_fields:
                            if hasattr(state, field):
                                value = getattr(state, field, "")
                            elif isinstance(state, dict) and field in state:
                                value = state[field]
                            else:
                                value = ""

                            if isinstance(value, str) and len(value.strip()) > 10:
                                if field in ['investment_plan', 'final_trade_decision']:
                                    if field == 'investment_plan':
                                        report_type = "investment"
                                    else:
                                        report_type = "final_decision"
                                    markdown_value = _convert_json_to_markdown(value.strip(), report_type)
                                    reports[field] = markdown_value
                            logger.info(f"📊 [REPORTS] 提取报告: {field} - 长度: {len(markdown_value)} (已转换JSON->Markdown)")
                        else:
                            reports[field] = value.strip()
                            logger.info(f"📊 [REPORTS] 提取报告: {field} - 长度: {len(value.strip())}")
                    else:
                        logger.debug(f"⚠️ [REPORTS] 跳过报告: {field} - 内容为空或太短")

                # Handle research team debate status report
                if hasattr(state, 'investment_debate_state') or (isinstance(state, dict) and 'investment_debate_state' in state):
                    debate_state = getattr(state, 'investment_debate_state', None) if hasattr(state, 'investment_debate_state') else state.get('investment_debate_state')
                    if debate_state:
                        # Extract long researcher history
                        if hasattr(debate_state, 'bull_history'):
                            bull_content = getattr(debate_state, 'bull_history', "")
                        elif isinstance(debate_state, dict) and 'bull_history' in debate_state:
                            bull_content = debate_state['bull_history']
                        else:
                            bull_content = ""

                        if bull_content and len(bull_content.strip()) > 10:
                            reports['bull_researcher'] = bull_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: bull_researcher - length: {len(bull_content.strip())}")

                        # Extract short researcher history
                        if hasattr(debate_state, 'bear_history'):
                            bear_content = getattr(debate_state, 'bear_history', "")
                        elif isinstance(debate_state, dict) and 'bear_history' in debate_state:
                            bear_content = debate_state['bear_history']
                        else:
                            bear_content = ""

                        if bear_content and len(bear_content.strip()) > 10:
                            reports['bear_researcher'] = bear_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: bear_researcher - length: {len(bear_content.strip())}")

                        # Extract Research Manager Analysis
                        if hasattr(debate_state, 'judge_decision'):
                            decision_content = getattr(debate_state, 'judge_decision', "")
                        elif isinstance(debate_state, dict) and 'judge_decision' in debate_state:
                            decision_content = debate_state['judge_decision']
                        else:
                            decision_content = str(debate_state)

                        if decision_content and len(decision_content.strip()) > 10:
                            # 🔥 New: If in JSON format, convert to Markdown
                            markdown_content = _convert_json_to_markdown(decision_content.strip(), "investment")
                            reports['research_team_decision'] = markdown_content
                            logger.info(f"📊 [REPORTS] Extract report: research_team_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

                # Handle risk management team debate status report
                if hasattr(state, 'risk_debate_state') or (isinstance(state, dict) and 'risk_debate_state' in state):
                    risk_state = getattr(state, 'risk_debate_state', None) if hasattr(state, 'risk_debate_state') else state.get('risk_debate_state')
                    if risk_state:
                        # Extract high-resilience scenario analyst history
                        if hasattr(risk_state, 'risky_history'):
                            risky_content = getattr(risk_state, 'risky_history', "")
                        elif isinstance(risk_state, dict) and 'risky_history' in risk_state:
                            risky_content = risk_state['risky_history']
                        else:
                            risky_content = ""

                        if risky_content and len(risky_content.strip()) > 10:
                            reports['risky_analyst'] = risky_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: risky_analyst - length: {len(risky_content.strip())}")

                        # Extract Defense Scenario Analyst History
                        if hasattr(risk_state, 'safe_history'):
                            safe_content = getattr(risk_state, 'safe_history', "")
                        elif isinstance(risk_state, dict) and 'safe_history' in risk_state:
                            safe_content = risk_state['safe_history']
                        else:
                            safe_content = ""

                        if safe_content and len(safe_content.strip()) > 10:
                            reports['safe_analyst'] = safe_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: safe_analyst - length: {len(safe_content.strip())}")

                        # Extract neutral analyst history
                        if hasattr(risk_state, 'neutral_history'):
                            neutral_content = getattr(risk_state, 'neutral_history', "")
                        elif isinstance(risk_state, dict) and 'neutral_history' in risk_state:
                            neutral_content = risk_state['neutral_history']
                        else:
                            neutral_content = ""

                        if neutral_content and len(neutral_content.strip()) > 10:
                            reports['neutral_analyst'] = neutral_content.strip()
                            logger.info(f"📊 [REPORTS] Extract report: neutral_analyst - length: {len(neutral_content.strip())}")

                        # Extract risk assessor decisions
                        if hasattr(risk_state, 'judge_decision'):
                            risk_decision = getattr(risk_state, 'judge_decision', "")
                        elif isinstance(risk_state, dict) and 'judge_decision' in risk_state:
                            risk_decision = risk_state['judge_decision']
                        else:
                            risk_decision = str(risk_state)

                        if risk_decision and len(risk_decision.strip()) > 10:
                            # 🔥 New: If in JSON format, convert to Markdown
                            markdown_content = _convert_json_to_markdown(risk_decision.strip(), "risk")
                            reports['risk_management_decision'] = markdown_content
                            logger.info(f"📊 [REPORTS] Extract report: risk_management_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

                logger.info(f"📊 [REPORTS] 从state中提取到 {len(reports)} 个报告: {list(reports.keys())}")

            except Exception as e:
                logger.warning(f"⚠️ Error while extracting reports: {e}")
                # Downgrade to extract from detailed_analysis
                try:
                    if isinstance(decision, dict):
                        for key, value in decision.items():
                            if isinstance(value, str) and len(value) > 50:
                                reports[key] = value
                        logger.info(f"📊 降级：从decision中提取到 {len(reports)} 个报告")
                except Exception as fallback_error:
                    logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 🔥 Format decision data (refer to the implementation of web directory)
            formatted_decision = {}
            try:
                if isinstance(decision, dict):
                    # Handle validation price (history field target_price is for compatibility only)
                    target_price = decision.get('target_price')
                    if target_price is not None and target_price != 'N/A':
                        try:
                            if isinstance(target_price, str):
                                # Remove currency symbols and spaces
                                clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').strip()
                                target_price = float(clean_price) if clean_price and clean_price != 'None' else None
                            elif isinstance(target_price, (int, float)):
                                target_price = float(target_price)
                            else:
                                target_price = None
                        except (ValueError, TypeError):
                            target_price = None
                    else:
                        target_price = None

                    # Convert English/old research conclusions into Chinese compliance terms
                    action_translation = {
                        'BUY': '乐观',
                        'SELL': '审慎',
                        'HOLD': '中性',
                        'buy': '乐观',
                        'sell': '审慎',
                        'hold': '中性',
                        '买入': '乐观',
                        '卖出': '审慎',
                        '持有': '中性',
                        '看涨': '乐观',
                        '看跌': '审慎',
                    }
                    action = decision.get('action', '中性')
                    chinese_action = action_translation.get(action, action)

                    formatted_decision = {
                        'action': chinese_action,
                        'confidence': decision.get('confidence', 0.5),
                        'risk_score': decision.get('risk_score', 0.3),
                        'target_price': target_price,
                        'reasoning': decision.get('reasoning', '暂无分析推理')
                    }

                    logger.info(f"🎯 [DEBUG] formatted decision: {formatted_decision}")
                else:
                    # Handle other types
                    formatted_decision = {
                        'action': '中性',
                        'confidence': 0.5,
                        'risk_score': 0.3,
                        'target_price': None,
                        'reasoning': '暂无分析推理'
                    }
                    logger.warning(f"⚠️ Decision Not a dictionary type: {type(decision)}")
            except Exception as e:
                logger.error(f"❌ Format decision failed: {e}")
                formatted_decision = {
                    'action': '中性',
                    'confidence': 0.5,
                    'risk_score': 0.3,
                    'target_price': None,
                    'reasoning': '暂无分析推理'
                }

            # 🔥 Generate summary and recommendation
            summary = ""
            recommendation = ""

            # 1. Prioritize extracting summary from final_trade_decision in reports (consistent with web directory)
            if isinstance(reports, dict) and 'final_trade_decision' in reports:
                final_decision_content = reports['final_trade_decision']
                if isinstance(final_decision_content, str) and len(final_decision_content) > 50:
                    # Extract the first 200 characters as a summary (exactly the same as the web directory)
                    summary = final_decision_content[:200].replace('#', '').replace('*', '').strip()
                    if len(final_decision_content) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从final_trade_decision提取摘要: {len(summary)}字符")

            # 2. If there is no final_trade_decision, extract it from state
            if not summary and isinstance(state, dict):
                final_decision = state.get('final_trade_decision', '')
                if isinstance(final_decision, str) and len(final_decision) > 50:
                    summary = final_decision[:200].replace('#', '').replace('*', '').strip()
                    if len(final_decision) > 200:
                        summary += "..."
                    logger.info(f"📝 [SUMMARY] 从state.final_trade_decision提取摘要: {len(summary)}字符")

            # 3. Generate recommendation (from reasoning of decision)
            if isinstance(formatted_decision, dict):
                action = formatted_decision.get('action', '中性')
                # 🔥 Compliance Modification: Use Compliance Terminology
                price_range = formatted_decision.get('price_analysis_range') or formatted_decision.get('target_price')
                reasoning = formatted_decision.get('reasoning', '')

                # 🔥 Compliance Modification: Generate Analytical Opinions (Excluding Specific Prices and Research Observations)
                recommendation_parts = []
                if action and action != '中性':
                    recommendation_parts.append(f"Analysis point of view:{action}")
                
                # 🔥 If reasoning is short (<100 characters) before adding it to the recommendation to avoid duplication
                if reasoning and len(reasoning) < 100 and reasoning != "暂无分析推理":
                    recommendation_parts.append(f"Analysis basis:{reasoning}")
                elif reasoning and reasoning != "暂无分析推理":
                    # If reasoning is longer, only the first 50 characters are extracted
                    short_reasoning = reasoning[:50] + "..." if len(reasoning) > 50 else reasoning
                    recommendation_parts.append(f"Analysis basis:{short_reasoning}")
                
                recommendation = "；".join(recommendation_parts) if recommendation_parts else "Please refer to the detailed analysis report."
                logger.info(f"💡 [RECOMMENDATION] 生成分析观点: {len(recommendation)}字符")

            # 4. If still not available, pull from other reports
            if not summary and isinstance(reports, dict):
                # Try extracting summaries from other reports
                for report_name, content in reports.items():
                    if isinstance(content, str) and len(content) > 100:
                        summary = content[:200].replace('#', '').replace('*', '').strip()
                        if len(content) > 200:
                            summary += "..."
                        logger.info(f"📝 [SUMMARY] 从{report_name}提取摘要: {len(summary)}字符")
                        break

            # 5. Last resort
            if not summary:
                summary = f"对{request.stock_code}的分析已完成，请查看详细报告。"
                logger.warning(f"⚠️ [SUMMARY] Use alternate summaries")

            if not recommendation or recommendation == "Analytical opinion: Neutral":
                recommendation = "Please refer to the detailed analysis report."
                logger.warning(f"⚠️ [RECOMMENDATION] Use backup suggestions")

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = {
                "analysis_id": str(uuid.uuid4()),
                "stock_code": request.stock_code,
                "stock_symbol": request.stock_code,  # Add stock_symbol field to maintain compatibility
                "analysis_date": analysis_date,
                "summary": summary,
                "recommendation": recommendation,
                "confidence_score": formatted_decision.get("confidence", 0.0) if isinstance(formatted_decision, dict) else 0.0,
                "risk_level": "中等",  # Can be calculated based on risk_score
                "key_points": [],  # Key points can be extracted from reasoning
                # ❌ Remove the following fields (not returned by default, can be obtained through query parameters)
                # "detailed_analysis": decision,  # Changed to optional and not returned by default
                # "state": state,  # Changed to optional and not returned by default
                "execution_time": execution_time,
                "tokens_used": decision.get("tokens_used", 0) if isinstance(decision, dict) else 0,
                # Add analyst information
                "analysts": request.parameters.selected_analysts if request.parameters else [],
                "research_depth": request.parameters.research_depth if request.parameters else "快速",
                # Add extracted report content
                "reports": reports,
                # 🔥 Key fix: Add formatted decision field!
                "decision": formatted_decision,
                # 🔥 Add model information fields
                "model_info": model_info,
                # 🆕 Performance index data
                "performance_metrics": state.get("performance_metrics", {}) if isinstance(state, dict) else {}
            }

            logger.info(f"✅ [线程池] 分析完成: {task_id} - 耗时{execution_time:.2f}秒")

            # 🔍 Debugging: Examine the returned result structure
            logger.info(f"🔍 [DEBUG] Returns the key of result: {list(result.keys())}")
            logger.info(f"🔍 [DEBUG] Return result contains decision: {bool(result.get('decision'))}")
            if result.get('decision'):
                decision = result['decision']
                logger.info(f"🔍 [DEBUG] Return decision content: {decision}")

            return result

        except Exception as e:
            logger.error(f"❌ [thread pool] Analysis execution failed: {task_id} - {e}")

            # Format error messages into user-friendly prompts
            from ..utils.error_formatter import ErrorFormatter

            # Gather contextual information
            error_context = {}
            if request and hasattr(request, 'parameters') and request.parameters:
                if hasattr(request.parameters, 'quick_model'):
                    error_context['model'] = request.parameters.quick_model
                if hasattr(request.parameters, 'deep_model'):
                    error_context['model'] = request.parameters.deep_model

            # Formatting error
            formatted_error = ErrorFormatter.format_error(str(e), error_context)

            # Build user-friendly error messages
            user_friendly_error = (
                f"{formatted_error['title']}\n\n"
                f"{formatted_error['message']}\n\n"
                f"💡 {formatted_error['suggestion']}"
            )

            # Throw an exception with a friendly error message
            raise Exception(user_friendly_error) from e

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        logger.info(f"🔍 查询任务状态: {task_id}")
        logger.info(f"🔍 当前服务实例ID: {id(self)}")
        logger.info(f"🔍 内存管理器实例ID: {id(self.memory_manager)}")

        # Force use of global memory manager instance (temporary solution)
        global_memory_manager = get_memory_state_manager()
        logger.info(f"🔍 Global memory manager instance ID: {id(global_memory_manager)}")

        # Get statistics
        stats = await global_memory_manager.get_statistics()
        logger.info(f"📊 内存中任务统计: {stats}")

        result = await global_memory_manager.get_task_dict(task_id)
        if result:
            logger.info(f"✅ 找到任务: {task_id} - 状态: {result.get('status')}")

            # 🔍 Debugging: Check the fetched from memory result_data
            result_data = result.get('result_data')
            logger.debug(f"🔍 [GET_STATUS] result_data exist: {bool(result_data)}")
            if result_data:
                logger.debug(f"🔍 [GET_STATUS] result_data key: {list(result_data.keys())}")
                logger.debug(f"🔍 [GET_STATUS] result_data There is decision: {bool(result_data.get('decision'))}")
                if result_data.get('decision'):
                    logger.debug(f"🔍 [GET_STATUS] decision content: {result_data['decision']}")
            else:
                logger.debug(f"🔍 [GET_STATUS] result_data Is empty or does not exist (the task is running, this is normal)")

            # Get detailed progress information from Redis first
            redis_progress = get_progress_by_id(task_id)
            if redis_progress:
                logger.info(f"📊 [Redis Progress] Get detailed progress: {task_id}")

                # Extract the name and description of the current step from the steps array
                current_step_index = redis_progress.get('current_step', 0)
                steps = redis_progress.get('steps', [])
                current_step_name = redis_progress.get('current_step_name', '')
                current_step_description = redis_progress.get('current_step_description', '')

                # If name/description in Redis is empty, extract from steps array
                if not current_step_name and steps and 0 <= current_step_index < len(steps):
                    current_step_info = steps[current_step_index]
                    current_step_name = current_step_info.get('name', '')
                    current_step_description = current_step_info.get('description', '')
                    logger.info(f"📋 Extract the current step information from the steps array: index={current_step_index}, name={current_step_name}")

                # Merge Redis progress data
                result.update({
                    'progress': redis_progress.get('progress_percentage', result.get('progress', 0)),
                    'current_step': current_step_index,  # Use index instead of name
                    'current_step_name': current_step_name,  # step name
                    'current_step_description': current_step_description,  # Step description
                    'message': redis_progress.get('last_message', result.get('message', '')),
                    'elapsed_time': redis_progress.get('elapsed_time', 0),
                    'remaining_time': redis_progress.get('remaining_time', 0),
                    'estimated_total_time': redis_progress.get('estimated_total_time', result.get('estimated_duration', 300)),  # 🔧 Fix: Use estimated total duration in Redis
                    'steps': steps,
                    'start_time': result.get('start_time'),  # Keep the original format
                    'last_update': redis_progress.get('last_update', result.get('start_time'))
                })
            else:
                # If not available in Redis, try to get it from the in-memory progress tracker
                if task_id in self._progress_trackers:
                    progress_tracker = self._progress_trackers[task_id]
                    progress_data = progress_tracker.to_dict()

                    # Details of merge progress tracker
                    result.update({
                        'progress': progress_data['progress'],
                        'current_step': progress_data['current_step'],
                        'message': progress_data['message'],
                        'elapsed_time': progress_data['elapsed_time'],
                        'remaining_time': progress_data['remaining_time'],
                        'estimated_total_time': progress_data.get('estimated_total_time', 0),
                        'steps': progress_data['steps'],
                        'start_time': progress_data['start_time'],
                        'last_update': progress_data['last_update']
                    })
                    logger.info(f"📊 Merge in-memory progress tracker data: {task_id}")
                else:
                    logger.info(f"⚠️ 未找到进度信息: {task_id}")
        else:
            logger.warning(f"❌ 未找到任务: {task_id}")

        return result

    async def list_all_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 999999,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all task lists (not limited to users)
        - Merge in-memory and MongoDB data
        - Sort by start time in descending order
        - By default, all records are returned, and paging is handled by the front end.
        """
        try:
            task_status = None
            if status:
                try:
                    status_mapping = {
                        "processing": "running",
                        "pending": "pending",
                        "completed": "completed",
                        "failed": "failed",
                        "cancelled": "cancelled"
                    }
                    mapped_status = status_mapping.get(status, status)
                    task_status = TaskStatus(mapped_status)
                except ValueError:
                    logger.warning(f"⚠️ [Tasks] Invalid status value: {status}")
                    task_status = None

            # 1) Read all tasks from memory
            logger.info(f"📋 [Tasks] Prepare to read all tasks from memory: status={status}, limit={limit}, offset={offset}")
            tasks_in_mem = await self.memory_manager.list_all_tasks(
                status=task_status,
                limit=limit * 2,
                offset=0
            )
            logger.info(f"📋 [Tasks] Memory return quantity: {len(tasks_in_mem)}")

            # 2) Read tasks from MongoDB
            db = get_mongo_db()
            collection = db["analysis_tasks"]

            query = {}
            if task_status:
                query["status"] = task_status.value

            count = await collection.count_documents(query)
            logger.info(f"📋 [Tasks] MongoDB total number of tasks: {count}")

            cursor = collection.find(query).sort("start_time", -1).limit(limit * 2)
            tasks_from_db = []
            async for doc in cursor:
                doc.pop("_id", None)
                tasks_from_db.append(doc)

            logger.info(f"📋 [Tasks] MongoDB Return quantity: {len(tasks_from_db)}")

            # 3) Merge tasks (memory first)
            task_dict = {}

            # First add the tasks in MongoDB
            for task in tasks_from_db:
                task_id = task.get("task_id")
                if task_id:
                    task_dict[task_id] = task

            # Then add an in-memory task (overwriting the task of the same name in MongoDB)
            for task in tasks_in_mem:
                task_id = task.get("task_id")
                if task_id:
                    task_dict[task_id] = task

            # Convert to list and sort by time
            merged_tasks = list(task_dict.values())
            merged_tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)

            # Pagination
            results = merged_tasks[offset:offset + limit]

            # Complete stock names for results
            results = self._enrich_stock_names(results)
            logger.info(f"📋 [Tasks] 合并后返回数量: {len(results)} (内存: {len(tasks_in_mem)}, MongoDB: {count})")
            return results
        except Exception as outer_e:
            logger.error(f"❌ list_all_tasks Outer layer anomaly: {outer_e}", exc_info=True)
            return []

    async def list_user_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 999999,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user task list
        - For processing status: read from memory first (real-time progress)
        - For completed/failed/all status: merge in-memory and MongoDB data
        - By default, all records are returned, and paging is handled by the front end.
        """
        try:
            task_status = None
            if status:
                try:
                    # What the front end passes is "processing", But TaskStatus uses "running"
                    # Need to do mapping conversion
                    status_mapping = {
                        "processing": "running",  # Front-end uses processing, memory usage running
                        "pending": "pending",
                        "completed": "completed",
                        "failed": "failed",
                        "cancelled": "cancelled"
                    }
                    mapped_status = status_mapping.get(status, status)
                    task_status = TaskStatus(mapped_status)
                except ValueError:
                    logger.warning(f"⚠️ [Tasks] Invalid status value: {status}")
                    task_status = None

            # 1) Read tasks from memory
            logger.info(f"📋 [Tasks] Prepare task to read from memory: user_id={user_id}, status={status} (mapped to {task_status}), limit={limit}, offset={offset}")
            tasks_in_mem = await self.memory_manager.list_user_tasks(
                user_id=user_id,
                status=task_status,
                limit=limit * 2,  # Read more and merge them later to remove duplicates.
                offset=0  # There are not many tasks in the memory, read them all
            )
            logger.info(f"📋 [Tasks] Memory return quantity: {len(tasks_in_mem)}")

            # 2) 🔧 For processing/running status, MongoDB data needs to be merged to get the latest progress
            # Because graph_progress_callback may directly update MongoDB, and the in-memory data may be old

            # 3) Read historical tasks from MongoDB (for merging or checking)
            logger.info(f"📋 [Tasks] Read historical tasks from MongoDB")
            mongo_tasks: List[Dict[str, Any]] = []
            count = 0
            try:
                db = get_mongo_db()

                # user_id May be a string or ObjectId, for compatibility
                uid_candidates: List[Any] = [user_id]

                # Special treatment for admin users
                if str(user_id) == 'admin':
                    # admin Users: Add fixed ObjectId and string form
                    try:
                        from bson import ObjectId
                        admin_oid_str = '507f1f77bcf86cd799439011'
                        uid_candidates.append(ObjectId(admin_oid_str))
                        uid_candidates.append(admin_oid_str)  # Compatible with string storage
                        logger.info(f"📋 [Tasks] admin user query, candidate ID: ['admin', ObjectId('{admin_oid_str}'), '{admin_oid_str}']")
                    except Exception as e:
                        logger.warning(f"⚠️ [Tasks] admin User ObjectId creation failed: {e}")
                else:
                    # Normal users: try converting to ObjectId
                    try:
                        from bson import ObjectId
                        uid_candidates.append(ObjectId(user_id))
                        logger.debug(f"📋 [Tasks] User ID has been converted to ObjectId: {user_id}")
                    except Exception as conv_err:
                        logger.warning(f"⚠️ [Tasks] User ID conversion to ObjectId failed, matching by string: {conv_err}")

                # Compatible with both user_id and user field names
                base_condition = {"$in": uid_candidates}
                or_conditions: List[Dict[str, Any]] = [
                    {"user_id": base_condition},
                    {"user": base_condition}
                ]
                query = {"$or": or_conditions}

                if task_status:
                    # Use the mapped status value (the value of the TaskStatus enumeration)
                    query["status"] = task_status.value
                    logger.info(f"📋 [Tasks] Add status filter: {task_status.value}")

                logger.info(f"📋 [Tasks] MongoDB Query conditions: {query}")
                # Read more data for merging
                cursor = db.analysis_tasks.find(query).sort("created_at", -1).limit(limit * 2)
                async for doc in cursor:
                    count += 1
                    # Compatible with user_id or user fields
                    user_field_val = doc.get("user_id", doc.get("user"))
                    # 🔧 Compatible with multiple stock code field names:symbol, stock_code, stock_symbol
                    stock_code_value = doc.get("symbol") or doc.get("stock_code") or doc.get("stock_symbol")
                    item = {
                        "task_id": doc.get("task_id"),
                        "user_id": str(user_field_val) if user_field_val is not None else None,
                        "symbol": stock_code_value,  # 🔧 Add symbol field (front-end priority)
                        "stock_code": stock_code_value,  # 🔧 Compatible fields
                        "stock_symbol": stock_code_value,  # 🔧 Compatible fields
                        "stock_name": doc.get("stock_name"),
                        "status": str(doc.get("status", "pending")),
                        "progress": int(doc.get("progress", 0) or 0),
                        "message": doc.get("message", ""),
                        "current_step": doc.get("current_step", ""),
                        "start_time": doc.get("started_at") or doc.get("created_at"),
                        "end_time": doc.get("completed_at"),
                        "parameters": doc.get("parameters", {}),
                        "execution_time": doc.get("execution_time"),
                        "tokens_used": doc.get("tokens_used"),
                        # For compatibility with the front end, the field name of memory_manager is used here.
                        "result_data": doc.get("result"),
                    }
                    # Convert time format to ISO string (add time zone information)
                    for k in ("start_time", "end_time"):
                        if item.get(k) and hasattr(item[k], "isoformat"):
                            dt = item[k]
                            # In the case of naive datetime (no time zone information), it is assumed to be UTC+8
                            if dt.tzinfo is None:
                                from datetime import timezone, timedelta
                                china_tz = timezone(timedelta(hours=8))
                                dt = dt.replace(tzinfo=china_tz)
                            item[k] = dt.isoformat()
                    mongo_tasks.append(item)

                logger.info(f"📋 [Tasks] MongoDB Return quantity: {count}")
            except Exception as mongo_e:
                logger.error(f"❌ MongoDB Failed to query task list: {mongo_e}", exc_info=True)
                # MongoDB Query failed, continue to use memory data

            # 4) Merge memory and MongoDB data to remove duplicates
            # 🔧 For processing/running status, progress data in MongoDB is preferred
            # Because graph_progress_callback directly updates MongoDB, and the in-memory data may be old
            task_dict = {}

            # First add tasks in memory
            for task in tasks_in_mem:
                task_id = task.get("task_id")
                if task_id:
                    task_dict[task_id] = task

            # Add tasks in MongoDB
            # For processing/running state, use progress data from MongoDB (updated)
            # For other states, skip if already in memory (memory first)
            for task in mongo_tasks:
                task_id = task.get("task_id")
                if not task_id:
                    continue

                # If the task already exists in memory
                if task_id in task_dict:
                    mem_task = task_dict[task_id]
                    mongo_task = task

                    # If it is processing/running state, use the progress data in MongoDB
                    if mongo_task.get("status") in ["processing", "running"]:
                        # Keep basic information in memory, but update progress-related fields
                        mem_task["progress"] = mongo_task.get("progress", mem_task.get("progress", 0))
                        mem_task["message"] = mongo_task.get("message", mem_task.get("message", ""))
                        mem_task["current_step"] = mongo_task.get("current_step", mem_task.get("current_step", ""))
                        logger.debug(f"🔄 [Tasks] Update task progress: {task_id}, progress={mem_task['progress']}%")
                else:
                    # If there is no memory, add the task in MongoDB directly.
                    task_dict[task_id] = task

            # Convert to list and sort by time
            merged_tasks = list(task_dict.values())
            merged_tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)

            # Pagination
            results = merged_tasks[offset:offset + limit]

            # 🔥 Process time zone information uniformly (ensure all time fields have time zone identifiers)
            from datetime import timezone, timedelta
            china_tz = timezone(timedelta(hours=8))

            for task in results:
                for time_field in ("start_time", "end_time", "created_at", "started_at", "completed_at"):
                    value = task.get(time_field)
                    if value:
                        # If it is a datetime object
                        if hasattr(value, "isoformat"):
                            # If it is naive datetime, add time zone information
                            if value.tzinfo is None:
                                value = value.replace(tzinfo=china_tz)
                            task[time_field] = value.isoformat()
                        # If it is a string and there is no time zone identifier, add the time zone identifier
                        elif isinstance(value, str) and value and not value.endswith(('Z', '+08:00', '+00:00')):
                            # Check if it is a time string in ISO format
                            if 'T' in value or ' ' in value:
                                task[time_field] = value.replace(' ', 'T') + '+08:00'

            # Complete stock names for results
            results = self._enrich_stock_names(results)
            logger.info(f"📋 [Tasks] 合并后返回数量: {len(results)} (内存: {len(tasks_in_mem)}, MongoDB: {count})")
            return results
        except Exception as outer_e:
            logger.error(f"❌ list_user_tasks Outer layer anomaly: {outer_e}", exc_info=True)
            return []

    async def cleanup_zombie_tasks(self, max_running_hours: int = 2) -> Dict[str, Any]:
        """Clean up zombie tasks (tasks that have been in processing/running state for a long time)

        Args:
            max_running_hours: Maximum running time (hours), tasks exceeding this time will be marked as failed

        Returns:
            Clean up result statistics
        """
        try:
            # 1) Clean up zombie tasks in memory
            memory_cleaned = await self.memory_manager.cleanup_zombie_tasks(max_running_hours)

            # 2) Cleaning up zombie tasks in MongoDB
            db = get_mongo_db()
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=max_running_hours)

            # Find tasks that have been in processing state for a long time
            zombie_filter = {
                "status": {"$in": ["processing", "running", "pending"]},
                "$or": [
                    {"started_at": {"$lt": cutoff_time}},
                    {"created_at": {"$lt": cutoff_time, "started_at": None}}
                ]
            }

            # Update to failed status
            update_result = await db.analysis_tasks.update_many(
                zombie_filter,
                {
                    "$set": {
                        "status": "failed",
                        "last_error": f"任务超时（运行时间超过 {max_running_hours} 小时）",
                        "completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            mongo_cleaned = update_result.modified_count

            logger.info(f"🧹 Zombie mission cleanup completed: memory={memory_cleaned}, MongoDB={mongo_cleaned}")

            return {
                "success": True,
                "memory_cleaned": memory_cleaned,
                "mongo_cleaned": mongo_cleaned,
                "total_cleaned": memory_cleaned + mongo_cleaned,
                "max_running_hours": max_running_hours
            }

        except Exception as e:
            logger.error(f"❌ 清理僵尸任务失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "memory_cleaned": 0,
                "mongo_cleaned": 0,
                "total_cleaned": 0
            }

    async def get_zombie_tasks(self, max_running_hours: int = 2) -> List[Dict[str, Any]]:
        """Get the list of zombie tasks (does not perform cleanup, only queries)

        Args:
            max_running_hours: Maximum run time (hours)

        Returns:
            Zombie mission list
        """
        try:
            db = get_mongo_db()
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=max_running_hours)

            # Find tasks that have been in processing state for a long time
            zombie_filter = {
                "status": {"$in": ["processing", "running", "pending"]},
                "$or": [
                    {"started_at": {"$lt": cutoff_time}},
                    {"created_at": {"$lt": cutoff_time, "started_at": None}}
                ]
            }

            cursor = db.analysis_tasks.find(zombie_filter).sort("created_at", -1)
            zombie_tasks = []

            async for doc in cursor:
                task = {
                    "task_id": doc.get("task_id"),
                    "user_id": str(doc.get("user_id", doc.get("user"))),
                    "stock_code": doc.get("stock_code"),
                    "stock_name": doc.get("stock_name"),
                    "status": doc.get("status"),
                    "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                    "started_at": doc.get("started_at").isoformat() if doc.get("started_at") else None,
                    "running_hours": None
                }

                # Calculate run time
                start_time = doc.get("started_at") or doc.get("created_at")
                if start_time:
                    running_seconds = (datetime.utcnow() - start_time).total_seconds()
                    task["running_hours"] = round(running_seconds / 3600, 2)

                zombie_tasks.append(task)

            logger.info(f"📋 查询到 {len(zombie_tasks)} 个僵尸任务")
            return zombie_tasks

        except Exception as e:
            logger.error(f"❌ 查询僵尸任务失败: {e}", exc_info=True)
            return []



    async def _update_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        progress: int,
        error_message: str = None
    ):
        """更新任务状态"""
        try:
            db = get_mongo_db()
            update_data = {
                "status": status,
                "progress": progress,
                "updated_at": datetime.utcnow()
            }

            if status == AnalysisStatus.PROCESSING and progress == 10:
                update_data["started_at"] = datetime.utcnow()
            elif status == AnalysisStatus.COMPLETED:
                update_data["completed_at"] = datetime.utcnow()
            elif status == AnalysisStatus.FAILED:
                update_data["last_error"] = error_message
                update_data["completed_at"] = datetime.utcnow()

            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )

            logger.debug(f"📊 任务状态已更新: {task_id} -> {status} ({progress}%)")

        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {task_id} - {e}")

    async def _save_analysis_result(self, task_id: str, result: Dict[str, Any]):
        """保存分析结果（原始方法）"""
        try:
            db = get_mongo_db()
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"result": result}}
            )
            logger.debug(f"💾 分析结果已保存: {task_id}")
        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {task_id} - {e}")

    async def _save_analysis_result_web_style(self, task_id: str, result: Dict[str, Any]):
        """Save analysis results - use the web directory to save to the analysis_reports collection

        Use unified report saving tool functions
        """
        try:
            from app.utils.report_saver import extract_reports_from_state, save_analysis_report
            from datetime import datetime

            db = get_mongo_db()
            stock_symbol = result.get('stock_symbol') or result.get('stock_code', 'UNKNOWN')

            # 🔥 Use unified report extraction functions
            reports = {}
            if 'state' in result:
                try:
                    state = result['state']
                    reports = extract_reports_from_state(state)
                except Exception as e:
                    logger.warning(f"⚠️ An error occurred while processing reports in state: {e}")
                    # Downgrade to extract from detailed_analysis
                    if 'detailed_analysis' in result:
                        try:
                            detailed_analysis = result['detailed_analysis']
                            if isinstance(detailed_analysis, dict):
                                for key, value in detailed_analysis.items():
                                    if isinstance(value, str) and len(value) > 50:
                                        reports[key] = value
                                logger.info(f"📊 降级：从detailed_analysis中提取到 {len(reports)} 个报告")
                        except Exception as fallback_error:
                            logger.warning(f"⚠️ 降级提取也失败: {fallback_error}")

            # 🔥 Infer market type based on stock symbol
            from tradingagents.utils.stock_utils import StockUtils
            market_info = StockUtils.get_market_info(stock_symbol)
            market_type_map = {
                "china_a": "A股",
                "hong_kong": "港股",
                "us": "美股",
                "unknown": "A股"  # Default is A shares
            }
            market_type = market_type_map.get(market_info.get("market", "unknown"), "A股")
            logger.info(f"📊 推断市场类型: {stock_symbol} -> {market_type}")

            # 🔥 Get stock name
            stock_name = stock_symbol  # Use stock symbol by default
            try:
                if market_info.get("market") == "china_a":
                    if _is_cn_etf_symbol(stock_symbol):
                        cached_name = _get_cached_security_name(stock_symbol)
                        if cached_name:
                            stock_name = cached_name
                            logger.info(f"✅ 获取ETF名称: {stock_symbol} -> {stock_name}")
                        else:
                            stock_name = f"ETF{stock_symbol}"
                    # A Stocks: Use a unified interface to obtain stock information
                    else:
                        from tradingagents.dataflows.interface import get_china_stock_info_unified
                        stock_info = get_china_stock_info_unified(stock_symbol)
                        logger.debug(f"📊 获取股票信息返回: {stock_info[:200] if stock_info else 'None'}...")

                        if stock_info and "股票名称:" in stock_info:
                            stock_name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                            logger.info(f"✅ 获取A股名称: {stock_symbol} -> {stock_name}")
                        else:
                            # Downgrade scenario: Try getting it directly from the data source manager
                            logger.warning(f"⚠️ Unable to parse stock name from unified interface: {stock_symbol}, Try a downgrade solution")
                            try:
                                from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                                info_dict = get_info_dict(stock_symbol)
                                if info_dict and info_dict.get('name'):
                                    stock_name = info_dict['name']
                                    logger.info(f"✅ The downgrade plan successfully obtained the stock name: {stock_symbol} -> {stock_name}")
                            except Exception as fallback_e:
                                logger.error(f"❌ 降级方案也失败: {fallback_e}")

                elif market_info.get("market") == "hong_kong":
                    # Hong Kong stocks: Use improved Hong Kong stocks tools
                    try:
                        from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                        stock_name = get_hk_company_name_improved(stock_symbol)
                        logger.info(f"📊 获取港股名称: {stock_symbol} -> {stock_name}")
                    except Exception:
                        clean_ticker = stock_symbol.replace('.HK', '').replace('.hk', '')
                        stock_name = f"港股{clean_ticker}"
                elif market_info.get("market") == "us":
                    # US stocks: using simple mapping
                    us_stock_names = {
                        'AAPL': '苹果公司', 'TSLA': '特斯拉', 'NVDA': '英伟达',
                        'MSFT': '微软', 'GOOGL': '谷歌', 'AMZN': '亚马逊',
                        'META': 'Meta', 'NFLX': '奈飞'
                    }
                    stock_name = us_stock_names.get(stock_symbol.upper(), f"美股{stock_symbol}")
                    logger.info(f"📊 获取美股名称: {stock_symbol} -> {stock_name}")
            except Exception as e:
                logger.warning(f"⚠️ 获取股票名称失败: {stock_symbol} - {e}")
                stock_name = stock_symbol

            # 🔥 Use unified report saving function
            analysis_id = await save_analysis_report(
                db=db,
                stock_symbol=stock_symbol,
                stock_name=stock_name,
                market_type=market_type,
                model_info=result.get("model_info", "Unknown"),
                reports=reports,
                decision=result.get("decision", {}),
                recommendation=result.get("recommendation", ""),
                confidence_score=result.get("confidence_score", 0.0),
                risk_level=result.get("risk_level", "中等"),
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                task_id=task_id,
                execution_time=result.get("execution_time", 0),
                tokens_used=result.get("tokens_used", 0),
                analysts=result.get("analysts", []),
                research_depth=str(result.get("research_depth", 1)),
                analysis_date=None,  # Use default timestamp
                source="api",
                engine="v2",
                user_id=None,
                performance_metrics=result.get("performance_metrics", {})
            )

            logger.info(f"✅ Analysis report has been saved to MongoDB analysis_reports: {analysis_id}")

            # Also update the result field in the analysis_tasks collection to maintain API compatibility.
            # 🔥 Note: The result field saved to the database here contains complete data (for debugging/auditing)
            # However, when the API returns, it will decide whether to include state and detailed_analysis
            await db.analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"result": {
                    "analysis_id": analysis_id,
                    "stock_symbol": stock_symbol,
                    "stock_code": result.get('stock_code', stock_symbol),
                    "analysis_date": result.get('analysis_date'),
                    "summary": result.get("summary", ""),
                    "recommendation": result.get("recommendation", ""),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "risk_level": result.get("risk_level", "中等"),
                    "key_points": result.get("key_points", []),
                    # 🔥 Keep detailed_analysis and state in database (for debugging/auditing)
                    # However, when the API returns, it will be decided based on the query parameters whether to include
                    "detailed_analysis": result.get("detailed_analysis", {}),
                    "state": result.get("state", {}),
                    "execution_time": result.get("execution_time", 0),
                    "tokens_used": result.get("tokens_used", 0),
                    "reports": reports,  # Contains extracted report content (cleaned of duplicate data)
                    # 🔥 Key fix: Add formatted decision field!
                    "decision": result.get("decision", {})
                }}}
            )
            logger.info(f"💾 Analysis results saved (web style): {task_id}")

        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {task_id} - {e}")
            # Downgrade to simple save
            try:
                simple_result = {
                    'task_id': task_id,
                    'success': result.get('success', True),
                    'error': str(e),
                    'completed_at': datetime.utcnow().isoformat()
                }
                await db.analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {"result": simple_result}}
                )
                logger.info(f"💾 使用简化结果保存: {task_id}")
            except Exception as fallback_error:
                logger.error(f"❌ 简化保存也失败: {task_id} - {fallback_error}")

    async def _save_analysis_results_complete(self, task_id: str, result: Dict[str, Any]):
        """Complete analysis result storage - completely adopts the dual saving method of web directory"""
        try:
            # Debugging: print all keys in result
            logger.info(f"🔍 [Debugging] result all keys in: {list(result.keys())}")
            logger.info(f"🔍 [Debugging] stock_code: {result.get('stock_code', 'NOT_FOUND')}")
            logger.info(f"🔍 [Debugging] stock_symbol: {result.get('stock_symbol', 'NOT_FOUND')}")

            # Prefer stock_symbol, if not available then use stock_code
            stock_symbol = result.get('stock_symbol') or result.get('stock_code', 'UNKNOWN')
            logger.info(f"💾 Start saving analysis results completely: {stock_symbol}")

            # 1. Save sub-module reports to local directory
            logger.info(f"📁 [Save locally] Start saving sub-module reports to the local directory")
            local_files = await self._save_modular_reports_to_data_dir(result, stock_symbol)
            if local_files:
                logger.info(f"✅ [本地保存] 已保存 {len(local_files)} 个本地报告文件")
                for module, path in local_files.items():
                    logger.info(f"  - {module}: {path}")
            else:
                logger.warning(f"⚠️ [Save locally] Failed to save local report file")

            # 2. Save analysis report to database
            logger.info(f"🗄️ [Database save] Start saving the analysis report to the database")
            await self._save_analysis_result_web_style(task_id, result)
            logger.info(f"✅ [Database save] The analysis report has been successfully saved to the database")

            # 3. Record saving results
            if local_files:
                logger.info(f"✅ Analysis reports are saved to database and local files")
            else:
                logger.warning(f"⚠️ The database was saved successfully, but the local file failed.")

        except Exception as save_error:
            logger.error(f"❌ [save completely] An error occurred while saving the analysis report: {str(save_error)}")
            # Downgrade to database only save
            try:
                await self._save_analysis_result_web_style(task_id, result)
                logger.info(f"💾 Downgrade saved successfully (Database only): {task_id}")
            except Exception as fallback_error:
                logger.error(f"❌ 降级保存也失败: {task_id} - {fallback_error}")

    async def _save_modular_reports_to_data_dir(self, result: Dict[str, Any], stock_symbol: str) -> Dict[str, str]:
        """Save sub-module reports to the data directory - completely using the file structure of the web directory"""
        try:
            import os
            from pathlib import Path
            from datetime import datetime
            import json

            # Get the project root directory
            project_root = Path(__file__).parent.parent.parent

            # Determine the results directory path - consistent with the web directory
            results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR")
            if results_dir_env:
                if not os.path.isabs(results_dir_env):
                    results_dir = project_root / results_dir_env
                else:
                    results_dir = Path(results_dir_env)
            else:
                # By default, the data directory is used instead of the results directory.
                results_dir = project_root / "data" / "analysis_results"

            # Create a stock-specific directory - exactly according to the structure of a web directory
            analysis_date_raw = result.get('analysis_date', datetime.now())

            # Make sure analysis_date is in string format
            if isinstance(analysis_date_raw, datetime):
                analysis_date_str = analysis_date_raw.strftime('%Y-%m-%d')
            elif isinstance(analysis_date_raw, str):
                # If already a string, check the format
                try:
                    # Try parsing the date string, making sure it is in the correct format
                    parsed_date = datetime.strptime(analysis_date_raw, '%Y-%m-%d')
                    analysis_date_str = analysis_date_raw
                except ValueError:
                    # If the format is incorrect, use the current date
                    analysis_date_str = datetime.now().strftime('%Y-%m-%d')
            else:
                # Other types, use the current date
                analysis_date_str = datetime.now().strftime('%Y-%m-%d')

            stock_dir = results_dir / stock_symbol / analysis_date_str
            reports_dir = stock_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            # Create message_tool.log file - consistent with the web directory
            log_file = stock_dir / "message_tool.log"
            log_file.touch(exist_ok=True)

            logger.info(f"📁 创建分析结果目录: {reports_dir}")
            logger.info(f"🔍 [调试] analysis_date_raw 类型: {type(analysis_date_raw)}, 值: {analysis_date_raw}")
            logger.info(f"🔍 [Debugging] analysis_date_str: {analysis_date_str}")
            logger.info(f"🔍 [调试] 完整路径: {os.path.normpath(str(reports_dir))}")

            state = result.get('state', {})
            saved_files = {}

            # Define reporting module mapping - exactly as defined by the web directory
            report_modules = {
                # 🆕 Macro analysis report (save first)
                'index_report': {
                    'filename': 'index_report.md',
                    'title': f'{stock_symbol} 大盘指数分析报告',
                    'state_key': 'index_report'
                },
                'sector_report': {
                    'filename': 'sector_report.md',
                    'title': f'{stock_symbol} 行业板块分析报告',
                    'state_key': 'sector_report'
                },
                # individual stock analysis report
                'market_report': {
                    'filename': 'market_report.md',
                    'title': f'{stock_symbol} 股票技术分析报告',
                    'state_key': 'market_report'
                },
                'sentiment_report': {
                    'filename': 'sentiment_report.md',
                    'title': f'{stock_symbol} 市场情绪分析报告',
                    'state_key': 'sentiment_report'
                },
                'news_report': {
                    'filename': 'news_report.md',
                    'title': f'{stock_symbol} 新闻事件分析报告',
                    'state_key': 'news_report'
                },
                'fundamentals_report': {
                    'filename': 'fundamentals_report.md',
                    'title': f'{stock_symbol} 基本面分析报告',
                    'state_key': 'fundamentals_report'
                },
                'investment_plan': {
                    'filename': 'investment_plan.md',
                    'title': f'{stock_symbol} 投资决策报告',
                    'state_key': 'investment_plan'
                },
                'trader_investment_plan': {
                    'filename': 'trader_investment_plan.md',
                    'title': f'{stock_symbol} 交易计划报告',
                    'state_key': 'trader_investment_plan'
                },
                'final_trade_decision': {
                    'filename': 'final_trade_decision.md',
                    'title': f'{stock_symbol} 最终分析结果',
                    'state_key': 'final_trade_decision'
                },
                'investment_debate_state': {
                    'filename': 'research_team_decision.md',
                    'title': f'{stock_symbol} 研究团队分析报告',
                    'state_key': 'investment_debate_state'
                },
                'risk_debate_state': {
                    'filename': 'risk_management_decision.md',
                    'title': f'{stock_symbol} 风险管理团队决策报告',
                    'state_key': 'risk_debate_state'
                }
            }

            # Save reports for each module - exactly as in the web directory
            for module_key, module_info in report_modules.items():
                try:
                    state_key = module_info['state_key']
                    if state_key in state:
                        # Extract module content
                        module_content = state[state_key]
                        if isinstance(module_content, str):
                            report_content = module_content
                        else:
                            report_content = str(module_content)

                        # Save to file - use the file name of the web directory
                        file_path = reports_dir / module_info['filename']
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(report_content)

                        saved_files[module_key] = str(file_path)
                        logger.info(f"✅ 保存模块报告: {file_path}")

                except Exception as e:
                    logger.warning(f"⚠️ 保存模块 {module_key} 失败: {e}")

            # Save the final research conclusion report - exactly as a web directory
            decision = result.get('decision', {})
            if decision:
                decision_content = f"# {stock_symbol} 最终研究结论\n\n"

                if isinstance(decision, dict):
                    decision_content += f"## 市场分析\n\n"
                    decision_content += f"**分析观点**: {decision.get('action', 'N/A')}\n\n"
                    decision_content += f"**置信度**: {decision.get('confidence', 0):.1%}\n\n"
                    decision_content += f"**风险评分**: {decision.get('risk_score', 0):.1%}\n\n"
                    decision_content += f"**关键验证价位**: {decision.get('target_price', 'N/A')}\n\n"
                    decision_content += f"## 分析推理\n\n{decision.get('reasoning', '暂无分析推理')}\n\n"
                else:
                    decision_content += f"{str(decision)}\n\n"

                decision_file = reports_dir / "final_trade_decision.md"
                with open(decision_file, 'w', encoding='utf-8') as f:
                    f.write(decision_content)

                saved_files['final_trade_decision'] = str(decision_file)
                logger.info(f"✅ 保存最终研究结论: {decision_file}")

            # Save analysis metadata files - exactly like a web directory
            metadata = {
                'stock_symbol': stock_symbol,
                'analysis_date': analysis_date_str,
                'timestamp': datetime.now().isoformat(),
                'research_depth': result.get('research_depth', 1),
                'analysts': result.get('analysts', []),
                'status': 'completed',
                'reports_count': len(saved_files),
                'report_types': list(saved_files.keys())
            }

            metadata_file = reports_dir.parent / "analysis_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 保存分析元数据: {metadata_file}")
            logger.info(f"✅ 分模块报告保存完成，共保存 {len(saved_files)} 个文件")
            logger.info(f"📁 保存目录: {os.path.normpath(str(reports_dir))}")

            return saved_files

        except Exception as e:
            logger.error(f"❌ 保存分模块报告失败: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            return {}

# Duplicate get_task_status method removed, use in-memory version on line 469


# Global service instance
_analysis_service = None

def get_simple_analysis_service() -> SimpleAnalysisService:
    """获取分析服务实例"""
    global _analysis_service
    if _analysis_service is None:
        logger.info("🔧 [Singleton] Create a new SimpleAnalysisService instance")
        _analysis_service = SimpleAnalysisService()
    else:
        logger.info(f"🔧 [Singleton] Returns an existing SimpleAnalysisService instance: {id(_analysis_service)}")
    return _analysis_service
