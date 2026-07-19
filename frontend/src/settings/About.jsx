import {
  PiEyeBold,
  PiInfoBold,
  PiTagBold,
  PiStackBold,
  PiHardDrivesBold,
  PiBrainBold,
  PiDatabaseBold,
  PiPlugsBold,
  PiScrollBold,
  PiUsersBold,
  PiGithubLogoBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";

const PROJECT_NAME = "Lavender Trinetra";
const PROJECT_VERSION = "v1.1";
const TAGLINE = "Observe. Learn. Protect.";

const DESCRIPTION =
  "Lavender Trinetra is an AI-driven system health and cybersecurity monitoring " +
  "platform. It continuously observes system resources and processes, applies " +
  "machine learning to detect anomalies, forecast issues, and surface root " +
  "causes, and pairs that with real-time threat and vulnerability detection — " +
  "giving a unified view of both system health and security posture.";

const TECH_STACK = [
  { category: "Backend", items: ["Python", "FastAPI", "psutil"] },
  { category: "Database", items: ["PostgreSQL", "SQLAlchemy"] },
  { category: "AI / ML", items: ["Anomaly Detection", "Trend Analysis", "Predictive Alerts"] },
  { category: "Frontend", items: ["React", "Vite", "Tailwind CSS", "Recharts"] },
];

/**
 * About — the About panel for Lavender Trinetra. Displays static
 * project metadata (name, version, tagline, description, stack,
 * license, developer placeholder) alongside live backend service
 * status sourced from SystemStatusContext, which in turn is populated
 * via services/api.js (GET /api/status). Implements no health
 * checking or status computation itself.
 */
function About() {
  const { status, isLoading } = useSystemStatus();

  const statusRows = [
    { key: "api", label: "API Status", icon: PiPlugsBold, value: status?.api },
    { key: "ai", label: "AI Engine Status", icon: PiBrainBold, value: status?.aiEngine },
    { key: "database", label: "Database Status", icon: PiDatabaseBold, value: status?.database },
    { key: "monitoring", label: "Backend Status", icon: PiHardDrivesBold, value: status?.monitoring },
  ];

  return (
    <div className="flex flex-col gap-5">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
        <PiInfoBold className="h-5 w-5 text-violet-400" />
        About
      </h3>

      {/* Hero */}
      <Card>
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-violet-600/15 text-violet-300">
              <PiEyeBold className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                {PROJECT_NAME}
              </p>
              <p className="text-sm italic text-[var(--color-text-secondary,#94a3b8)]">
                "{TAGLINE}"
              </p>
            </div>
          </div>
          <span className="flex items-center gap-1.5 rounded-full border border-[var(--color-border,#232733)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
            <PiTagBold className="h-3.5 w-3.5" />
            {PROJECT_VERSION}
          </span>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-[var(--color-text-secondary,#94a3b8)]">
          {DESCRIPTION}
        </p>
      </Card>

      {/* Technology stack */}
      <Card title="Technology Stack" icon={PiStackBold}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {TECH_STACK.map(({ category, items }) => (
            <div key={category}>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]">
                {category}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {items.map((item) => (
                  <span
                    key={item}
                    className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-[var(--color-text-primary,#f1f5f9)]"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Live status */}
      <Card title="System Status">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {statusRows.map(({ key, label, icon: Icon, value }) => (
            <div
              key={key}
              className="flex items-center justify-between rounded-lg border border-[var(--color-border,#232733)] px-3 py-2.5"
            >
              <span className="flex items-center gap-2 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                <Icon className="h-4 w-4 text-[var(--color-text-secondary,#64748b)]" />
                {label}
              </span>
              <StatusBadge status={isLoading ? "Loading" : value || "Unknown"} />
            </div>
          ))}
        </div>
      </Card>

      {/* License */}
      <Card title="License" icon={PiScrollBold}>
        <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">MIT License</p>
        <p className="mt-1 text-xs text-[var(--color-text-secondary,#64748b)]">
          Free to use, modify, and distribute, provided the original copyright and
          permission notice are included in all copies or substantial portions of the
          software.
        </p>
      </Card>

      {/* Developer info placeholder */}
      <Card title="Developer Information" icon={PiUsersBold}>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-white/5 text-[var(--color-text-secondary,#64748b)]">
            <PiGithubLogoBold className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
              Developer information coming soon
            </p>
            <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
              Contributor and contact details will be listed here in a future update.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default About;