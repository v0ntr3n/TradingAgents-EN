"""
Configure management API routing
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.models.user import User
from app.models.config import (
    SystemConfigResponse, LLMConfigRequest, DataSourceConfigRequest,
    DatabaseConfigRequest, ConfigTestRequest, ConfigTestResponse,
    LLMConfig, DataSourceConfig, DatabaseConfig,
    LLMProvider, LLMProviderRequest, LLMProviderResponse,
    MarketCategory, MarketCategoryRequest, DataSourceGrouping,
    DataSourceGroupingRequest, DataSourceOrderRequest,
    ModelCatalog, ModelInfo
)
from app.services.config_service import config_service
from datetime import datetime
from app.utils.timezone import now_tz

from app.services.operation_log_service import log_operation
from app.models.operation_log import ActionType
from app.services.config_provider import provider as config_provider
from app.core.response import ok, fail
from app.utils.error_formatter import ErrorFormatter



router = APIRouter(prefix="/config", tags=["Configuration management"])
logger = logging.getLogger("webapi")


def _reload_runtime_bridge(reason: str) -> None:
    """Refresh bridge environment variables immediately after a configuration update to avoid continuing to use old values at runtime."""
    try:
        from app.core.config_bridge import reload_bridged_config

        reload_bridged_config()
        logger.info(f"🔄 Runtime configuration bridge refreshed: {reason}")
    except Exception as e:
        logger.warning(f"⚠️ Refresh runtime configuration bridge failed (ignored): {reason}, error={e}")


def _check_jdyun_mode_protected():
    """Addition, deletion, and modification operations of large models and data sources are disabled in JD Cloud mode."""
    from app.core.jdyun import is_jdyun_mode
    if is_jdyun_mode():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="JD Cloud Cooperation Edition does not support modifying large model and data source configurations. Please configure them through environment variables."
        )


# ===== JD Cloud Cooperation Edition Status Endpoint =====

@router.get("/jdyun/status", summary="Get JD Cloud configuration status")
async def get_jdyun_status(
    current_user: User = Depends(get_current_user)
):
    """Obtain the configuration status of JD Cloud cooperation version (excluding sensitive information)"""
    from app.core.jdyun import get_jdyun_status as _get_status
    return _get_status()


# ===== Gateway Platform configuration endpoint =====

class GatewayConfigRequest(BaseModel):
    """Gateway Platform configuration request (common fields + Platform-specific optional fields)"""
    app_id: Optional[str] = Field(None, description="Platform AppID (QQ / Feishu)")
    app_secret: Optional[str] = Field(None, description="platform AppSecret")
    bot_secret: Optional[str] = Field(None, description="Webhook Signing key (bot_secret of QQ Bot)")
    connection_mode: str = Field(default="websocket", description="connection mode: webhook or websocket")
    enabled: bool = Field(default=True, description="Whether to enable")
    # Exclusive to Feishu
    verification_token: Optional[str] = Field(None, description="Feishu event subscription verification Token")
    encrypt_key: Optional[str] = Field(None, description="Feishu event encryption key")
    # Exclusive for DingTalk
    app_key: Optional[str] = Field(None, description="DingTalk AppKey")
    robot_code: Optional[str] = Field(None, description="DingTalk robot coding")


@router.get("/gateway/{platform}", summary="Get Gateway platform configuration")
async def get_gateway_config(
    platform: str,
    current_user: dict = Depends(get_current_user)
):
    """Obtain the Gateway configuration of the specified IM platform (such as QQ Bot s AppID / AppSecret)"""
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        doc = await db.system_configs.find_one({"config_key": f"gateway_{platform}"})

        if platform == "feishu":
            empty = {"platform": platform, "app_id": "", "app_secret": "",
                     "verification_token": "", "encrypt_key": "",
                     "enabled": False, "configured": False}
        elif platform == "dingtalk":
            empty = {"platform": platform, "app_key": "", "app_secret": "",
                     "robot_code": "", "enabled": False, "configured": False}
        else:
            empty = {"platform": platform, "app_id": "", "app_secret": "",
                     "bot_secret": "", "connection_mode": "websocket",
                     "enabled": False, "configured": False}

        if not doc or not doc.get("config_value"):
            return ok(data=empty)

        cfg = doc["config_value"]
        result = {**empty, **{k: cfg[k] for k in cfg if k in empty}, "configured": True}
        result["enabled"] = cfg.get("enabled", True)
        return ok(data=result)
    except Exception as e:
        logger.error(f"❌ get Gateway {platform} Configuration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/gateway/{platform}", summary="Update Gateway platform configuration")
async def update_gateway_config(
    platform: str,
    req: GatewayConfigRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update the Gateway configuration for a specified IM platform and hot-reload the adapter"""
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        if platform == "feishu":
            config_value = {
                "app_id": req.app_id or "",
                "app_secret": req.app_secret or "",
                "verification_token": req.verification_token or "",
                "encrypt_key": req.encrypt_key or "",
                "enabled": req.enabled,
            }
        elif platform == "dingtalk":
            config_value = {
                "app_key": req.app_key or "",
                "app_secret": req.app_secret or "",
                "robot_code": req.robot_code or "",
                "enabled": req.enabled,
            }
        else:
            config_value = {
                "app_id": req.app_id or "",
                "app_secret": req.app_secret or "",
                "bot_secret": req.bot_secret or "",
                "connection_mode": req.connection_mode,
                "enabled": req.enabled,
            }

        await db.system_configs.update_one(
            {"config_key": f"gateway_{platform}"},
            {"$set": {
                "config_key": f"gateway_{platform}",
                "config_value": config_value,
                "updated_at": now_tz(),
                "updated_by": str(current_user.get("user_id", "")),
            }},
            upsert=True,
        )

        has_credentials = req.enabled and req.app_secret
        if platform == "qq":
            has_credentials = has_credentials and req.app_id
        elif platform == "feishu":
            has_credentials = has_credentials and req.app_id
        elif platform == "dingtalk":
            has_credentials = has_credentials and req.app_key

        if has_credentials:
            try:
                from core.gateway.router import gateway_router
                if platform == "qq":
                    from core.gateway.adapters.qq import QQAdapter
                    adapter = QQAdapter(config=config_value)
                    gateway_router.register_adapter(adapter)
                    logger.info(f"✅ Gateway {platform} Adapter has been hot reloaded")
                    if req.connection_mode == "websocket":
                        await gateway_router.start_ws_client(config_value, db)
                        logger.info(f"✅ Gateway {platform} WebSocket Client has started")
                    else:
                        await gateway_router.stop_ws_client()
                        logger.info(f"✅ Gateway {platform} Switch to webhook mode")
                elif platform == "feishu":
                    from core.gateway.adapters.feishu import FeishuAdapter
                    adapter = FeishuAdapter(config=config_value)
                    gateway_router.register_adapter(adapter)
                    logger.info(f"✅ Gateway feishu Adapter has been hot reloaded")
                elif platform == "dingtalk":
                    from core.gateway.adapters.dingtalk import DingTalkAdapter
                    adapter = DingTalkAdapter(config=config_value)
                    gateway_router.register_adapter(adapter)
                    logger.info(f"✅ Gateway dingtalk Adapter has been hot reloaded")
            except Exception as reload_err:
                logger.warning(f"⚠️ Gateway {platform} Adapter hot reload failed: {reload_err}")
        else:
            try:
                from core.gateway.router import gateway_router
                if platform == "qq":
                    await gateway_router.stop_ws_client()
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")

        await log_operation(
            user_id=str(current_user.get("user_id", current_user.get("id", ""))),
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action=f"update Gateway {platform} Configuration",
            details={"platform": platform, "enabled": req.enabled},
        )

        return ok(message=f"Gateway {platform} Configuration saved")
    except Exception as e:
        logger.error(f"❌ update Gateway {platform} Configuration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gateway/{platform}/test", summary="Test Gateway platform connection")
async def test_gateway_connection(
    platform: str,
    current_user: dict = Depends(get_current_user)
):
    """Test the connection to the IM platform using saved credentials (obtain AccessToken to verify the validity of the credentials)"""
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        doc = await db.system_configs.find_one({"config_key": f"gateway_{platform}"})
        if not doc:
            return fail(message=f"Gateway {platform} Not configured yet, please save the configuration first")

        cfg = doc["config_value"]
        import httpx

        if platform == "qq":
            app_id = cfg.get("app_id", "")
            app_secret = cfg.get("app_secret", "")
            if not app_id or not app_secret:
                return fail(message="AppID Or AppSecret is empty, please complete the configuration first")
            QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(QQ_TOKEN_URL, json={
                    "appId": app_id,
                    "clientSecret": app_secret,
                })
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" in data:
                    expires_in = data.get("expires_in", "unknown")
                    logger.info(f"✅ Gateway {platform} The connection test is successful and the Token is valid. {expires_in}s")
                    return ok(
                        data={"expires_in": expires_in},
                        message=f"Connection successful! AccessToken validity period {expires_in} seconds",
                    )
                else:
                    err_msg = data.get("message", data.get("msg", str(data)))
                    return fail(message=f"Invalid credentials:{err_msg}")
            else:
                try:
                    err_data = resp.json()
                    err_msg = err_data.get("message", err_data.get("msg", resp.text))
                except Exception:
                    err_msg = resp.text
                return fail(message=f"QQ Platform returns {resp.status_code}: {err_msg}")

        elif platform == "feishu":
            app_id = cfg.get("app_id", "")
            app_secret = cfg.get("app_secret", "")
            if not app_id or not app_secret:
                return fail(message="App ID Or the App Secret is empty, please complete the configuration first")
            FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(FEISHU_TOKEN_URL, json={
                    "app_id": app_id,
                    "app_secret": app_secret,
                })
            data = resp.json()
            if data.get("code") == 0 and data.get("tenant_access_token"):
                expire = data.get("expire", 7200)
                logger.info(f"✅ Gateway feishu The connection test is successful and the Token is valid. {expire}s")
                return ok(
                    data={"expires_in": expire},
                    message=f"Feishu connection successful! Tenant Access Token validity period {expire} seconds",
                )
            else:
                err_msg = data.get("msg", str(data))
                return fail(message=f"Feishu voucher is invalid:{err_msg}")

        elif platform == "dingtalk":
            app_key = cfg.get("app_key", "")
            app_secret = cfg.get("app_secret", "")
            if not app_key or not app_secret:
                return fail(message="AppKey Or AppSecret is empty, please complete the configuration first")
            DINGTALK_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(DINGTALK_TOKEN_URL, json={
                    "appKey": app_key,
                    "appSecret": app_secret,
                })
            data = resp.json()
            if data.get("accessToken"):
                expire_in = data.get("expireIn", 7200)
                logger.info(f"✅ Gateway dingtalk The connection test is successful and the Token is valid. {expire_in}s")
                return ok(
                    data={"expires_in": expire_in},
                    message=f"DingTalk connection successful! Access Token validity period {expire_in} seconds",
                )
            else:
                err_msg = data.get("message", data.get("msg", str(data)))
                return fail(message=f"Invalid DingTalk voucher:{err_msg}")

        else:
            return fail(message=f"Testing is not supported yet {platform} Platform connection")

    except httpx.TimeoutException:
        return fail(message="Connection timed out, please check the network environment")
    except Exception as e:
        logger.error(f"❌ Gateway {platform} Connection test failed: {e}")
        return fail(message=f"Test failed:{str(e)}")


