"""
predictive_alerts.py

Explainable AI Predictive Alert Engine — Lavender Trinetra Platform
=====================================================================

Forecasts potential system issues *before* threshold violations occur by
combining lightweight statistical forecasting (linear trend extrapolation,
exponential smoothing) with signals from the anomaly detection, trend
analysis, and health scoring subsystems.

Every prediction is required to carry a human-readable explanation
(Explainable AI) and a concrete recommended action — predictions without
either are considered invalid and are dropped before export.

Designed to integrate with:
    - monitoring/collector.py      (real-time + historical metrics)
    - ai/anomaly_detection.py      (active anomaly signals)
    - ai/trend_analysis.py         (slope / trend direction)
    - ai/health_score.py           (current composite health score)
    - ai/recommendations.py        (shared recommendation vocabulary)
    - ai/root_cause.py             (responsible process attribution)
    - api/routes.py / dashboard    (consumes exported predictions)

Author: Lavender Trinetra AI Engineering
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    import joblib
except ImportError:  # pragma: no cover - joblib optional at runtime
    joblib = None

logger = logging.getLogger("lavender_trinetra.ai.predictive_alerts")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Severity(str, Enum):
    INFO = "Info"
    WARNING = "Warning"
    MAJOR = "Major"
    CRITICAL = "Critical"


class PredictedEventType(str, Enum):
    CPU_OVERLOAD = "CPU Overload"
    RAM_EXHAUSTION = "RAM Exhaustion"
    MEMORY_LEAK_PROGRESSION = "Memory Leak Progression"
    DISK_SATURATION = "Disk Saturation"
    NETWORK_CONGESTION = "Network Congestion"
    ANOMALY_PROBABILITY_INCREASE = "Increasing Anomaly Probability"
    HEALTH_DEGRADATION = "System Health Degradation"
    RESOURCE_BOTTLENECK = "Resource Bottleneck"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class PredictionConfig:
    """Tunable thresholds and forecasting parameters."""

    # Forecast horizon in minutes for near-term prediction window
    forecast_horizon_minutes: int = 15

    # Minimum number of historical samples required to attempt a forecast
    min_history_samples: int = 6

    # Metric ceiling thresholds (percent, 0-100) used to estimate ETA
    cpu_threshold: float = 90.0
    ram_threshold: float = 90.0
    disk_threshold: float = 90.0

    # Network congestion threshold expressed as % increase over baseline
    network_increase_threshold_pct: float = 35.0

    # Minimum probability required for a prediction to be emitted at all
    min_emit_probability: float = 0.30

    # Smoothing factor for exponential weighted forecasting
    ewm_alpha: float = 0.35

    # Sampling interval assumption (minutes) between historical points,
    # used only when timestamps are missing / irregular.
    default_sample_interval_minutes: float = 1.0


DEFAULT_CONFIG = PredictionConfig()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class MonitoringSnapshot:
    """Normalized input bundle consumed by the prediction engine."""

    timestamp: datetime
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    network_in_bps: float = 0.0
    network_out_bps: float = 0.0
    top_processes: list[dict[str, Any]] = field(default_factory=list)
    current_health_score: Optional[float] = None
    active_anomalies: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Prediction:
    """A single explainable predictive alert."""

    prediction_id: str
    timestamp: datetime
    predicted_event: str
    probability: float
    confidence_score: float
    eta_minutes: Optional[float]
    affected_metric: str
    responsible_process: Optional[str]
    severity: str
    risk_level: str
    recommended_action: str
    explanation: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def is_valid(self) -> bool:
        """A prediction without an explanation or recommendation is invalid."""
        return bool(self.explanation.strip()) and bool(self.recommended_action.strip())


# =====================================================================
# HISTORY LOADING
# =====================================================================

def load_monitoring_history(
    source: pd.DataFrame | list[dict[str, Any]] | str,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Load historical monitoring data into a normalized, time-sorted DataFrame.

    Args:
        source: One of:
            - a pandas DataFrame already in memory
            - a list of dict records (e.g. from collector.py buffers)
            - a path to a CSV file (e.g. backend/data/system_metrics.csv)
        timestamp_col: name of the timestamp column to parse/sort by.

    Returns:
        A DataFrame sorted ascending by timestamp with a DatetimeIndex.

    Raises:
        ValueError: if the source type is unsupported or required columns
            are missing.
    """
    try:
        if isinstance(source, pd.DataFrame):
            df = source.copy()
        elif isinstance(source, list):
            df = pd.DataFrame(source)
        elif isinstance(source, str):
            df = pd.read_csv(source)
        else:
            raise ValueError(f"Unsupported monitoring history source type: {type(source)}")

        if timestamp_col not in df.columns:
            raise ValueError(f"Missing required column '{timestamp_col}' in monitoring history")

        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce")
        df = df.dropna(subset=[timestamp_col])
        df = df.sort_values(timestamp_col).reset_index(drop=True)
        df = df.set_index(timestamp_col, drop=False)
        return df

    except Exception as exc:
        logger.exception("Failed to load monitoring history: %s", exc)
        raise


