import tests  # registers offline stubs
from core.backtest.result_evaluator import ProtocolAuditEvaluator


def test_protocol_audit_evaluator_metrics():
    evaluator = ProtocolAuditEvaluator(
        commission_bps=2.5,
        sell_stamp_duty_bps=5.0,
        half_spread_slippage_bps=7.5,
    )
    records = [
        {
            "date": "2026-01-05",
            "regime": "bull",
            "position": 1.0,
            "asset_return_pct": 1.5,
            "p_optimistic": 0.78,
            "p_neutral": 0.12,
            "p_cautious": 0.10,
            "prompt_tokens": 1800,
            "completion_tokens": 450,
            "latency_sec": 1.8,
            "debate_skipped": True,
            "execution_edge_bps": 28.0,
        },
        {
            "date": "2026-01-06",
            "regime": "bear",
            "position": 0.0,
            "asset_return_pct": -2.1,
            "p_optimistic": 0.12,
            "p_neutral": 0.18,
            "p_cautious": 0.70,
            "prompt_tokens": 4200,
            "completion_tokens": 1100,
            "latency_sec": 4.9,
            "debate_skipped": False,
            "execution_edge_bps": 42.0,
        },
        {
            "date": "2026-01-07",
            "regime": "sideways",
            "position": 0.5,
            "asset_return_pct": 0.4,
            "p_optimistic": 0.55,
            "p_neutral": 0.30,
            "p_cautious": 0.15,
            "prompt_tokens": 1900,
            "completion_tokens": 480,
            "latency_sec": 1.9,
            "debate_skipped": True,
            "execution_edge_bps": 24.0,
        },
    ]

    metrics = evaluator.evaluate_records(records)
    assert metrics["gross_cumulative_return"] > metrics["net_cumulative_return"]
    assert metrics["total_transaction_cost_bps"] > 0.0
    assert metrics["realized_cbs_bps"] > 0.0
    assert metrics["cbs_surplus_bps"] > 0.0
    assert "bull" in metrics["regime_metrics"]
    assert "bear" in metrics["regime_metrics"]
    assert "sideways" in metrics["regime_metrics"]
    assert 0.0 <= metrics["brier_score"] <= 1.0
    assert 0.0 <= metrics["expected_calibration_error"] <= 1.0
