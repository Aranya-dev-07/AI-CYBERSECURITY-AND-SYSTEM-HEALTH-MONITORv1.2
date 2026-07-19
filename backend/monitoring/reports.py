"""
reports.py

Session Report Generator — Lavender Trinetra Platform
=====================================================================

When monitoring stops, reads the current session's data from the
system_metrics.csv and system_processes.csv files (written throughout
the session by metrics.py), computes a summary (averages, peaks, alert
totals, top processes), appends it to system_report.csv via
metrics.py, and returns the summary as a structured dictionary.

Integrates with:
    - metrics.py    (sole CSV reader/writer — reports.py never touches disk directly)
    - alerts.py     (supplies session alert statistics)
    - main.py       (invokes generate_session_report() on "stop")
    - api/routes.py / dashboard.py (consume the returned summary dict)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

try:
    from . import metrics
    from . import alerts
except ImportError:  # pragma: no cover - fallback for non-package execution
    import metrics  # type: ignore
    import alerts  # type: ignore

logger = logging.getLogger("lavender_trinetra.monitoring.reports")
logger.addHandler(logging.NullHandler())


# =====================================================================
# HELPERS
# =====================================================================

def _to_float(value: Any, default: float = 0.0) -> float:
    """Safely coerce a CSV string value to float, tolerating blanks/None."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    """Safely coerce a value to int, tolerating blanks/None."""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# =====================================================================
# AGGREGATION
# =====================================================================

def _aggregate_metrics_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Compute averages/peaks for CPU, RAM, Disk, and Network from
    system_metrics.csv rows belonging to the current session."""
    if not rows:
        return {
            "avg_cpu": 0.0, "peak_cpu": 0.0,
            "avg_ram": 0.0, "peak_ram": 0.0,
            "avg_disk_usage": 0.0,
            "avg_network_usage_bps": 0.0,
        }

    cpu_values = [_to_float(r.get("cpu_usage")) for r in rows]
    ram_values = [_to_float(r.get("ram_usage")) for r in rows]
    disk_values = [_to_float(r.get("disk_usage")) for r in rows]
    network_values = [
        _to_float(r.get("network_in_bps")) + _to_float(r.get("network_out_bps"))
        for r in rows
    ]

    return {
        "avg_cpu": round(sum(cpu_values) / len(cpu_values), 2),
        "peak_cpu": round(max(cpu_values), 2),
        "avg_ram": round(sum(ram_values) / len(ram_values), 2),
        "peak_ram": round(max(ram_values), 2),
        "avg_disk_usage": round(sum(disk_values) / len(disk_values), 2),
        "avg_network_usage_bps": round(sum(network_values) / len(network_values), 2),
    }


def _top_resource_processes(rows: list[dict[str, str]], top_n: int = 5) -> list[dict[str, Any]]:
    """
    Identify the top resource-consuming processes across the session
    from system_processes.csv rows, ranked by average combined
    CPU + memory usage.
    """
    if not rows:
        return []

    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"cpu_sum": 0.0, "mem_sum": 0.0, "count": 0.0})

    for row in rows:
        name = row.get("name") or "unknown"
        totals[name]["cpu_sum"] += _to_float(row.get("cpu_percent"))
        totals[name]["mem_sum"] += _to_float(row.get("memory_percent"))
        totals[name]["count"] += 1

    ranked = []
    for name, agg in totals.items():
        count = agg["count"] or 1.0
        avg_cpu = agg["cpu_sum"] / count
        avg_mem = agg["mem_sum"] / count
        ranked.append({
            "name": name,
            "avg_cpu_percent": round(avg_cpu, 2),
            "avg_memory_percent": round(avg_mem, 2),
            "combined_score": round(avg_cpu + avg_mem, 2),
        })

    ranked.sort(key=lambda p: p["combined_score"], reverse=True)
    return ranked[:top_n]


# =====================================================================
# CORE REPORT GENERATION
# =====================================================================

def generate_session_report(
    session_start: datetime,
    session_end: Optional[datetime] = None,
    alert_tracker: Optional["alerts.AlertSessionTracker"] = None,
) -> dict[str, Any]:
    """
    Generate a full monitoring session summary and append it to
    system_report.csv.

    Args:
        session_start: Timestamp marking when monitoring began.
        session_end: Timestamp marking when monitoring stopped;
            defaults to the current UTC time.
        alert_tracker: AlertSessionTracker to pull statistics from;
            defaults to alerts.py's module-wide singleton.

    Returns:
        Structured dict summary, matching metrics.SYSTEM_REPORT_HEADERS
        plus a nested "top_processes" breakdown and raw alert counts.
    """
    try:
        end_time = session_end or datetime.utcnow()
        duration_seconds = max(0.0, (end_time - session_start).total_seconds())

        metrics_rows = metrics.read_metrics_since(
            metrics.SYSTEM_METRICS_CSV, session_start, metrics.SYSTEM_METRICS_HEADERS
        )
        process_rows = metrics.read_metrics_since(
            metrics.SYSTEM_PROCESSES_CSV, session_start, metrics.SYSTEM_PROCESSES_HEADERS
        )

        metric_aggregates = _aggregate_metrics_rows(metrics_rows)
        top_processes = _top_resource_processes(process_rows)

        alert_stats = alerts.get_alert_statistics(alert_tracker)

        top_processes_str = "; ".join(
            f"{p['name']} (cpu={p['avg_cpu_percent']}%, mem={p['avg_memory_percent']}%)"
            for p in top_processes
        )

        report_row = {
            "start_time": session_start.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "avg_cpu": metric_aggregates["avg_cpu"],
            "peak_cpu": metric_aggregates["peak_cpu"],
            "avg_ram": metric_aggregates["avg_ram"],
            "peak_ram": metric_aggregates["peak_ram"],
            "avg_disk_usage": metric_aggregates["avg_disk_usage"],
            "avg_network_usage_bps": metric_aggregates["avg_network_usage_bps"],
            "total_alerts": alert_stats["total_alerts"],
            "warning_alerts": alert_stats["warning_alerts"],
            "critical_alerts": alert_stats["critical_alerts"],
            "top_processes": top_processes_str,
        }

        metrics.save_system_report(report_row)

        summary: dict[str, Any] = dict(report_row)
        summary["top_processes"] = top_processes  # structured form for API/dashboard consumers
        summary["sample_count"] = len(metrics_rows)

        logger.info(
            "Session report generated: duration=%.1fs avg_cpu=%.1f%% total_alerts=%d",
            duration_seconds, metric_aggregates["avg_cpu"], alert_stats["total_alerts"],
        )

        return summary

    except Exception as exc:
        logger.exception("Session report generation failed: %s", exc)
        return {
            "start_time": session_start.isoformat(),
            "end_time": (session_end or datetime.utcnow()).isoformat(),
            "error": str(exc),
        }


def generate_report_on_stop(
    session_start: datetime,
    alert_tracker: Optional["alerts.AlertSessionTracker"] = None,
) -> dict[str, Any]:
    """
    Convenience entry point for main.py: invoked when the user types
    "stop", immediately generating and appending the final session
    report using the current time as the session end.

    Args:
        session_start: Timestamp marking when monitoring began (main.py
            should track and pass this in).
        alert_tracker: Optional AlertSessionTracker override.

    Returns:
        The generated summary dict (see generate_session_report()).
    """
    return generate_session_report(
        session_start=session_start,
        session_end=datetime.utcnow(),
        alert_tracker=alert_tracker,
    )


__all__ = [
    "generate_session_report",
    "generate_report_on_stop",
]