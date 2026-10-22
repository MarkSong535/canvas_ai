"""
Capture everything the Canvas tools could ask for into a SandboxStore, using the real Canvas API and token,
then download every file.

Crawl plan (all list endpoints are followed to the last page):
- the user, to-dos, upcoming events, groups, calendar events (as the tool asks, and all events for date filters)
- courses in every enrollment state, with every include the course tool can request
- per course: assignments (with submissions), modules and their items, files, folders and their files,
  discussion topics and their entries, pages and each page's content, quizzes, the student's enrollment
  (grades), and announcements over the course's whole history (Canvas defaults to the last 14 days)
- files referenced anywhere (module items, links in syllabus/assignment/page/discussion/announcement HTML),
  so courses that hide their Files tab still get their linked files
Failed endpoints (e.g. a hidden Files tab answers 401) are stored with their status, so the sandbox replays
the same error the tool would have seen.
"""

import asyncio
import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import aiohttp

from src.canvas_sandbox.store import SandboxStore, request_key

COURSE_STATES = [None, "active", "completed", "invited_or_pending"]
COURSE_INCLUDES = ["total_students", "teachers", "syllabus_body"]
# File ids in links: /files/<id> on Canvas, and Canvas's file storage (instructure-uploads...amazonaws.com/
# .../attachments/<id>/...), where the attachment id is the file id
FILE_LINK_RE = re.compile(r"/files/(\d+)|instructure-uploads[\w.-]*\.amazonaws\.com/[^\s\"'<>]*?/attachments/(\d+)/")
CONCURRENCY = 4
PER_PAGE = 100


def _ok_list(status: int, body: Any) -> list:
    return body if status == 200 and isinstance(body, list) else []


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1:part.find(">")]
    return None


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name or "unnamed").strip(" .")
    return name[:180] or "unnamed"


