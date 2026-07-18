"""Single-screen permissions onboarding for AURA."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui.onboarding import tokens as T
from jarvis_ui.onboarding.widgets import (
    BlackPillButton,
    FadePage,
    PermissionRow,
    TipBubble,
    aura_logo,
    muted,
    title_html,
)

def _permissions_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "Tap each row → Allow. macOS will open the right Settings page."
    if system == "Windows":
        return (
            "Tap each row → Allow. AURA asks for each permission, then opens the "
            "matching Windows Privacy / Settings page (mic & camera should list AURA)."
        )
    return (
        "Tap each row → Allow. Your desktop settings app will open so you can "
        "enable microphone, camera, and related access."
    )


class PermissionsOnlyPage(FadePage):
    """One screen: everything AURA needs to run well."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.CREAM};")
        self._granted: set[str] = set()
        self._rows: dict[str, PermissionRow] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left
        left_w = QWidget()
        left_w.setStyleSheet(f"background: {T.CREAM};")
        left = QVBoxLayout(left_w)
        left.setContentsMargins(48, 40, 36, 36)
        left.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(aura_logo(28))
        name = QLabel("AURA")
        name.setFont(T.sans(15, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
        brand.addWidget(name)
        brand.addStretch(1)
        left.addLayout(brand)
        left.addSpacing(40)

        left.addWidget(title_html("Allow what AURA needs."))
        left.addSpacing(12)
        left.addWidget(
            muted(
                "These permissions make voice, wake, vision, and automation work. "
                "You can change them later in system settings."
            )
        )
        left.addSpacing(28)
        left.addWidget(
            TipBubble("AURA only uses access when you ask — not in the background.")
        )
        left.addStretch(1)

        self.cta = BlackPillButton("Continue")
        self.cta.setMinimumWidth(220)
        left.addWidget(self.cta, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(left_w, 42)

        # Right — permission list
        right_w = QWidget()
        right_w.setStyleSheet("background: #EFEDE8;")
        right = QVBoxLayout(right_w)
        right.setContentsMargins(28, 36, 40, 36)
        right.setSpacing(0)

        head = QLabel("Required for a full experience")
        head.setFont(T.sans(12, QFont.Weight.DemiBold))
        head.setStyleSheet(f"color: {T.MUTED}; background: transparent; border: none;")
        right.addWidget(head)
        right.addSpacing(16)

        items = [
            (
                "mic",
                "Microphone",
                "Voice mode and double-clap wake (AURA + AURA Wake).",
            ),
            (
                "camera",
                "Camera",
                "Vision features when you ask AURA to look.",
            ),
            (
                "screen",
                "Screen Recording" if platform.system() == "Darwin" else "Screen capture",
                (
                    "So AURA can understand what’s on your display."
                    if platform.system() == "Darwin"
                    else "Desktop capture for vision. Windows usually does not list this under Privacy."
                ),
            ),
            (
                "a11y",
                "Accessibility",
                "Automate clicks, typing, and app control you request.",
            ),
            (
                "automation",
                "Automation",
                "Open apps and run system actions you request.",
            ),
        ]

        for key, title, body in items:
            row = PermissionRow(key, title, body)
            row.toggled.connect(self._on_toggle)
            self._rows[key] = row
            right.addWidget(row)
            right.addSpacing(10)

        right.addSpacing(8)
        right.addWidget(muted(_permissions_hint(), 12))
        right.addStretch(1)
        root.addWidget(right_w, 58)

    def _on_toggle(self, key: str) -> None:
        from jarvis_ui.onboarding.permissions_native import request_in_app

        row = self._rows.get(key)

        def _result(
            ok: bool,
            *,
            needs_settings: bool = False,
            prompted: bool = False,
        ) -> None:
            if ok:
                self._granted.add(key)
                if row is not None:
                    row.set_allowed(True)
            else:
                if row is not None:
                    row.set_allowed(False)

        request_in_app(key, _result)  # type: ignore[arg-type]


class _GeminiVerifyWorker(QThread):
    """Background Google probe — keeps the onboarding UI responsive."""

    finished_ok = pyqtSignal(str)  # normalized key
    finished_err = pyqtSignal(str)  # user-facing message

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key

    def run(self) -> None:  # noqa: N802
        try:
            from jarvis_ui.onboarding.gemini_key import verify_gemini_key

            result = verify_gemini_key(self._key)
            if result.ok:
                from jarvis_ui.onboarding.gemini_key import normalize_key

                self.finished_ok.emit(normalize_key(self._key))
            else:
                self.finished_err.emit(result.message)
        except Exception:
            self.finished_err.emit(
                "Couldn’t verify this key right now. Try again in a moment."
            )


class ApiKeySetupPage(FadePage):
    """First-boot Gemini key — shown inside onboarding so it never depends on MainWindow."""

    submitted = pyqtSignal(str, str)  # key, os_key

    GEMINI_KEY_URL = "https://aistudio.google.com/apikey"

    def __init__(self, parent=None, *, require_live_verify: bool = True):
        super().__init__(parent)
        self._require_live_verify = bool(require_live_verify)
        self._worker: _GeminiVerifyWorker | None = None
        self._busy = False
        self.setStyleSheet(f"background: {T.CREAM};")

        detected = {"darwin": "mac", "windows": "windows"}.get(
            platform.system().lower(), "linux"
        )
        self._sel_os = detected

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left_w = QWidget()
        left_w.setStyleSheet(f"background: {T.CREAM};")
        left = QVBoxLayout(left_w)
        left.setContentsMargins(48, 40, 36, 36)
        left.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(aura_logo(28))
        name = QLabel("AURA")
        name.setFont(T.sans(15, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
        brand.addWidget(name)
        brand.addStretch(1)
        left.addLayout(brand)
        left.addSpacing(36)

        left.addWidget(title_html("One key to unlock AURA."))
        left.addSpacing(12)
        left.addWidget(
            muted(
                "Paste a free Gemini API key. Voice, agents, and tools run with your key. "
                "It stays on this Mac in Application Support (never inside the app)."
            )
        )
        left.addSpacing(22)

        tip = TipBubble("Takes ~30 seconds · free tier · no credit card.")
        left.addWidget(tip)
        left.addStretch(1)
        root.addWidget(left_w, 42)

        right_w = QWidget()
        right_w.setStyleSheet("background: #EFEDE8;")
        right = QVBoxLayout(right_w)
        right.setContentsMargins(36, 40, 40, 36)
        right.setSpacing(0)

        hdr = QLabel("Gemini API key")
        hdr.setFont(T.sans(13, QFont.Weight.DemiBold))
        hdr.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
        right.addWidget(hdr)
        right.addSpacing(10)

        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Paste key from Google AI Studio")
        self._key.setFixedHeight(48)
        self._key.setFont(T.sans(13))
        self._key.setStyleSheet(self._field_style(ok=True))
        self._key.textChanged.connect(self._on_key_edited)
        self._key.returnPressed.connect(self._submit)
        right.addWidget(self._key)
        right.addSpacing(8)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(T.sans(12))
        self._status.setStyleSheet(
            f"color: {T.MUTED}; background: transparent; border: none;"
        )
        self._status.hide()
        right.addWidget(self._status)
        right.addSpacing(8)

        link = QLabel(
            f'<a href="{self.GEMINI_KEY_URL}" style="color:{T.CYAN_DEEP}; text-decoration:none;">'
            f"Get a free Gemini API key at Google AI Studio →</a>"
        )
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link.setFont(T.sans(12))
        link.setStyleSheet("background: transparent; border: none;")
        right.addWidget(link)
        right.addSpacing(28)

        os_hdr = QLabel("Operating system")
        os_hdr.setFont(T.sans(13, QFont.Weight.DemiBold))
        os_hdr.setStyleSheet(f"color: {T.INK}; background: transparent; border: none;")
        right.addWidget(os_hdr)
        right.addSpacing(6)
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        det = QLabel(f"Auto-detected: {det_name}")
        det.setFont(T.sans(11))
        det.setStyleSheet(f"color: {T.MUTED}; background: transparent; border: none;")
        right.addWidget(det)
        right.addSpacing(12)

        os_row = QHBoxLayout()
        os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in (("windows", "Windows"), ("mac", "macOS"), ("linux", "Linux")):
            btn = QPushButton(label)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(T.sans(12, QFont.Weight.Medium))
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        right.addLayout(os_row)
        self._sel(detected)
        right.addSpacing(28)

        self.cta = BlackPillButton("Start AURA")
        self.cta.setMinimumWidth(220)
        self.cta.clicked.connect(self._submit)
        right.addWidget(self.cta, 0, Qt.AlignmentFlag.AlignLeft)
        right.addStretch(1)
        root.addWidget(right_w, 58)

    def _field_style(self, *, ok: bool, success: bool = False) -> str:
        if success:
            border = "#2F9E6B"
        elif ok:
            border = T.CHIP_BORDER
        else:
            border = "#E24B4A"
        focus = T.CYAN if ok and not success else border
        return (
            f"QLineEdit {{ background: #FFFFFF; color: {T.INK}; border: 1px solid {border}; "
            f"border-radius: 12px; padding: 0 14px; }}"
            f"QLineEdit:focus {{ border: 1px solid {focus}; }}"
        )

    def _set_status(self, text: str, *, kind: str = "muted") -> None:
        if not text:
            self._status.hide()
            self._status.setText("")
            return
        colors = {
            "muted": T.MUTED,
            "error": "#C0392B",
            "ok": "#2F9E6B",
        }
        self._status.setStyleSheet(
            f"color: {colors.get(kind, T.MUTED)}; background: transparent; border: none;"
        )
        self._status.setText(text)
        self._status.show()

    def _on_key_edited(self, _text: str = "") -> None:
        if self._busy:
            return
        self._key.setStyleSheet(self._field_style(ok=True))
        self._set_status("")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._key.setEnabled(not busy)
        for btn in self._os_btns.values():
            btn.setEnabled(not busy)
        self.cta.setEnabled(not busy)
        if busy:
            self.cta.setText("Verifying key…")
            self.cta.setCursor(Qt.CursorShape.BusyCursor)
        else:
            self.cta.setText("Start AURA")
            self.cta.setCursor(Qt.CursorShape.PointingHandCursor)

    def _sel(self, key: str) -> None:
        if self._busy:
            return
        self._sel_os = key
        for k, btn in self._os_btns.items():
            if k == key:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {T.INK}; color: #FFFFFF; border: none; "
                    f"border-radius: 12px; font-weight: 600; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: #FFFFFF; color: {T.MUTED}; "
                    f"border: 1px solid {T.CHIP_BORDER}; border-radius: 12px; }}"
                    f"QPushButton:hover {{ color: {T.INK}; border-color: {T.INK}; }}"
                )

    def prefill_existing_key(self) -> None:
        """If a key is already saved (re-download), show it so the user can continue."""
        try:
            from core.app_paths import api_keys_path
            from jarvis_ui.onboarding.gemini_key import normalize_key

            path = api_keys_path()
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            key = normalize_key(str(data.get("gemini_api_key") or ""))
            if key:
                self._key.setText(key)
        except Exception:
            pass

    def _submit(self) -> None:
        if self._busy:
            return
        from jarvis_ui.onboarding.gemini_key import (
            format_error_message,
            looks_like_gemini_key,
            normalize_key,
        )

        key = normalize_key(self._key.text())
        if not key:
            self._key.setStyleSheet(self._field_style(ok=False))
            self._set_status("Paste your Gemini API key to continue.", kind="error")
            self._key.setFocus()
            return
        if not looks_like_gemini_key(key):
            self._key.setStyleSheet(self._field_style(ok=False))
            self._set_status(format_error_message(), kind="error")
            self._key.setFocus()
            return

        # Preview / design tooling: format-only gate, no Google round-trip.
        if not self._require_live_verify:
            self._key.setText(key)
            self.submitted.emit(key, self._sel_os)
            return

        self._set_status("Checking with Google…", kind="muted")
        self._set_busy(True)

        # Drop a previous worker reference if somehow still around.
        if self._worker is not None:
            try:
                self._worker.finished_ok.disconnect()
                self._worker.finished_err.disconnect()
            except Exception:
                pass

        worker = _GeminiVerifyWorker(key, self)
        self._worker = worker

        def _ok(normalized: str) -> None:
            if self._worker is not worker:
                return
            self._worker = None
            self._key.setText(normalized)
            self._key.setStyleSheet(self._field_style(ok=True, success=True))
            self._set_status("Key verified", kind="ok")
            self._set_busy(False)
            self.cta.setEnabled(False)
            self.cta.setText("Starting…")
            self.submitted.emit(normalized, self._sel_os)

        def _err(msg: str) -> None:
            if self._worker is not worker:
                return
            self._worker = None
            self._key.setStyleSheet(self._field_style(ok=False))
            self._set_status(msg or format_error_message(), kind="error")
            self._set_busy(False)
            self._key.setFocus()

        worker.finished_ok.connect(_ok)
        worker.finished_err.connect(_err)
        worker.start()


def save_api_keys(gemini_key: str, os_name: str) -> Path:
    """Persist keys for MainWindow / JarvisLive (never inside .app / DMG)."""
    from core.app_paths import api_keys_path
    from jarvis_ui.onboarding.gemini_key import normalize_key

    path = api_keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(
        {
            "gemini_api_key": normalize_key(gemini_key),
            "os_system": os_name,
            "camera_index": existing.get("camera_index", 0),
            "openai_api_key": existing.get("openai_api_key", ""),
            "hf_token": existing.get("hf_token", ""),
            "flux_model_id": existing.get(
                "flux_model_id", "black-forest-labs/FLUX.1-schnell"
            ),
            "openrouter_api_key": existing.get("openrouter_api_key", ""),
            "groq_api_key": existing.get("groq_api_key", ""),
            "deepseek_api_key": existing.get("deepseek_api_key", ""),
            "together_api_key": existing.get("together_api_key", ""),
            "lmstudio_base_url": existing.get(
                "lmstudio_base_url", "http://localhost:1234/v1"
            ),
            "ollama_base_url": existing.get(
                "ollama_base_url", "http://localhost:11434/api/generate"
            ),
            "default_tier": existing.get("default_tier", "free"),
            "router_policy": existing.get("router_policy", "hybrid_free"),
            "free_limits": existing.get("free_limits", {"daily": 300, "hourly": 35}),
        }
    )
    path.write_text(json.dumps(existing, indent=4), encoding="utf-8")
    return path
