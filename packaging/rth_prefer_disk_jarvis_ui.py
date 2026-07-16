"""PyInstaller runtime hook: prefer on-disk packages over baked PYZ bytecode.

Loads jarvis_ui (+ core when present on disk) from Contents/{Frameworks,Resources}
so hotfixes take effect without always requiring a full rebuild.

Also loads top-level ``ui.py`` from the same tree when present.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_DISK_PACKAGES = ("jarvis_ui", "core")
_DISK_MODULES = ("ui",)


def _disk_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    try:
        contents = Path(sys.executable).resolve().parent.parent
        roots.append(contents / "Frameworks")
        roots.append(contents / "Resources")
    except Exception:
        pass
    return roots


def _pick_root() -> Path | None:
    for base in _disk_roots():
        marker = base / "jarvis_ui" / "components.py"
        paths_py = base / "jarvis_ui" / "paths.py"
        if not marker.is_file() and not paths_py.is_file():
            continue
        if marker.is_file():
            try:
                text = marker.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""
            if "AvatarCircle" in text and "_open_permissions" in text:
                return base
        if paths_py.is_file():
            return base
    return None


class _DiskPackageFinder:
    def __init__(
        self,
        root: Path,
        packages: tuple[str, ...],
        modules: tuple[str, ...] = (),
    ) -> None:
        self._root = root
        self._packages = packages
        self._modules = modules

    def find_spec(self, fullname, path, target=None):  # noqa: ANN001
        if fullname in self._modules:
            mod_file = self._root / f"{fullname}.py"
            if mod_file.is_file():
                return importlib.util.spec_from_file_location(fullname, mod_file)
            return None
        top = fullname.split(".", 1)[0]
        if top not in self._packages:
            return None
        if not (self._root / top).is_dir():
            return None
        rel = fullname.replace(".", "/")
        pkg_init = self._root / rel / "__init__.py"
        mod_file = self._root / f"{rel}.py"
        if pkg_init.is_file():
            return importlib.util.spec_from_file_location(
                fullname,
                pkg_init,
                submodule_search_locations=[str(self._root / rel)],
            )
        if mod_file.is_file():
            return importlib.util.spec_from_file_location(fullname, mod_file)
        return None


_root = _pick_root()
if _root is not None:
    packages = _DISK_PACKAGES if (_root / "core").is_dir() else ("jarvis_ui",)
    sys.meta_path.insert(0, _DiskPackageFinder(_root, packages, _DISK_MODULES))
    for _name in list(sys.modules):
        top = _name.split(".", 1)[0]
        if top in packages or _name in _DISK_MODULES:
            del sys.modules[_name]
