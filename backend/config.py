from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Set

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback when python-dotenv is absent
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Environment variable helpers
# ---------------------------------------------------------------------------
def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_set(name: str, default: Set[str]) -> Set[str]:
    value = os.getenv(name)
    if value is None:
        return set(default)
    return {item.strip() for item in value.split(",") if item.strip()}


def _env_int_set(name: str, default: Set[int]) -> Set[int]:
    value = os.getenv(name)
    if value is None:
        return set(default)
    result: Set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            continue
    return result


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MonitoringConfig:
    CPU_THRESHOLD: float = _env_float("MONITORING_CPU_THRESHOLD", 85.0)
    RAM_THRESHOLD: float = _env_float("MONITORING_RAM_THRESHOLD", 85.0)
    DISK_THRESHOLD: float = _env_float("MONITORING_DISK_THRESHOLD", 90.0)
    NETWORK_THRESHOLD: float = _env_float("MONITORING_NETWORK_THRESHOLD", 100.0)
    MONITORING_INTERVAL_SECONDS: float = _env_float("MONITORING_INTERVAL_SECONDS", 2.0)
    CSV_UPDATE_INTERVAL_SECONDS: float = _env_float("MONITORING_CSV_UPDATE_INTERVAL_SECONDS", 2.0)


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIConfig:
    AI_ENABLED: bool = _env_bool("AI_ENABLED", True)
    HEALTH_SCORE_WEIGHT_CPU: float = _env_float("AI_HEALTH_SCORE_WEIGHT_CPU", 0.25)
    HEALTH_SCORE_WEIGHT_RAM: float = _env_float("AI_HEALTH_SCORE_WEIGHT_RAM", 0.25)
    HEALTH_SCORE_WEIGHT_DISK: float = _env_float("AI_HEALTH_SCORE_WEIGHT_DISK", 0.25)
    HEALTH_SCORE_WEIGHT_NETWORK: float = _env_float("AI_HEALTH_SCORE_WEIGHT_NETWORK", 0.25)
    ANOMALY_THRESHOLD: float = _env_float("AI_ANOMALY_THRESHOLD", 0.85)
    TREND_WINDOW_MINUTES: int = _env_int("AI_TREND_WINDOW_MINUTES", 60)
    PREDICTION_WINDOW_MINUTES: int = _env_int("AI_PREDICTION_WINDOW_MINUTES", 30)


# ---------------------------------------------------------------------------
# Cybersecurity - Phase 1 monitors
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FirewallConfig:
    COMMAND_TIMEOUT_SECONDS: float = _env_float("FIREWALL_COMMAND_TIMEOUT_SECONDS", 5.0)
    EVENT_HISTORY_LIMIT: int = _env_int("FIREWALL_EVENT_HISTORY_LIMIT", 100)


@dataclass(frozen=True)
class NetworkMonitorConfig:
    SPIKE_MULTIPLIER: float = _env_float("NETWORK_SPIKE_MULTIPLIER", 3.0)
    BASELINE_WINDOW_SAMPLES: int = _env_int("NETWORK_BASELINE_WINDOW_SAMPLES", 10)
    MIN_BASELINE_BPS: float = _env_float("NETWORK_MIN_BASELINE_BPS", 50_000.0)
    MAX_CONNECTIONS_PER_PROCESS: int = _env_int("NETWORK_MAX_CONNECTIONS_PER_PROCESS", 100)


@dataclass(frozen=True)
class PortMonitorConfig:
    EVENT_HISTORY_LIMIT: int = _env_int("PORT_EVENT_HISTORY_LIMIT", 200)


@dataclass(frozen=True)
class ProcessMonitorConfig:
    CPU_SUSPICION_THRESHOLD: float = _env_float("PROCESS_CPU_SUSPICION_THRESHOLD", 85.0)
    RAM_SUSPICION_THRESHOLD: float = _env_float("PROCESS_RAM_SUSPICION_THRESHOLD", 80.0)
    RAPID_CREATION_WINDOW_SECONDS: float = _env_float("PROCESS_RAPID_CREATION_WINDOW_SECONDS", 10.0)
    RAPID_CREATION_COUNT_THRESHOLD: int = _env_int("PROCESS_RAPID_CREATION_COUNT_THRESHOLD", 8)
    SUSPICIOUS_PROCESS_HISTORY_SIZE: int = _env_int("SUSPICIOUS_PROCESS_HISTORY_SIZE", 500)


