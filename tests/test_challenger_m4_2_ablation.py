"""
Adversarial Stress-Test Suite for CARE-Agents Milestone M4
(Challenger M4_2: Multi-Regime Slicing, CBS Tracking, & 4-Ablation Configurations)

Coverage:
1. Multi-regime breakdown stress-testing (missing regimes, unknown labels, empty slices, single-day, extremes)
2. CBS & Coordination cost stress-testing (missing tokens/latency, zero CBS, all vs zero bypass, polymorphic flags)
3. 4-Ablation configuration specifications verification (Config A, Config B, Config C, Config D invariants)
4. Hostile adversarial edge cases (rapid regime whipsaw, extreme friction gating, analyst dropouts, uncalibrated inputs)
"""

import copy
import math
import numpy as np
import pytest
from typing import Any, Dict, List

from core.backtest.result_evaluator import (
    FrictionConfig,
    calculate_cbs_and_coordination_cost,
    calculate_multi_regime_breakdown,
    calculate_net_performance_metrics,
)
from tests.test_care_agents_ablation import (
    ANALYST_IDS,
    REGIMES,
    AblationEngine,
    SyntheticMarketFeed,
    calculate_base2_jsd,
    calculate_bayesian_log_odds_target_price,
    calculate_cbs_routing,
    calculate_counterfactual_attribution,
    circuit_breaker_memory_filter,
    normalize_memory_metadata,
    ReferenceRegimeAdaptiveWeightCalculator,
)


# ==============================================================================
# 1. Multi-Regime Breakdown Stress-Tests
# ==============================================================================

class TestChallengerMultiRegimeStress:
    """Empirical challenge on calculate_multi_regime_breakdown."""

    def test_missing_regimes_partial_presence(self):
        """Stress-test when dataset contains only a subset of target regimes."""
        # Only 'bull' days present
        returns_bull = [0.015, 0.020, 0.012, 0.008]
        regimes_bull = ["bull", "bull", "bull", "bull"]

        res = calculate_multi_regime_breakdown(returns_bull, regimes_bull)
        assert "bull" in res
        assert "bear" not in res
        assert "sideways" not in res
        assert res["bull"]["count"] == 4.0
        assert res["bull"]["net_return"] > 0.0

        # Only 'bear' and 'sideways' present
        returns_mixed = [-0.02, -0.015, 0.001, -0.002]
        regimes_mixed = ["bear", "bear", "sideways", "sideways"]

        res2 = calculate_multi_regime_breakdown(returns_mixed, regimes_mixed)
        assert "bear" in res2
        assert "sideways" in res2
        assert "bull" not in res2
        assert res2["bear"]["count"] == 2.0
        assert res2["sideways"]["count"] == 2.0

    def test_unknown_regime_labels_and_none(self):
        """Stress-test unrecognized regime names, None, numbers, and whitespace."""
        returns = [0.01, -0.02, 0.005, 0.03, -0.01]
        regimes = ["crisis", "stagflation", None, "BULL", " bear "]

        res = calculate_multi_regime_breakdown(returns, regimes)
        # Only 'bull' (index 3) and 'bear' (index 4) should be parsed
        assert "bull" in res
        assert "bear" in res
        assert "crisis" not in res
        assert "stagflation" not in res
        assert res["bull"]["count"] == 1.0
        assert res["bear"]["count"] == 1.0

    def test_completely_unknown_regimes(self):
        """When no regime matches 'bull', 'bear', or 'sideways', result is empty dict."""
        returns = [0.01, 0.02, 0.03]
        regimes = ["crypto_bubble", "hyperinflation", "random_walk"]

        res = calculate_multi_regime_breakdown(returns, regimes)
        assert res == {}

    def test_empty_daily_returns_and_empty_regimes(self):
        """Empty input returns and regimes return empty breakdown without error."""
        assert calculate_multi_regime_breakdown([], []) == {}

    def test_mismatched_length_returns_and_regimes(self):
        """Handles length mismatches gracefully via zip truncation."""
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        regimes = ["bull", "bull"]  # shorter

        res = calculate_multi_regime_breakdown(returns, regimes)
        assert res["bull"]["count"] == 2.0

        returns_short = [0.01]
        regimes_long = ["bull", "bull", "bull"]

        res2 = calculate_multi_regime_breakdown(returns_short, regimes_long)
        assert res2["bull"]["count"] == 1.0

    def test_single_day_regime_statistics(self):
        """Single day in regime: std is 0.0, Sharpe is 0.0 (no division by zero)."""
        res = calculate_multi_regime_breakdown([0.025], ["bull"])
        assert res["bull"]["count"] == 1.0
        assert res["bull"]["net_sharpe"] == 0.0
        assert not math.isnan(res["bull"]["net_sharpe"])
        assert res["bull"]["net_return"] == pytest.approx(0.025 - 0.0002, abs=1e-6)

    def test_zero_volatility_in_regime(self):
        """Constant returns in a regime produce zero variance and zero Sharpe without NaN."""
        returns = [0.005] * 10
        regimes = ["sideways"] * 10

        res = calculate_multi_regime_breakdown(returns, regimes)
        assert res["sideways"]["count"] == 10.0
        assert res["sideways"]["net_sharpe"] == 0.0
        assert not math.isnan(res["sideways"]["net_sharpe"])

    def test_catastrophic_drawdown_total_loss_in_regime(self):
        """Disastrous -100% loss day in bear market correctly triggers cagr = -1.0."""
        res = calculate_multi_regime_breakdown([-1.0], ["bear"])
        assert res["bear"]["count"] == 1.0
        assert res["bear"]["net_return"] <= -1.0
        assert res["bear"]["net_max_drawdown"] <= -1.0

    def test_regime_breakdown_metric_keys_completeness(self):
        """Every regime partition contains all standard evaluation keys."""
        returns = [0.01, -0.01, 0.001]
        regimes = ["bull", "bear", "sideways"]

        res = calculate_multi_regime_breakdown(returns, regimes)
        expected_keys = {
            "count", "return", "net_return", "max_drawdown",
            "net_max_drawdown", "sharpe", "net_sharpe",
            "sortino", "net_sortino", "calmar", "net_calmar"
        }
        for r in ["bull", "bear", "sideways"]:
            assert expected_keys.issubset(res[r].keys()), f"Missing keys in regime {r}: {expected_keys - res[r].keys()}"

    def test_empty_trades_net_performance_metrics(self):
        """Zero trades during a regime period: total friction is 0.0 bps."""
        returns = [0.01, 0.02, 0.015]
        perf = calculate_net_performance_metrics(trades=[], daily_returns=returns, friction=FrictionConfig())
        assert perf["trade_count"] == 0
        assert perf["total_frictions_bps"] == 0.0
        assert perf["net_return"] == pytest.approx(perf["gross_return"], abs=1e-6)


