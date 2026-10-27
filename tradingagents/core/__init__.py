# tradingagents/core/__init__.py
"""
Core module - Stock analysis engine core components

contains:
- engine: Analysis engine core implementation
- contracts: Data contract definition
"""

from tradingagents.core.engine import (
    # data contract
    DataLayer,
    DataAccess,
    AgentDataContract,
    # Analyze context
    AnalysisContext,
    # data dictionary
    FieldDefinition,
    DynamicDataSchema,
    data_schema,
    # Data Access Manager
    DataAccessManager,
    AccessLogEntry,
    # contract validator
    ContractValidator,
    ValidationResult,
    ValidationError,
    # Analysis engine
    AnalysisPhase,
    PhaseResult,
    AnalysisResult,
    StockAnalysisEngine,
)

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
]

