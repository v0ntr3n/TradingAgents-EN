from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['config_provider', 'config_service', 'model_capability_service', 'prompt_assembly_service', 'prompt_injection_policy_service', 'system_prompt_seed_service', 'etf_workflow_prompt_template_service', 'report_template_service', 'schema_bundle_service']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === config_provider.py ===

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import os


class ConfigProvider:
    """Effective configuration provider with simple env→DB merge and TTL cache.

    - Priority: ENV > DB
    - Cache TTL: configurable (default 60s)
    - Invalidate on writes: caller should invoke `invalidate()` after writes
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._cache_settings: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None

    def invalidate(self) -> None:
        self._cache_settings = None
        self._cache_time = None

    def _is_cache_valid(self) -> bool:
        return (
            self._cache_settings is not None
            and self._cache_time is not None
            and __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - self._cache_time < self._ttl
        )

    async def get_effective_system_settings(self) -> Dict[str, Any]:
        if self._is_cache_valid():
            return dict(self._cache_settings or {})

        # Load DB settings
        cfg = await config_service.get_system_config()
        base: Dict[str, Any] = {}
        if cfg and getattr(cfg, "system_settings", None):
            try:
                base = dict(cfg.system_settings)
            except Exception:
                base = {}

        # Merge ENV over DB (best-effort heuristics):
        # - if ENV with exact key exists -> override
        # - try uppercased and dot/space to underscore variants
        merged: Dict[str, Any] = dict(base)
        for k, v in list(base.items()):
            candidates = [
                k,
                k.upper(),
                str(k).replace(".", "_").replace(" ", "_").upper(),
            ]
            found = None
            for ek in candidates:
                if ek in os.environ:
                    found = os.environ.get(ek)
                    break
            if found is not None:
                merged[k] = found

        # Optionally: allow whitelisting additional env-only keys via prefix
        # For now, keep minimal behavior to avoid surprising surfaces.

        # Cache
        self._cache_settings = dict(merged)
        self._cache_time = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        return dict(merged)
    async def get_system_settings_meta(self) -> Dict[str, Dict[str, Any]]:
        """Return metadata for system settings keys including sensitivity, editability and source.
        Fields per key:
          - sensitive: bool (by keyword patterns)
          - editable: bool (False if sensitive or source is environment; True otherwise)
          - source: 'environment' | 'database' | 'default'
          - has_value: bool (effective value is not None/empty)
        """
        # Load DB settings raw
        cfg = await config_service.get_system_config()
        db_settings: Dict[str, Any] = {}
        if cfg and getattr(cfg, "system_settings", None):
            try:
                db_settings = dict(cfg.system_settings)
            except Exception:
                db_settings = {}

        def _env_override_for_key(key: str) -> Optional[Any]:
            candidates = [
                key,
                key.upper(),
                str(key).replace(".", "_").replace(" ", "_").upper(),
            ]
            for ek in candidates:
                if ek in os.environ:
                    return os.environ.get(ek)
            return None

        sens_patterns = ("key", "secret", "password", "token", "client_secret")
        # 🔧 Agent configuration allows editing in the web interface (even from environment variables)
        proxy_keys = ("http_proxy", "https_proxy", "no_proxy", "proxy_enabled")

        meta: Dict[str, Dict[str, Any]] = {}
        for k, v in db_settings.items():
            env_v = _env_override_for_key(k)
            source = "environment" if env_v is not None else ("database" if v is not None else "default")
            sensitive = isinstance(k, str) and any(p in k.lower() for p in sens_patterns)

            # 🔧 Agent configuration special handling: allow editing (even from environment variables)
            if k in proxy_keys:
                editable = True  # Agent configuration is always editable
            else:
                editable = not sensitive and source != "environment"

            effective_val = env_v if env_v is not None else v
            has_value = effective_val not in (None, "")
            meta[k] = {
                "sensitive": bool(sensitive),
                "editable": bool(editable),
                "source": source,
                "has_value": bool(has_value),
            }
        return meta



# Module-level singleton
provider = ConfigProvider(ttl_seconds=60)


# === config_service.py ===
"""
配置管理服务
"""

import os
import time
import asyncio
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.utils.timezone import now_tz
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_mongo_db
from app.core.unified_config import unified_config
from app.models.config import (
    SystemConfig, LLMConfig, DataSourceConfig, DatabaseConfig,
    ModelProvider, DataSourceType, DatabaseType, LLMProvider,
    MarketCategory, DataSourceGrouping, ModelCatalog, ModelInfo
)

logger = logging.getLogger(__name__)


class ConfigService:
    """配置管理服务类"""

    def __init__(self, db_manager=None):
        self.db = None
        self.db_manager = db_manager

    async def _get_db(self):
        """获取数据库连接"""
        if self.db is None:
            if self.db_manager and self.db_manager.mongo_db is not None:
                # If there is a DatabaseManager instance, use it directly
                self.db = self.db_manager.mongo_db
            else:
                # Otherwise use global function
                self.db = get_mongo_db()
        return self.db

    @staticmethod
    def _read_llm_config_field(llm_config: Any, field_name: str) -> Any:
        if isinstance(llm_config, dict):
            return llm_config.get(field_name)
        return getattr(llm_config, field_name, None)

    @staticmethod
    def _write_llm_config_field(llm_config: Any, field_name: str, value: Any) -> None:
        if isinstance(llm_config, dict):
            llm_config[field_name] = value
            return
        setattr(llm_config, field_name, value)

    def _build_deterministic_llm_config_id(self, llm_config: Any, index: int) -> str:
        provider = str(self._read_llm_config_field(llm_config, "provider") or "").strip().lower()
        model_name = str(self._read_llm_config_field(llm_config, "model_name") or "").strip()
        api_base = str(self._read_llm_config_field(llm_config, "api_base") or "").strip()
        description = str(self._read_llm_config_field(llm_config, "description") or "").strip()
        seed = f"tradingagents-llm-config|{provider}|{model_name}|{api_base}|{description}|{index}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

    def _ensure_llm_config_ids(self, llm_configs: List[Any]) -> bool:
        changed = False
        seen_ids = set()

        for index, llm_config in enumerate(llm_configs):
            raw_config_id = self._read_llm_config_field(llm_config, "config_id")
            config_id = str(raw_config_id or "").strip()

            if not config_id or config_id in seen_ids:
                candidate = self._build_deterministic_llm_config_id(llm_config, index)
                suffix = 1
                while candidate in seen_ids:
                    suffix += 1
                    candidate = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{candidate}|{suffix}"))
                self._write_llm_config_field(llm_config, "config_id", candidate)
                config_id = candidate
                changed = True

            seen_ids.add(config_id)

        return changed

    def _select_llm_config(
        self,
        llm_configs: List[Any],
        *,
        config_id: Optional[str] = None,
        model_name: Optional[str] = None,
        preferred_provider: Optional[str] = None,
    ) -> Optional[Any]:
        normalized_config_id = str(config_id or "").strip()
        normalized_model_name = str(model_name or "").strip()
        normalized_provider = str(preferred_provider or "").strip().lower()

        if normalized_config_id:
            for llm_config in llm_configs:
                existing_config_id = str(self._read_llm_config_field(llm_config, "config_id") or "").strip()
                if existing_config_id == normalized_config_id:
                    return llm_config

        if not normalized_model_name:
            return None

        candidates = [
            llm_config
            for llm_config in llm_configs
            if str(self._read_llm_config_field(llm_config, "model_name") or "").strip() == normalized_model_name
        ]
        if not candidates:
            return None

        if normalized_provider:
            for llm_config in candidates:
                provider = str(self._read_llm_config_field(llm_config, "provider") or "").strip().lower()
                if provider == normalized_provider:
                    return llm_config

        return candidates[0]

    def _normalize_default_model_settings(
        self,
        settings: Dict[str, Any],
        existing_settings: Dict[str, Any],
        llm_configs: List[Any],
    ) -> Dict[str, Any]:
        normalized_settings = dict(settings)
        preferred_provider = str(
            normalized_settings.get("default_provider")
            or existing_settings.get("default_provider")
            or ""
        ).strip().lower()
        field_pairs = [
            ("quick_analysis_model", "quick_analysis_model_config_id"),
            ("deep_analysis_model", "deep_analysis_model_config_id"),
            ("deep_reasoning_model", "deep_reasoning_model_config_id"),
            ("coding_model", "coding_model_config_id"),
        ]

        for model_key, config_id_key in field_pairs:
            raw_config_id = normalized_settings.get(config_id_key)
            raw_model_name = normalized_settings.get(model_key)
            config_id_present = config_id_key in normalized_settings
            model_name_present = model_key in normalized_settings
            config_id = str(raw_config_id or "").strip()
            model_name = str(raw_model_name or "").strip()

            if config_id_present and not config_id:
                normalized_settings[config_id_key] = ""
                normalized_settings[model_key] = ""
                continue

            if model_name_present and not model_name and not config_id:
                normalized_settings[config_id_key] = ""
                normalized_settings[model_key] = ""
                continue

            if not config_id_present and not model_name_present:
                continue

            matched_config = self._select_llm_config(
                llm_configs,
                config_id=config_id,
                model_name=model_name,
                preferred_provider=preferred_provider,
            )
            if matched_config is None:
                if config_id_present:
                    normalized_settings[config_id_key] = ""
                if model_name_present:
                    normalized_settings[model_key] = ""
                continue

            normalized_settings[config_id_key] = str(self._read_llm_config_field(matched_config, "config_id") or "")
            normalized_settings[model_key] = str(self._read_llm_config_field(matched_config, "model_name") or "")

        return normalized_settings

    # ==================== Market classification management ====================

    async def get_market_categories(self) -> List[MarketCategory]:
        """获取所有市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories

            categories_data = await categories_collection.find({}).to_list(length=None)
            categories = [MarketCategory(**data) for data in categories_data]

            # If there is no category, create a default category
            if not categories:
                categories = await self._create_default_market_categories()

            # Sort by sort order
            categories.sort(key=lambda x: x.sort_order)
            return categories
        except Exception as e:
            print(f"❌ 获取市场分类失败: {e}")
            return []

    async def _create_default_market_categories(self) -> List[MarketCategory]:
        """创建默认市场分类"""
        default_categories = [
            MarketCategory(
                id="a_shares",
                name="a_shares",
                display_name="A股",
                description="中国A股市场数据源",
                enabled=True,
                sort_order=1
            ),
            MarketCategory(
                id="us_stocks",
                name="us_stocks",
                display_name="美股",
                description="美国股票市场数据源",
                enabled=True,
                sort_order=2
            ),
            MarketCategory(
                id="hk_stocks",
                name="hk_stocks",
                display_name="港股",
                description="香港股票市场数据源",
                enabled=True,
                sort_order=3
            ),
            MarketCategory(
                id="crypto",
                name="crypto",
                display_name="数字货币",
                description="数字货币市场数据源",
                enabled=True,
                sort_order=4
            ),
            MarketCategory(
                id="futures",
                name="futures",
                display_name="期货",
                description="期货市场数据源",
                enabled=True,
                sort_order=5
            )
        ]

        # Save to database
        db = await self._get_db()
        categories_collection = db.market_categories

        for category in default_categories:
            await categories_collection.insert_one(category.model_dump())

        return default_categories

    async def add_market_category(self, category: MarketCategory) -> bool:
        """添加市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories

            # Check if the ID already exists
            existing = await categories_collection.find_one({"id": category.id})
            if existing:
                return False

            await categories_collection.insert_one(category.model_dump())
            return True
        except Exception as e:
            print(f"❌ 添加市场分类失败: {e}")
            return False

    async def update_market_category(self, category_id: str, updates: Dict[str, Any]) -> bool:
        """更新市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories

            updates["updated_at"] = now_tz()
            result = await categories_collection.update_one(
                {"id": category_id},
                {"$set": updates}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ 更新市场分类失败: {e}")
            return False

    async def delete_market_category(self, category_id: str) -> bool:
        """删除市场分类"""
        try:
            db = await self._get_db()
            categories_collection = db.market_categories
            groupings_collection = db.datasource_groupings

            # Check if any data sources use this classification
            groupings_count = await groupings_collection.count_documents(
                {"market_category_id": category_id}
            )
            if groupings_count > 0:
                return False

            result = await categories_collection.delete_one({"id": category_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ 删除市场分类失败: {e}")
            return False

    # ==================== Data source group management ====================

    async def get_datasource_groupings(self) -> List[DataSourceGrouping]:
        """获取所有数据源分组关系"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            groupings_data = await groupings_collection.find({}).to_list(length=None)
            return [DataSourceGrouping(**data) for data in groupings_data]
        except Exception as e:
            print(f"❌ Failed to obtain data source grouping relationship: {e}")
            return []

    async def add_datasource_to_category(self, grouping: DataSourceGrouping) -> bool:
        """将数据源添加到分类"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            # Check if it already exists
            existing = await groupings_collection.find_one({
                "data_source_name": grouping.data_source_name,
                "market_category_id": grouping.market_category_id
            })
            if existing:
                return False

            await groupings_collection.insert_one(grouping.model_dump())
            return True
        except Exception as e:
            print(f"❌ Failed to add data source to classification: {e}")
            return False

    async def remove_datasource_from_category(self, data_source_name: str, category_id: str) -> bool:
        """从分类中移除数据源"""
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings

            result = await groupings_collection.delete_one({
                "data_source_name": data_source_name,
                "market_category_id": category_id
            })
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ Removing data source from classification failed: {e}")
            return False

    async def update_datasource_grouping(self, data_source_name: str, category_id: str, updates: Dict[str, Any]) -> bool:
        """Update data source grouping relationship

        🔥 Important: Update both datasource_groupings and system_configs collections at the same time
        - datasource_groupings: Used for front-end display and management
        - system_configs.data_source_configs: Used for priority judgment when obtaining actual data
        """
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings
            config_collection = db.system_configs

            # 1. Update the datasource_groupings collection
            updates["updated_at"] = now_tz()
            result = await groupings_collection.update_one(
                {
                    "data_source_name": data_source_name,
                    "market_category_id": category_id
                },
                {"$set": updates}
            )

            # 2. 🔥 If the priority is updated, update the system_configs collection synchronously
            if "priority" in updates and result.modified_count > 0:
                # Get the currently active configuration
                config_data = await config_collection.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )

                if config_data:
                    data_source_configs = config_data.get("data_source_configs", [])

                    # Find and update the corresponding data source configuration
                    # Note: data_source_name may be "AKShare", And the name in config is also "AKShare"
                    # But the type field is lowercase "akshare"
                    updated = False
                    for ds_config in data_source_configs:
                        # Try to match the name field (which takes precedence) or the type field
                        if (ds_config.get("name") == data_source_name or
                            ds_config.get("type") == data_source_name.lower()):
                            ds_config["priority"] = updates["priority"]
                            updated = True
                            logger.info(f"✅ [优先级同步] 更新 system_configs 中的数据源: {data_source_name}, 新优先级: {updates['priority']}")
                            break

                    if updated:
                        # Update configuration version
                        version = config_data.get("version", 0)
                        await config_collection.update_one(
                            {"_id": config_data["_id"]},
                            {
                                "$set": {
                                    "data_source_configs": data_source_configs,
                                    "version": version + 1,
                                    "updated_at": now_tz()
                                }
                            }
                        )
                        logger.info(f"✅ [Priority synchronization] system_configs Version update: {version} -> {version + 1}")
                    else:
                        logger.warning(f"⚠️ [Priority synchronization] No matching data source configuration found: {data_source_name}")

            return result.modified_count > 0
        except Exception as e:
            logger.error(f"❌ Failed to update data source grouping relationship: {e}")
            return False

    async def update_category_datasource_order(self, category_id: str, ordered_datasources: List[Dict[str, Any]]) -> bool:
        """Update the sorting of data sources in categories

        🔥 Important: Update both datasource_groupings and system_configs collections at the same time
        - datasource_groupings: Used for front-end display and management
        - system_configs.data_source_configs: Used for priority judgment when obtaining actual data
        """
        try:
            db = await self._get_db()
            groupings_collection = db.datasource_groupings
            config_collection = db.system_configs

            # 1. Batch update priorities in datasource_groupings collection
            for item in ordered_datasources:
                await groupings_collection.update_one(
                    {
                        "data_source_name": item["name"],
                        "market_category_id": category_id
                    },
                    {
                        "$set": {
                            "priority": item["priority"],
                            "updated_at": now_tz()
                        }
                    }
                )

            # 2. 🔥 Synchronously update the system_configs collection data_source_configs
            # Get the currently active configuration
            config_data = await config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data:
                # Build a mapping of data source names to priorities
                priority_map = {item["name"]: item["priority"] for item in ordered_datasources}

                # Update the priority of the corresponding data source in data_source_configs
                data_source_configs = config_data.get("data_source_configs", [])
                updated = False

                for ds_config in data_source_configs:
                    ds_name = ds_config.get("name")
                    if ds_name in priority_map:
                        ds_config["priority"] = priority_map[ds_name]
                        updated = True
                        print(f"📊 [优先级同步] 更新数据源 {ds_name} 的优先级为 {priority_map[ds_name]}")

                # If there are updates, save them back to the database
                if updated:
                    await config_collection.update_one(
                        {"_id": config_data["_id"]},
                        {
                            "$set": {
                                "data_source_configs": data_source_configs,
                                "updated_at": now_tz(),
                                "version": config_data.get("version", 0) + 1
                            }
                        }
                    )
                    print(f"✅ [Priority synchronization] The system_configs collection has been synchronized and updated with a new version: {config_data.get('version', 0) + 1}")
                else:
                    print("⚠️ [Priority synchronization] No data source configuration that needs to be updated was found.")
            else:
                print("⚠️ [Priority synchronization] Activated system configuration not found")

            return True
        except Exception as e:
            print(f"❌ Failed to update classification data source sorting: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_system_config(self) -> Optional[SystemConfig]:
        """Get system configuration - get latest data from database first"""
        try:
            # Get the latest configuration directly from the database to avoid caching issues
            db = await self._get_db()
            config_collection = db.system_configs

            config_data = await config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data:
                print(f"📊 从数据库获取配置，版本: {config_data.get('version', 0)}, LLM配置数量: {len(config_data.get('llm_configs', []))}")
                config = SystemConfig(**config_data)
                self._ensure_llm_config_ids(config.llm_configs)
                return config

            # If there is no configuration, create a default configuration
            print("⚠️ There is no configuration in the database, create a default configuration")
            return await self._create_default_config()

        except Exception as e:
            print(f"❌ Failed to get configuration from database: {e}")

            # As a final fallback, try getting the
            try:
                unified_system_config = await unified_config.get_unified_system_config()
                if unified_system_config:
                    print("🔄 回退到统一配置管理器")
                    return unified_system_config
            except Exception as e2:
                print(f"从统一配置获取也失败: {e2}")

            return None
    
    async def _create_default_config(self) -> SystemConfig:
        """创建默认系统配置"""
        default_config = SystemConfig(
            config_name="默认配置",
            config_type="system",
            llm_configs=[
                LLMConfig(
                    provider=ModelProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key="your-openai-api-key",
                    api_base="https://api.openai.com/v1",
                    max_tokens=4000,
                    temperature=0.7,
                    enabled=False,
                    description="OpenAI GPT-3.5 Turbo model"
                ),
                LLMConfig(
                    provider=ModelProvider.ZHIPU,
                    model_name="glm-4",
                    api_key="your-zhipu-api-key",
                    api_base="https://open.bigmodel.cn/api/paas/v4",
                    max_tokens=4000,
                    temperature=0.7,
                    enabled=True,
                    description="Zhipu AI GLM-4 model (recommended)"
                ),
                LLMConfig(
                    provider=ModelProvider.QWEN,
                    model_name="qwen-turbo",
                    api_key="your-qwen-api-key",
                    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    max_tokens=4000,
                    temperature=0.7,
                    enabled=False,
                    description="阿里云通义千问模型"
                )
            ],
            default_llm="glm-4",
            data_source_configs=[
                DataSourceConfig(
                    name="AKShare",
                    type=DataSourceType.AKSHARE,
                    endpoint="https://akshare.akfamily.xyz",
                    timeout=30,
                    rate_limit=100,
                    enabled=True,
                    priority=1,
                    description="AKShare Open source financial data interface"
                ),
                DataSourceConfig(
                    name="Tushare",
                    type=DataSourceType.TUSHARE,
                    api_key="your-tushare-token",
                    endpoint="http://api.tushare.pro",
                    timeout=30,
                    rate_limit=200,
                    enabled=False,
                    priority=2,
                    description="Tushare Professional financial data interface"
                ),
                DataSourceConfig(
                    name="QMT",
                    type=DataSourceType.QMT,
                    endpoint="miniqmt://local",
                    timeout=15,
                    rate_limit=600,
                    enabled=False,
                    priority=2,
                    description="QMT 本地数据接口",
                    config_params={
                        "listen_port_range": "58620-58650",
                        "init_markets": "SH,SZ,BJ",
                        "auto_download_history": True,
                        "auto_download_financial": False,
                        "auto_download_sector": True,
                    }
                )
            ],
            default_data_source="AKShare",
            database_configs=[
                DatabaseConfig(
                    name="MongoDB主库",
                    type=DatabaseType.MONGODB,
                    host="localhost",
                    port=27017,
                    database="tradingagents",
                    enabled=True,
                    description="MongoDB主数据库"
                ),
                DatabaseConfig(
                    name="Redis缓存",
                    type=DatabaseType.REDIS,
                    host="localhost",
                    port=6379,
                    database="0",
                    enabled=True,
                    description="Redis缓存数据库"
                )
            ],
            system_settings={
                "max_concurrent_tasks": 3,
                "default_analysis_timeout": 300,
                "enable_cache": True,
                "cache_ttl": 3600,
                "log_level": "INFO",
                "enable_monitoring": True,
                # Worker/Queue intervals
                "worker_heartbeat_interval_seconds": 30,
                "queue_poll_interval_seconds": 1.0,
                "queue_cleanup_interval_seconds": 60.0,
                # SSE intervals
                "sse_poll_timeout_seconds": 1.0,
                "sse_heartbeat_interval_seconds": 10,
                "sse_task_max_idle_seconds": 300,
                "sse_batch_poll_interval_seconds": 2.0,
                "sse_batch_max_idle_seconds": 600,
                # TradingAgents runtime intervals (optional; DB-managed)
                "ta_hk_min_request_interval_seconds": 2.0,
                "ta_hk_timeout_seconds": 60,
                "ta_hk_max_retries": 3,
                "ta_hk_rate_limit_wait_seconds": 60,
                "ta_hk_cache_ttl_seconds": 86400,
                # New: TradingAgents data source strategy
                # Whether to cache from app first(Mongo collection stock_basic_info / market_quotes) read
                "ta_use_app_cache": False,
                "ta_china_min_api_interval_seconds": 0.5,
                "ta_us_min_api_interval_seconds": 1.0,
                "ta_google_news_sleep_min_seconds": 2.0,
                "ta_google_news_sleep_max_seconds": 6.0,
                "app_timezone": "Asia/Shanghai"
            }
        )
        
        # Save to database
        await self.save_system_config(default_config)
        return default_config
    
    async def save_system_config(self, config: SystemConfig) -> bool:
        """保存系统配置到数据库"""
        try:
            print(f"💾 Start saving configuration, LLM configuration quantity: {len(config.llm_configs)}")
            self._ensure_llm_config_ids(config.llm_configs)

            # Save to database
            db = await self._get_db()
            config_collection = db.system_configs

            # Update timestamp and version
            config.updated_at = now_tz()
            config.version += 1

            # Make the currently active configuration inactive
            update_result = await config_collection.update_many(
                {"is_active": True},
                {"$set": {"is_active": False}}
            )
            print(f"📝 禁用旧配置数量: {update_result.modified_count}")

            # Insert new configuration - remove the _id field and let MongoDB automatically generate a new one
            config_dict = config.model_dump(by_alias=True)
            if '_id' in config_dict:
                del config_dict['_id']  # Remove the old _id and let MongoDB generate the new one

            # Print to be saved system_settings
            system_settings = config_dict.get('system_settings', {})
            print(f"📝 即将保存的 system_settings 包含 {len(system_settings)} 项")
            if 'quick_analysis_model' in system_settings:
                print(f"  ✓ contains quick_analysis_model: {system_settings['quick_analysis_model']}")
            else:
                print("  ⚠️  Not included quick_analysis_model")
            if 'deep_analysis_model' in system_settings:
                print(f"  ✓ contains deep_analysis_model: {system_settings['deep_analysis_model']}")
            else:
                print("  ⚠️  Not included deep_analysis_model")

            insert_result = await config_collection.insert_one(config_dict)
            print(f"📝 新配置ID: {insert_result.inserted_id}")

            # Verify save results
            saved_config = await config_collection.find_one({"_id": insert_result.inserted_id})
            if saved_config:
                print(f"✅ The configuration is saved successfully and the LLM configuration quantity is verified.: {len(saved_config.get('llm_configs', []))}")

                # Temporarily skip unified configuration synchronization to avoid conflicts
                # unified_config.sync_to_legacy_format(config)

                return True
            else:
                print("❌ 配置保存验证失败")
                return False

        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_llm_config(self, provider: str, model_name: str) -> bool:
        """删除大模型配置"""
        try:
            print(f"🗑️ Delete large model configuration - provider: {provider}, model_name: {model_name}")

            config = await self.get_system_config()
            if not config:
                print("❌ 系统配置为空")
                return False

            print(f"📊 当前大模型配置数量: {len(config.llm_configs)}")

            # Print all existing configurations
            for i, llm in enumerate(config.llm_configs):
                # 🔥 Fix: provider is a string, not an enumeration
                provider_str = llm.provider if isinstance(llm.provider, str) else llm.provider.value
                print(f"   {i+1}. provider: {provider_str}, model_name: {llm.model_name}")

            # Find and delete the specified LLM configuration
            original_count = len(config.llm_configs)

            # Use looser matching criteria
            config.llm_configs = [
                llm for llm in config.llm_configs
                if not (
                    (llm.provider if isinstance(llm.provider, str) else llm.provider.value).lower() == provider.lower()
                    and llm.model_name == model_name
                )
            ]

            new_count = len(config.llm_configs)
            print(f"🔄 删除后配置数量: {new_count} (原来: {original_count})")

            if new_count == original_count:
                print(f"❌ 没有找到匹配的配置: {provider}/{model_name}")
                return False  # The configuration to be deleted was not found

            # Save updated configuration
            save_result = await self.save_system_config(config)
            print(f"💾 保存结果: {save_result}")

            return save_result

        except Exception as e:
            print(f"❌ 删除LLM配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def set_default_llm(self, model_name: str) -> bool:
        """设置默认大模型"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # Checks whether the specified model exists
            model_exists = any(
                llm.model_name == model_name for llm in config.llm_configs
            )

            if not model_exists:
                return False

            config.default_llm = model_name
            return await self.save_system_config(config)

        except Exception as e:
            print(f"设置默认LLM失败: {e}")
            return False

    async def set_default_data_source(self, data_source_name: str) -> bool:
        """设置默认数据源"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # Check whether the specified data source exists
            source_exists = any(
                ds.name == data_source_name for ds in config.data_source_configs
            )

            if not source_exists:
                return False

            config.default_data_source = data_source_name
            return await self.save_system_config(config)

        except Exception as e:
            print(f"设置默认数据源失败: {e}")
            return False

    async def update_system_settings(self, settings: Dict[str, Any]) -> bool:
        """更新系统设置"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            self._ensure_llm_config_ids(config.llm_configs)
            settings = self._normalize_default_model_settings(
                settings,
                config.system_settings,
                config.llm_configs,
            )

            # Print system settings before update
            print(f"📝 更新前 system_settings 包含 {len(config.system_settings)} 项")
            if 'quick_analysis_model' in config.system_settings:
                print(f"  ✓ Included before updating quick_analysis_model: {config.system_settings['quick_analysis_model']}")
            else:
                print("  ⚠️  Not included before update quick_analysis_model")

            # Update system settings
            config.system_settings.update(settings)

            # Print updated system settings
            print(f"📝 更新后 system_settings 包含 {len(config.system_settings)} 项")
            if 'quick_analysis_model' in config.system_settings:
                print(f"  ✓ Updated to include quick_analysis_model: {config.system_settings['quick_analysis_model']}")
            else:
                print("  ⚠️  Not included after update quick_analysis_model")
            if 'deep_analysis_model' in config.system_settings:
                print(f"  ✓ Updated to include deep_analysis_model: {config.system_settings['deep_analysis_model']}")
            else:
                print("  ⚠️  Not included after update deep_analysis_model")

            result = await self.save_system_config(config)

            # Sync to file system (for use by unified_config)
            if result:
                try:
                    from app.core.unified_config import unified_config
                    unified_config.sync_to_legacy_format(config)
                    print("✅ System settings synced to file system")
                except Exception as e:
                    print(f"⚠️  Syncing system settings to file system failed: {e}")

                # Synchronize agent configuration to environment variables (requires restart to take full effect, but set environment variables first)
                import os
                proxy_keys = ['http_proxy', 'https_proxy', 'no_proxy']
                for key in proxy_keys:
                    if key in settings:
                        env_key = key.upper()
                        value = settings[key] or ""
                        if value:
                            os.environ[env_key] = value
                            print(f"✅ 已设置环境变量 {env_key}")
                        elif env_key in os.environ:
                            del os.environ[env_key]
                            print(f"✅ 已删除环境变量 {env_key}")

            return result

        except Exception as e:
            print(f"更新系统设置失败: {e}")
            return False

    async def get_system_settings(self) -> Dict[str, Any]:
        """获取系统设置"""
        try:
            config = await self.get_system_config()
            if not config:
                return {}
            return config.system_settings
        except Exception as e:
            print(f"获取系统设置失败: {e}")
            return {}

    async def export_config(self) -> Dict[str, Any]:
        """导出配置"""
        try:
            config = await self.get_system_config()
            if not config:
                return {}

            # Convert to serializable dictionary format
            # Solution A: Desensitize/clear sensitive fields when exporting
            def _llm_sanitize(x: LLMConfig):
                d = x.model_dump()
                d["api_key"] = ""
                # Ensure required fields have default values (prevent None or empty strings from being exported)
                # Note: max_tokens already has the correct value in system_configs, use it directly
                if not d.get("max_tokens") or d.get("max_tokens") == "":
                    d["max_tokens"] = 4000
                if not d.get("temperature") and d.get("temperature") != 0:
                    d["temperature"] = 0.7
                if not d.get("timeout") or d.get("timeout") == "":
                    d["timeout"] = 180
                if not d.get("retry_times") or d.get("retry_times") == "":
                    d["retry_times"] = 3
                return d
            def _ds_sanitize(x: DataSourceConfig):
                d = x.model_dump()
                d["api_key"] = ""
                d["api_secret"] = ""
                return d
            def _db_sanitize(x: DatabaseConfig):
                d = x.model_dump()
                d["password"] = ""
                return d
            export_data = {
                "config_name": config.config_name,
                "config_type": config.config_type,
                "llm_configs": [_llm_sanitize(llm) for llm in config.llm_configs],
                "default_llm": config.default_llm,
                "data_source_configs": [_ds_sanitize(ds) for ds in config.data_source_configs],
                "default_data_source": config.default_data_source,
                "database_configs": [_db_sanitize(db) for db in config.database_configs],
                # Plan A: Desensitize sensitive keys in system_settings when exporting
                "system_settings": {k: (None if any(p in k.lower() for p in ("key","secret","password","token","client_secret")) else v) for k, v in (config.system_settings or {}).items()},
                "exported_at": now_tz().isoformat(),
                "version": config.version
            }

            return export_data

        except Exception as e:
            print(f"导出配置失败: {e}")
            return {}

    async def import_config(self, config_data: Dict[str, Any]) -> bool:
        """导入配置"""
        try:
            # Verify configuration data format
            if not self._validate_config_data(config_data):
                return False

            # Create a new system configuration (Option A: Ignore sensitive fields when importing)
            def _llm_sanitize_in(llm: Dict[str, Any]):
                d = dict(llm or {})
                d.pop("api_key", None)
                d["api_key"] = ""
                # Clean empty strings and let Pydantic use default values
                if d.get("max_tokens") == "" or d.get("max_tokens") is None:
                    d.pop("max_tokens", None)
                if d.get("temperature") == "" or d.get("temperature") is None:
                    d.pop("temperature", None)
                if d.get("timeout") == "" or d.get("timeout") is None:
                    d.pop("timeout", None)
                if d.get("retry_times") == "" or d.get("retry_times") is None:
                    d.pop("retry_times", None)
                return LLMConfig(**d)
            def _ds_sanitize_in(ds: Dict[str, Any]):
                d = dict(ds or {})
                d.pop("api_key", None)
                d.pop("api_secret", None)
                d["api_key"] = ""
                d["api_secret"] = ""
                return DataSourceConfig(**d)
            def _db_sanitize_in(db: Dict[str, Any]):
                d = dict(db or {})
                d.pop("password", None)
                d["password"] = ""
                return DatabaseConfig(**d)
            new_config = SystemConfig(
                config_name=config_data.get("config_name", "导入的配置"),
                config_type="imported",
                llm_configs=[_llm_sanitize_in(llm) for llm in config_data.get("llm_configs", [])],
                default_llm=config_data.get("default_llm"),
                data_source_configs=[_ds_sanitize_in(ds) for ds in config_data.get("data_source_configs", [])],
                default_data_source=config_data.get("default_data_source"),
                database_configs=[_db_sanitize_in(db) for db in config_data.get("database_configs", [])],
                system_settings=config_data.get("system_settings", {})
            )

            return await self.save_system_config(new_config)

        except Exception as e:
            print(f"导入配置失败: {e}")
            return False

    def _validate_config_data(self, config_data: Dict[str, Any]) -> bool:
        """验证配置数据格式"""
        try:
            required_fields = ["llm_configs", "data_source_configs", "database_configs", "system_settings"]
            for field in required_fields:
                if field not in config_data:
                    print(f"配置数据缺少必需字段: {field}")
                    return False

            return True

        except Exception as e:
            print(f"验证配置数据失败: {e}")
            return False

    async def migrate_legacy_config(self) -> bool:
        """迁移传统配置"""
        try:
            # Here you can call the logic of the migration script
            # Or implement the migration logic directly here
            from scripts.migrate_config_to_webapi import ConfigMigrator

            migrator = ConfigMigrator()
            return await migrator.migrate_all_configs()

        except Exception as e:
            print(f"迁移传统配置失败: {e}")
            return False
    
    async def update_llm_config(self, llm_config: LLMConfig) -> bool:
        """更新大模型配置"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            self._ensure_llm_config_ids(config.llm_configs)
            if not llm_config.config_id:
                matched_config = self._select_llm_config(
                    config.llm_configs,
                    model_name=llm_config.model_name,
                    preferred_provider=llm_config.provider,
                )
                if matched_config is not None:
                    llm_config.config_id = self._read_llm_config_field(matched_config, "config_id")

            if not llm_config.config_id:
                llm_config.config_id = self._build_deterministic_llm_config_id(llm_config, len(config.llm_configs))

            # Save directly to Unified Configuration Manager
            success = unified_config.save_llm_config(llm_config)
            if not success:
                return False

            # Find and update the corresponding LLM configuration
            for i, existing_config in enumerate(config.llm_configs):
                same_config_id = bool(llm_config.config_id) and existing_config.config_id == llm_config.config_id
                same_provider_model = (
                    existing_config.provider == llm_config.provider
                    and existing_config.model_name == llm_config.model_name
                )
                if same_config_id or same_provider_model:
                    if not llm_config.config_id:
                        llm_config.config_id = existing_config.config_id
                    config.llm_configs[i] = llm_config
                    break
            else:
                # If it does not exist, add a new configuration
                config.llm_configs.append(llm_config)

            return await self.save_system_config(config)
        except Exception as e:
            print(f"更新LLM配置失败: {e}")
            return False

    async def batch_import_llm_configs(self, selected_providers: List[str] = None) -> Dict[str, Any]:
        """One-click import: from model directory + Factory configuration to create large model configurations in batches

        Args:
            selected_providers: Specify the list of manufacturers to import. If it is empty, all manufacturers with configured API keys will be imported.

        Logic:
        1. Get all enabled manufacturers with API Key (can be filtered by selected_providers)
        2. Get model catalogs from these manufacturers
        3. For each model in the directory, create it if it does not exist in the large model configuration
        4. Get metadata such as capability ratings from DEFAULT_MODEL_CAPABILITIES
        """
        from app.constants.model_capabilities import DEFAULT_MODEL_CAPABILITIES

        try:
            # 1. Get enabled manufacturers (filtered by selected_providers)
            providers = await self.get_llm_providers()
            active_providers = {
                p.name: p for p in providers
                if p.is_active
                and (not selected_providers or p.name in selected_providers)
                and (
                    p.name.lower() in ("ollama", "localai")
                    or (p.api_key and p.api_key.strip())
                    or p.extra_config.get("has_api_key", False)
                )
            }
            logger.info(f"📦 [batch_import] Active manufacturers: {list(active_providers.keys())}")

            if not active_providers:
                return {
                    "success": False,
                    "message": "If there is no manufacturer with an API key configured, please configure the API key in the manufacturer management first.",
                    "imported": 0,
                    "skipped": 0,
                    "errors": [],
                }

            # 2. Get model directory
            catalogs = await self.get_model_catalog()
            catalog_map = {c.provider: c for c in catalogs}

            # 3. Get existing large model configuration (for deduplication)
            config = await self.get_system_config()
            existing_keys = set()
            if config:
                for llm in config.llm_configs:
                    existing_keys.add(f"{llm.provider}/{llm.model_name}")

            # 4. Create in batches
            imported = 0
            skipped = 0
            errors = []
            new_configs = []

            for provider_name, provider in active_providers.items():
                catalog = catalog_map.get(provider_name)
                if not catalog:
                    continue

                for model in catalog.models:
                    if model.is_deprecated:
                        continue

                    config_key = f"{provider_name}/{model.name}"
                    if config_key in existing_keys:
                        skipped += 1
                        continue

                    try:
                        # Get metadata from capability catalog
                        cap = DEFAULT_MODEL_CAPABILITIES.get(model.name, {})

                        llm_config = LLMConfig(
                            provider=provider_name,
                            model_name=model.name,
                            model_display_name=model.display_name,
                            api_key="",  # Leave it blank and obtain it from the manufacturer configuration at runtime.
                            api_base=provider.default_base_url or "",
                            max_tokens=model.max_tokens or 8000,
                            temperature=0.2,
                            timeout=180,
                            retry_times=3,
                            enabled=True,
                            description=cap.get("description", model.description or ""),
                            model_category=None,
                            enable_memory=False,
                            enable_debug=False,
                            priority=0,
                            input_price_per_1k=model.input_price_per_1k,
                            output_price_per_1k=model.output_price_per_1k,
                            currency=model.currency or "CNY",
                            capability_level=cap.get("capability_level", 5),
                            suitable_roles=[r.value if hasattr(r, "value") else str(r) for r in cap.get("suitable_roles", ["both"])] or ["both"],
                            features=[f.value if hasattr(f, "value") else str(f) for f in cap.get("features", ["tool_calling", "long_context", "reasoning"])] or ["tool_calling", "long_context", "reasoning"],
                            recommended_depths=cap.get("recommended_depths", ["快速", "基础", "标准", "深度", "全面"]) or ["快速", "基础", "标准", "深度", "全面"],
                            performance_metrics=cap.get("performance_metrics"),
                        )

                        # save
                        success = await self.update_llm_config(llm_config)
                        if success:
                            new_configs.append(llm_config)
                            existing_keys.add(config_key)
                            imported += 1
                            logger.info(f"✅ [batch_import] import: {config_key}")
                        else:
                            errors.append(f"{config_key}: 保存失败")
                    except Exception as e:
                        errors.append(f"{config_key}: {str(e)}")
                        logger.warning(f"⚠️ [batch_import] Import failed {config_key}: {e}")

            # synchronized pricing
            if imported > 0:
                try:
                    from app.core.config_bridge import sync_pricing_config_now
                    sync_pricing_config_now()
                except Exception:
                    pass

            message = f"成功导入 {imported} 个模型配置"
            if skipped > 0:
                message += f"，跳过 {skipped} 个已存在的配置"
            if errors:
                message += f"，{len(errors)} 个失败"

            return {
                "success": True,
                "message": message,
                "imported": imported,
                "skipped": skipped,
                "errors": errors,
            }
        except Exception as e:
            logger.error(f"❌ [batch_import] Batch import failed: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"批量导入失败: {str(e)}",
                "imported": 0,
                "skipped": 0,
                "errors": [str(e)],
            }

    async def test_llm_config(self, llm_config: LLMConfig) -> Dict[str, Any]:
        """Test large model configuration - real call API for verification"""
        start_time = time.time()
        try:
            import requests

            # Get provider string value (compatible with enumeration and string)
            provider_str = llm_config.provider.value if hasattr(llm_config.provider, 'value') else str(llm_config.provider)

            logger.info(f"🧪 测试大模型配置: {provider_str} - {llm_config.model_name}")
            logger.info(f"📍 API Basics URL (Model configuration): {llm_config.api_base}")

            # Get manufacturer configuration (used to get API Key and default_base_url)
            db = await self._get_db()
            providers_collection = db.llm_providers
            provider_data = await providers_collection.find_one({"name": provider_str})

            # 1. Determine API Basics URL
            api_base = llm_config.api_base
            if not api_base:
                # If the model configuration does not have api_base, obtain it from the manufacturer configuration. default_base_url
                if provider_data and provider_data.get("default_base_url"):
                    api_base = provider_data["default_base_url"]
                    logger.info(f"✅ Get API base from factory configuration URL: {api_base}")
                else:
                    return {
                        "success": False,
                        "message": "Neither the model configuration nor the factory configuration has the API base set URL",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            # 🔥 Local model list (no API Key required)
            local_models = ["ollama", "localai"]
            is_local_model = provider_str.lower() in local_models

            # 2. Verify API Key (Priority: Factory Configuration > Model configuration > environment variables)
            # 🔥 Local models do not require API Key, skip checking
            api_key = None
            api_key_source = None

            if is_local_model:
                # Local models do not require an API Key, use placeholders
                api_key = "ollama"  # Placeholder, not actually used
                api_key_source = "Local model (no API key required)"
                logger.info(f"✅ 本地模型 {provider_str} 不需要 API Key")
            else:
                # Cloud model requires API Key
                # Prioritize obtaining configuration from manufacturer API Key
                if provider_data and provider_data.get("api_key") and self._is_valid_api_key(provider_data.get("api_key")):
                    api_key = provider_data["api_key"]
                    api_key_source = "厂家配置（数据库）"
                    logger.info("✅ Obtain API key from manufacturer configuration")
                # Secondly, get it from the model configuration
                elif llm_config.api_key and self._is_valid_api_key(llm_config.api_key):
                    api_key = llm_config.api_key
                    api_key_source = "模型配置"
                    logger.info("✅ Get API key from model configuration")
                # Finally try to get from environment variables
                else:
                    api_key = self._get_env_api_key(provider_str)
                    if api_key:
                        api_key_source = "环境变量"
                        logger.info("✅ Get API key from environment variable")

                # The cloud model must be configured with a valid API Key
                if not api_key or not self._is_valid_api_key(api_key):
                    return {
                        "success": False,
                        "message": f"{provider_str} No valid API key is configured (checked: manufacturer configuration, model configuration, environment variables)",
                        "response_time": time.time() - start_time,
                        "details": {
                            "provider": provider_str,
                            "checked_sources": ["厂家配置（数据库）", "模型配置", "环境变量"],
                            "has_provider_data": provider_data is not None,
                            "has_model_api_key": bool(llm_config.api_key)
                        }
                    }

            logger.info(f"🔑 使用API密钥来源: {api_key_source}")

            # 3. Select test method according to manufacturer type
            if provider_str == "google":
                # Google AI Use specialized testing methods
                logger.info("🔍 Use Google AI-specific testing methods")
                result = self._test_google_api(api_key, f"{provider_str} {llm_config.model_name}", api_base, llm_config.model_name)
                result["response_time"] = time.time() - start_time
                return result
            elif provider_str == "deepseek":
                # DeepSeek Use specialized testing methods
                logger.info("🔍 Use DeepSeek dedicated testing methods")
                result = self._test_deepseek_api(
                    api_key,
                    f"{provider_str} {llm_config.model_name}",
                    llm_config.model_name,
                    llm_config.temperature,
                    llm_config.max_tokens,
                    llm_config.timeout,
                )
                result["response_time"] = time.time() - start_time
                return result
            elif provider_str == "dashscope":
                # DashScope Use specialized testing methods
                logger.info("🔍 Using DashScope-specific test methods")
                result = self._test_dashscope_api(api_key, f"{provider_str} {llm_config.model_name}", llm_config.model_name)
                result["response_time"] = time.time() - start_time
                return result
            else:
                # Other manufacturers use OpenAI compatible test methods
                logger.info("🔍 Use OpenAI compliant testing methods")

                # Build test request
                api_base_normalized = api_base.rstrip("/")

                # 🔥 Ollama Special handling: Ollama's OpenAI compatible endpoint requires the /v1 prefix
                # if base_url is http://localhost:11434, Need to add /v1
                # If base_url is already http://localhost:11434/v1, then remains unchanged
                if is_local_model and provider_str.lower() == "ollama":
                    # Ollama OpenAI compatibility mode requires the /v1 prefix
                    if not api_base_normalized.endswith("/v1"):
                        api_base_normalized = api_base_normalized + "/v1"
                        logger.info(f"   Ollama: Add /v1 version number: {api_base_normalized}")
                    else:
                        logger.info(f"   Ollama: An existing version number is detected, keep it as is: {api_base_normalized}")
                else:
                    # 🔧 Intelligent version number processing: only add a version number if there is no version number /v1
                    # Avoid adding URLs with existing version numbers (such as /v4 of Zhipu AI) repeatedly. /v1
                    import re
                    if not re.search(r'/v\d+$', api_base_normalized):
                        # URL There is no version number at the end, add /v1 (OpenAI standard)
                        api_base_normalized = api_base_normalized + "/v1"
                        logger.info(f"   添加 /v1 版本号: {api_base_normalized}")
                    else:
                        # URL Already contains the version number (such as /v4), do not add it
                        logger.info(f"   An existing version number is detected, keep it as is: {api_base_normalized}")

                url = f"{api_base_normalized}/chat/completions"

                # 🔥 Local models can not set the Authorization header, or use placeholders
                headers = {
                    "Content-Type": "application/json",
                }
                # Only non-local models are added Authorization header
                if not is_local_model:
                    headers["Authorization"] = f"Bearer {api_key}"
                else:
                    # Some local services (such as Ollama) may require an Authorization header, but any value can be used
                    headers["Authorization"] = f"Bearer {api_key}"

                # 🔥 Ollama Model name format conversion: convert dash to colon
                # Ollama Use a colon in the model name (e.g. qwen2.5:7b) , But horizontal lines may be used in the configuration (qwen2.5-7b)
                model_name_for_request = (llm_config.model_name or "").strip()
                if is_local_model and provider_str.lower() == "ollama":
                    # Convert dash to colon (Ollama format)
                    if "-" in model_name_for_request and ":" not in model_name_for_request:
                        model_name_for_request = model_name_for_request.replace("-", ":", 1)
                        logger.info(f"   Ollama: Model name format conversion: {llm_config.model_name} -> {model_name_for_request}")
                
                data = {
                    "model": model_name_for_request,
                    "messages": [
                        {"role": "user", "content": "Hello, please respond with 'OK' if you can read this."}
                    ],
                    "max_tokens": llm_config.max_tokens,
                    "temperature": llm_config.temperature
                }

                logger.info(f"🌐 发送测试请求到: {url}")
                logger.info(f"📦 使用模型: {llm_config.model_name}")
                logger.info(
                    f"📦 Use test parameters: max_tokens={llm_config.max_tokens}, "
                    f"temperature={llm_config.temperature}, timeout={llm_config.timeout}"
                )
                logger.info(f"📦 请求数据: {data}")

                # Send test request
                response = requests.post(url, json=data, headers=headers, timeout=llm_config.timeout)
                response_time = time.time() - start_time

                logger.info(f"📡 收到响应: HTTP {response.status_code}")

                # Processing responses (only for OpenAI compatible vendors)
                if response.status_code == 200:
                    try:
                        result = response.json()
                        logger.info(f"📦 响应JSON: {result}")

                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0]["message"]["content"]
                            logger.info(f"📝 响应内容: {content}")

                            if content and len(content.strip()) > 0:
                                logger.info(f"✅ 测试成功: {content[:50]}")
                                return {
                                    "success": True,
                                    "message": f"成功连接到 {provider_str} {llm_config.model_name}",
                                    "response_time": response_time,
                                    "details": {
                                        "provider": provider_str,
                                        "model": llm_config.model_name,
                                        "api_base": api_base,
                                        "response_preview": content[:100]
                                    }
                                }
                            else:
                                logger.warning("⚠️ API响应内容为空")
                                return {
                                    "success": False,
                                    "message": "API响应内容为空",
                                    "response_time": response_time,
                                    "details": None
                                }
                        else:
                            logger.warning("⚠️ API The response format is abnormal and the choices field is missing")
                            logger.warning(f"   响应内容: {result}")
                            return {
                                "success": False,
                                "message": "API响应格式异常",
                                "response_time": response_time,
                                "details": None
                            }
                    except Exception as e:
                        logger.error(f"❌ 解析响应失败: {e}")
                        logger.error(f"   响应文本: {response.text[:500]}")
                        return {
                            "success": False,
                            "message": f"解析响应失败: {str(e)}",
                            "response_time": response_time,
                            "details": None
                        }
                elif response.status_code == 401:
                    return {
                        "success": False,
                        "message": "API密钥无效或已过期",
                        "message": "Account authentication failed, please check API Key, account status and model access permissions",
                        "response_time": response_time,
                        "details": None
                    }
                elif response.status_code == 402:
                    return {
                        "success": False,
                        "message": "The account balance is insufficient, please check the balance, package quota or model payment permissions",
                        "response_time": response_time,
                        "details": None
                    }
                elif response.status_code == 403:
                    return {
                        "success": False,
                        "message": "The account has insufficient permissions, or the current model quota has been used up. Please check the package and model authorization.",
                        "response_time": response_time,
                        "details": None
                    }
                elif response.status_code == 404:
                    # 🔥 Special prompts for local model (Ollama) 404 errors
                    if is_local_model:
                        error_msg = (
                            f"Ollama The service returns 404, possible reasons:\n"
                            f"1. Ollama The service is not started (please run `ollama serve` or launch the Ollama app)\n"
                            f"2. model '{llm_config.model_name}' Not downloaded (please run `ollama pull {llm_config.model_name}`) \n"
                            f"3. API Incorrect endpoint (currently: {url}) \n"
                            f"4. Ollama The version is too low and does not support OpenAI compatibility mode (requires Ollama 0.1.0+) "
                        )
                    else:
                        error_msg = f"API The endpoint does not exist, please check if the API base URL is correct: {url}"
                    
                    return {
                        "success": False,
                        "message": error_msg,
                        "response_time": response_time,
                        "details": {
                            "url": url,
                            "is_local_model": is_local_model,
                            "provider": provider_str,
                            "model": llm_config.model_name
                        }
                    }
                else:
                    try:
                        error_detail = response.json()
                        error_msg = error_detail.get("error", {}).get("message", f"HTTP {response.status_code}")
                        return {
                            "success": False,
                            "message": f"API测试失败: {error_msg}",
                            "response_time": response_time,
                            "details": None
                        }
                    except Exception:
                        return {
                        "success": False,
                        "message": f"API test failed: HTTP {response.status_code}",
                        "response_time": response_time,
                        "details": None
                    }

        except requests.exceptions.Timeout:
            response_time = time.time() - start_time
            return {
                "success": False,
                "message": "The connection timed out. Please check whether the API base URL is correct or whether the network is reachable.",
                "response_time": response_time,
                "details": None
            }
        except requests.exceptions.ConnectionError as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "message": f"Connection failed, please check whether the API base URL is correct: {str(e)}",
                "response_time": response_time,
                "details": None
            }
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"❌ 测试大模型配置失败: {e}")
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": response_time,
                "details": None
            }
    
    def _truncate_api_key(self, api_key: str, prefix_len: int = 6, suffix_len: int = 6) -> str:
        """
        Truncate API Key for display

        Args:
            api_key: complete API Key
            prefix_len: Preserve prefix length
            suffix_len: Keep suffix length

        Returns:
            Truncated API Key, for example:0f229a...c550ec
        """
        if not api_key or len(api_key) <= prefix_len + suffix_len:
            return api_key

        return f"{api_key[:prefix_len]}...{api_key[-suffix_len:]}"

    async def test_data_source_config(self, ds_config: DataSourceConfig) -> Dict[str, Any]:
        """Test data source configuration - real call API for verification"""
        start_time = time.time()
        try:
            import requests
            import os

            ds_type = ds_config.type.value if hasattr(ds_config.type, 'value') else str(ds_config.type)

            logger.info(f"🧪 [TEST] Testing data source config: {ds_config.name} ({ds_type})")

            # 🔥 The API Key in the configuration is used first. If it is not available or truncated, it is obtained from the database.
            api_key = ds_config.api_key
            used_db_credentials = False
            used_env_credentials = False

            logger.info(f"🔍 [TEST] Received API Key from config: {repr(api_key)} (type: {type(api_key).__name__}, length: {len(api_key) if api_key else 0})")

            # Test against different data source types
            if ds_type == "tushare":
                # 🔥 If the API Key in the configuration contains "..." (truncation mark), need to verify whether it is the unmodified original value
                if api_key and "..." in api_key:
                    logger.info("🔍 [TEST] API Key contains '...' (truncated), checking if it matches database value")

                    # Get complete from database API Key
                    system_config = await self.get_system_config()
                    db_config = None
                    if system_config:
                        for ds in system_config.data_source_configs:
                            if ds.name == ds_config.name:
                                db_config = ds
                                break

                    if db_config and db_config.api_key:
                        # Do the same truncation for the full API Key in the database
                        truncated_db_key = self._truncate_api_key(db_config.api_key)
                        logger.info(f"🔍 [TEST] Database API Key truncated: {truncated_db_key}")
                        logger.info(f"🔍 [TEST] Received API Key: {api_key}")

                        # Compare truncated values
                        if api_key == truncated_db_key:
                            # Same, indicating that the user has not modified it and uses the complete value in the database.
                            api_key = db_config.api_key
                            used_db_credentials = True
                            logger.info(f"✅ [TEST] Truncated values match, using complete API Key from database (length: {len(api_key)})")
                        else:
                            # Different, indicating that the user has modified it but the modification is incomplete.
                            logger.error("❌ [TEST] Truncated API Key doesn't match database value, user may have modified it incorrectly")
                            return {
                                "success": False,
                                "message": "API Key Format error: Truncation token detected but does not match value in database, please enter complete API Key",
                                "response_time": time.time() - start_time,
                                "details": {
                                    "error": "truncated_key_mismatch",
                                    "received": api_key,
                                    "expected": truncated_db_key
                                }
                            }
                    else:
                        # There is no valid API Key in the database, try to get it from environment variables
                        logger.info("⚠️  [TEST] No valid API Key in database, trying environment variable")
                        env_token = os.getenv('TUSHARE_TOKEN')
                        if env_token:
                            api_key = env_token.strip().strip('"').strip("'")
                            used_env_credentials = True
                            logger.info(f"🔑 [TEST] Using TUSHARE_TOKEN from environment (length: {len(api_key)})")
                        else:
                            logger.error("❌ [TEST] No valid API Key in database or environment")
                            return {
                                "success": False,
                                "message": "API Key Invalid: There is no valid configuration in the database or environment variables. Token",
                                "response_time": time.time() - start_time,
                                "details": None
                            }

                # If the API Key is empty, try to get it from the database or environment variables
                elif not api_key:
                    logger.info("⚠️  [TEST] API Key is empty, trying to get from database")

                    # Get complete from database API Key
                    system_config = await self.get_system_config()
                    db_config = None
                    if system_config:
                        for ds in system_config.data_source_configs:
                            if ds.name == ds_config.name:
                                db_config = ds
                                break

                    if db_config and db_config.api_key and "..." not in db_config.api_key:
                        api_key = db_config.api_key
                        used_db_credentials = True
                        logger.info(f"🔑 [TEST] Using API Key from database (length: {len(api_key)})")
                    else:
                        # If it is not in the database, try to get it from environment variables
                        logger.info("⚠️  [TEST] No valid API Key in database, trying environment variable")
                        env_token = os.getenv('TUSHARE_TOKEN')
                        if env_token:
                            api_key = env_token.strip().strip('"').strip("'")
                            used_env_credentials = True
                            logger.info(f"🔑 [TEST] Using TUSHARE_TOKEN from environment (length: {len(api_key)})")
                        else:
                            logger.error("❌ [TEST] No valid API Key in config, database, or environment")
                            return {
                                "success": False,
                                "message": "API Key Invalid: There is no valid configuration in the configuration, database and environment variables. Token",
                                "response_time": time.time() - start_time,
                                "details": None
                            }
                else:
                    # API Key is complete and can be used directly
                    logger.info(f"✅ [TEST] Using complete API Key from config (length: {len(api_key)})")

                # test Tushare API
                try:
                    logger.info(f"🔌 [TEST] Calling Tushare API with token (length: {len(api_key)})")
                    import tushare as ts
                    import os

                    # 🔧 Temporarily disable the proxy (Tushare is a domestic data source and does not require a proxy)
                    # Save original proxy settings
                    original_http_proxy = os.environ.get('HTTP_PROXY')
                    original_https_proxy = os.environ.get('HTTPS_PROXY')
                    original_http_proxy_lower = os.environ.get('http_proxy')
                    original_https_proxy_lower = os.environ.get('https_proxy')

                    try:
                        # temporary clearing agent
                        if 'HTTP_PROXY' in os.environ:
                            del os.environ['HTTP_PROXY']
                        if 'HTTPS_PROXY' in os.environ:
                            del os.environ['HTTPS_PROXY']
                        if 'http_proxy' in os.environ:
                            del os.environ['http_proxy']
                        if 'https_proxy' in os.environ:
                            del os.environ['https_proxy']

                        logger.info("🌐 [TEST] Proxy disabled for Tushare API call (domestic data source)")

                        # Directly pass the token to pro_api without calling set_token to avoid writing the tk.csv file
                        pro = ts.pro_api(api_key)
                        # Get trading calendar (lightweight test)
                        df = pro.trade_cal(exchange='SSE', start_date='20240101', end_date='20240101')
                    finally:
                        # Restore original proxy settings
                        if original_http_proxy is not None:
                            os.environ['HTTP_PROXY'] = original_http_proxy
                        if original_https_proxy is not None:
                            os.environ['HTTPS_PROXY'] = original_https_proxy
                        if original_http_proxy_lower is not None:
                            os.environ['http_proxy'] = original_http_proxy_lower
                        if original_https_proxy_lower is not None:
                            os.environ['https_proxy'] = original_https_proxy_lower

                    if df is not None and len(df) > 0:
                        response_time = time.time() - start_time
                        logger.info(f"✅ [TEST] Tushare API call successful (response time: {response_time:.2f}s)")

                        # Build a message stating which source of credentials was used
                        credential_source = "配置"
                        if used_db_credentials:
                            credential_source = "数据库"
                        elif used_env_credentials:
                            credential_source = "环境变量"

                        return {
                            "success": True,
                            "message": f"成功连接到 Tushare 数据源（使用{credential_source}中的凭证）",
                            "response_time": response_time,
                            "details": {
                                "type": ds_type,
                                "test_result": "获取交易日历成功",
                                "credential_source": credential_source,
                                "used_db_credentials": used_db_credentials,
                                "used_env_credentials": used_env_credentials
                            }
                        }
                    else:
                        logger.error("❌ [TEST] Tushare API returned empty data")
                        return {
                            "success": False,
                            "message": "Tushare API Return data is empty",
                            "response_time": time.time() - start_time,
                            "details": None
                        }
                except ImportError:
                    logger.error("❌ [TEST] Tushare library not installed")
                    return {
                        "success": False,
                        "message": "Tushare The library is not installed, please run: pip install tushare",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    logger.error(f"❌ [TEST] Tushare API call failed: {e}")
                    return {
                        "success": False,
                        "message": f"Tushare API call failed: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif ds_type == "akshare":
                # AKShare No API Key required, test directly
                try:
                    import akshare as ak
                    # Test with a more lightweight interface - get trading calendar
                    # This interface has small data volume and fast response, making it more suitable for testing connections.
                    df = ak.tool_trade_date_hist_sina()

                    if df is not None and len(df) > 0:
                        response_time = time.time() - start_time
                        return {
                            "success": True,
                            "message": "Successfully connected to AKShare data source",
                            "response_time": response_time,
                            "details": {
                                "type": ds_type,
                                "test_result": f"获取交易日历成功（{len(df)} 条记录）"
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "message": "AKShare API Return data is empty",
                            "response_time": time.time() - start_time,
                            "details": None
                        }
                except ImportError:
                    return {
                        "success": False,
                        "message": "AKShare The library is not installed, please run: pip install akshare",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"AKShare API call failed: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif ds_type == "qmt":
                original_env: Dict[str, Optional[str]] = {}
                temp_env = {
                    "QMT_TOKEN": ds_config.api_key or "",
                }
                qmt_param_map = {
                    "data_dir": "QMT_DATA_DIR",
                    "listen_port": "QMT_LISTEN_PORT",
                    "listen_port_range": "QMT_LISTEN_PORT_RANGE",
                    "init_markets": "QMT_INIT_MARKETS",
                    "kline_mirror_markets": "QMT_KLINE_MIRROR_MARKETS",
                    "allow_optimize_addresses": "QMT_ALLOW_OPTIMIZE_ADDRESSES",
                    "history_start_time": "QMT_HISTORY_START_TIME",
                    "start_local_service": "QMT_START_LOCAL_SERVICE",
                    "kline_mirror_enabled": "QMT_KLINE_MIRROR_ENABLED",
                    "auto_download_history": "QMT_AUTO_DOWNLOAD_HISTORY",
                    "auto_download_financial": "QMT_AUTO_DOWNLOAD_FINANCIAL",
                    "auto_download_sector": "QMT_AUTO_DOWNLOAD_SECTOR",
                }

                for key, env_key in qmt_param_map.items():
                    value = (ds_config.config_params or {}).get(key)
                    if value is None:
                        continue
                    if isinstance(value, list):
                        temp_env[env_key] = ",".join(str(item) for item in value)
                    elif isinstance(value, bool):
                        temp_env[env_key] = str(value).lower()
                    else:
                        temp_env[env_key] = str(value)

                try:
                    for env_key, env_value in temp_env.items():
                        original_env[env_key] = os.getenv(env_key)
                        if env_value:
                            os.environ[env_key] = env_value

                    from app.services.data_sources.qmt_adapter import QMTAdapter

                    logger.info(
                        "QMT Test connection starts: data_dir=%s, init_markets=%s, start_local_service=%s",
                        temp_env.get("QMT_DATA_DIR", ""),
                        temp_env.get("QMT_INIT_MARKETS", ""),
                        temp_env.get("QMT_START_LOCAL_SERVICE", ""),
                    )

                    adapter = QMTAdapter()
                    available = await asyncio.wait_for(
                        asyncio.to_thread(adapter.is_available),
                        timeout=15.0,
                    )
                    if not available:
                        logger.warning("QMT Test connection failed: adapter.is_available() returned False")
                        return {
                            "success": False,
                            "message": "QMT Unavailable: Please confirm that xtquant has been installed, QMT has been started, and the local market connection parameters are correct",
                            "response_time": time.time() - start_time,
                            "details": {
                                "type": ds_type,
                                "tested_params": sorted(list((ds_config.config_params or {}).keys())),
                            }
                        }

                    return {
                        "success": True,
                        "message": "Successfully connected to QMT data source",
                        "response_time": time.time() - start_time,
                        "details": {
                            "type": ds_type,
                            "test_result": "QMT Available, local QMT connection detection passed",
                        }
                    }
                except asyncio.TimeoutError:
                    logger.error("QMT Test connection timeout: adapter.is_available() exceeded 15 seconds")
                    return {
                        "success": False,
                        "message": "QMT Test timeout: local connection detection exceeds 15 seconds, please check the current status of QMT and try again",
                        "response_time": time.time() - start_time,
                        "details": {
                            "type": ds_type,
                            "tested_params": sorted(list((ds_config.config_params or {}).keys())),
                        }
                    }
                except ImportError:
                    return {
                        "success": False,
                        "message": "xtquant The library is not installed. Please install it first and confirm that the operating environment supports it. QMT",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"QMT 测试失败: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                finally:
                    for env_key, env_value in original_env.items():
                        if env_value is None:
                            os.environ.pop(env_key, None)
                        else:
                            os.environ[env_key] = env_value

            elif ds_type == "local":
                # Local data source - directly connect to the database to check whether there is local data
                try:
                    from app.core.database import get_mongo_db
                    db = get_mongo_db()

                    # Check if there is local data (data_source = "local") 
                    # Check multiple collections
                    collections_to_check = [
                        ("stock_basic_info", "source"),  # Basic stock information
                        ("market_quotes", "data_source"),  # Real-time quotes
                        ("stock_financial_data", "data_source"),  # financial data
                        ("stock_news", "data_source")  # news data
                    ]

                    total_count = 0
                    collection_stats = []

                    for collection_name, field_name in collections_to_check:
                        collection = db[collection_name]
                        count = await collection.count_documents({field_name: "local"})
                        total_count += count
                        if count > 0:
                            collection_stats.append(f"{collection_name}: {count}条")

                    response_time = time.time() - start_time

                    if total_count > 0:
                        stats_msg = "、".join(collection_stats)
                        return {
                            "success": True,
                            "message": f"成功连接到本地数据源，共找到 {total_count} 条本地数据",
                            "response_time": response_time,
                            "details": {
                                "type": ds_type,
                                "test_result": f"The database connection is successful,{stats_msg}",
                                "total_records": total_count
                            }
                        }
                    else:
                        return {
                            "success": True,
                            "message": "Successfully connected to the local data source, but there is no local data yet (data can be imported through the batch import API interface)",
                            "response_time": response_time,
                            "details": {
                                "type": ds_type,
                                "test_result": "Database connection successful, no local data yet",
                                "total_records": 0
                            }
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"本地数据源连接失败: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif ds_type == "baostock":
                # BaoStock No API Key is required, just test login directly
                try:
                    import baostock as bs
                    # Test login
                    lg = bs.login()

                    if lg.error_code == '0':
                        # Log in successfully, test to obtain data
                        try:
                            # Get trading calendar (lightweight test)
                            rs = bs.query_trade_dates(start_date="2024-01-01", end_date="2024-01-01")

                            if rs.error_code == '0':
                                response_time = time.time() - start_time
                                bs.logout()
                                return {
                                    "success": True,
                                    "message": "Successfully connected to BaoStock data source",
                                    "response_time": response_time,
                                    "details": {
                                        "type": ds_type,
                                        "test_result": "Login successful, obtain trading calendar successfully"
                                    }
                                }
                            else:
                                bs.logout()
                                return {
                                    "success": False,
                                    "message": f"BaoStock Data acquisition failed: {rs.error_msg}",
                                    "response_time": time.time() - start_time,
                                    "details": None
                                }
                        except Exception as e:
                            bs.logout()
                            return {
                                "success": False,
                                "message": f"BaoStock Data acquisition exception: {str(e)}",
                                "response_time": time.time() - start_time,
                                "details": None
                            }
                    else:
                        return {
                            "success": False,
                            "message": f"BaoStock Login failed: {lg.error_msg}",
                            "response_time": time.time() - start_time,
                            "details": None
                        }
                except ImportError:
                    return {
                        "success": False,
                        "message": "BaoStock The library is not installed, please run: pip install baostock",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"BaoStock API call failed: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif ds_type == "yahoo_finance":
                # Yahoo Finance Testing - Proxy access required
                if not ds_config.endpoint:
                    ds_config.endpoint = "https://query1.finance.yahoo.com"

                try:
                    # Normalize the proxy address, ensuring there is a protocol prefix
                    def normalize_proxy(proxy: str) -> str:
                        if not proxy:
                            return proxy
                        proxy = proxy.strip()
                        if not proxy.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
                            proxy = f"http://{proxy}"
                        return proxy

                    # Get proxy configuration
                    system_config = await self.get_system_config()
                    proxies = {}
                    proxy_used = False
                    if system_config and system_config.system_settings:
                        http_proxy = system_config.system_settings.get('http_proxy', '')
                        https_proxy = system_config.system_settings.get('https_proxy', '')
                        if http_proxy:
                            proxies['http'] = normalize_proxy(http_proxy)
                            proxy_used = True
                        if https_proxy:
                            proxies['https'] = normalize_proxy(https_proxy)
                            proxy_used = True

                    # Also check environment variables
                    if not proxies:
                        env_http = os.environ.get('HTTP_PROXY', '')
                        env_https = os.environ.get('HTTPS_PROXY', '')
                        if env_http:
                            proxies['http'] = normalize_proxy(env_http)
                            proxy_used = True
                        if env_https:
                            proxies['https'] = normalize_proxy(env_https)
                            proxy_used = True

                    if not proxy_used:
                        logger.warning("⚠️ [TEST] Yahoo Finance The test does not configure a proxy and may not be accessible.")
                    else:
                        logger.info(f"🔍 [TEST] Yahoo Finance Use a proxy: {proxies}")

                    url = f"{ds_config.endpoint}/v8/finance/chart/AAPL"
                    params = {"interval": "1d", "range": "1d"}

                    # Add browser User-Agent to avoid being rejected by Yahoo Finance
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    }

                    response = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=15,
                        proxies=proxies if proxies else None
                    )

                    # Log response status and header information for debugging
                    logger.info(f"🔍 [TEST] Yahoo Finance response: status={response.status_code}, headers={dict(response.headers)}")

                    if response.status_code == 200:
                        data = response.json()
                        if "chart" in data and "result" in data["chart"]:
                            response_time = time.time() - start_time
                            proxy_msg = "（使用代理）" if proxy_used else "（直连）"
                            return {
                                "success": True,
                                "message": f"Successfully connected to Yahoo Finance data source{proxy_msg}",
                                "response_time": response_time,
                                "details": {
                                    "type": ds_type,
                                    "endpoint": ds_config.endpoint,
                                    "test_result": "获取 AAPL 数据成功",
                                    "proxy_used": proxy_used
                                }
                            }
                        elif "chart" in data and "error" in data["chart"]:
                            error_info = data["chart"]["error"]
                            return {
                                "success": False,
                                "message": f"Yahoo Finance API Error: {error_info.get('description', str(error_info))}",
                                "response_time": time.time() - start_time,
                                "details": None
                            }
                        else:
                            logger.warning(f"⚠️ [TEST] Yahoo Finance Return unknown format: {data}")
                            return {
                                "success": False,
                                "message": "Yahoo Finance API Return unknown format",
                                "response_time": time.time() - start_time,
                                "details": {"raw_response": str(data)[:500]}
                            }
                    elif response.status_code == 429:
                        # HTTP 429 It means that the proxy connection is successful, but the request frequency is limited.
                        proxy_msg = "（使用代理）" if proxy_used else "（直连）"
                        return {
                            "success": True,
                            "message": f"代理连接正常{proxy_msg}，但 Yahoo Finance 请求频率受限（HTTP 429），请稍后再试",
                            "response_time": time.time() - start_time,
                            "details": {
                                "type": ds_type,
                                "endpoint": ds_config.endpoint,
                                "test_result": "Proxy connection successful, API frequency limit",
                                "proxy_used": proxy_used,
                                "note": "HTTP 429 Indicates that the request is too frequent and will be automatically restored later."
                            }
                        }
                    else:
                        # Logging the response body for debugging
                        try:
                            response_body = response.text[:500]
                        except Exception:
                            response_body = "无法读取响应体"
                        logger.warning(f"⚠️ [TEST] Yahoo Finance error response: status={response.status_code}, body={response_body}")
                        return {
                            "success": False,
                            "message": f"Yahoo Finance API return error: HTTP {response.status_code}",
                            "response_time": time.time() - start_time,
                            "details": {
                                "status_code": response.status_code,
                                "response_body": response_body,
                                "proxy_used": proxy_used
                            }
                        }
                except requests.exceptions.ProxyError as e:
                    return {
                        "success": False,
                        "message": "Proxy connection failed, please check proxy configuration",
                        "response_time": time.time() - start_time,
                        "details": {"error": str(e)}
                    }
                except requests.exceptions.ConnectTimeout:
                    return {
                        "success": False,
                        "message": "Connection timed out, please check network or proxy configuration",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    error_msg = str(e)
                    if "ProxyError" in error_msg or "proxy" in error_msg.lower():
                        return {
                            "success": False,
                            "message": f"代理连接失败: {error_msg}",
                            "response_time": time.time() - start_time,
                            "details": None
                        }
                    return {
                        "success": False,
                        "message": f"Yahoo Finance API call failed: {error_msg}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif ds_type == "alpha_vantage":
                # 🔥 If the API Key in the configuration contains "..." (truncation mark), need to verify whether it is the unmodified original value
                if api_key and "..." in api_key:
                    logger.info("🔍 [TEST] API Key contains '...' (truncated), checking if it matches database value")

                    # Get complete from database API Key
                    system_config = await self.get_system_config()
                    db_config = None
                    if system_config:
                        for ds in system_config.data_source_configs:
                            if ds.name == ds_config.name:
                                db_config = ds
                                break

                    if db_config and db_config.api_key:
                        # Do the same truncation for the full API Key in the database
                        truncated_db_key = self._truncate_api_key(db_config.api_key)
                        logger.info(f"🔍 [TEST] Database API Key truncated: {truncated_db_key}")
                        logger.info(f"🔍 [TEST] Received API Key: {api_key}")

                        # Compare truncated values
                        if api_key == truncated_db_key:
                            # Same, indicating that the user has not modified it and uses the complete value in the database.
                            api_key = db_config.api_key
                            used_db_credentials = True
                            logger.info(f"✅ [TEST] Truncated values match, using complete API Key from database (length: {len(api_key)})")
                        else:
                            # Different, indicating that the user has modified it but the modification is incomplete.
                            logger.error("❌ [TEST] Truncated API Key doesn't match database value")
                            return {
                                "success": False,
                                "message": "API Key Format error: Truncation token detected but does not match value in database, please enter complete API Key",
                                "response_time": time.time() - start_time,
                                "details": {
                                    "error": "truncated_key_mismatch",
                                    "received": api_key,
                                    "expected": truncated_db_key
                                }
                            }
                    else:
                        # There is no valid API Key in the database, try to get it from environment variables
                        logger.info("⚠️  [TEST] No valid API Key in database, trying environment variable")
                        env_key = os.getenv('ALPHA_VANTAGE_API_KEY')
                        if env_key:
                            api_key = env_key.strip().strip('"').strip("'")
                            used_env_credentials = True
                            logger.info(f"🔑 [TEST] Using ALPHA_VANTAGE_API_KEY from environment (length: {len(api_key)})")
                        else:
                            logger.error("❌ [TEST] No valid API Key in database or environment")
                            return {
                                "success": False,
                                "message": "API Key Invalid: There is no valid configuration in the database or environment variables. API Key",
                                "response_time": time.time() - start_time,
                                "details": None
                            }

                # If the API Key is empty, try to get it from the database or environment variables
                elif not api_key:
                    logger.info("⚠️  [TEST] API Key is empty, trying to get from database")

                    # Get complete from database API Key
                    system_config = await self.get_system_config()
                    db_config = None
                    if system_config:
                        for ds in system_config.data_source_configs:
                            if ds.name == ds_config.name:
                                db_config = ds
                                break

                    if db_config and db_config.api_key and "..." not in db_config.api_key:
                        api_key = db_config.api_key
                        used_db_credentials = True
                        logger.info(f"🔑 [TEST] Using API Key from database (length: {len(api_key)})")
                    else:
                        # If it is not in the database, try to get it from environment variables
                        logger.info("⚠️  [TEST] No valid API Key in database, trying environment variable")
                        env_key = os.getenv('ALPHA_VANTAGE_API_KEY')
                        if env_key:
                            api_key = env_key.strip().strip('"').strip("'")
                            used_env_credentials = True
                            logger.info(f"🔑 [TEST] Using ALPHA_VANTAGE_API_KEY from environment (length: {len(api_key)})")
                        else:
                            logger.error("❌ [TEST] No valid API Key in config, database, or environment")
                            return {
                                "success": False,
                                "message": "API Key Invalid: There is no valid configuration in the configuration, database and environment variables. API Key",
                                "response_time": time.time() - start_time,
                                "details": None
                            }
                else:
                    # API Key is complete and can be used directly
                    logger.info(f"✅ [TEST] Using complete API Key from config (length: {len(api_key)})")

                # test Alpha Vantage API
                endpoint = ds_config.endpoint or "https://www.alphavantage.co"
                url = f"{endpoint}/query"
                params = {
                    "function": "TIME_SERIES_INTRADAY",
                    "symbol": "IBM",
                    "interval": "5min",
                    "apikey": api_key
                }

                try:
                    logger.info(f"🔌 [TEST] Calling Alpha Vantage API with key (length: {len(api_key)})")
                    response = requests.get(url, params=params, timeout=10)

                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"🔍 [TEST] Alpha Vantage API response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")

                        if "Time Series (5min)" in data or "Meta Data" in data:
                            response_time = time.time() - start_time
                            logger.info(f"✅ [TEST] Alpha Vantage API call successful (response time: {response_time:.2f}s)")

                            # Build a message stating which source of credentials was used
                            credential_source = "配置"
                            if used_db_credentials:
                                credential_source = "数据库"
                            elif used_env_credentials:
                                credential_source = "环境变量"

                            return {
                                "success": True,
                                "message": f"成功连接到 Alpha Vantage 数据源（使用{credential_source}中的凭证）",
                                "response_time": response_time,
                                "details": {
                                    "type": ds_type,
                                    "endpoint": endpoint,
                                    "test_result": "API 密钥有效",
                                    "credential_source": credential_source,
                                    "used_db_credentials": used_db_credentials,
                                    "used_env_credentials": used_env_credentials
                                }
                            }
                        elif "Error Message" in data:
                            return {
                                "success": False,
                                "message": f"Alpha Vantage API Error: {data['Error Message']}",
                                "response_time": time.time() - start_time,
                                "details": None
                            }
                        elif "Note" in data:
                            return {
                                "success": False,
                                "message": f"API 调用频率超限: {data['Note']}",
                                "response_time": time.time() - start_time,
                                "details": None
                            }
                        elif "Information" in data:
                            # Alpha Vantage The returned Information field usually contains API restriction information
                            info_msg = data["Information"]
                            if "premium" in info_msg.lower() or "limit" in info_msg.lower() or "call frequency" in info_msg.lower():
                                return {
                                    "success": False,
                                    "message": f"API 调用频率超限: {info_msg}",
                                    "response_time": time.time() - start_time,
                                    "details": None
                                }
                            else:
                                return {
                                    "success": False,
                                    "message": f"Alpha Vantage API information: {info_msg}",
                                    "response_time": time.time() - start_time,
                                    "details": None
                                }
                        else:
                            # Unknown response format, record details
                            logger.warning(f"⚠️ [TEST] Alpha Vantage Return unknown format: {data}")
                            return {
                                "success": False,
                                "message": f"Alpha Vantage API Return unknown format: {list(data.keys()) if isinstance(data, dict) else str(data)[:100]}",
                                "response_time": time.time() - start_time,
                                "details": {"raw_response": str(data)[:500]}
                            }
                    else:
                        return {
                            "success": False,
                            "message": f"Alpha Vantage API return error: HTTP {response.status_code}",
                            "response_time": time.time() - start_time,
                            "details": None
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Alpha Vantage API call failed: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            else:
                # Other data source types - try to get the API Key from environment variables (if needed)
                # Supported environment variable mappings
                env_key_map = {
                    "finnhub": "FINNHUB_API_KEY",
                    "polygon": "POLYGON_API_KEY",
                    "iex": "IEX_API_KEY",
                    "quandl": "QUANDL_API_KEY",
                }

                # If there is no API Key in the configuration, try to get it from the environment variable
                if ds_type in env_key_map and (not api_key or "..." in api_key):
                    env_var_name = env_key_map[ds_type]
                    env_key = os.getenv(env_var_name)
                    if env_key:
                        api_key = env_key.strip()
                        used_env_credentials = True
                        logger.info(f"🔑 使用环境变量中的 {ds_type.upper()} API Key ({env_var_name})")

                # Basic endpoint testing
                if ds_config.endpoint:
                    try:
                        # If there is an API Key, add it to the request
                        headers = {}
                        params = {}

                        if api_key:
                            # Add based on authentication methods of different data sources API Key
                            if ds_type == "finnhub":
                                params["token"] = api_key
                            elif ds_type in ["polygon", "alpha_vantage"]:
                                params["apiKey"] = api_key
                            elif ds_type == "iex":
                                params["token"] = api_key
                            else:
                                # Use header authentication by default
                                headers["Authorization"] = f"Bearer {api_key}"

                        response = requests.get(ds_config.endpoint, params=params, headers=headers, timeout=10)
                        response_time = time.time() - start_time

                        if response.status_code < 500:
                            return {
                                "success": True,
                                "message": f"成功连接到数据源 {ds_config.name}",
                                "response_time": response_time,
                                "details": {
                                    "type": ds_type,
                                    "endpoint": ds_config.endpoint,
                                    "status_code": response.status_code,
                                    "used_env_credentials": used_env_credentials
                                }
                            }
                        else:
                            return {
                                "success": False,
                                "message": f"Data source returns server error: HTTP {response.status_code}",
                                "response_time": response_time,
                                "details": None
                            }
                    except Exception as e:
                        return {
                            "success": False,
                            "message": f"连接失败: {str(e)}",
                            "response_time": time.time() - start_time,
                            "details": None
                        }
                else:
                    return {
                        "success": False,
                        "message": f"不支持的数据源类型: {ds_type}，且未配置端点",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"❌ 测试数据源配置失败: {e}")
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": response_time,
                "details": None
            }
    
    async def test_database_config(self, db_config: DatabaseConfig) -> Dict[str, Any]:
        """Test database configuration - real connection test"""
        start_time = time.time()
        try:
            db_type = db_config.type.value if hasattr(db_config.type, 'value') else str(db_config.type)

            logger.info(f"🧪 测试数据库配置: {db_config.name} ({db_type})")
            logger.info(f"📍 连接地址: {db_config.host}:{db_config.port}")

            # Test against different database types
            if db_type == "mongodb":
                try:
                    from motor.motor_asyncio import AsyncIOMotorClient
                    import os

                    # 🔥 Prioritize using the complete connection information in the environment variable (including host, username, password)
                    host = db_config.host
                    port = db_config.port
                    username = db_config.username
                    password = db_config.password
                    database = db_config.database
                    auth_source = None
                    used_env_config = False

                    # Detect whether you are in a Docker environment
                    is_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'

                    # If there is no username and password in the configuration, try to get the complete configuration from environment variables
                    if not username or not password:
                        env_host = os.getenv('MONGODB_HOST')
                        env_port = os.getenv('MONGODB_PORT')
                        env_username = os.getenv('MONGODB_USERNAME')
                        env_password = os.getenv('MONGODB_PASSWORD')
                        env_auth_source = os.getenv('MONGODB_AUTH_SOURCE', 'admin')

                        if env_username and env_password:
                            username = env_username
                            password = env_password
                            auth_source = env_auth_source
                            used_env_config = True

                            # If there is a host configuration in the environment variable, use it as well
                            if env_host:
                                host = env_host
                                # 🔥 Docker environment, replace localhost with mongodb
                                if is_docker and host == 'localhost':
                                    host = 'mongodb'
                                    logger.info("🐳 Docker environment detected, change host from localhost to mongodb")

                            if env_port:
                                port = int(env_port)

                            logger.info(f"🔑 Using MongoDB configuration in environment variables (host={host}, port={port}, authSource={auth_source})")

                    # If there is no database name in the configuration, try to get it from the environment variable
                    if not database:
                        env_database = os.getenv('MONGODB_DATABASE')
                        if env_database:
                            database = env_database
                            logger.info(f"📦 Use the database name from the environment variable: {database}")

                    # Get authSource from connection parameters (if any)
                    if not auth_source and db_config.connection_params:
                        auth_source = db_config.connection_params.get('authSource')

                    # Build connection string
                    if username and password:
                        connection_string = f"mongodb://{username}:{password}@{host}:{port}"
                    else:
                        connection_string = f"mongodb://{host}:{port}"

                    if database:
                        connection_string += f"/{database}"

                    # Add connection parameters
                    params_list = []

                    # If there is authSource, add it to the parameters
                    if auth_source:
                        params_list.append(f"authSource={auth_source}")

                    # Add additional connection parameters
                    if db_config.connection_params:
                        for k, v in db_config.connection_params.items():
                            if k != 'authSource':  # authSource Already added
                                params_list.append(f"{k}={v}")

                    if params_list:
                        connection_string += f"?{'&'.join(params_list)}"

                    logger.info(f"🔗 连接字符串: {connection_string.replace(password or '', '***') if password else connection_string}")

                    # Create client and test connection
                    client = AsyncIOMotorClient(
                        connection_string,
                        serverSelectionTimeoutMS=5000  # 5 seconds timeout
                    )

                    # If a database is specified, tests access to that database
                    if database:
                        # Test access to the specified database (no administrator privileges required)
                        db = client[database]
                        # Try to list the collection (will report an error if you don't have permission)
                        collections = await db.list_collection_names()
                        test_result = f"数据库 '{database}' 可访问，包含 {len(collections)} 个集合"
                    else:
                        # If no database is specified, just execute the ping command
                        await client.admin.command('ping')
                        test_result = "连接成功"

                    response_time = time.time() - start_time

                    # close connection
                    client.close()

                    return {
                        "success": True,
                        "message": "Successfully connected to MongoDB database",
                        "response_time": response_time,
                        "details": {
                            "type": db_type,
                            "host": host,
                            "port": port,
                            "database": database,
                            "auth_source": auth_source,
                            "test_result": test_result,
                            "used_env_config": used_env_config
                        }
                    }
                except ImportError:
                    return {
                        "success": False,
                        "message": "Motor The library is not installed, please run: pip install motor",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"❌ MongoDB Connection test failed: {error_msg}")

                    if "Authentication failed" in error_msg or "auth failed" in error_msg.lower():
                        message = "Authentication failed, please check username and password"
                    elif "requires authentication" in error_msg.lower():
                        message = "Authentication is required, please configure username and password"
                    elif "not authorized" in error_msg.lower():
                        message = "Insufficient permissions, please check user permission configuration"
                    elif "Connection refused" in error_msg:
                        message = "Connection refused, please check host address and port"
                    elif "timed out" in error_msg.lower():
                        message = "Connection timed out, please check network and firewall settings"
                    elif "No servers found" in error_msg:
                        message = "Server not found, please check host address and port"
                    else:
                        message = f"连接失败: {error_msg}"

                    return {
                        "success": False,
                        "message": message,
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif db_type == "redis":
                try:
                    import redis.asyncio as aioredis
                    import os

                    # 🔥 Prioritize using the complete Redis configuration in the environment variable (including host and password)
                    host = db_config.host
                    port = db_config.port
                    password = db_config.password
                    database = db_config.database
                    used_env_config = False

                    # Detect whether you are in a Docker environment
                    is_docker = os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER') == 'true'

                    # If there is no password in the configuration, try to get the full configuration from the environment variables
                    if not password:
                        env_host = os.getenv('REDIS_HOST')
                        env_port = os.getenv('REDIS_PORT')
                        env_password = os.getenv('REDIS_PASSWORD')

                        if env_password:
                            password = env_password
                            used_env_config = True

                            # If there is a host configuration in the environment variable, use it as well
                            if env_host:
                                host = env_host
                                # 🔥 Docker environment, replace localhost with redis
                                if is_docker and host == 'localhost':
                                    host = 'redis'
                                    logger.info("🐳 Docker environment detected, change Redis host from localhost to redis")

                            if env_port:
                                port = int(env_port)

                            logger.info(f"🔑 Using Redis configuration in environment variables (host={host}, port={port})")

                    # If there is no database number in the configuration, try to get it from the environment variable
                    if database is None:
                        env_db = os.getenv('REDIS_DB')
                        if env_db:
                            database = int(env_db)
                            logger.info(f"📦 Use the Redis database number from the environment variable: {database}")

                    # Build connection parameters
                    redis_params = {
                        "host": host,
                        "port": port,
                        "decode_responses": True,
                        "socket_connect_timeout": 5
                    }

                    if password:
                        redis_params["password"] = password

                    if database is not None:
                        redis_params["db"] = int(database)

                    # Create connection and test
                    redis_client = await aioredis.from_url(
                        f"redis://{host}:{port}",
                        **redis_params
                    )

                    # Execute PING command
                    await redis_client.ping()

                    # Get server information
                    info = await redis_client.info("server")

                    response_time = time.time() - start_time

                    # close connection
                    await redis_client.close()

                    return {
                        "success": True,
                        "message": "Successfully connected to Redis database",
                        "response_time": response_time,
                        "details": {
                            "type": db_type,
                            "host": host,
                            "port": port,
                            "database": database,
                            "redis_version": info.get("redis_version", "unknown"),
                            "used_env_config": used_env_config
                        }
                    }
                except ImportError:
                    return {
                        "success": False,
                        "message": "Redis The library is not installed, please run: pip install redis",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    error_msg = str(e)
                    if "WRONGPASS" in error_msg or "Authentication" in error_msg:
                        message = "Authentication failed, please check password"
                    elif "Connection refused" in error_msg:
                        message = "Connection refused, please check host address and port"
                    elif "timed out" in error_msg.lower():
                        message = "Connection timed out, please check network and firewall settings"
                    else:
                        message = f"连接失败: {error_msg}"

                    return {
                        "success": False,
                        "message": message,
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif db_type == "mysql":
                try:
                    import aiomysql

                    # Create connection
                    conn = await aiomysql.connect(
                        host=db_config.host,
                        port=db_config.port,
                        user=db_config.username,
                        password=db_config.password,
                        db=db_config.database,
                        connect_timeout=5
                    )

                    # Execute test query
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT VERSION()")
                        version = await cursor.fetchone()

                    response_time = time.time() - start_time

                    # close connection
                    conn.close()

                    return {
                        "success": True,
                        "message": "Successfully connected to MySQL database",
                        "response_time": response_time,
                        "details": {
                            "type": db_type,
                            "host": db_config.host,
                            "port": db_config.port,
                            "database": db_config.database,
                            "version": version[0] if version else "unknown"
                        }
                    }
                except ImportError:
                    return {
                        "success": False,
                        "message": "aiomysql The library is not installed, please run: pip install aiomysql",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    error_msg = str(e)
                    if "Access denied" in error_msg:
                        message = "Access Denied, please check username and password"
                    elif "Unknown database" in error_msg:
                        message = f"数据库 '{db_config.database}' 不存在"
                    elif "Can't connect" in error_msg:
                        message = "Unable to connect, please check host address and port"
                    else:
                        message = f"连接失败: {error_msg}"

                    return {
                        "success": False,
                        "message": message,
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif db_type == "postgresql":
                try:
                    import asyncpg

                    # Create connection
                    conn = await asyncpg.connect(
                        host=db_config.host,
                        port=db_config.port,
                        user=db_config.username,
                        password=db_config.password,
                        database=db_config.database,
                        timeout=5
                    )

                    # Execute test query
                    version = await conn.fetchval("SELECT version()")

                    response_time = time.time() - start_time

                    # close connection
                    await conn.close()

                    return {
                        "success": True,
                        "message": "Successfully connected to PostgreSQL database",
                        "response_time": response_time,
                        "details": {
                            "type": db_type,
                            "host": db_config.host,
                            "port": db_config.port,
                            "database": db_config.database,
                            "version": version.split()[1] if version else "unknown"
                        }
                    }
                except ImportError:
                    return {
                        "success": False,
                        "message": "asyncpg The library is not installed, please run: pip install asyncpg",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    error_msg = str(e)
                    if "password authentication failed" in error_msg:
                        message = "Password authentication failed, please check username and password"
                    elif "does not exist" in error_msg:
                        message = f"数据库 '{db_config.database}' 不存在"
                    elif "Connection refused" in error_msg:
                        message = "Connection refused, please check host address and port"
                    else:
                        message = f"连接失败: {error_msg}"

                    return {
                        "success": False,
                        "message": message,
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            elif db_type == "sqlite":
                try:
                    import aiosqlite

                    # SQLite Use file path, no need host/port
                    db_path = db_config.database or db_config.host

                    # Create connection
                    async with aiosqlite.connect(db_path, timeout=5) as conn:
                        # Execute test query
                        async with conn.execute("SELECT sqlite_version()") as cursor:
                            version = await cursor.fetchone()

                    response_time = time.time() - start_time

                    return {
                        "success": True,
                        "message": "Successfully connected to SQLite database",
                        "response_time": response_time,
                        "details": {
                            "type": db_type,
                            "database": db_path,
                            "version": version[0] if version else "unknown"
                        }
                    }
                except ImportError:
                    return {
                        "success": False,
                        "message": "aiosqlite The library is not installed, please run: pip install aiosqlite",
                        "response_time": time.time() - start_time,
                        "details": None
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"连接失败: {str(e)}",
                        "response_time": time.time() - start_time,
                        "details": None
                    }

            else:
                return {
                    "success": False,
                    "message": f"不支持的数据库类型: {db_type}",
                    "response_time": time.time() - start_time,
                    "details": None
                }

        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"❌ 测试数据库配置失败: {e}")
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": response_time,
                "details": None
            }

    # ========== Database configuration management ==========

    async def add_database_config(self, db_config: DatabaseConfig) -> bool:
        """添加数据库配置"""
        try:
            logger.info(f"➕ 添加数据库配置: {db_config.name}")

            config = await self.get_system_config()
            if not config:
                logger.error("❌ 系统配置为空")
                return False

            # Check if a configuration with the same name already exists
            for existing_db in config.database_configs:
                if existing_db.name == db_config.name:
                    logger.error(f"❌ 数据库配置 '{db_config.name}' 已存在")
                    return False

            # Add new configuration
            config.database_configs.append(db_config)

            # Save configuration
            result = await self.save_system_config(config)
            if result:
                logger.info(f"✅ 数据库配置 '{db_config.name}' 添加成功")
            else:
                logger.error(f"❌ 数据库配置 '{db_config.name}' 添加失败")

            return result

        except Exception as e:
            logger.error(f"❌ 添加数据库配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def update_database_config(self, db_config: DatabaseConfig) -> bool:
        """更新数据库配置"""
        try:
            logger.info(f"🔄 更新数据库配置: {db_config.name}")

            config = await self.get_system_config()
            if not config:
                logger.error("❌ 系统配置为空")
                return False

            # Find and update configuration
            found = False
            for i, existing_db in enumerate(config.database_configs):
                if existing_db.name == db_config.name:
                    config.database_configs[i] = db_config
                    found = True
                    break

            if not found:
                logger.error(f"❌ 数据库配置 '{db_config.name}' 不存在")
                return False

            # Save configuration
            result = await self.save_system_config(config)
            if result:
                logger.info(f"✅ 数据库配置 '{db_config.name}' 更新成功")
            else:
                logger.error(f"❌ 数据库配置 '{db_config.name}' 更新失败")

            return result

        except Exception as e:
            logger.error(f"❌ 更新数据库配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_database_config(self, db_name: str) -> bool:
        """删除数据库配置"""
        try:
            logger.info(f"🗑️ 删除数据库配置: {db_name}")

            config = await self.get_system_config()
            if not config:
                logger.error("❌ 系统配置为空")
                return False

            # record original quantity
            original_count = len(config.database_configs)

            # Delete specified configuration
            config.database_configs = [
                db for db in config.database_configs
                if db.name != db_name
            ]

            new_count = len(config.database_configs)

            if new_count == original_count:
                logger.error(f"❌ 数据库配置 '{db_name}' 不存在")
                return False

            # Save configuration
            result = await self.save_system_config(config)
            if result:
                logger.info(f"✅ 数据库配置 '{db_name}' 删除成功")
            else:
                logger.error(f"❌ 数据库配置 '{db_name}' 删除失败")

            return result

        except Exception as e:
            logger.error(f"❌ 删除数据库配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_database_config(self, db_name: str) -> Optional[DatabaseConfig]:
        """获取指定的数据库配置"""
        try:
            config = await self.get_system_config()
            if not config:
                return None

            for db in config.database_configs:
                if db.name == db_name:
                    return db

            return None

        except Exception as e:
            logger.error(f"❌ 获取数据库配置失败: {e}")
            return None

    async def get_database_configs(self) -> List[DatabaseConfig]:
        """获取所有数据库配置"""
        try:
            config = await self.get_system_config()
            if not config:
                return []

            return config.database_configs

        except Exception as e:
            logger.error(f"❌ Failed to obtain database configuration list: {e}")
            return []

    # ========== Model catalog management ==========

    async def get_model_catalog(self) -> List[ModelCatalog]:
        """获取所有模型目录"""
        try:
            db = await self._get_db()
            catalog_collection = db.model_catalog

            catalogs = []
            async for doc in catalog_collection.find():
                catalogs.append(ModelCatalog(**doc))

            return catalogs
        except Exception as e:
            print(f"获取模型目录失败: {e}")
            return []

    async def get_provider_models(self, provider: str) -> Optional[ModelCatalog]:
        """获取指定厂家的模型目录"""
        try:
            db = await self._get_db()
            catalog_collection = db.model_catalog

            doc = await catalog_collection.find_one({"provider": provider})
            if doc:
                return ModelCatalog(**doc)
            return None
        except Exception as e:
            print(f"获取厂家模型目录失败: {e}")
            return None

    async def save_model_catalog(self, catalog: ModelCatalog) -> bool:
        """保存或更新模型目录"""
        try:
            db = await self._get_db()
            catalog_collection = db.model_catalog

            catalog.updated_at = now_tz()

            # update or insert
            result = await catalog_collection.replace_one(
                {"provider": catalog.provider},
                catalog.model_dump(by_alias=True, exclude={"id"}),
                upsert=True
            )

            return result.acknowledged
        except Exception as e:
            print(f"保存模型目录失败: {e}")
            return False

    async def delete_model_catalog(self, provider: str, cleanup_configs: bool = True) -> bool:
        """Delete model directory

        Args:
            provider: Manufacturer name
            cleanup_configs: Whether to also clean up large model configurations that reference the manufacturer s model (default True)

        Returns:
            bool: Is deletion successful?
        """
        try:
            logger.info(f"🗑️ 删除模型目录: {provider}, cleanup_configs={cleanup_configs}")

            db = await self._get_db()
            catalog_collection = db.model_catalog

            # 🔥 If you need to clean up the configuration, first delete all large model configurations that reference the manufacturer.
            if cleanup_configs:
                config = await self.get_system_config()
                if config:
                    original_count = len(config.llm_configs)

                    # Filter out all configurations of this manufacturer
                    config.llm_configs = [
                        llm for llm in config.llm_configs
                        if str(llm.provider.value if hasattr(llm.provider, 'value') else llm.provider).lower() != provider.lower()
                    ]

                    removed_count = original_count - len(config.llm_configs)
                    if removed_count > 0:
                        logger.info(f"🧹 清理了 {removed_count} 个引用 {provider} 的大模型配置")
                        await self.save_system_config(config)

            # Delete model directory
            result = await catalog_collection.delete_one({"provider": provider})

            if result.deleted_count > 0:
                logger.info(f"✅ 模型目录删除成功: {provider}")
                return True
            else:
                logger.warning(f"⚠️ 未找到模型目录: {provider}")
                return False

        except Exception as e:
            logger.error(f"❌ 删除模型目录失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def init_default_model_catalog(self) -> bool:
        """初始化默认模型目录"""
        try:
            db = await self._get_db()
            catalog_collection = db.model_catalog

            # Check if data already exists
            count = await catalog_collection.count_documents({})
            if count > 0:
                print("The model directory already exists, skip initialization")
                return True

            # Create default directory
            default_catalogs = self._get_default_model_catalog()

            for catalog_data in default_catalogs:
                catalog = ModelCatalog(**catalog_data)
                await self.save_model_catalog(catalog)

            print(f"✅ 初始化了 {len(default_catalogs)} 个厂家的模型目录")
            return True
        except Exception as e:
            print(f"初始化模型目录失败: {e}")
            return False

    def _get_default_model_catalog(self) -> List[Dict[str, Any]]:
        """获取默认模型目录数据"""
        return [
            {
                "provider": "dashscope",
                "provider_name": "通义千问",
                "models": [
                    {
                        "name": "qwen-turbo",
                        "display_name": "Qwen Turbo - Fast and economical (1M context)",
                        "input_price_per_1k": 0.0003,
                        "output_price_per_1k": 0.0003,
                        "context_length": 1000000,
                        "currency": "CNY",
                        "description": "Qwen2.5-Turbo, Supports 1 million tokens ultra-long context"
                    },
                    {
                        "name": "qwen-plus",
                        "display_name": "Qwen Plus - Balanced recommendation",
                        "input_price_per_1k": 0.0008,
                        "output_price_per_1k": 0.002,
                        "context_length": 32768,
                        "currency": "CNY"
                    },
                    {
                        "name": "qwen-plus-latest",
                        "display_name": "Qwen Plus Latest - latest balance",
                        "input_price_per_1k": 0.0008,
                        "output_price_per_1k": 0.002,
                        "context_length": 32768,
                        "currency": "CNY"
                    },
                    {
                        "name": "qwen-max",
                        "display_name": "Qwen Max - Maximum performance",
                        "input_price_per_1k": 0.02,
                        "output_price_per_1k": 0.06,
                        "context_length": 8192,
                        "currency": "CNY"
                    },
                    {
                        "name": "qwen-max-latest",
                        "display_name": "Qwen Max Latest - latest flagship",
                        "input_price_per_1k": 0.02,
                        "output_price_per_1k": 0.06,
                        "context_length": 8192,
                        "currency": "CNY"
                    },
                    {
                        "name": "qwen-long",
                        "display_name": "Qwen Long - long text",
                        "input_price_per_1k": 0.0005,
                        "output_price_per_1k": 0.002,
                        "context_length": 1000000,
                        "currency": "CNY"
                    },
                    {
                        "name": "qwen-vl-plus",
                        "display_name": "Qwen VL Plus - visual understanding",
                        "input_price_per_1k": 0.008,
                        "output_price_per_1k": 0.008,
                        "context_length": 8192,
                        "currency": "CNY"
                    },
                    {
                        "name": "qwen-vl-max",
                        "display_name": "Qwen VL Max - Visual flagship",
                        "input_price_per_1k": 0.02,
                        "output_price_per_1k": 0.02,
                        "context_length": 8192,
                        "currency": "CNY"
                    }
                ]
            },
            {
                "provider": "openai",
                "provider_name": "OpenAI",
                "models": [
                    {
                        "name": "gpt-4o",
                        "display_name": "GPT-4o - latest flagship",
                        "input_price_per_1k": 0.005,
                        "output_price_per_1k": 0.015,
                        "context_length": 128000,
                        "currency": "USD"
                    },
                    {
                        "name": "gpt-4o-mini",
                        "display_name": "GPT-4o Mini - lightweight flagship",
                        "input_price_per_1k": 0.00015,
                        "output_price_per_1k": 0.0006,
                        "context_length": 128000,
                        "currency": "USD"
                    },
                    {
                        "name": "gpt-4-turbo",
                        "display_name": "GPT-4 Turbo - Enhanced version",
                        "input_price_per_1k": 0.01,
                        "output_price_per_1k": 0.03,
                        "context_length": 128000,
                        "currency": "USD"
                    },
                    {
                        "name": "gpt-4",
                        "display_name": "GPT-4 - 经典版",
                        "input_price_per_1k": 0.03,
                        "output_price_per_1k": 0.06,
                        "context_length": 8192,
                        "currency": "USD"
                    },
                    {
                        "name": "gpt-3.5-turbo",
                        "display_name": "GPT-3.5 Turbo - Economy version",
                        "input_price_per_1k": 0.0005,
                        "output_price_per_1k": 0.0015,
                        "context_length": 16385,
                        "currency": "USD"
                    }
                ]
            },
            {
                "provider": "google",
                "provider_name": "Google Gemini",
                "models": [
                    {
                        "name": "gemini-2.5-pro",
                        "display_name": "Gemini 2.5 Pro - latest flagship",
                        "input_price_per_1k": 0.00125,
                        "output_price_per_1k": 0.005,
                        "context_length": 1000000,
                        "currency": "USD"
                    },
                    {
                        "name": "gemini-2.5-flash",
                        "display_name": "Gemini 2.5 Flash - Latest and fast",
                        "input_price_per_1k": 0.000075,
                        "output_price_per_1k": 0.0003,
                        "context_length": 1000000,
                        "currency": "USD"
                    },
                    {
                        "name": "gemini-1.5-pro",
                        "display_name": "Gemini 1.5 Pro - Professional version",
                        "input_price_per_1k": 0.00125,
                        "output_price_per_1k": 0.005,
                        "context_length": 2000000,
                        "currency": "USD"
                    },
                    {
                        "name": "gemini-1.5-flash",
                        "display_name": "Gemini 1.5 Flash - Express version",
                        "input_price_per_1k": 0.000075,
                        "output_price_per_1k": 0.0003,
                        "context_length": 1000000,
                        "currency": "USD"
                    }
                ]
            },
            {
                "provider": "deepseek",
                "provider_name": "DeepSeek",
                "models": [
                    {
                        "name": "deepseek-chat",
                        "display_name": "DeepSeek Chat - general conversation",
                        "input_price_per_1k": 0.0001,
                        "output_price_per_1k": 0.0002,
                        "context_length": 32768,
                        "currency": "CNY"
                    },
                    {
                        "name": "deepseek-coder",
                        "display_name": "DeepSeek Coder - Code only",
                        "input_price_per_1k": 0.0001,
                        "output_price_per_1k": 0.0002,
                        "context_length": 16384,
                        "currency": "CNY"
                    }
                ]
            },
            {
                "provider": "anthropic",
                "provider_name": "Anthropic Claude",
                "models": [
                    {
                        "name": "claude-3-5-sonnet-20241022",
                        "display_name": "Claude 3.5 Sonnet - current flagship",
                        "input_price_per_1k": 0.003,
                        "output_price_per_1k": 0.015,
                        "context_length": 200000,
                        "currency": "USD"
                    },
                    {
                        "name": "claude-3-5-sonnet-20240620",
                        "display_name": "Claude 3.5 Sonnet (Old version)",
                        "input_price_per_1k": 0.003,
                        "output_price_per_1k": 0.015,
                        "context_length": 200000,
                        "currency": "USD"
                    },
                    {
                        "name": "claude-3-opus-20240229",
                        "display_name": "Claude 3 Opus - Powerful performance",
                        "input_price_per_1k": 0.015,
                        "output_price_per_1k": 0.075,
                        "context_length": 200000,
                        "currency": "USD"
                    },
                    {
                        "name": "claude-3-sonnet-20240229",
                        "display_name": "Claude 3 Sonnet - Balanced version",
                        "input_price_per_1k": 0.003,
                        "output_price_per_1k": 0.015,
                        "context_length": 200000,
                        "currency": "USD"
                    },
                    {
                        "name": "claude-3-haiku-20240307",
                        "display_name": "Claude 3 Haiku - Express version",
                        "input_price_per_1k": 0.00025,
                        "output_price_per_1k": 0.00125,
                        "context_length": 200000,
                        "currency": "USD"
                    }
                ]
            },
            {
                "provider": "qianfan",
                "provider_name": "百度千帆",
                "models": [
                    {
                        "name": "ernie-3.5-8k",
                        "display_name": "ERNIE 3.5 8K - Fast and efficient",
                        "input_price_per_1k": 0.0012,
                        "output_price_per_1k": 0.0012,
                        "context_length": 8192,
                        "currency": "CNY"
                    },
                    {
                        "name": "ernie-4.0-turbo-8k",
                        "display_name": "ERNIE 4.0 Turbo 8K - Strong reasoning",
                        "input_price_per_1k": 0.03,
                        "output_price_per_1k": 0.09,
                        "context_length": 8192,
                        "currency": "CNY"
                    },
                    {
                        "name": "ERNIE-Speed-8K",
                        "display_name": "ERNIE Speed 8K - Extremely fast response",
                        "input_price_per_1k": 0.0004,
                        "output_price_per_1k": 0.0004,
                        "context_length": 8192,
                        "currency": "CNY"
                    },
                    {
                        "name": "ERNIE-Lite-8K",
                        "display_name": "ERNIE Lite 8K - Lightweight and economical",
                        "input_price_per_1k": 0.0003,
                        "output_price_per_1k": 0.0006,
                        "context_length": 8192,
                        "currency": "CNY"
                    }
                ]
            },
            {
                "provider": "zhipu",
                "provider_name": "智谱AI",
                "models": [
                    {
                        "name": "glm-4",
                        "display_name": "GLM-4 - 旗舰版",
                        "input_price_per_1k": 0.1,
                        "output_price_per_1k": 0.1,
                        "context_length": 128000,
                        "currency": "CNY"
                    },
                    {
                        "name": "glm-4-plus",
                        "display_name": "GLM-4 Plus - Enhanced version",
                        "input_price_per_1k": 0.05,
                        "output_price_per_1k": 0.05,
                        "context_length": 128000,
                        "currency": "CNY"
                    },
                    {
                        "name": "glm-3-turbo",
                        "display_name": "GLM-3 Turbo - Express version",
                        "input_price_per_1k": 0.001,
                        "output_price_per_1k": 0.001,
                        "context_length": 128000,
                        "currency": "CNY"
                    }
                ]
            }
        ]

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get the list of available models (read from database, return default data if empty)"""
        try:
            catalogs = await self.get_model_catalog()

            # If there is no data in the database, initialize the default directory
            if not catalogs:
                print("📦 The model directory is empty, initialize the default directory...")
                await self.init_default_model_catalog()
                catalogs = await self.get_model_catalog()

            # Convert to API response format
            result = []
            for catalog in catalogs:
                result.append({
                    "provider": catalog.provider,
                    "provider_name": catalog.provider_name,
                    "models": [
                        {
                            "name": model.name,
                            "display_name": model.display_name,
                            "description": model.description,
                            "context_length": model.context_length,
                            "input_price_per_1k": model.input_price_per_1k,
                            "output_price_per_1k": model.output_price_per_1k,
                            "is_deprecated": model.is_deprecated
                        }
                        for model in catalog.models
                    ]
                })

            return result
        except Exception as e:
            print(f"获取模型列表失败: {e}")
            # Returns default data on failure
            return self._get_default_model_catalog()


    async def set_default_llm(self, model_name: str) -> bool:
        """设置默认大模型"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # Check if the model exists
            model_exists = any(
                llm.model_name == model_name
                for llm in config.llm_configs
            )

            if not model_exists:
                return False

            config.default_llm = model_name
            return await self.save_system_config(config)
        except Exception as e:
            print(f"设置默认LLM失败: {e}")
            return False

    async def set_default_data_source(self, source_name: str) -> bool:
        """设置默认数据源"""
        try:
            config = await self.get_system_config()
            if not config:
                return False

            # Check if the data source exists
            source_exists = any(
                ds.name == source_name
                for ds in config.data_source_configs
            )

            if not source_exists:
                return False

            config.default_data_source = source_name
            return await self.save_system_config(config)
        except Exception as e:
            print(f"设置默认数据源失败: {e}")
            return False

    # ========== Large model manufacturer management ==========

    async def get_llm_providers(self) -> List[LLMProvider]:
        """Get all large model manufacturers (merge environment variable configuration)"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            providers_data = await providers_collection.find().sort({"_id": -1}).to_list(length=None)
            providers = []

            logger.info(f"🔍 [get_llm_providers] 从数据库获取到 {len(providers_data)} 个供应商")

            # 🔥 Local model list (no API Key required)
            local_models = ["ollama", "localai"]
            
            for provider_data in providers_data:
                provider = LLMProvider(**provider_data)

                # initialization extra_config
                provider.extra_config = provider.extra_config or {}

                # 🔥 Local models do not require API Key, skip checking
                if provider.name.lower() in local_models:
                    provider.extra_config["has_api_key"] = True
                    provider.extra_config["source"] = "local_model"
                    provider.extra_config["api_key_required"] = False
                    logger.info(f"✅ [get_llm_providers] 本地模型 {provider.display_name} 不需要 API Key")
                else:
                    # 🔥 Determine whether the API Key in the database is valid
                    db_key_valid = self._is_valid_api_key(provider.api_key)
                    logger.info(f"🔍 [get_llm_providers] 供应商 {provider.display_name} ({provider.name}): 数据库密钥有效={db_key_valid}")

                    if not db_key_valid:
                        # The Key in the database is invalid, try to get it from environment variables
                        logger.info(f"🔍 [get_llm_providers] 尝试从环境变量获取 {provider.name} 的 API 密钥...")
                        env_key = self._get_env_api_key(provider.name)
                        if env_key:
                            provider.api_key = env_key
                            provider.extra_config["source"] = "environment"
                            provider.extra_config["has_api_key"] = True
                            logger.info(f"✅ [get_llm_providers] 从环境变量为厂家 {provider.display_name} 获取API密钥")
                        else:
                            provider.extra_config["has_api_key"] = False
                            logger.warning(f"⚠️ [get_llm_providers] Manufacturer {provider.display_name} Neither the database configuration nor the environment variables are configured with a valid API key")
                    else:
                        # The Key in the database is valid, use database configuration
                        provider.extra_config["source"] = "database"
                        provider.extra_config["has_api_key"] = True
                        logger.info(f"✅ [get_llm_providers] 使用数据库配置的 {provider.display_name} API密钥")

                providers.append(provider)

            logger.info(f"🔍 [get_llm_providers] 返回 {len(providers)} 个供应商")
            return providers
        except Exception as e:
            logger.error(f"❌ [get_llm_providers] Failed to obtain manufacturer list: {e}", exc_info=True)
            return []

    async def get_embedding_providers(self) -> List[Dict[str, Any]]:
        """Get a list of all manufacturers and models that support embedding"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers
            
            # Check for vendors that support embedding
            providers_data = await providers_collection.find({
                "supported_features": "embedding",  # 🔥 direct match, avoid $in Returns empty results on some MongoDB versions
                "is_active": True
            }).sort("priority", 1).to_list(length=None)
            
            result = []
            for provider_data in providers_data:
                provider_name = provider_data.get("name", "")
                display_name = provider_data.get("display_name", provider_name)
                embedding_model = provider_data.get("embedding_model", "")
                
                # If embedding_model is configured, use the configured model
                if embedding_model:
                    models = [embedding_model]
                else:
                    # Otherwise use the default model list
                    default_models: Dict[str, List[str]] = {
                        "dashscope": ["text-embedding-v3", "text-embedding-v2"],
                        "openai": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
                        "deepseek": ["text-embedding-v3"],
                        "google": ["text-embedding-004", "text-embedding-003"],
                        "qianfan": ["bge-large-zh-v1.5", "bge-base-zh-v1.5"]
                    }
                    models = default_models.get(provider_name, [])
                
                # Only manufacturers with models are returned
                if models:
                    result.append({
                        "name": provider_name,
                        "display_name": display_name,
                        "models": models
                    })

            logger.info(f"✅ [get_embedding_providers] Return {len(result)} manufacturers that support embedding")
            return result
        except Exception as e:
            logger.error(f"❌ [get_embedding_providers] Failed to obtain Embedding manufacturer list: {e}", exc_info=True)
            return []

    async def _get_current_embedding_model(self) -> str:
        """Get the embedding model identifier of the current system configuration (such as dashscope:text-embedding-v4) """
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            # Get activated configurations first
            configs = list(db.system_configs.find(
                {"config_type": "system", "is_active": True},
                sort=[("version", -1)]
            ).limit(1))
            if configs:
                return configs[0].get("system_settings", {}).get("default_embedding_model", "")
        except Exception:
            pass
        return os.environ.get("DEFAULT_EMBEDDING_MODEL", "")

    async def _get_migration_records(self) -> Dict[str, Dict[str, Any]]:
        """Read migrated collection records from MongoDB
        
        Returns:
            {collection_name: {model_used: "dashscope:text-embedding-v4", migrated_at: "..."}}
        """
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            records = {}
            for doc in db.system_configs.find({"config_key": {"$regex": "^qdrant_migration_"}}):
                col_name = doc["config_key"].replace("qdrant_migration_", "")
                records[col_name] = doc.get("config_value", {})
            return records
        except Exception:
            return {}

    async def _save_migration_record(self, collection_name: str, model_used: str):
        """Save migration records to MongoDB"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            db.system_configs.update_one(
                {"config_key": f"qdrant_migration_{collection_name}"},
                {"$set": {
                    "config_key": f"qdrant_migration_{collection_name}",
                    "config_type": "system",
                    "config_value": {
                        "model_used": model_used,
                        "migrated_at": datetime.utcnow().isoformat(),
                    },
                    "updated_at": datetime.utcnow(),
                }},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"⚠️ 保存迁移记录失败: {e}")

    async def get_qdrant_collections(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all collection information in Qdrant (main storage + mem0) , for migration selection
        
        Returns data grouped by storage region, including migration status flags, without initializing the embedder.
        """
        result = {"main": [], "mem0": []}
        try:
            # Get the current embedding model and migration records
            current_model = await self._get_current_embedding_model()
            migration_records = await self._get_migration_records()

            def _migration_status(col_name: str, source: str) -> str:
                """判断迁移状态"""
                record = migration_records.get(col_name)
                if not record:
                    return "pending"
                if record.get("model_used") == current_model:
                    return "migrated"
                return "outdated"

            # 1. main storage — Reuse the existing client of the QdrantAdapter singleton to avoid lock conflicts
            try:
                from core.memory.qdrant_adapter import QdrantAdapter
                adapter = QdrantAdapter()
                for col in adapter.list_collections():
                    result["main"].append({
                        "name": col["name"],
                        "point_count": col["point_count"],
                        "dimensions": col["dimensions"],
                        "source": "main",
                        "migration_status": _migration_status(col["name"], "main"),
                        "current_model": current_model,
                        "last_migration": migration_records.get(col["name"], {}).get("migrated_at") or None,
                    })
                result["main"] = sorted(result["main"], key=lambda x: x["name"])
                logger.info(f"✅ [get_qdrant_collections] 主存储: {len(result['main'])} 个 collection")
            except Exception as e:
                logger.warning(f"⚠️ [get_qdrant_collections] Main storage read failed: {e}")

            # 2. mem0 storage
            try:
                from qdrant_client import QdrantClient
                qdrant_base = os.environ.get("QDRANT_DATA_DIR", "./data/qdrant")
                mem0_path = os.path.join(os.path.abspath(qdrant_base), "mem0")
                if os.path.exists(mem0_path):
                    mem0_client = QdrantClient(path=mem0_path)
                    for col in mem0_client.get_collections().collections:
                        if not col.name.startswith("mem0_memories"):
                            continue
                        info = mem0_client.get_collection(col.name)
                        result["mem0"].append({
                            "name": col.name,
                            "point_count": info.points_count or 0,
                            "dimensions": info.config.params.vectors.size if info.config.params.vectors else 0,
                            "source": "mem0",
                            "migration_status": _migration_status(col.name, "mem0"),
                            "current_model": current_model,
                            "last_migration": migration_records.get(col.name, {}).get("migrated_at") or None,
                        })
                    mem0_client.close()
                    result["mem0"] = sorted(result["mem0"], key=lambda x: x["name"])
                    logger.info(f"✅ [get_qdrant_collections] mem0 存储: {len(result['mem0'])} 个 collection")
            except Exception as e:
                logger.warning(f"⚠️ [get_qdrant_collections] mem0 Storage read failed: {e}")

            return result
        except Exception as e:
            logger.error(f"❌ [get_qdrant_collections] Failed to get collection list: {e}", exc_info=True)
            return {"main": [], "mem0": []}

    async def get_mem0_collections(self) -> List[Dict[str, Any]]:
        """[Compatible with old interfaces] Get all mem0 related collection information in Qdrant"""
        data = await self.get_qdrant_collections()
        return data.get("mem0", [])

    async def delete_qdrant_collection(self, collection_name: str, source: str = "main", force: bool = False) -> Dict[str, Any]:
        """Delete Qdrant collection
        
        Args:
            collection_name: collection Name
            source: "main" or "mem0"
            force: Whether to force deletion (skip points and security checks)
        """
        if not collection_name:
            raise ValueError("collection Name cannot be empty")

        try:
            from qdrant_client import QdrantClient
            from core.memory.qdrant_adapter import QdrantAdapter

            qdrant_base = os.environ.get("QDRANT_DATA_DIR", "./data/qdrant")

            if source == "mem0":
                client = QdrantClient(path=os.path.join(os.path.abspath(qdrant_base), "mem0"))
            else:
                # Main storage, reuse singleton client
                client = QdrantAdapter().get_raw_client()

            # Check if exists
            existing = {col.name for col in client.get_collections().collections}
            if collection_name not in existing:
                if source == "mem0":
                    client.close()
                raise RuntimeError(f"collection does not exist: {collection_name}")

            # Security verification: Check whether it is empty in non-forced mode
            if not force:
                info = client.get_collection(collection_name)
                if (info.points_count or 0) > 0:
                    if source == "mem0":
                        client.close()
                    raise RuntimeError(
                        f"collection {collection_name} 包含 {info.points_count} 条数据，"
                        f"Please migrate or use first force=true force delete"
                    )

            client.delete_collection(collection_name)
            if source == "mem0":
                client.close()

            logger.info(f"🗑️ [delete_qdrant_collection] Deleted collection: {collection_name} (source={source})")
            return {"success": True, "message": f"已删除 {collection_name}"}
        except Exception as e:
            logger.error(f"❌ [delete_qdrant_collection] Delete failed: {e}", exc_info=True)
            raise

    async def migrate_qdrant_collection(self, collection_name: str, dry_run: bool = False) -> Dict[str, Any]:
        """Re-encode the collection vector in main storage using the current embedding model (migrate in place)
        
        Args:
            collection_name: collection Name (such as memory_bull_researcher_v2)
            dry_run: Whether to only preview and not execute
        """
        if not collection_name:
            raise ValueError("collection Name cannot be empty")

        try:
            from qdrant_client.models import PointStruct
            from core.llm.embedding_manager import EmbeddingManager
            from core.memory.qdrant_adapter import QdrantAdapter

            # Reuse existing client of QdrantAdapter singleton
            adapter = QdrantAdapter()
            client = adapter.get_raw_client()

            # Check if collection exists
            existing = {col.name for col in client.get_collections().collections}
            if collection_name not in existing:
                raise RuntimeError(f"collection does not exist: {collection_name}")

            info = client.get_collection(collection_name)
            target_dims = info.config.params.vectors.size if info.config.params.vectors else 0

            # Get current embedding manager
            embed_manager = EmbeddingManager()

            logger.info(
                f"🔄 [Primary storage migration] collection={collection_name} dims={target_dims} dry_run={dry_run}"
            )

            batch_size = 10
            total_seen = 0
            total_migrated = 0
            total_skipped = 0

            if not dry_run:
                offset = None
                while True:
                    points, offset = client.scroll(
                        collection_name=collection_name,
                        limit=batch_size,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    if not points:
                        break

                    to_upsert = []
                    for point in points:
                        payload = dict(point.payload or {})
                        # Extract text content for recoding
                        text = str(payload.get("document") or payload.get("content") or "").strip()
                        if not text:
                            total_skipped += 1
                            continue

                        embedding, provider = embed_manager.get_embedding(text)
                        if embedding is None:
                            total_skipped += 1
                            continue

                        to_upsert.append(PointStruct(id=point.id, vector=embedding, payload=payload))

                    if to_upsert:
                        client.upsert(collection_name=collection_name, points=to_upsert)

                    total_seen += len(points)
                    total_migrated += len(to_upsert)
                    logger.info(
                        f"  批次: 已处理={total_seen}, 已迁移={total_migrated}, 已跳过={total_skipped}"
                    )

                    if offset is None:
                        break
            else:
                # dry_run: Only statistics
                offset = None
                while True:
                    points, offset = client.scroll(
                        collection_name=collection_name,
                        limit=batch_size,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    if not points:
                        break
                    for point in points:
                        payload = dict(point.payload or {})
                        text = str(payload.get("document") or payload.get("content") or "").strip()
                        if text:
                            total_migrated += 1
                        else:
                            total_skipped += 1
                    total_seen += len(points)
                    if offset is None:
                        break

            result = {
                "success": True,
                "collection_name": collection_name,
                "total_seen": total_seen,
                "migrated": total_migrated,
                "skipped": total_skipped,
                "dry_run": dry_run,
            }

            # Record status after successful migration
            if not dry_run and total_migrated > 0:
                current_model = await self._get_current_embedding_model()
                await self._save_migration_record(collection_name, current_model)
                result["model_used"] = current_model

            logger.info(f"✅ [Primary storage migration] Complete: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ [Primary storage migration] failed: {e}", exc_info=True)
            raise

    async def migrate_mem0_collection(self, source_collection: str, dry_run: bool = False) -> Dict[str, Any]:
        """Migrate data from the old Qdrant mem0 collection to MongoDB (vector storage has been migrated from Qdrant to MongoDB)

        Read all points (including payload + vector) , Write directly to the MongoDB collection with the same name,
        Document format and mongodb_vector_adapter.add() consistent.
        """
        if not source_collection or not source_collection.startswith("mem0_memories"):
            raise ValueError("Source collection name must start with mem0_memories")

        try:
            import sys
            # Qdrant pickle Deserialization requires the core module in path
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from qdrant_client import QdrantClient
            from pymongo import UpdateOne
            from app.core.database import get_mongo_db_sync

            qdrant_base = os.environ.get("QDRANT_DATA_DIR", "./data/qdrant")
            mem0_path = os.path.join(qdrant_base, "mem0")
            client = QdrantClient(path=mem0_path)

            # Check if Qdrant source exists
            qdrant_collections = {col.name for col in client.get_collections().collections}
            if source_collection not in qdrant_collections:
                client.close()
                raise RuntimeError(f"Qdrant source does not exist in collection: {source_collection}")

            source_count = client.count(source_collection).count
            logger.info(f"🔄 Qdrant->MongoDB Migration starts: {source_collection} ({source_count} points), dry_run={dry_run}")

            mongo_db = get_mongo_db_sync()
            mongo_col = mongo_db[source_collection]

            batch_size = 100
            total_migrated = 0
            total_skipped = 0
            offset = None

            while True:
                points, offset = client.scroll(
                    collection_name=source_collection,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                if not points:
                    break

                operations = []
                for point in points:
                    doc_id = str(point.id)
                    vector = point.vector
                    # Handling the case of named vector
                    if isinstance(vector, dict):
                        vector = list(vector.values())[0] if vector else []
                    elif not isinstance(vector, list):
                        vector = list(vector) if vector else []

                    payload = point.payload or {}
                    doc = {
                        "embedding": vector,
                        "document": payload.get("document", payload.get("page_content", payload.get("data", ""))),
                    }
                    # Tile the payload field to the top of the document
                    for k, v in payload.items():
                        if k not in ("document", "page_content"):
                            doc[k] = v
                    if not doc.get("document") and payload.get("page_content"):
                        doc["document"] = payload["page_content"]

                    operations.append(
                        UpdateOne(
                            {"_id": doc_id},
                            {"$set": doc},
                            upsert=True,
                        )
                    )

                if not dry_run and operations:
                    result = mongo_col.bulk_write(operations, ordered=False)
                    total_migrated += len(points)
                    logger.info(
                        f"  批次: 已处理={total_migrated}/{source_count}, "
                        f"upserted={result.upserted_count}, modified={result.modified_count}"
                    )
                else:
                    total_migrated += len(points)

                if offset is None:
                    break

            client.close()

            # Verify
            mongo_count = mongo_col.count_documents({}) if not dry_run else 0

            result = {
                "success": True,
                "source_collection": source_collection,
                "target": "mongodb",
                "source_count": source_count,
                "migrated": total_migrated,
                "skipped": total_skipped,
                "mongo_count": mongo_count,
                "dry_run": dry_run,
            }
            logger.info(f"✅ Qdrant->MongoDB Migration completed: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ 迁移失败: {e}", exc_info=True)
            raise

    def _is_valid_api_key(self, api_key: Optional[str]) -> bool:
        """
        Determine whether the API Key is valid

        Valid conditions:
        1. Key Not empty
        2. Key is not a placeholder (does not end with 'your_' or 'your-' does not begin with '_here' end)
        3. Key is not a truncated key (does not contain '...') 
        4. Key length > 10 (Basic format validation)

        Args:
            api_key: To be verified API Key

        Returns:
            bool: True means valid, False means invalid
        """
        if not api_key:
            return False

        # Remove leading and trailing spaces
        api_key = api_key.strip()

        # Check if it is empty
        if not api_key:
            return False

        # Check if it is a placeholder (prefix)
        if api_key.startswith('your_') or api_key.startswith('your-'):
            return False

        # Check if it is a placeholder (suffix)
        if api_key.endswith('_here') or api_key.endswith('-here'):
            return False

        # 🔥 Check for truncated keys (containing '...') 
        if '...' in api_key:
            return False

        # Check length (allow shorter test keys, but still exclude obviously invalid values)
        if len(api_key) < 5:
            return False

        return True

    def _get_env_api_key(self, provider_name: str) -> Optional[str]:
        """从环境变量获取API密钥"""
        import os

        # Environment variable mapping table
        env_key_mapping = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "qianfan": "QIANFAN_API_KEY",
            "azure": "AZURE_OPENAI_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            # 🆕 aggregation channel
            "302ai": "AI302_API_KEY",
            "oneapi": "ONEAPI_API_KEY",
            "newapi": "NEWAPI_API_KEY",
            "custom_aggregator": "CUSTOM_AGGREGATOR_API_KEY"
        }

        env_var = env_key_mapping.get(provider_name)
        if env_var:
            api_key = os.getenv(env_var)
            # Use a unified verification method
            if self._is_valid_api_key(api_key):
                return api_key

        return None

    async def add_llm_provider(self, provider: LLMProvider) -> str:
        """添加大模型厂家"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            # Check if the manufacturer name already exists
            existing = await providers_collection.find_one({"name": provider.name})
            if existing:
                raise ValueError(f"厂家 {provider.name} 已存在")

            provider.created_at = now_tz()
            provider.updated_at = now_tz()

            # Fix: Remove _id field and let MongoDB automatically generate it ObjectId
            provider_data = provider.model_dump(by_alias=True, exclude_unset=True)
            if "_id" in provider_data:
                del provider_data["_id"]

            result = await providers_collection.insert_one(provider_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"添加厂家失败: {e}")
            raise

    async def update_llm_provider(self, provider_id: str, update_data: Dict[str, Any]) -> bool:
        """更新大模型厂家"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            update_data["updated_at"] = now_tz()

            # Compatibility processing: try both ObjectId and string types
            # Reason: Historical data may mix ObjectId and string as _id
            try:
                # First try querying as ObjectId
                result = await providers_collection.update_one(
                    {"_id": ObjectId(provider_id)},
                    {"$set": update_data}
                )

                # If no match is found, try querying as a string again
                if result.matched_count == 0:
                    result = await providers_collection.update_one(
                        {"_id": provider_id},
                        {"$set": update_data}
                    )
            except Exception:
                # If ObjectId conversion fails, query directly with string
                result = await providers_collection.update_one(
                    {"_id": provider_id},
                    {"$set": update_data}
                )

            # Fix:matched_count > 0 Indicates that the record was found (even if it was not modified)
            # modified_count > 0 Only true if the field was actually modified
            # If the record exists but has the same value, modified_count is 0, but this should not be returned 404
            return result.matched_count > 0
        except Exception as e:
            print(f"更新厂家失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_llm_provider(self, provider_id: str) -> bool:
        """删除大模型厂家"""
        try:
            print(f"🗑️ Delete manufacturer - provider_id: {provider_id}")
            print(f"🔍 ObjectId Type: {type(ObjectId(provider_id))}")

            db = await self._get_db()
            providers_collection = db.llm_providers
            print(f"📊 数据库: {db.name}, 集合: {providers_collection.name}")

            # First list the IDs of all manufacturers and look at the format.
            all_providers = await providers_collection.find({}, {"_id": 1, "display_name": 1}).to_list(length=None)
            print("📋 All manufacturers in the database ID:")
            for p in all_providers:
                print(f"   - {p['_id']} ({type(p['_id'])}) - {p.get('display_name')}")
                if str(p['_id']) == provider_id:
                    print("   ✅ 找到匹配的ID!")

            # Try different search methods
            print("🔍 Try to find with ObjectId...")
            existing1 = await providers_collection.find_one({"_id": ObjectId(provider_id)})

            print("🔍 Try to find with string...")
            existing2 = await providers_collection.find_one({"_id": provider_id})

            print(f"🔍 ObjectId Find results: {existing1 is not None}")
            print(f"🔍 字符串查找结果: {existing2 is not None}")

            existing = existing1 or existing2
            if not existing:
                print(f"❌ Neither method can find the manufacturer: {provider_id}")
                return False

            print(f"✅ 找到厂家: {existing.get('display_name')}")

            # Delete using the method found
            if existing1:
                result = await providers_collection.delete_one({"_id": ObjectId(provider_id)})
            else:
                result = await providers_collection.delete_one({"_id": provider_id})

            success = result.deleted_count > 0

            print(f"🗑️ 删除结果: {success}, deleted_count: {result.deleted_count}")
            return success

        except Exception as e:
            print(f"❌ 删除厂家失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def toggle_llm_provider(self, provider_id: str, is_active: bool) -> bool:
        """切换大模型厂家状态"""
        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            # Compatibility processing: try both ObjectId and string types
            try:
                # First try querying as ObjectId
                result = await providers_collection.update_one(
                    {"_id": ObjectId(provider_id)},
                    {"$set": {"is_active": is_active, "updated_at": now_tz()}}
                )

                # If no match is found, try querying as a string again
                if result.matched_count == 0:
                    result = await providers_collection.update_one(
                        {"_id": provider_id},
                        {"$set": {"is_active": is_active, "updated_at": now_tz()}}
                    )
            except Exception:
                # If ObjectId conversion fails, query directly with string
                result = await providers_collection.update_one(
                    {"_id": provider_id},
                    {"$set": {"is_active": is_active, "updated_at": now_tz()}}
                )

            return result.matched_count > 0
        except Exception as e:
            print(f"切换厂家状态失败: {e}")
            return False

    async def init_aggregator_providers(self) -> Dict[str, Any]:
        """
        Initialize aggregation channel manufacturer configuration

        Returns:
            Initialization result statistics
        """
        from app.constants.model_capabilities import AGGREGATOR_PROVIDERS

        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            added_count = 0
            skipped_count = 0
            updated_count = 0

            for provider_name, config in AGGREGATOR_PROVIDERS.items():
                # Get from environment variables API Key
                api_key = self._get_env_api_key(provider_name)

                # Check if it already exists
                existing = await providers_collection.find_one({"name": provider_name})

                if existing:
                    # If it already exists but does not have an API Key, and it is in the environment variable, update
                    if not existing.get("api_key") and api_key:
                        update_data = {
                            "api_key": api_key,
                            "is_active": True,  # If there is an API Key, it will be automatically enabled.
                            "updated_at": now_tz()
                        }
                        await providers_collection.update_one(
                            {"name": provider_name},
                            {"$set": update_data}
                        )
                        updated_count += 1
                        print(f"✅ 更新聚合渠道 {config['display_name']} 的 API Key")
                    else:
                        skipped_count += 1
                        print(f"⏭️ 聚合渠道 {config['display_name']} 已存在，跳过")
                    continue

                # Create aggregation channel vendor configuration
                provider_data = {
                    "name": provider_name,
                    "display_name": config["display_name"],
                    "description": config["description"],
                    "website": config.get("website"),
                    "api_doc_url": config.get("api_doc_url"),
                    "default_base_url": config["default_base_url"],
                    "is_active": bool(api_key),  # If there is an API Key, it will be automatically enabled.
                    "supported_features": ["chat", "completion", "function_calling", "streaming"],
                    "api_key": api_key or "",
                    "extra_config": {
                        "supported_providers": config.get("supported_providers", []),
                        "source": "environment" if api_key else "manual"
                    },
                    # 🆕 Aggregation channel identifier
                    "is_aggregator": True,
                    "aggregator_type": "openai_compatible",
                    "model_name_format": config.get("model_name_format", "{provider}/{model}"),
                    "created_at": now_tz(),
                    "updated_at": now_tz()
                }

                provider = LLMProvider(**provider_data)
                # Fix: Remove _id field and let MongoDB automatically generate it ObjectId
                insert_data = provider.model_dump(by_alias=True, exclude_unset=True)
                if "_id" in insert_data:
                    del insert_data["_id"]
                await providers_collection.insert_one(insert_data)
                added_count += 1

                if api_key:
                    print(f"✅ 添加聚合渠道: {config['display_name']} (已从环境变量获取 API Key)")
                else:
                    print(f"✅ 添加聚合渠道: {config['display_name']} (需手动配置 API Key)")

            message_parts = []
            if added_count > 0:
                message_parts.append(f"成功添加 {added_count} 个聚合渠道")
            if updated_count > 0:
                message_parts.append(f"更新 {updated_count} 个")
            if skipped_count > 0:
                message_parts.append(f"跳过 {skipped_count} 个已存在的")

            return {
                "success": True,
                "added": added_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "message": "，".join(message_parts) if message_parts else "无变更"
            }

        except Exception as e:
            print(f"❌ 初始化聚合渠道失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "message": "初始化聚合渠道失败"
            }

    async def migrate_env_to_providers(self) -> Dict[str, Any]:
        """Migrate environment variable configuration to manufacturer management"""
        import os

        try:
            db = await self._get_db()
            providers_collection = db.llm_providers

            # Default factory configuration
            default_providers = [
                {
                    "name": "openai",
                    "display_name": "OpenAI",
                    "description": "OpenAI Is a leading company in the field of artificial intelligence, providing GPT series models",
                    "website": "https://openai.com",
                    "api_doc_url": "https://platform.openai.com/docs",
                    "default_base_url": "https://api.openai.com/v1",
                    "supported_features": ["chat", "completion", "embedding", "image", "vision", "function_calling", "streaming"]
                },
                {
                    "name": "anthropic",
                    "display_name": "Anthropic",
                    "description": "Anthropic Focus on AI security research and provide Claude series models",
                    "website": "https://anthropic.com",
                    "api_doc_url": "https://docs.anthropic.com",
                    "default_base_url": "https://api.anthropic.com",
                    "supported_features": ["chat", "completion", "function_calling", "streaming"]
                },
                {
                    "name": "dashscope",
                    "display_name": "阿里云百炼",
                    "description": "Alibaba Cloud Bailian large model service platform provides Tongyi Qianwen and other models",
                    "website": "https://bailian.console.aliyun.com",
                    "api_doc_url": "https://help.aliyun.com/zh/dashscope/",
                    "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "supported_features": ["chat", "completion", "embedding", "function_calling", "streaming"]
                },
                {
                    "name": "deepseek",
                    "display_name": "DeepSeek",
                    "description": "DeepSeek Provide high-performance AI inference services",
                    "website": "https://www.deepseek.com",
                    "api_doc_url": "https://platform.deepseek.com/api-docs",
                    "default_base_url": "https://api.deepseek.com",
                    "supported_features": ["chat", "completion", "function_calling", "streaming"]
                }
            ]

            migrated_count = 0
            updated_count = 0
            skipped_count = 0

            for provider_config in default_providers:
                # Get API key from environment variable
                api_key = self._get_env_api_key(provider_config["name"])

                # Check if it already exists
                existing = await providers_collection.find_one({"name": provider_config["name"]})

                if existing:
                    # If an API key exists but no API key exists, and the key is in the environment variable, update
                    if not existing.get("api_key") and api_key:
                        update_data = {
                            "api_key": api_key,
                            "is_active": True,
                            "extra_config": {"migrated_from": "environment"},
                            "updated_at": now_tz()
                        }
                        await providers_collection.update_one(
                            {"name": provider_config["name"]},
                            {"$set": update_data}
                        )
                        updated_count += 1
                        print(f"✅ 更新厂家 {provider_config['display_name']} 的API密钥")
                    else:
                        skipped_count += 1
                        print(f"⏭️ 跳过厂家 {provider_config['display_name']} (已有配置)")
                    continue

                # Create new factory configuration
                provider_data = {
                    **provider_config,
                    "api_key": api_key,
                    "is_active": bool(api_key),  # Automatic activation with key
                    "extra_config": {"migrated_from": "environment"} if api_key else {},
                    "created_at": now_tz(),
                    "updated_at": now_tz()
                }

                await providers_collection.insert_one(provider_data)
                migrated_count += 1
                print(f"✅ 创建厂家 {provider_config['display_name']}")

            total_changes = migrated_count + updated_count
            message_parts = []
            if migrated_count > 0:
                message_parts.append(f"新建 {migrated_count} 个厂家")
            if updated_count > 0:
                message_parts.append(f"更新 {updated_count} 个厂家的API密钥")
            if skipped_count > 0:
                message_parts.append(f"跳过 {skipped_count} 个已配置的厂家")

            if total_changes > 0:
                message = "Migration completed:" + "，".join(message_parts)
            else:
                message = "All manufacturers have configured it, no need to migrate"

            return {
                "success": True,
                "migrated_count": migrated_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "message": message
            }

        except Exception as e:
            print(f"环境变量迁移失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "环境变量迁移失败"
            }

    async def test_provider_api(self, provider_id: str) -> dict:
        """测试厂家API密钥"""
        try:
            print(f"🔍 Test manufacturer API - provider_id: {provider_id}")

            db = await self._get_db()
            providers_collection = db.llm_providers

            # Compatibility processing: try both ObjectId and string types
            from bson import ObjectId
            provider_data = None
            try:
                # First try querying as ObjectId
                provider_data = await providers_collection.find_one({"_id": ObjectId(provider_id)})
            except Exception:
                pass

            # If not found, try querying as a string again
            if not provider_data:
                provider_data = await providers_collection.find_one({"_id": provider_id})

            if not provider_data:
                return {
                    "success": False,
                    "message": f"厂家不存在 (ID: {provider_id})"
                }

            provider_name = provider_data.get("name")
            api_key = provider_data.get("api_key")
            display_name = provider_data.get("display_name", provider_name)

            # 🔥 Determine whether the API Key in the database is valid
            if not self._is_valid_api_key(api_key):
                # The Key in the database is invalid, try to read from environment variables
                env_api_key = self._get_env_api_key(provider_name)
                if env_api_key:
                    api_key = env_api_key
                    print(f"✅ 数据库配置无效，从环境变量读取到 {display_name} 的 API Key")
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} No valid API key configured (neither found in database nor environment variables)"
                    }
            else:
                print(f"✅ 使用数据库配置的 {display_name} API密钥")

            # Call the corresponding test function according to the manufacturer type
            test_result = await self._test_provider_connection(provider_name, api_key, display_name)

            return test_result

        except Exception as e:
            print(f"测试厂家API失败: {e}")
            return {
                "success": False,
                "message": f"测试失败: {str(e)}"
            }

    async def _test_provider_connection(self, provider_name: str, api_key: str, display_name: str) -> dict:
        """测试具体厂家的连接"""
        import asyncio

        def normalize_provider_aliases(value: Any) -> set[str]:
            provider_value = getattr(value, "value", value)
            normalized = str(provider_value or "").strip().lower()

            if not normalized:
                return set()

            alias_groups = {
                "kimi": {"kimi", "moonshot"},
                "moonshot": {"kimi", "moonshot"},
            }
            return alias_groups.get(normalized, {normalized})

        # Obtain the manufacturer's configuration information (including test_model)
        db = await self._get_db()
        providers_collection = db.llm_providers
        provider_data = await providers_collection.find_one({"name": provider_name})
        test_model = provider_data.get("test_model") if provider_data else None

        llm_temperature = 0.1
        llm_max_tokens = 200
        llm_timeout = 15

        try:
            system_config = await self.get_system_config()
            llm_configs = system_config.llm_configs if system_config else []
            provider_aliases = normalize_provider_aliases(provider_name)

            def matches_provider(llm: Any) -> bool:
                llm_provider_aliases = normalize_provider_aliases(getattr(llm, "provider", None))
                return bool(provider_aliases & llm_provider_aliases)

            candidate_configs = [
                llm for llm in llm_configs
                if matches_provider(llm)
            ]

            matched_llm_config = None
            if test_model:
                matched_llm_config = next(
                    (
                        llm for llm in candidate_configs
                        if llm.model_name == test_model
                    ),
                    None
                )

            if matched_llm_config is None:
                matched_llm_config = next(
                    (
                        llm for llm in candidate_configs
                        if llm.enabled
                    ),
                    None
                )

            if matched_llm_config is not None:
                llm_temperature = matched_llm_config.temperature
                llm_max_tokens = matched_llm_config.max_tokens
                llm_timeout = matched_llm_config.timeout
                logger.info(
                    f"🔧 [{display_name}] API Test using configuration parameters: "
                    f"model={matched_llm_config.model_name}, "
                    f"temperature={llm_temperature}, max_tokens={llm_max_tokens}, timeout={llm_timeout}"
                )
            else:
                candidate_summary = [
                    {
                        "provider": getattr(llm, "provider", None),
                        "model_name": getattr(llm, "model_name", None),
                        "enabled": getattr(llm, "enabled", None),
                    }
                    for llm in candidate_configs
                ]
                logger.info(
                    f"⚠️ [{display_name}] No matching model configuration found, using test defaults: "
                    f"temperature={llm_temperature}, max_tokens={llm_max_tokens}, timeout={llm_timeout}; "
                    f"provider_name={provider_name}, provider_aliases={sorted(provider_aliases)}, "
                    f"test_model={test_model}, candidate_configs={candidate_summary}"
                )
        except Exception as config_error:
            logger.warning(f"⚠️ [{display_name}] Failed to read model test configuration, fallback to default test parameters: {config_error}")

        try:
            # Aggregation channels (using OpenAI compatible API)
            if provider_name in ["302ai", "oneapi", "newapi", "custom_aggregator"]:
                # Get the manufacturer's base_url
                base_url = provider_data.get("default_base_url") if provider_data else None
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._test_openai_compatible_api, api_key, display_name, base_url, provider_name, test_model,
                    llm_temperature, llm_max_tokens, llm_timeout
                )
            elif provider_name == "google":
                # Get the manufacturer's base_url
                base_url = provider_data.get("default_base_url") if provider_data else None
                return await asyncio.get_event_loop().run_in_executor(None, self._test_google_api, api_key, display_name, base_url, test_model)
            elif provider_name == "deepseek":
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._test_deepseek_api,
                    api_key,
                    display_name,
                    test_model,
                    llm_temperature,
                    llm_max_tokens,
                    llm_timeout,
                )
            elif provider_name == "dashscope":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_dashscope_api, api_key, display_name, test_model)
            elif provider_name == "openrouter":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_openrouter_api, api_key, display_name, test_model)
            elif provider_name == "openai":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_openai_api, api_key, display_name, test_model)
            elif provider_name == "anthropic":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_anthropic_api, api_key, display_name, test_model)
            elif provider_name == "qianfan":
                return await asyncio.get_event_loop().run_in_executor(None, self._test_qianfan_api, api_key, display_name, test_model)
            elif provider_name == "openai_compatible":
                # 🔥 Generic OpenAI Compatible API Testing
                logger.info(f"🔍 Use OpenAI compatible API to test universally compatible manufacturers: {provider_name}")
                # Get the manufacturer's base_url
                base_url = provider_data.get("default_base_url") if provider_data else None

                if not base_url:
                    return {
                        "success": False,
                        "message": f"OpenAI 兼容厂家 {display_name} 未配置 API 基础 URL (default_base_url)"
                    }

                return await asyncio.get_event_loop().run_in_executor(
                    None, self._test_openai_compatible_api, api_key, display_name, base_url, provider_name, test_model,
                    llm_temperature, llm_max_tokens, llm_timeout
                )
            else:
                # 🔧 For unknown custom manufacturers, use OpenAI compatible API testing
                logger.info(f"🔍 Test custom manufacturers using OpenAI compatible APIs: {provider_name}")
                # Get the manufacturer's base_url
                base_url = provider_data.get("default_base_url") if provider_data else None

                if not base_url:
                    return {
                        "success": False,
                        "message": f"自定义厂家 {display_name} 未配置 API 基础 URL"
                    }

                return await asyncio.get_event_loop().run_in_executor(
                    None, self._test_openai_compatible_api, api_key, display_name, base_url, provider_name, test_model,
                    llm_temperature, llm_max_tokens, llm_timeout
                )
        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} 连接测试失败: {str(e)}"
            }

    def _test_google_api(self, api_key: str, display_name: str, base_url: str = None, test_model: str = None) -> dict:
        """test Google AI API"""
        try:
            import requests

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "gemini-2.0-flash-exp"
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            logger.info("🔍 [Google AI test] Start testing")
            logger.info(f"   display_name: {display_name}")
            logger.info(f"   model_name: {model_name}")
            logger.info(f"   base_url (original): {base_url}")
            logger.info(f"   api_key 长度: {len(api_key) if api_key else 0}")

            # Use configured base_url or default
            if not base_url:
                base_url = "https://generativelanguage.googleapis.com/v1beta"
                logger.info(f"   ⚠️ base_url If empty, use default value: {base_url}")

            # Remove trailing slash
            base_url = base_url.rstrip('/')
            logger.info(f"   base_url (remove slash): {base_url}")

            # If base_url ends with /v1, replace with /v1beta (the correct endpoint for Google AI)
            if base_url.endswith('/v1'):
                base_url = base_url[:-3] + '/v1beta'
                logger.info(f"   ✅ Replace /v1 with /v1beta: {base_url}")

            # Build complete API endpoints (using user-configured models)
            url = f"{base_url}/models/{model_name}:generateContent?key={api_key}"

            logger.info(f"🔗 [Google AI test] final request URL: {url.replace(api_key, '***')}")

            headers = {
                "Content-Type": "application/json"
            }

            # 🔧 Increase the token limit to 2000 to avoid thinking mode consumption resulting in no output
            data = {
                "contents": [{
                    "parts": [{
                        "text": "Hello, please respond with 'OK' if you can read this."
                    }]
                }],
                "generationConfig": {
                    "maxOutputTokens": 2000,
                    "temperature": 0.1
                }
            }

            response = requests.post(url, json=data, headers=headers, timeout=15)

            print(f"📥 [Google AI test] Response status code: {response.status_code}")

            if response.status_code == 200:
                # Print the complete response content for debugging
                print(f"📥 [Google AI test] Response content (first 1000 characters): {response.text[:1000]}")

                result = response.json()
                print("📥 [Google AI test] Parsed JSON structure:")
                print(f"   - 顶层键: {list(result.keys())}")
                print(f"   - Does it contain 'candidates': {'candidates' in result}")
                if "candidates" in result:
                    print(f"   - candidates length: {len(result['candidates'])}")
                    if len(result['candidates']) > 0:
                        print(f"   - candidates[0] key: {list(result['candidates'][0].keys())}")

                if "candidates" in result and len(result["candidates"]) > 0:
                    candidate = result["candidates"][0]
                    print(f"📥 [Google AI test] candidate structure: {candidate}")

                    # Check finishReason
                    finish_reason = candidate.get("finishReason", "")
                    print(f"📥 [Google AI test] finishReason: {finish_reason}")

                    if "content" in candidate:
                        content = candidate["content"]

                        # Check if there is parts
                        if "parts" in content and len(content["parts"]) > 0:
                            text = content["parts"][0].get("text", "")
                            print(f"📥 [Google AI test] Extracted text: {text}")

                            if text and len(text.strip()) > 0:
                                return {
                                    "success": True,
                                    "message": f"{display_name} API连接测试成功"
                                }
                            else:
                                print("❌ [Google AI test] Text is empty")
                                return {
                                    "success": False,
                                    "message": f"{display_name} API响应内容为空"
                                }
                        else:
                            # content There are no parts in , maybe because of MAX_TOKENS or other reasons
                            print("❌ [Google AI test] content None parts")
                            print(f"   content 的键: {list(content.keys())}")

                            if finish_reason == "MAX_TOKENS":
                                return {
                                    "success": False,
                                    "message": f"{display_name} API The response was truncated (MAX_TOKENS), please increase the maxOutputTokens configuration"
                                }
                            else:
                                return {
                                    "success": False,
                                    "message": f"{display_name} API Abnormal response format (missing parts,finishReason: {finish_reason}) "
                                }
                    else:
                        print("❌ [Google AI test] candidate missing in 'content'")
                        print(f"   candidate key: {list(candidate.keys())}")
                        return {
                            "success": False,
                            "message": f"{display_name} API Abnormal response format (missing content)"
                        }
                else:
                    print("❌ [Google AI test] candidates are missing or empty")
                    return {
                        "success": False,
                        "message": f"{display_name} API无有效候选响应"
                    }
            elif response.status_code == 400:
                print(f"❌ [Google AI test] 400 Error, response content: {response.text[:500]}")
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("error", {}).get("message", "未知错误")
                    return {
                        "success": False,
                        "message": f"{display_name} API请求错误: {error_msg}"
                    }
                except Exception:
                    return {
                        "success": False,
                        "message": f"{display_name} API请求格式错误"
                    }
            elif response.status_code == 403:
                print(f"❌ [Google AI test] 403 Error, response content: {response.text[:500]}")
                return {
                    "success": False,
                    "message": f"{display_name} Authentication or permissions are abnormal, please check the account, API Key and model access permissions"
                }
            elif response.status_code == 402:
                print(f"❌ [Google AI test] 402 Error, response content: {response.text[:500]}")
                return {
                    "success": False,
                    "message": f"{display_name} The account balance is insufficient, please check the balance, package or model payment permissions"
                }
            elif response.status_code == 503:
                print(f"❌ [Google AI test] 503 Error, response content: {response.text[:500]}")
                try:
                    error_detail = response.json()
                    error_code = error_detail.get("code", "")
                    error_msg = error_detail.get("message", "服务暂时不可用")

                    if error_code == "NO_KEYS_AVAILABLE":
                        return {
                            "success": False,
                            "message": f"{display_name} The transfer service has no available keys. Please try again later or contact the transfer service provider."
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} 服务暂时不可用: {error_msg}"
                        }
                except Exception:
                    return {
                        "success": False,
                        "message": f"{display_name} Service is temporarily unavailable (HTTP 503)"
                    }
            else:
                print(f"❌ [Google AI test] {response.status_code} Error, response content: {response.text[:500]}")
                return {
                    "success": False,
                    "message": f"{display_name} API test failed: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_deepseek_api(
        self,
        api_key: str,
        display_name: str,
        test_model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 200,
        timeout: int = 15,
    ) -> dict:
        """test DeepSeek API"""
        try:
            import requests

            def _normalize_message_text(value: Any) -> str:
                if value is None:
                    return ""
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, list):
                    text_parts = []
                    for item in value:
                        if isinstance(item, dict):
                            text = item.get("text") or item.get("content") or item.get("reasoning_content")
                            if text:
                                text_parts.append(str(text))
                        elif item:
                            text_parts.append(str(item))
                    return "".join(text_parts).strip()
                return str(value).strip()

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "deepseek-chat"
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            logger.info(f"🔍 [DeepSeek test] Use model: {model_name}")

            url = "https://api.deepseek.com/chat/completions"
            effective_temperature = float(temperature if temperature is not None else 0.1)
            effective_timeout = max(int(timeout if timeout is not None else 15), 1)
            requested_max_tokens = int(max_tokens if max_tokens is not None else 200)
            effective_max_tokens = max(requested_max_tokens, 256)

            logger.info(
                f"🔧 [DeepSeek test] Use test parameters: "
                f"temperature={effective_temperature}, max_tokens={effective_max_tokens}, timeout={effective_timeout}"
            )

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Hello, please introduce yourself briefly."}
                ],
                "max_tokens": effective_max_tokens,
                "temperature": effective_temperature
            }

            response = requests.post(url, json=data, headers=headers, timeout=effective_timeout)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    choice = result["choices"][0] or {}
                    message = choice.get("message") or {}
                    content = _normalize_message_text(message.get("content"))
                    reasoning_content = _normalize_message_text(message.get("reasoning_content"))
                    finish_reason = str(choice.get("finish_reason") or "").lower()

                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    elif reasoning_content:
                        logger.info(
                            f"✅ [{display_name}] DeepSeek The test returns reasoning_content, which is considered a successful connection.: "
                            f"finish_reason={finish_reason or 'N/A'}"
                        )
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    elif finish_reason in {"length", "max_tokens"}:
                        logger.info(
                            f"✅ [{display_name}] DeepSeek The test response is truncated due to token restrictions and the connection is considered successful.: "
                            f"finish_reason={finish_reason}, max_tokens={effective_max_tokens}"
                        )
                        return {
                            "success": True,
                            "message": f"{display_name} API Connection test successful (response truncated due to token limit)"
                        }
                    else:
                        logger.warning(
                            f"⚠️ [{display_name}] DeepSeek Test returns empty content: "
                            f"finish_reason={finish_reason or 'N/A'}, has_reasoning={bool(reasoning_content)}, "
                            f"response_keys={list(result.keys())}"
                        )
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": f"{display_name} Account authentication failed, please check API Key, account status and model access permissions"
                }
            elif response.status_code == 402:
                return {
                    "success": False,
                    "message": f"{display_name} The account balance is insufficient, please check the balance, package quota or model payment permissions"
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": f"{display_name} The account has insufficient permissions, or the current model quota has been used up. Please check the package and model authorization."
                }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API test failed: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_dashscope_api(self, api_key: str, display_name: str, test_model: str = None) -> dict:
        """测试阿里云百炼API"""
        try:
            import requests

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "qwen-turbo"
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            logger.info(f"🔍 [DashScope test] Use model: {model_name}")
            #logger.info(f"🔍 [DashScope test] API Key: Configured (desensitized)")
            logger.info(f"🔍 [DashScope test] API Key length: {len(api_key) if api_key else 0}")

            # Use Alibaba Cloud Bailian's OpenAI compatible interface
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Hello, please introduce yourself briefly."}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API test failed: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_openrouter_api(self, api_key: str, display_name: str, test_model: str = None) -> dict:
        """test OpenRouter API"""
        try:
            import requests

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "meta-llama/llama-3.2-3b-instruct:free"  # Use free models
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            url = "https://openrouter.ai/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://tradingagents.cn",  # OpenRouter request
                "X-Title": "TradingAgents-CN"
            }

            data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Hello, please introduce yourself briefly."}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=15)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API test failed: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_openai_api(self, api_key: str, display_name: str, test_model: str = None) -> dict:
        """测试OpenAI API"""
        try:
            import requests

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "gpt-3.5-turbo"
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            url = "https://api.openai.com/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Hello, please introduce yourself briefly."}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API test failed: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_anthropic_api(self, api_key: str, display_name: str, test_model: str = None) -> dict:
        """test Anthropic API"""
        try:
            import requests

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "claude-3-haiku-20240307"
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            url = "https://api.anthropic.com/v1/messages"

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }

            data = {
                "model": model_name,
                "max_tokens": 50,
                "messages": [
                    {"role": "user", "content": "Hello, please introduce yourself briefly."}
                ]
            }

            response = requests.post(url, json=data, headers=headers, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if "content" in result and len(result["content"]) > 0:
                    content = result["content"][0]["text"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            else:
                return {
                    "success": False,
                    "message": f"{display_name} API test failed: HTTP {response.status_code}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    def _test_qianfan_api(self, api_key: str, display_name: str, test_model: str = None) -> dict:
        """测试百度千帆API"""
        try:
            import requests

            # 🔥 The test model filled in by the user will be used first, if not, the default model will be used.
            if test_model and test_model.strip():
                model_name = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {model_name}")
            else:
                model_name = "ernie-3.5-8k"
                logger.info(f"⚠️ No model specified, default model used: {model_name}")

            # Qianfan's new generation API uses OpenAI compatible interface
            url = "https://qianfan.baidubce.com/v2/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Hello, please introduce yourself briefly."}
                ],
                "max_tokens": 50,
                "temperature": 0.1
            }

            response = requests.post(url, json=data, headers=headers, timeout=15)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": f"{display_name} Account authentication failed, please check API Key, account status and model access permissions"
                }
            elif response.status_code == 402:
                return {
                    "success": False,
                    "message": f"{display_name} The account balance is insufficient, please check the balance, package quota or model payment permissions"
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": f"{display_name} The account has insufficient permissions, or the current model quota has been used up. Please check the package and model authorization."
                }
            else:
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("error", {}).get("message", f"HTTP {response.status_code}")
                    return {
                        "success": False,
                        "message": f"{display_name} API测试失败: {error_msg}"
                    }
                except Exception:
                    return {
                        "success": False,
                        "message": f"{display_name} API test failed: HTTP {response.status_code}"
                    }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }

    async def fetch_provider_models(self, provider_id: str, filters: Optional[Dict[str, Any]] = None) -> dict:
        """Get model list from manufacturer API

        Args:
            provider_id: Manufacturer ID
            filters: Optional filtering parameters (filtered on the client after the front-end pulls it, the server only does compatible reception)
        """
        try:
            filters = filters or {}
            print(f"🔍 Get manufacturer model list - provider_id: {provider_id}, filters: {filters}")

            db = await self._get_db()
            providers_collection = db.llm_providers

            # Compatibility processing: try both ObjectId and string types
            from bson import ObjectId
            provider_data = None
            try:
                provider_data = await providers_collection.find_one({"_id": ObjectId(provider_id)})
            except Exception:
                pass

            if not provider_data:
                provider_data = await providers_collection.find_one({"_id": provider_id})

            if not provider_data:
                return {
                    "success": False,
                    "message": f"厂家不存在 (ID: {provider_id})"
                }

            provider_name = provider_data.get("name")
            api_key = provider_data.get("api_key")
            base_url = provider_data.get("default_base_url")
            display_name = provider_data.get("display_name", provider_name)

            # Volcano Ark programming: directly returns the hard-coded 11 models without adjusting API
            if provider_name == "volcengine_coding":
                coding_plan_models = [
                    {"id": "doubao-seed-2.0-code", "name": "Doubao-Seed-2.0-Code"},
                    {"id": "doubao-seed-2.0-pro", "name": "Doubao-Seed-2.0-pro"},
                    {"id": "doubao-seed-2.0-lite", "name": "Doubao-Seed-2.0-lite"},
                    {"id": "doubao-seed-code", "name": "Doubao-Seed-Code"},
                    {"id": "glm-5.2", "name": "GLM-5.2"},
                    {"id": "kimi-k2.7-code", "name": "Kimi-K2.7-Code"},
                    {"id": "minimax-m3", "name": "MiniMax-M3"},
                    {"id": "deepseek-v4-flash", "name": "DeepSeek-V4-Flash"},
                    {"id": "deepseek-v4-pro", "name": "DeepSeek-V4-Pro"},
                    {"id": "minimax-m2.7", "name": "MiniMax-M2.7"},
                    {"id": "kimi-k2.6", "name": "Kimi-K2.6"},
                ]
                print(f"✅ [火山方舟编程] 直接返回 {len(coding_plan_models)} 个预设模型")
                return {
                    "success": True,
                    "models": coding_plan_models,
                    "message": f"成功获取 {len(coding_plan_models)} 个预设模型"
                }

            # 🔥 Determine whether the API Key in the database is valid
            if not self._is_valid_api_key(api_key):
                # The Key in the database is invalid, try to read from environment variables
                env_api_key = self._get_env_api_key(provider_name)
                if env_api_key:
                    api_key = env_api_key
                    print(f"✅ 数据库配置无效，从环境变量读取到 {display_name} 的 API Key")
                else:
                    # The /models endpoint is not required for some aggregation platforms (such as OpenRouter) API Key
                    print(f"⚠️ {display_name} No valid API key is configured, trying to access without authentication")
            else:
                print(f"✅ 使用数据库配置的 {display_name} API密钥")

            if not base_url:
                return {
                    "success": False,
                    "message": f"{display_name} API base address not configured (default_base_url)"
                }

            # Call the OpenAI compatible /v1/models endpoint
            import asyncio
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_models_from_api, api_key, base_url, display_name, provider_name
            )

            return result

        except Exception as e:
            print(f"获取模型列表失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"获取模型列表失败: {str(e)}"
            }

    def _fetch_models_from_api(self, api_key: str, base_url: str, display_name: str, provider_name: str = None) -> dict:
        """从 API 获取模型列表"""
        try:
            import requests

            # 🔧 Intelligent version number processing: only add a version number if there is no version number /v1
            # Avoid adding URLs with existing version numbers (such as /v4 of Zhipu AI) repeatedly. /v1
            import re
            base_url = base_url.rstrip("/")
            if not re.search(r'/v\d+$', base_url):
                # URL There is no version number at the end, add /v1 (OpenAI standard)
                base_url = base_url + "/v1"
                logger.info(f"   [Get model list] Add /v1 version number: {base_url}")
            else:
                # URL Already contains the version number (such as /v4), do not add it
                logger.info(f"   [Get model list] An existing version number is detected, keep it as is: {base_url}")

            url = f"{base_url}/models"

            # Build request headers
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                print(f"🔍 请求 URL: {url} (with API Key)")
            else:
                print(f"🔍 请求 URL: {url} (without API Key)")

            response = requests.get(url, headers=headers, timeout=15)

            print(f"📊 响应状态码: {response.status_code}")
            print(f"📊 响应内容: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                print(f"📊 Response JSON structure: {list(result.keys())}")

                if "data" in result and isinstance(result["data"], list):
                    all_models = result["data"]
                    print(f"📊 API 返回 {len(all_models)} 个模型")

                    # Print the complete structure of the first few models (for debugging price fields)
                    if all_models:
                        print("🔍 Complete structure of the first model:")
                        import json
                        print(json.dumps(all_models[0], indent=2, ensure_ascii=False))

                    # Print all Anthropic models (for debugging)
                    anthropic_models = [m for m in all_models if "anthropic" in m.get("id", "").lower()]
                    if anthropic_models:
                        print(f"🔍 Anthropic 模型列表 ({len(anthropic_models)} 个):")
                        for m in anthropic_models[:20]:  # Only print the first 20
                            print(f"   - {m.get('id')}")

                    # Filtering: Only retain commonly used models from mainstream manufacturers
                    filtered_models = self._filter_popular_models(all_models, provider_name)
                    print(f"✅ 过滤后保留 {len(filtered_models)} 个常用模型")

                    # Convert model format to include price information
                    formatted_models = self._format_models_with_pricing(filtered_models)

                    return {
                        "success": True,
                        "models": formatted_models,
                        "message": f"成功获取 {len(formatted_models)} 个常用模型（已过滤）"
                    }
                else:
                    print("❌ Response format exception, expected 'data' Field is a list")
                    return {
                        "success": False,
                        "message": f"{display_name} API Response format exception (data field is missing or incorrectly formatted)"
                    }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": f"{display_name} Account authentication failed, please check API Key, account status and model access permissions"
                }
            elif response.status_code == 402:
                return {
                    "success": False,
                    "message": f"{display_name} The account balance is insufficient, please check the balance, package quota or model payment permissions"
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": f"{display_name} Insufficient account permissions, please check package and model authorization"
                }
            else:
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("error", {}).get("message", f"HTTP {response.status_code}")
                    print(f"❌ API 错误: {error_msg}")
                    return {
                        "success": False,
                        "message": f"{display_name} API请求失败: {error_msg}"
                    }
                except Exception:
                    print(f"❌ HTTP 错误: {response.status_code}")
                    return {
                        "success": False,
                        "message": f"{display_name} API请求失败: HTTP {response.status_code}, 响应: {response.text[:200]}"
                    }

        except Exception as e:
            print(f"❌ 异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"{display_name} API请求异常: {str(e)}"
            }

    def _format_models_with_pricing(self, models: list) -> list:
        """
        Formatted model list with price information

        Supports multiple price formats:
        1. OpenRouter: pricing.prompt/completion (USD per token)
        2. 302.ai: price.prompt/completion or price.input/output
        3. Others: Price information may not be available
        """
        formatted = []
        for model in models:
            model_id = model.get("id", "")
            model_name = model.get("name", model_id)

            # Try to get price information from multiple fields
            input_price_per_1k = None
            output_price_per_1k = None

            # Method 1: OpenRouter format (pricing.prompt/completion)
            pricing = model.get("pricing", {})
            if pricing:
                prompt_price = pricing.get("prompt", "0")  # USD per token
                completion_price = pricing.get("completion", "0")  # USD per token

                try:
                    if prompt_price and float(prompt_price) > 0:
                        input_price_per_1k = float(prompt_price) * 1000
                    if completion_price and float(completion_price) > 0:
                        output_price_per_1k = float(completion_price) * 1000
                except (ValueError, TypeError):
                    pass

            # Method 2: 302.ai format (price.prompt/completion or price.input/output)
            if not input_price_per_1k and not output_price_per_1k:
                price = model.get("price", {})
                if price and isinstance(price, dict):
                    # Try the prompt/completion field
                    prompt_price = price.get("prompt") or price.get("input")
                    completion_price = price.get("completion") or price.get("output")

                    try:
                        if prompt_price and float(prompt_price) > 0:
                            # Assuming per token, convert to per 1K tokens
                            input_price_per_1k = float(prompt_price) * 1000
                        if completion_price and float(completion_price) > 0:
                            output_price_per_1k = float(completion_price) * 1000
                    except (ValueError, TypeError):
                        pass

            # Get context length
            context_length = model.get("context_length")
            if not context_length:
                # Try to get from top_provider
                top_provider = model.get("top_provider", {})
                context_length = top_provider.get("context_length")

            # If still not, try inferring from max_completion_tokens
            if not context_length:
                max_tokens = model.get("max_completion_tokens")
                if max_tokens and max_tokens > 0:
                    # Typically the context length is 4-8 times the maximum output
                    context_length = max_tokens * 4

            formatted_model = {
                "id": model_id,
                "name": model_name,
                "context_length": context_length,
                "input_price_per_1k": input_price_per_1k,
                "output_price_per_1k": output_price_per_1k,
            }

            formatted.append(formatted_model)

            # Print price information (for debugging)
            if input_price_per_1k or output_price_per_1k:
                print(f"💰 {model_id}: 输入=${input_price_per_1k:.6f}/1K, 输出=${output_price_per_1k:.6f}/1K")

        return formatted

    def _filter_popular_models(self, models: list, provider_name: str = None) -> list:
        """Filter the model list to only retain commonly used models from major manufacturers"""
        import re

        # Volcano Ark Programming: No filtering, return all models (API has returned the corresponding models according to package permissions)
        # Volcano Ark (non-programming): no filtering, returns all models
        if provider_name in ("volcengine_coding", "volcengine"):
            print(f"✅ [{provider_name}] 返回全部 {len(models)} 个模型（不过滤）")
            return models

        # Only three major companies are retained: OpenAI, Anthropic,Google
        popular_providers = [
            "openai",      # OpenAI
            "anthropic",   # Anthropic
            "google",      # Google
        ]

        # Common model name prefixes (used to identify models without vendor prefixes)
        model_prefixes = {
            "gpt-": "openai",           # gpt-3.5-turbo, gpt-4, gpt-4o
            "o1-": "openai",            # o1-preview, o1-mini
            "claude-": "anthropic",     # claude-3-opus, claude-3-sonnet
            "gemini-": "google",        # gemini-pro, gemini-1.5-pro
            "gemini": "google",         # gemini (without hyphen)
            "doubao-": "volcengine",    # Volcano Ark Bean Bag Model
            "ep-": "volcengine",        # Volcano Ark Reasoning Access Point (Endpoint)
        }

        # Excluded keywords
        exclude_keywords = [
            "preview",
            "experimental",
            "alpha",
            "beta",
            "free",
            "extended",
            "nitro",
            ":free",
            ":extended",
            "online",  # Exclude versions with online search
            "instruct",  # Exclude instruct version
        ]

        # Date format regular expression (matches the format 2024-05-13)
        date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')

        filtered = []
        for model in models:
            model_id = model.get("id", "").lower()
            model_name = model.get("name", "").lower()

            # Check whether it belongs to the three major factories
            # Method 1: The model ID contains the manufacturer name (such as openai/gpt-4)
            is_popular_provider = any(provider in model_id for provider in popular_providers)

            # Method 2: Model ID starts with a common prefix (such as gpt-4, claude-3-sonnet) 
            if not is_popular_provider:
                for prefix, provider in model_prefixes.items():
                    if model_id.startswith(prefix):
                        is_popular_provider = True
                        print(f"🔍 识别模型前缀: {model_id} -> {provider}")
                        break

            if not is_popular_provider:
                continue

            # Check if a date is included (exclude older versions with dates)
            if date_pattern.search(model_id):
                print(f"⏭️ Skip older versions with dates: {model_id}")
                continue

            # Check if negative keywords are included
            has_exclude_keyword = any(keyword in model_id or keyword in model_name for keyword in exclude_keywords)

            if has_exclude_keyword:
                print(f"⏭️ 跳过排除关键词: {model_id}")
                continue

            # keep this model
            print(f"✅ 保留模型: {model_id}")
            filtered.append(model)

        return filtered

    def _test_openai_compatible_api(
        self,
        api_key: str,
        display_name: str,
        base_url: str = None,
        provider_name: str = None,
        test_model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 200,
        timeout: int = 15,
    ) -> dict:
        """Test OpenAI compatible API (for aggregation channels and custom manufacturers)"""
        try:
            import requests

            # If base_url is not provided, the default value is used
            if not base_url:
                return {
                    "success": False,
                    "message": f"{display_name} API base address not configured (default_base_url)"
                }

            # 🔧 Intelligent version number processing: only add a version number if there is no version number /v1
            # Avoid adding URLs with existing version numbers (such as /v4 of Zhipu AI) repeatedly. /v1
            import re
            logger.info(f"   [test API] original base_url: {base_url}")
            base_url = base_url.rstrip("/")
            logger.info(f"   [test API] After removing the slash: {base_url}")

            if not re.search(r'/v\d+$', base_url):
                # URL There is no version number at the end, add /v1 (OpenAI standard)
                base_url = base_url + "/v1"
                logger.info(f"   [test API] Add /v1 version number: {base_url}")
            else:
                # URL Already contains the version number (such as /v4), do not add it
                logger.info(f"   [test API] An existing version number is detected, keep it as is: {base_url}")

            url = f"{base_url}/chat/completions"
            logger.info(f"   [test API] final request URL: {url}")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            # 🔥 Priority is given to using the test model filled in by the user. If not, the default model is selected based on the manufacturer type.
            if test_model and test_model.strip():
                # The user has filled in the test model and is given priority.
                final_test_model = test_model.strip()
                logger.info(f"🔍 Use user-specified test model: {final_test_model}")
            else:
                # If not filled in by the user, use the system default value.
                final_test_model = "gpt-3.5-turbo"  # Default model
                if provider_name == "siliconflow":
                    # Silicon-based flow tested using free Qwen model
                    final_test_model = "Qwen/Qwen2.5-7B-Instruct"
                    logger.info(f"🔍 Silicon-based flow usage test model: {final_test_model}")
                elif provider_name == "zhipu":
                    # Zhipu AI uses the glm-4 model for testing
                    final_test_model = "glm-4.5-flash"
                    logger.info(f"🔍 Zhipu AI uses test model: {final_test_model}")
                else:
                    logger.info(f"🔍 使用默认测试模型: {final_test_model}")

            # Use a common model name for testing
            # Aggregation channels usually support multiple models, here the user-specified or default test model is used
            data = {
                "model": final_test_model,
                "messages": [
                    {"role": "user", "content": "Hello, please respond with 'OK' if you can read this."}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            }

            response = requests.post(url, json=data, headers=headers, timeout=timeout)

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    if content and len(content.strip()) > 0:
                        return {
                            "success": True,
                            "message": f"{display_name} API连接测试成功"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"{display_name} API响应为空"
                        }
                else:
                    return {
                        "success": False,
                        "message": f"{display_name} API响应格式异常"
                    }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": f"{display_name} Account authentication failed, please check API Key, account status and model access permissions"
                }
            elif response.status_code == 402:
                return {
                    "success": False,
                    "message": f"{display_name} The account balance is insufficient, please check the balance, package quota or model payment permissions"
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": f"{display_name} The account has insufficient permissions, or the current model quota has been used up. Please check the package and model authorization."
                }
            else:
                try:
                    error_detail = response.json()
                    error_msg = error_detail.get("error", {}).get("message", f"HTTP {response.status_code}")
                    logger.error(f"❌ [{display_name}] API测试失败")
                    logger.error(f"   请求URL: {url}")
                    logger.error(f"   状态码: {response.status_code}")
                    logger.error(f"   错误详情: {error_detail}")
                    return {
                        "success": False,
                        "message": f"{display_name} API测试失败: {error_msg}"
                    }
                except Exception:
                    logger.error(f"❌ [{display_name}] API测试失败")
                    logger.error(f"   请求URL: {url}")
                    logger.error(f"   状态码: {response.status_code}")
                    logger.error(f"   响应内容: {response.text[:500]}")
                    return {
                        "success": False,
                        "message": f"{display_name} API test failed: HTTP {response.status_code}"
                    }

        except Exception as e:
            return {
                "success": False,
                "message": f"{display_name} API测试异常: {str(e)}"
            }