# ===== Configure reload endpoint =====

@router.post("/reload", summary="Reload configuration")
async def reload_config(current_user: dict = Depends(get_current_user)):
    """
    Reload configuration and bridge to environment variables

    It is used to take effect immediately after configuration update without restarting the service.
    """
    try:
        from app.core.config_bridge import reload_bridged_config

        success = reload_bridged_config()

        if success:
            await log_operation(
                user_id=str(current_user.get("user_id", "")),
                username=current_user.get("username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="Overload configuration",
                details={"action": "reload_config"},
                ip_address="",
                user_agent=""
            )

            return {
                "success": True,
                "message": "Configuration reload successful",
                "data": {
                    "reloaded_at": now_tz().isoformat()
                }
            }
        else:
            return {
                "success": False,
                "message": "Configuration reload failed, please check the log"
            }
    except Exception as e:
        logger.error(f"Configuration reload failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Configuration reload failed: {str(e)}"
        )


# ===== Solution A: Sensitive field response desensitization & Request cleaning =====
from copy import deepcopy

def _sanitize_llm_configs(items, providers_dict=None):
    """
    Desensitize LLM configuration, return abbreviated API Key

    Logic (consistent with has_valid_api_key):
    1. If there is a valid API Key in the model configuration, return the abbreviated version
    2. If not found in the model configuration, attempts to read from the factory configuration and return an abbreviated version
    3. If it is not found in the manufacturer s configuration, try to read it from the environment variable and return the abbreviated version.
    4. If there are none, return None

    Args:
        items: LLM Configuration list
        providers_dict: Manufacturer configuration dictionary {provider_name: LLMProvider}, Optional
    """
    try:
        from app.utils.api_key_utils import (
            is_valid_api_key,
            truncate_api_key,
            get_env_api_key_for_provider
        )

        result = []
        for item in items:
            try:
                data = item.model_dump()
                provider_name = data.get("provider", "")

                # Handle API Key (check by priority)
                # 1. Check the model configuration for API Key
                model_key = data.get("api_key")
                if is_valid_api_key(model_key):
                    data["api_key"] = truncate_api_key(model_key)
                else:
                    # 2. Check the manufacturer's configuration API Key
                    provider_key = None
                    if providers_dict and provider_name in providers_dict:
                        provider = providers_dict[provider_name]
                        provider_key = provider.api_key

                    if is_valid_api_key(provider_key):
                        data["api_key"] = truncate_api_key(provider_key)
                    else:
                        # 3. Check the environment variables for API Key
                        env_key = get_env_api_key_for_provider(provider_name)
                        if env_key:
                            data["api_key"] = truncate_api_key(env_key)
                        else:
                            data["api_key"] = None

                result.append(LLMConfig(**data))
            except Exception as e:
                # 🔥 Fault tolerance processing: If a configuration fails to be processed (for example, the model directory has been deleted), the configuration will be skipped.
                logger.warning(f"⚠️ Processing LLM configuration failed, skipped: {item.model_dump() if hasattr(item, 'model_dump') else item}, Error: {e}")
                continue

        return result
    except Exception as e:
        logger.error(f"❌ Desensitization LLM configuration failed: {e}")
        return items

def _sanitize_datasource_configs(items):
    """
    Desensitized data source configuration, return abbreviated API Key

    Logic:
    1. If there is a valid API Key in the database, return the abbreviated version
    2. If not in the database, try to read from the environment variable and return the abbreviated version
    3. If there are none, return None
    """
    try:
        from app.utils.api_key_utils import (
            is_valid_api_key,
            truncate_api_key,
            get_env_api_key_for_datasource
        )

        result = []
        for item in items:
            data = item.model_dump()

            # Process API Key
            db_key = data.get("api_key")
            if is_valid_api_key(db_key):
                # There is a valid API Key in the database, return the abbreviated version
                data["api_key"] = truncate_api_key(db_key)
            else:
                # There is no valid API Key in the database, try reading from environment variables
                ds_type = data.get("type")
                if isinstance(ds_type, str):
                    env_key = get_env_api_key_for_datasource(ds_type)
                    if env_key:
                        # There is a valid API Key in the environment variable, and the abbreviated version is returned.
                        data["api_key"] = truncate_api_key(env_key)
                    else:
                        data["api_key"] = None
                else:
                    data["api_key"] = None

            # Handle API Secret (same logic)
            db_secret = data.get("api_secret")
            if is_valid_api_key(db_secret):
                data["api_secret"] = truncate_api_key(db_secret)
            else:
                data["api_secret"] = None

            result.append(DataSourceConfig(**data))

        return result
    except Exception as e:
        print(f"⚠️ Desensitized data source configuration failed: {e}")
        return items

def _sanitize_database_configs(items):
    try:
        return [DatabaseConfig(**{**i.model_dump(), "password": None}) for i in items]
    except Exception:
        return items

def _sanitize_kv(d: Dict[str, Any]) -> Dict[str, Any]:
    """Desensitize potentially sensitive keys in a dictionary (response only)."""
    try:
        if not isinstance(d, dict):
            return d
        sens_patterns = ("key", "secret", "password", "token", "client_secret")
        redacted = {}
        for k, v in d.items():
            if isinstance(k, str) and any(p in k.lower() for p in sens_patterns):
                redacted[k] = None
            else:
                redacted[k] = v
        return redacted
    except Exception:
        return d




class SetDefaultRequest(BaseModel):
    """Set default configuration request"""
    name: str


class FetchProviderModelsRequest(BaseModel):
    """Get manufacturer model list request"""
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Optional model filtering parameters")


@router.get("/system", response_model=SystemConfigResponse)
async def get_system_config(
    current_user: User = Depends(get_current_user)
):
    """Get system configuration"""
    try:
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System configuration does not exist"
            )

        # Obtain manufacturer configuration for desensitization API Key
        providers = await config_service.get_llm_providers()
        providers_dict = {p.name: p for p in providers}

        return SystemConfigResponse(
            config_name=config.config_name,
            config_type=config.config_type,
            llm_configs=_sanitize_llm_configs(config.llm_configs, providers_dict),
            default_llm=config.default_llm,
            data_source_configs=_sanitize_datasource_configs(config.data_source_configs),
            database_configs=_sanitize_database_configs(config.database_configs),
            system_settings=_sanitize_kv(config.system_settings),
            created_at=config.created_at,
            updated_at=config.updated_at,
            version=config.version,
            is_active=config.is_active
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain system configuration: {str(e)}"
        )


# ========== Large model manufacturer management ==========

@router.get("/llm/providers", response_model=List[LLMProviderResponse])
async def get_llm_providers(
    current_user: User = Depends(get_current_user)
):
    """Get all large model manufacturers"""
    try:
        from app.utils.api_key_utils import (
            is_valid_api_key,
            truncate_api_key,
            get_env_api_key_for_provider
        )

        providers = await config_service.get_llm_providers()
        result = []

        for provider in providers:
            # Handle API Key: use the database configuration first, if the database does not exist, check the environment variables
            db_key_valid = is_valid_api_key(provider.api_key)
            if db_key_valid:
                # There is a valid API Key in the database, return the abbreviated version
                api_key_display = truncate_api_key(provider.api_key)
            else:
                # There is no valid API Key in the database, try reading from environment variables
                env_key = get_env_api_key_for_provider(provider.name)
                if env_key:
                    # There is a valid API Key in the environment variable, and the abbreviated version is returned.
                    api_key_display = truncate_api_key(env_key)
                else:
                    api_key_display = None

            # Handle API Secret (same logic)
            db_secret_valid = is_valid_api_key(provider.api_secret)
            if db_secret_valid:
                api_secret_display = truncate_api_key(provider.api_secret)
            else:
                # Note: API Secret is usually not in the environment variable, so only the database is checked here
                api_secret_display = None

            result.append(
                LLMProviderResponse(
                    id=str(provider.id),
                    name=provider.name,
                    display_name=provider.display_name,
                    description=provider.description,
                    website=provider.website,
                    api_doc_url=provider.api_doc_url,
                    logo_url=provider.logo_url,
                    is_active=provider.is_active,
                    supported_features=provider.supported_features,
                    default_base_url=provider.default_base_url,
                    embedding_model=provider.embedding_model,  # 🔥 New: Return embedding_model
                    test_model=provider.test_model,  # 🔥 New: Return test_model
                    # Returns the abbreviated API Key (first 6 digits + "..." + last 6 digits)
                    api_key=api_key_display,
                    api_secret=api_secret_display,
                    extra_config={
                        **provider.extra_config,
                        "has_api_key": bool(api_key_display),
                        "has_api_secret": bool(api_secret_display)
                    },
                    created_at=provider.created_at,
                    updated_at=provider.updated_at
                )
            )

        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain manufacturer list: {str(e)}"
        )


