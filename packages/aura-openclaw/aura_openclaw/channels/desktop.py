"""Desktop channel — PyQt UI is the primary surface."""
from __future__ import annotations

from typing import Callable

from aura_openclaw.channels.base import OutboundMessage


class DesktopChannel:
    name = "desktop"

    def __init__(self, emit: Callable[[str], None] | None = None):
        self._emit = emit

    def send(self, message: OutboundMessage) -> str:
        if self._emit:
            self._emit(message.text)
        return "delivered"
