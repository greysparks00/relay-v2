"""Standalone voice commands for locating and launching Windows apps."""

import re


NAME = r'''(?:"([^"\n]{1,120})"|([\w+#()-]+(?: [\w+#()-]+){0,7}))'''
FIND = (
    rf"(?:find|look up) (?:the )?(?:app|application) {NAME}",
    rf"where(?: is|'s) {NAME} installed",
    rf"(?:is {NAME} installed)(?: on (?:my|this) (?:pc|computer))?",
    rf"do i have {NAME} (?:installed(?: on (?:my|this) (?:pc|computer))?|on (?:my|this) (?:pc|computer))",
)
OPEN = rf"(?:open|launch|start) (?:the app |the application |app )?{NAME}"


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


def app_reply(tool, result, args):
    status = result["status"]
    if status == "not_found":
        return f"I couldn't find {args['name']} among the apps on this computer."
    if status == "launch_requested":
        return f"Requested a local launch of {result['name']}."
    if status == "no_desktop":
        return f"I found {result['name']}, but this client has no graphical session to open it in."
    if status == "no_launcher":
        return f"I found {result['name']}, but this client needs the gio desktop launcher."
    if status == "not_launchable":
        return f"I found {result['name']}, but it has no app launch entry Relay can use."
    if status == "ambiguous":
        names = ", ".join(app["name"] for app in result["matches"])
        return f"I found {result['count']} matches, including {names}. Say open followed by the full app name."
    if status == "found":
        lines = []
        for app in result["matches"]:
            location = f" at {app['location']}" if app["location"] else " in the local app catalog"
            lines.append(f"{app['name']}{location}.")
        if result["count"] > len(lines):
            lines.append(f"Showing {len(lines)} of {result['count']} matches.")
        return " ".join(lines)
    raise ValueError(f"Unexpected {tool} result.")
