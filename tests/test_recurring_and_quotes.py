"""Tests for recurring reminders and the local daily-quote service."""
import json
import time
from datetime import datetime, timedelta

import pytest

import core.reminder_engine as re_mod
from core.daily_quotes import (
    QUOTE_REMINDER_ID, QUOTES, configure_daily_quote, get_quote, next_occurrence,
)
from core.reminder_engine import ReminderEngine


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "reminders.json"
    monkeypatch.setattr(re_mod, "_store_path", lambda: path)
    return path


def _run_engine(store, spoken, duration=0.35, fail=False):
    def speak(text, lang):
        if fail:
            raise RuntimeError("offline")
        spoken.append((text, lang))

    eng = ReminderEngine(speak_cb=speak, poll_interval=0.05)
    eng.start()
    time.sleep(duration)
    eng.stop()


# ----- recurrence ----------------------------------------------------------
def test_daily_reminder_rearms_after_fire(store):
    past = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    store.write_text(json.dumps([{
        "id": "d1", "status": "pending", "target": past,
        "message": "morning routine", "language": "en", "repeat": "daily",
    }]))
    spoken = []
    _run_engine(store, spoken)

    assert len(spoken) == 1  # fired once, not spammed
    saved = json.loads(store.read_text())[0]
    assert saved["status"] == "pending"  # still active
    assert datetime.fromisoformat(saved["target"]) > datetime.now()


def test_interval_repeat_minutes(store):
    past = (datetime.now() - timedelta(seconds=30)).isoformat(timespec="seconds")
    store.write_text(json.dumps([{
        "id": "i1", "status": "pending", "target": past,
        "message": "drink water", "language": "en", "repeat": "45",
    }]))
    spoken = []
    _run_engine(store, spoken)

    saved = json.loads(store.read_text())[0]
    next_target = datetime.fromisoformat(saved["target"])
    assert timedelta(0) < next_target - datetime.now() <= timedelta(minutes=45)


def test_stale_recurring_rolls_forward_instead_of_missed(store):
    stale = datetime.now() - timedelta(seconds=ReminderEngine.CATCHUP_WINDOW + 3600)
    store.write_text(json.dumps([{
        "id": "d2", "status": "pending", "target": stale.isoformat(timespec="seconds"),
        "message": "weekly report", "language": "en", "repeat": "weekly",
    }]))
    spoken = []
    _run_engine(store, spoken)

    saved = json.loads(store.read_text())[0]
    assert saved["status"] == "pending"
    assert datetime.fromisoformat(saved["target"]) > datetime.now()
    assert spoken == []  # rolled forward silently, no blurt


def test_one_shot_still_fires_once(store):
    past = (datetime.now() - timedelta(seconds=5)).isoformat(timespec="seconds")
    store.write_text(json.dumps([{
        "id": "o1", "status": "pending", "target": past,
        "message": "one shot", "language": "en",
    }]))
    spoken = []
    _run_engine(store, spoken)
    assert len(spoken) == 1
    assert json.loads(store.read_text())[0]["status"] == "fired"


def test_bad_repeat_value_treated_as_one_shot(store):
    past = (datetime.now() - timedelta(seconds=5)).isoformat(timespec="seconds")
    store.write_text(json.dumps([{
        "id": "b1", "status": "pending", "target": past,
        "message": "weird", "language": "en", "repeat": "sometimes",
    }]))
    spoken = []
    _run_engine(store, spoken)
    assert json.loads(store.read_text())[0]["status"] == "fired"


# ----- daily quotes --------------------------------------------------------
def test_get_quote_languages():
    assert get_quote("en") in QUOTES["en"]
    assert get_quote("ru") in QUOTES["ru"]
    assert get_quote("xx") in QUOTES["en"]  # unknown → english


def test_next_occurrence_future():
    now = datetime(2026, 7, 8, 10, 0)
    assert next_occurrence(9, 0, now) == datetime(2026, 7, 9, 9, 0)
    assert next_occurrence(11, 30, now) == datetime(2026, 7, 8, 11, 30)


def test_configure_daily_quote_enable_disable(tmp_path):
    path = tmp_path / "reminders.json"
    msg = configure_daily_quote(True, "08:30", "ru", store_path=path)
    assert "enabled" in msg
    items = json.loads(path.read_text())
    quote = next(i for i in items if i["id"] == QUOTE_REMINDER_ID)
    assert quote["repeat"] == "daily" and quote["kind"] == "quote"
    assert quote["language"] == "ru"

    configure_daily_quote(False, store_path=path)
    items = json.loads(path.read_text())
    assert all(i["id"] != QUOTE_REMINDER_ID for i in items)


def test_configure_daily_quote_invalid_time(tmp_path):
    path = tmp_path / "reminders.json"
    msg = configure_daily_quote(True, "25:99", store_path=path)
    assert "Invalid" in msg


def test_quote_reminder_speaks_fresh_quote(store):
    past = (datetime.now() - timedelta(seconds=5)).isoformat(timespec="seconds")
    store.write_text(json.dumps([{
        "id": QUOTE_REMINDER_ID, "kind": "quote", "status": "pending",
        "target": past, "message": "Daily motivational quote",
        "language": "en", "repeat": "daily",
    }]))
    spoken = []
    _run_engine(store, spoken)
    assert len(spoken) == 1
    assert spoken[0][0] in QUOTES["en"]
    # And it re-armed for tomorrow.
    saved = json.loads(store.read_text())[0]
    assert saved["status"] == "pending"
