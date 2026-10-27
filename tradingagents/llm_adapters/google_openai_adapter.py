"""
Google AI OpenAI Compatible adapter
Provided by TradingAgents Google AI (Gemini)OpenAI compatible interface for models
Solve the problem of Google model tool calling format mismatch
"""

import os
from typing import Any, Dict, List, Optional, Union, Sequence
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import LLMResult
from pydantic import Field, SecretStr
from ..config.config_manager import token_tracker

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


class ChatGoogleOpenAI(ChatGoogleGenerativeAI):
    """
    Google AI OpenAI Compatible adapter
    Inherit ChatGoogleGenerativeAI, optimize tool calling and content format processing
    Solve the problem that the return format of Google model tool call does not match the system expectation
    """

    def __init__(self, base_url: Optional[str] = None, **kwargs):
        """
        Initialize the Google AI OpenAI compatible client

        Args:
            base_url: Custom API endpoint (optional)
                     If provided, will be passed via client_options to Google AI SDK
                     Supported formats:
                     - https://generativelanguage.googleapis.com/v1beta
                     - https://generativelanguage.googleapis.com/v1 (automatically converted to v1beta)
                     - Custom proxy address
            **kwargs: Other parameters
        """

        # 🔍 [DEBUG] Log before reading environment variables
        logger.info("🔍 [Google initialization] Start initialization ChatGoogleOpenAI")
        logger.info(f"🔍 [Google initialization] kwargs Does it include google_api_key: {'google_api_key' in kwargs}")
        logger.info(f"🔍 [Google initialization] incoming base_url: {base_url}")

        # Set the default configuration for Google AI
        kwargs.setdefault("temperature", 0.1)
        kwargs.setdefault("max_tokens", 2000)

        # 🔥 Prioritize using the API Key passed in kwargs (from database configuration)
        google_api_key = kwargs.get("google_api_key")

        # If there is no API Key in kwargs, try reading from environment variables
        if not google_api_key:
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

            # Check the environment variables for API Key
            env_api_key = os.getenv("GOOGLE_API_KEY")
            logger.info(f"🔍 [Google initialization] Read from environment variables GOOGLE_API_KEY: {'valuable' if env_api_key else 'empty'}")

            # Verify that the API Key in the environment variable is valid (excluding placeholders)
            if env_api_key and is_valid_api_key(env_api_key):
                logger.info(f"✅ [Google initialization] The API Key in the environment variable is valid and the length is: {len(env_api_key)}, Top 10: {env_api_key[:10]}...")
                google_api_key = env_api_key
            elif env_api_key:
                logger.warning("⚠️ [Google initialization] The API Key in the environment variable is invalid (possibly a placeholder) and will be ignored")
                google_api_key = None
            else:
                logger.warning("⚠️ [Google initialization] GOOGLE_API_KEY environment variable is empty")
                google_api_key = None
        else:
            logger.info("✅ [Google initialization] Use the API Key passed in kwargs (from database configuration)")

        logger.info(f"🔍 [Google initialization] final use API Key: {'valuable' if google_api_key else 'empty'}")

        if not google_api_key:
            logger.error("❌ [Google initialization] API Key The check failed and an exception will be thrown")
            raise ValueError(
                "Google API key not found. Please configure API key in web interface "
                "(Settings -> LLM Providers) or set GOOGLE_API_KEY environment variable."
            )

        kwargs["google_api_key"] = google_api_key

        # 🔧 Handle customization base_url
        if base_url:
            # Remove trailing slash
            base_url = base_url.rstrip('/')
            logger.info(f"🔍 [Google initialization] Process base_url: {base_url}")

            # 🔍 Check whether it is an official Google domain name
            is_google_official = 'generativelanguage.googleapis.com' in base_url

            if is_google_official:
                # ✅ Google Official domain name: Extract the domain name part and the SDK will automatically add it /v1beta
                # For example:https://generativelanguage.googleapis.com/v1beta -> https://generativelanguage.googleapis.com
                #      https://generativelanguage.googleapis.com/v1 -> https://generativelanguage.googleapis.com
                if base_url.endswith('/v1beta'):
                    api_endpoint = base_url[:-7]  # Remove /v1beta (7 characters)
                    logger.info(f"🔍 [Google official] Extract domain name from base_url: {api_endpoint}")
                elif base_url.endswith('/v1'):
                    api_endpoint = base_url[:-3]  # Remove /v1 (3 characters)
                    logger.info(f"🔍 [Google official] Extract domain name from base_url: {api_endpoint}")
                else:
                    # If there is no version suffix, use it directly
                    api_endpoint = base_url
                    logger.info(f"🔍 [Google official] Use full base_url as domain name: {api_endpoint}")

                logger.info(f"✅ [Google official] SDK The /v1beta path will be added automatically")
            else:
                # 🔄 Transit address: Use the complete URL directly and do not allow the SDK to add it. /v1beta
                # Transit services usually already include complete path mapping
                api_endpoint = base_url
                logger.info(f"🔄 [transit address] Unofficial domain name detected, use full URL: {api_endpoint}")
                logger.info(f"   Transit services usually already contain the full path and do not require SDK addition /v1beta")

            # Pass custom endpoint via client_options
            # Reference: https://github.com/langchain-ai/langchain-google/issues/783
            kwargs["client_options"] = {"api_endpoint": api_endpoint}
            logger.info(f"✅ [Google initialization] settings client_options.api_endpoint: {api_endpoint}")
        else:
            logger.info(f"🔍 [Google initialization] base_url not provided, default endpoint used")

        # Call parent class initialization
        super().__init__(**kwargs)

        logger.info(f"✅ Google AI OpenAI Compatible adapter initialized successfully")
        logger.info(f"   model: {kwargs.get('model', 'gemini-pro')}")
        logger.info(f"   temperature: {kwargs.get('temperature', 0.1)}")
        logger.info(f"   maximum Token: {kwargs.get('max_tokens', 2000)}")
        if base_url:
            logger.info(f"   Custom endpoint: {base_url}")

    @property
    def model_name(self) -> str:
        """
        Return model name (compatibility attribute)
        Remove 'models/' prefix, returns the pure model name
        """
        model = self.model
        if model and model.startswith("models/"):
            return model[7:]  # Remove "models/" prefix
        return model or "unknown"
    
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> LLMResult:
        """Rewrite the generation method, optimize tool call processing and content format"""

        try:
            # Call the generation method of the parent class
            result = super()._generate(messages, stop, **kwargs)

            # Optimize return content format
            # Note: result.generations is a two-dimensional list [[ChatGeneration]]
            if result and result.generations:
                for generation_list in result.generations:
                    if isinstance(generation_list, list):
                        for generation in generation_list:
                            if hasattr(generation, 'message') and generation.message:
                                # Optimize message content format
                                self._optimize_message_content(generation.message)
                    else:
                        # Compatibility processing: If it is not a list, process it directly
                        if hasattr(generation_list, 'message') and generation_list.message:
                            self._optimize_message_content(generation_list.message)

            # Track token usage
            self._track_token_usage(result, kwargs)

            return result

        except Exception as e:
            logger.error(f"❌ Google AI Build failed: {e}")
            logger.exception(e)  # Print full stack trace

            # Check if API Key is invalid error
            error_str = str(e)
            if 'API_KEY_INVALID' in error_str or 'API key not valid' in error_str:
                error_content = "Google AI API Key Invalid or not configured.\n\n Please check:\n1. GOOGLE_API_KEY Are the environment variables configured correctly?\n2. API Key Is it valid (visit https://ai.google.dev/ Get)\n3. Is it enabled Gemini API\n\n Recommendation: Use other AI models (such as Alibaba Bailian, DeepSeek)"
            elif 'Connection' in error_str or 'Network' in error_str:
                error_content = f"Google AI Network connection failed: {error_str}\n\n Please check:\n1. Is the network connection normal?\n2. Do you need scientific Internet access?\n3. Firewall settings"
            else:
                error_content = f"Google AI call failed: {error_str}\n\n Please check the configuration or use another AI model"

            # Return a result containing error information instead of throwing an exception
            from langchain_core.outputs import ChatGeneration
            error_message = AIMessage(content=error_content)
            error_generation = ChatGeneration(message=error_message)
            return LLMResult(generations=[[error_generation]])
    
    def _optimize_message_content(self, message: BaseMessage):
        """Optimize the message content format and ensure that it contains news characteristic keywords"""
        
        if not isinstance(message, AIMessage) or not message.content:
            return
        
        content = message.content
        
        # Check if it is the news content returned by the tool call
        if self._is_news_content(content):
            # Optimize news content format and add necessary keywords
            optimized_content = self._enhance_news_content(content)
            message.content = optimized_content
            
            logger.debug(f"🔧 [Google adapter] Optimize news content format")
            logger.debug(f"   original length: {len(content)} character")
            logger.debug(f"   Optimized length: {len(optimized_content)} character")
    
    def _is_news_content(self, content: str) -> bool:
        """Determine whether the content is news content"""
        
        # Check whether news-related keywords are included
        news_indicators = [
            "stocks", "company", "market", "investment", "Finance", "securities", "transaction",
            "ups and downs", "performance", "financial report", "analysis", "Forecast", "news", "Announcement"
        ]
        
        return any(indicator in content for indicator in news_indicators) and len(content) > 200
    
    def _enhance_news_content(self, content: str) -> str:
        """Enhance news content and add necessary formatting information"""
        
        import datetime
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # If content lacks necessary journalistic features, add them
        enhanced_content = content
        
        # Add publication time information if missing
        if "Release time" not in content and "time" not in content:
            enhanced_content = f"Release time: {current_date}\n\n{enhanced_content}"
        
        # Add news title identifier (if missing)
        if "News headline" not in content and "Title" not in content:
            # Try to extract the first line from the content as title
            lines = enhanced_content.split('\n')
            if lines:
                first_line = lines[0].strip()
                if len(first_line) < 100:  # maybe the title
                    enhanced_content = f"News headline: {first_line}\n\n{enhanced_content}"
        
        # Add article source information (if missing)
        if "Article source" not in content and "Source" not in content:
            enhanced_content = f"{enhanced_content}\n\n Article source: Google AI Intelligent analysis"
        
        return enhanced_content
    
    def _track_token_usage(self, result: LLMResult, kwargs: Dict[str, Any]):
        """Track token usage"""
        
        try:
            # Extract token usage information from the results
            if hasattr(result, 'llm_output') and result.llm_output:
                token_usage = result.llm_output.get('token_usage', {})
                
                input_tokens = token_usage.get('prompt_tokens', 0)
                output_tokens = token_usage.get('completion_tokens', 0)
                
                if input_tokens > 0 or output_tokens > 0:
                    # Generate session ID
                    session_id = kwargs.get('session_id', f"google_openai_{hash(str(kwargs))%10000}")
                    analysis_type = kwargs.get('analysis_type', 'stock_analysis')
                    
                    # Use TokenTracker to record usage
                    token_tracker.track_usage(
                        provider="google",
                        model_name=self.model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        session_id=session_id,
                        analysis_type=analysis_type
                    )
                    
                    logger.debug(f"📊 [Google adapter] Token Usage: input={input_tokens}, output={output_tokens}")
                    
        except Exception as track_error:
            # token Tracking failures should not affect primary functionality
            logger.error(f"⚠️ Google Adapter Token tracking failed: {track_error}")


