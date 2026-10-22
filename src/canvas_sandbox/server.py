"""
Local Canvas look-alike for sandbox mode: answers /api/v1/... from the SandboxStore and serves downloaded files,
so every Canvas client in the app (tools, file downloader, course picker) works unchanged against it.

Reads: an exact captured response first (errors included, e.g. a hidden Files tab's 401); otherwise requests
whose parameters can't be pre-captured are answered from captured data (file search, calendar date ranges,
announcements for several courses); anything else is a 404 saying it wasn't captured.
Writes (POST/PUT/PATCH/DELETE): recorded in writes.jsonl and never sent anywhere. Submissions and discussion
replies also update the captured data, so later reads show them.
Every request is logged to requests.jsonl.

File links: no response ever points at Canvas. Every Canvas file link (file objects' download URLs, module items,
links inside page/assignment/announcement HTML) is rewritten to this platform as a signed, expiring link. With a
public URL configured, a separate files-only server serves those links (the API server stays on loopback);
without one the API server serves them itself.

The API only accepts the simulated access token the sandbox was started with; the real Canvas token is never
accepted, and this server never knows it.
"""

import datetime as dt
import hashlib
import hmac
import itertools
import re
import time
from typing import Any
from urllib.parse import quote, urlparse

from aiohttp import web

from src.canvas_sandbox.store import SandboxStore, request_key

SUBMISSION_RE = re.compile(r"courses/(\d+)/assignments/(\d+)/submissions")
ENTRY_RE = re.compile(r"courses/(\d+)/discussion_topics/(\d+)/entries")
COURSE_FILES_RE = re.compile(r"courses/(\d+)/files")


def _error(message: str) -> dict:
    return {"errors": [{"message": message}]}


