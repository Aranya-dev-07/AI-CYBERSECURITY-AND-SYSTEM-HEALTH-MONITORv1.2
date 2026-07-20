from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger

logger = get_logger("lavender_trinetra.cybersecurity.intrusion_detector")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------
CONNECTION_ATTEMPT_WINDOW_SECONDS = float(
    getattr(settings, "INTRUSION_CONNECTION_WINDOW_SECONDS", 60.0)
)
CONNECTION_ATTEMPT_THRESHOLD = int(getattr(settings, "INTRUSION_CONNECTION_ATTEMPT_THRESHOLD", 15))
PORT_SCAN_DISTINCT_PORTS_THRESHOLD = int(getattr(settings, "INTRUSION_PORT_SCAN_DISTINCT_PORTS", 5))

LOGIN_ATTEMPT_WINDOW_SECONDS = float(getattr(settings, "INTRUSION_LOGIN_WINDOW_SECONDS", 120.0))
LOGIN_ATTEMPT_THRESHOLD = int(getattr(settings, "INTRUSION_LOGIN_ATTEMPT_THRESHOLD", 5))

# Ports considered normal/expected to be listening. A newly-opened port
# outside this list is treated as "unexpected port activity" - a weak
# signal on its own, escalated further if the port is also flagged by
# port_monitor.py's own risk assessment.
EXPECTED_OPEN_PORTS = frozenset(
    getattr(settings, "INTRUSION_EXPECTED_OPEN_PORTS", {22, 80, 443, 3306, 5432, 8000, 5173})
)


class IntrusionSeverity:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class IntrusionCategory:
    UNUSUAL_NETWORK_ACTIVITY = "unusual_network_activity"
    UNEXPECTED_PORT_ACTIVITY = "unexpected_port_activity"
    SUSPICIOUS_SESSION_BEHAVIOR = "suspicious_session_behavior"
    REPEATED_CONNECTION_ATTEMPTS = "repeated_connection_attempts"
    PORT_SCAN_SUSPECTED = "port_scan_suspected"


@dataclass
class IntrusionAlert:
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    category: str = ""
    severity: str = IntrusionSeverity.LOW
    source: Optional[str] = None
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "severity": self.severity,
            "source": self.source,
            "reason": self.reason,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------
# State tracked across calls
# ---------------------------------------------------------------------
_lock = threading.Lock()
_connection_attempts: dict[str, deque] = defaultdict(deque)  # remote_ip -> deque[(datetime, port)]
_login_attempts: dict[str, deque] = defaultdict(deque)       # username -> deque[datetime]
_recent_alerts: deque = deque(maxlen=int(getattr(settings, "INTRUSION_DETECTOR_HISTORY_SIZE", 500)))


def _prune(dq: deque, window_start: datetime, key=lambda item: item) -> None:
    while dq and key(dq[0]) < window_start:
        dq.popleft()


def _record(alerts: list[IntrusionAlert]) -> None:
    if not alerts:
        return
    with _lock:
        _recent_alerts.extend(alerts)


# ---------------------------------------------------------------------
# Unusual network activity
# ---------------------------------------------------------------------
def _detect_unusual_network_activity(network_events: list[dict[str, Any]]) -> list[IntrusionAlert]:
    alerts: list[IntrusionAlert] = []
    for event in network_events or []:
        if event.get("type") != "connection":
            continue
        risk_level = str(event.get("risk_level", "none")).lower()
        if risk_level == "none":
            continue

        severity = {
            "low": IntrusionSeverity.LOW,
            "medium": IntrusionSeverity.MEDIUM,
            "high": IntrusionSeverity.HIGH,
        }.get(risk_level, IntrusionSeverity.LOW)

        reasons = event.get("risk_reasons") or []
        remote = event.get("remote_address") or "unknown"
        alerts.append(
            IntrusionAlert(
                category=IntrusionCategory.UNUSUAL_NETWORK_ACTIVITY,
                severity=severity,
                source=remote,
                reason="; ".join(reasons) if reasons else f"Unusual connection behavior involving {remote}.",
                evidence={
                    "pid": event.get("pid"),
                    "process_name": event.get("process_name"),
                    "remote_address": event.get("remote_address"),
                    "remote_port": event.get("remote_port"),
                    "local_port": event.get("local_port"),
                    "status": event.get("status"),
                },
            )
        )
    return alerts


