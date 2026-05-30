"""被扩展 LSP 子进程调用：用 Kval Lexer/token 流提取符号（类/结构体/函数/全局变量/类成员）。"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass


@dataclass
class Member:
    name: str
    kind: str  # method|field|ctor
    detail: str
    line: int
    startChar: int


@dataclass
class TypeDecl:
    name: str
    declKind: str  # class|struct
    line: int
    endLine: int
    startChar: int
    members: list[Member]


@dataclass
class Func:
    name: str
    params: str
    returnType: str
    line: int
    startChar: int


@dataclass
class Glob:
    name: str
    typeName: str
    line: int
    startChar: int


@dataclass
class Local:
    name: str
    typeName: str
    line: int
    startChar: int
    scopeStartLine: int
    scopeEndLine: int


@dataclass
class Param:
    name: str
    typeName: str
    line: int
    startChar: int
    scopeStartLine: int
    scopeEndLine: int


def _is_type_token(t: str) -> bool:
    return t in ("INT", "FLOAT", "BOOL", "STRING", "ARRAY", "AUTO", "VOID", "IDENT")


def _tok_text(tok) -> str:
    v = tok.value
    if v is None:
        return ""
    return str(v)


def _collect_params(toks, lp_i: int, rp_i: int) -> str:
    # Best-effort: rebuild textual params from token values.
    parts: list[str] = []
    for t in toks[lp_i + 1 : rp_i]:
        if t.type in ("SEMI", "EOF"):
            break
        if t.type == "COMMA":
            parts.append(", ")
            continue
        if t.type in ("COLCOL", "ARROW"):
            parts.append(_tok_text(t))
            continue
        if t.type in ("LBRACKET", "RBRACKET", "LPAREN", "RPAREN"):
            parts.append(_tok_text(t))
            continue
        if t.type == "STRING_LIT":
            parts.append('"..."')
            continue
        parts.append(_tok_text(t))
        parts.append(" ")
    s = "".join(parts).strip()
    # normalize spaces around commas
    s = " ".join(s.split())
    s = s.replace(" ,", ",")
    return s


def _parse_param_vars(toks, lp_i: int, rp_i: int, scope_start: int, scope_end: int) -> list[Param]:
    out: list[Param] = []
    i = lp_i + 1
    while i < rp_i:
        if toks[i].type in ("COMMA", "SLASH", "STAR", "STARSTAR"):
            i += 1
            continue
        ty = _parse_type_name(toks, i)
        if not ty:
            i += 1
            continue
        tname, j = ty
        if j < rp_i and toks[j].type == "IDENT":
            n_tok = toks[j]
            out.append(
                Param(
                    name=_tok_text(n_tok),
                    typeName=tname,
                    line=n_tok.line - 1,
                    startChar=n_tok.col - 1,
                    scopeStartLine=scope_start,
                    scopeEndLine=scope_end,
                )
            )
            i = j + 1
            continue
        i = j + 1
    return out


def _find_matching(toks, i: int, open_ty: str, close_ty: str) -> int | None:
    depth = 0
    for j in range(i, len(toks)):
        if toks[j].type == open_ty:
            depth += 1
        elif toks[j].type == close_ty:
            depth -= 1
            if depth == 0:
                return j
    return None


def _skip_modifiers(toks, i: int) -> int:
    while i < len(toks) and toks[i].type in ("EXPORT", "STATIC", "CONST", "CONSTEXPR"):
        i += 1
    return i


def _parse_type_name(toks, i: int) -> tuple[str, int] | None:
    if i >= len(toks) or not _is_type_token(toks[i].type):
        return None
    t = toks[i]
    typ = _tok_text(t)
    i += 1
    # pointer/ref suffix in tokens: STAR / AMP
    while i < len(toks) and toks[i].type in ("STAR", "AMP"):
        typ += _tok_text(toks[i])
        i += 1
    return typ, i


def _parse_var_name_with_optional_scope(toks, i: int) -> tuple[str, int] | None:
    # allow `global::x` etc.
    if i >= len(toks):
        return None
    if toks[i].type in ("GLOBAL", "LOCAL", "BUILTINS", "CLOSURE"):
        i += 1
        if i < len(toks) and toks[i].type == "COLCOL":
            i += 1
    if i < len(toks) and toks[i].type == "IDENT":
        name = _tok_text(toks[i])
        return name, i + 1
    return None


def extract_symbols(source: str, virt_path: str) -> dict:
    from Kval.Core.Parser.Lexer import Lexer  # noqa: PLC0415

    # Editor-oriented tokenization: mask preprocessor lines to preserve line/col,
    # but avoid full preprocessing expansion (which may shift columns).
    masked_lines: list[str] = []
    for ln in source.splitlines(True):
        if ln.lstrip().startswith("#"):
            # keep newline, drop the rest to keep following line numbers stable
            masked_lines.append("\n" if ln.endswith(("\n", "\r\n")) else "")
        else:
            masked_lines.append(ln)
    masked = "".join(masked_lines)
    toks = Lexer(masked).tokenize()

    types: list[TypeDecl] = []
    funcs: list[Func] = []
    globs: list[Glob] = []
    locals_: list[Local] = []
    params_: list[Param] = []

    i = 0
    brace_depth = 0
    while i < len(toks):
        i0 = i
        i = _skip_modifiers(toks, i)
        t = toks[i] if i < len(toks) else None

        # Track top-level brace depth so we don't treat locals as globals.
        if t and t.type == "LBRACE":
            brace_depth += 1
            i = i0 + 1
            continue
        if t and t.type == "RBRACE":
            brace_depth = max(0, brace_depth - 1)
            i = i0 + 1
            continue

        # class/struct
        if t and t.type in ("CLASS", "STRUCT"):
            decl_kind = "struct" if t.type == "STRUCT" else "class"
            if i + 1 < len(toks) and toks[i + 1].type == "IDENT":
                name_tok = toks[i + 1]
                # require `{` later
                j = i + 2
                while j < len(toks) and toks[j].type != "LBRACE":
                    if toks[j].type in ("SEMI", "EOF"):
                        break
                    j += 1
                if j < len(toks) and toks[j].type == "LBRACE":
                    close = _find_matching(toks, j, "LBRACE", "RBRACE")
                    if close is not None:
                        members: list[Member] = []
                        k = j + 1
                        # parse members by scanning tokens in body
                        while k < close:
                            k = _skip_modifiers(toks, k)
                            if k >= close or k >= len(toks):
                                break
                            # skip access tags `public:` etc
                            if toks[k].type in ("PUBLIC", "PRIVATE", "PROTECTED", "CODE") and k + 1 < close and toks[k + 1].type == "COLON":
                                k += 2
                                continue
                            ty_parsed = _parse_type_name(toks, k)
                            if not ty_parsed:
                                k += 1
                                continue
                            ret_or_type, k2 = ty_parsed
                            if k2 >= close or toks[k2].type != "IDENT":
                                k = k2 + 1
                                continue
                            mem_name_tok = toks[k2]
                            mem_name = _tok_text(mem_name_tok)
                            k3 = k2 + 1
                            # method/ctor
                            if k3 < close and toks[k3].type == "LPAREN":
                                rp = _find_matching(toks, k3, "LPAREN", "RPAREN")
                                if rp is None or rp >= close:
                                    k = k3 + 1
                                    continue
                                params = _collect_params(toks, k3, rp)
                                kind = "ctor" if mem_name == _tok_text(name_tok) else "method"
                                detail = f"{ret_or_type} {mem_name}({params})"
                                members.append(
                                    Member(
                                        name=mem_name,
                                        kind=kind,
                                        detail=detail,
                                        line=mem_name_tok.line - 1,
                                        startChar=mem_name_tok.col - 1,
                                    )
                                )
                                k = rp + 1
                                continue
                            # field
                            if k3 < close:
                                detail = f"{ret_or_type} {mem_name}"
                                members.append(
                                    Member(
                                        name=mem_name,
                                        kind="field",
                                        detail=detail,
                                        line=mem_name_tok.line - 1,
                                        startChar=mem_name_tok.col - 1,
                                    )
                                )
                            # advance to semicolon or next token
                            while k3 < close and toks[k3].type not in ("SEMI",):
                                if toks[k3].type == "LBRACE":
                                    bc = _find_matching(toks, k3, "LBRACE", "RBRACE")
                                    k3 = (bc + 1) if bc is not None else (k3 + 1)
                                    break
                                k3 += 1
                            k = k3 + 1

                        types.append(
                            TypeDecl(
                                name=_tok_text(name_tok),
                                declKind=decl_kind,
                                line=t.line - 1,
                                endLine=toks[close].line - 1,
                                startChar=t.col - 1,
                                members=members,
                            )
                        )
                        i = close + 1
                        continue

        # function or global var
        # Only collect funcs/globals at top-level.
        if brace_depth != 0:
            i = i0 + 1
            continue

        ty_parsed = _parse_type_name(toks, i)
        if ty_parsed:
            typ, j = ty_parsed
            vn = _parse_var_name_with_optional_scope(toks, j)
            if vn:
                name, k = vn
                # function: name '('
                if k < len(toks) and toks[k].type == "LPAREN":
                    rp = _find_matching(toks, k, "LPAREN", "RPAREN")
                    if rp is not None:
                        params = _collect_params(toks, k, rp)
                        funcs.append(
                            Func(
                                name=name,
                                params=params,
                                returnType=typ,
                                line=toks[k - 1].line - 1,
                                startChar=toks[k - 1].col - 1,
                            )
                        )
                        # If function has a body, capture its scope and collect locals inside.
                        b = rp + 1
                        while b < len(toks) and toks[b].type not in ("LBRACE", "SEMI", "EOF"):
                            b += 1
                        if b < len(toks) and toks[b].type == "LBRACE":
                            be = _find_matching(toks, b, "LBRACE", "RBRACE")
                            if be is not None:
                                scope_start = toks[b].line - 1
                                scope_end = toks[be].line - 1
                                # Scan locals at depth==1 inside body.
                                k2 = b + 1
                                inner_depth = 1
                                # Function parameters belong to this function scope.
                                params_.extend(_parse_param_vars(toks, k, rp, scope_start, scope_end))
                                while k2 < be:
                                    tt = toks[k2]
                                    if tt.type == "LBRACE":
                                        inner_depth += 1
                                        k2 += 1
                                        continue
                                    if tt.type == "RBRACE":
                                        inner_depth = max(0, inner_depth - 1)
                                        k2 += 1
                                        continue
                                    if inner_depth != 1:
                                        k2 += 1
                                        continue
                                    k2 = _skip_modifiers(toks, k2)
                                    if k2 >= be:
                                        break
                                    # local declarations should start at statement boundaries, not expression tails.
                                    if k2 > b + 1:
                                        prev_ty = toks[k2 - 1].type
                                        if prev_ty not in ("LBRACE", "SEMI", "LPAREN", "COLON", "COMMA"):
                                            k2 += 1
                                            continue
                                    ty2 = _parse_type_name(toks, k2)
                                    if not ty2:
                                        k2 += 1
                                        continue
                                    tname, p = ty2
                                    # local var name (do not accept scoped global::)
                                    if p < be and toks[p].type == "IDENT":
                                        n_tok = toks[p]
                                        n = _tok_text(n_tok)
                                        # avoid picking function defs as locals
                                        if p + 1 < be and toks[p + 1].type == "LPAREN":
                                            k2 = p + 1
                                            continue
                                        # skip expression-like IDENT IDENT? no; specifically `return x * x;`
                                        if p + 1 < be and toks[p + 1].type in (
                                            "STAR",
                                            "SLASH",
                                            "PLUS",
                                            "MINUS",
                                            "EQEQ",
                                            "NEQ",
                                            "LT",
                                            "GT",
                                            "LTE",
                                            "GTE",
                                            "AND",
                                            "OR",
                                        ):
                                            k2 = p + 1
                                            continue
                                        locals_.append(
                                            Local(
                                                name=n,
                                                typeName=tname,
                                                line=n_tok.line - 1,
                                                startChar=n_tok.col - 1,
                                                scopeStartLine=scope_start,
                                                scopeEndLine=scope_end,
                                            )
                                        )
                                    # advance to semicolon
                                    while p < be and toks[p].type != "SEMI":
                                        p += 1
                                    k2 = p + 1
                                i = be + 1
                                continue
                        i = rp + 1
                        continue
                # global var: `Type name ... ;`
                # accept declaration or assignment; stop at semicolon
                globs.append(
                    Glob(
                        name=name,
                        typeName=typ,
                        line=toks[k - 1].line - 1,
                        startChar=toks[k - 1].col - 1,
                    )
                )
                # skip to semicolon to avoid repeated matches
                while k < len(toks) and toks[k].type != "SEMI":
                    k += 1
                i = k + 1
                continue

        i = i0 + 1

    return {
        "classes": [asdict(t) for t in types],
        "functions": [asdict(f) for f in funcs],
        "globals": [asdict(g) for g in globs],
        "locals": [asdict(l) for l in locals_],
        "params": [asdict(p) for p in params_],
    }


def main() -> None:
    workspace = os.environ.get("PYTHONPATH", "").strip()
    if workspace:
        sys.path.insert(0, workspace)

    if len(sys.argv) >= 3 and sys.argv[1] == "--stdin":
        source = sys.stdin.read()
        virt = sys.argv[2]
        try:
            out = extract_symbols(source, virt)
        except Exception as e:
            print(f"ERROR:{e}", flush=True)
            sys.exit(2)
        print(json.dumps(out, ensure_ascii=False), flush=True)
        return

    print("USAGE: kval_symbols.py --stdin <virtualPath>", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()

