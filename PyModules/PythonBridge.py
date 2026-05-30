from __future__ import annotations

from typing import Any


def export(obj: Any):
    """Mark a python symbol as exported to Kval import."""
    setattr(obj, "__kval_export__", True)
    return obj


def module(*, exports: list[str] | tuple[str, ...] | set[str] | None = None):
    """Decorator for module factory style usage."""

    def _wrap(fn):
        setattr(fn, "__kval_export__", True)
        setattr(fn, "__kval_module_exports__", list(exports) if exports is not None else None)
        return fn

    return _wrap


def build_namespace(ns: dict[str, Any], exports: list[str] | tuple[str, ...] | set[str] | None = None) -> dict[str, Any]:
    """Create exported namespace dict for python bridge."""
    out = dict(ns)
    if exports is not None:
        out["__kval_exports__"] = list(exports)
    return out
