"""Built-in skills shipped with aura-openclaw."""
from __future__ import annotations


def ping(**kwargs) -> str:
    return "pong"


def echo(text: str = "", **kwargs) -> str:
    return text or "empty"