# =====================================================================
# FEATURE PREPARATION
# =====================================================================

def prepare_prediction_features(
    history: pd.DataFrame,
    snapshot: MonitoringSnapshot,
    config: PredictionConfig = DEFAULT_CONFIG,
) -> dict[str, pd.Series]:
    """
    Build per-metric time series (history + current snapshot appended)
    ready for forecasting.

    Args:
        history: Output of load_monitoring_history().
        snapshot: Current real-time monitoring snapshot.
        config: PredictionConfig instance.

    Returns:
        Dict mapping metric name -> pandas Series indexed by timestamp,
        ascending, with the current snapshot appended as the latest point.
    """
    metrics = ["cpu_usage", "ram_usage", "disk_usage", "network_in_bps", "network_out_bps"]
    series_map: dict[str, pd.Series] = {}

    snapshot_values = {
        "cpu_usage": snapshot.cpu_usage,
        "ram_usage": snapshot.ram_usage,
        "disk_usage": snapshot.disk_usage,
        "network_in_bps": snapshot.network_in_bps,
        "network_out_bps": snapshot.network_out_bps,
    }

    for metric in metrics:
        if metric in history.columns:
            s = history[metric].dropna().astype(float)
        else:
            s = pd.Series(dtype=float)

        # Append current snapshot as latest data point
        s = pd.concat([s, pd.Series([snapshot_values[metric]], index=[snapshot.timestamp])])
        s = s[~s.index.duplicated(keep="last")].sort_index()
        series_map[metric] = s

    return series_map


# =====================================================================
# FORECASTING
# =====================================================================

def _linear_trend_forecast(series: pd.Series, steps_ahead: int) -> tuple[float, float]:
    """
    Fit a simple linear regression (least squares) over the series index
    position and project `steps_ahead` samples forward.

    Returns:
        (forecast_value, slope_per_step)
    """
    if len(series) < 2:
        last_val = float(series.iloc[-1]) if len(series) else 0.0
        return last_val, 0.0

    y = series.values.astype(float)
    x = np.arange(len(y))

    # Least squares fit: y = slope * x + intercept
    slope, intercept = np.polyfit(x, y, 1)
    forecast_x = len(y) - 1 + steps_ahead
    forecast_value = slope * forecast_x + intercept
    return float(forecast_value), float(slope)


def _exponential_smoothing_forecast(series: pd.Series, alpha: float) -> float:
    """Simple exponentially weighted moving average forecast (next step)."""
    if series.empty:
        return 0.0
    ewm = series.ewm(alpha=alpha, adjust=False).mean()
    return float(ewm.iloc[-1])


