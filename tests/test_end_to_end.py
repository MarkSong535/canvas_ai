"""
End-to-end tests for the agent, streaming, memory, the WebSocket handler and LaTeX rendering.

The OpenAI client is replaced by a scripted fake that streams chunks like the real API, so no API key, Canvas
account or network is needed. Run with `pytest tests` or `python tests/test_end_to_end.py`.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Placeholders so the config's Canvas tools can be built; the fake model never lets them reach the network
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("CANVAS_ACCESS_TOKEN", "test-token")
os.environ.setdefault("CANVAS_URL", "https://canvas.example.com")

import src.agent  # noqa: E402,F401 - registers general_agent
from src.agent.stream_events import partial_json_string_value, stream_agent_events  # noqa: E402
from src.memory import TaskStep  # noqa: E402
from src.models import model_manager  # noqa: E402
from src.models.base import supports_stop_parameter  # noqa: E402
from src.models.models import MAX_PRICE_PER_1M_TOKENS, OPENAI_MODELS  # noqa: E402
from src.models.openaillm import OpenAIServerModel  # noqa: E402
from src.registry import AGENT  # noqa: E402
from src.tools import AsyncTool, ToolResult  # noqa: E402
from src.utils import latex_svg  # noqa: E402

USAGE = NS(prompt_tokens=10, completion_tokens=5)


class EchoCourses(AsyncTool):
    """Stand-in for canvas_list_courses that counts how often it really runs."""

    name = "canvas_list_courses"
    description = "List courses"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    output_type = "any"

    def __init__(self):
        super().__init__()
        self.calls = 0

    async def forward(self) -> ToolResult:
        self.calls += 1
        return ToolResult(output="Course A (ID 1), Course B (ID 2)", error=None)


def chunk(tool=None, usage=None):
    """One streamed chat-completions chunk: a tool-call delta (index, id, name, arguments) or the usage chunk."""
    tool_calls = None
    if tool:
        index, call_id, name, arguments = tool
        tool_calls = [NS(index=index, id=call_id, type="function" if call_id else None,
                         function=NS(name=name, arguments=arguments))]
    choices = [] if usage else [NS(delta=NS(content=None, tool_calls=tool_calls), finish_reason=None)]
    return NS(choices=choices, usage=usage)


def answer_turn(call_id, answer_json):
    return [chunk(tool=(0, call_id, "final_answer_tool", answer_json)), chunk(usage=USAGE)]


def tool_turn(call_id, name="canvas_list_courses"):
    return [chunk(tool=(0, call_id, name, "{}")), chunk(usage=USAGE)]


class FakeStream:
    def __init__(self, chunks):
        self._it = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeCompletions:
    """Plays back one scripted model turn per request and records every request."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs.get("stream") is True, "the agent should stream"
        assert "stop" not in kwargs, "reasoning models must not receive `stop`"
        return FakeStream(self.script.pop(0))


def make_agent(script, tool=None):
    from configs.canvas_agent_config import agent_config

    completions = FakeCompletions(script)
    model = OpenAIServerModel(model_id="gpt-6-luna", api_key="sk-test",
                              http_client=NS(chat=NS(completions=completions)), reasoning_effort="none")
    agent = AGENT.build(dict(
        type="general_agent", config=agent_config, model=model, tools=[tool or EchoCourses()],
        max_steps=5, stream_outputs=True, max_history_turns=agent_config["max_history_turns"],
        name="canvas_student_agent", description="test",
    ))
    return agent, completions


async def collect(agent, query, reset=False):
    return [event async for event in stream_agent_events(agent, query, reset=reset)]


# --- models -----------------------------------------------------------------------------------------------

def test_model_table_respects_price_cap():
    assert all(max(m["input_price"], m["output_price"]) <= MAX_PRICE_PER_1M_TOKENS for m in OPENAI_MODELS)
    model_manager.init_models()
    registered = set(model_manager.list_models())
    assert "gpt-6-luna" in registered
    assert "gpt-4o" not in registered and "gpt-5" not in registered


