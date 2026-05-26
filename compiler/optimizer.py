from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .lexer import C_KEYWORDS, tokenize


@dataclass(frozen=True)
class OptimizationNote:
    line: int
    message: str


_TRAIL_WS_RE = re.compile(r"[ \t]+$")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"')

# Very small, safe constant folding for arithmetic-only expressions.
_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.FloorDiv,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Pow,
    ast.Load,
    ast.Tuple,
)


def optimize_code(code: str) -> Tuple[str, List[OptimizationNote]]:
    """
    Returns (optimized_code, notes).

    Scope (intentionally safe / beginner-friendly):
    - Trims trailing whitespace
    - Normalizes spacing around common operators and punctuation (not inside strings)
    - Advanced algebraic simplification (safe subset)
    - Copy propagation (replace variables with their current copy source)
    - Constant propagation + folding (straight-line code, safe subset)
    - Merge uninitialized declarations with their immediate assignment (int x; x = e; -> int x = e;)
    - Dead code elimination (removes statements after `return` in the same block)
    - Unused variable removal (simple/obvious cases)
    - Common subexpression elimination (basic, reuse earlier computed expr if inputs unchanged)
    """
    if not code:
        return "", []

    original = code
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    notes: List[OptimizationNote] = []

    lines = code.splitlines()
    out_lines: List[str] = []

    # Pass 0: keep comments/preprocessor stable, normalize spacing/trailing ws.
    for ln, raw in enumerate(lines, start=1):
        # Keep preprocessor lines as-is (except trailing spaces).
        if raw.lstrip().startswith("#"):
            cleaned = _TRAIL_WS_RE.sub("", raw)
            if cleaned != raw:
                notes.append(OptimizationNote(ln, "Removed trailing spaces."))
            out_lines.append(cleaned)
            continue

        # Split single-line comments (avoid touching comments).
        if "//" in raw:
            before, after = raw.split("//", 1)
            comment = "//" + after
        else:
            before, comment = raw, ""

        line = _TRAIL_WS_RE.sub("", before)

        # Basic whitespace normalization (safe; preserves string literal contents).
        line2 = _normalize_spacing(line)
        if line2 != line:
            notes.append(OptimizationNote(ln, "Normalized spacing."))
        line = line2

        # Peephole algebraic simplifications (very conservative).
        simplified, did = _simplify_algebra(line)
        if did and simplified != line:
            notes.append(OptimizationNote(ln, "Applied algebraic simplification."))
        line = simplified

        # Constant folding on simple assignments/initializers:  x = <numeric expr>;
        folded, did_fold = _fold_assignment_constants(line)
        if did_fold and folded != line:
            notes.append(OptimizationNote(ln, "Folded constant expression."))
        line = folded

        # Remove no-op assignment: x = x;
        if _is_noop_self_assign(line):
            notes.append(OptimizationNote(ln, "Removed no-op assignment (x = x)."))
            line = ""

        out_lines.append((line + (" " if line and comment and not line.endswith(" ") else "") + comment).rstrip())

    normalized = "\n".join([l for l in out_lines if l != ""])
    normalized = _MULTI_BLANK_RE.sub("\n\n", normalized).strip() + ("\n" if normalized.strip() else "")

    # Pass 1+: run semantic-ish optimizations on code lines (skip preproc).
    optimized, more_notes = _optimize_statements(normalized)
    notes.extend(more_notes)

    if optimized != original.replace("\r\n", "\n").replace("\r", "\n"):
        if not notes:
            notes.append(OptimizationNote(0, "Applied formatting optimizations."))
    return optimized, notes


