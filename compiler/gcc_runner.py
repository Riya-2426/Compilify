from __future__ import annotations

import os
import re
import subprocess
from typing import List, Tuple


_GCC_ERR_RE = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+):\s+error:\s+(?P<msg>.*)$")


def compile_with_gcc(source_path: str, out_path: str) -> List[Tuple[int, str]]:
    cmd = ["gcc", source_path, "-o", out_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return [(1, "Syntax Error: `gcc` not found on PATH. Install MinGW-w64 and ensure gcc is available.")]

    errors: List[Tuple[int, str]] = []
    stderr = proc.stderr or ""
    for line in stderr.splitlines():
        m = _GCC_ERR_RE.match(line.strip())
        if m:
            ln = int(m.group("line"))
            msg = m.group("msg").strip()
            errors.append((ln, f"Syntax Error: {msg}"))

    errors.sort(key=lambda x: x[0])
    return errors


def run_executable(
    exe_path: str,
    cwd: str | None = None,
    stdin_text: str | None = None,
    timeout_s: float | None = 5.0,
) -> subprocess.CompletedProcess:
    if cwd is None:
        cwd = os.path.dirname(os.path.abspath(exe_path))
    return subprocess.run(
        [exe_path],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        input=stdin_text,
        timeout=timeout_s,
    )

