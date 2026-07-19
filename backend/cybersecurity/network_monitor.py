from __future__ import annotations

import ipaddress
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Optional

import psutil

from backend.config import settings
from backend.core import get_logger, safe_call

logger = get_logger("lavender_trinetra.cybersecurity.network_monitor")

# ---------------------------------------------------------------------
# Configuration (falls back to sane defaults if not present in config.py)
# ---------------------------------------------------------------------

# A traffic spike is flagged when current throughput exceeds the
# rolling baseline by this multiplier.
NETWORK_SPIKE_MULTIPLIER = float(getattr(settings, "NETWORK_SPIKE_MULTIPLIER", 3.0))

# Number of prior samples kept to compute the rolling baseline
# (simple moving average - no AI/ML involved).
NETWORK_BASELINE_WINDOW = int(getattr(settings, "NETWORK_BASELINE_WINDOW_SAMPLES", 10))

# Minimum throughput (bytes/sec) before spike detection even engages,
# so idle-network noise never triggers a "spike" off a near-zero baseline.
NETWORK_MIN_BASELINE_BPS = float(getattr(settings, "NETWORK_MIN_BASELINE_BPS", 50_000.0))

# Remote ports commonly associated with malware C2, reverse shells and
# known backdoor tooling. Not a definitive signal on its own - just a
# contributing factor, mirroring process_monitor.py's watch-list approach.
WATCHED_REMOTE_PORTS = frozenset(
    getattr(
        settings,
        "NETWORK_WATCHED_REMOTE_PORTS",
        {4444, 1337, 31337, 6667, 12345, 54321, 2323, 5555},
    )
)

# Flags a possible connection flood from a single process.
MAX_CONNECTIONS_PER_PROCESS = int(getattr(settings, "NETWORK_MAX_CONNECTIONS_PER_PROCESS", 100))

# Connection states considered active/meaningful for security review.
_ACTIVE_STATUSES = frozenset({"ESTABLISHED", "SYN_SENT", "SYN_RECV"})


class NetworkRiskLevel:
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------
@dataclass
class NetworkIOSample:
    timestamp: str
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    send_bps: float = 0.0
    recv_bps: float = 0.0
    baseline_send_bps: float = 0.0
    baseline_recv_bps: float = 0.0
    is_spike: bool = False
    spike_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "packets_sent": self.packets_sent,
            "packets_recv": self.packets_recv,
            "send_bps": round(self.send_bps, 2),
            "recv_bps": round(self.recv_bps, 2),
            "baseline_send_bps": round(self.baseline_send_bps, 2),
            "baseline_recv_bps": round(self.baseline_recv_bps, 2),
            "is_spike": self.is_spike,
            "spike_reasons": self.spike_reasons,
        }


@dataclass
class ConnectionObservation:
    pid: Optional[int]
    process_name: Optional[str]
    family: str
    conn_type: str
    local_ip: Optional[str]
    local_port: Optional[int]
    remote_ip: Optional[str]
    remote_port: Optional[int]
    status: Optional[str]
    is_remote_private: Optional[bool] = None
    risk_level: str = NetworkRiskLevel.NONE
    risk_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "process_name": self.process_name,
            "family": self.family,
            "conn_type": self.conn_type,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "remote_ip": self.remote_ip,
            "remote_port": self.remote_port,
            "status": self.status,
            "is_remote_private": self.is_remote_private,
            "risk_level": self.risk_level,
            "risk_reasons": self.risk_reasons,
        }


# ---------------------------------------------------------------------
# Internal rolling state (guarded by _state_lock - scan() may be
# invoked from security_engine's background thread and/or directly
# from the FastAPI layer for on-demand reads).
# ---------------------------------------------------------------------
_state_lock = threading.Lock()
_last_counters: Optional[Any] = None
_last_sample_time: Optional[datetime] = None
_send_history: Deque[float] = deque(maxlen=NETWORK_BASELINE_WINDOW)
_recv_history: Deque[float] = deque(maxlen=NETWORK_BASELINE_WINDOW)


