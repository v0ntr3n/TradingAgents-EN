"""
Intent Context Manager

Manage the intent context of Nanobot conversations to ensure that LLM Agent
Always know in discussion situations"Which Agent is currently being processed and at what stage". 

Problems solved:
  - Requirements Drift: After discussing Agent A for many rounds, LLM created Agent B
  - Phase jump: LLM attempts to build during the confirmation phase, or generates during the build phase Skill
  - Multi-Agent confusion: When multiple Agents are discussed in the same thread, LLM confuses the target
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)


def _to_str_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item is not None]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


class IntentStage(str, Enum):
    """Conversation phase enumeration."""
    EXPLORING = "exploring"              # User is exploring/describing needs
    CAPABILITY_CHECK = "capability_check"  # Checking for capability gaps
    DRAFT_PREPARING = "draft_preparing"    # Preparing workshop draft/demand confirmation draft
    REQUIREMENT_CONFIRMATION_PENDING = "requirement_confirmation_pending"  # Wait for user confirmation of demand
    PLAN_SELECTION_PENDING = "plan_selection_pending"  # Wait for the user to select a plan
    CONFIRMATION_PENDING = "confirmation_pending"  # Compatible with old names, same as PLAN_SELECTION_PENDING
    GENERATING = "generating"              # Generating Agent
    BUILDING = "building"                  # Building version
    TESTING = "testing"                    # Testing
    ITERATING = "iterating"                # Iteratively improving
    GAP_RESOLVING = "gap_resolving"        # Capacity gaps are being addressed
    PUBLISHING = "publishing"              # Publishing
    IDLE = "idle"                         # no clear intention


class IntentAction(str, Enum):
    """The user s top-level intent."""
    CREATE_AGENT = "create_agent"           # create new Agent
    ITERATE_AGENT = "iterate_agent"         # Iteration already Agent
    TEST_AGENT = "test_agent"               # test Agent
    PUBLISH_AGENT = "publish_agent"         # publish Agent
    ADD_CAPABILITY = "add_capability"       # Add new capabilities/Skill
    RESOLVE_GAP = "resolve_gap"             # Address capability gaps
    CHECK_STATUS = "check_status"           # View status/progress
    GENERAL_QA = "general_qa"               # General questions


@dataclass
class IntentContext:
    """The intent context of the current conversation.

    Stored in the thread_context.intent field.
    """
    # --- current focus Agent ---
    spec_id: str = ""
    spec_name: str = ""

    # --- current intention ---
    action: str = ""                        # IntentAction value
    stage: str = ""                         # IntentStage value

    # --- Intent description ---
    intent_summary: str = ""                # A brief description of what the user wants to do (≤200 word)
    active_subtask: str = ""                # Current subtask, such as: Create for goodwill gap Skill
    next_action: str = ""                   # What to do next

    # --- Father and son task chain ---
    task_stack: List[Dict[str, str]] = field(default_factory=list)
    # [{"type":"agent|gap|skill|test", "id":"...", "name":"...", "status":"...", "parent_id":"..."}]
    linked_skills: List[Dict[str, str]] = field(default_factory=list)
    # [{"skill_id":"...", "skill_name":"...", "gap":"...", "status":"..."}]

    # --- history ---
    agents_discussed: List[Dict[str, str]] = field(default_factory=list)
    # [{"spec_id": "...", "spec_name": "...", "last_action": "create/iterate/test"}]

    # --- Last evaluated evidence (for ITERATING phase routing) ---
    last_evaluation_decision: str = ""      # pass / revise / reject
    last_evaluation_blockers: List[str] = field(default_factory=list)
    # Extracted from publish_readiness.blockers of evaluation report
    last_evaluation_categories: List[str] = field(default_factory=list)
    # Extracted from evidence_bundle.findings.category like ["tool_usage", "output_coverage", "execution_plan"]

    # --- Options to be confirmed (solve LLM cross-turn reference resolution problem) ---
    pending_options: List[Dict[str, Any]] = field(default_factory=list)
    # A list of options currently waiting for the user to select, for example:
    # [{"index":1,"id":"plan_a","name":"A Plan","description":"..."}, ...]
    pending_question: str = ""              # Questions currently waiting to be answered by the user
    last_proposed_items: List[Dict[str, Any]] = field(default_factory=list)
    # Recently proposed plans/tools/stocks, etc., used to explain and resolve
    conversation_summary: str = ""          # Summary of the previous round of conversation, injected into the next round to avoid context loss

    # --- Timestamp ---
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "IntentContext":
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            spec_id=str(data.get("spec_id") or ""),
            spec_name=str(data.get("spec_name") or ""),
            action=str(data.get("action") or ""),
            stage=str(data.get("stage") or ""),
            intent_summary=str(data.get("intent_summary") or ""),
            active_subtask=str(data.get("active_subtask") or ""),
            next_action=str(data.get("next_action") or ""),
            last_evaluation_decision=str(data.get("last_evaluation_decision") or ""),
            last_evaluation_blockers=_to_str_list(data.get("last_evaluation_blockers")),
            last_evaluation_categories=_to_str_list(data.get("last_evaluation_categories")),
            pending_options=[
                {str(k): v for k, v in opt.items() if k is not None}
                for opt in (data.get("pending_options") or [])
                if isinstance(opt, dict) and opt.get("index")
            ],
            pending_question=str(data.get("pending_question") or ""),
            last_proposed_items=[
                {str(k): v for k, v in item.items() if k is not None}
                for item in (data.get("last_proposed_items") or [])
                if isinstance(item, dict)
            ],
            conversation_summary=str(data.get("conversation_summary") or ""),
            task_stack=[
                {
                    "type": str(t.get("type") or ""),
                    "id": str(t.get("id") or ""),
                    "name": str(t.get("name") or ""),
                    "status": str(t.get("status") or ""),
                    "parent_id": str(t.get("parent_id") or ""),
                }
                for t in (data.get("task_stack") or [])
                if isinstance(t, dict) and t.get("id")
            ],
            linked_skills=[
                {
                    "skill_id": str(s.get("skill_id") or ""),
                    "skill_name": str(s.get("skill_name") or ""),
                    "gap": str(s.get("gap") or ""),
                    "status": str(s.get("status") or ""),
                }
                for s in (data.get("linked_skills") or [])
                if isinstance(s, dict) and (s.get("skill_id") or s.get("skill_name"))
            ],
            agents_discussed=[
                {"spec_id": str(a.get("spec_id") or ""), "spec_name": str(a.get("spec_name") or ""), "last_action": str(a.get("last_action") or "")}
                for a in (data.get("agents_discussed") or [])
                if isinstance(a, dict) and a.get("spec_id")
            ],
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )

    def ensure_timestamps(self) -> None:
        """Make sure the timestamp exists."""
        now = time.time()
        if self.created_at <= 0:
            self.created_at = now
        self.updated_at = now

    def update_intent(
        self,
        action: str = "",
        stage: str = "",
        spec_id: str = "",
        spec_name: str = "",
        intent_summary: str = "",
        active_subtask: str = "",
        next_action: str = "",
        evaluation_decision: str = "",
        evaluation_blockers: Optional[List[str]] = None,
        evaluation_categories: Optional[List[str]] = None,
        pending_options: Optional[List[Dict[str, Any]]] = None,
        pending_question: str = "",
        proposed_items: Optional[List[Dict[str, Any]]] = None,
        clear_pending_options: bool = False,
        task: Optional[Dict[str, str]] = None,
        linked_skill: Optional[Dict[str, str]] = None,
        conversation_summary: str = "",
    ) -> None:
        """Update intent context."""
        if action:
            self.action = action
        if stage:
            self.stage = stage
        if spec_id:
            self.spec_id = spec_id
        if spec_name:
            self.spec_name = spec_name
        if intent_summary:
            self.intent_summary = intent_summary
        if active_subtask:
            self.active_subtask = active_subtask
        if next_action:
            self.next_action = next_action
        if evaluation_decision:
            self.last_evaluation_decision = evaluation_decision
        if evaluation_blockers is not None:
            self.last_evaluation_blockers = evaluation_blockers
        if evaluation_categories is not None:
            self.last_evaluation_categories = evaluation_categories

        # Management of options to be confirmed
        if clear_pending_options:
            self.pending_options = []
            self.pending_question = ""
        if pending_options is not None:
            self.pending_options = [
                opt for opt in pending_options
                if isinstance(opt, dict) and opt.get("index")
            ]
            # Also save to last_proposed_items
            self.last_proposed_items = self.pending_options[-8:]
        if pending_question:
            self.pending_question = pending_question
        if proposed_items is not None:
            self.last_proposed_items = [
                item for item in proposed_items
                if isinstance(item, dict)
            ][-8:]

        if conversation_summary:
            self.conversation_summary = conversation_summary

        if task:
            self.upsert_task(
                task_type=task.get("type", ""),
                task_id=task.get("id", ""),
                name=task.get("name", ""),
                status=task.get("status", ""),
                parent_id=task.get("parent_id", ""),
            )
        if linked_skill:
            self.link_skill(
                skill_id=linked_skill.get("skill_id", ""),
                skill_name=linked_skill.get("skill_name", ""),
                gap=linked_skill.get("gap", ""),
                status=linked_skill.get("status", ""),
            )
        self.ensure_timestamps()

        # Update agents_discussed list
        if self.spec_id:
            found = False
            for a in self.agents_discussed:
                if a["spec_id"] == self.spec_id:
                    a["spec_name"] = self.spec_name
                    a["last_action"] = self.action
                    found = True
                    break
            if not found:
                self.agents_discussed.append({
                    "spec_id": self.spec_id,
                    "spec_name": self.spec_name,
                    "last_action": self.action,
                })

    def upsert_task(self, task_type: str, task_id: str, name: str = "", status: str = "", parent_id: str = "") -> None:
        """Write/update a task node in the parent-child task chain."""
        if not task_id:
            return
        item = {
            "type": str(task_type or ""),
            "id": str(task_id),
            "name": str(name or task_id),
            "status": str(status or ""),
            "parent_id": str(parent_id or ""),
        }
        for idx, existing in enumerate(self.task_stack):
            if existing.get("id") == task_id and existing.get("type") == task_type:
                self.task_stack[idx] = {**existing, **item}
                break
        else:
            self.task_stack.append(item)
        self.task_stack = self.task_stack[-12:]
        self.ensure_timestamps()

    def link_skill(self, skill_id: str, skill_name: str = "", gap: str = "", status: str = "") -> None:
        """Record which gap of the current Agent a Skill is created for."""
        if not skill_id and not skill_name:
            return
        key = skill_id or skill_name
        item = {
            "skill_id": str(skill_id or ""),
            "skill_name": str(skill_name or key),
            "gap": str(gap or ""),
            "status": str(status or ""),
        }
        for idx, existing in enumerate(self.linked_skills):
            if (existing.get("skill_id") or existing.get("skill_name")) == key:
                self.linked_skills[idx] = {**existing, **item}
                break
        else:
            self.linked_skills.append(item)
        self.linked_skills = self.linked_skills[-12:]
        self.ensure_timestamps()

    def complete_subtask(self, task_id: str, status: str = "completed", next_action: str = "") -> None:
        """Mark the subtask complete and set the next step."""
        for item in self.task_stack:
            if item.get("id") == task_id:
                item["status"] = status
        if next_action:
            self.next_action = next_action
        self.ensure_timestamps()

    def build_injection_block(self) -> str:
        """Build an intent context block that is injected into the System Prompt.

        This is the most important contextual tip for LLM.
        """
        if not self.spec_id and not self.action:
            return ""

        lines = [
            "",
            "## 🔴 Current Intent Context (SYSTEM-INJECTED — READ BEFORE ACTING)",
            "",
        ]

        if self.spec_name and self.spec_id:
            lines.extend([
                f"**current focus Agent**:  [{self.spec_name}]  (spec_id={self.spec_id}) ",
                "",
            ])

        if self.action:
            action_labels = {
                "create_agent": "create new Agent",
                "iterate_agent": "Iterate over Agent versions",
                "test_agent": "test Agent",
                "publish_agent": "publish Agent",
                "add_capability": "Add new capabilities",
                "resolve_gap": "Address capability gaps",
                "check_status": "View status",
                "general_qa": "General Q&A",
            }
            label = action_labels.get(self.action, self.action)
            lines.append(f"**current intention**: {label}")

        if self.stage:
            stage_labels = {
                "exploring": "Requirements exploration",
                "capability_check": "Ability check",
                "draft_preparing": "Draft preparation",
                "confirmation_pending": "Wait for user confirmation",
                "generating": "Generating",
                "building": "Building",
                "testing": "Testing",
                "iterating": "Iterating",
                "gap_resolving": "Gap resolution",
                "publishing": "Publishing",
                "idle": "free",
            }
            label = stage_labels.get(self.stage, self.stage)
            lines.append(f" (stage: {label}) ")

        if self.intent_summary:
            lines.append(f"**summary of intent**: {self.intent_summary}")
        if self.active_subtask:
            lines.append(f"**current subtask**: {self.active_subtask}")
        if self.next_action:
            lines.append(f"**Next action**: {self.next_action}")

        if self.task_stack:
            lines.extend(["", "### Current task chain (Agent → Gap → Skill/Test) "])
            for task in self.task_stack[-8:]:
                parent = f" ← parent={task.get('parent_id')}" if task.get("parent_id") else ""
                lines.append(
                    f"- [{task.get('type')}] {task.get('name')} ({task.get('id')}) "
                    f"status={task.get('status')}{parent}"
                )

        if self.linked_skills:
            lines.extend(["", "### Completion of Skills/Abilities associated with the current Agent"])
            for skill in self.linked_skills[-8:]:
                gap = f", Corresponding gap:{skill.get('gap')}" if skill.get("gap") else ""
                lines.append(
                    f"- {skill.get('skill_name') or skill.get('skill_id')} "
                    f"status={skill.get('status')}{gap}"
                )

        lines.append("")

        # core binding rules
        lines.extend([
            "### 🔴 CRITICAL SCOPE RULES (must be observed)",
            "",
        ])

        if self.spec_id:
            lines.append(f"- All tool calls (inspect, create, build, test, iterate) only operate spec_id={self.spec_id}")
            lines.append(f"- When users say this Agent , it and what s the progress now , they are referring to {self.spec_name}] ")
            lines.append(f"- Do not query, discuss, or operate other Agents (unless the user explicitly mentions another Agent s name)")
            lines.append(f"- Do not save other Agent information in save_memory")

        lines.extend([
            "- When the user says confirm or ok , if the current stage is confirmation_pending, the user-selected plan in pending_options must be parsed first, and then executed according to selected_plan_id; do not understand confirmation as unconditional generation",
            "- Agent The creation v2 process must be followed: Requirements Clarification → Capability inventory+gap analysis → Show direct/complete/quick/narrow alternatives → User choice plan → Generate/supplement capabilities/reduce requirements according to plan",
            "- When the user selects complete/quick, the program must be acknowledged_gaps **and gap_report_json** (prepare_agent_generation_confirmation The returned gap_report field) is also passed to generate_confirmed_candidate_agent; when the user selects narrow, it returns to the requirement clarification and does not generate Agent",
            "💡 If the gap_report_json or capability_inventory_json data is lost (truncated after multiple rounds of dialogue), just pass it empty.——The backend automatically recovers from the Workshop Session s builder_contracts and does not re-call prepare_agent_generation_confirmation due to data loss.",
            "- After gap_report and candidate_plans have been formed in the prepare stage, do not restart an independent round of gap analysis after user confirmation; it should be executed according to the user confirmation plan, and iteration after execution or test failure",
            "- Before performing any write operation (create/build/iterate/publish), you must confirm that the spec_id is consistent with the intent context",
            "- If an agent_id is not a spec_id in the intent context, reject the operation and prompt the user",
            "- If you are currently solving gaps or creating Skills for Agents, you must return to the parent Agent to continue build/test/iterate after completing the Skills. Do not regard Skills as the final goal.",
            "- When answering the progress, you must follow the task chain description: parent Agent status, current gap/skill status, next action",
            "",
            "### Option confirmation and reference resolution rules",
            "",
            "When you present multiple mutually exclusive options (solutions, tools, action paths) to the user:",
            "1. Must be presented as a numbered list, and updated IntentContext.pending_options",
            "2. Each option must have an explicit name and index (starting from 1)",
            "3. You must log pending_question: the question currently waiting for the user to answer",
            "",
            "When the user replies in the following way, it must be parsed into specific options before taking action:",
            "-  [ The first one → index=1,  [The second one→ index=2, and so on",
            "-  [That what I just said just press this → The most recently proposed option or the last of pending_options",
            "-  [A Plan Plan B → Match option.id or option.name",
            "",
            "Before calling any tool, you must first reiterate your understanding in one sentence:",
            " [What you chose is:{option.name}. I will execute this now. ",
            "If you are not sure which option the user is referring to, you must confirm with the user and do not perform guesswork.",
            "Never treat a user s brief confirmation as a new topic.",
            "",
        ])

        # Options currently awaiting confirmation
        if self.pending_options:
            lines.extend([
                "### Options currently awaiting confirmation",
                f"Question:{self.pending_question or 'Please choose from the options below'}" if self.pending_question else "",
            ])
            for opt in self.pending_options[-6:]:
                idx = opt.get("index", "?")
                name = opt.get("name") or opt.get("id") or "Unnamed"
                desc = opt.get("description") or ""
                lines.append(f"  {idx}. {name}" + (f" — {desc}" if desc else ""))
            lines.append("")

        # Summary of the previous round of dialogue (cross-round context is not lost)
        if self.conversation_summary:
            lines.extend([
                "### Summary of the last conversation",
                self.conversation_summary,
                "",
            ])

        if self.last_proposed_items and not self.pending_options:
            lines.extend([
                "### Recently proposed solutions/options (for reference for reference resolution)",
            ])
            for item in self.last_proposed_items[-4:]:
                name = item.get("name") or item.get("id") or "Unnamed"
                desc = item.get("description") or ""
                lines.append(f"  - {name}" + (f" — {desc}" if desc else ""))
            lines.append("")

        # Multi-Agent discussion history (if multiple exist)
        other_agents = [a for a in self.agents_discussed if a["spec_id"] != self.spec_id]
        if other_agents:
            lines.append(f"### ⚠️ Other Agents are also discussed in this thread (for reference only, do not operate them)")
            for a in other_agents[-5:]:  # last 5
                lines.append(f"- {a['spec_name']} ({a['spec_id']}) — Last operation: {a['last_action']}")
            lines.append("")

        return "\n".join(lines)

    def validate_action(self, proposed_spec_id: str, action_name: str) -> Optional[str]:
        """Verify that an operation is consistent with the current intent.

        Returns:
            Returns an error message if inconsistent, None if consistent.
        """
        if not self.spec_id:
            return None  # no focus → Allow any operation

        if proposed_spec_id and proposed_spec_id != self.spec_id:
            return (
                f"intention drift: The current focus Agent is {self.spec_name}]  ({self.spec_id}) , "
                f"But you try to{proposed_spec_id}] execute {action_name}. "
                f"If you do want to operate another Agent, please make this clear in the conversation first."
            )

        return None


def get_intent_context_from_thread() -> IntentContext:
    """Read the IntentContext from the current contextvar."""
    try:
        from core.tools.context import get_current_assistant_thread_context
        ctx = get_current_assistant_thread_context() or {}
        intent_data = ctx.get("intent") if isinstance(ctx, dict) else None
        return IntentContext.from_dict(intent_data)
    except Exception:
        return IntentContext()


def update_intent_context_in_thread(
    *,
    action: str = "",
    stage: str = "",
    spec_id: str = "",
    spec_name: str = "",
    intent_summary: str = "",
    active_subtask: str = "",
    next_action: str = "",
    evaluation_decision: str = "",
    evaluation_blockers: Optional[List[str]] = None,
    evaluation_categories: Optional[List[str]] = None,
    pending_options: Optional[List[Dict[str, Any]]] = None,
    pending_question: str = "",
    proposed_items: Optional[List[Dict[str, Any]]] = None,
    clear_pending_options: bool = False,
    task: Optional[Dict[str, str]] = None,
    linked_skill: Optional[Dict[str, str]] = None,
    conversation_summary: str = "",
) -> IntentContext:
    """Update the intent context of the current thread (contextvar level, effective within the current turn).

    Returns the updated IntentContext.
    """
    try:
        from core.tools.context import get_current_assistant_thread_context, set_current_assistant_thread_context
        ctx = get_current_assistant_thread_context() or {}
        intent = IntentContext.from_dict(ctx.get("intent"))
        intent.update_intent(
            action=action,
            stage=stage,
            spec_id=spec_id or intent.spec_id,
            spec_name=spec_name or intent.spec_name,
            intent_summary=intent_summary or intent.intent_summary,
            active_subtask=active_subtask,
            next_action=next_action,
            evaluation_decision=evaluation_decision,
            evaluation_blockers=evaluation_blockers,
            evaluation_categories=evaluation_categories,
            pending_options=pending_options,
            pending_question=pending_question,
            proposed_items=proposed_items,
            clear_pending_options=clear_pending_options,
            task=task,
            linked_skill=linked_skill,
            conversation_summary=conversation_summary,
        )
        ctx["intent"] = intent.to_dict()
        # Synchronize top-level fields and be compatible with existing front-end/tool filtering logic
        if intent.spec_id:
            ctx["spec_id"] = intent.spec_id
        if intent.spec_name:
            ctx["spec_name"] = intent.spec_name
        # When the stage enters building/testing, clear the has_blocking_gaps flag
        #  (quick plan The gap has been confirmed accepted and should no longer trigger the GAP_RESOLVING fallback)
        if stage in ("building", "testing", "ready_to_build"):
            ctx.pop("has_blocking_gaps", None)
        set_current_assistant_thread_context(ctx)
        logger.info(
            "[IntentContext][Update] action=%s stage=%s spec_id=%s spec_name=%s pending_options=%d",
            action, stage, spec_id, spec_name, len(intent.pending_options),
        )
        # 🔒 Write to module-level storage (isolated by thread_id, replaces unstable contextvar)
        try:
            from core.tools.context import set_latest_nanobot_intent
            set_latest_nanobot_intent(intent.to_dict())
        except Exception:
            pass
        return intent
    except Exception as exc:
        logger.warning("[IntentContext][Update] failed: %s", exc)
        return IntentContext()


def update_evaluation_evidence_in_thread(
    *,
    decision: str = "",
    blockers: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
) -> IntentContext:
    """Updates the last evaluation evidence to the intent context."""
    try:
        from core.tools.context import get_current_assistant_thread_context, set_current_assistant_thread_context
        ctx = get_current_assistant_thread_context() or {}
        intent = IntentContext.from_dict(ctx.get("intent"))
        intent.update_intent(
            evaluation_decision=decision,
            evaluation_blockers=blockers,
            evaluation_categories=categories,
        )
        ctx["intent"] = intent.to_dict()
        set_current_assistant_thread_context(ctx)
        logger.info(
            "[IntentContext][EvalEvidence] decision=%s categories=%s blockers=%d",
            decision, categories, len(blockers or []),
        )
        return intent
    except Exception as exc:
        logger.warning("[IntentContext][EvalEvidence] failed: %s", exc)
        return IntentContext()
