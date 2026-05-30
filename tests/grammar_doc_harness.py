"""按 Grammar(zh-cn) 对已实现子集做冒烟测试；失败则打印源码与异常。"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Kval.Core.Parser.Parser import Parser  # noqa: E402
from Kval.Core.VM.VM import RunningMode, set_runner  # noqa: E402


def _run(src: str, run_eval: bool) -> None:
    m = Parser.parse_source(src, filename="<harness>")
    if run_eval:
        set_runner(RunningMode.ast)
        m.evaluate()


CASES: list[tuple[str, str, bool]] = [
    ("comments_line", "int main() { int x; // c\n x = 1; return x; }", True),
    ("comments_block", "int main() { /* a */ int x = 1; return x; }", True),
    ("delete", "int main() { int a = 1; delete a; return 0; }", True),
    ("string_var", 'int main() { string s = "ab"; s += "c"; return 1; }', True),
    ("compound_int", "int main() { int x = 10; x += 2; x -= 1; x *= 2; x /= 3; return x; }", True),
    ("compound_shift", "int main() { int x = 8; x <<= 1; x >>= 2; return x; }", True),
    (
        "scoped_compound",
        "int global::g = 1;\nint main() { global::g += 2; return global::g; }",
        True,
    ),
    (
        "varscopeorder_single",
        "int global::z = 5;\nint main() { varScopeOrder z: global; return z; }",
        True,
    ),
    (
        "varscopeorder_chain",
        "int local::a = 3;\nint main() { varScopeOrder x: (local -> global); return 0; }",
        True,
    ),
    ("kwargs_call", "void f(int a) {}\nint main() { f(a=1); return 0; }", True),
    ("slash_params", "void g(int a, /, int b) {}\nint main() { g(1, 2); return 0; }", True),
    (
        "starstar_kwonly",
        "void h(int a, int b, **kwargs) {}\nint main() { h(1, 2); return 0; }",
        True,
    ),
    (
        "class_code",
        """class C {
  code:
  int x = 0;
}
int main() { return 0; }
""",
        True,
    ),
    (
        "class_access",
        """class D {
  public:
  int v;
  code:
  int x = 0;
}
int main() { return 0; }
""",
        True,
    ),
    ("logic_ops", "int main() { int a = 1; return (!0 && a) || 0; }", True),
    ("for_empty_parts", "int main() { for (;;) { break; } return 0; }", True),
    ("this_expr", "class E { code: void m() { int x = 1; } }\nint main() { return 0; }", True),
    ("preprocessor_define", "#define ANS 9\nint main() { return ANS; }", True),
    ("call_mixed_kw", "void f(int a, int b) {}\nint main() { f(1, b=2); return 0; }", True),
    (
        "switch_break",
        "int main() { int x = 1; switch (x) { case (1) { break; } } return 0; }",
        True,
    ),
    (
        "pointer_deref_ref",
        """int main() {
  int x = 3;
  int* p = &x;
  int& r = x;
  *p = 7;
  r = 2;
  return x;
}""",
        True,
    ),
    (
        "overload_arity",
        """void f() {}
void f(int a) {}
int main() {
  f();
  f(1);
  return 0;
}""",
        True,
    ),
    (
        "class_operator_add",
        """class V {
  public:
  int operator+(int rhs) { return rhs + 1; }
}
int main() {
  V o;
  return o + 5;
}""",
        True,
    ),
    (
        "class_new_angle_syntax",
        """class A {
  public:
  int New<A>(int x) { return x; }
};
int main() { return 0; }
""",
        True,
    ),
    (
        "ctor_fallback_new_class",
        """class B {
  public:
  int New<B>(int x) { return x; }
};
int main() {
  B b = B(3);
  return 0;
}
""",
        True,
    ),
]


def main() -> int:
    failed = 0
    for name, src, run_eval in CASES:
        try:
            _run(src, run_eval)
        except Exception as e:
            failed += 1
            print(f"FAIL {name}: {e!r}")
            traceback.print_exc()
            print("--- source ---")
            print(src)
            print("--------------")
    if failed:
        print(f"\n{failed} case(s) failed")
        return 1
    print("all grammar harness cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
