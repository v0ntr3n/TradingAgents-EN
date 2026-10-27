"""
Data directory configuration tool
Data Directory Configuration Utilities

Provide a unified data directory access interface for other modules in the project
"""

import os
import sys
from pathlib import Path
from typing import Optional, Union

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from scripts.unified_data_manager import get_data_manager, get_data_path
except ImportError:
    # If it cannot be imported, provide a basic implementation
    def get_data_path(key: str, create: bool = True) -> Path:
        """Basic data path acquisition function"""
        project_root = Path(__file__).parent.parent
        
        # Basic path mapping
        path_mapping = {
            'data_root': 'data',
            'cache': 'data/cache',
            'analysis_results': 'data/analysis_results',
            'sessions': 'data/sessions',
            'logs': 'data/logs',
            'config': 'data/config',
            'temp': 'data/temp',
        }
        
        path_str = path_mapping.get(key, f'data/{key}')
        path = project_root / path_str
        
        if create:
            path.mkdir(parents=True, exist_ok=True)
        
        return path


# Convenience function
def get_cache_dir(subdir: Optional[str] = None, create: bool = True) -> Path:
    """
    Get cache directory
    
    Args:
        subdir: Subdirectory name
        create: Whether to automatically create directories
        
    Returns:
        Path: Cache directory path
    """
    if subdir:
        cache_path = get_data_path('cache', create=create) / subdir
        if create:
            cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path
    return get_data_path('cache', create=create)


def get_results_dir(subdir: Optional[str] = None, create: bool = True) -> Path:
    """
    Get analysis results directory
    
    Args:
        subdir: Subdirectory name
        create: Whether to automatically create directories
        
    Returns:
        Path: Result directory path
    """
    if subdir:
        results_path = get_data_path('analysis_results', create=create) / subdir
        if create:
            results_path.mkdir(parents=True, exist_ok=True)
        return results_path
    return get_data_path('analysis_results', create=create)


def get_sessions_dir(subdir: Optional[str] = None, create: bool = True) -> Path:
    """
    Get session data directory
    
    Args:
        subdir: Subdirectory name
        create: Whether to automatically create directories
        
    Returns:
        Path: session directory path
    """
    if subdir:
        sessions_path = get_data_path('sessions', create=create) / subdir
        if create:
            sessions_path.mkdir(parents=True, exist_ok=True)
        return sessions_path
    return get_data_path('sessions', create=create)


def get_logs_dir(subdir: Optional[str] = None, create: bool = True) -> Path:
    """
    Get log directory
    
    Args:
        subdir: Subdirectory name
        create: Whether to automatically create directories
        
    Returns:
        Path: Log directory path
    """
    if subdir:
        logs_path = get_data_path('logs', create=create) / subdir
        if create:
            logs_path.mkdir(parents=True, exist_ok=True)
        return logs_path
    return get_data_path('logs', create=create)


def get_config_dir(subdir: Optional[str] = None, create: bool = True) -> Path:
    """
    Get configuration directory
    
    Args:
        subdir: Subdirectory name
        create: Whether to automatically create directories
        
    Returns:
        Path: Configuration directory path
    """
    if subdir:
        config_path = get_data_path('config', create=create) / subdir
        if create:
            config_path.mkdir(parents=True, exist_ok=True)
        return config_path
    return get_data_path('config', create=create)


def get_temp_dir(subdir: Optional[str] = None, create: bool = True) -> Path:
    """
    Get temporary file directory
    
    Args:
        subdir: Subdirectory name
        create: Whether to automatically create directories
        
    Returns:
        Path: Temporary directory path
    """
    if subdir:
        temp_path = get_data_path('temp', create=create) / subdir
        if create:
            temp_path.mkdir(parents=True, exist_ok=True)
        return temp_path
    return get_data_path('temp', create=create)


# Compatibility functions - provide backward compatibility for existing code
def get_analysis_results_dir() -> Path:
    """Get analysis results directory (Compatibility function)"""
    return get_results_dir()


def get_stock_data_cache_dir() -> Path:
    """Get stock data cache directory"""
    return get_cache_dir('stock_data')


def get_news_data_cache_dir() -> Path:
    """Get the news data cache directory"""
    return get_cache_dir('news_data')


def get_fundamentals_cache_dir() -> Path:
    """Get the fundamental data cache directory"""
    return get_cache_dir('fundamentals')


def get_metadata_cache_dir() -> Path:
    """Get metadata cache directory"""
    return get_cache_dir('metadata')


def get_web_sessions_dir() -> Path:
    """Get web session directory"""
    return get_sessions_dir('web_sessions')


def get_cli_sessions_dir() -> Path:
    """Get CLI session directory"""
    return get_sessions_dir('cli_sessions')


def get_application_logs_dir() -> Path:
    """Get application log directory"""
    return get_logs_dir('application')


def get_operations_logs_dir() -> Path:
    """Get the operation log directory"""
    return get_logs_dir('operations')


def get_user_activities_logs_dir() -> Path:
    """Get user activity log directory"""
    return get_logs_dir('user_activities')


# Environment variable check function
def check_data_directory_config() -> dict:
    """
    Check data directory configuration status
    
    Returns:
        dict: Configuration status information
    """
    env_vars = [
        'TRADINGAGENTS_DATA_DIR',
        'TRADINGAGENTS_CACHE_DIR',
        'TRADINGAGENTS_RESULTS_DIR',
        'TRADINGAGENTS_SESSIONS_DIR',
        'TRADINGAGENTS_LOGS_DIR',
        'TRADINGAGENTS_CONFIG_DIR',
        'TRADINGAGENTS_TEMP_DIR',
    ]
    
    config_status = {}
    for var in env_vars:
        value = os.getenv(var)
        config_status[var] = {
            'set': value is not None,
            'value': value,
            'exists': Path(value).exists() if value else False
        }
    
    return config_status


def print_data_directory_status():
    """Print data directory configuration status"""
    print("📁 Data directory configuration status:")
    print("=" * 50)
    
    status = check_data_directory_config()
    
    for var, info in status.items():
        status_icon = "✅" if info['set'] else "❌"
        exists_icon = "📁" if info['exists'] else "❓"
        
        print(f"{status_icon} {var}")
        if info['set']:
            print(f"   value: {info['value']}")
            print(f"   {exists_icon} Directory exists: {'Yes' if info['exists'] else 'No'}")
        else:
            print("   not set")
        print()


if __name__ == '__main__':
    print_data_directory_status()