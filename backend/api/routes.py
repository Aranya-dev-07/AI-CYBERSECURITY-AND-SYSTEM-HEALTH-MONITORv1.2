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
    from backend.cybersecurity import (
        security_engine,
        process_monitor as cyber_process_monitor,
        network_monitor as cyber_network_monitor,
        port_monitor as cyber_port_monitor,
        firewall_monitor as cyber_firewall_monitor,
        session_monitor as cyber_session_monitor,
    )
except ImportError as _cyber_import_error:
    security_engine = None
    cyber_process_monitor = None
    cyber_network_monitor = None
    cyber_port_monitor = None
    cyber_firewall_monitor = None
    cyber_session_monitor = None
    logging.getLogger("lavender_trinetra.routes").warning(
        "backend.cybersecurity package not fully available (%s) - "
        "/cybersecurity/* endpoints will return 503 until it is complete.",
        _cyber_import_error,
    )

# Phase 2/3: threat detection, intrusion detection, vulnerability
# scanning, and the explainable AI security layer built on top of
# them. All read from in-memory buffers/state maintained by
# threat_detector.py's run_cycle() (driven by main.py) - these
# endpoints perform no detection or scoring of their own.
try:
    from backend.cybersecurity import threat_detector as cyber_threat_detector
except ImportError:
    cyber_threat_detector = None

try:
    from backend.cybersecurity import intrusion_detection as cyber_intrusion_detection
except ImportError:
    cyber_intrusion_detection = None

try:
    from backend.cybersecurity import vulnerability_scan as cyber_vulnerability_scan
except ImportError:
    cyber_vulnerability_scan = None

try:
    from backend.cybersecurity import security_score as cyber_security_score
except ImportError:
    cyber_security_score = None

try:
    from backend.cybersecurity import threat_classifier as cyber_threat_classifier
except ImportError:
    cyber_threat_classifier = None

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
def _require_cybersecurity_module(module, name: str):
    if module is None:
        raise HTTPException(
            status_code=503,
            detail=f"Cybersecurity module '{name}' not yet available",
        )


@router.get("/cybersecurity/status")
async def get_cybersecurity_status():
    """Overall security engine status, consumed by SecurityOverview.jsx."""
    _require_cybersecurity_module(security_engine, "security_engine")
    try:
        return security_engine.get_security_status()
    except Exception as exc:
        logger.exception("Failed to fetch cybersecurity status")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/processes")
async def get_cybersecurity_processes():
    """Process-level security observations from process_monitor.py."""
    _require_cybersecurity_module(cyber_process_monitor, "process_monitor")
    try:
        return cyber_process_monitor.scan()
    except Exception as exc:
        logger.exception("Failed to fetch process security events")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/network")
async def get_cybersecurity_network():
    """Network connection and traffic-rate events from network_monitor.py."""
    _require_cybersecurity_module(cyber_network_monitor, "network_monitor")
    try:
        return cyber_network_monitor.scan()
    except Exception as exc:
        logger.exception("Failed to fetch network security events")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/ports")
async def get_cybersecurity_ports():
    """Listening-port observations and change events from port_monitor.py."""
    _require_cybersecurity_module(cyber_port_monitor, "port_monitor")
    try:
        return cyber_port_monitor.scan()
    except Exception as exc:
        logger.exception("Failed to fetch port security events")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/firewall")
async def get_cybersecurity_firewall():
    """
    Firewall status/change events from firewall_monitor.py. Returns a
    list (current status snapshot plus any change events this cycle) -
    the frontend selects the "firewall_status" entry for the current
    snapshot, matching the same event-list shape every other
    cybersecurity endpoint uses.
    """
    _require_cybersecurity_module(cyber_firewall_monitor, "firewall_monitor")
    try:
        return cyber_firewall_monitor.scan()
    except Exception as exc:
        logger.exception("Failed to fetch firewall status")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/sessions")
async def get_cybersecurity_sessions():
    """Active user session observations and login/logout events from session_monitor.py."""
    _require_cybersecurity_module(cyber_session_monitor, "session_monitor")
    try:
        return cyber_session_monitor.scan()
    except Exception as exc:
        logger.exception("Failed to fetch session security events")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Cybersecurity - Threat Detection (threat_detector.py)
