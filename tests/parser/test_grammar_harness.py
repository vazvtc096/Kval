from __future__ import annotations

import pytest

from tests.grammar_doc_harness import CASES, _run


@pytest.mark.parametrize(("case_name", "src", "run_eval"), CASES, ids=[c[0] for c in CASES])
def test_grammar_harness_cases(case_name: str, src: str, run_eval: bool) -> None:
    _run(src, run_eval)