# ==============================================================================
# 2. Coordination Cost & CBS Calculations Stress-Tests
# ==============================================================================

class TestChallengerCoordinationCostStress:
    """Empirical challenge on calculate_cbs_and_coordination_cost."""

    def test_empty_debate_records_defaults(self):
        """Empty input records produce clean dictionary with zero metrics."""
        res = calculate_cbs_and_coordination_cost([])
        assert res["realized_cbs_bps"] == 0.0
        assert res["total_decisions"] == 0.0
        assert res["token_cost_per_decision"] == 0.0
        assert res["latency_ms_per_decision"] == 0.0
        assert res["fast_path_debate_bypass_rate"] == 0.0
        assert res["debate_trigger_rate"] == 0.0

    def test_zero_cbs_values(self):
        """Explicit 0.0 CBS values result in mean 0.0 bps."""
        records = [
            {"cbs_bps": 0.0, "route": "fast_path", "tokens": 100, "latency_ms": 10.0},
            {"cbs_bps": 0.0, "route": "fast_path", "tokens": 150, "latency_ms": 12.0},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert res["realized_cbs_bps"] == 0.0
        assert res["total_decisions"] == 2.0
        assert res["fast_path_debate_bypass_rate"] == 1.0

    def test_negative_and_extreme_cbs_values(self):
        """Negative CBS or extreme high CBS handled cleanly without numerical failure."""
        records = [
            {"cbs_bps": -5.0, "route": "fast_path", "tokens": 50},
            {"cbs_bps": 500.0, "route": "multi_round_debate", "tokens": 2500},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert res["realized_cbs_bps"] == pytest.approx(247.5, abs=1e-5)
        assert res["total_decisions"] == 2.0
        assert res["fast_path_debate_bypass_rate"] == 0.5
        assert res["debate_trigger_rate"] == 0.5

    def test_missing_tokens_fallback_resolution(self):
        """Fallback to prompt_tokens + completion_tokens, tokens_consumed, total_tokens."""
        records = [
            {"cbs_bps": 10.0, "prompt_tokens": 120, "completion_tokens": 30},
            {"cbs_bps": 12.0, "tokens_consumed": 200},
            {"cbs_bps": 14.0, "total_tokens": 300},
            {"cbs_bps": 16.0},  # Completely missing tokens key -> 0.0
        ]
        res = calculate_cbs_and_coordination_cost(records)
        # [150, 200, 300, 0] -> mean = 162.5
        assert res["token_cost_per_decision"] == pytest.approx(162.5, abs=1e-5)
        assert res["tokens_per_decision"] == pytest.approx(162.5, abs=1e-5)

    def test_missing_latency_various_units(self):
        """Parses latency_ms, latency_sec, latency_seconds, and raw seconds heuristic."""
        records = [
            {"cbs_bps": 10.0, "latency_ms": 250.0},
            {"cbs_bps": 10.0, "latency_sec": 0.50},       # 500 ms
            {"cbs_bps": 10.0, "latency_seconds": 0.15},   # 150 ms
            {"cbs_bps": 10.0, "latency": 0.05},          # < 10.0 -> treated as sec -> 50 ms
            {"cbs_bps": 10.0, "latency": 120.0},         # >= 10.0 -> treated as ms -> 120 ms
            {"cbs_bps": 10.0},                            # Missing -> 0 ms
        ]
        res = calculate_cbs_and_coordination_cost(records)
        # Latencies in ms: [250, 500, 150, 50, 120, 0] -> sum = 1070 -> mean = 178.333 ms
        assert res["latency_ms_per_decision"] == pytest.approx(1070.0 / 6.0, abs=1e-3)
        assert res["latency_sec_per_decision"] == pytest.approx((1070.0 / 6.0) / 1000.0, abs=1e-5)

    def test_all_bypass_rate_100_percent(self):
        """All records routing to fast_path results in bypass_rate = 1.0 and trigger_rate = 0.0."""
        records = [
            {"cbs_bps": 5.0, "route": "fast_path"},
            {"cbs_bps": 4.0, "is_fast_path": True},
            {"cbs_bps": 6.0, "debate_rounds": 0},
            {"cbs_bps": 3.0, "debate_triggered": False},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert res["fast_path_debate_bypass_rate"] == 1.0
        assert res["debate_trigger_rate"] == 0.0

    def test_zero_bypass_rate_0_percent(self):
        """All records routing to debate results in bypass_rate = 0.0 and trigger_rate = 1.0."""
        records = [
            {"cbs_bps": 25.0, "route": "multi_round_debate", "debate_rounds": 2},
            {"cbs_bps": 30.0, "route": "multi_round_debate", "debate_rounds": 3},
            {"cbs_bps": 18.0, "route": "debate", "debate_rounds": 1},
        ]
        res = calculate_cbs_and_coordination_cost(records)
        assert res["fast_path_debate_bypass_rate"] == 0.0
        assert res["debate_trigger_rate"] == 1.0

    def test_fast_path_flag_polymorphism(self):
        """All documented flags triggering fast_path are recognized correctly."""
        assert calculate_cbs_and_coordination_cost([{"route": "fast_path"}])["fast_path_debate_bypass_rate"] == 1.0
        assert calculate_cbs_and_coordination_cost([{"fast_path": True}])["fast_path_debate_bypass_rate"] == 1.0
        assert calculate_cbs_and_coordination_cost([{"is_fast_path": True}])["fast_path_debate_bypass_rate"] == 1.0
        assert calculate_cbs_and_coordination_cost([{"debate_triggered": False}])["fast_path_debate_bypass_rate"] == 1.0
        assert calculate_cbs_and_coordination_cost([{"debate_rounds": 0}])["fast_path_debate_bypass_rate"] == 1.0
        assert calculate_cbs_and_coordination_cost([{"dynamic_debate_rounds": 0}])["fast_path_debate_bypass_rate"] == 1.0

    def test_empty_dict_records_treated_as_debate(self):
        """An empty dict record with no fast-path markers defaults to debate_triggered = 1.0."""
        res = calculate_cbs_and_coordination_cost([{}])
        assert res["fast_path_debate_bypass_rate"] == 0.0
        assert res["debate_trigger_rate"] == 1.0


# ==============================================================================
# 3. Comprehensive Validation of Config A, B, C, D Specifications
# ==============================================================================

class TestChallengerAblationSpecifications:
    """Rigorous verification of the 4 ablation configurations per Milestone M4 specs."""

    @pytest.fixture(scope="class")
    @classmethod
    def dataset(cls):
        """Standard 60-day multi-regime dataset (20 bull, 20 bear, 20 sideways)."""
        return SyntheticMarketFeed.generate_60_day_series()

    def test_config_a_specification_invariants(self, dataset):
        """
        Config A (Linear Pipeline):
        1. Never triggers multi-round debate (debate_triggers == 0, fast_path == 60)
        2. Static uniform weights across all 60 days
        3. Regime-blind memory retrieval
        4. Lowest token overhead among multi-agent configurations
        """
        res = AblationEngine.run_simulation("CONFIG_A", dataset)

        assert res["config_type"] == "CONFIG_A"
        assert res["debate_triggers"] == 0
        assert res["fast_path_triggers"] == 60
        assert res["total_tokens"] > 0

        # Weights must be absent or static uniform
        assert res["weights_state"] is None

    def test_config_b_specification_invariants(self, dataset):
        """
        Config B (Vanilla TradingAgents):
        1. Always triggers multi-round debate on every single day (debate_triggers == 60, fast_path == 0)
        2. Static uniform weights (no adaptation)
        3. Regime-blind memory retrieval
        4. Highest token cost and highest latency among all 4 configurations
        """
        res_b = AblationEngine.run_simulation("CONFIG_B", dataset)
        res_a = AblationEngine.run_simulation("CONFIG_A", dataset)
        res_c = AblationEngine.run_simulation("CONFIG_C", dataset)

        assert res_b["config_type"] == "CONFIG_B"
        assert res_b["debate_triggers"] == 60
        assert res_b["fast_path_triggers"] == 0

        # Token and latency consumption must dominate Config A and C
        assert res_b["total_tokens"] > res_a["total_tokens"]
        assert res_b["total_tokens"] > res_c["total_tokens"]
        assert res_b["total_latency_sec"] > res_a["total_latency_sec"]
        assert res_b["total_latency_sec"] > res_c["total_latency_sec"]

    def test_config_c_specification_invariants(self, dataset):
        """
        Config C (Self-Debate 1-Shot):
        1. Replaces multi-round debate with 1-shot self-debate (debate_triggers == 0, fast_path == 60)
        2. Static uniform weights
        3. Regime-blind memory
        4. Token cost strictly between Config A and Config B
        """
        res_a = AblationEngine.run_simulation("CONFIG_A", dataset)
        res_b = AblationEngine.run_simulation("CONFIG_B", dataset)
        res_c = AblationEngine.run_simulation("CONFIG_C", dataset)

        assert res_c["config_type"] == "CONFIG_C"
        assert res_c["debate_triggers"] == 0
        assert res_c["fast_path_triggers"] == 60

        # Token cost strict ordering: Config A < Config C < Config B
        assert res_a["total_tokens"] < res_c["total_tokens"] < res_b["total_tokens"]
        assert res_a["total_latency_sec"] <= res_c["total_latency_sec"] < res_b["total_latency_sec"]

    def test_config_d_cbs_gating_invariants(self):
        """
        Config D CBS Gating Contract:
        - If JSD < 0.12 -> route == 'fast_path', dynamic_rounds == 0
        - If CBS_bps <= estimated_spread_bps -> route == 'fast_path', dynamic_rounds == 0
        - If JSD >= 0.12 AND CBS_bps > estimated_spread_bps -> route == 'multi_round_debate', dynamic_rounds in [1, max_rounds]
        """
        # Case 1: Low JSD, high expected move -> fast_path because JSD < 0.12
        post_low_jsd = {
            "a1": {"p_optimistic": 0.80, "p_neutral": 0.15, "p_cautious": 0.05, "expected_move_bps": 200.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.78, "p_neutral": 0.17, "p_cautious": 0.05, "expected_move_bps": 190.0, "confidence": 0.9},
        }
        r1 = calculate_cbs_routing(post_low_jsd, estimated_spread_bps=15.0)
        assert r1["jsd"] < 0.12
        assert r1["route"] == "fast_path"
        assert r1["dynamic_debate_rounds"] == 0

        # Case 2: High JSD, tiny expected move -> CBS <= 15 bps -> fast_path
        post_tiny_move = {
            "a1": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 10.0, "confidence": 1.0},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": 10.0, "confidence": 1.0},
        }
        r2 = calculate_cbs_routing(post_tiny_move, estimated_spread_bps=15.0)
        assert r2["jsd"] >= 0.12
        assert r2["cbs_bps"] <= 15.0
        assert r2["route"] == "fast_path"
        assert r2["dynamic_debate_rounds"] == 0

        # Case 3: High JSD AND CBS > 15 bps -> multi_round_debate
        post_high_divergence = {
            "a1": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 150.0, "confidence": 1.0},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": 150.0, "confidence": 1.0},
        }
        r3 = calculate_cbs_routing(post_high_divergence, estimated_spread_bps=15.0, max_debate_rounds=3)
        assert r3["jsd"] >= 0.12
        assert r3["cbs_bps"] > 15.0
        assert r3["route"] == "multi_round_debate"
        assert 1 <= r3["dynamic_debate_rounds"] <= 3

    def test_config_d_mwu_weights_regime_isolation(self):
        """
        Config D MWU Weight Adaptation:
        - Updates in 'bull' regime must NOT modify 'bear' or 'sideways' weights.
        - High-performing analysts gain weight; poorly-performing analysts lose weight.
        - Weight vector sums to 1.0 (normalization invariant).
        """
        calc = ReferenceRegimeAdaptiveWeightCalculator(learning_rate=0.3)
        bear_initial = copy.deepcopy(calc.get_weights("bear"))
        sideways_initial = copy.deepcopy(calc.get_weights("sideways"))

        bull_posteriors = {
            "market_analyst_v2": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05},
            "news_analyst_v2": {"p_optimistic": 0.05, "p_neutral": 0.10, "p_cautious": 0.85},
        }
        realized_return = +0.03  # Strong positive bull move

        updated_bull = calc.update_weights("bull", bull_posteriors, realized_return)

        # 1. Bull weights evolved correctly
        assert updated_bull["market_analyst_v2"] > updated_bull["news_analyst_v2"]
        assert abs(sum(updated_bull.values()) - 1.0) < 1e-4

        # 2. Strict regime isolation: bear and sideways weights remain unaltered
        bear_current = calc.get_weights("bear")
        sideways_current = calc.get_weights("sideways")
        for aid in ANALYST_IDS:
            assert bear_current[aid] == bear_initial[aid]
            assert sideways_current[aid] == sideways_initial[aid]

    def test_config_d_circuit_breaker_confidence_threshold(self):
        """
        Config D Circuit-Breaker on Memory:
        - When regime_confidence >= 0.5: conflicting regime memories are filtered out for decision agents.
        - When regime_confidence < 0.5: circuit is bypassed, cross-regime memories are retained.
        - Non-decision agents (e.g. news_analyst_v2) never have memories filtered.
        """
        memories = [
            {"id": "m_bull", "metadata": {"market_regime": "bull"}},
            {"id": "m_bear", "metadata": {"market_regime": "bear"}},
            {"id": "m_side", "metadata": {"market_regime": "sideways"}},
        ]

        # Decision agent with high confidence in bear regime
        filtered_bear = circuit_breaker_memory_filter(memories, "bear", regime_confidence=0.75, agent_id="trader_v2")
        assert len(filtered_bear) == 1
        assert filtered_bear[0]["id"] == "m_bear"

        # Decision agent with low confidence (< 0.5) in bear regime
        bypassed_bear = circuit_breaker_memory_filter(memories, "bear", regime_confidence=0.45, agent_id="trader_v2")
        assert len(bypassed_bear) == 3

        # Non-decision agent always bypassed
        analyst_mem = circuit_breaker_memory_filter(memories, "bear", regime_confidence=0.99, agent_id="news_analyst_v2")
        assert len(analyst_mem) == 3

    def test_config_d_counterfactual_credit_four_quadrants(self):
        """
        Config D Counterfactual Credit Assignment:
        Verifies all 4 quadrants calculate correct attribution scores and directional sign.
        """
        # Q1: Vindicated & Followed (Bull stance, bought, gained +3%) -> Score > 0
        q1 = calculate_counterfactual_attribution(+1.0, +0.03, "buy", agent_confidence=0.85)
        assert q1["quadrant"] == "Q1_Vindicated_Followed"
        assert q1["attribution_score"] == pytest.approx(0.03 * 0.85, abs=1e-5)

        # Q2: Vindicated & Overridden (Bear stance, bought, lost -4%) -> Score = +|R| (Counterfactual alpha)
        q2 = calculate_counterfactual_attribution(-1.0, -0.04, "buy", agent_confidence=0.80)
        assert q2["quadrant"] == "Q2_Vindicated_Overridden"
        assert q2["attribution_score"] == pytest.approx(0.04, abs=1e-5)

        # Q3: Faulty & Followed (Bull stance, bought, lost -5%) -> Score = -|R| * conf
        q3 = calculate_counterfactual_attribution(+1.0, -0.05, "buy", agent_confidence=0.90)
        assert q3["quadrant"] == "Q3_Faulty_Followed"
        assert q3["attribution_score"] == pytest.approx(-0.05 * 0.90, abs=1e-5)

        # Q4: Faulty & Overridden (Bear stance, bought, gained +6%) -> Score = -0.2 * |R| (Mitigated fault)
        q4 = calculate_counterfactual_attribution(-1.0, +0.06, "buy", agent_confidence=0.80)
        assert q4["quadrant"] == "Q4_Faulty_Overridden"
        assert q4["attribution_score"] == pytest.approx(-0.2 * 0.06, abs=1e-5)

    def test_full_ablation_pareto_dominance_and_tradeoffs(self, dataset):
        """
        Full 60-day ablation comparison verifying Milestone M4 Pareto claims:
        - Config D saves > 25% tokens vs Config B
        - Config D has lower total latency than Config B
        - Config D Net Sharpe >= Config A and Config B
        - Config D Bear regime Maximum Drawdown is better (less negative) than Config A
        """
        res_a = AblationEngine.run_simulation("CONFIG_A", dataset)
        res_b = AblationEngine.run_simulation("CONFIG_B", dataset)
        res_c = AblationEngine.run_simulation("CONFIG_C", dataset)
        res_d = AblationEngine.run_simulation("CONFIG_D", dataset)

        # 1. Token savings
        token_savings_pct = (res_b["total_tokens"] - res_d["total_tokens"]) / res_b["total_tokens"]
        assert token_savings_pct > 0.25, f"Expected >25% token savings vs Config B, got {token_savings_pct*100:.1f}%"

        # 2. Latency savings
        assert res_d["total_latency_sec"] < res_b["total_latency_sec"]

        # 3. Dynamic gating behavior
        assert res_d["fast_path_triggers"] > 0
        assert res_d["debate_triggers"] > 0
        assert res_d["fast_path_triggers"] + res_d["debate_triggers"] == len(dataset)

        # 4. Bear market risk control
        bear_mdd_d = res_d["regime_breakdown"]["bear"]["net_max_drawdown"]
        bear_mdd_a = res_a["regime_breakdown"]["bear"]["net_max_drawdown"]
        assert bear_mdd_d >= bear_mdd_a, f"Config D bear MDD ({bear_mdd_d}) should be >= Config A ({bear_mdd_a})"

        # 5. Risk-adjusted performance
        assert res_d["performance"]["net_sharpe"] >= res_a["performance"]["net_sharpe"]
        assert res_d["performance"]["net_sortino"] >= res_a["performance"]["net_sortino"]