@router.post("/llm/providers", response_model=dict)
async def add_llm_provider(
    request: LLMProviderRequest,
    current_user: User = Depends(get_current_user)
):
    """Add large model manufacturer"""
    _check_jdyun_mode_protected()
    try:
        from app.utils.api_key_utils import should_skip_api_key_update

        provider_data = request.model_dump()

        # 🔥 Modification: Process the addition logic of API Key (consistent with the update logic)
        # 1. If API Key is an empty string, it means the user does not want to set a key → Save empty string
        # 2. If API Key is a placeholder or truncated key (e.g. "sk-99054...") , then delete the field (not set)
        # 3. If API Key is a valid full key, save
        if 'api_key' in provider_data:
            api_key = provider_data.get('api_key', '')
            # Remove the field (not set) if it should be skipped (placeholder or truncated key)
            if should_skip_api_key_update(api_key):
                del provider_data['api_key']
            # If it is an empty string, keep it (indicating that the key is not set)
            # If it is a valid full key, keep it (indicates setting the key)

        # Handle API Secret (same logic)
        if 'api_secret' in provider_data:
            api_secret = provider_data.get('api_secret', '')
            if should_skip_api_key_update(api_secret):
                del provider_data['api_secret']

        provider = LLMProvider(**provider_data)
        provider_id = await config_service.add_llm_provider(provider)

        # Audit log (ignore exceptions)
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="add_llm_provider",
                details={"provider_id": str(provider_id), "name": request.name},
                success=True,
            )
        except Exception as e:
            logger.warning(f"[config] Operation failed: {e}")

        _reload_runtime_bridge(f"add_llm_provider:{request.name}")

        return {
            "success": True,
            "message": "Manufacturer added successfully",
            "data": {"id": str(provider_id)}
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add manufacturer: {str(e)}"
        )


@router.put("/llm/providers/{provider_id}", response_model=dict)
async def update_llm_provider(
    provider_id: str,
    request: LLMProviderRequest,
    current_user: User = Depends(get_current_user)
):
    _check_jdyun_mode_protected()
    """Update large model manufacturers"""
    try:
        from app.utils.api_key_utils import should_skip_api_key_update

        update_data = request.model_dump(exclude_unset=True)

        # 🔥 Modification: Processing API Key update logic
        # 1. If API Key is an empty string, it means the user wants to clear the key → Save empty string
        # 2. If API Key is a placeholder or truncated key (e.g. "sk-99054...") , Then delete the field (not update)
        # 3. Update if API Key is a valid full key
        if 'api_key' in update_data:
            api_key = update_data.get('api_key', '')
            # Remove the field if updates should be skipped (placeholder or truncated key)
            if should_skip_api_key_update(api_key):
                del update_data['api_key']
            # If it is an empty string, keep it (meaning to clear it)
            # If it is a valid full key, keep it (indicates an update)

        if 'api_secret' in update_data:
            api_secret = update_data.get('api_secret', '')
            # The same logical processing API Secret
            if should_skip_api_key_update(api_secret):
                del update_data['api_secret']

        success = await config_service.update_llm_provider(provider_id, update_data)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_llm_provider",
                    details={"provider_id": provider_id, "changed_keys": list(request.model_dump().keys())},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")

            _reload_runtime_bridge(f"update_llm_provider:{provider_id}")

            return {
                "success": True,
                "message": "Manufacturer update successful",
                "data": {}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The manufacturer does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Factory update failed: {str(e)}"
        )


@router.delete("/llm/providers/{provider_id}", response_model=dict)
async def delete_llm_provider(
    provider_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete large model manufacturer"""
    _check_jdyun_mode_protected()
    try:
        success = await config_service.delete_llm_provider(provider_id)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="delete_llm_provider",
                    details={"provider_id": provider_id},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {
                "success": True,
                "message": "Manufacturer deleted successfully",
                "data": {}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The manufacturer does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete manufacturer: {str(e)}"
        )


@router.patch("/llm/providers/{provider_id}/toggle", response_model=dict)
async def toggle_llm_provider(
    provider_id: str,
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Switch large model manufacturer status"""
    try:
        is_active = request.get("is_active", True)
        success = await config_service.toggle_llm_provider(provider_id, is_active)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="toggle_llm_provider",
                    details={"provider_id": provider_id, "is_active": bool(is_active)},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {
                "success": True,
                "message": f"The manufacturer has{'enable' if is_active else 'Disable'}",
                "data": {}
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The manufacturer does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch manufacturer status: {str(e)}"
        )


@router.post("/llm/providers/{provider_id}/fetch-models", response_model=dict)
async def fetch_provider_models(
    provider_id: str,
    request: Optional[FetchProviderModelsRequest] = None,
    current_user: User = Depends(get_current_user)
):
    """Get model list from manufacturer API"""
    try:
        filters = request.model_dump(exclude_none=True) if request else None
        result = await config_service.fetch_provider_models(
            provider_id,
            filters,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to get model list: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model list: {str(e)}"
        )


@router.post("/llm/providers/migrate-env", response_model=dict)
async def migrate_env_to_providers(
    current_user: User = Depends(get_current_user)
):
    """Migrate environment variable configuration to manufacturer management"""
    try:
        result = await config_service.migrate_env_to_providers()
        # Audit log (ignore exceptions)
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="migrate_env_to_providers",
                details={
                    "migrated_count": result.get("migrated_count", 0),
                    "skipped_count": result.get("skipped_count", 0)
                },
                success=bool(result.get("success", False)),
            )
        except Exception as e:
            logger.warning(f"[config] Operation failed: {e}")

        return {
            "success": result["success"],
            "message": result["message"],
            "data": {
                "migrated_count": result.get("migrated_count", 0),
                "skipped_count": result.get("skipped_count", 0)
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Environment variable migration failed: {str(e)}"
        )


@router.post("/llm/providers/init-aggregators", response_model=dict)
async def init_aggregator_providers(
    current_user: User = Depends(get_current_user)
):
    """Initialize aggregation channel manufacturer configuration (302.AI, OpenRouter, etc.)"""
    try:
        result = await config_service.init_aggregator_providers()

        # Audit log (ignore exceptions)
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="init_aggregator_providers",
                details={
                    "added_count": result.get("added", 0),
                    "skipped_count": result.get("skipped", 0)
                },
                success=bool(result.get("success", False)),
            )
        except Exception as e:
            logger.warning(f"[config] Operation failed: {e}")

        return {
            "success": result["success"],
            "message": result["message"],
            "data": {
                "added_count": result.get("added", 0),
                "skipped_count": result.get("skipped", 0)
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize aggregation channel: {str(e)}"
        )


@router.get("/llm/providers/embedding", response_model=List[dict])
async def get_embedding_providers(
    current_user: User = Depends(get_current_user)
):
    """Get a list of all manufacturers and models that support embedding"""
    try:
        result = await config_service.get_embedding_providers()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain Embedding manufacturer list: {str(e)}"
        )


@router.post("/llm/providers/{provider_id}/test", response_model=dict)
async def test_provider_api(
    provider_id: str,
    current_user: User = Depends(get_current_user)
):
    """Test manufacturer API key"""
    try:
        logger.info(f"🧪 API test request received - provider_id: {provider_id}")
        result = await config_service.test_provider_api(provider_id)
        logger.info(f"🧪 API Test results: {result}")
        return result
    except Exception as e:
        logger.error(f"Testing manufacturer API failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Testing manufacturer API failed: {str(e)}"
        )


# ========== Large model configuration management ==========

@router.post("/llm", response_model=dict)
async def add_llm_config(
    request: LLMConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Add or update large model configuration"""
    _check_jdyun_mode_protected()
    try:
        logger.info(f"🔧 Add/Update Large Model Configuration Start")
        logger.info(f"📊 Request data: {request.model_dump()}")
        logger.info(f"🏷️ Manufacturer: {request.provider}, model: {request.model_name}")

        # Create LLM configuration
        llm_config_data = request.model_dump()
        logger.info(f"📋 Original configuration data: {llm_config_data}")

        # 🔥 Solution 1: Do not automatically copy the API Key from the manufacturer configuration to the model configuration
        # Reason:
        # 1. The API Key in the model configuration becomes"Snapshot", Will not update with factory configuration updates
        # 2. Priority: Model Configuration > Factory configuration > environment variables, causing the old value to be used all the time
        # 3. The front end does not provide an API Key input box, and users cannot update the key in the model configuration through the interface. API Key
        #
        # New logic:
        # - The api_key field in the model configuration always remains an empty string or None
        # - When the system is running, it will be automatically obtained from the manufacturer's configuration or environment variables. API Key
        # - After updating the API Key configured by the manufacturer in this way, all models using this manufacturer will take effect immediately.

        # Clear the API Key (regardless of whether it is passed in by the front end)
        llm_config_data['api_key'] = ""
        logger.info(f"🔑 The api_key of the model configuration has been set to empty (will be obtained from the factory configuration or environment variables)")


        # Try to create LLMConfig object
        try:
            llm_config = LLMConfig(**llm_config_data)
            logger.info(f"✅ LLMConfig Object created successfully")
        except Exception as e:
            logger.error(f"❌ LLMConfig Object creation failed: {e}")
            logger.error(f"📋 failed data: {llm_config_data}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Configuration data validation failed: {str(e)}"
            )

        # Save configuration
        success = await config_service.update_llm_config(llm_config)

        if success:
            logger.info(f"✅ Large model configuration updated successfully: {llm_config.provider}/{llm_config.model_name}")

            # Sync pricing configuration to tradingagents
            try:
                from app.core.config_bridge import sync_pricing_config_now
                sync_pricing_config_now()
                logger.info(f"✅ Pricing configuration has been synced to tradingagents")
            except Exception as e:
                logger.warning(f"⚠️  Synchronized pricing configuration failed: {e}")

            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_llm_config",
                    details={"provider": llm_config.provider, "model_name": llm_config.model_name},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Large model configuration updated successfully", "model_name": llm_config.model_name}
        else:
            logger.error(f"❌ Failed to save large model configuration")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Large model configuration update failed"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Add large model configuration exception: {e}")
        import traceback
        logger.error(f"📋 exception stack: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add large model configuration: {str(e)}"
        )


@router.post("/datasource", response_model=dict)
async def add_data_source_config(
    request: DataSourceConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Add data source configuration"""
    _check_jdyun_mode_protected()
    try:
        # Open source version: all users can modify the configuration

        # Get current configuration
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System configuration does not exist"
            )

        # Add new data source configuration
        # 🔥 Modification: support saving API Key (consistent with large model manufacturer management logic)
        from app.utils.api_key_utils import should_skip_api_key_update, is_valid_api_key

        _req = request.model_dump()

        # Process API Key
        if 'api_key' in _req:
            api_key = _req.get('api_key', '')
            # If it is a placeholder or truncated key, clear this field
            if should_skip_api_key_update(api_key):
                _req['api_key'] = ""
            # If it is an empty string, keep it (indicating the use of environment variables)
            elif api_key == '':
                _req['api_key'] = ''
            # If it is a newly entered key, the validity must be verified
            elif not is_valid_api_key(api_key):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="API Key Invalid: length must be at least 5 characters and cannot be a placeholder"
                )
            # Valid full key, reserved

        # Process API Secret
        if 'api_secret' in _req:
            api_secret = _req.get('api_secret', '')
            if should_skip_api_key_update(api_secret):
                _req['api_secret'] = ""
            # If it is an empty string, keep it
            elif api_secret == '':
                _req['api_secret'] = ''
            # If it is a newly entered key, the validity must be verified
            elif not is_valid_api_key(api_secret):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="API Secret Invalid: length must be at least 5 characters and cannot be a placeholder"
                )

        ds_config = DataSourceConfig(**_req)
        config.data_source_configs.append(ds_config)

        success = await config_service.save_system_config(config)
        if success:
            # 🆕 Automatically create data source grouping relationships
            market_categories = _req.get('market_categories', [])
            if market_categories:
                for category_id in market_categories:
                    try:
                        grouping = DataSourceGrouping(
                            data_source_name=ds_config.name,
                            market_category_id=category_id,
                            priority=ds_config.priority,
                            enabled=ds_config.enabled
                        )
                        await config_service.add_datasource_to_category(grouping)
                    except Exception as e:
                        # If the group already exists or other errors occur, it will be recorded but will not affect the main process.
                        logger.warning(f"Automatic creation of data source grouping failed: {str(e)}")

            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="add_data_source_config",
                    details={"name": ds_config.name, "market_categories": market_categories},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Data source configuration added successfully", "name": ds_config.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add data source configuration"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add data source configuration: {str(e)}"
        )


