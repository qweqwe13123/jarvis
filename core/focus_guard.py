"""Focus Guard — distraction watchdog that voice-nudges when you drift off work.

Design:
- Cheap poll of the frontmost app + window title (no vision every tick).
- Classify as work / distraction / neutral.
- If distraction lasts >= idle_minutes, speak a friendly nudge via the live voice.
- Persist session in runtime/focus_guard.json so restarts keep the watch armed.

This is NOT OS Do Not Disturb (see actions/autonomous_mode). Focus Guard
actively watches and interrupts you when you asked it to.
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

ProgressLog = Callable[[str], None]
SpeakCb = Callable[[str, str], None]


def _base_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _state_path() -> Path:
    d = _base_dir() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d / "focus_guard.json"


# —— Classification tables ————————————————————————————————————————————————

# Process / app names that almost always mean entertainment.
DISTRACTION_APPS = frozenset(
    {
        "netflix",
        "disney+",
        "disney plus",
        "prime video",
        "hulu",
        "twitch",
        "plex",
        "iina",
        "vlc",
        "quicktime player",
        "tv",
        "apple tv",
        "steam",
        "steam helper",
        "epic games launcher",
        "geforce now",
    }
)

# Browsers: only distraction when the window title matches keywords below.
BROWSER_APPS = frozenset(
    {
        "safari",
        "google chrome",
        "chrome",
        "chromium",
        "firefox",
        "arc",
        "brave browser",
        "brave",
        "microsoft edge",
        "opera",
        "opera gx",
        "vivaldi",
        "orion",
        "dia",
        "yandex",
        "yandex browser",
        "яндекс",
        "яндекс браузер",
    }
)

_BROWSER_NAME_HINTS = (
    "chrome", "firefox", "safari", "edge", "brave", "opera", "arc",
    "yandex", "яндекс", "vivaldi", "orion", "chromium",
)

DISTRACTION_TITLE_RE = re.compile(
    r"("
    r"youtube|youtu\.be|netflix|twitch|disney\+|disney\s*plus|hulu|prime\s*video|"
    r"kinopoisk|кинопоиск|ivi\.ru|\bivi\b|okko|wink|premier|rutube|tiktok|"
    r"instagram|reels|shorts|reddit|vk\s*video|facebook|twitter|x\.com|"
    r"pornhub|xvideos|twitch\.tv"
    r")",
    re.IGNORECASE,
)

# Frontmost apps that mean "I'm working" — reset distraction timer.
WORK_APPS = frozenset(
    {
        "cursor",
        "code",
        "visual studio code",
        "visual studio",
        "xcode",
        "pycharm",
        "intellij idea",
        "webstorm",
        "goland",
        "clion",
        "android studio",
        "sublime text",
        "nova",
        "bbedit",
        "terminal",
        "iterm2",
        "iterm",
        "warp",
        "kitty",
        "alacritty",
        "ghostty",
        "figma",
        "sketch",
        "notion",
        "obsidian",
        "linear",
        "slack",  # borderline — treat as work/collab, not movie
        "zoom",
        "microsoft teams",
        "teams",
        "pages",
        "numbers",
        "keynote",
        "microsoft word",
        "microsoft excel",
        "microsoft powerpoint",
        "preview",  # reading docs
        "textedit",
    }
)

# Ignore these so JARVIS watching itself doesn't mess with the timer.
IGNORE_APPS = frozenset(
    {
        "python",
        "python3",
        "jarvis",
        "mark xxxix",
        "electron",  # too vague — only ignore if title suggests jarvis
    }
)


def _is_browser_app(app_l: str) -> bool:
    if app_l in BROWSER_APPS:
        return True
    return any(h in app_l for h in _BROWSER_NAME_HINTS)


def classify_frontmost(app: str, title: str) -> str:
    """Return 'work' | 'distraction' | 'neutral' | 'ignore'.

    Once Focus Guard is on, anything that is not an explicit work app counts as
    distraction — YouTube, Yandex, Finder, games, chat… wherever the user is.
    Only IDE/terminal-class apps reset the timer.
    """
    app_l = (app or "").strip().lower()
    title_l = (title or "").strip().lower()

    if app_l in IGNORE_APPS or app_l in ("jarvis", "mark xxxix"):
        return "ignore"
    if title_l in ("jarvis", "mark xxxix") or title_l.startswith("jarvis —"):
        return "ignore"

    if app_l in WORK_APPS:
        return "work"

    # Browser on GitHub/docs still counts as work-ish so coding in the browser
    # doesn't false-trigger — everything else is distraction.
    if _is_browser_app(app_l) and re.search(
        r"(github|gitlab|stackoverflow|localhost|docs\.|notion\.|linear\.app|figma\.com|cursor\.)",
        title_l,
        re.IGNORECASE,
    ):
        return "work"

    return "distraction"


def get_frontmost_app() -> tuple[str, str]:
    """Return (app_name, window_title_or_url). Empty strings on failure."""
    system = platform.system()
    if system == "Darwin":
        return _frontmost_macos()
    if system == "Windows":
        return _frontmost_windows()
    if system == "Linux":
        return _frontmost_linux()
    return "", ""


def _browser_active_url_macos(app_name: str) -> str:
    """Best-effort active tab URL for common macOS browsers (incl. Yandex)."""
    app = (app_name or "").strip()
    if not app:
        return ""
    app_l = app.lower()
    scripts: list[str] = []
    if "safari" in app_l:
        scripts.append('tell application "Safari" to return (URL of front document) as text')
    elif "chrome" in app_l:
        scripts.append(
            'tell application "Google Chrome" to return (URL of active tab of front window) as text'
        )
    elif "yandex" in app_l or "яндекс" in app_l:
        # Process name is often just "Yandex"; try both English/Russian app names.
        for name in ("Yandex", "Яндекс", "Yandex Browser", "Яндекс Браузер"):
            scripts.append(
                f'tell application "{name}" to return (URL of active tab of front window) as text'
            )
    elif "firefox" in app_l:
        # Firefox has no stable AppleScript URL API — skip.
        return ""
    elif "arc" in app_l:
        scripts.append(
            'tell application "Arc" to return (URL of active tab of front window) as text'
        )
    elif "brave" in app_l:
        scripts.append(
            'tell application "Brave Browser" to return (URL of active tab of front window) as text'
        )
    elif "edge" in app_l:
        scripts.append(
            'tell application "Microsoft Edge" to return (URL of active tab of front window) as text'
        )
    else:
        return ""

    for script in scripts:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )
            url = (result.stdout or "").strip()
            if result.returncode == 0 and url.startswith(("http://", "https://")):
                return url
        except Exception:
            continue
    return ""


def _frontmost_macos() -> tuple[str, str]:
    script = """
    tell application "System Events"
      set frontApp to first application process whose frontmost is true
      set appName to name of frontApp
      set winTitle to ""
      try
        set winTitle to name of front window of frontApp
      end try
      return appName & linefeed & winTitle
    end tell
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if result.returncode != 0:
            return "", ""
        parts = (result.stdout or "").split("\n", 1)
        app = (parts[0] if parts else "").strip()
        title = (parts[1] if len(parts) > 1 else "").strip()
        # Yandex (and some Chromium builds) often expose an empty window title
        # while YouTube is playing — pull the active tab URL as a fallback signal.
        if _is_browser_app(app.lower()) and (
            not title or not DISTRACTION_TITLE_RE.search(title)
        ):
            url = _browser_active_url_macos(app)
            if url:
                title = f"{title} {url}".strip() if title else url
        return app, title
    except Exception:
        return "", ""


