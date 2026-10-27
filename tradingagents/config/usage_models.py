#!/usr/bin/env python3
"""
Use the record data model
Used for Token usage statistics and cost tracking
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class UsageRecord:
    """Usage records"""
    timestamp: str  # Timestamp
    provider: str  # supplier
    model_name: str  # Model name
    input_tokens: int  # Enter the number of tokens
    output_tokens: int  # Output the number of tokens
    cost: float  # cost
    currency: str = "CNY"  # currency unit
    session_id: str = ""  # session ID
    analysis_type: str = "stock_analysis"  # Analysis type


@dataclass
class ModelConfig:
    """Model configuration"""
    provider: str  # Supplier:dashscope, openai, google, etc.
    model_name: str  # Model name
    api_key: str  # API key
    base_url: Optional[str] = None  # Custom API address
    max_tokens: int = 4000  # Maximum number of tokens
    temperature: float = 0.7  # Temperature parameter
    enabled: bool = True  # Whether to enable


@dataclass
class PricingConfig:
    """Pricing configuration"""
    provider: str  # supplier
    model_name: str  # Model name
    input_price_per_1k: float  # Enter token price (per 1000 tokens)
    output_price_per_1k: float  # Output token price (per 1000 tokens)
    currency: str = "CNY"  # currency unit

