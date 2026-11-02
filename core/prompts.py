from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['template', 'loader', 'manager']:
    _sys.modules[f"core.prompts.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === template.py ===
"""
prompt word template
"""

import re
from typing import Any, Dict, List, Optional, Set


class PromptTemplate:
    """
    prompt word template
    
    Support variable substitution and conditional rendering
    
    Usage:
        template = PromptTemplate('''
        you are a{role}. 
        
        Analyze the following stocks: {ticker}
        Date: {date}
        
        {#if include_history}
        historical data:
        {history}
        {/if}
        ''')
        
        result = template.render(
            role="market analyst",
            ticker="AAPL",
            date="2024-01-15",
            include_history=True,
            history="..."
        )
    """
    
    # variable mode: {variable_name}
    VAR_PATTERN = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
    
    # conditional pattern: {#if condition}...{/if}
    IF_PATTERN = re.compile(
        r'\{#if\s+([a-zA-Z_][a-zA-Z0-9_]*)\}(.*?)\{/if\}',
        re.DOTALL
    )
    
    def __init__(
        self,
        template: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        language: str = "zh"
    ):
        self.template = template
        self.name = name
        self.description = description
        self.language = language
        self._variables: Optional[Set[str]] = None
    
    @property
    def variables(self) -> Set[str]:
        """Get all variables in template"""
        if self._variables is None:
            self._variables = set(self.VAR_PATTERN.findall(self.template))
            # Add condition variable
            for match in self.IF_PATTERN.finditer(self.template):
                self._variables.add(match.group(1))
        return self._variables
    
    def render(self, **kwargs) -> str:
        """
        render template
        
        Args:
            **kwargs: Template variables
            
        Returns:
            Rendered string
        """
        result = self.template
        
        # Handle conditional blocks
        result = self._process_conditions(result, kwargs)
        
        # Substitute variables
        result = self._replace_variables(result, kwargs)
        
        return result.strip()
    
    def _process_conditions(self, text: str, variables: Dict[str, Any]) -> str:
        """Handle conditional blocks"""
        def replace_condition(match):
            condition_var = match.group(1)
            content = match.group(2)
            
            # Check conditions
            if variables.get(condition_var):
                return content
            return ""
        
        return self.IF_PATTERN.sub(replace_condition, text)
    
    def _replace_variables(self, text: str, variables: Dict[str, Any]) -> str:
        """Substitute variables"""
        def replace_var(match):
            var_name = match.group(1)
            value = variables.get(var_name, "")
            return str(value) if value is not None else ""
        
        return self.VAR_PATTERN.sub(replace_var, text)
    
    def validate(self, **kwargs) -> List[str]:
        """
        Verify that the variable is complete
        
        Returns:
            Missing variable list
        """
        missing = []
        for var in self.variables:
            if var not in kwargs:
                missing.append(var)
        return missing
    
    def __str__(self) -> str:
        return self.template
    
    def __repr__(self) -> str:
        return f"PromptTemplate(name={self.name!r}, variables={self.variables})"


class SystemPrompt(PromptTemplate):
    """System prompt word template"""
    pass


class UserPrompt(PromptTemplate):
    """User prompt word template"""
    pass


class AssistantPrompt(PromptTemplate):
    """Assistant prompt word template"""
    pass


# === loader.py ===
"""
prompt word loader

Load prompt word template from file system
"""

import os
from pathlib import Path
from typing import Dict, Optional


class PromptLoader:
    """
    prompt word loader
    
    Load prompt word template from prompts/ directory
    
    Directory structure:
        prompts/
        ├── en/
        │   ├── analysts/
        │   │   ├── market_analyst.txt
        │   │   └── news_analyst.txt
        │   └── researchers/
        │       └── bull_researcher.txt
        └── zh/
            ├── analysts/
            │   ├── market_analyst.txt
            │   └── news_analyst.txt
            └── researchers/
                └── bull_researcher.txt
    """
    
    DEFAULT_PROMPTS_DIR = "prompts"
    
    def __init__(self, prompts_dir: Optional[str] = None):
        self.prompts_dir = Path(prompts_dir or self.DEFAULT_PROMPTS_DIR)
        self._cache: Dict[str, PromptTemplate] = {}
    
    def load(
        self,
        name: str,
        language: str = "zh",
        category: Optional[str] = None
    ) -> Optional[PromptTemplate]:
        """
        Load prompt word template
        
        Args:
            name: Template name (without extension)
            language: language (zh/en)
            category: Category (analysts/researchers/traders)
            
        Returns:
            Prompt word template, if it does not exist, return None
        """
        cache_key = f"{language}/{category}/{name}" if category else f"{language}/{name}"
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Build file path
        if category:
            file_path = self.prompts_dir / language / category / f"{name}.txt"
        else:
            file_path = self.prompts_dir / language / f"{name}.txt"
        
        # try to load
        if not file_path.exists():
            # Try .md extension
            file_path = file_path.with_suffix('.md')
            if not file_path.exists():
                return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            template = PromptTemplate(
                template=content,
                name=name,
                language=language
            )
            
            self._cache[cache_key] = template
            return template
            
        except Exception as e:
            print(f"Failed to load prompt words {file_path}: {e}")
            return None
    
    def load_all(
        self,
        language: str = "zh",
        category: Optional[str] = None
    ) -> Dict[str, PromptTemplate]:
        """
        Load all prompt words in the specified directory
        
        Args:
            language: language
            category: Category
            
        Returns:
            {name: template} dictionary
        """
        templates = {}
        
        if category:
            dir_path = self.prompts_dir / language / category
        else:
            dir_path = self.prompts_dir / language
        
        if not dir_path.exists():
            return templates
        
        for file_path in dir_path.glob("*.txt"):
            name = file_path.stem
            template = self.load(name, language, category)
            if template:
                templates[name] = template
        
        for file_path in dir_path.glob("*.md"):
            name = file_path.stem
            if name not in templates:
                template = self.load(name, language, category)
                if template:
                    templates[name] = template
        
        return templates
    
    def exists(
        self,
        name: str,
        language: str = "zh",
        category: Optional[str] = None
    ) -> bool:
        """Check if the prompt word exists"""
        if category:
            file_path = self.prompts_dir / language / category / f"{name}.txt"
        else:
            file_path = self.prompts_dir / language / f"{name}.txt"
        
        return file_path.exists() or file_path.with_suffix('.md').exists()
    
    def clear_cache(self) -> None:
        """clear cache"""
        self._cache.clear()


# === manager.py ===
"""
prompt word manager

Unified management of loading, caching and rendering of prompt words
"""

import os
import threading
from typing import Dict, Optional


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


# === __init__.py ===
"""
Prompt word management module

Manage multilingual prompt word templates
"""

__all__ = [
    "PromptManager",
    "PromptTemplate",
    "PromptLoader",
]
