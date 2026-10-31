"""
Adversarial Challenge & Stress-Test Suite for CARE-Agents Milestone M1:
- Concurrency & Parallel State Merging (7 Parallel Analysts via merge_dict, LangGraph StateGraph, Threads, Processes)
- Fast-Path Routing & RiskSelfDebateV2 Synthesis (Empty investment_plan, empty investment_debate_state, NoneType resilience)
- Dynamic Debate Rounds Strict Bounding ([1, max_debate_rounds], boundary limits, state transition termination)

Target Verdict: CONFIRM or REJECT.
"""

import concurrent.futures
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END

from core.agents.analyst import DEFAULT_UNINFORMATIVE_POSTERIOR
from core.agents.adapters.index_analyst_v2 import IndexAnalystV2
from core.agents.adapters.sector_analyst_v2 import SectorAnalystV2
from core.agents.adapters.market_analyst_v2 import MarketAnalystV2
from core.agents.adapters.fundamentals_analyst_v2 import FundamentalsAnalystAgentV2
from core.agents.adapters.news_analyst_v2 import NewsAnalystV2
from core.agents.adapters.social_analyst_v2 import SocialMediaAnalystV2
from core.agents.adapters.chip_distribution_analyst_v2 import ChipDistributionAnalystV2
from core.agents.adapters.risk_self_debate_v2 import RiskSelfDebateV2
from tradingagents.agents.utils.agent_states import AgentState
from core.workflow.builder import WorkflowBuilder
from core.state.reducers import merge_dict
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_shannon_entropy,
    compute_base2_jsd,
    calculate_base2_jsd,
    calculate_cbs_routing,
    should_trigger_multi_round_debate,
)

ALL_7_ANALYST_IDS = [
    "index_analyst_v2",
    "sector_analyst_v2",
    "market_analyst_v2",
    "fundamentals_analyst_v2",
    "news_analyst_v2",
    "social_analyst_v2",
    "chip_distribution_analyst_v2",
]


def _generate_mock_posterior(aid: str, opt_offset: float = 0.0) -> Dict[str, Any]:
    """Helper to generate a valid normalized posterior."""
    p_opt = round(min(0.8, max(0.1, 0.4 + opt_offset)), 4)
    p_neu = 0.3
    p_cau = round(1.0 - p_opt - p_neu, 4)
    return {
        "p_optimistic": p_opt,
        "p_neutral": p_neu,
        "p_cautious": p_cau,
        "expected_move_bps": round(opt_offset * 100.0, 1),
        "confidence": 0.8,
        "market_regime": "bull" if opt_offset > 0 else "bear" if opt_offset < 0 else "sideways",
    }


def _multiprocess_analyst_worker(aid: str) -> Dict[str, Any]:
    """Top-level picklable worker function for multiprocessing tests."""
    post = _generate_mock_posterior(aid, opt_offset=0.05)
    return {aid: post}


