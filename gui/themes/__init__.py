from __future__ import annotations

from pathlib import Path


def load_stylesheet(dark: bool) -> str:
    name = "dark.qss" if dark else "light.qss"
    path = Path(__file__).parent / name
    return path.read_text(encoding="utf-8")