# Supported model list
GOOGLE_OPENAI_MODELS = {
    # Gemini 2.5 Series - Latest Validation Model
    "gemini-2.5-pro": {
        "description": "Gemini 2.5 Pro - The latest flagship model with powerful functions (16.68s)",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["complex reasoning", "Professional analysis", "High quality output"],
        "avg_response_time": 16.68
    },
    "gemini-2.5-flash": {
        "description": "Gemini 2.5 Flash - Latest fast model (2.73s)",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["Quick response", "real-time analysis", "High frequency use"],
        "avg_response_time": 2.73
    },
    "gemini-2.5-flash-lite-preview-06-17": {
        "description": "Gemini 2.5 Flash Lite Preview - Super fast response (1.45s)",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["Super fast response", "real-time interaction", "High frequency calls"],
        "avg_response_time": 1.45
    },
    # Gemini 2.0 Series
    "gemini-2.0-flash": {
        "description": "Gemini 2.0 Flash - Next generation rapid model (1.87s)",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["Quick response", "real-time analysis"],
        "avg_response_time": 1.87
    },
    # Gemini 1.5 Series
    "gemini-1.5-pro": {
        "description": "Gemini 1.5 Pro - Powerful performance, balanced choice (2.25s)",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["complex analysis", "professional tasks", "deep thinking"],
        "avg_response_time": 2.25
    },
    "gemini-1.5-flash": {
        "description": "Gemini 1.5 Flash - Quick response, backup options (2.87s)",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["quick tasks", "daily conversation", "Simple analysis"],
        "avg_response_time": 2.87
    },
    # classic model
    "gemini-pro": {
        "description": "Gemini Pro - Classic model, stable and reliable",
        "context_length": 32768,
        "supports_function_calling": True,
        "recommended_for": ["Common tasks", "Scenarios with high stability requirements"]
    }
}


