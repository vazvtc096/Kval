from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

from ..aot_exe import build_native_stub_exe
from ..constants import MAGIC_AST, MAGIC_RPN
from ..kir_format import encode_kir_payload
from ..Parser.Parser import Parser
from ..RunTime import Module


@dataclass
class CompileOptions:
    compile_type: str = "AST"


class Compiler:
    def __init__(self, options: CompileOptions | None = None):
        self.options = options or CompileOptions()

    def compile_source(self, text: str, filename: str | None = None) -> Module:
        return Parser.parse_source(text, filename=filename)

    def compile_file(self, path: str | Path) -> Module:
        p = Path(path)
        return self.compile_source(p.read_text(encoding="utf-8"), str(p.resolve()))

    def magic_byte(self) -> int:
        t = self.options.compile_type
        if t == "RPN":
            return MAGIC_RPN
        return MAGIC_AST

    def serialize(self, module: Module) -> bytes:
        payload = pickle.dumps(module, protocol=pickle.HIGHEST_PROTOCOL)
        return encode_kir_payload(self.magic_byte(), payload)

    def write_binary(self, module: Module, out: str | Path) -> None:
        Path(out).write_bytes(self.serialize(module))

    def write_aot_bundle(
        self,
        module: Module,
        out: str | Path,
        *,
        keep_launcher_c: bool = False,
        native_executable: bool = False,
        output_type: str = "exe",
    ) -> Path:
        if native_executable:
            from ..aot_native import build_standalone_native_exe

            return build_standalone_native_exe(
                module=module,
                exe_out=Path(out),
                keep_sources=keep_launcher_c,
                output_type=output_type,
            )
        return build_native_stub_exe(
            kbin_bytes=self.serialize(module),
            exe_out=Path(out),
            keep_launcher_c=keep_launcher_c,
        )

    def asm_text(self, module: Module) -> str:
        return module.asm_text()
