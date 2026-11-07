import copy
import json
import tiktoken
from mcp_client.mcp_manager import MCPManagerError
from groq import AsyncGroq
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
    def __init__(self, system_prompt, mcp_manager):
        self.agent = AsyncGroq(
            timeout=30,
            max_retries=3,
        )
        self.mcp = mcp_manager
        self.messages = []

        self.max_tool_calls = 5
        self.max_message_history = 50

        self.tokenizer = tiktoken.get_encoding("o200k_harmony")
        self.max_context_tokens = 24000
        self.context_safety_tokens = 2048

        # load system instructions first
        self.add_message("system", system_prompt)

    # discovers and loads available tools
    async def load_tools(self):
        await self.mcp.discover_tools()

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
    async def handle_streamed_response(self, model, reasoning_effort, max_completion_tokens):
        # try to handle streamed response up to 5 times
        for _ in range(self.max_tool_calls):
            completion = await self.create_chat_completion_request(
                model, reasoning_effort, max_completion_tokens
            )

            # reconstruct streamed tool call
            response_parts = []
            pending_calls = {}
            finish_reason = None

            async for chunk in completion:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason

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

            # handle finish reason errors
            if finish_reason == "length":
                raise AgentError("Model reached its completion token limit.")

            if finish_reason not in ("stop", "tool_calls"):
                raise AgentError("Model response ended unexpectedly.")
            
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

                    # validate the tool arguments
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be an object")

                    content = await self.mcp.execute_tool(name, arguments)

                except (ValueError, TypeError):
                    content = json.dumps({
                        "error": "Tool execution failed"
                    })

                except MCPManagerError as error:
                    raise AgentError("MCP tool service unavailable.") from error

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": content
                })

        raise AgentError("Maximum tool rounds exceeded")

    # responsible for creating a chat completion request to the Groq client
    async def create_chat_completion_request(self, model, reasoning_effort, max_completion_tokens):
        self.trim_context(max_completion_tokens)

        # create the chat completion request
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

        if self.mcp.tools:
            request["tools"] = self.mcp.tools
            request["tool_choice"] = "auto" # let the model decide whether to use a tool and which tool to use

        return await self.agent.chat.completions.create(**request)
        
    # add a user message and yield the streamed response, restoring history on failure
    async def chat(self, model, reasoning_effort, max_completion_tokens, user_message):
        previous_messages = copy.deepcopy(self.messages)
        completed = False

        try:
            self.add_message("user", user_message)

            try:
                async for chunk in self.handle_streamed_response(
                    model, reasoning_effort, max_completion_tokens
                ):
                    yield chunk

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

            self.trim_history()

            completed = True

        finally:
            # restore history if failed
            if not completed:
                self.messages = previous_messages

    # estimate the token count for the current context
    def estimate_context_tokens(self):
        payload = {
            "messages": self.messages,
            "tools": self.mcp.tools
        }

        text = json.dumps(payload, ensure_ascii=False)

        # add a small buffer for message metadata
        return (
            len(self.tokenizer.encode_ordinary(text))
            + len(self.messages) * 10
        )

    # trim the context to fit within the token budget
    def trim_context(self, max_completion_tokens):
        budget = (
            self.max_context_tokens
            - max_completion_tokens
            - self.context_safety_tokens
        )

        if budget <= 0:
            raise AgentError("Invalid context token budget.")

        while self.estimate_context_tokens() > budget:
            next_user_message = next(
                (
                    i for i in range(2, len(self.messages))
                    if self.messages[i]["role"] == "user"
                ),
                None
            )

            if next_user_message is None:
                raise AgentError("Current conversation turn exceeds the token budget.")

            del self.messages[1:next_user_message]

    # trim the message history to the maximum allowed length
    def trim_history(self):
        while len(self.messages) > self.max_message_history:
            # find the index of the next user message after the first one
            next_user_message = next(
                (
                    i for i in range(2, len(self.messages))
                    if self.messages[i]["role"] == "user"
                ),
                None
            )

            # stop if no later user message is found
            if next_user_message is None:
                break

            # remove the oldest user message and its response
            del self.messages[1:next_user_message]

    # clear the message history while preserving the system prompt
    def clear(self):
        self.messages = [self.messages[0]]