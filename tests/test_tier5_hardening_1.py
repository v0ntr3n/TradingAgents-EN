"""
Tier 5 Adversarial Coverage Hardening Suite 1 for CARE-Agents.

Focus areas:
1. AnalystAgent response parsing, heuristic fallback, probability normalization, edge cases.
2. ConditionalLogic base-2 JSD, entropy, CBS gating boundaries, dynamic debate rounds scaling.
3. RegimeAdaptiveWeightCalculator multiclass Brier loss boundaries, learning rate stability, dynamic analyst registration.
4. SignalProcessor Bayesian log-odds pooling, extreme logit clipping, price parsing, and fallback multipliers.
5. Mem0AgentMemory metadata normalization and regime circuit-breaker confidence thresholding.
6. Counterfactual credit assignment 4-quadrant attribution mathematical exactness and prompt builders.
7. Backtest result evaluator polymorphic inputs, A-share friction accounting, zero-division guards, and multi-regime breakdown.
8. RiskSelfDebateV2 single-pass self debate execution, output parsing, and fast-path state reconciliation.
"""

import math
import re
from typing import Any, Dict, List
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.agents.adapters.risk_self_debate_v2 import (
    RiskSelfDebateV2,
    parse_self_debate_response,
)
from core.agents.analyst import (
    DEFAULT_UNINFORMATIVE_POSTERIOR,
    AnalystAgent,
)
from core.agents.reflection_helper import (
    calculate_counterfactual_attribution,
    format_attribution_prompt_block,
)
from core.agents.reflection_prompts import (
    build_analysis_reflection_user_prompt,
    build_debate_reflection_user_prompt,
    build_trade_reflection_user_prompt,
)
from core.agents.utils.weight_calculator import (
    DEFAULT_ANALYST_IDS,
    RegimeAdaptiveWeightCalculator,
    calculate_report_weights,
)
from core.backtest.result_evaluator import (
    FrictionConfig,
    calculate_cbs_and_coordination_cost,
    calculate_multi_regime_breakdown,
    calculate_net_performance_metrics,
)
from core.memory.memory_manager import (
    Mem0AgentMemory,
    circuit_breaker_memory_filter,
)
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    calculate_base2_jsd,
    calculate_cbs_routing,
    compute_base2_jsd,
    compute_shannon_entropy,
    should_trigger_multi_round_debate,
)
from tradingagents.graph.reflection import Reflector
from tradingagents.graph.signal_processing import (
    SignalProcessor,
    calculate_bayesian_log_odds_target_price,
    compute_bayesian_log_odds_details,
)


class ConcreteAnalystAgent(AnalystAgent):
    """Concrete subclass for testing AnalystAgent abstract base class."""

    analyst_type = "test_analyst"
    output_field = "test_report"

    def _build_system_prompt(self, market_type: str, context=None, state: Dict[str, Any] = None) -> str:
        return "System prompt for test analyst"

    def _build_user_prompt(self, ticker: str, analysis_date: str, tool_data: Dict[str, Any], state: Dict[str, Any]) -> str:
        return f"Analyze {ticker} on {analysis_date}"


# ==============================================================================
# Suite 1: AnalystAgent Response Parsing & Normalization Hardening
# ==============================================================================

