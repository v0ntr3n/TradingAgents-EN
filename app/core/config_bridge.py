"""
Configure the bridge module
Bridge the configuration of the unified configuration system to environment variables for use by the TradingAgents core library
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.config_bridge")


def bridge_config_to_env():
    """
    Bridge unified configuration to environment variables

    This function will:
    1. Read large model manufacturer configuration (API key, timeout, temperature, etc.) from database
    2. Write configuration to environment variables
    3. Write the default model to the environment variable
    4. Write data source configuration to environment variables (API keys, timeouts, retries, etc.)
    5. Write system runtime configuration to environment variables

    In this way, the TradingAgents core library can read user-configured data through environment variables.
    """
    try:
        from app.core.unified_config import unified_config
        from app.services.config_service import config_service

        logger.info("🔧 Start bridging configuration to environment variables...")
        bridged_count = 0

        # Force enable MongoDB storage (for Token usage statistics)
        # Read configuration from .env file, enabled by default if not set
        use_mongodb_storage = os.getenv("USE_MONGODB_STORAGE", "true")
        os.environ["USE_MONGODB_STORAGE"] = use_mongodb_storage
        logger.info(f"  ✓ bridge USE_MONGODB_STORAGE: {use_mongodb_storage}")
        bridged_count += 1

        # Bridging MongoDB connection strings (built using unity tool functions)
        from tradingagents.config.mongodb_utils import build_mongodb_connection_string
        mongodb_conn_str = build_mongodb_connection_string()
        os.environ["MONGODB_CONNECTION_STRING"] = mongodb_conn_str
        logger.info(f"  ✓ bridge MONGODB_CONNECTION_STRING")
        bridged_count += 1

        # Bridge MongoDB database name
        mongodb_db_name = os.getenv("MONGODB_DATABASE_NAME", "tradingagents")
        os.environ["MONGODB_DATABASE_NAME"] = mongodb_db_name
        logger.info(f"  ✓ bridge MONGODB_DATABASE_NAME: {mongodb_db_name}")
        bridged_count += 1

        # 1. Bridge large model configuration (base API key)
        # 🔧 [priority] .env File > Database manufacturer configuration
        # 🔥 Modification: Read factory configuration from the database's llm_providers collection instead of from a JSON file
        # Only use the configuration in the database if the environment variable does not exist or is a placeholder
        try:
            # Read factory configuration using synchronous MongoDB client
            from pymongo import MongoClient
            from app.core.config import settings
            from app.models.config import LLMProvider

            # Create a synchronous MongoDB client
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            providers_collection = db.llm_providers

            # Query all manufacturer configurations
            providers_data = list(providers_collection.find())
            providers = [LLMProvider(**data) for data in providers_data]

            logger.info(f"  📊 read from database {len(providers)} Manufacturer configuration")

            for provider in providers:
                if not provider.is_active:
                    logger.debug(f"  ⏭️  Manufacturer {provider.name} Not enabled, skipped")
                    continue

                env_key = f"{provider.name.upper()}_API_KEY"
                existing_env_value = os.getenv(env_key)

                # Check if the environment variable already exists and is valid (not a placeholder)
                if existing_env_value and not existing_env_value.startswith("your_"):
                    logger.info(f"  ✓ Use the {env_key}")
                    bridged_count += 1
                elif provider.api_key and not provider.api_key.startswith("your_"):
                    # Database configuration is used only if the environment variable does not exist or is a placeholder
                    os.environ[env_key] = provider.api_key
                    logger.info(f"  ✓ Configured using the database manufacturer {env_key}")
                    bridged_count += 1
                else:
                    logger.debug(f"  ⏭️  {env_key} Not configured effectively API Key")

            # Close sync client
            client.close()

        except Exception as e:
            logger.error(f"❌ Failed to read manufacturer configuration from database: {e}", exc_info=True)
            logger.warning("⚠️  Will try to read the configuration from a JSON file as a fallback")

            # Fallback: Reading from a JSON file
            llm_configs = unified_config.get_llm_configs()
            for llm_config in llm_configs:
                # provider Now a string type, no longer an enum
                env_key = f"{llm_config.provider.upper()}_API_KEY"
                existing_env_value = os.getenv(env_key)

                # Check if the environment variable already exists and is valid (not a placeholder)
                if existing_env_value and not existing_env_value.startswith("your_"):
                    logger.info(f"  ✓ Use the {env_key}")
                    bridged_count += 1
                elif llm_config.enabled and llm_config.api_key:
                    # Database configuration is used only if the environment variable does not exist or is a placeholder
                    if not llm_config.api_key.startswith("your_"):
                        os.environ[env_key] = llm_config.api_key
                        logger.info(f"  ✓ Use the {env_key}")
                        bridged_count += 1
                    else:
                        logger.warning(f"  ⚠️  {env_key} Both are placeholders in .env and JSON files, skip")
                else:
                    logger.debug(f"  ⏭️  {env_key} Not configured")

        # 2. Bridge default model configuration
        default_model = unified_config.get_default_model()
        if default_model:
            os.environ['TRADINGAGENTS_DEFAULT_MODEL'] = default_model
            logger.info(f"  ✓ Bridge default model: {default_model}")
            bridged_count += 1

        quick_model = unified_config.get_quick_analysis_model()
        if quick_model:
            os.environ['TRADINGAGENTS_QUICK_MODEL'] = quick_model
            logger.info(f"  ✓ Bridging Rapid Analysis Models: {quick_model}")
            bridged_count += 1

        deep_model = unified_config.get_deep_analysis_model()
        if deep_model:
            os.environ['TRADINGAGENTS_DEEP_MODEL'] = deep_model
            logger.info(f"  ✓ Bridging deep analysis models: {deep_model}")
            bridged_count += 1

        # 3. Bridge data source configuration (base API key)
        # 🔧 [priority] .env File > Database configuration
        # 🔥 Modification: Read data source configuration from the database's system_configs collection instead of from a JSON file
        try:
            # Reading system configuration using a synchronous MongoDB client
            from pymongo import MongoClient
            from app.core.config import settings
            from app.models.config import SystemConfig

            # Create a synchronous MongoDB client
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            config_collection = db.system_configs

            # Query the latest system configuration
            config_data = config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data and config_data.get('data_source_configs'):
                system_config = SystemConfig(**config_data)
                data_source_configs = system_config.data_source_configs
                logger.info(f"  📊 read from database {len(data_source_configs)} data source configuration")
            else:
                logger.warning("  ⚠️  There is no data source configuration in the database, use JSON file configuration")
                data_source_configs = unified_config.get_data_source_configs()

            # Close sync client
            client.close()

        except Exception as e:
            logger.error(f"❌ Failed to read data source configuration from database: {e}", exc_info=True)
            logger.warning("⚠️  Will try to read the configuration from a JSON file as a fallback")
            data_source_configs = unified_config.get_data_source_configs()

        # 🔧 JD Cloud mode: Skip the data source configuration bridge and directly use the environment variable TUSHARE_TOKEN
        from app.core.jdyun import is_jdyun_mode
        if is_jdyun_mode():
            tushare_token = os.getenv('TUSHARE_TOKEN', '')
            if tushare_token:
                logger.info(f"  ✓ Jingdong cloud model: Use environment variables TUSHARE_TOKEN")
                bridged_count += 1
            else:
                logger.warning("  ⚠️  Jingdong cloud model: TUSHARE_TOKEN Environment variable not set")

        for ds_config in data_source_configs:
            if is_jdyun_mode():
                break  # Skip data source configuration traversal in JD Cloud mode
            if ds_config.enabled and ds_config.api_key:
                # Tushare Token
                # 🔥 Priority: Database Configuration > .env File (takes effect immediately after the user modifies it in the web background)
                if ds_config.type.value == 'tushare':
                    existing_token = os.getenv('TUSHARE_TOKEN')

                    # Prefer database configuration
                    if ds_config.api_key and not ds_config.api_key.startswith("your_"):
                        os.environ['TUSHARE_TOKEN'] = ds_config.api_key
                        logger.info(f"  ✓ Use the database TUSHARE_TOKEN")
                        if existing_token and existing_token != ds_config.api_key:
                            logger.info(f"  ℹ️  Overridden in .env file TUSHARE_TOKEN")
                    # Downgrade to .env file configuration
                    elif existing_token and not existing_token.startswith("your_"):
                        logger.info(f"  ✓ Use the TUSHARE_TOKEN")
                        logger.info(f"  ℹ️  No valid TUSHARE_TOKEN is configured in the database, use .env downgrade scheme")
                    else:
                        logger.warning(f"  ⚠️  TUSHARE_TOKEN No valid values configured in either database or .env")
                        continue
                    bridged_count += 1

                # FinnHub API Key
                # 🔥 Priority: Database Configuration > .env File
                elif ds_config.type.value == 'finnhub':
                    existing_key = os.getenv('FINNHUB_API_KEY')

                    # Prefer database configuration
                    if ds_config.api_key and not ds_config.api_key.startswith("your_"):
                        os.environ['FINNHUB_API_KEY'] = ds_config.api_key
                        logger.info(f"  ✓ Use the database FINNHUB_API_KEY")
                        if existing_key and existing_key != ds_config.api_key:
                            logger.info(f"  ℹ️  Overridden in .env file FINNHUB_API_KEY")
                    # Downgrade to .env file configuration
                    elif existing_key and not existing_key.startswith("your_"):
                        logger.info(f"  ✓ Use the FINNHUB_API_KEY")
                        logger.info(f"  ℹ️  A valid FINNHUB_API_KEY is not configured in the database, use the .env downgrade scheme")
                    else:
                        logger.warning(f"  ⚠️  FINNHUB_API_KEY No valid values configured in either database or .env")
                        continue
                    bridged_count += 1

                # QMT Quote Token (optional)
                elif ds_config.type.value == 'qmt':
                    existing_token = os.getenv('QMT_TOKEN')

                    if ds_config.api_key and not ds_config.api_key.startswith("your_"):
                        os.environ['QMT_TOKEN'] = ds_config.api_key
                        logger.info(f"  ✓ Use the database QMT_TOKEN (length: {len(ds_config.api_key)})")
                        if existing_token and existing_token != ds_config.api_key:
                            logger.info("  ℹ️  Overridden in .env file QMT_TOKEN")
                        bridged_count += 1
                    elif existing_token and not existing_token.startswith("your_"):
                        logger.info(f"  ✓ Use the QMT_TOKEN (length: {len(existing_token)})")
                        bridged_count += 1

        # 4. Bridge data source detailed configuration (timeout, retry, cache, etc.)
        bridged_count += _bridge_datasource_details(data_source_configs)

        # 5. Bridge system runtime configuration
        bridged_count += _bridge_system_settings()

        # 6. Reinitialize the MongoDB storage for the tradingagents library
        # Because the global config_manager instance is created when the module is imported, the environment variables have not yet been bridged at that time
        try:
            from tradingagents.config.config_manager import config_manager
            from tradingagents.config.mongodb_storage import MongoDBStorage
            logger.info("🔄 Reinitialize tradingagents MongoDB storage...")

            # Debugging: Check environment variables
            from tradingagents.config.mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name
            use_mongodb = os.getenv("USE_MONGODB_STORAGE", "false")
            mongodb_conn = build_mongodb_connection_string()
            mongodb_db = get_mongodb_database_name()
            logger.info(f"  📋 USE_MONGODB_STORAGE: {use_mongodb}")
            logger.info(f"  📋 MONGODB_CONNECTION_STRING: {mongodb_conn[:30]}..." if len(mongodb_conn) > 30 else f"  📋 MONGODB_CONNECTION_STRING: {mongodb_conn}")
            logger.info(f"  📋 MONGODB_DATABASE_NAME: {mongodb_db}")

            # Create a MongoDBStorage instance directly instead of calling _init_mongodb_storage()
            # This will capture more detailed error information
            if use_mongodb.lower() == "true":
                try:
                    # 🔍 Verbose log: shows the complete connection string (for debugging)
                    logger.info(f"  🔍 The actual connection string passed in: {mongodb_conn}")
                    logger.info(f"  🔍 The actual database name passed in: {mongodb_db}")

                    config_manager.mongodb_storage = MongoDBStorage(
                        connection_string=mongodb_conn,
                        database_name=mongodb_db
                    )
                    if config_manager.mongodb_storage.is_connected():
                        logger.info("✅ tradingagents MongoDB Storage is enabled")
                    else:
                        logger.warning("⚠️ tradingagents MongoDB Connection failed, will be stored using JSON file")
                        config_manager.mongodb_storage = None
                except Exception as e:
                    logger.error(f"❌ Failed to create MongoDBStorage instance: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    config_manager.mongodb_storage = None
            else:
                logger.info("ℹ️ USE_MONGODB_STORAGE Not enabled, will use JSON file storage")
        except Exception as e:
            logger.error(f"❌ Reinitializing tradingagents MongoDB storage failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

        # 7. Sync pricing configuration to tradingagents config/pricing.json
        # Note: The configuration needs to be read from the database here, because the configuration in the file does not have pricing information
        # Synchronize pricing configuration using asynchronous method
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # In an asynchronous context, create a background task
            task = loop.create_task(_sync_pricing_config_from_db())
            task.add_done_callback(_handle_sync_task_result)
            logger.info("🔄 Pricing configuration synchronization task has been created (executed in the background)")
        except RuntimeError:
            # Not in an asynchronous context, use asyncio.run
            asyncio.run(_sync_pricing_config_from_db())

        logger.info(f"✅ Configuration of bridge is completed, total bridge {bridged_count} item configuration")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to configure bridge: {e}", exc_info=True)
        logger.warning("⚠️  TradingAgents Will use the configuration in the .env file")
        return False


def _bridge_datasource_details(data_source_configs) -> int:
    """
    Configure bridging data source details to environment variables

    Args:
        data_source_configs: Data source configuration list

    Returns:
        int: Number of bridged configuration items
    """
    bridged_count = 0

    for ds_config in data_source_configs:
        if not ds_config.enabled:
            continue

        # Note: the field name is type instead of source_type
        source_type = ds_config.type.value.upper()

        # timeout
        if ds_config.timeout:
            env_key = f"{source_type}_TIMEOUT"
            os.environ[env_key] = str(ds_config.timeout)
            logger.debug(f"  ✓ bridge {env_key}: {ds_config.timeout}")
            bridged_count += 1

        # rate limit
        if ds_config.rate_limit:
            env_key = f"{source_type}_RATE_LIMIT"
            os.environ[env_key] = str(ds_config.rate_limit / 60.0)  # Convert to requests per second
            logger.debug(f"  ✓ bridge {env_key}: {ds_config.rate_limit / 60.0}")
            bridged_count += 1

        # Maximum number of retries (obtained from config_params)
        if ds_config.config_params and 'max_retries' in ds_config.config_params:
            env_key = f"{source_type}_MAX_RETRIES"
            os.environ[env_key] = str(ds_config.config_params['max_retries'])
            logger.debug(f"  ✓ bridge {env_key}: {ds_config.config_params['max_retries']}")
            bridged_count += 1

        # Cache TTL (obtained from config_params)
        if ds_config.config_params and 'cache_ttl' in ds_config.config_params:
            env_key = f"{source_type}_CACHE_TTL"
            os.environ[env_key] = str(ds_config.config_params['cache_ttl'])
            logger.debug(f"  ✓ bridge {env_key}: {ds_config.config_params['cache_ttl']}")
            bridged_count += 1

        # Whether to enable caching (obtained from config_params)
        if ds_config.config_params and 'cache_enabled' in ds_config.config_params:
            env_key = f"{source_type}_CACHE_ENABLED"
            os.environ[env_key] = str(ds_config.config_params['cache_enabled']).lower()
            logger.debug(f"  ✓ bridge {env_key}: {ds_config.config_params['cache_enabled']}")
            bridged_count += 1

        if source_type == "QMT" and ds_config.config_params:
            qmt_param_map = {
                'data_dir': 'QMT_DATA_DIR',
                'listen_port': 'QMT_LISTEN_PORT',
                'listen_port_range': 'QMT_LISTEN_PORT_RANGE',
                'init_markets': 'QMT_INIT_MARKETS',
                'kline_mirror_markets': 'QMT_KLINE_MIRROR_MARKETS',
                'allow_optimize_addresses': 'QMT_ALLOW_OPTIMIZE_ADDRESSES',
                'history_start_time': 'QMT_HISTORY_START_TIME',
                'start_local_service': 'QMT_START_LOCAL_SERVICE',
                'kline_mirror_enabled': 'QMT_KLINE_MIRROR_ENABLED',
                'auto_download_history': 'QMT_AUTO_DOWNLOAD_HISTORY',
                'auto_download_financial': 'QMT_AUTO_DOWNLOAD_FINANCIAL',
                'auto_download_sector': 'QMT_AUTO_DOWNLOAD_SECTOR',
            }

            for param_key, env_key in qmt_param_map.items():
                if param_key not in ds_config.config_params:
                    continue

                value = ds_config.config_params[param_key]
                if isinstance(value, list):
                    normalized = ",".join(str(item) for item in value)
                elif isinstance(value, bool):
                    normalized = str(value).lower()
                else:
                    normalized = str(value)

                os.environ[env_key] = normalized
                logger.debug(f"  ✓ bridge {env_key}: {normalized}")
                bridged_count += 1

    if bridged_count > 0:
        logger.info(f"  ✓ Bridge data source configuration details: {bridged_count} item")

    return bridged_count


def _bridge_system_settings() -> int:
    """
    Configure the bridge system runtime to environment variables

    Returns:
        int: Number of bridged configuration items
    """
    try:
        # Using a synchronous MongoDB client
        from pymongo import MongoClient
        from app.core.config import settings

        # Create a sync client
        client = MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )

        try:
            db = client[settings.MONGO_DB]
            # Read the activated configuration from the system_configs collection
            config_doc = db.system_configs.find_one({"is_active": True})

            if not config_doc or 'system_settings' not in config_doc:
                logger.debug("  ⚠️  System setting is empty, skip bridging")
                return 0

            system_settings = config_doc['system_settings']
        except Exception as e:
            logger.debug(f"  ⚠️  Unable to get system settings from database: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return 0
        finally:
            client.close()

        if not system_settings:
            logger.debug("  ⚠️  System setting is empty, skip bridging")
            return 0

        logger.debug(f"  📋 Get {len(system_settings)} system settings")
        bridged_count = 0

        # TradingAgents Runtime configuration
        ta_settings = {
            'ta_hk_min_request_interval_seconds': 'TA_HK_MIN_REQUEST_INTERVAL_SECONDS',
            'ta_hk_timeout_seconds': 'TA_HK_TIMEOUT_SECONDS',
            'ta_hk_max_retries': 'TA_HK_MAX_RETRIES',
            'ta_hk_rate_limit_wait_seconds': 'TA_HK_RATE_LIMIT_WAIT_SECONDS',
            'ta_hk_cache_ttl_seconds': 'TA_HK_CACHE_TTL_SECONDS',
            'ta_use_app_cache': 'TA_USE_APP_CACHE',
        }

        # Token Use statistics configuration
        token_tracking_settings = {
            'enable_cost_tracking': 'ENABLE_COST_TRACKING',
            'auto_save_usage': 'AUTO_SAVE_USAGE',
        }

        for setting_key, env_key in ta_settings.items():
            # Check whether the environment variable has been set in the .env file
            env_value = os.getenv(env_key)
            if env_value is not None:
                # .env has been set in the file, the value of .env will be used first.
                logger.info(f"  ✓ Use the {env_key}: {env_value}")
                bridged_count += 1
            elif setting_key in system_settings:
                # .env Not set in the file, use the value in the database
                value = system_settings[setting_key]
                os.environ[env_key] = str(value).lower() if isinstance(value, bool) else str(value)
                logger.info(f"  ✓ bridge {env_key}: {value}")
                bridged_count += 1
            else:
                logger.debug(f"  ⚠️  configuration key {setting_key} does not exist in system settings")

        # Bridge Token usage statistics configuration
        for setting_key, env_key in token_tracking_settings.items():
            if setting_key in system_settings:
                value = system_settings[setting_key]
                os.environ[env_key] = str(value).lower() if isinstance(value, bool) else str(value)
                logger.info(f"  ✓ bridge {env_key}: {value}")
                bridged_count += 1
            else:
                logger.debug(f"  ⚠️  configuration key {setting_key} does not exist in system settings")

        # 🔧 Proxy configuration (HTTP/HTTPS/NO_PROXY)
        # Check if proxy is enabled
        proxy_enabled = system_settings.get('proxy_enabled', False)

        def _normalize_proxy(proxy: str) -> str:
            try:
                if not proxy:
                    return ""
                proxy = str(proxy).strip()
                if not proxy:
                    return ""
                if not proxy.startswith(("http://", "https://", "socks5://", "socks4://")):
                    proxy = f"http://{proxy}"
                return proxy
            except Exception:
                return ""

        if proxy_enabled:
            logger.info("  🔧 proxy enabled (proxy_enabled=True)")

            # HTTP_PROXY
            env_http_proxy = os.getenv("HTTP_PROXY")
            if env_http_proxy:
                logger.info(f"  ✓ Use the HTTP_PROXY: {env_http_proxy}")
                bridged_count += 1
            elif 'http_proxy' in system_settings and system_settings['http_proxy']:
                val = _normalize_proxy(system_settings['http_proxy'])
                os.environ['HTTP_PROXY'] = val
                os.environ['http_proxy'] = val  # lower case version
                logger.info(f"  ✓ bridge HTTP_PROXY: {val}")
                bridged_count += 1
            else:
                logger.debug("  ⚠️  http_proxy is not configured (DB/ENV are empty)")

            # HTTPS_PROXY
            env_https_proxy = os.getenv("HTTPS_PROXY")
            if env_https_proxy:
                logger.info(f"  ✓ Use the HTTPS_PROXY: {env_https_proxy}")
                bridged_count += 1
            elif 'https_proxy' in system_settings and system_settings['https_proxy']:
                val = _normalize_proxy(system_settings['https_proxy'])
                os.environ['HTTPS_PROXY'] = val
                os.environ['https_proxy'] = val  # lower case version
                logger.info(f"  ✓ bridge HTTPS_PROXY: {val}")
                bridged_count += 1
            else:
                logger.debug("  ⚠️  https_proxy is not configured (DB/ENV are all empty)")
        else:
            logger.info("  🔧 proxy disabled (proxy_enabled=False), Clear proxy environment variables")
            # Clear proxy environment variables
            for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
                if key in os.environ:
                    del os.environ[key]
                    logger.debug(f"  ✓ cleared {key}")

        # NO_PROXY (Used to bypass proxy for domestic domain names, always set)
        env_no_proxy = os.getenv("NO_PROXY")
        if env_no_proxy:
            # If .env has NO_PROXY set, keep the status quo (usually contains a large number of domestic domain names)
            logger.info(f"  ✓ Use the NO_PROXY: {env_no_proxy}")
            bridged_count += 1
        elif 'no_proxy' in system_settings and system_settings['no_proxy']:
            os.environ['NO_PROXY'] = str(system_settings['no_proxy']).strip()
            os.environ['no_proxy'] = str(system_settings['no_proxy']).strip()  # lower case version
            logger.info(f"  ✓ bridge NO_PROXY: {os.environ['NO_PROXY']}")
            bridged_count += 1
        else:
            logger.debug("  ⚠️  no_proxy is not configured (DB/ENV are empty)")

        # Time zone configuration
        if 'app_timezone' in system_settings:
            os.environ['APP_TIMEZONE'] = system_settings['app_timezone']
            logger.debug(f"  ✓ bridge APP_TIMEZONE: {system_settings['app_timezone']}")
            bridged_count += 1

        # currency preference
        if 'currency_preference' in system_settings:
            os.environ['CURRENCY_PREFERENCE'] = system_settings['currency_preference']
            logger.debug(f"  ✓ bridge CURRENCY_PREFERENCE: {system_settings['currency_preference']}")
            bridged_count += 1

        if bridged_count > 0:
            logger.info(f"  ✓ Bridge system runtime configuration: {bridged_count} item")

        # Sync to file system (for use by unified_config)
        try:
            print(f"🔄 [config_bridge] Prepare to synchronize system settings to the file system")
            print(f"🔄 [config_bridge] system_settings contains {len(system_settings)} item")

            # Check key fields
            if "quick_analysis_model" in system_settings:
                print(f"  ✓ [config_bridge] contains quick_analysis_model: {system_settings['quick_analysis_model']}")
            else:
                print(f"  ⚠️  [config_bridge] Not included quick_analysis_model")

            if "deep_analysis_model" in system_settings:
                print(f"  ✓ [config_bridge] contains deep_analysis_model: {system_settings['deep_analysis_model']}")
            else:
                print(f"  ⚠️  [config_bridge] Not included deep_analysis_model")

            from app.core.unified_config import unified_config
            result = unified_config.save_system_settings(system_settings)

            if result:
                logger.info(f"  ✓ System settings synced to file system")
                print(f"✅ [config_bridge] System settings synchronized successfully")
            else:
                logger.warning(f"  ⚠️  System settings sync return False")
                print(f"⚠️  [config_bridge] System settings sync return False")
        except Exception as e:
            logger.warning(f"  ⚠️  Syncing system settings to file system failed: {e}")
            print(f"❌ [config_bridge] Syncing system settings to file system failed: {e}")
            import traceback
            print(traceback.format_exc())

        return bridged_count

    except Exception as e:
        logger.warning(f"  ⚠️  Bridge system setup failed: {e}")
        return 0


def get_bridged_api_key(provider: str) -> Optional[str]:
    """
    Get the bridge s API key
    
    Args:
        provider: Provider name (Such as: openai, deepseek, dashscope)
    
    Returns:
        API Key, returned if it does not exist None
    """
    env_key = f"{provider.upper()}_API_KEY"
    return os.environ.get(env_key)


def get_bridged_model(model_type: str = "default") -> Optional[str]:
    """
    Get the bridged model name
    
    Args:
        model_type: Model type (default, quick, deep)
    
    Returns:
        Model name, returned if it does not exist None
    """
    if model_type == "quick":
        return os.environ.get('TRADINGAGENTS_QUICK_MODEL')
    elif model_type == "deep":
        return os.environ.get('TRADINGAGENTS_DEEP_MODEL')
    else:
        return os.environ.get('TRADINGAGENTS_DEFAULT_MODEL')


def clear_bridged_config():
    """
    Clear bridge configuration

    Used for testing or reloading configuration
    """
    keys_to_clear = [
        # Model configuration
        'TRADINGAGENTS_DEFAULT_MODEL',
        'TRADINGAGENTS_QUICK_MODEL',
        'TRADINGAGENTS_DEEP_MODEL',
        # Data source API key
        'TUSHARE_TOKEN',
        'FINNHUB_API_KEY',
        # System configuration
        'APP_TIMEZONE',
        'CURRENCY_PREFERENCE',
    ]

    # Clear all possible API keys
    providers = ['OPENAI', 'ANTHROPIC', 'GOOGLE', 'DEEPSEEK', 'DASHSCOPE', 'QIANFAN']
    for provider in providers:
        keys_to_clear.append(f'{provider}_API_KEY')

    # Clear data source details configuration
    data_sources = ['TUSHARE', 'AKSHARE', 'FINNHUB']
    for ds in data_sources:
        keys_to_clear.extend([
            f'{ds}_TIMEOUT',
            f'{ds}_RATE_LIMIT',
            f'{ds}_MAX_RETRIES',
            f'{ds}_CACHE_TTL',
            f'{ds}_CACHE_ENABLED',
        ])

    # Clear TradingAgents runtime configuration
    ta_runtime_keys = [
        'TA_HK_MIN_REQUEST_INTERVAL_SECONDS',
        'TA_HK_TIMEOUT_SECONDS',
        'TA_HK_MAX_RETRIES',
        'TA_HK_RATE_LIMIT_WAIT_SECONDS',
        'TA_HK_CACHE_TTL_SECONDS',
        'TA_USE_APP_CACHE',
    ]
    keys_to_clear.extend(ta_runtime_keys)

    for key in keys_to_clear:
        if key in os.environ:
            del os.environ[key]
            logger.debug(f"  Clear environment variables: {key}")

    logger.info("✅ Cleared configuration for all bridges")


def reload_bridged_config():
    """
    Reload the bridge s configuration

    Used to re-bridge after configuration update
    """
    logger.info("🔄 Reload configuration bridge...")
    clear_bridged_config()
    return bridge_config_to_env()


def _sync_pricing_config(llm_configs):
    """
    Sync pricing configuration to tradingagents config/pricing.json

    Args:
        llm_configs: LLM Configuration list
    """
    try:
        # Get the config directory of the project root directory
        project_root = Path(__file__).parent.parent.parent
        config_dir = project_root / "config"
        config_dir.mkdir(exist_ok=True)

        pricing_file = config_dir / "pricing.json"

        # Build a list of pricing configurations
        pricing_configs = []
        for llm_config in llm_configs:
            if llm_config.enabled:
                pricing_config = {
                    # provider Now a string type, no longer an enum
                    "provider": llm_config.provider,
                    "model_name": llm_config.model_name,
                    "input_price_per_1k": llm_config.input_price_per_1k or 0.0,
                    "output_price_per_1k": llm_config.output_price_per_1k or 0.0,
                    "currency": llm_config.currency or "CNY"
                }
                pricing_configs.append(pricing_config)

        # save to file
        with open(pricing_file, 'w', encoding='utf-8') as f:
            json.dump(pricing_configs, f, ensure_ascii=False, indent=2)

        logger.info(f"  ✓ Sync pricing configuration to {pricing_file}: {len(pricing_configs)} models")

    except Exception as e:
        logger.warning(f"  ⚠️  Synchronized pricing configuration failed: {e}")


def sync_pricing_config_now():
    """
    Immediately synchronize pricing configuration (for real-time synchronization after configuration updates)

    Note: This function will perform synchronization operations asynchronously in the background
    """
    import asyncio

    try:
        # If in an asynchronous context, create a background task
        try:
            loop = asyncio.get_running_loop()
            # In an asynchronous context, create a background task (without waiting for completion)
            task = loop.create_task(_sync_pricing_config_from_db())
            # Add callback to log errors
            task.add_done_callback(_handle_sync_task_result)
            logger.info("🔄 Pricing configuration synchronization task has been created (executed in the background)")
            return True
        except RuntimeError:
            # Not in an asynchronous context, use asyncio.run
            asyncio.run(_sync_pricing_config_from_db())
            return True
    except Exception as e:
        logger.error(f"❌ Immediate synchronization of pricing configuration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def _handle_sync_task_result(task):
    """Processing the results of synchronization tasks"""
    try:
        task.result()
    except Exception as e:
        logger.error(f"❌ Pricing configuration synchronization task execution failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


def _sync_pricing_config_from_db_sync():
    """Sync pricing configuration from database (sync versions, avoid relying on current event loop state)."""
    from app.core.database import get_mongo_db_sync

    db = get_mongo_db_sync()

    config = db['system_configs'].find_one(
        {'is_active': True},
        sort=[('version', -1)]
    )

    if not config:
        logger.warning("⚠️  Activated configuration not found")
        return

    project_root = Path(__file__).parent.parent.parent
    config_dir = project_root / "config"
    config_dir.mkdir(exist_ok=True)

    pricing_file = config_dir / "pricing.json"

    pricing_configs = []
    for llm_config in config.get('llm_configs', []):
        if llm_config.get('enabled', False):
            provider = llm_config.get('provider')

            if hasattr(provider, 'value'):
                provider = provider.value

            pricing_configs.append({
                "provider": provider,
                "model_name": llm_config.get('model_name'),
                "input_price_per_1k": llm_config.get('input_price_per_1k') or 0.0,
                "output_price_per_1k": llm_config.get('output_price_per_1k') or 0.0,
                "currency": llm_config.get('currency') or "CNY"
            })

    with open(pricing_file, 'w', encoding='utf-8') as f:
        json.dump(pricing_configs, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ Sync pricing configuration to {pricing_file}: {len(pricing_configs)} models")


async def _sync_pricing_config_from_db():
    """
    Sync pricing configuration from database (asynchronous version)
    """
    try:
        import asyncio

        await asyncio.to_thread(_sync_pricing_config_from_db_sync)

    except Exception as e:
        logger.error(f"❌ Syncing pricing configuration from database failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


# Export function
__all__ = [
    'bridge_config_to_env',
    'get_bridged_api_key',
    'get_bridged_model',
    'clear_bridged_config',
    'reload_bridged_config',
    'sync_pricing_config_now',
]