@router.post("/database", response_model=dict)
async def add_database_config(
    request: DatabaseConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Add database configuration"""
    try:
        # Open source version: all users can modify the configuration

        # Get current configuration
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System configuration does not exist"
            )

        # Add new database configuration (Option A: Clean sensitive fields)
        _req = request.model_dump()
        _req['password'] = ""
        db_config = DatabaseConfig(**_req)
        config.database_configs.append(db_config)

        success = await config_service.save_system_config(config)
        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="add_database_config",
                    details={"name": db_config.name},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Database configuration added successfully", "name": db_config.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database configuration failed to add"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add database configuration: {str(e)}"
        )


@router.post("/test", response_model=ConfigTestResponse)
async def test_config(
    request: ConfigTestRequest,
    current_user: User = Depends(get_current_user)
):
    """Test configuration connection"""
    try:
        if request.config_type == "llm":
            llm_config = LLMConfig(**request.config_data)
            result = await config_service.test_llm_config(llm_config)
        elif request.config_type == "datasource":
            ds_config = DataSourceConfig(**request.config_data)
            result = await config_service.test_data_source_config(ds_config)
        elif request.config_type == "database":
            db_config = DatabaseConfig(**request.config_data)
            result = await config_service.test_database_config(db_config)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported configuration type"
            )

        return ConfigTestResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test configuration failed:{ErrorFormatter.format_user_message(str(e))}"
        )


class ProxyTestRequest(BaseModel):
    """Proxy test requests"""
    http_proxy: str = ""
    https_proxy: str = ""


def _normalize_proxy_url(proxy: str) -> str:
    """Normalize the proxy address, ensuring there is a protocol prefix"""
    if not proxy:
        return proxy
    proxy = proxy.strip()
    # If there is no protocol prefix, it is added by default http://
    if not proxy.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
        proxy = f"http://{proxy}"
    return proxy


@router.post("/test-proxy", response_model=dict)
async def test_proxy_connection(
    request: ProxyTestRequest,
    current_user: User = Depends(get_current_user)
):
    """Test proxy connection"""
    import time
    import requests

    start_time = time.time()

    try:
        # Use Google as test target (requires proxy to access)
        test_url = "https://www.google.com"

        proxies = {}
        if request.http_proxy:
            proxies["http"] = _normalize_proxy_url(request.http_proxy)
        if request.https_proxy:
            proxies["https"] = _normalize_proxy_url(request.https_proxy)

        if not proxies:
            return fail(message="Please configure at least one proxy address", data={"response_time": time.time() - start_time})

        logger.info(f"🔍 Test proxy connection: {proxies}")

        response = requests.get(
            test_url,
            proxies=proxies,
            timeout=10,
            allow_redirects=True
        )

        response_time = time.time() - start_time

        if response.status_code == 200:
            logger.info(f"✅ Proxy connection test successful (Time consuming: {response_time:.2f}s)")
            return ok(data={"response_time": response_time}, message="The proxy connection is normal")
        else:
            logger.warning(f"⚠️ Proxy connection returns non-200 status: {response.status_code}")
            return fail(message=f"Agent connection return status code: {response.status_code}", data={"response_time": response_time})

    except requests.exceptions.ProxyError as e:
        logger.error(f"❌ Agent connection error: {e}")
        return fail(message="Agent connection failed: Unable to connect to proxy server", data={"response_time": time.time() - start_time})
    except requests.exceptions.ConnectTimeout:
        logger.error("❌ Agent connection timeout")
        return fail(message="Agent connection timeout", data={"response_time": time.time() - start_time})
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Connection error: {e}")
        return fail(message="Connection failed: Please check if the proxy address is correct", data={"response_time": time.time() - start_time})
    except Exception as e:
        logger.error(f"❌ Agent test failed: {e}")
        return fail(message=f"test failed: {str(e)}", data={"response_time": time.time() - start_time})


@router.post("/database/{db_name}/test", response_model=ConfigTestResponse)
async def test_saved_database_config(
    db_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Test the saved database configuration (get the complete configuration from the database including password)"""
    try:
        logger.info(f"🧪 Test a saved database configuration: {db_name}")

        # Get complete system configuration from database
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System configuration does not exist"
            )

        # Find the specified database configuration
        db_config = None
        for db in config.database_configs:
            if db.name == db_name:
                db_config = db
                break

        if not db_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration '{db_name}' does not exist"
            )

        logger.info(f"✅ Find the database configuration: {db_config.name} ({db_config.type})")
        logger.info(f"📍 connection information: {db_config.host}:{db_config.port}")
        logger.info(f"🔐 Username: {db_config.username or '(None)'}")
        logger.info(f"🔐 Password: {'***' if db_config.password else '(None)'}")

        # Test with full configuration
        result = await config_service.test_database_config(db_config)

        return ConfigTestResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Test database configuration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test database configuration failed: {str(e)}"
        )


@router.get("/llm", response_model=List[LLMConfig])
async def get_llm_configs(
    current_user: User = Depends(get_current_user)
):
    """Get all large model configurations (only models with valid API Keys are returned)"""
    try:
        from app.utils.api_key_utils import has_valid_api_key

        logger.info("Start getting large model configuration...")
        config = await config_service.get_system_config()

        if not config:
            logger.warning("The system configuration is empty and an empty list is returned.")
            return []

        logger.info(f"System configuration exists, large model configuration number: {len(config.llm_configs)}")

        # If you don't have a big model configuration, create some sample configurations
        if not config.llm_configs:
            logger.info("There is no large model configuration, create a sample configuration...")
            # Here you can create sample configurations based on existing manufacturers
            # Temporarily return to the empty list and let the front end display it"No configuration yet"

        # Get all supplier information, used to filter models with disabled suppliers
        providers = await config_service.get_llm_providers()
        active_provider_names = {p.name for p in providers if p.is_active}

        # Build a manufacturer dictionary for checking API Key
        providers_dict = {p.name: p for p in providers}

        # Filter criteria:
        # 1. Model must be enabled (enabled=True) 
        # 2. The provider must enable (is_active=True) 
        # 3. Must have a valid API Key (at least one of model configuration, factory configuration, or environment variable)
        filtered_configs = [
            llm_config for llm_config in config.llm_configs
            if llm_config.enabled
            and llm_config.provider in active_provider_names
            and has_valid_api_key(llm_config, providers_dict)
        ]

        logger.info(f"Number of filtered large model configurations: {len(filtered_configs)} (original: {len(config.llm_configs)})")
        logger.info(f"   - Number of models filtered out: {len(config.llm_configs) - len(filtered_configs)}")

        return _sanitize_llm_configs(filtered_configs, providers_dict)
    except Exception as e:
        logger.error(f"Failed to obtain large model configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain large model configuration: {str(e)}"
        )


@router.delete("/llm/{provider}/{model_name}")
async def delete_llm_config(
    provider: str,
    model_name: str,
    current_user: User = Depends(get_current_user)
):
    """Delete large model configuration"""
    _check_jdyun_mode_protected()
    try:
        logger.info(f"🗑️ Delete large model configuration request - provider: {provider}, model_name: {model_name}")
        success = await config_service.delete_llm_config(provider, model_name)

        if success:
            logger.info(f"✅ Large model configuration deleted successfully - {provider}/{model_name}")

            # Sync pricing configuration to tradingagents
            try:
                from app.core.config_bridge import sync_pricing_config_now
                sync_pricing_config_now()
                logger.info(f"✅ Pricing configuration has been synced to tradingagents")
            except Exception as e:
                logger.warning(f"⚠️  Synchronized pricing configuration failed: {e}")

            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="delete_llm_config",
                    details={"provider": provider, "model_name": model_name},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Large model configuration deleted successfully"}
        else:
            logger.warning(f"⚠️ Large model configuration not found - {provider}/{model_name}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Large model configuration does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Remove large model configuration exception - {provider}/{model_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete large model configuration: {str(e)}"
        )


@router.post("/llm/set-default")
async def set_default_llm(
    request: SetDefaultRequest,
    current_user: User = Depends(get_current_user)
):
    """Set default large model"""
    try:
        success = await config_service.set_default_llm(request.name)
        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="set_default_llm",
                    details={"name": request.name},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "The default large model is set successfully", "default_llm": request.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The specified large model does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Setting default large model failed: {str(e)}"
        )