class TestTier5AnalystParsingHardening:
    @pytest.fixture
    def agent(self):
        return ConcreteAnalystAgent(config=None)

    def test_parse_response_none_and_empty(self, agent):
        """None or empty response should fallback to default uninformative posterior."""
        for val in [None, "", "   ", "\n\t"]:
            res = agent._parse_response(val)
            assert res["success"] is True
            assert res["content"].strip() == ""
            post = res["posterior"]
            assert pytest.approx(post["p_optimistic"] + post["p_neutral"] + post["p_cautious"], abs=1e-4) == 1.0
            assert post["market_regime"] == "sideways"
            assert post["confidence"] == 0.0

    def test_parse_response_dict_with_posteriors(self, agent):
        """Dict input containing posterior fields should normalize cleanly."""
        raw_dict = {
            "p_optimistic": 0.7,
            "p_neutral": 0.2,
            "p_cautious": 0.1,
            "expected_move_bps": 120.5,
            "confidence": 0.85,
            "market_regime": "bull",
            "content": "# Bullish Report\nStrong momentum observed."
        }
        res = agent._parse_response(raw_dict)
        assert res["success"] is True
        assert res["content"] == "# Bullish Report\nStrong momentum observed."
        assert res["p_optimistic"] == 0.7
        assert res["market_regime"] == "bull"

    def test_normalize_posterior_extreme_numbers(self, agent):
        """Probabilities with zero sum, extreme values, or percentages."""
        # All zeros -> equal fallback
        norm_zero = agent._normalize_posterior({"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 0.0})
        assert pytest.approx(norm_zero["p_optimistic"] + norm_zero["p_neutral"] + norm_zero["p_cautious"], abs=1e-4) == 1.0
        assert norm_zero["p_neutral"] >= 0.33

        # Percentage scale e.g. [70, 20, 10]
        norm_pct = agent._normalize_posterior({"p_optimistic": 70, "p_neutral": 20, "p_cautious": 10})
        assert pytest.approx(norm_pct["p_optimistic"], abs=1e-2) == 0.70
        assert pytest.approx(norm_pct["p_neutral"], abs=1e-2) == 0.20
        assert pytest.approx(norm_pct["p_cautious"], abs=1e-2) == 0.10

        # Negative probabilities clamped to >= 0
        norm_neg = agent._normalize_posterior({"p_optimistic": -0.5, "p_neutral": 0.8, "p_cautious": 0.2})
        assert norm_neg["p_optimistic"] == 0.0
        assert pytest.approx(norm_neg["p_neutral"] + norm_neg["p_cautious"], abs=1e-4) == 1.0

    def test_normalize_posterior_expected_move_variants(self, agent):
        """Parse various string formats for expected_move_bps."""
        cases = [
            ("+150bps", 150.0),
            ("-80bp", -80.0),
            ("2.5%", 250.0),  # 2.5% * 100 = 250 bps
            ("+0.75%", 75.0),
            ("1,200 bps", 1200.0),
            ("invalid_str", 0.0),
            (None, 0.0),
        ]
        for raw_val, expected in cases:
            norm = agent._normalize_posterior({
                "p_optimistic": 0.3333, "p_neutral": 0.3334, "p_cautious": 0.3333,
                "expected_move_bps": raw_val,
            })
            assert norm["expected_move_bps"] == expected

    def test_normalize_posterior_implicit_move_from_skew(self, agent):
        """When expected_move_bps is 0 but probability skew is high, estimate move."""
        norm = agent._normalize_posterior({
            "p_optimistic": 0.8,
            "p_neutral": 0.1,
            "p_cautious": 0.1,
            "expected_move_bps": 0.0,
        })
        # (0.8 - 0.1) * 100 = 70.0 bps
        assert norm["expected_move_bps"] == 70.0
        assert norm["market_regime"] == "bull"

    def test_normalize_posterior_confidence_clamping(self, agent):
        """Confidence percentages and out-of-bounds numbers."""
        assert agent._normalize_posterior({"confidence": "95%"})["confidence"] == 0.95
        assert agent._normalize_posterior({"confidence": 85.0})["confidence"] == 0.85
        assert agent._normalize_posterior({"confidence": 1.5})["confidence"] == 1.0
        assert agent._normalize_posterior({"confidence": -0.2})["confidence"] == 0.0

    def test_normalize_posterior_market_regime_synonyms(self, agent):
        """All supported regime synonyms and heuristic inference."""
        synonyms = {
            "bullish": "bull",
            "long": "bull",
            "uptrend": "bull",
            "bearish": "bear",
            "short": "bear",
            "downtrend": "bear",
            "range-bound": "sideways",
            "consolidation": "sideways",
            "flat": "sideways",
            "chop": "sideways",
        }
        for syn, expected in synonyms.items():
            norm = agent._normalize_posterior({"market_regime": syn})
            assert norm["market_regime"] == expected

        # Heuristic regime derivation from probabilities
        norm_derived_bull = agent._normalize_posterior({
            "p_optimistic": 0.75, "p_neutral": 0.15, "p_cautious": 0.10, "expected_move_bps": 80.0
        })
        assert norm_derived_bull["market_regime"] == "bull"

        norm_derived_bear = agent._normalize_posterior({
            "p_optimistic": 0.10, "p_neutral": 0.15, "p_cautious": 0.75, "expected_move_bps": -80.0
        })
        assert norm_derived_bear["market_regime"] == "bear"

    def test_signal_block_delimiters_and_repair(self, agent):
        """Parse various markdown tags, html comments, and repair single quotes & trailing commas."""
        # 1. XML tag <signal_block>
        t1 = "Analysis body\n<signal_block>\n{'p_optimistic': 0.6, 'p_neutral': 0.3, 'p_cautious': 0.1, 'expected_move_bps': 45.0,}\n</signal_block>"
        r1 = agent._parse_response(t1)
        assert r1["content"] == "Analysis body"
        assert pytest.approx(r1["p_optimistic"], abs=1e-2) == 0.6

        # 2. HTML comment <!-- SIGNAL_BLOCK: ... -->
        t2 = "Analysis body\n<!-- SIGNAL_BLOCK: {\"p_optimistic\": 0.2, \"p_neutral\": 0.3, \"p_cautious\": 0.5, \"expected_move_bps\": -35.0} -->"
        r2 = agent._parse_response(t2)
        assert r2["content"] == "Analysis body"
        assert pytest.approx(r2["p_cautious"], abs=1e-2) == 0.5

        # 3. Triple backticks with json:signal
        t3 = "Prefix report.\n```json:signal\n{\n  'p_optimistic': 0.8,\n  'p_neutral': 0.1,\n  'p_cautious': 0.1,\n  'confidence': None,\n}\n```\nSuffix note."
        r3 = agent._parse_response(t3)
        assert "Prefix report." in r3["content"]
        assert "Suffix note." in r3["content"]
        assert "```json:signal" not in r3["content"]
        assert pytest.approx(r3["p_optimistic"], abs=1e-2) == 0.8

    def test_heuristic_text_cues_fallback(self, agent):
        """When no JSON block is present, extract sentiment from text cues."""
        bull_text = "根据近期行情判断，该股突破上行，多头格局确立，建议强烈看多买入，未来空间巨大。"
        r_bull = agent._parse_response(bull_text)
        assert r_bull["market_regime"] == "bull"
        assert r_bull["p_optimistic"] > r_bull["p_cautious"]

        bear_text = "该股技术面严重破位，空头排列，资金持续流出，建议强烈看空卖出减持。"
        r_bear = agent._parse_response(bear_text)
        assert r_bear["market_regime"] == "bear"
        assert r_bear["p_cautious"] > r_bull["p_cautious"]


# ==============================================================================
# Suite 2: Conditional Logic, Base-2 JSD & CBS Debate Gating Hardening
# ==============================================================================

class TestTier5ConditionalLogicHardening:
    def test_entropy_properties(self):
        """Shannon entropy must be 0 for deterministic distribution and log2(k) for uniform."""
        assert compute_shannon_entropy([1.0, 0.0, 0.0]) == 0.0
        # Uniform 3-class distribution entropy = log2(3) ~ 1.58496
        u3 = compute_shannon_entropy([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])
        assert pytest.approx(u3, abs=1e-4) == math.log2(3.0)

    def test_compute_base2_jsd_edge_cases(self):
        """Base-2 JSD edge cases: single distribution, mismatched dimensions, all zeros."""
        assert compute_base2_jsd([]) == 0.0
        assert compute_base2_jsd([[0.5, 0.5]]) == 0.0
        assert compute_base2_jsd([[0.3, 0.7], [0.3, 0.7]]) == 0.0

        # Dimension mismatch should raise ValueError
        with pytest.raises(ValueError, match="Inconsistent distribution dimensions"):
            compute_base2_jsd([[0.5, 0.5], [0.3, 0.3, 0.4]])

        # Zero sum distributions normalized safely without zero-division
        res = compute_base2_jsd([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        assert 0.0 <= res <= 1.0

    def test_cbs_routing_threshold_exact_boundaries(self):
        """Test exact thresholds: JSD < 0.12 or CBS_bps <= 15.0."""
        # 1. JSD just below 0.12 -> fast_path regardless of move
        post_low_jsd = {
            "a1": {"p_optimistic": 0.40, "p_neutral": 0.30, "p_cautious": 0.30, "expected_move_bps": 200.0, "confidence": 0.8},
            "a2": {"p_optimistic": 0.45, "p_neutral": 0.25, "p_cautious": 0.30, "expected_move_bps": 200.0, "confidence": 0.8},
        }
        r_low_jsd = calculate_cbs_routing(post_low_jsd, estimated_spread_bps=15.0)
        assert r_low_jsd["jsd"] < 0.12
        assert r_low_jsd["route"] == "fast_path"
        assert r_low_jsd["dynamic_debate_rounds"] == 0

        # 2. High JSD but tiny expected move -> CBS <= 15.0 -> fast_path
        post_high_jsd_tiny_move = {
            "a1": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 10.0, "confidence": 0.8},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": 10.0, "confidence": 0.8},
        }
        r_tiny_move = calculate_cbs_routing(post_high_jsd_tiny_move, estimated_spread_bps=15.0)
        assert r_tiny_move["jsd"] > 0.50
        # CBS = (JSD * 10) / 2 < 5 bps <= 15 bps
        assert r_tiny_move["cbs_bps"] <= 15.0
        assert r_tiny_move["route"] == "fast_path"

        # 3. High JSD and high expected move -> CBS > 15.0 -> multi_round_debate
        post_high_cbs = {
            "a1": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 150.0, "confidence": 0.9},
            "a2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": 150.0, "confidence": 0.9},
        }
        r_high_cbs = calculate_cbs_routing(post_high_cbs, estimated_spread_bps=15.0, max_debate_rounds=3)
        assert r_high_cbs["jsd"] > 0.50
        assert r_high_cbs["cbs_bps"] > 15.0
        assert r_high_cbs["route"] == "multi_round_debate"
        assert r_high_cbs["dynamic_debate_rounds"] >= 2

    def test_dynamic_rounds_monotonic_scaling(self):
        """Dynamic rounds scale monotonically between 1 and max_debate_rounds as JSD increases."""
        cl = ConditionalLogic(max_debate_rounds=5)
        # Moderate JSD ~ 0.30
        p_mid = {
            "a1": {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 100.0},
            "a2": {"p_optimistic": 0.20, "p_neutral": 0.20, "p_cautious": 0.60, "expected_move_bps": 100.0},
        }
        r_mid = calculate_cbs_routing(p_mid, estimated_spread_bps=10.0, max_debate_rounds=5)
        assert r_mid["route"] == "multi_round_debate"
        rounds_mid = r_mid["dynamic_debate_rounds"]

        # Maximum JSD orthogonal ~ 1.0
        p_max = {
            "a1": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 100.0},
            "a2": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": 100.0},
        }
        r_max = calculate_cbs_routing(p_max, estimated_spread_bps=10.0, max_debate_rounds=5)
        rounds_max = r_max["dynamic_debate_rounds"]

        assert rounds_max >= rounds_mid
        assert rounds_max == 5

    def test_conditional_logic_state_mutation(self):
        """Verify state keys injected during should_trigger_multi_round_debate."""
        cl = ConditionalLogic(max_debate_rounds=3)
        state: Dict[str, Any] = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.35, "p_neutral": 0.35, "p_cautious": 0.30, "expected_move_bps": 10.0},
                "a2": {"p_optimistic": 0.33, "p_neutral": 0.34, "p_cautious": 0.33, "expected_move_bps": 10.0},
            },
            "estimated_spread_bps": 15.0,
        }
        decision = cl.should_trigger_multi_round_debate(state)
        assert decision == "fast_path"
        assert state["_risk_self_debate"] is True
        assert state["debate_jsd"] < 0.12
        assert state["dynamic_debate_rounds"] == 0

    def test_should_continue_debate_turns_and_limits(self):
        """Test debate continuation loop and termination count."""
        cl = ConditionalLogic(max_debate_rounds=2)
        # 1. First turn: Bull speaker finished -> Bear speaker turn
        state_turn1 = {
            "investment_debate_state": {
                "count": 1,
                "current_response": "Bull Researcher: Growth momentum strong",
            },
            "dynamic_debate_rounds": 2,
        }
        assert cl.should_continue_debate(state_turn1) == "Bear Researcher"

        # 2. Second turn: Bear speaker finished -> Bull speaker turn
        state_turn2 = {
            "investment_debate_state": {
                "count": 2,
                "current_response": "Bear Researcher: Valuation stretched",
            },
            "dynamic_debate_rounds": 2,
        }
        assert cl.should_continue_debate(state_turn2) == "Bull Researcher"

        # 3. Limit reached (count >= 2 * 2 rounds = 4) -> Research Manager
        state_limit = {
            "investment_debate_state": {
                "count": 4,
                "current_response": "Bear Researcher: Final counter",
            },
            "dynamic_debate_rounds": 2,
        }
        assert cl.should_continue_debate(state_limit) == "Research Manager"


