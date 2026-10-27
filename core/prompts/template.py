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

