"""A3 Investment debate parallel opening unit test

Coverage:
- _merge_debate_states: Debate status merging rules (history splicing order / non-null values first)
- _create_parallel_opening_node_func: Parallel execution, independent field merging,
  Share debate_state deep merge, count increment
- WorkflowAPI._prepare_inputs: Parallel deployment switch injection (default/env fallback/input override)
"""

import os
from types import SimpleNamespace

import pytest

from core.workflow.builder import WorkflowBuilder


# ==================== _merge_debate_states ====================

class TestMergeDebateStates:
    def test_old_empty_returns_new_copy(self):
        new = {"history": "Bull Analyst: A", "bull_history": "Bull Analyst: A"}
        merged = WorkflowBuilder._merge_debate_states(None, new)
        assert merged == new
        assert merged is not new

    def test_history_concat_in_speaker_order(self):
        old = {
            "history": "Bull Analyst: point of view A",
            "bull_history": "Bull Analyst: point of view A",
            "current_response": "Bull Analyst: point of view A",
        }
        new = {
            "history": "Bear Analyst: point of view B",
            "bear_history": "Bear Analyst: point of view B",
            "current_response": "Bear Analyst: point of view B",
        }
        merged = WorkflowBuilder._merge_debate_states(old, new)
        assert merged["history"] == "Bull Analyst: point of view A\nBear Analyst: point of view B"
        assert merged["bull_history"] == "Bull Analyst: point of view A"
        assert merged["bear_history"] == "Bear Analyst: point of view B"
        # The latest speaker is the speaker
        assert merged["current_response"] == "Bear Analyst: point of view B"

    def test_nonempty_wins_over_empty(self):
        """Both parallel parties are based on the same initial state copy, and the bull_history in the bear result is empty.
        Cannot overwrite merged non-null bull_history"""
        old = {"history": "Bull Analyst: A", "bull_history": "Bull Analyst: A"}
        new = {
            "history": "Bear Analyst: B",
            "bear_history": "Bear Analyst: B",
            "bull_history": "",  # bear Copied from initial state, bull_history is empty
        }
        merged = WorkflowBuilder._merge_debate_states(old, new)
        assert merged["bull_history"] == "Bull Analyst: A"
        assert merged["bear_history"] == "Bear Analyst: B"


# ==================== _create_parallel_opening_node_func ====================

def _make_builder_with_stubs(stub_results):
    """Construct a WorkflowBuilder that skips __init__ and stubs it out _create_node_function"""
    builder = object.__new__(WorkflowBuilder)
    calls = []

    def fake_create_node_function(node):
        pid = node.id

        def fn(state):
            calls.append(pid)
            return stub_results[pid]

        return fn

    builder._create_node_function = fake_create_node_function
    return builder, calls


class TestParallelOpeningNode:
    BULL_RESULT = {
        "bull_report": "optimistic briefing",
        "investment_debate_state": {
            "history": "Bull Analyst: point of view A",
            "bull_history": "Bull Analyst: point of view A",
            "current_response": "Bull Analyst: point of view A",
        },
    }
    BEAR_RESULT = {
        "bear_report": "Prudential Briefing",
        "investment_debate_state": {
            "history": "Bear Analyst: point of view B",
            "bear_history": "Bear Analyst: point of view B",
            "current_response": "Bear Analyst: point of view B",
        },
    }

    def _build_node_func(self):
        stub_results = {
            "bull_researcher": dict(self.BULL_RESULT),
            "bear_researcher": dict(self.BEAR_RESULT),
        }
        builder, calls = _make_builder_with_stubs(stub_results)
        config = {
            "participants": ["bull_researcher", "bear_researcher"],
            "rounds": 2,
            "next_node": "research_manager",
            "debate_key": "_debate_debate_count",
        }
        definition = SimpleNamespace(
            get_node=lambda pid: SimpleNamespace(id=pid)
        )
        node_func = builder._create_parallel_opening_node_func(
            "debate", config, definition
        )
        return node_func, calls

    def test_all_participants_executed(self):
        node_func, calls = self._build_node_func()
        node_func({"investment_debate_state": {"history": "", "count": 0}})
        assert sorted(calls) == ["bear_researcher", "bull_researcher"]

    def test_independent_fields_merged(self):
        node_func, _ = self._build_node_func()
        result = node_func({"investment_debate_state": {"history": "", "count": 0}})
        assert result["bull_report"] == "optimistic briefing"
        assert result["bear_report"] == "Prudential Briefing"

    def test_debate_state_deep_merged(self):
        node_func, _ = self._build_node_func()
        result = node_func({"investment_debate_state": {"history": "", "count": 0}})
        ds = result["investment_debate_state"]
        assert ds["history"] == "Bull Analyst: point of view A\nBear Analyst: point of view B"
        assert ds["bull_history"] == "Bull Analyst: point of view A"
        assert ds["bear_history"] == "Bear Analyst: point of view B"

    def test_count_increment_equals_participants(self):
        node_func, _ = self._build_node_func()
        result = node_func({"investment_debate_state": {"history": "", "count": 0}})
        assert result["_debate_debate_count"] == 2

    def test_missing_debate_state_falls_back_to_input(self):
        """When none of the participants returns debate_state, the initial value of the input is used. state"""
        stub_results = {
            "bull_researcher": {"bull_report": "x"},
            "bear_researcher": {"bear_report": "y"},
        }
        builder, _ = _make_builder_with_stubs(stub_results)
        config = {
            "participants": ["bull_researcher", "bear_researcher"],
            "rounds": 1,
            "next_node": "research_manager",
            "debate_key": "_debate_debate_count",
        }
        definition = SimpleNamespace(get_node=lambda pid: SimpleNamespace(id=pid))
        node_func = builder._create_parallel_opening_node_func(
            "debate", config, definition
        )
        initial = {"history": "", "count": 0}
        result = node_func({"investment_debate_state": initial})
        assert result["investment_debate_state"] == initial
        assert result["_debate_debate_count"] == 2


# ==================== Switch injection (workflow_api._prepare_inputs) ====================

class TestParallelOpeningSwitch:
    def _prepare(self, inputs=None, monkeypatch=None):
        from core.api.workflow_api import WorkflowAPI

        api = object.__new__(WorkflowAPI)
        if monkeypatch is not None:
            monkeypatch.delenv("RESEARCH_PARALLEL_OPENING", raising=False)
        return api._prepare_inputs(inputs or {"research_depth": "Depth"})

    def test_default_on(self, monkeypatch):
        prepared = self._prepare(monkeypatch=monkeypatch)
        assert prepared["_parallel_opening"] is True

    def test_env_off_forces_off(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PARALLEL_OPENING", "off")
        prepared = self._prepare()
        assert prepared["_parallel_opening"] is False

    def test_env_on_overrides_explicit_input(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PARALLEL_OPENING", "on")
        prepared = self._prepare({"research_depth": "fast", "parallel_opening": False})
        assert prepared["_parallel_opening"] is True

    def test_input_override_when_env_auto(self, monkeypatch):
        monkeypatch.delenv("RESEARCH_PARALLEL_OPENING", raising=False)
        prepared = self._prepare({"research_depth": "Standard", "parallel_opening": False})
        assert prepared["_parallel_opening"] is False

    def test_all_depths_default_on(self, monkeypatch):
        for depth in ("fast", "Basics", "Standard", "Depth", "Comprehensive"):
            prepared = self._prepare(
                {"research_depth": depth}, monkeypatch=monkeypatch
            )
            assert prepared["_parallel_opening"] is True, f"{depth} files should be enabled by default"
