"""
Configure system compatibility layer

Provides a configuration-compatible interface to the old tradingagents library,
Enables it to use the new configuration system without modifying the code.

⚠️ This module is for backwards compatibility only, new code should use it directly ConfigService
"""

import os
import asyncio
from typing import Dict, Any, Optional, List
from functools import lru_cache
import warnings

from app.core.config import settings


class ConfigManagerCompat:
    """
    ConfigManager Compatibility class
    
    Provides the same interface as the old ConfigManager, but uses the new configuration system.
    """
    
    def __init__(self):
        """Initialize the compatibility layer"""
        self._warned = False
        self._emit_deprecation_warning()
    
    def _emit_deprecation_warning(self):
        """Issue deprecation warning (only once)"""
        if not self._warned:
            warnings.warn(
                "ConfigManagerCompat is a compatibility layer for legacy code. "
                "Please migrate to app.services.config_service.ConfigService. "
                "See docs/DEPRECATION_NOTICE.md for details.",
                DeprecationWarning,
                stacklevel=3
            )
            self._warned = True
    
    def get_data_dir(self) -> str:
        """
        Get data directory
        
        Returns:
            str: Data directory path
        """
        # Read from environment variables first
        data_dir = os.getenv("DATA_DIR")
        if data_dir:
            return data_dir
        
        # Default value
        return "./data"
    
    def load_settings(self) -> Dict[str, Any]:
        """
        Load system settings
        
        Returns:
            Dict[str, Any]: System settings dictionary
        """
        try:
            # Try loading from a new configuration system
            from app.services.config_service import config_service
            
            # Run asynchronous code in a synchronous context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If the event loop is running, return the default value
                return self._get_default_settings()
            else:
                config = loop.run_until_complete(config_service.get_system_config())
                if config and config.system_settings:
                    return config.system_settings
        except Exception:
            pass
        
        # Return to default settings
        return self._get_default_settings()
    
    def save_settings(self, settings_dict: Dict[str, Any]) -> bool:
        """
        Save system settings
        
        Args:
            settings_dict: System settings dictionary
        
        Returns:
            bool: Is the save successful?
        """
        try:
            from app.services.config_service import config_service
            
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Cannot save if event loop is running
                warnings.warn("Cannot save settings in running event loop", RuntimeWarning)
                return False
            else:
                loop.run_until_complete(
                    config_service.update_system_settings(settings_dict)
                )
                return True
        except Exception as e:
            warnings.warn(f"Failed to save settings: {e}", RuntimeWarning)
            return False
    
    def get_models(self) -> List[Dict[str, Any]]:
        """
        Get the model configuration list (only models with valid API Keys are returned)

        Returns:
            List[Dict[str, Any]]: Model configuration list
        """
        try:
            from app.services.config_service import config_service
            from app.utils.api_key_utils import has_valid_api_key

            loop = asyncio.get_event_loop()
            if loop.is_running():
                return []
            else:
                config = loop.run_until_complete(config_service.get_system_config())
                if config and config.llm_configs:
                    # Get factory configuration
                    providers = loop.run_until_complete(config_service.get_llm_providers())
                    providers_dict = {p.name: p for p in providers}

                    # 🔥 Filter: Only return models with valid API Keys
                    return [
                        {
                            "provider": llm.provider,
                            "model_name": llm.model_name,
                            "api_key": llm.api_key or "",
                            "base_url": llm.base_url,
                            "max_tokens": llm.max_tokens,
                            "temperature": llm.temperature,
                            "enabled": llm.enabled,
                        }
                        for llm in config.llm_configs
                        if llm.enabled and has_valid_api_key(llm, providers_dict)
                    ]
        except Exception:
            pass

        return []
    
    def get_model_config(self, provider: str, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the configuration of the specified model
        
        Args:
            provider: Provider name
            model_name: Model name
        
        Returns:
            Optional[Dict[str, Any]]: Model configuration, returned if it does not exist None
        """
        models = self.get_models()
        for model in models:
            if model["provider"] == provider and model["model_name"] == model_name:
                return model
        return None
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """
        Get default system settings
        
        Returns:
            Dict[str, Any]: Default setting
        """
        return {
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "online_tools": True,
            "online_news": True,
            "realtime_data": False,
            "memory_enabled": True,
            "debug": False,
        }


class TokenTrackerCompat:
    """
    TokenTracker Compatibility class
    
    Provides the same interface as the old TokenTracker.
    """
    
    def __init__(self):
        """Initialize the compatibility layer"""
        self._usage_data = {}
    
    def track_usage(
        self,
        provider: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cost: float = 0.0
    ):
        """
        Record Token usage
        
        Args:
            provider: Provider name
            model_name: Model name
            input_tokens: Enter the number of Tokens
            output_tokens: Output the number of Tokens
            cost: cost
        """
        key = f"{provider}:{model_name}"
        
        if key not in self._usage_data:
            self._usage_data[key] = {
                "provider": provider,
                "model_name": model_name,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "call_count": 0,
            }
        
        self._usage_data[key]["total_input_tokens"] += input_tokens
        self._usage_data[key]["total_output_tokens"] += output_tokens
        self._usage_data[key]["total_cost"] += cost
        self._usage_data[key]["call_count"] += 1

        # NOTE: This compatibility layer only provides in-memory caching and does not persist to the database
        # For persistence, use the relevant functions in app.services.llm_service
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """
        Get usage statistics summary
        
        Returns:
            Dict[str, Any]: Use summary statistics
        """
        return self._usage_data.copy()
    
    def reset_usage(self):
        """Reset usage statistics"""
        self._usage_data.clear()


# Create a global instance (for backward compatibility)
config_manager_compat = ConfigManagerCompat()
token_tracker_compat = TokenTrackerCompat()


# Convenience function
def get_config_manager() -> ConfigManagerCompat:
    """
    Get a configuration manager compatible instance
    
    Returns:
        ConfigManagerCompat: Configuration Manager Compatible Instance
    """
    return config_manager_compat


def get_token_tracker() -> TokenTrackerCompat:
    """
    Get a Token tracker compatible instance
    
    Returns:
        TokenTrackerCompat: Token Tracker Compatibility Example
    """
    return token_tracker_compat

