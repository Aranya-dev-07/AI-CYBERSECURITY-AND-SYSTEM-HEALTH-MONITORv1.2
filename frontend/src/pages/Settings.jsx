import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  PiGearSixBold,
  PiBellRingingBold,
  PiSlidersHorizontalBold,
  PiPaintBrushBold,
  PiInfoBold,
} from "react-icons/pi";

import AlertPolicy from "../settings/AlertPolicy.jsx";
import Preferences from "../settings/Preferences.jsx";
import Appearance from "../settings/Appearance.jsx";
import About from "../settings/About.jsx";

const SECTIONS = [
  { key: "alertPolicy", label: "Alert Policy", icon: PiBellRingingBold, Component: AlertPolicy },
  { key: "preferences", label: "Preferences", icon: PiSlidersHorizontalBold, Component: Preferences },
  { key: "appearance", label: "Appearance", icon: PiPaintBrushBold, Component: Appearance },
  { key: "about", label: "About", icon: PiInfoBold, Component: About },
];

/**
 * Settings — the settings workspace. Pure orchestration: organizes
 * AlertPolicy, Preferences, Appearance, and About into clean, navigable
 * sections. No persistence, validation, or synchronization logic lives
 * here — each section owns its own local state and will call into a
 * future settings API/service independently.
 */
function Settings() {
  const [activeSection, setActiveSection] = useState("alertPolicy");

  const ActiveComponent = SECTIONS.find((s) => s.key === activeSection)?.Component;

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          <PiGearSixBold className="h-6 w-6 text-violet-400" />
          Settings
        </h2>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Alert policy, preferences, appearance, and application information.
        </p>
      </section>

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Section navigation */}
        <nav className="flex flex-row gap-1 overflow-x-auto lg:w-56 lg:flex-shrink-0 lg:flex-col lg:overflow-visible">
          {SECTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveSection(key)}
              className={`flex flex-shrink-0 items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                activeSection === key
                  ? "bg-violet-600/15 text-violet-300"
                  : "text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
              }`}
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              <span className="whitespace-nowrap">{label}</span>
            </button>
          ))}
        </nav>

        {/* Active section content */}
        <div className="min-w-0 flex-1">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeSection}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
              className="rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] p-5"
            >
              {ActiveComponent && <ActiveComponent />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default Settings;