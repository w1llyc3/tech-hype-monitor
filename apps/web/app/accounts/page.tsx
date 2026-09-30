"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AccountListItem, getAccounts } from "@/lib/api";

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function AccountsPage() {
  const [rows, setRows] = useState<AccountListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState("");
  const [tier, setTier] = useState("");
  const [priority, setPriority] = useState("");
  const [enabled, setEnabled] = useState("");
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState({ role: "", tier: "", priority: "", enabled: "", q: "" });

  useEffect(() => {
    setError(null);
    getAccounts({
      role: applied.role || undefined,
      tier: applied.tier || undefined,
      priority: applied.priority || undefined,
      enabled: applied.enabled || undefined,
      q: applied.q || undefined,
    })
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [applied]);

  const tiers = useMemo(
    () => Array.from(new Set(rows.map((r) => r.universe_tier).filter(Boolean))) as string[],
    [rows]
  );

  return (
    <main>
      <h1>Accounts</h1>
      <p className="sub">Monitored Account Universe — denominator for signal precision.</p>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="filters">
          <input placeholder="Search handle / name / role" value={q} onChange={(e) => setQ(e.target.value)} />
          <input placeholder="Role" value={role} onChange={(e) => setRole(e.target.value)} />
          <input placeholder="Tier" value={tier} onChange={(e) => setTier(e.target.value)} list="tiers" />
          <datalist id="tiers">
            {tiers.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">Priority</option>
            <option value="P0">P0</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
          </select>
          <select value={enabled} onChange={(e) => setEnabled(e.target.value)}>
            <option value="">Enabled</option>
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
          <button
            type="button"
            className="btn"
            onClick={() => setApplied({ role, tier, priority, enabled, q })}
          >
            Apply
          </button>
        </div>
      </section>

      {error && <p className="sub">Error: {error}</p>}

      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Handle</th>
                <th>Name</th>
                <th>Primary role</th>
                <th>Secondary role</th>
                <th>Tier</th>
                <th>Priority</th>
                <th>Conflict risk</th>
                <th>Tech→Crypto</th>
                <th>Enabled</th>
                <th>Last ingested</th>
                <th>30d events</th>
                <th>Open signals</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono">@{r.handle}</td>
                  <td>{r.display_name || "—"}</td>
                  <td>{r.primary_bucket || "—"}</td>
                  <td>{r.secondary_role || "—"}</td>
                  <td>{r.universe_tier || "—"}</td>
                  <td>{r.monitor_priority || "—"}</td>
                  <td>{r.conflict_risk || "—"}</td>
                  <td>{r.tech_to_crypto_relevance || "—"}</td>
                  <td>{r.enabled ? "yes" : "no"}</td>
                  <td className="mono">{fmt(r.last_ingested_post_at)}</td>
                  <td>{r.events_30d}</td>
                  <td>
                    {r.open_candidate_signals > 0 ? (
                      <Link href="/candidate-inbox">{r.open_candidate_signals}</Link>
                    ) : (
                      0
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="empty">No accounts. Import account_universe_v1.csv.</p>}
      </section>
    </main>
  );
}
