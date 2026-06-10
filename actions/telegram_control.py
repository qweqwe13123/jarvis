from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08
    _PYAUTOGUI = True
except Exception as e:
    pyautogui = None
    _PYAUTOGUI = False
    _PYAUTOGUI_ERROR = e

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    try:
        cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return cfg.get("os_system", "mac").lower()
    except Exception:
        return "mac"


def _paste(text: str) -> None:
    if not _PYAUTOGUI:
        if _get_os() == "mac":
            _mac_paste(text)
            return
        raise RuntimeError(f"PyAutoGUI is unavailable on this system: {_PYAUTOGUI_ERROR}")
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("command" if _get_os() == "mac" else "ctrl", "v")
    else:
        pyautogui.write(text, interval=0.02)


def _mac_script(script: str, timeout: int = 8) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript failed")
    return result.stdout.strip()


def _mac_paste(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)
    _mac_script('tell application "System Events" to keystroke "v" using command down')


def _mac_press_enter() -> None:
    _mac_script('tell application "System Events" to key code 36')


def _mac_search_hotkey() -> None:
    _mac_script('tell application "System Events" to keystroke "k" using command down')


def _mac_fallback_search_hotkey() -> None:
    _mac_script('tell application "System Events" to keystroke "f" using command down')


def _mac_call_hotkey() -> None:
    _mac_script('tell application "System Events" to keystroke "a" using {command down, shift down}')


def _open_telegram() -> None:
    os_name = _get_os()
    if os_name == "mac":
        result = subprocess.run(["open", "-a", "Telegram"], capture_output=True, timeout=10)
        if result.returncode != 0:
            subprocess.run(["open", "-a", "Telegram Desktop"], capture_output=True, timeout=10)
    elif os_name == "windows":
        subprocess.Popen("Telegram", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["telegram-desktop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)


def _open_chat(receiver: str) -> None:
    _open_telegram()
    if _get_os() == "mac" and not _PYAUTOGUI:
        try:
            _mac_search_hotkey()
            time.sleep(0.35)
            _mac_paste(receiver)
            time.sleep(1.0)
            _mac_press_enter()
            time.sleep(1.0)
        except Exception:
            _mac_fallback_search_hotkey()
            time.sleep(0.35)
            _mac_paste(receiver)
            time.sleep(1.0)
            _mac_press_enter()
            time.sleep(1.0)
        return
    if _get_os() == "mac":
        pyautogui.hotkey("command", "k")
    else:
        pyautogui.hotkey("ctrl", "k")
    time.sleep(0.35)
    _paste(receiver)
    time.sleep(1.0)
    pyautogui.press("enter")
    time.sleep(1.0)


def _mac_focused_process_name() -> str:
    try:
        return _mac_script(
            'tell application "System Events" to get name of first application process whose frontmost is true',
            timeout=4,
        )
    except Exception:
        return ""


def _message(receiver: str, text: str) -> str:
    _open_chat(receiver)
    if _get_os() == "mac":
        focused = _mac_focused_process_name().lower()
        if "telegram" not in focused:
            return f"Telegram did not become active for {receiver}; message was not sent."
    _paste(text)
    time.sleep(0.15)
    if _get_os() == "mac" and not _PYAUTOGUI:
        _mac_press_enter()
    else:
        pyautogui.press("enter")
    time.sleep(0.4)
    return f"Telegram message sent to {receiver}."


def _mac_click_call_button() -> bool:
    script = r'''
tell application "System Events"
  tell process "Telegram"
    set frontmost to true
    delay 0.2
    set candidates to every UI element of window 1 whose description contains "Call"
    if (count of candidates) > 0 then
      click item 1 of candidates
      return true
    end if
    set candidates to every button of window 1 whose description contains "Call"
    if (count of candidates) > 0 then
      click item 1 of candidates
      return true
    end if
    set candidates to every button of window 1 whose name contains "Call"
    if (count of candidates) > 0 then
      click item 1 of candidates
      return true
    end if
  end tell
end tell
return false
'''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=8)
        return "true" in result.stdout.lower()
    except Exception:
        return False


def _call(receiver: str, speak_text: str = "") -> str:
    _open_chat(receiver)
    clicked = _mac_click_call_button() if _get_os() == "mac" else False
    if not clicked:
        if _get_os() == "mac" and not _PYAUTOGUI:
            _mac_call_hotkey()
        else:
            pyautogui.hotkey("command" if _get_os() == "mac" else "ctrl", "shift", "a")
        time.sleep(0.5)
    if speak_text:
        time.sleep(3.0)
        try:
            subprocess.Popen(["say", speak_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return f"Telegram call started for {receiver}."


def telegram_control(parameters: dict, response=None, player=None, session_memory=None) -> str:
    if not _PYAUTOGUI and _get_os() != "mac":
        return f"Desktop control is unavailable on this system: {_PYAUTOGUI_ERROR}"
    params = parameters or {}
    action = (params.get("action") or "message").lower().strip()
    receiver = (params.get("receiver") or params.get("contact") or "").strip()
    message = (params.get("message") or params.get("message_text") or "").strip()
    speak_text = (params.get("speak_text") or "").strip()
    if not receiver:
        return "Please specify the Telegram contact."
    try:
        if action in ("message", "send", "text"):
            if not message:
                return "Please specify the Telegram message text."
            result = _message(receiver, message)
        elif action in ("call", "voice_call", "audio_call"):
            result = _call(receiver, speak_text=speak_text)
        else:
            result = f"Unknown Telegram action: {action}"
    except Exception as e:
        result = f"Telegram action failed: {e}"
    print(f"[Telegram] {result}")
    if player:
        player.write_log(f"[Telegram] {result}")
    return result
