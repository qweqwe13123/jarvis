# Releasing JARVIS Desktop

## Stack

- **App**: Python 3.11+ / PyQt6
- **Packaging**: PyInstaller (`packaging/jarvis.spec`)
- **Updates**: custom manifest + background downloader + detached installer
- **Website**: `jarvis-saas` serves `/api/releases/latest` and smart download links

## Supported targets

| Key | Platform |
|-----|----------|
| `darwin-arm64` | macOS Apple Silicon |
| `darwin-x64` | macOS Intel |
| `win-x64` | Windows 10/11 |
| `linux-x64` | Linux x86_64 |

Build each target on its native OS (or CI matrix).

## 1. Bump version

Edit `core/version.py`:

```python
VERSION = "1.0.1"
```

Keep `packaging/jarvis.spec` bundle version in sync if you change it there.

## 2. Build on each platform

```bash
pip install -r requirements.txt
pip install -r packaging/requirements-packaging.txt
python packaging/build.py --version 1.0.1 --notes "## 1.0.1\n- Voice latency improvements\n- Updater fixes"
```

Outputs:

- `dist/releases/JARVIS-<version>-<platform>.zip`
- `dist/releases/manifest.json` (merged per platform)

## 3. Upload artifacts

Upload all `.zip` files and the final `manifest.json` to your CDN, e.g.:

```
https://jarvis.app/releases/JARVIS-1.0.1-macos-arm64.zip
https://jarvis.app/releases/manifest.json
```

Copy `manifest.json` to the SaaS site:

```bash
cp dist/releases/manifest.json ../jarvis-saas/public/releases/manifest.json
```

## 4. Auto-update behavior

Packaged apps check:

- on startup (after 8 seconds)
- every 4 hours

Manifest URL:

- default: `https://jarvis.app/api/releases/latest`
- override: `JARVIS_UPDATE_MANIFEST_URL`

Skip checks in dev:

```bash
JARVIS_SKIP_UPDATE_CHECK=1 python main.py
```

## 5. CI suggestion

Use GitHub Actions matrix:

- `macos-14` → `darwin-arm64`
- `macos-13` → `darwin-x64`
- `windows-latest` → `win-x64`
- `ubuntu-latest` → `linux-x64`

Merge `manifest.json` artifacts from each job, upload to Releases + CDN.

## Installers

- **macOS**: notarized `.dmg` (first install) + `.zip` (in-app update)
- **Windows**: Inno Setup `.exe` installer (Start Menu / Desktop shortcuts) + `.zip` (in-app update)
- **Linux**: `.AppImage` (first install + in-app update) + `.zip` fallback

Website primary URLs come from `manifest.json` `platforms.*.url`; update packages use `update_url` + blockmap.
