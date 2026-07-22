"""
security_reports.py

Comprehensive Cybersecurity Reporting — Lavender Trinetra Platform
=====================================================================

Generates comprehensive cybersecurity reports by reading data already
produced and persisted by Phases 1-4 of the cybersecurity layer. This
module performs NO monitoring, detection, scanning, scoring, or AI
analysis of its own - it strictly aggregates results already computed
by:

    - threat_detector.py            (get_threat_summary - live counts)
    - vulnerability_scan.py         (get_vulnerability_summary - live counts)
    - incident_logger.py            (list_incidents, get_incident_summary)
    - security_recommendations.py   (get_recommendation_summary,
                                       get_recommendations_from_db)
    - security_history.py           (get_threat_timeline, get_incident_timeline,
                                       get_security_score_history,
                                       get_vulnerability_trends,
                                       get_latest_score - all PostgreSQL-backed)

Report types produced:
    - Security Summary
    - Threat Statistics
    - Incident Summary
    - Vulnerability Summary
    - Security Score Trends
    - Recommendation Summary

Also supports export preparation - flattening any of the above (or a
combined full report) into a serializable envelope for the frontend's
Reports -> Export workflow (SecurityReports.jsx), without performing
any file writing/serialization to disk itself.

Exposure: a self-contained FastAPI router (`/api/cybersecurity/reports/*`),
mounted the same way attack_patterns.py, security_recommendations.py,
incident_logger.py and security_history.py mount their own routers in
api/api.py.

Integrates with:
    - backend/config.py                                  (settings)
    - backend/core.py                                     (logging, safe_execute)
    - backend/database/database.py                        (get_db, session_scope)
    - backend/cybersecurity/incident_logger.py
    - backend/cybersecurity/security_recommendations.py
    - backend/cybersecurity/security_history.py
    - backend/cybersecurity/threat_detector.py             (guarded)
    - backend/cybersecurity/vulnerability_scan.py          (guarded)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core import get_logger, safe_execute

from backend.database.database import get_db, session_scope

from backend.cybersecurity import incident_logger
from backend.cybersecurity import security_recommendations
from backend.cybersecurity import security_history

# Guarded per the existing backend/cybersecurity/ convention - live
# threat/vulnerability counts are read from these modules' in-memory
# summaries; historical (PostgreSQL-backed) equivalents come from
# security_history.py regardless of whether these are importable.
try:
    from backend.cybersecurity import threat_detector
except ImportError:  # pragma: no cover - defensive
    threat_detector = None

try:
    from backend.cybersecurity import vulnerability_scan
except ImportError:  # pragma: no cover - defensive
    vulnerability_scan = None

logger = get_logger("lavender_trinetra.cybersecurity.security_reports")


# =====================================================================
# CONFIGURATION
# =====================================================================

REPORT_DEFAULT_WINDOW_DAYS = int(getattr(settings, "SECURITY_REPORT_DEFAULT_WINDOW_DAYS", 7))
REPORT_MAX_WINDOW_DAYS = int(getattr(settings, "SECURITY_REPORT_MAX_WINDOW_DAYS", 365))
REPORT_DEFAULT_LIMIT = int(getattr(settings, "SECURITY_REPORT_DEFAULT_LIMIT", 100))
REPORT_MAX_LIMIT = int(getattr(settings, "SECURITY_REPORT_MAX_LIMIT", 1000))

_SUPPORTED_EXPORT_FORMATS = frozenset({"json", "csv"})


def _resolved_window(window_days: Optional[int]) -> int:
    return min(max(1, window_days or REPORT_DEFAULT_WINDOW_DAYS), REPORT_MAX_WINDOW_DAYS)


def _resolved_limit(limit: int) -> int:
    return max(1, min(limit, REPORT_MAX_LIMIT))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =====================================================================
# SECURITY SUMMARY
# =====================================================================

def generate_security_summary(window_days: Optional[int] = None) -> dict[str, Any]:
    """
    Top-level "at a glance" security summary combining incident
    statistics, the latest persisted security score, and recommendation
    counts - for the Dashboard/Reports overview.
    """
    try:
        incident_stats = incident_logger.get_incident_summary()
        recommendation_stats = security_recommendations.get_recommendation_summary()
        latest_score = security_history.get_latest_score()

        critical_open = sum(
            1
            for incident in incident_logger.list_incidents(
                limit=incident_logger.MAX_INCIDENT_HISTORY, severity="Critical"
            )
            if incident.get("status") != incident_logger.IncidentStatus.RESOLVED
        )

        summary = {
            "generated_at": _now_iso(),
            "window_days": _resolved_window(window_days),
            "incident_totals": incident_stats,
            "critical_open_incidents": critical_open,
            "latest_security_score": latest_score,
            "recommendation_totals": recommendation_stats,
        }

        logger.info(
            "Security summary generated: %d total incident(s), latest score=%s",
            incident_stats.get("total_incidents", 0),
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
    window_days: Optional[int] = None,
    limit: int = REPORT_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Historical threat statistics from security_history.py's PostgreSQL-
    backed threat timeline, plus threat_detector.py's live severity
    summary for context. Performs no detection of its own.
    """
    try:
        resolved_window = _resolved_window(window_days)
        resolved_limit = _resolved_limit(limit)

        timeline = security_history.get_threat_timeline(
            window_days=resolved_window, limit=resolved_limit, db=db
        )
        events = timeline.get("timeline", [])

        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        by_source: dict[str, int] = {}
        daily_counts: dict[str, int] = {}

        for event in events:
            severity = event.get("severity", "Low")
            category = event.get("category", "unknown")
            source = event.get("source_module", "unknown")
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
            by_source[source] = by_source.get(source, 0) + 1
            timestamp = event.get("timestamp")
            if timestamp:
                day = str(timestamp)[:10]
                daily_counts[day] = daily_counts.get(day, 0) + 1

        live_summary = threat_detector.get_threat_summary() if threat_detector is not None else None

        result = {
            "generated_at": _now_iso(),
            "window_days": resolved_window,
            "total_threats": timeline.get("event_count", len(events)),
            "by_severity": by_severity,
            "by_category": by_category,
            "by_source_module": by_source,
            "daily_counts": dict(sorted(daily_counts.items())),
            "live_summary": live_summary,
        }

        logger.info("Threat statistics generated: %d threat-related event(s) in window.", len(events))
        return result

    except Exception as exc:
        logger.exception("Failed to generate threat statistics: %s", exc)
        raise


