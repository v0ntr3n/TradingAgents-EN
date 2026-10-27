"""
LLM Adapter base class
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from ..models import LLMConfig, LLMResponse, Message, ToolCall


class BaseAdapter(ABC):
    """
    LLM Adapter base class
    
    All provider adapters need to inherit this class and implement the corresponding methods
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize client connection"""
        pass
    
    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Synchronous chat interface
        
        Args:
            messages: Message list
            tools: List of available tool definitions
            **kwargs: Other parameters
            
        Returns:
            LLMResponse: Unified response format
        """
        pass
    
    @abstractmethod
    async def achat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Asynchronous chat interface
        
        Args:
            messages: Message list
            tools: List of available tool definitions
            **kwargs: Other parameters
            
        Returns:
            LLMResponse: Unified response format
        """
        pass
    
    @abstractmethod
    async def astream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Asynchronous streaming output interface
        
        Args:
            messages: Message list
            tools: List of available tool definitions
            **kwargs: Other parameters
            
        Yields:
            str: Text fragment for streaming output
        """
        pass
    
    def convert_tools_to_provider_format(
        self, 
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert unified tool format to provider specific format
        
        The default implementation returns OpenAI format, subclasses can override
        
        Args:
            tools: Unified tool definition list
            
        Returns:
            Converted tool definition list
        """
        return tools
    
    def convert_tool_calls_from_response(
        self, 
        raw_tool_calls: Any
    ) -> List[ToolCall]:
        """
        Extract and transform tool calls from provider responses
        
        Args:
            raw_tool_calls: Raw tool call data
            
        Returns:
            Standardized tool call list
        """
        return []
    
    def validate_config(self) -> bool:
        """
        Verify that the configuration is valid
        
        Returns:
            bool: Is the configuration valid?
        """
        if not self.config.api_key:
            return False
        if not self.config.model:
            return False
        return True
    
    @property
    def provider_name(self) -> str:
        """Provider name"""
        # Compatible use_enum_values=True: config.provider May be a string or an enumeration
        provider = self.config.provider
        return provider.value if hasattr(provider, "value") else str(provider)
    
    @property
    def model_name(self) -> str:
        """Model name"""
        return self.config.model

