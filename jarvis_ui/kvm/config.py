"""Generate Barrier / Input Leap server configuration text."""

from __future__ import annotations

import re

# Layout presets: where the *peer* screen sits relative to *this* (server) screen.
LAYOUTS: dict[str, tuple[str, str]] = {
    # peer_side -> (server_edge, peer_edge)
    "peer_right": ("right", "left"),
    "peer_left": ("left", "right"),
    "peer_below": ("down", "up"),
    "peer_above": ("up", "down"),
}

LAYOUT_LABELS = {
    "peer_right": "Peer on the right",
    "peer_left": "Peer on the left",
    "peer_below": "Peer below",
    "peer_above": "Peer above",
}


def sanitize_screen_name(raw: str, fallback: str = "screen") -> str:
    """Barrier screen names: letters, digits, underscore, hyphen; case-sensitive."""
    s = (raw or "").strip()
    s = s.replace(" ", "-")
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-_")
    if not s:
        s = fallback
    return s[:48]


def build_server_config(
    *,
    server_name: str,
    client_name: str,
    layout: str = "peer_right",
) -> str:
    """Two-screen config: keyboard/mouse on server_name."""
    srv = sanitize_screen_name(server_name, "server")
    cli = sanitize_screen_name(client_name, "client")
    if srv.lower() == cli.lower():
        cli = f"{cli}-peer"

    edges = LAYOUTS.get(layout) or LAYOUTS["peer_right"]
    srv_edge, cli_edge = edges

    # Tabs matter for some older parsers; use spaces consistently (accepted by both).
    lines = [
        "section: screens",
        f"\t{srv}:",
        f"\t{cli}:",
        "end",
        "",
        "section: links",
        f"\t{srv}:",
        f"\t\t{srv_edge} = {cli}",
        f"\t{cli}:",
        f"\t\t{cli_edge} = {srv}",
        "end",
        "",
        "section: options",
        "\trelativeMouseMoves = false",
        "\tscreenSaverSync = true",
        "\tclipboardSharing = true",
        "\tswitchCorners = none",
        "\tswitchCornerSize = 0",
        "end",
        "",
    ]
    return "\n".join(lines)
