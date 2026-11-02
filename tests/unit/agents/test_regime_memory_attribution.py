import tests  # registers offline stubs
from core.memory.memory_manager import Mem0AgentMemory
from tradingagents.graph.reflection import compute_counterfactual_attribution


def test_regime_filtering_and_circuit_breaker():
    raw_memories = [
        {"content": "Bull breakout lesson", "similarity": 0.60, "metadata": {"market_regime": "bull"}},
        {"content": "Bear capitulation lesson", "similarity": 0.85, "metadata": {"market_regime": "bear"}},
        {"content": "Sideways range lesson", "similarity": 0.65, "metadata": {"market_regime": "sideways"}},
    ]

    # In bull regime: bear memory is excluded; bull memory gets 1.5x boost (0.60 * 1.5 = 0.90 > 0.65)
    bull_filtered = Mem0AgentMemory.filter_and_rerank_by_regime(
        raw_memories, current_regime="bull", drawdown_circuit_breaker=False
    )
    assert len(bull_filtered) == 2
    assert bull_filtered[0]["content"] == "Bull breakout lesson"
    assert bull_filtered[0]["similarity"] == 0.90

    # Circuit breaker active: returns empty list
    cb_filtered = Mem0AgentMemory.filter_and_rerank_by_regime(
        raw_memories, current_regime="bull", drawdown_circuit_breaker=True
    )
    assert cb_filtered == []


def test_counterfactual_credit_assignment():
    state = {
        "final_action": "buy",
        "analyst_posteriors": {
            "market_analyst_v2": {"p_optimistic": 0.80, "p_neutral": 0.10, "p_cautious": 0.10},
            "fundamentals_analyst_v2": {"p_optimistic": 0.10, "p_neutral": 0.15, "p_cautious": 0.75},
        },
    }
    # Realized return is -2.8% (system bought, but stock dropped -> fundamentals & bear warned accurately!)
    attrib = compute_counterfactual_attribution(state, realized_return_pct=-2.8)
    assert attrib["market_analyst_v2"]["attribution_role"] == "false_driver"
    assert attrib["fundamentals_analyst_v2"]["attribution_role"] == "overridden_correct"
    assert attrib["BEAR"]["attribution_role"] == "correct_dissent_ignored"
    assert attrib["BULL"]["attribution_role"] == "false_driver"
