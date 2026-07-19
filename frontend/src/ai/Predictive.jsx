import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  PiChartLineBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiGaugeBold,
  PiTimerBold,
  PiCpuBold,
  PiNotePencilBold,
  PiLightbulbBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";
import { getPredictiveAlerts } from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;

const RISK_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };

const RISK_STYLES = {
  Critical: "border-rose-500/40 bg-rose-500/10",
  High: "border-orange-500/40 bg-orange-500/10",
  Medium: "border-amber-500/40 bg-amber-500/10",
  Low: "border-sky-500/40 bg-sky-500/10",
};

function riskStyle(riskLevel) {
  return RISK_STYLES[riskLevel] || "border-[var(--color-border,#232733)] bg-white/5";
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatProbability(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(1)}%`;
}

function formatEta(etaMinutes) {
  if (etaMinutes == null || Number.isNaN(Number(etaMinutes))) return "Unknown";
  if (etaMinutes < 1) return "< 1 min";
  if (etaMinutes < 60) return `${Math.round(etaMinutes)} min`;
  const hours = Math.floor(etaMinutes / 60);
  const mins = Math.round(etaMinutes % 60);
  return mins ? `${hours}h ${mins}m` : `${hours}h`;
}

/**
 * Predictive — displays AI predictive alerts produced by the backend
 * (ai/predictive_alerts.py -> Prediction / run_predictive_alerts),
 * fetched via GET /api/ai/predictive-alerts. Renders each prediction
 * (predicted_event, risk_level, confidence_score, eta_minutes,
 * explanation, recommended_action) as a professional alert card sorted
 * by risk level and ETA. Performs no forecasting logic itself.
 *
 * Props:
 *   predictions (array)      — optional pre-fetched predictions (e.g.
 *                               AIWorkspace's latestResult.predictions),
 *                               used as initial render / fallback.
 *   autoRefresh (bool)       — enable/disable polling. Default true.
 *   refreshInterval (number) — ms between polls. Default 15000.
 */
function Predictive({ predictions: initialPredictions = [], autoRefresh = true, refreshInterval = REFRESH_INTERVAL_MS }) {
  const [predictions, setPredictions] = useState(initialPredictions || []);
  const [isLoading, setIsLoading] = useState(!(initialPredictions && initialPredictions.length));
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchPredictions = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getPredictiveAlerts();
      if (!isMountedRef.current) return;
      setPredictions(Array.isArray(data) ? data : data?.predictions || []);
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load predictive alerts.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchPredictions({ silent: Boolean(initialPredictions && initialPredictions.length) });

    let intervalId;
    if (autoRefresh) {
      intervalId = setInterval(() => fetchPredictions({ silent: true }), refreshInterval);
    }

    return () => {
      isMountedRef.current = false;
      if (intervalId) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval, fetchPredictions]);

  const sortedPredictions = useMemo(() => {
    return (predictions || [])
      .slice()
      .sort((a, b) => {
        const riskA = a.risk_level || a.severity;
        const riskB = b.risk_level || b.severity;
        const riskDiff = (RISK_ORDER[riskA] ?? 99) - (RISK_ORDER[riskB] ?? 99);
        if (riskDiff !== 0) return riskDiff;
        const etaA = a.eta_minutes ?? Infinity;
        const etaB = b.eta_minutes ?? Infinity;
        return etaA - etaB;
      });
  }, [predictions]);

  if (isLoading) {
    return (
      <Card title="Predictive Alerts" icon={PiChartLineBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading predictive alerts..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card title="Predictive Alerts" icon={PiChartLineBold}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {sortedPredictions.length}
            </p>
            <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {sortedPredictions.length === 1 ? "issue predicted" : "issues predicted"}
            </p>
          </div>

          <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary,#64748b)]">
            {isRefreshing && (
              <span className="flex items-center gap-1">
                <PiArrowsClockwiseBold className="h-3.5 w-3.5 animate-spin" />
                Refreshing…
              </span>
            )}
            <span className="flex items-center gap-1">
              <PiClockBold className="h-3.5 w-3.5" />
              Updated {lastFetched ? lastFetched.toLocaleTimeString() : "—"}
            </span>
            <button
              type="button"
              onClick={() => fetchPredictions({ silent: true })}
              className="rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-3 text-xs text-rose-400">{error} — showing last known data.</p>
        )}
      </Card>

      {sortedPredictions.length === 0 ? (
        <Card>
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No predictive alerts at this time. The AI engine has not forecast any near-term issues.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {sortedPredictions.map((prediction) => {
            const riskLevel = prediction.risk_level || prediction.severity || "Unknown";
            const predictedEvent =
              prediction.predicted_event || prediction.predicted_issue || "Predicted issue";
            const confidence = prediction.confidence_score ?? prediction.probability;
            const key = prediction.prediction_id || prediction.id || `${predictedEvent}-${prediction.timestamp}`;

            return (
              <div key={key} className={`rounded-xl border p-4 ${riskStyle(riskLevel)}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={riskLevel} />
                    {prediction.affected_metric && (
                      <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-[var(--color-text-primary,#f1f5f9)]">
                        {prediction.affected_metric}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
                    <PiClockBold className="h-3.5 w-3.5" />
                    {formatTimestamp(prediction.timestamp || prediction.generated_at)}
                  </div>
                </div>

                <h3 className="mt-3 text-base font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                  {predictedEvent}
                </h3>

                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <p className="flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                      <PiGaugeBold className="h-3.5 w-3.5" />
                      Confidence
                    </p>
                    <p className="mt-1 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {formatProbability(confidence)}
                    </p>
                  </div>

                  <div>
                    <p className="flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                      <PiTimerBold className="h-3.5 w-3.5" />
                      ETA
                    </p>
                    <p className="mt-1 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {formatEta(prediction.eta_minutes)}
                    </p>
                  </div>

                  {prediction.responsible_process && (
                    <div>
                      <p className="flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                        <PiCpuBold className="h-3.5 w-3.5" />
                        Responsible Process
                      </p>
                      <p className="mt-1 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                        {prediction.responsible_process}
                      </p>
                    </div>
                  )}
                </div>

                {prediction.explanation && (
                  <div className="mt-3 flex items-start gap-2 rounded-lg bg-black/20 p-3">
                    <PiNotePencilBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-text-secondary,#64748b)]" />
                    <div>
                      <p className="text-xs font-medium text-[var(--color-text-secondary,#64748b)]">
                        Explanation
                      </p>
                      <p className="mt-0.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                        {prediction.explanation}
                      </p>
                    </div>
                  </div>
                )}

                {prediction.recommended_action && (
                  <div className="mt-2 flex items-start gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                    <PiLightbulbBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-400" />
                    <div>
                      <p className="text-xs font-medium text-emerald-300">Recommended Action</p>
                      <p className="mt-0.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                        {prediction.recommended_action}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default Predictive;