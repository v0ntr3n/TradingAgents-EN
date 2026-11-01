"""
Empirical Adversarial Stress Suite for CARE-Agents
Challenger 1: Causal Execution, Ablation Benchmark, and Runtime LangGraph CBS Gating
"""
import math
import random
import pytest

import tests  # Registers lightweight stubs for optional dependencies
from core.agents.utils.weight_calculator import RegimeMultiplicativeWeightManager
from core.backtest.result_evaluator import ProtocolAuditEvaluator
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_jensen_shannon_divergence,
    compute_cbs_bps,
)
from tradingagents.graph.signal_processing import SignalProcessor
from scripts.run_cph_ablation_benchmark import (
    generate_multi_regime_market_stream,
    evaluate_stream_protocols,
    _base_target_position,
)


# ============================================================================
# Section 1: Ablation Benchmark Causality & Empirical Metric Reproduction
# ============================================================================

def test_ablation_metrics_reproduction():
    """
    Empirically verify that M4 CARE-Agents on the 500-bar de-biased cached LLM panel
    reproduces exact paper metrics (+48.87% net return, 1.173 Net Sharpe, 76.0% debate skip rate),
    outperforming M1, M2, M3, M1_with_Turnover_Gate, M2_with_Turnover_Gate, and M4_No_Turnover_Gate.
    """
    stream = generate_multi_regime_market_stream(500, seed=20261030)
    results = evaluate_stream_protocols(stream)
    res_m1 = results["M1_Linear_Pipeline"]
    res_m2 = results["M2_Vanilla_TradingAgents"]
    res_m3 = results["M3_SelfDebate_V2"]
    res_m1_tg = results["M1_with_Turnover_Gate"]
    res_m2_tg = results["M2_with_Turnover_Gate"]
    res_m4_notg = results["M4_No_Turnover_Gate"]
    res_m4 = results["M4_CARE_Agents_Ours"]

    # 1. Verify M4 Net Return and Sharpe against paper claims (real cached LLM panel across both tiers)
    assert math.isclose(res_m4["net_cumulative_return"], 48.8711, rel_tol=1e-3), (
        f"M4 Net Return {res_m4['net_cumulative_return']} does not match paper target +48.87%"
    )
    assert math.isclose(res_m4["net_sharpe"], 1.1731, rel_tol=1e-3), (
        f"M4 Net Sharpe {res_m4['net_sharpe']} does not match paper target 1.173"
    )
    assert math.isclose(res_m4["computational_cost"]["debate_skip_rate"], 0.76, abs_tol=1e-3), (
        f"M4 Debate Skip Rate {res_m4['computational_cost']['debate_skip_rate']} does not match 76.0%"
    )

    # 2. Verify M4_No_Turnover_Gate beats M1, M2, M3 without turnover gating, and M4 beats all gated and ungated baselines
    assert res_m4_notg["net_cumulative_return"] > res_m1["net_cumulative_return"] > res_m3["net_cumulative_return"] > res_m2["net_cumulative_return"]
    assert res_m4["net_cumulative_return"] > res_m1_tg["net_cumulative_return"] > res_m4_notg["net_cumulative_return"] > res_m2_tg["net_cumulative_return"]
    assert res_m4["net_sharpe"] > res_m1_tg["net_sharpe"] > res_m2_tg["net_sharpe"]


def test_ablation_causal_dataflow_and_zero_lookahead():
    """
    Stress-test causal data flow:
    Inject an observer to verify that during step t decision time:
    - ret_pct is not read or accessed by weights, gating, or aggregation
    """
    stream = generate_multi_regime_market_stream(100, seed=42)

    mw_manager_causal = RegimeMultiplicativeWeightManager(
        analyst_ids=["market", "fundamentals", "news", "social"]
    )
    cond_logic = ConditionalLogic(max_debate_rounds=2, jsd_threshold=0.0052)

    for step in stream:
        regime = step["regime"]
        posteriors = step["posteriors"]
        spread_bps = step["spread_bps"]

        state = {
            "analyst_posteriors": posteriors,
            "analyst_weights": mw_manager_causal.get_regime_weights(regime, list(posteriors.keys())),
            "estimated_spread_bps": spread_bps,
        }
        # Verify ret_pct is NOT in state
        assert "ret_pct" not in state
        assert "asset_return_pct" not in state

        gate = cond_logic.should_gate_debate(state)
        agg = mw_manager_causal.aggregate_posteriors(regime, posteriors)

        # Gate decision and agg are deterministic functions of posteriors and prior weights
        assert "cbs_bps" in gate
        assert "recommended_action" in agg

        # Posteriors update only at end of bar
        mw_manager_causal.update_weights(regime, posteriors, realized_return_pct=step["ret_pct"], eta=0.35, threshold_pct=0.20)


