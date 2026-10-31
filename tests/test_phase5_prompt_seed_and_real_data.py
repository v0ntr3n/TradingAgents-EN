"""
Unit Tests for Phase 5:
  - Step 5.1: Real 2025-2026 Point-in-Time Market Dataset (12 equities, CN CSI 300 & US Tech)
  - Step 5.2: Dual-Backbone 2x4 Cross-Architecture CPH Evaluation (MR-1 to MR-7)
  - Step 5.3: Prompt Seed Structured JSON Posterior Contract (`system_prompt_seed_service.py`)
"""

import csv
import unittest
from pathlib import Path

import tests  # registers offline stubs
from core.agents.analyst import extract_structured_posterior

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPhase5RealMarketAndPromptSeed(unittest.TestCase):
    def test_step_5_1_real_2025_2026_dataset_integrity(self):
        csv_path = REPO_ROOT / "data" / "phase5_real_2025_2026_prices.csv"
        self.assertTrue(csv_path.exists(), "Real 2025-2026 dataset CSV must exist")
        with open(csv_path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertGreaterEqual(len(rows), 1000)
        symbols = {r["symbol"] for r in rows}
        expected_symbols = {
            "ASHR", "600519.SH", "000858.SZ", "300750.SZ",
            "002594.SZ", "600036.SH", "601318.SH", "000333.SZ",
            "NVDA", "AAPL", "GOOGL", "AMZN",
        }
        self.assertEqual(symbols, expected_symbols)

    def test_step_5_2_cph_2x4_factorial_results_and_artifacts(self):
        res_csv = REPO_ROOT / "results" / "phase5_real_market_cph_results.csv"
        tex_path = REPO_ROOT / "results" / "phase5_cph_table.tex"
        fig_path = REPO_ROOT / "results" / "regime_weight_trajectories.png"

        self.assertTrue(res_csv.exists(), "Phase 5 summary CSV must exist")
        self.assertTrue(tex_path.exists(), "Phase 5 LaTeX table must exist")
        self.assertTrue(fig_path.exists(), "Phase 6 regime weight figure must exist")

        with open(res_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        by_key = {(r["universe"], r["model_tier"], r["protocol"]): r for r in rows}

        # Verify Coordination Primacy Hypothesis on China CSI 300 A-Shares: coordination gain > model scaling gain
        cn_m2_slm = float(by_key[("CN_CSI300_A_Shares", "Small_SLM_Qwen2.5_14B", "M2_Vanilla_TradingAgents")]["net_sharpe"])
        cn_m4_slm = float(by_key[("CN_CSI300_A_Shares", "Small_SLM_Qwen2.5_14B", "M4_CARE_Agents_Ours")]["net_sharpe"])
        cn_m2_llm = float(by_key[("CN_CSI300_A_Shares", "Frontier_LLM_DeepSeek_V3", "M2_Vanilla_TradingAgents")]["net_sharpe"])
        cn_m4_llm = float(by_key[("CN_CSI300_A_Shares", "Frontier_LLM_DeepSeek_V3", "M4_CARE_Agents_Ours")]["net_sharpe"])

        coord_gain_slm = cn_m4_slm - cn_m2_slm
        coord_gain_llm = cn_m4_llm - cn_m2_llm
        scale_gain_m2 = cn_m2_llm - cn_m2_slm

        self.assertGreater(coord_gain_slm, 0.40)
        self.assertGreater(coord_gain_llm, 0.40)
        self.assertGreater(coord_gain_llm, scale_gain_m2)

        # Verify US Tech Benchmark robust positive Sharpe under real LLM posteriors
        us_m4_slm = float(by_key[("US_Tech_Benchmark", "Small_SLM_Qwen2.5_14B", "M4_CARE_Agents_Ours")]["net_sharpe"])
        us_m4_llm = float(by_key[("US_Tech_Benchmark", "Frontier_LLM_DeepSeek_V3", "M4_CARE_Agents_Ours")]["net_sharpe"])
        self.assertGreater(us_m4_slm, 0.50)
        self.assertGreater(us_m4_llm, 0.50)

    def test_step_5_3_system_prompt_seed_service_json_contract(self):
        seed_path = REPO_ROOT / "app" / "services" / "system_prompt_seed_service.py"
        content = seed_path.read_text(encoding="utf-8")
        self.assertIn("append a single-line JSON posterior block", content)
        self.assertIn("p_optimistic", content)
        self.assertIn("expected_move_bps", content)
        self.assertIn("market_regime", content)

        # Verify parser compatibility with the seeded JSON block format
        sample_output = (
            "Detailed fundamental and technical analysis completed.\n"
            "```json\n"
            '{"p_optimistic": 0.62, "p_neutral": 0.23, "p_cautious": 0.15, '
            '"expected_move_bps": 85.0, "confidence": 0.82, "market_regime": "bull"}\n'
            "```"
        )
        parsed = extract_structured_posterior(sample_output)
        self.assertAlmostEqual(parsed["p_optimistic"], 0.62, places=2)
        self.assertAlmostEqual(parsed["p_neutral"], 0.23, places=2)
        self.assertAlmostEqual(parsed["p_cautious"], 0.15, places=2)
        self.assertAlmostEqual(parsed["expected_move_bps"], 85.0, places=1)
        self.assertEqual(parsed["market_regime"], "bull")


if __name__ == "__main__":
    unittest.main()
