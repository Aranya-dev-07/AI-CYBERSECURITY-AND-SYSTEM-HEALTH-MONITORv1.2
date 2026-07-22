"""
backend/cybersecurity/security_history.py

Security History — Lavender Trinetra Cybersecurity Platform
=====================================================================

Provides historical cybersecurity analysis by retrieving and shaping
data already persisted in PostgreSQL. This module performs NO
monitoring, detection, scanning, or scoring of its own - it strictly
reads (and, for security score snapshots only, durably records) data
already produced upstream by:

    - incident_logger.py          (backend.cybersecurity.SecurityIncident)
    - attack_patterns.py          (backend.cybersecurity.AttackPatternRecord)
    - security_score.py           (in-memory score results; this module
                                    provides the PostgreSQL persistence
                                    layer that module has never owned)

Historical views produced:

    - Threat Timeline
    - Incident Timeline
    - Security Score History
    - Vulnerability Trends
    - Attack Pattern History

This module is the PostgreSQL-backed history source that
security_reports.py's `_get_latest_score()` / `_get_score_history()`
guarded hooks were written to prefer once available (see
security_reports.py's `security_history` import guard) - wiring that
integration (i.e. calling record_score_snapshot() from the monitoring
cycle) is a separate follow-up step, not performed here.

Integrates with:
    - backend/config.py                          (settings)
    - backend/core.py                             (logging, safe_execute)
    - backend/database/database.py                (Base, engine, get_db,
                                                     session_scope)
    - backend/cybersecurity/incident_logger.py     (SecurityIncident)
    - backend/cybersecurity/attack_patterns.py     (AttackPatternRecord,
                                                     get_patterns_from_db)
    - backend/cybersecurity/security_score.py      (score result shape)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, Index, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core import get_logger, safe_execute, utc_now

from backend.database.database import Base, SessionLocal, engine, get_db, session_scope

from backend.cybersecurity.incident_logger import (
    IncidentStatus,
    SecurityIncident,
)
from backend.cybersecurity.attack_patterns import (
    AttackPatternRecord,
    get_patterns_from_db,
)

logger = get_logger("lavender_trinetra.cybersecurity.security_history")


# =====================================================================
# CONFIGURATION
# =====================================================================

HISTORY_DEFAULT_WINDOW_DAYS = int(getattr(settings, "SECURITY_HISTORY_DEFAULT_WINDOW_DAYS", 30))
HISTORY_MAX_WINDOW_DAYS = int(getattr(settings, "SECURITY_HISTORY_MAX_WINDOW_DAYS", 365))
HISTORY_DEFAULT_LIMIT = int(getattr(settings, "SECURITY_HISTORY_DEFAULT_LIMIT", 200))
HISTORY_MAX_LIMIT = int(getattr(settings, "SECURITY_HISTORY_MAX_LIMIT", 1000))

_THREAT_SOURCE_MODULES = frozenset({"threat_detector", "intrusion_detector", "security_score"})
_VULNERABILITY_SOURCE_MODULE = "vulnerability_scan"


def _window_since(days: Optional[int]) -> datetime:
    resolved_days = min(max(1, days or HISTORY_DEFAULT_WINDOW_DAYS), HISTORY_MAX_WINDOW_DAYS)
    return (utc_now() - timedelta(days=resolved_days)).replace(tzinfo=None)


def _capped_limit(limit: int) -> int:
    return max(1, min(limit, HISTORY_MAX_LIMIT))


# =====================================================================
# ORM MODEL — SECURITY SCORE SNAPSHOTS
# =====================================================================
# security_score.py has never persisted its results (it only keeps an
# in-memory buffer, by design - see its own module docstring). Since
# "Security Score History" requires PostgreSQL-backed data, this
# module owns that persistence, defined here per the "no additional
# files" constraint. Registered against the shared Base so
# database.init_db() creates it alongside every other table.
# ---------------------------------------------------------------------
class SecurityScoreSnapshot(Base):
    """One durable snapshot of a computed security_score.py result."""

    __tablename__ = "security_score_history"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    score = Column(Float, nullable=False, default=100.0)
    grade = Column(String(20), nullable=False, default="Excellent", index=True)
    delta = Column(Float, nullable=True)
    factors = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_security_score_history_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<SecurityScoreSnapshot id={self.id} score={self.score} grade={self.grade}>"


def _score_snapshot_to_dict(record: SecurityScoreSnapshot) -> dict[str, Any]:
    return {
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "score": record.score,
        "grade": record.grade,
        "delta": record.delta,
        "factors": record.factors,
    }


def ensure_table_exists() -> None:
    """Creates only this module's table if it does not already exist."""
    with safe_execute("security_history.ensure_table_exists"):
        Base.metadata.create_all(bind=engine, tables=[SecurityScoreSnapshot.__table__])


