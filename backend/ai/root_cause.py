"""
root_cause.py

Explainable AI Root Cause Analysis Engine — Lavender Trinetra Platform
=====================================================================

Analyzes anomalies together with the surrounding monitoring context
(metrics, process activity, health score) to identify the affected
metric, the responsible process, and a natural-language explanation of
why the anomaly likely occurred, along with a severity rating and a
recommended corrective action.

Integrates with:
    - ai/anomaly_detection.py   (source of anomalies to analyze)
    - ai/health_score.py        (contextual system health)
    - ai/predictive_alerts.py   (consumes responsible_process attribution)
    - ai/recommendations.py     (shared recommendation vocabulary)
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

logger = logging.getLogger("lavender_trinetra.ai.root_cause")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RootCauseCategory(str, Enum):
    CPU_SATURATION = "CPU Saturation"
    MEMORY_PRESSURE = "Memory Pressure"
    DISK_IO_BOTTLENECK = "Disk I/O Bottleneck"
    DISK_SPACE_EXHAUSTION = "Disk Space Exhaustion"
    NETWORK_SATURATION = "Network Saturation"
    RUNAWAY_PROCESS = "Runaway Process"
    SYSTEM_INSTABILITY = "System Instability"
    UNKNOWN = "Unknown"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class RootCauseConfig:
    """Thresholds used to classify anomalies into root cause categories."""

    cpu_saturation_threshold: float = 85.0
    ram_saturation_threshold: float = 85.0
    disk_usage_threshold: float = 90.0
    disk_io_threshold_bps: float = 80_000_000.0   # 80 MB/s
    network_saturation_bps: float = 80_000_000.0  # 80 MB/s

    # Process considered dominant if it exceeds this share of the
    # affected resource (e.g. > 50% of total CPU usage).
    dominant_process_share_threshold: float = 0.5

    severity_by_category: dict[str, str] = field(default_factory=lambda: {
        RootCauseCategory.CPU_SATURATION.value: Severity.HIGH.value,
        RootCauseCategory.MEMORY_PRESSURE.value: Severity.HIGH.value,
        RootCauseCategory.DISK_IO_BOTTLENECK.value: Severity.MEDIUM.value,
        RootCauseCategory.DISK_SPACE_EXHAUSTION.value: Severity.CRITICAL.value,
        RootCauseCategory.NETWORK_SATURATION.value: Severity.MEDIUM.value,
        RootCauseCategory.RUNAWAY_PROCESS.value: Severity.HIGH.value,
        RootCauseCategory.SYSTEM_INSTABILITY.value: Severity.CRITICAL.value,
        RootCauseCategory.UNKNOWN.value: Severity.LOW.value,
    })


DEFAULT_CONFIG = RootCauseConfig()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class ProcessContext:
    """Per-process resource usage used for responsible-process attribution."""

    name: str
    pid: Optional[int] = None
    cpu_percent: float = 0.0
    memory_percent: float = 0.0


@dataclass
class AnomalyContext:
    """Input bundle describing the anomaly and surrounding monitoring state."""

    anomaly_id: str
    timestamp: datetime
    affected_metrics: list[str]
    anomaly_score: float
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    network_in_bps: float = 0.0
    network_out_bps: float = 0.0
    processes: list[ProcessContext] = field(default_factory=list)
    current_health_score: Optional[float] = None


@dataclass
class RootCauseResult:
    """Structured, explainable root cause analysis result."""

    analysis_id: str
    timestamp: datetime
    anomaly_id: str
    affected_metric: str
    responsible_process: Optional[str]
    root_cause_category: str
    severity: str
    explanation: str
    recommended_action: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# =====================================================================
# PROCESS ATTRIBUTION
# =====================================================================

def _identify_responsible_process(
    processes: list[ProcessContext],
    metric: str,
    config: RootCauseConfig,
) -> tuple[Optional[str], float]:
    """
    Identify the process most likely responsible for an anomaly in the
    given metric, and its share of the total resource usage.

    Returns:
        (process_name_or_None, share_fraction)
    """
    if not processes:
        return None, 0.0

    metric_key_map = {
        "cpu_usage": "cpu_percent",
        "ram_usage": "memory_percent",
    }
    attr = metric_key_map.get(metric)
    if not attr:
        return None, 0.0

    total = sum(getattr(p, attr, 0.0) for p in processes)
    if total <= 0:
        return None, 0.0

    top = max(processes, key=lambda p: getattr(p, attr, 0.0))
    share = getattr(top, attr, 0.0) / total

    if share >= config.dominant_process_share_threshold:
        return top.name, round(share, 3)

    return None, round(share, 3)


# =====================================================================
# CATEGORY CLASSIFICATION
# =====================================================================

def _classify_root_cause(
    context: AnomalyContext,
    config: RootCauseConfig,
) -> tuple[RootCauseCategory, str]:
    """
    Classify the anomaly into a root cause category based on the affected
    metrics and current resource state.

    Returns:
        (category, primary_affected_metric)
    """
    metrics = set(context.affected_metrics)

    if context.disk_usage >= config.disk_usage_threshold and "disk_usage" in metrics:
        return RootCauseCategory.DISK_SPACE_EXHAUSTION, "disk_usage"

    total_disk_io = context.disk_read_bps + context.disk_write_bps
    if total_disk_io >= config.disk_io_threshold_bps and (
        "disk_read_bps" in metrics or "disk_write_bps" in metrics
    ):
        return RootCauseCategory.DISK_IO_BOTTLENECK, (
            "disk_write_bps" if context.disk_write_bps >= context.disk_read_bps else "disk_read_bps"
        )

    total_network = context.network_in_bps + context.network_out_bps
    if total_network >= config.network_saturation_bps and (
        "network_in_bps" in metrics or "network_out_bps" in metrics
    ):
        return RootCauseCategory.NETWORK_SATURATION, (
            "network_out_bps" if context.network_out_bps >= context.network_in_bps else "network_in_bps"
        )

    if context.ram_usage >= config.ram_saturation_threshold and "ram_usage" in metrics:
        process, share = _identify_responsible_process(context.processes, "ram_usage", config)
        if process:
            return RootCauseCategory.RUNAWAY_PROCESS, "ram_usage"
        return RootCauseCategory.MEMORY_PRESSURE, "ram_usage"

    if context.cpu_usage >= config.cpu_saturation_threshold and "cpu_usage" in metrics:
        process, share = _identify_responsible_process(context.processes, "cpu_usage", config)
        if process:
            return RootCauseCategory.RUNAWAY_PROCESS, "cpu_usage"
        return RootCauseCategory.CPU_SATURATION, "cpu_usage"

    if len(metrics) >= 3:
        return RootCauseCategory.SYSTEM_INSTABILITY, next(iter(metrics), "overall_system_behavior")

    if metrics:
        return RootCauseCategory.UNKNOWN, next(iter(metrics))

    return RootCauseCategory.UNKNOWN, "overall_system_behavior"


# =====================================================================
# EXPLANATION + RECOMMENDATION
# =====================================================================

def _generate_explanation(
    category: RootCauseCategory,
    affected_metric: str,
    context: AnomalyContext,
    responsible_process: Optional[str],
    process_share: float,
) -> str:
    """Produce a grounded, human-readable explanation of the root cause."""

    if category == RootCauseCategory.RUNAWAY_PROCESS and responsible_process:
        resource = "CPU" if affected_metric == "cpu_usage" else "memory"
        return (
            f"{responsible_process} is consuming approximately {process_share * 100:.0f}% "
            f"of total {resource} usage, making it the dominant contributor to this anomaly."
        )

    if category == RootCauseCategory.CPU_SATURATION:
        return (
            f"CPU usage reached {context.cpu_usage:.1f}%, exceeding safe operating levels, "
            f"without a single dominant process — likely caused by cumulative load across "
            f"multiple processes."
        )

    if category == RootCauseCategory.MEMORY_PRESSURE:
        return (
            f"RAM usage reached {context.ram_usage:.1f}%, indicating system-wide memory "
            f"pressure not attributable to a single process."
        )

    if category == RootCauseCategory.DISK_SPACE_EXHAUSTION:
        return (
            f"Disk usage reached {context.disk_usage:.1f}%, approaching capacity limits "
            f"and risking write failures or degraded performance."
        )

    if category == RootCauseCategory.DISK_IO_BOTTLENECK:
        total_io = context.disk_read_bps + context.disk_write_bps
        return (
            f"Combined disk I/O reached {total_io / 1_000_000:.1f} MB/s, exceeding typical "
            f"throughput and suggesting a disk I/O bottleneck."
        )

    if category == RootCauseCategory.NETWORK_SATURATION:
        total_net = context.network_in_bps + context.network_out_bps
        return (
            f"Combined network throughput reached {total_net / 1_000_000:.1f} MB/s, "
            f"indicating network saturation."
        )

    if category == RootCauseCategory.SYSTEM_INSTABILITY:
        return (
            f"Multiple metrics ({', '.join(context.affected_metrics)}) deviated simultaneously, "
            f"suggesting broader system instability rather than a single isolated cause."
        )

    return (
        f"An anomaly was detected in {affected_metric.replace('_', ' ')}, but no single "
        f"dominant cause could be conclusively identified from available data."
    )


def _generate_recommendation(
    category: RootCauseCategory,
    responsible_process: Optional[str],
) -> str:
    """Map a root cause category to an actionable recommendation."""
    recommendations = {
        RootCauseCategory.RUNAWAY_PROCESS: (
            f"Restart or terminate {responsible_process} if it continues consuming "
            f"excessive resources." if responsible_process
            else "Identify and restart the dominant resource-consuming process."
        ),
        RootCauseCategory.CPU_SATURATION: "Close unused applications or reschedule non-critical workloads.",
        RootCauseCategory.MEMORY_PRESSURE: "Close unused applications and monitor for memory leaks.",
        RootCauseCategory.DISK_SPACE_EXHAUSTION: "Free up disk space immediately or expand storage capacity.",
        RootCauseCategory.DISK_IO_BOTTLENECK: "Investigate processes performing heavy disk I/O and defer non-critical writes.",
        RootCauseCategory.NETWORK_SATURATION: "Investigate abnormal network activity and consider running a malware scan.",
        RootCauseCategory.SYSTEM_INSTABILITY: "Perform a full system health review; consider a controlled restart.",
        RootCauseCategory.UNKNOWN: "Continue monitoring; insufficient evidence for a specific corrective action.",
    }
    return recommendations.get(category, "Monitor the affected metric closely.")


# =====================================================================
# CORE ANALYSIS
# =====================================================================

def analyze_root_cause(
    context: AnomalyContext,
    config: RootCauseConfig = DEFAULT_CONFIG,
) -> RootCauseResult:
    """
    Perform explainable root cause analysis for a single anomaly.

    Args:
        context: AnomalyContext bundling the anomaly and surrounding
            monitoring state (metrics, processes, health score).
        config: RootCauseConfig instance.

    Returns:
        A fully populated RootCauseResult.

    Raises:
        ValueError: if context.affected_metrics is empty.
    """
    try:
        if not context.affected_metrics:
            raise ValueError("AnomalyContext.affected_metrics must not be empty")

        category, affected_metric = _classify_root_cause(context, config)

        metric_to_attr = {"cpu_usage": "cpu_usage", "ram_usage": "ram_usage"}
        responsible_process, process_share = (None, 0.0)
        if affected_metric in ("cpu_usage", "ram_usage"):
            responsible_process, process_share = _identify_responsible_process(
                context.processes, affected_metric, config
            )

        severity = Severity(config.severity_by_category.get(category.value, Severity.LOW.value))

        explanation = _generate_explanation(
            category, affected_metric, context, responsible_process, process_share
        )
        recommendation = _generate_recommendation(category, responsible_process)

        result = RootCauseResult(
            analysis_id=str(uuid.uuid4()),
            timestamp=context.timestamp,
            anomaly_id=context.anomaly_id,
            affected_metric=affected_metric,
            responsible_process=responsible_process,
            root_cause_category=category.value,
            severity=severity.value,
            explanation=explanation,
            recommended_action=recommendation,
            evidence={
                "cpu_usage": context.cpu_usage,
                "ram_usage": context.ram_usage,
                "disk_usage": context.disk_usage,
                "disk_read_bps": context.disk_read_bps,
                "disk_write_bps": context.disk_write_bps,
                "network_in_bps": context.network_in_bps,
                "network_out_bps": context.network_out_bps,
                "anomaly_score": context.anomaly_score,
                "current_health_score": context.current_health_score,
                "process_share": process_share,
            },
        )

        logger.info(
            "Root cause analyzed [%s] category=%s severity=%s metric=%s process=%s",
            result.analysis_id, category.value, severity.value,
            affected_metric, responsible_process,
        )

        return result

    except Exception as exc:
        logger.exception("Root cause analysis failed: %s", exc)
        raise


def analyze_root_cause_batch(
    contexts: list[AnomalyContext],
    config: RootCauseConfig = DEFAULT_CONFIG,
) -> list[RootCauseResult]:
    """Analyze a batch of anomaly contexts, skipping any that fail individually."""
    results: list[RootCauseResult] = []
    for context in contexts:
        try:
            results.append(analyze_root_cause(context, config))
        except Exception as exc:
            logger.error("Skipping root cause analysis for anomaly %s: %s", context.anomaly_id, exc)
    return results


# =====================================================================
# MODULE-LEVEL ENTRY POINT (for ai_engine.py / main.py)
# =====================================================================

def run_root_cause_analysis(
    anomaly_id: str,
    affected_metrics: list[str],
    anomaly_score: float,
    cpu_usage: float,
    ram_usage: float,
    disk_usage: float,
    disk_read_bps: float = 0.0,
    disk_write_bps: float = 0.0,
    network_in_bps: float = 0.0,
    network_out_bps: float = 0.0,
    processes: Optional[list[dict[str, Any]]] = None,
    current_health_score: Optional[float] = None,
    timestamp: Optional[datetime] = None,
    config: RootCauseConfig = DEFAULT_CONFIG,
) -> RootCauseResult:
    """
    Convenience entry point invoked automatically from main.py / ai_engine.py
    whenever anomaly_detection.py flags a new anomaly. Builds an
    AnomalyContext from raw values and returns the analysis result.
    """
    process_contexts = [
        ProcessContext(
            name=p.get("name", "unknown"),
            pid=p.get("pid"),
            cpu_percent=p.get("cpu_percent", 0.0),
            memory_percent=p.get("memory_percent", 0.0),
        )
        for p in (processes or [])
    ]

    context = AnomalyContext(
        anomaly_id=anomaly_id,
        timestamp=timestamp or datetime.utcnow(),
        affected_metrics=affected_metrics,
        anomaly_score=anomaly_score,
        cpu_usage=cpu_usage,
        ram_usage=ram_usage,
        disk_usage=disk_usage,
        disk_read_bps=disk_read_bps,
        disk_write_bps=disk_write_bps,
        network_in_bps=network_in_bps,
        network_out_bps=network_out_bps,
        processes=process_contexts,
        current_health_score=current_health_score,
    )

    return analyze_root_cause(context, config)


# =====================================================================
# EXPORT
# =====================================================================

def export_result(result: RootCauseResult, fmt: str = "dict") -> Any:
    """Export a RootCauseResult as dict or JSON for API/dashboard consumption."""
    data = result.to_dict()

    if fmt == "dict":
        return data
    if fmt == "json":
        import json
        return json.dumps(data, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


__all__ = [
    "RootCauseConfig",
    "DEFAULT_CONFIG",
    "Severity",
    "RootCauseCategory",
    "ProcessContext",
    "AnomalyContext",
    "RootCauseResult",
    "analyze_root_cause",
    "analyze_root_cause_batch",
    "run_root_cause_analysis",
    "export_result",
]