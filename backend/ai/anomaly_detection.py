"""
anomaly_detection.py

Unsupervised AI Anomaly Detection Engine — Lavender Trinetra Platform
=====================================================================

Uses Scikit-learn's IsolationForest to detect anomalous system behavior
across CPU, RAM, Disk, Network, and process-level activity, trained on
historical monitoring data and applied to real-time snapshots.

Integrates with:
    - monitoring/collector.py   (historical + real-time metrics source)
    - ai/ai_engine.py           (orchestration entry point)
    - ai/predictive_alerts.py   (consumes active anomalies)
    - ai/root_cause.py          (consumes anomaly evidence)
    - main.py                  (auto-executes on monitoring startup)

Author: Lavender Trinetra AI Engineering
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("lavender_trinetra.ai.anomaly_detection")
logger.addHandler(logging.NullHandler())


# =====================================================================
# ENUMS
# =====================================================================

class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class AnomalyDetectionConfig:
    """Tunable parameters for the anomaly detection engine."""

    features: list[str] = field(default_factory=lambda: [
        "cpu_usage",
        "ram_usage",
        "disk_usage",
        "disk_read_bps",
        "disk_write_bps",
        "network_in_bps",
        "network_out_bps",
    ])

    n_estimators: int = 200
    contamination: float = 0.05
    random_state: int = 42
    max_samples: str | int = "auto"

    min_training_samples: int = 30

    # Anomaly score thresholds (IsolationForest decision_function output,
    # negative = more anomalous). Used to derive severity buckets.
    severity_thresholds: dict[str, float] = field(default_factory=lambda: {
        "critical": -0.20,
        "high": -0.10,
        "medium": -0.02,
    })

    model_dir: str = os.path.join("backend", "data", "models")
    model_filename: str = "anomaly_isolation_forest.joblib"
    scaler_filename: str = "anomaly_scaler.joblib"


DEFAULT_CONFIG = AnomalyDetectionConfig()


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class ProcessSample:
    """Per-process metric sample used for process-level anomaly context."""

    name: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0


@dataclass
class MonitoringSample:
    """A single real-time monitoring snapshot to be scored."""

    timestamp: datetime
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    network_in_bps: float = 0.0
    network_out_bps: float = 0.0
    processes: list[ProcessSample] = field(default_factory=list)


@dataclass
class AnomalyResult:
    """Structured anomaly detection result for a single sample."""

    anomaly_id: str
    timestamp: datetime
    is_anomaly: bool
    anomaly_score: float
    confidence: float
    severity: str
    affected_metrics: list[str]
    top_process: Optional[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# =====================================================================
# ANOMALY DETECTION ENGINE
# =====================================================================

class AnomalyDetectionEngine:
    """
    Wraps an IsolationForest model + StandardScaler for training,
    persistence, and real-time scoring of monitoring data.
    """

    def __init__(self, config: AnomalyDetectionConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self._is_trained: bool = False

    @property
    def is_trained(self) -> bool:
        """Whether the engine currently holds a trained (or loaded) model."""
        return self._is_trained

    # -----------------------------------------------------------------
    # TRAINING
    # -----------------------------------------------------------------

    def train(self, history: pd.DataFrame) -> None:
        """
        Train the IsolationForest model on historical monitoring data.

        Args:
            history: DataFrame containing at minimum the columns listed
                in config.features.

        Raises:
            ValueError: if insufficient or malformed training data.
        """
        try:
            missing = [f for f in self.config.features if f not in history.columns]
            if missing:
                raise ValueError(f"Missing required feature columns for training: {missing}")

            data = history[self.config.features].dropna()

            if len(data) < self.config.min_training_samples:
                raise ValueError(
                    f"Insufficient training samples: got {len(data)}, "
                    f"require at least {self.config.min_training_samples}"
                )

            self.scaler = StandardScaler()
            scaled = self.scaler.fit_transform(data.values)

            self.model = IsolationForest(
                n_estimators=self.config.n_estimators,
                contamination=self.config.contamination,
                max_samples=self.config.max_samples,
                random_state=self.config.random_state,
            )
            self.model.fit(scaled)
            self._is_trained = True

            logger.info(
                "AnomalyDetectionEngine trained on %d samples across %d features",
                len(data), len(self.config.features),
            )

        except ValueError as exc:
            if "Insufficient training samples" in str(exc) or "Missing required feature columns" in str(exc):
                # Expected during the warm-up period before enough monitoring
                # history has accumulated, or if the caller passed a malformed
                # frame - not a bug, so don't log it as one with a full
                # traceback. main.py retries training on every cycle until
                # enough samples exist.
                logger.info("Anomaly detection training deferred: %s", exc)
            else:
                logger.exception("Anomaly detection training failed: %s", exc)
            raise
        except Exception as exc:
            logger.exception("Anomaly detection training failed: %s", exc)
            raise

    # -----------------------------------------------------------------
    # PERSISTENCE
    # -----------------------------------------------------------------

    def save(self, model_dir: Optional[str] = None) -> None:
        """Persist the trained model and scaler to disk via joblib."""
        if joblib is None:
            raise RuntimeError("joblib is required to save models but is not installed.")
        if not self._is_trained or self.model is None or self.scaler is None:
            raise RuntimeError("Cannot save an untrained model.")

        target_dir = model_dir or self.config.model_dir
        os.makedirs(target_dir, exist_ok=True)

        model_path = os.path.join(target_dir, self.config.model_filename)
        scaler_path = os.path.join(target_dir, self.config.scaler_filename)

        joblib.dump(self.model, model_path)
        joblib.dump(self.scaler, scaler_path)

        logger.info("Anomaly model saved to %s", model_path)
        logger.info("Anomaly scaler saved to %s", scaler_path)

    def load(self, model_dir: Optional[str] = None) -> bool:
        """
        Load a previously persisted model and scaler from disk.

        Returns:
            True if both artifacts were successfully loaded, False if
            either is missing (caller should train instead).
        """
        if joblib is None:
            raise RuntimeError("joblib is required to load models but is not installed.")

        target_dir = model_dir or self.config.model_dir
        model_path = os.path.join(target_dir, self.config.model_filename)
        scaler_path = os.path.join(target_dir, self.config.scaler_filename)

        if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
            logger.warning("No persisted anomaly model found at %s", target_dir)
            return False

        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            self._is_trained = True
            logger.info("Anomaly model and scaler loaded from %s", target_dir)
            return True
        except Exception as exc:
            logger.exception("Failed to load persisted anomaly model: %s", exc)
            return False

    # -----------------------------------------------------------------
    # SCORING
    # -----------------------------------------------------------------

    def _extract_feature_vector(self, sample: MonitoringSample) -> np.ndarray:
        """Convert a MonitoringSample into an ordered feature vector."""
        values = {
            "cpu_usage": sample.cpu_usage,
            "ram_usage": sample.ram_usage,
            "disk_usage": sample.disk_usage,
            "disk_read_bps": sample.disk_read_bps,
            "disk_write_bps": sample.disk_write_bps,
            "network_in_bps": sample.network_in_bps,
            "network_out_bps": sample.network_out_bps,
        }
        return np.array([[values[f] for f in self.config.features]], dtype=float)

    def _score_to_severity(self, score: float) -> Severity:
        """Map a raw IsolationForest decision_function score to a severity bucket."""
        thresholds = self.config.severity_thresholds
        if score <= thresholds["critical"]:
            return Severity.CRITICAL
        if score <= thresholds["high"]:
            return Severity.HIGH
        if score <= thresholds["medium"]:
            return Severity.MEDIUM
        return Severity.LOW

    def _identify_affected_metrics(
        self,
        sample: MonitoringSample,
        history_stats: Optional[dict[str, dict[str, float]]] = None,
    ) -> list[str]:
        """
        Identify which metrics most likely drove the anomaly by comparing
        the sample against historical mean/std (z-score based), when
        historical statistics are available. Falls back to threshold-based
        heuristics otherwise.
        """
        affected: list[str] = []
        sample_values = {
            "cpu_usage": sample.cpu_usage,
            "ram_usage": sample.ram_usage,
            "disk_usage": sample.disk_usage,
            "disk_read_bps": sample.disk_read_bps,
            "disk_write_bps": sample.disk_write_bps,
            "network_in_bps": sample.network_in_bps,
            "network_out_bps": sample.network_out_bps,
        }

        if history_stats:
            for metric, value in sample_values.items():
                stats = history_stats.get(metric)
                if not stats or stats.get("std", 0) == 0:
                    continue
                z = abs((value - stats["mean"]) / stats["std"])
                if z >= 2.0:
                    affected.append(metric)
        else:
            heuristic_thresholds = {
                "cpu_usage": 85.0,
                "ram_usage": 85.0,
                "disk_usage": 90.0,
            }
            for metric, threshold in heuristic_thresholds.items():
                if sample_values.get(metric, 0) >= threshold:
                    affected.append(metric)

        return affected or ["overall_system_behavior"]

    def _top_process(self, sample: MonitoringSample) -> Optional[str]:
        """Identify the highest resource-consuming process in the sample."""
        if not sample.processes:
            return None
        top = max(sample.processes, key=lambda p: (p.cpu_percent + p.memory_percent))
        return top.name

    def compute_history_stats(self, history: pd.DataFrame) -> dict[str, dict[str, float]]:
        """Precompute mean/std per feature from historical data for z-score attribution."""
        stats: dict[str, dict[str, float]] = {}
        for feature in self.config.features:
            if feature in history.columns:
                col = history[feature].dropna()
                stats[feature] = {
                    "mean": float(col.mean()) if not col.empty else 0.0,
                    "std": float(col.std()) if not col.empty else 0.0,
                }
        return stats

    def detect(
        self,
        sample: MonitoringSample,
        history_stats: Optional[dict[str, dict[str, float]]] = None,
    ) -> AnomalyResult:
        """
        Score a single real-time monitoring sample against the trained
        model and return a structured AnomalyResult.

        Raises:
            RuntimeError: if the model has not been trained/loaded.
        """
        if not self._is_trained or self.model is None or self.scaler is None:
            raise RuntimeError("AnomalyDetectionEngine is not trained. Call train() or load() first.")

        try:
            vector = self._extract_feature_vector(sample)
            scaled_vector = self.scaler.transform(vector)

            prediction = self.model.predict(scaled_vector)[0]  # 1 = normal, -1 = anomaly
            raw_score = float(self.model.decision_function(scaled_vector)[0])

            is_anomaly = bool(prediction == -1)
            severity = self._score_to_severity(raw_score)

            # Confidence derived from distance from the decision boundary,
            # normalized into a 0-1 range.
            confidence = float(max(0.05, min(0.99, 1.0 - (raw_score + 0.5))))

            affected_metrics = self._identify_affected_metrics(sample, history_stats)
            top_process = self._top_process(sample)

            result = AnomalyResult(
                anomaly_id=str(uuid.uuid4()),
                timestamp=sample.timestamp,
                is_anomaly=is_anomaly,
                anomaly_score=round(raw_score, 4),
                confidence=round(confidence, 3),
                severity=severity.value,
                affected_metrics=affected_metrics,
                top_process=top_process,
                evidence={
                    "cpu_usage": sample.cpu_usage,
                    "ram_usage": sample.ram_usage,
                    "disk_usage": sample.disk_usage,
                    "network_in_bps": sample.network_in_bps,
                    "network_out_bps": sample.network_out_bps,
                },
            )

            if is_anomaly:
                logger.warning(
                    "Anomaly detected [%s] severity=%s score=%.4f metrics=%s",
                    result.anomaly_id, result.severity, result.anomaly_score, affected_metrics,
                )

            return result

        except Exception as exc:
            logger.exception("Anomaly detection scoring failed: %s", exc)
            raise

    def detect_batch(
        self,
        samples: list[MonitoringSample],
        history_stats: Optional[dict[str, dict[str, float]]] = None,
    ) -> list[AnomalyResult]:
        """Score a batch of monitoring samples, skipping any that fail individually."""
        results: list[AnomalyResult] = []
        for sample in samples:
            try:
                results.append(self.detect(sample, history_stats))
            except Exception as exc:
                logger.error("Skipping sample at %s due to error: %s", sample.timestamp, exc)
        return results


# =====================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =====================================================================

_default_engine: Optional[AnomalyDetectionEngine] = None


def get_default_engine(config: AnomalyDetectionConfig = DEFAULT_CONFIG) -> AnomalyDetectionEngine:
    """
    Return a process-wide singleton AnomalyDetectionEngine, attempting to
    load a persisted model first and falling back to an untrained engine
    (caller must train() before use if load fails).
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = AnomalyDetectionEngine(config)
        _default_engine.load()
    return _default_engine


