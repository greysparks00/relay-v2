"""Resolve standalone voice commands locally; leave conversational interpretation to the agent."""

import json
import re

from llm.system_info import system_command
from llm.timer_commands import NUMBERS, timer_command

TITLE = r'(?:"[^"\n]+"|[\w-]+(?: [\w-]+){0,7})'
TEXT = r'(?:"[^"\n]+"|[\w-]+(?: [\w-]+){0,40})'
DAY = r"(?:\d{4}-\d{2}-\d{2}|today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
UNIT = r"(?:(?:US |degrees? |fluid )?[a-z°_]+)"
ZONE = r"(?:[a-z_]+(?:/[a-z_+-]+){1,2}|UTC|Chicago|London|New York|Los Angeles|Tokyo)"
CITIES = {"chicago": "America/Chicago", "london": "Europe/London", "new york": "America/New_York",
          "los angeles": "America/Los_Angeles", "tokyo": "Asia/Tokyo", "utc": "UTC"}

# Optional quoted strings make exact note names and replacement text unambiguous.
NOTE_COMMANDS = (
    ("remember_fact", rf'remember (?:the )?fact (?P<name>{TITLE}) (?:as|is) (?P<fact>{TEXT})'),
    ("remember_fact", rf'remember that (?P<name>my [\w-]+(?: [\w-]+){{0,4}}) is (?P<fact>{TEXT})'),
    ("recall_facts", rf'(?:search (?:my )?(?:memory|facts) for|what do you remember about) (?P<query>{TITLE})'),
    ("read_fact", rf'(?:read|show) (?:the |my )?(?:fact|memory) (?P<name>{TITLE})'),
    ("edit_fact", rf'(?:in|edit) (?:the )?fact (?P<name>{TITLE}),? replace "(?P<old_text>[^"\n]+)" with "(?P<new_text>[^"\n]*)"'),
    ("forget_fact", rf'forget (?:the |my )?fact (?P<name>{TITLE})'),
    ("save_handoff", rf'save (?:a )?handoff (?:for )?(?P<topic>{TITLE}) (?:as|saying) (?P<summary>{TEXT})'),
    ("resume_handoff", rf'(?:resume|read) (?:the )?handoff (?:for )?(?P<topic>{TITLE})'),
    ("delete_handoff", rf'delete (?:the )?handoff (?:for )?(?P<topic>{TITLE})'),
)


def command_text(message: str) -> str:
    text = re.sub(r"^(?:hey relay,?\s+)?(?:please\s+)?", "", message.strip(), flags=re.I)
    return text.rstrip(".?!").strip()


def direct_command(message: str):
    text = message.strip()
    if text == "/tool" or text.startswith("/tool "):
        match = re.fullmatch(r"/tool\s+([\w.-]+)(?:\s+(.+))?", text, re.S)
        if not match:
            raise ValueError("Use /tool followed by the tool name and an optional JSON object.")
        try:
            args = json.loads(match[2] or "{}")
        except ValueError as error:
            raise ValueError("Tool arguments must be a JSON object.") from error
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        return match[1], args

    text = command_text(text)
    if hardware := system_command(text):
        return hardware
    timer = timer_command(text)
    if timer:
        return timer
    plain = text.casefold()
    if plain in {"what is the current date and time", "what's the current date and time"}:
        return "get_current_datetime", {}
    # An unquoted condition or second instruction needs the conversation model.
    outside_quotes = re.sub(r'"[^"\n]*"', "", text)
    if re.search(r"\b(then|if|unless|also|except|before you|after you)\b", outside_quotes, re.I):
        return None
    if re.search(r"\band\b", outside_quotes, re.I) and not plain.startswith(("pick between ", "pick one of ")):
        return None
    if plain in {"what time is it", "what's the time", "what is the current time", "what's today's date",
                 "what is today's date", "what day is it"}:
        return "get_current_datetime", {}
    if plain in {"list handoffs", "list my handoffs", "list conversation handoffs"}:
        return "list_handoffs", {}
    if plain in {"list my facts", "list recent memories"}:
        return "recall_facts", {"query": ""}
    for tool, pattern in NOTE_COMMANDS:
        if match := re.fullmatch(pattern, text, re.I):
            args = {key: value.removeprefix('"').removesuffix('"') for key, value in match.groupdict().items()}
            if plain.startswith("remember that "):
                args["fact"] = f"{args['name']} is {args['fact']}"
            return tool, args

    if match := re.fullmatch(rf"(?:convert|what is|what's) (-?\d+(?:\.\d+)?) ({UNIT}) (?:in|to) ({UNIT})", text, re.I):
        return "convert_units", {"value": float(match[1]), "from_unit": match[2], "to_unit": match[3]}
    if match := re.fullmatch(rf"how many days (?:from ({DAY}) )?(?:until|to) ({DAY})", text, re.I):
        return "date_math", {"start": match[1] or "today", "end": match[2]}
    if match := re.fullmatch(rf"(?:what (?:day|date) is )?(\d{{1,6}}|[a-z]+) (days?|weeks?) (from|after|before) ({DAY})", text, re.I):
        count = int(match[1]) if match[1].isdigit() else NUMBERS.get(match[1].casefold())
        if count is not None:
            key = "weeks" if match[2].lower().startswith("week") else "days"
            return "date_math", {"start": match[4], key: -count if match[3].lower() == "before" else count}
    if match := re.fullmatch(rf"convert (\d{{4}}-\d{{2}}-\d{{2}})[ T](\d{{1,2}}:\d{{2}}) (?:from |in )?({ZONE}) to ({ZONE})", text, re.I):
        source, target = [CITIES.get(zone.casefold(), zone) for zone in match.groups()[2:]]
        return "convert_timezone", {"local_datetime": f"{match[1]}T{match[2].zfill(5)}", "from_zone": source, "to_zone": target}
    if match := re.fullmatch(r"pick (?:between|one of) ([\w ,'-]+)", text, re.I):
        options = re.split(r",\s*(?:(?:or|and)\s+)?|\s+(?:or|and)\s+", match[1], flags=re.I)
        if len(options) >= 2 and all(option.strip() for option in options):
            return "pick_random", {"options": [option.strip() for option in options]}
    return None
