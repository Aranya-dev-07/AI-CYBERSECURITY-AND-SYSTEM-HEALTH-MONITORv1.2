from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger

logger = get_logger("lavender_trinetra.cybersecurity.threat_classifier")

MAX_CLASSIFICATION_HISTORY = int(getattr(settings, "THREAT_CLASSIFIER_HISTORY_SIZE", 500))


class ThreatCategory:
    RESOURCE_ABUSE = "Resource Abuse"
    NETWORK_THREAT = "Network Threat"
    INTRUSION = "Intrusion"
    FIREWALL_RISK = "Firewall Risk"
    VULNERABILITY = "Vulnerability"
    UNKNOWN = "Unknown"


_RESOURCE_KEYWORDS = re.compile(r"cpu|memory|ram|resource", re.IGNORECASE)
_LOGIN_KEYWORDS = re.compile(r"login|session|logon|credential|authentication", re.IGNORECASE)
_SCAN_KEYWORDS = re.compile(r"scan|repeated connection|brute", re.IGNORECASE)

# Maps a threat_detector.py subsystem directly onto a classification
# category when no more specific signal overrides it.
_SUBSYSTEM_DEFAULT_CATEGORY = {
    "process": ThreatCategory.RESOURCE_ABUSE,
    "network": ThreatCategory.NETWORK_THREAT,
    "port": ThreatCategory.VULNERABILITY,
    "firewall": ThreatCategory.FIREWALL_RISK,
    "session": ThreatCategory.INTRUSION,
    "correlated": ThreatCategory.INTRUSION,
}

_SEVERITY_CONFIDENCE_BONUS = {"Low": 0.0, "Medium": 0.05, "High": 0.1, "Critical": 0.15}


@dataclass
class ThreatClassification:
    classification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    threat_id: Optional[str] = None
    category: str = ThreatCategory.UNKNOWN
    severity: str = "Low"
    confidence: float = 0.4
    summary: str = ""
    matched_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification_id": self.classification_id,
            "timestamp": self.timestamp,
            "threat_id": self.threat_id,
            "category": self.category,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "summary": self.summary,
            "matched_signals": self.matched_signals,
        }


# ---------------------------------------------------------------------
# In-memory recent-classification buffer (until security_logger.py
# provides PostgreSQL persistence). This module never writes to the
# database directly, consistent with security_engine.py's ownership
# model - security_logger.record_cycle() is expected to persist
# whatever is attached to cycle_result by the caller.
# ---------------------------------------------------------------------
_lock = threading.Lock()
_recent_classifications: list[ThreatClassification] = []


def _record(classifications: list[ThreatClassification]) -> None:
    if not classifications:
        return
    with _lock:
        _recent_classifications.extend(classifications)
        overflow = len(_recent_classifications) - MAX_CLASSIFICATION_HISTORY
        if overflow > 0:
            del _recent_classifications[:overflow]


def _classify_one(threat: dict[str, Any]) -> ThreatClassification:
    """
    Classifies a single threat_detector.py Threat dict into a category
    with an explainable confidence score. Rule-based only - this
    reinterprets a threat that has already been detected upstream, it
    does not independently decide whether something is a threat.
    """
    subsystem = str(threat.get("subsystem", "")).lower()
    severity = threat.get("severity", "Low")
    reason = threat.get("reason", "") or ""
    title = threat.get("title", "") or ""
    correlated = threat.get("correlated_subsystems") or []
    text = f"{title} {reason}"

    matched_signals: list[str] = []
    category = _SUBSYSTEM_DEFAULT_CATEGORY.get(subsystem, ThreatCategory.UNKNOWN)
    if subsystem in _SUBSYSTEM_DEFAULT_CATEGORY:
        matched_signals.append(f"subsystem={subsystem}")

    # Keyword-based refinement can override the subsystem default when
    # the language of the threat more specifically indicates another
    # category (e.g. a "process" threat whose reason is actually about
    # a failed login attempt tied to that process).
    if _RESOURCE_KEYWORDS.search(text):
        category = ThreatCategory.RESOURCE_ABUSE
        matched_signals.append("keyword=resource_usage")
    elif _SCAN_KEYWORDS.search(text):
        category = ThreatCategory.INTRUSION
        matched_signals.append("keyword=scan_or_brute_force")
    elif _LOGIN_KEYWORDS.search(text):
        category = ThreatCategory.INTRUSION
        matched_signals.append("keyword=login_or_session")

    if correlated:
        category = ThreatCategory.INTRUSION
        matched_signals.append(f"correlated_with={','.join(correlated)}")

    # Base confidence reflects how many independent signals agree;
    # severity adds a small bonus since more severe findings tend to
    # be less ambiguous (e.g. a Critical masquerading process is
    # rarely a false categorization).
    base_confidence = 0.5 + 0.15 * (len(matched_signals) - 1) if matched_signals else 0.35
    confidence = min(1.0, base_confidence + _SEVERITY_CONFIDENCE_BONUS.get(severity, 0.0))

    summary = (
        f"Classified as {category} with {confidence * 100:.0f}% confidence "
        f"based on {', '.join(matched_signals) if matched_signals else 'no strong signals (defaulted)'}."
    )

    return ThreatClassification(
        threat_id=threat.get("threat_id"),
        category=category,
        severity=severity,
        confidence=confidence,
        summary=summary,
        matched_signals=matched_signals,
    )


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def classify_threats(threats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Classifies a list of threats already produced by
    threat_detector.py's detect_threats()/run_cycle() into
    Resource Abuse / Network Threat / Intrusion / Firewall Risk /
    Vulnerability / Unknown, each with a severity, confidence value
    and an explainable summary. Performs no new threat detection -
    every input is assumed to already be a confirmed threat.
    """
    try:
        threats = threats or []
        classifications = [_classify_one(t) for t in threats]

        if classifications:
            category_counts: dict[str, int] = {}
            for c in classifications:
                category_counts[c.category] = category_counts.get(c.category, 0) + 1
            logger.info(
                "Classified %d threat(s): %s",
                len(classifications),
                ", ".join(f"{cat}={count}" for cat, count in sorted(category_counts.items())),
            )
        else:
            logger.debug("Threat classifier: no threats to classify this cycle.")

        _record(classifications)
        return [c.to_dict() for c in classifications]
    except Exception as exc:
        logger.exception("Threat classification failed: %s", exc)
        return []


def get_recent_classifications(limit: int = 100) -> list[dict[str, Any]]:
    """Returns the most recent classifications, newest first. For FastAPI exposure."""
    with _lock:
        items = list(_recent_classifications[-limit:])
    items.reverse()
    return [c.to_dict() for c in items]


def get_classification_summary() -> dict[str, Any]:
    """Returns counts of recent classifications by category. For FastAPI/dashboard exposure."""
    with _lock:
        items = list(_recent_classifications)
    counts = {
        ThreatCategory.RESOURCE_ABUSE: 0,
        ThreatCategory.NETWORK_THREAT: 0,
        ThreatCategory.INTRUSION: 0,
        ThreatCategory.FIREWALL_RISK: 0,
        ThreatCategory.VULNERABILITY: 0,
        ThreatCategory.UNKNOWN: 0,
    }
    for c in items:
        if c.category in counts:
            counts[c.category] += 1
    return {
        "total": len(items),
        "counts": counts,
        "generated_at": datetime.utcnow().isoformat(),
    }