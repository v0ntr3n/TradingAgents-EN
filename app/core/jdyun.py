"""
JD Cloud Cooperation Edition Configuration

Pass JDYUN_MODE=true The environment variable enables the JD Cloud cooperative version mode.
All LLM and data source configurations are read from environment variables injected by JD Cloud Platform:
- OPENAI_API_BASE: JD Cloud Model Service Address
- OPENAI_API_KEY: JD Cloud API Key
- OPENAI_MODEL: Default dialogue model
- EMBEDDING_MODEL: Embedding model
- TUSHARE_TOKEN: Tushare data source Token
"""

import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# List of dialogue models preset by JD Cloud (all can be used as quick_model or deep_model)
# 🔥 Supports overwriting through the OPENAI_MODEL environment variable (comma-separated multiple models, the first one is the default model)
JDYUN_DEFAULT_CHAT_MODELS = [
    "GLM-5",
    "GLM-5.1",
    "GLM-5.2",
    "DeepSeek-V4-Flash",
]

# Default Embedding model
JDYUN_DEFAULT_EMBEDDING_MODEL = "Qwen3-Embedding-8B"

# Qwen3-Embedding-8B Output dimensions
# 🔥 JD Cloud local model only supports [64, 128, 256, 512, 768, 1024, 1536, 2048] Dimensions
# To ensure compatibility, 1024-dimensional
JDYUN_EMBEDDING_DIMS = 1024

# JD Cloud Provider Name
JDYUN_PROVIDER_NAME = "jdyun"


def is_jdyun_mode() -> bool:
    """Check whether JD Cloud cooperation version mode is enabled"""
    return os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes")


def get_jdyun_api_base() -> str:
    """Get JD Cloud Model Service Address"""
    return os.getenv("OPENAI_API_BASE", "").strip()


