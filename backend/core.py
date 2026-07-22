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
    multiple times; only the first call takes effect. Used by every
    backend module (monitoring, ai, cybersecurity, database, api, main)
    as the single source of logging configuration.
    """
    global _LOGGING_CONFIGURED
    with _LOGGING_LOCK:
        if _LOGGING_CONFIGURED:
            return
        handlers: list[logging.Handler] = [logging.StreamHandler()]
        if getattr(settings, "logging", None) is not None and settings.logging.LOG_TO_FILE:
            ensure_directory(settings.logging.LOG_FILE_PATH)
            handlers.append(logging.FileHandler(settings.logging.LOG_FILE_PATH, encoding="utf-8"))

        log_format = getattr(
            getattr(settings, "logging", None),
            "LOG_FORMAT",
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        date_format = getattr(getattr(settings, "logging", None), "LOG_DATE_FORMAT", None)

        logging.basicConfig(
            level=getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO),
            format=log_format,
            datefmt=date_format,
            handlers=handlers,
        )
        _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Returns a module-scoped logger, ensuring logging is configured first.
    The single central-logging entry point every module should use.
    """
    configure_logging()
    return logging.getLogger(name)


# Named convenience loggers for the major subsystems, so every module
# can grab a consistently-namespaced logger without hardcoding the
# "lavender_trinetra.<component>" prefix itself. These are thin
# wrappers around get_logger() - no subsystem logic lives here.
def get_central_logger() -> logging.Logger:
    """The general-purpose application logger (used by main.py, config, core itself)."""
    return get_logger("lavender_trinetra.core")


def get_security_logger() -> logging.Logger:
    """The shared logger namespace for every backend.cybersecurity module."""
    return get_logger("lavender_trinetra.cybersecurity")


def get_ai_logger() -> logging.Logger:
    """The shared logger namespace for every backend.ai module."""
    return get_logger("lavender_trinetra.ai")


def get_monitoring_logger() -> logging.Logger:
    """The shared logger namespace for every backend.monitoring module."""
    return get_logger("lavender_trinetra.monitoring")


logger = get_central_logger()


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
# Identifier Utilities
# ---------------------------------------------------------------------------
def generate_uuid() -> str:
    """Returns a new random UUID4 string. The general-purpose ID generator
    for every backend module (threat IDs, incident IDs, pattern IDs, etc.)."""
    return str(uuid.uuid4())


def generate_session_id() -> str:
    """Returns a new short, URL-safe session identifier."""
    return f"session-{uuid.uuid4().hex[:16]}"


def generate_test_run_external_id() -> str:
    """Returns a new external identifier for a monitoring test run."""
    return f"run-{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# Exception Handling
