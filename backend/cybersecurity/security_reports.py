"""
backend/cybersecurity/security_reports.py

Security Reports — Lavender Trinetra Cybersecurity Platform
=====================================================================

Generates comprehensive cybersecurity reports from historical data
already persisted in PostgreSQL. This module performs NO monitoring,
detection, scanning, scoring, or AI analysis of its own - it strictly
reads and aggregates data already produced and stored by:

    - incident_logger.py          (backend.cybersecurity.SecurityIncident)
    - security_recommendations.py (backend.cybersecurity.SecurityRecommendationRecord)
    - security_score.py           (in-memory score history, pending
                                    PostgreSQL persistence - see the
                                    `security_history` integration hook
                                    below, wired in a later phase)

Report types produced:

    - Security Summary
    - Threat Statistics
    - Incident Summary
    - Vulnerability Summary
    - Security Score Trends
    - Recommendation Summary

Also supports "export preparation" - flattening any of the above (or
a combined full report) into a serializable envelope suitable for
handoff to the frontend's Reports -> Export workspace (CSV/JSON).

Integrates with:
    - backend/config.py                          (settings)
    - backend/core.py                             (logging, safe_execute)
    - backend/database/database.py                (get_db, session_scope)
    - backend/cybersecurity/incident_logger.py     (SecurityIncident, stats)
    - backend/cybersecurity/security_recommendations.py
      (SecurityRecommendationRecord, get_recommendations_from_db)
    - backend/cybersecurity/security_score.py      (in-memory score history)
    - backend/cybersecurity/security_history.py    (future: PostgreSQL-backed
      score/threat/vulnerability history - guarded import, wired later)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core import get_logger, safe_execute, utc_now

from backend.database.database import get_db, session_scope

from backend.cybersecurity.incident_logger import (
    IncidentSeverity,
    IncidentStatus,
    SecurityIncident,
    get_incident_statistics,
    list_incidents,
)
from backend.cybersecurity.security_recommendations import (
    SecurityRecommendationRecord,
    get_recommendation_summary,
    get_recommendations_from_db,
)
from backend.cybersecurity import security_score

# ---------------------------------------------------------------------
# Future integration point (wired in a later phase): a PostgreSQL-backed
# history module for security score / threat / vulnerability snapshots.
# Guarded so this module works today against in-memory security_score
# history and the SecurityIncident table, and transparently upgrades
# to full DB-backed trend data once security_history.py exists.
# ---------------------------------------------------------------------
try:
    from backend.cybersecurity import security_history
except ImportError:  # pragma: no cover - not yet implemented
    security_history = None

logger = get_logger("lavender_trinetra.cybersecurity.security_reports")


# =====================================================================
# CONFIGURATION
# =====================================================================

REPORT_DEFAULT_WINDOW_DAYS = int(getattr(settings, "SECURITY_REPORT_DEFAULT_WINDOW_DAYS", 7))
REPORT_MAX_WINDOW_DAYS = int(getattr(settings, "SECURITY_REPORT_MAX_WINDOW_DAYS", 365))
REPORT_DEFAULT_LIMIT = int(getattr(settings, "SECURITY_REPORT_DEFAULT_LIMIT", 200))
REPORT_MAX_LIMIT = int(getattr(settings, "SECURITY_REPORT_MAX_LIMIT", 1000))

# Categories/source modules in SecurityIncident that represent
# "threats" vs "vulnerabilities", per incident_logger.record_incidents_from_cycle().
_THREAT_SOURCE_MODULES = frozenset({"threat_detector", "intrusion_detector", "security_score"})
_VULNERABILITY_SOURCE_MODULE = "vulnerability_scan"

_SUPPORTED_EXPORT_FORMATS = frozenset({"json", "csv"})


def _window_since(days: Optional[int]) -> datetime:
    resolved_days = min(max(1, days or REPORT_DEFAULT_WINDOW_DAYS), REPORT_MAX_WINDOW_DAYS)
    return (utc_now() - timedelta(days=resolved_days)).replace(tzinfo=None)


# =====================================================================
# SECURITY SUMMARY
# =====================================================================

def generate_security_summary(db: Optional[Session] = None, window_days: Optional[int] = None) -> dict[str, Any]:
    """
    Produces a single top-level "at a glance" security summary,
    combining incident statistics, the latest security score, and
    recommendation counts. Intended for the Dashboard/Reports overview.
    """
    try:
        since = _window_since(window_days)

        with safe_execute("generate_security_summary", reraise=True):
            incident_stats = get_incident_statistics(db=db)
            recommendation_stats = get_recommendation_summary()
            latest_score = _get_latest_score()

            with _resolve_session(db) as (session, _owns_session):
                incidents_in_window = (
                    session.query(func.count(SecurityIncident.incident_id))
                    .filter(SecurityIncident.timestamp >= since)
                    .scalar()
                    or 0
                )
                critical_open = (
                    session.query(func.count(SecurityIncident.incident_id))
                    .filter(
                        SecurityIncident.status != IncidentStatus.RESOLVED,
                        SecurityIncident.severity == IncidentSeverity.CRITICAL,
                    )
                    .scalar()
                    or 0
                )

            summary = {
                "generated_at": utc_now().isoformat(),
                "window_days": min(max(1, window_days or REPORT_DEFAULT_WINDOW_DAYS), REPORT_MAX_WINDOW_DAYS),
                "incident_totals": incident_stats,
                "incidents_in_window": incidents_in_window,
                "critical_open_incidents": critical_open,
                "latest_security_score": latest_score,
                "recommendation_totals": recommendation_stats,
            }

        logger.info(
            "Security summary generated: %d total incident(s), %d critical open, latest score=%s",
            incident_stats.get("total_incidents", 0),
            critical_open,
            latest_score.get("score") if latest_score else None,
        )
        return summary

    except Exception as exc:
        logger.exception("Failed to generate security summary: %s", exc)
        raise


# =====================================================================
# THREAT STATISTICS
# =====================================================================

def generate_threat_statistics(
    db: Optional[Session] = None,
    window_days: Optional[int] = None,
) -> dict[str, Any]:
    """
    Aggregates historical threat-related incidents (as confirmed and
    persisted by incident_logger.py from threat_detector.py,
    intrusion_detector.py, and security_score.py) into statistics by
    severity, category, and source module over the requested window.
    """
    try:
        since = _window_since(window_days)

        with _resolve_session(db) as (session, _owns_session):
            rows = (
                session.query(SecurityIncident)
                .filter(
                    SecurityIncident.source_module.in_(_THREAT_SOURCE_MODULES),
                    SecurityIncident.timestamp >= since,
                )
                .order_by(SecurityIncident.timestamp.desc())
                .all()
            )

        by_severity: dict[str, int] = defaultdict(int)
        by_category: dict[str, int] = defaultdict(int)
        by_source: dict[str, int] = defaultdict(int)
        daily_counts: dict[str, int] = defaultdict(int)

        for row in rows:
            by_severity[row.severity] += 1
            by_category[row.category] += 1
            by_source[row.source_module] += 1
            if row.timestamp:
                daily_counts[row.timestamp.date().isoformat()] += 1

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or REPORT_DEFAULT_WINDOW_DAYS), REPORT_MAX_WINDOW_DAYS),
            "total_threats": len(rows),
            "by_severity": dict(by_severity),
            "by_category": dict(by_category),
            "by_source_module": dict(by_source),
            "daily_counts": dict(sorted(daily_counts.items())),
        }

        logger.info("Threat statistics generated: %d threat-related incident(s) in window.", len(rows))
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to generate threat statistics: %s", exc)
        raise


# =====================================================================
# INCIDENT SUMMARY
# =====================================================================

def generate_incident_summary(
    db: Optional[Session] = None,
    limit: int = REPORT_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """
    Produces a full incident-management summary: aggregate statistics
    plus the most recent incidents, for the Reports workspace.
    """
    try:
        capped_limit = max(1, min(limit, REPORT_MAX_LIMIT))
        stats = get_incident_statistics(db=db)
        recent = list_incidents(limit=capped_limit, db=db)

        result = {
            "generated_at": utc_now().isoformat(),
            "statistics": stats,
            "recent_incidents": recent,
        }

        logger.info("Incident summary generated: %d total, %d returned in recent list.",
                    stats.get("total_incidents", 0), len(recent))
        return result

    except Exception as exc:
        logger.exception("Failed to generate incident summary: %s", exc)
        raise


# =====================================================================
# VULNERABILITY SUMMARY
# =====================================================================

def generate_vulnerability_summary(
    db: Optional[Session] = None,
    window_days: Optional[int] = None,
) -> dict[str, Any]:
    """
    Aggregates historical vulnerability-related incidents (confirmed
    and persisted by incident_logger.py from vulnerability_scan.py
    findings) into statistics by severity and category over the
    requested window.
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
                .order_by(SecurityIncident.timestamp.desc())
                .all()
            )

        by_severity: dict[str, int] = defaultdict(int)
        by_category: dict[str, int] = defaultdict(int)
        unresolved_count = 0

        for row in rows:
            by_severity[row.severity] += 1
            by_category[row.category] += 1
            if row.status != IncidentStatus.RESOLVED:
                unresolved_count += 1

        result = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or REPORT_DEFAULT_WINDOW_DAYS), REPORT_MAX_WINDOW_DAYS),
            "total_findings": len(rows),
            "unresolved_findings": unresolved_count,
            "by_severity": dict(by_severity),
            "by_category": dict(by_category),
        }

        logger.info("Vulnerability summary generated: %d finding(s) in window.", len(rows))
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to generate vulnerability summary: %s", exc)
        raise


