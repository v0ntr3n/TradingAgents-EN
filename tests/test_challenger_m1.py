"""
Empirical Challenger Test Suite for CARE-Agents Milestone M1.

Stress-tests:
1. Base-2 JSD calculation and CBS gating in `tradingagents/graph/conditional_logic.py`
   - Adversarial distributions: all 0s, all 1s, extreme unnormalized, orthogonal vectors,
     identical vectors, single analyst, empty, None, NaN/inf.
   - Property verification: zero crashes, pure base-2 values within [0.0, 1.0], exact boundary
     decisions around JSD=0.12 and CBS=15.0 bps.
2. Signal block parsing in `core/agents/analyst.py`
   - Adversarial inputs: malformed JSON, truncated markdown, negative probabilities,
     percentages, missing fields, embedded code blocks.
   - Property verification: sum(p_i) == 1.0 +- 1e-4 tolerance, clean report string without leaked tags.
"""

import json
import math
import random
from typing import Any, Dict, List
import pytest

from core.agents.analyst import AnalystAgent, DEFAULT_UNINFORMATIVE_POSTERIOR
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_shannon_entropy,
    compute_base2_jsd,
    calculate_base2_jsd,
    calculate_cbs_routing,
    should_trigger_multi_round_debate,
)


class DummyAnalyst(AnalystAgent):
    analyst_type = "dummy"
    output_field = "dummy_report"

    def _build_system_prompt(self, market_type: str = None, context=None, state=None) -> str:
        return "Dummy System Prompt"

    def _build_user_prompt(self, ticker: str, analysis_date: str, tool_data: Dict[str, Any], state: Dict[str, Any]) -> str:
        return "Dummy User Prompt"


