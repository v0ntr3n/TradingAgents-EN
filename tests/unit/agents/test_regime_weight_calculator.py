import tests  # registers offline stubs
import math
from core.agents.utils.weight_calculator import (
    calculate_report_weights,
    RegimeMultiplicativeWeightManager,
)
from tradingagents.graph.signal_processing import SignalProcessor


def test_brier_loss_and_multiplicative_weight_updates():
    mgr = RegimeMultiplicativeWeightManager(
        analyst_ids=["market_analyst_v2", "fundamentals_analyst_v2", "news_analyst_v2"]
    )
    posteriors = {
        "market_analyst_v2": {"p_optimistic": 0.85, "p_neutral": 0.10, "p_cautious": 0.05, "expected_move_bps": 110.0},
        "fundamentals_analyst_v2": {"p_optimistic": 0.10, "p_neutral": 0.20, "p_cautious": 0.70, "expected_move_bps": 90.0},
        "news_analyst_v2": {"p_optimistic": 0.33, "p_neutral": 0.34, "p_cautious": 0.33, "expected_move_bps": 60.0},
    }

    # Realized return is +3.2% in bull regime -> market_analyst_v2 was accurate, fundamentals was wrong
    updated = mgr.update_weights("bull", posteriors, realized_return_pct=3.2, eta=0.5)
    assert math.isclose(sum(updated.values()), 1.0, rel_tol=1e-5)
    assert updated["market_analyst_v2"] > updated["news_analyst_v2"] > updated["fundamentals_analyst_v2"]

    # Bear regime weights remain untouched and independent
    bear_w = mgr.get_regime_weights("bear")
    assert math.isclose(bear_w["market_analyst_v2"], 1.0 / 3.0, rel_tol=1e-4)

    # Logarithmic opinion pool aggregation
    agg = mgr.aggregate_posteriors("bull", posteriors)
    assert math.isclose(agg["p_optimistic"] + agg["p_neutral"] + agg["p_cautious"], 1.0, rel_tol=1e-5)
    assert 0.0 <= agg["confidence"] <= 1.0
    assert 0.0 <= agg["risk_score"] <= 1.0


def test_calibrated_signal_processor():
    proc = SignalProcessor(quick_thinking_llm=None)
    posteriors = {
        "market_analyst_v2": {"p_optimistic": 0.82, "p_neutral": 0.10, "p_cautious": 0.08, "expected_move_bps": 150.0},
        "chip_distribution_analyst_v2": {"p_optimistic": 0.78, "p_neutral": 0.12, "p_cautious": 0.10, "expected_move_bps": 130.0},
    }
    res = proc.process_calibrated_signal(
        full_signal="Strong institutional accumulation and breakout.",
        stock_symbol="000858.SZ",
        analyst_posteriors=posteriors,
        regime="bull",
        current_price=100.0,
    )
    assert res["action"] == "buy"
    assert res["target_price"] == 101.4  # +140 bps average expected move on 100.0
    assert res["confidence"] != 0.7  # Calibrated rather than hardcoded 0.7
