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

# Phase 3 (explainable AI security layer) - consumes this module's and
# intrusion_detection's output; never re-collects or re-detects
# anything itself. Guarded the same way as intrusion_detection above
# so threat_detector.py keeps functioning if any of these are absent.
try:
    from backend.cybersecurity import threat_classifier
except ImportError:
    threat_classifier = None

try:
    from backend.cybersecurity import security_score
except ImportError:
    security_score = None

try:
    from backend.cybersecurity import attack_patterns
except ImportError:
    attack_patterns = None

try:
    from backend.cybersecurity import security_recommendations
except ImportError:
    security_recommendations = None

# Phase 4 (incident management + historical reporting) - consumes this
# module's cycle_result (threats, intrusions, vulnerabilities, security
# score) purely to record confirmed incidents and durable score
# snapshots; neither module re-detects or re-scores anything itself.
# Imported after attack_patterns/security_recommendations above so that,
# if security_history.py is reached via its own import of
# attack_patterns.py, that module is already fully initialized in
# sys.modules (avoids a partial-import failure on the circular edge).
try:
    from backend.cybersecurity import incident_logger
except ImportError:
    incident_logger = None

try:
    from backend.cybersecurity import security_history
except ImportError:
    security_history = None

logger = get_logger("lavender_trinetra.cybersecurity.threat_detector")

# Only Medium+ severity findings are confirmed as incidents, to avoid
# flooding incident_logger.py with every transient Low-severity event.
_INCIDENT_MIN_SEVERITY_RANK = 1  # ThreatSeverity order index: Low=0, Medium=1, High=2, Critical=3

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
    if attack_patterns is not None and hasattr(attack_patterns, "start"):
        attack_patterns.start()
    if security_recommendations is not None and hasattr(security_recommendations, "start"):
        security_recommendations.start()
    # incident_logger.py's security_incidents table and
    # security_history.py's security_score_history table are both
    # defined against the shared Base but registered only once this
    # module (and therefore threat_detector.py, which is imported after
    # database.init_db() already ran) is imported - so each ensures its
    # own table exists here, mirroring attack_patterns.py's pattern.
    if incident_logger is not None and hasattr(incident_logger, "ensure_table_exists"):
        incident_logger.ensure_table_exists()
    if security_history is not None and hasattr(security_history, "start"):
        security_history.start()
    _active = True
    logger.info("Threat detection engine ready (cadence driven by main.py's monitoring loop).")


def stop() -> None:
    """Called once by main.py when monitoring stops."""
    global _active
    if attack_patterns is not None and hasattr(attack_patterns, "stop"):
        attack_patterns.stop()
    if security_recommendations is not None and hasattr(security_recommendations, "stop"):
        security_recommendations.stop()
    if security_history is not None and hasattr(security_history, "stop"):
        security_history.stop()
    _active = False
    logger.info("Threat detection engine stopped.")


