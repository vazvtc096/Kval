from __future__ import annotations

import pickle
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import RunTime
from .. import common as common_mod
from ..constants import MAGIC_AST, MAGIC_RPN
from ..Errors import RunTimeErrors as KRTE
from ..Errors.BaseErrors import Exceptions
from ..kir_format import decode_kir_payload, is_kir_container
from ..Parser.Parser import Parser
from ..RunTime import Module
from ..VM import VM


@dataclass
class RunOptions:
    run_type: str = "AST"
    skip_unbound_errors: bool = False


class Runner:
    def __init__(self, options: RunOptions | None = None):
        self.options = options or RunOptions()

    def apply_runtime_flags(self) -> None:
        common_mod.skip_unbound_errors = self.options.skip_unbound_errors

    @staticmethod
    def _detect_binary_magic(raw: bytes) -> int | None:
        if not raw:
            return None
        if is_kir_container(raw):
            payload_magic, _ = decode_kir_payload(raw)
            return payload_magic
        if raw[0] in (MAGIC_AST, MAGIC_RPN):
            return raw[0]
        return None

    def load_from_bytes(self, raw: bytes, path: str | None = None) -> Module:
        if not raw:
            raise ValueError("empty file")
        if is_kir_container(raw):
            _, payload = decode_kir_payload(raw)
            return pickle.loads(payload)
        magic = raw[0]
        payload = raw[1:]
        if magic == MAGIC_AST or magic == MAGIC_RPN:
            # Backward compatibility for legacy one-byte magic format.
            return pickle.loads(payload)
        return Parser.parse_source(raw.decode("utf-8"), filename=path)

    def load_file(self, path: str | Path) -> Module:
        p = Path(path)
        return self.load_from_bytes(p.read_bytes(), str(p.resolve()))

    def configure_vm(self, raw_first_byte: int | None) -> None:
        use_rpn = self.options.run_type == "RPN"
        if raw_first_byte is not None and raw_first_byte == MAGIC_RPN:
            use_rpn = True
        if self.options.run_type == "JIT":
            use_rpn = False
        if use_rpn:
            VM.set_runner(VM.RunningMode.bytecode)
        else:
            VM.set_runner(VM.RunningMode.ast)

    def run_module(self, module: Module, raw_preview: bytes | None = None) -> int:
        self.apply_runtime_flags()
        prev_jit = RunTime.jit_mode
        try:
            RunTime.jit_mode = self.options.run_type == "JIT"
            binary_magic = self._detect_binary_magic(raw_preview) if raw_preview else None
            self.configure_vm(binary_magic)
            rc = VM.run(module)
        except BaseException as e:
            self._print_error(e)
            return 1
        finally:
            RunTime.jit_mode = prev_jit
        if rc is None:
            return 0
        if isinstance(rc, int):
            return int(rc) & 255
        return 0

    def run_file(self, path: str | Path) -> int:
        try:
            p = Path(path)
            raw = p.read_bytes()
            mod = self.load_from_bytes(raw, str(p.resolve()))
            return self.run_module(mod, raw_preview=raw)
        except BaseException as e:
            try:
                e._kval_origin_file = str(Path(path).resolve())
            except Exception:
                pass
            self._print_error(e)
            return 1

    def _wrap_runtime_error(self, e: BaseException) -> Exceptions:
        if isinstance(e, Exceptions):
            return e
        if isinstance(e, TypeError):
            return KRTE.TypeError(str(e), cause=e)
        if isinstance(e, ValueError):
            return KRTE.ValueError(str(e), cause=e)
        if isinstance(e, NameError):
            return KRTE.NameError(str(e), cause=e)
        if isinstance(e, IndexError):
            return KRTE.IndexError(str(e), cause=e)
        if isinstance(e, KeyError):
            return KRTE.KeyError(str(e), cause=e)
        if isinstance(e, PermissionError):
            return KRTE.PermissionError(str(e), cause=e)
        if isinstance(e, ZeroDivisionError):
            return KRTE.ZeroDivisionError(str(e), cause=e)
        if isinstance(e, ImportError):
            return KRTE.ImportError(str(e), cause=e)
        return KRTE.RunTimeError(str(e), cause=e)

    def _print_error(self, e: BaseException) -> None:
        # 解析/静态阶段错误：保留原异常名（如 ParseError），但统一用 Kval 的 traceback 格式输出
        if isinstance(e, Exceptions):
            err: Exceptions = e
            err_name = type(e).__name__
            err_msg = e.error_message() or ""
        elif isinstance(e, SyntaxError):
            err = self._wrap_runtime_error(e)
            err_name = type(e).__name__
            err_msg = str(e)
        else:
            err = self._wrap_runtime_error(e)
            err_name = type(err).__name__
            err_msg = err.error_message() or ""

        frames = getattr(e, "_kval_stack_snapshot", None)
        if not frames:
            frames = RunTime.capture_call_stack()

        print("Traceback (most recent call last):", file=sys.stderr)
        if not frames:
            origin = getattr(e, "_kval_origin_file", None)
            msg = str(e)
            m = re.search(r"at\s+(\d+):(\d+)", msg)
            if not m:
                m = re.search(r"at\s+(\d+)", msg)
            lineon = int(m.group(1)) if m else 0
            code = ""
            if origin and lineon > 0:
                try:
                    lines = Path(origin).read_text(encoding="utf-8").splitlines()
                    if 1 <= lineon <= len(lines):
                        code = lines[lineon - 1]
                except Exception:
                    code = ""
            file = origin or "<memory>"
            print(f"  File: {file}, Lineon: {lineon}, In <module>:", file=sys.stderr)
            if code:
                print(f"      {code}", file=sys.stderr)
            else:
                print("      ", file=sys.stderr)
            print(f"{err_name}: {err_msg}", file=sys.stderr)
            return
        for sf in frames:
            file = sf.filename or "<memory>"
            lineon = int(getattr(sf, "lineon", 0) or 0)
            func = sf.funcname or "<module>"
            code = ""
            try:
                if (
                    sf.module is not None
                    and sf.module.lines
                    and 1 <= lineon <= len(sf.module.lines)
                ):
                    code = sf.module.lines[lineon - 1].rstrip("\n")
                elif getattr(sf, "code", None) and 1 <= lineon <= len(sf.code):
                    code = sf.code[lineon - 1].rstrip("\n")
            except Exception:
                code = ""
            print(f"  File: {file}, Lineon: {lineon}, In {func}:", file=sys.stderr)
            if code:
                print(f"      {code}", file=sys.stderr)
            else:
                print("      ", file=sys.stderr)

        print(f"{err_name}: {err_msg}", file=sys.stderr)