def test_stop_parameter_dropped_for_reasoning_models():
    for model_id in ["gpt-6-luna", "gpt-5.4-mini", "gpt-5-mini", "o4-mini"]:
        assert not supports_stop_parameter(model_id), model_id
    assert supports_stop_parameter("gpt-4.1-mini")


# --- streaming --------------------------------------------------------------------------------------------

def test_partial_json_decoder():
    assert partial_json_string_value('{"ans', "answer") is None
    assert partial_json_string_value('{"answer": "a\\', "answer") == "a"
    assert partial_json_string_value('{"answer": "a\\nb\\u00', "answer") == "a\nb"
    assert partial_json_string_value('{"answer": "\\ud83d\\ude00!"}', "answer") == "\U0001F600!"


def test_streaming_multi_turn_and_native_tool_history():
    answer_args = json.dumps({"answer": "You have 2 courses:\n- Course A\n- \"Course B\" é\U0001F600"})
    # Split the JSON at awkward points (mid-escape, mid-\u sequence) to exercise the partial decoder
    pieces = [answer_args[i:i + 3] for i in range(0, len(answer_args), 3)]
    agent, completions = make_agent([
        [chunk(tool=(0, "call_1", "canvas_list_courses", "")), chunk(tool=(0, None, None, "{}")), chunk(usage=USAGE)],
        [chunk(tool=(0, "call_2", "final_answer_tool", ""))] + [chunk(tool=(0, None, None, p)) for p in pieces]
        + [chunk(usage=USAGE)],
        answer_turn("call_3", json.dumps({"answer": "Course B is ID 2."})),
    ])

    events = asyncio.run(collect(agent, "List my courses"))
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert {"type": "tool", "name": "canvas_list_courses"} in events
    assert events[-1]["type"] == "final"
    assert deltas == json.loads(answer_args)["answer"] == events[-1]["answer"]
    assert sum(e["type"] == "delta" for e in events) > 10, "the answer should arrive in many deltas"

    events = asyncio.run(collect(agent, "What's the ID of the second one?"))
    assert events[-1] == {"type": "final", "answer": "Course B is ID 2."}

    # The second request carries the first turn: question, tool result and answer
    messages = completions.calls[-1]["messages"]
    sent = json.dumps(messages)
    assert "List my courses" in sent and "Course A (ID 1)" in sent and "You have 2 courses" in sent
    # Native tool calling: each assistant tool_calls message is followed by one `tool` message per call id
    for i, message in enumerate(messages):
        if message.get("tool_calls"):
            ids = [tc["id"] for tc in message["tool_calls"]]
            assert all(isinstance(tc["function"]["arguments"], str) for tc in message["tool_calls"])
            following = messages[i + 1:i + 1 + len(ids)]
            assert [m["role"] for m in following] == ["tool"] * len(ids)
            assert [m["tool_call_id"] for m in following] == ids
    assert any("Course A (ID 1)" in json.dumps(m["content"]) for m in messages if m["role"] == "tool")
    assert not any("Called Tool:" in json.dumps(m.get("content")) for m in messages), "no narrated tool calls"

    agent.memory.keep_last_tasks(1)
    assert sum(isinstance(s, TaskStep) for s in agent.memory.steps) == 1


def test_repeated_tool_call_served_from_memory():
    tool = EchoCourses()
    agent, completions = make_agent([tool_turn("r1"), tool_turn("r2"), answer_turn("r3", '{"answer": "done"}')], tool)
    events = asyncio.run(collect(agent, "courses?", reset=True))
    assert events[-1]["answer"] == "done"
    assert tool.calls == 1, "an identical repeat must not hit the API again"
    tool_messages = [m for m in completions.calls[-1]["messages"] if m["role"] == "tool"]
    assert "You already called canvas_list_courses" in json.dumps(tool_messages[-1]["content"])


def test_control_characters_stripped():
    agent, _ = make_agent([answer_turn("a1", json.dumps({"answer": "x\x02 = 1\n"}))])
    events = asyncio.run(collect(agent, "q", reset=True))
    assert events[-1]["answer"] == "x = 1\n"
    assert "\x02" not in "".join(e.get("text", "") for e in events)


# --- WebSocket handler and terminal chat ------------------------------------------------------------------

