"""
Alpha Vantage API Public module

Provides common request functionality for the Alpha Vantage API, including:
- API Request encapsulation
- Error handling and retrying
- Rate limiting handling
- Response parsing

Refer to the original TradingAgents implementation
"""

import os
import time
import json
import requests
from typing import Dict, Any, Optional
from datetime import datetime

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


class AlphaVantageRateLimitError(Exception):
    """Alpha Vantage rate limit error"""
    pass


class AlphaVantageAPIError(Exception):
    """Alpha Vantage API Error"""
    pass


def _get_api_key_from_database() -> Optional[str]:
    """
    Read from database Alpha Vantage API Key

    Priority: Database Configuration > environment variables
    In this way, after users modify the configuration in the web background, it can take effect immediately.

    Returns:
        Optional[str]: API Key, If not found return None
    """
    try:
        logger.debug("🔍 [DB Query] Start reading from database Alpha Vantage API Key...")
        from app.core.database import get_mongo_db_sync
        db = get_mongo_db_sync()
        config_collection = db.system_configs

        # Get the latest activation configuration
        logger.debug("🔍 [DB Query] Query is_active=True configuration...")
        config_data = config_collection.find_one(
            {"is_active": True},
            sort=[("version", -1)]
        )

        if config_data:
            logger.debug(f"✅ [DB Query] Find activation configuration, version: {config_data.get('version')}")
            if config_data.get('data_source_configs'):
                logger.debug(f"✅ [DB查询] 配置中有 {len(config_data['data_source_configs'])} 个数据源")
                for ds_config in config_data['data_source_configs']:
                    ds_type = ds_config.get('type')
                    logger.debug(f"🔍 [DB Query] Check data source: {ds_type}")
                    if ds_type == 'alpha_vantage':
                        api_key = ds_config.get('api_key')
                        logger.debug(f"✅ [DB Query] Find Alpha Vantage configuration, api_key length: {len(api_key) if api_key else 0}")
                        if api_key and not api_key.startswith("your_"):
                            logger.debug(f"✅ [DB Query] API Key valid (length: {len(api_key)})")
                            return api_key
                        else:
                            logger.debug(f"⚠️ [DB Query] API Key Invalid or a placeholder")
            else:
                logger.debug("⚠️ [DB Query] Not in configuration data_source_configs")
        else:
            logger.debug("⚠️ [DB Query] Activated configuration not found")

        logger.debug("⚠️ [DB Query] No valid one found in database Alpha Vantage API Key")
    except Exception as e:
        logger.debug(f"❌ [DB Query] Failed to read API Key from database: {e}")

    return None


def get_api_key() -> str:
    """
    get Alpha Vantage API Key

    Priority:
    1. Database configuration (system_configs collection)
    2. environment variables ALPHA_VANTAGE_API_KEY
    3. Configuration file

    Returns:
        str: API Key

    Raises:
        ValueError: if not configured API Key
    """
    # 1. Get from database (highest priority)
    logger.debug("🔍 [steps 1] Start reading from database Alpha Vantage API Key...")
    db_api_key = _get_api_key_from_database()
    if db_api_key:
        logger.debug(f"✅ [steps 1] found in database API Key (length: {len(db_api_key)})")
        return db_api_key
    else:
        logger.debug("⚠️ [steps 1] Not found in database API Key")

    # 2. Get from environment variables
    logger.debug("🔍 [steps 2] Read from .env API Key...")
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if api_key:
        logger.debug(f"✅ [steps 2] .env found in API Key (length: {len(api_key)})")
        return api_key
    else:
        logger.debug("⚠️ [steps 2] .env Not found in API Key")

    # 3. Get from configuration file
    logger.debug("🔍 [steps 3] Read the configuration file API Key...")
    try:
        from tradingagents.config.config_manager import ConfigManager
        config_manager = ConfigManager()
        api_key = config_manager.get("ALPHA_VANTAGE_API_KEY")
        if api_key:
            logger.debug(f"✅ [steps 3] Found in configuration file API Key (length: {len(api_key)})")
            return api_key
    except Exception as e:
        logger.debug(f"⚠️ [steps 3] Unable to get from configuration file Alpha Vantage API Key: {e}")

    # all ways fail
    raise ValueError(
        "❌ Alpha Vantage API Key Not configured!\n"
        "Please configure in any of the following ways:\n"
        "1. Web Backend configuration (recommended): http://localhost:3000/api/config/datasource\n"
        "2. Set environment variables: ALPHA_VANTAGE_API_KEY\n"
        "3. Configure in configuration file\n"
        "get API Key: https://www.alphavantage.co/support/#api-key"
    )

    return api_key


