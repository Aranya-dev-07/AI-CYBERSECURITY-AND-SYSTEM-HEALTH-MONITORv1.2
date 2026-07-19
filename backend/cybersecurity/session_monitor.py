from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import psutil

from backend.config import settings
from backend.core import get_logger

logger = get_logger("lavender_trinetra.cybersecurity.session_monitor")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------

# Usernames warranting extra attention when a login is observed. Not a
# definitive signal on its own - a contributing factor, mirroring the
# watch-list approach used across the other cybersecurity submodules.
WATCHED_USERNAMES = frozenset(
    getattr(settings, "SESSION_WATCHED_USERNAMES", {"root", "administrator", "admin"})
)

# Number of concurrent sessions for a single user before it is flagged
# as a possible shared/compromised credential.
MAX_CONCURRENT_SESSIONS_PER_USER = int(
    getattr(settings, "SESSION_MAX_CONCURRENT_PER_USER", 3)
)

# Recent session-event history kept in memory for on-demand reads (e.g.
# a future FastAPI dashboard endpoint calling get_recent_session_events()).
SESSION_EVENT_HISTORY_LIMIT = int(getattr(settings, "SESSION_EVENT_HISTORY_LIMIT", 200))


class SessionRiskLevel:
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------
@dataclass
class SessionObservation:
    username: Optional[str]
    terminal: Optional[str]
    host: Optional[str]
    login_time: Optional[str]
    pid: Optional[int]
    timestamp: str
    risk_level: str = SessionRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def key(self) -> tuple:
        # Identity used to diff this snapshot against the previous one.
        # psutil exposes no stable session id, so (user, terminal, host,
        # login_time) is the most stable practical identity - a session
        # closing and a new one opening on the same terminal will always
        # carry a different login_time.
        return (self.username, self.terminal, self.host, self.login_time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "terminal": self.terminal,
            "host": self.host,
            "login_time": self.login_time,
            "pid": self.pid,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


@dataclass
class SessionEvent:
    event_type: str  # "session_login" | "session_logout"
    username: Optional[str]
    terminal: Optional[str]
    host: Optional[str]
    login_time: Optional[str]
    timestamp: str
    risk_level: str = SessionRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "username": self.username,
            "terminal": self.terminal,
            "host": self.host,
            "login_time": self.login_time,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


# ---------------------------------------------------------------------
# Internal state (guarded by _state_lock - scan() may be invoked from
# security_engine's background thread and/or directly from the FastAPI
# layer for on-demand reads).
# ---------------------------------------------------------------------
_state_lock = threading.Lock()
_previous_sessions: dict[tuple, SessionObservation] = {}
_recent_events: list[dict[str, Any]] = []


def _format_login_time(started: Optional[float]) -> Optional[str]:
    if not started:
        return None
    try:
        return datetime.utcfromtimestamp(started).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _assess_session_risk(obs: SessionObservation, concurrent_counts: dict[Optional[str], int]) -> None:
    """
    Rule-based risk assessment. Intentionally simple and transparent -
    the AI layer (outside this module's scope) is responsible for
    deeper correlation, explanation and prioritization.
    """
    reasons: list[str] = []

    if obs.username and obs.username.lower() in WATCHED_USERNAMES:
        reasons.append(f"Login by privileged/watched account '{obs.username}'")

    if obs.host:
        reasons.append(f"Session originates from a recorded remote host: {obs.host}")

    count_for_user = concurrent_counts.get(obs.username, 0)
    if obs.username is not None and count_for_user > MAX_CONCURRENT_SESSIONS_PER_USER:
        reasons.append(
            f"User '{obs.username}' has {count_for_user} concurrent sessions "
            f"(threshold {MAX_CONCURRENT_SESSIONS_PER_USER})"
        )

    if not obs.username:
        reasons.append("Session could not be attributed to a username")

    obs.risk_reasons = reasons
    if not reasons:
        obs.risk_level = SessionRiskLevel.NONE
    elif len(reasons) == 1:
        obs.risk_level = SessionRiskLevel.LOW
    elif len(reasons) == 2:
        obs.risk_level = SessionRiskLevel.MEDIUM
    else:
        obs.risk_level = SessionRiskLevel.HIGH


# ---------------------------------------------------------------------
# Core scanning
# ---------------------------------------------------------------------
def _scan_active_sessions() -> list[SessionObservation]:
    try:
        raw_sessions = psutil.users()
    except Exception as exc:
        logger.exception("Failed to enumerate active user sessions: %s", exc)
        return []

    now_iso = datetime.utcnow().isoformat()
    observations: list[SessionObservation] = []
    concurrent_counts: dict[Optional[str], int] = {}

    for user in raw_sessions:
        username = getattr(user, "name", None)
        concurrent_counts[username] = concurrent_counts.get(username, 0) + 1

    for user in raw_sessions:
        obs = SessionObservation(
            username=getattr(user, "name", None),
            terminal=getattr(user, "terminal", None),
            host=getattr(user, "host", None) or None,
            login_time=_format_login_time(getattr(user, "started", None)),
            pid=getattr(user, "pid", None),
            timestamp=now_iso,
        )
        _assess_session_risk(obs, concurrent_counts)
        observations.append(obs)

    suspicious = [o for o in observations if o.risk_level != SessionRiskLevel.NONE]
    if suspicious:
        logger.warning(
            "Session scan flagged %d suspicious session(s) out of %d observed.",
            len(suspicious), len(observations),
        )
    else:
        logger.debug("Session scan complete: %d active sessions, none flagged.", len(observations))

    return observations


def _diff_sessions(current: list[SessionObservation]) -> tuple[list[SessionEvent], dict[tuple, SessionObservation]]:
    """
    Compares the current session snapshot against the previous one to
    detect new logins and session terminations. Must be called while
    holding _state_lock.
    """
    current_by_key = {obs.key(): obs for obs in current}
    events: list[SessionEvent] = []
    now_iso = datetime.utcnow().isoformat()

    for key, obs in current_by_key.items():
        if key not in _previous_sessions:
            events.append(
                SessionEvent(
                    event_type="session_login",
                    username=obs.username,
                    terminal=obs.terminal,
                    host=obs.host,
                    login_time=obs.login_time,
                    timestamp=now_iso,
                    risk_level=obs.risk_level,
                    risk_reasons=obs.risk_reasons,
                )
            )

    for key, prev_obs in _previous_sessions.items():
        if key not in current_by_key:
            events.append(
                SessionEvent(
                    event_type="session_logout",
                    username=prev_obs.username,
                    terminal=prev_obs.terminal,
                    host=prev_obs.host,
                    login_time=prev_obs.login_time,
                    timestamp=now_iso,
                )
            )

    if events:
        logins = sum(1 for e in events if e.event_type == "session_login")
        logouts = sum(1 for e in events if e.event_type == "session_logout")
        logger.info("Session changes detected: %d login(s), %d logout(s).", logins, logouts)

    return events, current_by_key


def _record_events(events: list[dict[str, Any]]) -> None:
    """Appends to the bounded in-memory recent-event buffer used by
    get_recent_session_events(). Must be called while holding _state_lock."""
    global _recent_events
    _recent_events.extend(events)
    if len(_recent_events) > SESSION_EVENT_HISTORY_LIMIT:
        _recent_events = _recent_events[-SESSION_EVENT_HISTORY_LIMIT:]


# ---------------------------------------------------------------------
# Reusable public accessors
# ---------------------------------------------------------------------
def get_active_sessions() -> list[dict[str, Any]]:
    """Reusable accessor returning all currently active user sessions."""
    return [obs.to_dict() for obs in _scan_active_sessions()]


def get_sessions_by_user(username: str) -> list[dict[str, Any]]:
    """Returns all currently active sessions for the given username."""
    return [obs.to_dict() for obs in _scan_active_sessions() if obs.username == username]


def get_suspicious_sessions() -> list[dict[str, Any]]:
    """Convenience wrapper returning only flagged sessions."""
    return [s for s in get_active_sessions() if s["risk_level"] != SessionRiskLevel.NONE]


def get_recent_session_events(limit: int = 50) -> list[dict[str, Any]]:
    """
    Reusable accessor for the most recent session_login/session_logout
    events, intended for a live FastAPI dashboard endpoint. Data is
    kept in memory here for fast reads; durable persistence and any
    WebSocket push to the frontend is handled downstream by
    security_logger.py via security_engine.py, not by this module.
    """
    with _state_lock:
        return list(_recent_events[-limit:])


# ---------------------------------------------------------------------
# Entry point for security_engine.py
# ---------------------------------------------------------------------
def scan(process_rows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """
    Performs one session security scan and returns a flat list of
    structured, timestamped event dicts, each tagged with a "type"
    discriminator:
        - "session_active" - one per currently active user session
        - "session_login"  - a session not present last cycle
        - "session_logout" - a session present last cycle but no longer active

    Called by security_engine.py once per security cycle; its return
    value is stored verbatim under cycle_result["sessions"] and
    forwarded to security_logger.py, which owns PostgreSQL persistence
    and any live delivery to the FastAPI dashboard. This module never
    writes to the database or a socket directly.

    `process_rows` is accepted for interface symmetry with the other
    cybersecurity submodules but is not used here.
    """
    events: list[dict[str, Any]] = []

    with _state_lock:
        global _previous_sessions
        try:
            current_sessions = _scan_active_sessions()
        except Exception as exc:
            logger.exception("Session scan failed: %s", exc)
            _record_events(events)
            return events

        try:
            diff_events, current_by_key = _diff_sessions(current_sessions)
        except Exception as exc:
            logger.exception("Session diff computation failed: %s", exc)
            diff_events, current_by_key = [], {obs.key(): obs for obs in current_sessions}

        events.extend({"type": "session_active", **obs.to_dict()} for obs in current_sessions)
        events.extend({"type": e.event_type, **e.to_dict()} for e in diff_events)

        _previous_sessions = current_by_key
        _record_events(events)

    return events