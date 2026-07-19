from __future__ import annotations

import asyncio
import signal
import sys
import threading
from datetime import datetime
from typing import Any, Optional

import uvicorn

from backend.config import settings
from backend.core import (
    get_logger,
    test_run_manager,
    application_status,
    StatusValue,
    startup_initialize,
    register_cleanup,
    safe_shutdown,
    safe_execute,
)
from backend.api.api import app as fastapi_app

from backend.monitoring import collector as monitoring_collector
from backend.monitoring import processes as monitoring_processes
from backend.monitoring import alerts as monitoring_alerts
from backend.monitoring import reports as monitoring_reports

from backend.ai import ai_engine as ai_engine_module
from backend.ai.predictive_alerts import load_monitoring_history

from backend.database import database as db_module
from backend.database import crud as db_crud

logger = get_logger("lavender_trinetra.main")

BANNER = """=========================================
\u222b Lavender Trinetra
Observe. Learn. Protect.
=========================================
Type "start" to begin monitoring.
Type "stop" to stop monitoring."""

METRICS_HEADERS = [
    "timestamp", "cpu_usage", "ram_usage", "disk_usage",
    "disk_read_bps", "disk_write_bps", "network_in_bps", "network_out_bps",
]
PROCESSES_HEADERS = ["timestamp", "pid", "name", "cpu_percent", "memory_percent"]
REPORT_HEADERS = ["timestamp", "run_id", "summary"]

MAX_HISTORY_ROWS = 500
MAX_PROCESS_HISTORY_ROWS = 500

COLLECTION_INTERVAL_SECONDS = settings.COLLECTION_INTERVAL_SECONDS
API_HOST = settings.API_HOST
API_PORT = settings.API_PORT


class CybersecurityEngineUnavailable(Exception):
    pass


def _load_cybersecurity_engine():
    """
    Loads the cybersecurity coordination entrypoint. Imported lazily and
    isolated behind a try/except so the orchestrator can still run
    monitoring, AI and the API even if the cybersecurity module is not
    yet present or fails to import.
    """
    try:
        from backend.cybersecurity import threat_detector

        return threat_detector
    except Exception as exc:
        logger.warning("Cybersecurity module unavailable: %s", exc)
        raise CybersecurityEngineUnavailable(str(exc))


