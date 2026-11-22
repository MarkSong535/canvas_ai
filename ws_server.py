"""Minimal WebSocket server that bridges clients to the Canvas agent."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
import json
import os
import ssl
import time
import weakref
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv
from websockets.server import WebSocketServerProtocol, serve

import file_index_downloader
from configs.canvas_agent_config import agent_config, build_tools
from src import canvas_sandbox
from src.canvas_account import CanvasAccount
from src.agent.routing import ConversationRouting, build_router
from src.agent.stream_events import escalate_events, stream_agent_events
from src.utils import latex_svg
from src.models import model_manager
from src.registry import AGENT

load_dotenv()

SendFn = Callable[[Dict[str, Any]], Awaitable[None]]

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


def _parse_max_conversations(raw: Optional[str]) -> int:
    """How many conversations may be open at once (MAX_CONVERSATIONS, default 20, minimum 1)."""
    try:
        return max(int(raw), 1) if raw is not None else 20
    except (TypeError, ValueError):
        return 20


MAX_CONVERSATIONS = _parse_max_conversations(os.getenv("MAX_CONVERSATIONS"))
_open_conversations = 0


def _parse_max_concurrent_requests(raw: Optional[str]) -> Optional[int]:
    """How many requests (across all conversations) may run at once (MAX_CONCURRENT_REQUESTS).

    Unset, empty or invalid means no limit beyond MAX_CONVERSATIONS. Requests over the limit wait their turn
    rather than being refused.
    """
    try:
        return max(int(raw), 1) if raw and raw.strip() else None
    except ValueError:
        return None


MAX_CONCURRENT_REQUESTS = _parse_max_concurrent_requests(os.getenv("MAX_CONCURRENT_REQUESTS"))
_request_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


async def _run_request(work: Awaitable[Dict[str, Any]]) -> Dict[str, Any]:
    """Run one request once a slot is free (immediately when MAX_CONCURRENT_REQUESTS is unset)."""
    if MAX_CONCURRENT_REQUESTS is None:
        return await work
    slots = _request_slots.get(asyncio.get_running_loop())
    if slots is None:
        slots = _request_slots[asyncio.get_running_loop()] = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    async with slots:
        return await work


@dataclass
class Conversation:
    """Everything one chat owns. Lives exactly as long as its WebSocket connection; nothing else references it."""

    account: CanvasAccount
    agent: Any  # its own agent: memory, routing state and last question for retries, tools bound to `account`
    pending_courses: Optional[List[Dict[str, Any]]] = None  # course list offered for the next download selection


_models_ready = False


def _configured_model() -> Any:
    """Register the models once per process; every conversation's agent shares these stateless clients."""
    global _models_ready
    if not _models_ready:
        model_manager.init_models()
        _models_ready = True
    try:
        return model_manager.registed_models[agent_config["model_id"]]
    except KeyError as exc:
        available = ", ".join(model_manager.list_models()) or "None"
        raise RuntimeError(
            f"Model '{agent_config['model_id']}' is not registered. Available: {available}"
        ) from exc


def build_agent(account: CanvasAccount) -> Any:
    """A fresh Canvas agent whose tools call Canvas as `account`."""
    agent = AGENT.build(dict(
        type=agent_config["type"],
        config=agent_config,
        model=_configured_model(),
        tools=build_tools(account),
        max_steps=agent_config["max_steps"],
        stream_outputs=agent_config.get("stream_outputs", False),
        max_history_turns=agent_config.get("max_history_turns"),
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    ))
    agent.router = build_router(agent_config)
    return agent


async def resolve_account(verification: Dict[str, Any]) -> CanvasAccount:
    """The Canvas account a verified connection acts as.

    Turnstile proves a human is present but carries no student identity, so every connection uses the shared
    account from the environment. Real per-student sign-in replaces this: identify the student from
    `verification` (the connection's first message) and return their own authorized account.
    """
    return CanvasAccount.from_env()


# Seams the server uses to admit a connection; tests replace them with fakes
AGENT_FACTORY: Callable[[CanvasAccount], Any] = build_agent
ACCOUNT_RESOLVER: Callable[[Dict[str, Any]], Awaitable[CanvasAccount]] = resolve_account


async def start_conversation(verification: Dict[str, Any]) -> Conversation:
    account = await ACCOUNT_RESOLVER(verification)
    return Conversation(account=account, agent=AGENT_FACTORY(account))


async def handle_agent_query(conversation: Conversation, message: Dict[str, Any], send: SendFn) -> Dict[str, Any]:
    """Process a chat payload through the conversation's agent, streaming progress through `send`.

    Streams `{"type": "route", "tier"}`, `{"type": "tool", "name"}`, `{"type": "delta", "text"}` and
    `{"type": "retract"}` frames while the agent works; the returned `{"type": "answer", ...}` frame is the
    authoritative final reply.
    """
    query = message.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "Payload must include a non-empty 'query' field."}
    # reset=False: the agent keeps this conversation's earlier exchanges
    return await _stream_answer(stream_agent_events(conversation.agent, query, reset=False), send)


