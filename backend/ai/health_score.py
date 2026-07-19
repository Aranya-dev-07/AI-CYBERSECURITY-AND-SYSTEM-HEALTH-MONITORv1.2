"""
health_score.py

Explainable AI Health Score Engine — Lavender Trinetra Platform
=====================================================================

Computes a composite, explainable system health score (0-100) derived
from CPU, RAM, Disk, Network, and active anomaly signals. Every score
carries a human-readable explanation and a breakdown of contributing
factors, suitable for direct dashboard consumption.

Integrates with:
    - monitoring/collector.py   (real-time metrics source)
    - ai/anomaly_detection.py   (active anomaly signals)
    - ai/ai_engine.py           (orchestration entry point)
    - ai/predictive_alerts.py   (consumes current_health_score)
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

logger = logging.getLogger("lavender_trinetra.ai.health_score")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class HealthStatus(str, Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    CRITICAL = "Critical"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class HealthScoreConfig:
    """Weights and thresholds used to compute the composite health score."""

    # Relative weights for each contributing factor. Must sum to 1.0.
    weight_cpu: float = 0.25
    weight_ram: float = 0.25
    weight_disk: float = 0.15
    weight_network: float = 0.10
    weight_anomalies: float = 0.25

    # Metric usage (%) considered "ideal" (no penalty) vs. saturated (full penalty)
    ideal_usage_pct: float = 40.0
    saturated_usage_pct: float = 95.0

    # Network: bytes/sec considered saturated (used to normalize a 0-100 load score)
    network_saturation_bps: float = 100_000_000.0  # 100 MB/s

    # Per-anomaly penalty applied to the anomaly sub-score, scaled by severity
    anomaly_severity_penalty: dict[str, float] = field(default_factory=lambda: {
        "Low": 5.0,
        "Medium": 12.0,
        "High": 25.0,
        "Critical": 40.0,
    })

    # Status thresholds (inclusive lower bound)
    status_thresholds: dict[str, int] = field(default_factory=lambda: {
        "Excellent": 90,
        "Good": 75,
        "Fair": 55,
        "Poor": 35,
        "Critical": 0,
    })


DEFAULT_CONFIG = HealthScoreConfig()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class HealthInput:
    """Normalized input bundle for a single health score computation."""

    timestamp: datetime
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    network_in_bps: float = 0.0
    network_out_bps: float = 0.0
    active_anomalies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ContributingFactor:
    """A single factor contributing to the overall health score."""

    name: str
    raw_value: float
    sub_score: float
    weight: float
    weighted_contribution: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealthScoreResult:
    """Structured, explainable health score result."""

    score_id: str
    timestamp: datetime
    score: float
    status: str
    contributing_factors: list[ContributingFactor]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "timestamp": self.timestamp.isoformat(),
            "score": self.score,
            "status": self.status,
            "contributing_factors": [f.to_dict() for f in self.contributing_factors],
            "explanation": self.explanation,
        }


# =====================================================================
# SUB-SCORE CALCULATIONS
# =====================================================================

def _usage_sub_score(usage_pct: float, config: HealthScoreConfig) -> float:
    """
    Convert a 0-100 resource usage percentage into a 0-100 sub-score,
    where lower usage yields a higher (healthier) sub-score.

    Usage at or below ideal_usage_pct -> 100.
    Usage at or above saturated_usage_pct -> 0.
    Linear interpolation in between.
    """
    if usage_pct <= config.ideal_usage_pct:
        return 100.0
    if usage_pct >= config.saturated_usage_pct:
        return 0.0

    span = config.saturated_usage_pct - config.ideal_usage_pct
    penalty_fraction = (usage_pct - config.ideal_usage_pct) / span
    return round(100.0 * (1.0 - penalty_fraction), 2)


def _network_sub_score(total_bps: float, config: HealthScoreConfig) -> float:
    """Convert combined network throughput into a 0-100 sub-score."""
    if total_bps <= 0:
        return 100.0
    load_fraction = min(1.0, total_bps / config.network_saturation_bps)
    return round(100.0 * (1.0 - load_fraction), 2)


def _anomaly_sub_score(
    active_anomalies: list[dict[str, Any]],
    config: HealthScoreConfig,
) -> float:
    """
    Convert the current set of active anomalies into a 0-100 sub-score,
    starting from 100 and subtracting severity-weighted penalties.
    """
    score = 100.0
    for anomaly in active_anomalies:
        severity = anomaly.get("severity", "Low")
        penalty = config.anomaly_severity_penalty.get(severity, 5.0)
        score -= penalty
    return round(max(0.0, score), 2)


# =====================================================================
# STATUS + EXPLANATION
# =====================================================================

def categorize_health_status(score: float, config: HealthScoreConfig = DEFAULT_CONFIG) -> HealthStatus:
    """Map a numeric score (0-100) to a HealthStatus category."""
    ordered = sorted(config.status_thresholds.items(), key=lambda kv: kv[1], reverse=True)
    for status_name, threshold in ordered:
        if score >= threshold:
            return HealthStatus(status_name)
    return HealthStatus.CRITICAL


def _generate_explanation(
    score: float,
    status: HealthStatus,
    factors: list[ContributingFactor],
    active_anomalies: list[dict[str, Any]],
) -> str:
    """
    Produce a human-readable explanation grounded in the weakest
    contributing factor(s) and any active anomalies.
    """
    sorted_factors = sorted(factors, key=lambda f: f.sub_score)
    weakest = sorted_factors[0] if sorted_factors else None

    parts: list[str] = [
        f"Overall system health is {status.value} with a score of {score:.1f}/100."
    ]

    if weakest and weakest.sub_score < 80:
        parts.append(weakest.detail)

    if active_anomalies:
        anomaly_count = len(active_anomalies)
        severities = ", ".join(sorted({a.get("severity", "Low") for a in active_anomalies}))
        parts.append(
            f"{anomaly_count} active anomaly(ies) detected (severity: {severities}), "
            f"reducing the overall score."
        )

    if status in (HealthStatus.EXCELLENT, HealthStatus.GOOD) and not active_anomalies:
        parts.append("All monitored resources are operating within healthy ranges.")

    return " ".join(parts)


# =====================================================================
# CORE CALCULATION
# =====================================================================

def calculate_health_score(
    health_input: HealthInput,
    config: HealthScoreConfig = DEFAULT_CONFIG,
) -> HealthScoreResult:
    """
    Calculate an explainable composite health score (0-100) from CPU,
    RAM, Disk, Network, and active anomaly signals.

    Args:
        health_input: Normalized HealthInput bundle.
        config: HealthScoreConfig instance.

    Returns:
        A fully populated HealthScoreResult including contributing
        factors and a natural-language explanation.

    Raises:
        ValueError: if input values are malformed (e.g. negative usage).
    """
    try:
        for field_name, value in (
            ("cpu_usage", health_input.cpu_usage),
            ("ram_usage", health_input.ram_usage),
            ("disk_usage", health_input.disk_usage),
        ):
            if value < 0:
                raise ValueError(f"Invalid negative value for {field_name}: {value}")

        cpu_sub = _usage_sub_score(health_input.cpu_usage, config)
        ram_sub = _usage_sub_score(health_input.ram_usage, config)
        disk_sub = _usage_sub_score(health_input.disk_usage, config)

        total_network_bps = health_input.network_in_bps + health_input.network_out_bps
        network_sub = _network_sub_score(total_network_bps, config)

        anomaly_sub = _anomaly_sub_score(health_input.active_anomalies, config)

        factors = [
            ContributingFactor(
                name="cpu",
                raw_value=health_input.cpu_usage,
                sub_score=cpu_sub,
                weight=config.weight_cpu,
                weighted_contribution=round(cpu_sub * config.weight_cpu, 2),
                detail=f"CPU usage is at {health_input.cpu_usage:.1f}%, "
                       f"contributing a sub-score of {cpu_sub:.1f}/100.",
            ),
            ContributingFactor(
                name="ram",
                raw_value=health_input.ram_usage,
                sub_score=ram_sub,
                weight=config.weight_ram,
                weighted_contribution=round(ram_sub * config.weight_ram, 2),
                detail=f"RAM usage is at {health_input.ram_usage:.1f}%, "
                       f"contributing a sub-score of {ram_sub:.1f}/100.",
            ),
            ContributingFactor(
                name="disk",
                raw_value=health_input.disk_usage,
                sub_score=disk_sub,
                weight=config.weight_disk,
                weighted_contribution=round(disk_sub * config.weight_disk, 2),
                detail=f"Disk usage is at {health_input.disk_usage:.1f}%, "
                       f"contributing a sub-score of {disk_sub:.1f}/100.",
            ),
            ContributingFactor(
                name="network",
                raw_value=total_network_bps,
                sub_score=network_sub,
                weight=config.weight_network,
                weighted_contribution=round(network_sub * config.weight_network, 2),
                detail=f"Combined network throughput is {total_network_bps / 1_000_000:.1f} MB/s, "
                       f"contributing a sub-score of {network_sub:.1f}/100.",
            ),
            ContributingFactor(
                name="anomalies",
                raw_value=float(len(health_input.active_anomalies)),
                sub_score=anomaly_sub,
                weight=config.weight_anomalies,
                weighted_contribution=round(anomaly_sub * config.weight_anomalies, 2),
                detail=f"{len(health_input.active_anomalies)} active anomaly(ies) present, "
                       f"contributing a sub-score of {anomaly_sub:.1f}/100.",
            ),
        ]

        composite_score = round(sum(f.weighted_contribution for f in factors), 2)
        composite_score = max(0.0, min(100.0, composite_score))

        status = categorize_health_status(composite_score, config)
        explanation = _generate_explanation(
            composite_score, status, factors, health_input.active_anomalies
        )

        result = HealthScoreResult(
            score_id=str(uuid.uuid4()),
            timestamp=health_input.timestamp,
            score=composite_score,
            status=status.value,
            contributing_factors=factors,
            explanation=explanation,
        )

        logger.info(
            "Health score computed: %.1f (%s) at %s",
            composite_score, status.value, health_input.timestamp.isoformat(),
        )

        return result

    except Exception as exc:
        logger.exception("Health score calculation failed: %s", exc)
        raise


# =====================================================================
# BATCH / HISTORICAL HELPERS
# =====================================================================

def calculate_health_score_batch(
    inputs: list[HealthInput],
    config: HealthScoreConfig = DEFAULT_CONFIG,
) -> list[HealthScoreResult]:
    """Compute health scores for a batch of HealthInput records, skipping failures."""
    results: list[HealthScoreResult] = []
    for item in inputs:
        try:
            results.append(calculate_health_score(item, config))
        except Exception as exc:
            logger.error("Skipping health score for %s due to error: %s", item.timestamp, exc)
    return results


def get_latest_health_score(
    results: list[HealthScoreResult],
) -> Optional[HealthScoreResult]:
    """Return the most recent HealthScoreResult by timestamp, or None if empty."""
    if not results:
        return None
    return max(results, key=lambda r: r.timestamp)


# =====================================================================
# MODULE-LEVEL ENTRY POINT (for ai_engine.py / main.py)
# =====================================================================

def run_health_score_check(
    cpu_usage: float,
    ram_usage: float,
    disk_usage: float,
    network_in_bps: float = 0.0,
    network_out_bps: float = 0.0,
    active_anomalies: Optional[list[dict[str, Any]]] = None,
    timestamp: Optional[datetime] = None,
    config: HealthScoreConfig = DEFAULT_CONFIG,
) -> HealthScoreResult:
    """
    Convenience entry point invoked automatically from main.py / ai_engine.py
    on each monitoring cycle. Builds a HealthInput from raw values and
    returns the computed HealthScoreResult.
    """
    health_input = HealthInput(
        timestamp=timestamp or datetime.utcnow(),
        cpu_usage=cpu_usage,
        ram_usage=ram_usage,
        disk_usage=disk_usage,
        network_in_bps=network_in_bps,
        network_out_bps=network_out_bps,
        active_anomalies=active_anomalies or [],
    )
    return calculate_health_score(health_input, config)


# =====================================================================
# EXPORT
# =====================================================================

def export_result(result: HealthScoreResult, fmt: str = "dict") -> Any:
    """Export a HealthScoreResult as dict or JSON for API/dashboard consumption."""
    data = result.to_dict()

    if fmt == "dict":
        return data
    if fmt == "json":
        import json
        return json.dumps(data, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


__all__ = [
    "HealthScoreConfig",
    "DEFAULT_CONFIG",
    "HealthStatus",
    "HealthInput",
    "ContributingFactor",
    "HealthScoreResult",
    "calculate_health_score",
    "calculate_health_score_batch",
    "get_latest_health_score",
    "categorize_health_status",
    "run_health_score_check",
    "export_result",
]