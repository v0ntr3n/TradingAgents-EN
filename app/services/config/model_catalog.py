"""Model catalog loader reading canonical definitions from `configs/models_registry.yaml`."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "configs" / "models_registry.yaml"


def load_model_catalog(registry_path: Path | None = None) -> List[Dict[str, Any]]:
    """Load all model entries from `configs/models_registry.yaml`."""
    target = registry_path or DEFAULT_REGISTRY_PATH
    if not target.exists():
        return []
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    models = list(raw.get("models") or [])
    ama_models = list(raw.get("ama_supplemental_models") or [])
    return models + ama_models


def list_models_by_provider(provider: str, registry_path: Path | None = None) -> List[Dict[str, Any]]:
    """Return catalog entries matching the given provider name."""
    norm = provider.strip().lower()
    return [
        m for m in load_model_catalog(registry_path)
        if str(m.get("provider", "")).strip().lower() == norm
    ]
