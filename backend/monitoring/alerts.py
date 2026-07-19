"""
alerts.py

Alert Generation & Session Tracking — Lavender Trinetra Platform
=====================================================================

Generates threshold-based alerts from system metrics and maintains
in-memory statistics for the current monitoring session (total,
warning, and critical alert counts). Does NOT write to CSV directly —
session statistics are exposed to reports.py, which persists the
final summary via metrics.py.

Integrates with:
    - collector.py   (supplies metrics evaluated for alert conditions)
    - reports.py     (consumes get_alert_statistics() on session end)
    - main.py        (drives the monitoring loop; may reset the session)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("lavender_trinetra.monitoring.alerts")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class AlertLevel(str, Enum):
    INFO = "Info"
    WARNING = "Warning"
    CRITICAL = "Critical"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class AlertThresholds:
    """Threshold values (percent / bytes-per-second) used to trigger alerts."""

    cpu_warning: float = 75.0
    cpu_critical: float = 90.0

    ram_warning: float = 75.0
    ram_critical: float = 90.0

    disk_warning: float = 80.0
    disk_critical: float = 95.0

    network_warning_bps: float = 60_000_000.0   # 60 MB/s
    network_critical_bps: float = 100_000_000.0  # 100 MB/s


DEFAULT_THRESHOLDS = AlertThresholds()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class Alert:
    """A single generated alert."""

    alert_id: str
    timestamp: str
    metric: str
    level: str
    value: float
    threshold: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# =====================================================================
# SESSION TRACKER
# =====================================================================

class AlertSessionTracker:
    """
    Thread-safe in-memory tracker for alert counts and history across
    the current monitoring session. A new instance (or reset_session())
    should be used per monitoring session.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._alerts: list[Alert] = []
        self._total_count: int = 0
        self._warning_count: int = 0
        self._critical_count: int = 0
        self._session_start: datetime = datetime.utcnow()

    def reset_session(self) -> None:
        """Clear all tracked alerts and counters, starting a fresh session."""
        with self._lock:
            self._alerts.clear()
            self._total_count = 0
            self._warning_count = 0
            self._critical_count = 0
            self._session_start = datetime.utcnow()
        logger.info("Alert session reset.")

    def record(self, alert: Alert) -> None:
        """Record a generated alert and update session counters."""
        with self._lock:
            self._alerts.append(alert)
            self._total_count += 1
            if alert.level == AlertLevel.WARNING.value:
                self._warning_count += 1
            elif alert.level == AlertLevel.CRITICAL.value:
                self._critical_count += 1

    def get_statistics(self) -> dict[str, Any]:
        """
        Return current session alert statistics for reports.py.

        Returns:
            Dict with total_alerts, warning_alerts, critical_alerts,
            session_start, and the full alert history as dicts.
        """
        with self._lock:
            return {
                "total_alerts": self._total_count,
                "warning_alerts": self._warning_count,
                "critical_alerts": self._critical_count,
                "session_start": self._session_start.isoformat(),
                "alerts": [a.to_dict() for a in self._alerts],
            }

    def get_alerts(self) -> list[Alert]:
        """Return a snapshot copy of all alerts recorded this session."""
        with self._lock:
            return list(self._alerts)


# Module-wide singleton session tracker, shared across collector cycles
# within a single monitoring session (main.py owns its lifecycle via
# reset_session()).
_session_tracker = AlertSessionTracker()


def get_session_tracker() -> AlertSessionTracker:
    """Return the module-wide singleton AlertSessionTracker."""
    return _session_tracker


# =====================================================================
# ALERT GENERATION
# =====================================================================

def _evaluate_metric(
    metric_name: str,
    value: float,
    warning_threshold: float,
    critical_threshold: float,
    unit_label: str,
    timestamp: str,
) -> Optional[Alert]:
    """Evaluate a single metric against its warning/critical thresholds."""
    if value >= critical_threshold:
        level = AlertLevel.CRITICAL
        threshold = critical_threshold
    elif value >= warning_threshold:
        level = AlertLevel.WARNING
        threshold = warning_threshold
    else:
        return None

    message = (
        f"{metric_name.replace('_', ' ').title()} is at {value:.1f}{unit_label}, "
        f"exceeding the {level.value.lower()} threshold of {threshold:.1f}{unit_label}."
    )

    return Alert(
        alert_id=str(uuid.uuid4()),
        timestamp=timestamp,
        metric=metric_name,
        level=level.value,
        value=round(value, 2),
        threshold=threshold,
        message=message,
    )


def generate_alerts(
    cpu_usage: float,
    ram_usage: float,
    disk_usage: float,
    network_in_bps: float = 0.0,
    network_out_bps: float = 0.0,
    timestamp: Optional[str] = None,
    thresholds: AlertThresholds = DEFAULT_THRESHOLDS,
    tracker: Optional[AlertSessionTracker] = None,
) -> list[Alert]:
    """
    Evaluate current metrics against configured thresholds, generate
    any resulting alerts, and record them in the session tracker.

    Args:
        cpu_usage, ram_usage, disk_usage: Current usage percentages (0-100).
        network_in_bps, network_out_bps: Current network throughput.
        timestamp: ISO 8601 timestamp for generated alerts; defaults to now.
        thresholds: AlertThresholds instance.
        tracker: AlertSessionTracker to record into; defaults to the
            module-wide singleton.

    Returns:
        List of Alert objects generated this cycle (may be empty).
    """
    try:
        ts = timestamp or datetime.utcnow().isoformat()
        active_tracker = tracker or _session_tracker

        total_network_bps = network_in_bps + network_out_bps

        checks = [
            ("cpu_usage", cpu_usage, thresholds.cpu_warning, thresholds.cpu_critical, "%"),
            ("ram_usage", ram_usage, thresholds.ram_warning, thresholds.ram_critical, "%"),
            ("disk_usage", disk_usage, thresholds.disk_warning, thresholds.disk_critical, "%"),
            ("network_usage", total_network_bps, thresholds.network_warning_bps,
             thresholds.network_critical_bps, " B/s"),
        ]

        generated: list[Alert] = []
        for metric_name, value, warn_th, crit_th, unit in checks:
            alert = _evaluate_metric(metric_name, value, warn_th, crit_th, unit, ts)
            if alert:
                generated.append(alert)
                active_tracker.record(alert)
                logger.warning("Alert generated: %s", alert.message)

        return generated

    except Exception as exc:
        logger.exception("Alert generation failed: %s", exc)
        return []


# =====================================================================
# PUBLIC ACCESSORS (for reports.py / main.py / api)
# =====================================================================

def get_alert_statistics(tracker: Optional[AlertSessionTracker] = None) -> dict[str, Any]:
    """
    Return the current session's alert statistics. Primary integration
    point for reports.py when generating the end-of-session summary.
    """
    active_tracker = tracker or _session_tracker
    return active_tracker.get_statistics()


def reset_alert_session(tracker: Optional[AlertSessionTracker] = None) -> None:
    """Reset alert counters/history for a new monitoring session."""
    active_tracker = tracker or _session_tracker
    active_tracker.reset_session()


__all__ = [
    "AlertLevel",
    "AlertThresholds",
    "DEFAULT_THRESHOLDS",
    "Alert",
    "AlertSessionTracker",
    "get_session_tracker",
    "generate_alerts",
    "get_alert_statistics",
    "reset_alert_session",
]