# -*- coding: utf-8 -*-
"""Pipeline timeout control and Judge model hierarchical testing.

Background: Code generation using the deep thinking model often takes 3-6 minutes, and the default timeout is 240s and is triggered multiple times.
"Request timed out", And the OpenAI SDK timed out message (timed out) and retry keyword
 (timeout) Mismatch results in never retrying; Judge quality assessment is a judgment task but is bound
Think about models. This group of tests covers: retry after timeout, Judge s fast model, code generation
Timeout can be overridden on a per-time basis.
"""
from types import SimpleNamespace

from core.tools.external.code_generator import (
    CODEGEN_LLM_TIMEOUT_SECONDS,
    CodeGenerator,
)
from core.tools.external.output_evaluator import OutputEvaluator
from core.utils.retry import is_retryable


class _FakeClient:
    def __init__(self, content: str = "ok", raise_exc: Exception | None = None):
        self._content = content
        self._raise = raise_exc
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self._raise:
            raise self._raise
        return SimpleNamespace(content=self._content)


# ---------- Retry after timeout ----------

def test_openai_timeout_message_is_retryable():
    # OpenAI SDK The timeout message is "Request timed out." (timed out two words),
    # Previously, the keyword list only had "timeout" As a result, the match cannot be matched and never retried.
    assert is_retryable(Exception("Request timed out.")) is True
    assert is_retryable(Exception("APITimeoutError: Request timed out.")) is True
    assert is_retryable(Exception("Read timeout")) is True


def test_non_retryable_error_still_not_retried():
    assert is_retryable(Exception("Error code: 403 - AccountOverdueError")) is False
    assert is_retryable(ValueError("bad spec")) is False


# ---------- Judge Go fast model ----------

def test_judge_uses_quick_model():
    quick, main = _FakeClient("<verdict>{}</verdict>"), _FakeClient("<verdict>{}</verdict>")
    evaluator = OutputEvaluator(llm_client=main, quick_llm_client=quick)

    out = evaluator._call_judge_llm_simple("Evaluation output", "tid")

    assert out == "<verdict>{}</verdict>"
    assert quick.calls == 1
    assert main.calls == 0


def test_judge_falls_back_to_main():
    quick = _FakeClient(raise_exc=RuntimeError("Error code: 403"))
    main = _FakeClient("<verdict>{}</verdict>")
    evaluator = OutputEvaluator(llm_client=main, quick_llm_client=quick)

    out = evaluator._call_judge_llm_simple("Evaluation output", "tid")

    assert out == "<verdict>{}</verdict>"
    assert main.calls == 1


def test_judge_without_quick_uses_main():
    main = _FakeClient("<verdict>{}</verdict>")
    evaluator = OutputEvaluator(llm_client=main)

    out = evaluator._call_judge_llm_simple("Evaluation output", "tid")

    assert out == "<verdict>{}</verdict>"
    assert main.calls == 1


# ---------- Code generation timeout pay-per-view coverage ----------

class _FakeAdapterClient:
    """Fake client with adapter/config structure for authentication timeout override"""

    def __init__(self, timeout: int):
        self._adapter = SimpleNamespace(
            config=SimpleNamespace(timeout=timeout),
            initialize=lambda: None,
        )


def test_codegen_default_timeout_is_480():
    assert CODEGEN_LLM_TIMEOUT_SECONDS == 480


def test_codegen_get_client_overrides_timeout():
    client = _FakeAdapterClient(timeout=240)
    generator = CodeGenerator(llm_client=client)  # type: ignore[arg-type]

    generator._get_client(timeout_seconds=900)

    assert client._adapter.config.timeout == 900


def test_codegen_get_client_resets_to_smaller_timeout():
    # Users can adjust the timeout smaller (for example, after switching to a fast model). It cannot just increase the timeout but not decrease it.
    client = _FakeAdapterClient(timeout=900)
    generator = CodeGenerator(llm_client=client)  # type: ignore[arg-type]

    generator._get_client(timeout_seconds=120)

    assert client._adapter.config.timeout == 120