# ---------------------------------------------------------------------
# Repeated connection attempts / port-scan detection
# ---------------------------------------------------------------------
def _detect_repeated_connection_attempts(network_events: list[dict[str, Any]]) -> list[IntrusionAlert]:
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=CONNECTION_ATTEMPT_WINDOW_SECONDS)
    alerts: list[IntrusionAlert] = []

    connections = [e for e in (network_events or []) if e.get("type") == "connection" and e.get("remote_address")]

    with _lock:
        for event in connections:
            remote_ip = event["remote_address"]
            dq = _connection_attempts[remote_ip]
            dq.append((now, event.get("local_port")))
            _prune(dq, window_start, key=lambda item: item[0])

        flagged_ips = list(_connection_attempts.items())

    for remote_ip, dq in flagged_ips:
        with _lock:
            attempts = list(dq)
        if not attempts:
            continue

        attempt_count = len(attempts)
        distinct_ports = {port for _, port in attempts if port is not None}

        if len(distinct_ports) >= PORT_SCAN_DISTINCT_PORTS_THRESHOLD:
            alerts.append(
                IntrusionAlert(
                    category=IntrusionCategory.PORT_SCAN_SUSPECTED,
                    severity=IntrusionSeverity.HIGH,
                    source=remote_ip,
                    reason=(
                        f"{remote_ip} connected to {len(distinct_ports)} distinct local ports within "
                        f"{CONNECTION_ATTEMPT_WINDOW_SECONDS:.0f} seconds, consistent with port scanning."
                    ),
                    evidence={"distinct_ports": sorted(p for p in distinct_ports if p is not None), "attempt_count": attempt_count},
                )
            )
        elif attempt_count >= CONNECTION_ATTEMPT_THRESHOLD:
            alerts.append(
                IntrusionAlert(
                    category=IntrusionCategory.REPEATED_CONNECTION_ATTEMPTS,
                    severity=IntrusionSeverity.MEDIUM,
                    source=remote_ip,
                    reason=(
                        f"{remote_ip} made {attempt_count} connection attempts within "
                        f"{CONNECTION_ATTEMPT_WINDOW_SECONDS:.0f} seconds, exceeding the "
                        f"{CONNECTION_ATTEMPT_THRESHOLD} threshold."
                    ),
                    evidence={"attempt_count": attempt_count},
                )
            )

    return alerts


# ---------------------------------------------------------------------
# Unexpected port activity
# ---------------------------------------------------------------------
def _detect_unexpected_port_activity(port_events: list[dict[str, Any]]) -> list[IntrusionAlert]:
    alerts: list[IntrusionAlert] = []
    for event in port_events or []:
        if event.get("type") != "port_opened":
            continue

        port = event.get("local_port") or event.get("port")
        if port in EXPECTED_OPEN_PORTS:
            continue

        alerts.append(
            IntrusionAlert(
                category=IntrusionCategory.UNEXPECTED_PORT_ACTIVITY,
                severity=IntrusionSeverity.MEDIUM,
                source=f"port {port}",
                reason=f"Port {port} began listening for connections and is not on the expected-ports list.",
                evidence={"port": port, "pid": event.get("pid"), "process_name": event.get("process_name")},
            )
        )

    for event in port_events or []:
        if event.get("type") != "port_listening":
            continue
        risk_level = str(event.get("risk_level", "none")).lower()
        if risk_level in ("high",):
            reasons = event.get("risk_reasons") or []
            alerts.append(
                IntrusionAlert(
                    category=IntrusionCategory.UNEXPECTED_PORT_ACTIVITY,
                    severity=IntrusionSeverity.HIGH,
                    source=f"port {event.get('local_port')}",
                    reason="; ".join(reasons) if reasons else "High-risk listening port detected.",
                    evidence={"port": event.get("local_port"), "pid": event.get("pid")},
                )
            )

    return alerts


