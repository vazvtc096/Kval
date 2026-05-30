from __future__ import annotations

from Kval.PyModules.PythonBridge import export


@export
def bit_and(a: int, b: int) -> int:
    return a & b


@export
def bit_or(a: int, b: int) -> int:
    return a | b


@export
def bit_xor(a: int, b: int) -> int:
    return a ^ b


@export
def bit_not(a: int) -> int:
    return ~a


@export
def shl(a: int, n: int) -> int:
    return a << n


@export
def shr(a: int, n: int) -> int:
    return a >> n


@export
def popcount(a: int) -> int:
    if a < 0:
        a = -a
    return int(a).bit_count()


__kval_exports__ = [
    "bit_and",
    "bit_or",
    "bit_xor",
    "bit_not",
    "shl",
    "shr",
    "popcount",
]