class Orchestrator:
    """
    Sole backend orchestrator. Coordinates monitoring, AI, cybersecurity,
    database and API modules without implementing their internal logic.
    All shared utilities (logging, status, CSV, cleanup) are delegated to
    core.py; all configuration is sourced from config.py.
    """

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._monitoring_thread: Optional[threading.Thread] = None
        self._api_thread: Optional[threading.Thread] = None
        self._api_server: Optional[uvicorn.Server] = None

        self._run_id: Optional[int] = None
        self._session_start: Optional[datetime] = None
        self._alert_tracker = monitoring_alerts.get_session_tracker()
        self._ai_engine: Optional[ai_engine_module.AIEngine] = None
        self._cyber_module = None

        self._history_rows: list[dict[str, Any]] = []
        self._process_history_rows: list[dict[str, Any]] = []
        self._last_ai_result: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------------
    # API server lifecycle
    # ------------------------------------------------------------------
    def start_api_server(self) -> None:
        config = uvicorn.Config(
            fastapi_app,
            host=API_HOST,
            port=API_PORT,
            log_level=settings.LOG_LEVEL.lower(),
            loop="asyncio",
        )
        self._api_server = uvicorn.Server(config)

        def _run_server() -> None:
            with safe_execute("api-server"):
                self._api_server.run()

        self._api_thread = threading.Thread(target=_run_server, name="api-server", daemon=True)
        self._api_thread.start()
        application_status.set_api_status(StatusValue.OPERATIONAL)
        logger.info("API service started at http://%s:%s", API_HOST, API_PORT)
        register_cleanup(self.stop_api_server)

    def stop_api_server(self) -> None:
        if self._api_server is not None:
            self._api_server.should_exit = True
        if self._api_thread is not None:
            self._api_thread.join(timeout=5)
        application_status.set_api_status(StatusValue.STOPPED)
        logger.info("API service stopped.")

    # ------------------------------------------------------------------
    # Database lifecycle
    # ------------------------------------------------------------------
    def init_database(self) -> None:
        with safe_execute("database-init", reraise=False):
            db_module.init_db()
            run = db_crud.create_test_run()
            self._run_id = run.get("id") if isinstance(run, dict) else None
            test_run_manager.start_run(run_id=self._run_id)
            application_status.set_database_status(StatusValue.OPERATIONAL)
            logger.info("Database initialized. Run ID: %s", self._run_id)
            register_cleanup(self.finalize_database)
            return
        application_status.set_database_status(StatusValue.UNAVAILABLE)
        self._run_id = None

    def finalize_database(self) -> None:
        with safe_execute("database-finalize"):
            if self._run_id is not None:
                context = test_run_manager.end_run()
                alert_count = context.alert_count if context else 0
                db_crud.end_test_run(self._run_id, total_alerts=alert_count)
            logger.info("Database writes finalized.")

    # ------------------------------------------------------------------
    # AI / Cybersecurity initialization
    # ------------------------------------------------------------------
    def init_ai_engine(self) -> None:
        if not settings.AI_ENABLED:
            application_status.set_ai_status(StatusValue.STOPPED)
            logger.info("AI engine disabled via configuration.")
            return
        with safe_execute("ai-engine-init"):
            self._ai_engine = ai_engine_module.get_engine()
            application_status.set_ai_status(StatusValue.OPERATIONAL)
            logger.info("AI engine started.")
            return
        application_status.set_ai_status(StatusValue.UNAVAILABLE)
        self._ai_engine = None

    def init_cybersecurity_engine(self) -> None:
        try:
            self._cyber_module = _load_cybersecurity_engine()
            if hasattr(self._cyber_module, "start"):
                self._cyber_module.start()
            application_status.set_cybersecurity_status(StatusValue.OPERATIONAL)
            logger.info("Cybersecurity engine started.")
            register_cleanup(self.shutdown_cybersecurity_engine)
        except CybersecurityEngineUnavailable:
            self._cyber_module = None
            application_status.set_cybersecurity_status(StatusValue.UNAVAILABLE)
            logger.warning("Cybersecurity engine not started (module unavailable).")
        except Exception as exc:
            self._cyber_module = None
            application_status.set_cybersecurity_status(StatusValue.UNAVAILABLE)
            logger.error("Failed to start cybersecurity engine: %s", exc)

    def shutdown_cybersecurity_engine(self) -> None:
        if self._cyber_module is not None and hasattr(self._cyber_module, "stop"):
            with safe_execute("cybersecurity-shutdown"):
                self._cyber_module.stop()
        application_status.set_cybersecurity_status(StatusValue.STOPPED)

    # ------------------------------------------------------------------
    # Monitoring loop
    # ------------------------------------------------------------------
    def _monitoring_cycle(self) -> None:
        timestamp = datetime.utcnow()
        timestamp_iso = timestamp.isoformat()

        system_metrics = monitoring_collector.collect_system_metrics()
        top_processes = monitoring_processes.collect_top_processes()

        metrics_row = {
            "timestamp": timestamp_iso,
            "cpu_usage": system_metrics.cpu_usage,
            "ram_usage": system_metrics.ram_usage,
            "disk_usage": system_metrics.disk_usage,
            "disk_read_bps": system_metrics.disk_read_bps,
            "disk_write_bps": system_metrics.disk_write_bps,
            "network_in_bps": system_metrics.network_in_bps,
            "network_out_bps": system_metrics.network_out_bps,
        }
        # NOTE: monitoring_collector.collect_system_metrics() and
        # monitoring_processes.collect_top_processes() already persist
        # their samples to CSV internally via monitoring/metrics.py
        # (metrics.save_system_metrics() / metrics.save_process_metrics()).
        # Do NOT call save_system_metrics()/save_process_metrics() again
        # here - doing so would write every row to system_metrics.csv
        # and system_processes.csv twice per cycle.

        process_rows = [
            {
                "timestamp": timestamp_iso,
                "pid": p.pid,
                "name": p.name,
                "cpu_percent": p.cpu_percent,
                "memory_percent": p.memory_percent,
            }
            for p in top_processes
        ]

        alerts = monitoring_alerts.generate_alerts(
            cpu_usage=metrics_row["cpu_usage"],
            ram_usage=metrics_row["ram_usage"],
            disk_usage=metrics_row["disk_usage"],
            network_in_bps=metrics_row["network_in_bps"],
            network_out_bps=metrics_row["network_out_bps"],
            timestamp=timestamp_iso,
            tracker=self._alert_tracker,
        )
        if alerts:
            test_run_manager.record_alert(len(alerts))

        with safe_execute("database-write-cycle"):
            with db_module.session_scope() as session:
                db_crud.insert_system_metrics(metrics_row, test_run_id=self._run_id, db=session)
                db_crud.insert_process_metrics(process_rows, test_run_id=self._run_id, db=session)

        # Maintain bounded in-memory history for the AI engine.
        self._history_rows.append(metrics_row)
        if len(self._history_rows) > MAX_HISTORY_ROWS:
            self._history_rows = self._history_rows[-MAX_HISTORY_ROWS:]

        self._process_history_rows.extend(process_rows)
        if len(self._process_history_rows) > MAX_PROCESS_HISTORY_ROWS:
            self._process_history_rows = self._process_history_rows[-MAX_PROCESS_HISTORY_ROWS:]

        if self._ai_engine is not None:
            with safe_execute("ai-engine-cycle"):
                # load_monitoring_history() parses the "timestamp" column
                # and sets it as a DatetimeIndex - this is the format
                # predictive_alerts.prepare_prediction_features() expects.
                # A plain pd.DataFrame(rows) would keep a default integer
                # RangeIndex and break sort_index() when concatenated
                # against a Timestamp-indexed snapshot series.
                history_df = load_monitoring_history(self._history_rows)
                result = ai_engine_module.run_ai_cycle(
                    timestamp=timestamp,
                    cpu_usage=metrics_row["cpu_usage"],
                    ram_usage=metrics_row["ram_usage"],
                    disk_usage=metrics_row["disk_usage"],
                    history=history_df,
                    disk_read_bps=metrics_row["disk_read_bps"],
                    disk_write_bps=metrics_row["disk_write_bps"],
                    network_in_bps=metrics_row["network_in_bps"],
                    network_out_bps=metrics_row["network_out_bps"],
                    processes=process_rows,
                    process_history=self._process_history_rows,
                )
                self._last_ai_result = result

        if self._cyber_module is not None and hasattr(self._cyber_module, "run_cycle"):
            with safe_execute("cybersecurity-cycle"):
                self._cyber_module.run_cycle(metrics_row, process_rows)

    def _monitoring_loop(self) -> None:
        logger.info("Monitoring loop started.")
        application_status.set_monitoring_status(StatusValue.OPERATIONAL)
        while not self._stop_event.is_set():
            with safe_execute("monitoring-cycle"):
                self._monitoring_cycle()
            self._stop_event.wait(COLLECTION_INTERVAL_SECONDS)
        application_status.set_monitoring_status(StatusValue.STOPPED)
        logger.info("Monitoring loop terminated.")

    # ------------------------------------------------------------------
    # Public start / stop
    # ------------------------------------------------------------------
    def start(self) -> None:
        logger.info("Starting Lavender Trinetra services...")

        self._session_start = datetime.utcnow()
        self._history_rows = []
        self._process_history_rows = []
        self._last_ai_result = None

        startup_initialize(METRICS_HEADERS, PROCESSES_HEADERS, REPORT_HEADERS)
        self.init_database()
        self.init_ai_engine()
        self.init_cybersecurity_engine()
        self.start_api_server()

        self._stop_event.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop, name="monitoring-loop", daemon=True
        )
        self._monitoring_thread.start()
        register_cleanup(self._stop_monitoring_thread)

        logger.info("All services started. Monitoring is now active.")

    def _stop_monitoring_thread(self) -> None:
        self._stop_event.set()
        if self._monitoring_thread is not None:
            self._monitoring_thread.join(timeout=10)

    def stop(self) -> None:
        logger.info("Stopping Lavender Trinetra services...")

        self._stop_monitoring_thread()

        with safe_execute("csv-report-finalize"):
            # generate_report_on_stop() -> generate_session_report() already
            # appends the summary to system_report.csv internally via
            # monitoring/metrics.py. Calling save_system_report() again
            # here would duplicate the final report row.
            report = monitoring_reports.generate_report_on_stop(
                session_start=self._session_start or datetime.utcnow(),
                alert_tracker=self._alert_tracker,
            )

        if self._last_ai_result is not None and self._run_id is not None:
            with safe_execute("ai-report-finalize"):
                with db_module.session_scope() as session:
                    db_crud.insert_ai_result(self._last_ai_result, test_run_id=self._run_id, db=session)

        # safe_shutdown() runs all registered cleanup callbacks (API,
        # cybersecurity, database) in reverse order and marks every
        # component's status as stopped.
        safe_shutdown()

        logger.info("All services stopped cleanly.")


