from __future__ import annotations

import pytest
from Kval.Core.Compiler.compiler import CompileOptions, Compiler
from Kval.Core.constants import MAGIC_AST
from Kval.Core.kir_format import decode_kir_payload, is_kir_container
from Kval.Core.Runner.runner import Runner


def test_compiler_writes_versioned_kir_container() -> None:
    compiler = Compiler(CompileOptions(compile_type="AST"))
    module = compiler.compile_source("int main() { return 0; }", filename="<kir-test>")
    binary = compiler.serialize(module)
    payload_magic, payload = decode_kir_payload(binary)

    assert is_kir_container(binary)
    assert payload_magic == MAGIC_AST
    assert payload


def test_runner_can_read_versioned_kir_container() -> None:
    compiler = Compiler(CompileOptions(compile_type="AST"))
    module = compiler.compile_source("int main() { return 7; }", filename="<kir-test>")
    binary = compiler.serialize(module)

    loaded_module = Runner().load_from_bytes(binary, "<kir-test>")
    rc = Runner().run_module(loaded_module, raw_preview=binary)
    assert rc == 7


def test_runner_rejects_tampered_kir_checksum() -> None:
    compiler = Compiler(CompileOptions(compile_type="AST"))
    module = compiler.compile_source("int main() { return 1; }", filename="<kir-test>")
    binary = bytearray(compiler.serialize(module))
    binary[-1] ^= 0x01

    with pytest.raises(ValueError, match="checksum mismatch"):
        Runner().load_from_bytes(bytes(binary), "<kir-test>")
