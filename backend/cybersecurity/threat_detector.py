from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger

from backend.cybersecurity import security_engine
from backend.cybersecurity import suspicious_process
from backend.cybersecurity import vulnerability_scan

try:
    # NOTE: this module exists on disk as intrusion_detection.py, not
    # intrusion_detector.py - imported under its real, current name
    # per the "do not rename files" constraint. Guarded so a rename
    # either direction doesn't break threat_detector.py's import.
    from backend.cybersecurity import intrusion_detection
except ImportError:
    intrusion_detection = None

logger = get_logger("lavender_trinetra.cybersecurity.threat_detector")

MAX_RECENT_THREATS = int(getattr(settings, "THREAT_DETECTOR_HISTORY_SIZE", 500))


# ---------------------------------------------------------------------
# Severity / subsystem vocabulary
# ---------------------------------------------------------------------
class ThreatSeverity:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


_SEVERITY_ORDER = {
    ThreatSeverity.LOW: 0,
    ThreatSeverity.MEDIUM: 1,
    ThreatSeverity.HIGH: 2,
    ThreatSeverity.CRITICAL: 3,
}

# Maps the risk_level vocabulary already produced by the Phase 1
# monitoring submodules (none/low/medium/high) onto this module's
# threat severity vocabulary (Low/Medium/High/Critical). Individual
# submodule risk is never reported here as Critical on its own -
# Critical is reserved for correlated, multi-subsystem findings.
_RISK_LEVEL_TO_SEVERITY = {
    "none": None,
    "low": ThreatSeverity.LOW,
    "medium": ThreatSeverity.MEDIUM,
    "high": ThreatSeverity.HIGH,
}


class ThreatSubsystem:
    PROCESS = "process"
    NETWORK = "network"
    PORT = "port"
    FIREWALL = "firewall"
    SESSION = "session"
    CORRELATED = "correlated"


def _max_severity(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b


def _escalate(severity: Optional[str]) -> Optional[str]:
    """Bumps a severity one level up, capped at Critical."""
    if severity is None:
        return ThreatSeverity.MEDIUM
    order = [ThreatSeverity.LOW, ThreatSeverity.MEDIUM, ThreatSeverity.HIGH, ThreatSeverity.CRITICAL]
    idx = min(order.index(severity) + 1, len(order) - 1)
    return order[idx]


# ---------------------------------------------------------------------
# Threat record
# ---------------------------------------------------------------------
@dataclass
class Threat:
    threat_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    subsystem: str = ThreatSubsystem.CORRELATED
    severity: str = ThreatSeverity.LOW
    title: str = ""
    reason: str = ""
    source_events: list[dict[str, Any]] = field(default_factory=list)
    correlated_subsystems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_id": self.threat_id,
            "timestamp": self.timestamp,
            "subsystem": self.subsystem,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "source_events": self.source_events,
            "correlated_subsystems": self.correlated_subsystems,
        }


# ---------------------------------------------------------------------
# In-memory recent-threat buffer (until security_logger.py provides
# PostgreSQL persistence - this module never writes to the database
# directly, consistent with security_engine.py's ownership model).
# ---------------------------------------------------------------------
_lock = threading.Lock()
_recent_threats: list[Threat] = []


def _record(threats: list[Threat]) -> None:
    if not threats:
        return
    with _lock:
        _recent_threats.extend(threats)
        overflow = len(_recent_threats) - MAX_RECENT_THREATS
        if overflow > 0:
            del _recent_threats[:overflow]


