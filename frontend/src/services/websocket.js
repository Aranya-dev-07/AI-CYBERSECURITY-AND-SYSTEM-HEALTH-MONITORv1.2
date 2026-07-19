/**
 * websocket.js
 *
 * Centralized WebSocket Communication Service — Lavender Trinetra Platform
 * =====================================================================
 *
 * A single, reusable WebSocket manager that connects to the FastAPI
 * backend's real-time channel, auto-reconnects with exponential
 * backoff, and lets any component subscribe to specific message
 * channels without knowing about the underlying socket.
 *
 * This module contains no backend logic and no business logic — it
 * only manages the connection lifecycle and routes already-parsed
 * messages to subscribers. Interpreting/aggregating that data is the
 * responsibility of the consuming context/component (e.g.
 * SystemStatusContext.jsx, Dashboard.jsx, Monitoring.jsx).
 *
 * Compatible with:
 *   - context/SystemStatusContext.jsx (useWebSocketStatus, CHANNELS.SYSTEM_STATUS)
 *   - pages/Dashboard.jsx              (CHANNELS.DASHBOARD)
 *   - pages/Monitoring.jsx             (CHANNELS.METRICS, CHANNELS.PROCESSES)
 *   - pages/AIWorkspace.jsx            (HEALTH_SCORE, ANOMALIES, ROOT_CAUSE, TRENDS, PREDICTIONS)
 *   - pages/Cybersecurity.jsx          (CHANNELS.CYBERSECURITY)
 *   - pages/Reports.jsx / Settings.jsx (CHANNELS.SYSTEM_STATUS, general lifecycle events)
 */

import { useEffect, useRef, useState } from "react";

// =====================================================================
// CONFIGURATION
// =====================================================================

const DEFAULT_WS_URL =
  import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_JITTER_MS = 300;
const DEFAULT_MAX_RECONNECT_ATTEMPTS = Infinity;

/**
 * CHANNELS — known real-time message channels the backend may publish
 * on. Each incoming message is expected to be JSON shaped as
 * { channel: <one of these>, payload: <data>, timestamp?: string }.
 * Consumers subscribe by channel name; unrecognized channels are still
 * delivered (subscribe with the raw string) so this list is a
 * convenience, not an enforced whitelist.
 */
export const CHANNELS = Object.freeze({
  METRICS: "metrics",
  PROCESSES: "processes",
  HEALTH_SCORE: "health_score",
  ANOMALIES: "anomalies",
  ROOT_CAUSE: "root_cause",
  TRENDS: "trends",
  PREDICTIONS: "predictions",
  CYBERSECURITY: "cybersecurity",
  SYSTEM_STATUS: "system_status",
  DASHBOARD: "dashboard",
});

/** Connection lifecycle states exposed to consumers. */
export const CONNECTION_STATE = Object.freeze({
  IDLE: "idle",
  CONNECTING: "connecting",
  OPEN: "open",
  RECONNECTING: "reconnecting",
  CLOSED: "closed",
  ERROR: "error",
});

/** Lifecycle event names for on()/off() (distinct from data channels). */
const LIFECYCLE_EVENTS = Object.freeze({
  OPEN: "open",
  CLOSE: "close",
  ERROR: "error",
  RECONNECTING: "reconnecting",
  RECONNECTED: "reconnected",
  STATE_CHANGE: "state_change",
});

// =====================================================================
// LOGGING (structure-ready; swap console for a real logger if added)
// =====================================================================

const logger = {
  info: (...args) => console.info("[websocket]", ...args),
  warn: (...args) => console.warn("[websocket]", ...args),
  error: (...args) => console.error("[websocket]", ...args),
};

// =====================================================================
// WEBSOCKET MANAGER
// =====================================================================