def format_datetime_for_api(date_str: str) -> str:
    """
    Format date and time to the format required by Alpha Vantage API
    
    Args:
        date_str: Date string, format YYYY-MM-DD
        
    Returns:
        Formatted date and time string, format YYYYMMDDTHHMM
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y%m%dT0000")
    except Exception as e:
        logger.warning(f"⚠️ 日期格式化失败 {date_str}: {e}，使用原始值")
        return date_str


def _make_api_request(
    function: str,
    params: Dict[str, Any],
    max_retries: int = 3,
    retry_delay: int = 2
) -> Dict[str, Any] | str:
    """
    Make an Alpha Vantage API request
    
    Args:
        function: API Function name (such as NEWS_SENTIMENT, OVERVIEW etc.)
        params: Request parameter dictionary
        max_retries: Maximum number of retries
        retry_delay: Retry delay (seconds)
        
    Returns:
        API Response JSON data or error message string
        
    Raises:
        AlphaVantageRateLimitError: rate limit error
        AlphaVantageAPIError: API Error
    """
    api_key = get_api_key()
    base_url = "https://www.alphavantage.co/query"
    
    # Build request parameters
    request_params = {
        "function": function,
        "apikey": api_key,
        **params
    }
    
    logger.debug(f"📡 [Alpha Vantage] Request {function}: {params}")
    
    for attempt in range(max_retries):
        try:
            # Make a request
            response = requests.get(base_url, params=request_params, timeout=30)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            # Check error messages
            if "Error Message" in data:
                error_msg = data["Error Message"]
                logger.error(f"❌ [Alpha Vantage] API Error: {error_msg}")
                raise AlphaVantageAPIError(f"Alpha Vantage API Error: {error_msg}")
            
            # Check rate limits
            if "Note" in data and "API call frequency" in data["Note"]:
                logger.warning(f"⚠️ [Alpha Vantage] rate limit: {data['Note']}")
                
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.info(f"⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise AlphaVantageRateLimitError(
                        "Alpha Vantage API rate limit exceeded. "
                        "Please wait a moment and try again, or upgrade your API plan."
                    )
            
            # Check information fields (may contain restriction hints)
            if "Information" in data:
                info_msg = data["Information"]
                logger.warning(f"⚠️ [Alpha Vantage] information: {info_msg}")
                
                # If it is a rate limit message
                if "premium" in info_msg.lower() or "limit" in info_msg.lower():
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.info(f"⏳ 等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise AlphaVantageRateLimitError(
                            f"Alpha Vantage API limit: {info_msg}"
                        )
            
            # Data obtained successfully
            logger.debug(f"✅ [Alpha Vantage] Request successful: {function}")
            return data
            
        except requests.exceptions.Timeout:
            logger.warning(f"⚠️ [Alpha Vantage] Request timeout (try {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                raise AlphaVantageAPIError("Alpha Vantage API request timeout")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ [Alpha Vantage] Request failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                raise AlphaVantageAPIError(f"Alpha Vantage API request failed: {e}")
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ [Alpha Vantage] JSON Parsing failed: {e}")
            raise AlphaVantageAPIError(f"Failed to parse Alpha Vantage API response: {e}")
    
    # All retries failed
    raise AlphaVantageAPIError(f"Failed to get data from Alpha Vantage after {max_retries} attempts")


def format_response_as_string(data: Dict[str, Any], title: str = "Alpha Vantage Data") -> str:
    """
    Format API response as string
    
    Args:
        data: API response data
        title: Data header
        
    Returns:
        Formatted string
    """
    try:
        # Add header information
        header = f"# {title}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # Convert to JSON string (formatted)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        return header + json_str
        
    except Exception as e:
        logger.error(f"❌ 格式化响应失败: {e}")
        return str(data)


def check_api_key_valid() -> bool:
    """
    Check if Alpha Vantage API Key is valid
    
    Returns:
        True If the API Key is valid, otherwise False
    """
    try:
        # Test using simple API calls
        data = _make_api_request("GLOBAL_QUOTE", {"symbol": "IBM"})
        
        # Check for errors
        if isinstance(data, dict) and "Global Quote" in data:
            logger.info("✅ Alpha Vantage API Key valid")
            return True
        else:
            logger.warning("⚠️ Alpha Vantage API Key May not be valid")
            return False
            
    except Exception as e:
        logger.error(f"❌ Alpha Vantage API Key Authentication failed: {e}")
        return False

