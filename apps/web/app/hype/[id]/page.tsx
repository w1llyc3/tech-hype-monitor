"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  CandidateSnapshot,
  HypeCandidate,
  SnapshotSchedule,
  TimelineItem,
  TrendAssessment,
  addHypeAlias,
  exportResearchBundle,
  getHypeCandidate,
  getHypeSchedule,
  getHypeSnapshots,
  getHypeTimeline,
  getTrendAssessments,
  patchHypeCandidate,
  postTrendOverride,
} from "@/lib/api";

function fmt(ts: string | null | undefined) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

function statusLabel(row: SnapshotSchedule) {
  if (row.status === "SKIPPED") {
    return `SKIPPED — ${row.skip_reason || "UNKNOWN"}`;
  }
  return row.status;
}

const STAGES = [
  "SEED",
  "WATCHING",
  "FORMATION",
  "BREAKOUT",
  "SATURATING",
  "DECLINING",
  "CLOSED",
];
const PATTERNS = [
  "NAMING_FIRST",
  "OBJECT_FIRST",
  "EMBEDDED_OBJECT",
  "REFRAMING",
  "CAPABILITY_LED",
  "CATEGORY_CONVERGENCE",
  "REACTIVATED_TERM",
  "PROOF_LED",
  "VISUAL_PROOF_LED",
  "LORE_NATIVE",
  "UNKNOWN",
];

