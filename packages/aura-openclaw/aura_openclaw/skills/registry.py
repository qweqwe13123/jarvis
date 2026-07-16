"""OpenClaw-style skills registry."""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class Skill:
    name: str
    description: str
    handler: Callable[..., str]
    triggers: list[str]
    metadata: dict[str, Any]


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> int:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for path in sorted(self.skills_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                skill = self._load_skill(data)
                self._skills[skill.name] = skill
                count += 1
            except Exception as e:
                print(f"[Skills] skip {path.name}: {e}")
        return count

    def _load_skill(self, data: dict) -> Skill:
        name = str(data["name"])
        handler_path = str(data["handler"])
        module_name, func_name = handler_path.rsplit(":", 1)
        module = importlib.import_module(module_name)
        handler = getattr(module, func_name)
        return Skill(
            name=name,
            description=str(data.get("description", "")),
            handler=handler,
            triggers=list(data.get("triggers", ["manual"])),
            metadata=dict(data.get("metadata") or {}),
        )

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, str]]:
        return [{"name": s.name, "description": s.description} for s in self._skills.values()]

    def run(self, name: str, **kwargs) -> str:
        skill = self.get(name)
        if not skill:
            raise KeyError(f"unknown skill: {name}")
        return str(skill.handler(**kwargs))
