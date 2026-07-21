"""Send a remote job to another linked AURA desktop (same account)."""

from __future__ import annotations

from typing import Any

SUPPORTED_KINDS = {
    "open_url",
    "open_app",
    "browser_control",
    "computer_control",
    "computer_settings",
    "file_controller",
    "agent_task",
}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _platform_aliases(hint: str) -> set[str]:
    h = _norm(hint)
    if h in {"mac", "macos", "darwin", "apple", "osx"}:
        return {"darwin"}
    if h in {"win", "windows", "pc", "win32"}:
        return {"win32"}
    if h in {"linux"}:
        return {"linux"}
    return {h} if h else set()


def _target_permissions(device: dict[str, Any]) -> dict[str, bool]:
    raw = device.get("permissions") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "allow_remote_control": raw.get("allow_remote_control", True) is not False,
        "allow_remote_files": raw.get("allow_remote_files") is True,
        "allow_remote_system": raw.get("allow_remote_system") is True,
    }


def _kind_allowed(kind: str, perms: dict[str, bool], payload: dict) -> str | None:
    """Return error string if blocked, else None."""
    if kind in {
        "open_url",
        "open_app",
        "browser_control",
        "computer_control",
        "agent_task",
    }:
        if not perms.get("allow_remote_control", True):
            return "Target device has remote control disabled (Devices → Allow remote control)."
    if kind == "file_controller":
        if not perms.get("allow_remote_files", False):
            return "Target device blocks remote files (enable Allow remote files on that PC)."
    if kind == "computer_settings":
        action = _norm(str(payload.get("action") or ""))
        dangerous = {
            "shutdown",
            "restart",
            "reboot",
            "sleep",
            "hibernate",
            "lock",
            "logout",
            "log out",
            "sign out",
        }
        if action in dangerous and not perms.get("allow_remote_system", False):
            return (
                "Target blocks remote system power actions "
                "(enable Allow remote system on that PC)."
            )
        if not perms.get("allow_remote_control", True):
            return "Target device has remote control disabled."
    return None


def resolve_target_device(
    devices: list[dict[str, Any]],
    *,
    device_id: str = "",
    device_name: str = "",
    platform: str = "",
) -> dict[str, Any] | None:
    """Pick a linked device by id, name, or platform (prefer online)."""
    if not devices:
        return None

    did = (device_id or "").strip()
    if did:
        for d in devices:
            if str(d.get("id") or "") == did:
                return d
        return None

    name_q = _norm(device_name)
    plat_set = _platform_aliases(platform)

    candidates = list(devices)
    if plat_set:
        filtered = [
            d
            for d in candidates
            if _norm(str(d.get("platform") or "")) in plat_set
            or any(p in _norm(str(d.get("name") or "")) for p in plat_set)
        ]
        if filtered:
            candidates = filtered

    if name_q:
        exact = [d for d in candidates if _norm(str(d.get("name") or "")) == name_q]
        if exact:
            candidates = exact
        else:
            partial = [
                d for d in candidates if name_q in _norm(str(d.get("name") or ""))
            ]
            if partial:
                candidates = partial

    others = [
        d
        for d in candidates
        if not d.get("isThisDevice") and not d.get("is_this_device")
    ]
    pool = others or candidates
    online = [d for d in pool if d.get("online")]
    pool = online or pool
    return pool[0] if pool else None


def _infer_kind(args: dict[str, Any], url: str) -> str:
    kind = str(args.get("kind") or args.get("action_kind") or "").strip().lower()
    if kind:
        return kind
    if url:
        return "open_url"
    if args.get("app_name") or args.get("app"):
        return "open_app"
    if args.get("goal"):
        return "agent_task"
    action = _norm(str(args.get("action") or ""))
    if action in {
        "list",
        "create_file",
        "create_folder",
        "delete",
        "move",
        "copy",
        "rename",
        "read",
        "write",
        "find",
        "info",
    }:
        return "file_controller"
    if action in {
        "volume",
        "brightness",
        "shutdown",
        "restart",
        "sleep",
        "lock",
        "wifi",
        "dark_mode",
        "close_window",
    }:
        return "computer_settings"
    return "browser_control"


