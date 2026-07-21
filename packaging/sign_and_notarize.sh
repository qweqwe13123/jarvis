#!/bin/zsh
# Local one-shot: sign → notarize+staple .app → DMG → notarize+staple DMG → ZIP verify.
#
# Critical order (Gatekeeper / "AURA Not Opened"):
#   1) Staple AURA.app BEFORE packing it into the DMG.
#   2) Copy into DMG via ditto (preserves CodeResources + staple ticket).
#   3) ZIP update package via ditto; round-trip must pass codesign+stapler+spctl.
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
# Prefer universal artifact names when the main binary is fat (arm64 + x86_64).
if [ -f "$APP/Contents/MacOS/AURA" ]; then
  LIPO_ARCHS="$(lipo -archs "$APP/Contents/MacOS/AURA" 2>/dev/null || true)"
  if [[ "$LIPO_ARCHS" == *arm64* && "$LIPO_ARCHS" == *x86_64* ]]; then
    ARCH="universal"
  fi
fi
DMG="dist/releases/AURA-${VERSION}-macos-${ARCH}.dmg"
ENT='packaging/entitlements.plist'
ENTW='packaging/entitlements-wake.plist'
NOTARY_ZIP="dist/releases/_AURA-${VERSION}-notarize-submit.zip"

echo "=== AURA sign + premium DMG + notarize ==="
echo "version=$VERSION arch=$ARCH"
echo "If macOS asks for Keychain access → Always Allow"

# Ensure wake is embedded when the helper build script is available.
if [ ! -d "$APP/Contents/Resources/AURAWake.app" ]; then
  if [ -f tools/build_wake_helper.py ]; then
    "$PY" tools/build_wake_helper.py
    mkdir -p "$APP/Contents/Resources"
    rm -rf "$APP/Contents/Resources/AURAWake.app"
    cp -R dist/AURAWake.app "$APP/Contents/Resources/AURAWake.app"
  else
    echo "[Wake] tools/build_wake_helper.py missing — skipping AURAWake.app embed"
  fi
fi

echo "[1/8] Regenerate Retina DMG background…"
"$PY" packaging/dmg_background.py

if [ -d "$APP/Contents/Resources/AURAWake.app" ]; then
  echo "[2/8] Sign AURAWake…"
  codesign --force --deep --options runtime --timestamp \
    --entitlements "$ENTW" --sign "$ID" \
    "$APP/Contents/Resources/AURAWake.app"
else
  echo "[2/8] Sign AURAWake… skipped (not embedded)"
fi

echo "[3/8] Sign AURA.app…"
codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENT" --sign "$ID" "$APP"
codesign --verify --deep --strict "$APP"

# Notarize the .app itself first so the ticket is stapled before DMG packaging.
# Opening AURA from a mounted DMG assesses the nested .app — DMG staple alone
# is not enough offline / on newer Gatekeeper ("AURA Not Opened").
echo "[4/8] Notarize AURA.app (zip submit)…"
mkdir -p dist/releases
rm -f "$NOTARY_ZIP"
ditto -c -k --keepParent "$APP" "$NOTARY_ZIP"
xcrun notarytool submit "$NOTARY_ZIP" --keychain-profile "$PROFILE" --wait
rm -f "$NOTARY_ZIP"

echo "[5/8] Staple ticket onto AURA.app…"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
codesign --verify --deep --strict "$APP"
spctl --assess --type execute -vv "$APP"

echo "[6/8] Build premium DMG from stapled .app…"
"$PY" packaging/make_dmg.py --app "$APP" --out "$DMG" --volume AURA

echo "[7/8] Sign + notarize + staple DMG…"
codesign --force --timestamp --sign "$ID" "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"

# Gate: nested .app inside DMG must carry a staple (what users open first).
echo "[7b] Gate: nested AURA.app inside DMG…"
DMG_MNT="$(mktemp -d /tmp/aura-dmg-gate-XXXXXX)"
cleanup_mnt() { hdiutil detach "$DMG_MNT" >/dev/null 2>&1 || true; rm -rf "$DMG_MNT"; }
trap cleanup_mnt EXIT
hdiutil attach "$DMG" -readonly -nobrowse -mountpoint "$DMG_MNT"
NESTED="$DMG_MNT/AURA.app"
codesign --verify --deep --strict "$NESTED"
xcrun stapler validate "$NESTED"
spctl --assess --type execute -vv "$NESTED"
cleanup_mnt
trap - EXIT

echo "[8/8] Update ZIP (ditto) + round-trip verify + blockmap…"
"$PY" - <<PY
import hashlib, json, subprocess, tempfile, shutil
from pathlib import Path
from datetime import datetime, timezone
from core.version import VERSION
from core.updater.blockmap import generate_blockmap

ROOT = Path('.').resolve()
app = ROOT / 'dist' / 'AURA.app'
arch = 'arm64' if __import__('platform').machine() == 'arm64' else 'x64'
exe = app / 'Contents' / 'MacOS' / 'AURA'
try:
    lipo = subprocess.check_output(['lipo', '-archs', str(exe)], text=True).strip().split()
    if 'arm64' in lipo and 'x86_64' in lipo:
        arch = 'universal'
