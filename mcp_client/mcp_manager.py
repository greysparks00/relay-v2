import logging

class MCPManagerError(Exception):
    pass

# manages MCP tool discovery and execution
class MCPManager:
    def __init__(self, client):
        self.client = client
        self.tools = []

    # discovers and loads available tools
    async def discover_tools(self):
        try:
            result = await self.client.list_tools()

        except Exception as error:
            logging.exception("Failed to discover MCP tools")
            raise MCPManagerError("Unable to discover MCP tools.") from error
        
        # convert tools to the OpenAI function calling format
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }

            for tool in result.tools
        ]

    # executes a tool and returns the result as JSON
    async def execute_tool(self, name, arguments):
        try:
            result = await self.client.call_tool(name, arguments)

        # invalid input
        except Exception as error:
            logging.exception("MCP request failed: %s", name)
            raise MCPManagerError("MCP tool request failed.") from error

        # tool encounters unexpected problems
        if result.is_error:
            logging.warning("MCP tool returned an error: %s", name)

        return result.model_dump_json(exclude_none=True)