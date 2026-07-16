#!/bin/zsh
# Local one-shot: sign AURA.app → premium DMG → notarize → staple → manifest.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PY="${AURA_PYTHON:-.venv/bin/python3.13}"
ID="${AURA_CODESIGN_IDENTITY:-Developer ID Application: Khalil Isaiev (PNY6NC68X3)}"
PROFILE="${AURA_NOTARY_PROFILE:-AURA-notarize}"
APP='dist/AURA.app'
VERSION="$("$PY" -c 'from core.version import VERSION; print(VERSION)')"
ARCH="$(uname -m)"
[[ "$ARCH" == "arm64" ]] || ARCH="x64"
DMG="dist/releases/AURA-${VERSION}-macos-${ARCH}.dmg"
ENT='packaging/entitlements.plist'
ENTW='packaging/entitlements-wake.plist'

echo "=== AURA sign + premium DMG + notarize ==="
echo "version=$VERSION arch=$ARCH"
echo "If macOS asks for Keychain access → Always Allow"

# Ensure wake is embedded
if [ ! -d "$APP/Contents/Resources/AURAWake.app" ]; then
  "$PY" tools/build_wake_helper.py
  mkdir -p "$APP/Contents/Resources"
  rm -rf "$APP/Contents/Resources/AURAWake.app"
  cp -R dist/AURAWake.app "$APP/Contents/Resources/AURAWake.app"
fi

echo "[1/6] Regenerate Retina DMG background…"
"$PY" packaging/dmg_background.py

echo "[2/6] Sign AURAWake…"
codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENTW" --sign "$ID" \
  "$APP/Contents/Resources/AURAWake.app"

echo "[3/6] Sign AURA.app…"
codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENT" --sign "$ID" "$APP"
codesign --verify --deep --strict "$APP"

echo "[4/6] Build premium DMG (Finder layout)…"
mkdir -p dist/releases
"$PY" packaging/make_dmg.py --app "$APP" --out "$DMG" --volume AURA

echo "[5/6] Sign DMG…"
codesign --force --timestamp --sign "$ID" "$DMG"

echo "[6/6] Notarize (may take a few minutes)…"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG" || true

# Update zip + manifest
"$PY" - <<PY
import hashlib, json, zipfile
from pathlib import Path
from datetime import datetime, timezone
from core.version import VERSION

ROOT = Path('.').resolve()
app = ROOT / 'dist' / 'AURA.app'
arch = 'arm64' if __import__('platform').machine() == 'arm64' else 'x64'
dmg = ROOT / 'dist' / 'releases' / f'AURA-{VERSION}-macos-{arch}.dmg'
zpath = ROOT / 'dist' / 'releases' / f'AURA-{VERSION}-macos-{arch}.zip'
if zpath.exists():
    zpath.unlink()
with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in app.rglob('*'):
        if p.is_file():
            zf.write(p, p.relative_to(app.parent).as_posix())

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1024 * 1024), b''):
            h.update(c)
    return h.hexdigest()

base = f'https://github.com/qweqwe13123/jarvis/releases/download/v{VERSION}'
platform_key = f'darwin-{arch}'
entry = {
    'url': f'{base}/AURA-{VERSION}-macos-{arch}.dmg',
    'sha256': sha(dmg),
    'size': dmg.stat().st_size,
    'filename': f'AURA-{VERSION}-macos-{arch}.dmg',
    'update_filename': f'AURA-{VERSION}-macos-{arch}.zip',
    'update_url': f'{base}/AURA-{VERSION}-macos-{arch}.zip',
    'update_sha256': sha(zpath),
    'update_size': zpath.stat().st_size,
}
manifest = {
    'version': VERSION,
    'released_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'notes': f'## A.U.R.A {VERSION}\n\n- Signed + notarized macOS (.dmg)\n- Premium drag-to-Applications installer\n- Double-clap wake (AURA Wake)',
    'releases_base_url': base,
    'links': {
        'homepage': 'https://www.hiauraai.com',
        'download': 'https://www.hiauraai.com/download',
        'docs': 'https://www.hiauraai.com/download',
    },
    'platforms': {platform_key: entry},
}
old = ROOT / 'dist' / 'releases' / 'manifest.json'
if old.exists():
    try:
        prev = json.loads(old.read_text())
        for k, v in (prev.get('platforms') or {}).items():
            if k != platform_key:
                manifest['platforms'][k] = v
    except Exception:
        pass
out = ROOT / 'dist' / 'releases' / 'manifest.json'
out.write_text(json.dumps(manifest, indent=2) + '\n')
print('Manifest written', out)
print('DMG sha256', entry['sha256'])
PY

echo ""
echo "✅ DONE"
echo "DMG: $DMG"
ls -lh "$DMG"
spctl -a -t open --context context:primary-signature -v "$DMG" 2>&1 || true
echo "EXIT:0"
