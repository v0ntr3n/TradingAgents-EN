"""
Model Capability Grading System

Define the model s ability level, applicable roles, feature labels and other metadata,
For intelligent matching of analysis depth and model selection.

🆕 Aggregation channel support:
- Support aggregation channels such as 302.AI, OpenRouter, One API, etc.
- Model name format for aggregation channels:{provider}/{model} (Such as openai/gpt-4)
- The system will automatically map to the capability configuration of the original model.
"""

from enum import IntEnum, Enum
from typing import Dict, List, Any, Tuple


class ModelCapabilityLevel(IntEnum):
    """Model ability level (level 1-5)"""
    BASIC = 1          # Basics: suitable for level 1-2 analysis, lightweight and fast
    STANDARD = 2       # Standard: Suitable for level 1-3 analysis, daily use
    ADVANCED = 3       # Advanced: Suitable for level 1-4 analysis and complex reasoning
    PROFESSIONAL = 4   # Professional: Suitable for level 1-5 analysis, professional level analysis
    FLAGSHIP = 5       # Flagship: Suitable for all levels, the strongest ability


class ModelRole(str, Enum):
    """Model role type"""
    QUICK_ANALYSIS = "quick_analysis"  # Quick analysis (data collection, tool invocation)
    DEEP_ANALYSIS = "deep_analysis"    # In-depth analysis (reasoning, decision-making)
    BOTH = "both"                      # suitable for both


class ModelFeature(str, Enum):
    """Model property labels"""
    TOOL_CALLING = "tool_calling"      # Support tool calling (required)
    LONG_CONTEXT = "long_context"      # Support long context
    REASONING = "reasoning"            # Strong reasoning ability
    VISION = "vision"                  # Support visual input
    FAST_RESPONSE = "fast_response"    # Quick response
    COST_EFFECTIVE = "cost_effective"  # Cost effective


# Description of ability level
CAPABILITY_DESCRIPTIONS = {
    1: "Basic model - suitable for quick analysis and simple tasks, fast response and low cost",
    2: "Standard model - suitable for daily analysis and routine tasks, balancing performance and cost",
    3: "Advanced models - suitable for deep analysis and complex reasoning, with higher quality",
    4: "Professional model - suitable for professional-level analysis and multi-round debates, high-quality output",
    5: "Flagship model - the most capable, suitable for comprehensive analysis and critical decision-making"
}


# Minimum competency level required for depth of analysis
ANALYSIS_DEPTH_REQUIREMENTS = {
    "fast": {
        "min_capability": 1,
        "quick_model_min": 1,
        "deep_model_min": 1,
        "required_features": [ModelFeature.TOOL_CALLING],
        "description": "1 Level quick analysis: any model is acceptable, with quick response models preferred."
    },
    "Basics": {
        "min_capability": 1,
        "quick_model_min": 1,
        "deep_model_min": 2,
        "required_features": [ModelFeature.TOOL_CALLING],
        "description": "2 Level basic analysis: Basic level can be used for fast models, and standard level or above is recommended for deep models."
    },
    "Standard": {
        "min_capability": 2,
        "quick_model_min": 1,
        "deep_model_min": 2,
        "required_features": [ModelFeature.TOOL_CALLING],
        "description": "3 Level standard analysis: Basic level is available for fast models, and standard level or above is required for deep models."
    },
    "Depth": {
        "min_capability": 3,
        "quick_model_min": 2,
        "deep_model_min": 3,
        "required_features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING],
        "description": "4 Level depth analysis: Fast models require standard level, deep models require advanced level or above, and require reasoning capabilities."
    },
    "Comprehensive": {
        "min_capability": 4,
        "quick_model_min": 2,
        "deep_model_min": 4,
        "required_features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING],
        "description": "5 Comprehensive analysis of levels: fast models require standard level, deep models require professional level or above, and strong reasoning ability"
    }
}


