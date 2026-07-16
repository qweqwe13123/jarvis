"""Manus-style Researcher — conversational chat with a live "computer" panel.

Left  : chat feed (rich answers: text, tables, lists) + composer.
Right : "JARVIS's Computer" — live plan / searches / sources for the active turn.

Each turn is routed automatically:
  * fresh/factual questions  -> full deep-research agent (web search + read + cite)
  * follow-ups / transforms  -> direct grounded answer using the conversation so far
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui import theme as T
from jarvis_ui.components import _AutoText, _LineIcon, _spaced_font
from jarvis_ui.markdown_utils import markdown_to_html

_DEPTHS = [
    ("quick", "Quick", 4),
    ("standard", "Standard", 6),
    ("deep", "Deep", 10),
]

_TRANSFORM_HINTS = (
    "summar", "резюм", "короче", "сократи", "table", "таблиц", "translate",
    "переведи", "rewrite", "перепиш", "bullet", "списк", "based on", "из этого",
    "на основе", "above", "выше", "reformat", "в виде", "оформи", "переформат",
)
_RESEARCH_HINTS = (
    "latest", "newest", "recent", "новост", "2026", "2025", "today", "сегодня",
    "current", "price", "цена", "стоит", "who is", "what is", "how many",
    "statistics", "data", "find", "search", "research", "актуал", "сравни",
    "compare", " vs ", "versus", "best ", "лучш", "обзор", "review", "исследуй",
)


class _Chip(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont(T.FONT_UI, 10))
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"QPushButton {{ background: {T.BG_ELEVATED}; color: {T.TEXT}; border: 1px solid {T.BORDER_HI}; "
            f"border-radius: 10px; padding: 10px 16px; text-align: left; }}"
            f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; background: {T.BG_CARD}; }}"
        )


class DeepResearchView(QWidget):
    """Self-contained Manus-style researcher chat."""

    _evt = pyqtSignal(dict)
    _research_done = pyqtSignal(str, object)
    _delta = pyqtSignal(str)
    _answer_done = pyqtSignal(str)
    _err = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._depth = "standard"
        self._running = False
        self._history: list[dict] = []
        self._last_answer = ""
        self._last_sources_md = ""
        self._turn: dict | None = None
        self._anim_phase = 0

        self.setStyleSheet(f"background: {T.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        root.addWidget(self._build_chat(), stretch=1)

        self._evt.connect(self._on_event)
        self._research_done.connect(self._on_research_done)
        self._delta.connect(self._on_delta)
        self._answer_done.connect(self._on_answer_done)
        self._err.connect(self._on_err)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick_status)

    # ------------------------------------------------------------------ header
    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet(f"background: {T.BG}; border-bottom: 1px solid {T.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        badge = QFrame()
        badge.setFixedSize(30, 30)
        badge.setStyleSheet(
            "background: rgba(64,224,208,0.10); border: 1px solid rgba(64,224,208,0.28); border-radius: 8px;"
        )
        b = QHBoxLayout(badge)
        b.setContentsMargins(0, 0, 0, 0)
        b.addWidget(_LineIcon("researcher", T.CYAN, 18), alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)

        name = QLabel("RESEARCHER")
        name.setFont(_spaced_font(T.FONT_DISPLAY, 11, 2.0, bold=True))
        name.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        lay.addWidget(name)

        lay.addStretch()
        self._status = QLabel("● READY")
        self._status.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        self._status.setStyleSheet(f"color: {T.GREEN}; background: transparent; letter-spacing: 1px;")
        lay.addWidget(self._status)

        self._new_btn = QPushButton("New chat")
        self._new_btn.clicked.connect(self._reset)
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._save_report)
        self._save_btn.setEnabled(False)
        for btn in (self._new_btn, self._save_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {T.TEXT_MED}; border: 1px solid {T.BORDER}; border-radius: 7px; padding: 5px 12px; }}"
                f"QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}"
                f"QPushButton:disabled {{ color: {T.TEXT_DIM}; border-color: {T.BORDER}; }}"
            )
            lay.addWidget(btn)
        return bar

    # ------------------------------------------------------------------ chat
    def _build_chat(self) -> QWidget:
        col = QFrame()
        col.setStyleSheet(f"background: {T.BG};")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._chat_stack = QStackedWidget()
        self._chat_stack.addWidget(self._build_hero())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 9px; }"
            f"QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 4px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        self._feed = QVBoxLayout(host)
        self._feed.setContentsMargins(0, 16, 0, 16)
        self._feed.setSpacing(14)
        self._feed.addStretch()
        self._scroll.setWidget(host)
        self._chat_stack.addWidget(self._scroll)

        lay.addWidget(self._chat_stack, stretch=1)
        lay.addWidget(self._build_composer())
        return col

    def _build_hero(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 0, 40, 0)
        outer.addStretch()

        wrap = QFrame()
        wrap.setMaximumWidth(680)
        wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(14)

        title = QLabel("What can I research for you?")
        title.setFont(_spaced_font(T.FONT_UI, 23, 0.3, bold=True))
        title.setStyleSheet(f"color: {T.WHITE}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(title)

        sub = QLabel("Ask a question. I plan the angles, search the open web, read the best sources, "
                     "and answer like an expert — with tables, structure, and citations.")
        sub.setFont(QFont(T.FONT_UI, 11))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(sub)

        chips = QVBoxLayout()
        chips.setSpacing(8)
        for ex in (
            "Compare the top open-source vector databases in 2026 for RAG",
            "Latest breakthroughs in fusion energy and realistic timelines",
            "Best local-first note apps — features, pricing, privacy (table)",
        ):
            chip = _Chip(ex)
            chip.clicked.connect(lambda _, t=ex: self._submit_text(t))
            chips.addWidget(chip)
        wl.addLayout(chips)

        center = QHBoxLayout()
        center.addStretch(1)
        center.addWidget(wrap, stretch=6)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch()
        return page

    def _build_composer(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background: {T.BG}; border-top: 1px solid {T.BORDER};")
        outer = QHBoxLayout(wrap)
        outer.setContentsMargins(24, 12, 24, 14)
        outer.setSpacing(0)
        outer.addStretch(1)

        inner = QFrame()
        inner.setMaximumWidth(860)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(6)

        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER_HI}; border-radius: 14px; }}"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 12, 14, 12)
        bl.setSpacing(10)
        self._input = QTextEdit()
        self._input.setPlaceholderText("Ask anything, or a follow-up on the last answer…")
        self._input.setFont(QFont(T.FONT_UI, 12))
        self._input.setFixedHeight(74)
        self._input.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {T.WHITE}; border: none; }}"
            f"QTextEdit:focus {{ border: none; }}"
        )
        self._input.installEventFilter(self)
        bl.addWidget(self._input)

        row = QHBoxLayout()
        row.setSpacing(8)
        depth_lbl = QLabel("Depth")
        depth_lbl.setFont(QFont(T.FONT_UI, 8))
        depth_lbl.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
        row.addWidget(depth_lbl)
        self._depth_btns: dict[str, QPushButton] = {}
        for key, label, _n in _DEPTHS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
            btn.clicked.connect(lambda _, k=key: self._set_depth(k))
            self._depth_btns[key] = btn
            row.addWidget(btn)
        row.addStretch()
        self._send_btn = QPushButton("Send  ↑")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold))
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: {T.CYAN}; color: {T.BG}; border: none; border-radius: 9px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background: #5ff0e0; }}"
            f"QPushButton:disabled {{ background: {T.BORDER_HI}; color: {T.TEXT_DIM}; }}"
        )
        self._send_btn.clicked.connect(self._submit_from_input)
        row.addWidget(self._send_btn)
        bl.addLayout(row)
        il.addWidget(box)

        outer.addWidget(inner, stretch=6)
        outer.addStretch(1)
        self._set_depth("standard")
        return wrap

    def _set_depth(self, key: str):
        self._depth = key
        for k, btn in self._depth_btns.items():
            if k == key:
                btn.setStyleSheet(
                    f"QPushButton {{ background: rgba(64,224,208,0.16); color: {T.CYAN}; "
                    f"border: 1px solid {T.CYAN_DIM}; border-radius: 8px; padding: 5px 12px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {T.TEXT_MED}; "
                    f"border: 1px solid {T.BORDER}; border-radius: 8px; padding: 5px 12px; }}"
                    f"QPushButton:hover {{ color: {T.CYAN}; }}"
                )

    # ------------------------------------------------------------------ submit
    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self._input and ev.type() == QEvent.Type.KeyPress:
            if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                ev.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                self._submit_from_input()
                return True
        return super().eventFilter(obj, ev)

    def start_topic(self, topic: str):
        self._submit_text(topic)

    def _submit_from_input(self):
        self._submit_text(self._input.toPlainText().strip())

    def _submit_text(self, text: str):
        text = (text or "").strip()
        if not text or self._running:
            return
        self._input.clear()
        if self._chat_stack.currentIndex() == 0:
            self._chat_stack.setCurrentIndex(1)
        self._running = True
        self._send_btn.setEnabled(False)
        self._history.append({"role": "user", "content": text})
        self._add_user_bubble(text)

        research = self._needs_research(text)
        self._begin_assistant_turn(research)
        if research:
            self._set_status("● RESEARCHING", T.CYAN)
            self._anim.start(420)
            max_sources = next((n for k, _l, n in _DEPTHS if k == self._depth), 6)
            query = self._contextual_query(text)
            threading.Thread(target=self._research_worker, args=(query, max_sources), daemon=True).start()
        else:
            self._set_status("● THINKING", T.CYAN)
            self._anim.start(420)
            threading.Thread(target=self._answer_worker, args=(text,), daemon=True).start()

    def _needs_research(self, msg: str) -> bool:
        if not self._last_answer:
            return True
        low = msg.lower()
        if any(h in low for h in _TRANSFORM_HINTS) and not any(h in low for h in _RESEARCH_HINTS):
            return False
        if any(h in low for h in _RESEARCH_HINTS):
            return True
        return False  # ambiguous follow-up → conversational answer using context

    def _contextual_query(self, text: str) -> str:
        if not self._last_answer:
            return text
        prior_user = next((m["content"] for m in reversed(self._history[:-1]) if m["role"] == "user"), "")
        ctx = f"{prior_user}\n{self._last_answer[:700]}".strip()
        return f"{text}\n\n[Earlier in this conversation]\n{ctx}"

    # ------------------------------------------------------------------ workers
    def _research_worker(self, query: str, max_sources: int):
        from core.deep_research import deep_research
        try:
            report = deep_research(query, max_sources=max_sources, on_event=lambda e: self._evt.emit(e))
            self._research_done.emit(report.markdown or "", report)
        except Exception as e:
            self._err.emit(str(e))

    def _answer_worker(self, text: str):
        from datetime import datetime

        from core.model_router import ModelRouterError, stream_text
        today = datetime.now().strftime("%A, %d %B %Y")
        system = (
            f"You are a Manus-style research assistant continuing a conversation. "
            f"Today's date is {today}. "
            "Write your ENTIRE answer in the SAME language as the user's latest message. "
            "Explain clearly like a smart friend — never lead with links. "
            "Open with a 2-4 sentence briefing of what you found, then optional bullets/table. "
            "Sources only at the very end (compact). "
            "Ground answers in conversation context and prior sources; keep [n] citations if reusing them."
        )
        parts: list[str] = []
        for m in self._history[-6:-1]:
            who = "User" if m["role"] == "user" else "Assistant"
            parts.append(f"{who}: {m['content']}")
        if self._last_sources_md:
            parts.append(f"\n[Sources available]\n{self._last_sources_md}")
        parts.append(f"User: {text}")
        prompt = "\n\n".join(parts)
        acc = ""
        try:
            for delta in stream_text(prompt, system=system, task_type="analysis"):
                acc += delta
                self._delta.emit(acc)
            if not acc.strip():
                raise ModelRouterError("empty response")
            self._answer_done.emit(acc)
        except Exception as e:
            self._err.emit(str(e))

    # ------------------------------------------------------------------ events
    def _on_event(self, e: dict):
        kind = e.get("type")
        if kind == "status":
            self._set_turn_status(e.get("text", ""))
        elif kind == "plan":
            queries = e.get("queries", [])
            self._set_turn_status(f"Planned {len(queries)} search angles")
        elif kind == "search":
            q = e.get("query", "")
            self._set_turn_status(f"Searching: {q}" if q else "Searching…")
        elif kind == "read":
            self._set_turn_status(f"Reading {e.get('domain', '')}")
        elif kind == "iteration":
            self._set_turn_status(f"Iteration {e.get('n', 0)} · {e.get('total', 0)} sources")
        elif kind == "gap":
            self._set_turn_status("Filling gaps…")
        elif kind == "writing":
            self._set_turn_status("Writing the answer…")

    def _on_research_done(self, markdown: str, report):
        self._finish_turn(markdown)
        self._last_sources_md = "\n".join(
            f"[{i}] {s.title} — {s.url}" for i, s in enumerate(getattr(report, "sources", []) or [], 1)
        )

    def _on_delta(self, acc: str):
        if self._turn:
            self._turn["body"].setHtml(self._wrap(markdown_to_html(acc)))
            self._scroll_bottom()

    def _on_answer_done(self, text: str):
        self._finish_turn(text)

    def _on_err(self, message: str):
        if self._turn:
            self._turn["status"].setText("Failed")
            self._turn["status"].setStyleSheet(f"color: {T.RED}; background: transparent;")
            self._turn["body"].setHtml(self._wrap(f"<span style='color:{T.RED}'>Request failed: {message}</span>"))
            self._turn["body"].setVisible(True)
        self._anim.stop()
        self._running = False
        self._send_btn.setEnabled(True)
        self._set_status("● ERROR", T.RED)

    def _finish_turn(self, markdown: str):
        self._anim.stop()
        self._running = False
        self._send_btn.setEnabled(True)
        self._last_answer = markdown
        self._history.append({"role": "assistant", "content": markdown})
        self._save_btn.setEnabled(True)
        self._set_status("● READY", T.GREEN)
        if self._turn:
            self._turn["status_wrap"].setVisible(False)
            self._turn["body"].setHtml(self._wrap(markdown_to_html(markdown)))
            self._turn["body"].setVisible(True)
        self._scroll_bottom()

    # ------------------------------------------------------------------ bubbles
    def _wrap(self, html: str) -> str:
        return f"<body style='font-family:{T.FONT_UI};font-size:13px;color:{T.TEXT};line-height:1.6;'>{html}</body>"

    def _add_user_bubble(self, text: str):
        wrap = QFrame()
        wrap.setStyleSheet("background: transparent;")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(24, 0, 24, 0)
        row.addStretch()
        bubble = QFrame()
        bubble.setMaximumWidth(560)
        bubble.setStyleSheet(
            f"QFrame {{ background: rgba(64,224,208,0.10); border: 1px solid {T.CYAN_DIM}; border-radius: 14px; }}"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 10, 14, 10)
        body = _AutoText()
        body.setFont(QFont(T.FONT_UI, 11))
        body.setHtml(self._wrap(markdown_to_html(text)))
        bl.addWidget(body)
        row.addWidget(bubble)
        self._feed.insertWidget(self._feed.count() - 1, wrap)
        self._scroll_bottom()

    def _begin_assistant_turn(self, researching: bool):
        wrap = QFrame()
        wrap.setStyleSheet("background: transparent;")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(24, 0, 24, 0)
        row.setSpacing(10)

        avatar = QFrame()
        avatar.setFixedSize(30, 30)
        avatar.setStyleSheet(
            "background: rgba(64,224,208,0.12); border: 1px solid rgba(64,224,208,0.30); border-radius: 15px;"
        )
        av = QHBoxLayout(avatar)
        av.setContentsMargins(0, 0, 0, 0)
        av.addWidget(_LineIcon("researcher", T.CYAN, 16), alignment=Qt.AlignmentFlag.AlignCenter)
        row.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {T.BG_CARD}; border: 1px solid {T.BORDER}; border-radius: 14px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        card.setGraphicsEffect(shadow)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 14)
        cl.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        name = QLabel("JARVIS Research")
        name.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {T.CYAN}; background: transparent; letter-spacing: 0.5px;")
        head.addWidget(name)
        head.addStretch()
        cl.addLayout(head)

        status_wrap = QFrame()
        status_wrap.setStyleSheet(
            f"QFrame {{ background: {T.BG_PANEL}; border: 1px solid {T.BORDER}; border-radius: 9px; }}"
        )
        sw = QHBoxLayout(status_wrap)
        sw.setContentsMargins(10, 7, 10, 7)
        sw.setSpacing(8)
        spinner = QLabel("◐")
        spinner.setFont(QFont(T.FONT_UI, 12, QFont.Weight.Bold))
        spinner.setStyleSheet(f"color: {T.CYAN}; background: transparent;")
        sw.addWidget(spinner)
        status = QLabel("Researching…" if researching else "Thinking…")
        status.setFont(QFont(T.FONT_UI, 10))
        status.setStyleSheet(f"color: {T.TEXT}; background: transparent;")
        sw.addWidget(status)
        sw.addStretch()
        cl.addWidget(status_wrap)

        body = _AutoText()
        body.setFont(QFont(T.FONT_UI, 11))
        body.setVisible(False)
        cl.addWidget(body)

        row.addWidget(card, stretch=1)
        self._feed.insertWidget(self._feed.count() - 1, wrap)
        self._turn = {"card": card, "status_wrap": status_wrap, "status": status,
                      "spinner": spinner, "body": body}
        self._scroll_bottom()

    def _set_turn_status(self, text: str):
        if self._turn and text:
            self._turn["status"].setText(text)

    def _scroll_end(self, scroll: QScrollArea):
        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _scroll_bottom(self):
        QTimer.singleShot(0, lambda: self._scroll_end(self._scroll))

    def _clear_column(self, lay: QVBoxLayout):
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ------------------------------------------------------------------ misc
    def _tick_status(self):
        frames = "◐◓◑◒"
        self._anim_phase = (self._anim_phase + 1) % len(frames)
        if self._turn:
            self._turn["spinner"].setText(frames[self._anim_phase])

    def _set_status(self, text: str, color: str):
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color}; background: transparent; letter-spacing: 1px;")

    def _reset(self):
        if self._running:
            return
        self._history.clear()
        self._last_answer = ""
        self._last_sources_md = ""
        self._turn = None
        self._clear_column(self._feed)
        self._chat_stack.setCurrentIndex(0)
        self._save_btn.setEnabled(False)
        self._set_status("● READY", T.GREEN)
        self._input.setFocus()

    def _save_report(self):
        if not self._last_answer:
            return
        default = Path.home() / "JarvisProjects" / "research"
        default.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        first_user = next((m["content"] for m in self._history if m["role"] == "user"), "report")
        slug = "".join(c if c.isalnum() else "_" for c in first_user.lower())[:40].strip("_")
        suggested = str(default / f"{slug or 'report'}_{stamp}.md")
        path, _ = QFileDialog.getSaveFileName(self, "Save answer", suggested, "Markdown (*.md)")
        if path:
            header = f"_JARVIS Researcher · {datetime.now():%Y-%m-%d %H:%M}_\n\n"
            Path(path).write_text(header + self._last_answer, encoding="utf-8")
