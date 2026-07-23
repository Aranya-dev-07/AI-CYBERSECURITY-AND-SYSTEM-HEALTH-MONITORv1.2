"""
websocket.py

Real-Time WebSocket Broadcast Service — Lavender Trinetra Platform
=====================================================================

Streams live backend updates (monitoring metrics, top processes,
alerts, AI results, and cybersecurity cycle results) to the React
dashboard over a single WebSocket endpoint, mounted directly on the
existing FastAPI application (backend/api/api.py's `app`) so it shares
the same host/port the REST API already serves on - matching what
frontend/src/services/websocket.js actually connects to
(`ws://<host>:<port><WS_PATH>`).

This module implements no monitoring, AI, or cybersecurity logic of
its own. It is purely a transport layer: main.py's monitoring loop
calls broadcast(payload) once per cycle with data every other
subsystem already produced; this module's only job is to safely
serialize, fan that payload out across per-channel messages matching
services/websocket.js's CHANNELS contract, deliver it to every
connected client, and keep the client registry alive/clean via a
periodic heartbeat.

Public module-level interface (called by backend/main.py exactly as
listed in main.py's `_load_websocket_service()` / start/stop
lifecycle):

    start(host, port, path)   - ready the WebSocket route and heartbeat
    stop()                    - stop broadcasting and close connections
    broadcast(payload)        - fan a cycle's combined payload out to clients

Integrates with:
    - backend/config.py            (settings.websocket: WS_HOST, WS_PORT,
                                      WS_PATH, WS_HEARTBEAT_INTERVAL_SECONDS)
    - backend/core.py               (get_logger, safe_execute)
    - backend/api/api.py            (the shared FastAPI `app` this module
                                      mounts its WebSocket route onto)
    - backend/main.py               (Orchestrator.start_websocket_service /
                                      stop_websocket_service / _broadcast_cycle_update)
    - frontend/src/services/websocket.js (CHANNELS-based subscriber model)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, date
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.core import get_logger, safe_execute
from backend.api.api import app as fastapi_app

logger = get_logger("lavender_trinetra.api.websocket")


# =====================================================================
# CONFIGURATION
# =====================================================================

WS_HOST = settings.websocket.WS_HOST
WS_PORT = settings.websocket.WS_PORT
WS_PATH = settings.websocket.WS_PATH
WS_HEARTBEAT_INTERVAL_SECONDS = settings.websocket.WS_HEARTBEAT_INTERVAL_SECONDS

# Channel names mirrored exactly from frontend/src/services/websocket.js's
# CHANNELS enum, so subscribers there receive messages under the names
# they already expect without any frontend changes.
CHANNEL_METRICS = "metrics"
CHANNEL_PROCESSES = "processes"
CHANNEL_HEALTH_SCORE = "health_score"
CHANNEL_ANOMALIES = "anomalies"
CHANNEL_ROOT_CAUSE = "root_cause"
CHANNEL_TRENDS = "trends"
CHANNEL_PREDICTIONS = "predictions"
CHANNEL_CYBERSECURITY = "cybersecurity"
CHANNEL_SYSTEM_STATUS = "system_status"
CHANNEL_DASHBOARD = "dashboard"
CHANNEL_HEARTBEAT = "heartbeat"


# =====================================================================
# MODULE STATE
# =====================================================================
# All mutable state here is guarded by _state_lock. Client connect/
# disconnect and heartbeat delivery run inside the FastAPI app's own
# asyncio event loop (the api-server thread started by main.py); the
# monitoring loop calls broadcast() from a *different* OS thread with
# no event loop of its own, so every send to a client is handed off to
# the captured loop via asyncio.run_coroutine_threadsafe() rather than
# awaited directly - this is what makes broadcast() non-blocking and
# thread-safe from the monitoring loop's point of view.
# ---------------------------------------------------------------------
_state_lock = threading.Lock()
_clients: set[WebSocket] = set()
_loop: Optional[asyncio.AbstractEventLoop] = None
_heartbeat_task: Optional[asyncio.Task] = None
_route_registered = False
_active = False


# =====================================================================
# JSON-SAFE SERIALIZATION
# =====================================================================

def _json_safe(value: Any) -> Any:
    """
    Recursively coerces datetime/date and NumPy/pandas scalar types
    into native Python types the stdlib json encoder (used internally
    by Starlette's WebSocket.send_json) can serialize, mirroring the
    same sanitizer database/crud.py applies at the PostgreSQL boundary.
    Monitoring/AI/cybersecurity payloads routinely contain numpy
    scalars (e.g. numpy.bool_, numpy.floating) and datetime objects
    that json.dumps() cannot handle directly.
    """
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a required dependency
        np = None

    if np is not None:
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return [_json_safe(item) for item in value.tolist()]

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if hasattr(value, "isoformat") and not isinstance(value, str):
        # Covers pandas.Timestamp and similar datetime-like objects.
        return value.isoformat()

    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    return value


def _envelope(channel: str, payload: Any, timestamp: Optional[str] = None) -> dict[str, Any]:
    """Builds one { channel, payload, timestamp } message, matching the
    shape frontend/src/services/websocket.js's _handleMessage() parses."""
    return {
        "channel": channel,
        "payload": _json_safe(payload),
        "timestamp": timestamp or datetime.utcnow().isoformat(),
    }


# =====================================================================
# CLIENT REGISTRY
# =====================================================================

def _add_client(websocket: WebSocket) -> None:
    with _state_lock:
        _clients.add(websocket)
    logger.info("WebSocket client connected (%d total).", _client_count())


def _remove_client(websocket: WebSocket) -> None:
    with _state_lock:
        _clients.discard(websocket)
    logger.info("WebSocket client disconnected (%d remaining).", _client_count())


def _client_count() -> int:
    with _state_lock:
        return len(_clients)


def _snapshot_clients() -> list[WebSocket]:
    with _state_lock:
        return list(_clients)


# =====================================================================
# WEBSOCKET ENDPOINT
# =====================================================================

async def _endpoint(websocket: WebSocket) -> None:
    """
    The single WebSocket endpoint mounted at WS_PATH. Accepts the
    connection, registers the client, captures the running event loop
    and starts the heartbeat task on first use, then simply keeps the
    connection open (reading and discarding any inbound frames) until
    the client disconnects or an error occurs. All outbound data is
    delivered exclusively via broadcast()/the heartbeat loop, not from
    this receive loop.
    """
    global _loop, _heartbeat_task

    try:
        await websocket.accept()
    except Exception:
        logger.exception("Failed to accept incoming WebSocket connection.")
        return

    with _state_lock:
        if _loop is None:
            _loop = asyncio.get_running_loop()
        if _heartbeat_task is None or _heartbeat_task.done():
            _heartbeat_task = _loop.create_task(_heartbeat_loop())

    _add_client(websocket)

    try:
        while True:
            # No inbound protocol is required from the dashboard; this
            # simply blocks until the client sends something or closes
            # the connection, which is how we detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket connection terminated unexpectedly.")
    finally:
        _remove_client(websocket)


def _register_route(path: str) -> None:
    """Mounts the WebSocket route on the shared FastAPI app exactly
    once, regardless of how many start()/stop() cycles occur."""
    global _route_registered
    if _route_registered:
        return
    with safe_execute("websocket.register_route", reraise=True):
        fastapi_app.add_api_websocket_route(path, _endpoint)
    _route_registered = True
    logger.info("WebSocket route registered at %s", path)


# =====================================================================
# HEARTBEAT
# =====================================================================

async def _heartbeat_loop() -> None:
    """
    Runs on the FastAPI event loop for the lifetime of the process
    (started lazily on first client connection). Periodically pings
    every connected client at WS_HEARTBEAT_INTERVAL_SECONDS; any client
    whose send fails is treated as disconnected and removed from the
    registry immediately, without waiting for its own receive loop to
    notice.
    """
    logger.info("WebSocket heartbeat loop started (interval=%.1fs).", WS_HEARTBEAT_INTERVAL_SECONDS)
    try:
        while True:
            await asyncio.sleep(WS_HEARTBEAT_INTERVAL_SECONDS)
            await _send_to_all(_envelope(CHANNEL_HEARTBEAT, {"alive": True, "clients": _client_count()}))
    except asyncio.CancelledError:
        logger.info("WebSocket heartbeat loop cancelled.")
        raise
    except Exception:
        logger.exception("WebSocket heartbeat loop terminated unexpectedly.")


# =====================================================================
# DELIVERY
# =====================================================================

async def _send_to_all(message: dict[str, Any]) -> None:
    """Delivers one already-built message to every connected client,
    pruning any client whose send fails (treated as disconnected)."""
    clients = _snapshot_clients()
    if not clients:
        return

    dead_clients: list[WebSocket] = []
    for client in clients:
        try:
            await client.send_json(message)
        except Exception:
            dead_clients.append(client)

    if dead_clients:
        with _state_lock:
            for client in dead_clients:
                _clients.discard(client)
        logger.info("Pruned %d dead WebSocket client(s) during broadcast.", len(dead_clients))


async def _broadcast_messages(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        with safe_execute(f"websocket.send:{message.get('channel')}"):
            await _send_to_all(message)


async def _close_all_clients() -> None:
    clients = _snapshot_clients()
    for client in clients:
        with safe_execute("websocket.close_client"):
            await client.close(code=1001)
    with _state_lock:
        _clients.clear()


# =====================================================================
# PAYLOAD FAN-OUT
# =====================================================================
# Turns one main.py monitoring-cycle payload
# ({ timestamp, metrics, processes, alerts, ai_result, cybersecurity })
# into the set of per-channel messages
# frontend/src/services/websocket.js's CHANNELS enum expects, plus a
# combined "dashboard" message and a lightweight "system_status"
# message for aggregate consumers (SystemStatusContext.jsx,
# Dashboard.jsx). Performs no aggregation/interpretation of the data
# itself - purely reshapes an already-computed payload for delivery.
# ---------------------------------------------------------------------

_AI_RESULT_CHANNEL_MAP = {
    "health_score": CHANNEL_HEALTH_SCORE,
    "anomalies": CHANNEL_ANOMALIES,
    "root_causes": CHANNEL_ROOT_CAUSE,
    "trends": CHANNEL_TRENDS,
    "predictions": CHANNEL_PREDICTIONS,
}


def _build_channel_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    timestamp = payload.get("timestamp") or datetime.utcnow().isoformat()
    messages: list[dict[str, Any]] = []

    if "metrics" in payload:
        messages.append(_envelope(CHANNEL_METRICS, payload.get("metrics"), timestamp))

    if "processes" in payload:
        messages.append(_envelope(CHANNEL_PROCESSES, payload.get("processes"), timestamp))

    if "cybersecurity" in payload:
        messages.append(_envelope(CHANNEL_CYBERSECURITY, payload.get("cybersecurity"), timestamp))

    ai_result = payload.get("ai_result") or {}
    if isinstance(ai_result, dict):
        for result_key, channel in _AI_RESULT_CHANNEL_MAP.items():
            if result_key in ai_result:
                messages.append(_envelope(channel, ai_result.get(result_key), timestamp))

    messages.append(
        _envelope(
            CHANNEL_SYSTEM_STATUS,
            {"timestamp": timestamp, "alerts": payload.get("alerts", [])},
            timestamp,
        )
    )

    messages.append(_envelope(CHANNEL_DASHBOARD, payload, timestamp))

    return messages


# =====================================================================
# PUBLIC MODULE-LEVEL INTERFACE (called by backend/main.py)
# =====================================================================

def start(host: Optional[str] = None, port: Optional[int] = None, path: Optional[str] = None) -> None:
    """
    Readies the WebSocket service. The route is mounted directly on
    the existing FastAPI app (backend/api/api.py's `app`), which is
    already served by main.py's own uvicorn server on API_HOST:API_PORT
    - so host/port are accepted here (matching the interface
    main.py's Orchestrator calls) and recorded for status/logging
    purposes, but the WebSocket endpoint is reachable at
    ws://<API_HOST>:<API_PORT><path>, matching what
    frontend/src/services/websocket.js actually connects to.
    """
    global _active

    resolved_path = path or WS_PATH
    resolved_host = host or WS_HOST
    resolved_port = port or WS_PORT

    with safe_execute("websocket.start", reraise=True):
        _register_route(resolved_path)

    _active = True
    logger.info(
        "WebSocket service ready at path=%s (served alongside the REST API; "
        "configured host=%s port=%s are informational only).",
        resolved_path, resolved_host, resolved_port,
    )


def stop() -> None:
    """
    Stops broadcasting and gracefully closes every connected client.
    The FastAPI route itself remains registered (Starlette does not
    support runtime route removal) but is inert - broadcast() is a
    no-op while inactive, and existing connections are closed rather
    than left dangling across a stop/start cycle.
    """
    global _active, _heartbeat_task

    _active = False

    if _loop is not None and _loop.is_running():
        with safe_execute("websocket.stop"):
            future = asyncio.run_coroutine_threadsafe(_close_all_clients(), _loop)
            future.result(timeout=5)

        if _heartbeat_task is not None:
            with safe_execute("websocket.cancel_heartbeat"):
                _loop.call_soon_threadsafe(_heartbeat_task.cancel)
            _heartbeat_task = None

    logger.info("WebSocket service stopped.")


def broadcast(payload: dict[str, Any]) -> None:
    """
    Fans one monitoring-cycle payload out to every connected client.
    Called synchronously, once per cycle, from main.py's monitoring
    loop (a plain background thread with no asyncio event loop of its
    own) - so delivery is handed off to the FastAPI server's event
    loop via asyncio.run_coroutine_threadsafe() and this function
    returns immediately without waiting for any client's send to
    complete. Never raises: any failure here must not interrupt the
    monitoring loop.
    """
    if not _active:
        return
    if _loop is None or not _loop.is_running():
        return
    if not payload:
        return

    with safe_execute("websocket.broadcast"):
        messages = _build_channel_messages(payload)
        asyncio.run_coroutine_threadsafe(_broadcast_messages(messages), _loop)


def get_status() -> dict[str, Any]:
    """Live status for FastAPI/dashboard exposure, if ever wired into a status endpoint."""
    return {
        "active": _active,
        "path": WS_PATH,
        "connected_clients": _client_count(),
        "heartbeat_interval_seconds": WS_HEARTBEAT_INTERVAL_SECONDS,
    }


__all__ = [
    "start",
    "stop",
    "broadcast",
    "get_status",
]