# Default capability configurations for common models (for initialization and reference)
DEFAULT_MODEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    # ==================== Ali Bailian (DashScope) ====================
    "qwen-turbo": {
        "capability_level": 1,
        "suitable_roles": [ModelRole.QUICK_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["fast", "Basics"],
        "performance_metrics": {"speed": 5, "cost": 5, "quality": 3},
        "description": "Tongyi Qianwen lightweight version, fast response, suitable for data collection"
    },
    "qwen-plus": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT],
        "recommended_depths": ["fast", "Basics", "Standard"],
        "performance_metrics": {"speed": 4, "cost": 4, "quality": 4},
        "description": "Tongyi Qianwen Standard Edition, balancing performance and cost"
    },
    "qwen-max": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 3, "cost": 2, "quality": 5},
        "description": "Tongyi Qianwen flagship version, powerful reasoning ability"
    },
    "qwen3-max": {
        "capability_level": 5,
        "suitable_roles": [ModelRole.DEEP_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING],
        "recommended_depths": ["Depth", "Comprehensive"],
        "performance_metrics": {"speed": 2, "cost": 1, "quality": 5},
        "description": "Tongyi Qianwen long text version, super long context"
    },
    
    # ==================== OpenAI ====================
    "gpt-3.5-turbo": {
        "capability_level": 1,
        "suitable_roles": [ModelRole.QUICK_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["fast", "Basics"],
        "performance_metrics": {"speed": 5, "cost": 5, "quality": 3},
        "description": "GPT-3.5 Turbo, Fast and economical"
    },
    "gpt-4": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 3, "cost": 3, "quality": 4},
        "description": "GPT-4, Strong reasoning skills"
    },
    "gpt-4-turbo": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING, ModelFeature.VISION],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 4, "cost": 2, "quality": 5},
        "description": "GPT-4 Turbo, Faster and stronger"
    },
    "gpt-4o-mini": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["fast", "Basics", "Standard"],
        "performance_metrics": {"speed": 5, "cost": 5, "quality": 3},
        "description": "GPT-4o Mini, Affordable"
    },
    "o1-mini": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.DEEP_ANALYSIS],
        "features": [ModelFeature.REASONING],
        "recommended_depths": ["Depth", "Comprehensive"],
        "performance_metrics": {"speed": 2, "cost": 3, "quality": 5},
        "description": "O1 Mini, Strong inference model"
    },
    "o1": {
        "capability_level": 5,
        "suitable_roles": [ModelRole.DEEP_ANALYSIS],
        "features": [ModelFeature.REASONING],
        "recommended_depths": ["Comprehensive"],
        "performance_metrics": {"speed": 1, "cost": 1, "quality": 5},
        "description": "O1, Strongest reasoning ability"
    },
    "o4-mini": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.DEEP_ANALYSIS],
        "features": [ModelFeature.REASONING],
        "recommended_depths": ["Depth", "Comprehensive"],
        "performance_metrics": {"speed": 2, "cost": 3, "quality": 5},
        "description": "O4 Mini, Next generation inference model"
    },
    
    # ==================== DeepSeek ====================
    "deepseek-chat": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 4, "cost": 5, "quality": 4},
        "description": "DeepSeek Chat, High cost performance"
    },
    
    # ==================== Baidu Wenxin (Qianfan) ====================
    "ernie-3.5": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING],
        "recommended_depths": ["fast", "Basics", "Standard"],
        "performance_metrics": {"speed": 4, "cost": 4, "quality": 3},
        "description": "Wen Xin Yi Yan 3.5, standard version"
    },
    "ernie-4.0": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 3, "cost": 3, "quality": 4},
        "description": "Wen Xin Yi Yan 4.0, advanced version"
    },
    "ernie-4.0-turbo": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING, ModelFeature.FAST_RESPONSE],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 4, "cost": 2, "quality": 5},
        "description": "Wen Xin Yi Yan 4.0 Turbo, flagship version"
    },
    
    # ==================== Wisdom spectrum AI (GLM) ====================
    "glm-3-turbo": {
        "capability_level": 1,
        "suitable_roles": [ModelRole.QUICK_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["fast", "Basics"],
        "performance_metrics": {"speed": 5, "cost": 5, "quality": 3},
        "description": "GLM-3 Turbo, fast version"
    },
    "glm-4": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 3, "cost": 3, "quality": 4},
        "description": "GLM-4, standard version"
    },
    "glm-4-plus": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 3, "cost": 2, "quality": 5},
        "description": "GLM-4 Plus, flagship version"
    },
    
    # ==================== Anthropic Claude ====================
    "claude-3-haiku": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.QUICK_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE],
        "recommended_depths": ["fast", "Basics", "Standard"],
        "performance_metrics": {"speed": 5, "cost": 4, "quality": 3},
        "description": "Claude 3 Haiku, express version"
    },
    "claude-3-sonnet": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.VISION],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 4, "cost": 3, "quality": 4},
        "description": "Claude 3 Sonnet, balanced version"
    },
    "claude-3-opus": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING, ModelFeature.VISION],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 3, "cost": 2, "quality": 5},
        "description": "Claude 3 Opus, flagship version"
    },
    "claude-3.5-sonnet": {
        "capability_level": 5,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING, ModelFeature.VISION],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 4, "cost": 2, "quality": 5},
        "description": "Claude 3.5 Sonnet, latest flagship"
    },

    # ==================== Google Gemini ====================
    "gemini-pro": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.REASONING],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 4, "cost": 4, "quality": 4},
        "description": "Gemini Pro, Classic stable version"
    },
    "gemini-1.5-pro": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING, ModelFeature.VISION],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 4, "cost": 3, "quality": 5},
        "description": "Gemini 1.5 Pro, Long context flagship"
    },
    "gemini-1.5-flash": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.QUICK_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["fast", "Basics", "Standard"],
        "performance_metrics": {"speed": 5, "cost": 5, "quality": 3},
        "description": "Gemini 1.5 Flash, Quick response version"
    },
    "gemini-2.0-flash": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING, ModelFeature.FAST_RESPONSE],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 5, "cost": 3, "quality": 5},
        "description": "Gemini 2.0 Flash, A new generation of fast flagship"
    },
    "gemini-2.5-flash-lite-preview-06-17": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.QUICK_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.FAST_RESPONSE, ModelFeature.COST_EFFECTIVE],
        "recommended_depths": ["fast", "Basics"],
        "performance_metrics": {"speed": 5, "cost": 5, "quality": 3},
        "description": "Gemini 2.5 Flash Lite, Light preview version"
    },

    # ==================== dark side of the moon (Moonshot) ====================
    "moonshot-v1-8k": {
        "capability_level": 2,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING],
        "recommended_depths": ["fast", "Basics", "Standard"],
        "performance_metrics": {"speed": 4, "cost": 4, "quality": 3},
        "description": "Moonshot V1 8K, Standard version"
    },
    "moonshot-v1-32k": {
        "capability_level": 3,
        "suitable_roles": [ModelRole.BOTH],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {"speed": 3, "cost": 3, "quality": 4},
        "description": "Moonshot V1 32K, long context version"
    },
    "moonshot-v1-128k": {
        "capability_level": 4,
        "suitable_roles": [ModelRole.DEEP_ANALYSIS],
        "features": [ModelFeature.TOOL_CALLING, ModelFeature.LONG_CONTEXT, ModelFeature.REASONING],
        "recommended_depths": ["Standard", "Depth", "Comprehensive"],
        "performance_metrics": {"speed": 2, "cost": 2, "quality": 5},
        "description": "Moonshot V1 128K, Ultra long context flagship"
    },
}


