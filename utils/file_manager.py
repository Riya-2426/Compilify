from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PyQt5.QtWidgets import QFileDialog, QWidget


@dataclass
class FileResult:
    path: Optional[str]
    content: Optional[str]


def open_c_file(parent: QWidget) -> FileResult:
    path, _ = QFileDialog.getOpenFileName(parent, "Open C File", "", "C Files (*.c);;All Files (*.*)")
    if not path:
        return FileResult(None, None)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return FileResult(path, f.read())


def save_file(parent: QWidget, path: str, content: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(content)
        return True
    except OSError:
        return False


def save_as(parent: QWidget, content: str) -> Tuple[Optional[str], bool]:
    path, _ = QFileDialog.getSaveFileName(parent, "Save As", "", "C Files (*.c);;All Files (*.*)")
    if not path:
        return None, False
    ok = save_file(parent, path, content)
    return path, ok

