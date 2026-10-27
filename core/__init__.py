"""
TradingAgents-CN core module

This module contains the core functional layers of TradingAgents-CN, including:
- Unified LLM client (llm/)
- Agent base class and registry (agents/)
- workflow engine (workflow/)
- Enhanced prompt word management (prompts/)
- Authorization management (licensing/)

Relationship to open source components:
- This module is built on open source 'tradingagents' on the package
- License ownership can be found in the LICENSE file in this directory.
"""

__version__ = "1.0.0"
__author__ = "TradingAgents-CN"

# Delay import to avoid circular dependencies
def get_version():
    """Get version number"""
    return __version__


def get_llm_client():
    """Get the unified LLM client"""
    from .llm import UnifiedLLMClient
    return UnifiedLLMClient


def get_workflow_engine():
    """Get workflow engine"""
    from .workflow import WorkflowEngine
    return WorkflowEngine


def get_agent_registry():
    """Get the agent registry"""
    from .agents import AgentRegistry
    return AgentRegistry


# version check
def check_compatibility():
    """Check compatibility with open source tradingagents"""
    try:
        import tradingagents
        ta_version = getattr(tradingagents, '__version__', '0.0.0')
        # Version compatibility checks can be added here
        return True, ta_version
    except ImportError:
        return False, None


def get_license_manager():
    """Get authorization manager"""
    from .licensing import LicenseManager
    return LicenseManager


def get_workflow_api():
    """Get workflow API"""
    from .api import WorkflowAPI
    return WorkflowAPI


def get_agent_api():
    """Get the agent API"""
    from .api import AgentAPI
    return AgentAPI


__all__ = [
    "__version__",
    "__author__",
    "get_version",
    "get_llm_client",
    "get_workflow_engine",
    "get_agent_registry",
    "get_license_manager",
    "get_workflow_api",
    "get_agent_api",
    "check_compatibility",
]

