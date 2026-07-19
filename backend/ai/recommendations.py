"""
recommendations.py

Intelligent AI Recommendation Engine — Lavender Trinetra Platform
=====================================================================

Aggregates signals from monitoring data, anomaly detection, health
scoring, trend analysis, and root cause analysis into a single,
prioritized, explainable list of actionable recommendations.

Integrates with:
    - ai/anomaly_detection.py   (active anomalies)
    - ai/health_score.py        (composite health score + factors)
    - ai/trend_analysis.py      (metric trend direction/slope)
    - ai/root_cause.py          (root cause + suggested action per anomaly)
    - ai/predictive_alerts.py   (forecasted future events)
    - ai/ai_engine.py           (orchestration entry point)
    - main.py                  (auto-executes on monitoring startup)

Author: Lavender Trinetra AI Engineering
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("lavender_trinetra.ai.recommendations")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RecommendationSource(str, Enum):
    HEALTH_SCORE = "health_score"
    ANOMALY_DETECTION = "anomaly_detection"
    ROOT_CAUSE = "root_cause"
    TREND_ANALYSIS = "trend_analysis"
    PREDICTIVE_ALERTS = "predictive_alerts"
    RULE_BASED = "rule_based"


class RecommendationCategory(str, Enum):
    PERFORMANCE = "Performance"
    STABILITY = "Stability"
    SECURITY = "Security"
    CAPACITY = "Capacity"
    MAINTENANCE = "Maintenance"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class RecommendationConfig:
    """Priority weighting and de-duplication settings."""

    severity_priority_weight: dict[str, int] = field(default_factory=lambda: {
        Severity.CRITICAL.value: 100,
        Severity.HIGH.value: 75,
        Severity.MEDIUM.value: 50,
        Severity.LOW.value: 25,
    })

    # Extra priority points added per source, to break ties sensibly
    # (e.g. an active anomaly is more urgent than a slow trend).
    source_priority_bonus: dict[str, int] = field(default_factory=lambda: {
        RecommendationSource.ANOMALY_DETECTION.value: 15,
        RecommendationSource.ROOT_CAUSE.value: 15,
        RecommendationSource.PREDICTIVE_ALERTS.value: 10,
        RecommendationSource.HEALTH_SCORE.value: 5,
        RecommendationSource.TREND_ANALYSIS.value: 0,
        RecommendationSource.RULE_BASED.value: 0,
    })

    max_recommendations: int = 20

    # Health score below this triggers a general capacity/stability recommendation
    health_score_warning_threshold: float = 70.0
    health_score_critical_threshold: float = 40.0


DEFAULT_CONFIG = RecommendationConfig()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class Recommendation:
    """A single structured, explainable recommendation."""

    recommendation_id: str
    timestamp: datetime
    title: str
    category: str
    severity: str
    priority_score: int
    source: str
    reasoning: str
    recommended_action: str
    affected_metric: Optional[str] = None
    related_process: Optional[str] = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class RecommendationInputs:
    """Aggregated signal bundle consumed by the recommendation engine."""

    timestamp: datetime

    # From health_score.py
    health_score: Optional[float] = None
    health_status: Optional[str] = None
    health_contributing_factors: list[dict[str, Any]] = field(default_factory=list)

    # From anomaly_detection.py
    active_anomalies: list[dict[str, Any]] = field(default_factory=list)

    # From root_cause.py
    root_cause_results: list[dict[str, Any]] = field(default_factory=list)

    # From trend_analysis.py
    trends: list[dict[str, Any]] = field(default_factory=list)

    # From predictive_alerts.py
    predictions: list[dict[str, Any]] = field(default_factory=list)


# =====================================================================
# PRIORITY CALCULATION
# =====================================================================

def _calculate_priority(
    severity: Severity,
    source: RecommendationSource,
    config: RecommendationConfig,
) -> int:
    """Compute a 0-115 priority score from severity and originating source."""
    base = config.severity_priority_weight.get(severity.value, 25)
    bonus = config.source_priority_bonus.get(source.value, 0)
    return base + bonus


# =====================================================================
# GENERATORS PER SOURCE
# =====================================================================

def _from_root_cause(
    inputs: RecommendationInputs,
    config: RecommendationConfig,
) -> list[Recommendation]:
    """Build recommendations directly from root cause analysis results."""
    recs: list[Recommendation] = []
    for rc in inputs.root_cause_results:
        try:
            severity = Severity(rc.get("severity", Severity.LOW.value))
            priority = _calculate_priority(severity, RecommendationSource.ROOT_CAUSE, config)

            recs.append(Recommendation(
                recommendation_id=str(uuid.uuid4()),
                timestamp=inputs.timestamp,
                title=f"Address {rc.get('root_cause_category', 'system issue')}",
                category=RecommendationCategory.STABILITY.value,
                severity=severity.value,
                priority_score=priority,
                source=RecommendationSource.ROOT_CAUSE.value,
                reasoning=rc.get("explanation", "Root cause analysis identified a contributing issue."),
                recommended_action=rc.get("recommended_action", "Investigate further."),
                affected_metric=rc.get("affected_metric"),
                related_process=rc.get("responsible_process"),
                evidence={"anomaly_id": rc.get("anomaly_id"), "analysis_id": rc.get("analysis_id")},
            ))
        except Exception as exc:
            logger.error("Failed to build recommendation from root cause result: %s", exc)
    return recs


def _from_anomalies(
    inputs: RecommendationInputs,
    config: RecommendationConfig,
) -> list[Recommendation]:
    """Build recommendations from active anomalies not already covered by root cause."""
    recs: list[Recommendation] = []
    root_cause_anomaly_ids = {rc.get("anomaly_id") for rc in inputs.root_cause_results}

    for anomaly in inputs.active_anomalies:
        anomaly_id = anomaly.get("anomaly_id")
        if anomaly_id in root_cause_anomaly_ids:
            continue  # already covered with a more specific recommendation

        try:
            severity = Severity(anomaly.get("severity", Severity.LOW.value))
            priority = _calculate_priority(severity, RecommendationSource.ANOMALY_DETECTION, config)
            affected = anomaly.get("affected_metrics", [])
            metric_str = ", ".join(affected) if affected else "system behavior"

            recs.append(Recommendation(
                recommendation_id=str(uuid.uuid4()),
                timestamp=inputs.timestamp,
                title=f"Investigate anomaly in {metric_str}",
                category=RecommendationCategory.STABILITY.value,
                severity=severity.value,
                priority_score=priority,
                source=RecommendationSource.ANOMALY_DETECTION.value,
                reasoning=(
                    f"An anomaly was detected with a score of {anomaly.get('anomaly_score', 0):.3f}, "
                    f"affecting {metric_str}."
                ),
                recommended_action="Review recent activity and consider running a full diagnostic scan.",
                affected_metric=affected[0] if affected else None,
                related_process=anomaly.get("top_process"),
                evidence={"anomaly_id": anomaly_id, "anomaly_score": anomaly.get("anomaly_score")},
            ))
        except Exception as exc:
            logger.error("Failed to build recommendation from anomaly: %s", exc)
    return recs


def _from_health_score(
    inputs: RecommendationInputs,
    config: RecommendationConfig,
) -> list[Recommendation]:
    """Build a recommendation from a degraded overall health score."""
    recs: list[Recommendation] = []
    if inputs.health_score is None:
        return recs

    if inputs.health_score >= config.health_score_warning_threshold:
        return recs

    try:
        severity = (
            Severity.CRITICAL if inputs.health_score < config.health_score_critical_threshold
            else Severity.HIGH
        )
        priority = _calculate_priority(severity, RecommendationSource.HEALTH_SCORE, config)

        weakest_factor = None
        if inputs.health_contributing_factors:
            weakest_factor = min(
                inputs.health_contributing_factors,
                key=lambda f: f.get("sub_score", 100),
            )

        reasoning = (
            f"Overall system health score is {inputs.health_score:.1f}/100 "
            f"({inputs.health_status or 'degraded'})."
        )
        if weakest_factor:
            reasoning += f" The weakest contributing factor is {weakest_factor.get('name')}."

        recs.append(Recommendation(
            recommendation_id=str(uuid.uuid4()),
            timestamp=inputs.timestamp,
            title="Improve overall system health",
            category=RecommendationCategory.STABILITY.value,
            severity=severity.value,
            priority_score=priority,
            source=RecommendationSource.HEALTH_SCORE.value,
            reasoning=reasoning,
            recommended_action="Delay heavy workloads and address the weakest contributing factor.",
            affected_metric=weakest_factor.get("name") if weakest_factor else None,
            related_process=None,
            evidence={"health_score": inputs.health_score, "health_status": inputs.health_status},
        ))
    except Exception as exc:
        logger.error("Failed to build recommendation from health score: %s", exc)
    return recs


def _from_trends(
    inputs: RecommendationInputs,
    config: RecommendationConfig,
) -> list[Recommendation]:
    """Build recommendations from concerning trend directions."""
    recs: list[Recommendation] = []
    for trend in inputs.trends:
        direction = trend.get("direction", "").lower()
        if direction not in ("increasing", "rising", "upward"):
            continue

        metric = trend.get("metric", "a monitored metric")
        try:
            severity_str = trend.get("severity", Severity.LOW.value)
            severity = Severity(severity_str) if severity_str in Severity._value2member_map_ else Severity.LOW
            priority = _calculate_priority(severity, RecommendationSource.TREND_ANALYSIS, config)

            recs.append(Recommendation(
                recommendation_id=str(uuid.uuid4()),
                timestamp=inputs.timestamp,
                title=f"Monitor rising trend in {metric}",
                category=RecommendationCategory.CAPACITY.value,
                severity=severity.value,
                priority_score=priority,
                source=RecommendationSource.TREND_ANALYSIS.value,
                reasoning=trend.get(
                    "explanation",
                    f"{metric} has shown a sustained upward trend over the recent monitoring window.",
                ),
                recommended_action="Monitor closely; plan capacity adjustments if the trend continues.",
                affected_metric=metric,
                related_process=None,
                evidence={"slope": trend.get("slope"), "window": trend.get("window")},
            ))
        except Exception as exc:
            logger.error("Failed to build recommendation from trend: %s", exc)
    return recs


def _from_predictions(
    inputs: RecommendationInputs,
    config: RecommendationConfig,
) -> list[Recommendation]:
    """Build recommendations from forecasted future events (predictive_alerts.py)."""
    recs: list[Recommendation] = []
    for prediction in inputs.predictions:
        try:
            severity = Severity(prediction.get("severity", Severity.LOW.value))
            priority = _calculate_priority(severity, RecommendationSource.PREDICTIVE_ALERTS, config)

            recs.append(Recommendation(
                recommendation_id=str(uuid.uuid4()),
                timestamp=inputs.timestamp,
                title=f"Prepare for predicted {prediction.get('predicted_event', 'event')}",
                category=RecommendationCategory.CAPACITY.value,
                severity=severity.value,
                priority_score=priority,
                source=RecommendationSource.PREDICTIVE_ALERTS.value,
                reasoning=prediction.get("explanation", "A future event was forecasted based on current trends."),
                recommended_action=prediction.get("recommended_action", "Monitor closely."),
                affected_metric=prediction.get("affected_metric"),
                related_process=prediction.get("responsible_process"),
                evidence={
                    "prediction_id": prediction.get("prediction_id"),
                    "probability": prediction.get("probability"),
                    "eta_minutes": prediction.get("eta_minutes"),
                },
            ))
        except Exception as exc:
            logger.error("Failed to build recommendation from prediction: %s", exc)
    return recs


# =====================================================================
# DEDUPLICATION + PRIORITIZATION
# =====================================================================

def _deduplicate(recommendations: list[Recommendation]) -> list[Recommendation]:
    """
    Remove near-duplicate recommendations that share the same category
    and affected metric, keeping the highest-priority instance of each.
    """
    best_by_key: dict[tuple[str, Optional[str]], Recommendation] = {}
    for rec in recommendations:
        key = (rec.category, rec.affected_metric)
        existing = best_by_key.get(key)
        if existing is None or rec.priority_score > existing.priority_score:
            best_by_key[key] = rec
    return list(best_by_key.values())


def prioritize_recommendations(
    recommendations: list[Recommendation],
    config: RecommendationConfig = DEFAULT_CONFIG,
) -> list[Recommendation]:
    """Sort recommendations by priority score descending and cap the list length."""
    ordered = sorted(recommendations, key=lambda r: r.priority_score, reverse=True)
    return ordered[: config.max_recommendations]


# =====================================================================
# CORE ENGINE
# =====================================================================

def generate_recommendations(
    inputs: RecommendationInputs,
    config: RecommendationConfig = DEFAULT_CONFIG,
) -> list[Recommendation]:
    """
    Generate a prioritized, de-duplicated list of explainable
    recommendations from all available AI subsystem signals.

    Args:
        inputs: RecommendationInputs bundling health score, anomalies,
            root cause results, trends, and predictions.
        config: RecommendationConfig instance.

    Returns:
        A prioritized list of Recommendation objects, capped at
        config.max_recommendations.
    """
    try:
        collected: list[Recommendation] = []
        collected.extend(_from_root_cause(inputs, config))
        collected.extend(_from_anomalies(inputs, config))
        collected.extend(_from_health_score(inputs, config))
        collected.extend(_from_trends(inputs, config))
        collected.extend(_from_predictions(inputs, config))

        deduplicated = _deduplicate(collected)
        prioritized = prioritize_recommendations(deduplicated, config)

        logger.info(
            "Generated %d recommendation(s) (from %d raw candidates) at %s",
            len(prioritized), len(collected), inputs.timestamp.isoformat(),
        )

        return prioritized

    except Exception as exc:
        logger.exception("Recommendation generation failed: %s", exc)
        return []


# =====================================================================
# MODULE-LEVEL ENTRY POINT (for ai_engine.py / main.py)
# =====================================================================

def run_recommendation_engine(
    health_score: Optional[float] = None,
    health_status: Optional[str] = None,
    health_contributing_factors: Optional[list[dict[str, Any]]] = None,
    active_anomalies: Optional[list[dict[str, Any]]] = None,
    root_cause_results: Optional[list[dict[str, Any]]] = None,
    trends: Optional[list[dict[str, Any]]] = None,
    predictions: Optional[list[dict[str, Any]]] = None,
    timestamp: Optional[datetime] = None,
    config: RecommendationConfig = DEFAULT_CONFIG,
) -> list[Recommendation]:
    """
    Convenience entry point invoked automatically from main.py / ai_engine.py
    on each monitoring cycle, after health_score, anomaly_detection,
    root_cause, trend_analysis, and predictive_alerts have all run.
    """
    inputs = RecommendationInputs(
        timestamp=timestamp or datetime.utcnow(),
        health_score=health_score,
        health_status=health_status,
        health_contributing_factors=health_contributing_factors or [],
        active_anomalies=active_anomalies or [],
        root_cause_results=root_cause_results or [],
        trends=trends or [],
        predictions=predictions or [],
    )
    return generate_recommendations(inputs, config)


# =====================================================================
# EXPORT
# =====================================================================

def export_recommendations(recommendations: list[Recommendation], fmt: str = "dict") -> Any:
    """Export recommendations as dict list, DataFrame, or JSON for API/dashboard consumption."""
    records = [r.to_dict() for r in recommendations]

    if fmt == "dict":
        return records
    if fmt == "dataframe":
        import pandas as pd
        return pd.DataFrame(records)
    if fmt == "json":
        import json
        return json.dumps(records, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


__all__ = [
    "RecommendationConfig",
    "DEFAULT_CONFIG",
    "Severity",
    "RecommendationSource",
    "RecommendationCategory",
    "Recommendation",
    "RecommendationInputs",
    "generate_recommendations",
    "prioritize_recommendations",
    "run_recommendation_engine",
    "export_recommendations",
]