# =====================================================================
# INCIDENT SUMMARY
# =====================================================================

def generate_incident_summary(limit: int = REPORT_DEFAULT_LIMIT) -> dict[str, Any]:
    """
    Full incident-management summary: aggregate statistics plus the
    most recent incidents, for the Reports workspace.
    """
    try:
        resolved_limit = _resolved_limit(limit)
        stats = incident_logger.get_incident_summary()
        recent = incident_logger.list_incidents(limit=resolved_limit)

        result = {
            "generated_at": _now_iso(),
            "statistics": stats,
            "recent_incidents": recent,
        }

        logger.info(
            "Incident summary generated: %d total, %d returned in recent list.",
            stats.get("total_incidents", 0), len(recent),
        )
        return result

    except Exception as exc:
        logger.exception("Failed to generate incident summary: %s", exc)
        raise


# =====================================================================
# VULNERABILITY SUMMARY
# =====================================================================

def generate_vulnerability_summary(
    window_days: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Historical vulnerability trend data from security_history.py's
    PostgreSQL-backed view, plus vulnerability_scan.py's live severity
    summary for context. Performs no scanning of its own.
    """
    try:
        resolved_window = _resolved_window(window_days)
        trends = security_history.get_vulnerability_trends(window_days=resolved_window, db=db)
        live_summary = vulnerability_scan.get_vulnerability_summary() if vulnerability_scan is not None else None

        result = {
            "generated_at": _now_iso(),
            "window_days": resolved_window,
            "total_findings": trends.get("total_findings", 0),
            "by_category": trends.get("by_category", {}),
            "trend": trends.get("trend", []),
            "live_summary": live_summary,
        }

        logger.info("Vulnerability summary generated: %d finding(s) in window.", result["total_findings"])
        return result

    except Exception as exc:
        logger.exception("Failed to generate vulnerability summary: %s", exc)
        raise


# =====================================================================
# SECURITY SCORE TRENDS
# =====================================================================

def generate_security_score_trends(
    window_days: Optional[int] = None,
    limit: int = REPORT_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Historical security score time series and trend direction, sourced
    entirely from security_history.py's PostgreSQL-backed snapshots
    (persisted once per cycle by threat_detector.run_cycle()).
    """
    try:
        resolved_window = _resolved_window(window_days)
        resolved_limit = _resolved_limit(limit)
        result = security_history.get_security_score_history(
            window_days=resolved_window, limit=resolved_limit, db=db
        )
        logger.info(
            "Security score trends generated: %d sample(s), direction=%s",
            result.get("sample_count", 0), result.get("direction"),
        )
        return result

    except Exception as exc:
        logger.exception("Failed to generate security score trends: %s", exc)
        raise


# =====================================================================
# RECOMMENDATION SUMMARY
# =====================================================================

def generate_recommendation_summary(
    limit: int = REPORT_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """
    Recommendation-management summary: aggregate counts by priority/
    source plus the most recent persisted recommendations.
    """
    try:
        resolved_limit = _resolved_limit(limit)
        summary_counts = security_recommendations.get_recommendation_summary()

        if db is not None:
            recent = security_recommendations.get_recommendations_from_db(db, limit=resolved_limit)
        else:
            with session_scope() as session:
                recent = security_recommendations.get_recommendations_from_db(session, limit=resolved_limit)

        result = {
            "generated_at": _now_iso(),
            "summary": summary_counts,
            "recent_recommendations": recent,
        }

        logger.info(
            "Recommendation summary generated: %d total (live), %d returned from database.",
            summary_counts.get("total", 0), len(recent),
        )
        return result

    except Exception as exc:
        logger.exception("Failed to generate recommendation summary: %s", exc)
        raise


# =====================================================================
# COMBINED / FULL REPORT + EXPORT PREPARATION
# =====================================================================

def generate_full_security_report(
    window_days: Optional[int] = None,
    limit: int = REPORT_DEFAULT_LIMIT,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """Assembles every report section into a single combined report for full export."""
    try:
        resolved_window = _resolved_window(window_days)
        report = {
            "generated_at": _now_iso(),
            "window_days": resolved_window,
            "security_summary": generate_security_summary(window_days=resolved_window),
            "threat_statistics": generate_threat_statistics(window_days=resolved_window, limit=limit, db=db),
            "incident_summary": generate_incident_summary(limit=limit),
            "vulnerability_summary": generate_vulnerability_summary(window_days=resolved_window, db=db),
            "security_score_trends": generate_security_score_trends(
                window_days=resolved_window, limit=limit, db=db
            ),
            "recommendation_summary": generate_recommendation_summary(limit=limit, db=db),
        }
        logger.info("Full security report assembled successfully.")
        return report

    except Exception as exc:
        logger.exception("Failed to assemble full security report: %s", exc)
        raise


def prepare_report_for_export(report: dict[str, Any], export_format: str = "json") -> dict[str, Any]:
    """
    Wraps a generated report into a standard export envelope. Performs
    no actual file writing/serialization to disk - only guarantees the
    payload is a flat, JSON-serializable structure with export metadata
    attached, for the frontend's Export Reports action to consume.
    """
    normalized_format = (export_format or "json").lower()
    if normalized_format not in _SUPPORTED_EXPORT_FORMATS:
        raise ValueError(
            f"Unsupported export format '{export_format}'. Supported formats: "
            f"{sorted(_SUPPORTED_EXPORT_FORMATS)}"
        )

    return {
        "export_format": normalized_format,
        "exported_at": _now_iso(),
        "report": report,
    }


# =====================================================================
# FASTAPI ROUTER
# =====================================================================

router = APIRouter(prefix="/api/cybersecurity/reports", tags=["Security Reports"])


@router.get("/summary")
async def api_get_security_summary(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
):
    try:
        return generate_security_summary(window_days=window_days)
    except Exception as exc:
        logger.exception("GET /reports/summary failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/threats")
async def api_get_threat_statistics(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
):
    try:
        return generate_threat_statistics(window_days=window_days, limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /reports/threats failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/incidents")
async def api_get_incident_summary(
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
):
    try:
        return generate_incident_summary(limit=limit)
    except Exception as exc:
        logger.exception("GET /reports/incidents failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/vulnerabilities")
async def api_get_vulnerability_summary(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    db: Session = Depends(get_db),
):
    try:
        return generate_vulnerability_summary(window_days=window_days, db=db)
    except Exception as exc:
        logger.exception("GET /reports/vulnerabilities failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/security-score-trends")
async def api_get_security_score_trends(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
):
    try:
        return generate_security_score_trends(window_days=window_days, limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /reports/security-score-trends failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recommendations")
async def api_get_recommendation_summary(
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
):
    try:
        return generate_recommendation_summary(limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /reports/recommendations failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/full")
async def api_get_full_report(
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
):
    try:
        return generate_full_security_report(window_days=window_days, limit=limit, db=db)
    except Exception as exc:
        logger.exception("GET /reports/full failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/export")
async def api_prepare_report_export(
    export_format: str = Query("json", description="One of: json, csv"),
    window_days: int = Query(REPORT_DEFAULT_WINDOW_DAYS, ge=1, le=REPORT_MAX_WINDOW_DAYS),
    limit: int = Query(REPORT_DEFAULT_LIMIT, ge=1, le=REPORT_MAX_LIMIT),
    db: Session = Depends(get_db),
):
    try:
        report = generate_full_security_report(window_days=window_days, limit=limit, db=db)
        return prepare_report_for_export(report, export_format=export_format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("GET /reports/export failed")
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