def dispatch_to_device(parameters: dict | None = None, player=None, **_kwargs) -> str:
    """
    Enqueue a job for a linked device and wait briefly for the result.

    parameters:
      device_id | device_name | platform — target selector
      kind — open_url | open_app | browser_control | computer_control |
              computer_settings | file_controller | agent_task
      url / app_name / goal / action / … — merged into payload
      wait — if false, return immediately after queue (default true)
    """
    from jarvis_ui import device_sync as DS
    from jarvis_ui import user_account as UA

    args = dict(parameters or {})
    if not UA.is_authenticated():
        return "Sign in required to control other devices. Open Profile → Sign in."

    try:
        snap = DS.start_device_sync().refresh_now()
        devices = list(snap.get("devices") or [])
    except Exception as e:
        return f"Could not list devices: {e}"

    if not devices:
        return (
            "No linked devices yet. Install AURA on the other computer, "
            "sign in with the same account, and open Devices in the sidebar."
        )

    target = resolve_target_device(
        devices,
        device_id=str(args.get("device_id") or ""),
        device_name=str(args.get("device_name") or args.get("device") or ""),
        platform=str(args.get("platform") or ""),
    )
    if not target:
        listing = ", ".join(
            f"{d.get('name')} ({'online' if d.get('online') else 'offline'}"
            f", {d.get('platform')})"
            for d in devices
        )
        return f"Could not find that device. Linked: {listing}"

    url = str(args.get("url") or "").strip()
    kind = _infer_kind(args, url)

    payload: dict[str, Any] = {}
    raw_payload = args.get("payload")
    if isinstance(raw_payload, dict):
        payload.update(raw_payload)
    for key in (
        "url",
        "app_name",
        "name",
        "goal",
        "priority",
        "action",
        "query",
        "engine",
        "browser",
        "text",
        "description",
        "selector",
        "direction",
        "amount",
        "key",
        "keys",
        "x",
        "y",
        "title",
        "path",
        "destination",
        "new_name",
        "content",
        "extension",
        "count",
        "value",
        "incognito",
        "clear_first",
        "seconds",
    ):
        if key in args and args[key] is not None and key not in payload:
            payload[key] = args[key]

    if "app_name" not in payload and args.get("app"):
        payload["app_name"] = args["app"]

    if kind == "open_url":
        if not payload.get("url") and url:
            payload["url"] = url
        if not payload.get("url"):
            return "open_url needs a url (e.g. https://news.google.com)."

    if kind == "open_app" and not payload.get("app_name"):
        return "open_app needs app_name (e.g. Chrome, Spotify)."

    if kind == "agent_task" and not payload.get("goal"):
        goal = str(args.get("description") or args.get("text") or "").strip()
        if goal:
            payload["goal"] = goal
        else:
            return "agent_task needs a goal describing what to do on the other PC."

    if kind not in SUPPORTED_KINDS:
        return (
            f"Unsupported kind '{kind}'. Use: " + ", ".join(sorted(SUPPORTED_KINDS))
        )

    blocked = _kind_allowed(kind, _target_permissions(target), payload)
    if blocked:
        return blocked

    try:
        job = DS.enqueue_job(str(target["id"]), kind, payload)
    except Exception as e:
        return f"Failed to send job: {e}"

    jid = ""
    if isinstance(job.get("job"), dict):
        jid = str(job["job"].get("id") or "")
    else:
        jid = str(job.get("id") or "")
    name = target.get("name") or "device"
    online = bool(target.get("online"))
    wait = args.get("wait", True)
    if isinstance(wait, str):
        wait = wait.strip().lower() not in {"0", "false", "no"}

    if not wait or not jid:
        state = "online" if online else "offline (runs when it comes online)"
        return (
            f"Queued {kind} for “{name}” ({state})"
            + (f" · job {jid}" if jid else "")
            + ". Keep AURA running on that machine."
        )

    # Wait for the target poller (~5s) to claim + finish.
    try:
        if player is not None and hasattr(player, "write_log"):
            player.write_log(f"SYS: Waiting for “{name}” to run {kind}…")
    except Exception:
        pass

    done = DS.wait_for_job(jid, timeout_s=50.0, poll_s=2.0)
    status = str(done.get("status") or "")
    if status == "done":
        result = str(done.get("result") or "ok")
        return f"Done on “{name}”: {result}"
    if status == "failed":
        err = str(done.get("error") or "failed")
        return f"Failed on “{name}”: {err}"
    return (
        f"Queued {kind} for “{name}” (still {status or 'pending'}). "
        "Keep AURA running there — it should finish shortly."
    )