class BatchImportRequest(BaseModel):
    providers: List[str] = Field(default=[], description="List of manufacturers to import. If empty, all manufacturers with configured API keys will be imported.")


@router.post("/llm/batch-import", response_model=dict)
async def batch_import_llm_configs(
    request: BatchImportRequest = BatchImportRequest(),
    current_user: User = Depends(get_current_user)
):
    """One-click import: Create large model configurations in batches from model catalogs and manufacturer configurations (by manufacturer)"""
    try:
        result = await config_service.batch_import_llm_configs(request.providers)

        # Audit log
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="batch_import_llm_configs",
                details=result,
                success=True,
            )
        except Exception:
            pass

        return result
    except Exception as e:
        logger.error(f"Batch import of large model configuration failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch import failed: {str(e)}"
        )


@router.get("/datasource", response_model=List[DataSourceConfig])
async def get_data_source_configs(
    current_user: User = Depends(get_current_user)
):
    """Get all data source configurations"""
    try:
        config = await config_service.get_system_config()
        if not config:
            return []
        return _sanitize_datasource_configs(config.data_source_configs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain data source configuration: {str(e)}"
        )


@router.put("/datasource/{name}", response_model=dict)
async def update_data_source_config(
    name: str,
    request: DataSourceConfigRequest,
    current_user: User = Depends(get_current_user)
):
    """Update data source configuration"""
    _check_jdyun_mode_protected()
    try:
        # Get current configuration
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System configuration does not exist"
            )

        # Find and update data source configuration
        from app.utils.api_key_utils import should_skip_api_key_update, is_valid_api_key

        def _truncate_api_key(api_key: str, prefix_len: int = 6, suffix_len: int = 6) -> str:
            """Truncate API Key for display"""
            if not api_key or len(api_key) <= prefix_len + suffix_len:
                return api_key
            return f"{api_key[:prefix_len]}...{api_key[-suffix_len:]}"

        for i, ds_config in enumerate(config.data_source_configs):
            if ds_config.name == name:
                # Update configuration
                # 🔥 Modification: Processing the update logic of API Key (consistent with the management logic of large model manufacturers)
                _req = request.model_dump()

                # Process API Key
                if 'api_key' in _req:
                    api_key = _req.get('api_key')
                    logger.info(f"🔍 [API Key Verify] received API Key: {repr(api_key)} (Type: {type(api_key).__name__}, length: {len(api_key) if api_key else 0})")

                    # If it is None or an empty string, retain the original value (not update)
                    if api_key is None or api_key == '':
                        logger.info(f"⏭️  [API Key Verify] None or empty string, retain the original value")
                        _req['api_key'] = ds_config.api_key or ""
                    # 🔥 if contains "..." (truncation mark), need to verify whether it is the unmodified original value
                    elif api_key and "..." in api_key:
                        logger.info(f"🔍 [API Key Verify] The truncation mark is detected and verified to match the original value in the database.")

                        # Do the same truncation for the full API Key in the database
                        if ds_config.api_key:
                            truncated_db_key = _truncate_api_key(ds_config.api_key)
                            logger.info(f"🔍 [API Key Verify] After the original value of the database is truncated: {truncated_db_key}")
                            logger.info(f"🔍 [API Key Verify] value received: {api_key}")

                            # Compare truncated values
                            if api_key == truncated_db_key:
                                # Same, indicating that the user has not modified it and retains the complete value in the database.
                                logger.info(f"✅ [API Key Verify] Truncate value matching, retain the original value of the database")
                                _req['api_key'] = ds_config.api_key
                            else:
                                # Different, indicating that the user has modified it but the modification is incomplete.
                                logger.error(f"❌ [API Key Verify] Truncation value does not match, user may have modified an incomplete key")
                                raise HTTPException(
                                    status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"API Key Format error: Truncation token detected but does not match value in database, please enter complete API Key"
                                )
                        else:
                            # There is no original value in the database, but the front end sends a truncated value, which is unreasonable
                            logger.error(f"❌ [API Key Verify] There is no original value in the database, but a truncated value was received")
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"API Key Format error: please enter the complete API Key"
                            )
                    # If it is a placeholder, it will not be updated (the original value will be retained)
                    elif should_skip_api_key_update(api_key):
                        logger.info(f"⏭️  [API Key Verify] Skip update (placeholder), keep original value")
                        _req['api_key'] = ds_config.api_key or ""
                    # If it is a newly entered key, the validity must be verified
                    elif not is_valid_api_key(api_key):
                        logger.error(f"❌ [API Key Verify] Authentication failed: '{api_key}' (length: {len(api_key)})")
                        logger.error(f"   - length check: {len(api_key)} >= 5? {len(api_key) >= 5}")
                        logger.error(f"   - Placeholder prefix checking: startswith('your_')? {api_key.startswith('your_')}, startswith('your-')? {api_key.startswith('your-')}")
                        logger.error(f"   - Placeholder suffix checking: endswith('_here')? {api_key.endswith('_here')}, endswith('-here')? {api_key.endswith('-here')}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"API Key Invalid: length must be at least 5 characters and cannot be a placeholder (current length: {len(api_key)}) "
                        )
                    else:
                        logger.info(f"✅ [API Key Verify] If the verification is passed, the key will be updated (length: {len(api_key)})")
                    # Valid full key, reserved (indicates update)

                # Process API Secret
                if 'api_secret' in _req:
                    api_secret = _req.get('api_secret')
                    logger.info(f"🔍 [API Secret Verify] received API Secret: {repr(api_secret)} (Type: {type(api_secret).__name__}, length: {len(api_secret) if api_secret else 0})")

                    # If it is None or an empty string, retain the original value (not update)
                    if api_secret is None or api_secret == '':
                        logger.info(f"⏭️  [API Secret Verify] None or empty string, retain the original value")
                        _req['api_secret'] = ds_config.api_secret or ""
                    # 🔥 if contains "..." (truncation mark), need to verify whether it is the unmodified original value
                    elif api_secret and "..." in api_secret:
                        logger.info(f"🔍 [API Secret Verify] The truncation mark is detected and verified to match the original value in the database.")

                        # Do the same truncation for the full API Secret in the database
                        if ds_config.api_secret:
                            truncated_db_secret = _truncate_api_key(ds_config.api_secret)
                            logger.info(f"🔍 [API Secret Verify] After the original value of the database is truncated: {truncated_db_secret}")
                            logger.info(f"🔍 [API Secret Verify] value received: {api_secret}")

                            # Compare truncated values
                            if api_secret == truncated_db_secret:
                                # Same, indicating that the user has not modified it and retains the complete value in the database.
                                logger.info(f"✅ [API Secret Verify] Truncate value matching, retain the original value of the database")
                                _req['api_secret'] = ds_config.api_secret
                            else:
                                # Different, indicating that the user has modified it but the modification is incomplete.
                                logger.error(f"❌ [API Secret Verify] Truncation value does not match, user may have modified an incomplete key")
                                raise HTTPException(
                                    status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"API Secret Format error: Truncation token detected but does not match value in database, please enter complete API Secret"
                                )
                        else:
                            # There is no original value in the database, but the front end sends a truncated value, which is unreasonable
                            logger.error(f"❌ [API Secret Verify] There is no original value in the database, but a truncated value was received")
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"API Secret Format error: please enter the complete API Secret"
                            )
                    # If it is a placeholder, it will not be updated (the original value will be retained)
                    elif should_skip_api_key_update(api_secret):
                        logger.info(f"⏭️  [API Secret Verify] Skip update (placeholder), keep original value")
                        _req['api_secret'] = ds_config.api_secret or ""
                    # If it is a newly entered key, the validity must be verified
                    elif not is_valid_api_key(api_secret):
                        logger.error(f"❌ [API Secret Verify] Authentication failed: '{api_secret}' (length: {len(api_secret)})")
                        logger.error(f"   - length check: {len(api_secret)} >= 5? {len(api_secret) >= 5}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"API Secret Invalid: length must be at least 5 characters and cannot be a placeholder (current length: {len(api_secret)}) "
                        )
                    else:
                        logger.info(f"✅ [API Secret Verify] If the verification is passed, the key will be updated (length: {len(api_secret)})")

                updated_config = DataSourceConfig(**_req)
                config.data_source_configs[i] = updated_config

                success = await config_service.save_system_config(config)
                if success:
                    # 🆕 Synchronize market classification relationships
                    new_categories = set(_req.get('market_categories', []))

                    # Get the current grouping relationship
                    current_groupings = await config_service.get_datasource_groupings()
                    current_categories = set(
                        g.market_category_id
                        for g in current_groupings
                        if g.data_source_name == name
                    )

                    # Categories that need to be added
                    to_add = new_categories - current_categories
                    for category_id in to_add:
                        try:
                            grouping = DataSourceGrouping(
                                data_source_name=name,
                                market_category_id=category_id,
                                priority=updated_config.priority,
                                enabled=updated_config.enabled
                            )
                            await config_service.add_datasource_to_category(grouping)
                        except Exception as e:
                            logger.warning(f"Failed to add data source grouping: {str(e)}")

                    # Category to be deleted
                    to_remove = current_categories - new_categories
                    for category_id in to_remove:
                        try:
                            await config_service.remove_datasource_from_category(name, category_id)
                        except Exception as e:
                            logger.warning(f"Failed to delete data source group: {str(e)}")

                    # Audit log (ignore exceptions)
                    try:
                        await log_operation(
                            user_id=str(getattr(current_user, "id", "")),
                            username=getattr(current_user, "username", "unknown"),
                            action_type=ActionType.CONFIG_MANAGEMENT,
                            action="update_data_source_config",
                            details={"name": name, "market_categories": list(new_categories)},
                            success=True,
                        )
                    except Exception:
                        pass
                    return {"message": "Data source configuration updated successfully"}
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Data source configuration update failed"
                    )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source configuration does not exist"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update data source configuration: {str(e)}"
        )