# ---------------------------------------------------------------------
# Suspicious session behavior
# ---------------------------------------------------------------------
def _detect_suspicious_session_behavior(session_events: list[dict[str, Any]]) -> list[IntrusionAlert]:
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=LOGIN_ATTEMPT_WINDOW_SECONDS)
    alerts: list[IntrusionAlert] = []

    for event in session_events or []:
        risk_level = str(event.get("risk_level", "none")).lower()
        if event.get("type") in ("session_active", "session_login") and risk_level not in ("none", ""):
            severity = {
                "low": IntrusionSeverity.LOW,
                "medium": IntrusionSeverity.MEDIUM,
                "high": IntrusionSeverity.HIGH,
            }.get(risk_level, IntrusionSeverity.LOW)
            reasons = event.get("risk_reasons") or []
            username = event.get("username") or "unknown"
            alerts.append(
                IntrusionAlert(
                    category=IntrusionCategory.SUSPICIOUS_SESSION_BEHAVIOR,
                    severity=severity,
                    source=username,
                    reason="; ".join(reasons) if reasons else f"Unusual session behavior for user {username}.",
                    evidence={"username": username, "terminal": event.get("terminal")},
                )
            )

        if event.get("type") == "session_login":
            username = event.get("username") or "unknown"
            with _lock:
                dq = _login_attempts[username]
                dq.append(now)
                _prune(dq, window_start)
                attempt_count = len(dq)

            if attempt_count >= LOGIN_ATTEMPT_THRESHOLD:
                alerts.append(
                    IntrusionAlert(
                        category=IntrusionCategory.SUSPICIOUS_SESSION_BEHAVIOR,
                        severity=IntrusionSeverity.HIGH,
                        source=username,
                        reason=(
                            f"User '{username}' logged in {attempt_count} times within "
                            f"{LOGIN_ATTEMPT_WINDOW_SECONDS:.0f} seconds, consistent with a "
                            f"brute-force or credential-stuffing attempt."
                        ),
                        evidence={"attempt_count": attempt_count, "username": username},
                    )
                )

    return alerts


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def detect_intrusions(cycle_result: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Analyzes one security_engine.py cycle_result for potential
    intrusion attempts across network, port and session activity, and
    returns a list of explainable intrusion alert dicts. Called by
    security_engine.py once per security cycle; does not perform any
    scanning itself, only re-analyzes data network_monitor.py,
    port_monitor.py and session_monitor.py already collected.
    """
    try:
        network_events = cycle_result.get("network_connections", [])
        port_events = cycle_result.get("open_ports", [])
        session_events = cycle_result.get("sessions", [])

        alerts: list[IntrusionAlert] = []
        alerts.extend(_detect_unusual_network_activity(network_events))
        alerts.extend(_detect_repeated_connection_attempts(network_events))
        alerts.extend(_detect_unexpected_port_activity(port_events))
        alerts.extend(_detect_suspicious_session_behavior(session_events))

        if alerts:
            logger.warning(
                "Intrusion detector raised %d alert(s) this cycle (categories: %s).",
                len(alerts),
                ", ".join(sorted({a.category for a in alerts})),
            )
        else:
            logger.debug("Intrusion detector: no intrusion indicators this cycle.")

        _record(alerts)
        return [a.to_dict() for a in alerts]
    except Exception as exc:
        logger.exception("Intrusion detection failed: %s", exc)
        return []


def get_recent_intrusions(limit: int = 100) -> list[dict[str, Any]]:
    """Returns the most recent intrusion alerts, newest first. For FastAPI exposure."""
    with _lock:
        items = list(_recent_alerts)[-limit:]
    items.reverse()
    return [a.to_dict() for a in items]