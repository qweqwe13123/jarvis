"""Talk to a local Ollama install (detect / list / pull / generate test)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PullProgress:
    """Live download progress from Ollama `/api/pull`."""

    status: str
    completed: int = 0  # bytes
    total: int = 0  # bytes
    fraction: float = -1.0  # 0..1, or -1 when unknown


ProgressCb = Callable[[PullProgress], None]


def format_bytes(n: int | float) -> str:
    """Human size: 420 MB, 1.25 GB."""
    n = max(0, int(n or 0))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    mb = n / (1024 * 1024)
    if mb < 1024:
        if mb < 10:
            return f"{mb:.1f} MB"
        return f"{mb:.0f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


def friendly_pull_status(raw: str) -> str:
    """Map Ollama stream statuses to short user-facing lines."""
    s = (raw or "").strip().lower()
    if not s:
        return "Preparing…"
    if "manifest" in s:
        return "Fetching model info…"
    if "pulling" in s and "manifest" not in s:
        return "Downloading layers…"
    if "downloading" in s:
        return "Downloading…"
    if "verif" in s:
        return "Verifying download…"
    if "writing" in s:
        return "Writing to disk…"
    if s in ("success", "done") or "success" in s:
        return "Finished"
    if len(raw) > 48:
        return raw[:45] + "…"
    return raw.strip()


@dataclass(frozen=True)
class OllamaStatus:
    binary_found: bool
    server_up: bool
    base_url: str
    models: list[str]
    message: str

    @property
    def ready(self) -> bool:
        return self.server_up


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        if self.base_url.endswith("/api/generate"):
            self.base_url = self.base_url[: -len("/api/generate")]

    def binary_path(self) -> str | None:
        return shutil.which("ollama")

    def install_page(self) -> str:
        return "https://ollama.com/download"

    def open_install_page(self) -> None:
        webbrowser.open(self.install_page())

    def _get_json(self, path: str, timeout: float = 3.0) -> dict | list | None:
        url = f"{self.base_url}{path}"
        try:
            req = Request(url, headers={"Accept": "application/json", "User-Agent": "AURA"})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def status(self) -> OllamaStatus:
        binary = self.binary_path() is not None
        data = self._get_json("/api/tags", timeout=2.5)
        if data is None:
            msg = (
                "Ollama is not running. Install it, then open the Ollama app."
                if not binary
                else "Ollama is installed but not running. Open the Ollama app."
            )
            return OllamaStatus(
                binary_found=binary,
                server_up=False,
                base_url=self.base_url,
                models=[],
                message=msg,
            )
        models: list[str] = []
        for m in (data.get("models") or []) if isinstance(data, dict) else []:
            name = str((m or {}).get("name") or "").strip()
            if name:
                models.append(name)
        return OllamaStatus(
            binary_found=binary or True,
            server_up=True,
            base_url=self.base_url,
            models=models,
            message="Ollama is ready" if models else "Ollama is running — download a model next",
        )

    def model_installed(self, model_id: str) -> bool:
        want = (model_id or "").strip().lower()
        if not want:
            return False
        st = self.status()
        for name in st.models:
            n = name.lower()
            if n == want:
                return True
            # Allow tag-less match: "llama3.2" matches "llama3.2:3b"
            if ":" not in want and n.split(":")[0] == want:
                return True
        return False

    def pull(
        self,
        model_id: str,
        *,
        on_progress: ProgressCb | None = None,
        cancel: threading.Event | None = None,
    ) -> tuple[bool, str]:
        """Download a model via Ollama HTTP API (streaming JSON lines)."""
        model_id = (model_id or "").strip()
        if not model_id:
            return False, "No model selected"
        st = self.status()
        if not st.server_up:
            return False, st.message

        url = f"{self.base_url}/api/pull"
        body = json.dumps({"name": model_id, "stream": True}).encode("utf-8")
        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/x-ndjson",
                "User-Agent": "AURA",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=600) as resp:
                last_status = "Downloading…"
                # Ollama reports each layer separately — sum digests for real MB.
                layers: dict[str, tuple[int, int]] = {}
                for raw in _iter_lines(resp):
                    if cancel is not None and cancel.is_set():
                        return False, "Cancelled"
                    try:
                        obj = json.loads(raw)
                    except Exception:
                        continue
                    status = str(obj.get("status") or last_status)
                    last_status = status
                    digest = str(obj.get("digest") or "").strip()
                    total = int(obj.get("total") or 0)
                    completed = int(obj.get("completed") or 0)
                    if digest and total > 0:
                        layers[digest] = (max(0, completed), total)

                    if layers:
                        use_done = sum(c for c, _t in layers.values())
                        use_total = sum(t for _c, t in layers.values())
                        frac = (use_done / use_total) if use_total > 0 else -1.0
                    elif total > 0:
                        use_done, use_total = completed, total
                        frac = completed / total
                    else:
                        use_done, use_total, frac = 0, 0, -1.0

                    if on_progress:
                        on_progress(
                            PullProgress(
                                status=status,
                                completed=use_done,
                                total=use_total,
                                fraction=frac,
                            )
                        )
                    if obj.get("error"):
                        return False, str(obj["error"])

            final_total = sum(t for _c, t in layers.values()) if layers else 0
            final_done = sum(c for c, _t in layers.values()) if layers else final_total
            if on_progress:
                on_progress(
                    PullProgress(
                        status="success",
                        completed=final_done or final_total,
                        total=final_total or final_done,
                        fraction=1.0,
                    )
                )
            size_note = format_bytes(final_total) if final_total else ""
            msg = f"Downloaded {model_id}"
            if size_note:
                msg = f"Downloaded {model_id} ({size_note})"
            return True, msg
        except HTTPError as e:
            return False, f"Download failed ({e.code})"
        except URLError as e:
            return False, f"Cannot reach Ollama: {e.reason}"
        except Exception as e:
            return False, str(e)[:200]

    def pull_via_cli(
        self,
        model_id: str,
        *,
        on_progress: ProgressCb | None = None,
    ) -> tuple[bool, str]:
        """Fallback: `ollama pull <model>` when HTTP pull is awkward."""
        exe = self.binary_path()
        if not exe:
            return False, "Ollama app not found"
        try:
            if on_progress:
                on_progress(PullProgress(status="Downloading…", fraction=-1.0))
            proc = subprocess.run(
                [exe, "pull", model_id],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "pull failed").strip()
                return False, err[:200]
            if on_progress:
                on_progress(PullProgress(status="success", fraction=1.0))
            return True, f"Downloaded {model_id}"
        except Exception as e:
            return False, str(e)[:200]

    def test_generate(self, model_id: str, timeout: float = 90.0) -> tuple[bool, str]:
        model_id = (model_id or "").strip()
        if not model_id:
            return False, "No model selected"
        url = f"{self.base_url}/api/generate"
        body = json.dumps(
            {
                "model": model_id,
                "prompt": "Say hi in one short sentence.",
                "stream": False,
            }
        ).encode("utf-8")
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "AURA"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = str(data.get("response") or "").strip()
            if not text:
                return False, "Empty reply from model"
            return True, text[:240]
        except Exception as e:
            return False, str(e)[:200]

    def try_start_app(self) -> bool:
        """Best-effort launch Ollama GUI / daemon."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(
                    ["open", "-a", "Ollama"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            if sys.platform == "win32":
                exe = self.binary_path()
                if exe:
                    subprocess.Popen(
                        [exe, "serve"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    return True
            exe = self.binary_path()
            if exe:
                subprocess.Popen(
                    [exe, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
        except Exception:
            pass
        return False


def _iter_lines(resp) -> Iterable[str]:
    buf = b""
    while True:
        chunk = resp.read(4096)
        if not chunk:
            if buf:
                yield buf.decode("utf-8", errors="replace")
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                yield text


_CLIENT: OllamaClient | None = None


def get_ollama_client(base_url: str | None = None) -> OllamaClient:
    global _CLIENT
    if base_url:
        return OllamaClient(base_url)
    if _CLIENT is None:
        from jarvis_ui.local_ai.prefs import load_prefs

        _CLIENT = OllamaClient(str(load_prefs().get("ollama_base_url") or ""))
    return _CLIENT
