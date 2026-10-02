"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { HypeCandidate, getHypeCandidates } from "@/lib/api";

const GROUPS = ["Emerging", "Accelerating", "Broadening", "Needs Review", "Cooling"] as const;

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

function groupOf(r: HypeCandidate) {
  return r.radar_group || "Needs Review";
}

function sortKey(r: HypeCandidate) {
  const stageRank: Record<string, number> = {
    BREAKOUT: 5,
    FORMATION: 4,
    WATCHING: 3,
    SEED: 2,
    SATURATING: 1,
    DECLINING: 0,
    CLOSED: -1,
  };
  const stage = stageRank[r.formation_stage || ""] ?? 0;
  const t = r.last_snapshot_at || r.updated_at || r.created_at;
  return stage * 1e15 + new Date(t).getTime();
}

export default function HypeRadarPage() {
  const [rows, setRows] = useState<HypeCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHypeCandidates()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  const grouped = useMemo(() => {
    const map: Record<string, HypeCandidate[]> = {};
    for (const g of GROUPS) map[g] = [];
    for (const r of rows) {
      const g = groupOf(r);
      if (!map[g]) map[g] = [];
      map[g].push(r);
    }
    for (const g of Object.keys(map)) {
      map[g].sort((a, b) => sortKey(b) - sortKey(a));
    }
    return map;
  }, [rows]);

  return (
    <main>
      <h1>Daily Hype Radar</h1>
      <p className="sub">
        What is emerging and why — stage, direction, and pattern stay separate. No opaque hype score.
      </p>
      {error && <p className="sub">Error: {error}</p>}

      {GROUPS.map((group) => (
        <section className="panel" key={group} style={{ marginTop: 16 }}>
          <h2>
            {group}{" "}
            <span className="muted" style={{ fontWeight: 400, fontSize: "0.9rem" }}>
              ({grouped[group]?.length || 0})
            </span>
          </h2>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Stage</th>
                  <th>Direction</th>
                  <th>Pattern</th>
                  <th>Age</th>
                  <th>Origin</th>
                  <th>Indep.</th>
                  <th>Platforms</th>
                  <th>GH new</th>
                  <th>HF Spaces</th>
                  <th>HN</th>
                  <th>Last change</th>
                  <th>Next ckpt</th>
                  <th>Why moving</th>
                  <th>Missing</th>
                </tr>
              </thead>
              <tbody>
                {(grouped[group] || []).map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link href={`/hype/${r.id}`}>{r.canonical_name}</Link>
                      {(r.review_flags || []).length > 0 ? (
                        <div className="muted" style={{ fontSize: "0.75rem" }}>
                          {(r.review_flags || []).join(" · ")}
                        </div>
                      ) : null}
                    </td>
                    <td>{r.formation_stage || r.candidate_status}</td>
                    <td>{r.trend_direction || "—"}</td>
                    <td>
                      {r.formation_pattern_suggested || r.formation_pattern || "—"}
                      {r.pattern_confidence ? (
                        <div className="muted" style={{ fontSize: "0.75rem" }}>
                          {r.pattern_confidence}
                        </div>
                      ) : null}
                    </td>
                    <td>{age(r.public_disclosure_t0 || r.created_at)}</td>
                    <td>{r.origin_account ? `@${r.origin_account}` : "—"}</td>
                    <td>{r.independent_accounts ?? "—"}</td>
                    <td>{r.platforms ?? "—"}</td>
                    <td>{r.github_repos ?? "—"}</td>
                    <td>{r.hf_spaces ?? "—"}</td>
                    <td>{r.hn_stories ?? "—"}</td>
                    <td className="muted" style={{ maxWidth: 160 }}>
                      {r.last_meaningful_change || "—"}
                    </td>
                    <td>
                      {r.next_checkpoint || "—"}
                      {r.next_checkpoint_due_at ? (
                        <div className="muted mono">{fmt(r.next_checkpoint_due_at)}</div>
                      ) : null}
                    </td>
                    <td className="muted" style={{ maxWidth: 200 }}>
                      {(r.why_moving || []).slice(0, 2).join(" · ") || "—"}
                    </td>
                    <td className="muted" style={{ maxWidth: 160 }}>
                      {(r.missing_evidence || []).slice(0, 2).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(grouped[group] || []).length === 0 && (
            <p className="empty">No candidates in this group.</p>
          )}
        </section>
      ))}
    </main>
  );
}
