"""Antigravity-matched welcome: mid-upper stack, soft chrome, AURA mark."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QTimer,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jarvis_ui.onboarding import tokens as T


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class _RevealTitle(QWidget):
    """Premium letter reveal — soft rise + fade, writes the title in."""

    def __init__(
        self,
        text: str,
        font: QFont,
        color: QColor | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._text = text
        self._font = QFont(font)
        self._color = QColor(color or QColor("#EDEDED"))
        self._progress = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

        fm = QFontMetrics(self._font)
        # Extra room for the rise offset during reveal.
        self.setFixedSize(fm.horizontalAdvance(text) + 8, fm.height() + 14)

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, v: float) -> None:
        self._progress = max(0.0, min(1.0, float(v)))
        self.update()

    progress = pyqtProperty(float, get_progress, set_progress)

    def paintEvent(self, _e) -> None:  # noqa: N802
        if self._progress <= 0.001:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self._font)

        fm = QFontMetrics(self._font)
        text = self._text
        n = max(1, len(text))
        # Letters cascade: early ones finish while later ones still enter.
        cascade = 0.62
        per = max(0.18, 1.0 - cascade)

        x = (self.width() - fm.horizontalAdvance(text)) / 2.0
        baseline = (self.height() + fm.ascent() - fm.descent()) / 2.0

        for i, ch in enumerate(text):
            start = (i / n) * cascade
            local = _smooth((self._progress - start) / per)
            if local <= 0.001:
                x += fm.horizontalAdvance(ch)
                continue

            # Soft write-in: fade + slight rise, tiny blur via lower early alpha.
            p.save()
            p.setOpacity(local)
            y = baseline + (1.0 - local) * 10.0
            col = QColor(self._color)
            col.setAlpha(int(255 * (0.55 + 0.45 * local)))
            p.setPen(col)
            p.drawText(int(round(x)), int(round(y)), ch)
            p.restore()
            x += fm.horizontalAdvance(ch)

        p.end()


class _GlowLogo(QWidget):
    """Compact mark + soft bloom — Antigravity scale, AURA icon."""

    def __init__(self, size: int = 72, parent=None):
        super().__init__(parent)
        self._size = size
        # Room for soft bloom around the mark (logo size unchanged).
        pad = 56
        self.setFixedSize(size + pad, size + pad)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        self._reveal = 0.0
        self._glow = 0.0
        self._rise = 0.0
        self._pix: QPixmap | None = None

        names = (
            "aura_logo_onboarding.png",
            "aura_logo.png",
            "aura_logo_square_bg.png",
        )
        roots: list[Path] = []
        here = Path(__file__).resolve()
        # Dev: repo root (…/jarvis_ui/onboarding → parents[2])
        roots.append(here.parents[2])
        # Frozen: MEIPASS / Contents/{Resources,Frameworks}
        meipass = getattr(__import__("sys"), "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
        try:
            contents = Path(__import__("sys").executable).resolve().parent.parent
            roots.extend([contents / "Resources", contents / "Frameworks"])
        except Exception:
            pass
        # Deduplicate while preserving order
        seen: set[str] = set()
        candidates: list[Path] = []
        for root in roots:
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            for name in names:
                candidates.append(root / "assets" / name)

        for candidate in candidates:
            if not candidate.is_file():
                continue
            img = QPixmap(str(candidate))
            if img.isNull():
                continue
            self._pix = img.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            break

    def get_reveal(self) -> float:
        return self._reveal

    def set_reveal(self, v: float) -> None:
        self._reveal = float(v)
        self.update()

    reveal = pyqtProperty(float, get_reveal, set_reveal)

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, v: float) -> None:
        self._glow = float(v)
        self.update()

    glow = pyqtProperty(float, get_glow, set_glow)

    def get_rise(self) -> float:
        return self._rise

    def set_rise(self, v: float) -> None:
        self._rise = float(v)
        self.update()

    rise = pyqtProperty(float, get_rise, set_rise)

    def paintEvent(self, _e) -> None:  # noqa: N802
        t = max(0.0, self._reveal)
        if t <= 0.001:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        cx = self.width() / 2
        cy = self.height() / 2 + (1.0 - _smooth(self._rise)) * 14.0
        opacity = _smooth(min(1.0, t * 1.2))
        scale = 0.78 + 0.22 * t
        g_amt = max(0.0, self._glow)

        # Soft colored atmosphere — Antigravity-like, not a loud flare.
        outer_r = self._size * (0.70 + 0.22 * g_amt)
        outer = QRadialGradient(cx, cy, outer_r)
        oa = int(18 + 30 * g_amt)
        outer.setColorAt(0.0, QColor(0, 183, 224, oa))
        outer.setColorAt(0.45, QColor(255, 150, 90, int(oa * 0.35)))
        outer.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(outer)
        p.drawEllipse(QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2))

        p.save()
        p.translate(cx, cy)
        p.scale(scale, scale)
        p.translate(-cx, -cy)
        p.setOpacity(opacity)

        if self._pix is not None:
            x = int(cx - self._pix.width() / 2)
            y = int(cy - self._pix.height() / 2)
            p.drawPixmap(x, y, self._pix)
        else:
            p.setPen(QColor(T.CYAN))
            f = T.display(34, QFont.Weight.Bold)
            p.setFont(f)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "A")
        p.restore()
        p.end()


def _asset_candidates(*names: str) -> list[Path]:
    """Resolve brand assets across repo, frozen Resources, and Frameworks."""
    roots: list[Path] = []
    try:
        from jarvis_ui.paths import resource_dir

        roots.append(Path(resource_dir()))
    except Exception:
        pass
    here = Path(__file__).resolve()
    # …/jarvis_ui/onboarding/this.py → repo root or Frameworks/
    roots.append(here.parents[2])
    # …/Contents/Resources when loaded from Frameworks/jarvis_ui
    try:
        contents = here.parents[3]
        roots.append(contents / "Resources")
        roots.append(contents / "Frameworks")
    except Exception:
        pass
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        for name in names:
            path = root / "assets" / name
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return out


class _GoogleG(QWidget):
    """Official multicolor Google G (SVG / PNG), matching Sign-in chrome."""

    def __init__(self, size: int = 18, parent=None):
        super().__init__(parent)
        self._s = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pix: QPixmap | None = None
        self._svg = None

        for png in _asset_candidates(
            "google_g.png",
            "google_g_72.png",
            "google_g_54.png",
            "google_g_36.png",
        ):
            if not png.is_file():
                continue
            pm = QPixmap(str(png))
            if not pm.isNull():
                self._pix = pm.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                break

        if self._pix is None:
            for svg in _asset_candidates("google_g.svg"):
                if not svg.is_file():
                    continue
                try:
                    from PyQt6.QtCore import QByteArray
                    from PyQt6.QtSvg import QSvgRenderer

                    self._svg = QSvgRenderer(QByteArray(svg.read_bytes()))
                    if not self._svg.isValid():
                        self._svg = None
                    else:
                        break
                except Exception:
                    self._svg = None

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = float(self._s)

        if self._pix is not None:
            p.drawPixmap(0, 0, self._pix)
            p.end()
            return

        if self._svg is not None:
            self._svg.render(p, QRectF(0, 0, s, s))
            p.end()
            return

        # Fallback drawn G if assets missing
        pen_w = max(2.2, s * 0.17)
        rect = QRectF(pen_w / 2, pen_w / 2, s - pen_w, s - pen_w)
        segments = (
            (QColor("#4285F4"), -45, 135),
            (QColor("#34A853"), 90, 90),
            (QColor("#FBBC05"), 180, 90),
            (QColor("#EA4335"), 270, 90),
        )
        for color, start, span in segments:
            pen = QPen(color, pen_w)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, int(start * 16), int(span * 16))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#4285F4"))
        p.drawRect(QRectF(s * 0.50, s * 0.42, s * 0.38, pen_w * 0.95))
        p.end()


class GoogleSignInButton(QPushButton):
    """Antigravity Continue with Google — flat dark chip, ~8px radius."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setFixedWidth(308)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setText("")
        self.setStyleSheet(
            """
            QPushButton {
                background: #2B2B2B;
                border: none;
                border-radius: 8px;
                padding: 0;
            }
            QPushButton:hover {
                background: #333333;
            }
            QPushButton:pressed {
                background: #242424;
            }
            """
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 0, 22, 0)
        row.setSpacing(14)
        g = _GoogleG(20)
        row.addWidget(g, 0, Qt.AlignmentFlag.AlignVCenter)
        lab = QLabel("Continue with Google")
        lab.setFont(T.sans(14, QFont.Weight.Medium))
        lab.setStyleSheet(
            "color: #F5F5F5; background: transparent; border: none;"
        )
        lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)


