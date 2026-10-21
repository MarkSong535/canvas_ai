"""
Turn an agent's raw stream (model deltas, tool calls, memory steps) into small UI events.

The agent answers by calling `final_answer_tool(answer=...)`, so the answer text arrives as streamed
tool-call *arguments* (partial JSON). This module decodes the `answer` string out of that partial JSON
as it grows, so front ends can render the reply token by token.

Events (plain dicts, JSON-serializable):
    {"type": "tool", "name": str}       a non-final tool is being called
    {"type": "delta", "text": str}      more answer text
    {"type": "retract"}                 the answer streamed in this step was rejected; clear it
    {"type": "final", "answer": str}    authoritative final answer (always sent last)
"""

import re
from collections.abc import AsyncGenerator
from typing import Any

from src.memory import ActionStep, FinalAnswerStep
from src.models import ChatMessageStreamDelta, ChatMessageToolCall

FINAL_ANSWER_TOOL = "final_answer_tool"

_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


def partial_json_string_value(raw: str, key: str) -> str | None:
    """Decode the (possibly unterminated) string value of `key` from a partial JSON object.

    Returns None until the key and its opening quote have arrived. Stops before an incomplete escape sequence.
    """
    match = re.search(r'"%s"\s*:\s*"' % re.escape(key), raw)
    if not match:
        return None
    out = []
    i = match.end()
    while i < len(raw):
        char = raw[i]
        if char == '"':
            break
        if char != "\\":
            out.append(char)
            i += 1
            continue
        if i + 1 >= len(raw):
            break
        escape = raw[i + 1]
        if escape != "u":
            out.append(_ESCAPES.get(escape, escape))
            i += 2
            continue
        if i + 6 > len(raw):
            break
        code = int(raw[i + 2:i + 6], 16)
        if 0xD800 <= code < 0xDC00:
            # High surrogate: wait for the low half before emitting
            if i + 12 > len(raw):
                break
            if raw[i + 6:i + 8] == "\\u":
                low = int(raw[i + 8:i + 12], 16)
                out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                i += 12
                continue
        out.append(chr(code))
        i += 6
    return "".join(out)


async def stream_agent_events(agent: Any, task: str, reset: bool = False) -> AsyncGenerator[dict]:
    """Run `agent` on `task` and yield UI events. `reset=False` keeps the conversation history."""
    # Tool calls being streamed in the current step, keyed by their stream index
    calls: dict[int, dict] = {}
    streamed_answer = False

    async for event in await agent.run(task, stream=True, reset=reset):
        if isinstance(event, ChatMessageStreamDelta):
            for delta in event.tool_calls or []:
                call = calls.setdefault(delta.index, {"name": "", "args": "", "sent": 0})
                if delta.function:
                    if delta.function.name:
                        call["name"] = delta.function.name
                    if delta.function.arguments:
                        call["args"] += delta.function.arguments
                if call["name"] != FINAL_ANSWER_TOOL:
                    continue
                text = partial_json_string_value(call["args"], "answer")
                if text is not None and len(text) > call["sent"]:
                    yield {"type": "delta", "text": text[call["sent"]:]}
                    call["sent"] = len(text)
                    streamed_answer = True
        elif isinstance(event, ChatMessageToolCall):
            if event.function.name != FINAL_ANSWER_TOOL:
                yield {"type": "tool", "name": event.function.name}
        elif isinstance(event, ActionStep):
            if streamed_answer and not event.is_final_answer:
                yield {"type": "retract"}
            calls = {}
            streamed_answer = False
        elif isinstance(event, FinalAnswerStep):
            yield {"type": "final", "answer": str(event.output)}
