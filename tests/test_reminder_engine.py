"""Unit tests for core.reminder_engine.ReminderEngine.

Uses a temp store path so the real runtime/reminders/reminders.json is never
touched. Covers: due firing, no double-fire, startup catch-up window,
speak-failure retry semantics.
"""
import json
import time
from datetime import datetime, timedelta

import pytest

import core.reminder_engine as re_mod
from core.reminder_engine import ReminderEngine


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "reminders.json"
    monkeypatch.setattr(re_mod, "_store_path", lambda: path)
    return path


def _write(store, items):
    store.write_text(json.dumps(items), encoding="utf-8")


def _make_engine(spoken, fail=False, poll=0.05):
    def speak(text, lang):
        if fail:
            raise RuntimeError("voice offline")
        spoken.append((text, lang))

    return ReminderEngine(speak_cb=speak, poll_interval=poll)


def test_due_reminder_fires_once(store):
    past = (datetime.now() - timedelta(seconds=5)).isoformat(timespec="seconds")
    _write(store, [{"id": "r1", "status": "pending", "target": past,
                    "message": "study English", "language": "en"}])
    spoken = []
    eng = _make_engine(spoken)
    eng.start()
    time.sleep(0.4)
    eng.stop()

    assert spoken and spoken[0][0] == "study English"
    saved = json.loads(store.read_text())
    assert saved[0]["status"] == "fired"
    # Exactly one fire even after several poll cycles.
    assert len(spoken) == 1


def test_future_reminder_not_fired(store):
    future = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
    _write(store, [{"id": "r2", "status": "pending", "target": future,
                    "message": "later", "language": "en"}])
    spoken = []
    eng = _make_engine(spoken)
    eng.start()
    time.sleep(0.25)
    eng.stop()

    assert spoken == []
    assert json.loads(store.read_text())[0]["status"] == "pending"


def test_stale_reminder_marked_missed_on_startup(store):
    stale = (datetime.now() - timedelta(seconds=ReminderEngine.CATCHUP_WINDOW + 60))
    _write(store, [{"id": "r3", "status": "pending",
                    "target": stale.isoformat(timespec="seconds"),
                    "message": "old", "language": "en"}])
    spoken = []
    eng = _make_engine(spoken)
    eng.start()
    time.sleep(0.25)
    eng.stop()

    assert spoken == []
    assert json.loads(store.read_text())[0]["status"] == "missed"


def test_recent_overdue_fires_on_catchup(store):
    overdue = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    _write(store, [{"id": "r4", "status": "pending", "target": overdue,
                    "message": "catch me up", "language": "ru"}])
    spoken = []
    eng = _make_engine(spoken)
    eng.start()
    time.sleep(0.3)
    eng.stop()

    assert spoken == [("catch me up", "ru")]


def test_speak_failure_keeps_reminder_pending(store):
    past = (datetime.now() - timedelta(seconds=5)).isoformat(timespec="seconds")
    _write(store, [{"id": "r5", "status": "pending", "target": past,
                    "message": "retry me", "language": "en"}])
    eng = _make_engine([], fail=True)
    eng.start()
    time.sleep(0.25)
    eng.stop()

    # Voice failed → must stay pending so it retries when voice is back.
    assert json.loads(store.read_text())[0]["status"] == "pending"


def test_fired_and_missed_items_ignored(store):
    past = (datetime.now() - timedelta(seconds=5)).isoformat(timespec="seconds")
    _write(store, [
        {"id": "a", "status": "fired", "target": past, "message": "done"},
        {"id": "b", "status": "missed", "target": past, "message": "gone"},
    ])
    spoken = []
    eng = _make_engine(spoken)
    eng.start()
    time.sleep(0.2)
    eng.stop()
    assert spoken == []
