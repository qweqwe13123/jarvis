"""Account session: Google / API OAuth for the desktop app."""

from __future__ import annotations

import base64
import getpass
import hashlib
import json
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


ACCOUNT_PATH = _base_dir() / "memory" / "account.json"
SECRETS_PATH = _base_dir() / "memory" / "account_secrets.json"
API_KEYS_PATH = _base_dir() / "config" / "api_keys.json"

DEFAULT_API_BASE = "http://localhost:3000"
DEFAULT_WEB_BASE = "http://localhost:3000"


def _api_base() -> str:
    try:
        cfg = _base_dir() / "config" / "aura_cloud.json"
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return str(data.get("api_base_url") or DEFAULT_API_BASE).rstrip("/")
    except Exception:
        pass
    return DEFAULT_API_BASE


def _web_base() -> str:
    try:
        cfg = _base_dir() / "config" / "aura_cloud.json"
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


def get_display_name() -> str:
    data = _load_account()
    name = str(data.get("display_name", "")).strip()
    if name:
        return name
    email = str(data.get("email") or "").strip()
    if email:
        return email.split("@")[0]
    return getpass.getuser().replace(".", " ").replace("_", " ").title() or "User"


def get_plan() -> str:
    return str(_load_account().get("plan") or "free")


def get_subtitle(*, authenticated: bool | None = None) -> str:
    authed = is_authenticated() if authenticated is None else authenticated
    if not authed:
        return "Guest"
    plan = get_plan().replace("_", " ").title()
    return f"{plan} Plan"


def is_authenticated() -> bool:
    data = _load_account()
    if not data.get("authenticated"):
        return False
    # Desktop tokens from jarvis-saas /api/auth/desktop-code, or legacy FastAPI.
    if get_access_token():
        return True
    # Session flag alone (rare) — still treat as signed in if email present.
    return bool(data.get("email") or data.get("user_id"))


def sign_in(*, timeout: float = 300.0) -> bool:
    """
    Cursor-style: open the website login in the browser, wait for localhost
    handoff code, then exchange for desktop tokens via jarvis-saas.
    """
    from urllib.parse import urlencode

    verifier, challenge = _pkce_pair()

    result: dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            code = (qs.get("code") or [""])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code")
                return
            result["code"] = code
            account_url = f"{_web_base()}/account?desktop=linked"
            # Delay redirect a few seconds so Yandex Browser users can tap Allow
            # before the page navigates away (their prompt closes on fast nav).
            html = f"""<!doctype html>
<html><head>
<meta charset="utf-8"/>
<title>AURA signed in</title>
</head>
<body style="font-family:system-ui;background:#050a14;color:#e8f8ff;display:grid;place-items:center;min-height:100vh;margin:0">
<div style="text-align:center;max-width:28rem;padding:1.5rem">
  <h2 style="color:#00d1ff;margin:0 0 .75rem">AURA подключено</h2>
  <p style="color:#7eb8d4;margin:0 0 1rem">Если браузер спрашивает доступ — нажмите «Разрешить».</p>
  <p style="color:#5a8fa8;margin:0 0 1rem;font-size:13px">Через 4 секунды вернём на hiauraai.com…</p>
  <a href="{account_url}" style="color:#00d1ff">Открыть Account сейчас →</a>
</div>
<script>
  setTimeout(function() {{ location.replace({account_url!r}); }}, 4000);
</script>
</body></html>""".encode(
                "utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)
            done.set()
        def log_message(self, *_a):  # noqa: N802
            return

    httpd = None
    port = 8765
    for candidate in range(8765, 8785):
        try:
            httpd = HTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if httpd is None:
        raise RuntimeError("Could not bind localhost callback port")
    desktop_redirect = f"http://127.0.0.1:{port}/callback"

    thread = threading.Thread(target=httpd.handle_request, daemon=True)
    thread.start()

    # Next.js login (not legacy login.html)
    login_q = urlencode(
        {
            "from": "desktop",
            "next": "/account",
            "desktop_redirect": desktop_redirect,
            "code_challenge": challenge,
        }
    )
    webbrowser.open(f"{_web_base()}/login?{login_q}")

    deadline = time.time() + timeout
    while not done.is_set():
        if time.time() > deadline:
            httpd.server_close()
            raise TimeoutError(
                "Sign-in timed out. In the browser: click Connect AURA, allow access, "
                "then Continue to account."
            )
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass
        done.wait(0.05)

    httpd.server_close()
    code = result.get("code")
    if not code:
        raise RuntimeError("Sign-in failed: no code")

    # jarvis-saas: PUT /api/auth/desktop-code exchanges the one-time code
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
    """Sync plan from server when legacy refresh endpoints exist."""
    secrets = _load_secrets()
    access = secrets.get("access_token")
    refresh = secrets.get("refresh_token")
    if not access and not refresh:
        return None

    # Desktop stub tokens from Next.js don't support /me Bearer yet — keep local profile.
    if str(access or "").startswith("desktop_"):
        data = _load_account()
        if data.get("authenticated"):
            return {
                "id": data.get("user_id"),
                "email": data.get("email"),
                "name": data.get("display_name"),
                "plan": data.get("plan") or "free",
            }
        return None

    def _load_user(tok: str) -> dict:
        try:
            synced = _http_json("POST", "/billing/sync", body={}, token=tok)
            if isinstance(synced.get("user"), dict):
                return synced["user"]
        except Exception:
            pass
        return _http_json("GET", "/me", token=tok)

    try:
        if access:
            user = _load_user(str(access))
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


def sign_out() -> None:
    secrets = _load_secrets()
    refresh = secrets.get("refresh_token")
    try:
        if refresh and not str(refresh).startswith("desktop_"):
            _http_json("POST", "/auth/logout", body={"refresh_token": refresh})
    except Exception:
        pass
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


def open_billing_portal() -> None:
    """Open account / billing on the web (Stripe portal lives there)."""
    if is_authenticated():
        open_account()
    else:
        open_pricing()


def start_checkout(plan: str = "pro") -> None:
    webbrowser.open(f"{_web_base()}/pricing?plan={plan}")
