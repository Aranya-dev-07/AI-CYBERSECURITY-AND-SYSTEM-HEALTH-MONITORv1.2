from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import psutil

from backend.config import settings
from backend.core import get_logger, safe_call

logger = get_logger("lavender_trinetra.cybersecurity.port_monitor")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------

# Ports commonly associated with backdoors, reverse shells and known
# malware C2 tooling when found LISTENING locally. Not a definitive
# signal on its own - a contributing factor, mirroring the watch-list
# approach used in process_monitor.py / network_monitor.py.
WATCHED_LISTEN_PORTS = frozenset(
    getattr(
        settings,
        "PORT_WATCHED_LISTEN_PORTS",
        {4444, 1337, 31337, 6667, 12345, 54321, 2323, 5555},
    )
)

# Local addresses considered "all interfaces" - a listening port bound
# here is reachable from outside the host, which raises its exposure
# relative to a loopback-only bind.
_ALL_INTERFACES_ADDRESSES = frozenset({"0.0.0.0", "::"})

# Recent port-event history kept in memory for on-demand reads (e.g. a
# future FastAPI dashboard endpoint calling get_recent_port_events()).
# Bounded to avoid unbounded growth over a long-running process.
PORT_EVENT_HISTORY_LIMIT = int(getattr(settings, "PORT_EVENT_HISTORY_LIMIT", 200))

# Maps psutil connection type constants to a human-readable protocol.
_PROTOCOL_BY_TYPE = {
    "SOCK_STREAM": "TCP",
    "SOCK_DGRAM": "UDP",
}


