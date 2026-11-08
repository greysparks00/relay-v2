# Resolve Windows display names using the current user's AppsFolder and install records.

import json
import os
from pathlib import Path
import subprocess
from threading import Lock
from time import monotonic

from .catalog import App


# AppsFolder preserves the registered launch identity, including shortcut arguments.
# The command is constant: user input never enters PowerShell or a shell command.
CATALOG_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$items = (New-Object -ComObject Shell.Application).Namespace('shell:AppsFolder').Items()
$apps = foreach ($item in $items) {
    [pscustomobject]@{name=$item.Name; app_id=$item.Path; location=[string]$item.ExtendedProperty('System.Link.TargetParsingPath')}
}
ConvertTo-Json -InputObject @($apps) -Compress
"""


def installed_records():
    import winreg

    path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            key = winreg.EnumKey(root, index)
                            with winreg.OpenKey(root, key) as entry:
                                name = winreg.QueryValueEx(entry, "DisplayName")[0]
                                try:
                                    location = winreg.QueryValueEx(entry, "InstallLocation")[0]
                                except FileNotFoundError:
                                    location = ""
                                if isinstance(name, str) and name.strip():
                                    yield App(name=name.strip(), location=location or "")
                        except OSError:
                            continue
            except OSError:
                continue


_lock = Lock()
_catalog = ()
_expires = 0.0


def catalog():
    global _catalog, _expires
    if os.name != "nt":
        raise ValueError("App discovery currently supports Windows.")
    with _lock:
        if monotonic() < _expires:
            return _catalog
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", CATALOG_SCRIPT],
                                capture_output=True, encoding="utf-8", check=True, timeout=12,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        apps = [App(**item) for item in json.loads(result.stdout) if item["name"] and item["app_id"]]
        _catalog = tuple(dict.fromkeys([*apps, *installed_records()]))
        _expires = monotonic() + 45
        return _catalog
