"""Run a resolved MCP command once and format its actual result for chat or speech."""

from datetime import datetime
import json

from llm.system_info import system_reply
from llm.timer_commands import format_timer
from llm.tool_commands import command_text, direct_command
from mcp_client.mcp_manager import MCPManagerError


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
    if tool in {"get_system_info", "convert_units", "date_math", "convert_timezone", "resume_handoff", "read_fact", "set_timer", "cancel_timer"}:
        return json.loads(texts[0])
    return "\n".join(texts)


def format_result(tool, value, args, message):
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
        answer = message.strip().rstrip(".?!").casefold()
        if pending and answer in {"no", "cancel", "never mind"}:
            return "Cancelled."
        confirmed = pending is not None and answer in {"yes", "confirm", "yes please"}
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
