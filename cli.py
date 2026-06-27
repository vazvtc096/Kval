from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .Core.Compiler import CompileOptions, Compiler
from .Core.aot_exe import AOTExecutableError, AOTToolBootstrapFailed
from .Core.tools_bootstrap import print_aot_tool_bootstrap_warning
from .Core.Runner import RunOptions, Runner


def _find_kval_vm() -> Path | None:
    """查找 C VM (kval_vm.exe / kval_vm) 可执行文件。

    搜索顺序:
      1. Kval/VM_C/ 目录下（项目自带）
      2. PATH 环境变量中
      3. KVAL_VM 环境变量指定
    """
    # 环境变量覆盖
    env_vm = sys.platform == "win32"
    env_path = Path(shutil.which("kval_vm" + (".exe" if env_vm else ""))) if shutil.which("kval_vm" + (".exe" if env_vm else "")) else None

    # KVAL_VM 环境变量
    kval_vm_env = os.environ.get("KVAL_VM")
    if kval_vm_env:
        p = Path(kval_vm_env)
        if p.exists():
            return p

    # 项目自带
    try:
        import Kval as _kv
        vm_dir = Path(_kv.__file__).parent / "VM_C"
        if sys.platform == "win32":
            exe = vm_dir / "kval_vm.exe"
        else:
            exe = vm_dir / "kval_vm"
        if exe.exists():
            return exe
    except Exception:
        pass

    # PATH 搜索
    name = "kval_vm.exe" if sys.platform == "win32" else "kval_vm"
    found = shutil.which(name)
    if found:
        return Path(found)

    return None


def _run_kir3_with_c_vm(kir3_path: str, vm_exe: Path) -> int:
    """用 C VM 执行 .kir3 文件，返回退出码。"""
    try:
        result = subprocess.run(
            [str(vm_exe), kir3_path],
            capture_output=False,
        )
        return result.returncode
    except FileNotFoundError:
        print(f"Kval KIR3: C VM 找不到: {vm_exe}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Kval KIR3: 执行出错: {e}", file=sys.stderr)
        return 1


import os