def get_model_capability_badge(level: int) -> Dict[str, str]:
    """Get ability level badge style"""
    badges = {
        1: {"text": "Basics", "color": "#909399", "icon": "⚡"},
        2: {"text": "Standard", "color": "#409EFF", "icon": "📊"},
        3: {"text": "Advanced", "color": "#67C23A", "icon": "🎯"},
        4: {"text": "Professional", "color": "#E6A23C", "icon": "🔥"},
        5: {"text": "flagship", "color": "#F56C6C", "icon": "👑"}
    }
    return badges.get(level, badges[2])


def get_role_badge(role: ModelRole) -> Dict[str, str]:
    """Get character badge style"""
    badges = {
        ModelRole.QUICK_ANALYSIS: {"text": "Quick analysis", "color": "success", "icon": "⚡"},
        ModelRole.DEEP_ANALYSIS: {"text": "deep reasoning", "color": "warning", "icon": "🧠"},
        ModelRole.BOTH: {"text": "Universal", "color": "primary", "icon": "🎯"}
    }
    return badges.get(role, badges[ModelRole.BOTH])


def get_feature_badge(feature: ModelFeature) -> Dict[str, str]:
    """Get feature badge style"""
    badges = {
        ModelFeature.TOOL_CALLING: {"text": "Tool call", "color": "info", "icon": "🔧"},
        ModelFeature.LONG_CONTEXT: {"text": "long context", "color": "success", "icon": "📚"},
        ModelFeature.REASONING: {"text": "strong reasoning", "color": "warning", "icon": "🧠"},
        ModelFeature.VISION: {"text": "Vision", "color": "primary", "icon": "👁️"},
        ModelFeature.FAST_RESPONSE: {"text": "fast", "color": "success", "icon": "⚡"},
        ModelFeature.COST_EFFECTIVE: {"text": "economy", "color": "success", "icon": "💰"}
    }
    return badges.get(feature, {"text": str(feature), "color": "info", "icon": "✨"})