@dataclass(frozen=True)
class SessionMonitorConfig:
    MONITORING_INTERVAL_SECONDS: float = _env_float("SESSION_MONITORING_INTERVAL_SECONDS", 30.0)
    WATCHED_USERNAMES: Set[str] = field(
        default_factory=lambda: _env_set("SESSION_WATCHED_USERNAMES", {"root", "administrator", "admin"})
    )
    MAX_CONCURRENT_PER_USER: int = _env_int("SESSION_MAX_CONCURRENT_PER_USER", 3)
    EVENT_HISTORY_LIMIT: int = _env_int("SESSION_EVENT_HISTORY_LIMIT", 200)


# ---------------------------------------------------------------------------
# Cybersecurity - Phase 2 detection
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IntrusionConfig:
    CONNECTION_WINDOW_SECONDS: float = _env_float("INTRUSION_CONNECTION_WINDOW_SECONDS", 60.0)
    CONNECTION_ATTEMPT_THRESHOLD: int = _env_int("INTRUSION_CONNECTION_ATTEMPT_THRESHOLD", 15)
    PORT_SCAN_DISTINCT_PORTS: int = _env_int("INTRUSION_PORT_SCAN_DISTINCT_PORTS", 5)
    LOGIN_WINDOW_SECONDS: float = _env_float("INTRUSION_LOGIN_WINDOW_SECONDS", 120.0)
    LOGIN_ATTEMPT_THRESHOLD: int = _env_int("INTRUSION_LOGIN_ATTEMPT_THRESHOLD", 5)
    EXPECTED_OPEN_PORTS: Set[int] = field(
        default_factory=lambda: _env_int_set(
            "INTRUSION_EXPECTED_OPEN_PORTS", {22, 80, 443, 3306, 5432, 8000, 5173}
        )
    )
    DETECTOR_HISTORY_SIZE: int = _env_int("INTRUSION_DETECTOR_HISTORY_SIZE", 500)


@dataclass(frozen=True)
class VulnerabilityScanConfig:
    SCAN_INTERVAL_SECONDS: float = _env_float("VULNERABILITY_SCAN_INTERVAL_SECONDS", 60.0)
    OPEN_PORT_COUNT_WARNING_THRESHOLD: int = _env_int("VULN_OPEN_PORT_COUNT_WARNING_THRESHOLD", 15)
    ELEVATED_USERNAMES: Set[str] = field(
        default_factory=lambda: _env_set(
            "VULN_ELEVATED_USERNAMES", {"root", "system", "administrator", "admin", "localsystem"}
        )
    )
    HISTORY_SIZE: int = _env_int("VULNERABILITY_SCAN_HISTORY_SIZE", 500)


@dataclass(frozen=True)
class ThreatDetectorConfig:
    HISTORY_SIZE: int = _env_int("THREAT_DETECTOR_HISTORY_SIZE", 500)


@dataclass(frozen=True)
class ThreatClassifierConfig:
    HISTORY_SIZE: int = _env_int("THREAT_CLASSIFIER_HISTORY_SIZE", 500)


# ---------------------------------------------------------------------------
# Cybersecurity - Phase 3 explainable AI security layer
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AttackPatternConfig:
    CORRELATION_WINDOW_SECONDS: float = _env_float("ATTACK_PATTERN_CORRELATION_WINDOW_SECONDS", 300.0)
    RECURRENCE_WINDOW_SECONDS: float = _env_float("ATTACK_PATTERN_RECURRENCE_WINDOW_SECONDS", 3600.0)
    RECURRENCE_THRESHOLD: int = _env_int("ATTACK_PATTERN_RECURRENCE_THRESHOLD", 3)
    HISTORY_SIZE: int = _env_int("ATTACK_PATTERN_HISTORY_SIZE", 500)
    SOURCE_LOOKBACK: int = _env_int("ATTACK_PATTERN_SOURCE_LOOKBACK", 2000)