# =====================================================================
# SECURITY SCORE PERSISTENCE (reusable entry point)
# =====================================================================

def record_score_snapshot(score_result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Durably persists one security_score.py result dict (as returned by
    compute_security_score()/get_latest_score()) to PostgreSQL. Safe to
    call once per security cycle; performs no scoring of its own.
    """
    if not score_result:
        return None

    try:
        with safe_execute("security_history.record_score_snapshot", reraise=True):
            with session_scope() as db:
                record = SecurityScoreSnapshot(
                    timestamp=_parse_ts(score_result.get("timestamp")),
                    score=float(score_result.get("score", 0.0)),
                    grade=score_result.get("grade", "Unknown"),
                    delta=score_result.get("delta"),
                    factors=str(score_result.get("factors", [])),
                )
                db.add(record)
                db.flush()
                result = _score_snapshot_to_dict(record)

        logger.info("Security score snapshot recorded: score=%.1f grade=%s", result["score"], result["grade"])
        return result
    except SQLAlchemyError as exc:
        logger.exception("Failed to record security score snapshot: %s", exc)
        raise


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning("Unparsable timestamp '%s'; using current UTC time.", value)
    return datetime.utcnow()


# =====================================================================
# SESSION RESOLUTION HELPER (mirrors crud.py / incident_logger.py conventions)
# =====================================================================

from contextlib import contextmanager
from typing import Generator


@contextmanager
def _resolve_session(db: Optional[Session]) -> Generator[tuple[Session, bool], None, None]:
    """
    Yields a (session, owns_session) pair. If `db` is supplied (e.g. a
    FastAPI Depends(get_db) session), it is used as-is. Otherwise a new
    session is opened and closed here for standalone/script use.
    """
    if db is not None:
        yield db, False
        return

    session = SessionLocal()
    try:
        yield session, True
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()


# =====================================================================
# THREAT TIMELINE
# =====================================================================

def get_threat_timeline(
    window_days: Optional[int] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Builds a chronological timeline of confirmed threat-related
    incidents (as persisted by incident_logger.py from
    threat_detector.py, intrusion_detector.py, and security_score.py),
    oldest first, over the requested window.
    """
    try:
        since = _window_since(window_days)
        capped_limit = _capped_limit(limit)

        with _resolve_session(db) as (session, _owns_session):
            rows = (
                session.query(SecurityIncident)
                .filter(
                    SecurityIncident.source_module.in_(_THREAT_SOURCE_MODULES),
                    SecurityIncident.timestamp >= since,
                )
                .order_by(SecurityIncident.timestamp.asc())
                .limit(capped_limit)
                .all()
            )

        timeline = [
            {
                "incident_id": row.incident_id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "severity": row.severity,
                "category": row.category,
                "source_module": row.source_module,
                "description": row.description,
                "status": row.status,
            }
            for row in rows
        ]

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or HISTORY_DEFAULT_WINDOW_DAYS), HISTORY_MAX_WINDOW_DAYS),
            "event_count": len(timeline),
            "timeline": timeline,
        }

        logger.info("Threat timeline built: %d event(s) in window.", len(timeline))
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to build threat timeline: %s", exc)
        raise


# =====================================================================
# INCIDENT TIMELINE
# =====================================================================

