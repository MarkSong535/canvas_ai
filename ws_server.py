"""Minimal WebSocket server that bridges clients to the Canvas agent."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
import ssl
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv
from websockets.server import WebSocketServerProtocol, serve

import file_index_downloader
from configs.canvas_agent_config import agent_config
from src import canvas_sandbox
from src.agent.routing import ConversationRouting, build_router
from src.agent.stream_events import escalate_events, stream_agent_events
from src.utils import latex_svg
from src.models import model_manager
from src.registry import AGENT

load_dotenv()

SendFn = Callable[[Dict[str, Any]], Awaitable[None]]

_AGENT_CACHE = None
WSS_ENABLED = os.getenv("WSS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WSS_CERTFILE = os.getenv("WSS_CERTFILE")
WSS_KEYFILE = os.getenv("WSS_KEYFILE")


def _parse_session_duration(raw: Optional[str]) -> int:
    """Parse session duration from environment variable (in minutes)."""
    if raw is None:
        return 30  # Default: 30 minutes
    try:
        duration = int(raw)
    except (TypeError, ValueError):
        return 30
    return max(duration, 1)  # Minimum 1 minute


SESSION_DURATION_MINUTES = _parse_session_duration(os.getenv("SESSION_DURATION"))

# Track the single active WebSocket connection
ACTIVE_WEBSOCKET: Optional[WebSocketServerProtocol] = None
ACTIVE_WEBSOCKET_LOCK = asyncio.Lock()


async def build_agent() -> Any:
    """Create and cache the Canvas agent instance."""
    global _AGENT_CACHE

    if _AGENT_CACHE is not None:
        return _AGENT_CACHE

    required = ("CANVAS_ACCESS_TOKEN", "CANVAS_URL")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"Missing environment variables: {missing_str}")

    model_manager.init_models()

    try:
        model = model_manager.registed_models[agent_config["model_id"]]
    except KeyError as exc:
        available = ", ".join(model_manager.list_models()) or "None"
        raise RuntimeError(
            f"Model '{agent_config['model_id']}' is not registered. Available: {available}"
        ) from exc

    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=agent_config["tools"],
        max_steps=agent_config["max_steps"],
        stream_outputs=agent_config.get("stream_outputs", False),
        max_history_turns=agent_config.get("max_history_turns"),
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )

    _AGENT_CACHE = AGENT.build(agent_build_config)
    _AGENT_CACHE.router = build_router(agent_config)
    return _AGENT_CACHE


async def handle_agent_query(message: Dict[str, Any], send: SendFn) -> Dict[str, Any]:
    """Process a chat payload through the Canvas agent, streaming progress through `send`.

    Streams `{"type": "route", "tier"}`, `{"type": "tool", "name"}`, `{"type": "delta", "text"}` and
    `{"type": "retract"}` frames while the agent works; the returned `{"type": "answer", ...}` frame is the
    authoritative final reply.
    """
    query = message.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "Payload must include a non-empty 'query' field."}
    agent = await build_agent()
    # reset=False: the agent keeps this connection's earlier exchanges (memory is cleared per connection)
    return await _stream_answer(stream_agent_events(agent, query, reset=False), send)


async def handle_escalation(send: SendFn) -> Dict[str, Any]:
    """The user accepted the offer to retry the last question one tier up."""
    agent = await build_agent()
    return await _stream_answer(escalate_events(agent), send)


async def _stream_answer(events, send: SendFn) -> Dict[str, Any]:
    final: Dict[str, Any] = {"answer": ""}
    async for event in events:
        if event["type"] == "final":
            final = event
        else:
            await send(event)
    answer = final["answer"]
    frame = {"type": "answer", "answer": answer,
             # Math and ```chemfig blocks are rendered to SVG here; the page swaps each snippet for its SVG by key
             "renders": await latex_svg.render_answer(answer)}
    if "tier" in final:
        frame["tier"] = final["tier"]
    # Only the user decides whether a struggling answer is retried with a stronger model ({"type": "escalate"})
    frame["can_escalate"] = bool(final.get("can_escalate"))
    return frame


async def reset_conversation() -> None:
    """Forget earlier exchanges so the next chat message starts a new conversation."""
    agent = await build_agent()
    agent.memory.reset()
    agent.routing_state = ConversationRouting()


async def fetch_course_catalog() -> List[Dict[str, Any]]:
    """Return the list of available Canvas courses."""

    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")

    if not canvas_url or not canvas_token:
        raise RuntimeError("Canvas configuration missing.")

    headers = {
        "Authorization": f"Bearer {canvas_token}",
        "Accept": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        courses = await file_index_downloader.fetch_all_pages(
            session,
            f"{canvas_url}/api/v1/courses",
            headers,
            params={"enrollment_state": "active", "per_page": 100},
            raise_on_error=True,
        )

    return courses


async def handle_download_request(
    message: Dict[str, Any],
    pending_courses: Optional[List[Dict[str, Any]]]
) -> Tuple[Dict[str, Any], Optional[List[Dict[str, Any]]]]:
    """Trigger the file index downloader with automated selections."""

    skip_download = bool(message.get("skip_download", False))
    course_ids_raw = message.get("course_ids")
    course_indices_raw = message.get("course_indices")
    auto_confirm = message.get("auto_confirm", True)

    if course_ids_raw is not None and not isinstance(course_ids_raw, list):
        return {"error": "course_ids must be a list of integers."}, pending_courses

    try:
        course_ids = [int(cid) for cid in course_ids_raw] if course_ids_raw is not None else None
    except (TypeError, ValueError):
        return {"error": "course_ids must contain valid integers."}, pending_courses

    if course_indices_raw is not None and not isinstance(course_indices_raw, list):
        return {"error": "course_indices must be a list of integers."}, pending_courses

    if course_indices_raw is not None:
        if pending_courses is None:
            return {"error": "Course list not initialized. Request the course list first."}, pending_courses
        try:
            indices = [int(idx) for idx in course_indices_raw]
        except (TypeError, ValueError):
            return {"error": "course_indices must contain valid integers."}, pending_courses

        if not indices:
            return {"error": "course_indices cannot be empty."}, pending_courses

        invalid = [idx for idx in indices if idx < 1 or idx > len(pending_courses)]
        if invalid:
            return {"error": f"course_indices out of range: {invalid}"}, pending_courses

        seen = set()
        resolved_course_ids: List[int] = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                resolved_course_ids.append(int(pending_courses[idx - 1]["id"]))

        course_ids = resolved_course_ids

    if not isinstance(auto_confirm, bool):
        return {"error": "auto_confirm must be a boolean."}, pending_courses

    if course_ids_raw is None and course_indices_raw is None and not skip_download:
        try:
            courses = await fetch_course_catalog()
        except Exception as exc:  # noqa: BLE001
            return {"status": "course_list_error", "error": f"Failed to fetch courses: {exc}"}, pending_courses

        course_list = [
            {
                "index": idx,
                "id": course.get("id"),
                "name": course.get("name"),
                "code": course.get("course_code"),
            }
            for idx, course in enumerate(courses, start=1)
        ]

        return {"status": "course_list", "courses": course_list}, courses

    if (course_ids is None or len(course_ids) == 0) and not skip_download:
        return {"error": "Provide course_ids or course_indices after requesting the course list."}, pending_courses

    file_index_downloader.reset_stats()

    if course_ids:
        file_index_downloader.configure_automation(course_ids=course_ids, auto_confirm=auto_confirm)
    else:
        file_index_downloader.configure_automation(course_ids=None, auto_confirm=auto_confirm)

    try:
        await file_index_downloader.main(skip_download=skip_download)
    finally:
        file_index_downloader.clear_automation()

    response = {
        "status": "completed",
        "stats": deepcopy(file_index_downloader.stats),
    }

    return response, None


async def handle_message(
    message: Dict[str, Any],
    pending_courses: Optional[List[Dict[str, Any]]],
    send: SendFn,
) -> Tuple[Dict[str, Any], Optional[List[Dict[str, Any]]]]:
    """Route messages to the appropriate handler based on type."""

    message_type = message.get("type") or "chat"

    if message_type in {"chat", "query"}:
        return await handle_agent_query(message, send), pending_courses

    if message_type == "reset":
        await reset_conversation()
        return {"status": "reset"}, pending_courses

    if message_type == "escalate":
        return await handle_escalation(send), pending_courses

    if message_type == "download":
        return await handle_download_request(message, pending_courses)

    return {"error": f"Unsupported message type: {message_type}"}, pending_courses


async def verify_turnstile_token(token: Any) -> bool:
    """Redeem a single-use challenge token; every validation failure denies access."""
    secret = os.getenv("TURNSTILE_SECRET", "")
    hostnames = {host.strip() for host in os.getenv("TURNSTILE_HOSTNAMES", "").split(",") if host.strip()}
    action = os.getenv("TURNSTILE_ACTION", "canvas_ws")
    if not secret or not hostnames or not isinstance(token, str) or not token.strip() or len(token) > 2048:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret, "response": token},
            ) as response:
                if response.status != 200:
                    return False
                result = await response.json()
        return (
            isinstance(result, dict)
            and result.get("success") is True
            and isinstance(result.get("hostname"), str)
            and result.get("hostname") in hostnames
            and result.get("action") == action
        )
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return False


async def authenticate_websocket(websocket: WebSocketServerProtocol) -> bool:
    """Require verification before acquiring a session or dispatching any request."""
    try:
        raw_message = await asyncio.wait_for(websocket.recv(), timeout=15)
        if len(raw_message) > 4096:
            raise ValueError("Oversized verification message")
        payload = json.loads(raw_message)
        verified = (
            isinstance(payload, dict)
            and payload.get("type") == "verify"
            and await verify_turnstile_token(payload.get("token"))
        )
    except (asyncio.TimeoutError, ValueError, TypeError):
        verified = False
    if not verified:
        await websocket.send(json.dumps({"status": "verification_error", "error": "Verification failed. Please refresh verification and try again."}))
        await websocket.close(1008, "Verification required")
    return verified


async def websocket_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle a single WebSocket connection."""
    global ACTIVE_WEBSOCKET

    if not await authenticate_websocket(websocket):
        return

    pending_courses: Optional[List[Dict[str, Any]]] = None
    session_start_time = time.time()
    session_duration_seconds = SESSION_DURATION_MINUTES * 60

    # Reject new connection if one is already active
    async with ACTIVE_WEBSOCKET_LOCK:
        if ACTIVE_WEBSOCKET is not None and ACTIVE_WEBSOCKET != websocket:
            await websocket.send(json.dumps({"error": "A connection is already active. Only one connection permitted at a time."}))
            return
        ACTIVE_WEBSOCKET = websocket

    async def send(frame: Dict[str, Any]) -> None:
        await websocket.send(json.dumps(frame))

    try:
        # Each connection is its own conversation
        await reset_conversation()
        await websocket.send(json.dumps({"status": "verified"}))
        async for raw_message in websocket:
            # Check if session duration has been exceeded
            elapsed_time = time.time() - session_start_time
            if elapsed_time > session_duration_seconds:
                await websocket.send(json.dumps({
                    "error": f"Session duration limit ({SESSION_DURATION_MINUTES} minutes) exceeded. Connection will be closed."
                }))
                await websocket.close(1000, "Session duration limit exceeded")
                break

            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "Invalid JSON payload."}))
                continue

            try:
                response, pending_courses = await handle_message(payload, pending_courses, send)
            except Exception as exc:
                pending_courses = None
                response = {"error": str(exc)}

            await websocket.send(json.dumps(response))
    finally:
        # Clear active websocket if this was the active connection
        async with ACTIVE_WEBSOCKET_LOCK:
            if ACTIVE_WEBSOCKET == websocket:
                ACTIVE_WEBSOCKET = None


async def run_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Start the WebSocket server."""
    ssl_context: Optional[ssl.SSLContext] = None
    if WSS_ENABLED:
        if not WSS_CERTFILE or not WSS_KEYFILE:
            raise RuntimeError("WSS_ENABLED requires WSS_CERTFILE and WSS_KEYFILE to be set.")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=WSS_CERTFILE, keyfile=WSS_KEYFILE)

    # CANVAS_SANDBOX=yes: capture Canvas first if needed, then answer every Canvas call locally
    await canvas_sandbox.start()

    async with serve(
        websocket_handler,
        host,
        port,
        logger=None,
        ssl=ssl_context,
        origins=["https://markso.ng"],
    ):
        await asyncio.Future()


def main() -> None:
    host = os.getenv("CANVAS_WS_HOST", "0.0.0.0")
    port = int(os.getenv("CANVAS_WS_PORT", "8765"))

    asyncio.run(run_server(host, port))


if __name__ == "__main__":
    main()
