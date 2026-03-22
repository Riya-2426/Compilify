"""
Heuristic symbol table for the GUI: Name, Type, Value, Scope, Uses.
Best-effort parsing for simple C-like declarations and assignments.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class SymbolRow:
    name: str
    type: str
    value: str
    scope: str
    uses: int


_DECL = re.compile(
    r"\b(int|float|char|double)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*([^;]+))?\s*;",
    re.MULTILINE,
)
_ASSIGN = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);",
    re.MULTILINE,
)


def build_symbol_table(code: str) -> List[SymbolRow]:
    declared: Dict[str, Tuple[str, str]] = {}  # name -> (type, value_str)
    order: List[str] = []

    for m in _DECL.finditer(code):
        typ, name, init = m.group(1), m.group(2), m.group(3)
        val = (init.strip() if init else "?").strip()
        if name not in declared:
            order.append(name)
        declared[name] = (typ, val)

    # Refine values from simple assignments (a = b + c;)
    for m in _ASSIGN.finditer(code):
        lhs, rhs = m.group(1), m.group(2).strip()
        if lhs in declared:
            typ, _ = declared[lhs]
            # keep simple rhs as display value
            if re.fullmatch(r"-?\d+(\.\d+)?", rhs):
                declared[lhs] = (typ, rhs)
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", rhs):
                other = rhs
                if other in declared:
                    declared[lhs] = (typ, declared[other][1])

    rows: List[SymbolRow] = []
    for name in order:
        typ, val = declared[name]
        uses = _count_uses(code, name)
        rows.append(SymbolRow(name=name, type=typ, value=val, scope="Local", uses=uses))

    return rows


def _count_uses(code: str, name: str) -> int:
    pat = re.compile(r"\b" + re.escape(name) + r"\b")
    return len(pat.findall(code))


def symbol_rows_for_gui(code: str) -> List[Tuple[str, str, str, str, str]]:
    return [(r.name, r.type, r.value, r.scope, str(r.uses)) for r in build_symbol_table(code)]
