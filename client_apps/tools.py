# Client-owned tools. Their names are reserved even if an older MCP server advertises them.

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .catalog import App, describe, matches, words


def get_catalog():
    if os.name == "nt":
        from .windows import catalog
    elif sys.platform.startswith("linux"):
        from .linux import catalog
    else:
        raise ValueError("Local app discovery supports Windows and Linux.")
    return catalog()


def lookup(name):
    found = matches(name, get_catalog())
    if not found and sys.platform.startswith("linux") and re.fullmatch(r"[\w.+-]+", name.strip()):
        executable = shutil.which(name.strip())
        if executable:
            # A command on PATH can be found, but is not a desktop launch registration.
            found = [App(name.strip(), location=str(Path(executable).resolve()))]
    return found


def find_app(name):
    found = lookup(name)
    return {"status": "found" if found else "not_found", "count": len(found), "matches": describe(found)}


def launch_registered(app):
    if os.name == "nt":
        os.startfile("shell:AppsFolder\\" + app.app_id)
        return "launch_requested"
    from .linux import launch
    return launch(app)


def open_app(name):
    found = lookup(name)
    if not found:
        return {"status": "not_found"}
    if len(found) != 1:
        return {"status": "ambiguous", "count": len(found), "matches": describe(found)}
    app = found[0]
    if not app.app_id or re.search(r"\b(uninstall|uninstaller|repair|setup)\b", words(app.name)):
        return {"status": "not_launchable", "name": app.name, "location": app.location}
    return {"status": launch_registered(app), "name": app.name}


HANDLERS = {"find_app": find_app, "open_app": open_app}
DESCRIPTIONS = {
    "find_app": "Find an installed application on the computer running Relay chat by name. Returns registered names, IDs and known locations.",
    "open_app": "Open a registered desktop application on the computer running Relay chat. Accepts a display name or an ID from find_app. Returns choices if ambiguous.",
}


def definitions():
    return [
        {"type": "function", "function": {"name": name, "description": description,
         "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                        "required": ["name"], "additionalProperties": False}}}
        for name, description in DESCRIPTIONS.items()
    ]


async def execute(name, arguments):
    if not isinstance(arguments, dict) or set(arguments) != {"name"} or not isinstance(arguments["name"], str):
        return json.dumps({"is_error": True, "content": [{"type": "text", "text": "Provide one application name."}]})
    try:
        result = await asyncio.to_thread(HANDLERS[name], arguments["name"])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return json.dumps({"is_error": True, "content": [{"type": "text", "text": f"Local app request failed: {error}"}]})
    return json.dumps({"is_error": False, "structured_content": result}, ensure_ascii=False)
