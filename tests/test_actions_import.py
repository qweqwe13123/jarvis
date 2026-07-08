"""Smoke tests: every action/core module must import without crashing.

These guard the "never break existing functionality" rule — a bad refactor
that leaves a syntax error or missing import in any tool module fails CI
before it can reach users.
"""
import importlib
import pkgutil
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ACTION_MODULES = sorted(
    m.name for m in pkgutil.iter_modules([str(ROOT / "actions")])
    if not m.name.startswith("_")
)

CORE_MODULES = [
    "core.agents",
    "core.language",
    "core.model_router",
    "core.reminder_engine",
    "core.task_analyzer",
    "core.usage_manager",
    "core.version",
    "core.updater.manifest",
]


@pytest.mark.parametrize("name", ACTION_MODULES)
def test_action_module_imports(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        importlib.import_module(f"actions.{name}")


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_module_imports(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        importlib.import_module(name)


def test_actions_folder_not_empty():
    assert len(ACTION_MODULES) >= 15, ACTION_MODULES
