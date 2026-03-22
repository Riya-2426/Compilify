from __future__ import annotations

import re
from typing import List, Optional, Tuple

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QSyntaxHighlighter,
)
from PyQt5.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.line_number_area_paint_event(event)


class CSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)

        self._rules: List[Tuple[re.Pattern, QTextCharFormat]] = []

        def fmt(color: str, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            return f

        keyword_format = fmt("#569CD6", bold=True)
        type_format = fmt("#4EC9B0", bold=True)
        number_format = fmt("#B5CEA8")
        string_format = fmt("#CE9178")
        comment_format = fmt("#6A9955")
        preproc_format = fmt("#C586C0", bold=True)

        keywords = [
            "auto",
            "break",
            "case",
            "const",
            "continue",
            "default",
            "do",
            "else",
            "enum",
            "extern",
            "for",
            "goto",
            "if",
            "inline",
            "register",
            "restrict",
            "return",
            "sizeof",
            "static",
            "struct",
            "switch",
            "typedef",
            "union",
            "volatile",
            "while",
        ]
        types = ["void", "char", "short", "int", "long", "float", "double", "signed", "unsigned", "bool"]

        for kw in keywords:
            self._rules.append((re.compile(rf"\b{re.escape(kw)}\b"), keyword_format))
        for tp in types:
            self._rules.append((re.compile(rf"\b{re.escape(tp)}\b"), type_format))

        self._rules.append((re.compile(r"\b\d+(?:\.\d+)?\b"), number_format))
        self._rules.append((re.compile(r'"(?:\\.|[^"\\])*"'), string_format))
        self._rules.append((re.compile(r"'(?:\\.|[^'\\])'"), string_format))
        self._rules.append((re.compile(r"//[^\n]*"), comment_format))
        self._rules.append((re.compile(r"/\*[\s\S]*?\*/"), comment_format))
        self._rules.append((re.compile(r"^\s*#\s*\w+.*$"), preproc_format))

    def highlightBlock(self, text: str) -> None:
        for pattern, f in self._rules:
            for m in pattern.finditer(text):
                start = m.start()
                length = m.end() - m.start()
                self.setFormat(start, length, f)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._error_line_set: set[int] = set()
        self._error_color = QColor(255, 80, 80, 60)

        self._line_number_area = LineNumberArea(self)
        self._highlighter = CSyntaxHighlighter(self.document())

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_area_width(0)
        self._highlight_current_line()

        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.setFont(font)

        metrics = self.fontMetrics()
        self.setTabStopDistance(4 * metrics.horizontalAdvance(" "))

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def _update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(30, 30, 30, 30))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(140, 140, 140))
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        extra_selections = self.extraSelections()

        selection = QTextCursor(self.textCursor())
        selection.clearSelection()

        line_sel = QTextCursor(self.textCursor())
        line_sel.clearSelection()

        base = QColor(80, 80, 80, 30)
        fmt = QTextCharFormat()
        fmt.setBackground(base)

        sel = self._make_line_selection(self.textCursor().blockNumber() + 1, fmt)
        extras: List = [sel] if sel is not None else []

        for ln in sorted(self._error_line_set):
            ef = QTextCharFormat()
            ef.setBackground(self._error_color)
            s = self._make_line_selection(ln, ef)
            if s is not None:
                extras.append(s)

        self.setExtraSelections(extras)

    def _make_line_selection(self, line_number_1based: int, fmt: QTextCharFormat):
        if line_number_1based < 1:
            return None
        block = self.document().findBlockByNumber(line_number_1based - 1)
        if not block.isValid():
            return None
        c = QTextCursor(block)
        c.clearSelection()
        sel = QTextEdit.ExtraSelection()
        sel.cursor = c
        sel.format = fmt
        sel.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        return sel

    def set_error_lines(self, lines: List[int], color: Optional[QColor] = None) -> None:
        self._error_line_set = set(lines)
        if color is not None:
            self._error_color = color
        self._highlight_current_line()

    def clear_error_lines(self) -> None:
        self._error_line_set.clear()
        self._highlight_current_line()

    def scroll_to_line(self, line_number_1based: int) -> None:
        block = self.document().findBlockByNumber(max(0, line_number_1based - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