def forecast_metrics(
    series_map: dict[str, pd.Series],
    config: PredictionConfig = DEFAULT_CONFIG,
) -> dict[str, dict[str, float]]:
    """
    Forecast each metric's near-term trajectory using a blend of linear
    trend extrapolation and exponential smoothing.

    Returns:
        Dict mapping metric -> {
            "current": float,
            "forecast": float,          # blended forecast at horizon end
            "slope_per_sample": float,  # linear trend slope
            "sample_interval_minutes": float,
        }
    """
    results: dict[str, dict[str, float]] = {}

    for metric, series in series_map.items():
        if series.empty:
            results[metric] = {
                "current": 0.0,
                "forecast": 0.0,
                "slope_per_sample": 0.0,
                "sample_interval_minutes": config.default_sample_interval_minutes,
            }
            continue

        # Estimate sampling interval from index if possible
        interval_minutes = config.default_sample_interval_minutes
        if len(series.index) >= 2:
            deltas = series.index.to_series().diff().dropna()
            if not deltas.empty:
                median_seconds = deltas.median().total_seconds()
                if median_seconds > 0:
                    interval_minutes = median_seconds / 60.0

        steps_ahead = max(1, int(round(config.forecast_horizon_minutes / interval_minutes)))

        if len(series) >= config.min_history_samples:
            linear_forecast, slope = _linear_trend_forecast(series, steps_ahead)
            smoothed = _exponential_smoothing_forecast(series, config.ewm_alpha)
            # Blend: weight linear trend more heavily for longer horizons,
            # smoothing more heavily for short/noisy series.
            blended_forecast = (0.7 * linear_forecast) + (0.3 * smoothed)
        else:
            # Not enough history for a reliable trend — fall back to smoothing
            blended_forecast = _exponential_smoothing_forecast(series, config.ewm_alpha)
            slope = 0.0

        results[metric] = {
            "current": float(series.iloc[-1]),
            "forecast": float(blended_forecast),
            "slope_per_sample": float(slope),
            "sample_interval_minutes": interval_minutes,
        }

    return results


# =====================================================================
# CONFIDENCE + RISK
# =====================================================================

def calculate_prediction_confidence(
    series: pd.Series,
    config: PredictionConfig = DEFAULT_CONFIG,
) -> float:
    """
    Estimate confidence (0-1) in a forecast based on history length and
    variance stability. More samples + lower relative volatility -> higher
    confidence.
    """
    n = len(series)
    if n < 2:
        return 0.2

    sample_component = min(1.0, n / max(config.min_history_samples * 3, 1))

    values = series.values.astype(float)
    mean_val = np.mean(values) if np.mean(values) != 0 else 1e-6
    volatility = np.std(values) / abs(mean_val)
    volatility_component = max(0.0, 1.0 - min(volatility, 1.0))

    confidence = round(float(0.5 * sample_component + 0.5 * volatility_component), 3)
    return max(0.05, min(confidence, 0.99))


def assign_risk_level(probability: float, severity: Severity) -> RiskLevel:
    """
    Assign a risk level from predicted probability and severity, per the
    platform's standard escalation matrix.
    """
    if severity == Severity.CRITICAL and probability >= 0.6:
        return RiskLevel.CRITICAL
    if probability >= 0.75:
        return RiskLevel.CRITICAL if severity in (Severity.MAJOR, Severity.CRITICAL) else RiskLevel.HIGH
    if probability >= 0.55:
        return RiskLevel.HIGH
    if probability >= 0.35:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


# =====================================================================
# ETA ESTIMATION
# =====================================================================

def _estimate_eta_minutes(
    current: float,
    slope_per_sample: float,
    sample_interval_minutes: float,
    threshold: float,
) -> Optional[float]:
    """
    Estimate minutes until `current` reaches `threshold` given a linear
    slope per sample. Returns None if the metric is not trending toward
    the threshold.
    """
    if slope_per_sample <= 0:
        return None
    if current >= threshold:
        return 0.0

    samples_needed = (threshold - current) / slope_per_sample
    if samples_needed <= 0:
        return None

    return round(samples_needed * sample_interval_minutes, 1)