# ---------------------------------------------------------------------
# Per-subsystem rule-based detection
# ---------------------------------------------------------------------
def _detect_from_risk_scored_events(
    events: list[dict[str, Any]],
    subsystem: str,
    event_types: Optional[set[str]] = None,
    title_key: str = "name",
) -> list[Threat]:
    """
    Generic detector for any Phase 1 submodule output that already
    carries a risk_level/risk_reasons pair (process_monitor,
    network_monitor's connection entries, port_monitor's listening
    entries, session_monitor's active-session entries). Translates
    that risk assessment into a Threat without re-deriving it.
    """
    threats: list[Threat] = []
    for event in events or []:
        if event_types is not None and event.get("type") not in event_types:
            continue

        risk_level = str(event.get("risk_level", "none")).lower()
        severity = _RISK_LEVEL_TO_SEVERITY.get(risk_level)
        if severity is None:
            continue

        reasons = event.get("risk_reasons") or []
        label = event.get(title_key) or event.get("name") or event.get("process_name") or subsystem
        threats.append(
            Threat(
                subsystem=subsystem,
                severity=severity,
                title=f"Suspicious {subsystem} activity: {label}",
                reason="; ".join(reasons) if reasons else f"{subsystem} risk level {risk_level}",
                source_events=[event],
            )
        )
    return threats


def _detect_firewall_threats(firewall_events: list[dict[str, Any]]) -> list[Threat]:
    threats: list[Threat] = []
    for event in firewall_events or []:
        event_type = event.get("type")
        if event_type == "firewall_disabled":
            threats.append(
                Threat(
                    subsystem=ThreatSubsystem.FIREWALL,
                    severity=ThreatSeverity.HIGH,
                    title="Firewall disabled",
                    reason=event.get("detail") or "The system firewall transitioned to a disabled state.",
                    source_events=[event],
                )
            )
        elif event_type == "firewall_unavailable":
            threats.append(
                Threat(
                    subsystem=ThreatSubsystem.FIREWALL,
                    severity=ThreatSeverity.MEDIUM,
                    title="Firewall management interface unavailable",
                    reason=event.get("detail") or "Unable to query firewall status.",
                    source_events=[event],
                )
            )
        elif event_type == "firewall_status":
            risk_level = str(event.get("risk_level", "none")).lower()
            severity = _RISK_LEVEL_TO_SEVERITY.get(risk_level)
            if severity is not None:
                reasons = event.get("risk_reasons") or []
                threats.append(
                    Threat(
                        subsystem=ThreatSubsystem.FIREWALL,
                        severity=severity,
                        title="Firewall configuration concern",
                        reason="; ".join(reasons) if reasons else "Firewall risk detected.",
                        source_events=[event],
                    )
                )
    return threats


def _detect_session_threats(session_events: list[dict[str, Any]]) -> list[Threat]:
    threats = _detect_from_risk_scored_events(
        session_events, ThreatSubsystem.SESSION, event_types={"session_active"}, title_key="username"
    )
    for event in session_events or []:
        if event.get("type") == "session_login" and str(event.get("risk_level", "none")).lower() not in ("none", ""):
            threats.append(
                Threat(
                    subsystem=ThreatSubsystem.SESSION,
                    severity=_RISK_LEVEL_TO_SEVERITY.get(str(event.get("risk_level")).lower(), ThreatSeverity.LOW),
                    title=f"Suspicious login: {event.get('username', 'unknown user')}",
                    reason="; ".join(event.get("risk_reasons") or []) or "Unusual session login detected.",
                    source_events=[event],
                )
            )
    return threats


def _detect_port_threats(port_events: list[dict[str, Any]]) -> list[Threat]:
    threats = _detect_from_risk_scored_events(
        port_events, ThreatSubsystem.PORT, event_types={"port_listening"}, title_key="local_port"
    )
    for event in port_events or []:
        if event.get("type") == "port_opened":
            threats.append(
                Threat(
                    subsystem=ThreatSubsystem.PORT,
                    severity=ThreatSeverity.LOW,
                    title=f"New listening port opened: {event.get('local_port', event.get('port', '?'))}",
                    reason="A previously closed port began listening for connections.",
                    source_events=[event],
                )
            )
    return threats


