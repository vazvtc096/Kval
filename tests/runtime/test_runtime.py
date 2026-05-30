from __future__ import annotations

from Kval.Core.Parser.Parser import Parser
from Kval.Core.Runner.runner import Runner, RunOptions


def test_runner_executes_main_and_returns_code() -> None:
    src = "int main() { int n = 40; n += 2; return n; }"
    mod = Parser.parse_source(src, filename="<runtime-test>")
    rc = Runner(RunOptions(run_type="AST")).run_module(mod)
    assert rc == 42