class PortRiskLevel:
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------
@dataclass
class PortObservation:
    protocol: str
    local_ip: Optional[str]
    local_port: Optional[int]
    pid: Optional[int]
    process_name: Optional[str]
    status: Optional[str]
    exposed_all_interfaces: bool
    timestamp: str
    risk_level: str = PortRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def key(self) -> tuple:
        # Identity used to diff this snapshot against the previous one.
        # Includes pid so a port closed by one process and immediately
        # reopened by another is correctly treated as closed+opened
        # rather than unchanged.
        return (self.protocol, self.local_ip, self.local_port, self.pid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "pid": self.pid,
            "process_name": self.process_name,
            "status": self.status,
            "exposed_all_interfaces": self.exposed_all_interfaces,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


@dataclass
class PortEvent:
    event_type: str  # "port_opened" | "port_closed"
    protocol: str
    local_ip: Optional[str]
    local_port: Optional[int]
    pid: Optional[int]
    process_name: Optional[str]
    timestamp: str
    risk_level: str = PortRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "protocol": self.protocol,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "pid": self.pid,
            "process_name": self.process_name,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


# ---------------------------------------------------------------------
# Internal state (guarded by _state_lock - scan() may be invoked from
# security_engine's background thread and/or directly from the FastAPI
# layer for on-demand reads).
# ---------------------------------------------------------------------
_state_lock = threading.Lock()
_previous_ports: dict[tuple, PortObservation] = {}
_recent_events: list[dict[str, Any]] = []


def _addr_to_ip_port(addr: Any) -> tuple[Optional[str], Optional[int]]:
    if not addr:
        return None, None
    ip = getattr(addr, "ip", None)
    port = getattr(addr, "port", None)
    if ip is None and isinstance(addr, tuple) and len(addr) == 2:
        ip, port = addr
    return ip, port


def _resolve_process_name(pid: Optional[int]) -> Optional[str]:
    if not pid:
        return None
    proc = safe_call(psutil.Process, pid)
    if proc is None:
        return None
    return safe_call(proc.name)


def _assess_port_risk(obs: PortObservation) -> None:
    """
    Rule-based risk assessment. Intentionally simple and transparent -
    the AI layer (outside this module's scope) is responsible for
    deeper correlation, explanation and prioritization.
    """
    reasons: list[str] = []

    if obs.local_port in WATCHED_LISTEN_PORTS:
        reasons.append(f"Listening port {obs.local_port} is on the watch list")

    if obs.exposed_all_interfaces:
        reasons.append(f"Port {obs.local_port} is bound to all interfaces ({obs.local_ip})")

    if obs.pid is not None and obs.process_name is None:
        reasons.append("Listening socket's owning process could not be resolved")

    obs.risk_reasons = reasons
    if not reasons:
        obs.risk_level = PortRiskLevel.NONE
    elif len(reasons) == 1:
        obs.risk_level = PortRiskLevel.LOW
    elif len(reasons) == 2:
        obs.risk_level = PortRiskLevel.MEDIUM
    else:
        obs.risk_level = PortRiskLevel.HIGH


def _is_listening_udp(conn: Any) -> bool:
    # UDP sockets have no LISTEN state in psutil; a bound UDP socket
    # with a local address and no remote peer is the UDP equivalent of
    # "open/listening".
    protocol = _PROTOCOL_BY_TYPE.get(getattr(conn.type, "name", str(conn.type)))
    return protocol == "UDP" and bool(conn.laddr) and not conn.raddr


def _is_listening_tcp(conn: Any) -> bool:
    protocol = _PROTOCOL_BY_TYPE.get(getattr(conn.type, "name", str(conn.type)))
    return protocol == "TCP" and conn.status == psutil.CONN_LISTEN


# ---------------------------------------------------------------------
# Core scanning
# ---------------------------------------------------------------------
def _scan_listening_ports() -> list[PortObservation]:
    try:
        raw_connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        logger.warning(
            "Insufficient permissions to enumerate listening ports; "
            "skipping this cycle's port scan."
        )
        return []
    except Exception as exc:
        logger.exception("Failed to enumerate listening ports: %s", exc)
        return []

    now_iso = datetime.utcnow().isoformat()
    observations: list[PortObservation] = []

    for conn in raw_connections:
        if not (_is_listening_tcp(conn) or _is_listening_udp(conn)):
            continue

        protocol = _PROTOCOL_BY_TYPE.get(getattr(conn.type, "name", str(conn.type)), "UNKNOWN")
        local_ip, local_port = _addr_to_ip_port(conn.laddr)

        obs = PortObservation(
            protocol=protocol,
            local_ip=local_ip,
            local_port=local_port,
            pid=conn.pid,
            process_name=_resolve_process_name(conn.pid),
            status=conn.status,
            exposed_all_interfaces=local_ip in _ALL_INTERFACES_ADDRESSES,
            timestamp=now_iso,
        )
        _assess_port_risk(obs)
        observations.append(obs)

    return observations


def _diff_ports(current: list[PortObservation]) -> tuple[list[PortEvent], dict[tuple, PortObservation]]:
    """
    Compares the current listening-port snapshot against the previous
    one to detect newly opened and newly closed ports. Must be called
    while holding _state_lock.
    """
    current_by_key = {obs.key(): obs for obs in current}
    events: list[PortEvent] = []
    now_iso = datetime.utcnow().isoformat()

    for key, obs in current_by_key.items():
        if key not in _previous_ports:
            events.append(
                PortEvent(
                    event_type="port_opened",
                    protocol=obs.protocol,
                    local_ip=obs.local_ip,
                    local_port=obs.local_port,
                    pid=obs.pid,
                    process_name=obs.process_name,
                    timestamp=now_iso,
                    risk_level=obs.risk_level,
                    risk_reasons=obs.risk_reasons,
                )
            )

    for key, prev_obs in _previous_ports.items():
        if key not in current_by_key:
            events.append(
                PortEvent(
                    event_type="port_closed",
                    protocol=prev_obs.protocol,
                    local_ip=prev_obs.local_ip,
                    local_port=prev_obs.local_port,
                    pid=prev_obs.pid,
                    process_name=prev_obs.process_name,
                    timestamp=now_iso,
                )
            )

    if events:
        opened = sum(1 for e in events if e.event_type == "port_opened")
        closed = sum(1 for e in events if e.event_type == "port_closed")
        logger.info("Port changes detected: %d opened, %d closed.", opened, closed)

    return events, current_by_key


def _record_events(events: list[dict[str, Any]]) -> None:
    """Appends to the bounded in-memory recent-event buffer used by
    get_recent_port_events(). Must be called while holding _state_lock."""
    global _recent_events
    _recent_events.extend(events)
    if len(_recent_events) > PORT_EVENT_HISTORY_LIMIT:
        _recent_events = _recent_events[-PORT_EVENT_HISTORY_LIMIT:]


# ---------------------------------------------------------------------
# Reusable public accessors
# ---------------------------------------------------------------------
def get_listening_ports() -> list[dict[str, Any]]:
    """Reusable accessor returning all currently observed listening ports."""
    return [obs.to_dict() for obs in _scan_listening_ports()]


def get_port_by_process(pid: int) -> list[dict[str, Any]]:
    """Returns all listening ports currently owned by the given pid."""
    return [obs.to_dict() for obs in _scan_listening_ports() if obs.pid == pid]


def get_suspicious_ports() -> list[dict[str, Any]]:
    """Convenience wrapper returning only flagged listening ports."""
    return [p for p in get_listening_ports() if p["risk_level"] != PortRiskLevel.NONE]


def get_recent_port_events(limit: int = 50) -> list[dict[str, Any]]:
    """
    Reusable accessor for the most recent port_opened/port_closed
    events, intended for a live FastAPI dashboard endpoint. Data is
    kept in memory here for fast reads; durable persistence and any
    WebSocket push to the frontend is handled downstream by
    security_logger.py via security_engine.py, not by this module.
    """
    with _state_lock:
        return list(_recent_events[-limit:])


# ---------------------------------------------------------------------
# Entry point for security_engine.py
# ---------------------------------------------------------------------
def scan(process_rows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """
    Performs one port security scan and returns a flat list of
    structured, timestamped event dicts, each tagged with a "type"
    discriminator:
        - "port_listening" - one per currently listening TCP/UDP port
        - "port_opened"    - a port that was not listening last cycle
        - "port_closed"    - a port that was listening last cycle but
                              is no longer present

    Called by security_engine.py once per security cycle; its return
    value is stored verbatim under cycle_result["open_ports"] and
    forwarded to security_logger.py, which owns PostgreSQL persistence
    and any live delivery to the FastAPI dashboard. This module never
    writes to the database or a socket directly.

    `process_rows` is accepted for interface symmetry with
    process_monitor.scan() but is not required here - port-to-process
    attribution is resolved independently via psutil.
    """
    events: list[dict[str, Any]] = []

    try:
        current_ports = _scan_listening_ports()
    except Exception as exc:
        logger.exception("Listening port scan failed: %s", exc)
        current_ports = []

    with _state_lock:
        global _previous_ports
        try:
            diff_events, current_by_key = _diff_ports(current_ports)
        except Exception as exc:
            logger.exception("Port diff computation failed: %s", exc)
            diff_events, current_by_key = [], {obs.key(): obs for obs in current_ports}

        events.extend({"type": "port_listening", **obs.to_dict()} for obs in current_ports)
        events.extend({"type": e.event_type, **e.to_dict()} for e in diff_events)

        _previous_ports = current_by_key
        _record_events(events)

    suspicious = [e for e in events if e.get("risk_level") not in (None, PortRiskLevel.NONE)]
    if suspicious:
        logger.warning("Port scan flagged %d suspicious port event(s).", len(suspicious))
    else:
        logger.debug("Port scan complete: %d listening ports, no flags raised.", len(current_ports))

    return events