# ---------------------------------------------------------------------
# Cross-subsystem correlation
# ---------------------------------------------------------------------
def _correlate(
    process_threats: list[Threat],
    network_events: list[dict[str, Any]],
    port_events: list[dict[str, Any]],
) -> list[Threat]:
    """
    Escalates a process-level threat to Critical when the same process
    (by pid) is independently implicated in a flagged network
    connection or a flagged listening port during the same cycle -
    multiple independent subsystems agreeing on the same process is a
    stronger signal than any one of them alone.
    """
    correlated: list[Threat] = []

    flagged_network_pids = {
        e.get("pid")
        for e in (network_events or [])
        if e.get("type") == "connection" and str(e.get("risk_level", "none")).lower() != "none" and e.get("pid")
    }
    flagged_port_pids = {
        e.get("pid")
        for e in (port_events or [])
        if e.get("type") == "port_listening" and str(e.get("risk_level", "none")).lower() != "none" and e.get("pid")
    }

    for threat in process_threats:
        pid = None
        if threat.source_events:
            pid = threat.source_events[0].get("pid")
        if pid is None:
            continue

        matched: list[str] = []
        if pid in flagged_network_pids:
            matched.append(ThreatSubsystem.NETWORK)
        if pid in flagged_port_pids:
            matched.append(ThreatSubsystem.PORT)

        if matched:
            threat.severity = _escalate(threat.severity)
            threat.correlated_subsystems = matched
            threat.subsystem = ThreatSubsystem.CORRELATED
            threat.reason = (
                f"{threat.reason} Correlated with flagged activity in: {', '.join(matched)} "
                f"(pid {pid}) during the same cycle."
            )
            correlated.append(threat)

    return correlated


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def detect_threats(cycle_result: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Analyzes one security_engine.py cycle_result and returns a list of
    threat dicts with assigned severity, affected subsystem, timestamp
    and an explainable reason. Called by security_engine.py once per
    security cycle; the returned list is expected to be merged into
    cycle_result and forwarded to security_logger.py for persistence
    and FastAPI exposure by the caller.
    """
    try:
        processes = cycle_result.get("processes", [])
        network_events = cycle_result.get("network_connections", [])
        port_events = cycle_result.get("open_ports", [])
        firewall_events = cycle_result.get("firewall_events", [])
        session_events = cycle_result.get("sessions", [])

        process_threats = _detect_from_risk_scored_events(processes, ThreatSubsystem.PROCESS, title_key="name")
        network_threats = _detect_from_risk_scored_events(
            network_events, ThreatSubsystem.NETWORK, event_types={"connection"}, title_key="remote_address"
        )
        traffic_spikes = [
            e for e in network_events or []
            if e.get("type") == "traffic_io" and str(e.get("risk_level", "none")).lower() != "none"
        ]
        for spike in traffic_spikes:
            network_threats.append(
                Threat(
                    subsystem=ThreatSubsystem.NETWORK,
                    severity=_RISK_LEVEL_TO_SEVERITY.get(str(spike.get("risk_level")).lower(), ThreatSeverity.MEDIUM),
                    title="Abnormal network traffic volume",
                    reason="; ".join(spike.get("risk_reasons") or []) or "Traffic rate exceeded expected bounds.",
                    source_events=[spike],
                )
            )

        port_threats = _detect_port_threats(port_events)
        firewall_threats = _detect_firewall_threats(firewall_events)
        session_threats = _detect_session_threats(session_events)

        correlated_threats = _correlate(process_threats, network_events, port_events)

        all_threats = (
            process_threats
            + network_threats
            + port_threats
            + firewall_threats
            + session_threats
            + correlated_threats
        )

        if all_threats:
            logger.warning(
                "Threat detector identified %d threat(s) this cycle (severities: %s).",
                len(all_threats),
                ", ".join(sorted({t.severity for t in all_threats})),
            )
        else:
            logger.debug("Threat detector: no threats identified this cycle.")

        _record(all_threats)
        return [t.to_dict() for t in all_threats]
    except Exception as exc:
        logger.exception("Threat detection failed: %s", exc)
        return []


def get_recent_threats(limit: int = 100) -> list[dict[str, Any]]:
    """Returns the most recent threats, newest first. For FastAPI exposure."""
    with _lock:
        items = list(_recent_threats[-limit:])
    items.reverse()
    return [t.to_dict() for t in items]


def get_active_threats(min_severity: str = ThreatSeverity.MEDIUM) -> list[dict[str, Any]]:
    """Returns recent threats at or above the given severity. For FastAPI exposure."""
    threshold = _SEVERITY_ORDER.get(min_severity, _SEVERITY_ORDER[ThreatSeverity.MEDIUM])
    with _lock:
        items = [t for t in _recent_threats if _SEVERITY_ORDER.get(t.severity, 0) >= threshold]
    items.sort(key=lambda t: t.timestamp, reverse=True)
    return [t.to_dict() for t in items]


def get_threat_summary() -> dict[str, Any]:
    """Returns counts of recent threats by severity. For FastAPI/dashboard exposure."""
    with _lock:
        items = list(_recent_threats)
    counts = {ThreatSeverity.LOW: 0, ThreatSeverity.MEDIUM: 0, ThreatSeverity.HIGH: 0, ThreatSeverity.CRITICAL: 0}
    for t in items:
        if t.severity in counts:
            counts[t.severity] += 1
    return {
        "total": len(items),
        "counts": counts,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------
# Coordination facade for main.py
# ---------------------------------------------------------------------
# main.py's orchestrator imports this module as "the cybersecurity
# coordination entrypoint" (see backend/main.py's
# _load_cybersecurity_engine()) and calls start()/stop()/run_cycle()
# on it directly, driven by its own single monitoring loop - the same
# cadence pattern already used for the AI engine. This module is the
# natural home for that facade since main.py already targets it by
# name; it does not start security_engine.py's own independent timer
# thread, to avoid scanning the same data on two separate schedules.
_active = False


def start() -> None:
    """Called once by main.py when monitoring starts."""
    global _active
    _active = True
    logger.info("Threat detection engine ready (cadence driven by main.py's monitoring loop).")


def stop() -> None:
    """Called once by main.py when monitoring stops."""
    global _active
    _active = False
    logger.info("Threat detection engine stopped.")


def run_cycle(
    metrics_row: Optional[dict[str, Any]] = None,
    process_rows: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Called by main.py once per monitoring tick. Drives one
    security_engine.py collection cycle, then runs every Phase 2
    analysis module (this module's own correlation, suspicious
    process detection, intrusion detection, vulnerability scanning)
    against that single cycle_result - no module re-collects data
    that security_engine.py already gathered this cycle.
    """
    if not _active:
        logger.debug("run_cycle() called while inactive; running anyway (idempotent).")

    cycle_result = security_engine.run_security_cycle(metrics_row, process_rows)

    cycle_result["threats"] = detect_threats(cycle_result)
    cycle_result["process_alerts"] = suspicious_process.analyze(cycle_result.get("processes", []))
    cycle_result["vulnerabilities"] = vulnerability_scan.scan_vulnerabilities(
        cycle_result.get("firewall_events", []), cycle_result.get("open_ports", [])
    )
    if intrusion_detection is not None:
        cycle_result["intrusions"] = intrusion_detection.detect_intrusions(cycle_result)
    else:
        cycle_result["intrusions"] = []
        logger.debug("intrusion_detection module unavailable; skipping intrusion analysis this cycle.")

    return cycle_result


def get_status() -> dict[str, Any]:
    """Live status for FastAPI/dashboard exposure, combining engine and threat-detector state."""
    status = security_engine.get_security_status()
    status["threat_summary"] = get_threat_summary()
    status["active"] = _active
    return status