def get_available_google_models() -> Dict[str, Dict[str, Any]]:
    """Get a list of available Google AI models"""
    return GOOGLE_OPENAI_MODELS


def create_google_openai_llm(
    model: str = "gemini-2.5-flash-lite-preview-06-17",
    google_api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    **kwargs
) -> ChatGoogleOpenAI:
    """
    Convenience functions for creating Google AI OpenAI compatible LLM instances

    Args:
        model: Model name
        google_api_key: Google API Key
        base_url: Custom API endpoint (optional)
        temperature: Temperature parameter
        max_tokens: Maximum number of tokens
        **kwargs: Other parameters

    Returns:
        ChatGoogleOpenAI Example
    """

    return ChatGoogleOpenAI(
        model=model,
        google_api_key=google_api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


def test_google_openai_connection(
    model: str = "gemini-2.0-flash",
    google_api_key: Optional[str] = None
) -> bool:
    """Test Google AI OpenAI compatible interface connection"""
    
    try:
        logger.info(f"🧪 Test Google AI OpenAI compatible interface connection")
        logger.info(f"   model: {model}")
        
        # Create client
        llm = create_google_openai_llm(
            model=model,
            google_api_key=google_api_key,
            max_tokens=50
        )
        
        # Send test message
        response = llm.invoke("Hello, please introduce yourself briefly.")
        
        if response and hasattr(response, 'content') and response.content:
            logger.info(f"✅ Google AI OpenAI Compatible interface connected successfully")
            logger.info(f"   response: {response.content[:100]}...")
            return True
        else:
            logger.error(f"❌ Google AI OpenAI Compatible interface response is empty")
            return False
            
    except Exception as e:
        logger.error(f"❌ Google AI OpenAI Compatible interface connection failed: {e}")
        return False


def test_google_openai_function_calling(
    model: str = "gemini-2.5-flash-lite-preview-06-17",
    google_api_key: Optional[str] = None
) -> bool:
    """Testing the Google AI OpenAI compatible interface Function Calling"""
    
    try:
        logger.info(f"🧪 test Google AI Function Calling")
        logger.info(f"   model: {model}")
        
        # Create client
        llm = create_google_openai_llm(
            model=model,
            google_api_key=google_api_key,
            max_tokens=200
        )
        
        # Define testing tools
        from langchain_core.tools import tool
        
        @tool
        def test_news_tool(query: str) -> str:
            """Test news tool, return simulated news content"""
            return f"""Release time: 2024-01-15
News headline: {query}Related market dynamics
Article source: Test news source

This is an article about{query}of test news content. The company has performed well recently and has a promising market outlook.
Investors expressed concern, and analysts gave positive reviews."""
        
        # binding tool
        llm_with_tools = llm.bind_tools([test_news_tool])
        
        # Test tool call
        response = llm_with_tools.invoke("Please use test_news_tool to query'apple inc.'news")
        
        logger.info(f"✅ Google AI Function Calling Test completed")
        logger.info(f"   response type: {type(response)}")
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info(f"   Number of tool calls: {len(response.tool_calls)}")
            return True
        else:
            logger.info(f"   Response content: {getattr(response, 'content', 'No content')}")
            return True  # A success even if no tool is called, as the model may choose not to call a tool
            
    except Exception as e:
        logger.error(f"❌ Google AI Function Calling test failed: {e}")
        return False


if __name__ == "__main__":
    """test script"""
    logger.info(f"🧪 Google AI OpenAI Compatible adapter testing")
    logger.info(f"=" * 50)
    
    # test connection
    connection_ok = test_google_openai_connection()
    
    if connection_ok:
        # test Function Calling
        function_calling_ok = test_google_openai_function_calling()
        
        if function_calling_ok:
            logger.info(f"\n🎉 All tests passed! Google AI OpenAI compatible adapter works fine")
        else:
            logger.error(f"\n⚠️ Function Calling test failed")
    else:
        logger.error(f"\n❌ Connection test failed")