# =====================================================================
# EXPLANATIONS + RECOMMENDATIONS
# =====================================================================

def generate_prediction_explanation(
    event_type: PredictedEventType,
    metric: str,
    current: float,
    forecast: float,
    eta_minutes: Optional[float],
    responsible_process: Optional[str],
    window_minutes: float,
) -> str:
    """
    Produce a human-readable, evidence-grounded explanation for a
    prediction. Every prediction must carry one of these.
    """
    trend_direction = "increased" if forecast > current else "decreased"
    delta = abs(forecast - current)

    if event_type == PredictedEventType.MEMORY_LEAK_PROGRESSION and responsible_process:
        return (
            f"Memory consumption of {responsible_process} has continuously increased "
            f"without recovery over the past {window_minutes:.0f} minutes, suggesting a "
            f"possible memory leak."
        )

    if event_type == PredictedEventType.NETWORK_CONGESTION:
        pct_change = (delta / current * 100.0) if current > 0 else 0.0
        return (
            f"Network traffic has {trend_direction} by approximately {pct_change:.0f}% "
            f"over the previous monitoring window and may result in congestion."
        )

    if eta_minutes is not None:
        return (
            f"{metric.replace('_', ' ').title()} has {trend_direction} steadily over the past "
            f"{window_minutes:.0f} minutes and is expected to exceed the configured threshold "
            f"within approximately {eta_minutes:.0f} minute(s)."
        )

    return (
        f"{metric.replace('_', ' ').title()} has {trend_direction} over the past "
        f"{window_minutes:.0f} minutes, indicating a developing trend worth monitoring."
    )


def generate_recommendation(
    event_type: PredictedEventType,
    responsible_process: Optional[str],
) -> str:
    """Map a predicted event type to an actionable recommendation."""
    recommendations = {
        PredictedEventType.CPU_OVERLOAD: (
            f"Consider closing or throttling {responsible_process}." if responsible_process
            else "Close unused applications or throttle high-CPU processes."
        ),
        PredictedEventType.RAM_EXHAUSTION: (
            f"Restart {responsible_process} or close unused applications to free memory."
            if responsible_process else "Close unused applications to free memory."
        ),
        PredictedEventType.MEMORY_LEAK_PROGRESSION: (
            f"Restart {responsible_process}; monitor for recurring memory growth."
            if responsible_process else "Monitor memory usage and restart the responsible process."
        ),
        PredictedEventType.DISK_SATURATION: "Free up disk space or move data to secondary storage.",
        PredictedEventType.NETWORK_CONGESTION: "Investigate abnormal network activity; consider running a malware scan.",
        PredictedEventType.ANOMALY_PROBABILITY_INCREASE: "Review recent anomalies and run a full malware scan.",
        PredictedEventType.HEALTH_DEGRADATION: "Delay heavy workloads and monitor system health closely.",
        PredictedEventType.RESOURCE_BOTTLENECK: "Investigate top resource-consuming processes and consider scaling resources.",
    }
    return recommendations.get(event_type, "Monitor the affected metric closely.")


# =====================================================================
# CORE PREDICTION LOGIC
# =====================================================================

