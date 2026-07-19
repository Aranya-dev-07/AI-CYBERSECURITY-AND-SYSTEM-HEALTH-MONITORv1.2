from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class StatusLevel(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ServiceStatus(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# System Status
# ---------------------------------------------------------------------------
class SystemStatusResponse(BaseModel):
    api: ServiceStatus = Field(default=ServiceStatus.OPERATIONAL, description="API service status")
    ai: ServiceStatus = Field(default=ServiceStatus.UNKNOWN, description="AI engine status")
    monitoring: ServiceStatus = Field(default=ServiceStatus.UNKNOWN, description="Monitoring service status")
    database: ServiceStatus = Field(default=ServiceStatus.UNKNOWN, description="Database connectivity status")


# ---------------------------------------------------------------------------
# System Metrics
# ---------------------------------------------------------------------------
class SystemMetrics(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Time metrics were captured")
    cpu_usage_percent: float = Field(..., ge=0, le=100, description="CPU utilization percentage")
    memory_usage_percent: float = Field(..., ge=0, le=100, description="Memory utilization percentage")
    disk_usage_percent: float = Field(..., ge=0, le=100, description="Disk utilization percentage")
    network_sent_mb: float = Field(default=0.0, ge=0, description="Network bytes sent in MB")
    network_received_mb: float = Field(default=0.0, ge=0, description="Network bytes received in MB")
    uptime_seconds: Optional[float] = Field(default=None, description="System uptime in seconds")


class LiveMetricsResponse(BaseModel):
    metrics: SystemMetrics
    status: StatusLevel = Field(default=StatusLevel.UNKNOWN, description="Overall system status derived from metrics")


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------
class ProcessInfo(BaseModel):
    pid: int = Field(..., description="Process ID")
    name: str = Field(..., description="Process name")
    cpu_percent: float = Field(default=0.0, ge=0, description="CPU usage percentage")
    memory_percent: float = Field(default=0.0, ge=0, description="Memory usage percentage")
    status: Optional[str] = Field(default=None, description="Process execution status")
    user: Optional[str] = Field(default=None, description="Owning user")
    created_at: Optional[datetime] = Field(default=None, description="Process creation time")


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class AlertItem(BaseModel):
    id: Optional[int] = Field(default=None, description="Alert identifier")
    title: str = Field(..., description="Short alert title")
    description: str = Field(..., description="Detailed alert description")
    severity: SeverityLevel = Field(default=SeverityLevel.LOW, description="Alert severity")
    source: str = Field(..., description="Origin module that raised the alert")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Alert creation time")
    resolved: bool = Field(default=False, description="Whether the alert has been resolved")


# ---------------------------------------------------------------------------
# AI Results - Generic
# ---------------------------------------------------------------------------
class AIResultBase(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of AI result generation")
    model_version: Optional[str] = Field(default=None, description="Version of the AI model used")


# ---------------------------------------------------------------------------
# Health Score
# ---------------------------------------------------------------------------
class HealthScoreResponse(AIResultBase):
    score: float = Field(..., ge=0, le=100, description="Overall system health score (0-100)")
    status: StatusLevel = Field(default=StatusLevel.UNKNOWN, description="Health status classification")
    contributing_factors: list[str] = Field(default_factory=list, description="Factors contributing to the score")


# ---------------------------------------------------------------------------
# Root Cause Analysis
# ---------------------------------------------------------------------------
class RootCauseFactor(BaseModel):
    factor: str = Field(..., description="Identified contributing factor")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score for this factor")
    explanation: Optional[str] = Field(default=None, description="Explanation of the factor's relevance")


class RootCauseResponse(AIResultBase):
    issue: str = Field(..., description="Summary of the identified issue")
    probable_causes: list[RootCauseFactor] = Field(default_factory=list, description="Ranked probable causes")
    affected_components: list[str] = Field(default_factory=list, description="System components affected")


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
class RecommendationItem(BaseModel):
    id: Optional[int] = Field(default=None, description="Recommendation identifier")
    title: str = Field(..., description="Short recommendation title")
    description: str = Field(..., description="Detailed recommendation")
    priority: SeverityLevel = Field(default=SeverityLevel.LOW, description="Recommendation priority")
    category: Optional[str] = Field(default=None, description="Category e.g. performance, security")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Time recommendation was generated")


# ---------------------------------------------------------------------------
# Trend Analysis
# ---------------------------------------------------------------------------
class TrendPoint(BaseModel):
    timestamp: datetime = Field(..., description="Data point timestamp")
    value: float = Field(..., description="Metric value at this point")


class TrendSeries(BaseModel):
    metric_name: str = Field(..., description="Name of the metric tracked")
    points: list[TrendPoint] = Field(default_factory=list, description="Time series data points")
    direction: Optional[str] = Field(default=None, description="Trend direction e.g. increasing, decreasing, stable")


class TrendAnalysisResponse(AIResultBase):
    window: str = Field(default="24h", description="Time window analyzed")
    series: list[TrendSeries] = Field(default_factory=list, description="Trend series per metric")
    summary: Optional[str] = Field(default=None, description="Natural language summary of trends")


# ---------------------------------------------------------------------------
# Predictive Alerts
# ---------------------------------------------------------------------------
class PredictiveAlert(BaseModel):
    id: Optional[int] = Field(default=None, description="Predictive alert identifier")
    metric: str = Field(..., description="Metric the prediction is based on")
    predicted_issue: str = Field(..., description="Description of the predicted issue")
    probability: float = Field(..., ge=0, le=1, description="Probability of occurrence")
    eta_minutes: Optional[float] = Field(default=None, description="Estimated time until predicted issue occurs")
    severity: SeverityLevel = Field(default=SeverityLevel.LOW, description="Predicted severity")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Prediction generation timestamp")


# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------
class AnomalyItem(BaseModel):
    id: Optional[int] = Field(default=None, description="Anomaly identifier")
    metric: str = Field(..., description="Metric where anomaly was detected")
    value: float = Field(..., description="Observed anomalous value")
    expected_range: Optional[str] = Field(default=None, description="Expected normal range")
    severity: SeverityLevel = Field(default=SeverityLevel.LOW, description="Anomaly severity")
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
class ReportSummary(BaseModel):
    id: int = Field(..., description="Report identifier")
    title: str = Field(..., description="Report title")
    created_at: datetime = Field(..., description="Report creation timestamp")
    report_type: Optional[str] = Field(default=None, description="Type/category of report")


class ReportDetail(ReportSummary):
    content: dict[str, Any] = Field(default_factory=dict, description="Full report content payload")
    generated_by: Optional[str] = Field(default=None, description="Module or engine that generated the report")


# ---------------------------------------------------------------------------
# Cybersecurity
# ---------------------------------------------------------------------------
class SecurityScoreResponse(BaseModel):
    score: float = Field(..., ge=0, le=100, description="Overall security score (0-100)")
    status: StatusLevel = Field(default=StatusLevel.UNKNOWN, description="Security status classification")
    open_threats: int = Field(default=0, ge=0, description="Number of currently open threats")
    last_scan_at: Optional[datetime] = Field(default=None, description="Timestamp of last security scan")


# ---------------------------------------------------------------------------
# Generic API Response Wrapper
# ---------------------------------------------------------------------------
class APIResponse(BaseModel):
    success: bool = Field(default=True, description="Whether the request succeeded")
    message: Optional[str] = Field(default=None, description="Optional response message")
    data: Optional[Any] = Field(default=None, description="Response payload")