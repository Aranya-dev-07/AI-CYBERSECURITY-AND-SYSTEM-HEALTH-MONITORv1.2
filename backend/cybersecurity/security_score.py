from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger

logger = get_logger("lavender_trinetra.cybersecurity.security_score")

MAX_SCORE_HISTORY = int(getattr(settings, "SECURITY_SCORE_HISTORY_SIZE", 500))

# ---------------------------------------------------------------------
# Category weights - the maximum points each factor can deduct from a
# perfect 100. Weights sum to 100 so a system failing every category
# completely bottoms out at 0, not below.
# ---------------------------------------------------------------------
CATEGORY_WEIGHTS = dict(
    getattr(
        settings,
        "SECURITY_SCORE_CATEGORY_WEIGHTS",
        {
            "active_threats": 30,
            "firewall_status": 15,
            "open_ports": 15,
            "network_activity": 10,
            "vulnerabilities": 20,
            "active_sessions": 10,
        },
    )
)

_SEVERITY_WEIGHT = {"Low": 1, "Medium": 2, "High": 4, "Critical": 8}


class SecurityGrade:
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    CRITICAL = "Critical"


def _grade_for_score(score: float) -> str:
    if score >= 90:
        return SecurityGrade.EXCELLENT
    if score >= 75:
        return SecurityGrade.GOOD
    if score >= 55:
        return SecurityGrade.FAIR
    if score >= 35:
        return SecurityGrade.POOR
    return SecurityGrade.CRITICAL


@dataclass
class ScoreFactor:
    category: str
    weight: float
    deduction: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "weight": self.weight,
            "deduction": round(self.deduction, 2),
            "reason": self.reason,
        }


@dataclass
class SecurityScoreResult:
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    score: float = 100.0
    grade: str = SecurityGrade.EXCELLENT
    factors: list[ScoreFactor] = field(default_factory=list)
    delta: Optional[float] = None
    delta_explanation: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "score": round(self.score, 2),
            "grade": self.grade,
            "factors": [f.to_dict() for f in self.factors],
            "delta": round(self.delta, 2) if self.delta is not None else None,
            "delta_explanation": self.delta_explanation,
        }


# ---------------------------------------------------------------------
# In-memory recent-score buffer (until security_logger.py provides
# PostgreSQL persistence). This module never writes to the database
# directly, consistent with security_engine.py's ownership model -
# security_logger.record_cycle() is expected to persist whatever is
# attached to cycle_result["security_score"] by the caller.
# ---------------------------------------------------------------------
_lock = threading.Lock()
_recent_scores: list[SecurityScoreResult] = []


def _record(result: SecurityScoreResult) -> None:
    with _lock:
        _recent_scores.append(result)
        overflow = len(_recent_scores) - MAX_SCORE_HISTORY
        if overflow > 0:
            del _recent_scores[:overflow]


def _last_score() -> Optional[SecurityScoreResult]:
    with _lock:
        return _recent_scores[-1] if _recent_scores else None