def _build_prediction(
    event_type: PredictedEventType,
    metric: str,
    forecast_data: dict[str, float],
    threshold: Optional[float],
    probability: float,
    confidence: float,
    responsible_process: Optional[str],
    severity: Severity,
    evidence: dict[str, Any],
) -> Prediction:
    """Assemble a fully-formed, self-explaining Prediction object."""
    eta = None
    if threshold is not None:
        eta = _estimate_eta_minutes(
            current=forecast_data["current"],
            slope_per_sample=forecast_data["slope_per_sample"],
            sample_interval_minutes=forecast_data["sample_interval_minutes"],
            threshold=threshold,
        )

    window_minutes = forecast_data["sample_interval_minutes"] * max(
        1, int(round(DEFAULT_CONFIG.min_history_samples))
    )

    explanation = generate_prediction_explanation(
        event_type=event_type,
        metric=metric,
        current=forecast_data["current"],
        forecast=forecast_data["forecast"],
        eta_minutes=eta,
        responsible_process=responsible_process,
        window_minutes=window_minutes,
    )

    recommendation = generate_recommendation(event_type, responsible_process)
    risk_level = assign_risk_level(probability, severity)

    return Prediction(
        prediction_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        predicted_event=event_type.value,
        probability=round(probability, 3),
        confidence_score=round(confidence, 3),
        eta_minutes=eta,
        affected_metric=metric,
        responsible_process=responsible_process,
        severity=severity.value,
        risk_level=risk_level.value,
        recommended_action=recommendation,
        explanation=explanation,
        evidence=evidence,
    )


def _identify_responsible_process(
    snapshot: MonitoringSnapshot,
    metric_key: str,
) -> Optional[str]:
    """
    Identify the top process contributing to a given metric, if
    top_processes data is available on the snapshot.
    """
    if not snapshot.top_processes:
        return None

    sort_key_map = {
        "cpu_usage": "cpu_percent",
        "ram_usage": "memory_percent",
    }
    sort_key = sort_key_map.get(metric_key)
    if not sort_key:
        return None

    candidates = [p for p in snapshot.top_processes if sort_key in p]
    if not candidates:
        return None

    top = max(candidates, key=lambda p: p.get(sort_key, 0))
    return top.get("name") or top.get("process_name")


