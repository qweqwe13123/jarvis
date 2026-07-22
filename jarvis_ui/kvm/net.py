"""LAN helpers for KVM peer addressing."""

from __future__ import annotations

import socket


def local_lan_ip() -> str:
    """Best-effort primary LAN IPv4 (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets sent — OS picks the outbound interface for this route.
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return ""


def looks_like_host(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if "://" in v:
        return False
    # host or host:port
    host = v.rsplit(":", 1)[0] if v.count(":") == 1 and not v.startswith("[") else v
    if host.startswith("[") and "]" in host:
        return True
    return bool(host) and " " not in host