async def handle_escalation(conversation: Conversation, send: SendFn) -> Dict[str, Any]:
    """The user accepted the offer to retry this conversation's last question one tier up."""
    return await _stream_answer(escalate_events(conversation.agent), send)


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


def reset_conversation(conversation: Conversation) -> None:
    """Forget this conversation's earlier exchanges so its next chat message starts afresh."""
    conversation.agent.memory.reset()
    conversation.agent.routing_state = ConversationRouting()


async def fetch_course_catalog(account: CanvasAccount) -> List[Dict[str, Any]]:
    """Return the account's active Canvas courses."""

    if not account.url or not account.token:
        raise RuntimeError("Canvas configuration missing.")

    async with aiohttp.ClientSession() as session:
        courses = await file_index_downloader.fetch_all_pages(
            session,
            f"{account.api_url}/courses",
            account.headers(accept_json=True),
            params={"enrollment_state": "active", "per_page": 100},
            raise_on_error=True,
        )

    return courses


async def handle_download_request(conversation: Conversation, message: Dict[str, Any]) -> Dict[str, Any]:
    """Run a download job for the conversation's account (the course list it offered is kept per conversation)."""
    response, conversation.pending_courses = await _download(conversation.account, message,
                                                             conversation.pending_courses)
    return response


async def _download(
    account: CanvasAccount,
    message: Dict[str, Any],
    pending_courses: Optional[List[Dict[str, Any]]]
) -> Tuple[Dict[str, Any], Optional[List[Dict[str, Any]]]]:

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
            courses = await fetch_course_catalog(account)
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

    # The job carries its own selections, counters and output folder, so overlapping downloads stay separate
    job = file_index_downloader.DownloadJob.automated(account, course_ids or None, auto_confirm)
    await file_index_downloader.main(skip_download=skip_download, job=job)

    response = {
        "status": "completed",
        "stats": deepcopy(job.stats),
    }

    return response, None


async def handle_message(conversation: Conversation, message: Dict[str, Any], send: SendFn) -> Dict[str, Any]:
    """Route a message to the handler for its type; every handler acts only on `conversation`."""

    message_type = message.get("type") or "chat"

    if message_type in {"chat", "query"}:
        return await handle_agent_query(conversation, message, send)

    if message_type == "reset":
        reset_conversation(conversation)
        return {"status": "reset"}

    if message_type == "escalate":
        return await handle_escalation(conversation, send)

    if message_type == "download":
        return await handle_download_request(conversation, message)

    return {"error": f"Unsupported message type: {message_type}"}


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


async def authenticate_websocket(websocket: WebSocketServerProtocol) -> Optional[Dict[str, Any]]:
    """Require verification before starting a conversation; returns the verification message, or None."""
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
        return None
    return payload


async def websocket_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle one WebSocket connection: one conversation, its messages processed strictly in order."""
    global _open_conversations

    verification = await authenticate_websocket(websocket)
    if verification is None:
        return

    # Admission: no awaits between the check and the increment, so the count can't be overshot
    if _open_conversations >= MAX_CONVERSATIONS:
        await websocket.send(json.dumps({"error": "Server is at capacity. Please try again shortly."}))
        await websocket.close(1013, "Server at capacity")
        return
    _open_conversations += 1

    closed = asyncio.ensure_future(websocket.wait_closed())
    try:
        try:
            conversation = await start_conversation(verification)
        except Exception as exc:  # noqa: BLE001 - e.g. missing Canvas or model configuration
            await websocket.send(json.dumps({"error": str(exc)}))
            await websocket.close(1011, "Agent unavailable")
            return

        async def send(frame: Dict[str, Any]) -> None:
            await websocket.send(json.dumps(frame))

        session_start_time = time.time()
        session_duration_seconds = SESSION_DURATION_MINUTES * 60
        await send({"status": "verified"})
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

            # One message at a time: the next isn't read until this one is answered. If the client leaves
            # mid-answer, the work it owns (agent run, download job) is cancelled rather than left running.
            work = asyncio.ensure_future(_run_request(handle_message(conversation, payload, send)))
            await asyncio.wait({work, closed}, return_when=asyncio.FIRST_COMPLETED)
            if not work.done():
                work.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await work
                break
            try:
                response = work.result()
            except Exception as exc:
                conversation.pending_courses = None
                response = {"error": str(exc)}

            await websocket.send(json.dumps(response))
    finally:
        closed.cancel()
        _open_conversations -= 1


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