def _normalize_spacing_code(s: str) -> str:
    """Normalize spacing outside of string literals."""
    if not s.strip():
        return ""

    parts: List[str] = []
    last = 0
    for m in _STRING_LITERAL_RE.finditer(s):
        if m.start() > last:
            parts.append(_normalize_spacing_segment(s[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    if last < len(s):
        parts.append(_normalize_spacing_segment(s[last:]))
    return "".join(parts)


def _normalize_spacing_segment(s: str) -> str:
    if not s.strip():
        return s
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*([=+\-*/%<>!]=|==|!=|<=|>=)\s*", r" \1 ", s)
    s = re.sub(r"\s*([=+\-*/%<>])\s*", r" \1 ", s)
    s = re.sub(r"\s*([;,)\]])", r"\1", s)
    s = re.sub(r"([(\[])\s+", r"\1", s)
    s = re.sub(r",\s*", ", ", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s


def _normalize_spacing(s: str) -> str:
    """Normalize spacing on a line/expression without altering string literal contents."""
    if not s.strip():
        return ""
    return _normalize_spacing_code(s).strip()


def _simplify_algebra(line: str) -> Tuple[str, bool]:
    """
    Conservative algebra peepholes on simple assignment lines only.
    """
    m = re.match(r"^(?P<lhs>[A-Za-z_]\w*)\s*=\s*(?P<rhs>.+);\s*$", line)
    if not m:
        return line, False

    lhs = m.group("lhs")
    rhs = m.group("rhs").strip()

    rhs2 = re.sub(rf"^\s*{re.escape(lhs)}\s*\+\s*0\s*$", lhs, rhs)
    rhs2 = re.sub(rf"^\s*0\s*\+\s*{re.escape(lhs)}\s*$", lhs, rhs2)
    rhs2 = re.sub(rf"^\s*{re.escape(lhs)}\s*-\s*0\s*$", lhs, rhs2)
    rhs2 = re.sub(rf"^\s*{re.escape(lhs)}\s*\*\s*1\s*$", lhs, rhs2)
    rhs2 = re.sub(rf"^\s*1\s*\*\s*{re.escape(lhs)}\s*$", lhs, rhs2)
    rhs2 = re.sub(rf"^\s*{re.escape(lhs)}\s*/\s*1\s*$", lhs, rhs2)
    rhs2 = re.sub(rf"^\s*{re.escape(lhs)}\s*\*\s*0\s*$", "0", rhs2)
    rhs2 = re.sub(rf"^\s*0\s*\*\s*{re.escape(lhs)}\s*$", "0", rhs2)

    if rhs2 != rhs:
        return f"{lhs} = {rhs2};", True
    return line, False


def _fold_assignment_constants(line: str) -> Tuple[str, bool]:
    m = re.match(r"^(?P<lhs>[A-Za-z_]\w*)\s*=\s*(?P<rhs>.+);\s*$", line)
    if not m:
        return line, False
    lhs = m.group("lhs")
    rhs = m.group("rhs").strip()

    if re.search(r"[A-Za-z_]\w*", rhs):
        return line, False

    if not re.fullmatch(r"[0-9+\-*/%(). \t]+", rhs):
        return line, False

    try:
        expr = ast.parse(rhs, mode="eval")
    except SyntaxError:
        return line, False

    for node in ast.walk(expr):
        if not isinstance(node, _ALLOWED_AST_NODES):
            return line, False

    try:
        value = eval(compile(expr, "<opt>", "eval"), {"__builtins__": {}}, {})
    except Exception:
        return line, False

    if isinstance(value, (int, float)):
        folded = (
            str(int(value))
            if isinstance(value, int) or (isinstance(value, float) and value.is_integer())
            else str(value)
        )
        return f"{lhs} = {folded};", True

    return line, False


def _is_noop_self_assign(line: str) -> bool:
    m = re.match(r"^(?P<lhs>[A-Za-z_]\w*)\s*=\s*(?P<rhs>[A-Za-z_]\w*)\s*;\s*$", line)
    return bool(m and m.group("lhs") == m.group("rhs"))


# -----------------------------
# Advanced optimization pipeline
# -----------------------------

_TYPE_KWS = {"int", "float", "double", "char", "long", "short", "signed", "unsigned"}
_TYPE_KW_PATTERN = r"(?:int|float|double|char|long|short|signed|unsigned)"
_ASSIGN_RE = re.compile(
    r"^\s*(?P<prefix>.*?)(?P<lhs>[A-Za-z_]\w*)\s*=\s*(?P<rhs>.+?)\s*;\s*$"
)
_DECL_ONLY_RE = re.compile(
    rf"^\s*(?P<prefix>(?:{_TYPE_KW_PATTERN}\s+)+)(?P<name>[A-Za-z_]\w*)\s*;\s*$"
)


@dataclass
class _Stmt:
    line: int
    raw: str
    kind: str  # decl|assign|return|other|preproc
    lhs: Optional[str] = None
    rhs: Optional[str] = None
    declared: Optional[str] = None
    brace_delta: int = 0


def _is_assign_like(st: _Stmt) -> bool:
    return st.kind == "assign" or (st.kind == "decl" and st.lhs is not None and st.rhs is not None)


def _parse_assign_parts(raw: str) -> Optional[Tuple[str, str, str]]:
    m = _ASSIGN_RE.match(raw.strip())
    if not m:
        return None
    return m.group("prefix"), m.group("lhs"), m.group("rhs").strip()


def _depth_before(stmts: List[_Stmt], index: int) -> int:
    return sum(st.brace_delta for st in stmts[:index])


def _parse_uninitialized_decl(st: _Stmt) -> Optional[Tuple[str, str]]:
    """Return (type_prefix, name) for `int x;` style declarations."""
    if st.kind != "decl" or not st.declared or not st.raw.strip():
        return None
    if st.rhs is not None:
        return None
    m = _DECL_ONLY_RE.match(st.raw.strip())
    if not m or m.group("name") != st.declared:
        return None
    return m.group("prefix"), st.declared


def _merge_decl_assignments(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    """
    Combine `int x;` followed immediately by `x = expr;` into `int x = expr;`.
    """
    notes: List[OptimizationNote] = []
    i = 0
    while i < len(stmts):
        decl_info = _parse_uninitialized_decl(stmts[i])
        if not decl_info:
            i += 1
            continue

        prefix, name = decl_info
        depth_decl = _depth_before(stmts, i)

        j = i + 1
        while j < len(stmts) and not stmts[j].raw.strip():
            j += 1

        if j >= len(stmts):
            i += 1
            continue

        nxt = stmts[j]
        if _depth_before(stmts, j) != depth_decl:
            i += 1
            continue
        if nxt.kind != "assign" or nxt.lhs != name:
            i += 1
            continue

        parts = _parse_assign_parts(nxt.raw)
        if not parts or parts[1] != name:
            i += 1
            continue

        _, _, rhs = parts
        merged = _format_assign_line(prefix, name, rhs)
        st = stmts[i]
        st.raw = merged
        st.lhs = name
        st.rhs = rhs
        nxt.raw = ""
        notes.append(
            OptimizationNote(
                st.line,
                f"Merged declaration and assignment into initialized declaration `{name} = {rhs}`.",
            )
        )
        i += 1

    return stmts, notes


def _remove_invalid_declarations(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    """Remove declarations whose name starts with a digit (invalid C)."""
    notes: List[OptimizationNote] = []
    invalid_name = re.compile(r"^\s*(?:" + _TYPE_KW_PATTERN + r"\s+)(\d+[A-Za-z_]\w*)")
    for st in stmts:
        if not st.raw.strip():
            continue
        m = invalid_name.match(st.raw)
        if m:
            st.raw = ""
            notes.append(
                OptimizationNote(st.line, f"Removed invalid declaration `{m.group(1)}`.")
            )
    return stmts, notes


def _stmt_snapshot(stmts: List[_Stmt]) -> Tuple[str, ...]:
    return tuple(s.raw for s in stmts)


def _run_core_passes(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote], bool]:
    """Run one round of copy/const/merge/CSE/unused passes. Returns (stmts, notes, changed)."""
    before = _stmt_snapshot(stmts)
    notes: List[OptimizationNote] = []

    stmts, n = _copy_propagation(stmts)
    notes.extend(n)

    stmts, n = _constant_propagation_and_simplify(stmts)
    notes.extend(n)

    stmts, n = _merge_decl_assignments(stmts)
    notes.extend(n)

    stmts, n = _copy_propagation(stmts)
    notes.extend(n)

    stmts, n = _common_subexpr_elim(stmts)
    notes.extend(n)

    stmts, n = _remove_invalid_declarations(stmts)
    notes.extend(n)

    for _ in range(16):
        stmts, n = _remove_unused_variables(stmts)
        notes.extend(n)
        if not n:
            break

    stmts, n = _merge_decl_assignments(stmts)
    notes.extend(n)

    changed = _stmt_snapshot(stmts) != before
    return stmts, notes, changed


def _build_statements(code: str) -> List[_Stmt]:
    stmts: List[_Stmt] = []
    for ln, raw in enumerate(code.splitlines(), start=1):
        if raw.lstrip().startswith("#"):
            stmts.append(_Stmt(ln, raw, "preproc"))
            continue
        brace_delta = raw.count("{") - raw.count("}")
        st = _classify_stmt(ln, raw)
        st.brace_delta = brace_delta
        stmts.append(st)
    return stmts


def _optimize_statements(code: str) -> Tuple[str, List[OptimizationNote]]:
    """
    Optimize any straight-line C-like code by repeating the core passes until stable.
    """
    notes: List[OptimizationNote] = []
    stmts = _build_statements(code)

    stmts, dce_notes = _dead_code_elimination(stmts)
    notes.extend(dce_notes)

    for _ in range(24):
        stmts, pass_notes, changed = _run_core_passes(stmts)
        notes.extend(pass_notes)
        if not changed:
            break

    out = "\n".join([s.raw for s in stmts if s.raw.strip() != ""]).strip() + ("\n" if code.strip() else "")
    return out, notes


def _classify_stmt(ln: int, raw: str) -> _Stmt:
    s = raw.strip()
    if not s:
        return _Stmt(ln, raw, "other")

    if s.startswith("return"):
        return _Stmt(ln, raw, "return")

    toks = tokenize(raw)
    if toks and toks[0].kind == "Keyword" and toks[0].lexeme in _TYPE_KWS:
        for i, t in enumerate(toks):
            if t.kind == "Identifier":
                if i + 1 < len(toks) and toks[i + 1].lexeme == "(":
                    continue
                lhs = t.lexeme
                parts = _parse_assign_parts(raw)
                if parts:
                    prefix, plhs, rhs = parts
                    if plhs == lhs:
                        return _Stmt(ln, raw, "decl", declared=lhs, lhs=lhs, rhs=rhs)
                return _Stmt(ln, raw, "decl", declared=lhs, lhs=lhs)

    parts = _parse_assign_parts(raw)
    if parts:
        prefix, lhs, rhs = parts
        if prefix.strip() == "":
            return _Stmt(ln, raw, "assign", lhs=lhs, rhs=rhs)

    return _Stmt(ln, raw, "other")


def _dead_code_elimination(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    notes: List[OptimizationNote] = []
    out: List[_Stmt] = []
    depth = 0
    suppress_until_depth: Optional[int] = None

    for st in stmts:
        if suppress_until_depth is not None:
            if depth < suppress_until_depth:
                suppress_until_depth = None
            else:
                if st.raw.strip() and not st.raw.strip().startswith("}"):
                    notes.append(OptimizationNote(st.line, "Removed dead code after return."))
                    depth += st.brace_delta
                    continue

        out.append(st)

        if st.kind == "return":
            suppress_until_depth = depth

        depth += st.brace_delta

    return out, notes


def _transform_outside_strings(s: str, transform_segment) -> str:
    """Apply transform_segment only to code portions, not inside \"...\" literals."""
    if not s:
        return s
    parts: List[str] = []
    last = 0
    for m in _STRING_LITERAL_RE.finditer(s):
        if m.start() > last:
            parts.append(transform_segment(s[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    if last < len(s):
        parts.append(transform_segment(s[last:]))
    return "".join(parts)


def _resolve_copy(name: str, copies: Dict[str, str]) -> str:
    seen: Set[str] = set()
    while name in copies and name not in seen:
        seen.add(name)
        name = copies[name]
    return name


def _kill_copies(var: str, copies: Dict[str, str]) -> None:
    """Invalidate copy facts for var and any variable that copies it (transitively)."""
    dead: Set[str] = {var}
    changed = True
    while changed:
        changed = False
        for alias, source in list(copies.items()):
            if alias in dead or source in dead:
                if alias not in dead:
                    dead.add(alias)
                    changed = True
    for name in dead:
        copies.pop(name, None)


def _is_simple_copy(rhs: str) -> Optional[str]:
    rhs = rhs.strip()
    if not re.fullmatch(r"[A-Za-z_]\w*", rhs):
        return None
    if rhs in C_KEYWORDS:
        return None
    return rhs


def _replace_ident_copies(expr: str, copies: Dict[str, str]) -> str:
    if not copies:
        return expr

    def transform_segment(segment: str) -> str:
        def repl(m: re.Match[str]) -> str:
            name = m.group(0)
            if name in C_KEYWORDS:
                return name
            return _resolve_copy(name, copies)

        return re.sub(r"\b[A-Za-z_]\w*\b", repl, segment)

    return _transform_outside_strings(expr, transform_segment)


def _apply_copy_to_line(raw: str, copies: Dict[str, str]) -> str:
    if not copies or not raw.strip():
        return raw
    new_raw = _replace_ident_copies(raw, copies)
    return _normalize_spacing(new_raw) if new_raw != raw else raw


def _copy_propagation(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    """
    Copy propagation: if x = y, replace later uses of x with y (follow copy chains).
    Invalidates facts when a variable is reassigned.
    """
    notes: List[OptimizationNote] = []
    copies: Dict[str, str] = {}

    for st in stmts:
        if not st.raw.strip() or st.kind == "preproc":
            continue

        if _is_assign_like(st):
            parts = _parse_assign_parts(st.raw)
            if not parts:
                continue

            prefix, lhs, rhs = parts
            rhs_prop = _replace_ident_copies(rhs, copies)
            changed = rhs_prop != rhs

            _kill_copies(lhs, copies)

            src = _is_simple_copy(rhs_prop)
            new_line = _format_assign_line(prefix, lhs, rhs_prop)
            if new_line != _normalize_spacing(st.raw):
                st.raw = new_line
                if changed:
                    notes.append(
                        OptimizationNote(
                            st.line,
                            f"Copy propagated into `{lhs}` (replaced with `{rhs_prop}`).",
                        )
                    )

            if src is not None and src != lhs:
                copies[lhs] = _resolve_copy(src, copies)
            continue

        if st.kind in {"return", "other"}:
            new_raw = _apply_copy_to_line(st.raw, copies)
            if new_raw != st.raw:
                st.raw = new_raw
                notes.append(OptimizationNote(st.line, "Copy propagated in statement."))
            continue

        if st.kind == "decl" and st.declared and st.lhs is None:
            _kill_copies(st.declared, copies)

    return stmts, notes


def _constant_propagation_and_simplify(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    notes: List[OptimizationNote] = []
    consts: Dict[str, int] = {}

    for st in stmts:
        if not _is_assign_like(st):
            continue

        parts = _parse_assign_parts(st.raw)
        if not parts:
            continue

        prefix, lhs, rhs = parts

        rhs2 = _replace_ident_constants(rhs, consts)
        rhs3 = _simplify_expr(rhs2)
        val = _try_eval_int_expr(rhs3)
        if val is not None:
            rhs3 = str(val)
            consts[lhs] = val
            notes.append(OptimizationNote(st.line, f"Constant propagated: `{lhs}` is now {val}."))
        else:
            val2 = _try_eval_int_expr(rhs3)
            if val2 is not None:
                rhs3 = str(val2)
                consts[lhs] = val2
                notes.append(OptimizationNote(st.line, f"Constant propagated: `{lhs}` is now {val2}."))
            elif lhs in consts:
                del consts[lhs]

        if rhs3 == lhs and st.kind == "assign":
            st.raw = ""
            notes.append(OptimizationNote(st.line, "Removed no-op assignment (x = x)."))
            continue

        new_line = _format_assign_line(prefix, lhs, rhs3)
        if new_line != _normalize_spacing(st.raw):
            st.raw = new_line
            notes.append(OptimizationNote(st.line, "Applied constant propagation/simplification."))

    return stmts, notes


def _format_assign_line(prefix: str, lhs: str, rhs: str) -> str:
    line = f"{prefix}{lhs} = {rhs};"
    return _normalize_spacing(line)


def _replace_ident_constants(expr: str, consts: Dict[str, int]) -> str:
    if not consts:
        return expr

    def repl(m: re.Match[str]) -> str:
        name = m.group(0)
        if name in consts:
            return str(consts[name])
        return name

    return re.sub(r"\b[A-Za-z_]\w*\b", repl, expr)


def _simplify_expr(expr: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_+\-*/%() \t]+", expr):
        return expr
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError:
        return expr

    def simp(n):
        if isinstance(n, ast.Expression):
            return ast.Expression(body=simp(n.body))
        if isinstance(n, ast.Constant):
            return n
        if isinstance(n, ast.Name):
            return n
        if isinstance(n, ast.UnaryOp):
            operand = simp(n.operand)
            if isinstance(n.op, ast.USub) and isinstance(operand, ast.Constant) and isinstance(
                operand.value, (int, float)
            ):
                return ast.Constant(value=-operand.value)
            if isinstance(n.op, ast.UAdd):
                return operand
            return ast.UnaryOp(op=n.op, operand=operand)
        if isinstance(n, ast.BinOp):
            left = simp(n.left)
            right = simp(n.right)

            if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
                v = _try_eval_int_expr(ast.unparse(ast.Expression(ast.BinOp(left=left, op=n.op, right=right))))
                if v is not None:
                    return ast.Constant(value=v)

            if isinstance(n.op, ast.Add):
                if _is_zero(right):
                    return left
                if _is_zero(left):
                    return right
            if isinstance(n.op, ast.Sub):
                if _is_zero(right):
                    return left
            if isinstance(n.op, ast.Mult):
                if _is_one(right):
                    return left
                if _is_one(left):
                    return right
                if _is_zero(right) or _is_zero(left):
                    return ast.Constant(value=0)
            if isinstance(n.op, (ast.Div, ast.FloorDiv)):
                if _is_one(right):
                    return left

            if (
                isinstance(n.op, ast.Add)
                and isinstance(right, ast.Constant)
                and isinstance(left, ast.BinOp)
                and isinstance(left.op, ast.Add)
            ):
                if isinstance(left.right, ast.Constant):
                    return ast.BinOp(
                        left=left.left,
                        op=ast.Add(),
                        right=ast.Constant(value=left.right.value + right.value),
                    )
            if (
                isinstance(n.op, ast.Mult)
                and isinstance(right, ast.Constant)
                and isinstance(left, ast.BinOp)
                and isinstance(left.op, ast.Mult)
            ):
                if isinstance(left.right, ast.Constant):
                    return ast.BinOp(
                        left=left.left,
                        op=ast.Mult(),
                        right=ast.Constant(value=left.right.value * right.value),
                    )

            return ast.BinOp(left=left, op=n.op, right=right)
        return n

    def _is_zero(n) -> bool:
        return isinstance(n, ast.Constant) and n.value == 0

    def _is_one(n) -> bool:
        return isinstance(n, ast.Constant) and n.value == 1

    try:
        simplified = simp(node)
        out = ast.unparse(simplified).strip()
        return out.replace("**", "^")
    except Exception:
        return expr


def _try_eval_int_expr(expr: str) -> Optional[int]:
    if re.search(r"\b[A-Za-z_]\w*\b", expr):
        return None
    if not re.fullmatch(r"[0-9+\-*/%() \t]+", expr):
        return None
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    for n in ast.walk(node):
        if not isinstance(n, _ALLOWED_AST_NODES):
            return None
    try:
        v = eval(compile(node, "<opt>", "eval"), {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(v, (int, float)) and float(v).is_integer():
        return int(v)
    return None


def _common_subexpr_elim(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    notes: List[OptimizationNote] = []
    var_version: Dict[str, int] = {}
    expr_to_var: Dict[str, Tuple[str, Dict[str, int]]] = {}

    def bump(var: str) -> None:
        var_version[var] = var_version.get(var, 0) + 1

    def versions_for(vars_used: Set[str]) -> Dict[str, int]:
        return {v: var_version.get(v, 0) for v in vars_used}

    for st in stmts:
        if not _is_assign_like(st):
            continue

        parts = _parse_assign_parts(st.raw)
        if not parts:
            continue

        prefix, lhs, rhs = parts

        if "(" in rhs or ")" in rhs:
            bump(lhs)
            continue

        vars_used = {
            t.lexeme for t in tokenize(rhs) if t.kind == "Identifier" and t.lexeme not in C_KEYWORDS
        }
        key = _normalize_expr_key(rhs)

        if key in expr_to_var:
            prev_var, prev_versions = expr_to_var[key]
            if prev_versions == versions_for(vars_used) and prev_var != lhs:
                st.raw = _format_assign_line(prefix, lhs, prev_var)
                notes.append(OptimizationNote(st.line, f"Common subexpression eliminated (reused `{prev_var}`)."))

        expr_to_var[key] = (lhs, versions_for(vars_used))
        bump(lhs)

    return stmts, notes


def _normalize_expr_key(rhs: str) -> str:
    return _normalize_spacing(rhs).replace(" ", "")


def _identifiers_in_stmt(st: _Stmt) -> Set[str]:
    if not st.raw.strip():
        return set()
    toks = tokenize(st.raw)
    names: Set[str] = set()
    for t in toks:
        if t.kind != "Identifier" or t.lexeme in C_KEYWORDS:
            continue
        if st.kind == "decl" and st.declared == t.lexeme:
            continue
        names.add(t.lexeme)
    return names


def _remove_unused_variables(stmts: List[_Stmt]) -> Tuple[List[_Stmt], List[OptimizationNote]]:
    notes: List[OptimizationNote] = []

    declared: Dict[str, int] = {}
    for st in stmts:
        if st.kind == "decl" and st.declared and st.raw.strip():
            declared[st.declared] = st.line

    used: Set[str] = set()
    for st in stmts:
        if not st.raw.strip():
            continue
        if st.kind in {"preproc", "return", "other"}:
            used |= _identifiers_in_stmt(st)
        elif _is_assign_like(st):
            parts = _parse_assign_parts(st.raw)
            if parts:
                _, lhs, rhs = parts
                used |= _identifiers_in_rhs(rhs)
                if st.kind == "assign":
                    used.discard(lhs)
        else:
            used |= _identifiers_in_stmt(st)

    unused = {name for name in declared if name not in used}
    if not unused:
        return stmts, notes

    changed = False
    for st in stmts:
        if st.kind == "decl" and st.declared in unused:
            st.raw = ""
            notes.append(OptimizationNote(st.line, f"Removed unused variable declaration `{st.declared}`."))
            changed = True
            continue
        if st.kind == "assign" and st.lhs in unused:
            st.raw = ""
            notes.append(OptimizationNote(st.line, f"Removed assignment to unused variable `{st.lhs}`."))
            changed = True

    if not changed:
        return stmts, []
    return stmts, notes


def _identifiers_in_rhs(rhs: str) -> Set[str]:
    return {t.lexeme for t in tokenize(rhs) if t.kind == "Identifier" and t.lexeme not in C_KEYWORDS}
