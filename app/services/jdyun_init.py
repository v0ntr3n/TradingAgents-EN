"""
JD Cloud Cooperation Edition - Automatic database initialization

When starting for the first time, read the configuration from the environment variables and write it to the database:
- llm_providers: JD Cloud Provider
- system_configs: 4 model configuration + Default model + Tushare data source + Embedding Configuration
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# JD Cloud initialization tag collection (used to avoid repeated initialization)
_JDYUN_INIT_MARKER = "jdyun_init_marker"


def _get_sync_db():
    """Get a synchronous MongoDB connection"""
    try:
        from app.core.database import get_mongo_db_sync
        return get_mongo_db_sync()
    except Exception as e:
        logger.error(f"❌ [JD Cloud initialization] Failed to obtain sync database connection: {e}")
        return None


def _is_jdyun_initialized(db) -> bool:
    """Check whether JD Cloud configuration has been initialized"""
    try:
        marker = db[_JDYUN_INIT_MARKER].find_one({"_id": "jdyun"})
        return marker is not None
    except Exception:
        return False


def _mark_jdyun_initialized(db):
    """标记京东云配置已初始化"""
    db[_JDYUN_INIT_MARKER].update_one(
        {"_id": "jdyun"},
        {"$set": {"initialized_at": datetime.utcnow(), "version": 1}},
        upsert=True,
    )


def _init_jdyun_provider(db, api_base: str, api_key: str, embedding_model: str):
    """Initialize JD Cloud Provider to llm_providers collection"""
    providers_collection = db.llm_providers

    # Check if it already exists
    existing = providers_collection.find_one({"name": "jdyun"})
    if existing:
        # Update existing records
        providers_collection.update_one(
            {"name": "jdyun"},
            {"$set": {
                "display_name": "京东云",
                "description": "JD Cloud Model Service (OpenAI compatible interface)",
                "website": "https://www.jdcloud.com",
                "api_doc_url": "https://docs.jdcloud.com",
                "default_base_url": api_base,
                "api_key": api_key,
                "is_active": True,
                "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"],
                "embedding_model": embedding_model,
                "updated_at": datetime.utcnow(),
            }},
        )
        logger.info("  ✓ Update JD Cloud Provider configuration")
    else:
        # Insert new record
        providers_collection.insert_one({
            "name": "jdyun",
            "display_name": "京东云",
            "description": "JD Cloud Model Service (OpenAI compatible interface)",
            "website": "https://www.jdcloud.com",
            "api_doc_url": "https://docs.jdcloud.com",
            "default_base_url": api_base,
            "api_key": api_key,
            "is_active": True,
            "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"],
            "embedding_model": embedding_model,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        logger.info("  ✓ Create JD Cloud Provider configuration")


def _build_jdyun_llm_configs(chat_models: List[str]) -> List[Dict[str, Any]]:
    """Build LLM configurations for 4 JD Cloud models"""
    configs = []
    for i, model_name in enumerate(chat_models):
        configs.append({
            "config_id": f"jdyun_{model_name.lower().replace('-', '_').replace('.', '_')}",
            "provider": "jdyun",
            "model_name": model_name,
            "model_display_name": model_name,
            "api_key": None,  # Use the factory configured API Key
            "api_base": None,  # Use the factory configured default_base_url
            "max_tokens": 8000,
            "temperature": 0.2,
            "timeout": 180,
            "retry_times": 3,
            "enabled": True,
            "description": f"京东云 {model_name} 模型",
            "capability_level": 3,
            "suitable_roles": ["both"],
            "features": ["tool_calling", "function_calling"],
            "recommended_depths": ["快速", "基础", "标准", "深度"],
            "priority": 10 - i,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
    return configs


def _init_system_config(db, chat_models: List[str], default_model: str, embedding_model: str, tushare_token: str):
    """Initialize system configuration to system_configs collection"""
    from app.core.jdyun import JDYUN_EMBEDDING_DIMS

    configs_collection = db.system_configs

    # Build LLM configuration list
    llm_configs = _build_jdyun_llm_configs(chat_models)

    # Build system settings
    system_settings = {
        "quick_analysis_model": default_model,
        "deep_analysis_model": default_model,
        "default_embedding_model": f"jdyun:{embedding_model}",
        "default_embedding_dims": JDYUN_EMBEDDING_DIMS,
    }

    # Build Tushare data source configuration
    data_source_configs = [{
        "name": "tushare",
        "type": "tushare",
        "api_key": tushare_token,
        "enabled": True,
        "priority": 100,
        "timeout": 30,
        "rate_limit": 100,
        "description": "Tushare A Stock data source (unified by JD Cloud)",
        "config_params": {},
        "market_categories": ["china"],
        "display_name": "Tushare",
        "provider": "tushare",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }]

    # Check if there is already an active configuration
    existing_config = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

    if existing_config:
        # Update existing configuration
        configs_collection.update_one(
            {"_id": existing_config["_id"]},
            {"$set": {
                "llm_configs": llm_configs,
                "system_settings": system_settings,
                "data_source_configs": data_source_configs,
                "updated_at": datetime.utcnow(),
            }},
        )
        logger.info(f"  ✓ 更新系统配置: {len(llm_configs)} 个模型, 默认模型={default_model}")
    else:
        # Create new configuration
        configs_collection.insert_one({
            "config_name": "jdyun_default",
            "config_type": "system",
            "llm_configs": llm_configs,
            "default_llm": default_model,
            "data_source_configs": data_source_configs,
            "database_configs": [],
            "system_settings": system_settings,
            "version": 1,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        logger.info(f"  ✓ 创建系统配置: {len(llm_configs)} 个模型, 默认模型={default_model}")


def init_jdyun_config():
    """
    Synchronize database configuration from environment variables when JD Cloud Edition starts

    Synchronization is performed on every startup (idempotent operation):
    - Update jdyun Provider in llm_providers (base_url/api_key/embedding_model)
    - Update model list in system_configs (parsed from OPENAI_MODEL comma separated) and default model
    - In this way, when changing the model, you only need to modify the OPENAI_MODEL environment variable, and it will take effect after restarting. There is no need to manually change the database.
    """
    from app.core.jdyun import (
        is_jdyun_mode, get_jdyun_api_base, get_jdyun_api_key,
        get_jdyun_default_model, get_jdyun_embedding_model,
        get_jdyun_tushare_token, get_jdyun_chat_models,
    )

    if not is_jdyun_mode():
        return False

    logger.info("🔧 [JD Cloud initialization] Start synchronizing database configuration from environment variables...")

    db = _get_sync_db()
    if db is None:
        logger.error("❌ [JD Cloud initialization] Unable to obtain database connection, skipping initialization")
        return False

    # Read environment variables
    api_base = get_jdyun_api_base()
    api_key = get_jdyun_api_key()
    default_model = get_jdyun_default_model()
    embedding_model = get_jdyun_embedding_model()
    tushare_token = get_jdyun_tushare_token()
    chat_models = get_jdyun_chat_models()

    if not api_base or not api_key:
        logger.error("❌ [JD Cloud initialization] OPENAI_API_BASE or OPENAI_API_KEY not set, skip initialization")
        return False

    if not tushare_token:
        logger.warning("⚠️ [JD Cloud initialization] TUSHARE_TOKEN If not set, data source functionality may not be available")

    try:
        # 1. Synchronization Provider (idempotent updates)
        _init_jdyun_provider(db, api_base, api_key, embedding_model)

        # 2. Synchronize system configuration (model list + Default model + data source)
        _init_system_config(db, chat_models, default_model, embedding_model, tushare_token)

        # 3. Tag is initialized
        _mark_jdyun_initialized(db)

        logger.info("✅ [JD Cloud initialization] Database configuration synchronization completed")
        logger.info(f"  - Provider: jdyun ({api_base})")
        logger.info(f"  - 模型: {', '.join(chat_models)}")
        logger.info(f"  - 默认模型: {default_model}")
        logger.info(f"  - Embedding: {embedding_model}")
        logger.info(f"  - Tushare: {'configured' if tushare_token else 'Not configured'}")
        return True

    except Exception as e:
        logger.error(f"❌ [JD Cloud initialization] Sync failed: {e}", exc_info=True)
        return False
