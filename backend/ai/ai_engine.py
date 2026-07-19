"""
ai_engine.py

Central AI Orchestrator — Lavender Trinetra Platform
=====================================================================

Coordinates all AI subsystems — anomaly detection, health scoring,
root cause analysis, trend analysis, predictive alerts, and
recommendations — into a single, unified execution pipeline driven by
real-time and historical data from monitoring/collector.py.

Exposes a small set of reusable, well-typed functions consumed by:
    - main.py       (starts monitoring and drives the AI cycle)
    - api/routes.py (dashboard-facing REST endpoints)
    - dashboard.py  (direct in-process consumption, if applicable)

Author: Lavender Trinetra AI Engineering
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

import pandas as pd

try:
    from . import anomaly_detection
    from . import health_score
    from . import root_cause
    from . import recommendations
    from . import trend_analysis
    from . import predictive_alerts
except ImportError:  # pragma: no cover - fallback for non-package execution
    import anomaly_detection      # type: ignore
    import health_score           # type: ignore
    import root_cause             # type: ignore
    import recommendations        # type: ignore
    import trend_analysis         # type: ignore
    import predictive_alerts      # type: ignore

logger = logging.getLogger("lavender_trinetra.ai.ai_engine")
logger.addHandler(logging.NullHandler())


# =====================================================================
# CONFIGURATION
# =====================================================================

@dataclass
class AIEngineConfig:
    """Top-level configuration controlling which subsystems run each cycle."""

    enable_anomaly_detection: bool = True
    enable_health_score: bool = True
    enable_root_cause: bool = True
    enable_trend_analysis: bool = True
    enable_predictive_alerts: bool = True
    enable_recommendations: bool = True

    # Trend analysis is comparatively expensive; run it every N cycles
    # rather than on every monitoring tick.
    trend_analysis_every_n_cycles: int = 5

    anomaly_config: anomaly_detection.AnomalyDetectionConfig = field(
        default_factory=anomaly_detection.AnomalyDetectionConfig
    )
    health_config: health_score.HealthScoreConfig = field(
        default_factory=health_score.HealthScoreConfig
    )
    root_cause_config: root_cause.RootCauseConfig = field(
        default_factory=root_cause.RootCauseConfig
    )
    trend_config: trend_analysis.TrendAnalysisConfig = field(
        default_factory=trend_analysis.TrendAnalysisConfig
    )
    prediction_config: predictive_alerts.PredictionConfig = field(
        default_factory=predictive_alerts.PredictionConfig
    )
    recommendation_config: recommendations.RecommendationConfig = field(
        default_factory=recommendations.RecommendationConfig
    )


DEFAULT_CONFIG = AIEngineConfig()


# =====================================================================
# INPUT DATA STRUCTURES
# =====================================================================

@dataclass
class ProcessMetric:
    """Normalized per-process metric supplied by monitoring/collector.py."""

    name: str
    pid: Optional[int] = None
    cpu_percent: float = 0.0
    memory_percent: float = 0.0


@dataclass
class MonitoringTick:
    """A single real-time monitoring reading passed in from collector.py."""

    timestamp: datetime
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    network_in_bps: float = 0.0
    network_out_bps: float = 0.0
    processes: list[ProcessMetric] = field(default_factory=list)


# =====================================================================
# UNIFIED OUTPUT
# =====================================================================

@dataclass
class AIEngineResult:
    """Unified result bundle returned to main.py / api / dashboard.py."""

    timestamp: datetime
    health_score: Optional[dict[str, Any]] = None
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    root_causes: list[dict[str, Any]] = field(default_factory=list)
    trends: list[dict[str, Any]] = field(default_factory=list)
    resource_growth: list[dict[str, Any]] = field(default_factory=list)
    process_memory_leaks: list[dict[str, Any]] = field(default_factory=list)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# =====================================================================
# AI ENGINE
# =====================================================================

class AIEngine:
    """
    Central orchestrator that wires together every AI subsystem into a
    single, unified execution pipeline. Maintains lightweight internal
    state (cycle counter, trained anomaly model, rolling history) across
    calls to run_cycle().
    """

    def __init__(self, config: AIEngineConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self._anomaly_engine: Optional[anomaly_detection.AnomalyDetectionEngine] = None
        self._cycle_count: int = 0
        self._is_initialized: bool = False

    # -----------------------------------------------------------------
    # INITIALIZATION
    # -----------------------------------------------------------------

    def initialize(self, history: pd.DataFrame) -> None:
        """
        Initialize AI subsystems that require historical data up front —
        primarily training (or loading) the anomaly detection model.
        Should be called once when monitoring starts (from main.py).

        Args:
            history: Historical monitoring DataFrame (e.g. loaded from
                backend/data/system_metrics.csv via collector.py).
        """
        try:
            if self.config.enable_anomaly_detection:
                self._anomaly_engine = anomaly_detection.run_on_monitoring_start(
                    history, self.config.anomaly_config
                )
            self._is_initialized = True
            logger.info("AIEngine initialized successfully.")
        except ValueError as exc:
            if "Insufficient training samples" in str(exc):
                # Expected during warm-up before enough monitoring history
                # exists - main.py's lazy-init retries each cycle until
                # there's enough data, so this isn't a failure worth an
                # ERROR-level stack trace.
                logger.info("AIEngine initialization deferred: %s", exc)
            else:
                logger.exception("AIEngine initialization failed: %s", exc)
            self._is_initialized = False
            raise
        except Exception as exc:
            logger.exception("AIEngine initialization failed: %s", exc)
            self._is_initialized = False
            raise

    # -----------------------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------------------

    def _run_anomaly_detection(
        self,
        tick: MonitoringTick,
        history: pd.DataFrame,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Run anomaly detection for the current tick; returns list of anomaly dicts."""
        if not self.config.enable_anomaly_detection or self._anomaly_engine is None:
            return []
        try:
            sample = anomaly_detection.MonitoringSample(
                timestamp=tick.timestamp,
                cpu_usage=tick.cpu_usage,
                ram_usage=tick.ram_usage,
                disk_usage=tick.disk_usage,
                disk_read_bps=tick.disk_read_bps,
                disk_write_bps=tick.disk_write_bps,
                network_in_bps=tick.network_in_bps,
                network_out_bps=tick.network_out_bps,
                processes=[
                    anomaly_detection.ProcessSample(
                        name=p.name, cpu_percent=p.cpu_percent, memory_percent=p.memory_percent
                    )
                    for p in tick.processes
                ],
            )
            history_stats = self._anomaly_engine.compute_history_stats(history) if not history.empty else None
            result = self._anomaly_engine.detect(sample, history_stats)
            return [result.to_dict()] if result.is_anomaly else []
        except Exception as exc:
            msg = f"anomaly_detection failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            return []

    def _run_health_score(
        self,
        tick: MonitoringTick,
        active_anomalies: list[dict[str, Any]],
        errors: list[str],
    ) -> Optional[dict[str, Any]]:
        """Run health score calculation; returns result dict or None on failure."""
        if not self.config.enable_health_score:
            return None
        try:
            result = health_score.run_health_score_check(
                cpu_usage=tick.cpu_usage,
                ram_usage=tick.ram_usage,
                disk_usage=tick.disk_usage,
                network_in_bps=tick.network_in_bps,
                network_out_bps=tick.network_out_bps,
                active_anomalies=active_anomalies,
                timestamp=tick.timestamp,
                config=self.config.health_config,
            )
            return result.to_dict()
        except Exception as exc:
            msg = f"health_score failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            return None

    def _run_root_cause(
        self,
        tick: MonitoringTick,
        active_anomalies: list[dict[str, Any]],
        current_health_score: Optional[float],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Run root cause analysis for each active anomaly."""
        if not self.config.enable_root_cause or not active_anomalies:
            return []
        results: list[dict[str, Any]] = []
        for anomaly in active_anomalies:
            try:
                result = root_cause.run_root_cause_analysis(
                    anomaly_id=anomaly.get("anomaly_id", ""),
                    affected_metrics=anomaly.get("affected_metrics", []),
                    anomaly_score=anomaly.get("anomaly_score", 0.0),
                    cpu_usage=tick.cpu_usage,
                    ram_usage=tick.ram_usage,
                    disk_usage=tick.disk_usage,
                    disk_read_bps=tick.disk_read_bps,
                    disk_write_bps=tick.disk_write_bps,
                    network_in_bps=tick.network_in_bps,
                    network_out_bps=tick.network_out_bps,
                    processes=[
                        {"name": p.name, "pid": p.pid, "cpu_percent": p.cpu_percent,
                         "memory_percent": p.memory_percent}
                        for p in tick.processes
                    ],
                    current_health_score=current_health_score,
                    timestamp=tick.timestamp,
                    config=self.config.root_cause_config,
                )
                results.append(result.to_dict())
            except Exception as exc:
                msg = f"root_cause failed for anomaly {anomaly.get('anomaly_id')}: {exc}"
                logger.error(msg)
                errors.append(msg)
        return results

    def _run_trend_analysis(
        self,
        history: pd.DataFrame,
        process_history: Optional[list[dict[str, Any]]],
        errors: list[str],
    ) -> dict[str, Any]:
        """Run trend analysis over historical data."""
        if not self.config.enable_trend_analysis or history.empty:
            return {"trends": [], "resource_growth": [], "process_memory_leaks": []}
        try:
            output = trend_analysis.run_trend_analysis(
                history=history,
                process_samples=process_history,
                config=self.config.trend_config,
            )
            return {
                "trends": [t.to_dict() for t in output["trends"]],
                "resource_growth": [t.to_dict() for t in output["resource_growth"]],
                "process_memory_leaks": [leak.to_dict() for leak in output["process_memory_leaks"]],
            }
        except Exception as exc:
            msg = f"trend_analysis failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            return {"trends": [], "resource_growth": [], "process_memory_leaks": []}

    def _run_predictive_alerts(
        self,
        tick: MonitoringTick,
        history: pd.DataFrame,
        active_anomalies: list[dict[str, Any]],
        current_health_score: Optional[float],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Run predictive alert forecasting."""
        if not self.config.enable_predictive_alerts:
            return []
        try:
            snapshot = predictive_alerts.MonitoringSnapshot(
                timestamp=tick.timestamp,
                cpu_usage=tick.cpu_usage,
                ram_usage=tick.ram_usage,
                disk_usage=tick.disk_usage,
                disk_read_bps=tick.disk_read_bps,
                disk_write_bps=tick.disk_write_bps,
                network_in_bps=tick.network_in_bps,
                network_out_bps=tick.network_out_bps,
                top_processes=[
                    {"name": p.name, "cpu_percent": p.cpu_percent, "memory_percent": p.memory_percent}
                    for p in tick.processes
                ],
                current_health_score=current_health_score,
                active_anomalies=active_anomalies,
            )
            results = predictive_alerts.predict_future_events(
                history=history, snapshot=snapshot, config=self.config.prediction_config
            )
            return [p.to_dict() for p in results]
        except Exception as exc:
            msg = f"predictive_alerts failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            return []

    def _run_recommendations(
        self,
        tick: MonitoringTick,
        health_result: Optional[dict[str, Any]],
        active_anomalies: list[dict[str, Any]],
        root_causes: list[dict[str, Any]],
        trends: list[dict[str, Any]],
        predictions: list[dict[str, Any]],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Run the recommendation engine over all collected AI signals."""
        if not self.config.enable_recommendations:
            return []
        try:
            results = recommendations.run_recommendation_engine(
                health_score=health_result.get("score") if health_result else None,
                health_status=health_result.get("status") if health_result else None,
                health_contributing_factors=health_result.get("contributing_factors", []) if health_result else [],
                active_anomalies=active_anomalies,
                root_cause_results=root_causes,
                trends=trends,
                predictions=predictions,
                timestamp=tick.timestamp,
                config=self.config.recommendation_config,
            )
            return [r.to_dict() for r in results]
        except Exception as exc:
            msg = f"recommendations failed: {exc}"
            logger.error(msg)
            errors.append(msg)
            return []

    # -----------------------------------------------------------------
    # MAIN EXECUTION CYCLE
    # -----------------------------------------------------------------

    def run_cycle(
        self,
        tick: MonitoringTick,
        history: pd.DataFrame,
        process_history: Optional[list[dict[str, Any]]] = None,
    ) -> AIEngineResult:
        """
        Execute one full AI orchestration cycle for a single monitoring
        tick, coordinating all enabled subsystems in dependency order:

            anomaly_detection -> health_score -> root_cause
                -> trend_analysis -> predictive_alerts -> recommendations

        Args:
            tick: The current real-time MonitoringTick from collector.py.
            history: Historical monitoring DataFrame accumulated so far.
            process_history: Optional list of per-process memory samples
                (dicts with timestamp, name, memory_percent) used for
                leak detection in trend_analysis.

        Returns:
            A unified AIEngineResult bundling every subsystem's output.
        """
        errors: list[str] = []

        if not self._is_initialized:
            logger.warning("AIEngine.run_cycle() called before initialize(); attempting lazy init.")
            try:
                self.initialize(history)
            except Exception as exc:
                errors.append(f"lazy initialization failed: {exc}")

        active_anomalies = self._run_anomaly_detection(tick, history, errors)

        health_result = self._run_health_score(tick, active_anomalies, errors)
        current_health_score = health_result.get("score") if health_result else None

        root_causes = self._run_root_cause(tick, active_anomalies, current_health_score, errors)

        trend_output = {"trends": [], "resource_growth": [], "process_memory_leaks": []}
        self._cycle_count += 1
        if self._cycle_count % max(1, self.config.trend_analysis_every_n_cycles) == 0:
            trend_output = self._run_trend_analysis(history, process_history, errors)

        predictions = self._run_predictive_alerts(
            tick, history, active_anomalies, current_health_score, errors
        )

        recs = self._run_recommendations(
            tick, health_result, active_anomalies, root_causes,
            trend_output["trends"], predictions, errors,
        )

        result = AIEngineResult(
            timestamp=tick.timestamp,
            health_score=health_result,
            anomalies=active_anomalies,
            root_causes=root_causes,
            trends=trend_output["trends"],
            resource_growth=trend_output["resource_growth"],
            process_memory_leaks=trend_output["process_memory_leaks"],
            predictions=predictions,
            recommendations=recs,
            errors=errors,
        )

        if errors:
            logger.warning("AI cycle completed with %d error(s) at %s", len(errors), tick.timestamp)
        else:
            logger.info(
                "AI cycle completed at %s: health=%s anomalies=%d recommendations=%d",
                tick.timestamp,
                health_result.get("status") if health_result else "n/a",
                len(active_anomalies),
                len(recs),
            )

        return result


# =====================================================================
# MODULE-LEVEL SINGLETON + CONVENIENCE FUNCTIONS
# (used by main.py, api/routes.py, dashboard.py)
# =====================================================================

_default_engine: Optional[AIEngine] = None


def get_engine(config: AIEngineConfig = DEFAULT_CONFIG) -> AIEngine:
    """Return the process-wide singleton AIEngine, creating it if necessary."""
    global _default_engine
    if _default_engine is None:
        _default_engine = AIEngine(config)
    return _default_engine


def initialize_ai_engine(history: pd.DataFrame, config: AIEngineConfig = DEFAULT_CONFIG) -> AIEngine:
    """
    Entry point called from main.py when monitoring starts. Initializes
    the singleton AIEngine (training/loading the anomaly model, etc.).
    """
    engine = get_engine(config)
    engine.initialize(history)
    return engine


def run_ai_cycle(
    timestamp: datetime,
    cpu_usage: float,
    ram_usage: float,
    disk_usage: float,
    history: pd.DataFrame,
    disk_read_bps: float = 0.0,
    disk_write_bps: float = 0.0,
    network_in_bps: float = 0.0,
    network_out_bps: float = 0.0,
    processes: Optional[list[dict[str, Any]]] = None,
    process_history: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    High-level convenience entry point for main.py's monitoring loop and
    for api/routes.py: builds a MonitoringTick from raw values, runs a
    full AI cycle via the singleton engine, and returns a plain dict
    ready for JSON serialization / dashboard consumption.
    """
    engine = get_engine()

    tick = MonitoringTick(
        timestamp=timestamp,
        cpu_usage=cpu_usage,
        ram_usage=ram_usage,
        disk_usage=disk_usage,
        disk_read_bps=disk_read_bps,
        disk_write_bps=disk_write_bps,
        network_in_bps=network_in_bps,
        network_out_bps=network_out_bps,
        processes=[
            ProcessMetric(
                name=p.get("name", "unknown"),
                pid=p.get("pid"),
                cpu_percent=p.get("cpu_percent", 0.0),
                memory_percent=p.get("memory_percent", 0.0),
            )
            for p in (processes or [])
        ],
    )

    result = engine.run_cycle(tick, history, process_history)
    return result.to_dict()


def get_latest_result_dict(result: AIEngineResult) -> dict[str, Any]:
    """Utility for api/routes.py / dashboard.py to serialize an AIEngineResult."""
    return result.to_dict()


__all__ = [
    "AIEngineConfig",
    "DEFAULT_CONFIG",
    "ProcessMetric",
    "MonitoringTick",
    "AIEngineResult",
    "AIEngine",
    "get_engine",
    "initialize_ai_engine",
    "run_ai_cycle",
    "get_latest_result_dict",
]