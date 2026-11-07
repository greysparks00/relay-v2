"""Handle literal English timer commands locally. Other phrasing goes to the agent."""

import re


# Unquoted names are single words. Quotes let callers specify an exact multiword name.
NAME = r'''(?:"(?P<quoted>[\w -]{1,100})"|(?P<word>[\w-]{1,100}))'''
AMOUNT = r"(?P<amount>[0-9]{1,8}|[a-z]+) (?P<unit>seconds?|minutes?|hours?)"
NUMBERS = {word: n for n, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split()
)}
NUMBERS.update(fifteen=15, twenty=20, thirty=30, forty=40, fifty=50, sixty=60)
UNITS = {"second": 1, "minute": 60, "hour": 3600}

SET = [
    re.compile(rf"set (?:a )?timer (?:called|named) {NAME} for {AMOUNT}", re.I),
    re.compile(rf"set (?:a )?{NAME} timer for {AMOUNT}", re.I),
]
CHECK = [
    re.compile(rf"how much time is left on (?:my |the )?timer (?:called|named) {NAME}", re.I),
    re.compile(rf"how much time is left on (?:my |the )?{NAME} timer", re.I),
]
CANCEL = [
    re.compile(rf"cancel (?:my |the )?timer (?:called|named) {NAME}", re.I),
    re.compile(rf"cancel (?:my |the )?{NAME} timer", re.I),
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


def duration(seconds: int) -> str:
    parts = []
    for unit, size in (("hour", 3600), ("minute", 60), ("second", 1)):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {unit}{'s' if count != 1 else ''}")
    return " ".join(parts) or "0 seconds"


def timer_status(item: dict) -> str:
    name, state = item["name"], item["state"]
    if state == "expired":
        return f"The {name} timer has finished."
    if state == "running":
        return f"The {name} timer has {duration(item['remaining_seconds'])} left."
    raise ValueError("Unexpected timer state")


def format_timer(tool, value, args, message):
    if tool == "check_timers":
        if message.strip().rstrip(".?!").strip().casefold() == "what timers are running":
            value = [item for item in value if item["state"] == "running"]
        if not value:
            return f"No timer named {args['name']}." if args else "No timers to report."
        return " ".join(timer_status(item) for item in value)
    name, state = value["name"], value["state"]
    if tool == "set_timer" and state == "running":
        return f"{name} timer set for {duration(value['remaining_seconds'])}."
    if tool == "cancel_timer":
        if state == "cancelled":
            return f"Cancelled the {name} timer."
        if state == "not_found":
            return f"No timer named {name}."
        if state == "expired":
            return timer_status(value)
    raise ValueError("Unexpected timer state.")