@dataclass(frozen=True)
class SecurityScoreConfig:
    WEIGHT_THREATS: float = _env_float("SECURITY_SCORE_WEIGHT_THREATS", 0.30)
    WEIGHT_INTRUSIONS: float = _env_float("SECURITY_SCORE_WEIGHT_INTRUSIONS", 0.25)
    WEIGHT_VULNERABILITIES: float = _env_float("SECURITY_SCORE_WEIGHT_VULNERABILITIES", 0.25)
    WEIGHT_FIREWALL: float = _env_float("SECURITY_SCORE_WEIGHT_FIREWALL", 0.20)
    HISTORY_SIZE: int = _env_int("SECURITY_SCORE_HISTORY_SIZE", 500)


@dataclass(frozen=True)
class SecurityRecommendationsConfig:
    HISTORY_SIZE: int = _env_int("SECURITY_RECOMMENDATIONS_HISTORY_SIZE", 500)
    LOW_SCORE_THRESHOLD: float = _env_float("SECURITY_RECOMMENDATIONS_LOW_SCORE_THRESHOLD", 75.0)
    CRITICAL_SCORE_THRESHOLD: float = _env_float("SECURITY_RECOMMENDATIONS_CRITICAL_SCORE_THRESHOLD", 40.0)
    LOW_CONFIDENCE_THRESHOLD: float = _env_float("SECURITY_RECOMMENDATIONS_LOW_CONFIDENCE_THRESHOLD", 0.55)


@dataclass(frozen=True)
class IncidentLoggerConfig:
    HISTORY_SIZE: int = _env_int("INCIDENT_LOGGER_HISTORY_SIZE", 1000)
    MIN_SEVERITY: str = _env_str("INCIDENT_LOGGER_MIN_SEVERITY", "Medium")
    POSTURE_SCORE_THRESHOLD: float = _env_float("INCIDENT_LOGGER_POSTURE_SCORE_THRESHOLD", 50.0)
    DEDUP_WINDOW_SECONDS: float = _env_float("INCIDENT_LOGGER_DEDUP_WINDOW_SECONDS", 3600.0)
    DEFAULT_PAGE_SIZE: int = _env_int("INCIDENT_DEFAULT_PAGE_SIZE", 100)
    MAX_PAGE_SIZE: int = _env_int("INCIDENT_MAX_PAGE_SIZE", 500)


@dataclass(frozen=True)
class SecurityHistoryConfig:
    DEFAULT_WINDOW_DAYS: int = _env_int("SECURITY_HISTORY_DEFAULT_WINDOW_DAYS", 30)
    MAX_WINDOW_DAYS: int = _env_int("SECURITY_HISTORY_MAX_WINDOW_DAYS", 365)
    DEFAULT_LIMIT: int = _env_int("SECURITY_HISTORY_DEFAULT_LIMIT", 200)
    MAX_LIMIT: int = _env_int("SECURITY_HISTORY_MAX_LIMIT", 1000)


@dataclass(frozen=True)
class SecurityReportConfig:
    DEFAULT_WINDOW_DAYS: int = _env_int("SECURITY_REPORT_DEFAULT_WINDOW_DAYS", 7)
    MAX_WINDOW_DAYS: int = _env_int("SECURITY_REPORT_MAX_WINDOW_DAYS", 365)
    DEFAULT_LIMIT: int = _env_int("SECURITY_REPORT_DEFAULT_LIMIT", 200)
    MAX_LIMIT: int = _env_int("SECURITY_REPORT_MAX_LIMIT", 1000)