# ==================== Aggregation channel configuration ====================

# Default configuration for aggregation channels
AGGREGATOR_PROVIDERS = {
    "302ai": {
        "display_name": "302.AI",
        "description": "302.AI Aggregation platform provides unified interface for multi-vendor models",
        "website": "https://302.ai",
        "api_doc_url": "https://doc.302.ai",
        "default_base_url": "https://api.302.ai/v1",
        "model_name_format": "{provider}/{model}",  # Such as: openai/gpt-4
        "supported_providers": ["openai", "anthropic", "google", "deepseek", "qwen"]
    },
    "aihubmix": {
        "display_name": "AiHubMix",
        "description": "AiHubMix Aggregation platform, providing OpenAI compatible unified interface",
        "website": "https://aihubmix.com/?aff=2rIi",
        "api_doc_url": "https://docs.aihubmix.com/cn/quick-start",
        "default_base_url": "https://aihubmix.com/v1",
        "model_name_format": "{model}",
        "supported_providers": ["openai", "anthropic", "google", "deepseek", "qwen"]
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "description": "OpenRouter Aggregation platform supports multiple AI models",
        "website": "https://openrouter.ai",
        "api_doc_url": "https://openrouter.ai/docs",
        "default_base_url": "https://openrouter.ai/api/v1",
        "model_name_format": "{provider}/{model}",
        "supported_providers": ["openai", "anthropic", "google", "meta", "mistral"]
    },
    "oneapi": {
        "display_name": "One API",
        "description": "One API Open source aggregation platform",
        "website": "https://github.com/songquanpeng/one-api",
        "api_doc_url": "https://github.com/songquanpeng/one-api",
        "default_base_url": "http://localhost:3000/v1",  # Users need to deploy by themselves
        "model_name_format": "{model}",  # One API Usually no prefix is needed
        "supported_providers": ["openai", "anthropic", "google", "azure", "claude"]
    },
    "newapi": {
        "display_name": "New API",
        "description": "New API aggregation platform",
        "website": "https://github.com/Calcium-Ion/new-api",
        "api_doc_url": "https://github.com/Calcium-Ion/new-api",
        "default_base_url": "http://localhost:3000/v1",
        "model_name_format": "{model}",
        "supported_providers": ["openai", "anthropic", "google", "azure", "claude"]
    }
}


def is_aggregator_model(model_name: str) -> bool:
    """
    Determine whether it is an aggregation channel model name

    Args:
        model_name: Model name

    Returns:
        Whether it is an aggregate channel model
    """
    return "/" in model_name


def parse_aggregator_model(model_name: str) -> Tuple[str, str]:
    """
    Parse the aggregation channel model name

    Args:
        model_name: Model name (such as openai/gpt-4)

    Returns:
        (provider, model) tuple
    """
    if "/" in model_name:
        parts = model_name.split("/", 1)
        return parts[0], parts[1]
    return "", model_name

