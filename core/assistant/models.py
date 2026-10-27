"""Intelligent Assistant Quality Architecture (A11)—— Data Contract.

See the design document for core concepts §3.2: 
- Evidence: The original text from which a reply was generated (Evidence Collection First Class Citizen)
- ReplyCandidate: Candidate responses produced by the strategy, carrying evidence + path type contract
- GateResult: Judgment on quality level

Path type contract (for class B"Nude transmission"fundamental means):
- answer: Answers to user questions must be contractually processed by LLM (llm_processed=True) , 
  And passed a full set of Class A traceability inspections;
- passthrough_allowed: The registered system will exit directly (HITL receipt/data synchronization prompt/downgrade rollback, etc.),
  route_id Must be in the REGISTERED_PASSTHROUGH whitelist.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# path type
ROUTE_TYPE_ANSWER = "answer"
ROUTE_TYPE_PASSTHROUGH = "passthrough_allowed"

# Evidence source type
EVIDENCE_TOOL = "tool"
EVIDENCE_SEARCH = "search"
EVIDENCE_USER_MESSAGE = "user_message"
EVIDENCE_HISTORY_TOOL = "history_tool"
EVIDENCE_MEMORY = "memory"

# available as"Data source reference"The type of evidence shown to the front end
_PRESENTABLE_SOURCE_TYPES = frozenset({EVIDENCE_TOOL, EVIDENCE_SEARCH})

# Registered system direct exit path whitelist (new additions require review, see design document §3.3 / risk table)
REGISTERED_PASSTHROUGH = frozenset(
    {
        "hitl",               # HITL Confirm/deny operation receipt
        "unsupported_asset",  # System prompt that the variety is not supported
        "data_precheck",      # Data synchronization guidance tips
        "llm_unavailable",    # LLM Client unavailable prompt
        "timeout",            # Timeout prompt
        "error",              # Abnormal tips
        "fallback_evidence",  # Level Downgrade: Limitations Explained + Evidence text
    }
)


@dataclass
class Evidence:
    """An original piece of evidence.

    Attributes:
        source_type: EVIDENCE_* constant
        source_id:   Tool name / "searxng" / "mem0" Wait
        content:     Original text (The source of digital provenance trusted candidate set)
        locator:     Optional data source positioning (report ID/file path, etc.) for front-end backlinking
    """

    source_type: str
    source_id: str
    content: str
    locator: Optional[str] = None


@dataclass
class ReplyCandidate:
    """Candidate responses produced by the policy.

    Prefer to use factory method construction:
    - ReplyCandidate.answer(..., llm_processed=True): answer type,llm_processed
      As keyword parameters are required, the caller is forced to explicitly declare that it has gone through LLM;
    - ReplyCandidate.passthrough(...): Register the system in the whitelist directly.
    """

    reply: str
    route_id: str
    route_type: str
    tools_used: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    llm_processed: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def answer(
        cls,
        reply: str,
        route_id: str,
        *,
        llm_processed: bool,
        tools_used: Optional[List[str]] = None,
        evidence: Optional[List[Evidence]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "ReplyCandidate":
        """Construct answer candidates. llm_processed required——Prohibited as default"Passed LLM". """
        return cls(
            reply=reply,
            route_id=route_id,
            route_type=ROUTE_TYPE_ANSWER,
            tools_used=list(tools_used or []),
            evidence=list(evidence or []),
            llm_processed=bool(llm_processed),
            meta=dict(meta or {}),
        )

    @classmethod
    def passthrough(
        cls,
        reply: str,
        route_id: str,
        *,
        tools_used: Optional[List[str]] = None,
        evidence: Optional[List[Evidence]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "ReplyCandidate":
        """Construct passthrough_allowed type candidates (route_id is whitelisted by gate verification)."""
        return cls(
            reply=reply,
            route_id=route_id,
            route_type=ROUTE_TYPE_PASSTHROUGH,
            tools_used=list(tools_used or []),
            evidence=list(evidence or []),
            llm_processed=False,
            meta=dict(meta or {}),
        )


@dataclass
class CheckFailure:
    """A single quality check failed."""

    check: str
    reason: str


@dataclass
class GateResult:
    """Quality gate ruling."""

    passed: bool
    failures: List[CheckFailure] = field(default_factory=list)

    @property
    def failed_checks(self) -> List[str]:
        return [f.check for f in self.failures]


def extract_data_refs(evidence: Optional[List[Evidence]]) -> List[Dict[str, Any]]:
    """Extract front-end displayable data references from the evidence set (data_refs true implementation).

    Only tool/search type evidence generates references; press (Type,Source,Positioning) Remove weight.
    user_message/history/memory inaction"External data source link"display.
    """
    refs: List[Dict[str, Any]] = []
    seen = set()
    for ev in evidence or []:
        if ev.source_type not in _PRESENTABLE_SOURCE_TYPES:
            continue
        key = (ev.source_type, ev.source_id, ev.locator)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "source_type": ev.source_type,
                "source_id": ev.source_id,
                "locator": ev.locator,
            }
        )
    return refs