class AntigravityWelcomePage(QWidget):
    """Mid-upper centered stack matching Antigravity spacing rhythm."""

    continue_clicked = pyqtSignal()
    google_sign_in_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AntiWelcome")
        self.setStyleSheet("QWidget#AntiWelcome { background: #0B0B0B; }")

        root = QVBoxLayout(self)
        # Generous side margins; vertical air comes from stretches.
        root.setContentsMargins(48, 0, 48, 0)
        root.setSpacing(0)
        # Vertically centered stack.
        root.addStretch(1)

        stage = QVBoxLayout()
        stage.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        stage.setSpacing(0)

        # Lift logo+title only; compensate below so CTA + link stay put.
        _brand_lift = 28
        stage.addSpacing(-_brand_lift)

        self._logo = _GlowLogo(72)
        stage.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignHCenter)

        # Pull title up into the logo widget’s empty lower pad — text closer to
        # the mark, without shrinking/moving the logo itself.
        stage.addSpacing(-12)

        title_font = T.sans(24, QFont.Weight.Medium)
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 120)
        self._title = _RevealTitle("Welcome to AURA", title_font, QColor("#EDEDED"))
        stage.addWidget(self._title, 0, Qt.AlignmentFlag.AlignHCenter)

        # Gap title → CTA includes the brand lift so button/link don't move.
        stage.addSpacing(36 + _brand_lift)

        # CTA + link nudged slightly right, independent of logo/title.
        cta_row = QHBoxLayout()
        cta_row.setSpacing(0)
        cta_row.addStretch(1)
        cta_row.addSpacing(18)
        cta_col = QVBoxLayout()
        cta_col.setSpacing(0)
        cta_col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._btn = GoogleSignInButton()
        self._btn.clicked.connect(self._on_google)
        cta_col.addWidget(self._btn, 0, Qt.AlignmentFlag.AlignHCenter)

        cta_col.addSpacing(20)

        # Cool muted link — Antigravity uses gray-blue underline, not warm gray.
        self._link = QLabel(
            '<a href="#local" style="color:#9AA3AD; text-decoration: underline;">'
            "Use AI locally without sharing data with third parties</a>"
        )
        self._link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._link.setTextFormat(Qt.TextFormat.RichText)
        self._link.setOpenExternalLinks(False)
        self._link.linkActivated.connect(self._on_local)
        link_font = T.sans(13, QFont.Weight.Normal)
        self._link.setFont(link_font)
        self._link.setStyleSheet("background: transparent; border: none;")
        self._link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link.setWordWrap(True)
        self._link.setMaximumWidth(380)
        cta_col.addWidget(self._link)

        cta_row.addLayout(cta_col)
        cta_row.addStretch(1)
        stage.addLayout(cta_row)

        root.addLayout(stage)
        root.addStretch(1)

        self._btn_fx = QGraphicsOpacityEffect(self._btn)
        self._link_fx = QGraphicsOpacityEffect(self._link)
        self._btn.setGraphicsEffect(self._btn_fx)
        self._link.setGraphicsEffect(self._link_fx)
        self._btn_fx.setOpacity(0.0)
        self._link_fx.setOpacity(0.0)
        self._title.set_progress(0.0)
        self._logo.set_reveal(0.0)
        self._logo.set_glow(0.0)
        self._logo.set_rise(0.0)

        self._anims: list = []
        self._breathe: QPropertyAnimation | None = None
        QTimer.singleShot(80, self._play_intro)

    def _on_local(self, _url: str = "") -> None:
        try:
            from jarvis_ui.user_account import continue_local

            continue_local()
        except Exception:
            pass
        self.continue_clicked.emit()

    def _on_google(self) -> None:
        # Non-blocking cloud sign-in — keep welcome animations smooth.
        # Repeated taps cancel a stuck attempt and open a fresh browser session.
        try:
            from jarvis_ui.auth_async import start_sign_in_worker
        except Exception as e:
            try:
                from PyQt6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "Sign-in failed", str(e))
            except Exception:
                pass
            return

        self._btn.setEnabled(False)
        self._btn.setCursor(Qt.CursorShape.BusyCursor)
        worker = start_sign_in_worker(self, timeout=180.0, replace_running=True)
        if worker is None:
            self._btn.setEnabled(True)
            self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
            return

        def _ok() -> None:
            self._btn.setEnabled(True)
            self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if getattr(self, "_sign_in_worker", None) is worker:
                self._sign_in_worker = None
            self.google_sign_in_clicked.emit()
            self.continue_clicked.emit()

        def _err(msg: str) -> None:
            self._btn.setEnabled(True)
            self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if getattr(self, "_sign_in_worker", None) is worker:
                self._sign_in_worker = None
            if "cancelled" in (msg or "").lower():
                # User (or a newer tap) cancelled — allow immediate retry.
                return
            try:
                from PyQt6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,
                    "Sign-in failed",
                    f"Could not complete Google / AURA sign-in.\n\n{msg}",
                )
            except Exception:
                pass

        worker.succeeded.connect(_ok)
        worker.failed.connect(_err)
        worker.start()

    def _anim(
        self,
        target,
        prop: bytes,
        start,
        end,
        ms: int,
        curve=QEasingCurve.Type.OutCubic,
    ):
        a = QPropertyAnimation(target, prop, self)
        a.setDuration(ms)
        a.setStartValue(start)
        a.setEndValue(end)
        a.setEasingCurve(curve)
        self._anims.append(a)
        return a

    def _start_breathe(self) -> None:
        breathe = QPropertyAnimation(self._logo, b"glow", self)
        breathe.setDuration(3600)
        breathe.setEasingCurve(QEasingCurve.Type.InOutSine)
        breathe.setLoopCount(-1)
        breathe.setKeyValueAt(0.0, 0.40)
        breathe.setKeyValueAt(0.5, 0.68)
        breathe.setKeyValueAt(1.0, 0.40)
        self._breathe = breathe
        self._anims.append(breathe)
        breathe.start()

    def _play_intro(self) -> None:
        # Calmer entrance — closer to Antigravity’s restrained motion.
        reveal = self._anim(self._logo, b"reveal", 0.0, 1.0, 980, QEasingCurve.Type.OutCubic)
        rise = self._anim(self._logo, b"rise", 0.0, 1.0, 980, QEasingCurve.Type.OutCubic)

        glow_up = self._anim(self._logo, b"glow", 0.0, 0.85, 480, QEasingCurve.Type.OutQuad)
        glow_settle = self._anim(
            self._logo, b"glow", 0.85, 0.45, 640, QEasingCurve.Type.InOutSine
        )
        glow_seq = QSequentialAnimationGroup(self)
        glow_seq.addAnimation(glow_up)
        glow_seq.addAnimation(glow_settle)

        logo_in = QParallelAnimationGroup(self)
        logo_in.addAnimation(reveal)
        logo_in.addAnimation(rise)
        logo_in.addAnimation(glow_seq)

        # Premium letter write-in after the mark settles.
        title_in = self._anim(
            self._title, b"progress", 0.0, 1.0, 980, QEasingCurve.Type.OutCubic
        )

        btn_in = self._anim(self._btn_fx, b"opacity", 0.0, 1.0, 420)
        link_in = self._anim(self._link_fx, b"opacity", 0.0, 1.0, 380)
        cta_in = QParallelAnimationGroup(self)
        cta_in.addAnimation(btn_in)
        cta_in.addAnimation(link_in)

        seq = QSequentialAnimationGroup(self)
        seq.addAnimation(logo_in)
        seq.addPause(140)
        seq.addAnimation(title_in)
        seq.addPause(80)
        seq.addAnimation(cta_in)
        seq.finished.connect(self._start_breathe)
        self._seq = seq
        seq.start()