def _maybe_legacy_run_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    first = argv[0]
    if first in ("compile", "run", "asm", "-h", "--help", "-V", "--version"):
        return argv
    if first.startswith("-"):
        return argv
    if Path(first).is_file():
        return ["run", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = _maybe_legacy_run_argv(argv)

    root = argparse.ArgumentParser(
        prog="kval",
        description="Kval：Compiler（解析/产物）与 Runner（加载/执行）统一入口。",
    )
    root.add_argument("-V", "--version", action="version", version="Kval (dev)")
    sub = root.add_subparsers(dest="cmd", metavar="COMMAND")

    # ─── run ───
    p_run = sub.add_parser("run", help="加载 .kval 源码或带魔数的二进制并执行")
    p_run.add_argument("path", help="源文件或编译产物路径")
    p_run.add_argument(
        "--run-type",
        choices=("AST", "RPN", "JIT", "KIR3"),
        default="AST",
        help="AST=树遍历；RPN=栈式 IR；JIT=边解释边执行；KIR3=C VM 执行 .kir3 二进制",
    )
    p_run.add_argument(
        "--skip-error",
        action="store_true",
        help="未绑定名在部分路径保留 Unbound（实验性）",
    )

    # ─── compile ───
    p_comp = sub.add_parser(
        "compile",
        help="将 .kval 源码编译为 Module 并可写出二进制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "AOT 环境变量：\n"
            "  KVAL_CC          C 编译器（路径或 PATH 名），未设则自动找 gcc/cc/clang\n"
            "  KVAL_CFLAGS      追加编译参数（空格分隔）\n"
            "  KVAL_LDFLAGS     追加链接参数（空格分隔）\n"
            "  KVAL_PYTHON      运行已生成的 stub 时使用的解释器（stub 内 getenv；未设则 python / python3）\n"
            "本机 AOT（--aot-native）：只生成 .asm，经 NASM 汇编后链接（不生成 C 中间码）\n"
            "  Windows：无 NASM/GoLink 时自动下载到 Kval/Tools（NASM 来自 nasm.us；GoLink 若被官网拦截则见 Tools/golink/README.txt）\n"
            "  KVAL_NASM / KVAL_GOLINK 可覆盖；另会搜索 PATH 与常见安装目录\n"
            "KIR3（--kir3）：生成 C VM 可读的二进制字节码（.kir3），由 kval_vm 执行\n"
            "  KVAL_VM          C VM 可执行文件路径（未设则自动搜索 Kval/VM_C/ 和 PATH）"
        ),
    )
    p_comp.add_argument("input", help="输入 .kval 路径")
    p_comp.add_argument(
        "-o",
        "--output",
        metavar="OUT",
        help="输出路径；省略则按类型自动推断（AST/RPN→.kir，AOT→.exe，KIR3→.kir3）",
    )
    p_comp.add_argument(
        "--compile-type",
        choices=("AST", "RPN", "AOT"),
        default="AST",
        help="AST/RPN 写魔数+pickle；AOT 生成本机 stub（见 KVAL_CC 等），-o 为 .exe/程序名，同目录写 .kbin",
    )
    p_comp.add_argument(
        "--dump-asm",
        action="store_true",
        help="打印栈式 IR；省略 -o 时不写文件",
    )
    p_comp.add_argument(
        "--generate-ir",
        action="store_true",
        help="预留，当前仅提示未实现",
    )
    p_comp.add_argument(
        "--aot-keep-c",
        action="store_true",
        help="stub 保留 *_aot_launcher.c；本机 AOT 默认已保留同名 .asm，勾选则额外保留汇编产生的 .obj/.o",
    )
    p_comp.add_argument(
        "--aot-native",
        action="store_true",
        help="与 --compile-type AOT 合用：生成不依赖 Python 的本机 exe/ELF（仅支持可静态求值子集）；省略则仍为 stub + .kbin",
    )
    p_comp.add_argument(
        "--kir3",
        action="store_true",
        help="输出 .kir3 格式（C VM 字节码），由 kval_vm 执行",
    )

    # ─── asm ───
    p_asm = sub.add_parser("asm", help="等同 compile --dump-asm")
    p_asm.add_argument("input", help="输入 .kval 路径")
    p_asm.add_argument(
        "--compile-type",
        choices=("AST", "RPN", "AOT"),
        default="AST",
        help="解析用（不影响 asm 文本）",
    )

    args = root.parse_args(argv)

    try:
        if args.cmd is None:
            root.print_help()
            return 1

        # ─── run ───
        if args.cmd == "run":
            # KIR3 运行模式：直接调用 C VM
            if args.run_type == "KIR3":
                vm_exe = _find_kval_vm()
                if vm_exe is None:
                    print("Kval KIR3: 找不到 kval_vm（搜索了 Kval/VM_C/ 和 PATH）。", file=sys.stderr)
                    print("  设置 KVAL_VM 环境变量指定路径，或将 kval_vm 编译后放入 PATH。", file=sys.stderr)
                    return 1
                return _run_kir3_with_c_vm(args.path, vm_exe)

            r = Runner(
                RunOptions(
                    run_type=args.run_type,
                    skip_unbound_errors=args.skip_error,
                )
            )
            return r.run_file(args.path)

        # ─── asm ───
        if args.cmd == "asm":
            comp = Compiler(CompileOptions(compile_type=args.compile_type))
            mod = comp.compile_file(args.input)
            print(comp.asm_text(mod))
            return 0

        # ─── compile ───
        if args.cmd == "compile":
            if args.aot_native and args.compile_type != "AOT":
                print("Kval: --aot-native 仅在与 --compile-type AOT 合用时有效。", file=sys.stderr)
                return 1
            if args.generate_ir:
                print("Kval: --generate-ir 尚未实现。", file=sys.stderr)

            comp = Compiler(CompileOptions(compile_type=args.compile_type))
            mod = comp.compile_file(args.input)
            if args.dump_asm:
                print(comp.asm_text(mod))

            # ── KIR3 输出 ──
            if args.kir3:
                from .Core.kir3_format import emit_kir3
                from .Core.Parser.AST.asm_ir import AsmContext

                ctx = AsmContext()
                insns = mod.body.asm(ctx)
                kir3_bytes = emit_kir3(insns)

                out_path = args.output
                if out_path is None:
                    out_path = str(Path(args.input).with_suffix(".kir3"))

                Path(out_path).write_bytes(kir3_bytes)
                print(out_path)
                return 0

            out_path = args.output
            if out_path is None and not args.dump_asm:
                inp = Path(args.input)
                if args.compile_type == "AOT":
                    out_path = str(inp.with_suffix(".exe") if sys.platform == "win32" else inp.parent / inp.stem)
                else:
                    out_path = str(inp.with_suffix(".kir"))

            if out_path:
                if args.compile_type == "AOT":
                    try:
                        exe = comp.write_aot_bundle(
                            mod,
                            out_path,
                            keep_launcher_c=args.aot_keep_c,
                            native_executable=args.aot_native,
                        )
                        print(exe)
                    except AOTToolBootstrapFailed as e:
                        print_aot_tool_bootstrap_warning(str(e))
                        return 1
                    except AOTExecutableError as e:
                        print(f"AOT: {e}", file=sys.stderr)
                        return 1
                else:
                    comp.write_binary(mod, out_path)

                return 0

            return 0

        return 1
    except BaseException as e:
        # 兜底：避免 Python traceback 泄漏到终端，使用 Runner 的统一渲染格式
        try:
            Runner()._print_error(e)
        except Exception:
            print(f"Traceback (most recent call last):\n{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
