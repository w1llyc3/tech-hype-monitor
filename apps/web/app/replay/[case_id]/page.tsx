"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ReplayCheckpoint, getReplayCase } from "@/lib/api";

export default function ReplayCasePage({ params }: { params: { case_id: string } }) {
  const caseId = decodeURIComponent(params.case_id);
  const [rows, setRows] = useState<ReplayCheckpoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReplayCase(caseId)
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [caseId]);

  const earliest = rows.find((r) => r.suggested_formation_stage && r.suggested_formation_stage !== "SEED");
  const last = rows[rows.length - 1];

  return (
    <main>
      <p className="muted">
        <Link href="/replay">← Replay registry</Link>
      </p>
      <h1>{caseId}</h1>
      <p className="sub">Checkpoint reconstruction from frozen evidence — no live network.</p>
      {error && <p className="sub">Error: {error}</p>}

      <section className="panel">
        <h2>Summary</h2>
        <p>
          <span className="muted">Earliest non-SEED stage</span>{" "}
          {earliest?.suggested_formation_stage || "SEED / none yet"}
        </p>
        <p>
          <span className="muted">Latest suggested pattern</span>{" "}
          {last?.suggested_formation_pattern || "—"}
        </p>
        {last?.evaluation_comparison ? (
          <p>
            <span className="muted">Eval-only compare</span>{" "}
            suggested={String(last.evaluation_comparison.suggested_pattern)} vs reference=
            {String(last.evaluation_comparison.reference_pattern)} (
            {last.evaluation_comparison.match ? "match" : "mismatch"})
          </p>
        ) : null}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Checkpoints</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ckpt</th>
                <th>Evidence</th>
                <th>Origin</th>
                <th>Indep.</th>
                <th>Platforms</th>
                <th>GH</th>
                <th>HF</th>
                <th>HN</th>
                <th>Stage</th>
                <th>Direction</th>
                <th>Pattern</th>
                <th>Evidence / missing</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.checkpoint}-${r.cutoff}`}>
                  <td>{r.checkpoint}</td>
                  <td>{r.visible_evidence_count}</td>
                  <td>{r.origin_account ? `@${r.origin_account}` : "—"}</td>
                  <td>{r.independent_amplifiers}</td>
                  <td>{r.active_platforms.join(", ") || "—"}</td>
                  <td>{r.post_t0_github}</td>
                  <td>{r.post_t0_hf}</td>
                  <td>{r.hn_evidence}</td>
                  <td>{r.suggested_formation_stage}</td>
                  <td>{r.suggested_trend_direction}</td>
                  <td>
                    {r.suggested_formation_pattern}
                    {r.pattern_confidence ? (
                      <div className="muted" style={{ fontSize: "0.75rem" }}>
                        {r.pattern_confidence}
                      </div>
                    ) : null}
                  </td>
                  <td className="muted" style={{ maxWidth: 240 }}>
                    {(r.pattern_evidence || []).slice(0, 2).join(" · ") || "—"}
                    {Object.keys(r.missing_evidence || {}).length ? (
                      <div>
                        missing:{" "}
                        {Object.values(r.missing_evidence)
                          .flat()
                          .slice(0, 2)
                          .map(String)
                          .join(" · ")}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
