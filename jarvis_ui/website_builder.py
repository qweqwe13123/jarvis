"""Website Builder workspace — prompt-to-live-site, modelled on F.O.R.G.E.

Left: a chat thread + composer. Right: a live HTML preview (QWebEngineView)
that re-renders on the fly as the model streams, with Preview/Code tabs, a
device toggle (desktop / tablet / mobile), reload, download and open-external.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QFileDialog,
)

from jarvis_ui import theme as T
from jarvis_ui.markdown_utils import markdown_to_html
from jarvis_ui.components import _LineIcon, _AutoText, _spaced_font
from core.extract_html import extract_html, strip_code_blocks

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE = True
except Exception:
    QWebEngineView = None
    _WEB_ENGINE = False


_PREVIEW_BASE = QUrl("https://forge.local/")

_DEVICE_WIDTHS = {"desktop": 0, "tablet": 768, "mobile": 390}

_PLACEHOLDER_HTML = """<!doctype html><html><head><meta charset='utf-8'>
<style>
  html,body{height:100%;margin:0}
  body{display:flex;align-items:center;justify-content:center;
       background:#050a14;color:#5a8fa8;
       font-family:'Courier New',monospace;letter-spacing:.18em;text-transform:uppercase}
  .b{text-align:center}.b b{color:#00d1ff;display:block;font-size:14px;margin-bottom:8px;
     text-shadow:0 0 12px rgba(0,209,255,.6)}
  .b span{font-size:11px;opacity:.7}
