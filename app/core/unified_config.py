"""
Unified configuration management system
Integrate configuration management of config/, tradingagents/config/ and webapi
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import asyncio
from dataclasses import dataclass, asdict

from app.models.config import (
    LLMConfig, DataSourceConfig, DatabaseConfig, SystemConfig,
    ModelProvider, DataSourceType, DatabaseType
)


# 🆕 .env Medium data source switch override mapping:env_key -> DataSourceType value
_ENV_OVERRIDE_MAP = {
    "ENABLE_BAOSTOCK": "baostock",
    "ENABLE_TUSHARE": "tushare",
}


def _apply_env_overrides(data_sources: List) -> None:
    """
    Change .env in ENABLE_* The switch is applied to the data source configuration.
    .env Settings take precedence over database cache configuration.
    """
    try:
        from app.core.config import settings as runtime_settings

        for env_key, ds_type in _ENV_OVERRIDE_MAP.items():
            env_val = getattr(runtime_settings, env_key, None)
            if env_val is None:
                continue  # .env The key is not set in and will not be overwritten.

            for ds in data_sources:
                if ds.type == ds_type:
                    old_enabled = ds.enabled
                    ds.enabled = bool(env_val)
                    if old_enabled != ds.enabled:
                        print(f"🔧 [unified_config] .env Cover: {ds.name} enabled={ds.enabled} (Original={old_enabled})")
                    break
    except Exception as e:
        print(f"⚠️ [unified_config] .env Coverage check failed: {e}")


@dataclass
class ConfigPaths:
    """Configuration file path"""
    root_config_dir: Path = Path("config")
    tradingagents_config_dir: Path = Path("tradingagents/config")
    webapi_config_dir: Path = Path("data/config")
    
    # Specific configuration file
    models_json: Path = root_config_dir / "models.json"
    settings_json: Path = root_config_dir / "settings.json"
    pricing_json: Path = root_config_dir / "pricing.json"
    verified_models_json: Path = root_config_dir / "verified_models.json"


class UnifiedConfigManager:
    """Unified configuration manager"""

    # Class-level data source configuration cache (shared by all instances to avoid repeated queries to MongoDB)
    _ds_config_cache: Optional[List] = None
    _ds_config_cache_time: float = 0.0
    _DS_CONFIG_CACHE_TTL: float = 300.0  # 5 minutes TTL

    def __init__(self):
        self.paths = ConfigPaths()
        self._cache = {}
        self._last_modified = {}
        
    def _get_file_mtime(self, file_path: Path) -> float:
        """Get file modification time"""
        try:
            return file_path.stat().st_mtime
        except FileNotFoundError:
            return 0.0
    
    def _is_cache_valid(self, cache_key: str, file_path: Path) -> bool:
        """Check if cache is valid"""
        if cache_key not in self._cache:
            return False
        
        current_mtime = self._get_file_mtime(file_path)
        cached_mtime = self._last_modified.get(cache_key, 0)
        
        return current_mtime <= cached_mtime
    
    def _load_json_file(self, file_path: Path, cache_key: str = None) -> Dict[str, Any]:
        """Load JSON files, support caching"""
        if cache_key and self._is_cache_valid(cache_key, file_path):
            return self._cache[cache_key]
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if cache_key:
                self._cache[cache_key] = data
                self._last_modified[cache_key] = self._get_file_mtime(file_path)
            
            return data
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            print(f"Configuration file format error {file_path}: {e}")
            return {}
    
    def _save_json_file(self, file_path: Path, data: Dict[str, Any], cache_key: str = None):
        """Save JSON file"""
        # Make sure the directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        if cache_key:
            self._cache[cache_key] = data
            self._last_modified[cache_key] = self._get_file_mtime(file_path)
    
    # ==================== Model configuration management ====================
    
    def get_legacy_models(self) -> List[Dict[str, Any]]:
        """Get model configuration in legacy format"""
        return self._load_json_file(self.paths.models_json, "models")
    
    def get_llm_configs(self) -> List[LLMConfig]:
        """Get standardized LLM configuration"""
        legacy_models = self.get_legacy_models()
        llm_configs = []

        for model in legacy_models:
            try:
                # Use provider string directly and no longer map to enumeration
                provider = model.get("provider", "openai")

                # Solution A: Sensitive keys are not loaded from the file, and the environment variables/manufacturer directory are uniformly used.
                llm_config = LLMConfig(
                    provider=provider,
                    model_name=model.get("model_name", ""),
                    api_key="",
                    api_base=model.get("base_url"),
                    max_tokens=model.get("max_tokens", 8000),
                    temperature=model.get("temperature", 0.7),
                    enabled=model.get("enabled", True),
                    description=f"{model.get('provider', '')} {model.get('model_name', '')}"
                )
                llm_configs.append(llm_config)
            except Exception as e:
                print(f"Conversion model configuration failed: {model}, Error: {e}")
                continue

        return llm_configs
    
    def save_llm_config(self, llm_config: LLMConfig) -> bool:
        """Save LLM configuration to legacy format"""
        try:
            legacy_models = self.get_legacy_models()

            # Use provider string directly, no mapping required
            # Scenario A: Don't write the key when saving to file
            legacy_model = {
                "provider": llm_config.provider,
                "model_name": llm_config.model_name,
                "api_key": "",
                "base_url": llm_config.api_base,
                "max_tokens": llm_config.max_tokens,
                "temperature": llm_config.temperature,
                "enabled": llm_config.enabled
            }
            
            # Find and update existing configurations, or add new ones
            updated = False
            for i, model in enumerate(legacy_models):
                if (model.get("provider") == legacy_model["provider"] and 
                    model.get("model_name") == legacy_model["model_name"]):
                    legacy_models[i] = legacy_model
                    updated = True
                    break
            
            if not updated:
                legacy_models.append(legacy_model)
            
            self._save_json_file(self.paths.models_json, legacy_models, "models")
            return True
            
        except Exception as e:
            print(f"Failed to save LLM configuration: {e}")
            return False
    
    # ==================== System settings management ====================
    
    def get_system_settings(self) -> Dict[str, Any]:
        """Get system settings"""
        return self._load_json_file(self.paths.settings_json, "settings")
    
    def save_system_settings(self, settings: Dict[str, Any]) -> bool:
        """Save system settings (keep existing fields, add new field mappings)"""
        try:
            print(f"📝 [unified_config] save_system_settings called")
            print(f"📝 [unified_config] The settings received contain {len(settings)} item")

            # Check key fields
            if "quick_analysis_model" in settings:
                print(f"  ✓ [unified_config] contains quick_analysis_model: {settings['quick_analysis_model']}")
            else:
                print(f"  ⚠️  [unified_config] Not included quick_analysis_model")

            if "deep_analysis_model" in settings:
                print(f"  ✓ [unified_config] contains deep_analysis_model: {settings['deep_analysis_model']}")
            else:
                print(f"  ⚠️  [unified_config] Not included deep_analysis_model")

            # Read existing configuration
            print(f"📖 [unified_config] Read existing configuration file: {self.paths.settings_json}")
            current_settings = self.get_system_settings()
            print(f"📖 [unified_config] Existing configuration contains {len(current_settings)} item")

            # Merge configuration (new configuration overwrites old configuration)
            merged_settings = current_settings.copy()
            merged_settings.update(settings)
            print(f"🔀 [unified_config] The merged configuration contains {len(merged_settings)} item")

            # Add field name mapping (new field name -> old field name)
            if "quick_analysis_model" in settings:
                merged_settings["quick_think_llm"] = settings["quick_analysis_model"]
                print(f"  ✓ [unified_config] mapping quick_analysis_model -> quick_think_llm: {settings['quick_analysis_model']}")

            if "deep_analysis_model" in settings:
                merged_settings["deep_think_llm"] = settings["deep_analysis_model"]
                print(f"  ✓ [unified_config] mapping deep_analysis_model -> deep_think_llm: {settings['deep_analysis_model']}")

            # Print the final configuration to be saved
            print(f"💾 [unified_config] About to save to file:")
            if "quick_think_llm" in merged_settings:
                print(f"  ✓ quick_think_llm: {merged_settings['quick_think_llm']}")
            if "deep_think_llm" in merged_settings:
                print(f"  ✓ deep_think_llm: {merged_settings['deep_think_llm']}")
            if "quick_analysis_model" in merged_settings:
                print(f"  ✓ quick_analysis_model: {merged_settings['quick_analysis_model']}")
            if "deep_analysis_model" in merged_settings:
                print(f"  ✓ deep_analysis_model: {merged_settings['deep_analysis_model']}")

            # Save the merged configuration
            print(f"💾 [unified_config] save to file: {self.paths.settings_json}")
            self._save_json_file(self.paths.settings_json, merged_settings, "settings")
            print(f"✅ [unified_config] Configuration saved successfully")

            return True
        except Exception as e:
            print(f"❌ [unified_config] Failed to save system settings: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def get_default_model(self) -> str:
        """Get the default model (backwards compatible)"""
        settings = self.get_system_settings()
        # Prioritize returning to fast analysis models to maintain backward compatibility
        return settings.get("quick_analysis_model", settings.get("default_model", "qwen-turbo"))

    def set_default_model(self, model_name: str) -> bool:
        """Set default model (backward compatibility)"""
        settings = self.get_system_settings()
        settings["quick_analysis_model"] = model_name
        return self.save_system_settings(settings)

    def get_quick_analysis_model(self) -> str:
        """Get a quick analysis model"""
        settings = self.get_system_settings()
        # Read the new field name first, if it does not exist, read the old field name (backward compatibility)
        return settings.get("quick_analysis_model") or settings.get("quick_think_llm", "qwen-turbo")

    def get_deep_analysis_model(self) -> str:
        """Get an in-depth analysis model"""
        settings = self.get_system_settings()
        # Read the new field name first, if it does not exist, read the old field name (backward compatibility)
        return settings.get("deep_analysis_model") or settings.get("deep_think_llm", "qwen-max")

    def set_analysis_models(self, quick_model: str, deep_model: str) -> bool:
        """Set up the analysis model"""
        settings = self.get_system_settings()
        settings["quick_analysis_model"] = quick_model
        settings["deep_analysis_model"] = deep_model
        return self.save_system_settings(settings)
    
    # ==================== Data source configuration management ====================
    
    def get_data_source_configs(self) -> List[DataSourceConfig]:
        """Get data source configuration - read from database first, fallback to hardcoded (synchronous version)

        Use class-level 5-minute TTL caching to avoid querying MongoDB every time the DataSourceManager is initialized.
        """
        now = time.monotonic()
        if (UnifiedConfigManager._ds_config_cache is not None and
                now - UnifiedConfigManager._ds_config_cache_time < UnifiedConfigManager._DS_CONFIG_CACHE_TTL):
            return UnifiedConfigManager._ds_config_cache

        try:
            # 🔥 Prioritize reading configuration from database (using synchronous connection)
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            config_collection = db.system_configs

            # Get the latest activation configuration
            config_data = config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data and config_data.get('data_source_configs'):
                # Read configuration from database
                data_source_configs = config_data.get('data_source_configs', [])
                print(f"✅ [unified_config] read from database {len(data_source_configs)} data source configuration")

                # Convert to DataSourceConfig object
                result = []
                for ds_config in data_source_configs:
                    try:
                        result.append(DataSourceConfig(**ds_config))
                    except Exception as e:
                        print(f"⚠️ [unified_config] Failed to parse data source configuration: {e}, Configuration: {ds_config}")
                        continue

                # Sort by priority (larger numbers have higher priority)
                result.sort(key=lambda x: x.priority, reverse=True)

                # 🆕 Apply the enabled override in .env (the switch set by .env has the highest priority)
                _apply_env_overrides(result)

                UnifiedConfigManager._ds_config_cache = result
                UnifiedConfigManager._ds_config_cache_time = now
                return result
            else:
                print("⚠️ [unified_config] There is no data source configuration in the database, use hard-coded configuration")
        except Exception as e:
            print(f"⚠️ [unified_config] Failed to read data source configuration from database: {e}, Use hardcoded configuration")

        # 🔥 Fallback to hardcoded configuration (compatibility)
        settings = self.get_system_settings()
        data_sources = []

        # AKShare (Enabled by default)
        akshare_config = DataSourceConfig(
            name="AKShare",
            type=DataSourceType.AKSHARE,
            endpoint="https://akshare.akfamily.xyz",
            enabled=True,
            priority=1,
            description="AKShare Open source financial data interface"
        )
        data_sources.append(akshare_config)

        # Tushare (If configured) - Check both settings.json and .env files
        tushare_token = settings.get("tushare_token") or os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_API_KEY")
        if tushare_token:
            tushare_config = DataSourceConfig(
                name="Tushare",
                type=DataSourceType.TUSHARE,
                api_key=tushare_token,
                endpoint="http://api.tushare.pro",
                enabled=True,
                priority=2,
                description="Tushare Professional financial data interface"
            )
            data_sources.append(tushare_config)

        try:
            from app.core.config import settings as runtime_settings

            qmt_enabled = bool(getattr(runtime_settings, "QMT_UNIFIED_ENABLED", False))
            qmt_token = getattr(runtime_settings, "QMT_TOKEN", "")
            qmt_data_dir = getattr(runtime_settings, "QMT_DATA_DIR", "")
            qmt_config_params = {
                "listen_port_range": getattr(runtime_settings, "QMT_LISTEN_PORT_RANGE", "58620-58650"),
                "init_markets": getattr(runtime_settings, "QMT_INIT_MARKETS", "SH,SZ,BJ"),
                "auto_download_history": getattr(runtime_settings, "QMT_AUTO_DOWNLOAD_HISTORY", True),
                "auto_download_financial": getattr(runtime_settings, "QMT_AUTO_DOWNLOAD_FINANCIAL", False),
                "auto_download_sector": getattr(runtime_settings, "QMT_AUTO_DOWNLOAD_SECTOR", True),
            }
            if qmt_data_dir:
                qmt_config_params["data_dir"] = qmt_data_dir
            if getattr(runtime_settings, "QMT_ALLOW_OPTIMIZE_ADDRESSES", ""):
                qmt_config_params["allow_optimize_addresses"] = getattr(runtime_settings, "QMT_ALLOW_OPTIMIZE_ADDRESSES", "")
            if getattr(runtime_settings, "QMT_KLINE_MIRROR_MARKETS", ""):
                qmt_config_params["kline_mirror_markets"] = getattr(runtime_settings, "QMT_KLINE_MIRROR_MARKETS", "")
            if getattr(runtime_settings, "QMT_HISTORY_START_TIME", ""):
                qmt_config_params["history_start_time"] = getattr(runtime_settings, "QMT_HISTORY_START_TIME", "")

            if qmt_enabled or qmt_token or qmt_data_dir:
                qmt_config = DataSourceConfig(
                    name="QMT",
                    type=DataSourceType.QMT,
                    api_key=qmt_token or None,
                    endpoint="miniqmt://local",
                    enabled=qmt_enabled,
                    priority=2,
                    description="QMT local data interface",
                    config_params=qmt_config_params,
                )
                data_sources.append(qmt_config)

            # BaoStock
            baostock_enabled = bool(getattr(runtime_settings, "ENABLE_BAOSTOCK", False))
            baostock_config = DataSourceConfig(
                name="BaoStock",
                type=DataSourceType.BAOSTOCK,
                endpoint="baostock://local",
                enabled=baostock_enabled,
                priority=0,
                description="BaoStock Open source financial data interface"
            )
            data_sources.append(baostock_config)
        except Exception:
            pass

        # Sort by priority
        data_sources.sort(key=lambda x: x.priority, reverse=True)
        return data_sources

    async def get_data_source_configs_async(self) -> List[DataSourceConfig]:
        """Get data source configuration - read from database first, fallback to hardcoded (asynchronous version)"""
        try:
            # 🔥 Prioritize reading configuration from the database (using an asynchronous connection)
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            config_collection = db.system_configs

            # Get the latest activation configuration
            config_data = await config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data and config_data.get('data_source_configs'):
                # Read configuration from database
                data_source_configs = config_data.get('data_source_configs', [])
                print(f"✅ [unified_config] read from database {len(data_source_configs)} data source configuration")

                # Convert to DataSourceConfig object
                result = []
                for ds_config in data_source_configs:
                    try:
                        result.append(DataSourceConfig(**ds_config))
                    except Exception as e:
                        print(f"⚠️ [unified_config] Failed to parse data source configuration: {e}, Configuration: {ds_config}")
                        continue

                # Sort by priority (larger numbers have higher priority)
                result.sort(key=lambda x: x.priority, reverse=True)

                # 🆕 Apply the enabled override in .env
                _apply_env_overrides(result)

                return result
            else:
                print("⚠️ [unified_config] There is no data source configuration in the database, use hard-coded configuration")
        except Exception as e:
            print(f"⚠️ [unified_config] Failed to read data source configuration from database: {e}, Use hardcoded configuration")

        # 🔥 Fallback to hardcoded configuration (compatibility)
        settings = self.get_system_settings()
        data_sources = []

        # AKShare (Enabled by default)
        akshare_config = DataSourceConfig(
            name="AKShare",
            type=DataSourceType.AKSHARE,
            endpoint="https://akshare.akfamily.xyz",
            enabled=True,
            priority=1,
            description="AKShare Open source financial data interface"
        )
        data_sources.append(akshare_config)

        # Tushare (If configured) - Check both settings.json and .env files
        tushare_token = settings.get("tushare_token") or os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_API_KEY")
        if tushare_token:
            tushare_config = DataSourceConfig(
                name="Tushare",
                type=DataSourceType.TUSHARE,
                api_key=tushare_token,
                endpoint="http://api.tushare.pro",
                enabled=True,
                priority=2,
                description="Tushare Professional financial data interface"
            )
            data_sources.append(tushare_config)

        try:
            from app.core.config import settings as runtime_settings

            qmt_enabled = bool(getattr(runtime_settings, "QMT_UNIFIED_ENABLED", False))
            qmt_token = getattr(runtime_settings, "QMT_TOKEN", "")
            qmt_data_dir = getattr(runtime_settings, "QMT_DATA_DIR", "")
            qmt_config_params = {
                "listen_port_range": getattr(runtime_settings, "QMT_LISTEN_PORT_RANGE", "58620-58650"),
                "init_markets": getattr(runtime_settings, "QMT_INIT_MARKETS", "SH,SZ,BJ"),
                "auto_download_history": getattr(runtime_settings, "QMT_AUTO_DOWNLOAD_HISTORY", True),
                "auto_download_financial": getattr(runtime_settings, "QMT_AUTO_DOWNLOAD_FINANCIAL", False),
                "auto_download_sector": getattr(runtime_settings, "QMT_AUTO_DOWNLOAD_SECTOR", True),
            }
            if qmt_data_dir:
                qmt_config_params["data_dir"] = qmt_data_dir
            if getattr(runtime_settings, "QMT_ALLOW_OPTIMIZE_ADDRESSES", ""):
                qmt_config_params["allow_optimize_addresses"] = getattr(runtime_settings, "QMT_ALLOW_OPTIMIZE_ADDRESSES", "")
            if getattr(runtime_settings, "QMT_KLINE_MIRROR_MARKETS", ""):
                qmt_config_params["kline_mirror_markets"] = getattr(runtime_settings, "QMT_KLINE_MIRROR_MARKETS", "")
            if getattr(runtime_settings, "QMT_HISTORY_START_TIME", ""):
                qmt_config_params["history_start_time"] = getattr(runtime_settings, "QMT_HISTORY_START_TIME", "")

            if qmt_enabled or qmt_token or qmt_data_dir:
                qmt_config = DataSourceConfig(
                    name="QMT",
                    type=DataSourceType.QMT,
                    api_key=qmt_token or None,
                    endpoint="miniqmt://local",
                    enabled=qmt_enabled,
                    priority=2,
                    description="QMT local data interface",
                    config_params=qmt_config_params,
                )
                data_sources.append(qmt_config)

            # BaoStock
            baostock_enabled = bool(getattr(runtime_settings, "ENABLE_BAOSTOCK", False))
            baostock_config = DataSourceConfig(
                name="BaoStock",
                type=DataSourceType.BAOSTOCK,
                endpoint="baostock://local",
                enabled=baostock_enabled,
                priority=0,
                description="BaoStock Open source financial data interface"
            )
            data_sources.append(baostock_config)
        except Exception:
            pass

        # Finnhub (If configured)
        if settings.get("finnhub_api_key"):
            finnhub_config = DataSourceConfig(
                name="Finnhub",
                type=DataSourceType.FINNHUB,
                api_key=settings.get("finnhub_api_key"),
                endpoint="https://finnhub.io/api/v1",
                enabled=True,
                priority=3,
                description="Finnhub Stock data interface"
            )
            data_sources.append(finnhub_config)

        return data_sources
    
    # ==================== Database configuration management ====================
    
    def get_database_configs(self) -> List[DatabaseConfig]:
        """Get database configuration"""
        configs = []
        
        # MongoDB Configuration
        mongodb_config = DatabaseConfig(
            name="MongoDB main library",
            type=DatabaseType.MONGODB,
            host=os.getenv("MONGODB_HOST", "localhost"),
            port=int(os.getenv("MONGODB_PORT", "27017")),
            database=os.getenv("MONGODB_DATABASE", "tradingagents"),
            enabled=True,
            description="MongoDB master database"
        )
        configs.append(mongodb_config)
        
        # Redis Configuration
        redis_config = DatabaseConfig(
            name="Redis cache",
            type=DatabaseType.REDIS,
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            database=os.getenv("REDIS_DB", "0"),
            enabled=True,
            description="Redis cache database"
        )
        configs.append(redis_config)
        
        return configs
    
    # ==================== Unified configuration interface ====================
    
    async def get_unified_system_config(self) -> SystemConfig:
        """Get unified system configuration"""
        try:
            config = SystemConfig(
                config_name="Unified system configuration",
                config_type="unified",
                llm_configs=self.get_llm_configs(),
                default_llm=self.get_default_model(),
                data_source_configs=self.get_data_source_configs(),
                database_configs=self.get_database_configs(),
                system_settings=self.get_system_settings()
            )
            return config
        except Exception as e:
            print(f"Failed to obtain unified configuration: {e}")
            # Return to default configuration
            return SystemConfig(
                config_name="Default configuration",
                config_type="default",
                llm_configs=[],
                data_source_configs=[],
                database_configs=[],
                system_settings={}
            )
    
    def sync_to_legacy_format(self, system_config: SystemConfig) -> bool:
        """Synchronize configuration to legacy format"""
        try:
            # Synchronize model configuration
            for llm_config in system_config.llm_configs:
                self.save_llm_config(llm_config)

            # read existing settings.json
            current_settings = self.get_system_settings()

            # Synchronize system settings (preserve existing fields, update only required fields)
            settings = current_settings.copy()

            # Map new field names to old field names
            if "quick_analysis_model" in system_config.system_settings:
                settings["quick_think_llm"] = system_config.system_settings["quick_analysis_model"]
                settings["quick_analysis_model"] = system_config.system_settings["quick_analysis_model"]

            if "deep_analysis_model" in system_config.system_settings:
                settings["deep_think_llm"] = system_config.system_settings["deep_analysis_model"]
                settings["deep_analysis_model"] = system_config.system_settings["deep_analysis_model"]

            if system_config.default_llm:
                settings["default_model"] = system_config.default_llm

            self.save_system_settings(settings)

            return True
        except Exception as e:
            print(f"Synchronizing configuration to legacy format failed: {e}")
            return False


# Create a global instance
unified_config = UnifiedConfigManager()
