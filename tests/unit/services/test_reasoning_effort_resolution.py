"""
Test reasoning_effort gear mapping and merging logic (A1: deep gear × inference budget)
"""
import pytest

from tradingagents.graph.trading_graph import (
    resolve_reasoning_efforts,
    _lower_reasoning_effort,
)


class TestLowerReasoningEffort:
    """Fast model downshift function"""

    def test_lower_two_steps(self):
        assert _lower_reasoning_effort("xhigh") == "medium"  # idx5 - 2 = idx3
        assert _lower_reasoning_effort("high") == "low"      # idx4 - 2 = idx2

    def test_floor_is_minimal(self):
        # minimal(idx1)/low(idx2) After downgrading two gears, it will not be lower than minimal(idx1), not lowered to none
        assert _lower_reasoning_effort("minimal") == "minimal"
        assert _lower_reasoning_effort("low") == "minimal"

    def test_none_passthrough(self):
        assert _lower_reasoning_effort(None) is None

    def test_unknown_value_passthrough(self):
        assert _lower_reasoning_effort("weird-value") == "weird-value"


class TestResolveReasoningEfforts:
    """Provider injection and DB priority of gear default value"""

    def test_non_volcengine_provider_not_injected(self):
        """Non-volcano manufacturers: gears are not injected by default"""
        config = {"llm_provider": "dashscope", "depth_reasoning_effort": "high"}
        quick, deep = resolve_reasoning_efforts(config, {}, {})
        assert quick is None
        assert deep is None

    def test_volcengine_coding_not_injected(self):
        """Coding Plan The default is not to inject the gear (code model semantics are different)"""
        config = {"llm_provider": "volcengine_coding", "depth_reasoning_effort": "high"}
        quick, deep = resolve_reasoning_efforts(config, {}, {})
        assert quick is None
        assert deep is None

    def test_volcengine_agent_plan_injected(self):
        """Agent Plan: deep Get the gear value, quick down two gears"""
        config = {"llm_provider": "volcengine", "depth_reasoning_effort": "high"}
        quick, deep = resolve_reasoning_efforts(config, {}, {})
        assert deep == "high"
        assert quick == "low"  # high(idx4) - 2 = low(idx2)

    def test_db_explicit_effort_takes_precedence(self):
        """DB Explicit effort in model configuration takes precedence over gear defaults"""
        config = {"llm_provider": "volcengine", "depth_reasoning_effort": "high"}
        quick_cfg = {"reasoning_effort": "max"}
        deep_cfg = {"reasoning_effort": "xhigh"}
        quick, deep = resolve_reasoning_efforts(config, quick_cfg, deep_cfg)
        assert quick == "max"
        assert deep == "xhigh"

    def test_mixed_provider_mode(self):
        """Mixed mode: quick/deep are judged separately when coming from different manufacturers."""
        config = {
            "llm_provider": "dashscope",
            "quick_provider": "dashscope",
            "deep_provider": "volcengine",
            "depth_reasoning_effort": "xhigh",
        }
        quick, deep = resolve_reasoning_efforts(config, {}, {})
        assert quick is None       # dashscope Not injected
        assert deep == "xhigh"     # Get the gear value of the volcano depth model

    def test_no_depth_effort_returns_db_values(self):
        """When there is no gear mapping, the DB value is returned as is (backwards compatible)"""
        config = {"llm_provider": "volcengine"}
        quick_cfg = {"reasoning_effort": "medium"}
        deep_cfg = {"reasoning_effort": "high"}
        quick, deep = resolve_reasoning_efforts(config, quick_cfg, deep_cfg)
        assert quick == "medium"
        assert deep == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
