"""
metrics.py

CSV Persistence Layer — Lavender Trinetra Platform
=====================================================================

The ONLY module in the monitoring package responsible for writing
monitoring data to CSV. All other monitoring modules (collector.py,
processes.py) must route their data through this module rather than
writing to disk directly.

Manages three pre-existing CSV files under backend/data/:
    - system_metrics.csv    (system-level metrics, one row per sample)
    - system_processes.csv  (top-process snapshots, one row per process)
    - system_report.csv     (session summary reports, one row per session)

Guarantees:
    - Files are never overwritten; new records are always appended.
    - Headers are created automatically only when a file is empty/missing.
    - Thread-safe writes via a per-file lock.
    - UTF-8 encoding throughout.

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import csv
import logging
import os
import threading
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("lavender_trinetra.monitoring.metrics")
logger.addHandler(logging.NullHandler())


# =====================================================================
# PATHS
# =====================================================================

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
)

SYSTEM_METRICS_CSV = os.path.join(_DATA_DIR, "system_metrics.csv")
SYSTEM_PROCESSES_CSV = os.path.join(_DATA_DIR, "system_processes.csv")
SYSTEM_REPORT_CSV = os.path.join(_DATA_DIR, "system_report.csv")

SYSTEM_METRICS_HEADERS = [
    "timestamp",
    "cpu_usage",
    "ram_usage",
    "disk_usage",
    "disk_read_bps",
    "disk_write_bps",
    "network_in_bps",
    "network_out_bps",
]

SYSTEM_PROCESSES_HEADERS = [
    "timestamp",
    "pid",
    "name",
    "cpu_percent",
    "memory_percent",
]

SYSTEM_REPORT_HEADERS = [
    "start_time",
    "end_time",
    "duration_seconds",
    "avg_cpu",
    "peak_cpu",
    "avg_ram",
    "peak_ram",
    "avg_disk_usage",
    "avg_network_usage_bps",
    "total_alerts",
    "warning_alerts",
    "critical_alerts",
    "top_processes",
]


# =====================================================================
# THREAD SAFETY
# =====================================================================

_locks_guard = threading.Lock()
_file_locks: dict[str, threading.Lock] = {}


def _get_lock(filepath: str) -> threading.Lock:
    """Return (creating if necessary) a dedicated lock for a given file path."""
    with _locks_guard:
        if filepath not in _file_locks:
            _file_locks[filepath] = threading.Lock()
        return _file_locks[filepath]


# =====================================================================
# CORE CSV OPERATIONS
# =====================================================================

def initialize_csv(filepath: str, headers: list[str]) -> None:
    """
    Ensure a CSV file exists and has a header row. Safe to call
    repeatedly — does nothing if the file already exists and is
    non-empty.

    Args:
        filepath: Absolute path to the CSV file.
        headers: Column headers to write if the file is new/empty.
    """
    lock = _get_lock(filepath)
    try:
        with lock:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            needs_header = (not os.path.exists(filepath)) or os.path.getsize(filepath) == 0

            if needs_header:
                with open(filepath, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                logger.info("Initialized CSV with headers: %s", filepath)

    except Exception as exc:
        logger.exception("Failed to initialize CSV %s: %s", filepath, exc)
        raise


def append_row(filepath: str, row: dict[str, Any], headers: list[str]) -> None:
    """
    Append a single row to a CSV file in a thread-safe manner. Creates
    the file with headers first if it does not already exist.

    Args:
        filepath: Absolute path to the CSV file.
        row: Dict mapping header name -> value for this record. Missing
            keys are written as empty strings; extra keys are ignored.
        headers: Column headers (also used to order the row's values).

    Raises:
        Exception: re-raised after logging if the write fails.
    """
    initialize_csv(filepath, headers)
    lock = _get_lock(filepath)

    try:
        with lock:
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                safe_row = {key: row.get(key, "") for key in headers}
                writer.writerow(safe_row)

    except Exception as exc:
        logger.exception("Failed to append row to %s: %s", filepath, exc)
        raise


def append_rows(filepath: str, rows: list[dict[str, Any]], headers: list[str]) -> None:
    """
    Append multiple rows to a CSV file in a single locked operation
    (more efficient than repeated append_row calls for batches, e.g.
    a top-5 process snapshot).

    Args:
        filepath: Absolute path to the CSV file.
        rows: List of dicts mapping header name -> value.
        headers: Column headers (also used to order each row's values).
    """
    if not rows:
        return

    initialize_csv(filepath, headers)
    lock = _get_lock(filepath)

    try:
        with lock:
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                for row in rows:
                    safe_row = {key: row.get(key, "") for key in headers}
                    writer.writerow(safe_row)

    except Exception as exc:
        logger.exception("Failed to append rows to %s: %s", filepath, exc)
        raise


def read_latest_metrics(filepath: str, n: int = 1) -> list[dict[str, str]]:
    """
    Read the most recent `n` rows from a CSV file as a list of dicts.

    Args:
        filepath: Absolute path to the CSV file.
        n: Number of most recent rows to return.

    Returns:
        List of row dicts (most recent last), or an empty list if the
        file does not exist or contains no data rows.
    """
    lock = _get_lock(filepath)
    try:
        with lock:
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                return []

            with open(filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        return rows[-n:] if n > 0 else rows

    except Exception as exc:
        logger.exception("Failed to read latest metrics from %s: %s", filepath, exc)
        return []


# =====================================================================
# DOMAIN-SPECIFIC SAVE FUNCTIONS
# =====================================================================

def save_system_metrics(metrics: dict[str, Any]) -> None:
    """
    Persist a single system metrics sample to system_metrics.csv.

    Args:
        metrics: Dict containing at least the keys in
            SYSTEM_METRICS_HEADERS. A "timestamp" is auto-populated
            with the current UTC time (ISO 8601) if not provided.
    """
    try:
        row = dict(metrics)
        row.setdefault("timestamp", datetime.utcnow().isoformat())
        append_row(SYSTEM_METRICS_CSV, row, SYSTEM_METRICS_HEADERS)
        logger.debug("System metrics saved at %s", row["timestamp"])

    except Exception as exc:
        logger.error("save_system_metrics failed: %s", exc)


def save_process_metrics(processes: list[dict[str, Any]], timestamp: Optional[str] = None) -> None:
    """
    Persist a batch of process samples (e.g. top 5 processes for the
    current tick) to system_processes.csv.

    Args:
        processes: List of dicts with keys pid, name, cpu_percent,
            memory_percent.
        timestamp: Shared ISO 8601 timestamp applied to all rows in
            this batch. Defaults to the current UTC time.
    """
    try:
        if not processes:
            return

        ts = timestamp or datetime.utcnow().isoformat()
        rows = [{**p, "timestamp": ts} for p in processes]
        append_rows(SYSTEM_PROCESSES_CSV, rows, SYSTEM_PROCESSES_HEADERS)
        logger.debug("Saved %d process record(s) at %s", len(rows), ts)

    except Exception as exc:
        logger.error("save_process_metrics failed: %s", exc)


def save_system_report(report: dict[str, Any]) -> None:
    """
    Persist a session summary report to system_report.csv.

    Args:
        report: Dict containing keys matching SYSTEM_REPORT_HEADERS.
    """
    try:
        append_row(SYSTEM_REPORT_CSV, report, SYSTEM_REPORT_HEADERS)
        logger.info("System report appended for session ending %s", report.get("end_time"))

    except Exception as exc:
        logger.error("save_system_report failed: %s", exc)


def read_metrics_since(filepath: str, since: datetime, headers: list[str]) -> list[dict[str, str]]:
    """
    Read all rows from a CSV file with a "timestamp" column at or after
    the given datetime. Used by reports.py to scope a session's data.

    Args:
        filepath: Absolute path to the CSV file.
        since: Only rows with timestamp >= this value are returned.
        headers: Expected headers (used only for validation/logging).

    Returns:
        List of matching row dicts. Rows with unparsable timestamps are
        skipped.
    """
    lock = _get_lock(filepath)
    try:
        with lock:
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                return []

            with open(filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        matched: list[dict[str, str]] = []
        for row in rows:
            ts_raw = row.get("timestamp")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                continue
            if ts >= since:
                matched.append(row)

        return matched

    except Exception as exc:
        logger.exception("Failed to read metrics since %s from %s: %s", since, filepath, exc)
        return []


# =====================================================================
# EXPORT
# =====================================================================

__all__ = [
    "SYSTEM_METRICS_CSV",
    "SYSTEM_PROCESSES_CSV",
    "SYSTEM_REPORT_CSV",
    "SYSTEM_METRICS_HEADERS",
    "SYSTEM_PROCESSES_HEADERS",
    "SYSTEM_REPORT_HEADERS",
    "initialize_csv",
    "append_row",
    "append_rows",
    "read_latest_metrics",
    "read_metrics_since",
    "save_system_metrics",
    "save_process_metrics",
    "save_system_report",
]