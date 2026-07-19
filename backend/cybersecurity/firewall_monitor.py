from __future__ import annotations

import platform
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from backend.config import settings
from backend.core import get_logger

logger = get_logger("lavender_trinetra.cybersecurity.firewall_monitor")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------

# Timeout (seconds) for any OS command used to query firewall state.
FIREWALL_COMMAND_TIMEOUT_SECONDS = float(getattr(settings, "FIREWALL_COMMAND_TIMEOUT_SECONDS", 5.0))

# Recent firewall-event history kept in memory for on-demand reads (e.g.
# a future FastAPI dashboard endpoint calling get_recent_firewall_events()).
FIREWALL_EVENT_HISTORY_LIMIT = int(getattr(settings, "FIREWALL_EVENT_HISTORY_LIMIT", 100))

_PLATFORM = platform.system()  # "Windows" | "Linux" | "Darwin" | other


class FirewallRiskLevel:
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------
@dataclass
class FirewallStateObservation:
    platform: str
    backend: Optional[str]
    available: bool
    enabled: Optional[bool]
    profiles: dict[str, bool] = field(default_factory=dict)
    detail: str = ""
    timestamp: str = ""
    risk_level: str = FirewallRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "backend": self.backend,
            "available": self.available,
            "enabled": self.enabled,
            "profiles": self.profiles,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


@dataclass
class FirewallEvent:
    event_type: str  # "firewall_status_changed" | "firewall_unavailable" | "firewall_disabled"
    previous_enabled: Optional[bool]
    current_enabled: Optional[bool]
    detail: str
    timestamp: str
    risk_level: str = FirewallRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "previous_enabled": self.previous_enabled,
            "current_enabled": self.current_enabled,
            "detail": self.detail,
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
_previous_state: Optional[FirewallStateObservation] = None
_recent_events: list[dict[str, Any]] = []


