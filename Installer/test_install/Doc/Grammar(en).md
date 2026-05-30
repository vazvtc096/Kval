# Kval Language Grammar

> **Document language:** English  
> **Placeholders:** Angle brackets such as `<...>` stand for syntactic slots (types, identifiers, expressions, etc.).

This document describes Kval in order: **preprocessor → lexing (including comments) → variables → functions/methods → control flow → classes → pointers and references**. Diagnostics and runtime behavior are implementation-defined unless stated otherwise.

## Contents

1. [Preprocessor](#preprocessor)
2. [Lexical rules and comments](#lexical-rules-and-comments)
3. [Variables](#variables)
4. [Declaration modifiers and type syntax](#declaration-modifiers-and-type-syntax)
5. [Functions and methods](#functions-and-methods)
6. [Expressions and operators](#expressions-and-operators)
7. [Control flow](#control-flow)
8. [Classes](#classes)
9. [Pointers and references](#pointers-and-references) ([Pointers](#pointers) · [References](#references))
10. [Exceptions and error model](#exceptions-and-error-model)
11. [Array declaration syntax (updated)](#array-declaration-syntax-updated)
12. [Class inheritance and `base`](#class-inheritance-and-base)
13. [Modules, packages, imports, and exports](#modules-packages-imports-and-exports)
14. [`namespace`](#namespace)
15. [PythonBridge strong typing rule](#pythonbridge-strong-typing-rule)

---

## Preprocessor

Runs before lexing. A line whose first non-space character is `#` is treated as a preprocessor line for the **whole line**. A `#` **inside** a string literal does **not** start preprocessing.

### `#include`

```kval
#include "file.kval"
#include <file.kval>
```

**Search order:** the directory of the current source file first; if not found, then **`Kval/Lib/`** inside the package. `""` and `<>` follow the **same** rules.

### `#define`

Object-like macros only (no function-like macros): replace an identifier with following text. A trailing `//` starts a comment and is **not** part of the replacement.

```kval
#define NAME replacement text
#define FLAG
```

`#undef NAME` removes a macro.

- Expansion applies to normal source lines only, **not** to other preprocessor lines (e.g. another `#define`).
- Whole-token replacement; identifiers inside `"..."` strings are not expanded.
- Expansion depth is capped; cyclic expansion is an error.

### `#pragma once`

If an included file contains `#pragma once` (case-insensitive), that path is expanded **at most once** per translation unit; a later `#include` of the same path yields no text.

---

## Lexical rules and comments

**After preprocessing**, the expanded source is tokenized. The following comments may appear between tokens; inside **string literals** (`"..."` and `'...'`), `//` and `/*` are ordinary characters and do **not** start a comment.

### `//` line comments

From `//` through the end of the line (excluding the newline) is discarded and produces no token.

```kval
int x;  // trailing remark
// whole line is a comment
```

### `/*` `*/` block comments

From `/*` through the **first** following `*/` is discarded (comments **do not nest**: an inner `/*` does not open a new block). Block comments may span lines.

```kval
int a;
/* one-line block */
int b;
/*
  multi-line
  comment
*/
int c;
```

### Interaction with preprocessing and `#define`

- A trailing `//` on a `#define` line is stripped by the preprocessor and is **not** part of the replacement text (see [`#define`](#define)).
- If `/* ... */` appears inside macro replacement text, it is expanded with the rest of the text. To annotate a `#define` line, prefer a trailing `//` or put the remark on a normal non-`#` line.

### Reserved keyword list (canonical: `Core/Parser/Lexer.py`)

The lexer treats these words as keyword tokens (not plain identifiers):

```kval
int float bool auto const static constexpr void string array
return delete varScopeOrder template typename
class struct public protected private code New operator roperator
global local builtins closure this base
true false
if elif else while for switch case break continue
throw try catch finally
import from as export namespace
```

### Compound operators and punctuation tokens (lexical level)

The lexer recognizes these multi-character tokens:

```kval
** <<= >>= += -= *= /= %= ^= &= |=
|| && :: -> <= >= == != .=
```

Other unary/binary punctuation is tokenized as single characters (e.g. `+ - * / % ^ & | ~ < > ( ) [ ] { } ; , : = . !`).

---

## Variables

### Declaration

**Local variable**

```kval
<type> <name>
```

**Variable with an explicit scope qualifier**

Built-in scope names (they cannot be reused as user-defined scope labels):

| Name       | Meaning        | Notes |
| :--------- | :------------- | :---- |
| `builtins` | Built-in scope | — |
| `global`   | Global scope   | — |
| `closure`  | Closure scope  | `closure{n}` is the *n*-th enclosing closure |
| `local`    | Local scope    | — |

Syntax:

```kval
<type> <scope>::<name>
```

Initialization may be combined with declaration:

```kval
<type> <name> = <value>
<type> <scope>::<name> = <value>
```

### Deleting variables

```kval
delete <name>, ...
```

- `...` means several names, comma-separated.
- Deleting a name that is not bound is not an error.
- There is no `scope::name` delete form. Closure frames are scanned in order; **module-shaped** frames (`f_locals is f_globals`) are skipped. If a name is found in some frame’s `f_locals`, it is removed and the search stops.

### Assignment

```kval
<name> = <value>
<scope>::<name> = <value>
```

The right-hand type must match the variable’s declared type, or the compiler reports an error at compile time.

### Compound assignment

The following compound operators are supported. The left-hand side must be a plain variable or `<scope>::<name>` (not `obj.attr +=`, etc.):

```kval
<name> += <expr>
<name> -= <expr>
<name> *= <expr>
<name> /= <expr>
<name> %= <expr>
<name> ^= <expr>
<name> &= <expr>
<name> |= <expr>
<name> <<= <expr>
<name> >>= <expr>

<scope>::<name> += <expr>
// … same for other compound operators on scoped names
```

This is equivalent to read–binary-op–write. **Static** type checking (after parsing, in `Kval/Core/TypeCheck.py`) requires the left-hand side to already have a type (`int` / `string` / scoped declaration, etc.), and checks that the right-hand side and operation are consistent with that type (e.g. `int` with `int` for arithmetic and shifts; `string` allows `+=` with `string` and `*=` with `int`).

### Static type checking

`Parser.parse_source` runs a static pass over the module: variables must be declared before assignment; assignments, compound assignments, and expressions are checked for `int` / `string` (and opaque template parameter types where applicable); `return` is checked against the function signature. Template function **bodies** are skipped for deep checking; **calls** to template functions use relaxed argument checks to match syntax before `<<…>>` instantiation.

### Plain-name assign/delete and *non-cross-function* closures

While an inner function runs, its frame’s **`f_back`** is the caller’s frame (usually the immediately enclosing function). When a plain-name assignment resolves to a captured frame `closure` such that **`closure is` the current frame’s `f_back`** and that frame is **not** module-shaped, the implementation treats it as a **non-cross-function** closure: it may assign to an **existing** binding in that frame’s `f_locals` **even if** the name is missing from that frame’s `declared_locals` (unusual in hand-written code; normal code should still declare with `int`, etc.).

If the target closure frame is **not** the current `f_back`, the usual `declared_locals` rule still applies for assignment.

Plain `delete` over the closure chain skips module-shaped frames; behavior when a name is not in `declared_locals` is implementation-defined once a cell is found.

### Reading

**Bare name (default resolution order)**

```kval
<name>
```

Default order: `local` → `closure` → `global` → `builtins`. If nothing is found, the result is `Unbound` or an error, depending on runtime options (e.g. `--skip-error`, when implemented).

**Explicit scope**

```kval
<scope>::<name>
```

## Declaration modifiers and type syntax

> This section gives syntax shapes only, not type-system or runtime semantics.

### Modifier positions

```kval
const <type> <name> = <expr>;
constexpr <type> <name> = <expr>;
constexpr <return-type> <function-name>(<param-list>) { ... }
static <type> <name> [= <expr>];
```

### Types and keywords (syntax level)

```kval
<type> ::= int | float | bool | string | array | void | auto | <identifier-type-name>
```

### `struct` syntax

```kval
struct <StructName> {
  <member-declaration>...
}
```

### `varScopeOrder` (changing bare-name lookup)

These forms must appear **before** the first use of that `<name>` as a bare identifier in an expression. They only affect **automatic (bare-name) lookup** afterward; they do **not** change the meaning of `<scope>::<name>`.

The keyword **`varScopeOrder`**; after `:` there are two shapes, and you may list **several** `name: ...` groups separated by commas.

**Form A — pin to one scope** (exactly **one** scope token after `:`, **no** parentheses)

```kval
varScopeOrder <name>: <scope>, ...
```

- Bare-name lookup uses **only** that scope. If there is no binding, resolution stops—there is **no** fallback to other levels of the default four-level order.
- Clears any previous custom chain for that name from this statement.

**Form B — custom lookup chain** (parenthesized list of scopes joined by `->`)

```kval
varScopeOrder <name>: (<scope> -> <scope> -> ...), ...
```

- Scopes are tried left to right; if one step has no binding, the next is tried.
- If none bind the name, resolution stops; the **default four-level order is not** used.
- Clears any previous single-scope pin for that name from this statement.

---

## Functions and methods

A function or method is a callable unit with parameters and a return type. It may appear at module scope, inside a class body, and in other contexts the implementation allows.

### Definition

```kval
<return-type> <name>(
  <positional-type> <positional-name>, ..., <star-args-type> *<star-args-name>, /,
  <either-kind-type> <either-kind-name>, ..., *,
  <keyword-type> <keyword-name>, ..., <kw-var-type> **<kw-var-name>
) {
  <body>
  return <value>;
}
```

- If the return type is not `void`, every path must be able to reach a `return`; otherwise it is a compile-time error.
- For `void`, no usable return value is produced.
- The segments before `/` and after the last `*` may be omitted; omitted parameters default to the “either positional or keyword” style.
- The signature and call site may be formatted on one line or split across lines.

### Call

```kval
<name>(
  <positional-values>, ..., *<positional-sequence>,
  <keyword-name>=<keyword-value>, ..., **<keyword-mapping>
)
```

### Overloading

Multiple functions in the **same scope** with the **same name** but **different parameter lists (signatures)** form an overload set. The call is resolved to a unique or best match; ambiguity is an error (implementation-defined details).

> **Implementation status:** **Non-template** overload sets are implemented: both the runtime and static checker pick a unique matching signature from arity and keyword arguments; no match or ambiguity is an error. Template functions follow separate rules.

### Templates

Let one definition work for many template argument combinations (types, values, etc.):

```kval
template <<template-param-type> <template-param-name>, ...>
<function-definition>
```

**Formatting:** The closing `>` of `template ... >` and the following **function definition** (return type, name, and the parameter list starting with `(`) must be on **different physical lines**, to avoid confusion with the `>` comparison operator.

A template parameter type may be **`typename`**, meaning the corresponding argument must be a **type name**.

**Call** (angle brackets: template arguments; parentheses: call arguments):

```kval
<name><<template-args>>(<call-args>)
```

Template argument lists may span one or many lines.

---

## Expressions and operators

### Logical operators

- **`!`**: logical NOT (unary); same precedence layer as unary `-` and `~`, with **`!` binding first** in a unary chain (right-associative).  
- **`&&`**: logical AND with **short-circuiting**: the right-hand side is not evaluated if the left-hand side is false.  
- **`||`**: logical OR with **short-circuiting**: the right-hand side is not evaluated if the left-hand side is true.  

**Precedence (tightest first):** unary `!` → multiplicative / shifts → additive → comparisons (`<` `<=` `>` `>=` `==` `!=`) → **`&&`** → **`||`**.  

**Truthiness** (same as `if` / `while`): non-zero `int` is true, `0` is false; non-empty `string` is true, empty string is false; `Unbound` / null-like values are false. The value of `&&` / `||` is an **`int`**, `0` or `1`.

**Implementation note:** if a function body contains **`&&` or `||`** anywhere in an expression, the whole function falls back to **AST interpretation** for that function so short-circuiting is preserved. Unary **`!`** is supported on the ASM path.

---

## Control flow

Control-flow statements select branches, loop, and dispatch on values. They are typically used inside function bodies, `code` sections, and anywhere else the implementation allows statements.

### `if` / `elif` / `else`

```kval
if (<condition>) {
  <body>
}
elif (<condition>) {
  <body>
}
else {
  <body>
}
```

- `if` is required; `<condition>` is evaluated in a Boolean context (rules are implementation-defined).  
- `elif` and `else` are optional; there may be several `elif` clauses in order.  
- At most one `else`, after all `elif` clauses.  
- Each branch is a `{ ... }` block (if single-statement bodies without braces are allowed, that is implementation-defined).

### `while`

```kval
while (<condition>) {
  <body>
}
```

`<condition>` is evaluated at the **start** of each iteration. If true, the body runs and the loop repeats; if false, the loop exits.

**`break`** exits the innermost enclosing `while` / `for`, or ends a `switch` `case` / `else` body. **`continue`** skips to the next iteration of the innermost `while` / `for`.

### `for`

**Form 1 — three-part loop (C-style)**

```kval
for (<init>; <condition>; <step>) {
  <body>
}
```

- **`<init>`** runs once before the first iteration (often a variable definition with assignment; may be an assignment or empty—implementation-defined).  
- **`<condition>`** is evaluated at the **start** of each iteration; if false, the loop ends.  
- **`<step>`** runs after each completion of the body.  
- The three parts are separated by semicolons; whether any part may be omitted is implementation-defined.

**Form 2 — range-style iteration**

```kval
for (<element-type> <element-variable> : <iterable-or-iterator>) {
  <body>
}
```

- **`<iterable-or-iterator>`** must satisfy the **iterable object** or **iterator object** rules under **Classes → Special protocols** in this document.  
- Each iteration binds the current element to `<element-variable>` for use inside the body.

### `switch`

```kval
switch (<expression>) {
  case (<case-expression>) {
    <body-when-matched>
  }
  ...
  else {
    <body-when-none-match>
  }
}
```

- `<expression>` is evaluated once, then compared for equality (exact rules are implementation-defined) to each `case`’s `<case-expression>`.  
- The first matching `case` body runs. **`else`** runs when no `case` matches.  
- Each `case` and `else` body uses `{ ... }`.  
- Whether execution falls through to the next `case`, and whether `else` is required, are implementation-defined.

---

## Classes

### Definition

```kval
class <ClassName> {
  public:
  ...
  protected:
  ...
  private:
  ...
  code:
  ...
};
```

Variables, functions, and nested classes declared in the body are **members** of the class, except material in the `code` section (see table below).

### Access sections and `code`

| Section     | Kind               | Meaning |
| :---------- | :----------------- | :------ |
| `public`    | Access control     | Visible everywhere |
| `protected` | Access control     | Visible inside this class and subclasses |
| `private`   | Access control     | Visible only inside this class; default if no section is written |
| `code`      | Procedural section | Executable logic while the class body is processed; **not** a normal member block |

Prefer member-related declarations inside `public` / `protected` / `private`. The `code` section may contain arbitrary statements.

### Special members

> **Implementation status:** Binary **`operator`** members (e.g. `operator+`) are parsed as methods with an implicit `this` parameter; for a class instance as the **left** operand of `+` `-` `*` `/` `%`, the runtime dispatches to `__op_add__` and similar (see code). **Construction call:** **`ClassName(args…)`** is supported; if there is **no** same-named **`void ClassName(…)`** member, the runtime falls back to a **`NewClassName`** member (produced by the **`any-type New<ClassName>(…)`** sugar). The **`New<ClassName>(…)`** form is **parsed**; the member name is **`New` + the identifier inside the angle brackets** (e.g. `NewPoint`). `roperator` / `uoperator`, destructor `~T`, and user-defined conversions are **not** fully wired yet. Access sections, `code`, and ordinary members remain supported.

1. `(public) <any-type> New<ClassName>(<signature>)` — custom object creation.  
2. `(public) void <ClassName>(<signature>)` — constructor.  
3. `(public) void ~<ClassName>()` — destructor.  
4. `(public) <any-type> operator<binary-op>(<any-type> <other>)` — binary operators with `this` as the **left** operand.

   | Operator | Meaning |
   | :------- | :------ |
   | `+` `-` `*` `/` `%` | Arithmetic |
   | <code>^</code> <code>&</code> <code>|</code> | Bitwise XOR, AND, OR |
   | `<<` `>>` | Shifts |
   | `<` `<=` `>` `>=` `==` `!=` | Comparisons |
   | `.` | Attribute read |
   | `.=` | Attribute write |
   | `[]` | Index read |
   | `[]=` | Index write |

5. `(public) <any-type> roperator<binary-op>(<any-type> <other>)` — binary operators with `this` as the **right** operand.  
6. `(public) <any-type> uoperator<unary-op>()` — unary operators.

   | Operator | Meaning |
   | :------- | :------ |
   | `-` | Unary minus |
   | `~` | Bitwise NOT |

7. `(public) <target-type> operator <target-type-name>()` — user-defined conversion to `<target-type>`.

### Special protocols

#### Iterable objects

Two protocols are supported. The runtime tries **protocol 1** first; if it does not apply, it tries **protocol 2**.

**Protocol 1 — `iter` / `next`**

- On the container: `<iterator-type> iter()`  
- On the iterator: `<any-type> next()`

If `iter()` does not return an “iterator object”, `iter()` is applied again to the return value until an iterator is obtained; iteration is then driven by `next()`.

**Protocol 2 — subscript and length**

- On the instance: `<any-type> operator[](int index)`  
- And either `int length()` **or** an `int length` property  

Indices run from `0` upward until the end condition implied by `length`.

#### Iterator objects

Must satisfy:

- `<iterator-type> iter()` **returns `this`** (the iterator itself);  
- `<any-type> next()` returns successive items while elements remain, and throws **`StopIteration`** when iteration is finished.

### The `this` pointer

Inside an instance method, `this` is a pointer to the **current instance**, used to access members and overloads tied to the receiving object.

### Instance construction, method calls, and reclamation (implementation)

This subsection ties the **target syntax** above to what the **current interpreter/runtime** actually does.

1. **Construction**  
   - **`ClassName(args…)`** (in expression position): the runtime **shallow-copies** the class template’s `members` into a new instance, then prefers the **same-named** member **`void ClassName(…)`**; **if absent**, it calls **`members["New" + className]`** (the function declared as **`ret-type New<ClassName>(…)`**, registered under **`NewClassName`**). In both cases **`this`** is bound to the new instance for the call.  
   - **`ClassName var;`** with no initializer: for class types the implementation currently **copies the template `members`** into an instance dict; it **does not** guarantee that either constructor path runs (unlike the explicit `ClassName(…)` path).  
   - **Declaration syntax:** you may write **`<return-type> New<SomeName>(<params>) { … }`** in a class or at module scope; the parser registers the member as **`NewSomeName`**, equivalent to spelling that name manually.

2. **Method calls and `this`**  
   - The spec calls `this` a **pointer**; in the implementation the instance is a mapping with `__kclass__` and a **`members`** table. For **`instance.method(…)`**, the runtime passes the receiver into the `KvalFunction` so that **`this` refers to that receiver** inside the method; member access goes through **`members`**. Semantically this is “the current object”, **not** a raw C/C++ pointer with manual `delete`.

3. **Destructor and end of life**  
   - **`void ~ClassName()`** from the spec is **not** hooked into the runtime yet; there is **no** automatic destructor call when an instance becomes unreachable.  
   - **Reclamation**: instances are ordinary Python objects (dicts); when nothing references them anymore, **CPython’s GC** may collect them. Block exit and reassignment drop references, which **looks** like “scope-based” cleanup, but there is **no** deterministic destructor ordering.

4. **Static typing**  
   - If there is **no** top-level function with the class name, but a class **`ClassName`** exists, and **either** a **`void ClassName(…)`** member **or** a **`NewClassName`** member (including one produced from **`New<ClassName>(…)`**) is present, then **`ClassName(args…)`** is checked against the chosen member’s parameter list and has static type **`ClassName`** (opaque).

---

## Pointers and references

> **Implementation status:** Address-of `&`, pointer types `T*`, unary `*`, reference types `T&` (alias semantics), and the statement `*<ptr-expr> = <expr>` are implemented. Code that uses pointers/references (and `&&` / `||`, etc.) runs on the AST path, not the stack ASM backend. Richer pointer member access (e.g. `->`) is still implementation-defined.

### Pointers

#### Address-of

Taking the address of a **variable** yields a pointer to the object it denotes:

```kval
&<name>
```

**Restriction:** you cannot take the address of a literal; only of a variable.

#### Declaration

```kval
<element-type>* <ptr-name> = &<name>
```

`<element-type>*` is the type “pointer to `<element-type>`”.

#### Indirection

```kval
*<ptr-name>
```

In an lvalue position, this designates the pointed-to object for read or write.

#### Multiple levels

A pointer type may itself be the pointed-to type:

```kval
<element-type>** <ptr2-name> = &<ptr-name>
```

#### Member access through a pointer

`->` is equivalent to dereference then `.`.

Read:

```kval
<ptr-name>-><member>
(*<ptr-name>).<member>
```

Write:

```kval
<ptr-name>-><member> = <value>
(*<ptr-name>).<member> = <value>
```

### References

A reference is an **alias** for an existing object. After binding, reads and writes through the reference name are the same as through the original variable.

#### Declaration and initialization

```kval
<element-type>& <ref-name> = <name>
```

- `&` after **`<element-type>`** forms a reference type.  
- A reference **must** be initialized in its declaration; ill-formed or uninitialized bindings are compile-time errors (when enforced by the implementation).  
- After binding, the reference does **not** rebind to another object (unlike a pointer variable, which may hold different addresses over time).

#### Using a reference

No `*` is needed; use the name like a value of the object type:

```kval
<ref-name>                // read
<ref-name> = <value>      // write through the alias
```

#### Member access

Use **`.`** (not the pointer form `->`):

```kval
<ref-name>.<member>
<ref-name>.<member> = <value>
```

#### Usage vs pointers

| | Pointer `T*` | Reference `T&` |
| :-- | :-- | :-- |
| Meaning | Stores an address; can be retargeted | Alias; no rebind |
| Whole object | `*p` | `r` |
| Member | `p->m` or `(*p).m` | `r.m` |

#### Restrictions

- In general you cannot bind a reference to a literal or an unnamed temporary (same spirit as address-of; implementation exceptions apply).  
- There is no “null reference”; the referenced object must remain valid for the uses you make of the reference.

---

## Exceptions and error model

### `throw`

```kval
throw <expression>;
```

- Throws the target exception object. Non-exception values may be wrapped by runtime rules.
- Errors are rendered in a Python-like `Traceback` format (`File`, `Lineon`, `In`, code context, `ExceptionName: message`) without exposing raw Python traceback internals.

### `try-catch-else-finally`

```kval
try {
  <statements...>
}
catch {
  <statements...>
}
catch (ExceptionType) {
  <statements...>
}
catch (ExceptionType e) {
  <statements...>
}
else {
  <statements...>
}
finally {
  <statements...>
}
```

- `catch {}`: catch all exceptions.
- `catch (T)`: catch `T` and subclasses.
- `catch (T e)`: same as above and bind the exception as `e`.
- `else` runs when `try` completes without exception; `finally` always runs.

### Exception hierarchy

- Root: `Exceptions`
- Runtime branch: `RunTimeError` and refined types (`TypeError`, `ValueError`, `NameError`, `IndexError`, `KeyError`, `ZeroDivisionError`, `ImportError`, etc.)
- System branch: `SysError` and its subclasses

## Array declaration syntax (updated)

Arrays use:

```kval
<element-type> <array-name>[<size>];
<element-type> <array-name>[<size>] = <initializer>;
```

- `<size>` must be an `int` expression.
- This is the canonical declaration form for arrays.

## Class inheritance and `base`

### Inheritance syntax

```kval
class SubClass : public BaseA, protected BaseB, private BaseC {
  ...
}
```

- Multiple inheritance is supported.
- `public/protected/private` in the base list controls inherited visibility folding.
- Member lookup follows MRO.

### `base` pointer

Inside class methods, `base` resolves parent members by MRO (starting after current owner class):

```kval
int f() {
  return base.f();
}
```

- `base` is for parent resolution and is not the same object as `this`.
- Write access through `base` is restricted by runtime access-control rules.

## Modules, packages, imports, and exports

### Import syntax

```kval
import ModuleName;
import ModuleName as Alias;
from ModuleName import Member;
from ModuleName import Member as Alias;
```

### Relative imports

```kval
import .ModuleName;
import ..ModuleName;
from .ModuleName import Member;
from ..Package import Member;
```

- `.` means current package level, `..` parent level, etc.

### Export rules

Either an explicit export list:

```kval
const string[2] exports = { "NameA", "NameB" };
```

or an `export` modifier:

```kval
export int add(int a, int b) { ... }
```

- If neither is present, default export includes public symbols not considered hidden by convention (typically excluding `__`-prefixed names).

### Module search order

1. `cwd`
2. `Kval/Lib`
3. `Kval/Lib/site-packages`
4. `Kval/PyModules`

### Package conventions

- `PackageName.kval`: package initializer entry.
- `~PackageName.kval`: package destructor entry (triggered at process exit).
- Subpackages and `from Package import ...` are supported.

## `namespace`

```kval
namespace Name {
  ...
}

Name::member
```

- `namespace` groups symbols and supports `::` access.
- Namespace members participate in imports and scoped lookup.

## PythonBridge strong typing rule

For Python modules imported through the Kval bridge:

- Exported functions must annotate every parameter.
- Exported functions must annotate return type.
- Missing annotations cause an import-time type error.