# ==============================================================================
# Suite 3: RegimeAdaptiveWeightCalculator Multiplicative Updates Hardening
# ==============================================================================

class TestTier5WeightCalculatorHardening:
    def test_initialization_with_custom_analysts(self):
        """Custom analysts initialize with uniform 1/N weights per regime."""
        custom_aids = ["quant_v2", "macro_v2"]
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=custom_aids)
        for r in ["bull", "bear", "sideways"]:
            w = calc.get_weights(r)
            assert len(w) == 2
            assert pytest.approx(w["quant_v2"], abs=1e-5) == 0.5
            assert pytest.approx(w["macro_v2"], abs=1e-5) == 0.5

    def test_brier_loss_boundaries_exact(self):
        """Brier loss targets: return > 0.005 -> opt, return < -0.005 -> caut, else neu."""
        calc = RegimeAdaptiveWeightCalculator(return_threshold=0.005)

        perfect_opt = {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0}
        perfect_caut = {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0}
        perfect_neu = {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0}

        # 1. Realized return = +0.010 (> +0.005) -> target [1, 0, 0]
        assert calc.compute_brier_loss(perfect_opt, realized_return=0.010) == 0.0
        assert calc.compute_brier_loss(perfect_caut, realized_return=0.010) == 2.0

        # 2. Realized return = -0.010 (< -0.005) -> target [0, 0, 1]
        assert calc.compute_brier_loss(perfect_caut, realized_return=-0.010) == 0.0
        assert calc.compute_brier_loss(perfect_opt, realized_return=-0.010) == 2.0

        # 3. Realized return = 0.002 (inside deadband [-0.005, +0.005]) -> target [0, 1, 0]
        assert calc.compute_brier_loss(perfect_neu, realized_return=0.002) == 0.0
        assert calc.compute_brier_loss(perfect_opt, realized_return=0.002) == 2.0

        # 4. Exact deadband boundary (+0.005) -> treated as neutral
        assert calc.compute_brier_loss(perfect_neu, realized_return=0.005) == 0.0

    def test_mwu_learning_rate_extremes(self):
        """MWU update stability with eta=0.0 (no change) and eta=50.0 (extreme)."""
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=["a1", "a2"], learning_rate=0.2)
        posteriors = {
            "a1": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0},  # loss = 0.0
            "a2": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0},  # loss = 2.0
        }

        # With eta = 0.0 -> weights unchanged
        w_zero = calc.update_weights("bull", posteriors, realized_return=0.02, learning_rate=0.0)
        assert pytest.approx(w_zero["a1"], abs=1e-5) == 0.5
        assert pytest.approx(w_zero["a2"], abs=1e-5) == 0.5

        # With eta = 50.0 -> a2 exponentially drops near 0 without crash
        w_extreme = calc.update_weights("bull", posteriors, realized_return=0.02, learning_rate=50.0)
        assert pytest.approx(w_extreme["a1"], abs=1e-5) == 1.0
        assert w_extreme["a2"] < 1e-10
        assert pytest.approx(sum(w_extreme.values()), abs=1e-5) == 1.0

    def test_dynamic_analyst_registration(self):
        """When an unexpected analyst ID appears in posteriors, register dynamically."""
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=["a1", "a2"])
        posteriors_with_new = {
            "a1": {"p_optimistic": 0.5, "p_neutral": 0.5, "p_cautious": 0.0},
            "a2": {"p_optimistic": 0.5, "p_neutral": 0.5, "p_cautious": 0.0},
            "new_analyst_v2": {"p_optimistic": 0.9, "p_neutral": 0.1, "p_cautious": 0.0},
        }
        w = calc.update_weights("bull", posteriors_with_new, realized_return=0.03)
        assert "new_analyst_v2" in w
        assert len(w) == 3
        assert pytest.approx(sum(w.values()), abs=1e-5) == 1.0

    def test_fallback_calculate_report_weights(self):
        """Preserve calculate_report_weights fallback functionality."""
        reports = {
            "market_report": "Technical analysis bullish.",
            "news_report": "Positive earnings surprise.",
            "sentiment_report": "Strong social buzz.",
        }
        w = calculate_report_weights(reports, trading_style="short")
        assert pytest.approx(w["market_report"], abs=1e-2) == 0.40
        assert pytest.approx(w["news_report"], abs=1e-2) == 0.30
        assert pytest.approx(w["sentiment_report"], abs=1e-2) == 0.30
        assert pytest.approx(sum(w.values()), abs=1e-4) == 1.0


