"""
Turn an agent's raw stream (model deltas, tool calls, memory steps) into small UI events.

The agent answers by calling `final_answer_tool(answer=...)`, so the answer text arrives as streamed
tool-call *arguments* (partial JSON). This module decodes the `answer` string out of that partial JSON
as it grows, so front ends can render the reply token by token.

Events (plain dicts, JSON-serializable):
    {"type": "route", "tier": str}      the model tier this question was routed to (only with a router)
    {"type": "tool", "name": str}       a non-final tool is being called
    {"type": "delta", "text": str}      more answer text
    {"type": "retract"}                 the answer streamed in this step was rejected; clear it
    {"type": "final", "answer": str}    authoritative final answer (always sent last)
"""

import re
from collections.abc import AsyncGenerator
from typing import Any

from src.agent.routing import ConversationRouting, apply_route, assess_turn, drop_last_turn, routing_state
from src.memory import ActionStep, FinalAnswerStep
from src.models import ChatMessageStreamDelta, ChatMessageToolCall

FINAL_ANSWER_TOOL = "final_answer_tool"

# C0 control characters (except tab/newline/CR) occasionally appear in model output and render as junk
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

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


async def stream_agent_events(agent: Any, task: str, reset: bool = False, tier: str | None = None) -> AsyncGenerator[dict]:
    """Run `agent` on `task` and yield UI events. `reset=False` keeps the conversation history.

    When the agent has a `router`, the question is routed once, before the run, to a model tier (or to `tier`
    when given): a {"type": "route", "tier"} event comes first, and the final event adds `tier`,
    `can_escalate` (the run struggled and a higher tier exists; only the user may accept) and `struggled`.
    """
    router = getattr(agent, "router", None)
    route = None
    if router is not None:
        if reset:
            agent.routing_state = ConversationRouting()
        state = routing_state(agent)
        if tier:
            route = router.route_for_tier(tier, "requested by the user")
        else:
            route = await router.choose(task, state.route, state.question)
        apply_route(agent, route)
        state.question, state.route = task, route
        yield {"type": "route", "tier": route.tier}

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
                    chunk = _CONTROL_RE.sub("", text[call["sent"]:])
                    call["sent"] = len(text)
                    if chunk:
                        yield {"type": "delta", "text": chunk}
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
            final = {"type": "final", "answer": _CONTROL_RE.sub("", str(event.output))}
            if route is not None:
                assessment = assess_turn(agent, final["answer"], route, router)
                final.update(tier=route.tier, can_escalate=assessment.can_escalate, struggled=assessment.struggled)
            yield final


async def escalate_events(agent: Any) -> AsyncGenerator[dict]:
    """Retry the conversation's last question one tier up. Only ever called on the user's request."""
    router = getattr(agent, "router", None)
    state = routing_state(agent)
    next_tier = router.next_tier(state.route.tier) if router is not None and state.route else None
    if not next_tier or not state.question:
        yield {"type": "final", "answer": "There's no earlier answer that can be retried with deeper reasoning.",
               "can_escalate": False}
        return
    drop_last_turn(agent)  # the retry replaces the struggling attempt instead of following it
    async for event in stream_agent_events(agent, state.question, tier=next_tier):
        yield event
