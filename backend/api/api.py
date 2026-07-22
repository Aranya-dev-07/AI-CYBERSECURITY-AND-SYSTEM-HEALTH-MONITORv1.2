import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.api.routes import router as api_router

# Phase 3 explainable-AI security modules each own a small self-contained
# FastAPI router (already prefixed with /api/cybersecurity/...) exposing
# their live/recent/summary/history endpoints. Mounted directly on the
# app, guarded the same way backend.cybersecurity is guarded in routes.py,
# so the rest of the API still comes up if either module is unavailable.
try:
    from backend.cybersecurity.attack_patterns import router as attack_patterns_router
except ImportError:
    attack_patterns_router = None

try:
    from backend.cybersecurity.security_recommendations import router as security_recommendations_router
except ImportError:
    security_recommendations_router = None

# Phase 4 (incident management + historical reporting) routers - same
# self-contained-router mounting pattern as the Phase 3 routers above.
try:
    from backend.cybersecurity.incident_logger import router as incident_logger_router
except ImportError:
    incident_logger_router = None

try:
    from backend.cybersecurity.security_history import router as security_history_router
except ImportError:
    security_history_router = None

try:
    from backend.cybersecurity.security_reports import router as security_reports_router
except ImportError:
    security_reports_router = None

logging.basicConfig(
    level=getattr(logging, getattr(settings, "LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("lavender_trinetra.api")

APP_NAME = getattr(settings, "APP_NAME", "Lavender-Trinetra")
APP_VERSION = getattr(settings, "APP_VERSION", "1.0.0")

app_status = {
    "api": "operational",
    "ai": "unknown",
    "monitoring": "unknown",
    "database": "unknown",
}


def _check_ai_status() -> str:
    try:
        from backend.ai import ai_engine  # noqa: F401
        return "operational"
    except Exception as exc:
        logger.warning("AI engine status check failed: %s", exc)
        return "unavailable"


def _check_monitoring_status() -> str:
    try:
        from backend.monitoring import collector  # noqa: F401
        return "operational"
    except Exception as exc:
        logger.warning("Monitoring status check failed: %s", exc)
        return "unavailable"


def _check_database_status() -> str:
    try:
        from backend.database.database import engine
        with engine.connect():
            return "operational"
    except Exception as exc:
        logger.warning("Database status check failed: %s", exc)
        return "unavailable"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s ...", APP_NAME, APP_VERSION)

    app_status["ai"] = _check_ai_status()
    app_status["monitoring"] = _check_monitoring_status()
    app_status["database"] = _check_database_status()

    logger.info("Startup status: %s", app_status)
    logger.info("%s startup complete.", APP_NAME)

    yield

    logger.info("Shutting down %s ...", APP_NAME)
    logger.info("%s shutdown complete.", APP_NAME)


def create_app() -> FastAPI:
    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description="AI-driven system monitoring, diagnostics, and cybersecurity platform.",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=getattr(settings, "CORS_ORIGINS", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router)

    if attack_patterns_router is not None:
        application.include_router(attack_patterns_router)
    else:
        logger.warning(
            "backend.cybersecurity.attack_patterns not available - "
            "/api/cybersecurity/attack-patterns/* endpoints will not be mounted."
        )

    if security_recommendations_router is not None:
        application.include_router(security_recommendations_router)
    else:
        logger.warning(
            "backend.cybersecurity.security_recommendations not available - "
            "/api/cybersecurity/recommendations/* endpoints will not be mounted."
        )

    if incident_logger_router is not None:
        application.include_router(incident_logger_router)
    else:
        logger.warning(
            "backend.cybersecurity.incident_logger not available - "
            "/api/cybersecurity/incidents/* endpoints will not be mounted."
        )

    if security_history_router is not None:
        application.include_router(security_history_router)
    else:
        logger.warning(
            "backend.cybersecurity.security_history not available - "
            "/api/cybersecurity/history/* endpoints will not be mounted."
        )

    if security_reports_router is not None:
        application.include_router(security_reports_router)
    else:
        logger.warning(
            "backend.cybersecurity.security_reports not available - "
            "/api/cybersecurity/reports/* endpoints will not be mounted."
        )

    @application.get("/", tags=["Root"])
    async def root():
        return {
            "application": APP_NAME,
            "version": APP_VERSION,
            "api_status": app_status["api"],
            "ai_status": app_status["ai"],
            "monitoring_status": app_status["monitoring"],
            "database_status": app_status["database"],
        }

    return application


app = create_app()