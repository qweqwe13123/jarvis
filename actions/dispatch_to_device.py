"""Send a remote job to another linked AURA desktop (same account)."""

from __future__ import annotations

from typing import Any

SUPPORTED_KINDS = {
    "open_url",
    "open_app",
    "close_app",
    "close_all_apps",
    "browser_control",
    "computer_control",
    "computer_settings",
    "file_controller",
    "agent_task",
}

_SYSTEM_DANGEROUS = {
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


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _truthy(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    return str(val or "").strip().lower() in {"1", "true", "yes", "confirm", "y"}


def _platform_aliases(hint: str) -> set[str]:
    h = _norm(hint)
    if h in {"mac", "macos", "darwin", "apple", "osx"}:
        return {"darwin"}
    if h in {"win", "windows", "pc", "win32"}:
        return {"win32"}
    if h in {"linux"}:
        return {"linux"}
    if h in {"all", "both", "все", "оба", "всех", "everyone", "every"}:
        return {"__all__"}
    return {h} if h else set()


def _wants_all_devices(args: dict[str, Any]) -> bool:
    if _truthy(args.get("all_devices")) or _truthy(args.get("both")):
        return True
    plat = _norm(str(args.get("platform") or ""))
    name = _norm(str(args.get("device_name") or args.get("device") or ""))
    if plat in {"all", "both", "все", "оба"}:
        return True
    if name in {"all", "both", "все", "оба", "оба устройства", "all devices"}:
        return True
    return False


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
        "close_app",
        "close_all_apps",
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
        if action in _SYSTEM_DANGEROUS and not perms.get("allow_remote_system", False):
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
    if "__all__" in plat_set:
        plat_set = set()

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

    if name_q and name_q not in {"all", "both", "все", "оба", "оба устройства", "all devices"}:
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


def resolve_all_targets(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """All linked devices (this + others), preferring online ones first."""
    if not devices:
        return []
    online = [d for d in devices if d.get("online")]
    return online or list(devices)


def _infer_kind(args: dict[str, Any], url: str) -> str:
    kind = str(args.get("kind") or args.get("action_kind") or "").strip().lower()
    if kind:
        return kind
    if url:
        return "open_url"
    action = _norm(str(args.get("action") or ""))
    if action in {
        "close_app",
        "quit_app",
        "kill_app",
        "close_application",
    }:
        return "close_app"
    if action in {
        "close_all_apps",
        "quit_all_apps",
        "close_everything",
    }:
        return "close_all_apps"
    if action == "close_all":
        # Prefer browser_control for tab/session close_all unless explicit OS kind.
        if str(args.get("kind") or "").lower() in {"close_all_apps", "computer_settings"}:
            return "close_all_apps"
        return "browser_control"
    if args.get("app_name") or args.get("app"):
        if action.startswith("close") or action.startswith("quit"):
            return "close_app"
        return "open_app"
    if args.get("goal"):
        return "agent_task"
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
        "close_tab",
    }:
        return "computer_settings"
    return "browser_control"


def _build_payload(args: dict[str, Any], url: str) -> dict[str, Any]:
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
        "confirmed",
    ):
        if key in args and args[key] is not None and key not in payload:
            payload[key] = args[key]

    if "app_name" not in payload and args.get("app"):
        payload["app_name"] = args["app"]
    if url and "url" not in payload:
        payload["url"] = url
    return payload


def _enqueue_and_wait(
    *,
    target: dict[str, Any],
    kind: str,
    payload: dict[str, Any],
    wait: bool,
    player=None,
) -> str:
    from jarvis_ui import device_sync as DS

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

    if not wait or not jid:
        state = "online" if online else "offline (runs when it comes online)"
        return (
            f"Queued {kind} for “{name}” ({state})"
            + (f" · job {jid}" if jid else "")
            + ". Keep AURA running on that machine."
        )

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


def _dispatch_all_power(
    *,
    devices: list[dict[str, Any]],
    action: str,
    wait: bool,
    player=None,
) -> str:
    """Shutdown/restart every linked device (this one locally + remotes).

    No chat confirm round-trip: consent is Devices → Allow remote system on
    each remote, and local power is intentional when the user said "both/all".
    """
    from actions.computer_settings import computer_settings

    targets = resolve_all_targets(devices)
    lines: list[str] = []
    for d in targets:
        is_this = bool(d.get("isThisDevice") or d.get("is_this_device"))
        name = d.get("name") or "device"
        if is_this:
            out = computer_settings(
                parameters={"action": action, "confirmed": "yes"}
            )
            lines.append(f"This device (“{name}”): {out}")
            continue
        blocked = _kind_allowed(
            "computer_settings",
            _target_permissions(d),
            {"action": action},
        )
        if blocked:
            lines.append(f"“{name}”: {blocked}")
            continue
        lines.append(
            _enqueue_and_wait(
                target=d,
                kind="computer_settings",
                payload={"action": action, "confirmed": "yes"},
                wait=wait,
                player=player,
            )
        )
    return "\n".join(lines) if lines else "No linked devices to power-control."


def dispatch_to_device(parameters: dict | None = None, player=None, **_kwargs) -> str:
    """
    Enqueue a job for a linked device and wait briefly for the result.

    parameters:
      device_id | device_name | platform — target selector
        platform=all|both → fan-out (power actions include this device)
      kind — open_url | open_app | close_app | close_all_apps |
              browser_control | computer_control | computer_settings |
              file_controller | agent_task
      confirmed — required for close_all_apps only.
        Remote shutdown/restart runs immediately (consent = Allow remote system
        on the target). Local computer_settings still has its own confirm.
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

    url = str(args.get("url") or "").strip()
    kind = _infer_kind(args, url)
    payload = _build_payload(args, url)
    wait = args.get("wait", True)
    if isinstance(wait, str):
        wait = wait.strip().lower() not in {"0", "false", "no"}
    confirmed = _truthy(args.get("confirmed") or payload.get("confirmed"))
    if confirmed:
        payload["confirmed"] = "yes"

    # Normalize close_* into dedicated kinds with computer_settings-compatible payload.
    if kind == "close_app":
        payload["action"] = "close_app"
        if not payload.get("app_name"):
            return "close_app needs app_name (e.g. Yandex, Chrome)."
    if kind == "close_all_apps":
        payload["action"] = "close_all_apps"
        if not confirmed:
            return (
                "This will close open user apps on the target. "
                "Confirm with confirmed=yes."
            )

    action = _norm(str(payload.get("action") or args.get("action") or ""))
    if kind == "computer_settings" and action in {"shutdown", "restart", "reboot"}:
        if action == "reboot":
            payload["action"] = "restart"
            action = "restart"
        # Execute immediately — bare "yes" confirm round-trips fail with Live.
        # Safety gate: target Devices → Allow remote system (checked on enqueue).
        payload["confirmed"] = "yes"
        if _wants_all_devices(args):
            return _dispatch_all_power(
                devices=devices,
                action=action,
                wait=wait,
                player=player,
            )

    if kind == "open_url" and not payload.get("url"):
        return "open_url needs a url (e.g. https://news.google.com)."

    if kind == "open_app" and not payload.get("app_name"):
        return "open_app needs app_name (e.g. Chrome, Yandex Browser)."

    if kind == "agent_task" and not payload.get("goal"):
        goal = str(args.get("description") or args.get("text") or "").strip()
        if goal:
            payload["goal"] = goal
        else:
            return "agent_task needs a goal describing what to do on the other PC."

    # Map dedicated close kinds onto computer_settings execution on the target
    # (same tool surface) while keeping kind labels for clarity in logs.
    exec_kind = kind
    if kind in {"close_app", "close_all_apps"}:
        exec_kind = "computer_settings"

    if exec_kind not in SUPPORTED_KINDS and kind not in SUPPORTED_KINDS:
        return (
            f"Unsupported kind '{kind}'. Use: " + ", ".join(sorted(SUPPORTED_KINDS))
        )

    if _wants_all_devices(args) and action not in {"shutdown", "restart"}:
        # Fan-out non-power actions to every *other* online device (not this one).
        others = [
            d
            for d in resolve_all_targets(devices)
            if not d.get("isThisDevice") and not d.get("is_this_device")
        ]
        if not others:
            return "No other linked devices to control."
        parts = [
            _enqueue_and_wait(
                target=d,
                kind=exec_kind if exec_kind in SUPPORTED_KINDS else kind,
                payload=dict(payload),
                wait=wait,
                player=player,
            )
            for d in others
        ]
        return "\n".join(parts)

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

    return _enqueue_and_wait(
        target=target,
        kind=exec_kind if exec_kind in SUPPORTED_KINDS else kind,
        payload=payload,
        wait=wait,
        player=player,
    )
