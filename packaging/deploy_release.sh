#!/bin/zsh
# Upload local notarized macOS DMG, sync all GitHub Release assets into
# jarvis-saas public/releases/manifest.json, and push (Vercel).
set -euo pipefail

ROOT="/Users/khalilisaiev/jarvis122"
SAAS="/Users/khalilisaiev/jarvis-saas"
ENVF="$SAAS/.env.deploy"
OWNER="qweqwe13123"
REPO="jarvis"

PY="$ROOT/.venv/bin/python3.13"
VERSION="$("$PY" "$ROOT/packaging/print_version.py")"
ARCH="$(uname -m)"
[[ "$ARCH" == "arm64" ]] || ARCH="x64"
TAG="v${VERSION}"
# Prefer universal DMG when present (one package for Apple Silicon + Intel).
if [[ -f "$ROOT/dist/releases/AURA-${VERSION}-macos-universal.dmg" ]]; then
  ARCH="universal"
fi
DMG="$ROOT/dist/releases/AURA-${VERSION}-macos-${ARCH}.dmg"
ZIP="$ROOT/dist/releases/AURA-${VERSION}-macos-${ARCH}.zip"
LOCAL_MANIFEST="$ROOT/dist/releases/manifest.json"

if [ ! -f "$ENVF" ]; then
  echo "Missing $ENVF"
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENVF"
set +a

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "GITHUB_TOKEN empty in .env.deploy"
  exit 1
fi

export GH_TOKEN="$GITHUB_TOKEN"

NOTES_DEFAULT="$(cat <<EOF
## What's new in ${VERSION}

- A refined desktop experience across macOS, Windows, and Linux
- Smoother wake and everyday interactions
- Performance and reliability improvements
- Important bug fixes under the hood
EOF
)"

echo "=== Ensure GitHub release $TAG ==="
if ! gh release view "$TAG" --repo "$OWNER/$REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$OWNER/$REPO" --title "AURA $VERSION" --notes "$NOTES_DEFAULT"
fi

# Cursor-style blockmap for differential in-app updates (zip only).
BLOCKMAP=""
if [ -f "$ZIP" ]; then
  echo "=== Generate update blockmap for $ZIP ==="
  BLOCKMAP="${ZIP}.blockmap"
  "$PY" "$ROOT/packaging/make_blockmap.py" "$ZIP" -o "$BLOCKMAP"
fi

if [ -f "$DMG" ]; then
  echo "=== Upload local macOS assets ==="
  UPLOAD_ARGS=("$DMG")
  [[ -f "$ZIP" ]] && UPLOAD_ARGS+=("$ZIP")
  [[ -f "$BLOCKMAP" ]] && UPLOAD_ARGS+=("$BLOCKMAP")
  [[ -f "$LOCAL_MANIFEST" ]] && UPLOAD_ARGS+=("$LOCAL_MANIFEST")
  gh release upload "$TAG" "${UPLOAD_ARGS[@]}" --repo "$OWNER/$REPO" --clobber
else
  echo "No local DMG at $DMG — syncing whatever is already on the GitHub release."
  if [[ -f "$ZIP" && -f "$BLOCKMAP" ]]; then
    echo "=== Upload zip + blockmap ==="
    gh release upload "$TAG" "$ZIP" "$BLOCKMAP" --repo "$OWNER/$REPO" --clobber
  fi
fi

echo "=== Rebuild site manifest from GitHub release assets ==="
"$PY" - <<PY
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path("$ROOT")
saas = Path("$SAAS") / "public" / "releases" / "manifest.json"
version = "$VERSION"
tag = "$TAG"
owner = "$OWNER"
repo = "$REPO"
token = os.environ["GITHUB_TOKEN"]
base = f"https://github.com/{owner}/{repo}/releases/download/{tag}"

notes = """$NOTES_DEFAULT"""
local_manifest = root / "dist" / "releases" / "manifest.json"
if local_manifest.exists():
    try:
        notes = json.loads(local_manifest.read_text()).get("notes") or notes
    except Exception:
        pass

api = subprocess.check_output(
    ["gh", "api", f"repos/{owner}/{repo}/releases/tags/{tag}"],
    text=True,
)
rel = json.loads(api)
assets = {a["name"]: a for a in rel.get("assets") or []}

