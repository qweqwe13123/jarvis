from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


WORKFLOW_DIR = _base_dir() / "runtime" / "workflows"


def _workflow_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or "workflow").lower()).strip("_")
    return WORKFLOW_DIR / f"{safe or 'workflow'}.json"


def _plan_workflow(goal: str) -> dict:
    steps = []
    low = goal.lower()
    if any(x in low for x in ("telegram", "телеграм")):
        steps.append({"tool": "telegram_control", "action": "message_or_call", "note": "Use Telegram contact and message/call intent from user."})
    if any(x in low for x in ("whatsapp", "email", "discord", "сообщ")):
        steps.append({"tool": "send_message", "action": "send", "note": "Send message through requested channel."})
    if any(x in low for x in ("site", "browser", "сайт", "брауз")):
        steps.append({"tool": "browser_control", "action": "go_to/search/click", "note": "Automate browser steps."})
    if any(x in low for x in ("file", "файл", "папк")):
        steps.append({"tool": "file_controller", "action": "manage_files", "note": "Read/write/move/analyze files."})
    if any(x in low for x in ("remind", "timer", "напом", "таймер", "schedule")):
        steps.append({"tool": "reminder", "action": "schedule", "note": "Schedule reminder or timer."})
    if not steps:
        steps.append({"tool": "agent_task", "action": "multi_step", "note": "Let the planner decompose the task."})
    return {
        "goal": goal,
        "created": datetime.now().isoformat(timespec="seconds"),
        "status": "draft",
        "steps": steps,
    }


def _install_launch_agent(name: str, prompt: str, interval_minutes: int) -> str:
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    label = f"com.jarvis.workflow.{name}"
    script_path = WORKFLOW_DIR / f"{name}_scheduled.py"
    script_path.write_text(
        "from pathlib import Path\n"
        "import datetime\n"
        f"Path({str(WORKFLOW_DIR / (name + '_runs.log'))!r}).write_text('Scheduled workflow tick: ' + datetime.datetime.now().isoformat() + '\\n', encoding='utf-8')\n"
        f"# Goal: {prompt!r}\n",
        encoding="utf-8",
    )
    plist = agents_dir / f"{label}.plist"
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{label}</string>
<key>ProgramArguments</key><array><string>{sys.executable}</string><string>{script_path}</string></array>
<key>StartInterval</key><integer>{max(60, interval_minutes * 60)}</integer>
<key>RunAtLoad</key><false/>
<key>StandardOutPath</key><string>/dev/null</string>
<key>StandardErrorPath</key><string>/dev/null</string>
</dict></plist>
""", encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
    if result.returncode != 0:
        return f"Workflow saved, but schedule install failed: {result.stderr.strip()}"
    return f"Workflow scheduled every {interval_minutes} minutes."


def automation_workflow(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "create").lower().strip()
    name = (params.get("name") or "jarvis_workflow").strip()
    goal = (params.get("goal") or params.get("description") or "").strip()
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)

    if action in ("create", "plan"):
        if not goal:
            return "Please provide the workflow goal."
        workflow = _plan_workflow(goal)
        path = _workflow_path(name)
        path.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
        result = f"Workflow '{path.stem}' planned with {len(workflow['steps'])} step(s): {path}"
    elif action == "list":
        items = sorted(p.stem for p in WORKFLOW_DIR.glob("*.json"))
        result = "Workflows: " + (", ".join(items) if items else "none")
    elif action == "schedule":
        if not goal:
            existing = _workflow_path(name)
            goal = existing.read_text(encoding="utf-8")[:500] if existing.exists() else name
        interval = int(params.get("interval_minutes", 60))
        result = _install_launch_agent(_workflow_path(name).stem, goal, interval)
    else:
        result = f"Unknown workflow action: {action}"

    print(f"[Workflow] {result}")
    if player:
        player.write_log(f"[Workflow] {result[:140]}")
    return result
