# TradingAgents/graph/trading_graph.py

import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional
import time
import threading

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from tradingagents.llm_adapters import ChatDashScopeOpenAI, ChatGoogleOpenAI

from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.core.engine.memory_provider import MemoryProvider

# Import unified log system
from tradingagents.utils.logging_init import get_logger

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.interface import set_config

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor
from app.utils.api_key_utils import truncate_api_key
from app.core.jdyun import get_llm_max_retries, is_jdyun_mode

# ============================================================================
# JD Cloud LLM call serialization (to avoid concurrent Agent calls triggering 429 current limit)
# ============================================================================
_jdyun_llm_semaphore = threading.Semaphore(1)

# JDYun 429 Retry interval (seconds): gradually doubled, starting from 3s
_JYDUN_RETRY_DELAYS = [3, 6, 12]


def _is_rate_limit_error(exc: Exception) -> bool:
    """Determine whether it is a 429 current limiting error"""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


class _JDYunRateLimitedLLM:
    """JDYun LLM agent in mode:
    1. The semaphore ensures that only one LLM call is in flight at a time
    2. 429 Retry with a longer interval when limiting current (3s/6s/12s)
    """

    def __init__(self, _llm):
        self.__llm = _llm

    def invoke(self, messages, *args, **kwargs):
        last_error = None
        for attempt in range(1 + len(_JYDUN_RETRY_DELAYS)):
            logger.debug(f"⏳ [JDYun Current limiting] Waiting for LLM call permission...")
            acquired = _jdyun_llm_semaphore.acquire(timeout=300)
            if not acquired:
                raise RuntimeError("[JDYun Current limiting] Timeout for obtaining LLM call permission (300s), there may be a deadlock")
            try:
                logger.debug(f"✅ [JDYun Current limiting] Obtain LLM calling permission and start calling (attempt {attempt+1})")
                return self.__llm.invoke(messages, *args, **kwargs)
            except Exception as exc:
                last_error = exc
                if _is_rate_limit_error(exc) and attempt < len(_JYDUN_RETRY_DELAYS):
                    delay = _JYDUN_RETRY_DELAYS[attempt]
                    logger.warning(
                        f"⚠️ [JDYun Current limiting] Encountered 429 current limit,{delay}s Try again later "
                        f"(No. {attempt+1}/{len(_JYDUN_RETRY_DELAYS)} times)"
                    )
                    time.sleep(delay)
                else:
                    raise
            finally:
                _jdyun_llm_semaphore.release()
                logger.debug(f"🔓 [JDYun Current limiting] Release LLM calling permission")

        raise last_error

    def __getattr__(self, name):
        return getattr(self.__llm, name)


def _normalize_provider_qualified_model(provider: str, model: str) -> tuple[str, str]:
    """Normalize provider-qualified model selections like provider::model."""
    raw_model = str(model or "").strip()
    normalized_provider = str(provider or "").strip()

    if "::" not in raw_model:
        return normalized_provider, raw_model

    provider_hint, model_name = raw_model.split("::", 1)
    provider_hint = provider_hint.strip()
    model_name = model_name.strip()

    if provider_hint and model_name:
        return provider_hint, model_name

    return normalized_provider, raw_model


# Volcano Ark reasoning_effort gear order (low→high)
_REASONING_EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


def _lower_reasoning_effort(effort: Optional[str], steps: int = 2) -> Optional[str]:
    """The fast model thinking budget is downgraded based on the depth level (minimum to minimal, not to none to avoid shutting down thinking)"""
    if not effort:
        return None
    try:
        idx = _REASONING_EFFORT_ORDER.index(effort)
    except ValueError:
        return effort
    return _REASONING_EFFORT_ORDER[max(1, idx - steps)]


def resolve_reasoning_efforts(
    config: dict, quick_model_config: dict, deep_model_config: dict
) -> tuple:
    """Incorporate reasoning_effort for fast/deep models.

    Priority: DB model configuration explicit value > The default gear mapping for this analysis is (config["depth_reasoning_effort"]) . 
    By default, the gear is only injected into Volcano Ark Agent Plan (provider=volcengine) inference model;
    Coding Plan (volcengine_coding) Unlike other manufacturers there is no injection; the fast model is two gears down from the depth gear.
    """
    quick_effort = quick_model_config.get("reasoning_effort")
    deep_effort = deep_model_config.get("reasoning_effort")
    depth_effort = config.get("depth_reasoning_effort")
    if not depth_effort:
        return quick_effort, deep_effort

    quick_provider = (config.get("quick_provider") or config.get("llm_provider") or "").lower()
    deep_provider = (config.get("deep_provider") or config.get("llm_provider") or "").lower()
    if not quick_effort and quick_provider == "volcengine":
        quick_effort = _lower_reasoning_effort(depth_effort)
    if not deep_effort and deep_provider == "volcengine":
        deep_effort = depth_effort
    return quick_effort, deep_effort