# =====================================================================
# SECURITY SCORE TRENDS
# =====================================================================

def _get_latest_score() -> Optional[dict[str, Any]]:
    """
    Resolves the latest security score, preferring a PostgreSQL-backed
    source (security_history.py, once integrated) and falling back to
    security_score.py's in-memory buffer.
    """
    if security_history is not None and hasattr(security_history, "get_latest_score"):
        with safe_execute("security_reports._get_latest_score(history)"):
            latest = security_history.get_latest_score()
            if latest is not None:
                return latest
    return security_score.get_latest_score()


def _get_score_history(limit: int) -> list[dict[str, Any]]:
    """
    Resolves recent security score history, preferring a
    PostgreSQL-backed source (security_history.py, once integrated)
    and falling back to security_score.py's in-memory buffer.
    """
    if security_history is not None and hasattr(security_history, "get_score_history"):
        with safe_execute("security_reports._get_score_history(history)"):
            history = security_history.get_score_history(limit=limit)
            if history:
                return history
    return security_score.get_score_history(limit=limit)


def generate_security_score_trends(limit: int = REPORT_DEFAULT_LIMIT) -> dict[str, Any]:
    """
    Returns a time series of historical security scores, along with a
    trend direction summary. Currently sourced from security_score.py's
    in-memory history; transparently upgrades to PostgreSQL-backed
    history once security_history.py is integrated (no caller changes
    required).
    """
    try:
        capped_limit = max(1, min(limit, REPORT_MAX_LIMIT))
        history = _get_score_history(limit=capped_limit)

        direction = "stable"
        change = 0.0
        if len(history) >= 2:
            first_score = history[0].get("score", 0.0)
            last_score = history[-1].get("score", 0.0)
            change = round(last_score - first_score, 2)
            if change > 1.0:
                direction = "improving"
            elif change < -1.0:
                direction = "declining"

        result = {
            "generated_at": utc_now().isoformat(),
            "sample_count": len(history),
            "direction": direction,
            "change": change,
            "series": history,
            "source": "security_history" if security_history is not None else "security_score (in-memory)",
        }

        logger.info("Security score trends generated: %d sample(s), direction=%s", len(history), direction)
        return result

    except Exception as exc:
        logger.exception("Failed to generate security score trends: %s", exc)
        raise


