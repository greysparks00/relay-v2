"""Look up XDG desktop entries on this Linux client. GIO handles Exec and D-Bus activation."""

import configparser
import os
from pathlib import Path
import shutil
import subprocess

from .catalog import App


def catalog():
    home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    system = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(os.pathsep)
    seen = set()
    apps = []
    for base in [home, *map(Path, system)]:
        if not base.is_absolute():
            continue
        folder = base / "applications"
        for file in sorted(folder.rglob("*.desktop")):
            app_id = "-".join(file.relative_to(folder).parts)
            if app_id in seen:
                continue
            seen.add(app_id)  # A user-level Hidden entry masks a system entry.
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                with file.open(encoding="utf-8") as stream:
                    parser.read_file(stream)
                entry = parser["Desktop Entry"]
                if entry.get("Type") != "Application" or entry.getboolean("Hidden", False) or entry.getboolean("NoDisplay", False):
                    continue
                if entry.get("TryExec") and not shutil.which(entry["TryExec"]):
                    continue
                if entry.get("Exec") or entry.getboolean("DBusActivatable", False):
                    apps.append(App(entry["Name"], app_id, str(file)))
            except (OSError, ValueError, KeyError, configparser.Error):
                continue
    return apps


def launch(app):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return "no_desktop"
    gio = shutil.which("gio")
    if not gio:
        return "no_launcher"
    subprocess.run([gio, "launch", app.location], timeout=10, check=True, capture_output=True)
    return "launch_requested"
