from __future__ import annotations

import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Column, DateTime, Integer, String, Index
from sqlalchemy.orm import Session

from backend.config import settings
from backend.core import get_logger, safe_execute

from backend.cybersecurity import security_score
from backend.cybersecurity import threat_classifier

try:
    from backend.cybersecurity import attack_patterns
except ImportError:  # pragma: no cover - guarded per existing module convention
    attack_patterns = None

try:
    from backend.cybersecurity import vulnerability_scan
except ImportError:  # pragma: no cover - guarded per existing module convention
    vulnerability_scan = None

from backend.database.database import Base, engine, session_scope
from backend.api.dependencies import get_db

logger = get_logger("lavender_trinetra.cybersecurity.security_recommendations")


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
MAX_RECENT_RECOMMENDATIONS = int(getattr(settings, "SECURITY_RECOMMENDATIONS_HISTORY_SIZE", 500))
LOW_SCORE_THRESHOLD = float(getattr(settings, "SECURITY_RECOMMENDATIONS_LOW_SCORE_THRESHOLD", 75.0))
CRITICAL_SCORE_THRESHOLD = float(getattr(settings, "SECURITY_RECOMMENDATIONS_CRITICAL_SCORE_THRESHOLD", 40.0))
LOW_CONFIDENCE_THRESHOLD = float(getattr(settings, "SECURITY_RECOMMENDATIONS_LOW_CONFIDENCE_THRESHOLD", 0.55))


class RecommendationPriority:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


_PRIORITY_ORDER = {
    RecommendationPriority.LOW: 0,
    RecommendationPriority.MEDIUM: 1,
    RecommendationPriority.HIGH: 2,
    RecommendationPriority.CRITICAL: 3,
}

_SEVERITY_TO_PRIORITY = {
    "Low": RecommendationPriority.LOW,
    "Medium": RecommendationPriority.MEDIUM,
    "High": RecommendationPriority.HIGH,
    "Critical": RecommendationPriority.CRITICAL,
}


class RecommendationSource:
    SECURITY_SCORE = "security_score"
    THREAT_CLASSIFIER = "threat_classifier"
    ATTACK_PATTERNS = "attack_patterns"
    VULNERABILITY_SCAN = "vulnerability_scan"


class RecommendationCategory:
    POSTURE = "security_posture"
    THREAT_RESPONSE = "threat_response"
    ATTACK_CAMPAIGN = "attack_campaign"
    VULNERABILITY_REMEDIATION = "vulnerability_remediation"
    CLASSIFICATION_CONFIDENCE = "classification_confidence"


# ---------------------------------------------------------------------
# ORM model - defined here per the "no additional files" constraint.
# Registered against the shared Base so database.init_db() creates it
# alongside every other table (SQLite in dev, PostgreSQL in production).
# ---------------------------------------------------------------------
class SecurityRecommendationRecord(Base):
    """
    One explainable security recommendation, derived from
    security_score.py, threat_classifier.py, attack_patterns.py and
    vulnerability_scan.py output.
    """

    __tablename__ = "security_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    recommendation_id = Column(String(64), nullable=False, unique=True, index=True)

    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = Column(String(64), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    priority = Column(String(16), nullable=False, default=RecommendationPriority.LOW, index=True)

    title = Column(String(255), nullable=False, default="")
    explanation = Column(String(2000), nullable=False, default="")
    action = Column(String(1000), nullable=False, default="")

    affected_components = Column(String(500), nullable=False, default="")
    evidence = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_security_recommendations_priority_timestamp", "priority", "timestamp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<SecurityRecommendationRecord id={self.id} category={self.category} "
            f"priority={self.priority}>"
        )


# ---------------------------------------------------------------------
# Recommendation record (in-memory / API shape)
# ---------------------------------------------------------------------
@dataclass
class SecurityRecommendation:
    recommendation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = RecommendationSource.SECURITY_SCORE
    category: str = RecommendationCategory.POSTURE
    priority: str = RecommendationPriority.LOW
    title: str = ""
    explanation: str = ""
    action: str = ""
    affected_components: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "explanation": self.explanation,
            "action": self.action,
            "affected_components": self.affected_components,
            "evidence": self.evidence,
        }


# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------
_lock = threading.Lock()
_recent_recommendations: deque = deque(maxlen=MAX_RECENT_RECOMMENDATIONS)


def _record(recommendations: list[SecurityRecommendation]) -> None:
    if not recommendations:
        return
    with _lock:
        _recent_recommendations.extend(recommendations)


