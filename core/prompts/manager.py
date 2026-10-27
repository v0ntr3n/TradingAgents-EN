"""
prompt word manager

Unified management of loading, caching and rendering of prompt words
"""

import os
import threading
from typing import Dict, Optional

from .template import PromptTemplate
from .loader import PromptLoader


class PromptManager:
    """
    prompt word manager (Singleton pattern)
    
    Usage:
        manager = PromptManager()
        
        # Get prompt word
        prompt = manager.get("market_analyst", category="analysts")
        
        # rendering prompt word
        text = manager.render(
            "market_analyst",
            category="analysts",
            ticker="AAPL",
            date="2024-01-15"
        )
        
        # switch language
        manager.set_language("en")
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PromptManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._language = os.getenv("PROMPT_LANGUAGE", "zh")
            self._loader = PromptLoader()
            self._custom_templates: Dict[str, PromptTemplate] = {}
            self._initialized = True
    
    @property
    def language(self) -> str:
        """Current language"""
        return self._language
    
    def set_language(self, language: str) -> None:
        """Set language"""
        self._language = language
        self._loader.clear_cache()
    
    def get(
        self,
        name: str,
        category: Optional[str] = None,
        language: Optional[str] = None
    ) -> Optional[PromptTemplate]:
        """
        Get prompt word template
        
        Args:
            name: Template name
            category: Category
            language: language (Use current language by default)
            
        Returns:
            prompt word template
        """
        lang = language or self._language
        
        # Check custom templates first
        custom_key = f"{lang}/{category}/{name}" if category else f"{lang}/{name}"
        if custom_key in self._custom_templates:
            return self._custom_templates[custom_key]
        
        # Load from file
        return self._loader.load(name, lang, category)
    
    def render(
        self,
        name: str,
        category: Optional[str] = None,
        language: Optional[str] = None,
        **variables
    ) -> str:
        """
        rendering prompt word
        
        Args:
            name: Template name
            category: Category
            language: language
            **variables: Template variables
            
        Returns:
            Rendered text
        """
        template = self.get(name, category, language)
        
        if template is None:
            return f"[prompt word '{name}' not found]"
        
        return template.render(**variables)
    
    def register(
        self,
        name: str,
        template: str,
        category: Optional[str] = None,
        language: Optional[str] = None
    ) -> PromptTemplate:
        """
        Register a custom prompt word template
        
        Args:
            name: Template name
            template: Template content
            category: Category
            language: language
            
        Returns:
            Created template object
        """
        lang = language or self._language
        key = f"{lang}/{category}/{name}" if category else f"{lang}/{name}"
        
        prompt_template = PromptTemplate(
            template=template,
            name=name,
            language=lang
        )
        
        self._custom_templates[key] = prompt_template
        return prompt_template
    
    def list_available(
        self,
        category: Optional[str] = None,
        language: Optional[str] = None
    ) -> Dict[str, PromptTemplate]:
        """List available prompt words"""
        lang = language or self._language
        return self._loader.load_all(lang, category)
    
    def exists(
        self,
        name: str,
        category: Optional[str] = None,
        language: Optional[str] = None
    ) -> bool:
        """Check if the prompt word exists"""
        lang = language or self._language
        
        # Check custom templates
        custom_key = f"{lang}/{category}/{name}" if category else f"{lang}/{name}"
        if custom_key in self._custom_templates:
            return True
        
        # Check files
        return self._loader.exists(name, lang, category)


# Convenience function
def get_prompt(
    name: str,
    category: Optional[str] = None,
    **variables
) -> str:
    """
    Convenience function: Get and render the prompt word
    
    Usage:
        from core.prompts import get_prompt
        
        prompt = get_prompt("market_analyst", category="analysts", ticker="AAPL")
    """
    manager = PromptManager()
    return manager.render(name, category, **variables)

