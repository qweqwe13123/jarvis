#!/usr/bin/env python3
"""Print AURA VERSION for CI / release scripts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "core" / "version.py").read_text(encoding="utf-8")
m = re.search(r'VERSION\s*=\s*["\']([^"\']+)', text)
if not m:
    print("0.0.0", file=sys.stderr)
    raise SystemExit(1)
print(m.group(1))