# ---------------------------------------------------------------------
# Per-source recommendation builders - each consumes results already
# produced upstream and interprets them into explainable, prioritized
# recommendations. No detection/scoring/scanning happens here.
# ---------------------------------------------------------------------
def _from_security_score(score_result: Optional[dict[str, Any]]) -> list[SecurityRecommendation]:
    recommendations: list[SecurityRecommendation] = []
    if not score_result:
        return recommendations

    score = score_result.get("score", 100.0)
    grade = score_result.get("grade", "Excellent")
    factors = score_result.get("factors", []) or []

    if score >= LOW_SCORE_THRESHOLD:
        return recommendations

    priority = (
        RecommendationPriority.CRITICAL
        if score < CRITICAL_SCORE_THRESHOLD
        else RecommendationPriority.HIGH
    )

    driving_factors = sorted(
        (f for f in factors if f.get("deduction", 0) > 0),
        key=lambda f: f.get("deduction", 0),
        reverse=True,
    )
    top_factors = driving_factors[:3]
    components = [f.get("category", "unknown") for f in top_factors]

    explanation = (
        f"Overall security score is {score:.1f} ({grade}), below the configured healthy "
        f"threshold of {LOW_SCORE_THRESHOLD:.0f}. The largest contributors are: "
        + "; ".join(f"{f.get('category')} ({f.get('reason', 'no detail')})" for f in top_factors)
        + "." if top_factors else f"Overall security score is {score:.1f} ({grade})."
    )
    action = (
        "Address the highest-deduction categories first: "
        + ", ".join(components) + ". Re-run the security score after remediation to confirm improvement."
        if components
        else "Review recent cycle activity and remediate the underlying causes of the score drop."
    )

    recommendations.append(
        SecurityRecommendation(
            source=RecommendationSource.SECURITY_SCORE,
            category=RecommendationCategory.POSTURE,
            priority=priority,
            title=f"Overall security posture is {grade.lower()} ({score:.1f}/100)",
            explanation=explanation,
            action=action,
            affected_components=components,
            evidence={"score": score, "grade": grade, "factors": top_factors},
        )
    )

    return recommendations


def _from_threat_classifications(classifications: list[dict[str, Any]]) -> list[SecurityRecommendation]:
    recommendations: list[SecurityRecommendation] = []
    if not classifications:
        return recommendations

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in classifications:
        by_category[c.get("category", "Unknown")].append(c)

    for category, items in by_category.items():
        top_severity = max(
            (i.get("severity", "Low") for i in items),
            key=lambda s: _PRIORITY_ORDER.get(_SEVERITY_TO_PRIORITY.get(s, RecommendationPriority.LOW), 0),
            default="Low",
        )
        priority = _SEVERITY_TO_PRIORITY.get(top_severity, RecommendationPriority.LOW)

        avg_confidence = sum(i.get("confidence", 0.0) for i in items) / len(items)
        low_confidence_note = (
            f" Average classifier confidence is {avg_confidence * 100:.0f}%, so manual triage is "
            f"recommended before acting." if avg_confidence < LOW_CONFIDENCE_THRESHOLD else ""
        )

        explanation = (
            f"{len(items)} threat(s) classified as '{category}' this cycle, with a maximum severity "
            f"of {top_severity} and average confidence of {avg_confidence * 100:.0f}%.{low_confidence_note}"
        )
        action = _threat_category_action(category)

        recommendations.append(
            SecurityRecommendation(
                source=RecommendationSource.THREAT_CLASSIFIER,
                category=RecommendationCategory.THREAT_RESPONSE,
                priority=priority,
                title=f"Respond to {len(items)} '{category}' threat(s)",
                explanation=explanation,
                action=action,
                affected_components=[category],
                evidence={"count": len(items), "average_confidence": round(avg_confidence, 2)},
            )
        )

    return recommendations


def _threat_category_action(category: str) -> str:
    return {
        "Resource Abuse": "Investigate the responsible process(es) for runaway resource consumption "
        "or cryptomining behavior; terminate or isolate if unauthorized.",
        "Network Threat": "Review flagged connections/traffic for data exfiltration or command-and-control "
        "activity; block the remote endpoint if confirmed malicious.",
        "Intrusion": "Treat as a potential active intrusion: verify the source, rotate any credentials "
        "involved, and consider isolating the affected host.",
        "Firewall Risk": "Review and correct the firewall configuration to close the identified gap.",
        "Vulnerability": "Prioritize remediation of the underlying vulnerability before it is exploited.",
    }.get(category, "Investigate the flagged activity and determine whether remediation is required.")


