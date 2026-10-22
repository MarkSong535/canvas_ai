"""
Per-question model routing.

Each question is routed ONCE, before the agent starts, to one of three tiers (configs: `routing`):
    simple    a single lookup of the student's Canvas data (due dates, grades, to-dos, course list)
    standard  explanations, or a few lookups combined
    hard      multi-step reasoning: derivations, proofs, problem solving, math or chemistry work
Obvious cases are decided by rules; anything unclear is classified by the cheap classifier model.
The model never changes in the middle of a question. If a run shows signs of struggle on a lower tier, the
answer carries an offer to escalate, and only the user can accept it (retry the question one tier up).
"""

import re
from dataclasses import dataclass, field

from src.exception import AgentMaxStepsError
from src.memory import ActionStep, TaskStep
from src.models import ChatMessage, MessageRole, model_manager

TIERS = ["simple", "standard", "hard"]

_HARD_RE = re.compile(
    r"\b(derive|derivation|prove|proof|step[- ]by[- ]step|mechanism|solve|calculate|compute|optimi[sz]e|"
    r"explain why|why does|why do|compare and contrast|evaluate|analy[sz]e|design|work out|integral|derivative|"
    r"equation|balance)\b|\\frac|\\int|\\ce\{|[∫∑√≤≥≠]|\d\s*[\^*/]\s*\d",
    re.I,
)
_LOOKUP_RE = re.compile(
    r"\b(due|deadlines?|to-?dos?|grades?|scores?|my courses|which courses|what courses|announcements?|calendar|"
    r"events?|upcoming|groups?|list|show|what'?s on|when is|when's|any new)\b",
    re.I,
)
_EXPLAIN_RE = re.compile(r"\b(explain|how does|how do|describe|summari[sz]e|help me understand|teach)\b", re.I)
_FOLLOW_UP_RE = re.compile(r"\b(it|that|this|those|these|them|the (first|second|third|last|other) one)\b", re.I)

_CLASSIFIER_PROMPT = (
    "You route questions for a Canvas study assistant to a model tier. Reply with exactly one word.\n"
    "simple: a single lookup of the student's own Canvas data (due dates, grades, to-dos, course list, "
    "announcements, calendar).\n"
    "standard: explaining a concept, summarizing course material, or combining a few lookups.\n"
    "hard: multi-step reasoning: derivations, proofs, solving problems, calculations, chemistry mechanisms, "
    "or comparing many sources.\n"
    "Question: {question}\n"
    "Previous question in this conversation (for context): {previous}\n"
    "Tier:"
)


@dataclass
class Route:
    tier: str
    model_id: str
    reason: str


@dataclass
class Assessment:
    """How a run went, and whether to offer the user a retry one tier up."""
    struggled: list[str] = field(default_factory=list)
    can_escalate: bool = False


@dataclass
class ConversationRouting:
    """What the last question was and how it was routed, kept per conversation for follow-ups and retries."""
    question: str = ""
    route: Route | None = None


def routing_state(agent) -> ConversationRouting:
    if not hasattr(agent, "routing_state"):
        agent.routing_state = ConversationRouting()
    return agent.routing_state


