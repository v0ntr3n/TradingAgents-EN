# tradingagents/core/engine/agent_integrator.py
"""
Agent integrator

Bridging StockAnalysisEngine with existing Agent implementation:
- Create an Agent instance (using the existing create_xxx factory function)
- Convert AnalysisContext with AgentState
- Call the Agent and extract the results

All Agent configurations are uniformly read from BUILTIN_AGENTS in core/agents/config.py
"""

from typing import Any, Dict, Optional, Callable, Tuple

from tradingagents.utils.logging_init import get_logger

from .analysis_context import AnalysisContext
from .data_contract import DataLayer

logger = get_logger("default")


# ========================================
# Agent Factory function mapping (From module name to factory function name)
# This is the only mapping that needs to be maintained, configuration information is read from BUILTIN_AGENTS
# ========================================
AGENT_FACTORY_REGISTRY = {
    # Analyst - required (llm, toolkit)
    "market_analyst": ("tradingagents.agents", "create_market_analyst", "analyst"),
    "news_analyst": ("tradingagents.agents", "create_news_analyst", "analyst"),
    "sentiment_analyst": ("tradingagents.agents", "create_social_media_analyst", "analyst"),
    "social_analyst": ("tradingagents.agents", "create_social_media_analyst", "analyst"),  # Alias
    "fundamentals_analyst": ("tradingagents.agents", "create_fundamentals_analyst", "analyst"),
    # Researcher - required (llm, memory)
    "bull_researcher": ("tradingagents.agents.researchers.bull_researcher", "create_bull_researcher", "researcher"),
    "bear_researcher": ("tradingagents.agents.researchers.bear_researcher", "create_bear_researcher", "researcher"),
    "research_manager": ("tradingagents.agents.managers.research_manager", "create_research_manager", "manager"),
    # Trader - required (llm, memory)
    "trader": ("tradingagents.agents.trader.trader", "create_trader", "trader"),
    # Risk Control - Required (llm) or (llm, memory)
    "risky_analyst": ("tradingagents.agents.risk_mgmt.aggresive_debator", "create_risky_debator", "risk"),
    "safe_analyst": ("tradingagents.agents.risk_mgmt.conservative_debator", "create_safe_debator", "risk"),
    "neutral_analyst": ("tradingagents.agents.risk_mgmt.neutral_debator", "create_neutral_debator", "risk"),
    "risk_manager": ("tradingagents.agents.managers.risk_manager", "create_risk_manager", "manager"),
}


