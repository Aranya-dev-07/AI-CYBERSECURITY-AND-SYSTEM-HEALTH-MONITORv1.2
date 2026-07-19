from __future__ import annotations

import re
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger

logger = get_logger("lavender_trinetra.cybersecurity.suspicious_process")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------
CPU_EXCESSIVE_THRESHOLD = float(getattr(settings, "PROCESS_CPU_SUSPICION_THRESHOLD", 85.0))
RAM_EXCESSIVE_THRESHOLD = float(getattr(settings, "PROCESS_RAM_SUSPICION_THRESHOLD", 80.0))

RAPID_CREATION_WINDOW_SECONDS = float(getattr(settings, "PROCESS_RAPID_CREATION_WINDOW_SECONDS", 10.0))
RAPID_CREATION_COUNT_THRESHOLD = int(getattr(settings, "PROCESS_RAPID_CREATION_COUNT_THRESHOLD", 8))

# Process names commonly spoofed/masqueraded by malware when run from a
# non-standard location.
SPOOFABLE_SYSTEM_NAMES = frozenset(
    getattr(
        settings,
        "PROCESS_SPOOFABLE_SYSTEM_NAMES",
        {"svchost.exe", "explorer.exe", "lsass.exe", "csrss.exe", "winlogon.exe", "services.exe", "systemd", "init"},
    )
)
EXPECTED_SYSTEM_DIRS = tuple(
    getattr(
        settings,
        "PROCESS_EXPECTED_SYSTEM_DIRS",
        ("C:\\Windows\\System32", "C:\\Windows\\SysWOW64", "/usr/sbin", "/sbin", "/usr/bin", "/bin"),
    )
)

# A random-looking name: long run of mixed alphanumerics with no vowels
# or dictionary-like structure - a weak heuristic, intentionally
# conservative to minimize false positives without an AI layer.
_RANDOM_NAME_PATTERN = re.compile(r"^[a-z0-9]{10,}$", re.IGNORECASE)
_VOWEL_PATTERN = re.compile(r"[aeiouAEIOU]")


class ProcessAlertSeverity:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


@dataclass
class ProcessAlert:
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    pid: Optional[int] = None
    process_name: Optional[str] = None
    category: str = ""
    severity: str = ProcessAlertSeverity.LOW
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "pid": self.pid,
            "process_name": self.process_name,
            "category": self.category,
            "severity": self.severity,
            "reason": self.reason,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------
# State tracked across calls (rapid process creation window, seen pids)
# ---------------------------------------------------------------------
_lock = threading.Lock()
_creation_events: deque = deque()  # (pid, datetime)
_known_pids: set[int] = set()
_recent_alerts: deque = deque(maxlen=int(getattr(settings, "SUSPICIOUS_PROCESS_HISTORY_SIZE", 500)))


def _looks_random(name: str) -> bool:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if len(stem) < 10:
        return False
    if _VOWEL_PATTERN.search(stem):
        return False
    return bool(_RANDOM_NAME_PATTERN.match(stem))


def _is_expected_system_dir(exe: Optional[str]) -> bool:
    if not exe:
        return False
    return any(exe.lower().startswith(d.lower()) for d in EXPECTED_SYSTEM_DIRS)


# ---------------------------------------------------------------------
# Individual detectors - each takes one process observation dict (the
# shape produced by process_monitor.py's ProcessObservation.to_dict())
# and returns zero or more alerts. No psutil calls happen here; this
# module only re-analyzes data process_monitor.py already collected,
# avoiding a duplicate scan.
# ---------------------------------------------------------------------
def _check_excessive_cpu(proc: dict[str, Any]) -> list[ProcessAlert]:
    cpu = float(proc.get("cpu_percent") or 0.0)
    if cpu < CPU_EXCESSIVE_THRESHOLD:
        return []
    severity = ProcessAlertSeverity.CRITICAL if cpu >= 95.0 else ProcessAlertSeverity.HIGH
    return [
        ProcessAlert(
            pid=proc.get("pid"),
            process_name=proc.get("name"),
            category="excessive_cpu",
            severity=severity,
            reason=f"Process is consuming {cpu:.1f}% CPU, exceeding the {CPU_EXCESSIVE_THRESHOLD:.0f}% threshold.",
            evidence={"cpu_percent": cpu},
        )
    ]


def _check_excessive_ram(proc: dict[str, Any]) -> list[ProcessAlert]:
    ram = float(proc.get("memory_percent") or 0.0)
    if ram < RAM_EXCESSIVE_THRESHOLD:
        return []
    severity = ProcessAlertSeverity.CRITICAL if ram >= 95.0 else ProcessAlertSeverity.HIGH
    return [
        ProcessAlert(
            pid=proc.get("pid"),
            process_name=proc.get("name"),
            category="excessive_ram",
            severity=severity,
            reason=f"Process is consuming {ram:.1f}% memory, exceeding the {RAM_EXCESSIVE_THRESHOLD:.0f}% threshold.",
            evidence={"memory_percent": ram},
        )
    ]


