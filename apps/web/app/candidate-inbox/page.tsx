"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  CandidateSignal,
  acceptSignal,
  attachSignal,
  getCandidateSignals,
  mergeSignal,
  rejectSignal,
} from "@/lib/api";

const REJECT_REASONS = [
  "NO_INDEPENDENT_ADOPTION",
  "TOO_GENERIC",
  "SOURCE_DEPENDENT",
  "EXTERNAL_BAIT",
  "NOT_A_TECH_OBJECT",
  "PURE_REPOST",
  "ALREADY_MAINSTREAM",
  "OTHER",
];

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function CandidateInboxPage() {
  const [rows, setRows] = useState<CandidateSignal[]>([]);
  const [state, setState] = useState("OPEN");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [attachId, setAttachId] = useState<Record<number, string>>({});
  const [mergeId, setMergeId] = useState<Record<number, string>>({});
  const [rejectReason, setRejectReason] = useState<Record<number, string>>({});

  const load = useCallback(() => {
    setError(null);
    getCandidateSignals({ state })
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [state]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(id: number, fn: () => Promise<unknown>) {
    setBusyId(id);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main>
      <h1>Candidate Inbox</h1>
      <p className="sub">Review extracted signals. Rejected rows stay forever for precision measurement.</p>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="filters">
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="OPEN">OPEN</option>
            <option value="ACCEPTED">ACCEPTED</option>
            <option value="REJECTED">REJECTED</option>
            <option value="MERGED">MERGED</option>
            <option value="IGNORED_DUPLICATE">IGNORED_DUPLICATE</option>
            <option value="">All</option>
          </select>
        </div>
      </section>

      {error && <p className="sub">Error: {error}</p>}

      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Detected</th>
                <th>Account</th>
                <th>Role</th>
                <th>Signal Type</th>
                <th>Candidate</th>
                <th>Priority</th>
                <th>Post Preview</th>
                <th>Source URL</th>
                <th>Conflict</th>
                <th>State</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{fmt(r.created_at)}</td>
                  <td>{r.account_handle ? `@${r.account_handle}` : "Unknown"}</td>
                  <td>{r.source_role || "—"}</td>
                  <td>{r.signal_type}</td>
                  <td>
                    <strong>{r.candidate_text}</strong>
                    {r.suggested_hype_ids?.length > 0 && (
                      <div className="muted">
                        Suggested:{" "}
                        {r.suggested_hype_ids.map((id) => (
                          <Link key={id} href={`/hype/${id}`}>
                            #{id}{" "}
                          </Link>
                        ))}
                      </div>
                    )}
                  </td>
                  <td>{r.initial_priority || "—"}</td>
                  <td>{r.post_preview || "—"}</td>
                  <td>
                    {r.source_url ? (
                      <a href={r.source_url} target="_blank" rel="noreferrer">
                        link
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{r.conflict_risk || "—"}</td>
                  <td>{r.state}</td>
                  <td>
                    {r.state === "OPEN" && (
                      <div className="action-stack">
                        <button
                          type="button"
                          className="btn"
                          disabled={busyId === r.id}
                          onClick={() => run(r.id, () => acceptSignal(r.id))}
                        >
                          Accept as new
                        </button>
                        <div className="inline-row">
                          <input
                            placeholder="hype id"
                            value={attachId[r.id] || ""}
                            onChange={(e) =>
                              setAttachId((m) => ({ ...m, [r.id]: e.target.value }))
                            }
                          />
                          <button
                            type="button"
                            className="btn"
                            disabled={busyId === r.id}
                            onClick={() =>
                              run(r.id, () => attachSignal(r.id, Number(attachId[r.id])))
                            }
                          >
                            Attach
                          </button>
                        </div>
                        <div className="inline-row">
                          <input
                            placeholder="into signal id"
                            value={mergeId[r.id] || ""}
                            onChange={(e) =>
                              setMergeId((m) => ({ ...m, [r.id]: e.target.value }))
                            }
                          />
                          <button
                            type="button"
                            className="btn"
                            disabled={busyId === r.id}
                            onClick={() =>
                              run(r.id, () => mergeSignal(r.id, Number(mergeId[r.id])))
                            }
                          >
                            Merge
                          </button>
                        </div>
                        <div className="inline-row">
                          <select
                            value={rejectReason[r.id] || ""}
                            onChange={(e) =>
                              setRejectReason((m) => ({ ...m, [r.id]: e.target.value }))
                            }
                          >
                            <option value="">Reject reason</option>
                            {REJECT_REASONS.map((x) => (
                              <option key={x} value={x}>
                                {x}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="btn"
                            disabled={busyId === r.id}
                            onClick={() =>
                              run(r.id, () => rejectSignal(r.id, rejectReason[r.id] || "OTHER"))
                            }
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    )}
                    {r.linked_hype_id && (
                      <Link href={`/hype/${r.linked_hype_id}`}>Hype #{r.linked_hype_id}</Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="empty">No signals for this filter.</p>}
      </section>
    </main>
  );
}
