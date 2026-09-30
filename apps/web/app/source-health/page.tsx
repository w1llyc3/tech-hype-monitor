"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { SourceHealth, getSourceHealth } from "@/lib/api";

const columnHelper = createColumnHelper<SourceHealth>();

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function SourceHealthPage() {
  const [rows, setRows] = useState<SourceHealth[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSourceHealth()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  const columns = useMemo(
    () => [
      columnHelper.accessor("name", { header: "Source" }),
      columnHelper.accessor("source_type", { header: "Type" }),
      columnHelper.accessor("enabled", {
        header: "Enabled",
        cell: (info) => (info.getValue() ? "yes" : "no"),
      }),
      columnHelper.accessor("last_success_at", {
        header: "Last success",
        cell: (info) => <span className="mono">{fmt(info.getValue())}</span>,
      }),
      columnHelper.accessor("last_error", {
        header: "Last error",
        cell: (info) => {
          const err = info.getValue();
          const at = info.row.original.last_error_at;
          if (!err) return "—";
          return (
            <span title={fmt(at)}>
              {err.length > 80 ? `${err.slice(0, 80)}…` : err}
            </span>
          );
        },
      }),
      columnHelper.accessor("events_24h", { header: "Events 24h" }),
      columnHelper.accessor("status", {
        header: "Status",
        cell: (info) => <span className={`badge ${info.getValue()}`}>{info.getValue()}</span>,
      }),
    ],
    []
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <main>
      <h1>Source Health</h1>
      <p className="sub">
        Adapter state only. A quiet period with no new events is not treated as failure.
      </p>
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
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} style={{ cursor: "default" }}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