# ==============================================================================
# Suite 1: Adversarial JSD Calculation & CBS Gating Stress-Tests
# ==============================================================================
class TestAdversarialJSDAndCBS:
    """Empirical verification and stress testing of JSD calculation and CBS gating."""

    def test_adversarial_distributions_all_zeros(self):
        """All zeros distributions should yield 0.0 JSD without division by zero."""
        # Raw compute_base2_jsd
        jsd = compute_base2_jsd([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        assert jsd == 0.0, f"Expected 0.0, got {jsd}"

        # Dict posteriors API
        posteriors = {
            "a1": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 0.0},
            "a2": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 0.0},
        }
        jsd_dict = calculate_base2_jsd(posteriors)
        assert jsd_dict == 0.0

        routing = calculate_cbs_routing(posteriors, estimated_spread_bps=15.0)
        assert routing["route"] == "fast_path"
        assert routing["jsd"] == 0.0
        assert routing["cbs_bps"] == 0.0

    def test_adversarial_distributions_all_ones(self):
        """All ones distributions normalize to identical uniform distributions and yield 0.0 JSD."""
        jsd = compute_base2_jsd([[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]])
        assert abs(jsd) < 1e-6

        posteriors = {
            f"a{i}": {"p_optimistic": 1.0, "p_neutral": 1.0, "p_cautious": 1.0, "expected_move_bps": 50.0}
            for i in range(5)
        }
        assert calculate_base2_jsd(posteriors) == 0.0
        routing = calculate_cbs_routing(posteriors, estimated_spread_bps=15.0)
        assert routing["route"] == "fast_path"

    def test_adversarial_distributions_extreme_unnormalized(self):
        """Extremely large or small values must normalize safely without overflow or underflow."""
        # Very large scale
        jsd_large = compute_base2_jsd([[1e15, 2e15, 3e15], [1e15, 2e15, 3e15]])
        assert abs(jsd_large) < 1e-6

        # Very small scale
        jsd_small = compute_base2_jsd([[1e-15, 2e-15, 3e-15], [1e-15, 2e-15, 3e-15]])
        assert abs(jsd_small) < 1e-6

        # Mixed scales across analysts
        jsd_mixed = compute_base2_jsd([[1e12, 1e12, 1e12], [1e-12, 1e-12, 1e-12]])
        assert abs(jsd_mixed) < 1e-6

        # Extreme divergence: one analyst sees extreme bullish, one sees extreme bearish
        posteriors = {
            "a1": {"p_optimistic": 1e10, "p_neutral": 1.0, "p_cautious": 1.0, "expected_move_bps": 100.0},
            "a2": {"p_optimistic": 1.0, "p_neutral": 1.0, "p_cautious": 1e10, "expected_move_bps": -100.0},
        }
        jsd_extreme = calculate_base2_jsd(posteriors)
        assert 0.0 <= jsd_extreme <= 1.0
        assert jsd_extreme > 0.9  # Nearly orthogonal

    def test_adversarial_distributions_orthogonal(self):
        """Orthogonal probability vectors must yield maximum divergence bounded in [0.0, 1.0]."""
        # 2 orthogonal distributions: [1, 0, 0] and [0, 1, 0]
        # In base-2, JSD of 2 completely disjoint distributions is exactly 1.0.
        jsd_2 = compute_base2_jsd([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        assert abs(jsd_2 - 1.0) < 1e-6

        # 3 orthogonal distributions: [1, 0, 0], [0, 1, 0], [0, 0, 1]
        jsd_3 = compute_base2_jsd([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        # Base-2 JSD is capped at 1.0 by definition in implementation:
        assert 0.0 <= jsd_3 <= 1.0
        assert jsd_3 == 1.0

        # 7 analysts split into opposing camps
        posteriors = {
            "a1": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 100.0},
            "a2": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 100.0},
            "a3": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 100.0},
            "a4": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": -100.0},
            "a5": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": -100.0},
            "a6": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": -100.0},
            "a7": {"p_optimistic": 0.0, "p_neutral": 0.0, "p_cautious": 1.0, "expected_move_bps": -100.0},
        }
        jsd_split = calculate_base2_jsd(posteriors)
        assert 0.0 <= jsd_split <= 1.0
        assert jsd_split > 0.95

    def test_adversarial_distributions_identical(self):
        """Any identical distributions must evaluate to exact 0.0 JSD."""
        for _ in range(50):
            p1 = random.random()
            p2 = random.random()
            p3 = random.random()
            vec = [p1, p2, p3]
            jsd = compute_base2_jsd([vec, vec, vec])
            assert abs(jsd) < 1e-6, f"Expected 0.0, got {jsd} for identical vec {vec}"

    def test_adversarial_distributions_single_analyst_and_empty(self):
        """A single analyst or empty posteriors cannot diverge, returning 0.0 JSD and fast-path."""
        assert compute_base2_jsd([[0.8, 0.1, 0.1]]) == 0.0
        assert compute_base2_jsd([]) == 0.0

        posteriors_single = {
            "market_analyst_v2": {
                "p_optimistic": 0.8,
                "p_neutral": 0.1,
                "p_cautious": 0.1,
                "expected_move_bps": 80.0,
                "confidence": 0.9,
            }
        }
        assert calculate_base2_jsd(posteriors_single) == 0.0
        routing_single = calculate_cbs_routing(posteriors_single, estimated_spread_bps=15.0)
        assert routing_single["route"] == "fast_path"
        assert routing_single["jsd"] == 0.0

        # Empty dict
        assert calculate_base2_jsd({}) == 0.0
        routing_empty = calculate_cbs_routing({}, estimated_spread_bps=15.0)
        assert routing_empty["route"] == "fast_path"

        # None input
        assert calculate_base2_jsd(None) == 0.0

    def test_adversarial_distributions_nan_inf_stability(self):
        """NaN and inf values in posteriors must be handled safely without unhandled exceptions."""
        posteriors = {
            "a1": {"p_optimistic": float("nan"), "p_neutral": float("nan"), "p_cautious": float("nan")},
            "a2": {"p_optimistic": float("inf"), "p_neutral": 0.0, "p_cautious": 0.0},
            "a3": {"p_optimistic": 0.5, "p_neutral": 0.3, "p_cautious": 0.2},
        }
        jsd = calculate_base2_jsd(posteriors)
        assert not math.isnan(jsd)
        assert 0.0 <= jsd <= 1.0

        routing = calculate_cbs_routing(posteriors, estimated_spread_bps=15.0)
        assert routing["route"] in ("fast_path", "multi_round_debate")
        assert not math.isnan(routing["cbs_bps"])

    def test_large_scale_random_simplex_stress_test(self):
        """10,000 randomized probability distributions must strictly satisfy JSD in [0.0, 1.0]."""
        for _ in range(10000):
            n_analysts = random.choice([2, 3, 4, 5, 6, 7])
            dists = []
            for _ in range(n_analysts):
                raw = [random.expovariate(1.0) for _ in range(3)]
                s = sum(raw)
                dists.append([x / s for x in raw])

            jsd = compute_base2_jsd(dists)
            assert 0.0 <= jsd <= 1.0, f"JSD out of bounds [0, 1]: {jsd}"

    def test_exact_boundary_decisions_jsd(self):
        """Exact boundary verification around JSD = 0.12."""
        # Binary search for two probability distributions [p, 1-p, 0] and [1-p, p, 0]
        # such that JSD is just below 0.12 vs just above 0.12
        p_boundary = 0.701053  # yields JSD ~ 0.120000

        # Sub-test 1: JSD just below 0.12 (e.g., 0.1139) with huge expected move (500 bps)
        # Even though CBS_bps would be ~28.5 bps (> 15.0 bps spread), JSD < 0.12 MUST bypass to fast_path.
        p_below = p_boundary - 0.005
        posts_below = {
            "a1": {"p_optimistic": p_below, "p_neutral": 1 - p_below, "p_cautious": 0.0, "expected_move_bps": 500.0, "confidence": 1.0},
            "a2": {"p_optimistic": 1 - p_below, "p_neutral": p_below, "p_cautious": 0.0, "expected_move_bps": 500.0, "confidence": 1.0},
        }
        r_below = calculate_cbs_routing(posts_below, estimated_spread_bps=15.0)
        assert r_below["jsd"] < 0.12, f"Expected JSD < 0.12, got {r_below['jsd']}"
        assert r_below["cbs_bps"] > 15.0, f"Expected CBS > 15, got {r_below['cbs_bps']}"
        assert r_below["route"] == "fast_path", "JSD < 0.12 must trigger fast_path regardless of CBS"
        assert r_below["dynamic_debate_rounds"] == 0

        # Sub-test 2: JSD just above 0.12 (e.g., 0.1262) with huge expected move (500 bps)
        # Both JSD >= 0.12 AND CBS > 15.0 hold -> must route to multi_round_debate.
        p_above = p_boundary + 0.005
        posts_above = {
            "a1": {"p_optimistic": p_above, "p_neutral": 1 - p_above, "p_cautious": 0.0, "expected_move_bps": 500.0, "confidence": 1.0},
            "a2": {"p_optimistic": 1 - p_above, "p_neutral": p_above, "p_cautious": 0.0, "expected_move_bps": 500.0, "confidence": 1.0},
        }
        r_above = calculate_cbs_routing(posts_above, estimated_spread_bps=15.0)
        assert r_above["jsd"] >= 0.12, f"Expected JSD >= 0.12, got {r_above['jsd']}"
        assert r_above["cbs_bps"] > 15.0, f"Expected CBS > 15, got {r_above['cbs_bps']}"
        assert r_above["route"] == "multi_round_debate"
        assert r_above["dynamic_debate_rounds"] >= 1

    def test_exact_boundary_decisions_cbs(self):
        """Exact boundary verification around CBS_bps = 15.0 bps when JSD >= 0.12."""
        p_above = 0.706053  # JSD is ~0.1262 > 0.12

        # 1. CBS just below 15.0 bps (move = 235 bps -> CBS ~ 14.83 bps)
        posts_below_cbs = {
            "a1": {"p_optimistic": p_above, "p_neutral": 1 - p_above, "p_cautious": 0.0, "expected_move_bps": 235.0, "confidence": 1.0},
            "a2": {"p_optimistic": 1 - p_above, "p_neutral": p_above, "p_cautious": 0.0, "expected_move_bps": 235.0, "confidence": 1.0},
        }
        r_below = calculate_cbs_routing(posts_below_cbs, estimated_spread_bps=15.0)
        assert r_below["jsd"] >= 0.12
        assert r_below["cbs_bps"] < 15.0
        assert r_below["route"] == "fast_path", "CBS <= estimated_spread_bps must trigger fast_path"

        # 2. CBS exactly equal to 15.0 bps
        r_calc = calculate_cbs_routing(posts_below_cbs)
        exact_move = 30.0 / r_calc["jsd"]
        posts_exact_cbs = {
            "a1": {"p_optimistic": p_above, "p_neutral": 1 - p_above, "p_cautious": 0.0, "expected_move_bps": exact_move, "confidence": 1.0},
            "a2": {"p_optimistic": 1 - p_above, "p_neutral": p_above, "p_cautious": 0.0, "expected_move_bps": exact_move, "confidence": 1.0},
        }
        r_exact = calculate_cbs_routing(posts_exact_cbs, estimated_spread_bps=15.0)
        assert abs(r_exact["cbs_bps"] - 15.0) < 1e-9
        assert r_exact["route"] == "fast_path", "CBS <= estimated_spread_bps boundary condition includes equality"

        # 3. CBS just above 15.0 bps (move = 240 bps -> CBS ~ 15.15 bps)
        posts_above_cbs = {
            "a1": {"p_optimistic": p_above, "p_neutral": 1 - p_above, "p_cautious": 0.0, "expected_move_bps": 240.0, "confidence": 1.0},
            "a2": {"p_optimistic": 1 - p_above, "p_neutral": p_above, "p_cautious": 0.0, "expected_move_bps": 240.0, "confidence": 1.0},
        }
        r_above = calculate_cbs_routing(posts_above_cbs, estimated_spread_bps=15.0)
        assert r_above["jsd"] >= 0.12
        assert r_above["cbs_bps"] > 15.0
        assert r_above["route"] == "multi_round_debate"

    def test_dynamic_debate_rounds_scaling(self):
        """Dynamic rounds scale linearly from 1 to max_debate_rounds as JSD progresses from 0.12 to 1.0."""
        # At boundary JSD = 0.12 -> dynamic rounds should be 1
        # At max JSD = 1.0 -> dynamic rounds should be max_debate_rounds (e.g. 5)
        max_rounds = 5
        # Low divergence near 0.12
        posts_low = {
            "a1": {"p_optimistic": 0.706, "p_neutral": 0.294, "p_cautious": 0.0, "expected_move_bps": 300.0, "confidence": 1.0},
            "a2": {"p_optimistic": 0.294, "p_neutral": 0.706, "p_cautious": 0.0, "expected_move_bps": 300.0, "confidence": 1.0},
        }
        r_low = calculate_cbs_routing(posts_low, estimated_spread_bps=15.0, max_debate_rounds=max_rounds)
        assert r_low["dynamic_debate_rounds"] == 1

        # Max divergence JSD = 1.0
        posts_max = {
            "a1": {"p_optimistic": 1.0, "p_neutral": 0.0, "p_cautious": 0.0, "expected_move_bps": 300.0, "confidence": 1.0},
            "a2": {"p_optimistic": 0.0, "p_neutral": 1.0, "p_cautious": 0.0, "expected_move_bps": 300.0, "confidence": 1.0},
        }
        r_max = calculate_cbs_routing(posts_max, estimated_spread_bps=15.0, max_debate_rounds=max_rounds)
        assert r_max["dynamic_debate_rounds"] == max_rounds

    def test_state_injection_contract(self):
        """should_trigger_multi_round_debate injects metrics into state dictionary."""
        logic = ConditionalLogic(max_debate_rounds=3)
        state = {
            "analyst_posteriors": {
                "a1": {"p_optimistic": 0.9, "p_neutral": 0.1, "p_cautious": 0.0, "expected_move_bps": 120.0, "confidence": 0.8},
                "a2": {"p_optimistic": 0.0, "p_neutral": 0.1, "p_cautious": 0.9, "expected_move_bps": -120.0, "confidence": 0.8},
            },
            "estimated_spread_bps": 15.0,
        }
        decision = logic.should_trigger_multi_round_debate(state)
        assert decision == "multi_round_debate"
        assert "debate_jsd" in state
        assert "cbs_bps" in state
        assert "dynamic_debate_rounds" in state
        assert state["debate_jsd"] > 0.12
        assert state["cbs_bps"] > 15.0


# ==============================================================================
# Suite 2: Adversarial Signal Block Parsing Stress-Tests
# ==============================================================================
class TestAdversarialSignalBlockParsing:
    """Empirical verification and stress testing of AnalystAgent signal block parsing."""

    @pytest.fixture
    def analyst(self):
        return DummyAnalyst()

    def test_probability_normalization_sum_tolerance_stress(self, analyst):
        """1,000 random unnormalized probability triples must always satisfy sum(p) == 1.0 +- 1e-4."""
        for _ in range(1000):
            p1 = random.uniform(0.001, 1000.0)
            p2 = random.uniform(0.001, 1000.0)
            p3 = random.uniform(0.001, 1000.0)

            normalized = analyst._normalize_posterior({
                "p_optimistic": p1,
                "p_neutral": p2,
                "p_cautious": p3,
            })
            p_sum = normalized["p_optimistic"] + normalized["p_neutral"] + normalized["p_cautious"]
            assert abs(p_sum - 1.0) <= 1e-4, f"Failed normalization sum tolerance: {p_sum} (from {[p1, p2, p3]})"
            assert normalized["p_optimistic"] >= 0.0
            assert normalized["p_neutral"] >= 0.0
            assert normalized["p_cautious"] >= 0.0

    def test_negative_and_out_of_bounds_probabilities(self, analyst):
        """Negative probabilities must be clamped to 0.0 and re-normalized."""
        raw = {
            "p_optimistic": -0.5,
            "p_neutral": 0.6,
            "p_cautious": 0.4,
        }
        res = analyst._normalize_posterior(raw)
        assert res["p_optimistic"] == 0.0
        assert res["p_neutral"] == 0.6
        assert res["p_cautious"] == 0.4
        assert abs(sum([res["p_optimistic"], res["p_neutral"], res["p_cautious"]]) - 1.0) <= 1e-4

        # All negative
        raw_all_neg = {
            "p_optimistic": -10.0,
            "p_neutral": -20.0,
            "p_cautious": -30.0,
        }
        res_all_neg = analyst._normalize_posterior(raw_all_neg)
        assert abs(sum([res_all_neg["p_optimistic"], res_all_neg["p_neutral"], res_all_neg["p_cautious"]]) - 1.0) <= 1e-4

    def test_percentage_format_variations(self, analyst):
        """Percentages formatted as strings with '%' or integers [70, 20, 10] must be scaled to [0, 1]."""
        # String percentages
        raw_str = {
            "p_optimistic": "65%",
            "p_neutral": "25%",
            "p_cautious": "10%",
        }
        res_str = analyst._normalize_posterior(raw_str)
        assert res_str["p_optimistic"] == 0.65
        assert res_str["p_neutral"] == 0.25
        assert res_str["p_cautious"] == 0.10
        assert abs(sum([res_str["p_optimistic"], res_str["p_neutral"], res_str["p_cautious"]]) - 1.0) <= 1e-4

        # Decimal percentages in strings
        raw_dec = {
            "p_optimistic": "33.33%",
            "p_neutral": "33.34%",
            "p_cautious": "33.33%",
        }
        res_dec = analyst._normalize_posterior(raw_dec)
        assert abs(sum([res_dec["p_optimistic"], res_dec["p_neutral"], res_dec["p_cautious"]]) - 1.0) <= 1e-4

        # Integer scale (70, 20, 10)
        raw_int = {
            "p_optimistic": 70,
            "p_neutral": 20,
            "p_cautious": 10,
        }
        res_int = analyst._normalize_posterior(raw_int)
        assert res_int["p_optimistic"] == 0.7
        assert res_int["p_neutral"] == 0.2
        assert res_int["p_cautious"] == 0.1

    def test_missing_fields_and_schema_enforcement(self, analyst):
        """Missing posterior fields must be safely populated with sensible defaults."""
        raw_sparse = {
            "p_optimistic": 0.8,
            # p_neutral, p_cautious missing
            # expected_move_bps, confidence, market_regime missing
        }
        res = analyst._normalize_posterior(raw_sparse)
        for key in ["p_optimistic", "p_neutral", "p_cautious", "expected_move_bps", "confidence", "market_regime"]:
            assert key in res, f"Missing expected key: {key}"
        assert abs(sum([res["p_optimistic"], res["p_neutral"], res["p_cautious"]]) - 1.0) <= 1e-4
        assert 0.0 <= res["confidence"] <= 1.0
        assert res["market_regime"] in ("bull", "bear", "sideways")

    def test_malformed_json_repairs(self, analyst):
        """_parse_response should successfully repair single quotes, trailing commas, and Python constants."""
        # Single quotes and trailing comma
        response_single_quotes = """
# Market Review
Fundamentals are strong.

```json:signal
{
  'p_optimistic': 0.6,
  'p_neutral': 0.3,
  'p_cautious': 0.1,
  'expected_move_bps': 45.0,
  'confidence': 0.75,
  'market_regime': 'bull',
}
```
"""
        parsed = analyst._parse_response(response_single_quotes)
        assert parsed["success"] is True
        assert parsed["posterior"]["p_optimistic"] == 0.6
        assert parsed["posterior"]["market_regime"] == "bull"
        assert "json:signal" not in parsed["report"]
        assert "p_optimistic" not in parsed["report"]

        # Python constants True / False / None
        response_constants = """
Analysis:
```json:signal
{
  "p_optimistic": 0.5,
  "p_neutral": 0.3,
  "p_cautious": 0.2,
  "expected_move_bps": 20.0,
  "confidence": 0.6,
  "market_regime": "bull",
  "active": True,
  "meta": None
}
```
"""
        parsed_c = analyst._parse_response(response_constants)
        assert parsed_c["posterior"]["p_optimistic"] == 0.5

    def test_clean_report_extraction_without_leaked_tags(self, analyst):
        """Clean markdown report string returned must have all delimiters and signal blocks stripped."""
        text_before = "# Section 1: Macro Environment\nGrowth outlook remains positive."
        text_after = "## Section 2: Technical Levels\nResistance at 3200, support at 3100."

        signal_payload = """
```json:signal
{
  "p_optimistic": 0.65,
  "p_neutral": 0.25,
  "p_cautious": 0.10,
  "expected_move_bps": 35.0,
  "confidence": 0.85,
  "market_regime": "bull"
}
```
"""
        full_text = f"{text_before}\n{signal_payload}\n{text_after}"
        parsed = analyst._parse_response(full_text)
        report = parsed["report"]

        # 1. Text before and after must be preserved
        assert text_before in report
        assert text_after in report

        # 2. No leaked delimiter tags or JSON payload keys
        assert "json:signal" not in report
        assert "p_optimistic" not in report
        assert "p_cautious" not in report
        assert "expected_move_bps" not in report

    def test_embedded_non_signal_code_blocks_preserved(self, analyst):
        """Markdown reports containing non-signal code fences (e.g. Python or SQL snippets) must preserve them."""
        full_text = """
# Data Processing Pipeline
Below is the feature generation query:
```sql
SELECT ticker, close, volume FROM quotes WHERE date >= '2026-01-01';
```

And here is the regression snippet:
```python
model = Ridge(alpha=1.0)
model.fit(X_train, y_train)
```

Summary conclusion is positive.

```json:signal
{
  "p_optimistic": 0.6,
  "p_neutral": 0.3,
  "p_cautious": 0.1,
  "expected_move_bps": 30.0,
  "confidence": 0.8,
  "market_regime": "bull"
}
```
"""
        parsed = analyst._parse_response(full_text)
        report = parsed["report"]

        # Ensure SQL and Python code fences remain intact in clean report
        assert "SELECT ticker, close, volume" in report
        assert "```sql" in report
        assert "model = Ridge(alpha=1.0)" in report
        assert "```python" in report

        # Signal block must be removed
        assert "json:signal" not in report
        assert "p_optimistic" not in report
        assert abs(sum([parsed["posterior"]["p_optimistic"], parsed["posterior"]["p_neutral"], parsed["posterior"]["p_cautious"]]) - 1.0) <= 1e-4

    def test_truncated_json_payload_graceful_fallback(self, analyst):
        """When JSON payload is severely truncated mid-stream, fallback gracefully without throwing exception."""
        truncated_text = """
# Partial Analysis
Market broke out of range. 强烈看多，买入信号明确。

```json:signal
{
  "p_optimistic": 0.7,
  "p_neutral":
"""
        parsed = analyst._parse_response(truncated_text)
        assert parsed["success"] is True
        # Heuristic fallback should detect Chinese bullish keywords "强烈看多", "买入"
        posterior = parsed["posterior"]
        assert posterior["market_regime"] in ("bull", "sideways")
        assert abs(sum([posterior["p_optimistic"], posterior["p_neutral"], posterior["p_cautious"]]) - 1.0) <= 1e-4