except Exception:
    pass
dmg = ROOT / 'dist' / 'releases' / f'AURA-{VERSION}-macos-{arch}.dmg'
shell_dmg = Path("$DMG")
if shell_dmg.is_file() and shell_dmg != dmg:
    dmg = shell_dmg
    stem = dmg.stem
    if '-macos-' in stem:
        arch = stem.split('-macos-', 1)[1]
zpath = ROOT / 'dist' / 'releases' / f'AURA-{VERSION}-macos-{arch}.zip'
if zpath.exists():
    zpath.unlink()
subprocess.check_call(['ditto', '-c', '-k', '--keepParent', str(app), str(zpath)])

# Hard gate: ZIP round-trip must pass codesign + stapler + spctl.
td = Path(tempfile.mkdtemp(prefix='aura-zipcheck-'))
try:
    subprocess.check_call(['ditto', '-x', '-k', str(zpath), str(td)])
    extracted = next(td.rglob('AURA.app'))
    subprocess.check_call(['codesign', '--verify', '--deep', '--strict', str(extracted)])
    subprocess.check_call(['xcrun', 'stapler', 'validate', str(extracted)])
    sp = subprocess.run(
        ['spctl', '--assess', '--type', 'execute', '-vv', str(extracted)],
        capture_output=True,
        text=True,
    )
    # spctl writes assessment to stderr
    out = (sp.stdout or '') + (sp.stderr or '')
    print(out.strip())
    if sp.returncode != 0 or 'accepted' not in out:
        raise SystemExit(f'ZIP round-trip spctl FAILED:\n{out}')
    print('ZIP round-trip codesign+staple+spctl OK:', extracted)
finally:
    shutil.rmtree(td, ignore_errors=True)

bm_path = Path(str(zpath) + '.blockmap')
bm = generate_blockmap(zpath)
bm.save(bm_path)
bm_file_sha = hashlib.sha256(bm_path.read_bytes()).hexdigest()

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1024 * 1024), b''):
            h.update(c)
    return h.hexdigest()

base = f'https://github.com/qweqwe13123/jarvis/releases/download/v{VERSION}'
keys = (
    ['darwin-arm64', 'darwin-x64', 'darwin-universal']
    if arch == 'universal'
    else [f'darwin-{arch}']
)
entry = {
    'url': f'{base}/AURA-{VERSION}-macos-{arch}.dmg',
    'sha256': sha(dmg),
    'size': dmg.stat().st_size,
    'filename': f'AURA-{VERSION}-macos-{arch}.dmg',
    'update_filename': f'AURA-{VERSION}-macos-{arch}.zip',
    'update_url': f'{base}/AURA-{VERSION}-macos-{arch}.zip',
    'update_sha256': sha(zpath),
    'update_size': zpath.stat().st_size,
    'update_blockmap_url': f'{base}/AURA-{VERSION}-macos-{arch}.zip.blockmap',
    'update_blockmap_sha256': bm_file_sha,
    'update_blockmap_size': bm_path.stat().st_size,
}
from core.version import RELEASE_INDEX, MAX_RELEASES_BEHIND
min_release_index = max(1, int(RELEASE_INDEX) - int(MAX_RELEASES_BEHIND))
manifest = {
    'version': VERSION,
    'released_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    'notes': (
        f"## What's new in {VERSION}\n\n"
        "- Multi-device: link Mac + Windows under one account and send commands across machines\n"
        "- Devices hub in the sidebar — online status, rename, remote open test\n"
        "- Chat photo attachments with drag-and-drop and lightbox preview\n"
        "- Windows updater reliability (Cursor-safe apply + relaunch)\n"
        "- Universal macOS build (Apple Silicon + Intel)"
    ),
    'release_index': int(RELEASE_INDEX),
    'min_release_index': min_release_index,
    'min_supported_version': '',
    'releases_base_url': base,
    'links': {
        'homepage': 'https://www.hiauraai.com',
        'download': 'https://www.hiauraai.com/download',
        'docs': 'https://www.hiauraai.com/download',
    },
    'platforms': {k: dict(entry) for k in keys},
}
old = ROOT / 'dist' / 'releases' / 'manifest.json'
if old.exists():
    try:
        prev = json.loads(old.read_text())
        for k, v in (prev.get('platforms') or {}).items():
            if k not in keys:
                manifest['platforms'][k] = v
    except Exception:
        pass
out = ROOT / 'dist' / 'releases' / 'manifest.json'
out.write_text(json.dumps(manifest, indent=2) + '\n')
print('Manifest written', out)
print('DMG sha256', entry['sha256'])
print('ZIP sha256', entry['update_sha256'])
print('ZIP blockmap', bm_path, 'blocks', bm.block_count)
PY

echo ""
echo "✅ DONE — all gates passed"
echo "DMG: $DMG"
ls -lh "$DMG"
ls -lh "dist/releases/AURA-${VERSION}-macos-"*.zip "dist/releases/AURA-${VERSION}-macos-"*.zip.blockmap 2>/dev/null || true
spctl -a -t open --context context:primary-signature -v "$DMG" 2>&1 || true
echo "EXIT:0"
