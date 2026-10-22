"""
On-disk Canvas sandbox: every captured API response, the downloaded course files, and the writes the agent
made while in sandbox mode (recorded here, never sent to Canvas).

Layout under the sandbox directory:
    manifest.json     when it was captured, from which host, counts and per-endpoint errors
    responses.json    {request key: {"status": int, "body": <JSON>}}
    files.json        {file id: {"path": <relative path>, "size", "content_type", "display_name"}}
    files/<id>/<name> the downloaded file contents
    writes.jsonl      one line per write (submission, discussion post, ...) made in sandbox mode
    requests.jsonl    one line per API request served in sandbox mode, and how it was answered
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

# Query parameters that never change which data a request returns from the sandbox:
# paging (the sandbox stores complete lists) and include[] (everything is captured with every include).
IGNORED_PARAMS = {"per_page", "page", "include[]", "access_token"}


def request_key(method: str, path: str, params: Iterable[tuple[str, Any]] = ()) -> str:
    """Canonical key for a Canvas API request, e.g. 'GET courses/12/files?search_term=lab'."""
    path = path.strip("/")
    if path.startswith("api/v1/"):
        path = path[len("api/v1/"):]
    kept = sorted((str(k), str(v)) for k, v in params if k not in IGNORED_PARAMS)
    query = "&".join(f"{k}={v}" for k, v in kept)
    return f"{method.upper()} {path}" + (f"?{query}" if query else "")


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


class SandboxStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.responses: dict[str, dict] = {}
        self.files: dict[str, dict] = {}
        self.manifest: dict = {}

    # --- lifecycle ---

    def is_complete(self) -> bool:
        """True once a sync has finished writing this sandbox."""
        try:
            return json.loads((self.root / "manifest.json").read_text(encoding="utf-8")).get("complete") is True
        except (OSError, ValueError):
            return False

    def load(self) -> "SandboxStore":
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.responses = json.loads((self.root / "responses.json").read_text(encoding="utf-8"))
        files_path = self.root / "files.json"
        self.files = json.loads(files_path.read_text(encoding="utf-8")) if files_path.exists() else {}
        return self

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.root / "responses.json", self.responses)
        _atomic_write_json(self.root / "files.json", self.files)
        _atomic_write_json(self.root / "manifest.json", self.manifest)

    # --- responses ---

    def put(self, key: str, status: int, body: Any) -> None:
        self.responses[key] = {"status": status, "body": body}

    def get(self, key: str) -> dict | None:
        return self.responses.get(key)

    def body(self, key: str) -> Any:
        """The stored body of a successful response, else None."""
        entry = self.responses.get(key)
        return entry["body"] if entry and entry["status"] == 200 else None

    # --- files ---

    def file_path(self, file_id: str) -> Path | None:
        entry = self.files.get(str(file_id))
        if not entry:
            return None
        path = self.root / entry["path"]
        return path if path.is_file() else None

    # --- logs ---

    def _append(self, name: str, entry: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / name, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), **entry}, ensure_ascii=False) + "\n")

    def log_request(self, entry: dict) -> None:
        self._append("requests.jsonl", entry)

    def record_write(self, entry: dict) -> None:
        self._append("writes.jsonl", entry)
