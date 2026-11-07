from dataclasses import asdict, dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class App:
    name: str
    app_id: str = ""
    location: str = ""


def words(name):
    return " ".join(re.findall(r"[\w+#]+", name.casefold()))


def matches(query, apps):
    query = query.strip()
    key = words(query)
    if not key or len(query) > 256:
        raise ValueError("Provide an app name between 1 and 256 characters.")
    launchers, records = [], []
    for app in apps:
        name = words(app.name)
        if app.app_id and app.app_id.casefold() == query.casefold():
            return [app]
        if f" {key} " not in f" {name} ":
            continue
        # "Open Widget" should never select "Uninstall Widget" or its help file.
        if name != key and re.search(r"\b(uninstall|uninstaller|repair|setup|help|manual|updates?)\b", name):
            continue
        (launchers if app.app_id else records).append(app)
    # A registry-only exact name can be a different product from a partially
    # matching launcher. Only associate it with an app in its install directory.
    exact_records = [app for app in records if app.name.casefold() == query.casefold()]
    if exact_records and not any(app.name.casefold() == query.casefold() for app in launchers):
        linked = [app for app in launchers if app.location and any(
            record.location and Path(app.location).is_relative_to(Path(record.location))
            for record in exact_records)]
        if linked:
            launchers = linked
        elif launchers:
            # A version suffix (Blender 4.4) is common when the uninstall entry
            # omits the version. Otherwise let the caller choose the full name.
            versioned = [app for app in launchers if re.fullmatch(re.escape(key) + r" (?:v?\d+)(?: \d+)*", words(app.name))]
            if not versioned:
                return exact_records
            launchers = versioned
    candidates = launchers or records
    exact = [app for app in candidates if app.name.casefold() == query.casefold()]
    return sorted(exact or candidates, key=lambda app: (len(words(app.name)), app.name.casefold(), app.app_id))


def describe(apps):
    return [asdict(app) for app in apps[:10]]
