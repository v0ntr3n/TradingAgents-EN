"""
prompt word loader

Load prompt word template from file system
"""

import os
from pathlib import Path
from typing import Dict, Optional

from .template import PromptTemplate


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

