from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import os
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget, QProgressBar, QDialog, QFormLayout,
)

from memory import workspace_manager as ws
from jarvis_ui.components import (
    NavSidebar, ChatPanel, JarvisConsole, CenterInputBar, PreviewPanel,
    ConversationView, ChatCenterPane, WORKFLOW_STEPS,
)
from jarvis_ui.website_builder import WebsiteBuilderView
from jarvis_ui.code_assistant import CodeAssistantView
from jarvis_ui.deep_research import DeepResearchView
from jarvis_ui.maps_prospector import MapsProspectorView
from jarvis_ui.connectors import ConnectorsView
from jarvis_ui.computer_use import ComputerUseView
from jarvis_ui.coming_soon import ComingSoonView
from jarvis_ui.almost_ready import AlmostReadyView
from jarvis_ui.early_access import EarlyAccessView
from jarvis_ui.floating_overlay import FloatingOverlay
from jarvis_ui.global_hotkey import GlobalHotkeyService, default_hotkey, hotkey_display
from jarvis_ui.app_tray import AppTrayController
from jarvis_ui import theme as T
from core.updater.controller import UpdateController
from PyQt6.QtWidgets import QInputDialog, QMessageBox

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        from core.app_paths import resource_dir

        return resource_dir()
    return Path(__file__).resolve().parent

BASE_DIR = _base_dir()
try:
    from core.app_paths import api_keys_path as _api_keys_path

    API_FILE = _api_keys_path()
    CONFIG_DIR = API_FILE.parent
except Exception:
    CONFIG_DIR = BASE_DIR / "config"
    API_FILE = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1480, 920
