"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { HypeCandidate, getHypeCandidates } from "@/lib/api";

function fmt(ts: string | null | undefined) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

function age(ts: string | null | undefined) {
  if (!ts) return "—";
  const ms = Date.now() - new Date(ts).getTime();
  const h = Math.floor(ms / 3600000);
  if (h < 48) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export default function HypeRadarPage() {
  const [rows, setRows] = useState<HypeCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHypeCandidates()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main>
      <h1>Hype Radar</h1>
      <p className="sub">Active candidates with confirmation evidence — no opaque hype score.</p>
      {error && <p className="sub">Error: {error}</p>}

      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Status</th>
                <th>Age</th>
                <th>Origin</th>
                <th>Initial Trigger</th>
                <th>Indep. Accounts</th>
                <th>Platforms</th>
                <th>GitHub</th>
                <th>HF Spaces</th>
                <th>HN</th>
                <th>Last Snapshot</th>
                <th>Next Checkpoint</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/hype/${r.id}`}>{r.canonical_name}</Link>
                  </td>
                  <td>{r.candidate_status}</td>
                  <td>{age(r.public_disclosure_t0 || r.created_at)}</td>
                  <td>{r.origin_account ? `@${r.origin_account}` : "—"}</td>
                  <td>{r.initial_trigger || "—"}</td>
                  <td>{r.independent_accounts ?? "—"}</td>
                  <td>{r.platforms ?? "—"}</td>
                  <td>{r.github_repos ?? "—"}</td>
                  <td>{r.hf_spaces ?? "—"}</td>
                  <td>{r.hn_stories ?? "—"}</td>
                  <td className="mono">{fmt(r.last_snapshot_at)}</td>
                  <td>
                    {r.next_checkpoint || "—"}
                    {r.next_checkpoint_due_at ? (
                      <div className="muted mono">{fmt(r.next_checkpoint_due_at)}</div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="empty">No hype candidates yet. Accept a signal from the inbox.</p>}
      </section>
    </main>
  );
}
