"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ReplayCaseListItem, getReplayCases } from "@/lib/api";

export default function ReplayRegistryPage() {
  const [rows, setRows] = useState<ReplayCaseListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReplayCases()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main>
      <h1>Historical Replay</h1>
      <p className="sub">
        Frozen local fixtures only. Reference pattern is evaluation-only and never feeds detection.
      </p>
      {error && <p className="sub">Error: {error}</p>}

      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Case</th>
                <th>Fixture status</th>
                <th>Reference pattern (eval-only)</th>
                <th>T0</th>
                <th>Events</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.case_id}>
                  <td>
                    <Link href={`/replay/${encodeURIComponent(r.case_id)}`}>
                      {r.display_name || r.case_id}
                    </Link>
                    <div className="muted mono">{r.case_id}</div>
                  </td>
                  <td>{r.fixture_status || "—"}</td>
                  <td>{r.reference_pattern || "—"}</td>
                  <td className="mono">{r.t0 || "—"}</td>
                  <td>{r.event_count}</td>
                  <td className="muted">{r.evaluation_notes || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="empty">No replay cases found.</p>}
      </section>
    </main>
  );
}
