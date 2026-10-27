from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict
import re
import logging

from app.core.config import settings
from app.routers.auth_db import get_current_user

router = APIRouter()
logger = logging.getLogger("webapi")

SENSITIVE_KEYS = {
    "MONGODB_PASSWORD",
    "REDIS_PASSWORD",
    "JWT_SECRET",
    "CSRF_SECRET",
    "STOCK_DATA_API_KEY",
    "REFRESH_TOKEN_EXPIRE_DAYS",  # not sensitive itself, but keep for completeness
}

MASK = "***"


def _mask_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in SENSITIVE_KEYS:
        return MASK
    # Mask URLs that may contain credentials
    if key in {"MONGO_URI", "REDIS_URL"} and isinstance(value, str):
        v = value
        # mongodb://user:pass@host:port/db?...
        v = re.sub(r"(mongodb://[^:/?#]+):([^@/]+)@", r"\1:***@", v)
        # redis://:pass@host:port/db
        v = re.sub(r"(redis://:)[^@/]+@", r"\1***@", v)
        return v
    return value


def _build_summary() -> Dict[str, Any]:
    raw = settings.model_dump()
    # Attach derived URLs
    raw["MONGO_URI"] = settings.MONGO_URI
    raw["REDIS_URL"] = settings.REDIS_URL

    summary: Dict[str, Any] = {}
    for k, v in raw.items():
        summary[k] = _mask_value(k, v)
    return summary


