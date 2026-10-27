"""
API Key Processing utility functions

Provides unified API Key verification, abbreviation, environment variable reading and other functions
"""

import os
from typing import Optional


def is_valid_api_key(api_key: Optional[str]) -> bool:
    """
    Determine whether the API Key is valid
    
    A valid API Key must satisfy:
    1. cannot be empty
    2. The length must be >= 5
    3. Cannot be a placeholder (prefix:your_, your-) 
    4. Cannot be a placeholder (suffix:_here, -here) 
    5. Cannot be a truncated key (containing '...') 
    
    Args:
        api_key: To be verified API Key
        
    Returns:
        bool: Is it valid?
    """
    if not api_key:
        return False
    
    api_key = api_key.strip()
    
    # 1. cannot be empty
    if not api_key:
        return False
    
    # 2. The length must be >= 5
    if len(api_key) < 5:
        return False
    
    # 3. Cannot be a placeholder (prefix)
    if api_key.startswith('your_') or api_key.startswith('your-'):
        return False
    
    # 4. Cannot be a placeholder (suffix)
    if api_key.endswith('_here') or api_key.endswith('-here'):
        return False
    
    # 5. Cannot be a truncated key (containing '...') 
    if '...' in api_key:
        return False
    
    return True


def truncate_api_key(api_key: Optional[str]) -> Optional[str]:
    """
    Abbreviated API Key, showing the first 6 digits and the last 6 digits
    
    Example:
        Input:'d1el869r01qghj41hahgd1el869r01qghj41hai0'
        Output:'d1el86...j41hai0'
    
    Args:
        api_key: To be abbreviated API Key
        
    Returns:
        str: Abbreviated API Key, if input is empty or length <= 12 then return the original value
    """
    if not api_key or len(api_key) <= 12:
        return api_key
    
    return f"{api_key[:6]}...{api_key[-6:]}"


def get_env_api_key_for_provider(provider_name: str) -> Optional[str]:
    """
    Obtain the large model manufacturer s information from environment variables API Key
    
    Environment variable name format:{PROVIDER_NAME}_API_KEY
    
    Args:
        provider_name: Manufacturer name (such as 'deepseek', 'dashscope') 
        
    Returns:
        str: API Key in environment variables, returned if it does not exist or is invalid None
    """
    env_key_name = f"{provider_name.upper()}_API_KEY"
    env_key = os.getenv(env_key_name)
    
    if env_key and is_valid_api_key(env_key):
        return env_key
    
    return None


def get_env_api_key_for_datasource(ds_type: str) -> Optional[str]:
    """
    Get the data source from environment variables API Key
    
    Mapping of data source types to environment variable names:
    - tushare → TUSHARE_TOKEN
    - finnhub → FINNHUB_API_KEY
    - polygon → POLYGON_API_KEY
    - iex → IEX_API_KEY
    - quandl → QUANDL_API_KEY
    - alphavantage → ALPHAVANTAGE_API_KEY
    
    Args:
        ds_type: Data source type (e.g. 'tushare', 'finnhub') 
        
    Returns:
        str: API Key in environment variables, returned if it does not exist or is invalid None
    """
    # Mapping of data source types to environment variable names
    env_key_map = {
        "tushare": "TUSHARE_TOKEN",
        "qmt": "QMT_TOKEN",
        "finnhub": "FINNHUB_API_KEY",
        "polygon": "POLYGON_API_KEY",
        "iex": "IEX_API_KEY",
        "quandl": "QUANDL_API_KEY",
        "alphavantage": "ALPHAVANTAGE_API_KEY",
    }
    
    env_key_name = env_key_map.get(ds_type.lower())
    if not env_key_name:
        return None
    
    env_key = os.getenv(env_key_name)
    
    if env_key and is_valid_api_key(env_key):
        return env_key
    
    return None


def should_skip_api_key_update(api_key: Optional[str]) -> bool:
    """
    Determine whether API Key update should be skipped

    Updates should be skipped (original values retained) in the following cases:
    1. API Key is the truncated key (containing '...') 
    2. API Key is a placeholder (your_*, your-*) 

    Args:
        api_key: To be checked API Key

    Returns:
        bool: Should updates be skipped?
    """
    if not api_key:
        return False

    api_key = api_key.strip()

    # 1. Truncated key (contains '...') 
    if '...' in api_key:
        return True

    # 2. placeholder
    if api_key.startswith('your_') or api_key.startswith('your-'):
        return True

    return False


def has_valid_api_key(llm_config, providers_dict: Optional[dict] = None) -> bool:
    """
    Determine whether the LLM configuration has a valid API Key

    Checking sequence (consistent with /api/config/llm/providers interface logic):
    1. Check whether it is a local model (ollama, localai), local models are not required API Key
    2. Check the model configuration for api_key
    3. Check api_key in manufacturer configuration (if providers_dict is provided)
    4. Check the environment variables for api_key

    Args:
        llm_config: LLM Configuration object (LLMConfig or dictionary)
        providers_dict: Manufacturer configuration dictionary {provider_name: LLMProvider}, Optional

    Returns:
        bool: Whether there is a valid API Key (logically consistent with the has_api_key field)
    """
    # Get provider and api_key
    if hasattr(llm_config, 'provider'):
        provider = llm_config.provider
        model_api_key = llm_config.api_key
    else:
        provider = llm_config.get('provider', '')
        model_api_key = llm_config.get('api_key', '')

    # 🔥 Not required for local models API Key
    local_models = ["ollama", "localai"]
    if provider.lower() in local_models:
        return True

    # 1. Check the model configuration for api_key
    if is_valid_api_key(model_api_key):
        return True

    # 2. Check the api_key in the manufacturer configuration (use database configuration first)
    if providers_dict and provider in providers_dict:
        provider_obj = providers_dict[provider]
        # 🔥 Check if the manufacturer is a local model
        provider_name = provider_obj.name if hasattr(provider_obj, 'name') else provider_obj.get('name', '')
        if provider_name.lower() in local_models:
            return True
        
        provider_api_key = provider_obj.api_key if hasattr(provider_obj, 'api_key') else provider_obj.get('api_key', '')
        if is_valid_api_key(provider_api_key):
            return True

    # 3. Check the api_key in the environment variable (logically consistent with /api/config/llm/providers)
    env_api_key = get_env_api_key_for_provider(provider)
    if env_api_key:
        return True

    return False

