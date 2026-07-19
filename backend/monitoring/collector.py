"""
collector.py

System Metrics Collector — Lavender Trinetra Platform
=====================================================================

Continuously collects system-level metrics (CPU, RAM, Disk, Network
I/O) using psutil, forwards each sample to metrics.py for immediate
CSV persistence, and returns the structured data for downstream
consumption (ai_engine.py, api/routes.py, dashboard.py).

Integrates with:
    - metrics.py    (sole CSV writer — collector never writes to disk directly)
    - main.py       (drives the monitoring loop)
    - ai/ai_engine.py (consumes returned MonitoringTick-shaped data)

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

logger = logging.getLogger("lavender_trinetra.monitoring.collector")
logger.addHandler(logging.NullHandler())


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class SystemMetrics:
    """Structured system metrics sample."""

    timestamp: str
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    disk_read_bps: float
    disk_write_bps: float
    network_in_bps: float
    network_out_bps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# =====================================================================
# INTERNAL STATE (for computing per-second I/O deltas)
# =====================================================================

class _IOBaseline:
    """Tracks the previous disk/network counters and timestamp to
    compute bytes-per-second rates between successive collect() calls."""

    def __init__(self) -> None:
        self._last_time: Optional[float] = None
        self._last_disk_read: Optional[int] = None
        self._last_disk_write: Optional[int] = None
        self._last_net_in: Optional[int] = None
        self._last_net_out: Optional[int] = None

    def compute_rates(self) -> tuple[float, float, float, float]:
        """
        Sample current disk/network counters and compute bytes/sec
        deltas since the previous call. Returns zeros on the first call.

        Returns:
            (disk_read_bps, disk_write_bps, network_in_bps, network_out_bps)
        """
        now = time.monotonic()

        disk_io = psutil.disk_io_counters()
        net_io = psutil.net_io_counters()

        disk_read = disk_io.read_bytes if disk_io else 0
        disk_write = disk_io.write_bytes if disk_io else 0
        net_in = net_io.bytes_recv if net_io else 0
        net_out = net_io.bytes_sent if net_io else 0

        if self._last_time is None:
            elapsed = 1.0  # avoid div-by-zero on first sample
            disk_read_bps = 0.0
            disk_write_bps = 0.0
            net_in_bps = 0.0
            net_out_bps = 0.0
        else:
            elapsed = max(now - self._last_time, 1e-6)
            disk_read_bps = max(0.0, (disk_read - self._last_disk_read) / elapsed)
            disk_write_bps = max(0.0, (disk_write - self._last_disk_write) / elapsed)
            net_in_bps = max(0.0, (net_in - self._last_net_in) / elapsed)
            net_out_bps = max(0.0, (net_out - self._last_net_out) / elapsed)

        self._last_time = now
        self._last_disk_read = disk_read
        self._last_disk_write = disk_write
        self._last_net_in = net_in
        self._last_net_out = net_out

        return disk_read_bps, disk_write_bps, net_in_bps, net_out_bps


_baseline = _IOBaseline()


# =====================================================================
# CORE COLLECTION
# =====================================================================

def collect_system_metrics(cpu_interval: float = 0.1) -> SystemMetrics:
    """
    Collect a single system metrics sample and persist it immediately
    via metrics.save_system_metrics().

    Args:
        cpu_interval: Blocking interval (seconds) passed to
            psutil.cpu_percent() for an accurate CPU reading.

    Returns:
        A structured SystemMetrics instance.

    Raises:
        Exception: re-raised after logging if collection fails.
    """
    try:
        timestamp = datetime.utcnow().isoformat()

        cpu_usage = psutil.cpu_percent(interval=cpu_interval)
        ram_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage("/").percent

        disk_read_bps, disk_write_bps, net_in_bps, net_out_bps = _baseline.compute_rates()

        sample = SystemMetrics(
            timestamp=timestamp,
            cpu_usage=round(cpu_usage, 2),
            ram_usage=round(ram_usage, 2),
            disk_usage=round(disk_usage, 2),
            disk_read_bps=round(disk_read_bps, 2),
            disk_write_bps=round(disk_write_bps, 2),
            network_in_bps=round(net_in_bps, 2),
            network_out_bps=round(net_out_bps, 2),
        )

        metrics.save_system_metrics(sample.to_dict())

        return sample

    except Exception as exc:
        logger.exception("System metrics collection failed: %s", exc)
        raise


def collect_metrics_loop(
    interval_seconds: float = 5.0,
    stop_flag: Optional[Any] = None,
) -> None:
    """
    Continuously collect system metrics on a fixed interval until
    stop_flag signals termination. Intended to be run from main.py,
    typically on a background thread.

    Args:
        interval_seconds: Delay between successive collection cycles.
        stop_flag: An object exposing an `is_set()` method (e.g.
            threading.Event). Loop exits when stop_flag.is_set() is
            True. If None, the loop runs a single iteration.
    """
    logger.info("Starting continuous system metrics collection (interval=%.1fs)", interval_seconds)

    while True:
        try:
            collect_system_metrics()
        except Exception as exc:
            logger.error("Metrics collection cycle failed, continuing: %s", exc)

        if stop_flag is None or (hasattr(stop_flag, "is_set") and stop_flag.is_set()):
            break

        time.sleep(interval_seconds)

    logger.info("System metrics collection stopped.")


__all__ = [
    "SystemMetrics",
    "collect_system_metrics",
    "collect_metrics_loop",
]