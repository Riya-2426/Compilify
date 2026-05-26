from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence, QTextCursor
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
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from compiler.error_filter import filter_cascade_syntax_errors, find_root_error_lines
from compiler.gcc_runner import compile_with_gcc, run_executable
from compiler.lexer import lexical_analysis, tokens_as_rows
from compiler.optimizer import optimize_code
from compiler.semantic import semantic_check
from compiler.symbol_table import symbol_rows_for_gui
from gui.editor import CodeEditor
from gui.themes import load_stylesheet
from gui.widgets.problems_panel import ProblemsPanel
from utils.file_manager import open_c_file, save_as, save_file


@dataclass(frozen=True)
class CompileMessage:
    line: int
    kind: str
    message: str
    suggestion: str = ""


ERROR_COLORS_LIGHT = {
    "Lexical": QColor("#B45309"),
    "Semantic": QColor("#C2410C"),
    "Syntax": QColor("#DC2626"),
    "Info": QColor("#2563EB"),
}

ERROR_COLORS_DARK = {
    "Lexical": QColor("#FBBF24"),
    "Semantic": QColor("#FB923C"),
    "Syntax": QColor("#F87171"),
    "Info": QColor("#58A6FF"),
}

SAMPLE_CODE = """#include <stdio.h>

int main() {
    int a = 10;
    int b = 20;
    int c;

    c = a + b;

    printf("Value = %d\\n", c);
    return 0;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Compiler IDE")
        self.resize(1360, 860)

        self._current_path: Optional[str] = None
        self._last_build_dir: Optional[str] = None
        self._last_exe_path: Optional[str] = None
        self._compile_messages: List[CompileMessage] = []
        self._dark_mode = False
        self._block_dark_sync = False
        self._dirty = False
        self._block_dirty = False

        self._editor = CodeEditor(self)
        self._output = QPlainTextEdit(self)
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Build log and program output…")
        self._opt_log = QPlainTextEdit(self)
        self._opt_log.setReadOnly(True)
        self._opt_log.setPlaceholderText("Optimization notes appear here…")

        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)
        self._output.setFont(mono)
        self._opt_log.setFont(mono)

        self._problems = ProblemsPanel(self, on_jump=self._editor.scroll_to_line)

        self._tokens = QTableWidget(self)
        self._tokens.setColumnCount(4)
        self._tokens.setHorizontalHeaderLabels(["Type", "Lexeme", "Line", "Col"])
        self._tokens.verticalHeader().setVisible(False)
        self._tokens.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tokens.setSelectionBehavior(QTableWidget.SelectRows)
        self._tokens.setAlternatingRowColors(True)
        self._tokens.setShowGrid(False)
        self._tokens.cellDoubleClicked.connect(self._jump_to_token)

        self._symbol_table = QTableWidget(self)
        self._symbol_table.setColumnCount(5)
        self._symbol_table.setHorizontalHeaderLabels(["Name", "Type", "Value", "Scope", "Uses"])
        self._symbol_table.verticalHeader().setVisible(False)
        self._symbol_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._symbol_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._symbol_table.setAlternatingRowColors(True)
        self._symbol_table.setShowGrid(False)

        self._build_layout()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()
        self._setup_shortcuts()

        self._editor.cursorPositionChanged.connect(self._update_status_cursor)
        self._editor.textChanged.connect(self._on_text_changed)
        self._update_status_cursor()
        self._on_text_changed()
        self._update_window_title()
        self._set_compile_status("Ready")
        self._apply_theme()

    def _panel(self) -> QFrame:
        f = QFrame(self)
        f.setObjectName("panel")
        f.setFrameShape(QFrame.StyledPanel)
        return f

    def _build_welcome_page(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)

        card = QFrame(page)
        card.setObjectName("welcomeCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(40, 36, 40, 36)
        card_lay.setSpacing(16)

        title = QLabel("Advanced C Compiler IDE", card)
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(title)

        hint = QLabel(
            "Write or open a C program, then Compile, Optimize, or Run.\n"
            "Shortcuts: F7 Compile · F5 Run · Ctrl+Shift+O Optimize · Ctrl+S Save",
            card,
        )
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        card_lay.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_open = QPushButton("Open File…", card)
        btn_open.setObjectName("primaryBtn")
        btn_open.clicked.connect(self.open_file)
        btn_sample = QPushButton("Load Sample", card)
        btn_sample.clicked.connect(self._load_sample)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_open)
        btn_row.addWidget(btn_sample)
        btn_row.addStretch(1)
        card_lay.addLayout(btn_row)

        lay.addWidget(card)
        return page

    def _build_layout(self) -> None:
        # Top header bar
        header = QFrame(self)
        header.setObjectName("headerBar")
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(16, 8, 16, 8)
        self._lbl_header_title = QLabel("Advanced C Compiler IDE", header)
        self._lbl_header_title.setObjectName("headerTitle")
        self._lbl_file = QLabel("Untitled", header)
        self._lbl_file.setObjectName("headerFile")
        self._lbl_dirty = QLabel("", header)
        self._lbl_dirty.setObjectName("headerDirty")
        header_lay.addWidget(self._lbl_header_title)
        header_lay.addSpacing(16)
        header_lay.addWidget(self._lbl_file, 1)
        header_lay.addWidget(self._lbl_dirty)

        # Editor area with welcome overlay
        self._editor_stack = QStackedWidget(self)
        self._editor_stack.addWidget(self._build_welcome_page())
        editor_wrap = self._panel()
        editor_lay = QVBoxLayout(editor_wrap)
        editor_lay.setContentsMargins(4, 4, 4, 4)
        editor_lay.addWidget(self._editor)
        self._editor_stack.addWidget(editor_wrap)
        self._editor_stack.setCurrentIndex(0)

        left_wrap = self._panel()
        left_lay = QVBoxLayout(left_wrap)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(8)
        left_lay.addWidget(self._editor_stack, 1)

        # Right: tabbed panels
        self._right_tabs = QTabWidget(self)
        self._right_tabs.setDocumentMode(True)
        self._right_tabs.addTab(self._problems, "Problems")
        self._right_tabs.addTab(self._output, "Output")
        self._right_tabs.addTab(self._tokens, "Tokens")
        self._right_tabs.addTab(self._symbol_table, "Symbols")
        self._right_tabs.addTab(self._opt_log, "Optimization")

        right_wrap = self._panel()
        right_lay = QVBoxLayout(right_wrap)
        right_lay.setContentsMargins(8, 8, 8, 8)
        right_lay.addWidget(self._right_tabs)

        main_split = QSplitter(Qt.Horizontal, self)
        main_split.addWidget(left_wrap)
        main_split.addWidget(right_wrap)
        main_split.setStretchFactor(0, 58)
        main_split.setStretchFactor(1, 42)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(header)
        layout.addWidget(main_split, 1)
        self.setCentralWidget(container)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        self._act_open = QAction("Open…", self)
        self._act_open.setShortcut(QKeySequence.Open)
        self._act_open.triggered.connect(self.open_file)
        file_menu.addAction(self._act_open)
        self._act_save = QAction("Save", self)
        self._act_save.setShortcut(QKeySequence.Save)
        self._act_save.triggered.connect(self.save_file)
        file_menu.addAction(self._act_save)
        self._act_save_as = QAction("Save As…", self)
        self._act_save_as.setShortcut(QKeySequence.SaveAs)
        self._act_save_as.triggered.connect(self.save_file_as)
        file_menu.addAction(self._act_save_as)
        file_menu.addSeparator()
        act_sample = QAction("Load Sample Program", self)
        act_sample.triggered.connect(self._load_sample)
        file_menu.addAction(act_sample)
        file_menu.addSeparator()
        self._act_exit = QAction("Exit", self)
        self._act_exit.setShortcut(QKeySequence.Quit)
        self._act_exit.triggered.connect(self.close)
        file_menu.addAction(self._act_exit)

        view_menu = menubar.addMenu("&View")
        self._act_dark = QAction("Dark Mode", self, checkable=True)
        self._act_dark.triggered.connect(self._toggle_dark_from_menu)
        view_menu.addAction(self._act_dark)

        run_menu = menubar.addMenu("&Build")
        act_compile = QAction("Compile", self)
        act_compile.setShortcut("F7")
        act_compile.triggered.connect(self.compile_code)
        run_menu.addAction(act_compile)
        act_opt = QAction("Optimize", self)
        act_opt.setShortcut("Ctrl+Shift+O")
        act_opt.triggered.connect(self.optimize_current_code)
        run_menu.addAction(act_opt)
        act_run = QAction("Run Program", self)
        act_run.setShortcut("F5")
        act_run.triggered.connect(self.run_program)
        run_menu.addAction(act_run)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        st = self.style()

        a_compile = QAction(st.standardIcon(QStyle.SP_DialogApplyButton), "Compile", self)
        a_compile.setToolTip("Compile (F7)")
        a_compile.triggered.connect(self.compile_code)
        tb.addAction(a_compile)

        a_run = QAction(st.standardIcon(QStyle.SP_MediaPlay), "Run", self)
        a_run.setToolTip("Run program (F5)")
        a_run.triggered.connect(self.run_program)
        tb.addAction(a_run)

        a_opt = QAction(st.standardIcon(QStyle.SP_BrowserReload), "Optimize", self)
        a_opt.setToolTip("Optimize code (Ctrl+Shift+O)")
        a_opt.triggered.connect(self.optimize_current_code)
        tb.addAction(a_opt)

        tb.addSeparator()

        a_clear = QAction(st.standardIcon(QStyle.SP_TrashIcon), "Clear Panels", self)
        a_clear.triggered.connect(self.clear_output)
        tb.addAction(a_clear)

        tb.addSeparator()
        self._chk_dark = QCheckBox(" Dark theme", self)
        self._chk_dark.stateChanged.connect(self._on_dark_checkbox)
        tb.addWidget(self._chk_dark)

    def _build_status_bar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self._lbl_compile_status = QLabel("Ready")
        self._lbl_gcc = QLabel(self._gcc_status_text())
        self._lbl_pos = QLabel("Ln 1, Col 1")
        sb.addWidget(self._lbl_compile_status, 1)
        sb.addPermanentWidget(self._lbl_gcc)
        sb.addPermanentWidget(self._lbl_pos)

    def _setup_shortcuts(self) -> None:
        pass  # shortcuts attached to QAction in menu

    def _gcc_status_text(self) -> str:
        gcc = shutil.which("gcc")
        return "GCC: available" if gcc else "GCC: not found"

    def _error_colors(self) -> dict:
        return ERROR_COLORS_DARK if self._dark_mode else ERROR_COLORS_LIGHT

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        app.setStyleSheet(load_stylesheet(self._dark_mode))
        self._editor.set_theme(self._dark_mode)
        if self._compile_messages:
            self._problems.set_messages(self._compile_messages, self._error_colors(), self._dark_mode)
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

    def _set_compile_status(self, text: str) -> None:
        self._lbl_compile_status.setText(text)

    def _update_window_title(self) -> None:
        name = os.path.basename(self._current_path) if self._current_path else "Untitled"
        dirty = " ●" if self._dirty else ""
        self._lbl_file.setText(name + dirty)
        self._lbl_dirty.setText("modified" if self._dirty else "")
        self.setWindowTitle(f"{name}{dirty} — Advanced Compiler IDE")

    def _mark_dirty(self, dirty: bool = True) -> None:
        if self._block_dirty:
            return
        self._dirty = dirty
        self._update_window_title()

    def _update_status_cursor(self) -> None:
        c = self._editor.textCursor()
        ln = c.blockNumber() + 1
        col = c.positionInBlock() + 1
        self._lbl_pos.setText(f"Ln {ln}, Col {col}")

    def _on_text_changed(self) -> None:
        code = self._editor.toPlainText()
        has_code = bool(code.strip())
        self._editor_stack.setCurrentIndex(1 if has_code else 0)
        self._mark_dirty(True)
        _, tokens = lexical_analysis(code)
        self._populate_tokens(tokens_as_rows(tokens))
        self._populate_symbol_table(code)

    def _load_sample(self) -> None:
        self._editor_stack.setCurrentIndex(1)
        self._block_dirty = True
        try:
            self._editor.setPlainText(SAMPLE_CODE)
            self._current_path = None
        finally:
            self._block_dirty = False
        self._mark_dirty(True)
        self.statusBar().showMessage("Sample program loaded", 2500)

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
            self._editor.scroll_to_line(int(item.text()))
        except ValueError:
            pass

    def clear_output(self) -> None:
        self._output.clear()
        self._opt_log.clear()
        self._problems.clear_all()
        self._compile_messages = []
        self._editor.clear_error_lines()
        self._set_compile_status("Ready")

    def _append_output(self, text: str) -> None:
        if not text.endswith("\n"):
            text += "\n"
        self._output.moveCursor(QTextCursor.End)
        self._output.insertPlainText(text)
        self._output.moveCursor(QTextCursor.End)

    def _append_opt_log(self, text: str) -> None:
        if not text.endswith("\n"):
            text += "\n"
        self._opt_log.moveCursor(QTextCursor.End)
        self._opt_log.insertPlainText(text)
        self._opt_log.moveCursor(QTextCursor.End)

    def _show_problems(self, messages: List[CompileMessage]) -> None:
        self._compile_messages = messages
        self._problems.set_messages(messages, self._error_colors(), self._dark_mode)
        self._right_tabs.setCurrentWidget(self._problems)
        self._output.clear()
        if not messages:
            self._append_output("Build finished: no issues found.")
            self._right_tabs.setCurrentWidget(self._output)
            return
        self._append_output(f"Build finished: {len(messages)} issue(s). See Problems tab (double-click a row to jump).")
        for m in messages:
            line_part = f"Line {m.line}: " if m.line > 0 else ""
            self._append_output(f"{line_part}[{m.kind}] {m.message}")

    def open_file(self) -> None:
        res = open_c_file(self)
        if not res.path:
            return
        self._editor_stack.setCurrentIndex(1)
        self._current_path = res.path
        self._block_dirty = True
        try:
            self._editor.setPlainText(res.content or "")
        finally:
            self._block_dirty = False
        self._mark_dirty(False)
        self.statusBar().showMessage(f"Opened {os.path.basename(res.path)}", 3000)

    def save_file(self) -> None:
        code = self._editor.toPlainText()
        if not code.strip():
            QMessageBox.information(self, "Empty", "Editor is empty. Nothing to save.")
            return
        if not self._current_path:
            self.save_file_as()
            return
        if save_file(self, self._current_path, code):
            self._mark_dirty(False)
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
            self._mark_dirty(False)
            self.statusBar().showMessage("Saved As", 2000)
        else:
            QMessageBox.warning(self, "Save failed", "Could not save file.")

    def compile_code(self) -> None:
        code = self._editor.toPlainText()
        self.clear_output()

        if not code.strip():
            QMessageBox.information(self, "Empty input", "Please type or open a C program first.")
            return

        self._set_compile_status("Compiling…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._last_build_dir = tempfile.mkdtemp(prefix="ccompiler_gui_")
            src_path = os.path.join(self._last_build_dir, "temp.c")
            exe_path = os.path.join(self._last_build_dir, "temp.exe")
            with open(src_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(code)

            lex_errs, tokens = lexical_analysis(code)
            sem_errs = semantic_check(code)
            syn_errs = compile_with_gcc(src_path, exe_path)

            root_lines = find_root_error_lines(lex_errs, syn_errs)
            syn_errs, cascade_note = filter_cascade_syntax_errors(syn_errs, root_lines)

            messages: List[CompileMessage] = []
            if cascade_note:
                messages.append(CompileMessage(0, "Info", cascade_note, ""))
            for ln, msg, sug in lex_errs:
                messages.append(CompileMessage(ln, "Lexical", msg, sug))
            for ln, msg, sug in syn_errs:
                messages.append(CompileMessage(ln, "Syntax", msg, sug))
            for ln, msg, sug in sem_errs:
                messages.append(CompileMessage(ln, "Semantic", msg, sug))

            _kind_order = {"Info": 0, "Lexical": 1, "Syntax": 2, "Semantic": 3}
            messages.sort(key=lambda m: (m.line if m.line > 0 else -1, _kind_order.get(m.kind, 9)))

            self._populate_tokens(tokens_as_rows(tokens))
            self._populate_symbol_table(code)

            if not messages:
                self._show_problems([])
                self._last_exe_path = exe_path
                self._editor.clear_error_lines()
                self._set_compile_status("Build succeeded")
                self.statusBar().showMessage("Compile succeeded", 3000)
                return

            self._show_problems(messages)
            self._highlight_error_lines(messages)
            first = next((m for m in messages if m.line > 0), messages[0])
            if first.line > 0:
                self._editor.scroll_to_line(first.line)
            self._set_compile_status(f"{len(messages)} issue(s)")
            self.statusBar().showMessage(f"Compile found {len(messages)} issue(s)", 4000)
        finally:
            QApplication.restoreOverrideCursor()

    def optimize_current_code(self) -> None:
        code = self._editor.toPlainText()
        self._output.clear()
        self._opt_log.clear()
        self._problems.clear_all()

        if not code.strip():
            QMessageBox.information(self, "Empty input", "Please type or open a C program first.")
            return

        self._set_compile_status("Optimizing…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            lex_errs, tokens = lexical_analysis(code)
            if lex_errs:
                self._append_output("Warning: lexical issue(s) — best-effort optimization.\n")
                for ln, msg, sug in lex_errs:
                    self._append_output(f"Line {ln} → {msg}")
                    if sug:
                        self._append_opt_log(f"Line {ln}: {sug}")

            optimized, notes = optimize_code(code)
            if optimized.strip() == code.strip():
                self._append_output("Code is already optimized (no safe changes found).")
                self._right_tabs.setCurrentWidget(self._output)
                self._set_compile_status("No changes")
                return

            cur = self._editor.textCursor()
            cur.beginEditBlock()
            try:
                self._editor.selectAll()
                self._editor.insertPlainText(optimized)
            finally:
                cur.endEditBlock()

            _, opt_tokens = lexical_analysis(optimized)
            self._populate_tokens(tokens_as_rows(opt_tokens))
            self._populate_symbol_table(optimized)

            self._append_output("Optimization applied successfully.")
            self._opt_log.clear()
            for n in notes:
                if n.line > 0:
                    self._append_opt_log(f"Line {n.line}: {n.message}")
                else:
                    self._append_opt_log(n.message)

            self._right_tabs.setCurrentWidget(self._opt_log)
            self._mark_dirty(True)
            self._set_compile_status("Optimized")
            self.statusBar().showMessage("Code optimized", 2500)
        finally:
            QApplication.restoreOverrideCursor()

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
                "Enter input for scanf (values separated by space or newline):",
                "",
            )
            if not ok:
                return
            stdin_text = text
            if stdin_text and not stdin_text.endswith("\n"):
                stdin_text += "\n"

        self._set_compile_status("Running…")
        self._right_tabs.setCurrentWidget(self._output)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            proc = run_executable(self._last_exe_path, stdin_text=stdin_text, timeout_s=10.0)
        except TimeoutError:
            self._append_output("\n--- Runtime ---\nProgram timed out.\n")
            self._set_compile_status("Timed out")
            return
        except Exception as e:
            self._append_output(f"\n--- Runtime ---\n{e}\n")
            self._set_compile_status("Run failed")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._append_output("\n--- Program output ---\n")
        if proc.stdout:
            self._append_output(proc.stdout.rstrip("\n"))
        if proc.stderr:
            self._append_output("\n--- stderr ---\n")
            self._append_output(proc.stderr.rstrip("\n"))
        if not proc.stdout and not proc.stderr:
            self._append_output("(no output)")

        self._set_compile_status("Run finished")
        self.statusBar().showMessage("Program finished", 3000)