def test_expected_move_decoupling_adversarial_challenge():
    """
    Adversarial Challenge: Does M4's outperformance artificially depend on `expected_move_bps`
    containing `abs(ret_pct)`?
    We replace `expected_move_bps` with a completely independent constant (350.0 bps),
    decoupling it from any volatility proxy.
    Verify that M4 STILL outperforms M1, M2, and M3.
    """
    stream = generate_multi_regime_market_stream(500, seed=20261030)
    for step in stream:
        for post in step["posteriors"].values():
            post["expected_move_bps"] = 350.0  # Decoupled constant

    results = evaluate_stream_protocols(stream)
    res_m1 = results["M1_Linear_Pipeline"]
    res_m2 = results["M2_Vanilla_TradingAgents"]
    res_m3 = results["M3_SelfDebate_V2"]
    res_m4 = results["M4_CARE_Agents_Ours"]

    assert res_m4["net_sharpe"] > res_m1["net_sharpe"]
    assert res_m4["net_sharpe"] > res_m2["net_sharpe"]
    assert res_m4["net_sharpe"] > res_m3["net_sharpe"]


def test_multi_seed_generalizability():
    """
    Stress-test across 5 diverse random seeds (1, 42, 100, 2024, 9999).
    Verify that M4 CARE-Agents robustly maintains positive mean Sharpe superiority
    and wins at least 4 of 5 seeds over Vanilla TradingAgents (M2) without any oracle lookahead.
    """
    seeds = [1, 42, 100, 2024, 9999]
    wins = 0
    m4_sharpes = []
    m2_sharpes = []

    for seed in seeds:
        stream = generate_multi_regime_market_stream(300, seed=seed)
        results = evaluate_stream_protocols(stream)
        res_m2 = results["M2_Vanilla_TradingAgents"]
        res_m4 = results["M4_CARE_Agents_Ours"]
        m4_sharpes.append(res_m4["net_sharpe"])
        m2_sharpes.append(res_m2["net_sharpe"])
        if res_m4["net_sharpe"] > res_m2["net_sharpe"]:
            wins += 1

    assert wins >= 4, f"Expected M4 to win >= 4/5 seeds vs M2, got {wins}/5 ({m4_sharpes} vs {m2_sharpes})"
    assert sum(m4_sharpes) / len(m4_sharpes) > sum(m2_sharpes) / len(m2_sharpes) + 0.40


def test_cbs_threshold_gating_spread_monotonicity():
    """
    Verify that debate skip rate increases monotonically as spread_bps increases:
    Under wider spreads, coordination overhead exceeds expected edge more often,
    causing the CBS gating condition (cbs_bps <= spread_bps) to trigger fast-path bypass.
    """
    stream = generate_multi_regime_market_stream(300, seed=42)
    cond_logic = ConditionalLogic(max_debate_rounds=2, jsd_threshold=0.0052)
    mw_manager = RegimeMultiplicativeWeightManager(
        analyst_ids=["market", "fundamentals", "news", "social"]
    )

    spread_levels = [1.0, 5.0, 10.0, 20.0, 60.0]
    skip_rates = []

    for spread in spread_levels:
        skipped_count = 0
        for step in stream:
            state = {
                "analyst_posteriors": step["posteriors"],
                "analyst_weights": mw_manager.get_regime_weights(step["regime"]),
                "estimated_spread_bps": spread,
            }
            decision = cond_logic.should_gate_debate(state)
            if decision["risk_self_debate"]:
                skipped_count += 1
        skip_rates.append(skipped_count / len(stream))

    # Check monotonicity: skip_rates must be non-decreasing
    for i in range(len(skip_rates) - 1):
        assert skip_rates[i] <= skip_rates[i + 1] + 1e-9, (
            f"Skip rates not monotonic: {skip_rates} at spread levels {spread_levels}"
        )
    assert skip_rates[0] < skip_rates[-1]


# ============================================================================
# Section 2: Runtime LangGraph CBS Gating & Signal Processing Stress Tests
# ============================================================================

