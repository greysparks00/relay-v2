import asyncio
import logging
import os
from pathlib import Path
from mcp import Client
from dotenv import load_dotenv
from mcp_client.mcp_manager import MCPManager
from llm.agent import Agent, AgentError

async def main():
    logging.basicConfig(
        filename="relay.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    load_dotenv()

    endpoint = os.environ.get("RELAY_MCP_URL") or "http://127.0.0.1:8000/mcp"
    async with Client(endpoint) as client:
        mcp_manager = MCPManager(client)

        agent = Agent(
            Path("./llm/system_prompt.txt").read_text(),
            mcp_manager
        )
        await mcp_manager.discover_tools()

        logging.info(f"Loaded {len(mcp_manager.tools)} available tools.")
    
        try:
            while True:
                try:
                    user_message = await asyncio.to_thread(input, "\nYou: ")
                    command = user_message.strip().lower()

                    if command in ("/exit", "/quit"):
                        break

                    if command == "/clear":
                        agent.clear()
                        logging.info("Conversation cleared.")
                        continue

                    if not user_message.strip():
                        continue

                except KeyboardInterrupt:
                    break

                try:
                    completion = agent.chat(
                        model="openai/gpt-oss-120b",
                        reasoning_effort="low",
                        max_completion_tokens=4096,
                        user_message=user_message
                    )

                    print("Assistant: ", end="", flush=True)

                    async for content in completion:
                        print(content, end="", flush=True)

                except AgentError as error:
                    print(f"\nError: {error}")
                    logging.error(f"Error: {error}")
                    
        finally:
            await agent.agent.close()
            logging.info("Agent session closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRelay interrupted.")