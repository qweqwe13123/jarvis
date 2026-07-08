"""In-app reminder/notification engine.

Single source of truth for firing reminders, timers, alarms, scheduled tasks
and automation announcements. Every announcement is routed through the supplied
``speak_cb`` which MUST be the live JARVIS voice engine — there is no system
TTS / ``say`` / browser-voice fallback anywhere in this module.

The engine polls ``runtime/reminders/reminders.json`` (written by
``actions.reminder``), fires anything that is due, and marks it ``fired`` so it
never fires twice. Pending reminders survive application restarts: on startup
overdue items are caught up (fired once) and future items keep waiting.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable


def _store_path() -> Path:
    base = Path(__file__).resolve().parent.parent
    d = base / "runtime" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d / "reminders.json"


class ReminderEngine:
    # How late a pending reminder may be (seconds) and still be fired on
    # startup catch-up. Anything older is marked "missed" to avoid surprises.
    CATCHUP_WINDOW = 12 * 3600

    def __init__(
        self,
        speak_cb: Callable[[str, str], None],
        log_cb: Callable[[str], None] | None = None,
        poll_interval: float = 2.0,
    ):
        self._speak_cb = speak_cb
        self._log_cb = log_cb
        self._poll = poll_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ----- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ReminderEngine", daemon=True)
        self._thread.start()
        self._log("Reminder engine started.")

    def stop(self) -> None:
        self._stop.set()

    # ----- storage helpers -------------------------------------------------
    def _load(self) -> list[dict]:
        try:
            data = json.loads(_store_path().read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, items: list[dict]) -> None:
        try:
            _store_path().write_text(
                json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            self._log(f"Reminder store write failed: {e}")

    def _mark(self, reminder_id: str, status: str) -> None:
        """Re-read just before writing so concurrent appends are preserved."""
        with self._lock:
            items = self._load()
            for item in items:
                if item.get("id") == reminder_id:
                    item["status"] = status
                    item[status] = datetime.now().isoformat(timespec="seconds")
                    break
            self._save(items)

    # ----- recurrence ------------------------------------------------------
    @staticmethod
    def _next_target(item: dict) -> datetime | None:
        """Next occurrence for a repeating reminder, or None for one-shots.

        ``repeat`` may be "daily", "weekly", or an interval in minutes
        (int/str). The next target is always pushed into the future even if
        several periods were missed while the app was closed.
        """
        repeat = item.get("repeat")
        if not repeat:
            return None
        try:
            target = datetime.fromisoformat(item.get("target", ""))
        except Exception:
            return None
        if repeat == "daily":
            step = timedelta(days=1)
        elif repeat == "weekly":
            step = timedelta(weeks=1)
        else:
            try:
                minutes = int(float(repeat))
                if minutes <= 0:
                    return None
                step = timedelta(minutes=minutes)
            except Exception:
                return None
        now = datetime.now()
        while target <= now:
            target += step
        return target

    def _rearm(self, reminder_id: str, next_target: datetime) -> None:
        with self._lock:
            items = self._load()
            for item in items:
                if item.get("id") == reminder_id:
                    item["target"] = next_target.isoformat(timespec="seconds")
                    item["status"] = "pending"
                    item["last_fired"] = datetime.now().isoformat(timespec="seconds")
                    break
            self._save(items)

    # ----- firing ----------------------------------------------------------
    def _fire(self, item: dict) -> None:
        if item.get("kind") == "quote":
            # Fresh quote each time; falls back to the stored message.
            try:
                from core.daily_quotes import get_quote
                spoken = get_quote(item.get("language") or "en")
            except Exception:
                spoken = item.get("message") or "Stay focused today."
        else:
            spoken = item.get("spoken") or item.get("message") or "Reminder."
        language = item.get("language") or "en"
        try:
            self._speak_cb(spoken, language)
            next_target = self._next_target(item)
            if next_target is not None:
                self._rearm(item.get("id", ""), next_target)
                self._log(f"Recurring reminder re-armed for {next_target.isoformat(timespec='minutes')}")
            else:
                self._mark(item.get("id", ""), "fired")
            self._log(f"Reminder fired [{language}]: {item.get('message', '')[:50]}")
        except Exception as e:
            # Do NOT fall back to another voice — leave pending and retry.
            self._log(f"Reminder speak failed (will retry): {e}")

    def _due_items(self) -> list[dict]:
        now = datetime.now()
        due: list[dict] = []
        for item in self._load():
            if item.get("status") != "pending":
                continue
            try:
                target = datetime.fromisoformat(item.get("target", ""))
            except Exception:
                continue
            if target <= now:
                due.append(item)
        return due

    def _run(self) -> None:
        # Startup catch-up: mark very old pending reminders as missed so they
        # don't all blurt out at once after a long downtime.
        now = datetime.now()
        for item in self._load():
            if item.get("status") != "pending":
                continue
            try:
                target = datetime.fromisoformat(item.get("target", ""))
            except Exception:
                continue
            if (now - target).total_seconds() > self.CATCHUP_WINDOW:
                # Repeating reminders silently roll forward to the next
                # occurrence; one-shots this stale are marked missed.
                next_target = self._next_target(item)
                if next_target is not None:
                    self._rearm(item.get("id", ""), next_target)
                else:
                    self._mark(item.get("id", ""), "missed")

        while not self._stop.is_set():
            try:
                for item in self._due_items():
                    self._fire(item)
            except Exception as e:
                self._log(f"Reminder engine loop error: {e}")
            self._stop.wait(self._poll)

    def _log(self, msg: str) -> None:
        print(f"[ReminderEngine] {msg}")
        if self._log_cb:
            try:
                self._log_cb(f"SYS: {msg}")
            except Exception:
                pass
