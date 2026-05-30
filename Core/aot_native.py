"""将可静态求值的 Kval 模块编译为本机可执行文件：只生成 .asm，经 NASM 汇编后用链接器链接（不生成 C 中间码）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .aot_exe import AOTExecutableError, AOTToolBootstrapFailed, normalize_aot_executable_output
from .aot_native_static import NativeAOTUnsupported, StaticNativeResult, static_eval_module_for_native
from .aot_platform import platform_tag
from .compiler_env import extra_cflags, extra_ldflags, resolve_cc, resolve_golink, resolve_nasm
from .RunTime import Module
from .tools_bootstrap import (
    ToolsBootstrapError,
    ensure_golink_for_native_aot_windows,
    ensure_nasm_for_native_aot_windows,
)


def _asm_db_bytes(s: str) -> str:
    b = s.encode("utf-8") + b"\n\0"
    return ", ".join(str(x) for x in b)


def emit_nasm_main(res: StaticNativeResult, *, win64: bool, macho: bool) -> str:
    """win64: Windows x64 调用约定；macho: macOS 下 C 符号带前导下划线。"""
    ext_pf = "_printf" if macho else "printf"
    entry = "_main" if macho else "main"

    data_lines = ['    fmt_int db "%d",10,0']
    str_i = 0
    for kind, val in res.prints:
        if kind == "str":
            lab = f"str_{str_i}"
            str_i += 1
            data_lines.append(f"    {lab} db {_asm_db_bytes(val)}")

    text_lines: list[str] = [
        "default rel",
        f"extern {ext_pf}",
        "section .data",
        *data_lines,
        "section .text",
        f"global {entry}",
        f"{entry}:",
        "    sub rsp, 40",
    ]

    str_i = 0
    for kind, val in res.prints:
        if kind == "int":
            if win64:
                text_lines.extend(
                    [
                        "    lea rcx, [fmt_int]",
                        f"    mov edx, {int(val)}",
                        "    xor eax, eax",
                        f"    call {ext_pf}",
                    ]
                )
            else:
                text_lines.extend(
                    [
                        "    lea rdi, [fmt_int]",
                        f"    mov esi, {int(val)}",
                        "    xor eax, eax",
                        f"    call {ext_pf}",
                    ]
                )
        elif kind == "str":
            lab = f"str_{str_i}"
            str_i += 1
            if win64:
                text_lines.extend(
                    [
                        f"    lea rcx, [{lab}]",
                        "    xor eax, eax",
                        f"    call {ext_pf}",
                    ]
                )
            else:
                text_lines.extend(
                    [
                        f"    lea rdi, [{lab}]",
                        "    xor eax, eax",
                        f"    call {ext_pf}",
                    ]
                )
        else:
            raise ValueError(kind)

    ret = int(res.exit_code) & 0xFFFFFFFF
    text_lines.extend(
        [
            f"    mov eax, {ret}",
            "    add rsp, 40",
            "    ret",
            "",
        ]
    )

    return "\n".join(text_lines) + "\n"


def _deps_native_readme(linker: str) -> str:
    return (
        "This executable was built by Kval native AOT (no Python runtime required).\n"
        f"Linker: {linker}\n"
        "Pipeline: NASM .asm → nasm → object → link (gcc/clang or Windows GoLink + msvcrt).\n"
        "Only a restricted subset of Kval is supported (statically evaluable Insn VM).\n"
        "A sibling .asm file is kept next to this executable.\n"
    )


def build_standalone_native_exe(
    *,
    module: Module,
    exe_out: Path,
    keep_sources: bool = False,
) -> Path:
    """生成 .asm → NASM → 链接。先检测 NASM / gcc / GoLink（含 Windows 自动安装），通过后再做静态求值。"""
    exe_out = normalize_aot_executable_output(exe_out)
    exe_out.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        try:
            ensure_nasm_for_native_aot_windows()
        except ToolsBootstrapError as e:
            raise AOTToolBootstrapFailed(str(e)) from e

    nasm = resolve_nasm()
    if not nasm:
        raise AOTExecutableError(
            "本机 AOT 需要 NASM：已尝试下载到 Kval/Tools、并搜索 PATH 与常见安装目录，仍未找到 nasm.exe。"
        )

    cc = resolve_cc()
    if sys.platform == "win32" and not cc:
        try:
            ensure_golink_for_native_aot_windows()
        except ToolsBootstrapError as e:
            raise AOTToolBootstrapFailed(str(e)) from e

    golink = resolve_golink() if sys.platform == "win32" else None
    if not cc and not golink:
        raise AOTExecutableError(
            "本机 AOT 需要链接器：已搜索 gcc/clang（PATH、KVAL_CC、常见 MinGW 目录）"
            + ("；在 Windows 上亦已搜索 GoLink（PATH、KVAL_GOLINK、常见目录）。" if sys.platform == "win32" else "。")
        )

    try:
        res = static_eval_module_for_native(module)
    except NativeAOTUnsupported as e:
        raise AOTExecutableError(
            "本机 AOT 不支持当前程序："
            f"{e}。"
            "可改用默认 AOT（生成调 Python 的 stub）或缩小为仅含编译期可折叠的 int/str 与 print/main。"
        ) from e

    stem = exe_out.stem
    asm_path = exe_out.parent / f"{stem}.asm"

    if sys.platform == "win32":
        nasm_fmt = "win64"
        obj_suffix = ".obj"
        win64 = True
        macho = False
    elif sys.platform == "darwin":
        nasm_fmt = "macho64"
        obj_suffix = ".o"
        win64 = False
        macho = True
    else:
        nasm_fmt = "elf64"
        obj_suffix = ".o"
        win64 = False
        macho = False

    asm_path.write_text(emit_nasm_main(res, win64=win64, macho=macho), encoding="utf-8")
    obj_path = exe_out.parent / f"{stem}_aot{obj_suffix}"

    r0 = subprocess.run(
        [nasm, f"-f{nasm_fmt}", "-o", str(obj_path), str(asm_path)],
        capture_output=True,
        text=True,
        cwd=str(exe_out.parent),
    )
    if r0.returncode != 0:
        err = (r0.stderr or r0.stdout or "").strip() or "nasm failed"
        if not keep_sources:
            obj_path.unlink(missing_ok=True)
        fail = exe_out.parent / f"{stem}.aot-native-failed-{platform_tag()}.txt"
        fail.write_text(err, encoding="utf-8")
        raise AOTExecutableError(f"本机 AOT：NASM 汇编失败: {err}")

    linker_note: str
    if cc:
        linker_note = cc
        r1 = subprocess.run(
            [cc, "-s", *extra_cflags(), "-o", str(exe_out), str(obj_path), *extra_ldflags()],
            capture_output=True,
            text=True,
            cwd=str(exe_out.parent),
        )
    else:
        assert golink is not None
        linker_note = golink
        r1 = subprocess.run(
            [
                golink,
                "/fo",
                str(exe_out),
                "/console",
                "/entry",
                "main",
                str(obj_path),
                "msvcrt.dll",
                "kernel32.dll",
            ],
            capture_output=True,
            text=True,
            cwd=str(exe_out.parent),
        )
    if r1.returncode != 0:
        err = (r1.stderr or r1.stdout or "").strip() or "link failed"
        if not keep_sources:
            obj_path.unlink(missing_ok=True)
        fail = exe_out.parent / f"{stem}.aot-native-failed-{platform_tag()}.txt"
        fail.write_text(err, encoding="utf-8")
        raise AOTExecutableError(f"本机 AOT：链接失败 ({linker_note}): {err}")

    if not keep_sources:
        obj_path.unlink(missing_ok=True)

    (exe_out.parent / f"{exe_out.name}.deps.txt").write_text(_deps_native_readme(linker_note), encoding="utf-8")
    return exe_out
