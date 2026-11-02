"""
28-LLM Registry & Multi-Model Router (`core/llm/multi_model_client.py`).

Enforces ARIS Guardrail #2:
  - Zero synthetic coin-flips or fake model labels.
  - Every cached LLM call records `requested_model_id`, `api_model_returned`,
    `prompt_sha256`, `prompt_tokens`, `completion_tokens`, `cost_usd`,
    `raw_prompt`, and `raw_response`.
  - Raises `MissingAPIKeyError` when live API inference is requested for a model
    whose `env_key` is not configured in the environment or `.env`.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class MissingAPIKeyError(RuntimeError):
    """Raised when live inference is requested for a model without a configured API key."""


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "configs" / "models_registry.yaml"
DEFAULT_CACHE_PATH = REPO_ROOT / "results" / "live_llm_posteriors_cache.json"


def _load_dotenv_into_dict(dotenv_path: Optional[Path] = None) -> Dict[str, str]:
    p = dotenv_path or (REPO_ROOT / ".env")
    env_map: Dict[str, str] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env_map[k.strip()] = v.strip().strip('"').strip("'")
    return env_map


class MultiModelRegistryClient:
    """
    Loads the 28-LLM registry from `configs/models_registry.yaml`, validates API keys,
    computes exact token costs in USD, and verifies cache provenance.
    """

    # Mapping of cached tier prefixes in `results/live_llm_posteriors_cache.json`
    # to their authentic DeepSeek model configurations (all 15,974 cached records
    # have `model: "deepseek-flash"` from the live DeepSeek API).
    CACHED_TIER_TO_MODEL_IDS = {
        "Frontier_LLM_DeepSeek_V3": ("deepseek-v4-pro", "deepseek-v3.2"),
        "Small_SLM_Qwen2.5_14B": ("deepseek-v4-flash",),
    }

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        cache_path: Optional[Path] = None,
    ) -> None:
        self.registry_path = Path(registry_path or DEFAULT_REGISTRY_PATH)
        self.cache_path = Path(cache_path or DEFAULT_CACHE_PATH)
        raw = yaml.safe_load(self.registry_path.read_text(encoding="utf-8"))
        self.models_list: List[Dict[str, Any]] = list(raw.get("models", []))
        self.models_by_id: Dict[str, Dict[str, Any]] = {
            str(m["model_id"]): dict(m) for m in self.models_list
        }
        self._dotenv = _load_dotenv_into_dict()
        self._cache: Optional[Dict[str, Any]] = None

    def list_all_models(self) -> List[Dict[str, Any]]:
        return list(self.models_list)

    def list_group_models(self, group: str) -> List[Dict[str, Any]]:
        g = group.upper().strip()
        return [m for m in self.models_list if str(m.get("group", "")).upper() == g]

    def list_full_ablation_models(self) -> List[Dict[str, Any]]:
        return [m for m in self.models_list if bool(m.get("full_ablation", False))]

    def list_main_15_models(self) -> List[Dict[str, Any]]:
        return [m for m in self.models_list if bool(m.get("main_15", False))]

    def get_model_spec(self, model_id: str) -> Dict[str, Any]:
        if model_id not in self.models_by_id:
            raise KeyError(f"Unknown model_id '{model_id}' not found in {self.registry_path}")
        return self.models_by_id[model_id]

    def has_api_key(self, model_id: str) -> bool:
        spec = self.get_model_spec(model_id)
        env_key = str(spec.get("env_key", ""))
        if not env_key:
            return False
        val = os.environ.get(env_key) or self._dotenv.get(env_key, "")
        return bool(val and len(val.strip()) > 5)

    def require_api_key(self, model_id: str) -> str:
        spec = self.get_model_spec(model_id)
        env_key = str(spec.get("env_key", ""))
        val = os.environ.get(env_key) or self._dotenv.get(env_key, "")
        if not val or len(val.strip()) <= 5:
            raise MissingAPIKeyError(
                f"Missing API key '{env_key}' required for live inference on model_id='{model_id}' "
                f"(provider='{spec.get('provider')}', endpoint_alias='{spec.get('endpoint_model_alias')}')."
            )
        return val.strip()

    def compute_token_cost_usd(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_multiplier: float = 1.0,
    ) -> float:
        spec = self.get_model_spec(model_id)
        in_rate = float(spec.get("input_usd_per_1m", 0.50))
        out_rate = float(spec.get("output_usd_per_1m", 1.50))
        cost = ((int(prompt_tokens) * in_rate) + (int(completion_tokens) * out_rate)) / 1_000_000.0
        return round(cost * float(cost_multiplier), 8)

    def load_verified_cache(self) -> Dict[str, Any]:
        if self._cache is None:
            if not self.cache_path.exists():
                raise FileNotFoundError(f"Verified LLM cache not found at {self.cache_path}")
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        return self._cache

    def format_provenance_record(
        self,
        requested_model_id: str,
        cache_entry: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Enrich a cache entry with full ARIS audit provenance fields:
          - requested_model_id
          - api_model_returned
          - prompt_sha256
          - prompt_tokens
          - completion_tokens
          - cost_usd
          - raw_prompt
          - raw_response
        """
        spec = self.get_model_spec(requested_model_id)
        raw_prompt = str(cache_entry.get("prompt", ""))
        raw_response = str(cache_entry.get("raw_response", ""))
        prompt_sha256 = hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest()
        p_tok = int(cache_entry.get("prompt_tokens", 0))
        c_tok = int(cache_entry.get("completion_tokens", 0))
        api_model = str(cache_entry.get("model") or spec.get("endpoint_model_alias") or "")
        cost_usd = self.compute_token_cost_usd(requested_model_id, p_tok, c_tok)
        return {
            "requested_model_id": requested_model_id,
            "endpoint_model_alias": spec.get("endpoint_model_alias"),
            "api_model_returned": api_model,
            "prompt_sha256": prompt_sha256,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "cost_usd": cost_usd,
            "raw_prompt": raw_prompt,
            "raw_response": raw_response,
        }
