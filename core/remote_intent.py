"""Deterministic parsing of cross-device power / remote OS intents.

Used so phrases like "выключи Windows" from a Mac never hit local shutdown
just because the Live model picked computer_settings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RemotePowerIntent:
    action: str  # shutdown | restart | sleep | lock
    platform: str = ""  # windows | mac | linux | all | ""
    device_name: str = ""
    confirmed: bool = False
    all_devices: bool = False

    def to_dispatch_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "kind": "computer_settings",
            "action": self.action,
        }
        if self.all_devices or self.platform == "all":
            args["platform"] = "all"
            args["all_devices"] = True
        elif self.platform:
            args["platform"] = self.platform
        if self.device_name:
            args["device_name"] = self.device_name
        # Remote power executes in one shot (no chat confirm). Always stamp
        # confirmed so the target computer_settings gate is satisfied.
        if self.action in {"shutdown", "restart", "sleep", "lock"} or self.confirmed:
            args["confirmed"] = "yes"
        return args


_POWER_ACTIONS: dict[str, tuple[str, ...]] = {
    "shutdown": (
        "выключи",
        "выключить",
        "отключи",
        "отключить",
        "заглуши",
        "погаси",
        "shut down",
        "shutdown",
        "power off",
        "turn off",
        "switch off",
        "выруби",
        "вырубить",
    ),
    "restart": (
        "перезагрузи",
        "перезагрузить",
        "рестарт",
        "restart",
        "reboot",
        "перезапусти компьютер",
        "перезапусти ноутбук",
        "перезапусти пк",
    ),
    "sleep": (
        "усыпи",
        "усып",
        "в сон",
        "в спящий",
        "спящий режим",
        "спящем режим",
        "режим сна",
        "в режим сна",
        "спящ",
        "засни",
        "усни",
        "поспи",
        "sleep",
        "hibernate",
        "suspend",
    ),
    "lock": (
        "заблокируй",
        "заблокировать",
        "lock screen",
        "lock the",
        "залочь",
    ),
}

_CONFIRM = (
    "да",
    "yes",
    "подтверждаю",
    "confirm",
    "подтверди",
    "согласен",
    "ок давай",
    "давай",
    "go ahead",
    "do it",
)

# Explicit "this machine" — keep local.
_LOCAL_ONLY = (
    "этот компьютер",
    "этот ноутбук",
    "этот мак",
    "этот пк",
    "эту машину",
    "this computer",
    "this mac",
    "this pc",
    "this laptop",
    "this machine",
    "здесь",
    "тут на",
    "на этом",
)

_ALL = (
    "оба",
    "обе",
    "все устройства",
    "все компы",
    "все компьютеры",
    "both",
    "all devices",
    "every device",
    "everywhere",
)

_WINDOWS = (
    "windows",
    "виндовс",
    "винду",
    "винда",
    "винде",
    "виндовый",
    "gaming pc",
    "gaming",
)
_MAC = (
    "macos",
    "mac os",
    "макбук",
    "маке",
    "мака",
    "маком",
    "мак ",
    " mac",
    "mac ",
    "apple silicon",
    "darwin",
)
_LINUX = ("linux", "линукс", "убунту", "ubuntu")


def _norm(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    t = re.sub(r"[^\w\s\-./]+", " ", t, flags=re.UNICODE)
    return " ".join(t.split())


def _has_any(low: str, needles: tuple[str, ...]) -> bool:
    return any(n in low for n in needles)


def _detect_action(low: str) -> str | None:
    # Sleep/lock verbs are unambiguous, so check them before shutdown/restart —
    # e.g. "переведи в спящий режим" must not be read as "выключи".
    for action in ("sleep", "lock", "restart", "shutdown"):
        if _has_any(low, _POWER_ACTIONS[action]):
            return action
    return None


def _detect_platform(low: str) -> tuple[str, str, bool]:
    """Return (platform, device_name, all_devices)."""
    if _has_any(low, _ALL):
        return "all", "", True

    # Named device after "устройство/device/на".
    m = re.search(
        r"(?:устройство|device|комп(?:ьютер)?|ноутбук|laptop|машину?)\s+"
        r"[«\"']?([a-z0-9][\w\- ]{1,40})",
        low,
    )
    device_name = ""
    if m:
        candidate = m.group(1).strip()
        # Strip trailing power words.
        for stop in ("выключ", "отключ", "shut", "turn", "restart", "reboot"):
            if stop in candidate:
                candidate = candidate.split(stop)[0].strip()
        if candidate and candidate not in {"windows", "mac", "macos", "linux", "пк", "pc"}:
            device_name = candidate[:64]

    if _has_any(low, _WINDOWS) or device_name in {"gaming", "gaming pc"}:
        # "пк" alone is weak on a Windows host — still OK as remote hint when
        # paired with power + not local-only; caller decides.
        return "windows", device_name, False
    if _has_any(low, _MAC):
        return "mac", device_name, False
    if _has_any(low, _LINUX):
        return "linux", device_name, False
    if device_name:
        return "", device_name, False
    return "", "", False


def parse_remote_power_intent(text: str) -> RemotePowerIntent | None:
    """If the user wants power action on another / all devices, return intent.

    Returns None for local-only phrases ("выключи этот компьютер") or when
    there is no power verb + remote target.
    """
    low = _norm(text)
    if not low:
        return None

    action = _detect_action(low)
    if not action:
        return None

    if _has_any(low, _LOCAL_ONLY):
        return None

    platform, device_name, all_devices = _detect_platform(low)

    # Need an explicit remote target — avoid stealing plain "выключи компьютер".
    remote_markers = (
        "windows",
        "виндовс",
        "винду",
        "винда",
        "винде",
        "macos",
        "mac os",
        "макбук",
        "маке",
        "мака",
        "маком",
        " mac",
        "mac ",
        "linux",
        "линукс",
        "другое устройство",
        "другой комп",
        "другой компьютер",
        "другой ноутбук",
        "на пк",
        "на pc",
        "на вин",
        "на мак",
        "remote",
        "other device",
        "other pc",
        "other computer",
        "other laptop",
        "gaming",
    )
    has_remote = (
        all_devices
        or bool(device_name)
        or bool(platform)
        or _has_any(low, remote_markers)
    )
    # "выключи пк" from Mac is a common remote ask; treat "пк"/"pc" as windows
    # only when NOT also saying mac/local.
    if not has_remote and _has_any(low, (" пк", "пк ", " pc", "pc ")) and not _has_any(
        low, ("мак", "mac", "этот", "this")
    ):
        platform = platform or "windows"
        has_remote = True

    if not has_remote:
        return None

    if all_devices:
        platform = "all"

    confirmed = _has_any(low, _CONFIRM) and (
        "confirm" in low
        or "подтверд" in low
        or low.strip() in {"да", "yes", "ok", "ок", "давай"}
        or any(low.strip().startswith(c) for c in ("да ", "yes ", "ok "))
    )
    # Also: "... confirmed" / "да, выключи windows"
    if re.search(r"\b(да|yes)\b.+\b(выключ|отключ|shut|turn off|restart)", low):
        confirmed = True
    if re.search(r"\b(выключ|отключ|shut|turn off|restart).+\b(да|yes|confirm)\b", low):
        confirmed = True

    return RemotePowerIntent(
        action=action,
        platform=platform,
        device_name=device_name,
        confirmed=confirmed,
        all_devices=all_devices,
    )


def wants_remote_target(text: str) -> bool:
    """True when the utterance clearly points at another machine."""
    low = _norm(text)
    if not low or _has_any(low, _LOCAL_ONLY):
        return False
    if _has_any(low, _ALL):
        return True
    return _has_any(
        low,
        (
            "windows",
            "виндовс",
            "винду",
            "винда",
            "macos",
            "макбук",
            "на мак",
            "на пк",
            "на pc",
            "linux",
            "линукс",
            "другое устройство",
            "другой комп",
            "другой компьютер",
            "other device",
            "other pc",
            "gaming",
        ),
    )


def should_redirect_local_power(action: str, recent_user_text: str) -> RemotePowerIntent | None:
    """If Live called local computer_settings but user meant a remote target."""
    act = (action or "").strip().lower().replace("-", "_")
    if act == "reboot":
        act = "restart"
    if act not in {"shutdown", "restart", "sleep", "lock", "hibernate"}:
        return None
    if act == "hibernate":
        act = "sleep"

    intent = parse_remote_power_intent(recent_user_text)
    if intent and intent.action in {"shutdown", "restart", "sleep", "lock"}:
        # Prefer the tool's action if user text was ambiguous, but keep target.
        return RemotePowerIntent(
            action=act if act in {"shutdown", "restart", "sleep", "lock"} else intent.action,
            platform=intent.platform,
            device_name=intent.device_name,
            confirmed=True,
            all_devices=intent.all_devices,
        )

    # Fallback: power tool + remote markers in recent text without full parse.
    if wants_remote_target(recent_user_text):
        platform, device_name, all_devices = _detect_platform(_norm(recent_user_text))
        if platform or device_name or all_devices:
            return RemotePowerIntent(
                action=act,
                platform=platform or ("all" if all_devices else ""),
                device_name=device_name,
                confirmed=True,
                all_devices=all_devices,
            )
    return None


def tool_result_ok(result: Any) -> bool:
    """Heuristic: did an action tool succeed?"""
    text = str(result or "").strip()
    if not text:
        return False
    low = text.lower()
    fail_markers = (
        "fail",
        "error",
        "could not",
        "couldn't",
        "cannot",
        "can't",
        "denied",
        "block",
        "offline",
        "not found",
        "missing",
        "sign in required",
        "не удалось",
        "ошибка",
        "запрещ",
        "не найден",
        "офлайн",
        "please confirm",
        "call again with confirmed",
        "confirm by calling",
        "needs app_name",
        "unsupported",
    )
    if any(m in low for m in fail_markers):
        # Confirm prompts are not successes.
        return False
    return True
