"""
iteration controller — Agent Driven Skill Generation Pipeline

Drawing on the idea of OpenClaw Agent Loop: LLM leads the iterative process and you can see the complete execution context
 (sandbox stdout/stderr/output) , After each round of failure, do a reflective analysis and then make targeted repairs.

Pipeline process:
  CodeGenerator → StaticValidator → SandboxRunner → OutputEvaluator
                                                      ↓ (PASS after)
                                                  Edge test verification

Iterative decision making:
  PASS  — Rating >= 8.0 And the edge test passes
  RETRY — Insufficient score, sandbox failure or edge test failure, and the round limit has not been exceeded
  FAIL  — Failure to pass after more than 10 rounds, with reasons for failure in each round
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.llm import UnifiedLLMClient, Message
from core.llm.tool_normalizer import ToolCallNormalizer

from .business_verifier import BusinessVerifierRegistry
from .code_generator import CODEGEN_LLM_TIMEOUT_SECONDS, CodeGenerator
from .output_evaluator import OutputEvaluator
from .reconnaissance_controller import DefaultReconnaissanceController, ReconnaissanceController
from .sandbox_runner import SandboxRunner
from .skill_spec import (
    BusinessVerificationResult,
    GeneratedCode,
    ImplementationFactReport,
    IterationRound,
    PipelineResult,
    ReflectionResult,
    SandboxResult,
    SkillSpec,
)
from .static_validator import StaticValidator

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10
PASS_THRESHOLD = 8.5
# Continuous identical failure detection threshold: If the failure items of N consecutive rounds of business acceptance are completely consistent, it will be determined as unrecoverable.
# Adjusted from 5 to 3: trigger circuit breakers earlier to avoid wasting iteration budget on unrecoverable failures
_STALE_FAILURE_THRESHOLD = 3

# Snapshot root directory (consistent with SkillGenerationService)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SNAPSHOT_DIR = _PROJECT_ROOT / "data" / "code" / "skill"


@dataclass
class PipelineToolResult:
    """Agentic Loop Structured results of a single round of pipeline_tool."""

    status: str = "fail"  # pass / fail / blocked
    round_number: int = 1
    iteration: Optional[IterationRound] = None
    code_path: str = ""
    snapshot_path: str = ""
    static_validation: Dict[str, Any] = field(default_factory=dict)
    sandbox_result: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    failure_summary: str = ""
    verified_facts: List[str] = field(default_factory=list)
    should_retry: bool = True
    final_code: str = ""
    final_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "round_number": self.round_number,
            "code_path": self.code_path,
            "snapshot_path": self.snapshot_path,
            "static_validation": self.static_validation,
            "sandbox_result": self.sandbox_result,
            "evaluation": self.evaluation,
            "failure_summary": self.failure_summary,
            "verified_facts": self.verified_facts,
            "should_retry": self.should_retry,
            "has_final_code": bool(self.final_code),
        }


class _AgenticPipelineAbort(Exception):
    """pipeline_tool Used internally to interrupt a single round of execution when an unrecoverable failure is encountered."""

    def __init__(self, result: PipelineToolResult):
        self.result = result
        super().__init__(result.failure_summary or result.status)


class IterationController:
    """
    iteration controller

    Arrange CodeGenerator → StaticValidator → SandboxRunner → OutputEvaluator
    A complete pipeline that inserts an LLM reflection step on each failed round with automatic retries for up to 10 rounds.
    """

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
        max_iterations: int = MAX_ITERATIONS,
        skip_judge: bool = False,
        reconnaissance_controller: Optional[ReconnaissanceController] = None,
        quick_llm_client: Optional[UnifiedLLMClient] = None,
    ):
        self._generator = CodeGenerator(
            llm_client=llm_client, provider=provider, model=model
        )
        self._validator = StaticValidator()
        self._runner = SandboxRunner()
        self._evaluator = OutputEvaluator(
            llm_client=llm_client,
            provider=provider,
            model=model,
            skip_judge=skip_judge,
            quick_llm_client=quick_llm_client,
        )
        self._business_verifiers = BusinessVerifierRegistry(
            llm_client=llm_client,
            provider=provider,
            model=model,
        )
        self._reconnaissance = reconnaissance_controller or DefaultReconnaissanceController()
        self._llm_client = llm_client
        self._provider = provider
        self._model = model
        self._max_iterations = max_iterations
        self._agentic_trace: List[Dict[str, Any]] = []

    def _get_client(self) -> UnifiedLLMClient:
        if self._llm_client is None:
            kwargs = {}
            if self._model:
                kwargs["model"] = self._model
            self._llm_client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
        return self._llm_client

    def run(
        self, spec: SkillSpec,
        initial_feedback: str = "",
        initial_code: str = "",
        progress_callback: Optional[Callable[[str, str, int, float], None]] = None,
        fact_report: Optional[ImplementationFactReport] = None,
        codegen_timeout: Optional[int] = None,
        thinking_callback: Optional[Callable[[str, str], None]] = None,
        iteration_mode: str = "repair",
    ) -> PipelineResult:
        """
        Execute the complete build pipeline

        Args:
            spec: Skill Specification (confirmed)
            initial_feedback: Initial feedback (optimizing scenario usage)
            initial_code: Initial code (optimized for scenario use)
            progress_callback: Progress callback (stage, message, iteration, progress)
            fact_report: Pre-built reconnaissance report (reconnaissance pre-mode), when None, reconnaissance is automatically performed internally
            codegen_timeout: Code generation single LLM call timeout (seconds), None uses the default value
            thinking_callback: thought process callback on_thinking(kind, text), Transparently transmitted to code generator for real-time display
            iteration_mode: "repair"=Directed repair after failure;"upgrade"=Upgrade with minimal changes to the proven old version

        Returns:
            PipelineResult: pipeline final result
        """
        start_time = time.time()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        iterations: List[IterationRound] = []
        feedback = initial_feedback
        previous_code = initial_code

        def _report(stage: str, message: str, it: int, prog: float, extra: Optional[Dict[str, Any]] = None):
            if progress_callback:
                try:
                    progress_callback(stage, message, it, prog, extra)
                except Exception as e:
                    logger.warning(f"progress_callback Abnormal: {e}")

        if fact_report is not None:
            # Reconnaissance pre-mode: reuse the reconnaissance report completed by the upstream
            logger.info(
                "🧭 Reuse upstream reconnaissance reports | strategy=%s | helpers=%d | checks=%d",
                fact_report.recommended_strategy or "(none)",
                len(fact_report.available_helpers),
                len(fact_report.validation_checks),
            )
            self._persist_fact_report(spec.tool_id, run_id, fact_report)
        else:
            # Internal recon mode (backwards compatible)
            try:
                _report("reconnaissance", "正在整理实现事实...", 0, 0.03)
                fact_report = self._reconnaissance.analyze(spec)
                logger.info(
                    "🧭 Preliminary reconnaissance completed | strategy=%s | helpers=%d | checks=%d",
                    fact_report.recommended_strategy or "(none)",
                    len(fact_report.available_helpers),
                    len(fact_report.validation_checks),
                )
                self._persist_fact_report(spec.tool_id, run_id, fact_report)

                for idx, update in enumerate(self._build_reconnaissance_updates(fact_report), start=1):
                    logger.info("🧭 Reconnaissance summary[%d]: %s", idx, update)
                    _report("reconnaissance", update, 0, min(0.03 + idx * 0.01, 0.08))
                _report("reconnaissance", "实现事实整理完成", 0, 0.08)
            except Exception as e:
                logger.warning(f"⚠️ Pre-reconnaissance failed, continue to use the original generation process: {e}")
                _report("reconnaissance", "Failed to implement fact sorting and downgraded to original process", 0, 0.08)

        for round_num in range(1, self._max_iterations + 1):
            logger.info(
                f"\n{'='*60}\n"
                f"🔄 Skill Build pipeline — No. {round_num}/{self._max_iterations} wheel | tool_id={spec.tool_id}\n"
                f"{'='*60}"
            )
            _report("iteration", f"第 {round_num}/{self._max_iterations} 轮", round_num, 0)

            iteration = IterationRound(round_number=round_num)

            # ===== stage 1: code generation =====
            _report("code_generation", "正在生成代码...", round_num, 0.1)
            try:
                generated = self._generator.generate(
                    spec,
                    feedback=feedback,
                    previous_code=previous_code,
                    fact_report=fact_report,
                    timeout_seconds=codegen_timeout,
                    on_thinking=thinking_callback,
                    # Only the first round (based on the parent version code) uses upgrade copy; subsequent rounds are to fix problems with the new code
                    iteration_mode=("upgrade" if iteration_mode == "upgrade" and round_num == 1 else "repair"),
                )
                iteration.generated_code = generated
                # Detailed log: code summary
                code_lines = generated.code.split("\n") if generated.code else []
                logger.info(
                    f"✅ [第{round_num}轮] 代码生成完成\n"
                    f"   ⏱️  Time consuming: {generated.generation_time}s\n"
                    f"   📏 Lines of code: {len(code_lines)}\n"
                    f"   📝 The first 5 lines of code:\n"
                    + "\n".join(f"      | {line}" for line in code_lines[:5])
                    + (f"\n      | ... (共 {len(code_lines)} 行)" if len(code_lines) > 5 else "")
                )
                self._persist_stage_artifact(
                    tool_id=spec.tool_id,
                    run_id=run_id,
                    round_num=round_num,
                    stage="code_generation",
                    payload={
                        "success": True,
                        "generation_time": generated.generation_time,
                        "code_lines": len(code_lines),
                        "metadata": generated.metadata or {},
                    },
                    code=generated.code,
                )
                _report("code_generation", f"代码生成完成 ({generated.generation_time}s)", round_num, 0.2)
            except Exception as e:
                logger.error(f"❌ [第{round_num}轮] 代码生成失败: {e}")
                self._persist_stage_artifact(
                    tool_id=spec.tool_id,
                    run_id=run_id,
                    round_num=round_num,
                    stage="code_generation",
                    payload={
                        "success": False,
                        "error": str(e),
                    },
                )
                iteration.decision = "FAIL"
                iteration.feedback = f"代码生成失败: {e}"
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                break

            # ===== stage 2: Static verification =====
            _report("static_validation", "正在语法检查...", round_num, 0.25)
            validation = self._validator.validate(generated, spec)
            iteration.validation = validation
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="static_validation",
                payload={
                    "passed": validation.passed,
                    "errors": validation.errors[:20],
                    "warnings": (validation.warnings or [])[:20],
                },
                code=generated.code,
            )

            if not validation.passed:
                feedback = self._build_rich_feedback(
                    stage="静态验证",
                    errors=validation.errors,
                    code=generated.code,
                    spec=spec,
                )
                previous_code = generated.code
                iteration.decision = "RETRY"
                iteration.feedback = feedback
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("static_validation", "Static verification failed, retrying...", round_num, 0.3)
                logger.warning(
                    f"⚠️ [第{round_num}轮] 静态验证失败:\n"
                    + "\n".join(f"   ❌ {err}" for err in validation.errors[:5])
                )
                continue

            logger.info(f"✅ [第{round_num}轮] 静态验证通过")
            _report("static_validation", "语法检查通过", round_num, 0.35)

            # ===== stage 3: sandbox execution =====
            _report("sandbox_execution", "正在沙箱执行...", round_num, 0.4)
            sandbox = self._runner.run(generated.code, spec)
            iteration.sandbox = sandbox
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="sandbox_execution",
                payload={
                    "success": sandbox.success,
                    "execution_time": sandbox.execution_time,
                    "error": sandbox.error,
                    "stdout": sandbox.stdout,
                    "stderr": sandbox.stderr,
                    "output": sandbox.output,
                },
                code=generated.code,
            )

            if not sandbox.success:
                _report("reflection", "正在分析失败原因...", round_num, 0.5)
                logger.warning(
                    f"⚠️ [第{round_num}轮] 沙箱执行失败:\n"
                    f"   Error: {sandbox.error or 'unknown error'}\n"
                    f"   stderr: {(sandbox.stderr or '(empty)')[:500]}"
                )
                reflection = self._reflect_on_failure(
                    spec=spec,
                    code=generated.code,
                    stage="沙箱执行",
                    error=sandbox.error or "未知错误",
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    fact_report=fact_report,
                sandbox_success=getattr(sandbox, "success", False),
            )
                iteration.reflection = reflection
                logger.info(
                    f"🔍 [第{round_num}轮] 反思结果:\n"
                    f"   root cause: {reflection.root_cause}\n"
                    f"   Repair plan: {reflection.fix_plan}\n"
                    f"   Confidence: {reflection.confidence}"
                )

                feedback = self._build_rich_feedback(
                    stage="沙箱执行",
                    errors=[sandbox.error or "未知错误"],
                    code=generated.code,
                    spec=spec,
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    reflection=reflection,
                )
                previous_code = generated.code
                # ---- Early exit: Reflection suggests giving up ----
                if not reflection.should_retry:
                    iteration.decision = "FAIL"
                    iteration.feedback = feedback
                    iterations.append(iteration)
                    self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                    _report("sandbox_execution", "After reflection, it was determined that it was irreparable and terminated early.", round_num, 0.55)
                    logger.warning(
                        f"🛑 [第{round_num}轮] 反思建议放弃 (should_retry=False): {reflection.root_cause}"
                    )
                    break
                iteration.decision = "RETRY"
                iteration.feedback = feedback
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("sandbox_execution", "Sandbox execution failed, trying again after reflection...", round_num, 0.55)
                continue

            # Detailed log: sandbox execution results
            output_preview = ""
            if sandbox.output is not None:
                try:
                    output_preview = json.dumps(sandbox.output, ensure_ascii=False, default=str)[:500]
                except Exception:
                    output_preview = str(sandbox.output)[:500]
            logger.info(
                f"✅ [第{round_num}轮] 沙箱执行成功\n"
                f"   ⏱️  Time consuming: {sandbox.execution_time}s\n"
                f"   📤 Return value preview: {output_preview or '(empty)'}\n"
                f"   📺 stdout: {(sandbox.stdout or '(empty)')[:300]}"
            )
            _report("sandbox_execution", f"沙箱执行成功 ({sandbox.execution_time}s)", round_num, 0.6)

            # ===== stage 4: Business acceptance (structural inspection, zero LLM cost) =====
            business_verification = self._business_verifiers.resolve(spec).verify(
                sandbox,
                spec,
                fact_report,
            )
            iteration.business_verification = business_verification
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="business_verification",
                payload={
                    "passed": business_verification.passed,
                    "business_score": business_verification.business_score,
                    "failures": [failure.model_dump() for failure in business_verification.failures[:20]],
                    "warnings": business_verification.warnings[:20],
                    "details": business_verification.details,
                },
                code=generated.code,
            )
            logger.info(
                f"🧪 [第{round_num}轮] 业务验收:\n"
                f"   Pass: {business_verification.passed}\n"
                f"   Business points: {business_verification.business_score}\n"
                f"   failed items: {len(business_verification.failures)}"
            )

            if not business_verification.passed:
                # If the business acceptance fails, collect error feedback
                _report("output_evaluation", "The business acceptance has not passed and is being analyzed....", round_num, 0.58)
                failure_messages = []
                failure_messages.extend(self._build_business_errors(business_verification))
                extra_context_parts = [self._build_business_reflection_context(business_verification)]

                #  [New] Financial expert judgment: If the sandbox output contains no_data, judge whether the business is reasonable + Recommended share exchange
                expert_advice = self._check_no_data_and_advise(
                    spec, sandbox.output, fact_report
                )
                if expert_advice:
                    extra_context_parts.append(expert_advice)

                reflection = self._reflect_on_failure(
                    spec=spec,
                    code=generated.code,
                    stage="业务验收",
                    error="\n".join(failure_messages),
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    fact_report=fact_report,
                    sandbox_success=getattr(sandbox, "success", False),
                    extra_context="\n\n".join(part for part in extra_context_parts if part),
                )
                iteration.reflection = reflection
                feedback = self._build_rich_feedback(
                    stage="业务验收",
                    errors=failure_messages,
                    code=generated.code,
                    spec=spec,
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    reflection=reflection,
                )
                # Add expert advice to feedback
                if expert_advice:
                    feedback = f"{feedback}\n\n{expert_advice}"
                iteration.decision = "RETRY"
                iteration.feedback = feedback
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("output_evaluation", "Business acceptance failed, trying again after reflection...", round_num, 0.7)
                continue

            # ===== stage 5: Black box verification — Standard function reference comparison =====
            _report("reference_comparison", "Comparing standard function output...", round_num, 0.65)
            ref_comparison_failures = self._compare_with_reference_helpers(
                sandbox, spec, fact_report
            )
            if ref_comparison_failures:
                logger.warning(
                    f"⚠️ [第{round_num}轮] 🔴 黑盒验证失败: 输出值不符合标准函数参考\n"
                    + "\n".join(f"   ❌ {f}" for f in ref_comparison_failures[:5])
                )
                _report("reflection", "Black box validation failed (incorrect value), white box code review skipped, analysis in progress...", round_num, 0.68)
                reflection = self._reflect_on_failure(
                    spec=spec,
                    code=generated.code,
                    stage="Black box verification (standard function reference comparison)",
                    error="\n".join(ref_comparison_failures),
                    stdout=sandbox.stdout,
                    stderr="",
                    output=sandbox.output,
                    fact_report=fact_report,
                sandbox_success=getattr(sandbox, "success", False),
            )
                iteration.reflection = reflection
                feedback = self._build_rich_feedback(
                    stage="Black box verification (standard function reference comparison)",
                    errors=ref_comparison_failures,
                    code=generated.code,
                    spec=spec,
                    stdout=sandbox.stdout,
                    output=sandbox.output,
                    reflection=reflection,
                )
                iteration.decision = "RETRY"
                iteration.feedback = feedback
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("reference_comparison", "Black box verification failed, trying again after reflection...", round_num, 0.72)
                continue

            _report("reference_comparison", "The black box verification is passed and the output value is consistent with the standard function.", round_num, 0.7)

            # ===== stage 6: white box evaluation — Judge LLM code review =====
            _report("output_evaluation", "White box code quality assessment in progress...", round_num, 0.75)
            eval_score = self._evaluator.evaluate(sandbox, spec, generated.code, fact_report=fact_report)
            iteration.eval_score = eval_score
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="output_evaluation",
                payload={
                    "eval_score": iteration.eval_score.model_dump(),
                },
                code=generated.code,
            )
            logger.info(
                f"📊 [第{round_num}轮] 评估得分:\n"
                f"   total score: {eval_score.total}/10 (threshold: {PASS_THRESHOLD})\n"
                f"   Enforceability: {eval_score.executability} | authenticity: {eval_score.authenticity}\n"
                f"   integrity: {eval_score.completeness} | Relevance: {eval_score.relevance}\n"
                f"   Format quality: {eval_score.format_quality}"
            )
            # The evaluation results are revealed in real time: the front-end can see the scores and comments of each dimension the moment the evaluation is completed.
            _eval_passed = eval_score.total >= PASS_THRESHOLD
            _report(
                "output_evaluation",
                f"Quality assessment completed:{eval_score.total}/10 ({'Meet the standard' if _eval_passed else 'Not up to standard'}) ",
                round_num,
                0.77,
                extra=self._build_eval_result_extra(eval_score, round_num),
            )

            if eval_score.total < PASS_THRESHOLD:
                _report("reflection", f"白盒评审未通过 ({eval_score.total}/10)，正在分析...", round_num, 0.78)
                failure_messages = []
                failure_messages.extend(self._build_eval_errors(eval_score))
                extra_context = []
                extra_context.append(self._build_eval_reflection_context(eval_score))
                reflection = self._reflect_on_failure(
                    spec=spec,
                    code=generated.code,
                    stage="白盒代码评审",
                    error="\n".join(failure_messages),
                    stdout=sandbox.stdout,
                    stderr="",
                    output=sandbox.output,
                    fact_report=fact_report,
                sandbox_success=getattr(sandbox, "success", False),
            )
                iteration.reflection = reflection
                feedback = self._build_rich_feedback(
                    stage="白盒代码评审",
                    errors=failure_messages,
                    code=generated.code,
                    spec=spec,
                    stdout=sandbox.stdout,
                    output=sandbox.output,
                    reflection=reflection,
                )
                iteration.decision = "RETRY"
                iteration.feedback = feedback
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("output_evaluation", "The white box review failed, and we are trying again after reflection....", round_num, 0.82)
                continue

                # ===== stage 5: Edge test verification =====
                _report("edge_testing", "Performing edge test verification...", round_num, 0.8)
                edge_failures = self._run_edge_tests(generated.code, spec)

                if edge_failures:
                    logger.warning(
                        f"⚠️ [第{round_num}轮] 边缘测试发现 {len(edge_failures)} 个问题:\n"
                        + "\n".join(f"   ❌ {f}" for f in edge_failures[:5])
                    )
                    _report("reflection", "Edge test failed, analyzing...", round_num, 0.85)
                    reflection = self._reflect_on_failure(
                        spec=spec,
                        code=generated.code,
                        stage="边缘测试",
                        error="\n".join(edge_failures),
                        stdout=sandbox.stdout,
                        stderr="",
                        output=sandbox.output,
                        fact_report=fact_report,
                        sandbox_success=getattr(sandbox, "success", False),
                    )
                    iteration.reflection = reflection

                    feedback = self._build_rich_feedback(
                        stage="边缘测试",
                        errors=edge_failures,
                        code=generated.code,
                        spec=spec,
                        stdout=sandbox.stdout,
                        output=sandbox.output,
                        reflection=reflection,
                    )
                    previous_code = generated.code
                    iteration.decision = "RETRY"
                    iteration.feedback = feedback
                    iterations.append(iteration)
                    self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                    _report("edge_testing", "Edge test failed, retrying after reflection...", round_num, 0.9)
                    continue

                # All passed
                iteration.decision = "PASS"
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("output_evaluation", f"Assessment passed, total score: {eval_score.total}", round_num, 1.0)
                total_time = round(time.time() - start_time, 2)
                logger.info(
                    f"\n{'='*60}\n"
                    f"🎉 Skill Generated successfully!\n"
                    f"   tool_id: {spec.tool_id}\n"
                    f"   total score: {eval_score.total}/10\n"
                    f"   Business acceptance: Pass\n"
                    f"   Number of iteration rounds: {round_num}\n"
                    f"   Total time spent: {total_time}s\n"
                    f"   Lines of code: {len(generated.code.split(chr(10)))}\n"
                    f"{'='*60}"
                )
                return PipelineResult(
                    success=True,
                    tool_id=spec.tool_id,
                    final_code=generated.code,
                    final_metadata=generated.metadata,
                    iterations=iterations,
                    total_rounds=round_num,
                    total_time=round(time.time() - start_time, 2),
                )
            else:
                failure_messages: List[str] = []
                extra_context_parts: List[str] = []
                if eval_score.total < PASS_THRESHOLD:
                    failure_messages.extend(self._build_eval_errors(eval_score))
                    extra_context_parts.append(self._build_eval_reflection_context(eval_score))
                if not business_verification.passed:
                    failure_messages.extend(self._build_business_errors(business_verification))
                    extra_context_parts.append(self._build_business_reflection_context(business_verification))

                reason = (
                    f"评分不足 ({eval_score.total}/10)"
                    if eval_score.total < PASS_THRESHOLD and business_verification.passed
                    else "业务验收未通过"
                    if eval_score.total >= PASS_THRESHOLD and not business_verification.passed
                    else f"Insufficient ratings and failed business acceptance ({eval_score.total}/10)"
                )
                _report("reflection", f"{reason}, Analyzing...", round_num, 0.75)
                reflection = self._reflect_on_failure(
                    spec=spec,
                    code=generated.code,
                    stage="质量评估/业务验收",
                    error="\n".join(failure_messages),
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    fact_report=fact_report,
                    sandbox_success=getattr(sandbox, "success", False),
                    extra_context="\n\n".join(part for part in extra_context_parts if part),
                )
                iteration.reflection = reflection
                logger.info(
                    f"🔍 [第{round_num}轮] 反思结果:\n"
                    f"   root cause: {reflection.root_cause}\n"
                    f"   Repair plan: {reflection.fix_plan}\n"
                    f"   Confidence: {reflection.confidence}"
                )

                feedback = self._build_rich_feedback(
                    stage="质量评估/业务验收",
                    errors=failure_messages,
                    code=generated.code,
                    spec=spec,
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    reflection=reflection,
                )
                previous_code = generated.code

                # ---- Early exit: Reflection suggests giving up ----
                if not reflection.should_retry:
                    iteration.decision = "FAIL"
                    iteration.feedback = feedback
                    iterations.append(iteration)
                    self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                    _report("output_evaluation", "After reflection, it was determined that it was irreparable and terminated early.", round_num, 0.8)
                    logger.warning(
                        f"🛑 [第{round_num}轮] 反思建议放弃 (should_retry=False): {reflection.root_cause}"
                    )
                    break

                # ---- Early exit: Continuous same failure detection ----
                if self._detect_stale_failures(iterations):
                    iteration.decision = "FAIL"
                    iteration.feedback = feedback + "\n\n[system] If the failed items in multiple rounds of business acceptance are exactly the same, it is determined that the data source is unavailable and terminated early."
                    iterations.append(iteration)
                    self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                    _report("output_evaluation", "Continuous identical failures, data unavailable, early termination", round_num, 0.8)
                    logger.warning(
                        f"🛑 [第{round_num}轮] 连续 {_STALE_FAILURE_THRESHOLD} 轮相同业务验收失败，判定为不可恢复"
                    )
                    break

                iteration.decision = "RETRY"
                iteration.feedback = feedback
                iterations.append(iteration)
                self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
                _report("output_evaluation", f"{reason}, Trying again after reflection...", round_num, 0.8)
                logger.warning(f"⚠️ [第{round_num}轮] {reason}，进入下一轮")

        failure_summary = self._build_failure_summary(iterations)
        total_time = round(time.time() - start_time, 2)
        logger.error(
            f"\n{'='*60}\n"
            f"❌ Skill Build failed — {self._max_iterations} Still not passed after rounds of iterations\n"
            f"   tool_id: {spec.tool_id}\n"
            f"   Total time spent: {total_time}s\n"
            f"{'='*60}"
        )
        # v3.6.0 Item 6 Path A: Write to the skill_iteration_alerts collection after failure and wait for manual decision-making
        self._write_iteration_alert(
            spec=spec,
            run_id=run_id,
            iterations=iterations,
            failure_summary=failure_summary,
            total_time=total_time,
            engine="legacy_pipeline",
        )
        return PipelineResult(
            success=False,
            tool_id=spec.tool_id,
            iterations=iterations,
            total_rounds=self._max_iterations,
            total_time=round(time.time() - start_time, 2),
            error=failure_summary,
        )

    # ==================== Exit detection early ====================

    @staticmethod
    def _detect_stale_failures(iterations: List[IterationRound]) -> bool:
        """
        Check whether the failed items in N consecutive rounds of business acceptance are exactly the same.
        If so, the reason for the failure is that external data is unavailable, and continued iteration will not improve it.
        """
        if len(iterations) < _STALE_FAILURE_THRESHOLD:
            return False

        recent = iterations[-_STALE_FAILURE_THRESHOLD:]

        # Extract the failed rule_id collection of each round
        failure_sets: List[frozenset] = []
        for it in recent:
            if it.business_verification and not it.business_verification.passed:
                rule_ids = frozenset(f.rule_id for f in it.business_verification.failures)
                failure_sets.append(rule_ids)
            else:
                return False  # If one round passes or there is no business acceptance, it is not considered consecutive.

        if len(failure_sets) < _STALE_FAILURE_THRESHOLD:
            return False

        # All sets are the same
        return len(set(failure_sets)) == 1

    # ==================== Instant order placement ====================

    @staticmethod
    def _get_snapshot_dir(tool_id: str, run_id: str) -> Path:
        """Get the snapshot directory of the currently running batch: data/code/skill/{tool_id}/{run_id}/"""
        d = _SNAPSHOT_DIR / tool_id / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _persist_fact_report(
        tool_id: str,
        run_id: str,
        fact_report: ImplementationFactReport,
    ) -> Optional[Path]:
        """Place fact_report.json immediately after the reconnaissance is completed."""
        try:
            d = IterationController._get_snapshot_dir(tool_id, run_id)
            path = d / "fact_report.json"
            data = fact_report.model_dump(mode="json")
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info("📝 The reconnaissance report has been placed: %s", path)
            return path
        except Exception as exc:
            logger.warning("⚠️ Reconnaissance report placement failed: %s", exc)
            return None

    @staticmethod
    def _dump_agentic_prompt_to_logfile(
        spec: SkillSpec,
        system_prompt: str,
        user_prompt: str,
        fact_report: Optional[ImplementationFactReport],
    ) -> None:
        """Write the complete system/user prompt in agentic mode to the log file to facilitate troubleshooting the problem of LLM not calling the recommended helper.

        Log file location:logs/codegen_prompts/agentic_<tool_id>_<timestamp>.log
        """
        try:
            from datetime import datetime
            log_dir = Path("logs/codegen_prompts")
            log_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_tool_id = re.sub(r"[^\w\-]", "_", spec.tool_id or "unknown")

            # Build helper summary
            helper_summary = " (no fact_report)"
            if fact_report:
                if fact_report.available_helpers:
                    helper_lines = []
                    for h in fact_report.available_helpers:
                        helper_lines.append(
                            f"  - {h.module}.{h.name} | signature={h.signature or ''} | "
                            f"data_source_handling={h.data_source_handling or ''} | reason={h.reason or ''}"
                        )
                    helper_summary = f"共 {len(fact_report.available_helpers)} 个:\n" + "\n".join(helper_lines)
                else:
                    helper_summary = "available_helpers is empty"

            content = (
                f"{'=' * 80}\n"
                f"# Agentic SkillGeneration Prompt Dump\n"
                f"{'=' * 80}\n"
                f"# tool_id: {spec.tool_id}\n"
                f"# timestamp: {timestamp}\n"
                f"# spec.display_name: {spec.display_name}\n"
                f"# spec.description: {spec.description[:200] if spec.description else ''}\n"
                f"# system_prompt length: {len(system_prompt)} character\n"
                f"# user_prompt length: {len(user_prompt)} character\n"
                f"\n"
                f"{'─' * 80}\n"
                f"## Recommended by the reconnaissance layer available_helpers\n"
                f"{'─' * 80}\n"
                f"{helper_summary}\n"
                f"\n"
                f"{'─' * 80}\n"
                f"## Agentic System Prompt (complete)\n"
                f"{'─' * 80}\n"
                f"{system_prompt}\n"
                f"\n"
                f"{'─' * 80}\n"
                f"## Agentic User Prompt (complete)\n"
                f"{'─' * 80}\n"
                f"{user_prompt}\n"
            )

            hist_path = log_dir / f"agentic_{safe_tool_id}_{timestamp}.log"
            hist_path.write_text(content, encoding="utf-8")

            latest_path = log_dir / f"agentic_{safe_tool_id}_latest.log"
            latest_path.write_text(content, encoding="utf-8")

            logger.info(
                f"[AgenticSkill] Prompt dump 已写入: {latest_path} "
                f"(system={len(system_prompt)}character, user={len(user_prompt)}character, "
                f"helpers={len(fact_report.available_helpers) if fact_report else 0}a)"
            )
        except Exception as exc:
            logger.warning(f"[AgenticSkill] Failed to write prompt dump log: {exc}", exc_info=True)

    @staticmethod
    def _persist_round_snapshot(
        tool_id: str,
        run_id: str,
        round_num: int,
        iteration: IterationRound,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> Optional[Path]:
        """After each iteration, a complete snapshot of the round (including code, ratings, reflections, etc.) will be released immediately."""
        try:
            d = IterationController._get_snapshot_dir(tool_id, run_id)
            snapshot: Dict[str, Any] = {
                "round_number": round_num,
                "decision": iteration.decision,
                "feedback_excerpt": (iteration.feedback or "")[:2000],
            }
            # generated code
            if iteration.generated_code:
                g = iteration.generated_code
                snapshot["generated_code"] = {
                    "code_lines": len((g.code or "").split("\n")),
                    "generation_time": g.generation_time,
                    "metadata": g.metadata,
                }
                # Save the complete code file at the same time
                code_path = d / f"round_{round_num:02d}.py"
                code_path.write_text(
                    (g.code or "") + "\n", encoding="utf-8"
                )
            # Static verification
            if iteration.validation:
                snapshot["validation"] = {
                    "passed": iteration.validation.passed,
                    "errors": iteration.validation.errors[:10],
                }
            # sandbox execution
            if iteration.sandbox:
                sb = iteration.sandbox
                snapshot["sandbox"] = {
                    "success": sb.success,
                    "execution_time": sb.execution_time,
                    "error": (sb.error or "")[:500],
                    "stdout_excerpt": (sb.stdout or "")[:500],
                    "output_excerpt": str(sb.output)[:1000] if sb.output else None,
                }
            # Assessment score
            if iteration.eval_score:
                snapshot["eval_score"] = iteration.eval_score.model_dump()
            # Business acceptance
            if iteration.business_verification:
                bv = iteration.business_verification
                snapshot["business_verification"] = {
                    "passed": bv.passed,
                    "business_score": bv.business_score,
                    "failures": bv.failures[:10],
                }
            # Reflection
            if iteration.reflection:
                r = iteration.reflection
                snapshot["reflection"] = {
                    "root_cause": r.root_cause,
                    "fix_plan": r.fix_plan,
                    "should_retry": r.should_retry,
                    "confidence": r.confidence,
                }
            # Comes with a quote from the current round's scouting report (confidence+A summary of the strategy will suffice)
            if fact_report:
                snapshot["fact_report_summary"] = {
                    "confidence": fact_report.confidence,
                    "strategy": (fact_report.recommended_strategy or "")[:200],
                    "helpers_count": len(fact_report.available_helpers),
                    "checks_count": len(fact_report.validation_checks),
                }

            path = d / f"round_{round_num:02d}_snapshot.json"
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info("📝 The %d round of snapshots has been released: %s", round_num, path)
            return path
        except Exception as exc:
            logger.warning("⚠️ The %d round of snapshot failed to be downloaded to disk: %s", round_num, exc)
            return None

    @staticmethod
    def _persist_stage_artifact(
        tool_id: str,
        run_id: str,
        round_num: int,
        stage: str,
        payload: Dict[str, Any],
        code: str = "",
    ) -> Optional[Path]:
        """Place the order immediately as soon as the stage is completed, making it easier to locate which step you are stuck on."""
        try:
            d = IterationController._get_snapshot_dir(tool_id, run_id)
            stage_payload = {
                "tool_id": tool_id,
                "run_id": run_id,
                "round_number": round_num,
                "stage": stage,
                "updated_at": datetime.utcnow().isoformat(),
                **payload,
            }
            path = d / f"round_{round_num:02d}_{stage}.json"
            path.write_text(
                json.dumps(stage_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            latest_path = d / "latest_stage.json"
            latest_path.write_text(
                json.dumps(stage_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            if code:
                code_path = d / f"round_{round_num:02d}.py"
                code_path.write_text((code or "") + ("" if code.endswith("\n") else "\n"), encoding="utf-8")
            logger.info("📝 Stage results have been settled: %s", path)
            return path
        except Exception as exc:
            logger.warning("⚠️ Stage result placement failed(stage=%s, round=%s): %s", stage, round_num, exc)
            return None

    @staticmethod
    def _build_reconnaissance_updates(fact_report: ImplementationFactReport) -> List[str]:
        updates: List[str] = []
        if fact_report.recommended_strategy:
            updates.append(f"Scouting strategy:{fact_report.recommended_strategy}")

        collections = [
            item.source
            for item in fact_report.schema_facts
            if item.source.startswith("stock_") or item.source == "market_quotes"
        ]
        if collections:
            unique_collections = list(dict.fromkeys(collections))[:3]
            updates.append(f"Hit local collection:{', '.join(unique_collections)}")

        if fact_report.available_helpers:
            helper_names = [f"{item.module}.{item.name}" for item in fact_report.available_helpers[:3]]
            updates.append(f"Recommended helpers:{'; '.join(helper_names)}")

        if fact_report.sample_fields:
            sample_parts: List[str] = []
            for collection, fields in list(fact_report.sample_fields.items())[:2]:
                sample_parts.append(f"{collection}: {', '.join(fields[:6])}")
            if sample_parts:
                updates.append(f"Sample fields:{'; '.join(sample_parts)}")

        if fact_report.runtime_gaps:
            gap_parts = [item.reason for item in fact_report.runtime_gaps[:2] if item.reason]
            if gap_parts:
                updates.append(f"Scouting Tips:{'; '.join(gap_parts)}")

        if fact_report.validation_checks:
            check_parts = [check.field or check.name for check in fact_report.validation_checks[:4]]
            updates.append(f"Dynamic acceptance fields:{', '.join(check_parts)}")

        return updates[:6]

    async def arun(self, spec: SkillSpec) -> PipelineResult:
        """异步版本的 run"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.run, spec)

    # ==================== Failure alarm (v3.6.0 item 6 path A) ====================

    def _write_iteration_alert(
        self,
        *,
        spec: SkillSpec,
        run_id: str,
        iterations: List[IterationRound],
        failure_summary: str,
        total_time: float,
        engine: str = "legacy_pipeline",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """After the iteration fails, it is written to the skill_iteration_alerts collection for display by the front end and waiting for manual decision-making.

        v3.6.0 Item 6 Path A: The original iteration failed and gave up directly, and the user could only view the log;
        Now writing to the MongoDB collection, the front end can display the failure reason and the user can choose:
        - Manually adjust spec and regenerate
        - Give up directly
        - Mark as solved (no more prompts)

        Failure handling strategy:
        - MongoDB Not available → Only log, no blocking return
        - write exception → Only log, no blocking return
        """
        try:
            from app.core.database import get_mongo_db_sync
            from datetime import datetime

            db = get_mongo_db_sync()
            if db is None:
                logger.warning("[IterationAlert] db The handle is empty and the write alarm is skipped.")
                return

            # Extract associated context (session_id / user_id etc.) from spec.metadata
            spec_metadata = getattr(spec, "metadata", None) or {}
            if not isinstance(spec_metadata, dict):
                spec_metadata = {}

            session_id = str(spec_metadata.get("session_id") or spec_metadata.get("skill_session_id") or "")
            user_id = str(spec_metadata.get("user_id") or "")
            workshop_session_id = str(spec_metadata.get("workshop_session_id") or "")
            agent_spec_id = str(spec_metadata.get("agent_spec_id") or "")

            # Collect failure summaries for each round (up to 5 rounds to avoid overly large documents)
            round_summaries = []
            for it in iterations[-5:]:
                round_summaries.append({
                    "round": it.round_number,
                    "decision": it.decision or "",
                    "validation_passed": bool(it.validation.passed) if it.validation else None,
                    "sandbox_success": bool(it.sandbox.success) if it.sandbox else None,
                    "eval_total": float(it.eval_score.total) if it.eval_score else None,
                    "business_passed": bool(it.business_verification.passed) if it.business_verification else None,
                    "root_cause": it.reflection.root_cause if it.reflection else "",
                })

            alert_doc = {
                "alert_id": f"alert_{run_id}_{spec.tool_id}",
                "tool_id": spec.tool_id,
                "display_name": getattr(spec, "display_name", "") or "",
                "description": (getattr(spec, "description", "") or "")[:500],
                "session_id": session_id,
                "workshop_session_id": workshop_session_id,
                "agent_spec_id": agent_spec_id,
                "user_id": user_id,
                "engine": engine,
                "run_id": run_id,
                "total_rounds": len(iterations),
                "total_time_seconds": total_time,
                "failure_summary": failure_summary[:5000],
                "round_summaries": round_summaries,
                "status": "pending_human_review",  # pending_human_review / resolved_give_up / resolved_retry / resolved_manual
                "created_at": datetime.utcnow().isoformat(),
                "extra_metadata": extra_metadata or {},
            }

            result = db.skill_iteration_alerts.update_one(
                {"alert_id": alert_doc["alert_id"]},
                {"$set": alert_doc},
                upsert=True,
            )
            logger.info(
                "[IterationAlert] Alarm written alert_id=%s tool_id=%s rounds=%d matched=%d modified=%d upserted=%s",
                alert_doc["alert_id"],
                spec.tool_id,
                len(iterations),
                result.matched_count,
                result.modified_count,
                result.upserted_id is not None,
            )
        except Exception as exc:
            logger.warning("[IterationAlert] Failed to write alarm (does not block the main process): %s", exc)

    # ==================== Agentic Loop / pipeline_tool ====================

    def run_agentic(
        self,
        spec: SkillSpec,
        initial_feedback: str = "",
        initial_code: str = "",
        progress_callback: Optional[Callable[[str, str, int, float], None]] = None,
        fact_report: Optional[ImplementationFactReport] = None,
        codegen_timeout: Optional[int] = None,
        thinking_callback: Optional[Callable[[str, str], None]] = None,
        iteration_mode: str = "repair",
    ) -> PipelineResult:
        """SkillGeneration Dedicated Agent Loop.

        The outer LLM can call the resident query/probe tool before and after each round of pipeline_tool;pipeline_tool
        Only a single round of candidate generation and quality control is performed, and multiple rounds of retries are not performed internally.

        iteration_mode: "repair"=Directed repair after failure;"upgrade"=Verified in old version
         (initial_code) Make minimal changes to the upgrade, and the first round of code generation carries the upgrade baseline and instructions.
        """
        start_time = time.time()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        iterations: List[IterationRound] = []
        feedback = initial_feedback
        previous_code = initial_code
        verified_facts: List[str] = []
        # Inherit verified facts from reconnaissance reports to avoid repeated exploration by Agentic LLM
        if fact_report:
            for h in (fact_report.available_helpers or [])[:10]:
                sig = (h.signature or "").strip()
                if sig:
                    verified_facts.append(f"{h.name} 签名已验证: {sig[:80]}")
                else:
                    verified_facts.append(f"{h.name} 已验证可用（模块: {h.module}）")
            for f in (fact_report.schema_facts or [])[:8]:
                desc = f.description or f.fact or ""
                if desc:
                    verified_facts.append(desc[:120])
        self._agentic_trace = []
        logger.info(
            "🤖 [AgenticSkill] start tool_id=%s max_steps=%s initial_feedback_chars=%s initial_code_chars=%s fact_report=%s",
            spec.tool_id,
            self._max_iterations,
            len(initial_feedback or ""),
            len(initial_code or ""),
            bool(fact_report),
        )

        def _report(stage: str, message: str, it: int, prog: float, extra: Optional[Dict[str, Any]] = None):
            if progress_callback:
                try:
                    progress_callback(stage, message, it, prog, extra)
                except Exception as e:
                    logger.warning("progress_callback Abnormal: %s", e)

        if fact_report is None:
            try:
                _report("reconnaissance", "正在整理实现事实...", 0, 0.03)
                fact_report = self._reconnaissance.analyze(spec)
                self._persist_fact_report(spec.tool_id, run_id, fact_report)
            except Exception as exc:
                logger.warning("⚠️ Agentic Pre-reconnaissance failed, continue running: %s", exc)
        elif fact_report is not None:
            self._persist_fact_report(spec.tool_id, run_id, fact_report)

        agentic_state = {
            "feedback": feedback,
            "previous_code": previous_code,
            "verified_facts": verified_facts,
            "progress_callback": _report,
            "codegen_timeout": codegen_timeout,
            "thinking_callback": thinking_callback,
        }
        tools = self._build_agentic_tools(
            spec=spec,
            run_id=run_id,
            iterations=iterations,
            fact_report=fact_report,
            state=agentic_state,
            iteration_mode=iteration_mode,
        )
        tool_defs = [ToolCallNormalizer.normalize_tool_definition(func) for func in tools.values()]
        client = self._get_client()
        client.inject_tools(tools)

        known_context = self._extract_known_context_from_spec(spec)
        logger.info(
            "🤖 [AgenticSkill] context tool_id=%s known_failures=%s known_facts=%s tools=%s",
            spec.tool_id,
            len(known_context.get("known_failure_summaries") or []),
            len(known_context.get("known_verified_facts") or []),
            sorted(tools.keys()),
        )
        agentic_system_prompt = self._build_agentic_system_prompt(spec)
        agentic_user_prompt = self._build_agentic_task_prompt(
            spec, initial_feedback, fact_report, known_context,
            parent_code=(initial_code if iteration_mode == "upgrade" else ""),
        )

        # Write the complete agentic prompt to the log file to facilitate troubleshooting the problem that LLM does not call the recommended helper
        self._dump_agentic_prompt_to_logfile(spec, agentic_system_prompt, agentic_user_prompt, fact_report)

        messages: List[Message] = [
            Message(role="system", content=agentic_system_prompt),
            Message(role="user", content=agentic_user_prompt),
        ]

        final_result: Optional[PipelineToolResult] = None
        failure_result: Optional[PipelineToolResult] = None
        stale_failure_counts: Dict[str, int] = {}
        # Exploration rhythm tracking: avoid LLM wasting steps on repeated exploration
        consecutive_explore_steps = 0
        total_explore_steps = 0
        _MAX_CONSECUTIVE_EXPLORE = 2
        _MAX_TOTAL_EXPLORE = 4

        for step in range(1, self._max_iterations + 1):
            _report("agentic_loop", f"Agentic Skill 生成循环第 {step}/{self._max_iterations} 步", step, min(0.05 + step * 0.08, 0.9))
            logger.info(
                "🤖 [AgenticSkill] step=%s/%s tool_id=%s messages=%s verified_facts=%s consecutive_explore=%s total_explore=%s",
                step,
                self._max_iterations,
                spec.tool_id,
                len(messages),
                len(verified_facts),
                consecutive_explore_steps,
                total_explore_steps,
            )
            try:
                response = client.chat(
                    messages,
                    tools=tool_defs,
                    auto_execute_tools=False,
                    max_tokens=2048,
                    temperature=0.2,
                    tool_choice="auto",
                )
            except Exception as exc:
                logger.warning("Agentic Loop LLM The call fails and is downgraded to a single round pipeline_tool: %s", exc)
                tools["pipeline_tool"]()
                failure_result = self._last_agentic_pipeline_result
                if failure_result and failure_result.iteration:
                    iterations.append(failure_result.iteration)
                break

            if response.has_tool_calls:
                tool_names = [str(call.name or "") for call in response.tool_calls]
                # Determine whether this step is called pipeline_tool
                step_called_pipeline = any(name == "pipeline_tool" for name in tool_names)
                logger.info(
                    "🤖 [AgenticSkill] step=%s tool_calls=%s pipeline=%s tool_id=%s",
                    step,
                    tool_names,
                    step_called_pipeline,
                    spec.tool_id,
                )
                messages.append(response.to_message())
                for tool_call in response.tool_calls:
                    result = ToolCallNormalizer.execute_tool_call(tool_call, tools)
                    content = result.content or ""
                    if result.name != "pipeline_tool":
                        fact = self._build_verified_fact_from_tool_result(result.name, content)
                        if fact and fact not in verified_facts:
                            verified_facts.append(fact)
                    self._agentic_trace.append({
                        "step": step,
                        "tool": result.name,
                        "arguments": tool_call.arguments,
                        "is_error": result.is_error,
                        "content_excerpt": content[:2000],
                    })
                    messages.append(Message(
                        role="tool",
                        content=content,
                        tool_call_id=result.tool_call_id,
                        name=result.name,
                    ))
                    if result.name == "pipeline_tool":
                        latest = self._last_agentic_pipeline_result
                        if latest and latest.iteration:
                            if latest.iteration not in iterations:
                                iterations.append(latest.iteration)
                            failure_result = latest
                            logger.info(
                                "🤖 [AgenticSkill] pipeline_result tool_id=%s round=%s status=%s should_retry=%s summary=%s",
                                spec.tool_id,
                                latest.round_number,
                                latest.status,
                                latest.should_retry,
                                (latest.failure_summary or "")[:300],
                            )
                            feedback = latest.failure_summary or feedback
                            previous_code = latest.final_code or previous_code
                            if latest.status == "pass":
                                final_result = latest
                                break
                            if latest.failure_summary:
                                signature = self._stale_failure_signature(latest.failure_summary)
                                stale_failure_counts[signature] = stale_failure_counts.get(signature, 0) + 1
                                messages.append(Message(
                                    role="user",
                                    content=(
                                        "The summary of the previous round of pipeline_tool failures is as follows. Please decide the next step based on it:"
                                        "If you need to check real data, call run_readonly_query. If you need to detect the interface, call probe_interface."
                                        "If you need a diagnostic script, call run_diagnostic_script, and then call pipeline_tool when the information is sufficient.\n"
                                        f"{latest.failure_summary}"
                                    ),
                                ))
                                # Static verification is a purely deterministic check (no ambient noise): the same signature 2 times in a row
                                # This means that LLM cannot be repaired, which is usually a specification-level error (such as an unrealizable parameter name).
                                # Early circuit breaker saves 2-4 minutes of code generation
                                is_static_sig = signature.startswith("静态验证失败")
                                effective_threshold = 2 if is_static_sig else _STALE_FAILURE_THRESHOLD
                                if stale_failure_counts[signature] >= effective_threshold:
                                    blocked_hint = (
                                        "This error is a deterministic verification failure and has not changed after two rounds of retries."
                                        "Most likely it s a specification issue rather than a code issue——Please check if the SkillSpec s parameter definitions are implementable."
                                        if is_static_sig
                                        else ""
                                    )
                                    failure_result = PipelineToolResult(
                                        status="blocked",
                                        round_number=latest.round_number,
                                        failure_summary=(
                                            f"连续 {effective_threshold} 次出现相同失败，触发 stale failure 熔断。"
                                            f"{blocked_hint}\n{latest.failure_summary}"
                                        ),
                                        verified_facts=list(verified_facts),
                                        should_retry=False,
                                    )
                                    logger.warning(
                                        "🤖 [AgenticSkill] stale_failure_blocked tool_id=%s signature=%s count=%s threshold=%s",
                                        spec.tool_id,
                                        signature[:120],
                                        stale_failure_counts[signature],
                                        effective_threshold,
                                    )
                                    break
                            if latest.status == "blocked" or not latest.should_retry:
                                break
                if final_result:
                    break
                if failure_result and (failure_result.status == "blocked" or not failure_result.should_retry):
                    break
                # Exploration rhythm statistics: If pipeline_tool is not called in this step, it is recorded as an exploration step.
                if not step_called_pipeline:
                    consecutive_explore_steps += 1
                    total_explore_steps += 1
                    if consecutive_explore_steps >= _MAX_CONSECUTIVE_EXPLORE or total_explore_steps >= _MAX_TOTAL_EXPLORE:
                        # Inject mandatory reminders to push LLM to call the next step directly pipeline_tool
                        reminder = (
                            f"⚠️ 你已连续探索 {consecutive_explore_steps} 步（累计 {total_explore_steps} 步），"
                            f"Exploration budget exceeded. The next step must be to directly call pipeline_tool to generate code."
                            f"Stop calling exploration tools such as run_readonly_query / probe_interface / run_diagnostic_script / describe_runtime_helper."
                        )
                        messages.append(Message(role="user", content=reminder))
                        logger.warning(
                            "🤖 [AgenticSkill] explore_budget_exceeded tool_id=%s step=%s consecutive=%s total=%s",
                            spec.tool_id, step, consecutive_explore_steps, total_explore_steps,
                        )
                else:
                    # Pipeline_tool has been called to reset the continuous count
                    consecutive_explore_steps = 0
                continue

            content = (response.content or "").strip()
            if content:
                messages.append(Message(role="assistant", content=content))
            if not iterations:
                logger.info("Agentic Loop pipeline_tool was not called, forcing a round of governed builds.")
                tools["pipeline_tool"]()
                failure_result = self._last_agentic_pipeline_result
                if failure_result and failure_result.iteration:
                    iterations.append(failure_result.iteration)
                if failure_result and failure_result.status == "pass":
                    final_result = failure_result
            break

        # Bottom line: If LLM has exhausted all steps and still fails (regardless of whether pipeline_tool has been called), another round of execution will be forced.
        if not final_result:
            last_round = iterations[-1] if iterations else None
            last_feedback = last_round.feedback if last_round else ""
            logger.warning(
                "🤖 [AgenticSkill] LLM After exhausting %s steps and still not passing, another round is forced. pipeline_tool tool_id=%s last_feedback=%s",
                self._max_iterations,
                spec.tool_id,
                (last_feedback[:80] + "...") if last_feedback else "(none)",
            )
            # Write the last round of failure feedback to agentic_state and let pipeline_tool perform directed repairs.
            if last_feedback:
                agentic_state["feedback"] = last_feedback
            tools["pipeline_tool"]()
            failure_result = self._last_agentic_pipeline_result
            if failure_result and failure_result.iteration:
                iterations.append(failure_result.iteration)
            if failure_result and failure_result.status == "pass":
                final_result = failure_result

        total_time = round(time.time() - start_time, 2)
        if final_result:
            _report("output_evaluation", "Agentic Skill Generate via", final_result.round_number, 1.0)
            logger.info(
                "🤖 [AgenticSkill] success tool_id=%s rounds=%s total_time=%.2fs trace_events=%s verified_facts=%s",
                spec.tool_id,
                len(iterations),
                total_time,
                len(self._agentic_trace),
                len(verified_facts),
            )
            return PipelineResult(
                success=True,
                tool_id=spec.tool_id,
                final_code=final_result.final_code,
                final_metadata={
                    **(final_result.final_metadata or {}),
                    "generation_engine": "agentic_loop",
                    "agentic_trace": self._public_agentic_trace(self._agentic_trace),
                    "verified_facts": verified_facts,
                },
                iterations=iterations,
                total_rounds=len(iterations),
                total_time=total_time,
            )

        error = self._build_failure_summary(iterations) if iterations else "Agentic Skill Generate no valid candidate code"
        if failure_result and failure_result.failure_summary:
            error = failure_result.failure_summary + "\n\n" + error
        logger.warning(
            "🤖 [AgenticSkill] failed tool_id=%s rounds=%s total_time=%.2fs trace_events=%s verified_facts=%s error=%s",
            spec.tool_id,
            len(iterations),
            total_time,
            len(self._agentic_trace),
            len(verified_facts),
            error[:500],
        )
        # v3.6.0 Item 6 Path A: Write to the skill_iteration_alerts collection after failure and wait for manual decision-making
        self._write_iteration_alert(
            spec=spec,
            run_id=run_id,
            iterations=iterations,
            failure_summary=error,
            total_time=total_time,
            engine="agentic_loop",
            extra_metadata={
                "agentic_trace": self._public_agentic_trace(self._agentic_trace),
                "verified_facts": verified_facts,
            },
        )
        return PipelineResult(
            success=False,
            tool_id=spec.tool_id,
            iterations=iterations,
            total_rounds=len(iterations),
            total_time=total_time,
            error=error,
            final_metadata={
                "generation_engine": "agentic_loop",
                "agentic_trace": self._public_agentic_trace(self._agentic_trace),
                "verified_facts": verified_facts,
            },
        )

    @property
    def _last_agentic_pipeline_result(self) -> Optional[PipelineToolResult]:
        trace = getattr(self, "_agentic_trace", []) or []
        for item in reversed(trace):
            result = item.get("pipeline_result")
            if isinstance(result, PipelineToolResult):
                return result
        return None

    @_last_agentic_pipeline_result.setter
    def _last_agentic_pipeline_result(self, value: Optional[PipelineToolResult]) -> None:
        if not hasattr(self, "_agentic_trace"):
            self._agentic_trace = []
        if value is None:
            return
        self._agentic_trace.append({
            "event": "pipeline_result",
            "status": value.status,
            "round_number": value.round_number,
            "failure_summary": value.failure_summary[:2000],
            "code_path": value.code_path,
            "snapshot_path": value.snapshot_path,
            "should_retry": value.should_retry,
            "pipeline_result": value,
        })

    @staticmethod
    def _public_agentic_trace(trace: List[Dict[str, Any]], limit: int = 80) -> List[Dict[str, Any]]:
        public_items: List[Dict[str, Any]] = []
        for item in trace[-limit:]:
            public_items.append({
                key: value
                for key, value in item.items()
                if key != "pipeline_result"
            })
        return public_items

    @staticmethod
    def _stale_failure_signature(summary: str) -> str:
        text = " ".join(str(summary or "").split())
        return text[:500]

    @staticmethod
    def _build_verified_fact_from_tool_result(tool_name: str, content: str) -> str:
        if not content:
            return ""
        try:
            data = json.loads(content)
        except Exception:
            return f"{tool_name} returned {len(content)} chars"
        if isinstance(data, dict):
            if data.get("success") is False:
                return f"{tool_name} failed: {str(data.get('error') or '')[:180]}"
            if tool_name == "probe_interface":
                func = data.get("function") or data.get("source_or_helper") or "unknown"
                shape = data.get("shape") or {}
                return f"probe_interface confirmed {func}: {shape}"
            if tool_name == "run_readonly_query":
                collection = data.get("collection") or "unknown"
                return f"run_readonly_query confirmed {collection}: returned_count={data.get('returned_count')}"
            if tool_name == "run_diagnostic_script":
                output = data.get("output") if isinstance(data.get("output"), dict) else {}
                return f"run_diagnostic_script success={data.get('success')}, tool_call_count={output.get('tool_call_count')}"
        return f"{tool_name} returned structured result"

    def _build_agentic_tools(
        self,
        *,
        spec: SkillSpec,
        run_id: str,
        iterations: List[IterationRound],
        fact_report: Optional[ImplementationFactReport],
        state: Dict[str, Any],
        iteration_mode: str = "repair",
    ) -> Dict[str, Callable]:
        from .recon_tools import (
            check_field_coverage,
            describe_runtime_helper,
            inspect_collection_schema,
            inspect_symbol_sample,
            list_analysis_tools,
            list_available_collections,
            list_external_data_sources,
            list_runtime_functions,
            probe_interface,
            run_readonly_query,
        )

        def run_diagnostic_script(script: str) -> str:
            """Execute diagnostic scripts in the build-time sandbox to confirm real fields, interface return shapes, and data coverage.
            You can directly import core.skill_runtime.data_access / core.skill_runtime.project_access in the script to verify the returned shape;
            Reconnaissance functions such as hermes_tools.run_readonly_query / hermes_tools.probe_interface can also be called (for diagnostic purposes only).
            The final Skill code must not rely on hermes_tools and can only use core.skill_runtime.* Public API."""
            logger.info(
                "🤖 [AgenticSkill] diagnostic_script tool_id=%s script_chars=%s",
                spec.tool_id,
                len(script or ""),
            )
            result = self._runner.run_diagnostic_script(script)
            payload = {
                "success": result.success,
                "output": result.output,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
                "execution_time": result.execution_time,
            }
            return json.dumps(payload, ensure_ascii=False, default=str)

        def pipeline_tool() -> str:
            """Perform a round of governed candidate skill generation and quality control.
            A single round includes: code generation, static verification, sandbox execution, Judge scoring, business acceptance and edge testing.
            There is no automatic progression to the next loop within the tool; the next step is determined by the Agent Loop."""
            round_num = len(iterations) + 1
            # Only the first round (based on the parent version code) uses the upgrade copy; after the first round, previous_code has been replaced by
            # The newly generated code in this round belongs to failure repair semantics
            round_mode = "upgrade" if iteration_mode == "upgrade" and round_num == 1 else "repair"
            result = self._run_pipeline_tool_once(
                spec=spec,
                run_id=run_id,
                round_num=round_num,
                feedback=state.get("feedback", ""),
                previous_code=state.get("previous_code", ""),
                fact_report=fact_report,
                progress_callback=state.get("progress_callback"),
                verified_facts=state.get("verified_facts") or [],
                codegen_timeout=state.get("codegen_timeout"),
                thinking_callback=state.get("thinking_callback"),
                iteration_mode=round_mode,
            )
            self._last_agentic_pipeline_result = result
            state["feedback"] = result.failure_summary or state.get("feedback", "")
            if result.final_code:
                state["previous_code"] = result.final_code
            for fact in result.verified_facts:
                if fact not in state["verified_facts"]:
                    state["verified_facts"].append(fact)
            return json.dumps(result.to_public_dict(), ensure_ascii=False, default=str)

        return {
            "pipeline_tool": pipeline_tool,
            "run_diagnostic_script": run_diagnostic_script,
            "run_readonly_query": run_readonly_query,
            "probe_interface": probe_interface,
            "inspect_collection_schema": inspect_collection_schema,
            "inspect_symbol_sample": inspect_symbol_sample,
            "check_field_coverage": check_field_coverage,
            "describe_runtime_helper": describe_runtime_helper,
            "list_runtime_functions": list_runtime_functions,
            "list_analysis_tools": list_analysis_tools,
            "list_available_collections": list_available_collections,
            "list_external_data_sources": list_external_data_sources,
        }

    @staticmethod
    def _build_agentic_system_prompt(spec: Optional[SkillSpec] = None) -> str:
        """Agent Loop Coordinator system prompt, split according to demand type.

        external_api (External interface integration, such as understanding Chedi): remove the local helper reuse/data source tag/
        Local data assumptions such as stock code preflight are replaced with external interface defense rules.
        """
        from .requirement_analyzer import classify_requirement_mode

        mode = classify_requirement_mode(spec) if spec is not None else "local_data"
        if mode == "external_api":
            return """You are a SkillGeneration-specific Agent Loop, not an ordinary chat assistant.
Goal: Generate a registrable Python Skill and pass the platform s hard quality control.

This requirement is for external interface integration: the data comes from an external API (not related to the local stock database). It is not recommended to query the local stock collection or use the local stock data helper.

You can call the tool:
- pipeline_tool: Perform a round of governed candidate code generation and quality control (code generation→Static verification→sandbox execution→rating). This is the core tool and must be called.
- run_readonly_query: Query real sample documents to confirm fields and coverage (only used when fields need to be verified after pipeline_tool fails).
- probe_interface: The actual call has registered helper to confirm the return shape (only used when the interface shape needs to be confirmed after pipeline_tool fails).
- run_diagnostic_script: Execute the build-time diagnostic script, which can be directly import core.skill_runtime.* or core.tools.implementations.* to verify the returned shape.
- list_external_data_sources: List the external data source directories registered in the system.
- inspect_collection_schema / inspect_symbol_sample / check_field_coverage / describe_runtime_helper / list_runtime_functions: Structural exploration tools.

Key rules (in order of priority):
1. Reconnaissance reports (fact_reports) are already prepared for you, containing interface facts, recommended strategies, and validation checks. Please call pipeline_tool directly to generate code and do not repeat reconnaissance.
2. pipeline_tool It is the core tool. Please call pipeline_tool directly in the first round without doing any exploration first.
3. Only when pipeline_tool returns failure_summary and the failure reason is clearly"Field name error""The interface return shape does not match""Data source is not available"Only then use probe_interface / run_diagnostic_script and other tools for targeted verification, and then call pipeline_tool again.
4. The final Skill code must be an independently runnable synchronous pure Python function (async def / await is prohibited);
   Allow using standard HTTP libraries such as requests to directly call external interfaces, and do not import the core.skill_runtime local data module.
   It is prohibited to rely on process tools such as hermes_tools, RPC stub, build-time diagnostic tools, agent_builder/assistant_ops/skill_builder, etc.
5. The interface fields are subject to the actual response: field mapping must come from the response structure confirmed by the reconnaissance report, and inventing field names or paths is prohibited.
6. Don t skip pipeline_tool; only pipeline_tool pass counts as success.
7. If it is confirmed that the external interface cannot provide the target capability (current limitation/authentication/field missing), stop retrying and explain the reason for the blocking.
8. Maximum of 10 steps. Either call pipeline_tool at each step, or do targeted verification instead of aimless exploration.
9. **Explore rhythm constraints**: The number of continuous exploration steps (non-pipeline_tool call) must not exceed 2 steps; the cumulative number of exploration steps must not exceed 4 steps. Pipeline_tool is called at least once every 3 steps.
10. 🛡️ External interface error prevention (generated code must follow to avoid edge test failures):
   - Parameter defense: Return immediately when required parameters are missing or illegal in format {"status": "error", "error_code": "invalid_param", "message": ...}, No network request is initiated.
   - HTTP The call must set a timeout (timeout=10 left and right) and wrap it with try-except; temporarily back off when the current is limited, and do not open interfaces one by one in a loop.
   - Return gracefully when the data is empty:{"status": "success", "data": [], "message": "No xxx data found"}, Never falsify data.
   - Return value consistency: Regardless of success or failure, the returned dict must contain the status field ("success"/"error") . 
   - Exception coverage: The main function body is wrapped with try-except, and a structured error response is returned after catching the exception. Do not throw uncaught exceptions.
   - Edge testing will pass in illegal parameter values, and the code must return an error response within 5 seconds without timeout."""

        return """You are a SkillGeneration-specific Agent Loop, not an ordinary chat assistant.
Goal: Generate a registrable Python Skill and pass the platform s hard quality control.

You can call the tool:
- pipeline_tool: Perform a round of governed candidate code generation and quality control (code generation→Static verification→sandbox execution→rating). This is the core tool and must be called.
- run_readonly_query: Query real sample documents to confirm fields and coverage (only used when fields need to be verified after pipeline_tool fails).
- probe_interface: The actual call has registered helper to confirm the return shape (only used when the interface shape needs to be confirmed after pipeline_tool fails).
- run_diagnostic_script: Execute the build-time diagnostic script, which can be directly import core.skill_runtime.* or core.tools.implementations.* to verify the returned shape.
- list_analysis_tools: List all reusable analysis tools (fundamentals/market/technical/portfolio/risk, etc. 180+ ) and its complete import path. The generated Skill code can be directly from <module_path> import <function_name> Call these tools.
- inspect_collection_schema / inspect_symbol_sample / check_field_coverage / describe_runtime_helper / list_runtime_functions: Structural exploration tools.

Key rules (in order of priority):
1. The recon report (fact_report) is already prepared for you, including available helpers, recommended strategies and validation checks. Please call pipeline_tool directly to generate code and do not repeat reconnaissance.
2. pipeline_tool It is the core tool. Please call pipeline_tool directly in the first round without doing any exploration first.
3. Only when pipeline_tool returns failure_summary and the failure reason is clearly"Field name error""The interface return shape does not match""Data source is not available"Only then use tools such as run_readonly_query / probe_interface / run_diagnostic_script to verify specifically, and then call pipeline_tool again.
4. The final Skill code allows the following modules to be imported:
   - core.skill_runtime.data_access / core.skill_runtime.project_access / core.skill_runtime.standard_financial_apis (Standard data access)
   - core.tools.implementations.fundamentals / market / technical / portfolio / risk / news / social / trade_review / legacy_bridge (180+ analysis tool, shared with the agent workshop)
   It is prohibited to rely on process tools such as hermes_tools, RPC stub, build-time diagnostic tools, agent_builder/assistant_ops/skill_builder, etc.
5. Existing tools must be reused: If there is a tool in fact_report.available_helpers that completes the target capability, it must be directly imported and called, and it is prohibited to implement equivalent data acquisition logic by yourself.
6. **Data source label usage rules** (Decision based on data_source_handling tag of each helper in available_helpers):
   - `self_contained`: helper The self-contained data source has been called. Just call it directly. Do not call additional external data sources to supplement the data.
   - `local_only`: helper Only check the local MongoDB. If the return is empty or there is insufficient data, you need to supplement the external data source call in the skill (such as tushare/akshare/finnhub) or core.skill_runtime.external_sources
   - `partial`: helper Only covers part of the requirements and needs to be used in conjunction with other helpers or supplementary data sources/calculation logic
7. Don t skip pipeline_tool; only pipeline_tool pass counts as success.
8. If it is confirmed that the data source cannot provide the target capability, the retry should be stopped and the reason for the blocking should be explained.
9. Maximum of 10 steps. Either call pipeline_tool at each step, or do targeted verification instead of aimless exploration.
10. **Explore rhythm constraints**: The number of continuous exploration steps (non-pipeline_tool call) must not exceed 2 steps; the cumulative number of exploration steps must not exceed 4 steps. Pipeline_tool is called at least once every 3 steps. If fact_report has given a helper signature, call pipeline_tool directly without verifying with probe_interface first.
11. 🛡️ General error prevention (generated code must follow to avoid edge test failures):
   - Stock code preflight: used at the beginning of the function get_stock_basic_info(symbol) Verify, return immediately if it does not exist {"status": "error", "error_code": "symbol_not_found", "message": ..., "symbol": symbol}, Do not proceed with follow-up inquiries.
   - Return gracefully when the data is empty: Return a structured error response when the key data query result is empty, so that subsequent calculations do not crash.
   - Division-by-zero protection: Use safe division for all ratio calculations (returns None when denominator is 0 or close to 0).
   - Exception coverage: The main function body is wrapped with try-except, and a structured error response is returned after catching the exception. Do not throw uncaught exceptions.
   - Return value consistency: Regardless of success or failure, the returned dict must contain the status field ("success"/"error") and symbol fields.
   - The edge test is passed in a stock symbol that does not exist, and the code must return an error response within 5 seconds without timeout."""

    @staticmethod
    def _extract_known_context_from_spec(spec: SkillSpec) -> Dict[str, List[str]]:
        metadata = getattr(spec, "metadata", None) or {}
        if not isinstance(metadata, dict):
            return {"known_failure_summaries": [], "known_verified_facts": []}
        return {
            "known_failure_summaries": [str(item) for item in list(metadata.get("known_failure_summaries") or []) if str(item).strip()][:5],
            "known_verified_facts": [str(item) for item in list(metadata.get("known_verified_facts") or []) if str(item).strip()][:12],
        }

    @staticmethod
    def _build_agentic_task_prompt(
        spec: SkillSpec,
        initial_feedback: str,
        fact_report: Optional[ImplementationFactReport],
        known_context: Optional[Dict[str, List[str]]] = None,
        parent_code: str = "",
    ) -> str:
        # Extract only key summaries, avoid injecting full fact_report JSON (too large and unfocused)
        recon_digest = ""
        if fact_report:
            parts = []
            # 1. Recommended strategy (1 line)
            if fact_report.recommended_strategy:
                parts.append(f"【推荐策略】\n{fact_report.recommended_strategy}")
            # 2. Authenticated available helper(name + module + signature + Data source labels, 1-2 lines per item)
            if fact_report.available_helpers:
                helper_lines = []
                for h in fact_report.available_helpers[:15]:  # Up to 15
                    sig = (h.signature or "")[:120]  # Signature truncation
                    ds = h.data_source_handling or "self_contained"
                    helper_lines.append(f"- {h.name} | {h.module} | {sig} | 数据源:{ds}")
                parts.append(
                    " [Verified helper is available (no need to repeat exploration)] \n"
                    + "  Data source tag: self_contained=self contained(call directly); local_only=local only MongoDB(May need to supplement external data sources); partial=partial coverage\n"
                    + "\n".join(helper_lines)
                )
            # 3. Verified facts (1 line each, maximum 12)
            if fact_report.schema_facts:
                fact_lines = []
                for f in fact_report.schema_facts[:12]:
                    desc = f.description or f.fact or ""
                    if desc:
                        fact_lines.append(f"- {desc[:150]}")
                if fact_lines:
                    parts.append("【已验证字段事实】\n" + "\n".join(fact_lines))
            # 4. Forbidden paths (1 line each, maximum 5)
            if fact_report.blocked_paths:
                blocked_lines = [f"- {p.path}: {p.reason}" for p in fact_report.blocked_paths[:5]]
                parts.append("【禁止路径】\n" + "\n".join(blocked_lines))
            recon_digest = "\n\n".join(parts) if parts else "(无)"

        known_context = known_context or {}
        known_failures = "\n".join(f"- {item}" for item in list(known_context.get("known_failure_summaries") or [])[:5])
        known_facts = "\n".join(f"- {item}" for item in list(known_context.get("known_verified_facts") or [])[:12])

        # Interface preflight measured facts (external_api mode): shares the same block with codegen user prompt,
        # The coordinator writes feedback accordingly——Wrong guidance such as "Spelling ignored business filtering parameters into the URL" will not be given.
        from .interface_preflight import build_preflight_facts_text

        preflight_block = build_preflight_facts_text(
            (getattr(spec, "metadata", None) or {}).get("interface_preflight")
        )

        # Version upgrade scenario: The parent version is a verified baseline, and the coordinator must plan "minimal changes" instead of redoing it from scratch
        upgrade_block = ""
        if parent_code:
            from .code_generator import CodeGenerator

            parent_snippet = CodeGenerator._format_previous_code_for_prompt(parent_code)
            upgrade_block = f"""
 [⬆️ Version upgrade tasks — This is an upgrade to an existing Skill, not generated from scratch]

Current version code (has been verified and is the baseline for this upgrade):
```python
{parent_snippet}
```

Upgrade planning requirements:
- First identify the differences between the new specifications and the current version (add fields/add parameters/adjust filtering, etc.), and only let pipeline_tool change the difference-related code
- The current version of request construction, paging, retry, response parsing, local filtering, field mapping and other verified logic must be retained, and it is strictly prohibited to instruct pipeline_tool to rewrite
- If the first-round candidate changes the verified logic, follow-up feedback will clearly require a return to the baseline implementation.
"""
        return f"""请完成以下 Skill 生成任务。

【SkillSpec】
{json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)}
{preflight_block}{upgrade_block}
【已有反馈/经验】
{initial_feedback or '(无)'}

【同一次 GapJob 已知失败摘要】
{known_failures or '(无)'}

【同一次 GapJob 已验证环境事实】
{known_facts or '(无)'}

【侦察阶段已验证结果（无需重复探索）】
{recon_digest}

⚠️ 重要：以上 helper 签名和字段事实已在侦察阶段验证过，不要重复调用 describe_runtime_helper / probe_interface / run_diagnostic_script 探索它们。
请直接调用 pipeline_tool 生成并验证候选 Skill。
仅当 pipeline_tool 失败且失败原因涉及"未探索过"的字段名/接口形状/数据源可用性时，才用探索工具针对性核实（最多 2 步），然后立即再次调用 pipeline_tool。"""


    def _run_pipeline_tool_once(
        self,
        *,
        spec: SkillSpec,
        run_id: str,
        round_num: int,
        feedback: str,
        previous_code: str,
        fact_report: Optional[ImplementationFactReport],
        progress_callback: Optional[Callable[[str, str, int, float], None]],
        verified_facts: List[str],
        codegen_timeout: Optional[int] = None,
        thinking_callback: Optional[Callable[[str, str], None]] = None,
        iteration_mode: str = "repair",
    ) -> PipelineToolResult:
        iteration = IterationRound(round_number=round_num)

        def _report(stage: str, message: str, progress: float, extra: Optional[Dict[str, Any]] = None) -> None:
            if progress_callback:
                progress_callback(stage, message, round_num, progress, extra)

        def _finish(status: str, summary: str, should_retry: bool = True) -> PipelineToolResult:
            snapshot_path = self._persist_round_snapshot(spec.tool_id, run_id, round_num, iteration, fact_report)
            code_path = ""
            if iteration.generated_code:
                code_path = str(self._get_snapshot_dir(spec.tool_id, run_id) / f"round_{round_num:02d}.py")
            return PipelineToolResult(
                status=status,
                round_number=round_num,
                iteration=iteration,
                code_path=code_path,
                snapshot_path=str(snapshot_path or ""),
                static_validation=iteration.validation.model_dump() if iteration.validation else {},
                sandbox_result=iteration.sandbox.model_dump() if iteration.sandbox else {},
                evaluation=self._build_pipeline_tool_evaluation(iteration),
                failure_summary=summary,
                verified_facts=list(verified_facts),
                should_retry=should_retry,
                final_code=iteration.generated_code.code if iteration.generated_code else "",
                final_metadata=iteration.generated_code.metadata if iteration.generated_code else {},
            )

        try:
            logger.info(
                "🔁 [pipeline_tool] start tool_id=%s round=%s feedback_chars=%s previous_code_chars=%s verified_facts=%s",
                spec.tool_id,
                round_num,
                len(feedback or ""),
                len(previous_code or ""),
                len(verified_facts or []),
            )
            _report("code_generation", "正在生成代码...", 0.1)
            generated = self._generator.generate(
                spec,
                feedback=feedback,
                previous_code=previous_code,
                fact_report=fact_report,
                timeout_seconds=codegen_timeout,
                on_thinking=thinking_callback,
                iteration_mode=iteration_mode,
            )
            iteration.generated_code = generated
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="code_generation",
                payload={
                    "success": True,
                    "generation_time": generated.generation_time,
                    "code_lines": len((generated.code or "").split("\n")),
                    "metadata": generated.metadata or {},
                    "agentic_loop": True,
                },
                code=generated.code,
            )

            _report("static_validation", "正在语法检查...", 0.25)
            validation = self._validator.validate(generated, spec)
            iteration.validation = validation
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="static_validation",
                payload={"passed": validation.passed, "errors": validation.errors[:20], "warnings": validation.warnings[:20]},
                code=generated.code,
            )
            if not validation.passed:
                logger.warning(
                    "🔁 [pipeline_tool] static_failed tool_id=%s round=%s errors=%s",
                    spec.tool_id,
                    round_num,
                    validation.errors[:5],
                )
                iteration.decision = "RETRY"
                summary = "Static validation failed:" + "；".join(validation.errors[:5])
                iteration.feedback = self._build_rich_feedback(stage="静态验证", errors=validation.errors, code=generated.code, spec=spec)
                return _finish("fail", summary)

            _report("sandbox_execution", "正在沙箱执行...", 0.4)
            sandbox = self._runner.run(generated.code, spec)
            iteration.sandbox = sandbox
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="sandbox_execution",
                payload={
                    "success": sandbox.success,
                    "execution_time": sandbox.execution_time,
                    "error": sandbox.error,
                    "stdout": sandbox.stdout,
                    "stderr": sandbox.stderr,
                    "output": sandbox.output,
                },
                code=generated.code,
            )
            if not sandbox.success:
                logger.warning(
                    "🔁 [pipeline_tool] sandbox_failed tool_id=%s round=%s error=%s stdout_chars=%s stderr_chars=%s",
                    spec.tool_id,
                    round_num,
                    sandbox.error,
                    len(sandbox.stdout or ""),
                    len(sandbox.stderr or ""),
                )
                reflection = self._reflect_on_failure(
                    spec=spec,
                    code=generated.code,
                    stage="沙箱执行",
                    error=sandbox.error or "未知错误",
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    fact_report=fact_report,
                sandbox_success=getattr(sandbox, "success", False),
            )
                iteration.reflection = reflection
                iteration.decision = "FAIL" if not reflection.should_retry else "RETRY"
                iteration.feedback = self._build_rich_feedback(
                    stage="沙箱执行",
                    errors=[sandbox.error or "未知错误"],
                    code=generated.code,
                    spec=spec,
                    stdout=sandbox.stdout,
                    stderr=sandbox.stderr,
                    output=sandbox.output,
                    reflection=reflection,
                )
                return _finish(
                    "blocked" if not reflection.should_retry else "fail",
                    self._build_agentic_failure_summary(iteration),
                    should_retry=reflection.should_retry,
                )

            _report("output_evaluation", "正在质量评估...", 0.65)
            eval_score = self._evaluator.evaluate(sandbox, spec, generated.code, fact_report=fact_report)
            iteration.eval_score = eval_score
            business_verification = self._business_verifiers.resolve(spec).verify(sandbox, spec, fact_report)
            iteration.business_verification = business_verification
            self._persist_stage_artifact(
                tool_id=spec.tool_id,
                run_id=run_id,
                round_num=round_num,
                stage="output_evaluation",
                payload={
                    "eval_score": eval_score.model_dump(),
                    "business_verification": business_verification.model_dump(),
                },
                code=generated.code,
            )
            # The evaluation results are disclosed in real time (including whether the business acceptance is passed)
            _eval_extra = self._build_eval_result_extra(eval_score, round_num)
            _eval_extra["eval_result"]["business_passed"] = business_verification.passed
            _eval_passed = eval_score.total >= PASS_THRESHOLD
            _report(
                "output_evaluation",
                f"Quality assessment completed:{eval_score.total}/10 ({'Meet the standard' if _eval_passed else 'Not up to standard'}) ",
                0.77,
                extra=_eval_extra,
            )

            if self._is_systemic_business_verifier_failure(business_verification):
                iteration.decision = "FAIL"
                summary = "The system-level business acceptance rules are configured incorrectly, and the current failure is not a code implementation defect."
                iteration.feedback = summary
                return _finish("blocked", summary, should_retry=False)

            if eval_score.total >= PASS_THRESHOLD and business_verification.passed:
                logger.info(
                    "🔁 [pipeline_tool] quality_pass tool_id=%s round=%s score=%.2f business_pass=%s",
                    spec.tool_id,
                    round_num,
                    eval_score.total,
                    business_verification.passed,
                )
                _report("edge_testing", "Performing edge test verification...", 0.8)
                edge_failures = self._run_edge_tests(generated.code, spec)
                if edge_failures:
                    reflection = self._reflect_on_failure(
                        spec=spec,
                        code=generated.code,
                        stage="边缘测试",
                        error="\n".join(edge_failures),
                        stdout=sandbox.stdout,
                        stderr="",
                        output=sandbox.output,
                        fact_report=fact_report,
                        sandbox_success=getattr(sandbox, "success", False),
                    )
                    iteration.reflection = reflection
                    iteration.decision = "RETRY"
                    iteration.feedback = self._build_rich_feedback(
                        stage="边缘测试",
                        errors=edge_failures,
                        code=generated.code,
                        spec=spec,
                        stdout=sandbox.stdout,
                        output=sandbox.output,
                        reflection=reflection,
                    )
                    return _finish("fail", self._build_agentic_failure_summary(iteration), should_retry=reflection.should_retry)

                iteration.decision = "PASS"
                result = _finish("pass", "pipeline_tool Passed single round of quality control", should_retry=False)
                logger.info(
                    "🔁 [pipeline_tool] pass tool_id=%s round=%s code_path=%s snapshot=%s",
                    spec.tool_id,
                    round_num,
                    result.code_path,
                    result.snapshot_path,
                )
                _report("output_evaluation", "评估通过", 1.0)
                return result

            failure_messages: List[str] = []
            logger.warning(
                "🔁 [pipeline_tool] quality_failed tool_id=%s round=%s score=%.2f business_pass=%s business_failures=%s",
                spec.tool_id,
                round_num,
                eval_score.total,
                business_verification.passed,
                len(business_verification.failures or []),
            )
            extra_context_parts: List[str] = []
            if eval_score.total < PASS_THRESHOLD:
                failure_messages.extend(self._build_eval_errors(eval_score))
                extra_context_parts.append(self._build_eval_reflection_context(eval_score))
            if not business_verification.passed:
                failure_messages.extend(self._build_business_errors(business_verification))
                extra_context_parts.append(self._build_business_reflection_context(business_verification))
            reflection = self._reflect_on_failure(
                spec=spec,
                code=generated.code,
                stage="质量评估/业务验收",
                error="\n".join(failure_messages),
                stdout=sandbox.stdout,
                stderr=sandbox.stderr,
                output=sandbox.output,
                fact_report=fact_report,
                    sandbox_success=getattr(sandbox, "success", False),
                    extra_context="\n\n".join(part for part in extra_context_parts if part),
            )
            iteration.reflection = reflection
            iteration.decision = "FAIL" if not reflection.should_retry else "RETRY"
            iteration.feedback = self._build_rich_feedback(
                stage="质量评估/业务验收",
                errors=failure_messages,
                code=generated.code,
                spec=spec,
                stdout=sandbox.stdout,
                stderr=sandbox.stderr,
                output=sandbox.output,
                reflection=reflection,
            )
            return _finish(
                "blocked" if not reflection.should_retry else "fail",
                self._build_agentic_failure_summary(iteration),
                should_retry=reflection.should_retry,
            )
        except Exception as exc:
            logger.error("pipeline_tool Single round execution exception: %s", exc, exc_info=True)
            # Exceptions (especially code generation timeouts) must be reported explicitly to the progress stream,
            # Otherwise the front end stays at"Generating code..."Can't see the reason for failure
            exc_text = str(exc)
            is_timeout = "timed out" in exc_text.lower() or "timeout" in exc_text.lower()
            if is_timeout:
                _report(
                    "error",
                    f"第 {round_num} 轮代码生成超时（{codegen_timeout or CODEGEN_LLM_TIMEOUT_SECONDS}s）: {exc_text}。"
                    "You can increase the timeout period and resubmit after the generation fails.",
                    0.95,
                )
            else:
                _report("error", f"第 {round_num} 轮执行异常: {exc_text}", 0.95)
            iteration.decision = "FAIL"
            iteration.feedback = f"pipeline_tool Execution exception: {exc}"
            return _finish("blocked", iteration.feedback, should_retry=False)

    @staticmethod
    def _build_pipeline_tool_evaluation(iteration: IterationRound) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if iteration.eval_score:
            payload["eval_score"] = iteration.eval_score.model_dump()
        if iteration.business_verification:
            payload["business_verification"] = iteration.business_verification.model_dump()
        if iteration.reflection:
            payload["reflection"] = iteration.reflection.model_dump()
        return payload

    @staticmethod
    def _build_agentic_failure_summary(iteration: IterationRound) -> str:
        parts: List[str] = [f"第 {iteration.round_number} 轮失败"]
        if iteration.validation and not iteration.validation.passed:
            parts.append("Static validation failed:" + "；".join(iteration.validation.errors[:5]))
        if iteration.sandbox and not iteration.sandbox.success:
            parts.append(f"Sandbox execution failed:{iteration.sandbox.error or 'unknown error'}")
            if iteration.sandbox.stdout:
                parts.append("stdout Summary:" + IterationController._summarize_text(iteration.sandbox.stdout, max_chars=1000))
            if iteration.sandbox.stderr:
                parts.append("stderr Summary:" + IterationController._summarize_text(iteration.sandbox.stderr, max_chars=1000))
        if iteration.eval_score:
            parts.append(f"Rating:total={iteration.eval_score.total}/10")
        if iteration.business_verification and not iteration.business_verification.passed:
            failures = [failure.message for failure in iteration.business_verification.failures[:5]]
            if failures:
                parts.append("Business acceptance failed:" + "；".join(failures))
        if iteration.reflection:
            parts.append(f"Root cause:{iteration.reflection.root_cause}")
            if iteration.reflection.fix_plan:
                parts.append("Repair plan:" + "；".join(iteration.reflection.fix_plan[:5]))
        return "\n".join(parts)

    # ==================== reflective mechanism ====================

    def _reflect_on_failure(
        self,
        *,
        spec: SkillSpec,
        code: str,
        stage: str,
        error: str,
        stdout: str = "",
        stderr: str = "",
        output: Any = None,
        extra_context: str = "",
        fact_report: Optional[ImplementationFactReport] = None,
        sandbox_success: bool = False,
    ) -> ReflectionResult:
        """LLM Reflection — agentic mode, LLM obtains evidence on demand to analyze root causes and develop remediation plans"""

        # ── Build utility functions (closures)──
        def get_error_info() -> str:
            """Get failure information (stage, error message, stderr)"""
            import json as _json
            info = {
                "stage": stage,
                "error": error[:2000],
                "stderr": (stderr or "")[:2000],
                "extra_context": extra_context[:1000] if extra_context else "",
            }
            return _json.dumps(info, ensure_ascii=False)

        def get_sandbox_logs(lines: int = 30) -> str:
            """Get the last N lines of the sandbox run log"""
            if not stdout:
                return "（无日志）"
            log_lines = stdout.strip().split("\n")
            try:
                lines = int(lines)
            except (TypeError, ValueError):
                lines = 30
            return "\n".join(log_lines[-lines:])

        def get_output() -> str:
            """Get Skill output results"""
            if output is None:
                return "（无输出）"
            try:
                return json.dumps(output, ensure_ascii=False, indent=2, default=str)[:4000]
            except Exception:
                return str(output)[:4000]

        def get_code_section(start_line: int = 1, end_line: int = 50) -> str:
            """获取代码的指定行范围"""
            code_lines = code.split("\n")
            try:
                start_line = int(start_line)
                end_line = int(end_line)
            except (TypeError, ValueError):
                pass
            return "\n".join(code_lines[start_line - 1 : end_line])

        def get_helper_signatures() -> str:
            """Get the confirmed available helper function signature"""
            if not fact_report or not fact_report.available_helpers:
                return "（无 helper）"
            lines = []
            for h in fact_report.available_helpers:
                ds = h.data_source_handling or "self_contained"
                sig = h.signature or "(无签名)"
                lines.append(f"{h.name}: {sig} [数据源:{ds}]")
            return "\n".join(lines)

        tools = {
            "get_error_info": get_error_info,
            "get_sandbox_logs": get_sandbox_logs,
            "get_output": get_output,
            "get_code_section": get_code_section,
            "get_helper_signatures": get_helper_signatures,
        }

        # ── Guided system prompt (tells LLM to diagnose the process instead of random exploration)──
        system_prompt = (
            f"You are an experienced Python developer. Follow this step-by-step process to diagnose Skill tool issues:\n\n"
            f"Skill Function:{spec.description}\n"
            f"Failure stage:{stage}\n"
            f"Sandbox execution status:success={sandbox_success}\n\n"
            f"Diagnosis process (strictly in sequence, only one tool is called for each step):\n"
            f"  Step 1: get_error_info → Understand the type of failure (exception/inconsistent data/low score)\n"
            f"  Step 2: get_sandbox_logs(lines=40) + get_output → View logs and output\n"
            f"  Step 3 (optional): get_code_section → Only used when the first two steps are not sufficient to locate the root cause\n"
            f"  Step 4: output immediately verdict\n\n"
            f"Key rules:\n"
            f"1. sandbox_success=true → The function must exist, the root cause is field mapping/business logic\n"
            f"2. code call helper ≠ Need to change function\n"
            f"3. Total number of tool calls ≤4 times, it must be output after exceeding verdict\n\n"
            f"<verdict>\n"
            f'{{"root_cause": "Specific root cause (which line of code/which field)", "fix_plan": ["steps 1", "steps 2"], '
            f'"should_retry": true/false, "confidence": 0.0-1.0}}\n'
            f"</verdict>"
        )

        try:
            client = self._get_client()
            logger.info(
                f"\n{'─'*50}\n"
                f"📤 [Reflection] Agentic LLM start | tool_id={spec.tool_id}\n"
                f"{'─'*50}"
            )

            # Wrapping LLM calls with thread timeouts
            import threading
            # agentic Reflection involves up to 5 round-trips of tool calls, and requires sufficient time to work with the deep inference model;
            # The previous 120s repeatedly timed out, and the timeout was misjudged as"Not repairable"Terminate iteration directly
            REFLECTION_LLM_TIMEOUT = 300
            response_holder: Dict[str, Any] = {"raw": None, "error": None}

            def _call_reflection_llm() -> None:
                try:
                    from core.llm.tool_normalizer import ToolCallNormalizer

                    client.inject_tools(tools)
                    tool_defs = [
                        ToolCallNormalizer.normalize_tool_definition(func, name=name)
                        for name, func in tools.items()
                    ]
                    messages = [
                        Message(role="system", content=system_prompt),
                        Message(
                            role="user",
                            content="Please follow the above diagnostic process step by step analysis. Start by calling get_error_info.",
                        ),
                    ]
                    resp = client.chat(
                        messages,
                        tools=tool_defs,
                        auto_execute_tools=True,
                        max_tool_rounds=5,
                        temperature=0.2,
                        max_tokens=8192,
                    )
                    response_holder["raw"] = (resp.content or "").strip()
                except Exception as exc:
                    response_holder["error"] = str(exc)

            thread = threading.Thread(target=_call_reflection_llm, daemon=True)
            thread.start()
            thread.join(timeout=REFLECTION_LLM_TIMEOUT)

            if thread.is_alive():
                logger.warning(
                    f"⚠️ [Reflection] LLM call timeout({REFLECTION_LLM_TIMEOUT}s) , skip reflection | tool_id={spec.tool_id}"
                )
                # Reflection timeouts are an infrastructure issue, not"Not repairable"Business judgment:
                # The fallback is to continue retrying (no directed repair plan), and the iteration must not be terminated directly due to reflection timeout.
                return ReflectionResult(
                    root_cause=f"反思 LLM 调用超时（{REFLECTION_LLM_TIMEOUT}s），已跳过反思分析，回退为普通重试",
                    fix_plan=[],
                    should_retry=True,
                    confidence=0.3,
                )

            if response_holder["error"]:
                logger.warning(f"⚠️ [Reflection] LLM call failed: {response_holder['error']}")
                return ReflectionResult(
                    root_cause=f"反思 LLM 调用失败: {response_holder['error']}",
                    fix_plan=[],
                    should_retry=False,
                )

            raw = response_holder["raw"] or ""
            logger.info(
                f"\n{'─'*50}\n"
                f"📥 [Reflection] LLM output ({len(raw)} character)\n"
                f"{'─'*50}\n"
                f"{raw}\n"
                f"{'─'*50}"
            )

            import re
            # Prioritize from <verdict> Extract from tags JSON
            verdict_match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", raw, re.DOTALL)
            if verdict_match:
                json_str = verdict_match.group(1).strip()
            else:
                fallback_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
                json_str = fallback_match.group() if fallback_match else ""

            if json_str:
                data = json.loads(json_str)
                return ReflectionResult(
                    root_cause=data.get("root_cause", "未知"),
                    fix_plan=data.get("fix_plan", []),
                    should_retry=data.get("should_retry", True),
                    confidence=float(data.get("confidence", 0.5)),
                )
        except Exception as e:
            logger.warning(f"LLM Reflection analysis fails, using default feedback: {e}")

        return ReflectionResult(
            root_cause=f"{stage}阶段失败: {error[:200]}",
            fix_plan=["修复上述报错", "确保代码可正常执行"],
            should_retry=True,
            confidence=0.3,
        )

    # ==================== Financial expert judgment ====================

    def _check_no_data_and_advise(
        self,
        spec: SkillSpec,
        sandbox_output: Any,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> str:
        """Check whether the sandbox output contains no_data, and if so, call financial experts to judge the rationality. + Share exchange is recommended.

        Returns expert advice text (used for injecting feedback and extra_context), or an empty string without no_data.
        """
        if not sandbox_output or not isinstance(sandbox_output, dict):
            return ""

        # Detect if there is no_data / no data signal in sandbox output
        output_status = str(sandbox_output.get("status", "")).lower()
        has_no_data_signal = (
            output_status in ("no_data", "no_news", "no_pledge", "error")
            or "无数据" in str(sandbox_output.get("message", ""))
            or "无可用" in str(sandbox_output.get("message", ""))
            or "不可用" in str(sandbox_output.get("message", ""))
        )
        if not has_no_data_signal:
            return ""

        # Check if all numeric fields are null (another no_data signal)
        if output_status == "success":
            profile = sandbox_output.get("profile", {})
            if isinstance(profile, dict):
                null_fields = sum(
                    1 for v in profile.values() if v is None or v == ""
                )
                total_fields = len(profile)
                if total_fields >= 3 and null_fields >= total_fields * 0.7:
                    has_no_data_signal = True

        if not has_no_data_signal:
            return ""

        # Extract test stock information
        test_symbol = (
            spec.test_input.get("symbol")
            or spec.test_input.get("code")
            or str(sandbox_output.get("symbol", ""))
            or ""
        )
        if not test_symbol:
            return ""

        # If fact_report already has expert judgment (made by the reconnaissance layer), reuse it directly
        if fact_report and fact_report.notes:
            expert_notes = [
                n for n in fact_report.notes
                if "专家判断" in n or "推荐测试股票" in n or "建议换股" in n
            ]
            if expert_notes:
                return " [Financial expert judgment (from the reconnaissance layer)]\n" + "\n".join(expert_notes)

        # Call on financial experts to judge
        try:
            from .financial_expert_advisor import get_financial_expert_advisor

            advisor = get_financial_expert_advisor(
                llm_client=self._get_client_safe() if hasattr(self, "_get_client_safe") else self._get_client(),
                provider=self._provider,
                model=self._model,
            )

            # Get basic stock information
            stock_name = ""
            industry = ""
            try:
                from core.skill_runtime.data_access import get_stock_basic_info

                basic = get_stock_basic_info(test_symbol) or {}
                stock_name = basic.get("name", "")
                industry = basic.get("industry", "")
            except Exception:
                pass

            # Infer data type
            data_type = "所需数据"
            helper_name = ""
            if fact_report and fact_report.available_helpers:
                helper_name = fact_report.available_helpers[0].name
                name_lower = helper_name.lower()
                if "pledge" in name_lower:
                    data_type = "质押数据"
                elif "financial" in name_lower or "annual" in name_lower:
                    data_type = "财务数据"
                elif "news" in name_lower or "announcement" in name_lower:
                    data_type = "新闻/公告数据"
                elif "valuation" in name_lower:
                    data_type = "估值数据"

            # helper warnings (extracted from sandbox_output)
            helper_warnings = []
            if isinstance(sandbox_output.get("data_source_note"), str):
                helper_warnings.append(sandbox_output.get("data_source_note"))
            if sandbox_output.get("note"):
                helper_warnings.append(str(sandbox_output.get("note")))

            judgment = advisor.judge_no_data_rationality(
                stock_symbol=test_symbol,
                stock_name=stock_name,
                industry=industry,
                skill_purpose=spec.display_name or spec.description or "",
                data_type=data_type,
                helper_name=helper_name,
                helper_warnings=helper_warnings,
                skill_category=getattr(spec, "category", ""),
            )

            logger.info(
                f"🧠 [financial expert] no_data judge: is_rational={judgment.is_rational}, "
                f"confidence={judgment.confidence:.2f}, stock={test_symbol}"
            )
            return judgment.to_feedback_text()

        except Exception as e:
            logger.warning(f"⚠️ 财经专家判断失败: {e}")
            return ""

    def _get_client_safe(self):
        """Obtain the LLM client safely and return if failed None"""
        try:
            return self._get_client()
        except Exception:
            return None

    # ==================== Standard function reference comparison ====================

    def _compare_with_reference_helpers(
        self,
        sandbox_result: SandboxResult,
        spec: SkillSpec,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> List[str]:
        """
        When the recon layer recommends reusable standard helpers, run these helpers and compare with the Skill output.

        If the Skill output is too different from the standard helper output (for example, the key value field is inconsistent),
        Description The Skill code is not reused/implemented correctly and should return RETRY.
        """
        failures: List[str] = []
        if not fact_report or not fact_report.available_helpers:
            return failures

        # Get test ticker
        test_symbol = spec.test_input.get("symbol") or spec.test_input.get("code") or ""
        if not test_symbol:
            return failures

        for helper in fact_report.available_helpers[:3]:  # Compare up to 3 helpers
            try:
                # Dynamically import and execute standard functions
                reference_result = self._run_reference_helper(
                    helper.module or "", helper.name or "", test_symbol, spec.test_input
                )
                if reference_result is None:
                    continue

                skill_output = sandbox_result.output

                # Extract key numerical fields for comparison
                diffs = self._compare_outputs(helper.name or "", reference_result, skill_output)
                if diffs:
                    failures.extend(diffs)
                    logger.info(
                        f"🔍 [参考对比] {helper.name}: 发现 {len(diffs)} 个差异"
                    )
                else:
                    logger.info(f"✅ [参考对比] {helper.name}: 输出一致，通过")
            except Exception as exc:
                logger.warning(f"⚠️ [参考对比] {helper.name}: 执行失败 {exc}")

        return failures

    @staticmethod
    def _run_reference_helper(
        module: str,
        function_name: str,
        symbol: str,
        test_input: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Dynamically import and execute standard helper functions"""
        try:
            # module Already a full path (such as core.skill_runtime.standard_financial_apis)
            # Use directly, do not repeat splicing
            func = None
            candidate_modules = [module]
            # If module does not start with core., supplement the candidate path
            if not module.startswith("core."):
                candidate_modules.append(f"core.skill_runtime.{module}")
                candidate_modules.append(f"core.tools.implementations.fundamentals.{module}")

            for full_module in candidate_modules:
                try:
                    mod = __import__(full_module, fromlist=[function_name])
                    func = getattr(mod, function_name, None)
                    if func is not None and callable(func):
                        break
                except ImportError:
                    continue

            if func is None or not callable(func):
                logger.warning(f"⚠️ [参考对比] 函数 {function_name} 在 {module} 中未找到")
                return None

            # Call standard functions
            result = func(symbol=symbol)
            if isinstance(result, str):
                import json
                result = json.loads(result)
            return result if isinstance(result, dict) else {"value": result}
        except Exception as e:
            logger.warning(f"⚠️ [参考对比] 执行 {function_name} 失败: {e}")
            return None

    @staticmethod
    def _compare_outputs(
        helper_name: str,
        reference: Dict[str, Any],
        skill_output: Any,
    ) -> List[str]:
        """比较两个输出的关键差异"""
        diffs: List[str] = []

        # Extract numeric fields recursively
        def _extract_numeric(obj: Any, prefix: str = "") -> Dict[str, float]:
            values: Dict[str, float] = {}
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        values[full] = float(v)
                    elif isinstance(v, dict):
                        values.update(_extract_numeric(v, full))
            return values

        ref_values = _extract_numeric(reference)
        skill_values = _extract_numeric(skill_output) if isinstance(skill_output, dict) else {}

        if not ref_values:
            return diffs

        # Find common fields to compare
        common_fields = set(ref_values.keys()) & set(skill_values.keys())
        if not common_fields:
            diffs.append(
                f"[{helper_name}] 标准函数返回 {len(ref_values)} 个数值字段，"
                f"But no matching fields were found in the Skill output, possibly due to inconsistent field naming."
            )
            return diffs

        for field in sorted(common_fields):
            ref_val = ref_values[field]
            skill_val = skill_values[field]

            # Both are 0: all pass (probably a true 0 value)
            if ref_val == 0.0 and skill_val == 0.0:
                continue

            # Reference Value but Skill is 0: Serious problem
            if ref_val != 0.0 and skill_val == 0.0:
                diffs.append(
                    f"[{helper_name}] 字段 {field}: 标准函数={ref_val}, Skill=0 "
                    f"(The data acquisition or calculation logic is incorrect and should not be 0)"
                )
                continue

            # Reference is 0 but Skill has a value: probably OK (Skill provides additional data)
            if ref_val == 0.0 and skill_val != 0.0:
                continue

            # Both have values, compare the difference ratio
            if ref_val != 0.0:
                ratio = abs(skill_val - ref_val) / abs(ref_val)
                if ratio > 0.5:  # difference exceeds 50%
                    diffs.append(
                        f"[{helper_name}] 字段 {field}: 标准函数={ref_val:.4f}, "
                        f"Skill={skill_val:.4f} (difference {ratio:.0%})"
                    )

        return diffs

    # ==================== Edge testing ====================

    def _run_edge_tests(self, code: str, spec: SkillSpec) -> List[str]:
        """
        After the main test passes, run additional edge test scenarios:
        1. Empty/invalid parameter testing — The function should not crash
        2. LLM Generated test cases — Check if there is mock data

        Edge tests use a shorter timeout (10s), enforcing Invalid input returns an error response within 5 seconds. rules.
        """
        failures: List[str] = []

        # Edge tests use separate runners with short timeouts, forcing code to fail quickly on invalid input
        edge_runner = self._get_edge_test_runner()

        edge_inputs = self._generate_edge_inputs(spec)
        for label, test_input in edge_inputs:
            try:
                result = edge_runner.run(code, spec, test_input=test_input)
                if not result.success:
                    # Sandbox execution crashes or times out are considered failures.
                    err_msg = result.error or "未知"
                    if "超时" in err_msg or "timeout" in err_msg.lower():
                        failures.append(
                            f"边缘测试「{label}」超时：代码未在 10s 内对无效输入返回响应，"
                            f"Stock symbol preflight must be done at the beginning of the function and errors returned quickly. Details: {err_msg}"
                        )
                    else:
                        failures.append(f"边缘测试「{label}」执行崩溃: {err_msg}")
                elif result.output is not None:
                    output_str = json.dumps(result.output, ensure_ascii=False, default=str)
                    if self._looks_like_mock_data(output_str):
                        failures.append(f"边缘测试「{label}」返回疑似模拟数据")
            except Exception as e:
                failures.append(f"边缘测试「{label}」异常: {e}")

        return failures

    def _get_edge_test_runner(self):
        """Get a dedicated runner for edge testing (short timeout)."""
        # Lazy loading and caching to avoid creating new instances for every edge test
        if getattr(self, "_edge_runner", None) is None:
            self._edge_runner = SandboxRunner(timeout=10)
        return self._edge_runner

    @staticmethod
    def _generate_edge_inputs(spec: SkillSpec) -> List[tuple]:
        """Generate edge test input according to spec parameter definition"""
        edges: List[tuple] = []

        has_symbol = any(
            p.name in ("symbol", "ticker", "stock_code", "code")
            for p in spec.parameters
        )
        if has_symbol:
            edge_args = dict(spec.test_input) if spec.test_input else {}
            symbol_key = next(
                (p.name for p in spec.parameters
                 if p.name in ("symbol", "ticker", "stock_code", "code")),
                None,
            )
            if symbol_key:
                edge_args[symbol_key] = "999999"
                edges.append(("不存在的股票代码", edge_args))

        return edges

    @staticmethod
    def _looks_like_mock_data(output_str: str) -> bool:
        mock_indicators = [
            '"mock"', '"模拟"', '"fake"', '"dummy"', '"placeholder"',
            '"示例数据"', '"测试数据"', '"sample"',
            "_generate_mock", "generate_fake", "random.uniform",
        ]
        lower = output_str.lower()
        return any(ind.lower() in lower for ind in mock_indicators)

    # ==================== failure report ====================

    @staticmethod
    def _build_failure_summary(iterations: List[IterationRound]) -> str:
        """
        Summarize the failure reasons of all iteration rounds and generate a structured failure report.
        """
        parts = [f"经过 {len(iterations)} 轮迭代仍未达到质量标准（≥{PASS_THRESHOLD}/10 分）。各轮失败原因如下：\n"]

        for it in iterations:
            header = f"【第 {it.round_number} 轮 — 决策: {it.decision or 'UNKNOWN'}】"
            parts.append(header)

            if it.validation and not it.validation.passed:
                parts.append(f"  静态验证失败:")
                for err in it.validation.errors[:3]:
                    parts.append(f"    - {err}")

            if it.sandbox and not it.sandbox.success:
                parts.append(f"  沙箱执行失败: {it.sandbox.error or '未知错误'}")

            if it.eval_score:
                parts.append(
                    f"  评分: 总分={it.eval_score.total}, "
                    f"Enforceability={it.eval_score.executability}, "
                    f"authenticity={it.eval_score.authenticity}, "
                    f"integrity={it.eval_score.completeness}, "
                    f"Relevance={it.eval_score.relevance}, "
                    f"Format={it.eval_score.format_quality}"
                )
                weak = []
                if it.eval_score.executability < 8.0:
                    weak.append(f"可执行性({it.eval_score.executability})")
                if it.eval_score.authenticity < 8.0:
                    weak.append(f"真实性({it.eval_score.authenticity})")
                if it.eval_score.completeness < 8.0:
                    weak.append(f"完整性({it.eval_score.completeness})")
                if it.eval_score.relevance < 8.0:
                    weak.append(f"相关性({it.eval_score.relevance})")
                if it.eval_score.format_quality < 8.0:
                    weak.append(f"格式质量({it.eval_score.format_quality})")
                if weak:
                    parts.append(f"  不达标维度: {', '.join(weak)}")

            if it.business_verification:
                parts.append(
                    f"  Business acceptance: passed={it.business_verification.passed}, "
                    f"business_score={it.business_verification.business_score}"
                )
                if it.business_verification.failures:
                    parts.append(
                        "  业务失败项: "
                        + "; ".join(f.message for f in it.business_verification.failures[:5])
                    )

            if it.reflection and it.reflection.root_cause:
                parts.append(f"  根因分析: {it.reflection.root_cause}")

            parts.append("")

        return "\n".join(parts).strip()

    @staticmethod
    def _build_business_errors(result: BusinessVerificationResult) -> List[str]:
        errors = [failure.message for failure in result.failures]
        if not errors and not result.passed:
            errors.append("业务验收未通过")
        return errors

    @staticmethod
    def _build_business_reflection_context(result: BusinessVerificationResult) -> str:
        lines = [
            f"- 业务验收通过: {result.passed}",
            f"- 业务分: {result.business_score}/10",
            f"- 验收器: {result.details.get('verifier', 'unknown')}",
        ]
        if result.failures:
            lines.append("- 失败规则:")
            for failure in result.failures[:5]:
                lines.append(f"  - {failure.rule_id}: {failure.message}")
        if result.warnings:
            lines.append("- 警告:")
            for warning in result.warnings[:5]:
                lines.append(f"  - {warning}")
        return "\n".join(lines)

    @staticmethod
    def _is_systemic_business_verifier_failure(result: BusinessVerificationResult) -> bool:
        unsupported = result.details.get("unsupported_rule_types") or []
        if unsupported:
            return True
        return any("未支持的业务验收规则类型" in failure.message for failure in result.failures)

    @staticmethod
    def _format_code_for_prompt(
        code: str,
        *,
        max_chars: int = 12000,
        full_code_line_limit: int = 260,
        head_lines: int = 140,
        tail_lines: int = 100,
    ) -> str:
        """Prioritize retaining the complete code for the reflection phase, and retain the first and last key fragments if it is too long."""
        if not code:
            return ""

        lines = code.splitlines()
        if len(code) <= max_chars and len(lines) <= full_code_line_limit:
            return code

        if len(lines) <= head_lines + tail_lines:
            combined = code
        else:
            combined = (
                "\n".join(lines[:head_lines])
                + f"\n# ... (中间省略，共 {len(lines)} 行) ...\n"
                + "\n".join(lines[-tail_lines:])
            )

        if len(combined) <= max_chars:
            return combined

        keep_each_side = max((max_chars - 32) // 2, 1000)
        return (
            combined[:keep_each_side]
            + "\n# ... (Omit the middle) ...\n"
            + combined[-keep_each_side:]
        )

    @staticmethod
    def _build_eval_reflection_context(score) -> str:
        """Explicitly pass the assessment scores to the reflection model to avoid it only seeing a deficient total score."""
        lines = [
            f"- 总分: {score.total}/10（阈值: {PASS_THRESHOLD}）",
            f"- 可执行性: {score.executability}/10",
            f"- 真实性: {score.authenticity}/10",
            f"- 完整性: {score.completeness}/10",
            f"- 相关性: {score.relevance}/10",
            f"- 格式质量: {score.format_quality}/10",
        ]

        weak_dims = []
        if score.executability < PASS_THRESHOLD:
            weak_dims.append(f"可执行性({score.executability})")
        if score.authenticity < PASS_THRESHOLD:
            weak_dims.append(f"真实性({score.authenticity})")
        if score.completeness < PASS_THRESHOLD:
            weak_dims.append(f"完整性({score.completeness})")
        if score.relevance < PASS_THRESHOLD:
            weak_dims.append(f"相关性({score.relevance})")
        if score.format_quality < PASS_THRESHOLD:
            weak_dims.append(f"格式质量({score.format_quality})")

        if weak_dims:
            lines.append(f"- 不达标维度: {', '.join(weak_dims)}")

        return "\n".join(lines)

    # ==================== feedback build ====================

    @staticmethod
    def _summarize_text(
        text: Any,
        *,
        max_chars: int,
        head_chars: Optional[int] = None,
        separator: str = "\n... (Omit the middle) ...\n",
    ) -> str:
        """By default, the beginning and end of long text are retained to avoid truncation of exception information at the end of execution."""
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
    def _build_rich_feedback(
        *,
        stage: str,
        errors: List[str],
        code: str,
        spec: SkillSpec,
        stdout: str = "",
        stderr: str = "",
        output: Any = None,
        reflection: Optional[ReflectionResult] = None,
    ) -> str:
        """
        Build rich feedback context — Contains complete execution information and LLM reflection analysis.
        """
        parts = [f" [{stage}failed — Nth round of iteration feedback]"]

        parts.append("\n## 错误详情")
        for e in errors[:8]:
            parts.append(f"  - {e}")

        if stdout:
            stdout_excerpt = IterationController._summarize_text(
                stdout,
                max_chars=2200,
                head_chars=1200,
            )
            parts.append(f"\n## standard output (stdout Summary)\n{stdout_excerpt}")

            # Extract helper return structure information (key: tell the code generator which fields the helper actually returns)
            helper_return_keys = IterationController._extract_helper_return_keys(stdout)
            if helper_return_keys:
                parts.append(f"\n## Helper actual return field (🚨 The code must match these field names)\n{helper_return_keys}")

        if stderr:
            stderr_excerpt = IterationController._summarize_text(
                stderr,
                max_chars=2200,
                head_chars=1200,
            )
            parts.append(f"\n## standard error (stderr Summary)\n{stderr_excerpt}")

        if output is not None:
            try:
                output_str = IterationController._summarize_text(
                    json.dumps(output, ensure_ascii=False, indent=2, default=str),
                    max_chars=2500,
                    head_chars=1500,
                )
            except Exception:
                output_str = IterationController._summarize_text(
                    output,
                    max_chars=2500,
                    head_chars=1500,
                )
            parts.append(f"\n## 函数实际返回值\n{output_str}")

        if reflection:
            parts.append(f"\n## AI 根因分析\n{reflection.root_cause}")
            if reflection.fix_plan:
                parts.append("\n## 修复计划")
                for i, step in enumerate(reflection.fix_plan, 1):
                    parts.append(f"  {i}. {step}")

        parts.append("\n## 修复要求")
        parts.append("Please fix the problems in the code in a targeted manner based on the complete execution context above.")
        parts.append("Prioritize addressing the root causes of failure rather than redesigning the entire architecture.")
        parts.append("Keep the parts that already work correctly and only modify the problematic code.")
        parts.append("⚠️ Prioritize fixing data acquisition and business logic issues, do not just adjust the status field value to avoid acceptance.")

        return "\n".join(parts)

    @staticmethod
    def _build_eval_result_extra(score, round_num: int) -> Dict[str, Any]:
        """Construct real-time event data for quality assessment (for front-end display at the moment the assessment is completed)."""
        data = score.model_dump()
        # total Yes @property, model_dump Not included, needs to be brought out explicitly
        data["total"] = score.total
        data["round"] = round_num
        data["passed"] = score.total >= PASS_THRESHOLD
        return {"eval_result": data}

    @staticmethod
    def _build_eval_errors(score) -> List[str]:
        """根据评分构建具体问题列表"""
        errors = []
        if score.executability < 7.0:
            errors.append(f"可执行性不足 ({score.executability}/10)")
        if score.authenticity < 7.0:
            errors.append(f"返回数据不够真实 ({score.authenticity}/10)")
        if score.completeness < 7.0:
            errors.append(f"功能不够完整 ({score.completeness}/10)")
        if score.relevance < 7.0:
            errors.append(f"与需求相关性不足 ({score.relevance}/10)")
        if score.format_quality < 7.0:
            errors.append(f"输出格式质量不足 ({score.format_quality}/10)")
        return errors or [f"综合评分 {score.total}/10 低于阈值 {PASS_THRESHOLD}"]

    @staticmethod
    def _build_feedback(stage: str, errors: list) -> str:
        """Simple feedback for older versions (compatibility preserved)"""
        error_lines = "\n".join(f"  - {e}" for e in errors[:5])
        return f"【{stage}失败】\n{error_lines}"

    @staticmethod
    def _build_eval_feedback(score) -> str:
        """Old version rating feedback (compatibility preserved)"""
        parts = []
        if score.executability < 7.0:
            parts.append(f"可执行性不足 ({score.executability}/10)")
        if score.authenticity < 7.0:
            parts.append(f"返回数据不够真实 ({score.authenticity}/10)")
        if score.completeness < 7.0:
            parts.append(f"功能不够完整 ({score.completeness}/10)")
        if score.relevance < 7.0:
            parts.append(f"与需求相关性不足 ({score.relevance}/10)")
        if score.format_quality < 7.0:
            parts.append(f"输出格式质量不足 ({score.format_quality}/10)")
        feedback_lines = "\n".join(f"  - {p}" for p in parts)
        return f"【评分不足 ({score.total}/10)】\n{feedback_lines}\n请针对以上维度改进代码。"

    @staticmethod
    def _extract_helper_return_keys(stdout: str) -> str:
        """Extract the return structure (field names) of the helper function from the sandbox stdout to help the code generator map it correctly"""
        import re
        # match "📊 xxx Return structure: ['field1', 'field2', ...]" or "returned keys: ['field1', ...]"
        pattern = re.compile(r"(?:Return structure|returned keys|return key).*?\[([^\]]+)\]", re.IGNORECASE)
        matches = pattern.findall(stdout)
        if not matches:
            # Also try matching pure "keys: ['...']" Format
            pattern2 = re.compile(r"(?:keys|Field)[: :]\s*\[([^\]]+)\]", re.IGNORECASE)
            matches = pattern2.findall(stdout)

        if not matches:
            return ""

        lines = []
        seen_keys = set()
        for m in matches:
            keys_str = m.strip()
            # Parse key list
            keys = [k.strip().strip("'\"") for k in keys_str.split(",") if k.strip().strip("'\"")]
            key_sig = ", ".join(keys[:12])  # Up to 12 fields
            if key_sig and key_sig not in seen_keys:
                seen_keys.add(key_sig)
                lines.append(f"  [{key_sig}]")

        if not lines:
            return ""
        return "\n".join(lines[:5])  # Return structure for up to 5 helpers
