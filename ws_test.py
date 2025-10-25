"""Simple WebSocket client for the Canvas agent server with auth handshake."""

import json
import os
import sys
from typing import List, Optional

import pyotp
from dotenv import load_dotenv
from websockets.sync.client import connect


def _prepare_auth_payload(password: str, totp_secret: str) -> dict:
    totp = pyotp.TOTP(totp_secret)
    return {
        "type": "auth",
        "password": password,
        "totp": totp.now(),
    }


def _send_authentication(websocket, auth_payload: dict) -> None:
    websocket.send(json.dumps(auth_payload))
    print(f"Sent auth: {auth_payload}")

    auth_response = websocket.recv()
    print(f"Received: {auth_response}")


def send_canvas_query(websocket) -> None:
    message = {"type": "chat", "query": "List my Canvas courses"}
    websocket.send(json.dumps(message))
    print(f"Sent: {message}")

    response = websocket.recv()
    print(f"Received: {response}")


def _parse_int_list(raw: Optional[str]) -> Optional[List[int]]:
    if not raw:
        return None
    values: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    return values or None


def _print_course_list(courses: List[dict]) -> None:
    if not courses:
        print("No courses returned.")
        return

    print("Available courses:")
    for course in courses:
        index = course.get("index")
        course_id = course.get("id")
        name = course.get("name") or "Unnamed course"
        code = course.get("code") or ""
        display = f"{index}. {name} (ID: {course_id})"
        if code:
            display += f" [{code}]"
        print(f"  {display}")


def send_download_request(websocket) -> None:
    course_ids = _parse_int_list(os.getenv("CANVAS_WS_TEST_COURSE_IDS"))
    course_indices = _parse_int_list(os.getenv("CANVAS_WS_TEST_COURSE_INDICES"))
    skip_download = os.getenv("CANVAS_WS_TEST_SKIP", "false").lower() == "true"

    initial_payload = {"type": "download"}

    websocket.send(json.dumps(initial_payload))
    print(f"Sent: {initial_payload}")

    course_list_raw = websocket.recv()
    print(f"Received: {course_list_raw}")

    try:
        course_list_response = json.loads(course_list_raw)
    except json.JSONDecodeError:
        print("Server returned non-JSON response; aborting.")
        return

    if course_list_response.get("status") != "course_list":
        print("Unexpected response; expected a course list.")
        return

    courses = course_list_response.get("courses", [])
    _print_course_list(courses)

    if course_ids is None and course_indices is None and not skip_download:
        print("Set CANVAS_WS_TEST_COURSE_IDS or CANVAS_WS_TEST_COURSE_INDICES to choose courses.")
        return

    selection_payload = {
        "type": "download",
        "skip_download": skip_download,
        "auto_confirm": True,
    }

    if course_ids is not None:
        selection_payload["course_ids"] = course_ids

    if course_indices is not None:
        selection_payload["course_indices"] = course_indices

    websocket.send(json.dumps(selection_payload))
    print(f"Sent: {selection_payload}")

    final_response = websocket.recv()
    print(f"Received: {final_response}")


if __name__ == "__main__":
    load_dotenv()

    uri = os.getenv("CANVAS_WS_URI", "ws://localhost:8765")
    password = os.getenv("CANVAS_WS_SECRET", "canvas-agent-password")
    totp_secret = os.getenv("CANVAS_WS_TOTP_SECRET")

    if not totp_secret:
        raise RuntimeError("CANVAS_WS_TOTP_SECRET is required for authentication.")

    mode = "download" if len(sys.argv) > 1 and sys.argv[1].lower() == "download" else "chat"

    with connect(uri) as websocket:
        _send_authentication(websocket, _prepare_auth_payload(password, totp_secret))

        if mode == "download":
            send_download_request(websocket)
        else:
            send_canvas_query(websocket)