def get_jdyun_api_key() -> str:
    """Get JD Cloud API Key"""
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_jdyun_chat_models() -> list:
    """Get the list of JD Cloud dialogue models

    Parsed from the OPENAI_MODEL environment variable (comma-separated multiple models, the first one is the default model),
    Fallback to default list if not set.
    """
    raw = os.getenv("OPENAI_MODEL", "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if models:
            return models
    return list(JDYUN_DEFAULT_CHAT_MODELS)


def get_jdyun_default_model() -> str:
    """Get the default dialogue model (the first in the OPENAI_MODEL list)"""
    models = get_jdyun_chat_models()
    return models[0] if models else JDYUN_DEFAULT_CHAT_MODELS[0]


def get_jdyun_embedding_model() -> str:
    """Get Embedding model"""
    model = os.getenv("EMBEDDING_MODEL", "").strip()
    return model if model else JDYUN_DEFAULT_EMBEDDING_MODEL


def get_jdyun_embedding_api_base() -> str:
    """Get the Embedding service address (leave it blank to use the conversation model service address)"""
    base = os.getenv("EMBEDDING_API_BASE", "").strip()
    return base if base else get_jdyun_api_base()


def get_jdyun_embedding_api_key() -> str:
    """Get the Embedding API Key (leave it blank to use the conversation model API Key)"""
    key = os.getenv("EMBEDDING_API_KEY", "").strip()
    return key if key else get_jdyun_api_key()


def get_jdyun_tushare_token() -> str:
    """get Tushare Token"""
    return os.getenv("TUSHARE_TOKEN", "").strip()


def is_jdyun_model(model_name: str) -> bool:
    """Determine whether the model belongs to JD Cloud preset model"""
    return (model_name or "").strip() in get_jdyun_chat_models()


def get_jdyun_status() -> dict:
    """Get JD Cloud configuration status (excluding sensitive information)"""
    basic_auth_users = get_jdyun_basic_auth_users()
    return {
        "jdyun_mode": is_jdyun_mode(),
        "api_base": get_jdyun_api_base(),
        "api_key_configured": bool(get_jdyun_api_key()),
        "current_model": get_jdyun_default_model(),
        "available_models": get_jdyun_chat_models(),
        "embedding_model": get_jdyun_embedding_model(),
        "embedding_dims": JDYUN_EMBEDDING_DIMS,
        "tushare_token_configured": bool(get_jdyun_tushare_token()),
        "akshare_available": True,  # AKShare is an open source free data source that is always available
        # Basic Auth Whitelist status (returns count only, no password)
        "basic_auth_enabled": bool(basic_auth_users),
        "basic_auth_users_count": len(basic_auth_users),
    }


# ============================================================================
# LLM Speed limit configuration (to cope with JD Cloud API speed limit)
# ============================================================================

def get_jdyun_llm_max_retries() -> int:
    """Get the maximum number of retries for LLM calls (JD Cloud mode defaults to 8, coping with 429 speed limit)"""
    return int(os.getenv("JDYUN_LLM_MAX_RETRIES", "8"))


def get_jdyun_llm_max_rpm() -> int:
    """Get the maximum number of LLM requests per minute (for rate limiter configuration, default 30)"""
    return int(os.getenv("JDYUN_LLM_MAX_RPM", "30"))


def get_jdyun_batch_max_concurrent() -> int:
    """Get the maximum number of concurrent batch analyzes (JD Cloud mode defaults to 1 to avoid LLM speed limit)"""
    return int(os.getenv("JDYUN_BATCH_MAX_CONCURRENT", "1"))


def get_jdyun_worker_max_concurrent() -> int:
    """Get the maximum number of concurrent tasks of the Worker (default 1 in JD Cloud mode to avoid LLM speed limit)"""
    return int(os.getenv("JDYUN_WORKER_MAX_CONCURRENT", "1"))


def get_jdyun_stock_interval_seconds() -> int:
    """Get the number of seconds between scheduled stock analysis (JD Cloud mode defaults to 10 seconds)"""
    return int(os.getenv("JDYUN_STOCK_INTERVAL_SECONDS", "10"))


def get_llm_max_retries(default: int = 2) -> int:
    """
    Get the maximum number of LLM retries (compatible with JD Cloud and non-JD Cloud modes)

    Args:
        default: The default number of retries in non-JD Cloud mode (default 2)

    Returns:
        JD Cloud Mode Returns get_jdyun_llm_max_retries(), Otherwise return default
    """
    if is_jdyun_mode():
        return get_jdyun_llm_max_retries()
    return default


# ============================================================================
# Basic Auth Whitelist configuration (JD Cloud gateway proxy scenario)
# ============================================================================
# Semantic description:
#   - Basic Auth The username is the unique identifier of the JD Cloud user (such as jcloud-ugidvcp)
#   - Basic Auth The password field is the "access token" generated by JD Cloud Platform
#   - Access tokens are completely decoupled from user login passwords
#
# Two configuration modes:
#   1. Strict mode (token is fixed): JDYUN_BASIC_AUTH_USERS="jcloud-ugidvcp:8437F13D..."
#      → username + token must match
#   2. Wildcard pattern (token variable):   JDYUN_BASIC_AUTH_USERS="jcloud-ugidvcp:*"
#      → Only the username is verified, and the token can be changed arbitrarily (applicable to scenarios where JD Cloud dynamically issues tokens)
#
# Wildcard pattern security:
#   - in"One user, one container"Under the architecture, the container port is only exposed to JD Cloud Gateway and is not directly exposed to the outside world.
#   - The JD Cloud gateway side has authenticated the user, and all requests arriving at the container are trusted.
#   - The container only needs to identify"which user"That's it, no secondary verification is required token
# ============================================================================

# Wildcard, indicating that token is not verified (only username is verified)
JDYUN_TOKEN_WILDCARD = "*"


def get_jdyun_basic_auth_users() -> Dict[str, str]:
    """
    Parsing JD Cloud Basic Auth whitelist (username → access token)

    Environment variable format: JDYUN_BASIC_AUTH_USERS=user1:token1,user2:token2
    - Multiple accounts are separated by commas (usually there is only one in a one-user-one-container scenario)
    - Username and access token separated by colon
    - Colons in tokens are split by the first colon (to avoid ambiguity)
    - The token is * indicates wildcard mode (only username is verified, token is not verified)

    Returns:
        {"user1": "token1", "user2": "*"} user-token dictionary of the form

    security:
    - The value here is the access token generated by JD Cloud Platform, not the user login password.
    - The token is stored in env in clear text, the same as OPENAI_API_KEY
    - It is recommended to use it only in the environment injected by JD Cloud. Do not write .env.jdyun and submit it to Git
    - JD Cloud Gateway is responsible for https encrypted transmission, and the plain text is only visible within the container.
    """
    raw = os.getenv("JDYUN_BASIC_AUTH_USERS", "").strip()
    if not raw:
        return {}
    result: Dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            logger.warning("⚠️ [JD Cloud Basic Auth] Skip malformed account configuration items: %s", entry)
            continue
        user, token = entry.split(":", 1)
        user = user.strip()
        token = token.strip()
        if user and token:
            result[user] = token
        else:
            logger.warning("⚠️ [JD Cloud Basic Auth] Skip accounts with empty usernames or tokens: %s", entry)
    if result:
        # Count the number of wildcard patterns
        wildcard_count = sum(1 for v in result.values() if v == JDYUN_TOKEN_WILDCARD)
        if wildcard_count:
            logger.info(
                "🔐 [JD Cloud Basic Auth] %d whitelist accounts have been loaded (%d of them are in wildcard mode, only verifying user names)",
                len(result), wildcard_count,
            )
        else:
            logger.info("🔐 [JD Cloud Basic Auth] Loaded %d whitelisted accounts (strict mode)", len(result))
    return result


def verify_jdyun_basic_auth(username: str, token: str) -> bool:
    """
    Verify JD Cloud Basic Auth credentials (username + access token)

    Args:
        username: JD Cloud user unique identifier (such as jcloud-ugidvcp)
        token: The access token (not the login password) generated by the JD Cloud platform for the user

    Returns:
        Returns True if the credentials are valid, otherwise False

    Two modes:
        - strict mode: When the token in the whitelist is a specific value,username + token must match
        - wildcard pattern: The tokens in the whitelist are * When, only username is verified (token can be changed arbitrarily)

    security:
        - Strict mode uses hmac.compare_digest for constant time comparison (to avoid timing attacks)
        - If the username is not in the whitelist, False is returned directly without token comparison.
        - The wildcard mode is suitable for scenarios where JD Cloud Gateway has been certified, and the container is not directly exposed to the outside world.
    """
    import hmac

    white_list = get_jdyun_basic_auth_users()
    expected_token = white_list.get(username, "")
    if not expected_token:
        # username Not in the whitelist
        return False
    if expected_token == JDYUN_TOKEN_WILDCARD:
        # Wildcard mode: only verify username, not verify token
        # Suitable for scenarios such as dynamic token issuance and regular rotation of tokens by JD Cloud
        return True
    # Strict mode:username + token All verified
    return hmac.compare_digest(
        token.encode("utf-8"),
        expected_token.encode("utf-8"),
    )


# ============================================================================
# JD Cloud Gateway IP Whitelist (Second Line of Defense)
# ============================================================================
# Under the hierarchical verification strategy, old users are exempted from token verification, and there is a risk of the username being forged after being leaked.
# IP The whitelist ensures that the request must come from the JD Cloud gateway. Even if the username is leaked, external attackers cannot forge it.
#
# Configuration method:
#   JDYUN_GATEWAY_IPS=10.0.0.1,10.0.0.2,172.16.0.0/12
#   - Supports single IP and CIDR format, comma separated
#   - Leave blank to disable IP verification (only rely on network isolation)
# ============================================================================

def get_jdyun_gateway_ips() -> list:
    """
    Parse the JD Cloud gateway IP whitelist.

    environment variables: JDYUN_GATEWAY_IPS=10.0.0.1,172.16.0.0/12
    - Supports single IP (10.0.0.1) and CIDR (172.16.0.0/12)
    - Comma separated multiple

    Returns:
        IP/CIDR String list, returns empty list if not configured
    """
    raw = os.getenv("JDYUN_GATEWAY_IPS", "").strip()
    if not raw:
        return []
    return [ip.strip() for ip in raw.split(",") if ip.strip()]


def is_from_jdyun_gateway(client_ip: str) -> bool:
    """
    Check whether the request comes from JD Cloud Gateway (IP whitelist verification).

    Args:
        client_ip: Client IP address (obtained from request.client.host)

    Returns:
        Returns True if it is in the whitelist, returns True if it is not in the whitelist or is not configured (no interception when not configured)

    security:
        - No verification when JDYUN_GATEWAY_IPS is not configured (backward compatibility)
        - After configuration, requests from non-whitelisted IPs are directly rejected.
        - Supports CIDR format (such as 172.16.0.0/12)
    """
    import ipaddress

    gateway_ips = get_jdyun_gateway_ips()
    if not gateway_ips:
        # IP whitelist not configured → No interception (backwards compatible)
        return True

    if not client_ip:
        return False

    try:
        client_addr = ipaddress.ip_address(client_ip)
        for rule in gateway_ips:
            try:
                if "/" in rule:
                    # CIDR Format
                    network = ipaddress.ip_network(rule, strict=False)
                    if client_addr in network:
                        return True
                else:
                    # single IP
                    if client_addr == ipaddress.ip_address(rule):
                        return True
            except ValueError:
                logger.warning(f"⚠️ [JD Cloud IP Whitelist] Invalid IP/CIDR rule: {rule}")
                continue
        return False
    except ValueError:
        logger.warning(f"⚠️ [JD Cloud IP Whitelist] Invalid client IP: {client_ip}")
        return False
