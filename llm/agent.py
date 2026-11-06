import copy
import json
from groq import Groq
from groq._exceptions import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)

class AgentError(Exception):
    pass

# creates a connection to the Groq client, handles message history, and manages chat completions
class Agent():
    def __init__(self, system_prompt):
        self.agent = Groq(
            timeout=30,
            max_retries=3,
        )
        self.messages = []
        self.tools = []
        self.tool_functions = {}

        self.max_tool_calls = 5
        self.max_message_history = 50

        # load system instructions first
        self.add_message("system", system_prompt)

    # registers multiple tools at once
    def register_multiple_tools(self, tools):
        for tool in tools:
            self.register_tool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                function=tool
            )

    # registers a tool with its description, parameters, and function
    def register_tool(self, name, description, parameters, function):
        # tool already exists
        if name in self.tool_functions:
            raise ValueError(f"Tool already registered: {name}")

        self.tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        })

        self.tool_functions[name] = function

    # adds a message to the message history
    def add_message(self, role, content):
        self.messages.append({
            "role": role,
            "content": content
        })

        # keep message count under self.max_message_history
        if len(self.messages) > self.max_message_history:
            self.messages.pop(1) # preserve system prompt

    # handles streamed responses and executes tool calls
    def handle_streamed_response(self, model, reasoning_effort, max_completion_tokens):
        # try to handle streamed response up to 5 times
        for _ in range(self.max_tool_calls):
            completion = self.create_chat_completion_request(
                model, reasoning_effort, max_completion_tokens
            )

            # reconstruct streamed tool call
            response_parts = []
            pending_calls = {}

            for chunk in completion:
                delta = chunk.choices[0].delta

                if delta.content:
                    response_parts.append(delta.content)
                    yield delta.content

                # process streamed tool call chunks
                for call in delta.tool_calls or []:
                    if call.index not in pending_calls:
                        pending_calls[call.index] = {
                            "id": "",
                            "type": "function",
                            "function": {
                                "name": "",
                                "arguments": ""
                            }
                        }

                    # update the pending call with the current chunk
                    pending = pending_calls[call.index]

                    if call.id:
                        pending["id"] = call.id

                    if call.function:
                        if call.function.name:
                            pending["function"]["name"] += call.function.name

                        if call.function.arguments:
                            pending["function"]["arguments"] += call.function.arguments

            # combine streamed response and tool calls
            response = "".join(response_parts)
            tool_calls = [
                pending_calls[i] for i in sorted(pending_calls)
            ]

            # no tool calls anymore, so return the response
            if not tool_calls:
                self.add_message("assistant", response)
                return

            # add to the message history
            self.messages.append({
                "role": "assistant",
                "content": response or None,
                "tool_calls": tool_calls
            })

            # try to call each tool
            for call in tool_calls:
                name = call["function"]["name"]

                try:
                    arguments = json.loads(
                        call["function"]["arguments"] or "{}"
                    )

                    function = self.tool_functions.get(name)

                    if function is None:
                        raise ValueError("Unknown tool")

                    result = function(**arguments)
                    content = json.dumps(result, default=str)

                except Exception:
                    content = json.dumps({
                        "error": "Tool execution failed"
                    })

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": content
                })

        raise RuntimeError("Maximum tool rounds exceeded")

    # responsible for creating a chat completion request to the Groq client
    def create_chat_completion_request(self, model, reasoning_effort, max_completion_tokens):
        request = {
            "model": model,
            "messages": self.messages,
            "temperature": 1,
            "max_completion_tokens": max_completion_tokens,
            "top_p": 1,
            "reasoning_effort": reasoning_effort,
            "stream": True,
            "stop": None
        }

        if self.tools:
            request["tools"] = self.tools
            request["tool_choice"] = "auto" # let the model decide whether to use a tool and which tool to use

        return self.agent.chat.completions.create(**request)
        
    # add a user message and yield the streamed response, restoring history on failure
    def chat(self, model, reasoning_effort, max_completion_tokens, user_message):
        previous_messages = copy.deepcopy(self.messages)
        completed = False

        try:
            self.add_message("user", user_message)

            try:
                yield from self.handle_streamed_response(
                    model, reasoning_effort, max_completion_tokens
                )

            # handle errors
            except RateLimitError as error:
                raise AgentError("Groq rate limit exceeded.") from error

            except APITimeoutError as error:
                raise AgentError("Groq request timed out.") from error

            except APIConnectionError as error:
                raise AgentError("Cannot connect to Groq.") from error

            except APIStatusError as error:
                raise AgentError(
                    f"Groq returned HTTP {error.status_code}."
                ) from error

            except APIError as error:
                raise AgentError("Groq request failed.") from error

            completed = True

        finally:
            # restore history if failed
            if not completed:
                self.messages = previous_messages

    # clear the message history while preserving the system prompt
    def clear(self):
        self.messages = [self.messages[0]]