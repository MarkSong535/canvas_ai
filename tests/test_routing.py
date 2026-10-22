"""
Model routing tests: rules, the classifier, one route per question, and escalation that only happens when the
user asks for it. Uses the fake streaming OpenAI client from test_end_to_end.
Run with `pytest tests` or `python tests/test_routing.py`.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_end_to_end import FakeCompletions, answer_turn, make_agent, tool_turn  # noqa: E402

from src.agent.routing import ModelRouter, Route  # noqa: E402
from src.agent.stream_events import escalate_events, stream_agent_events  # noqa: E402
from src.memory import TaskStep  # noqa: E402
from src.models import ChatMessage, MessageRole, model_manager  # noqa: E402
from src.models.openaillm import OpenAIServerModel  # noqa: E402


class FakeClassifier:
    """Stands in for the classifier model: replies with a fixed word, or raises."""

    def __init__(self, word=None):
        self.word, self.calls = word, 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        if self.word is None:
            raise RuntimeError("classifier down")
        return ChatMessage(role=MessageRole.ASSISTANT, content=self.word)


def make_router(classifier_word="standard"):
    """A router over three fake tier models; returns (router, {tier: FakeCompletions}, classifier)."""
    completions = {}
    for tier in ("simple", "standard", "hard"):
        completions[tier] = FakeCompletions([])
        model_manager.registed_models[f"fake-{tier}"] = OpenAIServerModel(
            model_id="gpt-6-luna", api_key="sk-test", http_client=NS(chat=NS(completions=completions[tier])))
    classifier = FakeClassifier(classifier_word)
    model_manager.registed_models["fake-classifier"] = classifier
    router = ModelRouter({t: f"fake-{t}" for t in completions}, "fake-classifier")
    return router, completions, classifier


async def collect(events):
    return [event async for event in events]


def test_rules_route_obvious_questions_without_the_classifier():
    router, _, classifier = make_router()
    choose = lambda q, prev=None: asyncio.run(router.choose(q, prev)).tier  # noqa: E731
    assert choose("What's due this week?") == "simple"
    assert choose("Show my grades in Chemistry") == "simple"
    assert choose("What is due tomorrow?") == "simple"
    assert choose("Derive why A* is optimal, step by step") == "hard"
    assert choose("Balance Fe + O2 -> Fe2O3") == "hard"
    assert choose("What is \\frac{1}{2} + 3^2?") == "hard"
    assert choose("what about the second one?", Route("hard", "fake-hard", "")) == "hard", "follow-ups keep the tier"
    assert classifier.calls == 0


def test_unclear_questions_go_to_the_classifier():
    router, _, classifier = make_router("standard")
    route = asyncio.run(router.choose("What is a heuristic in my AI course?"))
    assert (route.tier, route.reason, classifier.calls) == ("standard", "classifier", 1)
    router, _, _ = make_router(None)  # classifier failure falls back to the standard tier
    route = asyncio.run(router.choose("What is a heuristic in my AI course?"))
    assert route.tier == "standard" and "failed" in route.reason


def test_route_once_offer_escalation_and_retry_only_on_request():
    router, completions, _ = make_router()
    agent, _ = make_agent([])
    agent.router = router

    # A lookup goes to the simple tier and finishes cleanly: no offer
    completions["simple"].script += [tool_turn("a1"), answer_turn("a2", '{"answer": "Lab 1 is due Friday."}')]
    events = asyncio.run(collect(stream_agent_events(agent, "What's due this week?")))
    assert events[0] == {"type": "route", "tier": "simple"}
    assert events[-1]["tier"] == "simple" and events[-1]["can_escalate"] is False

    # The simple tier struggles (repeats a call): an offer, but nothing escalates on its own
    # A single repeat (routine; answered from memory) with a good answer is not a struggle
    completions["simple"].script += [tool_turn("g1"), tool_turn("g2"), answer_turn("g3", '{"answer": "Nothing is due."}')]
    events = asyncio.run(collect(stream_agent_events(agent, "Any to-dos?")))
    assert events[-1]["can_escalate"] is False and events[-1]["struggled"] == []

    # The simple tier goes in circles: an offer, but nothing escalates on its own
    completions["simple"].script += [tool_turn("b1"), tool_turn("b2"), tool_turn("b4"),
                                     answer_turn("b3", '{"answer": "Not sure."}')]
    events = asyncio.run(collect(stream_agent_events(agent, "Show my grades")))
    assert events[-1]["can_escalate"] is True and "kept repeating tool calls" in events[-1]["struggled"]
    assert not completions["standard"].calls, "no automatic escalation"

    # The user accepts: the same question is retried one tier up, replacing the struggling attempt
    completions["standard"].script += [answer_turn("c1", '{"answer": "Your current grade is 93.5%."}')]
    events = asyncio.run(collect(escalate_events(agent)))
    assert events[0] == {"type": "route", "tier": "standard"}
    assert events[-1]["answer"] == "Your current grade is 93.5%."
    tasks = [s.task for s in agent.memory.steps if isinstance(s, TaskStep)]
    assert len(tasks) == 3 and "Show my grades" in tasks[2], "the struggling attempt was replaced"
    sent = json.dumps(completions["standard"].calls[-1]["messages"])
    assert "Not sure." not in sent, "the stronger model doesn't see the failed attempt"
    assert "Lab 1 is due Friday." in sent, "but it keeps the earlier conversation"


def test_no_offer_at_the_top_tier():
    router, completions, _ = make_router()
    agent, _ = make_agent([])
    agent.router = router
    completions["hard"].script += [tool_turn("d1"), tool_turn("d2"), answer_turn("d3", '{"answer": "I cannot tell."}')]
    events = asyncio.run(collect(stream_agent_events(agent, "Prove the theorem step by step")))
    assert events[-1]["tier"] == "hard" and events[-1]["struggled"] and events[-1]["can_escalate"] is False
    events = asyncio.run(collect(escalate_events(agent)))
    assert events[-1]["can_escalate"] is False and "no earlier answer" in events[-1]["answer"].lower()


def test_websocket_escalate_message():
    import ws_server

    router, completions, _ = make_router()
    agent, _ = make_agent([])
    agent.router = router
    ws_server._AGENT_CACHE = agent
    completions["simple"].script += [tool_turn("e1"), tool_turn("e2"), tool_turn("e4"), answer_turn("e3", '{"answer": "Hmm."}')]
    completions["standard"].script += [answer_turn("f1", '{"answer": "Here it is."}')]
    frames = []

    async def send(frame):
        frames.append(frame)

    async def run():
        first, _ = await ws_server.handle_message({"type": "chat", "query": "List my courses"}, None, send)
        retry, _ = await ws_server.handle_message({"type": "escalate"}, None, send)
        return first, retry

    try:
        first, retry = asyncio.run(run())
    finally:
        ws_server._AGENT_CACHE = None
    assert first["tier"] == "simple" and first["can_escalate"] is True
    assert retry["tier"] == "standard" and retry["answer"] == "Here it is." and retry["can_escalate"] is False
    assert {"type": "route", "tier": "standard"} in frames


if __name__ == "__main__":
    for name, fn in [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]:
        fn()
        print(f"PASS {name}")
