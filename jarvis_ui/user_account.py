"""Account session: Google / API OAuth for the desktop app."""

from __future__ import annotations

import base64
import getpass
import hashlib
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from jarvis_ui.paths import cloud_config_path, data_dir, support_dir


def _base_dir() -> Path:
    """Writable data root (Application Support when frozen)."""
    return data_dir()


ACCOUNT_PATH = data_dir() / "memory" / "account.json"
SECRETS_PATH = data_dir() / "memory" / "account_secrets.json"
API_KEYS_PATH = data_dir() / "config" / "api_keys.json"

# Deep-link inbox (aura://auth?code=…) — Cursor-style, no localhost UX.
_SUPPORT_DIR = support_dir()
AUTH_INBOX_PATH = _SUPPORT_DIR / "auth_inbox.json"

# Production defaults — never silently talk to localhost in a shipped build.
DEFAULT_API_BASE = "https://www.hiauraai.com"
DEFAULT_WEB_BASE = "https://www.hiauraai.com"


def _api_base() -> str:
    try:
        cfg = cloud_config_path()
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return str(data.get("api_base_url") or DEFAULT_API_BASE).rstrip("/")
    except Exception:
        pass
    return DEFAULT_API_BASE


def _web_base() -> str:
    try:
        cfg = cloud_config_path()
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return str(data.get("web_base_url") or DEFAULT_WEB_BASE).rstrip("/")
    except Exception:
        pass
    return DEFAULT_WEB_BASE


def _load_account() -> dict:
    if not ACCOUNT_PATH.exists():
        return {}
    try:
        return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_account(data: dict) -> None:
    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_secrets(data: dict) -> None:
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        SECRETS_PATH.chmod(0o600)
    except Exception:
        pass


