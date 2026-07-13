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


def _emit_nasm_from_module(module: Module, *, win64: bool, macho: bool, output_type: str = "exe") -> str:
    """将模块编译为 NASM 汇编源代码。"""
    ctx = AsmContext()
    module_insns = flatten_stmt_asm(module.body.statements, ctx)
    return generate_nasm(
        insns_to_tuple(module_insns),
        win64=win64,
        macho=macho,
        output_type=output_type,
        export_names=module.export_names_marked,
    )


def _collect_extern_dlls_from_module(module: Module) -> dict[str, list[str]]:
    """从模块中收集所有 extern DLL 声明，返回 {dll_path: [func_names]}。"""
    from .Parser.AST.ASE import ExternDllDeclNode
    result: dict[str, list[str]] = {}
    for s in module.body.statements:
        if isinstance(s, ExternDllDeclNode):
            result.setdefault(s.dll_path, []).extend(func[1] for func in s.funcs)
    return result


def _deps_native_readme(linker: str, output_type: str = "exe") -> str:
    kind = "DLL" if output_type == "dll" else "executable"
    extra = ""
    if output_type == "dll":
        extra = (
            "Exports:\n"
            "  DllMain    — Windows DLL entry point (returns TRUE)\n"
            "  kval_main  — int kval_main(void); calls the Kval main() and returns its exit code\n"
        )
    return (
        f"This {kind} was built by Kval native AOT (no Python runtime required).\n"
        f"Linker: {linker}\n"
        "Pipeline: Kval AST → ASM IR → NASM .asm → nasm → object → link (gcc/clang or Windows GoLink + msvcrt).\n"
        "Supports: int/str/bool, arithmetic, comparisons, if/else, while, for, function calls.\n"
        f"{'A sibling .asm file is kept next to this ' + kind + '.\n'}"
        f"{extra}"
    )