def _mean(values: Deque[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _addr_to_ip_port(addr: Any) -> tuple[Optional[str], Optional[int]]:
    if not addr:
        return None, None
    ip = getattr(addr, "ip", None)
    port = getattr(addr, "port", None)
    if ip is None and isinstance(addr, tuple) and len(addr) == 2:
        ip, port = addr
    return ip, port


def _is_private_ip(ip: Optional[str]) -> Optional[bool]:
    if not ip:
        return None
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return None


# ---------------------------------------------------------------------
# Traffic (network I/O) monitoring
# ---------------------------------------------------------------------
def _sample_network_io() -> NetworkIOSample:
    """
    Reads cumulative network I/O counters via psutil, converts them to
    a throughput delta (bytes/sec) since the previous call, and
    compares that throughput against a rolling baseline to flag
    unusual traffic spikes. Pure arithmetic (simple moving average) -
    no AI/ML involved, per module scope.
    """
    global _last_counters, _last_sample_time

    now = datetime.utcnow()
    sample = NetworkIOSample(timestamp=now.isoformat())

    try:
        counters = psutil.net_io_counters()
    except Exception as exc:
        logger.exception("Failed to read network I/O counters: %s", exc)
        return sample

    sample.bytes_sent = counters.bytes_sent
    sample.bytes_recv = counters.bytes_recv
    sample.packets_sent = counters.packets_sent
    sample.packets_recv = counters.packets_recv

    with _state_lock:
        if _last_counters is not None and _last_sample_time is not None:
            elapsed = (now - _last_sample_time).total_seconds()
            if elapsed > 0:
                sent_delta = max(0, counters.bytes_sent - _last_counters.bytes_sent)
                recv_delta = max(0, counters.bytes_recv - _last_counters.bytes_recv)
                sample.send_bps = sent_delta / elapsed
                sample.recv_bps = recv_delta / elapsed

                sample.baseline_send_bps = _mean(_send_history)
                sample.baseline_recv_bps = _mean(_recv_history)

                reasons: list[str] = []
                if len(_send_history) >= max(3, NETWORK_BASELINE_WINDOW // 2):
                    if (
                        sample.send_bps > NETWORK_MIN_BASELINE_BPS
                        and sample.baseline_send_bps > 0
                        and sample.send_bps > sample.baseline_send_bps * NETWORK_SPIKE_MULTIPLIER
                    ):
                        reasons.append(
                            f"Outbound traffic spike: {sample.send_bps:.0f} B/s vs "
                            f"baseline {sample.baseline_send_bps:.0f} B/s"
                        )
                    if (
                        sample.recv_bps > NETWORK_MIN_BASELINE_BPS
                        and sample.baseline_recv_bps > 0
                        and sample.recv_bps > sample.baseline_recv_bps * NETWORK_SPIKE_MULTIPLIER
                    ):
                        reasons.append(
                            f"Inbound traffic spike: {sample.recv_bps:.0f} B/s vs "
                            f"baseline {sample.baseline_recv_bps:.0f} B/s"
                        )
                sample.spike_reasons = reasons
                sample.is_spike = bool(reasons)

                _send_history.append(sample.send_bps)
                _recv_history.append(sample.recv_bps)
            else:
                # Clock hasn't advanced meaningfully; skip this sample's
                # contribution to the baseline to avoid a divide-by-zero
                # or a spurious zero-throughput data point.
                sample.baseline_send_bps = _mean(_send_history)
                sample.baseline_recv_bps = _mean(_recv_history)
        else:
            # First sample of this process's lifetime - nothing to diff
            # against yet, so no throughput/spike data is available.
            logger.debug("Network I/O baseline initializing (first sample).")

        _last_counters = counters
        _last_sample_time = now

    if sample.is_spike:
        logger.warning("Network traffic spike detected: %s", "; ".join(sample.spike_reasons))

    return sample


def get_network_io_stats() -> dict[str, Any]:
    """
    Reusable, read-only accessor for the latest network throughput
    sample (with spike detection applied). Safe to call directly from
    the FastAPI layer or other backend modules.
    """
    return _sample_network_io().to_dict()


def detect_traffic_spike() -> dict[str, Any]:
    """Explicit alias for spike-focused callers; identical to get_network_io_stats()."""
    return get_network_io_stats()


# ---------------------------------------------------------------------
# Active connection monitoring
# ---------------------------------------------------------------------
def _resolve_process_name(pid: Optional[int]) -> Optional[str]:
    if not pid:
        return None
    proc = safe_call(psutil.Process, pid)
    if proc is None:
        return None
    return safe_call(proc.name)


def _assess_connection_risk(obs: ConnectionObservation, connection_counts: dict[Optional[int], int]) -> None:
    reasons: list[str] = []

    if obs.remote_port in WATCHED_REMOTE_PORTS:
        reasons.append(f"Remote port {obs.remote_port} is on the watch list")

    if obs.status in _ACTIVE_STATUSES and obs.remote_ip and obs.is_remote_private is False:
        # Informational contributing factor only; an external ESTABLISHED
        # connection is completely normal, so this alone stays LOW.
        reasons.append(f"Active external connection to {obs.remote_ip}:{obs.remote_port}")

    count_for_pid = connection_counts.get(obs.pid, 0)
    if obs.pid is not None and count_for_pid > MAX_CONNECTIONS_PER_PROCESS:
        reasons.append(
            f"Process holds {count_for_pid} concurrent connections "
            f"(possible connection flood, threshold {MAX_CONNECTIONS_PER_PROCESS})"
        )

    if obs.pid is not None and obs.process_name is None:
        reasons.append("Connection owner process could not be resolved")

    obs.risk_reasons = reasons
    if not reasons:
        obs.risk_level = NetworkRiskLevel.NONE
    elif len(reasons) == 1:
        obs.risk_level = NetworkRiskLevel.LOW
    elif len(reasons) == 2:
        obs.risk_level = NetworkRiskLevel.MEDIUM
    else:
        obs.risk_level = NetworkRiskLevel.HIGH


def _scan_connections() -> list[ConnectionObservation]:
    try:
        raw_connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        logger.warning(
            "Insufficient permissions to enumerate network connections; "
            "skipping this cycle's connection scan."
        )
        return []
    except Exception as exc:
        logger.exception("Failed to enumerate network connections: %s", exc)
        return []

    observations: list[ConnectionObservation] = []
    connection_counts: dict[Optional[int], int] = {}

    for conn in raw_connections:
        connection_counts[conn.pid] = connection_counts.get(conn.pid, 0) + 1

    for conn in raw_connections:
        local_ip, local_port = _addr_to_ip_port(conn.laddr)
        remote_ip, remote_port = _addr_to_ip_port(conn.raddr)

        obs = ConnectionObservation(
            pid=conn.pid,
            process_name=_resolve_process_name(conn.pid),
            family=getattr(conn.family, "name", str(conn.family)),
            conn_type=getattr(conn.type, "name", str(conn.type)),
            local_ip=local_ip,
            local_port=local_port,
            remote_ip=remote_ip,
            remote_port=remote_port,
            status=conn.status,
            is_remote_private=_is_private_ip(remote_ip),
        )
        _assess_connection_risk(obs, connection_counts)
        observations.append(obs)

    suspicious = [o for o in observations if o.risk_level != NetworkRiskLevel.NONE]
    if suspicious:
        logger.warning(
            "Connection scan flagged %d suspicious connection(s) out of %d observed.",
            len(suspicious), len(observations),
        )
    else:
        logger.debug("Connection scan complete: %d connections observed, none flagged.", len(observations))

    return observations


def get_active_connections() -> list[dict[str, Any]]:
    """Reusable accessor returning all currently observed connections."""
    return [c.to_dict() for c in _scan_connections()]


def get_suspicious_connections() -> list[dict[str, Any]]:
    """Convenience wrapper returning only flagged connections."""
    return [c for c in get_active_connections() if c["risk_level"] != NetworkRiskLevel.NONE]


# ---------------------------------------------------------------------
# Entry point for security_engine.py
# ---------------------------------------------------------------------
def scan(process_rows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """
    Performs one network security scan and returns a flat list of
    event dicts, each tagged with a "type" discriminator:
        - "traffic_io"  - one throughput/spike-detection summary
        - "connection"  - one per currently observed network connection

    Called by security_engine.py once per security cycle; its return
    value is stored verbatim under cycle_result["network_connections"].
    `process_rows` is accepted for interface symmetry with
    process_monitor.scan() but is not required here - connection-to-
    process attribution is resolved independently via psutil.
    """
    events: list[dict[str, Any]] = []

    try:
        io_sample = _sample_network_io()
        events.append({"type": "traffic_io", **io_sample.to_dict()})
    except Exception as exc:
        logger.exception("Network I/O sampling failed: %s", exc)

    try:
        connections = _scan_connections()
        events.extend({"type": "connection", **c.to_dict()} for c in connections)
    except Exception as exc:
        logger.exception("Connection scan failed: %s", exc)

    return events