"""
output evaluator — Two-tier evaluation mechanism

Tier 1: Basic inspection (zero LLM cost)
  - The return value is not empty
  - The return type is correct
  - Contains expected fields

Tier 2: Judge LLM Depth score (5 dimensions, 0-10 points)
  - Enforceability, authenticity, completeness, relevance, quality of format
"""

import json
import logging
import queue
import threading
from typing import Any, Callable, Dict, Optional

from core.llm import UnifiedLLMClient, Message

from .skill_spec import EvalScore, ImplementationFactReport, SandboxResult, SkillSpec

logger = logging.getLogger(__name__)

JUDGE_LLM_TIMEOUT_SECONDS = 120
JUDGE_LLM_MAX_TOKENS = 1200


class OutputEvaluator:
    """
    output evaluator

    Two-tier evaluation of sandbox execution results: Basic Check (free)+ Judge LLM (paid).
    """

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
        skip_judge: bool = False,
        quick_llm_client: Optional[UnifiedLLMClient] = None,
    ):
        """
        Args:
            llm_client: Preconfigured LLM client
            provider: LLM provider
            model: Model name
            skip_judge: Skip Judge LLM (basic check only)
            quick_llm_client: Quick model client (Judge scoring is used first, failure to fall back to the main model)
        """
        self._client = llm_client
        self._provider = provider
        self._model = model
        self._skip_judge = skip_judge
        self._quick_client = quick_llm_client

    def _get_client(self) -> UnifiedLLMClient:
        """懒加载 LLM 客户端"""
        if self._client is None:
            kwargs = {}
            if self._model:
                kwargs["model"] = self._model
            self._client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
        return self._client

    def evaluate(
        self,
        sandbox_result: SandboxResult,
        spec: SkillSpec,
        code: str,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> EvalScore:
        """
        Evaluate sandbox execution results

        Args:
            sandbox_result: Sandbox execution results
            spec: Skill Specifications
            code: generated code
            fact_report: Reconnaissance layer fact report (contains available_helpers that have been hit, used to prevent LLM from misjudging that the function does not exist)

        Returns:
            EvalScore: Assessment and scoring
        """
        score = EvalScore()

        # ===== Tier 1: basic check =====
        basic_passed = self._basic_check(sandbox_result, spec, score)

        if not basic_passed:
            # If the basic check fails, a low score will be returned directly.
            return score

        # ===== Tier 2: Judge LLM Depth scoring =====
        if not self._skip_judge:
            self._judge_llm_eval(sandbox_result, spec, code, score, fact_report)

        return score

    # ==================== Tier 1: basic check ====================

    def _basic_check(
        self, result: SandboxResult, spec: SkillSpec, score: EvalScore
    ) -> bool:
        """
        basic check — Zero LLM cost

        Returns:
            bool: Whether it passes the basic inspection
        """
        # 1. Whether the execution was successful
        if not result.success:
            score.executability = 0.0
            return False

        score.executability = 6.0  # Can run for at least 6 points

        output = result.output

        # 2. The return value is not empty
        if output is None or output == "" or output == [] or output == {}:
            score.completeness = 1.0
            score.authenticity = 1.0
            return False

        score.completeness = 5.0  # Have returned at least 5 points

        # 3. Check expected fields
        expected_fields = spec.expected_output.fields
        if expected_fields and isinstance(output, (list, dict)):
            sample = output[0] if isinstance(output, list) and output else output
            if isinstance(sample, dict):
                present = sum(1 for f in expected_fields if f in sample)
                ratio = present / len(expected_fields) if expected_fields else 1.0
                score.completeness = round(5.0 + ratio * 5.0, 1)
                score.format_quality = round(ratio * 8.0, 1)

        # 4. Return type check
        expected_type = spec.expected_output.type
        if "list" in expected_type and isinstance(output, list):
            score.format_quality = max(score.format_quality, 7.0)
        elif "dict" in expected_type and isinstance(output, dict):
            score.format_quality = max(score.format_quality, 7.0)
        elif "str" in expected_type and isinstance(output, str):
            score.format_quality = max(score.format_quality, 7.0)

        score.authenticity = 5.0  # Basic inspection cannot determine authenticity
        score.relevance = 5.0    # Basic inspection cannot determine correlation

        return True

    # ==================== Tier 2: Judge LLM (Simple Inline Prompt) ====================

    def _judge_llm_eval(
        self,
        result: SandboxResult,
        spec: SkillSpec,
        code: str,
        score: EvalScore,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> None:
        """Judge LLM Depth scoring — Simple inline prompt, all evidence is passed in at once"""
        import json as _json

        test_symbol = spec.test_input.get("symbol", "") or spec.test_input.get("code", "")
        test_name = spec.test_input.get("name", "") or spec.test_input.get("display_name", "")
        output_preview = self._format_output_preview(result.output)

        # Build helper manifest
        helpers_block = "（无 helper）"
        if fact_report and fact_report.available_helpers:
            lines = []
            for h in fact_report.available_helpers:
                ds_tag = getattr(h, 'data_source_handling', 'self_contained') or 'self_contained'
                sig = getattr(h, 'signature', '') or '(无签名)'
                lines.append(f"  {h.name}: {sig} [{ds_tag}]")
            if lines:
                helpers_block = "\n".join(lines)

        # Build log summary (take last 60 lines, about 4000 characters)
        log_block = "（无日志）"
        if result.stdout:
            log_lines = result.stdout.strip().split("\n")
            log_block = "\n".join(log_lines[-60:])

        # Build inline user message
        user_msg = (
            f"测试标的: {test_symbol} {test_name}\n"
            f"Skill Name: {spec.display_name}\n\n"
            f" [Sandbox execution results]\n"
            f"  success: {result.success}\n"
            f"  error: {result.error or 'None'}\n"
            f"  output JSON: {output_preview}\n\n"
            f" [Sandbox log (last 60 lines)]\n{log_block}\n\n"
            f" [Confirmed available helper functions]\n{helpers_block}\n\n"
            f"Scoring scale (1-10 points):\n"
            f"  executability: Normal execution≥7, There is an abnormality≤3\n"
            f"  authenticity: real data≥8, Data conflict≤3, no_data reasonable 5-6\n"
            f"  completeness: Field complete≥8, Core field is empty≤4\n"
            f"  relevance: Exact match≥8, Not answering the question≤3\n"
            f"  format_quality: Format specifications≥7, Naming confusion≤4\n\n"
            f"Rule: Execution successful=All functions must exist. It is strictly prohibited to judge functions based on training knowledge.'does not exist'\n\n"
            f"Output format, only output the following, no other content:\n"
            f"<verdict>\n"
            f'{{"executability": <points>, "authenticity": <points>, "completeness": <points>, '
            f'"relevance": <points>, "format_quality": <points>, "expert_comment": "<a word>"}}\n'
            f"</verdict>"
        )

        try:
            import re

            logger.info(f"\n{'─'*50}\n📤 [OutputEvaluator] Judge LLM 启动 ({len(user_msg)} 字符)\n{'─'*50}")
            raw = self._call_judge_llm_simple(user_msg, spec.tool_id)
            if raw is None:
                logger.warning("Judge LLM Timeout, retain base check score | tool_id=%s", spec.tool_id)
                return

            logger.info(f"\n{'─'*50}\n📥 [OutputEvaluator] Judge LLM output\n{'─'*50}\n{raw}\n{'─'*50}")

            # from <verdict> tag extraction JSON
            verdict_match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", raw, re.DOTALL)
            if verdict_match:
                json_str = verdict_match.group(1).strip()
            else:
                fallback = re.search(r"\{[^{}]*\}", raw)
                json_str = fallback.group() if fallback else ""

            if json_str:
                scores = _json.loads(json_str)
                score.executability = float(scores.get("executability", score.executability))
                score.authenticity = float(scores.get("authenticity", score.authenticity))
                score.completeness = float(scores.get("completeness", score.completeness))
                score.relevance = float(scores.get("relevance", score.relevance))
                score.format_quality = float(scores.get("format_quality", score.format_quality))

                # Hard Rule: Successful execution must≥7
                if result.success and score.executability < 7.0:
                    logger.warning(f"LLM Misjudgment: success=True But executability={score.executability}<7, Force promotion")
                    score.executability = 7.0

                comment = str(scores.get("expert_comment", "")).strip()
                if comment:
                    score.expert_comment = comment
                    logger.info(f"🎯 Judge LLM Rating: {score.total} | {comment}")
                else:
                    logger.info(f"🎯 Judge LLM Rating: {score.total}")
            else:
                logger.warning(f"⚠️ Judge LLM not found in output JSON: {raw[:500]}")
        except Exception as e:
            logger.warning(f"Judge LLM Scoring failed, basic inspection score retained: {e}")

    def _call_judge_llm_simple(self, user_msg: str, tool_id: str) -> Optional[str]:
        """Simple LLM call (no tools, single request + timeout protection).

        Judge Scoring is a judgment task, and fast models (second level) are preferred.
        Fallback to the main model when the fast model fails or has an empty reply.
        """
        result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)

        def _worker() -> None:
            try:
                messages = [
                    Message(role="system", content="You are an expert in financial data evaluation, evaluating the quality of output from Skill tools. Output strictly according to the format <verdict> JSON. "),
                    Message(role="user", content=user_msg),
                ]
                if self._quick_client is not None:
                    try:
                        response = self._quick_client.chat(
                            messages, temperature=0.0, max_tokens=2048
                        )
                        content = (response.content or "").strip()
                        if content:
                            result_queue.put(("ok", content))
                            return
                        logger.warning("Judge The quick model returns empty content and rolls back to the main model.")
                    except Exception as quick_exc:
                        logger.warning(f"Judge The quick model call failed and the main model was rolled back.: {quick_exc}")
                client = self._get_client()
                response = client.chat(messages, temperature=0.0, max_tokens=2048)
                result_queue.put(("ok", response.content or ""))
            except Exception as exc:
                result_queue.put(("error", exc))

        worker = threading.Thread(
            target=_worker, name=f"skill-judge-{tool_id}", daemon=True
        )
        worker.start()
        worker.join(JUDGE_LLM_TIMEOUT_SECONDS)

        if worker.is_alive():
            return None
        status, payload = result_queue.get_nowait()
        if status == "error":
            raise payload
        return str(payload)

    # ==================== Tool method ====================

    @staticmethod
    def _format_output_preview(output: Any, max_len: int = 8000) -> str:
        """格式化输出预览"""
        if output is None:
            return "(空)"
        try:
            text = json.dumps(output, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            text = str(output)
        if len(text) > max_len:
            text = text[:max_len] + "\n... (截断)"
        return text
