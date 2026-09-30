"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { RawEvent, getEvent, getEvents } from "@/lib/api";

const columnHelper = createColumnHelper<RawEvent>();

type Filters = {
  platform: string;
  source: string;
  q: string;
  since: string;
  until: string;
};

const EMPTY_FILTERS: Filters = {
  platform: "",
  source: "",
  q: "",
  since: "",
  until: "",
};

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

function preview(e: RawEvent) {
  const t = e.title || e.raw_text || "";
  return t.length > 100 ? `${t.slice(0, 100)}…` : t || "—";
}

export default function EventsPage() {
  const [rows, setRows] = useState<RawEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [selected, setSelected] = useState<RawEvent | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    setError(null);
    getEvents({
      platform: applied.platform || undefined,
      source: applied.source || undefined,
      q: applied.q || undefined,
      since: applied.since ? new Date(applied.since).toISOString() : undefined,
      until: applied.until ? new Date(applied.until).toISOString() : undefined,
      limit: "200",
    })
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, [applied]);

  const columns = useMemo(
    () => [
      columnHelper.accessor("retrieved_at", {
        header: "Time",
        cell: (info) => <span className="mono">{fmt(info.getValue())}</span>,
      }),
      columnHelper.accessor("platform", { header: "Platform" }),
      columnHelper.accessor((r) => r.source_name || String(r.source_id), {
        id: "source",
        header: "Source",
      }),
      columnHelper.accessor("author", {
        header: "Author",
        cell: (info) => info.getValue() || "—",
      }),
      columnHelper.display({
        id: "preview",
        header: "Title / text preview",
        cell: (info) => preview(info.row.original),
      }),
      columnHelper.accessor("event_type", { header: "Event type" }),
      columnHelper.accessor("canonical_url", {
        header: "URL",
        cell: (info) => {
          const url = info.getValue();
          if (!url) return "—";
          return (
            <a href={url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              link
            </a>
          );
        },
      }),
    ],
    []
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  async function openDetail(row: RawEvent) {
    setLoadingDetail(true);
    try {
      const full = await getEvent(row.id);
      setSelected(full);
    } catch {
      setSelected(row);
    } finally {
      setLoadingDetail(false);
    }
  }

  return (
    <main>
      <h1>Raw Events</h1>
      <p className="sub">Browse stored evidence. Filters apply only when you click Apply.</p>

      <div className="filters">
        <select
          value={draft.platform}
          onChange={(e) => setDraft((d) => ({ ...d, platform: e.target.value }))}
        >
          <option value="">All platforms</option>
          <option value="hn">hn</option>
          <option value="official_rss">official_rss</option>
        </select>
        <input
          placeholder="Source name"
          value={draft.source}
          onChange={(e) => setDraft((d) => ({ ...d, source: e.target.value }))}
        />
        <input
          placeholder="Text search"
          value={draft.q}
          onChange={(e) => setDraft((d) => ({ ...d, q: e.target.value }))}
        />
        <input
          type="datetime-local"
          value={draft.since}
          onChange={(e) => setDraft((d) => ({ ...d, since: e.target.value }))}
        />
        <input
          type="datetime-local"
          value={draft.until}
          onChange={(e) => setDraft((d) => ({ ...d, until: e.target.value }))}
        />
        <button type="button" onClick={() => setApplied({ ...draft })}>
          Apply
        </button>
      </div>

      {error && <p className="sub">Error: {error}</p>}

      <div className="table-wrap">
        <table className="data">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="muted">
                  No events match.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} onClick={() => openDetail(row.original)}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="drawer-backdrop" onClick={() => setSelected(null)}>
          <aside className="drawer" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginTop: 0 }}>Event #{selected.id}</h2>
            {loadingDetail && <p className="muted">Loading…</p>}
            <p>
              <strong>{selected.title || "(no title)"}</strong>
            </p>
            <p className="muted">
              {selected.platform} · {selected.source_name} · {selected.event_type}
            </p>
            <p>
              <a href={selected.canonical_url || undefined} target="_blank" rel="noreferrer">
                {selected.canonical_url || "No URL"}
              </a>
            </p>
            <h3>Raw text</h3>
            <pre>{selected.raw_text || "null"}</pre>
            <h3>Metadata JSON</h3>
            <pre>{JSON.stringify(selected.metadata_json, null, 2)}</pre>
            <h3>Full record</h3>
            <pre>{JSON.stringify(selected, null, 2)}</pre>
            <button type="button" onClick={() => setSelected(null)}>
              Close
            </button>
          </aside>
        </div>
      )}
    </main>
  );
}