def get_incident_timeline(
    window_days: Optional[int] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    status: Optional[str] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Builds a chronological timeline of ALL confirmed security
    incidents (any source module), oldest first, over the requested
    window, optionally filtered by status.
    """
    try:
        since = _window_since(window_days)
        capped_limit = _capped_limit(limit)

        with _resolve_session(db) as (session, _owns_session):
            query = session.query(SecurityIncident).filter(SecurityIncident.timestamp >= since)
            if status is not None:
                query = query.filter(SecurityIncident.status == status)

            rows = query.order_by(SecurityIncident.timestamp.asc()).limit(capped_limit).all()

        timeline = [
            {
                "incident_id": row.incident_id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "severity": row.severity,
                "category": row.category,
                "source_module": row.source_module,
                "description": row.description,
                "status": row.status,
                "resolution_notes": row.resolution_notes,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or HISTORY_DEFAULT_WINDOW_DAYS), HISTORY_MAX_WINDOW_DAYS),
            "event_count": len(timeline),
            "timeline": timeline,
        }

        logger.info("Incident timeline built: %d event(s) in window.", len(timeline))
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to build incident timeline: %s", exc)
        raise


# =====================================================================
# SECURITY SCORE HISTORY
# =====================================================================

def get_latest_score(db: Optional[Session] = None) -> Optional[dict[str, Any]]:
    """Returns the most recently persisted security score snapshot, or None."""
    try:
        with _resolve_session(db) as (session, _owns_session):
            record = (
                session.query(SecurityScoreSnapshot)
                .order_by(SecurityScoreSnapshot.timestamp.desc())
                .first()
            )
            return _score_snapshot_to_dict(record) if record else None
    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve latest security score snapshot: %s", exc)
        raise


def get_score_history(
    window_days: Optional[int] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Returns persisted security score snapshots, oldest first (suitable
    for trend charts), over the requested window.
    """
    try:
        since = _window_since(window_days)
        capped_limit = _capped_limit(limit)

        with _resolve_session(db) as (session, _owns_session):
            rows = (
                session.query(SecurityScoreSnapshot)
                .filter(SecurityScoreSnapshot.timestamp >= since)
                .order_by(SecurityScoreSnapshot.timestamp.desc())
                .limit(capped_limit)
                .all()
            )

        rows.reverse()
        return [_score_snapshot_to_dict(r) for r in rows]

    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve security score history: %s", exc)
        raise


def get_security_score_history(
    window_days: Optional[int] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Full "Security Score History" view: the time series plus a simple
    trend direction summary, for the Reports/Dashboard workspace.
    """
    try:
        series = get_score_history(window_days=window_days, limit=limit, db=db)

        direction = "stable"
        change = 0.0
        if len(series) >= 2:
            change = round(series[-1]["score"] - series[0]["score"], 2)
            if change > 1.0:
                direction = "improving"
            elif change < -1.0:
                direction = "declining"

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or HISTORY_DEFAULT_WINDOW_DAYS), HISTORY_MAX_WINDOW_DAYS),
            "sample_count": len(series),
            "direction": direction,
            "change": change,
            "series": series,
        }

        logger.info("Security score history built: %d sample(s), direction=%s.", len(series), direction)
        return result

    except Exception as exc:
        logger.exception("Failed to build security score history: %s", exc)
        raise


# =====================================================================
# VULNERABILITY TRENDS
# =====================================================================

def get_vulnerability_trends(
    window_days: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Builds a day-by-day trend of confirmed vulnerability findings (as
    persisted by incident_logger.py from vulnerability_scan.py),
    grouped by severity, over the requested window.
    """
    try:
        since = _window_since(window_days)

        with _resolve_session(db) as (session, _owns_session):
            rows = (
                session.query(SecurityIncident)
                .filter(
                    SecurityIncident.source_module == _VULNERABILITY_SOURCE_MODULE,
                    SecurityIncident.timestamp >= since,
                )
                .order_by(SecurityIncident.timestamp.asc())
                .all()
            )

        daily_severity_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        by_category: dict[str, int] = defaultdict(int)
        unresolved_count = 0

        for row in rows:
            day_key = row.timestamp.date().isoformat() if row.timestamp else "unknown"
            daily_severity_counts[day_key][row.severity] += 1
            by_category[row.category] += 1
            if row.status != IncidentStatus.RESOLVED:
                unresolved_count += 1

        trend_series = [
            {"date": day, "counts": dict(counts)}
            for day, counts in sorted(daily_severity_counts.items())
        ]

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or HISTORY_DEFAULT_WINDOW_DAYS), HISTORY_MAX_WINDOW_DAYS),
            "total_findings": len(rows),
            "unresolved_findings": unresolved_count,
            "by_category": dict(by_category),
            "trend": trend_series,
        }

        logger.info("Vulnerability trends built: %d finding(s) across %d day(s).", len(rows), len(trend_series))
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to build vulnerability trends: %s", exc)
        raise


# =====================================================================
# ATTACK PATTERN HISTORY
# =====================================================================