# =====================================================================
# RECOMMENDATION SUMMARY
# =====================================================================

def generate_recommendation_summary(
    db: Optional[Session] = None,
    limit: int = REPORT_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """
    Produces a recommendation-management summary: aggregate counts by
    priority/source plus the most recent persisted recommendations.
    """
    try:
        capped_limit = max(1, min(limit, REPORT_MAX_LIMIT))
        summary_counts = get_recommendation_summary()

        with _resolve_session(db) as (session, _owns_session):
            recent = get_recommendations_from_db(session, limit=capped_limit)

        result = {
            "generated_at": utc_now().isoformat(),
            "summary": summary_counts,
            "recent_recommendations": recent,
        }

        logger.info(
            "Recommendation summary generated: %d total (in-memory), %d returned from database.",
            summary_counts.get("total", 0), len(recent),
        )
        return result

    except SQLAlchemyError as exc:
        logger.exception("Failed to generate recommendation summary: %s", exc)
        raise


# =====================================================================
# COMBINED / FULL REPORT + EXPORT PREPARATION
# =====================================================================

def generate_full_security_report(
    db: Optional[Session] = None,
    window_days: Optional[int] = None,
    limit: int = REPORT_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """
    Assembles every report section into a single combined report,
    suitable for a "full export" request from the Reports workspace.
    """
    try:
        report = {
            "generated_at": utc_now().isoformat(),
            "window_days": min(max(1, window_days or REPORT_DEFAULT_WINDOW_DAYS), REPORT_MAX_WINDOW_DAYS),
            "security_summary": generate_security_summary(db=db, window_days=window_days),
            "threat_statistics": generate_threat_statistics(db=db, window_days=window_days),
            "incident_summary": generate_incident_summary(db=db, limit=limit),
            "vulnerability_summary": generate_vulnerability_summary(db=db, window_days=window_days),
            "security_score_trends": generate_security_score_trends(limit=limit),
            "recommendation_summary": generate_recommendation_summary(db=db, limit=limit),
        }
        logger.info("Full security report assembled successfully.")
        return report

    except Exception as exc:
        logger.exception("Failed to assemble full security report: %s", exc)
        raise


def prepare_report_for_export(
    report: dict[str, Any],
    export_format: str = "json",
) -> dict[str, Any]:
    """
    Wraps a generated report (any of the section reports above, or the
    combined full report) into a standard export envelope. Performs no
    actual file writing/serialization to disk - that responsibility
    belongs to reports/Export.jsx's backing endpoint - this function
    only guarantees the payload is a flat, JSON-serializable structure
    with export metadata attached.
    """
    normalized_format = (export_format or "json").lower()
    if normalized_format not in _SUPPORTED_EXPORT_FORMATS:
        raise ValueError(
            f"Unsupported export format '{export_format}'. Supported formats: "
            f"{sorted(_SUPPORTED_EXPORT_FORMATS)}"
        )

    return {
        "export_format": normalized_format,
        "exported_at": utc_now().isoformat(),
        "report": report,
    }


# =====================================================================
# SESSION RESOLUTION HELPER (mirrors crud.py / incident_logger.py conventions)
# =====================================================================

from contextlib import contextmanager
from typing import Generator

from backend.database.database import SessionLocal


@contextmanager
def _resolve_session(db: Optional[Session]) -> Generator[tuple[Session, bool], None, None]:
    """
    Yields a (session, owns_session) pair. If `db` is supplied (e.g. a
    FastAPI Depends(get_db) session), it is used as-is. Otherwise a new
    session is opened and closed here for standalone/report-script use.
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
# PYDANTIC RESPONSE SCHEMAS
# =====================================================================

class SecuritySummaryResponse(BaseModel):
    generated_at: str
    window_days: int
    incident_totals: dict[str, Any]
    incidents_in_window: int
    critical_open_incidents: int
    latest_security_score: Optional[dict[str, Any]] = None
    recommendation_totals: dict[str, Any]


class ThreatStatisticsResponse(BaseModel):
    generated_at: str
    window_days: int
    total_threats: int
    by_severity: dict[str, int]
    by_category: dict[str, int]
    by_source_module: dict[str, int]
    daily_counts: dict[str, int]


class IncidentSummaryResponse(BaseModel):
    generated_at: str
    statistics: dict[str, Any]
    recent_incidents: list[dict[str, Any]]


class VulnerabilitySummaryResponse(BaseModel):
    generated_at: str
    window_days: int
    total_findings: int
    unresolved_findings: int
    by_severity: dict[str, int]
    by_category: dict[str, int]


class SecurityScoreTrendsResponse(BaseModel):
    generated_at: str
    sample_count: int
    direction: str
    change: float
    series: list[dict[str, Any]]
    source: str


class RecommendationSummaryResponse(BaseModel):
    generated_at: str
    summary: dict[str, Any]
    recent_recommendations: list[dict[str, Any]]


class ExportEnvelopeResponse(BaseModel):
    export_format: str
    exported_at: str
    report: dict[str, Any]


# =====================================================================
# FASTAPI ROUTER
# =====================================================================

router = APIRouter(prefix="/api/cybersecurity/reports", tags=["Cybersecurity Reports"])


@router.get("/summary", response_model=SecuritySummaryResponse)
def api_get_security_summary(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return generate_security_summary(db=db, window_days=window_days)
    except Exception as exc:
        logger.exception("GET /reports/summary failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/threats", response_model=ThreatStatisticsResponse)
def api_get_threat_statistics(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return generate_threat_statistics(db=db, window_days=window_days)
    except Exception as exc:
        logger.exception("GET /reports/threats failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/incidents", response_model=IncidentSummaryResponse)
def api_get_incident_summary(
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return generate_incident_summary(db=db, limit=limit)
    except Exception as exc:
        logger.exception("GET /reports/incidents failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/vulnerabilities", response_model=VulnerabilitySummaryResponse)
def api_get_vulnerability_summary(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return generate_vulnerability_summary(db=db, window_days=window_days)
    except Exception as exc:
        logger.exception("GET /reports/vulnerabilities failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/security-score-trends", response_model=SecurityScoreTrendsResponse)
def api_get_security_score_trends(
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
) -> dict[str, Any]:
    try:
        return generate_security_score_trends(limit=limit)
    except Exception as exc:
        logger.exception("GET /reports/security-score-trends failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recommendations", response_model=RecommendationSummaryResponse)
def api_get_recommendation_summary(
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return generate_recommendation_summary(db=db, limit=limit)
    except Exception as exc:
        logger.exception("GET /reports/recommendations failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/full")
def api_get_full_report(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return generate_full_security_report(db=db, window_days=window_days, limit=limit)
    except Exception as exc:
        logger.exception("GET /reports/full failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/export", response_model=ExportEnvelopeResponse)
def api_prepare_report_export(
    export_format: str = Query("json", description="One of: json, csv"),
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        report = generate_full_security_report(db=db, window_days=window_days, limit=limit)
        return prepare_report_for_export(report, export_format=export_format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("GET /reports/export failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


__all__ = [
    "generate_security_summary",
    "generate_threat_statistics",
    "generate_incident_summary",
    "generate_vulnerability_summary",
    "generate_security_score_trends",
    "generate_recommendation_summary",
    "generate_full_security_report",
    "prepare_report_for_export",
    "router",
]