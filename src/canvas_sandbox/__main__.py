"""
python -m src.canvas_sandbox sync     capture everything from Canvas now (refreshes an existing sandbox)
python -m src.canvas_sandbox status   show what the sandbox holds
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from src.canvas_sandbox import sandbox_dir  # noqa: E402
from src.canvas_sandbox.store import SandboxStore  # noqa: E402
from src.canvas_sandbox.sync import sync  # noqa: E402


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    store = SandboxStore(sandbox_dir())
    if command == "sync":
        # The capture step: the only one that uses the real Canvas URL and access token
        url, token = os.environ.get("CANVAS_URL"), os.environ.get("CANVAS_ACCESS_TOKEN")
        if not url or not token:
            print("CANVAS_URL and CANVAS_ACCESS_TOKEN must be set to the real Canvas values.")
            return 1
        asyncio.run(sync(store, url, token))
        return 0
    if command == "status":
        if not store.is_complete():
            print(f"No complete sandbox at {store.root}. Run: python -m src.canvas_sandbox sync")
            return 1
        store.load()
        writes = store.root / "writes.jsonl"
        requests = store.root / "requests.jsonl"
        print(json.dumps({
            "dir": str(store.root),
            "captured": store.manifest.get("created"),
            "source": store.manifest.get("source"),
            "counts": store.manifest.get("counts"),
            "endpoints_with_errors": len(store.manifest.get("errors", {})),
            "writes_recorded": sum(1 for _ in open(writes)) if writes.exists() else 0,
            "requests_served": sum(1 for _ in open(requests)) if requests.exists() else 0,
        }, indent=2))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
