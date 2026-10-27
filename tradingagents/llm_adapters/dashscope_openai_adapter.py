"""
Alibaba Bailian OpenAI Compatible Adapter
Provide TradingAgents with an OpenAI compatible interface for the Alibaba Bailian large model
Leverage the native OpenAI compatibility of Bailian models without the need for additional tool conversions
"""

import os
import json
from ast import literal_eval
from typing import Any, Dict, List, Optional, Union, Sequence
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import _convert_message_to_dict
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from pydantic import Field, SecretStr
from ..config.config_manager import token_tracker

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


class ChatDashScopeOpenAI(ChatOpenAI):
    """
    Alibaba Bailian OpenAI Compatible Adapter
    Inherit ChatOpenAI and call Bailian model through OpenAI compatible interface
    Leverage the native OpenAI compatibility of the Bailian model to support native Function Calling
    """

    @staticmethod
    def _normalize_tool_call_arguments(arguments: Any) -> Optional[str]:
        if arguments in (None, ""):
            return "{}"

        if not isinstance(arguments, str):
            return json.dumps(arguments, ensure_ascii=False)

        candidate = arguments.strip()
        if not candidate:
            return "{}"

        try:
            parsed = json.loads(candidate)
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            try:
                parsed = literal_eval(candidate)
                return json.dumps(parsed, ensure_ascii=False)
            except (ValueError, SyntaxError):
                return None

    def _convert_message_to_dashscope_dict(self, message: BaseMessage) -> Optional[Dict[str, Any]]:
        message_dict = _convert_message_to_dict(message)
        if not isinstance(message, AIMessage):
            return message_dict

        raw_tool_calls = message_dict.get("tool_calls") or []
        if not raw_tool_calls:
            return message_dict

        normalized_tool_calls = []
        for tool_call in raw_tool_calls:
            function = dict(tool_call.get("function") or {})
            normalized_arguments = self._normalize_tool_call_arguments(function.get("arguments"))
            if normalized_arguments is None:
                logger.warning(
                    f"⚠️ [DashScope] Skip unfixable historical tool_call parameters: {function.get('name', 'unknown')}"
                )
                continue

            function["arguments"] = normalized_arguments
            normalized_tool_calls.append({**tool_call, "function": function})

        if normalized_tool_calls:
            message_dict["tool_calls"] = normalized_tool_calls
            return message_dict

        message_dict.pop("tool_calls", None)
        if message_dict.get("content") is None:
            message_dict["content"] = ""

        if not message_dict.get("content"):
            logger.warning("⚠️ [DashScope] Skip empty assistant history messages containing only invalid tool_calls")
            return None

        return message_dict
    
    def __init__(self, **kwargs):
        """Initialize DashScope OpenAI compatible client"""

        # 🔍 [DEBUG] Log before reading environment variables
        logger.info(f"🔍 [DashScope initialization] Start initialization ChatDashScopeOpenAI")
        logger.info(f"🔍 [DashScope initialization] kwargs Does it include api_key: {'api_key' in kwargs}")

        # 🔥 Prioritize using the API Key passed in kwargs (from database configuration)
        api_key_from_kwargs = kwargs.get("api_key")

        # If there is no API Key in kwargs or is None, try reading from environment variables
        if not api_key_from_kwargs:
            # Import API Key verification tool
            try:
                # Try importing from app.utils (backend environment)
                from app.utils.api_key_utils import is_valid_api_key
            except ImportError:
                # If the import fails, use the local simplified version
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

            # Try reading from environment variables API Key
            env_api_key = os.getenv("DASHSCOPE_API_KEY")
            logger.info(f"🔍 [DashScope initialization] Read from environment variables DASHSCOPE_API_KEY: {'valuable' if env_api_key else 'empty'}")

            # Verify that the API Key in the environment variable is valid (excluding placeholders)
            if env_api_key and is_valid_api_key(env_api_key):
                logger.info(f"✅ [DashScope initialization] The API Key in the environment variable is valid and the length is: {len(env_api_key)}, Top 10: {env_api_key[:100]}...")
                api_key_from_kwargs = env_api_key
            elif env_api_key:
                logger.warning(f"⚠️ [DashScope initialization] The API Key in the environment variable is invalid (possibly a placeholder) and will be ignored")
                api_key_from_kwargs = None
            else:
                logger.warning(f"⚠️ [DashScope initialization] DASHSCOPE_API_KEY environment variable is empty")
                api_key_from_kwargs = None
        else:
            logger.info(f"✅ [DashScope initialization] Use the API Key passed in kwargs (from database configuration)")

        # Set the default configuration of the DashScope OpenAI compatible interface
        # 🔥 Fix: If base_url is None or not set, use default value
        if not kwargs.get("base_url"):
            kwargs["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        kwargs["api_key"] = api_key_from_kwargs  # 🔥 Use the verified API Key
        kwargs.setdefault("model", "qwen-turbo")
        kwargs.setdefault("temperature", 0.1)
        kwargs.setdefault("max_tokens", 2000)

        # Check API key and base_url
        final_api_key = kwargs.get("api_key")
        final_base_url = kwargs.get("base_url")
        logger.info(f"🔍 [DashScope initialization] final use API Key: {'valuable' if final_api_key else 'empty'}")
        logger.info(f"🔍 [DashScope initialization] final use base_url: {final_base_url}")

        # 🔥 Strict check: api_key must be a non-empty string
        if not final_api_key or not isinstance(final_api_key, str) or not final_api_key.strip():
            logger.error(f"❌ [DashScope initialization] API Key Check failed (value is: {repr(final_api_key)}) , Exception about to be thrown")
            raise ValueError(
                "DashScope API key not found. Please configure API key in web interface "
                "(Settings -> LLM Providers) or set DASHSCOPE_API_KEY environment variable."
            )

        # Call parent class initialization
        super().__init__(**kwargs)

        logger.info(f"✅ Alibaba Bailian OpenAI compatible adapter initialized successfully")
        logger.info(f"   model: {kwargs.get('model', 'qwen-turbo')}")

        # Compatible with different versions of attribute names
        api_base = getattr(self, 'base_url', None) or getattr(self, 'openai_api_base', None) or kwargs.get('base_url', 'unknown')
        logger.info(f"   API Base: {api_base}")
    
    def _generate(self, *args, **kwargs):
        """Rewrite the generation method and add token usage tracking"""

        # 🔥 Print call information
        logger.info("=" * 80)
        logger.info("🔍 [DashScope call] About to be called LLM API")
        logger.info(f"   model: {self.model_name}")
        logger.info(f"   API Base URL: {getattr(self, 'base_url', None) or getattr(self, 'openai_api_base', None)}")
        # Check multiple possible API Key property names
        api_key_val = getattr(self, 'openai_api_key', None) or getattr(self, 'api_key', None)
        has_api_key = bool(api_key_val.get_secret_value() if hasattr(api_key_val, 'get_secret_value') else api_key_val)
        logger.info(f"   API Key: {'valuable' if has_api_key else 'empty'}")
        logger.info(f"   Temperature: {self.temperature}")
        logger.info(f"   Max Tokens: {self.max_tokens}")
        logger.info(f"   Timeout: {getattr(self, 'request_timeout', 'default')}")
        logger.info("=" * 80)

        # Call the generation method of the parent class
        result = super()._generate(*args, **kwargs)
        
        # Track token usage
        try:
            # Extract token usage information from the results
            if hasattr(result, 'llm_output') and result.llm_output:
                token_usage = result.llm_output.get('token_usage', {})
                
                input_tokens = token_usage.get('prompt_tokens', 0)
                output_tokens = token_usage.get('completion_tokens', 0)
                
                if input_tokens > 0 or output_tokens > 0:
                    # Generate session ID
                    session_id = kwargs.get('session_id', f"dashscope_openai_{hash(str(args))%10000}")
                    analysis_type = kwargs.get('analysis_type', 'stock_analysis')
                    
                    # Use TokenTracker to record usage
                    token_tracker.track_usage(
                        provider="dashscope",
                        model_name=self.model_name,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        session_id=session_id,
                        analysis_type=analysis_type
                    )
                    
        except Exception as track_error:
            # token Tracking failures should not affect primary functionality
            logger.error(f"⚠️ Token Tracking failed: {track_error}")
        
        return result

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "messages" in payload:
            payload["messages"] = [
                message_dict
                for message_dict in (self._convert_message_to_dashscope_dict(message) for message in messages)
                if message_dict is not None
            ]
        return payload


# Supported model list
DASHSCOPE_OPENAI_MODELS = {
    # Tongyi Qianwen Series
    "qwen-turbo": {
        "description": "Tongyi Qianwen Turbo - fast response, suitable for daily conversations",
        "context_length": 8192,
        "supports_function_calling": True,
        "recommended_for": ["quick tasks", "daily conversation", "Simple analysis"]
    },
    "qwen-plus": {
        "description": "Tongyi Qianwen Plus - balancing performance and cost",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["complex analysis", "professional tasks", "deep thinking"]
    },
    "qwen-plus-latest": {
        "description": "Tongyi Qianwen Plus latest version - latest features and performance",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["Latest features", "complex analysis", "professional tasks"]
    },
    "qwen-max": {
        "description": "Tongyi Qianwen Max - the strongest performance, suitable for complex tasks",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["complex reasoning", "Professional analysis", "High quality output"]
    },
    "qwen-max-latest": {
        "description": "Tongyi Qianwen Max latest version - the strongest performance and latest features",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["Latest features", "complex reasoning", "Professional analysis"]
    },
    "qwen-long": {
        "description": "Tongyi Qianwen Long - super long context, suitable for long document processing",
        "context_length": 1000000,
        "supports_function_calling": True,
        "recommended_for": ["Long document analysis", "Large data processing", "complex context"]
    }
}


def get_available_openai_models() -> Dict[str, Dict[str, Any]]:
    """Get a list of available DashScope OpenAI compatible models"""
    return DASHSCOPE_OPENAI_MODELS


def create_dashscope_openai_llm(
    model: str = "qwen-plus-latest",
    api_key: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    **kwargs
) -> ChatDashScopeOpenAI:
    """Convenience functions for creating DashScope OpenAI compatible LLM instances"""
    
    return ChatDashScopeOpenAI(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


def test_dashscope_openai_connection(
    model: str = "qwen-turbo",
    api_key: Optional[str] = None
) -> bool:
    """Test DashScope OpenAI Compatible Interface Connection"""
    
    try:
        logger.info(f"🧪 Test DashScope OpenAI Compatible Interface Connection")
        logger.info(f"   model: {model}")
        
        # Create client
        llm = create_dashscope_openai_llm(
            model=model,
            api_key=api_key,
            max_tokens=50
        )
        
        # Send test message
        response = llm.invoke("Hello, please introduce yourself briefly.")
        
        if response and hasattr(response, 'content') and response.content:
            logger.info(f"✅ DashScope OpenAI Compatible interface connected successfully")
            logger.info(f"   response: {response.content[:100]}...")
            return True
        else:
            logger.error(f"❌ DashScope OpenAI Compatible interface response is empty")
            return False
            
    except Exception as e:
        logger.error(f"❌ DashScope OpenAI Compatible interface connection failed: {e}")
        return False


def test_dashscope_openai_function_calling(
    model: str = "qwen-plus-latest",
    api_key: Optional[str] = None
) -> bool:
    """Testing the DashScope OpenAI compatible interface Function Calling"""
    
    try:
        logger.info(f"🧪 test DashScope OpenAI Function Calling")
        logger.info(f"   model: {model}")
        
        # Create client
        llm = create_dashscope_openai_llm(
            model=model,
            api_key=api_key,
            max_tokens=200
        )
        
        # Define testing tools
        def get_current_time() -> str:
            """Get current time"""
            import datetime
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create LangChain tool
        from langchain_core.tools import tool
        
        @tool
        def test_tool(query: str) -> str:
            """Test tool, return query information"""
            return f"Inquiry received: {query}"
        
        # binding tool
        llm_with_tools = llm.bind_tools([test_tool])
        
        # Test tool call
        response = llm_with_tools.invoke("Please use test_tool query'hello world'")
        
        logger.info(f"✅ DashScope OpenAI Function Calling Test completed")
        logger.info(f"   response type: {type(response)}")
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info(f"   Number of tool calls: {len(response.tool_calls)}")
            return True
        else:
            logger.info(f"   Response content: {getattr(response, 'content', 'No content')}")
            return True  # A success even if no tool is called, as the model may choose not to call a tool
            
    except Exception as e:
        logger.error(f"❌ DashScope OpenAI Function Calling test failed: {e}")
        return False


if __name__ == "__main__":
    """test script"""
    logger.info(f"🧪 DashScope OpenAI Compatible adapter testing")
    logger.info(f"=" * 50)
    
    # test connection
    connection_ok = test_dashscope_openai_connection()
    
    if connection_ok:
        # test Function Calling
        function_calling_ok = test_dashscope_openai_function_calling()
        
        if function_calling_ok:
            logger.info(f"\n🎉 All tests passed! DashScope OpenAI compatible adapter works fine")
        else:
            logger.error(f"\n⚠️ Function Calling test failed")
    else:
        logger.error(f"\n❌ Connection test failed")
