"""将 Kval 模块编译为本机可执行文件：生成 .asm，经 NASM 汇编后用链接器链接（不生成 C 中间码）。

支持真正的代码生成：算术、比较、控制流（if/else、while、for）、函数调用。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .aot_exe import AOTExecutableError, AOTToolBootstrapFailed, normalize_aot_executable_output
from .aot_native_codegen import generate_nasm
from .aot_native_static import NativeAOTUnsupported, _assert_module_native_safe
from .aot_platform import platform_tag
from .compiler_env import extra_cflags, extra_ldflags, resolve_cc, resolve_golink, resolve_nasm
from .Parser.AST.asm_ir import AsmContext, flatten_stmt_asm, insns_to_tuple
from .RunTime import Module
from .tools_bootstrap import (
    ToolsBootstrapError,
    ensure_golink_for_native_aot_windows,
    ensure_nasm_for_native_aot_windows,
)


def _emit_nasm_from_module(module: Module, *, win64: bool, macho: bool) -> str:
    """将模块编译为 NASM 汇编源代码。"""
    ctx = AsmContext()
    module_insns = flatten_stmt_asm(module.body.statements, ctx)
    return generate_nasm(insns_to_tuple(module_insns), win64=win64, macho=macho)


def _deps_native_readme(linker: str) -> str:
    return (
        "This executable was built by Kval native AOT (no Python runtime required).\n"
        f"Linker: {linker}\n"
        "Pipeline: Kval AST → ASM IR → NASM .asm → nasm → object → link (gcc/clang or Windows GoLink + msvcrt).\n"
        "Supports: int/str/bool, arithmetic, comparisons, if/else, while, for, function calls.\n"
        "A sibling .asm file is kept next to this executable.\n"
    )


def build_standalone_native_exe(
    *,
    module: Module,
    exe_out: Path,
    keep_sources: bool = False,
) -> Path:
    """生成 .asm → NASM → 链接。先检测工具链，通过后生成真正的本机代码。"""
    exe_out = normalize_aot_executable_output(exe_out).resolve()
    exe_out.parent.mkdir(parents=True, exist_ok=True)

    # 检查工具链
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

    # 安全检查（比之前更宽松：允许 while/for，但仍禁止 class/pointer/try/throw）
    try:
        _assert_module_native_safe(module)
    except NativeAOTUnsupported as e:
        raise AOTExecutableError(
            "本机 AOT 不支持当前程序："
            f"{e}。"
            "可改用默认 AOT（生成调 Python 的 stub）或移除不支持的特性。"
        ) from e

    # 确定平台格式
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

    stem = exe_out.stem
    asm_path = (exe_out.parent / f"{stem}.asm").resolve()
    obj_path = (exe_out.parent / f"{stem}_aot{obj_suffix}").resolve()

    # 生成 NASM 汇编源码
    asm_src = _emit_nasm_from_module(module, win64=win64, macho=macho)
    asm_path.write_text(asm_src, encoding="utf-8")

    # NASM 汇编
    r0 = subprocess.run(
        [nasm, f"-f{nasm_fmt}", "-o", str(obj_path), str(asm_path)],
        capture_output=True,
        text=True,
    )
    if r0.returncode != 0:
        err = (r0.stderr or r0.stdout or "").strip() or "nasm failed"
        if not keep_sources:
            obj_path.unlink(missing_ok=True)
        fail = exe_out.parent / f"{stem}.aot-native-failed-{platform_tag()}.txt"
        fail.write_text(err, encoding="utf-8")
        raise AOTExecutableError(f"本机 AOT：NASM 汇编失败: {err}")

    # 链接
    linker_note: str
    if cc:
        linker_note = cc
        r1 = subprocess.run(
            [cc, "-s", *extra_cflags(), "-o", str(exe_out), str(obj_path), *extra_ldflags()],
            capture_output=True,
            text=True,
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
