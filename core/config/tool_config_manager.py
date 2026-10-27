"""
Tool Configuration Manager

Manage tool runtime configuration and status
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ToolConfigManager:
    """
    Tool Configuration Manager
    
    Management:
    1. Tool enabled/disabled status
    2. The tool s runtime configuration (timeout, retry, cache_ttl) 
    3. Tool parameter definition
    4. Tool metadata
    
    Priority: Database Configuration > Code default configuration
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._db = None
        self._cache = {}  # tool_id -> config
        self._cache_ttl = 300  # 5 minutes cache
        self._cache_time = {}
        self._initialized = True
    
    def set_database(self, db):
        """Set up database connection"""
        self._db = db
        self._clear_cache()
    
    def _clear_cache(self):
        """Clear cache"""
        self._cache = {}
        self._cache_time = {}
    
    def _is_cache_valid(self, tool_id: str) -> bool:
        """Check if cache is valid"""
        if tool_id not in self._cache_time:
            return False
        elapsed = (datetime.utcnow() - self._cache_time[tool_id]).total_seconds()
        return elapsed < self._cache_ttl
    
    def get_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """
        Get tool configuration
        
        Args:
            tool_id: Tools ID
            
        Returns:
            Tool configuration dictionary, including:
            - enabled: Whether to enable
            - config: Runtime configuration (timeout, retry_count, cache_ttl) 
            - parameters: Parameter definition
            - metadata: metadata
        """
        # Check cache
        if tool_id in self._cache and self._is_cache_valid(tool_id):
            return self._cache[tool_id]
        
        config = None
        
        # Load from database
        if self._db is not None:
            try:
                config = self._db.tool_configs.find_one({"tool_id": tool_id})
                if config:
                    # Remove MongoDB's _id field
                    config.pop("_id", None)
            except Exception as e:
                logger.warning(f"Loading tool configuration from database failed: {e}")
        
        # If the database does not exist, use the default configuration
        if config is None:
            config = self._get_default_tool_config(tool_id)
        
        # Update cache
        if config:
            self._cache[tool_id] = config
            self._cache_time[tool_id] = datetime.utcnow()
        
        return config
    
    def _get_default_tool_config(self, tool_id: str) -> Dict[str, Any]:
        """Get the default configuration of the tool"""
        from core.tools.registry import ToolRegistry
        
        registry = ToolRegistry()
        tool = registry.get_tool(tool_id)
        
        if tool is None:
            return {
                "tool_id": tool_id,
                "enabled": False,
                "config": {},
                "parameters": {},
                "metadata": {}
            }
        
        # Get default configuration from tool class
        return {
            "tool_id": tool_id,
            "name": getattr(tool, "name", tool_id),
            "description": getattr(tool, "description", ""),
            "category": getattr(tool, "category", "general"),
            "enabled": True,
            "config": {
                "timeout": getattr(tool, "timeout", 30),
                "retry_count": getattr(tool, "retry_count", 3),
                "cache_ttl": getattr(tool, "cache_ttl", 300),
            },
            "parameters": getattr(tool, "args_schema", {}).schema() if hasattr(tool, "args_schema") else {},
            "metadata": {
                "is_builtin": True,
                "version": getattr(tool, "version", "1.0.0"),
            }
        }
    
    def save_tool_config(self, config: Dict[str, Any]) -> bool:
        """
        Save tool configuration to database
        
        Args:
            config: Tool configuration dictionary
            
        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        tool_id = config.get("tool_id")
        if not tool_id:
            logger.error("Configuration is missing tool_id")
            return False

        try:
            config["updated_at"] = datetime.utcnow().isoformat()
            self._db.tool_configs.update_one(
                {"tool_id": tool_id},
                {
                    "$set": config,
                    "$setOnInsert": {"created_at": datetime.utcnow().isoformat()}
                },
                upsert=True
            )

            # clear cache
            if tool_id in self._cache:
                del self._cache[tool_id]
            if tool_id in self._cache_time:
                del self._cache_time[tool_id]

            logger.info(f"✅ Tool configuration saved: {tool_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save tool configuration: {e}")
            return False

    def is_tool_enabled(self, tool_id: str) -> bool:
        """Check if the tool is enabled"""
        config = self.get_tool_config(tool_id)
        return config.get("enabled", False) if config else False

    def enable_tool(self, tool_id: str) -> bool:
        """enable tools"""
        return self._set_tool_enabled(tool_id, True)

    def disable_tool(self, tool_id: str) -> bool:
        """Disable tools"""
        return self._set_tool_enabled(tool_id, False)

    def _set_tool_enabled(self, tool_id: str, enabled: bool) -> bool:
        """Set tool enablement status"""
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.tool_configs.update_one(
                {"tool_id": tool_id},
                {
                    "$set": {
                        "enabled": enabled,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if tool_id in self._cache:
                del self._cache[tool_id]

            logger.info(f"✅ Tools {tool_id} Already{'enable' if enabled else 'Disable'}")
            return True
        except Exception as e:
            logger.error(f"Setting tool status failed: {e}")
            return False

    def get_all_tool_configs(self, category: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get all tool configurations

        Args:
            category: Optional, filter by category
            enabled_only: Whether to return only enabled tools

        Returns:
            Tool configuration list
        """
        result = []

        if self._db is not None:
            try:
                query = {}
                if category:
                    query["category"] = category
                if enabled_only:
                    query["enabled"] = True

                result = list(self._db.tool_configs.find(query))
                # Remove _id field
                for config in result:
                    config.pop("_id", None)
            except Exception as e:
                logger.warning(f"Failed to obtain tool configuration list: {e}")

        # If database is empty, load default configuration from code
        if not result:
            from core.tools.registry import ToolRegistry
            registry = ToolRegistry()
            for tool_id in registry.list_tools():
                config = self._get_default_tool_config(tool_id)
                if category and config.get("category") != category:
                    continue
                if enabled_only and not config.get("enabled", False):
                    continue
                result.append(config)

        return result

    def update_tool_runtime_config(self, tool_id: str, runtime_config: Dict[str, Any]) -> bool:
        """
        Update the tool s runtime configuration

        Args:
            tool_id: Tools ID
            runtime_config: Runtime configuration (timeout, retry_count, cache_ttl etc.)

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.tool_configs.update_one(
                {"tool_id": tool_id},
                {
                    "$set": {
                        "config": runtime_config,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if tool_id in self._cache:
                del self._cache[tool_id]

            logger.info(f"✅ Tool runtime configuration updated: {tool_id}")
            return True
        except Exception as e:
            logger.error(f"Update tool runtime configuration failed: {e}")
            return False


