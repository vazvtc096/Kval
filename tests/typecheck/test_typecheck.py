from __future__ import annotations

import pytest
from Kval.Core.Parser.Parser import ParseError, Parser


def test_typecheck_accepts_matching_assignment() -> None:
    src = "int main() { int a = 1; a = 2; return a; }"
    mod = Parser.parse_source(src, filename="<typecheck-test>")
    assert mod is not None


def test_typecheck_rejects_mismatched_assignment() -> None:
    src = 'int main() { int a = 1; a = "oops"; return 0; }'
    with pytest.raises(ParseError):
        Parser.parse_source(src, filename="<typecheck-test>")
