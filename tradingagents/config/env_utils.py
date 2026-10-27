#!/usr/bin/env python3
"""
Environment variable analysis tool
Provide compatibility Python 3.13+Robust environment variable parsing capabilities
"""

import os
from typing import Any, Union, Optional


def parse_bool_env(env_var: str, default: bool = False) -> bool:
    """
    Parse Boolean type environment variables, compatible with multiple formats
    
    Supported formats:
    - true/True/TRUE
    - false/False/FALSE  
    - 1/0
    - yes/Yes/YES
    - no/No/NO
    - on/On/ON
    - off/Off/OFF
    
    Args:
        env_var: Environment variable name
        default: Default value
        
    Returns:
        bool: parsed boolean value
    """
    value = os.getenv(env_var)
    
    if value is None:
        return default
    
    # Convert to string and remove whitespace
    value_str = str(value).strip()
    
    if not value_str:
        return default
    
    # Convert to lowercase for comparison
    value_lower = value_str.lower()
    
    # truth list
    true_values = {
        'true', '1', 'yes', 'on', 'enable', 'enabled', 
        't', 'y', 'ok', 'okay'
    }
    
    # list of false values
    false_values = {
        'false', '0', 'no', 'off', 'disable', 'disabled',
        'f', 'n', 'none', 'null', 'nil'
    }
    
    if value_lower in true_values:
        return True
    elif value_lower in false_values:
        return False
    else:
        # If not recognized, log a warning and return the default value
        print(f"⚠️ Unable to resolve environment variables {env_var}='{value}', Use default value {default}")
        return default


def parse_int_env(env_var: str, default: int = 0) -> int:
    """
    Parse integer type environment variables
    
    Args:
        env_var: Environment variable name
        default: Default value
        
    Returns:
        int: parsed integer value
    """
    value = os.getenv(env_var)
    
    if value is None:
        return default
    
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        print(f"⚠️ Unable to resolve environment variables {env_var}='{value}' is an integer, use default value {default}")
        return default


def parse_float_env(env_var: str, default: float = 0.0) -> float:
    """
    Parse floating point type environment variables
    
    Args:
        env_var: Environment variable name
        default: Default value
        
    Returns:
        float: Parsed floating point value
    """
    value = os.getenv(env_var)
    
    if value is None:
        return default
    
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        print(f"⚠️ Unable to resolve environment variables {env_var}='{value}' For floating point numbers, use the default value {default}")
        return default


def parse_str_env(env_var: str, default: str = "") -> str:
    """
    Parsing string type environment variables
    
    Args:
        env_var: Environment variable name
        default: Default value
        
    Returns:
        str: parsed string value
    """
    value = os.getenv(env_var)
    
    if value is None:
        return default
    
    return str(value).strip()


def parse_list_env(env_var: str, separator: str = ",", default: Optional[list] = None) -> list:
    """
    Parsing list type environment variables
    
    Args:
        env_var: Environment variable name
        separator: delimiter
        default: Default value
        
    Returns:
        list: parsed list
    """
    if default is None:
        default = []
    
    value = os.getenv(env_var)
    
    if value is None:
        return default
    
    try:
        # Split and remove whitespace
        items = [item.strip() for item in value.split(separator)]
        # filter empty string
        return [item for item in items if item]
    except AttributeError:
        print(f"⚠️ Unable to resolve environment variables {env_var}='{value}' For lists, use default values {default}")
        return default


def get_env_info(env_var: str) -> dict:
    """
    Get detailed information about environment variables
    
    Args:
        env_var: Environment variable name
        
    Returns:
        dict: Environment variable information
    """
    value = os.getenv(env_var)
    
    return {
        'name': env_var,
        'value': value,
        'exists': value is not None,
        'empty': value is None or str(value).strip() == '',
        'type': type(value).__name__ if value is not None else 'None',
        'length': len(str(value)) if value is not None else 0
    }


def validate_required_env_vars(required_vars: list) -> dict:
    """
    Verify that required environment variables are set
    
    Args:
        required_vars: List of required environment variables
        
    Returns:
        dict: Verification results
    """
    results = {
        'all_set': True,
        'missing': [],
        'empty': [],
        'valid': []
    }
    
    for var in required_vars:
        info = get_env_info(var)
        
        if not info['exists']:
            results['missing'].append(var)
            results['all_set'] = False
        elif info['empty']:
            results['empty'].append(var)
            results['all_set'] = False
        else:
            results['valid'].append(var)
    
    return results


# Compatibility functions: maintain backward compatibility
def get_bool_env(env_var: str, default: bool = False) -> bool:
    """Backward-compatible boolean parsing functions"""
    return parse_bool_env(env_var, default)


def get_int_env(env_var: str, default: int = 0) -> int:
    """Backward-compatible integer parsing functions"""
    return parse_int_env(env_var, default)


def get_str_env(env_var: str, default: str = "") -> str:
    """Backwards compatible string parsing functions"""
    return parse_str_env(env_var, default)


# Export main function
__all__ = [
    'parse_bool_env',
    'parse_int_env', 
    'parse_float_env',
    'parse_str_env',
    'parse_list_env',
    'get_env_info',
    'validate_required_env_vars',
    'get_bool_env',  # backwards compatible
    'get_int_env',   # backwards compatible
    'get_str_env'    # backwards compatible
]