@router.delete("/datasource/{name}", response_model=dict)
async def delete_data_source_config(
    name: str,
    current_user: User = Depends(get_current_user)
):
    """Delete data source configuration"""
    _check_jdyun_mode_protected()
    try:
        # Get current configuration
        config = await config_service.get_system_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System configuration does not exist"
            )

        # Find and delete data source configurations
        for i, ds_config in enumerate(config.data_source_configs):
            if ds_config.name == name:
                config.data_source_configs.pop(i)

                success = await config_service.save_system_config(config)
                if success:
                    # Audit log (ignore exceptions)
                    try:
                        await log_operation(
                            user_id=str(getattr(current_user, "id", "")),
                            username=getattr(current_user, "username", "unknown"),
                            action_type=ActionType.CONFIG_MANAGEMENT,
                            action="delete_data_source_config",
                            details={"name": name},
                            success=True,
                        )
                    except Exception:
                        pass
                    return {"message": "Data source configuration deleted successfully"}
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Data source configuration deletion failed"
                    )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source configuration does not exist"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete data source configuration: {str(e)}"
        )


@router.get("/datasource-quality", response_model=dict)
async def get_data_source_quality(
    current_user: User = Depends(get_current_user)
):
    """Get data source quality statistics (QMT, etc.)"""
    result = {}
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        adapter = QMTAdapter()
        result["qmt"] = adapter.get_quality_stats()
    except Exception as e:
        result["qmt"] = {"error": str(e)}

    return result


@router.get("/qmt-diagnosis", response_model=dict)
async def qmt_diagnosis(
    current_user: User = Depends(get_current_user)
):
    """QMT Connection diagnosis, returns detailed connection status and FAQ tips"""
    diagnosis = {
        "available": False,
        "connection": "unknown",
        "checks": [],
        "suggestions": [],
    }

    # 1. Check if QMT is enabled
    try:
        from app.core.config import settings as app_settings
        if not app_settings.QMT_UNIFIED_ENABLED:
            diagnosis["checks"].append({"item": "QMT Configuration switches", "status": "disabled", "detail": "QMT_UNIFIED_ENABLED=False"})
            diagnosis["suggestions"].append("Set in .env QMT_UNIFIED_ENABLED=True enable QMT")
            return diagnosis
        diagnosis["checks"].append({"item": "QMT Configuration switches", "status": "ok", "detail": "QMT_UNIFIED_ENABLED=True"})
    except Exception as e:
        diagnosis["checks"].append({"item": "QMT Configuration switches", "status": "error", "detail": str(e)})

    # 2. Check if xtquant is importable
    try:
        from app.services.data_sources.qmt_adapter import _get_xtdata
        xt = _get_xtdata()
        if xt is None:
            diagnosis["checks"].append({"item": "xtquant import", "status": "failed", "detail": "xtquant Module not found"})
            diagnosis["suggestions"].append("Verify that QMT is installed and the QMT_DATA_DIR environment variable points to the correct path")
            diagnosis["suggestions"].append("common paths: D:\\gjzq\\bin.x64 or C:\\gjzq\\bin.x64")
        else:
            diagnosis["checks"].append({"item": "xtquant import", "status": "ok", "detail": "xtdata module loaded"})
    except Exception as e:
        diagnosis["checks"].append({"item": "xtquant import", "status": "error", "detail": str(e)})
        diagnosis["suggestions"].append("xtquant Import failed, please confirm that the QMT client is installed")

    # 3. Check QMT connection
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        adapter = QMTAdapter()
        available = adapter.is_available()
        diagnosis["available"] = available
        if available:
            diagnosis["connection"] = "connected"
            diagnosis["checks"].append({"item": "QMT connect", "status": "ok", "detail": "QMT Connected"})
 
             # 4. Test data acquisition
            try:
                items = adapter.get_kline("000001.SH", period="day", limit=5)
                if items and len(items) > 0:
                    diagnosis["checks"].append({"item": "Data acquisition test", "status": "ok", "detail": f"Shanghai Composite Index Return {len(items)} K line"})
                else:
                    diagnosis["checks"].append({"item": "Data acquisition test", "status": "warning", "detail": "Shanghai Composite Index returns empty data"})
                    diagnosis["suggestions"].append("QMT Connected but the data is empty, you may need to wait for data synchronization")
            except Exception as e:
                diagnosis["checks"].append({"item": "Data acquisition test", "status": "failed", "detail": str(e)[:200]})
        else:
            diagnosis["connection"] = "disconnected"
            diagnosis["checks"].append({"item": "QMT connect", "status": "failed", "detail": "QMT connection not detected"})
            diagnosis["suggestions"].append("Please confirm that the QMT client is started and logged in")
            diagnosis["suggestions"].append("QMT Needs to be run on the local machine and does not support remote connections.")
    except Exception as e:
        diagnosis["checks"].append({"item": "QMT connect", "status": "error", "detail": str(e)[:200]})
        diagnosis["suggestions"].append(f"Connection check exception: {str(e)[:100]}")

    # 5. Check the QMT_DATA_DIR environment variable
    import os
    qmt_dir = os.getenv("QMT_DATA_DIR", "")
    if qmt_dir:
        from pathlib import Path
        if Path(qmt_dir).exists():
            diagnosis["checks"].append({"item": "QMT_DATA_DIR", "status": "ok", "detail": f"path exists: {qmt_dir}"})
        else:
            diagnosis["checks"].append({"item": "QMT_DATA_DIR", "status": "warning", "detail": f"path does not exist: {qmt_dir}"})
            diagnosis["suggestions"].append(f"QMT_DATA_DIR={qmt_dir} The path does not exist, please check the configuration")
    else:
        diagnosis["checks"].append({"item": "QMT_DATA_DIR", "status": "info", "detail": "Not set, use default path search"})

    return diagnosis


# ==================== Market classification management ====================

@router.get("/market-categories", response_model=List[MarketCategory])
async def get_market_categories(
    current_user: User = Depends(get_current_user)
):
    """Get all market categories"""
    try:
        categories = await config_service.get_market_categories()
        return categories
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get market category: {str(e)}"
        )


@router.post("/market-categories", response_model=dict)
async def add_market_category(
    request: MarketCategoryRequest,
    current_user: User = Depends(get_current_user)
):
    """Add market category"""
    try:
        category = MarketCategory(**request.model_dump())
        success = await config_service.add_market_category(category)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="add_market_category",
                    details={"id": str(getattr(category, 'id', ''))},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Market category added successfully", "id": category.id}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Market category ID already exists"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add market category: {str(e)}"
        )


@router.put("/market-categories/{category_id}", response_model=dict)
async def update_market_category(
    category_id: str,
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Update market classification"""
    try:
        success = await config_service.update_market_category(category_id, request)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_market_category",
                    details={"category_id": category_id, "changed_keys": list(request.keys())},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Market classification updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Market classification does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update market category: {str(e)}"
        )


@router.delete("/market-categories/{category_id}", response_model=dict)
async def delete_market_category(
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete market category"""
    try:
        success = await config_service.delete_market_category(category_id)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="delete_market_category",
                    details={"category_id": category_id},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Market category deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category cannot be deleted, there may be data sources using this category"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete market category: {str(e)}"
        )


# ==================== Data source group management ====================

@router.get("/datasource-groupings", response_model=List[DataSourceGrouping])
async def get_datasource_groupings(
    current_user: User = Depends(get_current_user)
):
    """Get the grouping relationships of all data sources"""
    try:
        groupings = await config_service.get_datasource_groupings()
        return groupings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain data source grouping relationship: {str(e)}"
        )


@router.post("/datasource-groupings", response_model=dict)
async def add_datasource_to_category(
    request: DataSourceGroupingRequest,
    current_user: User = Depends(get_current_user)
):
    """Add data source to taxonomy"""
    try:
        grouping = DataSourceGrouping(**request.model_dump())
        success = await config_service.add_datasource_to_category(grouping)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="add_datasource_to_category",
                    details={"data_source_name": request.data_source_name, "category_id": request.category_id},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Data source added to classification successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The data source is already in this category"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add data source to classification: {str(e)}"
        )


@router.delete("/datasource-groupings/{data_source_name}/{category_id}", response_model=dict)
async def remove_datasource_from_category(
    data_source_name: str,
    category_id: str,
    current_user: User = Depends(get_current_user)
):
    """Remove data source from category"""
    try:
        success = await config_service.remove_datasource_from_category(data_source_name, category_id)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="remove_datasource_from_category",
                    details={"data_source_name": data_source_name, "category_id": category_id},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "The data source was successfully removed from the classification"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The data source grouping relationship does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Removing data source from classification failed: {str(e)}"
        )


