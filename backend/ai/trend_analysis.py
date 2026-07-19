"""
trend_analysis.py

Explainable AI Trend Analysis Engine — Lavender Trinetra Platform
=====================================================================

Analyzes historical monitoring data to detect resource usage trends
across CPU, RAM, Disk, Network, and per-process activity — including
sustained growth patterns indicative of memory leaks — and produces
structured, human-readable trend summaries.

Integrates with:
    - monitoring/collector.py   (historical + real-time metrics source)
    - ai/predictive_alerts.py   (consumes slope/direction for forecasting)
    - ai/recommendations.py     (consumes trend direction + explanation)
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

import numpy as np
import pandas as pd

logger = logging.getLogger("lavender_trinetra.ai.trend_analysis")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class TrendDirection(str, Enum):
    INCREASING = "Increasing"
    DECREASING = "Decreasing"
    STABLE = "Stable"
    VOLATILE = "Volatile"


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class TrendAnalysisConfig:
    """Tunable parameters for trend detection and classification."""

    metrics: list[str] = field(default_factory=lambda: [
        "cpu_usage",
        "ram_usage",
        "disk_usage",
        "network_in_bps",
        "network_out_bps",
    ])

    min_samples: int = 6

    # Relative slope thresholds (fraction of series mean per sample) used
    # to classify a trend as increasing/decreasing vs. stable.
    stable_slope_ratio: float = 0.005

    # Coefficient of variation above which a series is considered volatile
    # rather than trending, regardless of slope.
    volatility_cv_threshold: float = 0.35

    # Minimum R^2 (goodness of linear fit) required to trust the slope
    # direction; below this, classify as volatile.
    min_r_squared: float = 0.3

    # Fraction of consecutive non-decreasing samples required to flag a
    # metric as sustained ("leak-like") growth.
    monotonic_growth_fraction: float = 0.75

    # Process memory growth threshold (percentage points over the window)
    # used to flag a possible per-process memory leak.
    process_memory_leak_growth_pct: float = 10.0

    severity_slope_ratio_thresholds: dict[str, float] = field(default_factory=lambda: {
        "critical": 0.05,
        "high": 0.03,
        "medium": 0.015,
    })


DEFAULT_CONFIG = TrendAnalysisConfig()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class ProcessMemorySample:
    """A single process's memory usage at a point in time."""

    timestamp: datetime
    name: str
    memory_percent: float


@dataclass
class TrendResult:
    """Structured, explainable trend result for a single metric."""

    trend_id: str
    timestamp: datetime
    metric: str
    direction: str
    severity: str
    slope_per_sample: float
    r_squared: float
    current_value: float
    window_start_value: float
    window_samples: int
    explanation: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class MemoryLeakResult:
    """Structured result flagging a possible per-process memory leak."""

    leak_id: str
    timestamp: datetime
    process_name: str
    growth_pct: float
    window_samples: int
    explanation: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# =====================================================================
# CORE STATISTICS
# =====================================================================

def _linear_fit(series: pd.Series) -> tuple[float, float, float]:
    """
    Fit a simple linear regression over series index position.

    Returns:
        (slope, intercept, r_squared)
    """
    n = len(series)
    if n < 2:
        return 0.0, float(series.iloc[-1]) if n else 0.0, 0.0

    y = series.values.astype(float)
    x = np.arange(n)

    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept

    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return float(slope), float(intercept), max(0.0, r_squared)


def _coefficient_of_variation(series: pd.Series) -> float:
    """Compute the coefficient of variation (std / mean) for a series."""
    values = series.values.astype(float)
    mean_val = np.mean(values)
    if mean_val == 0:
        return 0.0
    return float(np.std(values) / abs(mean_val))


def _classify_direction(
    slope: float,
    r_squared: float,
    cv: float,
    series_mean: float,
    config: TrendAnalysisConfig,
) -> TrendDirection:
    """Classify a metric's trend direction from slope, fit quality, and volatility."""
    if cv >= config.volatility_cv_threshold or r_squared < config.min_r_squared:
        return TrendDirection.VOLATILE

    if series_mean == 0:
        relative_slope = 0.0
    else:
        relative_slope = abs(slope) / abs(series_mean)

    if relative_slope < config.stable_slope_ratio:
        return TrendDirection.STABLE

    return TrendDirection.INCREASING if slope > 0 else TrendDirection.DECREASING


def _classify_severity(
    slope: float,
    series_mean: float,
    config: TrendAnalysisConfig,
) -> Severity:
    """Classify trend severity from the magnitude of relative slope."""
    if series_mean == 0:
        relative_slope = 0.0
    else:
        relative_slope = abs(slope) / abs(series_mean)

    thresholds = config.severity_slope_ratio_thresholds
    if relative_slope >= thresholds["critical"]:
        return Severity.CRITICAL
    if relative_slope >= thresholds["high"]:
        return Severity.HIGH
    if relative_slope >= thresholds["medium"]:
        return Severity.MEDIUM
    return Severity.LOW


