#!/bin/zsh
# Upload signed DMG to GitHub Releases + update jarvis-saas manifest + push (Vercel).
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
DMG="$ROOT/dist/releases/AURA-${VERSION}-macos-${ARCH}.dmg"
ZIP="$ROOT/dist/releases/AURA-${VERSION}-macos-${ARCH}.zip"

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

if [ ! -f "$DMG" ]; then
  echo "Missing DMG: $DMG — run packaging/build.py --notarize first"
  exit 1
fi

export GH_TOKEN="$GITHUB_TOKEN"

echo "=== Ensure GitHub release $TAG ==="
if ! gh release view "$TAG" --repo "$OWNER/$REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$OWNER/$REPO" --title "AURA $VERSION" --notes "AURA desktop release $VERSION"
fi

echo "=== Upload assets ==="
UPLOAD_ARGS=("$DMG")
[[ -f "$ZIP" ]] && UPLOAD_ARGS+=("$ZIP")
gh release upload "$TAG" "${UPLOAD_ARGS[@]}" --repo "$OWNER/$REPO" --clobber

echo "=== Update jarvis-saas manifest ==="
"$PY" - <<PY
import hashlib, json
from pathlib import Path
from datetime import datetime, timezone

root = Path("$ROOT")
saas = Path("$SAAS") / "public" / "releases" / "manifest.json"
dmg = Path("$DMG")
zpath = Path("$ZIP")
version = "$VERSION"
tag = "$TAG"
owner = "$OWNER"
repo = "$REPO"
arch = "$ARCH"
platform_key = f"darwin-{arch}"

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()

base = f"https://github.com/{owner}/{repo}/releases/download/{tag}"
prev = {}
if saas.exists():
    prev = json.loads(saas.read_text())
platforms = dict(prev.get("platforms") or {})
entry = {
    "url": f"{base}/AURA-{version}-macos-{arch}.dmg",
    "sha256": sha(dmg),
    "size": dmg.stat().st_size,
    "filename": f"AURA-{version}-macos-{arch}.dmg",
}
if zpath.exists():
    entry.update({
        "update_filename": f"AURA-{version}-macos-{arch}.zip",
        "update_url": f"{base}/AURA-{version}-macos-{arch}.zip",
        "update_sha256": sha(zpath),
        "update_size": zpath.stat().st_size,
    })
platforms[platform_key] = entry

# Prefer local dist manifest notes if present
local_manifest = root / "dist" / "releases" / "manifest.json"
notes = f"## A.U.R.A {version}\n\n- Signed + notarized macOS Apple Silicon (.dmg)\n- System-style drag-to-Applications installer\n- Double-clap wake (AURA Wake)"
if local_manifest.exists():
    try:
        notes = json.loads(local_manifest.read_text()).get("notes") or notes
    except Exception:
        pass

manifest = {
    "version": version,
    "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "notes": notes,
    "releases_base_url": base,
    "source": prev.get("source") or {
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
saas.write_text(json.dumps(manifest, indent=2) + "\n")
local_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
print("Updated", saas)
print(platform_key, "sha256", entry["sha256"])
print(platform_key, "size", entry["size"])
PY

echo "=== Push jarvis-saas (triggers Vercel) ==="
cd "$SAAS"
git add public/releases/manifest.json
if git diff --cached --quiet; then
  echo "No manifest changes to commit"
else
  git commit -m "$(cat <<EOF
Publish notarized AURA ${VERSION} macOS arm64 DMG

EOF
)"
  # Push with token if plain push fails (non-interactive)
  if ! git push origin HEAD 2>/dev/null; then
    git push "https://x-access-token:${GITHUB_TOKEN}@github.com/qweqwe13123/jarvis-saas.git" HEAD:main
  fi
fi

echo "✅ Deploy pipeline finished"
echo "Download page: https://www.hiauraai.com/download"
echo "API: https://www.hiauraai.com/api/releases/latest"
echo "Release: https://github.com/${OWNER}/${REPO}/releases/tag/${TAG}"
