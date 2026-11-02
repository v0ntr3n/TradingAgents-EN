"""Consolidated background workers package with lazy submodule attribute resolution."""

import importlib


def __getattr__(name: str):
    try:
        return importlib.import_module(f"app.worker.{name}")
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