def predict_future_events(
    history: pd.DataFrame,
    snapshot: MonitoringSnapshot,
    config: PredictionConfig = DEFAULT_CONFIG,
) -> list[Prediction]:
    """
    Main entry point: analyze historical + current monitoring data and
    produce a list of explainable predictive alerts.

    Args:
        history: DataFrame from load_monitoring_history().
        snapshot: Current MonitoringSnapshot (real-time + context from
            anomaly_detection.py, health_score.py, root_cause.py).
        config: PredictionConfig instance.

    Returns:
        List of valid Prediction objects (invalid/unexplained predictions
        are filtered out).
    """
    predictions: list[Prediction] = []

    try:
        series_map = prepare_prediction_features(history, snapshot, config)
        forecasts = forecast_metrics(series_map, config)

        # --- CPU Overload ---
        cpu_forecast = forecasts.get("cpu_usage")
        if cpu_forecast:
            confidence = calculate_prediction_confidence(series_map["cpu_usage"], config)
            if cpu_forecast["forecast"] >= config.cpu_threshold * 0.75:
                probability = min(1.0, cpu_forecast["forecast"] / config.cpu_threshold)
                if probability >= config.min_emit_probability:
                    process = _identify_responsible_process(snapshot, "cpu_usage")
                    severity = Severity.CRITICAL if cpu_forecast["forecast"] >= config.cpu_threshold else Severity.WARNING
                    predictions.append(_build_prediction(
                        event_type=PredictedEventType.CPU_OVERLOAD,
                        metric="cpu_usage",
                        forecast_data=cpu_forecast,
                        threshold=config.cpu_threshold,
                        probability=probability,
                        confidence=confidence,
                        responsible_process=process,
                        severity=severity,
                        evidence={
                            "current_cpu": cpu_forecast["current"],
                            "forecast_cpu": round(cpu_forecast["forecast"], 2),
                            "slope_per_sample": cpu_forecast["slope_per_sample"],
                        },
                    ))

        # --- RAM Exhaustion / Memory Leak ---
        ram_forecast = forecasts.get("ram_usage")
        if ram_forecast:
            confidence = calculate_prediction_confidence(series_map["ram_usage"], config)
            process = _identify_responsible_process(snapshot, "ram_usage")

            # Sustained, non-recovering growth suggests a leak rather than
            # ordinary exhaustion.
            ram_series = series_map["ram_usage"]
            is_monotonic_growth = (
                len(ram_series) >= config.min_history_samples
                and ram_series.diff().dropna().ge(0).mean() >= 0.8
            )

            if ram_forecast["forecast"] >= config.ram_threshold * 0.75:
                probability = min(1.0, ram_forecast["forecast"] / config.ram_threshold)
                if probability >= config.min_emit_probability:
                    event_type = (
                        PredictedEventType.MEMORY_LEAK_PROGRESSION
                        if is_monotonic_growth and process
                        else PredictedEventType.RAM_EXHAUSTION
                    )
                    severity = Severity.CRITICAL if ram_forecast["forecast"] >= config.ram_threshold else Severity.WARNING
                    predictions.append(_build_prediction(
                        event_type=event_type,
                        metric="ram_usage",
                        forecast_data=ram_forecast,
                        threshold=config.ram_threshold,
                        probability=probability,
                        confidence=confidence,
                        responsible_process=process,
                        severity=severity,
                        evidence={
                            "current_ram": ram_forecast["current"],
                            "forecast_ram": round(ram_forecast["forecast"], 2),
                            "monotonic_growth": is_monotonic_growth,
                        },
                    ))

        # --- Disk Saturation ---
        disk_forecast = forecasts.get("disk_usage")
        if disk_forecast:
            confidence = calculate_prediction_confidence(series_map["disk_usage"], config)
            if disk_forecast["forecast"] >= config.disk_threshold * 0.75:
                probability = min(1.0, disk_forecast["forecast"] / config.disk_threshold)
                if probability >= config.min_emit_probability:
                    severity = Severity.CRITICAL if disk_forecast["forecast"] >= config.disk_threshold else Severity.WARNING
                    predictions.append(_build_prediction(
                        event_type=PredictedEventType.DISK_SATURATION,
                        metric="disk_usage",
                        forecast_data=disk_forecast,
                        threshold=config.disk_threshold,
                        probability=probability,
                        confidence=confidence,
                        responsible_process=None,
                        severity=severity,
                        evidence={
                            "current_disk": disk_forecast["current"],
                            "forecast_disk": round(disk_forecast["forecast"], 2),
                        },
                    ))

        # --- Network Congestion ---
        for net_metric in ("network_in_bps", "network_out_bps"):
            net_forecast = forecasts.get(net_metric)
            if not net_forecast or net_forecast["current"] <= 0:
                continue
            pct_increase = ((net_forecast["forecast"] - net_forecast["current"]) / net_forecast["current"]) * 100.0
            if pct_increase >= config.network_increase_threshold_pct:
                confidence = calculate_prediction_confidence(series_map[net_metric], config)
                probability = min(1.0, pct_increase / (config.network_increase_threshold_pct * 2))
                if probability >= config.min_emit_probability:
                    predictions.append(_build_prediction(
                        event_type=PredictedEventType.NETWORK_CONGESTION,
                        metric=net_metric,
                        forecast_data=net_forecast,
                        threshold=None,
                        probability=probability,
                        confidence=confidence,
                        responsible_process=None,
                        severity=Severity.WARNING if pct_increase < 75 else Severity.MAJOR,
                        evidence={
                            "current": net_forecast["current"],
                            "forecast": round(net_forecast["forecast"], 2),
                            "pct_increase": round(pct_increase, 1),
                        },
                    ))

        # --- Increasing Anomaly Probability ---
        if snapshot.active_anomalies:
            anomaly_count = len(snapshot.active_anomalies)
            probability = min(1.0, 0.3 + 0.15 * anomaly_count)
            if probability >= config.min_emit_probability:
                avg_confidence = float(np.mean(
                    [a.get("confidence", 0.5) for a in snapshot.active_anomalies]
                ))
                predictions.append(_build_prediction(
                    event_type=PredictedEventType.ANOMALY_PROBABILITY_INCREASE,
                    metric="anomaly_rate",
                    forecast_data={
                        "current": float(anomaly_count),
                        "forecast": float(anomaly_count),
                        "slope_per_sample": 0.0,
                        "sample_interval_minutes": config.default_sample_interval_minutes,
                    },
                    threshold=None,
                    probability=probability,
                    confidence=round(avg_confidence, 3),
                    responsible_process=None,
                    severity=Severity.WARNING if anomaly_count < 3 else Severity.MAJOR,
                    evidence={"active_anomaly_count": anomaly_count},
                ))

        # --- System Health Degradation ---
        if snapshot.current_health_score is not None and snapshot.current_health_score < 70:
            probability = round((70 - snapshot.current_health_score) / 70, 3)
            if probability >= config.min_emit_probability:
                severity = Severity.CRITICAL if snapshot.current_health_score < 40 else Severity.WARNING
                predictions.append(_build_prediction(
                    event_type=PredictedEventType.HEALTH_DEGRADATION,
                    metric="health_score",
                    forecast_data={
                        "current": snapshot.current_health_score,
                        "forecast": snapshot.current_health_score,
                        "slope_per_sample": 0.0,
                        "sample_interval_minutes": config.default_sample_interval_minutes,
                    },
                    threshold=None,
                    probability=min(1.0, probability),
                    confidence=0.7,
                    responsible_process=None,
                    severity=severity,
                    evidence={"current_health_score": snapshot.current_health_score},
                ))

        # Filter to only valid, fully-explained predictions
        valid_predictions = [p for p in predictions if p.is_valid()]
        dropped = len(predictions) - len(valid_predictions)
        if dropped:
            logger.warning("Dropped %d prediction(s) missing explanation/recommendation", dropped)

        return valid_predictions

    except Exception as exc:
        logger.exception("predict_future_events failed: %s", exc)
        return []


