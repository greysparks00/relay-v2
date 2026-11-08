# The chat entry point calls direct_command before sending anything to Groq.
# A match returns the discovered tool name and its complete argument object.
# Returning None hands the original message and history back to the agent.
# Keep phrase matching here. Tool execution, confirmation, and spoken replies
# belong in tool_replies.py so matching alone never performs an action.
# When adding a tool, add a full-phrase match and a representative utterance to
# test_direct_tools.py. If a required argument needs research, composition, or
# conversation history, defer that phrasing to Groq instead of guessing it.

import json
import re


# Timer names and durations must be explicit. Pronouns like "the last one" need history.
# Unquoted names are single words. Quotes let callers specify an exact multiword name.
TIMER_NAME = r'''(?:"(?P<quoted>[\w -]{1,100})"|(?P<word>[\w-]{1,100}))'''
AMOUNT = r"(?P<amount>[0-9]{1,8}|[a-z]+) (?P<unit>seconds?|minutes?|hours?)"
NUMBERS = {word: n for n, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split()
)}
NUMBERS.update(fifteen=15, twenty=20, thirty=30, forty=40, fifty=50, sixty=60)
UNITS = {"second": 1, "minute": 60, "hour": 3600}

SET = [
    re.compile(rf"set (?:a )?timer (?:called|named) {TIMER_NAME} for {AMOUNT}", re.I),
    re.compile(rf"set (?:a )?{TIMER_NAME} timer for {AMOUNT}", re.I),
]
CHECK = [
    re.compile(rf"how much time is left on (?:my |the )?timer (?:called|named) {TIMER_NAME}", re.I),
    re.compile(rf"how much time is left on (?:my |the )?{TIMER_NAME} timer", re.I),
]
CANCEL = [
    re.compile(rf"cancel (?:my |the )?timer (?:called|named) {TIMER_NAME}", re.I),
    re.compile(rf"cancel (?:my |the )?{TIMER_NAME} timer", re.I),
]
CONTEXT_WORDS = set("a an the my that this other next previous last first second current running active expired all every each only same another new remaining".split())


def timer_command(message: str):
    text = message.strip().rstrip(".?!").strip()
    if text.casefold() in {"list my timers", "list timers", "what timers are running"}:
        return "check_timers", {}
    for tool, patterns in (("set_timer", SET), ("check_timers", CHECK), ("cancel_timer", CANCEL)):
        for pattern in patterns:
            match = pattern.fullmatch(text)
            if not match:
                continue
            name = (match["quoted"] or match["word"]).strip()
            if not name or (match["word"] and name.casefold() in CONTEXT_WORDS):
                return None
            args = {"name": name}
            if tool == "set_timer":
                amount = match["amount"].lower()
                count = int(amount) if amount.isdigit() else NUMBERS.get(amount, 0)
                seconds = count * UNITS[match["unit"].lower().rstrip("s")]
                if not 1 <= seconds <= 365 * 86400:
                    return None
                args["duration_seconds"] = seconds
            return tool, args
    return None


# App requests run on the chat client. Capture quoted names intact, including spaces.
APP_NAME = r'''(?:"([^"\n]{1,120})"|([\w+#()-]+(?: [\w+#()-]+){0,7}))'''
FIND = (
    rf"(?:find|look up) (?:the )?(?:app|application) {APP_NAME}",
    rf"where(?: is|'s) {APP_NAME} installed",
    rf"(?:is {APP_NAME} installed)(?: on (?:my|this) (?:pc|computer))?",
    rf"do i have {APP_NAME} (?:installed(?: on (?:my|this) (?:pc|computer))?|on (?:my|this) (?:pc|computer))",
)
OPEN = rf"(?:open|launch|start) (?:the app |the application |app )?{APP_NAME}"


def app_command(text):
    for pattern in FIND:
        if match := re.fullmatch(pattern, text, re.I):
            return "find_app", {"name": match[1] or match[2]}
    if match := re.fullmatch(OPEN, text, re.I):
        name = match[1] or match[2]
        if not match[1] and name.casefold() != "file explorer" and re.search(r"\b(and|or|then|if|unless|with|using|timer|handoff|fact|file|folder|website|again|it|that|this)\b", name, re.I):
            return None
        return "open_app", {"name": name}
    return None


# Hardware patterns choose a section on the MCP host. Match the whole phrase to avoid intercepting questions about a reading.
REQUESTS = {
    "overview": (r"(?:system|computer|pc) (?:info|information|specs|details|status)", r"how is my (?:pc|computer) doing"),
    "cpu": (r"(?:cpu|processor) (?:usage|load|specs|details|model)", r"what (?:cpu|processor) do i have", r"how busy is my cpu"),
    "gpu": (r"(?:gpu|graphics card) (?:usage|load|specs|details|model)", r"what (?:gpu|graphics card) do i have", r"vram usage"),
    "memory": (r"(?:ram|memory) (?:usage|available|details)", r"how much (?:ram|memory) (?:am i using|is (?:in use|free|available)|do i have)"),
    "disk": (r"(?:disk|storage) (?:space|usage)", r"how much (?:disk|storage) space (?:is (?:left|free)|do i have)"),
    "temperatures": (r"(?:cpu and gpu|gpu and cpu|system|hardware) temp(?:erature)?s?", r"how hot (?:are my cpu and gpu|is my computer)"),
    "cpu_temperature": (r"cpu temp(?:erature)?s?", r"how hot is my (?:cpu|processor)", r"temperature of my (?:cpu|processor)"),
    "gpu_temperature": (r"gpu temp(?:erature)?s?", r"how hot is my (?:gpu|graphics card)", r"temperature of my (?:gpu|graphics card)"),
}