def _run_command(args: list[str]) -> Optional[str]:
    """
    Runs a read-only OS command used to query firewall state. Returns
    stdout on success, or None if the command is unavailable, times
    out, or fails. Never raises.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=FIREWALL_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        return result.stdout or ""
    except FileNotFoundError:
        logger.debug("Firewall query command not found: %s", args[0])
        return None
    except subprocess.TimeoutExpired:
        logger.warning("Firewall query command timed out: %s", " ".join(args))
        return None
    except Exception as exc:
        logger.exception("Firewall query command failed (%s): %s", " ".join(args), exc)
        return None


# ---------------------------------------------------------------------
# Platform-specific detection
# ---------------------------------------------------------------------
def _detect_windows() -> FirewallStateObservation:
    output = _run_command(["netsh", "advfirewall", "show", "allprofiles", "state"])
    if output is None:
        return FirewallStateObservation(
            platform=_PLATFORM,
            backend="windows-advfirewall",
            available=False,
            enabled=None,
            detail="netsh advfirewall command unavailable or failed",
        )

    profiles: dict[str, bool] = {}
    current_profile: Optional[str] = None
    for line in output.splitlines():
        line = line.strip()
        profile_match = re.match(r"^(Domain|Private|Public) Profile Settings:", line, re.IGNORECASE)
        if profile_match:
            current_profile = profile_match.group(1)
            continue
        if current_profile and line.lower().startswith("state"):
            state_on = "on" in line.lower().split()[-1:] or line.lower().endswith("on")
            profiles[current_profile] = state_on
            current_profile = None

    if not profiles:
        return FirewallStateObservation(
            platform=_PLATFORM,
            backend="windows-advfirewall",
            available=True,
            enabled=None,
            detail="Unable to parse firewall profile state from netsh output",
        )

    enabled = all(profiles.values())
    return FirewallStateObservation(
        platform=_PLATFORM,
        backend="windows-advfirewall",
        available=True,
        enabled=enabled,
        profiles=profiles,
        detail=f"{sum(profiles.values())}/{len(profiles)} firewall profiles enabled",
    )


def _detect_linux() -> FirewallStateObservation:
    # Preference order: ufw (most common on Debian/Ubuntu desktops and
    # servers) -> firewalld (common on RHEL/Fedora/CentOS) -> raw
    # iptables rule presence as a last-resort availability signal.
    ufw_output = _run_command(["ufw", "status"])
    if ufw_output is not None and ufw_output.strip():
        status_line = ufw_output.strip().splitlines()[0].lower()
        if "status: active" in status_line:
            return FirewallStateObservation(
                platform=_PLATFORM,
                backend="ufw",
                available=True,
                enabled=True,
                detail="ufw reports active",
            )
        if "status: inactive" in status_line:
            return FirewallStateObservation(
                platform=_PLATFORM,
                backend="ufw",
                available=True,
                enabled=False,
                detail="ufw reports inactive",
            )

    firewalld_output = _run_command(["systemctl", "is-active", "firewalld"])
    if firewalld_output is not None and firewalld_output.strip():
        state = firewalld_output.strip().lower()
        if state == "active":
            return FirewallStateObservation(
                platform=_PLATFORM,
                backend="firewalld",
                available=True,
                enabled=True,
                detail="firewalld service is active",
            )
        if state in {"inactive", "failed", "unknown"}:
            return FirewallStateObservation(
                platform=_PLATFORM,
                backend="firewalld",
                available=True,
                enabled=False,
                detail=f"firewalld service is {state}",
            )

    iptables_output = _run_command(["iptables", "-L", "-n"])
    if iptables_output is not None:
        has_rules = any(
            line.strip() and not line.startswith(("Chain", "target"))
            for line in iptables_output.splitlines()
        )
        return FirewallStateObservation(
            platform=_PLATFORM,
            backend="iptables",
            available=True,
            enabled=has_rules,
            detail="Inferred from iptables rule presence (no ufw/firewalld detected)",
        )

    return FirewallStateObservation(
        platform=_PLATFORM,
        backend=None,
        available=False,
        enabled=None,
        detail="No supported firewall backend (ufw, firewalld, iptables) detected",
    )


def _detect_macos() -> FirewallStateObservation:
    output = _run_command(
        ["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"]
    )
    if output is None:
        return FirewallStateObservation(
            platform=_PLATFORM,
            backend="macos-application-firewall",
            available=False,
            enabled=None,
            detail="socketfilterfw command unavailable or failed",
        )

    normalized = output.strip().lower()
    if "enabled" in normalized:
        return FirewallStateObservation(
            platform=_PLATFORM,
            backend="macos-application-firewall",
            available=True,
            enabled=True,
            detail=output.strip(),
        )
    if "disabled" in normalized:
        return FirewallStateObservation(
            platform=_PLATFORM,
            backend="macos-application-firewall",
            available=True,
            enabled=False,
            detail=output.strip(),
        )
    return FirewallStateObservation(
        platform=_PLATFORM,
        backend="macos-application-firewall",
        available=True,
        enabled=None,
        detail=f"Unrecognized socketfilterfw output: {output.strip()}",
    )


def _detect_firewall_state() -> FirewallStateObservation:
    try:
        if _PLATFORM == "Windows":
            obs = _detect_windows()
        elif _PLATFORM == "Linux":
            obs = _detect_linux()
        elif _PLATFORM == "Darwin":
            obs = _detect_macos()
        else:
            obs = FirewallStateObservation(
                platform=_PLATFORM,
                backend=None,
                available=False,
                enabled=None,
                detail=f"Unsupported platform for firewall detection: {_PLATFORM}",
            )
    except Exception as exc:
        logger.exception("Firewall state detection failed: %s", exc)
        obs = FirewallStateObservation(
            platform=_PLATFORM,
            backend=None,
            available=False,
            enabled=None,
            detail=f"Detection error: {exc}",
        )

    obs.timestamp = datetime.utcnow().isoformat()
    _assess_risk(obs)
    return obs


def _assess_risk(obs: FirewallStateObservation) -> None:
    """
    Rule-based risk assessment. Intentionally simple and transparent -
    the AI layer (outside this module's scope) is responsible for
    deeper correlation, explanation and prioritization.
    """
    reasons: list[str] = []

    if not obs.available:
        reasons.append("No firewall management interface could be detected on this host")
    elif obs.enabled is False:
        reasons.append(f"Firewall ({obs.backend}) is disabled")
    elif obs.enabled is None:
        reasons.append(f"Firewall ({obs.backend}) state could not be determined")
    elif obs.profiles and not all(obs.profiles.values()):
        disabled_profiles = [name for name, on in obs.profiles.items() if not on]
        reasons.append(f"Firewall profile(s) disabled: {', '.join(disabled_profiles)}")

    obs.risk_reasons = reasons
    if not obs.available or obs.enabled is False:
        obs.risk_level = FirewallRiskLevel.HIGH
    elif reasons:
        obs.risk_level = FirewallRiskLevel.MEDIUM
    else:
        obs.risk_level = FirewallRiskLevel.NONE


# ---------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------
def _diff_state(previous: Optional[FirewallStateObservation], current: FirewallStateObservation) -> list[FirewallEvent]:
    events: list[FirewallEvent] = []

    if previous is None:
        return events

    if previous.available and not current.available:
        events.append(
            FirewallEvent(
                event_type="firewall_unavailable",
                previous_enabled=previous.enabled,
                current_enabled=current.enabled,
                detail="Firewall protection became unavailable on this host",
                timestamp=current.timestamp,
                risk_level=FirewallRiskLevel.HIGH,
                risk_reasons=["Firewall management interface was previously detected but is no longer reachable"],
            )
        )
    elif previous.enabled is True and current.enabled is False:
        events.append(
            FirewallEvent(
                event_type="firewall_disabled",
                previous_enabled=previous.enabled,
                current_enabled=current.enabled,
                detail=f"Firewall ({current.backend}) was disabled",
                timestamp=current.timestamp,
                risk_level=FirewallRiskLevel.HIGH,
                risk_reasons=[f"Firewall transitioned from enabled to disabled ({current.backend})"],
            )
        )
    elif previous.enabled != current.enabled:
        events.append(
            FirewallEvent(
                event_type="firewall_status_changed",
                previous_enabled=previous.enabled,
                current_enabled=current.enabled,
                detail=f"Firewall state changed from {previous.enabled} to {current.enabled}",
                timestamp=current.timestamp,
                risk_level=current.risk_level,
                risk_reasons=current.risk_reasons,
            )
        )

    if events:
        logger.warning(
            "Firewall status change detected: %s",
            "; ".join(e.detail for e in events),
        )

    return events


def _record_events(events: list[dict[str, Any]]) -> None:
    """Appends to the bounded in-memory recent-event buffer used by
    get_recent_firewall_events(). Must be called while holding _state_lock."""
    global _recent_events
    _recent_events.extend(events)
    if len(_recent_events) > FIREWALL_EVENT_HISTORY_LIMIT:
        _recent_events = _recent_events[-FIREWALL_EVENT_HISTORY_LIMIT:]


# ---------------------------------------------------------------------
# Reusable public accessors
# ---------------------------------------------------------------------
def get_firewall_status() -> dict[str, Any]:
    """Reusable accessor returning the current firewall state snapshot."""
    return _detect_firewall_state().to_dict()


def is_firewall_enabled() -> Optional[bool]:
    """
    Convenience wrapper returning True/False, or None if the enabled
    state could not be determined on this platform.
    """
    return _detect_firewall_state().enabled


def get_recent_firewall_events(limit: int = 50) -> list[dict[str, Any]]:
    """
    Reusable accessor for the most recent firewall status-change
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
    Performs one firewall security check and returns a flat list of
    structured, timestamped event dicts, each tagged with a "type"
    discriminator:
        - "firewall_status"          - the current status snapshot
        - "firewall_status_changed"  - enabled state changed since last cycle
        - "firewall_disabled"        - firewall transitioned enabled -> disabled
        - "firewall_unavailable"     - firewall management interface stopped
                                        responding entirely

    Called by security_engine.py once per security cycle; its return
    value is stored verbatim under cycle_result["firewall_events"] and
    forwarded to security_logger.py, which owns PostgreSQL persistence
    and any live delivery to the FastAPI dashboard. This module never
    writes to the database or a socket directly.

    `process_rows` is accepted for interface symmetry with the other
    cybersecurity submodules but is not used here.
    """
    events: list[dict[str, Any]] = []

    with _state_lock:
        global _previous_state
        try:
            current_state = _detect_firewall_state()
        except Exception as exc:
            logger.exception("Firewall scan failed: %s", exc)
            _record_events(events)
            return events

        events.append({"type": "firewall_status", **current_state.to_dict()})

        try:
            diff_events = _diff_state(_previous_state, current_state)
        except Exception as exc:
            logger.exception("Firewall state diff computation failed: %s", exc)
            diff_events = []

        events.extend({"type": e.event_type, **e.to_dict()} for e in diff_events)

        _previous_state = current_state
        _record_events(events)

    if current_state.risk_level != FirewallRiskLevel.NONE:
        logger.warning(
            "Firewall scan flagged risk_level=%s: %s",
            current_state.risk_level, "; ".join(current_state.risk_reasons),
        )
    else:
        logger.debug("Firewall scan complete: enabled=%s, backend=%s", current_state.enabled, current_state.backend)

    return events