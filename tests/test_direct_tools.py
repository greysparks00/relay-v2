import json
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from llm.tool_commands import direct_command
from llm.tool_replies import DirectTools


class DirectToolTests(IsolatedAsyncioTestCase):
    def test_voice_examples_cover_registered_tools(self):
        examples = {
                  "change_screen": 'Send "Hello" to screen 1',
                  "get_system_info": "What are my CPU and GPU temperatures?",
                  "get_current_datetime": "What time is it?",
                  "convert_units": "Convert 180 Celsius to Fahrenheit",
                  "convert_timezone": "Convert 2026-11-07 15:00 Chicago to London",
                  "date_math": "What day is six weeks from Friday?",
                  "pick_random": "Pick between tea and coffee",
                  "set_timer": "Set a tea timer for eight minutes.",
                  "check_timers": "List my timers",
                  "cancel_timer": "Cancel my tea timer",
                  "remember_fact": "Remember that my favorite color is blue",
                  "read_fact": "Read my fact my favorite color",
                  "recall_facts": "Search my memory for color",
                  "edit_fact": "In fact my favorite color, replace \"blue\" with \"green\"",
                  "forget_fact": "Forget the fact my favorite color",
                  "save_handoff": "Save a handoff for Release as Run the tests",
                  "list_handoffs": "List handoffs",
                  "resume_handoff": "Resume handoff for Release",
                  "delete_handoff": "Delete handoff for release"
        }
        # In the combined Relay workspace, also detect new MCP tools that lack
        # a phrase. The agent repository can still run its tests independently.
        catalog = Path(__file__).resolve().parents[2] / "relay-mcp" / "tools"
        if catalog.is_dir():
            registered = {p.parent.name for p in catalog.glob("*/tool.py")
                          if not p.parent.name.startswith(("_", "."))}
            self.assertEqual(set(examples), registered)
        for tool, message in examples.items():
            with self.subTest(tool=tool):
                self.assertEqual(direct_command(message)[0], tool)

    def test_screen_patterns_only_send_supplied_content(self):
        self.assertEqual(direct_command("Switch screen number 1 to Fortnite"), (
            "change_screen", {"id": 1, "screen": {"type": "text", "content": "Fortnite"}}))
        self.assertEqual(direct_command('Send "Coffee and tea?" to screen 2'), (
            "change_screen", {"id": 2, "screen": {"type": "text", "content": "Coffee and tea?"}}))
        self.assertEqual(direct_command('Show comparison "A: fast" versus "B: quiet" on screen 1'), (
            "change_screen", {"id": 1, "screen": {"type": "comparison", "option1": "A: fast", "option2": "B: quiet"}}))
        for message in ("Use screen 1 to explain airplanes", "Use screen 2 to compare English and Spanish",
                        "Send hello to screen 0", "Send hello to screen 1 then cancel my timer"):
            self.assertIsNone(direct_command(message))

    def test_compound_and_conditional_requests_fall_back(self):
        self.assertIsNone(direct_command("Forget the fact office if it is outdated"))
        self.assertIsNone(direct_command("Read my fact office and convert it to a handoff"))
        self.assertIsNone(direct_command("Search the web for tomorrow's forecast"))

    async def test_future_tool_uses_discovered_name_and_supplied_arguments(self):
        manager = SimpleNamespace(tools=[{"function": {"name": "new_tool"}}],
                                  execute_tool=AsyncMock(return_value=json.dumps({"content": [{"type": "text", "text": "done"}]})))
        router = DirectTools()
        self.assertEqual(await router.reply('/tool new_tool {"query":"today"}', manager), "done")
        manager.execute_tool.assert_awaited_once_with("new_tool", {"query": "today"})
        self.assertIn("JSON object", await router.reply("/tool new_tool [2]", manager))
        self.assertIn("No registered", await router.reply("/tool typo", manager))
        self.assertEqual(manager.execute_tool.await_count, 1)

    async def test_delete_is_confirmed_once_and_cleared_on_topic_change(self):
        manager = SimpleNamespace(tools=[{"function": {"name": "forget_fact"}}],
                                  execute_tool=AsyncMock(return_value=json.dumps({"content": [{"type": "text", "text": "Forgot."}]})))
        router = DirectTools()
        message = "Forget the fact coffee"
        self.assertIn("yes or no", await router.reply(message, manager))
        self.assertIsNone(await router.reply("Tell me a joke", manager))
        self.assertIsNone(await router.reply("yes", manager))
        manager.execute_tool.assert_not_awaited()
        await router.reply(message, manager)
        self.assertEqual(await router.reply("yes", manager), "Forgot.")
        self.assertIsNone(await router.reply("yes", manager))
        manager.execute_tool.assert_awaited_once_with("forget_fact", {"name": "coffee"})
