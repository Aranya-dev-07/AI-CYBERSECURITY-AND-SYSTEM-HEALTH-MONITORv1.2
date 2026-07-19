"""
crud.py

Database CRUD Operations — Lavender Trinetra Platform
=====================================================================

Reusable, transaction-safe database operations built on the ORM models
in models.py and the session infrastructure in database.py. Designed
to be called both from FastAPI request handlers (which supply an
injected Session via Depends(get_db)) and from the monitoring modules
/ main.py (which have no request-scoped session and can let these
functions manage their own).

Integrates with:
    - database/database.py  (SessionLocal, session_scope, get_db)
    - database/models.py    (TestRun, SystemMetric, SystemProcess)
    - monitoring/*.py        (insert_system_metrics / insert_process_metrics
                              called automatically while monitoring runs)
    - api/api.py              (all read/query functions backing REST endpoints)
    - main.py                 (create_test_run on start, end_test_run on stop)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional


def _to_json_safe(value: Any) -> Any:
    """
    Recursively converts numpy/pandas scalar types (numpy.bool_,
    numpy.integer, numpy.floating, numpy.ndarray, pandas.Timestamp, etc.)
    into native Python types the stdlib json encoder can serialize.

    AI modules (predictive_alerts.py, health_score.py, anomaly_detection.py,
    etc.) build their result dicts using numpy/pandas throughout, and stray
    numpy scalars (most commonly numpy.bool_, which prints as "bool" under
    NumPy 2.x and is easy to mistake for the builtin) routinely end up
    embedded in nested dicts/lists. json.dumps() only accepts the builtin
    bool/int/float/str/None - not their numpy counterparts - so this
    sanitizer is applied once at the database boundary rather than trying
    to track down and fix every upstream call site that might produce one.
    """
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a required dependency
        np = None

    if np is not None:
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return [_to_json_safe(item) for item in value.tolist()]

    if isinstance(value, datetime):
        return value.isoformat()

    if hasattr(value, "isoformat") and not isinstance(value, str):
        # Covers pandas.Timestamp and similar datetime-like objects.
        return value.isoformat()

    if isinstance(value, dict):
        return {key: _to_json_safe(val) for key, val in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]

    return value

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

try:
    from .database import SessionLocal, session_scope
    from .models import TestRun, SystemMetric, SystemProcess, AIResult
except ImportError:  # pragma: no cover - fallback for non-package execution
    from database import SessionLocal, session_scope  # type: ignore
    from models import TestRun, SystemMetric, SystemProcess, AIResult  # type: ignore

logger = logging.getLogger("lavender_trinetra.database.crud")
logger.addHandler(logging.NullHandler())


# =====================================================================
# SESSION RESOLUTION HELPER
# =====================================================================

@contextmanager
def _resolve_session(db: Optional[Session]) -> Generator[tuple[Session, bool], None, None]:
    """
    Yield a (session, owns_session) pair. If `db` is provided (e.g. from
    a FastAPI Depends(get_db) call), it is used as-is and the caller
    remains responsible for commit/close. If `db` is None, a new
    session is opened, committed, and closed automatically here — this
    is the path used by monitoring modules and main.py, which have no
    request-scoped session.
    """
    if db is not None:
        yield db, False
        return

    session = SessionLocal()
    try:
        yield session, True
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


# =====================================================================
# TEST RUN OPERATIONS
# =====================================================================

def create_test_run(db: Optional[Session] = None) -> dict[str, Any]:
    """
    Create a new TestRun row marking the start of a monitoring session.

    Args:
        db: Optional injected Session (FastAPI). If omitted, a session
            is opened and committed internally.

    Returns:
        Dict representation of the created TestRun (safe to use after
        the session closes).
    """
    try:
        with _resolve_session(db) as (session, owns_session):
            run = TestRun(start_time=datetime.utcnow(), total_alerts=0)
            session.add(run)
            session.flush()
            if owns_session:
                session.commit()
            else:
                session.flush()
            result = _test_run_to_dict(run)

        logger.info("Test run created: id=%s start_time=%s", result["id"], result["start_time"])
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to create test run: %s", exc)
        raise


def end_test_run(
    test_run_id: int,
    total_alerts: int,
    end_time: Optional[datetime] = None,
    db: Optional[Session] = None,
) -> Optional[dict[str, Any]]:
    """
    Finalize a TestRun when monitoring stops: sets end_time, computes
    duration, and records the total alert count.

    Args:
        test_run_id: ID of the TestRun to close out.
        total_alerts: Final alert count for the session.
        end_time: Session end timestamp; defaults to the current UTC time.
        db: Optional injected Session.

    Returns:
        Dict representation of the updated TestRun, or None if not found.
    """
    try:
        with _resolve_session(db) as (session, owns_session):
            run = session.get(TestRun, test_run_id)
            if run is None:
                logger.warning("end_test_run: TestRun id=%s not found", test_run_id)
                return None

            final_end_time = end_time or datetime.utcnow()
            run.end_time = final_end_time
            run.duration = max(0.0, (final_end_time - run.start_time).total_seconds())
            run.total_alerts = total_alerts

            session.add(run)
            session.flush()
            result = _test_run_to_dict(run)

        logger.info(
            "Test run ended: id=%s duration=%.2fs total_alerts=%d",
            result["id"], result["duration"] or 0.0, result["total_alerts"],
        )
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to end test run %s: %s", test_run_id, exc)
        raise


def get_latest_run(db: Optional[Session] = None) -> Optional[dict[str, Any]]:
    """
    Retrieve the most recently started TestRun.

    Args:
        db: Optional injected Session.

    Returns:
        Dict representation of the latest TestRun, or None if no runs exist.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            run = (
                session.query(TestRun)
                .order_by(TestRun.start_time.desc())
                .first()
            )
            return _test_run_to_dict(run) if run else None

    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve latest test run: %s", exc)
        raise


