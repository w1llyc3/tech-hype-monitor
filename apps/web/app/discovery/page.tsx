"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  discoverGithub,
  discoverHf,
  listEntities,
} from "@/lib/api";

type Tab = "github" | "models" | "spaces" | "datasets";

export default function DiscoveryPage() {
  const [q, setQ] = useState("vibe coding");
  const [tab, setTab] = useState<Tab>("github");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [entityIds, setEntityIds] = useState<Record<string, number>>({});

  const columns = useMemo(() => {
    if (tab === "github") {
      return ["Repo", "Owner", "Description", "Stars", "Forks", "Language", "Created", "Updated", "Link"];
    }
    return ["Repo ID", "Author", "Type", "Likes", "Downloads", "Last Modified", "Tags", "Link"];
  }, [tab]);

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      let data: Record<string, unknown>[] = [];
      if (tab === "github") {
        data = await discoverGithub(q);
      } else {
        data = await discoverHf(tab, q);
      }
      setRows(data);
      // Resolve persisted entity ids for detail links.
      const platform = tab === "github" ? "github" : "huggingface";
      const entities = await listEntities({ platform, q, limit: "100" });
      const map: Record<string, number> = {};
      for (const e of entities) {
        map[e.external_id] = e.id;
      }
      setEntityIds(map);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Discovery</h1>
      <p className="sub">
        Search public GitHub / Hugging Face. Results are persisted as tracked entities with metric
        observations — not hype judgments.
      </p>

      <div className="filters">
        <input
          style={{ minWidth: 260 }}
          placeholder="Search technology term..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") runSearch();
          }}
        />
        <button type="button" onClick={runSearch} disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      <div className="filters">
        {(
          [
            ["github", "GitHub"],
            ["models", "HF Models"],
            ["spaces", "HF Spaces"],
            ["datasets", "HF Datasets"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            style={{
              opacity: tab === id ? 1 : 0.65,
              background: tab === id ? "var(--accent)" : "var(--bg-soft)",
              color: tab === id ? "#041018" : "var(--text)",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="sub">Error: {error}</p>}

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="muted">
                  No results yet. Enter a query and search.
                </td>
              </tr>
            ) : tab === "github" ? (
              rows.map((r) => {
                const ext = String(r.external_id || "");
                const id = entityIds[ext];
                return (
                  <tr key={ext}>
                    <td>
                      {id ? <Link href={`/entities/${id}`}>{String(r.name || ext)}</Link> : String(r.name || ext)}
                    </td>
                    <td>{String(r.owner || "—")}</td>
                    <td>{String(r.description || "—").slice(0, 120)}</td>
                    <td>{String(r.stars ?? "—")}</td>
                    <td>{String(r.forks ?? "—")}</td>
                    <td>{String(r.language || "—")}</td>
                    <td className="mono">{String(r.created_at || "—").slice(0, 10)}</td>
                    <td className="mono">{String(r.updated_at || "—").slice(0, 10)}</td>
                    <td>
                      <a href={String(r.url || "#")} target="_blank" rel="noreferrer">
                        link
                      </a>
                    </td>
                  </tr>
                );
              })
            ) : (
              rows.map((r) => {
                const ext = String(r.external_id || r.repo_id || "");
                const id = entityIds[ext];
                return (
                  <tr key={ext}>
                    <td>
                      {id ? <Link href={`/entities/${id}`}>{ext}</Link> : ext}
                    </td>
                    <td>{String(r.author || "—")}</td>
                    <td>{String(r.entity_type || tab)}</td>
                    <td>{String(r.likes ?? "—")}</td>
                    <td>{r.downloads == null ? "—" : String(r.downloads)}</td>
                    <td className="mono">{String(r.last_modified || "—").slice(0, 19)}</td>
                    <td>{Array.isArray(r.tags) ? (r.tags as string[]).slice(0, 4).join(", ") : "—"}</td>
                    <td>
                      <a href={String(r.url || "#")} target="_blank" rel="noreferrer">
                        link
                      </a>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