# =====================================================================
# EXPLANATION
# =====================================================================

def _generate_trend_explanation(
    metric: str,
    direction: TrendDirection,
    current_value: float,
    window_start_value: float,
    window_samples: int,
) -> str:
    """Produce a grounded, human-readable trend explanation."""
    metric_label = metric.replace("_", " ").title()
    delta = current_value - window_start_value

    if direction == TrendDirection.VOLATILE:
        return (
            f"{metric_label} has fluctuated significantly over the past {window_samples} samples "
            f"without a clear directional trend."
        )

    if direction == TrendDirection.STABLE:
        return f"{metric_label} has remained stable over the past {window_samples} samples."

    trend_word = "increased" if direction == TrendDirection.INCREASING else "decreased"
    return (
        f"{metric_label} has {trend_word} from {window_start_value:.1f} to {current_value:.1f} "
        f"over the past {window_samples} samples (change of {abs(delta):.1f})."
    )


def _generate_leak_explanation(
    process_name: str,
    growth_pct: float,
    window_samples: int,
) -> str:
    """Produce a grounded explanation for a possible process memory leak."""
    return (
        f"Memory usage of {process_name} has grown by {growth_pct:.1f} percentage points "
        f"over the past {window_samples} samples without recovery, suggesting a possible "
        f"memory leak."
    )


# =====================================================================
# METRIC TREND ANALYSIS
# =====================================================================

def analyze_metric_trend(
    series: pd.Series,
    metric: str,
    config: TrendAnalysisConfig = DEFAULT_CONFIG,
) -> Optional[TrendResult]:
    """
    Analyze a single metric's historical time series and produce a
    structured TrendResult.

    Args:
        series: Time-ordered pandas Series of metric values.
        metric: Name of the metric (e.g. "cpu_usage").
        config: TrendAnalysisConfig instance.

    Returns:
        A TrendResult, or None if there is insufficient data.
    """
    try:
        clean = series.dropna()
        if len(clean) < config.min_samples:
            logger.debug("Insufficient samples for trend analysis on %s (%d)", metric, len(clean))
            return None

        slope, _, r_squared = _linear_fit(clean)
        cv = _coefficient_of_variation(clean)
        series_mean = float(clean.mean())

        direction = _classify_direction(slope, r_squared, cv, series_mean, config)
        severity = _classify_severity(slope, series_mean, config)

        current_value = float(clean.iloc[-1])
        window_start_value = float(clean.iloc[0])

        explanation = _generate_trend_explanation(
            metric, direction, current_value, window_start_value, len(clean)
        )

        result = TrendResult(
            trend_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            metric=metric,
            direction=direction.value,
            severity=severity.value if direction != TrendDirection.STABLE else Severity.LOW.value,
            slope_per_sample=round(slope, 6),
            r_squared=round(r_squared, 4),
            current_value=current_value,
            window_start_value=window_start_value,
            window_samples=len(clean),
            explanation=explanation,
            evidence={"coefficient_of_variation": round(cv, 4)},
        )

        return result

    except Exception as exc:
        logger.exception("Trend analysis failed for metric %s: %s", metric, exc)
        return None


def analyze_all_trends(
    history: pd.DataFrame,
    config: TrendAnalysisConfig = DEFAULT_CONFIG,
) -> list[TrendResult]:
    """
    Analyze trends across all configured metrics present in the
    historical monitoring DataFrame.

    Args:
        history: DataFrame with columns matching config.metrics.
        config: TrendAnalysisConfig instance.

    Returns:
        List of TrendResult objects (metrics with insufficient data
        or missing columns are skipped).
    """
    results: list[TrendResult] = []
    for metric in config.metrics:
        if metric not in history.columns:
            logger.debug("Metric %s not present in history; skipping", metric)
            continue
        result = analyze_metric_trend(history[metric], metric, config)
        if result:
            results.append(result)
    return results


# =====================================================================
# MEMORY LEAK DETECTION (RESOURCE-LEVEL + PROCESS-LEVEL)
# =====================================================================

def detect_resource_growth(
    trend_results: list[TrendResult],
    config: TrendAnalysisConfig = DEFAULT_CONFIG,
) -> list[TrendResult]:
    """
    Filter trend results down to those representing sustained,
    high-confidence resource growth (candidate memory/disk leak signals
    at the system level).
    """
    return [
        t for t in trend_results
        if t.direction == TrendDirection.INCREASING.value
        and t.r_squared >= config.min_r_squared
        and t.severity in (Severity.MEDIUM.value, Severity.HIGH.value, Severity.CRITICAL.value)
    ]


