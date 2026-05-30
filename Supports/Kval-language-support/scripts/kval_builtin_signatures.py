"""导出 builtin_namespace 的签名，供扩展动态补全/声明使用。"""
from __future__ import annotations

import inspect
import json
import os
import sys
from typing import Any, get_origin


def _map_ann(ann: Any) -> str:
    if ann in (int, "int"):
        return "int"
    if ann in (float, "float"):
        return "float"
    if ann in (str, "str"):
        return "string"
    if ann in (list, "list"):
        return "array"
    if ann in (type(None), "None", None):
        return "void"
    origin = get_origin(ann)
    if origin in (list, tuple):
        return "array"
    return "object"


def _param_kval_type(param: inspect.Parameter) -> str:
    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return "object"
    if param.kind == inspect.Parameter.VAR_KEYWORD:
        return "object"
    return _map_ann(param.annotation)


def main() -> None:
    py_path = os.environ.get("PYTHONPATH", "").strip()
    if py_path:
        sys.path.insert(0, py_path)
    from Kval.PyModules.builtin_namespace import builtin_namespace  # noqa: PLC0415

    out = []
    for name, fn in builtin_namespace.items():
        if not callable(fn):
            continue
        sig = inspect.signature(fn)
        params = []
        for p in sig.parameters.values():
            params.append(
                {
                    "name": p.name,
                    "kind": p.kind.name,
                    "type": _param_kval_type(p),
                    "has_default": p.default is not inspect._empty,
                }
            )
        ret = _map_ann(sig.return_annotation)
        label_parts = []
        for p in params:
            if p["kind"] == "VAR_POSITIONAL":
                label_parts.append(f"...{p['name']}")
            elif p["kind"] == "VAR_KEYWORD":
                label_parts.append(f"**{p['name']}")
            else:
                label_parts.append(f"{p['type']} {p['name']}")
        out.append(
            {
                "name": name,
                "returnType": ret,
                "params": params,
                "signature": f"{ret} {name}({', '.join(label_parts)})",
            }
        )
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

