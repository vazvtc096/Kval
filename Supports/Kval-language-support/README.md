# Kval Language Support

VS Code extension for Kval / KVI files.

## Features

- TextMate syntax highlighting for `.kval` and `.kvi`
- Language server features: completion, hover, signature help, go-to-definition, references
- Semantic tokens for class/function/member/parameter/global declarations
- Parser-based diagnostics (via bundled Python bridge script)
- Run/compile commands and run-style debug adapter entry (no step/breakpoint support yet)

## Grammar Sync Policy

The canonical lexical source is:

- `Kval/Core/Parser/Lexer.py`

When adding new language keywords/operators in the compiler, update these extension files together:

- `syntaxes/kval.tmLanguage.json` (TextMate keywords/operators)
- `src/model.ts` (`KW` completion + hover keyword list)

Current keyword sync includes:

- scope keywords: `global`, `local`, `builtins`, `closure`
- error-flow keywords: `throw`, `try`, `catch`, `finally`
- module keywords: `import`, `from`, `as`, `export`, `namespace`

## Build

```bash
npm install
npm run compile
```

## Package

```bash
npm run vsix
```