def test_websocket_chat_streams_frames_and_reset_clears_memory():
    import ws_server

    agent, _ = make_agent([
        tool_turn("c1"),
        [chunk(tool=(0, "c2", "final_answer_tool", '{"answer": "Two co')), chunk(tool=(0, None, None, 'urses."}')),
         chunk(usage=USAGE)],
    ])
    ws_server._AGENT_CACHE = agent
    frames = []

    async def send(frame):
        frames.append(json.loads(json.dumps(frame)))  # frames must be JSON-serializable

    async def run():
        chat, _ = await ws_server.handle_message({"type": "chat", "query": "courses?"}, None, send)
        assert len(agent.memory.steps) > 0
        reset, _ = await ws_server.handle_message({"type": "reset"}, None, send)
        return chat, reset

    try:
        chat, reset = asyncio.run(run())
    finally:
        ws_server._AGENT_CACHE = None
    assert chat == {"type": "answer", "answer": "Two courses.", "renders": {}, "can_escalate": False}
    assert frames[0] == {"type": "tool", "name": "canvas_list_courses"}
    assert "".join(f["text"] for f in frames if f["type"] == "delta") == "Two courses."
    assert reset == {"status": "reset"} and agent.memory.steps == []


def test_terminal_chat_renders_answer():
    import canvas_chat

    agent, completions = make_agent([answer_turn("t1", '{"answer": "**Bold** reply"}')])
    asyncio.run(canvas_chat.process_query(agent, "hi"))
    assert not completions.script, "the scripted answer should have been consumed"


# --- LaTeX ------------------------------------------------------------------------------------------------

def test_latex_extraction_rules():
    text = (
        "Inline \\(a+b\\) and $c$; prices $5 and $10; $$d=e$$ and \\[f\\]\n"
        "code `$x$` stays literal\n```chemfig\n\\chemfig{*6(=-=-=-)}\n```\n"
    )
    keys = [s.key for s in latex_svg.extract(text)]
    assert keys == ["C:\\chemfig{*6(=-=-=-)}", "I:a+b", "I:c", "D:d=e", "D:f"]


def test_chemfig_labels_made_formula_safe():
    fixed = latex_svg._fix_chemfig_labels(r"\arrow{->[1. NaOH][2. CH_3I]} \arrow{->[\ce{H2SO4}][\Delta]}")
    assert r"\ensuremath{\mathrm{CH_3I}}" in fixed and r"\ensuremath{\mathrm{\Delta}}" in fixed
    assert r"\ce{H2SO4}" in fixed and "NaOH" in fixed
    assert latex_svg._fix_chemfig_labels(r"\chemfig{H_3C-CH_2-OH}") == r"\chemfig{H_3C-CH_2-OH}"


def test_unsafe_latex_refused():
    [(svg, error)] = asyncio.run(latex_svg.render_many([latex_svg.Snippet("inline", r"\input{/etc/passwd}")]))
    assert svg is None and "not allowed" in error


def test_latex_renders_to_svg():
    if not latex_svg.available():
        print("skipped: latex/dvisvgm not installed")
        return
    scheme = (
        "\\schemestart \\chemfig{*6(-(-OH)=-=-=-)} \\arrow{->[1. NaOH][2. CH_3I]} "
        "\\chemfig{*6(-(-O-CH_3)=-=-=-)} \\schemestop"
    )
    answer = f"Inline \\(h(n) \\le h^*(n)\\), display $$\\frac{{1}}{{3}}$$\n\n```chemfig\n{scheme}\n```\n"
    renders = asyncio.run(latex_svg.render_answer(answer))
    assert set(renders) == {"I:h(n) \\le h^*(n)", "D:\\frac{1}{3}", "C:" + scheme}
    assert all(svg.startswith("<svg") and "currentColor" in svg for svg in renders.values())
    # One bad snippet must not take the others down
    results = asyncio.run(latex_svg.render_many([latex_svg.Snippet("inline", "\\frac{1}{"),
                                                 latex_svg.Snippet("inline", "x^2")]))
    assert results[0][0] is None and "unbalanced" in results[0][1]
    assert results[1][0] is not None


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
