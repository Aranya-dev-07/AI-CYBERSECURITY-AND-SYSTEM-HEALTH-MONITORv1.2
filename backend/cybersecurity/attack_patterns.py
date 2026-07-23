from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Column, DateTime, Integer, String, Index
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core import get_logger, safe_execute

try:
    from backend.cybersecurity import intrusion_detection
except ImportError:  # pragma: no cover - guarded per existing module convention
    intrusion_detection = None

# NOTE: threat_detector.py imports this module (guarded) to drive its
# Phase 3/4 cycle, so importing it back here at module level would
# create a circular import whose success depends on which module
# happens to be imported first across the app - fragile whenever a
# third module (e.g. security_history.py) imports this module before
# threat_detector.py has finished loading. get_recent_threats() is
# only ever needed inside analyze_patterns() below, so it is imported
# there, lazily, at call time instead - by then both modules are
# always fully initialized regardless of import order.

from backend.database.database import Base, engine, session_scope
from backend.api.dependencies import get_db

logger = get_logger("lavender_trinetra.cybersecurity.attack_patterns")


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
CORRELATION_WINDOW_SECONDS = float(getattr(settings, "ATTACK_PATTERN_CORRELATION_WINDOW_SECONDS", 300.0))
RECURRENCE_WINDOW_SECONDS = float(getattr(settings, "ATTACK_PATTERN_RECURRENCE_WINDOW_SECONDS", 3600.0))
RECURRENCE_THRESHOLD = int(getattr(settings, "ATTACK_PATTERN_RECURRENCE_THRESHOLD", 3))
MAX_RECENT_PATTERNS = int(getattr(settings, "ATTACK_PATTERN_HISTORY_SIZE", 500))
SOURCE_LOOKBACK_SIZE = int(getattr(settings, "ATTACK_PATTERN_SOURCE_LOOKBACK", 2000))


class PatternSeverity:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


_SEVERITY_ORDER = {
    PatternSeverity.LOW: 0,
    PatternSeverity.MEDIUM: 1,
    PatternSeverity.HIGH: 2,
    PatternSeverity.CRITICAL: 3,
}


class PatternCategory:
    MULTI_STAGE_INTRUSION = "multi_stage_intrusion"
    RECURRING_THREAT = "recurring_threat"
    RECONNAISSANCE_THEN_ACCESS = "reconnaissance_then_access"
    CREDENTIAL_ATTACK_CAMPAIGN = "credential_attack_campaign"
    COORDINATED_MULTI_SUBSYSTEM = "coordinated_multi_subsystem"


# ---------------------------------------------------------------------
# ORM model - defined here per the "no additional files" constraint.
# Registered against the shared Base so database.init_db() creates it
# alongside every other table (SQLite in dev, PostgreSQL in production).
# ---------------------------------------------------------------------
class AttackPatternRecord(Base):
    """
    One correlated attack-pattern finding, derived from threat_detector.py
    and intrusion_detection.py output. Stored as a flat, queryable row
    plus a text blob of supporting evidence so the FastAPI layer can
    render both a table view and a full explainable drill-down.
    """

    __tablename__ = "attack_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    pattern_id = Column(String(64), nullable=False, unique=True, index=True)

    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    category = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default=PatternSeverity.LOW, index=True)

    title = Column(String(255), nullable=False, default="")
    summary = Column(String(2000), nullable=False, default="")

    source = Column(String(255), nullable=True, index=True)
    affected_components = Column(String(500), nullable=False, default="")
    occurrence_count = Column(Integer, nullable=False, default=1)

    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)

    evidence = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_attack_patterns_category_timestamp", "category", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<AttackPatternRecord id={self.id} category={self.category} severity={self.severity}>"


# ---------------------------------------------------------------------
# Pattern record (in-memory / API shape)
# ---------------------------------------------------------------------
@dataclass
class AttackPattern:
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    category: str = PatternCategory.RECURRING_THREAT
    severity: str = PatternSeverity.LOW
    title: str = ""
    summary: str = ""
    source: Optional[str] = None
    affected_components: list[str] = field(default_factory=list)
    occurrence_count: int = 1
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "affected_components": self.affected_components,
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------
# State tracked across calls (for recurrence / campaign detection)
# ---------------------------------------------------------------------
_lock = threading.Lock()
_recent_patterns: deque = deque(maxlen=MAX_RECENT_PATTERNS)

_source_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=SOURCE_LOOKBACK_SIZE))


def _prune(dq: deque, window_start: datetime) -> None:
    while dq and dq[0][0] < window_start:
        dq.popleft()


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.utcnow()