# ==============================================================================
# Suite 4: Bayesian Log-Odds & Calibrated Signal Processing Hardening
# ==============================================================================

class TestTier5BayesianSignalProcessingHardening:
    def test_bayesian_log_odds_extreme_probabilities_clamping(self):
        """Posteriors with 0.0 probability clamp to eps=1e-4 avoiding math.log(0)."""
        extreme_posteriors = {
            "a1": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": -200.0},
            "a2": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 200.0},
        }
        # Equal weights 0.5 / 0.5 cancel out -> l_agg near l0
        details = compute_bayesian_log_odds_details(
            current_price=100.0,
            action="buy",
            regime="sideways",
            analyst_posteriors=extreme_posteriors,
            weights={"a1": 0.5, "a2": 0.5},
        )
        assert -10.0 <= details["l_agg"] <= 10.0
        assert 0.0 < details["p_agg"] < 1.0
        assert details["target_price"] > 100.0

    def test_bayesian_target_price_actions_and_multipliers_fallback(self):
        """When analyst_posteriors is empty, use legacy fallback multipliers."""
        p_buy = calculate_bayesian_log_odds_target_price(100.0, "buy", "bull", {}, is_china=True)
        assert p_buy == 115.00  # 100 * 1.15

        p_sell = calculate_bayesian_log_odds_target_price(100.0, "sell", "bear", {}, is_china=True)
        assert p_sell == 95.00  # 100 * 0.95

        p_hold = calculate_bayesian_log_odds_target_price(100.0, "hold", "sideways", {}, is_china=True)
        assert p_hold == 100.00

        # US stock market fallback
        p_buy_us = calculate_bayesian_log_odds_target_price(100.0, "buy", "bull", {}, is_china=False)
        assert p_buy_us == 112.00  # 100 * 1.12

        p_sell_us = calculate_bayesian_log_odds_target_price(100.0, "sell", "bear", {}, is_china=False)
        assert p_sell_us == 92.00  # 100 * 0.92

    def test_smart_price_estimation_text_extraction(self):
        """Extract prices and percentage changes from natural language."""
        sp = SignalProcessor()
        text_price = "Based on our model, current price is ¥84.50. We expect upward movement."
        res_price = sp._smart_price_estimation(text_price, action="buy", is_china=True)
        assert res_price == round(84.50 * 1.15, 2)

        text_pct = "The stock is trading at 50.00 yuan, and we anticipate an Increase 10% soon."
        res_pct = sp._smart_price_estimation(text_pct, action="buy", is_china=True)
        assert res_pct == 55.00  # 50 * 1.10

    def test_process_signal_offline_rule_mode(self):
        """Test process_signal without LLM (pure rule-based fallback)."""
        sp = SignalProcessor(quick_thinking_llm=None)
        signal = "FINAL TRANSACTION DECISION: BUY\nTarget Price: 125.00\nConfidence: 0.85\nRisk: 0.3"
        res = sp.process_signal(signal, stock_symbol="600519")
        assert res["action"] == "buy"
        assert res["target_price"] == 125.00
        assert res["confidence"] >= 0.7


# ==============================================================================
# Suite 5: Mem0 Metadata Normalization & Regime Circuit-Breaker Hardening
# ==============================================================================

