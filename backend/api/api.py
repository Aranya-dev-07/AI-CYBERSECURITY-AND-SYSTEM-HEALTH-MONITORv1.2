import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.api.routes import router as api_router

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