def train_from_history(
    history: pd.DataFrame,
    config: AnomalyDetectionConfig = DEFAULT_CONFIG,
    persist: bool = True,
) -> AnomalyDetectionEngine:
    """
    Convenience function to train a new engine from historical monitoring
    data (e.g. loaded from backend/data/system_metrics.csv) and optionally
    persist it to disk.
    """
    engine = AnomalyDetectionEngine(config)
    engine.train(history)
    if persist:
        engine.save()
    global _default_engine
    _default_engine = engine
    return engine


def detect_anomaly(
    sample: MonitoringSample,
    history: Optional[pd.DataFrame] = None,
    config: AnomalyDetectionConfig = DEFAULT_CONFIG,
) -> AnomalyResult:
    """
    High-level entry point used by ai_engine.py and main.py: scores a
    single real-time sample using the default (auto-loaded) engine.

    Args:
        sample: Real-time MonitoringSample to evaluate.
        history: Optional historical DataFrame used to compute z-score
            based affected-metric attribution. If omitted, heuristic
            thresholds are used instead.
        config: AnomalyDetectionConfig instance.

    Raises:
        RuntimeError: if no trained/persisted model is available.
    """
    engine = get_default_engine(config)
    if not engine.is_trained:
        raise RuntimeError(
            "No trained anomaly detection model available. "
            "Call train_from_history() during startup before detecting anomalies."
        )

    history_stats = engine.compute_history_stats(history) if history is not None else None
    return engine.detect(sample, history_stats)