def _check_unusual_name(proc: dict[str, Any]) -> list[ProcessAlert]:
    name = (proc.get("name") or "").strip()
    exe = proc.get("exe")
    alerts: list[ProcessAlert] = []

    if name.lower() in {n.lower() for n in SPOOFABLE_SYSTEM_NAMES} and not _is_expected_system_dir(exe):
        alerts.append(
            ProcessAlert(
                pid=proc.get("pid"),
                process_name=name,
                category="masquerading",
                severity=ProcessAlertSeverity.CRITICAL,
                reason=(
                    f"Process name '{name}' matches a common system process, but is executing "
                    f"from an unexpected location: {exe or 'unknown path'}."
                ),
                evidence={"exe": exe},
            )
        )

    if _looks_random(name):
        alerts.append(
            ProcessAlert(
                pid=proc.get("pid"),
                process_name=name,
                category="unusual_name",
                severity=ProcessAlertSeverity.LOW,
                reason=f"Process name '{name}' has an unusually random-looking structure.",
                evidence={"exe": exe},
            )
        )

    return alerts


def _check_zombie_or_orphan(proc: dict[str, Any]) -> list[ProcessAlert]:
    alerts: list[ProcessAlert] = []
    status = (proc.get("status") or "").lower()

    if status == "zombie":
        alerts.append(
            ProcessAlert(
                pid=proc.get("pid"),
                process_name=proc.get("name"),
                category="zombie_process",
                severity=ProcessAlertSeverity.LOW,
                reason="Process is in a zombie state and has not been reaped by its parent.",
                evidence={"status": status, "parent_pid": proc.get("parent_pid")},
            )
        )

    parent_pid = proc.get("parent_pid")
    name = (proc.get("name") or "").lower()
    if parent_pid in (None, 0) and name not in {"systemd", "init", "kernel_task", "wininit.exe"}:
        alerts.append(
            ProcessAlert(
                pid=proc.get("pid"),
                process_name=proc.get("name"),
                category="orphan_process",
                severity=ProcessAlertSeverity.MEDIUM,
                reason="Process has no identifiable parent process (orphaned).",
                evidence={"parent_pid": parent_pid},
            )
        )

    return alerts


def _check_rapid_creation(process_observations: list[dict[str, Any]]) -> list[ProcessAlert]:
    """
    Tracks newly-seen pids across calls in a rolling time window and
    flags a burst of process creation as a single system-level alert
    rather than per-process, since the signal is the rate itself.
    """
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=RAPID_CREATION_WINDOW_SECONDS)

    with _lock:
        current_pids = {p.get("pid") for p in process_observations if p.get("pid") is not None}
        new_pids = current_pids - _known_pids
        _known_pids.clear()
        _known_pids.update(current_pids)

        for pid in new_pids:
            _creation_events.append((pid, now))

        while _creation_events and _creation_events[0][1] < window_start:
            _creation_events.popleft()

        creation_count = len(_creation_events)

    if creation_count >= RAPID_CREATION_COUNT_THRESHOLD:
        return [
            ProcessAlert(
                pid=None,
                process_name=None,
                category="rapid_process_creation",
                severity=ProcessAlertSeverity.HIGH,
                reason=(
                    f"{creation_count} new processes were created within the last "
                    f"{RAPID_CREATION_WINDOW_SECONDS:.0f} seconds, exceeding the "
                    f"{RAPID_CREATION_COUNT_THRESHOLD} threshold."
                ),
                evidence={"creation_count": creation_count, "window_seconds": RAPID_CREATION_WINDOW_SECONDS},
            )
        ]
    return []


def _record(alerts: list[ProcessAlert]) -> None:
    if not alerts:
        return
    with _lock:
        _recent_alerts.extend(alerts)


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def analyze(process_observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Runs all rule-based process suspicion checks against the process
    observations already collected by process_monitor.py this cycle
    (via security_engine.py) and returns a list of explainable alert
    dicts. Does not call psutil itself - avoids a duplicate scan of
    the process table.
    """
    try:
        process_observations = process_observations or []
        alerts: list[ProcessAlert] = []

        for proc in process_observations:
            alerts.extend(_check_excessive_cpu(proc))
            alerts.extend(_check_excessive_ram(proc))
            alerts.extend(_check_unusual_name(proc))
            alerts.extend(_check_zombie_or_orphan(proc))

        alerts.extend(_check_rapid_creation(process_observations))

        if alerts:
            logger.warning(
                "Suspicious process analysis raised %d alert(s) across %d process(es).",
                len(alerts), len(process_observations),
            )
        else:
            logger.debug(
                "Suspicious process analysis complete: %d process(es) checked, no alerts.",
                len(process_observations),
            )

        _record(alerts)
        return [a.to_dict() for a in alerts]
    except Exception as exc:
        logger.exception("Suspicious process analysis failed: %s", exc)
        return []


def get_recent_alerts(limit: int = 100) -> list[dict[str, Any]]:
    """Returns the most recent suspicious-process alerts, newest first. For FastAPI exposure."""
    with _lock:
        items = list(_recent_alerts)[-limit:]
    items.reverse()
    return [a.to_dict() for a in items]