def create_llm_by_provider(provider: str, model: str, backend_url: str, temperature: float, max_tokens: int, timeout: int, api_key: str = None, reasoning_effort: Optional[str] = None):
    """
    Create corresponding LLM instance based on provider

    Args:
        provider: Supplier name (google, dashscope, deepseek, openai, etc.)
        model: Model name
        backend_url: API address
        temperature: Temperature parameter
        max_tokens: Maximum number of tokens
        timeout: timeout
        api_key: API Key (Optional, read from environment variables if not provided)
        reasoning_effort: Inference model thinking depth (none/minimal/low/medium/high/xhigh/max), Only the Volcano Ark inference model supports

    Returns:
        LLM Example
    """
    from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
    from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm, normalize_openai_temperature

    # 🔧 reasoning_effort: Volcano Ark inference model thinking depth control, passed through model_kwargs
    # 🛡️ Q1: The reasoning model (reasoning_effort has been set) takes a long time to think deeply (single measured 300s+) , 
    # SDK Retries reduced from global default to 1 (total 2 attempts) to avoid worst-case scenarios 3×timeout Waiting in vain
    _extra = {}
    _base_max_retries = get_llm_max_retries()
    if reasoning_effort:
        _extra["model_kwargs"] = {"reasoning_effort": reasoning_effort}
        if _base_max_retries > 1:
            _base_max_retries = 1
        logger.info(f"🔧 [reasoning_effort] set to {reasoning_effort} (max_retries=1) ")

    normalized_provider, normalized_model = _normalize_provider_qualified_model(provider, model)
    if normalized_provider != provider or normalized_model != model:
        logger.info(
            f"🔧 [Create LLM] normalization provider/model: provider={provider}, model={model} -> "
            f"provider={normalized_provider}, model={normalized_model}"
        )
        provider = normalized_provider
        model = normalized_model

    temperature = normalize_openai_temperature(
        provider=provider,
        model=model,
        temperature=temperature,
        base_url=backend_url,
    )

    logger.info(f"🔧 [Create LLM] provider={provider}, model={model}, url={backend_url}")
    logger.info(f"🔑 [API Key] Pass in value: {'valuable' if api_key else 'None (environment variables will be used)'}")
    if api_key:
        logger.info(f"🔑 [API Key] Incoming desensitization value: {truncate_api_key(api_key)}")
    logger.info(f"🌡️ [parameters] temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")

    if provider.lower() == "google":
        # Prioritize using the passed API Key, otherwise read from environment variables
        google_api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if not google_api_key:
            raise ValueError("To use Google, you need to set the GOOGLE_API_KEY environment variable or configure it in the database API Key")
        
        logger.info(f"✅ [Google] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        logger.info(f"🔑 [Google] final use API Key: {truncate_api_key(google_api_key)}")

        # Pass the base_url parameter to make the default_base_url configured by the manufacturer take effect.
        return ChatGoogleOpenAI(
            model=model,
            google_api_key=google_api_key,
            base_url=backend_url if backend_url else None,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

    elif provider.lower() == "dashscope":
        # Prioritize using the passed API Key, otherwise read from environment variables
        dashscope_api_key = api_key or os.getenv('DASHSCOPE_API_KEY')
        
        logger.info(f"✅ [DashScope] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        #logger.info(f"🔑 [DashScope] final use API Key: {truncate_api_key(dashscope_api_key)}")

        # Pass the base_url parameter to make the default_base_url configured by the manufacturer take effect.
        return ChatDashScopeOpenAI(
            model=model,
            api_key=dashscope_api_key,  # 🔥 pass on API Key
            base_url=backend_url if backend_url else None,  # If there is a custom URL then use
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout=timeout
        )

    elif provider.lower() == "deepseek":
        # Prioritize using the passed API Key, otherwise read from environment variables
        deepseek_api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
        if not deepseek_api_key:
            raise ValueError("Using DeepSeek requires setting the DEEPSEEK_API_KEY environment variable or configuring it in the database API Key")
        
        logger.info(f"✅ [DeepSeek] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        logger.info(f"🔑 [DeepSeek] final use API Key: {truncate_api_key(deepseek_api_key)}")

        return ChatDeepSeek(
            model=model,
            api_key=deepseek_api_key,
            base_url=backend_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

    elif provider.lower() == "zhipu":
        # Wisdom spectrum AI processing
        zhipu_api_key = api_key or os.getenv('ZHIPU_API_KEY')
        if not zhipu_api_key:
            raise ValueError("To use ZHIPU AI, you need to set the ZHIPU_API_KEY environment variable or configure it in the database API Key")
        
        logger.info(f"✅ [Zhipu] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        logger.info(f"🔑 [Zhipu] final use API Key: {truncate_api_key(zhipu_api_key)}")
        
        return create_openai_compatible_llm(
            provider="zhipu",
            model=model,
            api_key=zhipu_api_key,
            base_url=backend_url,  # Use user-provided backend_url
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=_base_max_retries,
            **_extra
        )

    elif provider.lower() in ["openai", "siliconflow", "openrouter", "aihubmix", "ollama", "jdyun"]:
        # Prioritize using the passed API Key, otherwise read from environment variables
        if not api_key:
            if provider.lower() == "siliconflow":
                api_key = os.getenv('SILICONFLOW_API_KEY')
            elif provider.lower() == "openrouter":
                api_key = os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')
            elif provider.lower() == "aihubmix":
                api_key = os.getenv('AIHUBMIX_API_KEY')
            elif provider.lower() == "openai":
                api_key = os.getenv('OPENAI_API_KEY')
            elif provider.lower() == "jdyun":
                # 🔧 JD Cloud: Use OPENAI_API_KEY environment variable
                api_key = os.getenv('OPENAI_API_KEY')
            elif provider.lower() == "ollama":
                # 🔥 Ollama It is a local model, does not require API Key, uses placeholders
                api_key = "ollama"
                logger.info(f"ℹ️  [Ollama] Local model, no API Key required, use placeholders")
        
        final_api_key = api_key  # Save for final use API Key
        logger.info(f"✅ [{provider.capitalize()}] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        if final_api_key:
            logger.info(f"🔑 [{provider.capitalize()}] final use API Key: {truncate_api_key(final_api_key)}")
        else:
            logger.info(f"🔑 [{provider.capitalize()}] final use API Key: None (environment variables will be used)")

        # JDYun Mode: The bottom layer only retains 1 fast retry (to deal with instantaneous network jitter),
        # 429 Rate limiting is handled by _JDYunRateLimitedLLM with long intervals
        _max_retries = 1 if provider.lower() == "jdyun" else _base_max_retries
        llm = ChatOpenAI(
            model=model,
            base_url=backend_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=_max_retries,
            **_extra
        )
        if provider.lower() == "jdyun":
            logger.info(f"🔒 [JDYun Current limiting] Enable serialization of LLM calls (avoids parallel Agent triggering 429)")
            return _JDYunRateLimitedLLM(llm)
        return llm

    elif provider.lower() in ["volcengine", "volcengine_coding"]:
        # 🔧 Volcano Ark: Using a dedicated adapter, support reasoning_effort
        if not api_key:
            env_key = "VOLCENGINE_CODING_API_KEY" if provider.lower() == "volcengine_coding" else "VOLCENGINE_API_KEY"
            api_key = os.getenv(env_key)
        logger.info(f"✅ [Volcano Ark] provider={provider}, model={model}, reasoning_effort={reasoning_effort or 'not set'}")
        if api_key:
            logger.info(f"🔑 [Volcano Ark] API Key: {truncate_api_key(api_key)}")

        return create_openai_compatible_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=backend_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=_base_max_retries,
            **_extra
        )

    elif provider.lower() == "anthropic":
        return ChatAnthropic(
            model=model,
            base_url=backend_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

    elif provider.lower() in ["qianfan", "custom_openai"]:
        logger.info(f"✅ [{provider.capitalize()}] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        if api_key:
            logger.info(f"🔑 [{provider.capitalize()}] final use API Key: {truncate_api_key(api_key)}")
        else:
            logger.info(f"🔑 [{provider.capitalize()}] final use API Key: None (environment variables will be used)")
        
        return create_openai_compatible_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=backend_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=_base_max_retries,
            **_extra
        )

    else:
        # 🔧 Custom manufacturer: use OpenAI compatibility mode
        logger.info(f"🔧 Use OpenAI compatibility mode to handle custom manufacturers: {provider}")

        # 🔥 Prioritize using the incoming api_key parameter
        custom_api_key = api_key
        
        # If the incoming api_key is empty, try to obtain the API Key from the environment variable (supports multiple naming formats)
        if not custom_api_key:
            api_key_candidates = [
                f"{provider.upper()}_API_KEY",  # For example: KYX_API_KEY
                f"{provider}_API_KEY",          # For example: kyx_API_KEY
                "CUSTOM_OPENAI_API_KEY"         # Common environment variables
            ]

            for env_var in api_key_candidates:
                custom_api_key = os.getenv(env_var)
                if custom_api_key:
                    logger.info(f"✅ from environment variables {env_var} Get API Key")
                    break

        if not custom_api_key:
            logger.error(f"❌ Custom manufacturer not found {provider} API Key (neither passed in parameters nor environment variables)")
            raise ValueError(f"Use custom manufacturers {provider} API Key needs to be set, please configure or set environment variables in the database")
        
        logger.info(f"✅ [{provider.capitalize()}] final parameters: model={model}, temperature={temperature}, max_tokens={max_tokens}, timeout={timeout}s")
        logger.info(f"🔑 [{provider.capitalize()}] final use API Key: {truncate_api_key(custom_api_key)}")

        return ChatOpenAI(
            model=model,
            base_url=backend_url,
            api_key=custom_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=_base_max_retries,
            **_extra
        )


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs
        # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
        quick_config = self.config.get("quick_model_config", {})
        deep_config = self.config.get("deep_model_config", {})

        # Read fast model parameters
        quick_max_tokens = quick_config.get("max_tokens", 4000)
        quick_temperature = quick_config.get("temperature", 0.7)
        quick_timeout = quick_config.get("timeout", 180)

        # Read depth model parameters
        deep_max_tokens = deep_config.get("max_tokens", 4000)
        deep_temperature = deep_config.get("temperature", 0.7)
        deep_timeout = deep_config.get("timeout", 180)

        # 🔧 reasoning_effort Merge: DB model configuration explicit value > The default gear mapping for this analysis (depth_reasoning_effort)
        # By default, the gear is only injected into the Volcano Ark Agent Plan (volcengine) inference model; Coding Plan and other manufacturers are not injected;
        # The fast model is downgraded by two levels based on the depth level (use low level for light queries to improve efficiency)
        quick_reasoning_effort, deep_reasoning_effort = resolve_reasoning_efforts(
            self.config, quick_config, deep_config
        )
        depth_reasoning_effort = self.config.get("depth_reasoning_effort")
        if depth_reasoning_effort:
            logger.info(
                f"🧠 [reasoning_effort] Gear default={depth_reasoning_effort}, "
                f"quick={quick_reasoning_effort or 'not set'}, deep={deep_reasoning_effort or 'not set'}"
            )

        # 🔧 Check whether it is a mixed mode (fast model and deep model are from different manufacturers)
        quick_provider = self.config.get("quick_provider")
        deep_provider = self.config.get("deep_provider")
        quick_backend_url = self.config.get("quick_backend_url")
        deep_backend_url = self.config.get("deep_backend_url")

        if quick_provider and deep_provider:
            if quick_provider != deep_provider:
                logger.info(f"🔀 [blend mode] Model combinations from different manufacturers detected")
            else:
                logger.info(f"🧩 [Explicit model configuration] If a combination of models from the same manufacturer is detected, the one carried in the request will be used first. provider/api_key/backend_url")

            logger.info(f"   quick model: {self.config['quick_think_llm']} ({quick_provider})")
            logger.info(f"   deep model: {self.config['deep_think_llm']} ({deep_provider})")

            # Create LLM instances using unified functions
            self.quick_thinking_llm = create_llm_by_provider(
                provider=quick_provider,
                model=self.config["quick_think_llm"],
                backend_url=quick_backend_url or self.config.get("backend_url", ""),
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                api_key=self.config.get("quick_api_key"),  # 🔥 pass on API Key
                reasoning_effort=quick_reasoning_effort  # 🔧 Inference model thinking depth
            )

            self.deep_thinking_llm = create_llm_by_provider(
                provider=deep_provider,
                model=self.config["deep_think_llm"],
                backend_url=deep_backend_url or self.config.get("backend_url", ""),
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                api_key=self.config.get("deep_api_key"),  # 🔥 pass on API Key
                reasoning_effort=deep_reasoning_effort  # 🔧 Inference model thinking depth
            )

            logger.info(f"✅ [Explicit model configuration] LLM Instance created successfully")

        elif self.config["llm_provider"].lower() in ["volcengine", "volcengine_coding"]:
            # 🔧 Volcano Ark: Support using create_llm_by_provider reasoning_effort
            logger.info(f"🔧 [Volcano Ark] llm_provider={self.config['llm_provider']}")
            volc_api_key = self.config.get("quick_api_key") or self.config.get("deep_api_key")

            self.deep_thinking_llm = create_llm_by_provider(
                provider=self.config["llm_provider"],
                model=self.config["deep_think_llm"],
                backend_url=self.config.get("backend_url", ""),
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                api_key=volc_api_key,
                reasoning_effort=deep_reasoning_effort
            )
            self.quick_thinking_llm = create_llm_by_provider(
                provider=self.config["llm_provider"],
                model=self.config["quick_think_llm"],
                backend_url=self.config.get("backend_url", ""),
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                api_key=volc_api_key,
                reasoning_effort=quick_reasoning_effort
            )

        elif self.config["llm_provider"].lower() == "openai":
            logger.info(f"🔧 [OpenAI-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [OpenAI-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            self.deep_thinking_llm = ChatOpenAI(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"],
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                max_retries=get_llm_max_retries()
            )
            self.quick_thinking_llm = ChatOpenAI(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                max_retries=get_llm_max_retries()
            )
        elif self.config["llm_provider"] == "siliconflow":
            # SiliconFlow Support: compatible with OpenAI API
            siliconflow_api_key = os.getenv('SILICONFLOW_API_KEY')
            if not siliconflow_api_key:
                raise ValueError("To use SiliconFlow, you need to set the SILICONFLOW_API_KEY environment variable")

            logger.info(f"🌐 [SiliconFlow] Use API key: {siliconflow_api_key[:20]}...")
            logger.info(f"🔧 [SiliconFlow-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [SiliconFlow-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            self.deep_thinking_llm = ChatOpenAI(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"],
                api_key=siliconflow_api_key,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                max_retries=get_llm_max_retries()
            )
            self.quick_thinking_llm = ChatOpenAI(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
                api_key=siliconflow_api_key,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                max_retries=get_llm_max_retries()
            )
        elif self.config["llm_provider"] == "openrouter":
            # OpenRouter Support: Use OPENROUTER_API_KEY first, otherwise use OPENAI_API_KEY
            openrouter_api_key = os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENAI_API_KEY')
            if not openrouter_api_key:
                raise ValueError("Using OpenRouter requires setting the OPENROUTER_API_KEY or OPENAI_API_KEY environment variable")

            logger.info(f"🌐 [OpenRouter] Use API key: {openrouter_api_key[:20]}...")
            logger.info(f"🔧 [OpenRouter-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [OpenRouter-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            self.deep_thinking_llm = ChatOpenAI(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"],
                api_key=openrouter_api_key,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                max_retries=get_llm_max_retries()
            )
            self.quick_thinking_llm = ChatOpenAI(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
                api_key=openrouter_api_key,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                max_retries=get_llm_max_retries()
            )
        elif self.config["llm_provider"] == "aihubmix":
            aihubmix_api_key = os.getenv('AIHUBMIX_API_KEY')
            if not aihubmix_api_key:
                raise ValueError("To use AIHubMix, you need to set the AIHUBMIX_API_KEY environment variable")

            logger.info(f"🌐 [AIHubMix] Use API key: {aihubmix_api_key[:20]}...")
            logger.info(f"🔧 [AIHubMix-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [AIHubMix-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            self.deep_thinking_llm = ChatOpenAI(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"],
                api_key=aihubmix_api_key,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                max_retries=get_llm_max_retries()
            )
            self.quick_thinking_llm = ChatOpenAI(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
                api_key=aihubmix_api_key,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                max_retries=get_llm_max_retries()
            )
        elif self.config["llm_provider"] == "ollama":
            logger.info(f"🔧 [Ollama-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Ollama-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            self.deep_thinking_llm = ChatOpenAI(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"],
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout,
                max_retries=get_llm_max_retries()
            )
            self.quick_thinking_llm = ChatOpenAI(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                max_retries=get_llm_max_retries()
            )
        elif self.config["llm_provider"].lower() == "anthropic":
            logger.info(f"🔧 [Anthropic-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Anthropic-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            self.deep_thinking_llm = ChatAnthropic(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"],
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = ChatAnthropic(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout
            )
        elif self.config["llm_provider"].lower() == "google":
            # Use Google OpenAI compatible adapter to solve tool call format mismatch problem
            logger.info(f"🔧 Using the Google AI OpenAI Compatible Adapter (Solve tool calling issues)")

            # 🔥 Priority is given to using the API Key configured in the database, otherwise reading from environment variables
            google_api_key = self.config.get("quick_api_key") or self.config.get("deep_api_key") or os.getenv('GOOGLE_API_KEY')
            if not google_api_key:
                raise ValueError("Using Google AI requires configuring the API Key in the database or setting the GOOGLE_API_KEY environment variable")

            logger.info(f"🔑 [Google AI] API Key Source: {'Database configuration' if self.config.get('quick_api_key') or self.config.get('deep_api_key') else 'environment variables'}")

            # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)

            logger.info(f"🔧 [Google-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Google-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            # Get backend_url (if there is one in the configuration)
            backend_url = self.config.get("backend_url")
            if backend_url:
                logger.info(f"🔧 [Google AI] Use configured backend_url: {backend_url}")
            else:
                logger.info(f"🔧 [Google AI] backend_url is not configured, default endpoint is used")

            self.deep_thinking_llm = ChatGoogleOpenAI(
                model=self.config["deep_think_llm"],
                google_api_key=google_api_key,
                base_url=backend_url if backend_url else None,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = ChatGoogleOpenAI(
                model=self.config["quick_think_llm"],
                google_api_key=google_api_key,
                base_url=backend_url if backend_url else None,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout,
                transport="rest"
            )

            logger.info(f"✅ [Google AI] Optimized tool invocation and content format processing enabled and application of user-configured model parameters")
        elif (self.config["llm_provider"].lower() == "dashscope" or
              self.config["llm_provider"].lower() == "alibaba" or
              "dashscope" in self.config["llm_provider"].lower() or
              "Ali Bailian" in self.config["llm_provider"]):
            # Use OpenAI compatible adapter to support native Function Calling
            logger.info(f"🔧 Using Alibaba Bailian OpenAI compatible adapter (Support native tool calls)")

            # 🔥 Priority is given to using the API Key configured in the database, otherwise reading from environment variables
            dashscope_api_key = self.config.get("quick_api_key") or self.config.get("deep_api_key") or os.getenv('DASHSCOPE_API_KEY')
            logger.info(f"🔑 [Ali Bailian] API Key Source: {'Database configuration' if self.config.get('quick_api_key') or self.config.get('deep_api_key') else 'environment variables'}")

            # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            # Read fast model parameters
            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            # Read depth model parameters
            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)

            logger.info(f"🔧 [Ali Bailian-Quick Model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Alibaba Bailian-Deep Model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            # Get backend_url (if there is one in the configuration)
            backend_url = self.config.get("backend_url")
            if backend_url:
                logger.info(f"🔧 [Ali Bailian] Use a custom API address: {backend_url}")

            # 🔥 Detailed log: print all LLM initialization parameters
            logger.info("=" * 80)
            logger.info("🤖 [LLM initialization] Alibaba Bailian depth model parameters:")
            logger.info(f"   model: {self.config['deep_think_llm']}")
            logger.info(f"   api_key: {'valuable' if dashscope_api_key else 'empty'} (length: {len(dashscope_api_key) if dashscope_api_key else 0})")
            logger.info(f"   base_url: {backend_url if backend_url else 'Default'}")
            logger.info(f"   temperature: {deep_temperature}")
            logger.info(f"   max_tokens: {deep_max_tokens}")
            logger.info(f"   request_timeout: {deep_timeout}")
            logger.info("=" * 80)

            self.deep_thinking_llm = ChatDashScopeOpenAI(
                model=self.config["deep_think_llm"],
                api_key=dashscope_api_key,  # 🔥 pass on API Key
                base_url=backend_url if backend_url else None,  # pass on base_url
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                request_timeout=deep_timeout
            )

            logger.info("=" * 80)
            logger.info("🤖 [LLM initialization] Alibaba Bailian rapid model parameters:")
            logger.info(f"   model: {self.config['quick_think_llm']}")
            logger.info(f"   api_key: {'valuable' if dashscope_api_key else 'empty'} (length: {len(dashscope_api_key) if dashscope_api_key else 0})")
            logger.info(f"   base_url: {backend_url if backend_url else 'Default'}")
            logger.info(f"   temperature: {quick_temperature}")
            logger.info(f"   max_tokens: {quick_max_tokens}")
            logger.info(f"   request_timeout: {quick_timeout}")
            logger.info("=" * 80)

            self.quick_thinking_llm = ChatDashScopeOpenAI(
                model=self.config["quick_think_llm"],
                api_key=dashscope_api_key,  # 🔥 pass on API Key
                base_url=backend_url if backend_url else None,  # pass on base_url
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                request_timeout=quick_timeout
            )
            logger.info(f"✅ [Ali Bailian] User-configured model parameters applied")
        elif (self.config["llm_provider"].lower() == "deepseek" or
              "deepseek" in self.config["llm_provider"].lower()):
            # DeepSeek V3 Configuration - Use an adapter that supports token statistics
            from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

            deepseek_api_key = os.getenv('DEEPSEEK_API_KEY')
            if not deepseek_api_key:
                raise ValueError("To use DeepSeek, you need to set the DEEPSEEK_API_KEY environment variable")

            deepseek_base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')

            # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            # Read fast model parameters
            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            # Read depth model parameters
            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)

            logger.info(f"🔧 [DeepSeek-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [DeepSeek-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            # Use the DeepSeek adapter that supports token statistics
            self.deep_thinking_llm = ChatDeepSeek(
                model=self.config["deep_think_llm"],
                api_key=deepseek_api_key,
                base_url=deepseek_base_url,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = ChatDeepSeek(
                model=self.config["quick_think_llm"],
                api_key=deepseek_api_key,
                base_url=deepseek_base_url,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout
            )

            logger.info(f"✅ [DeepSeek] The token statistics function has been enabled and user-configured model parameters have been applied.")
        elif self.config["llm_provider"].lower() == "custom_openai":
            # Custom OpenAI endpoint configuration
            from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm

            custom_api_key = os.getenv('CUSTOM_OPENAI_API_KEY')
            if not custom_api_key:
                raise ValueError("Using a custom OpenAI endpoint requires setting the CUSTOM_OPENAI_API_KEY environment variable")

            custom_base_url = self.config.get("custom_openai_base_url", "https://api.openai.com/v1")

            # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)

            logger.info(f"🔧 [Customize OpenAI] Use endpoints: {custom_base_url}")
            logger.info(f"🔧 [Custom OpenAI-Quick Model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Custom OpenAI-Deep Model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            # Create an LLM instance using an OpenAI compatible adapter
            self.deep_thinking_llm = create_openai_compatible_llm(
                provider="custom_openai",
                model=self.config["deep_think_llm"],
                base_url=custom_base_url,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = create_openai_compatible_llm(
                provider="custom_openai",
                model=self.config["quick_think_llm"],
                base_url=custom_base_url,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout
            )

            logger.info(f"✅ [Customize OpenAI] Custom endpoint configured and user-configured model parameters applied")
        elif self.config["llm_provider"].lower() == "qianfan":
            # Baidu Qianfan (Wen Xin Yiyan) configuration - uniformly read and verified internally by the adapter QIANFAN_API_KEY
            from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm

            # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)

            logger.info(f"🔧 [Qianfan-Quick Model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Qianfan-Depth Model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            # Create an LLM instance using an OpenAI compatible adapter (the base class will use Qianfan's default base_url and be responsible for key verification)
            self.deep_thinking_llm = create_openai_compatible_llm(
                provider="qianfan",
                model=self.config["deep_think_llm"],
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = create_openai_compatible_llm(
                provider="qianfan",
                model=self.config["quick_think_llm"],
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout
            )
            logger.info("✅ [Qianfan] Wenxinyiyan adapter has been successfully configured and the user-configured model parameters are applied")
        elif self.config["llm_provider"].lower() == "zhipu":
            # Zhipu AI GLM configuration - using the dedicated ChatZhipuOpenAI adapter
            from tradingagents.llm_adapters.openai_compatible_base import ChatZhipuOpenAI
            
            # 🔥 Priority is given to using the API Key configured in the database, otherwise reading from environment variables
            zhipu_api_key = self.config.get("quick_api_key") or self.config.get("deep_api_key") or os.getenv('ZHIPU_API_KEY')
            logger.info(f"🔑 [Wisdom spectrum AI] API Key Source: {'Database configuration' if self.config.get('quick_api_key') or self.config.get('deep_api_key') else 'environment variables'}")
            
            if not zhipu_api_key:
                raise ValueError("To use ZHIPU AI, you need to configure the API Key in the database or set the ZHIPU_API_KEY environment variable")
            
            # 🔧 Read model parameters from configuration (user configuration is used first, otherwise default values are used)
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})
            
            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)
            
            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)
            
            logger.info(f"🔧 [Zhipu AI-Quick Model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [Intelligent Spectrum AI-Deep Model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")
            
            # Get backend_url (if there is one in the configuration)
            backend_url = self.config.get("backend_url")
            if backend_url:
                logger.info(f"🔧 [Wisdom spectrum AI] Use configured backend_url: {backend_url}")
            else:
                logger.info(f"🔧 [Wisdom spectrum AI] backend_url is not configured, default endpoint is used")
            
            # Create LLM instance using specialized ChatZhipuOpenAI adapter
            self.deep_thinking_llm = ChatZhipuOpenAI(
                model=self.config["deep_think_llm"],
                api_key=zhipu_api_key,
                base_url=backend_url,  # Use user configured backend_url
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = ChatZhipuOpenAI(
                model=self.config["quick_think_llm"],
                api_key=zhipu_api_key,
                base_url=backend_url,  # Use user configured backend_url
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout
            )
            
            logger.info("✅ [Wisdom spectrum AI] Successfully configured using a dedicated adapter and applying user-configured model parameters")
        else:
            # 🔧 Universal OpenAI compatible vendor support (for custom vendors)
            logger.info(f"🔧 Handle custom vendors using a generic OpenAI compatible adapter: {self.config['llm_provider']}")
            from tradingagents.llm_adapters.openai_compatible_base import create_openai_compatible_llm

            # Get the API Key and base_url
            provider_name = self.config['llm_provider']

            # Try to get API Key from environment variable (supports multiple naming formats)
            api_key_candidates = [
                f"{provider_name.upper()}_API_KEY",  # For example: KYX_API_KEY
                f"{provider_name}_API_KEY",          # For example: kyx_API_KEY
                "CUSTOM_OPENAI_API_KEY"              # Common environment variables
            ]

            custom_api_key = None
            for env_var in api_key_candidates:
                custom_api_key = os.getenv(env_var)
                if custom_api_key:
                    logger.info(f"✅ from environment variables {env_var} Get API Key")
                    break

            if not custom_api_key:
                raise ValueError(
                    f"Use custom manufacturers {provider_name} One of the following environment variables needs to be set:\n"
                    f"  - {provider_name.upper()}_API_KEY\n"
                    f"  - CUSTOM_OPENAI_API_KEY"
                )

            # Get backend_url (obtained from configuration)
            backend_url = self.config.get("backend_url")
            if not backend_url:
                raise ValueError(
                    f"Use custom manufacturers {provider_name} Need to be set in database configuration default_base_url"
                )

            logger.info(f"🔧 [Custom manufacturer {provider_name}] Use endpoints: {backend_url}")

            # 🔧 Read model parameters from configuration
            quick_config = self.config.get("quick_model_config", {})
            deep_config = self.config.get("deep_model_config", {})

            quick_max_tokens = quick_config.get("max_tokens", 4000)
            quick_temperature = quick_config.get("temperature", 0.7)
            quick_timeout = quick_config.get("timeout", 180)

            deep_max_tokens = deep_config.get("max_tokens", 4000)
            deep_temperature = deep_config.get("temperature", 0.7)
            deep_timeout = deep_config.get("timeout", 180)

            logger.info(f"🔧 [{provider_name}-quick model] max_tokens={quick_max_tokens}, temperature={quick_temperature}, timeout={quick_timeout}s")
            logger.info(f"🔧 [{provider_name}-deep model] max_tokens={deep_max_tokens}, temperature={deep_temperature}, timeout={deep_timeout}s")

            # Create an LLM instance using the custom_openai adapter
            self.deep_thinking_llm = create_openai_compatible_llm(
                provider="custom_openai",
                model=self.config["deep_think_llm"],
                api_key=custom_api_key,
                base_url=backend_url,
                temperature=deep_temperature,
                max_tokens=deep_max_tokens,
                timeout=deep_timeout
            )
            self.quick_thinking_llm = create_openai_compatible_llm(
                provider="custom_openai",
                model=self.config["quick_think_llm"],
                api_key=custom_api_key,
                base_url=backend_url,
                temperature=quick_temperature,
                max_tokens=quick_max_tokens,
                timeout=quick_timeout
            )

            logger.info(f"✅ [Custom manufacturer {provider_name}] Custom endpoint configured and user-configured model parameters applied")
        
        self.toolkit = Toolkit(config=self.config)

        # Initialize memories (If enabled)
        memory_enabled = self.config.get("memory_enabled", True)
        if memory_enabled:
            memory_provider = MemoryProvider(config=self.config, memory_enabled=True)
            self.bull_memory = memory_provider.get_memory("bull_memory")
            self.bear_memory = memory_provider.get_memory("bear_memory")
            self.trader_memory = memory_provider.get_memory("trader_memory")
            self.invest_judge_memory = memory_provider.get_memory("invest_judge_memory")
            self.risk_manager_memory = memory_provider.get_memory("risk_manager_memory")
        else:
            # Create an empty memory object
            self.bull_memory = None
            self.bear_memory = None
            self.trader_memory = None
            self.invest_judge_memory = None
            self.risk_manager_memory = None

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        # 🔥 [Repair] Read debate round parameters from configuration
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 1)
        )
        logger.info(f"🔧 [ConditionalLogic] Initialization completed:")
        logger.info(f"   - max_debate_rounds: {self.conditional_logic.max_debate_rounds}")
        logger.info(f"   - max_risk_discuss_rounds: {self.conditional_logic.max_risk_discuss_rounds}")

        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.toolkit,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
            self.config,
            getattr(self, 'react_llm', None),
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources.

        Note: ToolNode contains all possible tools, but LLM will only call the tools it is bound to.
        ToolNode The purpose of is to execute tool_calls generated by LLM, rather than restricting which tools LLM can call.
        """
        return {
            "market": ToolNode(
                [
                    # Unified tools (recommended)
                    self.toolkit.get_stock_market_data_unified,
                    # Online tools (backup)
                    self.toolkit.get_YFin_data_online,
                    self.toolkit.get_stockstats_indicators_report_online,
                    # Offline tools (backup)
                    self.toolkit.get_YFin_data,
                    self.toolkit.get_stockstats_indicators_report,
                ]
            ),
            "social": ToolNode(
                [
                    # Unified tools (recommended)
                    self.toolkit.get_stock_sentiment_unified,
                    # Online tools (backup)
                    self.toolkit.get_stock_news_openai,
                    # Offline tools (backup)
                    self.toolkit.get_reddit_stock_info,
                ]
            ),
            "news": ToolNode(
                [
                    # Unified tools (recommended)
                    self.toolkit.get_stock_news_unified,
                    # Online tools (backup)
                    self.toolkit.get_global_news_openai,
                    self.toolkit.get_google_news,
                    # Offline tools (backup)
                    self.toolkit.get_finnhub_news,
                    self.toolkit.get_reddit_news,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Unified tools (recommended)
                    self.toolkit.get_stock_fundamentals_unified,
                    # Offline tools (backup)
                    self.toolkit.get_finnhub_company_insider_sentiment,
                    self.toolkit.get_finnhub_company_insider_transactions,
                    self.toolkit.get_simfin_balance_sheet,
                    self.toolkit.get_simfin_cashflow,
                    self.toolkit.get_simfin_income_stmt,
                    # China Market Tools (Alternate)
                    self.toolkit.get_china_stock_data,
                    self.toolkit.get_china_fundamentals,
                ]
            ),
            "index_analyst": ToolNode(
                [
                    # Market/index analysis tools
                    self.toolkit.get_stock_market_data_unified,
                    self.toolkit.get_YFin_data_online,
                    self.toolkit.get_stockstats_indicators_report_online,
                ]
            ),
            "sector_analyst": ToolNode(
                [
                    # Industry/sector analysis tools
                    self.toolkit.get_stock_market_data_unified,
                    self.toolkit.get_china_stock_data,
                    self.toolkit.get_china_fundamentals,
                ]
            ),
        }

    def propagate(self, company_name, trade_date, progress_callback=None, task_id=None, agent_context: Dict[str, Any] = None):
        """Run the trading agents graph for a company on a specific date.

        Args:
            company_name: Company name or stock symbol
            trade_date: Date for analysis
            progress_callback: Optional callback function for progress updates
            task_id: Optional task ID for tracking performance data
        """

        # Add detailed receiving log
        logger.debug(f"🔍 [GRAPH DEBUG] ===== TradingAgentsGraph.propagate Receive parameters =====")
        logger.debug(f"🔍 [GRAPH DEBUG] received company_name: '{company_name}' (Type: {type(company_name)})")
        logger.debug(f"🔍 [GRAPH DEBUG] received trade_date: '{trade_date}' (Type: {type(trade_date)})")
        logger.debug(f"🔍 [GRAPH DEBUG] received task_id: '{task_id}'")

        self.ticker = company_name
        logger.debug(f"🔍 [GRAPH DEBUG] settings self.ticker: '{self.ticker}'")

        # Initialize state
        logger.debug(f"🔍 [GRAPH DEBUG] Create initial state and pass parameters: company_name='{company_name}', trade_date='{trade_date}'")
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, agent_context
        )
        logger.debug(f"🔍 [GRAPH DEBUG] in initial state company_of_interest: '{init_agent_state.get('company_of_interest', 'NOT_FOUND')}'")
        logger.debug(f"🔍 [GRAPH DEBUG] in initial state trade_date: '{init_agent_state.get('trade_date', 'NOT_FOUND')}'")

        # Initialize timer
        node_timings = {}  # Record the execution time of each node
        total_start_time = time.time()  # overall start time
        current_node_start = None  # Current node start time
        current_node_name = None  # Current node name

        # Save task_id for subsequent saving of performance data
        self._current_task_id = task_id

        # Choose different ones depending on whether there is a progress callback stream_mode
        args = self.propagator.get_graph_args(use_progress_callback=bool(progress_callback))

        if self.debug:
            # Debug mode with tracing and progress updates
            trace = []
            final_state = None
            for chunk in self.graph.stream(init_agent_state, **args):
                # Record node timings
                for node_name in chunk.keys():
                    if not node_name.startswith('__'):
                        # If there is a previous node, record its end time
                        if current_node_name and current_node_start:
                            elapsed = time.time() - current_node_start
                            node_timings[current_node_name] = elapsed
                            logger.info(f"⏱️ [{current_node_name}] Time consuming: {elapsed:.2f}seconds")

                        # Start new node timing
                        current_node_name = node_name
                        current_node_start = time.time()
                        break

                # In updates mode, the chunk format is {node_name: state_update}
                # In values mode, the chunk format is complete
                if progress_callback and args.get("stream_mode") == "updates":
                    # updates Mode:chunk = {"Market Analyst": {...}}
                    self._send_progress_update(chunk, progress_callback)
                    # Cumulative status updates
                    if final_state is None:
                        final_state = init_agent_state.copy()
                    for node_name, node_update in chunk.items():
                        if not node_name.startswith('__'):
                            if isinstance(node_update, dict):
                                try:
                                    final_state.update(node_update)
                                except Exception:
                                    final_state[node_name] = node_update
                            else:
                                final_state[node_name] = node_update
                else:
                    # values Mode:chunk = {"messages": [...], ...}
                    if len(chunk.get("messages", [])) > 0:
                        chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
                    final_state = chunk

            if not trace and final_state:
                # updates mode, using the accumulated status
                pass
            elif trace:
                final_state = trace[-1]
        else:
            # Standard mode without tracing but with progress updates
            if progress_callback:
                # Use updates mode to get node-level progress
                trace = []
                final_state = None
                for chunk in self.graph.stream(init_agent_state, **args):
                    # Record node timings
                    for node_name in chunk.keys():
                        if not node_name.startswith('__'):
                            # If there is a previous node, record its end time
                            if current_node_name and current_node_start:
                                elapsed = time.time() - current_node_start
                                node_timings[current_node_name] = elapsed
                                logger.info(f"⏱️ [{current_node_name}] Time consuming: {elapsed:.2f}seconds")
                                logger.info(f"🔍 [TIMING] Node switching: {current_node_name} → {node_name}")

                            # Start new node timing
                            current_node_name = node_name
                            current_node_start = time.time()
                            logger.info(f"🔍 [TIMING] Start timing: {node_name}")
                            break

                    self._send_progress_update(chunk, progress_callback)
                    # Cumulative status updates
                    if final_state is None:
                        final_state = init_agent_state.copy()
                    for node_name, node_update in chunk.items():
                        if not node_name.startswith('__'):
                            if isinstance(node_update, dict):
                                try:
                                    final_state.update(node_update)
                                except Exception:
                                    final_state[node_name] = node_update
                            else:
                                final_state[node_name] = node_update
            else:
                # Original invoke mode (also requires timing)
                logger.info("⏱️ Perform analysis using invoke mode (no progress callback)")
                # Use stream mode for timing purposes but do not send progress updates
                trace = []
                final_state = None
                for chunk in self.graph.stream(init_agent_state, **args):
                    # Record node timings
                    for node_name in chunk.keys():
                        if not node_name.startswith('__'):
                            # If there is a previous node, record its end time
                            if current_node_name and current_node_start:
                                elapsed = time.time() - current_node_start
                                node_timings[current_node_name] = elapsed
                                logger.info(f"⏱️ [{current_node_name}] Time consuming: {elapsed:.2f}seconds")

                            # Start new node timing
                            current_node_name = node_name
                            current_node_start = time.time()
                            break

                    # Cumulative status updates
                    if final_state is None:
                        final_state = init_agent_state.copy()
                    for node_name, node_update in chunk.items():
                        if not node_name.startswith('__'):
                            if isinstance(node_update, dict):
                                try:
                                    final_state.update(node_update)
                                except Exception:
                                    final_state[node_name] = node_update
                            else:
                                final_state[node_name] = node_update

        # Record the time of the last node
        if current_node_name and current_node_start:
            elapsed = time.time() - current_node_start
            node_timings[current_node_name] = elapsed
            logger.info(f"⏱️ [{current_node_name}] Time consuming: {elapsed:.2f}seconds")

        # Calculate total time
        total_elapsed = time.time() - total_start_time

        # debug log
        logger.info(f"🔍 [TIMING DEBUG] Node timing number: {len(node_timings)}")
        logger.info(f"🔍 [TIMING DEBUG] Total time spent: {total_elapsed:.2f}seconds")
        logger.info(f"🔍 [TIMING DEBUG] node list: {list(node_timings.keys())}")

        # Print detailed time statistics
        logger.info("🔍 [TIMING DEBUG] ready to call _print_timing_summary")
        self._print_timing_summary(node_timings, total_elapsed)
        logger.info("🔍 [TIMING DEBUG] _print_timing_summary Call completed")

        # Build performance data
        performance_data = self._build_performance_data(node_timings, total_elapsed)

        # Add performance data to status
        final_state['performance_metrics'] = performance_data

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Get model information
        model_info = ""
        try:
            if hasattr(self.deep_thinking_llm, 'model_name'):
                model_info = f"{self.deep_thinking_llm.__class__.__name__}:{self.deep_thinking_llm.model_name}"
            else:
                model_info = self.deep_thinking_llm.__class__.__name__
        except Exception:
            model_info = "Unknown"

        # Process decisions and add model information
        decision = self.process_signal(final_state["final_trade_decision"], company_name)
        decision['model_info'] = model_info

        # Return decision and processed signal
        return final_state, decision

    def _send_progress_update(self, chunk, progress_callback):
        """Send progress updates to the callback function

        LangGraph stream Returned chunk format:{node_name: {...}}
        Node name example:
        - "Market Analyst", "Fundamentals Analyst", "News Analyst", "Social Analyst"
        - "tools_market", "tools_fundamentals", "tools_news", "tools_social"
        - "Msg Clear Market", "Msg Clear Fundamentals", etc.
        - "Bull Researcher", "Bear Researcher", "Research Manager"
        - "Trader"
        - "Risky Analyst", "Safe Analyst", "Neutral Analyst", "Risk Judge"
        """
        try:
            # Extract currently executing node information from chunk
            if not isinstance(chunk, dict):
                return

            # Get the first non-special key as node name
            node_name = None
            for key in chunk.keys():
                if not key.startswith('__'):
                    node_name = key
                    break

            if not node_name:
                return

            logger.info(f"🔍 [Progress] Node name: {node_name}")

            # Check if it is the end node
            if '__end__' in chunk:
                logger.info(f"📊 [Progress] __end__ node detected")
                progress_callback("📊 Generate report")
                return

            # Node name mapping table (matches LangGraph actual node names)
            node_mapping = {
                # Analyst Node
                'Market Analyst': "📊 market analyst",
                'Fundamentals Analyst': "💼 fundamental analyst",
                'News Analyst': "📰 news analyst",
                'Social Analyst': "💬 social media analyst",
                # Tool nodes (do not send progress updates to avoid duplication)
                'tools_market': None,
                'tools_fundamentals': None,
                'tools_news': None,
                'tools_social': None,
                # Message cleanup node (does not send progress updates)
                'Msg Clear Market': None,
                'Msg Clear Fundamentals': None,
                'Msg Clear News': None,
                'Msg Clear Social': None,
                # Researcher Node
                'Bull Researcher': "🐂 bullish researcher",
                'Bear Researcher': "🐻 bearish researcher",
                'Research Manager': "👔 research manager",
                # Research integration node
                'Trader': "🧩 Summary of research integrators",
                # Risk assessment node
                'Risky Analyst': "🔥 Radical risk assessment",
                'Safe Analyst': "🛡️ conservative risk assessment",
                'Neutral Analyst': "⚖️ neutral risk assessment",
                'Risk Judge': "🎯 risk manager",
            }

            # Find mapped messages
            message = node_mapping.get(node_name)

            if message is None:
                # None Indicates skipping (tool nodes, message cleaning nodes)
                logger.debug(f"⏭️ [Progress] skip node: {node_name}")
                return

            if message:
                # Send progress updates
                logger.info(f"📤 [Progress] Send progress updates: {message}")
                progress_callback(message)
            else:
                # Unknown node, use node name
                logger.warning(f"⚠️ [Progress] unknown node: {node_name}")
                progress_callback(f"🔍 {node_name}")

        except Exception as e:
            logger.error(f"❌ Progress update failed: {e}", exc_info=True)

    def _build_performance_data(self, node_timings: Dict[str, float], total_elapsed: float) -> Dict[str, Any]:
        """Build performance data structures

        Args:
            node_timings: Dictionary of execution times for each node
            total_elapsed: total execution time

        Returns:
            Performance Data Dictionary
        """
        # Node classification (Note: Risk management nodes should be judged before analyst nodes because they also contain'Analyst') 
        analyst_nodes = {}
        tool_nodes = {}
        msg_clear_nodes = {}
        research_nodes = {}
        trader_nodes = {}
        risk_nodes = {}
        other_nodes = {}

        for node_name, elapsed in node_timings.items():
            # Prioritize matching risk management teams (as they also include'Analyst') 
            if 'Risky' in node_name or 'Safe' in node_name or 'Neutral' in node_name or 'Risk Judge' in node_name:
                risk_nodes[node_name] = elapsed
            # Then match the analyst team
            elif 'Analyst' in node_name:
                analyst_nodes[node_name] = elapsed
            # tool node
            elif node_name.startswith('tools_'):
                tool_nodes[node_name] = elapsed
            # Message cleaning node
            elif node_name.startswith('Msg Clear'):
                msg_clear_nodes[node_name] = elapsed
            # research team
            elif 'Researcher' in node_name or 'Research Manager' in node_name:
                research_nodes[node_name] = elapsed
            # trading team
            elif 'Trader' in node_name:
                trader_nodes[node_name] = elapsed
            # Other nodes
            else:
                other_nodes[node_name] = elapsed

        # Calculate statistics
        slowest_node = max(node_timings.items(), key=lambda x: x[1]) if node_timings else (None, 0)
        fastest_node = min(node_timings.items(), key=lambda x: x[1]) if node_timings else (None, 0)
        avg_time = sum(node_timings.values()) / len(node_timings) if node_timings else 0

        return {
            "total_time": round(total_elapsed, 2),
            "total_time_minutes": round(total_elapsed / 60, 2),
            "node_count": len(node_timings),
            "average_node_time": round(avg_time, 2),
            "slowest_node": {
                "name": slowest_node[0],
                "time": round(slowest_node[1], 2)
            } if slowest_node[0] else None,
            "fastest_node": {
                "name": fastest_node[0],
                "time": round(fastest_node[1], 2)
            } if fastest_node[0] else None,
            "node_timings": {k: round(v, 2) for k, v in node_timings.items()},
            "category_timings": {
                "analyst_team": {
                    "nodes": {k: round(v, 2) for k, v in analyst_nodes.items()},
                    "total": round(sum(analyst_nodes.values()), 2),
                    "percentage": round(sum(analyst_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                },
                "tool_calls": {
                    "nodes": {k: round(v, 2) for k, v in tool_nodes.items()},
                    "total": round(sum(tool_nodes.values()), 2),
                    "percentage": round(sum(tool_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                },
                "message_clearing": {
                    "nodes": {k: round(v, 2) for k, v in msg_clear_nodes.items()},
                    "total": round(sum(msg_clear_nodes.values()), 2),
                    "percentage": round(sum(msg_clear_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                },
                "research_team": {
                    "nodes": {k: round(v, 2) for k, v in research_nodes.items()},
                    "total": round(sum(research_nodes.values()), 2),
                    "percentage": round(sum(research_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                },
                "trader_team": {
                    "nodes": {k: round(v, 2) for k, v in trader_nodes.items()},
                    "total": round(sum(trader_nodes.values()), 2),
                    "percentage": round(sum(trader_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                },
                "risk_management_team": {
                    "nodes": {k: round(v, 2) for k, v in risk_nodes.items()},
                    "total": round(sum(risk_nodes.values()), 2),
                    "percentage": round(sum(risk_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                },
                "other": {
                    "nodes": {k: round(v, 2) for k, v in other_nodes.items()},
                    "total": round(sum(other_nodes.values()), 2),
                    "percentage": round(sum(other_nodes.values()) / total_elapsed * 100, 1) if total_elapsed > 0 else 0
                }
            },
            "llm_config": {
                "provider": self.config.get('llm_provider', 'unknown'),
                "deep_think_model": self.config.get('deep_think_llm', 'unknown'),
                "quick_think_model": self.config.get('quick_think_llm', 'unknown')
            }
        }

    def _print_timing_summary(self, node_timings: Dict[str, float], total_elapsed: float):
        """Print detailed time statistics report

        Args:
            node_timings: Dictionary of execution times for each node
            total_elapsed: total execution time
        """
        logger.info("🔍 [_print_timing_summary] method is called")
        logger.info("🔍 [_print_timing_summary] node_timings Quantity: " + str(len(node_timings)))
        logger.info("🔍 [_print_timing_summary] total_elapsed: " + str(total_elapsed))

        logger.info("=" * 80)
        logger.info("⏱️  Analyze performance statistics reports")
        logger.info("=" * 80)

        # Node classification (Note: Risk management nodes should be judged before analyst nodes because they also contain'Analyst') 
        analyst_nodes = []
        tool_nodes = []
        msg_clear_nodes = []
        research_nodes = []
        trader_nodes = []
        risk_nodes = []
        other_nodes = []

        for node_name, elapsed in node_timings.items():
            # Prioritize matching risk management teams (as they also include'Analyst') 
            if 'Risky' in node_name or 'Safe' in node_name or 'Neutral' in node_name or 'Risk Judge' in node_name:
                risk_nodes.append((node_name, elapsed))
            # Then match the analyst team
            elif 'Analyst' in node_name:
                analyst_nodes.append((node_name, elapsed))
            # tool node
            elif node_name.startswith('tools_'):
                tool_nodes.append((node_name, elapsed))
            # Message cleaning node
            elif node_name.startswith('Msg Clear'):
                msg_clear_nodes.append((node_name, elapsed))
            # research team
            elif 'Researcher' in node_name or 'Research Manager' in node_name:
                research_nodes.append((node_name, elapsed))
            # trading team
            elif 'Trader' in node_name:
                trader_nodes.append((node_name, elapsed))
            # Other nodes
            else:
                other_nodes.append((node_name, elapsed))

        # Print classification statistics
        def print_category(title: str, nodes: List[Tuple[str, float]]):
            if not nodes:
                return
            logger.info(f"\n📊 {title}")
            logger.info("-" * 80)
            total_category_time = sum(t for _, t in nodes)
            for node_name, elapsed in sorted(nodes, key=lambda x: x[1], reverse=True):
                percentage = (elapsed / total_elapsed * 100) if total_elapsed > 0 else 0
                logger.info(f"  • {node_name:40s} {elapsed:8.2f}seconds  ({percentage:5.1f}%)")
            logger.info(f"  {'Subtotal':40s} {total_category_time:8.2f}seconds  ({total_category_time/total_elapsed*100:5.1f}%)")

        print_category("Analyst Team", analyst_nodes)
        print_category("Tool call", tool_nodes)
        print_category("Message cleaning", msg_clear_nodes)
        print_category("research team", research_nodes)
        print_category("trading team", trader_nodes)
        print_category("risk management team", risk_nodes)
        print_category("Other nodes", other_nodes)

        # Print overall statistics
        logger.info("\n" + "=" * 80)
        logger.info(f"🎯 total execution time: {total_elapsed:.2f}seconds ({total_elapsed/60:.2f}minutes)")
        logger.info(f"📈 Total number of nodes: {len(node_timings)}")
        if node_timings:
            avg_time = sum(node_timings.values()) / len(node_timings)
            logger.info(f"⏱️  Average node time: {avg_time:.2f}seconds")
            slowest_node = max(node_timings.items(), key=lambda x: x[1])
            logger.info(f"🐌 slowest node: {slowest_node[0]} ({slowest_node[1]:.2f}seconds)")
            fastest_node = min(node_timings.items(), key=lambda x: x[1])
            logger.info(f"⚡ Fastest node: {fastest_node[0]} ({fastest_node[1]:.2f}seconds)")

        # Print LLM configuration information
        logger.info(f"\n🤖 LLM Configuration:")
        logger.info(f"  • provider: {self.config.get('llm_provider', 'unknown')}")
        logger.info(f"  • deep thinking model: {self.config.get('deep_think_llm', 'unknown')}")
        logger.info(f"  • quick thinking model: {self.config.get('quick_think_llm', 'unknown')}")
        logger.info("=" * 80)

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        # Use .get() Secure access to all fields, allowing users to select only some analysts
        investment_debate = final_state.get("investment_debate_state", {})
        risk_debate = final_state.get("risk_debate_state", {})

        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state.get("company_of_interest", ""),
            "trade_date": final_state.get("trade_date", ""),
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "investment_debate_state": {
                "bull_history": investment_debate.get("bull_history", ""),
                "bear_history": investment_debate.get("bear_history", ""),
                "history": investment_debate.get("history", ""),
                "current_response": investment_debate.get("current_response", ""),
                "judge_decision": investment_debate.get("judge_decision", ""),
            },
            "trader_investment_decision": final_state.get("trader_investment_plan", ""),
            "risk_debate_state": {
                "risky_history": risk_debate.get("risky_history", ""),
                "safe_history": risk_debate.get("safe_history", ""),
                "neutral_history": risk_debate.get("neutral_history", ""),
                "history": risk_debate.get("history", ""),
                "judge_decision": risk_debate.get("judge_decision", ""),
            },
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
        }

        # Save to file
        directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal, stock_symbol=None):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal, stock_symbol)
