"""Minimal WebSocket server that bridges clients to the Canvas agent."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
import secrets
import ssl
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv
import pyotp
from websockets.server import WebSocketServerProtocol, serve

import file_index_downloader
from configs.canvas_agent_config import agent_config
from src.models import model_manager
from src.registry import AGENT

load_dotenv()

_AGENT_CACHE = None
AUTH_PASSWORD = os.getenv("CANVAS_WS_SECRET", "canvas-agent-password")
TOTP_SECRET_ENV = "CANVAS_WS_TOTP_SECRET"
TOTP_SECRET = os.getenv(TOTP_SECRET_ENV)
TOTP_DISABLED = os.getenv("CANVAS_WS_TOTP_DISABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WSS_ENABLED = os.getenv("WSS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WSS_CERTFILE = os.getenv("WSS_CERTFILE")
WSS_KEYFILE = os.getenv("WSS_KEYFILE")


def _parse_session_ttl(raw: Optional[str]) -> int:
    if raw is None:
        return 3600
    try:
        ttl = int(raw)
    except (TypeError, ValueError):
        return 3600
    return max(ttl, 0)


SESSION_TTL_SECONDS = _parse_session_ttl(os.getenv("CANVAS_WS_SESSION_TTL"))
SESSION_STORE: Dict[str, Dict[str, Any]] = {}
SESSION_LOCK = asyncio.Lock()


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
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )

    _AGENT_CACHE = AGENT.build(agent_build_config)
    return _AGENT_CACHE


async def handle_agent_query(message: Dict[str, Any]) -> Dict[str, Any]:
    """Process a chat payload through the Canvas agent."""
    agent = await build_agent()

    query = message.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "Payload must include a non-empty 'query' field."}

    result = await agent.run(query)
    return {"answer": str(result)}


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
            return {"error": f"Failed to fetch courses: {exc}"}, pending_courses

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
    pending_courses: Optional[List[Dict[str, Any]]]
) -> Tuple[Dict[str, Any], Optional[List[Dict[str, Any]]]]:
    """Route messages to the appropriate handler based on type."""

    message_type = message.get("type") or "chat"

    if message_type in {"chat", "query"}:
        return await handle_agent_query(message), pending_courses

    if message_type == "download":
        return await handle_download_request(message, pending_courses)

    return {"error": f"Unsupported message type: {message_type}"}, pending_courses


def authenticate_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate the incoming authentication payload."""
    password = payload.get("password")
    totp_code = payload.get("totp")

    if not AUTH_PASSWORD:
        return False, "Server password is not configured."

    if password != AUTH_PASSWORD:
        return False, "Invalid password."

    if TOTP_DISABLED:
        return True, None

    if not isinstance(totp_code, str) or not totp_code.strip():
        return False, "Missing TOTP code."

    if not TOTP_SECRET:
        return False, f"Server missing {TOTP_SECRET_ENV}."

    try:
        totp = pyotp.TOTP(TOTP_SECRET)
    except (TypeError, ValueError):
        return False, "Server TOTP secret is invalid."
    if not totp.verify(totp_code, valid_window=1):
        return False, "Invalid or expired TOTP code."

    return True, None


async def prune_sessions(now: Optional[float] = None) -> None:
    """Remove expired sessions from the session store."""
    if SESSION_TTL_SECONDS <= 0:
        return

    current = now or time.time()
    async with SESSION_LOCK:
        expired = [
            key
            for key, session in SESSION_STORE.items()
            if current - session.get("last_seen", current) > SESSION_TTL_SECONDS
        ]
        for key in expired:
            SESSION_STORE.pop(key, None)


async def create_session() -> Tuple[str, Dict[str, Any]]:
    """Create a new reusable session and return its key and data."""
    await prune_sessions()
    session_key = secrets.token_urlsafe(32)
    now = time.time()
    session_data: Dict[str, Any] = {
        "created": now,
        "last_seen": now,
        "pending_courses": None,
    }

    async with SESSION_LOCK:
        SESSION_STORE[session_key] = session_data

    return session_key, session_data


async def get_session(session_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve an existing session if it is still valid."""
    await prune_sessions()
    async with SESSION_LOCK:
        session = SESSION_STORE.get(session_key)
        if session is None:
            return None
        session["last_seen"] = time.time()
        return session


async def update_session(session_key: str, session_data: Dict[str, Any]) -> None:
    """Persist updated session data back into the store."""
    session_data["last_seen"] = time.time()
    async with SESSION_LOCK:
        if session_key in SESSION_STORE:
            SESSION_STORE[session_key] = session_data


async def websocket_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle a single WebSocket connection."""
    authenticated = False
    pending_courses: Optional[List[Dict[str, Any]]] = None
    session_key: Optional[str] = None
    session_data: Optional[Dict[str, Any]] = None

    try:
        async for raw_message in websocket:
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "Invalid JSON payload."}))
                continue

            if not authenticated:
                if payload.get("type") != "auth":
                    await websocket.send(json.dumps({"error": "Authentication required."}))
                    break

                requested_session_key_raw = payload.get("session_key")
                requested_session_key = (
                    requested_session_key_raw.strip()
                    if isinstance(requested_session_key_raw, str)
                    else None
                )

                if requested_session_key:
                    existing_session = await get_session(requested_session_key)
                    if existing_session is None:
                        await websocket.send(json.dumps({"error": "Invalid or expired session_key."}))
                        break

                    authenticated = True
                    session_key = requested_session_key
                    session_data = existing_session
                    pending_courses = session_data.get("pending_courses")
                    response = {"status": "authenticated", "session_key": session_key}
                    if SESSION_TTL_SECONDS > 0:
                        response["expires_in"] = SESSION_TTL_SECONDS
                    await websocket.send(json.dumps(response))
                    continue

                is_valid, error = authenticate_payload(payload)
                if not is_valid:
                    await websocket.send(json.dumps({"error": error}))
                    break

                session_key, session_data = await create_session()
                authenticated = True
                pending_courses = session_data.get("pending_courses")
                response = {"status": "authenticated", "session_key": session_key}
                if SESSION_TTL_SECONDS > 0:
                    response["expires_in"] = SESSION_TTL_SECONDS
                await websocket.send(json.dumps(response))
                continue

            try:
                response, pending_courses = await handle_message(payload, pending_courses)
            except Exception as exc:
                pending_courses = None
                response = {"error": str(exc)}

            await websocket.send(json.dumps(response))

            if session_key and session_data is not None:
                session_data["pending_courses"] = pending_courses
                await update_session(session_key, session_data)
    finally:
        if session_key and session_data is not None:
            session_data["pending_courses"] = pending_courses
            await update_session(session_key, session_data)


async def run_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Start the WebSocket server."""
    ssl_context: Optional[ssl.SSLContext] = None
    if WSS_ENABLED:
        if not WSS_CERTFILE or not WSS_KEYFILE:
            raise RuntimeError("WSS_ENABLED requires WSS_CERTFILE and WSS_KEYFILE to be set.")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=WSS_CERTFILE, keyfile=WSS_KEYFILE)

    async with serve(websocket_handler, host, port, logger=None, ssl=ssl_context):
        await asyncio.Future()


def main() -> None:
    host = os.getenv("CANVAS_WS_HOST", "0.0.0.0")
    port = int(os.getenv("CANVAS_WS_PORT", "8765"))

    asyncio.run(run_server(host, port))


if __name__ == "__main__":
    main()
