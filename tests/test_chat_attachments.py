"""Chat bar photo attachments: chips, signals, and submit payloads."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.fixture()
def bar(qapp):
    from jarvis_ui.components import CenterInputBar

    return CenterInputBar(["Live Voice (Gemini)"])


def _make_png(tmp_path, name="photo.png"):
    # Minimal 1x1 PNG.
    data = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcffff3f030005fe02fea72d1a680000000049454e44ae426082"
    )
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_add_and_remove_attachment(bar, tmp_path):
    p = _make_png(tmp_path)
    assert bar.add_attachment(str(p)) is True
    assert bar._attachments == [str(p)]
    assert not bar._chips_host.isHidden()
    # Duplicate is rejected.
    assert bar.add_attachment(str(p)) is False
    bar._remove_attachment(str(p))
    assert bar._attachments == []
    assert bar._chips_host.isHidden()


def test_missing_file_rejected(bar, tmp_path):
    assert bar.add_attachment(str(tmp_path / "nope.png")) is False


def test_attachment_limit(bar, tmp_path):
    for i in range(bar._MAX_ATTACHMENTS):
        assert bar.add_attachment(str(_make_png(tmp_path, f"p{i}.png"))) is True
    assert bar.add_attachment(str(_make_png(tmp_path, "extra.png"))) is False


def test_submit_with_files_emits_files_submitted(bar, tmp_path):
    p = _make_png(tmp_path)
    bar.add_attachment(str(p))
    bar._input.setText("what is this?")
    got: list = []
    bar.files_submitted.connect(lambda t, f: got.append((t, f)))
    plain: list = []
    bar.submitted.connect(lambda t: plain.append(t))
    bar._submit()
    assert got == [("what is this?", [str(p)])]
    assert plain == []
    # Attachments cleared after send.
    assert bar._attachments == []
    assert bar._input.text() == ""


def test_submit_files_without_text_uses_default_question(bar, tmp_path):
    p = _make_png(tmp_path)
    bar.add_attachment(str(p))
    got: list = []
    bar.files_submitted.connect(lambda t, f: got.append((t, f)))
    bar._submit()
    assert len(got) == 1
    assert got[0][1] == [str(p)]
    assert got[0][0]  # non-empty default question


def test_plain_text_still_uses_submitted(bar):
    got: list = []
    bar.submitted.connect(lambda t: got.append(t))
    bar._input.setText("hello")
    bar._submit()
    assert got == ["hello"]


def test_image_paths_from_mime_filters_non_images(bar, tmp_path):
    from PyQt6.QtCore import QMimeData, QUrl

    img = _make_png(tmp_path, "drop.png")
    doc = tmp_path / "notes.txt"
    doc.write_text("x", encoding="utf-8")
    missing = tmp_path / "ghost.jpg"

    mime = QMimeData()
    mime.setUrls([
        QUrl.fromLocalFile(str(img)),
        QUrl.fromLocalFile(str(doc)),
        QUrl.fromLocalFile(str(missing)),
        QUrl("https://example.com/photo.png"),
    ])
    assert bar._image_paths_from_mime(mime) == [str(img)]


def test_image_paths_from_mime_accepts_heic(bar, tmp_path):
    from PyQt6.QtCore import QMimeData, QUrl

    p = tmp_path / "iphone.HEIC"
    p.write_bytes(b"fake")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p))])
    assert bar._image_paths_from_mime(mime) == [str(p)]


def test_drop_event_attaches_images(bar, tmp_path):
    from PyQt6.QtCore import QMimeData, QUrl

    img = _make_png(tmp_path, "dropped.png")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(img))])

    class FakeDrop:
        def mimeData(self):
            return mime

        def acceptProposedAction(self):
            self.accepted = True

    ev = FakeDrop()
    bar.dropEvent(ev)
    assert bar._attachments == [str(img)]
    assert getattr(ev, "accepted", False)
