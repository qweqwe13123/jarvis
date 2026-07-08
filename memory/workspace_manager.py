"""Workspace, chat, automation, and settings persistence for JARVIS."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
import sys


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


STORE_PATH = _base_dir() / "memory" / "workspaces.json"
_lock = Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _default_store() -> dict:
    return {
        "active_workspace_id": "default",
        "active_chat_id": None,
        "workspaces": {
            "default": {
                "id": "default",
                "name": "Default Workspace",
                "path": str(_base_dir()),
                "chats": [],
                "created": _now(),
            }
        },
        "automations": [],
        "reminders": [],
        "settings": {
            "system_prompt": "",
            "model": "auto",
            "provider": "auto",
            "temperature": 0.7,
            "tools_enabled": True,
            "memory_enabled": True,
            "api_keys": {},
        },
    }


def load_store() -> dict:
    if not STORE_PATH.exists():
        return _default_store()
    with _lock:
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return _default_store()
            base = _default_store()
            base.update({k: data.get(k, v) for k, v in base.items() if k != "workspaces"})
            if isinstance(data.get("workspaces"), dict):
                base["workspaces"] = data["workspaces"]
            if isinstance(data.get("automations"), list):
                base["automations"] = data["automations"]
            if isinstance(data.get("settings"), dict):
                base["settings"].update(data["settings"])
            for workspace in base.get("workspaces", {}).values():
                workspace.setdefault("chats", [])
                for chat in workspace.get("chats", []):
                    chat.setdefault("pinned", False)
                    chat.setdefault("messages", [])
                    chat.setdefault("artifacts", [])
                    chat.setdefault("project_state", {})
                    chat.setdefault("created", _now())
                    chat.setdefault("updated", chat.get("created", _now()))
            base.setdefault("reminders", [])
            return base
        except Exception:
            return _default_store()


def save_store(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        STORE_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def get_active_workspace(store: dict | None = None) -> dict:
    store = store or load_store()
    ws_id = store.get("active_workspace_id", "default")
    ws = store["workspaces"].get(ws_id)
    if not ws:
        ws = _default_store()["workspaces"]["default"]
    return ws


def get_active_chat(store: dict | None = None) -> dict | None:
    store = store or load_store()
    chat_id = store.get("active_chat_id")
    if not chat_id:
        return None
    ws = get_active_workspace(store)
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            return chat
    return None


def create_chat(title: str | None = None) -> dict:
    store = load_store()
    ws = get_active_workspace(store)
    chat = {
        "id": _new_id(),
        "title": title or "New Chat",
        "pinned": False,
        "messages": [],
        "artifacts": [],
        "project_state": {},
        "created": _now(),
        "updated": _now(),
    }
    ws.setdefault("chats", []).insert(0, chat)
    store["active_chat_id"] = chat["id"]
    save_store(store)
    return chat


def rename_chat(chat_id: str, title: str) -> bool:
    store = load_store()
    ws = get_active_workspace(store)
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            chat["title"] = title.strip() or "Untitled"
            chat["updated"] = _now()
            save_store(store)
            return True
    return False


def delete_chat(chat_id: str) -> bool:
    store = load_store()
    ws = get_active_workspace(store)
    chats = ws.get("chats", [])
    new_chats = [c for c in chats if c.get("id") != chat_id]
    if len(new_chats) == len(chats):
        return False
    ws["chats"] = new_chats
    if store.get("active_chat_id") == chat_id:
        store["active_chat_id"] = new_chats[0]["id"] if new_chats else None
    save_store(store)
    return True


def pin_chat(chat_id: str, pinned: bool = True) -> bool:
    store = load_store()
    ws = get_active_workspace(store)
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            chat["pinned"] = pinned
            chat["updated"] = _now()
            save_store(store)
            return True
    return False


def toggle_pin_chat(chat_id: str) -> bool:
    store = load_store()
    ws = get_active_workspace(store)
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            chat["pinned"] = not bool(chat.get("pinned"))
            chat["updated"] = _now()
            save_store(store)
            return True
    return False


def set_active_chat(chat_id: str) -> bool:
    store = load_store()
    ws = get_active_workspace(store)
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            store["active_chat_id"] = chat_id
            save_store(store)
            return True
    return False


def add_message(role: str, content: str, meta: dict | None = None) -> dict | None:
    store = load_store()
    chat_id = store.get("active_chat_id")
    if not chat_id:
        chat = create_chat()
        chat_id = chat["id"]
        store = load_store()
    ws = get_active_workspace(store)
    msg = {
        "id": _new_id(),
        "role": role,
        "content": content,
        "meta": meta or {},
        "ts": _now(),
    }
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            chat.setdefault("messages", []).append(msg)
            chat["updated"] = _now()
            if role == "user" and chat.get("title") == "New Chat":
                chat["title"] = content[:48] + ("…" if len(content) > 48 else "")
            save_store(store)
            return msg
    return None


def add_artifact(kind: str, title: str, payload: str,
                 path: str | None = None, meta: dict | None = None) -> dict | None:
    """Persist a generated output in the active session workspace."""
    store = load_store()
    chat_id = store.get("active_chat_id")
    if not chat_id:
        chat = create_chat(title or "New Session")
        chat_id = chat["id"]
        store = load_store()
    ws = get_active_workspace(store)
    artifact = {
        "id": _new_id(),
        "kind": kind or "text",
        "title": (title or "Output")[:80],
        "payload": payload or "",
        "path": path or "",
        "meta": meta or {},
        "created": _now(),
        "updated": _now(),
    }
    for chat in ws.get("chats", []):
        if chat.get("id") == chat_id:
            chat.setdefault("artifacts", []).append(artifact)
            state = chat.setdefault("project_state", {})
            state["active_artifact_id"] = artifact["id"]
            state["last_output_kind"] = artifact["kind"]
            # Pointer into the single chronological thread so the conversation
            # timeline can render the artifact inline in order.
            chat.setdefault("messages", []).append({
                "id": _new_id(),
                "role": "artifact",
                "content": artifact["title"],
                "meta": {
                    "artifact_id": artifact["id"],
                    "kind": artifact["kind"],
                    "title": artifact["title"],
                    "path": artifact["path"],
                },
                "ts": _now(),
            })
            chat["updated"] = _now()
            save_store(store)
            return artifact
    return None


def get_session_state(chat_id: str | None = None) -> dict:
    store = load_store()
    if chat_id:
        ws = get_active_workspace(store)
        chat = next((c for c in ws.get("chats", []) if c.get("id") == chat_id), None)
    else:
        chat = get_active_chat(store)
    if not chat:
        return {"messages": [], "artifacts": [], "project_state": {}}
    return {
        "messages": list(chat.get("messages", [])),
        "artifacts": list(chat.get("artifacts", [])),
        "project_state": dict(chat.get("project_state", {})),
    }


def list_chats(workspace_id: str | None = None) -> list[dict]:
    store = load_store()
    if workspace_id:
        ws = store["workspaces"].get(workspace_id, {})
    else:
        ws = get_active_workspace(store)
    chats = list(ws.get("chats", []))
    chats.sort(key=lambda c: (not c.get("pinned", False), c.get("updated", "")), reverse=True)
    return chats


def list_workspaces() -> list[dict]:
    store = load_store()
    items = []
    for ws in store.get("workspaces", {}).values():
        items.append({
            "id": ws.get("id"),
            "name": ws.get("name"),
            "chat_count": len(ws.get("chats", [])),
            "path": ws.get("path", ""),
        })
    return sorted(items, key=lambda x: x.get("name", "").lower())


def add_workspace(name: str, path: str | None = None) -> dict:
    store = load_store()
    ws_id = _new_id()
    ws = {
        "id": ws_id,
        "name": name,
        "path": path or str(_base_dir()),
        "chats": [],
        "created": _now(),
    }
    store["workspaces"][ws_id] = ws
    store["active_workspace_id"] = ws_id
    store["active_chat_id"] = None
    save_store(store)
    return ws


def set_active_workspace(ws_id: str) -> bool:
    store = load_store()
    if ws_id not in store.get("workspaces", {}):
        return False
    store["active_workspace_id"] = ws_id
    store["active_chat_id"] = None
    save_store(store)
    return True


def rename_workspace(ws_id: str, name: str) -> bool:
    store = load_store()
    ws = store.get("workspaces", {}).get(ws_id)
    if not ws:
        return False
    ws["name"] = name.strip() or ws.get("name", "Workspace")
    save_store(store)
    return True


def delete_workspace(ws_id: str) -> bool:
    """Delete a workspace. The 'default' workspace cannot be removed."""
    store = load_store()
    if ws_id == "default" or ws_id not in store.get("workspaces", {}):
        return False
    del store["workspaces"][ws_id]
    if store.get("active_workspace_id") == ws_id:
        store["active_workspace_id"] = "default"
        store["active_chat_id"] = None
    save_store(store)
    return True


def get_active_ids() -> tuple[str, str | None]:
    store = load_store()
    return store.get("active_workspace_id", "default"), store.get("active_chat_id")


def load_automations() -> list[dict]:
    store = load_store()
    automations = list(store.get("automations", []))
    wf_dir = _base_dir() / "runtime" / "workflows"
    if wf_dir.exists():
        for fp in wf_dir.glob("*.json"):
            try:
                wf = json.loads(fp.read_text(encoding="utf-8"))
                automations.append({
                    "id": fp.stem,
                    "name": wf.get("goal", fp.stem)[:60],
                    "status": wf.get("status", "draft"),
                    "source": "file",
                    "path": str(fp),
                })
            except Exception:
                pass
    return automations


def save_automation(name: str, goal: str, status: str = "active") -> dict:
    store = load_store()
    auto = {
        "id": _new_id(),
        "name": name,
        "goal": goal,
        "status": status,
        "created": _now(),
    }
    store.setdefault("automations", []).append(auto)
    save_store(store)
    return auto


def update_automation_status(auto_id: str, status: str) -> bool:
    store = load_store()
    for auto in store.get("automations", []):
        if auto.get("id") == auto_id:
            auto["status"] = status
            save_store(store)
            return True
    return False


def get_settings() -> dict:
    return load_store().get("settings", _default_store()["settings"])


def save_settings(updates: dict) -> dict:
    store = load_store()
    store["settings"].update(updates)
    save_store(store)
    return store["settings"]


def discover_project_workspaces() -> list[dict]:
    """Scan common project roots and merge into workspace list."""
    store = load_store()
    roots = [
        Path.home() / "Desktop" / "JarvisProjects",
        _base_dir(),
    ]
    seen_paths = {ws.get("path") for ws in store["workspaces"].values()}
    for root in roots:
        if not root.exists():
            continue
        if str(root) not in seen_paths:
            add_workspace(root.name, str(root))
            store = load_store()
            seen_paths.add(str(root))
        if root.is_dir():
            for child in root.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    if str(child) not in seen_paths:
                        add_workspace(child.name, str(child))
                        store = load_store()
                        seen_paths.add(str(child))
    return list_workspaces()