def _frontmost_windows() -> tuple[str, str]:
    ps = (
        "Add-Type @'"
        "using System; using System.Runtime.InteropServices; "
        "public class W { "
        "[DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); "
        "[DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder t, int n); "
        "[DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p); "
        "}"
        "'@; "
        "$h = [W]::GetForegroundWindow(); "
        "$sb = New-Object System.Text.StringBuilder 512; "
        "[void][W]::GetWindowText($h, $sb, $sb.Capacity); "
        "$pid = 0; [void][W]::GetWindowThreadProcessId($h, [ref]$pid); "
        "$p = Get-Process -Id $pid -ErrorAction SilentlyContinue; "
        "Write-Output (($p.ProcessName) + \"`n\" + $sb.ToString())"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=5,
        )
        parts = (result.stdout or "").split("\n", 1)
        app = (parts[0] if parts else "").strip()
        title = (parts[1] if len(parts) > 1 else "").strip()
        return app, title
    except Exception:
        return "", ""


def _frontmost_linux() -> tuple[str, str]:
    try:
        wid = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if wid.returncode != 0:
            return "", ""
        w = (wid.stdout or "").strip()
        name = subprocess.run(
            ["xdotool", "getwindowname", w],
            capture_output=True,
            text=True,
            timeout=3,
        )
        title = (name.stdout or "").strip()
        # Best-effort app class
        cls = subprocess.run(
            ["xprop", "-id", w, "WM_CLASS"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        app = ""
        m = re.search(r'"([^"]+)"\s*,\s*"([^"]+)"', cls.stdout or "")
        if m:
            app = m.group(2)
        return app or "unknown", title
    except Exception:
        return "", ""


# —— Persistence ————————————————————————————————————————————————————————————


def default_state() -> dict:
    return {
        "enabled": False,
        "goal": "",
        "idle_minutes": 5.0,
        "language": "ru",
        "message": "",
        "distracted_since": None,
        "last_nudge_at": None,
        "last_app": "",
        "last_title": "",
        "last_kind": "neutral",
        "started_at": None,
        "nudge_count": 0,
        "updated": None,
    }


def load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_state()
        base = default_state()
        base.update(data)
        return base
    except Exception:
        return default_state()


def save_state(state: dict) -> None:
    state = dict(state)
    state["updated"] = datetime.now().isoformat(timespec="seconds")
    try:
        _state_path().write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def build_nudge_text(state: dict) -> str:
    custom = (state.get("message") or "").strip()
    if custom:
        return custom
    goal = (state.get("goal") or "").strip()
    lang = (state.get("language") or "ru").lower()
    if lang == "ru":
        if goal:
            return (
                f"Друг, помнишь — тебе нужно {goal}. "
                f"Хватит залипать, давай вернёмся к делу."
            )
        return "Друг, ты уже довольно долго отвлёкся. Пора вернуться к работе."
    if lang == "tr":
        if goal:
            return f"Dostum, hatırla — {goal}. Biraz dağıldın, işe dönelim."
        return "Dostum, epey dağıldın. İşe geri dönme vakti."
    if goal:
        return f"Hey — remember you wanted to {goal}. You've been drifting, let's get back to it."
    return "Hey, you've been distracted for a bit. Time to get back to work."


# —— Engine ————————————————————————————————————————————————————————————————


class FocusGuardEngine:
    """Background poller. Safe to start once per app lifetime."""

    def __init__(
        self,
        speak_cb: SpeakCb,
        log_cb: ProgressLog | None = None,
        poll_interval: float = 15.0,
        probe_fn: Callable[[], tuple[str, str]] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._speak_cb = speak_cb
        self._log_cb = log_cb
        self._poll = max(5.0, float(poll_interval))
        self._probe = probe_fn or get_frontmost_app
        self._clock = clock or time.monotonic
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="FocusGuardEngine", daemon=True
        )
        self._thread.start()
        self._log("Focus Guard engine started.")

    def stop(self) -> None:
        self._stop.set()

    def _log(self, msg: str) -> None:
        print(f"[FocusGuard] {msg}")
        if self._log_cb:
            try:
                self._log_cb(f"FOCUS: {msg}")
            except Exception:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                self._log(f"tick error: {e}")
            self._stop.wait(self._poll)

    def tick(self) -> dict:
        """One observation cycle. Returns the (possibly updated) state. Testable."""
        with self._lock:
            state = load_state()
            if not state.get("enabled"):
                return state

            app, title = self._probe()
            kind = classify_frontmost(app, title)
            state["last_app"] = app
            state["last_title"] = (title or "")[:180]
            state["last_kind"] = kind

            now = self._clock()
            wall = datetime.now().isoformat(timespec="seconds")

            if kind == "ignore":
                save_state(state)
                return state

            if kind == "work":
                if state.get("distracted_since"):
                    self._log(f"Back to work ({app}). Timer reset.")
                state["distracted_since"] = None
                state["_distracted_mono"] = None
                state["_pause_elapsed"] = None
                save_state(state)
                return state

            if kind == "distraction":
                # Resume after a neutral pause.
                if state.get("_pause_elapsed") is not None:
                    frozen = float(state["_pause_elapsed"] or 0)
                    state["_distracted_mono"] = now - frozen
                    state["_pause_elapsed"] = None
                    if not state.get("distracted_since"):
                        state["distracted_since"] = wall

                if not state.get("distracted_since"):
                    state["distracted_since"] = wall
                    state["_distracted_mono"] = now
                    self._log(f"Distraction detected: {app} — {title[:60]}")
                    save_state(state)
                    return state

                started_mono = state.get("_distracted_mono")
                if started_mono is None:
                    try:
                        started_wall = datetime.fromisoformat(state["distracted_since"])
                        elapsed = (datetime.now() - started_wall).total_seconds()
                    except Exception:
                        elapsed = 0.0
                        state["_distracted_mono"] = now
                else:
                    elapsed = max(0.0, now - float(started_mono))

                threshold = float(state.get("idle_minutes") or 5) * 60.0
                if elapsed >= threshold:
                    nudge = build_nudge_text(state)
                    try:
                        self._speak_cb(nudge, state.get("language") or "ru")
                        state["nudge_count"] = int(state.get("nudge_count") or 0) + 1
                        state["last_nudge_at"] = wall
                        # Require another full idle window before the next nudge.
                        state["distracted_since"] = wall
                        state["_distracted_mono"] = now
                        state["_pause_elapsed"] = None
                        self._log(f"Nudged after {elapsed:.0f}s distraction.")
                    except Exception as e:
                        # Keep timer; retry next poll when voice is ready.
                        self._log(f"Nudge deferred (voice): {e}")
                save_state(state)
                return state

            # neutral — pause the distraction clock (don't reset, don't advance)
            if state.get("distracted_since") and state.get("_pause_elapsed") is None:
                mono = state.get("_distracted_mono")
                if mono is not None:
                    state["_pause_elapsed"] = max(0.0, now - float(mono))
            save_state(state)
            return state


# —— Public API used by the action tool ————————————————————————————————————


def start_guard(
    goal: str,
    idle_minutes: float = 5.0,
    language: str = "ru",
    message: str = "",
) -> dict:
    state = load_state()
    state.update(
        {
            "enabled": True,
            "goal": (goal or "").strip(),
            "idle_minutes": max(0.5, float(idle_minutes or 5)),
            "language": (language or "ru").lower()[:2],
            "message": (message or "").strip(),
            "distracted_since": None,
            "_distracted_mono": None,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "nudge_count": int(state.get("nudge_count") or 0),
        }
    )
    save_state(state)
    return state


def stop_guard() -> dict:
    state = load_state()
    state["enabled"] = False
    state["distracted_since"] = None
    state["_distracted_mono"] = None
    save_state(state)
    return state


def status_text() -> str:
    state = load_state()
    if not state.get("enabled"):
        return "Focus Guard is off."
    goal = state.get("goal") or "your work"
    mins = state.get("idle_minutes") or 5
    kind = state.get("last_kind") or "—"
    app = state.get("last_app") or "—"
    elapsed = ""
    if state.get("distracted_since"):
        try:
            started = datetime.fromisoformat(state["distracted_since"])
            sec = int((datetime.now() - started).total_seconds())
            elapsed = f" Distracted for ~{sec // 60}m {sec % 60}s."
        except Exception:
            elapsed = " Currently distracted."
    return (
        f"Focus Guard is on — watching for distractions over {mins} min. "
        f"Goal: {goal}. Last seen: {app} ({kind}).{elapsed}"
    )