def classify(name: str):
    # Returns list of (platform_key, role) — universal maps to both Mac keys.
    if not name.startswith(f"AURA-{version}-"):
        return []
    if name.endswith("-macos-universal.dmg"):
        return [("darwin-arm64", "primary"), ("darwin-x64", "primary"), ("darwin-universal", "primary")]
    if name.endswith("-macos-universal.zip"):
        return [("darwin-arm64", "update"), ("darwin-x64", "update"), ("darwin-universal", "update")]
    if name.endswith("-macos-arm64.dmg"):
        return [("darwin-arm64", "primary")]
    if name.endswith("-macos-arm64.zip"):
        return [("darwin-arm64", "update")]
    if name.endswith("-macos-x64.dmg"):
        return [("darwin-x64", "primary")]
    if name.endswith("-macos-x64.zip"):
        return [("darwin-x64", "update")]
    if name.endswith("-win-x64.exe"):
        return [("win-x64", "primary")]
    if name.endswith("-win-x64.zip"):
        return [("win-x64", "update")]
    if name.endswith("-linux-x64.AppImage"):
        return [("linux-x64", "primary")]
    if name.endswith("-linux-x64.zip"):
        # Prefer AppImage as primary when both exist.
        return [("linux-x64", "update")]
    return []

def sha_of_url(url: str, size: int) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream",
            "User-Agent": "aura-deploy",
        },
    )
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=600) as resp:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()

def attach_blockmap(entry: dict, package_name: str, *, prefix: str = "update_blockmap") -> None:
    """Attach Cursor-style blockmap fields when <package>.blockmap exists on the release or locally."""
    bm_name = f"{package_name}.blockmap"
    bm_url = f"{base}/{bm_name}"
    local_bm = root / "dist" / "releases" / bm_name
    # Also accept path next to ZIP from this deploy.
    alt_bm = Path("$BLOCKMAP") if "$BLOCKMAP" else Path()
    url_key = f"{prefix}_url"
    sha_key = f"{prefix}_sha256"
    size_key = f"{prefix}_size"
    if local_bm.is_file():
        entry[url_key] = bm_url
        entry[sha_key] = sha_file(local_bm)
        entry[size_key] = local_bm.stat().st_size
        return
    if str(alt_bm) and alt_bm.is_file() and alt_bm.name == bm_name:
        entry[url_key] = bm_url
        entry[sha_key] = sha_file(alt_bm)
        entry[size_key] = alt_bm.stat().st_size
        return
    if bm_name in assets:
        a = assets[bm_name]
        digest = (a.get("digest") or "").removeprefix("sha256:")
        size = int(a.get("size") or 0)
        if not digest:
            print(f"hashing {bm_name} ({size} bytes)...")
            digest = sha_of_url(a["url"], size)
        entry[url_key] = bm_url
        entry[sha_key] = digest
        entry[size_key] = size

platforms: dict = {}
for name, asset in assets.items():
    mapped = classify(name)
    if not mapped:
        continue
    url = f"{base}/{name}"
    digest = (asset.get("digest") or "").removeprefix("sha256:")
    size = int(asset.get("size") or 0)
    if not digest:
        print(f"hashing {name} ({size} bytes)...")
        digest = sha_of_url(asset["url"], size)
    for key, role in mapped:
        entry = platforms.setdefault(key, {})
        if role == "primary":
            entry.update({"url": url, "sha256": digest, "size": size, "filename": name})
            # Linux AppImage is itself the live update payload.
            if name.lower().endswith(".appimage"):
                attach_blockmap(entry, name, prefix="blockmap")
        else:
            entry.update(
                {
                    "update_filename": name,
                    "update_url": url,
                    "update_sha256": digest,
                    "update_size": size,
                }
            )
            if name.lower().endswith(".zip"):
                attach_blockmap(entry, name, prefix="update_blockmap")

# Prefer local notarized DMG hashes when present (authoritative).
dmg = Path("$DMG")
zpath = Path("$ZIP")
if dmg.is_file():
    arch = "$ARCH"
    keys = (
        ["darwin-arm64", "darwin-x64", "darwin-universal"]
        if arch == "universal"
        else [f"darwin-{arch}"]
    )
    primary = {
        "url": f"{base}/AURA-{version}-macos-{arch}.dmg",
        "sha256": sha_file(dmg),
        "size": dmg.stat().st_size,
        "filename": f"AURA-{version}-macos-{arch}.dmg",
    }
    if zpath.is_file():
        zname = f"AURA-{version}-macos-{arch}.zip"
        primary.update(
            {
                "update_filename": zname,
                "update_url": f"{base}/{zname}",
                "update_sha256": sha_file(zpath),
                "update_size": zpath.stat().st_size,
            }
        )
        attach_blockmap(primary, zname, prefix="update_blockmap")
    for key in keys:
        platforms[key] = dict(primary)

