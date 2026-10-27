# tradingagents/core/engine/__init__.py
"""
Engine module - Stock analysis engine

provide:
- Data contract definition (DataLayer, DataAccess, AgentDataContract)
- Analyze context (AnalysisContext)
- Data Access Manager (DataAccessManager)
- dynamic data dictionary (DynamicDataSchema)
- contract validator (ContractValidator)
"""

from tradingagents.core.engine.data_contract import (
    DataLayer,
    DataAccess,
    AgentDataContract,
)
from tradingagents.core.engine.analysis_context import AnalysisContext
from tradingagents.core.engine.data_schema import (
    FieldDefinition,
    DynamicDataSchema,
    data_schema,
)
from tradingagents.core.engine.data_access_manager import (
    DataAccessManager,
    AccessLogEntry,
)
from tradingagents.core.engine.contract_validator import (
    ContractValidator,
    ValidationResult,
    ValidationError,
)
from tradingagents.core.engine.stock_analysis_engine import (
    AnalysisPhase,
    PhaseResult,
    AnalysisResult,
    StockAnalysisEngine,
)
from tradingagents.core.engine.agent_integrator import AgentIntegrator

__all__ = [
    # data contract
    "DataLayer",
    "DataAccess",
    "AgentDataContract",
    # Analyze context
    "AnalysisContext",
    # data dictionary
    "FieldDefinition",
    "DynamicDataSchema",
    "data_schema",
    # Data Access Manager
    "DataAccessManager",
    "AccessLogEntry",
    # contract validator
    "ContractValidator",
    "ValidationResult",
    "ValidationError",
    # Analysis engine
    "AnalysisPhase",
    "PhaseResult",
    "AnalysisResult",
    "StockAnalysisEngine",
    # Agent Integrate
    "AgentIntegrator",
]