# =====================================================================
# EXPORT
# =====================================================================

def export_predictions(
    predictions: list[Prediction],
    fmt: str = "dict",
) -> Any:
    """
    Export predictions for downstream consumption (API/dashboard/storage).

    Args:
        predictions: List of Prediction objects.
        fmt: One of "dict" (list of dicts), "dataframe", or "json".

    Returns:
        Data in the requested format.

    Raises:
        ValueError: if fmt is not supported.
    """
    records = [p.to_dict() for p in predictions]

    if fmt == "dict":
        return records
    if fmt == "dataframe":
        return pd.DataFrame(records)
    if fmt == "json":
        import json
        return json.dumps(records, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


# =====================================================================
# MODEL PERSISTENCE HOOKS (for future advanced forecasting models)
# =====================================================================

def save_model(model: Any, path: str) -> None:
    """
    Persist a trained forecasting model (e.g. ARIMA, Prophet, LSTM) to
    disk under backend/ai/models/. Placeholder for future extensibility —
    current implementation uses stateless statistical forecasting and
    does not require a persisted model.
    """
    if joblib is None:
        raise RuntimeError("joblib is required to save models but is not installed.")
    joblib.dump(model, path)
    logger.info("Model saved to %s", path)


def load_model(path: str) -> Any:
    """Load a previously persisted forecasting model."""
    if joblib is None:
        raise RuntimeError("joblib is required to load models but is not installed.")
    model = joblib.load(path)
    logger.info("Model loaded from %s", path)
    return model


# =====================================================================
# PUBLIC API
# =====================================================================

__all__ = [
    "PredictionConfig",
    "DEFAULT_CONFIG",
    "MonitoringSnapshot",
    "Prediction",
    "PredictedEventType",
    "RiskLevel",
    "Severity",
    "load_monitoring_history",
    "prepare_prediction_features",
    "forecast_metrics",
    "calculate_prediction_confidence",
    "assign_risk_level",
    "generate_prediction_explanation",
    "generate_recommendation",
    "predict_future_events",
    "export_predictions",
    "save_model",
    "load_model",
]