def system_command(text):
    text = text.casefold().replace("’", "'")
    # Normalize wrappers around short phrases such as "what's my RAM usage?".
    phrase = re.sub(r"^(?:what(?:'s| is| are)|show(?: me)?|check|get|tell me)\s+(?:(?:the|my)\s+)?", "", text)
    for section, patterns in REQUESTS.items():
        if any(re.fullmatch(pattern, candidate) for pattern in patterns for candidate in (text, phrase)):
            return "get_system_info", {"section": section}
    return None


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


# Quoted text allows punctuation and words such as "and" to be sent literally.
# Bare text is intentionally short; longer requests are often instructions to compose.
SCREEN_TEXT = r'(?:"([^"\n]*)"|([\w-]+(?: [\w-]+){0,12}))'


def screen_command(text):
    screen_id_pattern = r"(\d{1,10})"
    match = re.fullmatch(rf'(?:send|display|show) {SCREEN_TEXT} (?:on|to) screen {screen_id_pattern}', text, re.I)
    if match:
        # A bare topic after "show" might be a request for generated material.
        if match[1] is None and not text.lower().startswith("send "):
            return None
        screen_id = int(match[3])
        layout = {"type": "text", "content": match[1] if match[1] is not None else match[2]}
    elif match := re.fullmatch(rf'(?:set|switch|change) screen (?:number )?{screen_id_pattern} to (?:"([^"\n]*)"|([\w-]+))', text, re.I):
        # A one-word label or an exact quotation is sufficient display copy.
        # Leave a longer unquoted instruction to the model to interpret.
        if match[3] and match[3].casefold() in {"it", "that", "this", "previous", "last"}:
            return None
        screen_id = int(match[1])
        layout = {"type": "text", "content": match[2] if match[2] is not None else match[3]}
    elif match := re.fullmatch(rf'show comparison "([^"\n]+)" (?:vs\.?|versus) "([^"\n]+)" on screen {screen_id_pattern}', text, re.I):
        screen_id = int(match[3])
        layout = {"type": "comparison", "option1": match[1], "option2": match[2]}
    else:
        return None
    if 1 <= screen_id <= 2147483647:
        return "change_screen", {"id": screen_id, "screen": layout}
    return None


# Interpret yes/no only when DirectTools already holds a pending deletion.
# The caller clears that state when the user changes topic.
def confirmation_answer(message):
    answer = message.strip().rstrip(".?!").casefold()
    if answer in {"no", "cancel", "never mind"}:
        return False
    if answer in {"yes", "confirm", "yes please"}:
        return True
    return None


def command_text(message: str) -> str:
    text = re.sub(r"^(?:hey relay,?\s+)?(?:please\s+)?", "", message.strip(), flags=re.I)
    return text.rstrip(".?!").strip()


def direct_command(message: str):
    # /tool is the explicit escape hatch for every discovered tool, including future ones.
    # JSON must be an object because its keys are passed as keyword arguments.
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
    # These parsers use full matches and handle their own allowed conjunctions
    # (for example "CPU and GPU temperatures") before the generic compound guard.
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
    # A screen command can bypass the model only when the words to display
    # are already supplied. Quoting both options makes a comparison unambiguous.
    # "Use screen 2 to compare English and Spanish" needs generated copy, so
    # it deliberately falls through. The screen ID is always explicit here.
    if screen := screen_command(text):
        return screen
    if app := app_command(text):
        return app
    if plain in {"what time is it", "what's the time", "what is the current time", "what's today's date",
                 "what is today's date", "what day is it"}:
        return "get_current_datetime", {}
    if plain in {"list handoffs", "list my handoffs", "list conversation handoffs"}:
        return "list_handoffs", {}
    if plain in {"list my facts", "list recent memories"}:
        return "recall_facts", {"query": ""}
    # Named capture groups use the vault handlers' argument names. Preserve case
    # and quoted replacement text; only the command syntax is case-insensitive.
    for tool, pattern in NOTE_COMMANDS:
        if match := re.fullmatch(pattern, text, re.I):
            args = {key: value.removeprefix('"').removesuffix('"') for key, value in match.groupdict().items()}
            if plain.startswith("remember that "):
                args["fact"] = f"{args['name']} is {args['fact']}"
            return tool, args

    # Match concrete quantities and dates only. The MCP tool owns conversion,
    # time-zone and calendar rules; this layer just extracts its arguments.
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
