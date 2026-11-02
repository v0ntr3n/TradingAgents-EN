"""
Empirical Data & Cache Integrity Audit Test Suite.
Validates:
1. `results/live_llm_posteriors_cache.json` schema, probabilities, token counts, and zero look-ahead bias.
2. `data/phase5_real_2025_2026_prices.csv` and `data/phase5_multimodal_2024_2026_pit.csv` integrity,
   no NaN/Inf, zero duplicate timestamps, identical symbol sets, and point-in-time causality.
"""

from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
PRICES_CSV = REPO_ROOT / "data" / "phase5_real_2025_2026_prices.csv"
PIT_CSV = REPO_ROOT / "data" / "phase5_multimodal_2024_2026_pit.csv"
CACHE_JSON = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"

EXPECTED_SYMBOLS = {"NVDA", "AAPL", "GOOGL", "AMZN"}
EXPECTED_TIERS = {"deepseek-v4-pro", "deepseek-flash"}


class TestEmpiricalDataCacheIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load cache with duplicate key detection
        cls.raw_duplicate_keys = []

        def _track_pairs(pairs):
            seen = set()
            for k, _ in pairs:
                if k in seen:
                    cls.raw_duplicate_keys.append(k)
                seen.add(k)
            return dict(pairs)

        with CACHE_JSON.open("r", encoding="utf-8") as f:
            cls.cache = json.load(f, object_pairs_hook=_track_pairs)

        cls.prices_df = pd.read_csv(PRICES_CSV)
        cls.pit_df = pd.read_csv(PIT_CSV)

    def test_cache_keys_count_and_schema(self):
        """Verify 5,735 keys, exact schema {tier}::{role}::{symbol}::{date}, and no duplicate keys."""
        self.assertEqual(len(self.raw_duplicate_keys), 0, f"Found duplicate keys in raw JSON: {self.raw_duplicate_keys}")
        self.assertEqual(len(self.cache), 5735, f"Expected 5,735 keys, got {len(self.cache)}")

        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for k in self.cache.keys():
            parts = k.split("::")
            self.assertEqual(len(parts), 4, f"Key '{k}' must have exactly 4 segments separated by '::'")
            tier, role, sym, dt_str = parts
            self.assertIn(tier, EXPECTED_TIERS, f"Key '{k}' has invalid tier '{tier}'")
            self.assertTrue(len(role) > 0 and " " not in role, f"Key '{k}' has invalid role '{role}'")
            self.assertIn(sym, EXPECTED_SYMBOLS, f"Key '{k}' has invalid symbol '{sym}'")
            self.assertTrue(date_re.match(dt_str), f"Key '{k}' has invalid date format '{dt_str}'")

    def test_cache_tokens_and_probabilities(self):
        """Verify tokens_used > 0 and valid probability distribution (sum == 1.0) on all 5,735 keys."""
        for k, v in self.cache.items():
            self.assertIsInstance(v, dict, f"Entry for {k} must be a dict")

            # Token count verification
            tokens = v.get("tokens_used")
            self.assertIsNotNone(tokens, f"Entry {k} is missing 'tokens_used'")
            self.assertIsInstance(tokens, int, f"Entry {k} tokens_used must be int")
            self.assertGreater(tokens, 0, f"Entry {k} tokens_used must be > 0, got {tokens}")

            # Model tier matching
            tier = k.split("::")[0]
            model = v.get("model")
            self.assertEqual(model, tier, f"Entry {k} model '{model}' does not match key tier '{tier}'")

            # Probability distribution verification
            p_opt = v.get("p_optimistic")
            p_neu = v.get("p_neutral")
            p_cau = v.get("p_cautious")
            for name, p in [("p_optimistic", p_opt), ("p_neutral", p_neu), ("p_cautious", p_cau)]:
                self.assertIsNotNone(p, f"Entry {k} is missing '{name}'")
                self.assertIsInstance(p, (float, int), f"Entry {k} '{name}' must be numeric")
                self.assertFalse(math.isnan(p) or math.isinf(p), f"Entry {k} '{name}' is NaN/Inf")
                self.assertGreaterEqual(p, 0.0, f"Entry {k} '{name}' must be >= 0.0")
                self.assertLessEqual(p, 1.0, f"Entry {k} '{name}' must be <= 1.0")

            prob_sum = float(p_opt) + float(p_neu) + float(p_cau)
            self.assertAlmostEqual(
                prob_sum, 1.0, places=4,
                msg=f"Entry {k} probabilities do not sum to 1.0: {prob_sum}"
            )

            # Text content sanity
            self.assertTrue(len(str(v.get("prompt", "")).strip()) > 0, f"Entry {k} has empty prompt")

    def test_cache_zero_lookahead_bias(self):
        """Verify deliberation dates precede or match bar timestamps strictly without peeking at future prices."""
        price_dates = set(self.prices_df["date"].unique())
        date_pattern = re.compile(r"\b(202[4-9]-\d{2}-\d{2})\b")
        close_re = re.compile(r"Close=([\d\.]+)")

        price_lookup = {(r["symbol"], r["date"]): float(r["close"]) for _, r in self.prices_df.iterrows()}

        for k, v in self.cache.items():
            _, _, sym, dt_str = k.split("::")

            # Deliberation date must exist in the real prices dataset
            self.assertIn(dt_str, price_dates, f"Cache key {k} has date {dt_str} not in prices dataset")

            # Adversarial text check: verify no future date appears in prompt or raw_response
            prompt = v.get("prompt", "")
            for ref_dt in date_pattern.findall(prompt):
                self.assertLessEqual(
                    ref_dt, dt_str,
                    f"Look-ahead violation in prompt of {k}: referenced future date {ref_dt} > {dt_str}"
                )

            raw_resp = v.get("raw_response", "")
            for ref_dt in date_pattern.findall(raw_resp):
                self.assertLessEqual(
                    ref_dt, dt_str,
                    f"Look-ahead violation in raw_response of {k}: referenced future date {ref_dt} > {dt_str}"
                )

            # Price match check: if prompt cites Close=X, it must match point-in-time price
            m = close_re.search(prompt)
            if m:
                prompt_close = float(m.group(1))
                actual_close = price_lookup.get((sym, dt_str))
                self.assertIsNotNone(actual_close, f"Missing price for {(sym, dt_str)}")
                self.assertAlmostEqual(
                    prompt_close, actual_close, places=2,
                    msg=f"Close price mismatch in prompt {k}: prompt={prompt_close} vs actual={actual_close}"
                )

    def test_dataset_csv_integrity_and_duplicates(self):
        """Verify no NaN/Inf, zero duplicate timestamps, identical symbol sets, and CSV equality."""
        self.assertEqual(self.prices_df.shape, (380, 38))
        self.assertEqual(self.pit_df.shape, (380, 38))
        self.assertTrue(self.prices_df.equals(self.pit_df), "Prices and Multimodal PIT CSVs must be identical")

        # Zero NaNs / Infs across all 38 columns
        self.assertEqual(self.prices_df.isnull().sum().sum(), 0, "Prices CSV contains NaN values")
        self.assertEqual(self.pit_df.isnull().sum().sum(), 0, "PIT CSV contains NaN values")

        num_cols = self.prices_df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            self.assertEqual(np.isinf(self.prices_df[c]).sum(), 0, f"Column {c} contains Inf")

        # Symbol set check
        self.assertEqual(set(self.prices_df["symbol"].unique()), EXPECTED_SYMBOLS)
        self.assertEqual(set(self.pit_df["symbol"].unique()), EXPECTED_SYMBOLS)

        # Zero duplicate (symbol, date) timestamps
        self.assertEqual(self.prices_df.duplicated(subset=["symbol", "date"]).sum(), 0)
        self.assertEqual(self.pit_df.duplicated(subset=["symbol", "date"]).sum(), 0)

        # Monotonic ascending dates per symbol
        for sym in EXPECTED_SYMBOLS:
            sym_df = self.prices_df[self.prices_df["symbol"] == sym]
            self.assertEqual(len(sym_df), 95)
            dates = list(sym_df["date"])
            self.assertTrue(
                all(dates[i] < dates[i + 1] for i in range(len(dates) - 1)),
                f"Dates for symbol {sym} are not strictly monotonically increasing"
            )

        # News timestamps <= bar dates and no duplicate news timestamps per symbol
        for idx, row in self.prices_df.iterrows():
            sym = row["symbol"]
            bar_date = row["date"]
            news_ts = str(row["news_timestamp"])
            news_date = news_ts.split("T")[0] if "T" in news_ts else news_ts
            self.assertLessEqual(news_date, bar_date, f"Row {idx} ({sym}) has news_date {news_date} > bar_date {bar_date}")

        for sym in EXPECTED_SYMBOLS:
            sym_df = self.prices_df[self.prices_df["symbol"] == sym]
            self.assertEqual(sym_df.duplicated(subset=["news_timestamp"]).sum(), 0)

        # Price column sanity
        self.assertTrue((self.prices_df["close"] > 0).all(), "All close prices must be > 0")
        self.assertTrue((self.prices_df["ma4"] > 0).all(), "All ma4 values must be > 0")
        self.assertTrue((self.prices_df["ma8"] > 0).all(), "All ma8 values must be > 0")
        self.assertTrue((self.prices_df["rsi_14"].between(0, 100)).all(), "RSI_14 must be within [0, 100]")

    def test_zero_prohibited_chinese_stocks_or_synthetic_fallbacks(self):
        """Adversarial check: zero A-share codes or synthetic model strings in cache or data."""
        forbidden = [
            "600519", "000858", "300750", "002594", "600036", "601318", "000333",
            "ASHR", "CSI", "Moutai", "Kweichow",
            "Small_SLM_Qwen2.5_14B", "Frontier_LLM_DeepSeek_V3",
            "_synthesize_causal_posteriors_from_modalities", "synthetic",
        ]
        with CACHE_JSON.open("r", encoding="utf-8") as f:
            cache_text = f.read()
        for term in forbidden:
            self.assertNotIn(term, cache_text, f"Forbidden term '{term}' found in cache JSON")

        with PRICES_CSV.open("r", encoding="utf-8") as f:
            prices_text = f.read()
        for term in forbidden:
            self.assertNotIn(term, prices_text, f"Forbidden term '{term}' found in prices CSV")


if __name__ == "__main__":
    unittest.main()
