"""Minimal WebSocket server that bridges clients to the Canvas agent."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from websockets.server import WebSocketServerProtocol, serve

from configs.canvas_agent_config import agent_config
from src.models import model_manager
from src.registry import AGENT

load_dotenv()

_AGENT_CACHE = None


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


async def handle_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Process a client payload and return the agent response."""
    agent = await build_agent()

    query = message.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "Payload must include a non-empty 'query' field."}

    result = await agent.run(query)
    return {"answer": str(result)}


async def websocket_handler(websocket: WebSocketServerProtocol) -> None:
    """Handle a single WebSocket connection."""
    async for raw_message in websocket:
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"error": "Invalid JSON payload."}))
            continue

        try:
            response = await handle_message(payload)
        except Exception as exc:
            response = {"error": str(exc)}

        await websocket.send(json.dumps(response))


async def run_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Start the WebSocket server."""
    async with serve(websocket_handler, host, port, logger=None):
        await asyncio.Future()


def main() -> None:
    host = os.getenv("CANVAS_WS_HOST", "0.0.0.0")
    port = int(os.getenv("CANVAS_WS_PORT", "8765"))

    asyncio.run(run_server(host, port))


if __name__ == "__main__":
    main()