class AgentIntegrator:
    """
    Agent integrator

    Responsible for:
    1. Create and manage Agent instances
    2. Convert AnalysisContext <-> AgentState
    3. Execute Agent and extract results

    Configuration source:
    - Agent Metadata (output_field, etc.) is read from BUILTIN_AGENTS in core/agents/config.py
    - Factory function mapping is read from AGENT_FACTORY_REGISTRY
    """

    def __init__(self, llm: Any, toolkit: Any, memory_config: Dict[str, Any] = None):
        """
        Initialize Agent Integrator

        Args:
            llm: LLM Example
            toolkit: Toolset examples
            memory_config: Optional memory configuration dictionary, including various memory objects
        """
        self.llm = llm
        self.toolkit = toolkit
        self.memory_config = memory_config or {}
        self._agent_cache: Dict[str, Callable] = {}
        self._metadata_cache: Dict[str, Any] = {}

    def _get_agent_metadata(self, agent_id: str) -> Optional[Any]:
        """
        Get Agent metadata from BUILTIN_AGENTS configuration

        Args:
            agent_id: Agent ID

        Returns:
            AgentMetadata object or None
        """
        if agent_id in self._metadata_cache:
            return self._metadata_cache[agent_id]

        try:
            from core.agents.config import BUILTIN_AGENTS
            metadata = BUILTIN_AGENTS.get(agent_id)
            if metadata:
                self._metadata_cache[agent_id] = metadata
            return metadata
        except ImportError:
            logger.warning(f"⚠️ [AgentIntegrator] Unable to import BUILTIN_AGENTS configuration")
            return None

    def get_output_field(self, agent_id: str) -> Optional[str]:
        """
        Get the output field name of Agent

        Args:
            agent_id: Agent ID

        Returns:
            Output field names, such as "market_report"
        """
        metadata = self._get_agent_metadata(agent_id)
        if metadata and hasattr(metadata, 'output_field') and metadata.output_field:
            return metadata.output_field
        # Fallback: get from outputs list
        if metadata and hasattr(metadata, 'outputs') and metadata.outputs:
            return metadata.outputs[0].name
        return None
        
    def get_agent(self, agent_id: str) -> Optional[Callable]:
        """
        Get Agent node function

        Args:
            agent_id: Agent ID (Such as market_analyst, bull_researcher, trader Wait)

        Returns:
            Agent node function or None
        """
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]

        # Create Agent
        agent = self._create_agent(agent_id)
        if agent:
            self._agent_cache[agent_id] = agent
        return agent

    def _create_agent(self, agent_id: str) -> Optional[Callable]:
        """
        Create Agent instance

        Dynamically created based on configuration in AGENT_FACTORY_REGISTRY Agent
        """
        factory_info = AGENT_FACTORY_REGISTRY.get(agent_id)
        if not factory_info:
            # Try creating from extension registry
            return self._create_extension_agent(agent_id)

        module_path, factory_name, agent_type = factory_info

        try:
            # Dynamically import modules
            import importlib
            module = importlib.import_module(module_path)
            factory = getattr(module, factory_name, None)

            if factory:
                # Pass different parameters based on Agent type
                if agent_type == "analyst":
                    # analysts need (llm, toolkit)
                    agent = factory(self.llm, self.toolkit)
                elif agent_type in ("researcher", "manager", "trader"):
                    # Researchers, managers, traders need (llm, memory)
                    memory = self.memory_config.get(agent_id) or self.memory_config.get("default")
                    agent = factory(self.llm, memory)
                elif agent_type == "risk":
                    # Risk control may only require (llm) or (llm, memory)
                    memory = self.memory_config.get(agent_id)
                    if memory:
                        agent = factory(self.llm, memory)
                    else:
                        agent = factory(self.llm)
                else:
                    agent = factory(self.llm, self.toolkit)

                logger.debug(f"🔧 [AgentIntegrator] Create Agent: {agent_id} (Type: {agent_type})")
                return agent
        except Exception as e:
            logger.error(f"❌ [AgentIntegrator] Agent creation failed {agent_id}: {e}")
        return None

    def _create_extension_agent(self, agent_id: str) -> Optional[Callable]:
        """Create an extended Agent (from AgentRegistry or AnalystRegistry)"""
        try:
            from core.agents.analyst_registry import AnalystRegistry
            registry = AnalystRegistry()

            if registry.is_registered(agent_id):
                agent_class = registry.get_analyst_class(agent_id)
                if agent_class:
                    agent = agent_class()
                    if hasattr(agent, 'set_dependencies'):
                        agent.set_dependencies(self.llm, self.toolkit)
                    logger.debug(f"🔧 [AgentIntegrator] Create extension Agent: {agent_id}")
                    return lambda state, a=agent: a.execute(state)
        except Exception as e:
            logger.debug(f"⚠️ [AgentIntegrator] Extended Agent is not available {agent_id}: {e}")
        return None

    def context_to_state(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Convert AnalysisContext to AgentState format

        Args:
            context: Analyze context

        Returns:
            AgentState Compatible dictionary
        """
        ticker = context.get(DataLayer.CONTEXT, "ticker") or ""
        trade_date = context.get(DataLayer.CONTEXT, "trade_date") or ""

        # Build base state
        state = {
            "company_of_interest": ticker,
            "trade_date": trade_date,
            "messages": [],
            # Initialize tool call counter
            "market_tool_call_count": 0,
            "news_tool_call_count": 0,
            "sentiment_tool_call_count": 0,
            "fundamentals_tool_call_count": 0,
        }

        # Dynamically get all possible report fields from configuration
        try:
            from core.agents.config import BUILTIN_AGENTS
            for agent_id, metadata in BUILTIN_AGENTS.items():
                if hasattr(metadata, 'output_field') and metadata.output_field:
                    existing_report = context.get(DataLayer.REPORTS, metadata.output_field)
                    if existing_report:
                        state[metadata.output_field] = existing_report
        except ImportError:
            pass

        return state
    
    def run_agent_with_tools(
        self,
        agent: Callable,
        state: Dict[str, Any],
        agent_id: str,
        max_iterations: int = 3
    ) -> Dict[str, Any]:
        """
        Run the Agent and handle the tool invocation loop

        The existing Agent is designed for multiple rounds of iteration:
        1. Round 1: LLM returns tool call request
        2. Tool Execution: Execute the tool and add the results to messages
        3. Round 2: LLM generates report after seeing tool results

        Args:
            agent: Agent node function
            state: initial state
            agent_id: Agent ID
            max_iterations: Maximum number of iterations

        Returns:
            Final Agent execution result
        """
        from langchain_core.messages import ToolMessage

        current_state = state.copy()
        report_field = self.get_output_field(agent_id)

        for iteration in range(max_iterations):
            # execute Agent
            result = agent(current_state)

            # Check if the report has been generated
            if report_field and report_field in result and result[report_field]:
                logger.info(f"✅ [AgentIntegrator] {agent_id} No. {iteration + 1} wheel generation report")
                return result

            # Check if there is a tool call request
            messages = result.get("messages", [])
            if not messages:
                logger.warning(f"⚠️ [AgentIntegrator] {agent_id} Not returned messages")
                return result

            last_message = messages[-1] if messages else None
            if not last_message or not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                # No tool call, return directly
                logger.info(f"📝 [AgentIntegrator] {agent_id} No. {iteration + 1} Round No Tool Call")
                return result

            # Execute tool call
            logger.info(f"🔧 [AgentIntegrator] {agent_id} No. {iteration + 1} round execution tool call")
            tool_results = self._execute_tool_calls(last_message.tool_calls)

            # Update status: Added AI messages and tool results to history
            current_state["messages"] = current_state.get("messages", []) + [last_message] + tool_results

            # Update tool call counter
            counter_key = f"{agent_id.replace('_analyst', '')}_tool_call_count"
            current_state[counter_key] = current_state.get(counter_key, 0) + 1

        logger.warning(f"⚠️ [AgentIntegrator] {agent_id} Maximum number of iterations reached {max_iterations}")
        return result

    def _execute_tool_calls(self, tool_calls: list) -> list:
        """Performs a tool call and returns a list of ToolMessages"""
        from langchain_core.messages import ToolMessage

        tool_messages = []
        for tc in tool_calls:
            tool_name = tc.get('name', '')
            tool_args = tc.get('args', {})
            tool_id = tc.get('id', '')

            logger.info(f"🔧 [AgentIntegrator] Execution tool: {tool_name}")
            logger.debug(f"  parameters: {tool_args}")

            try:
                # Get tool functions from toolkit
                tool_func = self._get_tool_function(tool_name)
                if tool_func:
                    result = tool_func.invoke(tool_args)
                    tool_messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id,
                        name=tool_name
                    ))
                    logger.info(f"✅ [AgentIntegrator] Tools {tool_name} Successful execution, result length: {len(str(result))}")
                else:
                    error_msg = f"Tools {tool_name} does not exist"
                    logger.warning(f"⚠️ [AgentIntegrator] {error_msg}")
                    tool_messages.append(ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_id,
                        name=tool_name
                    ))
            except Exception as e:
                error_msg = f"Tool execution failed: {str(e)}"
                logger.error(f"❌ [AgentIntegrator] {error_msg}")
                tool_messages.append(ToolMessage(
                    content=error_msg,
                    tool_call_id=tool_id,
                    name=tool_name
                ))

        return tool_messages

    def _get_tool_function(self, tool_name: str):
        """Get tool functions from toolkit"""
        # Try getting it from a different toolset
        tool_sets = [
            self.toolkit.get_general_tools,
            self.toolkit.get_market_analysis_tools,
            self.toolkit.get_social_media_tools,
            self.toolkit.get_fundamental_tools,
            self.toolkit.get_us_tools,
            self.toolkit.get_china_tools,
        ]

        for get_tools in tool_sets:
            try:
                tools = get_tools()
                for tool in tools:
                    if hasattr(tool, 'name') and tool.name == tool_name:
                        return tool
            except Exception:
                continue
        return None

    def extract_report(
        self,
        agent_id: str,
        result: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract reports from Agent execution results

        Args:
            agent_id: Agent ID
            result: Agent Execution result

        Returns:
            (report_field, report_content) tuple
        """
        report_field = self.get_output_field(agent_id)
        
        # v2.0 agent Mapping of output fields to standard report fields
        v2_field_mapping = {
            # research_manager_v2: investment_advice -> investment_plan
            'investment_advice': 'investment_plan',
            # trader_v2: trade_plan -> trader_investment_plan  
            'trade_plan': 'trader_investment_plan',
            # risk_manager_v2: risk_assessment -> risk_management_decision
            'risk_assessment': 'risk_management_decision',
            # Other v2 field mappings
            'bull_report': 'bull_researcher',
            'bear_report': 'bear_researcher',
            'risky_opinion': 'risky_analyst',
            'safe_opinion': 'safe_analyst',
            'neutral_opinion': 'neutral_analyst',
        }
        
        if report_field and report_field in result:
            # If it is a v2 field, it is mapped to a standard field
            mapped_field = v2_field_mapping.get(report_field, report_field)
            return mapped_field, result[report_field]
        
        return report_field, None

