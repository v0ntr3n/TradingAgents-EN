"""
Agent configuration manager

Manage the Agent s runtime configuration and status
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentConfigManager:
    """
    Agent configuration manager
    
    Management:
    1. Agent enabled/disabled status
    2. Agent The execution configuration (max_iterations, timeout, temperature) 
    3. Agent Prompt word template configuration
    4. Agent Default tool list
    
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
        self._cache = {}  # agent_id -> config
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
    
    def _is_cache_valid(self, agent_id: str) -> bool:
        """Check if cache is valid"""
        if agent_id not in self._cache_time:
            return False
        elapsed = (datetime.utcnow() - self._cache_time[agent_id]).total_seconds()
        return elapsed < self._cache_ttl
    
    def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Agent configuration
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent Configuration dictionary, including:
            - enabled: Whether to enable
            - config: execute configure(max_iterations, timeout, temperature) 
            - prompt_template_type: Prompt word template type
            - prompt_template_name: Prompt word template name
            - default_tools: Default tool list
            - required_tools: List of required tools
        """
        # Check cache
        if agent_id in self._cache and self._is_cache_valid(agent_id):
            return self._cache[agent_id]
        
        config = None
        
        # Load from database
        if self._db is not None:
            try:
                config = self._db.agent_configs.find_one({"agent_id": agent_id})
                if config:
                    # Remove MongoDB's _id field
                    config.pop("_id", None)
            except Exception as e:
                logger.warning(f"Failed to load Agent configuration from database: {e}")
        
        # If the database does not exist, use the default configuration
        if config is None:
            config = self._get_default_agent_config(agent_id)
        
        # Update cache
        if config:
            self._cache[agent_id] = config
            self._cache_time[agent_id] = datetime.utcnow()
        
        return config
    
    def _get_default_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get the default configuration of the Agent"""
        from core.agents.registry import AgentRegistry
        
        registry = AgentRegistry()
        metadata = registry.get_metadata(agent_id)
        
        if metadata is None:
            return None
        
        # 🔥 Set different default temperatures based on Agent type
        # Debate Agent: 0.6 (needs creativity and variety)
        # Numerical calculation and evaluation Agent: 0.1 (high accuracy required)
        # Other Agents: 0.2 (balances accuracy and flexibility)
        default_temperature = self._get_default_temperature(agent_id)
        
        # Build default configuration from metadata
        return {
            "agent_id": agent_id,
            "name": metadata.name,
            "description": metadata.description,
            "category": metadata.category.value if hasattr(metadata.category, 'value') else str(metadata.category),
            "version": metadata.version,
            "enabled": True,
            "config": {
                "max_iterations": 3,
                # timeout Intentionally no default value: configured by model level (interface"Large model setup"timeout in
                # by unified_analysis_engine → workflow deep_timeout/quick_timeout) decide;
                # Only if the user is"Agent management"The model-level configuration is only overridden when timeout is explicitly configured for the Agent.
                "temperature": default_temperature,  # 🔥 Use type-specific default temperatures
            },
            "prompt_template_type": metadata.category.value if hasattr(metadata.category, 'value') else "general",
            "prompt_template_name": agent_id,
            "default_tools": metadata.default_tools if metadata.default_tools else [],
            "required_tools": metadata.default_tools if metadata.default_tools else [],
            "metadata": {
                "is_builtin": True,
                "license_tier": metadata.license_tier.value if hasattr(metadata.license_tier, 'value') else "free",
            }
        }
    
    def _get_default_temperature(self, agent_id: str) -> float:
        """
        Get the default temperature based on Agent type

        Args:
            agent_id: Agent ID

        Returns:
            Default temperature value
        """
        # Debate Agent (needs creativity and variety)
        debate_agents = [
            "bull_researcher", "bear_researcher",  # investment debate
            "risky_analyst", "safe_analyst", "neutral_analyst",  # risk debate
            "risky_analyst_v2", "safe_analyst_v2", "neutral_analyst_v2",  # v2.0 risk debate
        ]
        if agent_id in debate_agents:
            logger.info(f"[Agent Configuration] 🌡️ {agent_id} Is the Debate Agent, set the default temperature: 0.6")
            return 0.6
        
        # Numerical calculation and evaluation Agent (requires high accuracy)
        calculation_agents = [
            "risk_assessor", "risk_assessor_v2",  # risk assessment
            "position_analyst",  # Position analysis (numerical calculation)
        ]
        if agent_id in calculation_agents:
            logger.info(f"[Agent Configuration] 🌡️ {agent_id} It is a numerical calculation Agent and sets the default temperature.: 0.1")
            return 0.1
        
        # Other Agents (balancing accuracy and flexibility)
        logger.info(f"[Agent Configuration] 🌡️ {agent_id} It is a standard Agent and sets the default temperature.: 0.2")
        return 0.2
    
    def save_agent_config(self, config: Dict[str, Any]) -> bool:
        """
        Save Agent configuration to database
        
        Args:
            config: Agent Configuration dictionary
            
        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        agent_id = config.get("agent_id")
        if not agent_id:
            logger.error("Configuration is missing agent_id")
            return False

        try:
            # Prepare to update data
            update_data = config.copy()
            update_data["updated_at"] = datetime.utcnow().isoformat()

            # If created_at is present in the configuration, remove it (let$setOnInsert processing)
            created_at = update_data.pop("created_at", None)

            # Build update operation
            update_op = {"$set": update_data}

            # Only set on insert created_at
            if created_at:
                update_op["$setOnInsert"] = {"created_at": created_at}
            else:
                update_op["$setOnInsert"] = {"created_at": datetime.utcnow().isoformat()}

            self._db.agent_configs.update_one(
                {"agent_id": agent_id},
                update_op,
                upsert=True
            )

            # clear cache
            if agent_id in self._cache:
                del self._cache[agent_id]
            if agent_id in self._cache_time:
                del self._cache_time[agent_id]

            logger.info(f"✅ Agent Configuration saved: {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save Agent configuration: {e}")
            return False

    def is_agent_enabled(self, agent_id: str) -> bool:
        """Check if Agent is enabled"""
        config = self.get_agent_config(agent_id)
        return config.get("enabled", False) if config else False

    def enable_agent(self, agent_id: str) -> bool:
        """enable Agent"""
        return self._set_agent_enabled(agent_id, True)

    def disable_agent(self, agent_id: str) -> bool:
        """Disable Agent"""
        return self._set_agent_enabled(agent_id, False)

    def _set_agent_enabled(self, agent_id: str, enabled: bool) -> bool:
        """Set Agent enabled status"""
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.agent_configs.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "enabled": enabled,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if agent_id in self._cache:
                del self._cache[agent_id]

            logger.info(f"✅ Agent {agent_id} Already{'enable' if enabled else 'Disable'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set Agent status: {e}")
            return False

    def get_all_agent_configs(self, category: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get all Agent configurations

        Args:
            category: Optional, filter by category
            enabled_only: Whether to return only enabled Agent

        Returns:
            Agent Configuration list
        """
        result = []

        if self._db is not None:
            try:
                query = {}
                if category:
                    query["category"] = category
                if enabled_only:
                    query["enabled"] = True

                result = list(self._db.agent_configs.find(query))
                # Remove _id field
                for config in result:
                    config.pop("_id", None)
            except Exception as e:
                logger.warning(f"Failed to obtain Agent configuration list: {e}")

        # If database is empty, load default configuration from code
        if not result:
            from core.agents.registry import AgentRegistry
            registry = AgentRegistry()
            for metadata in registry.list_all():
                agent_id = metadata.id
                config = self._get_default_agent_config(agent_id)
                if config is None:
                    continue
                if category and config.get("category") != category:
                    continue
                if enabled_only and not config.get("enabled", False):
                    continue
                result.append(config)

        return result

    def update_agent_execution_config(self, agent_id: str, execution_config: Dict[str, Any]) -> bool:
        """
        Update the Agent s execution configuration

        Args:
            agent_id: Agent ID
            execution_config: execute configure(max_iterations, timeout, temperature etc.)

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.agent_configs.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "config": execution_config,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if agent_id in self._cache:
                del self._cache[agent_id]

            logger.info(f"✅ Agent Execution configuration updated: {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Update Agent execution configuration failed: {e}")
            return False

    def update_agent_prompt_template(self, agent_id: str, template_type: str, template_name: str) -> bool:
        """
        Update the Agent s prompt word template configuration

        Args:
            agent_id: Agent ID
            template_type: template type
            template_name: Template name

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("Database not connected")
            return False

        try:
            self._db.agent_configs.update_one(
                {"agent_id": agent_id},
                {
                    "$set": {
                        "prompt_template_type": template_type,
                        "prompt_template_name": template_name,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                },
                upsert=True
            )

            # clear cache
            if agent_id in self._cache:
                del self._cache[agent_id]

            logger.info(f"✅ Agent Prompt word template has been updated: {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Agent prompt word template: {e}")
            return False