def get_attack_pattern_history(
    window_days: Optional[int] = None,
    limit: int = HISTORY_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Builds a historical view of correlated attack patterns (as
    persisted by attack_patterns.py), most recent first, over the
    requested window.
    """
    try:
        since = _window_since(window_days)
        capped_limit = _capped_limit(limit)

        with _resolve_session(db) as (session, _owns_session):
            rows = (
                session.query(AttackPatternRecord)
                .filter(AttackPatternRecord.timestamp >= since)
                .order_by(AttackPatternRecord.timestamp.desc())
                .limit(capped_limit)
                .all()
            )

            patterns = get_patterns_from_db(session, limit=capped_limit) if False else [
                {
                    "pattern_id": row.pattern_id,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "category": row.category,
                    "severity": row.severity,
                    "title": row.title,
                    "summary": row.summary,
                    "source": row.source,
                    "affected_components": [
                        c.strip() for c in (row.affected_components or "").split(",") if c.strip()
                    ],
                    "occurrence_count": row.occurrence_count,
                    "first_seen": row.first_seen.isoformat() if row.first_seen else None,
                    "last_seen": row.last_seen.isoformat() if row.last_seen else None,
                }
                for row in rows
            ]

        by_category: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)
        for p in patterns:
            by_category[p["category"]] += 1
            by_severity[p["severity"]] += 1

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or HISTORY_DEFAULT_WINDOW_DAYS), HISTORY_MAX_WINDOW_DAYS),
            "pattern_count": len(patterns),
            "by_category": dict(by_category),
            "by_severity": dict(by_severity),
            "patterns": patterns,
        }

        logger.info("Attack pattern history built: %d pattern(s) in window.", len(patterns))
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to build attack pattern history: %s", exc)
        raise


# =====================================================================
# PYDANTIC RESPONSE SCHEMAS
# =====================================================================

class ThreatTimelineResponse(BaseModel):
    generated_at: str
    window_days: int
    event_count: int
    timeline: list[dict[str, Any]]


class IncidentTimelineResponse(BaseModel):
    generated_at: str
    window_days: int
    event_count: int
    timeline: list[dict[str, Any]]


class SecurityScoreHistoryResponse(BaseModel):
    generated_at: str
    window_days: int
    sample_count: int
    direction: str
    change: float
    series: list[dict[str, Any]]


class VulnerabilityTrendsResponse(BaseModel):
    generated_at: str
    window_days: int
    total_findings: int
    unresolved_findings: int
    by_category: dict[str, int]
    trend: list[dict[str, Any]]


class AttackPatternHistoryResponse(BaseModel):
    generated_at: str
    window_days: int
    pattern_count: int
    by_category: dict[str, int]
    by_severity: dict[str, int]
    patterns: list[dict[str, Any]]


class ScoreSnapshotResponse(BaseModel):
    timestamp: Optional[str] = None
    score: float
    grade: str
    delta: Optional[float] = None
    factors: Optional[str] = None


# =====================================================================
# COORDINATION FACADE (startup only — no monitoring/detection)
# =====================================================================

_active = False


def start() -> None:
    """Called once on application startup to ensure this module's table exists."""
    global _active
    ensure_table_exists()
    _active = True
    logger.info("Security history module ready.")


def stop() -> None:
    global _active
    _active = False
    logger.info("Security history module stopped.")


def get_status() -> dict[str, Any]:
    return {"active": _active}


# =====================================================================
# FASTAPI ROUTER
# =====================================================================

router = APIRouter(prefix="/api/cybersecurity/history", tags=["Security History"])


@router.get("/threats", response_model=ThreatTimelineResponse)
def api_get_threat_timeline(
    window_days: int = Query(HISTORY_DEFAULT_WINDOW_DAYS, ge=1, le=HISTORY_MAX_WINDOW_DAYS),
    limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return get_threat_timeline(window_days=window_days, limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /history/threats failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/incidents", response_model=IncidentTimelineResponse)
def api_get_incident_timeline(
    window_days: int = Query(HISTORY_DEFAULT_WINDOW_DAYS, ge=1, le=HISTORY_MAX_WINDOW_DAYS),
    limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    status: Optional[str] = Query(None, description="Filter by incident status"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return get_incident_timeline(window_days=window_days, limit=limit, status=status, db=db)
    except Exception as exc:
        logger.exception("GET /history/incidents failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/security-score", response_model=SecurityScoreHistoryResponse)
def api_get_security_score_history(
    window_days: int = Query(HISTORY_DEFAULT_WINDOW_DAYS, ge=1, le=HISTORY_MAX_WINDOW_DAYS),
    limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return get_security_score_history(window_days=window_days, limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /history/security-score failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/security-score/latest", response_model=Optional[ScoreSnapshotResponse])
def api_get_latest_score(db: Session = Depends(get_db)) -> Optional[dict[str, Any]]:
    try:
        return get_latest_score(db=db)
    except Exception as exc:
        logger.exception("GET /history/security-score/latest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/vulnerabilities", response_model=VulnerabilityTrendsResponse)
def api_get_vulnerability_trends(
    window_days: int = Query(HISTORY_DEFAULT_WINDOW_DAYS, ge=1, le=HISTORY_MAX_WINDOW_DAYS),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return get_vulnerability_trends(window_days=window_days, db=db)
    except Exception as exc:
        logger.exception("GET /history/vulnerabilities failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/attack-patterns", response_model=AttackPatternHistoryResponse)
def api_get_attack_pattern_history(
    window_days: int = Query(HISTORY_DEFAULT_WINDOW_DAYS, ge=1, le=HISTORY_MAX_WINDOW_DAYS),
    limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return get_attack_pattern_history(window_days=window_days, limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /history/attack-patterns failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status")
def api_get_status() -> dict[str, Any]:
    return get_status()


__all__ = [
    "SecurityScoreSnapshot",
    "ensure_table_exists",
    "record_score_snapshot",
    "get_threat_timeline",
    "get_incident_timeline",
    "get_latest_score",
    "get_score_history",
    "get_security_score_history",
    "get_vulnerability_trends",
    "get_attack_pattern_history",
    "start",
    "stop",
    "get_status",
    "router",
]