def _record(patterns: list[AttackPattern]) -> None:
    if not patterns:
        return
    with _lock:
        _recent_patterns.extend(patterns)


def _extract_source(evidence: dict[str, Any]) -> Optional[str]:
    for key in ("source", "remote_address", "username", "process_name", "pid"):
        value = evidence.get(key)
        if value:
            return str(value)
    return None


def _extract_component(item: dict[str, Any]) -> str:
    return str(item.get("subsystem") or item.get("category") or "unknown")


# ---------------------------------------------------------------------
# Correlation: threats + intrusions arising close together in time
# ---------------------------------------------------------------------
def _correlate_threats_and_intrusions(
    threats: list[dict[str, Any]],
    intrusions: list[dict[str, Any]],
) -> list[AttackPattern]:
    patterns: list[AttackPattern] = []
    window = timedelta(seconds=CORRELATION_WINDOW_SECONDS)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for threat in threats or []:
        source = _extract_source(threat) or _extract_source(
            (threat.get("source_events") or [{}])[0]
        )
        if source:
            grouped[source].append({**threat, "_kind": "threat"})

    for intrusion in intrusions or []:
        source = _extract_source(intrusion) or _extract_source(intrusion.get("evidence") or {})
        if source:
            grouped[source].append({**intrusion, "_kind": "intrusion"})

    for source, items in grouped.items():
        items.sort(key=lambda i: _parse_ts(i.get("timestamp")))
        if len(items) < 2:
            continue

        cluster: list[dict[str, Any]] = [items[0]]
        for item in items[1:]:
            if _parse_ts(item.get("timestamp")) - _parse_ts(cluster[-1].get("timestamp")) <= window:
                cluster.append(item)
            else:
                if len(cluster) >= 2:
                    patterns.append(_build_correlated_pattern(source, cluster))
                cluster = [item]
        if len(cluster) >= 2:
            patterns.append(_build_correlated_pattern(source, cluster))

    return patterns


def _build_correlated_pattern(source: str, cluster: list[dict[str, Any]]) -> AttackPattern:
    components = sorted({_extract_component(i) for i in cluster})
    kinds = {i["_kind"] for i in cluster}
    severities = [i.get("severity", PatternSeverity.LOW) for i in cluster]
    top_severity = max(severities, key=lambda s: _SEVERITY_ORDER.get(s, 0), default=PatternSeverity.LOW)
    escalated = top_severity
    if len(components) > 1:
        order = [PatternSeverity.LOW, PatternSeverity.MEDIUM, PatternSeverity.HIGH, PatternSeverity.CRITICAL]
        idx = min(order.index(top_severity) + 1, len(order) - 1)
        escalated = order[idx]

    category = (
        PatternCategory.RECONNAISSANCE_THEN_ACCESS
        if "intrusion" in kinds and "threat" in kinds
        else PatternCategory.COORDINATED_MULTI_SUBSYSTEM
    )

    timestamps = [_parse_ts(i.get("timestamp")) for i in cluster]
    first_seen, last_seen = min(timestamps), max(timestamps)

    summary = (
        f"{len(cluster)} related security events involving '{source}' occurred across "
        f"{len(components)} component(s) ({', '.join(components)}) within "
        f"{(last_seen - first_seen).total_seconds():.0f} seconds, escalating from "
        f"{top_severity} to {escalated} confidence."
    )

    return AttackPattern(
        category=category,
        severity=escalated,
        title=f"Correlated activity from {source}",
        summary=summary,
        source=source,
        affected_components=components,
        occurrence_count=len(cluster),
        first_seen=first_seen.isoformat(),
        last_seen=last_seen.isoformat(),
        evidence=cluster,
    )


