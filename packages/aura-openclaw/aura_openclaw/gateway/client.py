"""Client for official OpenClaw Node gateway."""
from __future__ import annotations

import asyncio
from typing import Any

from aura_openclaw.gateway import protocol as proto


class OpenClawClient:
    def __init__(self, url: str, auth_token: str = ""):
        self.url = url
        self.auth_token = auth_token
        self._ws = None
        self._connected = False

    async def connect(self) -> None:
        import websockets

        self._ws = await websockets.connect(self.url)
        async for raw in self._ws:
            frame = proto.parse_frame(raw)
            if frame.get("type") == "event" and frame.get("event") == "connect.challenge":
                req_id = proto.new_id()
                await self._ws.send(proto.req("connect", {
                    "minProtocol": 4,
                    "maxProtocol": 4,
                    "client": {"id": "aura", "version": "0.1.0", "platform": "desktop", "mode": "operator"},
                    "role": "operator",
                    "scopes": ["operator.read", "operator.write"],
                    "auth": {"token": self.auth_token} if self.auth_token else {},
                }, req_id))
            elif frame.get("type") == "res" and frame.get("ok"):
                payload = frame.get("payload") or {}
                if payload.get("type") == "hello-ok":
                    self._connected = True
                    return
            break
        if not self._connected:
            raise RuntimeError("OpenClaw handshake failed")

    async def chat_send(self, text: str, session_key: str = "main", timeout: float = 120.0) -> str:
        if not self._ws or not self._connected:
            raise RuntimeError("not connected")
        req_id = proto.new_id()
        await self._ws.send(proto.req("chat.send", {"sessionKey": session_key, "text": text}, req_id))

        parts: list[str] = []
        try:
            async with asyncio.timeout(timeout):
                async for raw in self._ws:
                    frame = proto.parse_frame(raw)
                    ftype = frame.get("type")

                    if ftype == "res" and frame.get("id") == req_id:
                        if not frame.get("ok"):
                            err = (frame.get("error") or {}).get("message", "chat.send failed")
                            raise RuntimeError(err)
                        payload = frame.get("payload") or {}
                        direct = payload.get("text") or payload.get("content")
                        if direct:
                            return str(direct)
                        if parts:
                            return "".join(parts)
                        return ""

                    if ftype == "event":
                        event = frame.get("event") or ""
                        payload = frame.get("payload") or {}
                        if event in ("chat.delta", "chat.stream", "message.delta"):
                            chunk = payload.get("text") or payload.get("delta") or payload.get("content")
                            if chunk:
                                parts.append(str(chunk))
                        elif event in ("chat.done", "chat.final", "message.done"):
                            final = payload.get("text") or payload.get("content")
                            if final:
                                return str(final)
                            if parts:
                                return "".join(parts)
                            return ""
        except TimeoutError as exc:
            if parts:
                return "".join(parts)
            raise RuntimeError("chat.send timed out") from exc

        if parts:
            return "".join(parts)
        raise RuntimeError("no response from gateway")

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
            self._connected = False