class FileLinks:
    """Signed, expiring public download links: {public_url}/files/<id>/<name>?expires=<ts>&sig=<hmac>."""

    def __init__(self, public_url: str, secret: bytes, ttl_seconds: int):
        self.public_url = public_url.rstrip("/")
        self.secret = secret
        self.ttl_seconds = ttl_seconds

    def _sign(self, file_id: str, expires: int) -> str:
        return hmac.new(self.secret, f"{file_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]

    def link(self, file_id: str, name: str) -> str:
        expires = int(time.time()) + self.ttl_seconds
        return (f"{self.public_url}/files/{file_id}/{quote(name or 'file', safe='')}"
                f"?expires={expires}&sig={self._sign(file_id, expires)}")

    def valid(self, file_id: str, expires: str, sig: str) -> bool:
        if not expires.isdigit() or int(expires) < time.time():
            return False
        return hmac.compare_digest(self._sign(file_id, int(expires)), sig)


class SandboxServer:
    def __init__(self, store: SandboxStore, token: str, file_links: FileLinks | None = None):
        self.store = store
        self.token = token  # the simulated access token; the real Canvas token is never accepted (or known) here
        self.file_links = file_links
        self.base_url = ""
        self._runners: list[web.AppRunner] = []
        self._ids = itertools.count(int(time.time()))
        # Canvas file links in captured data, absolute (on the captured Canvas host) or relative:
        # /files/123, /courses/4/files/123/download?wrap=1, /api/v1/courses/4/files/123, ...
        host = re.escape(urlparse(store.manifest.get("source") or "").netloc or "canvas.invalid")
        self._canvas_file_link = re.compile(
            r"(?<![\w.:/%-])(?:https?://" + host + r")?/(?:api/v1/)?(?:(?:courses|users|groups)/\d+/)?"
            r"files/(\d+)(?:/(?:download|preview)?)?(?:\?[^\s\"'<>)]*)?(?=[\s\"'<>)]|$)"
        )
        # Canvas's file storage links: the attachment id is the file id
        self._canvas_storage_link = re.compile(
            r"https?://instructure-uploads[\w.-]*\.amazonaws\.com/[^\s\"'<>)]*?/attachments/(\d+)/[^\s\"'<>)]*"
        )

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        """Start the API server (loopback only; it holds all captured data and accepts writes)."""
        app = web.Application(client_max_size=64 * 1024 * 1024)
        app.router.add_route("*", "/api/v1/{path:.*}", self.api)
        app.router.add_get("/files/{file_id}/{name}", self.public_download)  # signed links when there's no public URL
        port = await self._serve(app, host, port)
        self.base_url = f"http://{host}:{port}"
        return self.base_url

    async def start_public_files(self, host: str, port: int) -> int:
        """Start the files-only server behind the public URL: signed links in, file bytes out, nothing else."""
        app = web.Application()
        app.router.add_get("/files/{file_id}/{name}", self.public_download)
        return await self._serve(app, host, port)

    async def _serve(self, app: web.Application, host: str, port: int) -> int:
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        self._runners.append(runner)
        return site._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for runner in self._runners:
            await runner.cleanup()
        self._runners = []

    # --- handlers ---

    async def api(self, request: web.Request) -> web.Response:
        path = request.match_info["path"].strip("/")
        params = list(request.query.items())
        if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {self.token}"):
            self.store.log_request({"method": request.method, "path": path, "query": params,
                                    "outcome": "unauthorized", "status": 401})
            return web.json_response({"status": "unauthenticated", "errors": [{"message": "Invalid access token."}]},
                                     status=401)
        if request.method == "GET":
            outcome, status, body = self._read(path, params)
        else:
            payload = await self._payload(request)
            outcome, status, body = "write", 200, self._write(request.method, path, params, payload)
        self.store.log_request({"method": request.method, "path": path, "query": params,
                                "outcome": outcome, "status": status})
        return web.json_response(self._localize(body), status=status)

    async def public_download(self, request: web.Request) -> web.StreamResponse:
        file_id = request.match_info["file_id"]
        ok = self.file_links is not None and self.file_links.valid(
            file_id, request.query.get("expires", ""), request.query.get("sig", ""))
        path = self.store.file_path(file_id) if ok else None
        status = 200 if path else (404 if ok else 403)
        self.store.log_request({"method": "GET", "path": f"public/files/{file_id}", "outcome": "file" if path else
                                ("miss" if ok else "bad-link"), "status": status})
        if not ok:
            return web.Response(status=403, text="This download link is invalid or has expired. Ask the assistant again for a fresh link.")
        if not path:
            return web.Response(status=404, text="This file isn't available: Canvas didn't allow it to be downloaded.")
        name = (self.store.files.get(file_id) or {}).get("display_name") or path.name
        return web.FileResponse(path, headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
            "Cache-Control": "private, max-age=3600",
        })

    # --- reads ---

    def _read(self, path: str, params: list[tuple[str, str]]) -> tuple[str, int, Any]:
        entry = self.store.get(request_key("GET", path, params))
        if entry:
            return "hit", entry["status"], entry["body"]
        # A filtered request on an endpoint Canvas refused (e.g. searching a hidden Files tab): same refusal
        if any(key == "search_term" for key, _ in params):
            base = self.store.get(request_key("GET", path))
            if base and base["status"] != 200:
                return "hit", base["status"], base["body"]
        emulated = self._emulate(path, params)
        if emulated is not None:
            return "emulated", 200, emulated
        return "miss", 404, _error(
            f"Not captured in the Canvas sandbox: GET {path}. Run `python -m src.canvas_sandbox sync` to refresh it."
        )

    def _emulate(self, path: str, params: list[tuple[str, str]]) -> Any:
        values: dict[str, list[str]] = {}
        for key, value in params:
            values.setdefault(key, []).append(value)

        search = (values.get("search_term") or [""])[0].strip().lower()
        if search and COURSE_FILES_RE.fullmatch(path):
            files = self.store.body(request_key("GET", path))
            if isinstance(files, list):
                return [f for f in files
                        if search in str(f.get("display_name", "")).lower() or search in str(f.get("filename", "")).lower()]

        if path == "announcements" and values.get("context_codes[]"):
            merged, found = [], False
            for code in values["context_codes[]"]:
                for code_part in code.split(","):
                    items = self.store.body(request_key("GET", "announcements", [("context_codes[]", code_part.strip())]))
                    if isinstance(items, list):
                        found = True
                        merged.extend(items)
            if found:
                return sorted(merged, key=lambda a: a.get("posted_at") or "", reverse=True)

        if path == "calendar_events" and (values.get("start_date") or values.get("end_date")):
            events = self.store.body(request_key("GET", "calendar_events", [("all_events", "true")]))
            if isinstance(events, list):
                start = (values.get("start_date") or [""])[0][:10]
                end = (values.get("end_date") or ["9999-12-31"])[0][:10]
                return [e for e in events if start <= (e.get("start_at") or "")[:10] <= end]
        return None

    # --- writes ---

    async def _payload(self, request: web.Request) -> Any:
        if request.can_read_body:
            try:
                return await request.json()
            except ValueError:
                try:
                    return dict(await request.post())
                except ValueError:
                    return {"raw": (await request.text())[:10000]}
        return None

    def _write(self, method: str, path: str, params: list, payload: Any) -> dict:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        note = "Recorded in the local Canvas sandbox; nothing was sent to Canvas."
        submission_match = SUBMISSION_RE.fullmatch(path)
        entry_match = ENTRY_RE.fullmatch(path)

        if method == "POST" and submission_match:
            course_id, assignment_id = submission_match.groups()
            submission = (payload or {}).get("submission") or {}
            result = {
                "id": f"sandbox-{next(self._ids)}", "assignment_id": int(assignment_id), "course_id": int(course_id),
                "workflow_state": "submitted", "submitted_at": now,
                "submission_type": submission.get("submission_type"),
                "body": submission.get("body"), "url": submission.get("url"),
                "sandbox": True, "note": note,
            }
            self._apply_submission(course_id, assignment_id, result)
        elif method == "POST" and entry_match:
            course_id, topic_id = entry_match.groups()
            result = {
                "id": f"sandbox-{next(self._ids)}", "message": (payload or {}).get("message"), "created_at": now,
                "user_id": self.store.manifest.get("user_id"), "sandbox": True, "note": note,
            }
            self._apply_entry(course_id, topic_id, result)
        else:
            result = {"sandbox": True, "recorded": True, "method": method, "path": path, "note": note}

        self.store.record_write({"method": method, "path": path, "query": params, "body": payload, "response": result})
        return result

    def _apply_submission(self, course_id: str, assignment_id: str, submission: dict) -> None:
        key = request_key("GET", f"courses/{course_id}/assignments")
        assignments = self.store.body(key)
        if isinstance(assignments, list):
            for assignment in assignments:
                if str(assignment.get("id")) == assignment_id:
                    assignment["submission"] = {**(assignment.get("submission") or {}), **submission}
                    assignment["has_submitted_submissions"] = True
            self.store.save()

    def _apply_entry(self, course_id: str, topic_id: str, entry: dict) -> None:
        entries_key = request_key("GET", f"courses/{course_id}/discussion_topics/{topic_id}/entries")
        entries = self.store.body(entries_key)
        self.store.put(entries_key, 200, (entries if isinstance(entries, list) else []) + [entry])
        topics = self.store.body(request_key("GET", f"courses/{course_id}/discussion_topics"))
        for topic in topics if isinstance(topics, list) else []:
            if str(topic.get("id")) == topic_id:
                topic["discussion_subentry_count"] = (topic.get("discussion_subentry_count") or 0) + 1
        self.store.save()

    # --- responses ---

    def file_link(self, file_id: Any, name: str | None = None) -> str:
        """Signed download link for a file: on the public URL if configured, else on this server."""
        file_id = str(file_id)
        if name is None:
            entry = self.store.files.get(file_id) or {}
            name = entry.get("display_name") or (self.store.body(request_key("GET", f"files/{file_id}")) or {}).get("display_name")
        return self.file_links.link(file_id, name or "file")

    def _localize(self, body: Any) -> Any:
        """Copy of `body` in which no file link points at Canvas: each one is rewritten to this platform."""
        if isinstance(body, list):
            return [self._localize(item) for item in body]
        if isinstance(body, dict):
            out = {key: self._localize(value) for key, value in body.items()}
            if "id" in out and "url" in out and ("display_name" in out or "filename" in out):
                out["url"] = self.file_link(out["id"], out.get("display_name") or out.get("filename"))
            return out
        if isinstance(body, str):
            if "instructure-uploads" in body:
                body = self._canvas_storage_link.sub(lambda m: self.file_link(m.group(1)), body)
            if "files/" in body:
                body = self._canvas_file_link.sub(lambda m: self.file_link(m.group(1)), body)
        return body
