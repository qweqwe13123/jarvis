"""Early boot for frozen AURA: prefer on-disk jarvis_ui (sync/auth hotfixes).

PyInstaller may import this automatically from MEIPASS if site is enabled.
Also safe if imported manually from a runtime hook.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _install() -> None:
    try:
        probe = Path.home() / "Library" / "Application Support" / "AURA" / "_boot_probe.txt"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("sitecustomize_ran=1\n", encoding="utf-8")
    except Exception:
        pass

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    try:
        contents = Path(sys.executable).resolve().parent.parent
        roots.extend([contents / "Frameworks", contents / "Resources"])
    except Exception:
        pass

    root = None
    for base in roots:
        marker = base / "jarvis_ui" / "paths.py"
        if marker.is_file():
            root = base
            break
    if root is None:
        return

    class _DiskJarvisUIFinder:
        def __init__(self, base: Path) -> None:
            self._root = base

        def find_spec(self, fullname, path, target=None):  # noqa: ANN001
            if fullname != "jarvis_ui" and not fullname.startswith("jarvis_ui."):
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

    sys.meta_path.insert(0, _DiskJarvisUIFinder(root))
    for name in list(sys.modules):
        if name == "jarvis_ui" or name.startswith("jarvis_ui."):
            del sys.modules[name]

    try:
        probe = Path.home() / "Library" / "Application Support" / "AURA" / "_boot_probe.txt"
        probe.write_text(f"sitecustomize_ran=1\nroot={root}\n", encoding="utf-8")
    except Exception:
        pass


_install()
