"""
OpenAI Compatible adapter base class
Provide a unified basic implementation for all LLM providers that support the OpenAI interface
"""

import os
import time
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import CallbackManagerForLLMRun

# Import unified log system
from tradingagents.utils.logging_init import setup_llm_logging

# Import log module
from tradingagents.utils.logging_manager import get_logger, get_logger_manager
logger = get_logger('agents')
logger = setup_llm_logging()

KIMI_FIXED_TEMPERATURE_MODELS = ("kimi-k2.5", "kimi-k2.6")

# Import token tracker
try:
    from tradingagents.config.config_manager import token_tracker
    TOKEN_TRACKING_ENABLED = True
    logger.info("✅ Token Tracking is enabled")
except ImportError:
    TOKEN_TRACKING_ENABLED = False
    logger.warning("⚠️ Token Tracking is not enabled")


class OpenAICompatibleBase(ChatOpenAI):
    """
    OpenAI Compatible adapter base class
    Provides a unified implementation for all LLM providers that support the OpenAI interface
    """
    
    def __init__(
        self,
        provider_name: str,
        model: str,
        api_key_env_var: str,
        base_url: str,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize OpenAI compatible adapter
        
        Args:
            provider_name: Provider name (Such as: "deepseek", "dashscope")
            model: Model name
            api_key_env_var: API Key environment variable name
            base_url: API Basics URL
            api_key: API Key, obtained from environment variables if not provided
            temperature: Temperature parameter
            max_tokens: Maximum number of tokens
            **kwargs: Other parameters
        """
        
        # 🔍 [DEBUG] Log before reading environment variables
        logger.info(f"🔍 [{provider_name}initialization] Start initializing OpenAI compatible adapter")
        logger.info(f"🔍 [{provider_name}initialization] model: {model}")
        logger.info(f"🔍 [{provider_name}initialization] API Key Environment variable name: {api_key_env_var}")
        logger.info(f"🔍 [{provider_name}initialization] Whether to pass in the api_key parameter: {api_key is not None}")

        # Cache meta information into private properties before initializing the parent class (to avoid Pydantic field restrictions)
        object.__setattr__(self, "_provider_name", provider_name)
        object.__setattr__(self, "_model_name_alias", model)

        # Get API key
        if api_key is None:
            # Import API Key verification tool
            try:
                from app.utils.api_key_utils import is_valid_api_key
            except ImportError:
                def is_valid_api_key(key):
                    if not key or len(key) <= 10:
                        return False
                    if key.startswith('your_') or key.startswith('your-'):
                        return False
                    if key.endswith('_here') or key.endswith('-here'):
                        return False
                    if '...' in key:
                        return False
                    return True

            # 🔥 Not required for local model (Ollama) API Key
            if provider_name.lower() == "ollama":
                logger.info(f"ℹ️  [{provider_name}initialization] Ollama It is a local model, does not require API Key, uses placeholders")
                api_key = "ollama"  # The local model uses placeholders and is not actually verified.
            else:
                # Read from environment variables API Key
                env_api_key = os.getenv(api_key_env_var)
                logger.info(f"🔍 [{provider_name}initialization] Read from environment variables {api_key_env_var}: {'valuable' if env_api_key else 'empty'}")

                # Verify that the API Key in the environment variable is valid (excluding placeholders)
                if env_api_key and is_valid_api_key(env_api_key):
                    logger.info(f"✅ [{provider_name}initialization] The API Key in the environment variable is valid and the length is: {len(env_api_key)}, Top 10: {env_api_key[:100]}...")
                    api_key = env_api_key
                elif env_api_key:
                    logger.warning(f"⚠️ [{provider_name}initialization] The API Key in the environment variable is invalid (possibly a placeholder) and will be ignored")
                    api_key = None
                else:
                    logger.warning(f"⚠️ [{provider_name}initialization] {api_key_env_var} environment variable is empty")
                    api_key = None

                if not api_key:
                    logger.error(f"❌ [{provider_name}initialization] API Key The check failed and an exception will be thrown")
                    raise ValueError(
                        f"{provider_name} API Key not found."
                        f"Please configure in the web interface API Key (settings -> Large model manufacturer) or set {api_key_env_var} environment variables."
                    )
        else:
            logger.info(f"✅ [{provider_name}initialization] Use the passed API Key (from database configuration), length: {len(api_key)}")
        
        # Set OpenAI compatible parameters
        # Note: The model parameter will be mapped to the model_name field by Pydantic
        openai_kwargs = {
            "model": model,  # This will be mapped to the model_name field
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        # Use different parameter names according to LangChain version
        try:
            # new version LangChain
            openai_kwargs.update({
                "api_key": api_key,
                "base_url": base_url
            })
        except:
            # old version LangChain
            openai_kwargs.update({
                "openai_api_key": api_key,
                "openai_api_base": base_url
            })
        
        # Initialize parent class
        super().__init__(**openai_kwargs)

        # Again make sure the meta information is present (some implementations will super()Reset in __dict__)
        object.__setattr__(self, "_provider_name", provider_name)
        object.__setattr__(self, "_model_name_alias", model)

        logger.info(f"✅ {provider_name} OpenAI Compatible adapter initialized successfully")
        logger.info(f"   model: {model}")
        logger.info(f"   API Base: {base_url}")

    @property
    def provider_name(self) -> Optional[str]:
        return getattr(self, "_provider_name", None)

    # Remove model_name property definition and use Pydantic fields
    # model_name Fields are provided by Pydantic fields of the ChatOpenAI base class
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate chat responses and record token usage
        """
        
        # Recording start time
        start_time = time.time()
        
        # Call the parent class generation method
        result = super()._generate(messages, stop, run_manager, **kwargs)
        
        # Record token usage
        self._track_token_usage(result, kwargs, start_time)
        
        return result

    def _track_token_usage(self, result: ChatResult, kwargs: Dict, start_time: float):
        """Record token usage and output logs"""
        # 🛡️ Q1-3: finish_reason Permanent traces (not affected by TOKEN_TRACKING_ENABLED switch)
        # stop=End normally;length=Output is truncated by max_tokens; empty content with this field can be positioned in 5 seconds"Thought exhaustion/transient exception"
        finish_reason, content_len, reasoning_tokens = None, None, None
        try:
            _gen = result.generations[0] if getattr(result, "generations", None) else None
            _msg = getattr(_gen, "message", None) if _gen else None
            _meta = getattr(_msg, "response_metadata", None) or {}
            finish_reason = _meta.get("finish_reason")
            content_len = len(getattr(_msg, "content", "") or "")
            _usage_meta = getattr(_msg, "usage_metadata", None) or {}
            reasoning_tokens = ((_usage_meta.get("output_token_details") or {}).get("reasoning"))
            if (finish_reason is not None and finish_reason != "stop") or content_len == 0:
                logger.warning(
                    f"⚠️ [LLM Response abnormal characteristics] Provider: {getattr(self, 'provider_name', 'unknown')}, "
                    f"Model: {getattr(self, 'model_name', 'unknown')}, "
                    f"finish_reason={finish_reason}, content length={content_len}, think tokens={reasoning_tokens}"
                )
        except Exception as e:
            logger.debug(f"finish_reason Logging failed: {e}")

        if not TOKEN_TRACKING_ENABLED:
            return
        try:
            # Statistics token information
            usage = getattr(result, "usage_metadata", None)
            total_tokens = usage.get("total_tokens") if usage else None
            prompt_tokens = usage.get("input_tokens") if usage else None
            completion_tokens = usage.get("output_tokens") if usage else None

            elapsed = time.time() - start_time
            logger.info(
                f"📊 Token Use - Provider: {getattr(self, 'provider_name', 'unknown')}, Model: {getattr(self, 'model_name', 'unknown')}, "
                f"total tokens: {total_tokens}, Tips: {prompt_tokens}, Complete: {completion_tokens}, time: {elapsed:.2f}s, "
                f"finish_reason: {finish_reason}, think tokens: {reasoning_tokens}, content length: {content_len}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Token Trace recording failed: {e}")


def _canonical_model_name(model: str) -> str:
    normalized = str(model or "").strip().lower()
    if "::" in normalized:
        _, normalized = normalized.split("::", 1)
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def normalize_openai_temperature(
    provider: Optional[str],
    model: str,
    temperature: Optional[float],
    base_url: Optional[str] = None,
) -> Optional[float]:
    """Normalize provider/model-specific temperature constraints before request dispatch."""
    canonical_model = _canonical_model_name(model)
    if not canonical_model.startswith(KIMI_FIXED_TEMPERATURE_MODELS):
        return temperature

    normalized_provider = str(provider or "").strip().lower()
    normalized_base_url = str(base_url or "").strip().lower()
    is_moonshot_compatible = (
        normalized_provider in {"kimi", "moonshot", "custom_openai"}
        or "moonshot" in normalized_base_url
    )
    if not is_moonshot_compatible:
        return temperature

    forced_temperature = 1.0
    try:
        current_temperature = float(temperature) if temperature is not None else None
    except (TypeError, ValueError):
        current_temperature = None

    if current_temperature != forced_temperature:
        logger.info(
            f"🌡️ [LLM Parameter normalization] provider={provider}, model={model} Hit Kimi temperature limit,"
            f"temperature {temperature} -> {forced_temperature}"
        )

    return forced_temperature


class ChatDeepSeekOpenAI(OpenAICompatibleBase):
    """DeepSeek OpenAI Compatible adapter"""
    
    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        super().__init__(
            provider_name="deepseek",
            model=model,
            api_key_env_var="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


class ChatDashScopeOpenAIUnified(OpenAICompatibleBase):
    """Alibaba Bailian DashScope OpenAI Compatible Adapter"""
    
    def __init__(
        self,
        model: str = "qwen-turbo",
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        super().__init__(
            provider_name="dashscope",
            model=model,
            api_key_env_var="DASHSCOPE_API_KEY",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


class ChatQianfanOpenAI(OpenAICompatibleBase):
    """Wenxin Yiyan Qianfan Platform OpenAI Compatible Adapter"""
    
    def __init__(
        self,
        model: str = "ernie-3.5-8k",
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        # Qianfan's new generation API uses a single API Key authentication
        # Format: bce-v3/ALTAK-xxx/xxx

        # If no API Key is passed in, try reading from environment variables
        if not api_key:
            # Import API Key verification tool
            try:
                from app.utils.api_key_utils import is_valid_api_key
            except ImportError:
                def is_valid_api_key(key):
                    if not key or len(key) <= 10:
                        return False
                    if key.startswith('your_') or key.startswith('your-'):
                        return False
                    if key.endswith('_here') or key.endswith('-here'):
                        return False
                    if '...' in key:
                        return False
                    return True

            env_api_key = os.getenv('QIANFAN_API_KEY')
            if env_api_key and is_valid_api_key(env_api_key):
                qianfan_api_key = env_api_key
            else:
                qianfan_api_key = None
        else:
            qianfan_api_key = api_key

        if not qianfan_api_key:
            raise ValueError(
                "Qianfan model needs to configure API Key."
                "Please configure in the web interface (settings -> Large model manufacturer) or set the QIANFAN_API_KEY environment variable,"
                "The format is: bce-v3/ALTAK-xxx/xxx"
            )

        if not qianfan_api_key.startswith('bce-v3/'):
            raise ValueError(
                "QIANFAN_API_KEY Format error, should be: bce-v3/ALTAK-xxx/xxx"
            )
        
        super().__init__(
            provider_name="qianfan",
            model=model,
            api_key_env_var="QIANFAN_API_KEY",
            base_url="https://qianfan.baidubce.com/v2",
            api_key=qianfan_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimating the number of tokens in text (exclusively for Qianfan model)"""
        # The token estimate of Qianfan model: about 1.5 characters/token in Chinese and about 4 characters in English/token
        # Conservative estimate: 2 characters/token
        return max(1, len(text) // 2)
    
    def _truncate_messages(self, messages: List[BaseMessage], max_tokens: int = 4500) -> List[BaseMessage]:
        """Truncate the message to fit the token limit of the Qianfan model"""
        # Reserve some token space for the Qianfan model, use 4500 instead 5120
        truncated_messages = []
        total_tokens = 0
        
        # Start with the last message and keep messages going forward
        for message in reversed(messages):
            content = str(message.content) if hasattr(message, 'content') else str(message)
            message_tokens = self._estimate_tokens(content)
            
            if total_tokens + message_tokens <= max_tokens:
                truncated_messages.insert(0, message)
                total_tokens += message_tokens
            else:
                # If it is the first message and is too long, truncate the content.
                if not truncated_messages:
                    remaining_tokens = max_tokens - 100  # 100 reserved token
                    max_chars = remaining_tokens * 2  # 2 character/token
                    truncated_content = content[:max_chars] + "...(Content has been truncated)"
                    
                    # Create truncated message
                    if hasattr(message, 'content'):
                        message.content = truncated_content
                    truncated_messages.insert(0, message)
                break
        
        if len(truncated_messages) < len(messages):
            logger.warning(f"⚠️ The Qianfan model input is too long and has been truncated. {len(messages) - len(truncated_messages)} messages")
        
        return truncated_messages
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a chat response, including the token truncation logic of the Qianfan model"""
        
        # Input token truncation for Qianfan model
        truncated_messages = self._truncate_messages(messages)
        
        # Call the _generate method of the parent class
        return super()._generate(truncated_messages, stop, run_manager, **kwargs)


class ChatZhipuOpenAI(OpenAICompatibleBase):
    """GLM AI GLM OpenAI Compatible Adapter"""
    
    def __init__(
        self,
        model: str = "glm-4.6",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        if base_url is None:
            env_base_url = os.getenv("ZHIPU_BASE_URL")
            # Only use valid environment variable values (not placeholders)
            if env_base_url and not env_base_url.startswith('your_') and not env_base_url.startswith('your-'):
                base_url = env_base_url
            else:
                base_url = "https://open.bigmodel.cn/api/paas/v4"
                
        super().__init__(
            provider_name="zhipu",
            model=model,
            api_key_env_var="ZHIPU_API_KEY",
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimating the number of tokens in text (dedicated to GLM model)"""
        # GLM Token estimation of the model: about 1.5 characters/token for Chinese and about 4 characters for English/token
        # Conservative estimate: 2 characters/token
        return max(1, len(text) // 2)


class ChatCustomOpenAI(OpenAICompatibleBase):
    """Custom OpenAI endpoint adapter (proxy/aggregation platform)"""

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        # If base_url is not passed in, try reading from the environment variable
        if base_url is None:
            env_base_url = os.getenv("CUSTOM_OPENAI_BASE_URL")
            # Only use valid environment variable values (not placeholders)
            if env_base_url and not env_base_url.startswith('your_') and not env_base_url.startswith('your-'):
                base_url = env_base_url
            else:
                base_url = "https://api.openai.com/v1"

        super().__init__(
            provider_name="custom_openai",
            model=model,
            api_key_env_var="CUSTOM_OPENAI_API_KEY",
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


class ChatVolcengineOpenAI(OpenAICompatibleBase):
    """Volcengine Ark Agent Plan OpenAI Compatible Adapter

    Support reasoning_effort parameter to control reasoning model thinking depth.
    value: none/minimal/low/medium/high/xhigh/max
    """

    def __init__(
        self,
        model: str = "doubao-seed-2-1-turbo-260628",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        if base_url is None:
            env_base_url = os.getenv("VOLCENGINE_BASE_URL")
            if env_base_url and not env_base_url.startswith('your_'):
                base_url = env_base_url
            else:
                base_url = "https://ark.cn-beijing.volces.com/api/v3"

        super().__init__(
            provider_name="volcengine",
            model=model,
            api_key_env_var="VOLCENGINE_API_KEY",
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


class ChatVolcengineCodingOpenAI(OpenAICompatibleBase):
    """Volcano Ark Coding Plan OpenAI Compatible Adapter

    Coding Plan Only about 10 encoding related models are supported, base_url is different from Agent Plan.
    """

    def __init__(
        self,
        model: str = "doubao-seed-2.0-code",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        if base_url is None:
            env_base_url = os.getenv("VOLCENGINE_CODING_BASE_URL")
            if env_base_url and not env_base_url.startswith('your_'):
                base_url = env_base_url
            else:
                base_url = "https://ark.cn-beijing.volces.com/api/coding/v3"

        super().__init__(
            provider_name="volcengine_coding",
            model=model,
            api_key_env_var="VOLCENGINE_CODING_API_KEY",
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )


# Supported OpenAI compatible model configurations
OPENAI_COMPATIBLE_PROVIDERS = {
    "deepseek": {
        "adapter_class": ChatDeepSeekOpenAI,
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": {
            "deepseek-chat": {"context_length": 32768, "supports_function_calling": True},
            "deepseek-coder": {"context_length": 16384, "supports_function_calling": True}
        }
    },
    "dashscope": {
        "adapter_class": ChatDashScopeOpenAIUnified,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "models": {
            "qwen-turbo": {"context_length": 8192, "supports_function_calling": True},
            "qwen-plus": {"context_length": 32768, "supports_function_calling": True},
            "qwen-plus-latest": {"context_length": 32768, "supports_function_calling": True},
            "qwen-max": {"context_length": 32768, "supports_function_calling": True},
            "qwen-max-latest": {"context_length": 32768, "supports_function_calling": True}
        }
    },
    "qianfan": {
        "adapter_class": ChatQianfanOpenAI,
        "base_url": "https://qianfan.baidubce.com/v2",
        "api_key_env": "QIANFAN_API_KEY",
        "models": {
            "ernie-3.5-8k": {"context_length": 5120, "supports_function_calling": True},
            "ernie-4.0-turbo-8k": {"context_length": 5120, "supports_function_calling": True},
            "ERNIE-Speed-8K": {"context_length": 5120, "supports_function_calling": True},
            "ERNIE-Lite-8K": {"context_length": 5120, "supports_function_calling": True}
        }
    },
    "zhipu": {
        "adapter_class": ChatZhipuOpenAI,
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "models": {
            "glm-4.6": {"context_length": 200000, "supports_function_calling": True},
            "glm-4": {"context_length": 128000, "supports_function_calling": True},
            "glm-4-plus": {"context_length": 128000, "supports_function_calling": True},
            "glm-3-turbo": {"context_length": 128000, "supports_function_calling": True}
        }
    },
    "volcengine": {
        "adapter_class": ChatVolcengineOpenAI,
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key_env": "VOLCENGINE_API_KEY",
        "models": {
            "doubao-seed-2-1-turbo-260628": {"context_length": 128000, "supports_function_calling": True},
            "doubao-seed-2-1-turbo": {"context_length": 128000, "supports_function_calling": True},
            "doubao-seed-2.0": {"context_length": 128000, "supports_function_calling": True},
        }
    },
    "volcengine_coding": {
        "adapter_class": ChatVolcengineCodingOpenAI,
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "api_key_env": "VOLCENGINE_CODING_API_KEY",
        "models": {
            "doubao-seed-2.0-code": {"context_length": 128000, "supports_function_calling": True},
            "doubao-seed-1.6-code": {"context_length": 128000, "supports_function_calling": True},
        }
    },
    "custom_openai": {
        "adapter_class": ChatCustomOpenAI,
        "base_url": None,  # Will be configured by the user
        "api_key_env": "CUSTOM_OPENAI_API_KEY",
        "models": {
            "gpt-3.5-turbo": {"context_length": 16384, "supports_function_calling": True},
            "gpt-4": {"context_length": 8192, "supports_function_calling": True},
            "gpt-4-turbo": {"context_length": 128000, "supports_function_calling": True},
            "gpt-4o": {"context_length": 128000, "supports_function_calling": True},
            "gpt-4o-mini": {"context_length": 128000, "supports_function_calling": True},
            "claude-3-haiku": {"context_length": 200000, "supports_function_calling": True},
            "claude-3-sonnet": {"context_length": 200000, "supports_function_calling": True},
            "claude-3-opus": {"context_length": 200000, "supports_function_calling": True},
            "claude-3.5-sonnet": {"context_length": 200000, "supports_function_calling": True},
            "gemini-pro": {"context_length": 32768, "supports_function_calling": True},
            "gemini-1.5-pro": {"context_length": 1000000, "supports_function_calling": True},
            "llama-3.1-8b": {"context_length": 128000, "supports_function_calling": True},
            "llama-3.1-70b": {"context_length": 128000, "supports_function_calling": True},
            "llama-3.1-405b": {"context_length": 128000, "supports_function_calling": True},
            "custom-model": {"context_length": 32768, "supports_function_calling": True}
        }
    }
}


def create_openai_compatible_llm(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    base_url: Optional[str] = None,
    **kwargs
) -> OpenAICompatibleBase:
    """Unified factory function for creating OpenAI compatible LLM instances"""
    provider_info = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    if not provider_info:
        raise ValueError(f"Unsupported OpenAI compatible providers: {provider}")

    adapter_class = provider_info["adapter_class"]

    # If base_url is not provided in the call, the default value of provider is taken (possibly None)
    if base_url is None:
        base_url = provider_info.get("base_url")

    temperature = normalize_openai_temperature(
        provider=provider,
        model=model,
        temperature=temperature,
        base_url=base_url,
    )

    # The base_url is passed to the adapter only if the provider does not have base_url built in (such as custom_openai),
    # Avoid contact with adapter internal super().__init__(..., base_url=...) Conflict leads to "multiple values" Error.
    init_kwargs = dict(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    if provider_info.get("base_url") is None and base_url:
        init_kwargs["base_url"] = base_url

    return adapter_class(**init_kwargs)


def test_openai_compatible_adapters():
    """Quickly test whether all adapters can be instantiated correctly (without making real requests)"""
    for provider, info in OPENAI_COMPATIBLE_PROVIDERS.items():
        cls = info["adapter_class"]
        try:
            if provider == "custom_openai":
                cls(model="gpt-3.5-turbo", api_key="test", base_url="https://api.openai.com/v1")
            elif provider == "qianfan":
                # Qianfan's new generation API only requires QIANFAN_API_KEY, format: bce-v3/ALTAK-xxx/xxx
                cls(model="ernie-3.5-8k", api_key="bce-v3/test-key/test-secret")
            else:
                cls(model=list(info["models"].keys())[0], api_key="test")
            logger.info(f"✅ Adapter instantiated successfully: {provider}")
        except Exception as e:
            logger.warning(f"⚠️ Adapter instantiation failed (expected or ignorable): {provider} - {e}")


if __name__ == "__main__":
    test_openai_compatible_adapters()
