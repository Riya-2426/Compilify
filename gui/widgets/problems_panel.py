from __future__ import annotations

from typing import Callable, List, Optional, Protocol

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class CompileMessageLike(Protocol):
    line: int
    kind: str
    message: str
    suggestion: str


class ProblemsPanel(QWidget):
    """Problems list with a separate suggestion/details view."""

    def __init__(self, parent=None, on_jump: Optional[Callable[[int], None]] = None):
        super().__init__(parent)
        self._on_jump = on_jump
        self._messages: List[CompileMessageLike] = []

        self._table = QTableWidget(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Line", "Kind", "Message"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        detail = QFrame(self)
        detail.setObjectName("panel")
        detail_lay = QVBoxLayout(detail)
        detail_lay.setContentsMargins(10, 10, 10, 10)
        detail_lay.setSpacing(8)

        self._detail_title = QLabel("Select a problem to see details.", detail)
        self._detail_title.setWordWrap(True)
        self._detail_title.setObjectName("panelTitle")

        self._detail_text = QPlainTextEdit(detail)
        self._detail_text.setReadOnly(True)
        self._detail_text.setPlaceholderText("Suggestion/details will appear here…")

        detail_lay.addWidget(self._detail_title)
        detail_lay.addWidget(self._detail_text, 1)

        split = QSplitter(Qt.Vertical, self)
        split.addWidget(self._table)
        split.addWidget(detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(split)

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if not item or not self._on_jump:
            return
        text = item.text().strip()
        if text in {"", "—"}:
            return
        try:
            self._on_jump(int(text))
        except ValueError:
            pass

    def _on_selection_changed(self) -> None:
        items = self._table.selectedItems()
        if not items:
            self._detail_title.setText("Select a problem to see details.")
            self._detail_text.setPlainText("")
            return
        row = items[0].row()
        if row < 0 or row >= len(self._messages):
            return
        m = self._messages[row]
        line = f"Line {m.line}" if m.line > 0 else "Info"
        self._detail_title.setText(f"{line} • {m.kind} — {m.message}")
        self._detail_text.setPlainText(m.suggestion or "No suggestion available.")

    def set_messages(
        self,
        messages: List[CompileMessageLike],
        kind_colors: dict,
        dark_mode: bool,
    ) -> None:
        self._messages = list(messages)
        self._table.setRowCount(len(messages))
        muted = QColor("#64748b") if not dark_mode else QColor("#8b949e")
        for r, m in enumerate(messages):
            line_text = str(m.line) if m.line > 0 else "—"
            self._table.setItem(r, 0, QTableWidgetItem(line_text))
            kind_item = QTableWidgetItem(m.kind)
            kind_item.setForeground(kind_colors.get(m.kind, muted))
            self._table.setItem(r, 1, kind_item)
            self._table.setItem(r, 2, QTableWidgetItem(m.message))

        self._table.resizeColumnsToContents()
        if messages:
            self._table.selectRow(0)
            self._on_selection_changed()
        else:
            self._detail_title.setText("No problems.")
            self._detail_text.setPlainText("")

    def clear_all(self) -> None:
        self._messages = []
        self._table.setRowCount(0)
        self._detail_title.setText("No problems.")
        self._detail_text.setPlainText("")