# Ensure zip / AppImage platforms get blockmaps when present on the release.
for key, entry in list(platforms.items()):
    zname = str(entry.get("update_filename") or "")
    if zname.lower().endswith(".zip") and "update_blockmap_url" not in entry:
        attach_blockmap(entry, zname, prefix="update_blockmap")
    pname = str(entry.get("filename") or "")
    if pname.lower().endswith(".appimage") and "blockmap_url" not in entry:
        attach_blockmap(entry, pname, prefix="blockmap")

# Windows in-app updates must use the Inno .exe. ZIP replace fails under Program Files
# ACLs and leaves users on the old build after the app has already quit. Also lets
# older clients (that prefer update_url) download a package they can actually apply.
win = platforms.get("win-x64")
if win and str(win.get("filename") or "").lower().endswith(".exe") and win.get("url"):
    win["update_filename"] = win["filename"]
    win["update_url"] = win["url"]
    win["update_sha256"] = win["sha256"]
    win["update_size"] = win["size"]
    for k in list(win.keys()):
        if k.startswith("update_blockmap"):
            del win[k]
    print("win-x64: in-app update_url -> Inno Setup .exe")

prev = json.loads(saas.read_text()) if saas.exists() else {}
# Keep platforms missing from this GitHub tag (e.g. mac-only or win/linux-only deploys).
for k in ("darwin-arm64", "darwin-x64", "darwin-universal", "win-x64", "linux-x64"):
    if k not in platforms and k in (prev.get("platforms") or {}):
        platforms[k] = prev["platforms"][k]
        print(f"preserved {k} from previous site manifest")

# Monotonic release index + force-update window (current + 2 prior = 3 releases).
release_index = int(prev.get("release_index") or 0) + 1
max_behind = 2
try:
    import re as _re
    ver_py = (root / "core" / "version.py").read_text(encoding="utf-8")
    m_idx = _re.search(r"^RELEASE_INDEX\s*=\s*(\d+)", ver_py, _re.M)
    m_behind = _re.search(r"^MAX_RELEASES_BEHIND\s*=\s*(\d+)", ver_py, _re.M)
    if m_idx:
        release_index = int(m_idx.group(1))
    if m_behind:
        max_behind = int(m_behind.group(1))
except Exception:
    pass
min_release_index = max(1, release_index - max_behind)
# Optional kill-switch override from previous manifest (hotfix).
min_supported = str(prev.get("min_supported_version") or "").strip()
manifest = {
    "version": version,
    "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "notes": notes,
    "release_index": release_index,
    "min_release_index": min_release_index,
    "min_supported_version": min_supported,
    "releases_base_url": base,
    "source": prev.get("source")
    or {
        "repo": "https://www.hiauraai.com",
        "clone": "",
        "docs": "https://www.hiauraai.com/download",
    },
    "platforms": platforms,
    "links": {
        "homepage": "https://www.hiauraai.com",
        "download": "https://www.hiauraai.com/download",
        "docs": "https://www.hiauraai.com/download",
    },
}
saas.parent.mkdir(parents=True, exist_ok=True)
text = json.dumps(manifest, indent=2) + "\n"
saas.write_text(text)
local_manifest.parent.mkdir(parents=True, exist_ok=True)
local_manifest.write_text(text)
print("Updated", saas)
print("platforms:", ", ".join(sorted(platforms)) or "(none)")
for k, v in sorted(platforms.items()):
    print(f"  {k}: {v.get('filename')} ({v.get('size')} bytes)")
PY

echo "=== Push jarvis-saas (triggers Vercel) ==="
cd "$SAAS"
git add public/releases/manifest.json src/components/download-client.tsx src/lib/platform.ts 2>/dev/null || git add public/releases/manifest.json
if git diff --cached --quiet; then
  echo "No site changes to commit"
else
  git commit -m "$(cat <<EOF
Publish AURA ${VERSION} desktop builds (universal macOS when present)

EOF
)"
  if ! git push origin HEAD 2>/dev/null; then
    git push "https://x-access-token:${GITHUB_TOKEN}@github.com/qweqwe13123/jarvis-saas.git" HEAD:main
  fi
fi

echo "✅ Deploy pipeline finished"
echo "Download page: https://www.hiauraai.com/download"
echo "API: https://www.hiauraai.com/api/releases/latest"
echo "Release: https://github.com/${OWNER}/${REPO}/releases/tag/${TAG}"