@dataclass(frozen=True)
class CybersecurityConfig:
    THREAT_THRESHOLD: float = _env_float("CYBER_THREAT_THRESHOLD", 0.75)
    # Generic cybersecurity scan cadence, kept for backward compatibility
    # with modules that read a single top-level scan interval.
    SCAN_INTERVAL_SECONDS: float = _env_float("CYBER_SCAN_INTERVAL_SECONDS", 60.0)

    firewall: FirewallConfig = field(default_factory=FirewallConfig)
    network: NetworkMonitorConfig = field(default_factory=NetworkMonitorConfig)
    port: PortMonitorConfig = field(default_factory=PortMonitorConfig)
    process: ProcessMonitorConfig = field(default_factory=ProcessMonitorConfig)
    session: SessionMonitorConfig = field(default_factory=SessionMonitorConfig)
    intrusion: IntrusionConfig = field(default_factory=IntrusionConfig)
    vulnerability_scan: VulnerabilityScanConfig = field(default_factory=VulnerabilityScanConfig)
    threat_detector: ThreatDetectorConfig = field(default_factory=ThreatDetectorConfig)
    threat_classifier: ThreatClassifierConfig = field(default_factory=ThreatClassifierConfig)
    attack_patterns: AttackPatternConfig = field(default_factory=AttackPatternConfig)
    security_score: SecurityScoreConfig = field(default_factory=SecurityScoreConfig)
    security_recommendations: SecurityRecommendationsConfig = field(
        default_factory=SecurityRecommendationsConfig
    )
    incident_logger: IncidentLoggerConfig = field(default_factory=IncidentLoggerConfig)
    security_history: SecurityHistoryConfig = field(default_factory=SecurityHistoryConfig)
    security_reports: SecurityReportConfig = field(default_factory=SecurityReportConfig)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CSVConfig:
    SYSTEM_METRICS_CSV: str = _env_str(
        "CSV_SYSTEM_METRICS_PATH", str(BASE_DIR / "backend" / "data" / "system_metrics.csv")
    )
    SYSTEM_PROCESSES_CSV: str = _env_str(
        "CSV_SYSTEM_PROCESSES_PATH", str(BASE_DIR / "backend" / "data" / "system_processes.csv")
    )
    SYSTEM_REPORT_CSV: str = _env_str(
        "CSV_SYSTEM_REPORT_PATH", str(BASE_DIR / "backend" / "data" / "system_report.csv")
    )


# ---------------------------------------------------------------------------
# Database (PostgreSQL)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DatabaseConfig:
    DB_ENGINE: str = _env_str("DB_ENGINE", "sqlite")
    DB_HOST: str = _env_str("DB_HOST", "localhost")
    DB_PORT: int = _env_int("DB_PORT", 5432)
    DB_NAME: str = _env_str("DB_NAME", "lavender_trinetra")
    DB_USER: str = _env_str("DB_USER", "postgres")
    DB_PASSWORD: str = _env_str("DB_PASSWORD", "")
    DB_SSLMODE: str = _env_str("DB_SSLMODE", "prefer")
    SQLITE_PATH: str = _env_str(
        "SQLITE_PATH", str(BASE_DIR / "backend" / "data" / "lavender_trinetra.db")
    )
    DATABASE_URL: str = _env_str(
        "DATABASE_URL",
        f"sqlite:///{_env_str('SQLITE_PATH', str(BASE_DIR / 'backend' / 'data' / 'lavender_trinetra.db'))}"
        if _env_str("DB_ENGINE", "sqlite") == "sqlite"
        else (
            f"postgresql+psycopg2://{_env_str('DB_USER', 'postgres')}:"
            f"{_env_str('DB_PASSWORD', '')}@{_env_str('DB_HOST', 'localhost')}:"
            f"{_env_int('DB_PORT', 5432)}/{_env_str('DB_NAME', 'lavender_trinetra')}"
        ),
    )
    DB_POOL_SIZE: int = _env_int("DB_POOL_SIZE", 10)
    DB_MAX_OVERFLOW: int = _env_int("DB_MAX_OVERFLOW", 20)
    DB_ECHO: bool = _env_bool("DB_ECHO", False)


