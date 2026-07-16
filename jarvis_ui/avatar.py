"""Circular account avatar — Google photo with soft ring fallback to initial."""

from __future__ import annotations

import hashlib
import threading
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from jarvis_ui import theme as T


def _cache_dir() -> Path:
    try:
        from core.app_paths import writable_root

        d = writable_root() / "cache" / "avatars"
    except Exception:
        d = Path.home() / "Library/Application Support/AURA/cache/avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return _cache_dir() / f"{digest}.img"


class _AvatarFetchBridge(QObject):
    ready = pyqtSignal(str, object)  # url, QPixmap | None


_bridge: _AvatarFetchBridge | None = None


def _bridge_instance() -> _AvatarFetchBridge:
    global _bridge
    if _bridge is None:
        _bridge = _AvatarFetchBridge()
    return _bridge


def fetch_avatar_pixmap(url: str, size: int = 96) -> QPixmap | None:
    if not url:
        return None
    path = _cache_path(url)
    data = b""
    if path.exists() and path.stat().st_size > 0:
        data = path.read_bytes()
    else:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AURA-Desktop/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            if data:
                path.write_bytes(data)
        except Exception:
            return None
    if not data:
        return None
    pix = QPixmap()
    if not pix.loadFromData(data):
        return None
    return pix.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )


def load_avatar_async(url: str, size: int = 96) -> None:
    """Fetch on a worker thread; emit via `_bridge_instance().ready`."""

    def _work() -> None:
        pix = fetch_avatar_pixmap(url, size=size)
        _bridge_instance().ready.emit(url, pix)

    threading.Thread(target=_work, daemon=True, name="AvatarFetch").start()


class AvatarCircle(QWidget):
    """Soft-ring circular avatar. Shows Google photo or monogram fallback."""

    def __init__(self, diameter: int = 32, parent=None):
        super().__init__(parent)
        self._d = int(diameter)
        self.setFixedSize(self._d, self._d)
        self._initial = "U"
        self._pix: QPixmap | None = None
        self._url = ""
        self._authenticated = False
        br = _bridge_instance()
        br.ready.connect(self._on_fetched)

    def set_profile(self, *, initial: str = "", url: str = "", authenticated: bool = False) -> None:
        # Guest / Cursor-style: empty circle (no letter). Signed-in: photo or monogram.
        self._authenticated = bool(authenticated)
        if not self._authenticated:
            letter = ""
        else:
            letter = (initial or "U").strip()[:1].upper() or "U"
        self._initial = letter
        url = (url or "").strip() if self._authenticated else ""
        if url != self._url:
            self._url = url
            self._pix = None
            if url:
                # Try cache sync first for instant paint.
                cached = _cache_path(url)
                if cached.exists():
                    pix = fetch_avatar_pixmap(url, size=max(96, self._d * 3))
                    if pix is not None and not pix.isNull():
                        self._pix = pix
                load_avatar_async(url, size=max(96, self._d * 3))
        elif not url:
            self._pix = None
        self.update()

    def _on_fetched(self, url: str, pix: object) -> None:
        if url != self._url:
            return
        if isinstance(pix, QPixmap) and not pix.isNull():
            self._pix = pix
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        d = self._d
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Soft outer glow / ring
        ring = QRectF(0.5, 0.5, d - 1.0, d - 1.0)
        if self._authenticated:
            pen = QPen(QColor(0, 209, 255, 70), 1.6)
        else:
            pen = QPen(QColor(255, 255, 255, 28), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ring)

        inner = QRectF(2.2, 2.2, d - 4.4, d - 4.4)
        path = QPainterPath()
        path.addEllipse(inner)

        if self._pix is not None and not self._pix.isNull():
            p.setClipPath(path)
            # Center-crop
            src = self._pix
            side = min(src.width(), src.height())
            x = (src.width() - side) // 2
            y = (src.height() - side) // 2
            p.drawPixmap(inner.toRect(), src, QRectF(x, y, side, side).toRect())
            p.setClipping(False)
        else:
            # Soft fill — guest stays empty (Cursor-style); signed-in shows monogram.
            p.setPen(Qt.PenStyle.NoPen)
            bg = QColor(T.BG_ELEVATED)
            if self._authenticated:
                bg = QColor(0, 40, 55)
            else:
                bg = QColor(255, 255, 255, 14)
            p.setBrush(bg)
            p.drawEllipse(inner)
            if self._initial:
                p.setPen(QColor(T.SB_ACCENT if self._authenticated else T.SB_TEXT_MUTED))
                font = QFont(T.SB_FONT, max(10, int(d * 0.38)), QFont.Weight.DemiBold)
                p.setFont(font)
                p.drawText(inner, int(Qt.AlignmentFlag.AlignCenter), self._initial)

        # Crisp inner rim
        rim = QPen(
            QColor(0, 209, 255, 120) if self._authenticated else QColor(255, 255, 255, 40),
            1.0,
        )
        p.setPen(rim)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(inner)