_MIN_W,     _MIN_H     = 1180, 720
_LEFT_W  = 220
_LEFT_MIN = 200
_LEFT_MAX = 300

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#050a14"
    PANEL     = "#08121c"
    PANEL2    = "#0c1824"
    BORDER    = "#143040"
    BORDER_B  = "#1e4a62"
    BORDER_A  = "#1e4a62"
    PRI       = "#00d1ff"
    PRI_DIM   = "#0a6a88"
    PRI_GHO   = "rgba(0,209,255,0.10)"
    ACC       = "#ff5c00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff94"
    GREEN_D   = "#0a5c40"
    RED       = "#ff4466"
    MUTED_C   = "#ff4466"
    TEXT      = "#c8eeff"
    TEXT_DIM  = "#5a8fa8"
    TEXT_MED  = "#7eb8d4"
    WHITE     = "#e8f8ff"
    DARK      = "#050a14"
    BAR_BG    = "#0a1824"
    PANEL_HI  = "#0c1824"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            # Windows WMI temp probe is expensive and used to flash PowerShell windows.
            time.sleep(8.0 if _OS == "Windows" else 1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        run_fn = subprocess.run
        extra: dict = {}
        if _OS == "Windows":
            from core.win_subprocess import run as run_fn, hidden_kwargs

            extra.update(hidden_kwargs())
        # NVIDIA
        try:
            result = run_fn(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
                **extra,
            )
            if result.returncode == 0:
                vals = [float(v.strip()) for v in result.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # Windows: never spawn PowerShell for a HUD temperature probe.
        # WMI via powershell.exe was flashing a console every few seconds.
        if _OS == "Windows":
            return -1.0

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)
        self._compact = False
        self._dashboard_mode = False
        self._header_strip = False
        self._voice_level = 0.0
        self._smooth_voice = 0.0
        self.user_speaking = False

    def set_dashboard_mode(self, enabled: bool) -> None:
        self._dashboard_mode = bool(enabled)
        if enabled:
            self.set_compact(False)
            self._header_strip = False
        self.update()

    def set_header_strip(self, enabled: bool) -> None:
        """Compact chat header — circle only, no status line or waveform."""
        self._header_strip = bool(enabled)
        if enabled:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
        else:
            self.setMinimumSize(300, 300)
            self.setMaximumHeight(16777215)
        self.update()

    def _paint_header_badge(self, p: QPainter, w: int, h: int) -> None:
        """Crisp top-right chat orb — readable at ~76px."""
        from jarvis_ui import theme as chat_t

        p.fillRect(0, 0, w, h, QColor(chat_t.CHAT_BG))
        cx, cy = w / 2.0, h / 2.0
        fw = min(w, h)
        accent = QColor(chat_t.CHAT_ASSIST_ACCENT)
        if self.muted:
            accent = QColor(chat_t.RED)
        active = self.speaking or self.user_speaking or self.state in (
            "THINKING", "PROCESSING", "SPEAKING",
        )
        pulse = 1.0 + (0.08 if active else 0.0) + min(0.12, self._smooth_voice * 0.12)

        for i, (r_frac, alpha) in enumerate(
            ((0.46, 35), (0.38, 55), (0.30, 80), (0.22, 110))
        ):
            rr = fw * r_frac * pulse
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), alpha), 1.1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))

        for idx, (r_frac, arc_len) in enumerate(((0.42, 95), (0.34, 70))):
            ring_r = fw * r_frac
            a_val = 170 - idx * 40
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), a_val), 1.6))
            rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            start = int(self._rings[idx] * 16)
            p.drawArc(rect, start, int(arc_len * 16))

        p.setPen(QPen(accent, 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - fw * 0.13, cy - fw * 0.13, fw * 0.26, fw * 0.26))

        font = QFont(chat_t.CHAT_FONT, max(6, int(fw * 0.105)), QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 152)
        p.setFont(font)
        p.setPen(QPen(accent))
        p.drawText(
            QRectF(cx - fw * 0.42, cy - fw * 0.11, fw * 0.84, fw * 0.22),
            Qt.AlignmentFlag.AlignCenter,
            "A.U.R.A",
        )

    def set_voice_level(self, level: float) -> None:
        self._voice_level = max(0.0, float(level))
        if self.muted:
            self._voice_level = 0.0

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            self.setMinimumHeight(100)
            self.setMaximumHeight(140)
        else:
            self.setMinimumHeight(300)
            self.setMaximumHeight(16777215)
        self.updateGeometry()

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()

        voice_threshold = 380.0
        target_voice = 1.0 if self._voice_level > voice_threshold and not self.muted else 0.0
        self._smooth_voice += (target_voice - self._smooth_voice) * 0.28
        self.user_speaking = self._voice_level > voice_threshold and not self.muted
        voice_boost = min(1.0, self._voice_level / 3200.0) if self.user_speaking else 0.0

        interval = 0.10 if (self.speaking or self.user_speaking) else 0.5
        if now - self._last_t > interval:
            if self.user_speaking:
                self._tgt_scale = random.uniform(1.04, 1.10 + voice_boost * 0.06)
                self._tgt_halo  = random.uniform(130, 185 + voice_boost * 40)
            elif self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo  = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo  = random.uniform(48, 68)
            self._last_t = now

        active = self.speaking or self.user_speaking
        sp = 0.38 if active else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        if self.user_speaking:
            speeds = [2.2 + voice_boost, -1.6 - voice_boost, 2.8 + voice_boost]
        elif self.speaking:
            speeds = [1.3, -0.9, 2.0]
        else:
            speeds = [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        scan_spd = 4.5 if self.user_speaking else (3.0 if self.speaking else 1.3)
        self._scan  = (self._scan  + scan_spd) % 360
        self._scan2 = (self._scan2 + (-scan_spd * 0.7)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 5.5 if self.user_speaking else (4.2 if self.speaking else 2.0)
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        pulse_chance = 0.18 if self.user_speaking else (0.07 if self.speaking else 0.025)
        if len(self._pulses) < 4 and random.random() < pulse_chance:
            self._pulses.append(0.0)

        if (self.speaking or self.user_speaking) and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if self._header_strip:
            self._paint_header_badge(p, W, H)
            return

        p.fillRect(self.rect(), qcol(C.BG))
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # grid dots (hidden in compact chat header strip)
        if not self._header_strip:
            p.setPen(QPen(qcol(C.PRI_GHO), 1))
            for x in range(0, W, 48):
                for y in range(0, H, 48):
                    p.drawPoint(x, y)

        r_face = fw * 0.31

        # halo glow
        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
        ):
            ring_r = fw * r_frac
            base   = self._rings[idx]
            a_val  = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            col    = qcol(C.MUTED_C if self.muted else C.PRI, a_val)
            p.setPen(QPen(col, w_r)); p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect  = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn  * math.cos(rad), cy - inn  * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # face — dashboard hero uses the same text-only core as chat fallback
        if self._face_px and not self._dashboard_mode:
            fsz    = int(fw * 0.62 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            orb_r = int(fw * 0.27 * self._scale)
            oc    = (200, 0, 50) if self.muted else (0, 60, 110)
            for i in range(8, 0, -1):
                r2  = int(orb_r * i / 8)
                frc = i / 8
                a   = max(0, min(255, int(self._halo * 1.1 * frc)))
                p.setBrush(QBrush(QColor(int(oc[0]*frc), int(oc[1]*frc), int(oc[2]*frc), a)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            label_size = 22 if self._dashboard_mode else 13
            p.setPen(QPen(qcol(C.PRI, min(255, int(self._halo * 2))), 1))
            label_font = QFont(
                T.CHAT_FONT if self._dashboard_mode else "Courier New",
                label_size,
                QFont.Weight.DemiBold if self._dashboard_mode else QFont.Weight.Bold,
            )
            if self._dashboard_mode:
                label_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 168)
            else:
                label_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 148)
            p.setFont(label_font)
            p.drawText(QRectF(cx - fw * 0.36, cy - 18, fw * 0.72, 36),
                       Qt.AlignmentFlag.AlignCenter, "A.U.R.A")

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # status text + waveform (hidden on dashboard hero / compact chat header)
        if not self._dashboard_mode and not self._header_strip:
            sy = cy + fw * 0.40
            if self.muted:
                txt, col = "⊘  MUTED",     qcol(C.MUTED_C)
            elif self.speaking:
                txt, col = "●  SPEAKING",  qcol(C.ACC)
            elif self.user_speaking:
                txt, col = "●  HEARING YOU", qcol(C.GREEN)
            elif self.state == "THINKING":
                sym = "◈" if self._blink else "◇"
                txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
            elif self.state == "PROCESSING":
                sym = "▷" if self._blink else "▶"
                txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
            elif self.state == "LISTENING":
                sym = "●" if self._blink else "○"
                txt, col = f"{sym}  Always Ready",  qcol(C.GREEN)
            else:
                sym = "●" if self._blink else "○"
                txt, col = f"{sym}  {self.state}", qcol(C.PRI)

            p.setPen(QPen(col, 1))
            p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

            wy = sy + 30
            N, bw = 36, 8
            wx0 = (W - N * bw) / 2
            for i in range(N):
                if self.muted:
                    hgt, cl = 2, qcol(C.MUTED_C)
                elif self.speaking or self.user_speaking:
                    hgt = random.randint(3, 20)
                    cl  = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
                else:
                    hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                    cl  = qcol(C.BORDER_B)
                p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(52)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 10, 10)

        bar_h   = 5
        bar_y   = H - bar_h - 10
        bar_w   = W - 20
        bar_x   = 10
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(12, 8, 60, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 8, W - 12, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for AURA", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class SetupOverlay(QWidget):
    """First-boot gate: Gemini key + OS. Premium glass card with key guide link."""

    done = pyqtSignal(str, str)

    GEMINI_KEY_URL = "https://aistudio.google.com/apikey"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("SetupOverlay")
        self.setStyleSheet(f"""
            QWidget#SetupOverlay {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(5, 12, 22, 252),
                    stop:0.45 rgba(8, 22, 36, 250),
                    stop:1 rgba(4, 10, 18, 252)
                );
                border: 1px solid rgba(0, 209, 255, 0.28);
                border-radius: 18px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(0)

        brand = QLabel("AURA")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFont(QFont("SF Pro Display", 11, QFont.Weight.Bold))
        brand.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 4px;"
        )
        layout.addWidget(brand)
        layout.addSpacing(6)

        title = QLabel("Initialize your workspace")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("SF Pro Display", 18, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        layout.addWidget(title)
        layout.addSpacing(6)

        subtitle = QLabel(
            "Add a free Gemini API key once — AURA routes voice, agents,\n"
            "and tools through your key. Nothing leaves your machine by default."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setFont(QFont("SF Pro Text", 11))
        subtitle.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        key_hdr = QHBoxLayout()
        key_lbl = QLabel("Gemini API key")
        key_lbl.setFont(QFont("SF Pro Text", 10, QFont.Weight.Medium))
        key_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        key_hdr.addWidget(key_lbl)
        key_hdr.addStretch()
        layout.addLayout(key_hdr)
        layout.addSpacing(8)

        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Paste key from Google AI Studio")
        self._key_input.setFont(QFont("SF Mono", 12))
        self._key_input.setFixedHeight(44)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0, 12, 20, 0.85);
                color: {C.WHITE};
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
                padding: 0 14px;
                selection-background-color: {C.PRI_DIM};
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: rgba(0, 18, 28, 0.95);
            }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(10)

        link = QLabel(
            f'<a href="{self.GEMINI_KEY_URL}" '
            f'style="color:{C.PRI}; text-decoration:none;">'
            f"Get a free Gemini API key at Google AI Studio →</a>"
        )
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link.setFont(QFont("SF Pro Text", 11))
        link.setStyleSheet("background: transparent;")
        layout.addWidget(link)

        hint = QLabel("Takes ~30 seconds · free tier · no credit card required")
        hint.setFont(QFont("SF Pro Text", 9))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(hint)
        layout.addSpacing(20)

        os_lbl = QLabel("Operating system")
        os_lbl.setFont(QFont("SF Pro Text", 10, QFont.Weight.Medium))
        os_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        layout.addWidget(os_lbl)
        layout.addSpacing(4)

        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        det = QLabel(f"Auto-detected: {det_name}")
        det.setFont(QFont("SF Pro Text", 9))
        det.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        layout.addWidget(det)
        layout.addSpacing(10)

        os_row = QHBoxLayout()
        os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in (("windows", "Windows"), ("mac", "macOS"), ("linux", "Linux")):
            btn = QPushButton(label)
            btn.setFont(QFont("SF Pro Text", 11, QFont.Weight.Medium))
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(22)

        init_btn = QPushButton("Start AURA")
        init_btn.setFont(QFont("SF Pro Text", 13, QFont.Weight.DemiBold))
        init_btn.setFixedHeight(48)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b8e6, stop:1 #00d1ff
                );
                color: #041018;
                border: none;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d1ff, stop:1 #5ae4ff
                );
            }}
            QPushButton:pressed {{
                background: #00a8cc;
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)
        layout.addSpacing(8)

        foot = QLabel("Keys stay in Application Support on this device.")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setFont(QFont("SF Pro Text", 9))
        foot.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(foot)

    def _sel(self, key: str):
        self._sel_os = key
        for k, btn in self._os_btns.items():
            if k == key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(0, 209, 255, 0.16);
                        color: {C.WHITE};
                        border: 1px solid {C.PRI};
                        border-radius: 12px;
                        font-weight: 600;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(0, 12, 20, 0.6);
                        color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER};
                        border-radius: 12px;
                    }}
                    QPushButton:hover {{
                        color: {C.TEXT};
                        border: 1px solid {C.BORDER_B};
                        background: rgba(0, 18, 28, 0.85);
                    }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(f"""
                QLineEdit {{
                    background: rgba(0, 12, 20, 0.85);
                    color: {C.WHITE};
                    border: 1px solid {C.RED};
                    border-radius: 12px;
                    padding: 0 14px;
                }}
            """)
            self._key_input.setFocus()
            return
        self.done.emit(key, self._sel_os)


_FIXED_FORGE_PROVIDER = "gemini"
try:
    from core.gemini_models import primary as _gemini_primary

    _FIXED_FORGE_MODEL = _gemini_primary("balanced")
except Exception:
    _FIXED_FORGE_MODEL = "gemini-flash-latest"


class ApiSettingsDialog(QDialog):
    """Gemini API key only — Forge uses the balanced Gemini role with auto-fallback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini API key")
        self.setModal(True)
        self.setFixedWidth(440)
        self.setStyleSheet(
            f"QDialog {{ background: {T.BG_ELEVATED}; color: {T.TEXT}; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(0)

        title = QLabel("Gemini API key")
        title.setFont(QFont(T.SB_FONT, 16, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {T.WHITE}; background: transparent; border: none;")
        lay.addWidget(title)
        lay.addSpacing(6)

        hint = QLabel("Your key powers chat, voice, and Forge.")
        hint.setFont(QFont(T.SB_FONT, 12))
        hint.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
        lay.addWidget(hint)
        lay.addSpacing(18)

        key_lbl = QLabel("API key")
        key_lbl.setFont(QFont(T.SB_FONT, 12, QFont.Weight.Medium))
        key_lbl.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(key_lbl)
        lay.addSpacing(6)

        self._gemini = QLineEdit()
        self._gemini.setPlaceholderText("AIza… or AQ.…")
        self._gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini.setFixedHeight(40)
        self._gemini.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {T.BG_CARD}; color: {T.WHITE};"
            f"  border: 1px solid {T.BORDER}; border-radius: 10px; padding: 0 12px;"
            f"  font-family: '{T.SB_FONT}'; font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{ border: 1px solid {T.CYAN}; }}"
        )
        lay.addWidget(self._gemini)
        lay.addSpacing(16)

        model_lbl = QLabel("Forge model")
        model_lbl.setFont(QFont(T.SB_FONT, 12, QFont.Weight.Medium))
        model_lbl.setStyleSheet(f"color: {T.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(model_lbl)
        lay.addSpacing(6)

        model_box = QFrame()
        model_box.setFixedHeight(40)
        model_box.setStyleSheet(
            f"QFrame {{"
            f"  background: {T.BG_CARD}; border: 1px solid {T.BORDER};"
            f"  border-radius: 10px;"
            f"}}"
        )
        mb = QHBoxLayout(model_box)
        mb.setContentsMargins(12, 0, 12, 0)
        model_val = QLabel(_FIXED_FORGE_MODEL)
        model_val.setFont(QFont(T.SB_FONT, 13))
        model_val.setStyleSheet(f"color: {T.CYAN}; background: transparent; border: none;")
        mb.addWidget(model_val)
        mb.addStretch(1)
        fixed = QLabel("Fixed")
        fixed.setFont(QFont(T.SB_FONT, 11))
        fixed.setStyleSheet(f"color: {T.TEXT_DIM}; background: transparent; border: none;")
        mb.addWidget(fixed)
        lay.addWidget(model_box)
        lay.addSpacing(22)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        for b in (cancel, save):
            b.setFixedHeight(36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(QFont(T.SB_FONT, 12))
        cancel.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; color: {T.TEXT_MED};"
            f"  border: 1px solid {T.BORDER}; border-radius: 10px; padding: 0 16px;"
            f"}}"
            f"QPushButton:hover {{ color: {T.WHITE}; border-color: {T.BORDER_HI}; }}"
        )
        save.setStyleSheet(
            f"QPushButton {{"
            f"  background: {T.CYAN}; color: #041018;"
            f"  border: none; border-radius: 10px; padding: 0 18px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background: #33daff; }}"
        )
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

        self._load()

    def _load(self):
        cfg = {}
        if API_FILE.exists():
            try:
                cfg = json.loads(API_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        self._gemini.setText(str(cfg.get("gemini_api_key", "")))

    def save(self):
        cfg = {}
        if API_FILE.exists():
            try:
                cfg = json.loads(API_FILE.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        # Keep any advanced keys already in the file; only edit Gemini in UI.
        cfg["gemini_api_key"] = self._gemini.text().strip()
        cfg.setdefault("os_system", {"Darwin": "mac", "Windows": "windows"}.get(_OS, "linux"))
        cfg.setdefault("camera_index", 0)
        API_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        ws.save_settings({
            "builder_provider": _FIXED_FORGE_PROVIDER,
            "builder_model": _FIXED_FORGE_MODEL,
        })


class MainWindow(QMainWindow):
    _log_sig      = pyqtSignal(str)
    _state_sig    = pyqtSignal(str)
    _ai_sig       = pyqtSignal(dict)
    _workflow_sig = pyqtSignal(str)
    _chat_user_sig = pyqtSignal(str)
    _chat_ai_sig  = pyqtSignal(str)
    _preview_sig  = pyqtSignal(dict)
    _stream_delta_sig = pyqtSignal(str)
    _stream_end_sig = pyqtSignal(str)
    _activity_sig = pyqtSignal(dict)
    _builder_delta_sig = pyqtSignal(str)
    _builder_done_sig = pyqtSignal(str)
    _builder_err_sig = pyqtSignal(str)
    _code_delta_sig = pyqtSignal(str)
    _code_done_sig = pyqtSignal(str)
    _code_err_sig = pyqtSignal(str)
    _user_voice_sig = pyqtSignal(float)
    _preview_gate_sig = pyqtSignal()

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("AURA")
        self.setMinimumSize(_MIN_W, _MIN_H)

        screen = QApplication.primaryScreen().availableGeometry()
        # Fit the window to the available screen (with a small margin) so it
        # never opens partially off-screen on smaller displays.
        win_w = min(_DEFAULT_W, screen.width() - 40)
        win_h = min(_DEFAULT_H, screen.height() - 40)
        self.resize(win_w, win_h)
        self.move(
            screen.x() + max(0, (screen.width()  - win_w) // 2),
            screen.y() + max(0, (screen.height() - win_h) // 2),
        )

        self.on_text_command  = None
        self._muted           = False
        self._current_file: str | None = None
        self._active_agent = "general"
        self._center_view_mode = "dashboard"

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav = NavSidebar()
        self._nav.setMinimumWidth(_LEFT_MIN)
        self._nav.setMaximumWidth(_LEFT_MAX)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        # Invisible handle: the sidebar scrollbar is the only visual divider.
        # Keep a slim hit-target so the sidebar can still be resized by dragging.
        self._main_splitter.setHandleWidth(3)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setStyleSheet("""
            QSplitter::handle {
                background: transparent;
                border: none;
                margin: 0;
                padding: 0;
            }
            QSplitter::handle:hover { background: transparent; }
            QSplitter::handle:pressed { background: transparent; }
        """)
        self._main_splitter.addWidget(self._nav)

        self._center_panel = self._build_center_panel(face_path)
        self._init_hidden_services()

        self._workspace_stack = QStackedWidget()
        self._workspace_stack.addWidget(self._center_panel)
        self._builder = WebsiteBuilderView()
        self._workspace_stack.addWidget(self._builder)
        self._code_assistant = CodeAssistantView()
        self._workspace_stack.addWidget(self._code_assistant)
        self._maps_prospector = MapsProspectorView()
        self._workspace_stack.addWidget(self._maps_prospector)
        self._deep_research = DeepResearchView()
        self._workspace_stack.addWidget(self._deep_research)
        self._connectors = ConnectorsView()
        self._workspace_stack.addWidget(self._connectors)
        self._computer_use = ComputerUseView()
        self._workspace_stack.addWidget(self._computer_use)
        self._coming_soon = ComingSoonView()
        self._workspace_stack.addWidget(self._coming_soon)
        self._almost_ready = AlmostReadyView()
        self._workspace_stack.addWidget(self._almost_ready)
        self._early_access = EarlyAccessView()
        self._workspace_stack.addWidget(self._early_access)

        # Settings lives in the right pane only — main nav (profile) stays fixed.
        from jarvis_ui.settings_window import SettingsWindow

        self._settings_page = SettingsWindow(self, updater=None)
        self._settings_page.closed.connect(self._close_settings)
        self._settings_stack_index = self._workspace_stack.addWidget(self._settings_page)
        self._settings_return_index = 0

        self._main_splitter.addWidget(self._workspace_stack)

        saved_w = int(ws.get_settings().get("sidebar_width", _LEFT_W) or _LEFT_W)
        saved_w = max(_LEFT_MIN, min(_LEFT_MAX, saved_w))
        self._main_splitter.setSizes([saved_w, max(800, self.width() - saved_w)])
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        self._main_splitter.splitterMoved.connect(self._on_sidebar_resized)

        body.addWidget(self._main_splitter, stretch=1)

        root.addLayout(body, stretch=1)

        self._wire_navigation()
        self._refresh_sidebar()

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._on_log_line)
        self._state_sig.connect(self._apply_state)
        self._ai_sig.connect(self._apply_ai_status)
        self._workflow_sig.connect(self._on_workflow_step)
        self._chat_user_sig.connect(self._on_user_message)
        self._chat_ai_sig.connect(self._on_ai_chat_response)
        self._preview_sig.connect(self._on_preview)
        self._stream_delta_sig.connect(self._on_stream_delta)
        self._stream_end_sig.connect(self._on_stream_end)
        self._activity_sig.connect(self._on_activity)
        self._user_voice_sig.connect(self._on_user_voice_level)
        self._preview_gate_sig.connect(self._on_preview_gate_request)
        self._load_active_conversation()

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        # Show key gate AFTER first paint, and BEFORE native hotkeys (those can SIGTRAP).
        if not self._ready:
            QTimer.singleShot(50, self._ensure_setup_overlay)

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

        self._force_quit = False
        self._float_session = False
        self._sub_gate = None
        # Defer native tray/hotkey/wake UI — they caused macOS SIGTRAP before setup painted.
        QTimer.singleShot(1500, self._safe_init_floating_overlay)
        # If the free preview was already used, show soft Pro gate after paint.
        QTimer.singleShot(900, self._check_subscription_gate_on_launch)

    def _safe_init_floating_overlay(self) -> None:
        try:
            self._init_floating_overlay()
        except Exception as e:
            print(f"[AURA] Floating overlay / hotkey init deferred: {e}")
    def _init_floating_overlay(self) -> None:
        """Create once: floating launcher + global hotkey, system tray (all OS)."""
        self._float = FloatingOverlay()
        self._float.submitted.connect(self._on_float_submit)
        self._float.home_clicked.connect(self._on_float_home)
        self._float.voice_clicked.connect(self._toggle_mute)
        self._float.dismissed.connect(lambda: setattr(self, "_float_session", False))
        self._float_skip_user_mirror = False

        self._hotkeys = GlobalHotkeyService(self)
        self._hotkeys.set_host(self)

        def _on_overlay_hotkey() -> None:
            print(f"[AURA] Overlay hotkey fired → toggle ({hotkey_display(self._hotkeys.combo)})")
            try:
                self._log.append_log(
                    f"SYS: Overlay hotkey {hotkey_display(self._hotkeys.combo)}"
                )
            except Exception:
                pass
            self._float.toggle()

        self._hotkeys.triggered.connect(_on_overlay_hotkey)
        self._hotkeys.status_changed.connect(self._computer_use.set_hotkey_status)
        self._hotkeys.start(default_hotkey())

        self._computer_use.open_overlay.connect(self._float.show_animated)

        # Dev self-test: AURA_TEST_OVERLAY_HOTKEY=1 → synthesize ⌘+A and report result.
        import os as _os
        if _os.environ.get("AURA_TEST_OVERLAY_HOTKEY", "").strip() in ("1", "true", "yes"):
            QTimer.singleShot(800, self._selftest_overlay_hotkey)

        self._show_keyboard_shortcuts_overlay_hint()

        self._tray = AppTrayController(self)
        self._tray.open_requested.connect(self._on_tray_open)
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.update_requested.connect(self._on_tray_check_updates)
        self._tray.quit_requested.connect(self._quit_app)
        self._tray.start()

        self._start_cloud_entitlement_sync()

    def _start_cloud_entitlement_sync(self) -> None:
        """Refresh plan from AURA API periodically and on focus (never blocks UI)."""
        self._entitlement_timer = QTimer(self)
        self._entitlement_timer.setInterval(5 * 60 * 1000)
        self._entitlement_timer.timeout.connect(self._sync_cloud_entitlements)
        self._entitlement_timer.start()
        self._sign_in_worker = None
        QTimer.singleShot(1500, self._sync_cloud_entitlements)

    def _sync_cloud_entitlements(self) -> None:
        try:
            from jarvis_ui import user_account as UA
            from jarvis_ui.auth_async import refresh_entitlements_async

            if not UA.get_access_token():
                return

            def _done(_profile) -> None:
                if hasattr(self, "_nav"):
                    self._nav.refresh_user_account()

            refresh_entitlements_async(_done)
        except Exception:
            pass

    def changeEvent(self, event) -> None:  # noqa: N802
        try:
            from PyQt6.QtCore import QEvent

            # Debounce activate sync — avoid network storms while switching apps.
            if event.type() == QEvent.Type.WindowActivate:
                QTimer.singleShot(400, self._sync_cloud_entitlements)
        except Exception:
            pass
        super().changeEvent(event)

    def _begin_sign_in(self, *, reason: str = "sign_in") -> None:
        """Open browser login without freezing the main window.

        Repeated taps cancel any stuck previous attempt and start a fresh
        device session (so the website always opens again).
        """
        try:
            from jarvis_ui.auth_async import start_sign_in_worker
        except Exception as e:
            QMessageBox.warning(self, "Sign-in", str(e))
            return

        label = "create AURA account" if reason == "create_account" else "AURA sign-in"
        prev = getattr(self, "_sign_in_worker", None)
        if prev is not None and prev.isRunning():
            try:
                self._log.append_log("SYS: Restarting sign-in — opening a fresh browser tab…")
            except Exception:
                pass
        else:
            try:
                self._log.append_log(f"SYS: Opening browser for {label}…")
            except Exception:
                pass

        worker = start_sign_in_worker(self, timeout=180.0, replace_running=True)
        if worker is None:
            return

        def _ok() -> None:
            if getattr(self, "_sign_in_worker", None) is worker:
                self._sign_in_worker = None
            if hasattr(self, "_nav"):
                self._nav.refresh_user_account()
            try:
                from jarvis_ui import user_account as UA

                if UA.is_authenticated():
                    self._log.append_log(
                        f"SYS: Signed in as {UA.get_display_name()} · {UA.get_subtitle()}"
                    )
                else:
                    QMessageBox.warning(self, "Sign-in", "Sign-in did not complete.")
            except Exception as e:
                QMessageBox.warning(self, "Sign-in", str(e))
            self._sync_cloud_entitlements()

        def _err(msg: str) -> None:
            if getattr(self, "_sign_in_worker", None) is worker:
                self._sign_in_worker = None
            low = (msg or "").lower()
            if "cancelled" in low:
                try:
                    self._log.append_log("SYS: Previous sign-in cancelled.")
                except Exception:
                    pass
                return
            QMessageBox.warning(self, "Sign-in failed", msg)

        def _browser(_url: str) -> None:
            try:
                self._log.append_log("SYS: Browser opened — finish login on hiauraai.com.")
            except Exception:
                pass

        worker.succeeded.connect(_ok)
        worker.failed.connect(_err)
        worker.browser_opened.connect(_browser)
        worker.start()

    def _selftest_overlay_hotkey(self) -> None:
        """Synthesize the OS default overlay hotkey and write pass/fail."""
        import tempfile
        from pathlib import Path
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        report = Path(tempfile.gettempdir()) / "aura_hotkey_selftest.txt"
        try:
            before = bool(
                hasattr(self, "_float")
                and self._float.isVisible()
                and not getattr(self._float, "_closing", False)
            )
            self.raise_()
            self.activateWindow()
            combo = getattr(self, "_hotkeys", None).combo if hasattr(self, "_hotkeys") else default_hotkey()
            print(f"[AURA] SELFTEST: sending key event for {hotkey_display(combo)} …")
            mods = Qt.KeyboardModifier.NoModifier
            low = combo.lower()
            if "meta" in low or "cmd" in low or "command" in low:
                mods |= Qt.KeyboardModifier.MetaModifier
            if "ctrl" in low or "control" in low:
                mods |= Qt.KeyboardModifier.ControlModifier
            if "alt" in low or "option" in low:
                mods |= Qt.KeyboardModifier.AltModifier
            if "shift" in low:
                mods |= Qt.KeyboardModifier.ShiftModifier
            key = Qt.Key.Key_Space if "space" in low else Qt.Key.Key_A
            ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, "a" if key == Qt.Key.Key_A else " ")
            app = QApplication.instance()
            if app is not None:
                app.postEvent(self, ev)
            QTimer.singleShot(400, lambda: self._selftest_overlay_hotkey_finish(before, report))
        except Exception as e:
            report.write_text(f"FAIL setup: {e}\n", encoding="utf-8")
            print(f"[AURA] SELFTEST FAIL setup: {e}")

    def _selftest_overlay_hotkey_finish(self, before_visible: bool, report) -> None:
        try:
            after = bool(
                hasattr(self, "_float")
                and self._float.isVisible()
                and not getattr(self._float, "_closing", False)
            )
            ok = after != before_visible or after is True
            # Stronger: overlay should be visible after hotkey from hidden state
            if not before_visible:
                ok = after is True
            line = (
                f"{'PASS' if ok else 'FAIL'} before={before_visible} after={after} "
                f"combo={getattr(self, '_hotkeys', None).combo if hasattr(self, '_hotkeys') else '?'}\n"
            )
            report.write_text(line, encoding="utf-8")
            print(f"[AURA] SELFTEST {line.strip()}")
            try:
                self._log.append_log(f"SYS: Hotkey selftest {line.strip()}")
            except Exception:
                pass
        except Exception as e:
            report.write_text(f"FAIL finish: {e}\n", encoding="utf-8")
            print(f"[AURA] SELFTEST FAIL finish: {e}")

    def _show_keyboard_shortcuts_overlay_hint(self) -> None:
        # Extend shortcuts help text next time it's opened — also log once.
        hk = hotkey_display(default_hotkey())
        if hasattr(self, "_log"):
            self._log.append_log(f"SYS: Floating overlay ready — press {hk} anytime.")

    def _on_float_submit(self, text: str) -> None:
        # Stay in the floating window — do not raise the main app.
        self._float_session = True
        self._float_skip_user_mirror = True
        if self.isVisible():
            self._center_view_mode = "chat"
            if hasattr(self, "_chat_center"):
                self._chat_center.set_view_mode("chat")
            self._active_agent = "general"
        self._float.add_user(text)
        self._send_from_bar(text)

    def _on_float_home(self) -> None:
        self._float.hide_animated()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._on_agent_selected("dashboard")

    def _float_visible(self) -> bool:
        return hasattr(self, "_float") and self._float.isVisible() and not self._float._closing

    def _ensure_float_for_live(self) -> None:
        """If main window is hidden, surface the floating chat for voice/replies."""
        if not hasattr(self, "_float"):
            return
        if self.isVisible() and not getattr(self, "_float_session", False):
            return
        if not self._float_visible():
            self._float_session = True
            self._float.show_animated()

    def _on_tray_open(self) -> None:
        # Floating overlay from tray on every OS.
        if hasattr(self, "_float"):
            self._float_session = True
            self._float.show_animated()
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_check_updates(self) -> None:
        updater = getattr(self, "_updater_ref", None)
        if updater is not None:
            if hasattr(updater, "check_now"):
                updater.check_now()
            elif hasattr(updater, "_service"):
                updater._service.check_for_updates(background=True)
            if hasattr(self, "_log"):
                self._log.append_log("SYS: Checking for updates…")
            # If an update is already known, open the Cursor-style update flow.
            try:
                state = updater._service.state
                if state.release and hasattr(updater, "open_update_ui"):
                    updater.open_update_ui()
            except Exception:
                pass
            return
        QMessageBox.information(self, "Updates", "Checking for updates…")

    def _on_update_requested(self) -> None:
        updater = getattr(self, "_updater_ref", None)
        if updater is not None and hasattr(updater, "open_update_ui"):
            updater.open_update_ui()
            return
        QMessageBox.information(self, "Updates", "No update controller is available.")

    def _quit_app(self) -> None:
        self._force_quit = True
        if hasattr(self, "_hotkeys"):
            self._hotkeys.stop()
        if hasattr(self, "_tray"):
            self._tray.stop()
        if hasattr(self, "_float"):
            self._float.close()
            self._float.deleteLater()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._force_quit:
            if hasattr(self, "_hotkeys"):
                self._hotkeys.stop()
            event.accept()
            return
        # Hide to tray / menu bar — do not quit.
        event.ignore()
        self.hide()
        if hasattr(self, "_tray") and self._tray._tray is not None:
            self._tray.show_message(
                "AURA",
                f"Still running in the background. "
                f"Press {hotkey_display(default_hotkey())} "
                f"for the floating bar.",
            )

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 520, 560
            cw = self.centralWidget()
            self._overlay.setGeometry(
                max(12, (cw.width()  - ow) // 2),
                max(12, (cw.height() - oh) // 2),
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"{h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("--:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge("AURA", C.PRI_DIM))
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        title = QLabel("A.U.R.A")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Courier New", 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        mid.addWidget(title)
        sub = QLabel("Just A Rather Very Intelligent System")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Courier New", 7))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(sub)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        if hasattr(self, "_uptime_lbl"):
            try:
                boot_t = psutil.boot_time()
                elapsed = time.time() - boot_t
                h = int(elapsed // 3600)
                m = int((elapsed % 3600) // 60)
                self._uptime_lbl.setText(f"{h:02d}:{m:02d}")
            except Exception:
                pass

    def _available_providers(self) -> list[str]:
        items = ["Live Voice (Gemini)", "auto — Smart Router"]
        try:
            cfg = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
        except Exception:
            cfg = {}
        mapping = [
            ("gemini", "gemini_api_key", "Gemini 2.5 Flash"),
            ("openrouter", "openrouter_api_key", "OpenRouter"),
            ("groq", "groq_api_key", "Groq Llama 3.3"),
            ("deepseek", "deepseek_api_key", "DeepSeek Chat"),
        ]
        for pid, key, label in mapping:
            val = cfg.get(key, "")
            if val and len(str(val)) > 5:
                items.append(f"{label}")
        return items

    def _build_center_panel(self, face_path: str) -> QWidget:
        self._dashboard_hud = HudCanvas(face_path)
        self._dashboard_hud.set_dashboard_mode(True)
        self._dashboard_hud.setMinimumHeight(360)

        self._chat_center = ChatCenterPane(
            self._available_providers(), dashboard_hud=self._dashboard_hud,
        )
        self.hud = self._chat_center.chat_orb()
        self._conv = self._chat_center.conv
        self._input_bar = self._chat_center.input_bar
        self._chat_center.submitted.connect(self._send_from_bar)
        self._chat_center.files_submitted.connect(self._send_from_bar_with_files)
        self._chat_center.plan_requested.connect(self._send_plan_mode)
        self._chat_center.mute_clicked.connect(self._toggle_mute)

        self._chat = ChatPanel()
        self._chat.hide()
        self._chat_center.set_view_mode("dashboard")
        return self._chat_center

    def _sync_hero_compact(self):
        if getattr(self, "_center_view_mode", "chat") == "dashboard":
            if hasattr(self, "_chat_center"):
                self._chat_center.set_hud_compact(False)
            return
        has_messages = hasattr(self, "_conv") and self._conv.has_messages()
        if hasattr(self, "_chat_center"):
            self._chat_center.set_hud_compact(has_messages)

    def _wire_navigation(self):
        self._nav.new_chat.connect(self._on_new_chat)
        self._nav.agent_selected.connect(self._on_agent_selected)
        self._nav.chat_selected.connect(self._on_chat_selected)
        self._nav.workspace_selected.connect(self._on_workspace_selected)
        self._nav.section_changed.connect(self._on_section_changed)
        self._nav.workspace_create.connect(self._on_ws_create)
        self._nav.workspace_rename.connect(self._on_ws_rename)
        self._nav.workspace_delete.connect(self._on_ws_delete)
        self._nav.chat_rename.connect(self._on_chat_rename)
        self._nav.chat_delete.connect(self._on_chat_delete)
        self._nav.chat_pin.connect(self._on_chat_pin)
        self._nav.settings_requested.connect(self._open_settings)
        self._nav.update_requested.connect(self._on_update_requested)
        self._nav.profile_menu_action.connect(self._on_profile_menu_action)
        sc = QShortcut(QKeySequence("Ctrl+N"), self)
        sc.activated.connect(self._on_new_chat)
        sc2 = QShortcut(QKeySequence("Meta+N"), self)
        sc2.activated.connect(self._on_new_chat)
        self._builder.submitted.connect(self._on_builder_submit)
        self._builder_delta_sig.connect(self._builder.on_delta)
        self._builder_done_sig.connect(self._builder.finish)
        self._builder_err_sig.connect(self._builder.set_error)
        self._builder_history: list[dict] = []
        self._code_assistant.submitted.connect(self._on_code_submit)
        self._code_delta_sig.connect(self._code_assistant.on_delta)
        self._code_done_sig.connect(self._code_assistant.finish)
        self._code_err_sig.connect(self._code_assistant.set_error)
        self._code_history: list[dict] = []

    def _on_sidebar_resized(self, _pos: int, _index: int) -> None:
        w = self._nav.width()
        if _LEFT_MIN <= w <= _LEFT_MAX:
            ws.save_settings({"sidebar_width": w})

    def _show_keyboard_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "⌘N / Ctrl+N — New session\n"
            f"{hotkey_display(default_hotkey())} — Floating overlay\n"
            "F4 — Toggle mute\n"
            "F11 — Fullscreen\n"
            "Enter — Send message\n"
            "Esc — Hide floating overlay",
        )

    def _on_profile_menu_action(self, action: str) -> None:
        from jarvis_ui import user_account as UA

        if action == "profile":
            QMessageBox.information(
                self,
                "Profile",
                f"Signed in as {UA.get_display_name()}.\nPlan: {UA.get_subtitle()}",
            )
        elif action == "settings":
            self._open_settings()
        elif action == "permissions":
            try:
                from jarvis_ui.permissions_panel import PermissionsDialog

                PermissionsDialog(self).exec()
            except Exception as e:
                QMessageBox.warning(self, "Permissions", str(e))
        elif action == "subscription":
            if UA.is_authenticated():
                UA.open_account()
                self._log.append_log("SYS: Opening account / billing on the web…")
            else:
                UA.open_account()
                self._log.append_log("SYS: Opening web account — sign in to subscribe.")
        elif action == "referral":
            try:
                from jarvis_ui.referral_dialog import show_referral_dialog

                result = show_referral_dialog(self)
                if result == 2:
                    self._begin_sign_in(reason="sign_in")
                else:
                    self._log.append_log("SYS: Referral dialog closed.")
            except Exception as e:
                UA.open_referral()
                self._log.append_log(f"SYS: Referral opened in browser ({e}).")
        elif action == "shortcuts":
            self._show_keyboard_shortcuts()
        elif action == "help":
            UA.open_support()
            self._log.append_log("SYS: Help & Support opened in browser.")
        elif action == "sign_in":
            self._begin_sign_in(reason="sign_in")
        elif action == "create_account":
            self._begin_sign_in(reason="create_account")
        elif action == "sign_out":
            from jarvis_ui.auth_async import sign_out_async

            sign_out_async(lambda: self._nav.refresh_user_account())
            self._log.append_log("SYS: Signed out — Guest mode.")
    def _refresh_sidebar(self):
        workspaces = ws.list_workspaces()
        chats = ws.list_chats()
        active_ws, active_chat = ws.get_active_ids()
        self._nav.refresh(workspaces, chats, active_ws, active_chat)
        self._nav.refresh_automations(ws.load_automations())

    def _load_active_conversation(self):
        state = ws.get_session_state()
        if hasattr(self, "_conv"):
            self._conv.load(state.get("messages", []), state.get("artifacts", []))
        self._sync_hero_compact()

    def _reset_session_view(self):
        """Reset center panel when a new session starts."""
        if hasattr(self, "_conv"):
            self._conv.clear()
        self._sync_hero_compact()

    def _on_new_chat(self):
        ws.create_chat()
        self._reset_session_view()
        self._refresh_sidebar()

    def _on_agent_selected(self, agent_key: str):
        # Browse dashboard / chat freely; paid surfaces re-open Pro gate after preview.
        _paid_surfaces = {
            "computer_use",
            "connectors",
            "researcher",
            "writer",
            "designer",
            "automation",
            "maps_prospector",
            "website",
            "code",
        }
        if agent_key in _paid_surfaces and not self._require_subscription():
            return

        if agent_key == "dashboard":
            self._center_view_mode = "dashboard"
            self._workspace_stack.setCurrentIndex(0)
            if hasattr(self, "_chat_center"):
                self._chat_center.set_view_mode("dashboard")
            return
        if agent_key == "chat":
            self._center_view_mode = "chat"
            self._workspace_stack.setCurrentIndex(0)
            if hasattr(self, "_chat_center"):
                self._chat_center.set_view_mode("chat")
            self._sync_hero_compact()
            agent_key = "general"

        if agent_key == "connectors":
            self._workspace_stack.setCurrentIndex(5)
            return
        if agent_key == "computer_use":
            self._workspace_stack.setCurrentIndex(6)
            return
        if agent_key == "coming_soon":
            self._workspace_stack.setCurrentIndex(7)
            return
        if agent_key == "almost_ready":
            self._workspace_stack.setCurrentIndex(8)
            return
        # Website Builder / Code Assistant gated until founding clients.
        if agent_key in ("website", "code"):
            feature = (
                "Website Builder" if agent_key == "website" else "Code Assistant"
            )
            self._early_access.set_feature(feature)
            self._workspace_stack.setCurrentIndex(9)
            self._active_agent = agent_key
            if hasattr(self, "_log"):
                self._log.append_log(f"SYS: Early access — {feature}")
            return

        from core.agents import get_agent
        agent = get_agent(agent_key)
        self._active_agent = agent_key
        if hasattr(self, "_log"):
            self._log.append_log(f"SYS: Agent mode → {agent.name}")
        if agent_key == "maps_prospector":
            self._maps_prospector.reset_overlay()
            self._workspace_stack.setCurrentIndex(3)
        elif agent_key == "researcher":
            self._workspace_stack.setCurrentIndex(4)
        else:
            self._workspace_stack.setCurrentIndex(0)

    def _on_builder_submit(self, prompt: str):
        if not self._require_subscription():
            return
        from core.agents import get_agent
        agent = get_agent("website")
        self._builder.add_user(prompt)
        self._builder.begin_build()
        self._builder_history.append({"role": "user", "content": prompt})
        history = list(self._builder_history)
        provider = _FIXED_FORGE_PROVIDER
        model = _FIXED_FORGE_MODEL
        ws.save_settings({"builder_provider": provider, "builder_model": model})
        threading.Thread(
            target=self._run_builder, args=(agent.system_prompt, history, provider, model), daemon=True
        ).start()

    def _run_builder(self, system_prompt: str, history: list[dict], provider: str, model: str):
        from core.model_router import stream_text, ModelRouterError
        # Render the running transcript into a single user prompt so multi-turn
        # change requests carry the previous HTML for a full rebuild.
        parts: list[str] = []
        for msg in history[:-1]:
            who = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{who}: {msg['content']}")
        parts.append(f"User: {history[-1]['content']}")
        prompt = "\n\n".join(parts)

        pref = (provider or "gemini").lower()

        acc = ""
        last_emit = 0.0
        try:
            for delta in stream_text(prompt, system=system_prompt, task_type="coding",
                                     preferred_provider=pref, preferred_model=(model or "").strip()):
                acc += delta
                now = time.monotonic()
                if now - last_emit >= 0.12:
                    last_emit = now
                    self._builder_delta_sig.emit(acc)
            if not acc.strip():
                raise ModelRouterError("empty response")
            self._builder_history.append({"role": "assistant", "content": acc})
            self._builder_done_sig.emit(acc)
        except Exception as e:
            self._builder_err_sig.emit(str(e))

    def _on_code_submit(self, prompt: str):
        from core.agents import get_agent
        agent = get_agent("code")
        self._code_assistant.add_user(prompt)
        self._code_assistant.begin_run()
        self._code_history.append({"role": "user", "content": prompt})
        history = list(self._code_history)
        provider = self._input_bar.get_provider() if hasattr(self, "_input_bar") else "auto"
        threading.Thread(
            target=self._run_code_assistant, args=(agent.system_prompt, history, provider), daemon=True
        ).start()

    def _run_code_assistant(self, system_prompt: str, history: list[dict], provider: str):
        from core.model_router import stream_text, ModelRouterError

        parts: list[str] = []
        for msg in history[:-1]:
            who = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{who}: {msg['content']}")
        parts.append(f"User: {history[-1]['content']}")
        prompt = "\n\n".join(parts)

        ctx = ""
        if hasattr(self, "_code_assistant"):
            ctx = self._code_assistant.get_workspace_context()
        if ctx:
            prompt += (
                "\n\n## Open project context\n"
                f"{ctx}\n\n"
                "Apply changes directly to this project. When writing files, always include "
                "`# file: relative/path` as the first line inside each code fence."
            )

        pref = "auto"
        low = (provider or "").lower()
        if "gemini" in low:
            pref = "gemini"
        elif "groq" in low:
            pref = "groq"
        elif "openrouter" in low:
            pref = "openrouter"
        elif "deepseek" in low:
            pref = "deepseek"

        acc = ""
        last_emit = 0.0
        try:
            for delta in stream_text(prompt, system=system_prompt, task_type="coding",
                                     preferred_provider=pref):
                acc += delta
                now = time.monotonic()
                if now - last_emit >= 0.12:
                    last_emit = now
                    self._code_delta_sig.emit(acc)
            if not acc.strip():
                raise ModelRouterError("empty response")
            self._code_history.append({"role": "assistant", "content": acc})
            self._code_done_sig.emit(acc)
        except Exception as e:
            self._code_err_sig.emit(str(e))

    def _on_chat_selected(self, chat_id: str):
        ws.set_active_chat(chat_id)
        self._load_active_conversation()
        self._refresh_sidebar()

    def _on_workspace_selected(self, ws_id: str):
        ws.set_active_workspace(ws_id)
        self._reset_session_view()
        self._refresh_sidebar()

    def _on_ws_create(self):
        name, ok = QInputDialog.getText(self, "New Workspace", "Workspace name:")
        if ok and name.strip():
            ws.add_workspace(name.strip())
            self._reset_session_view()
            self._refresh_sidebar()

    def _on_ws_rename(self, ws_id: str):
        cur = next((x.get("name", "") for x in ws.list_workspaces() if x.get("id") == ws_id), "")
        name, ok = QInputDialog.getText(self, "Rename Workspace", "New name:", text=cur)
        if ok and name.strip():
            ws.rename_workspace(ws_id, name.strip())
            self._refresh_sidebar()

    def _on_ws_delete(self, ws_id: str):
        if ws_id == "default":
            return
        r = QMessageBox.question(self, "Delete Workspace",
                                 "Delete this workspace and all its sessions?")
        if r == QMessageBox.StandardButton.Yes:
            ws.delete_workspace(ws_id)
            self._reset_session_view()
            self._refresh_sidebar()

    def _on_chat_rename(self, chat_id: str):
        cur = next((c.get("title", "") for c in ws.list_chats() if c.get("id") == chat_id), "")
        name, ok = QInputDialog.getText(self, "Rename Session", "New name:", text=cur)
        if ok and name.strip():
            ws.rename_chat(chat_id, name.strip())
            self._refresh_sidebar()

    def _on_chat_delete(self, chat_id: str):
        ws.delete_chat(chat_id)
        self._reset_session_view()
        self._load_active_conversation()
        self._refresh_sidebar()

    def _on_chat_pin(self, chat_id: str):
        ws.toggle_pin_chat(chat_id)
        self._refresh_sidebar()

    def _on_section_changed(self, section: str):
        if section == "automation_create":
            ws.save_automation("New Workflow", "Describe automation goal…", "draft")
            self._refresh_sidebar()
        elif section == "automations_more":
            self._workspace_stack.setCurrentIndex(7)
        elif section.startswith("run_auto:"):
            auto_id = section.split(":", 1)[1]
            self._log.append_log(f"SYS: Running automation {auto_id}")
        elif section == "settings_saved":
            self._log.append_log("SYS: Customize settings saved.")

    def _open_settings(self):
        """Open Settings in the right pane; left nav / profile stay put."""
        page = getattr(self, "_settings_page", None)
        stack = getattr(self, "_workspace_stack", None)
        if page is None or stack is None:
            return
        settings_ix = getattr(self, "_settings_stack_index", None)
        if settings_ix is None:
            return
        if stack.currentIndex() != settings_ix:
            self._settings_return_index = stack.currentIndex()
        page.set_updater(getattr(self, "_updater_ref", None))
        page.open_page("general")
        stack.setCurrentIndex(settings_ix)
        self._log.append_log("SYS: Settings opened.")

    def _close_settings(self):
        stack = getattr(self, "_workspace_stack", None)
        settings_ix = getattr(self, "_settings_stack_index", None)
        if stack is not None and settings_ix is not None and stack.currentIndex() == settings_ix:
            back = int(getattr(self, "_settings_return_index", 0) or 0)
            if back == settings_ix:
                back = 0
            stack.setCurrentIndex(max(0, min(back, stack.count() - 1)))
        try:
            self._nav.refresh_user_account()
        except Exception:
            pass
        self._log.append_log("SYS: Settings closed.")

    def _settings_is_open(self) -> bool:
        stack = getattr(self, "_workspace_stack", None)
        settings_ix = getattr(self, "_settings_stack_index", None)
        return bool(
            stack is not None
            and settings_ix is not None
            and stack.currentIndex() == settings_ix
        )

    def _subscription_allows_use(self) -> bool:
        """True if Pro or free preview still available."""
        try:
            from jarvis_ui.preview_access import can_start_turn, is_pro

            return bool(is_pro() or can_start_turn())
        except Exception:
            return True

    def _require_subscription(self) -> bool:
        """Allow action, or show soft Pro gate and return False."""
        if self._subscription_allows_use():
            return True
        self._show_subscription_gate(reason="preview")
        return False

    def _check_subscription_gate_on_launch(self) -> None:
        try:
            from jarvis_ui.preview_access import can_start_turn, is_pro

            if is_pro() or can_start_turn():
                return
            self._show_subscription_gate(reason="preview")
        except Exception as e:
            print(f"[AURA] Subscription gate check failed: {e}")

    def _show_subscription_gate(self, *, reason: str = "preview") -> None:
        try:
            from jarvis_ui.preview_access import is_pro
            from jarvis_ui.subscription_gate import SubscriptionGateDialog
        except Exception as e:
            print(f"[AURA] Could not load subscription gate: {e}")
            return
        if is_pro():
            return
        if self._sub_gate is not None and self._sub_gate.isVisible():
            self._sub_gate.raise_()
            self._sub_gate.activateWindow()
            return
        dlg = SubscriptionGateDialog(self, reason=reason)
        dlg.unlocked.connect(self._on_subscription_unlocked)
        dlg.dismissed.connect(self._on_subscription_dismissed)
        self._sub_gate = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        try:
            self._log.append_log(
                "SYS: Pro required — you can browse the app; chat/voice reopen this."
            )
        except Exception:
            pass

    def _on_subscription_dismissed(self) -> None:
        self._sub_gate = None
        try:
            self._log.append_log(
                "SYS: Back to app — subscribe when you chat, speak, or run an agent."
            )
        except Exception:
            pass

    def _on_subscription_unlocked(self) -> None:
        self._sub_gate = None
        try:
            self._log.append_log("SYS: Pro unlocked — unlimited desktop access.")
        except Exception:
            pass

    def _on_preview_gate_request(self) -> None:
        self._force_mute_for_gate()
        self._show_subscription_gate(reason="preview")

    def _force_mute_for_gate(self) -> None:
        """Mute live mic without subscription checks (after free preview is used)."""
        if self._muted:
            return
        self._muted = True
        try:
            self.hud.muted = True
            if hasattr(self, "_dashboard_hud"):
                self._dashboard_hud.muted = True
            self._style_mute_btn()
            self._apply_state("MUTED")
            if hasattr(self, "_float"):
                self._float.set_muted(True)
        except Exception:
            pass
        try:
            self._log.append_log("SYS: Microphone muted — free preview used.")
        except Exception:
            pass

    def _maybe_consume_preview(self, text: str, *, require_pending: bool = True) -> None:
        try:
            from jarvis_ui.preview_access import note_assistant_success

            if note_assistant_success(text, require_pending=require_pending):
                # Stop further live voice immediately; show Pro gate shortly after.
                self._force_mute_for_gate()
                QTimer.singleShot(
                    900, lambda: self._show_subscription_gate(reason="preview")
                )
        except Exception as e:
            print(f"[AURA] Preview consume failed: {e}")

    def _on_log_line(self, text: str):
        self._log.append_log(text)
        low = text.lower()
        if low.startswith(("jarvis:", "aura:")):
            msg = text.split(":", 1)[1].strip()
            self._on_ai_chat_response(msg)

    def _on_user_message(self, text: str, images: list | None = None) -> bool:
        try:
            from jarvis_ui.preview_access import note_user_turn

            if not note_user_turn():
                self._force_mute_for_gate()
                self._show_subscription_gate(reason="preview")
                return False
        except Exception:
            pass
        if not hasattr(self, "_conv"):
            return False
        if images:
            self._conv.add_user_with_images(text, list(images))
            ws.add_message("user", text, meta={"images": list(images)})
        else:
            self._conv.add_user(text)
            ws.add_message("user", text)
        self._refresh_sidebar()
        self._sync_hero_compact()
        # Mirror into floating overlay (voice or text) without opening main window.
        if getattr(self, "_float_session", False) or self._float_visible() or not self.isVisible():
            self._ensure_float_for_live()
            if hasattr(self, "_float") and self._float_visible():
                # Avoid duplicating the bubble we already added on submit.
                if not getattr(self, "_float_skip_user_mirror", False):
                    self._float.add_user(text)
                self._float_skip_user_mirror = False
        return True

    def _on_ai_chat_response(self, text: str):
        if not hasattr(self, "_conv"):
            return
        self._conv.clear_live_activity()
        self._conv.add_assistant(text)
        ws.add_message("assistant", text)
        self._refresh_sidebar()
        if getattr(self, "_float_session", False) or self._float_visible() or not self.isVisible():
            self._ensure_float_for_live()
            if hasattr(self, "_float") and self._float_visible():
                self._float.add_assistant(text)
        self._maybe_consume_preview(text)

    def _on_stream_delta(self, text: str):
        if hasattr(self, "_conv"):
            self._conv.stream_delta(text)
        if getattr(self, "_float_session", False) or self._float_visible() or not self.isVisible():
            self._ensure_float_for_live()
            if hasattr(self, "_float") and self._float_visible():
                self._float.stream_delta(text)

    def _on_stream_end(self, text: str):
        if not hasattr(self, "_conv"):
            return
        self._conv.stream_end(text)
        if text.strip():
            ws.add_message("assistant", text)
            self._refresh_sidebar()
            # Startup greeting has no pending user turn — must not consume preview.
            self._maybe_consume_preview(text, require_pending=True)
        if hasattr(self, "_float") and self._float_visible():
            self._float.stream_end(text)

    def _normalize_workflow_label(self, step: str) -> str:
        """Map internal progress to a user-facing chat status line."""
        raw = (step or "").strip()
        if not raw:
            return "Thinking"
        low = raw.lower()
        if low == "thinking":
            return "Thinking"
        if "search" in low or "deep research" in low:
            return "Searching"
        if "read" in low and ("file" in low or "page" in low):
            return "Reading files"
        if "writing report" in low or ("writ" in low and "code" in low):
            return "Writing code"
        if "generat" in low and "image" in low:
            return "Generating image"
        if "generat" in low and "file" in low:
            return "Generating files"
        if low.startswith("running "):
            tool = raw[8:].strip().lower()
            if "search" in tool or "research" in tool or "fetch" in tool:
                return "Searching"
            if "browser" in tool:
                return "Browsing"
            if "write" in tool or "file" in tool:
                return "Writing code"
            return "Thinking"
        if low.startswith("using tool:"):
            tool = raw.split(":", 1)[-1].strip().lower()
            if "search" in tool or "research" in tool or "fetch" in tool:
                return "Searching"
            if "browser" in tool:
                return "Browsing"
            if "write" in tool or "file" in tool:
                return "Writing code"
            return "Thinking"
        if "planning" in low or "iteration" in low:
            return "Thinking"
        return raw.split(":", 1)[-1].strip().title() if ":" in raw else raw

    def _on_workflow_step(self, step: str):
        if hasattr(self, "_conv"):
            if step in ("Finished", "", None):
                self._conv.clear_live_activity()
            else:
                self._conv.set_live_activity(self._normalize_workflow_label(step))

    def _on_activity(self, data: dict):
        if not hasattr(self, "_conv"):
            return
        label = data.get("label", "Activity")
        detail = data.get("detail", "")
        self._conv.add_activity(label, detail)
        ws.add_message("activity", label, {"label": label, "detail": detail})

    def _on_preview(self, data: dict):
        if not hasattr(self, "_conv"):
            return
        kind = data.get("kind", "text")
        title = data.get("title", "")
        payload = data.get("payload", "")
        path = data.get("path")
        persist = data.get("persist", True)
        try:
            if persist:
                artifact = ws.add_artifact(kind, title, payload, path)
                if artifact:
                    kind = artifact.get("kind", kind)
                    title = artifact.get("title", title)
                    payload = artifact.get("payload", payload)
                    path = artifact.get("path", path)
            self._conv.add_artifact_card(kind, title, payload, path or "")
            self._refresh_sidebar()
        except Exception:
            pass

    def _current_provider(self) -> str:
        if hasattr(self, "_chat_center"):
            text = self._chat_center.model_combo.currentText().strip()
            low = text.lower()
            if "live voice" in low or "claude" in low or "opus" in low:
                return "auto"
            return text.split(" — ")[0].strip().lower()
        if hasattr(self, "_input_bar"):
            return self._input_bar.get_provider()
        return "auto"

    def _send_from_bar(self, text: str):
        if not text:
            return
        if not self._require_subscription():
            return
        if getattr(self, "_center_view_mode", "chat") == "dashboard":
            self._on_agent_selected("chat")
        if not ws.get_active_chat():
            ws.create_chat(text[:40])
        if not self._on_user_message(text):
            return
        # In General Chat, route image requests to local FLUX generator.
        if self._active_agent == "general" and self._looks_like_image_request(text):
            self._conv.set_live_activity("Generating image")
            self._log.append_log(f"You: {text}")
            threading.Thread(target=self._run_general_image_generation, args=(text,), daemon=True).start()
            return

        self._conv.set_live_activity("Thinking")
        provider = self._current_provider()
        model = ""
        # Specialized sidebar agents run through the local agent runtime:
        # own system prompt + toolset (web search, deep research, files) +
        # persistent per-agent session memory. General chat keeps the
        # live-voice pipeline below (Gemini Live + real tool calls).
        if self._active_agent in ("writer", "researcher", "designer", "automation"):
            self._log.append_log(f"You: {text}")
            threading.Thread(
                target=self._run_sidebar_agent,
                args=(self._active_agent, text, provider, model),
                daemon=True,
            ).start()
            return
        # General Chat MUST go through Live session so camera/browser/OS tools work.
        # mode=auto previously forced a plain Ollama reply with NO tools — that is
        # why "open site" / "turn on camera" got chatbot refusals instead of actions.
        mode = "live"
        payload = f"[JCFG mode={mode} provider={provider} model={model}] {text}"
        self._log.append_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(payload,), daemon=True).start()

    def _run_sidebar_agent(self, agent_key: str, text: str, provider: str, model: str):
        from core.agent_runtime import run_agent

        try:
            answer = run_agent(
                agent_key,
                text,
                preferred_provider=provider or "auto",
                preferred_model=model,
                on_progress=lambda step: self._workflow_sig.emit(step),
            )
            self._chat_ai_sig.emit(answer or "(no response)")
        except Exception as e:
            self._chat_ai_sig.emit(f"Agent error: {e}")

    def _send_plan_mode(self):
        self._send_from_bar("Help me plan a new idea step by step.")

    def _send_from_bar_with_files(self, text: str, files: list):
        """User attached photos via the plus button — answer with Gemini vision."""
        files = [str(f) for f in (files or []) if f]
        if not files:
            self._send_from_bar(text)
            return
        if not self._require_subscription():
            return
        if getattr(self, "_center_view_mode", "chat") == "dashboard":
            self._on_agent_selected("chat")
        if not ws.get_active_chat():
            ws.create_chat(text[:40])
        if not self._on_user_message(text, images=files):
            return
        self._conv.set_live_activity("Looking at the photo")
        names = ", ".join(Path(f).name for f in files)
        self._log.append_log(f"You: {text} [📎 {names}]")
        threading.Thread(
            target=self._run_image_question, args=(text, files), daemon=True
        ).start()

    def _run_image_question(self, text: str, files: list[str]):
        try:
            import io
            import json as _json

            from google.genai import types as gtypes
            from core.gemini_models import generate_content

            try:
                api_key = _json.loads(API_FILE.read_text(encoding="utf-8")).get(
                    "gemini_api_key", ""
                )
            except Exception:
                api_key = ""
            if not api_key:
                self._chat_ai_sig.emit(
                    "I need a Gemini API key to look at photos — add one in Settings."
                )
                return

            parts = []
            for path in files[:4]:
                data, mime = self._load_image_for_vision(path)
                if data:
                    parts.append(gtypes.Part.from_bytes(data=data, mime_type=mime))
            if not parts:
                self._chat_ai_sig.emit("I couldn't read those image files.")
                return

            prompt = (
                "You are AURA. The user attached photo(s) to this chat message. "
                "Answer their question about the image(s) directly and helpfully, "
                "in the user's language. Describe what matters, don't pad.\n\n"
                f"User message: {text}"
            )
            response = generate_content(
                "vision",
                contents=[*parts, prompt],
                api_key=api_key,
                retries_per_model=3,
            )
            answer = (response.text or "").strip()
            self._chat_ai_sig.emit(answer or "I looked at the image but got no answer back.")
        except Exception as e:
            self._chat_ai_sig.emit(f"Photo analysis failed: {e}")

    @staticmethod
    def _load_image_for_vision(path: str) -> tuple[bytes, str]:
        """Read + downscale one image so vision requests stay small."""
        import io

        suffix = Path(path).suffix.lower().lstrip(".") or "png"
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
                "heic": "image/heic", "heif": "image/heif",
                "tif": "image/tiff", "tiff": "image/tiff"}.get(
            suffix, "image/png"
        )
        try:
            raw = Path(path).read_bytes()
        except Exception:
            return b"", mime
        try:
            import PIL.Image

            img = PIL.Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((1600, 1600), PIL.Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            return buf.getvalue(), "image/jpeg"
        except Exception:
            return raw, mime

    @staticmethod
    def _looks_like_image_request(text: str) -> bool:
        low = text.lower()
        markers = (
            "generate image", "create image", "make image", "draw", "illustration",
            "render", "photo of", "image of",
            "сделай картин", "создай картин", "сгенерируй картин", "нарисуй",
            "сделай фото", "фото ",
            "resim", "görsel", "şəkil",
        )
        return any(m in low for m in markers)

    def _run_general_image_generation(self, prompt: str):
        from core.local_image import generate_flux_image

        try:
            png_path = Path(generate_flux_image(prompt, steps=4, guidance=0.0))
            html_path = png_path.with_suffix(".html")
            html_path.write_text(
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<style>html,body{height:100%;margin:0;background:#050a14;display:grid;place-items:center}"
                "img{max-width:96vw;max-height:96vh;border-radius:14px;border:1px solid #1e4a62;"
                "box-shadow:0 0 28px rgba(0,209,255,.25)}</style></head>"
                f"<body><img src='{png_path.name}' alt='Generated image'/></body></html>",
                encoding="utf-8",
            )

            self._preview_sig.emit({
                "kind": "web",
                "title": "Generated image",
                "payload": str(html_path),
                "path": str(html_path),
                "persist": True,
            })
            self._chat_ai_sig.emit(
                f"Generated locally with FLUX.\nSaved to: `{png_path}`"
            )
        except Exception as e:
            self._chat_ai_sig.emit(f"Image generation failed: {e}")
    def _init_hidden_services(self) -> None:
        """Background widgets (log, metrics) — no visible right panel."""
        sink = QWidget(self)
        sink.hide()

        self._log = LogWidget(sink)
        self._log.hide()
        self._live_status = QLabel("ACTIVE", sink)
        self._live_status.hide()

        self._uptime_lbl = QLabel("--:--", sink)
        self._uptime_lbl.hide()
        self._bar_cpu = MetricBar("CPU", C.PRI, sink)
        self._bar_mem = MetricBar("MEM", C.ACC2, sink)
        self._bar_net = MetricBar("NET", C.GREEN, sink)
        self._bar_gpu = MetricBar("GPU", C.ACC, sink)
        self._bar_tmp = MetricBar("TMP", "#ff6688", sink)
        for w in (self._bar_cpu, self._bar_mem, self._bar_net, self._bar_gpu, self._bar_tmp):
            w.hide()

        self._proc_lbl = QLabel("PROC  --", sink)
        self._proc_lbl.hide()
        self._ai_model_lbl = self._ai_cell("Current Model", "gemini-live")
        self._ai_state_lbl = self._ai_cell("AI Status", "Listening")
        self._ai_provider_lbl = self._ai_cell("Provider", "gemini-live")
        self._wake_lbl = self._ai_cell("Wake Word", "AURA")
        self._ai_mem_lbl = self._ai_cell("Memory", "Persistent")
        self._ai_index_lbl = self._ai_cell("Tools", "25 ready")
        self._ai_ctx_lbl = self._ai_mem_lbl
        self._ai_plugins_lbl = self._ai_index_lbl
        for w in (
            self._ai_model_lbl, self._ai_state_lbl, self._ai_provider_lbl,
            self._wake_lbl, self._ai_mem_lbl, self._ai_index_lbl,
        ):
            w.setParent(sink)
            w.hide()

        self._drop_zone = FileDropZone(sink)
        self._drop_zone.hide()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        self._file_hint = QLabel("", sink)
        self._file_hint.hide()

    def _switch_tab(self, key: str):
        return

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        controls = QVBoxLayout()
        controls.setSpacing(5)

        selectors = QHBoxLayout()
        selectors.setSpacing(5)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Live", "Auto Router"])
        self._mode_combo.setFixedHeight(30)
        self._mode_combo.setMinimumWidth(95)
        self._mode_combo.setStyleSheet(f"""
            QComboBox {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 6px;
            }}
            QComboBox QAbstractItemView {{
                background: #001018; color: {C.WHITE}; border: 1px solid {C.BORDER_B};
                selection-background-color: {C.PRI_GHO};
            }}
        """)
        selectors.addWidget(self._mode_combo, stretch=1)

        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["auto", "gemini", "openrouter", "groq", "deepseek", "together", "ollama", "lmstudio"])
        self._provider_combo.setFixedHeight(30)
        self._provider_combo.setMinimumWidth(95)
        self._provider_combo.setStyleSheet(self._mode_combo.styleSheet())
        selectors.addWidget(self._provider_combo, stretch=1)

        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("model(optional)")
        self._model_input.setFont(QFont("Courier New", 8))
        self._model_input.setFixedHeight(30)
        self._model_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        selectors.addWidget(self._model_input, stretch=1)
        controls.addLayout(selectors)

        command = QHBoxLayout()
        command.setSpacing(5)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        command.addWidget(self._input, stretch=1)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        command.addWidget(send)
        controls.addLayout(command)

        row.addLayout(controls)
        return row

    def _ai_cell(self, key: str, value: str) -> QWidget:
        box = QFrame()
        box.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL2}; border: 1px solid {C.BORDER};
                border-radius: 10px;
            }}
        """)
        vl = QVBoxLayout(box)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(4)
        k = QLabel(key)
        k.setFont(QFont("Menlo", 6))
        k.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; letter-spacing: 1px;")
        v = QLabel(value)
        v.setFont(QFont("Menlo", 8, QFont.Weight.Bold))
        v.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        v.setObjectName("value")
        vl.addWidget(k)
        vl.addWidget(v)
        box._value_lbl = v
        box._key_lbl = k
        return box

    def _set_ai_cell(self, box: QWidget, value: str):
        if hasattr(box, "_value_lbl"):
            box._value_lbl.setText(value)

    def _apply_ai_status(self, data: dict):
        model = str(data.get("model", "--"))
        provider = str(data.get("provider", "--"))
        status = str(data.get("status", "Listening"))
        wake = str(data.get("wake", "AURA"))
        self._set_ai_cell(self._ai_model_lbl, model)
        self._set_ai_cell(self._ai_provider_lbl, provider)
        self._set_ai_cell(self._ai_state_lbl, status.replace("listening", "Listening"))
        self._set_ai_cell(self._wake_lbl, wake if wake != "--" else "AURA")

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell AURA what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        # Unmuting starts live voice — require Pro after free preview.
        if self._muted and not self._require_subscription():
            return
        self._muted = not self._muted
        self.hud.muted = self._muted
        if hasattr(self, "_dashboard_hud"):
            self._dashboard_hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if hasattr(self, "_chat_center"):
            self._chat_center.set_muted(self._muted)
        elif hasattr(self, "_input_bar"):
            self._input_bar.set_muted(self._muted)

    def _send(self):
        if hasattr(self, "_input_bar"):
            self._send_from_bar(self._input_bar._input.text().strip())
            self._input_bar._input.clear()

    def _on_user_voice_level(self, level: float) -> None:
        if hasattr(self, "hud"):
            self.hud.set_voice_level(level)
        if hasattr(self, "_dashboard_hud"):
            self._dashboard_hud.set_voice_level(level)
        if hasattr(self, "_chat_center"):
            self._chat_center.set_voice_level(level)
        if hasattr(self, "_float") and self._float_visible():
            self._float.set_voice_level(level)

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        if hasattr(self, "_dashboard_hud"):
            self._dashboard_hud.state = state
            self._dashboard_hud.speaking = (state == "SPEAKING")
        if hasattr(self, "_chat_center"):
            self._chat_center.set_state(state)
            self._chat_center.set_speaking(state == "SPEAKING")
        # Live voice / thinking in the floating overlay without opening main.
        if state in ("LISTENING", "THINKING", "PROCESSING", "SPEAKING"):
            if not self.isVisible() or getattr(self, "_float_session", False):
                self._float_session = True
                self._ensure_float_for_live()
        if hasattr(self, "_float") and self._float_visible():
            self._float.set_status(state)
            if state == "MUTED":
                self._float.set_muted(True)
        status_map = {
            "LISTENING": "Always Ready",
            "THINKING": "Thinking",
            "PROCESSING": "Processing",
            "SPEAKING": "Speaking",
            "MUTED": "Muted",
        }
        if hasattr(self, "_status_top"):
            self._status_top.setText(status_map.get(state, state))
        if state == "THINKING":
            self._workflow_sig.emit("Thinking")
        elif state == "PROCESSING":
            self._workflow_sig.emit("Analyzing Code")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _ensure_setup_overlay(self):
        if self._ready:
            return
        if self._overlay is not None and self._overlay.isVisible():
            return
        self._show_setup()

    def _show_setup(self):
        if self._overlay is not None:
            try:
                self._overlay.close()
            except Exception:
                pass
            self._overlay = None
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 520, 560
        ov.setGeometry(
            max(12, (cw.width()  - ow) // 2),
            max(12, (cw.height() - oh) // 2),
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        ov.raise_()
        ov.activateWindow()
        self._overlay = ov
        # Keep asking until the main window has real size (post-onboarding race).
        if cw.width() < 200 or cw.height() < 200:
            QTimer.singleShot(200, self._ensure_setup_overlay)
    def _on_setup_done(self, key: str, os_name: str):
        try:
            from core.app_paths import api_keys_path

            path = api_keys_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            existing.update({
                "gemini_api_key": key,
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
                "free_limits": existing.get(
                    "free_limits", {"daily": 300, "hourly": 35}
                ),
            })
            path.write_text(json.dumps(existing, indent=4), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Could not save API key",
                f"AURA could not save your Gemini key.\n\n{e}",
            )
            return
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. AURA online.")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._app.setQuitOnLastWindowClosed(False)
        try:
            from jarvis_ui.app_tray import apply_app_icon

            apply_app_icon(self._app)
        except Exception:
            pass
        self._win = MainWindow(face_path)
        self._win.show()
        try:
            from jarvis_ui.user_account import install_update_controller_fix

            install_update_controller_fix()
        except Exception:
            pass
        self._updater = UpdateController(self._win, os.getpid())
        self._win._updater_ref = self._updater
        self.root = _RootShim(self._app)
        # Frozen AURA may reinstall a legacy wake plist; restore clap-filter from disk.
        try:
            from jarvis_ui.wake_bootstrap import ensure_clap_wake_async

            ensure_clap_wake_async(delay_s=2.5)
        except Exception:
            pass

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_user_voice_level(self, level: float):
        self._win._user_voice_sig.emit(level)

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def set_workflow_step(self, step: str):
        self._win._workflow_sig.emit(step)

    def add_user_message(self, text: str):
        self._win._chat_user_sig.emit(text)

    def add_ai_message(self, text: str):
        self._win._chat_ai_sig.emit(text)

    def stream_delta(self, text: str):
        self._win._stream_delta_sig.emit(text)

    def stream_end(self, text: str = ""):
        self._win._stream_end_sig.emit(text)

    def force_mute_for_gate(self):
        self._win._force_mute_for_gate()

    def request_preview_gate(self):
        self._win._preview_gate_sig.emit()

    def add_activity(self, label: str, detail: str = ""):
        self._win._activity_sig.emit({"label": label, "detail": detail})

    def set_ai_status(self, **kwargs):
        self._win._ai_sig.emit(kwargs)

    def show_preview(self, kind: str, title: str, payload: str, path: str | None = None, persist: bool = True):
        self._win._preview_sig.emit({
            "kind": kind, "title": title, "payload": payload, "path": path, "persist": persist,
        })

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")
