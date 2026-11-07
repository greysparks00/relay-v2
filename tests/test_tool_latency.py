import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from llm.timer_commands import timer_command, timer_reply
from mcp_client.mcp_manager import model_parameters


class ToolLatencyTests(IsolatedAsyncioTestCase):
    def test_only_complete_explicit_commands_match(self):
        self.assertEqual(timer_command("Set a pasta timer for eight minutes."),
                         ("set_timer", {"name": "pasta", "duration_seconds": 480}))
        self.assertEqual(timer_command('Cancel the timer called "pizza dough".'),
                         ("cancel_timer", {"name": "pizza dough"}))
        for message in ("Cancel my last timer", "Don't cancel the pasta timer",
                        "Cancel my pasta timer if it has finished", "Set a pasta timer for 8 minutes and pick dinner",
                        "Tell me how to set a tea timer for 5 minutes"):
            self.assertIsNone(timer_command(message))

    async def test_service_error_is_not_retried(self):
        response = {"is_error": True, "content": [{"type": "text", "text": "Timer already exists."}]}
        manager = SimpleNamespace(tools=[{"function": {"name": "set_timer"}}],
                                  execute_tool=AsyncMock(return_value=json.dumps(response)))
        self.assertIn("already exists", await timer_reply("Set a tea timer for 1 minute", manager))
        manager.execute_tool.assert_awaited_once()

    async def test_missing_tool_falls_back(self):
        manager = SimpleNamespace(tools=[], execute_tool=AsyncMock())
        self.assertIsNone(await timer_reply("List timers", manager))
        manager.execute_tool.assert_not_awaited()

    def test_schema_keeps_meaningful_titles_and_real_fields(self):
        schema = {"title": "exampleArguments", "required": ["title"],
                  "properties": {"title": {"title": "Title", "type": "string"},
                                 "date": {"title": "Departure date", "type": "string"}}}
        cleaned = model_parameters(SimpleNamespace(name="example", input_schema=schema))
        self.assertEqual(cleaned["properties"]["title"], {"type": "string"})
        self.assertEqual(cleaned["properties"]["date"]["title"], "Departure date")
        self.assertEqual(cleaned["required"], ["title"])
        self.assertEqual(schema["properties"]["title"]["title"], "Title")