# ==============================================================================
# 4. Hostile Adversarial Edge Cases
# ==============================================================================

class TestChallengerAdversarialScenarios:
    """Stress-test harsh boundary scenarios and extreme market configurations."""

    def test_adversarial_rapid_regime_whipsaw(self):
        """Rapid regime flipping every single day (bull -> bear -> sideways -> bull...)."""
        whipsaw_series = []
        regimes_cycle = ["bull", "bear", "sideways"]
        price = 100.0

        for t in range(1, 31):
            r = regimes_cycle[(t - 1) % 3]
            ret = 0.015 if r == "bull" else (-0.015 if r == "bear" else 0.0)
            price *= (1.0 + ret)

            if r == "bull":
                post = {aid: {"p_optimistic": 0.8, "p_neutral": 0.15, "p_cautious": 0.05, "expected_move_bps": 100.0, "confidence": 0.8} for aid in ANALYST_IDS}
            elif r == "bear":
                post = {aid: {"p_optimistic": 0.05, "p_neutral": 0.15, "p_cautious": 0.8, "expected_move_bps": -100.0, "confidence": 0.8} for aid in ANALYST_IDS}
            else:
                post = {aid: {"p_optimistic": 0.33, "p_neutral": 0.34, "p_cautious": 0.33, "expected_move_bps": 0.0, "confidence": 0.5} for aid in ANALYST_IDS}

            whipsaw_series.append({
                "day": t,
                "date": f"2026-06-{t:02d}",
                "ticker": "000001.SZ",
                "current_price": round(price, 2),
                "realized_return": ret,
                "market_regime": r,
                "volatility_quintile": 4,
                "analyst_posteriors": post,
            })

        res_d = AblationEngine.run_simulation("CONFIG_D", whipsaw_series)
        assert res_d["config_type"] == "CONFIG_D"
        assert len(res_d["regime_breakdown"]) == 3
        assert "bull" in res_d["regime_breakdown"]
        assert "bear" in res_d["regime_breakdown"]
        assert "sideways" in res_d["regime_breakdown"]

    def test_adversarial_extreme_frictions_cbs_suppression(self):
        """
        When friction spread is extremely high (e.g., 100 bps),
        CBS gating must suppress debate on almost all days to preserve capital.
        """
        posteriors = {
            "a1": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 80.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.10, "p_neutral": 0.10, "p_cautious": 0.80, "expected_move_bps": -80.0, "confidence": 0.9},
        }
        # JSD is high (~0.6), weighted move is 80 bps -> CBS = (0.6 * 80) / 2 = 24 bps
        # With spread = 50 bps, 24 bps <= 50 bps -> routes to fast_path
        routing = calculate_cbs_routing(posteriors, estimated_spread_bps=50.0)
        assert routing["route"] == "fast_path"
        assert routing["cbs_bps"] <= 50.0

    def test_adversarial_zero_friction_stability(self):
        """Zero friction configuration (0 bps stamp duty, 0 commission, 0 slippage)."""
        friction_zero = FrictionConfig(sell_stamp_duty_bps=0.0, commission_bps=0.0, slippage_bps=0.0)
        trades = [{"action": "buy"}, {"action": "sell"}]
        perf = calculate_net_performance_metrics([0.01, -0.005], trades, friction_zero)

        assert perf["total_frictions_bps"] == 0.0
        assert perf["net_return"] == perf["gross_return"]
        assert perf["net_sharpe"] == pytest.approx(perf["net_sharpe"], abs=1e-5)

    def test_adversarial_analyst_dropout_single_active(self):
        """When only 1 analyst responds, JSD is 0.0, CBS is 0.0, fast-path is selected."""
        single_post = {
            "market_analyst_v2": {"p_optimistic": 0.9, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 120.0, "confidence": 0.9}
        }
        routing = calculate_cbs_routing(single_post, estimated_spread_bps=15.0)
        assert routing["jsd"] == 0.0
        assert routing["cbs_bps"] == 0.0
        assert routing["route"] == "fast_path"

    def test_adversarial_uncalibrated_probabilities_normalization(self):
        """Probabilities that do not sum to 1.0 (e.g. unnormalized sum = 1.5) are normalized."""
        uncalibrated = {
            "a1": {"p_optimistic": 0.9, "p_neutral": 0.3, "p_cautious": 0.3, "expected_move_bps": 100.0},
            "a2": {"p_optimistic": 0.2, "p_neutral": 0.4, "p_cautious": 0.9, "expected_move_bps": 100.0},
        }
        jsd = calculate_base2_jsd(uncalibrated)
        assert 0.0 <= jsd <= 1.0

        calc = ReferenceRegimeAdaptiveWeightCalculator()
        loss = calc.compute_brier_loss(uncalibrated["a1"], realized_return=+0.02)
        assert 0.0 <= loss <= 2.0