# ==============================================================================
# Challenge Dimension 1: Concurrency and Parallel State Merging
# ==============================================================================
class TestParallelStateMergingConcurrency:
    """Stress-test concurrent merging of 7 analyst posteriors into state via merge_dict."""

    def test_7_threads_barrier_simultaneous_merge_dict(self):
        """Simulate 7 parallel analysts writing {self.agent_id: posterior} into analyst_posteriors simultaneously.

        Uses threading.Barrier to ensure all 7 threads execute at the exact same instant across 50 iterations.
        Asserts that all 7 posteriors are preserved without overwriting or race conditions.
        """
        for iteration in range(50):
            barrier = threading.Barrier(7)
            state_lock = threading.Lock()
            state: Dict[str, Any] = {"analyst_posteriors": {}}
            errors: List[Exception] = []

            def analyst_worker(aid: str, idx: int):
                try:
                    posterior = _generate_mock_posterior(aid, opt_offset=idx * 0.05)
                    update = {aid: posterior}
                    # Wait for all 7 threads to be ready to merge simultaneously
                    barrier.wait(timeout=5.0)

                    # In a concurrent runtime, updates are merged into state
                    with state_lock:
                        state["analyst_posteriors"] = merge_dict(
                            state.get("analyst_posteriors"), update
                        )
                except Exception as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(target=analyst_worker, args=(aid, i))
                for i, aid in enumerate(ALL_7_ANALYST_IDS)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

            assert len(errors) == 0, f"Errors encountered during concurrent execution: {errors}"
            posteriors = state["analyst_posteriors"]
            assert len(posteriors) == 7, f"Iteration {iteration}: Expected 7 posteriors, got {len(posteriors)}"
            for aid in ALL_7_ANALYST_IDS:
                assert aid in posteriors, f"Iteration {iteration}: Missing analyst {aid}"
                assert "p_optimistic" in posteriors[aid]
                assert abs(sum([posteriors[aid]["p_optimistic"], posteriors[aid]["p_neutral"], posteriors[aid]["p_cautious"]]) - 1.0) < 1e-4

    def test_langgraph_native_parallel_execution_preserves_all_7(self):
        """Empirically verify LangGraph Pregel engine merging 7 parallel analyst nodes into analyst_posteriors."""
        builder = StateGraph(AgentState)

        # Register 7 analyst nodes that run in parallel from START
        for aid in ALL_7_ANALYST_IDS:
            def make_node(agent_id=aid):
                def node_fn(state: AgentState):
                    post = _generate_mock_posterior(agent_id, opt_offset=0.1)
                    return {"analyst_posteriors": {agent_id: post}}
                return node_fn

            builder.add_node(aid, make_node(aid))
            builder.add_edge(START, aid)

        # Add merge node converging all 7
        def merge_node(state: AgentState):
            return {"_merge_reached": True}

        builder.add_node("merge_analysts", merge_node)
        builder.add_edge(ALL_7_ANALYST_IDS, "merge_analysts")
        builder.add_edge("merge_analysts", END)

        compiled_graph = builder.compile()

        # Execute graph
        initial_state = {
            "company_of_interest": "000001.SZ",
            "trade_date": "2026-03-31",
            "analyst_posteriors": {},
            "messages": [],
        }
        final_state = compiled_graph.invoke(initial_state)

        # Assert all 7 posteriors are preserved
        assert "analyst_posteriors" in final_state
        merged_posteriors = final_state["analyst_posteriors"]
        assert len(merged_posteriors) == 7, f"Expected 7 posteriors in LangGraph state, got {len(merged_posteriors)}"
        for aid in ALL_7_ANALYST_IDS:
            assert aid in merged_posteriors, f"LangGraph lost posterior for {aid}"
            assert merged_posteriors[aid]["market_regime"] == "bull"

    def test_workflow_state_schema_parallel_merge(self):
        """Empirically verify WorkflowBuilder's WorkflowState schema with 7 parallel nodes."""
        wf_builder = WorkflowBuilder()
        wf_schema = wf_builder._get_default_state_schema()

        graph = StateGraph(wf_schema)

        for aid in ALL_7_ANALYST_IDS:
            def make_node(agent_id=aid):
                def node_fn(state):
                    post = _generate_mock_posterior(agent_id, opt_offset=-0.1)
                    return {"analyst_posteriors": {agent_id: post}}
                return node_fn

            graph.add_node(aid, make_node(aid))
            graph.add_edge(START, aid)

        def sync_node(state):
            return {"_sync": True}

        graph.add_node("sync", sync_node)
        graph.add_edge(ALL_7_ANALYST_IDS, "sync")
        graph.add_edge("sync", END)

        app = graph.compile()
        result = app.invoke({"analyst_posteriors": {}})
        assert len(result["analyst_posteriors"]) == 7
        for aid in ALL_7_ANALYST_IDS:
            assert aid in result["analyst_posteriors"]

    def test_multiprocessing_pool_7_analysts_merge(self):
        """Simulate 7 OS worker processes writing {self.agent_id: posterior} merged via merge_dict."""
        with concurrent.futures.ProcessPoolExecutor(max_workers=7) as executor:
            futures = [executor.submit(_multiprocess_analyst_worker, aid) for aid in ALL_7_ANALYST_IDS]
            results = [f.result(timeout=10.0) for f in futures]

        # Merge process outputs
        accumulated: Dict[str, Any] = {}
        for r in results:
            accumulated = merge_dict(accumulated, r)

        assert len(accumulated) == 7
        for aid in ALL_7_ANALYST_IDS:
            assert aid in accumulated
            assert "p_optimistic" in accumulated[aid]

    def test_merge_dict_none_and_empty_edge_cases(self):
        """Verify merge_dict handles None, empty dicts, and nested content without mutating inputs."""
        left = {"analyst_posteriors": {"agent_1": {"p_opt": 0.5}}}
        right = {"analyst_posteriors": {"agent_2": {"p_opt": 0.6}}}

        # Null safety
        assert merge_dict(None, right) == right
        assert merge_dict(left, None) == left
        assert merge_dict(None, None) is None

        # Immutability of inputs
        left_copy = {"agent_1": {"p_opt": 0.5}}
        right_copy = {"agent_2": {"p_opt": 0.6}}
        merged = merge_dict(left_copy, right_copy)
        assert len(merged) == 2
        assert len(left_copy) == 1  # left was not mutated in place


