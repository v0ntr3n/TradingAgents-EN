"""Versioned YAML prompt loader (`prompts/loader.py`)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict
import yaml

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def load_prompt_yaml(filename: str) -> Dict[str, Any]:
    """Load and cache a YAML prompt catalog from the `prompts/` directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