class ModelRouter:
    def __init__(self, tiers: dict[str, str], classifier_model_id: str):
        missing = [t for t in TIERS if t not in tiers]
        if missing:
            raise ValueError(f"routing config is missing tiers: {missing}")
        self.tiers = tiers
        self.classifier_model_id = classifier_model_id

    async def choose(self, question: str, previous: "Route | None" = None, previous_question: str = "") -> Route:
        tier, reason = self._by_rules(question, previous)
        if tier is None:
            tier, reason = await self._classify(question, previous_question)
        return Route(tier, self.tiers[tier], reason)

    def next_tier(self, tier: str) -> str | None:
        index = TIERS.index(tier)
        return TIERS[index + 1] if index + 1 < len(TIERS) else None

    def route_for_tier(self, tier: str, reason: str) -> Route:
        return Route(tier, self.tiers[tier], reason)

    def _by_rules(self, question: str, previous: "Route | None") -> tuple[str | None, str]:
        text = question.strip()
        if _HARD_RE.search(text) or len(text) > 400 or text.count("?") > 2:
            return "hard", "rule: reasoning, math or a long multi-part question"
        if previous and len(text) < 60 and _FOLLOW_UP_RE.search(text):
            return previous.tier, "rule: short follow-up keeps the previous tier"
        if _LOOKUP_RE.search(text) and not _EXPLAIN_RE.search(text) and len(text) < 120:
            return "simple", "rule: a Canvas lookup"
        return None, ""

    async def _classify(self, question: str, previous_question: str) -> tuple[str, str]:
        try:
            model = model_manager.get_model(self.classifier_model_id)
            prompt = _CLASSIFIER_PROMPT.format(question=question[:1500], previous=previous_question[:300] or "none")
            reply = await model.generate(
                [ChatMessage(role=MessageRole.USER, content=[{"type": "text", "text": prompt}])],
                reasoning_effort="minimal",
            )
            word = re.findall(r"[a-z]+", str(reply.content or "").lower())
            tier = next((w for w in word if w in TIERS), None)
            if tier:
                return tier, "classifier"
        except Exception as exc:  # noqa: BLE001 - routing must never block an answer
            return "standard", f"classifier failed ({type(exc).__name__}); default tier"
        return "standard", "classifier gave no tier; default tier"


def apply_route(agent, route: Route) -> None:
    """Point the agent at the routed model for the next question (never changed mid-question)."""
    model = model_manager.get_model(route.model_id)
    agent.model = model
    agent.monitor.tracked_model = model


def _last_turn_start(agent) -> int:
    """Index of the current question's TaskStep in memory (older turns may have been trimmed away)."""
    for index in range(len(agent.memory.steps) - 1, -1, -1):
        if isinstance(agent.memory.steps[index], TaskStep):
            return index
    return 0


def drop_last_turn(agent) -> None:
    """Forget the last question and its steps, so a retry starts from the conversation before it."""
    agent.memory.steps = agent.memory.steps[:_last_turn_start(agent)]


def assess_turn(agent, answer: str, route: Route, router: ModelRouter) -> Assessment:
    """Look at the steps of the question that just finished for signs the model struggled."""
    steps = [s for s in agent.memory.steps[_last_turn_start(agent):] if isinstance(s, ActionStep)]
    reasons = []
    if any(isinstance(s.error, AgentMaxStepsError) for s in steps):
        reasons.append("hit the step limit")
    elif len(steps) >= 6:
        reasons.append(f"needed {len(steps)} steps")
    # One repeat is routine for these models (and answered from memory); more than one means it's going in circles
    repeats = sum(1 for s in steps for r in (s.tool_results or {}).values() if "You already called" in r)
    if repeats >= 2:
        reasons.append("kept repeating tool calls")
    if sum(1 for s in steps if s.error is not None) >= 2:
        reasons.append("hit several errors")
    if sum(1 for s in steps for r in (s.tool_results or {}).values() if r.startswith("Does not compile")) >= 2:
        reasons.append("LaTeX kept failing to compile")
    stripped = (answer or "").strip().lower().replace("’", "'")  # models often write ’ for '
    if not stripped or re.search(r"\b(i (can't|cannot|couldn't|could not|am unable|was unable)|unable to)\b", stripped):
        reasons.append("no clear answer")
    return Assessment(struggled=reasons, can_escalate=bool(reasons) and router.next_tier(route.tier) is not None)


def build_router(agent_config: dict) -> ModelRouter | None:
    routing = agent_config.get("routing")
    if not routing:
        return None
    return ModelRouter(routing["tiers"], routing.get("classifier_model_id", routing["tiers"]["simple"]))
