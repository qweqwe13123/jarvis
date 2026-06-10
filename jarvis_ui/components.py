"""JARVIS workspace UI components — screenshot-matched design."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSlider, QTextEdit, QVBoxLayout, QWidget,
)

from jarvis_ui.markdown_utils import markdown_to_html
from jarvis_ui import theme as T

WORKFLOW_STEPS = [
    "Thinking",
    "Searching",
    "Writing code",
    "Generating files",
    "Finished",
]


def _lbl(text: str, size: int = 8, color: str = T.TEXT_MED, bold: bool = False) -> QLabel:
    w = QLabel(text)
    w.setFont(QFont(T.FONT_UI, size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    w.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    return w


class ActivityPill(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._name = text
        self.setFixedHeight(38)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._label = QLabel(text)
        self._label.setFont(QFont(T.FONT_UI, 9))
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        lay.addStretch()
        self.set_state("idle")

    def set_state(self, state: str):
        if state == "active":
            self.setStyleSheet(f"""
                ActivityPill {{
                    background: rgba(0, 209, 255, 0.10);
                    border: 1px solid rgba(0, 209, 255, 0.22);
                    border-radius: 14px;
                }}
            """)
            self._dot.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
            self._label.setStyleSheet(f"color: {T.WHITE}; background: transparent; border: none;")
        elif state == "done":
            self.setStyleSheet(f"""
                ActivityPill {{
                    background: rgba(0, 255, 148, 0.08);
                    border: 1px solid rgba(0, 255, 148, 0.18);
                    border-radius: 14px;
                }}
            """)
            self._dot.setStyleSheet(f"color: {T.GREEN}; background: transparent; border: none;")
            self._label.setStyleSheet(f"color: {T.GREEN}; background: transparent; border: none;")
        else:
            self.setStyleSheet(f"""
                ActivityPill {{
                    background: rgba(12, 24, 36, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.04);
                    border-radius: 14px;
                }}
            """)
            self._dot.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
            self._label.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")


class JarvisConsole(QWidget):
    """Right panel: LIVE ACTIVITY pills + response stream."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pills: list[ActivityPill] = []
        self._entries: list[dict] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        hdr = _lbl("LIVE ACTIVITY", 7, T.CYAN, True)
        lay.addWidget(hdr)

        for step in WORKFLOW_STEPS:
            pill = ActivityPill(step)
            lay.addWidget(pill)
            self._pills.append(pill)

        lay.addSpacing(4)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {T.BG}; width: 6px; }}
            QScrollBar::handle:vertical {{ background: {T.BORDER_HI}; border-radius: 3px; }}
        """)
        self._output_host = QWidget()
        self._output_lay = QVBoxLayout(self._output_host)
        self._output_lay.setContentsMargins(0, 0, 0, 0)
        self._output_lay.setSpacing(8)
        self._output_lay.addStretch()
        self._scroll.setWidget(self._output_host)
        lay.addWidget(self._scroll, stretch=1)

    def reset_workflow(self):
        for pill in self._pills:
            pill.set_state("idle")

    def set_workflow_step(self, step_name: str):
        aliases = {
            "Reading Files": "Searching",
            "Analyzing Code": "Writing code",
            "Creating Files": "Generating files",
            "Editing Files": "Generating files",
        }
        step_name = aliases.get(step_name, step_name)
        try:
            idx = WORKFLOW_STEPS.index(step_name)
        except ValueError:
            return
        for i, pill in enumerate(self._pills):
            if i < idx:
                pill.set_state("done")
            elif i == idx:
                pill.set_state("active")
            else:
                pill.set_state("idle")

    def add_response(self, title: str, content: str, role: str = "assistant"):
        self._entries.insert(0, {"title": title, "content": content, "role": role})
        self._rebuild_output()

    def _rebuild_output(self):
        while self._output_lay.count() > 1:
            item = self._output_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for entry in self._entries:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {T.BG_CARD};
                    border: 1px solid {T.BORDER_HI};
                    border-radius: 12px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            hdr = QLabel(entry.get("title", "JARVIS"))
            hdr.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
            hdr.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
            cl.addWidget(hdr)
            body = QLabel()
            body.setWordWrap(True)
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setOpenExternalLinks(True)
            body.setText(markdown_to_html(entry.get("content", "")))
            body.setStyleSheet("background: transparent; border: none;")
            cl.addWidget(body)
            self._output_lay.insertWidget(0, card)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(0))


class ChatPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(24, 8, 24, 8)
        self._lay.setSpacing(10)
        self._lay.addStretch()
        self.setWidget(self._host)
        self.hide()

    def clear_messages(self):
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.hide()

    def load_messages(self, messages: list[dict]):
        self.clear_messages()
        if not messages:
            self.hide()
            return
        self.show()
        for msg in messages:
            self.add_message(msg.get("role", "user"), msg.get("content", ""), scroll=False)
        self._scroll_bottom()

    def add_message(self, role: str, content: str, scroll: bool = True):
        self.show()
        is_user = role == "user"
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {T.BG_CARD if is_user else '#0a1a28'};
                border: 1px solid {T.BORDER if is_user else T.BORDER_HI};
                border-radius: 12px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        tag = QLabel("YOU" if is_user else "JARVIS")
        tag.setFont(QFont(T.FONT_UI, 7, QFont.Weight.Bold))
        tag.setStyleSheet(f"color: {T.WHITE if is_user else T.CYAN}; background: transparent; border: none;")
        cl.addWidget(tag)
        body = QLabel()
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setText(markdown_to_html(content))
        body.setStyleSheet(f"color: {T.TEXT}; background: transparent; border: none;")
        cl.addWidget(body)
        self._lay.insertWidget(self._lay.count() - 1, card)
        if scroll:
            self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(30, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))


class NavSidebar(QWidget):
    new_chat = pyqtSignal()
    section_changed = pyqtSignal(str)
    chat_selected = pyqtSignal(str)
    workspace_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.BG_PANEL}; border-right: 1px solid {T.BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 18, 16, 16)
        lay.setSpacing(4)

        brand = QLabel("J.A.R.V.I.S")
        brand.setFont(QFont(T.FONT_DISPLAY, 15, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {T.RED}; background: transparent; letter-spacing: 6px;")
        lay.addWidget(brand)
        lay.addSpacing(14)

        self._nav_btns: dict[str, QPushButton] = {}
        for key, label, shortcut in [
            ("chat", "✦  New Agent", "⌘N"),
            ("automations", "⚡  Automations", ""),
            ("customize", "◎  Customize", ""),
        ]:
            btn = self._nav_button(label, shortcut, key == "chat")
            btn.clicked.connect(lambda _, k=key: self._on_nav(k))
            self._nav_btns[key] = btn
            lay.addWidget(btn)

        lay.addSpacing(12)
        lay.addWidget(_lbl("WORKSPACES", 7, T.CYAN, True))
        self._ws_host = QWidget()
        self._ws_lay = QVBoxLayout(self._ws_host)
        self._ws_lay.setContentsMargins(0, 4, 0, 0)
        self._ws_lay.setSpacing(2)
        lay.addWidget(self._ws_host, stretch=1)

        self._section_host = QWidget()
        self._section_lay = QVBoxLayout(self._section_host)
        self._section_lay.setContentsMargins(0, 0, 0, 0)
        self._section_host.hide()
        lay.addWidget(self._section_host)

        open_btn = QPushButton("↗  Open Workspace")
        open_btn.setFont(QFont(T.FONT_UI, 8))
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(self._link_style())
        lay.addWidget(open_btn)

        upgrade = QPushButton("Upgrade to a Pro account")
        upgrade.setFont(QFont(T.FONT_UI, 8))
        upgrade.setCursor(Qt.CursorShape.PointingHandCursor)
        upgrade.setFixedHeight(36)
        upgrade.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {T.TEXT_MED};
                border: 1px solid {T.CYAN_DIM}; border-radius: 10px;
            }}
            QPushButton:hover {{ border-color: {T.CYAN}; color: {T.CYAN}; }}
        """)
        lay.addWidget(upgrade)

        profile = QWidget()
        profile.setStyleSheet(f"background: {T.BG_CARD}; border: 1px solid {T.BORDER}; border-radius: 12px;")
        pl = QHBoxLayout(profile)
        pl.setContentsMargins(10, 8, 10, 8)
        av = QLabel("MT")
        av.setFixedSize(36, 36)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold))
        av.setStyleSheet(f"background: {T.CYAN_DIM}; color: {T.WHITE}; border-radius: 18px;")
        info = QVBoxLayout()
        info.setSpacing(0)
        info.addWidget(_lbl("Mehmet Turanoglu", 8, T.WHITE, True))
        info.addWidget(_lbl("Free Plan", 7, T.TEXT_DIM))
        pl.addWidget(av)
        pl.addLayout(info)
        pl.addStretch()
        gear = QPushButton("⚙")
        gear.setFixedSize(24, 24)
        gear.setStyleSheet("border:none; color:#7eb8d4; background:transparent;")
        pl.addWidget(gear)
        lay.addWidget(profile)

    def _nav_button(self, text: str, shortcut: str, primary: bool) -> QPushButton:
        display = f"{text}"
        if shortcut:
            btn = QPushButton()
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            inner = QHBoxLayout(btn)
            inner.setContentsMargins(12, 0, 12, 0)
            lbl = QLabel(display)
            lbl.setFont(QFont(T.FONT_UI, 9, QFont.Weight.Bold if primary else QFont.Weight.Normal))
            lbl.setStyleSheet(f"color: {T.CYAN if primary else T.TEXT_MED}; background: transparent;")
            kbd = QLabel(shortcut)
            kbd.setFont(QFont(T.FONT_UI, 8))
            kbd.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent;")
            kbd.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            inner.addWidget(lbl)
            inner.addWidget(kbd, stretch=1)
        else:
            btn = QPushButton(display)
            btn.setFixedHeight(36)
            btn.setFont(QFont(T.FONT_UI, 9))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        if primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0, 209, 255, 0.08);
                    border: 1px solid rgba(0, 209, 255, 0.20);
                    border-radius: 10px; text-align: left;
                }}
                QPushButton:hover {{ background: rgba(0, 209, 255, 0.14); }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {T.TEXT_MED};
                    border: none; border-radius: 8px; text-align: left; padding-left: 12px;
                }}
                QPushButton:hover {{ color: {T.CYAN}; background: rgba(255,255,255,0.03); }}
            """)
        return btn

    def _link_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {T.TEXT_MED};
                border: none; text-align: left; padding: 6px 0;
            }}
            QPushButton:hover {{ color: {T.CYAN}; }}
        """

    def _on_nav(self, key: str):
        if key == "chat":
            self.new_chat.emit()
        self.section_changed.emit(key)
        self._section_host.hide()
        if key == "automations":
            self._show_automations()
        elif key == "customize":
            self._show_customize()

    def _show_automations(self):
        self._clear_section()
        self._section_host.show()
        self._section_lay.addWidget(_lbl("AUTOMATIONS", 7, T.CYAN, True))
        self._auto_list = QVBoxLayout()
        host = QWidget()
        host.setLayout(self._auto_list)
        self._section_lay.addWidget(host)

    def _show_customize(self):
        self._clear_section()
        self._section_host.show()
        from memory.workspace_manager import get_settings
        settings = get_settings()
        self._section_lay.addWidget(_lbl("CUSTOMIZE", 7, T.CYAN, True))
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlainText(settings.get("system_prompt", ""))
        self._prompt_edit.setMaximumHeight(72)
        self._prompt_edit.setStyleSheet(f"background:{T.BG_CARD}; color:{T.TEXT}; border:1px solid {T.BORDER}; border-radius:8px;")
        self._section_lay.addWidget(self._prompt_edit)
        self._temp_slider = QSlider(Qt.Orientation.Horizontal)
        self._temp_slider.setRange(0, 100)
        self._temp_slider.setValue(int(float(settings.get("temperature", 0.7)) * 100))
        self._section_lay.addWidget(self._temp_slider)
        save = QPushButton("Save Settings")
        save.clicked.connect(self._save_customize)
        self._section_lay.addWidget(save)

    def _clear_section(self):
        while self._section_lay.count():
            item = self._section_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _save_customize(self):
        from memory.workspace_manager import save_settings
        save_settings({
            "system_prompt": self._prompt_edit.toPlainText().strip(),
            "temperature": self._temp_slider.value() / 100.0,
        })
        self.section_changed.emit("settings_saved")

    def refresh_workspaces(self, workspaces: list[dict], chats: list[dict]):
        while self._ws_lay.count():
            item = self._ws_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        demo = [
            ("solver company", ["Lovable dependencies a…"]),
            ("solver", ["Placeholder conversation"]),
            ("liquid-dreams-land…", ["Vercel deployment 404 …", "Vercel deployment 404 …"]),
        ]
        if not workspaces and not chats:
            for folder, children in demo:
                self._add_folder(folder, children)
            return

        chats_by_ws: dict[str, list] = {}
        for c in chats:
            chats_by_ws.setdefault(c.get("workspace_id", "default"), []).append(c)
        for ws_item in workspaces:
            name = ws_item.get("name", "Workspace")
            wid = ws_item.get("id", "")
            child_titles = [c.get("title", "Chat")[:30] for c in chats if True]
            child_titles = [c.get("title", "Chat")[:30] for c in chats][:4]
            self._add_folder(name, child_titles, wid)

    def _add_folder(self, name: str, children: list[str], ws_id: str = ""):
        row = QPushButton(f"▾  {name}")
        row.setFont(QFont(T.FONT_UI, 8, QFont.Weight.Bold))
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {T.WHITE}; border: none;
                text-align: left; padding: 6px 2px;
            }}
            QPushButton:hover {{ color: {T.CYAN}; }}
        """)
        if ws_id:
            row.clicked.connect(lambda _, w=ws_id: self.workspace_selected.emit(w))
        self._ws_lay.addWidget(row)
        for child in children:
            cbtn = QPushButton(f"    {child}")
            cbtn.setFont(QFont(T.FONT_UI, 8))
            cbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            cbtn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {T.TEXT_DIM}; border: none;
                    text-align: left; padding: 4px 2px 4px 12px;
                }}
                QPushButton:hover {{ color: {T.CYAN}; }}
            """)
            self._ws_lay.addWidget(cbtn)

    def refresh_automations(self, automations: list[dict]):
        if not hasattr(self, "_auto_list"):
            return
        while self._auto_list.count():
            item = self._auto_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class CenterInputBar(QWidget):
    submitted = pyqtSignal(str)
    plan_requested = pyqtSignal()

    def __init__(self, providers: list[str], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 0, 28, 20)
        lay.setSpacing(10)

        input_box = QFrame()
        input_box.setStyleSheet(f"""
            QFrame {{
                background: {T.BG_CARD};
                border: 1px solid {T.BORDER_HI};
                border-radius: 16px;
            }}
        """)
        ib_lay = QVBoxLayout(input_box)
        ib_lay.setContentsMargins(18, 16, 18, 12)
        ib_lay.setSpacing(10)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Ask anything, @ to mention, / for actions")
        self._input.setFont(QFont(T.FONT_UI, 11))
        self._input.setMinimumHeight(72)
        self._input.setMaximumHeight(110)
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: transparent; color: {T.WHITE};
                border: none; padding: 0;
            }}
        """)
        ib_lay.addWidget(self._input)
        self._input.installEventFilter(self)

        bottom = QHBoxLayout()
        plus = QPushButton("+")
        plus.setFixedSize(28, 28)
        plus.setStyleSheet(self._chip_style())
        bottom.addWidget(plus)

        self._provider_combo = QComboBox()
        models = providers or ["Claude Opus 4.6 (Thinking)"]
        self._provider_combo.addItems(models)
        self._provider_combo.setFixedHeight(30)
        self._provider_combo.setStyleSheet(f"""
            QComboBox {{
                background: {T.BG_PANEL}; color: {T.TEXT};
                border: 1px solid {T.BORDER}; border-radius: 14px;
                padding: 4px 14px; min-width: 200px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {T.BG_CARD}; color: {T.WHITE};
                selection-background-color: rgba(0,209,255,0.15);
            }}
        """)
        bottom.addWidget(self._provider_combo)
        bottom.addStretch()

        mic = QPushButton("🎙")
        mic.setFixedSize(34, 34)
        mic.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {T.TEXT_MED};
                border: 1px solid {T.BORDER}; border-radius: 17px;
            }}
            QPushButton:hover {{ color: {T.CYAN}; border-color: {T.CYAN_DIM}; }}
        """)
        mic.clicked.connect(self._submit)
        bottom.addWidget(mic)
        ib_lay.addLayout(bottom)
        lay.addWidget(input_box)

        pills = QHBoxLayout()
        pills.setSpacing(10)
        for label, is_plan in [("+ Composer 2.5", False), ("Plan New Idea  ⌘Tab", True)]:
            p = QPushButton(label)
            p.setFont(QFont(T.FONT_UI, 8))
            p.setCursor(Qt.CursorShape.PointingHandCursor)
            p.setFixedHeight(32)
            p.setStyleSheet(f"""
                QPushButton {{
                    background: {T.BG_CARD}; color: {T.TEXT_MED};
                    border: 1px solid {T.BORDER}; border-radius: 16px; padding: 0 14px;
                }}
                QPushButton:hover {{ color: {T.CYAN}; border-color: {T.BORDER_HI}; }}
            """)
            if is_plan:
                p.clicked.connect(self.plan_requested.emit)
            pills.addWidget(p)
        pills.addStretch()
        lay.addLayout(pills)

    def _chip_style(self) -> str:
        return f"""
            QPushButton {{
                background: {T.BG_PANEL}; color: {T.TEXT_MED};
                border: 1px solid {T.BORDER}; border-radius: 14px;
            }}
        """

    def _submit(self):
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self.submitted.emit(text)

    def get_provider(self) -> str:
        text = self._provider_combo.currentText().strip()
        if "claude" in text.lower() or "opus" in text.lower():
            return "auto"
        return text.split(" — ")[0].strip().lower()

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._submit()
                    return True
        return super().eventFilter(obj, event)