# Create a global instance
config_service = ConfigService()

# === model_capability_service.py ===
"""
Model capability management service

Provides model capability evaluation, verification and recommendation functions.
"""

from typing import Tuple, Dict, Optional, List, Any
from app.constants.model_capabilities import (
    ANALYSIS_DEPTH_REQUIREMENTS,
    DEFAULT_MODEL_CAPABILITIES,
    CAPABILITY_DESCRIPTIONS,
    ModelRole,
    ModelFeature
)
from app.core.unified_config import unified_config
import logging
import re

logger = logging.getLogger(__name__)


class ModelCapabilityService:
    """模型能力管理服务"""

    def _parse_aggregator_model_name(self, model_name: str) -> Tuple[Optional[str], str]:
        """
        Resolve model names for aggregation channels

        Args:
            model_name: Model name, which may include a prefix (e.g. openai/gpt-4, anthropic/claude-3-sonnet) 

        Returns:
            (original manufacturer, Original model name) tuple
        """
        # Common aggregation channel model name format:
        # - openai/gpt-4
        # - anthropic/claude-3-sonnet
        # - google/gemini-pro

        if "/" in model_name:
            parts = model_name.split("/", 1)
            if len(parts) == 2:
                provider_hint = parts[0].lower()
                original_model = parts[1]

                # Mapping provider hints to fully qualified names
                provider_map = {
                    "openai": "openai",
                    "anthropic": "anthropic",
                    "google": "google",
                    "deepseek": "deepseek",
                    "alibaba": "qwen",
                    "qwen": "qwen",
                    "zhipu": "zhipu",
                    "baidu": "baidu",
                    "moonshot": "moonshot"
                }

                provider = provider_map.get(provider_hint)
                return provider, original_model

        return None, model_name

    def _get_model_capability_with_mapping(self, model_name: str) -> Tuple[int, Optional[str]]:
        """
        Get model capability level (supports aggregation channel mapping)

        Returns:
            (Ability level, The original model name of the mapping) tuple
        """
        # 1. Try a direct match first
        if model_name in DEFAULT_MODEL_CAPABILITIES:
            return DEFAULT_MODEL_CAPABILITIES[model_name]["capability_level"], None

        # 2. Try to parse the aggregation channel model name
        provider, original_model = self._parse_aggregator_model_name(model_name)

        if original_model and original_model != model_name:
            # Try to search using the original model name
            if original_model in DEFAULT_MODEL_CAPABILITIES:
                logger.info(f"🔄 聚合渠道模型映射: {model_name} -> {original_model}")
                return DEFAULT_MODEL_CAPABILITIES[original_model]["capability_level"], original_model

        # 3. Return to default value
        return 2, None

    def get_model_capability(self, model_name: str) -> int:
        """
        Get the capability level of the model (supports aggregation channel model mapping)

        Args:
            model_name: Model name (may include aggregation channel prefix, such as openai/gpt-4)

        Returns:
            Ability level (1-5)
        """
        # 1. Read from database configuration first
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.model_name == model_name:
                    return getattr(config, 'capability_level', 2)
        except Exception as e:
            logger.warning(f"从配置读取模型能力失败: {e}")

        # 2. Read from default mapping table (supports aggregate channel mapping)
        capability, mapped_model = self._get_model_capability_with_mapping(model_name)
        if mapped_model:
            logger.info(f"✅ 使用映射模型 {mapped_model} 的能力等级: {capability}")

        return capability
    
    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """
        Obtain the complete configuration information of the model (supports aggregation channel model mapping)

        Args:
            model_name: Model name (may include aggregation channel prefix)

        Returns:
            Model configuration dictionary
        """
        # 1. Prefer reading from MongoDB database configuration (using sync client)
        try:
            from pymongo import MongoClient
            from app.core.config import settings
            from app.models.config import SystemConfig

            # Using the synchronous MongoDB client
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            collection = db.system_configs  # Note: the collection name is plural

            # Query system configuration (consistent with config_service)
            doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

            logger.info(f"🔍 [MongoDB] Query results: doc={'exist' if doc else 'does not exist'}")
            if doc:
                logger.info(f"🔍 [MongoDB] Document version: {doc.get('version')}, is_active: {doc.get('is_active')}")

            if doc and "llm_configs" in doc:
                llm_configs = doc["llm_configs"]
                logger.info(f"🔍 [MongoDB] llm_configs Quantity: {len(llm_configs)}")

                for config_dict in llm_configs:
                    if config_dict.get("model_name") == model_name:
                        logger.info(f"🔍 [MongoDB] Find model configuration: {model_name}")
                        # 🔧 Convert a list of strings to a list of enumerations
                        features_str = config_dict.get('features', [])
                        features_enum = []
                        for feature_str in features_str:
                            try:
                                # Compatible with older versions function_calling -> tool_calling
                                if feature_str == "function_calling":
                                    feature_str = "tool_calling"
                                features_enum.append(ModelFeature(feature_str))
                            except ValueError:
                                logger.warning(f"⚠️ 未知的特性值: {feature_str}")

                        # 🔧 Convert a list of strings to a list of enumerations
                        roles_str = config_dict.get('suitable_roles', ["both"])
                        roles_enum = []
                        for role_str in roles_str:
                            try:
                                # Convert string to ModelRole enumeration
                                roles_enum.append(ModelRole(role_str))
                            except ValueError:
                                logger.warning(f"⚠️ 未知的角色值: {role_str}")

                        # If there is no role, the default is both
                        if not roles_enum:
                            roles_enum = [ModelRole.BOTH]

                        logger.info(f"📊 [MongoDB Configuration] {model_name}: features={features_enum}, roles={roles_enum}")

                        # close connection
                        client.close()

                        return {
                            "model_name": config_dict.get("model_name"),
                            "capability_level": config_dict.get('capability_level', 2),
                            "suitable_roles": roles_enum,
                            "features": features_enum,
                            "recommended_depths": config_dict.get('recommended_depths', ["快速", "基础", "标准"]),
                            "performance_metrics": config_dict.get('performance_metrics', None)
                        }

            # close connection
            client.close()

        except Exception as e:
            logger.warning(f"Failed to read model information from MongoDB: {e}", exc_info=True)

        # 2. Read from default mapping table (direct match)
        if model_name in DEFAULT_MODEL_CAPABILITIES:
            return DEFAULT_MODEL_CAPABILITIES[model_name]

        # 3. Try aggregate channel model mapping
        provider, original_model = self._parse_aggregator_model_name(model_name)
        if original_model and original_model != model_name:
            if original_model in DEFAULT_MODEL_CAPABILITIES:
                logger.info(f"🔄 聚合渠道模型映射: {model_name} -> {original_model}")
                config = DEFAULT_MODEL_CAPABILITIES[original_model].copy()
                config["model_name"] = model_name  # Keep original model name
                config["_mapped_from"] = original_model  # Record mapping source
                return config

        # 4. Return to default configuration
        logger.warning(f"未找到模型 {model_name} 的配置，使用默认配置")
        return {
            "model_name": model_name,
            "capability_level": 2,
            "suitable_roles": [ModelRole.BOTH],
            "features": [ModelFeature.TOOL_CALLING],
            "recommended_depths": ["快速", "基础", "标准"],
            "performance_metrics": {"speed": 3, "cost": 3, "quality": 3}
        }
    
    def validate_model_pair(
        self,
        quick_model: str,
        deep_model: str,
        research_depth: str
    ) -> Dict[str, Any]:
        """
        Verify that a model pair is appropriate for the current depth of analysis

        Args:
            quick_model: Quickly analyze model names
            deep_model: In-depth analysis model name
            research_depth: Research depth (Quick/Basic/Standard/In-depth/Comprehensive)

        Returns:
            Dictionary of verification results, including valid, warnings, recommendations
        """
        logger.info(f"🔍 Start validating the model pair: quick={quick_model}, deep={deep_model}, depth={research_depth}")

        requirements = ANALYSIS_DEPTH_REQUIREMENTS.get(research_depth, ANALYSIS_DEPTH_REQUIREMENTS["标准"])
        logger.info(f"🔍 分析深度要求: {requirements}")

        quick_config = self.get_model_config(quick_model)
        deep_config = self.get_model_config(deep_model)

        logger.info(f"🔍 快速模型配置: {quick_config}")
        logger.info(f"🔍 深度模型配置: {deep_config}")

        result = {
            "valid": True,
            "warnings": [],
            "recommendations": []
        }
        
        # Check out the quick model
        quick_level = quick_config["capability_level"]
        logger.info(f"🔍 Check Quick Model Capability Level: {quick_level} >= {requirements['quick_model_min']}?")
        if quick_level < requirements["quick_model_min"]:
            warning = f"⚠️ 快速模型 {quick_model} (能力等级{quick_level}) 低于 {research_depth} 分析的建议等级({requirements['quick_model_min']})"
            result["warnings"].append(warning)
            logger.warning(warning)

        # Check out Quick Model Role Adaptation
        quick_roles = quick_config.get("suitable_roles", [])
        logger.info(f"🔍 检查快速模型角色: {quick_roles}")
        if ModelRole.QUICK_ANALYSIS not in quick_roles and ModelRole.BOTH not in quick_roles:
            warning = f"💡 模型 {quick_model} 不是为快速分析优化的，可能影响数据收集效率"
            result["warnings"].append(warning)
            logger.warning(warning)

        # Check if the express model supports tool calls
        quick_features = quick_config.get("features", [])
        logger.info(f"🔍 检查快速模型特性: {quick_features}")
        if ModelFeature.TOOL_CALLING not in quick_features:
            result["valid"] = False
            warning = f"❌ 快速模型 {quick_model} 不支持工具调用，无法完成数据收集任务"
            result["warnings"].append(warning)
            logger.error(warning)

        # Check the deep model
        deep_level = deep_config["capability_level"]
        logger.info(f"🔍 Check deep model capability level: {deep_level} >= {requirements['deep_model_min']}?")
        if deep_level < requirements["deep_model_min"]:
            result["valid"] = False
            warning = f"❌ 深度模型 {deep_model} (能力等级{deep_level}) 不满足 {research_depth} 分析的最低要求(等级{requirements['deep_model_min']})"
            result["warnings"].append(warning)
            logger.error(warning)
            result["recommendations"].append(
                self._recommend_model("deep", requirements["deep_model_min"])
            )

        # Checking Deep Model Role Adaptation
        deep_roles = deep_config.get("suitable_roles", [])
        logger.info(f"🔍 检查深度模型角色: {deep_roles}")
        if ModelRole.DEEP_ANALYSIS not in deep_roles and ModelRole.BOTH not in deep_roles:
            warning = f"💡 模型 {deep_model} 不是为深度推理优化的，可能影响分析质量"
            result["warnings"].append(warning)
            logger.warning(warning)

        # Check required attributes
        logger.info(f"🔍 检查必需特性: {requirements['required_features']}")
        for feature in requirements["required_features"]:
            if feature == ModelFeature.REASONING:
                deep_features = deep_config.get("features", [])
                logger.info(f"🔍 Check deep model inference capabilities: {deep_features}")
                if feature not in deep_features:
                    warning = f"💡 {research_depth} The analysis recommends using deep models with strong inference capabilities"
                    result["warnings"].append(warning)
                    logger.warning(warning)

        logger.info(f"🔍 验证结果: valid={result['valid']}, warnings={len(result['warnings'])}条")
        logger.info(f"🔍 警告详情: {result['warnings']}")

        return result
    
    def recommend_models_for_depth(
        self,
        research_depth: str
    ) -> Tuple[str, str]:
        """
        Recommend appropriate model pairs based on depth of analysis
        
        Args:
            research_depth: Research depth (Quick/Basic/Standard/In-depth/Comprehensive)
            
        Returns:
            (quick_model, deep_model) tuple
        """
        requirements = ANALYSIS_DEPTH_REQUIREMENTS.get(research_depth, ANALYSIS_DEPTH_REQUIREMENTS["标准"])
        
        # Get all enabled models
        try:
            llm_configs = unified_config.get_llm_configs()
            enabled_models = [c for c in llm_configs if c.enabled]
        except Exception as e:
            logger.error(f"获取模型配置失败: {e}")
            # Use default model
            return self._get_default_models()
        
        if not enabled_models:
            logger.warning("No models enabled, use default configuration")
            return self._get_default_models()
        
        # Filter models suitable for rapid analysis
        quick_candidates = []
        for m in enabled_models:
            roles = getattr(m, 'suitable_roles', [ModelRole.BOTH])
            level = getattr(m, 'capability_level', 2)
            features = getattr(m, 'features', [])
            
            if (ModelRole.QUICK_ANALYSIS in roles or ModelRole.BOTH in roles) and \
               level >= requirements["quick_model_min"] and \
               ModelFeature.TOOL_CALLING in features:
                quick_candidates.append(m)
        
        # Screen models suitable for in-depth analysis
        deep_candidates = []
        for m in enabled_models:
            roles = getattr(m, 'suitable_roles', [ModelRole.BOTH])
            level = getattr(m, 'capability_level', 2)
            
            if (ModelRole.DEEP_ANALYSIS in roles or ModelRole.BOTH in roles) and \
               level >= requirements["deep_model_min"]:
                deep_candidates.append(m)
        
        # Sort by cost performance (capability level vs cost)
        quick_candidates.sort(
            key=lambda x: (
                getattr(x, 'capability_level', 2),
                -getattr(x, 'performance_metrics', {}).get("cost", 3) if getattr(x, 'performance_metrics', None) else 0
            ),
            reverse=True
        )
        
        deep_candidates.sort(
            key=lambda x: (
                getattr(x, 'capability_level', 2),
                getattr(x, 'performance_metrics', {}).get("quality", 3) if getattr(x, 'performance_metrics', None) else 0
            ),
            reverse=True
        )
        
        # Choose the best model
        quick_model = quick_candidates[0].model_name if quick_candidates else None
        deep_model = deep_candidates[0].model_name if deep_candidates else None
        
        # If no suitable one is found, use the system default
        if not quick_model or not deep_model:
            return self._get_default_models()
        
        logger.info(
            f"🤖 为 {research_depth} 分析推荐模型: "
            f"quick={quick_model} (role:Quick analysis), "
            f"deep={deep_model} (role:deep reasoning)"
        )
        
        return quick_model, deep_model
    
    def _get_default_models(self) -> Tuple[str, str]:
        """获取默认模型对"""
        try:
            quick_model = unified_config.get_quick_analysis_model()
            deep_model = unified_config.get_deep_analysis_model()
            logger.info(f"Use system default model: quick={quick_model}, deep={deep_model}")
            return quick_model, deep_model
        except Exception as e:
            logger.error(f"获取默认模型失败: {e}")
            return "qwen-turbo", "qwen-plus"
    
    def _recommend_model(self, model_type: str, min_level: int) -> str:
        """推荐满足要求的模型"""
        try:
            llm_configs = unified_config.get_llm_configs()
            for config in llm_configs:
                if config.enabled and getattr(config, 'capability_level', 2) >= min_level:
                    display_name = config.model_display_name or config.model_name
                    return f"建议使用: {display_name}"
        except Exception as e:
            logger.warning(f"推荐模型失败: {e}")
        
        return "建议升级模型配置"