# ---------------------------------------------------------------------
# Recurrence: same source/behavior repeating over a longer window
# ---------------------------------------------------------------------
def _detect_recurring_behavior(
    threats: list[dict[str, Any]],
    intrusions: list[dict[str, Any]],
) -> list[AttackPattern]:
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=RECURRENCE_WINDOW_SECONDS)
    patterns: list[AttackPattern] = []

    all_items = [{**t, "_kind": "threat"} for t in (threats or [])] + [
        {**i, "_kind": "intrusion"} for i in (intrusions or [])
    ]

    touched_sources: set[str] = set()
    with _lock:
        for item in all_items:
            source = _extract_source(item) or _extract_source(item.get("evidence") or {})
            if not source:
                continue
            dq = _source_history[source]
            dq.append((_parse_ts(item.get("timestamp")), item))
            _prune(dq, window_start)
            touched_sources.add(source)

        snapshots = {source: list(_source_history[source]) for source in touched_sources}

    for source, events in snapshots.items():
        if len(events) < RECURRENCE_THRESHOLD:
            continue

        components = sorted({_extract_component(e) for _, e in events})
        credential_related = any(
            e.get("category") == "suspicious_session_behavior" or e.get("subsystem") == "session"
            for _, e in events
        )
        category = (
            PatternCategory.CREDENTIAL_ATTACK_CAMPAIGN
            if credential_related
            else PatternCategory.RECURRING_THREAT
        )

        timestamps = [ts for ts, _ in events]
        first_seen, last_seen = min(timestamps), max(timestamps)

        severity = PatternSeverity.HIGH if len(events) >= RECURRENCE_THRESHOLD * 2 else PatternSeverity.MEDIUM
        if len(components) > 2:
            severity = PatternSeverity.CRITICAL

        summary = (
            f"Source '{source}' has been implicated in {len(events)} security findings over the "
            f"past {(now - first_seen).total_seconds():.0f} seconds, spanning {len(components)} "
            f"component(s) ({', '.join(components)}). Recurrence at or above the configured "
            f"threshold of {RECURRENCE_THRESHOLD} indicates sustained, repeated attack behavior "
            f"rather than an isolated incident."
        )

        patterns.append(
            AttackPattern(
                category=category,
                severity=severity,
                title=f"Recurring attack behavior from {source}",
                summary=summary,
                source=source,
                affected_components=components,
                occurrence_count=len(events),
                first_seen=first_seen.isoformat(),
                last_seen=last_seen.isoformat(),
                evidence=[e for _, e in events],
            )
        )

    return patterns


def _detect_multi_stage_intrusion(intrusions: list[dict[str, Any]]) -> list[AttackPattern]:
    patterns: list[AttackPattern] = []
    window = timedelta(seconds=CORRELATION_WINDOW_SECONDS)

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in intrusions or []:
        source = item.get("source")
        if source:
            by_source[source].append(item)

    for source, items in by_source.items():
        scans = [i for i in items if i.get("category") == "port_scan_suspected"]
        follow_ups = [
            i for i in items
            if i.get("category") in ("repeated_connection_attempts", "suspicious_session_behavior")
        ]
        if not scans or not follow_ups:
            continue

        for scan in scans:
            scan_ts = _parse_ts(scan.get("timestamp"))
            related = [f for f in follow_ups if abs(_parse_ts(f.get("timestamp")) - scan_ts) <= window]
            if not related:
                continue

            cluster = [scan] + related
            timestamps = [_parse_ts(i.get("timestamp")) for i in cluster]
            first_seen, last_seen = min(timestamps), max(timestamps)

            patterns.append(
                AttackPattern(
                    category=PatternCategory.MULTI_STAGE_INTRUSION,
                    severity=PatternSeverity.CRITICAL,
                    title=f"Multi-stage intrusion attempt from {source}",
                    summary=(
                        f"Source '{source}' performed reconnaissance (port scan) followed by "
                        f"{len(related)} follow-on access attempt(s) within "
                        f"{(last_seen - first_seen).total_seconds():.0f} seconds, matching a "
                        f"classic scan-then-exploit attack progression."
                    ),
                    source=source,
                    affected_components=sorted({_extract_component(i) for i in cluster}),
                    occurrence_count=len(cluster),
                    first_seen=first_seen.isoformat(),
                    last_seen=last_seen.isoformat(),
                    evidence=cluster,
                )
            )

    return patterns


# ---------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------
def _persist(patterns: list[AttackPattern]) -> None:
    if not patterns:
        return
    with safe_execute("attack_patterns.persist"):
        with session_scope() as db:
            for pattern in patterns:
                record = AttackPatternRecord(
                    pattern_id=pattern.pattern_id,
                    timestamp=_parse_ts(pattern.timestamp),
                    category=pattern.category,
                    severity=pattern.severity,
                    title=pattern.title,
                    summary=pattern.summary,
                    source=pattern.source,
                    affected_components=", ".join(pattern.affected_components),
                    occurrence_count=pattern.occurrence_count,
                    first_seen=_parse_ts(pattern.first_seen) if pattern.first_seen else None,
                    last_seen=_parse_ts(pattern.last_seen) if pattern.last_seen else None,
                    evidence=str(pattern.evidence),
                )
                db.add(record)
        logger.info("Persisted %d attack pattern(s) to the database.", len(patterns))


