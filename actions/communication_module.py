import json
import subprocess
import urllib.parse
from dataclasses import dataclass
from typing import Any

from actions.send_message import send_message
from actions.telegram_control import telegram_control


SUPPORTED_APPS = ["Phone", "Messages", "WhatsApp", "Telegram", "Discord", "Email"]


@dataclass
class ContactMatch:
    name: str
    phones: list[str]
    emails: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "phones": self.phones, "emails": self.emails}


def _normalize_contact(name: str) -> str:
    return (name or "").strip()


def _as_script_text(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _run_osascript(script: str, timeout: int = 10) -> str:
    out = subprocess.check_output(
        ["osascript", "-e", script],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return out.strip()


def _open_url(url: str) -> bool:
    result = subprocess.run(["open", url], capture_output=True, text=True, timeout=10)
    return result.returncode == 0


def _clean_phone(value: str) -> str:
    allowed = "+0123456789"
    phone = "".join(ch for ch in (value or "") if ch in allowed)
    digits = "".join(ch for ch in phone if ch.isdigit())
    return phone if len(digits) >= 5 else ""


def _find_contact_macos(query: str) -> list[ContactMatch]:
    q = _as_script_text(query)
    script = f'''
    tell application "Contacts"
      set q to {q}
      set rows to {{}}
      repeat with p in people
        set nm to name of p as text
        ignoring case
        if nm contains q then
          set phoneList to {{}}
          repeat with ph in phones of p
            copy (value of ph as text) to end of phoneList
          end repeat
          set emailList to {{}}
          repeat with em in emails of p
            copy (value of em as text) to end of emailList
          end repeat
          set AppleScript's text item delimiters to ";;"
          set phonesJoined to phoneList as text
          set emailsJoined to emailList as text
          set AppleScript's text item delimiters to ""
          copy nm & "||" & phonesJoined & "||" & emailsJoined to end of rows
        end if
        end ignoring
      end repeat
      set AppleScript's text item delimiters to linefeed
      set joinedRows to rows as text
      set AppleScript's text item delimiters to ""
      return joinedRows
    end tell
    '''
    try:
        out = _run_osascript(script)
        matches: list[ContactMatch] = []
        for line in out.splitlines():
            parts = line.split("||")
            if not parts or not parts[0].strip():
                continue
            phones = [p.strip() for p in (parts[1] if len(parts) > 1 else "").split(";;") if p.strip()]
            emails = [e.strip() for e in (parts[2] if len(parts) > 2 else "").split(";;") if e.strip()]
            matches.append(ContactMatch(parts[0].strip(), phones, emails))
        return matches[:8]
    except Exception:
        return []


def _best_contact(query: str) -> ContactMatch | None:
    matches = _find_contact_macos(query)
    if not matches:
        return None
    q = query.strip().lower()
    for match in matches:
        if match.name.lower() == q:
            return match
    return matches[0]


def _resolve_receiver(contact: str) -> tuple[str, ContactMatch | None, str, str]:
    direct_phone = _clean_phone(contact)
    if direct_phone:
        return contact, None, direct_phone, ""
    if "@" in contact:
        return contact, None, "", contact
    match = _best_contact(contact)
    phone = _clean_phone(match.phones[0]) if match and match.phones else _clean_phone(contact)
    email = match.emails[0] if match and match.emails else (contact if "@" in contact else "")
    display = match.name if match else contact
    return display, match, phone, email


def _send_email(receiver: str, message: str) -> str:
    body = _as_script_text(message)
    rcpt = _as_script_text(receiver)
    script = f'''
    tell application "Mail"
      set newMessage to make new outgoing message with properties {{subject:"Message from JARVIS", content:{body} & return & return}}
      tell newMessage
        make new to recipient at end of to recipients with properties {{address:{rcpt}}}
        send
      end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=False)
    return f"Email sent to {receiver}."


def _send_messages(phone_or_contact: str, message: str) -> str:
    target = _as_script_text(phone_or_contact)
    body = _as_script_text(message)
    script = f'''
    tell application "Messages"
      set targetService to missing value
      repeat with svc in services
        if service type of svc is iMessage then
          set targetService to svc
          exit repeat
        end if
      end repeat
      if targetService is missing value then
        set targetService to 1st service
      end if
      set targetBuddy to buddy {target} of targetService
      send {body} to targetBuddy
    end tell
    '''
    try:
        _run_osascript(script, timeout=8)
        return f"Message sent to {phone_or_contact} via Messages."
    except Exception:
        pass

    encoded_to = urllib.parse.quote(phone_or_contact)
    encoded_body = urllib.parse.quote(message)
    for url in (f"sms:{encoded_to}&body={encoded_body}", f"imessage:{encoded_to}"):
        if _open_url(url):
            return f"Messages opened for {phone_or_contact} with the message prepared."
    return "Could not open Messages."


def _send_whatsapp(phone_or_contact: str, message: str, fallback_contact: str) -> str:
    phone = _clean_phone(phone_or_contact)
    if phone:
        encoded = urllib.parse.quote(message)
        if _open_url(f"whatsapp://send?phone={phone}&text={encoded}"):
            return f"WhatsApp opened for {fallback_contact} with the message prepared."
    return send_message(
        parameters={"receiver": fallback_contact, "message_text": message, "platform": "WhatsApp"},
        response=None,
        player=None,
        session_memory=None,
    )


def _call_phone(phone_or_contact: str, display: str) -> str:
    phone = _clean_phone(phone_or_contact)
    if not phone:
        return f"No phone number found for {display}."
    for url in (f"facetime-audio://{phone}", f"tel:{phone}"):
        if _open_url(url):
            return f"Call started for {display}."
    return f"Could not start a phone call for {display}."


def _call_whatsapp(phone_or_contact: str, display: str) -> str:
    phone = _clean_phone(phone_or_contact)
    if phone and _open_url(f"whatsapp://call?phone={phone}"):
        return f"WhatsApp call opened for {display}."
    if phone and _open_url(f"whatsapp://send?phone={phone}"):
        return f"WhatsApp chat opened for {display}. Press the call button to start."
    return f"No usable WhatsApp phone number found for {display}."


def communication_module(parameters: dict[str, Any], response=None, player=None):
    action = str((parameters or {}).get("action", "find_contact")).strip().lower()
    contact = _normalize_contact((parameters or {}).get("contact") or (parameters or {}).get("receiver") or "")
    message = str((parameters or {}).get("message") or (parameters or {}).get("message_text") or "").strip()
    app = str((parameters or {}).get("app") or (parameters or {}).get("platform") or "Phone").strip()
    require_confirmation = bool((parameters or {}).get("require_confirmation", False))
    app_key = app.lower()

    if action == "find_contact":
        if not contact:
            return "Please provide a contact name."
        found = _find_contact_macos(contact)
        if not found:
            return f"No contact found for '{contact}'."
        return json.dumps({"query": contact, "matches": [m.as_dict() for m in found]}, ensure_ascii=False)

    if action == "call":
        if not contact:
            return "Please provide a contact to call."
        display, match, phone, email = _resolve_receiver(contact)
        if require_confirmation:
            return f"Confirm call to {display} via {app}."
        if app_key == "telegram":
            return telegram_control(parameters={"action": "call", "receiver": contact}, response=response, player=player)
        if app_key in ("phone", "facetime", "call", "messages"):
            return _call_phone(phone, display)
        if app_key == "whatsapp":
            return _call_whatsapp(phone, display)
        if app_key == "discord":
            return send_message(
                parameters={"receiver": display, "message_text": "Call me when you can.", "platform": "Discord"},
                response=response,
                player=player,
                session_memory=None,
            )
        if app_key == "email":
            return f"Email does not support calls. Use Phone, WhatsApp, Telegram, or Discord."
        return f"Unsupported calling app '{app}'. Supported: {', '.join(SUPPORTED_APPS)}."

    if action == "message":
        if not contact or not message:
            return "Please provide both contact and message."
        display, match, phone, email = _resolve_receiver(contact)
        if app_key == "email":
            if not email:
                return f"No email address found for {display}."
            return _send_email(email, message)
        if app_key in ("phone", "messages", "imessage", "sms"):
            target = phone or display
            return _send_messages(target, message)
        if app_key == "whatsapp":
            return _send_whatsapp(phone or display, message, display)
        if app_key == "telegram":
            return telegram_control(
                parameters={"action": "message", "receiver": display, "message": message},
                response=response,
                player=player,
            )
        return send_message(
            parameters={"receiver": display, "message_text": message, "platform": app},
            response=response,
            player=player,
            session_memory=None,
        )

    if action == "choose_app":
        selected = app if app in SUPPORTED_APPS else "Phone"
        return json.dumps({"selected": selected, "supported": SUPPORTED_APPS}, ensure_ascii=False)

    return "Unsupported communication action."