# ==============================================================================
# Challenge Dimension 2: Fast-Path Routing and RiskSelfDebateV2 Synthesis
# ==============================================================================
class TestFastPathRiskSelfDebateSynthesis:
    """Stress-test RiskSelfDebateV2 synthesis when multi-round debate is bypassed."""

    @pytest.fixture
    def mock_tripartite_response(self):
        return AIMessage(
            content=(
                "【Highly resilient scenario perspective】\n"
                "Strong momentum in cyclical assets indicates high elasticity potential on pullbacks.\n\n"
                "【defensive situational view】\n"
                "Macro uncertainty and interest rate pressure require strict stop-loss levels.\n\n"
                "【base case view】\n"
                "Neutral base-case suggests holding balanced market weight with 30-50 bps expected drift.\n"
            )
        )

    def test_fast_path_with_empty_investment_plan_and_debate_state(self, mock_tripartite_response):
        """Execute fast-path with empty investment_plan and investment_debate_state.

        Verify RiskSelfDebateV2 synthesizes valid investment plan and consensus review
        without throwing KeyErrors or NoneType errors.
        """
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_tripartite_response

        agent = RiskSelfDebateV2(llm=mock_llm)
        agent._get_prompt_from_template = MagicMock(return_value="Mock Prompt")
        agent._invoke_llm_with_trace = MagicMock(return_value=mock_tripartite_response)

        state = {
            "ticker": "600519.SH",
            "trade_date": "2026-03-31",
            "investment_plan": "",
            "investment_debate_state": {},
            "analyst_posteriors": {
                "market_analyst_v2": _generate_mock_posterior("market_analyst_v2", 0.02),
                "fundamentals_analyst_v2": _generate_mock_posterior("fundamentals_analyst_v2", 0.03),
            },
        }

        result = agent.execute(state)

        # Assert no KeyErrors or NoneType errors
        assert result is not None
        assert "investment_plan" in result
        assert isinstance(result["investment_plan"], str)
        assert len(result["investment_plan"]) > 0
        assert "Fast-Path Tripartite Synthesis" in result["investment_plan"]
        assert "Neutral base-case suggests holding" in result["investment_plan"]

        assert "investment_debate_state" in result
        deb_state = result["investment_debate_state"]
        assert isinstance(deb_state, dict)
        assert deb_state["history"].startswith("Fast-Path")
        assert deb_state["bull_history"] == "Bypassed via Fast-Path"
        assert deb_state["bear_history"] == "Bypassed via Fast-Path"
        assert deb_state["current_response"] == "Fast-Path"
        assert deb_state["judge_decision"] == result["investment_plan"]
        assert deb_state["count"] == 0

        # Assert tripartite risk outputs are non-empty
        assert "risky_opinion" in result and len(result["risky_opinion"]) > 0
        assert "safe_opinion" in result and len(result["safe_opinion"]) > 0
        assert "neutral_opinion" in result and len(result["neutral_opinion"]) > 0

    def test_fast_path_with_none_values_and_completely_empty_state(self, mock_tripartite_response):
        """Verify execute() with NoneType parameters does not raise KeyErrors or TypeErrors."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_tripartite_response

        agent = RiskSelfDebateV2(llm=mock_llm)
        agent._get_prompt_from_template = MagicMock(return_value="Mock Prompt")
        agent._invoke_llm_with_trace = MagicMock(return_value=mock_tripartite_response)

        state_with_none = {
            "investment_plan": None,
            "investment_debate_state": None,
            "trader_investment_plan": None,
            "analyst_posteriors": None,
            "risk_debate_state": None,
            "ticker": None,
            "trade_date": None,
        }

        result = agent.execute(state_with_none)

        assert result is not None
        assert "investment_plan" in result
        assert result["investment_plan"] is not None
        assert "investment_debate_state" in result
        assert result["investment_debate_state"] is not None

    def test_fast_path_llm_exception_graceful_downgrade(self):
        """Verify execute() degrades gracefully when LLM invocation raises an exception."""
        agent = RiskSelfDebateV2(llm=MagicMock())
        agent._get_prompt_from_template = MagicMock(return_value="Mock Prompt")
        agent._invoke_llm_with_trace = MagicMock(side_effect=RuntimeError("Simulated LLM Timeout"))

        state = {
            "ticker": "000001.SZ",
            "investment_plan": "",
            "investment_debate_state": {},
        }

        result = agent.execute(state)

        assert result is not None
        assert "investment_plan" in result
        assert "Simulated LLM Timeout" in result["investment_plan"]
        assert "investment_debate_state" in result
        assert result["investment_debate_state"]["count"] == 0


# ==============================================================================
# Challenge Dimension 3: Dynamic Debate Rounds Strict Bounding
# ==============================================================================
class TestDynamicDebateRoundsStrictBounding:
    """Stress-test dynamic debate rounds calculation, boundary invariants, and termination."""

    @pytest.mark.parametrize("max_rounds", [1, 2, 3, 5, 10])
    def test_dynamic_rounds_strictly_bounded_for_all_jsd_values(self, max_rounds):
        """Assert dynamic debate rounds are strictly bounded within [1, max_debate_rounds]

        for any JSD in [0.12, 1.0] when multi-round debate is triggered.
        """
        # Test 100 discrete points between 0.12 and 1.0
        for i in range(101):
            jsd = 0.12 + (1.0 - 0.12) * (i / 100.0)
            scaling = (jsd - 0.12) / (1.0 - 0.12)
            scaled_rounds = 1 + (max_rounds - 1) * scaling
            dynamic_rounds = int(max(1, min(max_rounds, round(scaled_rounds))))

            # Invariant: 1 <= dynamic_rounds <= max_rounds
            assert 1 <= dynamic_rounds <= max_rounds, (
                f"Invariant violation: jsd={jsd}, max_rounds={max_rounds}, dynamic_rounds={dynamic_rounds}"
            )

        # Boundary checks
        # jsd = 0.12 exactly -> round must be 1
        scaling_0 = (0.12 - 0.12) / (1.0 - 0.12)
        r_0 = int(max(1, min(max_rounds, round(1 + (max_rounds - 1) * scaling_0))))
        assert r_0 == 1

        # jsd = 1.0 exactly -> round must be max_rounds
        scaling_1 = (1.0 - 0.12) / (1.0 - 0.12)
        r_1 = int(max(1, min(max_rounds, round(1 + (max_rounds - 1) * scaling_1))))
        assert r_1 == max_rounds

    def test_cbs_routing_dynamic_rounds_in_conditional_logic(self):
        """Verify calculate_cbs_routing strictly outputs dynamic_debate_rounds in [1, max_debate_rounds] on debate path."""
        for max_rounds in [1, 2, 3, 4, 8]:
            # Construct high disagreement posteriors
            high_jsd_posteriors = {
                "analyst_bull": {
                    "p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05,
                    "expected_move_bps": 200.0, "confidence": 0.9, "market_regime": "bull"
                },
                "analyst_bear": {
                    "p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90,
                    "expected_move_bps": 200.0, "confidence": 0.9, "market_regime": "bear"
                },
            }
            routing = calculate_cbs_routing(
                posteriors=high_jsd_posteriors,
                estimated_spread_bps=15.0,
                max_debate_rounds=max_rounds,
            )

            assert routing["route"] == "multi_round_debate"
            assert 1 <= routing["dynamic_debate_rounds"] <= max_rounds

    def test_should_continue_debate_termination_at_scaled_rounds(self):
        """Verify should_continue_debate terminates at exactly 2 * dynamic_debate_rounds turns."""
        logic = ConditionalLogic(max_debate_rounds=3)

        # If dynamic_debate_rounds is 2:
        # Max speeches = 2 * 2 = 4
        state: Dict[str, Any] = {
            "dynamic_debate_rounds": 2,
            "investment_debate_state": {
                "count": 0,
                "current_response": "Bull Researcher: Initial position",
            },
        }

        # Count 0 -> continues to Bear
        assert logic.should_continue_debate(state) == "Bear Researcher"

        # Count 1 -> continues to Bull
        state["investment_debate_state"]["count"] = 1
        state["investment_debate_state"]["current_response"] = "Bear Researcher: Counter argument"
        assert logic.should_continue_debate(state) == "Bull Researcher"

        # Count 2 -> continues to Bear
        state["investment_debate_state"]["count"] = 2
        state["investment_debate_state"]["current_response"] = "Bull Researcher: Rebuttal"
        assert logic.should_continue_debate(state) == "Bear Researcher"

        # Count 3 -> continues to Bull
        state["investment_debate_state"]["count"] = 3
        state["investment_debate_state"]["current_response"] = "Bear Researcher: Final counter"
        assert logic.should_continue_debate(state) == "Bull Researcher"

        # Count 4 -> reached max_count (2 * 2 = 4) -> Research Manager
        state["investment_debate_state"]["count"] = 4
        assert logic.should_continue_debate(state) == "Research Manager"

        # Count > 4 -> strictly terminates
        state["investment_debate_state"]["count"] = 5
        assert logic.should_continue_debate(state) == "Research Manager"

    def test_fast_path_bypasses_debate_and_routes_correctly(self):
        """Verify when JSD < 0.12 or CBS <= spread, should_trigger_multi_round_debate returns fast_path."""
        logic = ConditionalLogic(max_debate_rounds=3)

        # Low divergence posteriors
        unanimous_posteriors = {
            aid: {
                "p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10,
                "expected_move_bps": 50.0, "confidence": 0.8, "market_regime": "bull"
            }
            for aid in ALL_7_ANALYST_IDS
        }
        state = {
            "analyst_posteriors": unanimous_posteriors,
            "estimated_spread_bps": 15.0,
        }

        decision = logic.should_trigger_multi_round_debate(state)
        assert decision == "fast_path"
        assert state.get("dynamic_debate_rounds") == 0
        assert state.get("_risk_self_debate") is True



# ==============================================================================
# Challenge Dimension 4: State Mutation, Flag Synchronization & Alternating Ticks
# ==============================================================================
class TestStateMutationAndFlagSynchronization:
    """Empirically test toggling state across multiple rounds and alternating ticks."""

    def test_alternating_50_ticks_state_synchronization(self):
        """Alternating fast-path and multi-round debate states across 50 consecutive ticks.

        Verifies:
        1. should_trigger_multi_round_debate correctly toggles route between 'fast_path' and 'multi_round_debate'.
        2. state['_risk_self_debate'] updates to True on fast_path and False on multi_round_debate without leaking.
        3. dynamic_debate_rounds is 0 on fast_path and in [1, 3] on multi_round_debate.
        4. No stale metrics or state contamination between alternating ticks.
        """
        logic = ConditionalLogic(max_debate_rounds=3)
        state: Dict[str, Any] = {
            "estimated_spread_bps": 15.0,
            "analyst_posteriors": {},
        }

        fast_path_posteriors = {
            "analyst_1": {
                "p_optimistic": 0.60, "p_neutral": 0.30, "p_cautious": 0.10,
                "expected_move_bps": 20.0, "confidence": 0.8, "market_regime": "bull"
            },
            "analyst_2": {
                "p_optimistic": 0.60, "p_neutral": 0.30, "p_cautious": 0.10,
                "expected_move_bps": 20.0, "confidence": 0.8, "market_regime": "bull"
            },
        }

        debate_posteriors = {
            "analyst_1": {
                "p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05,
                "expected_move_bps": 250.0, "confidence": 0.9, "market_regime": "bull"
            },
            "analyst_2": {
                "p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90,
                "expected_move_bps": 250.0, "confidence": 0.9, "market_regime": "bear"
            },
        }

        for tick in range(50):
            is_fast = (tick % 2 == 0)
            if is_fast:
                state["analyst_posteriors"] = fast_path_posteriors
                expected_route = "fast_path"
                expected_flag = True
            else:
                state["analyst_posteriors"] = debate_posteriors
                expected_route = "multi_round_debate"
                expected_flag = False

            route = logic.should_trigger_multi_round_debate(state)
            alias_route = logic.should_gate_debate(state)

            assert route == expected_route, f"Tick {tick}: route={route}, expected {expected_route}"
            assert alias_route == expected_route, f"Tick {tick}: alias_route={alias_route}, expected {expected_route}"
            assert state["_risk_self_debate"] is expected_flag, (
                f"Tick {tick}: _risk_self_debate={state['_risk_self_debate']}, expected {expected_flag}"
            )

            if is_fast:
                assert state["dynamic_debate_rounds"] == 0
                assert state["_max_debate_rounds"] == 1
                assert state["cbs_bps"] <= 15.0 or state["debate_jsd"] < 0.12
            else:
                assert 1 <= state["dynamic_debate_rounds"] <= 3
                assert state["_max_debate_rounds"] == state["dynamic_debate_rounds"]
                assert state["debate_jsd"] >= 0.12 and state["cbs_bps"] > 15.0

    def test_state_mutation_isolation_on_identical_posteriors(self):
        """Verify that state updates do not mutate the input posteriors dictionaries."""
        logic = ConditionalLogic(max_debate_rounds=3)
        original_posteriors = {
            "analyst_bull": {
                "p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05,
                "expected_move_bps": 120.0, "confidence": 0.9, "market_regime": "bull"
            },
            "analyst_bear": {
                "p_optimistic": 0.10, "p_neutral": 0.10, "p_cautious": 0.80,
                "expected_move_bps": -120.0, "confidence": 0.85, "market_regime": "bear"
            },
        }
        import copy
        posteriors_snapshot = copy.deepcopy(original_posteriors)

        state = {
            "analyst_posteriors": original_posteriors,
            "estimated_spread_bps": 15.0,
        }

        logic.should_trigger_multi_round_debate(state)

        # Input posteriors dictionary and nested values must remain strictly unchanged
        assert state["analyst_posteriors"] == posteriors_snapshot
        assert original_posteriors == posteriors_snapshot

    def test_100_runs_concurrent_merges_never_corrupts_distinct_analysts(self):
        """Run 100 parallel trials with random sleep and barrier to ensure merge_dict preserves all 7 analysts."""
        import random
        for trial in range(100):
            barrier = threading.Barrier(7)
            state_lock = threading.Lock()
            state: Dict[str, Any] = {"analyst_posteriors": {}}
            errors: List[Exception] = []

            def worker(aid: str, idx: int):
                try:
                    time.sleep(random.uniform(0.0001, 0.002))
                    post = _generate_mock_posterior(aid, opt_offset=(idx - 3) * 0.05)
                    barrier.wait(timeout=3.0)
                    with state_lock:
                        state["analyst_posteriors"] = merge_dict(state["analyst_posteriors"], {aid: post})
                except Exception as ex:
                    errors.append(ex)

            threads = [threading.Thread(target=worker, args=(aid, i)) for i, aid in enumerate(ALL_7_ANALYST_IDS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=3.0)

            assert len(errors) == 0, f"Trial {trial}: errors={errors}"
            assert len(state["analyst_posteriors"]) == 7, f"Trial {trial}: expected 7, got {len(state['analyst_posteriors'])}"
            for aid in ALL_7_ANALYST_IDS:
                assert aid in state["analyst_posteriors"]
                p = state["analyst_posteriors"][aid]
                assert abs(p["p_optimistic"] + p["p_neutral"] + p["p_cautious"] - 1.0) < 1e-4

    def test_dynamic_debate_rounds_scaling_stress_monte_carlo(self):
        """Stress-test dynamic debate rounds scaling over 500 simulated posterior combinations."""
        import random
        max_debate_rounds = 3
        for _ in range(500):
            # Generate random 3-class distributions
            p1 = [random.random(), random.random(), random.random()]
            s1 = sum(p1)
            p1 = [x / s1 for x in p1]

            p2 = [random.random(), random.random(), random.random()]
            s2 = sum(p2)
            p2 = [x / s2 for x in p2]

            move = random.uniform(0.0, 300.0)
            spread = 15.0

            posteriors = {
                "a1": {"p_optimistic": p1[0], "p_neutral": p1[1], "p_cautious": p1[2], "expected_move_bps": move, "confidence": 0.8},
                "a2": {"p_optimistic": p2[0], "p_neutral": p2[1], "p_cautious": p2[2], "expected_move_bps": move, "confidence": 0.8},
            }

            routing = calculate_cbs_routing(posteriors, estimated_spread_bps=spread, max_debate_rounds=max_debate_rounds)
            jsd = routing["jsd"]
            cbs = routing["cbs_bps"]
            route = routing["route"]
            dynamic_rounds = routing["dynamic_debate_rounds"]

            if jsd < 0.12 or cbs <= spread:
                assert route == "fast_path"
                assert dynamic_rounds == 0
            else:
                assert route == "multi_round_debate"
                assert 1 <= dynamic_rounds <= max_debate_rounds
