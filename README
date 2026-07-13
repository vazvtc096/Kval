# Kval

Kval is a statically typed programming language runtime and toolchain implemented in Python.

## Quick Start

Requirements:

- Python 3.10+

Run a `.kval` file:

```bash
python -m Kval run path/to/file.kval
```

Compile a `.kval` file:

```bash
python -m Kval compile path/to/file.kval
```

## Project Structure

- `Core/` parser, type checker, runtime, VM
- `Doc/` language documentation
- `Lib/` standard modules and include search path
- `PyModules/` Python bridge modules
- `tests/` grammar and behavior tests
- `Supports/Kval-language-support/` VS Code language extension

## Language Docs

- Chinese grammar: `Doc/Grammar(zh-cn).md`
- English grammar: `Doc/Grammar(en).md`
- Chinese standard library: `Doc/StdLib(zh-cn).md`
- English standard library: `Doc/StdLib(en).md`
- Chinese stdlib quick reference: `Doc/StdLib-QuickRef(zh-cn).md`
- English stdlib quick reference: `Doc/StdLib-QuickRef(en).md`
- Engineering guide: `Doc/Engineering.md`

## VS Code Extension

Extension source is in `Supports/Kval-language-support/`.

Build:

```bash
npm run compile
```

Package:

```bash
npm run vsix
```

## CI

This repository includes GitHub Actions CI in `.github/workflows/ci.yml`.

It runs checks on push and pull requests, and only runs jobs when related files change:

- Python quality (`Core/`, `tests/`, CLI/tooling files):
  - `ruff check Core tests cli.py __main__.py`
  - `black --check Core tests cli.py __main__.py`
  - `pytest`
- VS Code extension quality (`Supports/Kval-language-support/**`):
  - `npm install`
  - `npm run lint`
  - `npm run format:check`
  - `npm run compile`

Other CI details:

- Concurrency is enabled to cancel older in-progress runs on the same branch.
- Python quality runs on Python `3.10` and `3.11`.

To reproduce locally:

```bash
ruff check Core tests cli.py __main__.py
black --check Core tests cli.py __main__.py
pytest
cd Supports/Kval-language-support
npm install
npm run lint
npm run format:check
npm run compile
```

## License

MIT License. See `LICENSE`.