def build_standalone_native_exe(
    *,
    module: Module,
    exe_out: Path,
    keep_sources: bool = False,
    output_type: str = "exe",
) -> Path:
    """生成 .asm → NASM → 链接。

    output_type:
      "exe" — 生成可执行文件 (.exe / ELF)
      "dll" — 生成动态链接库 (.dll / .so), 导出 DllMain + kval_main
    """
    if output_type not in ("exe", "dll"):
        raise ValueError(f"output_type must be 'exe' or 'dll', got {output_type!r}")

    exe_out = normalize_aot_executable_output(exe_out, output_type).resolve()
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
    asm_src = _emit_nasm_from_module(module, win64=win64, macho=macho, output_type=output_type)
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

    # 收集 extern DLL 声明，用于自动链接 .lib
    extern_dlls = _collect_extern_dlls_from_module(module)

    # 链接
    linker_note: str
    if cc:
        linker_note = cc
        # 自动构建 extern DLL 的 .lib 链接参数
        extern_lib_args: list[str] = []
        if extern_dlls and sys.platform == "win32":
            import shutil as _sh
            dlltool = _sh.which("dlltool") or "dlltool"
            for dll_path, func_names in extern_dlls.items():
                # 从 DLL 名称推导 lib 名称
                dll_basename = Path(dll_path).stem
                # 尝试查找 DLL 文件并生成 .lib（如果尚未存在）
                # 搜索路径：当前输出目录、源文件目录、PATH、Windows 系统目录
                dll_search_paths = [
                    exe_out.parent,
                    Path.cwd(),
                ]
                # 添加系统 DLL 目录
                import os
                sys_dirs = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep)]
                dll_search_paths.extend(sys_dirs)
                # Windows 系统目录
                for sys_dir in ("C:\\Windows\\System32", "C:\\Windows\\SysWOW64"):
                    if Path(sys_dir).exists():
                        dll_search_paths.append(Path(sys_dir))

                dll_found = False
                for search_dir in dll_search_paths:
                    candidate = search_dir / dll_path
                    if candidate.exists():
                        dll_found = True
                        break
                    # 也尝试带完整路径的
                    candidate2 = search_dir / f"{dll_basename}.dll"
                    if candidate2.exists():
                        dll_found = True
                        dll_path = str(candidate2)
                        break

                if dll_found:
                    # 生成 .def 文件和 .lib 导入库
                    def_content = f"LIBRARY {dll_basename}\nEXPORTS\n"
                    for fn in func_names:
                        def_content += f"    {fn}\n"
                    def_path = exe_out.parent / f"{dll_basename}_extern.def"
                    lib_path = exe_out.parent / f"{dll_basename}_extern.lib"
                    def_path.write_text(def_content, encoding="utf-8")
                    try:
                        r_def = subprocess.run(
                            [dlltool, "-d", str(def_path), "-D", dll_path, "-l", str(lib_path)],
                            capture_output=True, text=True,
                        )
                        if r_def.returncode == 0:
                            extern_lib_args.append(str(lib_path))
                        else:
                            # dlltool 失败，尝试直接链接 DLL
                            extern_lib_args.append(f"-l{dll_basename}")
                    except FileNotFoundError:
                        extern_lib_args.append(f"-l{dll_basename}")
                    # 清理临时 .def 文件
                    if not keep_sources:
                        def_path.unlink(missing_ok=True)
                else:
                    # DLL 未找到，尝试用 -l 选项直接链接（依赖系统搜索路径）
                    extern_lib_args.append(f"-l{dll_basename}")
        linker_note = cc
        if output_type == "dll":
            # DLL 模式: gcc -shared + 生成 .lib 导入库
            lib_path = exe_out.parent / f"{stem}.lib"
            # 生成 .def 文件供 dlltool 创建正式的导入库
            def_path = exe_out.parent / f"{stem}.def"
            def_path.write_text(
                f"LIBRARY {stem}\n"
                f"EXPORTS\n"
                f"    kval_main\n"
                f"    DllMain\n",
                encoding="utf-8",
            )
            r1 = subprocess.run(
                [cc, "-shared", "-s",
                 *extra_cflags(),
                 "-o", str(exe_out), str(obj_path),
                 f"-Wl,--out-implib,{lib_path}",
                 "-lmsvcrt", "-lkernel32",
                 *extern_lib_args,
                 *extra_ldflags()],
                capture_output=True,
                text=True,
            )
            # DLL 编译成功后, 用 dlltool 重新生成干净的 .lib
            if r1.returncode == 0:
                import shutil as _sh
                dlltool = _sh.which("dlltool") or "dlltool"
                try:
                    subprocess.run(
                        [dlltool, "-d", str(def_path),
                         "-D", str(exe_out),
                         "-l", str(lib_path)],
                        capture_output=True, text=True,
                    )
                except FileNotFoundError:
                    pass  # dlltool 不可用, 保留 gcc 生成的 .lib
        else:
            r1 = subprocess.run(
                [cc, "-s", *extra_cflags(), "-o", str(exe_out), str(obj_path), *extern_lib_args, *extra_ldflags()],
                capture_output=True,
                text=True,
            )
    else:
        assert golink is not None
        linker_note = golink
        # 为 GoLink 添加 extern DLL 名称
        golink_dll_args: list[str] = []
        if extern_dlls and sys.platform == "win32":
            for dll_path in extern_dlls:
                dll_basename = Path(dll_path).stem
                golink_dll_args.append(f"{dll_basename}.dll")
        if output_type == "dll":
            # GoLink DLL 模式
            r1 = subprocess.run(
                [
                    golink,
                    "/dll",
                    "/fo",
                    str(exe_out),
                    str(obj_path),
                    "msvcrt.dll",
                    "kernel32.dll",
                    *golink_dll_args,
                ],
                capture_output=True,
                text=True,
            )
        else:
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
                    *golink_dll_args,
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

    (exe_out.parent / f"{exe_out.name}.deps.txt").write_text(
        _deps_native_readme(linker_note, output_type), encoding="utf-8")
    return exe_out
