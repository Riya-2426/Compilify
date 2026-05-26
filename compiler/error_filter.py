"""Filter GCC cascade errors and identify root-cause lines."""
from __future__ import annotations

from typing import List, Tuple

ErrorTriple = Tuple[int, str, str]


_CASCADE_MSG_PARTS = (
    "expected expression",
    "expected declaration or statement",
    "expected ';' before",
    "expected '}'",
    "expected ')'",
    "expected '{'",
    "expected statement",
    "invalid suffix",
    "stray '@'",
)


def _raw_gcc_message(message: str) -> str:
    if message.startswith("Syntax Error: "):
        return message[len("Syntax Error: ") :]
    return message


def _is_root_syntax_message(raw: str) -> bool:
    m = raw.lower()
    return "missing terminating" in m or "unterminated" in m


def find_root_error_lines(lex_errs: List[ErrorTriple], syn_errs: List[ErrorTriple]) -> List[int]:
    """Lines that are likely primary causes (not GCC cascade)."""
    roots: List[int] = [ln for ln, _, _ in lex_errs]
    for ln, msg, _ in syn_errs:
        if _is_root_syntax_message(_raw_gcc_message(msg)):
            roots.append(ln)
    return sorted(set(roots))


def is_likely_cascade_gcc_error(raw_msg: str) -> bool:
    m = raw_msg.lower()
    if _is_root_syntax_message(raw_msg):
        return False
    return any(part in m for part in _CASCADE_MSG_PARTS)


def filter_cascade_syntax_errors(
    syn_errs: List[ErrorTriple],
    root_lines: List[int],
) -> Tuple[List[ErrorTriple], str]:
    """
    Drop GCC errors on lines after a root error that look like parser fallout.
    Returns (filtered_errors, optional_note_for_gui).
    """
    if not root_lines or not syn_errs:
        return syn_errs, ""

    earliest_root = min(root_lines)
    kept: List[ErrorTriple] = []
    suppressed = 0

    for ln, msg, sug in syn_errs:
        raw = _raw_gcc_message(msg)
        if ln > earliest_root and is_likely_cascade_gcc_error(raw):
            suppressed += 1
            continue
        kept.append((ln, msg, sug))

    note = ""
    if suppressed:
        note = (
            f"Note: {suppressed} extra syntax message(s) on later lines were hidden — "
            f"they are usually caused by the error near line {earliest_root}. Fix that first."
        )
    return kept, note