def detect_process_memory_leaks(
    process_samples: list[ProcessMemorySample],
    config: TrendAnalysisConfig = DEFAULT_CONFIG,
) -> list[MemoryLeakResult]:
    """
    Analyze per-process memory samples grouped by process name to detect
    sustained, non-recovering growth indicative of a memory leak.

    Args:
        process_samples: List of ProcessMemorySample across time for one
            or more processes.
        config: TrendAnalysisConfig instance.

    Returns:
        List of MemoryLeakResult for processes flagged as likely leaking.
    """
    results: list[MemoryLeakResult] = []

    if not process_samples:
        return results

    df = pd.DataFrame([asdict(s) for s in process_samples])
    if df.empty or "name" not in df.columns:
        return results

    for process_name, group in df.groupby("name"):
        try:
            group_sorted = group.sort_values("timestamp")
            values = group_sorted["memory_percent"].astype(float)

            if len(values) < config.min_samples:
                continue

            diffs = values.diff().dropna()
            if diffs.empty:
                continue

            monotonic_fraction = float((diffs >= 0).mean())
            growth_pct = float(values.iloc[-1] - values.iloc[0])

            if (
                monotonic_fraction >= config.monotonic_growth_fraction
                and growth_pct >= config.process_memory_leak_growth_pct
            ):
                explanation = _generate_leak_explanation(process_name, growth_pct, len(values))
                results.append(MemoryLeakResult(
                    leak_id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    process_name=process_name,
                    growth_pct=round(growth_pct, 2),
                    window_samples=len(values),
                    explanation=explanation,
                    evidence={
                        "monotonic_fraction": round(monotonic_fraction, 3),
                        "start_memory_percent": float(values.iloc[0]),
                        "end_memory_percent": float(values.iloc[-1]),
                    },
                ))
        except Exception as exc:
            logger.error("Memory leak detection failed for process %s: %s", process_name, exc)

    return results


# =====================================================================
# MODULE-LEVEL ENTRY POINT (for ai_engine.py / main.py)
# =====================================================================

def run_trend_analysis(
    history: pd.DataFrame,
    process_samples: Optional[list[dict[str, Any]]] = None,
    config: TrendAnalysisConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """
    Convenience entry point invoked automatically from main.py / ai_engine.py
    on each monitoring cycle (or periodically) once sufficient history has
    accumulated.

    Args:
        history: Historical monitoring DataFrame (e.g. loaded via
            collector.py or backend/data/system_metrics.csv).
        process_samples: Optional list of per-process memory samples
            (dicts with timestamp, name, memory_percent) for leak detection.
        config: TrendAnalysisConfig instance.

    Returns:
        Dict with keys "trends", "resource_growth", "process_memory_leaks".
    """
    try:
        trends = analyze_all_trends(history, config)
        resource_growth = detect_resource_growth(trends, config)

        leak_samples = [
            ProcessMemorySample(
                timestamp=pd.to_datetime(p["timestamp"]),
                name=p["name"],
                memory_percent=float(p["memory_percent"]),
            )
            for p in (process_samples or [])
            if "timestamp" in p and "name" in p and "memory_percent" in p
        ]
        process_leaks = detect_process_memory_leaks(leak_samples, config)

        logger.info(
            "Trend analysis complete: %d trend(s), %d growth signal(s), %d process leak(s)",
            len(trends), len(resource_growth), len(process_leaks),
        )

        return {
            "trends": trends,
            "resource_growth": resource_growth,
            "process_memory_leaks": process_leaks,
        }

    except Exception as exc:
        logger.exception("run_trend_analysis failed: %s", exc)
        return {"trends": [], "resource_growth": [], "process_memory_leaks": []}


# =====================================================================
# EXPORT
# =====================================================================

def export_trends(trends: list[TrendResult], fmt: str = "dict") -> Any:
    """Export a list of TrendResult objects as dict, DataFrame, or JSON."""
    records = [t.to_dict() for t in trends]

    if fmt == "dict":
        return records
    if fmt == "dataframe":
        return pd.DataFrame(records)
    if fmt == "json":
        import json
        return json.dumps(records, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


def export_memory_leaks(leaks: list[MemoryLeakResult], fmt: str = "dict") -> Any:
    """Export a list of MemoryLeakResult objects as dict, DataFrame, or JSON."""
    records = [leak.to_dict() for leak in leaks]

    if fmt == "dict":
        return records
    if fmt == "dataframe":
        return pd.DataFrame(records)
    if fmt == "json":
        import json
        return json.dumps(records, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


__all__ = [
    "TrendAnalysisConfig",
    "DEFAULT_CONFIG",
    "TrendDirection",
    "Severity",
    "ProcessMemorySample",
    "TrendResult",
    "MemoryLeakResult",
    "analyze_metric_trend",
    "analyze_all_trends",
    "detect_resource_growth",
    "detect_process_memory_leaks",
    "run_trend_analysis",
    "export_trends",
    "export_memory_leaks",
]