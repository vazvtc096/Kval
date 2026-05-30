from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .Core.Compiler import CompileOptions, Compiler
from .Core.aot_exe import AOTExecutableError, AOTToolBootstrapFailed
from .Core.tools_bootstrap import print_aot_tool_bootstrap_warning
from .Core.Runner import RunOptions, Runner


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

    p_run = sub.add_parser("run", help="加载 .kval 源码或带魔数的二进制并执行")
    p_run.add_argument("path", help="源文件或编译产物路径")
    p_run.add_argument(
        "--run-type",
        choices=("AST", "RPN", "JIT"),
        default="AST",
        help="AST=树遍历；RPN=栈式 IR；JIT=边解释边执行（禁用 InsnVM，全程 evaluate）",
    )
    p_run.add_argument(
        "--skip-error",
        action="store_true",
        help="未绑定名在部分路径保留 Unbound（实验性）",
    )

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
            "  KVAL_NASM / KVAL_GOLINK 可覆盖；另会搜索 PATH 与常见安装目录"
        ),
    )
    p_comp.add_argument("input", help="输入 .kval 路径")
    p_comp.add_argument(
        "-o",
        "--output",
        metavar="OUT",
        help="输出路径；省略则 AST/RPN 写为与输入同主文件名的 .kir，AOT 写为同主文件名的可执行文件（Windows 为 .exe）",
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

        if args.cmd == "run":
            r = Runner(
                RunOptions(
                    run_type=args.run_type,
                    skip_unbound_errors=args.skip_error,
                )
            )
            return r.run_file(args.path)

        if args.cmd == "asm":
            comp = Compiler(CompileOptions(compile_type=args.compile_type))
            mod = comp.compile_file(args.input)
            print(comp.asm_text(mod))
            return 0

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