def _has_api_keys() -> bool:
    if not API_KEYS_PATH.exists():
        return False
    try:
        data = json.loads(API_KEYS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    for key in (
        "gemini_api_key",
        "openai_api_key",
        "openrouter_api_key",
        "groq_api_key",
        "deepseek_api_key",
        "together_api_key",
    ):
        if str(data.get(key, "")).strip():
            return True
    return False


def _http_json(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    url = f"{_api_base()}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API {method} {path} failed ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach AURA at {_api_base()}. "
            f"Start the site (jarvis-saas: npm run dev) or set config/aura_cloud.json. ({e})"
        ) from e


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _write_auth_inbox(code: str) -> None:
    try:
        AUTH_INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTH_INBOX_PATH.write_text(
            json.dumps({"code": code, "ts": time.time()}),
            encoding="utf-8",
        )
        try:
            AUTH_INBOX_PATH.chmod(0o600)
        except Exception:
            pass
    except Exception:
        pass


def take_auth_inbox_code(*, max_age: float = 600.0) -> str | None:
    """Consume a one-time code delivered via aura:// deep link."""
    if not AUTH_INBOX_PATH.exists():
        return None
    try:
        data = json.loads(AUTH_INBOX_PATH.read_text(encoding="utf-8"))
        AUTH_INBOX_PATH.unlink(missing_ok=True)
        code = str(data.get("code") or "").strip()
        ts = float(data.get("ts") or 0)
        if not code or (time.time() - ts) > max_age:
            return None
        return code
    except Exception:
        try:
            AUTH_INBOX_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def handle_aura_deep_link(url: str) -> bool:
    """Parse aura://auth?code=… and stash for sign_in() / exchange."""
    from urllib.parse import parse_qs, unquote, urlparse

    raw = (url or "").strip()
    if not raw.lower().startswith("aura:"):
        return False
    try:
        parsed = urlparse(raw)
        # aura://auth?code=… or aura:auth?code=…
        qs = parse_qs(parsed.query)
        code = (qs.get("code") or [""])[0]
        if not code and parsed.path:
            # aura://auth/CODE rare form
            parts = [p for p in parsed.path.split("/") if p]
            if parts and parts[0] != "auth":
                code = parts[-1]
        code = unquote(code or "").strip()
        if not code:
            return False
        _write_auth_inbox(code)
        return True
    except Exception:
        return False


_deep_link_filter = None
_update_gui_bridge = None


def install_update_controller_fix() -> None:
    """Ensure update UI is opened only on the Qt GUI thread (macOS crash fix).

    Crash was: worker thread → QDialog.open() → NSWindow off-main-thread → SIGABRT.
    Bake-time UpdateController may still call `_on_state` from a worker; marshal it.
    """
    global _update_gui_bridge
    try:
        from PyQt6.QtCore import QObject, pyqtSignal
        from PyQt6.QtWidgets import QApplication
        from core.updater.controller import UpdateController
    except Exception:
        return

    if getattr(UpdateController, "_aura_gui_thread_fixed", False):
        return

    app = QApplication.instance()
    if app is None:
        return

    class _UpdateGuiBridge(QObject):
        open_update = pyqtSignal(object, object)  # controller, state

        def __init__(self) -> None:
            super().__init__()
            self.open_update.connect(self._open)

        def _open(self, controller, state) -> None:  # noqa: ANN001
            if state is None or not getattr(state, "release", None):
                return
            if getattr(state, "downloading", False):
                return
            if getattr(controller, "_dialog", None) is not None:
                return
            try:
                from jarvis_ui.update_dialog import UpdateDialog
            except Exception:
                return
            pid = getattr(controller, "_parent_pid", None)
            if pid is None:
                pid = getattr(controller, "_pid", 0)
            window = getattr(controller, "_window", None)
            service = getattr(controller, "_service", None)
            if service is None:
                return
            dialog = UpdateDialog(service, int(pid or 0), parent=window)
            controller._dialog = dialog
            clear = getattr(controller, "_clear_dialog", None)
            if callable(clear):
                dialog.finished.connect(clear)
            else:
                dialog.finished.connect(lambda *_: setattr(controller, "_dialog", None))
            dialog.open()

    if _update_gui_bridge is None:
        _update_gui_bridge = _UpdateGuiBridge()
        _update_gui_bridge.moveToThread(app.thread())

    bridge = _update_gui_bridge

    def _on_state(self, state) -> None:  # noqa: ANN001
        # Queued to GUI thread even when called from a worker.
        bridge.open_update.emit(self, state)

    def _on_state_main(self, state) -> None:  # noqa: ANN001
        bridge.open_update.emit(self, state)

    UpdateController._on_state = _on_state  # type: ignore[method-assign]
    UpdateController._on_state_main = _on_state_main  # type: ignore[attr-defined]
    UpdateController._aura_gui_thread_fixed = True  # type: ignore[attr-defined]

    # Marshal UpdateService listener callbacks onto the GUI thread.
    try:
        from core.updater.service import UpdateService

        if not getattr(UpdateService, "_aura_emit_main_thread", False):

            class _EmitBridge(QObject):
                dispatch = pyqtSignal(object)

                def __init__(self) -> None:
                    super().__init__()
                    self.dispatch.connect(self._run)

                def _run(self, fn) -> None:  # noqa: ANN001
                    try:
                        fn()
                    except Exception:
                        pass

            emit_bridge = _EmitBridge()
            emit_bridge.moveToThread(app.thread())

            def _emit_main(self) -> None:  # noqa: ANN001
                snapshot = self.state
                listeners = list(self._listeners)

                def _run() -> None:
                    for cb in listeners:
                        try:
                            cb(snapshot)
                        except Exception:
                            pass

                emit_bridge.dispatch.emit(_run)

            UpdateService._emit = _emit_main  # type: ignore[method-assign]
            UpdateService._aura_emit_main_thread = True  # type: ignore[attr-defined]
    except Exception:
        pass


def install_deep_link_handler() -> None:
    """Install QFileOpenEvent filter so aura:// opens while AURA is running."""
    global _deep_link_filter
    try:
        install_update_controller_fix()
    except Exception:
        pass
    try:
        from PyQt6.QtCore import QEvent, QObject
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return

    app = QApplication.instance()
    if app is None:
        return

    # Cold-start: macOS may pass the URL on argv.
    for arg in sys.argv[1:]:
        if isinstance(arg, str) and arg.lower().startswith("aura:"):
            handle_aura_deep_link(arg)

    if _deep_link_filter is not None:
        return

    class _AuraUrlFilter(QObject):
        def eventFilter(self, _obj, event):  # noqa: N802
            try:
                if event.type() == QEvent.Type.FileOpen:
                    handle_aura_deep_link(event.url().toString())
                    return True
            except Exception:
                pass
            return False

    _deep_link_filter = _AuraUrlFilter(app)
    app.installEventFilter(_deep_link_filter)


def _apply_profile(user: dict[str, Any] | None) -> None:
    if not user:
        return
    data = _load_account()
    data["authenticated"] = True
    data["user_id"] = user.get("id")
    data["email"] = user.get("email")
    if user.get("name"):
        data["display_name"] = user["name"]
    elif user.get("email") and not data.get("display_name"):
        data["display_name"] = str(user["email"]).split("@")[0]
    data["avatar_url"] = user.get("avatar_url") or user.get("picture") or ""
    data["plan"] = user.get("plan") or "free"
    data["status"] = user.get("status") or "active"
    data["current_period_end"] = user.get("current_period_end")
    data["synced_at"] = time.time()
    data.pop("local_only", None)
    _save_account(data)
    try:
        from core.usage_manager import set_tier_from_server

        set_tier_from_server(str(user.get("plan") or "free"))
    except Exception:
        pass


def _store_tokens(access: str, refresh: str = "") -> None:
    _save_secrets(
        {
            "access_token": access,
            "refresh_token": refresh or "",
            "updated_at": time.time(),
        }
    )


def get_access_token() -> str | None:
    return str(_load_secrets().get("access_token") or "") or None


def get_email() -> str:
    return str(_load_account().get("email") or "").strip()


def get_display_name() -> str:
    """Account name when signed in. Empty string for guests (UI shows “Sign in”)."""
    if not is_authenticated():
        return ""
    data = _load_account()
    name = str(data.get("display_name", "")).strip()
    if name:
        return name
    email = get_email()
    if email:
        return email.split("@")[0]
    return "User"


def get_avatar_url() -> str:
    """Google / account profile photo URL when signed in."""
    if not is_authenticated():
        return ""
    data = _load_account()
    return str(data.get("avatar_url") or data.get("picture") or "").strip()


def get_plan() -> str:
    return str(_load_account().get("plan") or "free").lower()


def has_active_subscription() -> bool:
    """True when the cloud account has a paid plan (Pro / Team / Enterprise)."""
    return get_plan() in ("pro", "team", "enterprise")


def get_subtitle(*, authenticated: bool | None = None) -> str:
    authed = is_authenticated() if authenticated is None else authenticated
    if not authed:
        return ""
    email = get_email()
    if email:
        return email
    if not has_active_subscription():
        return "Free plan"
    plan = get_plan().replace("_", " ").title()
    return f"{plan} plan"


def is_authenticated() -> bool:
    data = _load_account()
    if not data.get("authenticated"):
        return False
    # Desktop tokens from jarvis-saas /api/auth/desktop-code, or legacy FastAPI.
    if get_access_token():
        return True
    # Session flag alone (rare) — still treat as signed in if email present.
    return bool(data.get("email") or data.get("user_id"))


def _open_browser(url: str) -> None:
    """Open URL reliably on macOS (webbrowser.open can silently no-op)."""
    import subprocess

    url = (url or "").strip()
    if not url:
        raise RuntimeError("Sign-in failed: empty verification URL")
    opened = False
    if sys.platform == "darwin":
        try:
            subprocess.run(["open", url], check=False, timeout=8)
            opened = True
        except Exception:
            opened = False
    if not opened:
        try:
            opened = bool(webbrowser.open(url, new=2))
        except Exception:
            opened = False
    if not opened and sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-a", "Safari", url])
            opened = True
        except Exception:
            pass
    if not opened:
        raise RuntimeError(
            f"Could not open the browser. Open this link manually:\n{url}"
        )


def sign_in(
    *,
    timeout: float = 180.0,
    pump_events: bool = False,
    cancel_event: Any | None = None,
    is_current: Any | None = None,
    on_browser_opened: Any | None = None,
) -> bool:
    """
    Cursor-style domain login: browser stays on hiauraai.com, then opens
    aura://auth?code=… (or we poll the domain API as a backup).

    Prefer running via ``jarvis_ui.auth_async.SignInWorker`` so the UI thread
    never blocks. Pass ``is_current`` / ``cancel_event`` so a new Sign in can
    abort a stuck previous attempt.
    """
    install_deep_link_handler()
    take_auth_inbox_code()  # clear stale

    def _cancelled() -> bool:
        if cancel_event is not None and cancel_event.is_set():
            return True
        if callable(is_current):
            try:
                return not bool(is_current())
            except Exception:
                return False
        return False

    if _cancelled():
        raise RuntimeError("Sign-in cancelled.")

    verifier, challenge = _pkce_pair()

    try:
        start = _http_json(
            "POST",
            "/api/auth/device/start",
            body={"challenge": challenge},
        )
    except Exception as e:
        raise RuntimeError(
            f"Could not start domain login on {_web_base()}. "
            f"Check that the site is online and DATABASE_URL is configured. ({e})"
        ) from e

    if _cancelled():
        raise RuntimeError("Sign-in cancelled.")

    device_id = str(start.get("device_id") or "")
    device_secret = str(start.get("device_secret") or "")
    verify_url = str(
        start.get("verification_uri_complete")
        or f"{_web_base()}/auth/desktop?device_id={device_id}&challenge={challenge}"
    )
    if not device_id or not device_secret:
        raise RuntimeError("Sign-in failed: invalid device session from server")

    interval = max(1.0, float(start.get("interval") or 2))
    _open_browser(verify_url)
    if callable(on_browser_opened):
        try:
            on_browser_opened(verify_url)
        except Exception:
            pass

    code = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _cancelled():
            raise RuntimeError("Sign-in cancelled. Tap Sign in again.")

        if pump_events:
            try:
                from PyQt6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
            except Exception:
                pass

        # Prefer deep-link handoff (aura://) over poll.
        inbox = take_auth_inbox_code()
        if inbox:
            code = inbox
            break

        try:
            poll = _http_json(
                "POST",
                "/api/auth/device/poll",
                body={"device_id": device_id, "device_secret": device_secret},
            )
        except RuntimeError as e:
            msg = str(e)
            if "403" in msg:
                raise RuntimeError("Desktop login denied.") from e
            if "410" in msg or "expired" in msg.lower():
                raise TimeoutError(
                    "Sign-in expired. Open Sign In from AURA again."
                ) from e
            # Brief sleep in slices so cancel reacts quickly.
            end = time.time() + interval
            while time.time() < end:
                if _cancelled():
                    raise RuntimeError("Sign-in cancelled. Tap Sign in again.")
                time.sleep(min(0.25, end - time.time()))
            continue

        status = str(poll.get("status") or "")
        if status == "ready" and poll.get("code"):
            code = str(poll["code"])
            break
        if status in ("expired", "denied"):
            raise RuntimeError(f"Sign-in {status}. Try Sign In again from AURA.")
        end = time.time() + interval
        while time.time() < end:
            if _cancelled():
                raise RuntimeError("Sign-in cancelled. Tap Sign in again.")
            time.sleep(min(0.25, end - time.time()))

    if _cancelled():
        raise RuntimeError("Sign-in cancelled. Tap Sign in again.")

    if not code:
        raise TimeoutError(
            "Sign-in timed out. Tap Sign in again to reopen the website, "
            "then click Yes, Log In on hiauraai.com."
        )

    tokens = _http_json(
        "PUT",
        "/api/auth/desktop-code",
        body={"code": code, "code_verifier": verifier},
    )
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token") or ""
    if not access:
        raise RuntimeError("Sign-in failed: missing tokens from server")
    _store_tokens(str(access), str(refresh))
    user = tokens.get("user") if isinstance(tokens.get("user"), dict) else {}
    if not user.get("name") and user.get("email"):
        user = {**user, "name": str(user["email"]).split("@")[0]}
    _apply_profile(user)
    try:
        refresh_entitlements()
    except Exception:
        pass
    return True


def refresh_entitlements() -> dict[str, Any] | None:
    """Sync live plan from jarvis-saas /api/auth/me (after website Checkout)."""
    secrets = _load_secrets()
    access = str(secrets.get("access_token") or "")
    refresh = str(secrets.get("refresh_token") or "")
    if not access and not refresh:
        return None

    # Legacy stub tokens cannot call /me — force a clean sign-in next time.
    if access.startswith("desktop_") or refresh.startswith("desktop_refresh_"):
        return {
            "id": _load_account().get("user_id"),
            "email": _load_account().get("email"),
            "name": _load_account().get("display_name"),
            "plan": _load_account().get("plan") or "free",
            "needs_reauth": True,
        }

    def _load_user(tok: str) -> dict:
        try:
            me = _http_json("GET", "/api/auth/me", token=tok)
            if isinstance(me.get("user"), dict):
                user = dict(me["user"])
                if me.get("plan"):
                    user["plan"] = me["plan"]
                return user
        except Exception:
            pass
        try:
            synced = _http_json("POST", "/billing/sync", body={}, token=tok)
            if isinstance(synced.get("user"), dict):
                return synced["user"]
        except Exception:
            pass
        return _http_json("GET", "/me", token=tok)

    try:
        if access:
            user = _load_user(access)
            _apply_profile(user)
            return user
    except Exception:
        pass

    if refresh:
        try:
            renewed = _http_json("POST", "/auth/refresh", body={"refresh_token": refresh})
            new_access = renewed.get("access_token")
            if new_access:
                secrets["access_token"] = new_access
                secrets["updated_at"] = time.time()
                _save_secrets(secrets)
                user = _load_user(str(new_access))
                _apply_profile(user)
                return user
        except Exception:
            pass
    return None


def ensure_paid_access(*, sync: bool = True) -> tuple[bool, str]:
    """Returns (ok, reason). When sync=True, refresh plan from the website first."""
    if not is_authenticated() or not get_access_token():
        return False, "sign_in"
    if sync:
        try:
            refresh_entitlements()
        except Exception:
            pass
    if has_active_subscription():
        return True, "ok"
    return False, "upgrade"


def sign_out(*, revoke_remote_async: bool = True) -> None:
    """Clear local session immediately. Optionally revoke refresh token off-thread."""
    import threading

    secrets = _load_secrets()
    refresh = secrets.get("refresh_token")

    # Local clear first — UI must feel instant.
    _save_secrets({})
    data = _load_account()
    data["authenticated"] = False
    data.pop("user_id", None)
    data.pop("email", None)
    data.pop("plan", None)
    data.pop("status", None)
    data.pop("local_only", None)
    data.pop("display_name", None)
    data.pop("avatar_url", None)
    _save_account(data)
    try:
        from core.usage_manager import set_tier_from_server

        set_tier_from_server("free")
    except Exception:
        pass

    def _revoke() -> None:
        try:
            if refresh and not str(refresh).startswith("desktop_"):
                _http_json("POST", "/auth/logout", body={"refresh_token": refresh})
        except Exception:
            pass

    if refresh and not str(refresh).startswith("desktop_"):
        if revoke_remote_async:
            threading.Thread(target=_revoke, daemon=True, name="AuraSignOut").start()
        else:
            _revoke()


def create_account(display_name: str = "") -> None:
    """Legacy create_account → start real sign-in (name applied after)."""
    if display_name.strip():
        data = _load_account()
        data["display_name"] = display_name.strip()
        _save_account(data)
    sign_in()


def continue_local() -> None:
    """Mark guest local path (no cloud account)."""
    data = _load_account()
    data["authenticated"] = False
    data["local_only"] = True
    data["plan"] = "free"
    _save_account(data)
    try:
        from core.usage_manager import set_tier_from_server

        set_tier_from_server("free")
    except Exception:
        pass


def open_pricing() -> None:
    webbrowser.open(f"{_web_base()}/pricing")


def open_account() -> None:
    webbrowser.open(f"{_web_base()}/account")


def open_support() -> None:
    """Help & Support — docs / contact on the website."""
    webbrowser.open(f"{_web_base()}/support")


def open_referral() -> None:
    """Referral program dashboard on the website."""
    webbrowser.open(f"{_web_base()}/referral")


def open_billing_portal() -> None:
    """Open account / billing on the web (Stripe portal lives there)."""
    if is_authenticated():
        open_account()
    else:
        open_pricing()


def start_checkout(plan: str = "pro") -> None:
    webbrowser.open(f"{_web_base()}/pricing?plan={plan}")