class TestTier5MemoryCircuitBreakerHardening:
    def test_circuit_breaker_confidence_threshold_exact(self):
        """Circuit breaker triggers at confidence >= 0.5; bypasses at < 0.5."""
        memories = [
            {"id": "m1", "metadata": {"market_regime": "bull"}},
            {"id": "m2", "metadata": {"market_regime": "bear"}},
            {"id": "m3", "metadata": {"market_regime": "sideways"}},
        ]

        # 1. High confidence in Bull regime (0.50 and 0.80) -> filter out bear and sideways
        filtered_high = circuit_breaker_memory_filter(
            memories, current_regime="bull", regime_confidence=0.8, agent_id="bull_researcher_v2"
        )
        assert len(filtered_high) == 1
        assert filtered_high[0]["id"] == "m1"

        filtered_boundary = circuit_breaker_memory_filter(
            memories, current_regime="bull", regime_confidence=0.5, agent_id="bull_researcher_v2"
        )
        assert len(filtered_boundary) == 1
        assert filtered_boundary[0]["id"] == "m1"

        # 2. Low confidence (< 0.5 e.g. 0.49) -> bypass circuit breaker to preserve hedging memories
        bypassed = circuit_breaker_memory_filter(
            memories, current_regime="bull", regime_confidence=0.49, agent_id="bull_researcher_v2"
        )
        assert len(bypassed) == 3

    def test_circuit_breaker_exempt_agents(self):
        """Non-circuit-breaker agents (e.g. news_analyst_v2) are exempt from filtering."""
        memories = [
            {"id": "m1", "metadata": {"market_regime": "bull"}},
            {"id": "m2", "metadata": {"market_regime": "bear"}},
        ]
        res = circuit_breaker_memory_filter(
            memories, current_regime="bull", regime_confidence=1.0, agent_id="news_analyst_v2"
        )
        assert len(res) == 2

    def test_metadata_normalization_mandatory_keys(self):
        """Ensure market_regime, volatility_quintile, and brier_calibration_error are enforced."""
        # Canonical regime is preserved, out-of-bounds numbers clamped
        raw_meta = {
            "ticker": "600519.SH",
            "market_regime": "BULL",
            "volatility_quintile": "7",  # Out of bounds (>5)
            "brier_calibration_error": "-0.15",  # Negative
        }
        normalized = Mem0AgentMemory._normalize_store_metadata(raw_meta)
        assert normalized["market_regime"] == "bull"
        assert normalized["volatility_quintile"] == 5  # Clamped to 5
        assert normalized["brier_calibration_error"] == 0.0  # Clamped to 0.0

        # Non-canonical regime strictly falls back to sideways
        raw_non_canon = {"market_regime": "unknown_trend"}
        norm_non_canon = Mem0AgentMemory._normalize_store_metadata(raw_non_canon)
        assert norm_non_canon["market_regime"] == "sideways"

        # Missing keys default safely
        norm_empty = Mem0AgentMemory._normalize_store_metadata({})
        assert norm_empty["market_regime"] == "sideways"
        assert norm_empty["volatility_quintile"] == 3
        assert norm_empty["brier_calibration_error"] == 0.0


# ==============================================================================
# Suite 6: Counterfactual Credit Assignment & Prompt Hardening
# ==============================================================================

class TestTier5CounterfactualCreditHardening:
    def test_all_four_quadrants_exact_formulas(self):
        """Test exact credit assignment scores across Q1, Q2, Q3, Q4."""
        # Q1: Vindicated & Followed: +|R| * conf
        q1 = calculate_counterfactual_attribution(
            agent_stance="bull", realized_return=0.10, manager_action="buy", agent_confidence=0.8
        )
        assert q1["quadrant"] == "Q1_Vindicated_Followed"
        assert pytest.approx(q1["attribution_score"], abs=1e-5) == 0.08  # 0.10 * 0.8
        assert q1["is_vindicated"] is True
        assert q1["is_followed"] is True

        # Q2: Vindicated & Overridden: +|R| (counterfactual alpha)
        q2 = calculate_counterfactual_attribution(
            agent_stance="bear", realized_return=-0.15, manager_action="buy", agent_confidence=0.9
        )
        assert q2["quadrant"] == "Q2_Vindicated_Overridden"
        assert pytest.approx(q2["attribution_score"], abs=1e-5) == 0.15  # | -0.15 |
        assert q2["is_vindicated"] is True
        assert q2["is_followed"] is False

        # Q3: Faulty & Followed: -|R| * conf
        q3 = calculate_counterfactual_attribution(
            agent_stance="bull", realized_return=-0.08, manager_action="buy", agent_confidence=0.75
        )
        assert q3["quadrant"] == "Q3_Faulty_Followed"
        assert pytest.approx(q3["attribution_score"], abs=1e-5) == -0.06  # -0.08 * 0.75
        assert q3["is_vindicated"] is False
        assert q3["is_followed"] is True

        # Q4: Faulty & Overridden: -0.2 * |R| (mitigated fault)
        q4 = calculate_counterfactual_attribution(
            agent_stance="bull", realized_return=-0.10, manager_action="sell", agent_confidence=0.8
        )
        assert q4["quadrant"] == "Q4_Faulty_Overridden"
        assert pytest.approx(q4["attribution_score"], abs=1e-5) == -0.02  # -0.2 * 0.10
        assert q4["is_vindicated"] is False
        assert q4["is_followed"] is False

    def test_zero_realized_return_boundary(self):
        """Zero realized return yields 0.0 attribution score without crash."""
        q_zero = calculate_counterfactual_attribution(
            agent_stance="neutral", realized_return=0.0, manager_action="hold", agent_confidence=0.8
        )
        assert pytest.approx(q_zero["attribution_score"], abs=1e-5) == 0.0
        assert q_zero["is_vindicated"] is True

    def test_format_attribution_prompt_block(self):
        """Verify prompt block format containing status, attribution score, and directive."""
        attr = {
            "quadrant": "Q2_Vindicated_Overridden",
            "attribution_score": 0.125,
            "directive": "Highlight specific signals dismissed.",
        }
        block = format_attribution_prompt_block(attr)
        assert "=== Counterfactual Credit Assignment ===" in block
        assert "Status: Q2_Vindicated_Overridden" in block
        assert "+0.125" in block
        assert "Directive: Highlight specific signals dismissed." in block

    def test_reflection_prompt_builders_accept_attribution(self):
        """Prompt builders correctly inject attribution context."""
        attr = {
            "quadrant": "Q1_Vindicated_Followed",
            "attribution_score": 0.05,
            "directive": "Reinforce key predictive signals.",
        }
        # 1. Trade prompt builder
        trade_prompt = build_trade_reflection_user_prompt(
            trade_info=MagicMock(code="000001", name="Ping An", first_buy_date="2024-01-01"),
            ai_review=MagicMock(summary="Good trade", strengths=["Patience"], weaknesses=[], suggestions=[], plan_deviation="None"),
            attribution_context=attr,
        )
        assert "=== Counterfactual Credit Assignment ===" in trade_prompt
        assert "Q1_Vindicated_Followed" in trade_prompt

        # 2. Analysis prompt builder
        analysis_prompt = build_analysis_reflection_user_prompt(
            ticker="600519", report={"content": "Strong momentum", "stance": "bull"}, attribution_context=attr
        )
        assert "=== Counterfactual Credit Assignment ===" in analysis_prompt

        # 3. Debate prompt builder
        debate_prompt = build_debate_reflection_user_prompt(
            ticker="600519", debate_history="Bull vs Bear arguments", conclusion="Buy confirmed", attribution_context=attr
        )
        assert "=== Counterfactual Credit Assignment ===" in debate_prompt


