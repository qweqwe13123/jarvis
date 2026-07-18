"""Focus Guard one-shot: nudge once, then auto-disable."""

from __future__ import annotations

from core import focus_guard as fg


def test_start_guard_defaults_to_one_shot(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "_state_path", lambda: tmp_path / "focus_guard.json")
    state = fg.start_guard(goal="продолжить проект", idle_minutes=1)
    assert state["enabled"] is True
    assert state["one_shot"] is True
    assert state["goal"] == "продолжить проект"


def test_one_shot_nudge_disables_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "_state_path", lambda: tmp_path / "focus_guard.json")
    spoken: list[str] = []

    clock = {"t": 1000.0}

    def fake_clock() -> float:
        return clock["t"]

    def probe() -> tuple[str, str]:
        return "YouTube", "Funny video"

    engine = fg.FocusGuardEngine(
        speak_cb=lambda text, lang: spoken.append(text),
        poll_interval=5.0,
        probe_fn=probe,
        clock=fake_clock,
    )
    fg.start_guard(goal="вернуться к проекту", idle_minutes=1.0, one_shot=True)

    # First tick starts distraction timer.
    engine.tick()
    state = fg.load_state()
    assert state["enabled"] is True
    assert state["distracted_since"]

    # Advance past threshold and nudge.
    clock["t"] += 70.0
    engine.tick()
    assert spoken, "expected a voice nudge"
    state = fg.load_state()
    assert state["enabled"] is False
    assert state["nudge_count"] == 1
    assert state["distracted_since"] is None


def test_repeat_mode_stays_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "_state_path", lambda: tmp_path / "focus_guard.json")
    spoken: list[str] = []
    clock = {"t": 1000.0}

    engine = fg.FocusGuardEngine(
        speak_cb=lambda text, lang: spoken.append(text),
        poll_interval=5.0,
        probe_fn=lambda: ("Netflix", "Movie"),
        clock=lambda: clock["t"],
    )
    fg.start_guard(goal="работа", idle_minutes=1.0, one_shot=False)
    engine.tick()
    clock["t"] += 70.0
    engine.tick()
    assert spoken
    state = fg.load_state()
    assert state["enabled"] is True
    assert state["nudge_count"] == 1


def test_stop_guard_clears_watch(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "_state_path", lambda: tmp_path / "focus_guard.json")
    fg.start_guard(goal="проект", idle_minutes=2)
    fg.stop_guard()
    state = fg.load_state()
    assert state["enabled"] is False
