from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import psutil

from backend.config import settings
from backend.core import get_logger, safe_call

logger = get_logger("lavender_trinetra.cybersecurity.process_monitor")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------
CPU_SUSPICION_THRESHOLD = float(getattr(settings, "PROCESS_CPU_SUSPICION_THRESHOLD", 85.0))
RAM_SUSPICION_THRESHOLD = float(getattr(settings, "PROCESS_RAM_SUSPICION_THRESHOLD", 80.0))

# Directories processes are not normally expected to execute from.
SUSPICIOUS_EXEC_DIRS = tuple(
    getattr(
        settings,
        "PROCESS_SUSPICIOUS_EXEC_DIRS",
        (
            os.path.join(os.sep, "tmp"),
            os.environ.get("TEMP", ""),
            os.environ.get("TMP", ""),
            os.path.join(os.sep, "dev", "shm"),
        ),
    )
)
SUSPICIOUS_EXEC_DIRS = tuple(d for d in SUSPICIOUS_EXEC_DIRS if d)

# Process names commonly abused for masquerading (case-insensitive,
# compared against the reported process name only - not a definitive
# signal on its own, just a contributing factor).
WATCHED_PROCESS_NAMES = frozenset(
    getattr(
        settings,
        "PROCESS_WATCHED_NAMES",
        {"nc", "ncat", "netcat", "mimikatz", "psexec", "certutil", "powershell", "wscript", "cscript"},
    )
)


class ProcessRiskLevel:
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ProcessObservation:
    pid: int
    name: str
    status: Optional[str] = None
    username: Optional[str] = None
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    exe: Optional[str] = None
    cmdline: str = ""
    parent_pid: Optional[int] = None
    created_at: Optional[str] = None
    risk_level: str = ProcessRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "status": self.status,
            "username": self.username,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "exe": self.exe,
            "cmdline": self.cmdline,
            "parent_pid": self.parent_pid,
            "created_at": self.created_at,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


def _is_suspicious_exec_dir(exe: Optional[str]) -> bool:
    if not exe:
        return False
    return any(exe.startswith(d) for d in SUSPICIOUS_EXEC_DIRS if d)


def _assess_risk(obs: ProcessObservation) -> None:
    """
    Rule-based risk assessment. This is intentionally simple and
    transparent - the AI layer (outside this module's scope) is
    responsible for deeper correlation, explanation and prioritization.
    """
    reasons: list[str] = []

    if obs.cpu_percent >= CPU_SUSPICION_THRESHOLD:
        reasons.append(f"Sustained high CPU usage ({obs.cpu_percent:.1f}%)")

    if obs.memory_percent >= RAM_SUSPICION_THRESHOLD:
        reasons.append(f"Sustained high memory usage ({obs.memory_percent:.1f}%)")

    if obs.name and obs.name.lower() in WATCHED_PROCESS_NAMES:
        reasons.append(f"Process name '{obs.name}' is on the watch list")

    if _is_suspicious_exec_dir(obs.exe):
        reasons.append(f"Executing from an unusual location: {obs.exe}")

    if obs.parent_pid in (None, 0, 1) and obs.name and obs.name.lower() not in {"systemd", "init", "kernel_task"}:
        reasons.append("Process has no identifiable normal parent")

    obs.risk_reasons = reasons

    if not reasons:
        obs.risk_level = ProcessRiskLevel.NONE
    elif len(reasons) == 1:
        obs.risk_level = ProcessRiskLevel.LOW
    elif len(reasons) == 2:
        obs.risk_level = ProcessRiskLevel.MEDIUM
    else:
        obs.risk_level = ProcessRiskLevel.HIGH


def _observe_process(proc: "psutil.Process") -> Optional[ProcessObservation]:
    try:
        with proc.oneshot():
            info = proc.as_dict(
                attrs=[
                    "pid", "name", "status", "username",
                    "cpu_percent", "memory_percent", "exe",
                    "cmdline", "ppid", "create_time",
                ]
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    except Exception as exc:
        logger.debug("Failed to inspect process %s: %s", getattr(proc, "pid", "?"), exc)
        return None

    created_at = None
    if info.get("create_time"):
        created_at = datetime.utcfromtimestamp(info["create_time"]).isoformat()

    obs = ProcessObservation(
        pid=info.get("pid"),
        name=info.get("name") or "unknown",
        status=info.get("status"),
        username=info.get("username"),
        cpu_percent=float(info.get("cpu_percent") or 0.0),
        memory_percent=float(info.get("memory_percent") or 0.0),
        exe=info.get("exe"),
        cmdline=" ".join(info.get("cmdline") or []),
        parent_pid=info.get("ppid"),
        created_at=created_at,
    )
    _assess_risk(obs)
    return obs


def _observe_from_rows(process_rows: list[dict[str, Any]]) -> list[ProcessObservation]:
    """
    Builds observations from process rows already collected by
    monitoring/processes.py for this cycle, avoiding a second full
    psutil.process_iter() pass when the caller (security_engine.py via
    main.py) already has that data on hand.
    """
    observations: list[ProcessObservation] = []
    for row in process_rows:
        obs = ProcessObservation(
            pid=row.get("pid"),
            name=row.get("name") or "unknown",
            cpu_percent=float(row.get("cpu_percent") or 0.0),
            memory_percent=float(row.get("memory_percent") or 0.0),
        )
        # Enrich with security-relevant fields not present in the
        # lightweight monitoring row, when the process is still alive.
        with_extra = safe_call(psutil.Process, obs.pid)
        if with_extra is not None:
            try:
                obs.exe = safe_call(with_extra.exe)
                obs.username = safe_call(with_extra.username)
                obs.parent_pid = safe_call(with_extra.ppid)
                cmdline = safe_call(with_extra.cmdline)
                obs.cmdline = " ".join(cmdline) if cmdline else ""
            except Exception as exc:
                logger.debug("Failed to enrich process %s: %s", obs.pid, exc)
        _assess_risk(obs)
        observations.append(obs)
    return observations


def scan(process_rows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """
    Performs one process security scan and returns a list of process
    observation dicts, each with an assigned risk_level and
    risk_reasons. Called by security_engine.py once per security cycle.

    If process_rows is provided (the same rows main.py already collected
    for this monitoring cycle via monitoring/processes.py), those are
    reused and enriched rather than re-scanning every process from
    scratch - keeping this module in sync with the rest of the pipeline
    without duplicating collection work.
    """
    try:
        if process_rows:
            observations = _observe_from_rows(process_rows)
        else:
            observations = []
            for proc in psutil.process_iter():
                obs = _observe_process(proc)
                if obs is not None:
                    observations.append(obs)

        suspicious = [o for o in observations if o.risk_level != ProcessRiskLevel.NONE]
        if suspicious:
            logger.warning(
                "Process scan flagged %d suspicious process(es) out of %d observed.",
                len(suspicious), len(observations),
            )
        else:
            logger.debug("Process scan complete: %d processes observed, none flagged.", len(observations))

        return [o.to_dict() for o in observations]
    except Exception as exc:
        logger.exception("Process monitor scan failed: %s", exc)
        return []


def get_suspicious_processes(process_rows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Convenience wrapper returning only flagged processes."""
    return [p for p in scan(process_rows) if p["risk_level"] != ProcessRiskLevel.NONE]