def _from_attack_patterns(patterns: list[dict[str, Any]]) -> list[SecurityRecommendation]:
    recommendations: list[SecurityRecommendation] = []
    if not patterns:
        return recommendations

    for pattern in patterns:
        priority = _SEVERITY_TO_PRIORITY.get(pattern.get("severity", "Low"), RecommendationPriority.LOW)
        category = pattern.get("category", "attack_pattern")
        source = pattern.get("source") or "unknown source"
        components = pattern.get("affected_components", []) or []

        explanation = pattern.get("summary") or (
            f"Attack pattern '{category}' identified involving {source}, occurring "
            f"{pattern.get('occurrence_count', 1)} time(s) across {len(components)} component(s)."
        )
        action = _pattern_category_action(category)

        recommendations.append(
            SecurityRecommendation(
                source=RecommendationSource.ATTACK_PATTERNS,
                category=RecommendationCategory.ATTACK_CAMPAIGN,
                priority=priority,
                title=pattern.get("title") or f"Attack pattern detected: {category}",
                explanation=explanation,
                action=action,
                affected_components=components,
                evidence={
                    "pattern_id": pattern.get("pattern_id"),
                    "source": source,
                    "occurrence_count": pattern.get("occurrence_count"),
                    "first_seen": pattern.get("first_seen"),
                    "last_seen": pattern.get("last_seen"),
                },
            )
        )

    return recommendations


def _pattern_category_action(category: str) -> str:
    return {
        "multi_stage_intrusion": "Block the source immediately and audit all systems it reached "
        "during the reconnaissance-to-access window.",
        "recurring_threat": "Add the source to a watchlist and consider a standing block if recurrence continues.",
        "reconnaissance_then_access": "Treat as an active attack in progress: block the source and review "
        "logs for successful access.",
        "credential_attack_campaign": "Lock or reset the targeted account(s), enforce rate limiting or "
        "account lockout, and require re-authentication.",
        "coordinated_multi_subsystem": "Investigate the source across all affected components; the "
        "coordinated nature suggests deliberate, targeted activity.",
    }.get(category, "Review the correlated events and determine an appropriate containment action.")


def _from_vulnerabilities(findings: list[dict[str, Any]]) -> list[SecurityRecommendation]:
    recommendations: list[SecurityRecommendation] = []
    if not findings:
        return recommendations

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_category[f.get("category", "unknown")].append(f)

    for category, items in by_category.items():
        top_severity = max(
            (i.get("severity", "Low") for i in items),
            key=lambda s: _PRIORITY_ORDER.get(_SEVERITY_TO_PRIORITY.get(s, RecommendationPriority.LOW), 0),
            default="Low",
        )
        priority = _SEVERITY_TO_PRIORITY.get(top_severity, RecommendationPriority.LOW)

        most_severe = max(
            items,
            key=lambda i: _PRIORITY_ORDER.get(_SEVERITY_TO_PRIORITY.get(i.get("severity", "Low"), RecommendationPriority.LOW), 0),
        )
        action = most_severe.get("recommendation") or "Remediate the underlying vulnerability."

        explanation = (
            f"{len(items)} vulnerability finding(s) in '{category}' this cycle, with a maximum "
            f"severity of {top_severity}. Most significant: {most_severe.get('title', 'see evidence')} - "
            f"{most_severe.get('description', '')}"
        )

        recommendations.append(
            SecurityRecommendation(
                source=RecommendationSource.VULNERABILITY_SCAN,
                category=RecommendationCategory.VULNERABILITY_REMEDIATION,
                priority=priority,
                title=f"Remediate {len(items)} '{category}' vulnerability finding(s)",
                explanation=explanation,
                action=action,
                affected_components=[category],
                evidence={"count": len(items), "finding_ids": [i.get("finding_id") for i in items]},
            )
        )

    return recommendations


# ---------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------
def _persist(recommendations: list[SecurityRecommendation]) -> None:
    if not recommendations:
        return
    with safe_execute("security_recommendations.persist"):
        with session_scope() as db:
            for rec in recommendations:
                record = SecurityRecommendationRecord(
                    recommendation_id=rec.recommendation_id,
                    timestamp=datetime.fromisoformat(rec.timestamp),
                    source=rec.source,
                    category=rec.category,
                    priority=rec.priority,
                    title=rec.title,
                    explanation=rec.explanation,
                    action=rec.action,
                    affected_components=", ".join(rec.affected_components),
                    evidence=str(rec.evidence),
                )
                db.add(record)
        logger.info("Persisted %d security recommendation(s) to the database.", len(recommendations))


def ensure_table_exists() -> None:
    with safe_execute("security_recommendations.ensure_table_exists"):
        Base.metadata.create_all(bind=engine, tables=[SecurityRecommendationRecord.__table__])


