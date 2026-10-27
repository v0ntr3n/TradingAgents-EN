"""
DeepSeek LLM Adapter, supports Token usage statistics
"""

import os
import time
from typing import Any, Dict, List, Optional, Union
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import _convert_message_to_dict
from langchain_core.callbacks import CallbackManagerForLLMRun

# Import unified log system
from tradingagents.utils.logging_init import setup_llm_logging

# Import log module
from tradingagents.utils.logging_manager import get_logger, get_logger_manager
logger = get_logger('agents')
logger = setup_llm_logging()

# Import token tracker
try:
    from tradingagents.config.config_manager import token_tracker
    TOKEN_TRACKING_ENABLED = True
    logger.info("✅ Token Tracking is enabled")
except ImportError:
    TOKEN_TRACKING_ENABLED = False
    logger.warning("⚠️ Token Tracking is not enabled")


class ChatDeepSeek(ChatOpenAI):
    """
    DeepSeek Chat model adapter, supports Token usage statistics
    
    Inherited from ChatOpenAI, adding Token usage statistics function
    """

    @staticmethod
    def _supports_thinking_mode(model: str) -> bool:
        normalized = str(model or "").strip().lower()
        return (
            normalized.startswith("deepseek-v4")
            or "reasoner" in normalized
            or normalized.startswith("deepseek-r1")
        )

    @staticmethod
    def _build_thinking_kwargs(model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        updated_kwargs = dict(kwargs)
        thinking = updated_kwargs.pop("thinking", None)
        extra_body = dict(updated_kwargs.get("extra_body") or {})

        if thinking is not None:
            extra_body["thinking"] = thinking

        if ChatDeepSeek._supports_thinking_mode(model):
            extra_body.setdefault("thinking", {"type": "enabled"})
            updated_kwargs.setdefault("reasoning_effort", "high")

        if extra_body:
            updated_kwargs["extra_body"] = extra_body

        return updated_kwargs
    
    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize DeepSeek adapter
        
        Args:
            model: Model name, default is deepseek-chat
            api_key: API Key, if not provided it is obtained from the environment variable DEEPSEEK_API_KEY
            base_url: API Basics URL
            temperature: Temperature parameter
            max_tokens: Maximum number of tokens
            **kwargs: Other parameters
        """
        
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

            # Read from environment variables API Key
            env_api_key = os.getenv("DEEPSEEK_API_KEY")

            # Verify that the API Key in the environment variable is valid (excluding placeholders)
            if env_api_key and is_valid_api_key(env_api_key):
                api_key = env_api_key
                logger.info("✅ [DeepSeek initialization] Valid using environment variables API Key")
            elif env_api_key:
                logger.warning("⚠️ [DeepSeek initialization] The API Key in the environment variable is invalid (possibly a placeholder) and will be ignored")
                api_key = None
            else:
                api_key = None

            if not api_key:
                raise ValueError(
                    "DeepSeek API Key not found. Please configure in the web interface API Key "
                    "(settings -> Large model manufacturer) Or set the DEEPSEEK_API_KEY environment variable."
                )

        kwargs = self._build_thinking_kwargs(model, kwargs)
        thinking_config = (kwargs.get("extra_body") or {}).get("thinking")
        reasoning_effort = kwargs.get("reasoning_effort")
        if thinking_config:
            logger.info(
                f"✅ [DeepSeek initialization] thinking={thinking_config}, reasoning_effort={reasoning_effort or 'default'}"
            )
        
        # Initialize parent class
        super().__init__(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        self.model_name = model

    @staticmethod
    def _extract_reasoning_content_from_message(message: BaseMessage) -> Optional[str]:
        if not isinstance(message, AIMessage):
            return None

        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        reasoning_content = additional_kwargs.get("reasoning_content")
        if reasoning_content:
            return str(reasoning_content)

        response_metadata = getattr(message, "response_metadata", {}) or {}
        if isinstance(response_metadata, dict):
            reasoning_content = response_metadata.get("reasoning_content")
            if reasoning_content:
                return str(reasoning_content)

        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") not in {"thinking", "reasoning", "reasoning_content"}:
                    continue
                reasoning_text = block.get("text") or block.get("content") or block.get("reasoning_content")
                if reasoning_text:
                    return str(reasoning_text)

        return None

    def _convert_message_to_deepseek_dict(self, message: BaseMessage) -> Dict[str, Any]:
        message_dict = _convert_message_to_dict(message)
        reasoning_content = self._extract_reasoning_content_from_message(message)
        if reasoning_content and message_dict.get("role") == "assistant":
            message_dict["reasoning_content"] = reasoning_content
        return message_dict

    @staticmethod
    def _extract_tool_call_ids(message: BaseMessage) -> List[str]:
        if not isinstance(message, AIMessage):
            return []

        tool_calls = getattr(message, "tool_calls", None) or []
        tool_call_ids: List[str] = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = str(tool_call.get("id") or "").strip()
            if tool_call_id:
                tool_call_ids.append(tool_call_id)
        return tool_call_ids

    def _sanitize_messages_for_deepseek(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Remove illegal tool_call history under DeepSeek s strict verification."""
        sanitized: List[BaseMessage] = []
        index = 0

        while index < len(messages):
            message = messages[index]

            if isinstance(message, AIMessage):
                tool_call_ids = self._extract_tool_call_ids(message)
                if tool_call_ids:
                    contiguous_tool_messages: List[ToolMessage] = []
                    matched_tool_ids: List[str] = []
                    next_index = index + 1

                    while next_index < len(messages) and isinstance(messages[next_index], ToolMessage):
                        tool_message = messages[next_index]
                        tool_call_id = str(getattr(tool_message, "tool_call_id", "") or "").strip()
                        if tool_call_id and tool_call_id in tool_call_ids and tool_call_id not in matched_tool_ids:
                            contiguous_tool_messages.append(tool_message)
                            matched_tool_ids.append(tool_call_id)
                        else:
                            logger.warning(
                                "⚠️ [DeepSeek] Discard orphaned or unmatched ToolMessage: tool_call_id=%s",
                                tool_call_id or "<empty>",
                            )
                        next_index += 1

                    missing_tool_ids = [tool_call_id for tool_call_id in tool_call_ids if tool_call_id not in matched_tool_ids]
                    if missing_tool_ids:
                        logger.warning(
                            "⚠️ [DeepSeek] Unclosed assistant tool_calls detected, message fragment discarded: missing_tool_call_ids=%s",
                            missing_tool_ids,
                        )
                        index = next_index
                        continue

                    sanitized.append(message)
                    sanitized.extend(contiguous_tool_messages)
                    index = next_index
                    continue

            if isinstance(message, ToolMessage):
                logger.warning(
                    "⚠️ [DeepSeek] ToolMessage without preceding assistant tool_calls detected and discarded: tool_call_id=%s",
                    str(getattr(message, "tool_call_id", "") or "<empty>"),
                )
                index += 1
                continue

            sanitized.append(message)
            index += 1

        return sanitized

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        messages = self._convert_input(input_).to_messages()
        messages = self._sanitize_messages_for_deepseek(messages)
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "messages" in payload:
            payload["messages"] = [self._convert_message_to_deepseek_dict(message) for message in messages]
        return payload

    def _create_chat_result(
        self,
        response: Any,
        generation_info: Optional[Dict[str, Any]] = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        response_dict = response if isinstance(response, dict) else response.model_dump()
        choices = response_dict.get("choices") or []

        for generation, choice in zip(result.generations, choices):
            if not isinstance(generation.message, AIMessage):
                continue
            message_payload = choice.get("message") or {}
            reasoning_content = message_payload.get("reasoning_content")
            if reasoning_content:
                generation.message.additional_kwargs["reasoning_content"] = reasoning_content

        return result
        
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

        # Extract and remove custom parameters to avoid passing them to the parent class
        session_id = kwargs.pop('session_id', None)
        analysis_type = kwargs.pop('analysis_type', None)

        try:
            # Call parent class method to generate response
            result = super()._generate(messages, stop, run_manager, **kwargs)
            
            # Extract token usage
            input_tokens = 0
            output_tokens = 0
            
            # Try to extract the token usage from the response
            if hasattr(result, 'llm_output') and result.llm_output:
                token_usage = result.llm_output.get('token_usage', {})
                if token_usage:
                    input_tokens = token_usage.get('prompt_tokens', 0)
                    output_tokens = token_usage.get('completion_tokens', 0)
            
            # If the token usage is not obtained, estimate it
            if input_tokens == 0 and output_tokens == 0:
                input_tokens = self._estimate_input_tokens(messages)
                output_tokens = self._estimate_output_tokens(result)
                logger.debug(f"🔍 [DeepSeek] Use estimates token: input={input_tokens}, output={output_tokens}")
            else:
                logger.info(f"📊 [DeepSeek] Actual token usage: input={input_tokens}, output={output_tokens}")
            
            # Record token usage
            if TOKEN_TRACKING_ENABLED and (input_tokens > 0 or output_tokens > 0):
                try:
                    # Use extracted parameters or generate default values
                    if session_id is None:
                        session_id = f"deepseek_{hash(str(messages))%10000}"
                    if analysis_type is None:
                        analysis_type = 'stock_analysis'

                    # Record usage
                    usage_record = token_tracker.track_usage(
                        provider="deepseek",
                        model_name=self.model_name,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        session_id=session_id,
                        analysis_type=analysis_type
                    )

                    if usage_record:
                        if usage_record.cost == 0.0:
                            logger.warning(f"⚠️ [DeepSeek] The cost calculation is 0, there may be a configuration problem")
                        else:
                            logger.info(f"💰 [DeepSeek] Cost of this call: ¥{usage_record.cost:.6f}")

                        # Token recording method using unified log manager
                        logger_manager = get_logger_manager()
                        logger_manager.log_token_usage(
                            logger, "deepseek", self.model_name,
                            input_tokens, output_tokens, usage_record.cost,
                            session_id
                        )
                    else:
                        logger.warning(f"⚠️ [DeepSeek] No usage record created")

                except Exception as track_error:
                    logger.error(f"⚠️ [DeepSeek] Token Statistics failed: {track_error}", exc_info=True)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [DeepSeek] call failed: {e}", exc_info=True)
            raise
    
    def _estimate_input_tokens(self, messages: List[BaseMessage]) -> int:
        """
        Estimate the number of input tokens
        
        Args:
            messages: Enter message list
            
        Returns:
            Estimated number of input tokens
        """
        total_chars = 0
        for message in messages:
            if hasattr(message, 'content'):
                total_chars += len(str(message.content))
        
        # Rough estimate: Chinese about 1.5 characters/token, English about 4 characters/token
        # Using a conservative estimate here: 2 characters/token
        estimated_tokens = max(1, total_chars // 2)
        return estimated_tokens
    
    def _estimate_output_tokens(self, result: ChatResult) -> int:
        """
        Estimate the number of output tokens
        
        Args:
            result: Chat results
            
        Returns:
            Estimated number of output tokens
        """
        total_chars = 0
        for generation in result.generations:
            if hasattr(generation, 'message') and hasattr(generation.message, 'content'):
                total_chars += len(str(generation.message.content))
        
        # Rough estimate: 2 characters/token
        estimated_tokens = max(1, total_chars // 2)
        return estimated_tokens
    
    def invoke(
        self,
        input: Union[str, List[BaseMessage]],
        config: Optional[Dict] = None,
        **kwargs: Any,
    ) -> AIMessage:
        """
        Call the model to generate a response
        
        Args:
            input: Enter message
            config: Configuration parameters
            **kwargs: Other parameters (including session_id and analysis_type)
            
        Returns:
            AI message response
        """
        
        # Process input
        if isinstance(input, str):
            messages = [HumanMessage(content=input)]
        else:
            messages = input
        
        # Call the generate method
        result = self._generate(messages, **kwargs)
        
        # Returns the first message that produces a result
        if result.generations:
            return result.generations[0].message
        else:
            return AIMessage(content="")


def create_deepseek_llm(
    model: str = "deepseek-chat",
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    **kwargs
) -> ChatDeepSeek:
    """
    Convenience functions for creating DeepSeek LLM instances
    
    Args:
        model: Model name
        temperature: Temperature parameter
        max_tokens: Maximum number of tokens
        **kwargs: Other parameters
        
    Returns:
        ChatDeepSeek Example
    """
    return ChatDeepSeek(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )


# For backward compatibility, aliases are provided
DeepSeekLLM = ChatDeepSeek