class WebSocketManager {
  /**
   * @param {string} url - WebSocket endpoint URL.
   * @param {object} [options]
   * @param {boolean} [options.autoReconnect=true]
   * @param {number}  [options.maxReconnectAttempts=Infinity]
   * @param {number}  [options.reconnectBaseDelayMs=1000]
   * @param {number}  [options.reconnectMaxDelayMs=30000]
   */
  constructor(url, options = {}) {
    this.url = url;
    this.autoReconnect = options.autoReconnect ?? true;
    this.maxReconnectAttempts =
      options.maxReconnectAttempts ?? DEFAULT_MAX_RECONNECT_ATTEMPTS;
    this.reconnectBaseDelayMs =
      options.reconnectBaseDelayMs ?? RECONNECT_BASE_DELAY_MS;
    this.reconnectMaxDelayMs =
      options.reconnectMaxDelayMs ?? RECONNECT_MAX_DELAY_MS;

    /** @type {WebSocket|null} */
    this.socket = null;
    this.state = CONNECTION_STATE.IDLE;

    this._reconnectAttempts = 0;
    this._reconnectTimer = null;
    this._manuallyClosed = false;

    /** channel -> Set<callback> */
    this._channelSubscribers = new Map();
    /** Set<callback> — receives every parsed message regardless of channel */
    this._wildcardSubscribers = new Set();
    /** lifecycle event name -> Set<callback> */
    this._lifecycleSubscribers = new Map(
      Object.values(LIFECYCLE_EVENTS).map((event) => [event, new Set()])
    );

    /** Outbound messages queued while the socket isn't open yet. */
    this._sendQueue = [];
  }

  // -------------------------------------------------------------
  // CONNECTION LIFECYCLE
  // -------------------------------------------------------------

  /** Establish the WebSocket connection (no-op if already connecting/open). */
  connect() {
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this._manuallyClosed = false;
    this._setState(
      this._reconnectAttempts > 0
        ? CONNECTION_STATE.RECONNECTING
        : CONNECTION_STATE.CONNECTING
    );

    try {
      this.socket = new WebSocket(this.url);
    } catch (error) {
      logger.error("Failed to construct WebSocket:", error);
      this._setState(CONNECTION_STATE.ERROR);
      this._emitLifecycle(LIFECYCLE_EVENTS.ERROR, error);
      this._scheduleReconnect();
      return;
    }

    this.socket.onopen = (event) => this._handleOpen(event);
    this.socket.onmessage = (event) => this._handleMessage(event);
    this.socket.onerror = (event) => this._handleError(event);
    this.socket.onclose = (event) => this._handleClose(event);
  }

  /** Gracefully close the connection and cancel any pending reconnect. */
  disconnect() {
    this._manuallyClosed = true;
    this._clearReconnectTimer();

    if (this.socket) {
      try {
        this.socket.close(1000, "Client disconnect");
      } catch (error) {
        logger.warn("Error while closing socket:", error);
      }
    }

    this._setState(CONNECTION_STATE.CLOSED);
  }

  /** Force-close and immediately reconnect (e.g. after auth/token refresh). */
  reconnectNow() {
    this._clearReconnectTimer();
    this._reconnectAttempts = 0;
    if (this.socket) {
      this._manuallyClosed = true; // suppress the close handler's own retry
      try {
        this.socket.close();
      } catch {
        /* ignore */
      }
    }
    this._manuallyClosed = false;
    this.connect();
  }