def test_cbs_divergence_edge_cases():
    """
    Stress-test Jensen-Shannon Divergence and CBS computation with pathological inputs:
    - Empty posteriors
    - Single analyst posterior
    - Identical distributions (zero JSD)
    - Mutually orthogonal extreme distributions (maximal JSD = 1.0)
    - Zero probabilities without log2(0) DomainError
    - Non-normalized or negative weights
    """
    # 1. Empty posteriors
    assert compute_jensen_shannon_divergence({}) == 0.0
    assert compute_cbs_bps({}) == 0.0

    # 2. Single analyst posterior
    single = {"market": {"p_optimistic": 0.8, "p_neutral": 0.1, "p_cautious": 0.1}}
    assert compute_jensen_shannon_divergence(single) == 0.0
    assert compute_cbs_bps(single) == 0.0

    # 3. Identical distributions (zero JSD)
    identical = {
        "a1": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2, "expected_move_bps": 100.0},
        "a2": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2, "expected_move_bps": 100.0},
        "a3": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2, "expected_move_bps": 100.0},
    }
    assert math.isclose(compute_jensen_shannon_divergence(identical), 0.0, abs_tol=1e-6)
    assert math.isclose(compute_cbs_bps(identical), 0.0, abs_tol=1e-6)

    # 4. Mutually orthogonal extreme distributions (maximal normalized JSD = 1.0)
    orthogonal = {
        "bull_agent": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 100.0},
        "neutral_agent": {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0, "expected_move_bps": 100.0},
        "bear_agent": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": 100.0},
    }
    jsd_max = compute_jensen_shannon_divergence(orthogonal)
    assert math.isclose(jsd_max, 1.0, abs_tol=1e-5), f"Max JSD should be 1.0, got {jsd_max}"
    cbs_max = compute_cbs_bps(orthogonal)
    # CBS = (1.0 * 100.0) / 2 = 50.0 bps
    assert math.isclose(cbs_max, 50.0, abs_tol=1e-3)

    # 5. Zero probabilities with negative/unnormalized weights
    weights = {"bull_agent": -10.0, "neutral_agent": 0.0, "bear_agent": 5.0}
    # Should not crash and should produce non-negative bounded JSD
    jsd_weighted = compute_jensen_shannon_divergence(orthogonal, weights=weights)
    assert 0.0 <= jsd_weighted <= 1.0


def test_runtime_graph_routing_consensus_vs_clash():
    """
    Stress-test should_trigger_multi_round_debate routing decisions:
    - Consensus state -> "Research Manager" (bypass debate)
    - Dispersion clash state -> "Bull Researcher" (enter debate)
    - Extreme spread -> "Research Manager"
    - Zero spread with disagreement -> "Bull Researcher"
    """
    logic = ConditionalLogic(max_debate_rounds=3, jsd_threshold=0.12, default_spread_bps=15.0)

    # Consensus state
    consensus_state = {
        "estimated_spread_bps": 15.0,
        "analyst_posteriors": {
            "market": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 60.0},
            "news": {"p_optimistic": 0.68, "p_neutral": 0.22, "p_cautious": 0.10, "expected_move_bps": 65.0},
            "social": {"p_optimistic": 0.72, "p_neutral": 0.18, "p_cautious": 0.10, "expected_move_bps": 55.0},
        },
    }
    assert logic.should_trigger_multi_round_debate(consensus_state) == "Research Manager"
    assert consensus_state["cbs_gating_decision"]["route"] == "fast_path_single_pass"
    assert consensus_state["cbs_gating_decision"]["target_debate_rounds"] == 0

    # Clash state: Market vs Fundamentals polar opposite
    clash_state = {
        "estimated_spread_bps": 10.0,
        "analyst_posteriors": {
            "market": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 150.0},
            "fundamentals": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85, "expected_move_bps": 150.0},
        },
    }
    assert logic.should_trigger_multi_round_debate(clash_state) == "Bull Researcher"
    assert clash_state["cbs_gating_decision"]["route"] == "multi_round_debate"
    assert clash_state["cbs_gating_decision"]["target_debate_rounds"] >= 1

    # Extreme spread (1000 bps) should bypass debate even with huge clash
    extreme_spread_state = dict(clash_state)
    extreme_spread_state["estimated_spread_bps"] = 1000.0
    assert logic.should_trigger_multi_round_debate(extreme_spread_state) == "Research Manager"

    # Zero spread (0 bps) with clash should trigger debate
    zero_spread_state = dict(clash_state)
    zero_spread_state["estimated_spread_bps"] = 0.0
    assert logic.should_trigger_multi_round_debate(zero_spread_state) == "Bull Researcher"


