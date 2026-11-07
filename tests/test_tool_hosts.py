import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from mcp_client.mcp_manager import MCPManager


class ToolHostTests(IsolatedAsyncioTestCase):
    async def test_local_names_win_over_an_older_remote_server(self):
        names = ["find_app", "open_app", "read_fact"]
        listing = SimpleNamespace(tools=[SimpleNamespace(name=name, description="", input_schema={}) for name in names])
        remote = SimpleNamespace(list_tools=AsyncMock(return_value=listing), call_tool=AsyncMock())
        manager = MCPManager(remote)
        await manager.discover_tools()
        self.assertCountEqual([tool["function"]["name"] for tool in manager.tools], names)
        with patch("client_apps.tools.execute", new_callable=AsyncMock, return_value="local") as local:
            for name in ("find_app", "open_app"):
                self.assertEqual(await manager.execute_tool(name, {"name": "Calculator"}), "local")
            self.assertEqual(local.await_count, 2)
        remote.call_tool.assert_not_awaited()
        remote.call_tool.return_value = SimpleNamespace(is_error=False, model_dump_json=lambda **kwargs: "{}")
        self.assertEqual(json.loads(await manager.execute_tool("read_fact", {"name": "test"})), {})
        remote.call_tool.assert_awaited_once_with("read_fact", {"name": "test"})
