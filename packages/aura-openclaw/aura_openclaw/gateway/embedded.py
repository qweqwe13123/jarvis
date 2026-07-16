"""Embedded Aura Gateway — OpenClaw-compatible local WebSocket server."""
from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from aura_openclaw.gateway import protocol as proto

ChatHandler = Callable[[str, str, str], Awaitable[str] | str]
HistoryProvider = Callable[[str], list[dict[str, Any]]]


class AuraGateway:
    """Minimal OpenClaw protocol v4 gateway for A.U.R.A. desktop."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 18789,
        chat_handler: ChatHandler | None = None,
        history_provider: HistoryProvider | None = None,
        auth_token: str = "",
    ):
        self.host = host
        self.port = port
        self.chat_handler = chat_handler
        self.history_provider = history_provider
        self.auth_token = auth_token
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server = None
        self._histories: dict[str, list[dict[str, Any]]] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="AuraGateway")
        self._thread.start()

    def stop(self) -> None:
        if self._loop and self._server:
            asyncio.run_coroutine_threadsafe(self._server.close(), self._loop)

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())
        self._loop.run_forever()

    async def _serve(self) -> None:
        import websockets

        self._server = await websockets.serve(self._handle_client, self.host, self.port)
        print(f"[AuraGateway] listening on {self.url}")

    async def _handle_client(self, websocket) -> None:
        connected = False
        session_key = "main"
        try:
            challenge = proto.event("connect.challenge", {"nonce": proto.new_id(), "ts": 0})
            await websocket.send(challenge)

            async for raw in websocket:
                frame = proto.parse_frame(raw)
                if frame["type"] == "req":
                    req_id = frame["id"]
                    method = frame.get("method", "")
                    params = frame.get("params") or {}

                    if method == "connect":
                        token = (params.get("auth") or {}).get("token", "")
                        if self.auth_token and token != self.auth_token:
                            await websocket.send(proto.res(req_id, False, error="unauthorized"))
                            continue
                        connected = True
                        await websocket.send(proto.res(req_id, True, {
                            "type": "hello-ok",
                            "protocol": 4,
                            "server": {"version": "aura-openclaw/0.1.0"},
                            "features": {"methods": ["chat.send", "chat.history"], "events": ["chat"]},
                            "policy": {"maxPayload": 262144, "tickIntervalMs": 15000},
                            "auth": {"role": "operator", "scopes": ["operator.read", "operator.write"]},
                        }))
                        continue

                    if not connected:
                        await websocket.send(proto.res(req_id, False, error="not connected"))
                        continue

                    if method == "chat.history":
                        sk = params.get("sessionKey", session_key)
                        history = self._get_history(sk)
                        await websocket.send(proto.res(req_id, True, {"messages": history}))
                        continue

                    if method == "chat.send":
                        sk = params.get("sessionKey", session_key)
                        text = str(params.get("text", "")).strip()
                        if not text:
                            await websocket.send(proto.res(req_id, False, error="empty message"))
                            continue
                        reply = await self._dispatch_chat(sk, text)
                        self._append_history(sk, "user", text)
                        self._append_history(sk, "assistant", reply)
                        await websocket.send(proto.res(req_id, True, {"text": reply}))
                        await websocket.send(proto.event("chat", {
                            "sessionKey": sk,
                            "role": "assistant",
                            "text": reply,
                        }))
                        continue

                    await websocket.send(proto.res(req_id, False, error=f"unknown method: {method}"))
        except Exception as e:
            print(f"[AuraGateway] client error: {e}")

    async def _dispatch_chat(self, session_key: str, text: str) -> str:
        if not self.chat_handler:
            return "Gateway has no chat handler configured."
        result = self.chat_handler(session_key, "desktop", text)
        if asyncio.iscoroutine(result):
            return await result
        return str(result)

    def _get_history(self, session_key: str) -> list[dict[str, Any]]:
        if self.history_provider:
            return self.history_provider(session_key)
        return list(self._histories.get(session_key, []))

    def _append_history(self, session_key: str, role: str, text: str) -> None:
        self._histories.setdefault(session_key, []).append({"role": role, "text": text})
        self._histories[session_key] = self._histories[session_key][-40:]
