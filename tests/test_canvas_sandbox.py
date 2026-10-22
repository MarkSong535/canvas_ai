"""
Canvas sandbox tests against a fake Canvas server: capture (pagination, a hidden Files tab, linked files,
downloads), then the real tools served from the sandbox, with writes recorded locally and nothing reaching
Canvas. Run with `pytest tests` or `python tests/test_canvas_sandbox.py`.
"""

import asyncio
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("CANVAS_ACCESS_TOKEN", "test-token")
os.environ.setdefault("CANVAS_URL", "https://canvas.example.com")

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

import src.canvas_sandbox as canvas_sandbox  # noqa: E402
from src.canvas_sandbox.store import SandboxStore, request_key  # noqa: E402
from src.tools import canvas_tools as ct  # noqa: E402

TOKEN = "Bearer test-token"


class FakeCanvas:
    """Just enough of the Canvas API for one student with two courses; counts every request it serves."""

    def __init__(self):
        self.hits: list[str] = []
        self.base = ""
        from test_file_text import make_docx

        # Real file contents for some ids (others download as "bytes of <id>")
        self.contents = {
            94: make_docx(["Master the Active Voice Exercise", "1. The essay was written by Maria.",
                           "2. Mistakes were made."]),
            93: ("Lecture transcript. " * 1000).encode(),  # 20,000 characters: read in parts
        }

    async def start(self):
        app = web.Application()
        app.router.add_get("/api/v1/{path:.*}", self.api)
        app.router.add_route("*", "/api/v1/{path:.*}", self.api)  # writes too, so any that leak are counted
        app.router.add_get("/dl/{file_id}", self.download)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"

    async def stop(self):
        await self.runner.cleanup()

    def body_of(self, file_id) -> bytes:
        return self.contents.get(int(file_id), f"bytes of {file_id}".encode())

    def file(self, file_id, name):
        return {"id": file_id, "display_name": name, "filename": name, "size": len(self.body_of(file_id)),
                "content-type": "application/pdf", "url": f"{self.base}/dl/{file_id}"}

    async def download(self, request):
        self.hits.append(f"download {request.match_info['file_id']}")
        return web.Response(body=self.body_of(request.match_info["file_id"]))

    async def api(self, request):
        path = request.match_info["path"]
        self.hits.append(path)
        if request.headers.get("Authorization") != TOKEN:
            return web.json_response({"errors": [{"message": "Invalid access token"}]}, status=401)
        q = request.query
        data = {
            "users/self": {"id": 7, "name": "Student"},
            "users/self/todo": [{"type": "submitting", "assignment": {"name": "Lab 1"}}],
            "users/self/upcoming_events": [],
            "users/self/groups": [],
            "courses/1/assignments": [{"id": 11, "name": "Lab 1", "description": '<a href="/courses/1/files/99">x</a>',
                                       "submission": {"workflow_state": "unsubmitted"}}],
            "courses/1/modules": [{"id": 21, "name": "Week 1"}],
            "courses/1/modules/21/items": [{"id": 31, "type": "File", "content_id": 98, "title": "Slides"},
                                           {"id": 32, "type": "Page", "page_url": "course-syllabus", "title": "0. Syllabus"}],
            "courses/1/files": [self.file(97, "syllabus.pdf"), self.file(96, "lab-report.pdf"),
                                self.file(94, "active-voice-exercise.docx"), self.file(93, "transcript.txt")],
            "courses/1/folders": [{"id": 41, "name": "course files"}],
            "folders/41/files": [self.file(97, "syllabus.pdf")],
            "courses/1/discussion_topics": [{"id": 51, "title": "Intro", "message": "hi", "discussion_subentry_count": 0}],
            "courses/1/discussion_topics/51/entries": [],
            "courses/1/pages": [{"url": "welcome", "title": "Welcome"}],
            # Linked from a module but missing from the Pages list (as in courses that hide Pages)
            "courses/1/pages/course-syllabus": {"url": "course-syllabus", "body": "Grading: 40% labs"},
            "courses/1/pages/welcome": {"url": "welcome", "body": (
                f'Welcome! <a href="/courses/1/files/97/download?wrap=1">Syllabus</a> '
                f'<a href="{self.base}/courses/1/files/96?verifier=abc">Lab</a> <img src="/courses/1/files/98/preview"> '
                '<a href="https://example.org/files/5">elsewhere</a> '
                f'<a href="{self.base}/courses/1/files/99/?location=course_syllabus_1&amp;wrap=1">Handout</a> '
                '<img src="https://instructure-uploads.s3.amazonaws.com/account_1/attachments/95/photo.png'
                '?X-Amz-Signature=abc&amp;X-Amz-Expires=600">')},
            "courses/1/quizzes": [],
            "courses/1/enrollments": [{"grades": {"current_score": 93.5}}],
            "files/98": self.file(98, "week1-slides.pdf"),
            "files/99": self.file(99, "linked-handout.pdf"),
            "files/95": self.file(95, "photo.png"),  # only reachable through a Canvas storage link
            "files/94": self.file(94, "active-voice-exercise.docx"),
            "calendar_events": [{"title": "Today", "start_at": "2026-10-21T10:00:00Z"}],
        }
        if path == "courses":
            courses = [{"id": 1, "name": "Intro AI"}, {"id": 2, "name": "Chemistry"}]
            if q.get("enrollment_state") == "completed":
                courses = []
            # Paginate one course per page, like Canvas with a small per_page
            page = int(q.get("page", 1))
            response = web.json_response(courses[page - 1:page])
            if page < len(courses):
                nxt = f'{self.base}/api/v1/courses?page={page + 1}&enrollment_state={q.get("enrollment_state", "")}'
                response.headers["Link"] = f'<{nxt}>; rel="next"'
            return response
        if path == "courses/2/files":  # Files tab hidden in this course
            return web.json_response({"status": "unauthorized", "errors": [{"message": "user not authorized"}]}, status=401)
        if path.startswith("courses/2/"):
            return web.json_response([])
        if path == "calendar_events" and q.get("all_events") == "true":
            return web.json_response([{"title": "Midterm", "start_at": "2026-11-05T09:00:00Z"},
                                      {"title": "Final", "start_at": "2026-12-10T09:00:00Z"}])
        if path == "announcements":
            codes = q.getall("context_codes[]", [])
            if not codes:
                return web.json_response({"errors": [{"message": "context_codes is required"}]}, status=400)
            if codes == ["course_1"]:
                return web.json_response([{"title": "Welcome to AI", "posted_at": "2026-09-01T00:00:00Z", "message": "x"}])
            return web.json_response([{"title": "Lab safety", "posted_at": "2026-10-01T00:00:00Z", "message": "y"}])
        if path in data:
            return web.json_response(data[path])
        return web.json_response({"errors": [{"message": "not found"}]}, status=404)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _scenario(tmp: Path):
    canvas = FakeCanvas()
    await canvas.start()
    try:
        files_port = _free_port()
        public = f"http://127.0.0.1:{files_port}"  # stands in for https://canvas.marksong.tech
        os.environ.update({"CANVAS_SANDBOX": "yes", "CANVAS_SANDBOX_DIR": str(tmp), "CANVAS_URL": canvas.base,
                           "CANVAS_SANDBOX_PUBLIC_URL": public, "CANVAS_SANDBOX_FILES_PORT": str(files_port)})
        os.environ.pop("CANVAS_SANDBOX_SOURCE_URL", None)
        canvas_sandbox._server = None

        # --- start(): no sandbox yet, so it captures everything first
        local_url = await canvas_sandbox.start(log=lambda m: None)
        assert os.environ["CANVAS_URL"] == local_url != canvas.base
        # --- after the capture nothing in the process holds the real Canvas URL or token
        simulated = os.environ["CANVAS_ACCESS_TOKEN"]
        assert simulated.startswith("sandbox-") and simulated != "test-token"
        assert not any(canvas.base in v or v == "test-token" for v in os.environ.values())
        async with aiohttp.ClientSession() as session:
            for auth, expected in ((TOKEN, 401), (None, 401), (f"Bearer {simulated}", 200)):
                headers = {"Authorization": auth} if auth else {}
                async with session.get(f"{local_url}/api/v1/users/self", headers=headers) as response:
                    assert response.status == expected, f"{auth!r} -> {response.status}"
        assert oct((tmp / "link_secret").stat().st_mode & 0o777) == "0o600", "link key is private to the sandbox"
        store = SandboxStore(tmp).load()
        assert store.manifest["complete"] and store.manifest["user_id"] == 7
        courses = store.body(request_key("GET", "courses", [("enrollment_state", "active")]))
        assert [c["name"] for c in courses] == ["Intro AI", "Chemistry"], "pages must be concatenated"
        assert store.get(request_key("GET", "courses/2/files"))["status"] == 401, "errors are replayed"
        # Files: listed, in a folder, linked from a module item and from assignment HTML, all downloaded
        assert set(store.files) == {"93", "94", "95", "96", "97", "98", "99"}
        assert (tmp / store.files["99"]["path"]).read_bytes() == b"bytes of 99"
        hits_after_capture = len(canvas.hits)

        # --- the real tools, now answered by the sandbox
        out = (await ct.CanvasListCourses()()).output
        assert "Intro AI" in out and "Chemistry" in out
        out = (await ct.CanvasGetFiles()(course_id="1", search_term="report")).output
        assert "lab-report.pdf" in out and "syllabus.pdf" not in out, "search_term is applied locally"
        result = await ct.CanvasGetFiles()(course_id="2")
        assert result.error and "401" in result.error, "the hidden Files tab answers like Canvas did"
        result = await ct.CanvasSearchFiles()(course_id="2", search_term="syllabus")
        assert result.error and "401" in result.error, "searching a hidden Files tab is refused the same way"
        out = (await ct.CanvasGetCalendarEvents()(start_date="2026-11-01", end_date="2026-11-30")).output
        assert "Midterm" in out and "Final" not in out, "date ranges are applied locally"
        out = (await ct.CanvasGetAnnouncements()(context_codes="course_1,course_2")).output
        assert "Welcome to AI" in out and "Lab safety" in out
        # --- file links point at the platform (signed, expiring), never at Canvas
        out = (await ct.CanvasGetFileInfo()(file_id="99")).output
        link = re.search(r"Download link: (\S+)", out).group(1)
        assert link.startswith(f"{public}/files/99/linked-handout.pdf?expires=") and "&sig=" in link
        async with aiohttp.ClientSession() as session:
            async with session.get(link) as response:
                assert response.status == 200 and await response.read() == b"bytes of 99"
                assert "linked-handout.pdf" in response.headers["Content-Disposition"]
            async with session.get(link[:-4] + "0000") as response:
                assert response.status == 403, "a tampered signature is refused"
            async with session.get(re.sub(r"expires=\d+", "expires=1000", link)) as response:
                assert response.status == 403, "an expired link is refused"
            async with session.get(f"{public}/api/v1/users/self") as response:
                assert response.status == 404, "the public server serves files only"
            async with session.get(f"{local_url}/files/99/download") as response:
                assert response.status == 403, "unsigned downloads are refused everywhere"
        page = (await ct.CanvasGetPageContent()(course_id="1", page_url="welcome")).output
        assert canvas.base not in page and "/courses/1/files/" not in page, "no Canvas file link is left"
        assert page.count(f"{public}/files/") == 5 and "https://example.org/files/5" in page
        assert "amazonaws" not in page, "Canvas storage links are rewritten too"
        out = (await ct.CanvasGetModuleItems()(course_id="1", module_id="21")).output
        assert "File ID: 98" in out and "Page URL: course-syllabus" in out
        out = (await ct.CanvasGetPageContent()(course_id="1", page_url="course-syllabus")).output
        assert "40% labs" in out, "pages linked only from modules are captured too"
        out = (await ct.CanvasGetGrades()(course_id="1")).output
        assert "93.5" in out
        result = await ct.CanvasGetQuizzes()(course_id="404404")
        assert result.error, "requests that were never captured fail instead of reaching Canvas"

        # --- the model can read files' text, from the sandbox's own copies
        out = (await ct.CanvasReadFile()(file_id="94")).output
        assert "Master the Active Voice Exercise" in out and "1. The essay was written by Maria." in out
        first = (await ct.CanvasReadFile()(file_id="93")).output
        assert "start=12000" in first, "long files come in parts"
        rest = (await ct.CanvasReadFile()(file_id="93", start=12000)).output
        assert "showing from character 12000" in rest and "More text follows" not in rest
        out = (await ct.CanvasReadFile()(file_id="96")).output
        assert "couldn't be read" in out, "a broken file says so instead of failing"
        missing = (await ct.CanvasReadFile()(file_id="404404")).error
        assert missing, "a file that was never captured is an error, not a Canvas request"

        # --- writes are recorded locally and show up in later reads
        out = (await ct.CanvasSubmitAssignment()(course_id="1", assignment_id="11",
                                                 submission_type="online_text_entry", body="My answer")).output
        assert "SANDBOX" in out
        assignments = await ct.CanvasGetAssignments()._make_request("GET", "courses/1/assignments")
        assert assignments[0]["submission"]["workflow_state"] == "submitted"
        out = (await ct.CanvasPostDiscussion()(course_id="1", topic_id="51", message="Hello class")).output
        assert "SANDBOX" in out
        writes = [json.loads(line) for line in open(tmp / "writes.jsonl")]
        assert [w["path"] for w in writes] == ["courses/1/assignments/11/submissions",
                                               "courses/1/discussion_topics/51/entries"]
        assert writes[0]["body"]["submission"]["body"] == "My answer"
        # Survives a restart: the recorded submission is saved in the sandbox
        reloaded = SandboxStore(tmp).load()
        assert reloaded.body(request_key("GET", "courses/1/assignments"))[0]["submission"]["sandbox"] is True

        assert len(canvas.hits) == hits_after_capture, "nothing reached Canvas after the capture"
        logged = [json.loads(line) for line in open(tmp / "requests.jsonl")]
        assert {entry["outcome"] for entry in logged} >= {"hit", "emulated", "miss", "write", "file", "unauthorized"}

        # --- a restart with only simulated credentials serves the captured sandbox (no real ones needed)
        await canvas_sandbox._server.stop()
        canvas_sandbox._server = None
        os.environ.update({"CANVAS_URL": "http://sandbox.invalid", "CANVAS_ACCESS_TOKEN": "sandbox-placeholder"})
        restarted = await canvas_sandbox.start(log=lambda m: None)
        assert "Intro AI" in (await ct.CanvasListCourses()()).output
        assert os.environ["CANVAS_URL"] == restarted
        assert len(canvas.hits) == hits_after_capture
    finally:
        if canvas_sandbox._server:
            await canvas_sandbox._server.stop()
        canvas_sandbox._server = None
        for key in ("CANVAS_SANDBOX", "CANVAS_SANDBOX_DIR", "CANVAS_SANDBOX_PUBLIC_URL", "CANVAS_SANDBOX_FILES_PORT"):
            os.environ.pop(key, None)
        os.environ["CANVAS_URL"] = "https://canvas.example.com"
        os.environ["CANVAS_ACCESS_TOKEN"] = "test-token"
        await canvas.stop()