# ---------------------------------------------------------------------------
@contextmanager
def safe_execute(operation_name: str, reraise: bool = False) -> Generator[None, None, None]:
    """
    Context manager that logs and optionally suppresses exceptions raised
    within a block, tagging them with a human-readable operation name.
    The central exception-handling primitive used across every subsystem.
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
    """Returns the shared application settings object (from config.py)."""
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
# CSV Management
# ---------------------------------------------------------------------------
_CSV_LOCKS: Dict[str, threading.Lock] = {}
_CSV_LOCKS_GUARD = threading.Lock()

# Centralized paths for the three core monitoring CSV files - every
# backend module reads these paths from here rather than constructing
# them independently, so there is a single source of truth.
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
    The reusable single-row CSV writing helper for every module.
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
    The reusable multi-row (batch) CSV writing helper for every module.
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


def flush_csv_writers() -> None:
    """
    No buffered file handles are held open between writes (each
    write_csv_row/write_csv_rows call opens, writes and closes its own
    handle), so there is nothing to flush at the OS level. This is the
    explicit, safe no-op call sites (e.g. main.py's shutdown sequence)
    invoke to confirm that guarantee rather than assuming it silently.
    """
    logger.debug("CSV writers confirmed flushed (no buffered handles are held open).")


def initialize_all_csv_files(
    metrics_headers: Iterable[str],
    processes_headers: Iterable[str],
    report_headers: Iterable[str],
) -> None:
    """
    Initializes all three core CSV files used by the monitoring pipeline:
    system_metrics.csv, system_processes.csv and system_report.csv.
    """
    initialize_csv(CSV_FILES["system_metrics"], metrics_headers)
    initialize_csv(CSV_FILES["system_processes"], processes_headers)
    initialize_csv(CSV_FILES["system_report"], report_headers)


# ---------------------------------------------------------------------------
# Session Management (generic ORM session lifecycle helper)
# ---------------------------------------------------------------------------
@contextmanager
def managed_session(session_factory: Callable[[], Any]) -> Generator[Any, None, None]:
    """
    Generic session context manager for any object exposing close()/commit()/
    rollback() (e.g. a SQLAlchemy Session). Decouples core.py from a direct
    database dependency while still providing safe lifecycle handling to
    database/database.py and any module that needs one.
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
    external_id: str = field(default_factory=generate_test_run_external_id)
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
    only coordinates run identity and lifecycle state, shared by main.py
    and database/crud.py.
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


# The full set of components the React dashboard displays live status
# for, in the order the dashboard presents them: Monitoring, AI Engine,
# Cybersecurity, Database, API, WebSocket.
STATUS_COMPONENTS = ("monitoring", "ai", "cybersecurity", "database", "api", "websocket")


class ApplicationStatus:
    """
    Thread-safe, in-memory status registry shared across the backend.
    The FastAPI layer reads from this registry to expose live status
    (Monitoring, AI Engine, Cybersecurity, Database, API, WebSocket,
    plus application version) to the React dashboard.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: Dict[str, str] = {component: StatusValue.UNKNOWN for component in STATUS_COMPONENTS}
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

    def get_dashboard_status(self) -> Dict[str, Any]:
        """
        Returns the exact shape the React dashboard needs: current status
        for Monitoring, AI Engine, Cybersecurity, Database, API and
        WebSocket, plus the running application version. Intended to be
        returned directly (or merged into) a FastAPI status endpoint.
        """
        with self._lock:
            status = dict(self._status)
            updated_at = dict(self._updated_at)
        return {
            "monitoring": status.get("monitoring", StatusValue.UNKNOWN),
            "ai": status.get("ai", StatusValue.UNKNOWN),
            "cybersecurity": status.get("cybersecurity", StatusValue.UNKNOWN),
            "database": status.get("database", StatusValue.UNKNOWN),
            "api": status.get("api", StatusValue.UNKNOWN),
            "websocket": status.get("websocket", StatusValue.UNKNOWN),
            "version": settings.APP_VERSION,
            "updated_at": updated_at,
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

    def set_websocket_status(self, value: str) -> None:
        self.set_status("websocket", value)

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

    def get_websocket_status(self) -> str:
        return self.get_status("websocket")


application_status = ApplicationStatus()


# ---------------------------------------------------------------------------
# Connection Management (generic helpers shared by database/api/websocket)
# ---------------------------------------------------------------------------
class ConnectionManager:
    """
    Generic, transport-agnostic registry of live connections/clients.
    Used by the API and WebSocket layers to track and broadcast to
    connected clients, and by the database layer to track pool-level
    connection identifiers - without core.py implementing any
    database, HTTP or WebSocket protocol logic itself.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._lock = threading.Lock()
        self._connections: Dict[str, Any] = {}

    def register(self, connection: Any, connection_id: Optional[str] = None) -> str:
        connection_id = connection_id or generate_uuid()
        with self._lock:
            self._connections[connection_id] = connection
        logger.info("[%s] Connection registered: %s (total=%d)", self._name, connection_id, len(self._connections))
        return connection_id

    def unregister(self, connection_id: str) -> None:
        with self._lock:
            self._connections.pop(connection_id, None)
        logger.info("[%s] Connection unregistered: %s (total=%d)", self._name, connection_id, self.count())

    def get(self, connection_id: str) -> Optional[Any]:
        with self._lock:
            return self._connections.get(connection_id)

    def all(self) -> list[Any]:
        with self._lock:
            return list(self._connections.values())

    def count(self) -> int:
        with self._lock:
            return len(self._connections)

    def clear(self) -> None:
        with self._lock:
            self._connections.clear()
        logger.info("[%s] All connections cleared.", self._name)


# Shared singleton registries. database/database.py, api/api.py and the
# WebSocket service each register/unregister into the one relevant to
# them, giving a single place to observe live connection counts.
database_connections = ConnectionManager("database")
api_connections = ConnectionManager("api")
websocket_connections = ConnectionManager("websocket")


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
    propagating individual failures, flushes CSV writers, then marks all
    components stopped. The single, central "graceful shutdown"
    primitive used by main.py.
    """
    logger.info("Beginning safe shutdown sequence.")
    with _cleanup_lock:
        callbacks = list(reversed(_cleanup_registry))

    for callback in callbacks:
        with safe_execute(f"cleanup:{getattr(callback, '__name__', callback)}"):
            callback()

    flush_csv_writers()

    database_connections.clear()
    api_connections.clear()
    websocket_connections.clear()

    for component in STATUS_COMPONENTS:
        application_status.set_status(component, StatusValue.STOPPED)

    logger.info("Safe shutdown sequence complete.")