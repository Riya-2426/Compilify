from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QTextBlockUserData, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QProgressDialog,
)

from compiler.gcc_runner import compile_with_gcc, run_executable
from compiler.lexer import lexical_analysis, tokens_as_rows
from compiler.semantic import semantic_check
from compiler.symbol_table import symbol_rows_for_gui
from gui.editor import CodeEditor
from utils.file_manager import open_c_file, save_as, save_file


@dataclass(frozen=True)
class CompileMessage:
    line: int
    kind: str
    message: str


ERROR_COLORS_LIGHT = {
    "Lexical": QColor("#B8860B"),
    "Semantic": QColor("#CC6600"),
    "Syntax": QColor("#C62828"),
    "Info": QColor("#1565C0"),
}

ERROR_COLORS_DARK = {
    "Lexical": QColor("#FFD54A"),
    "Semantic": QColor("#FFB74D"),
    "Syntax": QColor("#EF5350"),
    "Info": QColor("#9CDCFE"),
}


def _light_stylesheet() -> str:
    return """
QMainWindow { background: #e8e8e8; }
QMenuBar { background: #f0f0f0; color: #222; border-bottom: 1px solid #ccc; }
QMenuBar::item:selected { background: #d0d0d0; }
QMenu { background: #fff; color: #222; border: 1px solid #ccc; }
QMenu::item:selected { background: #e0e8f0; }
QToolBar {
  background: #f5f5f5;
  border: none;
  border-bottom: 1px solid #ccc;
  spacing: 8px;
  padding: 6px 8px;
}
QToolBar QToolButton {
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 6px;
  padding: 6px 12px;
  color: #222;
}
QToolBar QToolButton:hover { background: #eef6ff; border-color: #99c; }
QStatusBar { background: #f0f0f0; color: #333; border-top: 1px solid #ccc; }
QFrame#panel { background: #fff; border: 1px solid #ccc; border-radius: 4px; }
QLabel#panelTitle { font-weight: bold; color: #333; padding: 4px; }
QPlainTextEdit {
  background: #fff;
  color: #111;
  border: 1px solid #ccc;
  border-radius: 2px;
}
QTableWidget {
  background: #fff;
  color: #111;
  gridline-color: #ccc;
  alternate-background-color: #e8f4fc;
}
QHeaderView::section {
  background: #e8e8e8;
  color: #222;
  padding: 6px;
  border: 1px solid #ccc;
  font-weight: bold;
}
QPushButton {
  background: #fff;
  border: 1px solid #bbb;
  border-radius: 6px;
  padding: 6px 14px;
  color: #222;
}
QPushButton:hover { background: #eef6ff; }
QCheckBox { color: #222; }
"""