# ---------------------------------------------------------------------------
# API (FastAPI)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class APIConfig:
    APP_NAME: str = _env_str("APP_NAME", "Lavender-Trinetra")
    APP_VERSION: str = _env_str("APP_VERSION", "1.0.0")
    API_HOST: str = _env_str("API_HOST", "127.0.0.1")
    API_PORT: int = _env_int("API_PORT", 8000)
    API_PREFIX: str = _env_str("API_PREFIX", "/api")
    LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WebSocketConfig:
    WS_HOST: str = _env_str("WS_HOST", "127.0.0.1")
    WS_PORT: int = _env_int("WS_PORT", 8001)
    WS_PATH: str = _env_str("WS_PATH", "/ws")
    WS_HEARTBEAT_INTERVAL_SECONDS: float = _env_float("WS_HEARTBEAT_INTERVAL_SECONDS", 15.0)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrontendConfig:
    CORS_ORIGINS: List[str] = field(
        default_factory=lambda: _env_list("CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])
    )
    CORS_ALLOW_CREDENTIALS: bool = _env_bool("CORS_ALLOW_CREDENTIALS", True)
    DASHBOARD_REFRESH_INTERVAL_SECONDS: float = _env_float("FRONTEND_DASHBOARD_REFRESH_INTERVAL_SECONDS", 5.0)
    STATUS_UPDATE_INTERVAL_SECONDS: float = _env_float("FRONTEND_STATUS_UPDATE_INTERVAL_SECONDS", 15.0)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LoggingConfig:
    LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = _env_str(
        "LOG_FORMAT", "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    LOG_DATE_FORMAT: str = _env_str("LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S")
    LOG_TO_FILE: bool = _env_bool("LOG_TO_FILE", False)
    LOG_FILE_PATH: str = _env_str(
        "LOG_FILE_PATH", str(BASE_DIR / "backend" / "data" / "lavender_trinetra.log")
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ApplicationConfig:
    APP_NAME: str = _env_str("APP_NAME", "Lavender-Trinetra")
    APP_VERSION: str = _env_str("APP_VERSION", "1.0.0")
    THEME_NAME: str = _env_str("THEME_NAME", "Lavender Trinetra")
    DEFAULT_STATUS: str = _env_str("APP_DEFAULT_STATUS", "unknown")


# ---------------------------------------------------------------------------
# Root settings object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    cybersecurity: CybersecurityConfig = field(default_factory=CybersecurityConfig)
    csv: CSVConfig = field(default_factory=CSVConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    api: APIConfig = field(default_factory=APIConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    frontend: FrontendConfig = field(default_factory=FrontendConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    application: ApplicationConfig = field(default_factory=ApplicationConfig)

    # -----------------------------------------------------------------
    # Flat convenience aliases for backward compatibility across every
    # backend module. No business logic lives here - these are pure
    # pass-throughs to the nested, grouped configuration above, kept so
    # every module (regardless of when it was written) can read either
    # `settings.<GROUP>.<FIELD>` or `settings.<FLAT_NAME>` /
    # `getattr(settings, "<FLAT_NAME>", default)`.
    # -----------------------------------------------------------------

    # Application
    @property
    def APP_NAME(self) -> str:
        return self.application.APP_NAME

    @property
    def APP_VERSION(self) -> str:
        return self.application.APP_VERSION

    @property
    def THEME_NAME(self) -> str:
        return self.application.THEME_NAME

    @property
    def DEFAULT_STATUS(self) -> str:
        return self.application.DEFAULT_STATUS

    # API
    @property
    def API_HOST(self) -> str:
        return self.api.API_HOST

    @property
    def API_PORT(self) -> int:
        return self.api.API_PORT

    @property
    def API_PREFIX(self) -> str:
        return self.api.API_PREFIX

    @property
    def LOG_LEVEL(self) -> str:
        return self.api.LOG_LEVEL

    # Frontend
    @property
    def CORS_ORIGINS(self) -> List[str]:
        return self.frontend.CORS_ORIGINS

    @property
    def CORS_ALLOW_CREDENTIALS(self) -> bool:
        return self.frontend.CORS_ALLOW_CREDENTIALS

    @property
    def DASHBOARD_REFRESH_INTERVAL_SECONDS(self) -> float:
        return self.frontend.DASHBOARD_REFRESH_INTERVAL_SECONDS

    @property
    def STATUS_UPDATE_INTERVAL_SECONDS(self) -> float:
        return self.frontend.STATUS_UPDATE_INTERVAL_SECONDS

    # Database
    @property
    def DATABASE_URL(self) -> str:
        return self.database.DATABASE_URL

    # Monitoring
    @property
    def COLLECTION_INTERVAL_SECONDS(self) -> float:
        return self.monitoring.MONITORING_INTERVAL_SECONDS

    @property
    def CSV_UPDATE_INTERVAL_SECONDS(self) -> float:
        return self.monitoring.CSV_UPDATE_INTERVAL_SECONDS

    @property
    def CPU_THRESHOLD(self) -> float:
        return self.monitoring.CPU_THRESHOLD

    @property
    def RAM_THRESHOLD(self) -> float:
        return self.monitoring.RAM_THRESHOLD

    @property
    def DISK_THRESHOLD(self) -> float:
        return self.monitoring.DISK_THRESHOLD

    @property
    def NETWORK_THRESHOLD(self) -> float:
        return self.monitoring.NETWORK_THRESHOLD

    # AI
    @property
    def AI_ENABLED(self) -> bool:
        return self.ai.AI_ENABLED

    @property
    def ANOMALY_THRESHOLD(self) -> float:
        return self.ai.ANOMALY_THRESHOLD

    @property
    def TREND_WINDOW_MINUTES(self) -> int:
        return self.ai.TREND_WINDOW_MINUTES

    @property
    def PREDICTION_WINDOW_MINUTES(self) -> int:
        return self.ai.PREDICTION_WINDOW_MINUTES

    # CSV paths
    @property
    def SYSTEM_METRICS_CSV(self) -> str:
        return self.csv.SYSTEM_METRICS_CSV

    @property
    def SYSTEM_PROCESSES_CSV(self) -> str:
        return self.csv.SYSTEM_PROCESSES_CSV

    @property
    def SYSTEM_REPORT_CSV(self) -> str:
        return self.csv.SYSTEM_REPORT_CSV

    # Cybersecurity - top-level
    @property
    def THREAT_THRESHOLD(self) -> float:
        return self.cybersecurity.THREAT_THRESHOLD

    @property
    def SCAN_INTERVAL_SECONDS(self) -> float:
        return self.cybersecurity.SCAN_INTERVAL_SECONDS

    # Cybersecurity - firewall
    @property
    def FIREWALL_COMMAND_TIMEOUT_SECONDS(self) -> float:
        return self.cybersecurity.firewall.COMMAND_TIMEOUT_SECONDS

    @property
    def FIREWALL_EVENT_HISTORY_LIMIT(self) -> int:
        return self.cybersecurity.firewall.EVENT_HISTORY_LIMIT

    # Cybersecurity - network
    @property
    def NETWORK_SPIKE_MULTIPLIER(self) -> float:
        return self.cybersecurity.network.SPIKE_MULTIPLIER

    @property
    def NETWORK_BASELINE_WINDOW_SAMPLES(self) -> int:
        return self.cybersecurity.network.BASELINE_WINDOW_SAMPLES

    @property
    def NETWORK_MIN_BASELINE_BPS(self) -> float:
        return self.cybersecurity.network.MIN_BASELINE_BPS

    @property
    def NETWORK_MAX_CONNECTIONS_PER_PROCESS(self) -> int:
        return self.cybersecurity.network.MAX_CONNECTIONS_PER_PROCESS

    # Cybersecurity - port
    @property
    def PORT_EVENT_HISTORY_LIMIT(self) -> int:
        return self.cybersecurity.port.EVENT_HISTORY_LIMIT

    # Cybersecurity - process
    @property
    def PROCESS_CPU_SUSPICION_THRESHOLD(self) -> float:
        return self.cybersecurity.process.CPU_SUSPICION_THRESHOLD

    @property
    def PROCESS_RAM_SUSPICION_THRESHOLD(self) -> float:
        return self.cybersecurity.process.RAM_SUSPICION_THRESHOLD

    @property
    def PROCESS_RAPID_CREATION_WINDOW_SECONDS(self) -> float:
        return self.cybersecurity.process.RAPID_CREATION_WINDOW_SECONDS

    @property
    def PROCESS_RAPID_CREATION_COUNT_THRESHOLD(self) -> int:
        return self.cybersecurity.process.RAPID_CREATION_COUNT_THRESHOLD

    @property
    def SUSPICIOUS_PROCESS_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.process.SUSPICIOUS_PROCESS_HISTORY_SIZE

    # Cybersecurity - session
    @property
    def SESSION_MONITORING_INTERVAL_SECONDS(self) -> float:
        return self.cybersecurity.session.MONITORING_INTERVAL_SECONDS

    @property
    def SESSION_WATCHED_USERNAMES(self) -> Set[str]:
        return self.cybersecurity.session.WATCHED_USERNAMES

    @property
    def SESSION_MAX_CONCURRENT_PER_USER(self) -> int:
        return self.cybersecurity.session.MAX_CONCURRENT_PER_USER

    @property
    def SESSION_EVENT_HISTORY_LIMIT(self) -> int:
        return self.cybersecurity.session.EVENT_HISTORY_LIMIT

    # Cybersecurity - intrusion detection
    @property
    def INTRUSION_CONNECTION_WINDOW_SECONDS(self) -> float:
        return self.cybersecurity.intrusion.CONNECTION_WINDOW_SECONDS

    @property
    def INTRUSION_CONNECTION_ATTEMPT_THRESHOLD(self) -> int:
        return self.cybersecurity.intrusion.CONNECTION_ATTEMPT_THRESHOLD

    @property
    def INTRUSION_PORT_SCAN_DISTINCT_PORTS(self) -> int:
        return self.cybersecurity.intrusion.PORT_SCAN_DISTINCT_PORTS

    @property
    def INTRUSION_LOGIN_WINDOW_SECONDS(self) -> float:
        return self.cybersecurity.intrusion.LOGIN_WINDOW_SECONDS

    @property
    def INTRUSION_LOGIN_ATTEMPT_THRESHOLD(self) -> int:
        return self.cybersecurity.intrusion.LOGIN_ATTEMPT_THRESHOLD

    @property
    def INTRUSION_EXPECTED_OPEN_PORTS(self) -> Set[int]:
        return self.cybersecurity.intrusion.EXPECTED_OPEN_PORTS

    @property
    def INTRUSION_DETECTOR_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.intrusion.DETECTOR_HISTORY_SIZE

    # Cybersecurity - vulnerability scan
    @property
    def VULNERABILITY_SCAN_INTERVAL_SECONDS(self) -> float:
        return self.cybersecurity.vulnerability_scan.SCAN_INTERVAL_SECONDS

    @property
    def VULN_OPEN_PORT_COUNT_WARNING_THRESHOLD(self) -> int:
        return self.cybersecurity.vulnerability_scan.OPEN_PORT_COUNT_WARNING_THRESHOLD

    @property
    def VULN_ELEVATED_USERNAMES(self) -> Set[str]:
        return self.cybersecurity.vulnerability_scan.ELEVATED_USERNAMES

    @property
    def VULNERABILITY_SCAN_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.vulnerability_scan.HISTORY_SIZE

    # Cybersecurity - threat detector / classifier
    @property
    def THREAT_DETECTOR_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.threat_detector.HISTORY_SIZE

    @property
    def THREAT_CLASSIFIER_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.threat_classifier.HISTORY_SIZE

    # Cybersecurity - attack patterns
    @property
    def ATTACK_PATTERN_CORRELATION_WINDOW_SECONDS(self) -> float:
        return self.cybersecurity.attack_patterns.CORRELATION_WINDOW_SECONDS

    @property
    def ATTACK_PATTERN_RECURRENCE_WINDOW_SECONDS(self) -> float:
        return self.cybersecurity.attack_patterns.RECURRENCE_WINDOW_SECONDS

    @property
    def ATTACK_PATTERN_RECURRENCE_THRESHOLD(self) -> int:
        return self.cybersecurity.attack_patterns.RECURRENCE_THRESHOLD

    @property
    def ATTACK_PATTERN_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.attack_patterns.HISTORY_SIZE

    @property
    def ATTACK_PATTERN_SOURCE_LOOKBACK(self) -> int:
        return self.cybersecurity.attack_patterns.SOURCE_LOOKBACK

    # Cybersecurity - security score
    @property
    def SECURITY_SCORE_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.security_score.HISTORY_SIZE

    # Cybersecurity - security recommendations
    @property
    def SECURITY_RECOMMENDATIONS_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.security_recommendations.HISTORY_SIZE

    @property
    def SECURITY_RECOMMENDATIONS_LOW_SCORE_THRESHOLD(self) -> float:
        return self.cybersecurity.security_recommendations.LOW_SCORE_THRESHOLD

    @property
    def SECURITY_RECOMMENDATIONS_CRITICAL_SCORE_THRESHOLD(self) -> float:
        return self.cybersecurity.security_recommendations.CRITICAL_SCORE_THRESHOLD

    @property
    def SECURITY_RECOMMENDATIONS_LOW_CONFIDENCE_THRESHOLD(self) -> float:
        return self.cybersecurity.security_recommendations.LOW_CONFIDENCE_THRESHOLD

    # Cybersecurity - incident logger
    @property
    def INCIDENT_LOGGER_HISTORY_SIZE(self) -> int:
        return self.cybersecurity.incident_logger.HISTORY_SIZE

    @property
    def INCIDENT_LOGGER_MIN_SEVERITY(self) -> str:
        return self.cybersecurity.incident_logger.MIN_SEVERITY

    @property
    def INCIDENT_LOGGER_POSTURE_SCORE_THRESHOLD(self) -> float:
        return self.cybersecurity.incident_logger.POSTURE_SCORE_THRESHOLD

    @property
    def INCIDENT_LOGGER_DEDUP_WINDOW_SECONDS(self) -> float:
        return self.cybersecurity.incident_logger.DEDUP_WINDOW_SECONDS

    @property
    def INCIDENT_DEFAULT_PAGE_SIZE(self) -> int:
        return self.cybersecurity.incident_logger.DEFAULT_PAGE_SIZE

    @property
    def INCIDENT_MAX_PAGE_SIZE(self) -> int:
        return self.cybersecurity.incident_logger.MAX_PAGE_SIZE

    # Cybersecurity - security history
    @property
    def SECURITY_HISTORY_DEFAULT_WINDOW_DAYS(self) -> int:
        return self.cybersecurity.security_history.DEFAULT_WINDOW_DAYS

    @property
    def SECURITY_HISTORY_MAX_WINDOW_DAYS(self) -> int:
        return self.cybersecurity.security_history.MAX_WINDOW_DAYS

    @property
    def SECURITY_HISTORY_DEFAULT_LIMIT(self) -> int:
        return self.cybersecurity.security_history.DEFAULT_LIMIT

    @property
    def SECURITY_HISTORY_MAX_LIMIT(self) -> int:
        return self.cybersecurity.security_history.MAX_LIMIT

    # Cybersecurity - security reports
    @property
    def SECURITY_REPORT_DEFAULT_WINDOW_DAYS(self) -> int:
        return self.cybersecurity.security_reports.DEFAULT_WINDOW_DAYS

    @property
    def SECURITY_REPORT_MAX_WINDOW_DAYS(self) -> int:
        return self.cybersecurity.security_reports.MAX_WINDOW_DAYS

    @property
    def SECURITY_REPORT_DEFAULT_LIMIT(self) -> int:
        return self.cybersecurity.security_reports.DEFAULT_LIMIT

    @property
    def SECURITY_REPORT_MAX_LIMIT(self) -> int:
        return self.cybersecurity.security_reports.MAX_LIMIT


settings = Settings()