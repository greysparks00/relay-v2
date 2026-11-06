from dotenv import load_dotenv

from llm.agent import Agent, AgentError
from llm.tools.get_time_tool import GetTimeTool
from datetime import datetime

def get_system_prompt_from_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

def get_current_time():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def main():
    load_dotenv()

    agent = Agent(get_system_prompt_from_file("./llm/system_prompt.txt"))

    tools = [GetTimeTool()]

    agent.register_multiple_tools(tools)

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
            for content in completion:
                print(content, end="", flush=True)

        except AgentError as error:
            print(f"Error: {error}")
            break

if __name__ == "__main__":
    main()