# =====================================================================
# SYSTEM METRICS OPERATIONS
# =====================================================================

def insert_system_metrics(
    metrics: dict[str, Any],
    test_run_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Insert a single system metrics sample. Intended to be called
    automatically by monitoring/collector.py on each collection cycle
    while a monitoring session is active.

    Args:
        metrics: Dict with keys timestamp, cpu_usage, ram_usage,
            disk_usage, disk_read_bps, disk_write_bps, network_in_bps,
            network_out_bps.
        test_run_id: Associated TestRun ID, if a session is active.
        db: Optional injected Session.

    Returns:
        Dict representation of the inserted SystemMetric row.
    """
    try:
        with _resolve_session(db) as (session, owns_session):
            record = SystemMetric(
                test_run_id=test_run_id,
                timestamp=_parse_timestamp(metrics.get("timestamp")),
                cpu_usage=float(metrics.get("cpu_usage", 0.0)),
                ram_usage=float(metrics.get("ram_usage", 0.0)),
                disk_usage=float(metrics.get("disk_usage", 0.0)),
                disk_read_bps=float(metrics.get("disk_read_bps", 0.0)),
                disk_write_bps=float(metrics.get("disk_write_bps", 0.0)),
                network_in_bps=float(metrics.get("network_in_bps", 0.0)),
                network_out_bps=float(metrics.get("network_out_bps", 0.0)),
            )
            session.add(record)
            session.flush()
            result = _system_metric_to_dict(record)

        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to insert system metrics: %s", exc)
        raise


def read_metrics(
    test_run_id: Optional[int] = None,
    since: Optional[datetime] = None,
    limit: int = 500,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Read system metrics rows, optionally scoped to a test run and/or
    a start timestamp, most recent first.

    Args:
        test_run_id: If provided, restrict to this TestRun.
        since: If provided, only rows with timestamp >= this value.
        limit: Maximum number of rows to return.
        db: Optional injected Session.

    Returns:
        List of SystemMetric dicts, ordered by timestamp descending.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            query = session.query(SystemMetric)
            if test_run_id is not None:
                query = query.filter(SystemMetric.test_run_id == test_run_id)
            if since is not None:
                query = query.filter(SystemMetric.timestamp >= since)

            rows = query.order_by(SystemMetric.timestamp.desc()).limit(limit).all()
            return [_system_metric_to_dict(r) for r in rows]

    except SQLAlchemyError as exc:
        logger.exception("Failed to read system metrics: %s", exc)
        raise


# =====================================================================
# SYSTEM PROCESS OPERATIONS
# =====================================================================

def insert_process_metrics(
    processes: list[dict[str, Any]],
    test_run_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Insert a batch of process samples (e.g. the top 5 processes for the
    current tick). Intended to be called automatically by
    monitoring/processes.py.

    Args:
        processes: List of dicts with keys timestamp, pid, name,
            cpu_percent, memory_percent.
        test_run_id: Associated TestRun ID, if a session is active.
        db: Optional injected Session.

    Returns:
        List of dict representations of the inserted SystemProcess rows.
    """
    if not processes:
        return []

    try:
        with _resolve_session(db) as (session, owns_session):
            records = [
                SystemProcess(
                    test_run_id=test_run_id,
                    timestamp=_parse_timestamp(p.get("timestamp")),
                    pid=p.get("pid"),
                    name=p.get("name", "unknown"),
                    cpu_percent=float(p.get("cpu_percent", 0.0)),
                    memory_percent=float(p.get("memory_percent", 0.0)),
                )
                for p in processes
            ]
            session.add_all(records)
            session.flush()
            results = [_system_process_to_dict(r) for r in records]

        return results

    except SQLAlchemyError as exc:
        logger.exception("Failed to insert process metrics: %s", exc)
        raise


def read_processes(
    test_run_id: Optional[int] = None,
    since: Optional[datetime] = None,
    limit: int = 500,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Read process metrics rows, optionally scoped to a test run and/or
    a start timestamp, most recent first.

    Args:
        test_run_id: If provided, restrict to this TestRun.
        since: If provided, only rows with timestamp >= this value.
        limit: Maximum number of rows to return.
        db: Optional injected Session.

    Returns:
        List of SystemProcess dicts, ordered by timestamp descending.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            query = session.query(SystemProcess)
            if test_run_id is not None:
                query = query.filter(SystemProcess.test_run_id == test_run_id)
            if since is not None:
                query = query.filter(SystemProcess.timestamp >= since)

            rows = query.order_by(SystemProcess.timestamp.desc()).limit(limit).all()
            return [_system_process_to_dict(r) for r in rows]

    except SQLAlchemyError as exc:
        logger.exception("Failed to read process metrics: %s", exc)
        raise


# =====================================================================
# AI RESULT OPERATIONS
# =====================================================================

def insert_ai_result(
    result: dict[str, Any],
    test_run_id: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Persist a single unified AI orchestration cycle result (the dict
    returned by ai.ai_engine.run_ai_cycle() / AIEngineResult.to_dict()).
    Intended to be called automatically from main.py after each AI
    cycle while a monitoring session is active.

    Args:
        result: Dict matching ai_engine.AIEngineResult's shape:
            timestamp, health_score (nested dict), anomalies, root_causes,
            trends, resource_growth, process_memory_leaks, predictions,
            recommendations, errors.
        test_run_id: Associated TestRun ID, if a session is active.
        db: Optional injected Session.

    Returns:
        Dict representation of the inserted AIResult row.
    """
    try:
        with _resolve_session(db) as (session, owns_session):
            health = result.get("health_score") or {}
            record = AIResult(
                test_run_id=test_run_id,
                timestamp=_parse_timestamp(result.get("timestamp")),
                health_score=health.get("score"),
                health_status=health.get("status"),
                health_details=_to_json_safe(health),
                anomalies=_to_json_safe(result.get("anomalies", [])),
                root_causes=_to_json_safe(result.get("root_causes", [])),
                trends=_to_json_safe(result.get("trends", [])),
                resource_growth=_to_json_safe(result.get("resource_growth", [])),
                process_memory_leaks=_to_json_safe(result.get("process_memory_leaks", [])),
                predictions=_to_json_safe(result.get("predictions", [])),
                recommendations=_to_json_safe(result.get("recommendations", [])),
                errors=_to_json_safe(result.get("errors", [])),
            )
            session.add(record)
            session.flush()
            saved = _ai_result_to_dict(record)

        return saved

    except SQLAlchemyError as exc:
        logger.exception("Failed to insert AI result: %s", exc)
        raise


def read_ai_results(
    test_run_id: Optional[int] = None,
    since: Optional[datetime] = None,
    limit: int = 200,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Read stored AI orchestration results, optionally scoped to a test
    run and/or a start timestamp, most recent first.

    Args:
        test_run_id: If provided, restrict to this TestRun.
        since: If provided, only rows with timestamp >= this value.
        limit: Maximum number of rows to return.
        db: Optional injected Session.

    Returns:
        List of AIResult dicts, ordered by timestamp descending.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            query = session.query(AIResult)
            if test_run_id is not None:
                query = query.filter(AIResult.test_run_id == test_run_id)
            if since is not None:
                query = query.filter(AIResult.timestamp >= since)

            rows = query.order_by(AIResult.timestamp.desc()).limit(limit).all()
            return [_ai_result_to_dict(r) for r in rows]

    except SQLAlchemyError as exc:
        logger.exception("Failed to read AI results: %s", exc)
        raise


# =====================================================================
# REPORTS (TEST RUN HISTORY)
# =====================================================================

def read_reports(
    limit: int = 50,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Read completed monitoring session reports (TestRun rows with an
    end_time set), most recent first.

    Args:
        limit: Maximum number of reports to return.
        db: Optional injected Session.

    Returns:
        List of TestRun dicts representing completed sessions.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            rows = (
                session.query(TestRun)
                .filter(TestRun.end_time.isnot(None))
                .order_by(TestRun.start_time.desc())
                .limit(limit)
                .all()
            )
            return [_test_run_to_dict(r) for r in rows]

    except SQLAlchemyError as exc:
        logger.exception("Failed to read reports: %s", exc)
        raise


# =====================================================================
# DASHBOARD STATISTICS
# =====================================================================

def get_dashboard_statistics(db: Optional[Session] = None) -> dict[str, Any]:
    """
    Aggregate cross-session statistics for the main dashboard: total
    sessions, total alerts, average/peak CPU and RAM across all
    recorded metrics, and the most recently active test run.

    Args:
        db: Optional injected Session.

    Returns:
        Dict of aggregate dashboard statistics.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            total_runs = session.query(func.count(TestRun.id)).scalar() or 0
            total_alerts = session.query(func.coalesce(func.sum(TestRun.total_alerts), 0)).scalar() or 0

            cpu_avg, cpu_max = session.query(
                func.coalesce(func.avg(SystemMetric.cpu_usage), 0.0),
                func.coalesce(func.max(SystemMetric.cpu_usage), 0.0),
            ).first() or (0.0, 0.0)

            ram_avg, ram_max = session.query(
                func.coalesce(func.avg(SystemMetric.ram_usage), 0.0),
                func.coalesce(func.max(SystemMetric.ram_usage), 0.0),
            ).first() or (0.0, 0.0)

            disk_avg = session.query(
                func.coalesce(func.avg(SystemMetric.disk_usage), 0.0)
            ).scalar() or 0.0

            total_metric_samples = session.query(func.count(SystemMetric.id)).scalar() or 0
            total_process_samples = session.query(func.count(SystemProcess.id)).scalar() or 0
            total_ai_results = session.query(func.count(AIResult.id)).scalar() or 0

            latest_run = (
                session.query(TestRun)
                .order_by(TestRun.start_time.desc())
                .first()
            )
            latest_ai_result = (
                session.query(AIResult)
                .order_by(AIResult.timestamp.desc())
                .first()
            )

            return {
                "total_runs": total_runs,
                "total_alerts": int(total_alerts),
                "avg_cpu": round(float(cpu_avg), 2),
                "peak_cpu": round(float(cpu_max), 2),
                "avg_ram": round(float(ram_avg), 2),
                "peak_ram": round(float(ram_max), 2),
                "avg_disk_usage": round(float(disk_avg), 2),
                "total_metric_samples": total_metric_samples,
                "total_process_samples": total_process_samples,
                "total_ai_results": total_ai_results,
                "latest_run": _test_run_to_dict(latest_run) if latest_run else None,
                "latest_health_status": latest_ai_result.health_status if latest_ai_result else None,
                "latest_health_score": latest_ai_result.health_score if latest_ai_result else None,
            }

    except SQLAlchemyError as exc:
        logger.exception("Failed to compute dashboard statistics: %s", exc)
        raise


# =====================================================================
# SERIALIZATION HELPERS
# =====================================================================

def _parse_timestamp(value: Any) -> datetime:
    """Coerce a timestamp value (str, datetime, or None) into a datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning("Unparsable timestamp '%s'; using current UTC time.", value)
    return datetime.utcnow()


def _test_run_to_dict(run: TestRun) -> dict[str, Any]:
    """Convert a TestRun ORM instance into a plain, session-independent dict."""
    return {
        "id": run.id,
        "start_time": run.start_time.isoformat() if run.start_time else None,
        "end_time": run.end_time.isoformat() if run.end_time else None,
        "duration": run.duration,
        "total_alerts": run.total_alerts,
    }


def _system_metric_to_dict(record: SystemMetric) -> dict[str, Any]:
    """Convert a SystemMetric ORM instance into a plain, session-independent dict."""
    return {
        "id": record.id,
        "test_run_id": record.test_run_id,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "cpu_usage": record.cpu_usage,
        "ram_usage": record.ram_usage,
        "disk_usage": record.disk_usage,
        "disk_read_bps": record.disk_read_bps,
        "disk_write_bps": record.disk_write_bps,
        "network_in_bps": record.network_in_bps,
        "network_out_bps": record.network_out_bps,
    }


def _system_process_to_dict(record: SystemProcess) -> dict[str, Any]:
    """Convert a SystemProcess ORM instance into a plain, session-independent dict."""
    return {
        "id": record.id,
        "test_run_id": record.test_run_id,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "pid": record.pid,
        "name": record.name,
        "cpu_percent": record.cpu_percent,
        "memory_percent": record.memory_percent,
    }


def _ai_result_to_dict(record: AIResult) -> dict[str, Any]:
    """Convert an AIResult ORM instance into a plain, session-independent dict."""
    return {
        "id": record.id,
        "test_run_id": record.test_run_id,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "health_score": record.health_score,
        "health_status": record.health_status,
        "health_details": record.health_details,
        "anomalies": record.anomalies,
        "root_causes": record.root_causes,
        "trends": record.trends,
        "resource_growth": record.resource_growth,
        "process_memory_leaks": record.process_memory_leaks,
        "predictions": record.predictions,
        "recommendations": record.recommendations,
        "errors": record.errors,
    }


__all__ = [
    "create_test_run",
    "end_test_run",
    "get_latest_run",
    "insert_system_metrics",
    "read_metrics",
    "insert_process_metrics",
    "read_processes",
    "insert_ai_result",
    "read_ai_results",
    "read_reports",
    "get_dashboard_statistics",
]