from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from .lexer import C_KEYWORDS, tokenize


_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"](?P<hdr>[^>"]+)[>"]')

_FUNC_HEADER_REQUIREMENTS: dict[str, str] = {
    # stdio.h
    "printf": "stdio.h",
    "scanf": "stdio.h",
    "puts": "stdio.h",
    "gets": "stdio.h",
    "fgets": "stdio.h",
    "putchar": "stdio.h",
    "getchar": "stdio.h",
    # stdlib.h
    "malloc": "stdlib.h",
    "calloc": "stdlib.h",
    "realloc": "stdlib.h",
    "free": "stdlib.h",
    "exit": "stdlib.h",
    "atoi": "stdlib.h",
    "atof": "stdlib.h",
    # string.h
    "strlen": "string.h",
    "strcpy": "string.h",
    "strncpy": "string.h",
    "strcat": "string.h",
    "strcmp": "string.h",
    # math.h
    "sqrt": "math.h",
    "pow": "math.h",
}


def semantic_check(code: str) -> List[Tuple[int, str, str]]:
    """Each error is (line, message, suggestion)."""
    declared: Dict[str, str] = {}
    declared_lines: Dict[str, int] = {}
    errors: List[Tuple[int, str, str]] = []

    included_headers: Set[str] = set()
    preproc_lines: Set[int] = set()
    for ln, line in enumerate(code.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            preproc_lines.add(ln)
        m = _INCLUDE_RE.match(line)
        if m:
            included_headers.add(m.group("hdr").strip())

    tokens = tokenize(code)

    # Lines with an odd number of `"` (in code, not // comments) confuse the tokenizer.
    unclosed_string_lines: Set[int] = set()
    for ln, line in enumerate(code.splitlines(), start=1):
        if _line_has_unclosed_string(line):
            unclosed_string_lines.add(ln)

    skip_idents: Set[str] = set(C_KEYWORDS)
    # Names declared on a given line (not identifiers used in initializers).
    declared_on_line: Set[Tuple[int, str]] = set()

    type_keywords = {"int", "float", "char"}

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.kind == "Keyword" and t.lexeme in type_keywords:
            decl_type = t.lexeme
            line = t.line

            j = i + 1
            in_initializer = False
            while j < len(tokens) and tokens[j].line == line:
                tok = tokens[j]
                if tok.lexeme == ";":
                    break
                if tok.lexeme == "=":
                    in_initializer = True
                    j += 1
                    continue
                if tok.lexeme == ",":
                    in_initializer = False
                    j += 1
                    continue
                if tok.lexeme in {"*", "[", "]"}:
                    j += 1
                    continue
                if tok.kind == "Identifier":
                    # Function prototypes/definitions: ignore identifier followed by '('
                    if j + 1 < len(tokens) and tokens[j + 1].lexeme == "(":
                        j += 1
                        continue

                    if in_initializer:
                        # e.g. int z = a + b  ->  a, b are uses, not declarations
                        use_name = tok.lexeme
                        if use_name not in declared and use_name not in skip_idents:
                            errors.append(
                                (
                                    line,
                                    f"Semantic Error: Undeclared variable `{use_name}`",
                                    f"Declare before use. Example: int {use_name};  or  int {use_name} = 0;  "
                                    f"then use it on later lines inside the same function.",
                                )
                            )
                        j += 1
                        continue

                    name = tok.lexeme
                    declared_on_line.add((line, name))
                    if name in declared:
                        prev = declared_lines[name]
                        errors.append(
                            (
                                line,
                                f"Semantic Error: Duplicate declaration of `{name}` (previous at line {prev})",
                                f"Use each variable name once per scope. Example: int {name} = 0; only once, "
                                f"or pick a new name for the second variable (e.g. {name}2).",
                            )
                        )
                    else:
                        declared[name] = decl_type
                        declared_lines[name] = line
                j += 1

            i = j
            continue
        i += 1

    for i, t in enumerate(tokens):
        if t.kind != "Identifier":
            continue
        ident = t.lexeme
        if ident in skip_idents:
            continue
        if t.line in preproc_lines:
            continue
        if (t.line, ident) in declared_on_line:
            continue
        if t.line in unclosed_string_lines:
            continue
        if i + 1 < len(tokens) and tokens[i + 1].lexeme == "(":
            required = _FUNC_HEADER_REQUIREMENTS.get(ident)
            if required and required not in included_headers:
                errors.append(
                    (
                        t.line,
                        f"Semantic Error: Missing header `<{required}>` for `{ident}()`",
                        f"Add at the top of the file: #include <{required}>   "
                        f"(before any call to `{ident}`). Example: #include <stdio.h>",
                    )
                )
            continue
        if ident not in declared:
            errors.append(
                (
                    t.line,
                    f"Semantic Error: Undeclared variable `{ident}`",
                    f"Declare before use. Example: int {ident};  or  int {ident} = 0;  "
                    f"then use it on later lines inside the same function.",
                )
            )

    seen: Set[Tuple[int, str]] = set()
    deduped: List[Tuple[int, str, str]] = []
    for err in errors:
        key = (err[0], err[1])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(err)

    deduped.sort(key=lambda x: x[0])
    return deduped


def _line_has_unclosed_string(line: str) -> bool:
    """True if a double-quoted string on this line is not closed (ignores // comments)."""
    code = line.split("//", 1)[0]
    in_string = False
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "\\" and in_string:
            i += 2
            continue
        if ch == '"':
            in_string = not in_string
        i += 1
    return in_string

