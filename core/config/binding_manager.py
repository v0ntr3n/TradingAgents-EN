"""
binding manager

The binding relationship between management tool-Agent and Agent-workflow
Supports loading from database and code configuration
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


LEGACY_AGENT_TOOL_REWRITES = {
    "news_analyst_v2": {
        "remove": {"get_stock_news_unified"},
        "ensure": [
            "get_stock_news_headlines_unified",
            "get_stock_news_details_unified",
        ],
    },
}


class BindingManager:
    """
    Unified binding manager
    
    Management:
    1. Tools -> Agent binding
    2. Agent -> Workflow binding
    3. Agent IO definition of
    
    Priority: Database Configuration > Code configuration
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
        self._cache = {
            "tool_agent": {},      # agent_id -> [tool_id, ...]
            "agent_workflow": {},  # workflow_id -> [agent_id, ...]
            "agent_io": {},        # agent_id -> AgentIODefinition
        }
        self._cache_ttl = 300  # 5 minutes cache
        self._cache_time = {}
        self._initialized = True
    
    def set_database(self, db):
        """Set up database connection"""
        self._db = db
        self._clear_cache()
    
    def _clear_cache(self):
        """Clear cache"""
        for key in self._cache:
            self._cache[key] = {}
        self._cache_time = {}
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is valid"""
        if cache_key not in self._cache_time:
            return False
        elapsed = (datetime.utcnow() - self._cache_time[cache_key]).total_seconds()
        return elapsed < self._cache_ttl
    
    # ==================== Tool-Agent Binding ====================
    
    def get_tools_for_agent(self, agent_id: str) -> List[str]:
        """
        Get the list of tools bound to the Agent

        Args:
            agent_id: Agent ID

        Returns:
            Tool ID list
        """
        logger.info(f"🔍 [BindingManager] Query {agent_id} tool binding...")

        cache_key = f"tool_agent:{agent_id}"

        # Check cache
        if agent_id in self._cache["tool_agent"] and self._is_cache_valid(cache_key):
            cached_tools = self._cache["tool_agent"][agent_id]
            logger.info(f"📦 [BindingManager] Get from cache {agent_id} Tools: {cached_tools}")
            return cached_tools

        tool_ids = []

        # Load from database
        if self._db is not None:
            try:
                logger.info(f"🔍 [BindingManager] Query the database tool_agent_bindings collection...")
                bindings = list(self._db.tool_agent_bindings.find(
                    {"agent_id": agent_id, "is_active": {"$ne": False}},
                    sort=[("priority", -1)]
                ))
                tool_ids = [b["tool_id"] for b in bindings]
                logger.info(f"📦 [BindingManager] Database query results: {len(bindings)} strip binding, Tools: {tool_ids}")
            except Exception as e:
                logger.warning(f"Loading tool binding from database failed: {e}")
        else:
            logger.warning(f"⚠️ [BindingManager] Database not connected")

        # If the database does not exist, load it from the code configuration
        if not tool_ids:
            logger.info(f"🔍 [BindingManager] No results in database, try loading from code configuration...")
            tool_ids = self._get_default_tools_for_agent(agent_id)
            logger.info(f"📦 [BindingManager] Code configuration results: {tool_ids}")

        tool_ids = self._normalize_tool_ids(agent_id, tool_ids)

        # Update cache
        self._cache["tool_agent"][agent_id] = tool_ids
        self._cache_time[cache_key] = datetime.utcnow()

        logger.info(f"✅ [BindingManager] {agent_id} The ultimate tool list: {tool_ids}")
        return tool_ids

    def _normalize_tool_ids(self, agent_id: str, tool_ids: List[str]) -> List[str]:
        """Normalize tool list, filter dirty data and be compatible with old bindings."""
        normalized_tools: List[str] = []
        seen_tools = set()
        invalid_tools: List[str] = []
        registry = None

        try:
            from core.tools.registry import ToolRegistry

            registry = ToolRegistry()
        except Exception as exc:
            logger.warning(f"⚠️ [BindingManager] Failed to initialize tool registry, skipping tool validity verification: {exc}")

        for tool_id in tool_ids:
            if not tool_id or tool_id in seen_tools:
                continue

            if registry is not None and not registry.has_tool(tool_id):
                invalid_tools.append(tool_id)
                continue

            seen_tools.add(tool_id)
            normalized_tools.append(tool_id)

        if invalid_tools:
            logger.warning(
                f"⚠️ [BindingManager] {agent_id} Invalid tool binding detected, automatically ignored: {invalid_tools}"
            )

        rewrite_rule = LEGACY_AGENT_TOOL_REWRITES.get(agent_id)
        if not rewrite_rule:
            return normalized_tools

        removed_tools = []
        remove_tools = rewrite_rule.get("remove", set())
        if remove_tools:
            filtered_tools = []
            for tool_id in normalized_tools:
                if tool_id in remove_tools:
                    removed_tools.append(tool_id)
                    continue
                filtered_tools.append(tool_id)
            normalized_tools = filtered_tools

        if removed_tools:
            logger.info(
                f"🔄 [BindingManager] {agent_id} Old tool binding detected, replaced with new tool flow: {removed_tools}"
            )

        added_tools = []
        for required_tool in rewrite_rule.get("ensure", []):
            if required_tool in normalized_tools:
                continue
            if registry is not None and not registry.has_tool(required_tool):
                logger.warning(
                    f"⚠️ [BindingManager] {agent_id} The required tools are not registered and cannot be automatically completed.: {required_tool}"
                )
                continue
            normalized_tools.append(required_tool)
            added_tools.append(required_tool)

        if added_tools:
            logger.info(f"✅ [BindingManager] {agent_id} Autocomplete tool: {added_tools}")

        return normalized_tools
    
    def _get_default_tools_for_agent(self, agent_id: str) -> List[str]:
        """Get default tools list from code configuration"""
        from core.agents.config import BUILTIN_AGENTS

        if agent_id in BUILTIN_AGENTS:
            agent = BUILTIN_AGENTS[agent_id]
            return agent.default_tools if hasattr(agent, 'default_tools') else []
        return []
    
    def bind_tool(self, agent_id: str, tool_id: str, priority: int = 0) -> bool:
        """
        bind tool to Agent
        
        Args:
            agent_id: Agent ID
            tool_id: Tools ID
            priority: Priority (the bigger the priority)
            
        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("The database is not connected and the tool cannot be bound.")
            return False
        
        try:
            self._db.tool_agent_bindings.update_one(
                {"agent_id": agent_id, "tool_id": tool_id},
                {
                    "$set": {
                        "agent_id": agent_id,
                        "tool_id": tool_id,
                        "priority": priority,
                        "is_active": True,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow().isoformat(),
                    }
                },
                upsert=True
            )
            
            # clear cache
            cache_key = f"tool_agent:{agent_id}"
            if agent_id in self._cache["tool_agent"]:
                del self._cache["tool_agent"][agent_id]
            if cache_key in self._cache_time:
                del self._cache_time[cache_key]
            
            return True
        except Exception as e:
            logger.error(f"Binding tool failed: {e}")
            return False
    
    def unbind_tool(self, agent_id: str, tool_id: str) -> bool:
        """Unbundling tool"""
        if self._db is None:
            return False

        try:
            self._db.tool_agent_bindings.update_one(
                {"agent_id": agent_id, "tool_id": tool_id},
                {"$set": {"is_active": False, "updated_at": datetime.utcnow().isoformat()}}
            )

            # clear cache
            if agent_id in self._cache["tool_agent"]:
                del self._cache["tool_agent"][agent_id]

            return True
        except Exception as e:
            logger.error(f"Failed to unbind tool: {e}")
            return False

    # ==================== Agent-Workflow binding ====================

    def get_agents_for_workflow(self, workflow_id: str) -> List[str]:
        """
        Get the list of Agents included in the workflow

        Args:
            workflow_id: Workflow ID

        Returns:
            Agent ID List (in order)
        """
        cache_key = f"agent_workflow:{workflow_id}"

        if workflow_id in self._cache["agent_workflow"] and self._is_cache_valid(cache_key):
            return self._cache["agent_workflow"][workflow_id]

        agent_ids = []

        if self._db is not None:
            try:
                bindings = list(self._db.agent_workflow_bindings.find(
                    {"workflow_id": workflow_id, "is_active": {"$ne": False}},
                    sort=[("order", 1)]
                ))
                agent_ids = [b["agent_id"] for b in bindings]
            except Exception as e:
                logger.warning(f"Failed to load Agent binding from database: {e}")

        # Update cache
        self._cache["agent_workflow"][workflow_id] = agent_ids
        self._cache_time[cache_key] = datetime.utcnow()

        return agent_ids

    def bind_agent(self, workflow_id: str, agent_id: str, order: int = 0) -> bool:
        """Bind Agent to Workflow"""
        if self._db is None:
            logger.error("The database is not connected and cannot be bound.Agent")
            return False

        try:
            self._db.agent_workflow_bindings.update_one(
                {"workflow_id": workflow_id, "agent_id": agent_id},
                {
                    "$set": {
                        "workflow_id": workflow_id,
                        "agent_id": agent_id,
                        "order": order,
                        "is_active": True,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow().isoformat(),
                    }
                },
                upsert=True
            )

            if workflow_id in self._cache["agent_workflow"]:
                del self._cache["agent_workflow"][workflow_id]

            return True
        except Exception as e:
            logger.error(f"Failed to bind Agent: {e}")
            return False

    # ==================== Node level tool binding (three levels of priority)====================

    def get_tools_for_node(
        self,
        agent_id: str,
        workflow_id: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> List[str]:
        """
        Get the tool list of the specified node (three-level priority)

        Priority:
        1. node level (workflow_id + node_id + agent_id)  ← highest priority
        2. Workflow level (workflow_id + agent_id, None node_id)
        3. Agent Default (agent_id only)                   ← Guaranteed

        Args:
            agent_id: Agent ID
            workflow_id: Workflow ID (optional)
            node_id: Node ID (optional)

        Returns:
            Tool ID list
        """
        logger.info(
            f"🔍 [BindingManager] get_tools_for_node: agent={agent_id}, "
            f"workflow={workflow_id}, node={node_id}"
        )

        # Priority 1: Node-specific bindings
        if workflow_id and node_id and self._db is not None:
            try:
                bindings = list(self._db.tool_agent_bindings.find(
                    {
                        "agent_id": agent_id,
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                        "is_active": {"$ne": False},
                    },
                    sort=[("priority", -1)]
                ))
                if bindings:
                    tool_ids = [b["tool_id"] for b in bindings]
                    logger.info(f"✅ [BindingManager] Node level tools ({node_id}): {tool_ids}")
                    return tool_ids
            except Exception as e:
                logger.warning(f"Query node level tool binding failed: {e}")

        # Priority 2: Workflow-specific bindings (no node_id)
        if workflow_id and self._db is not None:
            try:
                bindings = list(self._db.tool_agent_bindings.find(
                    {
                        "agent_id": agent_id,
                        "workflow_id": workflow_id,
                        "node_id": {"$in": [None, ""]},
                        "is_active": {"$ne": False},
                    },
                    sort=[("priority", -1)]
                ))
                if bindings:
                    tool_ids = [b["tool_id"] for b in bindings]
                    logger.info(f"✅ [BindingManager] Workflow level tools ({workflow_id}): {tool_ids}")
                    return tool_ids
            except Exception as e:
                logger.warning(f"Query workflow level tool binding failed: {e}")

        # Priority 3: Agent-level default
        logger.info(f"🔍 [BindingManager] Fall back to Agent default tool: {agent_id}")
        return self.get_tools_for_agent(agent_id)

    def bind_tool_for_node(
        self,
        agent_id: str,
        tool_id: str,
        workflow_id: str,
        node_id: str,
        priority: int = 10,
        is_active: bool = True,
    ) -> bool:
        """
        At the node level bind tools to Agent

        Args:
            agent_id: Agent ID
            tool_id: Tools ID
            workflow_id: Workflow ID
            node_id: node ID
            priority: Priority (the bigger the priority)
            is_active: Whether to activate (False indicates draft status)

        Returns:
            Is it successful?
        """
        if self._db is None:
            logger.error("The database is not connected and node-level tools cannot be bound.")
            return False

        try:
            self._db.tool_agent_bindings.update_one(
                {
                    "agent_id": agent_id,
                    "tool_id": tool_id,
                    "workflow_id": workflow_id,
                    "node_id": node_id,
                },
                {
                    "$set": {
                        "agent_id": agent_id,
                        "tool_id": tool_id,
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                        "priority": priority,
                        "is_active": is_active,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow().isoformat(),
                    },
                },
                upsert=True,
            )
            logger.info(
                f"✅ [BindingManager] Node-level tool binding successful: "
                f"{tool_id} → {agent_id} (workflow={workflow_id}, node={node_id})"
            )
            return True
        except Exception as e:
            logger.error(f"Node level binding tool failed: {e}")
            return False

    # ==================== Workflow level tool coverage ====================

    def get_tools_for_workflow_agent(
        self, workflow_id: str, agent_id: str
    ) -> List[str]:
        """
        Get the tool list for a specific Agent in the workflow

        Priority: Workflow level override > Agent Default binding

        Args:
            workflow_id: Workflow ID
            agent_id: Agent ID

        Returns:
            Tool ID list
        """
        # Check workflow level coverage first
        if self._db is not None:
            try:
                override = self._db.agent_workflow_bindings.find_one(
                    {"workflow_id": workflow_id, "agent_id": agent_id}
                )
                if override and override.get("tool_overrides"):
                    return override["tool_overrides"]
            except Exception as e:
                logger.warning(f"Failed to get workflow tool coverage: {e}")

        # Fallback to Agent default binding
        return self.get_tools_for_agent(agent_id)

    # ==================== Agent IO definition ====================

    def get_agent_io_definition(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the input and output definitions of the Agent

        Args:
            agent_id: Agent ID

        Returns:
            IO Definition dictionary, containing inputs, outputs, reads_from
        """
        cache_key = f"agent_io:{agent_id}"

        if agent_id in self._cache["agent_io"] and self._is_cache_valid(cache_key):
            return self._cache["agent_io"][agent_id]

        io_def = None

        # Load from database
        if self._db is not None:
            try:
                io_def = self._db.agent_io_definitions.find_one({"agent_id": agent_id})
            except Exception as e:
                logger.warning(f"Loading IO definition from database failed: {e}")

        # 🔥 Load from agent_configs (dynamic Agent released by Agent Workshop)
        # The inputs/outputs of the workshop Agent exist in agent_configs, but may not be synchronized to agent_io_definitions
        if io_def is None and self._db is not None:
            try:
                agent_doc = self._db.agent_configs.find_one(
                    {"agent_id": agent_id},
                    {"inputs": 1, "outputs": 1, "workflow_stage": 1, "output_field": 1},
                )
                if agent_doc and (agent_doc.get("inputs") or agent_doc.get("outputs")):
                    # 🔑 Critical fix: override the field name of outputs with output_field
                    # Agent The key actually written to state is output_field (such as "valuation_report") , 
                    # Instead of the name in outputs (such as "valuation_analysis_report") . 
                    # If the two are inconsistent, LangGraph will discard the Agent's output because the field names do not match.
                    output_field = agent_doc.get("output_field")
                    outputs = list(agent_doc.get("outputs") or [])
                    if output_field and outputs:
                        # Unify the names of all outputs to output_field
                        for out_item in outputs:
                            if isinstance(out_item, dict):
                                out_item["name"] = output_field
                    io_def = {
                        "agent_id": agent_id,
                        "inputs": agent_doc.get("inputs") or [],
                        "outputs": outputs,
                        "reads_from": [],
                    }
                    logger.info(f"Load IO definitions from agent_configs: {agent_id} (output_field={output_field})")
            except Exception as e:
                logger.warning(f"Failed to load IO definition from agent_configs: {e}")

        # Load from code configuration
        if io_def is None:
            io_def = self._get_default_io_definition(agent_id)

        # Update cache
        if io_def:
            self._cache["agent_io"][agent_id] = io_def
            self._cache_time[cache_key] = datetime.utcnow()

        return io_def

    def _get_default_io_definition(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get default IO definitions from code configuration"""
        from core.agents.config import BUILTIN_AGENTS

        if agent_id in BUILTIN_AGENTS:
            agent = BUILTIN_AGENTS[agent_id]
            # Convert Pydantic model to dictionary
            inputs = [inp.model_dump() for inp in agent.inputs] if hasattr(agent, 'inputs') else []
            outputs = [out.model_dump() for out in agent.outputs] if hasattr(agent, 'outputs') else []
            reads_from = agent.reads_from if hasattr(agent, 'reads_from') else []

            return {
                "agent_id": agent_id,
                "inputs": inputs,
                "outputs": outputs,
                "reads_from": reads_from,
            }
        return None

    def save_agent_io_definition(self, io_def: Dict[str, Any]) -> bool:
        """Save Agent IO definition to database"""
        if self._db is None:
            logger.error("Database not connected")
            return False

        agent_id = io_def.get("agent_id")
        if not agent_id:
            logger.error("IO definition missing agent_id")
            return False

        try:
            io_def["updated_at"] = datetime.utcnow().isoformat()
            self._db.agent_io_definitions.update_one(
                {"agent_id": agent_id},
                {
                    "$set": io_def,
                    "$setOnInsert": {"created_at": datetime.utcnow().isoformat()}
                },
                upsert=True
            )

            # clear cache
            if agent_id in self._cache["agent_io"]:
                del self._cache["agent_io"][agent_id]

            return True
        except Exception as e:
            logger.error(f"Failed to save IO definition: {e}")
            return False

    # ==================== Batch operations ====================

    def get_all_agent_io_definitions(self) -> List[Dict[str, Any]]:
        """Get the IO definitions of all Agents"""
        result = []

        if self._db is not None:
            try:
                result = list(self._db.agent_io_definitions.find({}))
            except Exception as e:
                logger.warning(f"Failed to get all IO definitions: {e}")

        # Merge definitions in code configuration
        from core.agents.config import BUILTIN_AGENTS
        db_agent_ids = {r["agent_id"] for r in result}

        for agent_id, agent in BUILTIN_AGENTS.items():
            if agent_id not in db_agent_ids:
                inputs = [inp.model_dump() for inp in agent.inputs] if hasattr(agent, 'inputs') else []
                outputs = [out.model_dump() for out in agent.outputs] if hasattr(agent, 'outputs') else []
                reads_from = agent.reads_from if hasattr(agent, 'reads_from') else []

                result.append({
                    "agent_id": agent_id,
                    "inputs": inputs,
                    "outputs": outputs,
                    "reads_from": reads_from,
                    "source": "builtin",
                })

        return result

