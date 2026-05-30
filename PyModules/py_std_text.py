from __future__ import annotations

from Kval.PyModules.PythonBridge import export


@export
def normalize_slashes(path: str) -> str:
    return path.replace("\\", "/")


@export
def to_lower(s: str) -> str:
    return s.lower()


@export
def to_upper(s: str) -> str:
    return s.upper()


@export
def starts_with(s: str, prefix: str) -> bool:
    return s.startswith(prefix)


@export
def ends_with(s: str, suffix: str) -> bool:
    return s.endswith(suffix)


__kval_exports__ = [
    "normalize_slashes",
    "to_lower",
    "to_upper",
    "starts_with",
    "ends_with",
]
