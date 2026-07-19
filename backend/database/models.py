"""
models.py

SQLAlchemy ORM Models — Lavender Trinetra Platform
=====================================================================

Defines the relational schema backing the monitoring platform:

    - TestRun         one row per monitoring session
    - SystemMetric     one row per collected system metrics sample
                        (mirrors backend/data/system_metrics.csv)
    - SystemProcess    one row per collected top-process sample
                        (mirrors backend/data/system_processes.csv)

SystemMetric and SystemProcess each optionally belong to a TestRun via
a foreign key, allowing a session's full metric/process history to be
queried through TestRun.metrics / TestRun.processes.

Integrates with:
    - database/database.py  (declares against the shared Base; tables
                              created via init_db())
    - database/crud.py      (performs queries/inserts against these models)
    - api/api.py             (schemas.py maps these to Pydantic response models)

Author: Lavender Trinetra Backend Engineering
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.orm import relationship

# NOTE: `sqlalchemy.dialects.postgresql` ships inside SQLAlchemy itself and
# always imports successfully, even without a PostgreSQL driver installed -
# so a bare `try/except ImportError` around this import never actually
# falls back. Use a dialect-aware variant type instead: it renders as
# JSONB on PostgreSQL and as plain JSON on every other backend (SQLite,
# MySQL, etc.) at DDL-compile time, based on the engine actually in use.
from sqlalchemy.dialects.postgresql import JSONB

_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

try:
    from .database import Base
except ImportError:  # pragma: no cover - fallback for non-package execution
    from database import Base  # type: ignore


# =====================================================================
# TEST RUN
# =====================================================================

class TestRun(Base):
    """Represents a single monitoring session, from start to stop."""

    __tablename__ = "test_run"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True, comment="Session duration in seconds")
    total_alerts = Column(Integer, nullable=False, default=0)

    metrics = relationship(
        "SystemMetric",
        back_populates="test_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    processes = relationship(
        "SystemProcess",
        back_populates="test_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ai_results = relationship(
        "AIResult",
        back_populates="test_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<TestRun id={self.id} start_time={self.start_time} "
            f"end_time={self.end_time} total_alerts={self.total_alerts}>"
        )


# =====================================================================
# SYSTEM METRICS
# =====================================================================

class SystemMetric(Base):
    """
    One system-level metrics sample, mirroring the columns written to
    backend/data/system_metrics.csv by monitoring/metrics.py.
    """

    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    test_run_id = Column(
        Integer,
        ForeignKey("test_run.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    cpu_usage = Column(Float, nullable=False, default=0.0)
    ram_usage = Column(Float, nullable=False, default=0.0)
    disk_usage = Column(Float, nullable=False, default=0.0)
    disk_read_bps = Column(Float, nullable=False, default=0.0)
    disk_write_bps = Column(Float, nullable=False, default=0.0)
    network_in_bps = Column(Float, nullable=False, default=0.0)
    network_out_bps = Column(Float, nullable=False, default=0.0)

    test_run = relationship("TestRun", back_populates="metrics")

    __table_args__ = (
        Index("ix_system_metrics_test_run_timestamp", "test_run_id", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<SystemMetric id={self.id} timestamp={self.timestamp} "
            f"cpu={self.cpu_usage} ram={self.ram_usage} disk={self.disk_usage}>"
        )


# =====================================================================
# SYSTEM PROCESSES
# =====================================================================

class SystemProcess(Base):
    """
    One process resource-usage sample, mirroring the columns written to
    backend/data/system_processes.csv by monitoring/metrics.py.
    """

    __tablename__ = "system_processes"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    test_run_id = Column(
        Integer,
        ForeignKey("test_run.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    pid = Column(Integer, nullable=True)
    name = Column(String(255), nullable=False, default="unknown", index=True)
    cpu_percent = Column(Float, nullable=False, default=0.0)
    memory_percent = Column(Float, nullable=False, default=0.0)

    test_run = relationship("TestRun", back_populates="processes")

    __table_args__ = (
        Index("ix_system_processes_test_run_timestamp", "test_run_id", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<SystemProcess id={self.id} name={self.name} "
            f"cpu={self.cpu_percent} mem={self.memory_percent}>"
        )


# =====================================================================
# AI RESULTS
# =====================================================================

class AIResult(Base):
    """
    One unified AI orchestration cycle result, mirroring
    ai.ai_engine.AIEngineResult. Stored as structured JSON/JSONB
    columns so the full explainable output (health score, anomalies,
    root causes, trends, predictions, recommendations) is preserved
    without needing a separate table per AI subsystem.
    """

    __tablename__ = "ai_results"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    test_run_id = Column(
        Integer,
        ForeignKey("test_run.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    health_score = Column(Float, nullable=True)
    health_status = Column(String(50), nullable=True)

    health_details = Column(_JSON_TYPE, nullable=True)
    anomalies = Column(_JSON_TYPE, nullable=True)
    root_causes = Column(_JSON_TYPE, nullable=True)
    trends = Column(_JSON_TYPE, nullable=True)
    resource_growth = Column(_JSON_TYPE, nullable=True)
    process_memory_leaks = Column(_JSON_TYPE, nullable=True)
    predictions = Column(_JSON_TYPE, nullable=True)
    recommendations = Column(_JSON_TYPE, nullable=True)
    errors = Column(_JSON_TYPE, nullable=True)

    test_run = relationship("TestRun", back_populates="ai_results")

    __table_args__ = (
        Index("ix_ai_results_test_run_timestamp", "test_run_id", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<AIResult id={self.id} timestamp={self.timestamp} "
            f"health_status={self.health_status}>"
        )


__all__ = [
    "TestRun",
    "SystemMetric",
    "SystemProcess",
    "AIResult",
]