@router.put("/datasource-groupings/{data_source_name}/{category_id}", response_model=dict)
async def update_datasource_grouping(
    data_source_name: str,
    category_id: str,
    request: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Update data source grouping relationship"""
    try:
        success = await config_service.update_datasource_grouping(data_source_name, category_id, request)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_datasource_grouping",
                    details={"data_source_name": data_source_name, "category_id": category_id, "changed_keys": list(request.keys())},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Data source grouping relationship updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The data source grouping relationship does not exist"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update data source grouping relationship: {str(e)}"
        )


@router.put("/market-categories/{category_id}/datasource-order", response_model=dict)
async def update_category_datasource_order(
    category_id: str,
    request: DataSourceOrderRequest,
    current_user: User = Depends(get_current_user)
):
    """Update the sorting of data sources in categories"""
    try:
        success = await config_service.update_category_datasource_order(category_id, request.data_sources)

        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_category_datasource_order",
                    details={"category_id": category_id, "data_sources": request.data_sources},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Data source sorting updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Data source sort update failed"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update data source sorting: {str(e)}"
        )


@router.get("/settings", response_model=Dict[str, Any])
async def get_system_settings(
    current_user: User = Depends(get_current_user)
):
    """Get system settings"""
    try:
        effective = await config_provider.get_effective_system_settings()
        return _sanitize_kv(effective)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system settings: {str(e)}"
        )


@router.get("/settings/meta", response_model=dict)
async def get_system_settings_meta(
    current_user: User = Depends(get_current_user)
):
    """Get the metadata of system settings (sensitivity, editability, source, whether there is a value).
    Return structure:{success, data: {items: [{key,sensitive,editable,source,has_value}]}, message}
    """
    try:
        meta_map = await config_provider.get_system_settings_meta()
        items = [
            {"key": k, **v} for k, v in meta_map.items()
        ]
        return {"success": True, "data": {"items": items}, "message": ""}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain system settings metadata: {str(e)}"
        )


@router.put("/settings", response_model=dict)
async def update_system_settings(
    settings: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Update system settings"""
    try:
        # Print received settings (for debugging)
        logger.info(f"📝 System settings update request received, including {len(settings)} item")
        if 'quick_analysis_model' in settings:
            logger.info(f"  ✓ quick_analysis_model: {settings['quick_analysis_model']}")
        else:
            logger.warning(f"  ⚠️  Not included quick_analysis_model")
        if 'deep_analysis_model' in settings:
            logger.info(f"  ✓ deep_analysis_model: {settings['deep_analysis_model']}")
        else:
            logger.warning(f"  ⚠️  Not included deep_analysis_model")

        success = await config_service.update_system_settings(settings)
        if success:
            # Audit log (ignore log exceptions and do not affect the main process)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="update_system_settings",
                    details={"changed_keys": list(settings.keys())},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            # invalid cache
            try:
                config_provider.invalidate()
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            # If the update contains runtime keys, the bridge's environment variables are immediately reloaded to take effect.
            try:
                reload_keys = {
                    'http_proxy',
                    'https_proxy',
                    'no_proxy',
                    'default_provider',
                    'quick_analysis_model',
                    'quick_analysis_model_config_id',
                    'deep_analysis_model',
                    'deep_analysis_model_config_id',
                    'deep_reasoning_model',
                    'deep_reasoning_model_config_id',
                    'coding_model',
                    'coding_model_config_id',
                }
                changed_reload_keys = sorted(k for k in settings.keys() if k in reload_keys)
                if changed_reload_keys:
                    _reload_runtime_bridge(f"update_system_settings:{','.join(changed_reload_keys)}")
            except Exception as e:
                logger.warning(f"⚠️  Trigger reload failed (ignored) after updating system settings:{e}")
            return ok(message="System settings updated successfully")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="System settings update failed"
            )
    except HTTPException:
        raise
    except Exception as e:
        # Audit failure records (ignoring log exceptions)
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.CONFIG_MANAGEMENT,
                action="update_system_settings",
                details={"changed_keys": list(settings.keys())},
                success=False,
                error_message=str(e),
            )
        except Exception as e:
            logger.warning(f"[config] Operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update system settings: {str(e)}"
        )


@router.post("/export", response_model=dict)
async def export_config(
    current_user: User = Depends(get_current_user)
):
    """Export configuration"""
    try:
        config_data = await config_service.export_config()
        # Audit log (ignore exceptions)
        try:
            await log_operation(
                user_id=str(getattr(current_user, "id", "")),
                username=getattr(current_user, "username", "unknown"),
                action_type=ActionType.DATA_EXPORT,
                action="export_config",
                details={"size": len(str(config_data))},
                success=True,
            )
        except Exception as e:
            logger.warning(f"[config] Operation failed: {e}")
        return {
            "message": "Configuration export successful",
            "data": config_data,
            "exported_at": now_tz().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export configuration failed: {str(e)}"
        )


@router.post("/import", response_model=dict)
async def import_config(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """Import configuration"""
    try:
        success = await config_service.import_config(config_data)
        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.DATA_IMPORT,
                    action="import_config",
                    details={"keys": list(config_data.keys())[:10]},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Configuration imported successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuration import failed"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import configuration failed: {str(e)}"
        )


@router.post("/migrate-legacy", response_model=dict)
async def migrate_legacy_config(
    current_user: User = Depends(get_current_user)
):
    """Migrate legacy configuration"""
    try:
        success = await config_service.migrate_legacy_config()
        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="migrate_legacy_config",
                    details={},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": "Traditional configuration migration successful"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Legacy configuration migration fails"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration of legacy configuration failed: {str(e)}"
        )


@router.post("/default/llm", response_model=dict)
async def set_default_llm(
    request: SetDefaultRequest,
    current_user: User = Depends(get_current_user)
):
    """Set default large model"""
    try:
        # Open source version: all users can modify the configuration

        success = await config_service.set_default_llm(request.name)
        if success:
            # Audit log (ignore exceptions)
            try:
                await log_operation(
                    user_id=str(getattr(current_user, "id", "")),
                    username=getattr(current_user, "username", "unknown"),
                    action_type=ActionType.CONFIG_MANAGEMENT,
                    action="set_default_llm",
                    details={"name": request.name},
                    success=True,
                )
            except Exception as e:
                logger.warning(f"[config] Operation failed: {e}")
            return {"message": f"The default large model has been set to: {request.name}"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to set the default large model, please check whether the model name is correct"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Setting default large model failed: {str(e)}"
        )


@router.get("/models", response_model=List[Dict[str, Any]])
async def get_available_models(
    current_user: User = Depends(get_current_user)
):
    """Get a list of available models"""
    try:
        models = await config_service.get_available_models()
        return models
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model list: {str(e)}"
        )


# ========== Model catalog management ==========

@router.get("/model-catalog", response_model=List[Dict[str, Any]])
async def get_model_catalog(
    current_user: User = Depends(get_current_user)
):
    """Get all model directories"""
    try:
        catalogs = await config_service.get_model_catalog()
        return [catalog.model_dump(by_alias=False) for catalog in catalogs]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain model directory: {str(e)}"
        )


@router.get("/model-catalog/{provider}", response_model=Dict[str, Any])
async def get_provider_model_catalog(
    provider: str,
    current_user: User = Depends(get_current_user)
):
    """Get the model catalog of the specified manufacturer"""
    try:
        catalog = await config_service.get_provider_models(provider)
        if not catalog:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No manufacturer found {provider} model directory"
            )
        return catalog.model_dump(by_alias=False)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain model directory: {str(e)}"
        )


class ModelCatalogRequest(BaseModel):
    """Model Catalog Request"""
    provider: str
    provider_name: str
    models: List[Dict[str, Any]]


@router.post("/model-catalog", response_model=dict)
async def save_model_catalog(
    request: ModelCatalogRequest,
    current_user: User = Depends(get_current_user)
):
    """Save or update model catalog"""
    try:
        logger.info(f"📝 Received request to save model directory: provider={request.provider}, models Quantity={len(request.models)}")
        logger.info(f"📝 Request data: {request.model_dump()}")

        # Convert to ModelInfo list
        models = [ModelInfo(**m) for m in request.models]
        logger.info(f"✅ Successfully converted {len(models)} models")

        catalog = ModelCatalog(
            provider=request.provider,
            provider_name=request.provider_name,
            models=models
        )
        logger.info(f"✅ ModelCatalog object created successfully")

        success = await config_service.save_model_catalog(catalog)
        logger.info(f"💾 Save results: {success}")

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save model directory"
            )

        # Record operation log
        await log_operation(
            user_id=str(current_user["id"]),
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action="update_model_catalog",
            details={"provider": request.provider, "provider_name": request.provider_name, "models_count": len(request.models)}
        )

        return {"success": True, "message": "Model directory saved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to save model directory: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save model directory: {str(e)}"
        )


@router.delete("/model-catalog/{provider}", response_model=dict)
async def delete_model_catalog(
    provider: str,
    current_user: User = Depends(get_current_user)
):
    """Delete model directory"""
    try:
        success = await config_service.delete_model_catalog(provider)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No manufacturer found {provider} model directory"
            )

        # Record operation log
        await log_operation(
            user_id=str(current_user["id"]),
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action="delete_model_catalog",
            details={"provider": provider}
        )

        return {"success": True, "message": "Model directory deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete model directory: {str(e)}"
        )


@router.post("/model-catalog/init", response_model=dict)
async def init_model_catalog(
    current_user: User = Depends(get_current_user)
):
    """Initialize the default model directory"""
    try:
        success = await config_service.init_default_model_catalog()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize model directory"
            )

        return {"success": True, "message": "Model directory initialization successful"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize model directory: {str(e)}"
        )


