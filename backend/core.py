from __future__ import annotations

import csv
import logging
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterable, Optional

from backend.config import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOGGING_CONFIGURED = False
_LOGGING_LOCK = threading.Lock()


def configure_logging(level: Optional[str] = None) -> None:
    """
    Configures root logging once for the entire application. Safe to call
    multiple times; only the first call takes effect.
    """
    global _LOGGING_CONFIGURED
    with _LOGGING_LOCK:
        if _LOGGING_CONFIGURED:
            return
        logging.basicConfig(
            level=getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO),
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Returns a module-scoped logger, ensuring logging is configured first.
    """
    configure_logging()
    return logging.getLogger(name)


logger = get_logger("lavender_trinetra.core")


# ---------------------------------------------------------------------------
# Timestamp Utilities
# ---------------------------------------------------------------------------
def utc_now() -> datetime:
    """Returns the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def timestamp_iso() -> str:
    """Returns the current UTC timestamp as an ISO-8601 string."""
    return utc_now().isoformat()


def timestamp_filename_safe() -> str:
    """Returns a filesystem-safe timestamp string, e.g. for report filenames."""
    return utc_now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Exception Handling
# ---------------------------------------------------------------------------
@contextmanager
def safe_execute(operation_name: str, reraise: bool = False) -> Generator[None, None, None]:
    """
    Context manager that logs and optionally suppresses exceptions raised
    within a block, tagging them with a human-readable operation name.
    """
    try:
        yield
    except Exception as exc:
        logger.error("Operation '%s' failed: %s", operation_name, exc, exc_info=True)
        if reraise:
            raise


