"""
backend/cybersecurity/incident_logger.py

Incident Logger — Lavender Trinetra Cybersecurity Platform
=====================================================================

Centralizes cybersecurity incident management. This module does NOT
perform monitoring, scanning, or threat detection of any kind - it
exclusively consumes already-produced security events/results from:

    - security_engine.py        (orchestrated cycle results)
    - threat_detector.py        (detected threats)
    - intrusion_detector.py     (intrusion events)
    - vulnerability_scan.py     (vulnerability findings)
    - security_score.py         (score/grade context, for correlation)

...and turns confirmed events into durable, queryable incident records:

    Incident ID · Timestamp · Severity · Category · Source Module ·
    Description · Status (Open / In Progress / Resolved) ·
    Resolution Notes

Incidents are persisted to PostgreSQL (via the shared SQLAlchemy Base/
session infrastructure in database/database.py) and exposed through a
FastAPI router intended to be mounted by api/routes.py or api/api.py.

Integrates with:
    - backend/config.py               (settings)
    - backend/core.py                 (logging, safe_execute, utc_now)
    - backend/database/database.py    (Base, SessionLocal, get_db)
    - backend/cybersecurity/security_engine.py (calls record_incident /
      record_incidents_from_cycle after each orchestration cycle)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Index, String, Text, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core import get_logger, safe_execute, utc_now

try:
    from backend.database.database import Base, SessionLocal
except ImportError:  # pragma: no cover - fallback for non-package execution
    from database.database import Base, SessionLocal  # type: ignore

logger = get_logger("lavender_trinetra.cybersecurity.incident_logger")


# =====================================================================
# CONSTANTS / CONFIGURATION
# =====================================================================

class IncidentStatus:
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"

    ALL = (OPEN, IN_PROGRESS, RESOLVED)


class IncidentSeverity:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

    ALL = (LOW, MEDIUM, HIGH, CRITICAL)


# Minimum severity (inclusive) at which an incoming security event is
# recorded as a confirmed incident, rather than silently ignored. Kept
# configurable via config.py without requiring a code change.
_SEVERITY_RANK = {
    IncidentSeverity.LOW: 1,
    IncidentSeverity.MEDIUM: 2,
    IncidentSeverity.HIGH: 3,
    IncidentSeverity.CRITICAL: 4,
}

INCIDENT_MIN_SEVERITY: str = getattr(
    settings, "INCIDENT_MIN_SEVERITY", IncidentSeverity.MEDIUM
)
INCIDENT_DEFAULT_PAGE_SIZE: int = int(getattr(settings, "INCIDENT_DEFAULT_PAGE_SIZE", 100))
INCIDENT_MAX_PAGE_SIZE: int = int(getattr(settings, "INCIDENT_MAX_PAGE_SIZE", 500))


def _meets_confirmation_threshold(severity: str) -> bool:
    return _SEVERITY_RANK.get(severity, 1) >= _SEVERITY_RANK.get(INCIDENT_MIN_SEVERITY, 2)


# =====================================================================
# ORM MODEL
# =====================================================================

class SecurityIncident(Base):
    """
    One confirmed cybersecurity incident. Shares the same declarative
    Base as database/models.py so it is created automatically by the
    existing init_db()/Base.metadata.create_all() call, without this
    module needing its own migration bootstrap.
    """

    __tablename__ = "security_incidents"

    incident_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    severity = Column(String(20), nullable=False, default=IncidentSeverity.LOW, index=True)
    category = Column(String(100), nullable=False, default="uncategorized", index=True)
    source_module = Column(String(100), nullable=False, default="unknown", index=True)
    description = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default=IncidentStatus.OPEN, index=True)
    resolution_notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_security_incidents_status_severity", "status", "severity"),
        Index("ix_security_incidents_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<SecurityIncident id={self.incident_id} severity={self.severity} "
            f"category={self.category} status={self.status}>"
        )


def _incident_to_dict(record: SecurityIncident) -> dict[str, Any]:
    return {
        "incident_id": record.incident_id,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "severity": record.severity,
        "category": record.category,
        "source_module": record.source_module,
        "description": record.description,
        "status": record.status,
        "resolution_notes": record.resolution_notes,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


# =====================================================================
# SESSION RESOLUTION HELPER (mirrors database/crud.py conventions)
# =====================================================================

@contextmanager
def _resolve_session(db: Optional[Session]) -> Generator[tuple[Session, bool], None, None]:
    """
    Yields a (session, owns_session) pair. If `db` is supplied (e.g. a
    FastAPI Depends(get_db) session), it is used as-is. Otherwise a new
    session is opened, committed, and closed here - the path used when
    security_engine.py and other backend modules call these functions
    without a request-scoped session.
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
# CORE INCIDENT CRUD
# =====================================================================