</style></head><body><div class='b'><b>Live Preview</b>
<span>Describe a site and it renders here</span></div></body></html>"""


class WebsiteBuilderView(QWidget):
    submitted = pyqtSignal(str)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.BG};")
        self._stream_bubble: _AutoText | None = None
        self._last_html: str = ""
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QFrame()
        body.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self._build_chat_column(), stretch=5)
        bl.addWidget(self._build_preview_column(), stretch=6)
        root.addWidget(body, stretch=1)

        self._show_suggestions()
        self._load_builder_defaults()

    # ------------------------------------------------------------------ header
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
            f"background: rgba(0,209,255,0.10); border: 1px solid rgba(0,209,255,0.30);"
            f" border-radius: 8px;"
        )
        bl = QHBoxLayout(badge)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(_LineIcon("globe", T.CYAN, 20), alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)

        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel("WEBSITE BUILDER")
        name.setFont(_spaced_font(T.FONT_DISPLAY, 11, 2.4, bold=True))
        name.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        sub = QLabel("From prompt to live site")
        sub.setFont(QFont(T.FONT_UI, 8))
        sub.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        col.addWidget(name)
        col.addWidget(sub)
        lay.addLayout(col)

        lay.addStretch()
        try:
            from core.gemini_models import primary as _gemini_primary

            _chip_model = _gemini_primary("balanced")
        except Exception:
            _chip_model = "gemini-flash-latest"
        model_chip = QLabel(_chip_model)
        model_chip.setFont(QFont(T.FONT_UI, 9))
        model_chip.setStyleSheet(
            f"color: {T.CYAN}; background: rgba(0,209,255,0.08);"
            f" border: 1px solid rgba(0,209,255,0.22); border-radius: 8px;"
            f" padding: 4px 10px;"
        )
        lay.addWidget(model_chip)

        self._status = QLabel("● READY")
        self._status.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        self._status.setStyleSheet(f"color: {T.GREEN}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(self._status)
        return bar

    def _load_builder_defaults(self):
        pass

    def selected_provider(self) -> str:
        return "gemini"

    def selected_model(self) -> str:
        try:
            from core.gemini_models import primary as _gemini_primary

            return _gemini_primary("balanced")
        except Exception:
            return "gemini-flash-latest"

    # -------------------------------------------------------------- chat column
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
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER_HI};"
            f" border-radius: 12px; }}"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 10, 10, 8)
        bl.setSpacing(6)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Describe the website you want to build…")
        self._input.setFont(QFont(T.FONT_UI, 11))
        self._input.setFixedHeight(64)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {T.WHITE}; border: none; padding: 0; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 5px; }}"
            f"QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 2px; }}"
        )
        self._input.installEventFilter(self)
        bl.addWidget(self._input)

        row = QHBoxLayout()
        row.setSpacing(8)
        tag = QLabel("◈  Forge Builder")
        tag.setFont(QFont(T.FONT_UI, 8))
        tag.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        row.addWidget(tag)
        row.addStretch()

        self._send_btn = QPushButton("Build  ↑")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(0,209,255,0.12); color: {T.CYAN};"
            f" border: 1px solid {T.CYAN_DIM}; border-radius: 8px; padding: 5px 14px; }}"
            f"QPushButton:hover {{ background: rgba(0,209,255,0.20); }}"
            f"QPushButton:disabled {{ color: {T.TEXT_DIM}; border-color: {T.BORDER}; }}"
        )
        self._send_btn.clicked.connect(self._emit_submit)
        row.addWidget(self._send_btn)
        bl.addLayout(row)
        outer.addWidget(box)

        hint = QLabel("Enter to build · Shift+Enter for a new line")
        hint.setFont(QFont(T.FONT_UI, 7))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        outer.addWidget(hint)
        return wrap

    # ----------------------------------------------------------- preview column
    def _build_preview_column(self) -> QWidget:
        col = QFrame()
        col.setStyleSheet(f"background: {T.BG};")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        lay.addWidget(self._build_preview_toolbar())

        # Centered device frame so tablet/mobile widths look right.
        self._device_host = QFrame()
        self._device_host.setStyleSheet("background: transparent;")
        dh = QHBoxLayout(self._device_host)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.addStretch()

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(
            f"QStackedWidget {{ background: white; border: 1px solid {T.BORDER_HI};"
            f" border-radius: 10px; }}"
        )
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        if _WEB_ENGINE:
            self._web = QWebEngineView()
            self._web.setStyleSheet("background: white; border-radius: 10px;")
            self._stack.addWidget(self._web)
        else:
            self._web = None
            msg = QLabel("QtWebEngine is not installed — preview shows code only.\n"
                         "Install with:  pip install PyQt6-WebEngine")
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet("background: #050a14; color: #5a8fa8; padding: 24px;")
            self._stack.addWidget(msg)

        self._code = QTextEdit()
        self._code.setReadOnly(True)
        self._code.setFont(QFont(T.FONT_DISPLAY, 9))
        self._code.setStyleSheet(
            f"QTextEdit {{ background: {T.BG}; color: {T.TEXT}; border: none;"
            f" border-radius: 10px; padding: 12px; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 7px; }}"
            f"QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 3px; }}"
        )
        self._stack.addWidget(self._code)

        dh.addWidget(self._stack, stretch=1)
        dh.addStretch()
        lay.addWidget(self._device_host, stretch=1)

        self._device = "desktop"
        self._tab = "preview"
        self._apply_device()
        self._set_preview_html(_PLACEHOLDER_HTML)
        return col

    def _build_preview_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(52)
        bar.setStyleSheet(
            f"QFrame {{ background: {T.BG_PANEL}; border: 1px solid {T.BORDER};"
            f" border-radius: 10px; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        self._tab_btns: dict[str, QPushButton] = {}
        for key, label in [("preview", "Preview"), ("code", "Code")]:
            b = self._toolbar_btn(label, checkable=True)
            b.clicked.connect(lambda _, k=key: self._switch_tab(k))
            self._tab_btns[key] = b
            lay.addWidget(b)

        lay.addStretch()

        self._device_btns: dict[str, QPushButton] = {}
        for key, label in [("desktop", "Desktop"), ("tablet", "Tablet"), ("mobile", "Mobile")]:
            b = self._toolbar_btn(label, checkable=True)
            b.clicked.connect(lambda _, k=key: self._set_device(k))
            self._device_btns[key] = b
            lay.addWidget(b)

        reload_btn = self._toolbar_btn("Reload")
        reload_btn.clicked.connect(self._reload)
        lay.addWidget(reload_btn)

        dl = self._toolbar_btn("Download")
        dl.clicked.connect(self._download)
        lay.addWidget(dl)

        ext = self._toolbar_btn("Open")
        ext.clicked.connect(self._open_external)
        lay.addWidget(ext)
        return bar

    def _toolbar_btn(self, label: str, checkable: bool = False, fixed: int = 0) -> QPushButton:
        b = QPushButton(label)
        b.setCheckable(checkable)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold))
        if fixed:
            b.setFixedSize(fixed, 28)
        else:
            b.setFixedHeight(34)
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {T.TEXT_DIM};"
            f" border: 1px solid transparent; border-radius: 7px; padding: 0 12px; }}"
            f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.BORDER_HI}; }}"
            f"QPushButton:checked {{ background: rgba(0,209,255,0.12); color: {T.CYAN};"
            f" border: 1px solid {T.CYAN_DIM}; }}"
        )
        return b

    # --------------------------------------------------------------- behaviour
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

    def _switch_tab(self, key: str):
        self._tab = key
        for k, b in self._tab_btns.items():
            b.setChecked(k == key)
        self._stack.setCurrentIndex(0 if key == "preview" else 1)

    def _set_device(self, key: str):
        self._device = key
        self._apply_device()

    def _apply_device(self):
        for k, b in self._device_btns.items():
            b.setChecked(k == self._device)
        width = _DEVICE_WIDTHS.get(self._device, 0)
        if width:
            self._stack.setMaximumWidth(width)
        else:
            self._stack.setMaximumWidth(16777215)

    def _set_preview_html(self, html: str):
        if _WEB_ENGINE and self._web is not None:
            self._web.setHtml(html, _PREVIEW_BASE)
        self._code.setPlainText(html)

    def _reload(self):
        if self._last_html:
            self._set_preview_html(self._last_html)

    def _download(self):
        if not self._last_html:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save website", "site.html", "HTML (*.html)")
        if path:
            Path(path).write_text(self._last_html, encoding="utf-8")

    def _open_external(self):
        if not self._last_html:
            return
        tmp = Path(tempfile.gettempdir()) / "forge_preview.html"
        tmp.write_text(self._last_html, encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(tmp)))

    # ----- feed helpers ----------------------------------------------------
    def _insert(self, widget: QWidget):
        self._feed.insertWidget(self._feed.count() - 1, widget)
        QTimer.singleShot(0, self._scroll_bottom)

    def _scroll_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _bubble(self, who: str, accent: str) -> _AutoText:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER};"
            f" border-left: 2px solid {accent}; border-radius: 10px; }}"
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

    def _clear_suggestions(self):
        if getattr(self, "_suggest_box", None) is not None:
            self._suggest_box.setParent(None)
            self._suggest_box.deleteLater()
            self._suggest_box = None

    def _show_suggestions(self):
        from core.agents import get_agent
        agent = get_agent("website")
        box = QFrame()
        box.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(2, 6, 2, 2)
        bl.setSpacing(8)
        title = QLabel("Try one of these")
        title.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        bl.addWidget(title)
        for s in agent.suggestions:
            chip = QPushButton(s)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFont(QFont(T.FONT_UI, 9))
            chip.setStyleSheet(
                f"QPushButton {{ background: {T.BG_CARD}; color: {T.TEXT_MED};"
                f" border: 1px solid {T.BORDER}; border-radius: 9px; padding: 9px 12px;"
                f" text-align: left; }}"
                f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}"
            )
            chip.clicked.connect(lambda _, t=s: (self._input.setPlainText(t), self._emit_submit()))
            bl.addWidget(chip)
        self._suggest_box = box
        self._insert(box)

    # ----- public API (called on the UI thread) ----------------------------
    def add_user(self, text: str):
        self._clear_suggestions()
        body = self._bubble("YOU", T.GREEN)
        body.setHtml(markdown_to_html(text))

    def begin_build(self):
        self._building = True
        self._send_btn.setEnabled(False)
        self._status.setText("● BUILDING")
        self._status.setStyleSheet(f"color: {T.CYAN}; background: transparent; letter-spacing: 1px;")
        self._stream_bubble = self._bubble("FORGE BUILDER", T.CYAN)
        self._stream_bubble.setHtml(markdown_to_html("_Designing your site…_"))

    def on_delta(self, full_text: str):
        if self._stream_bubble is None:
            self._stream_bubble = self._bubble("FORGE BUILDER", T.CYAN)
        prose = strip_code_blocks(full_text)
        self._stream_bubble.setHtml(markdown_to_html(prose or "_Designing your site…_"))
        html = extract_html(full_text)
        if html and html != self._last_html:
            self._last_html = html
            self._set_preview_html(html)
        QTimer.singleShot(0, self._scroll_bottom)

    def finish(self, full_text: str):
        self.on_delta(full_text)
        prose = strip_code_blocks(full_text)
        if self._stream_bubble is not None:
            self._stream_bubble.setHtml(markdown_to_html(prose or "Done — your site is on the right."))
        self._stream_bubble = None
        self._building = False
        self._send_btn.setEnabled(True)
        self._status.setText("● READY")
        self._status.setStyleSheet(f"color: {T.GREEN}; background: transparent; letter-spacing: 1px;")

    def set_error(self, message: str):
        if self._stream_bubble is None:
            self._stream_bubble = self._bubble("FORGE BUILDER", T.RED)
        self._stream_bubble.setHtml(markdown_to_html(f"**Build failed.** {message}"))
        self._stream_bubble = None
        self._building = False
        self._send_btn.setEnabled(True)
        self._status.setText("● ERROR")
        self._status.setStyleSheet(f"color: {T.RED}; background: transparent; letter-spacing: 1px;")

    @property
    def last_html(self) -> str:
        return self._last_html