# ==============================================================================
# Suite 7: Net Backtest Evaluation Metrics & Multi-Regime Hardening
# ==============================================================================

class TestTier5ResultEvaluatorHardening:
    def test_friction_config_defaults_and_aliases(self):
        """FrictionConfig defaults: 5 bps sell stamp duty, 2.5 bps commission, 5 bps slippage."""
        fc = FrictionConfig()
        assert fc.sell_stamp_duty_bps == 5.0
        assert fc.commission_bps == 2.5
        assert fc.slippage_bps == 5.0
        assert fc.stamp_duty_bps == 5.0  # Backward-compatible property

        # Test alias constructor
        fc_alias = FrictionConfig(stamp_duty_bps=8.0)
        assert fc_alias.sell_stamp_duty_bps == 8.0

    def test_friction_accounting_sell_vs_buy(self):
        """Sell trades incur stamp duty + commission + slippage; buy trades incur no stamp duty."""
        trades_sell_only = [{"action": "sell"}]
        # 5 bps stamp + 2.5 bps comm + 5 bps slip = 12.5 bps
        res_sell = calculate_net_performance_metrics(
            trades=trades_sell_only, daily_returns=[0.01, 0.01], friction=FrictionConfig()
        )
        assert res_sell["total_frictions_bps"] == 12.5

        trades_buy_only = [{"action": "buy"}]
        # 2.5 bps comm + 5 bps slip = 7.5 bps
        res_buy = calculate_net_performance_metrics(
            trades=trades_buy_only, daily_returns=[0.01, 0.01], friction=FrictionConfig()
        )
        assert res_buy["total_frictions_bps"] == 7.5

        # Completed round trip (1 buy + 1 sell) = 12.5 + 7.5 = 20.0 bps
        trades_round_trip = [{"action": "buy"}, {"action": "sell"}]
        res_round = calculate_net_performance_metrics(
            trades=trades_round_trip, daily_returns=[0.01, 0.01], friction=FrictionConfig()
        )
        assert res_round["total_frictions_bps"] == 20.0

    def test_zero_division_guards_in_net_metrics(self):
        """Zero-division protections when returns are empty, constant, or all positive."""
        # 1. Empty returns
        res_empty = calculate_net_performance_metrics(trades=[], daily_returns=[])
        assert res_empty["net_sharpe"] == 0.0
        assert res_empty["net_sortino"] == 0.0
        assert res_empty["net_calmar"] == 0.0
        assert res_empty["net_max_drawdown"] == 0.0

        # 2. Single return observation (ddof=1 protection)
        res_single = calculate_net_performance_metrics(trades=[], daily_returns=[0.01])
        assert res_single["net_sharpe"] == 0.0

        # 3. Constant returns (zero standard deviation)
        res_constant = calculate_net_performance_metrics(trades=[], daily_returns=[0.01, 0.01, 0.01])
        assert res_constant["net_sharpe"] == 0.0

        # 4. Strictly positive returns (downside deviation = 0)
        res_positive = calculate_net_performance_metrics(trades=[], daily_returns=[0.02, 0.03, 0.01, 0.04])
        assert res_positive["net_sortino"] == 0.0

    def test_polymorphic_signatures(self):
        """Support positional conventions: (trades, daily_returns), (trades, equity_curve), (gross_returns, trades)."""
        fc = FrictionConfig()
        trades = [{"action": "buy"}, {"action": "sell"}]
        returns = [0.01, -0.005, 0.02, 0.015]
        equity = [1.0, 1.01, 1.005, 1.025, 1.04]

        # Pattern 1: (trades, returns, friction)
        r1 = calculate_net_performance_metrics(trades, returns, fc)
        # Pattern 2: (trades, equity, friction)
        r2 = calculate_net_performance_metrics(trades, equity, fc)
        # Pattern 3: (gross_returns, trades, friction)
        r3 = calculate_net_performance_metrics(returns, trades, fc)

        assert r1["trade_count"] == 2
        assert r2["trade_count"] == 2
        assert r3["trade_count"] == 2
        assert pytest.approx(r1["net_return"], abs=1e-3) == r3["net_return"]

    def test_calculate_cbs_and_coordination_cost(self):
        """Calculate realized CBS, token cost, latency, and bypass rates."""
        # Empty input
        assert calculate_cbs_and_coordination_cost([])["total_decisions"] == 0.0

        records = [
            {"cbs_bps": 8.5, "tokens": 1200, "latency_ms": 450, "route": "fast_path"},
            {"cbs_bps": 22.0, "tokens": 4500, "latency_ms": 1850, "route": "multi_round_debate"},
            {"cbs_bps": 12.0, "tokens": 1100, "latency_ms": 400, "route": "fast_path"},
        ]
        metrics = calculate_cbs_and_coordination_cost(records)
        assert pytest.approx(metrics["realized_cbs_bps"], abs=1e-2) == (8.5 + 22.0 + 12.0) / 3.0
        assert pytest.approx(metrics["tokens_per_decision"], abs=1e-2) == (1200 + 4500 + 1100) / 3.0
        assert pytest.approx(metrics["fast_path_bypass_rate"], abs=1e-2) == 2.0 / 3.0
        assert pytest.approx(metrics["debate_trigger_rate"], abs=1e-2) == 1.0 / 3.0

    def test_calculate_multi_regime_breakdown(self):
        """Partition returns and compute Sharpe, Sortino, Calmar across bull, bear, sideways."""
        daily_returns = [0.01, 0.02, 0.015, -0.01, -0.02, -0.015, 0.001, -0.001, 0.002]
        regimes = ["bull", "bull", "bull", "bear", "bear", "bear", "sideways", "sideways", "sideways"]

        breakdown = calculate_multi_regime_breakdown(daily_returns, regimes)
        assert "bull" in breakdown
        assert "bear" in breakdown
        assert "sideways" in breakdown

        assert breakdown["bull"]["count"] == 3.0
        assert breakdown["bear"]["count"] == 3.0
        assert breakdown["sideways"]["count"] == 3.0

        # Bull returns should be positive, Bear negative
        assert breakdown["bull"]["net_return"] > 0
        assert breakdown["bear"]["net_return"] < 0


# ==============================================================================
# Suite 8: RiskSelfDebateV2 Execution & State Fast-Path Hardening
# ==============================================================================

