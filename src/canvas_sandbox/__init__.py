"""
Canvas sandbox mode (CANVAS_SANDBOX=yes in .env).

On start, if no complete sandbox exists yet (or CANVAS_SANDBOX_REFRESH=yes), everything the Canvas tools could
ask for is fetched from Canvas with the access token and every file is downloaded (see sync.py). Then a local
Canvas look-alike server starts on 127.0.0.1 and CANVAS_URL is pointed at it, so every tool call, file download
and course listing is answered locally, and every write (assignment submission, discussion reply, ...) is
recorded in the sandbox instead of reaching Canvas.

Credentials: the capture is the ONLY step that uses the real CANVAS_URL and CANVAS_ACCESS_TOKEN. Once the sandbox
starts, both are replaced in this process by the local server's URL and a simulated token that only the local
server accepts, so nothing after the capture holds the real ones. A process that serves an already-captured
sandbox doesn't need the real credentials at all (on oci, the production container doesn't get them).

Settings:
    CANVAS_SANDBOX=yes|no            turn sandbox mode on
    CANVAS_SANDBOX_DIR=<path>        where the sandbox lives (default: workdir/canvas_sandbox)
    CANVAS_SANDBOX_REFRESH=yes|no    re-fetch everything from Canvas on the next start
    CANVAS_SANDBOX_PUBLIC_URL=<url>  public base URL file links should use (e.g. https://canvas.marksong.tech);
                                     its /files/ path must reach the files-only server below
    CANVAS_SANDBOX_FILES_HOST/PORT   where the files-only server listens (default 127.0.0.1:8766)
    CANVAS_SANDBOX_LINK_TTL_HOURS    how long a file link stays valid (default 168 = 7 days)
    CANVAS_SANDBOX_LINK_SECRET       key that signs file links (default: a random key kept in the sandbox dir)

Manual commands: `python -m src.canvas_sandbox sync` (capture/refresh now) and `... status`.
"""

import os
import secrets
from pathlib import Path
from typing import Callable

from src.utils import assemble_project_path

_TRUE = {"1", "true", "yes", "on"}
_server = None


def enabled() -> bool:
    return os.getenv("CANVAS_SANDBOX", "no").strip().lower() in _TRUE


def sandbox_dir() -> Path:
    return Path(os.getenv("CANVAS_SANDBOX_DIR") or assemble_project_path("workdir/canvas_sandbox"))


def active_url() -> str | None:
    """URL of the local sandbox server while it runs in this process, else None."""
    return _server.base_url if _server is not None else None


def local_file_path(file_id) -> Path | None:
    """The downloaded copy of a file in the running sandbox, or None."""
    return _server.store.file_path(str(file_id)) if _server is not None else None


def _link_secret(root: Path) -> bytes:
    """Key that signs file links: CANVAS_SANDBOX_LINK_SECRET, else a random key kept in the sandbox (not the token)."""
    if os.getenv("CANVAS_SANDBOX_LINK_SECRET"):
        return os.environ["CANVAS_SANDBOX_LINK_SECRET"].encode()
    path = root / "link_secret"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip().encode()


async def start(log: Callable[[str], None] = print) -> str | None:
    """In sandbox mode: capture Canvas first if needed, start the local server, then switch this process to
    simulated credentials (local URL + a token only the local server accepts).

    Returns the local server URL, or None when sandbox mode is off. Safe to call more than once.
    """
    global _server
    if not enabled():
        return None
    if _server is not None:
        return _server.base_url

    from src.canvas_sandbox.server import FileLinks, SandboxServer
    from src.canvas_sandbox.store import SandboxStore
    from src.canvas_sandbox.sync import sync

    store = SandboxStore(sandbox_dir())
    if os.getenv("CANVAS_SANDBOX_REFRESH", "no").strip().lower() in _TRUE or not store.is_complete():
        # The capture is the only step that uses the real Canvas URL and access token
        real_url, real_token = os.environ.get("CANVAS_URL"), os.environ.get("CANVAS_ACCESS_TOKEN")
        if not real_url or not real_token or real_token.startswith("sandbox-"):
            raise RuntimeError("No complete Canvas sandbox yet: capture it first with the real CANVAS_URL and "
                               "CANVAS_ACCESS_TOKEN (python -m src.canvas_sandbox sync).")
        log(f"Canvas sandbox: capturing everything from {real_url} into {store.root} (this can take a while)...")
        await sync(store, real_url, real_token, log=log)
        del real_url, real_token
    store.load()

    simulated_token = "sandbox-" + secrets.token_hex(16)
    _server = SandboxServer(store, simulated_token)
    url = await _server.start()

    public_url = os.getenv("CANVAS_SANDBOX_PUBLIC_URL", "").strip()
    ttl_hours = float(os.getenv("CANVAS_SANDBOX_LINK_TTL_HOURS", "168"))
    # Downloads are always signed links: on the public URL if set, else on the local server itself
    _server.file_links = FileLinks(public_url or url, _link_secret(store.root), int(ttl_hours * 3600))
    if public_url:
        files_host = os.getenv("CANVAS_SANDBOX_FILES_HOST", "127.0.0.1")
        files_port = await _server.start_public_files(files_host, int(os.getenv("CANVAS_SANDBOX_FILES_PORT", "8766")))
        log(f"Canvas sandbox: file links point at {public_url}/files/... (served on {files_host}:{files_port})")

    # From here on nothing in this process holds the real Canvas URL or token
    os.environ["CANVAS_URL"] = url
    os.environ["CANVAS_ACCESS_TOKEN"] = simulated_token
    log(f"Canvas sandbox: serving {len(store.responses)} captured responses and {len(store.files)} files "
        f"(captured {store.manifest.get('created', '?')}) at {url} with simulated credentials. "
        "Writes are recorded locally, never sent to Canvas.")
    return url
