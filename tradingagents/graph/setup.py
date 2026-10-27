# TradingAgents/graph/setup.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import Toolkit

from .conditional_logic import ConditionalLogic

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        toolkit: Toolkit,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: ConditionalLogic,
        config: Dict[str, Any] = None,
        react_llm = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.toolkit = toolkit
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic
        self.config = config or {}
        self.react_llm = react_llm

        # Cache extension analyst registry
        self._extension_registry = None
        self._no_tool_analysts = set()

        # Analyst name mapping
        self._analyst_name_mapping = {
            "market": "Market",
            "social": "Social",
            "news": "News",
            "fundamentals": "Fundamentals",
            "index_analyst": "Index Analyst",
            "sector_analyst": "Sector Analyst",
        }

    def _get_analyst_display_name(self, analyst_type: str) -> str:
        """Get the analyst s display name"""
        return self._analyst_name_mapping.get(analyst_type, analyst_type.capitalize())

    def _get_extension_registry(self):
        """Get extended analyst registry (lazy loading)"""
        if self._extension_registry is None:
            try:
                from core.agents.analyst_registry import get_analyst_registry
                self._extension_registry = get_analyst_registry()
            except ImportError:
                logger.debug("📋 [DEBUG] core.agents.analyst_registry Not available, skip extension analyst")
                self._extension_registry = False
        return self._extension_registry if self._extension_registry else None

    def _load_extension_analysts(
        self,
        selected_analysts: list,
        analyst_nodes: dict,
        delete_nodes: dict
    ):
        """
        Dynamically load extension analysts from AnalystRegistry

        An extended analyst is an analyst who does not require a tool call loop,
        Such as SectorAnalyst, IndexAnalyst, etc.
        """
        registry = self._get_extension_registry()
        if not registry:
            return

        for analyst_id in selected_analysts:
            # Skip processed built-in analysts
            if analyst_id in analyst_nodes:
                continue

            # Check if it is in the registry
            if not registry.is_registered(analyst_id):
                continue

            # Get metadata
            metadata = registry.get_analyst_metadata(analyst_id)
            if not metadata:
                continue

            # Only handle analysts who do not require tool calls
            if metadata.requires_tools:
                continue

            # Create an analyst instance
            agent_class = registry.get_analyst_class(analyst_id)
            if agent_class:
                agent = agent_class()
                if hasattr(agent, 'set_dependencies'):
                    agent.set_dependencies(self.quick_thinking_llm, self.toolkit)
                analyst_nodes[analyst_id] = lambda state, a=agent: a.execute(state)
                delete_nodes[analyst_id] = create_msg_delete()
                self._no_tool_analysts.add(analyst_id)
                logger.info(f"📋 [Expand] Analyst loaded: {metadata.name}")

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "sector": Sector/Industry analyst (Sector Analyst)
                - "index": Index/Market analyst (Market Analyst)
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            # All LLMs now use standard market analysts (including Alibaba Bailian's OpenAI compatible adapter)
            llm_provider = self.config.get("llm_provider", "").lower()

            # Check whether the OpenAI compatible Alibaba Lian adapter is used
            using_dashscope_openai = (
                "dashscope" in llm_provider and
                hasattr(self.quick_thinking_llm, '__class__') and
                'OpenAI' in self.quick_thinking_llm.__class__.__name__
            )

            if using_dashscope_openai:
                logger.debug(f"📈 [DEBUG] Use standard market analysts (Alibaba Bailian OpenAI compatible mode)")
            elif "dashscope" in llm_provider or "Ali Bailian" in self.config.get("llm_provider", ""):
                logger.debug(f"📈 [DEBUG] Use standard market analysts (Alibaba Bailian native mode)")
            elif "deepseek" in llm_provider:
                logger.debug(f"📈 [DEBUG] Use Standard Market Analyst (DeepSeek)")
            else:
                logger.debug(f"📈 [DEBUG] Use standard market analysts")

            # All LLMs use standard analysts
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            # All LLMs now use standard fundamental analysts (including Alibaba Bailian's OpenAI compatible adapter)
            llm_provider = self.config.get("llm_provider", "").lower()

            # Check whether the OpenAI compatible Alibaba Lian adapter is used
            using_dashscope_openai = (
                "dashscope" in llm_provider and
                hasattr(self.quick_thinking_llm, '__class__') and
                'OpenAI' in self.quick_thinking_llm.__class__.__name__
            )

            if using_dashscope_openai:
                logger.debug(f"📊 [DEBUG] Use standard fundamental analysts (Alibaba Bailian OpenAI compatible mode)")
            elif "dashscope" in llm_provider or "Ali Bailian" in self.config.get("llm_provider", ""):
                logger.debug(f"📊 [DEBUG] Use standard fundamental analysts (Alibaba Bailian native mode)")
            elif "deepseek" in llm_provider:
                logger.debug(f"📊 [DEBUG] Using standard fundamental analysts (DeepSeek)")
            else:
                logger.debug(f"📊 [DEBUG] Use standard fundamental analysts")

            # All LLMs use standard analysts (including forced tool invocation mechanism)
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # 🆕 Market analysts and sector analysts use self-contained mode and do not require tool calls
        if "index_analyst" in selected_analysts:
            analyst_nodes["index_analyst"] = create_index_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["index_analyst"] = create_msg_delete()
            # 🔧 Mark as Toolless Call Analyst
            self._no_tool_analysts.add("index_analyst")
            logger.info("📋 Add market analyst (No tool invocation mode)")

        if "sector_analyst" in selected_analysts:
            analyst_nodes["sector_analyst"] = create_sector_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["sector_analyst"] = create_msg_delete()
            # 🔧 Mark as Toolless Call Analyst
            self._no_tool_analysts.add("sector_analyst")
            logger.info("📋 Add sector analyst (No tool invocation mode)")

        # 🆕 Dynamically load extension analysts from AnalystRegistry (no tool call type)
        self._load_extension_analysts(
            selected_analysts, analyst_nodes, delete_nodes
        )

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        risky_analyst = create_risky_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        safe_analyst = create_safe_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            display_name = self._get_analyst_display_name(analyst_type)
            workflow.add_node(f"{display_name} Analyst", node)
            workflow.add_node(
                f"Msg Clear {display_name}", delete_nodes[analyst_type]
            )
            # Add tool nodes only for analysts who need tools (extended analysts are in _no_tool_analysts)
            if analyst_type not in self._no_tool_analysts:
                workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        first_display_name = self._get_analyst_display_name(first_analyst)
        workflow.add_edge(START, f"{first_display_name} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            display_name = self._get_analyst_display_name(analyst_type)
            current_analyst = f"{display_name} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {display_name}"

            # Analysts without tool calls are connected directly to the next step (extended analysts are in _no_tool_analysts)
            if analyst_type in self._no_tool_analysts:
                # Connect directly from analysts to message cleaning nodes
                workflow.add_edge(current_analyst, current_clear)
            else:
                # Analysts with tool calls use conditional edges
                workflow.add_conditional_edges(
                    current_analyst,
                    getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                    [current_tools, current_clear],
                )
                workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst_type = selected_analysts[i+1]
                next_display_name = self._get_analyst_display_name(next_analyst_type)
                next_analyst = f"{next_display_name} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", END)

        # Compile and return
        return workflow.compile()
