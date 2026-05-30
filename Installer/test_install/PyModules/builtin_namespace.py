from __future__ import annotations


def _kval_print(*args: object) -> None:
    print(*args)


def _kval_input(prompt: str = "") -> str:
    return input(prompt)


def _kval_ord(s: str) -> int:
    if not isinstance(s, str) or len(s) == 0:
        raise TypeError("ord expects non-empty string")
    return ord(s[0])


def _kval_chr(i: int) -> str:
    if not isinstance(i, int):
        raise TypeError("chr expects int")
    return chr(i)


builtin_namespace = {
    "print": _kval_print,
    "input": _kval_input,
    "ord": _kval_ord,
    "chr": _kval_chr,
}