"""Cursor-like coding workspace for the Code Assistant agent."""
from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T
from jarvis_ui.components import _AutoText, _LineIcon, _spaced_font
from jarvis_ui.markdown_utils import markdown_to_html


_CODE_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\s*([\s\S]*?)```")


def _extract_code_block(text: str) -> tuple[str, str] | tuple[None, None]:
    matches = list(_CODE_BLOCK_RE.finditer(text or ""))
    if not matches:
        return None, None
    m = matches[-1]
    lang = (m.group(1) or "").strip().lower() or "txt"
    return lang, (m.group(2) or "").strip()


class CodeAssistantView(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream_bubble: _AutoText | None = None
        self._building = False
        self._last_code = ""
        self._last_lang = "txt"

        self.setStyleSheet(f"background: {T.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QFrame()
        body.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self._build_chat_column(), stretch=6)
        bl.addWidget(self._build_code_column(), stretch=5)
        root.addWidget(body, stretch=1)

        self._show_suggestions()

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"background: {T.BG}; border-bottom: 1px solid {T.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        badge = QFrame()
        badge.setFixedSize(34, 34)
        badge.setStyleSheet(
            f"background: rgba(0,209,255,0.10); border: 1px solid rgba(0,209,255,0.30); border-radius: 8px;"
        )
        b = QHBoxLayout(badge)
        b.setContentsMargins(0, 0, 0, 0)
        b.addWidget(_LineIcon("code", T.CYAN, 20), alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)

        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel("CODE ASSISTANT")
        name.setFont(_spaced_font(T.FONT_DISPLAY, 11, 2.2, bold=True))
        name.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        sub = QLabel("Cursor-style coding copilot")
        sub.setFont(QFont(T.FONT_UI, 8))
        sub.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        col.addWidget(name)
        col.addWidget(sub)
        lay.addLayout(col)
        lay.addStretch()

        self._status = QLabel("● READY")
        self._status.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        self._status.setStyleSheet(f"color: {T.GREEN}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(self._status)
        return bar

    def _build_chat_column(self) -> QWidget:
        col = QFrame()
        col.setStyleSheet(f"background: {T.BG_PANEL}; border-right: 1px solid {T.BORDER};")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            f"QScrollBar:vertical {{ background: transparent; width: 7px; }}"
            f"QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 3px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self._feed = QVBoxLayout(host)
        self._feed.setContentsMargins(16, 16, 12, 12)
        self._feed.setSpacing(10)
        self._feed.addStretch()
        self._scroll.setWidget(host)
        lay.addWidget(self._scroll, stretch=1)
        lay.addWidget(self._build_composer())
        return col

    def _build_composer(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background: {T.BG_PANEL}; border-top: 1px solid {T.BORDER};")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(6)

        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER_HI}; border-radius: 12px; }}"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 10, 10, 8)
        bl.setSpacing(6)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Describe feature/bug, paste code, ask to build an app...")
        self._input.setFont(QFont(T.FONT_UI, 11))
        self._input.setFixedHeight(84)
        self._input.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {T.WHITE}; border: none; padding: 0; }}"
        )
        self._input.installEventFilter(self)
        bl.addWidget(self._input)

        row = QHBoxLayout()
        row.setSpacing(8)
        tag = QLabel("⌁  Senior Software Engineer")
        tag.setFont(QFont(T.FONT_UI, 8))
        tag.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        row.addWidget(tag)
        row.addStretch()
        self._send_btn = QPushButton("Solve  ↑")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(0,209,255,0.12); color: {T.CYAN}; border: 1px solid {T.CYAN_DIM}; border-radius: 8px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ background: rgba(0,209,255,0.20); }}"
            f"QPushButton:disabled {{ color: {T.TEXT_DIM}; border-color: {T.BORDER}; }}"
        )
        self._send_btn.clicked.connect(self._emit_submit)
        row.addWidget(self._send_btn)
        bl.addLayout(row)
        outer.addWidget(box)
        return wrap

    def _build_code_column(self) -> QWidget:
        col = QFrame()
        col.setStyleSheet(f"background: {T.BG};")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        top = QFrame()
        top.setStyleSheet(
            f"QFrame {{ background: {T.BG_PANEL}; border: 1px solid {T.BORDER}; border-radius: 9px; }}"
        )
        tl = QHBoxLayout(top)
        tl.setContentsMargins(10, 5, 10, 5)
        lbl = QLabel("WORKSPACE")
        lbl.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {T.CYAN}; background: transparent; letter-spacing: 1px;")
        tl.addWidget(lbl)
        tl.addStretch()
        self._lang_lbl = QLabel("LANG: --")
        self._lang_lbl.setFont(QFont(T.FONT_UI, 8))
        self._lang_lbl.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        tl.addWidget(self._lang_lbl)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self._copy_code)
        self._save_btn = QPushButton("Save As")
        self._save_btn.clicked.connect(self._save_code)
        for b in (self._copy_btn, self._save_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(QFont(T.FONT_UI, 8))
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {T.TEXT_MED}; border: 1px solid {T.BORDER}; border-radius: 6px; padding: 3px 10px; }}"
                f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}"
            )
            tl.addWidget(b)
        lay.addWidget(top)

        self._code = QTextEdit()
        self._code.setReadOnly(True)
        self._code.setFont(QFont(T.FONT_DISPLAY, 10))
        self._code.setPlaceholderText("Generated code appears here...")
        self._code.setStyleSheet(
            f"QTextEdit {{ background: {T.BG_CARD}; color: {T.TEXT}; border: 1px solid {T.BORDER_HI}; border-radius: 10px; padding: 12px; }}"
        )
        lay.addWidget(self._code, stretch=1)
        return col

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self._input and ev.type() == QEvent.Type.KeyPress:
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                ev.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                self._emit_submit()
                return True
        return super().eventFilter(obj, ev)

    def _emit_submit(self):
        text = self._input.toPlainText().strip()
        if not text or self._building:
            return
        self._input.clear()
        self.submitted.emit(text)

    def _insert(self, widget: QWidget):
        self._feed.insertWidget(self._feed.count() - 1, widget)
        QTimer.singleShot(0, self._scroll_bottom)

    def _scroll_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _bubble(self, who: str, accent: str) -> _AutoText:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; border-left: 2px solid {accent}; border-radius: 10px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(4)
        tag = QLabel(who)
        tag.setFont(QFont(T.FONT_UI, 7, QFont.Weight.Bold))
        tag.setStyleSheet(f"color: {accent}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(tag)
        body = _AutoText()
        body.setFont(QFont(T.FONT_UI, 10))
        lay.addWidget(body)
        self._insert(frame)
        return body

    def _show_suggestions(self):
        suggestions = [
            "Build a full-stack task app architecture with file structure",
            "Fix this React bug and return updated component code",
            "Create Python FastAPI starter with auth and tests",
            "Generate Next.js landing page app with animations",
        ]
        box = QFrame()
        box.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(2, 6, 2, 2)
        bl.setSpacing(8)
        title = QLabel("Quick starts")
        title.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        bl.addWidget(title)
        for s in suggestions:
            chip = QPushButton(s)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFont(QFont(T.FONT_UI, 9))
            chip.setStyleSheet(
                f"QPushButton {{ background: {T.BG_CARD}; color: {T.TEXT_MED}; border: 1px solid {T.BORDER}; border-radius: 9px; padding: 9px 12px; text-align: left; }}"
                f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}"
            )
            chip.clicked.connect(lambda _, t=s: (self._input.setPlainText(t), self._emit_submit()))
            bl.addWidget(chip)
        self._suggest_box = box
        self._insert(box)

    def add_user(self, text: str):
        if getattr(self, "_suggest_box", None) is not None:
            self._suggest_box.deleteLater()
            self._suggest_box = None
        body = self._bubble("YOU", T.GREEN)
        body.setHtml(markdown_to_html(text))

    def begin_run(self):
        self._building = True
        self._send_btn.setEnabled(False)
        self._status.setText("● THINKING")
        self._status.setStyleSheet(f"color: {T.CYAN}; background: transparent; letter-spacing: 1px;")
        self._stream_bubble = self._bubble("CODE ASSISTANT", T.CYAN)
        self._stream_bubble.setHtml(markdown_to_html("_Working on your request…_"))

    def on_delta(self, full_text: str):
        if self._stream_bubble is None:
            self._stream_bubble = self._bubble("CODE ASSISTANT", T.CYAN)
        self._stream_bubble.setHtml(markdown_to_html(full_text))
        lang, code = _extract_code_block(full_text)
        if code:
            self._last_code = code
            self._last_lang = lang or "txt"
            self._code.setPlainText(code)
            self._lang_lbl.setText(f"LANG: {self._last_lang}")
        QTimer.singleShot(0, self._scroll_bottom)

    def finish(self, full_text: str):
        self.on_delta(full_text)
        self._stream_bubble = None
        self._building = False
        self._send_btn.setEnabled(True)
        self._status.setText("● READY")
        self._status.setStyleSheet(f"color: {T.GREEN}; background: transparent; letter-spacing: 1px;")

    def set_error(self, message: str):
        if self._stream_bubble is None:
            self._stream_bubble = self._bubble("CODE ASSISTANT", T.RED)
        self._stream_bubble.setHtml(markdown_to_html(f"**Request failed.** {message}"))
        self._stream_bubble = None
        self._building = False
        self._send_btn.setEnabled(True)
        self._status.setText("● ERROR")
        self._status.setStyleSheet(f"color: {T.RED}; background: transparent; letter-spacing: 1px;")

    def _copy_code(self):
        if not self._last_code:
            return
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self._last_code)

    def _save_code(self):
        if not self._last_code:
            return
        ext_map = {
            "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
            "typescript": ".ts", "ts": ".ts", "tsx": ".tsx", "html": ".html",
            "css": ".css", "json": ".json", "bash": ".sh", "sh": ".sh",
        }
        ext = ext_map.get(self._last_lang, ".txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save code", f"output{ext}", "All Files (*)")
        if path:
            Path(path).write_text(self._last_code, encoding="utf-8")
