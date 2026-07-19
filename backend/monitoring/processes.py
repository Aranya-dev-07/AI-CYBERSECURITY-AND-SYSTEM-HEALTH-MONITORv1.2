"""
processes.py

Top-Process Collector — Lavender Trinetra Platform
=====================================================================

Continuously collects the top 5 resource-consuming processes using
psutil, forwards each snapshot to metrics.py for immediate CSV
persistence, and returns structured process data for downstream
consumption (ai_engine.py, api/routes.py, dashboard.py).

Integrates with:
    - metrics.py    (sole CSV writer — processes.py never writes to disk directly)
    - main.py       (drives the monitoring loop)
    - ai/root_cause.py / ai/anomaly_detection.py (consume returned process data)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional

import psutil

try:
    from . import metrics
except ImportError:  # pragma: no cover - fallback for non-package execution
    import metrics  # type: ignore

logger = logging.getLogger("lavender_trinetra.monitoring.processes")
logger.addHandler(logging.NullHandler())


# =====================================================================
# CONFIGURATION
# =====================================================================

TOP_N_PROCESSES = 5


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class ProcessInfo:
    """Structured per-process resource usage sample."""

    timestamp: str
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# =====================================================================
# CORE COLLECTION
# =====================================================================

def _safe_process_info(proc: "psutil.Process") -> Optional[dict[str, Any]]:
    """Safely extract cpu/memory info from a psutil.Process, tolerating
    processes that exit or become inaccessible mid-iteration."""
    try:
        info = proc.info
        return {
            "pid": info.get("pid"),
            "name": info.get("name") or "unknown",
            "cpu_percent": info.get("cpu_percent") or 0.0,
            "memory_percent": info.get("memory_percent") or 0.0,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def collect_top_processes(top_n: int = TOP_N_PROCESSES) -> list[ProcessInfo]:
    """
    Collect the top N resource-consuming processes (ranked by combined
    CPU + memory usage) and persist the snapshot immediately via
    metrics.save_process_metrics().

    Args:
        top_n: Number of top processes to return.

    Returns:
        List of structured ProcessInfo instances, ranked descending by
        combined resource usage.

    Raises:
        Exception: re-raised after logging if collection fails entirely.
    """
    try:
        timestamp = datetime.utcnow().isoformat()

        candidates: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            info = _safe_process_info(proc)
            if info is not None:
                candidates.append(info)

        candidates.sort(
            key=lambda p: (p["cpu_percent"] + p["memory_percent"]),
            reverse=True,
        )
        top_candidates = candidates[:top_n]

        top_processes = [
            ProcessInfo(
                timestamp=timestamp,
                pid=p["pid"],
                name=p["name"],
                cpu_percent=round(float(p["cpu_percent"]), 2),
                memory_percent=round(float(p["memory_percent"]), 2),
            )
            for p in top_candidates
        ]

        metrics.save_process_metrics(
            [p.to_dict() for p in top_processes], timestamp=timestamp
        )

        return top_processes

    except Exception as exc:
        logger.exception("Top process collection failed: %s", exc)
        raise


def collect_processes_loop(
    interval_seconds: float = 5.0,
    top_n: int = TOP_N_PROCESSES,
    stop_flag: Optional[Any] = None,
) -> None:
    """
    Continuously collect the top N processes on a fixed interval until
    stop_flag signals termination. Intended to be run from main.py,
    typically on a background thread.

    Args:
        interval_seconds: Delay between successive collection cycles.
        top_n: Number of top processes to collect each cycle.
        stop_flag: An object exposing an `is_set()` method (e.g.
            threading.Event). Loop exits when stop_flag.is_set() is
            True. If None, the loop runs a single iteration.
    """
    logger.info("Starting continuous process collection (interval=%.1fs, top_n=%d)", interval_seconds, top_n)

    while True:
        try:
            collect_top_processes(top_n=top_n)
        except Exception as exc:
            logger.error("Process collection cycle failed, continuing: %s", exc)

        if stop_flag is None or (hasattr(stop_flag, "is_set") and stop_flag.is_set()):
            break

        time.sleep(interval_seconds)

    logger.info("Process collection stopped.")


__all__ = [
    "TOP_N_PROCESSES",
    "ProcessInfo",
    "collect_top_processes",
    "collect_processes_loop",
]