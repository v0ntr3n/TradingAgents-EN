"""
Workflow builder

Build LangGraph graph from WorkflowDefinition

Core design:
1. debate node(DEBATE)Not an execution node, but a mark of the control flow
2. debate participant(Such as bull_researcher, bear_researcher)Join by conditional edges
3. Conditional edges check the debate count in the state to decide whether to continue the debate or end it
"""

import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from app.utils.api_key_utils import truncate_api_key

logger = logging.getLogger(__name__)

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    EdgeType,
)


# ============================================================
# v3.6.0 Item 8: Debate reflection trigger (module-level function)
# ============================================================

def _trigger_debate_reflection(
    *,
    state: Dict[str, Any],
    result: Dict[str, Any],
    debate_state_field: str,
    debate_type: str,
    agent_id: str,
    node_id: str,
) -> None:
    """Trigger reflection and refinement after the debate.

    Called after the execution of the research_manager / risk_manager nodes, from state and result
    Extract the debate history and verdict from the file, and call run_reflection_sync to refine it into a structured debate_lesson.
    write AGENT_EXPERIENCE scope(memory_kind=debate_lesson) . 

    Downgrade strategy:
    - Debate history is empty → skip
    - LLM Timeout/return non JSON → fallback Write a summary of the debate history
    - mem0 Not available → skip
    - any exception → Does not block the main process (caller has try/except)
    """
    try:
        # Merge state and result (the result returned by the manager contains the updated debate_state)
        merged = dict(state or {})
        if isinstance(result, dict):
            merged.update(result)

        debate_state = merged.get(debate_state_field) or {}
        if not isinstance(debate_state, dict):
            return

        debate_history = str(debate_state.get("history", "") or "").strip()
        # judge_decision May exist in debate_state or top-level fields (such as investment_plan / final_trade_decision)
        conclusion = str(debate_state.get("judge_decision", "") or "").strip()
        if not conclusion:
            # Get the bottom line: Get the manager output from result
            if debate_state_field == "risk_debate_state":
                conclusion = str(merged.get("final_trade_decision", "") or "").strip()
            else:
                conclusion = str(merged.get("investment_plan", "") or "").strip()

        if not debate_history and not conclusion:
            logger.debug("[Debate reflection] Skip: Debate history and verdict are empty node=%s", node_id)
            return

        # Extract ticker (compatible with multiple field names)
        ticker = (
            merged.get("ticker")
            or merged.get("symbol")
            or merged.get("stock_code")
            or merged.get("code")
            or ""
        )
        ticker = str(ticker).strip() if ticker else ""

        # Extract user_id (for mem0 metadata)
        user_id = str(merged.get("user_id") or merged.get("userId") or "default_user")

        # Get db handle
        db = merged.get("_db") or merged.get("db")
        if db is None:
            try:
                from app.core.database import get_mongo_db_sync
                db = get_mongo_db_sync()
            except Exception as exc:
                logger.debug("[Debate reflection] Failed to obtain db handle: %s", exc)
                return
        if db is None:
            return

        # Construct fallback content
        fallback_parts = [f"Debate reflection {ticker} ({debate_type})"]
        if debate_history:
            # Only keep the last 800 words to avoid the fallback being too long
            fallback_parts.append(debate_history[-800:])
        if conclusion:
            fallback_parts.append(f"final verdict: {conclusion[:300]}")
        fallback_content = "\n\n".join(fallback_parts)

        from core.agents.reflection_helper import run_reflection_sync
        from core.agents.reflection_prompts import (
            DEBATE_REFLECTION_SYSTEM_PROMPT,
            build_debate_reflection_user_prompt,
        )
        from core.memory.models import MemoryScope

        user_prompt = build_debate_reflection_user_prompt(
            ticker=ticker,
            debate_history=debate_history,
            conclusion=conclusion,
            debate_type=debate_type,
        )
        if not user_prompt.strip():
            return

        success = run_reflection_sync(
            db=db,
            user_id=user_id,
            agent_id=agent_id,
            scope=MemoryScope.AGENT_EXPERIENCE,
            memory_kind="debate_lesson",
            system_prompt=DEBATE_REFLECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            fallback_content=fallback_content,
            fallback_metadata={
                "symbol": str(ticker).upper() if ticker else "",
                "debate_type": debate_type,
                "agent_id": agent_id,
                "node_id": node_id,
                "source": "debate_reflection",
            },
        )
        if success:
            logger.info(
                "[Debate reflection] Debate_lesson lesson written: ticker=%s type=%s node=%s",
                ticker, debate_type, node_id,
            )
    except Exception as exc:
        logger.warning("[Debate reflection] Abnormal: %s", exc, exc_info=True)


# v3.6.0 Item 8 fix: Manager agent_id prefix matching, covering v2 variants
_MANAGER_AGENT_PREFIXES = ("research_manager", "risk_manager")


def _is_manager_agent(agent_id: str) -> bool:
    """Determine whether agent_id belongs to the manager node (including v2 variant)."""
    agent_id = str(agent_id or "").strip()
    return any(agent_id.startswith(prefix) for prefix in _MANAGER_AGENT_PREFIXES)


from ..agents import AgentRegistry, AgentFactory, AgentConfig
from ..collaboration_runtime import (
    InvocationArtifactRef,
    InvocationPolicy,
    InvocationProvenance,
    InvocationRequest,
    InvocationResult,
    InvocationSourceType,
    InvocationStatus,
    InvocationTargetType,
    utc_now,
)

# Analyst Type Mapping - Agents that require tool node support
# Note: index_analyst and sector_analyst is"self contained"analyst,
# They do not use LangGraph's tool calling mechanism, but directly obtain the data and complete the analysis in a single call.
ANALYST_TOOL_MAPPING = {
    "market_analyst": "market",
    "news_analyst": "news",
    "fundamentals_analyst": "fundamentals",
    "social_analyst": "social",
    "market_analyst_v2": "market",
    "news_analyst_v2": "news",
    "fundamentals_analyst_v2": "fundamentals",
    "etf_analyst_v2": "fundamentals",  # ETF Analysts reuse fundamentals message slot
    "social_analyst_v2": "social",
}

_DEFAULT_CALLABLE_SURFACES = {"assistant", "workflow"}

_DEEP_AGENTS = {
    "research_manager_v2", "risk_manager_v2",
    "risky_analyst_v2", "safe_analyst_v2", "neutral_analyst_v2",
    # A9-P1: The risk self-debate node uses deep LLM (a single call hosts the three-perspective debate)
    "risk_self_debate_v2",
    "index_analyst_v2", "sector_analyst_v2",
    "research_manager", "risk_manager",
}


def _select_llm_type_for_agent(agent_id: str) -> str:
    normalized_agent_id = str(agent_id or "").strip()
    return "deep" if normalized_agent_id in _DEEP_AGENTS else "quick"


