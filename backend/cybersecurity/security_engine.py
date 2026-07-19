from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger, safe_execute

from backend.cybersecurity import (
    process_monitor,
    network_monitor,
    port_monitor,
    firewall_monitor,
    session_monitor,
    system_integrity,
    security_logger,
)

logger = get_logger("lavender_trinetra.cybersecurity.security_engine")

SCAN_INTERVAL_SECONDS = float(getattr(settings, "SCAN_INTERVAL_SECONDS", 60.0))


class SecurityStatus:
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class SecurityEngine:
    """
    Central orchestrator for the cybersecurity layer. Initializes and
    coordinates process_monitor, network_monitor, port_monitor,
    firewall_monitor, session_monitor and system_integrity, and routes
    everything they observe through security_logger for persistence and
    downstream API/FastAPI exposure.

    Mirrors the lifecycle shape of backend.ai.ai_engine and the
    monitoring loop in main.py's Orchestrator, so main.py can drive it
    the same way it drives the rest of the backend.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status: str = SecurityStatus.UNKNOWN
        self._last_cycle_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._cycle_count: int = 0
        self._component_status: dict[str, str] = {
            "process_monitor": SecurityStatus.UNKNOWN,
            "network_monitor": SecurityStatus.UNKNOWN,
            "port_monitor": SecurityStatus.UNKNOWN,
            "firewall_monitor": SecurityStatus.UNKNOWN,
            "session_monitor": SecurityStatus.UNKNOWN,
            "system_integrity": SecurityStatus.UNKNOWN,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Security engine already running; ignoring duplicate start().")
                return

            with safe_execute("security-logger-init"):
                security_logger.initialize()

            self._stop_event.clear()
            self._status = SecurityStatus.OPERATIONAL
            self._thread = threading.Thread(
                target=self._run_loop, name="security-engine-loop", daemon=True
            )
            self._thread.start()
            logger.info("Security engine started (scan interval=%ss).", SCAN_INTERVAL_SECONDS)

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=10)

        with safe_execute("security-logger-finalize"):
            security_logger.finalize()

        with self._lock:
            self._status = SecurityStatus.STOPPED
            self._thread = None
        logger.info("Security engine stopped.")

    # ------------------------------------------------------------------
    # Monitoring loop
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        logger.info("Security monitoring loop started.")
        while not self._stop_event.is_set():
            with safe_execute("security-cycle"):
                self.run_cycle()
            self._stop_event.wait(SCAN_INTERVAL_SECONDS)
        logger.info("Security monitoring loop terminated.")

    def run_cycle(
        self,
        metrics_row: Optional[dict[str, Any]] = None,
        process_rows: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Runs a single security observation cycle across all submodules
        and forwards everything collected to security_logger. Can be
        called directly by main.py's monitoring loop (passing the same
        metrics_row/process_rows already collected for the AI cycle) or
        left to run on its own timer via start()/stop().
        """
        timestamp = datetime.utcnow()
        cycle_result: dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "processes": [],
            "network_connections": [],
            "open_ports": [],
            "firewall_events": [],
            "sessions": [],
            "integrity_events": [],
            "errors": [],
        }

        with safe_execute("process-monitor-cycle"):
            cycle_result["processes"] = process_monitor.scan(process_rows)
            self._component_status["process_monitor"] = SecurityStatus.OPERATIONAL

        with safe_execute("network-monitor-cycle"):
            cycle_result["network_connections"] = network_monitor.scan()
            self._component_status["network_monitor"] = SecurityStatus.OPERATIONAL

        with safe_execute("port-monitor-cycle"):
            cycle_result["open_ports"] = port_monitor.scan()
            self._component_status["port_monitor"] = SecurityStatus.OPERATIONAL

        with safe_execute("firewall-monitor-cycle"):
            cycle_result["firewall_events"] = firewall_monitor.scan()
            self._component_status["firewall_monitor"] = SecurityStatus.OPERATIONAL

        with safe_execute("session-monitor-cycle"):
            cycle_result["sessions"] = session_monitor.scan()
            self._component_status["session_monitor"] = SecurityStatus.OPERATIONAL

        with safe_execute("system-integrity-cycle"):
            cycle_result["integrity_events"] = system_integrity.scan()
            self._component_status["system_integrity"] = SecurityStatus.OPERATIONAL

        with safe_execute("security-logger-record"):
            # security_logger owns persistence (database + anything the
            # FastAPI layer reads from) - security_engine only collects
            # and forwards, it does not touch storage directly.
            security_logger.record_cycle(cycle_result)

        self._cycle_count += 1
        self._last_cycle_at = timestamp
        return cycle_result

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "components": dict(self._component_status),
                "cycle_count": self._cycle_count,
                "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
                "last_error": self._last_error,
            }


# ---------------------------------------------------------------------
# Module-level singleton and entrypoints for main.py
# ---------------------------------------------------------------------
_engine: Optional[SecurityEngine] = None
_engine_lock = threading.Lock()


def _get_engine() -> SecurityEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SecurityEngine()
        return _engine


def start_security_monitoring() -> None:
    """Entry point for main.py to start the cybersecurity layer."""
    _get_engine().start()


def stop_security_monitoring() -> None:
    """Entry point for main.py to stop the cybersecurity layer."""
    _get_engine().stop()


def run_security_cycle(
    metrics_row: Optional[dict[str, Any]] = None,
    process_rows: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Entry point for main.py to drive a security cycle in lockstep with
    its own monitoring loop, instead of relying solely on the engine's
    independent timer thread.
    """
    return _get_engine().run_cycle(metrics_row, process_rows)


def get_security_status() -> dict[str, Any]:
    """Entry point for main.py / the FastAPI layer to read live status."""
    return _get_engine().get_status()