def ensure_table_exists() -> None:
    with safe_execute("attack_patterns.ensure_table_exists"):
        Base.metadata.create_all(bind=engine, tables=[AttackPatternRecord.__table__])


# ---------------------------------------------------------------------
# Public analysis API (reusable, importable functions)
# ---------------------------------------------------------------------
def analyze_patterns(
    threats: Optional[list[dict[str, Any]]] = None,
    intrusions: Optional[list[dict[str, Any]]] = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    try:
        if threats is None:
            from backend.cybersecurity import threat_detector  # lazy: see import note above

            threats = threat_detector.get_recent_threats(limit=200)
        if intrusions is None:
            intrusions = (
                intrusion_detection.get_recent_intrusions(limit=200)
                if intrusion_detection is not None
                else []
            )

        patterns: list[AttackPattern] = []
        patterns.extend(_correlate_threats_and_intrusions(threats, intrusions))
        patterns.extend(_detect_multi_stage_intrusion(intrusions))
        patterns.extend(_detect_recurring_behavior(threats, intrusions))

        if patterns:
            logger.warning(
                "Attack pattern analysis identified %d pattern(s) (categories: %s).",
                len(patterns),
                ", ".join(sorted({p.category for p in patterns})),
            )
        else:
            logger.debug("Attack pattern analysis: no recurring or correlated patterns identified.")

        _record(patterns)
        if persist:
            _persist(patterns)

        return [p.to_dict() for p in patterns]
    except Exception as exc:
        logger.exception("Attack pattern analysis failed: %s", exc)
        return []


def get_recent_patterns(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        items = list(_recent_patterns)[-limit:]
    items.reverse()
    return [p.to_dict() for p in items]


def get_pattern_summary() -> dict[str, Any]:
    with _lock:
        items = list(_recent_patterns)
    severity_counts = {k: 0 for k in _SEVERITY_ORDER}
    category_counts: dict[str, int] = defaultdict(int)
    for p in items:
        if p.severity in severity_counts:
            severity_counts[p.severity] += 1
        category_counts[p.category] += 1
    return {
        "total": len(items),
        "severity_counts": severity_counts,
        "category_counts": dict(category_counts),
        "generated_at": datetime.utcnow().isoformat(),
    }


def get_patterns_from_db(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        db.query(AttackPatternRecord)
        .order_by(AttackPatternRecord.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "pattern_id": row.pattern_id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "category": row.category,
            "severity": row.severity,
            "title": row.title,
            "summary": row.summary,
            "source": row.source,
            "affected_components": [c.strip() for c in (row.affected_components or "").split(",") if c.strip()],
            "occurrence_count": row.occurrence_count,
            "first_seen": row.first_seen.isoformat() if row.first_seen else None,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------
# Coordination facade for main.py / threat_detector.py
# ---------------------------------------------------------------------
_active = False


def start() -> None:
    global _active
    ensure_table_exists()
    _active = True
    logger.info("Attack pattern analysis engine ready.")


def stop() -> None:
    global _active
    _active = False
    logger.info("Attack pattern analysis engine stopped.")


def run_cycle(cycle_result: dict[str, Any]) -> dict[str, Any]:
    threats = cycle_result.get("threats", [])
    intrusions = cycle_result.get("intrusions", [])
    cycle_result["attack_patterns"] = analyze_patterns(threats, intrusions)
    return cycle_result


def get_status() -> dict[str, Any]:
    return {
        "active": _active,
        "pattern_summary": get_pattern_summary(),
    }


# ---------------------------------------------------------------------
# FastAPI router - live results exposure
# ---------------------------------------------------------------------
router = APIRouter(prefix="/api/cybersecurity/attack-patterns", tags=["Attack Patterns"])


@router.get("/live")
async def get_live_attack_patterns(limit: int = Query(default=100, ge=1, le=500)):
    try:
        return analyze_patterns(persist=True)[:limit]
    except Exception as exc:
        logger.exception("Failed to compute live attack patterns")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recent")
async def get_recent_attack_patterns(limit: int = Query(default=100, ge=1, le=500)):
    try:
        return get_recent_patterns(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch recent attack patterns")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
async def get_attack_pattern_summary():
    try:
        return get_pattern_summary()
    except Exception as exc:
        logger.exception("Failed to fetch attack pattern summary")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
async def get_attack_pattern_history(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        return get_patterns_from_db(db, limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch attack pattern history from the database")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status")
async def get_attack_pattern_status():
    try:
        return get_status()
    except Exception as exc:
        logger.exception("Failed to fetch attack pattern engine status")
        raise HTTPException(status_code=500, detail=str(exc))