def _dark_stylesheet() -> str:
    return """
QMainWindow { background: #1e1e1e; }
QMenuBar { background: #252526; color: #d4d4d4; border-bottom: 1px solid #333; }
QMenuBar::item:selected { background: #333; }
QMenu { background: #252526; color: #d4d4d4; }
QMenu::item:selected { background: #333; }
QToolBar { background: #252526; border-bottom: 1px solid #333; spacing: 8px; padding: 6px; }
QToolBar QToolButton {
  background: #333;
  border: 1px solid #444;
  border-radius: 6px;
  padding: 6px 12px;
  color: #d4d4d4;
}
QToolBar QToolButton:hover { background: #3a3a3a; }
QStatusBar { background: #252526; color: #d4d4d4; border-top: 1px solid #333; }
QFrame#panel { background: #252526; border: 1px solid #333; border-radius: 4px; }
QLabel#panelTitle { font-weight: bold; color: #ccc; padding: 4px; }
QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; border: 1px solid #333; }
QTableWidget { background: #1e1e1e; color: #d4d4d4; gridline-color: #333; alternate-background-color: #2a2d2e; }
QHeaderView::section { background: #333; color: #d4d4d4; border: 1px solid #444; padding: 6px; }
QPushButton { background: #333; color: #d4d4d4; border: 1px solid #444; border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { background: #3a3a3a; }
QCheckBox { color: #d4d4d4; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Compiler GUI")
        self.resize(1280, 820)

        self._current_path: Optional[str] = None
        self._last_build_dir: Optional[str] = None
        self._last_exe_path: Optional[str] = None
        self._compile_messages: List[CompileMessage] = []
        self._dark_mode = False
        self._block_dark_sync = False

        self._editor = CodeEditor(self)
        self._output = QPlainTextEdit(self)
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Compiler messages and program output appear here…")
        out_font = QFont("Consolas")
        out_font.setStyleHint(QFont.Monospace)
        out_font.setPointSize(10)
        self._output.setFont(out_font)

        self._tokens = QTableWidget(self)
        self._tokens.setColumnCount(4)
        self._tokens.setHorizontalHeaderLabels(["Type", "Lexeme", "Line", "Col"])
        self._tokens.verticalHeader().setVisible(False)
        self._tokens.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tokens.setSelectionBehavior(QTableWidget.SelectRows)
        self._tokens.setAlternatingRowColors(True)
        self._tokens.cellDoubleClicked.connect(self._jump_to_token)

        self._symbol_table = QTableWidget(self)
        self._symbol_table.setColumnCount(5)
        self._symbol_table.setHorizontalHeaderLabels(["Name", "Type", "Value", "Scope", "Uses"])
        self._symbol_table.verticalHeader().setVisible(False)
        self._symbol_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._symbol_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._symbol_table.setAlternatingRowColors(True)

        self._build_layout()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()

        self._editor.cursorPositionChanged.connect(self._update_status_cursor)
        self._editor.textChanged.connect(self._on_text_changed)
        self._update_status_cursor()
        self._on_text_changed()

        self._apply_theme()

    def _panel(self) -> QFrame:
        f = QFrame(self)
        f.setObjectName("panel")
        f.setFrameShape(QFrame.StyledPanel)
        return f

    def _build_layout(self) -> None:
        style = self.style()

        # Left: header + editor
        left_wrap = self._panel()
        left_lay = QVBoxLayout(left_wrap)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)

        ed_header = QHBoxLayout()
        btn_compile = QPushButton(style.standardIcon(QStyle.SP_DialogApplyButton), " Compile", self)
        btn_compile.clicked.connect(self.compile_code)
        btn_clear_ed = QPushButton(style.standardIcon(QStyle.SP_TrashIcon), " Clear Output", self)
        btn_clear_ed.clicked.connect(self.clear_output)
        ed_header.addWidget(btn_compile)
        ed_header.addWidget(btn_clear_ed)
        ed_header.addStretch(1)
        left_lay.addLayout(ed_header)
        left_lay.addWidget(self._editor, 1)

        # Right top: Output Terminal
        out_wrap = self._panel()
        out_lay = QVBoxLayout(out_wrap)
        out_lay.setContentsMargins(8, 8, 8, 8)
        out_lay.setSpacing(6)
        out_head = QHBoxLayout()
        out_title = QLabel("Output Terminal", self)
        out_title.setObjectName("panelTitle")
        btn_clear_out = QPushButton(style.standardIcon(QStyle.SP_TrashIcon), " Clear", self)
        btn_clear_out.clicked.connect(self.clear_output)
        out_head.addWidget(out_title)
        out_head.addStretch(1)
        out_head.addWidget(btn_clear_out)
        out_lay.addLayout(out_head)
        out_lay.addWidget(self._output, 1)

        # Right bottom: Symbol Table
        sym_wrap = self._panel()
        sym_lay = QVBoxLayout(sym_wrap)
        sym_lay.setContentsMargins(8, 8, 8, 8)
        sym_lay.setSpacing(6)
        sym_title = QLabel("Symbol Table", self)
        sym_title.setObjectName("panelTitle")
        sym_lay.addWidget(sym_title)
        sym_lay.addWidget(self._symbol_table, 1)

        # Tokens (lexical) — bottom of symbol area or separate? Image shows Symbol Table only.
        # Keep tokens in a tab under output OR stack tokens below symbol. Reference had tokens table.
        # Advanced GUI image: only Symbol Table on bottom right. We use symbol table + hide tokens in splitter
        # OR put tokens in a third tab. User asked for "like this" — Symbol Table bottom, Output top.
        # Add lexical tokens as a small third row or tabs. Simpler: vertical split: output | tokens+symbol
        # Re-read: first user image had Output + lexical table. Advanced image has Output Terminal + Symbol Table.
        # I'll stack: Output, then row with horizontal split: Tokens (left) | Symbol (right) — too busy.
        # Best: right column = Output (top), bottom = horizontal split Tokens | Symbol — still complex.
        # Simplest match Advanced: only Symbol Table bottom. Move tokens to View menu or keep under symbol.
        # I'll put Tokens table below Symbol in same panel with a label "Lexical Tokens" — actually that duplicates.
        # Keep structure: Output top half, bottom half = horizontal: Lexical (left) Symbol (right)
        tokens_wrap = self._panel()
        tok_lay = QVBoxLayout(tokens_wrap)
        tok_lay.setContentsMargins(8, 8, 8, 8)
        tok_title = QLabel("Lexical Tokens", self)
        tok_title.setObjectName("panelTitle")
        tok_lay.addWidget(tok_title)
        tok_lay.addWidget(self._tokens, 1)

        right_bottom = QSplitter(Qt.Horizontal, self)
        right_bottom.addWidget(tokens_wrap)
        right_bottom.addWidget(sym_wrap)
        right_bottom.setStretchFactor(0, 1)
        right_bottom.setStretchFactor(1, 1)

        right_split = QSplitter(Qt.Vertical, self)
        right_split.addWidget(out_wrap)
        right_split.addWidget(right_bottom)
        right_split.setStretchFactor(0, 2)
        right_split.setStretchFactor(1, 2)

        main_split = QSplitter(Qt.Horizontal, self)
        main_split.addWidget(left_wrap)
        main_split.addWidget(right_split)
        main_split.setStretchFactor(0, 58)
        main_split.setStretchFactor(1, 42)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        layout.addWidget(main_split)
        self.setCentralWidget(container)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        self._act_open = QAction("Open...", self)
        self._act_open.triggered.connect(self.open_file)
        file_menu.addAction(self._act_open)
        self._act_save = QAction("Save", self)
        self._act_save.triggered.connect(self.save_file)
        file_menu.addAction(self._act_save)
        self._act_save_as = QAction("Save As...", self)
        self._act_save_as.triggered.connect(self.save_file_as)
        file_menu.addAction(self._act_save_as)
        file_menu.addSeparator()
        self._act_exit = QAction("Exit", self)
        self._act_exit.triggered.connect(self.close)
        file_menu.addAction(self._act_exit)

        view_menu = menubar.addMenu("&View")
        self._act_dark = QAction("Dark Mode", self, checkable=True)
        self._act_dark.setChecked(False)
        self._act_dark.triggered.connect(self._toggle_dark_from_menu)
        view_menu.addAction(self._act_dark)

        run_menu = menubar.addMenu("&Run")
        run_menu.addAction("Compile", self.compile_code)
        run_menu.addAction("Run Program", self.run_program)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(tb)
        st = self.style()

        a_compile = QAction(st.standardIcon(QStyle.SP_DialogApplyButton), "Compile", self)
        a_compile.triggered.connect(self.compile_code)
        tb.addAction(a_compile)

        a_run = QAction(st.standardIcon(QStyle.SP_MediaPlay), "Run", self)
        a_run.triggered.connect(self.run_program)
        tb.addAction(a_run)

        a_clear = QAction(st.standardIcon(QStyle.SP_TrashIcon), "Clear Output", self)
        a_clear.triggered.connect(self.clear_output)
        tb.addAction(a_clear)

        tb.addSeparator()
        self._chk_dark = QCheckBox(" Dark", self)
        self._chk_dark.setChecked(False)
        self._chk_dark.stateChanged.connect(self._on_dark_checkbox)
        tb.addWidget(self._chk_dark)

    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self._lbl_pos = QLabel("Ln 1, Col 1", self)
        sb.addPermanentWidget(self._lbl_pos)

    def _error_colors(self) -> dict:
        return ERROR_COLORS_DARK if self._dark_mode else ERROR_COLORS_LIGHT

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if self._dark_mode:
            app.setStyleSheet(_dark_stylesheet())
        else:
            app.setStyleSheet(_light_stylesheet())
        self._populate_symbol_table(self._editor.toPlainText())

    def _toggle_dark_from_menu(self) -> None:
        self._dark_mode = self._act_dark.isChecked()
        self._sync_dark_widgets()
        self._apply_theme()

    def _on_dark_checkbox(self) -> None:
        if self._block_dark_sync:
            return
        self._dark_mode = self._chk_dark.isChecked()
        self._block_dark_sync = True
        try:
            self._act_dark.setChecked(self._dark_mode)
        finally:
            self._block_dark_sync = False
        self._apply_theme()

    def _sync_dark_widgets(self) -> None:
        self._block_dark_sync = True
        try:
            self._chk_dark.setChecked(self._dark_mode)
            self._act_dark.setChecked(self._dark_mode)
        finally:
            self._block_dark_sync = False

    def _update_status_cursor(self) -> None:
        c = self._editor.textCursor()
        ln = c.blockNumber() + 1
        col = c.positionInBlock() + 1
        self._lbl_pos.setText(f"Ln {ln}, Col {col}")

    def _on_text_changed(self) -> None:
        code = self._editor.toPlainText()
        _, tokens = lexical_analysis(code)
        self._populate_tokens(tokens_as_rows(tokens))
        self._populate_symbol_table(code)

    def _populate_tokens(self, rows: List[Tuple[str, str, int, int]]) -> None:
        self._tokens.setRowCount(len(rows))
        for r, (kind, lex, ln, col) in enumerate(rows):
            self._tokens.setItem(r, 0, QTableWidgetItem(kind))
            self._tokens.setItem(r, 1, QTableWidgetItem(lex))
            self._tokens.setItem(r, 2, QTableWidgetItem(str(ln)))
            self._tokens.setItem(r, 3, QTableWidgetItem(str(col)))
        self._tokens.resizeColumnsToContents()

    def _populate_symbol_table(self, code: str) -> None:
        rows = symbol_rows_for_gui(code)
        self._symbol_table.setRowCount(len(rows))
        value_color = QColor("#b45309") if not self._dark_mode else QColor("#fbbf24")
        for r, (name, typ, val, scope, uses) in enumerate(rows):
            self._symbol_table.setItem(r, 0, QTableWidgetItem(name))
            self._symbol_table.setItem(r, 1, QTableWidgetItem(typ))
            v = QTableWidgetItem(val)
            v.setForeground(value_color)
            self._symbol_table.setItem(r, 2, v)
            self._symbol_table.setItem(r, 3, QTableWidgetItem(scope))
            self._symbol_table.setItem(r, 4, QTableWidgetItem(uses))
        self._symbol_table.resizeColumnsToContents()

    def _jump_to_token(self, row: int, _col: int) -> None:
        item = self._tokens.item(row, 2)
        if not item:
            return
        try:
            ln = int(item.text())
        except ValueError:
            return
        self._editor.scroll_to_line(ln)

    def clear_output(self) -> None:
        self._output.clear()
        self._compile_messages = []
        self._editor.clear_error_lines()

    def _append_output(self, text: str) -> None:
        if not text.endswith("\n"):
            text += "\n"
        self._output.moveCursor(QTextCursor.End)
        self._output.insertPlainText(text)
        self._output.moveCursor(QTextCursor.End)

    def open_file(self) -> None:
        res = open_c_file(self)
        if not res.path:
            return
        self._current_path = res.path
        self._editor.setPlainText(res.content or "")
        self.statusBar().showMessage(f"Opened {os.path.basename(res.path)}", 3000)

    def save_file(self) -> None:
        code = self._editor.toPlainText()
        if not code.strip():
            QMessageBox.information(self, "Empty", "Editor is empty. Nothing to save.")
            return
        if not self._current_path:
            self.save_file_as()
            return
        ok = save_file(self, self._current_path, code)
        if ok:
            self.statusBar().showMessage("Saved", 2000)
        else:
            QMessageBox.warning(self, "Save failed", "Could not save file.")

    def save_file_as(self) -> None:
        code = self._editor.toPlainText()
        if not code.strip():
            QMessageBox.information(self, "Empty", "Editor is empty. Nothing to save.")
            return
        path, ok = save_as(self, code)
        if not path:
            return
        if ok:
            self._current_path = path
            self.statusBar().showMessage("Saved As", 2000)
        else:
            QMessageBox.warning(self, "Save failed", "Could not save file.")

    def compile_code(self) -> None:
        code = self._editor.toPlainText()
        self.clear_output()

        if not code.strip():
            self._append_output("Info: No input provided.")
            QMessageBox.information(self, "Empty input", "Please type or open a C program first.")
            return

        dlg = QProgressDialog("Compiling...", None, 0, 0, self)
        dlg.setWindowTitle("Advanced Compiler GUI")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.show()
        QApplication.processEvents()

        try:
            self._last_build_dir = tempfile.mkdtemp(prefix="ccompiler_gui_")
            src_path = os.path.join(self._last_build_dir, "temp.c")
            exe_path = os.path.join(self._last_build_dir, "temp.exe")
            with open(src_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(code)

            lex_errs, tokens = lexical_analysis(code)
            sem_errs = semantic_check(code)
            syn_errs = compile_with_gcc(src_path, exe_path)

            messages: List[CompileMessage] = []
            for ln, msg in lex_errs:
                messages.append(CompileMessage(ln, "Lexical", msg))
            for ln, msg in sem_errs:
                messages.append(CompileMessage(ln, "Semantic", msg))
            for ln, msg in syn_errs:
                messages.append(CompileMessage(ln, "Syntax", msg))

            messages.sort(key=lambda m: (m.line, m.kind))
            self._compile_messages = messages

            self._populate_tokens(tokens_as_rows(tokens))
            self._populate_symbol_table(code)

            if not messages:
                self._append_output("Output:\n")
                self._append_output("Success: No errors found. Compilation succeeded.")
                self.statusBar().showMessage("Compile succeeded", 3000)
                self._last_exe_path = exe_path
                self._editor.clear_error_lines()
                return

            self._render_messages(messages)
            self._highlight_error_lines(messages)

            first = messages[0]
            self._editor.scroll_to_line(first.line)
            self.statusBar().showMessage(f"Compile found {len(messages)} issue(s)", 4000)
        finally:
            dlg.close()

    def _render_messages(self, messages: List[CompileMessage]) -> None:
        self._output.clear()
        for m in messages:
            self._append_output(f"Line {m.line} → {m.message}")

        self._apply_output_coloring(messages)

    def _apply_output_coloring(self, messages: List[CompileMessage]) -> None:
        doc = self._output.document()
        cursor = self._output.textCursor()
        colors = self._error_colors()
        cursor.beginEditBlock()
        try:
            block = doc.firstBlock()
            i = 0
            while block.isValid() and i < len(messages):
                m = messages[i]
                fmt = QTextCharFormat()
                fmt.setForeground(colors.get(m.kind, QColor("#111" if not self._dark_mode else "#d4d4d4")))

                c = QTextCursor(block)
                c.select(QTextCursor.LineUnderCursor)
                c.mergeCharFormat(fmt)

                block.setUserData(_TooltipData(m.message))

                block = block.next()
                i += 1
        finally:
            cursor.endEditBlock()

        self._output.viewport().setMouseTracking(True)
        self._output.mouseMoveEvent = self._output_mouse_move_event  # type: ignore[method-assign]

    def _output_mouse_move_event(self, event):
        pos = event.pos()
        c = self._output.cursorForPosition(pos)
        block = c.block()
        data = block.userData()
        if isinstance(data, _TooltipData):
            self._output.setToolTip(data.text)
        else:
            self._output.setToolTip("")
        QPlainTextEdit.mouseMoveEvent(self._output, event)

    def _highlight_error_lines(self, messages: List[CompileMessage]) -> None:
        lines = sorted({m.line for m in messages if m.line > 0})
        self._editor.set_error_lines(lines)

    def run_program(self) -> None:
        if not self._last_exe_path or not os.path.exists(self._last_exe_path):
            QMessageBox.information(self, "Run", "No compiled executable found. Compile successfully first.")
            return

        code = self._editor.toPlainText()
        stdin_text = None
        if "scanf(" in code:
            text, ok = QInputDialog.getMultiLineText(
                self,
                "Program Input",
                "Enter input for scanf (each value separated by space/newline):",
                "",
            )
            if not ok:
                return
            stdin_text = text
            if stdin_text and not stdin_text.endswith("\n"):
                stdin_text += "\n"

        try:
            proc = run_executable(self._last_exe_path, stdin_text=stdin_text, timeout_s=10.0)
        except TimeoutError:
            self._append_output("\n--- Program Error ---\n")
            self._append_output("Program timed out (it may still be waiting for more input).")
            return
        except Exception as e:
            self._append_output("\n--- Program Error ---\n")
            self._append_output(str(e))
            return

        self._append_output("\nOutput:\n")
        out = proc.stdout.rstrip("\n") if proc.stdout else ""
        if out:
            # Highlight main numeric output in green (simple)
            self._append_output(out)
        if proc.stderr:
            self._append_output("\n--- Program Errors ---\n")
            self._append_output(proc.stderr.rstrip("\n"))

        if not proc.stdout and not proc.stderr:
            self._append_output("(No output)")


class _TooltipData(QTextBlockUserData):
    def __init__(self, text: str):
        super().__init__()
        self.text = text
