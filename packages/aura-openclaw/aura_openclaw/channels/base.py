"""Channel adapters — route inbound messages to the gateway."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

ProgressCb = Callable[[str], None]


@dataclass
class InboundMessage:
    channel: str
    session_key: str
    text: str
    sender: str = ""


@dataclass
class OutboundMessage:
    channel: str
    session_key: str
    text: str


class Channel(Protocol):
    name: str

    def send(self, message: OutboundMessage) -> str: ...
