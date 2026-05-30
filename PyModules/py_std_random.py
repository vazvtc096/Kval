from __future__ import annotations

import secrets
import random

from Kval.PyModules.PythonBridge import export


@export
def rand_secure() -> int:
    return secrets.randbits(31)


@export
def rand_range_secure(lo: int, hi: int) -> int:
    if lo > hi:
        lo, hi = hi, lo
    return random.SystemRandom().randint(lo, hi)


@export
def token_hex(nbytes: int) -> str:
    if nbytes < 1:
        nbytes = 1
    if nbytes > 128:
        nbytes = 128
    return secrets.token_hex(nbytes)


@export
def rand_bool() -> bool:
    return bool(random.SystemRandom().randint(0, 1))


__kval_exports__ = ["rand_secure", "rand_range_secure", "token_hex", "rand_bool"]
