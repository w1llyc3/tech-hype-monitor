"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  CandidateSnapshot,
  HypeCandidate,
  TimelineItem,
  addHypeAlias,
  getHypeCandidate,
  getHypeSnapshots,
  getHypeTimeline,
  patchHypeCandidate,
} from "@/lib/api";

function fmt(ts: string | null | undefined) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function HypeDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const [hype, setHype] = useState<HypeCandidate | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [snapshots, setSnapshots] = useState<CandidateSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [alias, setAlias] = useState("");
  const [status, setStatus] = useState("");
  const [plain, setPlain] = useState("");

  async function load() {
    setError(null);
    try {
      const h = await getHypeCandidate(id);
      setHype(h);
      setStatus(h.candidate_status);
      setPlain(h.plain_english || "");
      setTimeline(await getHypeTimeline(id));
      setSnapshots(await getHypeSnapshots(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function onAddAlias(e: FormEvent) {
    e.preventDefault();
    if (!alias.trim()) return;
    await addHypeAlias(id, alias.trim());
    setAlias("");
    load();
  }

  async function onSave() {
    await patchHypeCandidate(id, {
      candidate_status: status,
      plain_english: plain || null,
    });
    load();
  }

  if (error) {
    return (
      <main>
        <h1>Hype Candidate</h1>
        <p className="sub">{error}</p>
      </main>
    );
  }

  if (!hype) {
    return (
      <main>
        <h1>Hype Candidate</h1>
        <p className="sub">Loading…</p>
      </main>
    );
  }

  const lastMeta = snapshots.length ? snapshots[snapshots.length - 1].metadata_json || {} : {};

  return (
    <main>
      <p className="muted">
        <Link href="/hype-radar">← Hype Radar</Link>
      </p>
      <h1>{hype.canonical_name}</h1>
      <p className="sub">Evidence trail — no token inventory in Phase 3.</p>

      <section className="grid grid-2">
        <div className="panel">
          <h2>Summary</h2>
          <p>
            <span className="muted">Status</span> {hype.candidate_status}
          </p>
          <p>
            <span className="muted">Public disclosure T0</span> {fmt(hype.public_disclosure_t0)}
          </p>
          <p>
            <span className="muted">Breakout origin T0</span> {fmt(hype.breakout_origin_t0)}
          </p>
          <p>
            <span className="muted">Aliases</span>{" "}
            {(hype.aliases || []).map((a) => a.alias).join(", ") || "—"}
          </p>
          <label>
            Plain English
            <textarea rows={3} value={plain} onChange={(e) => setPlain(e.target.value)} />
          </label>
        </div>
        <div className="panel">
          <h2>Trigger</h2>
          <p>
            <span className="muted">Origin account</span>{" "}
            {hype.origin_account ? `@${hype.origin_account}` : "—"}
          </p>
          <p>
            <span className="muted">Initial trigger</span> {hype.initial_trigger || "—"}
          </p>
          <p>
            <span className="muted">Indep. accounts / platforms</span>{" "}
            {hype.independent_accounts ?? "—"} / {hype.platforms ?? "—"}
          </p>
          <h2 style={{ marginTop: 16 }}>Actions</h2>
          <div className="filters">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {["OPEN", "WATCHING", "FORMATION", "BREAKOUT", "SATURATING", "DECLINING", "REJECTED", "CLOSED"].map(
                (s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                )
              )}
            </select>
            <button type="button" className="btn" onClick={onSave}>
              Save status / summary
            </button>
          </div>
          <form onSubmit={onAddAlias} className="inline-row" style={{ marginTop: 12 }}>
            <input placeholder="Add alias" value={alias} onChange={(e) => setAlias(e.target.value)} />
            <button className="btn" type="submit">
              Add alias
            </button>
          </form>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Tech evidence (latest snapshot)</h2>
        <div className="grid grid-4">
          <div>
            <div className="stat-label">HN stories</div>
            <div className="stat">{String(lastMeta.hn_matching_story_count ?? "—")}</div>
          </div>
          <div>
            <div className="stat-label">GitHub repos</div>
            <div className="stat">{String(lastMeta.github_repo_count ?? "—")}</div>
          </div>
          <div>
            <div className="stat-label">HF spaces</div>
            <div className="stat">{String(lastMeta.hf_space_count ?? "—")}</div>
          </div>
          <div>
            <div className="stat-label">Detachment</div>
            <div className="stat" style={{ fontSize: "1.1rem" }}>
              {String(lastMeta.source_detachment_level ?? "UNKNOWN")}
            </div>
          </div>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Account propagation</h2>
        <p className="muted">
          Distinct monitored accounts in latest snapshot: {hype.independent_accounts ?? "—"}
        </p>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Timeline</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>When</th>
                <th>Kind</th>
                <th>Title</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {timeline.map((t, i) => (
                <tr key={`${t.kind}-${t.ref_id}-${i}`}>
                  <td className="mono">{fmt(t.at)}</td>
                  <td>{t.kind}</td>
                  <td>{t.title}</td>
                  <td>{t.detail || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Snapshot history</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Checkpoint</th>
                <th>At</th>
                <th>Mentions</th>
                <th>Indep. accounts</th>
                <th>Platforms</th>
                <th>HQ amplifiers</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.id}>
                  <td>{s.checkpoint || "—"}</td>
                  <td className="mono">{fmt(s.snapshot_at)}</td>
                  <td>{s.mention_count ?? "—"}</td>
                  <td>{s.independent_account_count ?? "—"}</td>
                  <td>{s.platform_count ?? "—"}</td>
                  <td>{s.high_quality_amplifier_count ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {snapshots.length === 0 && <p className="empty">No snapshots yet. Checkpoints run on schedule.</p>}
      </section>
    </main>
  );
}