def run_on_monitoring_start(
    history: pd.DataFrame,
    config: AnomalyDetectionConfig = DEFAULT_CONFIG,
) -> AnomalyDetectionEngine:
    """
    Entry point invoked automatically by main.py when monitoring starts.
    Attempts to load a persisted model; if unavailable, trains a new one
    from the supplied historical data and persists it.
    """
    engine = AnomalyDetectionEngine(config)
    if not engine.load():
        logger.info("No persisted anomaly model found — training a new one from history.")
        engine.train(history)
        engine.save()

    global _default_engine
    _default_engine = engine
    return engine


# =====================================================================
# EXPORT
# =====================================================================

def export_results(results: list[AnomalyResult], fmt: str = "dict") -> Any:
    """Export a list of AnomalyResult objects as dict, DataFrame, or JSON."""
    records = [r.to_dict() for r in results]

    if fmt == "dict":
        return records
    if fmt == "dataframe":
        return pd.DataFrame(records)
    if fmt == "json":
        import json
        return json.dumps(records, default=str, indent=2)

    raise ValueError(f"Unsupported export format: {fmt}")


__all__ = [
    "AnomalyDetectionConfig",
    "DEFAULT_CONFIG",
    "ProcessSample",
    "MonitoringSample",
    "AnomalyResult",
    "Severity",
    "AnomalyDetectionEngine",
    "get_default_engine",
    "train_from_history",
    "detect_anomaly",
    "run_on_monitoring_start",
    "export_results",
]