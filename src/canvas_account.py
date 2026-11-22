"""The Canvas account a conversation acts as: which Canvas to call, with whose token, and where its files live.

Every Canvas request, downloaded file and knowledge base (OpenAI vector store) belongs to one account. Passing the
account explicitly, rather than reading CANVAS_URL / CANVAS_ACCESS_TOKEN from the process environment on each
request, is what keeps two students' concurrent conversations from using each other's credentials or data.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ACCOUNT_KEY = "default"
# Metadata key on an OpenAI vector store naming the account that owns it
VECTOR_STORE_OWNER_KEY = "canvas_owner"
# The shared (demo / single-user) account keeps the original layout; other accounts get a folder each
DEFAULT_STORAGE_ROOT = Path("file_index")
STUDENT_STORAGE_ROOT = Path("file_index_students")


@dataclass(frozen=True)
class CanvasAccount:
    key: str  # stable identity of the account owner; scopes files and knowledge bases
    url: str
    token: str = field(repr=False)

    @classmethod
    def from_env(cls) -> "CanvasAccount":
        """The shared account configured by CANVAS_URL / CANVAS_ACCESS_TOKEN.

        Read when a conversation starts, not at import: sandbox mode rewrites both variables at startup.
        """
        url, token = os.getenv("CANVAS_URL"), os.getenv("CANVAS_ACCESS_TOKEN")
        missing = [name for name, value in (("CANVAS_ACCESS_TOKEN", token), ("CANVAS_URL", url)) if not value]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
        return cls(key=DEFAULT_ACCOUNT_KEY, url=url, token=token)

    @property
    def base_url(self) -> str:
        url = (self.url or "https://canvas.instructure.com").rstrip("/")
        if url.startswith("http://") and not url.startswith(("http://127.0.0.1", "http://localhost")):
            url = "https://" + url[len("http://"):]
        if "http" not in url:
            url = "https://" + url
        return url

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v1"

    def headers(self, accept_json: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        headers["Accept" if accept_json else "Content-Type"] = "application/json"
        return headers

    @property
    def storage_root(self) -> Path:
        if self.key == DEFAULT_ACCOUNT_KEY:
            return DEFAULT_STORAGE_ROOT
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", self.key).strip(".") or "_"
        return STUDENT_STORAGE_ROOT / safe

    def owns_vector_store(self, vector_store: Any) -> bool:
        """Stores created before ownership was recorded carry no owner and belong to the shared account."""
        metadata = getattr(vector_store, "metadata", None) or {}
        return metadata.get(VECTOR_STORE_OWNER_KEY, DEFAULT_ACCOUNT_KEY) == self.key

    @property
    def vector_store_metadata(self) -> dict:
        return {VECTOR_STORE_OWNER_KEY: self.key}
