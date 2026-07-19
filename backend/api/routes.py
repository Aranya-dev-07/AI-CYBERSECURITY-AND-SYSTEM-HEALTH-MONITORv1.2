import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api import schemas
from backend.api.dependencies import get_db

from backend.monitoring import collector, processes, reports as monitoring_reports
from backend.ai import (
    health_score as ai_health_score,
    root_cause as ai_root_cause,
    recommendations as ai_recommendations,
    trend_analysis as ai_trend_analysis,
    predictive_alerts as ai_predictive_alerts,
    anomaly_detection as ai_anomaly_detection,
)
try:
    from backend.cybersecurity import security_score as cyber_security_score
except ImportError:
    cyber_security_score = None
    logging.getLogger("lavender_trinetra.routes").warning(
        "backend.cybersecurity module not found - /cybersecurity/score will return 503 until it is implemented."
    )

logger = logging.getLogger("lavender_trinetra.routes")

router = APIRouter(prefix="/api", tags=["Lavender-Trinetra"])


# ---------------------------------------------------------------------------
# System Status
# ---------------------------------------------------------------------------
@router.get("/status", response_model=schemas.SystemStatusResponse)
async def get_system_status():
    try:
        return {
            "api": "operational",
            "ai": "operational",
            "monitoring": "operational",
            "database": "operational",
        }
    except Exception as exc:
        logger.exception("Failed to fetch system status")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Monitoring - Live Metrics
# ---------------------------------------------------------------------------
@router.get("/monitoring/metrics", response_model=schemas.LiveMetricsResponse)
async def get_live_metrics():
    try:
        data = collector.get_live_metrics()
        return data
    except Exception as exc:
        logger.exception("Failed to fetch live metrics")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Monitoring - Process Monitoring
# ---------------------------------------------------------------------------
@router.get("/monitoring/processes", response_model=list[schemas.ProcessInfo])
async def get_process_monitoring(limit: int = Query(default=50, ge=1, le=500)):
    try:
        data = processes.get_running_processes(limit=limit)
        return data
    except Exception as exc:
        logger.exception("Failed to fetch process monitoring data")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI - Health Score
# ---------------------------------------------------------------------------
@router.get("/ai/health-score", response_model=schemas.HealthScoreResponse)
async def get_health_score():
    try:
        return ai_health_score.compute_health_score()
    except Exception as exc:
        logger.exception("Failed to compute health score")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI - Root Cause Analysis
# ---------------------------------------------------------------------------
@router.get("/ai/root-cause", response_model=schemas.RootCauseResponse)
async def get_root_cause_analysis():
    try:
        return ai_root_cause.analyze_root_cause()
    except Exception as exc:
        logger.exception("Failed to run root cause analysis")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI - Recommendations
# ---------------------------------------------------------------------------
@router.get("/ai/recommendations", response_model=list[schemas.RecommendationItem])
async def get_recommendations():
    try:
        return ai_recommendations.generate_recommendations()
    except Exception as exc:
        logger.exception("Failed to generate recommendations")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI - Trend Analysis
# ---------------------------------------------------------------------------
@router.get("/ai/trends", response_model=schemas.TrendAnalysisResponse)
async def get_trend_analysis(window: str = Query(default="24h")):
    try:
        return ai_trend_analysis.analyze_trends(window=window)
    except Exception as exc:
        logger.exception("Failed to run trend analysis")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI - Predictive Alerts
# ---------------------------------------------------------------------------
@router.get("/ai/predictive-alerts", response_model=list[schemas.PredictiveAlert])
async def get_predictive_alerts():
    try:
        return ai_predictive_alerts.get_predictive_alerts()
    except Exception as exc:
        logger.exception("Failed to fetch predictive alerts")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI - Anomaly Detection
# ---------------------------------------------------------------------------
@router.get("/ai/anomalies", response_model=list[schemas.AnomalyItem])
async def get_anomalies():
    try:
        return ai_anomaly_detection.detect_anomalies()
    except Exception as exc:
        logger.exception("Failed to detect anomalies")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@router.get("/reports", response_model=list[schemas.ReportSummary])
async def get_reports(db: Session = Depends(get_db)):
    try:
        return monitoring_reports.get_all_reports(db)
    except Exception as exc:
        logger.exception("Failed to fetch reports")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/reports/{report_id}", response_model=schemas.ReportDetail)
async def get_report_detail(report_id: int, db: Session = Depends(get_db)):
    try:
        report = monitoring_reports.get_report_by_id(db, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return report
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch report detail")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Cybersecurity
# ---------------------------------------------------------------------------
@router.get("/cybersecurity/score", response_model=schemas.SecurityScoreResponse)
async def get_security_score():
    if cyber_security_score is None:
        raise HTTPException(status_code=503, detail="Cybersecurity module not yet implemented")
    try:
        return cyber_security_score.compute_security_score()
    except Exception as exc:
        logger.exception("Failed to compute security score")
        raise HTTPException(status_code=500, detail=str(exc))