# Singleton
_model_capability_service = None


def get_model_capability_service() -> ModelCapabilityService:
    """获取模型能力服务单例"""
    global _model_capability_service
    if _model_capability_service is None:
        _model_capability_service = ModelCapabilityService()
    return _model_capability_service


# === prompt_assembly_service.py ===
"""
Hierarchical prompt word assembly service

base template + Industry portrait + individual stock portrait + ability block + Task blocks are assembled into the final prompt.

Core responsibilities:
- Merge industry portraits and individual stock portraits (inherit/overwrite/addition)
- generate analysis_context_block
- generate capability_block
- generate task_block
- Complete assembly final Prompt
"""

import logging
from typing import Optional, Dict, Any, List

def AnalysisProfileService(*a, **kw):
    from app.services.analysis_services import AnalysisProfileService as _APS
    return _APS(*a, **kw)
from tradingagents.utils.template_client import get_template_client

logger = logging.getLogger(__name__)


class PromptAssemblyService:
    """
    Hierarchical prompt word assembly service
    
    Implement design documentation §5 Runtime assembly rules for:
    - Industry Analysis: Basic Template → scenario strategy → ability block → Industry portrait block → task block
    - Individual Stock Analysis: Basic Template → scenario strategy → ability block → Industry portrait summary → individual stock portrait block → task block
    """
    
    def __init__(self):
        self.profile_service = AnalysisProfileService()
        self.policy_service = PromptInjectionPolicyService()
        self.template_client = get_template_client()
    
    # ==================== public interface ====================
    
    def _get_policy_sync(
        self,
        agent_type: Optional[str],
        agent_name: Optional[str],
        scope: str,
    ):
        """Get the injection strategy synchronously and return if there is no strategy. None"""
        if not agent_type or not agent_name:
            return None
        return self.policy_service.get_policy_by_agent_scope_sync(
            agent_type=agent_type,
            agent_name=agent_name,
            scope=scope,
        )

    def build_analysis_context_block(
        self,
        analysis_type: str,
        industry: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        policy_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build analysis_context_block (analysis context block)
        
        Args:
            analysis_type: Analysis type "general" / "industry" / "stock"
            industry: Industry name
            stock_symbol: Stock code
            agent_type: Agent Type (optional, used for policy queries)
            agent_name: Agent Name (optional, used for policy queries)
        
        Returns:
            Formatted analysis context block text
        """
        if analysis_type == "general":
            return ""

        # Phase 2: policy control - injection_mode=none not injected
        policy = policy_override if policy_override is not None else self._get_policy_sync(agent_type, agent_name, analysis_type)
        if policy and policy.get("injection_mode") == "none":
            logger.info(f"📋 [策略] {agent_type}/{agent_name} scope={analysis_type} injection_mode=none，跳过上下文块")
            return ""
        
        blocks = []
        
        # 1. Get industry portraits
        industry_profile = None
        if industry:
            industry_profile = self._get_industry_profile_sync(industry)
        
        # 2. Get individual stock portraits
        stock_profile = None
        if stock_symbol and analysis_type == "stock":
            stock_profile = self._get_stock_profile_sync(stock_symbol)
        
        # 3. Merge portraits (policy control inherit_industry_for_stock, include_comparable_companies)
        inherit_industry = policy.get("inherit_industry_for_stock", True) if policy else True
        include_comparable = policy.get("include_comparable_companies", True) if policy else True
        merged = self._merge_profiles(
            industry_profile,
            stock_profile,
            inherit_industry_for_stock=inherit_industry,
            include_comparable_companies=include_comparable,
        )
        
        # 3.5 Strategy:injection_mode=summary When doing summary compression (design document §4.2) 
        injection_mode = (policy.get("injection_mode") if policy else None) or "full"
        if injection_mode == "summary":
            merged = self._summarize_merged_profile(merged)
            logger.info("📋 [analysis_context_block] Using summary mode, dimensions and text are compressed")
        
        # 4. Formatted output
        if merged.get("dimensions"):
            blocks.append("## 分析维度\n")
            for dim in merged["dimensions"]:
                importance = dim.get("importance", "high")
                name = dim.get("name", "")
                desc = dim.get("description", "")
                source = dim.get("source", "")
                source_hint = f"（来自{source}）" if source else ""
                blocks.append(f"- **{name}** [{importance}]{source_hint}: {desc}")
        
        if merged.get("key_metrics"):
            blocks.append("\n## 关键指标\n")
            blocks.append(", ".join(merged["key_metrics"]))
        
        if merged.get("analysis_focus"):
            blocks.append("\n## 分析重点\n")
            blocks.append(merged["analysis_focus"])
        
        if include_comparable and merged.get("comparable_companies"):
            blocks.append("\n## 可比公司\n")
            blocks.append(", ".join(merged["comparable_companies"]))
        
        if merged.get("special_notes"):
            blocks.append("\n## 特殊说明\n")
            blocks.append(merged["special_notes"])
        
        result = "\n".join(blocks)
        if result:
            logger.info(f"📋 [analysis_context_block] Generate length: {len(result)}")
        return result
    
    def build_capability_block(
        self,
        analysis_type: str,
        industry: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        policy_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build capability_block (capability boundary specification block)
        
        Tell the model which data can be used directly and which needs to be expressed conservatively
        
        Args:
            analysis_type: Analysis type
            industry: Industry name
            stock_symbol: Stock code
            agent_type: Agent Type (optional, used for policy queries)
            agent_name: Agent Name (optional, used for policy queries)
        
        Returns:
            Formatted capability boundary description text
        """
        # Phase 2: policy control - include_capability_block=False not injected
        policy = policy_override if policy_override is not None else self._get_policy_sync(agent_type, agent_name, analysis_type)
        if policy and policy.get("include_capability_block") is False:
            logger.info(f"🔧 [策略] {agent_type}/{agent_name} scope={analysis_type} include_capability_block=False，跳过能力块")
            return ""

        # Collection capability snapshot
        capability = self._collect_capability_snapshot_sync()
        
        blocks = []
        blocks.append("## 数据能力边界\n")
        
        # Can be used directly
        builtin = capability.get("builtin_sources", [])
        if builtin:
            blocks.append("### Ready-to-use data capabilities")
            for src in builtin[:4]:
                blocks.append(f"- {src.get('label')}: {src.get('description')[:80]}")
        
        # Can be obtained indirectly
        mcp_servers = capability.get("enabled_mcp_servers", [])
        skills = capability.get("active_skills", [])
        if mcp_servers or skills:
            blocks.append("\n### Indirectly accessible data capabilities")
            if mcp_servers:
                blocks.append("- MCP 服务:")
                for srv in mcp_servers[:3]:
                    desc = srv.get('description', '')[:60]
                    if not desc:
                        desc = f"{srv.get('tool_count', 0)} 个工具"
                    blocks.append(f"  - {srv.get('name')}: {desc}")
            if skills:
                blocks.append("- Skill 能力:")
                for sk in skills[:3]:
                    blocks.append(f"  - {sk.get('name')}: {sk.get('description', '')[:60]}")
        
        # Currently missing reminders (policy can turn off include_external_gap_notice)
        if policy is None or policy.get("include_external_gap_notice", True):
            blocks.append("\n### 数据缺口提醒")
            blocks.append("- If you need unstructured information such as operational indicators and industry external data, it is recommended to combine MCP/Skill or external data sources.")
            blocks.append("- Qualitative indicators (such as brand power, management execution ability, etc.) need to rely on professional judgment or external research reports")
        
        result = "\n".join(blocks)
        logger.info(f"🔧 [capability_block] Generate length: {len(result)}")
        return result
    
    def build_task_block(
        self,
        task_description: str,
        analysis_type: str,
    ) -> str:
        """
        Build task_block (task instruction block)
        
        Args:
            task_description: Current task description
            analysis_type: Analysis type
        
        Returns:
            Formatted task block text
        """
        if not task_description:
            return ""
        
        type_labels = {
            "general": "通用分析",
            "industry": "行业分析",
            "stock": "个股分析",
        }
        
        blocks = []
        blocks.append("## 当前分析任务\n")
        blocks.append(f"**分析类型**: {type_labels.get(analysis_type, analysis_type)}\n")
        blocks.append(f"**任务目标**:\n{task_description}")
        
        result = "\n".join(blocks)
        logger.info(f"🎯 [task_block] Generate length: {len(result)}")
        return result
    
    def assemble_prompt(
        self,
        agent_type: str,
        agent_name: str,
        analysis_type: str = "general",
        industry: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        task_description: str = "",
        include_capability: bool = True,
        variables: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        node_id: Optional[str] = None,
        template_override: Optional[Dict[str, Any]] = None,
        policy_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Complete assembly entrance: select template → Generate three blocks → variable substitution → return final Prompt
        
        Args:
            agent_type: Agent Type
            agent_name: Agent Name
            analysis_type: Analysis type "general" / "industry" / "stock"
            industry: Industry name
            stock_symbol: Stock code
            task_description: Task description
            include_capability: Whether to include ability blocks
            variables: Dictionary of extra variables
        
        Returns:
            {
                "final_prompt": str,          # finally complete Prompt
                "sections": Dict[str, str],   # Content of each paragraph
                "sources": Dict[str, str],    # Source of each paragraph
                "template_id": str,           # Template used ID
                "profile_used": Dict,         # Image information used
                "capability_gaps": List[str], # Ability gap reminder
            }
        """
        # 1. Get template
        template = template_override or self.template_client.get_effective_template(
            agent_type,
            agent_name,
            workflow_id=workflow_id,
            node_id=node_id,
        )
        if not template:
            logger.warning(f"⚠️ 未找到模板: {agent_type}/{agent_name}")
            template = {}
        
        template_id = template.get("template_id", "")
        
        # 2. Get Strategy (Phase 2)
        policy_override = (policy_overrides or {}).get(analysis_type)
        policy = policy_override if policy_override is not None else self._get_policy_sync(agent_type, agent_name, analysis_type)
        effective_include_capability = include_capability
        if policy and policy.get("include_capability_block") is False:
            effective_include_capability = False

        # 3. Generate three blocks (pass in agent information for policy control)
        context_block = self.build_analysis_context_block(
            analysis_type, industry, stock_symbol,
            agent_type=agent_type, agent_name=agent_name,
            policy_override=policy,
        )
        capability_block = self.build_capability_block(
            analysis_type, industry, stock_symbol,
            agent_type=agent_type, agent_name=agent_name,
            policy_override=policy,
        ) if effective_include_capability else ""
        task_block = self.build_task_block(task_description, analysis_type)
        
        # 4. Prepare variables (contains three new blocks)
        final_variables = variables or {}
        final_variables["analysis_context_block"] = context_block
        final_variables["capability_block"] = capability_block
        final_variables["task_block"] = task_block
        
        # 4. Format template
        formatted = self.template_client.format_template(template, final_variables)
        
        # 4.5 Strategy inject_position: If the template does not contain placeholders, append the block to the field specified by the strategy (design document §7.2) 
        inject_pos = (policy.get("inject_position") if policy else None) or "analysis_requirements"
        for key in ("system_prompt", "analysis_requirements", "constraints"):
            if key not in formatted or formatted[key] is None:
                formatted[key] = ""
        if context_block and inject_pos in formatted and context_block[:40] not in (formatted.get(inject_pos) or ""):
            formatted[inject_pos] = (formatted[inject_pos] or "").strip() + "\n\n" + context_block
        if task_block and "analysis_requirements" in formatted and task_block[:40] not in (formatted.get("analysis_requirements") or ""):
            formatted["analysis_requirements"] = (formatted["analysis_requirements"] or "").strip() + "\n\n" + task_block
        if capability_block and "constraints" in formatted and capability_block[:40] not in (formatted.get("constraints") or ""):
            formatted["constraints"] = (formatted["constraints"] or "").strip() + "\n\n" + capability_block
        
        # 5. Assembly final Prompt
        parts = []
        sections = {}
        sources = {}
        
        if formatted.get("system_prompt"):
            parts.append(formatted["system_prompt"])
            sections["system_prompt"] = formatted["system_prompt"]
            sources["system_prompt"] = "基础角色模板"
        
        if formatted.get("tool_guidance"):
            parts.append("\n\n" + formatted["tool_guidance"])
            sections["tool_guidance"] = formatted["tool_guidance"]
            sources["tool_guidance"] = "基础角色模板"
        
        # analysis_requirements bear context_block + task_block
        if formatted.get("analysis_requirements"):
            parts.append("\n\n" + formatted["analysis_requirements"])
            sections["analysis_requirements"] = formatted["analysis_requirements"]
            sources["analysis_requirements"] = "基础模板 + 上下文注入"
        
        if formatted.get("output_format"):
            parts.append("\n\n" + formatted["output_format"])
            sections["output_format"] = formatted["output_format"]
            sources["output_format"] = "基础角色模板"
        
        # constraints bear capability_block
        if formatted.get("constraints"):
            parts.append("\n\n" + formatted["constraints"])
            sections["constraints"] = formatted["constraints"]
            sources["constraints"] = "Basic template + Capability Boundary Injection"
        
        # Record three sources
        if context_block:
            sections["analysis_context_block"] = context_block
            sources["analysis_context_block"] = f"画像服务（行业={industry or 'N/A'}, 个股={stock_symbol or 'N/A'}）"
        if capability_block:
            sections["capability_block"] = capability_block
            sources["capability_block"] = "能力评估服务"
        if task_block:
            sections["task_block"] = task_block
            sources["task_block"] = "任务描述"
        
        final_prompt = "\n".join(parts)
        
        # 6. Collection capacity gap
        capability_gaps = self._collect_capability_gaps(analysis_type, industry, stock_symbol)
        
        # 7. Collect and use portrait information
        profile_used = {
            "industry": industry,
            "stock_symbol": stock_symbol,
            "industry_profile_found": bool(self._get_industry_profile_sync(industry)) if industry else False,
            "stock_profile_found": bool(self._get_stock_profile_sync(stock_symbol)) if stock_symbol else False,
        }
        
        logger.info(
            f"✅ [assemble_prompt] 组装完成: {agent_type}/{agent_name}, "
            f"Type={analysis_type}, final length={len(final_prompt)}"
        )
        
        return {
            "final_prompt": final_prompt,
            "sections": sections,
            "sources": sources,
            "template_id": template_id,
            "profile_used": profile_used,
            "capability_gaps": capability_gaps,
        }
    
    # ==================== internal tools ====================
    
    def _get_industry_profile_sync(self, industry: str) -> Optional[Dict]:
        """同步获取行业画像"""
        if not industry:
            return None
        try:
            result = AnalysisProfileService.get_industry_dimensions_sync(industry)
            if result:
                # Rebuild profile structure
                from app.core.database import get_mongo_db_sync
                db = get_mongo_db_sync()
                doc = db["industry_analysis_profiles"].find_one(
                    {"industry": industry, "is_active": True}
                )
                if doc:
                    doc["id"] = str(doc.pop("_id"))
                    return doc
        except Exception as e:
            logger.warning(f"⚠️ 获取行业画像失败: {e}")
        return None
    
    def _get_stock_profile_sync(self, stock_symbol: str) -> Optional[Dict]:
        """同步获取个股画像"""
        if not stock_symbol:
            return None
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            doc = db["stock_analysis_profiles"].find_one(
                {"stock_symbol": stock_symbol, "is_active": True}
            )
            if doc:
                doc["id"] = str(doc.pop("_id"))
                return doc
        except Exception as e:
            logger.warning(f"⚠️ 获取个股画像失败: {e}")
        return None
    
    def _merge_profiles(
        self,
        industry_profile: Optional[Dict],
        stock_profile: Optional[Dict],
        inherit_industry_for_stock: bool = True,
        include_comparable_companies: bool = True,
    ) -> Dict[str, Any]:
        """
        Merge industry portraits and individual stock portraits
        
        Rules (corresponding to design documents §6) :
        1. inherit: The analysis dimensions and key indicators in the industry portrait are inherited by default.
        2. append: Individual stocks can add exclusive dimensions
        3. override: Individual stocks can rewrite the description or importance of an industry dimension
        4. disable: Individual stocks can explicitly turn off the default dimensions of certain industries
        
        Args:
            industry_profile: Industry portrait
            stock_profile: individual stock portrait
            inherit_industry_for_stock: Whether individual stock scenarios inherit industry portraits (strategy control)
            include_comparable_companies: Whether to include comparable companies (strategic control)
        
        Returns:
            Combined structured content
        """
        result = {
            "dimensions": [],
            "key_metrics": [],
            "analysis_focus": "",
            "comparable_companies": [],
            "special_notes": "",
        }
        
        # 1. Inherited from industry portraits (individual stock scenarios and inherit_industry_for_stock=False skip when)
        if industry_profile and not (stock_profile and not inherit_industry_for_stock):
            dims = industry_profile.get("analysis_dimensions", [])
            for d in dims:
                result["dimensions"].append({
                    **d,
                    "source": "行业画像",
                })
            result["key_metrics"] = list(industry_profile.get("key_metrics", []))
            result["analysis_focus"] = industry_profile.get("analysis_focus", "")
            result["comparable_companies"] = list(industry_profile.get("comparable_companies", []))
        
        # 2. Apply stock portrait overlay
        if stock_profile:
            stock_dims = stock_profile.get("analysis_dimensions", [])
            stock_overrides = stock_profile.get("dimension_overrides", {})  # {Dimension name: {action: "override"/"disable", ...}}
            
            # Handle append/overwrite
            for sd in stock_dims:
                name = sd.get("name", "")
                existing_idx = next(
                    (i for i, d in enumerate(result["dimensions"]) if d.get("name") == name),
                    None
                )
                
                if existing_idx is not None:
                    # override: Overwrite existing dimensions
                    result["dimensions"][existing_idx] = {
                        **result["dimensions"][existing_idx],
                        **sd,
                        "source": "个股画像覆盖",
                    }
                else:
                    # append: Add new dimensions
                    result["dimensions"].append({
                        **sd,
                        "source": "个股画像追加",
                    })
            
            # Process disable
            for dim_name, override_info in stock_overrides.items():
                if override_info.get("action") == "disable":
                    result["dimensions"] = [
                        d for d in result["dimensions"]
                        if d.get("name") != dim_name
                    ]
            
            # Combine key metrics
            stock_metrics = stock_profile.get("key_metrics", [])
            for m in stock_metrics:
                if m not in result["key_metrics"]:
                    result["key_metrics"].append(m)
            
            # Special instructions
            if stock_profile.get("special_notes"):
                result["special_notes"] = stock_profile["special_notes"]

        # Policy Control: Empty when no comparable companies are included
        if not include_comparable_companies:
            result["comparable_companies"] = []
        
        return result
    
    def _summarize_merged_profile(self, merged: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summary mode: compress the merged portrait, control token (design document §4.2 injection_mode=summary) 
        - A maximum of 5 analysis dimensions are allowed, and the description is truncated to 50 words.
        - Up to 5 key indicators
        - Analysis highlights truncated to 100 words
        - Up to 3 comparable companies
        - Special instructions truncated to 80 words
        """
        out = dict(merged)
        summary_desc_len = 50
        summary_focus_len = 100
        summary_notes_len = 80
        max_dimensions = 5
        max_key_metrics = 5
        max_comparable = 3

        if out.get("dimensions"):
            out["dimensions"] = [
                {
                    **d,
                    "description": (d.get("description") or "")[:summary_desc_len]
                    + ("..." if len((d.get("description") or "")) > summary_desc_len else ""),
                }
                for d in out["dimensions"][:max_dimensions]
            ]
        if out.get("key_metrics"):
            out["key_metrics"] = list(out["key_metrics"][:max_key_metrics])
        if out.get("analysis_focus"):
            s = out["analysis_focus"]
            out["analysis_focus"] = s[:summary_focus_len] + ("..." if len(s) > summary_focus_len else "")
        if out.get("comparable_companies"):
            out["comparable_companies"] = list(out["comparable_companies"][:max_comparable])
        if out.get("special_notes"):
            s = out["special_notes"]
            out["special_notes"] = s[:summary_notes_len] + ("..." if len(s) > summary_notes_len else "")
        return out
    
    def _collect_capability_snapshot_sync(self) -> Dict[str, Any]:
        """同步收集能力快照"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            
            # Collection logic using the capabilities of AnalysisProfileService
            service = AnalysisProfileService()
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If there is an event loop, use synchronization
                    return self._collect_capability_sync_impl(db)
                else:
                    return loop.run_until_complete(service._collect_capability_snapshot(db))
            except RuntimeError:
                return self._collect_capability_sync_impl(db)
        except Exception as e:
            logger.warning(f"⚠️ 收集能力快照失败: {e}")
            return {"builtin_sources": [], "enabled_mcp_servers": [], "active_skills": []}
    
    def _collect_capability_sync_impl(self, db) -> Dict[str, Any]:
        """同步收集能力快照的实现"""
        from app.services.analysis_profile_service import BUILTIN_SOURCE_DEFINITIONS
        
        builtin_sources = [
            {"key": item["key"], "label": item["label"], "description": item["description"]}
            for item in BUILTIN_SOURCE_DEFINITIONS
        ]
        
        enabled_mcp_servers = []
        try:
            for doc in db["mcp_server_configs"].find({"is_enabled": True}):
                tools = doc.get("discovered_tools", []) or []
                enabled_mcp_servers.append({
                    "server_id": doc.get("server_id", ""),
                    "name": doc.get("name", ""),
                    "description": doc.get("description", ""),
                    "tool_count": len(tools),
                })
        except Exception:
            pass
        
        active_skills = []
        try:
            for doc in db["external_skills"].find({"status": "active"}):
                active_skills.append({
                    "tool_id": doc.get("tool_id", ""),
                    "name": doc.get("display_name", ""),
                    "description": doc.get("description", ""),
                })
        except Exception:
            pass
        
        return {
            "builtin_sources": builtin_sources,
            "enabled_mcp_servers": enabled_mcp_servers,
            "active_skills": active_skills,
        }
    
    def _collect_capability_gaps(
        self,
        analysis_type: str,
        industry: Optional[str],
        stock_symbol: Optional[str],
    ) -> List[str]:
        """收集能力缺口提醒"""
        gaps = []
        
        # Check whether the industry portrait exists
        if industry and analysis_type in ("industry", "stock"):
            profile = self._get_industry_profile_sync(industry)
            if not profile:
                gaps.append(f"行业「{industry}」暂无画像配置，建议先创建行业分析画像")
        
        # Check whether the stock image exists
        if stock_symbol and analysis_type == "stock":
            profile = self._get_stock_profile_sync(stock_symbol)
            if not profile:
                gaps.append(f"个股「{stock_symbol}」暂无画像配置，将使用行业画像作为默认框架")
        
        # Check MCP/Skill availability
        capability = self._collect_capability_snapshot_sync()
        if not capability.get("enabled_mcp_servers"):
            gaps.append("No MCP servers are currently enabled, and some data capabilities may be limited.")
        
        return gaps


# ==================== Global singleton ====================

_assembly_service: Optional[PromptAssemblyService] = None


def get_prompt_assembly_service() -> PromptAssemblyService:
    """Get the PromptAssemblyService global singleton"""
    global _assembly_service
    if _assembly_service is None:
        _assembly_service = PromptAssemblyService()
    return _assembly_service

# === prompt_injection_policy_service.py ===
"""
Prompt Inject strategy service

CRUD operations that manage the prompt_injection_policies collection,
Support pressing Agent + Scenario query strategy.
"""

import logging
from typing import Optional, List, Dict, Any

try:
    from bson import ObjectId
except ImportError:
    ObjectId = str
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

COLLECTION = "prompt_injection_policies"


class PromptInjectionPolicyService:
    """Prompt Inject strategy service"""

    async def list_policies(
        self,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List query, supports agent_type / agent_name / scope filtering
        """
        db = get_mongo_db()
        query = {}
        if agent_type:
            query["agent_type"] = agent_type
        if agent_name:
            query["agent_name"] = agent_name
        if scope:
            query["scope"] = scope

        cursor = db[COLLECTION].find(query).sort([
            ("agent_type", 1),
            ("agent_name", 1),
            ("scope", 1),
        ])
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
            results.append(doc)
        return results

    async def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        """获取单个策略"""
        db = get_mongo_db()
        try:
            doc = await db[COLLECTION].find_one({"_id": ObjectId(policy_id)})
        except Exception:
            return None
        if doc:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
        return doc

    async def get_policy_by_agent_scope(
        self,
        agent_type: str,
        agent_name: str,
        scope: str,
    ) -> Optional[Dict[str, Any]]:
        """
        press Agent + Scenario acquisition strategy (for assembly services, asynchronous)
        """
        db = get_mongo_db()
        doc = await db[COLLECTION].find_one({
            "agent_type": agent_type,
            "agent_name": agent_name,
            "scope": scope,
            "enabled": True,
        })
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    def get_policy_by_agent_scope_sync(
        self,
        agent_type: str,
        agent_name: str,
        scope: str,
    ) -> Optional[Dict[str, Any]]:
        """
        press Agent + Scene acquisition strategy (synchronous version, used for synchronous calls such as base.py)
        """
        from app.core.database import get_mongo_db_sync
        db = get_mongo_db_sync()
        try:
            doc = db[COLLECTION].find_one({
                "agent_type": agent_type,
                "agent_name": agent_name,
                "scope": scope,
                "enabled": True,
            })
            if doc:
                doc["id"] = str(doc.pop("_id"))
            return doc
        except Exception as e:
            logger.warning(f"⚠️ 获取注入策略失败: {e}")
            return None

    async def create_policy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建策略"""
        db = get_mongo_db()
        now = now_tz()
        data["created_at"] = now
        data["updated_at"] = now
        data.setdefault("enabled", True)
        data.setdefault("injection_mode", "summary")
        data.setdefault("inherit_industry_for_stock", True)
        data.setdefault("include_capability_block", True)
        data.setdefault("include_external_gap_notice", True)
        data.setdefault("include_comparable_companies", True)
        data.setdefault("inject_position", "analysis_requirements")
        data.setdefault("version", 1)

        result = await db[COLLECTION].insert_one(data)
        data["id"] = str(result.inserted_id)
        logger.info(f"✅ 创建注入策略: {data.get('agent_type')}/{data.get('agent_name')}/{data.get('scope')}")
        return data

    async def update_policy(self, policy_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新策略"""
        db = get_mongo_db()
        # Exclude non-updatable fields
        update_data = {k: v for k, v in data.items() if k not in ("id", "_id", "agent_type", "agent_name", "scope", "created_at")}
        if not update_data:
            return await self.get_policy(policy_id)
        update_data["updated_at"] = now_tz()

        try:
            result = await db[COLLECTION].update_one(
                {"_id": ObjectId(policy_id)},
                {"$set": update_data}
            )
        except Exception:
            return None
        if result.modified_count > 0:
            logger.info(f"✅ 更新注入策略: {policy_id}")
            return await self.get_policy(policy_id)
        return await self.get_policy(policy_id)

    async def delete_policy(self, policy_id: str) -> bool:
        """删除策略"""
        db = get_mongo_db()
        try:
            result = await db[COLLECTION].delete_one({"_id": ObjectId(policy_id)})
            return result.deleted_count > 0
        except Exception:
            return False

    async def upsert_policy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a policy (press agent_type + agent_name + scope only)
        for initialization script
        """
        db = get_mongo_db()
        agent_type = data.get("agent_type")
        agent_name = data.get("agent_name")
        scope = data.get("scope", "general")
        if not agent_type or not agent_name:
            raise ValueError("agent_type and agent_name are required")

        existing = await db[COLLECTION].find_one({
            "agent_type": agent_type,
            "agent_name": agent_name,
            "scope": scope,
        })
        now = now_tz()
        if existing:
            update_data = {
                "enabled": data.get("enabled", True),
                "injection_mode": data.get("injection_mode", "summary"),
                "inherit_industry_for_stock": data.get("inherit_industry_for_stock", True),
                "include_capability_block": data.get("include_capability_block", True),
                "include_external_gap_notice": data.get("include_external_gap_notice", True),
                "include_comparable_companies": data.get("include_comparable_companies", True),
                "inject_position": data.get("inject_position", "analysis_requirements"),
                "version": existing.get("version", 1),
                "updated_at": now,
            }
            await db[COLLECTION].update_one(
                {"_id": existing["_id"]},
                {"$set": update_data}
            )
            existing["id"] = str(existing.pop("_id"))
            existing.update(update_data)
            return existing
        else:
            data["created_at"] = now
            data["updated_at"] = now
            data.setdefault("enabled", True)
            data.setdefault("injection_mode", "summary")
            data.setdefault("inherit_industry_for_stock", True)
            data.setdefault("include_capability_block", True)
            data.setdefault("include_external_gap_notice", True)
            data.setdefault("include_comparable_companies", True)
            data.setdefault("inject_position", "analysis_requirements")
            data.setdefault("scope", scope)
            data.setdefault("version", 1)
            result = await db[COLLECTION].insert_one(data)
            data["id"] = str(result.inserted_id)
            return data

# === system_prompt_seed_service.py ===
"""The system default prompt word template seed service.

Unify the hard-coded Agent fallback prompt words in the code into the database prompt_templates collection,
Achieve unified management of prompt words. Automatic synchronization at system startup ensures there is always a baseline version in the database.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)

SYSTEM_SEED_REMARK = "system_seed:agent_default_prompts:v1"


def _build_system_prompt_templates() -> List[Dict[str, Any]]:
    """Build system default prompt word templates for all built-in Agents"""
    return [
        # --- See below for template list ---
        {
            "agent_type": "analysts_v2",
            "agent_name": "market_analyst_v2",
            "template_name": "系统默认-市场分析师",
            "content": {
                "system_prompt": """you are a professional{market_type}Market analyst, good at technical analysis.

Your responsibilities:
1. Analyze stock price trends (increases and decreases, trend direction)
2. Analyze technical indicators (MA, MACD, RSI, KDJ, etc.)
3. Analyze trading volume (increasing volume, shrinking volume, volume-price relationship)
4. Comprehensively judge market sentiment and trends

Analysis requirements:
- Objective, professional and data-based
- Point out key technical signals
- Give clear trend judgments
- Use Chinese output

Output format:
Please output the analysis report in a structured manner, including:
- Price trend analysis
- Technical indicator analysis
- Volume analysis
- Comprehensive judgment""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "analysts_v2",
            "agent_name": "fundamentals_analyst_v2",
            "template_name": "系统默认-基本面分析师",
            "content": {
                "system_prompt": """You are a professional and objective stock fundamental analyst responsible for providing reviewable financial and operating evidence to the research process and conducting balanced financial analysis.

    Your task is:
    1. Use tools to obtain a company s overall fundamentals, most recent quarterly earnings details, cash flow information, and necessary peer valuation comparisons
    2. Analyze financial health, profitability, operating flexibility, operating quality and cash flow matching based on industry characteristics
    3. The context in which the valuation is assessed, describing the expectations reflected in market pricing and how these factors support or undermine the overall research conclusion
    4. Balance analysis of opportunity factors and risk factors, explain the key premises for establishing the conclusion and give a brief summary

    Requirements:
    - The analysis must be based on real data, and the model s own memory, common sense completion, or data that does not appear in the tool results must not be used to make judgments.
    - If the tool is missing a financial field, valuation field or peer data, you must explicitly write"Tool results not provided"or"This dimension still needs to be verified"
    - By default, fundamental research only uses historical financials, historical valuation ranges and disclosed operating data; even if the tool returns daily snapshots of current stock price, rise and fall, trading volume, current total market capitalization, etc., these fields must not be written into the text or used as the basis for conclusions.
    - The most explanatory indicators should be selected based on industry characteristics and data available from tools, and mechanical coverage of all common financial accounts is not required; if a certain type of indicator is not applicable to the current industry, do not directly write its lack as a risk or data gap
    - As long as the text cites PE,PE(TTM), PB, PS(TTM) or other valuation snapshots, the snapshot date corresponding to the valuation must also be stated; if the dates of different indicators are different, they should be stated separately and cannot be regarded as the same day by default.
    - If the valuation snapshot date in the tool results is earlier than the analysis date, the actual valuation snapshot date returned by the tool must be used and must not be written"As of analysis date"Or replace the valuation date with the analysis date
    - If the tool explicitly prompts"There is currently no daily frequency data after the close of the day."or"Executed based on the caliber of the previous available trading day", The text must clearly state that the closing data of the day has not yet stabilized. This valuation or peer analysis is completed based on the data of the previous available trading day. You cannot just change the date without explaining the reason.
    - When the above stable data rollback prompt appears, you must `## core observation` Article 1 or `## Valuation background` Write down this date and caliber description at the beginning, and don t just mention it sporadically later in the article.
    - If get_financial_statements or get_cash_flow_statement is given explicitly"Single quarter derivation"Fields, use these fields first to describe quarterly changes;"Original reporting period cumulative/snapshot"The field is mainly used to check the caliber
    - Fields such as operating income, net profit attributable to the parent company, and operating cash flow in the A-share quarterly financial report are understood by default based on the cumulative caliber of the reporting period. Q2/Q3/Q4 are not single-quarter values and cannot be directly added or directly written as quarter-by-quarter improvement in a single quarter.
    - Indicators such as ROE and net interest rate are understood by default as snapshots of indicators during the reporting period; if they are not clearly deduced, do not write them as single-quarter indicators.
    - If you need to discuss valuation, you can only focus on the historical valuation quantiles, historical ranges or peer relative valuations clearly provided by the tool; you are not allowed to write the current stock price and current total market capitalization into the company profile, core observations or summary.
    - Try to break down the valuation background into four layers: absolute valuation, relative valuation, historical quantiles and market expectations. Don t just write"Overestimation/Underestimation"
    - When explaining valuation premium or discount, give priority to explaining that it is more likely to correspond to profitability sustainability, cash recovery ability, competitive landscape or prosperous position.
    - It is allowed to quote real numerical values such as revenue growth, gross profit margin, net profit margin, ROE, ROA, operating cash flow, PE, PB, PEG, etc. to illustrate the facts, but it cannot be rewritten into a reasonable price, target price, safety margin or intervention range.
    - You can write:"2025Q4 The operating income and net profit attributable to the parent company belong to the cumulative caliber for the whole year. If we want to observe the changes in a single quarter, we need to further deduce it based on the Q3 cumulative value."
    - You can write:"The current ROE is a snapshot of the reporting period indicator and should not be directly interpreted as a single-quarter ROE."
    - You can write:"Applicable indicators should be selected based on industry characteristics; if a certain type of traditional turnover or liquidity indicator is not suitable for the current industry, there is no need to mechanically list it as a gap."
    - You can write:"The current PE and PB are both higher than the peer median, and the valuation premium is more likely to correspond to the market s pricing of earnings resilience and cash recovery capabilities."
    - You can write:"If the PEG is significantly higher than that of comparable companies, it means that the current valuation is more dependent on growth realization and the continuation of the boom."
    - You can write:"Operating cash flow is weaker than net profit, and the quality of profit realization still needs to be verified."
    - Do not write:"Net profit attributable to the parent company in the single quarter increased from 14.096 billion yuan in Q1 to 42.633 billion yuan in Q4."
    - Do not write:"Due to the lack of several common indicators, the current industry operating quality is weak."
    - Do not write:"The cumulative total for the whole year is approximately 10% after adding the net profits of the four quarters. 1,199.38 billion."
    - Do not write:"There is currently a clear margin of safety."
    - Do not write:"The turning point of the industry s prosperity is approaching, so it is recommended to make arrangements in advance."
    - Do not write:"The reasonable price range is 18-22 yuan."
    - Do not write:"If the valuation falls back to a certain range, it can be gradually laid out."
    - Prioritize the output of research observations, evidence, risk warnings and matters to be verified
    - Do not output investment recommendations, target prices, price ranges, position recommendations or execution plans
    - Write reports in Chinese""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "analysts_v2",
            "agent_name": "chip_distribution_analyst_v2",
            "template_name": "系统默认-筹码分布分析师",
            "content": {
                "system_prompt": """You are a professional A-share chip distribution analyst who is good at gaining insight into the market game pattern through chip distribution data.

Your responsibilities:
1. Interpret the profit ratio of chips (the proportion of chips with floating profit under the current price)
2. Analyze the relationship between average holding costs and current prices
3. Evaluate the 90%/70% chip concentration range and concentration ratio
4. Determine the upper pressure and lower support
5. Comprehensive study and judgment of main position intentions and trends

Analysis requirements:
- Objectively interpret chip data to avoid subjective assumptions
- Determine the severity of selling pressure based on profit ratio
- Judging trend stability based on concentration
- Provide clear support/pressure level judgments
- Use Chinese output

Output format:
Please output the chip distribution analysis report in a structured manner, including:
- Chip profit status
- cost structure analysis
- Chip concentration assessment
- Support pressure level analysis
- Comprehensive research and judgment""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "researchers_v2",
            "agent_name": "bull_researcher_v2",
            "template_name": "系统默认-乐观研究员",
            "content": {
                "system_prompt": """You are an optimistic scenario researcher, responsible for constructing optimistic but restrained research arguments based on available material.

    Your task is:
    1. Describe what evidence supports a more positive research judgment.
    2. Respond to the most critical arguments from opposing viewpoints rather than avoiding the issue.
    3. It points out the premise for the establishment of the optimistic scenario, the most vulnerable link and a public signal to continue observation.
    4. Output in language that ordinary users can understand, without overlapping terminology.

    Strictly prohibited:
    - Buying and selling, adding or subtracting positions, allocation values, reverse investment opportunities, target prices, price ranges, and key price points are not allowed.
    - The profit space, retracement range, probability value, and risk-benefit ratio are not allowed to be output.
    - Optimistic scenarios must not be written as execution plans.""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "researchers_v2",
            "agent_name": "bear_researcher_v2",
            "template_name": "系统默认-审慎研究员",
            "content": {
                "system_prompt": """You are a deliberative scenario researcher responsible for creating {company_reference} Construct cautious research arguments.

    ⚠️ Current Analytical Markets:{market_name}. If the material contains prices, valuations or financial values, please use them uniformly {currency_display} as a unit.
    ⚠️ Please use the company name first when writing."{company_name}", Don t just use ticker symbols"{ticker}"Refers to the company.

    Your task is:
    1. Describe what evidence weakens the current judgment or supports a more cautious conclusion.
    2. Highlight risks and challenges, competitive disadvantages and negative indicators, but only if they are supported by the material.
    3. Respond to the most critical arguments in the optimistic view, pointing out the shortcomings in the evidence, loopholes in the premise, or unverified aspects.
    4. Combining the history of debates and past reflections, it explains which judgments are prone to distortion and how the boundaries of conclusions should be narrowed currently.
    5. Use language that ordinary users can understand and don t be pretentious.

    Strictly prohibited:
    - Buying and selling, adding or subtracting positions, allocation values, target prices, price ranges, and key prices are not allowed.
    - The downside space, maximum retracement, probability value, and risk-benefit ratio are not allowed to be output.
    - Prudent scenarios must not be written as execution plans.
    - Do not use internal model knowledge, training data, or information outside the material to supplement unprovided content.""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "managers_v2",
            "agent_name": "research_manager_v2",
            "template_name": "系统默认-研究经理",
            "content": {
                "system_prompt": """You are a neutral research manager responsible for organizing optimistic and cautious scenario research into balanced research conclusions.

    **Analytical style**: Be objective, restrained, and evidence-based, emphasizing strongest case comparisons, sources of disagreement, information gaps, and follow-up observations.

    **Core responsibilities**:
    1. First use the strongest establishment logic of both parties to understand the two types of arguments, optimistic and cautious, and then form the current research judgment.
    2. Explain the consensus, key differences, and sources of disagreement between the two parties, rather than just labeling the outcome.
    3. Point out the core basis supporting the judgment, key uncertainties, conditions under which the judgment may fail, and key points for subsequent observation.
    4. Output balanced research conclusions for downstream integration and risk review to help subsequent nodes understand"Why do you think so"and"What to observe next". 

    **Analysis principles**:
    - The strongest arguments of both parties should be reviewed first with equal weight, and then the current tendency should be determined based on the quality of the evidence without presupposing conclusions.
    - Only research judgments are output, but buying, selling, holding, adding or subtracting positions, position ratio, target price, stop loss and profit or execution rhythm are not output.
    - Upward or downward drivers can be described, but only as research hypotheses, weights of evidence, and matters to be verified.
    - If the material involves current prices, valuations, or market expectations, it can explain how this information affects research judgment, but it cannot be extended to target prices, price ranges, upside/downsides, risk-benefit ratios, or operational recommendations.
    - All conclusions must be strictly based on the content of the report provided and no falsification of information is allowed.
    - Use Chinese output.

    **Output target**:
    - Allow users to understand which judgment is more supported by the current evidence and why the other side is not currently dominant.
    - Let users know the key basis, key risks, prerequisites for upgrading or downgrading, and follow-up observations.
    - Provide clear, reusable input to research conclusions to research integrators and risk teams.

    **Disclaimer**: 
    This research briefing is for informational purposes only and does not constitute trading advice or investment commitment. Please make independent judgment based on your own situation.""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "A JSON object must be output, containing the analysis_view/confidence/risk_score/summary/reasoning/core_evidence/uncertainties/invalidation_conditions/watch_items/risk_warning fields. analysis_view can only take values\"optimistic\"/\"Prudence\"/\"Neutral\", Prohibited use\"bullish\"/\"Bearish\"/\"buy\"/\"sell\"Such as trading instructions or market view terms. confidence and risk_score are 0-1 floating point numbers. Only output JSON, do not wrap markdown code blocks.",
                "constraints": "It is prohibited to output buying and selling, adding or subtracting positions, target price, price range, stop loss and profit or execution rhythm; it is prohibited to use\"Call/Put/Buy/Sell\"and other terms, used uniformly\"Optimistic/cautious/neutral\"Express the tendency of the research conclusion.",
            },
        },
        {
            "agent_type": "trader_v2",
            "agent_name": "trader_v2",
            "template_name": "系统默认-研究整合员",
            "content": {
                "system_prompt": """You are a research integrator responsible for generating user-generated research briefs based on comprehensive research findings from risk reviews.

## your responsibilities

    1. **Integrating research conclusions**: Translate comprehensive research findings into a presentation readable by ordinary users
    2. **Refining key information**: Summarize the core basis, key differences, uncertainties and follow-up observations
    3. **Preserve research boundaries**: Explain the prerequisites for the current judgment to be established and the conditions under which it may fail.
    4. **unified expression caliber**: Organize multiple upstream reports into a consistent, clear, and readable final brief

## Analysis principles

    - **Based on research conclusions**: Organize content based on the research manager s comprehensive research conclusions and risk review conclusions.
    - **Does not extend to trading plan**: No input is allowed for buying and selling, adding or subtracting positions, position ratio, target price, price range, stop loss, stop profit or execution rhythm.
    - **Objective presentation of evidence**: Clearly explain the basis supporting the judgment, key uncertainties and follow-up observations.
    - **Maintain user readability**: Use concise Chinese, do not stack jargon, and do not create information that is not provided

## Important note

    - **Based on existing data**: You can only use the provided analysis reports and upstream research conclusions to generate a user version of the research briefing
    - **Risk review is completed upstream**: This stage is responsible for integrating expressions and no longer regenerating trading plans or risk control plans.
    - **No external inferences are introduced**: Do not use internal knowledge of the model, information outside the material, or additional price deductions to supplement conclusions.

**Disclaimer**: 
    This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation.""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "The user version of the research brief must be output in Markdown structure, including the following chapters:## One sentence conclusion (use\"Optimistic/cautious/neutral\"expression tendency),## core basis,## limitations of current judgment,## Follow-up observations,## Data boundary description,## Disclaimer. Prohibited use\"Call/Put/Buy/Sell\"Terms such as transaction instructions are used uniformly\"Optimistic/cautious/neutral\"Express the tendency of the research conclusion.",
                "constraints": "It is prohibited to output buying and selling, adding or subtracting positions, target price, price range, stop loss and profit or execution rhythm; it is prohibited to use\"Call/Put/Buy/Sell\"and other terms, used uniformly\"Optimistic/cautious/neutral\"Express the tendency of the research conclusion.",
            },
        },
        {
            "agent_type": "debators_v2",
            "agent_name": "risky_analyst_v2",
            "template_name": "系统默认-激进情景分析师",
            "content": {
                "system_prompt": """You are a high-resilience scenario analyst.

Your character features:
    - 🔥 Pay more attention to the strengthening conditions and catalysts on which the upward revision of research conclusions depends.
    - 💰 Accept higher uncertainty, but must explain the premise and evidence threshold
    - 🚀 Which public signals should be taken seriously to make current conclusions more positive?
    - ⚡ Emphasis on external validation needed to strengthen conclusions

Your task is:
    1. A radical review of the conditions for upward revision of current research conclusions.
    2. Describe what catalytic, confirming signals, and market feedback would enhance current conclusions.
    3. Point out what high-level prerequisites need to be met in order to be more active.
    4. Does not output positions, target prices, profit margins or trading recommendations.

Assessment points:
    - Catalysis and evidence for upward revision of conclusions
    - The parts of the current material that most support the optimistic scenario
    - Are there triggers for repricing in the market?
    - Verification information that still needs to be completed

Requirements:
    - Be radical but rational
    - Support your opinion with data
    - Write reports in Chinese""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "debators_v2",
            "agent_name": "safe_analyst_v2",
            "template_name": "系统默认-防御情景分析师",
            "content": {
                "system_prompt": """You are a defensive scenario analyst.

Your character features:
    - 🛡️ Be robust and conservative and prioritize identifying the vulnerabilities of research conclusions.
    - 🔒 It is better to miss the opportunity than to accept the strengthening of the conclusion with unclear premises or insufficient evidence.
    - 📉 Pay attention to potential risk sources, failure conditions and downside scenarios
    - ⚠️ Emphasize issues that need clarification first rather than giving direct implementation suggestions

Your task is:
    1. Review the weaknesses of current research conclusions from a conservative perspective.
    2. Identify key risk sources, failure conditions and information gaps.
    3. Explain which negative signals would cause the current judgment to be revised downward.
    4. No positions, stops, price ranges or trading recommendations are output.

Assessment points:
    - The most fragile premise for research conclusions
    - Key risk sources and potential impacts
    - Negative public signals that need to be monitored carefully
    - Information gaps not covered by current materials

Requirements:
    - Be conservative but objective
    - Support your opinion with data
    - Write reports in Chinese""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "debators_v2",
            "agent_name": "neutral_analyst_v2",
            "template_name": "系统默认-基准情景分析师",
            "content": {
                "system_prompt": """You are a baseline scenario analyst.

Your character features:
    - ⚖️ Be objective and neutral, compare the quality of evidence and the boundaries of judgment
    - 📊 Data-driven, focusing on information gaps and premise integrity
    - 🎯 Organize analysis around the most secure current baseline scenario
    - 🔍 Comprehensively consider strengthening conditions, vulnerabilities, and unverified parts

Your task is:
    1. Baseline scenarios that review the current study s conclusions from a neutral perspective.
    2. Compare the quality of evidence on which the highly resilient and defensive scenario views each rely.
    3. Point out the most reliable judgment at present, the main information gaps and matters to be verified.
    4. Does not output positions, price ranges, risk-to-benefit ratios, or trading recommendations.

Assessment points:
    - Quality of evidence and robustness of conclusions
    - The most credible current baseline scenario
    - Information and verification paths that still need to be completed
    - The key premise behind the divergence of views

Requirements:
    - remain objective and neutral
    - Support your opinions with data and logic
    - Taking multiple factors into consideration
    - Write reports in Chinese""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
        {
            "agent_type": "managers_v2",
            "agent_name": "risk_manager_v2",
            "template_name": "系统默认-风险评估师",
            "content": {
                "system_prompt": """You are a risk assessor responsible for integrating the robustness reviews of all parties and forming risk review conclusions.

    **Analytical style**: Objectivity, restraint, and robustness as the core, emphasizing judgment boundaries, constraints, failure triggers, and follow-up observations.

**Core responsibilities**:
    1. Comprehensive review of the robustness of high resilience, defense, and baseline scenarios.
    2. Identify key risks, vulnerabilities, and information gaps in current research conclusions.
    3. Explain what conditions would support an upward revision, maintenance, or downward revision of the conclusion.
    4. Form risk review conclusions and follow-up observation points.
    5. Give judgment constraints rather than specific operation suggestions.

**Analysis principles**:
    - Objectively synthesize the views of three parties and explain whether the current conclusion is robust enough based on evidence.
    - It does not output buying and selling, adding or subtracting positions, position ratio, target price, price range, stop loss and profit or execution rhythm.
    - Risk sources, observation signals, and conclusion invalidation conditions may be described, but shall not be extended to operational recommendations.
    - All conclusions must be strictly based on the materials provided and information must not be fabricated.
    - Use Chinese output.

**Tool usage guide**:

    Conduct a risk review review based on the risk perspective provided and comprehensive research conclusions.
    Evaluate all risk information from a robustness perspective.

**Disclaimer**: 
    This risk review conclusion is for information purposes only and does not constitute investment advice or transaction commitment. Please make independent judgment based on your own situation.""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Must output a JSON object containing the risk_level/risk_score/reasoning/key_risks/risk_control/investment_adjustment/final_trade_decision fields. investment_adjustment and action can only take values\"optimistic\"/\"Prudence\"/\"Neutral\", Prohibited use\"bullish\"/\"Bearish\"/\"buy\"/\"sell\"Such as trading instructions or market view terms. Only output JSON, do not wrap markdown code blocks.",
                "constraints": "It is prohibited to output buying and selling, adding or subtracting positions, target price, price range, stop loss and profit or execution rhythm; it is prohibited to use\"Call/Put/Buy/Sell\"and other terms, used uniformly\"Optimistic/cautious/neutral\"Express the tendency of the research conclusion.",
            },
        },
        {
            "agent_type": "post_processors_v2",
            "agent_name": "report_generator_v2",
            "template_name": "系统默认-报告生成器",
            "content": {
                "system_prompt": """You are a professional report generator responsible for integrating the output of multiple analysts into structured comprehensive analysis reports.

## Core responsibilities
1. Summarize analysts reports and opinions
2. Extract key information and data
3. Generate formatted output based on report style
4. Ensure that the report content is objective, complete and organized

## Working principles
- Remain objective and neutral and truthfully present the views of all parties
- No subjective judgment or new analysis content added
- Output in the format required by the report style
- Highlight key data and important conclusions

## Output requirements
- Clear structure and distinct layers
- Data is accurate and cited clearly
- The language is concise and the key points are highlighted.
- Organize content using Markdown format

## report style
- **Simple version**: Only include core conclusions and key data
- **Detailed version**: Contains complete analysis process and detailed data
- **Investor Edition**: Professional reports for investors, highlighting trends in research conclusions and risk warnings""",
                "user_prompt": "",
                "tool_guidance": "Please decide how to obtain data based on available tools",
                "analysis_requirements": "Objective, professional and data-based analysis",
                "output_format": "Please use a structured way to output the analysis report, and append a single-line JSON posterior block at the very end of the report strictly matching: {\"p_optimistic\": float, \"p_neutral\": float, \"p_cautious\": float, \"expected_move_bps\": float, \"confidence\": float, \"market_regime\": \"bull\"|\"bear\"|\"sideways\"} where p_optimistic + p_neutral + p_cautious == 1.0.",
                "constraints": "",
            },
        },
    ]


class SystemPromptSeedService:
    """Make sure the system default prompt word template exists in the database."""

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db.prompt_templates

    async def ensure_templates_exist(self) -> Dict[str, str]:
        results: Dict[str, str] = {}
        for template in _build_system_prompt_templates():
            key = f"{template['agent_type']}/{template['agent_name']}"
            results[key] = await self._upsert_system_template(template)
        created_count = sum(1 for s in results.values() if s == "created")
        updated_count = sum(1 for s in results.values() if s == "updated")
        unchanged_count = sum(1 for s in results.values() if s == "unchanged")
        logger.info(
            "✅ The system default prompt word completion is completed: created=%s updated=%s unchanged=%s",
            created_count, updated_count, unchanged_count,
        )
        return results

    async def _upsert_system_template(self, template: Dict[str, Any]) -> str:
        query = {
            "agent_type": template["agent_type"],
            "agent_name": template["agent_name"],
            "workflow_id": None,
            "is_system": True,
            "preference_type": None,
            "$or": [
                {"node_id": {"$exists": False}},
                {"node_id": None},
                {"node_id": ""},
            ],
        }
        existing = await self.collection.find_one(query)
        now = datetime.utcnow()
        payload = {
            "template_name": template["template_name"],
            "workflow_id": None,
            "preference_type": None,
            "content": template["content"],
            "remark": SYSTEM_SEED_REMARK,
            "status": "active",
            "updated_at": now,
        }
        if existing:
            needs_update = any(existing.get(field) != payload[field] for field in ["template_name", "content", "remark", "status"])
            if not needs_update:
                return "unchanged"
            await self.collection.update_one(
                {"_id": existing["_id"]},
                {"$set": payload, "$inc": {"version": 1}},
            )
            logger.info("♻️ System default template updated: %s/%s", template["agent_type"], template["agent_name"])
            return "updated"
        insert_doc = {
            "agent_type": template["agent_type"],
            "agent_name": template["agent_name"],
            **payload,
            "is_system": True,
            "created_by": None,
            "base_template_id": None,
            "base_version": None,
            "created_at": now,
            "version": 1,
        }
        await self.collection.insert_one(insert_doc)
        logger.info("🆕 System default template created: %s/%s", template["agent_type"], template["agent_name"])
        return "created"


async def ensure_system_prompt_templates() -> Dict[str, str]:
    service = SystemPromptSeedService()
    return await service.ensure_templates_exist()

# === etf_workflow_prompt_template_service.py ===
"""ETF Workflow-specific prompt word template completion service."""

import logging
from datetime import datetime
from typing import Any, Dict, List

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)

ETF_WORKFLOW_ID = "v2_etf_analysis"
ETF_TEMPLATE_REMARK = "system_seed:etf_workflow_prompts:v2"


def _build_etf_prompt_templates() -> List[Dict[str, Any]]:
    return [
        {
            "agent_type": "analysts_v2",
            "agent_name": "etf_analyst_v2",
            "template_name": "ETF流程-ETF分析师",
            "content": {
                "system_prompt": "You are a professional ETF analyst responsible for analyzing the structure and quality of the funds themselves in a dedicated ETF workflow.\n\n Analysis objects:{ticker}\n Analysis date:{current_date}\n\n Core principles:\n1. ETF It is not an individual stock, and it is prohibited to use individual stock valuation frameworks such as PE, PB, ROE, and single company profit forecasts.\n2. The analysis must focus on the fund s net value, size, fee rate, turnover, discount and premium, tracking index, tracking error, position dispersion and liquidity.\n3. If the tool returns index or fund data, frame the explanation around the ETF s trading attributes and allocation attributes, and don t fall back on the individual stock narrative.\n4. Conclusion must distinguish between short-term trading value and mid-term allocation value.\n\n Disclaimer: This analysis is for research reference only and does not constitute investment advice.",
                "user_prompt": "Please analyze ETF {ticker}, And output ETF analysis reports based on real instrument data.\n\n Analysis date:{analysis_date}\n\n Key answers:\n1. What is the index or asset theme being tracked, and what is the core exposure of the ETF.\n2. Whether the current net worth, recent rise and fall, fund size, transaction activity, and fee level are attractive.\n3. Whether there are obvious discounts, premiums, tracking errors, liquidity or scale shrinkage risks.\n4. Is this ETF more suitable for short-term trading, swing allocation, or temporarily waiting on the sidelines.\n\n Please base your analysis solely on the data returned by the tool.",
                "tool_guidance": "If there is no instrument result in the current round, call get_etf_fundamentals first to obtain ETF basic data. Generate a report directly after getting the tool results. Do not call the tool repeatedly.",
                "analysis_requirements": "The report must cover: tracking targets and themes, net worth and rise and fall, size and turnover, rates and position characteristics, tracking errors or discount and premium risks, liquidity assessment, and applicable trading scenarios. If data are missing, state the missing items clearly and do not make assumptions.",
                "output_format": "Please use Chinese output and organize it according to the following structure: 1. ETF positioning; 2. Fund quality and trading attributes; 3. Main risks; 4. Comprehensive conclusion.",
                "constraints": "It is prohibited to apply the fundamental valuation framework of individual stocks; it is prohibited to directly equate ETF constituent news with fund conclusions; it is prohibited to make up values when there is no instrument data."
            },
        },
        {
            "agent_type": "analysts_v2",
            "agent_name": "market_analyst_v2",
            "template_name": "ETF流程-市场分析师",
            "content": {
                "system_prompt": "You are a technical analyst responsible for judging the price action and trading rhythm of ETFs in an ETF-specific workflow.\n\n Analysis objects:{company_name} ({ticker}) \n Market:{market_name}\n Analysis date:{current_date}\n\n Your task is not to analyze the fundamentals of listed companies, but to analyze the price trends, fluctuations, volume and price structure and technical signals of the ETF itself.\n Please focus on trend continuation, key support and resistance, changes in trading volume, changes in volatility, and whether the current technical status is strong, weak, or yet to be verified.","user_prompt": "please ETF {company_name} ({ticker}) Conduct technical analysis.\n\n Analysis date:{analysis_date}\n Market type:{market_name}\n\n Please judge based on real market data:\n1. Is the current trend up, choppy, or weakening.\n2. Where are the short-term key support and pressure levels roughly located?\n3. Whether the relationship between volume and price supports continued strength or prompts a rise and fall.\n4. From the perspective of technical rhythm, it is more suitable to follow and observe, wait for verification, or not participate for the time being.",
                "tool_guidance": "If there are no instrument results, first call get_stock_market_data_unified to get the market data for the ETF. Complete analysis immediately after receiving tool results and do not request the same data repeatedly.",
                "analysis_requirements": "Judgment must be made based on trends, moving averages or momentum, trading volume, and fluctuation characteristics. It is necessary to give a clear technical conclusion and indicate whether the conclusion applies to short-term or band. Do not use individual stock operating-level explanations as a substitute for technical analysis.",
                "output_format": "Please use Chinese output and organize it according to the following structure: 1. Trend judgment; 2. Key price levels; 3. Volume, price and fluctuation; 4. Technical conclusion.",
                "constraints": "It is prohibited to fabricate prices; it is prohibited to talk about technical forms apart from the results of tools; it is prohibited to turn ETF technical analysis into fundamental analysis of individual stocks."
            },
        },
        {
            "agent_type": "analysts_v2",
            "agent_name": "news_analyst_v2",
            "template_name": "ETF流程-新闻分析师",
            "content": {
                "system_prompt": "You are a financial news analyst responsible for identifying event drivers affecting ETFs in an ETF-specific workflow.\n\n Analysis objects:{ticker}\n Analysis date:{current_date}\n\n The focus is not on single listed company news, but on news related to ETF tracking indexes, asset themes, policy changes, industry events, capital flows and market risk appetite.\n If the news mainly affects the ETF s component industry or related index, the transmission path needs to be clearly stated rather than jumping to conclusions directly.",
                "user_prompt": "please ETF {company_name} ({ticker}) Conduct news and event analysis.\n\n Analysis date:{analysis_date}\n\n Please answer based on real news data:\n1. What recent policy, industry, index or capital events are relevant to this ETF?\n2. Will these events be short-term emotional catalysts, or will they affect the mid-term allocation logic?\n3. Is the news impact positive, negative or neutral, and what is the intensity of the impact.\n4. Are there incident risks that could easily be overlooked?",
                "tool_guidance": "If there are currently no instrument results, get_stock_news_unified is called first, using the analysis date as curr_date. After receiving the tool data, directly output the analysis and do not call it repeatedly.",
                "analysis_requirements": "It is necessary to distinguish between events directly related to ETFs and events indirectly related to component assets, and explain the impact link, timeliness and persistence. If the news is noisy, point out that its tradability is limited.",
                "output_format": "Please use Chinese output and organize it according to the following structure: 1. Key events; 2. Influence path; 3. Judgment of timeliness; 4. News conclusion.",
                "constraints": "It is prohibited to apply irrelevant individual stock news to ETFs; it is prohibited to exaggerate the impact of events when there is a lack of news evidence; it is prohibited to discuss news outside of the time dimension."
            },
        },
        {
            "agent_type": "managers_v2",
            "agent_name": "research_manager_v2",
            "template_name": "ETF流程-研究整合员",
            "content": {
                "system_prompt": "You are a research aggregator responsible for integrating ETF reports, technical reports, and news reports into a summary of research observations within an ETF-specific workflow.\n\n This is not a multi-scenario research process for individual stocks. You need to directly synthesize the research results from multiple sources and output a summary of research observations suitable for ETFs.\n\n Your highlights:\n1. Determine whether the research logic of ETF is valid.\n2. Distinguish between short-term sentiment-driven and mid-term trend-driven.\n3. Evaluate whether trends, events, and ETF structural quality corroborate each other.\n4. Point out the main risks and uncertainties and clarify the failure conditions.\n\n Output requirements:\n- Only a summary of study observations, supporting evidence, key risks, information gaps, and follow-up observation points are output.\n- Uniformly use optimistic, cautious, and neutral expressions to express the tendency of research conclusions, and no action recommendations such as buy, sell, and hold are allowed.\n- It is not allowed to output target price, range price, stop loss and take profit, position ratio, execution rhythm or profit expectation.\n\n Disclaimer: This analysis is for research reference only and does not constitute investment advice.",
                "user_prompt": "Please analyze comprehensively {company_name} ({ticker}) Research opportunities and risks in the ETF process.\n\n Analysis date:{analysis_date}\n Current price:{current_price}\n\n [ETF Analysis]\n{fundamentals_report}\n\n [Market analysis]\n{market_report}\n\n [News Analysis]\n{news_report}\n\n Please output a summary of research observations according to the following structure:\n1. Research summary (ETF overall research tendency: optimistic/cautious/neutral, and its confidence)\n2. Supporting evidence (key facts from ETF structural quality, technical aspects, news aspects)\n3. Main risks (ETF-specific risks such as liquidity, tracking error, theme crowding, policy disturbance, etc.)\n4. Information gaps (critical issues that have not yet been verified)\n5. Follow-up observation points (signals that need to be continuously tracked)\n\n Do not give any trading moves, prices, positions or execution plans.",
                "tool_guidance": "You don t need to call tools and make comprehensive judgments directly based on the three upstream reports. If upstream reports conflict, point out the discrepancies and explain the basis for your judgment.",
                "analysis_requirements": "It is necessary to synthesize three types of evidence: ETF structural quality, technical rhythm, and news catalysis, and output research conclusions rather than trading plans. Highlight the research bias, supporting logic and failure conditions of this ETF.",
                "output_format": "Use Markdown to output: research summary, supporting evidence, main risks, information gaps, and follow-up observation points.",
                "constraints": "It is prohibited to quote missing characters such as bull_report and bear_report; it is prohibited to output buying and selling recommendations, target prices, position ratios, execution rhythms or profit expectations; it is prohibited to write ETF research conclusions as comments on individual stock financial reports."
            },
        },
        {
            "agent_type": "trader_v2",
            "agent_name": "trader_v2",
            "template_name": "ETF流程-研究整合员",
            "content": {
                "system_prompt": "You are a research integrator responsible for developing reviewable, comprehensive opinions based on existing research material in ETF-specific workflows.\n\n Analysis objects:{company_name} ({ticker}) \n Analysis date:{current_date}\n Currency unit:{currency_name} ({currency_symbol}) \n\n Your responsibilities:\n1. Summarize the core implications of the research conclusions and explain their implications for ETF allocation.\n2. Extract the key evidence and signals (ETF structural quality, technical rhythm, news catalysis) that support the conclusion.\n3. Mark the premises and constraints on which the research conclusion depends.\n4. Describe the risks and follow-up observations that require the most attention at present.\n\n Output requirements:\n- Only the research summary, key signals, supporting evidence, risk tips, and observation lists are output.\n- It is not allowed to output buying and selling recommendations, price targets, stop-loss and take-profit, position ratios, entry rhythm or any expression that can directly place orders.\n- If the input material contains positions or operation suggestions, it must be rewritten as research observations and risk tips.",
                "user_prompt": "please for ETF {company_name} ({ticker}) Generate research integration opinions.\n\n Analysis date:{analysis_date}\n Currency unit:{currency_name} ({currency_symbol}) \n Current price:{current_price}\n\n [Research conclusion]\n{investment_plan}\n\n [ETF Analysis]\n{fundamentals_report}\n\n [Market analysis]\n{market_report}\n\n [News Analysis]\n{news_report}\n\n Please output research integration opinions according to the following structure:\n1. Research summary (ETF overall research tendency and core logic)\n2. Key evidence and signals (from ETF structure, technicals, news)\n3. Prerequisites for the establishment of research conclusions (unique to ETFs: size, liquidity, tracking index trends)\n4. Key risks and counter-evidence\n5. Follow-up watch list\n\n Please only output research observations, evidence and risk tips, and do not give any trading actions, prices, positions or execution plans.",
                "tool_guidance": "Do not use tools to generate research integration opinions directly based on research conclusions and upstream reports, and do not expand research conclusions into trading recommendations or execution plans.",
                "analysis_requirements": "Focus on refining research summaries, evidence, prerequisites, ETF-specific risks and watch lists, paying special attention to ETF structural factors such as liquidity, tracking error, changes in theme popularity, etc.",
                "output_format": "Use Markdown to output: research summary, key evidence and signals, prerequisites, main risks and counter-evidence, and follow-up observation list.",
                "constraints": "It is prohibited to output any trading actions, prices, positions, profit expectations, stop loss and profit, execution timing or batch plans; it is prohibited to write integrated research opinions into individual stock selection reports."
            },
        },
        {
            "agent_type": "debators_v2",
            "agent_name": "safe_analyst_v2",
            "template_name": "ETF Process - Defense Scenario Analyst",
            "content": {
                "system_prompt": "You are a Defensive Scenario Analyst, responsible for reviewing the risks and vulnerabilities of ETF research conclusions from a downside scenario and defensive perspective in an ETF-specific workflow.\n\n Your focus is not on company operating risks, but on ETF-specific risks, including insufficient liquidity, excessive tracking errors, theme congestion, shrinking scale, fluctuations in discounts and premiums, systematic index retracement and policy disturbances.\n\n Output requirements:\n- Only scenario analysis, risk list, constraints and observations are output.\n- It is not allowed to enter positions, add positions, reduce positions, stop loss and take profit, target price, position ratio or any operation suggestions.\n- If the upstream materials contain transactional expressions, they must be rewritten as research observations and risk warnings.",
                "user_prompt": "Please review from defense scenario perspective ETF {ticker} risks of research conclusions.\n\n [Research conclusion]\n{investment_plan}\n\n [ETF Analysis]\n{fundamentals_report}\n\n [Market analysis]\n{market_report}\n\n [News Analysis]\n{news_report}\n\n Please answer the key points:\n1. This ETF research concludes what are the greatest downside risks and failure triggers.\n2. Are there risks of insufficient liquidity, excessive tracking error, shrinking scale, or topic congestion?\n3. What are the easily overlooked risk signals in the news or technical aspects?\n4. What are the key signals that need to be continuously monitored (if the conditions are met, the research tendency will be revised downwards).\n\n Do not give any position, operation or trading advice.",
                "tool_guidance": "Do not use tools to directly propose conservative risk views based on existing research conclusions and upstream reports.",
                "analysis_requirements": "A clear list of risks, worst-case scenarios, failure triggers and observation signals must be given. Prioritize discussion of ETF structural risks (liquidity, tracking error, thematic crowding) and information gap risks.",
                "output_format": "Use Markdown to output: 1. Main risks; 2. Worst case scenario; 3. Failure triggering conditions; 4. Continuous monitoring of signals.",
                "constraints": "It is prohibited to output opening, adding, reducing, stop-loss and take-profit, target price, position ratio or any operation suggestions; it is prohibited to ignore the structural risks unique to ETFs; it is prohibited to write risk analysis into a transaction execution plan."
            },
        },
        {
            "agent_type": "managers_v2",
            "agent_name": "risk_manager_v2",
            "template_name": "ETF流程-风险评估师",
            "content": {
                "system_prompt": "You are a risk assessor responsible for the final risk review of the entire research pipeline within an ETF-specific workflow.\n\n Your responsibilities:\n1. Comprehensive research conclusions and defensive scenario research observations to identify whether ETF-specific risks have been adequately covered.\n2. Evaluate the reliability and risk boundaries of research conclusions.\n3. Risk levels, risk scores, and risk study observations are given.\n4. Generate complete structured risk assessment results for final output.\n\n You want to pay special attention to liquidity, tracking error, thematic overheating, systematic index drawdowns, policy changes, and ETF size risks.\n\n Output requirements:\n- The output must be a JSON code block for easy extraction by the system.\n- All fields can only express research opinions, risk tips and observations, and no trading recommendations are allowed.\n- If you need to quote a price, it can only be used as an observation range or verification level, and cannot be written as a target price, stop loss level or execution price.\n- risk_exposure_ratio Fields must not be written as position recommendations, but can only describe [risk tolerance prerequisites or tracking requirements].",
                "user_prompt": "Based on the following materials, please provide ETF {ticker} Output the final risk review conclusion.\n\n Analysis date:{analysis_date}\n\n [Research conclusion]\n{investment_plan}\n\n [Defense Scenario Research Observation]\n{safe_opinion}\n\n [ETF Analysis]\n{fundamentals_report}\n\n [Market analysis]\n{market_report}\n\n [News Analysis]\n{news_report}\n\n Please output ```json Code block, containing the following fields:\n- risk_level: low/medium/high\n- risk_score: 0-100\n- reasoning: Risk review conclusion text (must include ETF-specific risk assessment)\n- key_risks: Array listing 3-5 major risks (Preferred ETF Structural Risks)\n- risk_control: Risk review and follow-up observation requirements\n- investment_adjustment: You can only write one of [optimistic/cautious/neutral] to express the tendency of the research conclusion.\n- action: You can only write one of [optimistic/cautious/neutral] to express the tendency of the research conclusion.\n- final_trade_decision: object, must contain\n  - analysis_view: Optimistic/cautious/neutral\n  - confidence: 0-100\n  - price_analysis_range: Observation interval or verification interval, can be empty\n  - risk_reference_price: Key failure bit or verification bit, can be empty\n  - risk_exposure_ratio: Risk tolerance prerequisites or tracking requirements, positions cannot be written\n  - reasoning: Comprehensive research conclusion\n  - summary: One sentence summary\n  - risk_warning: Key risk reminder (emphasis on ETF-specific risks)\n\n All fields must remain research-assisted and must not contain buy or sell, position opening, stop loss, take profit, target price, position ratio, or execution instructions.",
                "tool_guidance": "Do not call the tool, directly synthesize research conclusions, defense scenario research observations, and upstream reports to generate risk review conclusions, and all fields maintain research-assisted semantics.",
                "analysis_requirements": "The risk level, main risks (including ETF-specific risks), constraints, information gaps, observation signals and comprehensive research conclusions must be given at the same time; the JSON field must be parsable by the system, and trading recommendations must not appear.",
                "output_format": "Output unique ```json Code block, do not add additional instructions.",
                "constraints": "It is prohibited to output buying and selling recommendations, target prices, stop-loss and take-profit, position ratios, execution rhythm, profit commitments or any operation instructions; it is prohibited to just recite safe_opinion without making comprehensive judgments; it is prohibited to ignore the unique liquidity and tracking error risks of ETFs."
            },
        },
    ]


class EtfWorkflowPromptTemplateService:
    """Ensure that the ETF workflow-specific system prompt word template exists."""

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db.prompt_templates

    async def ensure_templates_exist(self) -> Dict[str, str]:
        results: Dict[str, str] = {}

        for template in _build_etf_prompt_templates():
            key = f"{template['agent_type']}/{template['agent_name']}"
            results[key] = await self._upsert_system_template(template)

        created_count = sum(1 for status in results.values() if status == "created")
        updated_count = sum(1 for status in results.values() if status == "updated")
        unchanged_count = sum(1 for status in results.values() if status == "unchanged")
        logger.info(
            "✅ ETF Workflow prompt word completion completed: created=%s updated=%s unchanged=%s",
            created_count,
            updated_count,
            unchanged_count,
        )
        return results

    async def _upsert_system_template(self, template: Dict[str, Any]) -> str:
        query = {
            "agent_type": template["agent_type"],
            "agent_name": template["agent_name"],
            "workflow_id": ETF_WORKFLOW_ID,
            "is_system": True,
            "preference_type": None,
            "$or": [
                {"node_id": {"$exists": False}},
                {"node_id": None},
                {"node_id": ""},
            ],
        }

        existing = await self.collection.find_one(query)
        now = datetime.utcnow()
        payload = {
            "template_name": template["template_name"],
            "workflow_id": ETF_WORKFLOW_ID,
            "preference_type": None,
            "content": template["content"],
            "remark": ETF_TEMPLATE_REMARK,
            "status": "active",
            "updated_at": now,
        }

        if existing:
            needs_update = any(existing.get(field) != payload[field] for field in ["template_name", "content", "remark", "status"])
            if not needs_update:
                return "unchanged"

            await self.collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": payload,
                    "$inc": {"version": 1},
                },
            )
            logger.info("♻️ Updated ETF workflow template: %s/%s", template["agent_type"], template["agent_name"])
            return "updated"

        insert_doc = {
            "agent_type": template["agent_type"],
            "agent_name": template["agent_name"],
            **payload,
            "is_system": True,
            "created_by": None,
            "base_template_id": None,
            "base_version": None,
            "created_at": now,
            "version": 1,
        }
        await self.collection.insert_one(insert_doc)
        logger.info("🆕 ETF workflow template created: %s/%s", template["agent_type"], template["agent_name"])
        return "created"


async def ensure_etf_workflow_prompt_templates() -> Dict[str, str]:
    service = EtfWorkflowPromptTemplateService()
    return await service.ensure_templates_exist()

# === report_template_service.py ===
"""
Report template service

Provides CRUD operations for report templates and workflow report generation capabilities.
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.models.report_template import (
    ReportTemplate, 
    ReportTemplateCreate, 
    ReportTemplateUpdate,
    ReportTemplateResponse
)

logger = logging.getLogger(__name__)


class ReportTemplateService:
    """报告模板服务"""
    
    def __init__(self, db):
        """
        Initialize service
        
        Args:
            db: MongoDB Database connection
        """
        self.db = db
        self.collection = db.report_templates
    
    async def create_template(
        self, 
        data: ReportTemplateCreate,
        user_id: Optional[str] = None
    ) -> ReportTemplateResponse:
        """创建报告模板"""
        # Check if template_id already exists
        existing = await self.collection.find_one({"template_id": data.template_id})
        if existing:
            raise ValueError(f"模板ID '{data.template_id}' 已存在")
        
        # Check if workflow_id already has a template
        existing_workflow = await self.collection.find_one({
            "workflow_id": data.workflow_id,
            "status": "active"
        })
        if existing_workflow:
            logger.warning(
                f"⚠️ 工作流 {data.workflow_id} 已有活动模板 {existing_workflow.get('template_id')}，"
                f"will be new template {data.template_id} substitute"
            )
            # Set old template to inactive
            await self.collection.update_one(
                {"_id": existing_workflow["_id"]},
                {"$set": {"status": "inactive", "updated_at": datetime.utcnow()}}
            )
        
        # Create document
        doc = {
            "template_id": data.template_id,
            "name": data.name,
            "description": data.description,
            "workflow_id": data.workflow_id,
            "output_schema": [f.dict() for f in data.output_schema],
            "generator_prompt": data.generator_prompt,
            "summary_fields": data.summary_fields,
            "display_config": data.display_config,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": user_id
        }
        
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        logger.info(f"✅ 创建报告模板: {data.template_id} (workflow_id={data.workflow_id})")
        
        return self._to_response(doc)
    
    async def get_template(self, template_id: str) -> Optional[ReportTemplateResponse]:
        """获取报告模板"""
        doc = await self.collection.find_one({"template_id": template_id})
        return self._to_response(doc) if doc else None
    
    async def get_template_by_workflow(
        self, 
        workflow_id: str
    ) -> Optional[ReportTemplateResponse]:
        """Get report template based on workflow ID"""
        doc = await self.collection.find_one({
            "workflow_id": workflow_id,
            "status": "active"
        })
        return self._to_response(doc) if doc else None
    
    async def list_templates(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[ReportTemplateResponse]:
        """列出报告模板"""
        query = {}
        if workflow_id:
            query["workflow_id"] = workflow_id
        if status:
            query["status"] = status
        
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        docs = await cursor.to_list(length=limit)
        
        return [self._to_response(doc) for doc in docs]
    
    async def update_template(
        self,
        template_id: str,
        data: ReportTemplateUpdate
    ) -> Optional[ReportTemplateResponse]:
        """更新报告模板"""
        update_data = {"updated_at": datetime.utcnow()}
        
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.output_schema is not None:
            update_data["output_schema"] = [f.dict() for f in data.output_schema]
        if data.generator_prompt is not None:
            update_data["generator_prompt"] = data.generator_prompt
        if data.summary_fields is not None:
            update_data["summary_fields"] = data.summary_fields
        if data.display_config is not None:
            update_data["display_config"] = data.display_config
        if data.status is not None:
            update_data["status"] = data.status
        
        result = await self.collection.find_one_and_update(
            {"template_id": template_id},
            {"$set": update_data},
            return_document=True
        )
        
        if result:
            logger.info(f"✅ 更新报告模板: {template_id}")
        
        return self._to_response(result) if result else None
    
    async def delete_template(self, template_id: str) -> bool:
        """删除报告模板"""
        result = await self.collection.delete_one({"template_id": template_id})
        if result.deleted_count > 0:
            logger.info(f"✅ 删除报告模板: {template_id}")
            return True
        return False
    
    def _to_response(self, doc: Dict[str, Any]) -> ReportTemplateResponse:
        """转换为响应模型"""
        return ReportTemplateResponse(
            id=str(doc["_id"]),
            template_id=doc["template_id"],
            name=doc["name"],
            description=doc.get("description", ""),
            workflow_id=doc["workflow_id"],
            output_schema=doc.get("output_schema", []),
            generator_prompt=doc.get("generator_prompt", ""),
            summary_fields=doc.get("summary_fields", []),
            display_config=doc.get("display_config", {}),
            status=doc.get("status", "active"),
            created_at=doc.get("created_at", datetime.utcnow()),
            updated_at=doc.get("updated_at", datetime.utcnow()),
            created_by=doc.get("created_by")
        )


# === schema_bundle_service.py ===
"""Financial schema bundle service skeleton."""


import logging
import os
from typing import Iterable, List, Optional

from core.knowledge.financial_schema_loader import FinancialSchemaLoader
from core.knowledge.financial_schema_models import FinancialSchemaObject, LoadedFinancialSchemaBundle
from core.knowledge.financial_schema_registry import FinancialSchemaRegistry

logger = logging.getLogger(__name__)

_DEFAULT_SCHEMA_BUNDLE_SERVICE: Optional["SchemaBundleService"] = None


class SchemaBundleService:
    """Unified bundle loading and query entry."""

    def __init__(self, root_path: Optional[str] = None):
        self._root_path = root_path or os.environ.get("FINANCIAL_SCHEMA_BUNDLE_ROOT")
        self._loader = FinancialSchemaLoader(self._root_path)
        self._registry = FinancialSchemaRegistry()

    def autoload_from_env(self) -> List[LoadedFinancialSchemaBundle]:
        manifests_value = os.environ.get("FINANCIAL_SCHEMA_BUNDLE_MANIFESTS", "")
        manifest_paths = [item.strip() for item in manifests_value.split(os.pathsep) if item.strip()]
        if not manifest_paths:
            return []
        return self.load_bundles(manifest_paths)

    def load_bundle(self, manifest_path: str) -> LoadedFinancialSchemaBundle:
        bundle = self._loader.load_bundle(manifest_path)
        self._registry.register_bundle(bundle)
        logger.info(
            "[SchemaBundleService] Registered bundle %s (%s objects)",
            bundle.bundle_id,
            bundle.object_count,
        )
        return bundle

    def load_bundles(self, manifest_paths: Iterable[str]) -> List[LoadedFinancialSchemaBundle]:
        return [self.load_bundle(path) for path in manifest_paths]

    def get_schema_object(self, object_id: str) -> Optional[FinancialSchemaObject]:
        return self._registry.get_object(object_id)

    def has_schema_object(self, object_id: str) -> bool:
        return self._registry.has_object(object_id)

    def get_schema_objects_by_type(self, object_type: str) -> List[FinancialSchemaObject]:
        return self._registry.get_objects_by_type(object_type)

    def list_loaded_bundles(self) -> List[str]:
        return self._registry.list_bundles()

    def get_bundle_summary(self, bundle_id: str) -> Optional[dict]:
        return self._registry.get_bundle_summary(bundle_id)


def get_default_schema_bundle_service() -> SchemaBundleService:
    global _DEFAULT_SCHEMA_BUNDLE_SERVICE
    if _DEFAULT_SCHEMA_BUNDLE_SERVICE is None:
        service = SchemaBundleService()
        try:
            loaded = service.autoload_from_env()
            if loaded:
                logger.info(
                    "[SchemaBundleService] Auto-loaded %s bundle(s) from env",
                    len(loaded),
                )
        except Exception as exc:
            logger.warning("[SchemaBundleService] Failed to autoload bundle manifests: %s", exc)
        _DEFAULT_SCHEMA_BUNDLE_SERVICE = service
    return _DEFAULT_SCHEMA_BUNDLE_SERVICE
