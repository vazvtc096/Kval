from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class Token:
    type: str
    value: Any = None
    line: int = 1
    col: int = 1


KEYWORDS = {
    "int": "INT",
    "float": "FLOAT",
    "bool": "BOOL",
    "auto": "AUTO",
    "const": "CONST",
    "static": "STATIC",
    "constexpr": "CONSTEXPR",
    "void": "VOID",
    "string": "STRING",
    "array": "ARRAY",
    "return": "RETURN",
    "delete": "DELETE",
    "varScopeOrder": "VARSCOPEORDER",
    "template": "TEMPLATE",
    "typename": "TYPENAME",
    "class": "CLASS",
    "struct": "STRUCT",
    "public": "PUBLIC",
    "protected": "PROTECTED",
    "private": "PRIVATE",
    "code": "CODE",
    "New": "NEW",
    "operator": "OPERATOR",
    "roperator": "ROPERATOR",
    "global": "GLOBAL",
    "local": "LOCAL",
    "builtins": "BUILTINS",
    "closure": "CLOSURE",
    "this": "THIS",
    "base": "BASE",
    "true": "TRUE",
    "false": "FALSE",
    "if": "IF",
    "elif": "ELIF",
    "else": "ELSE",
    "while": "WHILE",
    "for": "FOR",
    "switch": "SWITCH",
    "case": "CASE",
    "break": "BREAK",
    "continue": "CONTINUE",
    "throw": "THROW",
    "try": "TRY",
    "catch": "CATCH",
    "finally": "FINALLY",
    "import": "IMPORT",
    "from": "FROM",
    "as": "AS",
    "export": "EXPORT",
    "namespace": "NAMESPACE",
    "extern": "EXTERN",
}


class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.n = len(text)
        self.i = 0
        self.line = 1
        self.col = 1

    def _adv(self, d: int = 1):
        for _ in range(d):
            if self.i < self.n and self.text[self.i] == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            self.i += 1

    def _peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.text[j] if j < self.n else ""

    def tokenize(self) -> list[Token]:
        toks: list[Token] = []
        while self.i < self.n:
            c = self._peek()
            start_line, start_col = self.line, self.col
            if c in " \t\r\n":
                self._adv()
                continue
            if c == "/" and self._peek(1) == "/":
                while self.i < self.n and self._peek() != "\n":
                    self._adv()
                continue
            if c == "/" and self._peek(1) == "*":
                self._adv(2)
                while self.i < self.n:
                    if self._peek() == "*" and self._peek(1) == "/":
                        self._adv(2)
                        break
                    self._adv()
                else:
                    raise SyntaxError(f"unclosed block comment /* ... */ at {start_line}:{start_col}")
                continue
            if c == '"':
                self._adv()
                sb: list[str] = []
                while self.i < self.n:
                    ch = self._peek()
                    if ch == "\\":
                        self._adv()
                        nxt = self._peek()
                        self._adv()
                        sb.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
                    elif ch == '"':
                        self._adv()
                        break
                    else:
                        sb.append(ch)
                        self._adv()
                toks.append(Token("STRING_LIT", "".join(sb), start_line, start_col))
                continue
            if c == "'":
                self._adv()
                sb = []
                while self.i < self.n:
                    ch = self._peek()
                    if ch == "\\":
                        self._adv()
                        nxt = self._peek()
                        self._adv()
                        sb.append({"n": "\n", "t": "\t", "'": "'", "\\": "\\"}.get(nxt, nxt))
                    elif ch == "'":
                        self._adv()
                        break
                    else:
                        sb.append(ch)
                        self._adv()
                toks.append(Token("STRING_LIT", "".join(sb), start_line, start_col))
                continue
            if c.isdigit():
                j = self.i
                while j < self.n and self.text[j].isdigit():
                    j += 1
                is_float = False
                if j < self.n and self.text[j] == "." and j + 1 < self.n and self.text[j + 1].isdigit():
                    is_float = True
                    j += 1
                    while j < self.n and self.text[j].isdigit():
                        j += 1
                raw_num = self.text[self.i : j]
                num = float(raw_num) if is_float else int(raw_num)
                self._adv(j - self.i)
                toks.append(Token("NUMBER", num, start_line, start_col))
                continue
            if c.isalpha() or c == "_":
                j = self.i
                while j < self.n and (self.text[j].isalnum() or self.text[j] == "_"):
                    j += 1
                w = self.text[self.i : j]
                self._adv(j - self.i)
                ty = KEYWORDS.get(w, "IDENT")
                toks.append(Token(ty, w, start_line, start_col))
                continue
            if c == "*" and self._peek(1) == "*":
                self._adv(2)
                toks.append(Token("STARSTAR", "**", start_line, start_col))
                continue
            if self._peek(0) == "<" and self._peek(1) == "<" and self._peek(2) == "=":
                self._adv(3)
                toks.append(Token("LSHIFTEQ", "<<=", start_line, start_col))
                continue
            if self._peek(0) == ">" and self._peek(1) == ">" and self._peek(2) == "=":
                self._adv(3)
                toks.append(Token("RSHIFTEQ", ">>=", start_line, start_col))
                continue
            comp2 = c + self._peek(1)
            comp_tok = {
                "+=": "PLUSEQ",
                "-=": "MINEQ",
                "*=": "STAREQ",
                "/=": "SLASHEQ",
                "%=": "PERCENTEQ",
                "^=": "CARETEQ",
                "&=": "AMPEQ",
                "|=": "PIPEEQ",
            }
            if comp2 in comp_tok:
                self._adv(2)
                toks.append(Token(comp_tok[comp2], comp2, start_line, start_col))
                continue
            if c == "|" and self._peek(1) == "|":
                self._adv(2)
                toks.append(Token("LOGIC_OR", "||", start_line, start_col))
                continue
            if c == "&" and self._peek(1) == "&":
                self._adv(2)
                toks.append(Token("LOGIC_AND", "&&", start_line, start_col))
                continue
            # 不合并 << / >>，以便区分模板实参 `<<int>>` 与移位（由解析器连续消费两个 LT/GT）
            two = c + self._peek(1)
            if two in ("::", "->", "<=", ">=", "==", "!=", ".="):
                self._adv(2)
                toks.append(
                    Token(
                        {"::": "COLCOL", "->": "ARROW", "<=": "LE", ">=": "GE", "==": "EQEQ", "!=": "NE", ".=": "DOTEQ"}[two],
                        two,
                        start_line,
                        start_col,
                    )
                )
                continue
            self._adv()
            one_map = {
                "+": "PLUS",
                "-": "MINUS",
                "*": "STAR",
                "/": "SLASH",
                "%": "PERCENT",
                "^": "CARET",
                "&": "AMP",
                "|": "PIPE",
                "~": "TILDE",
                "<": "LT",
                ">": "GT",
                "(": "LPAREN",
                ")": "RPAREN",
                "[": "LBRACKET",
                "]": "RBRACKET",
                "{": "LBRACE",
                "}": "RBRACE",
                ";": "SEMI",
                ",": "COMMA",
                ":": "COLON",
                "=": "EQ",
                ".": "DOT",
                "!": "BANG",
            }
            if c in one_map:
                toks.append(Token(one_map[c], c, start_line, start_col))
            else:
                raise SyntaxError(f"unexpected character {c!r} at {start_line}:{start_col}")
        toks.append(Token("EOF", None, self.line, self.col))
        return toks
