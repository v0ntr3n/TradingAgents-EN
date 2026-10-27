"""
Google Generative AI adapter

Handle Google-specific API formats and tool calling methods
"""

from typing import Any, AsyncIterator, Dict, List, Optional

# Optional dependencies:google.generativeai
try:
    import google.generativeai as genai
    from google.generativeai.types import content_types
    GOOGLE_AVAILABLE = True
except ImportError:
    genai = None
    content_types = None
    GOOGLE_AVAILABLE = False

from ..models import (
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
)
from .base import BaseAdapter


class GoogleAdapter(BaseAdapter):
    """Google Generative AI adapter"""

    SUPPORTED_PROVIDERS = [LLMProvider.GOOGLE]

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not GOOGLE_AVAILABLE:
            raise ImportError(
                "google-generativeai Not installed. Please run: pip install google-generativeai"
            )
        self._model = None

    def initialize(self) -> None:
        """Initialize the Google AI client"""
        genai.configure(api_key=self.config.api_key)
        self._model = genai.GenerativeModel(self.config.model)
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert message format to Google format"""
        result = []
        system_instruction = None
        
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_instruction = msg.content
                continue
            
            role = "user" if msg.role == MessageRole.USER else "model"
            
            parts = []
            if msg.content:
                parts.append({"text": msg.content})
            
            # Process tool call results
            if msg.role == MessageRole.TOOL and msg.tool_call_id:
                parts.append({
                    "function_response": {
                        "name": msg.name or "unknown",
                        "response": {"result": msg.content}
                    }
                })
            
            # Handling tool calls
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append({
                        "function_call": {
                            "name": tc.name,
                            "args": tc.arguments
                        }
                    })
            
            if parts:
                result.append({"role": role, "parts": parts})
        
        return result, system_instruction
    
    def convert_tools_to_provider_format(
        self, 
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tool format to Google format"""
        google_tools = []
        
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                google_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
        
        return [{"function_declarations": google_tools}] if google_tools else []
    
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """synchronous chat"""
        if not self._model:
            self.initialize()
        
        contents, system_instruction = self._convert_messages(messages)
        
        generation_config = {
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        # max_tokens: kwargs first, second config
        max_tokens = kwargs.get("max_tokens") or self.config.max_tokens
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        # Create a model instance with system directives
        model = self._model
        if system_instruction:
            model = genai.GenerativeModel(
                self.config.model,
                system_instruction=system_instruction
            )
        
        # Preparation tools
        google_tools = None
        if tools:
            google_tools = self.convert_tools_to_provider_format(tools)
        
        response = model.generate_content(
            contents,
            generation_config=generation_config,
            tools=google_tools,
        )
        
        return self._parse_response(response)
    
    async def achat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """Asynchronous chat"""
        if not self._model:
            self.initialize()
        
        contents, system_instruction = self._convert_messages(messages)
        
        generation_config = {
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        # max_tokens: kwargs first, second config
        max_tokens = kwargs.get("max_tokens") or self.config.max_tokens
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        model = self._model
        if system_instruction:
            model = genai.GenerativeModel(
                self.config.model,
                system_instruction=system_instruction
            )
        
        google_tools = None
        if tools:
            google_tools = self.convert_tools_to_provider_format(tools)
        
        response = await model.generate_content_async(
            contents,
            generation_config=generation_config,
            tools=google_tools,
        )
        
        return self._parse_response(response)
    
    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Asynchronous streaming output"""
        # Google API Streaming implementation
        # Note: Need to be adjusted according to actual API
        response = await self.achat(messages, tools, **kwargs)
        if response.content:
            yield response.content
    
    def _parse_response(self, response) -> LLMResponse:
        """Parse Google response"""
        content = None
        tool_calls = []
        
        if response.candidates:
            candidate = response.candidates[0]
            parts = candidate.content.parts
            
            for part in parts:
                if hasattr(part, 'text') and part.text:
                    content = part.text
                elif hasattr(part, 'function_call'):
                    fc = part.function_call
                    tool_calls.append(ToolCall(
                        id=f"call_{hash(fc.name)}",
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {}
                    ))
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.candidates[0].finish_reason.name if response.candidates else None,
            model=self.config.model,
            provider=LLMProvider.GOOGLE,
        )

