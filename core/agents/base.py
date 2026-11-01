"""
Agent base class

All agents should inherit this base class
v2.0 New: Standardized tool call loop processing
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from app.utils.api_key_utils import truncate_api_key

try:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
    from langchain_core.tools import BaseTool
except ModuleNotFoundError:
    BaseChatModel = Any  # type: ignore

    class _FallbackMessage:
        def __init__(self, content: str = "", **kwargs: Any):
            self.content = content
            for k, v in kwargs.items():
                setattr(self, k, v)

    AIMessage = _FallbackMessage  # type: ignore
    ToolMessage = _FallbackMessage  # type: ignore
    HumanMessage = _FallbackMessage  # type: ignore
    BaseTool = Any  # type: ignore

from .config import AgentMetadata, AgentConfig

logger = logging.getLogger(__name__)
GENERIC_REPORT_FALLBACK = "Tool execution or model generation has not been completed, and the current conclusions still need to be verified."


def is_retryable_llm_error(error_msg: str) -> bool:
    normalized_error = str(error_msg or "").lower()
    return (
        "choices" in normalized_error or
        "null value" in normalized_error or
        "connection" in normalized_error or
        "timeout" in normalized_error or
        "timed out" in normalized_error or
        "rate_limit" in normalized_error or  # 🔧 Underline format
        "rate limit" in normalized_error or
        "429" in normalized_error or
        "limit" in normalized_error or  # 🔧 Keep everything in mind
        "503" in normalized_error or
        "502" in normalized_error or
        "500" in normalized_error
    )

# Default configuration
DEFAULT_MAX_TOOL_ITERATIONS = 3  # Maximum number of tool invocation iterations

# External fact memory injection whitelist: only debate session (optimistic/cautious scenario researcher) and risk assessment session
#  (Risk manager) consumes the memory_facts_summary injected by the analysis engine, and other links are not affected.
_MEMORY_AWARE_AGENTS = {"bull_researcher_v2", "bear_researcher_v2", "risk_manager_v2"}


class BaseAgent(ABC):
    """
    Agent base class

    Provide unified interface and common functions:
    - LLM call
    - Tool management (supports dynamic binding)
    - prompt word rendering
    - Status management
    - logging

    v2.0 new features:
    - Supports dynamic loading of tools from configuration or database
    - Support LangChain tool integration
    - Support automatic loading of metadata
    """

    # Metadata that subclasses need to define
    metadata: AgentMetadata = None

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        llm: Optional[BaseChatModel] = None,
        tool_ids: Optional[List[str]] = None
    ):
        """
        initialization Agent

        Args:
            config: Agent Configuration (legacy compatible)
            llm: LangChain LLM Example (new version)
            tool_ids: Tool ID list (new version, optional)
        """
        logger.info(f"[BaseAgent] 🚀 Start initialization Agent")
        # 🔥 Exclude llm_provider and llm_model as these should not be in the Agent configuration
        config_dict_log = config.model_dump(exclude={'llm_provider', 'llm_model'}) if config else None
        logger.info(f"   - config: {config_dict_log}")
        logger.info(f"   - llm: {type(llm).__name__ if llm else 'None'}")
        logger.info(f"   - tool_ids: {tool_ids}")

        self.config = config or AgentConfig()
        self._llm_client = None
        self._llm = llm  # LangChain LLM (new version)
        self._tools: Dict[str, Callable] = {}  # Old version tool dictionary
        self._langchain_tools: List[BaseTool] = []  # List of new LangChain tools
        self._prompt_template: Optional[str] = None
        self._execution_recorder = None  # 🔑 Execution trace recorder (automatically bound by start_execution_trace)

        # v2.0: Dynamic loading tool
        if tool_ids is not None:
            logger.info(f"[BaseAgent] 🔧 Start loading tools: {tool_ids}")
            self._load_tools_v2(tool_ids)
            logger.info(f"[BaseAgent] ✅ Tool loading completed, number of tools: {len(self._langchain_tools)}")
        else:
            logger.info(f"[BaseAgent] ⚠️ tool_ids not provided, tool loading skipped")

        logger.info(f"[BaseAgent] ✅ Agent Initialization completed")
        logger.info(f"   - Agent ID: {self.agent_id if hasattr(self, 'agent_id') else 'N/A'}")
        logger.info(f"   - _llm: {type(self._llm).__name__ if self._llm else 'None'}")
        logger.info(f"   - _langchain_tools Quantity: {len(self._langchain_tools)}")
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        """Get agent metadata"""
        if cls.metadata is None:
            raise NotImplementedError(f"{cls.__name__} must be defined metadata")
        return cls.metadata

    def set_dependencies(self, llm: BaseChatModel, toolkit: Optional[Any] = None):
        """
        Set dependencies (LLM and tools)

        Called by WorkflowEngine to inject LLM and tool dependencies

        Args:
            llm: Language model example
            toolkit: Toolset (optional)
        """
        self._llm = llm
        if toolkit and hasattr(toolkit, 'tools'):
            # If toolkit is provided, tools can be optionally added
            # But does not cover existing tools
            pass
        logger.info(f"✅ Agent {self.agent_id} LLM dependency has been set")

    def initialize(self) -> None:
        """
        Initialize the agent
        
        Subclasses can override this method for additional initialization
        """
        logger.info(f"[BaseAgent.initialize] 🔧 Start initialization Agent: {self.agent_id}")
        logger.info(f"   - _llm value: {type(self._llm).__name__ if self._llm else 'None'}")
        logger.info(f"   - _llm_client value: {type(self._llm_client).__name__ if self._llm_client else 'None'}")
        
        # 🔥 If llm has been passed in, there is no need to create _llm_client
        # LLM provider and model should be specified by the analysis process, not the Agent configuration
        if self._llm is None:
            logger.info(
                f"Agent {self.agent_id} The _llm is None (dry-run or no LLM passed in), an LLM client will be attempted to be created from the configuration."
                f"This should not normally happen as the LLM should be passed in by the WorkflowBuilder when creating the Agent."
            )
            self._setup_llm()
        else:
            logger.info(f"✅ Agent {self.agent_id} LLM instance passed in: {type(self._llm).__name__}")
            # 🔍 Verify that the LLM instance has API key
            if hasattr(self._llm, 'openai_api_key'):
                api_key_val = self._llm.openai_api_key
                if hasattr(api_key_val, 'get_secret_value'):
                    api_key_val = api_key_val.get_secret_value()
                logger.info(f"   - LLM API Key: {'valuable' if api_key_val else 'empty'}")
            elif hasattr(self._llm, 'api_key'):
                api_key_val = self._llm.api_key
                if hasattr(api_key_val, 'get_secret_value'):
                    api_key_val = api_key_val.get_secret_value()
                logger.info(f"   - LLM API Key: {'valuable' if api_key_val else 'empty'}")
        
        logger.info(f"[BaseAgent.initialize] 🔧 Start setting up tools...")
        self._setup_tools()
        logger.info(f"[BaseAgent.initialize] 🔧 Start setting prompt words...")
        self._setup_prompt()
        logger.info(f"[BaseAgent.initialize] ✅ Agent {self.agent_id} Initialization completed")
    
    def _setup_llm(self) -> None:
        """
        Set up the LLM client (only called if llm is not passed in)
        
        ⚠️ Note: This method reads the API key from an environment variable, which generally shouldn t happen.
        The correct approach is to pass in the configured LLM instance when creating the Agent.
        """
        from ..llm import UnifiedLLMClient
        
        # 🔥 If there are no llm_provider and llm_model in config, use the default values
        # But this shouldn't happen because the LLM should be passed in by the analysis process
        provider = getattr(self.config, 'llm_provider', None) or "dashscope"
        model = getattr(self.config, 'llm_model', None)
        
        if not model:
            logger.info(
                f"Agent {self.agent_id} There is no llm_model in the config, skipping the internal LLM client creation;"
                f"LLM It will be passed in by the analysis process (WorkflowBuilder) when creating the Agent."
            )
            return
        
        logger.warning(
            f"⚠️ Agent {self.agent_id} Reading API key from environment variable to create LLM client."
            f"This should not normally happen as the LLM should be passed in by the WorkflowBuilder when creating the Agent."
            f"Provider: {provider}, Model: {model}"
        )
        
        self._llm_client = UnifiedLLMClient.from_provider(
            provider=provider,
            model=model,
            temperature=self.config.temperature,
            timeout=self.config.timeout,
        )
    
    def _setup_tools(self) -> None:
        """
        Setup tool

        Subclasses should override this method to register available tools
        """
        pass

    def _load_tools_v2(self, tool_ids: List[str]) -> None:
        """
        v2.0: Load LangChain tools from a list of tool IDs

        Args:
            tool_ids: Tool ID list
        """
        from core.tools.registry import ToolRegistry

        registry = ToolRegistry()
        self._langchain_tools = []

        logger.info(f"🔧 [Agent {self.agent_id}] Start loading tools: {tool_ids}")

        for tool_id in tool_ids:
            # 🔍 Detailed diagnostics: Check if the tool is in the registry
            has_metadata = registry.has_tool(tool_id)
            has_function = registry.get_function(tool_id) is not None
            
            if not has_metadata:
                logger.warning(
                    f"⚠️ [Agent {self.agent_id}] Tool not found: {tool_id}\n"
                    f"   - metadata: ❌ does not exist\n"
                    f"   - function: {'✅ exist' if has_function else '❌ does not exist'}\n"
                    f"   💡 Possible reasons: Tool module not loaded or tool ID is wrong"
                )
            elif not has_function:
                logger.warning(
                    f"⚠️ [Agent {self.agent_id}] Tool not found: {tool_id}\n"
                    f"   - metadata: ✅ exist\n"
                    f"   - function: ❌ does not exist\n"
                    f"   💡 Possible reasons: The tool function is not registered, please check whether the tool module is imported correctly."
                )
                # 🔧 Try reloading the tools module
                try:
                    from core.tools.loader import get_tool_loader
                    loader = get_tool_loader()
                    if loader.load_tool(tool_id):
                        logger.info(f"🔄 [Agent {self.agent_id}] Tools module reloaded: {tool_id}")
                        # Try again to get
                        tool = registry.get_langchain_tool(tool_id)
                        if tool:
                            self._langchain_tools.append(tool)
                            logger.info(f"✅ [Agent {self.agent_id}] Successful acquisition of tools after reloading: {tool_id}")
                            continue
                except Exception as e:
                    logger.debug(f"Failed to reload tool {tool_id}: {e}")
            else:
                tool = registry.get_langchain_tool(tool_id)
                if tool:
                    self._langchain_tools.append(tool)
                    logger.info(f"✅ [Agent {self.agent_id}] Tool loaded successfully: {tool_id}")
                else:
                    logger.warning(
                        f"⚠️ [Agent {self.agent_id}] Tool metadata and functions exist, but LangChain tool cannot be created: {tool_id}\n"
                        f"   - metadata: ✅ exist\n"
                        f"   - function: ✅ exist\n"
                        f"   💡 Possible reasons: Function format is incorrect or LangChain tool creation failed"
                    )

        logger.info(f"🔧 [Agent {self.agent_id}] Tool loading completed: {len(self._langchain_tools)}/{len(tool_ids)} tools")

    def _load_bound_knowledge_skills(self, agent_name: str) -> Optional[str]:
        """Load the knowledge type Skill bound to the current Agent and return the prompt word block

        knowledge Type Skill has no implementation and is not registered as a callable tool.
        Instead, it is injected into the Agent s prompt words as context.

        Args:
            agent_name: Agent Name (such as market_analyst_v2)

        Returns:
            Formatted knowledge block text, returned if none None
        """
        try:
            from core.config.binding_manager import BindingManager
            from app.core.database import get_mongo_db_sync

            # Get all bindings to the current Agent tool_ids
            binding_manager = BindingManager()
            tool_ids = binding_manager.get_tools_for_agent(agent_name)
            if not tool_ids:
                return None

            # Query knowledge type Skill from MongoDB (no implementation field)
            db = get_mongo_db_sync()
            if db is None:
                return None

            # tool_ids The format in is skill_name (underlined) and needs to be converted back to hyphenated name
            # Skill When registering tool_id = name.replace("-", "_"), So here is the reverse conversion
            possible_names = []
            for tid in tool_ids:
                # Try both the original tool_id and the converted one name
                possible_names.append(tid)
                possible_names.append(tid.replace("_", "-"))

            knowledge_skills = list(db["skills"].find({
                "name": {"$in": possible_names},
                "implementation": None,  # knowledge Type
                "enabled": True,
            }))

            if not knowledge_skills:
                return None

            # building blocks of knowledge
            parts = ["\n\n## 📚 Available knowledge base\n"]
            for skill in knowledge_skills:
                name = skill.get("name", "")
                description = skill.get("description", "")
                instructions = skill.get("instructions", "")
                parts.append(f"\n### {name}\n")
                if description:
                    parts.append(f"{description}\n")
                if instructions:
                    parts.append(f"\n{instructions}\n")

            return "".join(parts)
        except Exception as e:
            logger.warning(f"⚠️ Failed to load knowledge-based Skill: {e}")
            return None

    def load_tools_from_config(self) -> List[str]:
        """
        v2.0: Load tool list from configuration

        priority:
        1. Database configuration (BindingManager)
        2. Default tools in metadata
        3. empty list

        Returns:
            Tool ID list
        """
        try:
            # Prioritize loading from database configuration
            from core.config.binding_manager import BindingManager
            tool_ids = BindingManager().get_tools_for_agent(self.agent_id)

            if tool_ids:
                logger.info(f"📦 Load from database {len(tool_ids)} tools: {tool_ids}")
                return tool_ids

            # Downgrade: Use default tools from metadata
            metadata = self.get_metadata()
            if hasattr(metadata, 'default_tools') and metadata.default_tools:
                logger.info(f"📦 Load from metadata {len(metadata.default_tools)} default tool")
                return metadata.default_tools

            if hasattr(metadata, 'tools') and metadata.tools:
                logger.info(f"📦 Load from metadata {len(metadata.tools)} tools")
                return metadata.tools

            logger.warning(f"⚠️ Agent '{self.agent_id}' No configuration tool")
            return []

        except Exception as e:
            logger.error(f"❌ Failed to load tool configuration: {e}")
            return []
    
    def _setup_prompt(self) -> None:
        """
        Set prompt word template
        
        Subclasses should override this method to set the prompt word
        """
        pass

    def _apply_global_trading_advice_guard(self, system_prompt: str) -> str:
        """
        Global transaction recommendation compliance protection: add compliance constraints at the end of the system prompt word,
        Avoid LLM outputting illegal trade proposal terms (e.g."Buy/Sell/Target Price"etc.).

        Subclasses can override this method to implement stricter protection logic.
        The default implementation appends a compliance prompt to ensure that the output uses compliant terms.
        """
        if not system_prompt:
            return system_prompt
        guard = (
            "\n\n [Compliance protection·Must comply]\n"
            '1. It is prohibited to output specific buying and selling instructions (such as"buy""sell""Add to position""Reduce positions""hold""Clearance") , '
            "Use consistent terms: optimistic/cautious/neutral to express the tendency of research conclusions.\n"
            '2. It is forbidden to give a specific target price or risk attention price, and it can be output"price analysis range"and label uncertainty.\n'
            "3. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.\n"
            "4. All conclusions must be based on obtained data and no fabricated data or indicators are allowed.\n"
        )
        return system_prompt + guard

    def _extract_common_params(self, state: Dict[str, Any]) -> tuple:
        """🔑 Unified extraction of ticker and analysis_date, including multi-field compatibility and cover-up logic.

        All subcategories (AnalystAgent / TraderAgent / ResearcherAgent / ManagerAgent
        and each adapter) should call this method to avoid repeated implementation of parameter extraction logic.

        Compatible scenarios:
        - ticker：state["ticker"] → state["company_of_interest"]
                  → state["trade_info"]["code"] (Transaction review)
                  → state["position_info"]["code"] (Position analysis)
        - analysis_date：state["analysis_date"] → state["trade_date"]
                         → state["end_date"] → Current date

        Args:
            state: Workflow status dictionary

        Returns:
            (ticker, analysis_date) tuple.
            analysis_date Guaranteed to be non-empty (revealing the current date);
            ticker May be None (it is up to the caller whether to throw an exception).
        """
        # 1. Extract ticker (compatible with multiple field names) + Scene details)
        ticker = state.get("ticker") or state.get("company_of_interest")

        # Support transaction review scenario: extracted from trade_info code
        if not ticker and "trade_info" in state:
            trade_info = state.get("trade_info", {})
            if isinstance(trade_info, dict):
                ticker = trade_info.get("code")

        # Support position analysis scenario: extracted from position_info code
        if not ticker and "position_info" in state:
            position_info = state.get("position_info", {})
            if isinstance(position_info, dict):
                ticker = position_info.get("code")

        # 2. Extract analysis_date (compatible with multiple field names)
        analysis_date = (
            state.get("analysis_date")
            or state.get("trade_date")
            or state.get("end_date")
        )

        # Bottom line: if analysis_date is empty, use the current date
        if not analysis_date:
            from datetime import datetime
            analysis_date = datetime.now().strftime("%Y-%m-%d")
            logger.info(f"[{self.agent_id}] analysis_date If empty, use the current date: {analysis_date}")

        return ticker, analysis_date

    def _record_llm_response_to_trace(self, response: Any, llm_duration_ms: Optional[int] = None) -> None:
        """🔑 Automatically record LLM responses to the execution trace (if recorder is bound)

        Called internally by invoke_with_tools to ensure that all adapters inheriting BaseAgent
         (Such as fundamentals_analyst_v2, index_analyst_v2, etc.) can automatically record Token usage.
        There is no need to manually call record_llm_response in each adapter s execute method.
        """
        recorder = getattr(self, '_execution_recorder', None)
        if recorder and response is not None:
            try:
                recorder.record_llm_response(response, llm_duration_ms=llm_duration_ms)
            except Exception as e:
                logger.debug(f"[{self.agent_id}] Automatically log LLM response failures (does not affect the agent): {e}")

    def _invoke_llm_with_trace(self, messages: list) -> Any:
        """🔑 encapsulation self._llm.invoke(messages), Automatically record Prompt and LLM responses to execution traces

        Called by Agents (such as risk analysts, research integrators) who do not use invoke_with_tools,
        Alternative to calling directly self._llm.invoke(messages). 
        """
        # record Prompt
        _recorder = getattr(self, '_execution_recorder', None)
        if _recorder:
            try:
                _sys_prompt = ""
                _usr_prompt = ""
                for _msg in messages:
                    _content = getattr(_msg, 'content', '') or ''
                    if type(_msg).__name__ == 'SystemMessage':
                        _sys_prompt = _content
                    elif type(_msg).__name__ == 'HumanMessage':
                        if not _usr_prompt:
                            _usr_prompt = _content
                if _sys_prompt or _usr_prompt:
                    _recorder.record_prompts(_sys_prompt, _usr_prompt)
            except Exception:
                pass

        # call LLM
        _start = time.time()
        response = self._llm.invoke(messages)
        _duration_ms = int((time.time() - _start) * 1000)

        # Logging LLM response
        self._record_llm_response_to_trace(response, llm_duration_ms=_duration_ms)
        return response

    def register_tool(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> None:
        """Registration tool"""
        tool_def = self._llm_client.register_tool(func, name, description)
        tool_name = tool_def["function"]["name"]
        self._tools[tool_name] = func
    
    @abstractmethod
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent logic
        
        Args:
            state: current state dictionary
            
        Returns:
            Updated status dictionary
        """
        pass
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Make the agent callable, for use with LangGraph nodes"""
        return self.execute(state)

    def invoke_agent(
        self,
        target_agent_id: str,
        state: Dict[str, Any],
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compatible with old delegation interfaces: reuse the current LLM to dynamically create and execute target Agents."""
        from .factory import AgentFactory

        normalized_target = str(target_agent_id or "").strip()
        if not normalized_target:
            raise ValueError("target_agent_id cannot be empty")

        logger.info(f"[BaseAgent] {self.agent_id} Start calling sub Agent: {normalized_target}")

        factory = AgentFactory()
        if self._llm is not None:
            target_agent = factory.create_with_dynamic_tools(
                normalized_target,
                llm=self._llm,
            )
        else:
            logger.warning(
                f"[BaseAgent] {self.agent_id} Not holding LangChain LLM,"
                f"will be downgraded to not explicitly injecting the llm creation sub Agent: {normalized_target}"
            )
            target_agent = factory.create(normalized_target)

        delegated_state = {
            **(state or {}),
            **(payload or {}),
        }
        if metadata:
            delegated_state["delegation_metadata"] = metadata

        # 🔑 Unified execution trace buried points: delegate calls also need to record traces
        _delegate_recorder = None
        from core.agents.execution_trace_recorder import start_execution_trace, is_trace_enabled
        if is_trace_enabled():
            try:
                _delegate_recorder = start_execution_trace(target_agent, delegated_state)
                target_agent._last_trace_id = _delegate_recorder.trace_id
            except Exception as e:
                logger.warning(f"⚠️ [{normalized_target}] Failed to start trajectory collection (does not affect agent): {e}")

        try:
            # P1: Record Prompt (if the child agent exposes the prompt word construction method)
            if _delegate_recorder:
                try:
                    _delegate_recorder.record_inputs({"ticker": delegated_state.get("ticker"), "analysis_date": delegated_state.get("analysis_date")})
                except Exception:
                    pass

            result = target_agent.execute(delegated_state)
            logger.info(f"[BaseAgent] {self.agent_id} Sub-Agent call completed: {normalized_target}")

            # P1: Record parsed output
            if _delegate_recorder:
                try:
                    _delegate_recorder.record_parsed_output(result)
                except Exception:
                    pass

            return result
        except Exception as e:
            if _delegate_recorder:
                try:
                    _delegate_recorder.record_error(e)
                except Exception:
                    pass
            raise
        finally:
            if _delegate_recorder:
                try:
                    _delegate_recorder.finish()
                except Exception:
                    pass
    
    def render_prompt(
        self,
        template: Optional[str] = None,
        **variables
    ) -> str:
        """
        Render prompt word template
        
        Args:
            template: prompt word template (If None, use the default template)
            **variables: Template variables
            
        Returns:
            Rendered prompt word
        """
        tpl = template or self._prompt_template
        if tpl is None:
            return ""
        
        # Merge variables in configuration
        all_vars = {**self.config.prompt_variables, **variables}
        
        try:
            return tpl.format(**all_vars)
        except KeyError as e:
            # Log warnings but don't interrupt
            return tpl
    
    def log(self, message: str, level: str = "info") -> None:
        """logging"""
        # TODO: Integrated unified logging system
        prefix = f"[{self.get_metadata().name}]"
        print(f"{prefix} {message}")
    
    @property
    def agent_id(self) -> str:
        """agent ID"""
        return self.get_metadata().id
    
    @property
    def agent_name(self) -> str:
        """Agent name"""
        return self.get_metadata().name
    
    @property
    def llm(self):
        """LLM Client (old version) or LangChain LLM (new version)"""
        return self._llm or self._llm_client

    @property
    def tools(self) -> List[BaseTool]:
        """v2.0: Get a list of LangChain tools"""
        return self._langchain_tools

    @property
    def tool_names(self) -> List[str]:
        """v2.0: Get a list of tool names"""
        return [tool.name for tool in self._langchain_tools]

    # ========== v2.0: Standardized tool call loop processing ==========

    def invoke_with_tools(
        self,
        messages: List,
        analysis_prompt: Optional[str] = None,
        max_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS
    ) -> str:
        """
        v2.0: Standardized tool call loop processing (self-contained mode)

        This is recommended LLM + Tool calling method, all Agents should use this method.

        process:
        1. Call LLM (binding tool)
        2. If LLM returns tool_calls:
           a. Execute all tools inside the Agent
           b. Add tool results to message history
           c. Call LLM again (without binding the tool) to generate the final report
        3. Return to final report content

        Args:
            messages: Message list (contains SystemMessage and HumanMessage)
            analysis_prompt: Analysis prompt word after tool execution (optional)
            max_iterations: Maximum number of tool call iterations (to prevent infinite loops)

        Returns:
            str: Final analysis report content
        """
        if not self._llm:
            raise ValueError("LLM Not configured, tool call cannot be executed")

        current_messages = list(messages)
        # 🆕 Reset tool invocation summary collector (independent statistics for each invoke_with_tools)
        self._tool_call_summaries_collected = []
        # 🔑 LLM Elapsed time (milliseconds) for _record_llm_response_to_trace recording
        _llm_ms: Optional[int] = None

        # 🔑 Automatically record Prompt to execution trace (extract SystemMessage and HumanMessage from messages)
        _recorder = getattr(self, '_execution_recorder', None)
        if _recorder:
            try:
                _sys_prompt = ""
                _usr_prompt = ""
                for _msg in current_messages:
                    _content = getattr(_msg, 'content', '') or ''
                    if type(_msg).__name__ == 'SystemMessage':
                        _sys_prompt = _content
                    elif type(_msg).__name__ == 'HumanMessage':
                        if not _usr_prompt:  # Only take the first one HumanMessage
                            _usr_prompt = _content
                if _sys_prompt or _usr_prompt:
                    _recorder.record_prompts(_sys_prompt, _usr_prompt)
            except Exception:
                pass

        logger.info(f"🚀 [{self.agent_id}] Start tool call loop, maximum number of iterations: {max_iterations}")
        logger.info(f"🔧 [{self.agent_id}] Number of tools available: {len(self._langchain_tools) if self._langchain_tools else 0}")
        if self._langchain_tools:
            logger.info(f"🔧 [{self.agent_id}] Tool list: {[tool.name for tool in self._langchain_tools]}")

        for iteration in range(max_iterations):
            logger.info(f"🔄 [{self.agent_id}] Tool call iteration {iteration + 1}/{max_iterations}")

            # Bind the tool and call LLM
            if self._langchain_tools:
                llm_with_tools = self._llm.bind_tools(self._langchain_tools)
                logger.info(f"🔗 [{self.agent_id}] LLM Bound {len(self._langchain_tools)} tools")
            else:
                llm_with_tools = self._llm
                logger.info(f"🔗 [{self.agent_id}] LLM Unbound tools")

            logger.info(f"💬 [{self.agent_id}] Call LLM, number of messages: {len(current_messages)}")

            # 🔍 Print LLM configuration information (including the first 5 digits of the API Key)
            logger.info(f"=" * 100)
            logger.info(f"🔍 [{self.agent_id}] LLM Configuration information:")
            logger.info(f"=" * 100)
            if hasattr(self._llm, 'model_name'):
                logger.info(f"   model: {self._llm.model_name}")
            if hasattr(self._llm, 'openai_api_base') or hasattr(self._llm, 'base_url'):
                base_url = getattr(self._llm, 'openai_api_base', None) or getattr(self._llm, 'base_url', None)
                logger.info(f"   API Base URL: {base_url}")
            # 🔍 Try multiple ways to obtain the real API Key (bypass desensitization)
            api_key = None

            # method 1: Get from client object
            if hasattr(self._llm, 'client') and hasattr(self._llm.client, 'api_key'):
                api_key = self._llm.client.api_key
                logger.info(f"   API Key Source: client.api_key")

            # method 2: Get (private property) from _client object
            elif hasattr(self._llm, '_client') and hasattr(self._llm._client, 'api_key'):
                api_key = self._llm._client.api_key
                logger.info(f"   API Key Source: _client.api_key")

            # method 3: Get from environment variables (for comparison)
            else:
                import os
                env_api_key = os.getenv("DASHSCOPE_API_KEY")
                if env_api_key:
                    logger.info(f"   API Key Source: environment variables DASHSCOPE_API_KEY")
                    logger.info(f"   environment variables API Key: {truncate_api_key(env_api_key)}")

                # Try to get from attribute (may be desensitized)
                api_key = getattr(self._llm, 'openai_api_key', None) or getattr(self._llm, 'api_key', None)
                if api_key and str(api_key) != "**********":
                    logger.info(f"   API Key Source: LLM Properties")
                else:
                    logger.info(f"   API Key Source: LLM Properties (desensitized)")

            # Print API Key information (full value, for debugging)
            if api_key:
                api_key_str = str(api_key)
                if api_key_str == "**********":
                    logger.info(f"   API Key: Desensitized (unable to obtain true value)")
                else:
                    logger.info(f"   API Key: valuable")
                    #logger.info(f"   API Key: {truncate_api_key(api_key_str)}")
                    logger.info(f"   API Key length: {len(api_key_str)}")
            else:
                logger.info(f"   API Key: empty")
            if hasattr(self._llm, 'temperature'):
                logger.info(f"   Temperature: {self._llm.temperature}")
            if hasattr(self._llm, 'max_tokens'):
                logger.info(f"   Max Tokens: {self._llm.max_tokens}")
            if hasattr(self._llm, 'timeout') or hasattr(self._llm, 'request_timeout'):
                timeout = getattr(self._llm, 'timeout', None) or getattr(self._llm, 'request_timeout', None)
                logger.info(f"   Timeout: {timeout}")
            logger.info(f"=" * 100)

            # Print each message in detail
            logger.info(f"=" * 100)
            logger.info(f"📋 [{self.agent_id}] No. {iteration + 1} LLM calls - message details:")
            logger.info(f"=" * 100)
            for idx, msg in enumerate(current_messages):
                msg_type = type(msg).__name__
                if hasattr(msg, 'content'):
                    # 🔥 For SystemMessage, print the complete content to verify that the template is correct
                    if msg_type == "SystemMessage":
                        logger.info(f"  [{idx+1}] {msg_type}:")
                        logger.info(f"      content length: {len(msg.content)} character")
                        logger.info(f"      🔍 full content: {msg.content}")
                    else:
                        content_preview = msg.content[:200] if len(msg.content) > 200 else msg.content
                        logger.info(f"  [{idx+1}] {msg_type}:")
                        logger.info(f"      content length: {len(msg.content)} character")
                        logger.info(f"      Content preview: {content_preview}")
                elif hasattr(msg, 'tool_calls'):
                    logger.info(f"  [{idx+1}] {msg_type}:")
                    logger.info(f"      Number of tool calls: {len(msg.tool_calls)}")
                    for tc_idx, tc in enumerate(msg.tool_calls):
                        logger.info(f"        [{tc_idx+1}] {tc.get('name', 'unknown')}: {tc.get('args', {})}")
                else:
                    logger.info(f"  [{idx+1}] {msg_type}: {str(msg)[:200]}")
            logger.info(f"=" * 100)

            # 🔥 Add a retry mechanism (use max_retries configured by agent, default 3 times)
            max_retries = getattr(self.config, 'max_retries', 3)
            retry_count = 0
            last_error = None
            
            while retry_count <= max_retries:
                try:
                    if retry_count > 0:
                        # Wait while retrying (exponential backoff)
                        wait_time = min(2 ** retry_count, 10)  # Wait up to 10 seconds
                        logger.info(f"⏳ [{self.agent_id}] wait {wait_time} Retry after seconds (No. {retry_count}/{max_retries} times)...")
                        time.sleep(wait_time)
                        logger.info(f"🔄 [{self.agent_id}] Start the first {retry_count} retries...")
                    
                    # 🔥 Use the original self._llm when retrying, making sure the arguments (temperature, max_tokens etc.) reserved
                    if retry_count > 0:
                        # Rebind tools when retrying (if needed)
                        if self._langchain_tools:
                            llm_with_tools = self._llm.bind_tools(self._langchain_tools)
                            logger.info(f"🔗 [{self.agent_id}] Rebind tool when retrying, retaining original LLM parameters")
                        else:
                            llm_with_tools = self._llm
                            logger.info(f"🔗 [{self.agent_id}] Use original LLM when retrying, retaining all parameters")
                    
                    _llm_start = time.time()
                    response = llm_with_tools.invoke(current_messages)
                    _llm_ms = int((time.time() - _llm_start) * 1000)
                    # 🔑 Record the LLM response during the tool invocation phase (including Token usage)
                    self._record_llm_response_to_trace(response, llm_duration_ms=_llm_ms)
                    # Success, jump out of retry loop
                    break
                    
                except Exception as e:
                    error_msg = str(e)
                    last_error = e
                    
                    # 🔥 Check if it is an error where choices is null or another retryable error
                    is_retryable = (
                        "choices" in error_msg.lower() or 
                        "null value" in error_msg.lower() or
                        "connection" in error_msg.lower() or
                        "timeout" in error_msg.lower() or
                        "rate_limit" in error_msg.lower() or  # 🔧 Fix: rate_limit underscore matching
                        "rate limit" in error_msg.lower() or
                        "429" in error_msg or  # 🔧 Check the 429 status code directly
                        "503" in error_msg or
                        "502" in error_msg or
                        "500" in error_msg or
                        "limit" in error_msg.lower()  # 🔧 Cover: any error containing limit (e.g. "request limit for seconds") 
                    )
                    
                    if is_retryable and retry_count < max_retries:
                        retry_count += 1
                        logger.warning(f"⚠️ [{self.agent_id}] LLM The call failed (retryable error): {error_msg}")
                        logger.warning(f"   will be carried out {retry_count}/{max_retries} retries...")
                        continue
                    else:
                        # Non-retryable error or maximum retries reached
                        logger.error(f"❌ [{self.agent_id}] LLM API call failed")
                        logger.error(f"   error message: {error_msg}")
                        logger.error(f"   Number of retries: {retry_count}/{max_retries}")
                        
                        if "choices" in error_msg.lower() or "null value" in error_msg.lower():
                            logger.error(f"   This may be because:")
                            logger.error(f"   1. LLM API Service exception")
                            logger.error(f"   2. API Key is invalid or expired")
                            logger.error(f"   3. Request parameters do not meet API requirements")
                            logger.error(f"   4. API Service is temporarily unavailable")
                            # 🔥 Try to get more debugging information
                            if hasattr(self._llm, 'model_name'):
                                logger.error(f"   Model used: {self._llm.model_name}")
                            elif hasattr(self._llm, 'model'):
                                logger.error(f"   Model used: {self._llm.model}")
                            if hasattr(self._llm, 'openai_api_base'):
                                logger.error(f"   API Base: {self._llm.openai_api_base}")
                            elif hasattr(self._llm, 'base_url'):
                                logger.error(f"   API Base: {self._llm.base_url}")
                        
                        raise ValueError(f"LLM API The call failed (retried {retry_count} times): {error_msg}") from last_error

            # Print response details
            logger.info(f"=" * 100)
            logger.info(f"📤 [{self.agent_id}] LLM Response details:")
            logger.info(f"=" * 100)
            logger.info(f"  response type: {type(response).__name__}")
            if hasattr(response, 'content'):
                logger.info(f"  content length: {len(response.content)} character")
                logger.info(f"  content Preview: {response.content[:200] if response.content else '(empty)'}")
            if hasattr(response, 'tool_calls') and response.tool_calls:
                logger.info(f"  tool_calls Quantity: {len(response.tool_calls)}")
                for tc_idx, tc in enumerate(response.tool_calls):
                    logger.info(f"    [{tc_idx+1}] {tc.get('name', 'unknown')}: {tc.get('args', {})}")
            logger.info(f"=" * 100)
            logger.info(f"💬 [{self.agent_id}] LLM Response completed")

            # Check if there is a tool call
            if hasattr(response, 'tool_calls') and response.tool_calls:
                logger.info(f"🔧 [{self.agent_id}] detected {len(response.tool_calls)} tool calls")

                # Execute all tool calls
                tool_messages = self._execute_tool_calls(response.tool_calls)

                # Build a new message history
                current_messages = current_messages + [response] + tool_messages

                # Add analysis prompt words (if provided)
                if analysis_prompt:
                    logger.info(f"📝 [{self.agent_id}] Add analysis prompt words, length: {len(analysis_prompt)} character")
                    current_messages.append(HumanMessage(content=analysis_prompt))
                else:
                    # If analysis_prompt is not provided, add a default report generation prompt
                    logger.info(f"[{self.agent_id}] analysis_prompt not provided, default report generation prompt is used")
                    default_prompt = """✅ The tool call has been completed and all required data has been obtained.

🚫 **It is strictly prohibited to call the tool again**

📝 **Please do it now**: 
Based on the real data returned by the above tools, a complete analysis report can be written directly according to the previous analysis requirements and output format.

⚠️ **Important reminder**: 
- Do not return any tool calls (tool_calls)
- don t say"I need to call the tool"or"Let me get the data first"
- Directly output Chinese analysis report content

Start writing your report now:"""
                    current_messages.append(HumanMessage(content=default_prompt))

                # Call LLM again (not binding the tool, forcing report generation)
                logger.info(f"📝 [{self.agent_id}] The tool execution is completed and the final report is generated...")
                logger.info(f"📝 [{self.agent_id}] Current number of messages: {len(current_messages)}")

                # Detailed printing of messages before the final report is generated
                logger.info(f"=" * 100)
                logger.info(f"📋 [{self.agent_id}] Final report generation - message details:")
                logger.info(f"=" * 100)
                for idx, msg in enumerate(current_messages):
                    msg_type = type(msg).__name__
                    if hasattr(msg, 'content'):
                        content_preview = msg.content[:200] if len(msg.content) > 200 else msg.content
                        logger.info(f"  [{idx+1}] {msg_type}:")
                        logger.info(f"      content length: {len(msg.content)} character")
                        logger.info(f"      Content preview: {content_preview}")
                    elif hasattr(msg, 'tool_calls'):
                        logger.info(f"  [{idx+1}] {msg_type}:")
                        logger.info(f"      Number of tool calls: {len(msg.tool_calls)}")
                        for tc_idx, tc in enumerate(msg.tool_calls):
                            logger.info(f"        [{tc_idx+1}] {tc.get('name', 'unknown')}: {tc.get('args', {})}")
                    else:
                        logger.info(f"  [{idx+1}] {msg_type}: {str(msg)[:200]}")
                logger.info(f"=" * 100)

                # 🔧 Directly call LLM to generate reports (without binding tools)
                # Note: do not use bind_tools([]), Because DashScope does not accept an empty tools array
                logger.info(f"🔗 [{self.agent_id}] Directly call LLM to generate reports (no tool binding)")
                
                # 🔥 Add a retry mechanism (use max_retries configured by agent, default 3 times)
                max_retries = getattr(self.config, 'max_retries', 3)
                retry_count = 0
                last_error = None
                
                while retry_count <= max_retries:
                    try:
                        if retry_count > 0:
                            # Wait while retrying (exponential backoff)
                            wait_time = min(2 ** retry_count, 10)  # Wait up to 10 seconds
                            logger.info(f"⏳ [{self.agent_id}] wait {wait_time} Retry generating the report after seconds (section {retry_count}/{max_retries} times)...")
                            time.sleep(wait_time)
                            logger.info(f"🔄 [{self.agent_id}] Start the first {retry_count} Generate report for retries...")
                        
                        # 🔥 Use the original self._llm, making sure the arguments (temperature, max_tokens etc.) reserved
                        _llm_start = time.time()
                        final_response = self._llm.invoke(current_messages)
                        _llm_ms = int((time.time() - _llm_start) * 1000)
                        # Success, jump out of retry loop
                        break

                    except Exception as e:
                        error_msg = str(e)
                        last_error = e

                        # 🔥 Check if it is an error where choices is null or another retryable error
                        is_retryable = is_retryable_llm_error(error_msg)

                        if is_retryable and retry_count < max_retries:
                            retry_count += 1
                            logger.warning(f"⚠️ [{self.agent_id}] LLM call fails when generating report (retryable error): {error_msg}")
                            logger.warning(f"   will be carried out {retry_count}/{max_retries} retries...")
                            continue
                        else:
                            # Non-retryable error or maximum retries reached
                            logger.error(f"❌ [{self.agent_id}] LLM API call fails when generating report")
                            logger.error(f"   error message: {error_msg}")
                            logger.error(f"   Number of retries: {retry_count}/{max_retries}")
                            
                            if "choices" in error_msg.lower() or "null value" in error_msg.lower():
                                logger.error(f"   This may be because:")
                                logger.error(f"   1. LLM API Service exception")
                                logger.error(f"   2. API Key is invalid or expired")
                                logger.error(f"   3. Request parameters do not meet API requirements")
                                logger.error(f"   4. API Service is temporarily unavailable")
                                # 🔥 Try to get more debugging information
                                if hasattr(self._llm, 'model_name'):
                                    logger.error(f"   Model used: {self._llm.model_name}")
                                elif hasattr(self._llm, 'model'):
                                    logger.error(f"   Model used: {self._llm.model}")
                                if hasattr(self._llm, 'openai_api_base'):
                                    logger.error(f"   API Base: {self._llm.openai_api_base}")
                                elif hasattr(self._llm, 'base_url'):
                                    logger.error(f"   API Base: {self._llm.base_url}")
                            
                            raise ValueError(f"LLM API The call failed (retried {retry_count} times): {error_msg}") from last_error

                # Print final response details
                logger.info(f"=" * 100)
                logger.info(f"📤 [{self.agent_id}] Final report response details:")
                logger.info(f"=" * 100)
                logger.info(f"  response type: {type(final_response).__name__}")
                if hasattr(final_response, 'content'):
                    logger.info(f"  content length: {len(final_response.content)} character")
                    logger.info(f"  content Preview: {final_response.content[:200] if final_response.content else '(empty)'}")
                if hasattr(final_response, 'tool_calls') and final_response.tool_calls:
                    logger.info(f"  tool_calls Quantity: {len(final_response.tool_calls)}")
                    for tc_idx, tc in enumerate(final_response.tool_calls):
                        logger.info(f"    [{tc_idx+1}] {tc.get('name', 'unknown')}: {tc.get('args', {})}")
                logger.info(f"=" * 100)

                # Check if there are still tool_calls (theoretically there should not be, because there is no binding tool)
                if hasattr(final_response, 'tool_calls') and final_response.tool_calls:
                    logger.warning(f"⚠️ [{self.agent_id}] The second call still returns tool_calls: {len(final_response.tool_calls)} a")
                    logger.warning(f"⚠️ [{self.agent_id}] LLM Didn t understand the command, try adding a stronger prompt and try again")

                    # Add stronger hints
                    retry_prompt = """🚨 **Severe warning: You just returned a tool call, which is wrong!**

❌ **prohibited conduct**: 
- It is prohibited to return any tool_calls
- forbidden to say"I need to call the tool"
- forbidden to say"Let me get the data first"

✅ **correct behavior**: 
- All data is already in the ToolMessage above
- Your only task now is: writing a Chinese analysis report
- Directly output report text content

📝 **Execute immediately**: 
Based on the data returned by the above tools, a complete analysis report can be written directly according to the previous requirements.

Now start writing the report (output only the report text, nothing else):"""
                    current_messages.append(HumanMessage(content=retry_prompt))

                    # Try again
                    logger.info(f"🔄 [{self.agent_id}] Retry generating report...")

                    # Detailed printing of messages before retry
                    logger.info(f"=" * 100)
                    logger.info(f"📋 [{self.agent_id}] Retry report generation - message details:")
                    logger.info(f"=" * 100)
                    for idx, msg in enumerate(current_messages):
                        msg_type = type(msg).__name__
                        if hasattr(msg, 'content'):
                            content_preview = msg.content[:200] if len(msg.content) > 200 else msg.content
                            logger.info(f"  [{idx+1}] {msg_type}:")
                            logger.info(f"      content length: {len(msg.content)} character")
                            logger.info(f"      Content preview: {content_preview}")
                        elif hasattr(msg, 'tool_calls'):
                            logger.info(f"  [{idx+1}] {msg_type}:")
                            logger.info(f"      Number of tool calls: {len(msg.tool_calls)}")
                            for tc_idx, tc in enumerate(msg.tool_calls):
                                logger.info(f"        [{tc_idx+1}] {tc.get('name', 'unknown')}: {tc.get('args', {})}")
                        else:
                            logger.info(f"  [{idx+1}] {msg_type}: {str(msg)[:200]}")
                    logger.info(f"=" * 100)

                    # 🔧 Call LLM directly when retrying (without binding the tool)
                    logger.info(f"🔗 [{self.agent_id}] Call LLM directly when retrying (no tool binding)")
                    
                    # 🔥 Add a retry mechanism (use max_retries configured by agent, default 3 times)
                    max_retries = getattr(self.config, 'max_retries', 3)
                    retry_count = 0
                    last_error = None
                    
                    while retry_count <= max_retries:
                        try:
                            if retry_count > 0:
                                # Wait while retrying (exponential backoff)
                                wait_time = min(2 ** retry_count, 10)  # Wait up to 10 seconds
                                logger.info(f"⏳ [{self.agent_id}] wait {wait_time} Retry after seconds (No. {retry_count}/{max_retries} times)...")
                                time.sleep(wait_time)
                                logger.info(f"🔄 [{self.agent_id}] Start the first {retry_count} retries...")
                            
                            # 🔥 Use the original self._llm, making sure the arguments (temperature, max_tokens etc.) reserved
                            _llm_start = time.time()
                            final_response = self._llm.invoke(current_messages)
                            _llm_ms = int((time.time() - _llm_start) * 1000)
                            # Success, jump out of retry loop
                            break
                            
                        except Exception as e:
                            error_msg = str(e)
                            last_error = e
                            
                            # 🔥 Check if it is an error where choices is null or another retryable error
                            is_retryable = (
                                "choices" in error_msg.lower() or 
                                "null value" in error_msg.lower() or
                                "connection" in error_msg.lower() or
                                "timeout" in error_msg.lower() or
                                "rate_limit" in error_msg.lower() or  # 🔧 Underline format
                                "rate limit" in error_msg.lower() or
                                "429" in error_msg or  # 🔧 Directly matches 429 status code
                                "503" in error_msg or
                                "502" in error_msg or
                                "500" in error_msg or
                                "limit" in error_msg.lower()  # 🔧 Keep everything in mind
                            )
                            
                            if is_retryable and retry_count < max_retries:
                                retry_count += 1
                                logger.warning(f"⚠️ [{self.agent_id}] LLM call fails on retry (retryable error): {error_msg}")
                                logger.warning(f"   will be carried out {retry_count}/{max_retries} retries...")
                                continue
                            else:
                                # Non-retryable error or maximum retries reached
                                logger.error(f"❌ [{self.agent_id}] LLM API call fails when retrying")
                                logger.error(f"   error message: {error_msg}")
                                logger.error(f"   Number of retries: {retry_count}/{max_retries}")
                                
                                if "choices" in error_msg.lower() or "null value" in error_msg.lower():
                                    logger.error(f"   This may be because:")
                                    logger.error(f"   1. LLM API Service exception")
                                    logger.error(f"   2. API Key is invalid or expired")
                                    logger.error(f"   3. Request parameters do not meet API requirements")
                                    logger.error(f"   4. API Service is temporarily unavailable")
                                    # 🔥 Try to get more debugging information
                                    if hasattr(self._llm, 'model_name'):
                                        logger.error(f"   Model used: {self._llm.model_name}")
                                    elif hasattr(self._llm, 'model'):
                                        logger.error(f"   Model used: {self._llm.model}")
                                    if hasattr(self._llm, 'openai_api_base'):
                                        logger.error(f"   API Base: {self._llm.openai_api_base}")
                                    elif hasattr(self._llm, 'base_url'):
                                        logger.error(f"   API Base: {self._llm.base_url}")
                                
                                raise ValueError(f"LLM API The call failed (retried {retry_count} times): {error_msg}") from last_error

                    # Print retry response details
                    logger.info(f"=" * 100)
                    logger.info(f"📤 [{self.agent_id}] Retry response details:")
                    logger.info(f"=" * 100)
                    logger.info(f"  response type: {type(final_response).__name__}")
                    if hasattr(final_response, 'content'):
                        logger.info(f"  content length: {len(final_response.content)} character")
                        logger.info(f"  content Preview: {final_response.content[:200] if final_response.content else '(empty)'}")
                    if hasattr(final_response, 'tool_calls') and final_response.tool_calls:
                        logger.info(f"  tool_calls Quantity: {len(final_response.tool_calls)}")
                        for tc_idx, tc in enumerate(final_response.tool_calls):
                            logger.info(f"    [{tc_idx+1}] {tc.get('name', 'unknown')}: {tc.get('args', {})}")
                    logger.info(f"=" * 100)

                    # Check again
                    if hasattr(final_response, 'tool_calls') and final_response.tool_calls:
                        logger.error(f"❌ [{self.agent_id}] After retrying, it still returns tool_calls and gives up.")
                        self._last_llm_response = final_response
                        self._record_llm_response_to_trace(final_response, llm_duration_ms=_llm_ms)
                        return "Analysis report generation failed: LLM keeps returning tool calls instead of report content. Please change the model or try again."

                self._last_llm_response = final_response
                self._record_llm_response_to_trace(final_response, llm_duration_ms=_llm_ms)
                content = final_response.content if hasattr(final_response, 'content') else str(final_response)
                logger.info(f"✅ [{self.agent_id}] Report generation completed, length: {len(content)} character")
                logger.debug(f"🔍 [{self.agent_id}] Report content preview: {content[:200] if content else '(empty)'}")
                if not content or len(content.strip()) == 0:
                    logger.warning(f"⚠️ [{self.agent_id}] The report content is empty! final_response type: {type(final_response)}, hasattr content: {hasattr(final_response, 'content')}")
                    if hasattr(final_response, 'content'):
                        logger.warning(f"⚠️ [{self.agent_id}] final_response.content value: {repr(final_response.content)}")
                    # Check if there is tool_calls
                    if hasattr(final_response, 'tool_calls'):
                        logger.warning(f"⚠️ [{self.agent_id}] final_response.tool_calls: {final_response.tool_calls}")
                    # Print the complete response object
                    logger.warning(f"⚠️ [{self.agent_id}] final_response complete object: {final_response}")
                return content
            else:
                # There is no tool call, and the content is returned directly.
                self._last_llm_response = response
                self._record_llm_response_to_trace(response, llm_duration_ms=_llm_ms)
                content = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"📝 [{self.agent_id}] Direct response (no tool call), length: {len(content)} character")
                return content

        # Maximum number of iterations reached
        logger.warning(f"⚠️ [{self.agent_id}] Maximum number of iterations reached {max_iterations}")
        return f"Analysis failed to complete (maximum number of iterations reached {max_iterations}) "

    def _format_tool_call_summary(self) -> str:
        """Format a summary of tool calls collected during the execution of this Agent as Markdown text

        For downstream agents to refer to in prompt words to understand which tools the pre-order Agent has called and what data it has obtained.

        Returns:
            str: Formatted tool call summary (Markdown), returns an empty string when no tool is called
        """
        summaries = getattr(self, "_tool_call_summaries_collected", [])
        if not summaries:
            return ""

        lines = [f"### {self.agent_id} Tool call records (total {len(summaries)} times)"]
        for idx, s in enumerate(summaries, 1):
            status = "✅success" if s.get("success") else f"❌failed({s.get('error', 'unknown')})"
            args_str = str(s.get("tool_args", {}))
            if len(args_str) > 150:
                args_str = args_str[:150] + "..."
            preview = s.get("result_preview", "")
            if len(preview) > 200:
                preview = preview[:200] + "..."
            lines.append(
                f"{idx}. **{s['tool_name']}** {status}\n"
                f"   - parameters: `{args_str}`\n"
                f"   - Results preview(length{s.get('result_length', 0)}): {preview}"
            )
        return "\n".join(lines)

    def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[ToolMessage]:
        """
        Performs a tool call and returns a list of ToolMessages

        Args:
            tool_calls: Tool call list

        Returns:
            List[ToolMessage]: Tool execution result message list
        """
        from core.tools.context import (
            reset_current_analysis_data_source,
            set_current_analysis_data_source,
        )

        tool_messages = []
        # 🆕 Collect tool call summaries for reference by downstream agents
        if not hasattr(self, "_tool_call_summaries_collected"):
            self._tool_call_summaries_collected = []
        current_state = getattr(self, "_current_state", None)
        analysis_data_source = None
        analysis_id = None
        if isinstance(current_state, dict):
            value = current_state.get("_analysis_data_source")
            if isinstance(value, str) and value.strip():
                analysis_data_source = value.strip().lower()
            analysis_id = current_state.get("analysis_id") or current_state.get("task_id")

        for tool_call in tool_calls:
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('args', {})
            tool_id = tool_call.get('id')

            logger.info(f"🔧 [{self.agent_id}] Execution tool: {tool_name}")
            logger.info(f"🔧 [{self.agent_id}] Tool parameters: {tool_args}")

            # Find the corresponding tool and execute it
            tool_result = None
            _tool_success = True
            _tool_error = None
            for tool in self._langchain_tools:
                if hasattr(tool, 'name') and tool.name == tool_name:
                    _exec_start = time.time()
                    try:
                        logger.info(f"🔄 [{self.agent_id}] Start calling tools {tool_name}...")
                        logger.debug(f"🔍 [{self.agent_id}] Tool type: {type(tool)}")
                        logger.debug(f"🔍 [{self.agent_id}] Tools func: {getattr(tool, 'func', 'N/A')}")
                        source_token = set_current_analysis_data_source(analysis_data_source)
                        try:
                            tool_result = tool.invoke(tool_args)
                        finally:
                            reset_current_analysis_data_source(source_token)
                        
                        # 🔥 Check whether the returned object is a coroutine object (fixes asynchronous function problem)
                        import asyncio
                        if asyncio.iscoroutine(tool_result):
                            logger.warning(f"⚠️ [{self.agent_id}] Tools {tool_name} Return the coroutine object and try to wait for completion...")
                            try:
                                # Try to get the event loop and wait for the coroutine
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    # If the event loop is running, it needs to be run in a new thread
                                    import threading
                                    result_container = {}
                                    exception_container = {}
                                    
                                    def run_coroutine():
                                        try:
                                            new_loop = asyncio.new_event_loop()
                                            asyncio.set_event_loop(new_loop)
                                            result_container['value'] = new_loop.run_until_complete(tool_result)
                                            new_loop.close()
                                        except Exception as e:
                                            exception_container['value'] = e
                                    
                                    thread = threading.Thread(target=run_coroutine, daemon=True)
                                    thread.start()
                                    thread.join(timeout=30)  # 30 seconds timeout
                                    
                                    if thread.is_alive():
                                        raise TimeoutError("Tool coroutine execution timeout")
                                    if 'value' in exception_container:
                                        raise exception_container['value']
                                    tool_result = result_container.get('value')
                                else:
                                    tool_result = loop.run_until_complete(tool_result)
                            except RuntimeError:
                                # There is no event loop, create new
                                tool_result = asyncio.run(tool_result)
                            logger.info(f"✅ [{self.agent_id}] Coroutine execution is completed, result type: {type(tool_result).__name__}")

                        # Detailed information about the results returned by the logging tool
                        if isinstance(tool_result, str):
                            result_preview = tool_result[:200] + "..." if len(tool_result) > 200 else tool_result
                            logger.info(f"✅ [{self.agent_id}] Tools {tool_name} Successful execution, return length: {len(tool_result)} character")
                            logger.info(f"📄 [{self.agent_id}] Tools {tool_name} Return to preview: {result_preview}")
                        else:
                            logger.info(f"✅ [{self.agent_id}] Tools {tool_name} Successful execution, return type: {type(tool_result).__name__}")
                            logger.info(f"📄 [{self.agent_id}] Tools {tool_name} Return content: {str(tool_result)[:200]}...")

                        # Record to tool execution log
                        _exec_ms = int((time.time() - _exec_start) * 1000)
                        try:
                            from core.tools.execution_logger import get_tool_execution_logger
                            get_tool_execution_logger().log(
                                tool_id=tool_name,
                                agent_id=self.agent_id,
                                tool_args=tool_args if isinstance(tool_args, dict) else {"value": str(tool_args)},
                                result=tool_result,
                                success=True,
                                execution_time_ms=_exec_ms,
                                analysis_id=analysis_id,
                            )
                        except Exception:
                            pass  # Logging failure does not affect the main process

                    except Exception as e:
                        logger.error(f"❌ [{self.agent_id}] Tools {tool_name} Execution failed: {e}")
                        import traceback
                        logger.error(f"❌ [{self.agent_id}] Tools {tool_name} Error details: {traceback.format_exc()}")
                        tool_result = f"Tool execution failed: {str(e)}"
                        _tool_success = False
                        _tool_error = str(e)

                        # Record failure log
                        _exec_ms = int((time.time() - _exec_start) * 1000)
                        try:
                            from core.tools.execution_logger import get_tool_execution_logger
                            get_tool_execution_logger().log(
                                tool_id=tool_name,
                                agent_id=self.agent_id,
                                tool_args=tool_args if isinstance(tool_args, dict) else {"value": str(tool_args)},
                                result=None,
                                success=False,
                                execution_time_ms=_exec_ms,
                                analysis_id=analysis_id,
                                error=str(e),
                            )
                        except Exception:
                            pass

                        # Reporting capability gaps
                        try:
                            from core.tools.external.skill_gap_detector import SkillGapDetector
                            SkillGapDetector.report_gap(
                                gap_type="tool_execution_error",
                                tool_name=tool_name,
                                agent_id=self.agent_id,
                                error=str(e),
                                context={
                                    "tool_call_args": tool_args if isinstance(tool_args, dict) else {"value": str(tool_args)},
                                    "analysis_id": analysis_id or "",
                                },
                            )
                        except Exception:
                            pass

                    break

            if tool_result is None:
                tool_result = f"Tool not found: {tool_name}"
                logger.warning(f"⚠️ [{self.agent_id}] {tool_result}")
                logger.warning(f"⚠️ [{self.agent_id}] List of available tools: {[t.name for t in self._langchain_tools]}")
                _tool_success = False
                _tool_error = "tool_not_found"

                # Missing reporting tool gap
                try:
                    from core.tools.external.skill_gap_detector import SkillGapDetector
                    SkillGapDetector.report_gap(
                        gap_type="tool_not_found",
                        tool_name=tool_name,
                        agent_id=self.agent_id,
                        error="Tool does not exist in the current registry",
                        context={
                            "available_tools": [t.name for t in self._langchain_tools],
                            "analysis_id": analysis_id or "",
                        },
                    )
                except Exception:
                    pass

            # 🆕 Collect tool call summary
            _result_str = str(tool_result) if tool_result else ""
            self._tool_call_summaries_collected.append({
                "tool_name": tool_name,
                "tool_args": tool_args if isinstance(tool_args, dict) else {"value": str(tool_args)},
                "result_preview": _result_str[:300] + ("..." if len(_result_str) > 300 else ""),
                "result_length": len(_result_str),
                "success": _tool_success,
                "error": _tool_error,
            })

            # 🔑 Record tool calls to execution traces
            _recorder = getattr(self, '_execution_recorder', None)
            if _recorder:
                try:
                    _recorder.record_tool_call(
                        tool_name=tool_name,
                        tool_args=tool_args if isinstance(tool_args, dict) else {"value": str(tool_args)},
                        success=_tool_success,
                        error=_tool_error,
                        result_length=len(_result_str),
                        result_preview=_result_str,
                    )
                except Exception:
                    pass

            # Create tool message
            tool_messages.append(ToolMessage(
                content=str(tool_result),
                tool_call_id=tool_id
            ))

        return tool_messages

    def _get_prompt_from_template(
        self,
        agent_type: str,
        agent_name: str,
        variables: Dict[str, Any],
        context: Any = None,
        fallback_prompt: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
        prompt_type: str = "user"  # 🆕 New parameter: Prompt word type ("user" or "system") 
    ) -> Optional[str]:
        """
        Get prompt words from template system (general method)

        This method is shared by all Agent base classes to avoid duplication of code.
        Automatically extract system variables (such as current_price, industry, etc.) from state.

        Args:
            agent_type: Agent Type (such as "analysts_v2", "researchers_v2", "managers_v2", "trader_v2") 
            agent_name: Agent Name (such as "market_analyst_v2", "bull_researcher_v2") 
            variables: template variable dictionary
            context: AgentContext Object (contains user_id and preference_id)
            fallback_prompt: Downgrade prompt word
            state: Workflow status (optional, used to extract system variables)
            prompt_type: Prompt word type ("user" Get user prompt words,"system" Get system prompt words)

        Returns:
            Prompt word text, returned if acquisition fails fallback_prompt
        """
        try:
            if prompt_type == "user":
                from tradingagents.utils.template_client import get_user_prompt as get_prompt_func
            else:
                from tradingagents.utils.template_client import get_agent_prompt as get_prompt_func
        except (ImportError, KeyError) as e:
            logger.warning(f"Unable to import template system: {e}")
            return fallback_prompt

        try:
            # 🆕 Automatically extract system variables from state (prepared by the workflow engine)
            if state:
                # Automatically inject all report class fields (no more hard-coded lists)
                # Fields matching _report, _plan, _opinion, _decision, _assessment, _analysis, _advice, _summary, _result suffix
                report_suffixes = ("_report", "_plan", "_opinion", "_decision", "_assessment", "_analysis", "_advice", "_summary", "_result")
                for key, val in state.items():
                    if key.endswith(report_suffixes) and key not in variables:
                        if isinstance(val, str) and len(val) > 200:
                            logger.info(f"📊 [system variables] Automatic extraction {key}: (length={len(val)})")
                        elif isinstance(val, str):
                            logger.info(f"📊 [system variables] Automatic extraction {key}: {val[:50]}...")
                        if isinstance(val, (str, dict)):
                            variables[key] = val

                # Preserve injection of underlying system variables (non-reporting classes)
                base_vars = [
                    "current_price", "industry", "market_name",
                    "currency_name", "currency_symbol", "current_date", "start_date",
                ]
                for var in base_vars:
                    if var in state and var not in variables:
                        val = state[var]
                        logger.info(f"📊 [system variables] Automatic extraction {var}: {val}")
                        variables[var] = val

                # 🆕 Automatic injection phase aggregation reports (analyst_reports/research_reports/risk_reports)
                try:
                    from core.workflow.stage_aggregator import inject_stage_reports
                    inject_stage_reports(state, variables)
                except Exception as e:
                    logger.debug(f"Stage reports aggregation failure (non-fatal): {e}")

                # 🆕 Automatic extraction tool call summary, formatted as a string for template reference
                tool_summaries = state.get("tool_call_summaries")
                if tool_summaries and isinstance(tool_summaries, dict) and "tool_call_summaries" not in variables:
                    summary_parts = []
                    for agent_key, summary_text in tool_summaries.items():
                        if summary_text:
                            summary_parts.append(str(summary_text))
                    if summary_parts:
                        formatted = "\n\n".join(summary_parts)
                        variables["tool_call_summaries"] = formatted
                        logger.info(f"📊 [system variables] Automatic extraction tool_call_summaries: ({len(tool_summaries)} Agent s tool records, total length {len(formatted)})")

            # Extract user_id and preference_id
            user_id = None
            preference_id = "neutral"

            if context:
                # 🔍 Diagnostic log: print context type and content
                logger.info(f"🔍 [_get_prompt_from_template] context Type: {type(context)}")
                if isinstance(context, dict):
                    logger.info(f"🔍 [_get_prompt_from_template] context is a dictionary, content: {context}")
                    user_id = context.get("user_id")
                    preference_id = context.get("preference_id", "neutral")
                else:
                    logger.info(f"🔍 [_get_prompt_from_template] context is an object, attribute: {dir(context)}")
                    if hasattr(context, 'user_id'):
                        user_id = context.user_id
                    if hasattr(context, 'preference_id'):
                        preference_id = context.preference_id or "neutral"
                
                logger.info(f"🔍 [_get_prompt_from_template] extracted preference_id: {preference_id}, user_id: {user_id}")

            # 🔍 Debugging: Print variables passed to the template system
            logger.info(f"🔍 [_get_prompt_from_template] Prepare variables to be passed to the template system (total {len(variables)} a):")
            if not variables:
                logger.warning(f"⚠️ [_get_prompt_from_template] The variable dictionary is empty!")
            else:
                for k, v in variables.items():
                    if isinstance(v, str) and len(v) > 100:
                        logger.info(f"  - {k}: {v[:100]}...")
                    else:
                        logger.info(f"  - {k}: {v}")
            
            # 🔍 Diagnostic logging: Print parameters passed to the template system
            logger.info(
                f"🔍 [_get_prompt_from_template] Call template system parameters: "
                f"agent_type={agent_type}, agent_name={agent_name}, "
                f"preference_id={preference_id}, user_id={user_id}, "
                f"variables Quantity={len(variables)}"
            )
            
            # Call the template system
            prompt = get_prompt_func(
                agent_type=agent_type,
                agent_name=agent_name,
                variables=variables,
                preference_id=preference_id,
                user_id=user_id,
                fallback_prompt=fallback_prompt,
                context=context
            )

            if prompt:
                logger.info(
                    f"✅ Get from template system {agent_name} {prompt_type} prompt word "
                    f"(user_id={user_id}, preference_id={preference_id}, length={len(prompt)})"
                )
                # 🔍 Diagnosis log: print the first 200 characters of the prompt word and check the template content
                prompt_preview = prompt[:200] if len(prompt) > 200 else prompt
                logger.info(f"🔍 [_get_prompt_from_template] Prompt word preview: {prompt_preview}")

                # 🏭 Industry context injection: Based on the industry to which the stock belongs, add industry analysis dimensions to the prompt words
                if state and state.get("industry") and state.get("industry") != "unknown":
                    try:
                        from app.services.analysis_profile_service import AnalysisProfileService
                        industry_block = AnalysisProfileService.build_industry_prompt_block(state["industry"])
                        if industry_block:
                            prompt = prompt + industry_block
                            logger.info(f"🏭 [Industry injection] {agent_name}: Added {state['industry']} Industry analysis dimensions")
                    except Exception as e:
                        logger.warning(f"⚠️ [Industry injection] failed: {e}")

                # 📚 Knowledge Skill Injection: Append the knowledge Skill content bound to the current Agent to the prompt word
                try:
                    knowledge_block = self._load_bound_knowledge_skills(agent_name)
                    if knowledge_block:
                        prompt = prompt + knowledge_block
                        logger.info(f"📚 [Knowledge injection] {agent_name}: Knowledge-based Skill content has been added")
                except Exception as e:
                    logger.warning(f"⚠️ [Knowledge injection] failed: {e}")

                # 🧠 External fact memory injection: The analysis engine connects the facts extracted by the intelligent assistant to the Internet
                #  (memory_facts_summary, (with collection date and source) into state, here only for
                # The debate session and risk assessment session are supplemented with analytical materials for them to improve their research and argumentation.
                if (
                    prompt_type == "user"
                    and agent_name in _MEMORY_AWARE_AGENTS
                    and state
                ):
                    memory_block = state.get("memory_facts_summary")
                    if isinstance(memory_block, str) and memory_block.strip():
                        prompt = prompt + "\n\n" + memory_block
                        logger.info(f"🧠 [factual memory injection] {agent_name}: External fact memory reference added")

                return prompt
            else:
                logger.warning(f"The template system returns empty prompt words, use downgrade prompt words")
                return fallback_prompt

        except Exception as e:
            logger.warning(f"Failed to obtain prompt word from template system: {e}")
            return fallback_prompt

