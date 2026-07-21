"""Send a remote job to another linked AURA desktop (same account)."""

from __future__ import annotations

from typing import Any


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

    # Prefer other machines over this one when the user said "Windows" / "Mac".
    others = [d for d in candidates if not d.get("isThisDevice") and not d.get("is_this_device")]
    pool = others or candidates
    online = [d for d in pool if d.get("online")]
    pool = online or pool
    return pool[0] if pool else None


def dispatch_to_device(parameters: dict | None = None, player=None, **_kwargs) -> str:
    """
    Enqueue a job for a linked device.

    parameters:
      device_id | device_name | platform — target selector
      kind — open_url | browser_control | computer_control
      url — for open_url (also accepted at top level)
      payload — dict passed through for browser/computer control
      action, query, … — merged into payload for convenience
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

    kind = str(args.get("kind") or args.get("action_kind") or "").strip().lower()
    url = str(args.get("url") or "").strip()
    if not kind:
        kind = "open_url" if url else "browser_control"

    payload: dict[str, Any] = {}
    raw_payload = args.get("payload")
    if isinstance(raw_payload, dict):
        payload.update(raw_payload)
    for key in (
        "url",
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
        "incognito",
        "clear_first",
        "seconds",
    ):
        if key in args and args[key] is not None and key not in payload:
            payload[key] = args[key]

    if kind == "open_url":
        if not payload.get("url") and url:
            payload["url"] = url
        if not payload.get("url"):
            return "open_url needs a url (e.g. https://news.google.com)."

    if kind not in {"open_url", "browser_control", "computer_control"}:
        return (
            f"Unsupported kind '{kind}'. Use open_url, browser_control, or computer_control."
        )

    try:
        job = DS.enqueue_job(str(target["id"]), kind, payload)
    except Exception as e:
        return f"Failed to send job: {e}"

    online = "online" if target.get("online") else "offline (will run when it comes online)"
    jid = (job.get("job") or job).get("id") if isinstance(job.get("job"), dict) else job.get("id")
    name = target.get("name") or "device"
    return (
        f"Queued {kind} for “{name}” ({online})"
        + (f" · job {jid}" if jid else "")
        + ". Keep AURA running on that machine."
    )
