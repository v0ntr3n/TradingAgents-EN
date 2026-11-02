"""
Mandatory Automated Verification Suite for Agent Market Arena (AMA, arXiv:2510.11695v2)
and FinBen FinTrade (`arXiv:2402.12659v2`) Integration (`tests/test_ama_finben_integration.py`).

Verifies all 5 Mandatory Gates:
  1. `test_ama_endpoint_contract`: Verify `POST /trading_action/` and `AMAProtocolAdapter.trading_action`
     accept the exact AMA payload for `TSLA`, `BMRN`, `BTC`, and `ETH`, route distinct modalities
     to the 4 specialists, run the CBS/VOI gate, and return valid
     `{"recommended_action": "BUY"|"SELL"|"HOLD", "reasoning": "..."}`.
  2. `test_ama_metrics_exact_match`: Verify `evaluate_ama_metrics()` matches the exact equations
     in Section 3.3 of `arXiv:2510.11695v2` (`CR%`, `AR%`, `AV%`, `SR`, `MDD%`).
  3. `test_finben_fintrade_schema_and_uniqueness`: Verify `FinBenAdapter` outputs valid Table 8 JSON
     (`investment_decision`, `summary_reason`, `short_memory_index`, `middle_memory_index`,
     `long_memory_index`, `reflection_memory_index`), computes `CR%`, `SR`, `DV%`, `AV%`, `MD%`
     with 95% CI, and asserts via SHA-256 that all 10 `FinTrade` tickers have unique,
     non-duplicated price/news series.
  4. `test_iso_budget_and_zero_leakage`: Verify that perturbing future prices/news at `>= t+1`
     changes 0 bits of step `t` outputs and that Iso-Budget mode matches verification rates
     within `±1.5%`.
  5. `test_all_existing_suites_pass`: Run all existing unit tests in `tests/` and confirm 0 failures.
"""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import tests  # registers offline test stubs if needed
from core.arena.ama_adapter import AMAProtocolAdapter, app
from core.backtest.result_evaluator import evaluate_ama_metrics, evaluate_finben_metrics
from core.baselines.policies import UnifiedBenchmarkPolicyRunner
from core.data.benchmark_loader import BenchmarkDatasetLoader, build_causal_step_record_at_index
from core.finben.finben_adapter import (
    FINBEN_FINTRADE_10_TICKERS,
    FINBEN_TABLE8_REQUIRED_KEYS,
    FinBenAdapter,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _sample_ama_payload(symbol: str, date_str: str = "2025-08-15") -> dict:
    is_crypto = symbol in ("BTC", "ETH")
    base_p = 98000.0 if symbol == "BTC" else (2850.0 if symbol == "ETH" else (215.40 if symbol == "TSLA" else 61.20))
    hist = [
        {"date": f"2025-08-{10 + i:02d}", "price": round(base_p * (0.97 + 0.006 * i), 2)}
        for i in range(5)
    ]
    return {
        "date": date_str,
        "price": {symbol: base_p},
        "news": {
            symbol: f"Expert-verified daily Market Intelligence Stream (MIS) summary for {symbol} on {date_str}: strong institutional growth and positive catalyst momentum."
        },
        "symbol": [symbol],
        "model": "gpt-4.1",
        "10k": {symbol: [] if is_crypto else [f"Point-in-time 10-K filing excerpt for {symbol}: revenue growth and margin expansion."]},
        "10q": {symbol: [] if is_crypto else [f"Point-in-time 10-Q filing excerpt for {symbol}: strong free cash flow and liquidity."]},
        "history_price": {symbol: hist},
    }


def test_ama_endpoint_contract():
    """
    Gate #1:
    Verify `POST /trading_action/` and `AMAProtocolAdapter.trading_action` accept the exact
    AMA payload for `TSLA`, `BMRN`, `BTC`, and `ETH`, route distinct modalities to the 4
    specialists, run the CBS/VOI gate, and return valid
    `{"recommended_action": "BUY"|"SELL"|"HOLD", "reasoning": "..."}`.
    """
    client = TestClient(app)
    adapter = AMAProtocolAdapter()

    for sym in ("TSLA", "BMRN", "BTC", "ETH"):
        payload = _sample_ama_payload(sym)

        # 1. Direct Python Adapter call
        py_res = adapter.trading_action(payload)
        assert set(py_res.keys()) == {"recommended_action", "reasoning"}
        assert py_res["recommended_action"] in ("BUY", "SELL", "HOLD")
        assert "Regime:" in py_res["reasoning"]
        assert "JSD:" in py_res["reasoning"]
        assert "CBS:" in py_res["reasoning"]
        assert "Gate:" in py_res["reasoning"]
        assert "Weights:" in py_res["reasoning"]

        # Verify distinct modalities routed to the 4 specialists
        trace = adapter.instance_last_trace
        assert trace is not None
        mods = trace["specialist_modalities"]
        assert set(mods.keys()) == {"market", "fundamentals", "news", "social"}
        key_sets = [frozenset(mods[k].keys()) for k in ("market", "fundamentals", "news", "social")]
        assert len(set(key_sets)) == 4, f"Expected 4 disjoint modality schemas for {sym}"

        if sym in ("BTC", "ETH"):
            assert mods["fundamentals"]["asset_class"] == "crypto"
            assert "onchain_nvt_velocity_proxy" in mods["fundamentals"]
        else:
            assert mods["fundamentals"]["asset_class"] == "equity"
            assert mods["fundamentals"]["sec_10k_excerpt_count"] >= 1

        # Verify CBS/VOI & EvidenceContract execution
        assert "voi_eval" in trace and "evidence_contract" in trace
        assert trace["jsd"] >= 0.0
        assert trace["cbs_bps"] >= 0.0

        # 2. FastAPI REST endpoint `POST /trading_action/`
        http_resp = client.post("/trading_action/", json=payload)
        assert http_resp.status_code == 200
        http_json = http_resp.json()
        assert set(http_json.keys()) == {"recommended_action", "reasoning"}
        assert http_json["recommended_action"] in ("BUY", "SELL", "HOLD")


def test_ama_metrics_exact_match():
    """
    Gate #2:
    Verify `evaluate_ama_metrics()` matches the exact equations in Section 3.3 of
    `arXiv:2510.11695v2` (`CR%`, `AR%`, `AV%`, `SR`, `MDD%`).
    """
    prices = [100.0, 102.0, 101.0, 104.0, 103.0, 106.0]
    signals = [1.0, 1.0, -1.0, 1.0, 0.0]
    fee_bps = 10.0
    c_fee = fee_bps * 1e-4

    # Hand-compute r_t = w_t * ((P_t - P_{t-1}) / P_{t-1}) - c_fee * |w_t - w_{t-1}|
    p_arr = np.array(prices, dtype=np.float64)
    asset_rets = (p_arr[1:] - p_arr[:-1]) / p_arr[:-1]
    w_arr = np.array(signals, dtype=np.float64)
    w_prev = np.concatenate([[0.0], w_arr[:-1]])
    r_expected = w_arr * asset_rets - c_fee * np.abs(w_arr - w_prev)

    T = len(r_expected)
    E = np.cumprod(1.0 + r_expected)
    R_T = float(E[-1] - 1.0)
    expected_cr_pct = R_T * 100.0
    expected_ar_pct = (((1.0 + R_T) ** (252.0 / T)) - 1.0) * 100.0
    sigma_ann = math.sqrt(252.0) * float(np.std(r_expected, ddof=0))
    expected_av_pct = sigma_ann * 100.0
    expected_sr = (float(np.mean(r_expected)) * 252.0) / sigma_ann
    peaks = np.maximum.accumulate(E)
    expected_mdd_pct = float(np.max((peaks - E) / peaks)) * 100.0

    res = evaluate_ama_metrics(signals=signals, prices=prices, fee_bps=fee_bps, ddof=0)
    assert abs(res["CR%"] - expected_cr_pct) < 1e-3
    assert abs(res["AR%"] - expected_ar_pct) < 1e-3
    assert abs(res["AV%"] - expected_av_pct) < 1e-3
    assert abs(res["SR"] - expected_sr) < 1e-3
    assert abs(res["MDD%"] - expected_mdd_pct) < 1e-3


def test_finben_fintrade_schema_and_uniqueness():
    """
    Gate #3:
    Verify `FinBenAdapter` outputs valid Table 8 JSON (`investment_decision`, `summary_reason`,
    `short_memory_index`, `middle_memory_index`, `long_memory_index`, `reflection_memory_index`),
    computes `CR%`, `SR`, `DV%`, `AV%`, `MD%` with 95% CI, and asserts via SHA-256 that all
    10 `FinTrade` tickers have unique, non-duplicated price/news series.
    """
    fb = FinBenAdapter(model_id="deepseek-v4-pro")
    data = fb.load_verified_fintrade_10_stocks(n_steps=30)

    # 1. Verify all 10 FinTrade tickers and SHA-256 uniqueness
    uniq_report = fb.verify_sha256_uniqueness(data)
    assert uniq_report["verified_unique"] is True
    assert tuple(uniq_report["tickers"]) == FINBEN_FINTRADE_10_TICKERS
    assert uniq_report["unique_price_hashes"] == 10
    assert uniq_report["unique_news_hashes"] == 10
    assert uniq_report["unique_filing_hashes"] == 10

    # Verify duplicate pickle corruption guard rejects corrupted DRIV_train.pkl copies
    corrupted = copy.deepcopy(data)
    corrupted["MSFT"] = copy.deepcopy(corrupted["TSLA"])
    with pytest.raises(ValueError, match="Duplicate"):
        fb.verify_sha256_uniqueness(corrupted)

    # 2. Verify Table 8 JSON output schema on each ticker
    for ticker in FINBEN_FINTRADE_10_TICKERS:
        step0 = data[ticker][0]
        out = fb.generate_table8_decision(step0)
        valid, msg = fb.validate_table8_schema(out)
        assert valid, f"Table 8 schema validation failed for {ticker}: {msg}"
        assert set(out.keys()) == set(FINBEN_TABLE8_REQUIRED_KEYS)
        assert out["investment_decision"] in ("buy", "sell", "hold")

    # 3. Verify FinBen metrics (`CR%`, `SR`, `DV%`, `AV%`, `MD%` with 95% CI)
    bench = fb.run_fintrade_10stock_benchmark(fee_bps=5.0)
    port_m = bench["portfolio_ours"]
    for key in ("CR%", "SR", "DV%", "AV%", "MD%", "ci95"):
        assert key in port_m, f"Missing FinBen metric key {key}"
    for m_key in ("CR%", "SR", "DV%", "AV%", "MD%"):
        low, high = port_m["ci95"][m_key]
        assert low <= high, f"Invalid 95% CI for {m_key}: ({low}, {high})"


def test_iso_budget_and_zero_leakage():
    """
    Gate #4:
    Verify that perturbing future prices/news at `>= t+1` changes 0 bits of step `t`
    outputs and that Iso-Budget mode matches verification rates within `±1.5%`.
    """
    # 1. AMA zero look-ahead check: append future dates > 2025-08-15 with extreme prices/news
    adapter_clean = AMAProtocolAdapter()
    adapter_corrupt = AMAProtocolAdapter()
    clean_payload = _sample_ama_payload("TSLA", date_str="2025-08-15")
    corrupt_payload = copy.deepcopy(clean_payload)
    corrupt_payload["history_price"]["TSLA"].append({"date": "2025-08-16", "price": 999999.0})
    corrupt_payload["history_price"]["TSLA"].append({"date": "2025-08-17", "price": 0.0001})
    corrupt_payload["news"]["TSLA"] += " On 2025-08-18 TSLA crashes 99% in future leak."

    res_clean = adapter_clean.trading_action(clean_payload)
    res_corrupt = adapter_corrupt.trading_action(corrupt_payload)
    assert res_clean == res_corrupt
    assert adapter_clean.instance_last_trace["specialist_modalities"] == adapter_corrupt.instance_last_trace["specialist_modalities"]

    # 2. Iso-budget verification rate matching across B in {0.10, 0.20, 0.35, 0.50}
    loader = BenchmarkDatasetLoader()
    splits = loader.get_temporal_splits()
    runner = UnifiedBenchmarkPolicyRunner(splits["TRAIN"], splits["VALIDATION"])
    test_steps = splits["EXTERNAL_TEST_2025"]

    for b_rate in (0.10, 0.20, 0.35, 0.50):
        for m_id in ("B06_Static_Tool_LLM", "B08_Random_Verify", "B09_Confidence_Gate", "B10_Empirical_VOI", "Ours"):
            decs = runner.generate_decisions(m_id, test_steps, iso_budget_rate=b_rate, seed=42)
            realized_b = sum(1 for d in decs if d["verified"]) / len(decs)
            assert abs(realized_b - b_rate) <= 0.015, (
                f"Iso-budget mismatch for {m_id} at B={b_rate}: realized={realized_b:.4f}"
            )


def test_all_existing_suites_pass():
    """
    Gate #5:
    Run all existing unit tests in `tests/` and confirm 0 failures.
    """
    existing_suites = [
        "tests/test_cbs_debate_gating.py",
        "tests/test_regime_weight_calculator.py",
        "tests/test_regime_memory_attribution.py",
        "tests/test_protocol_audit_evaluator.py",
        "tests/test_phase5_prompt_seed_and_real_data.py",
        "tests/test_adversarial_challenger_1.py",
        "tests/test_e1_e7_aris_audit.py",
    ]
    cmd = [sys.executable, "-m", "pytest", *existing_suites, "-q"]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"Existing test suite failed:\n{proc.stdout}\n{proc.stderr}"
