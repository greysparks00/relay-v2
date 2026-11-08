# Run a resolved MCP command once and format its actual result for chat or speech.

from datetime import datetime
import json

from llm.tool_commands import command_text, confirmation_answer, direct_command
from mcp_client.mcp_manager import MCPManagerError


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


def result_value(envelope, tool):
    structured = envelope.get("structured_content", envelope.get("structuredContent"))
    if structured is not None:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    blocks = envelope.get("content", [])
    if any(block.get("type") != "text" for block in blocks):
        return blocks
    texts = [block["text"] for block in blocks]
    if tool in {"list_handoffs", "recall_facts", "check_timers"}:
        return [json.loads(text) for text in texts]
    if tool in {"set_screen_enabled", "change_screen", "find_app", "open_app", "get_system_info", "convert_units", "date_math", "convert_timezone", "resume_handoff", "read_fact", "set_timer", "cancel_timer"}:
        return json.loads(texts[0])
    return "\n".join(texts)


def format_result(tool, value, args, message):
    if tool == "set_screen_enabled":
        if value.get("status") != "applied" or value.get("id") != args["id"]:
            raise ValueError("Unconfirmed kiosk state")
        state = "awake" if args["enabled"] else "asleep"
        return f"Screen {args['id']} is {state}."
    if tool == "change_screen":
        if value.get("status") != "accepted" or value.get("id") != args["id"]:
            raise ValueError("Unexpected screen acknowledgement")
        return f"Sent to screen {value['id']}."
    if tool in {"find_app", "open_app"}:
        return app_reply(tool, value, args)
    if tool == "get_system_info":
        return system_reply(value, args.get("section", "overview"))
    if tool in {"set_timer", "cancel_timer", "check_timers"}:
        return format_timer(tool, value, args, command_text(message))
    if tool == "get_current_datetime":
        return datetime.fromisoformat(value).strftime("%A, %B %d, %Y at %I:%M %p %z")
    if tool == "convert_units":
        return f"{value['value']} {args['to_unit']}."
    if tool == "convert_timezone":
        return f"{value['target_time']} in {value['target_zone']}."
    if tool == "date_math":
        if "end" in args:
            return f"{value['days']} days from {value['start']} to {value['date']}."
        return f"{value['weekday']}, {value['date']}."
    if tool == "read_fact":
        return value["fact"]
    if tool == "resume_handoff":
        return value["summary"]
    if tool == "recall_facts":
        return "\n".join(f"{item['name']}: {item['fact']}" for item in value) or "No matching facts."
    if tool == "list_handoffs":
        return ", ".join(item["topic"] for item in value) or "No saved handoffs."
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


class DirectTools:
    def __init__(self):
        self.pending = None

    async def reply(self, message, manager):
        pending, self.pending = self.pending, None
        answer = confirmation_answer(message) if pending else None
        if answer is False:
            return "Cancelled."
        confirmed = answer is True
        if confirmed:
            command = pending
        else:
            try:
                command = direct_command(message)
            except ValueError as error:
                return str(error)
        if command is None:
            return None
        tool, args = command
        if not any(t["function"]["name"] == tool for t in manager.tools):
            return f"No registered MCP tool named {tool}." if message.lstrip().startswith("/tool") else None

        if not confirmed and tool in {"forget_fact", "delete_handoff"}:
            field = "name" if tool == "forget_fact" else "topic"
            if not isinstance(args.get(field), str) or not args[field].strip():
                return f"Provide the exact {field} to delete."
            self.pending = command
            category = f" in {args['category']}" if args.get("category") else ""
            kind = "fact" if field == "name" else "handoff"
            return f"Delete the {kind} named {args[field]}{category}? Say yes or no."

        raw = await manager.execute_tool(tool, args)
        try:
            envelope = json.loads(raw)
            if envelope.get("is_error") or envelope.get("isError"):
                detail = next((p["text"] for p in envelope.get("content", []) if p.get("type") == "text"), "")
                return detail or f"{tool} reported an error."
            return format_result(tool, result_value(envelope, tool), args, message)
        except (ValueError, TypeError, IndexError, KeyError, AttributeError) as error:
            raise MCPManagerError(f"Unexpected result from {tool}.") from error
