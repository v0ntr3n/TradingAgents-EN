"""
OpenAI Compatible with API adapters

Supports all providers compatible with the OpenAI API format:
- OpenAI
- DeepSeek
- Tongyi Qianwen (DashScope)
- Wisdom spectrum AI
- silicon based flow
- Ollama
- OpenRouter
"""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from openai import AsyncOpenAI, OpenAI

from ..models import (
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
)
from .base import BaseAdapter

logger = logging.getLogger(__name__)


class OpenAICompatAdapter(BaseAdapter):
    """OpenAI Compatible with API adapters"""
    
    # List of supported providers
    SUPPORTED_PROVIDERS = [
        LLMProvider.OPENAI,
        LLMProvider.DEEPSEEK,
        LLMProvider.DASHSCOPE,
        LLMProvider.ZHIPU,
        LLMProvider.SILICONFLOW,
        LLMProvider.OLLAMA,
        LLMProvider.OPENROUTER,
    ]
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
    
    def initialize(self) -> None:
        """Initialize the OpenAI client"""
        # 🔥 Check if API key exists
        api_key = self.config.api_key
        
        # 🔥 Local model (Ollama) does not require API Key, use placeholder
        if not api_key and self.config.provider == LLMProvider.OLLAMA:
            api_key = "ollama"  # The local model uses placeholders and is not actually verified.
        
        if not api_key:
            # Determine the environment variable name that should be used based on provider
            provider_env_map = {
                LLMProvider.OPENAI: "OPENAI_API_KEY",
                LLMProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
                LLMProvider.DASHSCOPE: "DASHSCOPE_API_KEY",
                LLMProvider.ZHIPU: "ZHIPU_API_KEY",
                LLMProvider.SILICONFLOW: "SILICONFLOW_API_KEY",
                LLMProvider.OLLAMA: "OLLAMA_API_KEY",
                LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
            }
            # Compatible use_enum_values=True: config.provider may be a string
            provider_val = self.config.provider
            provider_key = provider_val.value if hasattr(provider_val, "value") else provider_val
            expected_env_key = provider_env_map.get(provider_key, "API_KEY")
            raise ValueError(
                f"The api_key client option must be set either by passing api_key to the client "
                f"or by setting the {expected_env_key} environment variable. "
                f"Provider: {provider_key}, Model: {self.config.model}"
            )
        
        client_kwargs = {
            "api_key": api_key,
            "timeout": self.config.timeout,
            # Turn off SDK's built-in retry: Retry is uniformly controlled by the application layer retry_sync/retry_async.
            # Otherwise SDK(Default 2 times) x Application layer(3 times) Double layer superposition, the worst-case scenario can be reached in a single call
            # Wait for more than ten minutes, and the timeout semantics become unpredictable.
            "max_retries": 0,
        }
        
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url
        
        self._sync_client = OpenAI(**client_kwargs)
        self._async_client = AsyncOpenAI(**client_kwargs)
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert message format to OpenAI format"""
        result = []
        for msg in messages:
            converted = {"role": msg.role, "content": msg.content or ""}

            # Reasoning models (such as Qwen thinking / DeepSeek reasoning) in tool rounds
            # The reasoning_content of the previous round of assistant needs to be returned, otherwise the provider will reject the request.
            if getattr(msg, 'reasoning_content', None):
                converted["reasoning_content"] = msg.reasoning_content
            
            if msg.name:
                converted["name"] = msg.name
            
            if msg.tool_calls:
                converted["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in msg.tool_calls
                ]
            
            if msg.tool_call_id:
                converted["tool_call_id"] = msg.tool_call_id
            
            result.append(converted)
        
        return result
    
    def _build_request_kwargs(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Build request parameters

        Supports overriding parameters such as temperature / max_tokens through kwargs,
        Priority:kwargs > self.config. 
        """
        request_kwargs = {
            "model": self.config.model,
            "messages": self._convert_messages(messages),
            "temperature": kwargs.pop("temperature", self.config.temperature),
        }

        # max_tokens: kwargs first, second config
        max_tokens = kwargs.pop("max_tokens", None) or self.config.max_tokens
        if max_tokens:
            request_kwargs["max_tokens"] = max_tokens

        # response_format: Support json_object / json_schema, etc. (OpenAI compatible protocol)
        response_format = kwargs.pop("response_format", self.config.response_format if hasattr(self.config, "response_format") else None)
        if response_format:
            request_kwargs["response_format"] = response_format

        # The remaining kwargs are transparently transmitted (such as top_p, seed, etc.)
        request_kwargs.update(kwargs)

        if tools:
            request_kwargs["tools"] = self.convert_tools_to_provider_format(tools)
            if self.config.tool_choice:
                request_kwargs["tool_choice"] = self.config.tool_choice

        return request_kwargs
    
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """synchronous chat"""
        if not self._sync_client:
            self.initialize()
        
        request_kwargs = self._build_request_kwargs(messages, tools, **kwargs)
        response = self._sync_client.chat.completions.create(**request_kwargs)
        
        return self._parse_response(response)
    
    async def achat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """Asynchronous chat"""
        if not self._async_client:
            self.initialize()
        
        request_kwargs = self._build_request_kwargs(messages, tools, **kwargs)
        response = await self._async_client.chat.completions.create(**request_kwargs)
        
        return self._parse_response(response)
    
    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Asynchronous streaming output"""
        if not self._async_client:
            self.initialize()
        
        request_kwargs = self._build_request_kwargs(messages, tools, **kwargs)
        request_kwargs["stream"] = True
        
        async for chunk in await self._async_client.chat.completions.create(**request_kwargs):
            # Safe access to delta: reasoning_content may be output first and then output when the reasoning model is streaming content
            if chunk.choices:
                delta = getattr(chunk.choices[0], 'delta', None)
                if delta and getattr(delta, 'content', None):
                    yield delta.content
    
    def chat_stream_deltas(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        """Synchronous streaming calls produce incremental dictionaries piece by piece.

        Each increment is of the form {"type": "reasoning"|"content", "text": str}: 
        - reasoning: reasoning_content delta for thinking models (like DeepSeek R1)
        - content: Text increment

        Only applicable to single-round scenarios without tool invocation (such as Skill code generation).
        The caller is responsible for splicing content to get a complete response.
        """
        if not self._sync_client:
            self.initialize()

        request_kwargs = self._build_request_kwargs(messages, tools, **kwargs)
        request_kwargs["stream"] = True

        stream = self._sync_client.chat.completions.create(**request_kwargs)
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = getattr(chunk.choices[0], "delta", None)
            if not delta:
                continue
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield {"type": "reasoning", "text": reasoning}
            if getattr(delta, "content", None):
                yield {"type": "content", "text": delta.content}

    def _parse_response(self, response) -> LLMResponse:
        """Parse response"""
        # 🔥 Check if the choices field exists and is not empty
        if not hasattr(response, 'choices') or response.choices is None:
            error_msg = f"LLM API The choices field in the returned response is null. response type: {type(response).__name__}"
            if hasattr(response, 'model'):
                error_msg += f", model: {response.model}"
            if hasattr(response, 'id'):
                error_msg += f", response ID: {response.id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if not response.choices or len(response.choices) == 0:
            error_msg = f"LLM API The choices field in the returned response is an empty list. response type: {type(response).__name__}"
            if hasattr(response, 'model'):
                error_msg += f", model: {response.model}"
            if hasattr(response, 'id'):
                error_msg += f", response ID: {response.id}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        choice = response.choices[0]
        
        # 🔥 Check if choice has message attribute
        if not hasattr(choice, 'message') or choice.message is None:
            error_msg = f"LLM API The message field in the returned choice is null. response type: {type(response).__name__}"
            if hasattr(response, 'model'):
                error_msg += f", model: {response.model}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        message = choice.message

        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                # 🔥 Fix: Handling tool_call objects of different types
                if isinstance(tc, dict):
                    # It is already a dictionary, use it directly
                    tool_calls.append(ToolCall.from_openai_format(tc))
                elif isinstance(tc, str):
                    # String type, skipped (should not appear, but does fault tolerance)
                    continue
                elif hasattr(tc, 'model_dump'):
                    # Pydantic model, call model_dump()
                    tool_calls.append(ToolCall.from_openai_format(tc.model_dump()))
                else:
                    # Other types, try converting to dictionary
                    try:
                        tool_calls.append(ToolCall.from_openai_format(dict(tc)))
                    except Exception:
                        # Conversion failed, skipped
                        continue

        # Reasoning models (DeepSeek R1, o1, etc.) may return reasoning_content, content is the main answer
        # When content is empty, use reasoning_content as fallback to avoid downstream parsing failure.
        raw_content = message.content if hasattr(message, 'content') else None
        if raw_content is None or (isinstance(raw_content, str) and not raw_content.strip()):
            raw_content = getattr(message, 'reasoning_content', None)
        content = raw_content if raw_content else None
        reasoning_content = getattr(message, 'reasoning_content', None)

        return LLMResponse(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason if hasattr(choice, 'finish_reason') else None,
            model=response.model if hasattr(response, 'model') else None,
            provider=self.config.provider,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if hasattr(response, 'usage') and response.usage else None
        )

