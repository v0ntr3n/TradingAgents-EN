"""
Intelligent body factory

Responsible for creating and configuring agent instances

v2.0 new features:
- Supports dynamic loading of tools from configuration or database
- Supports LangChain LLM integration
"""

import logging
from typing import Any, Dict, Optional, Type, List

from langchain_core.language_models import BaseChatModel

from .base import BaseAgent
from .config import AgentConfig, AgentMetadata, AgentMaintenanceStatus
from .registry import AgentRegistry, get_registry
from .universal import UniversalAgent

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Intelligent body factory
    
    Usage:
        factory = AgentFactory()
        
        # Create an agent instance
        agent = factory.create("market_analyst", config=my_config)
        
        # Create in batches
        agents = factory.create_many(["market_analyst", "news_analyst"])
    """
    
    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or get_registry()
    
    def create(
        self,
        agent_id: str,
        config: Optional[AgentConfig] = None,
        llm: Optional[BaseChatModel] = None,
        tool_ids: Optional[List[str]] = None,
        memory: Optional[Any] = None,
        **config_overrides
    ) -> BaseAgent:
        """
        Create an agent instance

        Args:
            agent_id: agent ID
            config: Agent Configuration (Legacy)
            llm: LangChain LLM Example (new version)
            tool_ids: Tool ID list (new version, optional)
            memory: Memory system instance (v2.0, optional)
            **config_overrides: Configure coverage parameters

        Returns:
            Initialized agent instance
        """
        logger.info(f"[AgentFactory] 🏭 Start creating Agent: {agent_id}")
        logger.info(f"   - config: {config.model_dump() if config else 'None'}")
        logger.info(f"   - llm: {type(llm).__name__ if llm else 'None'}")
        logger.info(f"   - tool_ids: {tool_ids}")
        logger.info(f"   - config_overrides: {config_overrides}")

        # 🔥 Check if it is obsolete Agent
        metadata = self.registry.get_metadata(agent_id)
        if metadata and metadata.maintenance_status == AgentMaintenanceStatus.DEPRECATED:
            import warnings
            warnings.warn(
                f"Agent '{agent_id}' Deprecated, please use v2 version (e.g. '{agent_id}_v2') . "
                f"This agent will be removed in a future release.",
                DeprecationWarning,
                stacklevel=3
            )
            logger.warning(f"[AgentFactory] ⚠️ Agent '{agent_id}' Deprecated, it is recommended to use v2 version")

        agent_class = self.registry.get(agent_id)

        if agent_class is None:
            # 🆕 Downgrade: Try loading and creating from agent_configs database UniversalAgent
            universal = self._try_create_universal_agent(
                agent_id, config, llm, tool_ids, memory
            )
            if universal is not None:
                return universal
            raise ValueError(f"agent '{agent_id}' The implementation is not registered and the corresponding configuration cannot be found in agent_configs")

        # Merge configuration
        if config is None:
            config = AgentConfig()

        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        # v2.0: Check the parameters supported by the Agent
        import inspect
        supports_llm = False
        supports_memory = False

        if llm is not None or memory is not None:
            try:
                sig = inspect.signature(agent_class.__init__)
                supports_llm = "llm" in sig.parameters
                supports_memory = "memory" in sig.parameters
                logger.info(f"[AgentFactory] 🔍 Check Agent constructor signature:")
                logger.info(f"   - Agent class: {agent_class.__name__}")
                logger.info(f"   - Support llm parameter: {supports_llm}")
                logger.info(f"   - Support memory parameter: {supports_memory}")
                logger.info(f"   - Constructor parameters: {list(sig.parameters.keys())}")
            except Exception as e:
                logger.warning(f"[AgentFactory] ⚠️ Checking constructor signature failed: {e}")

        try:
            # Build initialization parameters
            init_kwargs = {"config": config}

            if llm is not None and supports_llm:
                init_kwargs["llm"] = llm
                logger.info(f"[AgentFactory] ✅ Will pass in LLM parameters: {type(llm).__name__}")
            elif llm is not None and not supports_llm:
                logger.warning(
                    f"[AgentFactory] ⚠️ Agent {agent_id} The constructor of does not support the llm parameter,"
                    f"But the caller passed in llm. Legacy dependency injection will be used."
                )
            elif llm is None:
                logger.warning(
                    f"[AgentFactory] ⚠️ The caller did not pass in the llm parameter."
                    f"Agent {agent_id} You will need to create the LLM client from configuration or environment variables."
                )

            if tool_ids is not None and supports_llm:
                init_kwargs["tool_ids"] = tool_ids

            if memory is not None and supports_memory:
                init_kwargs["memory"] = memory

            # Create Agent
            if len(init_kwargs) > 1:  # There are additional parameters
                logger.info(f"[AgentFactory] ✅ Created using v2.0 method Agent: {agent_id}")
                logger.info(f"   - Pass parameters: {list(init_kwargs.keys())}")
                agent = agent_class(**init_kwargs)
            else:
                logger.info(f"[AgentFactory] ⚠️ Created using legacy methods Agent: {agent_id}")
                agent = agent_class(config)

        except TypeError as e:
            error_msg = str(e)
            if "unexpected keyword argument" in error_msg:
                logger.warning(f"[AgentFactory] ⚠️ Agent {agent_id} Some v2.0 parameters are not supported and will be downgraded to the old version.")
                logger.warning(f"   - Error: {e}")
                agent = agent_class(config)
            else:
                logger.error(f"[AgentFactory] ❌ Agent creation failed: {e}")
                raise

        # Legacy adaptation: If llm is provided but the constructor does not support it, try injecting the dependency
        if llm is not None and not supports_llm and hasattr(agent, "set_dependencies"):
            try:
                from tradingagents.agents.utils.agent_utils import Toolkit
                try:
                    from tradingagents.default_config import DEFAULT_CONFIG
                    toolkit = Toolkit(config=DEFAULT_CONFIG)
                except Exception:
                    toolkit = Toolkit()
                agent.set_dependencies(llm, toolkit)
                logger.info(f"Already for Agent {agent_id} Inject legacy dependencies (LLM/Toolkit)")
            except Exception as dep_err:
                logger.warning(f"for Agent {agent_id} Dependency injection failed: {dep_err}")

        # Initialization (if needed)
        if hasattr(agent, 'initialize'):
            logger.info(f"[AgentFactory] 🔧 call Agent.initialize()")
            agent.initialize()

        # 🔍 Print the final status of the Agent
        logger.info(f"[AgentFactory] ✅ Agent Creation completed: {agent_id}")
        logger.info(f"   - Agent Type: {type(agent).__name__}")
        logger.info(f"   - Is there _llm: {hasattr(agent, '_llm')}")
        logger.info(f"   - Is there _tools: {hasattr(agent, '_tools')}")
        if hasattr(agent, '_llm'):
            logger.info(f"   - _llm value: {type(agent._llm).__name__ if agent._llm else 'None'}")
        if hasattr(agent, '_tools'):
            logger.info(f"   - _tools value: {agent._tools}")
            if agent._tools:
                logger.info(f"   - Number of tools: {len(agent._tools)}")
                logger.info(f"   - Tool name: {[t.name if hasattr(t, 'name') else str(t) for t in agent._tools]}")

        return agent

    def _try_create_universal_agent(
        self,
        agent_id: str,
        config: Optional[AgentConfig],
        llm: Optional[Any],
        tool_ids: Optional[List[str]],
        memory: Optional[Any],
    ) -> Optional[BaseAgent]:
        """
        Try to load the configuration from the agent_configs database to create the UniversalAgent.

        Called when agent_id is not in the hardcoded registry, implemented"database driven new Agent"Ability.

        Args:
            agent_id: to create Agent ID
            config: Runtime configuration (may be None)
            llm: LangChain LLM Example
            tool_ids: Tool list (may have been parsed by WorkflowBuilder)
            memory: Memory system example

        Returns:
            UniversalAgent instance, or None if it is not found in the database either.
        """
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            if db is None:
                logger.warning(f"[AgentFactory] The database is not connected and cannot be created UniversalAgent: {agent_id}")
                return None

            doc = db.agent_configs.find_one({
                "agent_id": agent_id,
                "enabled": True,
                "$or": [
                    {"metadata.source": {"$ne": "agent_workshop"}},
                    {"metadata.source": "agent_workshop", "version_status": {"$in": ["active", "testing"]}, "runtime_status": "active"},
                ],
            })
            if doc is None:
                logger.debug(f"[AgentFactory] agent_configs No runnable found in '{agent_id}', Unable to create UniversalAgent")
                return None

            agent_name = doc.get("name") or doc.get("agent_name") or agent_id
            agent_description = doc.get("description") or f"{agent_name} - Driven by database configuration"
            output_field = doc.get("output_field") or "analysis_report"

            # Tool list: Priority is given to the one passed in by the caller (the one that has been parsed by WorkflowBuilder),
            # Otherwise read agent_configs default_tools
            resolved_tool_ids = tool_ids
            if not resolved_tool_ids:
                resolved_tool_ids = doc.get("default_tools") or doc.get("tools") or []

            if config is None:
                config = AgentConfig()

            logger.info(
                f"[AgentFactory] 🌐 Created from agent_configs UniversalAgent: {agent_id} "
                f"(name={agent_name}, output_field={output_field}, tools={resolved_tool_ids})"
            )

            agent = UniversalAgent(
                config=config,
                llm=llm,
                tool_ids=resolved_tool_ids,
                agent_id=agent_id,
                agent_name=agent_name,
                agent_description=agent_description,
                output_field=output_field,
                prompt_template_type=str(doc.get("prompt_template_type") or "universal"),
                prompt_template_name=str(doc.get("prompt_template_name") or agent_id),
                prompt_template_id=str(((doc.get("metadata") or {}).get("template_id") or "")).strip() or None,
                prompt_template_status=str(((doc.get("metadata") or {}).get("template_status") or "")).strip() or None,
                version_status=str(((doc.get("metadata") or {}).get("version_status") or "")).strip() or None,
            )

            if memory is not None and hasattr(agent, "_memory"):
                agent._memory = memory

            if hasattr(agent, "initialize"):
                agent.initialize()

            logger.info(f"[AgentFactory] ✅ UniversalAgent Created successfully: {agent_id}")
            return agent

        except Exception as e:
            logger.warning(f"[AgentFactory] ⚠️ Failed to create UniversalAgent ({agent_id}): {e}")
            return None

    def create_with_dynamic_tools(
        self,
        agent_id: str,
        llm: BaseChatModel,
        config: Optional[AgentConfig] = None
    ) -> BaseAgent:
        """
        v2.0: Create an agent instance and automatically load tools from the configuration

        Args:
            agent_id: agent ID
            llm: LangChain LLM Example
            config: Agent configuration (optional)

        Returns:
            Initialized agent instance
        """
        # Load tool list from configuration
        from core.config.binding_manager import BindingManager
        tool_ids = BindingManager().get_tools_for_agent(agent_id)

        if not tool_ids:
            # Downgrade: Use default tools from metadata
            metadata = self.registry.get_metadata(agent_id)
            if metadata:
                tool_ids = getattr(metadata, 'default_tools', None) or getattr(metadata, 'tools', [])

        logger.info(f"for Agent '{agent_id}' Loading tools: {tool_ids}")

        return self.create(
            agent_id=agent_id,
            config=config,
            llm=llm,
            tool_ids=tool_ids
        )
    
    def create_many(
        self,
        agent_ids: list,
        shared_config: Optional[AgentConfig] = None,
        **config_overrides
    ) -> Dict[str, BaseAgent]:
        """
        Create agents in batches
        
        Args:
            agent_ids: Agent ID list
            shared_config: Shared configuration
            **config_overrides: Configuration override
            
        Returns:
            {agent_id: agent_instance} dictionary
        """
        agents = {}
        for agent_id in agent_ids:
            try:
                agents[agent_id] = self.create(
                    agent_id, 
                    config=shared_config, 
                    **config_overrides
                )
            except ValueError as e:
                # Log warning but continue creating other agents
                print(f"warning: {e}")
        
        return agents
    
    def get_available_agents(self) -> list:
        """Get all registered implemented agents ID"""
        return [
            m.id for m in self.registry.list_all()
            if self.registry.is_registered(m.id)
        ]
    
    def get_agent_metadata(self, agent_id: str) -> Optional[AgentMetadata]:
        """Get agent metadata"""
        return self.registry.get_metadata(agent_id)


# Convenience function
def create_agent(
    agent_id: str,
    config: Optional[AgentConfig] = None,
    llm: Optional[BaseChatModel] = None,
    tool_ids: Optional[List[str]] = None,
    memory: Optional[Any] = None,
    **kwargs
) -> BaseAgent:
    """
    Convenience function: Create an agent

    Usage:
        from core.agents import create_agent

        # Old version
        agent = create_agent("market_analyst", llm_provider="deepseek")

        # New version (v2.0)
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("market_analyst", llm=llm, tool_ids=["get_stock_market_data_unified"])

        # v2.0 with memory
        from core.memory import MemoryManager
        memory_mgr = MemoryManager(embedding_mgr)
        agent_memory = memory_mgr.get_agent_memory("market_analyst")
        agent = create_agent("market_analyst", llm=llm, memory=agent_memory)
    """
    factory = AgentFactory()
    return factory.create(agent_id, config, llm=llm, tool_ids=tool_ids, memory=memory, **kwargs)


def create_agent_with_dynamic_tools(
    agent_id: str,
    llm: BaseChatModel,
    config: Optional[AgentConfig] = None
) -> BaseAgent:
    """
    v2.0 Convenience function: Create an agent and automatically load tools from the configuration

    Usage:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent_with_dynamic_tools

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent_with_dynamic_tools("market_analyst", llm)
    """
    factory = AgentFactory()
    return factory.create_with_dynamic_tools(agent_id, llm, config)
