"""Per-platform release version must drive in-app update offers."""

from __future__ import annotations

from core.updater.manifest import _platform_asset_version, parse_release


def test_platform_version_from_filename():
    assert (
        _platform_asset_version(
            {"filename": "AURA-1.0.22-macos-universal.dmg"},
            fallback="1.0.27",
        )
        == "1.0.22"
    )


def test_mac_does_not_offer_win_only_bump(monkeypatch):
    data = {
        "version": "1.0.27",
        "release_index": 27,
        "min_release_index": 25,
        "platforms": {
            "darwin-arm64": {
                "version": "1.0.22",
                "filename": "AURA-1.0.22-macos-universal.dmg",
                "url": "https://example.com/AURA-1.0.22-macos-universal.dmg",
                "sha256": "a" * 64,
                "size": 10,
                "update_filename": "AURA-1.0.22-macos-universal.zip",
                "update_url": "https://example.com/AURA-1.0.22-macos-universal.zip",
                "update_sha256": "b" * 64,
                "update_size": 11,
            }
        },
    }
    # Local Mac already on 1.0.22 — even if site top-level is 1.0.27.
    monkeypatch.setattr("core.updater.manifest.VERSION", "1.0.22")
    monkeypatch.setattr("core.updater.manifest.RELEASE_INDEX", 22)
    assert parse_release(data, target="darwin-arm64") is None


def test_mac_offers_when_platform_package_is_newer(monkeypatch):
    data = {
        "version": "1.0.27",
        "release_index": 27,
        "min_release_index": 25,
        "platforms": {
            "darwin-arm64": {
                "filename": "AURA-1.0.27-macos-universal.dmg",
                "url": "https://example.com/AURA-1.0.27-macos-universal.dmg",
                "sha256": "a" * 64,
                "size": 10,
                "update_filename": "AURA-1.0.27-macos-universal.zip",
                "update_url": "https://example.com/AURA-1.0.27-macos-universal.zip",
                "update_sha256": "b" * 64,
                "update_size": 11,
            }
        },
    }
    monkeypatch.setattr("core.updater.manifest.VERSION", "1.0.22")
    monkeypatch.setattr("core.updater.manifest.RELEASE_INDEX", 22)
    rel = parse_release(data, target="darwin-arm64")
    assert rel is not None
    assert rel.version == "1.0.27"
    assert rel.asset.filename.endswith(".zip")
