"""#include / #define / #pragma once，在词法前运行。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set

_MAX_INCLUDE_DEPTH = 256
_MAX_MACRO_EXPAND = 64

_INCLUDE_RE = re.compile(r"^\s*#include\s+([<\"])([^>\"]+)([>\"])\s*(?://.*)?$")
_DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_]\w*)(?:\s+(.*))?$")
_UNDEF_RE = re.compile(r"^\s*#undef\s+([A-Za-z_]\w*)\s*(?://.*)?$")
_PRAGMA_ONCE_RE = re.compile(r"^\s*#pragma\s+once\s*(?://.*)?$", re.IGNORECASE)


@dataclass
class PreprocessorState:
    macros: Dict[str, str] = field(default_factory=dict)
    pragma_once_done: Set[str] = field(default_factory=set)
    depth: int = 0


def preprocess(text: str, filepath: str | Path | None = None) -> str:
    if filepath is None:
        base = Path.cwd()
        canon = "<stdin>"
    else:
        p = Path(filepath).resolve()
        base = p.parent
        canon = os.path.normcase(str(p))
    if text.startswith("\ufeff"):
        text = text[1:]
    state = PreprocessorState()
    return _preprocess_text(text, canon, base, state)


def _preprocess_text(text: str, virtual_path: str, base_dir: Path, state: PreprocessorState) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        body, trail = _split_line_body_trail(line)
        s = body.lstrip()
        if s.startswith("#"):
            if _PRAGMA_ONCE_RE.match(body):
                continue
            m_inc = _INCLUDE_RE.match(body)
            if m_inc:
                if state.depth >= _MAX_INCLUDE_DEPTH:
                    raise PreprocessorError(f"#include nested too deeply (max {_MAX_INCLUDE_DEPTH})")
                q1, path_part, q2 = m_inc.group(1), m_inc.group(2), m_inc.group(3)
                if q1 != q2:
                    raise PreprocessorError(f"mismatched #include delimiters: {body!r}")
                chunk = _resolve_and_include(path_part.strip(), q1, base_dir, state)
                out.append(chunk)
                continue
            m_def = _DEFINE_RE.match(body)
            if m_def:
                name, repl = m_def.group(1), m_def.group(2)
                if repl is None:
                    repl = ""
                else:
                    repl = _strip_line_comment(repl).rstrip()
                state.macros[name] = repl
                continue
            m_undef = _UNDEF_RE.match(body)
            if m_undef:
                state.macros.pop(m_undef.group(1), None)
                continue
            if re.match(r"^\s*#pragma\b", body):
                raise PreprocessorError(f"unsupported #pragma: {body.strip()}")
            if re.match(r"^\s*#include\b", body):
                raise PreprocessorError(f"malformed #include: {body.strip()}")
            raise PreprocessorError(f"unknown preprocessor directive: {body.strip()}")
        expanded_body = _expand_macros(_strip_line_comment(body), state.macros)
        out.append(expanded_body + trail)
    return "".join(out)


def _split_line_body_trail(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _strip_line_comment(s: str) -> str:
    in_str = False
    escape = False
    i = 0
    while i < len(s) - 1:
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "/" and s[i + 1] == "/":
                return s[:i].rstrip()
        i += 1
    return s


def _expand_macros(line: str, macros: Dict[str, str]) -> str:
    if not macros:
        return line
    cur = line
    for _ in range(_MAX_MACRO_EXPAND):
        nxt = _expand_macros_one_pass(cur, macros)
        if nxt == cur:
            return cur
        cur = nxt
    raise PreprocessorError("macro expansion did not stabilize")


def _expand_macros_one_pass(line: str, macros: Dict[str, str]) -> str:
    in_str = False
    escape = False
    parts: list[str] = []
    i = 0
    n = len(line)
    keys = sorted(macros.keys(), key=len, reverse=True)

    def try_macro_at(j: int) -> tuple[str, int] | None:
        for k in keys:
            if line.startswith(k, j) and (j == 0 or not (line[j - 1].isalnum() or line[j - 1] == "_")):
                end = j + len(k)
                if end < n and (line[end].isalnum() or line[end] == "_"):
                    continue
                return macros[k], end
        return None

    while i < n:
        ch = line[i]
        if in_str:
            parts.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            parts.append(ch)
            i += 1
            continue
        hit = try_macro_at(i)
        if hit:
            rep, new_i = hit
            parts.append(rep)
            i = new_i
            continue
        parts.append(ch)
        i += 1
    return "".join(parts)


def _resolve_and_include(rel: str, include_kind: str, base_dir: Path, state: PreprocessorState) -> str:
    """
    include_kind:
      - '<' : only search Kval/Lib
      - '"' : search current file dir first, then Kval/Lib
    """
    lib = (Path(__file__).resolve().parent.parent.parent / "Lib" / rel).resolve()
    if include_kind == "<":
        cand = lib
        if not cand.is_file():
            raise PreprocessorError(f"#include file not found in Kval/Lib: {rel!r}")
    else:
        cand = (base_dir / rel).resolve()
        if not cand.is_file():
            if lib.is_file():
                cand = lib
            else:
                raise PreprocessorError(f"#include file not found: {rel!r} (cwd={base_dir}, lib=Kval/Lib)")
    key = os.path.normcase(str(cand))
    if key in state.pragma_once_done:
        return ""
    raw = cand.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    once = _file_contains_pragma_once(raw)
    state.depth += 1
    try:
        expanded = _preprocess_text(raw, str(cand), cand.parent, state)
    finally:
        state.depth -= 1
    if once:
        state.pragma_once_done.add(key)
    return expanded


def _file_contains_pragma_once(text: str) -> bool:
    return any(_PRAGMA_ONCE_RE.match(line) for line in text.splitlines())


class PreprocessorError(SyntaxError):
    pass
