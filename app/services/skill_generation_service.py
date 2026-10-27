"""
Skill Build service — business logic layer

Encapsulates each module in core/tools/external/ to handle MongoDB persistence and asynchronous orchestration.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.llm import Message
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.tools.external import (
    ConversationRound,
    DefaultReconnaissanceController,
    ExpectedOutput,
    ImplementationFactReport,
    IterationController,
    RequirementAnalyzer,
    SkillCreationSession,
    SkillHandoffContext,
    SkillParameter,
    SkillSpec,
    SessionStatus,
    PipelineResult,
)
from core.tools.external.requirement_analyzer import classify_requirement_mode

logger = logging.getLogger("webapi")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_CODE_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "code" / "skill"

# MongoDB Collection name
SESSION_COLLECTION = "skill_creation_sessions"
SKILL_COLLECTION = "external_skills"
# Consistent with iteration_controller.MAX_ITERATIONS; if you need to adjust it, please modify it simultaneously.
SKILL_PIPELINE_MAX_ITERATIONS = 10
SKILL_GENERATION_AGENTIC_ENABLED = os.getenv("SKILL_GENERATION_AGENTIC_ENABLED", "true").lower() not in {"0", "false", "no", "off"}


class SkillGenerationService:
    """
    Skill Build service

    Provides complete business logic for demand communication, code generation, and skill management.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        reasoning_llm_client=None,
        coding_llm_client=None,
        quick_llm_client=None,
        provider: str = "deepseek",
        model: Optional[str] = None,
    ):
        """
        Args:
            db: MongoDB database
            reasoning_llm_client: For requirements analysis (large model for deep reasoning), specification generation and other heavy reasoning steps
            coding_llm_client: For code generation (large programming model), code generation and Judge scoring
            quick_llm_client: Used for demand dialogue (quick model), clarity/boundary/multi-round reply and other low-latency links
            provider, model: Used for fallback, used when all the above clients are empty.
        """
        self._db = db
        self._provider = provider
        self._model = model
        self._analyzer = RequirementAnalyzer(
            llm_client=reasoning_llm_client,
            provider=provider,
            model=model,
            quick_llm_client=quick_llm_client,
        )
        self._reconnaissance = DefaultReconnaissanceController(
            llm_client=coding_llm_client, provider=provider, model=model,
            analyzer=self._analyzer,
        )
        self._controller = IterationController(
            llm_client=coding_llm_client,
            provider=provider,
            model=model,
            max_iterations=SKILL_PIPELINE_MAX_ITERATIONS,
            reconnaissance_controller=self._reconnaissance,
            quick_llm_client=quick_llm_client,
        )

    def _build_session_recommendations(
        self,
        *,
        spec: Optional[SkillSpec] = None,
        session: Optional[SkillCreationSession] = None,
        fact_report: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if spec is not None:
            return self._analyzer.build_recommendations(spec=spec, fact_report=fact_report)
        conversation = ""
        if session is not None:
            conversation = self._analyzer._collect_conversation(session)
        return self._analyzer.build_recommendations(conversation=conversation, fact_report=fact_report)

    @staticmethod
    def _dedupe_text_list(items: Any) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        if not isinstance(items, list):
            return result
        for item in items:
            value = str(item or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    async def _search_capability_index(self, spec: SkillSpec) -> list:
        """Search the capabilities index (Qdrant vector library) for tools related to spec semantics.

        using spec display_name + description Construct query, recall top_k=12 related tools.
        If the capability index service is unavailable, an empty list is returned (does not block the process).
        """
        try:
            from app.services.capability_index_service import CapabilityIndexService
            # Construct semantic query text
            query_parts = [
                spec.display_name or "",
                spec.description or "",
                spec.category or "",
            ]
            # Add parameter description to make the search more accurate
            for param in (spec.parameters or []):
                desc = getattr(param, "description", None) or (param.get("description") if isinstance(param, dict) else None)
                if desc:
                    query_parts.append(desc)
            query = " ".join(p for p in query_parts if p).strip()
            if not query:
                return []

            svc = CapabilityIndexService(self._db)
            hits = await svc.search_capabilities(
                query=query,
                top_k=12,
                bindable_only=True,
                source_types=["builtin_tool", "mcp_tool"],
            )
            logger.info(
                "🧭 Capability Index Vector Search: query='%s...' → %d hit",
                query[:40],
                len(hits),
            )
            return hits
        except Exception as exc:
            logger.warning("⚠️ Capability index search failed (does not block the process): %s", exc)
            return []

    @staticmethod
    def _infer_skill_role_metadata(spec: SkillSpec, session: SkillCreationSession) -> Dict[str, Any]:
        text = " ".join([
            spec.tool_id or "",
            spec.display_name or "",
            spec.description or "",
            spec.category or "",
            spec.data_source or "",
            " ".join(spec.constraints or []),
            " ".join(spec.expected_output.fields or []),
            spec.expected_output.description or "",
            str((spec.metadata or {}).get("handoff_context_summary") or ""),
            str((spec.metadata or {}).get("generation_context") or ""),
        ]).lower()
        handoff = session.handoff_context
        source = str(getattr(handoff, "source", "") or "") if handoff is not None else ""
        source_capability = str(getattr(handoff, "target_capability", "") or "") if handoff is not None else ""
        if source_capability:
            text += " " + source_capability.lower()

        capability_tags: List[str] = []
        tag_patterns = [
            (r"cash flow|cash\s*flow|cashflow|ocf|fcf|cfo|free cash flow", "cashflow_quality"),
            (r"financial health|debt repayment|Liabilities|debt|solvency|liquidity|current_ratio|interest_coverage", "financial_health"),
            (r"risk|risk|early warning|Abnormal|goodwill|receivable|goodwill|receivable", "financial_risk"),
            (r"Valuation|valuation|pe|pb|percentile|Quantile|dcf|peg", "valuation"),
            (r"Trend|trend|series|history|many years|time_series", "historical_series"),
            (r"quality|quality|roe|roa|roic|piotroski|altman|beneish", "quality_factor"),
            (r"technology|technical|macd|rsi|kdj|ma20", "technical"),
            (r"News|news|public opinion|sentiment", "news_sentiment"),
        ]
        for pattern, tag in tag_patterns:
            if re.search(pattern, text):
                capability_tags.append(tag)

        output_fields = [str(item or "").lower() for item in (spec.expected_output.fields or [])]
        output_type = str(spec.expected_output.type or "").lower()
        if output_type in {"dict", "list[dict]", "list"} and output_fields:
            if any(re.search(r"ratio|rate|score|metrics?|indicator|Ratio|score|flag", field) for field in output_fields):
                output_shape = "structured_metrics"
            else:
                output_shape = "structured_records"
        elif "markdown" in text or "报告" in text or "report" in text:
            output_shape = "report"
        else:
            output_shape = "structured_records" if output_fields else "text"

        preferred_for: List[str] = []
        if "financial_risk" in capability_tags:
            preferred_for.append("financial_risk_signal_detection")
        if "cashflow_quality" in capability_tags:
            preferred_for.append("cashflow_quality_analysis")
        if "financial_health" in capability_tags:
            preferred_for.append("financial_health_analysis")
        if "valuation" in capability_tags:
            preferred_for.append("valuation_analysis")
        if "historical_series" in capability_tags:
            preferred_for.append("historical_trend_analysis")

        if source in {"agent_studio_gap", "agent_workshop_gap"}:
            tool_role_hint = "specialized"
        elif output_shape == "report":
            tool_role_hint = "supporting"
        elif len(preferred_for) == 1:
            tool_role_hint = "specialized"
        elif preferred_for:
            tool_role_hint = "specialized"
        else:
            tool_role_hint = "supporting"

        not_replacement_for: List[str] = []
        if tool_role_hint in {"supporting", "generic", "fallback"}:
            not_replacement_for.extend(preferred_for)
        if output_shape == "report":
            not_replacement_for.extend(["structured_metric_calculation", "primary_capability"])

        return {
            "capability_tags": SkillGenerationService._dedupe_text_list(capability_tags),
            "tool_role_hint": tool_role_hint,
            "output_shape": output_shape,
            "preferred_for": SkillGenerationService._dedupe_text_list(preferred_for),
            "not_replacement_for": SkillGenerationService._dedupe_text_list(not_replacement_for),
        }

    @staticmethod
    def _get_last_generated_code(pipeline_result: Optional[PipelineResult]) -> str:
        if not pipeline_result:
            return ""
        if pipeline_result.final_code:
            return pipeline_result.final_code
        for iteration in reversed(pipeline_result.iterations or []):
            generated = iteration.generated_code
            if generated and generated.code:
                return generated.code
        return ""

    @staticmethod
    def _persist_generated_code_snapshots(
        *,
        session_id: str,
        tool_id: str,
        attempt_number: int,
        pipeline_result: Optional[PipelineResult],
    ) -> List[Path]:
        if not pipeline_result:
            return []

        session_dir = SKILL_CODE_SNAPSHOT_DIR / tool_id / session_id
        attempt_dir = session_dir / f"attempt_{attempt_number:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        written_files: List[Path] = []

        for iteration in pipeline_result.iterations or []:
            generated = iteration.generated_code
            code = (generated.code if generated and generated.code else "").strip()
            if not code:
                continue

            round_path = attempt_dir / f"round_{iteration.round_number:02d}.py"
            round_path.write_text(code + "\n", encoding="utf-8")
            written_files.append(round_path)

        latest_code = SkillGenerationService._get_last_generated_code(pipeline_result).strip()
        if latest_code:
            attempt_latest_path = attempt_dir / "latest.py"
            attempt_latest_path.write_text(latest_code + "\n", encoding="utf-8")
            written_files.append(attempt_latest_path)

            session_latest_path = session_dir / "latest.py"
            session_latest_path.write_text(latest_code + "\n", encoding="utf-8")
            written_files.append(session_latest_path)

        return written_files

    @staticmethod
    def _summarize_text(
        text: Any,
        *,
        max_chars: int,
        head_chars: Optional[int] = None,
        separator: str = "\n... (Omit the middle) ...\n",
    ) -> str:
        """Long text summaries keep the beginning and the end by default to avoid misjudgment caused by only seeing the first half."""
        if text is None:
            return ""

        text_str = str(text)
        if len(text_str) <= max_chars:
            return text_str

        if head_chars is None:
            head_chars = max_chars // 2

        head_chars = max(1, min(head_chars, max_chars - len(separator) - 1))
        tail_chars = max_chars - head_chars - len(separator)
        if tail_chars <= 0:
            return text_str[:max_chars]

        return text_str[:head_chars] + separator + text_str[-tail_chars:]

    @staticmethod
    def _format_single_pipeline(
        pipeline_result: PipelineResult,
        label: str = "",
        compact: bool = False,
    ) -> List[str]:
        """
        Format single-shot pipeline results into a structured list of text lines.

        Args:
            compact: True When only retaining root cause analysis and scoring, omit stdout/stderr/feedback
                     Equally large volume field, used to compress historical pipelines.
        """
        parts: List[str] = []
        if label:
            parts.append(f"\n{'='*20} {label} {'='*20}")
        if pipeline_result.error:
            parts.append(f"Final conclusion:{pipeline_result.error}")

        for iteration in pipeline_result.iterations or []:
            parts.append(f"\n[第{iteration.round_number}轮 | 决策={iteration.decision or 'UNKNOWN'}]")

            if iteration.validation and iteration.validation.errors:
                parts.append("Static validation issues:")
                parts.extend(f"- {item}" for item in iteration.validation.errors[:3])

            if iteration.sandbox and not iteration.sandbox.success:
                parts.append(f"Sandbox execution failed:{iteration.sandbox.error or 'unknown error'}")

            if not compact and iteration.sandbox and iteration.sandbox.success and iteration.sandbox.output is not None:
                import json as _json
                try:
                    out_str = SkillGenerationService._summarize_text(
                        _json.dumps(iteration.sandbox.output, ensure_ascii=False, default=str),
                        max_chars=1200,
                        head_chars=700,
                    )
                except Exception:
                    out_str = SkillGenerationService._summarize_text(
                        iteration.sandbox.output,
                        max_chars=1200,
                        head_chars=700,
                    )
                parts.append(f"Sandbox return value (summary):{out_str}")

            if iteration.eval_score:
                parts.append(
                    "Assessment score:"
                    f"total={iteration.eval_score.total}, "
                    f"executability={iteration.eval_score.executability}, "
                    f"authenticity={iteration.eval_score.authenticity}, "
                    f"completeness={iteration.eval_score.completeness}, "
                    f"relevance={iteration.eval_score.relevance}, "
                    f"format_quality={iteration.eval_score.format_quality}"
                )

            if iteration.reflection and iteration.reflection.root_cause:
                parts.append(f"Root cause analysis:{iteration.reflection.root_cause}")
                if iteration.reflection.fix_plan:
                    parts.append("Repair plan:" + " → ".join(iteration.reflection.fix_plan[:5]))

            if not compact and iteration.feedback:
                feedback_excerpt = SkillGenerationService._summarize_text(
                    iteration.feedback,
                    max_chars=1200,
                    head_chars=700,
                )
                parts.append(f"System feedback (summary):{feedback_excerpt}")

        return parts

    @staticmethod
    def _extract_lessons(results: List[PipelineResult]) -> List[str]:
        """Key lessons for extracting duplicates from pipeline result lists."""
        lessons: List[str] = []
        for pr in results:
            for it in pr.iterations or []:
                if it.reflection and it.reflection.root_cause:
                    lessons.append(it.reflection.root_cause)
        return list(dict.fromkeys(lessons))[:15]

    @staticmethod
    def _build_pipeline_failure_feedback(
        pipeline_result: Optional[PipelineResult],
        user_feedback: str = "",
    ) -> str:
        if not pipeline_result:
            return user_feedback.strip()

        parts: List[str] = ["=== Last round of pipeline failure information ==="]
        parts.extend(
            SkillGenerationService._format_single_pipeline(pipeline_result, compact=False)
        )

        if user_feedback.strip():
            parts.append(f"\n=== User s additional correction comments ===\n{user_feedback.strip()}")

        return "\n".join(parts)

    # Token budget for experience feedback (press 1 Chinese character ≈ 2 token estimate,8K token ≈ 4K characters)
    _EXPERIENCE_CHAR_BUDGET = 6000

    @staticmethod
    def _build_accumulated_experience(
        pipeline_history: List[PipelineResult],
        current_pipeline: Optional[PipelineResult],
        user_feedback: str = "",
    ) -> str:
        """
        Build cumulative experience feedback — Progressive compression strategy:

        1. Most recent pipeline: full details (stdout/return value/feedback)
        2. Older pipeline: only root cause analysis and scoring (compact mode)
        3. Summary of all lessons learned with deduplication
        4. If still over budget, start cropping from oldest history
        """
        history = list(pipeline_history or [])
        all_results = list(history)
        if current_pipeline is not None:
            all_results.append(current_pipeline)

        if not all_results:
            return user_feedback.strip()

        budget = SkillGenerationService._EXPERIENCE_CHAR_BUDGET
        parts: List[str] = [
            f"=== 累积生成经验（共 {len(all_results)} 次尝试）===",
            "Please learn from the lessons of history and avoid making the same mistakes again.\n",
        ]

        # ---- Summary of key lessons learned (always retained, highest priority)----
        lessons = SkillGenerationService._extract_lessons(all_results)
        if lessons:
            parts.append(f"=== 关键教训总结（{len(lessons)} 条，必须遵守）===")
            for i, lesson in enumerate(lessons, 1):
                parts.append(f"{i}. {lesson}")
            parts.append("")

        # ---- Most recent pipeline: full details ----
        latest = all_results[-1]
        success_label = "✅ 成功" if latest.success else "❌ 失败"
        latest_label = f"最近一次尝试（第 {len(all_results)} 次, {latest.total_rounds} 轮, {latest.total_time}s, {success_label}）"
        latest_lines = SkillGenerationService._format_single_pipeline(latest, latest_label, compact=False)
        parts.extend(latest_lines)

        # ---- Earlier pipeline: compact mode, filling from latest to earliest ----
        older = all_results[:-1]
        if older:
            parts.append(f"\n=== 更早的 {len(older)} 次尝试（摘要）===")

            current_len = sum(len(p) for p in parts)
            remaining = budget - current_len - 300  # Reserve tail space

            included = 0
            for pr in reversed(older):
                idx = older.index(pr) + 1
                s_label = "✅" if pr.success else "❌"
                pr_label = f"第 {idx} 次（{pr.total_rounds} 轮, {s_label}）"
                pr_lines = SkillGenerationService._format_single_pipeline(pr, pr_label, compact=True)
                block = "\n".join(pr_lines)
                if current_len + len(block) > remaining and included > 0:
                    parts.append(f"（更早的 {len(older) - included} 次尝试因篇幅省略，教训已汇总在上方）")
                    break
                parts.extend(pr_lines)
                current_len += len(block)
                included += 1

        if user_feedback.strip():
            parts.append(f"\n=== Users additional comments in this round ===\n{user_feedback.strip()}")

        parts.append("\n=== 要求 ===")
        parts.append("Please combine the above lessons to avoid repeating previous mistakes, make targeted repairs, and generate high-quality code.")

        return "\n".join(parts)

    @staticmethod
    def _build_repair_plan_fallback(
        spec: SkillSpec,
        feedback: str,
        pipeline_feedback: str,
    ) -> str:
        return "\n".join([
            "## 我理解到的问题",
            f"- The current goal of Skill is still:{spec.description}",
            f"- The new issues you highlighted are:{feedback.strip() or 'Please correct the failure message'}",
            "- I will give priority to fixing the deterministic errors that have been exposed in the static verification, sandbox execution and scoring phases, and will not change the confirmed requirement boundaries.",
            "",
            "## 修正计划",
            "1. First, locate the root cause of the failure based on the previous round of failure information, and prioritize the elimination of problems that block execution.",
            "2. Preserve existing skill specifications and target outputs to avoid extending the revision process into new requirements.",
            "3. Directly modify based on the previous round of code instead of regenerating it from scratch.",
            "4. Explicitly return error / invalid in scenarios where key inputs or key data are missing, to avoid using forged default values to continue output.",
            "5. After correction, it re-passed static verification, sandbox execution and quality assessment.",
            "",
            "## Important things to check when regenerating",
            pipeline_feedback.strip() or "- Repairs are made one by one, focusing on static verification, sandboxing and evaluation errors in the previous round of failed sessions.",
            "",
            "If there is no deviation from this plan, please confirm and let me regenerate according to this plan.",
        ])

    def _generate_repair_plan_message(
        self,
        session: SkillCreationSession,
        feedback: str,
    ) -> Tuple[str, Optional[Any]]:
        """
        Generate correction plan messages.

        Returns:
            (ai_message, llm_response) — llm_response May be None (no specification or fallback scheme).
            llm_response Used by asynchronous callers to record tokens to avoid calling asynchronous methods in a synchronous context.
        """
        spec = session.spec
        if not spec:
            return "There are no Skill specifications available for the current session and a remediation plan cannot be generated.", None

        accumulated_exp = self._build_accumulated_experience(
            pipeline_history=session.pipeline_history,
            current_pipeline=session.pipeline_result,
            user_feedback=feedback,
        )
        pipeline_feedback = self._build_pipeline_failure_feedback(
            session.pipeline_result,
            feedback,
        )
        last_code = self._get_last_generated_code(session.pipeline_result)
        code_excerpt = self._summarize_text(
            last_code,
            max_chars=12000,
            head_chars=7000,
        )
        attempt_count = len(session.pipeline_history) + (1 if session.pipeline_result else 0)
        prompt = f"""
你现在是 Skill 生成失败后的修正协作者。该 Skill 已经经过 {attempt_count} 次生成尝试，均未达标。
先不要输出代码，而是先向用户说明：
1. 从所有历史尝试中你总结出的关键问题是什么
2. 你准备怎么修（避免重复之前犯过的错误）
3. 重新生成时会重点检查什么

请严格遵守：
- 不要重新定义需求，不要扩展到新的功能范围
- 不要输出完整代码
- 不要承诺无法验证的内容
- 用中文回答
- 输出结构固定为：
  ## 历史尝试中的关键问题
  ## 修正计划
  ## 重新生成时的重点检查项

=== 当前 Skill 规格 ===
tool_id: {spec.tool_id}
display_name: {spec.display_name}
description: {spec.description}
category: {spec.category}
data_source: {spec.data_source}
test_input: {spec.test_input}

=== 累积经验（共 {attempt_count} 次尝试）===
{accumulated_exp}

=== 最近一次生成的代码（摘要，保留首尾） ===
{code_excerpt or '无'}

请给出一份让用户可以确认的修正计划。
""".strip()

        try:
            client = self._analyzer._get_client()
            response = client.chat([Message(role="user", content=prompt)])
            content = (getattr(response, "content", "") or "").strip()
            if content:
                return content, response
        except Exception as e:
            logger.warning(f"Failed to generate correction plan, use fallback plan: {e}")

        return self._build_repair_plan_fallback(spec, feedback, pipeline_feedback), None

    async def _launch_pipeline_task(
        self,
        *,
        session: SkillCreationSession,
        spec: SkillSpec,
        initial_feedback: str = "",
        initial_code: str = "",
        fact_report: Optional[ImplementationFactReport] = None,
        codegen_timeout: Optional[int] = None,
        iteration_mode: str = "repair",
    ) -> Dict[str, Any]:
        # Code generation single call timeout (seconds): None Use pipeline default; only accepted 60~1800 integer
        if isinstance(codegen_timeout, bool) or not isinstance(codegen_timeout, int):
            codegen_timeout = None
        elif not (60 <= codegen_timeout <= 1800):
            codegen_timeout = None

        # external_api Mode: Inject the interface preflight measured facts (connectivity/real fields/measured query parameters)
        # spec.metadata, Code generation prompt constructs the [Interface Measured Facts] block based on this——
        # LLM No more imaginary return fields, no more business filtering parameters (such as brand) URL
        try:
            if classify_requirement_mode(spec) == "external_api":
                sess_doc = await self._db[SESSION_COLLECTION].find_one(
                    {"session_id": session.session_id}, {"interface_preflight": 1}
                )
                preflight = (sess_doc or {}).get("interface_preflight")
                if preflight:
                    metadata = dict(getattr(spec, "metadata", None) or {})
                    metadata["interface_preflight"] = preflight
                    spec.metadata = metadata
                    logger.info(
                        "[Preflight] Interface measured facts are injected into code generation: status=%s data_items=%s fields=%s probed_params=%s",
                        preflight.get("status"),
                        preflight.get("data_items"),
                        preflight.get("sample_fields"),
                        list((preflight.get("probed_params") or {}).keys()),
                    )
        except Exception as exc:
            logger.debug("[Preflight] Measured fact injection code generation failed (ignored): %s", exc)

        session.status = SessionStatus.GENERATING
        if session.pipeline_result is not None:
            session.pipeline_history.append(session.pipeline_result)
        session.pipeline_result = None
        attempt_number = len(session.pipeline_history) + 1
        await self._save_session(session)
        await self._db[SESSION_COLLECTION].update_one(
            {"session_id": session.session_id},
            {
                "$set": {
                    "pipeline_stage": "code_generation",
                    "pipeline_message": "准备开始生成...",
                    "pipeline_iteration": 0,
                    "pipeline_progress": 0,
                    "pipeline_thinking": "",
                    "pipeline_eval_result": None,
                    "pipeline_details": [],
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        from app.core.database import get_mongo_db_sync
        sync_db = get_mongo_db_sync()
        session_id = session.session_id

        def _progress_cb(stage: str, message: str, iteration: int, progress: float,
                         extra: Optional[Dict[str, Any]] = None):
            try:
                detail_event: Dict[str, Any] = {
                    "stage": stage,
                    "message": message,
                    "iteration": iteration,
                    "progress": progress,
                    "timestamp": datetime.utcnow(),
                }
                set_fields: Dict[str, Any] = {
                    "pipeline_stage": stage,
                    "pipeline_message": message,
                    "pipeline_iteration": iteration,
                    "pipeline_progress": progress,
                    "updated_at": datetime.utcnow(),
                }
                # Quality assessment completed: structured results are logged into the database in real time, and scores/comments can be seen through front-end polling
                eval_result = (extra or {}).get("eval_result")
                if eval_result:
                    detail_event["eval_result"] = eval_result
                    set_fields["pipeline_eval_result"] = eval_result

                sync_db[SESSION_COLLECTION].update_one(
                    {"session_id": session_id},
                    {
                        "$set": set_fields,
                        "$push": {
                            "pipeline_details": {
                                "$each": [detail_event],
                                "$slice": -30,
                            }
                        },
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to update pipeline progress: {e}")

        # Real-time display of the thinking process: buffering reasoning increments, throttling writing of session documents (front-end polling reading)
        thinking_state = {"buf": "", "last_flush": 0.0}
        THINKING_FLUSH_INTERVAL = 1.5   # seconds
        THINKING_DOC_TAIL = 6000        # Only the tail is retained in the document to prevent unlimited growth

        def _flush_thinking() -> None:
            try:
                sync_db[SESSION_COLLECTION].update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "pipeline_thinking": thinking_state["buf"][-THINKING_DOC_TAIL:],
                        "updated_at": datetime.utcnow(),
                    }},
                )
            except Exception as e:
                logger.warning(f"Writing to pipeline_thinking failed: {e}")

        def _thinking_cb(kind: str, text: str):
            try:
                import time as _time
                if kind == "reset":
                    thinking_state["buf"] = ""
                    thinking_state["last_flush"] = _time.time()
                    _flush_thinking()
                    return
                if kind != "reasoning" or not text:
                    return
                thinking_state["buf"] = (thinking_state["buf"] + text)[-THINKING_DOC_TAIL * 2:]
                now = _time.time()
                if now - thinking_state["last_flush"] >= THINKING_FLUSH_INTERVAL:
                    thinking_state["last_flush"] = now
                    _flush_thinking()
            except Exception as e:
                logger.warning(f"Update pipeline_thinking failed: {e}")

        async def _run_pipeline():
            try:
                # mem0: Recall the historical lessons of similar skills and inject them into initial_feedback
                enriched_feedback = initial_feedback
                try:
                    mem0_lessons = await _recall_skill_lessons(self._db, spec)
                    if mem0_lessons:
                        enriched_feedback = (
                            f"{mem0_lessons}\n\n{initial_feedback}" if initial_feedback
                            else mem0_lessons
                        )
                        metadata = dict(getattr(spec, "metadata", None) or {})
                        metadata["cross_session_skill_lessons"] = mem0_lessons[:2000]
                        spec.metadata = metadata
                except Exception as e:
                    logger.debug("[mem0] Skill Lesson recall failed (ignored): %s", e)

                # Capture fact_report into local variables to avoid lambda closure issues
                _fr = fact_report
                method_name = "run_agentic" if SKILL_GENERATION_AGENTIC_ENABLED else "run"
                logger.info("Skill Build engine: %s", method_name)
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: getattr(self._controller, method_name)(
                        spec,
                        initial_feedback=enriched_feedback,
                        initial_code=initial_code,
                        progress_callback=_progress_cb,
                        fact_report=_fr,
                        codegen_timeout=codegen_timeout,
                        thinking_callback=_thinking_cb,
                        iteration_mode=iteration_mode,
                    ),
                )
                # After the flow ends, flush the remaining thinking content to avoid tail loss.
                _flush_thinking()
                session.status = SessionStatus.COMPLETED if result.success else SessionStatus.FAILED
                session.pipeline_result = result
                await self._save_session(session)

                try:
                    written_files = self._persist_generated_code_snapshots(
                        session_id=session.session_id,
                        tool_id=spec.tool_id,
                        attempt_number=attempt_number,
                        pipeline_result=result,
                    )
                    if written_files:
                        logger.info(
                            "📝 Skill Code snapshot saved: %s",
                            str((SKILL_CODE_SNAPSHOT_DIR / spec.tool_id / session.session_id).resolve()),
                        )
                except Exception as e:
                    logger.warning("⚠️ Failed to save skill code snapshot: %s", e)

                if result.success:
                    await self._save_skill(session, spec, result)

                # mem0: Write the lessons learned from this iteration into memory
                try:
                    await _store_skill_lessons(self._db, spec, result)
                except Exception as e:
                    logger.debug("[mem0] Skill Lesson storage failed (ignored): %s", e)
            except Exception as e:
                logger.error(f"管线执行异常: {e}", exc_info=True)
                await self._db[SESSION_COLLECTION].update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "status": "failed",
                            "pipeline_stage": "error",
                            "pipeline_message": str(e),
                            "updated_at": datetime.utcnow(),
                        },
                        "$push": {
                            "pipeline_details": {
                                "$each": [{
                                    "stage": "error",
                                    "message": str(e),
                                    "iteration": 0,
                                    "progress": 0,
                                    "timestamp": datetime.utcnow(),
                                }],
                                "$slice": -30,
                            }
                        },
                    },
                )

        asyncio.create_task(_run_pipeline())

        return {
            "status": "generating",
            "session_id": session_id,
            "skill_id": None,
            "spec": spec.model_dump() if spec else None,
            "success": False,
            "total_rounds": 0,
            "total_time": 0,
            "final_score": None,
            "error": None,
        }

    @staticmethod
    def _apply_handoff_context_to_spec(spec: SkillSpec, handoff_context: Any) -> None:
        """Attach the upstream handoff context to SkillSpec.metadata for use by Agentic Loop."""
        if spec is None or handoff_context is None:
            return
        metadata = dict(getattr(spec, "metadata", None) or {})

        def _string_list(field: str, limit: int) -> List[str]:
            return [
                str(item).strip()
                for item in list(getattr(handoff_context, field, None) or [])
                if str(item).strip()
            ][:limit]

        context_summary = {
            "source": str(getattr(handoff_context, "source", "") or ""),
            "source_spec_id": str(getattr(handoff_context, "source_spec_id", "") or getattr(handoff_context, "spec_id", "") or ""),
            "source_name": str(getattr(handoff_context, "source_name", "") or getattr(handoff_context, "agent_name", "") or ""),
            "target_capability": str(getattr(handoff_context, "target_capability", "") or ""),
            "handoff_intent": str(getattr(handoff_context, "handoff_intent", "") or ""),
            "workshop_session_id": str(getattr(handoff_context, "workshop_session_id", "") or ""),
            "gap_id": str(getattr(handoff_context, "gap_id", "") or ""),
            "agent_goal": str(getattr(handoff_context, "agent_goal", "") or ""),
            "gap_context": str(getattr(handoff_context, "gap_context", "") or ""),
            "searched_capabilities": _string_list("searched_capabilities", 12),
            "confirmed_data_sources": _string_list("confirmed_data_sources", 12),
            "user_clarifications": _string_list("user_clarifications", 12),
            "related_gaps": _string_list("related_gaps", 12),
        }
        context_summary = {
            key: value for key, value in context_summary.items()
            if value not in ("", [], None)
        }
        if context_summary:
            metadata["handoff_context_summary"] = context_summary

        failures = _string_list("known_failure_summaries", 5)
        facts = _string_list("known_verified_facts", 12)
        if failures:
            metadata["known_failure_summaries"] = failures
        if facts:
            metadata["known_verified_facts"] = facts
        if context_summary or failures or facts:
            logger.info(
                "[SkillGeneration][HandoffContext] tool_id=%s context_keys=%s known_failures=%s known_facts=%s",
                getattr(spec, "tool_id", ""),
                sorted(context_summary.keys()),
                len(metadata.get("known_failure_summaries") or []),
                len(metadata.get("known_verified_facts") or []),
            )
        spec.metadata = metadata

    @staticmethod
    def _has_generation_context(context: Optional[Dict[str, Any]]) -> bool:
        if not context:
            return False
        return bool(
            context.get("category_hint")
            or context.get("data_source_hint")
            or context.get("stock_collections")
            or context.get("external_sources")
        )

    def _build_spec_from_skill_doc(self, doc: Dict[str, Any]) -> Optional[SkillSpec]:
        try:
            params = [SkillParameter(**p) for p in doc.get("parameters", [])]
            expected_output_data = doc.get("expected_output", {})
            expected_output = ExpectedOutput(**expected_output_data) if expected_output_data else ExpectedOutput()
            return SkillSpec(
                tool_id=doc.get("tool_id", ""),
                display_name=doc.get("display_name", ""),
                description=doc.get("description", ""),
                category=doc.get("category", "other"),
                data_source=doc.get("data_source", ""),
                parameters=params,
                expected_output=expected_output,
                test_input=doc.get("test_input", {}),
            )
        except Exception:
            return None

    async def _hydrate_skill_generation_context(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        context = doc.get("generation_context")
        if self._has_generation_context(context):
            return doc

        metadata = dict(doc.get("metadata") or {})
        metadata_context = metadata.get("generation_context")
        if self._has_generation_context(metadata_context):
            doc["generation_context"] = metadata_context
            return doc

        recommendations: Optional[Dict[str, Any]] = None
        session_id = doc.get("session_id")
        if session_id:
            session = await self._load_session(session_id)
            if session:
                spec = session.spec if isinstance(session.spec, SkillSpec) else None
                recommendations = self._build_session_recommendations(spec=spec, session=session)

        if not self._has_generation_context(recommendations):
            spec = self._build_spec_from_skill_doc(doc)
            if spec is not None:
                recommendations = self._build_session_recommendations(spec=spec)

        if self._has_generation_context(recommendations):
            doc["generation_context"] = recommendations

        return doc

    # ==================== Requirements communication ====================

    async def start_session(
        self,
        description: str,
        user_id: str = "",
        handoff_context: Optional[Dict[str, Any]] = None,
        iterate_skill_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Start creating a session: Submit initial requirements

        Args:
            description: User requirement description
            user_id: User ID
            handoff_context: Handover context from upstream workshop
            iterate_skill_id: Existing in iteration mode Skill tool_id

        Returns:
            contains session_id, ai_message, clarity_level Waiting for information dict
        """
        # Create session
        context = SkillHandoffContext(**handoff_context) if handoff_context else None
        session = self._analyzer.create_session(
            user_id=user_id, handoff_context=context, iterate_skill_id=iterate_skill_id,
        )

        # Iterative mode: load the context of an existing Skill
        skill_context: Optional[str] = None
        if iterate_skill_id:
            try:
                skill_doc = await self._db[SKILL_COLLECTION].find_one(
                    {"tool_id": iterate_skill_id}
                )
                if skill_doc:
                    skill_doc.pop("_id", None)
                    code = skill_doc.get("code") or skill_doc.get("implementation") or ""
                    skill_context = json.dumps({
                        "tool_id": skill_doc.get("tool_id", ""),
                        "display_name": skill_doc.get("display_name", ""),
                        "description": skill_doc.get("description", ""),
                        "category": skill_doc.get("category", ""),
                        "parameters": skill_doc.get("parameters", []),
                        "status": skill_doc.get("status", ""),
                        "code_abbreviated": code[:1500] + ("..." if len(code) > 1500 else ""),
                    }, ensure_ascii=False, indent=2)
                    logger.info(
                        "[SkillGeneration][Iterate] Load an existing Skill context: tool_id=%s",
                        iterate_skill_id,
                    )
                else:
                    logger.warning(
                        "[SkillGeneration][Iterate] not found Skill: tool_id=%s",
                        iterate_skill_id,
                    )
            except Exception as exc:
                logger.error("[SkillGeneration][Iterate] Failed to load skill: %s", exc)

        # Process the first round of input (will do clarity evaluation and boundary detection)
        session, ai_message = await asyncio.get_event_loop().run_in_executor(
            None,
            self._analyzer.process_user_input,
            session,
            description,
            skill_context,  # Pass in existing Skill context in iterative mode
        )

        # persist to MongoDB
        session_doc = session.model_dump(mode="json")
        await self._db[SESSION_COLLECTION].insert_one(session_doc)

        max_rounds = self._analyzer._get_max_rounds(session.clarity_level)

        return {
            "session_id": session.session_id,
            "ai_message": ai_message,
            "clarity_level": session.clarity_level.value if session.clarity_level else "medium",
            "boundary_check": session.boundary_check.model_dump() if session.boundary_check else None,
            "current_round": session.current_round,
            "expected_rounds": max_rounds,
        }

    async def respond_to_session(
        self, session_id: str, user_message: str
    ) -> Dict[str, Any]:
        """
        User reply conversation turn

        Returns:
            contains ai_message, current_round, is_final_round Waiting for information dict
        """
        # Load session from MongoDB
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        if session.spec_confirmed:
            raise ValueError("The specifications have been confirmed and the conversation cannot be continued.")

        # Handle user input
        session, ai_message = await asyncio.get_event_loop().run_in_executor(
            None, self._analyzer.process_user_input, session, user_message
        )

        # update MongoDB
        await self._save_session(session)

        max_rounds = self._analyzer._get_max_rounds(session.clarity_level)

        return {
            "session_id": session.session_id,
            "ai_message": ai_message,
            "current_round": session.current_round,
            "expected_rounds": max_rounds,
            "is_final_round": session.current_round >= max_rounds,
            "boundary_check": session.boundary_check.model_dump() if session.boundary_check else None,
        }

    async def _inherit_parent_interface_constraints(
        self, spec: SkillSpec, parent_tool_id: str
    ) -> bool:
        """Iteration mode: Inherit interface specification constraints (including URL constraints) from the parent Skill.

        Background: There is no original requirement text in the dialogue of the upgrade session, and the URL generated by the specification is extracted.
        Unable to obtain the interface address, causing the new version spec to lose the interface contract——Confirmation page appears
         [ Interface URL not recognized warning, the URL will be forged during the code generation phase.
        Source priority: constraints field of parent Skill (new version has been persisted);
        Older versions fall back to extracting the interface URL from the parent code.
        """
        url_re = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")

        def _base_urls(text: str) -> set:
            return {
                m.group(0).split("?")[0].rstrip(".,;:")
                for m in url_re.finditer(text or "")
            }

        try:
            parent = await self._db[SKILL_COLLECTION].find_one(
                {"tool_id": parent_tool_id},
                {"constraints": 1, "code": 1, "session_id": 1},
            )
        except Exception as exc:
            logger.warning("[Iterate] Failed to load parent Skill (interface constraint inheritance skipped): %s", exc)
            return False
        if not parent:
            return False

        # Source priority:
        # 1) The constraints field of the parent Skill (_save_skill has been persisted and the new version of the skill is available)
        # 2) spec.constraints of the parent Skill source session (older version skills also have complete interface constraint lines)
        # 3) Extract the interface URL from the parent code (finally, multi-level paths are required to exclude pure domain names such as Referer)
        interface_lines = [
            str(c) for c in (parent.get("constraints") or []) if url_re.search(str(c))
        ]
        if not interface_lines:
            origin_session_id = parent.get("session_id")
            if origin_session_id:
                try:
                    origin_sess = await self._db[SESSION_COLLECTION].find_one(
                        {"session_id": origin_session_id}, {"spec.constraints": 1}
                    )
                except Exception as exc:
                    logger.debug("[Iterate] Failed to load parent session: %s", exc)
                    origin_sess = None
                if origin_sess and origin_sess.get("spec"):
                    interface_lines = [
                        str(c)
                        for c in ((origin_sess["spec"] or {}).get("constraints") or [])
                        if url_re.search(str(c))
                    ]
        if not interface_lines:
            urls = [
                u
                for u in _base_urls(parent.get("code") or "")
                # At least 2 levels of path after the domain name (such as /motor/pc/car/rank_data),
                # Exclude Referer references of pure domain names and single-level paths
                if len([s for s in u.split("//", 1)[-1].split("/") if s]) >= 3
            ]
            interface_lines = [
                f"【接口规格 — 必须原样使用】接口 URL: {u}（继承自父版本 {parent_tool_id}，"
                "It is strictly prohibited to rewrite the path/parameter name. For example, rank_data must not be written as rank/data;"
                "URL The query parameters in are only examples, and parameters are passed as function parameters during implementation)"
                for u in urls
            ]
        if not interface_lines:
            return False

        existing = _base_urls("\n".join(str(c) for c in (spec.constraints or [])))
        added = False
        for line in interface_lines:
            line_urls = _base_urls(line)
            if line_urls and not (line_urls & existing):
                spec.constraints.insert(0, line)
                existing |= line_urls
                added = True
        if added:
            logger.info(
                "[Iterate] Inherited the interface specification constraints of the parent version (parent=%s)", parent_tool_id
            )
        return added

    async def _load_parent_skill_code(self, parent_tool_id: str) -> str:
        """Iteration mode: Load the complete verified code of the parent version as the upgrade baseline.

        Background: Upgrades are usually just small adjustments such as adding fields/parameters. The human approach is to change a few lines of the original code.
        If there is no parent code, the first round of generation will be rewritten from scratch, which is wasteful and will lose the parent version. It took many rounds of iterations to fix it.
        Details (pagination/retries/local filtering/field mapping, etc.).
        """
        try:
            parent = await self._db[SKILL_COLLECTION].find_one(
                {"tool_id": parent_tool_id},
                {"code": 1, "implementation": 1, "status": 1},
            )
        except Exception as exc:
            logger.warning("[Iterate] Failed to load parent Skill code (handled as generated from scratch): %s", exc)
            return ""
        if not parent:
            logger.warning("[Iterate] Parent not found Skill: tool_id=%s", parent_tool_id)
            return ""
        code = parent.get("code") or parent.get("implementation") or ""
        if code:
            logger.info(
                "[Iterate] Parent version code loaded as upgrade baseline: parent=%s chars=%d status=%s",
                parent_tool_id, len(code), parent.get("status"),
            )
        return code

    async def _load_parent_skill_contract(
        self, parent_tool_id: str
    ) -> Optional[Dict[str, Any]]:
        """Iteration mode: load the parent version of the complete contract (parameters/constraints/output/complete code)+ Calculate the new version number.

        Source of truth for upgrade patch mode: spec generation LLM reads it to locate change points, patch is applied
        Unmentioned fields are inherited from it as is. Version number query has the same logic as _save_skill.
        Ensure that spec.tool_id is consistent with the final library during the generation period (codegen function name/
        Static verification is aligned according to tool_id, and subsequent changes will invalidate the entire round).
        """
        try:
            parent = await self._db[SKILL_COLLECTION].find_one(
                {"tool_id": parent_tool_id}
            )
        except Exception as exc:
            logger.warning("[Iterate] Failed to load parent Skill contract: %s", exc)
            return None
        if not parent:
            logger.warning("[Iterate] Parent Skill not found (contract loading): tool_id=%s", parent_tool_id)
            return None

        root_tool_id = parent.get("parent_skill_id") or parent_tool_id
        # The maximum version number in the series (including the root version), consistent with the version calculation of _save_skill
        new_version = 2
        try:
            cursor = (
                self._db[SKILL_COLLECTION]
                .find({"$or": [{"tool_id": root_tool_id}, {"parent_skill_id": root_tool_id}]})
                .sort("version", -1)
                .limit(1)
            )
            max_docs = await cursor.to_list(1)
            if max_docs:
                new_version = int(max_docs[0].get("version") or 1) + 1
        except Exception as exc:
            logger.warning("[Iterate] Failed to query the series version number, use the default v2: %s", exc)

        contract = {
            "tool_id": parent.get("tool_id") or parent_tool_id,
            "root_tool_id": root_tool_id,
            "new_tool_id": f"{root_tool_id}_v{new_version}",
            "new_version": new_version,
            "display_name": parent.get("display_name") or "",
            "description": parent.get("description") or "",
            "category": parent.get("category") or "utility",
            "data_source": parent.get("data_source") or "",
            "parameters": list(parent.get("parameters") or []),
            "expected_output": dict(parent.get("expected_output") or {}),
            "constraints": list(parent.get("constraints") or []),
            "test_input": dict(parent.get("test_input") or {}),
            "code": parent.get("code") or parent.get("implementation") or "",
        }
        logger.info(
            "[Iterate] Parent version contract loaded (patch mode base): parent=%s root=%s next=%s "
            "params=%d constraints=%d code_chars=%d",
            contract["tool_id"], root_tool_id, contract["new_tool_id"],
            len(contract["parameters"]), len(contract["constraints"]),
            len(contract["code"]),
        )
        return contract

    async def _preflight_external_interface(
        self, spec: SkillSpec, parent_code: str = ""
    ) -> Optional[Dict[str, Any]]:
        """external_api Mode: Really call the interface in the sandbox to do connectivity pre-check.

        During the specification confirmation stage, URL error/interface unreachable/parameter problem was discovered.
        Avoid waiting for code generation (2-4 minutes per round) before sandbox execution is exposed.

        parent_code: Upgrade the parent version code of the scene——When there is only a bare URL (no query string) in the constraint,
        Extract the parent code s validated query parameters (such as count/offset) from it as a preflight baseline,
        Prevent new spec parameters (such as limit) from being misjudged as interface available parameters.
        """
        from core.tools.external.interface_preflight import (
            build_interface_probe,
            interpret_probe_result,
        )
        from core.tools.external.sandbox_runner import SandboxRunner

        probe = build_interface_probe(spec, parent_code=parent_code)
        if probe is None:
            return None
        runner = SandboxRunner(timeout=25)
        sandbox = await asyncio.get_event_loop().run_in_executor(
            None, lambda: runner.run(probe["code"], spec, test_input=probe["params"])
        )
        verdict = interpret_probe_result(sandbox)
        verdict["url"] = probe["url"]
        # Available query parameters verified by actual testing = Baseline parameters (user URL documented query parameters).
        # The suspected business filtering parameters (such as brand_name) fall into
        # ignored_params (ignored→Local filtering)/server_filter_params (server filtering takes effect)
        baseline = probe.get("baseline_params") or {}
        if baseline:
            verdict["probed_params"] = dict(baseline)
        verdict["checked_at"] = datetime.utcnow().isoformat()
        logger.info(
            "[Preflight] External interface preflight tool_id=%s url=%s status=%s message=%s",
            spec.tool_id,
            probe["url"],
            verdict.get("status"),
            verdict.get("message"),
        )
        return verdict

    async def preview_spec(
        self, session_id: str, user_message: str = "确认"
    ) -> Optional[Dict[str, Any]]:
        """
        Only a SkillSpec preview is generated, the session state is not modified.
        Used to demonstrate specification confirmation steps.

        Process: First generate a draft spec → run recon → Regenerate enriched spec based on recon facts.
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        # Iteration mode: Load the parent version contract, and use the upgrade patch mode for specification generation (parent contract + delta) 
        parent_contract = None
        if session.iterate_skill_id:
            parent_contract = await self._load_parent_skill_contract(
                session.iterate_skill_id
            )

        # First pass: Generate draft spec (no recon facts)
        draft_spec = await asyncio.get_event_loop().run_in_executor(
            None, self._analyzer.preview_spec, session, user_message, None, parent_contract
        )
        if not draft_spec:
            return None

        # Vector Search: Tools for Recalling Semantic Relevance from Capability Indexes Using Spec Descriptions
        capability_hits = await self._search_capability_index(draft_spec)

        # Run reconnaissance layer: detect real data availability based on draft spec (with vector search results)
        fact_report = await asyncio.get_event_loop().run_in_executor(
            None, self._reconnaissance.analyze, draft_spec, capability_hits
        )
        logger.info("🧭 Reconnaissance completed (preview), Confidence: %.0f%%", fact_report.confidence * 100)

        # Second pass: Regenerate enriched spec based on recon facts.
        # Only executed when scouting output field-level empirical facts and not in external_api mode——
        # external_api Pattern reconnaissance does not detect external interfaces, and the report content is static guidance derived from the pattern.
        #  (The field list is still copied from the draft), and there is no substantial difference between the secondary generation input and the draft.
        # It only costs one more LLM call (about 5 minutes under the thinking model).
        enriched_spec = None
        if (
            classify_requirement_mode(draft_spec) != "external_api"
            and fact_report.has_spec_grounding_facts
        ):
            enriched_spec = await asyncio.get_event_loop().run_in_executor(
                None, self._analyzer.preview_spec, session, user_message, fact_report,
                parent_contract,
            )
        final_spec = enriched_spec or draft_spec

        # Cache spec and fact_report to session and reuse them directly when confirm_spec.
        # Avoid calling LLM generation specs again causing the front end to stay at 0% for a long time.
        session.spec = final_spec
        self._apply_handoff_context_to_spec(session.spec, session.handoff_context)
        # Iteration mode: inherit the parent version interface specification constraints (including URL), and the confirmation page will no longer appear
        # ""Interface URL not recognized" warning, code generation does not lose the interface contract
        if session.iterate_skill_id:
            await self._inherit_parent_interface_constraints(
                session.spec, session.iterate_skill_id
            )
        session.fact_report = fact_report
        await self._save_session(session)

        # External interface pre-check: Really call the interface in the sandbox to verify connectivity, and the results are displayed on the confirmation page
        interface_preflight = None
        if classify_requirement_mode(session.spec) == "external_api":
            # Upgrade scenario: with parent code, the preflight baseline inherits the verified query parameters of the parent version
            preview_parent_code = ""
            if session.iterate_skill_id:
                preview_parent_code = await self._load_parent_skill_code(session.iterate_skill_id)
            try:
                interface_preflight = await self._preflight_external_interface(
                    session.spec, parent_code=preview_parent_code
                )
            except Exception as exc:
                logger.warning("[Preflight] Interface preflight failed (no blocking confirmation): %s", exc)
            if interface_preflight is not None:
                try:
                    await self._db[SESSION_COLLECTION].update_one(
                        {"session_id": session.session_id},
                        {"$set": {"interface_preflight": interface_preflight}},
                    )
                except Exception as exc:
                    logger.warning("[Preflight] The pre-check result failed to be dropped into the database.: %s", exc)

        return {
            "spec": final_spec.model_dump(),
            "recommendations": self._build_session_recommendations(spec=final_spec, fact_report=fact_report),
            "fact_report": fact_report.model_dump() if fact_report else None,
            "interface_preflight": interface_preflight,
            # List of change points in the upgrade patch mode (diff-style display on the confirmation page: what has been changed, the rest will be inherited)
            "upgrade_change_points": (
                (final_spec.metadata or {}).get("upgrade_change_points")
                if parent_contract else None
            ),
        }

    async def confirm_spec(
        self, session_id: str, user_message: str = "确认", codegen_timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Confirm specs and trigger code generation

        Process: Reuse the fact_report cached in the preview stage, and conduct on-site reconnaissance if there is none.
        Inject fact_report into spec generation and pipeline execution at the same time to achieve"reconnaissance→Make rules→generate"Closed loop.

        Args:
            session_id: session ID
            user_message: Confirm message
            codegen_timeout: Code generation single LLM call timeout (seconds), None uses the default value

        Returns:
            contains status, spec, generation_result Waiting for information dict
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        # Reuse the fact_report cached in the preview stage. If there is none, run reconnaissance first.
        fact_report = session.fact_report
        if fact_report is None:
            # Need to generate draft spec first for reconnaissance
            draft_parent_contract = (
                await self._load_parent_skill_contract(session.iterate_skill_id)
                if session.iterate_skill_id else None
            )
            draft_spec = await asyncio.get_event_loop().run_in_executor(
                None, self._analyzer.preview_spec, session, user_message,
                None, draft_parent_contract,
            )
            if draft_spec:
                # Vector search: Recalling semantically related tools from capability indexes
                capability_hits = await self._search_capability_index(draft_spec)
                fact_report = await asyncio.get_event_loop().run_in_executor(
                    None, self._reconnaissance.analyze, draft_spec, capability_hits
                )
                logger.info("🧭 Reconnaissance completed (confirm), Confidence: %.0f%%", fact_report.confidence * 100)

        # If the specification has been cached in the preview stage and is currently only regular"Confirm", 
        # Then reuse it directly to avoid calling LLM again to generate SkillSpec when confirming.
        normalized_message = (user_message or "").strip()
        can_reuse_preview_spec = bool(
            session.spec
            and fact_report is not None
            and normalized_message in ("", "确认", "确认生成", "继续生成")
        )

        if can_reuse_preview_spec:
            spec = session.spec
            session.spec_confirmed = True
            session.status = SessionStatus.CONFIRMED
            session.updated_at = datetime.utcnow()
            await self._save_session(session)
        else:
            # Generate the final SkillSpec based on the reconnaissance facts (iteration mode with parent contract in patch mode)
            confirm_parent_contract = (
                await self._load_parent_skill_contract(session.iterate_skill_id)
                if session.iterate_skill_id else None
            )
            session, spec = await asyncio.get_event_loop().run_in_executor(
                None, self._analyzer.confirm_spec, session, user_message, fact_report,
                confirm_parent_contract,
            )

        if not spec:
            return {
                "status": "failed",
                "message": "Specification generation failed, please describe the requirements again",
            }

        self._apply_handoff_context_to_spec(spec, session.handoff_context)

        # Iteration mode: inherit the parent version interface specification constraints (including URL)——preview Cache reuse path
        # We must also be careful to prevent the upgraded version from losing the interface contract, resulting in fictitious code generation. URL
        if session.iterate_skill_id and await self._inherit_parent_interface_constraints(
            spec, session.iterate_skill_id
        ):
            session.spec = spec
            await self._save_session(session)

        # Iteration mode: Load parent version code in advance (preflight baseline parameters + Pipeline upgrade baselines are shared to avoid repeated library checks)
        parent_code = ""
        if session.iterate_skill_id:
            parent_code = await self._load_parent_skill_code(session.iterate_skill_id)

        # External interface preflight interception: prevent code generation when the interface is clearly unavailable (unreachable/4xx/5xx),
        # Avoid burning through 2-4 minutes/round of builds only to discover interface issues in the sandbox.
        # preview Cached results are reused; run now when confirmed directly (skip preview).
        if classify_requirement_mode(spec) == "external_api":
            preflight = None
            try:
                sess_doc = await self._db[SESSION_COLLECTION].find_one(
                    {"session_id": session_id}, {"interface_preflight": 1}
                )
                preflight = (sess_doc or {}).get("interface_preflight")
            except Exception:
                preflight = None
            if preflight is None:
                try:
                    preflight = await self._preflight_external_interface(
                        spec, parent_code=parent_code
                    )
                except Exception as exc:
                    logger.warning("[Preflight] Confirmation phase pre-inspection failed (release): %s", exc)
                if preflight is not None:
                    try:
                        await self._db[SESSION_COLLECTION].update_one(
                            {"session_id": session_id},
                            {"$set": {"interface_preflight": preflight}},
                        )
                    except Exception:
                        pass
            if preflight and preflight.get("status") == "failed":
                return {
                    "status": "failed",
                    "message": (
                        f"The external interface preflight failed and code generation has been blocked:{preflight.get('message')}. "
                        "Please correct the interface specifications (URL/request headers/parameters) and reconfirm."
                    ),
                    "interface_preflight": preflight,
                }

        # Iteration mode: The parent version code is used as the upgrade baseline (small change scenarios to avoid rewriting from scratch)
        iteration_mode = "upgrade" if parent_code else "repair"

        # fact_report Also passed to the pipeline, skipping internal repeated reconnaissance
        return await self._launch_pipeline_task(
            session=session, spec=spec, fact_report=fact_report,
            codegen_timeout=codegen_timeout,
            initial_code=parent_code,
            iteration_mode=iteration_mode,
        )

    async def repair_session(
        self,
        session_id: str,
        feedback: str,
        repair_plan: str = "",
        codegen_timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Re-correct and generate based on the current failed session.

        Use all accumulated historical pipeline experience + Users additional comments serve as the initial feedback for a new round,
        Make sure the LLM learns from each previous attempt rather than just seeing the latest failure.
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        if not session.spec_confirmed or not session.spec:
            raise ValueError("The current session has not confirmed the specifications and cannot enter correction mode.")
        if session.status != SessionStatus.FAILED:
            raise ValueError("Only failed creation sessions can be confirmed and rerun.")

        merged_feedback = feedback.strip()
        if repair_plan.strip():
            merged_feedback = (
                f"{merged_feedback}\n\n=== Confirmed correction plan ===\n{repair_plan.strip()}"
            )

        attempt_count = len(session.pipeline_history) + (1 if session.pipeline_result else 0)
        session.rounds.append(ConversationRound(
            round_number=len(session.rounds) + 1,
            user_message=f"[修正] {feedback}",
            ai_message=(
                f"已确认修正计划，结合前 {attempt_count} 次经验重新生成..."
                if repair_plan.strip() else
                f"已接收修正意见，结合前 {attempt_count} 次经验重新生成..."
            ),
        ))

        initial_feedback = self._build_accumulated_experience(
            pipeline_history=session.pipeline_history,
            current_pipeline=session.pipeline_result,
            user_feedback=merged_feedback,
        )
        initial_code = self._get_last_generated_code(session.pipeline_result)

        return await self._launch_pipeline_task(
            session=session,
            spec=session.spec,
            initial_feedback=initial_feedback,
            initial_code=initial_code,
            codegen_timeout=codegen_timeout,
        )

    async def preview_repair_session(
        self,
        session_id: str,
        feedback: str,
    ) -> Dict[str, Any]:
        """
        First generate an AI correction plan and wait for user confirmation before running again.
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        if not session.spec_confirmed or not session.spec:
            raise ValueError("The current session has not confirmed the specifications and cannot generate a correction plan.")
        if session.status != SessionStatus.FAILED:
            raise ValueError("Only failed creation sessions can generate remediation plans first")

        ai_message, repair_llm_response = await asyncio.get_event_loop().run_in_executor(
            None,
            self._generate_repair_plan_message,
            session,
            feedback,
        )

        # Logging token usage (LLM calls are done in synchronous methods, here they are logged in their asynchronous callers)
        try:
            if repair_llm_response is not None:
                from app.services.usage_statistics_service import usage_statistics_service
                await usage_statistics_service.record_llm_usage(
                    response=repair_llm_response,
                    session_id=session_id,
                    analysis_type="skill_generation",
                )
        except Exception as e:
            logger.warning(f"Record token usage failure: {e}")

        session.rounds.append(ConversationRound(
            round_number=len(session.rounds) + 1,
            user_message=f"[修正讨论] {feedback}",
            ai_message=ai_message,
        ))
        await self._save_session(session)

        return {
            "status": "repair-planned",
            "session_id": session_id,
            "ai_message": ai_message,
        }

    # ==================== Skill management ====================

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话详情"""
        doc = await self._db[SESSION_COLLECTION].find_one({"session_id": session_id})
        if not doc:
            return None
        doc.pop("_id", None)
        try:
            session = SkillCreationSession(**doc)
            spec = session.spec if isinstance(session.spec, SkillSpec) else None
            doc["recommendations"] = self._build_session_recommendations(spec=spec, session=session)
        except Exception:
            rounds = doc.get("rounds", []) or []
            conversation = "\n\n".join(
                f"[用户 - 第{item.get('round_number', '?')}轮]: {item.get('user_message', '')}\n"
                f"[AI - No.{item.get('round_number', '?')}wheel]: {item.get('ai_message', '')}"
                for item in rounds
            )
            doc["recommendations"] = self._analyzer.build_recommendations(conversation=conversation)
        return doc

    async def list_sessions(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List creation sessions (draft/incomplete)"""
        query: Dict[str, Any] = {}
        if status:
            # Supports comma separated multiple states:gathering,confirmed
            statuses = [s.strip() for s in status.split(",")]
            query["status"] = {"$in": statuses}
        if user_id:
            query["user_id"] = user_id

        total = await self._db[SESSION_COLLECTION].count_documents(query)
        skip = (page - 1) * page_size

        sessions = []
        cursor = (
            self._db[SESSION_COLLECTION]
            .find(query)
            .sort("updated_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        async for doc in cursor:
            doc.pop("_id", None)
            try:
                session = SkillCreationSession(**doc)
                spec = session.spec if isinstance(session.spec, SkillSpec) else None
                doc["recommendations"] = self._build_session_recommendations(spec=spec, session=session)
            except Exception:
                rounds = doc.get("rounds", []) or []
                conversation = "\n\n".join(
                    f"[用户 - 第{item.get('round_number', '?')}轮]: {item.get('user_message', '')}\n"
                    f"[AI - No.{item.get('round_number', '?')}wheel]: {item.get('ai_message', '')}"
                    for item in rounds
                )
                doc["recommendations"] = self._analyzer.build_recommendations(conversation=conversation)
            sessions.append(doc)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": sessions,
        }

    async def delete_session(self, session_id: str) -> bool:
        """删除草稿会话"""
        result = await self._db[SESSION_COLLECTION].delete_one({"session_id": session_id})
        return result.deleted_count > 0

    async def list_skills(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List external skills (paginated)"""
        query: Dict[str, Any] = {}
        if category:
            query["category"] = category
        if status:
            query["status"] = status
        if source:
            clean_source = str(source or "").strip()
            if clean_source == "agent_studio_auto_gap_resolution":
                query["origin_source"] = clean_source
            elif clean_source == "manual_or_other":
                query["origin_source"] = {"$ne": "agent_studio_auto_gap_resolution"}
            else:
                query["source"] = clean_source

        logger.info(
            "[SkillGeneration][ListSkills] start source=%s category=%s status=%s page=%s page_size=%s query=%s",
            source or "-",
            category or "-",
            status or "-",
            page,
            page_size,
            query,
        )

        total = await self._db[SKILL_COLLECTION].count_documents(query)
        skip = (page - 1) * page_size

        skills = []
        cursor = (
            self._db[SKILL_COLLECTION]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        async for doc in cursor:
            doc.pop("_id", None)
            doc = await self._hydrate_skill_generation_context(doc)
            doc["used_by_agents"] = await self._find_skill_agent_usage(str(doc.get("tool_id") or ""))
            skills.append(doc)

        logger.info(
            "[SkillGeneration][ListSkills] done source=%s total=%s returned=%s",
            source or "-",
            total,
            len(skills),
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": skills,
        }

    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """获取 Skill 详情"""
        clean_skill_id = str(skill_id or "").strip()
        logger.info(
            "[SkillGeneration][GetSkill] start skill_id=%s",
            clean_skill_id or "-",
        )
        doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": clean_skill_id})
        if not doc:
            logger.info("[SkillGeneration][GetSkill] not_found skill_id=%s", clean_skill_id or "-")
            return None
        doc.pop("_id", None)
        doc = await self._hydrate_skill_generation_context(doc)
        doc["used_by_agents"] = await self._find_skill_agent_usage(str(doc.get("tool_id") or ""))
        logger.info(
            "[SkillGeneration][GetSkill] done skill_id=%s status=%s source=%s origin_source=%s",
            clean_skill_id or "-",
            doc.get("status", ""),
            doc.get("source", ""),
            doc.get("origin_source", ""),
        )
        return doc

    async def _find_skill_agent_usage(self, skill_id: str) -> List[Dict[str, Any]]:
        """Check which Agent versions the Skill is used by."""
        clean_skill_id = str(skill_id or "").strip()
        if not clean_skill_id:
            return []

        try:
            cursor = self._db["agent_versions"].find(
                {"required_tools": clean_skill_id},
                {
                    "_id": 0,
                    "version_id": 1,
                    "spec_id": 1,
                    "version": 1,
                    "status": 1,
                    "agent_metadata": 1,
                    "published_from_session_id": 1,
                    "updated_at": 1,
                },
            ).sort("updated_at", -1).limit(20)
            docs = await cursor.to_list(length=20)
        except Exception as exc:
            logger.debug("[SkillGeneration][AgentUsage] query failed skill_id=%s err=%s", clean_skill_id, exc)
            return []

        usage: List[Dict[str, Any]] = []
        for doc in docs or []:
            metadata = doc.get("agent_metadata") if isinstance(doc.get("agent_metadata"), dict) else {}
            usage.append({
                "version_id": str(doc.get("version_id") or ""),
                "spec_id": str(doc.get("spec_id") or ""),
                "version": doc.get("version"),
                "status": str(doc.get("status") or ""),
                "agent_name": str(metadata.get("name") or metadata.get("agent_name") or ""),
                "published_from_session_id": str(doc.get("published_from_session_id") or ""),
                "updated_at": str(doc.get("updated_at") or ""),
            })

        logger.info(
            "[SkillGeneration][AgentUsage] done skill_id=%s agents=%s",
            clean_skill_id,
            len(usage),
        )
        return usage

    async def get_skill_code(self, skill_id: str) -> Optional[str]:
        """获取 Skill 源代码"""
        doc = await self._db[SKILL_COLLECTION].find_one(
            {"tool_id": skill_id}, {"code": 1}
        )
        if not doc:
            return None
        return doc.get("code", "")

    async def get_skill_history(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Skill full communication history: original creation session + All optimization sessions

        Returns:
            {
                "skill_id": "...",
                "sections": [
                    { "type": "creation", "label": "Create", "session_id": "...", "rounds": [...], "created_at": "..." },
                    { "type": "optimize", "label": "Optimize v2", "session_id": "...", "rounds": [...], "created_at": "...", "feedback": "..." },
                    ...
                ]
            }
        """
        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            return None

        sections = []

        # original create session
        original_session_id = skill_doc.get("session_id", "")
        if original_session_id:
            session = await self.get_session(original_session_id)
            if session:
                sections.append({
                    "type": "creation",
                    "label": "初始创建",
                    "session_id": original_session_id,
                    "rounds": session.get("rounds", []),
                    "created_at": session.get("created_at", ""),
                })

        # All optimization sessions
        optimize_ids = skill_doc.get("optimize_session_ids", [])
        # Backward compatibility: if only the old optimize_session_id field
        legacy_id = skill_doc.get("optimize_session_id", "")
        if legacy_id and legacy_id not in optimize_ids:
            optimize_ids = [legacy_id] + optimize_ids

        for idx, opt_sid in enumerate(optimize_ids):
            session = await self.get_session(opt_sid)
            if session:
                version_label = f"优化 v{idx + 2}"
                # Extract optimization feedback from rounds
                feedback = ""
                rounds = session.get("rounds", [])
                if rounds:
                    first_msg = rounds[0].get("user_message", "")
                    if first_msg.startswith("[优化] "):
                        feedback = first_msg[len("[优化] "):]
                sections.append({
                    "type": "optimize",
                    "label": version_label,
                    "session_id": opt_sid,
                    "rounds": rounds,
                    "created_at": session.get("created_at", ""),
                    "feedback": feedback,
                })

        return {
            "skill_id": skill_id,
            "display_name": skill_doc.get("display_name", ""),
            "sections": sections,
        }

    async def update_skill_status(
        self, skill_id: str, new_status: str
    ) -> bool:
        """Update Skill status (active / disabled / archived) and synchronize the runtime ToolRegistry."""
        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            return False

        result = await self._db[SKILL_COLLECTION].update_one(
            {"tool_id": skill_id},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow().isoformat()}},
        )

        try:
            from core.tools.registry import get_tool_registry
            registry = get_tool_registry()
            if new_status == "active":
                from core.tools.external_skill_loader import register_single_external_skill
                skill_doc["status"] = new_status
                register_single_external_skill(None, registry, skill_doc)
            else:
                registry.unregister(skill_id)
        except Exception as e:
            logger.warning(f"⚠️ Skill '{skill_id}' 运行时状态同步失败: {e}")

        return result.modified_count > 0

    async def update_skill_info(
        self, skill_id: str, display_name: str, description: str
    ) -> bool:
        """Update the display name and function description of the Skill (manually edited by the user).

        Only these two display fields are allowed to be changed——Parameters/code/constraints belong to the verified contract,
        To change, please use iterative optimization to generate a new version. Sync runtime after update ToolRegistry
         (The name/description is part of the ToolMetadata) and capability index.
        """
        clean_name = str(display_name or "").strip()
        clean_desc = str(description or "").strip()
        if not clean_name:
            raise ValueError("Skill 名称不能为空")

        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            return False

        await self._db[SKILL_COLLECTION].update_one(
            {"tool_id": skill_id},
            {
                "$set": {
                    "display_name": clean_name,
                    "description": clean_desc,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
        )

        # Synchronous runtime registration (re-register with updated documentation, ToolMetadata name/description refreshed)
        try:
            from core.tools.registry import get_tool_registry
            from core.tools.external_skill_loader import register_single_external_skill

            skill_doc["display_name"] = clean_name
            skill_doc["description"] = clean_desc
            skill_doc["status"] = skill_doc.get("status", "active")
            register_single_external_skill(None, get_tool_registry(), skill_doc)
        except Exception as e:
            logger.warning(f"⚠️ Skill '{skill_id}' Description Runtime synchronization failed after update: {e}")

        # Capability index contains name/description, refreshed asynchronously
        try:
            from app.services.capability_index_service import CapabilityIndexService
            asyncio.create_task(CapabilityIndexService(self._db).ensure_index())
        except Exception as e:
            logger.warning(f"⚠️ Skill '{skill_id}' 能力索引刷新失败: {e}")

        return True

    async def delete_skill(self, skill_id: str) -> bool:
        """Remove the skill and clean up the runtime registration and tool bindings."""
        result = await self._db[SKILL_COLLECTION].delete_one({"tool_id": skill_id})
        if result.deleted_count:
            await self._db.tool_agent_bindings.delete_many({"tool_id": skill_id})
            try:
                from core.tools.registry import get_tool_registry
                get_tool_registry().unregister(skill_id)
            except Exception as e:
                logger.warning(f"⚠️ Skill '{skill_id}' 运行时注销失败: {e}")
        return result.deleted_count > 0

    async def test_skill(
        self, skill_id: str, test_args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """手动测试 Skill"""
        doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not doc:
            raise ValueError(f"Skill {skill_id} 不存在")

        code = doc.get("code", "")
        if not code:
            raise ValueError("Skill 没有代码")

        # 🔬 Write the code to be executed to the log
        logger.info(f"🔬 [test_skill] About to be executed skill={skill_id}, code_len={len(code)}\n" + code)

        # Execute using SandboxRunner
        from core.tools.external import SandboxRunner, SkillSpec

        # 🔬 Printed from the front end test_args
        logger.info(f"🔬 [test_skill] original test_args={test_args}")

        # Filter out unfilled parameters (None/empty string) and let the function default value take effect.
        # Note that 0/False is a legal input parameter (such as offset=0) , It cannot be deleted as falsy.
        if test_args:
            test_args = {k: v for k, v in test_args.items() if v is not None and v != ''}
            logger.info(f"🔬 [test_skill] After filtering test_args={test_args}")

        runner = SandboxRunner()
        # Build a simple spec for testing
        spec = SkillSpec(
            tool_id=doc["tool_id"],
            display_name=doc.get("display_name", ""),
            description=doc.get("description", ""),
            test_input=test_args or doc.get("test_input", {}),
        )
        sandbox_result = runner.run(code, spec)

        # Write the stdout/stderr of the child process to the webapi log
        if sandbox_result.stdout:
            for line in sandbox_result.stdout.split("\n"):
                line = line.strip()
                if line:
                    logger.info(f"📦 [Skill Test sandbox stdout] {line}")
        if sandbox_result.stderr:
            for line in sandbox_result.stderr.split("\n"):
                line = line.strip()
                if line:
                    logger.warning(f"📦 [Skill Test sandbox stderr] {line}")

        return {
            "success": sandbox_result.success,
            "output": sandbox_result.output,
            "stdout": sandbox_result.stdout,
            "stderr": sandbox_result.stderr,
            "execution_time": sandbox_result.execution_time,
            "error": sandbox_result.error,
        }

    async def optimize_skill(
        self, skill_id: str, feedback: str
    ) -> Dict[str, Any]:
        """
        Optimize existing skills: regenerate code based on user feedback

        Process:
        1. Load existing Skill and original Session
        2. convert original conversation + current code + User feedback Synthesize new context
        3. Create a new Session to record the optimization process
        4. Execute code generation pipeline
        5. If successful, the Skill code will be updated and the optimized version number will be saved.
        """
        # Load existing Skill
        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            raise ValueError(f"Skill {skill_id} 不存在")

        # Load the original session (get the original communication record and spec)
        original_session_id = skill_doc.get("session_id", "")
        original_session = None
        if original_session_id:
            original_session = await self.get_session(original_session_id)

        # rebuild SkillSpec
        params = [SkillParameter(**p) for p in skill_doc.get("parameters", [])]
        expected_output_data = skill_doc.get("expected_output", {})
        expected_output = ExpectedOutput(**expected_output_data) if expected_output_data else ExpectedOutput()

        spec = SkillSpec(
            tool_id=skill_doc["tool_id"],
            display_name=skill_doc.get("display_name", ""),
            description=skill_doc.get("description", ""),
            category=skill_doc.get("category", "other"),
            data_source=skill_doc.get("data_source", ""),
            parameters=params,
            expected_output=expected_output,
            test_input=skill_doc.get("test_input", {}),
        )

        # Constructing Augmented Feedback: Raw Conversation Summaries + current code + User feedback
        enhanced_feedback = self._build_optimization_feedback(
            original_session=original_session,
            current_code=skill_doc.get("code", ""),
            user_feedback=feedback,
        )

        # Create optimization Session
        optimize_session = self._analyzer.create_session(
            user_id=skill_doc.get("user_id", "")
        )
        optimize_session.status = SessionStatus.GENERATING
        optimize_session.rounds.append(ConversationRound(
            round_number=1,
            user_message=f"[优化] {feedback}",
            ai_message="Start optimizing Skill...",
        ))
        optimize_session.spec = spec
        optimize_session.spec_confirmed = True
        await self._save_session(optimize_session)

        # Execute code generation pipeline (with feedback and previous_code)
        current_code = skill_doc.get("code", "")
        method_name = "run_agentic" if SKILL_GENERATION_AGENTIC_ENABLED else "run"
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: getattr(self._controller, method_name)(
                spec,
                initial_feedback=enhanced_feedback,
                initial_code=current_code,
            )
        )

        # Update optimization Session
        optimize_session.status = (
            SessionStatus.COMPLETED if result.success else SessionStatus.FAILED
        )
        optimize_session.pipeline_result = result
        await self._save_session(optimize_session)

        generation_context = None

        # If successful, update Skill
        if result.success:
            version = skill_doc.get("version", 1) + 1
            now = datetime.utcnow().isoformat()
            generation_context = self._build_session_recommendations(spec=spec, session=optimize_session)
            metadata = dict(result.final_metadata or {})
            metadata["generation_context"] = generation_context
            await self._db[SKILL_COLLECTION].update_one(
                {"tool_id": skill_id},
                {
                    "$set": {
                        "code": result.final_code,
                        "metadata": metadata,
                        "generation_context": generation_context,
                        "version": version,
                        "optimize_feedback": feedback,
                        "generation_rounds": result.total_rounds,
                        "generation_time": result.total_time,
                        "final_score": (
                            result.iterations[-1].eval_score.total
                            if result.iterations and result.iterations[-1].eval_score
                            else None
                        ),
                        "updated_at": now,
                    },
                    "$push": {
                        "optimize_session_ids": optimize_session.session_id,
                    },
                },
            )
            logger.info(f"✅ Skill '{skill_id}' 已优化到 v{version}")

        return {
            "status": "completed" if result.success else "failed",
            "skill_id": skill_id,
            "optimize_session_id": optimize_session.session_id,
            "success": result.success,
            "version": skill_doc.get("version", 1) + 1 if result.success else skill_doc.get("version", 1),
            "total_rounds": result.total_rounds,
            "total_time": result.total_time,
            "final_score": (
                result.iterations[-1].eval_score.total
                if result.iterations and result.iterations[-1].eval_score
                else None
            ),
            "generation_context": generation_context,
            "error": result.error,
        }

    @staticmethod
    def _build_optimization_feedback(
        original_session: Optional[Dict],
        current_code: str,
        user_feedback: str,
    ) -> str:
        """构建优化反馈上下文"""
        parts = []

        # Summary of original requirements communication
        if original_session and original_session.get("rounds"):
            parts.append("=== Original requirement communication record ===")
            for r in original_session["rounds"]:
                parts.append(f"[用户]: {r.get('user_message', '')}")
                parts.append(f"[AI]: {r.get('ai_message', '')}")

        # current code
        if current_code:
            parts.append(f"\n=== Current code (needs optimization)===\n```python\n{current_code}\n```")

        # User feedback
        parts.append(f"\n=== User optimization needs ===\n{user_feedback}")

        return "\n".join(parts)

    # ==================== internal tool methods ====================

    async def _load_session(self, session_id: str) -> Optional[SkillCreationSession]:
        """Load session from MongoDB"""
        doc = await self._db[SESSION_COLLECTION].find_one({"session_id": session_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return SkillCreationSession(**doc)

    async def _save_session(self, session: SkillCreationSession) -> None:
        """Save session to MongoDB"""
        session.updated_at = datetime.utcnow()
        session_doc = session.model_dump(mode="json")
        await self._db[SESSION_COLLECTION].update_one(
            {"session_id": session.session_id},
            {"$set": session_doc},
            upsert=True,
        )

    async def _save_skill(
        self,
        session: SkillCreationSession,
        spec: SkillSpec,
        result: PipelineResult,
    ) -> str:
        """Save the generated Skill to the external_skills collection"""
        now = datetime.utcnow().isoformat()
        generation_context = self._build_session_recommendations(spec=spec, session=session)
        role_metadata = self._infer_skill_role_metadata(spec, session)
        metadata = dict(result.final_metadata or {})
        metadata["generation_context"] = generation_context
        metadata.update({key: value for key, value in role_metadata.items() if value})
        skill_doc = {
            "tool_id": spec.tool_id,
            "display_name": spec.display_name,
            "description": spec.description,
            "category": spec.category,
            "data_source": spec.data_source,
            "parameters": [p.model_dump() for p in spec.parameters],
            "expected_output": spec.expected_output.model_dump(),
            # Persistence behavior/interface specification constraints: inherit the interface contract (including URL) from it during iterative upgrades,
            # Prevent the new version from losing the interface address, resulting in code generation and artifacts URL
            "constraints": list(spec.constraints or []),
            "code": result.final_code,
            "metadata": metadata,
            "test_input": spec.test_input,
            "generation_context": generation_context,
            "capability_tags": role_metadata.get("capability_tags") or [],
            "tool_role_hint": role_metadata.get("tool_role_hint") or "",
            "output_shape": role_metadata.get("output_shape") or "",
            "preferred_for": role_metadata.get("preferred_for") or [],
            "not_replacement_for": role_metadata.get("not_replacement_for") or [],
            "known_failure_summaries": metadata.get("known_failure_summaries") or [],
            "known_verified_facts": metadata.get("known_verified_facts") or [],
            "status": "active",
            "source": "generated",
            "session_id": session.session_id,
            "user_id": session.user_id,
            "generation_rounds": result.total_rounds,
            "generation_time": result.total_time,
            "final_score": (
                result.iterations[-1].eval_score.total
                if result.iterations and result.iterations[-1].eval_score
                else None
            ),
            "created_at": now,
            "updated_at": now,
        }

        # Reverse provenance: Skill writeback from Agent Studio gap filling origin_* Fields (Phase 2)
        handoff = session.handoff_context
        if handoff is not None:
            handoff_source = str(getattr(handoff, "source", "") or "").strip()
            if handoff_source in ("agent_studio_gap", "agent_workshop_gap"):
                skill_doc["origin_source"] = "agent_studio_auto_gap_resolution"
                skill_doc["origin_workshop_session_id"] = str(getattr(handoff, "workshop_session_id", "") or "")
                skill_doc["origin_spec_id"] = str(getattr(handoff, "spec_id", "") or getattr(handoff, "source_spec_id", "") or "")
                skill_doc["origin_version_id"] = str(getattr(handoff, "version_id", "") or "")
                skill_doc["origin_gap_id"] = str(getattr(handoff, "gap_id", "") or "")
                skill_doc["origin_agent_name"] = str(getattr(handoff, "agent_name", "") or getattr(handoff, "source_name", "") or "")

        # 🔧 Version management: Calculate the version number in iteration mode to ensure that tool_id matches _v{N} Naming rules
        is_iteration = bool(session.iterate_skill_id)
        if is_iteration:
            original_tool_id = session.iterate_skill_id or ""
            try:
                original = await self._db[SKILL_COLLECTION].find_one(
                    {"tool_id": original_tool_id}
                )
            except Exception as exc:
                logger.warning("[SkillGeneration][Iterate] Failed to query the original Skill, press New Process: %s", exc)
                original = None

            if original:
                # parent_skill_id Points to the root Skill (if the original Skill also has a parent, it will be used; otherwise, the original tool_id will be used)
                parent_skill_id = original.get("parent_skill_id") or original_tool_id

                # Find the current maximum version number (among all versions in the same series)
                try:
                    cursor = self._db[SKILL_COLLECTION].find({
                        "$or": [
                            {"tool_id": parent_skill_id},
                            {"parent_skill_id": parent_skill_id},
                        ]
                    }).sort("version", -1).limit(1)
                    max_docs = await cursor.to_list(1)
                    new_version = (max_docs[0].get("version", 1) + 1) if max_docs else 2
                except Exception as exc:
                    logger.warning("[SkillGeneration][Iterate] Failed to query version number, use default v2: %s", exc)
                    new_version = 2

                # Make sure tool_id follows naming rules:{parent_skill_id}_v{new_version}
                expected_tool_id = f"{parent_skill_id}_v{new_version}"
                if skill_doc["tool_id"] != expected_tool_id:
                    # LLM Constraints may not be adhered to, so corrections are mandatory here.
                    logger.info(
                        "[SkillGeneration][Iterate] Correction tool_id: %s → %s",
                        skill_doc["tool_id"],
                        expected_tool_id,
                    )
                    skill_doc["tool_id"] = expected_tool_id
                    spec.tool_id = expected_tool_id

                # Extract the version description (take the first 50 words of the first round of user messages in the session)
                version_note = ""
                if session.rounds:
                    version_note = (session.rounds[0].user_message or "")[:50]
                if not version_note:
                    version_note = "迭代优化"

                skill_doc["parent_skill_id"] = parent_skill_id
                skill_doc["version"] = new_version
                skill_doc["version_note"] = version_note
                skill_doc["iteration_session_id"] = session.session_id

                logger.info(
                    "[SkillGeneration][Iterate] iterative save: parent=%s, version=%d, tool_id=%s",
                    parent_skill_id,
                    new_version,
                    expected_tool_id,
                )
            else:
                # The original Skill does not exist and is downgraded to a new one.
                logger.warning(
                    "[SkillGeneration][Iterate] The original Skill %s does not exist and is downgraded to new",
                    original_tool_id,
                )
                skill_doc["version"] = 1
        else:
            skill_doc["version"] = 1

        await self._db[SKILL_COLLECTION].insert_one(skill_doc)
        logger.info(f"✅ Skill '{spec.tool_id}' Saved to database (version={skill_doc.get('version', 1)})")

        try:
            from core.tools.registry import get_tool_registry
            from core.tools.external_skill_loader import register_single_external_skill
            from app.services.capability_index_service import CapabilityIndexService
            register_single_external_skill(None, get_tool_registry(), skill_doc)
            await CapabilityIndexService(self._db).ensure_index()
        except Exception as e:
            logger.warning(f"⚠️ Skill '{spec.tool_id}' Hot registration failed (takes effect after restart): {e}")

        return spec.tool_id


# ------------------------------------------------------------------
#  mem0 unified memory layer — Skill Build integration
# ------------------------------------------------------------------

def _build_skill_memory_metadata_filters(spec: SkillSpec) -> Optional[Dict[str, str]]:
    filters: Dict[str, str] = {}

    category = (spec.category or "").strip()
    data_source = (spec.data_source or "").strip()
    tool_id = (spec.tool_id or "").strip()

    if category:
        filters["category"] = category
    if data_source:
        filters["data_source"] = data_source
    if filters:
        return filters
    if tool_id:
        return {"tool_id": tool_id}
    return None


async def _recall_skill_lessons(db, spec: SkillSpec) -> str:
    """Historical lessons from recalling similar Skills from mem0"""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        query = f"{spec.description} {spec.data_source} {spec.category}"
        return await svc.recall_formatted(
            query=query.strip(),
            agent_id="skill_generator",
            scopes=["skill_lesson"],
            limit=10,
            max_chars=2000,
            metadata_filters=_build_skill_memory_metadata_filters(spec),
            ranking_profile="skill_generation",
            group_by_scope=True,
            per_scope_limit=5,
        )
    except Exception as e:
        logger.debug("[mem0] Skill Lesson recall failed: %s", e)
        return ""


async def _store_skill_lessons(db, spec: SkillSpec, result: PipelineResult) -> None:
    """Write the iteration lessons learned in this pipeline to mem0."""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)

        lessons = []
        metadata = dict(result.final_metadata or {})
        verified_facts = [str(item) for item in list(metadata.get("verified_facts") or []) if str(item).strip()]
        agentic_trace = metadata.get("agentic_trace") if isinstance(metadata.get("agentic_trace"), list) else []
        last_failure_summary = str(result.error or "").strip()
        if not last_failure_summary:
            for item in reversed(agentic_trace):
                if isinstance(item, dict) and str(item.get("failure_summary") or "").strip():
                    last_failure_summary = str(item.get("failure_summary") or "").strip()
                    break

        if last_failure_summary:
            lessons.append(
                f"Skill '{spec.tool_id}' ({spec.category}/{spec.data_source}) Agentic Failure summary: {last_failure_summary[:1200]}"
            )
        if verified_facts:
            lessons.append(
                f"Skill '{spec.tool_id}' 已验证环境事实: " + "；".join(verified_facts[:8])
            )
        for it in (result.iterations or []):
            if it.reflection and it.reflection.root_cause:
                lessons.append(
                    f"Skill '{spec.tool_id}' ({spec.category}/{spec.data_source}) "
                    f"No.{it.round_number}Round failed: {it.reflection.root_cause}"
                )

        if result.success:
            lessons.append(
                f"Skill '{spec.tool_id}' 最终在第{result.total_rounds}轮通过"
            )

        if not lessons:
            return

        messages = [{"role": "system", "content": "\n".join(lessons)}]
        await svc.store(
            messages,
            agent_id="skill_generator",
            scope="skill_lesson",
            metadata={
                "tool_id": spec.tool_id,
                "category": spec.category,
                "data_source": spec.data_source,
                "success": result.success,
                "total_rounds": result.total_rounds,
                "generation_engine": metadata.get("generation_engine", ""),
                "verified_fact_count": len(verified_facts),
            },
        )
    except Exception as e:
        logger.debug("[mem0] Skill Lesson storage failed: %s", e)

