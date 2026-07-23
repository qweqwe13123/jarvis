import sys
from pathlib import Path


def _early_special_mode() -> bool:
    """Handle updater/wake argv before loading the full UI stack.

    Frozen updater/wake children must not import ui, sounddevice, or google.
    Returns True if the process should exit after this handler.
    """
    if len(sys.argv) < 2:
        return False
    flag = sys.argv[1]
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if flag == "--jarvis-apply-update":
        if len(sys.argv) < 3:
            print("usage: --jarvis-apply-update PACKAGE [PARENT_PID]", file=sys.stderr)
            raise SystemExit(2)
        from core.updater.installer import apply_update

        package = Path(sys.argv[2])
        parent_pid = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        raise SystemExit(apply_update(package, parent_pid=parent_pid))

    if flag in ("--wake-listener", "--aura-wake"):
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from launcher.wake_listener import main as wake_main

        wake_main()
        return True

    if flag == "--aura-smoke":
        # CI / packaging gate: prove numpy C-extensions load in the frozen app.
        import numpy as np

        print(f"SMOKE_OK numpy={np.__version__}", flush=True)
        raise SystemExit(0)

    return False


if __name__ == "__main__" and _early_special_mode():
    raise SystemExit(0)


import asyncio
import atexit
import re
import threading
import json
import traceback
import time

import sounddevice as sd
import numpy as np
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    append_conversation, format_recent_conversation_for_prompt,
    load_recent_conversation,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.dispatch_to_device import dispatch_to_device
from actions.game_updater      import game_updater
from actions.autonomous_mode   import autonomous_mode
from actions.focus_guard       import focus_guard
from actions.telegram_control  import telegram_control
from actions.automation_workflow import automation_workflow
from actions.communication_module import communication_module
from actions.media_downloader import media_downloader
from core.language import detect_and_save_language, language_instruction, DEFAULT_GREETING_HINT, load_language
from core.task_analyzer import analyze_task
from core.usage_manager import usage_stats
from core.model_router import generate_text, ModelRouterError
from core.remote_intent import (
    parse_remote_power_intent,
    should_redirect_local_power,
    tool_result_ok,
)
from memory.vector_memory import remember_vector


def get_base_dir():
    if getattr(sys, "frozen", False):
        from core.app_paths import resource_dir

        return resource_dir()
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
try:
    from core.app_paths import api_keys_path as _api_keys_path

    API_CONFIG_PATH = _api_keys_path()
except Exception:
    API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
# Display / initial preference — runtime picks from core.gemini_models live chain.
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_live_api_version() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("live_api_version", "v1alpha")
    except Exception:
        return "v1alpha"


def _flatten_exceptions(err: BaseException) -> list:
    """Recursively unwrap ExceptionGroup into a flat list of leaf exceptions."""
    group = getattr(err, "exceptions", None)
    if group:
        out = []
        for sub in group:
            out.extend(_flatten_exceptions(sub))
        return out
    return [err]