class TestTier5RiskSelfDebateHardening:
    def test_parse_self_debate_response_strict_and_loose(self):
        """Parse structured tri-perspective opinions."""
        strict_response = (
            "[Highly resilient scenario perspective]\nHigh resilience arguments.\n"
            "[defensive situational view]\nDefensive arguments.\n"
            "[base case view]\nBaseline arguments."
        )
        risky, safe, neutral = parse_self_debate_response(strict_response)
        assert risky == "High resilience arguments."
        assert safe == "Defensive arguments."
        assert neutral == "Baseline arguments."

        # Degraded unstructured response should duplicate full text into all three fields
        unstructured = "General market observation without specific tags."
        u_risky, u_safe, u_neutral = parse_self_debate_response(unstructured)
        assert u_risky == unstructured
        assert u_safe == unstructured
        assert u_neutral == unstructured

    def test_execute_populates_investment_plan_and_debate_states(self):
        """Executing RiskSelfDebateV2 on fast-path initializes debate states and investment plan."""
        agent = RiskSelfDebateV2()
        # Mock LLM to return valid 3-perspective response
        mock_response = MagicMock()
        mock_response.content = (
            "[Highly resilient scenario perspective]\nCatalyst upside.\n"
            "[defensive situational view]\nDownside risks.\n"
            "[base case view]\nConsensus balance."
        )
        agent._llm = MagicMock()
        agent._get_prompt_from_template = MagicMock(return_value="Mock Prompt")
        agent._invoke_llm_with_trace = MagicMock(return_value=mock_response)

        state = {
            "ticker": "600519",
            "analysis_date": "2024-06-01",
            "analyst_posteriors": {
                "market_analyst_v2": {"p_optimistic": 0.6, "p_neutral": 0.3, "p_cautious": 0.1, "expected_move_bps": 50.0},
            },
        }
        res = agent.execute(state)
        assert res["risky_opinion"] == "Catalyst upside."
        assert res["safe_opinion"] == "Downside risks."
        assert res["neutral_opinion"] == "Consensus balance."

        # Check risk_debate_state
        rds = res["risk_debate_state"]
        assert rds["count"] == 3
        assert rds["latest_speaker"] == "SelfDebate"

        # Check investment_plan & investment_debate_state fallback population
        assert "Fast-Path Tripartite Synthesis" in res["investment_plan"]
        assert res["investment_debate_state"]["count"] == 0
        assert "bypassed by CBS gating" in res["investment_debate_state"]["history"]


# ==============================================================================
# Suite 9: Deep Stress, Convergence & Cross-Milestone Integration Hardening
# ==============================================================================

