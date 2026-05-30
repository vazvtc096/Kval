from __future__ import annotations

import pytest
from Kval.Core.Parser.Parser import ParseError, Parser


def test_parser_accepts_valid_program() -> None:
    src = "int main() { int x = 1; x += 2; return x; }"
    mod = Parser.parse_source(src, filename="<parser-test>")
    assert mod is not None
    assert mod.body is not None


def test_parser_rejects_syntax_error() -> None:
    src = "int main( { return 0; }"
    with pytest.raises(ParseError):
        Parser.parse_source(src, filename="<parser-test>")
