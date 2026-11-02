import tests  # registers offline stubs
import math
from core.agents.analyst import extract_structured_posterior
from tradingagents.graph.conditional_logic import (
    ConditionalLogic,
    compute_jensen_shannon_divergence,
    compute_cbs_bps,
)


def test_extract_structured_posterior_from_json_and_text():
    raw_report = """
    ## Market Technical Analysis
    Trend is strong with rising volume.
    {"p_optimistic": 0.70, "p_neutral": 0.20, "p_cautious": 0.10, "expected_move_bps": 120.0, "confidence": 0.82, "market_regime": "bull"}
    """
    post = extract_structured_posterior(raw_report)
    assert math.isclose(post["p_optimistic"] + post["p_neutral"] + post["p_cautious"], 1.0, rel_tol=1e-4)
    assert post["p_optimistic"] == 0.70
    assert post["market_regime"] == "bull"
    assert post["expected_move_bps"] == 120.0

    fallback_post = extract_structured_posterior("The stock shows strong growth and positive bullish opportunity.")
    assert math.isclose(
        fallback_post["p_optimistic"] + fallback_post["p_neutral"] + fallback_post["p_cautious"],
        1.0,
        rel_tol=1e-4,
    )
    assert fallback_post["p_optimistic"] > fallback_post["p_cautious"]


def test_cbs_debate_gating_fast_path_vs_multi_round():
    logic = ConditionalLogic(max_debate_rounds=3)

    # Case 1: High consensus among analysts -> low JSD -> fast path
    consensus_state = {
        "estimated_spread_bps": 15.0,
        "analyst_posteriors": {
            "market_analyst_v2": {"p_optimistic": 0.75, "p_neutral": 0.15, "p_cautious": 0.10, "expected_move_bps": 80.0},
            "fundamentals_analyst_v2": {"p_optimistic": 0.72, "p_neutral": 0.18, "p_cautious": 0.10, "expected_move_bps": 85.0},
            "news_analyst_v2": {"p_optimistic": 0.74, "p_neutral": 0.16, "p_cautious": 0.10, "expected_move_bps": 75.0},
        },
    }
    decision_low = logic.should_gate_debate(consensus_state)
    assert decision_low["jsd"] < 0.12
    assert decision_low["risk_self_debate"] is True
    assert decision_low["target_debate_rounds"] == 0
    assert logic.should_trigger_multi_round_debate(consensus_state) == "Research Manager"

    # Case 2: Strong clash between technical/chip and fundamentals with large expected move -> multi-round debate
    clash_state = {
        "estimated_spread_bps": 12.0,
        "analyst_posteriors": {
            "market_analyst_v2": {"p_optimistic": 0.90, "p_neutral": 0.05, "p_cautious": 0.05, "expected_move_bps": 180.0},
            "fundamentals_analyst_v2": {"p_optimistic": 0.05, "p_neutral": 0.05, "p_cautious": 0.90, "expected_move_bps": 180.0},
            "chip_distribution_analyst_v2": {"p_optimistic": 0.05, "p_neutral": 0.90, "p_cautious": 0.05, "expected_move_bps": 160.0},
        },
    }
    decision_high = logic.should_gate_debate(clash_state)
    assert decision_high["jsd"] >= 0.40
    assert decision_high["cbs_bps"] > 12.0
    assert decision_high["risk_self_debate"] is False
    assert decision_high["target_debate_rounds"] >= 2
    assert logic.should_trigger_multi_round_debate(clash_state) == "Bull Researcher"