# ---------------------------------------------------------------------
# Per-category deduction calculators - each consumes the relevant
# slice of a threat_detector.run_cycle() cycle_result and returns a
# capped, explainable ScoreFactor. No scanning/detection happens here;
# this module only interprets results already produced upstream.
# ---------------------------------------------------------------------
def _score_active_threats(cycle_result: dict[str, Any]) -> ScoreFactor:
    weight = CATEGORY_WEIGHTS.get("active_threats", 30)
    threats = cycle_result.get("threats", []) or []

    if not threats:
        return ScoreFactor("active_threats", weight, 0.0, "No active threats detected this cycle.")

    severity_counts: dict[str, int] = {}
    weighted_total = 0
    for t in threats:
        sev = t.get("severity", "Low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        weighted_total += _SEVERITY_WEIGHT.get(sev, 1)

    # Scale so a handful of Critical threats alone can exhaust the
    # category weight, without a large pile of Low threats doing the
    # same - severity matters more than raw count.
    deduction = min(weight, weight * (weighted_total / 12.0))
    summary = ", ".join(f"{count} {sev}" for sev, count in sorted(severity_counts.items()))
    return ScoreFactor(
        "active_threats", weight, deduction,
        f"{len(threats)} active threat(s) this cycle ({summary}).",
    )


def _score_firewall_status(cycle_result: dict[str, Any]) -> ScoreFactor:
    weight = CATEGORY_WEIGHTS.get("firewall_status", 15)
    firewall_events = cycle_result.get("firewall_events", []) or []
    status = next((e for e in firewall_events if e.get("type") == "firewall_status"), None)

    if status is None:
        return ScoreFactor("firewall_status", weight, weight * 0.5, "Firewall status could not be determined.")

    if not status.get("available", True):
        return ScoreFactor(
            "firewall_status", weight, weight * 0.75,
            "Firewall management interface is unavailable.",
        )
    if not status.get("enabled", True):
        return ScoreFactor("firewall_status", weight, weight, "Firewall is disabled.")

    return ScoreFactor("firewall_status", weight, 0.0, "Firewall is enabled and reachable.")


def _score_open_ports(cycle_result: dict[str, Any]) -> ScoreFactor:
    weight = CATEGORY_WEIGHTS.get("open_ports", 15)
    vulnerabilities = cycle_result.get("vulnerabilities", []) or []
    port_findings = [v for v in vulnerabilities if v.get("category") == "open_ports"]

    if not port_findings:
        return ScoreFactor("open_ports", weight, 0.0, "No insecure or excessive open-port findings this cycle.")

    weighted_total = sum(_SEVERITY_WEIGHT.get(f.get("severity", "Low"), 1) for f in port_findings)
    deduction = min(weight, weight * (weighted_total / 10.0))
    return ScoreFactor(
        "open_ports", weight, deduction,
        f"{len(port_findings)} open-port finding(s) flagged by the vulnerability scan.",
    )


def _score_network_activity(cycle_result: dict[str, Any]) -> ScoreFactor:
    weight = CATEGORY_WEIGHTS.get("network_activity", 10)
    network_events = cycle_result.get("network_connections", []) or []

    flagged_connections = [
        e for e in network_events
        if e.get("type") == "connection" and str(e.get("risk_level", "none")).lower() != "none"
    ]
    traffic_spikes = [
        e for e in network_events
        if e.get("type") == "traffic_io" and str(e.get("risk_level", "none")).lower() != "none"
    ]

    if not flagged_connections and not traffic_spikes:
        return ScoreFactor("network_activity", weight, 0.0, "Network activity within normal bounds.")

    deduction = min(weight, weight * 0.4 * len(flagged_connections) + (weight * 0.5 if traffic_spikes else 0))
    parts = []
    if flagged_connections:
        parts.append(f"{len(flagged_connections)} flagged connection(s)")
    if traffic_spikes:
        parts.append("abnormal traffic volume")
    return ScoreFactor("network_activity", weight, deduction, "; ".join(parts) + " detected this cycle.")


def _score_vulnerabilities(cycle_result: dict[str, Any]) -> ScoreFactor:
    weight = CATEGORY_WEIGHTS.get("vulnerabilities", 20)
    vulnerabilities = cycle_result.get("vulnerabilities", []) or []

    if not vulnerabilities:
        return ScoreFactor("vulnerabilities", weight, 0.0, "No vulnerability findings this cycle.")

    weighted_total = sum(_SEVERITY_WEIGHT.get(v.get("severity", "Low"), 1) for v in vulnerabilities)
    deduction = min(weight, weight * (weighted_total / 16.0))
    severity_counts: dict[str, int] = {}
    for v in vulnerabilities:
        sev = v.get("severity", "Low")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
    summary = ", ".join(f"{count} {sev}" for sev, count in sorted(severity_counts.items()))
    return ScoreFactor(
        "vulnerabilities", weight, deduction,
        f"{len(vulnerabilities)} vulnerability finding(s) ({summary}).",
    )


def _score_active_sessions(cycle_result: dict[str, Any]) -> ScoreFactor:
    weight = CATEGORY_WEIGHTS.get("active_sessions", 10)
    session_events = cycle_result.get("sessions", []) or []

    flagged_sessions = [
        e for e in session_events
        if e.get("type") == "session_active" and str(e.get("risk_level", "none")).lower() != "none"
    ]
    failed_logins = [
        e for e in session_events
        if e.get("type") == "session_login" and str(e.get("status", "")).lower() in ("failed", "denied", "locked_out")
    ]

    if not flagged_sessions and not failed_logins:
        return ScoreFactor("active_sessions", weight, 0.0, "No suspicious session activity this cycle.")

    deduction = min(weight, weight * 0.5 * len(flagged_sessions) + weight * 0.2 * len(failed_logins))
    parts = []
    if flagged_sessions:
        parts.append(f"{len(flagged_sessions)} flagged session(s)")
    if failed_logins:
        parts.append(f"{len(failed_logins)} failed login attempt(s)")
    return ScoreFactor("active_sessions", weight, deduction, "; ".join(parts) + " detected this cycle.")


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def compute_security_score(cycle_result: dict[str, Any]) -> dict[str, Any]:
    """
    Computes an explainable 0-100 Security Score from one
    threat_detector.run_cycle() cycle_result (expected to already
    contain processes, network_connections, open_ports,
    firewall_events, sessions, threats, vulnerabilities, and
    optionally process_alerts/intrusions). Performs no detection of
    its own - purely interprets results already produced upstream by
    security_engine.py, threat_detector.py, suspicious_process.py,
    intrusion_detector.py and vulnerability_scan.py.
    """
    try:
        factors = [
            _score_active_threats(cycle_result),
            _score_firewall_status(cycle_result),
            _score_open_ports(cycle_result),
            _score_network_activity(cycle_result),
            _score_vulnerabilities(cycle_result),
            _score_active_sessions(cycle_result),
        ]

        total_deduction = sum(f.deduction for f in factors)
        score = max(0.0, min(100.0, 100.0 - total_deduction))
        grade = _grade_for_score(score)

        previous = _last_score()
        delta = None
        delta_explanation = None
        if previous is not None:
            delta = score - previous.score
            if abs(delta) < 0.5:
                delta_explanation = "Security posture is stable compared to the previous cycle."
            else:
                direction = "improved" if delta > 0 else "declined"
                changed_factors = [
                    f.category for f in factors
                    if f.deduction > 0.5
                ]
                driver = f" (driven by: {', '.join(changed_factors)})" if changed_factors else ""
                delta_explanation = f"Score {direction} by {abs(delta):.1f} points since the last cycle{driver}."

        result = SecurityScoreResult(
            score=score,
            grade=grade,
            factors=factors,
            delta=delta,
            delta_explanation=delta_explanation,
        )

        logger.info("Security score computed: %.1f (%s)", score, grade)
        _record(result)
        return result.to_dict()
    except Exception as exc:
        logger.exception("Security score computation failed: %s", exc)
        return SecurityScoreResult(score=0.0, grade=SecurityGrade.CRITICAL, factors=[]).to_dict()


def get_latest_score() -> Optional[dict[str, Any]]:
    """Returns the most recently computed score. For FastAPI exposure."""
    result = _last_score()
    return result.to_dict() if result is not None else None


def get_score_history(limit: int = 100) -> list[dict[str, Any]]:
    """Returns recent scores, oldest first (suitable for trend charts). For FastAPI exposure."""
    with _lock:
        items = list(_recent_scores[-limit:])
    return [r.to_dict() for r in items]