def _record_confirmed_incidents(cycle_result: dict[str, Any]) -> None:
    """
    Phase 4 integration point: turns this cycle's confirmed findings
    (threats, intrusions, vulnerabilities) into durable incidents via
    incident_logger.log_incident(), and persists the cycle's security
    score via security_history.record_score_snapshot(). Performs no
    detection, scoring, or confirmation logic of its own - it only
    records what the modules above already confirmed this cycle.
    """
    if incident_logger is not None:
        try:
            for threat in cycle_result.get("threats", []) or []:
                if _SEVERITY_ORDER.get(threat.get("severity", "Low"), 0) < _INCIDENT_MIN_SEVERITY_RANK:
                    continue
                incident_logger.log_incident(
                    severity=threat.get("severity", "Low"),
                    category=incident_logger.IncidentCategory.THREAT,
                    source_module="threat_detector",
                    description=threat.get("reason") or threat.get("title") or "Threat detected.",
                )

            for intrusion in cycle_result.get("intrusions", []) or []:
                incident_logger.log_incident(
                    severity=intrusion.get("severity", "Medium"),
                    category=incident_logger.IncidentCategory.INTRUSION,
                    source_module="intrusion_detection",
                    description=intrusion.get("description") or intrusion.get("category") or "Intrusion event detected.",
                )

            for vulnerability in cycle_result.get("vulnerabilities", []) or []:
                if _SEVERITY_ORDER.get(vulnerability.get("severity", "Low"), 0) < _INCIDENT_MIN_SEVERITY_RANK:
                    continue
                incident_logger.log_incident(
                    severity=vulnerability.get("severity", "Low"),
                    category=incident_logger.IncidentCategory.VULNERABILITY,
                    source_module="vulnerability_scan",
                    description=vulnerability.get("description") or vulnerability.get("title") or "Vulnerability finding.",
                )
        except Exception:
            logger.exception("incident_logger integration failed this cycle.")

    if security_history is not None:
        try:
            security_score_result = cycle_result.get("security_score")
            if security_score_result:
                security_history.record_score_snapshot(security_score_result)
        except Exception:
            logger.exception("security_history score snapshot failed this cycle.")


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
    # NOTE: the public entry point is scan(), not scan_vulnerabilities();
    # it also accepts this cycle's process events for suspicious-service
    # checks, in addition to the firewall/port events already passed.
    cycle_result["vulnerabilities"] = vulnerability_scan.scan(
        cycle_result.get("firewall_events", []),
        cycle_result.get("open_ports", []),
        cycle_result.get("processes", []),
    )
    if intrusion_detection is not None:
        cycle_result["intrusions"] = intrusion_detection.detect_intrusions(cycle_result)
    else:
        cycle_result["intrusions"] = []
        logger.debug("intrusion_detection module unavailable; skipping intrusion analysis this cycle.")

    # ------------------------------------------------------------
    # Phase 3 - explainable AI security layer. Each module below
    # consumes only what has already been produced above in this same
    # cycle_result (threats, intrusions, vulnerabilities) - none of
    # them re-collect or re-detect anything themselves.
    # ------------------------------------------------------------
    if threat_classifier is not None:
        try:
            cycle_result["threat_classifications"] = threat_classifier.classify_threats(
                cycle_result.get("threats", [])
            )
        except Exception:
            cycle_result["threat_classifications"] = []
            logger.exception("threat_classifier failed this cycle.")
    else:
        cycle_result["threat_classifications"] = []
        logger.debug("threat_classifier module unavailable; skipping classification this cycle.")

    if security_score is not None:
        try:
            cycle_result["security_score"] = security_score.compute_security_score(cycle_result)
        except Exception:
            cycle_result["security_score"] = None
            logger.exception("security_score computation failed this cycle.")
    else:
        cycle_result["security_score"] = None
        logger.debug("security_score module unavailable; skipping scoring this cycle.")

    if attack_patterns is not None:
        try:
            attack_patterns.run_cycle(cycle_result)
        except Exception:
            cycle_result["attack_patterns"] = []
            logger.exception("attack_patterns analysis failed this cycle.")
    else:
        cycle_result["attack_patterns"] = []
        logger.debug("attack_patterns module unavailable; skipping pattern analysis this cycle.")

    if security_recommendations is not None:
        try:
            security_recommendations.run_cycle(cycle_result)
        except Exception:
            cycle_result["security_recommendations"] = []
            logger.exception("security_recommendations generation failed this cycle.")
    else:
        cycle_result["security_recommendations"] = []
        logger.debug("security_recommendations module unavailable; skipping recommendations this cycle.")

    # ------------------------------------------------------------
    # Phase 4 - incident management + historical reporting. Consumes
    # only what has already been produced above in this same
    # cycle_result; performs no detection, scoring, or confirmation
    # logic of its own.
    # ------------------------------------------------------------
    _record_confirmed_incidents(cycle_result)

    return cycle_result


def get_status() -> dict[str, Any]:
    """Live status for FastAPI/dashboard exposure, combining engine and threat-detector state."""
    status = security_engine.get_security_status()
    status["threat_summary"] = get_threat_summary()
    status["active"] = _active
    if attack_patterns is not None and hasattr(attack_patterns, "get_status"):
        status["attack_patterns"] = attack_patterns.get_status()
    if security_recommendations is not None and hasattr(security_recommendations, "get_status"):
        status["security_recommendations"] = security_recommendations.get_status()
    if incident_logger is not None and hasattr(incident_logger, "get_incident_summary"):
        status["incident_summary"] = incident_logger.get_incident_summary()
    if security_history is not None and hasattr(security_history, "get_status"):
        status["security_history"] = security_history.get_status()
    return status