def create_incident(
    severity: str,
    category: str,
    source_module: str,
    description: str,
    status: str = IncidentStatus.OPEN,
    resolution_notes: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Persists a single confirmed security incident.

    Args:
        severity: One of IncidentSeverity.ALL.
        category: Short category label (e.g. "intrusion", "vulnerability").
        source_module: Name of the module that confirmed the event
            (e.g. "threat_detector", "intrusion_detector").
        description: Human-readable incident description.
        status: One of IncidentStatus.ALL. Defaults to Open.
        resolution_notes: Optional notes, typically set on update.
        timestamp: Event time; defaults to current UTC time.
        db: Optional injected Session.

    Returns:
        Dict representation of the created incident.
    """
    try:
        if severity not in IncidentSeverity.ALL:
            logger.warning("Unrecognized severity '%s'; defaulting to Low.", severity)
            severity = IncidentSeverity.LOW
        if status not in IncidentStatus.ALL:
            logger.warning("Unrecognized status '%s'; defaulting to Open.", status)
            status = IncidentStatus.OPEN

        with _resolve_session(db) as (session, _owns_session):
            record = SecurityIncident(
                incident_id=str(uuid.uuid4()),
                timestamp=timestamp or utc_now().replace(tzinfo=None),
                severity=severity,
                category=category,
                source_module=source_module,
                description=description,
                status=status,
                resolution_notes=resolution_notes,
            )
            session.add(record)
            session.flush()
            result = _incident_to_dict(record)

        logger.info(
            "Incident recorded: id=%s severity=%s category=%s source=%s",
            result["incident_id"], severity, category, source_module,
        )
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to create incident: %s", exc)
        raise


def get_incident(incident_id: str, db: Optional[Session] = None) -> Optional[dict[str, Any]]:
    """Retrieves a single incident by ID, or None if not found."""
    try:
        with _resolve_session(db) as (session, _owns_session):
            record = session.get(SecurityIncident, incident_id)
            return _incident_to_dict(record) if record else None
    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve incident %s: %s", incident_id, exc)
        raise


def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    source_module: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = INCIDENT_DEFAULT_PAGE_SIZE,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Lists incidents, most recent first, with optional filters.

    Args:
        status, severity, category, source_module: Optional exact-match filters.
        since: If provided, only incidents with timestamp >= this value.
        limit: Maximum number of rows to return (capped by INCIDENT_MAX_PAGE_SIZE).
        db: Optional injected Session.

    Returns:
        List of incident dicts.
    """
    try:
        capped_limit = max(1, min(limit, INCIDENT_MAX_PAGE_SIZE))
        with _resolve_session(db) as (session, _owns_session):
            query = session.query(SecurityIncident)
            if status is not None:
                query = query.filter(SecurityIncident.status == status)
            if severity is not None:
                query = query.filter(SecurityIncident.severity == severity)
            if category is not None:
                query = query.filter(SecurityIncident.category == category)
            if source_module is not None:
                query = query.filter(SecurityIncident.source_module == source_module)
            if since is not None:
                query = query.filter(SecurityIncident.timestamp >= since)

            rows = (
                query.order_by(SecurityIncident.timestamp.desc())
                .limit(capped_limit)
                .all()
            )
            return [_incident_to_dict(r) for r in rows]

    except SQLAlchemyError as exc:
        logger.exception("Failed to list incidents: %s", exc)
        raise


def update_incident_status(
    incident_id: str,
    status: str,
    resolution_notes: Optional[str] = None,
    db: Optional[Session] = None,
) -> Optional[dict[str, Any]]:
    """
    Updates an incident's status and, optionally, its resolution notes.

    Args:
        incident_id: Target incident ID.
        status: One of IncidentStatus.ALL.
        resolution_notes: Optional notes to attach (e.g. remediation summary).
        db: Optional injected Session.

    Returns:
        Dict representation of the updated incident, or None if not found.
    """
    try:
        if status not in IncidentStatus.ALL:
            raise ValueError(f"Invalid status '{status}'. Must be one of {IncidentStatus.ALL}.")

        with _resolve_session(db) as (session, _owns_session):
            record = session.get(SecurityIncident, incident_id)
            if record is None:
                logger.warning("update_incident_status: incident id=%s not found", incident_id)
                return None

            record.status = status
            if resolution_notes is not None:
                record.resolution_notes = resolution_notes
            record.updated_at = utc_now().replace(tzinfo=None)

            session.add(record)
            session.flush()
            result = _incident_to_dict(record)

        logger.info("Incident updated: id=%s status=%s", incident_id, status)
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to update incident %s: %s", incident_id, exc)
        raise


def get_incident_statistics(db: Optional[Session] = None) -> dict[str, Any]:
    """
    Returns aggregate incident statistics for dashboard/summary use:
    total incidents, counts by status/severity, and open-incident count.
    """
    try:
        with _resolve_session(db) as (session, _owns_session):
            total = session.query(func.count(SecurityIncident.incident_id)).scalar() or 0

            status_rows = (
                session.query(SecurityIncident.status, func.count(SecurityIncident.incident_id))
                .group_by(SecurityIncident.status)
                .all()
            )
            severity_rows = (
                session.query(SecurityIncident.severity, func.count(SecurityIncident.incident_id))
                .group_by(SecurityIncident.severity)
                .all()
            )

            by_status = {status: count for status, count in status_rows}
            by_severity = {severity: count for severity, count in severity_rows}

            return {
                "total_incidents": total,
                "open_incidents": by_status.get(IncidentStatus.OPEN, 0),
                "in_progress_incidents": by_status.get(IncidentStatus.IN_PROGRESS, 0),
                "resolved_incidents": by_status.get(IncidentStatus.RESOLVED, 0),
                "by_status": by_status,
                "by_severity": by_severity,
            }

    except SQLAlchemyError as exc:
        logger.exception("Failed to compute incident statistics: %s", exc)
        raise


# =====================================================================
# REUSABLE INTEGRATION FUNCTIONS FOR security_engine.py
# =====================================================================

def record_incident(
    severity: str,
    category: str,
    source_module: str,
    description: str,
    db: Optional[Session] = None,
) -> Optional[dict[str, Any]]:
    """
    Convenience entry point for other cybersecurity modules to log a
    single confirmed incident. Applies the configured minimum-severity
    confirmation threshold - events below it are logged (debug) but
    not persisted as incidents.
    """
    with safe_execute(f"record_incident:{source_module}"):
        if not _meets_confirmation_threshold(severity):
            logger.debug(
                "Event below confirmation threshold, not recorded: severity=%s source=%s",
                severity, source_module,
            )
            return None
        return create_incident(
            severity=severity,
            category=category,
            source_module=source_module,
            description=description,
            db=db,
        )
    return None


def record_incidents_from_cycle(
    cycle_result: dict[str, Any],
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    """
    Consumes one security_engine.py orchestration cycle_result and
    records a confirmed incident for every qualifying finding across
    threats, intrusions, and vulnerabilities. Performs no detection -
    purely interprets results already produced upstream.

    Expected (optional) cycle_result keys:
        threats: list of dicts from threat_detector.py
        intrusions: list of dicts from intrusion_detector.py
        vulnerabilities: list of dicts from vulnerability_scan.py

    Returns:
        List of created incident dicts (only those meeting the
        confirmation threshold).
    """
    created: list[dict[str, Any]] = []

    with safe_execute("record_incidents_from_cycle"):
        for threat in cycle_result.get("threats", []) or []:
            incident = record_incident(
                severity=threat.get("severity", IncidentSeverity.LOW),
                category=threat.get("category", "threat"),
                source_module="threat_detector",
                description=threat.get("description")
                or threat.get("explanation")
                or "Threat detected.",
                db=db,
            )
            if incident:
                created.append(incident)

        for intrusion in cycle_result.get("intrusions", []) or []:
            incident = record_incident(
                severity=intrusion.get("severity", IncidentSeverity.MEDIUM),
                category=intrusion.get("category", "intrusion"),
                source_module="intrusion_detector",
                description=intrusion.get("description")
                or intrusion.get("explanation")
                or "Intrusion event detected.",
                db=db,
            )
            if incident:
                created.append(incident)

        for vulnerability in cycle_result.get("vulnerabilities", []) or []:
            incident = record_incident(
                severity=vulnerability.get("severity", IncidentSeverity.LOW),
                category=vulnerability.get("category", "vulnerability"),
                source_module="vulnerability_scan",
                description=vulnerability.get("description")
                or vulnerability.get("explanation")
                or "Vulnerability finding.",
                db=db,
            )
            if incident:
                created.append(incident)

        security_score = cycle_result.get("security_score")
        if isinstance(security_score, dict) and security_score.get("grade") in ("Poor", "Critical"):
            incident = record_incident(
                severity=IncidentSeverity.HIGH
                if security_score.get("grade") == "Poor"
                else IncidentSeverity.CRITICAL,
                category="security_score",
                source_module="security_score",
                description=(
                    f"Overall security score dropped to {security_score.get('score')} "
                    f"({security_score.get('grade')})."
                ),
                db=db,
            )
            if incident:
                created.append(incident)

    if created:
        logger.info("Recorded %d incident(s) from security cycle.", len(created))
    return created


# =====================================================================
# PYDANTIC SCHEMAS (FastAPI request/response models)
# =====================================================================

class IncidentResponse(BaseModel):
    incident_id: str
    timestamp: Optional[str] = None
    severity: str
    category: str
    source_module: str
    description: str
    status: str
    resolution_notes: Optional[str] = None
    updated_at: Optional[str] = None


class IncidentStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="One of: Open, In Progress, Resolved")
    resolution_notes: Optional[str] = Field(None, description="Optional resolution/remediation notes")


class IncidentStatisticsResponse(BaseModel):
    total_incidents: int
    open_incidents: int
    in_progress_incidents: int
    resolved_incidents: int
    by_status: dict[str, int]
    by_severity: dict[str, int]


# =====================================================================
# FASTAPI ROUTER
# =====================================================================

router = APIRouter(prefix="/api/cybersecurity/incidents", tags=["Cybersecurity Incidents"])


@router.get("", response_model=list[IncidentResponse])
def api_list_incidents(
    status: Optional[str] = Query(None, description="Filter by status"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source_module: Optional[str] = Query(None, description="Filter by source module"),
    limit: int = Query(INCIDENT_DEFAULT_PAGE_SIZE, ge=1, le=INCIDENT_MAX_PAGE_SIZE),
) -> list[dict[str, Any]]:
    try:
        return list_incidents(
            status=status,
            severity=severity,
            category=category,
            source_module=source_module,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("GET /incidents failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/statistics", response_model=IncidentStatisticsResponse)
def api_get_incident_statistics() -> dict[str, Any]:
    try:
        return get_incident_statistics()
    except Exception as exc:
        logger.exception("GET /incidents/statistics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{incident_id}", response_model=IncidentResponse)
def api_get_incident(incident_id: str) -> dict[str, Any]:
    try:
        incident = get_incident(incident_id)
    except Exception as exc:
        logger.exception("GET /incidents/%s failed: %s", incident_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.put("/{incident_id}/status", response_model=IncidentResponse)
def api_update_incident_status(incident_id: str, payload: IncidentStatusUpdateRequest) -> dict[str, Any]:
    try:
        incident = update_incident_status(
            incident_id=incident_id,
            status=payload.status,
            resolution_notes=payload.resolution_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("PUT /incidents/%s/status failed: %s", incident_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


__all__ = [
    "IncidentStatus",
    "IncidentSeverity",
    "SecurityIncident",
    "create_incident",
    "get_incident",
    "list_incidents",
    "update_incident_status",
    "get_incident_statistics",
    "record_incident",
    "record_incidents_from_cycle",
    "router",
]