def _classify_connection_error(err: Exception) -> str:
    """Return 'auth' for fatal API-key problems, 'transient' otherwise."""
    msg = str(err).lower()
    auth_markers = (
        "api key expired", "api_key_invalid", "api key not valid",
        "invalid api key", "permission_denied", "permission denied",
        "unauthenticated", "invalid authentication", "expired",
        "401", "403",
    )
    if any(m in msg for m in auth_markers):
        return "auth"
    return "transient"


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are AURA, an advanced AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)
_JCFG_RE = re.compile(r"^\[JCFG\s+mode=(?P<mode>\w+)\s+provider=(?P<provider>[\w\-]+)\s+model=(?P<model>[^\]]*)\]\s*", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    replacements = {
        "джар вис": "джарвис",
        "джарвиз": "джарвис",
        "jar viss": "jarvis",
        "таймар": "таймер",
        "таймир": "таймер",
        "випить": "выпить",
        "выпит": "выпить",
        "воды": "воды",
        "напомнить меня": "напомни мне",
    }
    low = text.lower()
    for bad, good in replacements.items():
        low = low.replace(bad, good)
    text = low
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on THIS computer. "
            "Use whenever the user asks to open, launch, or start an app "
            "(Chrome, Yandex Browser / Яндекс, Spotify, Notepad, etc.). "
            "For another linked PC use dispatch_to_device with kind=open_app. "
            "Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Application name (e.g. 'Yandex Browser', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web for information. Use mode='deep_research' when the user asks for "
            "deep research, detailed research, investigate, compare sources, or wants a sourced answer. "
            "Do NOT use this to open a specific website; use browser_control action='go_to' for that."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) | deep_research | compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"},
                "max_sources": {"type": "INTEGER", "description": "Number of sources to read for deep_research (default: 5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": (
            "Sends a text message via WhatsApp, Telegram, Signal, Discord, Instagram, Messenger, or another app. "
            "Use this whenever the user says to write/send/message a specific contact. "
            "For calls or system Contacts/Phone/Messages/Email requests prefer communication_module. "
            "For Telegram requests set platform='Telegram'. Extract receiver and message exactly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "autonomous_mode",
        "description": (
            "Enables, disables, or checks autonomous/focus mode. Use when the user asks for autonomous mode, "
            "do not disturb, focus mode, nobody should bother me, or a work/protection mode. "
            "On macOS this attempts to enable Do Not Disturb/Focus and saves local mode state. "
            "Do NOT use this for 'remind me if I get distracted watching a movie' — use focus_guard for that."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "on | off | status"},
                "note": {"type": "STRING", "description": "Optional reason or context"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "focus_guard",
        "description": (
            "Distraction watchdog the USER must explicitly request. "
            "Use when they ask to be reminded if they get distracted "
            "(YouTube/movie/gaming/scrolling) and should return to a project/task. "
            "Examples: 'напомни вернуться к проекту если отвлекусь', "
            "'если залипну — один раз напомни продолжить работу', "
            "'перестань следить' / 'выключи focus'. "
            "Default one_shot=true: speak ONE nudge then auto-disable. "
            "Set one_shot=false only if they ask to keep reminding / каждый раз. "
            "Do NOT use for plain timers ('напомни через 10 минут') — use reminder instead."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "start | stop | status",
                },
                "goal": {
                    "type": "STRING",
                    "description": "What to remind them about, e.g. 'продолжить проект'",
                },
                "idle_minutes": {
                    "type": "NUMBER",
                    "description": "Minutes of distraction before nudging. Default 5.",
                },
                "one_shot": {
                    "type": "BOOLEAN",
                    "description": (
                        "true (default) = nudge once then turn off; "
                        "false = keep watching until user says stop"
                    ),
                },
                "message": {
                    "type": "STRING",
                    "description": "Optional custom nudge text. If empty, a friendly default is used.",
                },
                "language": {
                    "type": "STRING",
                    "description": "ru | en | tr | az",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "telegram_control",
        "description": (
            "Controls Telegram Desktop professionally. Use for Telegram messages and Telegram audio calls. "
            "For 'call this contact in Telegram' use action='call'. For 'write/send in Telegram' use action='message'. "
            "If the user asks AURA to say a specific phrase after call starts, pass speak_text."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "message | call"},
                "receiver": {"type": "STRING", "description": "Telegram contact name or username"},
                "message": {"type": "STRING", "description": "Message text for action=message"},
                "speak_text": {"type": "STRING", "description": "Optional phrase for AURA to speak after the call starts"}
            },
            "required": ["action", "receiver"]
        }
    },
    {
        "name": "automation_workflow",
        "description": (
            "Plans, lists, and schedules automation workflows like a lightweight n8n/agent workflow manager. "
            "Use for automations involving Telegram, WhatsApp, email, CRM, browser, files, reminders, scheduled tasks, and AI pipelines."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "create | plan | list | schedule"},
                "name": {"type": "STRING", "description": "Workflow name"},
                "goal": {"type": "STRING", "description": "What the workflow should accomplish"},
                "interval_minutes": {"type": "INTEGER", "description": "For schedule action"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "communication_module",
        "description": (
            "Runs communication actions on behalf of the user: search system Contacts, call someone, "
            "send exactly dictated text, and choose the communication app. "
            "Use this whenever the user says call/ring/phone someone, find a contact, write to someone, "
            "send a message through Phone/Messages/WhatsApp/Telegram/Discord/Email, or asks AURA to message "
            "from the user's account. For simple calls set action='call'. For dictated text set action='message'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "find_contact | call | message | choose_app"},
                "contact": {"type": "STRING", "description": "Contact name"},
                "message": {"type": "STRING", "description": "Message text"},
                "app": {"type": "STRING", "description": "Phone | Messages | WhatsApp | Telegram | Discord | Email"},
                "require_confirmation": {"type": "BOOLEAN", "description": "Require explicit user confirmation before call"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "media_downloader",
        "description": (
            "Downloads media by URL with quality and destination selection. "
            "Use when user asks to download video/audio/image/document from a link."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Source URL"},
                "quality": {"type": "STRING", "description": "best | 1080p | 720p | 480p | audio"},
                "save_to": {"type": "STRING", "description": "Destination path or alias (Desktop/Downloads)"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "reminder",
        "description": (
            "Sets reminders and short timers. Use delay_minutes or delay_seconds for requests like "
            "'in 1 minute', 'через 10 секунд', 'напомни через час'. Use date/time only for exact wall-clock reminders."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"},
                    "language": {"type": "STRING", "description": "Original user language code for the reminder: ru, en, tr, or az"},
                "delay_seconds": {"type": "INTEGER", "description": "Relative delay in seconds for timer reminders"},
                "delay_minutes": {"type": "NUMBER", "description": "Relative delay in minutes for timer reminders"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera/webcam, what is in front of me, read visible text, etc. "
            "You have NO visual ability without this tool. "
            "Use angle='camera' for webcam questions and angle='screen' for display questions. "
            "Return the vision result to the user; do not invent visual details."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls THIS computer only: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing a named app (action=close_app + app_name), "
            "closing all user apps (action=close_all_apps, requires confirmed=yes), "
            "fullscreen, dark mode, WiFi, restart, shutdown (requires confirmed=yes), "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page, "
            "and wake_status diagnostics. "
            "NEVER use this for another machine. If the user says Windows / Mac / Linux / "
            "another PC / другое устройство / на ПК / на маке — call dispatch_to_device instead "
            "(kind=computer_settings, action=shutdown|restart|…). NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "Action e.g. close_app | close_all_apps | shutdown | volume_up"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."},
                "app_name":    {"type": "STRING", "description": "App to close when action=close_app (e.g. Yandex, Chrome)"},
                "confirmed":   {"type": "STRING", "description": "Must be yes for shutdown/restart/close_all_apps"},
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "For exact website opening requests, ALWAYS use action='go_to' with url set to the requested domain or URL. "
            "Examples: 'open YouTube' -> url='youtube.com'; 'открой github.com' -> url='github.com'. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": (
            "Builds complete projects from scratch. Use for mini websites, landing pages, dashboards, "
            "browser tools, automations, scripts, and multi-file apps. It plans, writes files, installs deps, "
            "opens the result, runs it, and fixes errors when possible."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language or stack (default: python; use html for static mini-sites)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "project_type": {"type": "STRING", "description": "Optional: static_site | automation | script | app"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop AURA. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "dispatch_to_device",
        "description": (
            "Full remote control of another linked AURA desktop on the same account "
            "(Windows PC, Mac, or Linux). REQUIRED when the user names another machine: "
            "'выключи Windows', 'turn off the PC', 'на маке', 'shutdown Gaming PC', "
            "'отключи ноутбук Windows', 'restart the Mac from here'. "
            "Use for open/close apps, browser, click, type, files, settings, shutdown. "
            "Kinds: open_url | open_app | close_app | close_all_apps | browser_control | "
            "computer_control | computer_settings | file_controller | agent_task. "
            "Examples: open Yandex on Windows → kind=open_app, app_name=Yandex, platform=windows. "
            "Close Chrome on Mac → kind=close_app, app_name=Chrome, platform=mac. "
            "Shut down Windows from Mac → platform=windows, kind=computer_settings, action=shutdown "
            "(ONE call; if needed the other PC shows Allow once / Always / Deny — do NOT ask chat 'yes'). "
            "Shut down BOTH → platform=all, kind=computer_settings, action=shutdown. "
            "Do NOT use this for the current machine alone — call local tools instead. "
            "Target with platform (windows|mac|linux|all), device_name, or device_id. "
            "After the tool returns, tell the user that exact result — never invent success."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {
                    "type": "STRING",
                    "description": "Target OS hint: windows | mac | linux | all (both devices)",
                },
                "device_name": {
                    "type": "STRING",
                    "description": "Display name of the linked device (partial match ok)",
                },
                "device_id": {
                    "type": "STRING",
                    "description": "Exact device UUID from Devices list (optional)",
                },
                "kind": {
                    "type": "STRING",
                    "description": (
                        "open_url | open_app | close_app | close_all_apps | browser_control | "
                        "computer_control | computer_settings | file_controller | agent_task"
                    ),
                },
                "url": {
                    "type": "STRING",
                    "description": "URL for open_url / browser go_to",
                },
                "app_name": {
                    "type": "STRING",
                    "description": "Application name for open_app / close_app",
                },
                "goal": {
                    "type": "STRING",
                    "description": "Natural-language goal for agent_task on the target",
                },
                "action": {
                    "type": "STRING",
                    "description": "For browser_control / computer_control / computer_settings / file_controller",
                },
                "query": {"type": "STRING", "description": "Search query for browser_control search"},
                "text": {"type": "STRING", "description": "Text for type/click actions"},
                "path": {"type": "STRING", "description": "Path for file_controller"},
                "description": {
                    "type": "STRING",
                    "description": "Natural-language element or task description",
                },
                "confirmed": {
                    "type": "STRING",
                    "description": "yes — only required for close_all_apps after user agrees (remote shutdown needs no confirm)",
                },
                "all_devices": {
                    "type": "BOOLEAN",
                    "description": "If true (or platform=all), fan-out; shutdown includes this device too",
                },
                "wait": {
                    "type": "BOOLEAN",
                    "description": "Wait for remote result (default true)",
                },
            },
            "required": [],
        },
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._startup_greeting_done = False
        self._preferred_provider = "auto"
        self._preferred_model = ""
        self._live_model = LIVE_MODEL
        self._last_output_audio_at = 0.0
        self._last_voice_log_at = 0.0
        self._playback_grace_seconds = 0.75
        self._pending_user_text = ""
        self._reminder_engine = None
        self._focus_guard_engine = None
        self._start_reminder_engine()
        self._start_focus_guard_engine()

    def _start_reminder_engine(self) -> None:
        """Fire reminders/timers/alarms through the live JARVIS voice only."""
        try:
            from core.reminder_engine import ReminderEngine
            self._reminder_engine = ReminderEngine(
                speak_cb=self.speak_notification,
                log_cb=self.ui.write_log,
            )
            self._reminder_engine.start()
        except Exception as e:
            print(f"[JARVIS] ⚠️ reminder engine: {e}")

    def _start_focus_guard_engine(self) -> None:
        """Watch frontmost app and voice-nudge after prolonged distraction."""
        try:
            from core.focus_guard import FocusGuardEngine
            self._focus_guard_engine = FocusGuardEngine(
                speak_cb=self.speak_notification,
                log_cb=self.ui.write_log,
                poll_interval=15.0,
            )
            self._focus_guard_engine.start()
        except Exception as e:
            print(f"[JARVIS] ⚠️ focus guard engine: {e}")

    def _emit_workflow_for_task(self, task_category: str) -> None:
        steps = {
            "coding": ["Thinking", "Writing code", "Generating files"],
            "search": ["Thinking", "Searching"],
            "documents": ["Thinking", "Searching", "Writing code"],
            "analysis": ["Thinking", "Writing code"],
            "automation": ["Thinking", "Generating files"],
        }
        for step in steps.get(task_category, ["Thinking", "Searching"]):
            self.ui.set_workflow_step(step)

    def _on_text_command(self, text: str):
        mode = "live"
        cfg = _JCFG_RE.match(text or "")
        if cfg:
            mode = (cfg.group("mode") or "live").lower()
            self._preferred_provider = (cfg.group("provider") or "auto").lower()
            self._preferred_model = (cfg.group("model") or "").strip()
            text = (text[cfg.end():] or "").strip()
        profile = analyze_task(text)
        self.ui.set_state("THINKING")
        self.ui.set_workflow_step("Thinking")
        stats = usage_stats()
        self.ui.write_log(
            f"SYS: AI status | task={profile.category} | tier={stats.tier} | left={stats.requests_left} | queue={stats.queued}"
        )
        self.ui.set_ai_status(
            model="live-gemini",
            provider="gemini-live",
            queue=stats.queued,
            requests_left=stats.requests_left,
            tier=stats.tier,
            blocked_heavy=stats.blocked_heavy_tasks,
            latency_ms="--",
            status="listening",
            wake=self._wake_status_text(),
        )
        detect_and_save_language(text)
        append_conversation("user", text)
        remember_vector(text, kind="user_message")

        # Arm/disarm Focus Guard deterministically — don't rely on the Live model
        # remembering to call the tool (users often get a verbal "ок" with no watch).
        try:
            armed = self._maybe_arm_focus_guard(text)
            if armed:
                self.ui.write_log(f"AURA: {armed}")
        except Exception:
            pass

        # Cross-device power (Mac→Windows / Windows→Mac) — never local shutdown by mistake.
        try:
            remote = self._maybe_handle_remote_power(text)
            if remote:
                self.ui.set_workflow_step("Finished")
                self.ui.write_log(f"AURA: {remote}")
                self.ui.set_state("LISTENING")
                append_conversation("jarvis", remote)
                return
        except Exception as e:
            print(f"[JARVIS] remote power intercept: {e}")

        if mode == "auto":
            self._fallback_local_response(text, self._preferred_provider, self._preferred_model)
            return
        if not self._loop or not self.session:
            self._fallback_local_response(text, self._preferred_provider, self._preferred_model)
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _wake_status_text(self) -> str:
        try:
            log = Path.home() / "Library" / "Logs" / "mark_xxxix_wake.log"
            if not log.exists():
                return "inactive"
            lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not lines:
                return "inactive"
            tail = lines[-1].lower()
            if "wake listener started" in tail or "clap detected" in tail or "launched jarvis" in tail:
                last_launch = ""
                for line in reversed(lines[-120:]):
                    if "launched jarvis" in line.lower():
                        last_launch = line.split("]")[0].lstrip("[")
                        break
                return f"active ({last_launch or 'recent'})"
            return "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _focus_guard_phrases(low: str) -> tuple[bool, bool]:
        """Return (want_on, want_off) from lowercase user text."""
        focus_off = any(
            m in low
            for m in (
                "выключи focus",
                "стоп focus",
                "не следи",
                "focus guard off",
                "выключи фокус",
                "выключи фокус гард",
                "перестань следить",
                "хватит следить",
                "отмени слежен",
                "отмени focus",
                "stop watching",
                "stop focus",
                "don't watch me",
                "dont watch me",
            )
        )
        # Explicit distraction-watch intent (not plain "напомни через N минут").
        focus_on = any(
            m in low
            for m in (
                "если отвлек",
                "если отвлеч",
                "если залип",
                "если отвлекусь",
                "если я отвлек",
                "focus guard",
                "watch me",
                "если буду смотреть",
                "если смотрю фильм",
                "напомни вернуться",
                "напомни про работ",
                "напомни о работ",
                "напомни про проект",
                "напомни о проект",
                "вернут к проект",
                "вернуться к проект",
                "следить если",
                "следи если",
                "следи за мной",
            )
        )
        # Avoid treating a plain timer as Focus Guard.
        if focus_on and re.search(
            r"напомни\s+(через|в\s+\d|завтра|today|tomorrow)", low
        ) and not any(
            x in low for x in ("если отвлек", "если залип", "если отвлекусь", "watch me")
        ):
            focus_on = False
        return focus_on, focus_off

    @staticmethod
    def _parse_focus_guard_args(raw: str, low: str) -> dict:
        mins = 5.0
        m = re.search(r"(\d+[.,]?\d*)\s*(минут|мин|minute|min)", low)
        if m:
            try:
                mins = float(m.group(1).replace(",", "."))
            except ValueError:
                mins = 5.0
        goal = "продолжить работу"
        gm = re.search(
            r"(?:про|о|about|to|к)\s+(.+?)(?:\s+если|\s+when|\s+for\s+\d|$)",
            raw,
            re.IGNORECASE,
        )
        if gm:
            candidate = gm.group(1).strip(" \t.,!?;:\"'")
            if candidate and len(candidate) < 80:
                goal = candidate
        # Default one_shot; user can ask for repeat.
        one_shot = not any(
            m in low
            for m in (
                "каждый раз",
                "постоянно",
                "не выключай",
                "keep watching",
                "keep reminding",
                "repeat",
                "снова и снова",
            )
        )
        return {
            "action": "start",
            "goal": goal,
            "idle_minutes": mins,
            "one_shot": one_shot,
            "language": "ru",
        }

    def _maybe_arm_focus_guard(self, text: str) -> str | None:
        """Start/stop Focus Guard from natural language without waiting for a tool call."""
        raw = (text or "").strip()
        if not raw:
            return None
        low = raw.lower()
        focus_on, focus_off = self._focus_guard_phrases(low)
        if not focus_on and not focus_off:
            return None
        if focus_off:
            return focus_guard({"action": "stop", "language": "ru"}, player=self.ui)
        return focus_guard(self._parse_focus_guard_args(raw, low), player=self.ui)

    def _maybe_handle_remote_power(self, text: str) -> str | None:
        """Deterministic Mac↔Windows power routing (bypass Live model guesswork)."""
        intent = parse_remote_power_intent(text)
        if not intent:
            return None
        args = intent.to_dispatch_args()
        print(f"[JARVIS] 📡 remote power intercept → {args}")
        try:
            self.ui.set_workflow_step(
                f"Remote {intent.action} → {intent.platform or intent.device_name or 'device'}"
            )
        except Exception:
            pass
        return dispatch_to_device(parameters=args, player=self.ui)

    def _recent_user_utterance(self, limit: int = 6) -> str:
        pending = str(getattr(self, "_pending_user_text", "") or "").strip()
        if pending:
            return pending
        try:
            entries = load_recent_conversation(limit)
        except Exception:
            return ""
        for item in reversed(entries):
            if str(item.get("role") or "").lower() in {"user", "human"}:
                return str(item.get("text") or "")
        return ""

    def _try_direct_local_actions(self, text: str) -> str | None:
        """Deterministic tool shortcuts when Live session is unavailable.

        Keeps critical OS actions (open site / camera / open app) working even
        if Gemini Live is reconnecting — plain chat models have no tools.
        """
        # Remote power first — same as Live text path.
        remote = self._maybe_handle_remote_power(text)
        if remote:
            return remote

        raw = (text or "").strip()
        if not raw:
            return None
        low = raw.lower()

        # —— Camera / webcam (before "open …" so "открой камеру" is not treated as a URL) ——
        cam_markers = (
            "камер", "webcam", "web cam", "camera",
            "что ты видишь", "что видишь", "look at me", "посмотри на меня",
        )
        if any(m in low for m in cam_markers):
            open_cam = any(
                m in low
                for m in (
                    "включи", "открой", "запусти", "turn on", "open", "start", "enable",
                )
            )
            try:
                if open_cam and not any(
                    m in low
                    for m in ("что", "видишь", "look", "see", "покажи что", "analyze")
                ):
                    app_name = "Photo Booth" if sys.platform == "darwin" else "Camera"
                    result = open_app(
                        parameters={"app_name": app_name},
                        response=None,
                        player=self.ui,
                    )
                    return result or f"Открыл {app_name}."
                result = screen_process(
                    parameters={"angle": "camera", "text": raw},
                    response=None,
                    player=self.ui,
                    session_memory=None,
                )
                return result or "Камера отработала, но результата нет."
            except Exception as e:
                return f"Камера недоступна: {e}"

        # —— Focus Guard (distract → one nudge) ——
        focus_on, focus_off = self._focus_guard_phrases(low)
        if focus_off:
            try:
                return focus_guard(
                    parameters={"action": "stop", "language": "ru"},
                    player=self.ui,
                )
            except Exception as e:
                return f"Focus Guard: {e}"
        if focus_on:
            try:
                return focus_guard(
                    parameters=self._parse_focus_guard_args(raw, low),
                    player=self.ui,
                )
            except Exception as e:
                return f"Focus Guard: {e}"

        # —— Open website / URL ——
        open_site = re.search(
            r"(?:открой(?:\s+сайт)?|зайди\s+на|откройте|open(?:\s+(?:the\s+)?(?:site|website|page))?|go\s+to|visit)\s+"
            r"(.+)$",
            raw,
            re.IGNORECASE,
        )
        if open_site:
            target = open_site.group(1).strip(" \t.,!?;:\"'")
            target = re.sub(
                r"\s+(пожалуйста|please|thanks|спасибо).*$",
                "",
                target,
                flags=re.IGNORECASE,
            ).strip()
            if target and len(target) < 120:
                try:
                    result = browser_control(
                        parameters={"action": "go_to", "url": target},
                        player=self.ui,
                    )
                    return result or f"Открыл {target}."
                except Exception as e:
                    return f"Не смог открыть сайт: {e}"

        if re.match(r"^(https?://|www\.)\S+$", raw, re.IGNORECASE) or (
            " " not in raw
            and "." in raw
            and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/\S*)?$", low)
        ):
            try:
                result = browser_control(
                    parameters={"action": "go_to", "url": raw},
                    player=self.ui,
                )
                return result or f"Открыл {raw}."
            except Exception as e:
                return f"Не смог открыть сайт: {e}"

        return None

    def _fallback_local_response(self, text: str, preferred_provider: str = "auto", preferred_model: str = "") -> None:
        try:
            # Prefer real local tools over a tool-less LLM refusal.
            direct = self._try_direct_local_actions(text)
            if direct:
                self.ui.set_workflow_step("Finished")
                self.ui.write_log(f"AURA: {direct}")
                self.ui.set_state("LISTENING")
                append_conversation("jarvis", direct)
                return

            profile = analyze_task(text)
            # Keep "Thinking" until a real search/tool step is reported via on_progress.
            routed = generate_text(
                text,
                task_type=profile.category,
                preferred_provider=preferred_provider,
                preferred_model=preferred_model,
            )
            self.ui.set_workflow_step("Finished")
            self.ui.write_log(f"AURA: {routed.text}")
            self.ui.set_state("LISTENING")
            self.ui.set_ai_status(
                model=routed.model,
                provider=routed.provider,
                queue=usage_stats().queued,
                requests_left=usage_stats().requests_left,
                tier=usage_stats().tier,
                blocked_heavy=usage_stats().blocked_heavy_tasks,
                latency_ms=routed.latency_ms,
                status=f"fallback/{routed.routed_task}",
                wake=self._wake_status_text(),
            )
            append_conversation("jarvis", routed.text)
            append_conversation("meta", f"model={routed.model};provider={routed.provider};task={routed.routed_task};fallback={routed.fallback_depth}")
        except ModelRouterError as e:
            self.ui.set_workflow_step("Finished")
            self.ui.set_state("LISTENING")
            self.ui.write_log(f"ERR: model_router {e}")

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
            if value:
                self._last_output_audio_at = time.monotonic()
        # The UI window may be torn down (closed) while audio tasks are still
        # winding down; ignore the resulting "C/C++ object deleted" race.
        try:
            if value:
                self.ui.set_state("SPEAKING")
            elif not self.ui.muted:
                self.ui.set_state("LISTENING")
        except RuntimeError:
            pass

    def _voice_log(self, message: str, min_interval: float = 1.0):
        now = time.monotonic()
        if now - self._last_voice_log_at >= min_interval:
            self._last_voice_log_at = now
            print(f"[JARVIS][voice] {message}")
            try:
                self.ui.write_log(f"VOICE: {message}")
            except Exception:
                pass

    def _output_busy(self) -> bool:
        with self._speaking_lock:
            speaking = self._is_speaking
            last_audio = self._last_output_audio_at
        return speaking or (time.monotonic() - last_audio) < self._playback_grace_seconds

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    _NOTIFY_LANG_NAMES = {
        "ru": "Russian", "en": "English", "tr": "Turkish", "az": "Azerbaijani",
    }

    def speak_notification(self, text: str, language: str = "auto") -> None:
        """Speak a reminder / Focus Guard announcement in JARVIS's Live voice (Charon).

        Never uses macOS ``say`` / Milena / any system TTS. Mute only blocks the
        microphone — output still goes through Gemini Live. If Live is not ready,
        raises so Focus Guard / ReminderEngine can retry.
        """
        try:
            self.ui.add_activity("Focus Guard", text)
        except Exception:
            pass

        if not self._loop or not self.session:
            raise RuntimeError("live Jarvis voice session not ready")

        lang_key = (language or "auto").strip().lower()[:2]
        if lang_key and lang_key not in ("au", "a"):
            lang_name = self._NOTIFY_LANG_NAMES.get(lang_key, lang_key)
        else:
            lang_name = "the user's language"
        directive = (
            f"[NOTIFICATION] Speak this out loud right now in {lang_name}, "
            f"in your normal AURA voice, short and natural — do not stay silent, "
            f'do not answer in text only: "{text}"'
        )
        muted = False
        try:
            muted = bool(self.ui.muted)
        except Exception:
            muted = False

        async def _deliver() -> None:
            # When the mic is muted no PCM is flowing; flush + send realtime TEXT
            # so Live still produces AUDIO in Charon's (Jarvis) voice.
            if muted:
                try:
                    await self.session.send_realtime_input(audio_stream_end=True)
                except Exception:
                    pass
            try:
                await self.session.send_realtime_input(text=directive)
            except Exception:
                await self.session.send_client_content(
                    turns={"parts": [{"text": directive}]},
                    turn_complete=True,
                )

        fut = asyncio.run_coroutine_threadsafe(_deliver(), self._loop)
        fut.result(timeout=8)
        try:
            self.ui.write_log(
                f"FOCUS: AURA voice nudge{' (mic muted)' if muted else ''}: {text[:120]}"
            )
        except Exception:
            pass

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:220]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        if not self._loop or not self.session:
            return
        low = short.lower()
        permissionish = any(
            k in low
            for k in (
                "permission",
                "screen recording",
                "camera",
                "microphone",
                "accessibility",
                "system settings",
                "relaunch",
                "api key",
            )
        )
        if permissionish or tool_name == "screen_process":
            directive = (
                f"[TOOL ERROR] {tool_name} failed. Reason: {short}. "
                "Tell the user this exact problem clearly and warmly — like a friend, "
                "but do NOT hide it behind 'my eyes are broken'. "
                "If permissions/settings are mentioned, say what to turn on and that a full relaunch may be needed. "
                "Use the user's language. Keep it short."
            )
        else:
            directive = (
                f"[TOOL ERROR] Tell the user casually like a friend that {tool_name} failed. "
                f"Reason: {short}. Keep it short and warm — no 'Sir', no corporate tone. "
                "Use the user's language."
            )
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": directive}]},
                turn_complete=True,
            ),
            self._loop,
        )

    def _device_context_for_prompt(self) -> str:
        """Tell Live which OS this is + which linked devices exist (remote routing)."""
        try:
            from core.platform_detect import normalize_os, platform_label
            from jarvis_ui.device_sync import default_device_name, start_device_sync

            os_key = normalize_os()
            os_label = platform_label()
            this_name = default_device_name()
            lines = [
                "[THIS DEVICE]",
                f"You are running on: {os_label} (platform={os_key}), name “{this_name}”.",
                "Local tools (computer_settings, open_app, …) act ONLY on this machine.",
                "If the user names a different OS or another device, use dispatch_to_device.",
            ]
            try:
                snap = start_device_sync().refresh_now()
                devices = list(snap.get("devices") or [])
            except Exception:
                devices = []
            others = [
                d
                for d in devices
                if not d.get("isThisDevice") and not d.get("is_this_device")
            ]
            if others:
                lines.append("[LINKED DEVICES]")
                for d in others[:8]:
                    name = d.get("name") or "device"
                    plat = d.get("platform") or "?"
                    online = "online" if d.get("online") else "offline"
                    lines.append(f"- {name} ({plat}, {online})")
                lines.append(
                    "Remote shutdown/restart needs Devices → Allow remote system on the target."
                )
            else:
                lines.append(
                    "[LINKED DEVICES]\nNone linked yet — remote control unavailable until another AURA signs in."
                )
            return "\n".join(lines) + "\n\n"
        except Exception as e:
            print(f"[JARVIS] device context: {e}")
            return ""

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        recent_str = format_recent_conversation_for_prompt()
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )
        speech_ctx = (
            "[VOICE RECOGNITION HINTS]\n"
            "The user may speak any language — Russian, English, Turkish, Azerbaijani, or others. "
            "Voice transcription may contain mistakes. Interpret intent generously. "
            "Common corrections: 'випить' means 'выпить', 'таймар/таймир' means 'таймер', "
            "'напомнить меня' means 'напомни мне'.\n"
            "[TONE]\n"
            "Talk back like a close friend on a call — short, casual, warm, a little funny. "
            "Answer identity questions directly and warmly — never brush off with 'какая разница'. "
            "Keep replies tight and human, the way a buddy would actually talk.\n\n"
        )
        lang_ctx = language_instruction()
        device_ctx = self._device_context_for_prompt()

        parts = [time_ctx, lang_ctx, speech_ctx]
        if device_ctx:
            parts.append(device_ctx)
        if mem_str:
            parts.append(mem_str)
        if recent_str:
            parts.append(recent_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    prefix_padding_ms=200,
                    silence_duration_ms=550,
                ),
                activity_handling=types.ActivityHandling.NO_INTERRUPTION,
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ALL_INPUT,
            ),
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _say_startup_greeting_once(self) -> None:
        if self._startup_greeting_done:
            return
        self._startup_greeting_done = True
        self.ui.write_log(f"AURA: {DEFAULT_GREETING_HINT}")
        await self.session.send_client_content(
            turns={"parts": [{"text": (
                "Give a warm, brief startup greeting in the user's language — "
                f"casual buddy tone like: \"{DEFAULT_GREETING_HINT}\" "
                "Keep it to one short sentence."
            )}]},
            turn_complete=True,
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")
        try:
            self.ui.set_workflow_step(f"Running {name.replace('_', ' ')}")
        except Exception:
            pass

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "autonomous_mode":
                r = await loop.run_in_executor(None, lambda: autonomous_mode(parameters=args, response=None, player=self.ui))
                result = r or "Autonomous mode updated."

            elif name == "focus_guard":
                if not args.get("language"):
                    from core.language import detect_language, load_language
                    sample = args.get("goal") or args.get("message") or ""
                    args["language"] = detect_language(sample) if sample else load_language()
                r = await loop.run_in_executor(
                    None,
                    lambda: focus_guard(parameters=args, response=None, player=self.ui),
                )
                result = r or "Focus Guard updated."

            elif name == "telegram_control":
                r = await loop.run_in_executor(
                    None,
                    lambda: telegram_control(
                        parameters=args, response=None, player=self.ui, speak=self.speak
                    ),
                )
                result = r or "Telegram action complete."

            elif name == "automation_workflow":
                r = await loop.run_in_executor(None, lambda: automation_workflow(parameters=args, response=None, player=self.ui))
                result = r or "Workflow action complete."
            elif name == "communication_module":
                r = await loop.run_in_executor(None, lambda: communication_module(parameters=args, response=None, player=self.ui))
                result = r or "Communication action complete."
            elif name == "media_downloader":
                r = await loop.run_in_executor(None, lambda: media_downloader(parameters=args, response=None, player=self.ui))
                result = r or "Media downloader action complete."

            elif name == "reminder":
                if not args.get("language"):
                    from core.language import detect_language
                    args["language"] = detect_language(args.get("message", ""))
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                r = await loop.run_in_executor(
                    None,
                    lambda: screen_process(
                        parameters=args,
                        response=None,
                        player=self.ui,
                        session_memory=None,
                    )
                )
                result = r or "Vision finished, but no result was returned."

            elif name == "computer_settings":
                # If Live guessed local shutdown but the user named another device,
                # redirect to dispatch_to_device (Mac↔Windows / etc.).
                action = str(args.get("action") or "").strip().lower()
                if not action and args.get("description"):
                    action = str(args.get("description") or "").strip().lower()
                recent = self._recent_user_utterance()
                redirect = should_redirect_local_power(action, recent)
                if redirect is None and args.get("description"):
                    redirect = should_redirect_local_power(
                        action, str(args.get("description") or "")
                    )
                if redirect is not None:
                    print(f"[JARVIS] 📡 redirect local {action} → remote {redirect}")
                    r = await loop.run_in_executor(
                        None,
                        lambda: dispatch_to_device(
                            parameters=redirect.to_dispatch_args(),
                            player=self.ui,
                        ),
                    )
                    result = r or "Remote power request finished with no details."
                else:
                    r = await loop.run_in_executor(
                        None,
                        lambda: computer_settings(
                            parameters=args, response=None, player=self.ui
                        ),
                    )
                    result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "dispatch_to_device":
                r = await loop.run_in_executor(
                    None, lambda: dispatch_to_device(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        if result and name != "save_memory":
            append_conversation("tool", f"{name}: {str(result)[:900]}")
        try:
            self.ui.add_activity(f"Used {name.replace('_', ' ')}", str(result)[:600])
        except Exception:
            pass
        try:
            self._emit_preview(name, args, result)
        except Exception as e:
            print(f"[JARVIS] ⚠️ preview: {e}")

        ok = tool_result_ok(result) if name != "save_memory" else True
        # Give the Live model an explicit success/failure signal so it cannot
        # invent "готово" when the tool failed or only asked for confirmation.
        payload: dict = {"result": result, "ok": ok}
        if not ok:
            payload["result"] = (
                f"NOT DONE. Tell the user this exact outcome, do not claim success: {result}"
            )
        else:
            payload["result"] = (
                f"DONE. Tell the user this exact outcome (do not invent extras): {result}"
            )
        return types.FunctionResponse(
            id=fc.id, name=name,
            response=payload,
        )

    _PATH_RE = re.compile(r"(~?/[^\s'\"]+?\.[A-Za-z0-9]{1,6})")
    _CODE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".json", ".md",
                  ".txt", ".java", ".cpp", ".c", ".go", ".rs", ".sh", ".sql", ".yml", ".yaml")
    _PREVIEW_TEXT_TOOLS = {
        "web_search", "automation_workflow", "agent_task", "screen_process",
        "flight_finder", "weather_report",
    }

    def _emit_preview(self, name: str, args: dict, result) -> None:
        ui = self.ui
        if not hasattr(ui, "show_preview") or not result:
            return
        text = str(result)

        # 1) Artifact-producing tools: detect a saved file path.
        if name in ("dev_agent", "code_helper", "file_processor", "game_updater"):
            path = self._extract_artifact_path(text)
            if path:
                low = path.lower()
                if low.endswith((".html", ".htm")):
                    ui.show_preview("web", Path(path).name, path, path)
                    return
                if low.endswith(self._CODE_EXTS):
                    try:
                        content = Path(path).expanduser().read_text(encoding="utf-8", errors="ignore")
                        ui.show_preview("code", Path(path).name, content, path)
                        return
                    except Exception:
                        pass
                ui.show_preview("text", name, text, path)
                return
            ui.show_preview("text", name.replace("_", " ").title(), text)
            return

        # 2) Text-result tools: show the result as a readable card.
        if name in self._PREVIEW_TEXT_TOOLS and len(text.strip()) > 12:
            ui.show_preview("text", name.replace("_", " ").title(), text)

    def _extract_artifact_path(self, text: str) -> str | None:
        candidates = self._PATH_RE.findall(text or "")
        # Prefer an index.html / .html path, else the first code/file path.
        html = [c for c in candidates if c.lower().endswith((".html", ".htm"))]
        if html:
            return html[-1]
        for c in candidates:
            if c.lower().endswith(self._CODE_EXTS):
                return c
        return candidates[-1] if candidates else None

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            try:
                await self.session.send_realtime_input(media=msg)
            except Exception as e:
                print(f"[JARVIS] ❌ Send realtime: {e}")
                raise

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if status:
                self._voice_log(f"mic status: {status}", min_interval=5.0)
            # Free preview: stop sending mic audio after the one allowed turn.
            voice_ok = True
            try:
                from jarvis_ui.preview_access import allow_live_mic

                voice_ok = bool(allow_live_mic())
            except Exception:
                voice_ok = True
            if self.ui.muted or not voice_ok:
                return
            try:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                self.ui.set_user_voice_level(rms)
            except RuntimeError:
                pass
            if not self._output_busy():
                data = indata.tobytes()
                def _enqueue_audio():
                    try:
                        self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                    except asyncio.QueueFull:
                        try:
                            self.out_queue.get_nowait()
                            self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                            self._voice_log("mic queue full; dropped oldest chunk", min_interval=5.0)
                        except Exception:
                            pass
                loop.call_soon_threadsafe(_enqueue_audio)

        try:
            sd.query_devices(kind="input")
        except Exception:
            self.ui.write_log(
                "ERR: No microphone detected. Connect a mic and grant Microphone "
                "permission in System Settings → Privacy & Security → Microphone."
            )
            print("[JARVIS] ❌ No input device available.")
            raise RuntimeError("No microphone input device available")

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                self.ui.write_log("SYS: Microphone active — listening.")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            self.ui.write_log(
                f"ERR: Microphone error: {e}. Check macOS Microphone permission "
                "for your terminal/Python in System Settings → Privacy & Security."
            )
            raise

    def _emit_user_turn(self, in_buf: list) -> bool:
        """Persist + display the user's transcribed turn. Returns True if emitted."""
        full_in = " ".join(in_buf).strip()
        if not full_in:
            return False
        try:
            from jarvis_ui.preview_access import note_user_turn

            if not note_user_turn():
                # Block further free voice; UI shows Pro gate + mutes (via Qt signal).
                try:
                    self.ui.request_preview_gate()
                except Exception:
                    try:
                        self.ui.write_log("SYS: Free preview used — subscribe for more voice.")
                    except Exception:
                        pass
                return False
        except Exception:
            pass
        detect_and_save_language(full_in)
        self.ui.add_user_message(full_in)
        append_conversation("user", full_in)
        remember_vector(full_in, kind="user_message")
        return True

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []
        user_emitted = False

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        # Never let a full playback queue crash the receive loop
                        # (that would force a mid-conversation reconnect). Drop the
                        # oldest buffered chunk and keep the newest audio instead.
                        try:
                            self.audio_in_queue.put_nowait(response.data)
                        except asyncio.QueueFull:
                            try:
                                self.audio_in_queue.get_nowait()
                                self.audio_in_queue.put_nowait(response.data)
                                self._voice_log("playback queue full; dropped oldest chunk",
                                                min_interval=5.0)
                            except Exception:
                                pass

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                # Show the user's message before the assistant's
                                # streamed reply so the thread stays in order.
                                if not user_emitted and in_buf:
                                    user_emitted = self._emit_user_turn(in_buf)
                                out_buf.append(txt)
                                try:
                                    self.ui.stream_delta(txt)
                                except Exception:
                                    pass

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._pending_user_text = " ".join(in_buf).strip()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            if not user_emitted:
                                self._emit_user_turn(in_buf)
                            in_buf = []
                            user_emitted = False
                            self._pending_user_text = ""

                            full_out = " ".join(out_buf).strip()
                            self.ui.stream_end(full_out)
                            if full_out:
                                append_conversation("jarvis", full_out)
                                remember_vector(full_out, kind="assistant_message")
                                stats = usage_stats()
                                self.ui.set_ai_status(
                                    model=getattr(self, "_live_model", LIVE_MODEL),
                                    provider="gemini-live",
                                    queue=stats.queued,
                                    requests_left=stats.requests_left,
                                    tier=stats.tier,
                                    blocked_heavy=stats.blocked_heavy_tasks,
                                    latency_ms="live",
                                    status="connected",
                                    wake=self._wake_status_text(),
                                )
                            out_buf = []

                    if response.tool_call:
                        # Persist the voice utterance before tools so remote-power
                        # redirect can read what the user actually said.
                        if not user_emitted and in_buf:
                            user_emitted = self._emit_user_turn(in_buf)
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.25,
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                        and (time.monotonic() - self._last_output_audio_at) > self._playback_grace_seconds
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                self._last_output_audio_at = time.monotonic()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        from core.gemini_models import (
            is_model_unavailable_error,
            live_model_candidates,
            mark_bad,
            mark_good,
        )

        backoff = 3
        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")

                # Re-read the key/version every attempt so a renewed key is
                # picked up automatically without restarting the app.
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": _get_live_api_version()},
                )
                config = self._build_config()

                # Try live model chain — Gemini won't auto-pick when one id dies.
                last_connect_err: BaseException | None = None
                connected = False
                for live_model in live_model_candidates():
                    try:
                        print(f"[JARVIS] 🔌 Live model: {live_model}")
                        async with (
                            client.aio.live.connect(model=live_model, config=config) as session,
                            asyncio.TaskGroup() as tg,
                        ):
                            self.session = session
                            self._live_model = live_model
                            mark_good(live_model, "live")
                            self._loop = asyncio.get_event_loop()
                            self.audio_in_queue = asyncio.Queue(maxsize=200)
                            self.out_queue = asyncio.Queue(maxsize=200)
                            self._turn_done_event = asyncio.Event()

                            backoff = 3  # reset after a successful connection
                            connected = True
                            print(f"[JARVIS] ✅ Connected ({live_model}).")
                            self.ui.set_state("LISTENING")
                            self.ui.write_log("SYS: AURA online.")
                            await self._say_startup_greeting_once()

                            tg.create_task(self._send_realtime())
                            tg.create_task(self._listen_audio())
                            tg.create_task(self._receive_audio())
                            tg.create_task(self._play_audio())
                        break
                    except Exception as e:
                        last_connect_err = e
                        leaves = _flatten_exceptions(e)
                        # Only hop models on connect/model-unavailable failures,
                        # not after a healthy session dies mid-flight.
                        if connected:
                            raise
                        if any(is_model_unavailable_error(err) for err in leaves) or (
                            not leaves and is_model_unavailable_error(e)
                        ):
                            mark_bad(live_model)
                            print(f"[JARVIS] ⚠️  Live model unavailable: {live_model}")
                            continue
                        # Auth / other errors: don't burn the whole chain.
                        raise
                if not connected and last_connect_err is not None:
                    raise last_connect_err

            except Exception as e:
                # TaskGroup raises ExceptionGroup; flatten to inspect real causes.
                errors = _flatten_exceptions(e)
                kind = "transient"
                for err in errors:
                    print(f"[JARVIS] ⚠️ {err}")
                    if _classify_connection_error(err) == "auth":
                        kind = "auth"
                traceback.print_exc()

                self.set_speaking(False)
                self.session = None

                if kind == "auth":
                    self.ui.set_state("THINKING")
                    self.ui.write_log(
                        "ERR: Gemini API key is invalid or expired. "
                        "Get a new free key at https://aistudio.google.com/apikey "
                        "and paste it via the settings panel (or config/api_keys.json)."
                    )
                    print("[JARVIS] 🔑 Invalid/expired key. Waiting for a new key...")
                    # Slow retry — picks up a renewed key automatically.
                    await asyncio.sleep(15)
                    continue

                self.ui.set_state("THINKING")
                self.ui.write_log(f"SYS: Connection lost, reconnecting in {backoff}s...")
                print(f"[JARVIS] 🔄 Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # exponential backoff, capped

def _ensure_double_clap_wake() -> None:
    """Install/refresh the double-clap wake agent (LaunchAgent / schtasks / systemd)."""
    try:
        from jarvis_ui.wake_bootstrap import is_wake_enabled_pref, set_wake_enabled

        if not is_wake_enabled_pref():
            return
        # Re-run install so login agent stays on the current binary after updates.
        set_wake_enabled(True)
    except Exception:
        try:
            from launcher.install_wake_agent import install as install_wake

            install_wake()
        except Exception as e:
            print(f"[Wake] Could not install double-clap listener: {e}")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--jarvis-apply-update":
        from pathlib import Path
        from core.updater.installer import apply_update
        package = Path(sys.argv[2])
        parent_pid = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        raise SystemExit(apply_update(package, parent_pid=parent_pid))

    # Background double-clap agent (LaunchAgent). No UI — for all installed users.
    if len(sys.argv) >= 2 and sys.argv[1] in ("--wake-listener", "--aura-wake"):
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from launcher.wake_listener import main as wake_main

        wake_main()
        return

    # Keep double-clap wake alive for this machine (and for future public installs).
    # Defer so it never races with first-run UI paint / SIGTRAPs.
    def _wake_later():
        try:
            _ensure_double_clap_wake()
        except Exception as e:
            print(f"[Wake] Could not install double-clap listener: {e}")

    threading.Thread(
        target=_wake_later, daemon=True, name="WakeAgentInstall"
    ).start()

    # Disable macOS window restoration (crash-recovery sheets after setup).
    try:
        if sys.platform == "darwin":
            from Foundation import NSUserDefaults

            NSUserDefaults.standardUserDefaults().setBool_forKey_(
                False, "NSQuitAlwaysKeepsWindows"
            )
    except Exception:
        pass

    # Windows Privacy settings list apps by AppUserModelID when possible.
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "app.hiaura.aura.desktop"
            )
    except Exception:
        pass

    # Double-click on DMG → auto-copy to Applications → relaunch → exit.
    # Onboarding runs in the installed app (not from the read-only disk).
    try:
        from jarvis_ui.install_gate import run_install_gate_if_needed

        if run_install_gate_if_needed():
            return
    except Exception as e:
        print(f"[AURA] Install gate skipped due to error: {e}")

    # First-run welcome → permissions → Gemini key, then desktop with one free preview.
    # Pro is required after the preview (soft Cursor-style gate inside the main UI).
    try:
        from jarvis_ui.onboarding import run_onboarding_if_needed

        run_onboarding_if_needed()
    except Exception as e:
        print(f"[AURA] Onboarding skipped due to error: {e}")

    ui = JarvisUI("")
    # Guarantee setup card after main window is up (fallback if key skipped).
    try:
        from PyQt6.QtCore import QTimer

        if not ui._win._ready:
            QTimer.singleShot(250, ui._win._ensure_setup_overlay)
    except Exception:
        pass

    def _openclaw_progress(msg: str) -> None:
        ui.write_log(f"OpenClaw: {msg}")

    def _start_openclaw() -> None:
        try:
            from core.integrations.openclaw import bootstrap_and_start_gateway, stop_gateway

            atexit.register(stop_gateway)
            gw_url = bootstrap_and_start_gateway(on_progress=_openclaw_progress)
            ui.write_log(f"SYS: OpenClaw gateway online — {gw_url}")
        except Exception as e:
            ui.write_log(f"SYS: OpenClaw fallback mode ({e})")

    threading.Thread(target=_start_openclaw, daemon=True, name="OpenClawBootstrap").start()

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
