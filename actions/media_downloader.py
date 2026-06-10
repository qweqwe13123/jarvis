import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _detect_platform(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "instagram.com" in host:
        return "instagram"
    if "tiktok.com" in host:
        return "tiktok"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    return "web"


def _target_dir(path_text: str) -> Path:
    if not path_text:
        return Path.home() / "Downloads"
    p = Path(path_text).expanduser()
    if "рабоч" in path_text.lower() or "desktop" in path_text.lower():
        p = Path.home() / "Desktop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def media_downloader(parameters: dict[str, Any], response=None, player=None):
    params = parameters or {}
    url = str(params.get("url") or params.get("link") or "").strip()
    quality = str(params.get("quality") or "best").strip().lower()
    save_to = str(params.get("save_to") or params.get("folder") or "").strip()
    if not url or not re.match(r"^https?://", url, flags=re.I):
        return "Please provide a valid URL."

    target = _target_dir(save_to)
    platform = _detect_platform(url)
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return "yt-dlp is not installed. Install it: pip install yt-dlp"

    fmt = "best"
    if quality in {"audio", "mp3"}:
        fmt = "bestaudio"
    elif quality in {"720p", "1080p", "480p"}:
        h = quality.replace("p", "")
        fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"

    cmd = [ytdlp, "-f", fmt, "-P", str(target), url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        return "Download timed out."

    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-300:]
        return f"Download failed for {platform}: {tail}"

    return f"Downloaded from {platform} to {target}."