async def command_loop(orchestrator: Orchestrator) -> None:
    monitoring_active = False
    loop = asyncio.get_event_loop()

    while True:
        command = (await loop.run_in_executor(None, input, "> ")).strip().lower()

        if command == "start":
            if monitoring_active:
                print("Monitoring is already active.")
                continue
            orchestrator.start()
            monitoring_active = True

        elif command == "stop":
            if not monitoring_active:
                print("Monitoring is not currently active.")
                continue
            orchestrator.stop()
            monitoring_active = False
            print("User has stopped data collection.")
            print("Exiting!!")
            print("Thank You for using The System Health Monitor \U0001F600")
            break

        else:
            print('Unrecognized command. Type "start" or "stop".')


def _install_signal_handlers(orchestrator: Orchestrator) -> None:
    def _handle_signal(signum, frame) -> None:  # noqa: ANN001
        logger.info("Received signal %s, shutting down.", signum)
        orchestrator.stop()
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass


def main() -> None:
    print(BANNER)
    orchestrator = Orchestrator()
    _install_signal_handlers(orchestrator)

    try:
        asyncio.run(command_loop(orchestrator))
    except KeyboardInterrupt:
        orchestrator.stop()
        print("User has stopped data collection.")
        print("Exiting!!")
        print("Thank You for using The System Health Monitor \U0001F600")


if __name__ == "__main__":
    main()