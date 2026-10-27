"""
legacy code adapter

Adapt tools from the old Toolkit class to the new ToolRegistry
"""

import logging
from typing import Dict, Any, List, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class LegacyToolkitAdapter:
    """
    Adapt old Toolkit to new ToolRegistry
    
    Purpose:
    1. Maintain backward compatibility during migration
    2. Automatically register tools from Toolkit to new Registry
    """
    
    # Tool map: old method names -> New tool configuration
    TOOL_MAPPING = {
        "get_reddit_news": {
            "id": "get_reddit_news",
            "name": "Reddit global news",
            "category": "news",
            "description": "Get Reddit global news",
        },
        "get_finnhub_news": {
            "id": "get_finnhub_news",
            "name": "Finnhub News",
            "category": "news",
            "description": "Get Finnhub stock news",
        },
        "get_reddit_stock_info": {
            "id": "get_reddit_stock_sentiment",
            "name": "Reddit stock sentiment",
            "category": "social",
            "description": "Get Reddit stock discussion sentiment",
        },
        "get_chinese_social_sentiment": {
            "id": "get_chinese_social_sentiment",
            "name": "Chinese social media sentiment",
            "category": "social",
            "description": "Get China Social Media Stock Sentiment",
        },
        "get_stock_market_data_unified": {
            "id": "get_stock_market_data_unified",
            "name": "Unified stock market data",
            "category": "market",
            "description": "Obtain complete market data of A-share stocks: core market indicators such as stock price, increase or decrease, trading volume, market capitalization, PE/PB, turnover rate, amplitude, etc.",
            "capability_tags": ["Quotes", "stock price", "Market value", "Increase or decrease", "Volume", "PE", "PB", "turnover rate", "Technical indicators", "A shares"],
            "when_to_use": "Use it when you need to obtain market data such as stock price, market value, rise and fall, PE/PB valuation, trading volume, etc. of A-share stocks.",
            "tool_role_hint": "primary",
            "output_shape": "structured_metrics",
        },
        "get_stock_fundamentals_unified": {
            "id": "get_stock_fundamentals_unified",
            "name": "Unify fundamental data",
            "category": "fundamentals",
            "description": "Obtain stock fundamental data in a unified format",
        },
        "get_YFin_data_online": {
            "id": "get_yfinance_data",
            "name": "Yahoo Finance data",
            "category": "market",
            "description": "Get stock data from Yahoo Finance",
        },
        "get_SEC_filings_analysis": {
            "id": "get_sec_filings",
            "name": "SEC File analysis",
            "category": "fundamentals",
            "description": "Obtain and analyze SEC financial documents",
        },
        "get_simfin_balance_sheet": {
            "id": "get_balance_sheet",
            "name": "balance sheet",
            "category": "fundamentals",
            "description": "Get balance sheet data",
        },
        "get_simfin_cashflow": {
            "id": "get_cashflow",
            "name": "cash flow statement",
            "category": "fundamentals",
            "description": "Get cash flow statement data",
        },
        "get_simfin_income_stmt": {
            "id": "get_income_statement",
            "name": "income statement",
            "category": "fundamentals",
            "description": "Get income statement data",
        },
    }
    
    @classmethod
    def register_all(cls, tool_registry=None) -> int:
        """
        Register tools from Toolkit to new Registry
        
        Args:
            tool_registry: ToolRegistry instance, if None the default instance is used
            
        Returns:
            Number of successfully registered tools
        """
        if tool_registry is None:
            from core.tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
        
        registered = 0
        
        try:
            from tradingagents.agents.utils.agent_utils import Toolkit
            toolkit = Toolkit()
            
            for method_name, config in cls.TOOL_MAPPING.items():
                try:
                    # Get the original method
                    if not hasattr(toolkit, method_name):
                        logger.warning(f"Toolkit No method found in: {method_name}")
                        continue
                    
                    method = getattr(toolkit, method_name)
                    
                    # Register to the new Registry and pass through capability_tags, when_to_use Enhanced fields
                    extra_kwargs = {}
                    for key in ("capability_tags", "when_to_use", "when_not_to_use",
                                "returns", "tool_role_hint", "output_shape",
                                "preferred_for", "not_replacement_for", "fc_enabled",
                                "data_source_handling"):
                        if key in config:
                            extra_kwargs[key] = config[key]
                    tool_registry.register_function(
                        tool_id=config["id"],
                        func=method,
                        name=config["name"],
                        category=config["category"],
                        description=config["description"],
                        is_legacy=True,
                        **extra_kwargs,
                    )
                    
                    registered += 1
                    logger.debug(f"Register old tools: {method_name} -> {config['id']}")
                    
                except Exception as e:
                    logger.error(f"Registration tool {method_name} failed: {e}")
            
            logger.info(f"✅ Registered from Toolkit {registered} tools")
            
        except ImportError as e:
            logger.warning(f"Unable to import Toolkit: {e}")
        except Exception as e:
            logger.error(f"Failed to register old tool: {e}")
        
        return registered
    
    @classmethod
    def get_tool_mapping(cls) -> Dict[str, Dict[str, Any]]:
        """Get tool mapping table"""
        return cls.TOOL_MAPPING.copy()
    
    @classmethod
    def get_new_tool_id(cls, old_method_name: str) -> str:
        """Get new tool based on old method name ID"""
        if old_method_name in cls.TOOL_MAPPING:
            return cls.TOOL_MAPPING[old_method_name]["id"]
        return old_method_name

