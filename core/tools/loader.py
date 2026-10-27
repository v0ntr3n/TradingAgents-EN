"""
tool loader

Dynamically loading tool modules
"""

import logging
import importlib
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class ToolLoader:
    """
    tool loader
    
    Automatically discover and load tool modules
    
    Usage:
        loader = ToolLoader()
        
        # Load all tools
        loader.load_all()
        
        # Load specific categories
        loader.load_category("market")
        
        # Load specific tools
        loader.load_tool("get_stock_market_data_unified")
    """
    
    def __init__(self, tools_dir: Optional[str] = None):
        """
        Initialize tool loader
        
        Args:
            tools_dir: Tool directory path, default is core/tools/implementations
        """
        if tools_dir is None:
            # Default tool directory
            current_dir = Path(__file__).parent
            tools_dir = current_dir / "implementations"
        
        self.tools_dir = Path(tools_dir)
        self._loaded_modules = set()
    
    def load_all(self) -> int:
        """
        Load all tool modules
        
        Returns:
            Number of loaded modules
        """
        if not self.tools_dir.exists():
            logger.warning(f"工具目录不存在: {self.tools_dir}")
            return 0
        
        count = 0

        # Traverse all Python files (including .pyc: after JD Cloud source code protection, .py is deleted, leaving only .pyc)
        py_files = list(self.tools_dir.rglob("*.py"))
        py_files += list(self.tools_dir.rglob("*.pyc"))
        for py_file in py_files:
            if py_file.name.startswith("_"):
                continue
            # __pycache__ .pyc in is skipped (overridden by a .py or .pyc top-level file with the same name)
            if "__pycache__" in py_file.parts:
                continue

            try:
                self._load_module_from_file(py_file)
                count += 1
            except Exception as e:
                logger.error(f"加载工具模块失败 {py_file}: {e}")
        
        logger.info(f"✅ 加载了 {count} 个工具模块")
        return count
    
    def load_category(self, category: str) -> int:
        """
        Load a specific category of tools
        
        Args:
            category: Tool category (corresponding subdirectory name)
            
        Returns:
            Number of loaded modules
        """
        category_dir = self.tools_dir / category
        
        if not category_dir.exists():
            logger.warning(f"类别目录不存在: {category_dir}")
            return 0
        
        count = 0
        
        for py_file in category_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                self._load_module_from_file(py_file)
                count += 1
            except Exception as e:
                logger.error(f"加载工具模块失败 {py_file}: {e}")
        
        logger.info(f"✅ 加载了 {count} 个 {category} 类别的工具")
        return count
    
    def load_tool(self, tool_id: str) -> bool:
        """
        Load specific tools
        
        Args:
            tool_id: Tools ID
            
        Returns:
            Is loading successful?
        """
        # Try to search from various category directories
        for category_dir in self.tools_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            # try tool_id.py
            tool_file = category_dir / f"{tool_id}.py"
            if tool_file.exists():
                try:
                    self._load_module_from_file(tool_file)
                    logger.info(f"✅ 加载工具: {tool_id}")
                    return True
                except Exception as e:
                    logger.error(f"加载工具失败 {tool_id}: {e}")
                    return False
        
        logger.warning(f"找不到工具: {tool_id}")
        return False
    
    def _load_module_from_file(self, file_path: Path) -> None:
        """
        Load module from file

        Args:
            file_path: Python file path
        """
        # Calculate module name: starting from the project root directory
        # For example:C:\TradingAgentsCN\core\tools\implementations\market\stock_market_data.py
        # should become:core.tools.implementations.market.stock_market_data

        # Get the project root directory (assuming it is the current working directory or look up)
        current_dir = Path.cwd()

        try:
            rel_path = file_path.relative_to(current_dir)
        except ValueError:
            # If the file is not in the current directory, try using the last few segments of the absolute path
            # start from core
            parts = file_path.parts
            if 'core' in parts:
                core_index = parts.index('core')
                rel_path = Path(*parts[core_index:])
            else:
                raise ValueError(f"无法计算模块路径: {file_path}")

        module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

        # Avoid repeated loading (local tracker)
        if module_name in self._loaded_modules:
            return

        # Avoid conflicts with explicit imports in __init__.py: if the module is already loaded from another path
        #  (Such as __init__.py's from .xxx import ...), reuse directly without secondary import.
        if module_name in sys.modules:
            self._loaded_modules.add(module_name)
            return

        # Import module
        try:
            importlib.import_module(module_name)
        except RecursionError:
            # Circular reference: The module may be loading in another import chain, record it first
            logger.warning(f"模块 {module_name} 因循环引用跳过（可能已由 __init__.py 加载）")
            if module_name not in sys.modules:
                logger.error(f"模块 {module_name} 未加载成功，存在真实的循环依赖问题")
            else:
                self._loaded_modules.add(module_name)
            return

        self._loaded_modules.add(module_name)

        logger.debug(f"加载模块: {module_name}")
    
    def get_loaded_modules(self) -> List[str]:
        """获取已加载的模块列表"""
        return list(self._loaded_modules)


# Global loader instance
_global_loader: Optional[ToolLoader] = None


def get_tool_loader() -> ToolLoader:
    """获取全局工具加载器"""
    global _global_loader
    if _global_loader is None:
        _global_loader = ToolLoader()
    return _global_loader