@router.get("/config/summary", tags=["system"], summary="Configuration summary (sensitive items have been blocked, administrator required)")
async def get_config_summary(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Returns a summary of the settings currently in effect. Sensitive fields will be *** Mask display.
    Access control: Administrator status required.
    """
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return {"settings": _build_summary()}


@router.get("/config/validate", tags=["system"], summary="Verify configuration integrity")
async def validate_config():
    """
    Verify the integrity and validity of the system configuration.
    Return verification results, including missing configuration items and invalid configurations.

    Verify content:
    1. Environment variable configuration (.env file)
    2. MongoDB Configurations stored in (large models, data sources, etc.)

    Note: This interface will first be reloaded from MongoDB into environment variables and then verified.
    """
    from app.core.startup_validator import StartupValidator
    from app.core.config_bridge import bridge_config_to_env
    from app.services.config_service import config_service

    try:
        # 🔧 steps 1: Overloaded configuration - reads configuration from MongoDB and bridges to environment variables
        try:
            bridge_config_to_env()
            logger.info("✅ Configuration has been reloaded from MongoDB into environment variables")
        except Exception as e:
            logger.warning(f"⚠️  Configuration reload failed: {e}, Will verify the configuration in the .env file")

        # 🔍 steps 2: Verify environment variable configuration
        validator = StartupValidator()
        env_result = validator.validate()

        # 🔍 steps 3: Verify configuration in MongoDB (vendor level)
        mongodb_validation = {
            "llm_providers": [],
            "data_source_configs": [],
            "warnings": []
        }

        try:
            from app.utils.api_key_utils import (
                is_valid_api_key,
                get_env_api_key_for_provider
            )

            # 🔥 Modification: Read raw data directly from the database to avoid using get_llm_providers() Modified data returned
            # get_llm_providers() The Key of the environment variable will be assigned to provider.api_key, making it impossible to distinguish the source.
            from pymongo import MongoClient
            from app.core.config import settings
            from app.models.config import LLMProvider

            # Create a synchronous MongoDB client
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]
            providers_collection = db.llm_providers

            # Query all manufacturer configurations (raw data)
            providers_data = list(providers_collection.find())
            llm_providers = [LLMProvider(**data) for data in providers_data]

            # Close sync client
            client.close()

            logger.info(f"🔍 Get {len(llm_providers)} A large model manufacturer")

            for provider in llm_providers:
                # Only verify enabled manufacturers
                if not provider.is_active:
                    continue

                validation_item = {
                    "name": provider.name,
                    "display_name": provider.display_name,
                    "is_active": provider.is_active,
                    "has_api_key": False,
                    "status": "Not configured",
                    "source": None,  # Identify the configuration source (database/environment)
                    "mongodb_configured": False,  # MongoDB Whether to configure
                    "env_configured": False  # Are environment variables configured?
                }

                # 🔥 Key: Check whether the original API Key in the database is valid
                db_key_valid = is_valid_api_key(provider.api_key)
                validation_item["mongodb_configured"] = db_key_valid

                # Check whether the API Key in the environment variable is valid
                env_key = get_env_api_key_for_provider(provider.name)
                env_key_valid = env_key is not None
                validation_item["env_configured"] = env_key_valid

                if db_key_valid:
                    # MongoDB There is a valid API Key in (highest priority)
                    validation_item["has_api_key"] = True
                    validation_item["status"] = "configured"
                    validation_item["source"] = "database"
                elif env_key_valid:
                    # MongoDB There is no one in the environment variable, but there is a valid one in the environment variable. API Key
                    validation_item["has_api_key"] = True
                    validation_item["status"] = "Configured (environment variable)"
                    validation_item["source"] = "environment"
                    # Prompt users with a yellow warning that they can be configured in the database
                    mongodb_validation["warnings"].append(
                        f"Large model manufacturer {provider.display_name} Use environment variable configuration. It is recommended to configure it in the database for unified management."
                    )
                else:
                    # MongoDB Neither the environment variables nor the environment variables are valid. API Key
                    validation_item["status"] = "Not configured"
                    mongodb_validation["warnings"].append(
                        f"Large model manufacturer {provider.display_name} A valid API Key is enabled but not configured (neither found in database nor environment variables)"
                    )

                mongodb_validation["llm_providers"].append(validation_item)

            # Verify data source configuration
            from app.utils.api_key_utils import (
                is_valid_api_key,
                get_env_api_key_for_datasource
            )

            system_config = await config_service.get_system_config()
            if system_config and system_config.data_source_configs:
                logger.info(f"🔍 Get {len(system_config.data_source_configs)} data source configuration")

                for ds_config in system_config.data_source_configs:
                    # Only verify enabled data sources
                    if not ds_config.enabled:
                        continue

                    validation_item = {
                        "name": ds_config.name,
                        "type": ds_config.type,
                        "enabled": ds_config.enabled,
                        "has_api_key": False,
                        "status": "Not configured",
                        "source": None,  # Identify the configuration source (database/environment/builtin)
                        "mongodb_configured": False,  # New: Whether MongoDB is configured
                        "env_configured": False  # New: Whether environment variables are configured
                    }

                    # Some data sources do not require an API Key (such as AKShare)
                    if ds_config.type in ["akshare", "yahoo", "baostock", "local", "qmt"]:
                        validation_item["has_api_key"] = True
                        validation_item["status"] = "Configured (no key required)"
                        validation_item["source"] = "builtin"
                        validation_item["mongodb_configured"] = True
                        validation_item["env_configured"] = True
                    else:
                        # Check whether the API Key in the database is valid
                        db_key_valid = is_valid_api_key(ds_config.api_key)
                        validation_item["mongodb_configured"] = db_key_valid

                        # Check whether the API Key in the environment variable is valid
                        ds_type = ds_config.type.value if hasattr(ds_config.type, 'value') else ds_config.type
                        env_key = get_env_api_key_for_datasource(ds_type)
                        env_key_valid = env_key is not None
                        validation_item["env_configured"] = env_key_valid

                        if db_key_valid:
                            # MongoDB There is a valid API Key in (highest priority)
                            validation_item["has_api_key"] = True
                            validation_item["status"] = "configured"
                            validation_item["source"] = "database"
                        elif env_key_valid:
                            # MongoDB There is no one in the environment variable, but there is a valid one in the environment variable. API Key
                            validation_item["has_api_key"] = True
                            validation_item["status"] = "Configured (environment variable)"
                            validation_item["source"] = "environment"
                            # Prompt users with a yellow warning that they can be configured in the database
                            mongodb_validation["warnings"].append(
                                f"data source {ds_config.name} Use environment variable configuration. It is recommended to configure it in the database for unified management."
                            )
                        else:
                            # MongoDB Neither the environment variables nor the environment variables are valid. API Key
                            validation_item["status"] = "Not configured"
                            mongodb_validation["warnings"].append(
                                f"data source {ds_config.name} A valid API Key is enabled but not configured (neither found in database nor environment variables)"
                            )

                    mongodb_validation["data_source_configs"].append(validation_item)

        except Exception as e:
            logger.error(f"Validating MongoDB configuration failed: {e}", exc_info=True)
            mongodb_validation["warnings"].append(f"MongoDB Configuration verification failed: {str(e)}")

        # Merge verification results
        logger.info(f"🔍 MongoDB Verification results: {len(mongodb_validation['llm_providers'])} A large model manufacturer, {len(mongodb_validation['data_source_configs'])} data sources, {len(mongodb_validation['warnings'])} warning")

        # 🔥 Modification: Validation will be considered failed only if there is a problem with the required configuration
        # MongoDB Configuration warnings (recommended configuration) do not affect the overall verification results
        # Red errors are displayed only when required configurations in environment variables are missing or invalid
        overall_success = env_result.success

        return {
            "success": True,
            "data": {
                # Environment variable verification results
                "env_validation": {
                    "success": env_result.success,
                    "missing_required": [
                        {"key": config.key, "description": config.description}
                        for config in env_result.missing_required
                    ],
                    "missing_recommended": [
                        {"key": config.key, "description": config.description}
                        for config in env_result.missing_recommended
                    ],
                    "invalid_configs": [
                        {"key": config.key, "error": config.description}
                        for config in env_result.invalid_configs
                    ],
                    "warnings": env_result.warnings
                },
                # MongoDB Configuration verification results
                "mongodb_validation": mongodb_validation,
                # Overall verification results (only required configurations considered)
                "success": overall_success
            },
            "message": "Configuration verification completed"
        }
    except Exception as e:
        logger.error(f"Configuration verification failed: {e}", exc_info=True)
        return {
            "success": False,
            "data": None,
            "message": f"Configuration verification failed: {str(e)}"
        }