def safe_call(func: Callable[..., Any], *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """
    Calls a function, returning `default` and logging the error if it raises.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        logger.error("Safe call to '%s' failed: %s", getattr(func, "__name__", func), exc)
        return default


# ---------------------------------------------------------------------------
# Configuration Loading
# ---------------------------------------------------------------------------
def get_settings():
    """Returns the shared application settings object."""
    return settings


# ---------------------------------------------------------------------------
# File Validation
# ---------------------------------------------------------------------------
def ensure_directory(path: str) -> None:
    """Ensures the parent directory of `path` exists."""
    directory = os.path.dirname(path)
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)


def file_exists(path: str) -> bool:
    return Path(path).is_file()


def validate_file_readable(path: str) -> bool:
    """Validates that a file exists and is readable."""
    return Path(path).is_file() and os.access(path, os.R_OK)


def validate_file_writable(path: str) -> bool:
    """Validates that a file's parent directory exists and is writable."""
    ensure_directory(path)
    directory = os.path.dirname(path) or "."
    return os.access(directory, os.W_OK)


# ---------------------------------------------------------------------------
# CSV Helpers
# ---------------------------------------------------------------------------
_CSV_LOCKS: Dict[str, threading.Lock] = {}
_CSV_LOCKS_GUARD = threading.Lock()

CSV_FILES = {
    "system_metrics": settings.SYSTEM_METRICS_CSV,
    "system_processes": settings.SYSTEM_PROCESSES_CSV,
    "system_report": settings.SYSTEM_REPORT_CSV,
}


def _get_csv_lock(path: str) -> threading.Lock:
    with _CSV_LOCKS_GUARD:
        if path not in _CSV_LOCKS:
            _CSV_LOCKS[path] = threading.Lock()
        return _CSV_LOCKS[path]


def initialize_csv(path: str, headers: Iterable[str]) -> None:
    """
    Creates the CSV file with a header row if it does not already exist.
    """
    lock = _get_csv_lock(path)
    with lock:
        ensure_directory(path)
        if not file_exists(path) or os.path.getsize(path) == 0:
            with open(path, mode="w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(headers))
                writer.writeheader()
            logger.info("Initialized CSV file: %s", path)


def write_csv_row(path: str, row: Dict[str, Any], headers: Iterable[str]) -> None:
    """
    Appends a single row to a CSV file, initializing it first if needed.
    """
    headers = list(headers)
    initialize_csv(path, headers)
    lock = _get_csv_lock(path)
    with lock:
        with open(path, mode="a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writerow({key: row.get(key, "") for key in headers})


def write_csv_rows(path: str, rows: Iterable[Dict[str, Any]], headers: Iterable[str]) -> None:
    """
    Appends multiple rows to a CSV file, initializing it first if needed.
    """
    headers = list(headers)
    rows = list(rows)
    if not rows:
        return
    initialize_csv(path, headers)
    lock = _get_csv_lock(path)
    with lock:
        with open(path, mode="a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in headers})


def initialize_all_csv_files(
    metrics_headers: Iterable[str],
    processes_headers: Iterable[str],
    report_headers: Iterable[str],
) -> None:
    """
    Initializes all three core CSV files used by the monitoring pipeline.
    """
    initialize_csv(CSV_FILES["system_metrics"], metrics_headers)
    initialize_csv(CSV_FILES["system_processes"], processes_headers)
    initialize_csv(CSV_FILES["system_report"], report_headers)


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------
@contextmanager
def managed_session(session_factory: Callable[[], Any]) -> Generator[Any, None, None]:
    """
    Generic session context manager for any object exposing close()/commit()/
    rollback() (e.g. a SQLAlchemy Session). Decouples core.py from a direct
    database dependency while still providing safe lifecycle handling.
    """
    session = session_factory()
    try:
        yield session
        if hasattr(session, "commit"):
            session.commit()
    except Exception:
        if hasattr(session, "rollback"):
            session.rollback()
        raise
    finally:
        if hasattr(session, "close"):
            session.close()


# ---------------------------------------------------------------------------
# Test Run Management
# ---------------------------------------------------------------------------
@dataclass
class TestRunContext:
    run_id: Optional[int] = None
    external_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=utc_now)
    ended_at: Optional[datetime] = None
    alert_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_ended(self) -> None:
        self.ended_at = utc_now()

    def increment_alerts(self, count: int = 1) -> None:
        self.alert_count += count

    def as_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "external_id": self.external_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "alert_count": self.alert_count,
            "metadata": self.metadata,
        }


class TestRunManager:
    """
    Tracks the currently active test run in memory. Persistence to the
    database is the responsibility of the database/ module; this manager
    only coordinates run identity and lifecycle state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: Optional[TestRunContext] = None

    def start_run(self, run_id: Optional[int] = None, **metadata: Any) -> TestRunContext:
        with self._lock:
            self._current = TestRunContext(run_id=run_id, metadata=metadata)
            logger.info("Test run started: %s", self._current.external_id)
            return self._current

    def end_run(self) -> Optional[TestRunContext]:
        with self._lock:
            if self._current is not None:
                self._current.mark_ended()
                logger.info("Test run ended: %s", self._current.external_id)
            return self._current

    def get_current(self) -> Optional[TestRunContext]:
        with self._lock:
            return self._current

    def record_alert(self, count: int = 1) -> None:
        with self._lock:
            if self._current is not None:
                self._current.increment_alerts(count)


test_run_manager = TestRunManager()


# ---------------------------------------------------------------------------
# Application Status Management
# ---------------------------------------------------------------------------
class StatusValue:
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ApplicationStatus:
    """
    Thread-safe, in-memory status registry shared across the backend.
    The FastAPI layer reads from this registry to expose live status to
    the React dashboard.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: Dict[str, str] = {
            "monitoring": StatusValue.UNKNOWN,
            "ai": StatusValue.UNKNOWN,
            "database": StatusValue.UNKNOWN,
            "api": StatusValue.UNKNOWN,
            "cybersecurity": StatusValue.UNKNOWN,
        }
        self._updated_at: Dict[str, str] = {key: timestamp_iso() for key in self._status}

    def set_status(self, component: str, value: str) -> None:
        with self._lock:
            self._status[component] = value
            self._updated_at[component] = timestamp_iso()
            logger.info("Status updated: %s -> %s", component, value)

    def get_status(self, component: str) -> str:
        with self._lock:
            return self._status.get(component, StatusValue.UNKNOWN)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": dict(self._status),
                "updated_at": dict(self._updated_at),
            }

    def set_monitoring_status(self, value: str) -> None:
        self.set_status("monitoring", value)

    def set_ai_status(self, value: str) -> None:
        self.set_status("ai", value)

    def set_database_status(self, value: str) -> None:
        self.set_status("database", value)

    def set_api_status(self, value: str) -> None:
        self.set_status("api", value)

    def set_cybersecurity_status(self, value: str) -> None:
        self.set_status("cybersecurity", value)

    def get_monitoring_status(self) -> str:
        return self.get_status("monitoring")

    def get_ai_status(self) -> str:
        return self.get_status("ai")

    def get_database_status(self) -> str:
        return self.get_status("database")

    def get_api_status(self) -> str:
        return self.get_status("api")

    def get_cybersecurity_status(self) -> str:
        return self.get_status("cybersecurity")


application_status = ApplicationStatus()


# ---------------------------------------------------------------------------
# Startup / Shutdown / Resource Cleanup Helpers
# ---------------------------------------------------------------------------
_cleanup_registry: list[Callable[[], None]] = []
_cleanup_lock = threading.Lock()


def register_cleanup(callback: Callable[[], None]) -> None:
    """
    Registers a callback to be invoked during safe_shutdown(). Callbacks
    are executed in reverse registration order (LIFO), mirroring typical
    resource teardown semantics.
    """
    with _cleanup_lock:
        _cleanup_registry.append(callback)


def startup_initialize(
    metrics_headers: Iterable[str],
    processes_headers: Iterable[str],
    report_headers: Iterable[str],
) -> None:
    """
    Performs generic startup initialization: logging, CSV files, and
    baseline status values. Does not start any monitoring, AI or
    cybersecurity logic - that is the responsibility of main.py and the
    respective modules.
    """
    configure_logging()
    initialize_all_csv_files(metrics_headers, processes_headers, report_headers)
    application_status.set_api_status(StatusValue.OPERATIONAL)
    logger.info("Startup initialization complete.")


def safe_shutdown() -> None:
    """
    Executes all registered cleanup callbacks safely, logging but not
    propagating individual failures, then marks all components stopped.
    """
    logger.info("Beginning safe shutdown sequence.")
    with _cleanup_lock:
        callbacks = list(reversed(_cleanup_registry))

    for callback in callbacks:
        with safe_execute(f"cleanup:{getattr(callback, '__name__', callback)}"):
            callback()

    for component in ("monitoring", "ai", "cybersecurity", "api", "database"):
        application_status.set_status(component, StatusValue.STOPPED)

    logger.info("Safe shutdown sequence complete.")