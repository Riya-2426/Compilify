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


def semantic_check(code: str) -> List[Tuple[int, str]]:
    declared: Dict[str, str] = {}
    declared_lines: Dict[str, int] = {}
    errors: List[Tuple[int, str]] = []

    included_headers: Set[str] = set()
    preproc_lines: Set[int] = set()
    for ln, line in enumerate(code.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            preproc_lines.add(ln)
        m = _INCLUDE_RE.match(line)
        if m:
            included_headers.add(m.group("hdr").strip())

    tokens = tokenize(code)
    skip_idents: Set[str] = set(C_KEYWORDS)
    decl_lines: Set[int] = set()

    type_keywords = {"int", "float", "char"}

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.kind == "Keyword" and t.lexeme in type_keywords:
            decl_type = t.lexeme
            line = t.line

            j = i + 1
            just_saw_comma = False
            while j < len(tokens) and tokens[j].line == line:
                tok = tokens[j]
                if tok.lexeme == ";":
                    break
                if tok.lexeme == ",":
                    just_saw_comma = True
                    j += 1
                    continue
                if tok.lexeme in {"*", "[" , "]"}:
                    j += 1
                    continue
                if tok.kind == "Identifier":
                    # Function prototypes/definitions: ignore identifier followed by '('
                    if j + 1 < len(tokens) and tokens[j + 1].lexeme == "(":
                        j += 1
                        just_saw_comma = False
                        continue

                    name = tok.lexeme
                    decl_lines.add(line)
                    if name in declared:
                        errors.append(
                            (line, f"Semantic Error: Duplicate declaration of `{name}` (previous at line {declared_lines[name]})")
                        )
                    else:
                        declared[name] = decl_type
                        declared_lines[name] = line
                    just_saw_comma = False
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
        if t.line in decl_lines:
            continue
        if i + 1 < len(tokens) and tokens[i + 1].lexeme == "(":
            required = _FUNC_HEADER_REQUIREMENTS.get(ident)
            if required and required not in included_headers:
                errors.append((t.line, f"Semantic Error: Missing header `<{required}>` for `{ident}()`"))
            continue
        if ident not in declared:
            errors.append((t.line, f"Semantic Error: Undeclared variable `{ident}`"))

    errors.sort(key=lambda x: x[0])
    return errors

