"""Telegram channel — delegates to JARVIS telegram_control."""
from __future__ import annotations

from aura_openclaw.channels.base import OutboundMessage


class TelegramChannel:
    name = "telegram"

    def send(self, message: OutboundMessage) -> str:
        try:
            from actions.telegram_control import telegram_control
        except ImportError:
            return "telegram module unavailable"
        receiver = message.session_key.replace("telegram:", "", 1) or "contact"
        return telegram_control({
            "action": "message",
            "receiver": receiver,
            "message_text": message.text,
        })
