import logging

from client_apps import tools as local_apps

# removes redundant display labels from tool schemas
def model_parameters(tool):
    schema = tool.input_schema.copy()

    if schema.get("title") == f"{tool.name}Arguments":
        del schema["title"]

    if isinstance(schema.get("properties"), dict):
        properties = schema["properties"].copy()

        for name, detail in properties.items():
            if isinstance(detail, dict) and detail.get("title") == name.replace("_", " ").title():
                properties[name] = {key: value for key, value in detail.items() if key != "title"}
        
        schema["properties"] = properties

    return schema

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
                    "parameters": model_parameters(tool)
                }
            }

            for tool in result.tools if tool.name not in local_apps.HANDLERS
        ] + local_apps.definitions()

    # executes a tool and returns the result as JSON
    async def execute_tool(self, name, arguments):
        if name in local_apps.HANDLERS:
            return await local_apps.execute(name, arguments)
        try:
            result = await self.client.call_tool(name, arguments)

        except Exception as error:
            logging.exception("MCP request failed: %s", name)
            raise MCPManagerError("MCP tool request failed.") from error

        # tool encounters unexpected problems
        if result.is_error:
            logging.warning("MCP tool returned an error: %s", name)

        return result.model_dump_json(exclude_none=True)