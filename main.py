import asyncio
import logging
from mcp import Client
from dotenv import load_dotenv
from mcp_client.mcp_manager import MCPManager
from llm.agent import Agent, AgentError
from datetime import datetime

def get_system_prompt_from_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

async def main():
    # configure logging
    logging.basicConfig(
        filename="relay.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    load_dotenv()

    async with Client("http://127.0.0.1:8000/mcp") as client:
        mcp_manager = MCPManager(client)

        agent = Agent(
            get_system_prompt_from_file("./llm/system_prompt.txt"),
            mcp_manager
        )
        await agent.load_tools()

        print(f"Loaded {len(mcp_manager.tools)} MCP tools.")

        while True:
            try:
                user_message = input("\nYou: ")

            except KeyboardInterrupt:
                break

            try:
                completion = agent.chat(
                    model="openai/gpt-oss-120b",
                    reasoning_effort="low",
                    max_completion_tokens=1024,
                    user_message=user_message
                )

                print("Assistant: ", end="", flush=True)
                async for content in completion:
                    print(content, end="", flush=True)

            except AgentError as error:
                print(f"Error: {error}")

if __name__ == "__main__":
    asyncio.run(main())