export default function HypeDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const [hype, setHype] = useState<HypeCandidate | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [snapshots, setSnapshots] = useState<CandidateSnapshot[]>([]);
  const [schedule, setSchedule] = useState<SnapshotSchedule[]>([]);
  const [assessments, setAssessments] = useState<TrendAssessment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [alias, setAlias] = useState("");
  const [status, setStatus] = useState("");
  const [plain, setPlain] = useState("");
  const [overrideStage, setOverrideStage] = useState("");
  const [overridePattern, setOverridePattern] = useState("");
  const [bundleMsg, setBundleMsg] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const h = await getHypeCandidate(id);
      setHype(h);
      setStatus(h.candidate_status);
      setPlain(h.plain_english || "");
      setOverrideStage(h.formation_stage || "");
      setOverridePattern(h.formation_pattern_suggested || h.formation_pattern || "");
      setTimeline(await getHypeTimeline(id));
      setSnapshots(await getHypeSnapshots(id));
      setSchedule(await getHypeSchedule(id));
      setAssessments(await getTrendAssessments(id));
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

  async function onOverride() {
    await postTrendOverride(id, {
      formation_stage: overrideStage || undefined,
      formation_pattern: overridePattern || undefined,
    });
    load();
  }

  async function onExportBundle() {
    const res = await exportResearchBundle(id);
    setBundleMsg(`Wrote ${res.path}`);
    try {
      await navigator.clipboard.writeText(res.prompt);
      setBundleMsg(`Wrote ${res.path} · ChatGPT research prompt copied`);
    } catch {
      /* clipboard optional */
    }
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
  const latest = assessments.length ? assessments[assessments.length - 1] : null;
  const suggested = (latest?.metrics_json as Record<string, unknown> | null)?.suggested as
    | Record<string, string>
    | undefined;

  return (
    <main>
      <p className="muted">
        <Link href="/hype-radar">← Hype Radar</Link>
      </p>
      <h1>{hype.canonical_name}</h1>
      <p className="sub">
        Formation stage / trend direction / pattern stay separate. No token inventory.
      </p>

      <section className="grid grid-2">
        <div className="panel">
          <h2>Current state</h2>
          <p>
            <span className="muted">Formation stage</span> {hype.formation_stage || "—"}
          </p>
          <p>
            <span className="muted">Trend direction</span> {hype.trend_direction || "—"}
          </p>
          <p>
            <span className="muted">Formation pattern</span>{" "}
            {hype.formation_pattern || hype.formation_pattern_suggested || "—"}
          </p>
          <p>
            <span className="muted">Confidence</span> {hype.pattern_confidence || "—"}
          </p>
          {latest?.is_manual_override ? (
            <p className="muted">
              Suggested: {suggested?.formation_pattern || "—"} / {suggested?.formation_stage || "—"}
              <br />
              Manual: {latest.formation_pattern} / {latest.formation_stage}
            </p>
          ) : null}
          <p>
            <span className="muted">Why</span> {(hype.why_moving || []).join(" · ") || "—"}
          </p>
          <p>
            <span className="muted">Missing evidence</span>{" "}
            {(hype.missing_evidence || []).join(" · ") || "—"}
          </p>
          <p>
            <span className="muted">Radar group</span> {hype.radar_group || "—"}
          </p>
        </div>
        <div className="panel">
          <h2>Origin</h2>
          <p>
            <span className="muted">Origin account</span>{" "}
            {hype.origin_account ? `@${hype.origin_account}` : "—"}
          </p>
          <p>
            <span className="muted">First signal</span> {hype.initial_trigger || "—"}
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
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Propagation</h2>
        <p>
          Independent amplifiers (origin excluded): {hype.independent_accounts ?? "—"}
          {hype.total_monitored_accounts != null
            ? ` · total monitored matches: ${hype.total_monitored_accounts}`
            : ""}
        </p>
        <p>
          Active platforms: {hype.platforms ?? "—"} · HQ amplifiers:{" "}
          {String(lastMeta.high_quality_independent_amplifier_count ?? lastMeta.high_quality_amplifier_count ?? "—")}
        </p>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Derivatives (post-T0 vs preexisting)</h2>
        <div className="grid grid-4">
          <div>
            <div className="stat-label">HN stories</div>
            <div className="stat">{String(lastMeta.hn_matching_story_count ?? "—")}</div>
          </div>
          <div>
            <div className="stat-label">GitHub new since T0</div>
            <div className="stat">
              {String(lastMeta.github_repo_count_post_t0 ?? lastMeta.github_repo_count ?? "—")}
            </div>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              Pre-existing: {String(lastMeta.github_repo_count_preexisting ?? "—")}
            </div>
          </div>
          <div>
            <div className="stat-label">HF Spaces new since T0</div>
            <div className="stat">
              {String(lastMeta.hf_space_count_post_t0 ?? lastMeta.hf_space_count ?? "—")}
            </div>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              Pre-existing: {String(lastMeta.hf_space_count_preexisting ?? "—")}
            </div>
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
        <h2>Actions</h2>
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
          <button type="button" className="btn" onClick={onExportBundle}>
            Export research bundle
          </button>
        </div>
        <form onSubmit={onAddAlias} className="inline-row" style={{ marginTop: 12 }}>
          <input placeholder="Add alias" value={alias} onChange={(e) => setAlias(e.target.value)} />
          <button className="btn" type="submit">
            Add alias
          </button>
        </form>
        {bundleMsg && <p className="muted">{bundleMsg}</p>}
        <div className="filters" style={{ marginTop: 12 }}>
          <select value={overrideStage} onChange={(e) => setOverrideStage(e.target.value)}>
            <option value="">Stage override…</option>
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select value={overridePattern} onChange={(e) => setOverridePattern(e.target.value)}>
            <option value="">Pattern override…</option>
            {PATTERNS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={onOverride}>
            Apply manual override
          </button>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          Manual override appends a new assessment; the prior engine suggestion is preserved in history.
        </p>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Trend timeline</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Assessed</th>
                <th>Stage</th>
                <th>Direction</th>
                <th>Pattern</th>
                <th>Version</th>
                <th>Override</th>
                <th>Deltas / reasons</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((a) => {
                const deltas = ((a.metrics_json || {}) as Record<string, unknown>).deltas as
                  | Record<string, number | null>
                  | undefined;
                const reasons = a.reasons_json || {};
                return (
                  <tr key={a.id}>
                    <td className="mono">{fmt(a.assessed_at)}</td>
                    <td>{a.formation_stage}</td>
                    <td>{a.trend_direction}</td>
                    <td>
                      {a.formation_pattern}
                      {a.pattern_confidence ? (
                        <div className="muted" style={{ fontSize: "0.75rem" }}>
                          {a.pattern_confidence}
                        </div>
                      ) : null}
                    </td>
                    <td className="mono">{a.engine_version}</td>
                    <td>{a.is_manual_override ? "yes" : "no"}</td>
                    <td className="muted" style={{ maxWidth: 280 }}>
                      {deltas
                        ? Object.entries(deltas)
                            .filter(([, v]) => typeof v === "number" && v !== 0)
                            .slice(0, 3)
                            .map(([k, v]) => `${k}=${v}`)
                            .join("; ") || "—"
                        : "—"}
                      <div>
                        {Array.isArray((reasons as Record<string, unknown>).direction)
                          ? ((reasons as Record<string, string[]>).direction || []).slice(0, 1).join("")
                          : ""}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {assessments.length === 0 && <p className="empty">No trend assessments yet.</p>}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Evidence trail</h2>
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
        <h2>Checkpoint schedule</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Checkpoint</th>
                <th>Status</th>
                <th>Target due</th>
                <th>Collected at</th>
                <th>Late by (s)</th>
                <th>Timing quality</th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((s) => (
                <tr key={s.id}>
                  <td>{s.checkpoint}</td>
                  <td>{statusLabel(s)}</td>
                  <td className="mono">{fmt(s.due_at)}</td>
                  <td className="mono">
                    {s.status === "COMPLETED" ? fmt(s.snapshot_at || s.completed_at) : "—"}
                  </td>
                  <td>{s.status === "COMPLETED" ? s.late_by_seconds ?? "—" : "—"}</td>
                  <td>{s.status === "COMPLETED" ? s.timing_quality || "—" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {schedule.length === 0 && <p className="empty">No schedule rows.</p>}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Snapshot history</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Checkpoint</th>
                <th>Collected at</th>
                <th>Mentions</th>
                <th>Indep. accounts</th>
                <th>Platforms</th>
                <th>Timing</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => {
                const meta = s.metadata_json || {};
                return (
                  <tr key={s.id}>
                    <td>{s.checkpoint || "—"}</td>
                    <td className="mono">{fmt(s.snapshot_at)}</td>
                    <td>{s.mention_count ?? "—"}</td>
                    <td>{s.independent_account_count ?? "—"}</td>
                    <td>{s.platform_count ?? "—"}</td>
                    <td>
                      {String(meta.timing_quality ?? "—")}
                      {meta.late_by_seconds != null ? ` (+${String(meta.late_by_seconds)}s)` : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {snapshots.length === 0 && (
          <p className="empty">No snapshots yet. SKIPPED historical checkpoints never invent data.</p>
        )}
      </section>
    </main>
  );
}
