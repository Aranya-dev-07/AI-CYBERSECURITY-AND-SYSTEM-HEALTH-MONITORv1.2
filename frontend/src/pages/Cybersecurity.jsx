import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { PiShieldCheckeredBold } from "react-icons/pi";

import ThreatOverview from "../cybersecurity/ThreatOverview.jsx";
import Firewall from "../cybersecurity/Firewall.jsx";
import Ports from "../cybersecurity/Ports.jsx";
import Intrusion from "../cybersecurity/Intrusion.jsx";
import Vulnerabilities from "../cybersecurity/Vulnerabilities.jsx";
import SecurityScore from "../cybersecurity/SecurityScore.jsx";

import Loader from "../components/Loader.jsx";

import {
  getSecurityScore,
  getThreats,
  getFirewallStatus,
  getPortScanResults,
  getIntrusionEvents,
  getVulnerabilities,
} from "../services/api.js";

/**
 * Cybersecurity — the cybersecurity workspace. Pure orchestration:
 * fetches data for each security domain from the backend cybersecurity
 * APIs and arranges the corresponding widgets in a responsive card
 * layout. No detection, scanning, or scoring logic lives here — that
 * is owned entirely by the backend (cybersecurity/*.py).
 */
function Cybersecurity() {
  const [securityScore, setSecurityScore] = useState(null);
  const [threats, setThreats] = useState([]);
  const [firewall, setFirewall] = useState(null);
  const [ports, setPorts] = useState([]);
  const [intrusions, setIntrusions] = useState([]);
  const [vulnerabilities, setVulnerabilities] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadSecurityData() {
      setIsLoading(true);
      try {
        const results = await Promise.allSettled([
          getSecurityScore(),
          getThreats(),
          getFirewallStatus(),
          getPortScanResults(),
          getIntrusionEvents(),
          getVulnerabilities(),
        ]);

        if (!isMounted) return;

        const [
          scoreRes,
          threatsRes,
          firewallRes,
          portsRes,
          intrusionsRes,
          vulnerabilitiesRes,
        ] = results;

        if (scoreRes.status === "fulfilled") setSecurityScore(scoreRes.value);
        if (threatsRes.status === "fulfilled") setThreats(threatsRes.value || []);
        if (firewallRes.status === "fulfilled") setFirewall(firewallRes.value);
        if (portsRes.status === "fulfilled") setPorts(portsRes.value || []);
        if (intrusionsRes.status === "fulfilled") setIntrusions(intrusionsRes.value || []);
        if (vulnerabilitiesRes.status === "fulfilled") {
          setVulnerabilities(vulnerabilitiesRes.value || []);
        }

        if (results.some((r) => r.status === "rejected")) {
          toast.error("Some cybersecurity data could not be loaded.");
        }
      } catch {
        if (isMounted) toast.error("Failed to load cybersecurity data.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadSecurityData();
    return () => {
      isMounted = false;
    };
  }, []);

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

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader label="Loading cybersecurity data..." />
        </div>
      ) : (
        <>
          {/* Security score hero */}
          <SecurityScore score={securityScore} />

          {/* Threat overview */}
          <ThreatOverview threats={threats} />

          {/* Firewall + Ports */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Firewall firewall={firewall} />
            <Ports ports={ports} />
          </section>

          {/* Intrusion + Vulnerabilities */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Intrusion intrusions={intrusions} />
            <Vulnerabilities vulnerabilities={vulnerabilities} />
          </section>
        </>
      )}
    </div>
  );
}

export default Cybersecurity;