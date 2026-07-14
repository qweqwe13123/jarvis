"""Single-screen permissions onboarding for AURA."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
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

_PREF = {
    "mic": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    "screen": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "a11y": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
}


def _open_pref(key: str) -> None:
    url = _PREF.get(key)
    if not url:
        return
    try:
        subprocess.Popen(["open", url])
    except Exception:
        pass


class PermissionsOnlyPage(FadePage):
    """One screen: everything AURA needs to run well."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.CREAM};")
        self._granted: set[str] = set()

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
                "You can change them later in System Settings."
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
                "Screen Recording",
                "So AURA can understand what’s on your display.",
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
            right.addWidget(row)
            right.addSpacing(10)

        right.addSpacing(8)
        right.addWidget(
            muted("Tap each row → Allow. macOS will open the right Settings page.", 12)
        )
        right.addStretch(1)
        root.addWidget(right_w, 58)

    def _on_toggle(self, key: str) -> None:
        self._granted.add(key)
        _open_pref(key)


class ApiKeySetupPage(FadePage):
    """First-boot Gemini key — shown inside onboarding so it never depends on MainWindow."""

    submitted = pyqtSignal(str, str)  # key, os_key

    GEMINI_KEY_URL = "https://aistudio.google.com/apikey"

    def __init__(self, parent=None):
        super().__init__(parent)
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
                "It stays on this Mac in config/api_keys.json."
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
        self._key.setPlaceholderText("Paste key · starts with AIza…")
        self._key.setFixedHeight(48)
        self._key.setFont(T.sans(13))
        self._key.setStyleSheet(
            f"QLineEdit {{ background: #FFFFFF; color: {T.INK}; border: 1px solid {T.CHIP_BORDER}; "
            f"border-radius: 12px; padding: 0 14px; }}"
            f"QLineEdit:focus {{ border: 1px solid {T.CYAN}; }}"
        )
        right.addWidget(self._key)
        right.addSpacing(12)

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

    def _sel(self, key: str) -> None:
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

    def _submit(self) -> None:
        key = self._key.text().strip()
        if not key:
            self._key.setStyleSheet(
                f"QLineEdit {{ background: #FFFFFF; color: {T.INK}; border: 1px solid #E24B4A; "
                f"border-radius: 12px; padding: 0 14px; }}"
            )
            self._key.setFocus()
            return
        self.submitted.emit(key, self._sel_os)


def save_api_keys(gemini_key: str, os_name: str) -> Path:
    """Persist keys for MainWindow / JarvisLive."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parents[2]
    path = base / "config" / "api_keys.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(
        {
            "gemini_api_key": gemini_key,
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
