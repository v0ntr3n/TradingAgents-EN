"""Intelligent Assistant Quality Architecture (A11).

Module responsibilities:
- models:      Evidence set/reply candidate/level result data contract
- defense:     Reply to the quality defense line (digital traceability, fabrication detection), pure functions collected from service
- reply_gate:  Contractual only quality exit (reply from all paths passes through here)
- paths:       Path registry (explicit priority) and request context
- lexicon:     Dictionary Fact Source (Stock List / Stock Gate), Stage 4
- metrics:     Quality issues are dropped into inventory (S9), stage 4

Design documents:docs/05-design/v3.0/assistant-quality-architecture-refactor.md
"""

from .models import (
    ROUTE_TYPE_ANSWER,
    ROUTE_TYPE_PASSTHROUGH,
    REGISTERED_PASSTHROUGH,
    EVIDENCE_TOOL,
    EVIDENCE_SEARCH,
    EVIDENCE_USER_MESSAGE,
    EVIDENCE_HISTORY_TOOL,
    EVIDENCE_MEMORY,
    Evidence,
    ReplyCandidate,
    CheckFailure,
    GateResult,
    extract_data_refs,
)
from .reply_gate import ReplyGate
from .reply_gate import build_fallback_candidate
from .lexicon import (
    A_SHARE_CODE_RE,
    StockDirectory,
    detect_unsupported_asset,
    extract_a_share_code,
    stock_directory,
)
from .metrics import AssistantQualityMetrics, quality_metrics
from .paths import (
    AssistantRequest,
    PathRegistry,
    RegisteredPath,
    PathHandler,
    ROUTE_HITL,
    ROUTE_UNSUPPORTED_ASSET,
    ROUTE_LLM_UNAVAILABLE,
    ROUTE_FAST_SEARCH,
    ROUTE_DATA_PRECHECK,
    ROUTE_MAIN_LLM,
    ROUTE_TIMEOUT,
    ROUTE_ERROR,
    PRIORITY_HITL,
    PRIORITY_UNSUPPORTED_ASSET,
    PRIORITY_LLM_UNAVAILABLE,
    PRIORITY_FAST_SEARCH,
    PRIORITY_DATA_PRECHECK,
    PRIORITY_MAIN_LLM,
)

__all__ = [
    "ROUTE_TYPE_ANSWER",
    "ROUTE_TYPE_PASSTHROUGH",
    "REGISTERED_PASSTHROUGH",
    "EVIDENCE_TOOL",
    "EVIDENCE_SEARCH",
    "EVIDENCE_USER_MESSAGE",
    "EVIDENCE_HISTORY_TOOL",
    "EVIDENCE_MEMORY",
    "Evidence",
    "ReplyCandidate",
    "CheckFailure",
    "GateResult",
    "extract_data_refs",
    "ReplyGate",
    "build_fallback_candidate",
    "A_SHARE_CODE_RE",
    "StockDirectory",
    "detect_unsupported_asset",
    "extract_a_share_code",
    "stock_directory",
    "AssistantQualityMetrics",
    "quality_metrics",
    "AssistantRequest",
    "PathRegistry",
    "RegisteredPath",
    "PathHandler",
    "ROUTE_HITL",
    "ROUTE_UNSUPPORTED_ASSET",
    "ROUTE_LLM_UNAVAILABLE",
    "ROUTE_FAST_SEARCH",
    "ROUTE_DATA_PRECHECK",
    "ROUTE_MAIN_LLM",
    "ROUTE_TIMEOUT",
    "ROUTE_ERROR",
    "PRIORITY_HITL",
    "PRIORITY_UNSUPPORTED_ASSET",
    "PRIORITY_LLM_UNAVAILABLE",
    "PRIORITY_FAST_SEARCH",
    "PRIORITY_DATA_PRECHECK",
    "PRIORITY_MAIN_LLM",
]
