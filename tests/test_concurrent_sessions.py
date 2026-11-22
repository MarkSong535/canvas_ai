"""
Two students' conversations overlapping on one server must not share anything.

Alice and Bob connect over real WebSockets, each with their own fake Canvas account (the fake Canvas answers by
bearer token). The model is scripted, but its answers list exactly which course names were in the context it was
sent, so any leaked history or tool output shows up in the answer. Run with `pytest tests` or
`python tests/test_concurrent_sessions.py`.
"""

import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiohttp import web  # noqa: E402
import websockets  # noqa: E402

from test_end_to_end import USAGE, FakeStream, chunk  # noqa: E402 - also sets placeholder env vars
import ws_server  # noqa: E402
from configs.canvas_agent_config import agent_config  # noqa: E402
from src.canvas_account import CanvasAccount  # noqa: E402
from src.models.openaillm import OpenAIServerModel  # noqa: E402
from src.registry import AGENT  # noqa: E402
from src.tools.canvas_tools import CanvasListCourses  # noqa: E402

COURSES = {
    "alice-token": [{"id": 101, "name": "Alice Organic Chemistry", "course_code": "CHEM-A"}],
    "bob-token": [{"id": 202, "name": "Bob Medieval History", "course_code": "HIST-B"}],
}
ALICE_COURSE, BOB_COURSE = "Alice Organic Chemistry", "Bob Medieval History"


class FakeCanvas:
    """Answers every request with the data of the account whose token it carries, and records who asked."""

    def __init__(self):
        self.hits = []  # (token, path)
        self.hold = {}  # token -> (arrived, release): park that account's next course-list request
        self.hold_downloads = {}  # file name -> (arrived, release)
        self.url = None

    async def start(self):
        app = web.Application()
        app.router.add_get("/api/v1/courses", self.courses)
        app.router.add_get("/api/v1/courses/{course_id}/modules", self.empty)
        app.router.add_get("/api/v1/courses/{course_id}/files", self.files)
        app.router.add_get("/dl/{name}", self.download)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"

    async def stop(self):
        await self.runner.cleanup()

    def _token(self, request):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        self.hits.append((token, request.path))
        if token not in COURSES:
            raise web.HTTPUnauthorized()
        return token

    async def courses(self, request):
        token = self._token(request)
        if token in self.hold:
            arrived, release = self.hold.pop(token)
            arrived.set()
            await release.wait()
        return web.json_response(COURSES[token])

    async def empty(self, request):
        self._token(request)
        return web.json_response([])

    async def files(self, request):
        token = self._token(request)
        owner = token.split("-")[0]
        if int(request.match_info["course_id"]) not in {c["id"] for c in COURSES[token]}:
            raise web.HTTPForbidden()
        body = f"{owner}'s notes"
        return web.json_response([{"id": 1, "display_name": f"{owner}_notes.txt", "size": len(body),
                                   "url": f"{self.url}/dl/{owner}_notes.txt"}])

    async def download(self, request):
        name = request.match_info["name"]
        if name in self.hold_downloads:
            arrived, release = self.hold_downloads.pop(name)
            arrived.set()
            await release.wait()
        return web.Response(text=f"{name.split('_')[0]}'s notes")


