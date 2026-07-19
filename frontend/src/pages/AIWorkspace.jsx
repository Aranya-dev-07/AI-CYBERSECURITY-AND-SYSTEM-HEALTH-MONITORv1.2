import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { motion, AnimatePresence } from "framer-motion";
import {
  PiBrainBold,
  PiHeartbeatBold,
  PiMagnifyingGlassBold,
  PiLightbulbBold,
  PiWarningCircleBold,
  PiTrendUpBold,
  PiCrystalBallBold,
  PiFileTextBold,
} from "react-icons/pi";

import AIEngine from "../ai/AIEngine.jsx";
import HealthScore from "../ai/HealthScore.jsx";
import RootCause from "../ai/RootCause.jsx";
import Recommendations from "../ai/Recommendations.jsx";
import Anomalies from "../ai/Anomalies.jsx";
import Trends from "../ai/Trends.jsx";
import Predictive from "../ai/Predictive.jsx";
import AIReports from "../ai/AIReports.jsx";

import Loader from "../components/Loader.jsx";

import { getLatestAIResult, getAIResults } from "../services/api.js";

const TABS = [
  { key: "health", label: "Health Score", icon: PiHeartbeatBold },
  { key: "anomalies", label: "Anomalies", icon: PiWarningCircleBold },
  { key: "rootCause", label: "Root Cause", icon: PiMagnifyingGlassBold },
  { key: "trends", label: "Trends", icon: PiTrendUpBold },
  { key: "predictive", label: "Predictive", icon: PiCrystalBallBold },
  { key: "recommendations", label: "Recommendations", icon: PiLightbulbBold },
  { key: "reports", label: "AI Reports", icon: PiFileTextBold },
];

/**
 * AIWorkspace — the Trinetra AI workspace. Pure orchestration: fetches
 * the latest unified AI result (and recent AI result history) and
 * distributes the relevant slice to each AI widget. No scoring,
 * detection, or explanation logic lives here — that is owned entirely
 * by the backend (ai/ai_engine.py and its subsystems).
 */
function AIWorkspace() {
  const [latestResult, setLatestResult] = useState(null);
  const [resultHistory, setResultHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("health");

  useEffect(() => {
    let isMounted = true;

    async function loadAIData() {
      setIsLoading(true);
      try {
        const [latestRes, historyRes] = await Promise.allSettled([
          getLatestAIResult(),
          getAIResults({ limit: 20 }),
        ]);

        if (!isMounted) return;

        if (latestRes.status === "fulfilled") setLatestResult(latestRes.value);
        if (historyRes.status === "fulfilled") setResultHistory(historyRes.value || []);

        if ([latestRes, historyRes].some((r) => r.status === "rejected")) {
          toast.error("Some AI data could not be loaded.");
        }
      } catch {
        if (isMounted) toast.error("Failed to load AI workspace data.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadAIData();
    return () => {
      isMounted = false;
    };
  }, []);

  const renderActiveTab = () => {
    switch (activeTab) {
      case "health":
        return (
          <HealthScore
            score={latestResult?.health_score}
            status={latestResult?.health_status}
            details={latestResult?.health_details}
          />
        );
      case "anomalies":
        return <Anomalies anomalies={latestResult?.anomalies || []} />;
      case "rootCause":
        return <RootCause rootCauses={latestResult?.root_causes || []} />;
      case "trends":
        return (
          <Trends
            trends={latestResult?.trends || []}
            resourceGrowth={latestResult?.resource_growth || []}
            processMemoryLeaks={latestResult?.process_memory_leaks || []}
          />
        );
      case "predictive":
        return <Predictive predictions={latestResult?.predictions || []} />;
      case "recommendations":
        return <Recommendations recommendations={latestResult?.recommendations || []} />;
      case "reports":
        return <AIReports results={resultHistory} />;
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          <PiBrainBold className="h-6 w-6 text-violet-400" />
          Trinetra AI
        </h2>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Explainable anomaly detection, root cause analysis, trends, and predictions.
        </p>
      </section>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader label="Loading AI workspace..." />
        </div>
      ) : (
        <>
          {/* AI Engine overview */}
          <AIEngine result={latestResult} errors={latestResult?.errors || []} />

          {/* Tab navigation */}
          <div className="flex flex-wrap gap-2 border-b border-[var(--color-border,#232733)] pb-2">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => setActiveTab(key)}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  activeTab === key
                    ? "bg-violet-600/15 text-violet-300"
                    : "text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>

          {/* Active tab content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              {renderActiveTab()}
            </motion.div>
          </AnimatePresence>
        </>
      )}
    </div>
  );
}

export default AIWorkspace;