def test_capture_then_serve_everything_locally():
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_scenario(Path(tmp)))


async def _live_mode_writes_blocked():
    canvas = FakeCanvas()
    await canvas.start()
    try:
        os.environ.pop("CANVAS_SANDBOX", None)
        canvas_sandbox._server = None
        os.environ["CANVAS_URL"] = canvas.base  # live mode, pointed at "Canvas"
        submit = await ct.CanvasSubmitAssignment()(course_id="1", assignment_id="11",
                                                   submission_type="online_text_entry", body="My answer")
        post = await ct.CanvasPostDiscussion()(course_id="1", topic_id="51", message="Hello class")
        reads = (await ct.CanvasListCourses()()).output
        ct.CanvasReadFile._text_cache.clear()  # the sandbox scenario may have cached this file's text
        worksheet = (await ct.CanvasReadFile()(file_id="94")).output
    finally:
        os.environ["CANVAS_URL"] = "https://canvas.example.com"
        await canvas.stop()
    assert submit.output is None and submit.error.startswith("Blocked")
    assert post.output is None and post.error.startswith("Blocked")
    assert "Intro AI" in reads, "reads still go to Canvas"
    assert "2. Mistakes were made." in worksheet, "live mode reads files through Canvas's download link"
    assert all(not hit.startswith("courses/1/assignments/11/submissions") and "entries" not in hit
               for hit in canvas.hits), "no write may reach Canvas"


def test_live_mode_blocks_writes_before_sending():
    asyncio.run(_live_mode_writes_blocked())


def test_write_tools_always_offered():
    from configs.canvas_agent_config import agent_config

    names = {tool.name for tool in agent_config["tools"]}
    assert {"canvas_submit_assignment", "canvas_post_discussion"} <= names


def test_sandbox_off_by_default():
    os.environ.pop("CANVAS_SANDBOX", None)
    assert canvas_sandbox.enabled() is False
    assert asyncio.run(canvas_sandbox.start()) is None


if __name__ == "__main__":
    for name, fn in [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]:
        fn()
        print(f"PASS {name}")