class TestTier5DeepStressAndConvergence:
    def test_analyst_parsing_large_input_resilience(self):
        """Ensure no catastrophic backtracking or memory crash on 50KB input text."""
        agent = ConcreteAnalystAgent(config=None)
        filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 800  # ~45KB
        large_text = (
            f"# Massive Market Overview\n{filler}\n"
            f"```json:signal\n"
            f'{{\n  "p_optimistic": 0.65,\n  "p_neutral": 0.25,\n  "p_cautious": 0.10,\n'
            f'  "expected_move_bps": 75.0,\n  "confidence": 0.90,\n  "market_regime": "bull"\n}}\n'
            f"```\n"
            f"Conclusion summary follows."
        )
        res = agent._parse_response(large_text)
        assert res["success"] is True
        assert res["market_regime"] == "bull"
        assert res["p_optimistic"] == 0.65
        assert "Massive Market Overview" in res["content"]

    def test_analyst_parsing_scientific_notation(self):
        """Parse probabilities specified in scientific notation."""
        agent = ConcreteAnalystAgent(config=None)
        json_sci = (
            '```json\n'
            '{"p_optimistic": 1e-3, "p_neutral": 0.099, "p_cautious": 0.90, "expected_move_bps": -150.0}\n'
            '```'
        )
        res = agent._parse_response(json_sci)
        assert res["success"] is True
        assert res["p_cautious"] >= 0.85
        assert pytest.approx(sum([res["p_optimistic"], res["p_neutral"], res["p_cautious"]]), abs=1e-4) == 1.0

    def test_conditional_logic_seven_analysts_consensus_vs_polarized(self):
        """7 V2 Analysts: Complete consensus (JSD=0.0) vs Highly polarized split (JSD > 0.6)."""
        aids = [
            "index_analyst_v2", "sector_analyst_v2", "market_analyst_v2",
            "fundamentals_analyst_v2", "news_analyst_v2", "social_analyst_v2",
            "chip_distribution_analyst_v2",
        ]
        # 1. 100% consensus across all 7 analysts
        consensus_posteriors = {
            aid: {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 100.0}
            for aid in aids
        }
        jsd_consensus = calculate_base2_jsd(consensus_posteriors)
        assert jsd_consensus == 0.0
        route_consensus = calculate_cbs_routing(consensus_posteriors, estimated_spread_bps=15.0)
        assert route_consensus["route"] == "fast_path"

        # 2. Polarized split: 4 Bullish vs 3 Bearish analysts
        polarized_posteriors = {}
        for i, aid in enumerate(aids):
            if i < 4:
                polarized_posteriors[aid] = {
                    "p_optimistic": 0.95, "p_neutral": 0.03, "p_cautious": 0.02, "expected_move_bps": 150.0
                }
            else:
                polarized_posteriors[aid] = {
                    "p_optimistic": 0.02, "p_neutral": 0.03, "p_cautious": 0.95, "expected_move_bps": -150.0
                }
        jsd_polarized = calculate_base2_jsd(polarized_posteriors)
        assert jsd_polarized > 0.60
        route_polarized = calculate_cbs_routing(polarized_posteriors, estimated_spread_bps=15.0, max_debate_rounds=3)
        assert route_polarized["route"] == "multi_round_debate"
        assert route_polarized["dynamic_debate_rounds"] >= 2

    def test_weight_calculator_20_period_convergence(self):
        """Over 20 periods, accurate analyst weight converges to ~1.0, failing analyst decays to ~0.0."""
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=["good_analyst", "bad_analyst"], learning_rate=0.3)
        posteriors = {
            "good_analyst": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05},  # loss ~ 0.02
            "bad_analyst": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90},   # loss ~ 1.70
        }
        # Market moves up consistently
        for _ in range(20):
            w = calc.update_weights("bull", posteriors, realized_return=0.03)

        assert w["good_analyst"] > 0.99
        assert w["bad_analyst"] < 0.01
        assert pytest.approx(sum(w.values()), abs=1e-5) == 1.0

    def test_weight_calculator_regime_decoupling(self):
        """Updating weights in 'bull' regime leaves 'bear' and 'sideways' weights unchanged."""
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=["a1", "a2"])
        initial_bear = dict(calc.get_weights("bear"))

        posteriors = {
            "a1": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0},
            "a2": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0},
        }
        # Update bull regime 10 times
        for _ in range(10):
            calc.update_weights("bull", posteriors, realized_return=0.05)

        # Bear regime weights must remain strictly equal
        current_bear = calc.get_weights("bear")
        assert current_bear == initial_bear
        assert calc.get_weights("bull")["a1"] > 0.80

    def test_bayesian_log_odds_hold_action_invariance(self):
        """Regardless of posteriors or regime, action='hold' always preserves current_price."""
        posteriors = {
            "a1": {"p_optimistic": 0.99, "p_neutral": 0.01, "p_cautious": 0.0, "expected_move_bps": 500.0},
        }
        for current_price in [10.0, 55.75, 1200.0]:
            target = calculate_bayesian_log_odds_target_price(
                current_price=current_price,
                action="hold",
                regime="bull",
                analyst_posteriors=posteriors,
            )
            assert target == round(current_price, 2)

    def test_bayesian_log_odds_contrarian_balance(self):
        """Bear prior L0 (-0.405) balanced against Bullish analyst posteriors."""
        bull_posteriors = {
            "a1": {"p_optimistic": 0.80, "p_neutral": 0.10, "p_cautious": 0.10, "expected_move_bps": 100.0},
        }
        details = compute_bayesian_log_odds_details(
            current_price=100.0,
            action="buy",
            regime="bear",  # Bear prior log-odds ~ -0.405
            analyst_posteriors=bull_posteriors,
            weights={"a1": 1.0},
        )
        # ell_i = ln(0.8 / 0.1) = ln(8) ~ +2.079
        # L_agg = -0.405 + 2.079 ~ +1.674 > 0 -> P_agg > 0.5
        assert details["l_agg"] > 0.0
        assert details["p_agg"] > 0.5
        assert details["target_price"] > 100.0

    def test_memory_circuit_breaker_boundary_float_epsilon(self):
        """Test exact float epsilons around confidence 0.5."""
        memories = [
            {"id": "m1", "metadata": {"market_regime": "bull"}},
            {"id": "m2", "metadata": {"market_regime": "bear"}},
        ]
        # Just below 0.5 (0.499999) -> bypasses
        bypassed = circuit_breaker_memory_filter(
            memories, current_regime="bull", regime_confidence=0.499999, agent_id="trader_v2"
        )
        assert len(bypassed) == 2

        # Just at/above 0.5 (0.500001) -> filters
        filtered = circuit_breaker_memory_filter(
            memories, current_regime="bull", regime_confidence=0.500001, agent_id="trader_v2"
        )
        assert len(filtered) == 1
        assert filtered[0]["id"] == "m1"

    def test_result_evaluator_deep_drawdown_recovery(self):
        """Verify MDD with peak at 1.0, drop to 0.4 (-60%), partial recovery to 0.8, and second drop to 0.3 (-70%)."""
        equity = [1.0, 0.4, 0.8, 0.3]
        metrics = calculate_net_performance_metrics(trades=[], equity_curve=equity)
        # Maximum drawdown should be from peak 1.0 to trough 0.3 = -70%
        assert pytest.approx(metrics["net_max_drawdown"], abs=1e-4) == -0.70

    def test_result_evaluator_all_negative_returns_sortino(self):
        """When all returns are negative, downside deviation is nonzero and Sortino is negative and finite."""
        neg_returns = [-0.01, -0.02, -0.015, -0.005]
        metrics = calculate_net_performance_metrics(trades=[], daily_returns=neg_returns)
        assert metrics["net_sortino"] < 0.0
        assert not math.isnan(metrics["net_sortino"])
        assert not math.isinf(metrics["net_sortino"])

    def test_counterfactual_credit_unvindicated_neutral(self):
        """When agent is neutral (0.0), but market makes a big move (+5%), agent is not vindicated."""
        q = calculate_counterfactual_attribution(
            agent_stance="neutral", realized_return=0.05, manager_action="buy", agent_confidence=0.8
        )
        assert q["is_vindicated"] is False
        assert q["quadrant"] in ["Q3_Faulty_Followed", "Q4_Faulty_Overridden"]

    def test_cross_milestone_end_to_end_invariance(self):
        """Full cross-milestone integration pipeline from parsing to evaluation."""
        # 1. Parse analyst output
        agent = ConcreteAnalystAgent(config=None)
        raw_output = (
            "Bullish thesis on strong fundamentals.\n"
            "```json:signal\n"
            '{"p_optimistic": 0.80, "p_neutral": 0.15, "p_cautious": 0.05, "expected_move_bps": 120.0, "confidence": 0.85, "market_regime": "bull"}\n'
            "```"
        )
        parsed = agent._parse_response(raw_output)
        posterior = parsed["posterior"]

        # 2. Gate debate with CBS
        state = {
            "analyst_posteriors": {"test_analyst": posterior},
            "estimated_spread_bps": 15.0,
        }
        cl = ConditionalLogic()
        decision = cl.should_trigger_multi_round_debate(state)
        assert decision in ["fast_path", "multi_round_debate"]

        # 3. Compute weights
        calc = RegimeAdaptiveWeightCalculator(analyst_ids=["test_analyst"])
        weights = calc.get_weights("bull")

        # 4. Bayesian pricing
        target_price = calculate_bayesian_log_odds_target_price(
            current_price=100.0,
            action="buy",
            regime="bull",
            analyst_posteriors=state["analyst_posteriors"],
            weights=weights,
            is_china=True,
        )
        assert target_price > 100.0

        # 5. Counterfactual attribution on realized return
        attr = calculate_counterfactual_attribution(
            agent_stance="bull",
            realized_return=0.03,
            manager_action="buy",
            agent_confidence=posterior["confidence"],
        )
        assert attr["quadrant"] == "Q1_Vindicated_Followed"

        # 6. Evaluate net performance
        eval_metrics = calculate_net_performance_metrics(
            trades=[{"action": "buy"}, {"action": "sell"}],
            daily_returns=[0.01, 0.02, 0.015, -0.005],
            friction=FrictionConfig(),
        )
        assert eval_metrics["net_return"] > 0.0
        assert eval_metrics["trade_count"] == 2