@router.get("/model-catalog/export", response_model=dict)
async def export_model_catalog(
    provider: Optional[str] = Query(None, description="Specify the manufacturer. If not passed, all will be exported."),
    current_user: User = Depends(get_current_user)
):
    """Export model directory (for download)"""
    try:
        if provider:
            # Export the model directory of the specified manufacturer
            catalog = await config_service.get_provider_models(provider)
            if not catalog:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No manufacturer found {provider} model directory"
                )
            catalogs_data = [catalog.model_dump(by_alias=False)]
        else:
            # Export all model directories
            catalogs = await config_service.get_model_catalog()
            catalogs_data = [catalog.model_dump(by_alias=False) for catalog in catalogs]

        # Record operation log
        await log_operation(
            user_id=str(current_user["id"]),
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action="export_model_catalog",
            details={"provider": provider or "all", "catalogs_count": len(catalogs_data)}
        )

        return {
            "success": True,
            "message": "Model directory exported successfully",
            "data": {
                "catalogs": catalogs_data,
                "exported_at": now_tz().isoformat(),
                "version": "1.0"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to export model directory: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export model directory: {str(e)}"
        )


@router.get("/model-catalog/template", response_model=dict)
async def get_model_catalog_template(
    current_user: User = Depends(get_current_user)
):
    """Get the preset model directory template (default configuration)"""
    try:
        # Get default model directory data
        default_catalogs = config_service._get_default_model_catalog()

        return {
            "success": True,
            "message": "Obtain the default template successfully",
            "data": {
                "catalogs": default_catalogs,
                "exported_at": now_tz().isoformat(),
                "version": "1.0",
                "description": "This is the system s preset model catalog template, which contains the latest model information and prices."
            }
        }
    except Exception as e:
        logger.error(f"❌ Failed to obtain default template: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain default template: {str(e)}"
        )


class ModelCatalogImportRequest(BaseModel):
    """Model catalog import request"""
    catalogs: List[Dict[str, Any]] = Field(..., description="Model directory list")
    merge_mode: str = Field("update", description="merge mode: update(Update existing), replace(Replace all), append(Add new model)")


@router.post("/model-catalog/import", response_model=dict)
async def import_model_catalog(
    request: ModelCatalogImportRequest,
    current_user: User = Depends(get_current_user)
):
    """Import model directory (from JSON file)"""
    try:
        logger.info(f"📥 Import model catalog request received: Quantity={len(request.catalogs)}, mode={request.merge_mode}")

        success_count = 0
        failed_count = 0
        errors = []

        for catalog_data in request.catalogs:
            try:
                provider = catalog_data.get("provider")
                provider_name = catalog_data.get("provider_name", provider)
                models_data = catalog_data.get("models", [])

                if not provider:
                    errors.append(f"Missing provider field")
                    failed_count += 1
                    continue

                # Convert to ModelInfo list
                models = []
                for model_data in models_data:
                    try:
                        model = ModelInfo(**model_data)
                        models.append(model)
                    except Exception as e:
                        errors.append(f"Manufacturer {provider} model {model_data.get('name', 'unknown')} Format error: {str(e)}")
                        logger.warning(f"⚠️ Model format error: {model_data} - {e}")

                if not models:
                    errors.append(f"Manufacturer {provider} No valid model data")
                    failed_count += 1
                    continue

                # Processed according to merge mode
                if request.merge_mode == "replace":
                    # Replacement mode: save directly
                    catalog = ModelCatalog(
                        provider=provider,
                        provider_name=provider_name,
                        models=models
                    )
                    success = await config_service.save_model_catalog(catalog)
                    if success:
                        success_count += 1
                        logger.info(f"✅ Replace manufacturer {provider} model directory: {len(models)} models")
                    else:
                        failed_count += 1
                        errors.append(f"Manufacturer {provider} Save failed")
                elif request.merge_mode == "append":
                    # Append mode: Get the existing directory and append new models
                    existing_catalog = await config_service.get_provider_models(provider)
                    if existing_catalog:
                        # Merge model lists (avoid duplication)
                        existing_model_names = {m.name for m in existing_catalog.models}
                        new_models = [m for m in models if m.name not in existing_model_names]
                        if new_models:
                            existing_catalog.models.extend(new_models)
                            success = await config_service.save_model_catalog(existing_catalog)
                            if success:
                                success_count += 1
                                logger.info(f"✅ Add manufacturer {provider} model: {len(new_models)} new models")
                            else:
                                failed_count += 1
                                errors.append(f"Manufacturer {provider} Save failed")
                        else:
                            logger.info(f"⏭️ Manufacturer {provider} No new models need to be added")
                            success_count += 1  # Considered successful (nothing needs to be updated)
                    else:
                        # Create if it does not exist
                        catalog = ModelCatalog(
                            provider=provider,
                            provider_name=provider_name,
                            models=models
                        )
                        success = await config_service.save_model_catalog(catalog)
                        if success:
                            success_count += 1
                            logger.info(f"✅ Create a manufacturer {provider} model directory: {len(models)} models")
                        else:
                            failed_count += 1
                            errors.append(f"Manufacturer {provider} Save failed")
                else:
                    # Update mode (default): Update existing models, add new models, and retain models in the original model that are not in the new data (not deleted)
                    existing_catalog = await config_service.get_provider_models(provider)
                    if existing_catalog:
                        # Create a mapping of model names to models (preserving all original models)
                        model_map = {m.name: m for m in existing_catalog.models}
                        # Update or add models (only update/add models in the new data, do not delete existing models that are not in the new data)
                        for new_model in models:
                            model_map[new_model.name] = new_model
                        # Update catalog (contains original models and new models)
                        existing_catalog.models = list(model_map.values())
                        existing_catalog.provider_name = provider_name  # Update display name
                        success = await config_service.save_model_catalog(existing_catalog)
                        if success:
                            # Count the number of updated and newly added models
                            new_model_names = {m.name for m in models}
                            updated_count = len([name for name in model_map.keys() if name in new_model_names])
                            preserved_count = len(existing_catalog.models) - updated_count
                            logger.info(
                                f"✅ Update manufacturer {provider} model directory: "
                                f"total {len(existing_catalog.models)} models "
                                f"(Update/New {updated_count} a, Keep original {preserved_count} a)"
                            )
                        else:
                            failed_count += 1
                            errors.append(f"Manufacturer {provider} Save failed")
                    else:
                        # Create if it does not exist
                        catalog = ModelCatalog(
                            provider=provider,
                            provider_name=provider_name,
                            models=models
                        )
                        success = await config_service.save_model_catalog(catalog)
                        if success:
                            success_count += 1
                            logger.info(f"✅ Create a manufacturer {provider} model directory: {len(models)} models")
                        else:
                            failed_count += 1
                            errors.append(f"Manufacturer {provider} Save failed")

            except Exception as e:
                failed_count += 1
                error_msg = f"Manufacturer {catalog_data.get('provider', 'unknown')} Import failed: {str(e)}"
                errors.append(error_msg)
                logger.error(f"❌ {error_msg}", exc_info=True)

        # Record operation log
        await log_operation(
            user_id=str(current_user["id"]),
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action="import_model_catalog",
            details={
                "merge_mode": request.merge_mode,
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(request.catalogs)
            },
            success=success_count > 0
        )

        return {
            "success": success_count > 0,
            "message": f"Import completed: success {success_count}, failed {failed_count}",
            "data": {
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": len(request.catalogs),
                "errors": errors[:10] if errors else []  # Returns up to 10 errors
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to import model directory: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import model directory: {str(e)}"
        )


# ===== Database configuration management endpoint =====

@router.get("/database", response_model=List[DatabaseConfig])
async def get_database_configs(
    current_user: dict = Depends(get_current_user)
):
    """Get all database configurations"""
    try:
        logger.info("🔄 Get database configuration list...")
        configs = await config_service.get_database_configs()
        logger.info(f"✅ Get {len(configs)} database configuration")
        return configs
    except Exception as e:
        logger.error(f"❌ Failed to obtain database configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain database configuration: {str(e)}"
        )


@router.get("/database/{db_name}", response_model=DatabaseConfig)
async def get_database_config(
    db_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Get the specified database configuration"""
    try:
        logger.info(f"🔄 Get database configuration: {db_name}")
        config = await config_service.get_database_config(db_name)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration '{db_name}' does not exist"
            )

        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to obtain database configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain database configuration: {str(e)}"
        )


@router.post("/database", response_model=dict)
async def add_database_config(
    request: DatabaseConfigRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add database configuration"""
    try:
        logger.info(f"➕ Add database configuration: {request.name}")

        # Convert to DatabaseConfig object
        db_config = DatabaseConfig(**request.model_dump())

        # Add configuration
        success = await config_service.add_database_config(db_config)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add database configuration. Configuration with the same name may already exist."
            )

        # Record operation log
        await log_operation(
            user_id=current_user["id"],
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action=f"Add database configuration: {request.name}",
            details={"name": request.name, "type": request.type, "host": request.host, "port": request.port}
        )

        return {"success": True, "message": "Database configuration added successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to add database configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add database configuration: {str(e)}"
        )


@router.put("/database/{db_name}", response_model=dict)
async def update_database_config(
    db_name: str,
    request: DatabaseConfigRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update database configuration"""
    try:
        logger.info(f"🔄 Update database configuration: {db_name}")

        # Check if the names match
        if db_name != request.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL The name in does not match the name in the request body"
            )

        # Convert to DatabaseConfig object
        db_config = DatabaseConfig(**request.model_dump())

        # Update configuration
        success = await config_service.update_database_config(db_config)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration '{db_name}' does not exist"
            )

        # Record operation log
        await log_operation(
            user_id=current_user["id"],
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action=f"Update database configuration: {db_name}",
            details={"name": request.name, "type": request.type, "host": request.host, "port": request.port}
        )

        return {"success": True, "message": "Database configuration updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update database configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update database configuration: {str(e)}"
        )


@router.delete("/database/{db_name}", response_model=dict)
async def delete_database_config(
    db_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete database configuration"""
    try:
        logger.info(f"🗑️ Delete database configuration: {db_name}")

        # Delete configuration
        success = await config_service.delete_database_config(db_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Database configuration '{db_name}' does not exist"
            )

        # Record operation log
        await log_operation(
            user_id=current_user["id"],
            username=current_user.get("username", "unknown"),
            action_type=ActionType.CONFIG_MANAGEMENT,
            action=f"Delete database configuration: {db_name}",
            details={"name": db_name}
        )

        return {"success": True, "message": "Database configuration deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete database configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete database configuration: {str(e)}"
        )


@router.get("/qdrant/collections")
async def get_qdrant_collections(
    current_user: User = Depends(get_current_user)
):
    """Get the list of all collections in Qdrant (main storage + mem0) , Contains migration status flags (for vector migration selection)"""
    try:
        result = await config_service.get_qdrant_collections()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection list: {str(e)}"
        )


@router.get("/memory/collections", response_model=List[dict])
async def get_mem0_collections(
    current_user: User = Depends(get_current_user)
):
    """[Compatible with old interfaces] Get the list of all mem0 collections in Qdrant"""
    try:
        result = await config_service.get_mem0_collections()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection list: {str(e)}"
        )


@router.post("/qdrant/migrate", response_model=dict)
async def migrate_qdrant_collection(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Migrate vector data of Qdrant collection
    
    Args:
        collection_name: collection Name
        source: "main" (main storage, in-place recoding) or "mem0" (Migrating from the old collection to the current mem0 collection)
        dry_run: Whether to only preview and not execute (default false)
    """
    try:
        collection_name = request.get("collection_name", "")
        source = request.get("source", "main")
        dry_run = request.get("dry_run", False)

        if source == "mem0":
            result = await config_service.migrate_mem0_collection(collection_name, dry_run)
        else:
            result = await config_service.migrate_qdrant_collection(collection_name, dry_run)

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector migration failed: {str(e)}"
        )


@router.post("/memory/migrate", response_model=dict)
async def migrate_mem0_collection(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """[Compatible with old interfaces] Migrate the vector data of the old mem0 collection to the current collection"""
    try:
        source = request.get("source_collection", "")
        dry_run = request.get("dry_run", False)
        result = await config_service.migrate_mem0_collection(source, dry_run)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector migration failed: {str(e)}"
        )


@router.post("/qdrant/delete-collection", response_model=dict)
async def delete_qdrant_collection(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Delete Qdrant collection (only empty collections are allowed to be deleted or forced deletion after confirmation)"""
    collection_name = request.get("collection_name", "")
    source = request.get("source", "main")
    force = request.get("force", False)

    if not collection_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="collection Name cannot be empty")

    try:
        result = await config_service.delete_qdrant_collection(collection_name, source, force)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete collection: {str(e)}"
        )