class LegacyDependencyProvider:
    """
    Legacy agent dependency provider

    Provide LLM and Toolkit instances to the adapter
    """

    _instance = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._quick_llm = None
        self._deep_llm = None
        self._debate_llm = None  # 🆕 Debate-specific LLM (use higher temperatures)
        self._toolkit = None
        self._memories = {}
        self._memory_provider = None

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> "LegacyDependencyProvider":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls(config)
        elif config:
            # If there is a new configuration, reset the instance so it can be recreated LLM
            cls._instance._config.update(config)
            cls._instance._quick_llm = None
            cls._instance._deep_llm = None
            cls._instance._debate_llm = None  # 🆕 reset debate LLM
            cls._instance._toolkit = None
            cls._instance._memories = {}
            cls._instance._memory_provider = None
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing or reconfiguration)"""
        cls._instance = None

    def get_llm(
        self,
        llm_type: str = "quick",
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Get LLM instance

        Args:
            llm_type: "quick" or "deep"
            temperature: Optional, if specified creates a new LLM instance (for Agent specific temperature configuration)
            timeout: Optional, overrides the default timeout
            max_tokens: Optional, overrides the default maximum output length
        """
        # Create a standalone instance whenever any Agent-level LLM overlay exists
        if temperature is not None or timeout is not None or max_tokens is not None:
            logger.info(
                f"[Depend on provider] Create custom LLM: type={llm_type}, "
                f"temperature={temperature}, timeout={timeout}, max_tokens={max_tokens}"
            )
            return self._create_custom_llm(
                llm_type,
                temperature=temperature,
                timeout=timeout,
                max_tokens=max_tokens,
            )
        
        # 🔥 Check whether the configuration changes every time it is called, and recreate the LLM instance if it changes
        # This ensures that the API key takes effect immediately after being updated without restarting the service.
        self._create_llm_instances(force_refresh=True)
        return self._deep_llm if llm_type == "deep" else self._quick_llm

    def get_toolkit(self):
        """Get Toolkit instance"""
        if self._toolkit is None:
            self._create_toolkit()
        return self._toolkit

    def get_memory(self, memory_type: str):
        """Get Memory instance"""
        if memory_type not in self._memories:
            self._create_memory(memory_type)
        return self._memories.get(memory_type)

    def _create_llm_instances(self, force_refresh: bool = False):
        """
        Create LLM instance

        Logic and the old engine (simple_analysis_service.create_analysis_config) Be consistent:
        1. If the user passes in a model name (quick_think_llm, deep_think_llm), Find configuration from database based on model name
        2. If the user does not pass in a model name, get the default configuration from the database
        3. Get the corresponding provider, backend_url, based on the model name api_key
        
        Args:
            force_refresh: Whether to force a refresh (re-read the configuration from the database and re-create the LLM instance)
        """
        from tradingagents.graph.trading_graph import create_llm_by_provider

        # 🔥 if force_refresh=False And the LLM instance already exists, return directly (to avoid repeated creation)
        if not force_refresh and self._quick_llm and self._deep_llm:
            logger.debug("[Depend on provider] LLM The instance already exists and does not need to be refreshed, use cache")
            return

        # Get the model name passed in by the user
        quick_model = self._config.get("quick_think_llm")
        deep_model = self._config.get("deep_think_llm")

        logger.info(f"[Depend on provider] User input configuration: quick_model={quick_model}, deep_model={deep_model}")

        # 🔧 JD Cloud mode: If no model name is passed in, the default model in the environment variable is used and the database query is skipped.
        from app.core.jdyun import is_jdyun_mode, get_jdyun_default_model
        if is_jdyun_mode():
            jdyun_default = get_jdyun_default_model()
            if not quick_model:
                quick_model = jdyun_default
            if not deep_model:
                deep_model = jdyun_default
            logger.info(f"[Depend on provider] Jingdong cloud model: quick_model={quick_model}, deep_model={deep_model}")
        else:
            # If the user does not pass in a model name, get the default configuration from the database
            if not quick_model or not deep_model:
                db_default = self._get_default_llm_config_from_db()
                if not quick_model:
                    quick_model = db_default.get("quick_think_llm", "qwen-flash")
                if not deep_model:
                    deep_model = db_default.get("deep_think_llm", "qwen-plus")
                logger.info(f"[Depend on provider] Supplement using database default configuration: quick_model={quick_model}, deep_model={deep_model}")

        # Get the full configuration from the database based on the model name (provider, url, api_key) 
        # Reuse existing unified query functions in simple_analysis_service
        # 🔥 The configuration is re-read from the database each time it is called to ensure that the API key takes effect immediately after being updated.
        from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
        quick_config = get_provider_and_url_by_model_sync(quick_model)
        deep_config = get_provider_and_url_by_model_sync(deep_model)

        quick_provider = quick_config.get("provider", "dashscope")
        deep_provider = deep_config.get("provider", "dashscope")

        # URL and API Key are preferred to be explicitly specified by the user, otherwise the database configuration is used.
        quick_url = self._config.get("quick_backend_url") or self._config.get("backend_url") or quick_config.get("backend_url", "")
        deep_url = self._config.get("deep_backend_url") or deep_config.get("backend_url", "") or quick_url

        # 🔥 API Key Get priority: explicitly specified by the user > Database configuration > Environment variables (handled in create_llm_by_provider)
        quick_api_key_from_config = self._config.get("quick_api_key") or self._config.get("api_key")
        quick_api_key_from_db = quick_config.get("api_key")
        quick_api_key = quick_api_key_from_config or quick_api_key_from_db
        
        deep_api_key_from_config = self._config.get("deep_api_key")
        deep_api_key_from_db = deep_config.get("api_key")
        deep_api_key = deep_api_key_from_config or deep_api_key_from_db or quick_api_key

        logger.info("[Depend on provider] Create LLM:")
        logger.info(f"  - Quick: provider={quick_provider}, model={quick_model}, url={quick_url[:50] if quick_url else 'None'}...")
        logger.info(f"  - Quick API Key Source: {'Explicitly specified by the user' if quick_api_key_from_config else ('Database configuration' if quick_api_key_from_db else 'Not configured (environment variables will be used)')}")
        if quick_api_key:
            logger.info(f"  - Quick API Key: configured ({truncate_api_key(quick_api_key)})")
        else:
            logger.info(f"  - Quick API Key: empty")
        logger.info(f"  - Deep: provider={deep_provider}, model={deep_model}, url={deep_url[:50] if deep_url else 'None'}...")
        logger.info(f"  - Deep API Key Source: {'Explicitly specified by the user' if deep_api_key_from_config else ('Database configuration' if deep_api_key_from_db else ('inheritance Quick' if quick_api_key else 'Not configured (environment variables will be used)'))}")
        if deep_api_key:
            logger.info(f"  - Deep API Key: configured ({truncate_api_key(deep_api_key)})")
        else:
            logger.info(f"  - Deep API Key: empty")

        try:
            # 🔧 Read model configuration from database (max_tokens, temperature, timeout, reasoning_effort) 
            # Priority: explicitly specified by the user(self._config) > Database configuration > Default value
            # Fix: The previous builder did not read the max_tokens of the DB, causing the number of Tokens configured in the UI to not take effect.
            from app.services.simple_analysis_service import _load_model_config_from_db
            quick_db_cfg = _load_model_config_from_db(quick_model)
            deep_db_cfg = _load_model_config_from_db(deep_model)

            quick_max_tokens = self._config.get("quick_max_tokens") or quick_db_cfg.get("max_tokens", 2000)
            deep_max_tokens = self._config.get("deep_max_tokens") or deep_db_cfg.get("max_tokens", 4000)
            logger.info(
                f"🔧 [Depend on provider] max_tokens: quick={quick_model}={quick_max_tokens}, "
                f"deep={deep_model}={deep_max_tokens}"
            )

            # 🧠 A1b: Depth gear → reasoning_effort Think about budget
            # Merge semantics are consistent with the old link (resolve_reasoning_efforts): DB explicit configuration > The gear is the default,
            # Only Volcano Ark Agent Plan (provider=volcengine) Injection; fast models move down two gears
            from tradingagents.graph.trading_graph import resolve_reasoning_efforts
            _effort_cfg = dict(self._config)
            _effort_cfg.setdefault("quick_provider", quick_provider)
            _effort_cfg.setdefault("deep_provider", deep_provider)
            quick_effort, deep_effort = resolve_reasoning_efforts(_effort_cfg, quick_db_cfg, deep_db_cfg)
            if self._config.get("depth_reasoning_effort"):
                logger.info(
                    f"🧠 [Depend on provider] reasoning_effort: Gear default={self._config.get('depth_reasoning_effort')}"
                    f" → quick={quick_model}={quick_effort}, deep={deep_model}={deep_effort}"
                    f" (DB Explicit configuration takes precedence, only volcano injection)"
                )

            # Create a quick model
            self._quick_llm = create_llm_by_provider(
                provider=quick_provider,
                model=quick_model,
                backend_url=quick_url,
                temperature=self._config.get("quick_temperature") or quick_db_cfg.get("temperature", 0.1),
                max_tokens=quick_max_tokens,
                timeout=self._config.get("quick_timeout") or quick_db_cfg.get("timeout", 60),
                api_key=quick_api_key,
                reasoning_effort=quick_effort,
            )

            # Create a deep model
            self._deep_llm = create_llm_by_provider(
                provider=deep_provider,
                model=deep_model,
                backend_url=deep_url,
                temperature=self._config.get("deep_temperature") or deep_db_cfg.get("temperature", 0.1),
                max_tokens=deep_max_tokens,
                timeout=self._config.get("deep_timeout") or deep_db_cfg.get("timeout", 120),
                api_key=deep_api_key,
                reasoning_effort=deep_effort,
            )

            logger.info("[Depend on provider] LLM Instance created successfully")
            logger.info(f"  - Quick LLM: {type(self._quick_llm).__name__}")
            logger.info(f"  - Deep LLM: {type(self._deep_llm).__name__}")
        except Exception as e:
            logger.error(f"[Depend on provider] LLM Creation failed: {e}")
            raise

    def _create_custom_llm(
        self,
        llm_type: str,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Create an LLM instance with agent-level override parameters.

        Args:
            llm_type: "quick" or "deep"
            temperature: Temperature parameter
            timeout: timeout parameter
            max_tokens: Maximum output length

        Returns:
            LLM Example
        """
        from tradingagents.graph.trading_graph import create_llm_by_provider

        # Get the model name (from the configuration specified when the analysis process was created)
        model = self._config.get(f"{llm_type}_think_llm")
        if not model:
            db_default = self._get_default_llm_config_from_db()
            model = db_default.get(f"{llm_type}_think_llm", "qwen-turbo" if llm_type == "quick" else "qwen-plus")

        # Get configuration based on model name (provider, url, api_key) 
        from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
        config = get_provider_and_url_by_model_sync(model)

        provider = config.get("provider", "dashscope")
        url = self._config.get(f"{llm_type}_backend_url") or self._config.get("backend_url") or config.get("backend_url", "")
        
        # 🔥 API Key Get priority: explicitly specified by the user > Database configuration > Environment variables (handled in create_llm_by_provider)
        api_key_from_config = self._config.get(f"{llm_type}_api_key") or self._config.get("api_key")
        api_key_from_db = config.get("api_key")
        api_key = api_key_from_config or api_key_from_db

        # 🔧 Read model configuration from database (max_tokens, temperature, timeout, reasoning_effort) 
        # Priority: explicit parameters > self._config > Database configuration > Default value
        from app.services.simple_analysis_service import _load_model_config_from_db
        db_cfg = _load_model_config_from_db(model)

        resolved_temperature = (
            temperature if temperature is not None
            else self._config.get(f"{llm_type}_temperature") or db_cfg.get("temperature", 0.1)
        )
        resolved_max_tokens = (
            max_tokens if max_tokens is not None
            else self._config.get(f"{llm_type}_max_tokens") or db_cfg.get("max_tokens", 2000 if llm_type == "quick" else 4000)
        )
        resolved_timeout = (
            timeout if timeout is not None
            else self._config.get(f"{llm_type}_timeout") or db_cfg.get("timeout", 60 if llm_type == "quick" else 120)
        )

        # 🧠 A1b: reasoning_effort Merge (DB explicit configuration > The gear is default; only Volcano Ark is injected; quick downgrades by two gears)
        from tradingagents.graph.trading_graph import _lower_reasoning_effort
        resolved_effort = db_cfg.get("reasoning_effort")
        _depth_effort = self._config.get("depth_reasoning_effort")
        if _depth_effort and not resolved_effort and str(provider or "").lower() == "volcengine":
            resolved_effort = _lower_reasoning_effort(_depth_effort) if llm_type == "quick" else _depth_effort

        logger.info(
            f"[Depend on provider] Create custom LLM: type={llm_type}, model={model}, "
            f"temperature={resolved_temperature}, timeout={resolved_timeout}, max_tokens={resolved_max_tokens}"
            + (f", reasoning_effort={resolved_effort}" if resolved_effort else "")
        )
        logger.info(f"  - API Key Source: {'Explicitly specified by the user' if api_key_from_config else ('Database configuration' if api_key_from_db else 'Not configured (environment variables will be used)')}")
        if api_key:
            logger.info(f"  - API Key: configured ({truncate_api_key(api_key)})")
        else:
            logger.info(f"  - API Key: empty")

        return create_llm_by_provider(
            provider=provider,
            model=model,
            backend_url=url,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            timeout=resolved_timeout,
            api_key=api_key,
            reasoning_effort=resolved_effort,
        )

    def _get_llm_config_from_db(self) -> Dict[str, Any]:
        """Get LLM configuration from database"""
        try:
            from pymongo import MongoClient
            from app.core.config import settings

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]

            # 1. Get the default model in system configuration
            configs_collection = db.system_configs
            doc = configs_collection.find_one({"is_active": True}, sort=[("version", -1)])

            if not doc or "llm_configs" not in doc:
                logger.warning("[Depend on provider] There is no LLM configuration in the database, use the default configuration")
                return {}

            llm_configs = doc["llm_configs"]

            # Find the first enabled non-google model as the default model
            #  (Because the Google model is not suitable for direct use in China)
            default_config = None
            for cfg in llm_configs:
                if cfg.get("enabled", True):
                    provider = cfg.get("provider", "").lower()
                    # Give priority to Ali Bailian or DeepSeek
                    if provider in ["dashscope", "deepseek"]:
                        default_config = cfg
                        break

            # If no preferred manufacturer is found, use any available configuration
            if not default_config:
                for cfg in llm_configs:
                    if cfg.get("enabled", True):
                        default_config = cfg
                        break

            if not default_config:
                logger.warning("[Depend on provider] No enabled LLM configuration found")
                return {}

            # 2. Get manufacturer configuration (API Key and base_url)
            provider_name = default_config.get("provider", "")
            model_name = default_config.get("model_name", "")
            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider_name})

            # 🔥 Determine API Key (Priority: Model Configuration > Factory configuration > environment variables)
            api_key = None
            model_api_key = default_config.get("api_key", "")
            if model_api_key and model_api_key.strip() and model_api_key != "your-api-key" and not model_api_key.startswith("sk-xxx"):
                api_key = model_api_key
                logger.info(f"✅ [Depend on provider] Configured using models API Key")
            elif provider_doc:
                provider_api_key = provider_doc.get("api_key", "")
                if provider_api_key and provider_api_key.strip() and provider_api_key != "your-api-key" and not provider_api_key.startswith("sk-xxx"):
                    api_key = provider_api_key
                    logger.info(f"✅ [Depend on provider] Use factory configured API Key")
            
            backend_url = default_config.get("api_base", "")
            if provider_doc and not backend_url:
                backend_url = provider_doc.get("default_base_url", "")

            # If the database does not have an API Key, try to get it from the environment variable
            if not api_key:
                api_key = self._get_env_api_key(provider_name)
                if api_key:
                    logger.info(f"✅ [Depend on provider] using environment variables API Key")

            result = {
                "llm_provider": provider_name,
                "quick_think_llm": model_name,
                "deep_think_llm": model_name,
                "backend_url": backend_url,
                "api_key": api_key,
                "quick_temperature": default_config.get("temperature", 0.1),
                "quick_max_tokens": default_config.get("max_tokens", 2000),
                "quick_timeout": default_config.get("timeout", 30),
            }

            logger.info(f"[Depend on provider] Get configuration from database: provider={provider_name}, model={model_name}, url={backend_url[:50] if backend_url else 'None'}...")

            client.close()
            return result

        except Exception as e:
            logger.warning(f"[Depend on provider] Failed to get configuration from database: {e}")
            return {}

    def _get_env_api_key(self, provider_name: str) -> Optional[str]:
        """Get from environment variables API Key"""
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "google": "GOOGLE_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "qianfan": "QIANFAN_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
        }
        env_name = env_key_map.get(provider_name.lower())
        if env_name:
            return os.getenv(env_name)
        return None

    def _get_default_llm_config_from_db(self) -> Dict[str, Any]:
        """
        Get default LLM configuration from database (model name only)

        Used to obtain the system default configuration when the user does not pass in a model name.
        """
        try:
            from pymongo import MongoClient
            from app.core.config import settings

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]

            # Get the default model in system configuration
            doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])

            if not doc or "llm_configs" not in doc:
                logger.warning("[Depend on provider] There is no LLM configuration in the database, use the default configuration")
                client.close()
                return {"quick_think_llm": "qwen-turbo", "deep_think_llm": "qwen-plus"}

            llm_configs = doc["llm_configs"]

            # Find the first enabled non-google model as the default model
            default_config = None
            for cfg in llm_configs:
                if cfg.get("enabled", True):
                    provider = cfg.get("provider", "").lower()
                    if provider in ["dashscope", "deepseek"]:
                        default_config = cfg
                        break

            if not default_config:
                for cfg in llm_configs:
                    if cfg.get("enabled", True):
                        default_config = cfg
                        break

            client.close()

            if default_config:
                model_name = default_config.get("model_name", "qwen-turbo")
                return {
                    "quick_think_llm": model_name,
                    "deep_think_llm": model_name,
                }

            return {"quick_think_llm": "qwen-turbo", "deep_think_llm": "qwen-plus"}

        except Exception as e:
            logger.warning(f"[Depend on provider] Failed to get default configuration from database: {e}")
            return {"quick_think_llm": "qwen-turbo", "deep_think_llm": "qwen-plus"}

    def _get_config_by_model_name(self, model_name: str) -> Dict[str, Any]:
        """
        Get the full configuration from the database based on the model name (provider, url, api_key) 

        Logic remains consistent with old engine get_provider_and_url_by_model_sync

        Args:
            model_name: Model name, such as 'qwen-turbo', 'gpt-4' Wait

        Returns:
            dict: {"provider": "dashscope", "backend_url": "https://...", "api_key": "xxx"}
        """
        # Default URL mapping
        default_urls = {
            "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "deepseek": "https://api.deepseek.com",
            "openai": "https://api.openai.com/v1",
            "google": "https://generativelanguage.googleapis.com/v1beta/openai",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "siliconflow": "https://api.siliconflow.cn/v1",
        }

        # Default mapping of model name to manufacturer
        model_provider_map = {
            "qwen": "dashscope",
            "gpt": "openai",
            "deepseek": "deepseek",
            "gemini": "google",
            "glm": "zhipu",
            "ernie": "qianfan",
        }

        try:
            from pymongo import MongoClient
            from app.core.config import settings

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]

            # Query active system configuration
            doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])

            if doc and "llm_configs" in doc:
                for cfg in doc["llm_configs"]:
                    if cfg.get("model_name") == model_name:
                        provider = cfg.get("provider", "")
                        api_base = cfg.get("api_base", "")
                        model_api_key = cfg.get("api_key")

                        # Get factory configuration from llm_providers
                        provider_doc = db.llm_providers.find_one({"name": provider})

                        # 🔥 Option 3: Determine API Key (new priority: factory configuration > Model configuration > environment variables)
                        api_key = None

                        # Priority 1: Factory configuration
                        if provider_doc and provider_doc.get("api_key"):
                            pk = provider_doc["api_key"]
                            if pk and pk.strip() and pk != "your-api-key" and not pk.startswith("sk-xxx"):
                                api_key = pk

                        # Priority 2: Model configuration (as an alternative)
                        if not api_key:
                            if model_api_key and model_api_key.strip() and model_api_key != "your-api-key":
                                api_key = model_api_key

                        # Priority 3: Environment variables
                        if not api_key:
                            api_key = self._get_env_api_key(provider)

                        # OK backend_url
                        backend_url = api_base
                        if not backend_url and provider_doc:
                            backend_url = provider_doc.get("default_base_url", "")
                        if not backend_url:
                            backend_url = default_urls.get(provider.lower(), "")

                        client.close()
                        logger.info(f"[Depend on provider] model {model_name} Configuration: provider={provider}, url={backend_url[:40] if backend_url else 'None'}...")
                        return {
                            "provider": provider,
                            "backend_url": backend_url,
                            "api_key": api_key
                        }

            client.close()

        except Exception as e:
            logger.warning(f"[Depend on provider] Get model from database {model_name} Configuration failed: {e}")

        # If not found in database, use default mapping
        provider = "dashscope"
        for prefix, p in model_provider_map.items():
            if model_name.lower().startswith(prefix):
                provider = p
                break

        logger.info(f"[Depend on provider] Use default mapping: {model_name} -> {provider}")
        return {
            "provider": provider,
            "backend_url": default_urls.get(provider, ""),
            "api_key": self._get_env_api_key(provider)
        }

    def _get_provider_config_from_db(self, provider_name: str) -> Dict[str, Any]:
        """
        Get the corresponding configuration (URL and API Key) from the database based on the provider name

        Args:
            provider_name: Manufacturer name, such as "dashscope", "deepseek", "openai" Wait

        Returns:
            Configuration dictionary containing backend_url and api_key
        """
        # Default URL mapping
        default_urls = {
            "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "deepseek": "https://api.deepseek.com",
            "openai": "https://api.openai.com/v1",
            "google": "https://generativelanguage.googleapis.com/v1beta/openai",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "siliconflow": "https://api.siliconflow.cn/v1",
        }

        result = {
            "backend_url": default_urls.get(provider_name.lower(), ""),
            "api_key": None,
        }

        try:
            from pymongo import MongoClient
            from app.core.config import settings

            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]

            # Get manufacturer configuration from llm_providers collection
            providers_collection = db.llm_providers
            provider_doc = providers_collection.find_one({"name": provider_name})

            if provider_doc:
                if provider_doc.get("default_base_url"):
                    result["backend_url"] = provider_doc["default_base_url"]
                if provider_doc.get("api_key") and not provider_doc["api_key"].startswith("sk-xxx"):
                    result["api_key"] = provider_doc["api_key"]

            client.close()

        except Exception as e:
            logger.debug(f"[Depend on provider] Get from database {provider_name} Configuration failed: {e}")

        # If the database does not have an API Key, try to get it from the environment variable
        if not result["api_key"]:
            result["api_key"] = self._get_env_api_key(provider_name)

        logger.debug(f"[Depend on provider] {provider_name} Configuration: url={result['backend_url'][:30] if result['backend_url'] else 'None'}..., api_key={'valuable' if result['api_key'] else 'None'}")

        return result

    def _create_toolkit(self):
        """Create Toolkit instance"""
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG

        config = {**DEFAULT_CONFIG, **self._config}
        self._toolkit = Toolkit(config=config)
        logger.info("[Depend on provider] Toolkit Created successfully")

    def _create_memory(self, memory_type: str):
        """Create a Memory instance"""
        from tradingagents.core.engine.memory_provider import MemoryProvider
        from tradingagents.default_config import DEFAULT_CONFIG

        config = {**DEFAULT_CONFIG, **self._config}

        if config.get("memory_enabled", True):
            if self._memory_provider is None:
                self._memory_provider = MemoryProvider(config=config, memory_enabled=True)
            self._memories[memory_type] = self._memory_provider.get_memory(memory_type)
        else:
            self._memories[memory_type] = None

    def get_tool_nodes(self) -> Dict[str, ToolNode]:
        """Get the tool node (used in the analyst s tool call loop)"""
        toolkit = self.get_toolkit()
        return {
            "market": ToolNode([
                toolkit.get_stock_market_data_unified,
                toolkit.get_YFin_data_online,
                toolkit.get_stockstats_indicators_report_online,
                toolkit.get_YFin_data,
                toolkit.get_stockstats_indicators_report,
            ]),
            "social": ToolNode([
                toolkit.get_stock_sentiment_unified,
                toolkit.get_stock_news_openai,
                toolkit.get_reddit_stock_info,
            ]),
            "news": ToolNode([
                toolkit.get_stock_news_unified,
                toolkit.get_global_news_openai,
                toolkit.get_google_news,
                toolkit.get_finnhub_news,
                toolkit.get_reddit_news,
            ]),
            "fundamentals": ToolNode([
                toolkit.get_stock_fundamentals_unified,
                toolkit.get_finnhub_company_insider_sentiment,
                toolkit.get_finnhub_company_insider_transactions,
                toolkit.get_simfin_balance_sheet,
                toolkit.get_simfin_cashflow,
                toolkit.get_simfin_income_stmt,
                toolkit.get_china_stock_data,
                toolkit.get_china_fundamentals,
            ]),
        }


class WorkflowBuilder:
    """
    Workflow builder

    Convert WorkflowDefinition to executable LangGraph

    Usage:
        builder = WorkflowBuilder()
        graph = builder.build(workflow_definition)
        result = graph.invoke({"ticker": "AAPL", "trade_date": "2024-01-15"})
    """

    # Analyst agent_id to type mapping (used for selected_analysts filtering)
    ANALYST_ID_TO_TYPE = {
        "market_analyst": "market",
        "news_analyst": "news",
        "fundamentals_analyst": "fundamentals",
        "social_analyst": "social",
        "market_analyst_v2": "market",
        "news_analyst_v2": "news",
        "fundamentals_analyst_v2": "fundamentals",
        "etf_analyst_v2": "etf",  # ETF analyst
        "social_analyst_v2": "social",
        "index_analyst": "index_analyst",
        "sector_analyst": "sector_analyst",
        "index_analyst_v2": "index_analyst",
        "sector_analyst_v2": "sector_analyst",
    }

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        factory: Optional[AgentFactory] = None,
        default_config: Optional[AgentConfig] = None,
        legacy_config: Optional[Dict[str, Any]] = None,
        binding_manager: Optional[Any] = None,  # BindingManager
        llm_override: Optional[Any] = None,  # Optional LLM instance override
    ):
        from ..agents.registry import get_registry
        from ..config.binding_manager import BindingManager
        from ..config.agent_config_manager import AgentConfigManager

        # Ensure that the Agent adapter module is imported to trigger Agent registration
        try:
            import core.agents.adapters  # noqa: F401
            logger.debug("[WorkflowBuilder] Agent Adapter module loaded")
        except ImportError as e:
            logger.warning(f"[WorkflowBuilder] Failed to load Agent adapter module: {e}")

        self.registry = registry or get_registry()
        self.factory = factory or AgentFactory(self.registry)
        self.default_config = default_config or AgentConfig()
        self.llm_override = llm_override

        # BindingManager for dynamic tool binding
        self.binding_manager = binding_manager or BindingManager()

        # 🔥 AgentConfigManager Used to load Agent configuration
        self.agent_config_manager = AgentConfigManager()

        # Set up database connections for BindingManager and AgentConfigManager
        # 🆕 Also initialize EmbeddingManager and MemoryManager
        self.embedding_manager = None
        self.memory_manager = None

        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            self.binding_manager.set_database(db)
            self.agent_config_manager.set_database(db)
            logger.info("[WorkflowBuilder] BindingManager and AgentConfigManager has been initialized and connected to the database")

            # 🆕 Initialize EmbeddingManager and MemoryManager
            try:
                from core.llm import EmbeddingManager
                from core.memory import MemoryManager

                self.embedding_manager = EmbeddingManager(db=db)
                self.memory_manager = MemoryManager(self.embedding_manager)
                logger.info("[WorkflowBuilder] 🧠 EmbeddingManager and MemoryManager is initialized")
            except Exception as mem_error:
                logger.warning(f"[WorkflowBuilder] Memory system initialization failed: {mem_error}")
                logger.info("[WorkflowBuilder] Agent Will run without memory function")

        except Exception as e:
            logger.warning(f"[WorkflowBuilder] Database connection failed: {e}")
            logger.info("[WorkflowBuilder] Code configuration mode will be used")

        # Legacy dependency provider (used to adapt original agents)
        self._legacy_provider = LegacyDependencyProvider.get_instance(legacy_config)

        # Get selected_analysts from legacy_config (used to dynamically filter analyst nodes)
        self._selected_analysts: Optional[List[str]] = None
        if legacy_config:
            self._selected_analysts = legacy_config.get("selected_analysts")
            if self._selected_analysts:
                logger.info(f"[WorkflowBuilder] selected analysts: {self._selected_analysts}")

        self._agents: Dict[str, Any] = {}  # Cache created agents
        self._workflow_id: Optional[str] = None  # Current workflow ID

    def _is_analyst_selected(self, node: NodeDefinition) -> bool:
        """
        Check if the analyst node is selected

        Args:
            node: Node definition

        Returns:
            True If the node is selected or is not an analyst node
        """
        # If selected_analysts is not set, all analysts execute
        if not self._selected_analysts:
            return True

        # Not an analyst node, no filtering
        if node.type != NodeType.ANALYST:
            return True

        # Check if it is in the selected list
        if node.agent_id in self.ANALYST_ID_TO_TYPE:
            analyst_type = self.ANALYST_ID_TO_TYPE[node.agent_id]
            is_selected = analyst_type in self._selected_analysts
            if not is_selected:
                logger.info(f"[WorkflowBuilder] Filter analyst nodes: {node.id} (Type: {analyst_type})")
            return is_selected

        # Unknown type of analyst, reserved
        return True

    def build(
        self,
        definition: WorkflowDefinition,
        state_schema: Optional[type] = None,
    ):
        """
        Build a LangGraph graph

        Args:
            definition: Workflow definition
            state_schema: state mode (Use universal dictionary by default)

        Returns:
            compiled LangGraph
        """
        # Save workflow ID for dynamic tool binding
        self._workflow_id = definition.id
        logger.info(f"[WorkflowBuilder] Start building a workflow: {self._workflow_id}")

        # Use default state mode
        if state_schema is None:
            state_schema = self._get_default_state_schema()

        # Create diagram
        graph = StateGraph(state_schema)

        # Filter analyst nodes in workflow definition
        filtered_definition = self._filter_analyst_nodes(definition)

        # First identify the debate configuration
        debate_configs = self._identify_debate_configs(filtered_definition)

        # Construct a set of debate participants and their corresponding debate_key
        participant_debate_keys: Dict[str, str] = {}
        for debate_id, config in debate_configs.items():
            debate_key = f"_debate_{debate_id}_count"
            for p in config["participants"]:
                participant_debate_keys[p] = debate_key

        # Identify analyst nodes (requires tool node support)
        analyst_nodes_info: Dict[str, str] = {}  # node_id -> analyst_type
        for node in filtered_definition.nodes:
            if node.agent_id and node.agent_id in ANALYST_TOOL_MAPPING:
                analyst_type = ANALYST_TOOL_MAPPING[node.agent_id]
                analyst_nodes_info[node.id] = analyst_type
                logger.info(f"[tool node] Identify analyst nodes: {node.id} -> {analyst_type}")

        # Get tool node
        tool_nodes = {}
        if analyst_nodes_info:
            tool_nodes = self._legacy_provider.get_tool_nodes()
            logger.info(f"[tool node] Create tool node: {list(tool_nodes.keys())}")

        # Add node (using filtered definition)
        logger.info(f"[Graph construction] 📋 Workflow node list: {[n.id for n in filtered_definition.nodes]}")
        for node in filtered_definition.nodes:
            if node.type in (NodeType.START, NodeType.END):
                continue

            # If you are a debate participant, use a wrapper function
            if node.id in participant_debate_keys:
                debate_key = participant_debate_keys[node.id]
                node_func = self._create_debate_participant_wrapper(node, debate_key)
            elif _is_manager_agent(node.agent_id):
                # v3.6.0 Item 8: Manager nodes (research_manager / risk_manager and their v2 variants)
                # Trigger debate reflection after the manager produces a ruling and save the debate history+The ruling is distilled into
                # Structured debate_lesson lesson, written to AGENT_EXPERIENCE scope.
                debate_state_field = (
                    "risk_debate_state" if node.agent_id.startswith("risk_manager")
                    else "investment_debate_state"
                )
                node_func = self._create_manager_with_debate_reflection(
                    node, debate_state_field=debate_state_field
                )
            else:
                node_func = self._create_node_function(node)

            graph.add_node(node.id, node_func)
            logger.info(f"[Graph construction] ✅ Add node: {node.id} (agent_id={node.agent_id}, type={node.type})")

            # If it is an analyst node, add the corresponding tool node and message cleaning node
            if node.id in analyst_nodes_info:
                analyst_type = analyst_nodes_info[node.id]
                tools_node_id = f"tools_{node.id}"
                clear_node_id = f"msg_clear_{node.id}"

                # Add tool node (wrapped to use independent message history)
                wrapped_tool_node = self._create_tool_node_wrapper(
                    tool_nodes[analyst_type], node.id, analyst_type
                )
                graph.add_node(tools_node_id, wrapped_tool_node)
                logger.info(f"[tool node] Add tool node: {tools_node_id}")

                # Add message cleaning node
                graph.add_node(clear_node_id, self._create_msg_clear_node(node.id, analyst_type))
                logger.info(f"[tool node] Add message cleaning node: {clear_node_id}")

        # A9-P1: Add hidden self-debate single node for each risk debate
        # only when running state["_risk_self_debate"]=True (depth/full range and the switch is on) is routed to,
        # By default, the original risk triangle multi-agent path is adopted. When node creation fails, downgrade to no node (retaining the original path).
        # Does not block the entire workflow build.
        risk_self_debate_nodes: Set[str] = set()
        for debate_id in debate_configs:
            if "risk" in debate_id.lower():
                self_debate_node_id = f"{debate_id}_self_debate"
                try:
                    graph.add_node(
                        self_debate_node_id,
                        self._create_risk_self_debate_node_func(debate_id),
                    )
                    risk_self_debate_nodes.add(self_debate_node_id)
                    logger.info(f"[Graph construction] ✅ Add risk self debate node: {self_debate_node_id} (A9-P1)")
                except Exception as e:
                    logger.warning(
                        f"[Graph construction] ⚠️ The risk self-debate node failed to be created and the original risk triangle path was rolled back.: {e}"
                    )

        # A3: Added hidden parallel opening node for investment debate (non-risk)
        # only when running state["_parallel_opening"]=True (Enabled by default, can be turned off with one click) when being routed to,
        # In the first round, optimistic and cautious researchers gave briefings in parallel, and subsequent rounds returned to the original round of confrontation. When node creation fails
        # Downgrade to not adding nodes (retaining the original serial path) without blocking the entire workflow construction.
        parallel_opening_nodes: Set[str] = set()
        for debate_id, debate_config in debate_configs.items():
            if "risk" in debate_id.lower():
                continue  # Risk Debate: Deep range is taken over by A9-P1, low range retains original serial triangle
            if len(debate_config["participants"]) < 2:
                continue  # Single participant cannot run in parallel
            po_node_id = f"{debate_id}_parallel_opening"
            try:
                graph.add_node(
                    po_node_id,
                    self._create_parallel_opening_node_func(
                        debate_id, debate_config, filtered_definition
                    ),
                )
                parallel_opening_nodes.add(po_node_id)
                logger.info(f"[Graph construction] ✅ Add investment debate parallel start node: {po_node_id} (A3)")
            except Exception as e:
                logger.warning(
                    f"[Graph construction] ⚠️ The creation of the parallel deployment node failed and the original serial path was rolled back.: {e}"
                )

        # Add edges (using filtered definition)
        self._add_edges(
            graph, filtered_definition, debate_configs, analyst_nodes_info,
            risk_self_debate_nodes=risk_self_debate_nodes,
            parallel_opening_nodes=parallel_opening_nodes,
        )

        # compile
        return graph.compile()

    def _filter_analyst_nodes(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """
        Filter analyst nodes in a workflow definition based on selected_analysts

        This method will:
        1. Remove unselected analyst nodes
        2. Update the edges to directly connect the incoming edges of the filtered nodes to the outgoing edges.
        3. Keep your workflow connected

        Args:
            definition: Original workflow definition

        Returns:
            Filtered workflow definition (copy)
        """
        # If there is no selected_analysts configuration, return the original definition
        if not self._selected_analysts:
            return definition

        # Collect analyst nodes to be removed ID
        nodes_to_remove: Set[str] = set()
        for node in definition.nodes:
            if not self._is_analyst_selected(node):
                nodes_to_remove.add(node.id)

        if not nodes_to_remove:
            logger.info("[WorkflowBuilder] There are no analyst nodes to filter")
            return definition

        logger.info(f"[WorkflowBuilder] The following analyst nodes will be filtered: {nodes_to_remove}")

        # Create new node list (exclude filtered nodes)
        new_nodes = [n for n in definition.nodes if n.id not in nodes_to_remove]

        # Reconstruct edges
        # Strategy: For PARALLEL -> analyst -> MERGE mode
        # If the analyst is filtered, just remove the corresponding edge.
        # Because the PARALLEL and MERGE nodes automatically handle the remaining analysts

        new_edges = []
        for edge in definition.edges:
            # If the edge's source or target is a removed node, skip the edge
            if edge.source in nodes_to_remove or edge.target in nodes_to_remove:
                logger.debug(f"[WorkflowBuilder] remove edge: {edge.source} -> {edge.target}")
                continue
            new_edges.append(edge)

        # Create a new workflow definition
        filtered_definition = WorkflowDefinition(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            version=definition.version,
            nodes=new_nodes,
            edges=new_edges,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
            created_by=definition.created_by,
            config=definition.config,
            tags=definition.tags,
            is_template=definition.is_template,
        )

        logger.info(f"[WorkflowBuilder] Filtering completed: {len(definition.nodes)} node -> {len(new_nodes)} node, "
                   f"{len(definition.edges)} side -> {len(new_edges)} side")

        return filtered_definition

    def _create_msg_clear_node(self, node_id: str, analyst_type: str) -> Callable:
        """
        Create message cleaning node

        Clean up the independent message history of analysts to avoid unlimited accumulation of messages.
        """
        messages_key = f"_{analyst_type}_messages"

        def safe_msg_clear(state):
            """Clean analyst s independent message history"""
            logger.info(f"[Message cleaning] {node_id} - Clean independent message history: {messages_key}")
            # Clear independent message history
            return {messages_key: []}

        return safe_msg_clear

    def _create_tool_node_wrapper(
        self,
        tool_node: ToolNode,
        analyst_node_id: str,
        analyst_type: str
    ) -> Callable:
        """
        Create a wrapper for the tool node, using the analyst s independent message history
        """
        messages_key = f"_{analyst_type}_messages"

        def wrapped_tool_node(state):
            logger.info(f"[tool node] tools_{analyst_node_id} - Start execution")

            # Get analyst-independent message history
            analyst_messages = list(state.get(messages_key, []))
            if not analyst_messages:
                logger.warning(f"[tool node] {analyst_node_id} - The independent message history is empty, use shared messages")
                analyst_messages = list(state.get("messages", []))

            # Create tool node-specific state
            tool_state = {**state, "messages": analyst_messages}

            # Execute tool node
            result = tool_node.invoke(tool_state)

            # Update independent message history and remove shared messages field
            if "messages" in result:
                new_messages = result["messages"]
                if isinstance(new_messages, list):
                    updated_messages = analyst_messages + new_messages
                else:
                    updated_messages = analyst_messages + [new_messages]
                # Store to separate message field
                result[messages_key] = updated_messages
                # Remove shared messages field
                del result["messages"]
                logger.info(f"[tool node] {analyst_node_id} - Update message history, number of messages: {len(updated_messages)}")

            logger.info(f"[tool node] tools_{analyst_node_id} - Execution completed")
            return result

        return wrapped_tool_node

    def _create_analyst_condition_func(self, node_id: str, analyst_type: str) -> Callable:
        """
        Conditional function to create analyst node
        Determine whether there is a tool call and decide whether to route to the tool node or the message cleaning node
        Use an analyst s independent message history
        """
        tools_node_id = f"tools_{node_id}"
        clear_node_id = f"msg_clear_{node_id}"
        messages_key = f"_{analyst_type}_messages"

        # Report field mapping
        report_field_map = {
            "market": "market_report",
            "social": "sentiment_report",
            "news": "news_report",
            "fundamentals": "fundamentals_report",
        }
        report_field = report_field_map.get(analyst_type, f"{analyst_type}_report")

        # Tool count field mapping
        tool_count_field_map = {
            "market": "market_tool_call_count",
            "social": "sentiment_tool_call_count",
            "news": "news_tool_call_count",
            "fundamentals": "fundamentals_tool_call_count",
        }
        tool_count_field = tool_count_field_map.get(analyst_type, f"{analyst_type}_tool_call_count")

        def condition_func(state):
            """Determine whether to continue the tool call loop (using independent message history)"""
            # Use analyst-independent message history
            messages = state.get(messages_key, [])
            if not messages:
                # If there are no independent messages, fall back to shared messages
                messages = state.get("messages", [])

            if not messages:
                logger.info(f"🔀 [{node_id}] No message, return: {clear_node_id}")
                return clear_node_id

            last_message = messages[-1]
            report = state.get(report_field, "")
            tool_call_count = state.get(tool_count_field, 0)
            max_tool_calls = 3  # Maximum number of tool calls

            logger.info(f"🔀 [{node_id}] Conditional judgment (independent news: {messages_key}):")
            logger.info(f"  - Number of messages: {len(messages)}")
            logger.info(f"  - Report length: {len(report)}")
            logger.info(f"  - Number of tool calls: {tool_call_count}/{max_tool_calls}")
            logger.info(f"  - last message type: {type(last_message).__name__}")

            # If there is already a report, end the loop
            if report and len(report) > 100:
                logger.info(f"🔀 [{node_id}] ✅ Report completed, return: {clear_node_id}")
                return clear_node_id

            # If the maximum number of tool calls is reached, force the end
            if tool_call_count >= max_tool_calls:
                logger.warning(f"🔀 [{node_id}] ⚠️ The maximum number of calls is reached and returns: {clear_node_id}")
                return clear_node_id

            # Check if there is a tool call
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                logger.info(f"🔀 [{node_id}] 🔧 Tool call detected, return: {tools_node_id}")
                return tools_node_id

            logger.info(f"🔀 [{node_id}] ✅ No tool call, return: {clear_node_id}")
            return clear_node_id

        return condition_func

    def _create_analyst_wrapper(
        self,
        analyst_node: Callable,
        node_id: str,
        node_label: str,
        agent_id: str,
        analyst_type: str,
        output_field: Optional[str] = None,
    ) -> Callable:
        """
        Create a wrapper for analysts to use independent message history

        This resolves issues caused by sharing the messages field when multiple analysts execute in parallel:
        - Use separate message fields per analyst (e.g. _fundamentals_messages)
        - Avoid confusing tool calls and responses
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        # Independent message field name
        messages_key = f"_{analyst_type}_messages"

        def wrapped_analyst(state):
            logger.info(f"[Node execution] 🚀 {node_id} ({node_label}) - Start execution (analyst: {agent_id})")

            # Print debugging information
            logger.info(f"[Analyst debugging] {node_id} - independent message field: {messages_key}")
            logger.info(f"[Analyst debugging] {node_id} - Number of shared messages: {len(state.get('messages', []))}")
            logger.info(f"[Analyst debugging] {node_id} - Number of independent messages: {len(state.get(messages_key, []))}")

            # Counter in print status
            for key in ["market_tool_call_count", "sentiment_tool_call_count", "news_tool_call_count", "fundamentals_tool_call_count"]:
                if key in state:
                    logger.info(f"[Analyst debugging] {node_id} - In status {key}: {state.get(key)}")

            # Get analyst-independent message history
            analyst_messages = list(state.get(messages_key, []))

            if not analyst_messages:
                # First call: from state["messages"] Extract basic information from
                base_messages = []
                for msg in state.get("messages", []):
                    if isinstance(msg, (HumanMessage, SystemMessage)):
                        base_messages.append(msg)
                analyst_messages = base_messages
                logger.info(f"[analyst] {node_id} - Initialization message history, basic message number: {len(base_messages)}")
            else:
                logger.info(f"[analyst] {node_id} - Use existing message history, number of messages: {len(analyst_messages)}")
                # Print message type
                for i, msg in enumerate(analyst_messages):
                    logger.info(f"[analyst] {node_id} - news[{i}]: {type(msg).__name__}")

            # Create analyst-specific state (using separate messages)
            analyst_state = {**state, "messages": analyst_messages}

            # Call the analyst node
            result = self._execute_agent_node_with_runtime(
                state=analyst_state,
                agent_callable=analyst_node,
                agent_id=agent_id,
                node_id=node_id,
                node_label=node_label,
                output_field=output_field,
                legacy_adapter=True,
            )

            # Print the counter in the returned result
            for key in ["market_tool_call_count", "sentiment_tool_call_count", "news_tool_call_count", "fundamentals_tool_call_count"]:
                if key in result:
                    logger.info(f"[analyst] {node_id} - The return result contains {key}: {result[key]}")

            # Update independent message history and remove shared messages field
            if "messages" in result:
                new_messages = result["messages"]
                if isinstance(new_messages, list):
                    updated_messages = analyst_messages + new_messages
                else:
                    updated_messages = analyst_messages + [new_messages]
                # Store to separate message field
                result[messages_key] = updated_messages
                # Remove shared messages field to avoid contamination
                del result["messages"]
                logger.info(f"[analyst] {node_id} - Update message history, number of messages: {len(updated_messages)}")

            logger.info(f"[Node execution] ✅ {node_id} ({node_label}) - Execution completed")
            return result

        return wrapped_analyst
    
    def _get_default_state_schema(self) -> type:
        """
        Get the default state mode

        Use TypedDict but include __extra_items__ to support dynamic fields
        Refer to the AgentState design of tradingagents
        """
        from typing import Annotated, Any, List
        from typing_extensions import TypedDict
        from langgraph.graph import MessagesState
        import operator
        from core.state.reducers import keep_non_empty, merge_dict, keep_latest_list

        class WorkflowState(MessagesState):
            # Basic information
            company_of_interest: Annotated[str, keep_non_empty]
            trade_date: Annotated[str, keep_non_empty]

            # 🆕 System variables (prepared by the workflow engine on startup)
            ticker: Annotated[str, keep_non_empty]
            analysis_date: Annotated[str, keep_non_empty]
            company_name: Annotated[str, keep_non_empty]
            industry: Annotated[str, keep_non_empty]
            current_price: Annotated[str, keep_non_empty]
            market_name: Annotated[str, keep_non_empty]
            currency_name: Annotated[str, keep_non_empty]
            currency_symbol: Annotated[str, keep_non_empty]
            current_date: Annotated[str, keep_non_empty]
            start_date: Annotated[str, keep_non_empty]

            # Analysis report - using reducer to support concurrent updates
            market_report: Annotated[str, keep_non_empty]
            fundamentals_report: Annotated[str, keep_non_empty]
            news_report: Annotated[str, keep_non_empty]
            sentiment_report: Annotated[str, keep_non_empty]
            index_report: Annotated[str, keep_non_empty]
            sector_report: Annotated[str, keep_non_empty]

            # 🆕 Tool call summary (each analyst's tool call record, for reference by downstream agents)
            # key: analyst_type or agent_id,value: Markdown Format summary text
            tool_call_summaries: Annotated[dict, merge_dict]

            # 🆕 v3.5.0 Quality gate flags (quality inspection results reported by each analyst for downstream and monitoring reference)
            # Each element is {agent_id, analyst_type, ticker, reason, severity, retried} dictionary
            quality_flags: Annotated[list, keep_latest_list]

            # Research results
            bull_report: Annotated[str, keep_non_empty]
            bear_report: Annotated[str, keep_non_empty]
            investment_plan: Annotated[str, keep_non_empty]
            trader_investment_plan: Annotated[str, keep_non_empty]

            # final research conclusion
            final_decision: Annotated[str, keep_non_empty]
            risk_assessment: Annotated[str, keep_non_empty]
            final_trade_decision: Annotated[str, keep_non_empty]

            # 🆕 Transaction review related fields
            trade_info: Annotated[dict, merge_dict]
            market_data: Annotated[dict, merge_dict]
            benchmark_data: Annotated[dict, merge_dict]
            trading_plan: Annotated[dict, merge_dict]  # 🆕 trading plan rules
            timing_analysis: Annotated[str, keep_non_empty]
            position_analysis: Annotated[str, keep_non_empty]
            emotion_analysis: Annotated[str, keep_non_empty]
            attribution_analysis: Annotated[str, keep_non_empty]
            review_summary: Annotated[str, keep_non_empty]

            # Debate status - using merge_dict reducer to handle concurrent updates
            investment_debate_state: Annotated[dict, merge_dict]
            risk_debate_state: Annotated[dict, merge_dict]

            # Debate count - note the use of operator.add to handle concurrent updates
            _debate_debate_count: Annotated[int, operator.add]
            _debate_risk_debate_count: Annotated[int, operator.add]

            # debate configuration
            _max_debate_rounds: Annotated[int, keep_non_empty]
            _max_risk_rounds: Annotated[int, keep_non_empty]

            # A9-P1: Risk Self Debate Switch (True=The deep/comprehensive file takes the single-node self-debate path,
            # False/Default=Take the original risk triangle multi-agent debate path). keep_non_empty guarantee
            # Once injected True will not be overridden by a null return from a parallel node.
            _risk_self_debate: Annotated[bool, keep_non_empty]

            # 🆕 CARE-Agents R1: Structured probability posteriors & CBS debate gating
            analyst_posteriors: Annotated[dict, merge_dict]
            estimated_spread_bps: Annotated[float, keep_non_empty]
            debate_jsd: Annotated[float, keep_non_empty]
            cbs_bps: Annotated[float, keep_non_empty]
            dynamic_debate_rounds: Annotated[int, keep_non_empty]

            # Analyst-independent message history (to avoid message confusion during parallel execution)
            # NOTE: These fields are used in tool call loops, each analyst uses their own message history
            _market_messages: Annotated[List, keep_latest_list]
            _social_messages: Annotated[List, keep_latest_list]
            _news_messages: Annotated[List, keep_latest_list]
            _fundamentals_messages: Annotated[List, keep_latest_list]

            # Analyst tool call count (to prevent infinite loops)
            market_tool_call_count: Annotated[int, keep_non_empty]
            sentiment_tool_call_count: Annotated[int, keep_non_empty]
            news_tool_call_count: Annotated[int, keep_non_empty]
            fundamentals_tool_call_count: Annotated[int, keep_non_empty]

            # v2.0 Debate related fields
            bull_opinion: Annotated[str, keep_non_empty]
            bear_opinion: Annotated[str, keep_non_empty]
            risky_opinion: Annotated[str, keep_non_empty]
            safe_opinion: Annotated[str, keep_non_empty]
            neutral_opinion: Annotated[str, keep_non_empty]

            # Position analysis related fields (v2.0)
            technical_analysis: Annotated[str, keep_non_empty]
            fundamental_analysis: Annotated[str, keep_non_empty]
            risk_analysis: Annotated[str, keep_non_empty]
            action_advice: Annotated[str, keep_non_empty]
            
            # Position information
            position_info: Annotated[dict, merge_dict]
            stock_analysis_report: Annotated[dict, merge_dict]
            user_preference: Annotated[str, keep_non_empty]
            analysis_params: Annotated[dict, merge_dict]

            # 🆕 Debug and context-sensitive fields
            context: Annotated[Any, keep_non_empty]  # AgentContext object
            skip_cache: Annotated[bool, keep_non_empty]  # Whether to skip caching
            prompt_overrides: Annotated[dict, merge_dict]  # Prompt word override

            # 🆕 External fact memory injection (facts extracted by the intelligent assistant online, with collection date and source)
            # Written by UnifiedAnalysisEngine by ticker query at startup, debate session only
            #  (bull/bear) Consumption with the risk assessment link (risk_manager), other links will not be affected
            memory_facts_summary: Annotated[str, keep_non_empty]

        # 🔥 Dynamically inject the output_field of the workshop Agent into State schema
        # LangGraph The StateGraph will only retain the fields declared in the schema, undeclared fields will be discarded
        # Agents created by the workshop (such as valuation_analyst_v1) use custom output_field (such as valuation_report)
        # It must be declared dynamically here, otherwise the output returned by Agent will be discarded by LangGraph
        try:
            from tradingagents.config.mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name
            from pymongo import MongoClient as _MC
            _client = _MC(build_mongodb_connection_string(), serverSelectionTimeoutMS=2000)
            _db = _client[get_mongodb_database_name()]
            _docs = list(_db.agent_configs.find(
                {"enabled": True, "version_status": "active", "runtime_status": "active"},
                {"agent_id": 1, "output_field": 1, "metadata.output_field": 1, "_id": 0},
            ))
            _client.close()
            _builtin_fields = set(WorkflowState.__annotations__.keys())
            _added = []
            for _doc in _docs:
                _field = _doc.get("output_field") or (_doc.get("metadata") or {}).get("output_field")
                if _field and _field not in _builtin_fields and _field not in _added:
                    WorkflowState.__annotations__[_field] = Annotated[str, keep_non_empty]
                    _added.append(_field)
            if _added:
                logger.info(f"[StateSchema] Dynamic injection workshop Agent output_field: {_added}")
        except Exception as _e:
            logger.warning(f"[StateSchema] Dynamic injection of workshop Agent output_field failed: {_e}")

        return WorkflowState
    
    def _create_node_function(self, node: NodeDefinition) -> Callable:
        """Create execution function for node"""

        if node.type == NodeType.CONDITION:
            return self._create_condition_node(node)
        elif node.type == NodeType.PARALLEL:
            return self._create_parallel_node(node)
        elif node.type == NodeType.MERGE:
            return self._create_merge_node(node)
        elif node.type == NodeType.DEBATE:
            return self._create_debate_node(node)
        else:
            return self._create_agent_node(node)

    def _create_agent_node(self, node: NodeDefinition) -> Callable:
        """Create an agent node"""
        agent_id = node.agent_id
        node_id = node.id
        node_label = node.label or node_id

        if agent_id is None:
            raise ValueError(f"node {node.id} missing agent_id")

        # 🔥 Load Agent configuration from database
        db_agent_config = self.agent_config_manager.get_agent_config(agent_id)
        if db_agent_config:
            logger.debug(f"[Agent creation] Load Agent configuration from database: {agent_id}")
            execution_config = db_agent_config.get('config', {})
            logger.debug(f"[Agent creation] Execute configuration: {execution_config}")
        else:
            logger.debug(f"[Agent creation] Database configuration not found, using default configuration: {agent_id}")
            execution_config = {}

        # Merge node configuration (priority:node.config > Database configuration > default configuration)
        # 🔥 Exclude llm_provider and llm_model as these should not be in the Agent configuration
        default_dict = self.default_config.model_dump(exclude={'llm_provider', 'llm_model'})
        execution_config_clean = {k: v for k, v in execution_config.items() if k not in ['llm_provider', 'llm_model']}
        node_config_clean = {k: v for k, v in (node.config or {}).items() if k not in ['llm_provider', 'llm_model']}
        
        # 🔥 Create a configuration dictionary, explicitly setting llm_provider and llm_model to None to override the defaults
        config_dict = {
            **default_dict,
            **execution_config_clean,
            **node_config_clean,
            'llm_provider': None,  # 🔥 Explicitly set to None, overriding AgentConfig's default value "deepseek"
            'llm_model': None      # 🔥 Explicitly set to None
        }
        
        config = AgentConfig(**config_dict)
        
        # 🔥 Validate and clean again after creation: recreate using exclude to make sure these fields are not in the final configuration
        config_dict_clean = config.model_dump(exclude={'llm_provider', 'llm_model'})
        # When recreating, since these fields are not in the dictionary, Pydantic will use the default values, so we need to set them explicitly again
        config_dict_clean['llm_provider'] = None
        config_dict_clean['llm_model'] = None
        config = AgentConfig(**config_dict_clean)
        
        # 🔥 Final validation: log warning if these fields are still present in model_dump with values
        final_dict = config.model_dump()
        if final_dict.get('llm_provider') not in [None, '']:
            logger.warning(f"⚠️ Agent The configuration still contains llm_provider={final_dict.get('llm_provider')}, this shouldn t happen")

        # First try to create an agent using the new schema (registered OR with agent_configs record in database)
        if self.registry.is_registered(agent_id) or self._has_agent_config_in_db(agent_id):
            logger.info(f"=" * 80)
            logger.info(f"[Agent creation] Start creating Agent: {agent_id} (node={node_id})")

            # 🆕 Three-level priority tool query:node > workflow > agent Default
            tool_ids = self.binding_manager.get_tools_for_node(
                agent_id=agent_id,
                workflow_id=self._workflow_id,
                node_id=node_id,
            )
            if tool_ids:
                logger.info(f"[Agent creation] 🔧 Get tools from BindingManager (Three levels of priority): {agent_id} -> {tool_ids}")
            else:
                logger.warning(f"[Agent creation] ⚠️ No tool bindings found: {agent_id}")

            # 🔥 Key fix: Determine whether to use quick or based on agent_id deep LLM
            llm_type = _select_llm_type_for_agent(agent_id)
            agent_temperature = node_config_clean.get("temperature", execution_config_clean.get("temperature"))
            agent_timeout = node_config_clean.get("timeout", execution_config_clean.get("timeout"))
            agent_max_tokens = node_config_clean.get("max_tokens", execution_config_clean.get("max_tokens"))

            if self.llm_override:
                llm = self.llm_override
            elif any(value is not None for value in (agent_temperature, agent_timeout, agent_max_tokens)):
                llm = self._legacy_provider.get_llm(
                    llm_type,
                    temperature=agent_temperature,
                    timeout=agent_timeout,
                    max_tokens=agent_max_tokens,
                )
            else:
                llm = self._legacy_provider.get_llm(llm_type)
            logger.debug(
                f"[Agent creation] LLM: type={llm_type}, temp={agent_temperature}, "
                f"timeout={agent_timeout}, max_tokens={agent_max_tokens}"
            )

            agent_memory = None
            if self.memory_manager:
                try:
                    agent_memory = self.memory_manager.get_agent_memory(agent_id)
                except Exception as mem_error:
                    logger.warning(f"[Agent creation] Failed to obtain memory instance: {mem_error}")

            agent = self.factory.create(
                agent_id,
                config,
                llm=llm,
                tool_ids=tool_ids,
                memory=agent_memory
            )

            if hasattr(agent, 'set_dependencies'):
                toolkit = self._legacy_provider.get_toolkit()
                agent.set_dependencies(llm, toolkit)

            self._agents[node.id] = agent
            logger.info(f"[Agent creation] {agent_id} -> {type(agent).__name__} (tools={len(getattr(agent, '_tools', []) or [])})")

            # Wrap to add logs
            self._ensure_workflow_surface_access(agent_id, db_agent_config)
            output_field = self._resolve_agent_output_field(agent_id, node.config, db_agent_config)

            def logged_agent(state, _agent=agent, _id=node_id, _label=node_label, _agent_id=agent_id, _output_field=output_field):
                return self._execute_agent_node_with_runtime(
                    state=state,
                    agent_callable=_agent,
                    agent_id=_agent_id,
                    node_id=_id,
                    node_label=_label,
                    output_field=_output_field,
                    node_config=node.config,
                )
            return logged_agent

        # Try using legacy adapter
        legacy_node = self._try_create_legacy_agent(agent_id)
        if legacy_node is not None:
            self._agents[node.id] = legacy_node
            logger.info(f"[Agent creation] ✅ Created using legacy adapter: {agent_id} -> node_id: {node.id}")

            self._ensure_workflow_surface_access(agent_id, db_agent_config)
            output_field = self._resolve_agent_output_field(agent_id, node.config, db_agent_config)

            # Check if it is an analyst node (requires independent message history)
            if agent_id in ANALYST_TOOL_MAPPING:
                analyst_type = ANALYST_TOOL_MAPPING[agent_id]
                return self._create_analyst_wrapper(
                    legacy_node,
                    node_id,
                    node_label,
                    agent_id,
                    analyst_type,
                    output_field=output_field,
                )

            def logged_legacy(state, _node=legacy_node, _id=node_id, _label=node_label, _agent_id=agent_id, _output_field=output_field):
                return self._execute_agent_node_with_runtime(
                    state=state,
                    agent_callable=_node,
                    agent_id=_agent_id,
                    node_id=_id,
                    node_label=_label,
                    output_field=_output_field,
                    node_config=node.config,
                    legacy_adapter=True,
                )
            return logged_legacy

        # The agent is not implemented and returns the placeholder function.
        def placeholder_node(state, _id=node_id, _label=node_label, _agent_id=agent_id):
            logger.info(f"[Node execution] 🔸 {_id} ({_label}) - Placeholder execution (agent {_agent_id} Not implemented)")
            return {
                f"{_agent_id}_report": f"[{_agent_id}] Agent is not implemented"
            }
        return placeholder_node

    def _has_agent_config_in_db(self, agent_id: str) -> bool:
        """
        Check if a configuration for this agent_id exists in the agent_configs collection.

        Used to determine whether an unregistered Agent can be replaced by a UniversalAgent.
        """
        try:
            db = self.binding_manager._db
            if db is None:
                return False
            doc = db.agent_configs.find_one({
                "agent_id": agent_id,
                "enabled": True,
                "$or": [
                    {"metadata.source": {"$ne": "agent_workshop"}},
                    {"metadata.source": "agent_workshop", "version_status": "active", "runtime_status": "active"},
                ],
            }, {"_id": 1})
            return doc is not None
        except Exception:
            return False

    def _normalize_callable_surfaces(self, raw_surfaces: Optional[List[Any]]) -> Set[str]:
        normalized = {
            str(item).strip().lower()
            for item in (raw_surfaces or [])
            if str(item).strip()
        }
        return normalized or set(_DEFAULT_CALLABLE_SURFACES)

    def _ensure_workflow_surface_access(
        self,
        agent_id: str,
        db_agent_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = self.registry.get_metadata(agent_id)
        metadata_surfaces = getattr(metadata, "callable_surfaces", None)
        db_surfaces = ((db_agent_config or {}).get("metadata") or {}).get("callable_surfaces")
        allowed_surfaces = self._normalize_callable_surfaces(db_surfaces or metadata_surfaces)

        if "workflow" not in allowed_surfaces:
            raise ValueError(f"Agent {agent_id} Direct calls from the workflow entry are currently not allowed")

    def _resolve_agent_output_field(
        self,
        agent_id: str,
        node_config: Optional[Dict[str, Any]] = None,
        db_agent_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        config = node_config or {}
        if config.get("output_field"):
            return str(config["output_field"])

        if (db_agent_config or {}).get("output_field"):
            return str(db_agent_config["output_field"])

        db_metadata = (db_agent_config or {}).get("metadata") or {}
        if db_metadata.get("output_field"):
            return str(db_metadata["output_field"])

        metadata = self.registry.get_metadata(agent_id)
        if metadata and getattr(metadata, "output_field", None):
            return str(metadata.output_field)
        if metadata and getattr(metadata, "outputs", None):
            outputs = getattr(metadata, "outputs", []) or []
            if outputs and getattr(outputs[0], "name", None):
                return str(outputs[0].name)
        return None

    def _sanitize_runtime_value(self, value: Any, max_text_length: int = 2000, depth: int = 0) -> Any:
        if isinstance(value, str):
            return value[:max_text_length]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if depth >= 1:
            return str(value)[:max_text_length]
        if isinstance(value, list):
            return [self._sanitize_runtime_value(item, max_text_length=max_text_length, depth=depth + 1) for item in value[:10]]
        if isinstance(value, dict):
            sanitized: Dict[str, Any] = {}
            for key, item in list(value.items())[:20]:
                sanitized[str(key)] = self._sanitize_runtime_value(item, max_text_length=max_text_length, depth=depth + 1)
            return sanitized
        return str(value)[:max_text_length]

    def _build_workflow_payload(self, state: Any) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return {"raw_state": self._sanitize_runtime_value(state)}

        payload: Dict[str, Any] = {}
        preferred_keys = [
            "symbol",
            "ticker",
            "stock_symbol",
            "stock_code",
            "trade_date",
            "analysis_date",
            "market_type",
            "task",
            "task_description",
            "query",
        ]

        for key in preferred_keys:
            if key in state:
                payload[key] = self._sanitize_runtime_value(state.get(key))

        if not payload:
            snapshot = {}
            for key, value in state.items():
                if key.startswith("_") or key == "messages":
                    continue
                snapshot[key] = self._sanitize_runtime_value(value)
                if len(snapshot) >= 12:
                    break
            payload["state_snapshot"] = snapshot

        return payload

    def _extract_report_text(self, result: Dict[str, Any], output_field: Optional[str]) -> str:
        candidate_fields = [
            output_field,
            "final_report",
            "analysis_report",
            "summary",
            "analysis_result",
        ]
        for field_name in candidate_fields:
            if not field_name:
                continue
            value = result.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                for nested_key in ("content", "markdown", "text", "message", "report"):
                    nested_value = value.get(nested_key)
                    if isinstance(nested_value, str) and nested_value.strip():
                        return nested_value.strip()

        for value in result.values():
            if isinstance(value, str) and value.strip() and len(value.strip()) > 20:
                return value.strip()
        return ""

    def _sanitize_structured_output(self, result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {"raw_result": self._sanitize_runtime_value(result, max_text_length=4000)}

        sanitized: Dict[str, Any] = {}
        for key, value in result.items():
            if key == "messages":
                continue
            sanitized[str(key)] = self._sanitize_runtime_value(value, max_text_length=4000)
        return sanitized

    def _build_workflow_invocation_request(
        self,
        *,
        state: Any,
        agent_id: str,
        node_id: str,
        node_label: str,
        output_field: Optional[str],
        timeout_seconds: int,
    ) -> InvocationRequest:
        runtime_context = {}
        user_id = None
        thread_id = None
        execution_id = None
        parent_invocation_id = None
        root_invocation_id = None
        if isinstance(state, dict):
            runtime_context = dict(state.get("_workflow_runtime") or {})
            user_id = state.get("user_id") or runtime_context.get("user_id")
            thread_id = state.get("thread_id") or runtime_context.get("thread_id")
            execution_id = state.get("execution_id") or runtime_context.get("execution_id")
            lineage = state.get("invocation_lineage") if isinstance(state.get("invocation_lineage"), dict) else {}
            parent_invocation_id = lineage.get("current_invocation_id") or lineage.get("parent_invocation_id")
            root_invocation_id = lineage.get("root_invocation_id")
            if not user_id:
                context = state.get("context")
                if isinstance(context, dict):
                    user_id = context.get("user_id")
                    thread_id = thread_id or context.get("thread_id") or context.get("session_id")
                    execution_id = execution_id or context.get("request_id")
                    extra = context.get("extra") if isinstance(context.get("extra"), dict) else {}
                    parent_invocation_id = parent_invocation_id or context.get("request_id") or extra.get("invocation_id")
                    root_invocation_id = root_invocation_id or extra.get("root_invocation_id") or parent_invocation_id
                elif context is not None:
                    user_id = getattr(context, "user_id", None)
                    thread_id = thread_id or getattr(context, "thread_id", None) or getattr(context, "session_id", None)
                    execution_id = execution_id or getattr(context, "request_id", None)
                    extra = getattr(context, "extra", None)
                    if isinstance(extra, dict):
                        parent_invocation_id = parent_invocation_id or getattr(context, "request_id", None) or extra.get("invocation_id")
                        root_invocation_id = root_invocation_id or extra.get("root_invocation_id") or parent_invocation_id

        workflow_id = runtime_context.get("workflow_id") or self._workflow_id
        execution_id = execution_id or runtime_context.get("execution_id")
        invocation_id = f"winv_{uuid.uuid4().hex}"
        idempotency_key = f"{execution_id}:{node_id}" if execution_id else invocation_id

        return InvocationRequest(
            invocation_id=invocation_id,
            target_type=InvocationTargetType.AGENT,
            target_id=agent_id,
            action="execute",
            payload=self._build_workflow_payload(state),
            provenance=InvocationProvenance(
                source_type=InvocationSourceType.WORKFLOW,
                source_id=workflow_id,
                user_id=user_id,
                session_id=execution_id,
                thread_id=thread_id,
                workflow_id=workflow_id,
                step_id=node_id,
                trigger="workflow_node",
                metadata={
                    "node_label": node_label,
                    "state_keys": [
                        key for key in list(state.keys())[:30]
                        if isinstance(state, dict) and not str(key).startswith("_")
                    ] if isinstance(state, dict) else [],
                },
            ),
            policy=InvocationPolicy(
                idempotency_key=idempotency_key,
                timeout_seconds=timeout_seconds,
                lane=f"workflow.{workflow_id or 'default'}",
                visible_to_caller=True,
            ),
            metadata={
                "invocation_source": "workflow_builder",
                "node_id": node_id,
                "node_label": node_label,
                "output_field": output_field,
                "root_invocation_id": root_invocation_id or parent_invocation_id or invocation_id,
                "parent_invocation_id": parent_invocation_id,
            },
        )

    def _persist_workflow_invocation_record(
        self,
        request: InvocationRequest,
        result: InvocationResult,
    ) -> None:
        db = getattr(self.binding_manager, "_db", None)
        if db is None:
            return

        db.workflow_agent_invocations.update_one(
            {"invocation_id": request.invocation_id},
            {
                "$set": {
                    "invocation_id": request.invocation_id,
                    "root_invocation_id": request.metadata.get("root_invocation_id") or request.invocation_id,
                    "parent_invocation_id": request.metadata.get("parent_invocation_id"),
                    "workflow_id": request.provenance.workflow_id,
                    "execution_id": request.provenance.session_id,
                    "thread_id": request.provenance.thread_id,
                    "step_id": request.provenance.step_id,
                    "user_id": request.provenance.user_id,
                    "target_type": request.target_type.value,
                    "target_id": request.target_id,
                    "status": result.status.value,
                    "request": request.to_python_dict(),
                    "result": result.to_python_dict(),
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )

    def _execute_agent_node_with_runtime(
        self,
        *,
        state: Any,
        agent_callable: Callable,
        agent_id: str,
        node_id: str,
        node_label: str,
        output_field: Optional[str],
        node_config: Optional[Dict[str, Any]] = None,
        legacy_adapter: bool = False,
    ) -> Dict[str, Any]:
        logger.info(
            f"[Node execution] 🚀 {node_id} ({node_label}) - Start execution"
            + (f" (legacy adapter: {agent_id})" if legacy_adapter else "")
        )

        agent_metadata = self.registry.get_metadata(agent_id)
        agent_version = getattr(agent_metadata, "version", None)
        raw_maintenance_status = getattr(agent_metadata, "maintenance_status", None)
        if raw_maintenance_status is not None:
            agent_maintenance_status = getattr(raw_maintenance_status, "value", str(raw_maintenance_status))
        else:
            normalized_version = str(agent_version or "").lower()
            agent_maintenance_status = "unmaintained" if normalized_version.startswith(("1", "v1")) else "maintained"

        # 🔥 Check if it is obsolete Agent
        if agent_maintenance_status == "deprecated":
            import warnings
            warnings.warn(
                f"Agent '{agent_id}' Deprecated, please use v2 version. This agent will be removed in a future release.",
                DeprecationWarning,
                stacklevel=3
            )
            logger.warning(f"[Node execution] ⚠️ Agent '{agent_id}' Deprecated, it is recommended to use v2 version")

        invocation_request = self._build_workflow_invocation_request(
            state=state,
            agent_id=agent_id,
            node_id=node_id,
            node_label=node_label,
            output_field=output_field,
            timeout_seconds=180,
        )
        started_at = utc_now()

        _trace_recorder = None  # 🔑 Unified execution track buried point: initialize in advance to ensure that finally is available
        try:
            agent_state = state
            if isinstance(state, dict):
                agent_state = {
                    **state,
                    "node_id": node_id,
                    "node_config": dict(node_config or {}),
                    "invocation_provenance": invocation_request.provenance.to_python_dict(),
                    "invocation_lineage": {
                        "current_invocation_id": invocation_request.invocation_id,
                        "parent_invocation_id": invocation_request.metadata.get("parent_invocation_id"),
                        "root_invocation_id": invocation_request.metadata.get("root_invocation_id") or invocation_request.invocation_id,
                    },
                }

            import time as _time
            _agent_start = _time.time()
            logger.info(f"[Node execution] ⏳ {node_id} ({node_label}) - call agent_callable...")
            # 🔑 Unified execution trajectory burying point: start trajectory collection at the node execution level
            # In this way, no matter whether the adapter covers execute or not, the trace can be recorded.
            _agent_obj = agent_callable if hasattr(agent_callable, 'execute') else None
            _trace_recorder = None
            if _agent_obj is not None:
                from core.agents.execution_trace_recorder import start_execution_trace, is_trace_enabled
                if is_trace_enabled():
                    try:
                        _trace_recorder = start_execution_trace(_agent_obj, agent_state)
                        _agent_obj._last_trace_id = _trace_recorder.trace_id
                    except Exception as _trace_err:
                        logger.warning(f"⚠️ [Node execution] Failed to start trajectory collection (does not affect execution): {_trace_err}")

            raw_result = agent_callable(agent_state)
            _agent_elapsed = _time.time() - _agent_start
            logger.info(f"[Node execution] ⏱️ {node_id} ({node_label}) - agent_callable Execution completed, Time consuming: {_agent_elapsed:.1f}s")
            result = raw_result if isinstance(raw_result, dict) else {
                (output_field or f"{agent_id}_report"): raw_result
            }

            # 🔑 Unified execution trace buried points: record the output after analysis
            if _trace_recorder:
                try:
                    _trace_recorder.record_parsed_output(result)
                except Exception:
                    pass

            logger.info(f"[Node execution] 📝 {node_id} ({node_label}) - Return field: {list(result.keys())}")

            invocation_result = InvocationResult(
                invocation_id=invocation_request.invocation_id,
                target_type=InvocationTargetType.AGENT,
                target_id=agent_id,
                status=InvocationStatus.SUCCEEDED,
                started_at=started_at,
                output_text=self._extract_report_text(result, output_field),
                structured_output=self._sanitize_structured_output(result),
                output_field=output_field,
                artifacts=[
                    InvocationArtifactRef(
                        ref_type="workflow_agent_invocation",
                        artifact_key=invocation_request.invocation_id,
                        title=f"Workflow Node call:{node_label}",
                        summary=self._extract_report_text(result, output_field)[:300],
                        source_collection="workflow_agent_invocations",
                        output_field=output_field,
                        metadata={
                            "agent_id": agent_id,
                            "agent_version": agent_version,
                            "maintenance_status": agent_maintenance_status,
                            "node_id": node_id,
                            "workflow_id": invocation_request.provenance.workflow_id,
                        },
                    )
                ],
                metadata={
                    "node_id": node_id,
                    "node_label": node_label,
                    "workflow_id": invocation_request.provenance.workflow_id,
                    "execution_id": invocation_request.provenance.session_id,
                    "agent_version": agent_version,
                    "maintenance_status": agent_maintenance_status,
                    "legacy_adapter": legacy_adapter,
                    "root_invocation_id": invocation_request.metadata.get("root_invocation_id") or invocation_request.invocation_id,
                    "parent_invocation_id": invocation_request.metadata.get("parent_invocation_id"),
                },
            )
            self._persist_workflow_invocation_record(invocation_request, invocation_result)

            logger.info(f"[Node execution] ✅ {node_id} ({node_label}) - Execution completed")
            return result
        except Exception as exc:
            # 🔑 Unified execution trace buried points: recording exceptions
            if _trace_recorder:
                try:
                    _trace_recorder.record_error(exc)
                except Exception:
                    pass

            invocation_result = InvocationResult(
                invocation_id=invocation_request.invocation_id,
                target_type=InvocationTargetType.AGENT,
                target_id=agent_id,
                status=InvocationStatus.FAILED,
                started_at=started_at,
                output_field=output_field,
                error_message=str(exc),
                metadata={
                    "node_id": node_id,
                    "node_label": node_label,
                    "workflow_id": invocation_request.provenance.workflow_id,
                    "execution_id": invocation_request.provenance.session_id,
                    "agent_version": agent_version,
                    "maintenance_status": agent_maintenance_status,
                    "legacy_adapter": legacy_adapter,
                },
            )
            self._persist_workflow_invocation_record(invocation_request, invocation_result)
            logger.exception(f"[Node execution] ❌ {node_id} ({node_label}) - Execution failed: {exc}")

            field_key = output_field or f"{agent_id}_report"
            degraded = {
                field_key: (
                    f"[{node_label} Execution failed]\n\n"
                    f"The analysis node encountered an error during operation and has been skipped.\n"
                    f"Error summary: {type(exc).__name__}\n\n"
                    f"The analysis results of the remaining nodes are not affected, please refer to other reports."
                ),
                f"_node_errors": {
                    **(state.get("_node_errors", {}) if isinstance(state, dict) else {}),
                    node_id: {
                        "agent_id": agent_id,
                        "label": node_label,
                        "error": str(exc)[:500],
                    },
                },
            }
            logger.warning(
                f"[Node execution] ⚠️ {node_id} ({node_label}) - Downgrade processing, workflow continues execution"
            )
            return degraded
        finally:
            # 🔑 Unified execution trace buried points: complete collection and write to MongoDB (non-blocking)
            if _trace_recorder:
                try:
                    _trace_recorder.finish()
                except Exception:
                    pass

    def _try_create_legacy_agent(self, agent_id: str) -> Optional[Callable]:
        """
        Try creating an agent using a legacy adapter — Deactivated

        v3.0 The old version of the agent (without the _v2 suffix) is no longer maintained, and all entrances have been blocked.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Args:
            agent_id: agent ID

        Returns:
            Always returns None (the old version of agent has been deactivated, use placeholder_node as placeholder)
        """
        logger.warning(
            "[Deactivated] _try_create_legacy_agent deactivated,agent_id=%s The corresponding _v2 version should be used."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md",
            agent_id,
        )
        return None
        # pragma: no cover - The following legacy factory_map code is retained but not executed in preparation for v4.0 removal
        # Mapping of agents to factory functions
        factory_map = {
            # analyst
            "market_analyst": ("tradingagents.agents.analysts.market_analyst", "create_market_analyst", "toolkit"),
            "news_analyst": ("tradingagents.agents.analysts.news_analyst", "create_news_analyst", "toolkit"),
            "fundamentals_analyst": ("tradingagents.agents.analysts.fundamentals_analyst", "create_fundamentals_analyst", "toolkit"),
            "social_analyst": ("tradingagents.agents.analysts.social_media_analyst", "create_social_media_analyst", "toolkit"),
            # 🆕 Market analysts and sector analysts (toolkit is required, but the tool calling mechanism is not used internally)
            "index_analyst": ("tradingagents.agents.analysts.index_analyst", "create_index_analyst", "toolkit"),
            "sector_analyst": ("tradingagents.agents.analysts.sector_analyst", "create_sector_analyst", "toolkit"),
            # researcher
            "bull_researcher": ("tradingagents.agents.researchers.bull_researcher", "create_bull_researcher", "bull_memory"),
            "bear_researcher": ("tradingagents.agents.researchers.bear_researcher", "create_bear_researcher", "bear_memory"),
            # research integrator
            "trader": ("tradingagents.agents.trader.trader", "create_trader", "trader_memory"),
            # manager
            "research_manager": ("tradingagents.agents.managers.research_manager", "create_research_manager", "invest_judge_memory"),
            "risk_manager": ("tradingagents.agents.managers.risk_manager", "create_risk_manager", "risk_manager_memory"),
            # risk debater
            "risky_analyst": ("tradingagents.agents.risk_mgmt.aggresive_debator", "create_risky_debator", None),
            "safe_analyst": ("tradingagents.agents.risk_mgmt.conservative_debator", "create_safe_debator", None),
            "neutral_analyst": ("tradingagents.agents.risk_mgmt.neutral_debator", "create_neutral_debator", None),
        }

        if agent_id not in factory_map:
            return None

        module_path, func_name, dep_type = factory_map[agent_id]

        try:
            import importlib
            module = importlib.import_module(module_path)
            factory_func = getattr(module, func_name)

            # 🔥 Key fix: Determine whether to use quick or based on agent_id deep LLM
            # Agent using deep model:
            # 1. manager (research_manager, risk_manager) - Need to synthesize large amounts of information to make decisions
            # 2. Risk Analyst (risky/safe/neutral_analyst) - needs to process a large number of analysis reports
            llm_type = "quick"  # Use fast model by default
            if agent_id in [
                "research_manager", "risk_manager",  # manager
                "risky_analyst", "safe_analyst", "neutral_analyst"  # Legacy Risk Analyst
            ]:
                llm_type = "deep"  # Use deep models
                logger.info(f"[legacy adapter] 🔧 {agent_id} Use deep analysis models (deep_think_llm)")
            else:
                logger.info(f"[legacy adapter] 🔧 {agent_id} Use rapid analysis models (quick_think_llm)")
            
            # 🔥 Get the temperature of the Agent configuration (if it exists)
            # Note: Agents created by legacy adapters may not have configuration loaded from the database
            # The default LLM is used here temporarily, and improvements can be considered in the future.
            llm = self._legacy_provider.get_llm(llm_type)

            # Get the second parameter based on the dependency type
            if dep_type == "toolkit":
                second_arg = self._legacy_provider.get_toolkit()
            elif dep_type:
                second_arg = self._legacy_provider.get_memory(dep_type)
            else:
                second_arg = None

            # Create node function
            if second_arg is not None:
                node_func = factory_func(llm, second_arg)
            else:
                # risk debaters just need LLM
                node_func = factory_func(llm)

            logger.info(f"[legacy adapter] Created successfully: {agent_id}")
            return node_func

        except Exception as e:
            logger.warning(f"[legacy adapter] Creation failed {agent_id}: {e}")
            return None

    def _create_condition_node(self, node: NodeDefinition) -> Callable:
        """Create condition node"""
        condition_expr = node.condition or "True"
        node_id = node.id
        node_label = node.label or node_id

        def condition_node(state):
            logger.info(f"[Node execution] 🔀 {node_id} ({node_label}) - Conditional judgment")
            # Evaluation conditions
            try:
                result = eval(condition_expr, {"state": state})
                logger.info(f"[Node execution] 🔀 {node_id} result: {result}")
                return {"_condition_result": bool(result)}
            except Exception as e:
                logger.error(f"[Node execution] ❌ {node_id} Condition evaluation error: {e}")
                return {"_condition_result": True, "_condition_error": str(e)}

        return condition_node

    def _create_parallel_node(self, node: NodeDefinition) -> Callable:
        """Create parallel nodes (mark start)"""
        node_id = node.id
        node_label = node.label or node_id

        def parallel_node(state):
            logger.info(f"[Node execution] ⚡ {node_id} ({node_label}) - Start in parallel")
            return {"_parallel_start": node_id}
        return parallel_node

    def _create_merge_node(self, node: NodeDefinition) -> Callable:
        """Create merge node"""
        node_id = node.id
        node_label = node.label or node_id

        def merge_node(state):
            logger.info(f"[Node execution] 🔗 {node_id} ({node_label}) - Merge completed")
            return {"_parallel_end": node_id}
        return merge_node

    def _create_debate_node(self, node: NodeDefinition) -> Callable:
        """
        Create debate nodes - coordinate multiple participants for multiple debate rounds

        The debate node itself does not perform analysis, but initializes the debate state.
        The actual debate flow is controlled through conditional edges.

        Important: The debate status dictionary must be initialized, containing count=0, 
        Because the researcher agent expects state["investment_debate_state"]["count"] exist
        """
        participants = node.config.get("participants", [])
        rounds = node.config.get("rounds", 1)
        node_id = node.id
        node_label = node.label or node_id

        # Determine the state key to initialize based on the debate node ID
        # "debate" -> investment_debate_state
        # "risk_debate" -> risk_debate_state
        is_risk_debate = "risk" in node_id.lower()
        state_key = "risk_debate_state" if is_risk_debate else "investment_debate_state"

        def debate_node(state):
            logger.info(f"[Node execution] 💬 {node_id} ({node_label}) - Debate begins, participants: {participants}")

            # Initialize debate status dictionary
            # This is the state structure expected by the researcher's agent
            if is_risk_debate:
                # The state of the risk debate
                debate_state = {
                    "risky_history": "",
                    "safe_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_risky_response": "",
                    "current_safe_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            else:
                # The state of the investment debate
                debate_state = {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }

            logger.info(f"[Debate initialization] initialization {state_key} Status: count=0")

            return {
                f"{node_id}_status": "debate_started",
                "_debate_node": node_id,
                "_debate_participants": participants,
                "_debate_rounds": rounds,
                state_key: debate_state,  # 🔥 Key: Initialize debate state
            }
        return debate_node

    def _create_debate_participant_wrapper(
        self,
        node: NodeDefinition,
        debate_key: str
    ) -> Callable:
        """
        Wrapping execution functions for debate participants to automatically increment the debate count

        Use operator.add as reducer to return increment each time 1
        """
        original_func = self._create_agent_node(node)

        def wrapped(state):
            # Execute the original function first (log included)
            result = original_func(state)
            # Returns increment 1 (will be accumulated to the current value by operator.add)
            result[debate_key] = 1
            return result

        return wrapped

    @staticmethod
    def _merge_debate_states(
        old: Optional[Dict[str, Any]],
        new: Dict[str, Any],
    ) -> Dict[str, Any]:
        """A3: Merge two debate states according to the order of speech (only for parallel start)

        Rules:
        - history: Splicing in order of participants (to ensure the complete debate history is in order)
        - Other fields (respective *_history / current_response / latest_speaker) : 
          Non-null values take precedence (to avoid overwriting each other as null when both parallel parties copy based on the same initial state)
        """
        if not old:
            return dict(new)
        merged = dict(old)
        for k, v in new.items():
            if k == "history":
                merged["history"] = (
                    str(merged.get("history") or "") + "\n" + str(v or "")
                ).strip("\n")
            elif v not in (None, ""):
                merged[k] = v
        return merged

    def _create_parallel_opening_node_func(
        self,
        debate_id: str,
        config: Dict[str, Any],
        definition: WorkflowDefinition,
    ) -> Callable:
        """A3: Create a parallel opening node for the first round of investment debate

        Internally, a thread pool is used to execute all participants in parallel (optimistic/cautious researchers are each based on the same
        Analyst material independently produces initial briefing), manually merges and shares debate_state,
        count Increment = Number of participants (accumulated by operator.add reducer).

        The outgoing edge is routed conditionally by _add_edges:count >= max → next_node (Such as
        research_manager) ; Otherwise return to round robin(participants[count % N] continue
        adversarial debate). The original serial path passes state["_parallel_opening"] The switch is retained.
        """
        participants = list(config["participants"])
        debate_key = config["debate_key"]
        # Exclusively for investment debates (risk debates are taken over by A9-P1 and do not take this path)
        debate_state_field = "investment_debate_state"

        # Pre-create the original execution function of the participant (create Agent instance independently each time, concurrency safety)
        participant_funcs = []
        for pid in participants:
            node_def = definition.get_node(pid)
            if node_def is None:
                raise ValueError(f"Parallel start: participant node does not exist: {pid}")
            participant_funcs.append((pid, self._create_node_function(node_def)))

        def parallel_opening_node(state):
            t0 = time.time()
            logger.info(
                f"[Node execution] ⚡ {debate_id}_parallel_opening (Debate starts in parallel) - "
                f"Participants execute in parallel: {participants}"
            )
            # Shallow copy state isolates concurrent reading and writing
            with ThreadPoolExecutor(max_workers=len(participant_funcs)) as pool:
                futures = {
                    pid: pool.submit(fn, dict(state))
                    for pid, fn in participant_funcs
                }
                # Collect in order of participation (guaranteed that the history splicing order is determined)
                results = {pid: futures[pid].result() for pid, _ in participant_funcs}

            # Merge: direct union of independent fields (bull_report / bear_report, etc.);
            # Share debate_state deep merge
            merged: Dict[str, Any] = {}
            merged_debate: Optional[Dict[str, Any]] = None
            for pid, res in (results or {}).items():
                if not isinstance(res, dict):
                    logger.warning(f"[A3] participants {pid} Return non-dict results, skip: {type(res)}")
                    continue
                for k, v in res.items():
                    if k == debate_state_field and isinstance(v, dict):
                        merged_debate = self._merge_debate_states(merged_debate, v)
                    else:
                        merged[k] = v
            if merged_debate is None:
                merged_debate = dict(state.get(debate_state_field) or {})
            merged[debate_state_field] = merged_debate
            # count Increment = Number of participants (operator.add reducer accumulates to current value)
            merged[debate_key] = len(participants)
            logger.info(
                f"[Node execution] ✅ {debate_id}_parallel_opening - Parallel start completed, "
                f"Time consuming {time.time() - t0:.1f}s, participants {len(participants)} a"
            )
            return merged

        return parallel_opening_node

    def _create_risk_self_debate_node_func(self, debate_id: str) -> Callable:
        """
        A9-P1: Create risk self-debate node function (single node replaces risk triangle multi-round debate).

        Construct and synthesize NodeDefinition to reuse the complete creation chain of _create_agent_node
         (Database configuration merging, deep LLM selection, execution trajectory packaging, etc.),
        agent Implemented as core/agents/adapters/risk_self_debate_v2.py.
        """
        node = NodeDefinition(
            id=f"{debate_id}_self_debate",
            type=NodeType.RISK,
            agent_id="risk_self_debate_v2",
            label="Self-debate from three perspectives of risk",
            config={
                "description": "Complete high-resilience/defense/baseline three-perspective cross-examination within a single node (A9-P1 depth file path)",
            },
        )
        return self._create_agent_node(node)

    def _create_manager_with_debate_reflection(
        self,
        node: NodeDefinition,
        debate_state_field: str,
    ) -> Callable:
        """Wrap execution functions for manager nodes (research_manager / risk_manager).

        v3.6.0 Item 8: After the manager produces a ruling, the debate reflection node is triggered and the debate history is+ruling
        Distilled into a structured debate_lesson lesson, written into the AGENT_EXPERIENCE scope.

        Reflection is executed in a separate thread (run_reflection_sync internally handles sync→async) , 
        The helper is internally demoted on failure and does not block the main workflow.
        """
        original_func = self._create_agent_node(node)
        node_id = node.id
        agent_id = node.agent_id or node_id
        debate_type = (
            "risk_debate_state" if debate_state_field == "risk_debate_state"
            else "investment_debate_state"
        )

        def wrapped(state):
            # 1. First execute the manager's original logic (output judge_decision / final_trade_decision, etc.)
            result = original_func(state)

            # 2. Trigger debate reflection (failure does not affect the main process)
            try:
                _trigger_debate_reflection(
                    state=state,
                    result=result,
                    debate_state_field=debate_state_field,
                    debate_type=debate_type,
                    agent_id=agent_id,
                    node_id=node_id,
                )
            except Exception as exc:
                logger.warning(
                    "[Debate reflection] Trigger failed node=%s agent=%s: %s",
                    node_id, agent_id, exc,
                )

            return result

        return wrapped

    def _add_edges(
        self,
        graph: StateGraph,
        definition: WorkflowDefinition,
        debate_configs: Optional[Dict[str, Dict[str, Any]]] = None,
        analyst_nodes_info: Optional[Dict[str, str]] = None,
        risk_self_debate_nodes: Optional[Set[str]] = None,
        parallel_opening_nodes: Optional[Set[str]] = None,
    ) -> None:
        """
        Add edges to graph

        Debate process design:
        - debate node → First participant (normal side)
        - Use conditional edges between participants (check count to decide continue or end)
        - last participant → Next stage (controlled by conditional edges)
        - A9-P1: The risk debate entry uses conditional edges,state["_risk_self_debate"]=True time
          Route to the hidden self-debate single node (deep/full file), otherwise follow the original participant path
        - A3: The investment debate entrance uses conditional edges,state["_parallel_opening"]=True time
          Route to hidden parallel opening node (first round optimistic/cautious researcher parallel opening briefing,
          Subsequent rounds will return to the original round robin), otherwise the original serial participant path will be followed.

        Analyst tool loop design:
        - Analyst Node → conditional edge → Tool node/message cleaning node
        - tool node → Analyst node (loop)
        - Message cleaning node → next node
        """
        start_node = definition.get_start_node()
        added_edges: Set[tuple] = set()
        merge_barriers: Dict[str, Set[str]] = {}

        def add_merge_predecessor(merge_node_id: str, predecessor: str) -> None:
            merge_barriers.setdefault(merge_node_id, set()).add(predecessor)
            logger.info(f"[merge barrier] Collect upstream: {predecessor} -> {merge_node_id}")

        def merge_waits_all(merge_node: NodeDefinition) -> bool:
            config = merge_node.config or {}
            strategy = str(config.get("strategy") or config.get("merge_strategy") or "wait_all").strip().lower()
            return strategy in {"", "wait_all", "wait-all", "all"}

        if debate_configs is None:
            debate_configs = self._identify_debate_configs(definition)

        if analyst_nodes_info is None:
            analyst_nodes_info = {}

        if risk_self_debate_nodes is None:
            risk_self_debate_nodes = set()

        if parallel_opening_nodes is None:
            parallel_opening_nodes = set()

        # Collect all debate participants
        all_participants: Set[str] = set()
        for config in debate_configs.values():
            all_participants.update(config["participants"])

        # Add START edge
        if start_node:
            for edge in definition.get_edges_from(start_node.id):
                graph.add_edge(START, edge.target)

        # 1. Deal with the side of the debate process first
        for debate_id, config in debate_configs.items():
            participants = config["participants"]

            # A9-P1: Risk Debate Entry Conditional Routing
            # state["_risk_self_debate"]=True → Single-node self-debate path (in-depth/comprehensive file)
            # Otherwise → Original risk triangle multi-agent debate path (default, unchanged behavior)
            self_debate_node_id = f"{debate_id}_self_debate"
            if self_debate_node_id in risk_self_debate_nodes:
                def debate_entry_router(
                    state,
                    _first_participant=participants[0],
                    _self_debate_node=self_debate_node_id,
                    _debate_id=debate_id,
                ):
                    if state.get("_risk_self_debate"):
                        logger.info(
                            f"[A9-P1] Risk self-debate is enabled: {_debate_id} -> {_self_debate_node}"
                        )
                        return _self_debate_node
                    return _first_participant

                graph.add_conditional_edges(
                    debate_id,
                    debate_entry_router,
                    [participants[0], self_debate_node_id],
                )
                added_edges.add((debate_id, participants[0]))
                added_edges.add((debate_id, self_debate_node_id))

                # self debate node → The next node after the debate (such as risk_manager)
                next_node = config["next_node"]
                if next_node:
                    next_node_def = definition.get_node(next_node)
                    if (
                        next_node_def
                        and next_node_def.type == NodeType.MERGE
                        and merge_waits_all(next_node_def)
                    ):
                        add_merge_predecessor(next_node, self_debate_node_id)
                    else:
                        graph.add_edge(self_debate_node_id, next_node)
                    added_edges.add((self_debate_node_id, next_node))
                else:
                    graph.add_edge(self_debate_node_id, END)
                logger.info(
                    f"[A9-P1] Risk Debate Entry Conditional Routing: {debate_id} -> "
                    f"[{participants[0]}(Original path), {self_debate_node_id}(self debate)]"
                )
            else:
                # A3: Investment Debate Entry Conditional Routing
                # state["_parallel_opening"]=True → Parallel launch node (first round of parallel launch briefing)
                # Otherwise → Original serial path (debate node → first participant)
                po_node_id = f"{debate_id}_parallel_opening"
                if po_node_id in parallel_opening_nodes:
                    def opening_entry_router(
                        state,
                        _first_participant=participants[0],
                        _po_node=po_node_id,
                        _debate_id=debate_id,
                    ):
                        if state.get("_parallel_opening"):
                            logger.info(
                                f"[A3] Investment Debate Parallel Start is enabled: {_debate_id} -> {_po_node}"
                            )
                            return _po_node
                        return _first_participant

                    graph.add_conditional_edges(
                        debate_id,
                        opening_entry_router,
                        [participants[0], po_node_id],
                    )
                    added_edges.add((debate_id, participants[0]))
                    added_edges.add((debate_id, po_node_id))

                    # Parallel start → Conditional routing (reusing round-robin semantics):
                    # count >= rounds × Number of participants → next_node (Such as research_manager)
                    # Otherwise → participants[count % N] Continue the confrontational debate (the original participant's conditional side takes over the follow-up)
                    _po_max_rounds = int(config["rounds"]) if config["rounds"] else 1
                    _po_debate_key = config["debate_key"]
                    _po_next_node = config["next_node"]
                    _po_num_participants = len(participants)
                    _po_participants = list(participants)

                    def opening_exit_router(
                        state,
                        _debate_key=_po_debate_key,
                        _max_rounds=_po_max_rounds,
                        _next_node=_po_next_node,
                        _num_participants=_po_num_participants,
                        _participants=_po_participants,
                    ):
                        count = state.get(_debate_key, 0)
                        dynamic_rounds = state.get("_max_debate_rounds", _max_rounds)
                        max_count = dynamic_rounds * _num_participants
                        if count >= max_count:
                            logger.info(
                                f"[A3] Parallel deployment routing: count={count} >= {max_count} "
                                f"-> {_next_node or 'END'} (Debate ended)"
                            )
                            return _next_node if _next_node else END
                        target = _participants[count % _num_participants]
                        logger.info(
                            f"[A3] Parallel deployment routing: count={count} -> {target} (continue the debate)"
                        )
                        return target

                    _po_exit_targets = list(participants)
                    if _po_next_node and _po_next_node not in _po_exit_targets:
                        _po_exit_targets.append(_po_next_node)
                    graph.add_conditional_edges(
                        po_node_id, opening_exit_router, _po_exit_targets
                    )
                    logger.info(
                        f"[A3] Investment Debate Entry Conditional Routing: {debate_id} -> "
                        f"[{participants[0]}(Original path), {po_node_id}(Parallel start)]"
                    )
                else:
                    # debate node → First participant (original path)
                    graph.add_edge(debate_id, participants[0])
                    added_edges.add((debate_id, participants[0]))

            # Add conditional edges for each participant (the original logic is retained, the self-debate path will not pass through)
            for i, participant in enumerate(participants):
                self._add_participant_conditional_edge(
                    graph, participant, config, i, debate_id
                )
                # Mark all edges originating from the actor as processed
                for edge in definition.get_edges_from(participant):
                    added_edges.add((participant, edge.target))

        # 2. Tools for handling analyst node edge loops
        for node_id, analyst_type in analyst_nodes_info.items():
            tools_node_id = f"tools_{node_id}"
            clear_node_id = f"msg_clear_{node_id}"

            # Analyst Node → conditional edge → Tool node/message cleaning node
            condition_func = self._create_analyst_condition_func(node_id, analyst_type)
            graph.add_conditional_edges(
                node_id,
                condition_func,
                [tools_node_id, clear_node_id]
            )
            logger.info(f"[tool cycle] Add conditional edge: {node_id} -> [{tools_node_id}, {clear_node_id}]")

            # tool node → Analyst node (loop)
            graph.add_edge(tools_node_id, node_id)
            logger.info(f"[tool cycle] Add edge loop: {tools_node_id} -> {node_id}")

            # Find the next target node of the analyst node
            for edge in definition.get_edges_from(node_id):
                target = edge.target
                target_node = definition.get_node(target)

                # Message cleaning node → original target node
                if target_node and target_node.type == NodeType.END:
                    graph.add_edge(clear_node_id, END)
                    logger.info(f"[tool cycle] Add out edge: {clear_node_id} -> END")
                elif target_node and target_node.type == NodeType.MERGE and merge_waits_all(target_node):
                    add_merge_predecessor(target, clear_node_id)
                    logger.info(f"[tool cycle] Delayed addition of merge barrier outgoing edges: {clear_node_id} -> {target}")
                else:
                    graph.add_edge(clear_node_id, target)
                    logger.info(f"[tool cycle] Add out edge: {clear_node_id} -> {target}")

                # Mark edge as processed
                added_edges.add((node_id, target))

        # 3. Handle common edges
        for edge in definition.edges:
            source_node = definition.get_node(edge.source)
            target_node = definition.get_node(edge.target)

            if source_node is None or target_node is None:
                continue
            if source_node.type == NodeType.START:
                continue

            edge_key = (edge.source, edge.target)
            if edge_key in added_edges:
                continue

            # Skip all outgoing edges of debate nodes (handled above)
            if source_node.type == NodeType.DEBATE:
                continue

            # Skipping participant edges (already handled above)
            if source_node.id in all_participants:
                continue

            # Skip edges of analyst nodes (already handled above)
            if source_node.id in analyst_nodes_info:
                continue

            # Normal side
            if target_node.type == NodeType.END:
                graph.add_edge(edge.source, END)
            elif edge.type == EdgeType.CONDITIONAL:
                self._add_conditional_edge(graph, edge, definition)
            elif target_node.type == NodeType.MERGE and merge_waits_all(target_node):
                add_merge_predecessor(edge.target, edge.source)
            else:
                graph.add_edge(edge.source, edge.target)
            added_edges.add(edge_key)

        # 4. Add real barrier edges for merged nodes
        # LangGraph support graph.add_edge([a, b, c], merge), The merge is only triggered after all upstreams have completed.
        # Otherwise, when multiple parallel branches arrive at merge one by one, merge and its downstream nodes will be triggered repeatedly.
        for merge_node_id, predecessors in merge_barriers.items():
            ordered_predecessors = sorted(predecessors)
            if len(ordered_predecessors) == 1:
                graph.add_edge(ordered_predecessors[0], merge_node_id)
                logger.info(
                    f"[merge barrier] Single upstream common edge: {ordered_predecessors[0]} -> {merge_node_id}"
                )
            else:
                graph.add_edge(ordered_predecessors, merge_node_id)
                logger.info(
                    f"[merge barrier] Add barrier edge: {ordered_predecessors} -> {merge_node_id}"
                )

    def _add_participant_conditional_edge(
        self,
        graph: StateGraph,
        participant: str,
        debate_config: Dict[str, Any],
        participant_index: int,
        debate_id: str
    ) -> None:
        """Add conditional edges for debate participants"""
        participants = debate_config["participants"]
        max_rounds = int(debate_config["rounds"]) if debate_config["rounds"] else 1
        next_node = debate_config["next_node"]
        debate_key = debate_config["debate_key"]
        num_participants = len(participants)

        # next participant
        next_idx = (participant_index + 1) % num_participants
        next_participant = participants[next_idx]

        # Dynamic number of rounds selected based on debate type state key
        # "risk" Related debates use _max_risk_rounds, others use _max_debate_rounds
        is_risk_debate = "risk" in debate_id.lower()
        dynamic_rounds_key = "_max_risk_rounds" if is_risk_debate else "_max_debate_rounds"

        # Create routing function
        def create_router(
            _debate_key: str,
            _max_rounds: int,
            _next_participant: str,
            _next_node: str,
            _num_participants: int,
            _dynamic_rounds_key: str,
            _participant: str
        ):
            def router(state):
                count = state.get(_debate_key, 0)
                dynamic_rounds = state.get(_dynamic_rounds_key, _max_rounds)
                max_count = dynamic_rounds * _num_participants
                logger.info(
                    f"[debate routing] {_participant}: count={count}, max={max_count} "
                    f"(rounds={dynamic_rounds}, participants={_num_participants})"
                )
                if count >= max_count:
                    logger.info(f"[debate routing] {_participant} -> {_next_node} (Debate ended)")
                    return _next_node if _next_node else END
                logger.info(f"[debate routing] {_participant} -> {_next_participant} (continue the debate)")
                return _next_participant
            return router

        router = create_router(
            debate_key, max_rounds, next_participant, next_node,
            num_participants, dynamic_rounds_key, participant
        )

        targets = [next_participant]
        if next_node and next_node != next_participant:
            targets.append(next_node)

        graph.add_conditional_edges(participant, router, targets)

    def _identify_debate_configs(
        self, definition: WorkflowDefinition
    ) -> Dict[str, Dict[str, Any]]:
        """Identify debate configurations in workflows"""
        debate_configs = {}

        for node in definition.nodes:
            if node.type == NodeType.DEBATE:
                participants = node.config.get("participants", [])
                rounds_raw = node.config.get("rounds", 1)

                # Handles cases where rounds may be a string (e.g. "auto", "1" etc.)
                if isinstance(rounds_raw, str):
                    if rounds_raw.lower() == "auto" or not rounds_raw.isdigit():
                        rounds = 1  # The default is 1 round, which will actually be read from state
                    else:
                        rounds = int(rounds_raw)
                else:
                    rounds = int(rounds_raw) if rounds_raw else 1

                # Find the next node after the debate
                next_node = None
                for edge in definition.get_edges_from(node.id):
                    target = definition.get_node(edge.target)
                    if target and target.id not in participants:
                        next_node = edge.target
                        break

                debate_configs[node.id] = {
                    "participants": participants,
                    "rounds": rounds,
                    "next_node": next_node,
                    "debate_key": f"_debate_{node.id}_count"
                }

        return debate_configs

    def _add_conditional_edge(
        self,
        graph: StateGraph,
        edge: EdgeDefinition,
        definition: WorkflowDefinition
    ) -> None:
        """Add normal conditional edges"""
        all_edges = definition.get_edges_from(edge.source)

        def route(state):
            result = state.get("_condition_result", True)
            for e in all_edges:
                if e.condition == "true" and result:
                    return e.target
                if e.condition == "false" and not result:
                    return e.target
            return all_edges[0].target if all_edges else END

        targets = {e.target for e in all_edges}
        graph.add_conditional_edges(edge.source, route, list(targets))