class ContextEchoModel:
    """Per-conversation scripted model. Each step either calls canvas_list_courses or answers with the course
    names found anywhere in the context it was sent, so the answer exposes exactly what the agent remembered."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs["messages"])
        step = self.steps.pop(0)
        call_id = f"c{len(self.requests)}"
        if step == "tool":
            return FakeStream([chunk(tool=(0, call_id, "canvas_list_courses", "{}")), chunk(usage=USAGE)])
        context = json.dumps(kwargs["messages"], default=str)
        seen = [name for name in (ALICE_COURSE, BOB_COURSE) if name in context]
        answer = json.dumps({"answer": "Courses I know about: " + (", ".join(seen) or "none")})
        return FakeStream([chunk(tool=(0, call_id, "final_answer_tool", answer)), chunk(usage=USAGE)])


def agent_for(account, model_steps):
    """A real agent with the real Canvas tool bound to `account`, driven by the context-echo model."""
    completions = ContextEchoModel(model_steps[account.key])
    model = OpenAIServerModel(model_id="gpt-6-luna", api_key="sk-test",
                              http_client=NS(chat=NS(completions=completions)), reasoning_effort="none")
    agent = AGENT.build(dict(
        type="general_agent", config=agent_config, model=model, tools=[CanvasListCourses(account)],
        max_steps=5, stream_outputs=True, max_history_turns=agent_config["max_history_turns"],
        name="canvas_student_agent", description="test",
    ))
    agent.completions = completions
    return agent


async def recv_until_final(socket, frames):
    """Collect frames until the reply that ends a request (an answer, a status or an error)."""
    while True:
        frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        frames.append(frame)
        if frame.get("type") == "answer" or "status" in frame or "error" in frame:
            return frame


async def _overlapping_chats():
    canvas = FakeCanvas()
    await canvas.start()
    accounts = {
        "alice": CanvasAccount(key="alice", url=canvas.url, token="alice-token"),
        "bob": CanvasAccount(key="bob", url=canvas.url, token="bob-token"),
    }
    model_steps = {"alice": ["tool", "answer", "answer"], "bob": ["tool", "answer"]}
    agents = {}

    async def resolve(verification):
        return accounts[verification["token"]]

    def factory(account):
        agents[account.key] = agent_for(account, model_steps)
        return agents[account.key]

    async def accept(token):
        return token in accounts

    saved = ws_server.ACCOUNT_RESOLVER, ws_server.AGENT_FACTORY, ws_server.verify_turnstile_token
    ws_server.ACCOUNT_RESOLVER, ws_server.AGENT_FACTORY, ws_server.verify_turnstile_token = resolve, factory, accept
    server = await websockets.serve(ws_server.websocket_handler, "127.0.0.1", 0, logger=None)
    url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    frames = {"alice": [], "bob": []}
    try:
        alice = await websockets.connect(url)
        bob = await websockets.connect(url)
        for name, socket in (("alice", alice), ("bob", bob)):
            await socket.send(json.dumps({"type": "verify", "token": name}))
            assert await recv_until_final(socket, frames[name]) == {"status": "verified"}

        # Alice's course lookup is parked inside Canvas while Bob finishes a whole turn and resets
        alice_waiting, release_alice = asyncio.Event(), asyncio.Event()
        canvas.hold["alice-token"] = (alice_waiting, release_alice)
        await alice.send(json.dumps({"type": "chat", "query": "What are my courses?"}))
        await asyncio.wait_for(alice_waiting.wait(), timeout=10)

        await bob.send(json.dumps({"type": "chat", "query": "What are my courses?"}))
        bob_answer = await recv_until_final(bob, frames["bob"])
        await bob.send(json.dumps({"type": "reset"}))
        assert await recv_until_final(bob, frames["bob"]) == {"status": "reset"}
        assert agents["bob"].memory.steps == []

        release_alice.set()
        alice_answer = await recv_until_final(alice, frames["alice"])

        # Bob leaves; Alice's conversation carries on with her own history
        await bob.close()
        await alice.send(json.dumps({"type": "chat", "query": "Remind me which ones those were?"}))
        alice_follow_up = await recv_until_final(alice, frames["alice"])
        await alice.close()
    finally:
        server.close()
        await server.wait_closed()
        ws_server.ACCOUNT_RESOLVER, ws_server.AGENT_FACTORY, ws_server.verify_turnstile_token = saved
        await canvas.stop()
    return canvas, agents, frames, bob_answer, alice_answer, alice_follow_up


def test_overlapping_conversations_stay_separate():
    canvas, agents, frames, bob_answer, alice_answer, alice_follow_up = asyncio.run(_overlapping_chats())

    # Each Canvas request used the right student's credentials (one course lookup each)
    assert sorted(canvas.hits) == [("alice-token", "/api/v1/courses"), ("bob-token", "/api/v1/courses")]

    # Each socket got only its own progress frames and answer
    assert bob_answer["answer"] == f"Courses I know about: {BOB_COURSE}"
    assert alice_answer["answer"] == f"Courses I know about: {ALICE_COURSE}"
    for name, other in (("alice", BOB_COURSE), ("bob", ALICE_COURSE)):
        assert other not in json.dumps(frames[name]), f"{name} received the other student's data"
    assert [f for f in frames["bob"] if f.get("type") == "tool"] == [{"type": "tool", "name": "canvas_list_courses"}]
    assert [f for f in frames["alice"] if f.get("type") == "tool"] == [{"type": "tool", "name": "canvas_list_courses"}]

    # Alice's follow-up, after Bob's reset and disconnect, answered from her own history without a new lookup
    assert alice_follow_up["answer"] == f"Courses I know about: {ALICE_COURSE}"
    follow_up_context = json.dumps(agents["alice"].completions.requests[-1], default=str)
    assert ALICE_COURSE in follow_up_context and BOB_COURSE not in follow_up_context
    assert agents["alice"].completions.steps == [] and agents["bob"].completions.steps == []


async def _overlapping_downloads(workdir):
    canvas = FakeCanvas()
    await canvas.start()
    conversations = {
        name: ws_server.Conversation(account=CanvasAccount(key=name, url=canvas.url, token=f"{name}-token"),
                                     agent=None)
        for name in ("alice", "bob")
    }

    async def ignore(frame):
        raise AssertionError(f"downloads stream nothing: {frame}")

    async def download(name):
        conversation = conversations[name]
        listing = await ws_server.handle_message(conversation, {"type": "download"}, ignore)
        result = await ws_server.handle_message(conversation, {"type": "download", "course_indices": [1]}, ignore)
        return listing, result

    try:
        # Alice's file transfer is parked until Bob's whole job has finished, so the two jobs overlap
        alice_waiting, release_alice = asyncio.Event(), asyncio.Event()
        canvas.hold_downloads["alice_notes.txt"] = (alice_waiting, release_alice)
        alice_job = asyncio.ensure_future(download("alice"))
        await asyncio.wait_for(alice_waiting.wait(), timeout=10)
        bob_listing, bob_result = await download("bob")
        assert not alice_job.done()
        release_alice.set()
        alice_listing, alice_result = await asyncio.wait_for(alice_job, timeout=10)
    finally:
        await canvas.stop()
    return canvas, conversations, (alice_listing, alice_result), (bob_listing, bob_result)


def test_overlapping_downloads_stay_separate():
    previous = os.getcwd()
    saved_key = os.environ.pop("OPENAI_API_KEY", None)  # no knowledge-base upload: nothing leaves the machine
    with tempfile.TemporaryDirectory() as workdir:
        os.chdir(workdir)
        try:
            canvas, conversations, alice, bob = asyncio.run(_overlapping_downloads(workdir))
            files = sorted(
                os.path.relpath(os.path.join(dirpath, f), workdir)
                for dirpath, _, names in os.walk(workdir) for f in names if f.endswith(".txt")
            )
            contents = {path: open(os.path.join(workdir, path)).read() for path in files}
        finally:
            os.chdir(previous)
            if saved_key is not None:
                os.environ["OPENAI_API_KEY"] = saved_key

    for (listing, result), course in ((alice, COURSES["alice-token"][0]), (bob, COURSES["bob-token"][0])):
        # Selections: each saw and picked only its own course list
        assert [c["id"] for c in listing["courses"]] == [course["id"]]
        assert result["status"] == "completed"
        # Counters: one course and one file each, no matter how the jobs interleaved
        stats = result["stats"]
        assert (stats["courses"], stats["files_total"], stats["files_downloaded"], stats["errors"]) == (1, 1, 1, [])
    assert all(c.pending_courses is None for c in conversations.values())

    # Output: each student's files are in their own folder, with their own content
    assert files == [
        os.path.join("file_index_students", "alice", "CHEM-A_Alice Organic Chemistry", "Files", "alice_notes.txt"),
        os.path.join("file_index_students", "bob", "HIST-B_Bob Medieval History", "Files", "bob_notes.txt"),
    ]
    assert [contents[f] for f in files] == ["alice's notes", "bob's notes"]

    # Every Canvas call used the token of the account whose course it touched
    for token, path in canvas.hits:
        if path.startswith("/api/v1/courses/"):
            course_id = int(path.split("/")[4])
            assert course_id in {c["id"] for c in COURSES[token]}, (token, path)


def test_request_limit_queues_instead_of_refusing():
    assert ws_server._parse_max_concurrent_requests(None) is None
    assert ws_server._parse_max_concurrent_requests("  ") is None
    assert ws_server._parse_max_concurrent_requests("abc") is None
    assert ws_server._parse_max_concurrent_requests("0") == 1
    assert ws_server._parse_max_concurrent_requests("3") == 3

    started, release_first = [], asyncio.Event()

    async def request(name):
        started.append(name)
        if name == "first":
            await release_first.wait()
        return {"done": name}

    async def run():
        first = asyncio.ensure_future(ws_server._run_request(request("first")))
        second = asyncio.ensure_future(ws_server._run_request(request("second")))
        await asyncio.sleep(0.05)
        waiting = list(started)  # the second must still be queued behind the first
        release_first.set()
        return waiting, await first, await second

    saved = ws_server.MAX_CONCURRENT_REQUESTS
    ws_server.MAX_CONCURRENT_REQUESTS = 1
    try:
        waiting, first, second = asyncio.run(run())
    finally:
        ws_server.MAX_CONCURRENT_REQUESTS = saved
    assert waiting == ["first"]
    assert (first, second) == ({"done": "first"}, {"done": "second"})


if __name__ == "__main__":
    for name, fn in [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]:
        fn()
        print(f"PASS {name}")