# ---------------------------------------------------------------------
# Public analysis API (reusable, importable functions)
# ---------------------------------------------------------------------
def generate_recommendations(
    score_result: Optional[dict[str, Any]] = None,
    classifications: Optional[list[dict[str, Any]]] = None,
    patterns: Optional[list[dict[str, Any]]] = None,
    vulnerabilities: Optional[list[dict[str, Any]]] = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    try:
        if score_result is None:
            score_result = security_score.get_latest_score()
        if classifications is None:
            classifications = threat_classifier.get_recent_classifications(limit=200)
        if patterns is None:
            patterns = attack_patterns.get_recent_patterns(limit=200) if attack_patterns is not None else []
        if vulnerabilities is None:
            vulnerabilities = (
                vulnerability_scan.get_recent_findings(limit=200) if vulnerability_scan is not None else []
            )

        recommendations: list[SecurityRecommendation] = []
        recommendations.extend(_from_security_score(score_result))
        recommendations.extend(_from_threat_classifications(classifications))
        recommendations.extend(_from_attack_patterns(patterns))
        recommendations.extend(_from_vulnerabilities(vulnerabilities))

        recommendations.sort(key=lambda r: _PRIORITY_ORDER.get(r.priority, 0), reverse=True)

        if recommendations:
            logger.warning(
                "Generated %d security recommendation(s) (priorities: %s).",
                len(recommendations),
                ", ".join(sorted({r.priority for r in recommendations})),
            )
        else:
            logger.debug("Security recommendations: nothing to recommend this cycle.")

        _record(recommendations)
        if persist:
            _persist(recommendations)

        return [r.to_dict() for r in recommendations]
    except Exception as exc:
        logger.exception("Security recommendation generation failed: %s", exc)
        return []


def get_recent_recommendations(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        items = list(_recent_recommendations)[-limit:]
    items.reverse()
    return [r.to_dict() for r in items]


def get_recommendation_summary() -> dict[str, Any]:
    with _lock:
        items = list(_recent_recommendations)
    priority_counts = {k: 0 for k in _PRIORITY_ORDER}
    source_counts: dict[str, int] = defaultdict(int)
    for r in items:
        if r.priority in priority_counts:
            priority_counts[r.priority] += 1
        source_counts[r.source] += 1
    return {
        "total": len(items),
        "priority_counts": priority_counts,
        "source_counts": dict(source_counts),
        "generated_at": datetime.utcnow().isoformat(),
    }


def get_recommendations_from_db(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        db.query(SecurityRecommendationRecord)
        .order_by(SecurityRecommendationRecord.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "recommendation_id": row.recommendation_id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "source": row.source,
            "category": row.category,
            "priority": row.priority,
            "title": row.title,
            "explanation": row.explanation,
            "action": row.action,
            "affected_components": [c.strip() for c in (row.affected_components or "").split(",") if c.strip()],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------
# Coordination facade for main.py
# ---------------------------------------------------------------------
_active = False


def start() -> None:
    global _active
    ensure_table_exists()
    _active = True
    logger.info("Security recommendations engine ready.")


def stop() -> None:
    global _active
    _active = False
    logger.info("Security recommendations engine stopped.")


def run_cycle(cycle_result: dict[str, Any]) -> dict[str, Any]:
    cycle_result["security_recommendations"] = generate_recommendations(
        score_result=cycle_result.get("security_score"),
        classifications=cycle_result.get("threat_classifications"),
        patterns=cycle_result.get("attack_patterns"),
        vulnerabilities=cycle_result.get("vulnerabilities"),
    )
    return cycle_result


def get_status() -> dict[str, Any]:
    return {
        "active": _active,
        "recommendation_summary": get_recommendation_summary(),
    }


# ---------------------------------------------------------------------
# FastAPI router - live results exposure
# ---------------------------------------------------------------------
router = APIRouter(prefix="/api/cybersecurity/recommendations", tags=["Security Recommendations"])


@router.get("/live")
async def get_live_recommendations(limit: int = Query(default=100, ge=1, le=500)):
    try:
        return generate_recommendations(persist=True)[:limit]
    except Exception as exc:
        logger.exception("Failed to compute live security recommendations")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recent")
async def get_recent(limit: int = Query(default=100, ge=1, le=500)):
    try:
        return get_recent_recommendations(limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch recent security recommendations")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
async def get_summary():
    try:
        return get_recommendation_summary()
    except Exception as exc:
        logger.exception("Failed to fetch security recommendation summary")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
async def get_history(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        return get_recommendations_from_db(db, limit=limit)
    except Exception as exc:
        logger.exception("Failed to fetch security recommendation history from the database")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status")
async def get_engine_status():
    try:
        return get_status()
    except Exception as exc:
        logger.exception("Failed to fetch security recommendations engine status")
        raise HTTPException(status_code=500, detail=str(exc))