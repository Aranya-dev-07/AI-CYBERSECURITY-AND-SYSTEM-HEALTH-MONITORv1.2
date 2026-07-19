import logging
from typing import Generator

from fastapi import Depends

from backend.config import settings

logger = logging.getLogger("lavender_trinetra.dependencies")


# ---------------------------------------------------------------------------
# Database Session
# ---------------------------------------------------------------------------
def get_db() -> Generator:
    """
    Provides a SQLite database session per request.
    Ensures the session is always closed after use, even on error.
    Imported lazily to avoid circular imports between the database
    and api packages.
    """
    from backend.database.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def get_settings():
    """
    Provides application configuration/settings object.
    """
    return settings


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def get_logger(name: str = "lavender_trinetra") -> logging.Logger:
    """
    Provides a configured logger instance for a given module name.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# AI Engine
# ---------------------------------------------------------------------------
def get_ai_engine():
    """
    Provides a shared AI engine instance.
    Lazily imported to avoid circular imports and to allow the API
    to start even if the AI module fails to load.
    """
    try:
        from backend.ai.ai_engine import AIEngine
        if not hasattr(get_ai_engine, "_instance"):
            get_ai_engine._instance = AIEngine()
        return get_ai_engine._instance
    except Exception as exc:
        logger.error("Failed to initialize AI engine: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Monitoring Engine
# ---------------------------------------------------------------------------
def get_monitoring_engine():
    """
    Provides a shared monitoring collector instance.
    Lazily imported to avoid circular imports and to allow the API
    to start even if the monitoring module fails to load.
    """
    try:
        from backend.monitoring.collector import MonitoringCollector
        if not hasattr(get_monitoring_engine, "_instance"):
            get_monitoring_engine._instance = MonitoringCollector()
        return get_monitoring_engine._instance
    except Exception as exc:
        logger.error("Failed to initialize monitoring engine: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Common Dependency Bundle
# ---------------------------------------------------------------------------
class CommonDependencies:
    """
    Aggregates commonly used dependencies for endpoints that require
    multiple shared resources at once.
    """

    def __init__(
        self,
        db=Depends(get_db),
        config=Depends(get_settings),
        ai_engine=Depends(get_ai_engine),
        monitoring_engine=Depends(get_monitoring_engine),
    ):
        self.db = db
        self.config = config
        self.ai_engine = ai_engine
        self.monitoring_engine = monitoring_engine