  isConnected() {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  // -------------------------------------------------------------
  // OUTBOUND MESSAGES
  // -------------------------------------------------------------

  /**
   * Send a JSON-serializable payload to the server. Queued
   * automatically if the socket isn't open yet and flushed on connect.
   */
  send(data) {
    const message = typeof data === "string" ? data : JSON.stringify(data);

    if (this.isConnected()) {
      this.socket.send(message);
    } else {
      this._sendQueue.push(message);
    }
  }

  _flushSendQueue() {
    if (!this._sendQueue.length || !this.isConnected()) return;
    for (const message of this._sendQueue) {
      this.socket.send(message);
    }
    this._sendQueue = [];
  }

  // -------------------------------------------------------------
  // SUBSCRIPTIONS (data channels)
  // -------------------------------------------------------------

  /**
   * Subscribe to a specific channel. Returns an unsubscribe function.
   * @param {string} channel - e.g. CHANNELS.METRICS
   * @param {(payload: any, message: object) => void} callback
   */
  subscribe(channel, callback) {
    if (!this._channelSubscribers.has(channel)) {
      this._channelSubscribers.set(channel, new Set());
    }
    this._channelSubscribers.get(channel).add(callback);

    return () => this.unsubscribe(channel, callback);
  }

  unsubscribe(channel, callback) {
    this._channelSubscribers.get(channel)?.delete(callback);
  }

  /**
   * Subscribe to every incoming message regardless of channel. Useful
   * for aggregate consumers like SystemStatusContext.jsx. Returns an
   * unsubscribe function.
   */
  subscribeAll(callback) {
    this._wildcardSubscribers.add(callback);
    return () => this._wildcardSubscribers.delete(callback);
  }

  // -------------------------------------------------------------
  // LIFECYCLE EVENT SUBSCRIPTIONS
  // -------------------------------------------------------------

  /** Subscribe to a connection lifecycle event (see LIFECYCLE_EVENTS). */
  on(event, callback) {
    if (!this._lifecycleSubscribers.has(event)) {
      this._lifecycleSubscribers.set(event, new Set());
    }
    this._lifecycleSubscribers.get(event).add(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    this._lifecycleSubscribers.get(event)?.delete(callback);
  }

  _emitLifecycle(event, payload) {
    this._lifecycleSubscribers.get(event)?.forEach((callback) => {
      try {
        callback(payload);
      } catch (error) {
        logger.error(`Lifecycle subscriber for "${event}" threw:`, error);
      }
    });
  }

  // -------------------------------------------------------------
  // INTERNAL EVENT HANDLERS
  // -------------------------------------------------------------

  _handleOpen(event) {
    const wasReconnecting = this._reconnectAttempts > 0;
    this._reconnectAttempts = 0;
    this._clearReconnectTimer();
    this._setState(CONNECTION_STATE.OPEN);
    this._flushSendQueue();

    this._emitLifecycle(LIFECYCLE_EVENTS.OPEN, event);
    if (wasReconnecting) {
      this._emitLifecycle(LIFECYCLE_EVENTS.RECONNECTED, event);
    }
    logger.info("Connected:", this.url);
  }

  _handleMessage(event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      logger.warn("Received non-JSON message, ignoring:", event.data);
      return;
    }

    const channel = message?.channel ?? message?.type ?? null;
    const payload = message?.payload ?? message;

    this._wildcardSubscribers.forEach((callback) => {
      try {
        callback(payload, message);
      } catch (error) {
        logger.error("Wildcard subscriber threw:", error);
      }
    });

    if (channel && this._channelSubscribers.has(channel)) {
      this._channelSubscribers.get(channel).forEach((callback) => {
        try {
          callback(payload, message);
        } catch (error) {
          logger.error(`Subscriber for channel "${channel}" threw:`, error);
        }
      });
    }
  }

  _handleError(event) {
    logger.error("WebSocket error:", event);
    this._setState(CONNECTION_STATE.ERROR);
    this._emitLifecycle(LIFECYCLE_EVENTS.ERROR, event);
  }

  _handleClose(event) {
    this._setState(CONNECTION_STATE.CLOSED);
    this._emitLifecycle(LIFECYCLE_EVENTS.CLOSE, event);
    logger.info("Disconnected:", event.code, event.reason);

    if (!this._manuallyClosed && this.autoReconnect) {
      this._scheduleReconnect();
    }
  }

  // -------------------------------------------------------------
  // RECONNECTION
  // -------------------------------------------------------------

  _scheduleReconnect() {
    if (this._manuallyClosed) return;
    if (this._reconnectAttempts >= this.maxReconnectAttempts) {
      logger.warn("Max reconnect attempts reached; giving up.");
      return;
    }

    this._clearReconnectTimer();
    this._reconnectAttempts += 1;

    const exponentialDelay =
      this.reconnectBaseDelayMs * 2 ** (this._reconnectAttempts - 1);
    const cappedDelay = Math.min(exponentialDelay, this.reconnectMaxDelayMs);
    const jitter = Math.random() * RECONNECT_JITTER_MS;
    const delay = cappedDelay + jitter;

    this._setState(CONNECTION_STATE.RECONNECTING);
    this._emitLifecycle(LIFECYCLE_EVENTS.RECONNECTING, {
      attempt: this._reconnectAttempts,
      delayMs: Math.round(delay),
    });

    logger.info(
      `Reconnecting in ${Math.round(delay)}ms (attempt ${this._reconnectAttempts})`
    );

    this._reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  _clearReconnectTimer() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  _setState(state) {
    if (this.state === state) return;
    this.state = state;
    this._emitLifecycle(LIFECYCLE_EVENTS.STATE_CHANGE, state);
  }
}

// =====================================================================
// SINGLETON INSTANCE
// =====================================================================

let managerInstance = null;

/**
 * Return the process-wide singleton WebSocketManager, creating and
 * auto-connecting it on first access. Subsequent calls reuse the same
 * instance and connection.
 */
export function getWebSocketManager() {
  if (!managerInstance) {
    managerInstance = new WebSocketManager(DEFAULT_WS_URL, {
      autoReconnect: true,
    });
    managerInstance.connect();
  }
  return managerInstance;
}

/** Explicitly (re)connect the singleton manager. */
export function connectWebSocket() {
  getWebSocketManager().connect();
}

/** Gracefully disconnect the singleton manager. */
export function disconnectWebSocket() {
  managerInstance?.disconnect();
}

/** Send a message through the singleton manager. */
export function sendWebSocketMessage(data) {
  getWebSocketManager().send(data);
}

// =====================================================================
// REACT HOOKS
// =====================================================================

/**
 * useWebSocketChannel — subscribe a component to a specific real-time
 * channel for the lifetime of the component. Automatically connects
 * the underlying singleton on mount and unsubscribes on unmount.
 *
 * @param {string} channel - one of CHANNELS.*
 * @param {(payload: any, message: object) => void} onMessage
 * @param {{ enabled?: boolean }} [options]
 */
export function useWebSocketChannel(channel, onMessage, options = {}) {
  const { enabled = true } = options;
  const callbackRef = useRef(onMessage);
  callbackRef.current = onMessage;

  useEffect(() => {
    if (!enabled || !channel) return undefined;

    const manager = getWebSocketManager();
    const unsubscribe = manager.subscribe(channel, (payload, message) =>
      callbackRef.current?.(payload, message)
    );

    return () => unsubscribe();
  }, [channel, enabled]);
}

/**
 * useWebSocketStatus — track the live connection state of the
 * singleton WebSocket manager. Intended for SystemStatusContext.jsx
 * and any component that needs to reflect API/socket liveness.
 *
 * @returns {string} one of CONNECTION_STATE.*
 */
export function useWebSocketStatus() {
  const [state, setState] = useState(() => getWebSocketManager().state);

  useEffect(() => {
    const manager = getWebSocketManager();
    setState(manager.state);

    const unsubscribe = manager.on("state_change", (nextState) => {
      setState(nextState);
    });

    return () => unsubscribe();
  }, []);

  return state;
}

/**
 * useWebSocketAll — subscribe to every incoming message regardless of
 * channel. Intended for aggregate consumers like
 * SystemStatusContext.jsx that need to react to any live update.
 *
 * @param {(payload: any, message: object) => void} onMessage
 * @param {{ enabled?: boolean }} [options]
 */
export function useWebSocketAll(onMessage, options = {}) {
  const { enabled = true } = options;
  const callbackRef = useRef(onMessage);
  callbackRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return undefined;

    const manager = getWebSocketManager();
    const unsubscribe = manager.subscribeAll((payload, message) =>
      callbackRef.current?.(payload, message)
    );

    return () => unsubscribe();
  }, [enabled]);
}

export default {
  CHANNELS,
  CONNECTION_STATE,
  getWebSocketManager,
  connectWebSocket,
  disconnectWebSocket,
  sendWebSocketMessage,
  useWebSocketChannel,
  useWebSocketStatus,
  useWebSocketAll,
};