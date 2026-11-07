"""Direct voice requests and spoken responses for the MCP host's hardware."""

import re


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


def gib(size):
    return f"{size / 2**30:.1f}"


def system_reply(info, section):
    lines = []
    if system := info.get("system"):
        lines.append(f"{system['os']} on {system['architecture']}. Uptime is {system['uptime_seconds'] // 3600} hours.")
    if cpu := info.get("cpu"):
        cores = f"{cpu['physical_cores']} cores, " if cpu["physical_cores"] is not None else ""
        lines.append(f"{cpu['model']}, {cores}{cpu['logical_processors']} logical processors. CPU usage is {cpu['usage_percent']:g}%.")
    if memory := info.get("memory"):
        lines.append(f"RAM usage is {memory['usage_percent']:g}%: {gib(memory['used_bytes'])} of {gib(memory['total_bytes'])} GiB in use, {gib(memory['available_bytes'])} GiB available.")
    if disk := info.get("system_disk"):
        lines.append(f"The system drive is {disk['usage_percent']:g}% full, with {gib(disk['free_bytes'])} GiB free.")
    if "cpu_temperature_sensors" in info:
        sensors = info["cpu_temperature_sensors"]
        if sensors:
            peak = max(sensors, key=lambda s: s["celsius"])
            lines.append(f"The highest reported CPU temperature is {peak['celsius']:g} degrees Celsius at {peak['sensor']}.")
        else:
            lines.append("CPU temperature is unavailable from the system's sensors.")
    if "gpus" in info and not info["gpus"]:
        lines.append("GPU information is unavailable.")
    for card in info.get("gpus", []):
        metrics = []
        temp = card.get("temperature_c")
        metrics.append(f"{temp:g} degrees Celsius" if temp is not None else "temperature unavailable")
        if section not in {"temperatures", "gpu_temperature"}:
            if card.get("usage_percent") is not None:
                metrics.append(f"{card['usage_percent']:g}% GPU usage")
            if card.get("vram_used_mib") is not None and card.get("vram_total_mib") is not None:
                metrics.append(f"{card['vram_used_mib']/1024:.1f} of {card['vram_total_mib']/1024:.1f} GiB of video memory in use")
        lines.append(f"{card['name']}: {', '.join(metrics)}.")
    return " ".join(lines)
