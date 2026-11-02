# -*- coding: utf-8 -*-
"""Valuation measurement specification generation layer single measurement (A10-D1 piece ①) 

Cover with stakes LLM: one pass, fence+Retry, PE loss period correction, garbage output, end-to-end.
"""

import json
import os

import pytest

from core.deliverables.valuation_spec_generator import (
    build_spec_user_prompt,
    extract_json_block,
    generate_valuation_deliverable,
    generate_valuation_spec,
    merge_spec,
)


class StubLLM:
    """Returns the replied piles in a preset order LLM"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)

        class _R:
            content = reply

        return _R()


BUNDLE = {
    "ticker": "601127",
    "stock_name": "Thalys",
    "analysis_date": "2026-09-10",
    "current_price": 56.82,
    "share_count": 15.1,
    "financial_history": [
        {"period": "TTM", "revenue": 1716.5, "net_profit": 59.63},
    ],
    "investment_plan": '{"analysis_view": "Neutral", "summary": "Channel adjustment and profit restoration need to be verified, long and short evidence is balanced"}',
    "fundamentals_report": "ROE rebounded, gross profit margin was stable, and expense ratio decreased.",
    "bull_report": "Sales of new models are ramping up, and revenue is expected to increase significantly in 2026.",
    "bear_report": "The profit base is low and competition intensifies, which suppresses net profit margins.",
}

GOOD_OUTPUT = {
    "earnings_forecast": {
        "assumptions": [
            {"period": "2026E", "revenue_growth": 0.22, "net_margin": 0.05,
             "rationale": "New models are increasing in volume (optimistic researcher), but net profit margins are suppressed by competition (prudent researcher)"},
            {"period": "2027E", "revenue_growth": 0.15, "net_margin": 0.055,
             "rationale": "Scale effect dilutes expenses and net profit margin moderately improves"},
        ]
    },
    "valuation": {
        "scenarios": [
            {"name": "pessimistic", "method": "PE", "multiple": 12, "eps_period": "2026E",
             "benchmark_basis": "Approximately 12 times lower than that of OEMs",
             "applicability_check": {"passed": True, "notes": ["Net profit attributable to parent company is positive"]}},
            {"name": "Neutral", "method": "PE", "multiple": 18, "eps_period": "2026E",
             "benchmark_basis": "Comparable vehicle companies 15-20 times the range center",
             "applicability_check": {"passed": True, "notes": ["Net profit attributable to parent company is positive"]}},
            {"name": "optimistic", "method": "PE", "multiple": 22, "eps_period": "2027E",
             "benchmark_basis": "The upper edge of the range of comparable vehicle companies",
             "applicability_check": {"passed": True, "notes": ["Net profit attributable to parent company is positive"]}},
        ],
        "risk_notes": ["The calculations are scenario assumptions and do not constitute investment advice."],
    },
}


def test_extract_json_block_variants():
    obj = {"a": 1}
    assert extract_json_block(json.dumps(obj)) == obj
    assert extract_json_block("```json\n" + json.dumps(obj, ensure_ascii=False) + "\n```") == obj
    assert extract_json_block("Okay, here are the specs:\n" + json.dumps(obj) + "\n above.") == obj
    assert extract_json_block("Not at all JSON") is None
    assert extract_json_block("") is None


def test_merge_spec_injects_bundle_data():
    model_out = json.loads(json.dumps(GOOD_OUTPUT))
    # Even if the model outputs wrong history/price, the bundle will prevail
    model_out["current_price"] = 999.0
    model_out["share_count"] = 1.0
    spec = merge_spec(model_out, BUNDLE)
    assert spec["current_price"] == 56.82
    assert spec["share_count"] == 15.1
    assert spec["earnings_forecast"]["history"] == BUNDLE["financial_history"]
    assert spec["earnings_forecast"]["assumptions"] == model_out["earnings_forecast"]["assumptions"]


def test_user_prompt_contains_data_anchors():
    prompt = build_spec_user_prompt(BUNDLE)
    assert "56.82" in prompt and "15.1" in prompt
    assert "1716.5" in prompt
    assert "No modifications allowed" in prompt


def test_first_pass_success():
    llm = StubLLM([json.dumps(GOOD_OUTPUT, ensure_ascii=False)])
    result = generate_valuation_spec(BUNDLE, llm)
    assert result["passed"], result["errors"]
    assert result["attempts"] == 1
    assert result["spec"]["current_price"] == 56.82


def test_fenced_and_invalid_then_retry():
    bad = json.loads(json.dumps(GOOD_OUTPUT))
    bad["valuation"]["scenarios"][0]["multiple"] = 0  # trigger"multiplier is zero"
    llm = StubLLM([
        "```json\n" + json.dumps(bad, ensure_ascii=False) + "\n```",  # fence + illegal
        json.dumps(GOOD_OUTPUT, ensure_ascii=False),                   # Correction
    ])
    result = generate_valuation_spec(BUNDLE, llm)
    assert result["passed"]
    assert result["attempts"] == 2
    # The feedback message for the second call contains an error description
    feedback = llm.calls[1][-1].content
    assert "multiplier is zero" in feedback


def test_pe_on_loss_year_corrected_by_retry():
    bundle = json.loads(json.dumps(BUNDLE))
    bundle["financial_history"] = [
        {"period": "TTM", "revenue": 1716.5, "net_profit": -12.0},  # loss period
    ]
    bad = json.loads(json.dumps(GOOD_OUTPUT))
    bad["valuation"]["scenarios"][0]["eps_period"] = "TTM"  # PE Falling into a period of loss
    llm = StubLLM([
        json.dumps(bad, ensure_ascii=False),
        json.dumps(GOOD_OUTPUT, ensure_ascii=False),  # Return to profit forecast period
    ])
    result = generate_valuation_spec(bundle, llm)
    assert result["passed"], result["errors"]
    assert "PE" in llm.calls[1][-1].content  # PE suitability issues noted in feedback


def test_garbage_output_exhausts_attempts():
    llm = StubLLM(["I don t think it can be done", "Still not working", "third failure"])
    result = generate_valuation_spec(BUNDLE, llm, max_attempts=3)
    assert not result["passed"]
    assert result["attempts"] == 3
    assert any("JSON" in e for e in result["errors"])


def test_end_to_end_deliverable(tmp_path):
    llm = StubLLM([json.dumps(GOOD_OUTPUT, ensure_ascii=False)])
    out = generate_valuation_deliverable(
        BUNDLE, llm, output_path=str(tmp_path / "e2e.xlsx"))
    assert out["success"], out.get("validation")
    assert os.path.exists(out["path"])
    assert out["attempts"] == 1
    # TTM Revenue 1716.5 × 1.22 × 0.05 = 104.71 billion net profit;EPS = 104.71/15.1
    eps = 1716.5 * 1.22 * 0.05 / 15.1
    assert out["validation"]["summary"]["scenarios"]["Neutral"]["eps"] == pytest.approx(eps, abs=1e-3)


def test_end_to_end_spec_failure(tmp_path):
    llm = StubLLM(["Not a JSON reply at all"])
    out = generate_valuation_deliverable(BUNDLE, llm, output_path=str(tmp_path / "x.xlsx"),
                                         max_attempts=1)
    assert not out["success"]
    assert out["stage"] == "spec_generation"
    assert not os.path.exists(str(tmp_path / "x.xlsx"))
