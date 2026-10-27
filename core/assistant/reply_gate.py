"""Intelligent Assistant Quality Architecture (A11)—— Contractual only quality outlet ReplyGate.

Design documentation §3.3: 
- Contract verification (for Class B naked pass-through):
  * answer type must llm_processed=True (Path deeds prohibit direct exit without LLM);
  * passthrough_allowed The route_id of type must be in the registration whitelist.
- A Class traceability check (only for answer type): Incorporate the four lines of defense.

No heuristic online blocking such as text overlap rate/number of links (v1 review abandoned, see decision D1/D5):
The threshold not only allows for accidental damage to reasonable references but also allows for rearrangement and transparent transmission, and the immunity area will be so large that the level will be invalid.
B Classes are enforced by contract, and text statistical signals are only analyzed offline.
"""

import logging
from typing import List, Optional

from . import defense
from .models import (
    EVIDENCE_HISTORY_TOOL,
    EVIDENCE_MEMORY,
    EVIDENCE_SEARCH,
    EVIDENCE_TOOL,
    ROUTE_TYPE_ANSWER,
    REGISTERED_PASSTHROUGH,
    CheckFailure,
    Evidence,
    GateResult,
    ReplyCandidate,
)

logger = logging.getLogger(__name__)

# failed check → human reading instructions
_CHECK_REASONS = {
    "llm_processed_contract": "answer The path has not been processed by LLM (the contract prohibits naked export)",
    "passthrough_registration": "The direct outgoing path is not registered in the whitelist",
    "fabricated_tool_json": "Reply with crafted JSON structured results",
    "fabricated_tool_refs": "The reply faked tool call traces",
    "unsourced_numbers": "Contains a large number of specific numbers without calling the tool",
    "untraced_risky_numbers": "Contains high-risk numbers that cannot be traced to tools/search/history/user input",
}

# Maximum length of each evidence excerpt during downgrade rollback
_EVIDENCE_SNIPPET_LIMIT = 800
_FALLBACK_EVIDENCE_LIMIT = 8


class ReplyGate:
    """The only quality outlet for all path replies (stateless, reusable singleton)."""

    def run(
        self,
        candidate: ReplyCandidate,
        user_message: str = "",
        history_tool_contents: Optional[List[str]] = None,
    ) -> GateResult:
        failures: List[CheckFailure] = []

        # ① Path type contract verification
        if candidate.route_type == ROUTE_TYPE_ANSWER:
            if not candidate.llm_processed:
                failures.append(self._fail("llm_processed_contract"))
        else:
            if candidate.route_id not in REGISTERED_PASSTHROUGH:
                failures.append(
                    CheckFailure(
                        check="passthrough_registration",
                        reason=f"straight out path {candidate.route_id!r} Not registered in the whitelist",
                    )
                )

        # ② A Class traceability check (only answer type; must be blocked when the contract fails, no need to run traceability repeatedly)
        if candidate.route_type == ROUTE_TYPE_ANSWER and candidate.llm_processed:
            failures.extend(self._run_answer_checks(candidate, user_message, history_tool_contents or []))

        return GateResult(passed=not failures, failures=failures)

    @staticmethod
    def _fail(check: str) -> CheckFailure:
        return CheckFailure(check=check, reason=_CHECK_REASONS.get(check, check))

    @staticmethod
    def _run_answer_checks(
        candidate: ReplyCandidate,
        user_message: str,
        history_tool_contents: List[str],
    ) -> List[CheckFailure]:
        """Restore the evidence into the input parameters required by the four lines of defense and execute them one by one."""
        out: List[CheckFailure] = []
        reply = candidate.reply or ""
        tools_used = candidate.tools_used or []

        # tool/search evidence → tool_results for this round (defense line read-only content/is_error)
        tool_results = [
            {"tool": ev.source_id, "content": ev.content or ""}
            for ev in candidate.evidence
            if ev.source_type in (EVIDENCE_TOOL, EVIDENCE_SEARCH)
        ]
        # history_tool/memory evidence + The history of multiple rounds passed in by the caller → Trusted text
        trusted = list(history_tool_contents)
        trusted.extend(
            ev.content or ""
            for ev in candidate.evidence
            if ev.source_type in (EVIDENCE_HISTORY_TOOL, EVIDENCE_MEMORY)
        )

        if defense._has_fabricated_tool_json(reply):
            out.append(ReplyGate._fail("fabricated_tool_json"))
        if defense._has_fabricated_tool_refs(reply, tools_used):
            out.append(ReplyGate._fail("fabricated_tool_refs"))
        if defense._has_unsourced_numbers(reply, tools_used):
            out.append(ReplyGate._fail("unsourced_numbers"))
        if defense._has_untraced_risky_numbers(
            reply, tool_results, tools_used, user_message, trusted
        ):
            out.append(ReplyGate._fail("untraced_risky_numbers"))
        return out


def build_fallback_candidate(
    candidate: ReplyCandidate,
    failures: List[CheckFailure],
) -> ReplyCandidate:
    """The level that failed ② Level downgrade: fallback"Limitations + Evidence text" (No naked transparent transmission, no loss of functions).

    No.① level"Feedback reanswer"This is done by each answer path when calling LLM (the main path _do_chat
    There are fine retries; the fast path has a built-in summary). Coming here means that I still can t do it after re-answering.
    Switch to the registered fallback_evidence system to ensure that users get real information.
    """
    checks = "、".join(dict.fromkeys(f.check for f in failures)) or "Source verification"
    header = (
        f"Sorry, the answer generated this time failed the data quality check ({checks}) , "
        "In order to avoid presenting unverified information, only the raw data actually obtained by the system are provided below."
        "Please make your own judgment based on the source:\n\n"
    )

    presentable = [
        ev
        for ev in candidate.evidence
        if ev.source_type in (EVIDENCE_TOOL, EVIDENCE_SEARCH) and ev.content
    ]
    if presentable:
        blocks = []
        for ev in presentable[:_FALLBACK_EVIDENCE_LIMIT]:
            snippet = ev.content.strip()
            if len(snippet) > _EVIDENCE_SNIPPET_LIMIT:
                snippet = snippet[:_EVIDENCE_SNIPPET_LIMIT] + "……"
            blocks.append(f" [Source:{ev.source_id}] \n{snippet}")
        body = "\n\n".join(blocks)
    else:
        body = " (No citationable original data was obtained this time. Please change the question to a more specific one and try again. )"

    return ReplyCandidate.passthrough(
        reply=header + body,
        route_id="fallback_evidence",
        tools_used=candidate.tools_used,
        evidence=candidate.evidence,
        meta={"degraded_from": candidate.route_id, "failed_checks": [f.check for f in failures]},
    )
