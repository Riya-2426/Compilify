from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class Token:
    kind: str
    lexeme: str
    line: int
    column: int


C_KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "inline",
    "int",
    "long",
    "register",
    "restrict",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
}

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BAD_IDENT_RE = re.compile(r"^[0-9]+[A-Za-z_][A-Za-z0-9_]*$")

_TOKENIZER = re.compile(
    r"""
    (?P<PREPROC>^[ \t]*\#[^\n]*)
  | (?P<WS>\s+)
  | (?P<COMMENT>//[^\n]*)
  | (?P<MCOMMENT>/\*[\s\S]*?\*/)
  | (?P<STRING>"(?:\\.|[^"\\])*")
  | (?P<CHAR>'(?:\\.|[^'\\])')
  | (?P<NUMBER>\b\d+(?:\.\d+)?\b)
  | (?P<IDENT>\b[A-Za-z_][A-Za-z0-9_]*\b)
  | (?P<OP>(==|!=|<=|>=|\+\+|--|->|&&|\|\||<<|>>|[+\-*/%=&|^~!<>?:]))
  | (?P<PUNC>[()[\]{};,\.])
  | (?P<OTHER>.)
""",
    re.VERBOSE | re.MULTILINE,
)


def tokenize(code: str) -> List[Token]:
    tokens: List[Token] = []
    line = 1
    col = 1
    i = 0
    n = len(code)
    while i < n:
        m = _TOKENIZER.match(code, i)
        if not m:
            tokens.append(Token("Unknown", code[i], line, col))
            i += 1
            col += 1
            continue

        lex = m.group(0)
        kind = m.lastgroup or "OTHER"

        if kind in {"WS"}:
            newlines = lex.count("\n")
            if newlines:
                line += newlines
                col = 1 + len(lex) - (lex.rfind("\n") + 1)
            else:
                col += len(lex)
        elif kind in {"PREPROC"}:
            tokens.append(Token("Preprocessor", lex.strip(), line, col))
            col += len(lex)
        elif kind in {"COMMENT", "MCOMMENT"}:
            newlines = lex.count("\n")
            if newlines:
                line += newlines
                col = 1 + len(lex) - (lex.rfind("\n") + 1)
            else:
                col += len(lex)
        else:
            tok_kind = kind
            if kind == "IDENT":
                tok_kind = "Keyword" if lex in C_KEYWORDS else "Identifier"
            elif kind == "NUMBER":
                tok_kind = "Constant"
            elif kind in {"STRING", "CHAR"}:
                tok_kind = "Constant"
            elif kind in {"OP"}:
                tok_kind = "Operator"
            elif kind in {"PUNC"}:
                tok_kind = "Punctuation"
            elif kind == "OTHER":
                tok_kind = "Unknown"

            tokens.append(Token(tok_kind, lex, line, col))
            col += len(lex)

        i = m.end()
    return tokens


def lexical_analysis(code: str) -> Tuple[List[Tuple[int, str, str]], List[Token]]:
    """Returns (errors, tokens). Each error is (line, message, suggestion)."""
    errors: List[Tuple[int, str, str]] = []
    tokens = tokenize(code)

    sug_invalid_symbol = (
        "Remove or replace the character; C programs use ASCII letters, digits, and standard punctuation. "
        "If you pasted from a document, retype quotes as \" and apostrophes as '."
    )
    sug_bad_ident = (
        "Identifiers must start with a letter or underscore, then letters/digits/underscore. "
        "Valid: int count1;  Invalid: int 1count;  Use: int x = 10; instead of merging digits into the name."
    )

    lines = code.splitlines()
    bad_ident_lines: set[int] = set()
    for idx, line in enumerate(lines, start=1):
        for m in re.finditer(r"\b\d+[A-Za-z_][A-Za-z0-9_]*\b", line):
            bad = m.group(0)
            bad_ident_lines.add(idx)
            errors.append((idx, f"Lexical Error: Invalid identifier `{bad}`", sug_bad_ident))

    for t in tokens:
        if t.kind == "Unknown":
            if t.line in bad_ident_lines:
                continue
            errors.append((t.line, f"Lexical Error: Invalid symbol `{t.lexeme}`", sug_invalid_symbol))

    for t in tokens:
        if t.kind == "Identifier" and not _IDENT_RE.match(t.lexeme):
            errors.append((t.line, f"Lexical Error: Invalid identifier `{t.lexeme}`", sug_bad_ident))

    seen: set[Tuple[int, str]] = set()
    deduped: List[Tuple[int, str, str]] = []
    for err in errors:
        key = (err[0], err[1])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(err)

    deduped.sort(key=lambda x: x[0])
    return deduped, tokens


def tokens_as_rows(tokens: Sequence[Token]) -> List[Tuple[str, str, int, int]]:
    rows: List[Tuple[str, str, int, int]] = []
    for t in tokens:
        if t.kind in {"Keyword", "Identifier", "Operator", "Constant"}:
            rows.append((t.kind, t.lexeme, t.line, t.column))
    return rows