class CanvasCrawler:
    def __init__(self, store: SandboxStore, canvas_url: str, token: str, log: Callable[[str], None] = print):
        self.store = store
        self.api = canvas_url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.log = log
        self.semaphore = asyncio.Semaphore(CONCURRENCY)
        self.errors: dict[str, int] = {}
        self.file_meta: dict[str, dict] = {}
        self.linked_file_ids: set[str] = set()
        self.request_count = 0

    async def fetch(self, session: aiohttp.ClientSession, path: str, params: list[tuple[str, Any]] = (),
                    key: str | None = None) -> tuple[int, Any]:
        """GET every page of `path`, store the result under `key` (default: the request's key), return it."""
        key = key or request_key("GET", path, params)
        url: str | None = f"{self.api}/{path}"
        query: list | None = list(params) + [("per_page", PER_PAGE)]
        items: list = []
        status, body = 0, None
        while url:
            status, body, link = await self._get(session, url, query)
            if status != 200:
                break
            if isinstance(body, list):
                items.extend(body)
                url, query = _next_link(link), None  # the next-page link carries the query
            else:
                url = None
        if status == 200 and isinstance(body, list):
            body = items
        if status != 200:
            self.errors[key] = status
        self.store.put(key, status, body)
        return status, body

    async def _get(self, session, url, query) -> tuple[int, Any, str]:
        for attempt in range(5):
            try:
                async with self.semaphore:
                    self.request_count += 1
                    async with session.get(url, headers=self.headers, params=query,
                                           timeout=aiohttp.ClientTimeout(total=60)) as response:
                        status, text, link = response.status, await response.text(), response.headers.get("Link", "")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                status, text, link = 599, json.dumps({"errors": [{"message": f"Request error: {exc}"}]}), ""
            if status == 403 and "Rate Limit Exceeded" in text or status in (429, 599):
                await asyncio.sleep(2 ** attempt)  # back off and retry
                continue
            break
        try:
            body = json.loads(text) if text else None
        except ValueError:
            body = {"errors": [{"message": text[:300]}]}
        return status, body, link

    def _scan_html(self, html: Any) -> None:
        if isinstance(html, str):
            self.linked_file_ids.update(a or b for a, b in FILE_LINK_RE.findall(html))

    def _add_files(self, status: int, body: Any) -> None:
        for meta in _ok_list(status, body):
            file_id = str(meta.get("id"))
            self.file_meta[file_id] = meta
            # A listed file object is what GET files/<id> returns, so it answers that request too
            self.store.put(request_key("GET", f"files/{file_id}"), 200, meta)

    async def crawl(self) -> dict:
        started = time.time()
        async with aiohttp.ClientSession() as session:
            status, me = await self.fetch(session, "users/self")
            if status != 200:
                raise RuntimeError(f"Canvas rejected the access token (HTTP {status}); nothing was captured.")
            user_id = me["id"]
            await asyncio.gather(
                self.fetch(session, "users/self/todo"),
                self.fetch(session, "users/self/upcoming_events"),
                self.fetch(session, "users/self/groups"),
                self.fetch(session, "calendar_events"),
                # Every event, so the sandbox can answer any start_date / end_date range itself
                self.fetch(session, "calendar_events", [("all_events", "true")]),
                self.fetch(session, "announcements"),
            )

            courses: dict[int, dict] = {}
            for state in COURSE_STATES:
                params = [("include[]", inc) for inc in COURSE_INCLUDES]
                if state:
                    params.append(("enrollment_state", state))
                for course in _ok_list(*await self.fetch(session, "courses", params)):
                    courses[course["id"]] = course
            self.log(f"Sandbox sync: {len(courses)} courses; capturing each one...")

            done = 0

            async def crawl_course(course):
                nonlocal done
                await self._crawl_course(session, course, user_id)
                done += 1
                if done % 10 == 0 or done == len(courses):
                    self.log(f"Sandbox sync: {done}/{len(courses)} courses captured ({self.request_count} requests)")

            await asyncio.gather(*(crawl_course(c) for c in courses.values()))

            # Files only reachable through links (hidden Files tab, module items, embedded links)
            missing = sorted(self.linked_file_ids - set(self.file_meta))
            self.log(f"Sandbox sync: fetching metadata for {len(missing)} linked files...")
            for status, meta in await asyncio.gather(*(self.fetch(session, f"files/{fid}") for fid in missing)):
                if status == 200 and isinstance(meta, dict):
                    self.file_meta[str(meta.get("id"))] = meta

            downloaded, skipped, failed = await self._download_files(session)

        self.store.manifest = {
            "complete": True,
            "created": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": self.api.split("/api/v1")[0],
            "user_id": user_id,
            "duration_s": round(time.time() - started, 1),
            "requests": self.request_count,
            "counts": {
                "responses": len(self.store.responses),
                "courses": len(courses),
                "files_known": len(self.file_meta),
                "files_downloaded": downloaded,
                "files_unavailable": skipped,
                "files_failed": len(failed),
            },
            "errors": self.errors,
            "file_errors": failed,
        }
        return self.store.manifest

    async def _crawl_course(self, session, course: dict, user_id: int) -> None:
        cid = course["id"]
        base = f"courses/{cid}"
        self._scan_html(course.get("syllabus_body"))

        for assignment in _ok_list(*await self.fetch(session, f"{base}/assignments", [("include[]", "submission")])):
            self._scan_html(assignment.get("description"))

        linked_pages: set[str] = set()
        for module in _ok_list(*await self.fetch(session, f"{base}/modules")):
            for item in _ok_list(*await self.fetch(session, f"{base}/modules/{module['id']}/items")):
                if item.get("type") == "File" and item.get("content_id"):
                    self.linked_file_ids.add(str(item["content_id"]))
                elif item.get("type") == "Page" and item.get("page_url"):
                    linked_pages.add(item["page_url"])

        self._add_files(*await self.fetch(session, f"{base}/files"))
        for folder in _ok_list(*await self.fetch(session, f"{base}/folders")):
            self._add_files(*await self.fetch(session, f"folders/{folder['id']}/files"))

        for topic in _ok_list(*await self.fetch(session, f"{base}/discussion_topics")):
            self._scan_html(topic.get("message"))
            for entry in _ok_list(*await self.fetch(session, f"{base}/discussion_topics/{topic['id']}/entries")):
                self._scan_html(entry.get("message"))

        listed_pages = {page["url"] for page in _ok_list(*await self.fetch(session, f"{base}/pages"))}
        # Pages linked from modules count too: many courses hide the Pages list but link pages in modules
        for page_url in sorted(listed_pages | linked_pages):
            status, content = await self.fetch(session, f"{base}/pages/{page_url}")
            if status == 200 and isinstance(content, dict):
                self._scan_html(content.get("body"))

        await self.fetch(session, f"{base}/quizzes")
        await self.fetch(session, f"{base}/enrollments", [("user_id", user_id)])

        # The announcements tool asks per course; store the course's whole history under that request
        far_future = (dt.date.today() + dt.timedelta(days=730)).isoformat()
        status, announcements = await self.fetch(
            session, "announcements",
            [("context_codes[]", f"course_{cid}"), ("start_date", "2000-01-01"), ("end_date", far_future)],
            key=request_key("GET", "announcements", [("context_codes[]", f"course_{cid}")]),
        )
        for announcement in _ok_list(status, announcements):
            self._scan_html(announcement.get("message"))

    async def _download_files(self, session) -> tuple[int, int, dict]:
        downloaded, unavailable = 0, 0
        failed: dict[str, str] = {}
        files_root = self.store.root / "files"

        async def download(file_id: str, meta: dict):
            nonlocal downloaded, unavailable
            url = meta.get("url")
            if not url or meta.get("locked_for_user") or meta.get("hidden_for_user"):
                unavailable += 1
                return
            name = _safe_name(meta.get("display_name") or meta.get("filename"))
            path = files_root / file_id / name
            size = meta.get("size")
            if not (path.is_file() and size is not None and path.stat().st_size == size):
                try:
                    async with self.semaphore:
                        # No auth header: the URL is pre-signed and redirects to file storage on another host
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=600)) as response:
                            if response.status != 200:
                                failed[file_id] = f"HTTP {response.status}"
                                return
                            path.parent.mkdir(parents=True, exist_ok=True)
                            tmp = path.with_suffix(path.suffix + ".part")
                            with open(tmp, "wb") as f:
                                async for chunk in response.content.iter_chunked(1 << 16):
                                    f.write(chunk)
                            tmp.replace(path)
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    failed[file_id] = str(exc)[:200]
                    return
            downloaded += 1
            self.store.files[file_id] = {
                "path": str(path.relative_to(self.store.root)),
                "size": path.stat().st_size,
                "content_type": meta.get("content-type"),
                "display_name": meta.get("display_name"),
            }

        self.log(f"Sandbox sync: downloading {len(self.file_meta)} files (existing complete files are kept)...")
        await asyncio.gather(*(download(fid, meta) for fid, meta in self.file_meta.items()))
        return downloaded, unavailable, failed


async def sync(store: SandboxStore, canvas_url: str, token: str, log: Callable[[str], None] = print) -> dict:
    """Capture Canvas into `store` (replacing earlier responses; downloaded files are reused) and save it."""
    store.root.mkdir(parents=True, exist_ok=True)
    store.responses, store.files, store.manifest = {}, {}, {"complete": False}
    store.save()  # marks the sandbox incomplete until this sync finishes
    manifest = await CanvasCrawler(store, canvas_url, token, log).crawl()
    store.save()
    counts = manifest["counts"]
    log(f"Sandbox sync done in {manifest['duration_s']}s: {counts['responses']} responses, "
        f"{counts['courses']} courses, {counts['files_downloaded']} files downloaded "
        f"({counts['files_unavailable']} locked, {counts['files_failed']} failed), "
        f"{len(manifest['errors'])} endpoints answered with an error.")
    return manifest
