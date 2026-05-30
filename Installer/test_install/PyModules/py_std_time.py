from __future__ import annotations

import time
from datetime import datetime, timezone

from Kval.PyModules.PythonBridge import export


@export
def unix_time() -> int:
    return int(time.time())


@export
def unix_time_ms() -> int:
    return int(time.time() * 1000)


@export
def iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__kval_exports__ = ["unix_time", "unix_time_ms", "iso_utc_now"]