# ---------------------------------------------------------------------------
@router.get("/cybersecurity/threats/summary")
async def get_threat_summary():
    """Counts of recent threats by severity, consumed by ThreatOverview.jsx."""
    _require_cybersecurity_module(cyber_threat_detector, "threat_detector")
    try:
        return cyber_threat_detector.get_threat_summary()
    except Exception as exc:
        logger.exception("Failed to fetch threat summary")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/threats/active")
async def get_active_threats(min_severity: str = Query(default="Medium")):
    """Recent threats at or above the given severity, consumed by ThreatOverview.jsx."""
    _require_cybersecurity_module(cyber_threat_detector, "threat_detector")
    try:
        return cyber_threat_detector.get_active_threats(min_severity=min_severity)
    except Exception as exc:
        logger.exception("Failed to fetch active threats")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/threats/recent")
async def get_recent_threats(limit: int = Query(default=100, ge=1, le=500)):
    """Most recent threats newest-first, consumed by ThreatOverview.jsx."""
    _require_cybersecurity_module(cyber_threat_detector, "threat_detector")
    try:
        return cyber_threat_detector.get_recent_threats(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch recent threats")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Cybersecurity - Intrusion Detection (intrusion_detection.py)
# ---------------------------------------------------------------------------
@router.get("/cybersecurity/intrusions")
async def get_recent_intrusions(limit: int = Query(default=100, ge=1, le=500)):
    """Most recent intrusion alerts newest-first, consumed by Intrusion.jsx."""
    _require_cybersecurity_module(cyber_intrusion_detection, "intrusion_detection")
    try:
        return cyber_intrusion_detection.get_recent_intrusions(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch recent intrusions")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Cybersecurity - Vulnerability Scan (vulnerability_scan.py)
# ---------------------------------------------------------------------------
@router.get("/cybersecurity/vulnerabilities")
async def get_recent_vulnerabilities(limit: int = Query(default=100, ge=1, le=500)):
    """Most recent vulnerability findings newest-first, consumed by Vulnerabilities.jsx."""
    _require_cybersecurity_module(cyber_vulnerability_scan, "vulnerability_scan")
    try:
        return cyber_vulnerability_scan.get_recent_findings(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch recent vulnerabilities")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/vulnerabilities/summary")
async def get_vulnerability_summary():
    """Counts of recent vulnerability findings by severity, consumed by Vulnerabilities.jsx."""
    _require_cybersecurity_module(cyber_vulnerability_scan, "vulnerability_scan")
    try:
        return cyber_vulnerability_scan.get_vulnerability_summary()
    except Exception as exc:
        logger.exception("Failed to fetch vulnerability summary")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Cybersecurity - Explainable AI Security Score (security_score.py, threat_classifier.py)
# ---------------------------------------------------------------------------
@router.get("/cybersecurity/score")
async def get_security_score():
    """Latest explainable security score/grade/breakdown, consumed by SecurityScore.jsx."""
    _require_cybersecurity_module(cyber_security_score, "security_score")
    try:
        return cyber_security_score.get_latest_score()
    except Exception as exc:
        logger.exception("Failed to fetch security score")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/score/history")
async def get_security_score_history(limit: int = Query(default=100, ge=1, le=500)):
    """Recent security score history newest-first, for trend charts."""
    _require_cybersecurity_module(cyber_security_score, "security_score")
    try:
        return cyber_security_score.get_score_history(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch security score history")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/classifications/summary")
async def get_threat_classification_summary():
    """Counts of recent threat classifications by category, consumed by SecurityScore.jsx."""
    _require_cybersecurity_module(cyber_threat_classifier, "threat_classifier")
    try:
        return cyber_threat_classifier.get_classification_summary()
    except Exception as exc:
        logger.exception("Failed to fetch threat classification summary")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cybersecurity/classifications")
async def get_threat_classifications(limit: int = Query(default=100, ge=1, le=500)):
    """Most recent threat classifications newest-first."""
    _require_cybersecurity_module(cyber_threat_classifier, "threat_classifier")
    try:
        return cyber_threat_classifier.get_recent_classifications(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch threat classifications")
        raise HTTPException(status_code=500, detail=str(exc))