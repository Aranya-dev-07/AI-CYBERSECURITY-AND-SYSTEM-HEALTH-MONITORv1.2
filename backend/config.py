from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback when python-dotenv is absent
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


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
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class MonitoringConfig:
    CPU_THRESHOLD: float = _env_float("MONITORING_CPU_THRESHOLD", 85.0)
    RAM_THRESHOLD: float = _env_float("MONITORING_RAM_THRESHOLD", 85.0)
    DISK_THRESHOLD: float = _env_float("MONITORING_DISK_THRESHOLD", 90.0)
    NETWORK_THRESHOLD: float = _env_float("MONITORING_NETWORK_THRESHOLD", 100.0)
    MONITORING_INTERVAL_SECONDS: float = _env_float("MONITORING_INTERVAL_SECONDS", 2.0)


@dataclass(frozen=True)
class AIConfig:
    AI_ENABLED: bool = _env_bool("AI_ENABLED", True)
    HEALTH_SCORE_WEIGHT_CPU: float = _env_float("AI_HEALTH_SCORE_WEIGHT_CPU", 0.25)
    HEALTH_SCORE_WEIGHT_RAM: float = _env_float("AI_HEALTH_SCORE_WEIGHT_RAM", 0.25)
    HEALTH_SCORE_WEIGHT_DISK: float = _env_float("AI_HEALTH_SCORE_WEIGHT_DISK", 0.25)
    HEALTH_SCORE_WEIGHT_NETWORK: float = _env_float("AI_HEALTH_SCORE_WEIGHT_NETWORK", 0.25)
    ANOMALY_THRESHOLD: float = _env_float("AI_ANOMALY_THRESHOLD", 0.85)
    PREDICTION_WINDOW_MINUTES: int = _env_int("AI_PREDICTION_WINDOW_MINUTES", 30)


@dataclass(frozen=True)
class CybersecurityConfig:
    THREAT_THRESHOLD: float = _env_float("CYBER_THREAT_THRESHOLD", 0.75)
    SCAN_INTERVAL_SECONDS: float = _env_float("CYBER_SCAN_INTERVAL_SECONDS", 60.0)


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


@dataclass(frozen=True)
class APIConfig:
    APP_NAME: str = _env_str("APP_NAME", "Lavender-Trinetra")
    APP_VERSION: str = _env_str("APP_VERSION", "1.0.0")
    API_HOST: str = _env_str("API_HOST", "127.0.0.1")
    API_PORT: int = _env_int("API_PORT", 8000)
    API_PREFIX: str = _env_str("API_PREFIX", "/api")
    LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO")


@dataclass(frozen=True)
class WebSocketConfig:
    WS_HOST: str = _env_str("WS_HOST", "127.0.0.1")
    WS_PORT: int = _env_int("WS_PORT", 8001)
    WS_PATH: str = _env_str("WS_PATH", "/ws")
    WS_HEARTBEAT_INTERVAL_SECONDS: float = _env_float("WS_HEARTBEAT_INTERVAL_SECONDS", 15.0)


@dataclass(frozen=True)
class FrontendConfig:
    CORS_ORIGINS: List[str] = field(
        default_factory=lambda: _env_list("CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])
    )
    CORS_ALLOW_CREDENTIALS: bool = _env_bool("CORS_ALLOW_CREDENTIALS", True)


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

    # -----------------------------------------------------------------
    # Flat convenience aliases for backward compatibility across modules
    # -----------------------------------------------------------------
    @property
    def APP_NAME(self) -> str:
        return self.api.APP_NAME

    @property
    def APP_VERSION(self) -> str:
        return self.api.APP_VERSION

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

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return self.frontend.CORS_ORIGINS

    @property
    def DATABASE_URL(self) -> str:
        return self.database.DATABASE_URL

    @property
    def COLLECTION_INTERVAL_SECONDS(self) -> float:
        return self.monitoring.MONITORING_INTERVAL_SECONDS

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

    @property
    def AI_ENABLED(self) -> bool:
        return self.ai.AI_ENABLED

    @property
    def ANOMALY_THRESHOLD(self) -> float:
        return self.ai.ANOMALY_THRESHOLD

    @property
    def PREDICTION_WINDOW_MINUTES(self) -> int:
        return self.ai.PREDICTION_WINDOW_MINUTES

    @property
    def THREAT_THRESHOLD(self) -> float:
        return self.cybersecurity.THREAT_THRESHOLD

    @property
    def SCAN_INTERVAL_SECONDS(self) -> float:
        return self.cybersecurity.SCAN_INTERVAL_SECONDS

    @property
    def SYSTEM_METRICS_CSV(self) -> str:
        return self.csv.SYSTEM_METRICS_CSV

    @property
    def SYSTEM_PROCESSES_CSV(self) -> str:
        return self.csv.SYSTEM_PROCESSES_CSV

    @property
    def SYSTEM_REPORT_CSV(self) -> str:
        return self.csv.SYSTEM_REPORT_CSV


settings = Settings()