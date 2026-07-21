import { PiShieldCheckeredBold } from "react-icons/pi";

import SecurityOverview from "../cybersecurity/Securityoverview.jsx";
import ThreatOverview from "../cybersecurity/ThreatOverview.jsx";
import Firewall from "../cybersecurity/Firewall.jsx";
import Ports from "../cybersecurity/Ports.jsx";
import Intrusion from "../cybersecurity/Intrusion.jsx";
import Vulnerabilities from "../cybersecurity/Vulnerabilities.jsx";

/**
 * Cybersecurity — the cybersecurity workspace. Pure layout shell: each
 * widget below (SecurityOverview, ThreatOverview, Firewall, Ports,
 * Intrusion, Vulnerabilities) fetches its own data directly from
 * services/api.js and manages its own loading/refresh state - this
 * component does not fetch, hold, or pass down any security data
 * itself. No detection, scanning, or scoring logic lives here; that
 * is owned entirely by the backend (cybersecurity/*.py).
 */
function Cybersecurity() {
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          <PiShieldCheckeredBold className="h-6 w-6 text-violet-400" />
          Cybersecurity
        </h2>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Threats, firewall activity, open ports, intrusion attempts, and vulnerability posture.
        </p>
      </section>

      {/* Overall security posture */}
      <SecurityOverview />

      {/* Threat overview */}
      <ThreatOverview />

      {/* Firewall + Ports */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Firewall />
        <Ports />
      </section>

      {/* Intrusion + Vulnerabilities */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Intrusion />
        <Vulnerabilities />
      </section>
    </div>
  );
}

export default Cybersecurity;