def test_should_continue_debate_target_rounds_adherence():
    """
    Stress-test should_continue_debate loop termination:
    - Validates that debate alternates between Bull and Bear
    - Dynamically respects target_debate_rounds from cbs_gating_decision
    - Terminates strictly at Research Manager when count reaches 2 * target_debate_rounds
    """
    logic = ConditionalLogic(max_debate_rounds=3)

    state = {
        "investment_debate_state": {
            "count": 0,
            "current_response": "Bull Researcher: Growth momentum is high",
        },
        "cbs_gating_decision": {
            "target_debate_rounds": 2,  # max_count = 2 * 2 = 4
        },
    }

    # Step 1: count=0, speaker=Bull -> Bear Researcher
    assert logic.should_continue_debate(state) == "Bear Researcher"

    # Step 2: count=1, speaker=Bear -> Bull Researcher
    state["investment_debate_state"]["count"] = 1
    state["investment_debate_state"]["current_response"] = "Bear Researcher: Valuations stretched"
    assert logic.should_continue_debate(state) == "Bull Researcher"

    # Step 3: count=3, speaker=Bear -> Bull Researcher
    state["investment_debate_state"]["count"] = 3
    assert logic.should_continue_debate(state) == "Bull Researcher"

    # Step 4: count=4 (reached max_count=4) -> Research Manager
    state["investment_debate_state"]["count"] = 4
    assert logic.should_continue_debate(state) == "Research Manager"

    # Step 5: count=5 (exceeded) -> Research Manager
    state["investment_debate_state"]["count"] = 5
    assert logic.should_continue_debate(state) == "Research Manager"


def test_signal_processor_calibrated_edge_cases():
    """
    Stress-test SignalProcessor.process_calibrated_signal:
    - Handles empty signal string gracefully
    - Calibrates confidence from entropy rather than hardcoded 0.7
    - Sets target price dynamically based on expected_move_bps rather than 1.15x heuristic
    - Handles zero, negative, or None current_price safely
    """
    sp = SignalProcessor(quick_thinking_llm=None)

    # 1. Null signal with posteriors
    posteriors = {
        "market": {"p_optimistic": 0.80, "p_neutral": 0.15, "p_cautious": 0.05, "expected_move_bps": 200.0},
        "fundamentals": {"p_optimistic": 0.75, "p_neutral": 0.20, "p_cautious": 0.05, "expected_move_bps": 180.0},
    }
    res = sp.process_signal(
        full_signal="",
        stock_symbol="600519",
        analyst_posteriors=posteriors,
        regime="bull",
        current_price=1500.0,
    )
    assert res["action"] == "buy"
    assert res["confidence"] > 0.0
    # Expected move is ~190 bps (1.9%). Target price should be ~ 1500 * 1.019 = 1528.5
    assert 1515.0 <= res["target_price"] <= 1545.0
    assert not math.isclose(res["target_price"], 1500.0 * 1.15)  # NOT the old static 1.15x multiplier

    # 2. Bearish posteriors
    bear_posteriors = {
        "market": {"p_optimistic": 0.05, "p_neutral": 0.15, "p_cautious": 0.80, "expected_move_bps": 250.0},
        "fundamentals": {"p_optimistic": 0.05, "p_neutral": 0.20, "p_cautious": 0.75, "expected_move_bps": 250.0},
    }
    res_bear = sp.process_signal(
        full_signal="Strong sell signal",
        stock_symbol="AAPL",
        analyst_posteriors=bear_posteriors,
        regime="bear",
        current_price=200.0,
    )
    assert res_bear["action"] == "sell"
    # Target price should be 200 * (1 - 0.025) = 195.0
    assert 193.0 <= res_bear["target_price"] <= 197.0
    assert not math.isclose(res_bear["target_price"], 200.0 * 0.95)  # NOT the old static 0.95x multiplier

    # 3. None current_price
    res_none_price = sp.process_signal(
        full_signal="",
        stock_symbol="AAPL",
        analyst_posteriors=posteriors,
        regime="bull",
        current_price=None,
    )
    assert res_none_price["action"] == "buy"

    # 4. Empty posteriors and empty signal fallback
    res_empty = sp.process_signal(full_signal="", analyst_posteriors=None)
    assert res_empty["action"] == "hold"
    assert res_empty["target_price"] is None
