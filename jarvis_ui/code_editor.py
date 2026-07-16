"""Cursor-style code editor: line-number gutter + multi-language syntax highlighting."""
from __future__ import annotations

import re

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextFormat,
)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

# One Dark Pro-ish palette (Cursor default feel)
_C = {
    "bg": "#0d1117",
    "gutter_bg": "#0d1117",
    "gutter_fg": "#495162",
    "gutter_cur": "#c9d1d9",
    "current_line": "#161b22",
    "text": "#c9d1d9",
    "keyword": "#c678dd",
    "builtin": "#56b6c2",
    "string": "#98c379",
    "number": "#d19a66",
    "comment": "#5c6370",
    "func": "#61afef",
    "decorator": "#e5c07b",
    "tag": "#e06c75",
    "attr": "#d19a66",
    "selection": "#264f78",
}

_PY_KEYWORDS = (
    "and as assert async await break class continue def del elif else except "
    "finally for from global if import in is lambda nonlocal not or pass raise "
    "return try while with yield None True False self match case"
).split()

_JS_KEYWORDS = (
    "abstract await break case catch class const continue debugger default delete "
    "do else enum export extends false finally for function if implements import in "
    "instanceof interface let new null package private protected public return static "
    "super switch this throw true try typeof var void while with yield async of from as"
).split()

_LANG_BY_EXT = {
    "py": "python", "pyw": "python",
    "js": "js", "jsx": "js", "ts": "js", "tsx": "js", "mjs": "js", "cjs": "js",
    "json": "json",
    "html": "html", "htm": "html", "xml": "html", "vue": "html", "svelte": "html",
    "css": "css", "scss": "css", "sass": "css",
}


def lang_for(ext_or_name: str) -> str:
    key = (ext_or_name or "").lower().lstrip(".")
    if "." in key:
        key = key.rsplit(".", 1)[-1]
    return _LANG_BY_EXT.get(key, "text")


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class CodeHighlighter(QSyntaxHighlighter):
    """Lightweight regex highlighter for Python / JS / CSS / HTML / JSON."""

    def __init__(self, document, language: str = "text"):
        super().__init__(document)
        self.language = language
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._string_fmt = _fmt(_C["string"])
        self._comment_fmt = _fmt(_C["comment"], italic=True)
        self._build_rules()

    def set_language(self, language: str) -> None:
        if language == self.language:
            return
        self.language = language
        self._build_rules()
        self.rehighlight()

    def _build_rules(self) -> None:
        r: list[tuple[re.Pattern, QTextCharFormat]] = []
        lang = self.language

        if lang == "python":
            r.append((re.compile(r"\b(" + "|".join(_PY_KEYWORDS) + r")\b"), _fmt(_C["keyword"])))
            r.append((re.compile(r"\b(print|len|range|int|str|float|list|dict|set|tuple|bool|open|super|isinstance|Exception)\b"), _fmt(_C["builtin"])))
            r.append((re.compile(r"@\w+"), _fmt(_C["decorator"])))
            r.append((re.compile(r"\bdef\s+(\w+)"), _fmt(_C["func"])))
            r.append((re.compile(r"\bclass\s+(\w+)"), _fmt(_C["func"], bold=True)))
            r.append((re.compile(r"\b\d+(\.\d+)?\b"), _fmt(_C["number"])))
        elif lang == "js":
            r.append((re.compile(r"\b(" + "|".join(_JS_KEYWORDS) + r")\b"), _fmt(_C["keyword"])))
            r.append((re.compile(r"\b(console|document|window|Math|JSON|Object|Array|Promise|useState|useEffect)\b"), _fmt(_C["builtin"])))
            r.append((re.compile(r"\bfunction\s+(\w+)"), _fmt(_C["func"])))
            r.append((re.compile(r"\b\d+(\.\d+)?\b"), _fmt(_C["number"])))
        elif lang == "css":
            r.append((re.compile(r"[.#]?[\w-]+(?=\s*\{)"), _fmt(_C["tag"])))
            r.append((re.compile(r"[\w-]+(?=\s*:)"), _fmt(_C["attr"])))
            r.append((re.compile(r"#[0-9a-fA-F]{3,8}\b"), _fmt(_C["number"])))
            r.append((re.compile(r"\b\d+(\.\d+)?(px|em|rem|%|vh|vw|s|ms)?\b"), _fmt(_C["number"])))
        elif lang == "html":
            r.append((re.compile(r"</?[\w-]+"), _fmt(_C["tag"])))
            r.append((re.compile(r"\b[\w-]+(?==)"), _fmt(_C["attr"])))
            r.append((re.compile(r">"), _fmt(_C["tag"])))
        elif lang == "json":
            r.append((re.compile(r"\"[\w-]+\"(?=\s*:)"), _fmt(_C["tag"])))
            r.append((re.compile(r"\b(true|false|null)\b"), _fmt(_C["keyword"])))
            r.append((re.compile(r"-?\b\d+(\.\d+)?\b"), _fmt(_C["number"])))

        self._rules = r

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                start = m.start(1) if m.groups() else m.start()
                end = m.end(1) if m.groups() else m.end()
                self.setFormat(start, end - start, fmt)

        # strings
        for m in re.finditer(r"(\"[^\"\\]*(?:\\.[^\"\\]*)*\"|'[^'\\]*(?:\\.[^'\\]*)*')", text):
            self.setFormat(m.start(), m.end() - m.start(), self._string_fmt)

        # comments
        if self.language == "python":
            c = text.find("#")
            if c >= 0:
                self.setFormat(c, len(text) - c, self._comment_fmt)
        elif self.language in ("js", "css"):
            c = text.find("//")
            if c >= 0 and self.language == "js":
                self.setFormat(c, len(text) - c, self._comment_fmt)


class _LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """QPlainTextEdit with a Cursor-like gutter and current-line highlight."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gutter = _LineNumberArea(self)
        self.setFont(QFont("Menlo", 12))
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {_C['bg']}; color: {_C['text']}; "
            f"border: none; padding: 6px 6px 6px 2px; selection-background-color: {_C['selection']}; }}"
            "QScrollBar:vertical { background: transparent; width: 10px; }"
            f"QScrollBar::handle:vertical {{ background: #2a3142; border-radius: 5px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._highlighter = CodeHighlighter(self.document(), "text")
        self._update_gutter_width(0)
        self._highlight_current_line()

    def set_language(self, language: str) -> None:
        self._highlighter.set_language(language)

    def line_number_area_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self, _count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def _highlight_current_line(self) -> None:
        selections = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(_C["current_line"]))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        self.setExtraSelections(selections)

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(_C["gutter_bg"]))
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        cur = self.textCursor().blockNumber()
        painter.setFont(self.font())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(_C["gutter_cur"] if num == cur else _C["gutter_fg"]))
                painter.drawText(
                    0, int(top), self._gutter.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(num + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            num += 1


EDITOR_BG = _C["bg"]
DIFF_ADD_BG = "rgba(46, 160, 67, 0.18)"
DIFF_DEL_BG = "rgba(248, 81, 73, 0.16)"
DIFF_ADD_FG = "#3fb950"
DIFF_DEL_FG = "#f85149"
